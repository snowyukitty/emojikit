const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = { session: null, presets: [], active: null, bg: "light",
                parts: [], offset: [0, 0] };
const PART_COLOR = { tail: "#ff5b6e", ear: "#4ba0ff", arm: "#42c878", leg: "#ffaa3c" };
const ROLE_EMO = { tail: "🌀", ear: "👂", arm: "💪", leg: "🦵" };

/* ---------- helpers ---------- */
function loader(on, text = "Working…") {
  $("#loaderText").textContent = text;
  $("#overlayLoader").hidden = !on;
}
let toastT;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => (t.hidden = true), 2600);
}

/* ---------- presets ---------- */
async function loadPresets() {
  state.presets = await (await fetch("/api/presets")).json();
  const grid = $("#presetGrid");
  grid.innerHTML = "";
  for (const p of state.presets) {
    const el = document.createElement("button");
    el.className = "preset";
    el.dataset.name = p.name; el.dataset.accent = p.accent;
    el.innerHTML = `<span class="emo">${p.emoji}</span>
      <span><span class="nm">${p.name}</span><span class="desc">${p.desc}</span></span>`;
    el.onclick = () => choosePreset(p.name);
    grid.appendChild(el);
  }
}

function choosePreset(name) {
  if (!state.session) { toast("Drop an image first 🐾"); return; }
  state.active = name;
  $$(".preset").forEach((el) => {
    const on = el.dataset.name === name;
    el.classList.toggle("active", on);
    el.style.background = on ? `linear-gradient(135deg, ${el.dataset.accent}, #9b6bff)` : "";
    el.style.color = on ? "#fff" : "";
  });
  animate(name);
}

/* ---------- upload ---------- */
async function uploadFile(file) {
  if (!file) return;
  loader(true, "Removing background & auto-rigging…");
  try {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    if (!r.ok) throw new Error("upload failed");
    const data = await r.json();
    state.session = data.session;
    state.offset = data.offset;
    state.parts = data.parts.map((p) => ({ ...p, enabled: true }));
    showSource(data);
    toast("Rig detected — pick an emote ✨");
  } catch (e) { toast("Upload failed 😢"); }
  finally { loader(false); }
}

function showSource(d) {
  $(".dz-empty").hidden = true;
  $(".dz-stage").hidden = false;
  $("#imgOverlay").src = d.overlay + "?t=" + Date.now();
  $("#imgMaster").src = d.master + "?t=" + Date.now();
  const chips = $("#partChips"); chips.innerHTML = "";
  const counts = {};
  d.parts.forEach((p) => (counts[p.role] = (counts[p.role] || 0) + 1));
  Object.entries(counts).forEach(([role, n]) => {
    const t = document.createElement("span"); t.className = "tag";
    t.innerHTML = `${ROLE_EMO[role] || "•"} ${n} ${role}${n > 1 ? "s" : ""}`;
    chips.appendChild(t);
  });
  if (d.eyes.length) {
    const t = document.createElement("span"); t.className = "tag eye";
    t.innerHTML = `👁 ${d.eyes.length} eyes`; chips.appendChild(t);
  }
  $("#rigInfo").hidden = false;
  const img = $("#imgOverlay");
  if (img.complete) renderHandles(); else img.onload = renderHandles;
}

/* ---------- editable rig handles ---------- */
function visibleImg() {
  return $("#imgMaster").hidden ? $("#imgOverlay") : $("#imgMaster");
}
function contentBox(img) {
  const r = img.getBoundingClientRect();
  const nar = img.naturalWidth / img.naturalHeight, bar = r.width / r.height;
  let cw, ch;
  if (nar > bar) { cw = r.width; ch = cw / nar; } else { ch = r.height; cw = ch * nar; }
  return { r, ox: (r.width - cw) / 2, oy: (r.height - ch) / 2, scale: cw / img.naturalWidth };
}
function renderHandles() {
  const wrap = $("#handles"); wrap.innerHTML = "";
  const img = visibleImg(); if (!img.naturalWidth) return;
  const cont = $("#stageImg").getBoundingClientRect();
  const b = contentBox(img);
  const baseX = b.r.left - cont.left + b.ox, baseY = b.r.top - cont.top + b.oy;
  state.parts.filter((p) => p.enabled).forEach((p) => {
    const ix = p.pivot[0] - state.offset[0], iy = p.pivot[1] - state.offset[1];
    const h = document.createElement("div");
    h.className = "handle"; h.style.left = baseX + ix * b.scale + "px"; h.style.top = baseY + iy * b.scale + "px";
    h.style.borderColor = PART_COLOR[p.role] || "#9b6bff";
    h.innerHTML = `<span class="lbl">${p.role}</span><span class="x">✕</span>`;
    h.querySelector(".x").onclick = (e) => { e.stopPropagation(); p.enabled = false; renderHandles(); };
    h.addEventListener("pointerdown", (e) => startDrag(e, p, h));
    wrap.appendChild(h);
  });
}
function startDrag(e, part, h) {
  if (e.target.classList.contains("x")) return;
  e.preventDefault();
  const img = visibleImg(), b = contentBox(img);
  const move = (ev) => {
    let ix = (ev.clientX - b.r.left - b.ox) / b.scale;
    let iy = (ev.clientY - b.r.top - b.oy) / b.scale;
    ix = Math.max(0, Math.min(img.naturalWidth, ix));
    iy = Math.max(0, Math.min(img.naturalHeight, iy));
    part.pivot = [Math.round(ix + state.offset[0]), Math.round(iy + state.offset[1])];
    const cont = $("#stageImg").getBoundingClientRect();
    h.style.left = (b.r.left - cont.left + b.ox + ix * b.scale) + "px";
    h.style.top = (b.r.top - cont.top + b.oy + iy * b.scale) + "px";
  };
  const up = () => { document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", up); };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", up);
}
async function saveRig() {
  if (!state.session) return;
  loader(true, "Applying rig edits…");
  try {
    await fetch("/api/rig", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: state.session,
        parts: state.parts.map((p) => ({ name: p.name, pivot: p.pivot, enabled: p.enabled })) }),
    });
    toast("Rig updated ✏️");
    if (state.active) await animate(state.active);
  } catch (e) { toast("Save failed 😢"); }
  finally { loader(false); }
}

/* ---------- animate + preview ---------- */
async function animate(preset) {
  loader(true, `Animating “${preset}” across all sizes…`);
  try {
    const r = await fetch("/api/animate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: state.session, preset }),
    });
    if (!r.ok) throw new Error();
    renderPreview(await r.json());
  } catch (e) { toast("Animation failed 😢"); }
  finally { loader(false); }
}

function urlFor(out, platform, size) {
  const o = out.find((x) => x.platform === platform && x.size === size);
  return o ? o.url + "?t=" + Date.now() : null;
}

function renderPreview(res) {
  $("#previewPlaceholder").hidden = true;
  $("#previewStage").hidden = false;
  $("#exportBlock").hidden = false;

  const out = res.outputs;
  $("#heroGif").src = urlFor(out, "slack", 128);

  // size swatches: 128 (slack), 112/56/28 (twitch)
  const want = [["slack", 128], ["twitch", 112], ["twitch", 56], ["twitch", 28]];
  const strip = $("#sizeStrip"); strip.innerHTML = "";
  for (const [plat, size] of want) {
    const u = urlFor(out, plat, size); if (!u) continue;
    const sw = document.createElement("div");
    sw.className = "swatch" + (state.bg === "dark" ? " dark" : "");
    sw.innerHTML = `<div class="tile" style="width:${size + 16}px;height:${size + 16}px">
        <img src="${u}" width="${size}" height="${size}"/></div>
        <div class="lbl">${size}px</div>`;
    strip.appendChild(sw);
  }

  // platform export cards
  const byPlat = {};
  out.forEach((o) => (byPlat[o.platform] = byPlat[o.platform] || []).push(o));
  const meta = { slack: "💬", discord: "🎮", twitch: "🟣" };
  const wrap = $("#platforms"); wrap.innerHTML = "";
  for (const [plat, items] of Object.entries(byPlat)) {
    const card = document.createElement("div"); card.className = "plat";
    let rows = "";
    for (const o of items) {
      const kb = (o.bytes / 1024).toFixed(0), bud = (o.budget / 1024).toFixed(0);
      rows += `<div class="row"><span>${o.size}px</span>
        <span class="badge ${o.fit ? "ok" : "over"}">${kb}KB / ${bud}KB</span>
        <a class="dl" href="${o.url}" download>↓</a></div>`;
    }
    card.innerHTML = `<h3>${meta[plat] || "•"} ${plat}</h3>${rows}`;
    wrap.appendChild(card);
  }
  const dl = $("#dlPreset");
  dl.href = `/api/zip?session=${state.session}&preset=${res.preset}`;
  dl.setAttribute("download", "");
  applyBg();
}

async function exportPack() {
  if (!state.session) { toast("Drop an image first 🐾"); return; }
  loader(true, "Rendering all emotes & zipping… (~1 min)");
  try {
    const r = await fetch("/api/pack", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: state.session }),
    });
    const d = await r.json();
    const a = document.createElement("a"); a.href = d.url; a.download = ""; a.click();
    toast(`Pack ready · ${d.count} emotes 📦`);
  } catch (e) { toast("Pack failed 😢"); }
  finally { loader(false); }
}

function applyBg() {
  $("#heroStage").classList.toggle("dark", state.bg === "dark");
  $$(".swatch").forEach((s) => s.classList.toggle("dark", state.bg === "dark"));
}

/* ---------- wire up ---------- */
function init() {
  loadPresets();

  const dz = $("#dropzone"), fi = $("#file");
  $("#browse").onclick = (e) => { e.stopPropagation(); fi.click(); };
  dz.onclick = (e) => { if (!$(".dz-stage").hidden) return; fi.click(); };
  fi.onchange = () => uploadFile(fi.files[0]);
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => uploadFile(e.dataTransfer.files[0]));

  $$(".stage-toggle button").forEach((b) => b.onclick = (e) => {
    e.stopPropagation();
    $$(".stage-toggle button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    const ov = b.dataset.view === "overlay";
    $("#imgOverlay").hidden = !ov; $("#imgMaster").hidden = ov;
    renderHandles();
  });

  $("#saveRig").onclick = saveRig;
  $("#dlPack").onclick = exportPack;
  window.addEventListener("resize", () => { if (state.parts.length) renderHandles(); });

  $$("#bgToggle button").forEach((b) => b.onclick = () => {
    $$("#bgToggle button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active"); state.bg = b.dataset.bg; applyBg();
  });
}
init();
