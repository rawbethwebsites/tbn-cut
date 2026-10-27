"""TBN Cut dashboard: a local page to pick a folder and a style, run, watch, review.

    ~/.ai-video-editor/venv/bin/python -m tbncut.dashboard        # http://127.0.0.1:4321

Standard library only. Binds to 127.0.0.1, serves media only from output/.
"""
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
JOBS_FILE = OUTPUT / "_jobs.json"
PORT = int(os.environ.get("TBNCUT_PORT", "4321"))
PY = sys.executable
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv"}

_lock = threading.Lock()
_jobs: list[dict] = json.loads(JOBS_FILE.read_text()) if JOBS_FILE.exists() else []
_queue: list[str] = []


def _save():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    JOBS_FILE.write_text(json.dumps(_jobs, indent=2))


def templates() -> list[dict]:
    out = []
    for p in sorted((ROOT / "templates").glob("*.json")):
        t = json.loads(p.read_text())
        if "name" not in t:  # brand-*.json and other non-style files live here too
            continue
        out.append({"id": p.stem, "name": t["name"], "about": t.get("about", "")})
    return out


def _job(jid: str) -> dict | None:
    return next((j for j in _jobs if j["id"] == jid), None)


def _worker():
    while True:
        with _lock:
            jid = next((q for q in _queue), None)
        if not jid:
            time.sleep(0.5)
            continue
        job = _job(jid)
        out_dir = OUTPUT / ("scripts" if job.get("kind") == "script" else Path(job["folder"]).name)
        if job.get("kind") == "rerender":  # text fix: only the captions/graphics layer
            cmd = [PY, "-m", "tbncut.motion", "rerender", job["work"]]
        elif job.get("kind") == "script":  # text to a voiced explainer, no footage
            cmd = [PY, "-m", "tbncut.script", job["script_file"], "--voice", job.get("voice") or "default",
                   "--series", job.get("series") or "THE BOOST NATION", "--episode", job.get("episode") or "",
                   "--out", str(OUTPUT / "scripts"), "--brand", job.get("brand", "tbn")]
            if job.get("music", True):
                cmd += ["--music", "beat"]
            if job.get("cta"):
                cmd += ["--cta", job["cta"]]
        else:
            cmd = [PY, "-m", "tbncut.run", job["folder"], "--template", job["template"], "--out", str(out_dir)]
            if job.get("only"):
                cmd += ["--only", job["only"]]
            if job.get("focus"):
                cmd += ["--focus", job["focus"]]
            mode = job.get("mode") or ("mix" if job.get("combine") else "edit")
            if mode == "mix":
                cmd += ["--combine"]
            elif mode == "shorts":
                cmd += ["--shorts", str(job.get("shorts") or 4)]
            elif mode == "explainer":
                cmd += ["--explainer"] + (["--series", job["series"]] if job.get("series") else []) + (["--episode", job["episode"]] if job.get("episode") else [])
            elif mode == "workout":
                cmd += ["--workout"]
            for k, v in (job.get("set") or {}).items():
                cmd += ["--set", f"{k}={json.dumps(v) if not isinstance(v, str) else v}"]
        log = OUTPUT / f"_job-{jid}.log"
        with _lock:
            job.update(status="running", started=time.time(), log=str(log), out_dir=str(out_dir))
            _save()
        with open(log, "w") as fh:
            code = subprocess.call(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT,
                                   env={**os.environ, "OPENCV_LOG_LEVEL": "ERROR"})
        with _lock:
            job.update(status="done" if code == 0 else "failed", finished=time.time())
            _queue.remove(jid)
            _save()


def job_view(job: dict) -> dict:
    """Job plus its log tail and the finished videos with their edit reports."""
    v = dict(job)
    log = Path(job.get("log", ""))
    lines = log.read_text(errors="replace").splitlines() if log.is_file() else []
    v["log_tail"] = [l for l in lines if "WARN" not in l][-8:]
    v["failed_videos"] = [l for l in lines if "FAILED" in l]
    v["skipped_videos"] = [l.split("] ", 1)[-1].replace(": SKIPPED", ":") for l in lines if "SKIPPED" in l]
    outs = []
    od = Path(job.get("out_dir", ""))
    tname = next((t["name"] for t in templates() if t["id"] == job["template"]), job["template"])
    slug = re.sub(r"[^a-z0-9]+", "-", tname.lower()).strip("-")
    if od.is_dir():
        pats = [f"* - {tname}.mp4"] + (["* - explainer.mp4"] if job.get("mode") == "explainer" else []) \
            + ([f"{job.get('name', '')} - script video.mp4"] if job.get("kind") == "script" else [])
        for mp4 in sorted({m for pat in pats for m in od.glob(pat)}):
            if job.get("started") and mp4.stat().st_mtime < job["started"] - 1:
                continue  # an older render of the same video, not this job's
            stem = mp4.name.replace(f" - {tname}.mp4", "").replace(" - explainer.mp4", "")
            stem = re.sub(r" - short \d+ .*$", "", stem)
            vdir = od / stem
            reps = sorted([*vdir.glob(f"{slug}*/edit.json"), *vdir.glob(f"{slug}*/short-*/edit.json"), *vdir.glob("explainer/edit.json"),
                           *(od / f"{stem}").glob("*/edit.json")], key=lambda r: r.stat().st_mtime)  # newest, incl. redo variants
            report = json.loads(reps[-1].read_text()) if reps else {}
            work = str(reps[-1].parent) if reps else ""
            outs.append({"file": str(mp4), "url": "/media?path=" + quote(str(mp4)), "name": mp4.stem,
                         "seconds": report.get("seconds"), "source_seconds": report.get("source_seconds"),
                         "kept": len(report.get("kept", [])), "dropped": len(report.get("dropped", [])),
                         "review": (job.get("reviews") or {}).get(str(mp4)),
                         "work": work, "editable": bool(work) and (Path(work) / "render.json").exists()})
    v["outputs"] = outs
    return v


INBOX = Path.home() / "Movies" / "TBN Cut Inbox"
INBOX_SEEN = OUTPUT / "_inbox_seen.json"


def _inbox_watcher():
    """Clips dropped into ~/Movies/TBN Cut Inbox get a Talking edit (TBN house) automatically.
    A file is picked up once its size stops changing (AirDrop / copies finished)."""
    INBOX.mkdir(parents=True, exist_ok=True)
    seen = set(json.loads(INBOX_SEEN.read_text())) if INBOX_SEEN.exists() else set()
    sizes: dict[str, int] = {}
    while True:
        try:
            for p in sorted(INBOX.iterdir()):
                if p.suffix.lower() not in VIDEO_EXT or p.name.startswith(".") or str(p) in seen:
                    continue
                size = p.stat().st_size
                if sizes.get(str(p)) != size:
                    sizes[str(p)] = size  # still arriving, check again next round
                    continue
                seen.add(str(p))
                INBOX_SEEN.write_text(json.dumps(sorted(seen)))
                job = {"id": uuid.uuid4().hex[:8], "folder": str(INBOX), "template": "tbn-house", "only": p.stem, "set": {},
                       "note": "from the inbox", "status": "queued", "created": time.time(), "reviews": {}, "mode": "edit"}
                with _lock:
                    _jobs.append(job)
                    _queue.append(job["id"])
                    _save()
        except Exception:
            pass
        time.sleep(30)


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
PICKS = OUTPUT / "_picks"


def pick_files() -> list[str]:
    """Native macOS file picker: several videos and pictures at once (cmd-click), no folder needed."""
    r = subprocess.run(["osascript", "-e", 'set fs to choose file with prompt "Pick your videos and pictures" '
                        'of type {"public.movie", "public.image"} with multiple selections allowed',
                        "-e", 'set out to ""', "-e", 'repeat with f in fs', "-e", 'set out to out & POSIX path of f & linefeed',
                        "-e", 'end repeat', "-e", 'return out'], capture_output=True, text=True)
    return [l for l in r.stdout.splitlines() if l.strip()]


def gather(paths: list[Path], name: str = "") -> Path:
    """Picked files -> a folder of links the pipeline can read like any other folder (nothing is copied).
    Files that all come from one folder keep that folder's name, so its saved transcripts and checks are reused.
    iPhone HEIC pictures become JPGs (macOS sips)."""
    parents = {p.parent for p in paths}
    name = name or (next(iter(parents)).name if len(parents) == 1 else time.strftime("Picked %d %b %H.%M"))
    d = PICKS / time.strftime("%Y%m%d-%H%M%S") / name
    d.mkdir(parents=True, exist_ok=True)
    for p in paths:
        ext = p.suffix.lower()
        if ext in VIDEO_EXT or ext in IMAGE_EXT:
            (d / p.name).symlink_to(p.resolve())
        elif ext in (".heic", ".heif"):
            subprocess.run(["sips", "-s", "format", "jpeg", str(p), "--out", str(d / (p.stem + ".jpg"))], capture_output=True)
    return d


def pick_folder() -> str | None:
    """Native macOS folder picker."""
    r = subprocess.run(["osascript", "-e", 'POSIX path of (choose folder with prompt "Pick a folder of raw videos")'],
                       capture_output=True, text=True)
    return r.stdout.strip() or None


def folder_info(path: str) -> dict:
    p = Path(path).expanduser()
    if not p.is_dir():
        return {"ok": False, "error": "That folder doesn't exist."}
    vids = sorted(x.name for x in p.iterdir() if x.suffix.lower() in VIDEO_EXT and not x.name.startswith("."))
    pics = sorted(x.name for x in p.iterdir() if x.suffix.lower() in IMAGE_EXT and not x.name.startswith("."))
    return {"ok": True, "folder": str(p), "videos": vids, "pictures": pics, "picked": PICKS in p.parents}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code: int, body: bytes, ctype="application/json", extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode())

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, (ROOT / "tbncut" / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
        if u.path == "/api/templates":
            return self._json(templates())
        if u.path == "/api/jobs":
            with _lock:
                return self._json([job_view(j) for j in reversed(_jobs[-30:])])
        if u.path == "/api/folder":
            return self._json(folder_info(parse_qs(u.query).get("path", [""])[0]))
        if u.path == "/api/text":
            work = Path(parse_qs(u.query).get("work", [""])[0])
            if OUTPUT.resolve() not in work.resolve().parents or not (work / "props.json").exists():
                return self._json({"ok": False, "error": "No editable text for this video."}, 404)
            pr = json.loads((work / "props.json").read_text())
            lines = [" ".join(w["w"] for w in pr["words"][a:z]) for a, z in pr.get("lines") or []]
            beats = [{"i": i, **{k: b.get(k) for k in ("type", "text", "items", "a", "b", "sub") if k in b}}
                     for i, b in enumerate(pr["beats"]) if b.get("type") != "broll"]
            st = pr.get("style", {})
            return self._json({"ok": True, "lines": lines, "beats": beats,
                               "style": {"accent": st.get("accent", "#EA6113"), "text": st.get("text", "#FFFFFF"), "ink": st.get("ink", "#0B0B0B")}})
        if u.path == "/api/pack":
            d = Path(parse_qs(u.query).get("dir", [""])[0])
            f = d / "Posting pack.md"
            if OUTPUT.resolve() not in d.resolve().parents and d.resolve() != OUTPUT.resolve():
                return self._json({"ok": False, "error": "Not an output folder."}, 403)
            if not f.exists():
                from .pack import make
                make(d)
            return self._json({"ok": True, "text": f.read_text()})
        if u.path == "/media":
            return self._media(parse_qs(u.query).get("path", [""])[0])
        if u.path.startswith("/brand/"):
            f = ROOT / "motion" / "public" / "brand" / Path(u.path).name
            if f.is_file():
                return self._send(200, f.read_bytes(), "image/png", {"Cache-Control": "max-age=3600"})
        self._send(404, b"not found", "text/plain")

    def _media(self, path: str):
        p = Path(path).resolve()
        if OUTPUT.resolve() not in p.parents or not p.is_file():
            return self._send(403, b"forbidden", "text/plain")
        size = p.stat().st_size
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
            start = int(m.group(1) or 0)
            end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        with open(p, "rb") as fh:
            fh.seek(start)
            data = fh.read(end - start + 1)
        extra = {"Accept-Ranges": "bytes"}
        if rng:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self._send(206 if rng else 200, data, mimetypes.guess_type(p.name)[0] or "video/mp4", extra)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/upload":  # one dropped file per request, streamed to disk
            q = parse_qs(u.query)
            name = Path(q.get("name", ["clip.mp4"])[0]).name
            d = Path(q.get("to", [""])[0])
            if not d or PICKS.resolve() not in d.resolve().parents:
                d = PICKS / time.strftime("%Y%m%d-%H%M%S") / time.strftime("Dropped %d %b %H.%M")
            d.mkdir(parents=True, exist_ok=True)
            left = int(self.headers.get("Content-Length") or 0)
            with open(d / name, "wb") as fh:
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    fh.write(chunk)
                    left -= len(chunk)
            if Path(name).suffix.lower() in (".heic", ".heif"):
                subprocess.run(["sips", "-s", "format", "jpeg", str(d / name), "--out", str(d / (Path(name).stem + ".jpg"))], capture_output=True)
                (d / name).unlink()
            return self._json(folder_info(str(d)))
        b = self._body()
        if u.path == "/api/pick-folder":
            path = pick_folder()
            return self._json(folder_info(path) if path else {"ok": False, "error": "No folder picked."})
        if u.path == "/api/pick-files":
            paths = [Path(x) for x in pick_files()]
            if not paths:
                return self._json({"ok": False, "error": "Nothing picked."})
            return self._json(folder_info(str(gather(paths))))
        if u.path == "/api/run":
            info = folder_info(b.get("folder", ""))
            if not info["ok"]:
                return self._json(info, 400)
            if not any(t["id"] == b.get("template") for t in templates()):
                return self._json({"ok": False, "error": "Pick a style."}, 400)
            job = {"id": uuid.uuid4().hex[:8], "folder": info["folder"], "template": b["template"],
                   "only": b.get("only") or "", "focus": (b.get("focus") or "").strip(), "set": b.get("set") or {}, "note": b.get("note") or "",
                   "combine": bool(b.get("combine")), "mode": b.get("mode") or "edit", "shorts": b.get("shorts") or 4,
                   "series": b.get("series") or "", "episode": b.get("episode") or "",
                   "status": "queued", "created": time.time(), "reviews": {}}
            with _lock:
                _jobs.append(job)
                _queue.append(job["id"])
                _save()
            return self._json({"ok": True, "job": job["id"]})
        if u.path == "/api/text":
            work = Path(b.get("work", ""))
            if OUTPUT.resolve() not in work.resolve().parents or not (work / "props.json").exists():
                return self._json({"ok": False, "error": "No editable text for this video."}, 404)
            from .motion import apply_text
            apply_text(work, b.get("lines"), b.get("beats"), b.get("style"))
            src = _job(b.get("job", "")) or {}
            job = {"id": uuid.uuid4().hex[:8], "kind": "rerender", "work": str(work), "folder": src.get("folder", ""),
                   "template": src.get("template", ""), "only": Path(work).parent.name, "set": {}, "note": "text fixed",
                   "status": "queued", "created": time.time(), "reviews": {}}
            with _lock:
                _jobs.append(job)
                _queue.append(job["id"])
                _save()
            return self._json({"ok": True, "job": job["id"]})
        if u.path == "/api/script":
            text = (b.get("script") or "").strip()
            if len(text.split()) < 5:
                return self._json({"ok": False, "error": "Write at least a sentence or two."}, 400)
            name = re.sub(r"[^a-z0-9]+", "-", (b.get("name") or text[:40]).lower()).strip("-")[:40] or "script"
            d = OUTPUT / "scripts"
            d.mkdir(parents=True, exist_ok=True)
            f = d / f"{name}.txt"
            f.write_text(text)
            job = {"id": uuid.uuid4().hex[:8], "kind": "script", "script_file": str(f), "name": name, "folder": str(d),
                   "template": "tbn-house", "voice": b.get("voice") or "default", "series": b.get("series") or "",
                   "episode": b.get("episode") or "", "cta": (b.get("cta") or "").strip(), "music": b.get("music", True),
                   "status": "queued", "created": time.time(), "reviews": {}, "mode": "script", "set": {}}
            with _lock:
                _jobs.append(job)
                _queue.append(job["id"])
                _save()
            return self._json({"ok": True, "job": job["id"]})
        if u.path == "/api/export":
            f = Path(b.get("file", "")).resolve()
            if OUTPUT.resolve() not in f.parents or not f.is_file():
                return self._json({"ok": False, "error": "Unknown video."}, 404)
            from .export import export
            outs = [export(f, fmt) for fmt in ("16x9", "4x5", "1x1")]
            return self._json({"ok": True, "files": [{"name": o.name, "url": "/media?path=" + quote(str(o))} for o in outs]})
        if u.path == "/api/review":
            with _lock:
                job = _job(b.get("job", ""))
                if not job:
                    return self._json({"ok": False, "error": "Unknown job."}, 404)
                job.setdefault("reviews", {})[b["file"]] = {"verdict": b.get("verdict"), "note": b.get("note", ""), "at": time.time()}
                _save()
            return self._json({"ok": True})
        self._send(404, b"not found", "text/plain")


def main():
    for j in _jobs:  # anything left running from a previous start is gone
        if j["status"] in ("queued", "running"):
            j["status"] = "stopped"
    _save()
    threading.Thread(target=_worker, daemon=True).start()
    threading.Thread(target=_inbox_watcher, daemon=True).start()
    print(f"TBN Cut dashboard on http://127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    main()
