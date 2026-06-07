"""Prompt construction for generative emoji redraws.

The `subject` description is the in-the-loop intelligence: a human or Claude looks
at the source image and names what the emoji should depict and in what style.
"""

from __future__ import annotations

STYLE_PRESETS = {
    "flat": "clean flat vector emoji, bold simple shapes, thick clean outline, high color saturation",
    "3d": "glossy 3D emoji like Apple/Microsoft emoji, soft shading, rounded forms, vivid colors",
    "sticker": "die-cut sticker with a thick white border, playful, saturated, slight drop shadow",
    "pixel": "crisp pixel-art emoji, limited palette, bold readable silhouette",
}


def build_prompt(subject: str, style: str = "flat", transparent: bool = True) -> str:
    """Compose a redraw prompt optimized for small-size legibility."""
    style_text = STYLE_PRESETS.get(style, STYLE_PRESETS["flat"])
    bg = "transparent background" if transparent else "plain flat single-color background"
    return (
        f"A single {subject}, drawn as a {style_text}. "
        f"Centered, no text, no extra objects, {bg}. "
        f"Designed to stay clearly recognizable when scaled down to 32x32 pixels."
    )
