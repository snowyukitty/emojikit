"""FastAPI backend: upload -> auto-rig -> animate(preset) -> multi-size GIFs.

Heavy work (rembg, render, encode) runs synchronously; the frontend shows progress.
Rendered frames are cached per (session, preset) so switching sizes is instant.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
from fastapi import Body, FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw

from ..core import profiles, segment
from ..core.io_utils import load_rgba
from ..puppet import autodetect as AD
from ..puppet import presets as P
from ..puppet import rig as R

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
DATA = Path("web_data")
DATA.mkdir(exist_ok=True)

app = FastAPI(title="emojikit")
app.mount("/files", StaticFiles(directory=str(DATA)), name="files")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

_FRAMES: dict[tuple, list] = {}

# emoji glyph + accent + category per preset for the UI
PRESET_META = {
    "love": ("💞", "#ff6b9d", "Positive"), "dance": ("💃", "#9b6bff", "Hype"),
    "celebrate": ("🎉", "#ffb84d", "Hype"), "happy": ("✨", "#ffd24d", "Positive"),
    "shocked": ("❗", "#ff5d5d", "Reaction"), "confused": ("❓", "#5db4ff", "Reaction"),
    "sleep": ("😴", "#7aa7ff", "Mood"), "sad": ("🥺", "#6b9bd1", "Mood"),
    "angry": ("😡", "#ff5a45", "Mood"), "yes": ("✅", "#57c97a", "Positive"),
    "no": ("🙅", "#ff8a8a", "Reaction"), "shy": ("☺️", "#ff9ec7", "Positive"),
}

PALETTE = [(255, 91, 110), (75, 160, 255), (66, 200, 120), (255, 170, 60),
           (200, 90, 230), (60, 200, 210)]


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/presets")
def presets():
    out = []
    for name, pr in P.LIBRARY.items():
        emoji, accent, category = PRESET_META.get(name, ("⭐", "#888", "Other"))
        out.append({"name": name, "desc": pr.desc, "emoji": emoji,
                    "accent": accent, "category": category})
    return out


def _overlay(master: Image.Image, apps, eyes) -> Image.Image:
    ov = Image.new("RGBA", master.size, (0, 0, 0, 0))
    ov.alpha_composite(master)
    arr = np.array(ov)
    for ci, a in enumerate(apps):
        col = PALETTE[ci % len(PALETTE)]
        sub = arr[a["mask"]]
        sub[:, :3] = (sub[:, :3] * 0.5 + np.array(col) * 0.5).astype("uint8")
        arr[a["mask"]] = sub
    ov = Image.fromarray(arr)
    d = ImageDraw.Draw(ov)
    for ci, a in enumerate(apps):
        x, y = a["pivot"]
        col = PALETTE[ci % len(PALETTE)]
        d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=col + (255,), outline=(255, 255, 255, 255), width=3)
    for ex, ey in eyes:
        d.ellipse([ex - 11, ey - 11, ex + 11, ey + 11], outline=(255, 60, 200, 255), width=4)
    return ov


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    sid = uuid.uuid4().hex[:8]
    sdir = DATA / sid
    sdir.mkdir(parents=True, exist_ok=True)
    raw = sdir / ("input" + Path(file.filename or "x.png").suffix)
    raw.write_bytes(await file.read())

    img = load_rgba(raw)
    seg = segment.remove_background(img)         # transparent subject
    master = sdir / "master.png"
    seg.save(master)

    rig, apps, eyes = AD.build_auto_rig(str(master), name=sid, out_dir=str(DATA))
    _overlay(seg, apps, eyes).save(sdir / "overlay.png")

    return {
        "session": sid,
        "master": f"/files/{sid}/master.png",
        "overlay": f"/files/{sid}/overlay.png",
        "dims": list(seg.size),
        "canvas": rig.canvas,
        "offset": list(rig.offset),
        "parts": [{"name": p.name, "role": p.role, "pivot": list(p.pivot), "reach": round(p.reach)}
                  for p in rig.parts],
        "eyes": [list(e) for e in eyes],
    }


@app.post("/api/rig")
def edit_rig(payload: dict = Body(...)):
    """Apply in-browser rig edits: move pivots, drop parts. Invalidates render cache."""
    sid = payload["session"]
    rp = DATA / sid / "rig.json"
    rig = R.Rig.load(rp)
    edits = {p["name"]: p for p in payload.get("parts", [])}
    kept = []
    for part in rig.parts:
        e = edits.get(part.name)
        if e is None or not e.get("enabled", True):
            continue                              # dropped part
        part.pivot = [int(e["pivot"][0]), int(e["pivot"][1])]
        if "reach" in e:
            part.reach = float(e["reach"])
        kept.append(part)
    rig.parts = kept
    rig.save(rp)
    for k in [k for k in _FRAMES if k[0] == sid]:   # invalidate cached frames
        _FRAMES.pop(k, None)
    return {"ok": True, "parts": len(kept)}


@app.get("/api/zip")
def zip_preset(session: str, preset: str):
    """Zip every platform file for one already-rendered emote."""
    import zipfile
    sdir = DATA / session / preset
    if not sdir.exists():
        return JSONResponse({"error": "render it first"}, status_code=404)
    zpath = DATA / session / f"{preset}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sdir.rglob("*"):
            if f.is_file() and "_frames" not in f.parts:   # skip preview-only PNGs
                z.write(f, f.relative_to(sdir.parent))
    return FileResponse(zpath, filename=f"{preset}_emote.zip")


@app.post("/api/pack")
def export_pack(payload: dict = Body(...)):
    """Render a set of presets and bundle everything into one downloadable zip."""
    import zipfile
    sid = payload["session"]
    names = payload.get("presets") or list(P.LIBRARY.keys())
    rig = R.Rig.load(DATA / sid / "rig.json")
    for nm in names:
        key = (sid, nm)
        frames = _FRAMES.get(key) or R.render(rig, P.get(nm))
        _FRAMES[key] = frames
        R.export(frames, nm, out_dir=str(DATA / sid), platform="all", fps=rig.fps, webp=False)
    zpath = DATA / sid / "emote_pack.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for nm in names:
            for f in (DATA / sid / nm).rglob("*.gif"):
                z.write(f, f.relative_to(DATA / sid))
    return {"url": f"/files/{sid}/emote_pack.zip", "count": len(names)}


@app.post("/api/animate")
def animate(payload: dict = Body(...)):
    sid = payload["session"]
    preset = payload["preset"]
    rig = R.Rig.load(DATA / sid / "rig.json")

    key = (sid, preset)
    frames = _FRAMES.get(key)
    if frames is None:
        frames = R.render(rig, P.get(preset))
        _FRAMES[key] = frames

    rep = R.export(frames, preset, out_dir=str(DATA / sid), platform="all", fps=rig.fps, webp=False)
    sizes = []
    for o in rep["outputs"]:
        rel = Path(o["file"]).relative_to(DATA).as_posix()
        sizes.append({"platform": o["platform"], "size": o["size"], "bytes": o["bytes"],
                      "budget": o["budget"], "fit": o["fit"], "url": f"/files/{rel}"})

    # preview-size per-frame PNGs let the browser scrub/pause/retime the loop
    # (a <img> GIF can only autoplay at a fixed speed).
    preview = _preview_frames(sid, preset, frames)
    return {"preset": preset, "outputs": sizes, "webp": f"/files/{sid}/{preset}/master.webp",
            "frames": preview, "fps": rig.fps}


_PREVIEW_PX = 256


def _preview_frames(sid: str, preset: str, frames) -> list[str]:
    fdir = DATA / sid / preset / "_frames"
    fdir.mkdir(parents=True, exist_ok=True)
    urls = []
    for i, fr in enumerate(frames):
        im = fr.resize((_PREVIEW_PX, _PREVIEW_PX), Image.LANCZOS)
        im.save(fdir / f"{i:03d}.png")
        urls.append(f"/files/{sid}/{preset}/_frames/{i:03d}.png")
    return urls


def main(host="127.0.0.1", port=8000):
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
