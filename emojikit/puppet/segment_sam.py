"""SAM-assisted part segmentation (the v2 generalization step).

Claude point-prompts SAM for each semantic part; SAM returns a precise mask. Positive
points mark the part, negative points (on the body / other parts) carve it out. This is
how the puppet rig is built for an ARBITRARY character without hand-reading polygons.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

_MODEL = None


def _model(weights: str = "mobile_sam.pt"):
    global _MODEL
    if _MODEL is None:
        from ultralytics import SAM

        _MODEL = SAM(weights)
    return _MODEL


def segment(image_path: str | Path, points: list[tuple[int, int]], labels: list[int]) -> np.ndarray:
    """Return a boolean HxW mask for the part indicated by point prompts.

    points: [(x,y), ...] in image pixels. labels: 1 = part (positive), 0 = not-part.
    """
    res = _model()(str(image_path), points=[list(p) for p in points], labels=labels, verbose=False)
    m = res[0].masks.data[0].cpu().numpy()
    return m.astype(bool)


def mask_to_image(mask: np.ndarray) -> Image.Image:
    return Image.fromarray((mask * 255).astype("uint8"), "L")


def attachment_pivot(part: np.ndarray, parent: np.ndarray) -> tuple[int, int]:
    """Estimate a part's joint = the part pixel closest to the parent's centroid.

    A good first guess for the rotation/bend pivot of an appendage.
    """
    ys, xs = np.where(parent)
    pcx, pcy = float(xs.mean()), float(ys.mean())
    pys, pxs = np.where(part)
    d2 = (pxs - pcx) ** 2 + (pys - pcy) ** 2
    i = int(np.argmin(d2))
    return int(pxs[i]), int(pys[i])
