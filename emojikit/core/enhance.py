"""Legibility enhancement: the steps that make a subject read clearly at small sizes.

Saturation + contrast boost, a clean contour stroke (the single biggest win for
small-size readability), and an optional post-downscale sharpen.
"""

from __future__ import annotations

from PIL import Image, ImageEnhance, ImageFilter

# Named stroke colors.
STROKE_COLORS = {
    "white": (255, 255, 255),
    "black": (20, 20, 20),
    "none": None,
}


def _split_alpha(img: Image.Image):
    img = img.convert("RGBA")
    return img, img.getchannel("A")


def boost(img: Image.Image, saturation: float = 1.2, contrast: float = 1.08) -> Image.Image:
    """Boost saturation and contrast on the color channels, preserving alpha."""
    rgba, alpha = _split_alpha(img)
    rgb = rgba.convert("RGB")
    rgb = ImageEnhance.Color(rgb).enhance(saturation)
    rgb = ImageEnhance.Contrast(rgb).enhance(contrast)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def add_stroke(img: Image.Image, width: int, color=(255, 255, 255), threshold: int = 40) -> Image.Image:
    """Add a clean outline around the subject by dilating its alpha and filling with `color`.

    `width` is in pixels at the current resolution. The image must have transparent
    margins of at least `width` px so the stroke is not clipped.
    """
    if width <= 0 or color is None:
        return img
    rgba, alpha = _split_alpha(img)

    # Binarize then dilate by repeated 3x3 max-filtering (~1px growth per pass).
    mask = alpha.point(lambda a: 255 if a > threshold else 0)
    dilated = mask
    for _ in range(width):
        dilated = dilated.filter(ImageFilter.MaxFilter(3))
    dilated = dilated.filter(ImageFilter.GaussianBlur(0.7))  # anti-alias the stroke edge

    stroke = Image.new("RGBA", rgba.size, tuple(color) + (0,))
    stroke.putalpha(dilated)
    return Image.alpha_composite(stroke, rgba)


def sharpen(img: Image.Image, percent: int = 70) -> Image.Image:
    return img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=percent, threshold=2))
