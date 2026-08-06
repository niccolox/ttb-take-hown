/* Label Check — M3 batch client (master-detail).
   Single-label mode is the same structure with a one-item list auto-selected.
   Rows never reorder; results stream in place; per-row retry; reviewer
   override with audited export (original/final/overwritten). */
"use strict";

const $ = (id) => document.getElementById(id);
const CONCURRENCY = 3;
const FIELD_ORDER = ["brand_name", "class_type", "fanciful_name", "origin",
                     "vintage", "appellation", "grape_varietals",
                     "alcohol_content", "net_contents",
                     "internal_consistency", "government_warning", "image"];
const FIELD_LABELS = {
  brand_name: "Brand name", class_type: "Class / type",
  fanciful_name: "Fanciful name", origin: "Origin",
  vintage: "Vintage", appellation: "Appellation",
  grape_varietals: "Grape varietal(s)",
  alcohol_content: "Alcohol content", net_contents: "Net contents",
  sulfite_declaration: "Sulfite declaration", name_address: "Name & address",
  aspartame_declaration: "Aspartame declaration",
  internal_consistency: "Internal consistency",
  government_warning: "Government Warning", image: "Image",
};
const FAMILY = {
  MATCH: ["green", "✓ MATCH"], LIKELY_MATCH: ["amber", "≈ LIKELY MATCH"],
  WITHIN_TOLERANCE: ["amber", "≈ WITHIN TOLERANCE"], NEEDS_REVIEW: ["amber", "👁 NEEDS REVIEW"],
  MISMATCH: ["red", "✗ MISMATCH"], NOT_CHECKED: ["grey", "— NOT CHECKED"],
  NOT_REQUIRED: ["grey", "○ NOT REQUIRED"],
};
const ITEM_STATES = {   // item lifecycle — status words follow COLAs Online
  // (Received / In Process / Needs Correction); verdict words stay the
  // screening tool's own (never Approved/Rejected — no approval authority)
  waiting: ["grey", "Received"], checking: ["amber", "In Process…"],
  done_green: ["green", "All clear"], pass_agent: ["green", "Pass ·agent"],
  done_amber: ["amber", "Review"],
  done_red: ["red", "Needs Correction"], fail_agent: ["red", "Fail ·agent"],
  error: ["red", "Couldn't finish"],
  canceled: ["grey", "Canceled"],
};

/** items: {id, file, bitmap, app:{beverage_type,brand_name,class_type,
 *  alcohol_content,net_contents}, state, result, override, stale} */
let items = [];
let selectedId = null;
let sessionDirty = false;         // tab state diverges from the DuckDB store
let lastSavedAt = null;
let running = false, cancelRequested = false;
let filter = "all";
let commodityFilter = "all";      // scope facet (COLA commodity), ANDs with `filter`

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const err = (m) => { const e = $("err"); e.textContent = m || ""; e.style.display = m ? "block" : "none"; };

/** Focus restoration (508, TODOS P2): renders rebuild DOM via innerHTML and
 *  drop keyboard focus to <body>. Capture a stable selector for the focused
 *  control before a rebuild and re-focus its successor after. */
function captureFocus() {
  const a = document.activeElement;
  if (!a || a === document.body
      || !a.matches("button, [href], input, select, [tabindex]")) return null;
  if (a.id) return `#${CSS.escape(a.id)}`;
  const parts = [];
  for (const at of a.attributes) {
    if (at.name.startsWith("data-")) parts.push(`[${at.name}="${CSS.escape(at.value)}"]`);
  }
  return parts.length ? a.tagName.toLowerCase() + parts.join("") : null;
}
function restoreFocus(sel) {
  if (!sel) return;
  const el = document.querySelector(sel);
  if (el) el.focus({ preventScroll: true });
}

/** DaisyUI progress bar under the status line: numbers → determinate,
 *  done=null with a total → indeterminate stripe, total=null → hidden. */
function progressBar(done, total) {
  const p = $("progressbar");
  if (total == null) { p.style.display = "none"; p.removeAttribute("value"); return; }
  p.style.display = "block"; p.max = total;
  if (done == null) p.removeAttribute("value");
  else p.value = done;
}

// megamenu dropdowns (details-based) don't close on outside click natively —
// close any open panel when clicking elsewhere, but never while clicking
// inside a panel (loading several eval sets in a row stays one gesture)
document.addEventListener("click", (e) => {
  for (const d of document.querySelectorAll("header details.dropdown[open]")) {
    if (!d.contains(e.target)) d.removeAttribute("open");
  }
});

// ── intake ───────────────────────────────────────────────────────────────────
async function addFiles(files, app = {}) {
  let skipped = 0;
  for (const f of files) {
    if (!(await addItem([{ file: f, panel: "front" }], app))) skipped++;
  }
  if (skipped) err(`${skipped} image(s) already imported — skipped (same name and size).`);
  if (items.length && selectedId === null) select(items[0].id);
  renderList();
}

/** One application = one item; panelFiles = [{file, panel}] front first.
 *  COLA Cloud corpora supply front+back — the warning lives on the back. */
async function addItem(panelFiles, app = {}, registry = null) {
  noteFirstAdd();                            // T5: time-to-first-decision clock
  const f = panelFiles[0].file;
  // same application twice = same primary file (name + size) — skip re-imports
  // (clicking an eval set again, re-choosing a file, restoring over a batch)
  const dup = items.find((x) =>
    x.file.name.toLowerCase() === f.name.toLowerCase() && x.file.size === f.size);
  if (dup) return null;
  const id = `${f.name}-${items.length}-${Date.now() % 1e6}`;
  const panels = [];
  for (const p of panelFiles) {
    panels.push({ file: p.file, panel: p.panel || "front",
                  bitmap: await createImageBitmap(p.file).catch(() => null) });
  }
  markSessionDirty();
  const item = { id, file: f, bitmap: panels[0].bitmap, panels, registry, fieldOverrides: {},
               app: { beverage_type: "unspecified", brand_name: "", class_type: "",
                      fanciful_name: "", origin: "", vintage: "", appellation: "",
                      grape_varietals: "", alcohol_content: "", net_contents: "", ...app },
               state: "waiting", result: null, override: null, stale: false };
  items.push(item);
  return item;
}

$("files").addEventListener("change", (e) => { err(""); addFiles([...e.target.files]); e.target.value = ""; });

$("pair").addEventListener("change", async (e) => {
  err("");
  const fs = [...e.target.files]; e.target.value = "";
  if (!fs.length) return;
  if (fs.length > 2) { err("Front + back takes exactly 2 images — front first."); return; }
  const added = await addItem(fs.map((f, i) => ({ file: f, panel: i === 0 ? "front" : "back" })));
  if (!added) { err("This label is already imported (same front image)."); return; }
  if (selectedId === null) select(added.id);
  renderList();
});

$("tpl").addEventListener("click", () => {
  const csv = "filename,beverage_type,brand_name,class_type,alcohol_content,net_contents,back_filename\r\n" +
              "mylabel.jpg,distilled_spirits,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45% Alc./Vol.,750 mL,mylabel_back.jpg\r\n";
  download("label-check-template.csv", csv);
});

$("csv").addEventListener("change", async (e) => {
  err("");
  const file = e.target.files[0]; e.target.value = "";
  if (!file) return;
  const text = (await file.text()).replace(/^﻿/, "");   // BOM tolerant
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  const header = splitCsv(lines[0] || "").map((h) => h.trim().toLowerCase());
  const need = ["filename", "brand_name"];
  if (!need.every((c) => header.includes(c))) {
    err(`CSV needs at least columns: filename, brand_name (got: ${header.join(", ") || "nothing"}). Download the template for the full format.`);
    return;
  }
  const idx = Object.fromEntries(header.map((h, i) => [h, i]));
  const bevOk = ["wine", "distilled_spirits", "malt_beverage", "unspecified", ""];
  let applied = 0, unmatched = [], badBev = 0, paired = 0;
  for (const line of lines.slice(1)) {
    const cells = splitCsv(line);
    const fname = (cells[idx.filename] || "").trim();
    if (!fname) continue;
    const item = items.find((it) => it.file.name.toLowerCase() === fname.toLowerCase()); // case-insensitive match
    let bev = (cells[idx.beverage_type] || "").trim().toLowerCase();
    if (!bevOk.includes(bev)) { badBev++; bev = "unspecified"; }
    const rec = { beverage_type: bev || "unspecified",
                  brand_name: (cells[idx.brand_name] || "").trim(),
                  class_type: (cells[idx.class_type] || "").trim(),
                  alcohol_content: (cells[idx.alcohol_content] || "").trim(),
                  net_contents: (cells[idx.net_contents] || "").trim() };
    for (const k of ["fanciful_name", "origin", "vintage", "appellation", "grape_varietals"])
      if (idx[k] != null && (cells[idx[k]] || "").trim()) rec[k] = cells[idx[k]].trim();
    if (item) {
      Object.assign(item.app, rec); markStale(item); applied++;
      // optional back_filename: fold that uploaded image in as this label's back panel
      const bname = idx.back_filename != null ? (cells[idx.back_filename] || "").trim() : "";
      if (bname) {
        const bi = items.findIndex((x) => x !== item &&
          x.file.name.toLowerCase() === bname.toLowerCase());
        if (bi >= 0) {
          const back = items[bi];
          item.panels = (item.panels || []).filter((p) => p.panel !== "back");
          item.panels.push({ file: back.file, panel: "back", bitmap: back.bitmap });
          items.splice(bi, 1);                          // absorbed into the front item
          if (selectedId === back.id) selectedId = item.id;
          paired++;
        } else unmatched.push(bname + " (back)");
      }
    }
    else unmatched.push(fname);
  }
  const msgs = [`Manifest applied to ${applied} label(s).`];
  if (paired) msgs.push(`${paired} front+back pair(s) merged.`);
  if (unmatched.length) msgs.push(`${unmatched.length} row(s) had no matching uploaded image: ${unmatched.slice(0, 3).join(", ")}${unmatched.length > 3 ? "…" : ""}`);
  if (badBev) msgs.push(`${badBev} row(s) had an unknown beverage_type — treated as "Not specified".`);
  err(msgs.length > 1 ? msgs.join(" ") : "");
  $("progress").textContent = msgs[0];
  renderList(); renderDetail();
});

function splitCsv(line) {   // minimal quoted-cell support
  const out = []; let cur = "", inQ = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inQ) { if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
               else if (c === '"') inQ = false; else cur += c; }
    else if (c === '"') inQ = true;
    else if (c === ",") { out.push(cur); cur = ""; }
    else cur += c;
  }
  out.push(cur); return out;
}

async function loadSamples() {
  const list = await (await fetch("/api/samples")).json();
  // training set first, in lesson order (train-before-pilot T4) — the five
  // curated lessons ARE the hands-on training; everything else follows
  const training = list.filter((s) => s.training)
    .sort((a, b) => a.training[0] - b.training[0]);
  const rest = list.filter((s) => !s.training);
  if (training.length) {
    const h = document.createElement("p");
    h.className = "note samples-h";
    h.textContent = "Training set — five lessons, one point each:";
    $("samples").appendChild(h);
  }
  for (const s of [...training, ...rest]) {
    if (rest.length && s === rest[0]) {
      const h2 = document.createElement("p");
      h2.className = "note samples-h";
      h2.textContent = "More samples:";
      $("samples").appendChild(h2);
    }
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `<strong>${esc(s.label)}</strong><span class="shows">${esc(s.training ? s.training[1] : s.shows)}</span>`;
    b.addEventListener("click", async () => {
      err("");
      if (s.images?.length) {                 // front+back sample pair
        const panelFiles = [];
        for (const p of s.images) {
          const blob = await (await fetch(p.url)).blob();
          panelFiles.push({ file: new File([blob], `${s.id}_${p.panel}.jpg`,
                                           { type: "image/jpeg" }),
                            panel: p.panel });
        }
        const added = await addItem(panelFiles, s.application);
        if (added) { select(added.id); renderList(); }
        else err("This sample is already imported.");
        return;
      }
      const blob = await (await fetch(s.image)).blob();
      await addFiles([new File([blob], s.id + ".jpg", { type: "image/jpeg" })], s.application);
      select(items[items.length - 1].id);
    });
    $("samples").appendChild(b);
  }
}

// ── list pane (stable order, filters, progress) ──────────────────────────────
// PASS renders its own chip: green must say "Pass ·agent" when the state is
// the reviewer's decision rather than the machine's all-clear
const OV_STATE = { "PASS": "pass_agent", "NEEDS REVIEW": "done_amber", "FAIL": "fail_agent" };
const GREENS = ["done_green", "pass_agent"];
const OV_FIELD_STATUS = { "PASS": "MATCH", "NEEDS REVIEW": "NEEDS_REVIEW", "FAIL": "MISMATCH" };

// whole-label PASS is EARNED, not asserted: every field check must pass —
// machine-green, or resolved by a per-field agent decision (effStatus folds
// those in). Anything amber/red/refining blocks it; NEEDS REVIEW and FAIL
// stay always available.
const PASSING_STATUSES = new Set(["MATCH", "NOT_REQUIRED", "NOT_CHECKED"]);
function passBlockers(it) {
  if (!it.result) return ["no check has run yet"];
  const out = [];
  for (const f of it.result.fields) {
    const name = FIELD_LABELS[f.field] || f.field;
    if (isRefining(it, f)) { out.push(`${name} (still cross-checking)`); continue; }
    if (!PASSING_STATUSES.has(effStatus(it, f))) out.push(name);
  }
  return out;
}

// daisyui button-with-icon treatment for the three decision verbs
const OV_ICONS = {
  "PASS": '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.2" stroke="currentColor" class="size-[1.1em]" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5"/></svg>',
  "NEEDS REVIEW": '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-[1.1em]" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"/></svg>',
  "FAIL": '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.2" stroke="currentColor" class="size-[1.1em]" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/></svg>',
};
const OV_BTN_COLOR = { "PASS": "btn-success", "NEEDS REVIEW": "btn-warning", "FAIL": "btn-error" };
function ovBtnClass(v, pressed) {
  return `btn btn-sm ${OV_BTN_COLOR[v]} ${pressed ? "" : "btn-outline"} gap-1 font-semibold`;
}

function fieldOv(it, name) { return (it.fieldOverrides || {})[name] || null; }

/** field status with any per-field agent override applied */
function effStatus(it, f) {
  const ov = fieldOv(it, f.field);
  return ov ? OV_FIELD_STATUS[ov.value] || f.status : f.status;
}

// AD-12: guard-scoped fields lead with PROCESS, not verdict, while the
// second-engine cross-check is pending — the fast engine's raw read of the
// statutory small print is exactly the read the refinement layers exist to
// correct, so it must never render as a (red) verdict.
const GUARD_FIELDS = new Set(["government_warning", "alcohol_content", "net_contents"]);
function isRefining(it, f) {
  return !!(it.result && it.result.settled === false && !it.stale
            && GUARD_FIELDS.has(f.field) && !fieldOv(it, f.field));
}

let persistTimer = null;
function schedulePersist() {
  // one save shortly after the last verdict lands (a batch saves once, not per label)
  clearTimeout(persistTimer);
  // load-test batches exceed the 200-label session cap — skip auto-save
  // quietly instead of erroring on every settle during a physics run
  if (items.length > 200) {
    $("progress").textContent =
      `${items.length} labels — over the 200-label session cap; results stay in this tab only.`;
    return;
  }
  persistTimer = setTimeout(() => {
    persistSession().catch(() =>
      err("Results kept in this tab — saving to the server failed."));
  }, 1500);
}

function packOverride(it) {
  const hasFields = it.fieldOverrides && Object.keys(it.fieldOverrides).length;
  if (!it.override && !hasFields && !it.summary) return null;
  return { whole: it.override || null, fields: hasFields ? it.fieldOverrides : {},
           summary: it.summary || null,            // draft survives reload
           summary_error: it.summaryError || null };   // and so does the debug message
}

function unpackOverride(it, raw) {
  if (raw && typeof raw === "object" && ("whole" in raw || "fields" in raw)) {
    it.override = raw.whole || null;
    it.summary = raw.summary || null;
    it.summaryError = raw.summary_error || null;
    it.fieldOverrides = raw.fields || {};
  } else {                                        // legacy: whole-label only
    it.override = raw || null;
    it.fieldOverrides = {};
  }
}

function ovStamp() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
         `${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

function ovValue(it) {          // override may be a legacy string or {value, at, original}
  return typeof it.override === "string" ? it.override : it.override?.value || null;
}

function autoState(it) {
  if (it.state !== "done") return it.state;
  // a provisional result stays "Checking…" in the Applications list — a
  // green "All clear" must only ever mean the SETTLED verdict (the same
  // no-premature-verdict rule as AD-12, applied to the rollup). Red still
  // shows immediately: a provisional MISMATCH on a non-guard field is
  // actionable attention, and guard fields are excluded while refining.
  const st = it.result.fields.filter((f) => !isRefining(it, f))
    .map((f) => effStatus(it, f));
  const settling = it.result.settled === false && !it.stale;
  if (st.includes("MISMATCH")) return "done_red";
  if (settling) return "checking";
  if (st.some((s) => ["NEEDS_REVIEW", "WITHIN_TOLERANCE", "LIKELY_MATCH"].includes(s))) return "done_amber";
  return "done_green";
}

function itemState(it) {        // the reviewer's override IS the main status
  if (it.state === "done" && ovValue(it)) return OV_STATE[ovValue(it)] || autoState(it);
  return autoState(it);
}

function markSessionDirty() {
  sessionDirty = true;
  updateSaveButton();
}

function updateSaveButton() {
  const btn = $("saveSession");
  if (btn.disabled) return;                       // mid-save; persistSession restores it
  btn.textContent = sessionDirty || !lastSavedAt
    ? "Save session" + (sessionDirty && lastSavedAt ? " •" : "")
    : `Saved ✓ ${lastSavedAt.slice(11, 16)}`;
}

function itemTitle(it) {
  // Fanciful name leads, brand follows ('“Pelopee” — Chateau Le Coteau');
  // the filename is the fallback and lives in the tooltip.
  const brand = (it.app.brand_name || "").trim();
  const fanciful = (it.app.fanciful_name || "").trim();
  if (brand && fanciful) return `“${fanciful}” — ${brand}`;
  if (fanciful) return `“${fanciful}”`;
  return brand || it.file.name;
}

function visible(it) {
  // commodity is a SCOPE: it ANDs with the status filter below
  if (commodityFilter !== "all" && it.app.beverage_type !== commodityFilter) return false;
  const s = itemState(it);
  if (filter === "waiting") return s === "waiting";
  if (filter === "attention") return !reviewComplete(it) && ["done_red", "done_amber", "error"].includes(s);
  if (filter === "mismatch") return s === "done_red";
  if (filter === "review") return s === "done_amber";
  if (filter === "allclear") return s === "done_green"; // machine green, no decision yet
  if (filter === "passed") return s === "pass_agent";   // agent PASS decisions
  if (filter === "failed") return s === "fail_agent";   // reviewer FAIL decisions
  if (filter === "progress") return s === "checking";
  return true;
}

function renderList() {
  const focusSel = captureFocus();
  const list = $("list");
  list.innerHTML = "";
  if (!items.length) {
    // empty first-run must offer the two most likely actions in the main
    // field, not only behind the nav menus (UX audit P1)
    const hero = document.createElement("div");
    hero.className = "empty-hero";
    hero.innerHTML = `
      <p class="note" style="margin:0 0 10px">Screen a label against its COLA
        application — start with your own images or a built-in sample.</p>
      <button type="button" class="btn btn-primary btn-block" data-hero="files">Choose label image(s)</button>
      <button type="button" class="btn btn-outline btn-primary btn-block mt-2" data-hero="sample">Try a sample</button>
      <button type="button" class="btn btn-ghost btn-block mt-2" data-hero="tour">▶ Watch a guided sample check (90 s)</button>
      <p class="cite" style="margin-top:10px">Batches: Add labels → Import CSV manifest.
        Eval sets and registry pipelines live in the top navigation.</p>`;
    hero.querySelector('[data-hero="files"]').addEventListener("click", () => $("files").click());
    hero.querySelector('[data-hero="tour"]').addEventListener("click", () => startTour());
    hero.querySelector('[data-hero="sample"]').addEventListener("click", (e) => {
      e.stopPropagation();  // same: don't let the outside-click closer undo the open
      const d = document.querySelectorAll("header details")[1];
      d?.setAttribute("open", "");
      d?.querySelector("#samples button")?.focus();
    });
    list.appendChild(hero);
  }
  // commodity counts are unfiltered totals; status counts recompute within
  // the selected commodity (facet convention: numbers answer "what's in
  // front of me now")
  const cCounts = { wine: 0, malt_beverage: 0, distilled_spirits: 0, unspecified: 0 };
  for (const it of items) {
    const b = it.app.beverage_type || "unspecified";
    cCounts[b] = (cCounts[b] || 0) + 1;
  }
  if (commodityFilter !== "all" && !cCounts[commodityFilter]) commodityFilter = "all";
  const inScope = (it) => commodityFilter === "all"
    || it.app.beverage_type === commodityFilter;
  const counts = { waiting: 0, attention: 0, mismatch: 0, review: 0,
                   allclear: 0, passed: 0, progress: 0, failed: 0, all: 0 };
  for (const it of items) {
    if (!inScope(it)) continue;
    counts.all++;
    const s = itemState(it);
    if (!reviewComplete(it) && ["done_red", "done_amber", "error"].includes(s)) counts.attention++;
    if (s === "done_green") counts.allclear++;   // machine green, undecided
    if (s === "pass_agent") counts.passed++;     // agent PASS decisions
    if (s === "fail_agent") counts.failed++;     // decided FAILs get their own row
    if (s === "done_red") counts.mismatch++;     // machine mismatch, undecided
    if (s === "done_amber") counts.review++;     // machine amber, undecided
    if (s === "waiting") counts.waiting++;       // queued, not yet started
    if (s === "checking") counts.progress++;     // actively verifying/refining
  }
  for (const it of items) {                      // insertion order — never reorder
    if (!visible(it)) continue;
    const state = itemState(it);
    const [cls, txt] = ITEM_STATES[state] || ITEM_STATES.waiting;
    const b = document.createElement("button");
    b.className = "list-item"; b.type = "button";
        b.setAttribute("aria-current", String(it.id === selectedId));
    b.title = it.file.name;
    // glyph follows the VERDICT family, never "decided-ness" — a checkmark
    // on a Fail chip read as approval (UX audit P1)
    const glyph = { done_green: "✓ ", pass_agent: "✓ ", done_amber: "👁 ",
                    done_red: "✗ ", fail_agent: "✗ ", error: "✗ " }[state] || "";
    b.innerHTML = `<span class="fn">${esc(itemTitle(it))}
        <span class="cite fn-file">${esc(it.file.name)}</span></span>
      <span class="loz ${cls}">${glyph}${txt}${it.stale ? " ⟳" : ""}</span>`;
    const mini = document.createElement("img");
    mini.className = "mini"; mini.alt = "";           // decorative; the title names the label
    mini.loading = "lazy";
    if (!it.thumbUrl) it.thumbUrl = URL.createObjectURL(it.file);   // front panel, cached per item
    mini.src = it.thumbUrl;
    b.prepend(mini);
    b.dataset.id = it.id;
    b.addEventListener("click", () => select(it.id));
    list.appendChild(b);
  }
  const done = items.filter((i) => i.state === "done").length;
  if (items.length) {
    $("progress").textContent = running
      ? `${done} of ${items.length} checked`
      : done === items.length && done > 0
        ? completionText()
        : `${items.length} received — ${done} checked`;
    progressBar(running ? done : null, running ? items.length : null);
    const allDone = !running && items.length > 0 && items.every(reviewComplete);
    $("progress").classList.toggle("text-success", allDone);
    $("progress").classList.toggle("font-bold", allDone);
  }
  $("subnav").style.display = items.length ? "flex" : "none";
  {
    const C_LABEL = { all: "All", wine: "🍷 Wine", malt_beverage: "🍺 Malt",
                      distilled_spirits: "🥃 Spirits", unspecified: "Not specified" };
    for (const btn of $("commodities").querySelectorAll("button")) {
      const c = btn.dataset.c;
      const n = c === "all" ? items.length : (cCounts[c] ?? 0);
      btn.setAttribute("aria-pressed", String(c === commodityFilter));
      btn.disabled = c !== "all" && n === 0;        // empty scope: disable, don't hide
      if (c === "unspecified") btn.style.display = n ? "" : "none";
      btn.innerHTML = `${C_LABEL[c]} <span class="ccnt">${n}</span>`;
    }
  }
  $("saveSession").style.display = items.length ? "inline-block" : "none";
  updateSaveButton();
  const FILTER_META = {   // literal colors — the old CSS vars left with the restyle
    waiting: ["Received", "#5f5f5f", "#efefef"],
    attention: ["Needs attention", "#b3261e", "#fdecea"],
    mismatch: ["Needs Correction", "#b3261e", "#fdecea"],
    review: ["Needs review", "#8a6d00", "#fff7d6"],
    allclear: ["All clear", "#2e7d32", "#e8f5e9"],
    passed: ["Passed ·agent", "#2e7d32", "#e8f5e9"],
    failed: ["Failed ·agent", "#b3261e", "#fdecea"],
    progress: ["In Process", "#005ea2", "#e8f1f8"],
    all: ["All", "#005ea2", "#e8f1f8"],
  };
  for (const btn of $("filters").querySelectorAll("button")) {
    btn.setAttribute("aria-pressed", String(btn.dataset.f === filter));
    const c = counts[btn.dataset.f] ?? 0;
    const [label, dot, tint] = FILTER_META[btn.dataset.f] || [btn.dataset.f, "var(--grey)", "transparent"];
    const pct = items.length ? Math.round((c / items.length) * 100) : 0;
    btn.innerHTML = `<span class="dot" style="background:${dot}"></span>
      <span class="flabel">${label}</span><span class="cnt">${c}</span>`;
    btn.style.background = `linear-gradient(to right, ${tint} ${pct}%, #fff ${pct}%)`;
  }
  $("verifyAll").style.display = items.length ? "inline-block" : "none";
  $("verifyAll").textContent = items.length > 1 ? "Verify all" : "Verify label";
  $("cancel").style.display = running ? "inline-block" : "none";
  $("export").style.display = done > 0 ? "inline-block" : "none";
  restoreFocus(focusSel);
}

/** An application's review is COMPLETE when it has a final disposition:
 *  effectively green (auto all-clear, or ambers/reds resolved by agent
 *  decisions), or an explicit whole-label PASS/FAIL. A red or amber with no
 *  decision — or a "NEEDS REVIEW" override — is still open. */
function reviewComplete(it) {
  if (it.state !== "done") return false;
  const ov = ovValue(it);
  if (ov === "PASS" || ov === "FAIL") return true;
  return GREENS.includes(itemState(it));
}

function completionText() {
  const total = items.length;
  const complete = items.filter(reviewComplete).length;
  if (complete === total && total > 0) {
    const passed = items.filter((it) => GREENS.includes(itemState(it))).length;
    const failed = total - passed;
    return `✓ Review complete — ${total} application${total > 1 ? "s" : ""} decided ` +
           `(${passed} passed${failed ? `, ${failed} failed` : ""})`;
  }
  let g = 0, a = 0, r = 0;
  for (const it of items) {
    const s = itemState(it);
    if (GREENS.includes(s)) g++; else if (s === "done_amber") a++; else if (["done_red", "fail_agent", "error"].includes(s)) r++;
  }
  return `Checked: ${g} matched, ${a} need review, ${r} need correction/failed — ` +
         `${complete} of ${total} reviews complete`;
}

$("filters").addEventListener("click", (e) => {
  const f = e.target.closest("button")?.dataset.f;
  if (f) { filter = f; renderList(); }
});

$("commodities").addEventListener("click", (e) => {
  const c = e.target.closest("button")?.dataset.c;
  if (c) { commodityFilter = c; renderList(); }
});

// ── train-before-pilot: guided walk-through (T1) + usage beacons (T5) ────────
// beacons are local-only (same-origin /api/telemetry → E4 stream); they
// never block or break anything
function beacon(event, ms) {
  try {
    fetch("/api/telemetry", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ms == null ? { event } : { event, ms }) });
  } catch { /* telemetry never matters more than the work */ }
}

let firstAddAt = null, firstDecisionSent = false;
function noteFirstAdd() { firstAddAt ||= performance.now(); }
function noteDecision() {
  if (firstDecisionSent || firstAddAt == null) return;
  firstDecisionSent = true;
  beacon("first_decision", performance.now() - firstAddAt);
}

let tourT0 = null;
const TOUR_STEPS = [
  { title: "The application's journey",
    sel: () => document.querySelector("#detail .timing-steps"),
    text: "Every label moves through the same four steps: Received → Screened " +
          "(the fast read) → Cross-checked (a second engine double-checks) → " +
          "Your decision. The last step is always yours — the tool never decides." },
  { title: "The verdict summary",
    sel: () => document.querySelector("#detail .banner"),
    text: "One line, color-coded. Green: everything matched. Amber: something " +
          "needs your eyes. Red: a check failed — this sample has a planted " +
          "defect, so it's red and names the field." },
  { title: "A field row: claim, evidence, decision",
    sel: () => [...document.querySelectorAll("#detail .row")]
      .find((r) => /Government Warning/i.test(r.querySelector(".fname")?.textContent || ""))
      || document.querySelector("#detail .row"),
    text: "Each row shows what the label says next to what the application " +
          "says, with a crop of the exact spot on the label as evidence. This " +
          "warning is printed in title case — the law requires capitals, and " +
          "the sub-checks below the row say exactly that. The ✓ 👁 ✗ buttons " +
          "record YOUR decision for this row." },
  { title: "Your decision — the whole label",
    sel: () => document.querySelector("#detail .override"),
    text: "PASS stays locked until every row passes — machine-green or decided " +
          "by you. NEEDS REVIEW and FAIL are always available. For this label, " +
          "FAIL is one click, and the record keeps what the machine found." },
  { title: "That's the whole job",
    sel: () => document.querySelector(".batchbar"),
    text: "Add real labels (or a CSV batch), let the checks run, decide, then " +
          "Export results or Save session. The one-page runbook in the footer " +
          "covers everything you just saw." },
];

function endTour(completed) {
  document.querySelectorAll(".tour-anchor").forEach((x) => x.classList.remove("tour-anchor"));
  $("tourtip")?.remove();
  if (completed && tourT0 != null) beacon("tour_completed", performance.now() - tourT0);
  tourT0 = null;
}

function showTourStep(i) {
  const step = TOUR_STEPS[i];
  document.querySelectorAll(".tour-anchor").forEach((x) => x.classList.remove("tour-anchor"));
  const el = step.sel();
  if (el) { el.classList.add("tour-anchor"); el.scrollIntoView({ block: "center", behavior: "smooth" }); }
  let tip = $("tourtip");
  if (!tip) {
    tip = document.createElement("div");
    tip.id = "tourtip";
    tip.setAttribute("role", "dialog");
    tip.setAttribute("aria-label", "Guided walk-through");
    document.body.appendChild(tip);
    tip.addEventListener("click", (e) => {
      const act = e.target.closest("button")?.dataset.tour;
      if (act === "next") (i => i < TOUR_STEPS.length ? showTourStep(i) : endTour(true))(Number(tip.dataset.idx) + 1);
      else if (act === "back") showTourStep(Number(tip.dataset.idx) - 1);
      else if (act === "exit") endTour(false);
    });
  }
  tip.dataset.idx = String(i);
  tip.innerHTML = `<strong>${esc(step.title)}</strong><p>${esc(step.text)}</p>
    <div class="tour-nav"><span class="cite">${i + 1} of ${TOUR_STEPS.length}</span>
      ${i > 0 ? '<button type="button" data-tour="back" class="btn btn-xs">Back</button>' : ""}
      <button type="button" data-tour="next" class="btn btn-xs btn-primary">
        ${i === TOUR_STEPS.length - 1 ? "Done" : "Next"}</button>
      <button type="button" data-tour="exit" class="btn btn-xs btn-ghost">Exit</button></div>`;
  tip.querySelector('[data-tour="next"]')?.focus();
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && $("tourtip")) endTour(false);
});

async function startTour() {
  if (tourT0 != null) return;                     // already running
  tourT0 = performance.now();
  beacon("tour_started");
  err("");
  try {
    const list = await (await fetch("/api/samples")).json();
    const s = list.find((x) => x.id === "titlecase_trap") || list[0];
    const existing = items.find((x) => x.file.name.startsWith(s.id));
    let it = existing;
    if (!it) {
      const blob = await (await fetch(s.image)).blob();
      await addFiles([new File([blob], s.id + ".jpg", { type: "image/jpeg" })], s.application);
      it = items[items.length - 1];
    }
    select(it.id);
    if (it.state !== "done") await runOne(it);
    // wait for the cross-check to settle so every step shows its final form
    for (let n = 0; n < 40 && it.result && it.result.settled === false; n++)
      await new Promise((r) => setTimeout(r, 500));
    renderDetail();
    showTourStep(0);
  } catch (e) {
    tourT0 = null;
    err("The walk-through couldn't load its sample — try again, or just click a sample in the Samples menu.");
  }
}

// footer workflow/corpora links re-enter the app: file pickers fire
// directly; menu links scroll up and open the matching megamenu
document.querySelector("footer").addEventListener("click", (e) => {
  const act = e.target.closest("[data-act]")?.dataset.act;
  if (!act) return;
  e.preventDefault();
  e.stopPropagation();      // the outside-click menu closer must not see this click
  const MENUS = { "menu-samples": 1, "menu-evalsets": 2, "menu-pipelines": 3 };
  if (act in MENUS) {
    window.scrollTo({ top: 0, behavior: "smooth" });
    const d = document.querySelectorAll("header details")[MENUS[act]];
    d?.setAttribute("open", "");
    d?.querySelector("summary")?.focus();
  } else if (act === "tour") {
    startTour();
  } else if (act === "export") {
    if ($("export").style.display === "none") {
      err("No results to export yet — run a check first.");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else $("export").click();
  } else {
    $(act).click();                 // files / pair / csv inputs
  }
});

// ── detail pane (form + results + override) ──────────────────────────────────
function select(id) { selectedId = id; renderList(); renderDetail(); }
const sel = () => items.find((i) => i.id === selectedId);
function markStale(it) { if (it.state === "done") { it.stale = true; } }

function renderDetail() {
  const focusSel = captureFocus();
  const it = sel();
  const d = $("detail");
  const fp = $("appform");                     // application form column (side by side with the image)
  const badge = $("appstatus");                // disposition summary, top right of the panel
  if (!it) {
    d.innerHTML = '<p class="note">Select a label from the Applications list.</p>';
    fp.innerHTML = '<p class="note">The application values appear here.</p>';
    badge.style.display = "none";
    return;
  }
  {
    const [cls, txt] = ITEM_STATES[itemState(it)] || ITEM_STATES.waiting;
    badge.className = "badge badge-soft font-bold " +
      ({ green: "badge-success", amber: "badge-warning",
         red: "badge-error", grey: "badge-neutral" }[cls] || "badge-neutral");
    badge.textContent = txt;
    badge.style.display = "inline-flex";
  }
  d.innerHTML = ""; fp.innerHTML = "";
  {
    const head = document.createElement("div");
    head.style.marginBottom = "8px";
    const t = document.createElement("strong");
    t.textContent = itemTitle(it);
    const sub = document.createElement("div");
    sub.className = "cite";
    sub.textContent = it.file.name;
    head.append(t, sub);
    d.appendChild(head);
  }
  renderJourney(d, it);
  renderSummaryCard(d, it, "top");   // AI drafts lead the record
  renderAiReview(d, it);             // auto triage when ≥50% of rows troubled
  for (const p of (it.panels || []).filter((p) => p.bitmap)) {
    const img = document.createElement("img");
    img.className = "thumb";
    img.alt = `${p.panel} label panel ${p.file.name}`;
    if ((it.panels || []).length > 1) img.title = `${p.panel} panel`;
    p.thumbUrl ||= URL.createObjectURL(p.file);   // one URL per panel, reused across renders
    img.src = p.thumbUrl;
    // zoom-on-hover magnifier: the image scales up inside its frame with the
    // transform origin tracking the cursor — inspect small print (the
    // warning block) by just pointing at it
    const wrap = document.createElement("div");
    wrap.className = "zoomable";
    wrap.appendChild(img);
    wrap.addEventListener("mousemove", (e) => {
      const r = wrap.getBoundingClientRect();
      img.style.transformOrigin =
        `${(((e.clientX - r.left) / r.width) * 100).toFixed(1)}% ` +
        `${(((e.clientY - r.top) / r.height) * 100).toFixed(1)}%`;
    });
    d.appendChild(wrap);
    {
      // rotate 90° clockwise — re-rasterizes the panel (canvas), so the
      // thumbnail, zoom, AND the next verify all use the upright image
      const rot = document.createElement("button");
      rot.dataset.role = `rotate-${p.panel}`;
      rot.type = "button";
      rot.className = "btn btn-sm btn-outline gap-1 mb-2";
      rot.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="size-[1.1em]" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99"/></svg>' +
        `Rotate ${p.panel} 90°`;
      rot.setAttribute("aria-label", `Rotate the ${p.panel} panel image 90 degrees clockwise`);
      rot.addEventListener("click", async () => {
        rot.disabled = true;
        try {
          const bmp = p.bitmap || await createImageBitmap(p.file);
          const c = document.createElement("canvas");
          c.width = bmp.height; c.height = bmp.width;
          const ctx = c.getContext("2d");
          ctx.translate(c.width, 0);
          ctx.rotate(Math.PI / 2);
          ctx.drawImage(bmp, 0, 0);
          const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.92));
          p.file = new File([blob], p.file.name, { type: "image/jpeg" });
          p.bitmap = await createImageBitmap(p.file);
          if (p.thumbUrl) { URL.revokeObjectURL(p.thumbUrl); p.thumbUrl = null; }
          if (p === (it.panels || [])[0]) { it.bitmap = p.bitmap; }
          markStale(it); markSessionDirty();
          renderList(); renderDetail();
        } finally { rot.disabled = false; }
      });
      d.appendChild(rot);
    }
    if ((it.panels || []).length > 1) {
      const cap = document.createElement("div");
      cap.className = "cite"; cap.style.marginTop = "-8px"; cap.style.marginBottom = "8px";
      cap.textContent = `${p.panel} panel`;
      d.appendChild(cap);
    }
  }
  // attach/replace/remove a back panel — the scan then covers both sides
  {
    const hasBack = (it.panels || []).some((p) => p.panel === "back");
    const bar = document.createElement("div");
    bar.style.cssText = "display:flex;gap:8px;margin-bottom:10px";
    const add = document.createElement("button");
    add.type = "button"; add.className = "btn btn-sm btn-outline btn-primary";
    add.textContent = hasBack ? "Replace back panel image" : "Add back panel image";
    add.addEventListener("click", () => {
      const inp = document.createElement("input");
      inp.type = "file"; inp.accept = "image/png,image/jpeg";
      inp.addEventListener("change", async () => {
        const f = inp.files[0];
        if (!f) return;
        const bitmap = await createImageBitmap(f).catch(() => null);
        it.panels = (it.panels || []).filter((p) => p.panel !== "back");
        it.panels.push({ file: f, panel: "back", bitmap });
        markStale(it);
        renderList(); renderDetail();
      });
      inp.click();
    });
    bar.appendChild(add);
    if (hasBack) {
      const rm = document.createElement("button");
      rm.type = "button"; rm.className = "btn btn-sm btn-outline btn-primary";
      rm.textContent = "Remove back panel";
      rm.addEventListener("click", () => {
        it.panels = (it.panels || []).filter((p) => p.panel !== "back");
        markStale(it);
        renderList(); renderDetail();
      });
      bar.appendChild(rm);
    }
    d.appendChild(bar);
  }
  if (it.registry && Object.keys(it.registry).length) {
    const REG_LABELS = { status: "Status", type_of_application: "Type of application",
      class_type_code: "Class/Type", origin: "Origin",
      brand_name: "Brand name", fanciful_name: "Fanciful name",
      domestic_or_imported: "Domestic/imported", grape_varietals: "Grape varietal(s)",
      wine_vintage_year: "Vintage", wine_appellation: "Appellation",
      total_bottle_capacity: "Total bottle capacity",
      is_distinctive_container: "Distinctive container",
      application_date: "Application date", approval_date: "Approval date",
      expiration_date: "Expiration date", permit_number: "Permit #" };
    const reg = document.createElement("details");
    reg.className = "sub"; reg.style.marginBottom = "10px";
    const summary = document.createElement("summary");
    summary.style.cursor = "pointer"; summary.style.fontWeight = "700";
    const tid = (it.file?.name || "").match(/^(\d{14})/)?.[1];
    summary.textContent = tid ? `COLA Detail — TTB ID ${tid} (registry record)`
                              : "COLA Detail (registry record)";
    reg.appendChild(summary);
    const dl = document.createElement("div");
    for (const [k, label] of Object.entries(REG_LABELS)) {
      let v = it.registry[k];
      if (v === undefined || v === null || v === "") continue;
      if (Array.isArray(v)) v = v.join(", ");
      if (typeof v === "boolean") v = v ? "yes" : "no";
      const row = document.createElement("div");
      row.style.cssText = "display:flex;gap:8px;font-size:13px;padding:1px 0";
      const kEl = document.createElement("span");
      kEl.style.cssText = "color:var(--grey);min-width:150px";
      kEl.textContent = label;
      const vEl = document.createElement("span");
      vEl.textContent = String(v);
      row.append(kEl, vEl);
      dl.appendChild(row);
    }
    reg.appendChild(dl);
    fp.appendChild(reg);
  }
  const form = document.createElement("div");
  form.innerHTML = `
    <label>Beverage type</label>
    <select data-k="beverage_type">
      ${["unspecified|Not specified (strictest checks)", "wine|Wine",
         "distilled_spirits|Distilled spirits", "malt_beverage|Malt beverage (beer)"]
        .map((o) => { const [v, t] = o.split("|");
          return `<option value="${v}" ${it.app.beverage_type === v ? "selected" : ""}>${t}</option>`; }).join("")}
    </select>
    <label>Brand name</label><input type="text" data-k="brand_name" value="${esc(it.app.brand_name)}">
    <label>Class / type</label><input type="text" data-k="class_type" value="${esc(it.app.class_type)}">
    <label>Fanciful name</label><input type="text" data-k="fanciful_name" value="${esc(it.app.fanciful_name || "")}" placeholder="optional — e.g. Pelopee">
    <label>Origin</label><input type="text" data-k="origin" value="${esc(it.app.origin || "")}" placeholder="optional — e.g. France">
    ${it.app.beverage_type === "wine" ? `
    <label>Vintage</label><input type="text" data-k="vintage" value="${esc(it.app.vintage || "")}" placeholder="optional — e.g. 2022">
    <label>Appellation</label><input type="text" data-k="appellation" value="${esc(it.app.appellation || "")}" placeholder="optional — e.g. Margaux">
    <label>Grape varietal(s)</label><input type="text" data-k="grape_varietals" value="${esc(it.app.grape_varietals || "")}" placeholder="optional — any listed matches, e.g. chardonnay/pinot noir">` : ""}
    <label>Alcohol content</label><input type="text" data-k="alcohol_content" value="${esc(it.app.alcohol_content)}" placeholder="e.g. 45% Alc./Vol.">
    <label>Net contents</label><input type="text" data-k="net_contents" value="${esc(it.app.net_contents)}" placeholder="e.g. 750 mL">
    <p class="note">The Government Warning is always checked — no entry needed.</p>`;
  form.addEventListener("change", (e) => {
    const k = e.target.dataset.k;
    if (k) { it.app[k] = e.target.value.trim(); markStale(it); markSessionDirty(); renderList();
             if (it.stale) staleNote.style.display = "block";
             if (k === "beverage_type") renderDetail();   // wine fields show/hide
    }
  });
  fp.appendChild(form);

  const staleNote = document.createElement("p");
  staleNote.className = "ov-note";
  staleNote.textContent = "Values changed since the last check — re-check to refresh this result.";
  staleNote.style.display = it.stale ? "block" : "none";
  fp.appendChild(staleNote);

  const verifyBtn = document.createElement("button");
  verifyBtn.dataset.role = "verify-one";
  verifyBtn.className = "primary"; verifyBtn.type = "button";
  verifyBtn.textContent = it.state === "done" ? "Re-check this label" : "Verify this label";
  verifyBtn.addEventListener("click", () => runOne(it));
  fp.appendChild(verifyBtn);

  if (it.state === "error") {
    const p = document.createElement("p"); p.className = "inline-error";
    p.style.display = "block"; p.textContent = it.errorMsg || "This check didn't finish — retry.";
    fp.appendChild(p);
  }
  if (it.result) renderResult(d, it);
  restoreFocus(focusSel);
}

function bannerFor(fields, it = null) {
  const stat = (f) => (it ? effStatus(it, f) : f.status);
  const names = (s) => fields.filter((f) => stat(f) === s).map((f) => FIELD_LABELS[f.field] || f.field);
  const mis = names("MISMATCH"), rev = names("NEEDS_REVIEW"),
        amber = [...names("WITHIN_TOLERANCE"), ...names("LIKELY_MATCH")];
  if (mis.length) return ["red", `${mis.length} field${mis.length > 1 ? "s don't" : " doesn't"} match the application — see ${mis.join(", ")} below${rev.length ? `; ${rev.length} more need${rev.length > 1 ? "" : "s"} your eyes` : ""}`];
  if (rev.length) return ["amber", `${rev.length} field${rev.length > 1 ? "s need" : " needs"} your eyes — see ${rev.join(", ")} below`];
  if (amber.length) return ["amber", `Everything matches, ${amber.length} small difference${amber.length > 1 ? "s" : ""} to confirm`];
  return ["green", "All checks matched — ready for agent sign-off"];
}

/** The application's full journey as a stepper — every lifecycle step, not
 *  just the two machine stages. Renders for any selected item so an agent
 *  always sees where the case stands and what happens next. The last step
 *  belongs to the AGENT: a machine all-clear never fills it (human primacy,
 *  docs/ai-risk-statement.md). */
function renderJourney(container, it) {
  const st = itemState(it);
  const r = it.result;
  const steps = document.createElement("ul");
  steps.className = "steps timing-steps";
  steps.setAttribute("aria-label", "Application progress");
  const add = (marker, label, cls) => {
    const li = document.createElement("li");
    li.className = "step" + (cls ? " " + cls : "");
    li.dataset.content = marker;
    li.textContent = label;
    steps.appendChild(li);
  };
  // 1 · Received — it's in the list, so this step has happened
  add("✓", "Received", "step-primary");
  // 2 · Screened (first read — what the 5s promise covers)
  const s = it.elapsedMs != null ? it.elapsedMs / 1000 : null;
  const within = s != null && s < 5;
  if (st === "error") add("!", "Couldn't finish", "step-error");
  else if (r && s != null) add(within ? "✓" : "!",
    within ? `Screened ${s.toFixed(1)}s` : `Screened ${s.toFixed(1)}s — over 5s target`,
    within ? "step-primary" : "step-error");
  else if (r) add("✓", "Screened", "step-primary");
  else if (st === "checking") add("●", "Screening…", "step-running");
  else add("○", "Screening", "");
  // 3 · Cross-checked (background QA: second engine, warning re-read)
  const twoStage = r && (r.settled === false || it.settleMs != null
    || (r.jobs || []).length > 0);
  if (r && r.settled === false) add("●", "Cross-checking…", "step-running");
  else if (twoStage) add("✓", it.settleMs != null
    ? `Cross-checked ${(it.settleMs / 1000).toFixed(1)}s` : "Cross-checked",
    "step-primary");
  else if (r) add("○", "Cross-check — single engine", "");
  else add("○", "Cross-check", "");
  // 4 · Disposition — only an agent decision fills this step
  const ov = ovValue(it);
  if (ov === "PASS") add("✓", "Decided — PASS", "step-success");
  else if (ov === "FAIL") add("✗", "Decided — FAIL", "step-error");
  else if (ov === "NEEDS REVIEW") add("👁", "Flagged — needs review", "step-warning");
  else add("○", "Your decision", "");
  container.appendChild(steps);
  if (r && s != null) {     // 5s target (Sarah's threshold) + OCR split, small print
    const sub = document.createElement("p");
    sub.className = "cite timing-sub";
    const ocrNote = r.timing_ms?.ocr != null
      ? `reading the label: ${(r.timing_ms.ocr / 1000).toFixed(1)}s — ` : "";
    sub.textContent = `${ocrNote}first answer ${within ? "within" : "OVER"} the 5-second target`;
    container.appendChild(sub);
  }
}

function renderResult(container, it) {
  const r = it.result;
  // N3 provisional state (AD-12 lean): a verdict with checks still running
  // must never read as the settled answer — name the running layers.
  if (r.settled === false) {
    const pending = (r.pending || []).map((j) => ({
      "second-engine-check": "cross-checking with second engine",
      "warning-reread": "re-reading warning text at full resolution",
    }[j.layer] || j.layer)).join("; ");
    const prov = document.createElement("div");
    prov.className = "timing";
    prov.textContent = `⏳ Preliminary result — ${pending || "additional checks"} still running. Details below may upgrade in a few seconds.`;
    container.appendChild(prov);
  }
  // timing/stage display lives in the journey stepper (renderJourney),
  // which renders above the label image for every selected item
  let [cls, text] = bannerFor(r.fields.filter((f) => !isRefining(it, f)), it);
  const ov = ovValue(it);
  if (ov) {
    cls = { "PASS": "green", "NEEDS REVIEW": "amber", "FAIL": "red" }[ov] || cls;
    text = { "PASS": "PASS — agent decision", "NEEDS REVIEW": "NEEDS REVIEW — agent decision",
             "FAIL": "FAIL — agent decision" }[ov] || text;
  }
  const banner = document.createElement("div");
  banner.className = "banner " + cls; banner.textContent = text;
  container.appendChild(banner);
  if (ov && typeof it.override === "object") {
    const audit = document.createElement("p");
    audit.className = "ov-note";
    audit.textContent = `${(it.override.original || screeningLabel(it)).toLowerCase()} ` +
                        `overridden on ${it.override.at}`;
    container.appendChild(audit);
  }

  // rows live in a per-render host so the delegated field-override listener
  // never stacks on the persistent #detail element (stale-closure hazard)
  const rowsHost = document.createElement("div");
  rowsHost.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-fov]");
    if (!btn) return;
    const name = btn.dataset.field, v = btn.dataset.fov;
    it.fieldOverrides = it.fieldOverrides || {};
    if (it.fieldOverrides[name]?.value === v) {
      delete it.fieldOverrides[name];              // click again to retract
    } else {
      const f = it.result.fields.find((x) => x.field === name);
      noteDecision();                      // T5
      it.fieldOverrides[name] = { value: v, at: ovStamp(),
                                  original: f ? f.status : "" };
    }
    markSessionDirty();
    renderDetail(); renderList();
    schedulePersist();                       // debounced — decisions still auto-save
  });

  const sorted = [...r.fields].sort((a, b) =>
    FIELD_ORDER.indexOf(a.field) - FIELD_ORDER.indexOf(b.field));
  for (const f of sorted) {
    const fov = fieldOv(it, f.field);
    const refining = isRefining(it, f);
    const shown = effStatus(it, f);
    const [fam, chipText] = refining
      ? ["grey", "⏳ CHECKING"]
      : (FAMILY[shown] || ["grey", shown]);
    const origChip = (FAMILY[f.status] || ["grey", f.status])[1];
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div class="fname">${esc(FIELD_LABELS[f.field] || f.field)}</div>
      <div>
        <span class="chip ${fam}">${chipText}${fov ? " ·agent" : ""}</span>
        ${fov ? `<div class="ov-note" style="font-size:12px">${esc(origChip.replace(/^[^A-Za-z]+/, "").toLowerCase())} overridden on ${esc(fov.at)}</div>` : ""}
        <div class="fieldov btns" style="margin-top:4px">
          ${["PASS", "NEEDS REVIEW", "FAIL"].map((v) =>
            `<button type="button" data-fov="${v}" data-field="${esc(f.field)}"
               class="${ovBtnClass(v, fov?.value === v)} btn-square"
               title="${v} this field (agent decision)"
               aria-label="${v} — ${esc(FIELD_LABELS[f.field] || f.field)} (agent decision)"
               aria-pressed="${String(fov?.value === v)}"
               style="min-height:44px;min-width:48px">${OV_ICONS[v]}</button>`).join("")}
        </div>
      </div>
      <div>
        ${refining
          ? `<div class="note">Verifying with second engine — the preliminary read is withheld until the cross-check settles (a few seconds).</div>`
          : `${f.label_value ? `<div class="vals"><span class="lbl">Label says:</span> ${esc(f.label_value)}</div>` : ""}
        ${f.application_value ? `<div class="vals"><span class="lbl">Application says:</span> ${esc(f.application_value)}</div>` : ""}
        <div class="note">${esc(f.note || "")}</div>
        ${f.citation ? `<div class="cite">${esc(f.citation)}</div>` : ""}
        ${(f.sub_results || []).map((s) => `<div class="sub"><strong>${esc(s.check.replace(/_/g, " "))}:</strong> ${esc(s.outcome.toUpperCase())} — ${esc(s.detail)}</div>`).join("")}
        ${f.vlm ? `<div class="sub" style="border-left:3px solid #b58900;padding-left:6px;margin-top:4px"><strong>Vision model suggests:</strong> ${esc(f.vlm.suggestion)}<div class="cite">${esc(f.vlm.disclaimer)} · ${esc(f.vlm.engine)}</div></div>` : ""}
        ${mmRereadHtml(f)}`}
      </div>
      <div class="cropcell"></div>`;
    rowsHost.appendChild(row);
    const evBitmap = (it.panels || [])[f.evidence?.panel ?? 0]?.bitmap || it.bitmap;
    if (f.evidence?.bbox && evBitmap) {
      const c = document.createElement("canvas");
      c.className = "crop";
      // visible zoom affordance rides the cell (UX audit P2) c.tabIndex = 0; c.setAttribute("role", "button");
      c.title = "Click to enlarge — region outlined on the full label";
      const diffBoxes = f.evidence.diff_boxes || null;
      if (drawCrop(c, evBitmap, f.evidence.bbox, 12, diffBoxes)) {
        if (diffBoxes && diffBoxes.length) {
          // diff image gets a full-width cell spanning the row's columns
          const wide = document.createElement("div");
          wide.className = "cropwide";
          wide.appendChild(c);
          const legend = document.createElement("div");
          legend.className = "cite";
          legend.textContent = "boxed: differs from required text; dashed: required words missing here";
          wide.appendChild(legend);
          row.appendChild(wide);
        } else {
          const cell = row.querySelector(".cropcell");
          cell.classList.add("has-crop");
          cell.appendChild(c);
        }
        const open = () => zoomCrop(evBitmap, f.evidence.bbox, diffBoxes);
        c.addEventListener("click", open);
        c.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
        });
      }
    }
  }

  // reviewer override — the agent decides; export carries original/final/overwritten
  container.appendChild(rowsHost);

  const ovBox = document.createElement("div");
  ovBox.className = "override";
  const auto = screeningLabel(it);
  const cur = ovValue(it);
  const blockers = passBlockers(it);
  const passLocked = blockers.length > 0 && cur !== "PASS";   // saved PASS stays retractable
  ovBox.innerHTML = `<strong>Agent decision — whole label (all fields)</strong>
    <div class="note">Screening result: ${esc(auto)}. Your decision becomes the status and is
      saved; per-field decisions live on each row above.</div>
    ${summaryProgressHtml(it)}
    <div class="btns">
      ${["PASS", "NEEDS REVIEW", "FAIL"].map((v) => {
        const locked = v === "PASS" && passLocked;
        return `<button type="button" data-ov="${v}" class="${ovBtnClass(v, cur === v)}"
           aria-pressed="${String(cur === v)}" ${locked ? 'disabled aria-disabled="true"' : ""}
           ${locked ? `title="Every field check must pass first — resolve: ${esc(blockers.join(", "))}"` : ""}
           >${OV_ICONS[v]}${v}</button>`; }).join("")}
    </div>
    ${passLocked ? `<div class="note ov-lock">🔒 PASS unlocks when every field check passes —
      resolve ${esc(blockers.join(", "))} on the row${blockers.length > 1 ? "s" : ""} above
      (or decide NEEDS REVIEW / FAIL now).</div>` : ""}`;
  ovBox.addEventListener("click", (e) => {
    const v = e.target.closest("button")?.dataset.ov;
    if (!v) return;
    if (v === "PASS" && passLocked) return;        // belt + suspenders with disabled
    if (ovValue(it) === v) {
      it.override = null;                            // click again to retract
      it.summary = null;                             // draft dies with the decision
      it.summaryError = null;
    } else {
      noteDecision();                      // T5
      it.override = { value: v, at: ovStamp(), original: auto };
      it.summary = null;
      it.summaryError = null;
      if (v === "PASS" || v === "FAIL") requestSummary(it);   // AI record draft (E3)
    }
    markSessionDirty();
    renderDetail(); renderList();
    schedulePersist();                       // debounced — decisions still auto-save
  });
  container.appendChild(ovBox);
  renderSummaryCard(container, it, "bottom");   // auto-generated fallback as footer
}

// PASS-decision summary (E3): server drafts from the STORED result; absent
// config → 204 → nothing appears (D3). The draft dies with the decision.
async function requestSummary(it) {
  const rid = it.result?.result_id;
  const decision = ovValue(it);
  if (!rid || (decision !== "PASS" && decision !== "FAIL")) return;
  it.summaryPending = true;
  if (sel() === it) renderDetail();
  try {
    const res = await fetch(`/api/verify/${rid}/summary`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, at: ovStamp(), application: it.app,
        overrides: { whole: it.override || null, fields: it.fieldOverrides || {} } }),
    });
    if (res.status !== 200) {
      it.summaryPending = false;
      const skip = res.headers.get("X-Summary-Skip");
      if (res.status === 404) it.summaryError =
        "Draft summary unavailable — this result has expired (restored session). " +
        "Re-check the label, then decide again to draft one.";
      else if (res.status === 204) it.summaryError =
        "Draft summary unavailable — " + ({
          flag_off: "summaries are disabled (LABELCHECK_SUMMARY=off).",
          unavailable: "the Azure OpenAI client is not configured or is cooling down after failures.",
          no_text: "the model returned no text (see server logs; OPENAI_DEBUG=true traces the call).",
          contradiction: "the draft contradicted the recorded verdicts and was withheld.",
        }[skip] || `no content (reason: ${skip || "unknown"}).`);
      else it.summaryError =
        `Draft summary failed — HTTP ${res.status}${skip ? " (" + skip + ")" : ""}.`;
      console.warn("[summary]", res.status, skip || "", "for", rid);
      markSessionDirty(); schedulePersist();      // the debug message survives return
      if (sel() === it) renderDetail();
      return;
    }
    const body = await res.json();
    it.summaryPending = false;
    if (ovValue(it) !== decision) return;    // decision changed while drafting
    it.summary = body;
    markSessionDirty();
    schedulePersist();                        // the draft rides the session save
    if (sel() === it) renderDetail();
  } catch (e) {
    it.summaryPending = false;
    it.summaryError = `Draft summary failed — network error (${e?.message || e}).`;
    console.warn("[summary] network error", e);
    if (sel() === it) renderDetail();
  }
}

function summaryProgressHtml(it) {
  // rendered INSIDE the decision box, between the screening note and the
  // buttons — drafting feedback lives where the decision was made
  const dec = ovValue(it);
  if (dec !== "PASS" && dec !== "FAIL") return "";
  if (it.summaryPending && !it.summary?.text)
    return '<div class="summary-card summary-pending"><span class="loading loading-dots loading-xs"></span> Drafting AI summary…</div>';
  return "";
}

function renderSummaryCard(container, it, where = "top") {
  const dec = ovValue(it);
  if (dec !== "PASS" && dec !== "FAIL") return;
  // the genuine AI draft leads the result; the auto-generated fallback
  // (facts the rows above already show) reads as a footer record instead
  const auto = /AI draft unavailable/i.test(it.summary?.disclaimer || "");
  if (it.summary?.text && ((where === "top" && auto) || (where === "bottom" && !auto)))
    return;
  if (where === "bottom" && !it.summary?.text) return;
  if (!it.summary?.text) {
    if (it.summaryError && !it.summaryPending) {
      const err = document.createElement("div");
      err.className = "summary-card summary-pending";
      err.innerHTML = `<div class="summary-head"><strong>Draft summary</strong>
          <span class="badge badge-soft badge-sm">not available</span>
          <button type="button" class="btn btn-xs btn-outline" data-retry>Retry</button></div>
        <p>${esc(it.summaryError)}</p>`;
      err.querySelector("[data-retry]").addEventListener("click", () => {
        it.summaryError = null;
        requestSummary(it);
        renderDetail();
      });
      container.appendChild(err);
    }
    return;
  }
  const card = document.createElement("div");
  card.className = "summary-card";
  card.innerHTML = `<div class="summary-head"><strong>Draft summary</strong>
      <span class="badge badge-soft badge-sm">${esc(it.summary.disclaimer || "AI-assisted — verify before use")}</span>
      <button type="button" class="btn btn-xs btn-outline" data-copy>Copy</button></div>
    ${it.summary.text.split(/\n\n+/).map((block) => {
      const lines = block.split(/\n/).map((l) => l.trim()).filter(Boolean);
      if (lines.length && lines.every((l) => /^[-•]\s/.test(l)))
        return `<ul>${lines.map((l) => {
          const text = l.replace(/^[-•]\s*/, "");
          const diff = /^override\b|machine found/i.test(text);
          return `<li${diff ? ' class="sum-diff"' : ""}>${esc(text)}</li>`;
        }).join("")}</ul>`;
      return `<p>${esc(block)}</p>`;
    }).join("")}
    <p class="cite">model: ${esc(it.summary.model || "?")} · drafted from the recorded
      result; statuses above are authoritative.</p>`;
  card.querySelector("[data-copy]").addEventListener("click", async (e) => {
    try { await navigator.clipboard.writeText(it.summary.text);
          e.target.textContent = "Copied ✓"; } catch { /* clipboard denied */ }
  });
  container.appendChild(card);
}

// mm second read (mm-ocr-augment D-4): headline chips for agrees /
// sides-with-application ONLY — plain differs/unreadable/error verdicts
// live in the debug details (asymmetric semantics: the second reader is
// weaker than the primary OCR, raw disagreement is noise). Transcription
// text is model-controlled: escaped, control-stripped, capped (T15).
// Fixture-provider chips are visibly demos (amendment 26).
function mmRereadHtml(f) {
  const mm = f.mm_reread;
  if (!mm) return "";
  const clean = (s, n) =>
    esc(String(s || "").replace(/[\u0000-\u001f\u007f]/g, " ").slice(0, n));
  const fixture = mm.model === "fixture";
  const head = mm.verdict === "agrees"
    ? `<strong>Second read: agrees</strong> — ${clean(mm.text, 120)}`
    : mm.verdict === "sides_with_application"
      ? `<strong class="sum-diff">Second read: sides with the application</strong> — ${clean(mm.text, 120)}`
      : "";
  const debug = `<details class="cite"><summary>Second-read debug</summary>
      verdict: ${esc(mm.verdict)}${mm.cause ? ` · cause: ${esc(mm.cause)}` : ""}
      · model: ${esc(String(mm.model || "?"))} · ${mm.elapsed_ms ?? "?"} ms
      ${mm.note ? `<div>${clean(mm.note, 240)}</div>` : ""}
      ${mm.text && !head ? `<div>text: ${clean(mm.text, 240)}</div>` : ""}</details>`;
  if (!head) return `<div class="sub">${debug}</div>`;
  const border = mm.verdict === "sides_with_application" ? "#b58900" : "#2e7d32";
  return `<div class="sub" style="border-left:3px solid ${border};padding-left:6px;margin-top:4px">
      ${head}${fixture ? ' <span class="badge badge-soft badge-sm">fixture demo</span>' : ""}
      <div class="cite">AI second read — suggestion only; the screening verdict above is unchanged.</div>
      ${debug}</div>`;
}

// Troubled-application AI review: auto-triggered server-side when ≥50% of
// checked rows settle MISMATCH/NEEDS_REVIEW. Suggestion-only — and it shows
// its debugging (trigger math, model, timing) so the trust story is visible.
function renderAiReview(container, it) {
  const ai = it.result?.enrichments?.ai_review;
  if (!ai) return;
  const card = document.createElement("div");
  if (ai === "pending") {
    card.className = "summary-card summary-pending";
    card.innerHTML = `<div class="summary-head"><strong>AI review</strong>
        <span class="badge badge-soft badge-sm">running…</span></div>
      <p class="note">Over half of the checks need attention — drafting a triage
        review of this application.</p>`;
    container.appendChild(card);
    return;
  }
  const dbg = ai.debug || {};
  const bullets = (ai.text || "").split(/\n/).map((l) => l.trim())
    .filter((l) => /^[-•]\s/.test(l)).map((l) => l.replace(/^[-•]\s*/, ""));
  const body = bullets.length
    ? `<ul>${bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>`
    : `<p>${esc(ai.text || "")}</p>`;
  card.className = "summary-card";
  card.innerHTML = `<div class="summary-head"><strong>AI review — troubled application</strong>
      <span class="badge badge-soft badge-sm badge-warning">${esc(ai.disclaimer || "AI triage — the agent decides")}</span></div>
    ${body}
    <details class="cite"><summary>Debug — why this ran</summary>
      <div>trigger: ${dbg.flagged ?? "?"}/${dbg.counted ?? "?"} checked rows troubled —
        ratio ${dbg.ratio ?? "?"} ≥ threshold ${dbg.threshold ?? "?"}</div>
      <div>flagged: ${esc((dbg.flagged_fields || []).map((f) =>
        `${f.field}=${f.status}${f.reason ? ` (${f.reason})` : ""}`).join(", "))}</div>
      <div>model: ${esc(String(dbg.model || "?"))} · dialect: ${esc(String(dbg.dialect || "?"))}
        · elapsed: ${dbg.elapsed_ms ?? "?"} ms
        · fallback: ${dbg.fallback ? "yes — deterministic (model returned no text)" : "no"}</div>
    </details>`;
  container.appendChild(card);
}

function screeningLabel(it) {
  const s = autoState(it);
  return { done_green: "All clear", pass_agent: "Passed by agent decision",
           fail_agent: "Failed by agent decision",
           done_amber: "Needs review", done_red: "Needs correction",
           checking: "In Process", error: "Couldn't finish" }[s] || "Received";
}

// ── crops ────────────────────────────────────────────────────────────────────
const DIFF_COLORS = { differs: "#b3261e", missing_here: "#8a6d00" };

function strokeDiffBoxes(ctx, diffBoxes, mapX, mapY) {
  for (const d of diffBoxes || []) {
    const [bx1, by1, bx2, by2] = d.box;
    ctx.strokeStyle = DIFF_COLORS[d.kind] || "#b3261e";
    ctx.setLineDash(d.kind === "missing_here" ? [4, 3] : []);
    ctx.lineWidth = 2;
    ctx.strokeRect(mapX(bx1), mapY(by1), mapX(bx2) - mapX(bx1), mapY(by2) - mapY(by1));
  }
  ctx.setLineDash([]);
}

function drawCrop(canvas, bitmap, bbox, pad = 12, diffBoxes = null) {
  const [x1, y1, x2, y2] = bbox;
  const sx = Math.max(0, x1 - pad), sy = Math.max(0, y1 - pad);
  const sw = Math.min(bitmap.width - sx, x2 - x1 + 2 * pad);
  const sh = Math.min(bitmap.height - sy, y2 - y1 + 2 * pad);
  if (sw <= 0 || sh <= 0) return false;
  const scale = (diffBoxes && diffBoxes.length ? 140 : 56) / sh;  // taller when boxing a diff (full-width row)
  canvas.width = Math.max(1, sw * scale); canvas.height = Math.round(sh * scale);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(bitmap, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  strokeDiffBoxes(ctx, diffBoxes, (x) => (x - sx) * scale, (y) => (y - sy) * scale);
  return true;
}

function zoomCrop(bitmap, bbox, diffBoxes = null) {
  const c = $("zoomc");
  const maxW = Math.min(window.innerWidth * 0.85, bitmap.width);
  const scale = maxW / bitmap.width;
  c.width = bitmap.width * scale; c.height = bitmap.height * scale;
  const ctx = c.getContext("2d");
  ctx.drawImage(bitmap, 0, 0, c.width, c.height);
  ctx.strokeStyle = "#b3261e"; ctx.lineWidth = 3;
  ctx.strokeRect(bbox[0] * scale, bbox[1] * scale,
                 (bbox[2] - bbox[0]) * scale, (bbox[3] - bbox[1]) * scale);
  strokeDiffBoxes(ctx, diffBoxes, (x) => x * scale, (y) => y * scale);
  $("zoom").showModal();
}

// ── verification runs (fan-out, per-item independence, cancel-waiting) ───────
async function runOne(it) {
  const anyField = ["brand_name", "class_type", "fanciful_name", "origin", "vintage",
                    "appellation", "grape_varietals", "alcohol_content", "net_contents"]
    .some((k) => it.app[k]);
  if (!anyField) { err("Enter at least one field to check — the Government Warning is always checked."); return; }
  err("");
  it.state = "checking"; it.stale = false; it.override = null; it.fieldOverrides = {};
  renderList(); if (sel() === it) renderDetail();
  const t0 = performance.now();
  try {
    const fd = new FormData();
    for (const p of (it.panels || [{ file: it.file }])) fd.append("images", p.file);
    fd.append("application", JSON.stringify(it.app));
    // batch physics: a 300-label run WILL hit the per-IP rate limiter — a
    // 429 is pacing, not failure; honor Retry-After instead of erroring
    // the item (measured: 19/30 rapid submits 429'd at default limits)
    let res, body;
    for (let attempt = 0; ; attempt++) {
      res = await fetch("/api/verify", { method: "POST", body: fd });
      body = await res.json();
      if (res.status === 429 && attempt < 60) {
        const wait = Math.min(10, parseInt(res.headers.get("Retry-After") || "2", 10) || 2);
        $("progress").textContent = `Rate limit pacing — retrying in ${wait}s…`;
        await new Promise((r) => setTimeout(r, wait * 1000));
        continue;
      }
      break;
    }
    if (!res.ok) throw new Error(body.error || "This check didn't finish — retry.");
    it.result = body; it.state = "done"; it.errorMsg = null;
    it.elapsedMs = performance.now() - t0;
    markSessionDirty();
    // N3: provisional results settle via background layers — poll until
    // settled (AD-34), applying only monotonically newer revisions (AD-19).
    if (body.settled === false && body.result_id) pollRefinements(it, body.result_id);
  } catch (e) {
    it.state = "error"; it.errorMsg = e.message;
    markSessionDirty();
  }
  renderList(); if (sel() === it) renderDetail();
  schedulePersist();                     // status (all clear / review / mismatch) is saved
}

// N3 refinement polling (AD-19): 1s → backoff → stop at settled or 60s.
// The reviewer's own decisions always win — a refinement never reopens an
// overridden field (precedence rule AD-18 is enforced server-side; here we
// only swap in newer machine results and re-render).
async function pollRefinements(it, resultId) {
  const pollStart = performance.now();      // stage-2 clock starts at handoff
  let delay = 1000, deadline = Date.now() + 60000, settledAt = 0;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, delay));
    delay = Math.min(delay * 1.5, 5000);
    if (it.state !== "done" || !it.result || it.result.result_id !== resultId) return;
    let body;
    try {
      const res = await fetch(`/api/verify/${resultId}`);
      if (res.status === 404) {
        // the server restarted (or the result expired) mid-refinement — the
        // provisional verdict on screen will never settle. Mark it stale (⟳)
        // so its details aren't presented as the answer; re-verify refreshes.
        it.stale = true;
        markSessionDirty(); renderList(); if (sel() === it) renderDetail();
        return;
      }
      if (!res.ok) return;                       // transient: keep last state
      body = await res.json();
    } catch { return; }
    if ((body.revision || 0) > (it.result.revision || 0)) {
      body.cancel_token = it.result.cancel_token; // token only arrives on POST
      it.result = body;
      if (body.settled) {                    // total = stage 1 + cross-check wait
        it.settleMs = (it.elapsedMs || 0) + (performance.now() - pollStart);
      }
      markSessionDirty(); renderList(); if (sel() === it) renderDetail();
      schedulePersist();
    }
    if (body.settled) {
      // Troubled-application AI review: when ≥50% of checked rows settle
      // red/amber the server attaches enrichments.ai_review moments after
      // settle ("pending" → the triage card). Follow it so the card lands
      // without a manual refresh; give up quietly when it never appears
      // (Azure client not configured) or the model is too slow.
      const ai = (body.enrichments || {}).ai_review;
      if (ai && ai !== "pending") return;          // review landed
      const counted = (body.fields || []).filter((f) => f.status !== "NOT_CHECKED");
      const troubled = counted.filter((f) =>
        f.status === "MISMATCH" || f.status === "NEEDS_REVIEW").length;
      if (!counted.length || troubled / counted.length < 0.5) return;
      settledAt = settledAt || Date.now();
      // 90s: the Azure client's incomplete-retry (reasoning models burning
      // the output cap) can take ~55s before the deterministic fallback lands
      const grace = ai === "pending" ? 90000 : 6000;
      if (Date.now() - settledAt > grace) return;
      deadline = Math.max(deadline, settledAt + grace + 2000);
      delay = 1500;
    }
  }
  // 60s without settling (queue backlog, shed jobs): stop polling but never
  // leave a provisional verdict looking final
  if (it.state === "done" && it.result && it.result.result_id === resultId
      && it.result.settled === false) {
    it.stale = true;
    markSessionDirty(); renderList(); if (sel() === it) renderDetail();
  }
}

$("verifyAll").addEventListener("click", async () => {
  if (running) return;
  $("verifyAll").disabled = true;
  const queue = items.filter((it) =>
    ["waiting", "error", "canceled"].includes(it.state) || it.stale);
  if (!queue.length) { err("Nothing to check — all labels are up to date."); return; }
  running = true; cancelRequested = false; renderList();
  let idx = 0;
  const workers = Array.from({ length: Math.min(CONCURRENCY, queue.length) }, async () => {
    while (idx < queue.length) {
      if (cancelRequested) {                 // cancel affects WAITING items only
        for (let j = idx; j < queue.length; j++)
          if (queue[j].state === "waiting") queue[j].state = "canceled";
        idx = queue.length; break;
      }
      const it = queue[idx++];
      await runOne(it);
    }
  });
  await Promise.all(workers);
  running = false;
  $("verifyAll").disabled = false;
  renderList();
  clearTimeout(persistTimer);
  persistSession().catch(() => err("Results kept in this tab — saving to the server failed."));
});

$("cancel").addEventListener("click", () => { cancelRequested = true; });

window.addEventListener("beforeunload", (e) => {
  if (running) { e.preventDefault(); e.returnValue = ""; }
});

// ── export (formula-escaped CSV with override audit columns) ─────────────────
function csvCell(v) {
  let s = String(v ?? "");
  if (/^[=+\-@\t]/.test(s)) s = "'" + s;            // OWASP formula-injection guard
  return `"${s.replace(/"/g, '""')}"`;
}

$("export").addEventListener("click", () => {
  const head = ["filename", "beverage_type", "brand_name", "class_type",
                "alcohol_content", "net_contents", "screening_result",
                "original_result", "final_result", "overwritten", "overridden_at",
                ...FIELD_ORDER.filter((f) => f !== "image").map((f) => `field_${f}`)];
  const rows = [head.map(csvCell).join(",")];
  for (const it of items) {
    if (!it.result && it.state !== "error") continue;
    const orig = screeningLabel(it);
    const final = ovValue(it) || orig;
    const byField = Object.fromEntries((it.result?.fields || []).map((f) => {
      const ov = fieldOv(it, f.field);
      return [f.field, ov ? `${effStatus(it, f)}[agent ${ov.at}]` : f.status];
    }));
    rows.push([it.file.name, it.app.beverage_type, it.app.brand_name, it.app.class_type,
               it.app.alcohol_content, it.app.net_contents,
               it.result?.screening_result || "error", orig, final,
               String(Boolean(it.override || Object.keys(it.fieldOverrides || {}).length)),
               (typeof it.override === "object" && it.override?.at) || "",
               ...FIELD_ORDER.filter((f) => f !== "image").map((f) => byField[f] || "")]
              .map(csvCell).join(","));
  }
  download("label-check-results.csv", "﻿" + rows.join("\r\n"));
});

function download(name, content) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([content], { type: "text/csv" }));
  a.download = name; a.click();
  URL.revokeObjectURL(a.href);
}

async function loadCorpora() {
  const list = await (await fetch("/api/corpora")).json();
  // two groups (left panel): synthetic golden sets vs real registry pulls
  const GROUPS = [
    ["golden", "Golden images (synthetic, controlled truth)"],
    ["cola", "COLA Cloud pipelines (real registry labels)"],
    ["batch", "Load-test batches (300 labels each)"],
  ];
  const host = $("corpora");
  for (const [gid, heading] of GROUPS) {
    const members = list.filter((c) => (c.group || "golden") === gid);
    if (!members.length) continue;
    const h = document.createElement("div");
    h.className = "cite";
    h.dataset.corpusGroup = gid;
    h.style.cssText = "font-weight:700;font-style:normal;margin:10px 0 2px;" +
      "text-transform:uppercase;letter-spacing:.04em";
    h.textContent = heading;
    host.appendChild(h);
    for (const c of members) appendCorpusButton(c);
  }
}

function appendCorpusButton(c) {
  {
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `<strong>${esc(c.label)}</strong><span class="shows">${esc(c.shows)}</span>`;
    b.addEventListener("click", async () => {
      err("");
      b.disabled = true;
      try {
        const items0 = await (await fetch(`/api/corpus/${c.id}`)).json();
        let skipped = 0, loaded = 0;
        $("progress").textContent = `Loading ${items0.length} labels…`;
        progressBar(0, items0.length);
        for (const it of items0) {
          const sources = it.images?.length ? it.images
            : [{ panel: "front", url: it.image }];
          const panelFiles = [];
          for (const s of sources) {
            const blob = await (await fetch(s.url)).blob();
            const name = s.url.split("/").pop();
            panelFiles.push({ file: new File([blob], name, { type: "image/jpeg" }),
                             panel: s.panel });
          }
          if (!(await addItem(panelFiles, it.application, it.registry || null))) skipped++;
          progressBar(++loaded, items0.length);
        }
        progressBar(null, null);
        if (items.length && selectedId === null) select(items[0].id);
        $("progress").textContent = `${c.label} loaded` +
          (skipped ? ` — ${skipped} already imported, skipped` : "") + ` — press "Verify all".`;
      } catch {
        err("Couldn't load that eval set — retry.");
      } finally {
        b.disabled = false;
        renderList();
      }
    });
    $("corpora").appendChild(b);
  }
}

// ── registry pipelines (wine / beer / spirits pulls) ─────────────────────────
const PIPE_LABELS = { wine: "Wine pipeline", beer: "Beer pipeline",
                      spirits: "Spirits pipeline",
                      imported_wine: "Imported wine pipeline",
                      champagne: "Champagne pipeline (imported)",
                      kentucky_whisky: "Kentucky whisky pipeline",
                      napa_zinfandel: "Napa Zinfandel pipeline" };
let pipePoll = null;

async function refreshCorpora() {
  $("corpora").querySelectorAll("button, [data-corpus-group]")
    .forEach((b) => b.remove());
  await loadCorpora();
}

async function renderPipelines() {
  const data = await (await fetch("/api/pipelines")).json();
  const host = $("pipelines");
  host.querySelectorAll("button").forEach((b) => b.remove());
  $("pipelines-note").textContent = data.api_key_configured
    ? "Pull real approved COLAs per commodity; the registry record is the ground truth."
    : "Set COLACLOUD_API_KEY on the server (free key at app.colacloud.us) to enable pulls.";
  let anyRunning = false;
  for (const t of Object.keys(data.pipelines)) {   // server is the source of truth
    const st = data.pipelines[t];
    if (!st) continue;
    if (st.status === "running") anyRunning = true;
    const b = document.createElement("button");
    b.type = "button";
    b.disabled = !data.api_key_configured || st.status === "running";
    const badge = { idle: "", running: " — pulling…", done: ` — done (${st.count})`,
                    error: " — failed" }[st.status] || "";
    b.innerHTML = `<strong>${PIPE_LABELS[t]}${esc(badge)}</strong>
      <span class="shows">${esc(st.message || "Pull 4 approved labels from the registry.")}</span>`;
    b.addEventListener("click", async () => {
      const res = await fetch(`/api/pipelines/${t}/run?per_type=4`, { method: "POST" });
      const body = await res.json();
      if (!res.ok) { err(body.error || "Couldn't start the pull — retry."); return; }
      err("");
      startPipelinePolling();
    });
    host.appendChild(b);
  }
  if (anyRunning && !pipePoll) startPipelinePolling();
  if (!anyRunning && pipePoll) { clearInterval(pipePoll); pipePoll = null; await refreshCorpora(); }
}

function startPipelinePolling() {
  if (pipePoll) return;
  pipePoll = setInterval(renderPipelines, 2500);
}

loadSamples();
loadCorpora();

// ── session persistence (server-side DuckDB) ────────────────────────────────
async function refreshSessionUI() {
  try {
    const s = await (await fetch("/api/session?summary=1")).json();
    $("clearSession").style.display = s.saved ? "inline-block" : "none";
    const show = s.saved && items.length === 0;
    $("restore").style.display = show ? "block" : "none";
    if (show) {
      $("restoreBtn").innerHTML =
        `<strong>Restore saved session</strong><span class="shows">` +
        `${esc(String(s.item_count))} label(s), saved ${esc(s.saved_at || "")}</span>`;
    }
  } catch { /* server without session support */ }
}

async function persistSession(showProgress = false) {
  if (!items.length) return;
  const meta = [];
  const fd = new FormData();
  for (const it of items) {
    const panels = (it.panels || []).map((p) => ({ panel: p.panel, file: p.file.name }));
    meta.push({ file_name: it.file.name, state: it.state, stale: !!it.stale,
                override: packOverride(it),
                application: it.app, result: it.result, panels, registry: it.registry || null,
                verification_status: autoState(it),      // machine verdict
                final_status: itemState(it),             // after agent decisions
                review_complete: reviewComplete(it),
                elapsed_ms: it.elapsedMs != null ? Math.round(it.elapsedMs) : null,
                settle_ms: it.settleMs != null ? Math.round(it.settleMs) : null });
    for (const p of it.panels || []) fd.append("images", p.file);
  }
  fd.append("meta", JSON.stringify(meta));
  const res = await fetch("/api/session", { method: "POST", body: fd });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || "Save failed — retry.");
  sessionDirty = false;
  lastSavedAt = body.saved_at || null;
  if (showProgress) {
    $("progress").textContent = `Session saved (${items.length} labels) at ${body.saved_at}.`;
  }
  updateSaveButton();
  refreshSessionUI();
  return body;
}

$("saveSession").addEventListener("click", async () => {
  err("");
  const btn = $("saveSession");
  btn.disabled = true; btn.textContent = "Saving…";
  try {
    await persistSession(true);
  } catch (e) {
    err(e.message);
  } finally {
    btn.disabled = false; updateSaveButton();
  }
});

$("clearSession").addEventListener("click", async () => {
  err("");
  clearTimeout(persistTimer);              // a scheduled save must not resurrect the session
  sessionDirty = false;
  await fetch("/api/session", { method: "DELETE" });
  $("progress").textContent = "Saved session cleared.";
  refreshSessionUI();
});

async function restoreSession({ quiet = false } = {}) {
  const s = await (await fetch("/api/session")).json();
  if (!s.saved) { if (!quiet) err("No saved session found."); return false; }
    for (const rec of s.items) {
      const panelFiles = [];
      for (const p of rec.panels.length ? rec.panels : [{ panel: "front", file: rec.file_name }]) {
        const r = await fetch(`/api/session/panel/${rec.idx}/${encodeURIComponent(p.panel)}`);
        if (!r.ok) continue;
        const blob = await r.blob();
        panelFiles.push({ file: new File([blob], p.file || rec.file_name,
                                         { type: blob.type || "image/jpeg" }),
                          panel: p.panel });
      }
      if (!panelFiles.length) continue;
      const it = await addItem(panelFiles, rec.application, rec.registry || null);
      if (!it) continue;                       // already in the tab — don't double-import
      it.result = rec.result;
      it.state = rec.result ? "done"
        : (["error", "checking", "canceled"].includes(rec.state) ? "waiting" : rec.state);
      // a session saved mid-refinement carries a PROVISIONAL verdict whose
      // result_id has long expired — mark it stale (⟳) so the sub-check
      // details aren't presented as the settled answer
      if (rec.result && rec.result.settled === false) it.stale = true;
      if (rec.elapsed_ms != null) it.elapsedMs = rec.elapsed_ms;   // timing chip survives
      if (rec.settle_ms != null) it.settleMs = rec.settle_ms;      // both stages survive
      if (rec.stale) it.stale = true;          // out-of-date verdicts stay marked ⟳
      unpackOverride(it, rec.override);
    }
  if (items.length && selectedId === null) select(items[0].id);
  sessionDirty = false;
  lastSavedAt = s.saved_at || null;
  $("progress").textContent = `Restored ${s.items.length} label(s) from the saved session` +
                              (quiet ? ` (saved ${s.saved_at || ""})` : "") + ".";
  renderList(); renderDetail();
  updateSaveButton();
  refreshSessionUI();
  return true;
}

$("restoreBtn").addEventListener("click", async () => {
  err("");
  const btn = $("restoreBtn");
  btn.disabled = true;
  try {
    await restoreSession();
  } catch {
    err("Couldn't restore the saved session — retry.");
  } finally {
    btn.disabled = false;
    refreshSessionUI();
  }
});

(async () => {
  // hard-refresh continuity: if the tab is empty and a session snapshot exists,
  // restore it automatically — statuses, decisions, and timings come back
  // without a click. The manual Restore button remains for after "Clear".
  try {
    if (!items.length) await restoreSession({ quiet: true });
  } catch { /* server without a session — leave the tab empty */ }
  refreshSessionUI();
})();
renderPipelines();
