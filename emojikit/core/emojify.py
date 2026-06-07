"""Function 1 pipeline: any image -> a small, clean, recognizable emoji/sticker."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import enhance, profiles, segment
from .io_utils import ensure_dir, focus_crop, load_rgba, resize_square, smart_square_crop

MASTER = profiles.MASTER_SIZE  # 512


def _place_on_canvas(subject: Image.Image, ratio: float) -> Image.Image:
    """Center the subject on a transparent MASTER square, occupying `ratio` of it.

    Leaving margin is what gives the contour stroke room to grow without clipping.
    """
    subject = smart_square_crop(subject, margin=0.0)
    inner = int(MASTER * ratio)
    subject = subject.resize((inner, inner), Image.LANCZOS)
    canvas = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    canvas.paste(subject, ((MASTER - inner) // 2, (MASTER - inner) // 2), subject)
    return canvas


def build_master(
    img: Image.Image,
    *,
    segment_bg: bool = True,
    force_segment: bool = False,
    saturation: float = 1.2,
    contrast: float = 1.08,
    stroke: str = "white",
    stroke_width: int = 14,
    focus: str = "none",
) -> Image.Image:
    """Run the legibility pipeline and return the 512px transparent master emoji."""
    if segment_bg:
        img = segment.remove_background(img, force=force_segment)

    img = focus_crop(img, focus)

    color = enhance.STROKE_COLORS.get(stroke, enhance.STROKE_COLORS["white"])
    # Reserve room for the stroke so it isn't clipped at the canvas edge.
    ratio = 0.84 if (color and stroke_width > 0) else 0.94
    base = _place_on_canvas(img, ratio)
    base = enhance.boost(base, saturation=saturation, contrast=contrast)
    base = enhance.add_stroke(base, width=stroke_width, color=color)
    return base


def emojify(
    input_path: str | Path,
    out_dir: str | Path = "output",
    platform: str = "all",
    *,
    segment_bg: bool = True,
    force_segment: bool = False,
    saturation: float = 1.2,
    contrast: float = 1.08,
    stroke: str = "white",
    stroke_width: int = 14,
    focus: str = "none",
    keep_master: bool = True,
    name: str | None = None,
) -> dict:
    """Full Function 1 pipeline (local engine). Returns a structured report."""
    platforms = profiles.resolve(platform)
    img = load_rgba(input_path)

    master = build_master(
        img,
        segment_bg=segment_bg,
        force_segment=force_segment,
        saturation=saturation,
        contrast=contrast,
        stroke=stroke,
        stroke_width=stroke_width,
        focus=focus,
    )

    stem = name or Path(input_path).stem
    root = ensure_dir(Path(out_dir) / stem)
    report: dict = {"input": str(input_path), "stroke": stroke, "outputs": []}

    if keep_master:
        mpath = root / "master.png"
        master.save(mpath)
        report["outputs"].append({"file": str(mpath), "kind": "archive",
                                  "size": MASTER, "bytes": mpath.stat().st_size})

    for p in platforms:
        pdir = ensure_dir(root / p.name)
        for size in p.sizes:
            out = resize_square(master, size, sharpen=True)
            fpath = pdir / f"{stem}_{size}.png"
            out.save(fpath, optimize=True)
            nbytes = fpath.stat().st_size
            report["outputs"].append({
                "file": str(fpath), "platform": p.name, "size": size,
                "bytes": nbytes, "budget": p.static_budget,
                "fit": nbytes <= p.static_budget,
            })

    return report
