# TTB/ALFD Labeling Rules — Wine, Distilled Spirits, Malt Beverages, and the Health Warning

Compiled 2026-07-31 **directly from the eCFR** (27 CFR, current text as of 2026-07-01): Part 4 (wine, §§4.32/4.36), Part 5 (distilled spirits, §§5.63/5.65 — the modernized 2022 layout), Part 7 (malt beverages, §§7.63/7.65), and Part 16 (health warning, complete). Supporting sections cited by number where not fetched verbatim. This is the regulatory ground truth for the verification rules engine in `../../PLAN.md`.

---

## 1. Health Warning Statement — 27 CFR Part 16 (all alcoholic beverages)

**Scope (§16.10, §16.20):** applies to every beverage ≥0.5% ABV intended for human consumption, bottled or imported for sale in the U.S. on/after November 18, 1989. COLAs cannot issue without it (§16.30). Exports are exempt — *except* products for U.S. Armed Forces, which must carry it (§16.31).

**The exact statutory text (§16.21)** — stated "separate and apart from all other information," on brand, front, back, or side label:

> GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink alcoholic beverages during pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages impairs your ability to drive a car or operate machinery, and may cause health problems.

**Format requirements (§16.22) — more specific than any competitor implemented:**
- Readily legible under ordinary conditions, on a **contrasting background** (§16.22(a)(1)).
- **"GOVERNMENT WARNING" must be in capital letters AND bold type** (§16.22(a)(2)).
- **The remainder of the statement may NOT appear in bold type** (§16.22(a)(2)) — an *all-bold* warning is also a violation. No solution in our seven-competitor survey checks this direction.
- Text may not be compressed to illegibility (§16.22(a)(3)).
- **Characters-per-inch caps by type size** (§16.22(a)(4)): 1mm type → max 40 char/inch; 2mm → max 25; 3mm → max 12.
- **Minimum type size by container** (§16.22(b)): ≤237mL (8 fl oz) → ≥1mm; >237mL to 3L → ≥2mm; >3L → ≥3mm.
- Labels must be affixed so they can't be removed without water/solvents (§16.22(c)).
- **Federal preemption (§16.32):** no state may require any *other* alcohol-health statement on containers.
- Civil penalty: up to $10,000 per violation, inflation-adjusted, **each day a separate offense** (§16.33).

## 2. Wine — 27 CFR Part 4 (products ≥7% ABV)

**Mandatory on the brand label (§4.32(a)):** brand name (§4.33); class/type designation (§4.34); exact percentage of foreign wine if referenced in American/foreign blends.

**Mandatory anywhere on the container (§4.32(b)):** name and address (§4.35); net contents (§4.37 — must be on the *front* if a non-metric standard of fill); alcohol content (§4.36).

**Conditional declarations (§4.32(c)-(e)):** FD&C Yellow No. 5; cochineal extract/carmine by common name ("Contains Carmine"); **"Contains sulfites"** when ≥10 ppm total SO₂.

**Alcohol content (§4.36):**
- **Required only above 14% ABV.** At ≤14%, the statement is optional *if* "table wine" or "light wine" appears as the type designation.
- Must be percent-by-volume, never anything else; abbreviations exactly "alc." and "vol."
- **Tolerances: ±1.0 percentage point for wines >14% ABV; ±1.5 points for wines ≤14%** (§4.36(b)(1)).
- Range labeling permitted ("Alcohol _% to _% by volume"): max spread 2 points (>14%) or 3 points (≤14%), no tolerance outside the range.
- Tolerance can never carry a wine across a class/tax-grade boundary (§4.36(c)) — e.g., a "table wine" can't be over 14% in fact.

**Related (cited, not fetched):** standards of fill §4.72 (authorized metric sizes, e.g. 750mL); type-size minimums §4.38 (generally 2mm, 1mm for ≤187mL); appellations/varietals subpart C (AVA ≥85% rule — the reviewer-error hotspot documented in `cola-swot.md`); vintage rules 27 CFR 4.27.

## 3. Distilled Spirits — 27 CFR Part 5 (2022 modernized layout)

**Same-field-of-vision rule (§5.63(a)) — unique to spirits:** brand name (§5.64), class/type (subpart I), and alcohol content (§5.65) must appear **within a single field of vision — one side of the container, defined for cylinders as 40% of the circumference**, viewable without turning the bottle.

**Anywhere on the container (§5.63(b)):** name/address of bottler-distiller or importer (§§5.66-5.68); net contents (§5.70 — may be blown/embossed/molded into the glass).

**Required disclosures (§5.63(c)):** neutral spirits percentage and source commodity (§5.71); coloring/wood treatment (§§5.72-5.73); **age statements** when required or used (§5.74); state of distillation for U.S.-distilled whisky types (§5.66(f)); FD&C Yellow No. 5; cochineal/carmine; sulfites ≥10 ppm; **aspartame in capital letters: "PHENYLKETONURICS: CONTAINS PHENYLALANINE."**

**Alcohol content (§5.65):**
- Mandatory, as percent alcohol by volume.
- **Proof is optional** — permitted only in the same field of vision as the mandatory ABV statement (additional proof statements may appear elsewhere) (§5.65(b)(1)(i)). Proof = 2 × ABV by definition, so the label-internal cross-check in PLAN.md is regulation-shaped.
- Exactly three authorized sentence formats, with authorized abbreviations (alc, %, /, vol): compliant examples include "40% alc/vol", "Alc. 40 percent by vol.", "Alc 40% by vol", "40% Alcohol by Volume" (§5.65(b)).
- Products with spirit-absorbing solids must state "Bottled at __ percent alcohol by volume" (§5.65(a)).
- **Tolerance: ±0.3 percentage points** (§5.65(c)).

**Related (cited):** standards of fill §5.203 (authorized container sizes incl. 50mL, 375mL, 750mL, 1L, 1.75L); minimum type sizes §5.53; distinctive liquor bottle exemptions §5.205(b)(2).

## 4. Malt Beverages — 27 CFR Part 7

**Mandatory (§7.63(a)):** brand name (§7.64); class/type (subpart I); name/address of bottler or importer (may be molded into the container); net contents (same); **alcohol content only conditionally mandatory** — required when alcohol derives from added non-beverage flavors or ingredients (other than hop extract). Otherwise optional federally — but governed by **state law** where states require or prohibit it (§7.65(a)).

**Disclosures (§7.63(b)):** FD&C Yellow No. 5; cochineal/carmine; sulfites ≥10 ppm; aspartame (same all-caps phenylketonurics statement as spirits).

**Alcohol content (§7.65):**
- Percent alcohol by volume; alcohol-by-weight allowed only alongside and as part of the ABV statement.
- **Stated to the nearest 0.1 percentage point** for ≥0.5% ABV products (§7.65(b)(2)).
- Same three authorized formats and abbreviations as spirits; compliant examples "4.2% alc/vol", "Alc 4% by vol" (§7.65(b)(5)).
- **Tolerance: ±0.3 percentage points** — but a beverage labeled ≥0.5% may never actually be under 0.5% (§7.65(c)).
- **"Low alcohol"/"reduced alcohol"**: only under 2.5% ABV, hard cap, no tolerance rescue (§7.65(d)).
- **"Non-alcoholic"**: only with "contains less than 0.5% alcohol by volume" immediately adjacent, legible, contrasting background; zero tolerance (§7.65(e)).
- Sub-0.5% products may state ABV to the nearest 0.01 point, no tolerance (§7.65(b)(2)).

## 5. Cross-commodity comparison table

| Requirement | Wine (Pt 4) | Spirits (Pt 5) | Malt (Pt 7) |
|---|---|---|---|
| Brand name | Brand label | Same field of vision | Any label |
| Class/type | Brand label | Same field of vision | Any label |
| ABV statement | Required >14%; optional ≤14% w/ "table"/"light" | Required, w/ optional co-located proof | Optional unless flavor-derived alcohol; state law governs |
| ABV tolerance | **±1.0 (>14%) / ±1.5 (≤14%)** | **±0.3** | **±0.3** (floor at 0.5%) |
| Net contents | §4.37 + §4.72 fills; front label if non-metric | §5.70; may be molded in glass | §7.70; may be molded in glass |
| Name/address | §4.35 | §§5.66-5.68 | §§7.66-7.68 |
| Sulfites ≥10ppm | Yes | Yes | Yes |
| Yellow 5 / carmine | Yes | Yes | Yes |
| Aspartame all-caps | — | Yes | Yes |
| Health warning | Pt 16 (≥0.5% ABV) | Pt 16 | Pt 16 |

## 6. Rules-engine implications for PLAN.md (corrections and additions)

1. **ABV comparison must be tolerance-aware and commodity-aware** — replace strict stated-precision equality: wine ±1.0/±1.5 by tier, spirits ±0.3, malt ±0.3 with the 0.5% floor. (The earlier competitor-derived "±0.25" TODO was close but wrong; the regulation gives exact numbers.) Class-boundary override: tolerance never rescues a wine across 14% or a "non-alcoholic" claim across 0.5%.
2. **Warning bold check is two-sided**: prefix must be bold+caps; **body must not be bold** — add the second direction to the bold heuristic's spec (still M0 kill-gated).
3. **ABV-statement *format* is itself checkable**: three authorized sentence shapes + authorized abbreviations per §5.65(b)/§7.65(b) — a cheap regex family with per-section citations (feeds the citations TODO).
4. **Absent-ABV disposition must be commodity-aware**: missing ABV on a ≤14% "table wine" or an unflavored beer is *compliant*, not MISMATCH — the beverage-type checklist TODO graduates from nice-to-have to correctness requirement.
5. **Net contents "absent from label" needs a molded-in-glass caveat** for spirits/malt (photo may genuinely not show embossed contents) — route to "not visible in submitted image," never MISMATCH.
6. **Same-field-of-vision (spirits)** and type-size/char-per-inch rules are physical-layout checks: partially checkable with bounding boxes (co-presence in one image region), honestly documented as unverifiable from photos otherwise — matching the existing "type size not checked" disclosure.
7. **Sulfites/Yellow 5/carmine/aspartame** are presence-only string checks with exact statutory phrasings — trivially addable as cited optional checks (aspartame's all-caps requirement mirrors the warning-caps logic already built).
8. The statutory-warning constant in PLAN.md should carry **§16.21's citation and the §16.22 format matrix** in the provenance block, and the golden set should include an *all-bold warning* adversarial case (fails §16.22(a)(2) second clause).
