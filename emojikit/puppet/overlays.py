"""Procedural expression/FX overlays: hearts, sparkles, blush. Drawn per frame.

Each function composites onto a full-canvas RGBA layer, so they layer cleanly over
the puppet. All motion is phase-based on t in [0,1) for seamless looping.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    f = None
    for name in ("arialbd.ttf", "ariblk.ttf", "seguiemj.ttf", "DejaVuSans-Bold.ttf"):
        try:
            f = ImageFont.truetype(name, size)
            break
        except OSError:
            continue
    if f is None:
        f = ImageFont.load_default()
    _FONT_CACHE[size] = f
    return f


def _heart_points(cx: float, cy: float, size: float) -> list[tuple[float, float]]:
    pts = []
    n = 28
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * size / 16.0, cy - y * size / 16.0))
    return pts


def draw_heart(canvas_size, cx, cy, size, color=(255, 90, 120), alpha=255, outline=(200, 40, 70)) -> Image.Image:
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    pts = _heart_points(cx, cy, size)
    d.polygon(pts, fill=color + (alpha,), outline=outline + (alpha,))
    return layer


def draw_sparkle(canvas_size, cx, cy, r, color=(255, 240, 180), alpha=255) -> Image.Image:
    """4-point twinkle star."""
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    inner = r * 0.22
    pts = [
        (cx, cy - r), (cx + inner, cy - inner), (cx + r, cy), (cx + inner, cy + inner),
        (cx, cy + r), (cx - inner, cy + inner), (cx - r, cy), (cx - inner, cy - inner),
    ]
    d.polygon(pts, fill=color + (alpha,))
    return layer


def draw_blush(canvas_size, centers, rx, ry, color=(255, 120, 140), alpha=120) -> Image.Image:
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for cx, cy in centers:
        d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=color + (alpha,))
    return layer


def floating_hearts(canvas_size, t, spawns, rise, drift=18.0, size=26.0) -> Image.Image:
    """Several hearts at staggered phases, each rising and fading over one loop.

    `spawns` = list of (x, base_y, phase_offset). Each heart's local phase = (t+offset)%1;
    it rises by `rise` px and fades out; staggering offsets makes the stream seamless.
    """
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    for x, by, off in spawns:
        p = (t + off) % 1.0
        y = by - rise * p
        dx = drift * math.sin(p * math.pi * 2)
        alpha = int(255 * max(0.0, math.sin(math.pi * p)))      # fade in then out
        scale = 0.6 + 0.4 * math.sin(math.pi * p)
        if alpha <= 4:
            continue
        h = draw_heart(canvas_size, x + dx, y, size * scale, alpha=alpha)
        out.alpha_composite(h)
    return out


def twinkle_sparkles(canvas_size, t, spots) -> Image.Image:
    """`spots` = list of (x, y, r, phase). Each sparkle pops in/out on its phase."""
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    for x, y, r, ph in spots:
        p = (t + ph) % 1.0
        a = max(0.0, math.sin(math.pi * p))
        alpha = int(255 * (a ** 1.5))
        rr = r * (0.4 + 0.6 * a)
        if alpha <= 4:
            continue
        out.alpha_composite(draw_sparkle(canvas_size, x, y, rr, alpha=alpha))
    return out


# --------------------------------------------------------------------------- #
# extended FX library (v3): stars, notes, text pops, tears, anger, sweat, confetti
# --------------------------------------------------------------------------- #
def _star5(cx, cy, r):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.42
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def draw_star(canvas_size, cx, cy, r, color=(255, 215, 80), alpha=255, outline=(220, 150, 0)):
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(_star5(cx, cy, r), fill=color + (alpha,), outline=outline + (alpha,))
    return layer


def draw_note(canvas_size, cx, cy, r, color=(60, 60, 70), alpha=255):
    layer = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - r, cy - r * 0.7, cx + r, cy + r * 0.7], fill=color + (alpha,))
    d.rectangle([cx + r * 0.7, cy - r * 2.6, cx + r * 1.05, cy], fill=color + (alpha,))
    d.polygon([(cx + r * 1.05, cy - r * 2.6), (cx + r * 2.0, cy - r * 2.1),
               (cx + r * 1.05, cy - r * 1.5)], fill=color + (alpha,))
    return layer


def _drop(cx, cy, r):
    return [(cx, cy - r * 1.6), (cx + r * 0.8, cy - r * 0.2), (cx + r, cy + r * 0.4),
            (cx, cy + r), (cx - r, cy + r * 0.4), (cx - r * 0.8, cy - r * 0.2)]


def draw_text_pop(canvas_size, t, anchors, text, color, window=(0.15, 0.85), size=120):
    """Pop a symbol (e.g. '!' or '?') in/out over the loop at each anchor."""
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    lo, hi = window
    if not (lo <= t <= hi):
        return out
    p = (t - lo) / (hi - lo)
    s = math.sin(math.pi * p)
    if s <= 0.04:
        return out
    fnt = _font(max(8, int(size * (0.5 + 0.5 * s))))
    a = int(255 * min(1.0, s * 1.4))
    for ax, ay in anchors:
        tmp = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        d = ImageDraw.Draw(tmp)
        d.text((ax, ay), text, font=fnt, fill=color + (a,),
               stroke_width=max(2, size // 30), stroke_fill=(255, 255, 255, a), anchor="mm")
        out.alpha_composite(tmp)
    return out


def draw_caption(canvas_size, text, *, pos="bottom", fill=(255, 255, 255),
                 stroke=(20, 20, 20), max_width_frac=0.94, max_height_frac=0.24,
                 margin_frac=0.04) -> Image.Image:
    """A bold meme-style caption (white fill + thick dark outline), auto-fit to width.

    Steady (not flashing) for legibility — text emotes live or die on being readable.
    Font size grows until the text just fills `max_width_frac` of the canvas (or the
    height cap), so a short word like 'GG'/'F'/'POG' lands large; placed in the canvas
    margin band (bottom by default) so it doesn't cover the face.
    """
    W, H = canvas_size
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    text = (text or "").strip()
    if not text:
        return out
    target_w, target_h = W * max_width_frac, H * max_height_frac
    d = ImageDraw.Draw(out)
    best, size = 8, 8
    while size < H:                                   # grow until it no longer fits
        f = _font(size)
        sw = max(2, size // 10)
        bb = d.textbbox((0, 0), text, font=f, stroke_width=sw)
        if (bb[2] - bb[0]) > target_w or (bb[3] - bb[1]) > target_h:
            break
        best, size = size, size + 4
    f = _font(best)
    sw = max(2, best // 10)
    bb = d.textbbox((0, 0), text, font=f, stroke_width=sw)
    th = bb[3] - bb[1]
    cx = W // 2
    cy = int(margin_frac * H + th / 2) if pos == "top" else int(H * (1 - margin_frac) - th / 2)
    d.text((cx, cy), text, font=f, fill=fill + (255,), anchor="mm",
           stroke_width=sw, stroke_fill=stroke + (255,))
    return out


def floating_glyphs(canvas_size, t, spawns, kind="star", rise=150, size=24):
    """Generic rising/fading FX stream (kind: star|note|heart)."""
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    for x, by, off in spawns:
        p = (t + off) % 1.0
        y = by - rise * p
        dx = 16 * math.sin(p * math.pi * 2 + by)
        alpha = int(255 * max(0.0, math.sin(math.pi * p)))
        if alpha <= 4:
            continue
        sc = 0.6 + 0.4 * math.sin(math.pi * p)
        if kind == "star":
            out.alpha_composite(draw_star(canvas_size, x + dx, y, size * sc, alpha=alpha))
        elif kind == "note":
            out.alpha_composite(draw_note(canvas_size, x + dx, y, size * 0.5 * sc, alpha=alpha))
        else:
            out.alpha_composite(draw_heart(canvas_size, x + dx, y, size * sc, alpha=alpha))
    return out


def zzz(canvas_size, t, anchor, size=46, color=(120, 150, 220)):
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    ax, ay = anchor
    for k in range(3):
        ph = (t + k / 3.0) % 1.0
        a = int(220 * max(0.0, math.sin(math.pi * ph)))
        if a <= 4:
            continue
        s = int(size * (0.6 + 0.5 * ph))
        x = ax + 26 * ph + k * 6
        y = ay - 60 * ph - k * 4
        tmp = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((x, y), "Z", font=_font(s), fill=color + (a,),
                                 stroke_width=2, stroke_fill=(255, 255, 255, a), anchor="mm")
        out.alpha_composite(tmp)
    return out


def tears(canvas_size, t, eyes, size=16, color=(120, 190, 240)):
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    for ex, ey in eyes:
        p = (t * 2) % 1.0
        y = ey + 18 + 80 * p
        a = int(235 * max(0.0, math.sin(math.pi * p)))
        if a <= 4:
            continue
        d.polygon(_drop(ex, y, size), fill=color + (a,), outline=(80, 150, 210, a))
    return out


def sweat(canvas_size, t, anchor, size=22, color=(150, 205, 245)):
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    ax, ay = anchor
    p = t % 1.0
    y = ay + 70 * p
    a = int(235 * max(0.0, math.sin(math.pi * min(1.0, p * 1.3))))
    if a > 4:
        ImageDraw.Draw(out).polygon(_drop(ax, y, size), fill=color + (a,), outline=(80, 150, 210, a))
    return out


def anger(canvas_size, t, anchor, size=44, color=(220, 40, 40)):
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    pulse = 0.7 + 0.3 * math.sin(2 * math.pi * t * 2)
    r = size * pulse
    ax, ay = anchor
    d = ImageDraw.Draw(out)
    w = max(3, int(r * 0.16))
    for sx, sy in [(0, 0), (r * 0.55, -r * 0.1), (r * 0.1, r * 0.55)]:
        d.line([(ax + sx, ay + sy), (ax + sx + r * 0.32, ay + sy)], fill=color + (255,), width=w)
        d.line([(ax + sx + r * 0.32, ay + sy), (ax + sx + r * 0.16, ay + sy + r * 0.34)], fill=color + (255,), width=w)
    return out


def confetti(canvas_size, t, n=14, rise=False):
    out = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    W, H = canvas_size
    palette = [(255, 90, 110), (255, 200, 70), (90, 200, 255), (120, 220, 130), (200, 130, 255)]
    for i in range(n):
        off = (i * 0.137) % 1.0
        p = (t + off) % 1.0
        x = (i * 97 % W)
        y = (p * H) if not rise else (H - p * H)
        ang = (i * 53 + p * 360) % 360
        s = 9 + (i % 3) * 3
        col = palette[i % len(palette)]
        a = int(235 * max(0.2, math.sin(math.pi * p)))
        rect = Image.new("RGBA", (s, int(s * 0.5)), col + (a,))
        rect = rect.rotate(ang, expand=True)
        out.paste(rect, (int(x), int(y)), rect)   # paste clips at edges (no out-of-range)
    return out
