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

  * --preview renders 8 of the 64 directions at the SAME angles the full sheet uses, a
    strict subset, so nothing is thrown away when you commit to --full.
  * frames are cached under the hash of only the knobs that affect that pass. Change
    `compare.background` and 64 Cycles frames survive; change `model.scale` and none do.
  * --jobs runs several Blenders over disjoint frame sets. A sprite-sized tile is pure
    launch overhead for one process, and this machine has 12 performance cores.

EVERY OUTPUT IS TRACEABLE. Each sheet carries the config hash in a PNG text chunk, a visible
footer and a sidecar `.json` holding the fully resolved knobs, so a sheet found in a folder
weeks later still knows what made it.

Renders land in render-out/ (gitignored). Promoting a sheet into mod/jamaltron/graphics/
is a DELIBERATE act: that directory carries the RenderHub carve-out licence, and this tool
never writes there.
"""

# sys.path, verbatim per tools/README.md -- Python and Blender both put THIS file's own
# directory on sys.path[0], never tools/, and `package = false` means no installed `render`
# to fall back on. Cannot be a helper: importing the helper is what needs the path fixed.
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

    `output.dir` takes an absolute path (out_root()), and Path.relative_to(REPO) RAISES on
    a path outside the repo. A progress line must not throw: rendering into /tmp is how a
    timing run avoids touching the shipped cache.
    """
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def pass_dir(cfg, which: str, samples: int) -> pathlib.Path:
    """Cache directory for one pass: the hash of the knobs that change its pixels, plus
    the sample count (preview and full differ ONLY in samples, and a 16-sample frame must
    never be served as a 64-sample one)."""
    return out_root(cfg) / which / f"{ac.pass_hash(cfg, which)}_s{samples}"


def blend_path(cfg) -> pathlib.Path:
    """Where the model is. artconfig owns the resolution because it DIGESTS this file; two
    resolvers and the hash could describe a different file from the one Blender opened.
    Kept as a name here because tune.py and the render loop both call it."""
    return ac.blend_path(cfg)


def chunk(items, n):
    """Round-robin so every worker gets a mix of angles and they finish together."""
    n = max(1, min(n, len(items)))
    out = [[] for _ in range(n)]
    for i, item in enumerate(items):
        out[i % n].append(item)
    return [c for c in out if c]


def run_blender(blend, config_json, which, frames, outdir, quiet=True):
    # --python-exit-code 1: WITHOUT it a Python exception inside render_jamal exits Blender
    # with 0, so a crash after the FIX lines looked like a finished render -- no frames,
    # engine "?", and a cheerful "1 frames in 0.58s". MEASURED: a shadowed variable in
    # main() hid exactly that way.
    cmd = [BLENDER, "-b", str(blend), "--python-exit-code", "1",
           "--python", str(RENDER_SCRIPT), "--",
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

    FIX / CAM / SUN / RENDER / POSE are running commentary and belong behind `-v`. A WARN
    says the picture is wrong and is worthless if only `-v` shows it: C.5's "the posed body
    reaches 0.36 tiles BELOW the ground plane" (the one line explaining a flop whose shadow
    comes back sliced) landed in a list nobody printed, CLI and tuner both quiet.

    Deduped one level up: N jobs are N Blenders, each saying it about its own frames.
    """
    return [n for n in notes if n.startswith("WARN ")]


def render_pass(cfg, which, frames, samples, *, jobs=1, force=False, verbose=False,
                quiet=False):
    """Render the missing frames of one pass. Returns (directory, stats).

    `quiet` drops the one progress line per pass and nothing else -- a sequence renders one
    pass per FRAME, and 72 such lines bury the WARNs (which still print)."""
    outdir = pass_dir(cfg, which, samples)
    outdir.mkdir(parents=True, exist_ok=True)
    have = {i for i in frames if (outdir / f"frame_{i:03d}.png").exists()}
    todo = [i for i in frames if force or i not in have]

    # The sidecar IS the payload handed to Blender: one file, so a cached frame and its
    # config cannot drift apart.
    payload = outdir / "config.json"
    blob = ac.stamp(cfg, {"pass": which, "samples": samples, "frames": sorted(frames)})
    payload.write_text(json.dumps(blob, indent=2, sort_keys=True))

    if not todo:
        if not quiet:
            print(f"  {which:<7} {len(frames)} frames CACHED  {shorten(outdir)}")
        warn_if_clipped(cfg, outdir, frames, which)
        replay_warnings(outdir, frames)
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
    # Never trust the exit code alone: asked for N frames and wrote fewer is a failed
    # render, whatever Blender said.
    lost = [i for i in todo if not (outdir / f"frame_{i:03d}.png").exists()]
    if lost:
        raise SystemExit(f"blender reported success but wrote no frame for {lost[:8]} in "
                         f"{outdir} -- rerun with -v to see its output")

    d = ac.derived(cfg)
    ss = d["supersample"]
    final = d["shadow_resolution_px"] if which == "shadow" else d["body_resolution_px"]
    if ss > 1:
        downsample(outdir, todo, final)
    engine = (results[0][0] or {}).get("engine", "?")
    size = f"{final}px" if ss == 1 else f"{final}px (rendered {final * ss}, x{ss} SS)"
    if not quiet:
        print(f"  {which:<7} {len(todo)} frames in {wall:6.2f}s  "
              f"({wall / len(todo):.2f}s/frame, {engine}, {samples} samples, {size}, "
              f"{len(groups)} job{'s' if len(groups) > 1 else ''})  "
              f"{shorten(outdir)}")
    warn_if_clipped(cfg, outdir, frames, which)
    stats = {"seconds": wall, "rendered": len(todo), "cached": len(frames) - len(todo),
             "engine": engine, "jobs": len(groups)}
    # THE POSED BOX, unioned over every Blender that ran. artconfig.derived() reports the
    # REST box off a measured constant: right for the standing shark, wrong once he
    # thrashes. C.17 needs the real one, as does anyone pricing the bounce.
    boxes = [r[0]["box_tiles"] for r in results if (r[0] or {}).get("box_tiles")]
    if boxes:
        stats["box_tiles"] = [[min(b[k][0] for b in boxes), max(b[k][1] for b in boxes)]
                              for k in range(3)]
    # The renderer's own warnings, once each. -v has already printed every note per job.
    if not verbose:
        for w in dict.fromkeys(w for r in results for w in warn_notes(r[1])):
            print("   " + w)
    record_warnings(outdir, [(g, warn_notes(r[1])) for g, r in zip(groups, results)])
    # A partial hit: the cached frames' caveats, minus any the fresh chunk just printed --
    # the standing shark's burial is the same sentence on every frame, and replaying it
    # (tagged with its frames) beside the fresh copy would show it twice in the tuner's
    # warning box.
    fresh = {w for r in results for w in warn_notes(r[1])}
    replay_warnings(outdir, [i for i in frames if i not in todo], skip=fresh)
    for r in results:
        for m in (r[0] or {}).get("clip_mismatches", ()):
            print("  WARN clip table vs the model: " + m)
    return outdir, stats


#: Where a pass directory keeps the WARN lines its frames were rendered with.
WARNINGS_FILE = "warnings.json"

#: How render_jamal opens the clip-table WARN, which record_warnings deliberately drops.
CLIP_TABLE_WARN = "WARN clip table vs the model"


def record_warnings(outdir, groups) -> None:
    """Keep each render's WARN lines beside the frames they are about (C.23).

    A WARN is something only a render can know (the posed body under the floor, the clip
    table drifting from the model), and it used to print once, on the cold render; the
    identical command re-run came out of the cache silent, exactly when somebody re-runs it
    to look at the problem. So every frame a process rendered is filed under that process's
    warnings (a Blender warns about its whole chunk, so attribution is per chunk, never
    finer), a re-render replaces a frame's entry and a clean re-render clears it.

    NOT the clip-table check: it describes pose.py against the model, not these frames, and
    the table is deliberately outside every hash (pose.table_digest), so after a table fix
    the frames stay cached and a recorded mismatch would replay a fixed problem. Every cold
    posed render re-checks the table anyway.
    """
    path = pathlib.Path(outdir) / WARNINGS_FILE
    try:
        book = json.loads(path.read_text())
    except (OSError, ValueError):
        book = {}
    for frames, warns in groups:
        keep = [w for w in warns if not w.startswith(CLIP_TABLE_WARN)]
        for i in frames:
            book[str(i)] = keep
    book = {k: v for k, v in book.items() if v}
    if book:
        path.write_text(json.dumps(book, indent=1, sort_keys=True))
    elif path.exists():
        path.unlink()


def replay_warnings(outdir, frames, skip=()) -> list:
    """Print, and return, the recorded WARNs for frames this run served from the cache.

    Printed as ordinary `WARN` lines (the tuner lifts anything starting with WARN into its
    warning box) with the frames named, so a cached picture carries the cold render's
    caveat."""
    try:
        book = json.loads((pathlib.Path(outdir) / WARNINGS_FILE).read_text())
    except (OSError, ValueError):
        return []
    by_warn = {}
    for i in frames:
        for w in book.get(str(i), ()):
            if w not in skip:
                by_warn.setdefault(w, []).append(i)
    out = []
    for w, hit in by_warn.items():
        line = "%s  [cached frame%s %s]" % (w, "s" if len(hit) > 1 else "",
                                             ",".join(str(i) for i in sorted(hit)))
        print("   " + line)
        out.append(line)
    return out


#: Knob to turn when a pass runs out of canvas, per pass.
CANVAS_KNOB = {"body": "camera.canvas_tiles", "shadow": "camera.shadow_canvas_tiles"}


#: Alpha at which a pixel IS PART OF THE SPRITE, because Factorio DRAWS it: the engine
#: composites with the PNG's alpha, so an alpha-1 pixel is faint, not absent. Every "how
#: big is he" or "did a crop cut him" question (the packer's frame box, the refusals around
#: it, the compare cell's crop check) is asked at THIS number.
#:
#: It used to be 8, which is how C.4 shipped a shark with his tail fin sliced off: the fin
#: tip's antialiasing ramp does not clear alpha 8, so it was measured OUT of the box meant to
#: contain it, and the cut-sprite gate read the same thresholded mask and agreed nothing was
#: wrong. The faint pixels were visible in game; he was clipped at the frame edge in dir 16
#: and 48.
SPRITE_VISIBLE_ALPHA = 1

#: Alpha below which a Cycles SHADOW-CATCHER frame is SAMPLING NOISE, not shadow. A claim
#: about what the renderer scattered, not what is visible: MEASURED on a 704 px shadow
#: frame, the alpha>=1 bbox is the whole canvas (9537 noise pixels) while the alpha>=8 bbox
#: is (271,318)-(513,386), the shadow. pack.py ZEROES everything under this in the shadow
#: sheets it writes BEFORE measuring them, so both thresholds agree on the pixels that ship.
RENDER_NOISE_FLOOR = 8

#: Per PASS, what counts as sprite in a RAW render. Body and mask are transparent-film
#: renders whose alpha IS the subject's coverage (MEASURED on the shipped 64-frame body
#: pass: the alpha>=1 union is one pixel wider per side than alpha>=8, no stray alpha
#: elsewhere), so the visible threshold is honest there. A raw shadow frame is noise edge
#: to edge; the visible question reports every frame clipped every run, and the warning
#: stops meaning anything.
PASS_ALPHA_FLOOR = {"shadow": RENDER_NOISE_FLOOR}


def pass_alpha_floor(which: str) -> int:
    """What counts as sprite in a raw `which`-pass frame. One lookup, so no caller picks
    the noise floor for a body frame by accident."""
    return PASS_ALPHA_FLOOR.get(which, SPRITE_VISIBLE_ALPHA)


def warn_if_clipped(cfg, outdir, frames, which, floor: int | None = None):
    """Shout when the render ran out of canvas. Measured off the alpha, every run.

    A clipped frame does not look broken, it looks like a shark with a flat dorsal fin, and
    you spend twenty minutes on the LIGHTING before noticing the canvas. At the VISIBLE
    threshold (the default, per pass) the shipped 6-tile body canvas holds scale 0.81 with
    12 px (0.19 tiles) to spare at the SIDES, frames 16 and 48, the broadside pair; scaled
    off that margin the first cut lands just under 0.86. At alpha >= 8 the same canvas
    looked good to 0.87, a pixel of margin per side that is not actually empty. Either way
    it is one nudge of the scale slider, so this runs on every pass.

    Runs on cached frames too: the second run at a too-big scale is the one where you have
    forgotten, and a cache-miss-only warning is never seen.
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

    The render canvas has warned since C.10; the cell it is composited into did not, and a
    too-small cell crops the sprite silently (it reads as a tight crop, not a bug). That is
    the worst failure for THIS image, where scale, pivot and offset are decided against the
    cropped picture. So the verdict goes on stdout AND in the footer, good news or bad, like
    the mount self-check.
    """
    have, oy = cfg["compare.cell_tiles"], cfg["compare.origin_y"]
    # Rounded UP to the printed precision: 0.01 tiles is 0.64 px, and a pasted
    # recommendation that still crops half a pixel is worse than none.
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
    """Supersampled frames -> the STAMPED size, Lanczos. Here, not in Blender, because
    Blender has no Pillow.

    Resizes to the derived target, not width // factor, so the file on disk and its
    sidecar's resolution cannot disagree by a rounding."""
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
    # Reserved, filled once the cells are measured -- without the placeholder the grid is
    # laid out one line short and the text renders off-canvas.
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
                               cfg["compare.origin_y"], shrink=sheets.mount_shrink(),
                               lift=sheets.mount_lift())
        canvas.alpha_composite(bg, (x, y))
        draw.text((x + 3, y - 15), f"{i:02d} {ac.compass(i, cfg['rotations.count'])}",
                  font=font, fill=(190, 196, 202, 255))
    # The SHADOW pass renders on an 11-tile canvas (a 45-degree sun runs the shadow a tile
    # east per tile of height), so a body-sized contact cell is a deliberate window onto
    # it: footer only, no shout. Body and mask ride the compare cell exactly, and a crop
    # there is the bug this check exists for.
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

    The STOCK row is base_animation (the non-rotating under-plate the legs attach to) with
    the rotating torso over it, in Factorio's draw order. The mount markers land on that
    plate, so leaving it out understates stock's footprint and makes the shark look like he
    has more to cover -- on the sheet where his size is decided. sheets.mount_selfcheck()
    proves the markers against it every run; the verdict goes to stdout, the footer and the
    sidecar.

    TWO MOUNT RINGS, do not mix them up. The self-check is about STOCK art, so it uses
    stock's declared positions. Everything on the JAMALTRON row (markers, legs, coverage
    count) uses the ratio and lift entity.lua ships (C.13 and C.27, read out of shared.lua);
    marking stock's ring on that row would answer a question nobody is asking.
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

    shrink, lift = sheets.mount_shrink(), sheets.mount_lift()
    hw, north, south = sheets.mount_extents(ppt, shrink, lift)
    check = sheets.mount_selfcheck()
    check_line = sheets.selfcheck_line(check)
    print("  " + check_line)
    # Measured off the cells as drawn, but the footer's HEIGHT must be known before the
    # canvas exists, so the lines are reserved here and filled below (without the
    # placeholders the grid is one line short and the text renders off-canvas).
    coverage, cuts, needs = [], [], []
    foot = footer_lines(cfg, "compare", passes) + [
        "leg mounts at %.2f of stock (C.13), lifted %.3f tiles (C.27), span %+.0f..%+.0f px "
        "transverse, %+.0f..%+.0f px along screen (+-%.2f x %.2f..%.2f tiles); "
        "shark %.2f x %.2f tiles at scale %.3f"
        % (shrink, lift, -hw, hw, north, south, hw / ppt, north / ppt, south / ppt,
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
        coverage.append((label, sheets.mount_coverage(jam_body, ppt, oy, shrink=shrink,
                                                      lift=lift)))
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
                    # Ghost the FULL stock footprint, plate included: the overlay answers
                    # "where does stock end", and the plate is where it ends.
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
                stock = name == "STOCK"
                sheets.draw_mounts(bg, ppt, cfg["compare.show_legs"], oy,
                                   shrink=1.0 if stock else shrink,
                                   lift=0.0 if stock else lift)
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
                             "mount_lift": lift,
                             "mount_coverage": {"per_frame": coverage,
                                                "line": cover_line},
                             "cell_fit": {"cell_tiles": cfg["compare.cell_tiles"],
                                          "origin_y": cfg["compare.origin_y"],
                                          "tiles_needed": max(needs) if needs else 0.0,
                                          "cut_px": {label: list(cut)
                                                     for label, cut in cuts if any(cut)},
                                          "line": fit_line}})
    return path


# ---------------------------------------------------------------------- C.21 sequence

#: The three passes a sequence sheet CAN ship, and the samples knob each renders at. Body and
#: mask follow --preview like --full does; the shadow has one sample count either way. Which
#: ones a sequence renders is ITS call (sequence.Sequence.passes): the beached flop ships no
#: mask, so --sequence never launches a mask Blender for it.
SEQUENCE_PASSES = (("body", "render.samples", "render.preview_samples"),
                   ("mask", "render.samples", "render.preview_samples"),
                   ("shadow", "render.shadow_samples", "render.shadow_samples"))

#: GIF delays are whole CENTISECONDS, so 24 fps (41.67 ms) cannot be one number. Five frames
#: at 40 ms and one at 50 average exactly 41.67 (the tuner's and the game's tempo), with an
#: invisible 10 ms wobble once every quarter second.
GIF_DELAYS_MS = (40, 40, 40, 40, 40, 50)


def sequence_samples(cfg, which: str, preview: bool) -> int:
    """Samples one pass of a sequence renders at. pack.py reads the same answer."""
    full, quick = next((f, q) for w, f, q in SEQUENCE_PASSES if w == which)
    return cfg[quick if preview else full]


def render_sequence(seq, *, preview=False, jobs=4, force=False, verbose=False) -> dict:
    """Every unique config of a C.21 sequence, at its one direction, through every pass it
    ships (seq.passes -- all three unless its [sequence] table says otherwise).

    ONE BLENDER PER FRAME PER PASS, the cost of one frame = one config = one hash: a pass
    cannot render two configs. So the parallelism is ACROSS configs (`jobs` Blenders at
    once, one frame each), not across directions as a wheel renders. Everything lands in
    the ordinary per-config cache, so frames the tuner already rendered at this direction
    are served from it, and pack.py finds them by the same pass_dir() rule.
    """
    t0 = time.time()
    passes = [which for which, _, _ in SEQUENCE_PASSES if which in seq.passes]
    tasks = [(k, cfg, which) for k, cfg in enumerate(seq.configs) for which in passes]
    stats = {which: {"rendered": 0, "cached": 0} for which in passes}

    def one(task):
        k, cfg, which = task
        _, st = render_pass(cfg, which, [seq.direction], sequence_samples(cfg, which, preview),
                            jobs=1, force=force, verbose=verbose, quiet=True)
        return which, st

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for which, st in pool.map(one, tasks):
            stats[which]["rendered"] += st["rendered"]
            stats[which]["cached"] += st["cached"]
    for which, st in stats.items():
        print(f"  {which:<7} {len(seq.configs)} frames: {st['rendered']} rendered, "
              f"{st['cached']} cached")
    stats["seconds"] = time.time() - t0
    return stats


def sequence_gif(seq, *, preview=False):
    """The whole cycle as an animated GIF at 24 fps: shadow under body over the compare
    ground, one frame per PLAYED frame, labelled with its beat. Returns the path.

    THIS is how to watch a flop that is more than one clip. The tuner plays one clip's loop;
    a sequence is several clips, holds and ramps, and the seams between beats are what
    needs watching. Same pixels the pack gathers, in Factorio's play order.

    The two passes render on different canvases (6 and 11 tiles, same px-per-tile), so both
    are placed on the shadow's canvas by their shared ORIGIN PIXEL, then the stack is cropped
    to the union of everything visible across the cycle -- one box, so only he moves.
    """
    from PIL import Image, ImageDraw
    base = seq.configs[0]
    d = ac.derived(base)
    body_px, shadow_px = d["body_resolution_px"], d["shadow_resolution_px"]
    off = int(round(fc.origin_pixel(shadow_px) - fc.origin_pixel(body_px)))
    frame_name = f"frame_{seq.direction:03d}.png"
    cells = []
    for cfg in seq.configs:
        body = Image.open(pass_dir(cfg, "body", sequence_samples(cfg, "body", preview))
                          / frame_name).convert("RGBA")
        shadow = Image.open(pass_dir(cfg, "shadow", sequence_samples(cfg, "shadow", preview))
                            / frame_name).convert("RGBA")
        shadow = shadow.copy()      # the noise-floor surgery below writes its alpha
        alpha = shadow.getchannel("A").point(lambda v: v if v >= RENDER_NOISE_FLOOR else 0)
        shadow.putalpha(alpha)
        layer = Image.new("RGBA", (shadow_px, shadow_px), (0, 0, 0, 0))
        layer.alpha_composite(sheets.shadow_layer(shadow))
        layer.alpha_composite(body, (off, off))
        cells.append(layer)
    box = None
    for cell in cells:
        b = cell.getchannel("A").point(lambda v: 255 if v >= SPRITE_VISIBLE_ALPHA else 0).getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]),
                                         max(box[2], b[2]), max(box[3], b[3]))
    pad = 12
    box = (max(0, box[0] - pad), max(0, box[1] - pad),
           min(shadow_px, box[2] + pad), min(shadow_px, box[3] + pad))
    strip = 18
    font = sheets._font(12)
    ground = tuple(base["compare.background"]) + (255,)
    frames = []
    for n, (k, (beat, f)) in enumerate(zip(seq.order, seq.played)):
        w, h = box[2] - box[0], box[3] - box[1]
        out = Image.new("RGBA", (w, h + strip), ground)
        out.alpha_composite(cells[k].crop(box))
        ImageDraw.Draw(out).text(
            (4, h + 3), "%-7s f%-2d  %3d/%d  %.2fs  %s"
            % (beat, f, n + 1, len(seq.order), n / pose.FPS, ac.config_hash(seq.configs[k])),
            font=font, fill=(206, 212, 218, 255))
        frames.append(out.convert("RGB"))
    root = out_root(base) / "sheets"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"sequence_{seq.name}_{seq.digest}.gif"
    delays = [GIF_DELAYS_MS[i % len(GIF_DELAYS_MS)] for i in range(len(frames))]
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=delays, loop=0)
    path.with_suffix(".json").write_text(json.dumps({
        "sequence": seq.name, "digest": seq.digest, "direction": seq.direction,
        "fps": pose.FPS, "played": [list(x) for x in seq.played], "order": list(seq.order),
        "frame_hashes": list(seq.hashes), "preview_samples": preview,
    }, indent=1))
    return path


def footer_lines(cfg, label, passes=()):
    """The visible half of the provenance. `passes` is what ACTUALLY rendered -- a shadow
    sheet footer reading "EEVEE/64 samples" because those are the body knobs is a lie you
    will believe weeks later."""
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
    # THE POSE LINE, only when there is one. A flop sheet whose footer reads like the
    # standing sheet's gets misfiled: at 132 px a rolled thrash frame and a standing frame
    # are not always distinguishable by eye.
    if cfg["model.action"] != pose.REST or cfg["bounce.height"]:
        clip = pose.clip_of(cfg["model.action"])
        # TWO lines: the draw does not wrap, and at one line the broadside sheet (the flop
        # preset's, 1250 px) cut the shadow-east figure, the one number the bounce is for.
        lines.append(
            "POSE %s%s frame %d gain %.2f phase_lock %.2f  reparent_head=%s  ground_contact=%s"
            % (cfg["model.action"], " (%s)" % clip.action if clip else "",
               cfg["model.frame"], cfg["model.pose_gain"], cfg["model.phase_lock"],
               cfg["model.reparent_head"], cfg["model.ground_contact"]))
        # Its own line for the same reason: the bone list alone runs 27 characters.
        if bedding_note(cfg):
            lines.append("BED" + bedding_note(cfg))
        lines.append(
            "BOUNCE %.2f tiles peak (phase %.2f, g %.1f -> %.1f of %d frames airborne)  this "
            "frame lifted %.3f tiles = %.1f px up-screen, %.1f px of shadow east"
            % (cfg["bounce.height"], cfg["bounce.phase"], cfg["bounce.gravity"],
               d["bounce_airtime_frames"], d["bounce_cycle_frames"], d["bounce_lift_tiles"],
               d["bounce_lift_up_screen_tiles"] * d["body_px_per_tile"],
               d["bounce_lift_tiles"] * d["light_run_east"] * d["shadow_px_per_tile"]))
    return lines


def bedding_note(cfg) -> str:
    """C.5.6's four knobs as a suffix for the pose lines, or "" while all sit at default --
    the standing shark's lines stay exactly as they were."""
    if not (ac.bedded_in(cfg) or cfg["model.fin_fold"] or cfg["model.spine_sag"]):
        return ""
    return "  ignore=%s sink %.3f fin_fold %.0f%s spine_sag %.1f" % (
        "/".join(cfg["model.ground_ignore"]) or "-", cfg["model.ground_sink"],
        cfg["model.fin_fold"], " (floor)" if cfg["model.fin_floor"] else "",
        cfg["model.spine_sag"])


def pose_log_line(cfg, d) -> str:
    """The one-line pose summary main() prints, or "" for a standing, grounded config. A
    function so the format string is tested: a placeholder count drifting from its
    arguments is a TypeError that only fires on POSED renders."""
    if cfg["model.action"] == pose.REST and not cfg["bounce.height"]:
        return ""
    return ("  pose %s frame %d gain %.2f phase_lock %.2f  reparent_head=%s  "
            "ground_contact=%s%s  bounce peak %.2f tiles (phase %.2f) -> this frame +%.3f tiles "
            "= %.1f px up-screen, %.1f px shadow east"
            % (cfg["model.action"], cfg["model.frame"], cfg["model.pose_gain"],
               cfg["model.phase_lock"], cfg["model.reparent_head"],
               cfg["model.ground_contact"], bedding_note(cfg), cfg["bounce.height"],
               cfg["bounce.phase"],
               d["bounce_lift_tiles"],
               d["bounce_lift_up_screen_tiles"] * d["body_px_per_tile"],
               d["bounce_lift_tiles"] * d["light_run_east"] * d["shadow_px_per_tile"]))


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
    m.add_argument("--sequence", action="store_true",
                   help="the config's [sequence] (C.21): every unique frame through the passes "
                        "it ships (body, mask, shadow unless [sequence] passes says less) at "
                        "its one direction, then an animated GIF of the whole cycle at 24 "
                        "fps. Add --preview for preview samples")
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
    # A typo'd knob is a user error, not a crash: a traceback buries the one line saying
    # which knob and what to type instead.
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

    if args.sequence:
        return run_sequence(args, cfg)

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
    line = pose_log_line(cfg, d)
    if line:
        print(line)
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
        # Same samples rule as the body pass (it IS the body pass with a different
        # material): --mask alone previews, --mask --full is the sheet.
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


def run_sequence(args, cfg) -> int:
    """`--sequence`: render a config's [sequence] and write the GIF. cfg is the file's own
    resolved knobs (--set and --blend applied), which every beat inherits."""
    from render import sequence
    try:
        table = ac.load_sequence(args.config)
        if table is None:
            sys.stderr.write("art.py: %s has no [sequence] table -- that lives in "
                             "render/beached.toml (C.21)\n" % (args.config or "jamaltron.toml"))
            return 2
        seq = sequence.parse(table, cfg)
    except ac.ConfigError as exc:
        sys.stderr.write("art.py: %s\n" % exc)
        return 2
    print("jamaltron sequence %s  %s  %s samples"
          % (seq.name, seq.digest, "preview" if args.preview else "full"))
    for line in sequence.describe(seq):
        print(line)
    for w in dict.fromkeys(w for c in seq.configs for w in ac.warnings(c)):
        print("WARN " + w)
    t0 = time.time()
    render_sequence(seq, preview=args.preview, jobs=args.jobs, force=args.force,
                    verbose=args.verbose)
    gif = sequence_gif(seq, preview=args.preview)
    print("TOTAL %.2fs" % (time.time() - t0))
    print("  -> %s" % gif)
    print("  watch it: open -a Safari %s   (or Quick Look: qlmanage -p ...)" % shorten(gif))
    return 0


if __name__ == "__main__":
    sys.exit(main())
