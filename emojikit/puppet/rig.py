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
    fps: int = 20
    frames: int = 24

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

    # split parts; body = base minus the union of all part masks
    part_imgs = []
    union = Image.new("L", (cv, cv), 0)
    for p in rig.parts:
        m = Image.open(p.mask).convert("L")
        if m.size != (cv, cv):
            m = m.resize((cv, cv))
        layer = Image.new("RGBA", (cv, cv), (0, 0, 0, 0))
        layer.paste(base, (0, 0), m)
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

        # body squash (squeeze) and slump (droop), feet planted
        body = warp.scale_about(body0, feet, 1.0 - pr.squeeze * s, 1.0 + pr.squeeze * 0.6 * s - pr.droop * s)
        if eyeband and pr.blink:
            bt = max(0.0, 1.0 - abs(t - 0.18) / 0.05)
            body = _apply_blink(body, eyeband, 1.0 - 0.5 * bt)

        # parts (bend by role; tails use preset amp), drawn under body
        char = Image.new("RGBA", (cv, cv), (0, 0, 0, 0))
        for p, layer in sorted(part_imgs, key=lambda pl: pl[0].z):
            amp = pr.tail_amp if p.role == "tail" else {"ear": 6.0, "arm": 8.0}.get(p.role, 0.0)
            ang = amp * math.sin(2 * math.pi * pr.part_cycles * t + (0.7 * math.pi if "yellow" in p.name else 0.0))
            char.alpha_composite(warp.bend(layer, tuple(p.pivot), ang, reach=p.reach))
        char.alpha_composite(body)

        # whole-character sway + vertical bob/jump
        if abs(pr.sway_deg) > 0.01:
            char = warp.rotate_about(char, feet, pr.sway_deg * osc)
        dy = pr.bob * (0.5 - 0.5 * math.cos(2 * math.pi * pr.cycles * t)) - pr.jump * abs(math.sin(math.pi * pr.cycles * t))
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

        # --- expression overlays
        if rig.blush and pr.blush > 0:
            a = int(180 * pr.blush * (0.6 + 0.4 * math.sin(2 * math.pi * t)))
            frame.alpha_composite(overlays.draw_blush((cv, cv), [rig.C(*b) for b in rig.blush], 30, 18, alpha=max(0, a)))
        if rig.eyes and pr.heart_eyes > 0:
            he = warp.ease_io(max(0.0, 1.0 - abs(t - 0.5) / 0.28)) * pr.heart_eyes
            if he > 0.03:
                for ex, ey in rig.eyes:
                    cx, cyy = rig.C(ex, ey - 6 * he)
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


def export(frames, name, out_dir="output", platform="all", fps=20, webp=True):
    from ..core.encode import encode_gif, encode_webp

    platforms = profiles.resolve(platform)
    root = ensure_dir(Path(out_dir) / name)
    rep = {"name": name, "outputs": []}
    if webp:
        encode_webp(frames, profiles.MASTER_SIZE, fps, root / "master.webp")
    for p in platforms:
        pdir = ensure_dir(root / p.name)
        for size in p.sizes:
            gif = pdir / f"{name}_{size}.gif"
            r = encode_gif(frames, size, fps, gif, budget=p.animated_budget)
            r.update({"platform": p.name, "size": size, "budget": p.animated_budget, "file": str(gif)})
            rep["outputs"].append(r)
    return rep
