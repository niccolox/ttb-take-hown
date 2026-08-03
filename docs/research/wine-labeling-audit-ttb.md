# Wine-Labeling Audit — TTB Guidance vs. Label Check (2026-08-03)

Audited sources (fetched 2026-08-03; ttb.gov "Labeling Wine" hub and
subpages — the plain-language layer over 27 CFR part 4):

- Hub: ttb.gov/regulated-commodities/beverage-alcohol/wine/labeling
- Alcohol Content (§4.36) — audited separately; remediated in `cfb0d7d`
- Declaration of Sulfites (§4.32(e))
- Name and Address (§4.35)
- Net Contents (§4.37, §4.72 standards of fill)
- Appellation of Origin (§4.25; conditions in §4.23/§4.27)
- Grape Variety Designations (§4.23, §4.91/§4.92)
- Brand Name (§4.33, §4.39(i) viticultural significance)

Scope: the wine (part 4) checks in `api/verify.py` + `api/rules/`.
Verdict language: findings are labeled W-1..W-7; every implemented item
lands amber (NEEDS_REVIEW) unless the defect is definitive — screening
posture, the agent decides.

## Coverage matrix (TTB mandatory items)

| TTB mandatory item | Placement rule | Status before audit | Disposition |
|---|---|---|---|
| Brand name | brand label | checked (fuzzy, diacritics, caps) | OK |
| Class/type designation | brand label | checked (slash alternatives) | OK |
| Alcohol content | brand label | deep (post-`cfb0d7d`) | OK |
| Health warning | any label | deepest check in the tool | OK |
| Net contents | any label or blown into bottle | value match only | W-3, W-5 |
| Appellation (conditional) | brand label, with class/type | text-match when supplied | W-4 |
| Sulfite declaration | any label | **not checked** | W-1 |
| Name and address | any label | **not checked** | W-2 |
| % foreign wine / country of origin (imports) / color ingredient disclosures | various | not modeled | out of scope — unknowable from application data |

## Findings

**W-1 · Sulfite declaration (implemented).** "Contains Sulfites" is
mandatory at ≥10 ppm total SO2, and TTB will not approve a COLA without
the declaration unless a TTB-laboratory sulfite waiver is on file. For a
screening tool that means: on a wine label, absence of the statement is
at minimum a review item, presence is checkable text. New wine-only
field `sulfite_declaration`: found → MATCH (informational); not found →
NEEDS_REVIEW naming the waiver path. Never red — the waiver is invisible
to us. "Sulphites" is an authorized spelling; both match. (§4.32(e))

**W-2 · Name & address (implemented).** Every wine label must carry
"Bottled by"/"Packed by" (domestic) or "Imported by" (imports) + name,
city, state, with optional descriptive prefixes (Produced and…, Vinted
and…). New wine-only field `name_address`: presence of the phrase family
→ MATCH with the located line; absence → NEEDS_REVIEW. Identity match
against the permit name is future work (needs registry data). (§4.35)

**W-3 · Standards of fill (implemented).** The tool verified label ==
application but both could agree on an unauthorized size (723 mL sailed
through green). §4.72's authorized list is enumerable: 3 L, 2.25 L,
1.8 L, 1.5 L, 1 L, 750, 720, 700, 620, 600, 568, 550, 500, 473, 375,
360, 355, 330, 300, 250, 200, 187, 180, 100, 50 mL; even liters for
4–17 L; exempt at ≥18 L. Off-list wine fills escalate MATCH →
NEEDS_REVIEW (`nonstandard_fill`) — amber, not red, because the saké
exemption is invisible in our data. (§4.72)

**W-4 · Conditional appellation requiredness (implemented,
application-side).** A vintage date or varietal designation requires an
appellation of origin (§4.27, §4.23(a)) — a relationship between fields
the tool never checked. When the application supplies vintage or
varietals with no appellation, an `appellation` NEEDS_REVIEW row now
flags it. Label-side detection (vintage printed, no appellation
locatable) is future work. The 75%/51% content rules and the §4.91
approved-variety list are unverifiable from a photo — out of scope.

**W-5 · Blown-in-glass carve-out excluded wine (implemented).** The
"net contents may be molded into the container" note fired only for
spirits/malt (§5.70/§7.70), but TTB's wine guidance allows blown/branded
net contents for wine too (§4.37). Wine joins the branch.

**W-6 · Below-7% gate (implemented).** Wine under 7% ABV (much cider
and mead) is FDA-labeled, not FAA/COLA — part 4 mostly does not apply
(the §16.21 health warning still does at 0.5%+). A declared wine ABV
below 7% now annotates the alcohol-content row instead of silently
applying part 4 as if it governed.

**W-7 · Placement & conspicuousness (documented, not implemented).**
Brand name/class/ABV/appellation belong on the *brand label*; the
appellation must sit in direct conjunction with the class/type; every
statement carries 1 mm/2 mm type minimums (by container size) and
contrasting-background/legibility requirements. Panels are treated
equally by design — single-photo submissions can't prove which panel is
the designated brand label — and physical type size needs a scale
reference no photo provides. Recorded in the UI footer disclaimer; the
contrast machinery exists only for the warning (extension possible, low
value).

## Explicitly out of scope (and why)

- Percentage of foreign wine, country of origin, color ingredient
  disclosures: require import/formulation facts absent from our
  application model.
- Misleading-brand-name and viticultural-significance determinations
  (§4.39(i)): TTB decides these case-by-case; not a screening call.
- Varietal percentage rules (75%/51%), vintage percentage rules
  (85%/95%): wine-composition facts, invisible on the label.
- Semi-generic designations, estate bottled, AVA validity (part 9
  boundary data): future work if registry data ever carries them.
