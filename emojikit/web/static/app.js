const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = {
  session: null, presets: [], active: null, bg: "light",
  parts: [], offset: [0, 0],
  cat: "All", query: "",
  player: { frames: [], idx: 0, playing: true, rate: 1, fps: 20, raf: null, last: 0, acc: 0 },
};
const PART_COLOR = { tail: "#ff5b6e", ear: "#4ba0ff", arm: "#42c878", leg: "#ffaa3c" };
const ROLE_EMO = { tail: "🌀", ear: "👂", arm: "💪", leg: "🦵" };
const CAT_ORDER = ["All", "Positive", "Hype", "Reaction", "Mood"];

/* ---------- toast ---------- */
let toastT;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastT); toastT = setTimeout(() => (t.hidden = true), 2600);
}

/* ---------- staged progress ----------
   Backend calls are single blocking requests, so true mid-call progress isn't
   available. We advance a bar through estimated stages while the fetch is in
   flight, then snap to 100% on completion. */
function progressCtl(bar, label, container) {
  let timer;
  const resetBar = () => {
    bar.style.transition = "none"; bar.style.width = "0%";
    void bar.offsetWidth; bar.style.transition = "";
  };
  return {
    start(stages) {
      container.hidden = false; resetBar();
      let i = 0;
      const step = () => {
        if (i >= stages.length) return;
        const s = stages[i++];
        if (label) label.textContent = s.label;
        bar.style.width = (s.to * 100) + "%";
        timer = setTimeout(step, s.ms);
      };
      step();
    },
    done(text) { clearTimeout(timer); bar.style.width = "100%"; if (text && label) label.textContent = text; },
    hide(delay = 350) { clearTimeout(timer); setTimeout(() => { container.hidden = true; resetBar(); }, delay); },
  };
}
let srcProg, loadProg;

/* ---------- theme ---------- */
function applyTheme(pref) {
  localStorage.setItem("ek-theme", pref);
  document.documentElement.dataset.themePref = pref;
  const sys = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.dataset.theme = pref === "auto" ? sys : pref;
  $$("#themeSwitch button").forEach((b) => b.classList.toggle("active", b.dataset.themeVal === pref));
}

/* ---------- presets: load + filter ---------- */
async function loadPresets() {
  state.presets = await (await fetch("/api/presets")).json();
  renderCatChips();
  renderPresetGrid();
}

function renderCatChips() {
  const have = new Set(state.presets.map((p) => p.category));
  const cats = CAT_ORDER.filter((c) => c === "All" || have.has(c));
  const wrap = $("#catChips"); wrap.innerHTML = "";
  for (const c of cats) {
    const b = document.createElement("button");
    b.className = "cat-chip" + (c === state.cat ? " active" : "");
    b.textContent = c;
    b.onclick = () => { state.cat = c; renderCatChips(); renderPresetGrid(); };
    wrap.appendChild(b);
  }
}

function renderPresetGrid() {
  const q = state.query.trim().toLowerCase();
  const list = state.presets.filter((p) => {
    const catOk = state.cat === "All" || p.category === state.cat;
    const qOk = !q || p.name.toLowerCase().includes(q) || p.desc.toLowerCase().includes(q);
    return catOk && qOk;
  });
  const grid = $("#presetGrid"); grid.innerHTML = "";
  for (const p of list) {
    const el = document.createElement("button");
    el.className = "preset" + (p.name === state.active ? " active" : "");
    el.dataset.name = p.name;
    el.innerHTML = `<span class="emo">${p.emoji}</span>
      <span class="meta"><span class="nm">${p.name}</span><span class="desc">${p.desc}</span></span>`;
    el.onclick = () => choosePreset(p.name);
    grid.appendChild(el);
  }
  $("#presetEmpty").hidden = list.length > 0;
  $("#presetCount").textContent = `${list.length} of ${state.presets.length} emotes`;
}

function choosePreset(name) {
  if (!state.session) { toast("Drop an image first 🐾"); return; }
  state.active = name;
  $$(".preset").forEach((el) => el.classList.toggle("active", el.dataset.name === name));
  animate(name);
}

/* ---------- upload ---------- */
async function uploadFile(file) {
  if (!file) return;
  srcProg.start([
    { to: 0.3, label: "Removing background…", ms: 900 },
    { to: 0.62, label: "Detecting parts…", ms: 1100 },
    { to: 0.85, label: "Building rig…", ms: 1500 },
  ]);
  try {
    const fd = new FormData(); fd.append("file", file);
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    if (!r.ok) throw new Error("upload failed");
    const data = await r.json();
    state.session = data.session;
    state.offset = data.offset;
    state.parts = data.parts.map((p) => ({ ...p, enabled: true }));
    showSource(data);
    srcProg.done("Rig ready ✨"); srcProg.hide(700);
    toast("Rig detected — pick an emote ✨");
  } catch (e) { srcProg.hide(0); toast("Upload failed 😢"); }
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
function visibleImg() { return $("#imgMaster").hidden ? $("#imgOverlay") : $("#imgMaster"); }
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
    h.style.borderColor = PART_COLOR[p.role] || "var(--accent)";
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
  loadProg.start([{ to: 0.7, label: "Applying rig edits…", ms: 700 }]);
  try {
    await fetch("/api/rig", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: state.session,
        parts: state.parts.map((p) => ({ name: p.name, pivot: p.pivot, enabled: p.enabled })) }),
    });
    loadProg.done("Rig updated ✏️");
    toast("Rig updated ✏️");
    if (state.active) { loadProg.hide(0); await animate(state.active); }
    else loadProg.hide(300);
  } catch (e) { loadProg.hide(0); toast("Save failed 😢"); }
}

/* ---------- animate + preview ---------- */
async function animate(preset) {
  loadProg.start([
    { to: 0.4, label: `Rendering “${preset}” frames…`, ms: 700 },
    { to: 0.72, label: "Encoding GIFs…", ms: 900 },
    { to: 0.9, label: "Preparing preview…", ms: 900 },
  ]);
  try {
    const r = await fetch("/api/animate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: state.session, preset }),
    });
    if (!r.ok) throw new Error();
    loadProg.done("Done ✨"); loadProg.hide(250);
    renderPreview(await r.json());
  } catch (e) { loadProg.hide(0); toast("Animation failed 😢"); }
}

function urlFor(out, platform, size) {
  const o = out.find((x) => x.platform === platform && x.size === size);
  return o ? o.url + "?t=" + Date.now() : null;
}

function renderPreview(res) {
  $("#previewPlaceholder").hidden = true;
  $("#previewStage").hidden = false;
  $("#exportBlock").hidden = false;

  setupPlayer(res.frames || [], res.fps || 20);

  // real exported GIFs at native sizes
  const out = res.outputs;
  const want = [["slack", 128], ["twitch", 112], ["twitch", 56], ["twitch", 28]];
  const strip = $("#sizeStrip"); strip.innerHTML = "";
  for (const [plat, size] of want) {
    const u = urlFor(out, plat, size); if (!u) continue;
    const sw = document.createElement("div");
    sw.className = "swatch " + state.bg;
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
        <span class="badge ${o.fit ? "ok" : "over"}">${kb} / ${bud}KB</span>
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

/* ---------- frame player ---------- */
function setupPlayer(frames, fps) {
  const p = state.player;
  p.frames = frames; p.fps = fps; p.idx = 0; p.last = 0; p.acc = 0;
  const has = frames.length > 0;
  $("#player").style.display = has ? "" : "none";
  frames.forEach((u) => { const im = new Image(); im.src = u; });   // warm cache
  const scrub = $("#scrub");
  scrub.max = Math.max(0, frames.length - 1); scrub.value = 0;
  setPlaying(has);
  if (has) paintFrame();
}
function paintFrame() {
  const p = state.player; if (!p.frames.length) return;
  $("#heroGif").src = p.frames[p.idx];
  $("#scrub").value = p.idx;
  $("#frameCount").textContent = `${p.idx + 1} / ${p.frames.length}`;
}
function setPlaying(on) {
  const p = state.player; p.playing = on; p.last = 0;
  $("#playBtn").textContent = on ? "❚❚" : "▶";
}
function playerTick(ts) {
  const p = state.player;
  if (p.playing && p.frames.length) {
    if (!p.last) p.last = ts;
    p.acc += ts - p.last; p.last = ts;
    const frameMs = 1000 / (p.fps * p.rate);
    let moved = false;
    while (p.acc >= frameMs) { p.acc -= frameMs; p.idx = (p.idx + 1) % p.frames.length; moved = true; }
    if (moved) paintFrame();
  }
  requestAnimationFrame(playerTick);
}

async function exportPack() {
  if (!state.session) { toast("Drop an image first 🐾"); return; }
  loadProg.start([
    { to: 0.2, label: "Rendering emotes…", ms: 1500 },
    { to: 0.5, label: "Rendering emotes…", ms: 4500 },
    { to: 0.78, label: "Encoding & sizing…", ms: 6000 },
    { to: 0.92, label: "Zipping pack…", ms: 4000 },
  ]);
  try {
    const r = await fetch("/api/pack", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: state.session }),
    });
    const d = await r.json();
    loadProg.done("Pack ready 📦"); loadProg.hide(400);
    const a = document.createElement("a"); a.href = d.url; a.download = ""; a.click();
    toast(`Pack ready · ${d.count} emotes 📦`);
  } catch (e) { loadProg.hide(0); toast("Pack failed 😢"); }
}

function applyBg() {
  const dark = state.bg === "dark";
  $("#heroStage").classList.toggle("dark", dark);
  $("#heroStage").classList.toggle("light", !dark);
  $$(".swatch").forEach((s) => { s.classList.toggle("dark", dark); s.classList.toggle("light", !dark); });
}

/* ---------- wire up ---------- */
function init() {
  srcProg = progressCtl($("#srcBar"), $("#srcLabel"), $("#srcProgress"));
  loadProg = progressCtl($("#loadBar"), $("#loaderText"), $("#overlayLoader"));

  // theme switch
  $$("#themeSwitch button").forEach((b) => b.onclick = () => applyTheme(b.dataset.themeVal));
  applyTheme(localStorage.getItem("ek-theme") || "auto");
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if ((localStorage.getItem("ek-theme") || "auto") === "auto") applyTheme("auto");
  });

  loadPresets();

  // upload
  const dz = $("#dropzone"), fi = $("#file");
  $("#browse").onclick = (e) => { e.stopPropagation(); fi.click(); };
  $("#replaceBtn").onclick = (e) => { e.stopPropagation(); fi.click(); };
  dz.onclick = (e) => { if (!$(".dz-stage").hidden) return; fi.click(); };
  fi.onchange = () => { uploadFile(fi.files[0]); fi.value = ""; };
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => uploadFile(e.dataTransfer.files[0]));

  // stage toggle (rig / clean)
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

  // search + categories
  const search = $("#presetSearch");
  search.oninput = () => { state.query = search.value; renderPresetGrid(); };
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== search) { e.preventDefault(); search.focus(); }
    if (e.key === "Escape" && document.activeElement === search) { search.value = ""; state.query = ""; renderPresetGrid(); search.blur(); }
  });

  // preview bg toggle
  $$("#bgToggle button").forEach((b) => b.onclick = () => {
    $$("#bgToggle button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active"); state.bg = b.dataset.bg; applyBg();
  });

  // playback controls
  $("#playBtn").onclick = () => setPlaying(!state.player.playing);
  $("#scrub").addEventListener("input", (e) => {
    setPlaying(false);
    state.player.idx = +e.target.value; paintFrame();
  });
  $$("#speed button").forEach((b) => b.onclick = () => {
    $$("#speed button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active"); state.player.rate = +b.dataset.rate; state.player.last = 0;
  });

  requestAnimationFrame(playerTick);
}
init();
