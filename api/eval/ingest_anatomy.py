"""Anatomy-of-a-Wine-Label ingest (TTB's interactive label tool → eval
reference case).

Source: https://www.ttb.gov/regulated-commodities/beverage-alcohol/wine/anatomy-of-a-label
(U.S. government work — public domain). The page's "image map" is modern:
each label panel is a stack of horizontal PNG slices, clickable slices wired
to an explanation panel via showInfo('<element>','<slice>'). This script
reads the saved page (api/eval/anatomy/page.html) + downloaded slices and
regenerates:

- api/eval/anatomy/front.png, back.png — stitched full panels (usable as
  real front/back inputs to the verifier)
- api/eval/anatomy/reference.json — slice geometry (x, y, w, h per slice),
  the element each slice activates, TTB's full explanation text per
  element, and the mapping onto this tool's field model

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
    m = re.search(rf"id=\"{slice_id}\"[^>]*onclick=\"showInfo\('([^']+)'", page)
    return m.group(1) if m else None


def _info_text(page: str, key: str) -> str:
    m = re.search(rf'<div[^>]*id="{key}"[^>]*>(.*?)</div>', page, re.S)
    if not m:
        return ""
    txt = re.sub(r"<[^>]+>", " ", m.group(1))
    return re.sub(r"\s+", " ", html_mod.unescape(txt)).strip()


def main() -> int:
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
