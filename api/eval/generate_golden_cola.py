"""Per-pipeline golden generator: synthetic front+back label pairs patterned
on the REAL label structures in each COLA Cloud corpus (layout, field mix,
panel split — the warning on the back, imported-by blocks, appellations),
with FICTIONAL brands and controlled ground truth.

Why: the pulled corpora are capped at ~700px by the provider's CDN and their
registry records carry no per-field expectations — these goldens give each
pipeline a full-resolution, known-truth equivalent (clean by construction:
verdicts should be green/amber-explainable, never false mismatches).

Deterministic — no randomness; regeneration is byte-stable per Pillow build.
Output: api/eval/golden_cola/<pipeline>/{id}_{front,back}.jpg + manifest.json
(corpus schema; auto-registered by get_corpora as golden_<pipeline>).

Run: .venv/bin/python -m api.eval.generate_golden_cola
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from .generate_golden import (WARNING_TEXT, degrade_glare, degrade_skew,
                              draw_warning, font, wrap)

OUT = Path(__file__).parent / "golden_cola"


def degrade_blur(img: Image.Image) -> Image.Image:
    from PIL import ImageFilter
    return img.filter(ImageFilter.GaussianBlur(2.2))


def degrade_dark(img: Image.Image) -> Image.Image:
    from PIL import ImageEnhance
    return ImageEnhance.Brightness(img).enhance(0.45)


# Photographic degradations applied to the WINE golden (both panels — a bad
# phone photo degrades front and back alike). Expectations follow the
# ratified screening posture: recoverable degradations stay green (S0
# deskew handles the angle; the refinement layers recover blur), and
# anything unrecoverable degrades to honest NEEDS_REVIEW — never a false
# MISMATCH on a compliant label.
WINE_DEGRADATIONS = [
    ("blur", degrade_blur, "blurry phone photo"),
    ("angle", lambda im: degrade_skew(im, angle=7), "photographed at an angle (7°)"),
    ("dark", degrade_dark, "poor lighting (underexposed)"),
    ("glare", degrade_glare, "flash glare across the upper label"),
]


def _center(d, img_w, y, text, fnt, fill="#1d1d1d"):
    w = d.textlength(text, font=fnt)
    d.text(((img_w - w) / 2, y), text, font=fnt, fill=fill)


def front_panel(spec: dict) -> Image.Image:
    """Front label: brand identity + class/type (+ vintage/appellation/origin),
    patterned on the corpus style for the pipeline."""
    W, H = 1000, 1300
    img = Image.new("RGB", (W, H), spec.get("bg", "#f6f2e8"))
    d = ImageDraw.Draw(img)
    d.rectangle([24, 24, W - 24, H - 24], outline=spec.get("frame", "#463a28"), width=5)

    y = 120
    if spec.get("vintage"):
        _center(d, W, y, spec["vintage"], font("serif", 40))
        y += 70
    brand_fnt = font(spec.get("brand_font", "serif_bold"), spec.get("brand_size", 64))
    for line in spec["brand_label"].split("\n"):
        _center(d, W, y, line, brand_fnt, fill="#241a0e")
        y += int(spec.get("brand_size", 64) * 1.25)
    y += 36
    for line in wrap(d, spec["class_type"], font("serif", 36), W - 220):
        _center(d, W, y, line, font("serif", 36))
        y += 50
    y += 24
    for extra in spec.get("front_extras", []):
        _center(d, W, y, extra, font("sans", 28))
        y += 44
    if spec.get("front_abv"):
        _center(d, W, H - 220, spec["front_abv"], font("sans", 30))
    if spec.get("front_net"):
        _center(d, W, H - 160, spec["front_net"], font("sans", 30))
    return img


def back_panel(spec: dict) -> Image.Image:
    """Back label: the statutory warning (bold heading, regular body), net
    contents/ABV, sulfites, imported-by block — the corpus back-label shape."""
    W, H = 1000, 900
    img = Image.new("RGB", (W, H), "#fbfaf6")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, W - 20, H - 20], outline="#6b6152", width=3)

    y = 70
    _center(d, W, y, spec["brand_label"].replace("\n", " "), font("serif_bold", 34))
    y += 60
    for line in wrap(d, spec["class_type"], font("serif", 26), W - 240):
        _center(d, W, y, line, font("serif", 26))
        y += 38
    y += 20
    mid = "   ".join(x for x in (spec.get("net_line"), spec.get("sulfites") and
                                 "CONTAINS SULFITES") if x)
    if mid:
        _center(d, W, y, mid, font("sans", 26))
        y += 50
    y = draw_warning(d, 70, y + 10, W - 140, body_size=22,
                     text=spec.get("warning_text", WARNING_TEXT)) or y + 220

    by = H - 240
    for line in spec.get("back_block", []):
        _center(d, W, by, line, font("sans", 24))
        by += 38
    if spec.get("abv_line"):
        d.text((70, H - 70), spec["abv_line"], font=font("sans", 26), fill="#1d1d1d")
    if spec.get("origin_line"):
        t = spec["origin_line"]
        d.text((W - 70 - d.textlength(t, font=font("sans", 26)), H - 70), t,
               font=font("sans", 26), fill="#1d1d1d")
    return img


# One clean, structure-faithful golden per pipeline. `brand_label` is what the
# LABEL prints; `application.brand_name` is the registry text — they differ
# only where the real corpora differ (imports print diacritics the registry
# ASCII-folds → expected LIKELY_MATCH/diacritics_differ, an intended amber).
PIPELINES: list[dict] = [
    dict(pipeline="wine", id="gw_wine_01",
         brand_label="SEACLIFF ESTATE", vintage="2023",
         class_type="California Chardonnay — Table Wine",
         front_extras=["Estate Grown & Bottled"], sulfites=True,
         net_line="750 mL", abv_line="ALC. 12.5% BY VOL.",
         front_abv="ALC. 12.5% BY VOL.", front_net="750 mL",
         origin_line="CENTRAL COAST, CALIFORNIA",
         back_block=["VINTED AND BOTTLED BY SEACLIFF ESTATE",
                     "PASO ROBLES, CALIFORNIA"],
         application=dict(beverage_type="wine", brand_name="SEACLIFF ESTATE",
                          class_type="California Chardonnay — Table Wine",
                          alcohol_content="12.5%", net_contents="750 mL"),
         expect="all green; table wine with ABV printed and matching (12.5%)"),
    dict(pipeline="beer", id="gw_beer_01",
         brand_label="IRON HARBOR\nBREWING CO.", brand_font="sans_bold",
         brand_size=56, bg="#eef1f2", frame="#22343c",
         class_type="American Pale Ale", sulfites=False,
         front_extras=["DRY-HOPPED · SMALL BATCH"],
         net_line="12 FL OZ", abv_line="5.6% ALC/VOL", front_abv="5.6% ALC/VOL",
         origin_line="PORTLAND, MAINE",
         back_block=["BREWED AND CANNED BY IRON HARBOR BREWING CO.",
                     "PORTLAND, MAINE"],
         application=dict(beverage_type="malt_beverage",
                          brand_name="IRON HARBOR BREWING CO.",
                          class_type="American Pale Ale",
                          alcohol_content="5.6%", net_contents="12 FL OZ"),
         expect="all green; malt ABV optional but printed and matching"),
    dict(pipeline="beer", id="gw_beer_02",
         brand_label="BRIDGETOWN\nORGANIC ALES", brand_font="sans_bold",
         brand_size=54, bg="#efe7d8", frame="#2b1d16",
         class_type="Organic Stout", sulfites=False,
         front_extras=["MADE WITH ORGANIC BARLEY & HOPS",
                       "ROASTED · FULL-BODIED"],
         net_line="12 FL OZ", abv_line="5.9% ALC/VOL", front_abv="5.9% ALC/VOL",
         origin_line="PORTLAND, OREGON",
         back_block=["BREWED AND BOTTLED BY BRIDGETOWN ORGANIC ALES",
                     "PORTLAND, OREGON",
                     "CERTIFIED ORGANIC BY OREGON TILTH"],
         application=dict(beverage_type="malt_beverage",
                          brand_name="BRIDGETOWN ORGANIC ALES",
                          class_type="Organic Stout",
                          alcohol_content="5.9%", net_contents="12 FL OZ"),
         expect="all green; organic claims are USDA NOP territory (certifier "
                "line on the info panel), outside TTB screening scope"),
    dict(pipeline="spirits", id="gw_spirits_01",
         brand_label="SILVER MERIDIAN", class_type="Straight Rye Whiskey",
         front_extras=["AGED 4 YEARS IN NEW CHARRED OAK"], sulfites=False,
         net_line="750 mL", abv_line="45% Alc./Vol. (90 Proof)",
         front_abv="45% ALC./VOL. (90 PROOF)", front_net="750 mL",
         origin_line="DISTILLED IN INDIANA",
         back_block=["DISTILLED AND BOTTLED BY",
                     "SILVER MERIDIAN DISTILLING CO., LAWRENCEBURG, IN"],
         application=dict(beverage_type="distilled_spirits",
                          brand_name="SILVER MERIDIAN",
                          class_type="Straight Rye Whiskey",
                          alcohol_content="45% Alc./Vol.", net_contents="750 mL"),
         expect="all green incl. proof consistency (90 = 2×45)"),
    dict(pipeline="imported_wine", id="gw_imported_01",
         brand_label="Château Bellerive",       # label prints the accent…
         vintage="2021", class_type="Red Bordeaux Wine",
         front_extras=["Appellation Bordeaux Contrôlée",
                       "Mis en Bouteille au Château"], sulfites=True,
         net_line="750 mL", abv_line="ALC. 13.5% BY VOL.",
         origin_line="PRODUCT OF FRANCE",
         back_block=["IMPORTED BY:", "HARBORGATE IMPORTS LLC",
                     "PROVIDENCE, RI"],
         application=dict(beverage_type="wine",
                          brand_name="Chateau Bellerive",   # …registry ASCII-folds it
                          class_type="Red Bordeaux Wine",
                          alcohol_content="13.5%", net_contents="750 mL"),
         expect="brand LIKELY_MATCH/diacritics_differ (intended amber); rest green"),
    dict(pipeline="champagne", id="gw_champagne_01",
         brand_label="MAISON VERLET",
         class_type="Champagne Blanc de Blancs — Sparkling Wine",
         front_extras=["Brut", "Épernay, France"], sulfites=True,
         net_line="750ML", abv_line="ALC 12% BY VOL",
         origin_line="PRODUCT OF FRANCE",
         back_block=["IMPORTED BY:", "MERIDIAN CELLARS IMPORTS",
                     "HAYWARD, CA"],
         application=dict(beverage_type="wine", brand_name="MAISON VERLET",
                          class_type="Champagne Blanc de Blancs — Sparkling Wine",
                          alcohol_content="12%", net_contents="750 mL"),
         expect="all green; the corpus-faithful glued '750ML' reads on one "
                "engine only — passes via the green+no-read single-read rule "
                "(guard state agreed_single_read)"),
    dict(pipeline="kentucky_whisky", id="gw_kentucky_01",
         brand_label="CUMBERLAND OAK",
         class_type="Kentucky Straight Bourbon Whiskey",
         front_extras=["SOUR MASH · BOTTLED IN BOND"], sulfites=False,
         net_line="750 mL", abv_line="50% Alc./Vol. (100 Proof)",
         front_abv="50% ALC./VOL. (100 PROOF)", front_net="750 mL",
         origin_line="BARDSTOWN, KENTUCKY",
         back_block=["DISTILLED AND BOTTLED BY CUMBERLAND OAK DISTILLERY",
                     "BARDSTOWN, KENTUCKY"],
         application=dict(beverage_type="distilled_spirits",
                          brand_name="CUMBERLAND OAK",
                          class_type="Kentucky Straight Bourbon Whiskey",
                          alcohol_content="50% Alc./Vol.", net_contents="750 mL"),
         expect="all green incl. proof consistency (100 = 2×50)"),
    dict(pipeline="napa_zinfandel", id="gw_napa_01",
         brand_label="RIDGELINE VINEYARDS", vintage="2022",
         class_type="Napa Valley Zinfandel",
         front_extras=["ESTATE BOTTLED", "NAPA VALLEY"], sulfites=True,
         net_line="750 mL", abv_line="ALC. 14.8% BY VOL.",
         origin_line="ST. HELENA, CALIFORNIA",
         back_block=["PRODUCED AND BOTTLED BY RIDGELINE VINEYARDS",
                     "ST. HELENA, CALIFORNIA"],
         application=dict(beverage_type="wine", brand_name="RIDGELINE VINEYARDS",
                          class_type="Napa Valley Zinfandel",
                          alcohol_content="14.8%", net_contents="750 mL"),
         expect="all green; >14% wine so ABV mandatory and printed"),
]


def _entry(fid: str, spec: dict, expect: str) -> dict:
    return {
        "id": fid,
        "file": f"{fid}_front.jpg",
        "files": [{"file": f"{fid}_front.jpg", "panel": "front"},
                  {"file": f"{fid}_back.jpg", "panel": "back"}],
        "application": spec["application"],
        "note": (f"Synthetic golden patterned on the {spec['pipeline']} "
                 f"corpus structure; ground truth by construction. "
                 f"Expected: {expect}"),
        "provenance": {"source": "generate_golden_cola.py (synthetic; "
                                 "fictional brand, controlled truth)"},
    }


def main() -> None:
    # manifests accumulate per pipeline — a pipeline may carry several
    # goldens (beer has two), and per-spec writes clobbered the earlier ones
    manifests: dict[str, list] = {}
    for spec in PIPELINES:
        out = OUT / spec["pipeline"]
        out.mkdir(parents=True, exist_ok=True)
        fid = spec["id"]
        front = front_panel(spec)
        back = back_panel(spec)
        front.save(out / f"{fid}_front.jpg", "JPEG", quality=92)
        back.save(out / f"{fid}_back.jpg", "JPEG", quality=92)
        entries = manifests.setdefault(spec["pipeline"], [])
        entries.append(_entry(fid, spec, spec["expect"]))
        if spec["pipeline"] == "wine":
            for suffix, transform, desc in WINE_DEGRADATIONS:
                did = f"gw_wine_{suffix}"          # gw_wine_blur, gw_wine_angle…
                transform(front).save(out / f"{did}_front.jpg", "JPEG", quality=88)
                transform(back).save(out / f"{did}_back.jpg", "JPEG", quality=88)
                entries.append(_entry(did, spec,
                                      f"{desc} — recoverable checks stay green; "
                                      f"unrecoverable ones degrade to honest "
                                      f"NEEDS_REVIEW, never a false MISMATCH"))
                print(f"  wine degraded: {did} ({desc})")
        print(f"{spec['pipeline']}: {fid} (front+back)")
    for pipeline, entries in manifests.items():
        (OUT / pipeline / "manifest.json").write_text(json.dumps(entries, indent=1))


if __name__ == "__main__":
    main()
