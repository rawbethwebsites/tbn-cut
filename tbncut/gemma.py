"""Steps 3-4: ask the local Gemma (Ollama) to score what's interesting.

Gemma only ranks. It never decides timings: Python keeps those.
"""
import base64
import io
import json
import os
import subprocess
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

OLLAMA = "http://127.0.0.1:11434/api/chat"
MODEL = os.environ.get("TBN_CUT_VISION_MODEL", "gemma4-uncensored-vision")  # install.sh sets this on other machines


STATE = {"down": False}  # set when Ollama is too busy to answer; later calls in the run skip straight to defaults


def ask(prompt: str, images: list[bytes] | None = None, schema: dict | None = None, timeout: int = 180) -> dict:
    if STATE["down"]:
        raise RuntimeError("gemma busy earlier in this run")
    msg = {"role": "user", "content": prompt}
    if images:
        msg["images"] = [base64.b64encode(b).decode() for b in images]
    body = {"model": MODEL, "stream": False, "think": False, "messages": [msg],
            "options": {"temperature": 0.2}, "format": schema or "json"}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = json.load(r)["message"]["content"]
    except Exception as e:
        if "timed out" in str(e).lower():
            STATE["down"] = True
        raise
    return json.loads(text)


def frames(video: Path, out_dir: Path, every: float = 2.0, width: int = 256) -> list[tuple[float, Path]]:
    """One small frame every `every` seconds (cached)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not any(out_dir.glob("f_*.jpg")):
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                                   capture_output=True, text=True).stdout.strip() or 0)
        every = min(every, max(0.5, dur / 3))  # short clips still get a few frames
        # keyframes only on the video chip: one frame every 2 s doesn't need every frame decoded
        fast = ["-hwaccel", "videotoolbox", "-skip_frame", "nokey"] if every >= 1.5 else []
        subprocess.run(["ffmpeg", "-v", "error", *fast, "-i", str(video), "-vf", f"fps=1/{every},scale={width}:-2",
                        "-q:v", "5", str(out_dir / "f_%05d.jpg")], check=True)
    files = sorted(out_dir.glob("f_*.jpg"))
    return [(i * every, f) for i, f in enumerate(files)]


def _sheet(paths: list[Path]) -> bytes:
    """3x3 grid with a big number on each cell so Gemma can refer to them."""
    ims = [Image.open(p).convert("RGB") for p in paths]
    w, h = ims[0].size
    sheet = Image.new("RGB", (w * 3, h * 3), "black")
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(ims):
        x, y = (i % 3) * w, (i // 3) * h
        sheet.paste(im.resize((w, h)), (x, y))
        d.rectangle([x, y, x + 34, y + 30], fill="black")
        d.text((x + 8, y + 4), str(i + 1), fill="yellow", font_size=22)
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=80)
    return buf.getvalue()


VISUAL_SCHEMA = {"type": "object", "properties": {"scores": {"type": "array", "items": {"type": "integer"}}},
                 "required": ["scores"]}


def score_frames(video: Path, work: Path, cache: Path, kind: str = "talk") -> list[dict]:
    """[{"t": seconds, "v": 1-10}] — how watchable each moment looks."""
    if cache.exists():
        return json.loads(cache.read_text())
    fr = frames(video, work / "frames")
    out = []
    for i in range(0, len(fr), 9):
        chunk = fr[i:i + 9]
        if kind == "broll":
            prompt = (f"This grid shows {len(chunk)} numbered frames from a B-roll clip (no talking), in time order. "
                      "Score each frame 1-10 as a 2-second cutaway in a short-form video: clear subject, action or "
                      "movement, good light, sharp, nice composition. Low: blurry, dark, floor or ceiling, camera being "
                      "set up, nothing happening. "
                      f'Reply as JSON {{"scores": [{len(chunk)} integers in frame order]}}.')
        else:
            prompt = (f"This grid shows {len(chunk)} numbered frames from a talking-to-camera video, in time order. "
                      "Score each frame 1-10 for how engaging it is to watch in a short-form video: "
                      "clear face looking at camera, expression, energy, gestures, action, good framing. "
                      "Low scores: blurry, looking away, empty frame, mid-blink, camera being set up. "
                      f'Reply as JSON {{"scores": [{len(chunk)} integers in frame order]}}.')
        try:
            s = ask(prompt, [_sheet([p for _, p in chunk])], VISUAL_SCHEMA)["scores"]
        except Exception:
            s = []
        s = (s + [5] * len(chunk))[:len(chunk)]
        out += [{"t": t, "v": max(1, min(10, int(v)))} for (t, _), v in zip(chunk, s)]
    cache.write_text(json.dumps(out))
    return out


HOOK_SCHEMA = {"type": "object", "properties": {"scores": {"type": "array", "items": {"type": "integer"}}},
               "required": ["scores"]}


def score_lines(lines: list[str], cache: Path) -> list[int]:
    # Whole transcript first, so off-topic chatter can be judged against the main topic.
    """1-10 per spoken line: would it stop a scroller / is it worth keeping."""
    if cache.exists():
        return json.loads(cache.read_text())
    out = []
    for i in range(0, len(lines), 25):
        chunk = lines[i:i + 25]
        listing = "\n".join(f"{j + 1}. {t}" for j, t in enumerate(chunk))
        prompt = ("Full transcript of a raw video, for context:\n" + " ".join(lines)[:3000] + "\n\n"
                  "First work out the video's main topic. Then score each numbered line below 1-10: "
                  "10 = strong hook or key point about the main topic (bold claim, number, surprising fact, clear value), "
                  "5 = useful but plain, "
                  "1-3 = off-topic side talk (food, people in the room, jokes unrelated to the topic), "
                  "filler, repeats, rambling or setup chatter.\n\n"
                  f"{listing}\n\nReply as JSON {{\"scores\": [{len(chunk)} integers in line order]}}.")
        try:
            s = ask(prompt, schema=HOOK_SCHEMA)["scores"]
        except Exception:
            s = []
        out += [max(1, min(10, int(v))) for v in (s + [5] * len(chunk))[:len(chunk)]]
    cache.write_text(json.dumps(out))
    return out
