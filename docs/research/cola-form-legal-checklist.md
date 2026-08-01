# COLA Form & Legal Requirements Checklist — 27 CFR Part 5, Subpart B

Sources: 27 CFR Part 5 Subpart B ("Certificates of Label Approval") §§ 5.21–5.30,
read via the Cornell LII mirror of the current CFR (the eCFR site blocks automated
retrieval; citations verified 2026-08-01); TTB Form 5100.31 and its instructions;
the TTB Public COLA Registry detail view (field names cross-checked against a live
registry record, TTB ID 26203001000106); companion doc: `ttb-labeling-rules.md`
(the content rules of Subparts C–I that the label itself must satisfy) and
`cola-fact-sheet.md` (COLAs Online process, 100-point fact sheet).

Scope note: Part 5 governs **distilled spirits**. Wine (Part 4) and malt beverages
(Part 7) have parallel COLA subparts with the same skeleton; the form is common to
all three commodities. This checklist is written from the Part 5 text and marks
commodity-specific items.

---

## 1. The form itself — TTB F 5100.31 field checklist

What a complete application carries (fields as they appear on the form and echo in
the Public Registry detail view):

- [ ] **Serial number** — applicant-assigned, format `YY`+alphanumeric (e.g. 261539).
      *Not derivable from the TTB ID; the TTB ID's last 6 digits are a registry
      sequence, a distinct number.*
- [ ] **Type of application** — label approval / exemption from label approval
      (§5.23) / distinctive liquor bottle approval / resubmission (rejected TTB ID
      referenced).
- [ ] **Vendor code** (registry-assigned) and **plant registry / basic permit /
      brewer's number** of the applicant.
- [ ] **Applicant name and mailing address** (must match the permit).
- [ ] **Brand name** — as it will appear on the container.
- [ ] **Fanciful name** — required when the brand name plus class/type do not
      adequately identify the product; otherwise optional.
- [ ] **Class/type code and designation** (e.g. `straight bourbon whisky`,
      `TABLE RED WINE` code 80, `sparkling wine/champagne` code 81).
- [ ] **Origin code** — country or U.S. state of production (drives §5.30
      certificate obligations for imports).
- [ ] **Grape varietal(s)** — wine only (≥75% rule, 27 CFR 4.23).
- [ ] **Formula number** — when the product requires pre-approval under §5.28 /
      Formulas Online (flavored spirits, specialties); date of approval.
- [ ] **"For sale in ___ only"** — exemption applications (§5.23) must name the
      single state.
- [ ] **Total bottle capacity** — distinctive liquor bottle applications only.
- [ ] **Label images affixed** — every panel of the container (front, back, neck,
      strip) exactly as printed; the approval covers *these images*.
- [ ] **Signature of applicant or authorized representative** under penalties of
      perjury; date of application.
- [ ] **Item 11 / allowable revisions** — awareness that TTB's published list of
      allowable changes (e.g. ABV within the approved class, vintage, net contents)
      may be applied to an approved label *without* a new COLA.

Registry echo (what approval adds): **TTB ID** (14 digits: YY + Julian day received
+ method code + 6-digit sequence), **status** (approved / rejected / surrendered /
expired), **approval date**, **expiration** (rare), **qualifications** printed on
the certificate.

---

## 2. When a COLA is legally required — §§ 5.21, 5.24

- [ ] **Domestic bottling** (§5.21): no person may bottle distilled spirits —
      outside customs custody, for interstate or foreign commerce — without first
      obtaining a COLA. Covers imported bulk spirits bottled in the U.S.
- [ ] **Imports in containers** (§5.24): no removal from customs custody for sale
      or any commercial purpose without a COLA (or authorized use of another
      holder's COLA).
  - [ ] Electronic entry: file the **TTB ID of the valid COLA** with CBP.
  - [ ] Paper entry: present a **copy of the COLA** at entry.
  - [ ] Using another person's COLA: prove authorization, and the label must show
        the **name/trade name and address of the COLA holder**.
  - [ ] Non-conforming containers: relabel **under customs supervision** before
        removal.
- [ ] **Evidence on demand** (§§5.21(b)/5.24, §5.27): produce original COLA,
      copy, or records showing the TTB ID when a TTB officer asks.

## 3. What the COLA authorizes — §§ 5.22, 5.25

- [ ] Containers must bear labels **identical to the labels on the face of the
      COLA**, or with changes **authorized** (by the form's allowable-revisions
      list or TTB public guidance).
- [ ] **Timing**: COLA in hand *before bottling* (domestic) / *before removal
      from customs custody* (imports).
- [ ] Application on **TTB F 5100.31** via COLAs Online or paper; issuance
      procedures in 27 CFR Part 13 (appeal rights, revocation).
- [ ] Any label change beyond the allowable list ⇒ **new COLA before use**.

## 4. Exemption path — § 5.23

- [ ] Available only where the product will **not** enter interstate or foreign
      commerce (single-state distribution).
- [ ] Apply on the same Form 5100.31 (type: exemption), **before bottling**.
- [ ] Label must carry **"For sale in [State] only"**.
- [ ] Distilled spirits plants: see §§19.517–19.518 for companion marking rules.

## 5. Supporting evidence TTB may require — § 5.28

- [ ] **Formula** (Formulas Online or TTB F 5100.51) before or with the COLA
      application, when the product's composition requires it.
- [ ] **Lab test results / samples** on request.
- [ ] Post-issuance: a **full and accurate statement of contents** of any
      container on demand.

## 6. Personalized labels — § 5.29

- [ ] Submit a **template** with the application showing what will vary.
- [ ] May vary: salutations, names, graphics/artwork, congratulatory or event
      dates — **without** reapplying.
- [ ] May not vary: anything describing the **product's characteristics**, or
      anything violating Part 5 or other law.
- [ ] The COLA issues with a **qualification** authorizing the personalization.

## 7. Import certificates of age and origin — § 5.30

| Product | Certificate required | Contents |
|---|---|---|
| Scotch / Irish / Canadian whisky | Origin + age, from the foreign government | type, compliance with home-country law; oak storage period after distillation |
| Brandy | Age | youngest spirit ≥ 2 years oak (or the label's stated age) |
| Cognac | French government origin | grape brandy distilled in the Cognac region |
| Rum | Age — only if the label states age | youngest rum's oak age |
| Tequila | Certificate of Tequila Export (Mexico) | qualifies as tequila; age if stated |
| Other whiskies | Type/production certificate | distillation proof, neutral-spirit content, blend percentages, ages |
| Miscellaneous | Origin, if the home government issues one | — |

- [ ] Importer retains certificate copies **5 years** after removal from customs.

---

## 8. What the Label Check prototype covers (traceability)

Checkable from the label image + application data (this project verifies):

| Checklist item | Prototype field |
|---|---|
| Brand name as applied-for | `brand_name` (case-insensitive match; confusable→review) |
| Fanciful name | `fanciful_name` (optional field) |
| Class/type designation | `class_type` (slash-alternation for registry phrases) |
| Alcohol content vs application | `alcohol_content` (commodity bands; class boundaries never rescued) |
| Proof vs ABV consistency | `internal_consistency` (§5.65(c) 2:1) |
| Net contents | `net_contents` (unit conversion; molded-glass note) |
| Government warning | `government_warning` (§16.21 text, §16.22 caps + bold contrast, visual diff) |
| Origin / state claims | `origin` (vs registry origin) |
| Vintage / appellation / varietals (wine) | `vintage`, `appellation`, `grape_varietals` |
| "Labels identical to the COLA" (§5.22/5.25) | the whole verify loop: approved registry artwork *is* the ground truth in the COLA Cloud eval sets |

Process-level requirements **not** checkable from an image (documented, out of
scope): timing of application vs bottling/customs, formula/lab submissions,
certificate-of-origin paperwork (§5.30), authorization to use another holder's
COLA, exemption commerce restrictions, record retention, CBP filing. The
prototype's role is the §5.22/5.25 *identity* question — does the container's
label match what was approved/applied for — which is exactly the screening task.
