"""Conservative refinement merge (PLAN-enrichment AD-20).

Deliberately SEPARATE from verify_multi's `_MERGE_RANK` — the logged eng
learning: panel merges prefer definitive positives (a MATCH on any panel
wins), which is exactly wrong for refinement tiers, where a later layer's
MATCH must not silently override the primary read.

Rules (full status lattice, not the 3-state triangle):
- Downgrades (toward review/red) apply immediately.
- Discovery (base located nothing; the layer found text) applies
  immediately — it can create a MISMATCH.
- Upgrades to green require corroboration: `upgrade_ok=True` means the
  AD-20 condition holds (two independent agreeing reads, or the
  privileged J2 warning-reread WITH J1 guard concurrence). Without it
  the upgrade is recorded as an annotation, never applied.
- Every applied change appends provenance to `field["refinements"]`.
"""

from __future__ import annotations

GREEN = {"MATCH", "LIKELY_MATCH", "WITHIN_TOLERANCE", "NOT_REQUIRED"}
REVIEW = {"NEEDS_REVIEW", "NOT_CHECKED"}
RED = {"MISMATCH"}

_SEVERITY = {**{s: 0 for s in GREEN}, **{s: 1 for s in REVIEW},
             **{s: 2 for s in RED}}


def classify(base_status: str, new_status: str, base_located: bool,
             new_located: bool) -> str:
    """→ 'same' | 'downgrade' | 'upgrade' | 'discovery'."""
    if new_status == base_status:
        return "same"
    if not base_located and new_located:
        return "discovery"
    if _SEVERITY.get(new_status, 1) > _SEVERITY.get(base_status, 1):
        return "downgrade"
    return "upgrade"


def merge_refinement(field: dict, refined: dict, layer: str, engine: str,
                     upgrade_ok: bool, note: str = "",
                     refresh_on_same: bool = False) -> bool:
    """Mutates `field` in place (caller holds the store's entry lock via
    ResultStore.mutate). Returns True when the status changed.

    `refresh_on_same`: a higher-fidelity re-read (J2) that CONFIRMS the
    status still carries better details — corrected sub-checks, label text,
    evidence. Without refreshing them, a reviewer acts on the fast read's
    artifacts (e.g. the dropout's 'word missing' line surviving on a
    titlecase trap whose real defect is the caps violation)."""
    base_status = field["status"]
    kind = classify(base_status, refined["status"],
                    base_located=field.get("label_value") is not None,
                    new_located=refined.get("label_value") is not None)
    prov = {"layer": layer, "engine": engine, "from": base_status,
            "to": refined["status"], "kind": kind, "applied": False,
            "note": note or refined.get("note", "")}
    field.setdefault("refinements", []).append(prov)

    if kind == "same":
        if refresh_on_same:
            prov["details_refreshed"] = True
            for key in ("label_value", "reason_code", "note", "evidence",
                        "sub_results"):
                if key in refined:
                    field[key] = refined[key]
        return False
    if kind == "upgrade" and not upgrade_ok:
        # recorded, never applied — a single uncorroborated read cannot
        # green a field (the anti-_MERGE_RANK rule)
        return False

    prov["applied"] = True
    for key in ("status", "label_value", "reason_code", "note", "evidence",
                "sub_results"):
        if key in refined:
            field[key] = refined[key]
    return True
