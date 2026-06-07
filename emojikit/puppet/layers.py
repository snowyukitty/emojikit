"""Cut a character image into movable part-layers via polygon masks.

A part is extracted onto a full-canvas transparent image; the base layer has that
region softly removed so the moving part doesn't leave a ghost behind it. Soft
(feathered) mask edges keep the seams invisible.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter


def polygon_mask(size: tuple[int, int], points: list[tuple[float, float]], feather: float = 2.0) -> Image.Image:
    """Rasterize a polygon to an 'L' mask with feathered edges."""
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon(points, fill=255)
    if feather > 0:
        m = m.filter(ImageFilter.GaussianBlur(feather))
    return m


def extract(canvas_img: Image.Image, mask: Image.Image) -> Image.Image:
    """Return a full-canvas RGBA layer containing only the masked region."""
    layer = Image.new("RGBA", canvas_img.size, (0, 0, 0, 0))
    layer.paste(canvas_img, (0, 0), mask)
    return layer


def remove_region(canvas_img: Image.Image, mask: Image.Image) -> Image.Image:
    """Return `canvas_img` with the masked region made transparent (the base layer)."""
    base = canvas_img.copy()
    # multiply existing alpha by (255 - mask)
    from PIL import ImageChops

    inv = mask.point(lambda v: 255 - v)
    a = base.getchannel("A")
    base.putalpha(ImageChops.multiply(a, inv))
    return base
