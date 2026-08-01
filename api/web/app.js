/* Label Check — M3 batch client (master-detail).
   Single-label mode is the same structure with a one-item list auto-selected.
   Rows never reorder; results stream in place; per-row retry; reviewer
   override with audited export (original/final/overwritten). */
"use strict";

const $ = (id) => document.getElementById(id);
const CONCURRENCY = 3;
const FIELD_ORDER = ["brand_name", "class_type", "alcohol_content", "net_contents",
                     "internal_consistency", "government_warning", "image"];
const FIELD_LABELS = {
  brand_name: "Brand name", class_type: "Class / type",
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
async function addItem(panelFiles, app = {}) {
  const f = panelFiles[0].file;
  const id = `${f.name}-${items.length}-${Date.now() % 1e6}`;
  const panels = [];
  for (const p of panelFiles) {
    panels.push({ file: p.file, panel: p.panel || "front",
                  bitmap: await createImageBitmap(p.file).catch(() => null) });
  }
  items.push({ id, file: f, bitmap: panels[0].bitmap, panels,
               app: { beverage_type: "unspecified", brand_name: "", class_type: "",
                      alcohol_content: "", net_contents: "", ...app },
               state: "waiting", result: null, override: null, stale: false });
}

$("files").addEventListener("change", (e) => { err(""); addFiles([...e.target.files]); e.target.value = ""; });

$("tpl").addEventListener("click", () => {
  const csv = "filename,beverage_type,brand_name,class_type,alcohol_content,net_contents\r\n" +
              "mylabel.jpg,distilled_spirits,OLD TOM DISTILLERY,Kentucky Straight Bourbon Whiskey,45% Alc./Vol.,750 mL\r\n";
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
  let applied = 0, unmatched = [], badBev = 0;
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
    if (item) { Object.assign(item.app, rec); markStale(item); applied++; }
    else unmatched.push(fname);
  }
  const msgs = [`Manifest applied to ${applied} label(s).`];
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
function itemState(it) {
  if (it.state !== "done") return it.state;
  const st = it.result.fields.map((f) => f.status);
  if (st.includes("MISMATCH")) return "done_red";
  if (st.some((s) => ["NEEDS_REVIEW", "WITHIN_TOLERANCE", "LIKELY_MATCH"].includes(s))) return "done_amber";
  return "done_green";
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
    b.innerHTML = `<span class="fn">${esc(it.file.name)}</span>
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
    <label>Alcohol content</label><input type="text" data-k="alcohol_content" value="${esc(it.app.alcohol_content)}" placeholder="e.g. 45% Alc./Vol.">
    <label>Net contents</label><input type="text" data-k="net_contents" value="${esc(it.app.net_contents)}" placeholder="e.g. 750 mL">
    <p class="note">The Government Warning is always checked — no entry needed.</p>`;
  form.addEventListener("change", (e) => {
    const k = e.target.dataset.k;
    if (k) { it.app[k] = e.target.value.trim(); markStale(it); renderList();
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
  const [cls, text] = bannerFor(r.fields);
  const banner = document.createElement("div");
  banner.className = "banner " + cls; banner.textContent = text;
  container.appendChild(banner);

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
      if (drawCrop(c, evBitmap, f.evidence.bbox)) {
        row.querySelector(".cropcell").appendChild(c);
        const open = () => zoomCrop(evBitmap, f.evidence.bbox);
        c.addEventListener("click", open);
        c.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") open(); });
      }
    }
  }

  // reviewer override — the agent decides; export carries original/final/overwritten
  const ov = document.createElement("div");
  ov.className = "override";
  const auto = screeningLabel(it);
  ov.innerHTML = `<strong>Agent decision</strong>
    <div class="note">Screening result: ${esc(auto)}. Override if your judgment differs.</div>
    <div class="btns">
      ${["PASS", "NEEDS REVIEW", "FAIL"].map((v) =>
        `<button type="button" data-ov="${v}" aria-pressed="${String(it.override === v)}">${v}</button>`).join("")}
    </div>
    ${it.override ? `<p class="ov-note">Overwritten: ${esc(auto)} → ${esc(it.override)}</p>` : ""}`;
  ov.addEventListener("click", (e) => {
    const v = e.target.closest("button")?.dataset.ov;
    if (v) { it.override = it.override === v ? null : v; renderDetail(); renderList(); }
  });
  container.appendChild(ov);
}

function screeningLabel(it) {
  const s = itemState(it);
  return { done_green: "All clear", done_amber: "Needs review", done_red: "Mismatch found",
           error: "Couldn't finish" }[s] || "Not checked";
}

// ── crops ────────────────────────────────────────────────────────────────────
function drawCrop(canvas, bitmap, bbox, pad = 12) {
  const [x1, y1, x2, y2] = bbox;
  const sx = Math.max(0, x1 - pad), sy = Math.max(0, y1 - pad);
  const sw = Math.min(bitmap.width - sx, x2 - x1 + 2 * pad);
  const sh = Math.min(bitmap.height - sy, y2 - y1 + 2 * pad);
  if (sw <= 0 || sh <= 0) return false;
  const scale = 56 / sh;
  canvas.width = Math.max(1, sw * scale); canvas.height = 56;
  canvas.getContext("2d").drawImage(bitmap, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  return true;
}

function zoomCrop(bitmap, bbox) {
  const c = $("zoomc");
  const maxW = Math.min(window.innerWidth * 0.85, bitmap.width);
  const scale = maxW / bitmap.width;
  c.width = bitmap.width * scale; c.height = bitmap.height * scale;
  const ctx = c.getContext("2d");
  ctx.drawImage(bitmap, 0, 0, c.width, c.height);
  ctx.strokeStyle = "#b3261e"; ctx.lineWidth = 3;
  ctx.strokeRect(bbox[0] * scale, bbox[1] * scale,
                 (bbox[2] - bbox[0]) * scale, (bbox[3] - bbox[1]) * scale);
  $("zoom").showModal();
}

// ── verification runs (fan-out, per-item independence, cancel-waiting) ───────
async function runOne(it) {
  const anyField = ["brand_name", "class_type", "alcohol_content", "net_contents"]
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
                "original_result", "final_result", "overwritten",
                ...FIELD_ORDER.slice(0, 6).map((f) => `field_${f}`)];
  const rows = [head.map(csvCell).join(",")];
  for (const it of items) {
    if (!it.result && it.state !== "error") continue;
    const orig = screeningLabel(it);
    const final = it.override || orig;
    const byField = Object.fromEntries((it.result?.fields || []).map((f) => [f.field, f.status]));
    rows.push([it.file.name, it.app.beverage_type, it.app.brand_name, it.app.class_type,
               it.app.alcohol_content, it.app.net_contents,
               it.result?.screening_result || "error", orig, final,
               String(Boolean(it.override)),
               ...FIELD_ORDER.slice(0, 6).map((f) => byField[f] || "")]
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
          await addItem(panelFiles, it.application);
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
renderPipelines();
