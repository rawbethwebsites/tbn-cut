"""Cover image for a finished short: the sharpest, best-lit frame (a face if there is one) + the title.

    python -m tbncut.thumbnail <video> "<title>" <out.jpg> [--accent #EA6113]
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
YUNET = Path.home() / ".ai-video-editor/models/yunet.onnx"
W, H = 1080, 1920


def best_frame(video: Path, samples: int = 24) -> np.ndarray:
    cap = cv2.VideoCapture(str(video))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    best, best_score = None, -1.0
    for i in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (i + 0.5) / samples))
        ok, f = cap.read()
        if not ok:
            continue
        g = cv2.cvtColor(cv2.resize(f, (270, 480)), cv2.COLOR_BGR2GRAY)
        sharp = cv2.Laplacian(g, cv2.CV_64F).var()
        light = 1 - abs(g.mean() - 128) / 128
        face = 0.0
        if YUNET.exists():
            det = cv2.FaceDetectorYN.create(str(YUNET), "", (270, 480), 0.7)
            _, faces = det.detect(cv2.resize(f, (270, 480)))
            face = 1.0 if faces is not None and len(faces) else 0.0
        score = min(sharp, 600) / 600 + light + 1.5 * face
        if score > best_score:
            best, best_score = f, score
    cap.release()
    return best


def make_cover(video: Path, title: str, out: Path, accent: str = "#EA6113") -> Path:
    f = best_frame(video)
    img = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)).convert("RGB")
    s = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * s), int(img.height * s)))
    img = img.crop(((img.width - W) // 2, (img.height - H) // 2, (img.width - W) // 2 + W, (img.height - H) // 2 + H))
    # darken the bottom 45% so the title reads
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        grad.putpixel((0, y), int(max(0, (y - H * 0.55) / (H * 0.45)) * 190))
    img = Image.composite(Image.new("RGB", (W, H), "black"), img, grad.resize((W, H)))
    words = title.upper().split()
    size = 120
    while size > 60:
        font = ImageFont.truetype(FONT, size)
        lines, cur = [], []
        for w in words:
            if cur and font.getlength(" ".join(cur + [w])) > 940:
                lines.append(cur)
                cur = []
            cur.append(w)
        if cur:
            lines.append(cur)
        if len(lines) <= 3:
            break
        size -= 8
    lh = int(size * 1.08)
    y0 = H - 260 - lh * len(lines)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds, dt = ImageDraw.Draw(shadow), ImageDraw.Draw(text)
    dt.rectangle([70, y0 - 40, 70 + 140, y0 - 28], fill=accent)
    for li, line in enumerate(lines):
        x, y = 70, y0 + li * lh
        for wi, w in enumerate(line):
            last = li == len(lines) - 1 and wi == len(line) - 1
            ds.text((x + 4, y + 6), w, font=font, fill=(0, 0, 0, 200))
            dt.text((x, y), w, font=font, fill=accent if last else "white")
            x += font.getlength(w + " ")
    img = Image.alpha_composite(img.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(6)))
    img = Image.alpha_composite(img, text).convert("RGB")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=90)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("title")
    ap.add_argument("out")
    ap.add_argument("--accent", default="#EA6113")
    a = ap.parse_args()
    print(make_cover(Path(a.video), a.title, Path(a.out), a.accent))
