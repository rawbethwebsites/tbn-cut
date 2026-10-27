"""Script to video: text in, a voiced motion-graphics explainer out. No camera, no footage.

    python -m tbncut.script script.txt [--voice default] [--series "TBN"] [--episode "EP 01"] [--out output/scripts]

1. VoiceStudio (local, free) reads the script, one sentence at a time.
2. Whisper times every word of that voice, so captions and scenes land on the words.
3. The explainer planner (model, or word rules if the models are busy) designs the scenes.
4. Remotion renders the TBNExplainer composition.
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import explainer, motion, transcribe

VOICESTUDIO = "http://127.0.0.1:3900/v1/audio/speech"
ROOT = Path(__file__).resolve().parent.parent


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def speak(text: str, out: Path, voice: str = "default", speed: float = 1.0) -> Path:
    if out.exists():
        return out
    body = {"model": "omnivoice", "input": text, "voice": voice, "response_format": "wav", "language": "English",
            "num_step": 32, "speed": speed}
    req = urllib.request.Request(VOICESTUDIO, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        out.write_bytes(r.read())
    return out


def voice_track(script: str, work: Path, voice: str) -> Path:
    """One clip per script line, so the sentences inside a line flow together (Rob 19 Oct: one clip per sentence
    sounded choppy). Lines over 300 characters fall back to one clip per sentence. Joined with small breaths."""
    sents = []
    for line in (l.strip() for l in script.splitlines() if l.strip()):
        sents += [line] if len(line) <= 300 else [s for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    parts = []
    for i, s in enumerate(sents):
        log(f"voice {i + 1}/{len(sents)}: {s[:60]}")
        parts.append(speak(s, work / f"line_{i:03d}.wav", voice))
    lst = work / "voice.txt"
    gap = work / "gap.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "0.28", str(gap)], check=True)
    lst.write_text("".join(f"file '{p}'\nfile '{gap}'\n" for p in parts))
    out = work / "voice.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-ar", "48000", "-ac", "2",
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", str(out)], check=True)
    return out


def make(script_path: Path, voice: str, series: str, episode: str, out_dir: Path, accent: str = "#D7141A", cta: str = "", music: str = "", brand: str = "", captions: str = "tbn-house", motion_name: str = "") -> Path:
    script = script_path.read_text().strip()
    work = out_dir / script_path.stem
    work.mkdir(parents=True, exist_ok=True)
    voice_wav = voice_track(script, work, voice)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(voice_wav)],
                               capture_output=True, text=True).stdout)
    # A plain dark "video" carrying the voice: the explainer covers every frame with scenes anyway.
    cut = work / "cut.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x141414:s=1080x1920:r=30:d={dur:.2f}",
                    "-i", str(voice_wav), "-shortest", "-c:v", "h264_videotoolbox", "-b:v", "2M", "-c:a", "aac", "-b:a", "192k", str(cut)], check=True)
    log("timing every word")
    words = transcribe.transcribe(voice_wav, work / "words.json")
    # We know exactly what was said: when the word counts match, the script's own words replace Whisper's guesses.
    said = script.split()
    if len(said) == len(words):
        words = [{**w, "w": t} for w, t in zip(words, said)]
    else:
        log(f"script has {len(said)} words, Whisper heard {len(words)}: captions use Whisper's words")
    # Units: script sentences, timed by the voice's words (split long ones like the explainer does).
    us, cur = [], []
    for w in words:
        cur.append({"w": w["w"], "s": w["s"], "e": w["e"]})
        if re.search(r"[.!?]$", w["w"]):
            us.append(cur)
            cur = []
    if cur:
        us.append(cur)
    units = [{"sent": i, "s": u[0]["s"], "e": u[-1]["e"], "words": u, "text": " ".join(x["w"] for x in u)} for i, u in enumerate(us)]
    tpl = {"max_seconds": 999, "explainer": {"series": series, "episode": episode, "cta": cta or "SAVE THIS"}}
    explainer.KEYWORDS["value"] = motion.line_keywords([{"text": u["text"]} for u in units], work / "keywords.json")
    raw = explainer.plan(units, tpl, work / "scenes_raw.json")
    if not raw:
        log("no model answered for scenes, using word rules")
        raw = explainer.rule_plan(units, explainer.KEYWORDS["value"] or [])
    scenes = explainer.validate(raw, units, tpl)
    if cta and scenes:
        scenes[-1]["cta"] = cta  # a call to action set by hand beats the planner's
    for sc in scenes:
        if sc["kind"] == "hook":
            sc["kind"] = "statement"  # no footage to blur behind a hook
    log(f"{len(scenes)} scenes: " + ", ".join(s["kind"] for s in scenes))
    explainer.add_images(scenes, work, log)
    props = {"video": "", "fps": 30, "durationInFrames": int(round(dur * 30)), "words": [w for u in units for w in u["words"]],
             "scenes": scenes, "series": series, "episode": episode, "handle": "@rawbeth", "accent": accent, "sfx": True, "beats": []}
    if captions != "box":  # Rob's locked caption look (big caps, hero word, spoken word coloured), from that template
        props["captionStyle"] = json.loads((ROOT / "templates" / f"{captions}.json").read_text())["style"]
    if brand:  # brand colours + logo: templates/brand-<name>.json
        b = json.loads((ROOT / "templates" / f"brand-{brand}.json").read_text())
        props.update(accent=b["accent"], palette=b["palette"], logoOnDark=b["logo_on_dark"], logoOnCream=b["logo_on_cream"])
    # motion template from the library (templates/motion); "auto" lets Gemma pick one for this script
    from tbncut import motionlib
    if not motion_name:  # Rob, 19 Oct 2026: the cdsigrl.org motion is the locked look for TBN-branded videos
        motion_name = "cds-os" if brand == "tbn" else "classic"
    if motion_name == "auto":
        motion_name = motionlib.pick(script)
        log(f"gemma picked the {motion_name!r} motion template")
    props["motion"] = motionlib.load(motion_name)
    (work / "props.json").write_text(json.dumps(props))
    final = out_dir / f"{script_path.stem} - script video.mp4"
    (work / "render.json").write_text(json.dumps({"cut": str(cut), "out": str(final), "composition": "TBNExplainer",
                                                      "music": motion._music({"style": {"music": music}}, cut, work)}))
    motion.render_props(work)
    log(f"done -> {final.name}")
    return final


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("--voice", default="default", help="VoiceStudio voice or profile id (default: the neutral default voice)")
    ap.add_argument("--series", default="THE BOOST NATION")
    ap.add_argument("--episode", default="")
    ap.add_argument("--accent", default="#D7141A")
    ap.add_argument("--cta", default="", help="end-card call to action, e.g. 'DM ME \"CUT\"' (default: SAVE THIS)")
    ap.add_argument("--music", default="", help="bed under the voice: 'beat' (generated, free) or a path to a track")
    ap.add_argument("--brand", default="", help="brand look from templates/brand-<name>.json (colours + animated logo), e.g. tbn")
    ap.add_argument("--captions", default="tbn-house", help="caption look: a template slug (its locked caption style) or 'box' for the small boxed captions")
    ap.add_argument("--motion", default="", help="motion template from templates/motion, or 'auto' to let Gemma pick (default: cds-os with --brand tbn, else classic)")
    ap.add_argument("--out", default=str(ROOT / "output" / "scripts"))
    a = ap.parse_args()
    try:
        make(Path(a.script).expanduser().resolve(), a.voice, a.series, a.episode, Path(a.out).expanduser().resolve(), a.accent, a.cta, a.music, a.brand, a.captions, a.motion)
    except Exception as e:
        log(f"FAILED {e}")
        sys.exit(1)
