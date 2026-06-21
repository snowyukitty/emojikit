"""v4 — fully automatic rigging from a single image, character-agnostic.

No human-face assumptions. Appendages and their joints come from pure shape analysis
(morphological opening to find the thick 'core' body; whatever sticks out is an
appendage, attached where it is nearest the core). Roles are inferred from each
appendage's direction, so it works for animals, cartoons, mascots — anything.
Eyes (optional, for expression FX) are dark symmetric blobs in the upper region;
if not found, expression FX degrade gracefully.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from ..core.io_utils import ensure_dir
from .rig import Part, Rig


def _subject(img: Image.Image, thr: int = 16) -> np.ndarray:
    return np.asarray(img.convert("RGBA").getchannel("A")) > thr


def detect_appendages(subj: np.ndarray, core_frac: float = 0.10, min_area_frac: float = 0.004):
    """Return appendages as dicts: {mask, pivot(x,y), reach, role}. Pure geometry."""
    from skimage.morphology import disk, opening

    H, W = subj.shape
    R = max(6, int(core_frac * min(W, H)))
    core = opening(subj, disk(R))
    if core.sum() == 0:                       # very thin subject: fall back
        core = ndi.binary_erosion(subj, iterations=R)
    app = subj & ~ndi.binary_dilation(core, iterations=4)
    lbl, n = ndi.label(app)
    core_dt = ndi.distance_transform_edt(~core)

    ys, xs = np.where(subj)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    bh = max(1, y1 - y0)
    min_area = min_area_frac * subj.sum()

    out = []
    for i in range(1, n + 1):
        part = lbl == i
        area = int(part.sum())
        if area < min_area:
            continue
        pys, pxs = np.where(part)
        k = int(np.argmin(core_dt[part]))
        pvx, pvy = int(pxs[k]), int(pys[k])           # attachment = nearest-to-core
        reach = float(np.sqrt((pxs - pvx) ** 2 + (pys - pvy) ** 2).max())
        cx, cy = pxs.mean(), pys.mean()
        dx, dy = cx - pvx, cy - pvy                    # appendage direction

        if (pvy - y0) < 0.25 * bh and dy <= abs(dx):   # high + not pointing down
            role = "ear"
        elif dy > abs(dx) and dy > 0:                  # points clearly downward
            role = "leg"
        else:                                          # sideways / upward, long
            role = "tail"
        out.append({"mask": part, "pivot": (pvx, pvy), "reach": reach, "role": role,
                    "area": area})
    return out


def detect_head(subj: np.ndarray, *, neck_ratio: float = 0.78,
                min_frac: float = 0.10, max_frac: float = 0.72):
    """Split the head off at the narrowest 'neck' above the body — a first-class part.

    Pure geometry: scan the per-row width profile for the narrowest cut in the upper
    body; if it's a real pinch (neck notably narrower than the head above it) and the
    head is a sane fraction of the subject, return {mask, pivot(neck joint), reach}.
    Degrades gracefully (returns None) for neckless round blobs / multi-character art,
    so nod/shake fall back to whole-body motion instead of tearing.
    """
    ys, xs = np.where(subj)
    if ys.size == 0:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    bh = y1 - y0
    if bh < 20:
        return None
    widths = subj.sum(axis=1).astype(float)              # subject pixels per row
    b0, b1 = y0 + int(0.18 * bh), y0 + int(0.62 * bh)    # plausible neck band
    if b1 <= b0:
        return None
    yn = b0 + int(np.argmin(widths[b0:b1]))
    head_w = widths[y0:yn].max() if yn > y0 else 0.0
    if head_w <= 0 or widths[yn] >= neck_ratio * head_w:  # no real pinch -> no head
        return None

    slab = np.zeros_like(subj)
    slab[y0:yn + 1] = subj[y0:yn + 1]
    lbl, n = ndi.label(slab)                              # keep the main head blob only
    if n == 0:
        return None
    sizes = ndi.sum(np.ones_like(lbl), lbl, index=range(1, n + 1))
    head = lbl == (1 + int(np.argmax(sizes)))

    frac = head.sum() / subj.sum()
    if frac < min_frac or frac > max_frac:
        return None
    cols = np.where(subj[yn])[0]                          # neck joint = neck-row center
    pvx, pvy = int(cols.mean()), int(yn)
    hy, hx = np.where(head)
    reach = float(np.sqrt((hx - pvx) ** 2 + (hy - pvy) ** 2).max())
    return {"mask": head, "pivot": (pvx, pvy), "reach": reach}


def detect_eyes(img: Image.Image, subj: np.ndarray, max_pair=True):
    """Dark, compact, roughly symmetric blobs in the upper region → eye anchors."""
    L = np.asarray(img.convert("L"))
    ys, xs = np.where(subj)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    head = np.zeros_like(subj)
    head[y0:int(y0 + 0.55 * (y1 - y0)), x0:x1] = True
    dark = (L < 80) & subj & head
    lbl, n = ndi.label(dark)
    cand = []
    total = subj.sum()
    for i in range(1, n + 1):
        m = lbl == i
        a = int(m.sum())
        if a < 0.0006 * total or a > 0.03 * total:
            continue
        yy, xx = np.where(m)
        h, w = yy.max() - yy.min() + 1, xx.max() - xx.min() + 1
        if max(w, h) / max(1, min(w, h)) > 6:
            continue
        cand.append((float(xx.mean()), float(yy.mean()), a))
    if len(cand) < 2:
        return []
    cand.sort(key=lambda c: -c[2])
    midx = (x0 + x1) / 2
    # choose the pair on opposite sides with the closest y
    best, bd = None, 1e9
    for i in range(len(cand)):
        for j in range(i + 1, len(cand)):
            a, b = cand[i], cand[j]
            if (a[0] - midx) * (b[0] - midx) > 0:      # same side -> skip
                continue
            d = abs(a[1] - b[1])
            if d < bd:
                bd, best = d, (a, b)
    if not best:
        return []
    (ax, ay, _), (bx, by, _) = best
    pair = sorted([(int(ax), int(ay)), (int(bx), int(by))])
    return pair


def build_auto_rig(src: str, *, name="auto", out_dir="rigs", margin=0.16,
                   animate_roles=("tail", "ear"), fps=20, frames=24) -> Rig:
    """Detect parts + eyes and write an editable rig JSON. The human/AI loop can tweak it."""
    img = Image.open(src).convert("RGBA")
    W, H = img.size
    subj = _subject(img)
    apps = detect_appendages(subj)
    head = detect_head(subj)
    eyes = detect_eyes(img, subj)

    canvas = int(max(W, H) * (1 + 2 * margin))
    ox, oy = (canvas - W) // 2, (canvas - H) // 2
    root = ensure_dir(Path(out_dir) / name)
    mdir = ensure_dir(root / "masks")

    def _save_mask(arr, fname):
        cmask = Image.new("L", (canvas, canvas), 0)
        cmask.paste(Image.fromarray((arr * 255).astype("uint8"), "L"), (ox, oy))
        mp = mdir / fname
        cmask.save(mp)
        return str(mp)

    parts = []
    if head is not None:
        # Head is a first-class part (real nod/shake/tilt). Ears ride with it -> drop
        # them as separate parts so they don't detach from the moving head.
        animate_roles = tuple(r for r in animate_roles if r != "ear")
        parts.append(Part(name="head", role="head", mask=_save_mask(head["mask"], "head.png"),
                          pivot=(head["pivot"][0] + ox, head["pivot"][1] + oy),
                          reach=head["reach"], z=5))
    for idx, a in enumerate(apps):
        if a["role"] not in animate_roles:
            continue
        # An appendage that lies inside the head slab is part of the head -> skip it.
        if head is not None and a["pivot"][1] <= head["pivot"][1]:
            continue
        mp = _save_mask(a["mask"], f"{a['role']}_{idx}.png")
        parts.append(Part(name=f"{a['role']}_{idx}", role=a["role"], mask=mp,
                          pivot=(a["pivot"][0] + ox, a["pivot"][1] + oy),
                          reach=a["reach"], z=-1))

    ys, xs = np.where(subj)
    feet = (int((xs.min() + xs.max()) / 2), int(ys.max()) - 10)
    if eyes:
        ex = int(sum(e[0] for e in eyes) / 2)
        ey = int(sum(e[1] for e in eyes) / 2)
        blush = [(eyes[0][0] - 6, eyes[0][1] + 26), (eyes[1][0] + 6, eyes[1][1] + 26)]
        head = (ex, max(0, min(e[1] for e in eyes) - 130))
    else:
        blush, head = [], (int((xs.min() + xs.max()) / 2), int(ys.min()) - 60)

    hx = int((xs.min() + xs.max()) / 2)
    hy = int(ys.min()) + 30
    hearts = [(hx - 40, hy, 0.0), (hx, hy - 20, 0.33), (hx - 70, hy + 10, 0.66)]
    sparkles = [(hx - 60, hy - 40, 12, 0.1), (hx + 10, hy - 60, 10, 0.5), (hx + 60, hy - 20, 9, 0.8)]

    rig = Rig(src=src, canvas=canvas, offset=(ox, oy), parts=parts,
              eyes=eyes, blush=blush, feet=feet, head=head,
              hearts=hearts, sparkles=sparkles, fps=fps, frames=frames)
    rig.save(root / "rig.json")
    return rig, apps, eyes
