"""Step 1: words with timestamps, from the free local Whisper model."""
import json
from pathlib import Path

MODEL_DIR = Path.home() / ".ai-video-editor/models/faster-whisper-small"
_model = None


def _load():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        src = str(MODEL_DIR) if MODEL_DIR.exists() else "small"
        _model = WhisperModel(src, device="cpu", compute_type="int8")
    return _model


def transcribe(video: Path, out: Path) -> list[dict]:
    """Returns [{"w": word, "s": start, "e": end, "p": prob}], cached in out."""
    if out.exists():
        return apply_vocab(json.loads(out.read_text()))
    out.parent.mkdir(parents=True, exist_ok=True)
    segments, _ = _load().transcribe(
        str(video), language="en", word_timestamps=True, vad_filter=True,
        # Keep "um" / "uh" in the text so the cutter can see them.
        initial_prompt="Um, uh, so, like, you know, I mean.",
    )
    words = []
    for seg in segments:
        for w in seg.words or []:
            words.append({"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3),
                          "p": round(w.probability, 3)})
    out.write_text(json.dumps(words))
    return apply_vocab(words)


VOCAB = Path(__file__).resolve().parent.parent / "vocab.json"


def _norm(w: str) -> str:
    import re
    return re.sub(r"[^a-z0-9']", "", w.lower())


def apply_vocab(words: list[dict]) -> list[dict]:
    """Swap known mishearings (1-3 word phrases) for the right words, keeping punctuation and timing."""
    import json as _j
    if not VOCAB.exists():
        return words
    v = _j.loads(VOCAB.read_text())
    fixes = {**v.get("fixes", {}), **v.get("learned", {})}
    table = {tuple(k.lower().split()): val.split() for k, val in fixes.items() if k.strip()}
    out, i = [], 0
    while i < len(words):
        for n in (3, 2, 1):
            key = tuple(_norm(w["w"]) for w in words[i:i + n])
            if len(key) == n and key in table:
                rep = table[key]
                span = words[i:i + n]
                tail = "".join(ch for ch in span[-1]["w"] if not ch.isalnum() and ch != "'")[-1:]  # keep end punctuation
                s0, e1 = span[0]["s"], span[-1]["e"]
                for k, r in enumerate(rep):
                    out.append({**span[min(k, n - 1)], "w": r + (tail if k == len(rep) - 1 else ""),
                                "s": round(s0 + (e1 - s0) * k / len(rep), 3), "e": round(s0 + (e1 - s0) * (k + 1) / len(rep), 3)})
                i += n
                break
        else:
            out.append(words[i])
            i += 1
    return out


def learn(old: list[str], new: list[str]) -> None:
    """Remember single-word fixes made in the dashboard (same word count only, so it's a clean swap)."""
    import json as _j
    if len(old) != len(new) or not VOCAB.exists():
        return
    v = _j.loads(VOCAB.read_text())
    changed = False
    for a, b in zip(old, new):
        na, nb = _norm(a), _norm(b)
        if na and nb and na != nb and len(na) > 2:
            v.setdefault("learned", {})[na] = b.strip(".,!?;:")
            changed = True
    if changed:
        VOCAB.write_text(_j.dumps(v, indent=2))
