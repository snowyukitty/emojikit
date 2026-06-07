"""Hug-cats puppet rig + renderer.

Coordinates are authored in the ORIGINAL image space (789x763) and offset onto a
square working canvas. This file doubles as the reference for how to rig a character:
define part polygons + pivots, write motion as functions of loop phase t, add overlays.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..core import profiles
from ..core.io_utils import ensure_dir, load_rgba
from . import layers, overlays, warp

# --- working canvas placement --------------------------------------------- #
CANVAS = 860
OX, OY = 35, 30          # image -> canvas offset


def C(x, y):
    return (x + OX, y + OY)


# --- rig definition (image coords) ---------------------------------------- #
PINK_TAIL = [(585, 446), (640, 420), (700, 398), (748, 398), (770, 372),
             (758, 345), (705, 332), (655, 348), (608, 400), (582, 430)]
YELLOW_TAIL = [(200, 458), (206, 502), (160, 546), (110, 566), (84, 556),
               (96, 518), (140, 484), (186, 460)]

PINK_TAIL_PIVOT = (590, 430)
YELLOW_TAIL_PIVOT = (198, 472)
PINK_COVER_R = 42        # body patch that hides the tail-root seam at the joint
YELLOW_COVER_R = 38
FEET_ANCHOR = (360, 706)

# Expression anchors (pink cat face).
BLUSH = [(308, 252), (468, 252)]
EYES = [(338, 226), (446, 226)]     # eye centers (for heart-eyes)
EYE_BAND = (290, 205, 490, 246)     # x0,y0,x1,y1

# Floating hearts: (x, base_y, phase_offset) — staggered for a seamless stream.
HEART_SPAWNS = [(285, 135, 0.0), (335, 120, 0.33), (255, 150, 0.66)]
SPARKLE_SPOTS = [(300, 90, 13, 0.1), (350, 70, 10, 0.5), (240, 110, 9, 0.8),
                 (520, 120, 9, 0.4)]


def _apply_blink(body: Image.Image, band, sy: float) -> Image.Image:
    """Vertically squash the eye band about its center -> a geometric blink."""
    if sy >= 0.999:
        return body
    x0, y0, x1, y1 = (band[0] + OX, band[1] + OY, band[2] + OX, band[3] + OY)
    cy = (y0 + y1) / 2
    strip = body.crop((x0, y0, x1, y1))
    h = strip.height
    nh = max(1, int(round(h * sy)))
    squashed = strip.resize((strip.width, nh), Image.BICUBIC)
    # Composite the squashed eye band OVER the original (opaque) face — no clearing,
    # so the vacated rows show skin from the original instead of transparency.
    out = body.copy()
    out.alpha_composite(squashed, (x0, int(round(cy - nh / 2))))
    return out


def _cover_disk(pivot, r, feather=4.0):
    """A soft disk at the joint; the body keeps this region to hide the root seam."""
    m = Image.new("L", (CANVAS, CANVAS), 0)
    cx, cy = pivot
    ImageDraw.Draw(m).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    return m.filter(ImageFilter.GaussianBlur(feather))


def build_layers(src_path: str | Path):
    """Split out the tail layers, leaving a joint 'cover' on the body to hide seams.

    Seam-free rotation trick: the tail LAYER includes the root, but the body only has
    the tail removed OUTSIDE a small disk at the joint (mask - cover). The body therefore
    retains a patch over the joint; tails are drawn UNDER the body, so the rotating root
    edge is hidden beneath that patch and never tears.
    """
    img = load_rgba(src_path)
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.alpha_composite(img, (OX, OY))

    pink_mask = layers.polygon_mask((CANVAS, CANVAS), [C(*p) for p in PINK_TAIL], feather=2.0)
    yellow_mask = layers.polygon_mask((CANVAS, CANVAS), [C(*p) for p in YELLOW_TAIL], feather=2.0)

    # `bend` keeps the root glued to the body, so a plain full-polygon hole lines up
    # with the tail root exactly — no cover patch, no ghost.
    pink_tail = layers.extract(canvas, pink_mask)
    yellow_tail = layers.extract(canvas, yellow_mask)
    body = layers.remove_region(layers.remove_region(canvas, pink_mask), yellow_mask)
    return body, pink_tail, yellow_tail


def render(src_path: str | Path, frames: int = 24) -> list[Image.Image]:
    body0, pink_tail0, yellow_tail0 = build_layers(src_path)
    out = []
    for i in range(frames):
        t = i / frames

        # --- body: anchored "squeeze" (narrower + slightly taller), feet planted
        s = warp.ping(t)                       # 0..1..0 once per loop
        sx = 1.0 - 0.05 * s
        sy = 1.0 + 0.03 * s
        body = warp.scale_about(body0, C(*FEET_ANCHOR), sx, sy)

        # --- subtle blink (eye band squash) layered over the squeeze
        bt = max(0.0, 1.0 - abs(t - 0.18) / 0.05)
        body = _apply_blink(body, EYE_BAND, sy=1.0 - 0.5 * bt)

        # --- tails swish via BEND (root glued, tip curls) -> no tear, seamless loop
        pink_ang = 15.0 * math.sin(2 * math.pi * t)
        yellow_ang = 13.0 * math.sin(2 * math.pi * t + math.pi * 0.7)
        pink_tail = warp.bend(pink_tail0, C(*PINK_TAIL_PIVOT), pink_ang, reach=185)
        yellow_tail = warp.bend(yellow_tail0, C(*YELLOW_TAIL_PIVOT), yellow_ang, reach=135)

        # --- compose the CHARACTER (tails under body), then sway it as one rigid piece
        char = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        char.alpha_composite(yellow_tail)
        char.alpha_composite(pink_tail)
        char.alpha_composite(body)
        sway = 1.8 * math.sin(2 * math.pi * t)            # gentle side-to-side sway
        char = warp.rotate_about(char, C(*FEET_ANCHOR), sway)
        bob = -6.0 * (0.5 - 0.5 * math.cos(2 * math.pi * t))   # tiny vertical lift
        if abs(bob) > 0.5:
            shifted = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
            shifted.alpha_composite(char, (0, int(round(bob))))
            char = shifted

        frame = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        frame.alpha_composite(char)

        # --- expression: blush pulse + heart-eyes pop (once per loop, peak t=0.5)
        blush_a = int(70 + 80 * (0.5 + 0.5 * math.sin(2 * math.pi * t)))
        frame.alpha_composite(overlays.draw_blush((CANVAS, CANVAS), [C(*b) for b in BLUSH],
                                                  rx=30, ry=18, alpha=blush_a))
        he = max(0.0, 1.0 - abs(t - 0.5) / 0.28)
        he = warp.ease_io(he)
        if he > 0.03:
            for ex, ey in EYES:
                cx, cy = C(ex, ey - 6.0 * he)
                frame.alpha_composite(overlays.draw_heart(
                    (CANVAS, CANVAS), cx, cy, 20 * he,
                    color=(255, 70, 110), alpha=int(235 * he), outline=(200, 30, 70)))

        # --- FX: floating hearts + sparkles (world-up, unaffected by sway)
        frame.alpha_composite(overlays.floating_hearts(
            (CANVAS, CANVAS), t, [(C(x, y)[0], C(x, y)[1], o) for x, y, o in HEART_SPAWNS],
            rise=170, size=30))
        frame.alpha_composite(overlays.twinkle_sparkles(
            (CANVAS, CANVAS), t, [(C(x, y)[0], C(x, y)[1], r, ph) for x, y, r, ph in SPARKLE_SPOTS]))

        out.append(frame)
    return out


def export(frames, name, out_dir="output", platform="all", fps=20, keep_master=True) -> dict:
    from ..core.encode import encode_gif, encode_webp

    platforms = profiles.resolve(platform)
    root = ensure_dir(Path(out_dir) / name)
    report = {"name": name, "frames": len(frames), "fps": fps, "outputs": []}

    if keep_master:
        mp = root / "master.webp"
        encode_webp(frames, profiles.MASTER_SIZE, fps, mp)
        report["outputs"].append({"file": str(mp), "kind": "archive"})

    for p in platforms:
        pdir = ensure_dir(root / p.name)
        for size in p.sizes:
            gif = pdir / f"{name}_{size}.gif"
            rep = encode_gif(frames, size, fps, gif, budget=p.animated_budget)
            rep.update({"file": str(gif), "platform": p.name, "size": size, "budget": p.animated_budget})
            report["outputs"].append(rep)
    return report
