# tools/

Python side of the mod: Blender render driver, sprite packer, line-catalog codegen.
A `uv` project, not a package - nothing here is ever published, so `pyproject.toml`
sets `package = false` and carries no build backend.

Python is pinned to **3.11** (`.python-version`) to match the **3.11.11** CPython
that Blender 4.4.3 bundles. `uv.lock` is committed; `uv sync --frozen` rebuilds the
exact venv.

## The art loop

Change a knob, look at a picture, repeat. One line:

```sh
uv run --directory tools python render/art.py --compare --set model.scale=0.85
```

That renders 8 rotations of the body (EEVEE) and the shadow (Cycles), composites the
shark beside the shipped spidertron at matched rotations with the eight leg mounts drawn
on both, and writes `render-out/sheets/compare_<hash>.png`. MEASURED on a 12-core M-series,
shipped knobs, cold: 1.5 s for the eight body frames and 12.8 s for the eight Cycles shadow
frames, 14 s in total - Cycles IS the loop time, which is why `--preview` (body only, no
shadow) is the 1.5 s knob-twiddling pass and `--compare` is the one you run when you want
the answer. Instant when the frames are cached. Every knob lives in `render/jamaltron.toml`,
every one carries a comment saying what it defaults to and what it does to the picture, and
a misspelled knob is a hard error with a `did you mean` rather than a no-op.

Three numbers come back on every `--compare`, on stdout and in the sheet's own footer:

* **the mount self-check** - do the eight markers land on stock's `base_animation` plate.
  8/8 means this module is reading `mount_position` correctly. It is a check on the SHEET.
* **the shark's own mount coverage** - how many of those eight the shark's silhouette
  actually covers, per rotation, worst rotation named. That is the sizing question. On the
  shipped scale 0.75 it is **15/64 samples, worst 0/8 pointing south**, because stock does
  not cover them either: it leans on a non-rotating plate. Either the shark grows or C.4
  draws a plate, and this is the number that decides which.
* **a canvas warning**, when any frame's alpha touches the edge of its render canvas. A
  clipped frame looks like a flat-topped shark, not like an error. The shipped 6-tile body
  canvas is already cutting frame 32 at `model.scale` 1.1.

Drop `--set` to use the shipped values, `--show` to print the resolved config without
rendering. The model is gitignored, so point at your copy with `--blend PATH` or
`$JAMALTRON_BLEND`. Sheets land in `render-out/` (gitignored) and nothing is ever promoted
into `mod/jamaltron/graphics/` for you - that directory carries the licence carve-out.

## Commands

| command | what it does |
| --- | --- |
| `cd tools && uv sync` | create `.venv` and install Pillow + pytest |
| `cd tools && uv run pytest` | run the unit tests |
| `uv run --directory tools pytest` | same, from the repo root |
| `uv lock --check` | non-zero if `pyproject.toml` and `uv.lock` have drifted |
| `Blender -b --python tools/render/blender_check.py` | prove the Blender entry point still works |
| `uv run --directory tools python render/factorio_camera.py` | print the camera and sun constants |
| `uv run --directory tools python render/factorio_camera.py --verify` | re-derive both constants off the installed game's own sprites |
| `Blender -b MODEL.blend --python tools/render/model_inspect.py -- --out report.json` | dump mesh, rig, clips and materials from a model |

The C.10 art harness, all from the repo root (`--set` takes TOML values, repeatable):

| command | what it does |
| --- | --- |
| `uv run --directory tools python render/art.py --compare` | **the image to look at.** stock / jamaltron / overlay at 8 matched rotations, shadow composited, leg mounts drawn, mount self-check printed |
| `uv run --directory tools python render/art.py --preview` | 8 body rotations + a contact sheet. the fast loop |
| `uv run --directory tools python render/art.py --full` | all 64 rotations + a contact sheet |
| `uv run --directory tools python render/art.py --shadow` | the Cycles shadow-catcher pass on its own |
| `uv run --directory tools python render/art.py --show` | print the resolved config, the derived numbers and the hashes; render nothing |
| `... --set model.scale=0.85 --set 'model.rotation=[0,6,0]'` | override knobs for one run |
| `... --blend /path/to/HAMMERHEAD.blend` | the model, or set `$JAMALTRON_BLEND` |
| `... --force` / `--jobs N` / `-v` | ignore the cache / parallel Blenders (default 4) / echo Blender's own report |

`Blender` is `/Applications/Blender.app/Contents/MacOS/Blender` on this machine.
`blender_check.py` prints the Blender and bundled-Python versions plus the usable
render engines, and exits non-zero if Cycles is missing.

**Trap:** `uv run --project tools pytest` FAILS with `ModuleNotFoundError: No module
named 'render'`. `--project` does not change directory, so pytest takes the repo root
as rootdir, never reads `tools/pyproject.toml` as its config, and silently ignores
`pythonpath = ["."]`. Use `--directory tools` (which does chdir) or plain `cd tools`.

**Second trap:** every entry-point script under `render/` opens with

```python
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
```

because Python puts the SCRIPT's directory on `sys.path[0]`, never the CWD, and
`package = false` means there is no installed `render` to fall back on. Blender does
the same thing to `--python` scripts. Those two lines cannot be factored into a helper
module - importing the helper is the thing that needs the path fixed. Repeat them.

**Third trap, and the corollary of the second:** because `render/` is on `sys.path[0]`,
a file in it named after a **stdlib module shadows that module for every sibling script**.
`render/inspect.py` did exactly this. `dataclasses` imports `inspect`, so
`from dataclasses import dataclass` in `spritesheet.py` imported a module that does
`import bpy` - and `uv run python render/spritesheet.py` exited 1, as did
`blender_check.py`, both of them checked in and both of them "working" right up until you
ran them. It is now `model_inspect.py`, and `test_art_harness.py` fails the suite if any
file under `render/` takes a stdlib name again. Do not solve this one with a sys.path
guard; rename the file.

## The Blender boundary

A script running inside Blender uses **Blender's** interpreter and does **not** see
`tools/.venv`. Blender 4.4.3 bundles numpy 1.26.4, requests and zstandard. It does
**not** bundle Pillow. So the split is enforced by convention:

| side | may import | runs as |
| --- | --- | --- |
| Blender | stdlib, `bpy`, bundled numpy | `Blender -b <file> --python render/x.py -- args` |
| uv | stdlib, Pillow | `uv run python render/x.py` |
| both | stdlib only (`render/spritesheet.py`) | either |

Data crosses as JSON, either a sentinel line on stdout or a path handed in after `--`.
The payoff is `render/spritesheet.py`: the projection and sheet math, the part most
likely to be wrong, gets unit tests with Blender nowhere in the loop.

Injecting the venv into Blender does work (`sys.path.append('tools/.venv/lib/python3.11/site-packages')`,
then `from PIL import Image`) and it is the documented break-glass move if some render
pass genuinely needs Pillow inside a `bpy` context. Use `append`, not `insert(0)`, so
Blender's own numpy keeps winning. We do not build on it: it hard-couples the pipeline
to Blender's exact CPython minor, and it makes the Blender-side code untestable without
Blender.

## Rendering

**Body is EEVEE Next. Shadow is Cycles and has no choice.** That is what the shipped
config does (`render.engine`, `render.shadow_engine`), and here is why:

- **the shadow pass is not a choice.** Only Cycles honours `object.is_shadow_catcher`.
  The attribute exists under EEVEE Next too, so a naive script looks like it works, but
  EEVEE renders the catcher plane fully opaque across the frame and the pass comes back
  as a grey square. Factorio's `shadow_animation` needs the alpha. Move
  `render.shadow_engine` off `"CYCLES"` and the harness prints a WARN.
- **the body pass is a choice, and EEVEE wins it.** Measured on the real model, 8
  rotations at 384 px / 16 samples / 4 jobs: EEVEE **1.47 s wall, 4.6 s CPU**; Cycles CPU
  **2.01 s wall, 13.3 s CPU**. Same picture for a third of the CPU - and Cycles is the
  noisy one at low sample counts, which is exactly where the fast loop lives.
- **the two pictures really are the same.** Mean absolute difference across those 8
  frames: **0.31/255** over the whole RGBA frame, 6.1/255 over the pixels either render
  puts ink on. It is almost entirely the antialiased silhouette edge - 19.3/255 on
  partial-alpha fringe pixels against 2.7/255 on the fully opaque interior.
- **CPU, not GPU, for Cycles.** A sprite-size tile is pure launch overhead for a GPU:
  Metal costs a 39 s one-time kernel compile and then MORE per frame than CPU. `GPU`
  exists in the config for when the canvas grows.

Flip `render.engine` to `"CYCLES"` for a final sheet if you want the model's Cycles-only
features; at 132 px you will not see them, which is why `render.use_subsurface` is off.
Re-measure both engines in C.4 if the geometry or the canvas changes. The shadow-catcher
requirement does not move either way.

`gpu.platform.backend_type_get()` raises `SystemError` in background mode. Do not
probe the `gpu` module headless - rendering is fine, that one call is not.

## Layout

```
pyproject.toml      deps + pytest config
.python-version     3.11, matches Blender's bundled CPython
uv.lock             committed
render/
  jamaltron.toml       EVERY art knob, with what it defaults to and what it does to the
                       picture. The one file you edit while iterating
  art.py               entry point, uv side. THE art harness (C.10): resolves the config,
                       decides which frames are missing, shells out to N Blenders, builds
                       the compare and contact sheets, stamps provenance on everything
  artconfig.py         the knob SCHEMA, resolution, validation, derived numbers and the
                       per-pass cache hashes. stdlib only, so both sides import it
  render_jamal.py      entry point, Blender side. Takes a resolved config, fixes the C.2
                       hazards (NLA, pivot, stale keyframes, shipped cams/lights), renders
                       N rotations of the body or the shadow pass
  sheets.py            compare/contact sheet layout and compositing, plus the mount
                       self-check. Pure arithmetic above the Pillow import, so it tests
                       without rendering
  spritesheet.py       sheet layout math. stdlib ONLY, imported from both sides
  factorio_camera.py   the projection, the rotation order and the sun, with the provenance
                       of every constant. stdlib at import time (Pillow is imported inside
                       --verify), so both sides can use it. Runs three ways: print, --verify,
                       or as a Blender script
  model_inspect.py     entry point, headless model triage (C.2): dimensions, origin, axes,
                       rig, animation clips, materials, texture sizes, hazards
  blender_check.py     entry point, proves headless Blender works
tests/
  test_art_harness.py       the C.10 harness's pure logic: knob resolution, cache keys,
                            sheet geometry, and the mount self-check against stock art
  test_spritesheet.py       layout math, incl. two cases checked against shipped Factorio assets
  test_factorio_camera.py   projection against 8 muzzle positions the GAME computes, the sun,
                            and the guard that keeps the module importable inside Blender
  test_env.py               python version, Pillow present, spritesheet.py still stdlib-only
smoke.sh, build.sh  shell, not part of the uv project (PLAN A.2)
```
