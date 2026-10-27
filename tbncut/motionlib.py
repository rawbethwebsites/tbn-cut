"""Motion template library: templates/motion/<name>.json.

A template is a small JSON combo of motion *primitives* (built in motion/src/OsMotion.tsx + Explainer.tsx).
Python validates every template, so Gemma can pick one for a script or write a brand-new one from a brief
without touching any code: it only ever chooses values from PRIMITIVES below.

    python -m tbncut.motionlib list
    python -m tbncut.motionlib show cds-os
    python -m tbncut.motionlib pick script.txt                    # Gemma picks the best template for a script
    python -m tbncut.motionlib create "calm luxury, slow reveals" --name luxe   # Gemma writes a new template
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "templates" / "motion"

# The vocabulary. Each value is something the renderer can draw; the text is what Gemma reads to choose.
PRIMITIVES = {
    "title": {"spring": "words pop up one after another with a springy bounce",
              "maskrise": "letters rise out of an invisible mask, one after another (cdsigrl.org boot wordmark)"},
    "stat": {"count": "a big number counts up",
             "gauge": "a 270-degree gauge draws itself, ticks pop in, the needle climbs then snaps home with an elastic bounce while the number counts"},
    "transition": {"fade": "scenes fade into each other",
                   "shutter": "two panels close over the end of a scene and split open (top up, bottom down) on the next"},
    "backdrop": {"plain": "flat brand colour behind every scene", "grid": "a faint blueprint grid behind every scene"},
    "window": {"pop": "pictures and screen recordings pop in inside a desktop window",
               "genie": "pictures and screen recordings pour out of the dock like a macOS genie and fold back at the end"},
}
NUMBERS = {"speed": (0.6, 1.6, 1.0, "1 = cdsigrl.org timing; lower is slower, higher is faster"),
           "stagger": (0.02, 0.1, 0.045, "seconds between letters when title is maskrise")}
DEFAULT = "classic"


def validate(t: dict) -> dict:
    """Keep only known primitives; unknown or bad values fall back to the classic look."""
    m = t.get("motion", t)
    out = {}
    for k, opts in PRIMITIVES.items():
        out[k] = m.get(k) if m.get(k) in opts else next(iter(opts))
    for k, (lo, hi, dflt, _) in NUMBERS.items():
        try:
            out[k] = round(min(hi, max(lo, float(m.get(k, dflt)))), 3)
        except (TypeError, ValueError):
            out[k] = dflt
    return out


def names() -> list[str]:
    return sorted(p.stem for p in LIB.glob("*.json"))


def load(name: str) -> dict:
    """The validated motion pack for a template name (or a path to a template file)."""
    p = Path(name) if name.endswith(".json") else LIB / f"{name}.json"
    if not p.exists():
        raise SystemExit(f"no motion template {name!r}. Have: {', '.join(names())}")
    return validate(json.loads(p.read_text()))


def catalogue() -> str:
    lines = []
    for n in names():
        t = json.loads((LIB / f"{n}.json").read_text())
        lines.append(f"- {n}: {t.get('description', '')} Use for: {t.get('when_to_use', '')}")
    return "\n".join(lines)


def teach() -> str:
    """What Gemma reads before choosing or writing a template."""
    prim = "\n".join(f"- {k}: " + "; ".join(f'"{v}" = {d}' for v, d in opts.items()) for k, opts in PRIMITIVES.items())
    nums = "\n".join(f"- {k}: number {lo}-{hi} ({d})" for k, (lo, hi, _, d) in NUMBERS.items())
    return f"Motion primitives you can combine:\n{prim}\n{nums}\n\nTemplates in the library:\n{catalogue()}"


def pick(script: str) -> str:
    """Gemma chooses the library template that fits a script best (classic when Gemma is unavailable)."""
    from tbncut import gemma
    schema = {"type": "object", "properties": {"template": {"type": "string", "enum": names()}, "why": {"type": "string"}},
              "required": ["template"]}
    prompt = (f"You choose the motion style for a short vertical video.\n{teach()}\n\nScript:\n{script[:2500]}\n\n"
              "Pick the ONE template whose 'Use for' fits this script best. Reply as JSON.")
    try:
        r = gemma.ask(prompt, schema=schema, timeout=120)
        return r["template"] if r.get("template") in names() else DEFAULT
    except Exception as e:  # Ollama busy or down: the classic look is always safe
        print(f"[motion] gemma unavailable ({e}); using {DEFAULT}", file=sys.stderr)
        return DEFAULT


def create(brief: str, name: str) -> Path:
    """Gemma writes a new template from a brief, using only the primitives; Python validates and saves it."""
    from tbncut import gemma
    name = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "gemma-template"
    motion_schema = {"type": "object", "properties": {
        **{k: {"type": "string", "enum": list(v)} for k, v in PRIMITIVES.items()},
        **{k: {"type": "number"} for k in NUMBERS}}, "required": list(PRIMITIVES) + list(NUMBERS)}
    schema = {"type": "object", "properties": {"description": {"type": "string"}, "when_to_use": {"type": "string"},
                                               "motion": motion_schema}, "required": ["description", "when_to_use", "motion"]}
    prompt = (f"You design motion templates for short vertical videos.\n{teach()}\n\n"
              f"Brief from the editor: {brief}\n\nWrite ONE new template that fits the brief, combining the primitives "
              "(it should differ from the existing templates). description = what it looks like in one sentence; "
              "when_to_use = which videos it suits. Reply as JSON.")
    r = gemma.ask(prompt, schema=schema, timeout=180)
    t = {"name": name, "description": str(r.get("description", ""))[:300], "when_to_use": str(r.get("when_to_use", ""))[:200],
         "motion": validate(r.get("motion", {})), "made_by": "gemma", "brief": brief}
    out = LIB / f"{name}.json"
    out.write_text(json.dumps(t, indent=1))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("teach")
    s = sub.add_parser("show"); s.add_argument("name")
    s = sub.add_parser("pick"); s.add_argument("script")
    s = sub.add_parser("create"); s.add_argument("brief"); s.add_argument("--name", required=True)
    a = ap.parse_args()
    if a.cmd == "list":
        print(catalogue())
    elif a.cmd == "teach":
        print(teach())
    elif a.cmd == "show":
        print(json.dumps(load(a.name), indent=1))
    elif a.cmd == "pick":
        print(pick(Path(a.script).read_text()))
    elif a.cmd == "create":
        p = create(a.brief, a.name)
        print(p)
        print(p.read_text())
