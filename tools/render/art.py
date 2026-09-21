#!/usr/bin/env python3
"""The C.10 art-iteration harness. Change a knob, look at a picture, repeat.

    uv run --directory tools python render/art.py --preview     # 8 rotations, seconds
    uv run --directory tools python render/art.py --compare     # THE image to look at
    uv run --directory tools python render/art.py --full        # the real 64
    uv run --directory tools python render/art.py --shadow      # shadow-only pass
    uv run --directory tools python render/art.py --mask        # the runtime-tint harness
    uv run --directory tools python render/art.py --show        # print resolved knobs

    ... --set model.scale=0.85 --set 'model.rotation=[0,6,0]'   # try before you commit
    ... --blend /path/to/HAMMERHEAD.blend                       # or $JAMALTRON_BLEND

THE FLOP (C.5) is knobs like everything else -- one clip, one frame of it, the rig fix it
needs, and the bounce:

    ... --set 'model.action="SWIM_FAST"' --set model.frame=12 \
        --set model.reparent_head=true --set 'model.rotation=[85,0,0]' \
        --set bounce.height=0.3 --set bounce.phase=0.25

THE DESIGN CONSTRAINT IS FEEDBACK SPEED, NOT FEATURES. A 64-rotation Cycles sheet is the
wrong loop for "make him 10% bigger and nudge the pitch": by the time it finishes you have
forgotten what you were comparing against. So:

  * --preview renders 8 of the 64 directions at the SAME angles the full sheet uses, so
    preview frames are a strict subset and nothing is thrown away when you commit to --full.
  * frames are cached under the hash of only the knobs that affect that pass. Change
    `compare.background` and 64 Cycles frames survive; change `model.scale` and none do.
  * --jobs runs several Blenders over disjoint frame sets. A sprite-sized tile is pure
    launch overhead for one process and this machine has 12 performance cores.

EVERY OUTPUT IS TRACEABLE. Each sheet carries the config hash in a PNG text chunk, in a
visible footer, and in a sidecar `.json` holding the fully resolved knobs. A sheet you
found in a folder three weeks later still knows what made it.

Renders land in render-out/ (gitignored). Promoting a sheet into mod/jamaltron/graphics/
is a DELIBERATE act -- that directory carries the RenderHub carve-out licence and this
tool will not put anything there for you.
"""

# sys.path, verbatim per tools/README.md -- Python and Blender both put THIS file's own
# directory on sys.path[0], never tools/, and `package = false` means there is no installed
# `render` to fall back on. Cannot be factored into a helper: importing the helper is the
# thing that needs the path fixed.
import pathlib, sys  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse  # noqa: E402
import concurrent.futures  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402

from render import artconfig as ac  # noqa: E402
from render import factorio_camera as fc  # noqa: E402
from render import pose  # noqa: E402
from render import sheets  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
RENDER_SCRIPT = pathlib.Path(__file__).resolve().parent / "render_jamal.py"


# --------------------------------------------------------------------------- plumbing


def out_root(cfg) -> pathlib.Path:
    p = pathlib.Path(cfg["output.dir"])
    return p if p.is_absolute() else REPO / p


def shorten(path: pathlib.Path) -> str:
    """A path for a human, repo-relative WHERE THAT IS POSSIBLE.

    `output.dir` takes an absolute path -- out_root() says so -- and every render then
    printed it through Path.relative_to(REPO), which RAISES on a path outside the repo.
    A progress line is not a place to throw from: rendering into /tmp is exactly what you
    do when you want a timing run that does not touch the shipped cache.
    """
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def pass_dir(cfg, which: str, samples: int) -> pathlib.Path:
    """Cache directory for one pass. Named by the hash of the knobs that change its
    pixels, plus the sample count -- preview and full differ ONLY in samples, and a
    16-sample frame must never be served as a 64-sample one."""
    return out_root(cfg) / which / f"{ac.pass_hash(cfg, which)}_s{samples}"


def blend_path(cfg) -> pathlib.Path:
    """Where the model is. artconfig owns the resolution because it DIGESTS this file --
    two resolvers and the hash would describe a different file from the one Blender
    opened. Kept as a name here because tune.py and the render loop both call it."""
    return ac.blend_path(cfg)


def chunk(items, n):
    """Round-robin so every worker gets a mix of angles and they finish together."""
    n = max(1, min(n, len(items)))
    out = [[] for _ in range(n)]
    for i, item in enumerate(items):
        out[i % n].append(item)
    return [c for c in out if c]


def run_blender(blend, config_json, which, frames, outdir, quiet=True):
    cmd = [BLENDER, "-b", str(blend), "--python", str(RENDER_SCRIPT), "--",
           "--config", str(config_json), "--pass", which,
           "--frames", ",".join(str(f) for f in frames), "--out", str(outdir)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout[-4000:] + "\n" + proc.stderr[-4000:] + "\n")
        raise SystemExit(f"blender failed ({proc.returncode}) on frames {frames}")
    result, notes = None, []
    for line in proc.stdout.splitlines():
        if line.startswith("JAMALTRON_RESULT "):
            result = json.loads(line.split(" ", 1)[1])
        elif line.startswith(("FIX ", "CHECK ", "CAM ", "SUN ", "RENDER ", "POSE ", "WARN ")):
            notes.append(line.rstrip())
    if not quiet:
        for n in notes:
            print("   " + n)
    return result, notes


def warn_notes(notes):
    """The notes that are WARNINGS. render_pass prints these however quiet the pass is.

    FIX / CAM / SUN / RENDER / POSE are a running commentary and belong behind `-v`. A WARN is
    the renderer telling you the picture is wrong, and it is worth nothing if only `-v` shows
    it: C.5's own "the posed body reaches 0.36 tiles BELOW the ground plane" -- the one line
    that explains a flop whose shadow comes back sliced -- landed in a list nobody printed,
    and both the CLI and the tuner were quiet, so nobody saw it in either.

    Deduped one level up, because N jobs are N Blenders and each one says it about its own
    frames.
    """
    return [n for n in notes if n.startswith("WARN ")]


def render_pass(cfg, which, frames, samples, *, jobs=1, force=False, verbose=False):
    """Render the missing frames of one pass. Returns (directory, stats)."""
    outdir = pass_dir(cfg, which, samples)
    outdir.mkdir(parents=True, exist_ok=True)
    have = {i for i in frames if (outdir / f"frame_{i:03d}.png").exists()}
    todo = [i for i in frames if force or i not in have]

    # The sidecar IS the payload handed to Blender: one file, so a cached frame and the
    # config that made it can never drift apart.
    payload = outdir / "config.json"
    blob = ac.stamp(cfg, {"pass": which, "samples": samples, "frames": sorted(frames)})
    payload.write_text(json.dumps(blob, indent=2, sort_keys=True))

    if not todo:
        print(f"  {which:<7} {len(frames)} frames CACHED  {shorten(outdir)}")
        warn_if_clipped(cfg, outdir, frames, which)
        return outdir, {"seconds": 0.0, "rendered": 0, "cached": len(frames)}

    blend = blend_path(cfg)
    if not blend.exists():
        raise SystemExit(
            f"model not found: {blend}\n"
            f"  the .blend is gitignored and machine-local. Point at it with\n"
            f"  --blend /path/to/HAMMERHEAD.blend or ${ac.BLEND_ENV}=...")

    t0 = time.time()
    groups = chunk(todo, jobs)
    results = []
    if len(groups) == 1:
        results.append(run_blender(blend, payload, which, groups[0], outdir, quiet=not verbose))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(groups)) as pool:
            futures = [pool.submit(run_blender, blend, payload, which, g, outdir,
                                   not (verbose and i == 0))
                       for i, g in enumerate(groups)]
            results = [f.result() for f in futures]
    wall = time.time() - t0

    d = ac.derived(cfg)
    ss = d["supersample"]
    final = d["shadow_resolution_px"] if which == "shadow" else d["body_resolution_px"]
    if ss > 1:
        downsample(outdir, todo, final)
    engine = (results[0][0] or {}).get("engine", "?")
    size = f"{final}px" if ss == 1 else f"{final}px (rendered {final * ss}, x{ss} SS)"
    print(f"  {which:<7} {len(todo)} frames in {wall:6.2f}s  "
          f"({wall / len(todo):.2f}s/frame, {engine}, {samples} samples, {size}, "
          f"{len(groups)} job{'s' if len(groups) > 1 else ''})  "
          f"{shorten(outdir)}")
    warn_if_clipped(cfg, outdir, frames, which)
    stats = {"seconds": wall, "rendered": len(todo), "cached": len(frames) - len(todo),
             "engine": engine, "jobs": len(groups)}
    # THE POSED BOX, unioned over however many Blenders ran. artconfig.derived() reports the
    # REST box off a measured constant, which is right for the standing shark and wrong the
    # moment he thrashes -- C.17 needs the real one and so does anyone pricing the bounce.
    boxes = [r[0]["box_tiles"] for r in results if (r[0] or {}).get("box_tiles")]
    if boxes:
        stats["box_tiles"] = [[min(b[k][0] for b in boxes), max(b[k][1] for b in boxes)]
                              for k in range(3)]
    # The renderer's own warnings, once each. -v has already printed every note per job.
    if not verbose:
        for w in dict.fromkeys(w for r in results for w in warn_notes(r[1])):
            print("   " + w)
    for r in results:
        for m in (r[0] or {}).get("clip_mismatches", ()):
            print("  WARN clip table vs the model: " + m)
    return outdir, stats


#: Knob to turn when a pass runs out of canvas, per pass.
CANVAS_KNOB = {"body": "camera.canvas_tiles", "shadow": "camera.shadow_canvas_tiles"}


#: Alpha at which a pixel IS PART OF THE SPRITE, because Factorio DRAWS it: the engine
#: composites with the alpha in the PNG, so an alpha-1 pixel is a faint pixel, not an
#: absent one. Every question of the form "how big is he" or "did a crop cut him" -- the
#: packer's frame box, the refusals around it, the compare cell's own crop check -- is
#: asked at THIS number.
#:
#: It used to be 8, and that is exactly how C.4 shipped a shark with his tail fin sliced
#: off: the fin tip's antialiasing ramp does not clear alpha 8, so it was measured OUT of
#: the box that was supposed to contain it, and the gate meant to catch a cut sprite was
#: reading the same thresholded mask and therefore agreed that nothing was wrong. The
#: faint pixels were visible in game. He was clipped at the frame edge in dir 16 and 48.
SPRITE_VISIBLE_ALPHA = 1

#: Alpha below which a Cycles SHADOW-CATCHER frame is SAMPLING NOISE rather than shadow.
#: NOT a claim about what is visible -- see above -- but about what the renderer scattered:
#: MEASURED on a 704 px shadow frame, the alpha>=1 bbox is the whole canvas (9537 noise
#: pixels) while the alpha>=8 bbox is (271,318)-(513,386), which is the shadow. pack.py
#: ZEROES everything under this in the shadow sheets it writes, and it does so BEFORE it
#: measures them, which is what makes both thresholds agree about the pixels that ship.
RENDER_NOISE_FLOOR = 8

#: Per PASS, what counts as sprite in a RAW render. Body and mask are transparent-film
#: renders whose alpha IS the subject's own coverage -- MEASURED on the shipped 64-frame
#: body pass, the alpha>=1 union is one pixel wider per side than the alpha>=8 one and
#: there is no stray alpha anywhere else on the canvas -- so the visible threshold is the
#: honest one there. A raw shadow frame is noise edge to edge, so asking the visible
#: question of one reports every frame clipped, every run, and the warning stops working.
PASS_ALPHA_FLOOR = {"shadow": RENDER_NOISE_FLOOR}


def pass_alpha_floor(which: str) -> int:
    """What counts as sprite in a raw `which`-pass frame. One lookup, so no caller picks
    the noise floor for a body frame by accident -- which is the bug this fixes."""
    return PASS_ALPHA_FLOOR.get(which, SPRITE_VISIBLE_ALPHA)


def warn_if_clipped(cfg, outdir, frames, which, floor: int | None = None):
    """Shout when the render ran out of canvas. Measured off the alpha, every run.

    A clipped frame does not look broken, it looks like a shark with a flat dorsal fin,
    and you will spend twenty minutes on the LIGHTING before you notice the canvas. At the
    VISIBLE threshold (the default, per pass) the shipped 6-tile body canvas holds scale
    0.81 with 12 px -- 0.19 tiles -- to spare at the SIDES, frames 16 and 48, the broadside
    pair. Scaled off that margin the first cut lands just under 0.86. Read at alpha >= 8
    the same canvas looked good to 0.87, because that reading hands you a pixel of margin
    per side that is not actually empty. Either way it is one nudge of the scale slider,
    which is why this runs on every pass.

    Runs on cached frames too: the second run at a too-big scale is the one where you have
    forgotten, and a warning that only fires on a cache miss is a warning you never see.
    """
    from PIL import Image
    floor = pass_alpha_floor(which) if floor is None else floor
    clipped = []
    for i in frames:
        p = outdir / f"frame_{i:03d}.png"
        if not p.exists():
            continue
        img = Image.open(p)
        if img.mode not in ("RGBA", "LA"):
            continue
        bb = img.getchannel("A").point(lambda v: 255 if v >= floor else 0).getbbox()
        if bb and (bb[0] <= 0 or bb[1] <= 0 or bb[2] >= img.width or bb[3] >= img.height):
            clipped.append(i)
    if clipped:
        knob = CANVAS_KNOB.get(which, "camera.canvas_tiles")
        shown = ",".join(str(i) for i in clipped[:8]) + ("..." if len(clipped) > 8 else "")
        print("WARN %s pass: %d/%d frames TOUCH THE CANVAS EDGE (frames %s). The sprite is "
              "cut, not small -- raise %s (now %.2f) and re-render."
              % (which, len(clipped), len(frames), shown, knob, cfg[knob]))
    return clipped


def cell_fit_line(cfg, cuts, needs) -> str:
    """One line saying whether the compare CELL held every frame, and what it cost.

    The render canvas has had a warning since C.10; the cell it gets composited into had
    none, and a cell that is too small crops the sprite silently -- it reads as a tight
    crop, not as a bug. That is the worst possible failure for THIS image, because the
    compare sheet is where scale, pivot and offset get decided: every one of those
    judgements is made against a picture the sheet cropped. So the verdict goes on stdout
    AND in the footer, whether or not it is bad news, the way the mount self-check does.
    """
    have, oy = cfg["compare.cell_tiles"], cfg["compare.origin_y"]
    # Rounded UP to the printed precision: 0.01 tiles is 0.64 px, and a recommendation
    # you paste in that still crops by half a pixel is worse than no recommendation.
    want = math.ceil((max(needs) if needs else 0.0) * 100) / 100
    bad = [(label, cut) for label, cut in cuts if any(cut)]
    if not bad:
        return ("compare cell %.2f tiles at origin_y %.2f holds every frame "
                "(tightest needs %.2f)" % (have, oy, want))
    worst = [max(cut[k] for _, cut in bad) for k in range(4)]
    return ("compare cell %.2f tiles at origin_y %.2f CROPS %d/%d frames -- worst "
            "L/T/R/B %d/%d/%d/%d px (%s). Raise compare.cell_tiles to %.2f, or move "
            "compare.origin_y: the sprite is CUT, and this is the sheet you size him on"
            % (have, oy, len(bad), len(cuts), worst[0], worst[1], worst[2], worst[3],
               ", ".join(label for label, _ in bad[:4])
               + ("..." if len(bad) > 4 else ""), want))


def downsample(outdir, frames, target_px):
    """Supersampled frames -> the STAMPED size, Lanczos. Done here and not in Blender
    because Blender has no Pillow and the uv side does.

    Resizes to the derived target rather than width // factor, so the file on disk and the
    resolution in its own sidecar cannot disagree by a rounding."""
    from PIL import Image
    for i in frames:
        p = outdir / f"frame_{i:03d}.png"
        img = Image.open(p)
        img.resize((target_px, target_px), Image.LANCZOS).save(p)


# ----------------------------------------------------------------------------- sheets


def sheet_paths(cfg, name):
    d = out_root(cfg) / "sheets"
    d.mkdir(parents=True, exist_ok=True)
    h = ac.config_hash(cfg)
    return d / f"{name}_{h}.png", d / f"{name}_{h}.json"


def contact_sheet(cfg, which, frames, bodydir, label, passes=()):
    """Plain grid of one pass's frames, 8 across like the stock sheet."""
    from PIL import Image, ImageDraw
    d = ac.derived(cfg)
    ppt = d["body_px_per_tile"] if which != "shadow" else d["shadow_px_per_tile"]
    cell = int(round(cfg["compare.cell_tiles"] * d["sprite_px_per_tile"]))
    cols, rows = sheets.contact_grid(len(frames))
    # Reserved, filled once the cells have been measured -- drop the placeholder and the
    # grid is laid out one line short and the text renders off-canvas.
    foot = footer_lines(cfg, label, passes) + [""]
    lay = sheets.GridLayout(cols=cols, rows=rows, cell=cell, left=10, top=22,
                            bottom=sheets.footer_height(len(foot)))
    canvas = Image.new("RGBA", (lay.width, lay.height), (26, 28, 30, 255))
    draw = ImageDraw.Draw(canvas)
    font = sheets._font(12)
    cuts, needs = [], []
    for n, i in enumerate(frames):
        col, row = n % cols, n // cols
        x, y = lay.cell_origin(col, row)
        bg = sheets.cell_background(cell, cfg["compare.background"],
                                    d["sprite_px_per_tile"], cfg["compare.grid"],
                                    cfg["compare.origin_y"])
        frame, cut, need = sheets.render_frame_cell(
            bodydir / f"frame_{i:03d}.png", cell, ppt, d["sprite_px_per_tile"],
            cfg["compare.origin_y"], pass_alpha_floor(which))
        cuts.append(("%02d" % i, cut))
        needs.append(need)
        bg.alpha_composite(frame)
        if cfg["compare.show_mounts"]:
            sheets.draw_mounts(bg, d["sprite_px_per_tile"], cfg["compare.show_legs"],
                               cfg["compare.origin_y"], shrink=sheets.mount_shrink())
        canvas.alpha_composite(bg, (x, y))
        draw.text((x + 3, y - 15), f"{i:02d} {ac.compass(i, cfg['rotations.count'])}",
                  font=font, fill=(190, 196, 202, 255))
    # The SHADOW pass renders on an 11-tile canvas because a 45-degree sun runs the shadow
    # a tile east per tile of height, so a body-sized contact cell is a deliberate window
    # onto it, not a defect -- it goes in the footer without the shout. Body and mask ride
    # the compare cell exactly, and a crop there is the bug this check exists for.
    foot[-1] = cell_fit_line(cfg, cuts, needs)
    if which != "shadow" and any(any(cut) for _, cut in cuts):
        print("  WARN " + foot[-1])
    sheets.draw_footer(canvas, lay, foot)
    path, side = sheet_paths(cfg, which if which != "body" else label)
    canvas.convert("RGB").save(path)
    finish(cfg, path, side, {"sheet": label, "frames": frames})
    return path


def compare_sheet(cfg, bodydir, shadowdir, frames, passes=()):
    """Stock / jamaltron / overlay, at matched rotations, with the leg mounts on top.

    The STOCK row is base_animation (the non-rotating under-plate the legs attach to) and
    then the rotating torso over it, in Factorio's own draw order. That plate is the layer
    the mount markers land on, so leaving it out understates stock's footprint and makes
    the shark look like he has more to cover than he does -- and this sheet is where the
    shark's size gets decided. sheets.mount_selfcheck() proves the markers against it,
    every run, and the verdict goes to stdout, into the footer and into the sidecar.

    TWO MOUNT RINGS, and mixing them up is the whole reason this note exists. The
    self-check is about STOCK art, so it uses stock's own declared positions. Everything
    drawn on the JAMALTRON row -- the markers, the legs, the coverage count -- uses the
    ratio entity.lua actually ships (C.13, read out of shared.lua), because a sheet that
    marks a ring this mod no longer declares is answering a question nobody is asking.
    """
    from PIL import Image, ImageDraw
    d = ac.derived(cfg)
    ppt = d["sprite_px_per_tile"]
    cell = int(round(cfg["compare.cell_tiles"] * ppt))
    oy = cfg["compare.origin_y"]
    rows = []
    if cfg["compare.show_stock"]:
        rows.append("STOCK")
    rows += ["JAMALTRON", "OVERLAY"]

    shrink = sheets.mount_shrink()
    hw, north, south = sheets.mount_extents(ppt, shrink)
    check = sheets.mount_selfcheck()
    check_line = sheets.selfcheck_line(check)
    print("  " + check_line)
    # Measured off the cells as they are drawn, but the footer's HEIGHT has to be known
    # before the canvas exists. So the line is reserved here and filled in below; drop the
    # placeholder and the grid is laid out one line short and the text renders off-canvas.
    coverage, cuts, needs = [], [], []
    foot = footer_lines(cfg, "compare", passes) + [
        "leg mounts at %.2f of stock (C.13) span %+.0f..%+.0f px transverse, "
        "%+.0f..%+.0f px along screen (+-%.2f x %.2f..%.2f tiles); "
        "shark %.2f x %.2f tiles at scale %.3f"
        % (shrink, -hw, hw, north, south, hw / ppt, north / ppt, south / ppt,
           d["shark_length_tiles"], d["shark_width_tiles"], cfg["model.scale"]),
        check_line,
        "",   # placeholder: the shark's own coverage, measured below
        "",   # placeholder: whether the cell held him, measured below
    ]

    lay = sheets.GridLayout(cols=len(frames), rows=len(rows), cell=cell,
                            bottom=sheets.footer_height(len(foot)))
    canvas = Image.new("RGBA", (lay.width, lay.height), (26, 28, 30, 255))
    draw = ImageDraw.Draw(canvas)
    font, small = sheets._font(13), sheets._font(11)

    stock_ok = os.path.exists(sheets.STOCK_BODY["path"])
    # One frame, no rotation: crop the plate once and reuse it under every column.
    stock_base = (sheets.load_sheet_frame(sheets.STOCK_BASE, 0, cell, ppt, oy)
                  if stock_ok and os.path.exists(sheets.STOCK_BASE["path"]) else None)
    for col, i in enumerate(frames):
        x, _ = lay.cell_origin(col, 0)
        draw.text((x + 3, 6), f"{i:02d}  {ac.compass(i, cfg['rotations.count'])}",
                  font=font, fill=(206, 212, 218, 255))

        label = "%02d %s" % (i, ac.compass(i, cfg["rotations.count"]))
        jam_body, cut, need = sheets.render_frame_cell(
            bodydir / f"frame_{i:03d}.png", cell, d["body_px_per_tile"], ppt, oy,
            SPRITE_VISIBLE_ALPHA)
        cuts.append((label, cut))
        needs.append(need)
        coverage.append((label, sheets.mount_coverage(jam_body, ppt, oy, shrink=shrink)))
        jam_shadow = None
        if shadowdir is not None:
            sp = shadowdir / f"frame_{i:03d}.png"
            if sp.exists():
                jam_shadow = sheets.shadow_layer(
                    sheets.load_render_frame(sp, cell, d["shadow_px_per_tile"], ppt, oy))

        stock_body = stock_shadow = None
        if stock_ok:
            stock_body = sheets.load_sheet_frame(sheets.STOCK_BODY, i, cell, ppt, oy)
            if cfg["compare.show_shadow"]:
                stock_shadow = sheets.shadow_layer(
                    sheets.load_sheet_frame(sheets.STOCK_SHADOW, i, cell, ppt, oy))

        for r, name in enumerate(rows):
            bg = sheets.cell_background(cell, cfg["compare.background"], ppt,
                                        cfg["compare.grid"], oy)
            if name == "STOCK":
                if stock_shadow is not None:
                    bg.alpha_composite(stock_shadow)
                if stock_base is not None:
                    bg.alpha_composite(stock_base)
                if stock_body is not None:
                    bg.alpha_composite(stock_body)
            elif name == "JAMALTRON":
                if jam_shadow is not None:
                    bg.alpha_composite(jam_shadow)
                bg.alpha_composite(jam_body)
            else:
                if stock_body is not None:
                    # Ghost the FULL stock footprint, plate included -- the overlay is
                    # read as "where does stock end", and the plate is where it ends.
                    ghost = Image.new("RGBA", stock_body.size, (0, 0, 0, 0))
                    if stock_base is not None:
                        ghost.alpha_composite(stock_base)
                    ghost.alpha_composite(stock_body)
                    ghost.putalpha(ghost.getchannel("A").point(
                        lambda v: int(v * cfg["compare.stock_alpha"])))
                    bg.alpha_composite(ghost)
                if jam_shadow is not None:
                    bg.alpha_composite(jam_shadow)
                bg.alpha_composite(jam_body)
            if cfg["compare.show_mounts"]:
                sheets.draw_mounts(bg, ppt, cfg["compare.show_legs"], oy,
                                   shrink=1.0 if name == "STOCK" else shrink)
            canvas.alpha_composite(bg, lay.cell_origin(col, r))

    for r, name in enumerate(rows):
        _, y = lay.cell_origin(0, r)
        draw.text((6, y + 4), name, font=font, fill=(206, 212, 218, 255))
        note = {"STOCK": "stock plate\n+ torso",
                "JAMALTRON": "ours +\nshadow",
                "OVERLAY": "ours over\nstock ghost"}[name]
        draw.text((6, y + 22), note, font=small, fill=(130, 136, 142, 255))

    cover_line = sheets.coverage_line(coverage)
    print("  " + cover_line)
    foot[-2] = cover_line
    fit_line = cell_fit_line(cfg, cuts, needs)
    print(("  WARN " if any(any(cut) for _, cut in cuts) else "  ") + fit_line)
    foot[-1] = fit_line
    sheets.draw_footer(canvas, lay, foot)
    path, side = sheet_paths(cfg, "compare")
    canvas.convert("RGB").save(path)
    finish(cfg, path, side, {"sheet": "compare", "frames": frames, "rows": rows,
                             "mount_selfcheck": check,
                             "mount_shrink": shrink,
                             "mount_coverage": {"per_frame": coverage,
                                                "line": cover_line},
                             "cell_fit": {"cell_tiles": cfg["compare.cell_tiles"],
                                          "origin_y": cfg["compare.origin_y"],
                                          "tiles_needed": max(needs) if needs else 0.0,
                                          "cut_px": {label: list(cut)
                                                     for label, cut in cuts if any(cut)},
                                          "line": fit_line}})
    return path


def footer_lines(cfg, label, passes=()):
    """The visible half of the provenance. `passes` is what ACTUALLY rendered -- a shadow
    sheet footer that reads "EEVEE/64 samples" because those are the body knobs is a lie
    you will believe three weeks from now."""
    d = ac.derived(cfg)
    rendered = "  ".join("%s %s/%d" % (name, engine, samples)
                         for name, engine, samples in passes) or "no render pass"
    lines = [
        "jamaltron %s  config %s  %s  [%s]"
        % (label, ac.config_hash(cfg), time.strftime("%Y-%m-%d %H:%M:%S"), rendered),
        "scale %.3f -> %.2f x %.2f tiles  offset %s  rot %s  pivot %s  "
        "sun az%.0f el%.0f e%.1f amb%.2f  ssub=%s nrm=%s"
        % (cfg["model.scale"], d["shark_length_tiles"], d["shark_width_tiles"],
           cfg["model.offset"], cfg["model.rotation"], cfg["model.pivot"],
           cfg["sun.azimuth"], cfg["sun.elevation"], cfg["sun.energy"], cfg["sun.ambient"],
           cfg["render.use_subsurface"], cfg["render.use_normal_map"]),
    ]
    # THE POSE LINE, and only when there is one. A flop sheet whose footer reads like the
    # standing sheet's is a sheet you will misfile three weeks from now: at 132 px a rolled
    # thrash frame and a standing frame are not always distinguishable by eye.
    if cfg["model.action"] != pose.REST or cfg["bounce.height"]:
        clip = pose.clip_of(cfg["model.action"])
        lines.append(
            "POSE %s%s frame %d gain %.2f  reparent_head=%s  bounce %.2f tiles peak "
            "(phase %.2f, g %.1f -> %.1f of %d frames airborne)  this frame lifted %.3f "
            "tiles = %.1f px up-screen, %.1f px of shadow east"
            % (cfg["model.action"], " (%s)" % clip.action if clip else "",
               cfg["model.frame"], cfg["model.pose_gain"], cfg["model.reparent_head"],
               cfg["bounce.height"], cfg["bounce.phase"], cfg["bounce.gravity"],
               d["bounce_airtime_frames"], d["bounce_cycle_frames"], d["bounce_lift_tiles"],
               d["bounce_lift_up_screen_tiles"] * d["body_px_per_tile"],
               d["bounce_lift_tiles"] * d["light_run_east"] * d["shadow_px_per_tile"]))
    return lines


def finish(cfg, png, sidecar, extra):
    blob = ac.stamp(cfg, extra)
    sheets.stamp_png(png, blob)
    sidecar.write_text(json.dumps(blob, indent=2, sort_keys=True))


# -------------------------------------------------------------------------------- cli


def build_parser():
    p = argparse.ArgumentParser(
        prog="art.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    m = p.add_argument_group("what to make")
    m.add_argument("--preview", action="store_true",
                   help="rotations.preview frames of the body pass + a contact sheet (fast loop)")
    m.add_argument("--full", action="store_true",
                   help="all rotations.count frames of the body pass + a contact sheet")
    m.add_argument("--shadow", action="store_true",
                   help="the shadow-catcher pass (Cycles only) + a contact sheet")
    m.add_argument("--mask", action="store_true",
                   help="the runtime-tint pass (the harness, C.4b) + a contact sheet; "
                        "add --full for all rotations.count of them")
    m.add_argument("--compare", action="store_true",
                   help="jamaltron beside the stock spidertron at matched rotations, "
                        "with shadow and leg mounts. The one to look at")
    m.add_argument("--show", action="store_true", help="print the resolved config and exit")

    k = p.add_argument_group("knobs")
    k.add_argument("--config", default=None, help="config TOML (default render/jamaltron.toml)")
    k.add_argument("--set", action="append", dest="sets", metavar="key=value",
                   help="override one knob, TOML syntax: --set model.scale=0.8")
    k.add_argument("--blend", default=None, help="the .blend (or $%s)" % ac.BLEND_ENV)
    k.add_argument("--frames", default=None,
                   help="explicit frame indices, e.g. 0,8,16 (overrides the count)")

    r = p.add_argument_group("how")
    r.add_argument("--jobs", type=int, default=4, help="parallel Blender processes (default 4)")
    r.add_argument("--force", action="store_true", help="re-render even if cached")
    r.add_argument("-v", "--verbose", action="store_true", help="echo Blender's own report")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    # A typo'd knob is a user error, not a crash. A traceback buries the one line that
    # says which knob and what to type instead, and this tool is driven by typing knobs.
    try:
        cfg = ac.load(args.config, ac.parse_set(args.sets))
    except ac.ConfigError as exc:
        sys.stderr.write("art.py: %s\n" % exc)
        return 2
    if args.blend:
        cfg["model.blend"] = args.blend
    d = ac.derived(cfg)

    for w in ac.warnings(cfg):
        print("WARN " + w)

    if args.show or not (args.preview or args.full or args.shadow or args.compare
                         or args.mask):
        print(json.dumps(ac.stamp(cfg), indent=2, sort_keys=True))
        if not args.show:
            print("\nnothing to do: pass --preview, --compare, --full or --shadow "
                  "(--help for the rest)")
        return 0

    explicit = [int(x) for x in args.frames.split(",")] if args.frames else None
    print("jamaltron %s  scale %.3f -> %.2f x %.2f x %.2f tiles  offset %s  rot %s"
          % (ac.config_hash(cfg), cfg["model.scale"], d["shark_length_tiles"],
             d["shark_width_tiles"], d["shark_height_tiles"],
             cfg["model.offset"], cfg["model.rotation"]))
    if cfg["model.action"] != pose.REST or cfg["bounce.height"]:
        print("  pose %s frame %d gain %.2f  reparent_head=%s  bounce peak %.2f tiles "
              "(phase %.2f) -> this frame +%.3f tiles = %.1f px up-screen, %.1f px shadow east"
              % (cfg["model.action"], cfg["model.frame"], cfg["model.pose_gain"],
                 cfg["model.reparent_head"], cfg["bounce.height"], cfg["bounce.phase"],
                 d["bounce_lift_tiles"],
                 d["bounce_lift_up_screen_tiles"] * d["body_px_per_tile"],
                 d["bounce_lift_tiles"] * d["light_run_east"] * d["shadow_px_per_tile"]))
    made = []
    t0 = time.time()

    if args.preview or args.compare:
        frames = explicit or ac.frame_indices(
            cfg, cfg["compare.rotations"] if args.compare and not args.preview
            else cfg["rotations.preview"])
        bodydir, _ = render_pass(cfg, "body", frames, cfg["render.preview_samples"],
                                 jobs=args.jobs, force=args.force, verbose=args.verbose)
        passes = [("body", cfg["render.engine"], cfg["render.preview_samples"])]
        shadowdir = None
        if args.compare and cfg["compare.show_shadow"]:
            shadowdir, _ = render_pass(cfg, "shadow", frames, cfg["render.shadow_samples"],
                                       jobs=args.jobs, force=args.force, verbose=args.verbose)
            passes.append(("shadow", cfg["render.shadow_engine"], cfg["render.shadow_samples"]))
        if args.preview:
            made.append(contact_sheet(cfg, "body", frames, bodydir, "preview", passes[:1]))
        if args.compare:
            made.append(compare_sheet(cfg, bodydir, shadowdir, frames, passes))

    if args.full:
        frames = explicit or ac.frame_indices(cfg)
        bodydir, _ = render_pass(cfg, "body", frames, cfg["render.samples"],
                                 jobs=args.jobs, force=args.force, verbose=args.verbose)
        made.append(contact_sheet(cfg, "body", frames, bodydir, "full",
                                  [("body", cfg["render.engine"], cfg["render.samples"])]))

    if args.mask:
        # Same samples rule as the body pass, because it IS the body pass with a different
        # material: --mask alone previews, --mask --full is the sheet.
        frames = explicit or ac.frame_indices(cfg, None if args.full
                                              else cfg["rotations.preview"])
        samples = cfg["render.samples"] if args.full else cfg["render.preview_samples"]
        maskdir, _ = render_pass(cfg, "mask", frames, samples, jobs=args.jobs,
                                 force=args.force, verbose=args.verbose)
        made.append(contact_sheet(cfg, "mask", frames, maskdir, "mask",
                                  [("mask", cfg["render.engine"], samples)]))

    if args.shadow:
        frames = explicit or ac.frame_indices(cfg, cfg["rotations.preview"]
                                              if not args.full else None)
        shadowdir, _ = render_pass(cfg, "shadow", frames, cfg["render.shadow_samples"],
                                   jobs=args.jobs, force=args.force, verbose=args.verbose)
        made.append(contact_sheet(cfg, "shadow", frames, shadowdir, "shadow",
                                  [("shadow", cfg["render.shadow_engine"],
                                    cfg["render.shadow_samples"])]))

    print("TOTAL %.2fs" % (time.time() - t0))
    for p in made:
        print("  -> %s" % p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
