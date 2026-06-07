"""Build a puppet Rig from SAM point-prompts — the semi-automatic v2 path.

Given, per part, a few positive/negative point prompts, SAM produces a precise mask;
we auto-estimate the joint pivot and tip reach, save the masks, and emit an editable
rig JSON. Swapping in a new character means new point-prompts, not hand-read polygons.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from ..core.io_utils import ensure_dir
from . import segment_sam as S
from .rig import Part, Rig


def _subject_mask(img: Image.Image, thr: int = 16) -> np.ndarray:
    return np.asarray(img.convert("RGBA").getchannel("A")) > thr


def build_rig(
    src: str,
    parts_spec: list[dict],   # [{name, role, pos:[(x,y)], neg:[(x,y)], z}]
    *,
    eyes=None, blush=None, feet=(0, 0), hearts=None, sparkles=None,
    margin: float = 0.16, name: str = "rig", out_dir: str = "rigs",
    fps: int = 20, frames: int = 24,
) -> Rig:
    from scipy.ndimage import binary_dilation

    img = Image.open(src).convert("RGBA")
    W, H = img.size
    subject = _subject_mask(img)

    canvas = int(max(W, H) * (1 + 2 * margin))
    ox, oy = (canvas - W) // 2, (canvas - H) // 2
    root = ensure_dir(Path(out_dir) / name)
    mdir = ensure_dir(root / "masks")

    parts: list[Part] = []
    for spec in parts_spec:
        pts = list(spec["pos"]) + list(spec.get("neg", []))
        labels = [1] * len(spec["pos"]) + [0] * len(spec.get("neg", []))
        part_bool = S.segment(src, pts, labels)
        part_bool = binary_dilation(part_bool, iterations=3)   # include the ink outline

        parent = subject & ~part_bool
        px, py = S.attachment_pivot(part_bool, parent)         # image coords
        pys, pxs = np.where(part_bool)
        reach = float(np.sqrt((pxs - px) ** 2 + (pys - py) ** 2).max())

        # place mask on the canvas
        cmask = Image.new("L", (canvas, canvas), 0)
        cmask.paste(Image.fromarray((part_bool * 255).astype("uint8"), "L"), (ox, oy))
        mpath = mdir / f"{spec['name']}.png"
        cmask.save(mpath)

        parts.append(Part(name=spec["name"], role=spec["role"], mask=str(mpath),
                          pivot=(px + ox, py + oy), reach=reach, z=spec.get("z", 0)))

    rig = Rig(src=src, canvas=canvas, offset=(ox, oy), parts=parts,
              eyes=eyes or [], blush=blush or [], feet=feet,
              hearts=hearts or [], sparkles=sparkles or [], fps=fps, frames=frames)
    rig.save(root / "rig.json")
    return rig
