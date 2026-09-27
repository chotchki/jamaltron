"""Every render knob, in one place, with a schema that rejects typos.

The C.10 art-iteration harness's spine: `jamaltron.toml` holds the knobs, this module
resolves, validates and hashes them. Stdlib only (`tomllib` is stdlib on 3.11, both uv's
pin and Blender 4.4.3's bundled CPython), so it imports on BOTH sides of the Blender
boundary and unit-tests with no Blender in the loop -- the split tools/README.md enforces.

WHY TOML AND NOT JSON. Every knob carries a comment saying its default and what it does to
the picture. JSON has no comments, so a commented JSON config is either a lie (a `_comment`
key nobody reads) or a custom parser. TOML comments are free, `tomllib` is stdlib on the
exact Python both sides run, and a one-line TOML diff reviews cleanly. The resolved config
still crosses the Blender boundary as JSON, because that boundary is a `--` argv payload.

WHAT THIS BUYS BEYOND "a settings file":

 1. UNKNOWN KEYS ARE ERRORS. A typo'd knob that silently does nothing is the worst outcome
    for a tool whose job is "change one number, look at the picture" -- you would spend
    the morning tweaking a key the renderer never reads.
 2. PER-PASS HASHES. Each knob declares which render passes it affects: changing
    `compare.background` does not invalidate 64 cached body frames, changing `model.scale`
    invalidates everything, so a one-knob re-run is cheap. The declarations cannot be the
    whole key: `render.resolution_px` lets a body knob move the shadow pass's resolution,
    so each pass also hashes the derived numbers it renders with (PASS_DERIVED). A cache
    key that misses a dependency serves stale pixels.
 3. PROVENANCE. `config_hash()` over the fully resolved config is stamped into every PNG
    and written as a sidecar, so a sheet traces back to its knobs. It hashes the HASHABLE
    form (`hashable()`): the resolved knobs with `model.blend` replaced by a digest of the
    file's CONTENT. Hashing the path made the stamp a fact about one machine's filesystem
    (three copies of the same .blend gave three hashes for identical pixels, none
    reproducible elsewhere). The digest also keeps a private scratch path out of PNGs that
    ship in a public repo. A stamp read back off a sheet re-hashes to the hash it claims, on
    any machine.
    ONE DELIBERATE HOLE: a knob added after art shipped is left OUT of the hash while it
    sits at a default that is an exact no-op, so the schema can grow without re-dating
    pixels that did not move. See ADDITIVE.

Constants are NOT forked from render/factorio_camera.py: the camera pitch, sprite scale and
sun geometry defaults are read from that module at import time, so the derived 45-degree
camera lives in one place. `render/pose.py` is read the same way for the clip ids
`model.action` accepts.
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

#: Repo root. A relative `model.blend` resolves against it exactly as art.py's renderer
#: does; if they differ, the digest describes a different file from the one Blender opened.
REPO = pathlib.Path(__file__).resolve().parents[2]

#: Render passes a knob can affect. "compare" is a compositing pass: it consumes the
#: others rather than invoking Blender.
#:
#: "mask" is the runtime-tint pass (C.4c). It shares the body's camera, canvas and
#: resolution and differs only in MATERIAL: one flat grey shader whose alpha is the harness
#: band, so `render.use_normal_map` and friends are deliberately absent from its dependency
#: list (the mask never sees the shark's textures).
PASSES = ("body", "shadow", "mask", "compare")

#: Every knob: dotted key -> (type, default, passes it invalidates).
#:
#: `type` is one of str/int/float/bool, a tuple ("vec", n, elem_type) for a
#: fixed-length list, or ("list", elem_type) for a list of any length (bone names).
#: Floats accept ints (TOML writes `0` for 0.0 readily enough).
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
    # ---- C.5.6's bedding-in: what the floor holds him up on, and what it swallows ----
    "model.ground_ignore":        (("list", str),       [], ("body", "shadow", "mask")),
    "model.ground_sink":          (float,              0.0, ("body", "shadow", "mask")),
    "model.fin_fold":             (float,              0.0, ("body", "shadow", "mask")),
    "model.spine_sag":            (float,              0.0, ("body", "shadow", "mask")),
    "model.fin_floor":            (bool,             False, ("body", "shadow", "mask")),
    # ---- C.5.8's U: the standing wave the lock alone could not make read ------------
    "model.recentre":             (float,              0.0, ("body", "shadow", "mask")),
    "model.amplitude_even":       (float,              0.0, ("body", "shadow", "mask")),
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

#: String knobs with a closed set of legal values. A misspelled VALUE is the same bug as a
#: misspelled KEY (it silently renders the wrong thing), so it is fatal here rather than a
#: warning at the far end.
#:
#: `model.action` takes its list from render/pose.py rather than repeating the five clip
#: ids, because a second list drifts. A clip added to the table is selectable from the CLI
#: the same minute.
ENUMS = {
    "mask.mode": ("harness", "silhouette"),
    "model.action": pose.ACTION_CHOICES,
}

#: Knobs added AFTER the standing sheets shipped, excluded from every hash while they sit
#: at their defaults: the one deliberate hole in the provenance story, for one reason.
#:
#: mod/jamaltron/graphics/ ships four PNGs stamped `config bd71cb367d90` plus a per-pass
#: hash each, and pack.py REFUSES a sheet whose pass hash does not match the config being
#: packed. A hash over every SCHEMA key means the schema can never grow without
#: invalidating correct art: adding `bounce.height = 0.0` to the file would move all five
#: hashes and re-date pixels that did not move.
#:
#: The hash promises "these knobs made these pixels". A knob at a default that is an exact
#: no-op (no action assigned, gain 1.0, the rig as bought, zero lift) cannot have made any
#: pixel, so it hashes as ABSENT and the standing config keeps the hash its sheets carry.
#: Off its default it hashes like anything else, so a posed or bouncing render cannot
#: collide with a standing one. test_art_harness.py pins both halves, and a new entry here
#: MUST be a provable no-op at its default or it does not belong in this tuple.
ADDITIVE = ("model.action", "model.pose_gain", "model.phase_lock", "model.reparent_head",
            "model.ground_contact", "model.ground_ignore", "model.ground_sink", "model.fin_fold",
            "model.spine_sag", "model.fin_floor", "model.recentre", "model.amplitude_even",
            "bounce.height", "bounce.phase", "bounce.gravity")

#: Where `model.rotation[0]` stops reading as BEACHED, in degrees of roll either way.
#: Measured off the C.5 sheets (sheet B): 80-90 is the flop and past about 105 he reads as
#: dead, belly-up, in WATER -- a different animal in a different place, not a worse flop.
#:
#: A number, not a clamp, deliberately. The schema range-checks nothing else either, and an
#: edge you cannot set past is one you take on faith; C.5 exists to replace faith with
#: looking. So the slider reaches past it, warnings() says what you are looking at, and
#: `--set model.rotation=[140,0,0]` is no longer silent (it was, until this landed).
ROLL_BELLY_UP = 105.0

#: Where `model.fin_fold` runs out, in degrees. MEASURED at the beached framing, the lower
#: pectoral's span dives 50-54 deg on the ground frames and up to 59 on the bite, so 60 levels
#: it on every frame of the cycle; past it the tip climbs into his flank.
#: A warning, not a clamp, like ROLL_BELLY_UP.
FIN_FOLD_LEVEL = 60.0

#: The joints `model.spine_sag` bends, root first: the back half of the spine, from where
#: the trunk starts to taper to the caudal. MEASURED: all 12 bones deform and the spine is
#: one chain SPINE_01..SPINE_07 -> TAIL; SPINE_01..03 carry the trunk flank contact seats
#: him on, so bending them would tip the whole body rather than lay the tail down.
SPINE_SAG_CHAIN = ("SPINE_04", "SPINE_05", "SPINE_06", "SPINE_07", "TAIL")

#: The chord `model.recentre` holds level: spine root (at the nose) to caudal-bone tip. The
#: swim bends that chain and nothing else, so the chord's turn off rest IS how far the curl
#: has tipped him; with a pinned root all of it shows as the tail swinging while the nose
#: stays put.
RECENTRE_CHORD = ("SPINE_01", "TAIL")

#: Where `model.spine_sag` runs out, in degrees per joint. MEASURED on the beached cycle, the
#: tail comes down to his trunk's level at 2.57 on the rest shape and 4.23 at the pause (the
#: most curled-up frame he lies still on); past that even the pause stands on its tail and his
#: trunk hovers, the fin-tip problem at the other end. A warning, not a clamp.
SPINE_SAG_LEVEL = 4.25

#: Env var that overrides `model.blend`. The model is gitignored and machine-local,
#: so the committed config cannot name a path that works for anyone else.
BLEND_ENV = "JAMALTRON_BLEND"


class ConfigError(ValueError):
    """A knob is missing, misspelled, or the wrong type. Always fatal: a silently
    ignored knob wastes a morning."""


def suggest(key: str) -> str:
    """`"; did you mean model.scale?"` for a misspelled knob, or "" when nothing is close.

    Two lookups, because knobs get misspelled two ways. A right leaf in the wrong section
    (`render.scale`) is an exact leaf match. A misspelled leaf (`model.scal`) is not, and is
    the typo you actually make at 9am, so it needs edit distance; the exact match alone only
    catches typos you would have spotted anyway.

    Cutoff 0.7, measured against the real knob list: at 0.6 the shared "model." prefix alone
    carries `model.zzz` over the line and the hint confidently names a knob you never meant.
    A wrong suggestion costs more than none.
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
    if isinstance(kind, tuple) and kind[0] == "list":    # ("list", elem): any length
        if not isinstance(value, (list, tuple)):
            raise ConfigError(f"{key}: expected a list, got {value!r}")
        return [_coerce_scalar(key, kind[1], v) for v in value]
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

    Unknown keys raise: `model.scal = 0.8` must fail loudly, not quietly render at 0.75
    while you wonder why the shark did not grow.
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


#: The overlay on the standing shark (C.24): the beached flop is jamaltron.toml plus only
#: the knobs the flop is about, so a shared knob (scale, girth, sun, camera, mask) has ONE
#: home and the two sheets cannot drift apart.
BEACHED_CONFIG_PATH = DEFAULT_CONFIG_PATH.parent / "beached.toml"


def read_layers(path=None) -> list:
    """A config file and every file under it, BASE FIRST: [(path, raw TOML), ...].

    A file whose top level says `base = "jamaltron.toml"` is an OVERLAY: the base resolves
    first, relative to the overlay's own directory, and the overlay replaces keys on top.
    Keys, never whole tables: an overlay saying `[model] action = "SWIM_FAST"` changes the
    action and keeps the base's scale. `base` is popped from the raw dict here, so nothing
    downstream sees it as a knob.

    Chains are legal (an overlay on an overlay) and a cycle is an error, not a hang.
    """
    import tomllib
    chain, seen = [], []
    p = pathlib.Path(path or DEFAULT_CONFIG_PATH).resolve()
    while True:
        if p in seen:
            raise ConfigError("config base cycle: %s"
                              % " -> ".join(q.name for q in seen + [p]))
        seen.append(p)
        try:
            with open(p, "rb") as fh:
                raw = tomllib.load(fh)
        except FileNotFoundError:
            if len(seen) == 1:
                raise
            raise ConfigError(f"{seen[-2].name}: base {p.name!r} not found at {p}") from None
        base = raw.pop("base", None)
        chain.append((p, raw))
        if base is None:
            return chain[::-1]
        if not isinstance(base, str):
            raise ConfigError(f"{p.name}: base must be a file name, got {base!r}")
        p = (p.parent / base).resolve()


def merged(layers) -> tuple:
    """(flat knobs, sequence table or None) out of read_layers(), base first.

    Unknown keys are caught HERE, per file, so the error names the file with the typo;
    after the merge there is one flat dict and no way to say whose line it was. `sequence`
    is the one non-knob table (render/sequence.py reads it), taken whole from the topmost
    file that has one: a frame list does not merge key by key.
    """
    knobs, sequence = {}, None
    for path, raw in layers:
        raw = dict(raw)
        if "sequence" in raw:
            sequence = raw.pop("sequence")
        flat = flatten(raw)
        for key in flat:
            if key not in SCHEMA:
                raise ConfigError(f"unknown knob {key!r} in {path.name}{suggest(key)}")
        knobs.update(flat)
    return knobs, sequence


def load(path=None, overrides: dict | None = None, *, env: dict | None = None) -> dict:
    """Read jamaltron.toml (or `path`, and whatever it names as its base) and resolve it."""
    knobs, _ = merged(read_layers(path))
    return resolve(knobs, overrides, env=env)


def load_sequence(path=None):
    """The `[sequence]` table `path` carries (or inherits), or None. Raw TOML; render/
    sequence.py is what validates and expands it."""
    return merged(read_layers(path))[1]


def overlay_of(path=None):
    """(base knobs resolved, the overlay's own flat keys) for an overlay; None otherwise.

    What the tuner's export needs to write an overlay-shaped block: the base to diff against
    and the keys the overlay already owns."""
    layers = read_layers(path)
    if len(layers) < 2:
        return None
    base, _ = merged(layers[:-1])
    top = dict(layers[-1][1])
    top.pop("sequence", None)
    return resolve(base, env={}), flatten(top)


def parse_set(assignments) -> dict:
    """`--set model.scale=0.8` -> {'model.scale': 0.8}, typed by the SCHEMA.

    Values go through the TOML value parser, not eval/ast, so `[1,0,2]`, `true` and
    `"text"` mean exactly what they mean in the config file.
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
    """(lo, hi) of the frames `model.action` plays, inclusive. REST is (1, 1): one frame, no
    cycle, which zeroes the bounce arithmetic below."""
    c = pose.clip_of(cfg["model.action"])
    return (c.lo, c.hi) if c else (1, 1)


def bounce_flight(cfg: dict) -> tuple:
    """(launch speed in tiles/s, airtime in seconds) implied by height and gravity.

    Airtime is DERIVED, not a knob: gravity is one number for every jump, so saying how high
    he gets also says how long he hangs. A separate airtime knob would let a 0.3-tile hop
    float for a second, the exact tell of an animation that was drawn rather than dropped.
    """
    h = max(0.0, cfg["bounce.height"])
    g = max(1e-6, cfg["bounce.gravity"])
    if h <= 0.0:
        return 0.0, 0.0
    v0 = math.sqrt(2.0 * g * h)
    return v0, 2.0 * v0 / g


def bounce_lift(cfg: dict, frame=None) -> float:
    """World-z lift in TILES at one animation frame. Zero on the ground, never negative.

    A PARABOLA, NOT A SINE. A sine spends most of its time near the extremes and crosses the
    middle fast, so it reads as floating: hanging low, hanging high, easing through the
    transit. Ballistic flight leaves the ground at full speed, decelerates into a brief apex
    and accelerates back down, which is what being PULLED looks like. Same peak either way;
    only one reads as gravity. So v0 = sqrt(2gh) up, z = v0 t - gt^2 / 2, and the 45-degree
    camera turns each tile of that into 0.707 tiles up-screen and -- the part that sells it
    -- a whole tile of shadow travel east.

    GROUND CONTACT IS A HARD FLOOR, not the bottom of a curve. Outside the flight window he
    sits at exactly z = 0 for whatever frames the cycle has left: the max() is the floor,
    and a max() rather than an abs() because a bounced ball waits on the floor instead of
    mirroring through it. Those waiting frames are where the curl-up happens, which is why
    the phase knob matters more than the height.

    PHASE IS A KNOB, NOT A RELATIONSHIP. `bounce.phase` is where in the clip's cycle the
    push-off happens, as a fraction: 0.0 launches on the clip's first frame, 0.5 half a
    cycle in. You want to launch ON the thrash's peak curl, and which frame that is depends
    on the clip, the roll and the gain -- an eyeball call on a compare sheet, not an
    identity to write down here. Wrong phase and the lift fights the pose: he leaves the
    ground while the body is straight and reads as a sprite dragged upward.
    """
    lo, hi = cycle_of(cfg)
    span = hi - lo + 1
    v0, airtime = bounce_flight(cfg)
    if span < 2 or airtime <= 0.0:
        # No clip, no cycle to push off in, so no bounce (a constant hover is not one).
        # warnings() says so rather than letting a set height silently do nothing.
        return 0.0
    f = cfg["model.frame"] if frame is None else frame
    # CLAMPED to the clip, as apply_action clamps the frame it POSES (C.22). Without it,
    # model.frame=32 on SWIM_FAST posed frame 20 and lifted frame 32: one config, two frames,
    # 14 px apart. A float clamp, not pose.clamp_frame (which rounds): a fractional sample is
    # a legitimate question to ask of a parabola.
    f = min(max(float(f), float(lo)), float(hi))
    phase = cfg["bounce.phase"] - math.floor(cfg["bounce.phase"])     # wraps, so 1.25 == 0.25
    launch = lo + phase * span
    fps = pose.FPS
    t = ((float(f) - launch) % span) / fps
    if t >= airtime:
        return 0.0
    g = max(1e-6, cfg["bounce.gravity"])
    return max(0.0, v0 * t - 0.5 * g * t * t)


def bedded_in(cfg: dict) -> bool:
    """Does contact put part of him under the floor ON PURPOSE? Then the body and mask passes
    draw a holdout ground at z=0 to hide it (the shadow pass's catcher already does).

    Only with ground_contact on: the ignore list and the sink both re-seat contact, so without
    it neither moves anything and nothing gains a holdout it did not have before.
    """
    return bool(cfg["model.ground_contact"]
                and (cfg["model.ground_ignore"] or cfg["model.ground_sink"] > 0.0))


def bounce_profile(cfg: dict) -> list:
    """The lift at every frame of the cycle, for reporting. [(frame, tiles), ...]."""
    lo, hi = cycle_of(cfg)
    return [(f, bounce_lift(cfg, f)) for f in range(lo, hi + 1)]


# ---------------------------------------------------------------------------- derived


def derived(cfg: dict) -> dict:
    """Numbers computed from knobs. Never authored, always reported.

    TWO RESOLUTIONS, AND CONFLATING THEM WAS THIS FUNCTION'S BUG. `*_render_px` is what
    Blender is told to render. `*_resolution_px` is what LANDS ON DISK after art.py's
    Lanczos downsample, and is what the PNG text chunk, the sidecar, the visible footer and
    the compare sheet's resampling all mean. They differ by exactly `render.supersample`.
    Conflating them stamped `384 px, 64 px/tile` on a 192 px file; a provenance stamp that
    misreports its own pixels is worse than none.

    `render.resolution_px` pins the FINAL px-per-tile off the body canvas; the shadow canvas
    rides the same scale so the two passes still overlay. supersample then multiplies the
    render size on top, whether or not resolution_px is set -- one meaning everywhere.
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
    # ground DEPTH is sin(pitch). Factorio's math3d.lua folds them into one constant because
    # at 45 degrees sin == cos; spelled separately so the height term stays right if the
    # camera ever moves off 45 (the harness warns).
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
        # girth is a WIDTH-only multiplier, so it belongs here and nowhere else: every
        # report site reads this derived value, and before this they all printed the
        # un-girthed width at every girth.
        "shark_width_tiles": model_bu[1] * s * cfg["model.girth"],
        "shark_height_tiles": model_bu[2] * s,
        # Sun as the shadow's ground run, the form factorio_camera states it in.
        "light_run_east": run * math.sin(az),
        "light_run_south": -run * math.cos(az),
        # THE BOUNCE, every number it costs. `bounce_lift_tiles` is THIS frame's lift in
        # world z; the rest is what it does to the picture. The shadow term matters most: at
        # the game's 45-degree sun a tile of lift is a tile of shadow travel east while the
        # body rises only 0.707 tiles up-screen, and that SEPARATION reads as airborne. It is
        # free: the shadow pass is a real Cycles render with a real sun and a catcher at z=0,
        # so lifting the model lands the shadow correctly with no sprite offset.
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
    if not cfg["model.ground_contact"] and (cfg["model.ground_ignore"]
                                            or cfg["model.ground_sink"] != 0.0):
        out.append(
            "model.ground_ignore %s / ground_sink %.3f do NOTHING with model.ground_contact "
            "off: both re-seat contact, so they only move the hash"
            % (cfg["model.ground_ignore"], cfg["model.ground_sink"]))
    if "TAIL" in cfg["model.ground_ignore"]:
        out.append(
            "model.ground_ignore lists TAIL: the caudal lobe is what the flick frames push off, "
            "and with it ignored the floor swallows it 0.32-0.54 tiles on exactly those frames "
            "(MEASURED)")
    if cfg["model.ground_sink"] < 0.0:
        out.append(
            "model.ground_sink %.3f is NEGATIVE, which floats him that far off the floor on "
            "every frame -- a hover, not a sink. The bounce is what lifts him"
            % cfg["model.ground_sink"])
    if cfg["model.fin_fold"] > FIN_FOLD_LEVEL or cfg["model.fin_fold"] < 0.0:
        out.append(
            "model.fin_fold %.1f is off the 0..%.0f rail: past about %.0f deg the lower "
            "pectoral's tip swings up past level and into his own flank, and below 0 it digs "
            "deeper into the floor" % (cfg["model.fin_fold"], FIN_FOLD_LEVEL, FIN_FOLD_LEVEL))
    if cfg["model.spine_sag"] > SPINE_SAG_LEVEL or cfg["model.spine_sag"] < 0.0:
        out.append(
            "model.spine_sag %.2f is off the 0..%.2f rail: past about %.2f deg a joint the "
            "tail droops BELOW his trunk even at the pause and props him up on it -- the "
            "fin-tip problem moved to the other end -- and below 0 it curls up off the floor"
            % (cfg["model.spine_sag"], SPINE_SAG_LEVEL, SPINE_SAG_LEVEL))
    if cfg["model.spine_sag"] and abs(abs(cfg["model.rotation"][0]) - 90.0) > 45.0:
        out.append(
            "model.spine_sag %.1f at roll %.0f: the swim bends the spine SIDEWAYS, and only "
            "on his side does sideways mean down. Near upright it swings the tail across the "
            "ground instead of onto it" % (cfg["model.spine_sag"], cfg["model.rotation"][0]))
    rec, even = cfg["model.recentre"], cfg["model.amplitude_even"]
    if rec and not posed:
        out.append(
            "model.recentre %.2f with model.action=rest levels nothing: a rest spine has no "
            "curl to counter-rotate. It only moves the hash" % rec)
    if rec and not cfg["model.ground_contact"]:
        out.append(
            "model.recentre %.2f with model.ground_contact off: the counter-rotation swings "
            "one end of him DOWN every frame, and only contact re-seats him on the floor -- "
            "without it that end goes through it" % rec)
    if cfg["model.fin_floor"] and not cfg["model.fin_fold"]:
        out.append(
            "model.fin_floor with model.fin_fold 0 pins the lower pectoral at its REST dive, "
            "about 50 deg into the floor: the hold keeps the fold's starting point still, the "
            "fold is what lays it flat")
    if cfg["model.fin_floor"] and not posed and not rec:
        out.append(
            "model.fin_floor on a rest pose with no recentre does NOTHING: the chest is "
            "already at rest and nothing turned the body. It only moves the hash. (On a "
            "POSED frame it acts with or without a recentre -- it takes out the chest's "
            "swing too)")
    if not 0.0 <= rec <= 1.0:
        out.append(
            "model.recentre %.2f is off the 0..1 rail: 1 holds the nose-to-tail chord level, "
            "past it the whole body tips AGAINST the curl, below 0 it tips with it" % rec)
    if even:
        clip = pose.clip_of(cfg["model.action"])
        if clip is None or not clip.wave:
            out.append(
                "model.amplitude_even %.2f does NOTHING on %s: there is no wave down the spine "
                "to even out. It only moves the hash" % (even, cfg["model.action"]))
    if not 0.0 <= even <= 1.0:
        out.append(
            "model.amplitude_even %.2f is off the 0..1 rail: 1 gives every spine joint the "
            "chain's MEAN swing, past it the front out-swings the back (the rear-loading "
            "inverted) and below 0 it loads the rear harder" % even)
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


#: How a redacted `model.blend` is spelled. A value with this prefix is already a content
#: digest and passes through untouched, so a stamp read back off a PNG re-hashes to the
#: hash it claims.
BLEND_DIGEST_PREFIX = "sha256:"

#: The digest when the .blend is not on this machine. Deterministic on purpose (packing
#: cached frames without the model still needs a stable hash), but a DIFFERENT hash from
#: the one the frames were rendered under, so pack.py's pass-hash check refuses rather than
#: shipping a sheet whose provenance nobody can verify.
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
    $JAMALTRON_BLEND, so hashing it says "this render happened in this directory on this
    laptop": three copies of one file gave three config hashes for pixel-identical sheets,
    and the shipped hash reproduced on zero other machines. The content digest is the same
    wherever the same model is.
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

    Two jobs in one substitution: it makes the stamp a fact about the model rather than one
    filesystem (see blend_digest), and keeps an absolute path (here, a private scratch
    directory) out of PNG text chunks that ship in a public repo. Already-redacted values
    pass straight through, so resolving a stamped config and re-hashing it reproduces the
    stamp exactly.
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

    The subtraction is ADDITIVE's whole story: a knob that cannot have changed a pixel stays
    out of the key, so the schema can grow without re-dating shipped art. Everything else,
    including each of those knobs the moment it is touched, hashes exactly as before.
    """
    view = redacted(cfg)
    for key in ADDITIVE:
        if key in view and is_default(key, view[key]):
            del view[key]
    # Same rule for a knob a SWITCH makes dead rather than a default: with ground_contact on,
    # offset z is added and then cancelled (render_jamal.ground_contact), so it cannot move a
    # pixel (MEASURED, 0.5 vs 1.0 render identical). Keeping it in the key re-rendered the
    # same picture under a new hash on every drag of the tuner's height slider. Pinned to 0
    # here; the stamp still records what the file said.
    if view.get("model.ground_contact") and "model.offset" in view:
        view["model.offset"] = list(view["model.offset"][:2]) + [0.0]
    return view


def config_hash(cfg: dict, length: int = 12) -> str:
    """Hash of the WHOLE resolved config. This is the provenance stamp."""
    return hashlib.sha256(canonical(hashable(cfg)).encode()).hexdigest()[:length]


#: Derived numbers a pass's PIXELS depend on, on top of the knobs it declares.
#:
#: The schema cannot express this alone, and the gap served stale pixels:
#: `render.resolution_px` makes the SHADOW pass's resolution a function of
#: `camera.canvas_tiles`, which is declared body-only. At resolution_px = 384, moving
#: canvas_tiles 6.0 -> 4.5 takes the shadow pass from 704 px / 64.00 px-per-tile to
#: 939 px / 85.36; the old pass hash did not move, so cached shadow frames at the wrong
#: pixel scale were composited under the shark. So hash what the pass actually renders
#: with rather than trusting a static dependency list. A formula change here invalidates
#: caches, correctly: if the numbers move, the pixels moved.
PASS_DERIVED = {
    "body": ("body_render_px", "body_resolution_px"),
    "shadow": ("shadow_render_px", "shadow_resolution_px"),
    # The mask rides the body canvas exactly: its frames must crop to the same box as the
    # body's or the two layers slide apart in game.
    "mask": ("body_render_px", "body_resolution_px"),
    "compare": ("sprite_px_per_tile", "body_px_per_tile", "shadow_px_per_tile"),
}


def pass_keys(pass_name: str) -> list[str]:
    if pass_name not in PASSES:
        raise ConfigError(f"unknown pass {pass_name!r}, expected one of {PASSES}")
    return sorted(k for k, spec in SCHEMA.items() if pass_name in spec[2])


def pass_hash(cfg: dict, pass_name: str, length: int = 12) -> str:
    """Hash of everything that CHANGES this pass's pixels: its knobs AND its geometry.

    The cache key. `compare.background` must not throw away 64 Cycles frames; `model.scale`
    must throw away all of them, and so must anything that changes the pass's own
    resolution, even a knob belonging to another pass (see PASS_DERIVED).
    """
    view = hashable(cfg)
    # `if k in view`: hashable() drops an ADDITIVE knob at its default, and a KeyError here
    # would be the schema growing and the CACHE crashing on the same commit.
    subset = {k: view[k] for k in pass_keys(pass_name) if k in view}
    d = derived(cfg)
    subset.update(("derived." + k, d[k]) for k in PASS_DERIVED[pass_name])
    return hashlib.sha256(canonical(subset).encode()).hexdigest()[:length]


def stamp(cfg: dict, extra: dict | None = None) -> dict:
    """The provenance blob written beside every render and into every PNG.

    `config` is the REDACTED view, not the resolved one: `model.blend` is a content digest.
    Nothing downstream wants the path (Blender gets the file on argv), a PNG shipping in a
    public repo must not carry one, and resolving this blob back and re-hashing it must
    return `config_hash` -- which holds because resolve() fills every knob back in from the
    schema, including the ADDITIVE ones the HASH leaves out.

    Redacted rather than hashable on purpose: this blob is also the payload handed to
    Blender and the sidecar a human reads three weeks later, and both want every knob
    written down (`model.action = "rest"` is worth saying even though it hashes as absent).
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

    Preview frames MUST be a subset of the full wheel at the same angles, or the preview
    is a different picture from the sheet it previews and the cache cannot share work.
    `count=8` of 64 gives 0, 8, 16 ... 56.
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
