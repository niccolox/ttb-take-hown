"""The golden manifest carries two ABV facts per case: abv_line (what the
label prints) and app_abv (what the COLA application declares). The eval-set
loader must feed app_abv to the application record — falling back to the
label's own value defeated the ABV traps (exact match instead of band
checks) and left the table wine's application blank (NOT_CHECKED instead of
the §4.36(a) NOT_REQUIRED the case exists to demonstrate)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

MANIFEST = Path(__file__).parents[1] / "eval" / "golden" / "manifest.json"

# case id -> (application ABV, label-printed ABV)
SPLIT_CASES = {
    "wine_no_abv_table": ("12.5%", None),
    "trap_abv_within_band": ("45% Alc./Vol.", "45.2% Alc./Vol."),
    "trap_abv_outside_band": ("45% Alc./Vol.", "46% Alc./Vol. (92 Proof)"),
}


def test_manifest_splits_application_abv_from_label_abv():
    entries = {e["id"]: e for e in json.loads(MANIFEST.read_text())}
    for cid, (app_abv, label_abv) in SPLIT_CASES.items():
        t = entries[cid]["truth"]
        assert t["app_abv"] == app_abv, cid
        assert t.get("abv_line") == label_abv, cid


def test_corpus_loader_prefers_declared_abv():
    from api.main import _corpus_items
    items = {i["id"]: i for i in _corpus_items("golden")}
    for cid, (app_abv, _) in SPLIT_CASES.items():
        assert items[cid]["application"]["alcohol_content"] == app_abv, cid
    # non-split cases keep label == application (spirits_clean prints 45%)
    assert items["spirits_clean"]["application"]["alcohol_content"] == "45% Alc./Vol. (90 Proof)"
