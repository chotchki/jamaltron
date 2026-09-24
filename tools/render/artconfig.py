"""Every render knob, in one place, with a schema that rejects typos.

This is the C.10 art-iteration harness's spine: `jamaltron.toml` holds the knobs,
this module resolves them, validates them and hashes them. Stdlib only (`tomllib`
is stdlib on 3.11, which is both uv's pin and Blender 4.4.3's bundled CPython), so
it imports on BOTH sides of the Blender boundary and unit-tests with Blender
nowhere in the loop -- same split tools/README.md already enforces.

WHY TOML AND NOT JSON. The requirement is that every knob carries a comment saying
what it defaults to and what it does to the picture. JSON has no comments, so a
commented JSON config is either a lie (a `_comment` key nobody reads) or a custom
parser. TOML comments are free, `tomllib` is stdlib on the exact Python both sides
already run, and a one-line diff in a TOML file is the cleanest possible review
artifact. The resolved config still crosses the Blender boundary as JSON, because
that boundary is a `--` argv payload and JSON is what argv payloads should be.

THREE THINGS THIS BUYS BEYOND "a settings file":

 1. UNKNOWN KEYS ARE ERRORS. A typo'd knob that silently does nothing is the worst
    possible outcome for a tool whose whole job is "change one number, look at the
    picture" -- you would spend the morning tweaking a key the renderer never reads.
 2. PER-PASS HASHES. Each knob declares which render passes it affects. Changing
    `compare.background` does not invalidate 64 cached body frames; changing
    `model.scale` invalidates everything. That is what makes re-running after a
    one-knob change cheap. The declarations are not the whole key, because they
    cannot be: `render.resolution_px` lets a body knob move the shadow pass's
    resolution, so each pass also hashes the derived numbers it renders with
    (PASS_DERIVED). A cache key that misses a dependency serves stale pixels, which
    is the one failure mode a caching harness must not have.
 3. PROVENANCE. `config_hash()` over the fully resolved config is stamped into every
    PNG and written as a sidecar, so a sheet is always traceable back to its knobs.
    The hash is over the config's HASHABLE form (`hashable()`), which is the resolved
    knobs with `model.blend` replaced by a digest of the file's CONTENT. Hashing the
    path made the stamp a fact about one machine's filesystem -- three copies of the
    same .blend gave three hashes for identical pixels, and none of them reproduced
    anywhere else. The digest also keeps a private scratch path out of a PNG that
    ships in a public repo. A stamp read back off a sheet re-hashes to the hash it
    claims, on any machine, which is the promise the word provenance was making.
    ONE DELIBERATE HOLE, and it is the only one: a knob added after art shipped is
    left OUT of the hash while it sits at a default that is an exact no-op, so the
    schema can grow without re-dating pixels that did not move. See ADDITIVE.

Constants are NOT forked from render/factorio_camera.py -- the defaults for camera
pitch, sprite scale and sun geometry are read out of that module at import time, so
there is exactly one place the derived 45-degree camera lives. `render/pose.py` is read
the same way for the clip ids `model.action` accepts.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import math
import os
import pathlib
import sys

# sys.path, verbatim per tools/README.md -- Python and Blender both put THIS file's own
# directory on sys.path[0], never tools/, and `package = false` means there is no installed
# `render` to fall back on.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from render import factorio_camera as fc  # noqa: E402
from render import pose  # noqa: E402

#: Where the shipped config lives. Committed; the model it points at is not.
DEFAULT_CONFIG_PATH = pathlib.Path(__file__).resolve().parent / "jamaltron.toml"

#: Repo root. A relative `model.blend` resolves against it, the same way art.py's
#: renderer does -- and it has to be the same way, or the digest describes a different
#: file from the one Blender opened.
REPO = pathlib.Path(__file__).resolve().parents[2]

#: Render passes a knob can affect. "compare" is a compositing pass -- it consumes
#: the others rather than invoking Blender.
#:
#: "mask" is the runtime-tint pass (C.4c). It shares the body's camera, canvas and
#: resolution and differs only in the MATERIAL: one flat grey shader whose alpha is the
#: harness band, so `render.use_normal_map` and friends are deliberately absent from its
#: dependency list -- the mask never sees the shark's textures.
PASSES = ("body", "shadow", "mask", "compare")

#: Every knob: dotted key -> (type, default, passes it invalidates).
#:
#: `type` is one of str/int/float/bool, or a tuple ("vec", n, elem_type) for a
#: fixed-length list. Floats accept ints (TOML writes `0` for 0.0 readily enough).
SCHEMA: dict[str, tuple] = {
    # ---- the model and where it sits -------------------------------------------
    "model.blend":                (str, "assets/source/FILES/HAMMERHEAD.blend", ("body", "shadow", "mask")),
    "model.object":               (str,    "HAMMERHEAD_RIG", ("body", "shadow", "mask")),
    "model.pivot":                (("vec", 3, float), [-1.0746, 0.0, 0.3872], ("body", "shadow", "mask")),
    "model.scale":                (float,             0.75, ("body", "shadow", "mask")),
    "model.girth":                (float,             1.0,  ("body", "shadow", "mask")),
    "model.offset":               (("vec", 3, float), [0.0, 0.0, 0.85], ("body", "shadow", "mask")),
    "model.rotation":             (("vec", 3, float), [0.0, 0.0, 0.0], ("body", "shadow", "mask")),
    "model.base_yaw":             (float,             90.0, ("body", "shadow", "mask")),
    "model.mute_nla":             (bool,              True, ("body", "shadow", "mask")),
    "model.rest_pose":            (bool,              True, ("body", "shadow", "mask")),
    "model.drop_stale_keyframes": (bool,              True, ("body", "shadow", "mask")),
    "model.frame":                (int,                  1, ("body", "shadow", "mask")),
    "model.subdiv_render_levels": (int,                  1, ("body", "shadow", "mask")),
    # ---- C.5's flop: which clip, how hard, and the rig fix it needs ---------------
    "model.action":               (str,          pose.REST, ("body", "shadow", "mask")),
    "model.pose_gain":            (float,              1.0, ("body", "shadow", "mask")),
    "model.phase_lock":           (float,              0.0, ("body", "shadow", "mask")),
    "model.reparent_head":        (bool,             False, ("body", "shadow", "mask")),
    "model.ground_contact":       (bool,             False, ("body", "shadow", "mask")),
    # ---- C.5's bounce: the lift that makes the shadow separate --------------------
    "bounce.height":              (float,              0.0, ("body", "shadow", "mask")),
    "bounce.phase":               (float,              0.0, ("body", "shadow", "mask")),
    "bounce.gravity":             (float,              9.8, ("body", "shadow", "mask")),
    # ---- the camera -------------------------------------------------------------
    "camera.pitch":               (float, fc.CAMERA_ELEVATION_DEG, ("body", "shadow", "mask")),
    "camera.sprite_scale":        (float,              0.5, ("body", "shadow", "mask", "compare")),
    "camera.canvas_tiles":        (float,              6.0, ("body", "mask")),
    "camera.shadow_canvas_tiles": (float,             11.0, ("shadow",)),
    # ---- the sun ----------------------------------------------------------------
    "sun.azimuth":                (float, fc.SUN_AZIMUTH_DEG, ("body", "shadow", "mask")),
    "sun.elevation":              (float, fc.SUN_ELEVATION_DEG, ("body", "shadow", "mask")),
    "sun.energy":                 (float,             16.0, ("body", "shadow", "mask")),
    "sun.angular_size":           (float,              1.0, ("body", "shadow", "mask")),
    "sun.ambient":                (float,             0.25, ("body", "shadow", "mask")),
    # ---- the renderer -----------------------------------------------------------
    "render.engine":              (str, "BLENDER_EEVEE_NEXT", ("body", "mask")),
    "render.shadow_engine":       (str,           "CYCLES", ("shadow",)),
    "render.device":              (str,              "CPU", ("body", "shadow", "mask")),
    "render.samples":             (int,                 64, ("body", "mask")),
    "render.preview_samples":     (int,                 16, ("body", "mask")),
    "render.shadow_samples":      (int,                 32, ("shadow",)),
    "render.supersample":         (int,                  1, ("body", "shadow", "mask")),
    "render.resolution_px":       (int,                  0, ("body", "shadow", "mask")),
    "render.view_transform":      (str,         "Standard", ("body", "mask")),
    "render.look":                (str,             "None", ("body", "mask")),
    "render.use_subsurface":      (bool,             False, ("body",)),
    "render.use_normal_map":      (bool,              True, ("body",)),
    "render.normal_strength":     (float,              0.4, ("body",)),
    # ---- the rotation wheel ------------------------------------------------------
    "rotations.count":            (int,                 64, ("body", "shadow", "mask")),
    "rotations.preview":          (int,                  8, ()),
    "rotations.counterclockwise": (bool,             False, ("body", "shadow", "mask")),
    # ---- the runtime-tint mask ----------------------------------------------------
    "mask.mode":                  (str,          "harness", ("mask",)),
    "mask.strap_fore":            (float,             0.20, ("mask",)),
    "mask.strap_aft":             (float,            -0.62, ("mask",)),
    "mask.strap_width":           (float,             0.16, ("mask",)),
    "mask.plate_z":               (float,             0.24, ("mask",)),
    "mask.plate_top_z":           (float,             0.70, ("mask",)),
    "mask.edge":                  (float,             0.04, ("mask",)),
    "mask.grey":                  (float,             0.12, ("mask",)),
    # ---- the water reflection (built at pack time, no Blender pass) ----------------
    "reflection.blur_tiles":      (float,             0.16, ()),
    "reflection.gain":            (float,              2.6, ()),
    "reflection.recentre":        (bool,              True, ()),
    # ---- the compare sheet -------------------------------------------------------
    "compare.rotations":          (int,                  8, ("compare",)),
    "compare.cell_tiles":         (float,              6.0, ("compare",)),
    "compare.origin_y":           (float,             0.60, ("compare",)),
    "compare.background":         (("vec", 3, int), [58, 62, 66], ("compare",)),
    "compare.stock_alpha":        (float,             0.45, ("compare",)),
    "compare.show_stock":         (bool,              True, ("compare",)),
    "compare.show_shadow":        (bool,              True, ("compare",)),
    "compare.show_mounts":        (bool,              True, ("compare",)),
    "compare.show_legs":          (bool,              True, ("compare",)),
    "compare.grid":               (bool,              True, ("compare",)),
    # ---- output -------------------------------------------------------------------
    "output.dir":                 (str,       "render-out", ()),
}

#: String knobs with a closed set of legal values. A misspelled VALUE is the same class
#: of bug as a misspelled KEY -- it renders something, it renders the wrong thing, and it
#: does it silently -- so it is fatal here rather than a warning at the far end.
#:
#: `model.action` takes its list from render/pose.py rather than repeating the five clip
#: ids, because two lists of the same thing is one list that rots. A clip added to the
#: table is selectable from the CLI the same minute.
ENUMS = {
    "mask.mode": ("harness", "silhouette"),
    "model.action": pose.ACTION_CHOICES,
}

#: Knobs added AFTER the standing sheets shipped, and excluded from every hash while they
#: sit at their defaults. Read that twice, because it is the one deliberate hole in the
#: provenance story and it exists for exactly one reason.
#:
#: mod/jamaltron/graphics/ ships four PNGs stamped `config 83d6be794998` plus a per-pass
#: hash each, and pack.py REFUSES a sheet whose pass hash does not match the config being
#: packed. A hash over "every key in SCHEMA" therefore means the schema can never grow
#: again without invalidating art that is already correct: adding `bounce.height = 0.0` to
#: the file would move all five hashes and re-date pixels that did not move.
#:
#: The invariant the hash actually promises is "these knobs made these pixels". A knob at a
#: default that is an exact no-op -- no action assigned, gain 1.0, the rig as bought, zero
#: lift -- cannot have made any pixel, so it hashes as ABSENT and the standing config keeps
#: the hash its sheets carry. Move any of them off the default and it is in the hash like
#: anything else, which is what keeps a posed or bouncing render from colliding with a
#: standing one. test_art_harness.py pins both halves, and a new entry here MUST be a
#: provable no-op at its default -- if it is not, it does not belong in this tuple.
ADDITIVE = ("model.action", "model.pose_gain", "model.phase_lock", "model.reparent_head",
            "model.ground_contact", "bounce.height", "bounce.phase", "bounce.gravity")

#: Where `model.rotation[0]` stops reading as BEACHED, in degrees of roll either way.
#: Measured off the C.5 sheets (sheet B): 80-90 is the flop and past about 105 he reads as
#: dead, belly-up, in WATER -- a different animal in a different place, not a worse flop.
#:
#: A number and not a clamp, deliberately. The schema does not range-check anything else
#: either, and a knob you cannot set past the edge is an edge you have to take on faith --
#: which is the opposite of what C.5 needs, since the whole phase exists to replace faith
#: with looking. So the slider reaches past it, warnings() says what you are looking at,
#: and `--set model.rotation=[140,0,0]` stops being silent (it was, until this landed).
ROLL_BELLY_UP = 105.0

#: Env var that overrides `model.blend`. The model is gitignored and machine-local,
#: so the committed config cannot name a path that works for anyone else.
BLEND_ENV = "JAMALTRON_BLEND"


class ConfigError(ValueError):
    """A knob is missing, misspelled, or the wrong type. Always fatal: a silently
    ignored knob wastes a morning."""


def suggest(key: str) -> str:
    """`"; did you mean model.scale?"` for a misspelled knob, or "" when nothing is close.

    Two lookups, because knobs get misspelled two ways. A right leaf in the wrong section
    (`render.scale`) is an exact leaf match. A misspelled leaf (`model.scal`) is not, and
    that is the typo you actually make at 9am -- it needs edit distance. Matching only the
    first case is the hint firing on the case you would have spotted anyway.

    Cutoff 0.7, measured against the real knob list: 0.6 is loose enough that the shared
    "model." prefix alone carries `model.zzz` over the line and the hint confidently names
    a knob you never meant. A wrong suggestion costs more than none.
    """
    leaf = key.split(".")[-1]
    exact = sorted(k for k in SCHEMA if k.split(".")[-1] == leaf and k != key)
    near = exact or difflib.get_close_matches(key, sorted(SCHEMA), n=1, cutoff=0.7)
    return f"; did you mean {near[0]}?" if near else ""

# ---------------------------------------------------------------------------- flatten


def flatten(nested: dict, prefix: str = "") -> dict:
    """{'a': {'b': 1}} -> {'a.b': 1}. Lists stay whole; they are vector knobs."""
    out = {}
    for k, v in nested.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten(v, key + "."))
        else:
            out[key] = v
    return out


def unflatten(flat: dict) -> dict:
    """Inverse of flatten(), for writing a config back out."""
    out: dict = {}
    for key, value in flat.items():
        node = out
        parts = key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
    return out


# ---------------------------------------------------------------------------- coerce


def _coerce(key: str, spec, value):
    kind = spec[0]
    if isinstance(kind, tuple):                      # ("vec", n, elem)
        _, n, elem = kind
        if not isinstance(value, (list, tuple)) or len(value) != n:
            raise ConfigError(f"{key}: expected {n} numbers, got {value!r}")
        return [_coerce_scalar(key, elem, v) for v in value]
    return _coerce_scalar(key, kind, value)


def _coerce_scalar(key: str, kind, value):
    if kind is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{key}: expected true/false, got {value!r}")
        return value
    if kind is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{key}: expected an integer, got {value!r}")
        return value
    if kind is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{key}: expected a number, got {value!r}")
        return float(value)
    if kind is str:
        if not isinstance(value, str):
            raise ConfigError(f"{key}: expected a string, got {value!r}")
        return value
    raise ConfigError(f"{key}: unhandled schema type {kind!r}")


def defaults() -> dict:
    """The schema's defaults as a flat dict. Deep-copies the vector knobs so a
    caller mutating a resolved config cannot poison the next resolve()."""
    return {k: (list(v[1]) if isinstance(v[1], list) else v[1]) for k, v in SCHEMA.items()}


def resolve(raw: dict | None = None, overrides: dict | None = None, *,
            env: dict | None = None) -> dict:
    """Schema defaults <- TOML <- CLI overrides <- env, validated. Flat dict out.

    Unknown keys raise. That is the point: `model.scal = 0.8` must fail loudly, not
    quietly render at 0.75 while you wonder why the shark did not grow.
    """
    cfg = defaults()
    for source, name in ((raw, "config file"), (overrides, "--set override")):
        if not source:
            continue
        flat = flatten(source) if any(isinstance(v, dict) for v in source.values()) else dict(source)
        for key, value in flat.items():
            if key not in SCHEMA:
                raise ConfigError(f"unknown knob {key!r} in {name}{suggest(key)}")
            cfg[key] = _coerce(key, SCHEMA[key], value)

    for key, allowed in ENUMS.items():
        if cfg[key] not in allowed:
            raise ConfigError("%s: %r is not one of %s"
                              % (key, cfg[key], ", ".join(repr(v) for v in allowed)))

    env = os.environ if env is None else env
    if env.get(BLEND_ENV):
        cfg["model.blend"] = env[BLEND_ENV]
    return cfg


def load(path=None, overrides: dict | None = None, *, env: dict | None = None) -> dict:
    """Read jamaltron.toml (or `path`) and resolve it."""
    import tomllib
    p = pathlib.Path(path or DEFAULT_CONFIG_PATH)
    with open(p, "rb") as fh:
        raw = tomllib.load(fh)
    return resolve(raw, overrides, env=env)


def parse_set(assignments) -> dict:
    """`--set model.scale=0.8` -> {'model.scale': 0.8}, typed by the SCHEMA.

    Values go through the TOML value parser rather than eval/ast, so `[1,0,2]`,
    `true` and `"text"` all mean what they mean in the config file. One syntax,
    not two.
    """
    import tomllib
    out = {}
    for item in assignments or ():
        if "=" not in item:
            raise ConfigError(f"--set needs key=value, got {item!r}")
        key, _, value = item.partition("=")
        key = key.strip()
        if key not in SCHEMA:
            raise ConfigError(f"unknown knob {key!r} in --set{suggest(key)}")
        try:
            parsed = tomllib.loads(f"v = {value.strip()}")["v"]
        except Exception as exc:
            raise ConfigError(f"--set {key}: {value.strip()!r} is not a TOML value ({exc})") from None
        out[key] = _coerce(key, SCHEMA[key], parsed)
    return out


# ----------------------------------------------------------------------------- bounce


def cycle_of(cfg: dict) -> tuple:
    """(lo, hi) of the frames `model.action` plays, inclusive. REST is (1, 1) -- one frame
    and no cycle, which is what makes the bounce arithmetic below fall to zero."""
    c = pose.clip_of(cfg["model.action"])
    return (c.lo, c.hi) if c else (1, 1)


def bounce_flight(cfg: dict) -> tuple:
    """(launch speed in tiles/s, airtime in seconds) implied by height and gravity.

    Airtime is DERIVED, not a knob, and that is the choice worth defending: gravity is one
    number for every jump, so once you have said how high he gets you have also said how
    long he hangs. A separate airtime knob would let a 0.3-tile hop float for a second,
    which is the exact tell of an animation that was drawn rather than dropped.
    """
    h = max(0.0, cfg["bounce.height"])
    g = max(1e-6, cfg["bounce.gravity"])
    if h <= 0.0:
        return 0.0, 0.0
    v0 = math.sqrt(2.0 * g * h)
    return v0, 2.0 * v0 / g


def bounce_lift(cfg: dict, frame=None) -> float:
    """World-z lift in TILES at one animation frame. Zero on the ground, never negative.

    A PARABOLA, NOT A SINE, and the difference is the whole point of the bounce. A sine
    spends most of its time near the extremes and crosses the middle fast, so it reads as
    something floating -- hanging low, hanging high, easing through the transit. Ballistic
    flight is the opposite shape: it leaves the ground at full speed, decelerates into a
    brief apex and accelerates back down, which is what a thing being PULLED looks like.
    Same peak height either way; only one of them reads as gravity. So: v0 = sqrt(2gh) up,
    z = v0 t - gt^2 / 2, and the 45-degree camera turns every tile of that into 0.707 tiles
    up-screen and -- the part that sells it -- a whole tile of shadow travel east.

    GROUND CONTACT IS A HARD FLOOR, not the bottom of a curve. Outside the flight window he
    is ON the ground at exactly z = 0 for as many frames as the cycle has left over: the
    max() is the floor, and it is a max() rather than an abs() because a bounced ball does
    not mirror through the floor, it waits there. Those waiting frames are where the curl-up
    happens, which is why the phase knob matters more than the height one.

    PHASE, and why it is a knob rather than a relationship. `bounce.phase` is where in the
    clip's own cycle the push-off happens, as a fraction: 0.0 launches on the clip's first
    frame, 0.5 half a cycle in. The thrash's peak curl is the frame you want to launch ON,
    and which frame that is depends on the clip, the roll and the gain -- it is an eyeball
    decision on a compare sheet, not an identity we can write down here. Wrong phase and the
    lift fights the pose: he leaves the ground at the moment the body is straight, which
    reads as a sprite being dragged upward.
    """
    lo, hi = cycle_of(cfg)
    span = hi - lo + 1
    v0, airtime = bounce_flight(cfg)
    if span < 2 or airtime <= 0.0:
        # No clip means no cycle to push off in, so there is no bounce -- a constant hover
        # is not one. warnings() says so out loud rather than letting a set height do nothing.
        return 0.0
    f = cfg["model.frame"] if frame is None else frame
    # CLAMPED to the clip, exactly as apply_action clamps the frame it POSES (C.22). Without
    # it, model.frame=32 on SWIM_FAST posed frame 20 and lifted frame 32 -- one config, two
    # different frames, 14 px apart. A float clamp rather than pose.clamp_frame, which rounds:
    # a fractional sample is a legitimate question to ask of a parabola.
    f = min(max(float(f), float(lo)), float(hi))
    phase = cfg["bounce.phase"] - math.floor(cfg["bounce.phase"])     # wraps, so 1.25 == 0.25
    launch = lo + phase * span
    fps = pose.FPS
    t = ((float(f) - launch) % span) / fps
    if t >= airtime:
        return 0.0
    g = max(1e-6, cfg["bounce.gravity"])
    return max(0.0, v0 * t - 0.5 * g * t * t)


def bounce_profile(cfg: dict) -> list:
    """The lift at every frame of the cycle, for reporting. [(frame, tiles), ...]."""
    lo, hi = cycle_of(cfg)
    return [(f, bounce_lift(cfg, f)) for f in range(lo, hi + 1)]


# ---------------------------------------------------------------------------- derived


def derived(cfg: dict) -> dict:
    """Numbers computed from knobs. Never authored, always reported.

    TWO RESOLUTIONS, AND THE DIFFERENCE IS THE WHOLE BUG THIS FUNCTION USED TO HAVE.
    `*_render_px` is what Blender is told to render. `*_resolution_px` is what LANDS ON
    DISK after art.py's Lanczos downsample, and it is what the PNG text chunk, the sidecar,
    the visible footer and the compare sheet's resampling all mean. They differ by exactly
    `render.supersample`. Conflating them stamped `384 px, 64 px/tile` on a 192 px file,
    and a provenance stamp that misreports the pixels it is stamping is worse than none.

    `render.resolution_px` pins the FINAL px-per-tile off the body canvas; the shadow
    canvas rides that same scale so the two passes can still be overlaid. supersample then
    multiplies the render size on top, whether or not resolution_px is set -- one meaning
    for the knob everywhere.
    """
    ppt_nominal = fc.px_per_tile(cfg["camera.sprite_scale"])
    ss = max(1, cfg["render.supersample"])
    forced = cfg["render.resolution_px"]
    ppt_final = forced / cfg["camera.canvas_tiles"] if forced > 0 else ppt_nominal

    def res_for(canvas_tiles):
        return max(1, int(round(canvas_tiles * ppt_final)))

    body_res = res_for(cfg["camera.canvas_tiles"])
    shadow_res = res_for(cfg["camera.shadow_canvas_tiles"])
    # The shark's rest-pose bounding box in Blender units (C.2, measured), scaled.
    model_bu = (5.0272, 1.9682, 1.8771)
    s = cfg["model.scale"]
    el = math.radians(cfg["sun.elevation"])
    az = math.radians(cfg["sun.azimuth"])
    run = math.cos(el) / max(math.sin(el), 1e-9)
    # One tile of world HEIGHT is cos(pitch) tiles of up-screen travel and one tile of
    # ground DEPTH is sin(pitch) -- Factorio's own math3d.lua collapses the two into one
    # constant because at 45 degrees sin == cos. Spelled separately here so the height
    # term still means height if anyone ever moves the camera off 45 (the harness warns).
    up_per_height = math.cos(math.radians(cfg["camera.pitch"]))
    lift = bounce_lift(cfg)
    peak = max(0.0, cfg["bounce.height"])
    lo, hi = cycle_of(cfg)
    _, airtime = bounce_flight(cfg)
    return {
        # On disk, and therefore what every stamp means.
        "body_resolution_px": body_res,
        "shadow_resolution_px": shadow_res,
        # What Blender is asked for. Equal to the above unless supersample > 1.
        "body_render_px": body_res * ss,
        "shadow_render_px": shadow_res * ss,
        "supersample": ss,
        "body_px_per_tile": body_res / cfg["camera.canvas_tiles"],
        "shadow_px_per_tile": shadow_res / cfg["camera.shadow_canvas_tiles"],
        "sprite_px_per_tile": ppt_nominal,
        "shark_length_tiles": model_bu[0] * s,
        # girth is a WIDTH-only multiplier, so it belongs here and nowhere else - every
        # report site reads this derived value, and before this it printed the un-girthed
        # width at every girth, which is a tool confidently reporting a number that is wrong.
        "shark_width_tiles": model_bu[1] * s * cfg["model.girth"],
        "shark_height_tiles": model_bu[2] * s,
        # Sun as the shadow's ground run, the form factorio_camera states it in.
        "light_run_east": run * math.sin(az),
        "light_run_south": -run * math.cos(az),
        # THE BOUNCE, every number it costs. `bounce_lift_tiles` is THIS frame's lift in
        # world z; the rest is what that does to the picture. The shadow term is the one
        # that matters: at the game's own 45-degree sun a tile of lift is a tile of shadow
        # travel east while the body only rises 0.707 tiles up-screen, and that SEPARATION
        # is what reads as airborne. It is free -- the shadow pass is a real Cycles render
        # with a real sun and a catcher at z=0, so lifting the model lands the shadow
        # correctly by itself rather than us applying an offset to a sprite.
        "bounce_lift_tiles": lift,
        "bounce_peak_tiles": peak,
        "bounce_cycle_frames": hi - lo + 1,
        "bounce_airtime_seconds": airtime,
        "bounce_airtime_frames": airtime * pose.FPS,
        "bounce_lift_up_screen_tiles": lift * up_per_height,
        "bounce_peak_up_screen_tiles": peak * up_per_height,
        "bounce_peak_shadow_east_tiles": peak * run * math.sin(az),
        # What the frame box grows by: the canvas has to hold the peak, not this frame.
        "bounce_canvas_cost_tiles": peak * up_per_height,
        "camera_is_factorio_default": (
            abs(cfg["camera.pitch"] - fc.CAMERA_ELEVATION_DEG) < 1e-9
            and abs(cfg["camera.sprite_scale"] - 0.5) < 1e-9
        ),
        "sun_is_factorio_default": (
            abs(cfg["sun.azimuth"] - fc.SUN_AZIMUTH_DEG) < 1e-9
            and abs(cfg["sun.elevation"] - fc.SUN_ELEVATION_DEG) < 1e-9
        ),
    }


def warnings(cfg: dict) -> list[str]:
    """Knob settings that are legal but will bite. Printed, never fatal."""
    d = derived(cfg)
    out = []
    if not d["camera_is_factorio_default"]:
        out.append(
            "camera.pitch/%.3f sprite_scale/%.3f are OFF the game's own projection "
            "(math3d.lua pins 45 deg); sprites rendered here will not line up with stock art"
            % (cfg["camera.pitch"], cfg["camera.sprite_scale"]))
    if not d["sun_is_factorio_default"]:
        out.append(
            "sun.azimuth/%.1f elevation/%.1f are off the measured stock shadow direction "
            "(90 deg / 45 deg); the shadow sheet will not match neighbouring entities"
            % (cfg["sun.azimuth"], cfg["sun.elevation"]))
    if cfg["render.shadow_engine"] != "CYCLES":
        out.append(
            "render.shadow_engine=%s: only Cycles honours is_shadow_catcher. EEVEE Next "
            "renders the catcher plane fully opaque and the shadow pass is garbage"
            % cfg["render.shadow_engine"])
    if cfg["mask.mode"] == "silhouette":
        out.append(
            "mask.mode=silhouette paints the WHOLE shark with the player's colour at ~90% "
            "opacity (stock's own mask does this to the spidertron, which is a machine). "
            "On a hammerhead it stops reading as a shark; `harness` tints the straps only")
    if cfg["mask.plate_top_z"] <= cfg["mask.plate_z"] + cfg["mask.edge"]:
        out.append(
            "mask.plate_top_z %.3f is not above mask.plate_z %.3f by more than one edge "
            "ramp (%.3f), so the dorsal plate is EMPTY and the harness is two bare straps"
            % (cfg["mask.plate_top_z"], cfg["mask.plate_z"], cfg["mask.edge"]))
    if cfg["mask.strap_fore"] <= cfg["mask.strap_aft"]:
        out.append(
            "mask.strap_fore %.3f is not forward of mask.strap_aft %.3f (+x is the nose), "
            "so the dorsal plate spans backwards and the harness renders inside out"
            % (cfg["mask.strap_fore"], cfg["mask.strap_aft"]))
    posed = cfg["model.action"] != pose.REST
    roll = cfg["model.rotation"][0]
    if abs(roll) > ROLL_BELLY_UP:
        out.append(
            "model.rotation roll %.1f is past %.0f deg, where C.5's own sheets say he stops "
            "reading as BEACHED and starts reading as dead, belly-up, in WATER. 80-90 is the "
            "flop -- far enough over that the swim's bend plane stands up into the bounce's "
            "plane, not so far that he is floating" % (roll, ROLL_BELLY_UP))
    if posed and not cfg["model.reparent_head"]:
        out.append(
            "model.action=%s with model.reparent_head=false: HEAD is a ROOT bone on this rig "
            "and NO swim clip touches it (C.18a), so the snout is welded to world space and "
            "the head cannot lift off the ground however hard the spine thrashes. At roll "
            "80-90 that is the curl-up the whole pose depends on. Set "
            "model.reparent_head = true" % cfg["model.action"])
    if cfg["model.ground_contact"] and not posed:
        out.append(
            "model.ground_contact with model.action=rest MOVES THE STANDING SHARK off the height "
            "his shipped sheets were rendered at: contact cancels model.offset z (%.2f) and "
            "re-seats him on his lowest vertex. At the committed config that vertex is 0.26 "
            "tiles BELOW z=0 (C.27), so contact RAISES him about 12 px. It is the flop's knob; "
            "pick a clip or turn it off" % cfg["model.offset"][2])
    if not posed and not cfg["model.rest_pose"]:
        out.append(
            "model.action=rest with model.rest_pose=false renders whatever pose the .blend "
            "happened to be SAVED in, scrubbed by model.frame -- not a clip, and not the rest "
            "shark either. Pick a model.action, or set rest_pose = true. (The other way round "
            "is fine: with an action selected, the pose is cleared and posed either way, so "
            "rest_pose stops meaning anything.)")
    if posed:
        lo, hi = cycle_of(cfg)
        if not lo <= cfg["model.frame"] <= hi:
            out.append(
                "model.frame %d is outside %s's own range %d-%d, so the renderer CLAMPS it to "
                "%d -- two configs that hash differently and render the same pixels. Set a "
                "frame the clip has"
                % (cfg["model.frame"], cfg["model.action"], lo, hi,
                   min(max(cfg["model.frame"], lo), hi)))
    lock = cfg["model.phase_lock"]
    if lock:
        clip = pose.clip_of(cfg["model.action"])
        if clip is None:
            out.append(
                "model.phase_lock %.2f with model.action=rest locks nothing: there is no clip, "
                "so there is no wave to take the lag out of. Pick a swim or set it to 0" % lock)
        elif not clip.wave:
            out.append(
                "model.phase_lock %.2f does NOTHING on %s: a bite is a one-shot on "
                "HEAD/JAW/fins, not a wave running down the spine, so there is no per-joint "
                "lag to cancel. It only moves the hash. Pick a swim or set it to 0"
                % (lock, clip.id))
        if not pose.LOCK_MIN <= lock <= pose.LOCK_MAX:
            out.append(
                "model.phase_lock %.2f is off the 0..1 rail: past 1 the lag OVERSHOOTS and the "
                "wave runs backwards, tail to nose; below 0 it stretches the swim's own lag. "
                "Legal, and neither one is a flop" % lock)
    if cfg["model.pose_gain"] > pose.GAIN_SAFE:
        out.append(
            "model.pose_gain %.2f is past the %.1fx the rig was MEASURED to survive. Above "
            "it, check the neck and the tail tip for mesh tearing before you believe the "
            "frame" % (cfg["model.pose_gain"], pose.GAIN_SAFE))
    if cfg["model.pose_gain"] < 0.0:
        out.append(
            "model.pose_gain %.2f is NEGATIVE, which mirrors every bone through its rest "
            "rotation -- a shark bent the wrong way, not a quieter one. 1.0 is the clip as "
            "bought" % cfg["model.pose_gain"])
    if cfg["bounce.height"] > 0.0 and not posed:
        out.append(
            "bounce.height %.2f with model.action=rest never leaves the ground: the lift is "
            "driven by the thrash PHASE and a rest pose has no cycle to push off in. Pick a "
            "clip or set the height to 0" % cfg["bounce.height"])
    if cfg["bounce.height"] > 0.0 and posed:
        air, span = d["bounce_airtime_frames"], d["bounce_cycle_frames"]
        if air > span:
            out.append(
                "bounce.height %.2f at gravity %.1f is %.1f frames of airtime in a %d-frame "
                "cycle: he is still up when the next push-off comes, so the loop POPS at the "
                "seam instead of landing. Lower the height or raise bounce.gravity"
                % (cfg["bounce.height"], cfg["bounce.gravity"], air, span))
        elif air > span * 0.85:
            out.append(
                "bounce.height %.2f leaves only %.1f of %d frames on the GROUND. The landing "
                "is where the comedy is and he has no time to lie in it"
                % (cfg["bounce.height"], span - air, span))
    if cfg["bounce.gravity"] <= 0.0:
        out.append("bounce.gravity %.2f is not gravity; nothing comes down. 9.8 is real"
                   % cfg["bounce.gravity"])
    if cfg["rotations.count"] % max(cfg["rotations.preview"], 1):
        out.append("rotations.preview=%d does not divide rotations.count=%d, so preview "
                   "frames are not a subset of the full sheet and cannot be reused"
                   % (cfg["rotations.preview"], cfg["rotations.count"]))
    return out


# ---------------------------------------------------------------------------- hashing


def canonical(cfg: dict) -> str:
    """Stable text form of a config. Sorted keys, no whitespace, floats via repr."""
    return json.dumps(cfg, sort_keys=True, separators=(",", ":"))


#: How a redacted `model.blend` is spelled. Anything carrying this prefix is already a
#: content digest and is passed through untouched, which is what makes a stamp read back
#: off a PNG re-hash to the hash it claims.
BLEND_DIGEST_PREFIX = "sha256:"

#: What a digest is when the .blend is not on this machine. Deterministic on purpose --
#: packing cached frames without the model must still produce a stable hash -- but it is
#: a DIFFERENT hash from the one the frames were rendered under, so pack.py's pass-hash
#: check refuses rather than shipping a sheet whose provenance nobody can verify.
BLEND_ABSENT = "absent"

#: (path, size, mtime_ns) -> digest. A 1.7 MiB .blend hashes in about 2 ms, and every
#: stamp asks for it five times (config plus four passes).
_DIGEST_CACHE: dict = {}


def blend_path(cfg: dict) -> pathlib.Path:
    """The .blend a config points at, absolute. Relative paths resolve from the repo."""
    p = pathlib.Path(os.path.expanduser(cfg["model.blend"]))
    return p if p.is_absolute() else REPO / p


def blend_digest(path, length: int = 16) -> str:
    """sha256 of the .blend's CONTENT, or BLEND_ABSENT when it is not readable.

    THE PATH IS NOT THE MODEL. It is gitignored, machine-local and overridable by
    $JAMALTRON_BLEND, so a hash over it says "this render happened in this directory on
    this laptop" -- three copies of one file gave three config hashes for pixel-identical
    sheets, and the shipped hash reproduced on exactly zero other machines. The content
    digest is the same everywhere the same model is, which is what the provenance stamp
    was always claiming to be.
    """
    p = pathlib.Path(path)
    try:
        st = p.stat()
    except OSError:
        return BLEND_ABSENT
    key = (str(p), st.st_size, st.st_mtime_ns)
    if key not in _DIGEST_CACHE:
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        _DIGEST_CACHE[key] = BLEND_DIGEST_PREFIX + h.hexdigest()[:length]
    return _DIGEST_CACHE[key]


def redacted(cfg: dict) -> dict:
    """The config as it is STAMPED: `model.blend` replaced by a digest of its CONTENT.

    Two jobs in one substitution. It makes the stamp a fact about the model rather than
    about one filesystem (see blend_digest), and it keeps an absolute path -- which on
    this machine is a private scratch directory -- out of PNG text chunks that ship in a
    public repo. Already-redacted values pass straight through, so resolving a stamped
    config and re-hashing it reproduces the stamp exactly.
    """
    value = cfg["model.blend"]
    if not value.startswith(BLEND_DIGEST_PREFIX) and value != BLEND_ABSENT:
        value = blend_digest(blend_path(cfg))
    return dict(cfg, **{"model.blend": value})


def is_default(key: str, value) -> bool:
    """Is this the value the schema ships? Lists compare by content, not identity."""
    want = SCHEMA[key][1]
    if isinstance(want, list):
        return list(value) == list(want)
    return value == want and isinstance(value, type(want))


def hashable(cfg: dict) -> dict:
    """The config as it is HASHED: redacted, minus any ADDITIVE knob still at its default.

    The subtraction is the whole of the story in ADDITIVE above: a knob that cannot have
    changed a pixel is not in the key, so the schema can grow without re-dating art that
    already shipped. Everything else -- including every one of those knobs the moment it is
    touched -- is hashed exactly as before.
    """
    view = redacted(cfg)
    for key in ADDITIVE:
        if key in view and is_default(key, view[key]):
            del view[key]
    # The same rule, for a knob that a SWITCH makes dead rather than a default: with
    # ground_contact on, offset z is added and then cancelled (render_jamal.ground_contact),
    # so it cannot move a pixel -- MEASURED, 0.5 vs 1.0 renders identical -- and keeping it in
    # the key made every drag of the tuner's height slider re-render the same picture under
    # a new hash. It is pinned to 0 here; the stamp still records what the file said.
    if view.get("model.ground_contact") and "model.offset" in view:
        view["model.offset"] = list(view["model.offset"][:2]) + [0.0]
    return view


def config_hash(cfg: dict, length: int = 12) -> str:
    """Hash of the WHOLE resolved config. This is the provenance stamp."""
    return hashlib.sha256(canonical(hashable(cfg)).encode()).hexdigest()[:length]


#: Derived numbers a pass's PIXELS depend on, on top of the knobs it declares.
#:
#: The schema cannot express this on its own, and the gap was serving stale pixels.
#: `render.resolution_px` makes the SHADOW pass's resolution a function of
#: `camera.canvas_tiles`, which is declared body-only: at resolution_px = 384, moving
#: canvas_tiles 6.0 -> 4.5 takes the shadow pass from 704 px / 64.00 px-per-tile to
#: 939 px / 85.36, and the old pass hash did not move, so cached shadow frames at the
#: wrong pixel scale were served and composited under the shark. Hash what the pass
#: actually renders with instead of trusting a static dependency list to be complete.
#: A formula change here does invalidate caches, and that is correct -- if the numbers
#: move, the pixels moved.
PASS_DERIVED = {
    "body": ("body_render_px", "body_resolution_px"),
    "shadow": ("shadow_render_px", "shadow_resolution_px"),
    # The mask rides the body canvas exactly, which is the point: its frames have to
    # crop to the same box as the body's or the two layers slide apart in game.
    "mask": ("body_render_px", "body_resolution_px"),
    "compare": ("sprite_px_per_tile", "body_px_per_tile", "shadow_px_per_tile"),
}


def pass_keys(pass_name: str) -> list[str]:
    if pass_name not in PASSES:
        raise ConfigError(f"unknown pass {pass_name!r}, expected one of {PASSES}")
    return sorted(k for k, spec in SCHEMA.items() if pass_name in spec[2])


def pass_hash(cfg: dict, pass_name: str, length: int = 12) -> str:
    """Hash of everything that CHANGES this pass's pixels: its knobs AND its geometry.

    This is the cache key. `compare.background` must not throw away 64 Cycles frames,
    `model.scale` must throw away all of them, and anything that changes the pass's own
    resolution must throw away all of them too even when the knob that moved it belongs
    to another pass -- see PASS_DERIVED.
    """
    view = hashable(cfg)
    # `if k in view` because hashable() drops an ADDITIVE knob sitting at its default. A
    # KeyError here would be the schema growing and the CACHE crashing on the same commit.
    subset = {k: view[k] for k in pass_keys(pass_name) if k in view}
    d = derived(cfg)
    subset.update(("derived." + k, d[k]) for k in PASS_DERIVED[pass_name])
    return hashlib.sha256(canonical(subset).encode()).hexdigest()[:length]


def stamp(cfg: dict, extra: dict | None = None) -> dict:
    """The provenance blob written beside every render and into every PNG.

    `config` is the REDACTED view, not the resolved one: `model.blend` is a content
    digest. Nothing downstream wants the path (Blender is handed the file on argv), a
    PNG that ships in a public repo must not carry one, and resolving this blob back and
    re-hashing it has to return `config_hash` -- which holds because resolve() fills every
    knob back in from the schema, including the ADDITIVE ones the HASH leaves out.

    Redacted rather than hashable on purpose: this blob is also the payload handed to
    Blender and the sidecar a human reads three weeks later, and both want every knob
    written down -- `model.action = "rest"` is worth saying even though it hashes as absent.
    """
    blob = {
        "config_hash": config_hash(cfg),
        "pass_hashes": {p: pass_hash(cfg, p) for p in PASSES},
        "config": unflatten(redacted(cfg)),
        "derived": derived(cfg),
    }
    if extra:
        blob.update(extra)
    return blob


# ------------------------------------------------------------------------- rotations


def frame_indices(cfg: dict, count: int | None = None) -> list[int]:
    """Which of the `rotations.count` directions to render, evenly spaced.

    Preview frames MUST be a subset of the full wheel, at the same angles, or the
    preview is a different picture from the sheet it is previewing and the cache
    cannot share work between them. `count=8` of 64 gives 0, 8, 16 ... 56.
    """
    total = cfg["rotations.count"]
    n = total if count is None else count
    if n < 1 or n > total:
        raise ConfigError(f"frame count {n} outside 1..{total}")
    step = total / n
    return sorted({int(round(i * step)) % total for i in range(n)})


def compass(index: int, total: int = 64) -> str:
    """Frame index -> a bearing label, for compare-sheet column headers."""
    names = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
    return names[int(round(index / total * 16)) % 16]
