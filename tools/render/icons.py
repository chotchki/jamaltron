#!/usr/bin/env python3
"""PLAN C.6 icon CANDIDATES: every icon the mod needs, rendered from the real model.

    uv run --directory tools python render/icons.py                 # all candidates + sheets
    uv run --directory tools python render/icons.py --only beached  # one candidate
    uv run --directory tools python render/icons.py --preview       # 16 samples, fast look
    uv run --directory tools python render/icons.py --promote portrait  # ship the picked one

Renders write to render-out/review/icons/ (gitignored) and NOTHING ELSE. chotchki picks the
look before any of it goes near mod/jamaltron/graphics/, which carries the licence carve-out.
`--promote NAME` is the one step that writes into the mod, and it renders NOTHING: it lints
the candidate --strict where it sits, refuses a --preview render (the candidate's icons.json
records its samples), copies the files byte for byte (what was reviewed is what ships) to
the paths the prototypes name (SHIPPED) and writes graphics/icons.json, the manifest CI's
sprite gate and test_icon_coverage.py read.

WHAT EACH CANDIDATE PRODUCES, one directory apiece, shaped like base's spidertron:

  icon.png                120x64   64px item icon, 4 mipmap levels (64+32+16+8 side by side,
                                   top-aligned), exactly __base__/graphics/icons/spidertron.png's
                                   layout. Harness tinted Factorio's default player orange.
  icon-tintable.png       120x64   the same, harness untinted - item.lua's icon_tintable
  icon-tintable-mask.png  120x64   the harness alone, grey - icon_tintable_mask
  technology.png          480x256  256px tech icon, 4 levels (256+128+64+32), as base ships it
  minimap.png             128x128  flat silhouette, white fill, red rim - base's spidertron-map.png
                                   style, measured: RGBA (255,255,255) body, (255,0,0) outline
  minimap-selected.png    128x128  same silhouette, (141,127,122) rim - spidertron-map-selected.png
  thumbnail.png           144x144  the mod-list / portal image; base's is 144x144 too
  icons.json                       a lint_sprites.py icon manifest describing the above, so
                                   `python3 tools/lint_sprites.py --strict .../icons.json` gates
                                   them exactly as CI will gate the chosen set (PLAN C.15)

Every pixel comes out of art.render_pass (same model, cache and knobs as the sprite sheets)
at `render.resolution_px` ICON_RES, cropped and Lanczos-downsampled with premultiplied alpha
(no dark fringe off the transparent black). Each mip level is resampled from the full-res
crop, never from the level above it.

THE LEGS. The model has none and the mod draws stock's by REFERENCE; stock's leg pixels may
not be copied into anything we ship. So the `legs` candidate draws its own: eight two-segment
strokes from the harness's REAL mount points (sheets.mount_markers, with shared.lua's
mount_shrink and mount_lift, the ring entity.lua ships) up to a knee and down to a foot.
Pure vector geometry, no Wube pixel read. The stance is pulled in to LEG_STANCE of the real
foot ring: the real one is 6 tiles wide and would shrink the shark to a smudge in a 64px
square (an icon is an illustration, not a sprite).

THE DROP SHADOW is synthetic: the subject's own alpha, offset and blurred. The Cycles shadow
pass runs due east at 45 degrees and would make every icon half shadow.
"""

import pathlib, sys  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont  # noqa: E402

from render import factorio_camera as fc  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / "render-out" / "review" / "icons"
STOCK = pathlib.Path("/Applications/factorio.app/Contents/data/base/graphics")

#: Final body resolution for icon renders: 6-tile canvas -> 256 px a tile, so a shark three
#: tiles across is ~770 px before it is cut to 256 (3x oversampled at the tech icon).
ICON_RES = 1536

#: Base's spidertron, measured 2026-09-26: (base size, levels).
ITEM = (64, 4)
TECH = (256, 4)
MINIMAP = 128
THUMB = 144

#: The base minimap palette, read off spidertron-map*.png's pixel histogram.
MAP_FILL = (255, 255, 255, 255)
MAP_RIM = (255, 0, 0, 255)
MAP_RIM_SELECTED = (141, 127, 122, 255)
#: Rim width at 128 px. Base's star carries a 4-6 px rim.
MAP_RIM_PX = 5

#: Factorio's default player colour, (0.869, 0.5, 0.130). What the untinted item icon wears.
PLAYER_ORANGE = (222, 128, 33)

#: Alpha a pixel needs to count toward a crop box. Well above the drop shadow's soft edge,
#: which would fatten the tail past `core`'s erosion and keep it in the box.
CROP_FLOOR = 64

#: Fraction of the real foot ring the drawn legs stand on (see THE LEGS above).
LEG_STANCE = 0.5


# ------------------------------------------------------------------ pure image helpers


def premul_resize(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Lanczos resize in premultiplied alpha. Straight-alpha resampling averages the RGB of
    fully transparent pixels (black) into every edge: a dark halo. MEASURED: Pillow's own
    RGBA resize already premultiplies (a white disc comes back with no halo either way), so
    this pins the behaviour, not a live bug."""
    return img.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")


def alpha_bbox(img: Image.Image, floor: int = 8):
    """Bounding box of pixels with alpha >= floor, or None when there are none."""
    return img.getchannel("A").point(lambda a: 255 if a >= floor else 0).getbbox()


def square_box(img: Image.Image, margin: float, floor: int = 8, core: int = 0):
    """(left, top, side) of the square the subject is cut from: its alpha box grown to a
    square about its centre, plus `margin` (a fraction of the side) on every edge.

    `core` > 0 measures the box on the alpha ERODED by that many px, then grows it back by
    the same amount, so anything thinner than 2*core (the tail's last third, a fin tip) may
    run off the edge. A hammerhead is four tiles of mostly tail; boxing all of him leaves
    the head a third of a 64px square.
    """
    mask = img.getchannel("A").point(lambda a: 255 if a >= floor else 0)
    if core:
        mask = mask.filter(ImageFilter.MinFilter(2 * core + 1))
    box = mask.getbbox()
    if box is None:
        raise ValueError("nothing to crop: the image is fully transparent"
                         + (f" once eroded by {core}px" if core else ""))
    x0, y0, x1, y1 = box[0] - core, box[1] - core, box[2] + core, box[3] + core
    side = int(round(max(x1 - x0, y1 - y0) / (1 - 2 * margin)))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return int(round(cx - side / 2)), int(round(cy - side / 2)), side


def cut(img: Image.Image, box) -> Image.Image:
    """Cut a square_box out of `img`, transparent where the square leaves the canvas."""
    left, top, side = box
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    out.alpha_composite(img.crop((left, top, left + side, top + side)))
    return out


def square_crop(img: Image.Image, margin: float, floor: int = 8, core: int = 0) -> Image.Image:
    return cut(img, square_box(img, margin, floor, core))


def mip_widths(size: int, levels: int) -> list[int]:
    """Level sides: 64, 4 -> [64, 32, 16, 8]."""
    sides = [size >> k for k in range(levels)]
    if any(s < 1 or (size % (1 << k)) for k, s in enumerate(sides)):
        raise ValueError(f"{size}px cannot hold {levels} whole mipmap levels")
    return sides


def mip_strip(square: Image.Image, size: int, levels: int) -> Image.Image:
    """Factorio's mipmap chain: every level resampled from `square`, laid left to right,
    top-aligned, largest first. 64/4 -> 120x64, 256/4 -> 480x256."""
    sides = mip_widths(size, levels)
    strip = Image.new("RGBA", (sum(sides), size), (0, 0, 0, 0))
    x = 0
    for side in sides:
        strip.alpha_composite(premul_resize(square, (side, side)), (x, 0))
        x += side
    return strip


def drop_shadow(img: Image.Image, offset=(0.012, 0.022), blur=0.012, strength=0.45):
    """The subject over a soft copy of its own alpha, offset down-right. Offsets and blur are
    fractions of the image's larger side, so the shadow scales with the crop."""
    side = max(img.size)
    alpha = img.getchannel("A").point(lambda a: int(a * strength))
    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shade.putalpha(alpha)
    shade = shade.filter(ImageFilter.GaussianBlur(max(1.0, blur * side)))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(shade, (int(offset[0] * side), int(offset[1] * side)))
    out.alpha_composite(img)
    return out


def tint(mask: Image.Image, rgb) -> Image.Image:
    """The harness mask multiplied by a colour, as the engine does to a runtime-tinted
    layer."""
    return ImageChops.multiply(mask, Image.new("RGBA", mask.size, tuple(rgb) + (255,)))


def silhouette(img: Image.Image, size: int, rim_rgba, fill_rgba=MAP_FILL,
               rim_px: int = MAP_RIM_PX, floor: int = 96) -> Image.Image:
    """Base's minimap style: a flat fill with a solid rim, on transparency, fitted to a
    `size` square with the rim inside it. Thresholded, not antialiased - base's map art is
    hard-edged apart from a 1 px fringe."""
    fit = square_crop(img, margin=0.0, floor=floor)
    inner = size - 2 * rim_px - 2
    body = fit.getchannel("A").resize((inner, inner), Image.LANCZOS)
    body = body.point(lambda a: 255 if a >= floor else 0)
    canvas_mask = Image.new("L", (size, size), 0)
    canvas_mask.paste(body, ((size - inner) // 2, (size - inner) // 2))
    rim_mask = canvas_mask.filter(ImageFilter.MaxFilter(2 * rim_px + 1))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (size, size), rim_rgba), (0, 0), rim_mask)
    out.paste(Image.new("RGBA", (size, size), fill_rgba), (0, 0), canvas_mask)
    return out


# --------------------------------------------------------------------------- the legs


def leg_segments(mounts, stance: float = LEG_STANCE, knee_lift_px: float = 0.0,
                 knee_t: float = 0.42):
    """(mount, knee, foot, is_front) per leg, in px offsets from the entity origin.

    `mounts` is sheets.mount_markers output: (mount_px, ground_px) pairs. The foot is the
    ground point pulled toward the origin by `stance`; the knee is `knee_t` of the way out
    and lifted `knee_lift_px` up-screen, which is the spidertron's high-kneed gait. A leg is
    FRONT when its foot is south of the origin: it is drawn over the body, the rest under.
    """
    out = []
    for (mx, my), (gx, gy) in mounts:
        fx, fy = gx * stance, gy * stance
        kx = mx + (fx - mx) * knee_t
        ky = my + (fy - my) * knee_t - knee_lift_px
        out.append(((mx, my), (kx, ky), (fx, fy), fy > 0))
    return out


def draw_legs(size, origin, segments, ppt: float, front: bool) -> Image.Image:
    """Gunmetal strokes with a lit core and an orange knee cap. Our own vector art."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    ox, oy = origin
    thick = max(2, int(0.13 * ppt))
    thin = max(2, int(0.10 * ppt))
    for mount, knee, foot, is_front in segments:
        if is_front != front:
            continue
        m = (ox + mount[0], oy + mount[1])
        k = (ox + knee[0], oy + knee[1])
        f = (ox + foot[0], oy + foot[1])
        d.line([m, k], fill=(48, 50, 56, 255), width=thick)
        d.line([k, f], fill=(48, 50, 56, 255), width=thin)
        d.line([m, k], fill=(128, 132, 142, 255), width=max(1, thick // 3))
        d.line([k, f], fill=(128, 132, 142, 255), width=max(1, thin // 3))
        r = thick * 0.8
        d.ellipse([k[0] - r, k[1] - r, k[0] + r, k[1] + r], fill=PLAYER_ORANGE + (255,),
                  outline=(40, 30, 20, 255), width=max(1, thick // 4))
        rf = thin * 0.6
        d.ellipse([f[0] - rf, f[1] - rf, f[0] + rf, f[1] + rf], fill=(48, 50, 56, 255))
    return layer


def draw_map_legs(size, origin, ground_tiles, ppt: float, stance: float,
                  width_tiles: float = 0.32) -> Image.Image:
    """Top-down leg spokes for the minimap: tapered white wedges from the origin out to each
    foot, the way base's spidertron-map.png draws its star. `ground_tiles` are (east, south)."""
    layer = Image.new("L", size, 0)
    d = ImageDraw.Draw(layer)
    ox, oy = origin
    half = width_tiles * ppt / 2
    for gx, gy in ground_tiles:
        fx, fy = ox + gx * stance * ppt, oy + gy * stance * ppt
        dx, dy = fx - ox, fy - oy
        n = max(1e-6, (dx * dx + dy * dy) ** 0.5)
        px, py = -dy / n * half, dx / n * half
        d.polygon([(ox + px, oy + py), (ox - px, oy - py), (fx, fy)], fill=255)
    return layer


# ------------------------------------------------------------------------ candidates


@dataclass
class Shot:
    """One render: which config, which of the 64 directions, which knobs on top."""

    config: str = "render/jamaltron.toml"
    frame: int = 36
    sets: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    name: str
    title: str
    how: str
    icon: Shot
    tech: Shot
    minimap: Shot
    legs: bool = False
    harness: bool = True
    #: square_box's `core` for the item icon and the tech icon / thumbnail, in px of the
    #: ICON_RES render: how thin a part may be and still run off the edge.
    icon_core: int = 0
    tech_core: int = 0


CANDIDATES = [
    Candidate(
        name="portrait",
        title="1  PORTRAIT - the shark, 3/4 toward you",
        how="standing config, direction 34 of 64 (just west of S, nose at the camera), the "
            "game's 45 deg camera; tech icon + thumbnail from a lower 30 deg camera so the "
            "hammer reads head-on. Cropped on his CORE (parts thinner than 32 px at 1536, "
            "20 on the tech icon, may leave the frame), so the tail tip runs off the top. "
            "Minimap: 90 deg top-down",
        icon=Shot(frame=34),
        tech=Shot(frame=35, sets=["camera.pitch=30.0"]),
        minimap=Shot(frame=0, sets=["camera.pitch=90.0"]),
        icon_core=16,
        tech_core=10,
    ),
    Candidate(
        name="legs",
        title="2  ON HIS LEGS - the vehicle read",
        how="standing config, direction 40 (SW), plus eight legs drawn by icons.py as vector "
            "strokes from the harness's real mount ring (shared.lua mount_shrink/mount_lift), "
            f"stance pulled in to {LEG_STANCE}; no stock pixel used. Minimap: top-down "
            "shark + eight white spokes, base's star idea",
        icon=Shot(frame=40),
        tech=Shot(frame=40),
        minimap=Shot(frame=0, sets=["camera.pitch=90.0"]),
        legs=True,
    ),
    Candidate(
        name="beached",
        title="3  BEACHED - the comedy read",
        how="beached.toml (the shipped flop), SWIM_FAST frame 1 - head and tail both up, "
            "belly and grin to camera - broadside at direction 16; minimap is the same "
            "pose from 90 deg, i.e. a shark lying on his side. No harness: it is not on "
            "the flop body either",
        icon=Shot(config="render/beached.toml", frame=16, sets=["model.frame=1"]),
        tech=Shot(config="render/beached.toml", frame=16, sets=["model.frame=1"]),
        minimap=Shot(config="render/beached.toml", frame=16,
                     sets=["camera.pitch=90.0", "model.frame=1"]),
        harness=False,
    ),
]


# ------------------------------------------------------------------------- rendering


def render(shot: Shot, which: str, samples: int):
    """(PIL image, cfg, px per tile) for one frame of one pass, through the shared cache."""
    from render import art, artconfig as ac
    sets = [f"render.resolution_px={ICON_RES}", "render.supersample=1"] + shot.sets
    cfg = ac.load(REPO / "tools" / shot.config, ac.parse_set(sets))
    outdir, _ = art.render_pass(cfg, which, [shot.frame], samples, jobs=1)
    img = Image.open(outdir / f"frame_{shot.frame:03d}.png").convert("RGBA")
    return img, cfg, ICON_RES / cfg["camera.canvas_tiles"]


def subject(cand: Candidate, shot: Shot, samples: int, *, harness_rgb=PLAYER_ORANGE,
            mask_only: bool = False) -> Image.Image:
    """The full-res subject for one shot: body, harness tint, legs. Uncropped, unshadowed."""
    from render import sheets
    body, cfg, ppt = render(shot, "body", samples)
    mask = None
    if cand.harness:
        mask, _, _ = render(shot, "mask", samples)
    pad = int(ppt * 2) if cand.legs else 0
    size = (body.width + 2 * pad, body.height + 2 * pad)
    origin = (fc.origin_pixel(body.width) + pad, fc.origin_pixel(body.height) + pad)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    segments = []
    if cand.legs:
        mounts = sheets.mount_markers(ppt, sheets.mount_shrink(), sheets.mount_lift())
        segments = leg_segments(mounts, knee_lift_px=1.05 * fc.K * ppt)
        if not mask_only:
            canvas.alpha_composite(draw_legs(size, origin, segments, ppt, front=False))
    if mask_only:
        if mask is not None:
            canvas.alpha_composite(mask, (pad, pad))
        return canvas
    canvas.alpha_composite(body, (pad, pad))
    if mask is not None and harness_rgb is not None:
        canvas.alpha_composite(tint(mask, harness_rgb), (pad, pad))
    if cand.legs:
        canvas.alpha_composite(draw_legs(size, origin, segments, ppt, front=True))
    return canvas


def minimap_source(cand: Candidate, samples: int) -> Image.Image:
    """Top-down alpha for the minimap, legs as spokes for the legs candidate."""
    from render import sheets
    body, _, ppt = render(cand.minimap, "body", samples)
    if not cand.legs:
        return body
    pad = int(ppt * 2)
    size = (body.width + 2 * pad, body.height + 2 * pad)
    origin = (fc.origin_pixel(body.width) + pad, fc.origin_pixel(body.height) + pad)
    ground = [g for _, g in sheets.LEG_MOUNTS]
    spokes = draw_map_legs(size, origin, ground, ppt, LEG_STANCE)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.putalpha(spokes)
    out.alpha_composite(body, (pad, pad))
    return out


def build(cand: Candidate, samples: int) -> dict:
    """Render and write one candidate's full set. Returns {role: path}."""
    d = OUT / cand.name
    d.mkdir(parents=True, exist_ok=True)
    paths = {}

    icon_src = drop_shadow(subject(cand, cand.icon, samples))
    icon_box = square_box(icon_src, margin=0.02, floor=CROP_FLOOR, core=cand.icon_core)
    icon_sq = cut(icon_src, icon_box)
    mip_strip(icon_sq, *ITEM).save(d / "icon.png")
    paths["icon"] = d / "icon.png"
    if cand.harness:
        # The tintable pair must register with icon.png pixel for pixel, so both are cut
        # with icon.png's crop box, not recropped around their own alpha.
        plain = drop_shadow(subject(cand, cand.icon, samples, harness_rgb=None))
        mask = subject(cand, cand.icon, samples, mask_only=True)
        for name, img in (("icon-tintable", plain), ("icon-tintable-mask", mask)):
            sq = cut(img, icon_box)
            mip_strip(sq, *ITEM).save(d / f"{name}.png")
            paths[name] = d / f"{name}.png"

    tech_src = drop_shadow(subject(cand, cand.tech, samples))
    tech_sq = square_crop(tech_src, margin=0.03, floor=CROP_FLOOR, core=cand.tech_core)
    mip_strip(tech_sq, *TECH).save(d / "technology.png")
    paths["technology"] = d / "technology.png"
    premul_resize(square_crop(tech_src, margin=0.07, floor=CROP_FLOOR, core=cand.tech_core),
                  (THUMB, THUMB)).save(d / "thumbnail.png")
    paths["thumbnail"] = d / "thumbnail.png"

    top = minimap_source(cand, samples)
    silhouette(top, MINIMAP, MAP_RIM).save(d / "minimap.png")
    silhouette(top, MINIMAP, MAP_RIM_SELECTED).save(d / "minimap-selected.png")
    paths["minimap"] = d / "minimap.png"
    paths["minimap-selected"] = d / "minimap-selected.png"

    write_manifest(d, cand, samples)
    return paths


def manifest(cand: Candidate, samples: int | None = None) -> dict:
    """The lint_sprites.py icon manifest for one candidate directory. `sprites: []` is there
    because that key is what ci.yml's classifier recognises (see lint_sprites.py). `samples`
    is what --promote reads to refuse a --preview render."""
    icons = [
        {"id": f"{cand.name}.icon", "kind": "icon", "filename": "__jamaltron__/icon.png"},
        {"id": f"{cand.name}.technology", "kind": "technology",
         "filename": "__jamaltron__/technology.png"},
        {"id": f"{cand.name}.minimap", "kind": "minimap", "filename": "__jamaltron__/minimap.png"},
        {"id": f"{cand.name}.minimap_selected", "kind": "minimap",
         "filename": "__jamaltron__/minimap-selected.png"},
        {"id": f"{cand.name}.thumbnail", "kind": "thumbnail",
         "filename": "__jamaltron__/thumbnail.png"},
    ]
    if cand.harness:
        icons[1:1] = [
            {"id": f"{cand.name}.icon_tintable", "kind": "icon",
             "filename": "__jamaltron__/icon-tintable.png"},
            {"id": f"{cand.name}.icon_tintable_mask", "kind": "icon",
             "filename": "__jamaltron__/icon-tintable-mask.png"},
        ]
    blob = {"version": 1, "generated_by": "tools/render/icons.py", "candidate": cand.name,
            "mod_roots": {"jamaltron": "."}, "sprites": [], "icons": icons}
    if samples is not None:
        blob["samples"] = samples
    return blob


def write_manifest(d: pathlib.Path, cand: Candidate, samples: int | None = None) -> None:
    (d / "icons.json").write_text(json.dumps(manifest(cand, samples), indent=2) + "\n")


# ---------------------------------------------------------------------------- promote

#: --promote's mod root. Its graphics/ is the tree ci.yml lints --strict and the one carrying
#: the RenderHub carve-out; thumbnail.png is the one file the engine wants at the root.
PROMOTE_ROOT = REPO / "mod" / "jamaltron"
SHIPPED_MANIFEST = "graphics/icons.json"
#: A candidate rendered below this is a --preview: fine to look at, not to ship.
SHIP_SAMPLES = 64

#: (candidate file, path under the mod root, manifest id, kind). item.lua, technology.lua and
#: entity.lua name these paths as literals; test_icons.py checks each one is named.
SHIPPED = (
    ("icon.png", "graphics/jamaltron-icon.png", "item.icon", "icon"),
    ("icon-tintable.png", "graphics/jamaltron-icon-tintable.png", "item.icon_tintable", "icon"),
    ("icon-tintable-mask.png", "graphics/jamaltron-icon-tintable-mask.png",
     "item.icon_tintable_mask", "icon"),
    ("technology.png", "graphics/jamaltron-technology.png", "technology.icon", "technology"),
    ("minimap.png", "graphics/jamaltron-minimap.png", "entity.minimap_representation",
     "minimap"),
    ("minimap-selected.png", "graphics/jamaltron-minimap-selected.png",
     "entity.selected_minimap_representation", "minimap"),
    ("thumbnail.png", "thumbnail.png", "mod.thumbnail", "thumbnail"),
)


def shipped_manifest(candidate: str, samples: int) -> dict:
    """graphics/icons.json: every icon the mod ships, with its kind, so the C.15 gate checks
    size, mip chain and alpha. `mod_roots` is one level up because the manifest sits in
    graphics/ - ci.yml's --mod-root wins over it anyway."""
    return {"version": 1, "generated_by": "tools/render/icons.py --promote",
            "candidate": candidate, "samples": samples,
            "mod_roots": {"jamaltron": ".."}, "sprites": [],
            "icons": [{"id": ident, "kind": kind, "filename": f"__jamaltron__/{dest}"}
                      for _, dest, ident, kind in SHIPPED]}


class PromoteError(Exception):
    pass


def promote(name: str, src_root: pathlib.Path = OUT,
            mod_root: pathlib.Path = PROMOTE_ROOT) -> list[pathlib.Path]:
    """Copy candidate `name` into `mod_root` under the SHIPPED names and write the manifest.
    Refuses before touching the mod when the candidate is missing a file, was rendered at
    preview samples, or does not lint --strict where it sits. Returns the paths written."""
    import lint_sprites
    src = src_root / name
    blob_path = src / "icons.json"
    if not blob_path.is_file():
        raise PromoteError(f"no candidate at {src}: run icons.py --only {name} first")
    blob = json.loads(blob_path.read_text())
    samples = blob.get("samples")
    if not isinstance(samples, int) or samples < SHIP_SAMPLES:
        raise PromoteError(
            f"{blob_path} records samples={samples!r}; shipping wants >= {SHIP_SAMPLES}. "
            f"Re-render without --preview (icons.py --only {name}) and look again")
    missing = [f for f, *_ in SHIPPED if not (src / f).is_file()]
    if missing:
        raise PromoteError(f"candidate {name} has no {', '.join(missing)} - item.lua wires "
                           "the tintable pair, so a harnessless candidate cannot ship as-is")
    result = lint_sprites.lint_detail([blob_path], lint_sprites.ModPaths(), strict=True)
    if result.findings:
        raise PromoteError("candidate fails the strict icon lint where it sits:\n"
                           + "\n".join(f.render() for f in result.findings))

    written = []
    for src_name, dest, _, _ in SHIPPED:
        out = mod_root / dest
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / src_name, out)
        written.append(out)
    manifest_path = mod_root / SHIPPED_MANIFEST
    manifest_path.write_text(json.dumps(shipped_manifest(name, samples), indent=2) + "\n")
    written.append(manifest_path)

    mods = lint_sprites.ModPaths()
    mods.add("jamaltron", mod_root)
    result = lint_sprites.lint_detail([manifest_path], mods, strict=True)
    if result.findings or result.icons != len(SHIPPED):
        raise PromoteError(f"the promoted manifest does not lint clean ({result.icons} icons):\n"
                           + "\n".join(f.render() for f in result.findings))
    return written


# ----------------------------------------------------------------------- review sheets

BG = (36, 38, 41, 255)
INK = (225, 225, 225, 255)
DIM = (150, 150, 150, 255)


def _font(size: int):
    for name in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def checker(size, cell: int = 8) -> Image.Image:
    """Transparency checkerboard, so an alpha fringe is visible on the sheet."""
    img = Image.new("RGBA", size, (70, 72, 76, 255))
    d = ImageDraw.Draw(img)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=(56, 58, 62, 255))
    return img


def on_checker(img: Image.Image, scale: int = 1) -> Image.Image:
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    bg = checker(img.size)
    bg.alpha_composite(img)
    return bg


def candidate_sheet(cands, samples: int) -> Image.Image:
    """00-icon-candidates.png: every candidate, every file, at 1x then 2x (nearest-neighbour,
    so the 2x shows the real pixels, not a smoother fake)."""
    f_title, f_label = _font(20), _font(13)
    blocks = []
    for cand in cands:
        d = OUT / cand.name
        files = [("icon.png  120x64", "icon.png"),
                 ("minimap", "minimap.png"), ("minimap-selected", "minimap-selected.png"),
                 ("technology.png  480x256", "technology.png"), ("thumbnail  144", "thumbnail.png")]
        if cand.harness:
            files[1:1] = [("icon-tintable", "icon-tintable.png"),
                          ("icon-tintable-mask", "icon-tintable-mask.png")]
        rows = []
        for scale in (1, 2):
            tiles = [(label, on_checker(Image.open(d / fn).convert("RGBA"), scale))
                     for label, fn in files]
            rows.append((scale, tiles))
        blocks.append((cand, rows))

    gap, label_h, pad = 18, 18, 24
    width = max(pad * 2 + 60 + sum(t.width + gap for _, t in tiles)
                for _, rows in blocks for _, tiles in rows)
    height = pad
    for _, rows in blocks:
        height += 34 + 22 + sum(label_h + max(t.height for _, t in tiles) + gap
                                for _, tiles in rows) + 20
    sheet = Image.new("RGBA", (width, height), BG)
    dr = ImageDraw.Draw(sheet)
    y = pad
    for cand, rows in blocks:
        dr.text((pad, y), cand.title, font=f_title, fill=INK)
        y += 34
        dr.text((pad, y), cand.how[:230], font=f_label, fill=DIM)
        y += 22
        for scale, tiles in rows:
            dr.text((pad, y + label_h + 4), f"{scale}x", font=f_title, fill=DIM)
            x = pad + 60
            for label, tile in tiles:
                dr.text((x, y), label, font=f_label, fill=DIM)
                sheet.alpha_composite(tile, (x, y + label_h))
                x += tile.width + gap
            y += label_h + max(t.height for _, t in tiles) + gap
        dr.line([(pad, y + 4), (width - pad, y + 4)], fill=(70, 70, 70, 255))
        y += 20
    dr.text((pad, height - 18),
            f"tools/render/icons.py  ICON_RES={ICON_RES}  samples={samples}  "
            "checker = transparency; 2x is nearest-neighbour", font=f_label, fill=DIM)
    return sheet


def slot(size: int, light: bool) -> Image.Image:
    """A Factorio-ish inventory slot: bevelled square, dark (inventory) or light (the pale
    slot Factorio uses for hovered / filter / crafting-queue buttons)."""
    face = (198, 198, 198, 255) if light else (48, 48, 48, 255)
    hi = (232, 232, 232, 255) if light else (74, 74, 74, 255)
    lo = (140, 140, 140, 255) if light else (22, 22, 22, 255)
    img = Image.new("RGBA", (size, size), face)
    d = ImageDraw.Draw(img)
    b = max(1, size // 20)
    d.rectangle([0, 0, size - 1, b - 1], fill=lo)
    d.rectangle([0, 0, b - 1, size - 1], fill=lo)
    d.rectangle([0, size - b, size - 1, size - 1], fill=hi)
    d.rectangle([size - b, 0, size - 1, size - 1], fill=hi)
    return img


def level(strip: Image.Image, side: int) -> Image.Image:
    """Pull one mip level out of a strip (64/32/16/8 for an item icon)."""
    x, s = 0, strip.height
    while s > side:
        x += s
        s //= 2
    return strip.crop((x, 0, x + side, side))


def context_sheet(cand: Candidate, stock: Image.Image | None) -> Image.Image:
    """01-context-<name>.png: the item icon in a row of inventory slots, dark and light, at
    100% UI scale (32 px mip in a 40 px slot) and 200% (the 64 in an 80). The second slot
    holds stock's spidertron icon for scale when the game is installed - REVIEW ONLY, it is
    never written anywhere that ships."""
    strip = Image.open(OUT / cand.name / "icon.png").convert("RGBA")
    f = _font(13)
    rows = []
    for ui, slot_px, icon_px in (("100% UI", 40, 32), ("200% UI", 80, 64)):
        for light in (False, True):
            cells = []
            for who in ("ours", "stock", "ours", "empty", "ours"):
                s = slot(slot_px, light)
                src = strip if who == "ours" else stock
                if who != "empty" and src is not None:
                    icon = level(src, icon_px)
                    o = (slot_px - icon_px) // 2
                    s.alpha_composite(icon, (o, o))
                cells.append(s)
            rows.append((f"{ui}  {'light' if light else 'dark'}", cells))
    title = f"{cand.title} - in a slot (2nd column: stock spidertron, reference only)"
    title_w = int(ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(title, font=f))
    width = max(24 + 150 + max(sum(c.width + 4 for c in cells) for _, cells in rows),
                24 + title_w) + 24
    height = 44 + sum(cells[0].height + 14 for _, cells in rows) + 30
    img = Image.new("RGBA", (width, height), (30, 30, 30, 255))
    d = ImageDraw.Draw(img)
    d.text((24, 14), title, font=f, fill=INK)
    y = 44
    for label, cells in rows:
        d.text((24, y + cells[0].height // 2 - 7), label, font=f, fill=DIM)
        x = 24 + 150
        for c in cells:
            img.alpha_composite(c, (x, y))
            x += c.width + 4
        y += cells[0].height + 14
    return img


# ------------------------------------------------------------------------------ main


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--only", choices=[c.name for c in CANDIDATES], action="append")
    p.add_argument("--preview", action="store_true", help="16 samples instead of 64")
    p.add_argument("--promote", choices=[c.name for c in CANDIDATES], metavar="NAME",
                   help=f"copy the rendered candidate NAME into {PROMOTE_ROOT.relative_to(REPO)} "
                        "(renders nothing; see the docstring)")
    args = p.parse_args(argv)
    if args.promote:
        if args.only or args.preview:
            p.error("--promote renders nothing: it takes no --only or --preview")
        try:
            written = promote(args.promote)
        except PromoteError as exc:
            sys.stderr.write(f"icons.py: {exc}\n")
            return 1
        for path in written:
            print(f"icons: promoted {path.relative_to(REPO)}")
        return 0
    samples = 16 if args.preview else 64
    cands = [c for c in CANDIDATES if not args.only or c.name in args.only]
    OUT.mkdir(parents=True, exist_ok=True)
    stock_path = STOCK / "icons" / "spidertron.png"
    stock = Image.open(stock_path).convert("RGBA") if stock_path.is_file() else None
    for cand in cands:
        print(f"icons: {cand.name}")
        build(cand, samples)
        context_sheet(cand, stock).save(OUT / f"01-context-{cand.name}.png")
    have = [c for c in CANDIDATES if (OUT / c.name / "icon.png").is_file()]
    candidate_sheet(have, samples).save(OUT / "00-icon-candidates.png")
    print(f"icons: wrote {OUT / '00-icon-candidates.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
