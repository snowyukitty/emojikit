"""Loading, normalization, alpha-aware cropping and square padding."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def load_rgba(path: str | Path) -> Image.Image:
    """Load an image as RGBA with EXIF orientation applied."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    return img.convert("RGBA")


def alpha_bbox(img: Image.Image, threshold: int = 8) -> tuple[int, int, int, int] | None:
    """Bounding box of pixels whose alpha exceeds `threshold`. None if fully transparent."""
    alpha = np.asarray(img.getchannel("A"))
    ys, xs = np.where(alpha > threshold)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def smart_square_crop(img: Image.Image, margin: float = 0.08) -> Image.Image:
    """Crop to the subject (via alpha bbox) and pad to a centered transparent square.

    If the image has no meaningful alpha (fully opaque), we just pad the whole frame
    to a square so nothing gets cut off.
    """
    bbox = alpha_bbox(img)
    if bbox is None:
        cropped = img
    else:
        cropped = img.crop(bbox)

    w, h = cropped.size
    side = max(w, h)
    pad = int(round(side * margin))
    side += pad * 2

    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(cropped, ((side - w) // 2, (side - h) // 2), cropped)
    return canvas


def focus_crop(img: Image.Image, mode: str = "none") -> Image.Image:
    """Crop the subject region for better small-size legibility.

    - none:   return as-is (use the whole subject).
    - top:    square crop at the TOP of the subject bbox (head of sitting animals/portraits).
    - center: centered square crop of the subject bbox.
    """
    if mode == "none":
        return img
    bbox = alpha_bbox(img)
    if bbox is None:
        return img
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    side = min(w, h)
    if mode == "top":
        cx = x0 + w // 2
        left = max(x0, cx - side // 2)
        return img.crop((left, y0, left + side, y0 + side))
    if mode == "center":
        cx, cy = x0 + w // 2, y0 + h // 2
        return img.crop((cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2))
    raise ValueError(f"unknown focus mode '{mode}' (none|top|center)")


def pad_to_square(img: Image.Image, fill=(0, 0, 0, 0)) -> Image.Image:
    """Pad (never crop) to a centered square."""
    w, h = img.size
    if w == h:
        return img
    side = max(w, h)
    canvas = Image.new("RGBA", (side, side), fill)
    canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
    return canvas


def resize_square(img: Image.Image, size: int, sharpen: bool = True) -> Image.Image:
    """High-quality square downscale (Lanczos) with optional mild post-sharpen."""
    from PIL import ImageFilter

    out = img.resize((size, size), Image.LANCZOS)
    if sharpen and size <= 128:
        out = out.filter(ImageFilter.UnsharpMask(radius=1.0, percent=60, threshold=2))
    return out


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
