"""In-process job queue + result store (PLAN-enrichment N1).

Design constraints from the plan's review decisions:
- AD-23: background jobs get their OWN executor, never the fast-path pool.
- AD-25: correctness requires a single app process (one store instance).
- AD-27: terminality is server-side — a watchdog forces `timed_out`/`lost`;
  late completions hit a tombstone check inside the store lock; every
  enqueued job writes exactly one terminal state, exception paths included;
  durations use monotonic time.
- AD-28: TTL is idle-based (touched on every read/mutate).
- AD-32: `revision` increments on EVERY store mutation, including
  job-state-only transitions, and field order is preserved by mutators.
- AD-13/AD-38: jobs can terminate as `shed` (refused at submit) and the
  POST response must be able to say so immediately.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
TIMED_OUT = "timed_out"
CANCELLED = "cancelled"
SHED = "shed"
LOST = "lost"
TERMINAL = frozenset({DONE, FAILED, TIMED_OUT, CANCELLED, SHED, LOST})

QUEUE_BOUND = 64
DEFAULT_TTL_S = 3600.0
DEFAULT_DEADLINE_S = 60.0
WATCHDOG_INTERVAL_S = 5.0
# `lost` guard: a job pending far past its deadline with no worker having
# picked it up means the executor died or the entry was dropped mid-submit.
LOST_GRACE_S = 30.0


@dataclass
class Job:
    layer: str
    state: str = PENDING
    submitted_at: float = 0.0      # monotonic
    started_at: float | None = None
    deadline_s: float = DEFAULT_DEADLINE_S
    error: str | None = None

    def public(self) -> dict:
        return {"layer": self.layer, "state": self.state}


@dataclass
class _Entry:
    result: dict
    revision: int = 1
    jobs: dict[str, Job] = field(default_factory=dict)
    cancel_token: str = field(default_factory=lambda: str(uuid.uuid4()))
    last_access: float = field(default_factory=time.monotonic)
    cancelled: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def settled(self) -> bool:
        return all(j.state in TERMINAL for j in self.jobs.values())

    def public(self) -> dict:
        status = "settled" if self.settled() else "provisional"
        return {**self.result,
                "result_id": self.result.get("request_id"),
                "status": status, "settled": status == "settled",
                "revision": self.revision,
                "pending": [j.public() for j in self.jobs.values()
                            if j.state not in TERMINAL],
                "jobs": [j.public() for j in self.jobs.values()]}


class ResultStore:
    """In-memory, single-process (AD-25). Idle-based TTL; reaped ids are
    remembered (bounded) so GET can answer `expired` vs `not_found`."""

    def __init__(self, ttl_s: float = DEFAULT_TTL_S, max_expired_ids: int = 1000):
        self._items: dict[str, _Entry] = {}
        self._expired: OrderedDict[str, None] = OrderedDict()
        self._max_expired = max_expired_ids
        self._ttl_s = ttl_s
        self._lock = threading.Lock()          # guards the maps, not entries

    def put(self, result: dict) -> _Entry:
        rid = result["request_id"]
        entry = _Entry(result=result)
        with self._lock:
            self._items[rid] = entry
        return entry

    def get(self, rid: str) -> _Entry | None:
        with self._lock:
            entry = self._items.get(rid)
        if entry is not None:
            entry.last_access = time.monotonic()
        return entry

    def status_of_missing(self, rid: str) -> str:
        with self._lock:
            return "expired" if rid in self._expired else "not_found"

    def mutate(self, rid: str, fn) -> bool:
        """Run `fn(entry)` under the entry lock and bump revision (AD-32).
        Returns False when the entry is gone or cancelled (tombstone check
        inside the lock — a late job completion must not resurrect state)."""
        entry = self.get(rid)
        if entry is None:
            return False
        with entry.lock:
            if entry.cancelled:
                return False
            fn(entry)
            entry.revision += 1
            entry.last_access = time.monotonic()
        return True

    def cancel(self, rid: str) -> bool:
        entry = self.get(rid)
        if entry is None:
            return False
        with entry.lock:
            entry.cancelled = True
            for j in entry.jobs.values():
                if j.state not in TERMINAL:
                    j.state = CANCELLED
            entry.revision += 1
        return True

    def reap(self) -> int:
        """Remove idle entries. Entry locks are taken so a reap never races a
        merge mid-mutation (the mutate holds the lock while writing)."""
        now = time.monotonic()
        reaped = 0
        with self._lock:
            for rid in list(self._items):
                entry = self._items[rid]
                if now - entry.last_access <= self._ttl_s:
                    continue
                with entry.lock:
                    entry.cancelled = True         # tombstone: late merges reject
                    del self._items[rid]
                    self._expired[rid] = None
                    while len(self._expired) > self._max_expired:
                        self._expired.popitem(last=False)
                reaped += 1
        return reaped


class JobQueue:
    """Bounded background executor (AD-23). Submit either enqueues a job or
    sheds it AT SUBMIT TIME (AD-27) — callers learn `shed` in the POST
    response, not by polling."""

    def __init__(self, store: ResultStore, workers: int = 2,
                 bound: int = QUEUE_BOUND,
                 watchdog_interval_s: float = WATCHDOG_INTERVAL_S):
        self._store = store
        self._bound = bound
        self._inflight = 0
        self._watch_every = watchdog_interval_s
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=workers,
                                            thread_name_prefix="labelcheck-job")
        self._watchdog = threading.Thread(target=self._watch, daemon=True,
                                          name="labelcheck-job-watchdog")
        self._stop = threading.Event()
        self._watchdog.start()

    # -- public -----------------------------------------------------------

    def depth(self) -> int:
        with self._lock:
            return self._inflight

    def oldest_age_s(self) -> float:
        oldest = None
        now = time.monotonic()
        for entry in list(self._store._items.values()):
            for j in entry.jobs.values():
                if j.state in (PENDING, RUNNING):
                    age = now - j.submitted_at
                    oldest = age if oldest is None else max(oldest, age)
        return round(oldest or 0.0, 1)

    def submit(self, rid: str, layer: str, fn,
               deadline_s: float = DEFAULT_DEADLINE_S) -> str:
        """Returns the job's initial state: `pending` or `shed`."""
        job = Job(layer=layer, submitted_at=time.monotonic(),
                  deadline_s=deadline_s)
        with self._lock:
            if self._inflight >= self._bound:
                job.state = SHED
            else:
                self._inflight += 1
        # record the job on the entry either way — `shed` is a terminal
        # state the client sees in the POST response (AD-13)
        added = self._store.mutate(rid, lambda e: e.jobs.__setitem__(layer, job))
        if not added:
            if job.state != SHED:
                with self._lock:
                    self._inflight -= 1
            return SHED
        if job.state == SHED:
            return SHED
        self._executor.submit(self._run, rid, layer, fn)
        return PENDING

    def cancel_result(self, rid: str) -> bool:
        return self._store.cancel(rid)

    def shutdown(self) -> None:
        self._stop.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    # -- internals --------------------------------------------------------

    def _set_state(self, rid: str, layer: str, state: str,
                   error: str | None = None, only_from: tuple = ()) -> None:
        def fn(entry):
            j = entry.jobs.get(layer)
            if j is None or j.state in TERMINAL:
                return                      # exactly-one-terminal-state guard
            if only_from and j.state not in only_from:
                return
            j.state = state
            j.error = error
            if state == RUNNING:
                j.started_at = time.monotonic()
        self._store.mutate(rid, fn)

    def _run(self, rid: str, layer: str, fn) -> None:
        try:
            self._set_state(rid, layer, RUNNING, only_from=(PENDING,))
            entry = self._store.get(rid)
            if entry is None or entry.cancelled:
                return                       # cancelled while queued
            j = entry.jobs.get(layer)
            if j is None or j.state != RUNNING:
                return                       # watchdog/cancel got there first
            fn()                             # the layer's work; merges via store.mutate
            self._set_state(rid, layer, DONE)
        except Exception as exc:             # exactly one terminal state, always
            self._set_state(rid, layer, FAILED, error=repr(exc)[:200])
        finally:
            with self._lock:
                self._inflight -= 1

    def _watch(self) -> None:
        while not self._stop.wait(self._watch_every):
            now = time.monotonic()
            for rid, entry in list(self._store._items.items()):
                for layer, j in list(entry.jobs.items()):
                    if j.state == RUNNING and j.started_at is not None \
                            and now - j.started_at > j.deadline_s:
                        self._set_state(rid, layer, TIMED_OUT)
                    elif j.state == PENDING \
                            and now - j.submitted_at > j.deadline_s + LOST_GRACE_S:
                        self._set_state(rid, layer, LOST)
            self._store.reap()
