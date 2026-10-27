"""Step 2: turn words into clean phrases. Rules only, so every cut is explainable.

Drops filler words, long silences and false starts (a phrase the speaker restarts:
its opening words come again right after, so the later take is kept).
"""
import re

FILLERS = {"um", "uh", "erm", "er", "ah", "uhm", "hmm", "mm"}


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def phrases(words: list[dict], gap: float = 0.55) -> list[dict]:
    """Group words into phrases split at pauses longer than `gap`, minus fillers."""
    out, cur = [], []
    for w in words:
        if norm(w["w"]) in FILLERS:
            continue
        if cur and w["s"] - cur[-1]["e"] > gap:
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return [{"s": p[0]["s"], "e": p[-1]["e"], "words": p,
             "text": " ".join(x["w"] for x in p)} for p in out]


def _starts_same(a: dict, b: dict, n: int = 3) -> bool:
    wa = [norm(w["w"]) for w in a["words"]][:n]
    wb = [norm(w["w"]) for w in b["words"]][:n]
    return len(wa) >= 2 and len(wb) >= 2 and wa[:min(len(wa), len(wb))] == wb[:min(len(wa), len(wb))]


def drop_retakes(ps: list[dict], window: int = 3) -> list[dict]:
    """If a phrase's opening words reappear within the next few phrases, it was a false start."""
    keep = []
    for i, p in enumerate(ps):
        later = ps[i + 1:i + 1 + window]
        if any(_starts_same(p, q) for q in later):
            p = {**p, "dropped": "retake"}
        keep.append(p)
    return keep


def drop_junk(ps: list[dict], min_words: int = 3, min_prob: float = 0.45) -> list[dict]:
    """Very short or mumbled phrases (low Whisper confidence) go."""
    out = []
    for p in ps:
        probs = [w["p"] for w in p["words"]]
        if "dropped" not in p:
            if len(p["words"]) < min_words:
                p = {**p, "dropped": "too short"}
            elif sum(probs) / len(probs) < min_prob:
                p = {**p, "dropped": "unclear"}
        out.append(p)
    return out


def clean(words: list[dict], pad: float = 0.08, gap: float = 0.55) -> list[dict]:
    """gap: pause (s) that starts a new phrase; smaller = more, shorter cuts (faster pace)."""
    ps = drop_junk(drop_retakes(phrases(words, gap)))
    for p in ps:
        p["cs"] = max(0.0, p["s"] - pad)
        p["ce"] = p["e"] + pad
    return ps
