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

## v7 follow-ups (next)
- [ ] Re-run existing saved rigs through `build_auto_rig` to pick up head parts (or add a
      "re-detect head" button in the web studio for rigs made before v7).
- [ ] Head shake (`no`) is a 2D z-roll (chibi convention); consider a subtle horizontal
      shift for a more literal "turn".
- [ ] Tune `detect_head` neck_ratio/band on more real characters (mascots, full-body animals).
- [ ] ② mouth + pupil anchors (open/smile/talk, eyes look up for `think`) — builds on v7.
