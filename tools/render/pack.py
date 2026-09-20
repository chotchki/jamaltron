#!/usr/bin/env python3
"""C.7, the packer: rendered frames -> sprite sheets -> the Lua table AND the JSON manifest.

    uv run --directory tools python render/pack.py                 # into render-out/pack (gitignored)
    uv run --directory tools python render/pack.py --promote       # into mod/jamaltron, where CI looks
    uv run --directory tools python render/pack.py --preview       # pack the 8-frame preview cache
    uv run --directory tools python render/pack.py --crush         # oxipng afterwards, verified lossless

ONE DICT, TWO ARTIFACTS. Every number a prototype needs -- width, height, line_length,
direction_count, frame_count, lines_per_file, scale, shift -- is computed once, into one
Python dict per sprite, and that dict is serialized twice: as a Lua table for the data
stage and as a JSON entry for `tools/lint_sprites.py`. The manifest entry is the Lua table
plus an `id`, nothing else, because the two artifacts sharing field names is what makes the
gate real. There is no translation layer for them to drift across, and no number anywhere
in the repo that a human typed off a render.

WHERE THE OUTPUT GOES, AND WHY IT IS NOT A DETAIL. `--out` names a MOD ROOT, and the tree
under it is mod-shaped either way:

    <out>/graphics/jamaltron-body.png        the sheets
    <out>/graphics/sprites.json              the manifest, BESIDE the sheets
    <out>/prototypes/sprites_generated.lua   the table the data stage requires

.github/workflows/ci.yml derives `--strict` from the manifest's PATH, in one `case`, and
the path it matches is `mod/jamaltron/graphics`. A manifest anywhere else is either linted
in the tolerant mode (useless on art we generated: our sheets come off an exact grid, so
every warning is a defect) or trips the job's stray-manifest tripwire. Sheets committed
with no manifest beside them fail CI on purpose. So the default `--out render-out/pack` is
a dry run that is lintable IN PLACE -- same relative shape, `mod_roots` pointing one
directory up -- and `--promote` is the deliberate act that writes into the tree carrying
the RenderHub carve-out licence.

WHAT THE PACKER DECIDES, measured rather than chosen:

  * THE FRAME BOX is the UNION of every frame's alpha bounding box, padded by `--pad`.
    One box for the whole sheet, because Factorio gets ONE width, ONE height and ONE shift
    for all 64 rotations. Union, not per-frame: a box that fits frame 0 clips frame 32.
  * THE SHIFT falls out of that box. Our canvas is centred on the entity origin by
    construction (the camera looks at the world origin), so the origin sits at pixel index
    (res-1)/2 -- see factorio_camera.origin_pixel for why that is not res/2 -- and the
    shift is the distance from there to the cropped frame's own centre, in tiles.
    Cross-checked against the stock torso in tests: 132x138 with the entity at pixel
    (65.5, 106.5) is shift by_pixel(0, -19), which is what Wube declares.
  * LINE_LENGTH IS ALWAYS EMITTED, and it always DIVIDES the frame count. Without it the
    engine's default depends on which prototype field is loading and the linter can only
    check a frame budget. And a line_length that does not divide the count leaves blank
    cells in the last row, which `--strict` reports as `unused-frames` -- correctly, since
    a sheet we generated should not carry frames nothing draws. Ask for 8 (stock's own
    torso layout) on a count 8 does not divide and you get the largest divisor that fits,
    with a line on stdout saying so.
  * CLIPPED IS FATAL. If any frame's alpha touches its canvas edge the sprite is cut, not
    small, and it ships as a shark with a flat dorsal fin. Raise camera.canvas_tiles and
    re-render. `--allow-clipped` exists for deliberate experiments and says so loudly.
  * STALE FRAMES ARE FATAL. Every frame directory carries art.py's own config.json; the
    pass hash in it must match the config being packed, or you are shipping pixels from
    knobs you have since moved. `--any-config` overrides, for packing somebody else's
    frames on purpose.

SHADOW SHEETS GET SURGERY, and it is deliberate: RGB forced to black and alpha below
SPRITE_ALPHA_FLOOR zeroed. Factorio draws a `draw_as_shadow` sprite as a darkening mask
where only alpha matters (stock's spidertron-body-shadow.png is a palette PNG of pure
black plus alpha), and a Cycles shadow catcher scatters alpha 1..7 sampling noise across
the whole plane -- MEASURED, 9537 noise pixels on a 704px frame. Left in, that noise is a
faint grey rectangle over every tile the shark stands near.

BASE_ANIMATION: NOT WORTH RENDERING, and the number that settles it is 512/512. Stock
needs a non-rotating under plate because its legs bolt to the corners of a machine and its
rotating torso does not reach them; the plate is what the mounts land on. Jamal is in a
HARNESS -- C.13 moved the mounts inboard to 0.45 of stock, +-0.352 tiles transverse.
MEASURED on the shipped 64-frame body render at that ratio: all eight mounts land on
opaque shark at all 64 rotations, 512 of 512 samples, no rotation below 8/8. At the
unshrunk stock ring the same render covers 171 of 512, which is what a plate would have
had to cover and is why stock ships one. There is nothing left for a plate to do, so the
packer emits no base_animation and instead names it in `clear`, because entity.lua
deepcopies the stock spidertron and an uncleared slot keeps drawing WUBE'S PLATE under our
shark. The one thing that would reopen this is the in-game walk cycle showing a seam where
the leg tops meet him; that is F.2's eyeball, not a number.

THE RUNTIME-TINT MASK is a real render pass (`mask`), not a packer trick: same camera,
same canvas, one flat grey shader whose alpha is a harness band in the model's own local
coordinates. See the [mask] block in jamaltron.toml for why the tinted region is the
harness and not the whole fish. Here it is just another target whose frames crop to their
own box -- which comes out smaller than the body's, exactly as stock's 130x100 mask does
against its 132x138 body.

THE WATER REFLECTION is built HERE, from the body frames, because there is nothing to
render. Stock's spidertron-body-water-reflection.png is one 448x448 frame, variation_count
1, shift 0, every pixel pure red (255,0,0) with the shape entirely in the alpha: a soft
blurred ellipse 194x133 px, 1.7x the torso sprite's own footprint, centred on the entity
origin. The 448 canvas is Wube not cropping a 5.6 KiB palette PNG, not a number to match.
Ours is the same object derived honestly -- the MEAN alpha of all 64 body rotations, which
is rotationally symmetric by construction, gained, blurred, recentred on the origin and
forced to red. A REDUCE target: 64 frames in, one variation out.

PNG CRUSHING: WORTH IT, WITH THE TOOL THAT IS ACTUALLY HERE. pngcrush and optipng are not
installed on this machine; oxipng is (`brew install oxipng`), and it is the faster tool of
the three anyway. `--crush` runs it, then re-opens every sheet and compares RGBA bytes
against the original before keeping the result -- a "lossless" optimizer is a claim, and
this is a sprite pipeline with no in-game validation to catch a broken claim. Metadata is
NOT stripped: the config-hash text chunk this tool writes is the provenance, and
`--strip safe` would quietly take it. Measured savings are printed per sheet. It is off by
default because it is seconds per sheet and the iteration loop should not pay for it.

Runs on the uv side (Pillow). Imports art.py for SPRITE_ALPHA_FLOOR and the cache-directory
naming on purpose: if this module computed its own pass directory it would eventually
disagree with the renderer's, and pack the wrong frames without a word.
"""

# sys.path, verbatim per tools/README.md -- Python and Blender both put THIS file's own
# directory on sys.path[0], never tools/, and `package = false` means there is no installed
# `render` to fall back on. Cannot be factored into a helper: importing the helper is the
# thing that needs the path fixed.
import pathlib, sys  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402

from render import artconfig as ac  # noqa: E402
from render import factorio_camera as fc  # noqa: E402
from render import sheets  # noqa: E402
from render.art import REPO, SPRITE_ALPHA_FLOOR, pass_dir  # noqa: E402
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

#: Stock's own torso layout: 64 frames of 132x138 in an 8x8 grid. Ours matches so a
#: contact sheet and a shipped sheet can be eyeballed against each other.
DEFAULT_LINE_LENGTH = 8

#: Pixels of margin around the union alpha box. The box is measured at
#: SPRITE_ALPHA_FLOOR, so the 1..7 antialiasing fringe sits just outside it; one pixel
#: keeps that fringe rather than shaving the silhouette's edge ramp.
DEFAULT_PAD = 1

#: How a graphics_set slot wraps its sprite(s). Read off spidertron-animations.lua's
#: spidertron_torso_graphics_set: `animation` and `base_animation` are layer STACKS,
#: `shadow_animation` is a BARE sprite, and `water_reflection` is a
#: WaterReflectionDefinition whose `pictures` stock fills with ONE sprite table, not a list
#: -- `pictures` is SpriteVariations, and the single-sheet form is the one that may carry
#: `variation_count`. Wrapping it in a list instead would declare an array of Sprites, and
#: a Sprite has no variation_count for the engine to read.
SLOT_WRAP = {
    "animation": "layers",
    "base_animation": "layers",
    "shadow_animation": None,
    "shadow_base_animation": None,
    "water_reflection": "pictures",
}

#: Wraps that name ONE sprite under a key rather than a list of them.
SINGLE_WRAPS = ("pictures",)

#: Every graphics_set slot the stock spidertron fills with STOCK ART. entity.lua
#: deepcopies that prototype, so any slot we do not overwrite keeps drawing a spidertron.
#: The ones no target covers are emitted as `clear` -- see the module docstring.
STOCK_ART_SLOTS = ("base_animation", "shadow_base_animation", "animation",
                   "shadow_animation", "water_reflection")

#: Which derived px-per-tile a pass renders at. The mask shares the body canvas exactly,
#: which is what makes its frames croppable against the same origin pixel.
PASS_PPT = {"body": "body_px_per_tile", "shadow": "shadow_px_per_tile",
            "mask": "body_px_per_tile"}

#: The art.py flags that render each pass, as (preview, full), so "no frames" can say
#: exactly what to type instead of naming a flag that renders the wrong pass.
PASS_FLAG = {"body": ("--preview", "--full"),
             "shadow": ("--shadow", "--shadow --full"),
             "mask": ("--mask", "--mask --full")}


@dataclass(frozen=True)
class Target:
    """One sheet to build: where its frames come from, where its numbers end up.

    This table is the contract C.4 fills. Adding a pass means adding a row, not editing
    the packer -- which is why `pass_name` is allowed to name a render pass that does not
    exist yet: the row documents the slot and the run prints what is missing.
    """

    id: str                       # manifest id, Lua key, and the name in every finding
    slot: str                     # graphics_set key it lands in
    order: int                    # position within the slot's layer stack
    pass_name: str                # render pass supplying the frames
    stem: str                     # sheet filename stem under graphics/
    # How Factorio counts the cells: "rotations" -> direction_count, "animation" ->
    # frame_count, "variations" -> variation_count. Same pixels, three declarations, and
    # the engine multiplies all three.
    kind: str = "rotations"
    draw_as_shadow: bool = False
    apply_runtime_tint: bool = False
    optional: bool = False        # a missing frame directory is a note, not an error
    # Name in REDUCERS. A reduce target consumes a whole pass and emits FEWER frames than
    # it read -- the water reflection is 64 rotations in and one blob out.
    reduce: str | None = None


#: THE SHIPPED TARGETS. Four sheets, three passes: the reflection rides the body's frames.
#:
#: `body_mask` is layer 1 of `animation`, over the body, exactly where stock puts
#: spidertron-body-mask.png. Without it the entity colour picker does nothing at all,
#: which would also make D.4's careful preservation of `color` across the beached swap
#: dead code. It is no longer optional: a promote that quietly shipped no tint layer is
#: the failure this row exists to prevent.
TARGETS = (
    Target(id="body", slot="animation", order=0, pass_name="body",
           stem="jamaltron-body"),
    Target(id="body_mask", slot="animation", order=1, pass_name="mask",
           stem="jamaltron-body-mask", apply_runtime_tint=True),
    Target(id="shadow", slot="shadow_animation", order=0, pass_name="shadow",
           stem="jamaltron-body-shadow", draw_as_shadow=True),
    Target(id="reflection", slot="water_reflection", order=0, pass_name="body",
           stem="jamaltron-body-water-reflection", kind="variations",
           reduce="reflection"),
)


class PackError(RuntimeError):
    """A fatal packing problem, phrased for the person who has to fix it."""


# ------------------------------------------------------------------ frame discovery


def frames_dir(cfg, target: Target, *, preview: bool = False, explicit=None):
    """Where `target`'s frames live, or None when its render pass does not exist yet.

    Derived from art.py's own pass_dir(), never recomputed here: a second copy of the
    cache-naming rule is a second chance to read a directory the renderer never wrote.
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

    art.py's --preview renders indices 0, 8, 16 ... 56 of 64, and packing those as a
    64-direction sheet is fine at direction_count 8: frame i covers orientation i/8. A
    directory holding 48 of 64 frames because a render died halfway is NOT fine, and it
    looks identical on disk. So the set is checked rather than counted. An `animation`
    target has no ring: its frames are a clip and must run 0..N-1 with no gap.
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

    art.py writes config.json into every pass directory, holding the resolved knobs AND
    the per-pass hash. Comparing it here is the difference between "these pixels came
    from the config I am about to stamp on them" and a hope.
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
            # The pass hash covers `model.blend` as a CONTENT digest, so a mismatch can
            # also mean "the model is not on this machine" rather than "a knob moved".
            # Say which: the two have completely different fixes.
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


def union_box(images, floor: int = SPRITE_ALPHA_FLOOR):
    """Union of every frame's alpha bounding box. One box for the whole sheet.

    Returns (box, per_frame) so a caller can report WHICH frame is widest -- when the box
    is bigger than expected the answer is always one rotation, and naming it saves opening
    64 files.
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
    """Frames whose alpha touches the canvas edge. See the module docstring: fatal."""
    width, height = canvas
    return [i for i, b in per_frame
            if b is not None and (b[0] <= 0 or b[1] <= 0 or b[2] >= width or b[3] >= height)]


def pad_box(box, pad: int, canvas):
    """Grow the union box by `pad` px, clamped to the canvas."""
    width, height = canvas
    return (max(0, box[0] - pad), max(0, box[1] - pad),
            min(width, box[2] + pad), min(height, box[3] + pad))


def sheet_shift(box, canvas, px_per_tile: float):
    """Frame size and Factorio `shift` for a crop out of an origin-centred canvas.

    The canvas is centred on the entity origin, so the origin is at pixel index
    (res-1)/2. A sprite is drawn with its own CENTRE `shift` tiles from the entity, so
    the shift is centre-minus-origin measured inside the cropped frame, divided by the
    render's px-per-tile. `util.by_pixel(x, y)` is this number times 32.

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

    A line_length that does not divide the count leaves blank cells in the last row, and
    `--strict` -- the mode CI runs our own manifests in -- reports those as unused-frames.
    Correctly: art we generated should not ship frames nothing draws. Returns
    (line_length, note) where note is "" when the request survived untouched.
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

#: Field order for the one dict. Factorio ignores order; a diff does not, and these two
#: artifacts are read side by side when a number looks wrong.
FIELD_ORDER = ("filename", "filenames", "width", "height", "line_length",
               "direction_count", "frame_count", "variation_count", "lines_per_file",
               "scale", "shift", "draw_as_shadow", "apply_runtime_tint")

#: kind -> the ONE count field Factorio should read, and what the other two default to.
#: Emitting only the one that applies is deliberate: `direction_count = 1` on a
#: SpriteVariations is a field that struct does not have, and stock never writes it.
COUNT_FIELD = {"rotations": "direction_count", "animation": "frame_count",
               "variations": "variation_count"}


def sprite_fields(target: Target, filenames, layout, shift, scale: float) -> dict:
    """THE dict. The Lua table and the manifest entry are both this, verbatim.

    Built off SheetLayout.prototype_fields() rather than re-deriving the geometry, with
    one remap: the layout counts FRAMES and only the target knows whether those frames
    are directions (a rotating body) or animation frames (C.5's flop loop). Factorio
    spells those as different keys and multiplies them together.
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
    # A rotated sheet still says frame_count = 1 out loud, because that is the pair a
    # reader checks; the other two kinds leave the fields their struct does not own alone.
    if target.kind == "rotations":
        fields["frame_count"] = 1
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
    axis -- a 5.6-tile circle for a 4.07-tile shark, which is a reflection of something he
    never is. The mean is dense where he sits at every heading and faint out at the nose
    and tail he only sometimes reaches, which after the blur is exactly the soft ellipse
    Wube ships: theirs is 194x133 px against a 114x88 px torso sprite, 1.7x its footprint.

    The canvas GROWS by the blur's own reach first. Blurring in place would push alpha into
    the canvas edge, and the packer's clipped-frames check would then correctly refuse a
    sheet that is not actually cut -- fixing that by loosening the check would blind it to
    the real thing.
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

    The render canvas is centred on the entity, but the SHARK is not -- model.offset lifts
    him and the 45-degree camera turns that lift into up-screen pixels, so his mean alpha
    sits high. Stock declares the spidertron's reflection at shift 0, i.e. on the entity
    origin, and this is what lets ours be declared the same way instead of carrying a shift
    that is really just the body's lift written down twice.
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


#: name -> a function taking (images, cfg, px_per_tile, floor) and returning
#: (images, note). Named rather than passed as a callable so a Target stays a frozen
#: dataclass of plain data that a test can build without importing Pillow.
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
    notes: list[str] = field(default_factory=list)
    source: pathlib.Path | None = None


# ------------------------------------------------------------------------- packing


def pack_target(cfg, target: Target, out_root: pathlib.Path, *, mod_name: str,
                line_length: int = DEFAULT_LINE_LENGTH, pad: int = DEFAULT_PAD,
                max_side: int = MAX_SHEET_SIDE, floor: int = SPRITE_ALPHA_FLOOR,
                preview: bool = False, explicit_dir=None, allow_clipped: bool = False,
                any_config: bool = False) -> Packed | None:
    """Frames -> sheet PNG(s) + the sprite dict. None when the target has no frames yet."""
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

    # The frames' OWN derived numbers where the sidecar has them: a render's px-per-tile
    # is a fact about those pixels, not about the config file as it stands today.
    key = PASS_PPT.get(target.pass_name, "body_px_per_tile")
    derived = (blob or {}).get("derived") or ac.derived(cfg)
    ppt = derived.get(key) or ac.derived(cfg)[key]

    images = [(i, Image.open(directory / f"frame_{i:03d}.png").convert("RGBA"))
              for i in frames]
    canvas = images[0][1].size
    odd = [i for i, img in images if img.size != canvas]
    if odd:
        raise PackError(f"{target.id}: frames {odd[:5]} are not {canvas[0]}x{canvas[1]}; "
                        f"one sheet needs one canvas")

    notes = []
    if target.draw_as_shadow:
        images = [(i, blacken(img, floor)) for i, img in images]
        notes.append(f"shadow surgery: RGB forced to black, alpha < {floor} zeroed")
    if target.reduce:
        if target.reduce not in REDUCERS:
            raise PackError(f"{target.id}: no reducer named {target.reduce!r}; known: "
                            f"{', '.join(sorted(REDUCERS))}")
        images, note = REDUCERS[target.reduce](images, cfg, ppt, floor)
        frames = [i for i, _ in images]
        canvas = images[0][1].size      # a reducer may grow the canvas; see reflection_blob
        notes.append(note)

    box, per_frame = union_box(images, floor)
    if box is None:
        raise PackError(f"{target.id}: every frame is empty at alpha >= {floor}")
    clipped = clipped_frames(per_frame, canvas)
    if clipped:
        knob = ("camera.shadow_canvas_tiles" if target.pass_name == "shadow"
                else "camera.canvas_tiles")
        message = (f"{target.id}: {len(clipped)} frame(s) touch the canvas edge "
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

    graphics = out_root / GRAPHICS_DIR
    graphics.mkdir(parents=True, exist_ok=True)
    stems = ([target.stem] if layout.file_count == 1
             else [f"{target.stem}-{n + 1}" for n in range(layout.file_count)])
    paths = [graphics / f"{stem}.png" for stem in stems]
    write_sheets([img for _, img in images], box, layout, paths)

    scale = fc.NOMINAL_PX_PER_TILE / ppt
    fields = sprite_fields(target, [f"__{mod_name}__/{GRAPHICS_DIR}/{p.name}" for p in paths],
                           layout, shift, scale)
    for path in paths:
        sheets.stamp_png(path, ac.stamp(cfg, {
            "sheet": target.id, "frames": frames, "source": str(directory),
            "sprite": fields}))
    return Packed(target=target, fields=fields, frames=frames, paths=paths, box=box,
                  layout=layout, notes=notes, source=directory)


def blacken(img, floor: int):
    """A Cycles shadow-catcher frame -> what Factorio's draw_as_shadow actually reads."""
    from PIL import Image
    alpha = img.getchannel("A").point(lambda v: v if v >= floor else 0)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.putalpha(alpha)
    return out


def write_sheets(images, box, layout, paths):
    """Crop every frame to `box` and paste it into its cell. No compositing: `paste`
    copies alpha verbatim, `alpha_composite` would blend the sprite against the sheet's
    own transparency and eat the edge ramp."""
    from PIL import Image
    per_file = layout.frames_per_file
    for index, path in enumerate(paths):
        size = layout.sheet_size(index)
        sheet = Image.new("RGBA", size, (0, 0, 0, 0))
        first = index * per_file
        for n in range(first, min(first + per_file, layout.frame_count)):
            slot = n - first
            col, row = slot % layout.line_length, slot // layout.line_length
            sheet.paste(images[n].crop(box),
                        (col * layout.frame_width, row * layout.frame_height))
        sheet.save(path)


# ------------------------------------------------------------------------ emitting


def slot_map(packed: list[Packed]) -> dict:
    """graphics_set slot -> the sprite ids in it, in layer order."""
    out: dict[str, list[str]] = {}
    for item in sorted(packed, key=lambda p: (p.target.slot, p.target.order)):
        out.setdefault(item.target.slot, []).append(item.target.id)
    return out


def clear_list(slots) -> list[str]:
    """Stock slots no sheet of ours covers. entity.lua must nil these or the stock
    spidertron's own art keeps drawing under (and beside) Jamal."""
    return [s for s in STOCK_ART_SLOTS if s not in slots]


def manifest_blob(cfg, packed: list[Packed], *, mod_name: str) -> dict:
    """The JSON the linter eats. `sprites` entries are the SAME dicts plus an `id`.

    `mod_roots` is relative to the manifest, so the tree lints in place with no flags --
    and CI's own --mod-root still wins over it (lint_sprites.specs_from_manifest only
    fills roots the CLI has not already claimed).
    """
    slots = slot_map(packed)
    return {
        "version": MANIFEST_VERSION,
        "generated_by": "tools/render/pack.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config_hash": ac.config_hash(cfg),
        "mod": mod_name,
        "mod_roots": {mod_name: ".."},
        "slots": slots,
        "clear": clear_list(slots),
        "sprites": [dict(id=p.target.id, **p.fields) for p in packed],
    }


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
            return "{" + ", ".join(lua_value(v, indent) for v in value) + "}"
        inner = indent + "  "
        body = ",\n".join(inner + lua_value(v, inner) for v in value)
        return "{\n" + body + "\n" + indent + "}"
    raise PackError(f"no Lua form for {value!r}")


def lua_table(fields: dict, indent: str = "") -> str:
    """Brace on its own line, one field per line: the shape base's own prototype files
    use, so a generated table reads like a hand-written one in a diff."""
    body = ",\n".join(f"{indent}  {key} = {lua_value(value, indent + '  ')}"
                      for key, value in fields.items())
    return indent + "{\n" + body + "\n" + indent + "}"


def lua_blob(cfg, packed: list[Packed]) -> str:
    """The generated data-stage module. Same dicts, Lua syntax, nothing added.

    Emits the sprites by id AND assembled into their graphics_set slots, sharing the same
    table references -- so `sprites.body` and `slots.animation.layers[1]` are one table in
    Lua exactly as they are one dict here. No ---@type annotations: the slot decides
    whether a table is a RotatedAnimation or a RotatedSprite, so the annotation belongs at
    the assignment in entity.lua, where a wrong one is a real finding.
    """
    slots = slot_map(packed)
    by_id = {p.target.id: p for p in packed}
    lines = [
        "-- GENERATED by tools/render/pack.py from render/jamaltron.toml. DO NOT EDIT.",
        "--",
        "-- Every number here was measured off the rendered frames: the frame box is the",
        "-- union of all %d rotations' alpha, and the shift is the distance from the render"
        % max(len(p.frames) for p in packed),
        "-- canvas's own origin pixel to the cropped frame's centre. The JSON manifest",
        "-- beside the sheets is these same tables plus an id, which is what",
        "-- tools/lint_sprites.py checks against the real PNGs.",
        "--",
        "-- config %s   packed %s" % (ac.config_hash(cfg), time.strftime("%Y-%m-%d %H:%M:%S")),
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
        '  config_hash = "%s",' % ac.config_hash(cfg),
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
    faster of the three); when none of them is present this says so and changes nothing.
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
        started = time.time()           # a file CI has to have an opinion about
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

    Same code CI runs, same --strict, so a sheet that would turn CI red turns pack.py red
    first. Importing rather than shelling out keeps the failure a Python value.
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
                   help=f"px of margin around the union alpha box (default {DEFAULT_PAD})")
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
                   help="pack frames whose alpha touches the canvas edge (they are CUT)")
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

    wanted = set(args.targets.split(",")) if args.targets else None
    targets = [t for t in TARGETS if wanted is None or t.id in wanted]
    if wanted and not targets:
        sys.stderr.write(f"pack.py: no target matches {sorted(wanted)}; known: "
                         f"{', '.join(t.id for t in TARGETS)}\n")
        return 2

    print("jamaltron pack  config %s  -> %s" % (ac.config_hash(cfg),
                                                _relative(root)))
    packed: list[Packed] = []
    try:
        for target in targets:
            item = pack_target(cfg, target, root, mod_name=mod_name,
                               line_length=args.line_length, pad=args.pad,
                               max_side=args.max_side, preview=args.preview,
                               explicit_dir=overrides.get(target.id),
                               allow_clipped=args.allow_clipped,
                               any_config=args.any_config)
            if item is None:
                continue
            packed.append(item)
            geometry = item.fields
            print("  %-10s %2d frames  %3dx%-3d  ll %-2d  shift %+.4f,%+.4f tiles "
                  "(by_pixel %+.1f,%+.1f)  %s"
                  % (target.id, len(item.frames), geometry["width"], geometry["height"],
                     geometry["line_length"], geometry["shift"][0], geometry["shift"][1],
                     geometry["shift"][0] * 32, geometry["shift"][1] * 32,
                     ", ".join("%dx%d" % item.layout.sheet_size(i)
                               for i in range(item.layout.file_count))))
            for note in item.notes:
                print("       NOTE " + note)
    except PackError as exc:
        sys.stderr.write("pack.py: %s\n" % exc)
        return 1

    if not packed:
        sys.stderr.write("pack.py: nothing packed; no target had frames\n")
        return 1

    # Two cross-target facts no single sheet can see. Neither is fatal -- a coarse sheet
    # is a legitimate thing to look at -- but both ship as a wrong-looking vehicle rather
    # than as an error, which is exactly the class of thing that needs saying out loud.
    rotating = {p.fields["direction_count"] for p in packed
                if p.target.kind == "rotations"}
    if len(rotating) > 1:
        print("  WARN the rotating sheets disagree on direction_count (%s). The body and "
              "its shadow would turn at different rates; pack them from the same render."
              % ", ".join(str(n) for n in sorted(rotating)))
    coarse = sorted(n for n in rotating if n < cfg["rotations.count"])
    if coarse:
        print("  WARN direction_count %s against rotations.count %d: this is a PREVIEW "
              "sheet, fine to look at and not fine to ship."
              % (", ".join(str(n) for n in coarse), cfg["rotations.count"]))

    graphics = root / GRAPHICS_DIR
    manifest_path = graphics / MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest_blob(cfg, packed, mod_name=mod_name),
                                        indent=2) + "\n")
    lua_path = root / PROTOTYPES_DIR / LUA_NAME
    lua_path.parent.mkdir(parents=True, exist_ok=True)
    lua_path.write_text(lua_blob(cfg, packed))

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


def _relative(path: pathlib.Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
