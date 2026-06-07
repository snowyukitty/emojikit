"""Function 2 pipeline: static emoji -> animated GIF/WebP across platforms."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import effects, profiles
from .io_utils import ensure_dir, load_rgba, smart_square_crop

WORKING = 320  # render resolution; downscaled per target size for best quality


def _prepare_base(img: Image.Image, names: list[str]) -> Image.Image:
    """Place the subject on a WORKING square canvas, leaving motion headroom if needed."""
    subject = smart_square_crop(img, margin=0.0)
    needs_headroom = any(n in effects.NEEDS_HEADROOM for n in names)
    ratio = 0.70 if needs_headroom else 0.92
    inner = int(WORKING * ratio)
    subject = subject.resize((inner, inner), Image.LANCZOS)
    base = Image.new("RGBA", (WORKING, WORKING), (0, 0, 0, 0))
    base.paste(subject, ((WORKING - inner) // 2, (WORKING - inner) // 2), subject)
    return base


def render_frames(base: Image.Image, names: list[str], n_frames: int) -> list[Image.Image]:
    return [effects.render_frame(base, names, i / n_frames) for i in range(n_frames)]


def animate(
    input_path: str | Path,
    effect: str,
    out_dir: str | Path = "output",
    platform: str = "all",
    fps: int = profiles.DEFAULT_FPS,
    frames: int = profiles.DEFAULT_FRAMES,
    keep_master: bool = True,
    name: str | None = None,
) -> dict:
    """Run the full animate pipeline. Returns a structured report."""
    from .encode import encode_gif, encode_webp

    names = effects.parse_chain(effect)
    platforms = profiles.resolve(platform)

    img = load_rgba(input_path)
    base = _prepare_base(img, names)
    rendered = render_frames(base, names, frames)

    stem = name or Path(input_path).stem
    root = ensure_dir(Path(out_dir) / stem)

    report: dict = {"input": str(input_path), "effect": effect, "fps": fps,
                    "frames": frames, "outputs": []}

    # High-quality archive copies (WebP, true alpha) at master size.
    if keep_master:
        master_webp = root / "master.webp"
        encode_webp(rendered, profiles.MASTER_SIZE, fps, master_webp)
        rendered[0].resize((profiles.MASTER_SIZE,) * 2, Image.LANCZOS).save(root / "master.png")
        report["outputs"].append({"file": str(master_webp), "kind": "archive"})

    for p in platforms:
        pdir = ensure_dir(root / p.name)
        for size in p.sizes:
            gif_path = pdir / f"{stem}_{size}.gif"
            rep = encode_gif(rendered, size, fps, gif_path, budget=p.animated_budget)
            rep.update({"file": str(gif_path), "platform": p.name, "size": size,
                        "budget": p.animated_budget})
            report["outputs"].append(rep)

    return report
