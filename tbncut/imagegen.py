"""Free, local AI images through Draw Things (installed) or any Automatic1111-style server on this Mac.

Turn it on once: Draw Things → Settings → "API Server" (HTTP, port 7860). Nothing leaves the Mac.
If no server is running, every call returns None and the edit carries on without images.
"""
import base64
import json
import urllib.request
from pathlib import Path

URLS = ["http://127.0.0.1:7860", "http://127.0.0.1:7861"]


def available() -> str | None:
    for u in URLS:
        try:
            urllib.request.urlopen(u + "/sdapi/v1/options", timeout=2)
            return u
        except Exception:
            continue
    return None


def make(prompt: str, out: Path, width: int = 768, height: int = 1344, steps: int = 20, seed: int = -1) -> Path | None:
    """One image (portrait 9:16-ish), cached by file name. Returns None when no local server is on."""
    if out.exists():
        return out
    base = available()
    if not base:
        return None
    body = {"prompt": prompt + ", photographic, natural light, high detail", "negative_prompt": "text, watermark, logo, blurry, deformed",
            "width": width, "height": height, "steps": steps, "seed": seed, "cfg_scale": 5}
    req = urllib.request.Request(base + "/sdapi/v1/txt2img", json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            img = json.load(r)["images"][0]
    except Exception:
        return None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(img.split(",", 1)[-1]))
    return out
