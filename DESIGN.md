# emojikit — Design Document

> A hybrid (human + AI + deterministic-script) toolkit that does two things:
> 1. **Image → Emoji** — turn any picture into a small, clean, instantly-recognizable emoji/sticker.
> 2. **Emoji → Animated GIF emoji** — add motion (party, shake, spin, pulse, …) to a static emoji.
>
> Design philosophy: the *brain* is the human + Claude (deciding subject, style, prompt, effect);
> the *hands* are deterministic Python (crop/stroke/resize/encode/size-budget) plus a generative
> engine (codex / gpt-image) for redraws. Nothing is a fully-automated black box.

---

## 1. Goals & non-goals

**Goals**
- High-quality output. "Recognizable at 32–64 px" is the bar for emoji; "smooth + under platform byte limit" is the bar for GIFs.
- Reproducible: deterministic finishing steps so the same input + params give the same output.
- Multi-platform export in one shot: Slack, Discord, Twitch.
- Pluggable engine for Function 1: `local` (no AI), `codex` (gpt-image-2 + auto bg-removal), `api` (gpt-image-1 native transparent).
- Human/AI-in-the-loop: easy to inspect intermediate steps and re-run a single stage.

**Non-goals (for now)**
- Emoji *mosaic* (compose a big picture out of tiny emojis) — explicitly NOT what we want.
- A hosted web service / multi-user app. This is a personal local tool.
- Training our own models.

---

## 2. Platform output matrix

| Platform | Type | Sizes (px) | Format | Byte budget | Frames / fps |
|---|---|---|---|---|---|
| Slack | static | 128 | PNG (transparent) | < 128 KB | — |
| Slack | animated | 128 | GIF (transparent) | < 128 KB | 12–24 / ~20 fps |
| Discord | static | 128 | PNG (transparent) | < 256 KB | — |
| Discord | animated | 128 | GIF (transparent) | < 256 KB | 12–24 / ~20 fps |
| Twitch | static | 28, 56, 112 (all required) | PNG (transparent) | < 1 MB (manual < 512 KB ea.) | — |
| Twitch | animated | 28, 56, 112 (all required) | GIF (transparent) | < 1 MB (manual < 512 KB ea.) | ≤ 60, sweet spot 12–24 / 20 fps |

We always keep a **512 px master PNG** (transparent) and a **WebP** animated variant (true alpha, better quality) alongside the platform GIFs, even though no platform requires them — they're the high-quality archive copy.

> Note on GIF transparency: GIF only supports **1-bit alpha** (a pixel is either fully opaque or fully transparent), so soft/anti-aliased edges get jagged. We mitigate with edge matting against a neutral mid-gray and a dither-aware palette. WebP/APNG keep full alpha for the archive copy.

---

## 3. Architecture

Layered so the *core* is reusable by CLI, by Claude, by codex, and (phase 2) by a local web UI.

```
emojikit/
  core/
    profiles.py    # platform specs (sizes, byte budgets, fps) — single source of truth
    io_utils.py    # load/save, RGBA normalization, padding to square, smart-crop
    enhance.py     # legibility boosters: saturation, contrast, contour/stroke, sharpen
    segment.py     # background removal (rembg | imagemagick | passthrough)
    effects.py     # per-frame transforms for animation (the effect library)
    encode.py      # GIF (ffmpeg palettegen) + WebP encode + size-budget optimizer
    emojify.py     # Function 1 pipeline (local engine)
    animate.py     # Function 2 pipeline
  engines/
    codex.py       # invoke codex CLI -> gpt-image-2, then hand off to segment.py
    openai_api.py  # gpt-image-1 native transparent (optional, needs API key)
  cli.py           # `python -m emojikit ...`  (typer)
  web/             # phase 2: FastAPI app + static frontend (calls core)
```

### Data contract
Everything in the pipeline is an **RGBA `PIL.Image` at the working resolution (512 px)**. Only the final
`encode` stage downsamples to each platform size with Lanczos. This keeps quality high (process big, shrink last).

---

## 4. Function 1 — Image → Emoji

The hard problem: detail vanishes at 32–64 px. The fix is "redraw or simplify into bold shapes + a clean
outline, then shrink last."

### Pipeline (local engine)
1. **Load & normalize** → RGBA, fix EXIF orientation.
2. **Segment** (background removal) → subject on transparent bg. Engine: `rembg` (U²-Net, best) → fallback ImageMagick → fallback none.
3. **Smart square crop** → bounding box of the alpha, pad to square with a small margin (default 8%).
4. **Legibility enhancement** (the part that makes it "pop" at small size):
   - saturation +15–25%, local contrast (CLAHE-ish) boost,
   - **contour stroke**: a clean outline around the subject (configurable color/width) — the single biggest win for small-size readability,
   - optional posterize / edge-aware simplify for very busy sources,
   - mild unsharp mask **after** downscale.
5. **Master render** at 512 px, then **multi-size export** (see matrix) with Lanczos + post-sharpen.

### Generative engines (for photographic / busy sources)
- `codex`: Claude writes a tailored prompt → `codex` runs **gpt-image-2** → opaque result → our `segment.py`
  removes the background → continue from step 3. (No API key needed if codex is logged in.)
- `api`: call **gpt-image-1** with `background=transparent`, `quality=high`, `format=png` → already transparent
  → continue from step 3. (Needs `OPENAI_API_KEY`.)

### Prompt template (generative)
> "A single <SUBJECT>, drawn as a clean flat emoji / sticker. Bold simple shapes, thick clean outline,
> high color saturation, centered, no text, **transparent background**, designed to stay clearly
> recognizable when scaled down to 32 px."

Claude fills `<SUBJECT>` after *looking at* the source image — that's the in-the-loop intelligence.

### Why human/AI-in-the-loop here
"What is the *logo/标志* of this image" and "which style reads best small" are judgment calls, not script
logic. Claude inspects the image, picks subject + engine + stroke style; the script does the rest deterministically.

---

## 5. Function 2 — Emoji → Animated GIF emoji

Pattern (proven by ezrgif / partymoji): **base RGBA image → N per-frame transforms → encode GIF/WebP**.

### Effect library (`effects.py`)
Each effect is `f(base_image, t) -> frame` where `t ∈ [0,1)` is the loop phase.

| Effect | Transform |
|---|---|
| `party` / `rainbow` | cyclic hue rotation (HSV) — the classic party-parrot |
| `shake` | sinusoidal x/y jitter |
| `spin` | rotate 0→360° about center |
| `pulse` | scale oscillates 0.85 ↔ 1.0 |
| `bounce` | vertical position via abs(sin) easing |
| `wobble` | sine wave horizontal shear |
| `jello` | non-uniform squash/stretch |
| `slide` | marquee scroll, wraps around |
| `zoom` | ease-in scale 1.0 → 1.3 |
| `sparkle` | overlay animated star/confetti particles |
| `glitch` | per-frame channel shift + scanline noise |

Effects are **composable** (e.g. `party+bounce`). Params (amplitude, frequency, frames, fps) are exposed.

### Encoding (`encode.py`)
- **GIF**: render frames to PNGs → `ffmpeg` `palettegen`/`paletteuse` with `reserve_transparent=1` and
  `dither=bayer` for clean color + 1-bit alpha. Loop forever.
- **WebP**: Pillow `save(..., format=WEBP, lossless/quality, transparency)` — true alpha archive copy.
- **Size-budget optimizer**: if a GIF exceeds the platform byte budget, iteratively reduce
  (palette colors 256→…→32, then frame count, then add lossy `-lossy` via gifsicle if installed) until it fits.
  Always log what was sacrificed (never silently truncate).

---

## 6. Frontend selection (the explicit question)

**Decision: a thin local Web UI (FastAPI backend + static HTML/JS frontend), built in Phase 2.
CLI + core library first.**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **CLI only** | simplest, scriptable, what Claude/codex drive | no visual preview; animated transparent GIF is painful to judge in a terminal | ✅ ship first (it's the engine for everything) |
| **Local web app** (FastAPI + browser) | all image logic stays in Python; browser is the *best* place to preview transparent animated GIF/WebP at 28/56/112/128 side-by-side; drag-drop + param sliders + live re-render; zero packaging; Claude can hit the same REST API | needs a (tiny) server process | ✅ **chosen for the GUI layer** |
| **Electron** | native-app feel | heavy; you'd still need a Python sidecar (all our libs are Python) or rewrite logic in JS; packaging/update pain | ❌ overkill for a personal tool |
| **Tauri** | lighter than Electron | Rust toolchain + still needs a Python sidecar | ❌ same sidecar problem, more setup |

**Rationale.** Every piece of heavy lifting (Pillow, ffmpeg, rembg, codex) is Python-native. Wrapping that
in Electron/Tauri means shipping a Python sidecar anyway — all the desktop-packaging cost for no real benefit
on a single-user local tool. A localhost web app gives the one thing the CLI can't: a live, side-by-side
visual preview of transparent animation at every target size, with sliders to tune params and re-render
instantly. The browser is simply the best preview canvas for this domain. The same FastAPI endpoints are
also callable by Claude/codex, so the GUI and the automation share one core.

UI sketch (phase 2): drag image → choose **Emojify** or **Animate** → (animate: pick effect chips + sliders)
→ live preview grid at 28/56/112/128 on both light & dark backgrounds → per-platform byte-size readout →
"Download all" (zip of platform-specific files).

---

## 7. Engines & dependencies

- **Always present (already on machine):** Python 3.12, ffmpeg 5.0, ImageMagick 7.1, node 22, codex 0.137.
- **Python deps:** `Pillow`, `numpy` (core); `rembg` + `onnxruntime` (local bg-removal, lazy-imported,
  downloads ~170 MB model on first use); `typer` (CLI); `fastapi` + `uvicorn` (phase-2 web).
- **Optional binaries:** `gifsicle` (extra GIF compression; `npm i -g gifsicle` provides a binary). ffmpeg
  covers the baseline so gifsicle is not required.

---

## 8. CLI surface (target)

```bash
# Function 2 (built first — pure local, instant visible result)
python -m emojikit animate input.png --effect party --platform all
python -m emojikit animate input.png --effect "shake+bounce" --fps 20 --frames 18

# Function 1
python -m emojikit emojify photo.jpg --engine local  --stroke white
python -m emojikit emojify photo.jpg --engine codex  --subject "a red fox head"
python -m emojikit emojify photo.jpg --engine api    --quality high

# shared
  --platform slack|discord|twitch|all   --out ./output   --keep-master
```

Output layout: `output/<name>/<platform>/<name>_<size>.<ext>` + `output/<name>/master.png`.

---

## 9. Build phases

1. ✅ **MVP-A:** project skeleton + `profiles` + `effects` (11 effects) + `encode` + `animate` CLI.
   Pure local, ffmpeg/Pillow → GIFs across all platforms, size-budget optimizer. *(Function 2)*
2. ✅ **MVP-B:** `segment` (rembg) + `enhance` (stroke/boost/sharpen) + `focus` crop + `emojify` CLI, `local` engine. *(Function 1 local)*
3. ✅ **MVP-C:** `engines/prompts.py` + `engines/openai_api.py` (gpt-image-1, native transparent) + codex handoff via `--redraw`. *(Generative Function 1)*
4. ⏳ **Phase 2:** FastAPI web UI with live multi-size preview.

Verified end-to-end: photo → `emojify --focus top` (rembg cut + stroke) → `animate --effect bounce`
→ 97.5KB Slack GIF (under budget). All 11 effects smoke-tested; all platform exports within byte limits.

---

## 10.5 Animated emotes — the puppet engine & how to generalize it

Whole-image transforms (scale/shake/spin a still) are NOT real animation. A real emote
needs the character's **parts to move** and its **expression to change** — like hand-made
Twitch/LINE emotes. We do this with a **2D puppet engine** (`emojikit/puppet/`). The
example (`hugcats`) is hand-rigged; below is how the four stages generalize to any image.

### Stage 1 — Segmentation (accuracy): "what are the parts?"
- **SAM-assisted, human/AI-in-the-loop (primary):** Claude looks at the image and point-prompts
  SAM for each *semantic* part (head, body, arm L/R, tail, ear, eyes, mouth). SAM returns precise
  masks. Accurate + general; the semantic understanding comes from the brain, the pixels from SAM.
- **Auto-assist heuristics (reduce clicks):** medial-axis / skeleton of the silhouette → thin
  protrusions = appendages (tail/limbs) and their *attachment joint* = the narrowest neck where the
  protrusion meets the main mass (auto-proposes pivots). Face/landmark heuristics inside the head
  mask locate eyes/mouth for expression anchors.
- Output: labelled part masks + proposed pivots + z-order → a **rig JSON** (editable, reproducible).

### Stage 2 — Rigging (accuracy): "how do parts connect & move?"
- Pivot = joint = narrowest cut between part and parent (auto from mask, refined by Claude).
- z-order from occlusion analysis.
- Each part gets a **role** (head/arm/tail/ear/body/eye/mouth) — roles drive motion presets.
- **Seam-free deformation is essential** (this is what fixed the tail tearing):
  - appendages → **`bend`** (rotation grows with distance from the pivot, so the root stays glued
    to the body — no tear), NOT rigid rotation;
  - body → **anchored squash** (feet planted);
  - rigid parts → rotate-about-joint with a joint cover; organic → mesh warp.

### Stage 3 — Motion (artistry): "what animation?"
- A **role-keyed preset library**, hand-crafted to look good and reusable across characters:
  idle/breathe, hug-squeeze, bounce, nod, head-shake, wave, jump, wiggle, tail-swish, ear-twitch,
  peek, dance… A preset = `{role → curve(amplitude, freq, phase, easing)}`; applying it to any rig
  matches roles → parts, so "squeeze + tail-swish + sway" works on any rigged character.
- Loop-correctness enforced (integer cycles per loop). Secondary motion (follow-through swish,
  squash overshoot) added automatically.

### Stage 4 — Expression & FX (artistry): "emotion?"
- Procedural, anchored to face landmarks: blink, heart-eyes, wink, blush, tears, sweat-drop,
  anger-vein, sparkle-eyes. Floating FX (character-agnostic): hearts, sparkles, stars, ! / ?,
  music notes, zzz, confetti.

### The brain = you + me loop
Claude drives segmentation (semantic clicks), picks preset + FX, tunes pivots/coords by reading a
grid overlay of the image, and judges quality by viewing renders. The engine does the deterministic
bend/squash/composite/encode. The rig JSON keeps it reproducible and re-editable.

### Generalization roadmap
- **v1 (done):** hand-authored rig (hugcats) — `bend` tails (seam-free), anchored squeeze, body
  sway+bob, blink, heart-eyes, blush, floating hearts + sparkles → transparent looping GIF/WebP.
- **v2:** SAM-assisted segmentation → semi-auto **rig JSON** (click parts, auto pivots).
- **v3 (done):** role-based **motion preset library** (`presets.py`, 12 emotes) + **FX library**
  (`overlays.py`: hearts/stars/notes/!/?/zzz/tears/anger/sweat/confetti). One rig → many emotes via
  `emojikit emote <rig.json> --preset <name>`.
- **v4 (done):** **character-agnostic** auto-rig (`autodetect.py`) — morphological-opening core +
  appendage/joint geometry (no human-face assumptions; works on animals/cartoons), role inference from
  appendage direction, dark-symmetric-blob eye detection (degrades gracefully). One-shot:
  `emojikit auto <image> --preset <name>`. Verified on hug-cats AND a fox face.
- **v5 (done):** local web UI (`emojikit/web/`, FastAPI + glassmorphic frontend) — drag image →
  auto-rig (visualized: parts coloured, pivots, eyes) → pick from 12 emote presets → live preview at
  128/112/56/28 on light/dark → per-platform export with byte readouts + download. Launch:
  `emojikit serve`. (Render ~3s + encode ~3s per emote after bbox-bend + fast-webp optimizations.)
- **v6 (done):** studio UI redesign — a proper light/dark **design-token system** (segmented theme
  switch, persisted + flash-free; light = warm white/coral, dark = deep slate/cyan), a **searchable +
  category-filtered** emote picker, **real playback controls** (play/pause/scrub/0.5–2× retime, driven
  by per-frame preview PNGs since a GIF `<img>` can't be paused or retimed in-browser), and **staged
  progress** for upload/animate/pack. Backend additions: `/api/presets` returns a `category`;
  `/api/animate` also emits preview-size per-frame PNGs (`_frames/`, excluded from the per-emote zip).

(Alternative AI route — local AnimateDiff/SVD on the RTX 3070 — remains available for organic motion,
but the puppet path is the one that guarantees clean alpha, perfect loops, and controllable, on-theme
motion, so it is the primary engine.)

## 10. Open questions / future
- Auto-suggest best effect from image content? (Claude-in-the-loop already covers this manually.)
- APNG output (Discord doesn't take it as emoji, but nice for archive).
- Batch mode (folder → all emojis).
