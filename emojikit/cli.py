"""emojikit command-line interface."""

from __future__ import annotations

import typer

from .core import effects, profiles

app = typer.Typer(add_completion=False, help="image -> emoji and emoji -> animated GIF emoji.")


def _human(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024 or unit == "MB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size}"


@app.command()
def animate(
    input: str = typer.Argument(..., help="path to a static emoji/image (png with alpha preferred)"),
    effect: str = typer.Option("party", "--effect", "-e", help="effect or chain, e.g. 'party+bounce'"),
    platform: str = typer.Option("all", "--platform", "-p", help="slack|discord|twitch|all"),
    fps: int = typer.Option(profiles.DEFAULT_FPS, help="frames per second"),
    frames: int = typer.Option(profiles.DEFAULT_FRAMES, help="number of frames"),
    out: str = typer.Option("output", "--out", "-o", help="output directory"),
):
    """Turn a static emoji into an animated GIF (Function 2)."""
    from .core.animate import animate as run

    rep = run(input, effect=effect, out_dir=out, platform=platform, fps=fps, frames=frames)
    typer.secho(f"\n  animated '{input}'  effect={effect}  {frames}f @ {fps}fps\n", fg="cyan")
    for o in rep["outputs"]:
        if o.get("kind") == "archive":
            typer.echo(f"  archive  {o['file']}")
            continue
        fit = "ok " if o.get("fit") else "OVER"
        line = (f"  [{fit}] {o['platform']:<7} {o['size']:>3}px  "
                f"{_human(o['bytes']):>8} / {_human(o['budget'])}  "
                f"colors={o.get('colors')} frames={o.get('frames')}")
        if o.get("sacrificed"):
            line += f"  (reduced: {', '.join(o['sacrificed'])})"
        typer.secho(line, fg="green" if o.get("fit") else "red")
    typer.echo("")


@app.command()
def auto(
    image: str = typer.Argument(..., help="any character image (animal/cartoon/mascot)"),
    preset: str = typer.Option("love", "--preset", help="motion+FX preset"),
    platform: str = typer.Option("all", "--platform", "-p"),
    name: str = typer.Option(None, "--name", help="rig name (default: image stem)"),
    out: str = typer.Option("output", "--out", "-o"),
):
    """Fully automatic: auto-rig (SAM-free geometry) + animate with a preset (v4)."""
    from pathlib import Path

    from .puppet import autodetect as AD
    from .puppet import presets as P
    from .puppet import rig as R

    rig_name = name or Path(image).stem
    rg, apps, eyes = AD.build_auto_rig(image, name=rig_name)
    roles = [p.role for p in rg.parts]
    typer.secho(f"\n  auto-rigged '{image}': parts={roles}  eyes={len(eyes)}", fg="cyan")
    typer.echo(f"  rig saved: rigs/{rig_name}/rig.json (editable)\n")
    frames = R.render(rg, P.get(preset))
    rep = R.export(frames, f"{rig_name}_{preset}", out_dir=out, platform=platform, fps=rg.fps)
    for o in rep["outputs"]:
        fit = "ok " if o.get("fit") else "OVER"
        typer.secho(f"  [{fit}] {o['platform']:<7} {o['size']:>3}px  {_human(o['bytes'])}",
                    fg="green" if o.get("fit") else "red")
    typer.echo("")


@app.command()
def emote(
    rig: str = typer.Argument(..., help="path to a rig.json (from SAM autorig)"),
    preset: str = typer.Option("love", "--preset", help="motion+FX preset name"),
    platform: str = typer.Option("all", "--platform", "-p", help="slack|discord|twitch|all"),
    out: str = typer.Option("output", "--out", "-o", help="output directory"),
):
    """Animate a rigged character with a motion preset (puppet engine, Function 2 v3)."""
    from pathlib import Path

    from .puppet import presets as P
    from .puppet import rig as R

    rg = R.Rig.load(rig)
    frames = R.render(rg, P.get(preset))
    name = f"{Path(rig).parent.name}_{preset}"
    rep = R.export(frames, name, out_dir=out, platform=platform, fps=rg.fps)
    typer.secho(f"\n  emote '{name}'  ({P.get(preset).desc})\n", fg="cyan")
    for o in rep["outputs"]:
        fit = "ok " if o.get("fit") else "OVER"
        typer.secho(f"  [{fit}] {o['platform']:<7} {o['size']:>3}px  "
                    f"{_human(o['bytes'])} / {_human(o['budget'])}",
                    fg="green" if o.get("fit") else "red")
    typer.echo("")


@app.command()
def serve(host: str = typer.Option("127.0.0.1"), port: int = typer.Option(8000)):
    """Launch the local web UI (drag image, auto-rig, pick emote, preview, download)."""
    from .web.app import main
    typer.secho(f"  emojikit studio -> http://{host}:{port}", fg="cyan")
    main(host=host, port=port)


@app.command("presets")
def list_presets():
    """List available emote presets."""
    from .puppet import presets as P

    typer.echo("available emote presets:\n")
    for name, pr in P.LIBRARY.items():
        typer.echo(f"  {name:<12} {pr.desc}")


@app.command("effects")
def list_effects():
    """List available animation effects."""
    typer.echo("available effects (combine with '+'):\n")
    for name in effects.REGISTRY:
        head = " (needs motion headroom)" if name in effects.NEEDS_HEADROOM else ""
        typer.echo(f"  {name}{head}")


@app.command()
def emojify(
    input: str = typer.Argument(..., help="any image to turn into an emoji"),
    engine: str = typer.Option("local", help="local | codex | api"),
    subject: str = typer.Option(None, help="what the emoji depicts (for codex/api redraw)"),
    style: str = typer.Option("flat", help="redraw style: flat|3d|sticker|pixel"),
    redraw: str = typer.Option(None, "--redraw", help="finish an externally-generated redraw (e.g. from codex)"),
    platform: str = typer.Option("all", "--platform", "-p", help="slack|discord|twitch|all"),
    focus: str = typer.Option("none", help="crop focus: none|top|center (top = head of portraits)"),
    stroke: str = typer.Option("white", help="contour stroke color: white|black|none"),
    stroke_width: int = typer.Option(14, help="stroke width in px at 512 master"),
    saturation: float = typer.Option(1.2, help="saturation multiplier"),
    contrast: float = typer.Option(1.08, help="contrast multiplier"),
    no_segment: bool = typer.Option(False, "--no-segment", help="skip background removal"),
    force_segment: bool = typer.Option(False, "--force-segment", help="run rembg even if already transparent"),
    out: str = typer.Option("output", "--out", "-o", help="output directory"),
):
    """Turn any image into a small, clean emoji (Function 1)."""
    from pathlib import Path

    from .core.emojify import emojify as run
    from .engines import prompts

    # Resolve the source image to finish, depending on engine.
    source = input
    if redraw:
        source = redraw  # externally generated (e.g. codex/gpt-image-2) -> just finish it
    elif engine == "api":
        if not subject:
            typer.secho("--engine api needs --subject (what the emoji depicts).", fg="red")
            raise typer.Exit(1)
        from .engines import openai_api
        prompt = prompts.build_prompt(subject, style=style, transparent=True)
        tmp = Path(out) / Path(input).stem / "_redraw.png"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        typer.secho(f"  gpt-image-1 redraw: {prompt}", fg="cyan")
        openai_api.redraw(input, prompt, tmp)
        source = str(tmp)
    elif engine == "codex":
        prompt = prompts.build_prompt(subject or "<SUBJECT - describe what to draw>", style=style, transparent=False)
        typer.secho("\n  codex / gpt-image-2 handoff (transparent not supported -> we'll cut bg after):\n", fg="cyan")
        typer.echo(f"  PROMPT:\n    {prompt}\n")
        typer.echo("  1) Generate this image with codex (gpt-image-2), save it (e.g. redraw.png).")
        typer.echo(f"  2) Finish it:  python -m emojikit emojify {input} --redraw redraw.png\n")
        raise typer.Exit(0)
    elif engine != "local":
        typer.secho(f"unknown engine '{engine}'. choose local|codex|api.", fg="red")
        raise typer.Exit(1)

    rep = run(
        source, out_dir=out, platform=platform,
        segment_bg=not no_segment, force_segment=force_segment,
        saturation=saturation, contrast=contrast,
        stroke=stroke, stroke_width=stroke_width, focus=focus,
        name=Path(input).stem,
    )
    typer.secho(f"\n  emojified '{input}'  stroke={stroke}({stroke_width}px) "
                f"sat={saturation} con={contrast}\n", fg="cyan")
    for o in rep["outputs"]:
        if o.get("kind") == "archive":
            typer.echo(f"  master   {o['size']}px  {_human(o['bytes']):>8}  {o['file']}")
            continue
        fit = "ok " if o.get("fit") else "OVER"
        typer.secho(
            f"  [{fit}] {o['platform']:<7} {o['size']:>3}px  "
            f"{_human(o['bytes']):>8} / {_human(o['budget'])}  {o['file']}",
            fg="green" if o.get("fit") else "red",
        )
    typer.echo("")


if __name__ == "__main__":
    app()
