"""Workout mode: gym footage with no (or little) talking -> a beat-cut highlight short.

1. Motion: how much each clip moves, 5 times a second (frame differences, cv2).
2. Gemma looks at frame sheets: action score per frame + the exercise name per clip.
3. Music: a track in the folder (or music/), else a free generated beat. Beats found with numpy.
4. Pick: the best-moving, best-looking windows; every cut lands on a beat, one exercise at a time.
5. Render: ffmpeg cuts + music, Remotion adds exercise labels, a progress bar and the TBN look.
"""
import json
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np

from . import gemma

MUSIC_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac"}


# ---------- motion ----------

def motion_curve(video: Path, cache: Path, fps: float = 5.0) -> list[float]:
    """Mean frame difference, sampled `fps` times a second, normalised 0-1 per clip.
    ffmpeg decodes on the Mac's video chip and hands over tiny grey frames: a 26-min 4K clip took 11 min with
    OpenCV reading every full frame, this takes well under a minute."""
    if cache.exists():
        return json.loads(cache.read_text())
    W, H = 96, 170
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                               capture_output=True, text=True).stdout.strip() or 0)
    long_clip = dur > 180  # over 3 min: keyframes only (about 1 a second), 10x faster, then spread back to `fps`
    args = ["-skip_frame", "nokey"] if long_clip else []
    vf = f"scale={W}:{H},format=gray" if long_clip else f"fps={fps},scale={W}:{H},format=gray"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-hwaccel", "videotoolbox", *args, "-i", str(video), "-an", "-vf", vf,
                          *(["-fps_mode", "passthrough"] if long_clip else []), "-f", "rawvideo", "-"], capture_output=True).stdout
    n = len(raw) // (W * H)
    vals = [0.0]
    if n > 1:
        f = np.frombuffer(raw[:n * W * H], np.uint8).reshape(n, H, W).astype(np.float32)
        vals += [float(x) for x in np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))]
    if long_clip and dur and len(vals) > 1:
        t_key = np.linspace(0, dur, len(vals))
        vals = list(np.interp(np.arange(0, dur, 1 / fps), t_key, vals))
    a = np.array(vals)
    a = np.convolve(a, np.ones(3) / 3, mode="same")
    lo, hi = np.percentile(a, 5), np.percentile(a, 95)
    out = [round(float(x), 3) for x in np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


NAME_SCHEMA = {"type": "object", "properties": {"exercise": {"type": "string"}, "scores": {"type": "array", "items": {"type": "integer"}}},
               "required": ["exercise", "scores"]}


def look(video: Path, shared: Path) -> dict:
    """Gemma: exercise name for the clip + a 1-10 action score per frame (every 2 s)."""
    cache = shared / "workout_look.json"
    if cache.exists():
        return json.loads(cache.read_text())
    fr = gemma.frames(video, shared / "frames")
    if len(fr) > 36:  # long clips: 36 frames spread over the whole clip are plenty to name and rate it (4 Gemma calls)
        fr = [fr[round(i * (len(fr) - 1) / 35)] for i in range(36)]
    names, scores = [], []
    for i in range(0, len(fr), 9):
        chunk = fr[i:i + 9]
        prompt = (f"This grid shows {len(chunk)} numbered frames from a gym/workout video, in time order. "
                  "1) exercise: name the exercise being done in 1-4 words (e.g. 'Incline dumbbell press', 'Push-ups', "
                  "'Shadow boxing'), or 'Rest' if no one is exercising. 2) scores: 1-10 per frame for how good it looks as a "
                  "highlight: someone mid-rep, strong effort, good form, clear framing. Low: resting, walking around, "
                  "setting up the camera, blurry. "
                  f'Reply as JSON {{"exercise": "...", "scores": [{len(chunk)} integers]}}.')
        try:
            r = gemma.ask(prompt, [gemma._sheet([p for _, p in chunk])], NAME_SCHEMA)
            names.append(str(r.get("exercise", "")).strip())
            s = r.get("scores", [])
        except Exception:
            s = []
        scores += [max(1, min(10, int(v))) for v in (s + [5] * len(chunk))[:len(chunk)]]
    named = [n for n in names if n and n.lower() != "rest"]
    exercise = max(set(named), key=named.count) if named else ""
    out = {"exercise": exercise, "frames": [{"t": t, "v": v} for (t, _), v in zip(fr, scores)]}
    cache.write_text(json.dumps(out, indent=2))
    return out


TEXT_SCHEMA = {"type": "object", "properties": {"captions": {"type": "boolean"}}, "required": ["captions"]}
LIBRARY = Path.home() / "TBN-HQ" / "footage-library" / "catalog"


def has_old_captions(video: Path, shared: Path) -> bool:
    """Clips already edited elsewhere (CapCut exports with subtitles burned in) make a mess under our captions.
    The footage library remembers where a clip came from; Gemma checks the picture too."""
    cache = shared / "text_check.json"
    if cache.exists():
        return json.loads(cache.read_text())["captions"]
    m = re.search(r"_([0-9a-f]{10})$", video.stem)
    came_from = ""
    if m and (LIBRARY / f"{m.group(1)}.json").exists():
        came_from = json.loads((LIBRARY / f"{m.group(1)}.json").read_text()).get("path", "")
    edited = bool(re.search(r"capcut|export|finished|final|edit", came_from, re.I))
    seen = False
    if not edited:
        fr = gemma.frames(video, shared / "frames")
        pick = [fr[round(i * (len(fr) - 1) / 8)] for i in range(9)] if len(fr) >= 9 else fr
        try:
            r = gemma.ask("This grid shows frames from one video. Are there subtitles or captions that an editing app put on "
                          "top of the picture (spoken words as white or yellow text, usually lower middle)? Signs, posters, "
                          "logos or writing on walls and clothes do NOT count. Reply as JSON {\"captions\": true or false}.",
                          [gemma._sheet([q for _, q in pick])], TEXT_SCHEMA)
            seen = bool(r.get("captions"))
        except Exception:
            seen = False
    raw_camera = bool(re.search(r"(DJI|IMG|GOPR|MVI|PXL)_\d+", Path(came_from).name))  # straight off a camera: nothing burned in
    has = edited or (seen and not raw_camera)
    cache.write_text(json.dumps({"captions": has, "came_from": came_from, "edited": edited, "seen": seen}))
    return has


def action_box(video: Path, t0: float, t1: float, n: int = 6) -> dict:
    """Where the movement is inside one cut, as a zoom: tall shots from a high camera are 40% ceiling, so the crop
    leans in on the people moving. {x, y} = centre (0-1 of the frame), z = zoom (1 = whole frame)."""
    W, H = 108, 192
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t0:.2f}", "-t", f"{max(0.4, t1 - t0):.2f}", "-i", str(video), "-an",
                          "-vf", f"fps={n / max(0.4, t1 - t0):.3f},scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    k = len(raw) // (W * H)
    if k < 2:
        return {"x": 0.5, "y": 0.5, "z": 1.0}
    f = np.frombuffer(raw[:k * W * H], np.uint8).reshape(k, H, W).astype(np.float32)
    d = np.abs(np.diff(f, axis=0)).mean(axis=0)
    d = np.where(d > np.percentile(d, 80), d, 0)  # only the clearly moving parts
    if d.sum() < 1:
        return {"x": 0.5, "y": 0.5, "z": 1.0}
    col, row = d.sum(axis=0), d.sum(axis=1)
    span = lambda a: (np.searchsorted(np.cumsum(a) / a.sum(), 0.1), np.searchsorted(np.cumsum(a) / a.sum(), 0.9))
    (x0, x1), (y0, y1) = span(col), span(row)
    cx, cy = (x0 + x1) / 2 / W, (y0 + y1) / 2 / H
    need = max((x1 - x0) / W, (y1 - y0) / H) * 1.5  # some room around the action
    z = float(np.clip(1 / max(need, 1e-3), 1.0, 1.7))
    if abs(cy - 0.5) > 0.12:  # action sits low (or high) in the frame: always lose some of the empty ceiling / floor
        z = max(z, 1.35)
    return {"x": round(float(cx), 3), "y": round(float(cy), 3), "z": round(z, 2)}


# ---------- music ----------

def find_music(folder: Path) -> Path | None:
    for d in (folder, folder / "music"):
        if d.is_dir():
            for p in sorted(d.iterdir()):
                if p.suffix.lower() in MUSIC_EXT and not p.name.startswith("."):
                    return p
    return None


def make_beat(out: Path, seconds: float, bpm: int = 124) -> Path:
    """A free, generated four-on-the-floor beat (kick, clap, hats, a bass pulse). No licensing worries."""
    if out.exists():
        return out
    sr, beat = 48000, 60.0 / bpm
    n = int(sr * (seconds + 2))
    t = np.arange(n) / sr
    mix = np.zeros(n, dtype=np.float32)

    def hit(at: float, wave: np.ndarray):
        i = int(at * sr)
        j = min(n, i + len(wave))
        if i < n:
            mix[i:j] += wave[:j - i]

    kt = np.arange(int(0.25 * sr)) / sr
    kick = (np.sin(2 * np.pi * (50 + 120 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 12)).astype(np.float32)
    ht = np.arange(int(0.05 * sr)) / sr
    hat = (np.random.default_rng(1).standard_normal(len(ht)) * np.exp(-ht * 90) * 0.25).astype(np.float32)
    ct = np.arange(int(0.18 * sr)) / sr
    clap = (np.random.default_rng(2).standard_normal(len(ct)) * np.exp(-ct * 25) * 0.45).astype(np.float32)
    bt = np.arange(int(beat * sr)) / sr
    k = 0
    while k * beat < seconds + 1:
        at = k * beat
        hit(at, kick)
        hit(at + beat / 2, hat)
        if k % 2 == 1:
            hit(at, clap)
        root = 55.0 if (k // 8) % 2 == 0 else 49.0
        hit(at + beat / 2, (np.sin(2 * np.pi * root * bt[: len(bt) // 2]) * np.exp(-bt[: len(bt) // 2] * 6) * 0.35).astype(np.float32))
        k += 1
    mix = mix / max(1e-6, float(np.abs(mix).max())) * 0.9
    raw = out.with_suffix(".f32")
    np.stack([mix, mix], axis=1).astype(np.float32).tofile(raw)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", str(raw),
                    "-af", "afade=t=out:st=%.2f:d=1.5" % max(0, seconds - 1.0), "-t", f"{seconds + 0.5:.2f}", str(out)], check=True)
    raw.unlink(missing_ok=True)
    return out


def beats(music: Path, cache: Path) -> dict:
    """Tempo and beat times from onset energy (numpy only)."""
    if cache.exists():
        return json.loads(cache.read_text())
    sr = 22050
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(music), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(pcm, dtype=np.float32)
    hop = 512
    frames = len(x) // hop
    env = np.array([np.sqrt((x[i * hop:(i + 1) * hop] ** 2).mean() + 1e-9) for i in range(frames)])
    onset = np.maximum(0, np.diff(np.log(env + 1e-6), prepend=0))
    # tempo: autocorrelation peak between 80 and 160 bpm
    ac = np.correlate(onset - onset.mean(), onset - onset.mean(), mode="full")[len(onset) - 1:]
    fps = sr / hop
    lags = np.arange(int(fps * 60 / 160), int(fps * 60 / 80))
    lag = int(lags[np.argmax(ac[lags])])
    period = lag / fps
    # phase: offset that lines the grid up with the strongest onsets
    best = max(range(lag), key=lambda o: onset[o::lag].sum())
    t0 = best / fps
    dur = len(x) / sr
    grid = [round(t0 + k * period, 3) for k in range(int((dur - t0) / period))]
    out = {"bpm": round(60 / period, 1), "beats": grid, "duration": round(dur, 2)}
    cache.write_text(json.dumps(out))
    return out


# ---------- reps ----------

def rep_times(motion: list[float], t0: float, t1: float, fps: float = 5.0) -> list[float]:
    """Moments of peak effort inside [t0, t1] (seconds from t0): one per rep, from the motion rhythm."""
    a, z = int(t0 * fps), int(t1 * fps)
    seg = np.array(motion[a:z])
    if len(seg) < 6 or seg.max() - seg.min() < 0.15:
        return []
    x = seg - seg.mean()
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    lo, hi = int(0.8 * fps), min(len(ac) - 1, int(4.0 * fps))  # a rep takes 0.8-4 s
    if hi <= lo:
        return []
    period = lo + int(np.argmax(ac[lo:hi]))
    if ac[period] < 0.2 * ac[0]:
        return []  # no clear rhythm: not counting
    peaks, last = [], -period
    thresh = seg.mean() + 0.25 * seg.std()
    for i in range(1, len(seg) - 1):
        if seg[i] >= seg[i - 1] and seg[i] >= seg[i + 1] and seg[i] > thresh and i - last >= period * 0.7:
            peaks.append(round(i / fps, 2))
            last = i
    return peaks if len(peaks) >= 2 else []


def reps_in(motion: list[float], t0: float, t1: float, pad: float = 4.0) -> list[float]:
    """Reps inside a short cut: find the rhythm over a wider window, keep the peaks that land in the cut."""
    w0 = max(0.0, t0 - pad)
    peaks = [w0 + p for p in rep_times(motion, w0, t1 + pad)]
    return [round(p - t0, 2) for p in peaks if t0 <= p < t1]


# ---------- pick ----------

def pick(clips: list[dict], beat_times: list[float], tpl: dict) -> list[dict]:
    """Segments that land on beats. clips: [{"video","exercise","motion","look","dur","k"}].
    Each clip gets its best windows (action x motion), in story order: one exercise at a time."""
    w = tpl.get("workout", {})
    target = w.get("seconds", 30)
    bars = w.get("beats_per_cut", 4)
    period = (beat_times[1] - beat_times[0]) if len(beat_times) > 1 else 0.5
    seg = bars * period
    usable = [c for c in clips if c["exercise"] and c["dur"] > seg + 1]
    if not usable:
        usable = [c for c in clips if c["dur"] > seg + 1]
    n_cuts = max(1, int(target / seg))
    per_clip = max(1, n_cuts // max(1, len(usable)))
    chosen = []
    for c in usable:
        mot = np.array(c["motion"])  # 5 / s
        looks = {round(f["t"]): f["v"] for f in c["look"]}

        def score(t: float) -> float:
            a, z = int(t * 5), int((t + seg) * 5)
            m = float(mot[a:z].mean()) if z > a and a < len(mot) else 0
            v = looks.get(round(t / 2) * 2, 5) / 10
            return 0.6 * m + 0.4 * v

        cands = sorted(np.arange(0.5, c["dur"] - seg - 0.3, 0.5), key=lambda t: -score(t))
        took = []
        for t in cands:
            if all(abs(t - u) >= seg for u in took) and score(t) > 0.35:
                took.append(float(t))
            if len(took) >= per_clip:
                break
        for t in sorted(took):
            chosen.append({"src": c["k"], "cs": round(t, 2), "ce": round(t + seg, 2), "exercise": c["exercise"],
                           "score": round(score(t), 2), "words": [], "text": c["exercise"],
                           "reps": reps_in(c["motion"], t, t + seg)})
        if len(chosen) >= n_cuts:
            break
    return chosen[:n_cuts]


# File names from the footage library say what the clip is ("..._gym-heavy-bag-training-session_..."). Gemma's
# small vision model calls boxing "Dumbbell row" now and then, so a boxing name beats a gym guess.
BOX_NAMES = [("skipp", "Skipping"), ("rope", "Skipping"), ("heavy-bag", "Heavy bag"), ("bag", "Bag work"), ("spar", "Sparring"),
             ("shadowbox", "Shadow boxing"), ("pad", "Pad work"), ("boxing", "Boxing drills"), ("boxer", "Boxing drills")]


def _trust_name(v: Path, exercise: str) -> str:
    stem = v.stem.lower()
    named = next((label for key, label in BOX_NAMES if key in stem), "")
    if named and not re.search(r"box|bag|spar|punch|rope|skip|pad|jab|hook", exercise.lower()):
        return named
    return exercise


# ---------- run ----------

def run(videos: list[Path], folder: Path, tpl: dict, out_dir: Path, log) -> Path:
    from . import edit, motion
    w = tpl.get("workout", {})
    work = out_dir / f"{folder.name} - workout" / re.sub(r"[^a-z0-9]+", "-", tpl["name"].lower()).strip("-")
    work.mkdir(parents=True, exist_ok=True)
    clips = []
    # Focus ("boxing and skipping"): clips whose file name says so go first; if none do, every clip is looked at
    # and the ones whose exercise matches are kept.
    words = [w[:5] for w in re.findall(r"[a-z]+", (tpl.get("focus") or "").lower()) if len(w) > 2 and w not in ("and", "the", "was", "part", "with", "where", "when")]
    SAME = {"skipp": ["rope", "jump"], "jumpi": ["rope", "skipp"], "punch": ["bag", "boxin"], "lifti": ["press", "squat", "deadl"]}
    words += [x for w in list(words) for x in SAME.get(w, [])]
    hit = lambda s: any(w in s.lower() for w in words)
    flat = lambda v: v.stem.replace("-", " ").replace("_", " ").lower()
    # only trust file names when every focus word is in at least one name; otherwise look inside every clip
    named = [v for v in videos if hit(flat(v))] if words and all(any(w in flat(v) for v in videos) for w in words) else []
    if words:
        log(f"focus: {tpl['focus']} ({len(named)} clip{'s' if len(named) != 1 else ''} named like it)" if named else
            f"focus: {tpl['focus']} (no file names match, checking what's in every clip)")
    looked = named or videos
    for k, v in enumerate(videos):
        if v not in looked:
            continue
        info = edit.probe(v)
        if info["dur"] < 3:
            log(f"{v.name}: SKIPPED only {info['dur']:.1f}s long")
            continue
        shared = out_dir / v.stem
        log(f"{v.name}: measuring movement and asking Gemma what exercise this is")
        mot = motion_curve(v, shared / "motion.json")
        lk = look(v, shared)
        if has_old_captions(v, shared):
            log(f"{v.name}: SKIPPED it already has captions from another edit")
            continue
        ex = _trust_name(v, lk["exercise"])
        log(f"{v.name}: {ex or 'no exercise seen'}" + (f" (Gemma said {lk['exercise']})" if ex != lk["exercise"] else ""))
        clips.append({"video": v, "k": k, "dur": info["dur"], "motion": mot, "look": lk["frames"], "exercise": ex})
    if words and not named:
        match = [c for c in clips if hit(c["exercise"]) or hit(flat(c["video"]))]
        if match:
            clips = match
        else:
            log(f"focus: no clip showed {tpl['focus']}, using all of them")
    if not clips:
        raise RuntimeError("no usable gym clips (all too short)")
    music = find_music(folder)
    seconds = w.get("seconds", 30)
    if music:
        log(f"music: {music.name}")
    else:
        music = make_beat(work / "tbn-beat.wav", seconds + 4, w.get("bpm", 124))
        log("music: no track in the folder, using a generated TBN beat (free)")
    bt = beats(music, work / "beats.json")
    log(f"music: {bt['bpm']} bpm, cuts every {w.get('beats_per_cut', 4)} beats")
    chosen = pick(clips, bt["beats"], tpl)
    if not chosen:
        raise RuntimeError("no moments with enough movement")
    for p in chosen:  # lean in on the action in every cut
        p["focus"] = action_box(videos[p["src"]], p["cs"], p["ce"])
    if w.get("replays", True):
        # Coach-Fixes style: the best cut of each exercise plays again at half speed
        best = {}
        for i, p in enumerate(chosen):
            if p["exercise"] and (p["exercise"] not in best or p["score"] > chosen[best[p["exercise"]]]["score"]):
                best[p["exercise"]] = i
        for i in sorted(best.values(), reverse=True)[:3]:
            chosen.insert(i + 1, {**chosen[i], "speed": 0.5, "replay": True, "reps": []})
    total = sum((p["ce"] - p["cs"]) / p.get("speed", 1.0) for p in chosen)
    log(f"workout: {len(chosen)} cuts, {total:.1f}s, exercises: {', '.join(dict.fromkeys(p['exercise'] for p in chosen))}")
    # Cut and crop (no captions), then lay the music under it, starting on the first beat.
    silent_cut = edit.render(videos, chosen, {**tpl, "captions": {"on": False}}, work, work / "cut_raw.mp4")
    first = bt["beats"][0] if bt["beats"] else 0
    cut = work / "cut.mp4"
    keep_room = w.get("room_sound", 0.12)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent_cut), "-ss", f"{first:.3f}", "-i", str(music),
                    "-filter_complex", f"[0:a]volume={keep_room}[r];[1:a]volume=0.9,atrim=0:{total:.3f}[m];[r][m]amix=inputs=2:normalize=0:duration=first,"
                    f"afade=t=out:st={max(0, total - 1.2):.2f}:d=1.2,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(cut)], check=True)
    # Exercise labels as graphics: one when each new exercise starts.
    beats_out, t, last, count = [], 0.0, None, 0
    for p in chosen:
        if p["exercise"] != last:
            beats_out.append({"type": "keyword", "s": round(t + 0.1, 2), "e": round(t + 2.2, 2), "text": p["exercise"], "icon": "Dumbbell"})
            last, count = p["exercise"], 0
        if p.get("replay"):
            beats_out.append({"type": "replay", "s": round(t, 2), "e": round(t + (p["ce"] - p["cs"]) / p["speed"], 2), "text": "SLOW-MO"})
        if p.get("reps") and w.get("rep_counter", True):
            beats_out.append({"type": "reps", "s": round(t, 2), "e": round(t + p["ce"] - p["cs"], 2), "text": "REP",
                              "at": p["reps"], "start": count})
            count += len(p["reps"])
        t += (p["ce"] - p["cs"]) / p.get("speed", 1.0)
    title = w.get("title") or "WORKOUT OF THE WEEK"
    beats_out.insert(0, {"type": "hook", "s": 0.0, "e": 2.4, "text": title})
    final = out_dir / f"{folder.name} - workout - {tpl['name']}.mp4"
    motion.render_workout(cut, chosen, beats_out, tpl, work, final)
    (work / "edit.json").write_text(json.dumps({
        "videos": [str(v) for v in videos], "template": tpl["name"], "output": str(final), "seconds": round(total, 1),
        "source_seconds": round(sum(c["dur"] for c in clips), 1), "music": str(music), "bpm": bt["bpm"],
        "kept": [{"clip": videos[p["src"]].name, "t": f"{p['cs']:.1f}-{p['ce']:.1f}", "score": p["score"], "text": p["exercise"]} for p in chosen],
        "dropped": [], "topic": "workout"}, indent=2))
    log(f"done -> {final.name}")
    return final
