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
  internal_consistency: "Internal consistency",
  government_warning: "Government Warning", image: "Image",
};
const FAMILY = {
  MATCH: ["green", "✓ MATCH"], LIKELY_MATCH: ["amber", "≈ LIKELY MATCH"],
  WITHIN_TOLERANCE: ["amber", "≈ WITHIN TOLERANCE"], NEEDS_REVIEW: ["amber", "👁 NEEDS REVIEW"],
  MISMATCH: ["red", "✗ MISMATCH"], NOT_CHECKED: ["grey", "— NOT CHECKED"],
  NOT_REQUIRED: ["grey", "○ NOT REQUIRED"],
};
const ITEM_STATES = {   // item lifecycle (UI spec: named states)
  waiting: ["grey", "Waiting"], checking: ["amber", "Checking…"],
  done_green: ["green", "All clear"], done_amber: ["amber", "Review"],
  done_red: ["red", "Mismatch"], error: ["red", "Couldn't finish"],
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

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const err = (m) => { const e = $("err"); e.textContent = m || ""; e.style.display = m ? "block" : "none"; };

// ── intake ───────────────────────────────────────────────────────────────────
async function addFiles(files, app = {}) {
  for (const f of files) await addItem([{ file: f, panel: "front" }], app);
  if (items.length && selectedId === null) select(items[0].id);
  renderList();
}

/** One application = one item; panelFiles = [{file, panel}] front first.
 *  COLA Cloud corpora supply front+back — the warning lives on the back. */
async function addItem(panelFiles, app = {}, registry = null) {
  const f = panelFiles[0].file;
  const id = `${f.name}-${items.length}-${Date.now() % 1e6}`;
  const panels = [];
  for (const p of panelFiles) {
    panels.push({ file: p.file, panel: p.panel || "front",
                  bitmap: await createImageBitmap(p.file).catch(() => null) });
  }
  markSessionDirty();
  items.push({ id, file: f, bitmap: panels[0].bitmap, panels, registry,
               app: { beverage_type: "unspecified", brand_name: "", class_type: "",
                      fanciful_name: "", origin: "", vintage: "", appellation: "",
                      grape_varietals: "", alcohol_content: "", net_contents: "", ...app },
               state: "waiting", result: null, override: null, stale: false });
}

$("files").addEventListener("change", (e) => { err(""); addFiles([...e.target.files]); e.target.value = ""; });

$("pair").addEventListener("change", async (e) => {
  err("");
  const fs = [...e.target.files]; e.target.value = "";
  if (!fs.length) return;
  if (fs.length > 2) { err("Front + back takes exactly 2 images — front first."); return; }
  await addItem(fs.map((f, i) => ({ file: f, panel: i === 0 ? "front" : "back" })));
  if (selectedId === null) select(items[items.length - 1].id);
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
  for (const s of list) {
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `<strong>${esc(s.label)}</strong><span class="shows">${esc(s.shows)}</span>`;
    b.addEventListener("click", async () => {
      err("");
      const blob = await (await fetch(s.image)).blob();
      await addFiles([new File([blob], s.id + ".jpg", { type: "image/jpeg" })], s.application);
      select(items[items.length - 1].id);
    });
    $("samples").appendChild(b);
  }
}

// ── list pane (stable order, filters, progress) ──────────────────────────────
const OV_STATE = { "PASS": "done_green", "NEEDS REVIEW": "done_amber", "FAIL": "done_red" };

function ovValue(it) {          // override may be a legacy string or {value, at, original}
  return typeof it.override === "string" ? it.override : it.override?.value || null;
}

function autoState(it) {
  if (it.state !== "done") return it.state;
  const st = it.result.fields.map((f) => f.status);
  if (st.includes("MISMATCH")) return "done_red";
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
  // Applications are identified the way TTB identifies them: brand name plus
  // fanciful name ('Chateau Le Coteau — "Pelopee"'); the filename is the
  // fallback and lives in the tooltip.
  const brand = (it.app.brand_name || "").trim();
  const fanciful = (it.app.fanciful_name || "").trim();
  if (brand && fanciful) return `${brand} — “${fanciful}”`;
  if (fanciful) return `“${fanciful}”`;
  return brand || it.file.name;
}

function visible(it) {
  const s = itemState(it);
  if (filter === "attention") return ["done_red", "done_amber", "error"].includes(s);
  if (filter === "progress") return ["waiting", "checking"].includes(s);
  return true;
}

function renderList() {
  const list = $("list");
  list.innerHTML = "";
  const counts = { attention: 0, progress: 0, all: items.length };
  for (const it of items) {
    const s = itemState(it);
    if (["done_red", "done_amber", "error"].includes(s)) counts.attention++;
    if (["waiting", "checking"].includes(s)) counts.progress++;
  }
  for (const it of items) {                      // insertion order — never reorder
    if (!visible(it)) continue;
    const [cls, txt] = ITEM_STATES[itemState(it)] || ITEM_STATES.waiting;
    const b = document.createElement("button");
    b.className = "list-item"; b.type = "button";
    b.setAttribute("role", "option");
    b.setAttribute("aria-current", String(it.id === selectedId));
    const nPanels = (it.panels || []).length;
    b.title = it.file.name;                       // filename stays discoverable
    b.innerHTML = `<span class="fn">${esc(itemTitle(it))}</span>
      ${nPanels > 1 ? '<span class="loz grey">front+back</span>' : ""}
      <span class="loz ${cls}">${txt}${it.stale ? " ⟳" : ""}</span>`;
    b.addEventListener("click", () => select(it.id));
    list.appendChild(b);
  }
  const done = items.filter((i) => i.state === "done").length;
  if (items.length) {
    $("progress").textContent = running
      ? `${done} of ${items.length} checked`
      : done === items.length && done > 0
        ? completionText()
        : `${items.length} label(s) ready — ${done} checked`;
  }
  $("filters").style.display = items.length > 1 ? "flex" : "none";
  $("saveSession").style.display = items.length ? "inline-block" : "none";
  updateSaveButton();
  for (const btn of $("filters").querySelectorAll("button")) {
    btn.setAttribute("aria-pressed", String(btn.dataset.f === filter));
    const c = counts[btn.dataset.f];
    btn.textContent = `${{ attention: "Needs attention", progress: "In progress", all: "All" }[btn.dataset.f]} (${c})`;
  }
  $("verifyAll").style.display = items.length ? "inline-block" : "none";
  $("verifyAll").textContent = items.length > 1 ? "Verify all" : "Verify label";
  $("cancel").style.display = running ? "inline-block" : "none";
  $("export").style.display = done > 0 ? "inline-block" : "none";
}

function completionText() {
  let g = 0, a = 0, r = 0;
  for (const it of items) {
    const s = itemState(it);
    if (s === "done_green") g++; else if (s === "done_amber") a++; else if (s === "done_red" || s === "error") r++;
  }
  return `Done: ${g} matched, ${a} need review, ${r} mismatched/failed`;
}

$("filters").addEventListener("click", (e) => {
  const f = e.target.closest("button")?.dataset.f;
  if (f) { filter = f; renderList(); }
});

// ── detail pane (form + results + override) ──────────────────────────────────
function select(id) { selectedId = id; renderList(); renderDetail(); }
const sel = () => items.find((i) => i.id === selectedId);
function markStale(it) { if (it.state === "done") { it.stale = true; } }

function renderDetail() {
  const it = sel();
  const d = $("detail");
  if (!it) { d.innerHTML = '<p class="note">Select a label from the Applications list.</p>'; return; }
  d.innerHTML = "";
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
  for (const p of (it.panels || []).filter((p) => p.bitmap)) {
    const img = document.createElement("img");
    img.className = "thumb";
    img.alt = `${p.panel} label panel ${p.file.name}`;
    if ((it.panels || []).length > 1) img.title = `${p.panel} panel`;
    p.file.arrayBuffer().then(() => { img.src = URL.createObjectURL(p.file); });
    d.appendChild(img);
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
    add.type = "button"; add.className = "secondary";
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
      rm.type = "button"; rm.className = "secondary";
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
    d.appendChild(reg);
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
    <label>Vintage</label><input type="text" data-k="vintage" value="${esc(it.app.vintage || "")}" placeholder="optional — e.g. 2022">
    <label>Appellation</label><input type="text" data-k="appellation" value="${esc(it.app.appellation || "")}" placeholder="optional — e.g. Margaux">
    <label>Grape varietal(s)</label><input type="text" data-k="grape_varietals" value="${esc(it.app.grape_varietals || "")}" placeholder="optional — any listed matches, e.g. chardonnay/pinot noir">
    <label>Alcohol content</label><input type="text" data-k="alcohol_content" value="${esc(it.app.alcohol_content)}" placeholder="e.g. 45% Alc./Vol.">
    <label>Net contents</label><input type="text" data-k="net_contents" value="${esc(it.app.net_contents)}" placeholder="e.g. 750 mL">
    <p class="note">The Government Warning is always checked — no entry needed.</p>`;
  form.addEventListener("change", (e) => {
    const k = e.target.dataset.k;
    if (k) { it.app[k] = e.target.value.trim(); markStale(it); markSessionDirty(); renderList();
             if (it.stale) staleNote.style.display = "block"; }
  });
  d.appendChild(form);

  if (items.length > 1) {
    const applyAll = document.createElement("button");
    applyAll.className = "secondary"; applyAll.type = "button";
    applyAll.style.marginTop = "8px";
    applyAll.textContent = "Apply these values to all labels…";
    applyAll.addEventListener("click", () => {
      const n = items.length - 1;
      if (confirm(`Copy beverage type, class/type, ABV, and net contents from this label to the other ${n} label(s)? (Brand name is NOT copied.) You can undo by editing rows individually.`)) {
        for (const other of items) if (other !== it) {
          Object.assign(other.app, { beverage_type: it.app.beverage_type,
            class_type: it.app.class_type, alcohol_content: it.app.alcohol_content,
            net_contents: it.app.net_contents });
          markStale(other);
        }
        renderList();
      }
    });
    d.appendChild(applyAll);
  }

  const staleNote = document.createElement("p");
  staleNote.className = "ov-note";
  staleNote.textContent = "Values changed since the last check — re-check to refresh this result.";
  staleNote.style.display = it.stale ? "block" : "none";
  d.appendChild(staleNote);

  const verifyBtn = document.createElement("button");
  verifyBtn.className = "primary"; verifyBtn.type = "button";
  verifyBtn.textContent = it.state === "done" ? "Re-check this label" : "Verify this label";
  verifyBtn.addEventListener("click", () => runOne(it));
  d.appendChild(verifyBtn);

  if (it.state === "error") {
    const p = document.createElement("p"); p.className = "inline-error";
    p.style.display = "block"; p.textContent = it.errorMsg || "This check didn't finish — retry.";
    d.appendChild(p);
  }
  if (it.result) renderResult(d, it);
}

function bannerFor(fields) {
  const names = (s) => fields.filter((f) => f.status === s).map((f) => FIELD_LABELS[f.field] || f.field);
  const mis = names("MISMATCH"), rev = names("NEEDS_REVIEW"),
        amber = [...names("WITHIN_TOLERANCE"), ...names("LIKELY_MATCH")];
  if (mis.length) return ["red", `${mis.length} field${mis.length > 1 ? "s don't" : " doesn't"} match the application — see ${mis.join(", ")} below${rev.length ? `; ${rev.length} more need${rev.length > 1 ? "" : "s"} your eyes` : ""}`];
  if (rev.length) return ["amber", `${rev.length} field${rev.length > 1 ? "s" : ""} need your eyes — see ${rev.join(", ")} below`];
  if (amber.length) return ["amber", `Everything matches, ${amber.length} small difference${amber.length > 1 ? "s" : ""} to confirm`];
  return ["green", "All checks matched — ready for agent sign-off"];
}

function renderResult(container, it) {
  const r = it.result;
  if (it.elapsedMs != null) {                       // 5s target (Sarah's threshold) made visible
    const s = it.elapsedMs / 1000;
    const within = s < 5;
    const timing = document.createElement("div");
    timing.className = "timing " + (within ? "ok" : "over");
    const ocr = r.timing_ms?.ocr != null ? ` (reading the label: ${(r.timing_ms.ocr / 1000).toFixed(1)}s)` : "";
    timing.textContent = within
      ? `⏱ Checked in ${s.toFixed(1)}s — within the 5-second target${ocr}`
      : `⏱ Checked in ${s.toFixed(1)}s — OVER the 5-second target${ocr}`;
    container.appendChild(timing);
  }
  let [cls, text] = bannerFor(r.fields);
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

  const sorted = [...r.fields].sort((a, b) =>
    FIELD_ORDER.indexOf(a.field) - FIELD_ORDER.indexOf(b.field));
  for (const f of sorted) {
    const [fam, chipText] = FAMILY[f.status] || ["grey", f.status];
    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div class="fname">${esc(FIELD_LABELS[f.field] || f.field)}</div>
      <div><span class="chip ${fam}">${chipText}</span></div>
      <div>
        ${f.label_value ? `<div class="vals"><span class="lbl">Label says:</span> ${esc(f.label_value)}</div>` : ""}
        ${f.application_value ? `<div class="vals"><span class="lbl">Application says:</span> ${esc(f.application_value)}</div>` : ""}
        <div class="note">${esc(f.note || "")}</div>
        ${f.citation ? `<div class="cite">${esc(f.citation)}</div>` : ""}
        ${(f.sub_results || []).map((s) => `<div class="sub"><strong>${esc(s.check.replace(/_/g, " "))}:</strong> ${esc(s.outcome.toUpperCase())} — ${esc(s.detail)}</div>`).join("")}
      </div>
      <div class="cropcell"></div>`;
    container.appendChild(row);
    const evBitmap = (it.panels || [])[f.evidence?.panel ?? 0]?.bitmap || it.bitmap;
    if (f.evidence?.bbox && evBitmap) {
      const c = document.createElement("canvas");
      c.className = "crop"; c.tabIndex = 0; c.setAttribute("role", "button");
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
          row.querySelector(".cropcell").appendChild(c);
        }
        const open = () => zoomCrop(evBitmap, f.evidence.bbox, diffBoxes);
        c.addEventListener("click", open);
        c.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") open(); });
      }
    }
  }

  // reviewer override — the agent decides; export carries original/final/overwritten
  const ovBox = document.createElement("div");
  ovBox.className = "override";
  const auto = screeningLabel(it);
  const cur = ovValue(it);
  ovBox.innerHTML = `<strong>Agent decision</strong>
    <div class="note">Screening result: ${esc(auto)}. Your decision becomes the status and is saved.</div>
    <div class="btns">
      ${["PASS", "NEEDS REVIEW", "FAIL"].map((v) =>
        `<button type="button" data-ov="${v}" aria-pressed="${String(cur === v)}">${v}</button>`).join("")}
    </div>`;
  ovBox.addEventListener("click", (e) => {
    const v = e.target.closest("button")?.dataset.ov;
    if (!v) return;
    if (ovValue(it) === v) {
      it.override = null;                            // click again to retract
    } else {
      const now = new Date();
      const pad = (n) => String(n).padStart(2, "0");
      const stamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ` +
                    `${pad(now.getHours())}:${pad(now.getMinutes())}`;
      it.override = { value: v, at: stamp, original: auto };
    }
    markSessionDirty();
    renderDetail(); renderList();
    persistSession().catch(() => err("Decision kept in this tab — saving to the server failed."));
  });
  container.appendChild(ovBox);
}

function screeningLabel(it) {
  const s = autoState(it);
  return { done_green: "All clear", done_amber: "Needs review", done_red: "Mismatch found",
           error: "Couldn't finish" }[s] || "Not checked";
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
  it.state = "checking"; it.stale = false; it.override = null;
  renderList(); if (sel() === it) renderDetail();
  const t0 = performance.now();
  try {
    const fd = new FormData();
    for (const p of (it.panels || [{ file: it.file }])) fd.append("images", p.file);
    fd.append("application", JSON.stringify(it.app));
    const res = await fetch("/api/verify", { method: "POST", body: fd });
    const body = await res.json();
    if (!res.ok) throw new Error(body.error || "This check didn't finish — retry.");
    it.result = body; it.state = "done"; it.errorMsg = null;
    it.elapsedMs = performance.now() - t0;
    markSessionDirty();
  } catch (e) {
    it.state = "error"; it.errorMsg = e.message;
  }
  renderList(); if (sel() === it) renderDetail();
}

$("verifyAll").addEventListener("click", async () => {
  if (running) return;
  const queue = items.filter((it) => it.state === "waiting" || it.stale || it.state === "error");
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
  renderList();
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
    const byField = Object.fromEntries((it.result?.fields || []).map((f) => [f.field, f.status]));
    rows.push([it.file.name, it.app.beverage_type, it.app.brand_name, it.app.class_type,
               it.app.alcohol_content, it.app.net_contents,
               it.result?.screening_result || "error", orig, final,
               String(Boolean(it.override)),
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
  for (const c of list) {
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `<strong>${esc(c.label)}</strong><span class="shows">${esc(c.shows)}</span>`;
    b.addEventListener("click", async () => {
      err("");
      b.disabled = true;
      try {
        const items0 = await (await fetch(`/api/corpus/${c.id}`)).json();
        $("progress").textContent = `Loading ${items0.length} labels…`;
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
          await addItem(panelFiles, it.application, it.registry || null);
        }
        if (items.length && selectedId === null) select(items[0].id);
        $("progress").textContent = `${c.label} loaded — press "Verify all".`;
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
                      champagne: "Champagne pipeline (imported)" };
let pipePoll = null;

async function refreshCorpora() {
  $("corpora").querySelectorAll("button").forEach((b) => b.remove());
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
  for (const t of ["wine", "beer", "spirits", "imported_wine", "champagne"]) {
    const st = data.pipelines[t];
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
    meta.push({ file_name: it.file.name, state: it.state, override: it.override,
                application: it.app, result: it.result, panels });
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
  await fetch("/api/session", { method: "DELETE" });
  $("progress").textContent = "Saved session cleared.";
  refreshSessionUI();
});

$("restoreBtn").addEventListener("click", async () => {
  err("");
  const btn = $("restoreBtn");
  btn.disabled = true;
  try {
    const s = await (await fetch("/api/session")).json();
    if (!s.saved) { err("No saved session found."); return; }
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
      await addItem(panelFiles, rec.application);
      const it = items[items.length - 1];
      it.result = rec.result;
      it.state = rec.result ? "done" : (rec.state === "error" ? "waiting" : rec.state);
      it.override = rec.override || null;
    }
    if (items.length && selectedId === null) select(items[0].id);
    sessionDirty = false;
    lastSavedAt = s.saved_at || null;
    $("progress").textContent = `Restored ${s.items.length} label(s) from the saved session.`;
    renderList(); renderDetail();
    updateSaveButton();
  } catch {
    err("Couldn't restore the saved session — retry.");
  } finally {
    btn.disabled = false;
    refreshSessionUI();
  }
});

refreshSessionUI();
renderPipelines();
