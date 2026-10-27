"""Steps 4-6: pick the phrases, cut + crop with ffmpeg, burn captions.

Everything here is plain rules driven by the template, so the same input and
template always give the same edit.
"""
import json
import subprocess
from pathlib import Path

import os
os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
import cv2
from PIL import Image, ImageDraw, ImageFont

FONTS = {
    "arial-black": "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "impact": "/System/Library/Fonts/Supplemental/Impact.ttf",
    "futura": "/System/Library/Fonts/Supplemental/Futura.ttc",
    "avenir": "/System/Library/Fonts/Avenir Next.ttc",
    "sf": "/System/Library/Fonts/SFNS.ttf",
}
YUNET = Path.home() / ".ai-video-editor/models/yunet.onnx"


def probe(video: Path) -> dict:
    d = json.loads(subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams",
                                   "-show_format", str(video)], capture_output=True, text=True).stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    w, h = int(v["width"]), int(v["height"])
    rot = int((v.get("side_data_list") or [{}])[0].get("rotation", 0) or 0)
    if abs(rot) == 90:
        w, h = h, w
    num, den = v.get("avg_frame_rate", "30/1").split("/")
    return {"w": w, "h": h, "dur": float(d["format"]["duration"]), "fps": float(num) / float(den or 1)}


# ---------- pick ----------

def score(ps: list[dict], line_scores: list[int], visual: list[dict]) -> list[dict]:
    """Attach line, visual and combined scores to the kept phrases; returns them."""
    kept = [p for p in ps if "dropped" not in p]
    for p, s in zip(kept, line_scores):
        vis = [x["v"] for x in visual if p["cs"] - 1 <= x["t"] <= p["ce"] + 1] or [5]
        p["line"] = s
        p["vis"] = round(sum(vis) / len(vis), 1)
        p["score"] = round(0.65 * s + 0.35 * p["vis"], 2)
    return kept


def pick(ps: list[dict], line_scores: list[int], visual: list[dict], tpl: dict) -> list[dict]:
    return select(score(ps, line_scores, visual), tpl)


def select(kept: list[dict], tpl: dict) -> list[dict]:
    """Fit the template length: weakest lines go first, story order kept (clip by clip when mixing)."""
    limit = tpl["max_seconds"]
    floor = tpl.get("min_line_score", 0)
    chosen = [p for p in kept if p["line"] >= floor] or list(kept)
    # Too long: drop the weakest lines first, keep the story in order.
    while sum(p["ce"] - p["cs"] for p in chosen) > limit and len(chosen) > 1:
        chosen.remove(min(chosen, key=lambda p: p["score"]))
    chosen.sort(key=lambda p: (p.get("src", 0), p["cs"]))
    if tpl.get("hook_first") and len(chosen) > 2:
        hook_max = tpl.get("hook_max_seconds", 6)
        cands = [p for p in kept if p["ce"] - p["cs"] <= hook_max and p["line"] >= 8]
        if cands:
            hook = max(cands, key=lambda p: p["score"])
            chosen = [hook] + [p for p in chosen if p is not hook]
    return chosen


# ---------- crop ----------

def face_x(video: Path, info: dict, samples: int = 24) -> float:
    return face_box(video, info, samples)[0]


def face_x_at(video: Path, t0: float, t1: float, default: float, samples: int = 3) -> float:
    """Face centre x (0-1) inside one cut, so the crop follows a speaker who moves between cuts."""
    if not YUNET.exists():
        return default
    cap = cv2.VideoCapture(str(video))
    xs = []
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_MSEC, 1000 * (t0 + (t1 - t0) * (i + 0.5) / samples))
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        sc = 640 / max(w, h)
        small = cv2.resize(frame, (int(w * sc), int(h * sc)))
        det = cv2.FaceDetectorYN.create(str(YUNET), "", (small.shape[1], small.shape[0]), 0.7)
        _, faces = det.detect(small)
        if faces is not None and len(faces):
            f = max(faces, key=lambda f: f[2] * f[3])
            xs.append(float((f[0] + f[2] / 2) / small.shape[1]))
    cap.release()
    return sorted(xs)[len(xs) // 2] if xs else default


def face_box(video: Path, info: dict, samples: int = 24) -> tuple[float, float, float]:
    """Median face centre x, top y and bottom y (0-1 of the source) so crops and captions avoid it."""
    if not YUNET.exists():
        return 0.5, 0.3, 0.6
    cap = cv2.VideoCapture(str(video))
    xs, tops, bots = [], [], []
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_MSEC, info["dur"] * 1000 * (i + 0.5) / samples)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = 640 / max(w, h)
        small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        det = cv2.FaceDetectorYN.create(str(YUNET), "", (small.shape[1], small.shape[0]), 0.7)
        _, faces = det.detect(small)
        if faces is not None and len(faces):
            f = max(faces, key=lambda f: f[2] * f[3])
            xs.append((f[0] + f[2] / 2) / small.shape[1])
            tops.append(f[1] / small.shape[0])
            bots.append((f[1] + f[3]) / small.shape[0])
    cap.release()
    med = lambda v, d: sorted(v)[len(v) // 2] if v else d
    return float(med(xs, 0.5)), float(med(tops, 0.3)), float(med(bots, 0.6))


# ---------- captions ----------

def caption_chunks(chosen: list[dict], n: int) -> list[dict]:
    """Words mapped onto the output timeline, grouped n at a time."""
    out, t0 = [], 0.0
    for p in chosen:
        words = [{**w, "s": w["s"] - p["cs"] + t0, "e": w["e"] - p["cs"] + t0} for w in p["words"]]
        for i in range(0, len(words), n):
            g = words[i:i + n]
            out.append({"words": g, "s": g[0]["s"], "e": g[-1]["e"]})
        t0 += p["ce"] - p["cs"]
    for a, b in zip(out, out[1:]):
        a["e"] = b["s"]  # hold each caption until the next one
    return out


def _draw(text_words: list[str], active: int, cap: dict, size: tuple[int, int]) -> Image.Image:
    W, H = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONTS.get(cap["font"], FONTS["arial-black"]), cap["size"])
    words = [w.upper() if cap.get("uppercase") else w for w in text_words]
    space = d.textlength(" ", font=font)
    widths = [d.textlength(w, font=font) for w in words]
    # wrap to max 85% width
    lines, cur, cw = [], [], 0
    for i, wd in enumerate(widths):
        if cur and cw + space + wd > W * 0.85:
            lines.append(cur); cur, cw = [], 0
        cur.append(i); cw += (space if len(cur) > 1 else 0) + wd
    if cur:
        lines.append(cur)
    lh = int(cap["size"] * 1.15)
    y = int(H * cap["y"]) - lh * len(lines) // 2
    for line in lines:
        lw = sum(widths[i] for i in line) + space * (len(line) - 1)
        x = (W - lw) / 2
        for i in line:
            color = cap["highlight"] if i == active and cap.get("highlight") else cap["color"]
            d.text((x, y), words[i], font=font, fill=color, stroke_width=cap.get("outline", 6),
                   stroke_fill=cap.get("outline_color", "black"))
            x += widths[i] + space
        y += lh
    return img


def caption_track(chunks: list[dict], cap: dict, size: tuple[int, int], total: float, work: Path) -> Path:
    """One PNG per caption state, joined with exact durations into an alpha video."""
    d = work / "captions"
    d.mkdir(parents=True, exist_ok=True)
    blank = d / "blank.png"
    Image.new("RGBA", size, (0, 0, 0, 0)).save(blank)
    entries, t, k = [], 0.0, 0
    for c in chunks:
        if c["s"] > t + 0.01:
            entries.append((blank, c["s"] - t)); t = c["s"]
        texts = [w["w"] for w in c["words"]]
        if cap.get("highlight"):
            for i, w in enumerate(c["words"]):
                end = c["words"][i + 1]["s"] if i + 1 < len(c["words"]) else c["e"]
                f = d / f"c{k:05d}.png"; k += 1
                _draw(texts, i, cap, size).save(f)
                entries.append((f, max(0.04, end - t))); t = end
        else:
            f = d / f"c{k:05d}.png"; k += 1
            _draw(texts, -1, cap, size).save(f)
            entries.append((f, max(0.04, c["e"] - t))); t = c["e"]
    if total > t:
        entries.append((blank, total - t))
    lst = d / "list.txt"
    lst.write_text("".join(f"file '{f}'\nduration {dur:.3f}\n" for f, dur in entries) + f"file '{entries[-1][0]}'\n")
    out = work / "captions.mov"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", "fps=30,format=argb", "-c:v", "qtrle", str(out)], check=True)
    return out


# ---------- render ----------

def _geometry(video: Path, W: int, H: int) -> dict:
    """9:16 crop around the speaker's face, plus the face band in the finished frame."""
    info = probe(video)
    fx, ftop, fbot = face_box(video, info)
    cw = min(info["w"], int(info["h"] * W / H))
    ch = int(cw * H / W)
    cx = int(min(max(fx * info["w"] - cw / 2, 0), info["w"] - cw))
    cy = (info["h"] - ch) // 2
    return {"cw": cw, "ch": ch, "cx": cx, "cy": cy, "fx": fx, "w": info["w"], "h": info["h"],
            "top": max(0.0, (ftop * info["h"] - cy) / ch - 0.04),
            "bottom": min(1.0, (fbot * info["h"] - cy) / ch + 0.10)}


def render(video, chosen: list[dict], tpl: dict, work: Path, out: Path) -> Path:
    """video: one path, or a list when mixing clips (each phrase's "src" picks its clip)."""
    videos = video if isinstance(video, list) else [video]
    W, H = tpl.get("width", 1080), tpl.get("height", 1920)
    used = sorted({p.get("src", 0) for p in chosen})
    geo = {k: _geometry(videos[k], W, H) for k in used}
    has_audio = {k: bool(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                                         "-of", "csv=p=0", str(videos[k])], capture_output=True, text=True).stdout.strip())
                 for k in used}
    # Captions keep clear of the face in every clip used.
    (work / "face.json").write_text(json.dumps({
        "top": round(min(g["top"] for g in geo.values()), 3),
        "bottom": round(max(g["bottom"] for g in geo.values()), 3)}))
    zoom = tpl.get("zoom", {})
    parts, labels = [], []
    for i, p in enumerate(chosen):
        k = p.get("src", 0)
        cw, ch, cx, cy = geo[k]["cw"], geo[k]["ch"], geo[k]["cx"], geo[k]["cy"]
        if tpl.get("track_face", True) and geo[k]["w"] > cw + 8:  # wider than 9:16: follow the face cut by cut
            fx = face_x_at(videos[k], p["cs"], p["ce"], geo[k]["fx"])
            cx = int(min(max(fx * geo[k]["w"] - cw / 2, 0), geo[k]["w"] - cw))
        if zoom.get("cycle"):  # punchy styles: a different zoom on every cut
            cyc = zoom["cycle"] or [1.0]
            z = cyc[i % len(cyc)]
        else:
            z = zoom.get("amount", 1.0) if zoom.get("alternate") and i % 2 == 1 else 1.0
        f = p.get("focus")  # workout: where the movement is (workout.action_box)
        if f:
            z = max(z, f["z"])
        zw, zh = int(cw / z) // 2 * 2, int(ch / z) // 2 * 2
        zx = cx + (cw - zw) // 2
        zy = cy + int((ch - zh) * 0.35)  # zoom towards the face, not the chin
        if f:
            zx = int(min(max(f["x"] * geo[k]["w"] - zw / 2, cx), cx + cw - zw))
            zy = int(min(max(f["y"] * geo[k]["h"] - zh / 2, cy), cy + ch - zh))
        sp = p.get("speed", 1.0)  # 0.5 = slow-motion replay (video only; audio becomes silence)
        parts.append(f"[{k}:v]trim={p['cs']:.3f}:{p['ce']:.3f},setpts=(PTS-STARTPTS)/{sp},"
                     f"crop={zw}:{zh}:{zx}:{zy},scale={W}:{H},setsar=1,fps=30[v{i}];"
                     + (f"[{k}:a]atrim={p['cs']:.3f}:{p['ce']:.3f},asetpts=PTS-STARTPTS,"
                        f"aresample=48000,aformat=channel_layouts=stereo[a{i}];" if has_audio[k] and sp == 1.0 else
                        # clip has no sound at all (some DJI gym clips): silence of the same length
                        f"anullsrc=r=48000:cl=stereo,atrim=0:{(p['ce'] - p['cs']) / sp:.3f}[a{i}];"))
        labels.append(f"[v{i}][a{i}]")
    total = sum((p["ce"] - p["cs"]) / p.get("speed", 1.0) for p in chosen)
    graph = "".join(parts) + "".join(labels) + f"concat=n={len(chosen)}:v=1:a=1[vc][ac];"
    inputs = [x for v in videos for x in ("-i", str(v))]
    if tpl.get("captions", {}).get("on", True):
        cap_mov = caption_track(caption_chunks(chosen, tpl["captions"]["words"]), tpl["captions"], (W, H), total, work)
        inputs += ["-i", str(cap_mov)]
        graph += f"[vc][{len(videos)}:v]overlay=0:0:shortest=1[vo];"
    else:
        graph += "[vc]null[vo];"
    # Voice cleanup (gym rooms are noisy): rumble cut, gentle denoise, light compression. Off with audio.clean=false.
    clean = "highpass=f=80,afftdn=nf=-25,acompressor=threshold=-18dB:ratio=3:attack=5:release=80," if tpl.get("audio", {}).get("clean", True) else ""
    graph += f"[ac]{clean}loudnorm=I=-14:TP=-1.5:LRA=11[ao]"
    (work / "graph.txt").write_text(graph)
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-/filter_complex", str(work / "graph.txt"),
                    "-map", "[vo]", "-map", "[ao]", "-c:v", "h264_videotoolbox", "-b:v", "10M",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)], check=True)
    return out
