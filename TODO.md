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
- [ ] Batch: drag multiple images → auto-pack each.
- [ ] APNG output option (true alpha, for platforms that accept it).
- [ ] v4 face landmarks: detect mouth for talk/laugh expressions.

## Done this session
- v5 web studio · in-browser rig editing (drag joints, delete parts) · zip + full-pack export.
