"""Sound effects for the Remotion graphics, and a listen-back of a finished short.

The four WAVs in motion/public/sfx/ are rendered from earshot's sound bank (pure DSP,
offline, same bytes every time) instead of the ffmpeg-synthesised placeholders, and
every take is audited before it is kept. earshot also reads a finished video back, so
the editor can check its own sound instead of guessing.

    python -m tbncut.sfx build            # render motion/public/sfx/*.wav from motion/sfx-kit.json
    python -m tbncut.sfx check            # model-free audit of the four WAVs
    python -m tbncut.sfx listen <video>   # what earshot hears in a finished short (needs the models)

Needs earshot: ~/Documents/PROJECTS/earshot (EARSHOT or EARSHOT_PY to point elsewhere).
For real recorded sound and music on a client film, use the `real-sound` agent skill.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "motion" / "sfx-kit.json"
PACK = ROOT / "motion" / "public" / "sfx"
TAKES = Path.home() / ".ai-video-editor" / "sfx-takes"
EARSHOT = Path(os.environ.get("EARSHOT", Path.home() / "Documents/PROJECTS/earshot"))
# Hermes' PYTHONPATH hijacks the venv (numpy imports fail), so every call clears it.
ENV = {**os.environ, "PYTHONPATH": ""}
# earshot's shared role names -> the file names Composition.tsx plays.
FILES = {"tick": "tick", "pop": "pop", "hit": "impact", "whoosh.short": "whoosh"}
# What each sound is meant to be, for `earshot match` in `check --listen`.
MEANS = {"tick": "a soft quiet UI tick", "pop": "a short rounded UI pop",
         "impact": "a short deep impact hit", "whoosh": "a fast crisp air whoosh"}


def earshot_py() -> Path:
    py = Path(os.environ.get("EARSHOT_PY", EARSHOT / ".venv/bin/python"))
    if not py.exists():
        sys.exit(f"earshot not installed at {py}. Clone github.com/Leonxlnx/earshot and make its venv, "
                 "or set EARSHOT / EARSHOT_PY.")
    return py


def run(*args: str, json_out: bool = False):
    """One earshot call. Each CLI call reloads the models (~20-40 s); sfx/kit load none."""
    cmd = [str(earshot_py()), "-m", "earshot", *args]
    p = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    if p.returncode != 0:
        sys.exit(f"earshot {' '.join(args[:2])}: {(p.stderr or p.stdout).strip().splitlines()[-1]}")
    return json.loads(p.stdout) if json_out else p.stdout.strip()


def build(force: bool = False) -> dict:
    """Render the kit's takes, bake each role's level into its WAV, write PACK.json."""
    TAKES.mkdir(parents=True, exist_ok=True)
    PACK.mkdir(parents=True, exist_ok=True)
    print(run("kit", "check", str(KIT), "--out", str(TAKES)))
    print(run("kit", "render", str(KIT), "--out", str(TAKES), *(["--force"] if force else [])))
    lock = json.loads((TAKES / "kit.lock.json").read_text())
    pack = {"source": "earshot kit", "kit": KIT.name, "earshot": lock.get("earshot"),
            "bank": lock.get("bank"), "sounds": {}}
    for role, spec in lock["roles"].items():
        if not spec:
            continue
        take = spec["takes"][0]
        name = FILES.get(role, role.replace(".", "-"))
        src, dest = TAKES / take["file"], PACK / f"{name}.wav"
        level = spec.get("level_db", 0.0)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src),
                        # 16-bit 48k stereo: the format the Remotion renderer has always been given.
                        "-filter:a", f"volume={level}dB", "-c:a", "pcm_s16le", str(dest)], check=True)
        pack["sounds"][name] = {"role": role, "id": spec["sound"], "level_db": level, "align": spec.get("align"),
                                "take": take["file"], "seed": take.get("seed"),
                                "onset_s": take.get("onset_s"), "peak_s": take.get("peak_s"),
                                "dur_s": take.get("dur_s"), "lufs_m_max": take.get("lufs_m_max"),
                                "checks": take.get("checks", [])}
        print(f"  {name}.wav  <- {spec['sound']}  {level:+.1f} dB  {take.get('dur_s')}s")
    (PACK / "PACK.json").write_text(json.dumps(pack, indent=2) + "\n")
    print(f"{len(pack['sounds'])} sound(s) in {PACK}")
    return pack


def check(listen: bool = False) -> int:
    """The model-free audit of every WAV in the pack; --listen also asks what it sounds like."""
    bad = 0
    for wav in sorted(PACK.glob("*.wav")):
        out = run("sfx", "check", str(wav))
        first = out.splitlines()[0] if out else ""
        flag = "FAIL" if ("fail" in out.lower() or "clipping" in out.lower()) else "ok"
        bad += flag == "FAIL"
        print(f"{wav.name:12s} {flag}  {first}")
        if listen and wav.stem in MEANS:
            print(f"             match: {run('match', str(wav), MEANS[wav.stem]).splitlines()[0]}")
            print(f"             real?: {run('realness', str(wav)).splitlines()[0]}")
    return 1 if bad else 0


def listen(video: Path, sheet: bool = False) -> None:
    """What earshot hears in a finished short: events, sync to the cuts, loudness."""
    print(run("timeline", str(video), "--video", str(video)))
    if sheet:
        png = video.with_name(video.stem + " - earshot.png")
        run("sheet", str(video), "-o", str(png))
        print(f"sheet -> {png}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tbncut.sfx", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="render the pack from the kit")
    b.add_argument("--force", action="store_true", help="re-render every take")
    c = sub.add_parser("check", help="audit the pack")
    c.add_argument("--listen", action="store_true", help="also ask earshot what each sound is (loads the models)")
    l = sub.add_parser("listen", help="read a finished video's sound back")
    l.add_argument("video", type=Path)
    l.add_argument("--sheet", action="store_true", help="also write an annotated PNG")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        build(a.force)
    elif a.cmd == "check":
        return check(a.listen)
    else:
        listen(a.video, a.sheet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
