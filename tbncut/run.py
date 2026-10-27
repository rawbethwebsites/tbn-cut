"""TBN Cut: folder of raw videos + template -> finished vertical shorts.

    python -m tbncut.run <folder> --template tbn-house [--out <dir>] [--only <name>]

Every step is cached in <out>/<video>/ so a re-run only redoes what changed.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

from . import broll, edit, gemma, motion, story, transcribe

ROOT = Path(__file__).resolve().parent.parent
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv"}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_template(name: str) -> dict:
    p = Path(name)
    if not p.exists():
        p = ROOT / "templates" / f"{name}.json"
    return json.loads(p.read_text())


MIN_SECONDS, MIN_WORDS = 3.0, 15


DURATIONS: dict[str, float] = {}  # probed once up front, so a drive unplugged mid-run can't break the report


class Skip(Exception):
    """A clip we can't make a talking short from (too short, or no one talking)."""


def _slug(tpl: dict) -> str:
    return re.sub(r"[^a-z0-9]+", "-", tpl["name"].lower()).strip("-") + tpl.get("_variant", "")


def _sentences(video: Path, k: int, tpl: dict, out_dir: Path) -> list[dict]:
    """Transcribe and score one clip; returns its sentences (dropped ones marked)."""
    dur = edit.probe(video)["dur"]
    DURATIONS[str(video)] = dur
    if dur < MIN_SECONDS:
        raise Skip(f"only {dur:.1f}s long")
    shared = out_dir / video.stem
    work_k = shared / _slug(tpl)
    work_k.mkdir(parents=True, exist_ok=True)
    log(f"{video.name}: transcribing")
    words = transcribe.transcribe(video, shared / "words.json")
    if len(words) < MIN_WORDS:
        raise Skip(f"no one talking ({len(words)} words), kept for B-roll later")
    sents = story.sentences(words)
    kept = [s for s in sents if "dropped" not in s]
    log(f"{video.name}: {len(words)} words, {len(kept)}/{len(sents)} sentences usable; Gemma scoring lines and frames")
    line_scores = gemma.score_lines([s["text"] for s in kept], work_k / "sentence_scores.json")
    visual = gemma.score_frames(video, shared, shared / "visual_scores.json")
    for s in sents:
        s["src"] = k
        s["cs"], s["ce"] = s["s"], s["e"]
    edit.score(sents, line_scores, visual)  # adds line / vis / score to the kept ones
    return sents


def edit_clips(videos: list[Path], tpl: dict, out_dir: Path, work: Path, final_path: Path,
               broll_clips: list[Path] | None = None, choice: dict | None = None, pool_in: list[dict] | None = None) -> dict:
    """Whole-sentence edit of one clip, or a mix of several (the editor model builds one story).
    Clips with no one talking become B-roll instead of being dropped."""
    pool, every, skipped = [], [], []
    broll_clips = list(broll_clips or [])
    for k, v in enumerate(videos if pool_in is None else []):
        try:
            sents = _sentences(v, k, tpl, out_dir)
        except Skip as e:
            if len(videos) == 1:
                raise
            if "no one talking" in str(e):
                log(f"{v.name}: no one talking, using it as B-roll")
                broll_clips.append(v)
            else:
                log(f"{v.name}: SKIPPED {e}")
            skipped.append(v.name)
            continue
        every += sents
        pool += [s for s in sents if "dropped" not in s]
    if pool_in is not None:  # several shorts from one video: sentences and choice already made
        pool = every = pool_in
    if not pool:
        raise Skip("no clip has anyone talking")
    work.mkdir(parents=True, exist_ok=True)
    if choice is None:
        log(f"editor (Qwen) choosing the story from {len(pool)} sentences")
        choice = story.choose(pool, tpl, work / "story.json", clip_names=[v.name for v in videos] if len(videos) > 1 else None)
    chosen_sents = story.assemble(pool, choice, tpl)
    chosen = story.to_parts(chosen_sents, tpl)
    total = sum(p["ce"] - p["cs"] for p in chosen)
    cuts_n = len(chosen)
    log(f"story: {len(chosen_sents)} sentences, {cuts_n} cuts, {total:.1f}s (topic: {choice.get('topic', '')[:80]}); rendering")
    pieces = []
    if broll_clips and tpl.get("broll", {}).get("on", True) and tpl.get("renderer") == "remotion":
        length = tpl.get("broll", {}).get("length", 2.2)
        log(f"B-roll: Gemma picking the best moments from {len(broll_clips)} silent clips")
        moments = broll.pick_moments(broll_clips, out_dir, length)
        need = max(1, int(total / tpl.get("broll", {}).get("every", 8.0)) + 1)
        pieces = broll.cut_pieces(moments[:need], work, length)
        log(f"B-roll: {len(pieces)} pieces ready")
    if tpl.get("renderer") == "remotion":
        cut = edit.render(videos, chosen, {**tpl, "captions": {"on": False}}, work, work / "cut.mp4")
        log("planning motion graphics and rendering with Remotion")
        screens = broll.find_screens(sorted({v.parent for v in videos}))
        if screens:
            log(f"screens: {len(screens)} screenshots found; they pop in when their name is said")
        final = motion.render(cut, chosen, tpl, work, final_path, pieces, screens)
    else:
        final = edit.render(videos, chosen, tpl, work, final_path)
    report = {
        "videos": [str(v) for v in videos], "template": tpl["name"], "output": str(final), "seconds": round(total, 1),
        "source_seconds": round(sum(DURATIONS.get(str(v), 0) for v in videos if v.name not in skipped), 1),
        "topic": choice.get("topic", ""), "skipped": skipped, "broll": [str(p) for p in pieces],
        "kept": [{"clip": videos[s["src"]].name, "t": f"{s['s']:.1f}-{s['e']:.1f}", "score": s.get("score"), "text": s["text"]}
                 for s in chosen_sents],
        "cuts": [{"clip": videos[p["src"]].name, "t": f"{p['cs']:.2f}-{p['ce']:.2f}", "len": round(p["ce"] - p["cs"], 2)} for p in chosen],
        "dropped": [{"clip": videos[s["src"]].name, "t": f"{s['s']:.1f}", "why": s.get("dropped", "not picked"), "text": s["text"]}
                    for s in every if s not in chosen_sents],
    }
    (work / "edit.json").write_text(json.dumps(report, indent=2))
    # Cover image next to the video: a clean frame from the cut (no captions) + the opening title.
    try:
        from . import thumbnail
        props = json.loads((work / "props.json").read_text()) if (work / "props.json").exists() else {}
        hook = next((b["text"] for b in props.get("beats", []) if b.get("type") == "hook"), "")
        title = choice.get("title") or hook or choice.get("topic", "")
        clean = work / "cut.mp4" if (work / "cut.mp4").exists() else final
        if title:
            thumbnail.make_cover(clean, title, final.with_suffix(".jpg"), tpl.get("style", {}).get("accent", "#EA6113"))
    except Exception as e:
        log(f"cover: skipped ({e})")
    log(f"done -> {final.name}")
    return report


def edit_one(video: Path, tpl: dict, out_dir: Path, broll_clips: list[Path] | None = None) -> dict:
    return edit_clips([video], tpl, out_dir, out_dir / video.stem / _slug(tpl), out_dir / f"{video.stem} - {tpl['name']}.mp4",
                      broll_clips)


def edit_shorts(video: Path, tpl: dict, out_dir: Path, n: int, broll_clips: list[Path] | None = None) -> list[dict]:
    """Several separate shorts from one long video (each its own idea)."""
    sents = _sentences(video, 0, tpl, out_dir)
    pool = [s for s in sents if "dropped" not in s]
    base = out_dir / video.stem / (_slug(tpl) + f"-shorts{n}")
    base.mkdir(parents=True, exist_ok=True)
    log(f"{video.name}: editor (Qwen) finding up to {n} shorts in {len(pool)} sentences")
    picks = story.choose_many(pool, tpl, n, base / "shorts.json")
    log(f"{video.name}: {len(picks)} shorts: " + " | ".join(p["title"] for p in picks))
    reports = []
    for k, pick in enumerate(picks, 1):
        title = re.sub(r"[^A-Za-z0-9 ]+", "", pick["title"]).strip()[:40] or f"Short {k}"
        work = base / f"short-{k}"
        final = out_dir / f"{video.stem} - short {k} {title} - {tpl['name']}.mp4"
        try:
            reports.append(edit_clips([video], tpl, out_dir, work, final, broll_clips, choice=pick, pool_in=pool))
        except Exception as e:
            log(f"{video.name} short {k}: FAILED {e}")
    return reports


def edit_mix(videos: list[Path], tpl: dict, out_dir: Path, name: str) -> dict:
    return edit_clips(videos, tpl, out_dir, out_dir / f"{name} - mix" / _slug(tpl), out_dir / f"{name} - mix - {tpl['name']}.mp4")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--template", default="tbn-house")
    ap.add_argument("--out")
    ap.add_argument("--only", help="only videos whose name contains this")
    ap.add_argument("--focus", help="what the video should be about, in plain words (e.g. 'boxing and skipping')")
    ap.add_argument("--combine", action="store_true", help="mix every clip into one video instead of one video per clip")
    ap.add_argument("--explainer", action="store_true", help="voice over full motion-graphics scenes (the Gist & Grind look)")
    ap.add_argument("--series", help="explainer series tag, e.g. 'GIST & GRIND'")
    ap.add_argument("--episode", help="explainer episode tag, e.g. 'EP 04'")
    ap.add_argument("--workout", action="store_true", help="gym footage: beat-cut highlight with exercise labels")
    ap.add_argument("--shorts", type=int, default=0, metavar="N", help="cut up to N separate shorts from each video")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="override a template value, dotted for nested keys (e.g. motion.per_minute=12)")
    a = ap.parse_args(argv)
    folder = Path(a.folder).expanduser().resolve()
    tpl = load_template(a.template)
    for kv in a.set:
        key, _, raw = kv.partition("=")
        try:
            val = json.loads(raw)
        except json.JSONDecodeError:
            val = raw
        node = tpl
        *path, last = key.split(".")
        for k in path:
            node = node.setdefault(k, {})
        node[last] = val
    if a.focus:
        tpl["focus"] = a.focus.strip()
    if a.set or a.focus:  # overrides get their own cache folder so a redo really re-plans
        import hashlib
        tpl["_variant"] = "-" + hashlib.sha1("|".join(sorted(a.set or []) + [a.focus or ""]).encode()).hexdigest()[:6]
    out_dir = Path(a.out).expanduser().resolve() if a.out else ROOT / "output" / folder.name
    out_dir.mkdir(parents=True, exist_ok=True)
    videos = sorted(p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXT and not p.name.startswith("."))
    only = (lambda v: a.only.lower() in v.name.lower()) if a.only else (lambda v: True)  # B-roll still comes from the whole folder
    if not videos:
        print("no videos found", file=sys.stderr)
        return 1
    if a.only and not any(only(v) for v in videos):
        log(f"FAILED no file name contains \"{a.only}\" (that box is for file names; describe what you want under Focus instead)")
        return 1
    if a.workout:
        from . import workout
        try:
            workout.run([v for v in videos if only(v)], folder, tpl, out_dir, log)
        except Exception as e:
            log(f"workout: FAILED {e}")
            return 1
        return 0
    if a.combine:
        try:
            edit_mix([v for v in videos if only(v)], tpl, out_dir, folder.name)
        except Skip as e:
            log(f"mix: SKIPPED {e}")
            return 1
        except Exception as e:
            log(f"mix: FAILED {e}")
            return 1
        return 0
    # One pass to sort the folder: talking clips get edited, silent ones become B-roll for them.
    talking, silent = [], []
    for v in videos:
        try:
            dur = edit.probe(v)["dur"]
            DURATIONS[str(v)] = dur
            if dur < MIN_SECONDS:
                log(f"{v.name}: SKIPPED only {dur:.1f}s long")
                continue
            n = len(transcribe.transcribe(v, out_dir / v.stem / "words.json"))
            (talking if n >= MIN_WORDS else silent).append(v)
        except Exception as e:
            log(f"{v.name}: SKIPPED unreadable file ({type(e).__name__}{': ' + str(e) if str(e) else ''})")
    if silent:
        log(f"{len(silent)} clips have no one talking: used as B-roll ({', '.join(s.name for s in silent[:6])}{'…' if len(silent) > 6 else ''})")
    if not talking:
        log("SKIPPED no clip in this folder has anyone talking")
        return 0
    for v in [t for t in talking if only(t)]:
        try:
            if a.explainer:
                from . import explainer
                ex = tpl.setdefault("explainer", {})
                if a.series:
                    ex["series"] = a.series
                if a.episode:
                    ex["episode"] = a.episode
                explainer.run(v, tpl, out_dir, log, _sentences)
                continue
            if a.shorts > 1:
                edit_shorts(v, tpl, out_dir, a.shorts, silent)
                continue
            edit_one(v, tpl, out_dir, silent)
        except Skip as e:
            log(f"{v.name}: SKIPPED {e}")
        except Exception as e:  # one bad file shouldn't stop the batch
            log(f"{v.name}: FAILED {e}")
    try:
        from . import pack
        log(f"posting pack: {pack.make(out_dir).name} (draft captions, nothing posted)")
    except Exception as e:
        log(f"posting pack: skipped ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
