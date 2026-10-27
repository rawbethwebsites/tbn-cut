# Motion template library

A motion template is a small JSON file that says **how** an explainer moves: how titles arrive, how numbers land, how scenes change, what sits behind them and how screenshots appear. The renderer draws the primitives (`motion/src/OsMotion.tsx` + `Explainer.tsx`); templates only combine them, so nobody (staff, Gemma or Claude) has to write code to get a new look.

## Use one
```
python -m tbncut.script my-script.txt --brand tbn --motion cds-os     # a named template
python -m tbncut.script my-script.txt --brand tbn --motion auto       # Gemma picks from the library
```

## The primitives
| key | values |
|---|---|
| `title` | `spring` (words pop up) · `maskrise` (letters rise out of a mask, cdsigrl.org boot) |
| `stat` | `count` (number counts up) · `gauge` (arc draws, ticks pop, needle climbs then springs home) |
| `transition` | `fade` · `shutter` (panels close over a scene and split open on the next, accent seam) |
| `backdrop` | `plain` · `grid` (faint blueprint grid) |
| `window` | `pop` · `genie` (picture/screen recording pours out of the dock, folds back) |
| `speed` | 0.6–1.6 (1 = cdsigrl.org timing) |
| `stagger` | 0.02–0.1 s between letters (maskrise) |

A `window` scene needs a picture or screen recording in the job folder: `{"kind": "window", "title": "...", "label": "window title bar text", "media": "file.png|.mp4"}`.

## Make a new one
- **By hand:** copy a JSON here, change the values, give it a `description` and `when_to_use`.
- **With Gemma:** `python -m tbncut.motionlib create "brief in plain words" --name my-look`. Gemma reads the primitives and the existing library (`python -m tbncut.motionlib teach` prints exactly what it reads), writes a new combo, Python validates every value and saves it with `"made_by": "gemma"`.
- **A new primitive** (a new kind of motion) is code: add it to `OsMotion.tsx`, wire it in `Explainer.tsx`, then add its value and one-line description to `PRIMITIVES` in `tbncut/motionlib.py`. From then on Gemma can use it in templates.

| Template | Made by | Look |
|---|---|---|
| classic | claude | original springy words, counting numbers, fades |
| cds-os | claude | cdsigrl.org: mask-rise letters, gauge, shutters, genie windows, grid |
| boot-calm | claude | cds-os letters and gauge, slower, fades |
| punchy | claude | fast spring words, shutters, genie windows |
| warm-kitchen | gemma | gentle spring words, soft grid, slow fades (food brands) |
