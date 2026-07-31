# Codex DX Voice (developer experience challenge) — 2026-07-31

Overall: strong product and systems thinking, weak evaluator-facing developer experience. The plan explains what to build far better than how a stranger will run, inspect, and verify it.

Estimated developer-experience readiness: **4.2/10**.

| Dimension | Score | Adversarial assessment |
|---|---:|---|
| Getting started | 4/10 | `docker compose up` is named, but the complete clone-to-browser path is unspecified. |
| API naming/design | 4/10 | `/api/verify` is reasonable, but the contract is mostly absent. |
| Setup error messages | 2/10 | Excellent in-app errors; almost no startup/installation diagnostics. |
| Docs/discoverability | 5/10 | Good intended content, but README work is deferred to M4 and no information architecture is defined. |
| Upgrade/reproducibility | 4/10 | Tests and evaluation are mentioned, but locking, commands, fixtures, and expected outputs are not. |
| Dev-environment friction | 3/10 | Docker may be simple after download; the native path is effectively undefined. |

## 1. Time to hello world

The under-five-minute target is not reliably plausible for a fresh clone.

A 2–4 GB compressed image alone takes approximately:

- 1 Gbps: 20–45 seconds theoretically, perhaps 1–2 minutes in practice.
- 100 Mbps: 3–6 minutes just to download.
- 25 Mbps: 11–22 minutes.
- Corporate VPN or throttled registry: potentially much longer.

That excludes cloning, extraction, container creation, model initialization, health checks, and first-page load. “Models baked” avoids an additional runtime download, but only if PaddleOCR is explicitly configured never to fetch or validate remote assets during startup.

Realistic TTHW estimates:

- Warm image cache: **1–3 minutes**
- Fast connection, cold cache: **4–8 minutes**
- Typical home/corporate connection: **8–20 minutes**
- Native installation from scratch: **20–60+ minutes**, assuming it works

Therefore the requirement should be split:

- **Under 5 minutes of developer interaction**
- **Under 2 minutes after the image is locally available**
- Publish the expected image download size and likely cold-start time honestly

The plan needs an exact golden path, for example:

```bash
git clone ...
cd treasury-instructions
docker compose up --build
# Open http://localhost:8000
```

That command is not necessarily ideal, though: `--build` can make first run much slower. A prebuilt, versioned image plus a separate contributor build command would produce a better evaluator experience.

The local no-Docker path is missing. “Next.js remains the build toolchain only” describes the production artifact, not native development. A new developer cannot tell:

- Supported Python and Node versions
- Whether Node is needed for normal backend work
- How OCR models are installed
- Where models live
- Whether CPU-only Paddle is installed
- How to build the static frontend
- How to launch FastAPI
- Whether separate hot-reload processes are supported
- How much disk and memory are required

A credible native path needs one copy-paste sequence, ideally behind `make dev`, `just dev`, or a bootstrap script. Otherwise explicitly say Docker is the only supported evaluator path and describe native setup as contributor-only.

## 2. Setup and startup errors

The plan is unusually thorough about errors after the app opens, but nearly silent about errors before it opens. That is a major DX mismatch.

Required startup diagnostics include:

| Failure | What the developer should see | Recovery |
|---|---|---|
| Docker missing | “Docker 24+ with Compose v2 is required.” | Installation link and native alternative |
| Docker daemon stopped | Distinguish this from missing CLI | Start Docker Desktop/service |
| Port occupied | Name port and owning conflict when possible | `APP_PORT=8001 docker compose up` |
| Insufficient memory | State detected/required memory | Reduce workers or allocate ≥N GB |
| Insufficient disk | State image size and required free space | Free ≥N GB |
| Wrong CPU architecture | State supported platforms | Use provided amd64/arm64 image or build locally |
| Model missing/corrupt | Name exact asset and expected checksum | Rebuild or run model verification |
| Unexpected model download | Fail clearly in offline mode | Bake assets correctly |
| Slow warm-up | “Loading OCR models; first startup may take N seconds” | Wait, with health status |
| Worker failed to initialize | Preserve the underlying Paddle/native-library error | Switch to single-worker mode or documented platform fix |

“Model warmed at container boot” creates another usability issue: Docker may report the process as running while the app is not ready. The Compose service needs a health check, and the UI or `/health/ready` endpoint should distinguish:

- Process alive
- Models loading
- Ready for verification
- Degraded to fewer workers

The plan mentions single-worker fallback, but not how it is activated. This should be a documented environment variable with a safe default, such as `OCR_WORKERS=1`.

## 3. API design

`POST /api/verify` is understandable, but multipart image plus loosely described fields is not sufficiently guessable. The plan needs an explicit contract.

Open questions include:

- Is the file part named `image`, `file`, or `label`?
- Are application fields individual multipart parts or one JSON part?
- Which fields are optional?
- Are empty strings equivalent to omitted fields?
- How are numeric values and units represented?
- Is the endpoint synchronous despite the ten-second timeout?
- Is batch processing a separate endpoint?
- How are status and reason values enumerated?
- How are image crops returned: base64, URLs, coordinates, or all three?
- How does the API distinguish validation errors, OCR failure, overload, and timeout?
- Are application values echoed exactly?
- Is there a request or correlation ID?

A cleaner multipart contract would use:

- `image`: binary file
- `application`: JSON string conforming to a documented schema

That avoids multipart field proliferation and makes future schema evolution easier.

The response needs a stable envelope, not just the hour-one sketch:

```json
{
  "schema_version": "1",
  "request_id": "...",
  "screening_result": "mismatch_found",
  "attention_state": "action_required",
  "timing_ms": {
    "total": 1842,
    "ocr": 1620,
    "rules": 3
  },
  "fields": [
    {
      "field": "brand_name",
      "status": "mismatch",
      "label_value": "Old Tom Distilling Co.",
      "application_value": "Old Tom Distillery",
      "reason_code": "value_differs",
      "evidence": {
        "bbox": [100, 120, 420, 190],
        "crop_url": "..."
      }
    }
  ],
  "warnings": []
}
```

The plan also conflates human-facing language with machine-facing reason codes. Stable codes should be separate from display copy.

FastAPI normally provides OpenAPI, Swagger UI, and ReDoc, but the plan does not promise that they remain enabled or reachable. Static-file routing can also accidentally swallow `/docs` if mounted carelessly. Make these explicit acceptance criteria:

- `/docs`
- `/redoc`
- `/openapi.json`
- A copy-paste `curl` example checked in CI
- Error schemas and examples included in OpenAPI

A `/api/v1/verify` route would give an on-prem contractor a clearer compatibility boundary. For a take-home, unversioned `/api/verify` is acceptable only if the schema is explicitly versioned.

## 4. Documentation

The architecture argument is strong in the plan, but evaluator discoverability is not secured. “README leads with…” is only an intention, and README creation is deferred to M4. That makes the most important evaluator artifact a late-stage risk.

Within two minutes, the README should reveal, in this order:

1. What the app does, with screenshot or short GIF
2. One-command run and exact URL
3. “Try these five samples”
4. Architecture in one diagram or six lines
5. Why deterministic rules issue verdicts and OCR does not
6. Current measured latency and hardware
7. Limitations and assumptions
8. Test and evaluation commands
9. On-prem/offline deployment notes

The plan repeats architecture reasoning at length but does not define a concise evaluator path. A 30-minute reviewer should not need to excavate the plan or implementation to discover the main argument.

Measured latency must include:

- Commit or image version
- CPU model, RAM, architecture, and worker count
- Dataset size and image characteristics
- Cold startup time
- Warm p50/p95
- Batch throughput
- Peak RSS
- Accuracy or routing metrics, especially warning exact-match behavior

“PaddleOCR on CPU: ~1–2s” conflicts with the later, more cautious “3–8s on shared vCPUs.” The README must prominently label unmeasured estimates and replace them with actual results. Until M0 data exists, the plan should not imply that the five-second requirement is met.

All commands should be copy-paste complete and tested from a clean checkout. Avoid placeholders such as `docker compose up` without stating URL, expected startup text, health check, memory requirements, and how to stop/reset it.

## 5. Reproducibility and upgrades

“One-command tests” and “one-command eval” are not currently designed; only their existence is mentioned.

The plan should require named commands such as:

```bash
make test
make eval
make smoke
make lint
```

Their scope and output should be explicit:

- `make test`: deterministic unit tests; no network or model download
- `make eval`: golden images plus OCR models; emits machine-readable and Markdown results
- `make smoke`: starts the built container, waits for readiness, calls `/api/verify`, then exits
- `make lint`: Python and TypeScript checks

Dependency pinning also needs definition:

- Fully locked Python transitive dependencies
- Locked npm dependencies with committed lockfile
- Docker base image pinned by digest
- Paddle/PaddleOCR/OpenCV versions pinned
- OCR models vendored or downloaded by checksum during build
- Model version and checksum exposed in diagnostics
- Multi-architecture policy documented
- Golden-set expected metrics versioned with tolerated ranges

For offline/on-prem use, add an automated no-egress test. Merely asserting that no cloud API exists does not prove Paddle, font loading, analytics, package code, or the frontend will not attempt outbound access.

The evaluation dataset also needs provenance and licensing documentation. “AI-generated labels” is not enough for a future contractor to know whether fixtures can be redistributed or compared across releases.

## Highest-priority changes

Before implementation, I would add these acceptance criteria:

1. A clean-machine smoke test demonstrating clone-to-sample-result.
2. Two explicit run paths: prebuilt Docker image and native contributor setup.
3. Published minimum RAM, disk, architecture, image size, and startup duration.
4. Readiness endpoint with visible model-loading progress and actionable startup failures.
5. A versioned request/response schema with `curl`, OpenAPI examples, and documented error envelopes.
6. README completed in M1, not M4.
7. `make test`, `make eval`, and `make smoke` operating without undocumented prerequisites.
8. Fully pinned dependencies, models, and base images.
9. CI that builds from a clean checkout and verifies no runtime model download.
10. Measured TTHW as a release metric, separately reporting image download and application readiness.

The core architecture will impress an evaluator once understood. The present risk is that they spend much of their 30 minutes downloading a huge image, interpreting opaque startup behavior, and reverse-engineering an API whose contract exists only implicitly.
