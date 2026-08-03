"""Golden-set generator: programmatic labels with known ground truth.

Generates the M0 calibration corpus (PLAN.md M0): clean controls plus
adversarial variants — title-case warning trap, word-substitution trap,
all-bold warning trap, skew, glare, curved-bottle shading, decorative font,
small text, and a within-tolerance ABV digit-misread pair. Each image ships
with a manifest entry carrying ground truth and the intended disposition.

Programmatic generation (vs AI images) gives controlled ground truth
(adopted from competitor survey; see docs/reviews/comparison-treasury-take-home.md).
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

OUT = Path(__file__).parent / "golden"

FONT_DIR = Path("/usr/share/fonts/truetype")
FONTS = {
    "serif": FONT_DIR / "dejavu/DejaVuSerif.ttf",
    "serif_bold": FONT_DIR / "dejavu/DejaVuSerif-Bold.ttf",
    "sans": FONT_DIR / "dejavu/DejaVuSans.ttf",
    "sans_bold": FONT_DIR / "dejavu/DejaVuSans-Bold.ttf",
    "decorative": FONT_DIR / "ubuntu/Ubuntu-BI.ttf",  # italic-bold as a stand-in for script
}

WARNING_TEXT = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not "
    "drink alcoholic beverages during pregnancy because of the risk of birth "
    "defects. (2) Consumption of alcoholic beverages impairs your ability to "
    "drive a car or operate machinery, and may cause health problems."
)


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS[kind]
    if not path.exists():  # fall back to any dejavu
        path = FONTS["sans"]
    return ImageFont.truetype(str(path), size)


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_warning(draw, x, y, max_w, *, body_size=16, prefix_bold=True, body_bold=False,
                 prefix_caps=True, text=WARNING_TEXT):
    """Render the government warning; returns final y. Prefix styling is controllable
    so traps (title-case, all-bold) can be generated."""
    prefix = "GOVERNMENT WARNING:" if prefix_caps else "Government Warning:"
    body = text.split(":", 1)[1].strip()
    pfnt = font("sans_bold" if prefix_bold else "sans", body_size)
    bfnt = font("sans_bold" if body_bold else "sans", body_size)
    full = prefix + " " + body
    # naive mixed rendering: draw prefix, then wrap body continuing on same lines
    lines = wrap(draw, full, bfnt, max_w)
    py = y
    first = True
    for line in lines:
        if first and line.startswith(prefix):
            draw.text((x, py), prefix, font=pfnt, fill="black")
            rest = line[len(prefix):]
            draw.text((x + draw.textlength(prefix, font=pfnt), py), rest, font=bfnt, fill="black")
            first = False
        else:
            draw.text((x, py), line, font=bfnt, fill="black")
        py += int(body_size * 1.35)
    return py


def base_label(spec: dict) -> Image.Image:
    W, H = 1000, 1400
    img = Image.new("RGB", (W, H), spec.get("bg", "#f4efe4"))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, W - 20, H - 20], outline="#3a2f22", width=6)

    brand_fnt = font(spec.get("brand_font", "serif_bold"), spec.get("brand_size", 68))
    y = 90
    for line in spec["brand"].split("\n"):
        w = d.textlength(line, font=brand_fnt)
        d.text(((W - w) / 2, y), line, font=brand_fnt, fill="#2a1f12")
        y += int(spec.get("brand_size", 68) * 1.2)

    y += 30
    ct_fnt = font("serif", 34)
    for line in wrap(d, spec["class_type"], ct_fnt, W - 200):
        w = d.textlength(line, font=ct_fnt)
        d.text(((W - w) / 2, y), line, font=ct_fnt, fill="#2a1f12")
        y += 46

    y += 40
    info_fnt = font("sans", 30)
    if spec.get("abv_line"):
        w = d.textlength(spec["abv_line"], font=info_fnt)
        d.text(((W - w) / 2, y), spec["abv_line"], font=info_fnt, fill="#2a1f12")
        y += 44
    if spec.get("net_line"):
        w = d.textlength(spec["net_line"], font=info_fnt)
        d.text(((W - w) / 2, y), spec["net_line"], font=info_fnt, fill="#2a1f12")
        y += 44

    prod_fnt = font("sans", 22)
    py = H - 380
    for line in wrap(d, spec.get("producer", ""), prod_fnt, W - 160):
        d.text((80, py), line, font=prod_fnt, fill="#2a1f12")
        py += 30

    if spec.get("warning", True):
        draw_warning(
            d, 80, H - 280, W - 160,
            body_size=spec.get("warning_size", 17),
            prefix_bold=spec.get("warning_prefix_bold", True),
            body_bold=spec.get("warning_body_bold", False),
            prefix_caps=spec.get("warning_prefix_caps", True),
            text=spec.get("warning_text", WARNING_TEXT),
        )
    return img


# ── photographic degradations ────────────────────────────────────────────────

def degrade_skew(img, angle=7):
    return img.rotate(angle, expand=True, fillcolor="#d8d2c4", resample=Image.BICUBIC)


def degrade_glare(img):
    W, H = img.size
    overlay = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(overlay)
    d.ellipse([W * 0.15, H * 0.05, W * 0.75, H * 0.45], fill=180)
    overlay = overlay.filter(ImageFilter.GaussianBlur(80))
    white = Image.new("RGB", (W, H), "white")
    return Image.composite(white, img, overlay)


def degrade_blur_dark(img):
    img = img.filter(ImageFilter.GaussianBlur(2.2))
    return ImageEnhance.Brightness(img).enhance(0.55)


def degrade_curved(img):
    """Cylindrical shading + mild horizontal squeeze at edges."""
    W, H = img.size
    shade = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(shade)
    for x in range(W):
        v = int(90 * (abs(x - W / 2) / (W / 2)) ** 2)
        d.line([(x, 0), (x, H)], fill=v)
    black = Image.new("RGB", (W, H), "black")
    return Image.composite(black, img, shade)


def degrade_lowres(img):
    W, H = img.size
    return img.resize((W // 4, H // 4), Image.BILINEAR).resize((W, H), Image.BILINEAR)


# ── corpus definition ────────────────────────────────────────────────────────

def corpus() -> list[dict]:
    old_tom = dict(
        brand="OLD TOM\nDISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        abv_line="45% Alc./Vol. (90 Proof)",
        net_line="750 mL",
        producer="Distilled and bottled by Old Tom Distillery Co., Bardstown, Kentucky",
        beverage_type="distilled_spirits",
    )
    stones = dict(
        brand="STONE'S THROW",
        class_type="American Pale Ale",
        abv_line="5.2% ALC/VOL",
        net_line="12 FL OZ",
        producer="Brewed and canned by Stone's Throw Brewing, Portland, Oregon",
        beverage_type="malt_beverage",
        brand_font="sans_bold",
        bg="#e8f0e4",
    )
    seabreeze = dict(
        brand="SEABREEZE\nCELLARS",
        class_type="California Chardonnay — Table Wine",
        abv_line=None,  # legally omitted: table wine ≤14% (§4.36(a))
        app_abv="12.5%",  # the COLA still declares the band even when the label omits it
        net_line="750 mL",
        producer="Vinted and bottled by Seabreeze Cellars, Napa, California — Contains Sulfites",
        beverage_type="wine",
        bg="#f0e8f0",
    )

    # truth carries TWO abv facts: abv_line is what the LABEL prints (drives
    # drawing), app_abv is what the COLA APPLICATION declares. They differ by
    # design on the ABV traps (app 45.0 vs printed 45.2/46) and on the table
    # wine (app 12.5%, label lawfully prints nothing — §4.36(a)); collapsing
    # them made the eval-set loader feed the label value back as the
    # application, which turned every trap into an exact match.
    truth = lambda s: {
        "brand": s["brand"].replace("\n", " "),
        "class_type": s["class_type"],
        "abv_line": s.get("abv_line"),
        "app_abv": s.get("app_abv") or s.get("abv_line"),
        "net_line": s.get("net_line"),
        "beverage_type": s["beverage_type"],
    }

    cases = [
        # clean controls
        dict(id="spirits_clean", spec=old_tom, degrade=None,
             expect="all fields readable; warning exact w/ caps+contrast OK", truth=truth(old_tom)),
        dict(id="malt_clean", spec=stones, degrade=None,
             expect="all fields readable", truth=truth(stones)),
        dict(id="wine_no_abv_table", spec=seabreeze, degrade=None,
             expect="ABV absent → NOT REQUIRED (table wine); sulfites present", truth=truth(seabreeze)),
        # warning traps
        dict(id="trap_titlecase_warning", spec={**old_tom, "warning_prefix_caps": False}, degrade=None,
             expect="prefix caps check FAILS (title case)", truth=truth(old_tom)),
        dict(id="trap_word_substitution", spec={**old_tom, "warning_text": WARNING_TEXT.replace("birth defects", "birth defect")},
             degrade=None, expect="warning text diff catches 'defect' vs 'defects'", truth=truth(old_tom)),
        dict(id="trap_all_bold_warning", spec={**old_tom, "warning_body_bold": True}, degrade=None,
             expect="weight contrast: no-contrast violation (§16.22(a)(2) body may not be bold)", truth=truth(old_tom)),
        dict(id="trap_missing_warning", spec={**old_tom, "warning": False}, degrade=None,
             expect="warning absent → finding (coverage gate permitting)", truth=truth(old_tom)),
        # ABV traps
        dict(id="trap_abv_within_band",
             spec={**old_tom, "abv_line": "45.2% Alc./Vol.", "app_abv": "45% Alc./Vol."}, degrade=None,
             expect="app=45.0 → WITHIN TOLERANCE amber (spirits ±0.3), never green",
             truth=truth({**old_tom, "abv_line": "45.2% Alc./Vol.", "app_abv": "45% Alc./Vol."})),
        dict(id="trap_abv_outside_band",
             spec={**old_tom, "abv_line": "46% Alc./Vol. (92 Proof)", "app_abv": "45% Alc./Vol."}, degrade=None,
             expect="app=45.0 → MISMATCH (outside ±0.3)",
             truth=truth({**old_tom, "abv_line": "46% Alc./Vol. (92 Proof)", "app_abv": "45% Alc./Vol."})),
        # photographic degradations
        dict(id="photo_skew", spec=old_tom, degrade="skew", expect="fields recoverable after deskew/rotation"),
        dict(id="photo_glare", spec=old_tom, degrade="glare", expect="glare region → low conf → NEEDS REVIEW on affected fields"),
        dict(id="photo_blur_dark", spec=stones, degrade="blur_dark", expect="degrades to NEEDS REVIEW, never false verdicts"),
        dict(id="photo_curved", spec=stones, degrade="curved", expect="edge shading tolerated or NEEDS REVIEW"),
        dict(id="photo_lowres", spec=seabreeze, degrade="lowres", expect="small text unreadable → NEEDS REVIEW(unreadable)"),
        dict(id="decorative_font", spec={**old_tom, "brand_font": "decorative"}, degrade=None,
             expect="stylized brand still located (fuzzy) or honest NEEDS REVIEW"),
    ]
    for c in cases:
        c.setdefault("truth", truth(c["spec"]))
    return cases


DEGRADES = {
    "skew": degrade_skew, "glare": degrade_glare, "blur_dark": degrade_blur_dark,
    "curved": degrade_curved, "lowres": degrade_lowres,
}


def main():
    random.seed(20260731)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for case in corpus():
        img = base_label(case["spec"])
        if case["degrade"]:
            img = DEGRADES[case["degrade"]](img)
        # TTB input distribution: JPEG, medium quality, ≤1.5MB (cola-fact-sheet facts 63-68)
        path = OUT / f"{case['id']}.jpg"
        img.save(path, "JPEG", quality=75)
        manifest.append({
            "file": path.name,
            "id": case["id"],
            "degrade": case["degrade"],
            "expect": case["expect"],
            "truth": case["truth"],
        })
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} labels to {OUT}")


if __name__ == "__main__":
    main()
