"""Per-frame transforms for animated emoji.

Each effect has the signature ``effect(img, t, **params) -> Image`` where
``img`` is a square RGBA frame and ``t`` is the loop phase in ``[0, 1)``.
Effects return a frame of the *same* canvas size, so they compose by chaining.

Geometric effects assume the base image already has motion headroom around the
subject (added by ``animate.py``) so scaling/translation does not clip.
"""

from __future__ import annotations

import math

from PIL import Image


# --------------------------------------------------------------------------- #
# geometric helpers (size-preserving, alpha-safe)
# --------------------------------------------------------------------------- #
def _translate(img: Image.Image, dx: float, dy: float) -> Image.Image:
    canvas = Image.new("RGBA", img.size, (0, 0, 0, 0))
    canvas.paste(img, (int(round(dx)), int(round(dy))), img)
    return canvas


def _scale_centered(img: Image.Image, fx: float, fy: float | None = None) -> Image.Image:
    fy = fx if fy is None else fy
    w, h = img.size
    nw, nh = max(1, int(round(w * fx))), max(1, int(round(h * fy)))
    scaled = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(scaled, ((w - nw) // 2, (h - nh) // 2), scaled)
    return canvas


def _rotate(img: Image.Image, deg: float) -> Image.Image:
    return img.rotate(deg, resample=Image.BICUBIC, expand=False)


# --------------------------------------------------------------------------- #
# color effects
# --------------------------------------------------------------------------- #
def party(img: Image.Image, t: float, **_) -> Image.Image:
    """Cyclic hue rotation — preserves shading. Best for already-colored emoji."""
    alpha = img.getchannel("A")
    hsv = img.convert("RGB").convert("HSV")
    h, s, v = hsv.split()
    shift = int(t * 256) % 256
    h = h.point(lambda x: (x + shift) % 256)
    out = Image.merge("HSV", (h, s, v)).convert("RGB")
    out.putalpha(alpha)
    return out


def rainbow(img: Image.Image, t: float, **_) -> Image.Image:
    """Party-parrot flood: keep brightness, flood a single rotating saturated hue.

    Works even on grayscale/monochrome emoji where ``party`` would do nothing.
    """
    alpha = img.getchannel("A")
    hsv = img.convert("RGB").convert("HSV")
    _, _, v = hsv.split()
    hue = int(t * 256) % 256
    h = Image.new("L", img.size, hue)
    s = Image.new("L", img.size, 255)
    out = Image.merge("HSV", (h, s, v)).convert("RGB")
    out.putalpha(alpha)
    return out


# --------------------------------------------------------------------------- #
# geometric effects
# --------------------------------------------------------------------------- #
def shake(img: Image.Image, t: float, amp: float = 0.06, freq: int = 3, **_) -> Image.Image:
    a = img.size[0] * amp
    dx = a * math.sin(2 * math.pi * freq * t)
    dy = a * math.sin(2 * math.pi * freq * t + math.pi / 2)
    return _translate(img, dx, dy)


def spin(img: Image.Image, t: float, revolutions: int = 1, **_) -> Image.Image:
    return _rotate(img, -360 * revolutions * t)


def pulse(img: Image.Image, t: float, lo: float = 0.82, hi: float = 1.0, **_) -> Image.Image:
    f = lo + (hi - lo) * 0.5 * (1 + math.sin(2 * math.pi * t - math.pi / 2))
    return _scale_centered(img, f)


def bounce(img: Image.Image, t: float, amp: float = 0.12, **_) -> Image.Image:
    a = img.size[1] * amp
    dy = -a * abs(math.sin(math.pi * t))
    return _translate(img, 0, dy)


def wobble(img: Image.Image, t: float, amp: float = 0.10, freq: int = 1, **_) -> Image.Image:
    """Horizontal shear oscillation."""
    w, h = img.size
    shear = amp * math.sin(2 * math.pi * freq * t)
    # affine: x' = x + shear*(y - h/2)
    coeffs = (1, shear, -shear * h / 2, 0, 1, 0)
    return img.transform((w, h), Image.AFFINE, coeffs, resample=Image.BICUBIC)


def jello(img: Image.Image, t: float, amp: float = 0.16, **_) -> Image.Image:
    """Squash/stretch: width and height oscillate in anti-phase (volume-ish preserving)."""
    s = amp * math.sin(2 * math.pi * t)
    return _scale_centered(img, 1 + s, 1 - s)


def zoom(img: Image.Image, t: float, lo: float = 0.85, hi: float = 1.25, **_) -> Image.Image:
    f = lo + (hi - lo) * t
    return _scale_centered(img, f)


def slide(img: Image.Image, t: float, **_) -> Image.Image:
    """Marquee horizontal scroll that wraps around."""
    w, h = img.size
    dx = int(t * w)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(img, (dx, 0), img)
    canvas.paste(img, (dx - w, 0), img)
    return canvas


def glitch(img: Image.Image, t: float, amp: float = 0.03, **_) -> Image.Image:
    """RGB channel split shift for a digital-glitch feel."""
    w, h = img.size
    off = int(w * amp * math.sin(2 * math.pi * t))
    r, g, b, a = img.split()
    r = r.transform((w, h), Image.AFFINE, (1, 0, off, 0, 1, 0))
    b = b.transform((w, h), Image.AFFINE, (1, 0, -off, 0, 1, 0))
    return Image.merge("RGBA", (r, g, b, a))


# --------------------------------------------------------------------------- #
# registry / composition
# --------------------------------------------------------------------------- #
REGISTRY = {
    "party": party,
    "rainbow": rainbow,
    "shake": shake,
    "spin": spin,
    "pulse": pulse,
    "bounce": bounce,
    "wobble": wobble,
    "jello": jello,
    "zoom": zoom,
    "slide": slide,
    "glitch": glitch,
}

# Geometric effects need motion headroom around the subject so they don't clip.
NEEDS_HEADROOM = {"shake", "spin", "pulse", "bounce", "wobble", "jello", "zoom", "slide"}


def parse_chain(spec: str) -> list[str]:
    """'party+bounce' -> ['party', 'bounce']. Validates names."""
    names = [p.strip().lower() for p in spec.split("+") if p.strip()]
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        raise ValueError(
            f"unknown effect(s): {', '.join(unknown)}. available: {', '.join(REGISTRY)}"
        )
    return names


def render_frame(base: Image.Image, names: list[str], t: float) -> Image.Image:
    frame = base
    for name in names:
        frame = REGISTRY[name](frame, t)
    return frame
