"""Background removal (subject segmentation).

Engine order: rembg (U^2-Net, best) -> passthrough. rembg is lazy-imported so the
package works without it installed; the first call downloads a ~176MB model.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

_REMBG_SESSION = None


def already_cut_out(img: Image.Image, frac: float = 0.05) -> bool:
    """True if the image already has a meaningful transparent region (>= `frac` of pixels)."""
    if img.mode != "RGBA":
        return False
    alpha = np.asarray(img.getchannel("A"))
    transparent = float((alpha < 16).mean())
    return transparent >= frac


def _rembg_session():
    global _REMBG_SESSION
    if _REMBG_SESSION is None:
        from rembg import new_session

        _REMBG_SESSION = new_session("u2net")
    return _REMBG_SESSION


def remove_background(img: Image.Image, force: bool = False) -> Image.Image:
    """Return the subject on a transparent background.

    If the image already looks cut out and `force` is False, it is returned as-is.
    Falls back to passthrough (with a warning) if rembg is unavailable.
    """
    if not force and already_cut_out(img):
        return img.convert("RGBA")

    try:
        from rembg import remove

        out = remove(img.convert("RGBA"), session=_rembg_session())
        return out.convert("RGBA")
    except ImportError:
        import warnings

        warnings.warn("rembg not installed; skipping background removal. "
                      "`pip install rembg onnxruntime` for best results.")
        return img.convert("RGBA")
