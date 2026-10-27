---
name: tbn-cut
description: TBN Cut, a free local video editor. Turns a folder of raw talking-head clips into finished 9:16 shorts (cuts, captions, motion graphics, B-roll, sound) and also makes workout edits, explainers and script-to-video. Use when the user says "TBN Cut", "edit my video with TBN Cut", "make shorts from this folder", "cut this talking-head video", or wants the TBN Cut dashboard opened.
---

# TBN Cut

The app lives in the folder this skill links to (`readlink ~/.claude/skills/tbn-cut` then go two levels up). Call it `$APP`.
Always run Python as `PYTHONPATH= ~/.ai-video-editor/venv/bin/python` from `$APP`, after `source ~/.tbn-cut.env` if that file exists.
If the venv or `~/.tbn-cut.env` is missing, run `$APP/install.sh` first.

## Easiest: the dashboard
`open "$APP/Open TBN Cut.command"` starts it and opens http://127.0.0.1:4321 . The user picks videos, a style and presses one button.

## From the command line
```bash
python -m tbncut.run "<folder of clips>" --template tbn-house           # one short per clip
python -m tbncut.run "<folder>" --template jack-roberts --shorts 4      # find 4 shorts in a long clip
python -m tbncut.run "<folder>" --workout                               # beat-synced workout edit
python -m tbncut.run "<folder>" --explainer --series "Name" --episode 1
python -m tbncut.script script.txt                                      # script -> voiced video
```
Styles are the files in `$APP/templates/` (tbn-house, tbn-editorial, jack-roberts, ali-abdaal, nick-saraev).
Run `python -m tbncut.run --help` for every option. Finished videos land in `$APP/output/<folder>/`;
`edit.json` beside each one lists every kept and dropped line and why.

## Notes
- Everything runs on this Mac: Whisper for words, Ollama for the AI picks, Remotion for graphics. No paid services.
- Ollama must be running (open the Ollama app). The first edit is slow while models load.
- Script-to-video needs a local voice server on :3900 and AI pictures need one on :7860; both are skipped when absent.
- Fix caption text after a render from the dashboard's "Fix text" button (re-renders only the graphics layer).
