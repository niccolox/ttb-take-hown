"""DuckDB-backed session state.

One saved session per deployment (the prototype is single-reviewer): Save
snapshots the whole batch — applications, verdicts, overrides, and the label
panel images themselves (BLOBs) — so a browser reload or restart can restore
the exact review state. Clear drops it. The database file lives in api/data/
(gitignored — it contains uploaded label images and reviewer decisions).
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "state.duckdb"

_lock = threading.Lock()          # duckdb connections aren't thread-safe; FastAPI is threaded


def _connect():
    import duckdb
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute("""
        CREATE TABLE IF NOT EXISTS session_meta (
            k TEXT PRIMARY KEY, v TEXT)""")
    con.execute("""
        CREATE TABLE IF NOT EXISTS session_items (
            idx INTEGER PRIMARY KEY,
            file_name TEXT,
            state TEXT,
            override TEXT,
            application TEXT,      -- JSON
            result TEXT)           -- JSON (null when not yet verified)
        """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS session_panels (
            item_idx INTEGER,
            panel TEXT,
            file_name TEXT,
            mime TEXT,
            data BLOB)""")
    return con


def save_session(items: list[dict], panel_blobs: list[tuple[int, str, str, str, bytes]]) -> dict:
    """items: [{file_name, state, override, application, result}] in order.
    panel_blobs: [(item_idx, panel, file_name, mime, bytes)]. Replaces any
    previously saved session."""
    with _lock:
        con = _connect()
        try:
            con.execute("BEGIN")
            con.execute("DELETE FROM session_items")
            con.execute("DELETE FROM session_panels")
            con.execute("DELETE FROM session_meta")
            for i, it in enumerate(items):
                con.execute(
                    "INSERT INTO session_items VALUES (?, ?, ?, ?, ?, ?)",
                    [i, it.get("file_name") or "", it.get("state") or "waiting",
                     it.get("override"), json.dumps(it.get("application") or {}),
                     json.dumps(it["result"]) if it.get("result") else None])
            for idx, panel, fname, mime, data in panel_blobs:
                con.execute("INSERT INTO session_panels VALUES (?, ?, ?, ?, ?)",
                            [idx, panel, fname, mime, data])
            saved_at = time.strftime("%Y-%m-%d %H:%M:%S")
            con.execute("INSERT INTO session_meta VALUES ('saved_at', ?)", [saved_at])
            con.execute("INSERT INTO session_meta VALUES ('item_count', ?)",
                        [str(len(items))])
            con.execute("COMMIT")
            return {"saved_at": saved_at, "item_count": len(items)}
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()


def load_session() -> dict | None:
    """Full session (without image bytes — those stream via get_panel)."""
    if not DB_PATH.exists():
        return None
    with _lock:
        con = _connect()
        try:
            meta = dict(con.execute("SELECT k, v FROM session_meta").fetchall())
            if not meta:
                return None
            rows = con.execute("""
                SELECT idx, file_name, state, override, application, result
                FROM session_items ORDER BY idx""").fetchall()
            panels = con.execute("""
                SELECT item_idx, panel, file_name FROM session_panels
                ORDER BY item_idx, CASE panel WHEN 'front' THEN 0 ELSE 1 END""").fetchall()
            by_item: dict[int, list] = {}
            for idx, panel, fname in panels:
                by_item.setdefault(idx, []).append({"panel": panel, "file": fname})
            return {
                "saved_at": meta.get("saved_at"),
                "items": [{
                    "idx": idx, "file_name": fname, "state": state, "override": override,
                    "application": json.loads(app) if app else {},
                    "result": json.loads(result) if result else None,
                    "panels": by_item.get(idx, []),
                } for idx, fname, state, override, app, result in rows],
            }
        finally:
            con.close()


def get_panel(item_idx: int, panel: str) -> tuple[bytes, str] | None:
    if not DB_PATH.exists():
        return None
    with _lock:
        con = _connect()
        try:
            row = con.execute(
                "SELECT data, mime FROM session_panels WHERE item_idx = ? AND panel = ?",
                [item_idx, panel]).fetchone()
            return (bytes(row[0]), row[1] or "image/jpeg") if row else None
        finally:
            con.close()


def clear_session() -> None:
    with _lock:
        con = _connect()
        try:
            con.execute("DELETE FROM session_items")
            con.execute("DELETE FROM session_panels")
            con.execute("DELETE FROM session_meta")
        finally:
            con.close()


def session_summary() -> dict | None:
    if not DB_PATH.exists():
        return None
    with _lock:
        con = _connect()
        try:
            meta = dict(con.execute("SELECT k, v FROM session_meta").fetchall())
            if not meta:
                return None
            return {"saved_at": meta.get("saved_at"),
                    "item_count": int(meta.get("item_count") or 0)}
        finally:
            con.close()
