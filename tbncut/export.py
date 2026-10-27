"""Other sizes from a finished vertical video.

    python -m tbncut.export <video.mp4> [16x9] [4x5] [1x1]

16x9: the vertical video centred over a blurred, darkened copy of itself (YouTube, LinkedIn).
4x5 / 1x1: a centre crop that keeps the middle of the frame (Instagram feed).
"""
import subprocess
import sys
from pathlib import Path

FILTERS = {
    "16x9": "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,boxblur=30:3,eq=brightness=-0.18[bg];"
            "[0:v]scale=-2:1080[fg];[bg][fg]overlay=(W-w)/2:0",
    "4x5": "crop=1080:1350:0:(ih-1350)*0.45",
    "1x1": "crop=1080:1080:0:(ih-1080)*0.45",
}


def export(video: Path, fmt: str) -> Path:
    out = video.with_name(f"{video.stem} [{fmt}].mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-filter_complex" if fmt == "16x9" else "-vf", FILTERS[fmt],
                    "-c:v", "h264_videotoolbox", "-b:v", "10M", "-c:a", "copy", "-movflags", "+faststart", str(out)], check=True)
    return out


if __name__ == "__main__":
    v = Path(sys.argv[1]).expanduser().resolve()
    for f in sys.argv[2:] or ["16x9", "4x5", "1x1"]:
        print(export(v, f))
