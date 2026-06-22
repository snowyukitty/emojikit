# emojikit — TODO

## Deferred (next session)

### 3. Polish presets & FX
- [ ] Brighten/enlarge `dance` music notes (faint at small sizes).
- [ ] Auto-filter tiny false appendages in autodetect (e.g. fox cheek tuft mis-read as a tail:
      drop `tail` candidates with `reach < ~0.08 * min(W,H)`).
- [ ] More presets: `wave` (arm), `love-you` (hand heart), `think`, `peek`, `nod-shy`.
- [ ] Per-preset FX tuning pass (tears density, sparkle brightness, confetti amount).

### 4. Generative "iconify" path (Function 1, top quality)
- [ ] Run a real codex / gpt-image-2 redraw of a busy photo into a clean emoji, then
      `emojify --redraw` finish; compare small-size legibility vs local pipeline.
- [ ] Wire gpt-image-1 API path end-to-end (needs OPENAI_API_KEY) and A/B it.

## Nice-to-have / future
- [ ] Web: caption text field (engine + CLI shipped in v10; just needs a UI input wired to
      `render(caption=, caption_pos=)`, with a live char-count and a 28px legibility hint).
- [ ] Web: add-a-part (draw/brush a mask) in addition to drag-pivot + delete.
- [ ] Web: per-part reach slider; live (debounced) re-render preview.
- [ ] Web: real backend progress via SSE/WebSocket (current progress bars are estimated stages,
      since each endpoint is a single blocking request — accurate enough, but not live).
- [ ] Web: prune old `web_data/<session>/<preset>/_frames/` PNGs (preview frames accumulate on disk).
- [ ] Batch: drag multiple images → auto-pack each.
- [ ] APNG output option (true alpha, for platforms that accept it).
- [ ] v4 face landmarks: detect mouth for talk/laugh expressions.

## Done this session
- v5 web studio · in-browser rig editing (drag joints, delete parts) · zip + full-pack export.
- v6 studio redesign · light/dark design-token system (segmented theme switch, flash-free) ·
  searchable + category-filtered emote picker · real playback controls (play/pause/scrub/retime
  via per-frame preview PNGs) · staged progress for upload/animate/pack · refreshed docs screenshots.
- v7 head-as-part + animation-principles (quality pass vs EmoteLab) · `detect_head` neck split
  (graceful fallback) · real nod/shake/tilt about the neck joint (seam-free bend) · blink+blush+
  heart-eyes follow the head · jump anticipation/squash-stretch · appendage follow-through lag ·
  new preset channels head_nod/head_shake/head_tilt; remapped yes/no/shy/sad/confused/sleep/angry.
- v8 legibility + life (researched emote makers + Twitch 28px design law) · size-adaptive
  sticker outline on the animated path (stroke AFTER per-size resize; encode_gif/webp + web
  preview, so preview==download; `--stroke white|black|none`) · always-on idle breathe
  (Character Animator behavior) so head-only presets aren't frozen below the neck.
- v9 reaction coverage + frame-rate right-sizing (researched Twitch/BTTV/7TV/FFZ guides) ·
  puppet default 24f@20fps -> 18f@15fps (10-15fps emote sweet spot; ~25% smaller GIFs, same
  1.2s loop, more palette headroom on busy art) · 3 most-used reaction presets built from
  any-rig channels: `laugh` (KEKW/LUL hop + tears of joy), `nervous` (monkaS tremble + sweat),
  `cry` (downcast sob + waterfall tears) · all visually verified on the fox face-rig.
- v10 text-caption emotes (a whole high-use category the puppet path lacked) · `draw_caption`
  bold white-fill + thick-outline, auto-fit to ~94% canvas width, margin-band placement
  (bottom default / top) so it doesn't cover the face · `render(caption=, caption_pos=)` +
  `--caption`/`--caption-pos` on auto/emote (value never echoed -> keeps cp1252 ASCII rule) ·
  verified legible at master/112px, exports within budget.

## v7 follow-ups (next)
- [ ] Re-run existing saved rigs through `build_auto_rig` to pick up head parts (or add a
      "re-detect head" button in the web studio for rigs made before v7).
- [ ] Head shake (`no`) is a 2D z-roll (chibi convention); consider a subtle horizontal
      shift for a more literal "turn".
- [ ] Tune `detect_head` neck_ratio/band on more real characters (mascots, full-body animals).
- [ ] ② mouth + pupil anchors (open/smile/talk, eyes look up for `think`) — builds on v7.
