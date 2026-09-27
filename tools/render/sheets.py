"""Contact sheets and the C.10 COMPARE sheet: jamaltron beside the stock spidertron.

The compare sheet is the highest-value thing in the harness. "Does he sit right on the
legs" otherwise means building the mod, launching Factorio, spawning him and driving him in
a circle. Here it is one PNG:

    row STOCK      the shipped spidertron: base plate, then rotating torso, eight rotations
    row JAMALTRON  our render at the SAME eight rotations, shadow composited under it
    row OVERLAY    ours over a ghost of stock, so size and footprint are directly readable

and on every cell, the eight LEG MOUNT POINTS the entity prototype declares plus a line
out to each leg's ground position. A mount off the shark's silhouette is a leg growing out
of thin air -- the question C.4 has to answer.

THE STOCK ROW IS TWO LAYERS AND THE UNDER ONE IS THE POINT. spidertron-animations.lua
declares `base_animation` (spidertron-body-bottom.png, 126x106, direction_count = 1)
beneath the rotating `animation` (spidertron-body.png, 132x138, direction_count = 64). The
plate does NOT turn, and it is what the legs attach to: all eight mounts land on opaque
plate pixels, each within 0.71 px of a fully opaque one (the half-pixel sampling floor, not
a miss). On the ROTATING torso, 230 of the 512 mount samples (8 mounts x 64 frames) land on
TRANSPARENT pixels, because the torso is narrower than the leg spread. Omit the plate and
the sheet asks the shark to cover ground the stock torso does not cover either, silently
oversizing him -- and sizing is what this sheet decides.

THE SHEET CHECKS ITS OWN ASSUMPTION, AND --compare PRINTS THE RESULT. `mount_position` is
declared with `util.by_pixel` (sprite pixels to tiles), so we read it as a SCREEN-space
offset from the entity origin, not a world position at body height -- the two differ by
0.7071 on the vertical, and the wrong one puts the markers a third of a torso off.
`mount_selfcheck()` samples the base plate's own alpha at all eight marker positions: 8 of 8
on opaque plate means the by_pixel reading is right, fewer means the reading is wrong (not
the shark). The count goes in the footer and the sidecar, so every sheet carries it.

Everything above the Pillow import is image-library-free layout arithmetic, so
tools/tests/test_art_harness.py exercises the part most likely to be off by half a pixel
without rendering anything.
"""

from __future__ import annotations

import pathlib
import sys

# sys.path, verbatim per tools/README.md -- Python and Blender both put THIS file's own
# directory on sys.path[0], never tools/, and `package = false` means there is no installed
# `render` to fall back on.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from dataclasses import dataclass  # noqa: E402

from render import factorio_camera as fc  # noqa: E402

FACTORIO_DATA = "/Applications/factorio.app/Contents/data/"
STOCK_TORSO = FACTORIO_DATA + "base/graphics/entity/spidertron/torso/"

#: The stock sprites we compare against, straight out of spidertron-animations.lua.
#: `shift` is in TILES (util.by_pixel(x, y) == {x/32, y/32}).
STOCK_BODY = dict(path=STOCK_TORSO + "spidertron-body.png", width=132, height=138,
                  line_length=8, direction_count=64, scale=0.5, shift=(0 / 32, -19 / 32))
STOCK_SHADOW = dict(path=STOCK_TORSO + "spidertron-body-shadow.png", width=192, height=94,
                    line_length=8, direction_count=64, scale=0.5, shift=(26 / 32, 0.5 / 32))
#: `base_animation`, the NON-ROTATING under-plate beneath the torso and the layer the eight
#: leg mounts land on. One frame (direction_count = 1), so every rotation of the compare
#: sheet shows the same plate -- see the module docstring.
STOCK_BASE = dict(path=STOCK_TORSO + "spidertron-body-bottom.png", width=126, height=106,
                  line_length=1, direction_count=1, scale=0.5, shift=(0 / 32, 0 / 32))

#: base/prototypes/entity/entities.lua, create_spidertron, scale = leg_scale = 1.
#: mount is a screen offset in tiles; ground is a world position in tiles (east, south).
LEG_MOUNTS = [
    ((15 / 32, -22 / 32), (2.25, -2.5)),
    ((23 / 32, -10 / 32), (3.0, -1.0)),
    ((25 / 32, 4 / 32), (3.0, 1.0)),
    ((15 / 32, 17 / 32), (2.25, 2.5)),
    ((-15 / 32, -22 / 32), (-2.25, -2.5)),
    ((-23 / 32, -10 / 32), (-3.0, -1.0)),
    ((-25 / 32, 4 / 32), (-3.0, 1.0)),
    ((-15 / 32, 17 / 32), (-2.25, 2.5)),
]

#: base/prototypes/entity/entities.lua: body_height = 1.5 * scale * leg_scale.
STOCK_BODY_HEIGHT_TILES = 1.5

#: Alpha a pixel needs before A LEG MAY STAND ON IT. Deliberately NOT
#: art.SPRITE_VISIBLE_ALPHA, because the question differs: "is there body under this mount"
#: is a POINT SAMPLE of something a leg hangs from, while "how big is he" is an EXTENT and
#: must keep every pixel the engine draws. An alpha-2 antialiasing whisker under a mount is
#: a leg hanging in the air, so counting it would be a tolerance pointing the wrong way.
#: 8 is what stock's own plate was validated at: 8 of 8 markers on opaque base_animation,
#: every gap inside the 0.71 px sampling floor.
MOUNT_OPAQUE_ALPHA = 8

#: Where the SHIPPED mount ratio lives. C.13 moved Jamal's mounts inboard (he is in a
#: harness, not a chassis), so stock's eight markers are not the eight this mod draws. The
#: prototype is the source of truth; this reads it instead of copying the number, because a
#: second copy of a ratio drifts.
MOUNT_SHRINK_LUA = pathlib.Path(__file__).resolve().parents[2] / "mod" / "jamaltron" \
    / "prototypes" / "shared.lua"


def _shared_number(name: str, default: float) -> float:
    """A number out of shared.lua, or `default` when the prototype is unreadable.

    Never fatal: this module must work with the mod tree missing (tests that build their
    own fixtures import it), and a missing number degrades to stock's ring instead of
    blocking a look at the shark.
    """
    import re
    try:
        text = MOUNT_SHRINK_LUA.read_text()
    except OSError:
        return default
    found = re.search(r"^\s*%s\s*=\s*(-?[0-9.]+)" % re.escape(name), text, re.M)
    return float(found.group(1)) if found else default


def mount_shrink(default: float = 1.0) -> float:
    """The mod's own `mount_shrink` (C.13), or `default` when it cannot be read."""
    return _shared_number("mount_shrink", default)


def mount_lift(default: float = 0.0) -> float:
    """The mod's own `mount_lift` (C.27): tiles of screen offset every mount moves UP after
    the shrink, because ground contact drew the standing body that much higher. Zero
    (stock's ring at stock's height) when it cannot be read."""
    return _shared_number("mount_lift", default)


# ------------------------------------------------------------------ pure layout math


def origin_in_frame(width: int, height: int, shift_tiles, px_per_tile: float):
    """Where the ENTITY sits inside one sprite frame, in source pixels.

    A sprite's centre is drawn `shift` tiles from the entity, so the entity is at the
    frame centre MINUS the shift. Centre is pixel index (n-1)/2, not n/2 -- pixel k
    covers [k, k+1), so the continuous centre of 138 pixels falls between 68 and 69. Half
    a pixel of bias here misaligns every cell of the compare sheet by the same half pixel
    you would then chase in the render.
    """
    return (fc.origin_pixel(width) - shift_tiles[0] * px_per_tile,
            fc.origin_pixel(height) - shift_tiles[1] * px_per_tile)


def frame_box(index: int, width: int, height: int, line_length: int):
    """Crop box of frame `index` in a sheet packed left-to-right, top-to-bottom."""
    col, row = index % line_length, index // line_length
    return (col * width, row * height, (col + 1) * width, (row + 1) * height)


def cell_anchor(cell_px: int, origin_y: float = 0.5):
    """Where the entity origin sits inside a compare cell, in pixels.

    Horizontally centred; vertically anchored at `origin_y` of the cell. `model.offset`
    lifts the shark 0.5 tiles of world height (0.5 * 0.7071 = 0.35 tiles up-screen), so he
    sits high in his canvas and a cell centred on the origin wastes its bottom half.
    MEASURED on the shipped knobs, union of all 64 rotations: the rendered body reaches
    2.68 tiles above the origin and 1.81 below, so the honest split is 0.60. Factorio
    biases its own frames the same way (the stock torso is 138 px tall with the entity at
    pixel 106, 77% down), but that is STOCK's ratio; on a shark this long it made a
    4.6-tile cell slice 50 px off his tail.
    """
    return (fc.origin_pixel(cell_px), (cell_px - 1) * origin_y)


def centred_crop(origin_xy, cell_px: int, origin_y: float = 0.5):
    """Crop box that lands `origin_xy` on this cell's anchor.

    Returns (box, residual). The box is integral (Pillow crops on integers); the residual
    is the sub-pixel remainder, reported so a caller judging alignment knows the floor is
    +-0.5 px, not zero.
    """
    ax, ay = cell_anchor(cell_px, origin_y)
    x0, y0 = round(origin_xy[0] - ax), round(origin_xy[1] - ay)
    residual = (origin_xy[0] - ax - x0, origin_xy[1] - ay - y0)
    return (x0, y0, x0 + cell_px, y0 + cell_px), residual


def crop_loss(sprite_box, cell_box):
    """px of sprite that `cell_box` cuts off each edge: (left, top, right, bottom).

    `sprite_box` is a Pillow alpha bbox (right/bottom exclusive) in the same pixel space
    the crop box is stated in. All zeros means the cell holds the whole sprite.
    """
    if sprite_box is None:
        return (0, 0, 0, 0)
    x0, y0, x1, y1 = cell_box
    return (max(0, x0 - sprite_box[0]), max(0, y0 - sprite_box[1]),
            max(0, sprite_box[2] - x1), max(0, sprite_box[3] - y1))


def cell_tiles_needed(sprite_box, origin_xy, cell_px_per_tile: float,
                      origin_y: float = 0.5) -> float:
    """Smallest square cell, IN TILES, that holds `sprite_box` at this anchor.

    The four constraints are the four edges, and the vertical pair depends on `origin_y`:
    the anchor sits (cell-1) * origin_y down the cell, with origin_y of the cell above it
    and 1 - origin_y below. A bias that suits one render clips the next -- the shipped
    4.6-tile cell cut 32 px off each side and 50 off the bottom of a shark nobody had
    re-measured it against.
    """
    if sprite_box is None:
        return 0.0
    ox, oy = origin_xy
    oyf = min(max(origin_y, 1e-6), 1 - 1e-6)
    need = max(2 * (ox - sprite_box[0]) + 1,
               2 * (sprite_box[2] - ox) + 1,
               (oy - sprite_box[1]) / oyf + 1,
               (sprite_box[3] - oy) / (1 - oyf) + 1)
    return max(0.0, need / cell_px_per_tile)


def mount_markers(px_per_tile: float, shrink: float = 1.0, lift: float = 0.0):
    """The eight leg mounts as (mount_px, ground_px) offsets from the entity origin.

    Mount is a screen offset: straight multiply. Ground is a world position on the ground
    plane, so it goes through the camera: north-south foreshortens by 0.7071 and east-west
    does not, so the stance reads as an ellipse.

    `shrink` scales the MOUNTS ONLY, exactly as entity.lua does. Ground positions are
    untouched there (shrinking the feet too gives a mincing stance instead of the
    splayed-from-a-harness look), so they are untouched here and the drawn legs splay the
    way the shipped ones do.

    `lift` moves the MOUNTS up-screen by that many tiles, after the shrink, exactly as
    entity.lua does (C.27). Feet again untouched: the legs just get that much longer.
    """
    out = []
    for (mx, my), (gx, gy) in LEG_MOUNTS:
        mount = (mx * shrink * px_per_tile, (my * shrink - lift) * px_per_tile)
        # fc.project takes (east, north, up); a ground position's y is SOUTH.
        ground = fc.project(gx, -gy, 0.0, scale=fc.NOMINAL_PX_PER_TILE / px_per_tile)
        out.append((mount, ground))
    return out


def mount_extents(px_per_tile: float, shrink: float = 1.0, lift: float = 0.0):
    """(half_width_px, north_px, south_px) the mounts span. What the shark must cover."""
    xs = [m[0] * shrink * px_per_tile for (m, _) in LEG_MOUNTS]
    ys = [(m[1] * shrink - lift) * px_per_tile for (m, _) in LEG_MOUNTS]
    return (max(abs(x) for x in xs), min(ys), max(ys))


@dataclass(frozen=True)
class GridLayout:
    """Geometry of a labelled grid of square cells. Pure arithmetic, unit-tested."""

    cols: int
    rows: int
    cell: int
    gutter: int = 6
    left: int = 78      # row-label gutter
    top: int = 26       # column-label strip
    bottom: int = 34    # provenance footer
    right: int = 8

    @property
    def width(self) -> int:
        return self.left + self.cols * self.cell + (self.cols - 1) * self.gutter + self.right

    @property
    def height(self) -> int:
        return self.top + self.rows * self.cell + (self.rows - 1) * self.gutter + self.bottom

    def cell_origin(self, col: int, row: int):
        if not (0 <= col < self.cols and 0 <= row < self.rows):
            raise IndexError(f"cell ({col},{row}) outside {self.cols}x{self.rows}")
        return (self.left + col * (self.cell + self.gutter),
                self.top + row * (self.cell + self.gutter))

    def footer_origin(self):
        return (self.left, self.height - self.bottom + 6)


#: Baseline-to-baseline pixels between footer lines, matching draw_footer()'s 12 px font.
FOOTER_LEADING = 13


def footer_height(n_lines: int, leading: int = FOOTER_LEADING, pad: int = 6) -> int:
    """Bottom strip tall enough to actually SHOW `n_lines` of footer.

    GridLayout's default 34 fits exactly two, and the compare sheet draws three -- the third
    (the leg-mount footprint, the one number answering "how big is he") rendered two pixels
    tall off the bottom edge. Size the strip from the lines.
    """
    if n_lines < 0:
        raise ValueError(f"n_lines must be >= 0, got {n_lines}")
    return pad + n_lines * leading + pad


def contact_grid(n: int, max_cols: int = 8) -> tuple[int, int]:
    """Rows and columns for a plain contact sheet of `n` frames.

    8 columns mirrors the stock spidertron sheet's line_length, so a 64-frame contact
    sheet is laid out like the sheet C.7 emits and the two can be eyeballed side by side.
    """
    if n < 1:
        raise ValueError(f"need at least one frame, got {n}")
    cols = min(n, max_cols)
    rows = -(-n // cols)
    return cols, rows


# -------------------------------------------------------------------------- Pillow side

try:
    from PIL import Image, ImageDraw, ImageFont
    from PIL.PngImagePlugin import PngInfo
except ImportError:                                   # Blender side has no Pillow
    Image = ImageDraw = ImageFont = PngInfo = None


def _font(size=13):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                  # Pillow < 10.1: bitmap default
        return ImageFont.load_default()


def load_sheet_frame(spec: dict, index: int, cell_px: int, px_per_tile: float,
                     origin_y: float = 0.5):
    """One frame of a stock sprite sheet, cropped to a cell centred on the entity.

    The stock sheet's pixel scale is 32/scale px per tile; a cell at a different
    px_per_tile gets the frame resampled, so both rows of the compare sheet share ONE
    scale (without that the comparison is meaningless).
    """
    src = Image.open(spec["path"]).convert("RGBA")
    # A direction_count = 1 layer (base_animation) has one frame; frame 24 of it would crop
    # 24 rows past the bottom of a 106 px file and return transparency.
    if spec.get("direction_count", 1) <= 1:
        index = 0
    frame = src.crop(frame_box(index, spec["width"], spec["height"], spec["line_length"]))
    native_ppt = fc.px_per_tile(spec["scale"])
    origin = origin_in_frame(spec["width"], spec["height"], spec["shift"], native_ppt)
    if abs(native_ppt - px_per_tile) > 1e-6:
        k = px_per_tile / native_ppt
        frame = frame.resize((max(1, round(frame.width * k)), max(1, round(frame.height * k))),
                             Image.LANCZOS)
        origin = (origin[0] * k, origin[1] * k)
    box, _ = centred_crop(origin, cell_px, origin_y)
    return frame.crop(box)


def mount_selfcheck(spec: dict | None = None, alpha_threshold: int = MOUNT_OPAQUE_ALPHA,
                    search_px: int = 6) -> dict:
    """Do the mount markers land on the stock layer the legs attach to? Measured, not eyed.

    `spec` defaults to STOCK_BASE (`base_animation`, the non-rotating under-plate), NOT the
    rotating torso: 230 of the torso's 512 mount samples are transparent, a fact about
    Wube's art, not a bug here (see the module docstring).

    Reports each marker's alpha plus the distance to the nearest fully opaque pixel: by the
    (n-1)/2 origin convention a marker lands on a .5/.5 subpixel position and can never get
    closer than 0.71 px to a pixel centre, which is the sampling grid, not a miss.

    `ran` is False when Factorio is not installed. A diagnostic that travels with the
    sheet, never a gate -- a missing game must not block a look at the shark.
    """
    import math
    spec = spec or STOCK_BASE
    out = {"ran": False, "layer": pathlib.Path(spec["path"]).name,
           "alpha_threshold": alpha_threshold, "total": len(LEG_MOUNTS),
           "on_layer": 0, "worst_gap_px": None, "ok": False, "samples": [], "why": ""}
    if Image is None:
        out["why"] = "Pillow not importable on this side of the Blender boundary"
        return out
    if not pathlib.Path(spec["path"]).exists():
        out["why"] = "Factorio art not found at " + spec["path"]
        return out

    frame = load_sheet_frame_raw(spec)
    alpha = frame.getchannel("A").load()
    native_ppt = fc.px_per_tile(spec["scale"])
    ox, oy = origin_in_frame(spec["width"], spec["height"], spec["shift"], native_ppt)
    for i, ((mx, my), _) in enumerate(LEG_MOUNTS):
        px, py = ox + mx * native_ppt, oy + my * native_ppt
        ix, iy = int(round(px)), int(round(py))
        inside = 0 <= ix < frame.width and 0 <= iy < frame.height
        a = alpha[ix, iy] if inside else 0
        gap = None
        for yy in range(max(0, iy - search_px), min(frame.height, iy + search_px + 1)):
            for xx in range(max(0, ix - search_px), min(frame.width, ix + search_px + 1)):
                if alpha[xx, yy] >= 255:
                    d = math.hypot(xx - px, yy - py)
                    gap = d if gap is None else min(gap, d)
        out["samples"].append({"index": i, "px": (round(px, 2), round(py, 2)),
                               "alpha": a, "inside_frame": inside,
                               "gap_px": None if gap is None else round(gap, 3)})
        if a >= alpha_threshold:
            out["on_layer"] += 1
    gaps = [s["gap_px"] for s in out["samples"] if s["gap_px"] is not None]
    out["ran"] = True
    out["worst_gap_px"] = max(gaps) if len(gaps) == out["total"] else None
    out["ok"] = out["on_layer"] == out["total"]
    return out


def load_sheet_frame_raw(spec: dict, index: int = 0):
    """One frame of a stock sheet at its NATIVE scale, uncropped and unresampled."""
    src = Image.open(spec["path"]).convert("RGBA")
    if spec.get("direction_count", 1) <= 1:
        index = 0
    return src.crop(frame_box(index, spec["width"], spec["height"], spec["line_length"]))


def selfcheck_line(res: dict) -> str:
    """The self-check as one line, for stdout and for the sheet's own footer."""
    if not res["ran"]:
        return "mount self-check SKIPPED: %s" % res["why"]
    gap = "n/a" if res["worst_gap_px"] is None else "%.2f px" % res["worst_gap_px"]
    return ("mount self-check %s: %d/%d markers on opaque %s (alpha>=%d), worst gap to a "
            "fully opaque pixel %s (0.71 px is the subpixel floor)"
            % ("PASS" if res["ok"] else "FAIL", res["on_layer"], res["total"],
               res["layer"], res["alpha_threshold"], gap))


def mount_coverage(frame, px_per_tile: float, origin_y: float = 0.5,
                   alpha_threshold: int = MOUNT_OPAQUE_ALPHA, shrink: float = 1.0,
                   lift: float = 0.0) -> int:
    """How many of the eight leg mounts land on opaque pixels of OUR shark.

    mount_selfcheck() for the other row. Stock answers "do the mounts land on something"
    with base_animation, a plate that never turns; we ship no plate, so either the shark's
    own silhouette covers them or C.4 draws one -- the sizing decision this sheet exists to
    make. Stock's 8/8 alone reads as reassurance for a row nobody is deciding about.

    `frame` is one body render already cropped to a cell, so the cell anchor IS the entity
    origin. Eight point samples, no antialiasing allowance: a mount one pixel off the fin
    is a leg hanging in the air either way, and a marker that needs a tolerance to count is
    one to look at, not round up.
    """
    alpha = frame.getchannel("A").load()
    ax, ay = cell_anchor(frame.width, origin_y)
    on = 0
    for (mx, my), _ in mount_markers(px_per_tile, shrink, lift):
        ix, iy = int(round(ax + mx)), int(round(ay + my))
        if 0 <= ix < frame.width and 0 <= iy < frame.height:
            on += alpha[ix, iy] >= alpha_threshold
    return on


def coverage_line(samples, total: int = len(LEG_MOUNTS)) -> str:
    """The shark's own mount coverage as one line, for stdout, the footer and the sidecar.

    `samples` is [(label, count), ...], one per rendered rotation. Reports the WORST
    rotation as well as the total: a leg that floats at one heading floats in the game, and
    an average hides that frame.

    The tail of the line is the C.4 verdict: a full house means `base_animation` can stay
    empty; anything less means a leg hangs in the air somewhere, and stock's answer to that
    was to draw a plate.
    """
    if not samples:
        return "shark mount coverage: no frames"
    got = sum(c for _, c in samples)
    want = total * len(samples)
    worst = min(samples, key=lambda s: s[1])
    best = max(samples, key=lambda s: s[1])
    verdict = ("FULL HOUSE, so base_animation stays empty" if got == want else
               "the gap is what a base_animation plate would have to cover")
    return ("shark covers %d/%d mount samples over %d rotations (worst %d/%d at %s, "
            "best %d/%d at %s); %s"
            % (got, want, len(samples), worst[1], total, worst[0],
               best[1], total, best[0], verdict))


def load_render_frame(path, cell_px: int, render_ppt: float, px_per_tile: float,
                      origin_y: float = 0.5):
    """One of our own renders, cropped to a cell. Our canvas is centred on the origin
    by construction, so the entity is at pixel index (res-1)/2 in both axes.

    The crop alone, no alpha threshold: a caller that does not want the measurement must
    not have to invent a number to get the picture.
    """
    img, origin = _to_cell_scale(path, render_ppt, px_per_tile)
    box, _ = centred_crop(origin, cell_px, origin_y)
    return img.crop(box)


def render_frame_cell(path, cell_px: int, render_ppt: float, px_per_tile: float,
                      origin_y: float, alpha_threshold: int):
    """The same crop, plus WHAT IT THREW AWAY: (cell, cut, tiles_needed).

    The render pass shouts when a frame runs out of RENDER canvas (art.warn_if_clipped).
    A cell crop running out is more dangerous: size and pivot decisions are made against
    it, it looks like deliberately tight framing, and being wrong costs no Blender time.
    So it is measured here, every cell.

    `alpha_threshold` HAS NO DEFAULT on purpose. This asks the packer's question (did a
    crop cut the sprite), and a default would be a second opinion on what counts as sprite,
    one import away from art.SPRITE_VISIBLE_ALPHA and free to drift from it. Two thresholds
    quietly disagreeing is how C.4 shipped a clipped tail fin, so every caller names its
    question: art.pass_alpha_floor(pass) for a raw render (the shadow pass carries noise
    the others do not), SPRITE_VISIBLE_ALPHA otherwise.
    """
    img, origin = _to_cell_scale(path, render_ppt, px_per_tile)
    box, _ = centred_crop(origin, cell_px, origin_y)
    sprite = img.getchannel("A").point(
        lambda v: 255 if v >= alpha_threshold else 0).getbbox()
    return (img.crop(box), crop_loss(sprite, box),
            cell_tiles_needed(sprite, origin, px_per_tile, origin_y))


def _to_cell_scale(path, render_ppt: float, px_per_tile: float):
    """A render resampled to the sheet's px-per-tile, entity origin moved with it. Shared
    so the crop and its measurement cannot resample differently."""
    img = Image.open(path).convert("RGBA")
    origin = (fc.origin_pixel(img.width), fc.origin_pixel(img.height))
    if abs(render_ppt - px_per_tile) > 1e-6:
        k = px_per_tile / render_ppt
        img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))),
                         Image.LANCZOS)
        origin = (origin[0] * k, origin[1] * k)
    return img, origin


def shadow_layer(img, strength: float = 0.55):
    """A Cycles shadow-catcher render -> a black layer whose alpha IS the shadow.

    Factorio draws shadow sprites as a darkening multiply; on a compare sheet plain black
    at partial alpha reads the same with no blend mode.
    """
    alpha = img.getchannel("A").point(lambda v: int(v * strength))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.putalpha(alpha)
    return out


def cell_background(cell_px: int, rgb, px_per_tile: float, grid: bool,
                    origin_y: float = 0.5):
    """Flat ground with an optional one-tile grid, anchored on the entity origin.

    The horizontal lines are one tile of GROUND DEPTH apart, so they foreshorten by 0.7071
    while the vertical ones do not (the 45-degree camera made visible) -- the ruler to
    measure the shark against.
    """
    bg = Image.new("RGBA", (cell_px, cell_px), tuple(rgb) + (255,))
    if not grid:
        return bg
    d = ImageDraw.Draw(bg)
    ax, ay = cell_anchor(cell_px, origin_y)
    line = tuple(min(255, v + 14) for v in rgb) + (255,)
    axis = tuple(min(255, v + 30) for v in rgb) + (255,)
    n = int(cell_px / (px_per_tile * fc.K)) + 2
    for i in range(-n, n + 1):
        x = ax + i * px_per_tile
        y = ay + i * px_per_tile * fc.K
        d.line([(x, 0), (x, cell_px)], fill=axis if i == 0 else line)
        d.line([(0, y), (cell_px, y)], fill=axis if i == 0 else line)
    return bg


def draw_mounts(cell, px_per_tile: float, show_legs: bool, origin_y: float = 0.5,
                mount_rgb=(255, 64, 190), leg_rgb=(255, 205, 70), shrink: float = 1.0,
                lift: float = 0.0):
    """Leg mounts as crosses, plus each leg as a faint line to its ground position.

    Drawn on an overlay and composited, so the markers sit at a fixed opacity instead of
    punching through the cell -- ImageDraw writes RGBA straight into the buffer and
    ignores the requested alpha.
    """
    over = Image.new("RGBA", cell.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    ax, ay = cell_anchor(cell.width, origin_y)
    for mount, ground in mount_markers(px_per_tile, shrink, lift):
        mx, my = ax + mount[0], ay + mount[1]
        if show_legs:
            gx, gy = ax + ground[0], ay + ground[1]
            d.line([(mx, my), (gx, gy)], fill=leg_rgb + (70,), width=1)
            if 0 <= gx < cell.width and 0 <= gy < cell.height:
                d.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], outline=leg_rgb + (150,))
        r = 5
        d.line([(mx - r, my), (mx + r, my)], fill=mount_rgb + (235,), width=1)
        d.line([(mx, my - r), (mx, my + r)], fill=mount_rgb + (235,), width=1)
        d.ellipse([mx - 2, my - 2, mx + 2, my + 2], outline=mount_rgb + (235,))
    cell.alpha_composite(over)
    return cell


def stamp_png(path, blob: dict):
    """Write the config hash and the resolved knobs INTO the PNG.

    `exiftool -PNG:all` or `python -c "from PIL import Image; print(Image.open(p).text)"`
    gets it back, so a sheet copied out of render-out/ and emailed around still knows
    which knobs made it.

    A C.21 SEQUENCE sheet has no one config behind it, so its blob carries a `sequence`
    chunk (the base knobs, every beat, every frame's config hash, the play order) and its
    `config_hash` is the sequence digest (the id its manifest and Lua carry), not one
    frame's knobs.
    """
    import json
    img = Image.open(path)
    meta = PngInfo()
    meta.add_text("jamaltron:config_hash", blob["config_hash"])
    for key in ("pass_hashes", "config", "derived", "sequence"):
        if key in blob:
            meta.add_text("jamaltron:" + key, json.dumps(blob[key], sort_keys=True))
    img.save(path, pnginfo=meta)


def draw_footer(canvas, layout: GridLayout, lines):
    d = ImageDraw.Draw(canvas)
    f = _font(12)
    x, y = layout.footer_origin()
    for i, line in enumerate(lines):
        d.text((x, y + i * 13), line, font=f, fill=(150, 156, 162, 255))
    return canvas
