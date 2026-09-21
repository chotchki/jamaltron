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

Four numbers come back on every `--compare`, on stdout and in the sheet's own footer:

* **the mount self-check** - do the eight markers land on stock's `base_animation` plate.
  8/8 means this module is reading `mount_position` correctly. It is a check on the SHEET.
* **the shark's own mount coverage** - how many of those eight the shark's silhouette
  actually covers, per rotation, worst rotation named. That was the sizing question, and it
  is ANSWERED: at the C.13 harness ratio the shipped shark covers **512/512 samples over
  all 64 rotations, no rotation below 8/8**, so `base_animation` ships empty. Note the two
  rings - the self-check above uses STOCK's declared mount positions because it is a check
  on stock's art, while everything drawn on the jamaltron row uses the 0.45 ratio
  entity.lua actually ships, read out of `shared.lua` so the two cannot drift. At the
  unshrunk ring the same render covers 171/512, which is why stock draws a plate.
* **a canvas warning**, when any frame's alpha touches the edge of its render canvas. A
  clipped frame looks like a flat-topped shark, not like an error. MEASURED on the shipped
  knobs: the union of all 64 rotations is **5.59 x 4.48 tiles** of the 6, 2.68 above the
  entity origin and 1.81 below, so the headroom is **0.31 tiles at the top and 0.20 at each
  SIDE** - the side is the tight edge, and it starts cutting frames 16 and 48 at
  `model.scale` **0.87** against a shipped 0.81.
* **a cell-fit line**, the same check for the compare CELL, which had none until an
  adversarial review found the shipped 4.6-tile cell cropping 32 px off each side and 50
  off the bottom of every frame - silently, because a cropped cell reads as a tight
  framing. The cell is `camera.canvas_tiles` wide now, so it cannot cut what the render
  did not, and the line says either what it holds or exactly what to raise.

Drop `--set` to use the shipped values, `--show` to print the resolved config without
rendering. The model is gitignored, so point at your copy with `--blend PATH` or
`$JAMALTRON_BLEND`. Sheets land in `render-out/` (gitignored) and nothing is ever promoted
into `mod/jamaltron/graphics/` for you - that directory carries the licence carve-out.

## Sliders, when you do not know the number yet

`--compare` answers "is this value right". It is the wrong tool for "which value IS right",
where you are moving one number by 0.1 and looking again:

```sh
uv run --directory tools python render/tune.py            # opens a browser at 127.0.0.1:8765
```

Eight sliders - pivot fore/aft, height, girth, scale, pitch, roll, bounce height and bounce
phase - driving the SAME
`ac.load -> art.render_pass -> art.compare_sheet` path the CLI drives, so a value found
there is the same value here: same cache, same sheet, same coverage count, same hash. The
page shows the shark's dimensions and the leg-mount coverage as you drag, and a **copy
TOML** button emits the exact lines to paste into `jamaltron.toml` - the hash it prints is
the hash `art.py --compare` stamps after the paste, so there is no transcription step.
`--set` seeds it, the same syntax as `art.py`, which is how you carry on from yesterday.

MEASURED, and it is why the defaults are what they are: **1.8 s per slider change** (8
body rotations, EEVEE, 16 samples, 384 px, 4 jobs), 0.2 s when the frames are cached, and
**17 s with the shadow toggle on** - Cycles is the whole difference, so shadow is OFF until
you ask for it. Four rotations is NOT faster than eight (the loop is Blender *launch*-bound,
not pixel-bound) and `--jobs 8` is **14x SLOWER** than `--jobs 4` on this machine: eight
simultaneous Blenders thrash the Metal context. Do not go looking for speed there.

It is a local tool and it acts like one: stdlib `http.server`, one file, no dependency, and
it binds 127.0.0.1 only. A render that fails leaves the last good image up and puts the
error on the page - a tuner that dies on a value you were curious about is worse than none.

### Flopping him (C.5)

The same page picks one of the model's **five shipped clips** (SWIM_FAST / SWIM_MEDIUM /
SWIM_SLOW / BITE_01 / BITE_02, or the rest pose), scrubs a frame of it, amplifies it with
**pose gain**, and **PLAYS** the loop. Play is the point: a flop is a MOTION, and frame 7 of
a thrash and frame 7 of a shark swimming sideways are the same picture. The loop renders
once and then plays out of the browser's own memory, so the second cycle is free.

MEASURED, ten frames from cold: **15.1 s** to fill broadside (1.51 s a frame), 18.1 s on the
full wheel, and **0.13 s a frame** to re-tick PLAY afterwards - zero in the browser, which is
where it plays. 256 px is **not** faster than 384 - this loop is Blender *launch*-bound at
both ends, exactly like `--jobs`. The **broadside** view is not a speed knob either (17%,
i.e. nothing); it is there because a beached shark only reads as beached from the side -
nose-on, the roll is invisible and the thrash is all in screen depth, so five of the wheel's
eight views cannot answer the question.

**flop preset** is the C.5 recipe in one click - SWIM_FAST, roll 85, gain 1.0, bounce 0.3,
HEAD reparented, broadside - and it leaves scale, girth, pivot and pitch where you have them,
because half the time those are mid-tuning. The page still OPENS on the committed standing
config (the header's `paste` hash reads `83d6be794998` on arrival, which is the live proof the
flop work has not touched the art that ships), so 85 is a button and not a boot value.

AND THE LOOP WAS MEASURED BY DRIVING IT, which is the whole point - every call about this pose
until now was made off still frames. **Stride 1: 23.40 fps against the 24.00 target** (mean
42.7 ms a frame, min 40.4, max 43.4), seven clean passes of f1..f20, wrapping; stride 2 is
11.80 against 12.00. The 2.5% shortfall is `setInterval`'s own drift - there is no network and
no render inside the loop, just an `img.src` swap to an object URL. The fill is the cost and
it is paid once: 15.2 s for 20 frames, 0.10 s to re-tick the whole loop afterwards. A still is
**1.37-1.42 s** round trip, and 16 renders with one knob moved each came back 16 DIFFERENT
sheets - no slider on that page is decorative.

The **roll** slider runs 15 deg past the 105 where sheet B says he stops reading as beached
and starts reading as dead, belly-up, in WATER, and `artconfig.warnings()` says so from 105
on - `art.py --set 'model.rotation=[140,0,0]'` used to render that in silence. A warning and
not a clamp on purpose: C.5 is judged by eye, and an edge you cannot cross is an edge you have
to take on faith.

**THE FLOP IS KNOBS**, so everything above is available from the CLI too:

```sh
uv run --directory tools python render/art.py --compare \
    --set 'model.action="SWIM_FAST"' --set model.frame=12 --set model.pose_gain=1.0 \
    --set model.reparent_head=true --set 'model.rotation=[85,0,0]' \
    --set bounce.height=0.3 --set bounce.phase=0.25
```

| knob | what it does |
| --- | --- |
| `model.action` | which of the five clips, or `"rest"` for the standing shark. A misspelled id is a fatal `not one of` - the enum IS `render/pose.py`'s table |
| `model.frame` | which frame of that clip, clamped to its range |
| `model.pose_gain` | every bone's rotation scaled away from rest. **1.0 ships**: at roll 80-90 the bounce carries the thrash. The rig survives 2.6x, measured |
| `model.reparent_head` | C.18a rig fix, applied in memory - HEAD ships as a ROOT bone, so the snout is welded to world space until this is on |
| `bounce.height` / `.phase` / `.gravity` | the ballistic lift: how high, where in the cycle he pushes off, and the `g` that fixes the airtime |

All of them are ordinary schema knobs, so a flop frame caches, hashes and stamps exactly like
a standing one. Two consequences worth knowing. The tuner's header names the hash of the
picture it is showing you, pose included (it used to say `pending bake`, because the pose
lived in a temp `.blend` that did not exist until a render ran). And they are **hash-neutral
at their defaults** - `ac.ADDITIVE` - so adding them did not move the `83d6be794998` the
shipped sheets carry; move one off its default and it is in the hash like anything else.

### What the bounce is for

The shadow. The shadow pass is a real Cycles render with the game's own 45-degree sun and a
catcher at z=0, so lifting the model separates the shadow by itself. MEASURED at 0.3 tiles,
one direction, one clip frame, the lift the only difference between two renders: the shadow's
alpha centroid moves **+19.12 px east** (0.2987 tiles against 0.300 predicted, a pure
translation) while the body rises **exactly 14 px up-screen** (0.219 against 0.212
predicted). That separation is what reads as airborne; a lift without it looks like the
sprite growing. It costs 8 px of the body canvas's 84 px of headroom over the whole loop.

The fall is a **parabola, not a sine**, and the airtime is derived from the height and
gravity rather than authored - see `artconfig.bounce_lift` for the argument. A sine hangs at
both extremes and reads as floating; ballistic flight leaves at full speed and comes back
accelerating, which is what being pulled looks like. Ground contact is a hard floor, so the
frames he is not airborne for are frames spent lying on the ground - which is where the
landing, and the joke, lives.

## Shipping a sheet

`art.py` answers "does he look right". `pack.py` turns the frames that answered it into
the two files the mod and CI actually read:

```sh
uv run --directory tools python render/pack.py            # dry run into render-out/pack
uv run --directory tools python render/pack.py --promote --crush   # into mod/jamaltron
```

`--out` names a MOD ROOT and the tree under it is mod-shaped either way -
`<out>/graphics/` gets the sheets and `sprites.json`, `<out>/prototypes/` gets
`sprites_generated.lua`. That is not cosmetic: `.github/workflows/ci.yml` derives
`--strict` from the manifest's PATH, and the path it matches is `mod/jamaltron/graphics`.
A manifest anywhere else is either linted in the tolerant mode or trips the stray-manifest
tripwire, and sheets committed with no manifest beside them fail CI on purpose. So the
default is a gitignored dry run that is lintable IN PLACE, and `--promote` is the
deliberate act that writes into the tree carrying the sprite licence carve-out.

ONE DICT, TWO ARTIFACTS. Every number - width, height, line_length, direction_count,
frame_count, lines_per_file, scale, shift - is computed once and serialized twice, as a
Lua table and as a manifest entry with the same field names plus an `id`. There is no
translation layer for them to drift across, and `test_pack.py` reads both back through
`lint_sprites.py`'s two independent front ends and asserts they normalise identically.
pack.py then runs that gate over its own output before it exits, so a sheet that would
turn CI red turns the packer red first.

MEASURED on the shipped config, crushed, four sheets out of three passes:

| sheet | frame | cells | grid | on disk | VRAM raw | stock's own |
| --- | --- | --- | --- | --- | --- | --- |
| `jamaltron-body` | 360x289 | 64 dir | 2880x2312, 8x8 | 1676 KiB | 25.40 MiB | 1308 KiB / 4.45 MiB |
| `jamaltron-body-mask` | 166x121 | 64 dir | 1328x968, 8x8 | 324 KiB | 4.90 MiB | 1012 KiB / 3.17 MiB |
| `jamaltron-body-shadow` | 405x256 | 64 dir | 3240x2048, 8x8 | 244 KiB | 25.31 MiB | 99 KiB / 4.41 MiB |
| `jamaltron-body-water-reflection` | 332x192 | 1 var | 332x192 | 11 KiB | 0.24 MiB | 5 KiB / 0.77 MiB |
| **total** | | | | **2255 KiB** | **55.86 MiB** | 2425 KiB / 12.8 MiB |

The mask frame is 20 px shorter than the body's box is tall, and that is the fix landing:
the harness stops below the dorsal fin, so the union of its 64 rotations no longer reaches
up the blade.

The rotating frames are the UNION of all 64 rotations' alpha, which for a rotating body is
a disc of radius "furthest point from the turn axis" - so a 4.07-tile shark needs a
5.6-tile box where the stock torso needs 2.06, and the pixel count goes as the SQUARE of
that. That is the whole 4.4x VRAM gap, and it is why we come out SMALLER on disk than stock
while being four times the texture: our sheets are mostly transparent. 56 MiB of raw sprite
for one entity is real; Factorio's own sprite compression takes it to about a quarter of
that, and the lever if it ever matters is `model.scale`, not the packer.

The two non-obvious sheets:

* **the mask** is `apply_runtime_tint`, i.e. the layer the entity colour picker drives, and
  without one the picker does nothing at all (which would also make D.4's careful
  preservation of `color` across the beached swap dead code). It is its own render pass -
  same camera, same canvas, one flat grey shader whose ALPHA is a harness band in the
  model's own local coordinates - and it tints the HARNESS, not the whole fish. The band is
  a saddle between two girth straps, floored AND CEILINGED in the model's local z: without
  the ceiling the tallest thing between the straps is the dorsal fin, and the first shipped
  mask painted it base to tip, which is a colour picker that tints a shark's fin. Stock's
  mask is a shaded greyscale copy of the entire torso at alpha 224, which turns a machine
  into the player's colour and would turn a hammerhead into a lozenge. See the `[mask]`
  block in `jamaltron.toml`; `mask.mode = "silhouette"` is stock's approach kept as a
  one-line escape hatch, and the harness warns you if you pick it.
* **the water reflection** is built by the packer out of the body frames, because there is
  nothing to render. MEASURED off stock: one frame, `variation_count` 1, shift 0, every
  pixel pure red (255,0,0) with the shape entirely in the alpha, a soft blurred ellipse
  1.7x the torso sprite's own footprint. Ours is the mean alpha of all 64 rotations -
  rotationally symmetric by construction - gained, blurred, recentred on the origin and
  forced to red. Stock's 448x448 canvas is Wube not cropping a 5.5 KiB palette PNG, not a
  number to match.

**PNG crushing: worth it, with the tool that is here.** `pngcrush` and `optipng` are not
installed on this machine; `oxipng` is (`brew install oxipng`). `--crush` runs `oxipng -o 4`,
then re-opens every sheet and compares RGBA bytes against the original before keeping the
result - a "lossless" optimizer is a claim, and this pipeline has no in-game validation to
catch a broken one. MEASURED: **-29.2%** on the body sheet, **-40.4%** on the shadow,
-18.5% on the mask, -30.6% on the reflection, **-29.3% over the four**, 8.2 s. Pillow's own `optimize=True` gets -24.4% and -1.0% for comparable time, so the
gap is almost entirely oxipng's colour-type reduction: it turns the black-plus-alpha shadow
sheet into a palette PNG, which is exactly what Wube ships their own shadow sheets as.
Metadata is NOT stripped - the config-hash text chunk is the provenance, and `--strip safe`
would quietly take it. Off by default because the iteration loop should not pay 7 s.

**What a shipped sheet carries, and what it deliberately does not.** Four text chunks:
`jamaltron:config_hash`, the per-pass hashes, the fully resolved config and the derived
numbers. `model.blend` inside that config is a **content digest** (`sha256:` + 16 hex),
never a path, and the hash is taken over the same substitution. That fixes two things with
one change. Hashing the path made the stamp a fact about one laptop - three copies of one
`.blend` hashed to `e7de16fab859` / `335119bf9c46` / `2da921d030cb` for pixel-identical
sheets, and the shipped value reproduced on exactly zero other machines. And the path is
not ours to publish: on the machine that rendered these it was an absolute scratch
directory, heading into a public repo, in the one tree the licence carve-out governs.
Check a sheet against your own copy with `shasum -a 256 HAMMERHEAD.blend | cut -c1-16`;
resolve the stamped config and re-hash it and you get the `config_hash` it claims, which
is the promise the word provenance was making.

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
| `uv run --directory tools python render/art.py --mask` | the runtime-tint pass (the harness) on its own; add `--full` for all 64 |
| `uv run --directory tools python render/art.py --show` | print the resolved config, the derived numbers and the hashes; render nothing |
| `... --set model.scale=0.85 --set 'model.rotation=[0,6,0]'` | override knobs for one run |
| `... --blend /path/to/HAMMERHEAD.blend` | the model, or set `$JAMALTRON_BLEND` |
| `... --force` / `--jobs N` / `-v` | ignore the cache / parallel Blenders (default 4) / echo Blender's own report |
| `uv run --directory tools python render/tune.py` | **the slider UI.** eight knobs, the five shipped clips with a PLAY loop that holds 23.4 of 24 fps, the flop preset, the rig-fix toggle, live coverage count, copy-TOML button; shadow off by default |
| `... --port N` / `--no-open` / `--set model.girth=1.3` | pick the port / do not launch a browser / start from a knob you already found |

The C.7 packer, also from the repo root:

| command | what it does |
| --- | --- |
| `uv run --directory tools python render/pack.py` | frames -> sheets + manifest + Lua, into the gitignored `render-out/pack` |
| `... --promote` | the same, into `mod/jamaltron`, which is the tree CI lints with `--strict` |
| `... --crush` | oxipng afterwards, kept only if the bytes come back identical |
| `... --preview` | pack the preview-samples body cache (8 rotations) instead of the full one |
| `... --line-length N` / `--pad N` / `--max-side N` | columns per row (reduced to a divisor of the frame count) / margin around the union alpha box / sheet ceiling |
| `... --targets body,shadow` / `--frames-dir body=DIR` | pack a subset (ids: `body`, `body_mask`, `shadow`, `reflection`) / point one target somewhere else |
| `... --allow-clipped` / `--any-config` / `--no-verify` | pack frames that are CUT / frames from another config / skip the strict lint of our own output |
| `python3 tools/lint_sprites.py --strict --mod-root jamaltron=mod/jamaltron mod/jamaltron/graphics/sprites.json` | the sprite gate, exactly as CI runs it |

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

**The mask pass rides the body's engine**, its canvas and its resolution, and differs only
in the material - one flat grey shader whose alpha is the harness band. That is deliberate:
its frames have to crop against the same origin pixel the body's do, or the two layers of
`animation` slide apart in game. It is DITHERED (hashed alpha) with backfaces culled, not
BLENDED: alpha-blended EEVEE geometry writes no depth, so the strap on his far flank draws
straight through his back.

Flip `render.engine` to `"CYCLES"` for a final sheet if you want the model's Cycles-only
features; at 132 px you will not see them, which is why `render.use_subsurface` is off.
Re-measure both engines if the geometry or the canvas changes. The shadow-catcher
requirement does not move either way.

MEASURED, the full 64-rotation set cold, 4 jobs, shipped knobs, 12-core M-series: body
**6.1 s**, mask **5.7 s**, shadow **86.6 s**, so **98 s** of Blender and 10 s more for
`pack.py --promote --crush`. Cycles is 90% of it and always will be. Re-rendering the whole
set reproduces the pixels to within **1/255**, and every difference that turns up is a
single LSB: across two runs of the same knobs, 0 then 1 of 64 body frames differed and 54
then 50 of 64 shadow frames. That is what makes a cached frame safe to ship - and it is
why re-packing an untouched pass moves a couple of hundred bytes of PNG.

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
  render_jamal.py      entry point, Blender side. Takes a resolved config, fixes the C.2 and
                       C.18a hazards (NLA, pivot, stale keyframes, shipped cams/lights, HEAD
                       parented to nothing), poses the rig from model.action, lifts it from
                       [bounce], renders N rotations of the body, shadow or mask pass
  pose.py              the five shipped clips: which action, which frames, which bones, and
                       the arithmetic of a loop over one. `model.action`'s enum reads this
                       table, and every posed render re-checks it against the model. stdlib
                       only and imports no sibling -- artconfig imports IT
  tune.py              entry point, uv side. The slider UI (127.0.0.1, stdlib http.server):
                       drives the same ac.load -> render_pass -> compare_sheet path art.py
                       does, plus the flop's clip select, frame scrub and PLAY loop
  sheets.py            compare/contact sheet layout and compositing, plus the mount
                       self-check. Pure arithmetic above the Pillow import, so it tests
                       without rendering
  spritesheet.py       sheet layout math. stdlib ONLY, imported from both sides
  factorio_camera.py   the projection, the rotation order and the sun, with the provenance
                       of every constant. stdlib at import time (Pillow is imported inside
                       --verify), so both sides can use it. Runs three ways: print, --verify,
                       or as a Blender script
  pack.py              entry point, uv side. THE packer (C.7): union frame box, shift,
                       sheet grid, then the SAME dict written out as Lua and as the JSON
                       manifest CI lints. Verifies its own output before it exits
  model_inspect.py     entry point, headless model triage (C.2): dimensions, origin, axes,
                       rig, animation clips, materials, texture sizes, hazards
  blender_check.py     entry point, proves headless Blender works
tests/
  test_art_harness.py       the C.10 harness's pure logic: knob resolution, cache keys,
                            sheet geometry, and the mount self-check against stock art
  test_spritesheet.py       layout math, incl. two cases checked against shipped Factorio assets
  test_factorio_camera.py   projection against 8 muzzle positions the GAME computes, the sun,
                            and the guard that keeps the module importable inside Blender
  test_pose.py              the clip table: its own consistency, the checker that catches
                            the model moving under it, and the loop arithmetic
  test_tune.py              the tuner's two promises: the TOML export round-trips to the hash
                            the page printed, and nothing can slip out of the export
  test_pack.py              the packer: shift against the stock torso's own declaration,
                            the union box, the line_length divisor property over every
                            count, a byte-exact place-it-back round trip, and the two
                            artifacts read through both of lint_sprites.py's front ends
  test_env.py               python version, Pillow present, spritesheet.py still stdlib-only
smoke.sh, build.sh  shell, not part of the uv project (PLAN A.2)
```
