"""Contact sheets and the C.10 COMPARE sheet: jamaltron beside the stock spidertron.

The compare sheet is the highest-value thing in the harness. "Does he sit right on the
legs" is otherwise a question you answer by building the mod, launching Factorio,
spawning the thing and driving it in a circle. Here it is one PNG:

    row STOCK      the shipped spidertron torso at eight rotations
    row JAMALTRON  our render at the SAME eight rotations, shadow composited under it
    row OVERLAY    ours over a ghost of stock, so size and footprint are directly readable

and on every cell, the eight LEG MOUNT POINTS the entity prototype declares plus a line
out to each leg's ground position. A mount that falls off the shark's silhouette is a leg
growing out of thin air, and that is the question C.4 has to answer.

THE SHEET CHECKS ITS OWN ASSUMPTION. `mount_position` is declared with `util.by_pixel`,
which converts sprite pixels to tiles, so we read it as a SCREEN-space offset from the
entity origin rather than a world position at body height -- the two differ by a factor of
0.7071 on the vertical and the wrong one puts the markers a third of a torso off. The
STOCK row settles it by eye: draw the markers on Wube's own art, and if the interpretation
is right they land on the torso's shoulders where its legs visibly attach. If they do not,
the constant below is wrong, not the shark.

Split deliberately: everything above the Pillow import is layout arithmetic with no
image library in it, so tools/tests/test_sheets.py exercises the part most likely to be
off by half a pixel without rendering anything.
"""

from __future__ import annotations

import pathlib
import sys

# sys.path, and a TRAP that tools/README.md's two-line idiom does not cover. Python (and
# Blender) put THIS file's directory on sys.path[0], and this directory contains
# render/inspect.py -- which SHADOWS the standard library's `inspect`, so importing
# dataclasses (which imports inspect) pulls in a module that does `import bpy` and dies.
# Drop the render dir from the path entirely and put tools/ on instead; every import here
# goes through the `render.` package, so nothing needs it.
_HERE = pathlib.Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if pathlib.Path(p or ".").resolve() != _HERE]
sys.path.insert(0, str(_HERE.parent))

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


# ------------------------------------------------------------------ pure layout math


def origin_in_frame(width: int, height: int, shift_tiles, px_per_tile: float):
    """Where the ENTITY sits inside one sprite frame, in source pixels.

    A sprite's centre is drawn `shift` tiles from the entity, so the entity is at the
    frame centre MINUS the shift. Centre is pixel index (n-1)/2, not n/2 -- pixel k
    covers [k, k+1), so the continuous centre of 138 pixels falls on the seam between
    68 and 69. Half a pixel of bias here is half a pixel of misalignment on every cell
    of the compare sheet, which is exactly the size of error you would then chase in
    the render.
    """
    return (fc.origin_pixel(width) - shift_tiles[0] * px_per_tile,
            fc.origin_pixel(height) - shift_tiles[1] * px_per_tile)


def frame_box(index: int, width: int, height: int, line_length: int):
    """Crop box of frame `index` in a sheet packed left-to-right, top-to-bottom."""
    col, row = index % line_length, index // line_length
    return (col * width, row * height, (col + 1) * width, (row + 1) * height)


def cell_anchor(cell_px: int, origin_y: float = 0.5):
    """Where the entity origin sits inside a compare cell, in pixels.

    Horizontally centred; vertically anchored at `origin_y` of the cell. The bias is not
    decoration -- the shark is lifted 1.5 tiles by `model.offset`, so on screen he sits
    about a tile ABOVE the entity position and a cell centred on the origin cuts his nose
    off. Factorio does exactly this to its own frames: the stock torso is 138 px tall with
    the entity at pixel 106, i.e. 77% of the way down.
    """
    return (fc.origin_pixel(cell_px), (cell_px - 1) * origin_y)


def centred_crop(origin_xy, cell_px: int, origin_y: float = 0.5):
    """Crop box that lands `origin_xy` on this cell's anchor.

    Returns (box, residual). The box is integral because Pillow crops on integers; the
    residual is the sub-pixel remainder, reported rather than hidden so a caller judging
    alignment knows the floor is +-0.5 px and not zero.
    """
    ax, ay = cell_anchor(cell_px, origin_y)
    x0, y0 = round(origin_xy[0] - ax), round(origin_xy[1] - ay)
    residual = (origin_xy[0] - ax - x0, origin_xy[1] - ay - y0)
    return (x0, y0, x0 + cell_px, y0 + cell_px), residual


def mount_markers(px_per_tile: float):
    """The eight leg mounts as (mount_px, ground_px) offsets from the entity origin.

    Mount is a screen offset: straight multiply. Ground is a world position on the
    ground plane, so it goes through the camera -- and its north-south foreshortens by
    0.7071 while its east-west does not, which is why the stance reads as an ellipse
    rather than a circle.
    """
    out = []
    for (mx, my), (gx, gy) in LEG_MOUNTS:
        mount = (mx * px_per_tile, my * px_per_tile)
        # fc.project takes (east, north, up); a ground position's y is SOUTH.
        ground = fc.project(gx, -gy, 0.0, scale=fc.NOMINAL_PX_PER_TILE / px_per_tile)
        out.append((mount, ground))
    return out


def mount_extents(px_per_tile: float):
    """(half_width_px, north_px, south_px) the mounts span. What the shark must cover."""
    xs = [m[0] * px_per_tile for (m, _) in LEG_MOUNTS]
    ys = [m[1] * px_per_tile for (m, _) in LEG_MOUNTS]
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


def contact_grid(n: int, max_cols: int = 8) -> tuple[int, int]:
    """Rows and columns for a plain contact sheet of `n` frames.

    8 columns mirrors the stock spidertron sheet's own line_length, so a 64-frame
    contact sheet is laid out exactly like the sheet C.7 will emit and the two can be
    eyeballed against each other.
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

    The stock sheet's own pixel scale is 32/scale px per tile; if the cell is being
    rendered at a different px_per_tile the frame is resampled so both rows of the
    compare sheet are at ONE scale. Without that the comparison is meaningless.
    """
    src = Image.open(spec["path"]).convert("RGBA")
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


def load_render_frame(path, cell_px: int, render_ppt: float, px_per_tile: float,
                      origin_y: float = 0.5):
    """One of our own renders, cropped to a cell. Our canvas is centred on the origin
    by construction, so the entity is at pixel index (res-1)/2 in both axes."""
    img = Image.open(path).convert("RGBA")
    origin = (fc.origin_pixel(img.width), fc.origin_pixel(img.height))
    if abs(render_ppt - px_per_tile) > 1e-6:
        k = px_per_tile / render_ppt
        img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))),
                         Image.LANCZOS)
        origin = (origin[0] * k, origin[1] * k)
    box, _ = centred_crop(origin, cell_px, origin_y)
    return img.crop(box)


def shadow_layer(img, strength: float = 0.55):
    """A Cycles shadow-catcher render -> a black layer whose alpha IS the shadow.

    Factorio draws shadow sprites as a darkening multiply; on a compare sheet plain
    black at partial alpha reads the same and needs no blend mode.
    """
    alpha = img.getchannel("A").point(lambda v: int(v * strength))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.putalpha(alpha)
    return out


def cell_background(cell_px: int, rgb, px_per_tile: float, grid: bool,
                    origin_y: float = 0.5):
    """Flat ground with an optional one-tile grid, anchored on the entity origin.

    The horizontal lines are one tile of GROUND DEPTH apart, so they foreshorten by
    0.7071 while the vertical ones do not. That asymmetry is the 45-degree camera made
    visible, and it is the ruler you measure the shark against.
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
                mount_rgb=(255, 64, 190), leg_rgb=(255, 205, 70)):
    """Leg mounts as crosses, plus each leg as a faint line to its ground position.

    Drawn on an overlay and composited, so the markers sit at a fixed opacity instead
    of being punched through whatever the cell already had -- ImageDraw writes RGBA
    straight into the buffer and ignores the alpha you asked for.
    """
    over = Image.new("RGBA", cell.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    ax, ay = cell_anchor(cell.width, origin_y)
    for mount, ground in mount_markers(px_per_tile):
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
    gets it back. A sheet that has been copied out of render-out/ and emailed around
    still knows which knobs made it, which is the whole point of provenance.
    """
    import json
    img = Image.open(path)
    meta = PngInfo()
    meta.add_text("jamaltron:config_hash", blob["config_hash"])
    meta.add_text("jamaltron:pass_hashes", json.dumps(blob["pass_hashes"]))
    meta.add_text("jamaltron:config", json.dumps(blob["config"], sort_keys=True))
    meta.add_text("jamaltron:derived", json.dumps(blob["derived"], sort_keys=True))
    img.save(path, pnginfo=meta)


def draw_footer(canvas, layout: GridLayout, lines):
    d = ImageDraw.Draw(canvas)
    f = _font(12)
    x, y = layout.footer_origin()
    for i, line in enumerate(lines):
        d.text((x, y + i * 13), line, font=f, fill=(150, 156, 162, 255))
    return canvas
