"""Sentence-level editing: whole sentences are the unit, so cuts always make sense.

1. sentences(): words -> complete sentences (punctuation, or a long pause), fillers out,
   restarted sentences (false starts) dropped.
2. parts(): inside a kept sentence, long pauses are trimmed out, but no piece is
   shorter than min_part seconds: short pieces keep the pause instead of becoming a cut.
3. choose(): the local Qwen 35B (smarter than Gemma at text) picks which sentences tell
   a clear story; Python checks it (valid, in order, within length) and falls back to scores.
"""
import json
import os
import re
import urllib.request
from pathlib import Path

from .cuts import FILLERS, norm

OLLAMA = "http://127.0.0.1:11434/api/chat"
EDITOR_MODEL = os.environ.get("TBN_CUT_EDITOR_MODEL", "qwen3.5-35b-64k")  # the file is Qwen3.6-35B-A3B Uncensored; only ~3B active, so fast


def sentences(words: list[dict], max_pause: float = 1.2) -> list[dict]:
    out, cur = [], []
    for i, w in enumerate(words):
        if norm(w["w"]) in FILLERS:
            continue
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt and norm(w["w"]) and norm(w["w"]) == norm(nxt["w"]) and nxt["s"] - w["e"] < 1.5:
            continue  # stutter: "before, before he gets paid" keeps the second one
        if cur and w["s"] - cur[-1]["e"] > max_pause:
            out.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?]$", w["w"]):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    sents = [{"s": ws[0]["s"], "e": ws[-1]["e"], "words": ws, "text": " ".join(x["w"] for x in ws)} for ws in out if ws]
    # False starts: a sentence whose opening words come again in one of the next two.
    for i, a in enumerate(sents):
        wa = [norm(w["w"]) for w in a["words"]][:3]
        for b in sents[i + 1:i + 3]:
            wb = [norm(w["w"]) for w in b["words"]][:3]
            if len(wa) == 3 and wa == wb:
                a["dropped"] = "retake"
    for a in sents:
        probs = [w["p"] for w in a["words"]]
        if "dropped" not in a and sum(probs) / len(probs) < 0.4:
            a["dropped"] = "unclear"
    return sents


def parts(sent: dict, trim: float = 0.45, min_part: float = 1.0, pad: float = 0.08) -> list[dict]:
    """Pieces of one sentence with long pauses cut out. Pieces under min_part are merged."""
    groups, cur = [], [sent["words"][0]]
    for w in sent["words"][1:]:
        if w["s"] - cur[-1]["e"] > trim:
            groups.append(cur)
            cur = []
        cur.append(w)
    groups.append(cur)
    # Merge any piece shorter than min_part into its shorter neighbour (keeping the pause, not cutting).
    span = lambda g: g[-1]["e"] - g[0]["s"]
    while len(groups) > 1:
        short = [i for i, g in enumerate(groups) if span(g) < min_part]
        if not short:
            break
        i = short[0]
        if i == 0:
            j = 1
        elif i == len(groups) - 1:
            j = i - 1
        else:
            j = i - 1 if span(groups[i - 1]) <= span(groups[i + 1]) else i + 1
        lo, hi = min(i, j), max(i, j)
        groups[lo:hi + 1] = [groups[lo] + groups[hi]]
    return [{"cs": max(0.0, g[0]["s"] - pad), "ce": g[-1]["e"] + pad, "s": g[0]["s"], "e": g[-1]["e"],
             "words": g, "text": " ".join(w["w"] for w in g)} for g in groups]


FALLBACK_MODEL = os.environ.get("TBN_CUT_VISION_MODEL", "gemma4-uncensored-vision")  # already loaded for scoring; used when Qwen can't load in time
LAST_MODEL = {"name": EDITOR_MODEL}


def _ask(prompt: str, schema: dict, timeout: int = 150) -> dict:
    """Editor model call: Qwen first; if it doesn't answer in time (load stuck, memory), Gemma."""
    err = None
    from . import gemma
    models = (EDITOR_MODEL, FALLBACK_MODEL) if not LAST_MODEL.get("qwen_down") else (FALLBACK_MODEL,)
    if gemma.STATE["down"]:
        models = tuple(m for m in models if m != FALLBACK_MODEL)
    if not models:
        raise RuntimeError("editor models busy earlier in this run")
    for model in models:
        body = {"model": model, "stream": False, "think": False, "format": schema, "keep_alive": "15m",
                "messages": [{"role": "user", "content": prompt}], "options": {"temperature": 0.2, "num_ctx": 8192}}
        req = urllib.request.Request(OLLAMA, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(json.load(r)["message"]["content"])
            LAST_MODEL["name"] = model
            return out
        except Exception as e:  # timeout, broken JSON, model missing: try the next one
            err = e
            if "timed out" in str(e).lower():
                if model == EDITOR_MODEL:
                    LAST_MODEL["qwen_down"] = True  # don't wait on Qwen again this run
                else:
                    gemma.STATE["down"] = True
    raise RuntimeError(f"editor models failed: {err}")


CHOICE_SCHEMA = {"type": "object", "properties": {
    "topic": {"type": "string"},
    "off_topic": {"type": "array", "items": {"type": "integer"}},
    "hook": {"type": ["integer", "null"]},
    "keep": {"type": "array", "items": {"type": "integer"}}}, "required": ["topic", "off_topic", "hook", "keep"]}


def choose(sents: list[dict], tpl: dict, cache: Path, clip_names: list[str] | None = None) -> dict:
    """{"hook": i|None, "keep": [i...]} over the kept sentences, decided by the editor model."""
    if cache.exists():
        return json.loads(cache.read_text())
    target, limit = tpl.get("target_seconds", min(45, tpl["max_seconds"])), tpl["max_seconds"]
    rows = []
    for i, s in enumerate(sents):
        clip = f"[clip {s.get('src', 0) + 1}] " if clip_names else ""
        rows.append(f"{i}. {clip}({s['e'] - s['s']:.1f}s, looks {s.get('vis', 5)}/10) {s['text']}")
    prompt = (
        "You are the video editor for a short vertical video (Instagram/TikTok). Below are the complete sentences "
        "the speaker said, numbered, in time order" + (" per clip" if clip_names else "") +
        ", with length and how good the shot looks.\n\n" + "\n".join(rows) + "\n\n"
        f"Build the best short of about {target:.0f}s (never more than {limit:.0f}s total):\n"
        + (f"The creator wants this video to be about: {tpl['focus']}. Build it around the sentences on that.\n" if tpl.get("focus") else "") +
        "- topic: one line, what the video is about.\n"
        "- off_topic: EVERY sentence number that is not about that topic: chat with people in the room, phone calls, "
        "jokes, food, asking someone something, 'that's what I was going to say', mumbles. Be strict.\n"
        "- keep: sentence numbers to use, in the order they should play. Keep the story clear: a viewer who never saw "
        "the raw video must understand it. Prefer whole runs of consecutive sentences. Never keep a sentence that "
        "only makes sense with a sentence you dropped (e.g. starts with 'that's why' or 'so' after a dropped point). "
        "Drop side talk with people in the room, repeats, rambling, setup chatter and anything off topic.\n"
        "- hook: one sentence number to play first as the opener, only if it works on its own and makes people "
        "want to keep watching (a bold claim, the problem, the result); otherwise null. Don't also list it in keep.\n"
        'Reply as JSON {"topic": "...", "off_topic": [n, ...], "hook": n or null, "keep": [n, ...]}.'
    )
    try:
        raw = _ask(prompt, CHOICE_SCHEMA)
    except Exception as e:
        raw = {"topic": "", "hook": None, "keep": [], "error": str(e)}
    cache.write_text(json.dumps(raw, indent=2))
    return raw


def assemble(sents: list[dict], choice: dict, tpl: dict) -> list[dict]:
    """Validate the editor's choice and fall back to scores when it's unusable. Returns ordered sentences."""
    limit = tpl["max_seconds"]
    n = len(sents)
    off = {i for i in choice.get("off_topic", []) if isinstance(i, int)}
    keep = [i for i in choice.get("keep", []) if isinstance(i, int) and 0 <= i < n and i not in off]
    keep = list(dict.fromkeys(keep))  # no duplicates
    # Within one clip, keep time order (the editor may order clips, not scramble a clip).
    by_clip: dict[int, list[int]] = {}
    for i in keep:
        by_clip.setdefault(sents[i].get("src", 0), []).append(i)
    order = {c: iter(sorted(ix)) for c, ix in by_clip.items()}
    keep = [next(order[sents[i].get("src", 0)]) for i in keep]
    hook = choice.get("hook")
    hook = hook if isinstance(hook, int) and 0 <= hook < n and hook not in keep and hook not in off else None
    dur = lambda ix: sum(sents[i]["e"] - sents[i]["s"] for i in ix)
    if dur(keep) < min(12, sum(s["e"] - s["s"] for s in sents) * 0.3):
        # Editor gave too little: take the best-scored sentences, story order.
        ranked = sorted(range(n), key=lambda i: -sents[i].get("score", 5))
        keep = []
        for i in ranked:
            if dur(keep + [i]) <= limit * 0.9:
                keep.append(i)
        keep.sort(key=lambda i: (sents[i].get("src", 0), sents[i]["s"]))
        hook = None
    while keep and dur(keep) + (dur([hook]) if hook is not None else 0) > limit:
        keep.remove(min(keep, key=lambda i: sents[i].get("score", 5)))  # trim the weakest
    return ([sents[hook]] if hook is not None else []) + [sents[i] for i in keep]


def _glue(chosen: list[dict], max_gap: float = 1.0) -> list[dict]:
    """Sentences that follow each other in the raw clip play as one continuous piece: no cut between them."""
    out = []
    for s in chosen:
        prev = out[-1] if out else None
        if prev and prev.get("src", 0) == s.get("src", 0) and 0 <= s["s"] - prev["e"] <= max_gap:
            out[-1] = {**prev, "e": s["e"], "words": prev["words"] + s["words"], "text": prev["text"] + " " + s["text"],
                       "score": max(prev.get("score") or 0, s.get("score") or 0)}
        else:
            out.append(dict(s))
    return out


def to_parts(chosen: list[dict], tpl: dict) -> list[dict]:
    """Flatten chosen sentences into renderable pieces (each keeps its clip, words and sentence id)."""
    out = []
    min_cut = tpl.get("min_cut", 1.0)
    for k, s in enumerate(_glue(chosen)):
        for p in parts(s, trim=tpl.get("pause_gap", 0.45), min_part=min_cut):
            out.append({**p, "src": s.get("src", 0), "sent": k, "score": s.get("score")})
    # Last rule: no piece under min_cut plays on its own. Join it to the neighbour it follows in the raw
    # clip (keeping the pause between), or drop it if it stands alone (a tiny stray sentence).
    i = 0
    while i < len(out):
        p = out[i]
        if p["ce"] - p["cs"] >= min_cut:
            i += 1
            continue
        prev = out[i - 1] if i > 0 else None
        nxt = out[i + 1] if i + 1 < len(out) else None
        if prev and prev["src"] == p["src"] and 0 <= p["s"] - prev["e"] <= 2.5:
            out[i - 1] = {**prev, "ce": p["ce"], "e": p["e"], "words": prev["words"] + p["words"], "text": prev["text"] + " " + p["text"]}
            del out[i]
        elif nxt and nxt["src"] == p["src"] and 0 <= nxt["s"] - p["e"] <= 2.5:
            out[i + 1] = {**nxt, "cs": p["cs"], "s": p["s"], "words": p["words"] + nxt["words"], "text": p["text"] + " " + nxt["text"]}
            del out[i]
        else:
            del out[i]
    return out


MANY_SCHEMA = {"type": "object", "properties": {"shorts": {"type": "array", "items": {"type": "object", "properties": {
    "title": {"type": "string"},
    "hook": {"type": ["integer", "null"]},
    "keep": {"type": "array", "items": {"type": "integer"}}}, "required": ["title", "hook", "keep"]}}},
    "required": ["shorts"]}


def choose_many(sents: list[dict], tpl: dict, n: int, cache: Path) -> list[dict]:
    """Several separate shorts from one long video: each its own clear topic, no sentence used twice."""
    if cache.exists():
        return json.loads(cache.read_text())
    target, limit = tpl.get("target_seconds", 40), tpl["max_seconds"]
    rows = [f"{i}. ({s['e'] - s['s']:.1f}s) {s['text']}" for i, s in enumerate(sents)]
    prompt = (
        "You are cutting a long talking video into separate short vertical videos (Instagram/TikTok). Below are the "
        "complete sentences the speaker said, numbered, in time order, with length.\n\n" + "\n".join(rows) + "\n\n"
        f"Find up to {n} different shorts. Each short is about ONE idea, makes sense on its own to someone who never "
        f"saw the rest, and runs about {target:.0f}s (never more than {limit:.0f}s). For each give: title (a 3-7 word "
        "hook title), keep (sentence numbers in play order, prefer whole consecutive runs), hook (one sentence number to "
        "play first if it works alone and grabs attention, else null; not also in keep). Never use a sentence in two "
        "shorts. Leave out side talk, repeats and setup chatter. Fewer good shorts beat more weak ones.\n"
        'Reply as JSON {"shorts": [{"title": "...", "hook": n or null, "keep": [n, ...]}]}.'
    )
    try:
        raw = _ask(prompt, MANY_SCHEMA).get("shorts", [])
    except Exception as e:
        raw = []
    used, out = set(), []
    for sh in raw[:n]:
        keep = [i for i in sh.get("keep", []) if isinstance(i, int) and 0 <= i < len(sents) and i not in used]
        if sum(sents[i]["e"] - sents[i]["s"] for i in keep) < 12:
            continue  # too thin to be a short
        used.update(keep)
        hook = sh.get("hook")
        if isinstance(hook, int) and hook in used:
            hook = None
        if isinstance(hook, int):
            used.add(hook)
        out.append({"title": str(sh.get("title", ""))[:60], "hook": hook, "keep": keep, "off_topic": []})
    cache.write_text(json.dumps(out, indent=2))
    return out
