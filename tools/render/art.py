#!/usr/bin/env python3
"""The C.10 art-iteration harness. Change a knob, look at a picture, repeat.

    uv run --directory tools python render/art.py --preview     # 8 rotations, seconds
    uv run --directory tools python render/art.py --compare     # THE image to look at
    uv run --directory tools python render/art.py --full        # the real 64
    uv run --directory tools python render/art.py --shadow      # shadow-only pass
    uv run --directory tools python render/art.py --show        # print resolved knobs

    ... --set model.scale=0.85 --set 'model.rotation=[0,6,0]'   # try before you commit
    ... --blend /path/to/HAMMERHEAD.blend                       # or $JAMALTRON_BLEND

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

# sys.path, and a TRAP that tools/README.md's two-line idiom does not cover. Python (and
# Blender) put THIS file's directory on sys.path[0], and this directory contains
# render/inspect.py -- which SHADOWS the standard library's `inspect`, so importing
# dataclasses (which imports inspect) pulls in a module that does `import bpy` and dies.
# Drop the render dir from the path entirely and put tools/ on instead; every import here
# goes through the `render.` package, so nothing needs it.
import pathlib, sys  # noqa: E401
_HERE = pathlib.Path(__file__).resolve().parent
sys.path[:] = [p for p in sys.path if pathlib.Path(p or ".").resolve() != _HERE]
sys.path.insert(0, str(_HERE.parent))

import argparse  # noqa: E402
import concurrent.futures  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402

from render import artconfig as ac  # noqa: E402
from render import factorio_camera as fc  # noqa: E402
from render import sheets  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
RENDER_SCRIPT = pathlib.Path(__file__).resolve().parent / "render_jamal.py"


# --------------------------------------------------------------------------- plumbing


def out_root(cfg) -> pathlib.Path:
    p = pathlib.Path(cfg["output.dir"])
    return p if p.is_absolute() else REPO / p


def pass_dir(cfg, which: str, samples: int) -> pathlib.Path:
    """Cache directory for one pass. Named by the hash of the knobs that change its
    pixels, plus the sample count -- preview and full differ ONLY in samples, and a
    16-sample frame must never be served as a 64-sample one."""
    return out_root(cfg) / which / f"{ac.pass_hash(cfg, which)}_s{samples}"


def blend_path(cfg) -> pathlib.Path:
    p = pathlib.Path(os.path.expanduser(cfg["model.blend"]))
    return p if p.is_absolute() else REPO / p


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
        elif line.startswith(("FIX ", "CHECK ", "CAM ", "SUN ", "RENDER ", "WARN ")):
            notes.append(line.rstrip())
    if not quiet:
        for n in notes:
            print("   " + n)
    return result, notes


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
        print(f"  {which:<7} {len(frames)} frames CACHED  {outdir.relative_to(REPO)}")
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
    ss = max(1, cfg["render.supersample"])
    if ss > 1:
        downsample(outdir, todo, ss)
    engine = (results[0][0] or {}).get("engine", "?")
    print(f"  {which:<7} {len(todo)} frames in {wall:6.2f}s  "
          f"({wall / len(todo):.2f}s/frame, {engine}, {samples} samples, "
          f"{d['shadow_resolution_px'] if which == 'shadow' else d['body_resolution_px']}px, "
          f"{len(groups)} job{'s' if len(groups) > 1 else ''})  "
          f"{outdir.relative_to(REPO)}")
    return outdir, {"seconds": wall, "rendered": len(todo), "cached": len(frames) - len(todo),
                    "engine": engine, "jobs": len(groups)}


def downsample(outdir, frames, factor):
    """Supersampled frames -> final size, Lanczos. Done here and not in Blender because
    Blender has no Pillow and the uv side does."""
    from PIL import Image
    for i in frames:
        p = outdir / f"frame_{i:03d}.png"
        img = Image.open(p)
        img.resize((img.width // factor, img.height // factor), Image.LANCZOS).save(p)


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
    lay = sheets.GridLayout(cols=cols, rows=rows, cell=cell, left=10, top=22, bottom=34)
    canvas = Image.new("RGBA", (lay.width, lay.height), (26, 28, 30, 255))
    draw = ImageDraw.Draw(canvas)
    font = sheets._font(12)
    for n, i in enumerate(frames):
        col, row = n % cols, n // cols
        x, y = lay.cell_origin(col, row)
        bg = sheets.cell_background(cell, cfg["compare.background"],
                                    d["sprite_px_per_tile"], cfg["compare.grid"],
                                    cfg["compare.origin_y"])
        frame = sheets.load_render_frame(bodydir / f"frame_{i:03d}.png", cell, ppt,
                                         d["sprite_px_per_tile"], cfg["compare.origin_y"])
        bg.alpha_composite(frame)
        if cfg["compare.show_mounts"]:
            sheets.draw_mounts(bg, d["sprite_px_per_tile"], cfg["compare.show_legs"],
                               cfg["compare.origin_y"])
        canvas.alpha_composite(bg, (x, y))
        draw.text((x + 3, y - 15), f"{i:02d} {ac.compass(i, cfg['rotations.count'])}",
                  font=font, fill=(190, 196, 202, 255))
    sheets.draw_footer(canvas, lay, footer_lines(cfg, label, passes))
    path, side = sheet_paths(cfg, which if which != "body" else label)
    canvas.convert("RGB").save(path)
    finish(cfg, path, side, {"sheet": label, "frames": frames})
    return path


def compare_sheet(cfg, bodydir, shadowdir, frames, passes=()):
    """Stock / jamaltron / overlay, at matched rotations, with the leg mounts on top."""
    from PIL import Image, ImageDraw
    d = ac.derived(cfg)
    ppt = d["sprite_px_per_tile"]
    cell = int(round(cfg["compare.cell_tiles"] * ppt))
    oy = cfg["compare.origin_y"]
    rows = []
    if cfg["compare.show_stock"]:
        rows.append("STOCK")
    rows += ["JAMALTRON", "OVERLAY"]
    lay = sheets.GridLayout(cols=len(frames), rows=len(rows), cell=cell)
    canvas = Image.new("RGBA", (lay.width, lay.height), (26, 28, 30, 255))
    draw = ImageDraw.Draw(canvas)
    font, small = sheets._font(13), sheets._font(11)

    stock_ok = os.path.exists(sheets.STOCK_BODY["path"])
    for col, i in enumerate(frames):
        x, _ = lay.cell_origin(col, 0)
        draw.text((x + 3, 6), f"{i:02d}  {ac.compass(i, cfg['rotations.count'])}",
                  font=font, fill=(206, 212, 218, 255))

        jam_body = sheets.load_render_frame(bodydir / f"frame_{i:03d}.png", cell,
                                            d["body_px_per_tile"], ppt, oy)
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
                if stock_body is not None:
                    bg.alpha_composite(stock_body)
            elif name == "JAMALTRON":
                if jam_shadow is not None:
                    bg.alpha_composite(jam_shadow)
                bg.alpha_composite(jam_body)
            else:
                if stock_body is not None:
                    ghost = stock_body.copy()
                    ghost.putalpha(ghost.getchannel("A").point(
                        lambda v: int(v * cfg["compare.stock_alpha"])))
                    bg.alpha_composite(ghost)
                if jam_shadow is not None:
                    bg.alpha_composite(jam_shadow)
                bg.alpha_composite(jam_body)
            if cfg["compare.show_mounts"]:
                sheets.draw_mounts(bg, ppt, cfg["compare.show_legs"], oy)
            canvas.alpha_composite(bg, lay.cell_origin(col, r))

    for r, name in enumerate(rows):
        _, y = lay.cell_origin(0, r)
        draw.text((6, y + 4), name, font=font, fill=(206, 212, 218, 255))
        note = {"STOCK": "shipped\nspidertron",
                "JAMALTRON": "ours +\nshadow",
                "OVERLAY": "ours over\nstock ghost"}[name]
        draw.text((6, y + 22), note, font=small, fill=(130, 136, 142, 255))

    hw, north, south = sheets.mount_extents(ppt)
    sheets.draw_footer(canvas, lay, footer_lines(cfg, "compare", passes) + [
        "leg mounts span %+.0f..%+.0f px transverse, %+.0f..%+.0f px along screen "
        "(+-%.2f x %.2f..%.2f tiles); shark %.2f x %.2f tiles at scale %.3f"
        % (-hw, hw, north, south, hw / ppt, north / ppt, south / ppt,
           d["shark_length_tiles"], d["shark_width_tiles"], cfg["model.scale"])])
    path, side = sheet_paths(cfg, "compare")
    canvas.convert("RGB").save(path)
    finish(cfg, path, side, {"sheet": "compare", "frames": frames, "rows": rows})
    return path


def footer_lines(cfg, label, passes=()):
    """The visible half of the provenance. `passes` is what ACTUALLY rendered -- a shadow
    sheet footer that reads "EEVEE/64 samples" because those are the body knobs is a lie
    you will believe three weeks from now."""
    d = ac.derived(cfg)
    rendered = "  ".join("%s %s/%d" % (name, engine, samples)
                         for name, engine, samples in passes) or "no render pass"
    return [
        "jamaltron %s  config %s  %s  [%s]"
        % (label, ac.config_hash(cfg), time.strftime("%Y-%m-%d %H:%M:%S"), rendered),
        "scale %.3f -> %.2f x %.2f tiles  offset %s  rot %s  pivot %s  "
        "sun az%.0f el%.0f e%.1f amb%.2f  ssub=%s nrm=%s"
        % (cfg["model.scale"], d["shark_length_tiles"], d["shark_width_tiles"],
           cfg["model.offset"], cfg["model.rotation"], cfg["model.pivot"],
           cfg["sun.azimuth"], cfg["sun.elevation"], cfg["sun.energy"], cfg["sun.ambient"],
           cfg["render.use_subsurface"], cfg["render.use_normal_map"]),
    ]


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
    cfg = ac.load(args.config, ac.parse_set(args.sets))
    if args.blend:
        cfg["model.blend"] = args.blend
    d = ac.derived(cfg)

    for w in ac.warnings(cfg):
        print("WARN " + w)

    if args.show or not (args.preview or args.full or args.shadow or args.compare):
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
