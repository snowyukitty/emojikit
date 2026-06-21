"""Geometric deformations used by the puppet rig — all size-preserving and alpha-safe.

Layers are full-canvas RGBA images (the part placed at its canvas position, the rest
transparent), so transforms compose by simple alpha compositing.
"""

from __future__ import annotations

import math

from PIL import Image


def ease_io(t: float) -> float:
    """Smooth ease-in-out on [0,1]."""
    return 0.5 - 0.5 * math.cos(math.pi * t)


def ping(t: float) -> float:
    """0 -> 1 -> 0 over t in [0,1], smooth (for one squeeze/pulse per loop)."""
    return math.sin(math.pi * t)


def bend_point(pt, pivot, theta_max_deg: float, reach: float):
    """Where a point lands after `bend()` — same ramped rotation about the pivot.

    Keeps face anchors (eyes/blush/heart-eyes) glued to the head while it nods/tilts,
    using the exact angle ramp `bend()` applies to pixels at that distance.
    """
    if abs(theta_max_deg) < 1e-3:
        return pt
    px, py = pivot
    dx, dy = pt[0] - px, pt[1] - py
    frac = min(1.0, math.hypot(dx, dy) / max(1.0, reach))
    frac = 0.5 - 0.5 * math.cos(math.pi * frac)
    th = math.radians(theta_max_deg) * frac
    c, s = math.cos(th), math.sin(th)
    return (px + dx * c - dy * s, py + dx * s + dy * c)


def _key(p: float, keys) -> float:
    """Eased linear interpolation of a keyframed curve (sorted (phase, value) pairs).

    Endpoints at phase 0 and 1 should match so the curve is loop-continuous.
    """
    for (p0, v0), (p1, v1) in zip(keys, keys[1:]):
        if p0 <= p <= p1:
            k = (p - p0) / (p1 - p0) if p1 > p0 else 0.0
            k = 0.5 - 0.5 * math.cos(math.pi * k)          # ease in/out each segment
            return v0 + (v1 - v0) * k
    return keys[-1][1]


def jump_profile(phase: float):
    """One hop per cycle with the 12-principles feel: anticipation crouch -> takeoff
    stretch -> airborne arc -> landing squash -> recover. Loop-safe and continuous
    (keyed so every segment boundary matches, no per-frame pop).

    Returns (lift, squash): lift in [0,1] (multiply by jump px, moves the body up);
    squash in [-1,1] where +1 = compressed (shorter+wider), -1 = stretched (taller+thinner).
    """
    p = phase % 1.0
    lift = _key(p, [(0.0, 0.0), (0.16, 0.0), (0.48, 1.0), (0.80, 0.0), (1.0, 0.0)])
    squash = _key(p, [(0.0, 0.0), (0.16, 1.0), (0.30, -0.5), (0.74, -0.2),
                      (0.86, 0.7), (1.0, 0.0)])
    return lift, squash


def rotate_about(layer: Image.Image, pivot: tuple[float, float], angle_deg: float) -> Image.Image:
    """Rotate a full-canvas layer about a pivot point (canvas coords)."""
    if angle_deg == 0:
        return layer
    return layer.rotate(angle_deg, resample=Image.BICUBIC, center=pivot, expand=False)


def scale_about(layer: Image.Image, anchor: tuple[float, float], sx: float, sy: float) -> Image.Image:
    """Non-uniform scale about an anchor point (canvas coords). Anchor stays fixed.

    Used for an anchored squash/stretch (e.g. feet planted, body squeezes) — distinct
    from a uniform zoom because sx != sy and the anchor does not move.
    """
    if sx == 1.0 and sy == 1.0:
        return layer
    ax, ay = anchor
    # PIL AFFINE uses inverse mapping: input = M * output.
    coeffs = (1.0 / sx, 0.0, ax * (1.0 - 1.0 / sx),
              0.0, 1.0 / sy, ay * (1.0 - 1.0 / sy))
    return layer.transform(layer.size, Image.AFFINE, coeffs, resample=Image.BICUBIC)


def bend(layer: Image.Image, pivot: tuple[float, float], theta_max_deg: float, reach: float) -> Image.Image:
    """Curl/bend a layer about a pivot — rotation grows with distance from the pivot.

    Each pixel is rotated about `pivot` by an angle that ramps from 0 (at the pivot)
    to `theta_max_deg` (at `reach` px away and beyond). Because displacement is zero at
    the root, the part stays glued to the body there — no seam, no tear — while the tip
    swings. This is the correct way to animate a tail/limb, replacing rigid rotation.
    """
    import numpy as np
    from scipy.ndimage import map_coordinates

    if abs(theta_max_deg) < 1e-3:
        return layer
    W, H = layer.size
    # Only the part's neighbourhood matters; warp inside its bbox (+pad) for big speedups.
    alpha = np.asarray(layer.getchannel("A"))
    ys0, xs0 = np.where(alpha > 0)
    if xs0.size == 0:
        return layer
    pad = int(reach * 0.4) + 12
    x0 = max(0, int(xs0.min()) - pad); y0 = max(0, int(ys0.min()) - pad)
    x1 = min(W, int(xs0.max()) + 1 + pad); y1 = min(H, int(ys0.max()) + 1 + pad)

    arr = np.asarray(layer.crop((x0, y0, x1, y1)))
    h, w = arr.shape[:2]
    px, py = pivot[0] - x0, pivot[1] - y0
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - px, yy - py
    frac = np.clip(np.sqrt(dx * dx + dy * dy) / max(1.0, reach), 0.0, 1.0)
    frac = 0.5 - 0.5 * np.cos(np.pi * frac)            # ease so the bend is smooth
    th = np.radians(theta_max_deg) * frac
    cth, sth = np.cos(-th), np.sin(-th)
    sx = px + dx * cth - dy * sth
    sy = py + dx * sth + dy * cth
    coords = np.stack([sy.ravel(), sx.ravel()])
    warped = np.zeros_like(arr)
    for c in range(arr.shape[2]):
        warped[..., c] = map_coordinates(arr[..., c], coords, order=1, mode="constant", cval=0).reshape(h, w)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    out.paste(Image.fromarray(warped, "RGBA"), (x0, y0))
    return out
