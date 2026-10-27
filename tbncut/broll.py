"""B-roll: clips with no one talking become short cutaways over the talking parts.

Gemma rates each silent clip's frames for how good they look as B-roll; the best
window of each clip is cut to a silent 9:16 piece and placed between graphics.
"""
import json
import subprocess
from pathlib import Path

from . import gemma


def pick_moments(videos: list[Path], out_dir: Path, length: float, max_clips: int = 12) -> list[dict]:
    """Best window per silent clip: [{"video", "t", "score"}], best first.
    Big folders: score an even spread of max_clips clips (each scored clip is cached for next time)."""
    if len(videos) > max_clips:
        step = len(videos) / max_clips
        videos = [videos[int(i * step)] for i in range(max_clips)]
    out = []
    for v in videos:
        shared = out_dir / v.stem
        shared.mkdir(parents=True, exist_ok=True)
        scores = gemma.score_frames(v, shared, shared / "broll_scores.json", kind="broll")
        if not scores:
            continue
        best = max(scores, key=lambda x: x["v"])
        out.append({"video": str(v), "t": max(0.0, best["t"] - length / 2), "score": best["v"]})
    return sorted([m for m in out if m["score"] >= 5], key=lambda m: -m["score"])


def cut_pieces(moments: list[dict], work: Path, length: float, W: int = 1080, H: int = 1920) -> list[Path]:
    """Silent vertical pieces, centre-cropped, cached in the work folder."""
    files = []
    for k, m in enumerate(moments):
        f = work / f"broll_{k}.mp4"
        if not f.exists():
            r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{m['t']:.2f}", "-t", f"{length + 0.3:.2f}", "-i", m["video"],
                                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,setsar=1",
                                "-an", "-c:v", "h264_videotoolbox", "-b:v", "8M", str(f)])
            if r.returncode != 0:
                continue
        files.append(f)
    return files


def place(beats: list[dict], total: float, pieces: list[Path], tpl: dict) -> list[dict]:
    """Drop B-roll into gaps between graphics, every `every` seconds, never over the opening."""
    cfg = tpl.get("broll", {})
    if not pieces or not cfg.get("on", True):
        return beats
    every, length = cfg.get("every", 8.0), cfg.get("length", 2.2)
    busy = [(b["s"] - 0.4, b["e"] + 0.4) for b in beats]
    out, t, k = list(beats), 3.5, 0
    while t + length < total - 1.0:
        if not any(s < t + length and e > t for s, e in busy):
            out.append({"type": "broll", "s": round(t, 2), "e": round(t + length, 2), "text": "",
                        "src": pieces[k % len(pieces)].name})
            busy.append((t - 0.4, t + length + 0.4))
            k += 1
            t += every
        else:
            t += 0.5
    return sorted(out, key=lambda b: b["s"])


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def find_screens(folders: list[Path]) -> list[Path]:
    """Screenshots dropped next to the videos (or in a screens/ folder). Covers we made are skipped."""
    out = []
    for f in folders:
        for d in (f, f / "screens"):
            if d.is_dir():
                out += [p for p in sorted(d.iterdir()) if p.suffix.lower() in IMAGE_EXT and not p.name.startswith(".")
                        and " - " not in p.stem]
    return list(dict.fromkeys(out))


def place_screens(beats: list[dict], words: list[dict], screens: list[Path], work: Path, gap: float = 3.0) -> list[dict]:
    """A screenshot pops in when its name is said (worktick-dashboard.png -> "dashboard")."""
    import re
    import shutil
    out = list(beats)
    for k, img in enumerate(screens):
        tokens = [t for t in re.split(r"[^a-z0-9]+", img.stem.lower()) if len(t) >= 4]
        hit = next((w for w in words if any(re.sub(r"[^a-z0-9]", "", w["w"].lower()).startswith(t[:6]) for t in tokens)), None)
        if not hit:
            continue
        s = hit["s"]
        if any(b["s"] - gap < s < b["e"] + gap and b["type"] != "broll" for b in out):
            # make room: the screen wins over a keyword pop, otherwise skip
            clash = [b for b in out if b["s"] - gap < s < b["e"] + gap and b["type"] == "keyword" and b.get("fill")]
            if not clash:
                continue
            out = [b for b in out if b not in clash]
        name = f"screen_{k}{img.suffix.lower()}"
        shutil.copyfile(img, work / name)
        label = " ".join(t for t in re.split(r"[^A-Za-z0-9]+", img.stem) if t)
        out.append({"type": "screen", "s": round(s, 2), "e": round(s + 2.8, 2), "text": label, "src": name})
    return sorted(out, key=lambda b: b["s"])
