"""gpt-image-1 redraw via the OpenAI Images API (native transparent background).

Uses the /images/edits endpoint so the source image conditions the result.
Requires the OPENAI_API_KEY environment variable. Implemented with urllib so no
extra dependency is needed. NOTE: untested without a key — guarded with clear errors.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.request
import uuid
from pathlib import Path

API_URL = "https://api.openai.com/v1/images/edits"


def _multipart(fields: dict[str, str], files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    crlf = b"\r\n"
    out = bytearray()
    for k, v in fields.items():
        out += b"--" + boundary.encode() + crlf
        out += f'Content-Disposition: form-data; name="{k}"'.encode() + crlf + crlf
        out += str(v).encode() + crlf
    for k, path in files.items():
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        out += b"--" + boundary.encode() + crlf
        out += f'Content-Disposition: form-data; name="{k}"; filename="{path.name}"'.encode() + crlf
        out += f"Content-Type: {ctype}".encode() + crlf + crlf
        out += path.read_bytes() + crlf
    out += b"--" + boundary.encode() + b"--" + crlf
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def redraw(
    image_path: str | Path,
    prompt: str,
    out_path: str | Path,
    *,
    size: str = "1024x1024",
    quality: str = "high",
) -> Path:
    """Redraw `image_path` per `prompt` into a transparent PNG saved at `out_path`."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set. Use --engine codex, or export the key.")

    body, ctype = _multipart(
        fields={
            "model": "gpt-image-1",
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "background": "transparent",
            "output_format": "png",
            "n": "1",
        },
        files={"image[]": Path(image_path)},
    )
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": ctype},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    b64 = data["data"][0]["b64_json"]
    out_path = Path(out_path)
    out_path.write_bytes(base64.b64decode(b64))
    return out_path
