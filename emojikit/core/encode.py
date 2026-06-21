"""Encoding frames to GIF (via ffmpeg palettegen) and WebP, with a size-budget optimizer."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from .enhance import add_stroke

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def stroke_width(size: int) -> int:
    """Sticker-outline width (px) for a target size — bolder, relatively, at small sizes.

    Emote design law: an outline of >=2px at 112px is what keeps a character legible
    when it shrinks to 28px (Twitch's main size). We therefore stroke AFTER resizing to
    each export size, not once at master res (a master-res stroke is too thin at 28 and
    too thick at 128). ~size/56 gives 1px@28, 1px@56, 2px@112, 2px@128, capped at 4.
    """
    return max(1, min(4, round(size / 56)))


def _resize_frames(frames: list[Image.Image], size: int, stroke=None) -> list[Image.Image]:
    if frames[0].size == (size, size):
        sized = list(frames)
    else:
        sized = [f.resize((size, size), Image.LANCZOS) for f in frames]
    if stroke is not None:
        w = stroke_width(size)
        sized = [add_stroke(f, w, color=stroke) for f in sized]
    return sized


def _run_ffmpeg_gif(png_dir: Path, fps: int, max_colors: int, out_path: Path) -> None:
    """Encode a numbered PNG sequence to a transparent GIF with a generated palette."""
    vf = (
        f"split[a][b];"
        f"[a]palettegen=max_colors={max_colors}:reserve_transparent=1:stats_mode=full[p];"
        f"[b][p]paletteuse=dither=bayer:bayer_scale=3:alpha_threshold=128"
    )
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(fps),
        "-i", str(png_dir / "frame_%04d.png"),
        "-filter_complex", vf,
        "-loop", "0",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def encode_gif(
    frames: list[Image.Image],
    size: int,
    fps: int,
    out_path: Path,
    budget: int | None = None,
    stroke=None,
) -> dict:
    """Encode frames to a GIF at `size`, shrinking under `budget` bytes if needed.

    Returns a report dict: {bytes, colors, frames, fit, sacrificed[]}.
    Never silently truncates — every reduction is recorded in `sacrificed`.
    `stroke` is an (r,g,b) sticker-outline color applied per-size (None = no outline).
    """
    sized = _resize_frames(frames, size, stroke)
    sacrificed: list[str] = []

    # Reduction ladder: drop palette colors first (least visible), then frames.
    color_ladder = [256, 192, 128, 96, 64, 48, 32]
    cur_frames = sized

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        def write(seq: list[Image.Image]) -> None:
            for f in tdp.glob("frame_*.png"):
                f.unlink()
            for i, fr in enumerate(seq):
                fr.save(tdp / f"frame_{i:04d}.png")

        best = None
        for colors in color_ladder:
            write(cur_frames)
            _run_ffmpeg_gif(tdp, fps, colors, out_path)
            nbytes = out_path.stat().st_size
            best = {"bytes": nbytes, "colors": colors, "frames": len(cur_frames)}
            if budget is None or nbytes <= budget:
                break
        else:
            # Still over budget after the color ladder -> thin the frames out.
            colors = color_ladder[-1]
            while len(cur_frames) > 6 and best and best["bytes"] > (budget or 0):
                cur_frames = cur_frames[::2]
                sacrificed.append(f"frames -> {len(cur_frames)}")
                write(cur_frames)
                _run_ffmpeg_gif(tdp, fps, colors, out_path)
                best = {"bytes": out_path.stat().st_size, "colors": colors, "frames": len(cur_frames)}
                if best["bytes"] <= (budget or 0):
                    break

    if best and best["colors"] < 256:
        sacrificed.append(f"colors -> {best['colors']}")

    report = dict(best or {})
    report["fit"] = budget is None or report.get("bytes", 0) <= budget
    report["sacrificed"] = sacrificed
    return report


def encode_webp(frames: list[Image.Image], size: int, fps: int, out_path: Path,
                quality: int = 90, stroke=None) -> dict:
    """Animated WebP with true alpha — the high-quality archive copy."""
    sized = _resize_frames(frames, size, stroke)
    duration = int(round(1000 / fps))
    sized[0].save(
        out_path,
        format="WEBP",
        save_all=True,
        append_images=sized[1:],
        duration=duration,
        loop=0,
        disposal=2,
        quality=quality,
        method=4,
    )
    return {"bytes": out_path.stat().st_size, "frames": len(sized)}
