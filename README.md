# TBN Cut

Free, local video editor: folder of raw talking-head videos + a template -> finished 9:16 shorts.

## Install on another Mac (Apple silicon, Homebrew)

```bash
git clone https://github.com/rawbethwebsites/tbn-cut.git ~/tbn-cut
cd ~/tbn-cut && ./install.sh
```

It installs ffmpeg, Node, Ollama and the Python packages, downloads the free models (about 7 GB), and adds the
`tbn-cut` skill to Claude Code. Then double-click `Open TBN Cut.command`, or ask Claude "edit my video with TBN Cut".
Pick other Ollama models with `TBN_CUT_VISION_MODEL=... TBN_CUT_EDITOR_MODEL=... ./install.sh`.

```bash
~/.ai-video-editor/venv/bin/python -m tbncut.run "<folder>" --template tbn-house
```

Steps (all cached per video in `output/<folder>/<video>/`):
1. `transcribe.py` faster-whisper (local) -> words with timestamps
2. `cuts.py` rules: drop fillers, pauses, false starts, mumbles
3. `gemma.py` local Gemma 4 (Ollama) scores each line (topic-aware) and each frame (3x3 sheets)
4. `edit.py` pick to the template length, strongest line first, face-centred crop, punch-ins,
   word-by-word captions (drawn with PIL; this ffmpeg has no subtitle filter), loudness -14 LUFS
5. `edit.json` lists every kept and dropped line and why

Templates (styles) live in `templates/`.

## Sound

The graphics' sound effects come from [earshot](https://github.com/Leonxlnx/earshot)'s sound bank (pure DSP,
offline, audited, the same bytes every time) — not from the old ffmpeg-synthesised placeholders.

```bash
python -m tbncut.sfx build            # render motion/public/sfx/*.wav from motion/sfx-kit.json
python -m tbncut.sfx check --listen   # audit them, and ask earshot what they sound like
python -m tbncut.sfx listen "<finished short.mp4>"   # events, sync to the cuts, loudness
```

`motion/sfx-kit.json` names one bank sound per role (tick, pop, impact, whoosh) with its mix level;
`motion/public/sfx/PACK.json` records what was rendered, measured and checked. Change a sound by editing
the kit and running `build` again.

For a client film that needs **real recorded** sound — foley, ambience, a licensed music edit, mastering,
credits — use the `real-sound` agent skill (installed in `~/.claude/skills/real-sound`), which sources from
Freesound / Mixkit with licence checks and mixes to picture. earshot is how any of it gets verified: never
say a soundtrack works without an earshot reading behind it.
