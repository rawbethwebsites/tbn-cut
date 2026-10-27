"""Motion layer: Gemma suggests graphic beats, Python checks them, Remotion renders.

Gemma proposes; the rules below decide what survives (timing inside the spoken line,
spacing between beats, short text), so a bad suggestion can't break the edit.
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

from . import gemma

MOTION = Path(__file__).resolve().parent.parent / "motion"
# Our own download of Remotion's browser came down incomplete (no ICU data); the cooked editor's works.
BROWSER = Path.home() / ".ai-video-editor/remotion/node_modules/.remotion/chrome-headless-shell/mac-arm64/chrome-headless-shell-mac-arm64/chrome-headless-shell"

# Lucide icons Gemma may pick (all checked to exist in lucide-react 0.468).
ICONS = ["Briefcase", "Wrench", "Hammer", "Paintbrush", "House", "Building2", "Car", "Smartphone", "Laptop", "Globe",
         "Wallet", "Banknote", "CreditCard", "PiggyBank", "TrendingUp", "ChartColumn", "Users", "User", "UserCheck",
         "Handshake", "CircleCheck", "CircleX", "TriangleAlert", "Clock", "Calendar", "MapPin", "Truck", "ShoppingCart",
         "Package", "Star", "Heart", "Zap", "Flame", "Rocket", "Target", "Trophy", "Lightbulb", "Brain", "MessageCircle",
         "Mail", "Camera", "Video", "Mic", "Dumbbell", "Bike", "Timer", "ShieldCheck", "Lock", "Sparkles", "ListChecks",
         "Search", "Settings", "ClipboardList", "Gift", "Coffee", "Utensils", "Sprout", "HeartPulse", "Footprints", "Activity"]

BEATS_SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "beats": {"type": "array", "items": {"type": "object", "properties": {
            "line": {"type": "integer"},
            "type": {"type": "string", "enum": ["keyword", "list", "stat", "cutaway", "versus", "quote"]},
            "text": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}},
            "value": {"type": "number"},
            "sub": {"type": "string"},
            "a": {"type": "string"},
            "b": {"type": "string"},
            "icon": {"type": "string"},
        }, "required": ["line", "type", "text"]}},
    },
    "required": ["hook", "beats"],
}


def timeline(chosen: list[dict]) -> tuple[list[dict], list[dict]]:
    """Words and lines with times on the finished (cut) timeline."""
    words, lines, t0 = [], [], 0.0
    for p in chosen:
        ws = [{"w": w["w"], "s": round(w["s"] - p["cs"] + t0, 3), "e": round(w["e"] - p["cs"] + t0, 3)} for w in p["words"]]
        words += ws
        lines.append({"s": ws[0]["s"], "e": ws[-1]["e"], "text": p["text"]})
        t0 += p["ce"] - p["cs"]
    return words, lines


def _fresh(cache: Path, lines: list[dict]) -> dict | list | None:
    """Cached result only if it was made for exactly these lines (an edit change invalidates it)."""
    import hashlib
    key = hashlib.sha1("\n".join(l["text"] for l in lines).encode()).hexdigest()[:12]
    if cache.exists():
        d = json.loads(cache.read_text())
        if isinstance(d, dict) and d.get("_key") == key:
            return d["value"]
    return None


def _store(cache: Path, lines: list[dict], value) -> None:
    import hashlib
    key = hashlib.sha1("\n".join(l["text"] for l in lines).encode()).hexdigest()[:12]
    cache.write_text(json.dumps({"_key": key, "value": value}, indent=2))


def _hook_examples(n: int = 8) -> str:
    """Proven hook shapes from hooks.json (if present), as inspiration for the opening title."""
    f = Path(__file__).resolve().parent.parent / "hooks.json"
    try:
        forms = json.loads(f.read_text()).get("formulas", [])
    except Exception:
        return ""
    if not forms:
        return ""
    picks = [x.get("example") or x.get("template") for x in forms[:: max(1, len(forms) // n)]][:n]
    return "   Hook shapes that work (copy the shape, never the facts): " + " | ".join(p for p in picks if p) + "\n"


def plan_beats(lines: list[dict], tpl: dict, cache: Path) -> list[dict]:
    if (hit := _fresh(cache, lines)) is not None:
        return hit
    m = tpl.get("motion", {})
    total = lines[-1]["e"] if lines else 0
    want = max(1, round(total / 60 * m.get("per_minute", 6)))
    listing = "\n".join(f"{i + 1}. [{l['s']:.1f}s] {l['text']}" for i, l in enumerate(lines))
    prompt = (
        "You are the motion designer for a short vertical video. Spoken lines with start times:\n"
        f"{listing}\n\n"
        "1) hook: an opening headline that tells a scroller what this video is about and why to watch, "
        "3-7 plain words, no colons, based only on what is said (e.g. 'An app to hire and pay artisans').\n"
        + _hook_examples() +
        f"2) beats: pick about {want} lines that deserve an animated graphic. Types:\n"
        "- keyword: 1-3 words that sum up the line (a name, a key idea).\n"
        "- list: the line names several things; text = 2-4 word heading, items = 2-5 short items taken from the words said.\n"
        "- stat: the line says a number; value = that number, text = 2-4 words saying what it counts.\n"
        "- cutaway: a key idea worth a full-screen animated title; text = 2-5 words, sub = optional 3-7 word line.\n"
        "- versus: the line compares or contrasts two things; a and b = 1-2 words each, text = a short label.\n"
        "- quote: a short punchy sentence worth showing word for word; text = the exact words, max 8.\n"
        "Use only facts and words from the lines. No made-up numbers. Spread beats across the video.\n"
        "For keyword and cutaway beats also give icon: the one name from this list that best shows the idea, "
        f"or \"\" if none fits: {', '.join(ICONS)}.\n"
        'Reply as JSON {"hook": "...", "beats": [{"line": n, "type": "...", "text": "...", "items": [], "value": 0, "sub": "", "a": "", "b": ""}]}.'
    )
    try:
        raw = gemma.ask(prompt, schema=BEATS_SCHEMA)
    except Exception:
        raw = {"hook": "", "beats": []}
    _store(cache, lines, raw)
    return raw


STOP = {"a", "an", "the", "is", "are", "was", "it", "to", "of", "and", "or", "i", "you", "he", "she", "we", "they",
        "be", "in", "on", "at", "so", "like", "just", "that", "this", "put", "get", "do", "job"}

KW_SCHEMA = {"type": "object", "properties": {"keywords": {"type": "array", "items": {"type": "string"}},
                                             "icons": {"type": "array", "items": {"type": "string"}}},
             "required": ["keywords", "icons"]}


def line_keywords(lines: list[dict], cache: Path) -> list[list[str]]:
    """[keyword, icon] per line (1-3 words + a Lucide icon or ""), used to fill stretches with no graphic."""
    if (hit := _fresh(cache, lines)) is not None:
        return hit
    out = []
    for i in range(0, len(lines), 30):
        chunk = lines[i:i + 30]
        listing = "\n".join(f"{j + 1}. {l['text']}" for j, l in enumerate(chunk))
        try:
            k = gemma.ask("For each spoken line, give the 1-3 word NOUN phrase that sums it up: the thing, person, "
                          "result or idea (e.g. 'Cleaners', 'Paid after the job', 'Website'). Use words from the line. "
                          "Never a verb phrase like 'list it' or 'give job', never filler. Also an icon per line from "
                          f"this list (or \"\"): {', '.join(ICONS)}.\n"
                          f"{listing}\n"
                          f'Reply as JSON {{"keywords": [{len(chunk)} strings], "icons": [{len(chunk)} strings]}}.',
                          schema=KW_SCHEMA)
            kw, ic = k.get("keywords", []), k.get("icons", [])
        except Exception:
            kw, ic = [], []
        kw = (kw + [""] * len(chunk))[:len(chunk)]
        ic = (ic + [""] * len(chunk))[:len(chunk)]
        out += [[str(a), b if b in ICONS else ""] for a, b in zip(kw, ic)]
    _store(cache, lines, out)
    return out


def _said_at(text: str, L: dict, words: list[dict]) -> float:
    """When the first word of `text` is spoken inside line L (so a graphic lands on its word)."""
    for tok in text.split():  # first word of the phrase that is actually said
        first = re.sub(r"[^a-z0-9]", "", tok.lower())[:5]
        if len(first) < 3:
            continue
        for w in words:
            if L["s"] - 0.01 <= w["s"] <= L["e"] and re.sub(r"[^a-z0-9]", "", w["w"].lower()).startswith(first):
                return w["s"]
    return L["s"]


def _words(s: str, n: int) -> str:
    return " ".join(s.replace("\n", " ").split()[:n]).strip(" .,!?;:")


def _item_times(items: list[str], L: dict, words: list[dict]) -> list[float]:
    """When each list item is actually spoken, so it appears on cue (falls back to even spacing)."""
    span = [w for w in words if L["s"] - 0.01 <= w["s"] <= L["e"] + 0.01]
    times, after = [], L["s"]
    for k, it in enumerate(items):
        first = re.sub(r"[^a-z0-9]", "", it.split()[0].lower()) if it.split() else ""
        hit = next((w["s"] for w in span if w["s"] >= after and re.sub(r"[^a-z0-9]", "", w["w"].lower()).startswith(first[:5])), None)
        if hit is None:
            hit = L["s"] + (L["e"] - L["s"]) * (k + 0.5) / len(items)
        times.append(round(hit - L["s"], 3))
        after = hit
    return times


def validate(raw: dict, lines: list[dict], tpl: dict, words: list[dict] | None = None) -> list[dict]:
    m = tpl.get("motion", {})
    gap = m.get("min_gap", 3.0)
    out = []
    hook = _words(raw.get("hook", ""), 6)
    if hook and lines and m.get("hook", True):
        out.append({"type": "hook", "s": 0.0, "e": min(2.6, lines[-1]["e"]), "text": hook})
    last_end = out[-1]["e"] if out else -99
    cut_last = -99
    for b in sorted(raw.get("beats", []), key=lambda b: b.get("line", 0)):
        i = int(b.get("line", 0)) - 1
        if not 0 <= i < len(lines):
            continue
        L = lines[i]
        kind = b.get("type")
        if kind not in m.get("types", ["keyword", "list", "stat", "cutaway"]):
            continue
        s = L["s"]
        if kind in ("keyword", "quote"):
            s = _said_at(b.get("text", ""), L, words or [])
        elif kind == "versus":
            s = _said_at(b.get("a", ""), L, words or [])
        if s < last_end + gap:
            continue
        if kind == "keyword":
            text = _words(b.get("text", ""), 3)
            beat = {"type": "keyword", "s": s, "e": min(max(L["e"], s + 1.4) + 0.4, s + 2.2), "text": text,
                    "icon": b.get("icon") if b.get("icon") in ICONS else ""}
        elif kind == "versus":
            a, bb = _words(b.get("a", ""), 2), _words(b.get("b", ""), 2)
            said = L["text"].lower()
            real = lambda x: x and x.lower() in said and any(re.sub(r"[^a-z]", "", w.lower()) not in STOP for w in x.split())
            if not (real(a) and real(bb)):
                continue  # both sides must be real words from the line, not "is" / "the"
            beat = {"type": "versus", "s": s, "e": max(L["e"] + 0.6, s + 2.0), "text": _words(b.get("text", "") or f"{a} vs {bb}", 5), "a": a, "b": bb}
        elif kind == "quote":
            q = _words(b.get("text", ""), 8)
            said = " ".join(w["w"] for w in (words or []) if L["s"] - 0.01 <= w["s"] <= L["e"]).lower()
            if len(q.split()) < 3 or re.sub(r"[^a-z ]", "", q.lower()) not in re.sub(r"[^a-z ]", "", said):
                continue  # quotes must be word for word
            beat = {"type": "quote", "s": s, "e": min(L["e"] + 0.8, s + 3.2), "text": q}
        elif kind == "list":
            items = [_words(x, 3) for x in (b.get("items") or []) if x.strip()][:5]
            if len(items) < 2:
                continue
            at = _item_times(items, L, words or [])
            # Start just before the first item is said (not at the start of a long line), end after the last.
            first = max(0.0, at[0] - 0.6)
            s = L["s"] + first
            if s < last_end + gap:
                continue
            beat = {"type": "list", "s": s, "e": max(L["s"] + at[-1] + 2.0, s + 2.5), "text": _words(b.get("text", ""), 4),
                    "items": items, "at": [round(x - first, 3) for x in at]}
        elif kind == "stat":
            v = b.get("value")
            nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", L["text"])]
            if v is None or float(v) not in nums:  # only numbers actually said
                continue
            beat = {"type": "stat", "s": s, "e": min(L["e"] + 0.5, s + 2.5), "text": _words(b.get("text", ""), 4), "value": float(v)}
        else:
            if s - cut_last < m.get("cutaway_every", 15):
                continue
            beat = {"type": "cutaway", "s": s, "e": max(min(L["e"], s + 3.0), s + 1.8), "text": _words(b.get("text", ""), 5),
                    "sub": _words(b.get("sub", "") or "", 7), "icon": b.get("icon") if b.get("icon") in ICONS else ""}
            cut_last = s
        if not beat["text"]:
            continue
        out.append(beat)
        last_end = beat["e"]
    return out


def fill_gaps(beats: list[dict], lines: list[dict], keywords: list[str], words: list[dict], tpl: dict) -> list[dict]:
    """No stretch longer than max_gap goes without a graphic: drop in a keyword pop."""
    m = tpl.get("motion", {})
    if "keyword" not in m.get("types", ["keyword"]):
        return beats
    max_gap = m.get("max_gap", 60 / max(1, m.get("per_minute", 6)) * 1.4)
    gap = m.get("min_gap", 3.0)
    out = sorted(beats, key=lambda b: b["s"])
    changed = True
    while changed:
        changed = False
        edges = [0.0] + [x for b in out for x in (b["s"], b["e"])] + [lines[-1]["e"] if lines else 0]
        spans = [(edges[i], edges[i + 1]) for i in range(0, len(edges) - 1, 2)]
        for a, z in spans:
            if z - a < max_gap:
                continue
            mid = (a + z) / 2
            cands = []
            for i, L in enumerate(lines):
                kw = keywords[i][0] if isinstance(keywords[i], list) else keywords[i]
                if not kw.strip() or L["e"] < a + gap or L["s"] > z - gap:
                    continue
                at = _said_at(kw, L, words)  # lands when the keyword is said, even mid-line
                if a + gap <= at <= z - gap:
                    cands.append((abs(at - mid), i, at))
            if not cands:
                continue
            _, i, s = min(cands)
            kw, icon = (keywords[i] + [""])[:2] if isinstance(keywords[i], list) else (keywords[i], "")
            out.append({"type": "keyword", "s": s, "e": s + 2.0, "text": _words(kw, 3), "icon": icon, "fill": True})
            out.sort(key=lambda b: b["s"])
            changed = True
            break
    return out


def render(cut: Path, chosen: list[dict], tpl: dict, work: Path, out: Path, broll_pieces: list[Path] | None = None,
           screens: list[Path] | None = None) -> Path:
    from . import broll
    words, lines = timeline(chosen)
    beats = validate(plan_beats(lines, tpl, work / "beats_raw.json"), lines, tpl, words)
    beats = fill_gaps(beats, lines, line_keywords(lines, work / "keywords.json"), words, tpl)
    total = sum(p["ce"] - p["cs"] for p in chosen)
    beats = broll.place_screens(beats, words, screens or [], work)
    beats = broll.place(beats, total, broll_pieces or [], tpl)
    # Line spans as word index ranges, so the dashboard can show and edit text line by line.
    spans, k = [], 0
    for p in chosen:
        spans.append([k, k + len(p["words"])])
        k += len(p["words"])
    bounds, acc = [], 0.0
    for p in chosen[:-1]:
        acc += p["ce"] - p["cs"]
        bounds.append(round(acc, 3))
    props = {"video": "", "fps": 30, "durationInFrames": int(round(total * 30)), "cuts": bounds,
             "words": words, "beats": beats, "lines": spans, "style": {**DEFAULT_STYLE, **tpl.get("style", {})},
             "face": json.loads((work / "face.json").read_text()) if (work / "face.json").exists() else None}
    (work / "props.json").write_text(json.dumps(props))
    (work / "render.json").write_text(json.dumps({"cut": str(cut), "out": str(out), "music": _music(tpl, cut, work)}))
    return render_props(work)


def render_workout(cut: Path, chosen: list[dict], beats: list[dict], tpl: dict, work: Path, out: Path) -> Path:
    """Workout edits: no spoken words, so just the given graphics over the music cut."""
    total = sum((p["ce"] - p["cs"]) / p.get("speed", 1.0) for p in chosen)
    bounds, acc = [], 0.0
    for p in chosen[:-1]:
        acc += (p["ce"] - p["cs"]) / p.get("speed", 1.0)
        bounds.append(round(acc, 3))
    props = {"video": "", "fps": 30, "durationInFrames": int(round(total * 30)), "cuts": bounds,
             "words": [], "beats": beats, "lines": [], "style": {**DEFAULT_STYLE, **tpl.get("style", {})}, "face": None}
    (work / "props.json").write_text(json.dumps(props))
    (work / "render.json").write_text(json.dumps({"cut": str(cut), "out": str(out), "music": _music(tpl, cut, work)}))
    return render_props(work)


def _music(tpl: dict, cut: Path, work: Path) -> str:
    """Optional bed under talking edits: style.music = "beat" (generated, free) or a path to a track."""
    m = tpl.get("style", {}).get("music")
    if not m:
        return ""
    if m == "beat":
        from .workout import make_beat
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(cut)],
                                   capture_output=True, text=True).stdout or 60)
        return str(make_beat(work / "bed.wav", dur + 2, 96))
    return m if Path(m).exists() else ""


def render_props(work: Path) -> Path:
    """Render props.json over cut.mp4. Also used after a text fix: only this step re-runs (about a minute)."""
    work = Path(work).resolve()  # Remotion runs from motion/, so every path must be absolute
    meta = json.loads((work / "render.json").read_text())
    cut, out = Path(meta["cut"]), Path(meta["out"])
    props = json.loads((work / "props.json").read_text())
    job = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{work.parent.name}_{work.name}")
    pub = MOTION / "public" / "jobs" / job
    pub.mkdir(parents=True, exist_ok=True)
    dst = pub / "cut.mp4"
    dst.unlink(missing_ok=True)
    subprocess.run(["cp", "-c", str(cut), str(dst)], check=True)  # APFS clone: no extra disk
    props["video"] = f"jobs/{job}/cut.mp4"
    for sc in props.get("scenes", []):  # explainer background pictures and window media travel with the job
        for key in ("bg", "media"):
            if sc.get(key) and not sc[key].startswith("jobs/"):
                subprocess.run(["cp", "-c", str(work / sc[key]), str(pub / sc[key])], check=True)
                sc[key] = f"jobs/{job}/{sc[key]}"
    for b in props["beats"]:  # B-roll pieces travel with the job
        if b.get("src") and not b["src"].startswith("jobs/"):
            name = Path(b["src"]).name
            subprocess.run(["cp", "-c", str(work / name), str(pub / name)], check=True)
            b["src"] = f"jobs/{job}/{name}"
    tmp = work / "props.render.json"
    tmp.write_text(json.dumps(props))
    try:
        subprocess.run(["npx", "remotion", "render", meta.get("composition", "TBNEdit"), str(out), f"--props={tmp}",
                        "--codec=h264", "--crf=20", "--log=error",
                        *([f"--browser-executable={BROWSER}"] if BROWSER.exists() else [])], cwd=MOTION, check=True)
    finally:
        shutil.rmtree(pub, ignore_errors=True)
    # Remotion's audio pass drops the mix ~2-3 dB (see the reel taste book): master the final to -14 LUFS.
    tmp_out = out.with_name(out.stem + ".master.mp4")
    music = Path(meta["music"]) if meta.get("music") else None
    if music and music.exists():
        # music bed under the voice: ducks whenever someone talks (sidechain), then the whole mix to -14 LUFS
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(out), "-stream_loop", "-1", "-i", str(music), "-filter_complex",
               "[1:a]volume=0.35,aformat=channel_layouts=stereo[m];[0:a]asplit=2[v][sc];"
               "[m][sc]sidechaincompress=threshold=0.04:ratio=10:attack=20:release=400[md];"
               "[v][md]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp_out)]
    else:
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(out), "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
               "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp_out)]
    r = subprocess.run(cmd)
    if r.returncode == 0:
        tmp_out.replace(out)
    return out


def apply_text(work: Path, lines: list[str] | None, beats: list[dict] | None, style: dict | None = None) -> None:
    """Rob's text fixes. Lines: same word count keeps each word's timing; a different count
    spreads the new words over the line's time, longer words getting more. Beats: edit or remove."""
    props = json.loads((work / "props.json").read_text())
    orig = work / "props.orig.json"
    if not orig.exists():
        orig.write_text(json.dumps(props))
    words, spans = props["words"], props.get("lines") or []
    if lines is not None:
        new_words, new_spans = [], []
        for k, (a, z) in enumerate(spans):
            old = words[a:z]
            text = lines[k] if k < len(lines) else " ".join(w["w"] for w in old)
            toks = text.split()
            try:
                from .transcribe import learn
                learn([w["w"] for w in old], toks)  # Rob's fixes teach the vocabulary for next time
            except Exception:
                pass
            if not toks or not old:
                new_spans.append([len(new_words), len(new_words)])
                continue
            if len(toks) == len(old):
                ws = [{**w, "w": t} for w, t in zip(old, toks)]
            else:
                s0, e1 = old[0]["s"], old[-1]["e"]
                weights = [len(t) + 2 for t in toks]
                total, acc, ws = sum(weights), 0.0, []
                for t, wt in zip(toks, weights):
                    st = s0 + (e1 - s0) * acc / total
                    acc += wt
                    ws.append({"w": t, "s": round(st, 3), "e": round(s0 + (e1 - s0) * acc / total, 3)})
            new_spans.append([len(new_words), len(new_words) + len(ws)])
            new_words += ws
        props["words"], props["lines"] = new_words, new_spans
    if beats is not None:
        keep = []
        for i, b in enumerate(props["beats"]):
            fix = next((x for x in beats if x.get("i") == i), None)
            if fix and fix.get("remove"):
                continue
            if fix:
                for key in ("text", "sub", "a", "b"):
                    if key in fix:
                        b[key] = str(fix[key]).strip()
                if "items" in fix:
                    b["items"] = [x.strip() for x in fix["items"] if x.strip()]
                    b.pop("at", None)  # timings no longer match the new items: spread them evenly
            keep.append(b)
        props["beats"] = keep
    if style:  # colours chosen in the dashboard
        props["style"] = {**props["style"], **{k: v for k, v in style.items() if k in ("accent", "text", "ink")}}
    (work / "props.json").write_text(json.dumps(props))


DEFAULT_STYLE = {"accent": "#EA6113", "ink": "#0B0B0B", "font": "Poppins", "captionSize": 70,
                 "captionY": 0.76, "maxWords": 4, "progressBar": True, "uppercase": True}


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "rerender":
        print(render_props(Path(sys.argv[2])))
    else:
        sys.exit("usage: python -m tbncut.motion rerender <work dir>")
