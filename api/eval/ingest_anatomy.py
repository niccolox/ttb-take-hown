"""Anatomy-of-a-Label ingest (TTB's interactive label tools → eval
reference cases): wine (api/eval/anatomy/) and distilled spirits
(api/eval/anatomy_spirits/).

Sources (U.S. government works — public domain):
- wine: ttb.gov/.../wine/anatomy-of-a-label
- spirits: ttb.gov/.../distilled-spirits/ds-labeling-home/
  anatomy-of-a-distilled-spirits-label-tool

The pages' "image maps" are modern: each label panel is a stack of PNG
slices, clickable slices wired to an explanation panel via
showInfo('<element>','<slice>') (HTML-escaped quotes on the 2024 spirits
tool). This script reads each saved page + downloaded slices and
regenerates, per commodity:

- front.png / back.png — stitched full panels (real verifier inputs)
- reference.json — slice geometry, the element each slice activates,
  TTB's full explanation text, and the mapping onto this tool's fields

Run: .venv/bin/python -m api.eval.ingest_anatomy
"""

from __future__ import annotations

import html as html_mod
import json
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent / "anatomy"
IMAGES = ROOT / "images"

# element key (page id) → this tool's field, or None where we deliberately
# have no check (graphics, marketing prose, web links, UPC — the last is
# explicitly "not regulated by TTB")
FIELD_MAP = {
    "imageLH": None, "brandName": "brand_name", "fancifulName": "fanciful_name",
    "class": "class_type", "origin1": "appellation", "vintage": "vintage",
    "address": "name_address", "addInfo": None, "web": None,
    "health": "government_warning", "sulfites": "sulfite_declaration",
    "net": "net_contents", "alcohol": "alcohol_content", "UPC": None,
}

# curated from the page text: is the element mandatory, and where may it go
REQUIREDNESS = {
    "imageLH": ("no", "any label"),
    "brandName": ("yes", "brand label"),
    "fancifulName": ("no", "any label"),
    "class": ("yes", "brand label"),
    "origin1": ("conditional — required with varietal/vintage/semi-generic/estate",
                "brand label, with the class/type"),
    "vintage": ("no", "any label"),
    "address": ("yes", "any label"),
    "addInfo": ("no", "any label"),
    "web": ("no", "any label"),
    "health": ("yes (0.5%+ ABV)", "any label"),
    "sulfites": ("conditional — 10+ ppm total SO2", "any label"),
    "net": ("yes", "any label"),
    "alcohol": ("conditional — mandatory over 14% ABV", "any label"),
    "UPC": ("no — not regulated by TTB", "any label"),
}

# stack geometry straight from the page markup: front is 9 full-width rows;
# back is 5 full-width rows, a two-column flex block (health/sulfites+net/
# alcohol left, UPC right), then a full-width footer row
FRONT = ["f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9"]
BACK_ROWS = ["b1", "b2", "b3", "b4", "b5"]


def _element_of(page: str, slice_id: str) -> str | None:
    # quotes are literal on the wine tool, &apos;-escaped on the 2024 spirits tool
    m = re.search(rf"id=\"{slice_id}\"[^>]*showInfo\((?:'|&apos;)([A-Za-z0-9]+)", page)
    return m.group(1) if m else None


def _info_text(page: str, key: str) -> str:
    m = re.search(rf'<div[^>]*id="{key}"[^>]*>(.*?)</div>', page, re.S)
    if not m:
        return ""
    txt = re.sub(r"<[^>]+>", " ", m.group(1))
    return re.sub(r"\s+", " ", html_mod.unescape(txt)).strip()


def build_wine() -> None:
    page = (ROOT / "page.html").read_text(encoding="utf-8")
    dims = {p.stem: Image.open(p).size for p in IMAGES.glob("*.png")}

    slices = []

    def place(name: str, x: int, y: int, panel: str):
        w, h = dims[name]
        slices.append({"file": f"images/{name}.png", "panel": panel,
                       "x": x, "y": y, "w": w, "h": h,
                       "element": _element_of(page, name)})
        return h

    y = 0
    for name in FRONT:
        y += place(name, 0, y, "front")
    front_h = y

    y = 0
    for name in BACK_ROWS:
        y += place(name, 0, y, "back")
    flex_top = y
    y += place("b6", 0, y, "back")
    place("b7", 0, y, "back")
    y += place("b8", dims["b7"][0], y, "back")
    y += place("b9", 0, y, "back")
    place("b11", dims["b6"][0], flex_top, "back")
    y = max(y, flex_top + dims["b11"][1])
    y += place("b10", 0, y, "back")
    back_h = y

    for panel, width, height in (("front", 325, front_h), ("back", 325, back_h)):
        canvas = Image.new("RGB", (width, height), "#ffffff")
        for s in slices:
            if s["panel"] == panel:
                canvas.paste(Image.open(ROOT / s["file"]), (s["x"], s["y"]))
        canvas.save(ROOT / f"{panel}.png")

    elements = {}
    for key, field in FIELD_MAP.items():
        mandatory, placement = REQUIREDNESS[key]
        elements[key] = {"field": field, "mandatory": mandatory,
                         "placement": placement, "ttb_text": _info_text(page, key)}

    ref = {
        "source": "https://www.ttb.gov/regulated-commodities/beverage-alcohol/wine/anatomy-of-a-label",
        "fetched": "2026-08-03",
        "license": "U.S. government work (public domain)",
        "note": "TTB's interactive Anatomy of a Wine Label: slice geometry is the "
                "page's image map (stacked clickable PNGs); elements carry TTB's "
                "own explanation text and the mapping onto this tool's fields.",
        "panels": {"front": {"width": 325, "height": front_h},
                   "back": {"width": 325, "height": back_h}},
        "slices": slices,
        "elements": elements,
    }
    (ROOT / "reference.json").write_text(json.dumps(ref, indent=2) + "\n")
    covered = sum(1 for e in elements.values() if e["field"])
    print(f"anatomy: {len(slices)} slices, front {front_h}px, back {back_h}px, "
          f"{covered}/{len(elements)} elements mapped to fields")


# ── distilled spirits (2024 tool) ────────────────────────────────────────────

DS_ROOT = Path(__file__).parent / "anatomy_spirits"
DS_IMAGES = DS_ROOT / "images"

# nameAddress maps to None on purpose: the name_address check is wine/malt
# only so far — the part 5 audit is pending, and this reference records the
# coverage gap honestly rather than papering over it
DS_FIELD_MAP = {
    "GPI": None, "brandName": "brand_name", "fancifulName": "fanciful_name",
    "classType": "class_type", "alcoholContent": "alcohol_content",
    "nameAddress": None, "webAdd": None, "netCont": "net_contents",
    "addInfo": None, "healthWarning": "government_warning", "upcBar": None,
}

DS_REQUIREDNESS = {
    "GPI": ("no", "any label"),
    "brandName": ("yes", "any label"),
    "fancifulName": ("conditional — required with a statement of composition "
                     "(specialty products)", "any label"),
    "classType": ("yes", "any label"),
    "alcoholContent": ("yes — mandatory for distilled spirits (§5.63)", "any label"),
    "nameAddress": ("yes", "any label, or blown/embossed/molded into the container"),
    "webAdd": ("no", "any label"),
    "netCont": ("yes", "any label, or blown/embossed/molded into the container"),
    "addInfo": ("no", "any label"),
    "healthWarning": ("yes (0.5%+ ABV)", "any label"),
    "upcBar": ("no", "any label"),
}

# straight from the page markup: full-width stacks with two side-by-side
# pairs on the back (webAdd+netCont, healthWarning+upcBar)
DS_FRONT_ROWS = [["f0"], ["f1"], ["f2"], ["f3"], ["f4"], ["f5"], ["f6"]]
DS_BACK_ROWS = [["b0"], ["b1"], ["b2", "b7"], ["b3"], ["b4", "b5"], ["b6"]]


def build_spirits() -> None:
    page = (DS_ROOT / "page.html").read_text(encoding="utf-8")
    dims = {p.stem: Image.open(p).size for p in DS_IMAGES.glob("*.png")}

    slices = []

    def stack(rows: list[list[str]], panel: str) -> int:
        y = 0
        for row in rows:
            x, row_h = 0, 0
            for name in row:
                w, h = dims[name]
                slices.append({"file": f"images/{name}.png", "panel": panel,
                               "x": x, "y": y, "w": w, "h": h,
                               "element": _element_of(page, name)})
                x += w
                row_h = max(row_h, h)
            y += row_h
        return y

    front_h = stack(DS_FRONT_ROWS, "front")
    back_h = stack(DS_BACK_ROWS, "back")

    for panel, height in (("front", front_h), ("back", back_h)):
        canvas = Image.new("RGB", (325, height), "#ffffff")
        for s in slices:
            if s["panel"] == panel:
                canvas.paste(Image.open(DS_ROOT / s["file"]), (s["x"], s["y"]))
        canvas.save(DS_ROOT / f"{panel}.png")

    elements = {}
    for key, field in DS_FIELD_MAP.items():
        mandatory, placement = DS_REQUIREDNESS[key]
        elements[key] = {"field": field, "mandatory": mandatory,
                         "placement": placement, "ttb_text": _info_text(page, key)}

    ref = {
        "source": "https://www.ttb.gov/regulated-commodities/beverage-alcohol/"
                  "distilled-spirits/ds-labeling-home/anatomy-of-a-distilled-spirits-label-tool",
        "fetched": "2026-08-03",
        "license": "U.S. government work (public domain)",
        "note": "TTB's interactive Anatomy of a Distilled Spirits Label (2024 tool): "
                "slice geometry is the page's image map; elements carry TTB's own "
                "explanation text and the mapping onto this tool's fields. "
                "nameAddress is unmapped pending the part 5 audit.",
        "panels": {"front": {"width": 325, "height": front_h},
                   "back": {"width": 325, "height": back_h}},
        "slices": slices,
        "elements": elements,
    }
    (DS_ROOT / "reference.json").write_text(json.dumps(ref, indent=2) + "\n")
    covered = sum(1 for e in elements.values() if e["field"])
    print(f"anatomy_spirits: {len(slices)} slices, front {front_h}px, back {back_h}px, "
          f"{covered}/{len(elements)} elements mapped to fields")


# ── malt beverage tool ───────────────────────────────────────────────────────

MB_ROOT = Path(__file__).parent / "anatomy_malt"
MB_IMAGES = MB_ROOT / "images"

MB_FIELD_MAP = {
    "GPI": None, "brandName": "brand_name", "fancifulName": "fanciful_name",
    "classType": "class_type", "alcoholContent": "alcohol_content",
    "netContent": "net_contents", "nameAddress": "name_address",
    "addInfo": None, "webAdd": None, "healthWarning": "government_warning",
    "upcBar": None,
}

MB_REQUIREDNESS = {
    "GPI": ("no", "any label"),
    "brandName": ("yes — bottler/importer name serves if none", "any label"),
    "fancifulName": ("conditional — required with a statement of composition "
                     "(specialty products, §7.147)", "any label"),
    "classType": ("yes", "any label"),
    "alcoholContent": ("conditional — mandatory when alcohol derives from added "
                       "flavors/nonbeverage ingredients (§7.63(a)(3)); otherwise "
                       "optional", "any label"),
    "netContent": ("yes", "any label, or blown/embossed/molded into the container"),
    "nameAddress": ("yes — name + city/state; explanatory phrase optional (§7.66)",
                    "any label, or blown/embossed/molded into the container"),
    "addInfo": ("no", "any label"),
    "webAdd": ("no", "any label"),
    "healthWarning": ("yes (0.5%+ ABV)", "any label"),
    "upcBar": ("no", "any label"),
}

# from the page markup: nameAddress deliberately has TWO hotspots — the
# bottler name up top (f0) and the city/state line lower down (f5): §7.66's
# "the name and address does not need to appear together" drawn literally.
# Several slices are GIFs served as .png — actual dims (read from the
# files) tile the 325px rows exactly where the HTML attributes are off-by-few.
MB_FRONT_ROWS = [["a1"], ["f0"], ["f1"], ["f2"], ["f6"],
                 ["a3_1", "f3", "a3_2", "f4", "a3_3"], ["a4"], ["f5"], ["a5"]]
MB_BACK_ROWS = [["b0"], ["b1", "b2", "b3"], ["b4"], ["b6", "b7", "b8", "b9"], ["b10"]]


def build_malt() -> None:
    page = (MB_ROOT / "page.html").read_text(encoding="utf-8")
    dims = {p.stem: Image.open(p).size for p in MB_IMAGES.glob("*.png")}

    slices = []

    def stack(rows: list[list[str]], panel: str) -> int:
        y = 0
        for row in rows:
            x, row_h = 0, 0
            for name in row:
                w, h = dims[name]
                slices.append({"file": f"images/{name}.png", "panel": panel,
                               "x": x, "y": y, "w": w, "h": h,
                               "element": _element_of(page, name)})
                x += w
                row_h = max(row_h, h)
            y += row_h
        return y

    front_h = stack(MB_FRONT_ROWS, "front")
    back_h = stack(MB_BACK_ROWS, "back")

    for panel, height in (("front", front_h), ("back", back_h)):
        canvas = Image.new("RGB", (325, height), "#ffffff")
        for s in slices:
            if s["panel"] == panel:
                canvas.paste(Image.open(MB_ROOT / s["file"]).convert("RGB"),
                             (s["x"], s["y"]))          # GIF slices are palette-mode
        canvas.save(MB_ROOT / f"{panel}.png")

    elements = {}
    for key, field in MB_FIELD_MAP.items():
        mandatory, placement = MB_REQUIREDNESS[key]
        elements[key] = {"field": field, "mandatory": mandatory,
                         "placement": placement, "ttb_text": _info_text(page, key)}

    ref = {
        "source": "https://www.ttb.gov/regulated-commodities/beverage-alcohol/"
                  "beer/labeling/anatomy-of-a-malt-beverage-label-tool",
        "fetched": "2026-08-03",
        "license": "U.S. government work (public domain)",
        "note": "TTB's interactive Anatomy of a Malt Beverage Label: slice "
                "geometry is the page's image map; nameAddress spans two "
                "hotspots (name and city/state on separate lines, §7.66).",
        "panels": {"front": {"width": 325, "height": front_h},
                   "back": {"width": 325, "height": back_h}},
        "slices": slices,
        "elements": elements,
    }
    (MB_ROOT / "reference.json").write_text(json.dumps(ref, indent=2) + "\n")
    covered = sum(1 for e in elements.values() if e["field"])
    print(f"anatomy_malt: {len(slices)} slices, front {front_h}px, back {back_h}px, "
          f"{covered}/{len(elements)} elements mapped to fields")


def main() -> int:
    build_wine()
    build_spirits()
    build_malt()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
