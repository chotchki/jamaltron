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

Constants are NOT forked from render/factorio_camera.py -- the defaults for camera
pitch, sprite scale and sun geometry are read out of that module at import time, so
there is exactly one place the derived 45-degree camera lives.
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
ENUMS = {
    "mask.mode": ("harness", "silhouette"),
}

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


def hashable(cfg: dict) -> dict:
    """The config as it is HASHED and STAMPED: `model.blend` replaced by its digest.

    Two jobs in one substitution. It makes the hash a fact about the model rather than
    about one filesystem (see blend_digest), and it keeps an absolute path -- which on
    this machine is a private scratch directory -- out of PNG text chunks that ship in a
    public repo. Already-redacted values pass straight through, so resolving a stamped
    config and re-hashing it reproduces the stamp exactly.
    """
    value = cfg["model.blend"]
    if not value.startswith(BLEND_DIGEST_PREFIX) and value != BLEND_ABSENT:
        value = blend_digest(blend_path(cfg))
    return dict(cfg, **{"model.blend": value})


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
    subset = {k: view[k] for k in pass_keys(pass_name)}
    d = derived(cfg)
    subset.update(("derived." + k, d[k]) for k in PASS_DERIVED[pass_name])
    return hashlib.sha256(canonical(subset).encode()).hexdigest()[:length]


def stamp(cfg: dict, extra: dict | None = None) -> dict:
    """The provenance blob written beside every render and into every PNG.

    `config` is the HASHABLE view, not the resolved one: `model.blend` is a content
    digest. Nothing downstream wants the path (Blender is handed the file on argv), a
    PNG that ships in a public repo must not carry one, and resolving this blob back and
    re-hashing it has to return `config_hash` -- which only holds if what is written is
    what was hashed.
    """
    blob = {
        "config_hash": config_hash(cfg),
        "pass_hashes": {p: pass_hash(cfg, p) for p in PASSES},
        "config": unflatten(hashable(cfg)),
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
