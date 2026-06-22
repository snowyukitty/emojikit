"""Data-driven puppet rig: a JSON-serializable description of a character's parts,
pivots, face anchors and FX, plus a renderer that animates any such rig.

This is the v2 generalization: instead of hand-coding one character, a rig is produced
by SAM-assisted segmentation (see autorig.py) and rendered here. Editable + reproducible.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image, ImageChops

from ..core import profiles
from ..core.io_utils import ensure_dir, load_rgba
from . import overlays, warp


@dataclass
class Part:
    name: str
    role: str               # "tail" | "ear" | "arm" | ... (drives motion)
    mask: str               # path to an L-mode PNG mask (canvas-sized)
    pivot: tuple[int, int]  # canvas coords
    reach: float            # px from pivot to the part's tip (for bend)
    z: int = 0              # draw order; lower = behind body


@dataclass
class Rig:
    src: str
    canvas: int
    offset: tuple[int, int]
    parts: list[Part] = field(default_factory=list)
    eyes: list[tuple[int, int]] = field(default_factory=list)     # image coords
    blush: list[tuple[int, int]] = field(default_factory=list)    # image coords
    feet: tuple[int, int] = (0, 0)                                # image coords
    head: tuple[int, int] = (0, 0)                                # image coords (FX anchor); auto if (0,0)
    hearts: list[tuple[int, int, float]] = field(default_factory=list)   # image x,y,phase
    sparkles: list[tuple[int, int, int, float]] = field(default_factory=list)
    fps: int = 15
    frames: int = 18

    def save(self, path: str | Path):
        d = asdict(self)
        d["parts"] = [asdict(p) if not isinstance(p, dict) else p for p in self.parts]
        Path(path).write_text(json.dumps(d, indent=2))

    @staticmethod
    def load(path: str | Path) -> "Rig":
        d = json.loads(Path(path).read_text())
        parts = [Part(**p) for p in d.pop("parts")]
        return Rig(parts=parts, **d)

    def C(self, x, y):
        return (x + self.offset[0], y + self.offset[1])


def _apply_blink(body, band, sy):
    if sy >= 0.999:
        return body
    x0, y0, x1, y1 = band
    cy = (y0 + y1) / 2
    strip = body.crop((x0, y0, x1, y1))
    nh = max(1, int(round(strip.height * sy)))
    squashed = strip.resize((strip.width, nh), Image.BICUBIC)
    out = body.copy()
    out.alpha_composite(squashed, (x0, int(round(cy - nh / 2))))
    return out


def _flat_alpha(size, mask, intensity):
    return ImageChops.multiply(mask, Image.new("L", size, int(255 * intensity)))


def render(rig: Rig, preset=None) -> list[Image.Image]:
    from .presets import get as get_preset

    pr = preset or get_preset("love")
    cv = rig.canvas
    base = Image.new("RGBA", (cv, cv), (0, 0, 0, 0))
    base.alpha_composite(load_rgba(rig.src), tuple(rig.offset))

    # split parts; body = base minus the union of all part masks. The head (if any) is
    # a first-class part rendered with its own neck-joint motion (nod/shake/tilt).
    part_imgs = []
    head_part = None
    union = Image.new("L", (cv, cv), 0)
    for p in rig.parts:
        m = Image.open(p.mask).convert("L")
        if m.size != (cv, cv):
            m = m.resize((cv, cv))
        layer = Image.new("RGBA", (cv, cv), (0, 0, 0, 0))
        layer.paste(base, (0, 0), m)
        if p.role == "head":
            head_part = (p, layer)
        else:
            part_imgs.append((p, layer))
        union = ImageChops.lighter(union, m)
    body0 = base.copy()
    body0.putalpha(ImageChops.multiply(body0.getchannel("A"), union.point(lambda v: 255 - v)))

    feet = rig.C(*rig.feet)
    head = rig.C(*rig.head) if rig.head != (0, 0) else (
        (rig.C(*(int(sum(x for x, _ in rig.eyes) / len(rig.eyes)),
                 min(y for _, y in rig.eyes) - 130))) if rig.eyes else (cv // 2, cv // 5))
    eyeband = (rig.C(min(x for x, _ in rig.eyes) - 30, min(y for _, y in rig.eyes) - 22) +
               rig.C(max(x for x, _ in rig.eyes) + 30, max(y for _, y in rig.eyes) + 22)) if rig.eyes else None

    out = []
    n = rig.frames
    for i in range(n):
        t = i / n
        s = warp.ping(t)
        osc = math.sin(2 * math.pi * pr.cycles * t)

        # head motion (relative to body): nod dips down only (seam-safe), shake/tilt
        # rotate about the neck joint via seam-free bend. Anchors follow the head.
        head_ang = pr.head_tilt * warp.ping(t) + pr.head_shake * osc
        head_dy = pr.head_nod * (0.5 - 0.5 * math.cos(2 * math.pi * pr.cycles * t))

        def head_xform(pt):
            if head_part is None:
                return pt
            hp, _ = head_part
            q = warp.bend_point(pt, tuple(hp.pivot), head_ang, hp.reach)
            return (q[0], q[1] + head_dy)

        # body squash (squeeze) + slump (droop) + always-on idle breathe, feet planted.
        # The breathe is a slow chest rise (taller+narrower on inhale) so even head-only
        # presets (yes/no/shy) never look frozen below the neck.
        bph = 0.5 - 0.5 * math.cos(2 * math.pi * t)
        body = warp.scale_about(body0, feet,
                                1.0 - pr.squeeze * s - 0.6 * pr.breathe * bph,
                                1.0 + pr.squeeze * 0.6 * s - pr.droop * s + pr.breathe * bph)
        # blink lives on the head layer when the head is split off, else on the body
        if eyeband and pr.blink and head_part is None:
            bt = max(0.0, 1.0 - abs(t - 0.18) / 0.05)
            body = _apply_blink(body, eyeband, 1.0 - 0.5 * bt)

        # under-body parts (tails/legs): bend by role with a follow-through lag (tip
        # trails the body for secondary motion)
        char = Image.new("RGBA", (cv, cv), (0, 0, 0, 0))
        for p, layer in sorted(part_imgs, key=lambda pl: pl[0].z):
            if p.z >= 0:
                continue
            amp = pr.tail_amp if p.role == "tail" else {"ear": 6.0, "arm": 8.0}.get(p.role, 0.0)
            ph = 0.7 * math.pi if "yellow" in p.name else 0.0
            ang = amp * math.sin(2 * math.pi * pr.part_cycles * t - 0.5 + ph)
            char.alpha_composite(warp.bend(layer, tuple(p.pivot), ang, reach=p.reach))
        char.alpha_composite(body)
        # over-body parts (arms), then the head with its own motion
        for p, layer in sorted(part_imgs, key=lambda pl: pl[0].z):
            if p.z < 0:
                continue
            amp = {"ear": 6.0, "arm": 8.0}.get(p.role, 0.0)
            ang = amp * math.sin(2 * math.pi * pr.part_cycles * t - 0.5)
            char.alpha_composite(warp.bend(layer, tuple(p.pivot), ang, reach=p.reach))
        if head_part is not None:
            hp, hlayer = head_part
            if eyeband and pr.blink:
                bt = max(0.0, 1.0 - abs(t - 0.18) / 0.05)
                hlayer = _apply_blink(hlayer, eyeband, 1.0 - 0.5 * bt)
            hlayer = warp.bend(hlayer, tuple(hp.pivot), head_ang, reach=hp.reach)
            char.alpha_composite(hlayer, (0, int(round(head_dy))))

        # jump: anticipation crouch -> stretch -> landing squash, applied to the whole
        # character about the feet (squash + stretch principle)
        if pr.jump > 0:
            lift, sq = warp.jump_profile(pr.cycles * t)
            char = warp.scale_about(char, feet, 1.0 + 0.12 * sq, 1.0 - 0.18 * sq)
            jump_dy = -pr.jump * lift
        else:
            lift, jump_dy = 0.0, 0.0

        # whole-character sway + vertical bob/jump
        if abs(pr.sway_deg) > 0.01:
            char = warp.rotate_about(char, feet, pr.sway_deg * osc)
        dy = pr.bob * (0.5 - 0.5 * math.cos(2 * math.pi * pr.cycles * t)) + jump_dy
        if abs(dy) > 0.5:
            sh = Image.new("RGBA", (cv, cv), (0, 0, 0, 0))
            sh.alpha_composite(char, (0, int(round(dy))))
            char = sh

        # color tint (sad/angry), masked to the character
        if pr.tint:
            (tr, tg, tb), ti = pr.tint
            tl = Image.new("RGBA", (cv, cv), (tr, tg, tb, 0))
            tl.putalpha(_flat_alpha((cv, cv), char.getchannel("A"), ti))
            char = Image.alpha_composite(char, tl)

        frame = Image.new("RGBA", (cv, cv), (0, 0, 0, 0))
        frame.alpha_composite(char)

        # --- expression overlays (anchors follow the head so they stay on the face)
        if rig.blush and pr.blush > 0:
            a = int(180 * pr.blush * (0.6 + 0.4 * math.sin(2 * math.pi * t)))
            frame.alpha_composite(overlays.draw_blush((cv, cv), [head_xform(rig.C(*b)) for b in rig.blush],
                                                      30, 18, alpha=max(0, a)))
        if rig.eyes and pr.heart_eyes > 0:
            he = warp.ease_io(max(0.0, 1.0 - abs(t - 0.5) / 0.28)) * pr.heart_eyes
            if he > 0.03:
                for ex, ey in rig.eyes:
                    cx, cyy = head_xform(rig.C(ex, ey - 6 * he))
                    frame.alpha_composite(overlays.draw_heart((cv, cv), cx, cyy, 20 * he,
                                          color=(255, 70, 110), alpha=int(235 * he), outline=(200, 30, 70)))

        # --- streaming + event FX
        spawns = [(rig.C(x, y)[0], rig.C(x, y)[1], o) for x, y, o in rig.hearts] or \
                 [(head[0], head[1], k / 3) for k in range(3)]
        if pr.fx_hearts > 0:
            frame.alpha_composite(overlays.floating_glyphs((cv, cv), t, spawns, "heart", rise=170, size=30))
        if pr.fx_stars > 0:
            frame.alpha_composite(overlays.floating_glyphs((cv, cv), t, spawns, "star", rise=160, size=26))
        if pr.fx_notes > 0:
            frame.alpha_composite(overlays.floating_glyphs((cv, cv), t, spawns, "note", rise=160, size=40))
        if pr.fx_sparkles > 0 and rig.sparkles:
            frame.alpha_composite(overlays.twinkle_sparkles((cv, cv), t,
                                  [(rig.C(x, y)[0], rig.C(x, y)[1], r, ph) for x, y, r, ph in rig.sparkles]))
        if pr.fx_confetti > 0:
            frame.alpha_composite(overlays.confetti((cv, cv), t))
        if pr.fx_zzz:
            frame.alpha_composite(overlays.zzz((cv, cv), t, (head[0] + 30, head[1])))
        if pr.fx_exclaim:
            frame.alpha_composite(overlays.draw_text_pop((cv, cv), t, [(head[0], head[1])], "!", (235, 50, 50)))
        if pr.fx_question:
            frame.alpha_composite(overlays.draw_text_pop((cv, cv), t, [(head[0], head[1])], "?", (90, 140, 220)))
        if pr.fx_tears and rig.eyes:
            frame.alpha_composite(overlays.tears((cv, cv), t, [rig.C(*e) for e in rig.eyes]))
        if pr.fx_anger:
            frame.alpha_composite(overlays.anger((cv, cv), t, (head[0] + 20, head[1] + 30)))
        if pr.fx_sweat:
            frame.alpha_composite(overlays.sweat((cv, cv), t, (head[0] + 40, head[1] + 40)))

        out.append(frame)
    return out


def export(frames, name, out_dir="output", platform="all", fps=20, webp=True, stroke="white"):
    from ..core.encode import encode_gif, encode_webp
    from ..core.enhance import STROKE_COLORS

    color = STROKE_COLORS.get(stroke) if isinstance(stroke, str) else stroke
    platforms = profiles.resolve(platform)
    root = ensure_dir(Path(out_dir) / name)
    rep = {"name": name, "outputs": []}
    if webp:
        encode_webp(frames, profiles.MASTER_SIZE, fps, root / "master.webp", stroke=color)
    for p in platforms:
        pdir = ensure_dir(root / p.name)
        for size in p.sizes:
            gif = pdir / f"{name}_{size}.gif"
            r = encode_gif(frames, size, fps, gif, budget=p.animated_budget, stroke=color)
            r.update({"platform": p.name, "size": size, "budget": p.animated_budget, "file": str(gif)})
            rep["outputs"].append(r)
    return rep
