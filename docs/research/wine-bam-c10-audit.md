# Wine BAM Chapter 10 Audit — TTB Sample Labels vs. Label Check (2026-08-03)

Source: `source/c10-sample-wine-labels.pdf` (Wine Beverage Alcohol Manual,
Chapter 10 "Sample Wine Labels", 8/2018) — TTB's eight approvable label
formats, run through `verify()`/`verify_multi()` as synthetic word lists.
The premise: **every label TTB publishes as approvable must screen clean**;
anything red or amber on these formats is a tool defect, not a label defect.

## Sweep result

Before the audit: p.10-7 and p.10-8 screened **MISMATCH (false red)**;
p.10-2/10-3 screened amber on brand; p.10-6 degraded to
`screening_incomplete` with printed facts reported as not found. After the
C10 fixes: **all eight formats screen `no_mismatch_found` with every field
MATCH or NOT_REQUIRED.** The eight formats are pinned as regression
fixtures in `api/tests/test_rules.py` (BAM section).

## Findings (all implemented)

**C10-1 · Varietal percentages hijacked the ABV read (false RED).**
The ABV locator took the first percent-line. On the three-piece blend
(p.10-7) `60% CHARDONNAY` sits above `ALC. 12.5% BY VOL.` → label ABV read
as 60%, class-boundary crossing, MISMATCH — on content §4.23(d) *requires*
blends to print. Same failure from prose on p.10-8 ("blend of 50% MERLOT
and…"). Fix: `Locator.find_regex` gained a `prefer` pattern; ABV search
prefers lines carrying ALC/VOL/PROOF context (`ABV_CONTEXT_RE`), falling
back to the old first-match when no line has context (bare "12.5%" labels
still locate).

**C10-2 · Bottler-as-brand screened amber.** p.10-2/10-3 have no separate
brand line — §4.33(a): the bottler's name serves as the brand, printed only
inside "BOTTLED BY XYZ WINERY, CITY, STATE". The fuzzy brand match either
missed it or tripped the confusable guard on the address comma
("XYZ WINERY,"). Fix: when the located name-address line loosely contains
the application brand, the brand row becomes MATCH with the §4.33(a) note.
A brand genuinely absent stays a review item (pinned).

**C10-3 · "table"/"light" substring false-optionality (false GREEN
direction).** `abv_required` used substring containment, so "Moonlight
Cellars Red" and "Twilight Zinfandel" excused a mandatory ABV statement as
light-wine designations. Fix: word-boundary match. "Light Rice Wine" still
qualifies (and per BAM p.10-2 the non-grape commodity qualifier is exactly
how such wine is designated).

**C10-4 · Art-dominant front panels failed the text-mass floor.** p.10-6
(imported + strip label): the front is brand + vintage + artwork — under
the per-panel 4-word floor it was flagged "not a label" and its words
dropped, sending brand and vintage to not_found and the whole result to
`screening_incomplete`. Real wine fronts look like this constantly. Fix:
in `verify_multi` the floor applies to the panels' **combined** text mass;
a single sparse image is still floored (nothing to combine with).

**C10-5 · Varietal percentages must total 100 (§4.23(d)).** "60%
CHARDONNAY / 40% SEMILLON" is checkable arithmetic the tool ignored. New:
when the application names ≥2 varietals and **every** one carries a printed
percentage, a sum ≠ 100 escalates the grape_varietals row to NEEDS_REVIEW
(`varietal_percentages_sum`). A partial read (some varietal without a
percentage) proves nothing and stays silent.

## Confirmed-correct behaviors (no change needed)

- p.10-4's "CONTAINS SULFITES" printed flush-right at the end of the
  Government Warning block: the trailing-neighbor rule keeps the warning
  text green, the statutory char-budget keeps weight-contrast honest, and
  the sulfite presence check still fires on the merged line.
- Table wine without ABV → NOT_REQUIRED; dessert wine ("Red Wine", 14.1%)
  → numeric statement required and matched ("Dessert Wine" does NOT
  substitute — only table/light, as encoded).
- Two-piece and statement-of-composition ("RED WINE WITH NATURAL FLAVORS")
  formats, imported strip-label "IMPORTED BY" + "PRODUCT OF" origin.

## Noted, out of scope

- Color words must be followed by "Wine" to serve as class/type
  (§4.21(a)(1)(iv)) — application data governs class/type here.
- Warning ≤25 characters/inch (§16.22(a)(3)), ABV 1–3 mm type size:
  physical-scale facts, unverifiable from a photo (footer disclaimer).
- Formula-approval linkage for non-standard wine (p.10-9 note) and the
  bottled/packed record rules (27 CFR 24.308): process facts outside the
  label image.
