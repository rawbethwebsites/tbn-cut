"""Explainer mode (the "Gist & Grind Ep03" look): your voice over full motion-graphics scenes.

The talking clip is cut to whole sentences as usual, then Qwen turns the story into a
sequence of designed scenes (hook question, big statements, charts that draw in, habit
grids, lists, versus, a stat, an end card). Python checks every scene against what was
actually said, then Remotion renders the TBNExplainer composition over the cut's audio.
"""
import json
import re
from pathlib import Path

from . import edit, motion, story

KEYWORDS: dict = {}  # filled per run with motion.line_keywords for the spoken lines

KINDS = ["hook", "statement", "chart", "tracker", "list", "versus", "stat", "end", "typeon"]

PLAN_SCHEMA = {"type": "object", "properties": {"scenes": {"type": "array", "items": {"type": "object", "properties": {
    "from": {"type": "integer"}, "to": {"type": "integer"},
    "kind": {"type": "string", "enum": KINDS}, "theme": {"type": "string", "enum": ["dark", "cream"]},
    "label": {"type": "string"}, "title": {"type": "string"}, "accent": {"type": "string"}, "sub": {"type": "string"},
    "box": {"type": "string"}, "chart": {"type": "string", "enum": ["wave_vs_steps", "up", "down", "bars", ""]},
    "a": {"type": "string"}, "b": {"type": "string"}, "rows": {"type": "array", "items": {"type": "string"}},
    "items": {"type": "array", "items": {"type": "string"}}, "left": {"type": "string"}, "right": {"type": "string"},
    "value": {"type": "number"}, "unit": {"type": "string"}, "cta": {"type": "string"}, "image": {"type": "string"}},
    "required": ["from", "to", "kind", "theme", "title"]}}}, "required": ["scenes"]}


def units(chosen_parts: list[dict]) -> list[dict]:
    """Spoken units (glued sentences) with their times on the finished timeline."""
    out, t = [], 0.0
    for p in chosen_parts:
        d = p["ce"] - p["cs"]
        ws = [{"w": w["w"], "s": round(w["s"] - p["cs"] + t, 3), "e": round(w["e"] - p["cs"] + t, 3)} for w in p["words"]]
        if out and out[-1]["sent"] == p.get("sent"):
            out[-1]["e"] = t + d
            out[-1]["words"] += ws
            out[-1]["text"] += " " + p["text"]
        else:
            out.append({"sent": p.get("sent"), "s": t, "e": t + d, "words": ws, "text": p["text"]})
        t += d
    # Break long lines (over 4 s) at sentence ends or the biggest pause near the middle, so scenes can change often.
    fine = []
    stack = list(reversed(out))
    while stack:
        u = stack.pop()
        ws = u["words"]
        if u["e"] - u["s"] <= 4.0 or len(ws) < 6:
            fine.append(u)
            continue
        mid = (u["s"] + u["e"]) / 2
        best = min(range(2, len(ws) - 2), key=lambda i: (0 if re.search(r"[.!?,]$", ws[i - 1]["w"]) else 1,
                                                          -min(ws[i]["s"] - ws[i - 1]["e"], 1.0), abs(ws[i]["s"] - mid)))
        a_, b_ = ws[:best], ws[best:]
        mk = lambda w: {"sent": u["sent"], "s": w[0]["s"] if w is b_ else u["s"], "e": u["e"] if w is b_ else w[-1]["e"],
                        "words": w, "text": " ".join(x["w"] for x in w)}
        stack += [mk(b_), mk(a_)]
    return fine


def _plan_chunk(us: list[dict], off: int, part: int, parts: int) -> tuple[list[dict], str]:
    rows = [f"{off + i}. [{u['s']:.1f}-{u['e']:.1f}s] {u['text']}" for i, u in enumerate(us)]
    prompt = (
        "You are the motion designer of a short vertical explainer (Instagram reel). The speaker's voice plays the whole "
        "time; the screen shows designed motion-graphics scenes, not the speaker. Spoken lines, numbered, with times:\n\n"
        + "\n".join(rows) + "\n\n"
        + (f"(This is part {part} of {parts} of the video. " + ("Start with the hook scene. " if part == 1 else "No hook here. ")
           + ("Finish with the end scene. " if part == parts else "No end scene here. ") + "Use the line numbers exactly as given.)\n\n")
        + "Group the lines, in order, into scenes (every line in exactly one scene, from..to inclusive, no gaps, scenes "
        "about 2-6 s). Scene kinds:\n"
        "- hook: first scene only. label = 2-5 word context chip (e.g. 'A VISITOR ASKED ME'), title = the question or "
        "claim that opens the video, in quotes if it's a question someone asked.\n"
        "- statement: a big idea. title 1-5 words, accent = the punch word(s) from the title, optional sub (2-6 words) "
        "and optional box (a 3-8 word line in a red box).\n"
        "- chart: an idea about change over time. chart = wave_vs_steps (ups and downs vs steady progress, e.g. motivation "
        "vs systems), up, down, or bars. a and b = 1-3 word legend labels. title 1-4 words.\n"
        "- tracker: the speaker lists habits/routines/things done daily. rows = 2-4 short row names from the words said. "
        "title like 'SYSTEMS LOOK LIKE'.\n"
        "- list: 2-5 items said; items = short items from the words said.\n"
        "- versus: two things compared; left and right = 1-2 words each.\n"
        "- stat: a number the speaker said; value = that number, unit optional.\n"
        "- typeon: the single most quotable line, typed out on a screen; title = that line (5-12 words, the speaker's "
        "words), accent = one punch word. Use once or twice per video.\n"
        "- end: last scene only. title = the takeaway in 4-8 words (accent the key words), cta = 'SAVE THIS' plus a "
        "short reason if it fits (e.g. 'SAVE THIS FOR MONDAY').\n"
        "image (optional, statement scenes only, at most 3 per video): a short photo prompt for a background picture "
        "that fits the line (e.g. 'empty gym at dawn, one dumbbell on the floor').\n"
        "theme: alternate dark and cream in runs, so the look changes every few scenes. Titles use the speaker's own "
        "words; never invent facts or numbers. Keep titles short: big type.\n"
        'Reply as JSON {"scenes": [{"from": n, "to": n, "kind": "...", "theme": "dark", "label": "", "title": "...", '
        '"accent": "", "sub": "", "box": "", "chart": "", "a": "", "b": "", "rows": [], "items": [], "left": "", '
        '"right": "", "value": 0, "unit": "", "cta": ""}]}.'
    )
    raw, err = [], ""
    for attempt in range(2):  # small models sometimes return broken JSON; one retry
        try:
            raw = story._ask(prompt, PLAN_SCHEMA).get("scenes", [])
            if raw:
                break
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:300]
    return raw, err


def plan(us: list[dict], tpl: dict, cache: Path, chunk: int = 6) -> list[dict]:
    """Scene plan in chunks of `chunk` lines: small requests a local model answers quickly."""
    if cache.exists():
        return json.loads(cache.read_text())
    parts = max(1, -(-len(us) // chunk))
    raw, errs = [], []
    for k in range(parts):
        got, err = _plan_chunk(us[k * chunk:(k + 1) * chunk], k * chunk, k + 1, parts)
        raw += got
        if err:
            errs.append(err)
    if raw:
        cache.write_text(json.dumps(raw, indent=2))
    if errs:
        (cache.parent / "scenes_error.txt").write_text("\n".join(errs))
    return raw


def _clip(s: str, n: int) -> str:
    return " ".join(str(s or "").split()[:n]).strip(" ,;:\"\u201c\u201d")  # models like to wrap titles in quotes


def _times(names: list[str], words: list[dict], s0: float) -> list[float]:
    out, after = [], s0
    for k, n in enumerate(names):
        first = re.sub(r"[^a-z0-9]", "", (n.split() or [""])[0].lower())[:5]
        hit = next((w["s"] for w in words if w["s"] >= after and first and re.sub(r"[^a-z0-9]", "", w["w"].lower()).startswith(first)), None)
        if hit is None:
            hit = after + 0.6
        out.append(round(max(0.0, hit - s0), 3))
        after = hit
    return out


def validate(raw: list[dict], us: list[dict], tpl: dict) -> list[dict]:
    """Every line covered in order; fields trimmed; numbers only if said; hook first, end last."""
    n = len(us)
    if not n:
        return []
    scenes, nxt = [], 0
    for sc in sorted(raw, key=lambda x: x.get("from", 0)):
        a, z = int(sc.get("from", nxt)), int(sc.get("to", nxt))
        a, z = max(a, nxt), min(max(a, z), n - 1)
        if a > z or a >= n:
            continue
        kind = sc.get("kind") if sc.get("kind") in KINDS else "statement"
        words = [w for u in us[a:z + 1] for w in u["words"]]
        said = " ".join(w["w"] for w in words).lower()
        out = {"kind": kind, "s": us[a]["s"], "e": us[z]["e"], "theme": "cream" if sc.get("theme") == "cream" else "dark",
               "title": _clip(sc.get("title"), 12 if kind == "typeon" else 9) or _clip(us[a]["text"], 5), "accent": _clip(sc.get("accent"), 3)}
        for k, lim in (("label", 5), ("sub", 7), ("box", 9), ("cta", 6), ("image", 14)):
            if sc.get(k):
                out[k] = _clip(sc[k], lim)
        if kind == "chart":
            out["chart"] = {"type": sc.get("chart") or "wave_vs_steps", "a": _clip(sc.get("a"), 3), "b": _clip(sc.get("b"), 3)}
        if kind == "tracker":
            out["rows"] = [_clip(r, 3) for r in (sc.get("rows") or []) if str(r).strip()][:4] or ["Habit tracker"]
            out["at"] = _times(out["rows"], words, out["s"])
        if kind == "list":
            out["items"] = [_clip(r, 4) for r in (sc.get("items") or []) if str(r).strip()][:5]
            if len(out["items"]) < 2:
                out["kind"] = "statement"
            else:
                out["at"] = _times(out["items"], words, out["s"])
        if kind == "versus":
            out["left"], out["right"] = _clip(sc.get("left"), 2), _clip(sc.get("right"), 2)
            if not (out["left"] and out["right"]):
                out["kind"] = "statement"
        if kind == "stat":
            v = sc.get("value")
            nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", said)]
            if v is None or float(v) not in nums:
                out["kind"] = "statement"
            else:
                out["value"], out["unit"] = float(v), _clip(sc.get("unit"), 1)
        prev = scenes[-1] if scenes else None
        if (out["kind"] == "versus" and prev and prev["kind"] in ("versus", "statement") and prev.get("pair") ==
                (out["left"], out["right"])):
            prev["e"] = out["e"]  # the same pair split over two scenes: one card for both
            nxt = z + 1
            continue
        if out["kind"] == "versus" and out["title"].lower() in (out["left"].lower(), out["right"].lower()):
            # "No camera" vs "No editing" is a list said in a row, not two sides: one statement holds both
            out.update(kind="statement", title=f"{out['left']}. {out['right']}.", accent=out["left"].split()[0],
                       pair=(out.pop("left"), out.pop("right")))
        scenes.append(out)
        nxt = z + 1
    if nxt < n:  # anything left over joins the last scene
        if scenes:
            scenes[-1]["e"] = us[-1]["e"]
        else:
            scenes.append({"kind": "statement", "s": us[0]["s"], "e": us[-1]["e"], "theme": "dark", "title": _clip(us[0]["text"], 5)})
    # Long scenes (over max_scene s) get split at line boundaries; the extra parts become big statements
    # titled with that line's keyword, so the screen keeps changing like the original Ep03.
    max_scene = tpl.get("explainer", {}).get("max_scene", 5.5)
    kws = KEYWORDS.get("value") or []
    split = []
    for sc in scenes:
        if sc["e"] - sc["s"] <= max_scene or sc["kind"] in ("hook",):
            split.append(sc)
            continue
        idx = [i for i, u in enumerate(us) if u["s"] >= sc["s"] - 0.01 and u["e"] <= sc["e"] + 0.01]
        cur_end = sc["s"] + max_scene
        first = dict(sc)
        rest = [i for i in idx if us[i]["s"] >= cur_end - 0.01]
        if not rest:
            split.append(sc)
            continue
        first["e"] = us[rest[0]]["s"]
        split.append(first)
        theme = "cream" if sc["theme"] == "dark" else "dark"
        for i in rest:
            kw = (kws[i][0] if i < len(kws) and isinstance(kws[i], list) else "") or _clip(us[i]["text"], 3)
            split.append({"kind": "statement", "s": us[i]["s"], "e": us[i]["e"], "theme": theme, "title": _clip(kw, 4),
                          "accent": _clip(kw, 4).split()[-1] if kw else ""})
            theme = "cream" if theme == "dark" else "dark"
    scenes = split
    for sc in scenes:
        sc.pop("pair", None)
    # close any gaps between scenes (silence between cuts)
    for x, y in zip(scenes, scenes[1:]):
        x["e"] = y["s"]
    scenes[0]["s"] = 0.0
    if scenes[0]["kind"] != "hook":
        scenes[0]["kind"] = "hook"
    if len(scenes) > 1 and scenes[-1]["kind"] != "end":
        scenes[-1]["kind"] = "end"
    if not scenes[-1].get("cta"):
        scenes[-1]["cta"] = tpl.get("explainer", {}).get("cta", "SAVE THIS")
    return scenes


def run(video: Path, tpl: dict, out_dir: Path, log, sentences_fn) -> Path:
    """sentences_fn = run._sentences (kept there so caches are shared with the other modes)."""
    ex = tpl.get("explainer", {})
    sents = sentences_fn(video, 0, tpl, out_dir)
    pool = [s for s in sents if "dropped" not in s]
    work = out_dir / video.stem / "explainer"
    work.mkdir(parents=True, exist_ok=True)
    log(f"{video.name}: editor (Qwen) choosing the story")
    choice = story.choose(pool, tpl, work / "story.json")
    chosen = story.to_parts(story.assemble(pool, choice, tpl), tpl)
    cut = edit.render([video], chosen, {**tpl, "captions": {"on": False}, "zoom": {}}, work, work / "cut.mp4")
    us = units(chosen)
    log(f"{video.name}: Qwen designing scenes for {len(us)} spoken lines")
    KEYWORDS["value"] = motion.line_keywords([{"text": u["text"]} for u in us], work / "keywords.json")
    raw = plan(us, tpl, work / "scenes_raw.json")
    if not raw:
        log(f"{video.name}: no model answered for scenes, using word rules")
        raw = rule_plan(us, KEYWORDS["value"] or [])
    scenes = validate(raw, us, tpl)
    log(f"{video.name}: {len(scenes)} scenes: " + ", ".join(s["kind"] for s in scenes))
    add_images(scenes, work, log)
    words = [w for u in us for w in u["words"]]
    total = sum(p["ce"] - p["cs"] for p in chosen)
    props = {"video": "", "fps": 30, "durationInFrames": int(round(total * 30)), "words": words, "scenes": scenes,
             "series": ex.get("series", "GIST & GRIND"), "episode": ex.get("episode", ""), "handle": ex.get("handle", "@rawbeth"),
             "accent": ex.get("accent", "#D7141A"), "sfx": True, "beats": []}
    (work / "props.json").write_text(json.dumps(props))
    final = out_dir / f"{video.stem} - explainer.mp4"
    (work / "render.json").write_text(json.dumps({"cut": str(cut), "out": str(final), "composition": "TBNExplainer"}))
    motion.render_props(work)
    (work / "edit.json").write_text(json.dumps({"video": str(video), "template": "Explainer", "output": str(final),
                                                "seconds": round(total, 1), "topic": choice.get("topic", ""),
                                                "kept": [{"t": f"{u['s']:.1f}-{u['e']:.1f}", "text": u["text"]} for u in us],
                                                "scenes": scenes, "dropped": []}, indent=2))
    log(f"done -> {final.name}")
    return final


def rule_plan(us: list[dict], kws: list) -> list[dict]:
    """No model available: scene types from simple word rules, titles from the keyword pass (or the words)."""
    out, i, theme = [], 0, "dark"
    while i < len(us):
        u = us[i]
        txt = u["text"].lower()
        kw = (kws[i][0] if i < len(kws) and isinstance(kws[i], list) else "") or " ".join(u["text"].split()[:4])
        sc = {"from": i, "to": i, "theme": theme, "title": kw, "accent": kw.split()[-1] if kw else ""}
        if i == 0:
            sc.update(kind="hook", title=" ".join(u["text"].split()[:9]))
        elif re.search(r"\b(habit|routine|track|every day|daily|morning|evening)\b", txt):
            rows = re.findall(r"\b(habit \w+|morning routine|evening routine|\w+ routine|\w+ tracker)\b", txt) or ["Habit tracker"]
            sc.update(kind="tracker", title="Systems look like", accent="look like", rows=list(dict.fromkeys(r.title() for r in rows))[:3])
        elif re.search(r"\b(vs|versus)\b|\bor\b.*\?", txt):
            m = re.search(r"(\w+)\s+(?:vs|versus|or)\s+(\w+)", txt)
            sc.update(kind="versus", left=m.group(1) if m else kw, right=m.group(2) if m else "")
        elif re.search(r"\d", txt):
            n = re.search(r"\d[\d,]*\.?\d*", txt).group(0).replace(",", "")
            sc.update(kind="stat", value=float(n))
        elif re.search(r"\b(nobody|never|always|truth|remember|that's why|the secret)\b", txt) and len(u["text"].split()) <= 14:
            sc.update(kind="typeon", title=u["text"], accent=kw.split()[-1] if kw else "")
        elif re.search(r"\b(feel|motivation|up and down|ups|downs|grow|progress|consisten)", txt):
            sc.update(kind="chart", chart="wave_vs_steps", a="How you feel", b="What gets done")
        else:
            sc.update(kind="statement")
        if i == len(us) - 1 and i > 0:
            sc.update(kind="end", cta="SAVE THIS")
        out.append(sc)
        if i % 2 == 1:
            theme = "cream" if theme == "dark" else "dark"
        i += 1
    return out


def add_images(scenes: list[dict], work: Path, log) -> None:
    """Background photos for scenes that asked for one, made locally (Draw Things). Skipped if it isn't on."""
    from . import imagegen
    want = [s for s in scenes if s.get("image") and s["kind"] == "statement"][:3]
    if not want:
        return
    if not imagegen.available():
        log("images: Draw Things API isn't on, so no background pictures (scenes still render)")
        return
    for k, s in enumerate(want):
        img = imagegen.make(s["image"], work / f"bg_{k}.png")
        if img:
            s["bg"] = img.name
            log(f"images: made a background for '{s['title']}'")
