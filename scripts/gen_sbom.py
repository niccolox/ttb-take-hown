"""SBOM generator (audit F4): CycloneDX 1.5 from the repo's own trust
artifacts — api/requirements.lock (names, versions, SHA-256s) and
api/models.sha256 (OCR weight digests) — plus license metadata from the
installed environment and PRC-origin annotations per the 2026 SBOM
Minimum Elements (CISA/NSA/FBI: component hash, license, generation
context) and docs/research/ai-supply-chain-risk.md.

Fully offline; no SBOM toolchain dependency. Run:
    .venv/bin/python scripts/gen_sbom.py            # writes sbom/labelcheck.cdx.json
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parents[1]
LOCK = ROOT / "api" / "requirements.lock"
WEIGHTS = ROOT / "api" / "models.sha256"
OUT = ROOT / "sbom" / "labelcheck.cdx.json"

# PRC-origin components flagged by the supply-chain research; mitigations
# are the shipped controls, stated so the SBOM answers the M-26-05 question
PRC_ORIGIN = {
    "paddleocr": "Baidu (PRC) — mitigations: version+hash pinned, weights "
                 "SHA-256 pinned (api/models.sha256), no-egress runtime, "
                 "no telemetry path",
    "paddlepaddle": "Baidu (PRC) — same mitigations as paddleocr",
    "paddlex": "Baidu (PRC) — transitive; same mitigations",
    "aistudio-sdk": "Baidu (PRC) — transitive, never imported at runtime",
    "modelscope": "Alibaba (PRC) — transitive, never imported at runtime",
}


def parse_lock() -> list[dict]:
    """(name, version, [sha256...]) triples from the pip-compile lock."""
    entries: list[dict] = []
    current: dict | None = None
    for raw in LOCK.read_text().splitlines():
        line = raw.strip()
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^ \\;]+)", line)
        if m:
            current = {"name": m.group(1).lower(), "version": m.group(2),
                       "hashes": []}
            entries.append(current)
            continue
        h = re.search(r"--hash=sha256:([0-9a-f]{64})", line)
        if h and current is not None:
            current["hashes"].append(h.group(1))
    return entries


def license_of(name: str) -> str | None:
    try:
        from importlib.metadata import metadata
        md = metadata(name)
    except Exception:
        return None
    lic = md.get("License-Expression") or md.get("License")
    if lic and lic.strip() and lic.strip().upper() != "UNKNOWN" and len(lic) < 120:
        return lic.strip()
    for c in md.get_all("Classifier") or []:
        if c.startswith("License ::"):
            return c.split("::")[-1].strip()
    return None


def main() -> int:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                            capture_output=True, text=True).stdout.strip()
    components = []
    for e in parse_lock():
        comp = {
            "type": "library",
            "name": e["name"],
            "version": e["version"],
            "purl": f"pkg:pypi/{e['name']}@{e['version']}",
            "hashes": [{"alg": "SHA-256", "content": h} for h in e["hashes"][:1]],
        }
        lic = license_of(e["name"])
        if lic:
            comp["licenses"] = [{"license": {"name": lic}}]
        if e["name"] in PRC_ORIGIN:
            comp["properties"] = [
                {"name": "labelcheck:origin-risk", "value": PRC_ORIGIN[e["name"]]}]
        components.append(comp)

    for line in WEIGHTS.read_text().strip().splitlines():
        digest, name = line.split()
        components.append({
            "type": "machine-learning-model",
            "name": f"paddleocr-weights/{name}",
            "version": "pinned-2026-08-02",
            "hashes": [{"alg": "SHA-256", "content": digest}],
            "properties": [
                {"name": "labelcheck:origin-risk",
                 "value": "Baidu (PRC) CDN download — integrity asserted at "
                          "image build AND extractor warm (api/integrity.py)"},
            ],
        })

    bom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "component": {"type": "application", "name": "labelcheck",
                          "version": commit[:12] or "unversioned"},
            "properties": [
                {"name": "labelcheck:generation-context",
                 "value": "scripts/gen_sbom.py from api/requirements.lock "
                          "(hash-locked install source) + api/models.sha256 "
                          f"at commit {commit[:12]}"},
            ],
        },
        "components": components,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(bom, indent=1) + "\n")
    n_lic = sum(1 for c in components if c.get("licenses"))
    print(f"wrote {OUT.relative_to(ROOT)}: {len(components)} components "
          f"({n_lic} with licenses, {sum(1 for c in components if c.get('properties'))} "
          f"origin-annotated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
