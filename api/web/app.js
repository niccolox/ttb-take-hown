/* Label Check — M1 client. Evidence-as-coordinates: the browser keeps the image
   and renders crops from bboxes client-side (PLAN.md eng hardening). */
"use strict";

const $ = (id) => document.getElementById(id);
const FIELD_ORDER = ["brand_name", "class_type", "alcohol_content", "net_contents",
                     "internal_consistency", "government_warning", "image"];
const FIELD_LABELS = {
  brand_name: "Brand name", class_type: "Class / type",
  alcohol_content: "Alcohol content", net_contents: "Net contents",
  internal_consistency: "Internal consistency",
  government_warning: "Government Warning", image: "Image",
};
const FAMILY = {   // 5 states in data → 3 visual families (+grey)
  MATCH: ["green", "✓ MATCH"],
  LIKELY_MATCH: ["amber", "≈ LIKELY MATCH"],
  WITHIN_TOLERANCE: ["amber", "≈ WITHIN TOLERANCE"],
  NEEDS_REVIEW: ["amber", "👁 NEEDS REVIEW"],
  MISMATCH: ["red", "✗ MISMATCH"],
  NOT_CHECKED: ["grey", "— NOT CHECKED"],
  NOT_REQUIRED: ["grey", "○ NOT REQUIRED"],
};

let currentImage = null;   // ImageBitmap of the submitted label

async function loadSamples() {
  const res = await fetch("/api/samples");
  const list = await res.json();
  for (const s of list) {
    const b = document.createElement("button");
    b.type = "button";
    b.innerHTML = `<strong>${s.label}</strong><span class="shows">${s.shows}</span>`;
    b.addEventListener("click", async () => {
      const blob = await (await fetch(s.image)).blob();
      setImage(new File([blob], s.id + ".jpg", { type: "image/jpeg" }));
      $("bev").value = s.application.beverage_type || "unspecified";
      $("brand").value = s.application.brand_name || "";
      $("ct").value = s.application.class_type || "";
      $("abv").value = s.application.alcohol_content || "";
      $("net").value = s.application.net_contents || "";
    });
    $("samples").appendChild(b);
  }
}

let selectedFile = null;
async function setImage(file) {
  selectedFile = file;
  currentImage = await createImageBitmap(file);
  const url = URL.createObjectURL(file);
  $("preview").src = url;
  $("preview").style.display = "block";
  $("filebtn").textContent = "Change label image";
}

$("file").addEventListener("change", (e) => {
  if (e.target.files[0]) setImage(e.target.files[0]);
});

function err(msg) {
  const el = $("err");
  el.textContent = msg;
  el.style.display = msg ? "block" : "none";
}

function drawCrop(canvas, bbox, pad = 12) {
  if (!currentImage || !bbox) return false;
  const [x1, y1, x2, y2] = bbox;
  const sx = Math.max(0, x1 - pad), sy = Math.max(0, y1 - pad);
  const sw = Math.min(currentImage.width - sx, x2 - x1 + 2 * pad);
  const sh = Math.min(currentImage.height - sy, y2 - y1 + 2 * pad);
  const scale = 64 / sh;
  canvas.width = Math.max(1, sw * scale);
  canvas.height = 64;
  canvas.getContext("2d").drawImage(currentImage, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  return true;
}

function zoomCrop(bbox) {
  const c = $("zoomc");
  const maxW = Math.min(window.innerWidth * 0.85, currentImage.width);
  const scale = maxW / currentImage.width;
  c.width = currentImage.width * scale;
  c.height = currentImage.height * scale;
  const ctx = c.getContext("2d");
  ctx.drawImage(currentImage, 0, 0, c.width, c.height);
  if (bbox) {
    ctx.strokeStyle = "#b3261e"; ctx.lineWidth = 3;
    ctx.strokeRect(bbox[0] * scale, bbox[1] * scale,
                   (bbox[2] - bbox[0]) * scale, (bbox[3] - bbox[1]) * scale);
  }
  $("zoom").showModal();
}

function bannerFor(fields) {
  const by = (s) => fields.filter((f) => f.status === s).map((f) => FIELD_LABELS[f.field] || f.field);
  const mis = by("MISMATCH"), rev = by("NEEDS_REVIEW"),
        amber = [...by("WITHIN_TOLERANCE"), ...by("LIKELY_MATCH")];
  if (mis.length) return ["red", `${mis.length} field${mis.length > 1 ? "s don't" : " doesn't"} match the application — see ${mis.join(", ")} below${rev.length ? `; ${rev.length} more need${rev.length > 1 ? "" : "s"} your eyes` : ""}`];
  if (rev.length) return ["amber", `${rev.length} field${rev.length > 1 ? "s" : ""} need your eyes — see ${rev.join(", ")} below`];
  if (amber.length) return ["amber", `Everything matches, ${amber.length} small difference${amber.length > 1 ? "s" : ""} to confirm`];
  return ["green", "All checks matched — ready for agent sign-off"];
}

function render(result) {
  $("empty").style.display = "none";
  const [cls, text] = bannerFor(result.fields);
  const banner = $("banner");
  banner.className = "banner " + cls;
  banner.textContent = text;

  const rows = $("rows");
  rows.innerHTML = "";
  const sorted = [...result.fields].sort((a, b) =>
    FIELD_ORDER.indexOf(a.field) - FIELD_ORDER.indexOf(b.field));
  for (const f of sorted) {
    const [fam, chipText] = FAMILY[f.status] || ["grey", f.status];
    const row = document.createElement("div");
    row.className = "row";
    const vals = f.application_value || f.label_value ? `
      <div class="vals">
        ${f.label_value ? `<div><span class="lbl">Label says:</span> ${escapeHtml(f.label_value)}</div>` : ""}
        ${f.application_value ? `<div><span class="lbl">Application says:</span> ${escapeHtml(f.application_value)}</div>` : ""}
      </div>` : "";
    row.innerHTML = `
      <div class="fname">${FIELD_LABELS[f.field] || f.field}</div>
      <div><span class="chip ${fam}">${chipText}</span></div>
      <div>${vals}<div class="note">${escapeHtml(f.note || "")}</div>
        ${f.citation ? `<div class="cite">${escapeHtml(f.citation)}</div>` : ""}
        ${(f.sub_results || []).map((s) => `<div class="sub"><strong>${s.check.replace("_", " ")}:</strong> ${s.outcome.toUpperCase()} — ${escapeHtml(s.detail)}</div>`).join("")}
      </div>
      <div class="cropcell"></div>`;
    rows.appendChild(row);
    if (f.evidence && f.evidence.bbox && currentImage) {
      const c = document.createElement("canvas");
      c.className = "crop";
      c.title = "Click to enlarge — region outlined on the full label";
      c.setAttribute("role", "button");
      c.tabIndex = 0;
      if (drawCrop(c, f.evidence.bbox)) {
        row.querySelector(".cropcell").appendChild(c);
        const open = () => zoomCrop(f.evidence.bbox);
        c.addEventListener("click", open);
        c.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") open(); });
      }
    }
  }
  $("again").style.display = "block";
}

function escapeHtml(s) {   // OCR text is attacker-controlled — text nodes only (S1)
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const STAGES = ["Reading the label…", "Checking fields…", "Almost done"];
$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  err("");
  if (!selectedFile) { err("Choose a label image (or a sample) first."); return; }
  const anyField = ["brand", "ct", "abv", "net"].some((id) => $(id).value.trim());
  if (!anyField) { err("Enter at least one field to check — the Government Warning is always checked."); return; }

  const go = $("go");
  go.disabled = true;
  const t0 = performance.now();
  let stageIdx = 0;
  $("stage").style.display = "block";
  const tick = setInterval(() => {
    const dt = ((performance.now() - t0) / 1000).toFixed(0);
    $("stage").textContent = `${STAGES[Math.min(stageIdx++, 2)]} (${dt}s)`;
  }, 900);
  $("stage").textContent = STAGES[0];

  try {
    const fd = new FormData();
    fd.append("image", selectedFile);
    fd.append("application", JSON.stringify({
      beverage_type: $("bev").value,
      brand_name: $("brand").value.trim(),
      class_type: $("ct").value.trim(),
      alcohol_content: $("abv").value.trim(),
      net_contents: $("net").value.trim(),
    }));
    const res = await fetch("/api/verify", { method: "POST", body: fd });
    const body = await res.json();
    if (!res.ok) { err(body.error || "This check didn't finish — retry."); return; }
    render(body);
    $("stage").textContent = `Done in ${((performance.now() - t0) / 1000).toFixed(1)}s`;
  } catch {
    err("This check didn't finish — retry.");
  } finally {
    clearInterval(tick);
    go.disabled = false;
  }
});

$("again").addEventListener("click", () => {   // keeps form values, clears image (daily loop)
  selectedFile = null; currentImage = null;
  $("preview").style.display = "none";
  $("filebtn").textContent = "Choose label image (PNG/JPG)";
  $("banner").className = "banner"; $("rows").innerHTML = "";
  $("empty").style.display = "block"; $("again").style.display = "none";
  $("stage").style.display = "none";
  window.scrollTo({ top: 0, behavior: "smooth" });
});

loadSamples();
