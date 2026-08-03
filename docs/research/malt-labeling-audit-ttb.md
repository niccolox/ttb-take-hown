# Malt-Beverage Labeling Audit — TTB Guidance vs. Label Check (2026-08-03)

Audited sources (fetched 2026-08-03; ttb.gov "Malt Beverage Labeling" hub
and subpages — the plain-language layer over 27 CFR part 7, post-2020
modernization T.D. TTB-158):

- Hub: ttb.gov/regulated-commodities/beverage-alcohol/beer/labeling
- Alcohol Content (§7.63(a)(3), §7.65)
- Net Contents (§7.63(a)(5), §7.70; tolerance §25.142(d))
- Name and Address, domestic (§7.63(a)(4), §7.66)
- Class and Type Designation (§7.141–7.147)
- Sulfite and Aspartame Declarations (§7.63(b)(3)–(4))

Companion to the wine audits (wine-labeling-audit-ttb.md, wine-bam-c10);
findings M-1..M-9, all amber-at-worst except where the statement itself is
definitively illegal. Part 7 semantics genuinely differ from part 4 in
several places — copying the wine checks over unchanged would have been
wrong in both directions.

## What was already correct

- **ABV requiredness** (§7.63(a)(3)): optional unless alcohol derives from
  added flavors/nonbeverage ingredients — `abv_required(MALT)` already
  returns optional-with-confirm, exactly the page's rule.
- **Tolerance ±0.3** (§7.65(c)) and the two un-rescuable lines: the 0.5%
  floor and the 2.5% low/reduced-alcohol cap ("regardless of any
  tolerance") — `band()` and `crosses_class_boundary()` had both.
- **Blown-in-glass carve-outs** (§7.63(a)(4)–(5)): net contents already
  carried the malt citation; name/address for malt is NOT_CHECKED anyway.
- **No standards of fill**: the §4.72 check is correctly wine-scoped.

## Findings (all implemented)

**M-1 · Ranges prohibited (false-amber → definitive red).** Malt alcohol
content may not be expressed as a range or max/min at all (§7.65(b)). The
range branch treated a malt range like wine's (inside → amber). Now: any
range on a malt label is MISMATCH — the statement itself is the defect.

**M-2 · Statement wording extended to malt (§7.65(b)).** 'ABV' is
prohibited on malt exactly as on wine; malt additionally bans 'ABW' for
alcohol-by-weight. `abv_format_legality` now covers WINE + MALT with the
right citation each; spirits stays unasserted (part 5 not yet audited).

**M-3 · Expression precision.** At 0.5%+ ABV the statement must be to the
nearest 0.1% (§7.65(b)(2)) — '5.25% ALC/VOL' is a wording defect (amber
via the format sub-check); hundredths remain legal under 0.5%.

**M-4/M-5 · Net-contents form (§7.70).** US standard measures are
mandatory; metric may accompany but never replace them (metric-only label
→ amber `metric_only_net`); and exact pint/quart/gallon volumes must be
stated as such — TTB's own example: a 16 fl oz container must say
'1 Pint' (→ amber `net_form`). Agreement with the application does not
launder an unlawful form.

**M-6 · Name/address, malt semantics (§7.66).** Two fixes: (a) 'BREWED
AND CANNED BY' was invisible to the phrase regex (BOTTLED/PACKED/IMPORTED
only) — BREWED and CANNED added, which lit up both beer goldens; (b) the
phrase is OPTIONAL for malt — bottler name + city/state alone satisfy
§7.66 — so absence is NOT_CHECKED (grey, confirm visually), never the
amber the wine rule correctly produces. The bottler-as-brand rescue
(§7.64) applies as it does for wine.

**M-7/M-8 · Sulfites, malt semantics (§7.63(b)(3)).** Declaration found →
informational MATCH. Absence → NO field: unlike wine there is no waiver
regime — most malt beverages are lawfully under 10 ppm — so wine's
"absence is suspicious" amber would be a standing false alarm on beer.
But TTB prohibits negative claims ('sulfite free', 'contains no
sulfites'): those now flag NEEDS_REVIEW (`sulfite_negative_claim`).

**M-9 · Aspartame declaration (§7.63(b)(4)).** Presence-triggered: if the
label mentions aspartame/phenylalanine at all, the required capital-letter
statement "PHENYLKETONURICS: CONTAINS PHENYLALANINE." must be present —
exact-caps match → MATCH, anything else → amber with the found text.
Absence proves nothing about the product and stays silent.

## Noted, out of scope

- Class/type validity ('IPA' alone insufficient, §7.141–147; sub-0.5%
  naming rules §7.145): the application's class/type is the registry's
  call; we match against it rather than adjudicate it.
- State-law variations (ABV mandatory/prohibited by state; type-size
  overrides): jurisdiction facts outside the label image.
- Fill-tolerance accounting (§25.142(d) three-month barrel equivalents):
  brewery records, not label content.
- Type size (1mm/2mm minimums, 3mm/4mm ABV maximums by container size),
  contrasting background: physical-scale facts (footer disclaimer).
- Color additive disclosures, country of origin (imports), alcohol-by-
  weight state formats: unknowable from our application data.

## Verification

Suite 199 passed (+7 malt tests: range prohibition, format legality incl.
precision and ABW, phrase-found/phrase-absent semantics, sulfite
silent/positive/negative, aspartame both forms, net form unit +
verify-level). Both beer goldens re-verified live front+back:
no_mismatch_found with name_address now MATCH.
