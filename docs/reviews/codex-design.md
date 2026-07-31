# Codex Design Voice (UX challenge) — 2026-07-31

## Classification: APP UI

This is a task-focused operational tool, not marketing and not hybrid. Apply app-UI rules:

- Optimize for speed, clarity, error prevention, and auditability.
- Keep branding quiet and subordinate to the work.
- Favor dense, stable, familiar controls over decorative composition.
- Preserve context while data changes.
- Never hide compliance-critical evidence behind hover, animation, or color alone.

The plan understands the product domain well, but it does not yet specify the interface well enough. It describes capabilities and generic patterns, then leaves the hardest interaction design decisions to the implementer.

## Verdict

The information hierarchy currently serves the data model and development milestones more than the agent’s workflow.

The strongest UI decision is the evidence-first field comparison:

> Label says X + crop / Application says Y

That is exactly the right primary unit. The weakest decision is putting upload, application entry, batch management, progress, file-level status, field-level results, crops, warning diffs, retry, cancellation, CSV import, and export on “one screen” without defining how that screen is organized.

“One screen, no navigation” is a constraint—not a design.

For a 73-year-old usability benchmark, the plan needs explicit screen structure, control behavior, language, and state transitions. “Big,” “plain-language,” and “giant” are aspirations, not specifications.

## Recommended hierarchy

The page should have three permanent regions:

1. **Start a check**
   Upload labels, try a sample, or import a CSV manifest.

2. **Applications**
   One row per file with processing state and compact inline application fields.

3. **Selected application**
   A persistent detail panel containing the image, overall screening summary, and field comparisons.

On desktop, use a master-detail layout: batch list on the left, selected-file evidence on the right. On narrow screens, render those regions sequentially with a conspicuous “Back to applications” control and preserve the selected item and scroll position. That is still one screen and no navigation.

Do not expand complete field results beneath every batch row. Two hundred expanded records with evidence crops would be unusable, slow, and visually chaotic. Batch rows should summarize; selection should reveal detail.

The primary order should be:

1. What requires my attention?
2. Why?
3. What does the label actually show?
4. What did the application expect?
5. What can I do next?

The current plan instead risks leading with system output and status taxonomy.

## Critical ambiguities that will haunt implementation

### 1. Overall status is underdefined

“Worst of checked fields” sounds deterministic but does not define the precedence among all five states. In particular:

- Is `NEEDS REVIEW` worse than `MISMATCH`, or merely less certain?
- Does `LIKELY MATCH` make the file require action?
- What does an all-`NOT CHECKED` record become?
- Can a system error coexist with completed results?
- Does unknown warning boldness change the overall summary?

Use separate concepts:

- **Screening result:** mismatch found, no mismatch found, or screening incomplete.
- **Attention state:** action required or no action required.

Do not force uncertainty, failure, and substantive mismatch onto one severity ladder.

### 2. “Inline application data” is not designed

For hundreds of files, inline fields can become a spreadsheet disguised as a form. The plan must define:

- Which fields appear in the collapsed row.
- Whether fields save on blur, Enter, or an explicit action.
- How missing and invalid values are shown.
- Whether editing invalidates an existing result.
- Whether re-verification is automatic or explicit.
- How “apply to all” previews its scope and supports undo.
- How filename-to-record mapping failures are repaired.
- How duplicate filenames are handled.
- Whether bulk edits affect completed records.

“Apply to all” is especially dangerous. It needs a confirmation showing the field, value, and number of affected files, followed by undo.

### 3. Evidence crops need interaction rules

Crops are central, but their presentation is unspecified:

- Minimum useful dimensions.
- Whether users can enlarge them.
- How the crop relates to the full label.
- What happens when multiple candidate regions exist.
- What is shown when no bounding box exists.
- Whether OCR highlighting can be toggled.
- Whether the crop is oriented and contrast-adjusted differently from the source.
- How crop provenance appears in CSV export, if at all.

A tiny crop beside every row will satisfy the requirement technically while failing the user. Make the crop clickable, open an accessible enlarged view, and show its location on the full image. Never use hover as the only enlargement mechanism.

### 4. Verdicts and reason codes are too system-oriented

The five states are valid, but users should not have to decode their ontology. Every non-match state needs visible next-action language:

- **Likely match:** “Capitalization or punctuation differs—compare both values.”
- **Mismatch:** “Application and label differ.”
- **Needs review—unreadable:** “Image text could not be read—inspect the label or upload a clearer image.”
- **Needs review—absent:** “Expected text was not found—inspect the full label.”
- **Needs review—system error:** “This check did not finish—retry.”
- **Not checked:** “No application value was provided.”

“Absent from label” should not automatically mean `NEEDS REVIEW`. If the system confidently searched a readable label and did not find required text, that is potentially a substantive mismatch. The boundary between “not found” and “unreadable” must be explicit.

### 5. The warning section can become incomprehensible

Three sub-results plus a word-level diff, prefix capitalization, bold confidence, crop, and unchecked properties are too much for one ordinary field row.

Government warning should be a visually distinct grouped check with:

- A one-line summary.
- Three clearly labeled subchecks.
- The evidence image.
- The exact differences, revealed by a button—not permanently expanded.
- A persistent note listing properties the tool does not check.

The diff must be accessible without relying on red/green text or strike-through alone. Use labels such as “Expected,” “Found,” “Missing word,” and “Different capitalization.”

### 6. “Giant chips” will damage scanning

Large status chips repeated across every field and every batch row will dominate the evidence. Status should be highly legible, but not visually louder than the mismatched values.

Use a compact icon-and-text status lozenge with a minimum readable type size. Reserve the large summary treatment for the selected application’s overall result.

### 7. The evaluator path is only partially designed

“Try a sample” is good, but the evaluator should encounter a deliberate 30-minute narrative:

- Clean match.
- Obvious mismatch.
- Title-case government-warning failure.
- Poor image routed to human review.
- Small batch demonstrating independent progress and failure.

The sample chooser must describe what each example demonstrates. A generic demo button that silently loads one sample wastes the product’s strongest proof points.

## Interaction states: insufficiently specified

The plan names several states, but naming is not designing. Most are deferred to M4, which is a major mistake. Empty, loading, partial, and error states determine the architecture of this interface and must be designed before batch implementation.

Required states include:

### Empty

- No files yet.
- Files uploaded but application data missing.
- CSV imported with no filename matches.
- File selected but no checks run.
- All fields `NOT CHECKED`.
- Batch filtered to a category with no results.

The initial empty state should have three obvious choices: upload files, import manifest, or try a sample. Drag-and-drop cannot be the only upload mechanism.

### Loading and queued

Define distinct labels:

- Waiting.
- Uploading.
- Ready to verify.
- Queued.
- Checking.
- Complete.
- Canceled.
- Could not finish.

Show batch progress as exact counts—“18 of 42 checked”—not just a spinner or elapsed time. Per-file progress should not imply precision the OCR pipeline cannot provide.

### Partial completion

This is the core batch state and currently lacks a UI model.

Completed files must remain usable while others process. Sorting and focus must not jump as rows stream in. New results should update in place, not reorder automatically. Provide filters for “Needs attention,” “In progress,” and “All,” with counts.

A system timeout should not convert already completed field checks into a single blanket result. Preserve successful fields and mark only unfinished checks as incomplete.

### Error

Separate:

- Unsupported type.
- Oversized file.
- Corrupt image.
- CSV format error.
- Filename mapping error.
- Server busy.
- OCR failure.
- Timeout.
- Network interruption.
- Export failure.

Each needs a plain explanation, a recovery action, and preservation of entered data. “Service busy” also needs an honest expectation: queued, retry later, or unavailable. Those are different experiences.

### Cancellation and page exit

Define whether cancel affects queued items only or also interrupts active items. The plan says unstarted items stop, so the control should read “Cancel waiting checks,” not simply “Cancel.”

The navigation warning must distinguish between:

- Work actively processing.
- Unsaved browser-only results that will disappear.
- Both.

Because there is no persistence, the page should visibly state “Results are stored only in this browser tab” near export—not bury it in a warning on exit.

## Responsive strategy: currently an afterthought

There is no responsive strategy beyond “one screen.” That is inadequate.

The app should be desktop-first because compliance comparison benefits from width and the likely workplace is a desktop. It should still support tablet and narrow browser windows without losing functionality.

Specify these rules:

- Desktop: master-detail layout with a resizable or fixed-width batch pane.
- Tablet/narrow window: stacked regions with a sticky selected-file summary and explicit return control.
- Never place the evidence crop, label value, and application value in three compressed columns.
- At narrow widths, show them vertically in the semantic order “Label evidence” then “Application value.”
- Batch tables should not depend on horizontal scrolling for status or retry.
- Secondary metadata may collapse; status and action may not.
- Mobile support can be functional rather than optimized, but every action must remain available.

Do not claim responsive design if it merely wraps a desktop table.

## Accessibility: aspirational and scheduled too late

“Accessibility pass” in M4 is a hard failure for this audience. Keyboard behavior, focus management, semantics, and contrast affect component architecture and must begin in M1.

The plan should require:

- WCAG 2.2 AA, not merely “WCAG AA.”
- Minimum 44×44 CSS-pixel pointer targets.
- Default body text of at least 16px; operational values preferably 18px.
- Visible keyboard focus with at least 3:1 contrast against adjacent colors.
- Text and icons accompanying every status color.
- Programmatic labels for all fields and controls.
- Native buttons and inputs wherever possible.
- Keyboard-operable upload through a visible “Choose files” button.
- No drag-and-drop-only interaction.
- A logical focus order that does not change as batch rows complete.
- Focus moved to the first actionable error after submission.
- New status announcements through restrained live regions.
- No announcement for every OCR token or every streaming row update.
- Accessible modal/dialog behavior for enlarged evidence.
- Table semantics only if the batch layout is genuinely tabular.
- Error summaries linked to corresponding inputs.
- Zoom support through 200% without clipped actions or two-dimensional scrolling.
- Contrast requirements for every status and diff state.
- Motion reduction support.
- Testing with keyboard only and at least one screen reader.

Also specify that the all-clear state cannot use a checkmark resembling regulatory approval. The screening-assistant wording is correct, but iconography can still contradict it.

## Specific versus generic design decisions

Specific and good:

- One-screen operational UI.
- Per-file application data as the primary batch path.
- Image evidence beside extracted values.
- Five named verdict states.
- Icon, word, and color status encoding.
- Independent item processing and retry.
- Sample data in the first milestone.
- No approval language.

Generic or incomplete:

- “Big drag-drop zone.”
- “Plain-language form fields.”
- “Giant status chips.”
- “Progress indicator.”
- “Results table.”
- “Accessibility pass.”
- “Graceful service busy state.”
- “Rows streaming in.”
- “Large targets.”
- “No hunting.”
- “One screen.”

These phrases describe intent, not implementable behavior.

## Hard-rejection patterns

No generic marketing card grid is explicitly proposed, but the plan is highly vulnerable to several hard-rejection outcomes:

- **Stacked cards as the entire layout:** likely if every file and field becomes a card. Reject it. Use a batch list plus structured detail.
- **Card inside card inside card:** file card → field card → evidence card → status chip. Reject it.
- **Status-chip wallpaper:** repeated oversized colored pills competing with values and evidence. Reject it.
- **Dashboard cosplay:** summary statistic cards for counts before the actual work. Reject it.
- **Drag-and-drop as a decorative hero:** reject a huge upload zone that consumes the viewport after files have been added. Collapse it to a compact “Add more files” control.
- **Responsive-by-stacking:** reject a desktop grid merely converted into a long mobile column.
- **Mystery icon actions:** retry, cancel, enlarge, and export require visible text labels.
- **Accordion dependence:** do not hide every field or critical mismatch behind nested disclosure controls.
- **Automatic reordering while processing:** reject it; it destroys spatial memory and keyboard focus.
- **Shadow-based hierarchy:** unnecessary for an administrative tool and hostile to visual calm.

Cards are justified only for the selected file’s overall summary or a clearly bounded government-warning group. They are not the base layout primitive.

## Seven litmus checks

| Check | Result | Judgment |
|---|---:|---|
| Brand unmistakable | **NO** | No product identity, agency context, or restrained visual system is specified. For app UI, this should be subtle—but it still needs a recognizable name and purpose. |
| One visual anchor | **YES** | The label image and its evidence crops are the natural anchor. The implementation must keep them visually central. |
| Scannable by headlines | **NO** | The plan has system concepts, not an explicit on-screen heading structure or task-oriented labels. |
| One job per section | **NO** | Upload, data entry, batch control, status, evidence, editing, and export are compressed into an undefined single screen. |
| Cards necessary | **NO** | Most content is relational and tabular. A card-heavy implementation would make it worse. |
| Motion purposeful | **NO** | Streaming results are specified, but update behavior, focus stability, announcements, and reduced motion are not. |
| Premium without shadows | **YES** | Evidence-led typography, spacing, and precise states can make this feel excellent without ornamental elevation. Nothing requires shadows. |

## Priority changes to the plan

Before implementation, add a UI specification milestone ahead of M1 that locks:

1. Desktop master-detail structure and narrow-width behavior.
2. Batch-row anatomy and selected-file detail anatomy.
3. Exact overall-state model and precedence.
4. Every empty, queued, partial, canceled, and error state.
5. Field-editing, stale-result, re-verification, and bulk-apply behavior.
6. Evidence enlargement and full-image location behavior.
7. Keyboard focus rules and WCAG 2.2 AA acceptance criteria.
8. Government-warning subcheck presentation.
9. Stable ordering and filtering during streaming.
10. Evaluator sample flow.

M4 should be visual refinement and validation, not the first time accessibility and “remaining states” are considered.

The product concept is strong. The UI plan is not yet a design—it is a collection of sound requirements surrounding an unresolved screen. If implemented as written, the most likely result is a long stack of cards with oversized status pills, unstable streaming rows, and critical evidence squeezed into thumbnails. Lock the master-detail structure and state model now; everything else depends on them.
