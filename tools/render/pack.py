#!/usr/bin/env python3
"""C.7, the packer: rendered frames -> sprite sheets -> the Lua table AND the JSON manifest.

    uv run --directory tools python render/pack.py                 # into render-out/pack (gitignored)
    uv run --directory tools python render/pack.py --promote       # into mod/jamaltron, where CI looks
    uv run --directory tools python render/pack.py --preview       # pack the 8-frame preview cache
    uv run --directory tools python render/pack.py --crush         # oxipng afterwards, verified lossless

ONE DICT, TWO ARTIFACTS. Every number a prototype needs -- width, height, line_length,
direction_count, frame_count, lines_per_file, scale, shift -- is computed once, into one
Python dict per sprite, serialized twice: a Lua table for the data stage and a JSON entry
for `tools/lint_sprites.py`. The manifest entry is the Lua table plus an `id`, nothing else;
shared field names are what make the gate real. No translation layer to drift across, and
no number in the repo that a human typed off a render.

WHERE THE OUTPUT GOES MATTERS. `--out` names a MOD ROOT, and the tree under it is
mod-shaped either way:

    <out>/graphics/jamaltron-body.png        the sheets
    <out>/graphics/sprites.json              the manifest, BESIDE the sheets
    <out>/prototypes/sprites_generated.lua   the table the data stage requires

.github/workflows/ci.yml derives `--strict` from the manifest's PATH, in one `case`, matching
`mod/jamaltron/graphics`. A manifest anywhere else is either linted tolerant (useless on
generated art: our sheets come off an exact grid, so every warning is a defect) or trips the
job's stray-manifest tripwire. Sheets committed with no manifest beside them fail CI on
purpose. So the default `--out render-out/pack` is a dry run lintable IN PLACE (same
relative shape, `mod_roots` pointing one directory up), and `--promote` is the deliberate
act that writes into the tree carrying the RenderHub carve-out licence.

WHAT THE PACKER DECIDES, measured, not chosen:

  * THE FRAME BOX is the UNION of every frame's alpha bounding box AT alpha >= 1, padded
    by `--pad`. One box for the whole sheet, because Factorio gets ONE width, height and
    shift for all 64 rotations; per-frame would fit frame 0 and clip frame 32. Alpha >= 1
    because Factorio composites with the PNG's alpha, so every non-zero pixel is drawn --
    C.4 measured this box at alpha >= 8 and shipped a shark whose tail fin was sliced flat
    at the frame edge in directions 16 and 48 (the faint ramp below 8 was visible in game).
    art.SPRITE_VISIBLE_ALPHA is that threshold, in ONE place, and every extent question
    here asks it.
  * THE SHIFT falls out of that box. Our canvas is centred on the entity origin by
    construction (the camera looks at the world origin), so the origin sits at pixel index
    (res-1)/2 (factorio_camera.origin_pixel says why not res/2), and the shift is the
    distance from there to the cropped frame's centre, in tiles. Cross-checked against the
    stock torso in tests: 132x138 with the entity at pixel (65.5, 106.5) is shift
    by_pixel(0, -19), which is what Wube declares.
  * LINE_LENGTH IS ALWAYS EMITTED, and it always DIVIDES the frame count. Without it the
    engine's default depends on which prototype field is loading and the linter can only
    check a frame budget. A line_length that does not divide the count leaves blank cells
    in the last row, which `--strict` reports as `unused-frames` (generated art should not
    ship frames nothing draws). Ask for 8 (stock's torso layout) on a count 8 does not
    divide and you get the largest divisor that fits, with a line on stdout saying so.
  * CLIPPED IS FATAL, TWICE, and the second is the gate C.4 did not have. A frame whose
    visible alpha touches the RENDER CANVAS edge is cut before the packer sees it: raise
    camera.canvas_tiles and re-render, no box can fix that. Then, once the sheets are laid
    out, EVERY frame is re-measured inside its own cell and must keep the margin `--pad`
    promised. That check runs on the finished pixels, so it catches the box math, the crop,
    the pad or a threshold alike -- the hand measurement off a shipped PNG, on every pack.
    `--allow-clipped` downgrades both to notes for deliberate experiments and says so
    loudly.
  * STALE FRAMES ARE FATAL. Every frame directory carries art.py's config.json; its pass
    hash must match the config being packed, or you are shipping pixels from knobs you have
    since moved. `--any-config` overrides, for packing somebody else's frames on purpose.

SHADOW SHEETS GET SURGERY BEFORE ANYTHING IS MEASURED: RGB forced to black, alpha below
RENDER_NOISE_FLOOR zeroed. Factorio draws a `draw_as_shadow` sprite as a darkening mask
where only alpha matters (stock's spidertron-body-shadow.png is a palette PNG of pure black
plus alpha), and a Cycles shadow catcher scatters alpha 1..7 sampling noise across the
whole plane -- MEASURED, 9537 noise pixels on a 704px frame, which left in is a faint grey
rectangle over every tile near the shark. Doing it FIRST lets this pass measure its frame
box at the visible threshold too: no sub-floor alpha is left to disagree about, so the
measured pixels are the shipped pixels. The noise floor is a fact about the RENDERER, the
visible threshold a fact about the ENGINE, and the packer never measures with one and
writes the other.

THE TINT MASK GETS THE SAME FLOOR, alpha only (its grey RGB is what the tint multiplies, so
it stays). MEASURED on the beached flop (897cda204427): 36 stray pixels at alpha 1..5 in 18
of 72 cells, far off the harness band, stretched the mask's union box from 56 to 251 px
wide -- 7.8 MiB of VRAM holding nothing. The cost is the band's own 1 px antialiasing ramp
(alpha 1..7, under 3% tint), which the floor also takes. Same order as the shadow: zeroed
first, then measured at the visible threshold.

BASE_ANIMATION: NOT WORTH RENDERING, settled by 512/512. Stock needs a non-rotating under
plate because its legs bolt to the corners of a machine its rotating torso does not reach;
the mounts land on the plate. Jamal is in a HARNESS -- C.13 moved the mounts inboard to
0.45 of stock, +-0.352 tiles transverse. MEASURED on the shipped 64-frame body render at that
ratio: all eight mounts land on opaque shark at all 64 rotations, 512 of 512 samples, no
rotation below 8/8. At the unshrunk stock ring the same render covers 171 of 512 (what a
plate would have to cover, and why stock ships one). So the packer emits no base_animation
and names it in `clear` instead: entity.lua deepcopies the stock spidertron, and an
uncleared slot keeps drawing WUBE'S PLATE under our shark. What would reopen this is the
in-game walk cycle showing a seam where the leg tops meet him -- F.2's eyeball, not a number.

THE RUNTIME-TINT MASK is a real render pass (`mask`), not a packer trick: same camera and
canvas, one flat grey shader whose alpha is a harness band in the model's local
coordinates (the [mask] block in jamaltron.toml says why the harness and not the whole
fish). Here it is another target cropped to its own box, smaller than the body's, as
stock's 130x100 mask is against its 132x138 body.

THE WATER REFLECTION is built HERE from the body frames; there is nothing to render. Stock's
spidertron-body-water-reflection.png is one 448x448 frame, variation_count 1, shift 0, every
pixel pure red (255,0,0) with the shape entirely in the alpha: a soft blurred ellipse 194x133
px, 1.7x the torso sprite's footprint, centred on the entity origin. The 448 canvas is Wube
not cropping a 5.6 KiB palette PNG, not a number to match. Ours is the same object derived
honestly: the MEAN alpha of all 64 body rotations (rotationally symmetric by construction),
gained, blurred, recentred on the origin and forced to red. A REDUCE target: 64 frames in,
one variation out.

PNG CRUSHING: WORTH IT, WITH OXIPNG. pngcrush and optipng are not installed here; oxipng is
(`brew install oxipng`) and is the fastest of the three anyway. `--crush` runs it, then
re-opens every sheet and compares RGBA bytes against the original before keeping the result
-- "lossless" is the optimizer's claim, and this sprite pipeline has no in-game validation to
catch a broken one. Metadata is NOT stripped: the config-hash text chunk is the provenance,
and `--strip safe` would quietly take it. Measured savings print per sheet. Off by default:
seconds per sheet the iteration loop should not pay.

Runs on the uv side (Pillow). Imports art.py for the alpha thresholds and the cache-directory
naming on purpose: a second pass-directory computation would eventually disagree with the
renderer's and pack the wrong frames silently, and a second copy of "what counts as part of
the sprite" is the bug that clipped C.4's tail fin.
"""

# sys.path, verbatim per tools/README.md -- Python and Blender both put THIS file's own
# directory on sys.path[0], never tools/, and `package = false` means no installed `render`
# to fall back on. Cannot be a helper: importing the helper is what needs the path fixed.
import pathlib, sys  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass, field, replace  # noqa: E402

from render import artconfig as ac  # noqa: E402
from render import factorio_camera as fc  # noqa: E402
from render import pose  # noqa: E402
from render import sheets  # noqa: E402
from render.art import (REPO, RENDER_NOISE_FLOOR, SPRITE_VISIBLE_ALPHA,  # noqa: E402
                        pass_dir, sequence_samples)
from render.spritesheet import MAX_SHEET_SIDE, SheetLayout, plan_sheet  # noqa: E402

#: Dry-run root. Gitignored, and mod-shaped so the manifest lints where it lands.
DEFAULT_OUT = "render-out/pack"
#: `--promote`. The tree CI lints with --strict, and the one carrying the sprite licence.
PROMOTE_OUT = "mod/jamaltron"

GRAPHICS_DIR = "graphics"
PROTOTYPES_DIR = "prototypes"
MANIFEST_NAME = "sprites.json"
LUA_NAME = "sprites_generated.lua"
MANIFEST_VERSION = 1

#: Fallback when <out>/info.json does not exist (the dry-run tree has none).
MOD_NAME = "jamaltron"

#: Stock's torso layout: 64 frames of 132x138 in an 8x8 grid. Ours matches, so a contact
#: sheet and a shipped sheet can be eyeballed side by side.
DEFAULT_LINE_LENGTH = 8

#: Pixels of transparent margin around the union alpha box. NOT there to keep the sprite
#: whole: the box is measured at SPRITE_VISIBLE_ALPHA, so it already holds every pixel the
#: engine draws, and a pad the sprite depended on would mean the box was wrong. MEASURED on
#: the art this mod stands next to: Wube crops FLUSH. The stock torso's 132x138 cells hold
#: alpha>0 pixels at margin 0 on all four edges, its mask and shadow the same, so the
#: engine's atlas evidently handles a sprite touching its cell edge and a margin buys
#: nothing at draw time.
#:
#: What it buys is a FALSIFIABLE GATE. cell_margins() re-measures every finished cell and
#: tight_frames() requires the promised margin; at pad 1 that check fails while the sprite
#: is still INTACT (one pixel from the edge, nothing lost yet) instead of after the pixels
#: are gone -- a gate with no slack is a post-mortem. The bill on the shipped body sheet is
#: 2 px per axis: 2880x2296 without, 2896x2312 with, +1.3% of the pixels. Stop there:
#: pixels go as the SQUARE of the box, so more margin pays real VRAM for detection slack
#: one pixel already has.
DEFAULT_PAD = 1

#: How a graphics_set slot wraps its sprite(s). Read off spidertron-animations.lua's
#: spidertron_torso_graphics_set: `animation` and `base_animation` are layer STACKS,
#: `shadow_animation` is a BARE sprite, and `water_reflection` is a
#: WaterReflectionDefinition whose `pictures` stock fills with ONE sprite table, not a list:
#: `pictures` is SpriteVariations, and only the single-sheet form may carry
#: `variation_count` (a list declares an array of Sprites, and a Sprite has no
#: variation_count for the engine to read).
SLOT_WRAP = {
    "animation": "layers",
    "base_animation": "layers",
    "shadow_animation": None,
    "shadow_base_animation": None,
    "water_reflection": "pictures",
}

#: Wraps that name ONE sprite under a key rather than a list of them.
SINGLE_WRAPS = ("pictures",)

#: Every graphics_set slot the stock spidertron fills with STOCK ART. entity.lua deepcopies
#: that prototype, so any slot we do not overwrite keeps drawing a spidertron; slots no
#: target covers are emitted as `clear` (see the module docstring).
STOCK_ART_SLOTS = ("base_animation", "shadow_base_animation", "animation",
                   "shadow_animation", "water_reflection")

#: Which derived px-per-tile a pass renders at. The mask shares the body canvas exactly, so
#: its frames crop against the same origin pixel.
PASS_PPT = {"body": "body_px_per_tile", "shadow": "shadow_px_per_tile",
            "mask": "body_px_per_tile"}

#: The art.py flags that render each pass, as (preview, full), so "no frames" names what to
#: type, not a flag that renders the wrong pass.
PASS_FLAG = {"body": ("--preview", "--full"),
             "shadow": ("--shadow", "--shadow --full"),
             "mask": ("--mask", "--mask --full")}


@dataclass(frozen=True)
class Target:
    """One sheet to build: where its frames come from, where its numbers end up.

    This table is the contract C.4 fills. Adding a pass means adding a row, not editing
    the packer, so `pass_name` may name a render pass that does not exist yet: the row
    documents the slot and the run prints what is missing.
    """

    id: str                       # manifest id, Lua key, and the name in every finding
    slot: str                     # graphics_set key it lands in
    order: int                    # position within the slot's layer stack
    pass_name: str                # render pass supplying the frames
    stem: str                     # sheet filename stem under graphics/
    # How Factorio counts the cells: "rotations" -> direction_count, "animation" ->
    # frame_count, "variations" -> variation_count. The engine multiplies all three.
    kind: str = "rotations"
    draw_as_shadow: bool = False
    apply_runtime_tint: bool = False
    optional: bool = False        # a missing frame directory is a note, not an error
    # Name in REDUCERS. A reduce target consumes a whole pass and emits FEWER frames than it
    # read (the water reflection: 64 rotations in, one blob out).
    reduce: str | None = None
    # Zero alpha below the render noise floor BEFORE measuring, RGB kept. The tint mask's
    # surgery (see the module docstring); a draw_as_shadow target gets it inside blacken.
    denoise: bool = False


#: THE SHIPPED TARGETS. Four sheets, three passes: the reflection rides the body's frames.
#:
#: `body_mask` is layer 1 of `animation`, over the body, exactly where stock puts
#: spidertron-body-mask.png. Without it the entity colour picker does nothing, and D.4's
#: preservation of `color` across the beached swap is dead code. Not optional: a promote
#: that quietly shipped no tint layer is the failure this row prevents.
TARGETS = (
    Target(id="body", slot="animation", order=0, pass_name="body",
           stem="jamaltron-body"),
    Target(id="body_mask", slot="animation", order=1, pass_name="mask",
           stem="jamaltron-body-mask", apply_runtime_tint=True, denoise=True),
    Target(id="shadow", slot="shadow_animation", order=0, pass_name="shadow",
           stem="jamaltron-body-shadow", draw_as_shadow=True),
    Target(id="reflection", slot="water_reflection", order=0, pass_name="body",
           stem="jamaltron-body-water-reflection", kind="variations",
           reduce="reflection"),
)


#: A SEQUENCE sheet (C.21): the beached flop, one direction, N animation frames gathered from
#: N per-frame cache directories. Body, tint mask and shadow (the standing layers) as
#: `animation` frames. `stem` is completed with the sequence's name (jamaltron-beached-body)
#: so a sequence can never overwrite the standing sheets.
#:
#: A sequence ships a SUBSET when its [sequence] `passes` says so (sequence.PASSES): the
#: beached flop ships body + shadow and no mask, his harness having broken off with his legs
#: (chotchki 2026-09-26). drop_unshipped() removes a sheet an earlier pack left behind.
#:
#: NO REFLECTION. Stock's reflection is a rotationally symmetric blob under a turning torso;
#: a beached shark lies one way and refuses water, and a mean-of-rotations means nothing
#: over animation frames. The slot goes in `clear`, which says so explicitly.
SEQUENCE_TARGETS = (
    Target(id="body", slot="animation", order=0, pass_name="body", stem="body",
           kind="animation"),
    Target(id="body_mask", slot="animation", order=1, pass_name="mask", stem="body-mask",
           kind="animation", apply_runtime_tint=True, denoise=True),
    Target(id="shadow", slot="shadow_animation", order=0, pass_name="shadow",
           stem="body-shadow", kind="animation", draw_as_shadow=True),
)


def sequence_targets(name: str, passes=None) -> tuple:
    """SEQUENCE_TARGETS with their stems completed for sequence `name`, only those whose pass
    is in `passes` when given (a Sequence's .passes)."""
    return tuple(replace(t, stem=f"{MOD_NAME}-{name}-{t.stem}") for t in SEQUENCE_TARGETS
                 if passes is None or t.pass_name in passes)


def drop_unshipped(seq, out_root: pathlib.Path) -> list:
    """Delete the sheets of every sequence target `seq` does NOT ship from out_root's
    graphics/, and return what went. Otherwise a dropped pass leaves its old sheet behind,
    unreferenced by manifest and Lua (so no lint sees it), shipping in the zip as dead
    weight. Exact stems only (`<stem>.png`, `<stem>-<n>.png`): the body's stem is a PREFIX
    of the mask's, so a glob would take the wrong sheet."""
    shipped = {t.id for t in sequence_targets(seq.name, seq.passes)}
    graphics = out_root / GRAPHICS_DIR
    gone = []
    for target in sequence_targets(seq.name):
        if target.id in shipped or not graphics.is_dir():
            continue
        for path in sorted(graphics.iterdir()):
            rest = path.name[len(target.stem):] if path.name.startswith(target.stem) else None
            if rest == ".png" or (rest and rest.startswith("-") and rest.endswith(".png")
                                  and rest[1:-4].isdigit()):
                path.unlink()
                gone.append(path)
    return gone


def sequence_outputs(name: str) -> tuple:
    """(manifest file name, Lua module name) for sequence `name`. Beside the standing pair,
    never over it: CI recognises both kinds by CONTENT, so a second manifest in the strict
    tree is linted exactly like the first."""
    return f"{name}-{MANIFEST_NAME}", f"{name}_{LUA_NAME}"


class PackError(RuntimeError):
    """A fatal packing problem, phrased for the person who has to fix it."""


# ------------------------------------------------------------------ frame discovery


def frames_dir(cfg, target: Target, *, preview: bool = False, explicit=None):
    """Where `target`'s frames live, or None when its render pass does not exist yet.

    Derived from art.py's pass_dir(), never recomputed: a second copy of the cache-naming
    rule is a second chance to read a directory the renderer never wrote.
    """
    if explicit is not None:
        return pathlib.Path(explicit)
    if target.pass_name not in ac.PASSES:
        return None
    if target.pass_name == "shadow":
        samples = cfg["render.shadow_samples"]
    else:
        samples = cfg["render.preview_samples"] if preview else cfg["render.samples"]
    return pass_dir(cfg, target.pass_name, samples)


def discover_frames(directory: pathlib.Path) -> list[int]:
    """Frame indices present in a render directory, ascending."""
    out = []
    for path in sorted(directory.glob("frame_*.png")):
        stem = path.stem.split("_", 1)[1]
        if stem.isdigit():
            out.append(int(stem))
    return out


def check_frame_set(frames: list[int], kind: str, total: int, origin: str) -> None:
    """Frames must be a full ring (or a full clip) -- or the sheet lies about its own frames.

    art.py's --preview renders indices 0, 8, 16 ... 56 of 64, which packs fine at
    direction_count 8 (frame i covers orientation i/8). A directory holding 48 of 64 frames
    because a render died halfway is NOT fine and looks identical on disk, so the set is
    checked, not counted. An `animation` target has no ring: its frames are a clip and must
    run 0..N-1 with no gap.
    """
    if not frames:
        raise PackError(f"{origin}: no frame_NNN.png files")
    if kind == "animation":
        want = list(range(len(frames)))
    else:
        try:
            want = ac.frame_indices({"rotations.count": total}, len(frames))
        except ac.ConfigError as exc:
            raise PackError(f"{origin}: {len(frames)} frames against rotations.count "
                            f"{total}: {exc}") from None
    if frames != want:
        raise PackError(
            f"{origin}: {len(frames)} frames are not a complete set "
            f"({'clip' if kind == 'animation' else f'evenly spaced ring of {total}'}).\n"
            f"  have {frames[:10]}{'...' if len(frames) > 10 else ''}\n"
            f"  want {want[:10]}{'...' if len(want) > 10 else ''}\n"
            f"  a part-rendered directory packs into a sheet whose rotations are wrong "
            f"and which looks fine on disk. Re-run art.py, or point --frames-dir at a "
            f"complete pass.")


def check_pass_hash(cfg, target: Target, directory: pathlib.Path, *, any_config: bool):
    """Refuse frames rendered with knobs that have since moved. Returns the sidecar blob.

    art.py writes config.json into every pass directory, holding the resolved knobs AND the
    per-pass hash. Comparing it here turns "these pixels came from the config I am about to
    stamp on them" from a hope into a check.
    """
    sidecar = directory / "config.json"
    if not sidecar.is_file():
        print(f"  NOTE {target.id}: {sidecar} missing, cannot verify the frames' "
              f"provenance; falling back to the current config's derived numbers")
        return None
    blob = json.loads(sidecar.read_text())
    if target.pass_name in ac.PASSES:
        want = ac.pass_hash(cfg, target.pass_name)
        got = blob.get("pass_hashes", {}).get(target.pass_name)
        if got != want and not any_config:
            # The pass hash covers `model.blend` as a CONTENT digest, so a mismatch can also
            # mean "the model is not on this machine", not "a knob moved". Say which: the
            # fixes differ.
            absent = ""
            if ac.hashable(cfg)["model.blend"] == ac.BLEND_ABSENT:
                absent = (f"\n  The model is not where this config points "
                          f"({ac.blend_path(cfg)}), so its digest -- part of every pass "
                          f"hash -- could not be taken. Point at it with ${ac.BLEND_ENV} "
                          f"to verify these frames properly, or pass --any-config to "
                          f"ship them unverified.")
            raise PackError(
                f"{target.id}: the frames in {directory} were rendered at {target.pass_name} "
                f"pass hash {got}, the config being packed is {want}. Those are different "
                f"pixels. Re-render, or pass --any-config if you mean it.{absent}")
    return blob


# ---------------------------------------------------------------------- the geometry


def union_box(images, floor: int = SPRITE_VISIBLE_ALPHA):
    """Union of every frame's alpha bounding box. One box for the whole sheet.

    THE DEFAULT IS THE VISIBLE THRESHOLD, and every caller here takes it: a box measured
    higher cuts pixels the engine draws. Pass a different floor only for a pass whose
    sub-floor alpha is already ZEROED in the pixels (the shadow and mask surgery) or to
    demonstrate the difference in a test -- never to make a subject fit.

    Returns (box, per_frame) so a caller can name WHICH frame is widest (an oversized box is
    always one rotation, and naming it saves opening 64 files). `per_frame` is measured at
    the SAME threshold as the box and the refusals below consume it, so no gate reads a
    different mask from the box it guards.
    """
    per_frame, box = [], None
    for index, img in images:
        mask = img.getchannel("A").point(lambda v: 255 if v >= floor else 0)
        bounds = mask.getbbox()
        per_frame.append((index, bounds))
        if bounds is None:
            continue
        box = bounds if box is None else (min(box[0], bounds[0]), min(box[1], bounds[1]),
                                          max(box[2], bounds[2]), max(box[3], bounds[3]))
    return box, per_frame


def clipped_frames(per_frame, canvas):
    """Frames whose alpha touches the RENDER canvas edge. See the module docstring: fatal.

    Canvas, not frame box: damage no box can undo, because the pixels were never rendered.
    Whether the BOX held everything is asked afterwards, on the finished cells, by
    cell_margins() and tight_frames().
    """
    width, height = canvas
    return [i for i, b in per_frame
            if b is not None and (b[0] <= 0 or b[1] <= 0 or b[2] >= width or b[3] >= height)]


def pad_box(box, pad: int, canvas):
    """Grow the union box by `pad` px, clamped to the canvas."""
    width, height = canvas
    return (max(0, box[0] - pad), max(0, box[1] - pad),
            min(width, box[2] + pad), min(height, box[3] + pad))


#: Edge order for every margin tuple and every message that prints one.
EDGES = ("L", "T", "R", "B")


def cell_margins(sheet_images, layout, *, floor: int = SPRITE_VISIBLE_ALPHA):
    """Per frame, the transparent margin inside its own cell of the finished sheet(s).

    Measured on the LAID-OUT pixels (the buffers about to be saved), not on the frames or
    the box arithmetic that produced them: box math, `--pad`, the crop, the cell placement
    and every threshold picked along the way all land in these pixels, so no upstream
    mistake can fool it. The measurement you would make by hand on the shipped PNG when
    something looks sliced, done on every pack.

    Returns (worst, per_frame): `worst` is edge -> (px, frame index) over every frame, and
    `per_frame` is [(index, (left, top, right, bottom) or None), ...] with None for an
    empty cell (a reducer may legitimately leave one, and an empty cell clips nothing).
    """
    worst: dict = {}
    per_frame = []
    for file_index, sheet in enumerate(sheet_images):
        alpha = sheet.getchannel("A")
        first = file_index * layout.frames_per_file
        for index in range(first, min(first + layout.frames_per_file, layout.frame_count)):
            slot = index - first
            cell = alpha.crop(sheets.frame_box(slot, layout.frame_width,
                                               layout.frame_height, layout.line_length))
            box = cell.point(lambda v: 255 if v >= floor else 0).getbbox()
            if box is None:
                per_frame.append((index, None))
                continue
            margins = (box[0], box[1], layout.frame_width - box[2],
                       layout.frame_height - box[3])
            per_frame.append((index, margins))
            for edge, value in zip(EDGES, margins):
                if edge not in worst or value < worst[edge][0]:
                    worst[edge] = (value, index)
    return worst, per_frame


def margin_line(worst: dict, layout, floor: int) -> str:
    """The margin measurement as one line, for stdout and for the sheet's notes."""
    if not worst:
        return "every cell is empty at alpha >= %d; nothing to measure" % floor
    return ("tightest margin inside the %dx%d cell at alpha >= %d: %s (over %d frame(s))"
            % (layout.frame_width, layout.frame_height, floor,
               "  ".join("%s%d px (frame %d)" % (edge, worst[edge][0], worst[edge][1])
                         for edge in EDGES if edge in worst),
               layout.frame_count))


def tight_frames(per_frame, want: int):
    """Frames whose visible pixels sit closer to their cell edge than `want`.

    At `want` 0 this is vacuous by construction (the cells were cropped out of the box, so
    nothing can lie outside one), which is why DEFAULT_PAD is 1: the pad is the slack that
    lets this check fail BEFORE a pixel is lost.
    """
    return [(index, margins) for index, margins in per_frame
            if margins is not None and min(margins) < want]


def sheet_shift(box, canvas, px_per_tile: float):
    """Frame size and Factorio `shift` for a crop out of an origin-centred canvas.

    The canvas is centred on the entity origin, so the origin is at pixel index (res-1)/2.
    A sprite's CENTRE is drawn `shift` tiles from the entity, so the shift is
    centre-minus-origin inside the cropped frame, divided by the render's px-per-tile.
    `util.by_pixel(x, y)` is this number times 32.

    Returns (width, height, (shift_x_tiles, shift_y_tiles)).
    """
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    if width < 1 or height < 1:
        raise PackError(f"degenerate frame box {box}")
    origin_x = fc.origin_pixel(canvas[0]) - x0
    origin_y = fc.origin_pixel(canvas[1]) - y0
    return width, height, ((fc.origin_pixel(width) - origin_x) / px_per_tile,
                           (fc.origin_pixel(height) - origin_y) / px_per_tile)


def choose_line_length(frame_count: int, requested: int, columns_that_fit: int):
    """Largest divisor of `frame_count` that is <= the request and fits the sheet.

    A line_length that does not divide the count leaves blank cells in the last row, which
    `--strict` (CI's mode for our manifests) reports as unused-frames, correctly: generated
    art should not ship frames nothing draws. Returns (line_length, note), note "" when
    the request survived untouched.
    """
    if frame_count < 1:
        raise PackError(f"frame_count must be >= 1, got {frame_count}")
    cap = min(requested, columns_that_fit, frame_count)
    if cap < 1:
        raise PackError(
            f"no legal line_length: one frame row already exceeds the {MAX_SHEET_SIDE}px "
            f"sheet limit (requested {requested}, {columns_that_fit} column(s) fit)")
    for columns in range(cap, 0, -1):
        if frame_count % columns == 0:
            note = ""
            if columns != requested:
                note = (f"line_length {requested} does not divide {frame_count} frames "
                        f"(or does not fit); using {columns}, the largest divisor that "
                        f"leaves no blank cells for --strict to call unused-frames")
            return columns, note
    raise PackError("unreachable: 1 divides everything")  # pragma: no cover


# ------------------------------------------------------------------- the sprite dict

#: Field order for the one dict. Factorio ignores order; a diff does not, and the two
#: artifacts are read side by side when a number looks wrong.
FIELD_ORDER = ("filename", "filenames", "width", "height", "line_length",
               "direction_count", "frame_count", "frame_sequence", "animation_speed",
               "variation_count",
               "lines_per_file", "scale", "shift", "draw_as_shadow", "apply_runtime_tint")

#: kind -> the ONE count field Factorio should read. Only that one is emitted:
#: `direction_count = 1` on a SpriteVariations is a field that struct does not have, and
#: stock never writes it.
COUNT_FIELD = {"rotations": "direction_count", "animation": "frame_count",
               "variations": "variation_count"}


def sprite_fields(target: Target, filenames, layout, shift, scale: float,
                  frame_sequence=None, animation_speed=None) -> dict:
    """THE dict. The Lua table and the manifest entry are both this, verbatim.

    Built off SheetLayout.prototype_fields(), not re-derived, with one remap: the layout
    counts FRAMES and only the target knows whether they are directions (a rotating body)
    or animation frames (C.5's flop loop). Factorio spells those as different keys and
    multiplies them.
    """
    proto = layout.prototype_fields()
    count = proto.pop("frame_count")
    fields: dict = {}
    if len(filenames) == 1:
        fields["filename"] = filenames[0]
    else:
        fields["filenames"] = list(filenames)
    fields["width"] = proto["width"]
    fields["height"] = proto["height"]
    fields["line_length"] = proto["line_length"]        # ALWAYS. See the module docstring.
    if target.kind not in COUNT_FIELD:
        raise PackError(f"{target.id}: unknown kind {target.kind!r}, expected one of "
                        f"{', '.join(sorted(COUNT_FIELD))}")
    fields[COUNT_FIELD[target.kind]] = count
    # A rotated sheet still says frame_count = 1 explicitly (the pair a reader checks); the
    # other two kinds leave alone the fields their struct does not own.
    if target.kind == "rotations":
        fields["frame_count"] = 1
    if frame_sequence is not None:
        # C.21's order: 1-based cells, repeats and holds included. Only an animation plays in
        # order; a rotation or variation is picked, never played.
        if target.kind != "animation":
            raise PackError(f"{target.id}: frame_sequence on a {target.kind} sheet")
        fields["frame_sequence"] = list(frame_sequence)
    if animation_speed is not None:
        # IN THE SHEET, not a comment for the consumer to retype: without it the engine plays
        # one cell a tick, and the 24 fps flop ran 2.5x fast (MEASURED, 117-tick cycle).
        if target.kind != "animation":
            raise PackError(f"{target.id}: animation_speed on a {target.kind} sheet")
        fields["animation_speed"] = animation_speed
    if "lines_per_file" in proto:
        fields["lines_per_file"] = proto["lines_per_file"]
    fields["scale"] = scale
    fields["shift"] = [shift[0], shift[1]]
    if target.draw_as_shadow:
        fields["draw_as_shadow"] = True
    if target.apply_runtime_tint:
        fields["apply_runtime_tint"] = True
    return {k: fields[k] for k in FIELD_ORDER if k in fields}


# ------------------------------------------------------------------------- reducers


def reflection_blob(images, cfg, px_per_tile: float, floor: int):
    """64 body rotations -> one soft red blob. Stock's water reflection, derived.

    THE MEAN, not the union. A union is the disc swept by the furthest point from the turn
    axis -- a 5.6-tile circle for a 4.07-tile shark, a reflection of something he never is.
    The mean is dense where he sits at every heading and faint at the nose and tail he only
    sometimes reaches, which after the blur is the soft ellipse Wube ships (theirs is
    194x133 px against a 114x88 px torso sprite, 1.7x its footprint).

    The canvas GROWS by the blur's reach first. Blurring in place pushes alpha into the
    canvas edge, and the clipped-frames check then rightly refuses a sheet that is not cut;
    loosening the check would blind it to the real thing. With the box measured at the
    visible threshold, a Gaussian's skirt runs out to alpha 1 and ALL of it is inside the
    box: on the shipped render the skirt takes the blob from 330x190 to 378x293 px, 193 KiB
    on one frame -- the price of not slicing a soft edge into a hard rectangle.
    """
    from PIL import Image, ImageFilter

    width, height = images[0][1].size
    total = [0] * (width * height)
    for _, img in images:
        for index, value in enumerate(img.getchannel("A").tobytes()):
            total[index] += value
    n, gain = len(images), cfg["reflection.gain"]
    mean = bytes(min(255, int(v * gain / n)) for v in total)
    alpha = Image.frombytes("L", (width, height), mean)

    radius = cfg["reflection.blur_tiles"] * px_per_tile
    margin = int(round(radius * 3)) + 1
    grown = Image.new("L", (width + 2 * margin, height + 2 * margin), 0)
    grown.paste(alpha, (margin, margin))
    grown = grown.filter(ImageFilter.GaussianBlur(radius))

    note = ("reflection: mean alpha of %d rotations x%.2f gain, Gaussian blur %.1f px "
            "(%.2f tiles), canvas grown %d px for it" % (n, gain, radius,
                                                         cfg["reflection.blur_tiles"], margin))
    if cfg["reflection.recentre"]:
        grown, moved = recentre_on_origin(grown, floor)
        note += ", recentred %+d,%+d px onto the entity origin" % moved

    out = Image.new("RGBA", grown.size, (255, 0, 0, 0))
    out.putalpha(grown)
    return [(0, out)], note


def recentre_on_origin(alpha, floor: int):
    """Slide a blob so its alpha centroid lands on the canvas's own origin pixel.

    `floor` is the visible threshold: every non-zero pixel is mass. The blob is the MEAN of
    64 clean body frames, so there is no noise to exclude, and excluding the faint skirt
    would put the centroid somewhere the blob is not.

    The render canvas is centred on the entity, but the SHARK is not: model.offset lifts
    him and the 45-degree camera turns that into up-screen pixels, so his mean alpha sits
    high. Stock declares the spidertron's reflection at shift 0 (on the entity origin);
    recentring lets ours do the same instead of carrying a shift that is just the body's
    lift written down twice.
    """
    from PIL import Image

    data, width = alpha.tobytes(), alpha.width
    mass = weighted_x = weighted_y = 0
    for index, value in enumerate(data):
        if value < floor:
            continue
        mass += value
        weighted_x += value * (index % width)
        weighted_y += value * (index // width)
    if not mass:
        raise PackError("reflection: every pixel is below the alpha floor")
    dx = int(round(fc.origin_pixel(alpha.width) - weighted_x / mass))
    dy = int(round(fc.origin_pixel(alpha.height) - weighted_y / mass))
    moved = Image.new("L", alpha.size, 0)
    moved.paste(alpha, (dx, dy))
    return moved, (dx, dy)


#: name -> a function taking (images, cfg, px_per_tile, floor) and returning (images, note).
#: Named, not passed as a callable, so a Target stays a frozen dataclass of plain data a
#: test can build without importing Pillow.
REDUCERS = {"reflection": reflection_blob}


@dataclass
class Packed:
    """One finished sheet: the dict, the files, and what it took to get there."""

    target: Target
    fields: dict
    frames: list[int]
    paths: list[pathlib.Path]
    box: tuple
    layout: SheetLayout
    #: edge -> (px, frame index): the tightest transparent margin inside a cell, measured off
    #: the finished sheet. Zero on any edge means a clipped sprite, so it travels with the
    #: result, not just a stdout line.
    margins: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    source: pathlib.Path | None = None


# ------------------------------------------------------------------------- packing


def pack_target(cfg, target: Target, out_root: pathlib.Path, *, mod_name: str,
                line_length: int = DEFAULT_LINE_LENGTH, pad: int = DEFAULT_PAD,
                max_side: int = MAX_SHEET_SIDE, visible: int = SPRITE_VISIBLE_ALPHA,
                noise_floor: int = RENDER_NOISE_FLOOR,
                preview: bool = False, explicit_dir=None, allow_clipped: bool = False,
                any_config: bool = False) -> Packed | None:
    """Frames -> sheet PNG(s) + the sprite dict. None when the target has no frames yet.

    TWO THRESHOLDS, ONE JOB EACH. `visible` is what the engine draws: it measures every
    extent and guards every refusal. `noise_floor` is what Cycles scattered: it only ever
    DELETES pixels (the shadow surgery), before anything is measured, so the two never
    disagree about a pixel that ships.
    """
    from PIL import Image

    directory = frames_dir(cfg, target, preview=preview, explicit=explicit_dir)
    if directory is None:
        print(f"  SKIP {target.id}: render pass {target.pass_name!r} does not exist yet "
              f"(art.py knows {', '.join(ac.PASSES)})")
        return None
    if not directory.is_dir():
        if target.optional:
            print(f"  SKIP {target.id}: no frames at {directory}")
            return None
        flags = PASS_FLAG.get(target.pass_name, ("--preview", "--full"))
        raise PackError(
            f"{target.id}: no frames at {directory}\n"
            f"  render them first: uv run --directory tools python render/art.py "
            f"{flags[0] if preview else flags[1]}")

    frames = discover_frames(directory)
    check_frame_set(frames, target.kind, cfg["rotations.count"], str(directory))
    blob = check_pass_hash(cfg, target, directory, any_config=any_config)

    # The frames' OWN derived numbers where the sidecar has them: a render's px-per-tile is
    # a fact about those pixels, not the config file as it stands today.
    key = PASS_PPT.get(target.pass_name, "body_px_per_tile")
    derived = (blob or {}).get("derived") or ac.derived(cfg)
    ppt = derived.get(key) or ac.derived(cfg)[key]

    images = [(i, Image.open(directory / f"frame_{i:03d}.png").convert("RGBA"))
              for i in frames]
    return pack_images(cfg, target, images, ppt, out_root, mod_name=mod_name,
                       line_length=line_length, pad=pad, max_side=max_side, visible=visible,
                       noise_floor=noise_floor, allow_clipped=allow_clipped, source=directory)


def pack_images(cfg, target: Target, images, ppt: float, out_root: pathlib.Path, *,
                mod_name: str, line_length: int = DEFAULT_LINE_LENGTH, pad: int = DEFAULT_PAD,
                max_side: int = MAX_SHEET_SIDE, visible: int = SPRITE_VISIBLE_ALPHA,
                noise_floor: int = RENDER_NOISE_FLOOR, allow_clipped: bool = False,
                source=None, frame_sequence=None, animation_speed=None,
                stamp_blob=None) -> Packed:
    """[(index, RGBA image), ...] -> sheet PNG(s) + the sprite dict. Everything after the
    frames are FOUND: the shadow surgery, the box, the refusals, the layout, the stamp.

    Split from pack_target because a C.21 sequence finds its frames elsewhere (one per
    cache directory, not N in one) and must not get a second copy of anything below.
    """
    frames = [i for i, _ in images]
    canvas = images[0][1].size
    odd = [i for i, img in images if img.size != canvas]
    if odd:
        raise PackError(f"{target.id}: frames {odd[:5]} are not {canvas[0]}x{canvas[1]}; "
                        f"one sheet needs one canvas")

    notes = []
    if target.draw_as_shadow:
        # FIRST, before any measurement: a raw shadow-catcher frame is 1..7 noise edge to
        # edge, and this removes it from the PIXELS instead of hiding it behind a
        # measurement threshold. Everything after this measures what will ship.
        images = [(i, blacken(img, noise_floor)) for i, img in images]
        notes.append(f"shadow surgery: RGB forced to black, alpha < {noise_floor} zeroed "
                     f"BEFORE the box is measured, so the box sees what ships")
    elif target.denoise:
        images = [(i, denoise(img, noise_floor)) for i, img in images]
        notes.append(f"mask surgery: alpha < {noise_floor} zeroed BEFORE the box is "
                     f"measured, so a stray render speck cannot stretch the sheet")
    if target.reduce:
        if target.reduce not in REDUCERS:
            raise PackError(f"{target.id}: no reducer named {target.reduce!r}; known: "
                            f"{', '.join(sorted(REDUCERS))}")
        images, note = REDUCERS[target.reduce](images, cfg, ppt, visible)
        frames = [i for i, _ in images]
        canvas = images[0][1].size      # a reducer may grow the canvas; see reflection_blob
        notes.append(note)

    box, per_frame = union_box(images, visible)
    if box is None:
        raise PackError(f"{target.id}: every frame is empty at alpha >= {visible}")
    clipped = clipped_frames(per_frame, canvas)
    if clipped:
        knob = ("camera.shadow_canvas_tiles" if target.pass_name == "shadow"
                else "camera.canvas_tiles")
        message = (f"{target.id}: {len(clipped)} frame(s) touch the canvas edge at "
                   f"alpha >= {visible} "
                   f"({', '.join(str(i) for i in clipped[:8])}"
                   f"{'...' if len(clipped) > 8 else ''}). The sprite is CUT, not small. "
                   f"Raise {knob} (now {cfg[knob]:.2f}) and re-render.")
        if not allow_clipped:
            raise PackError(message)
        notes.append("CLIPPED, packed anyway on --allow-clipped: " + message)

    box = pad_box(box, pad, canvas)
    width, height, shift = sheet_shift(box, canvas, ppt)
    columns, note = choose_line_length(len(frames), line_length, max_side // width)
    if note:
        notes.append(note)
    try:
        layout = plan_sheet(len(frames), width, height, max_side=max_side,
                            line_length=columns)
    except ValueError as exc:      # spritesheet.py's own guards, as a packer error
        raise PackError(f"{target.id}: {exc}") from None

    # Laid out in memory and MEASURED BEFORE IT IS SAVED. A sheet failing the margin check
    # is never written, so a failed pack cannot leave a clipped PNG for somebody to commit.
    built = build_sheets([img for _, img in images], box, layout)
    worst, per_cell = cell_margins(built, layout, floor=visible)
    notes.append(margin_line(worst, layout, visible))
    tight = tight_frames(per_cell, pad)
    if tight:
        shown = ", ".join(
            "%d %s" % (index, " ".join("%s%d" % pair for pair in zip(EDGES, margins)))
            for index, margins in tight[:6])
        message = (
            f"{target.id}: {len(tight)} frame(s) have visible pixels closer than the "
            f"{pad} px `--pad` promised to their own cell edge ({shown}"
            f"{'...' if len(tight) > 6 else ''}). Measured on the finished cells, so the "
            f"sprite is being CUT by the frame box itself -- not by the render canvas. The "
            f"box comes off the union at alpha >= {visible}; if that union is right this "
            f"cannot happen, so read it as box arithmetic, a crop or a threshold, not as "
            f"something to fix with a bigger --pad.")
        if not allow_clipped:
            raise PackError(message)
        notes.append("CLIPPED BY THE BOX, packed anyway on --allow-clipped: " + message)

    graphics = out_root / GRAPHICS_DIR
    graphics.mkdir(parents=True, exist_ok=True)
    stems = ([target.stem] if layout.file_count == 1
             else [f"{target.stem}-{n + 1}" for n in range(layout.file_count)])
    paths = [graphics / f"{stem}.png" for stem in stems]
    for sheet, path in zip(built, paths):
        sheet.save(path)

    scale = fc.NOMINAL_PX_PER_TILE / ppt
    fields = sprite_fields(target, [f"__{mod_name}__/{GRAPHICS_DIR}/{p.name}" for p in paths],
                           layout, shift, scale, frame_sequence, animation_speed)
    for path in paths:
        sheets.stamp_png(path, stamp_blob or ac.stamp(cfg, {
            "sheet": target.id, "frames": frames, "source": str(source),
            "sprite": fields}))
    return Packed(target=target, fields=fields, frames=frames, paths=paths, box=box,
                  layout=layout, margins=worst, notes=notes, source=source)


def gather_sequence(seq, target: Target, *, preview: bool = False, any_config: bool = False):
    """(images, px_per_tile) for one target of a C.21 sequence: frame k is the sequence's
    ONE direction out of unique config k's own cache directory.

    Every directory is verified against ITS OWN config (check_pass_hash, the standing
    pack's refusal), so a 72-frame sheet is 72 provenance checks and one stale frame stops
    the pack. Missing frames are reported together; one at a time would take 72 runs to
    learn the sequence was never rendered.
    """
    from PIL import Image
    name = f"frame_{seq.direction:03d}.png"
    missing, found = [], []
    for k, cfg in enumerate(seq.configs):
        directory = pass_dir(cfg, target.pass_name,
                             sequence_samples(cfg, target.pass_name, preview))
        if not (directory / name).is_file():
            missing.append(k)
            continue
        found.append((k, cfg, directory))
    if missing:
        raise PackError(
            f"{target.id}: {len(missing)} of {len(seq.configs)} sequence frames have no "
            f"{target.pass_name} render at direction {seq.direction} (unique frames "
            f"{missing[:8]}{'...' if len(missing) > 8 else ''}).\n"
            f"  render them first: uv run --directory tools python render/art.py "
            f"--config <this config> --sequence{' --preview' if preview else ''}")
    images, ppt = [], None
    for k, cfg, directory in found:
        blob = check_pass_hash(cfg, target, directory, any_config=any_config)
        key = PASS_PPT.get(target.pass_name, "body_px_per_tile")
        got = ((blob or {}).get("derived") or ac.derived(cfg)).get(key) or ac.derived(cfg)[key]
        if ppt is not None and abs(got - ppt) > 1e-9:
            raise PackError(f"{target.id}: sequence frame {k} renders at {got} px/tile, the "
                            f"rest at {ppt}; one sheet needs one scale")
        ppt = got
        images.append((k, Image.open(directory / name).convert("RGBA")))
    return images, ppt


def pack_sequence(seq, out_root: pathlib.Path, *, mod_name: str, targets=None,
                  preview: bool = False, any_config: bool = False, **kw) -> list:
    """Every target of a C.21 sequence -> Packed list. `kw` goes to pack_images.

    Stamped with the SEQUENCE's provenance (sequence.Sequence.provenance), not one frame's
    config: the sheet's config_hash is the digest (the id the manifest and Lua carry), and
    the samples it was rendered at are recorded."""
    frame_sequence = seq.frame_sequence()
    out = []
    for target in targets or sequence_targets(seq.name, seq.passes):
        images, ppt = gather_sequence(seq, target, preview=preview, any_config=any_config)
        blob = {"config_hash": seq.digest, "derived": ac.derived(seq.configs[0]),
                "sequence": seq.provenance(sequence_samples_of(seq, preview))}
        out.append(pack_images(seq.configs[0], target, images, ppt, out_root,
                               mod_name=mod_name, source=f"sequence {seq.name} {seq.digest}",
                               frame_sequence=frame_sequence,
                               animation_speed=sequence_speed(), stamp_blob=blob, **kw))
    return out


#: The engine's clock. An animation_speed is cells per TICK, so a sheet rendered at pose.FPS
#: plays at FPS / this.
TICKS_PER_SECOND = 60


def sequence_speed() -> float:
    """animation_speed for a sequence sheet: its render rate against the engine's tick."""
    return pose.FPS / TICKS_PER_SECOND


def sequence_samples_of(seq, preview: bool) -> dict:
    """pass -> the samples its frames were rendered at, for the record."""
    return {t.pass_name: sequence_samples(seq.configs[0], t.pass_name, preview)
            for t in SEQUENCE_TARGETS if t.pass_name in seq.passes}


def denoise(img, floor: int):
    """`img` with every pixel below alpha `floor` made fully transparent, RGB and all; the
    pixels at or above it are untouched. The one noise-floor cut both surgeries share."""
    from PIL import Image
    keep = img.getchannel("A").point(lambda v: 255 if v >= floor else 0)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), keep)
    return out


def blacken(img, floor: int):
    """A Cycles shadow-catcher frame -> what Factorio's draw_as_shadow actually reads."""
    from PIL import Image
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.putalpha(denoise(img, floor).getchannel("A"))
    return out


def build_sheets(images, box, layout):
    """Crop every frame to `box` and paste it into its cell. Returns the sheet(s).

    No compositing: `paste` copies alpha verbatim, while `alpha_composite` would blend the
    sprite against the sheet's transparency and eat the edge ramp. Returns instead of saving
    so the caller can MEASURE the finished cells before any reaches the disk.
    """
    from PIL import Image
    per_file = layout.frames_per_file
    built = []
    for index in range(layout.file_count):
        sheet = Image.new("RGBA", layout.sheet_size(index), (0, 0, 0, 0))
        first = index * per_file
        for n in range(first, min(first + per_file, layout.frame_count)):
            slot = n - first
            col, row = slot % layout.line_length, slot // layout.line_length
            sheet.paste(images[n].crop(box),
                        (col * layout.frame_width, row * layout.frame_height))
        built.append(sheet)
    return built


# ------------------------------------------------------------------------ emitting


def slot_map(packed: list[Packed]) -> dict:
    """graphics_set slot -> the sprite ids in it, in layer order."""
    out: dict[str, list[str]] = {}
    for item in sorted(packed, key=lambda p: (p.target.slot, p.target.order)):
        out.setdefault(item.target.slot, []).append(item.target.id)
    return out


def clear_list(slots) -> list[str]:
    """Stock slots no sheet of ours covers. entity.lua must nil these or the stock
    spidertron's art keeps drawing under (and beside) Jamal."""
    return [s for s in STOCK_ART_SLOTS if s not in slots]


def manifest_blob(cfg, packed: list[Packed], *, mod_name: str, seq=None,
                  samples: dict | None = None) -> dict:
    """The JSON the linter eats. `sprites` entries are the SAME dicts plus an `id`.

    `mod_roots` is relative to the manifest, so the tree lints in place with no flags; CI's
    --mod-root still wins (lint_sprites.specs_from_manifest only fills roots the CLI has
    not claimed).
    """
    slots = slot_map(packed)
    blob = {
        "version": MANIFEST_VERSION,
        "generated_by": "tools/render/pack.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        # A sequence has no one config: its id is the digest over every frame's hash.
        "config_hash": seq.digest if seq is not None else ac.config_hash(cfg),
        "mod": mod_name,
        "mod_roots": {mod_name: ".."},
        "slots": slots,
        "clear": clear_list(slots),
        "sprites": [dict(id=p.target.id, **p.fields) for p in packed],
    }
    if seq is not None:
        blob["sequence"] = {"name": seq.name, "direction": seq.direction,
                            "passes": list(seq.passes),
                            "played": len(seq.order), "unique": len(seq.configs),
                            "samples": samples or {}, "frame_hashes": list(seq.hashes)}
    return blob


#: Numbers per line before a numeric list wraps. 20 three-digit indices is ~100 columns.
LUA_NUMBERS_PER_LINE = 20


def lua_value(value, indent: str) -> str:
    """A Python value as Lua source. Numbers keep their exact decimal form."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = repr(value)
        return text[:-2] if text.endswith(".0") else text
    if isinstance(value, (list, tuple)):
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            if len(value) <= LUA_NUMBERS_PER_LINE:
                return "{" + ", ".join(lua_value(v, indent) for v in value) + "}"
            # A 117-frame frame_sequence on one line is 450 characters against luacheck's
            # 120, and the generated file is linted like any other.
            inner = indent + "  "
            rows = [", ".join(lua_value(v, inner) for v in value[i:i + LUA_NUMBERS_PER_LINE])
                    for i in range(0, len(value), LUA_NUMBERS_PER_LINE)]
            return "{\n" + ",\n".join(inner + r for r in rows) + "\n" + indent + "}"
        inner = indent + "  "
        body = ",\n".join(inner + lua_value(v, inner) for v in value)
        return "{\n" + body + "\n" + indent + "}"
    raise PackError(f"no Lua form for {value!r}")


def lua_table(fields: dict, indent: str = "") -> str:
    """Brace on its own line, one field per line: base's prototype-file shape, so a
    generated table reads like a hand-written one in a diff."""
    body = ",\n".join(f"{indent}  {key} = {lua_value(value, indent + '  ')}"
                      for key, value in fields.items())
    return indent + "{\n" + body + "\n" + indent + "}"


def lua_blob(cfg, packed: list[Packed], *, seq=None, origin: str = "render/jamaltron.toml") -> str:
    """The generated data-stage module. Same dicts, Lua syntax, nothing added.

    Emits the sprites by id AND assembled into their graphics_set slots, sharing table
    references, so `sprites.body` and `slots.animation.layers[1]` are one table in Lua as
    they are one dict here. No ---@type annotations: the slot decides whether a table is a
    RotatedAnimation or a RotatedSprite, so the annotation belongs at the assignment in
    entity.lua, where a wrong one is a real finding.
    """
    slots = slot_map(packed)
    ident = seq.digest if seq is not None else ac.config_hash(cfg)
    what = ("%d animation frames'" % max(len(p.frames) for p in packed) if seq is not None
            else "%d rotations'" % max(len(p.frames) for p in packed))
    lines = [
        "-- GENERATED by tools/render/pack.py from %s. DO NOT EDIT." % origin,
        "--",
        "-- Every number here was measured off the rendered frames: the frame box is the",
        "-- union of all %s alpha, and the shift is the distance from the render" % what,
        "-- canvas's own origin pixel to the cropped frame's centre. The JSON manifest",
        "-- beside the sheets is these same tables plus an id, which is what",
        "-- tools/lint_sprites.py checks against the real PNGs.",
        "--",
    ]
    if seq is not None:
        lines += [
            "-- SEQUENCE %s (C.21): %d played frames at %d fps out of %d unique renders, one"
            % (seq.name, len(seq.order), pose.FPS, len(seq.configs)),
            "-- direction (%d). frame_sequence is the order they play in; a repeated cell is"
            % seq.direction,
            "-- loaded once. config_hash below is the digest over every frame's own config",
            "-- hash, so it moves if any frame's knobs do. Every sheet carries its",
            "-- animation_speed (%s: %d fps against the engine's %d ticks a second)."
            % (lua_value(sequence_speed(), ""), pose.FPS, TICKS_PER_SECOND),
            "--",
        ]
    lines += [
        "-- config %s   packed %s" % (ident, time.strftime("%Y-%m-%d %H:%M:%S")),
        "",
        "local sprites = {}",
        "",
    ]
    for item in packed:
        lines.append("sprites.%s =" % item.target.id)
        lines.append(lua_table(item.fields))
        lines.append("")

    lines += [
        "-- The slots as the entity prototype wants them. graphics_set[slot] = value,",
        "-- which REPLACES the stock layer stack wholesale -- a layer we do not emit",
        "-- cannot survive underneath.",
        "local slots =",
        "{",
    ]
    for slot, ids in slots.items():
        wrap = SLOT_WRAP.get(slot, "layers")
        refs = ", ".join("sprites.%s" % i for i in ids)
        if wrap is None or wrap in SINGLE_WRAPS:
            if len(ids) != 1:
                raise PackError(f"slot {slot} takes one sprite, got {ids}")
            lines.append("  %s = sprites.%s," % (slot, ids[0]) if wrap is None
                         else "  %s = {%s = sprites.%s}," % (slot, wrap, ids[0]))
        else:
            lines.append("  %s = {%s = {%s}}," % (slot, wrap, refs))
    lines += [
        "}",
        "",
        "-- Stock graphics_set slots NO sheet of ours covers. entity.lua deepcopies the",
        "-- spidertron, so these still hold WUBE'S art and must be set to nil, or a stock",
        "-- plate draws under the shark. base_animation is deliberate, not missing: at the",
        "-- C.13 harness ratio all 8 mounts land on the shark's own silhouette at all 64",
        "-- rotations (512/512 samples measured), so there is nothing for a plate to cover.",
        "local clear =",
        "{",
    ]
    for slot in clear_list(slots):
        lines.append('  "%s",' % slot)
    lines += [
        "}",
        "",
        "return",
        "{",
        '  config_hash = "%s",' % ident,
        "  sprites = sprites,",
        "  slots = slots,",
        "  clear = clear,",
        "}",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- crushing


def crush(paths, *, tool: str | None = None) -> list[str]:
    """oxipng over the sheets, kept only when the pixels come back identical.

    Returns report lines. pngcrush and optipng are not installed here (and oxipng is the
    fastest of the three); with no oxipng this says so and changes nothing.
    """
    from PIL import Image
    binary = tool or shutil.which("oxipng")
    if binary is None:
        return ["crush SKIPPED: oxipng not on PATH (`brew install oxipng`); pngcrush and "
                "optipng are not installed on this machine either"]
    out = []
    for path in paths:
        before = path.stat().st_size
        source = Image.open(path)
        source.load()
        original, was_stamped = source.convert("RGBA").tobytes(), bool(source.text)
        backup = path.read_bytes()      # in memory: a stray .orig beside the sheets is
        started = time.time()           # one more file CI has to judge
        # No --strip: the config-hash text chunk IS the provenance, and `--strip safe`
        # takes it. -o 4 is oxipng's cost/benefit knee on sheets this size.
        proc = subprocess.run([binary, "-o", "4", "--quiet", str(path)],
                              capture_output=True, text=True)
        elapsed = time.time() - started
        if proc.returncode != 0:
            path.write_bytes(backup)
            out.append(f"crush FAILED on {path.name}: {proc.stderr.strip()[:200]}")
            continue
        crushed = Image.open(path)
        crushed.load()
        if crushed.convert("RGBA").tobytes() != original:
            path.write_bytes(backup)
            out.append(f"crush REVERTED on {path.name}: pixels changed, so it was not "
                       f"lossless. Shipping the uncrushed sheet.")
            continue
        if was_stamped and "jamaltron:config_hash" not in (crushed.text or {}):
            path.write_bytes(backup)
            out.append(f"crush REVERTED on {path.name}: the provenance text chunk was "
                       f"stripped, and the stamp is how a sheet stays traceable.")
            continue
        after = path.stat().st_size
        out.append("crush %-34s %7.1f KiB -> %7.1f KiB  (-%.1f%%, %.1fs)"
                   % (path.name, before / 1024, after / 1024,
                      100.0 * (before - after) / before, elapsed))
    return out


# -------------------------------------------------------------------------- verifying


def verify(manifest_path: pathlib.Path, mod_root: pathlib.Path, *,
           mod_name: str = MOD_NAME, strict: bool = True):
    """Run the C.8 gate over what we just wrote. Returns (ok, text).

    Same code and --strict as CI, so a sheet that would fail CI fails pack.py first.
    Importing, not shelling out, keeps the failure a Python value.
    """
    import lint_sprites as lint

    mods = lint.ModPaths()
    mods.add(mod_name, mod_root)
    findings, declarations, files = lint.lint([manifest_path], mods, strict=strict)
    errors = [f for f in findings if f.severity == lint.ERROR]
    warnings = [f for f in findings if f.severity == lint.WARN]
    text = "\n".join(f.render() for f in errors + warnings)
    ok = not errors and not (warnings and strict)
    tally = (f"{declarations} declaration(s), {files} file(s), {len(errors)} error(s), "
             f"{len(warnings)} warning(s)")
    return ok, (text + "\n" if text else "") + f"lint-sprites: {'PASSED' if ok else 'FAILED'}  {tally}"


# -------------------------------------------------------------------------------- cli


def resolve_mod_name(out_root: pathlib.Path) -> str:
    """The mod a tree belongs to, from its own info.json when it has one."""
    info = out_root / "info.json"
    if info.is_file():
        name = json.loads(info.read_text()).get("name")
        if name:
            return name
    return MOD_NAME


def build_parser():
    p = argparse.ArgumentParser(
        prog="pack.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    w = p.add_argument_group("where")
    w.add_argument("--out", default=None,
                   help=f"mod root to write into (default {DEFAULT_OUT}, gitignored)")
    w.add_argument("--promote", action="store_true",
                   help=f"write into {PROMOTE_OUT} -- the tree CI lints with --strict and "
                        f"the one carrying the sprite licence carve-out")
    w.add_argument("--frames-dir", action="append", default=[], metavar="TARGET=DIR",
                   help="override one target's frame directory")

    k = p.add_argument_group("knobs")
    k.add_argument("--config", default=None, help="config TOML (default render/jamaltron.toml)")
    k.add_argument("--set", action="append", dest="sets", metavar="key=value",
                   help="override one knob, TOML syntax (same as art.py)")
    k.add_argument("--preview", action="store_true",
                   help="pack the preview-samples body cache instead of the full one")
    k.add_argument("--line-length", type=int, default=DEFAULT_LINE_LENGTH,
                   help=f"frames per row (default {DEFAULT_LINE_LENGTH}, stock's own torso "
                        f"layout); reduced to a divisor of the frame count if it is not one")
    k.add_argument("--pad", type=int, default=DEFAULT_PAD,
                   help=f"px of transparent margin around the union alpha box, and the "
                        f"margin every finished cell is then checked against "
                        f"(default {DEFAULT_PAD})")
    k.add_argument("--max-side", type=int, default=MAX_SHEET_SIDE,
                   help=f"per-sheet px ceiling (default {MAX_SHEET_SIDE})")
    k.add_argument("--targets", default=None,
                   help="comma-separated target ids to pack (default all)")

    h = p.add_argument_group("how")
    h.add_argument("--crush", action="store_true",
                   help="run oxipng afterwards, keeping the result only if it is lossless")
    h.add_argument("--no-verify", action="store_true",
                   help="skip the --strict lint of the manifest we just wrote")
    h.add_argument("--allow-clipped", action="store_true",
                   help="pack frames whose visible alpha touches the render canvas edge, "
                        "or whose finished cells lose the --pad margin (they are CUT)")
    h.add_argument("--any-config", action="store_true",
                   help="pack frames whose pass hash does not match the config")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        cfg = ac.load(args.config, ac.parse_set(args.sets))
    except ac.ConfigError as exc:
        sys.stderr.write("pack.py: %s\n" % exc)
        return 2

    root = pathlib.Path(args.out) if args.out else pathlib.Path(
        PROMOTE_OUT if args.promote else DEFAULT_OUT)
    if not root.is_absolute():
        root = REPO / root
    mod_name = resolve_mod_name(root)

    overrides = {}
    for pair in args.frames_dir:
        name, _, value = pair.partition("=")
        if not name or not value:
            sys.stderr.write(f"pack.py: --frames-dir wants TARGET=DIR, got {pair!r}\n")
            return 2
        overrides[name] = value

    # A config with a [sequence] (render/beached.toml) packs THAT: one sheet per pass,
    # gathered frame by frame across per-config cache dirs. See pack_sequence.
    from render import sequence as sequence_mod
    try:
        table = ac.load_sequence(args.config)
        seq = sequence_mod.parse(table, cfg) if table is not None else None
    except ac.ConfigError as exc:
        sys.stderr.write("pack.py: %s\n" % exc)
        return 2
    if seq is not None and overrides:
        sys.stderr.write("pack.py: --frames-dir does not apply to a sequence; its frames "
                         "come from one cache dir per frame config\n")
        return 2
    catalogue = sequence_targets(seq.name, seq.passes) if seq is not None else TARGETS

    wanted = set(args.targets.split(",")) if args.targets else None
    targets = [t for t in catalogue if wanted is None or t.id in wanted]
    if wanted and not targets:
        sys.stderr.write(f"pack.py: no target matches {sorted(wanted)}; known: "
                         f"{', '.join(t.id for t in catalogue)}\n")
        return 2

    if seq is not None:
        print("jamaltron pack  sequence %s %s (%d played, %d unique, direction %d)  -> %s"
              % (seq.name, seq.digest, len(seq.order), len(seq.configs), seq.direction,
                 _relative(root)))
    else:
        print("jamaltron pack  config %s  -> %s" % (ac.config_hash(cfg), _relative(root)))
    packed: list[Packed] = []
    try:
        if seq is not None:
            packed = pack_sequence(seq, root, mod_name=mod_name, targets=targets,
                                   preview=args.preview, any_config=args.any_config,
                                   line_length=args.line_length, pad=args.pad,
                                   max_side=args.max_side,
                                   allow_clipped=args.allow_clipped)
            for item in packed:
                report(item)
            for path in drop_unshipped(seq, root):
                print("  removed %s (sequence %s ships passes %s)"
                      % (_relative(path), seq.name, "+".join(seq.passes)))
        for target in (targets if seq is None else ()):
            item = pack_target(cfg, target, root, mod_name=mod_name,
                               line_length=args.line_length, pad=args.pad,
                               max_side=args.max_side, preview=args.preview,
                               explicit_dir=overrides.get(target.id),
                               allow_clipped=args.allow_clipped,
                               any_config=args.any_config)
            if item is None:
                continue
            packed.append(item)
            report(item)
    except PackError as exc:
        sys.stderr.write("pack.py: %s\n" % exc)
        return 1

    if not packed:
        sys.stderr.write("pack.py: nothing packed; no target had frames\n")
        return 1

    # Two cross-target facts no single sheet can see. Neither is fatal (a coarse sheet is
    # legitimate to look at), but both ship as a wrong-looking vehicle instead of an error,
    # so they get said explicitly.
    rotating = {p.fields["direction_count"] for p in packed
                if p.target.kind == "rotations"}
    if len(rotating) > 1:
        print("  WARN the rotating sheets disagree on direction_count (%s). The body and "
              "its shadow would turn at different rates; pack them from the same render."
              % ", ".join(str(n) for n in sorted(rotating)))
    if seq is not None and args.preview:
        # The standing path's preview guard is a coarse direction_count, which an animation
        # never has, so without this a preview-samples flop promotes silently.
        print("  WARN packed at PREVIEW samples (%s): fine to look at, not the shipping "
              "sheet. Drop --preview (after art.py --sequence without it) to ship"
              % ", ".join("%s %d" % kv for kv in sequence_samples_of(seq, True).items()))
    coarse = sorted(n for n in rotating if n < cfg["rotations.count"])
    if coarse:
        print("  WARN direction_count %s against rotations.count %d: this is a PREVIEW "
              "sheet, fine to look at and not fine to ship."
              % (", ".join(str(n) for n in coarse), cfg["rotations.count"]))

    graphics = root / GRAPHICS_DIR
    manifest_name, lua_name = (sequence_outputs(seq.name) if seq is not None
                               else (MANIFEST_NAME, LUA_NAME))
    manifest_path = graphics / manifest_name
    samples = sequence_samples_of(seq, args.preview) if seq is not None else None
    manifest_path.write_text(json.dumps(manifest_blob(cfg, packed, mod_name=mod_name, seq=seq,
                                                      samples=samples), indent=2) + "\n")
    lua_path = root / PROTOTYPES_DIR / lua_name
    lua_path.parent.mkdir(parents=True, exist_ok=True)
    lua_path.write_text(lua_blob(cfg, packed, seq=seq, origin=config_label(args.config)))

    sheet_paths = [p for item in packed for p in item.paths]
    total = sum(p.stat().st_size for p in sheet_paths)
    print("  %d sheet(s), %.1f KiB" % (len(sheet_paths), total / 1024))
    if args.crush:
        for line in crush(sheet_paths):
            print("  " + line)
        crushed = sum(p.stat().st_size for p in sheet_paths)
        if crushed != total:
            print("  crush total %.1f KiB -> %.1f KiB (-%.1f%%)"
                  % (total / 1024, crushed / 1024, 100.0 * (total - crushed) / total))
    print("  -> %s" % _relative(manifest_path))
    print("  -> %s" % _relative(lua_path))

    slots = slot_map(packed)
    print("  slots %s" % ", ".join("%s(%s)" % (s, "+".join(ids)) for s, ids in slots.items()))
    cleared = clear_list(slots)
    print("  clear %s  <- entity.lua must nil these or stock art keeps drawing"
          % ", ".join(cleared))
    if "animation" in cleared:
        print("  WARN `animation` is in that list, i.e. this run packed no body sheet. "
              "Applied as-is the entity has NO torso sprite at all. A subset pack is for "
              "looking at, not for promoting.")

    if args.no_verify:
        return 0
    ok, text = verify(manifest_path, root, mod_name=mod_name, strict=True)
    for line in text.splitlines():
        print("  " + line)
    return 0 if ok else 1


def config_label(path) -> str:
    """How the generated Lua names the config it came from: relative to tools/ (where every
    documented command runs, so `render/beached.toml`), else to the repo, else as given."""
    p = pathlib.Path(path).resolve() if path else ac.DEFAULT_CONFIG_PATH
    for root in (REPO / "tools", REPO):
        try:
            return str(p.relative_to(root))
        except ValueError:
            continue
    return str(p)


def report(item: Packed) -> None:
    """One packed sheet as a line of stdout, plus its notes."""
    geometry = item.fields
    count = geometry.get("direction_count") or geometry.get("frame_count") or 1
    played = geometry.get("frame_sequence")
    print("  %-10s %2d frames%s  %3dx%-3d  ll %-2d  shift %+.4f,%+.4f tiles "
          "(by_pixel %+.1f,%+.1f)  %s"
          % (item.target.id, len(item.frames),
             " (%d played)" % len(played) if played else "",
             geometry["width"], geometry["height"],
             geometry["line_length"], geometry["shift"][0], geometry["shift"][1],
             geometry["shift"][0] * 32, geometry["shift"][1] * 32,
             ", ".join("%dx%d" % item.layout.sheet_size(i)
                       for i in range(item.layout.file_count))))
    assert count >= 1
    for note in item.notes:
        print("       NOTE " + note)


def _relative(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
