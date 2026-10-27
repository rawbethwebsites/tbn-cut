"""Posting pack: a draft caption for every finished video in a folder, next to its cover. Nothing is posted.

    python -m tbncut.pack <output folder>

Caption rules come from the TBN reel taste book: hook first, short plain body, then the call to action:
build logs / business videos end on "Comment AUDIT" + theboostnation.space/get-started, everything else on
"Save this". Gemma drafts it from what was actually said; if Gemma is busy, a plain rule-based draft is used.
"""
import json
import re
import sys
from pathlib import Path

from . import gemma

LINK = "theboostnation.space/get-started"
BUSINESS = re.compile(r"\b(app|website|client|business|build|audit|founder|startup|ai|automation|brand|leads?)\b", re.I)
SCHEMA = {"type": "object", "properties": {"hook": {"type": "string"}, "body": {"type": "string"},
                                           "hashtags": {"type": "array", "items": {"type": "string"}}},
          "required": ["hook", "body", "hashtags"]}


def _report(video: Path) -> dict:
    """Find the edit.json that made this video (any mode)."""
    root = video.parent
    for rep in sorted(root.rglob("edit.json"), key=lambda p: -p.stat().st_mtime):
        try:
            d = json.loads(rep.read_text())
        except Exception:
            continue
        if Path(d.get("output", "")).name == video.name:
            return d
    return {}


def caption(video: Path) -> str:
    d = _report(video)
    said = " ".join(k.get("text", "") for k in d.get("kept", []))[:1800]
    topic = d.get("topic", "") or video.stem
    business = bool(BUSINESS.search(said + " " + topic)) and d.get("topic") != "workout"
    cta = f"Comment AUDIT and I'll send you the link.\n{LINK}" if business else "Save this for later."
    try:
        r = gemma.ask("Write an Instagram caption draft for this short video, in a confident, warm, plain voice (no hype, "
                      "no emojis spam, no made-up facts or numbers). hook: one short first line that makes people stop. "
                      "body: 2-3 short lines saying the point, using only what was said. hashtags: 5 relevant hashtags.\n"
                      f"Topic: {topic}\nWhat was said: {said or topic}", schema=SCHEMA, timeout=120)
        hook, body = r["hook"].strip(), r["body"].strip()
        tags = " ".join("#" + re.sub(r"[^A-Za-z0-9]", "", t) for t in r.get("hashtags", [])[:5] if t.strip())
    except Exception:
        first = re.split(r"(?<=[.!?])\s+", said.strip())
        hook = topic if topic != video.stem else (first[0] if first else video.stem)
        body = " ".join(first[1:3]) if len(first) > 1 else ""
        tags = "#TheBoostNation #BuildInPublic" if business else "#GistAndGrind #Discipline #Fitness"
    return f"{hook}\n\n{body}\n\n{cta}\n\n{tags}".strip()


def make(folder: Path) -> Path:
    vids = sorted(p for p in folder.glob("*.mp4") if "(preview)" not in p.name and ".master" not in p.name)
    lines = [f"# Posting pack: {folder.name}", "", "Drafts only. Nothing here has been posted. Check every line before you use it.", ""]
    for v in vids:
        cover = v.with_suffix(".jpg")
        lines += [f"## {v.stem}", "", f"- Video: `{v.name}`", f"- Cover: `{cover.name}`" if cover.exists() else "- Cover: none", "",
                  "```", caption(v), "```", ""]
    out = folder / "Posting pack.md"
    out.write_text("\n".join(lines))
    return out


if __name__ == "__main__":
    print(make(Path(sys.argv[1]).expanduser().resolve()))
