#!/usr/bin/env python3
"""Sliders for the knobs you actually tune by eye, and a PLAY button for the flop. Local
page, no dependency.

    uv run --directory tools python render/tune.py            # opens a browser
    uv run --directory tools python render/tune.py --set model.girth=1.3

WHY THIS EXISTS. `art.py --compare` is the right tool for "is this value correct" and the
wrong one for "which value is correct" -- three round trips of render / open the PNG /
describe what is wrong burns ten minutes to move one number by 0.1. This drives the SAME
harness (ac.load -> ac.resolve -> art.render_pass -> art.compare_sheet), so a value found
here is the same value there: same cache, same sheet, same coverage count, same hash.

MEASURED ON THIS MACHINE, and the numbers picked the defaults:

  * 8 body frames, EEVEE Next, 16 samples, 384 px, 4 jobs: 1.5 s render, 1.7 s wall.
  * 4 body frames, same: 1.8-2.3 s. NOT FASTER. The slider loop is Blender LAUNCH-bound,
    not pixel-bound -- four processes cost the same second to start whether they render one
    frame each or two. So `rotations` defaults to 8 (more picture for the same second) and
    the 4 option is there for when you have made him big enough that pixels start to matter.
  * 8 jobs: 21.3 s, a 14x REGRESSION. Eight simultaneous Blenders thrash the Metal context.
    Do not raise --jobs above 4 on this machine looking for speed; you will find the
    opposite, and the tool will feel broken rather than slow.
  * the shadow pass is Cycles and costs 12-15 s. That is the entire reason --compare feels
    slow, so it is OFF here and behind a toggle that says so.

TWO HASHES, ON PURPOSE. The tuner renders with shadow off (and possibly 4 rotations, and
possibly a reduced resolution), and all three of those are knobs, so the hash of what you
are LOOKING AT is not the hash you get after pasting the TOML and running `art.py
--compare`. The page shows both: `tuner` is provenance for the image on screen, `paste` is
what the CLI will stamp once the exported knobs are committed. A tool that showed one
hash would be lying about one of them.

ONE CAVEAT ON `paste`, inherited from artconfig and not fixable here: `model.blend` is in
the config, so it is in the hash, so the paste hash is only reproducible under the SAME
$JAMALTRON_BLEND. MEASURED: one config, 6fa699a20345 with the env var unset and
adce61e09b13 with it set. Same shark either way -- the path is in the key, not the pixels.
Your own shell is consistent, so the round trip holds; a hash mailed to someone else does
not. art.py has always had this, the tuner just promises a hash out loud.

THROWAWAY BUT NOT DISPOSABLE: C.5 needs the same loop for the flop poses, so the slider
list is data (KNOBS) and not markup. Add a row, and the TOML export, the reset button and
the round-trip all pick it up -- TOML_KEYS asserts at import that a new slider cannot
silently fall out of the export.

C.5 ARRIVED AND BROUGHT THE FLOP: pick one of the five shipped clips, scrub a frame of it,
and PLAY it, because a flop is a MOTION and a still frame of one cannot be judged -- frame 7
of a thrash and frame 7 of a shark swimming sideways are the same picture. Plus the bounce,
which is the part that carries it: a per-frame ballistic lift whose whole payoff is that the
shadow separates from the body.

ALL OF IT IS KNOBS NOW. `model.action`, `model.pose_gain`, `model.reparent_head` and the
`bounce` table live in artconfig.SCHEMA, so this page sets knobs and the renderer poses the
rig inside the render it was launching anyway. There is no temp .blend and no third hash any
more: the `tuner` hash is the hash of the picture on screen, including the pose, and `paste`
is that same config minus the tuner's own three render options. The pose USED to be baked
into a copy of the model, which meant the header could not name the hash of what you were
looking at until the bake had run -- that seam is gone.

MEASURED for the flop loop, same machine, a 10-frame loop from cold:
  * broadside (3 directions): 15.1 s to fill, 1.51 s a frame. Full wheel (8): 18.1 s, 1.81 s.
  * re-ticking PLAY after a fill: 0.13 s a frame from the server, and ZERO in the browser,
    which is where it actually plays -- the frames are object URLs by then.
  * 256 px is NOT faster than 384 px, same as 4 rotations was not faster than 8. This loop
    is Blender LAUNCH-bound at both ends and the pixels are free.
  * so BROADSIDE IS NOT A SPEED KNOB. It is 17% cheaper, which is nothing; it is there
    because those are the three directions that answer the question, and eight all-round
    views of a beached shark include five that cannot show you a roll.
  * a knob move during playback stops the loop, re-renders the frame you are on as a still,
    and refills afterwards -- dragging roll against a flopping shark would be 10 renders a
    tick, which is the tool feeling broken rather than slow.

AND THEN IT WAS DRIVEN, which is the whole point of the phase -- every call about this pose so
far was made off still frames. The page's own script, run against a live server with a DOM
stub standing in for the browser (scratchpad, not shipped -- it is a measuring rig, not a
test), at roll 85 / SWIM_FAST / bounce 0.3 / broadside:
  * PLAY LOOPS. Stride 1: 140 swaps in 6.00 s = 23.40 fps against the 24.00 target, mean
    42.7 ms a frame (min 40.4, max 43.4), seven clean passes of f1..f20 and it wraps. Stride
    2: 11.80 fps against 12.00, mean 84.8 ms. The 2.5% shortfall is setInterval's own drift,
    not the frames -- there is no network and no render inside the loop.
  * the fill is the cost and it is paid once: 15.2 s for 20 frames, 14.2 s for 10 (~1.4 s a
    frame, broadside). Re-ticking PLAY on the same knobs: 0.10 s, the whole loop out of the
    page's blob cache.
  * a still is 1.37-1.42 s round trip (median 1.42 over 16 one-knob-at-a-time renders), and
    every one of those 16 came back a DIFFERENT sheet -- no slider on this page is decorative.
  * the export round-trips: the block the server hands you, pasted into the shipped TOML,
    re-hashes to the `paste` hash the header showed (460805dd6aef), and the shipped file with
    nothing pasted still hashes 83d6be794998.
"""

# sys.path, verbatim per tools/README.md -- Python and Blender both put THIS file's own
# directory on sys.path[0], never tools/, and `package = false` means there is no installed
# `render` to fall back on. Cannot be factored into a helper: importing the helper is the
# thing that needs the path fixed.
import pathlib, sys  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse  # noqa: E402
import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
import webbrowser  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from functools import partial  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

from render import art  # noqa: E402
from render import artconfig as ac  # noqa: E402
from render import pose  # noqa: E402
from render import sheets  # noqa: E402


@dataclass(frozen=True)
class Knob:
    """One slider. `key`/`index` address the real knob -- no parallel config format."""

    id: str
    key: str
    index: int | None
    lo: float
    hi: float
    step: float
    label: str
    unit: str
    lo_label: str
    hi_label: str
    hint: str


#: The knobs you tune by eye, in the order they matter. Ranges bracket the shipped values
#: wide enough to find the answer and narrow enough that a drag is not a lottery.
KNOBS = [
    Knob("pivot_x", "model.pivot", 0, -2.0, 0.5, 0.02,
         "rotation axis, fore/aft", "BU", "&larr; TAIL", "NOSE &rarr;",
         "The point the 64 frames spin about, in model units along the body. MORE NEGATIVE "
         "moves the axis BACK toward the tail; LESS NEGATIVE moves it FORWARD toward the "
         "nose. Wrong and he orbits the cell instead of spinning in place: watch the nose "
         "across N / E / S / W, not one frame."),
    Knob("offset_z", "model.offset", 2, 0.0, 1.6, 0.01,
         "height above ground", "tiles", "&darr; sunk", "floating &uarr;",
         "World height, before the 45-degree camera turns it into 0.707x that much "
         "up-screen lift. 0.85 is the measured match to stock's own torso shift. Too high "
         "and he floats off his legs, too low and the legs grow out of his back."),
    Knob("girth", "model.girth", None, 1.0, 2.0, 0.05,
         "girth (width only)", "x", "as sculpted", "chonk &rarr;",
         "Width multiplier, length and height untouched. The canon way to make him bigger "
         "-- the books call him overweight, never longer -- and the cheapest way to cover "
         "the leg mounts at &plusmn;0.78 tiles transverse."),
    Knob("scale", "model.scale", None, 0.5, 1.2, 0.01,
         "overall scale", "x", "&larr; smaller", "bigger &rarr;",
         "Uniform. Watch the canvas warning: the 6-tile body canvas starts CUTTING him "
         "around 1.1, and a clipped frame reads as a flat-topped shark, not as an error."),
    Knob("pitch", "model.rotation", 1, -20.0, 20.0, 0.5,
         "pitch (nose up/down)", "deg", "nose down", "nose up",
         "A few degrees of nose-up reads as swimming rather than dead-fish-on-a-stick. "
         "C.5's jump arc wants a lot more."),
    Knob("yaw", "model.rotation", 2, -180.0, 180.0, 1.0,
         "yaw (spin, INSIDE the roll)", "deg", "&larr; ccw", "cw &rarr;",
         "Spins him about his OWN z BEFORE roll and pitch apply, so on a rolled shark this "
         "swings the nose through the roll axis rather than around the screen. 180 flips him "
         "head-for-tail in his own frame. If what you want is 'turn him round as seen from "
         "above', use base yaw instead: on an UPRIGHT shark the two are identical, on a ROLLED "
         "one they are not, and that difference is the whole reason both sliders exist."),
    Knob("base_yaw", "model.base_yaw", None, -180.0, 180.0, 1.0,
         "base yaw (spin, OUTSIDE the roll)", "deg", "&larr; ccw", "cw &rarr;",
         "Spins the whole already-rolled assembly about WORLD z - the plain turn-him-round "
         "knob. Default 90 is the quarter turn that points a +x nose north, so 270 faces him "
         "the other way. Sitting outside the art rotations is what lets pitch keep meaning "
         "nose-up whatever this is set to."),
    Knob("roll", "model.rotation", 0, -(ac.ROLL_BELLY_UP + 15.0), ac.ROLL_BELLY_UP + 15.0, 1.0,
         "roll (lays him over)", "deg", "&larr; onto one flank", "onto the other &rarr;",
         "THE beached knob: 0 is upright, &plusmn;90 is flat on a flank. Sign picks which "
         "flank, and it is worth looking at both -- the dorsal fin and the harness are not "
         "symmetric. 80-90 IS THE CALL (chotchki, off the C.5 sheets). THE STATED REASON WAS "
         "WRONG AND IS STRUCK: watching the loop at 24 fps measured NO curl - the spine bows "
         "gently, the body goes up and down, two effects at once rather than one composed "
         "motion, and the bounce moves silhouette change only 15.0% -> 15.5%. What the bounce "
         "actually buys is the SHADOW separating (overlap 41.8% -> 18.7%), the only height cue "
         "in the frame. Whether ungained is enough is STILL OPEN - that is what pose_gain is for. "
         "The slider runs 15 deg PAST the 105 where sheet B says he starts reading as dead "
         "belly-up in WATER, and warns from there on -- a limit you cannot cross is a limit you "
         "have to take on faith, and this phase exists to replace faith with looking. Drag it "
         "there once, see it, come back."),
    Knob("bounce_height", "bounce.height", None, 0.0, 0.8, 0.02,
         "bounce height", "tiles", "&larr; sliding", "launched &uarr;",
         "How far off the ground the push-off throws him, in world tiles. 0 pins him to the "
         "floor and he SLIDES, which is the failure this knob exists to fix. THE SHADOW IS "
         "THE POINT: MEASURED at 0.3 tiles, the body rises 14 px up-screen while the shadow "
         "runs 19 px EAST, and that separation is what reads as airborne -- a lift without it "
         "just looks like the sprite growing. Airtime follows from the height (real gravity), "
         "so 0.3 is already 12 of SWIM_FAST's 20 frames in the air."),
    Knob("bounce_phase", "bounce.phase", None, 0.0, 1.0, 0.05,
         "bounce phase", "cycle", "push off at f1", "&larr; late in the cycle",
         "WHERE in the clip's own cycle he pushes off, as a fraction. Launch on the frame of "
         "peak curl and the thrash throws him; launch on a straight frame and the sprite "
         "looks dragged upward. Which frame that is depends on clip, roll and gain, so it is "
         "an eyeball decision -- watch the lift-off against the body, not one still."),
]

#: Keys the TOML export writes, in the order it writes them. Every KNOBS entry must land in
#: one of these or the export would quietly drop a value you spent an afternoon finding --
#: asserted at import, not documented and hoped for.
#:
#: Five of these are NOT sliders (`action`, `pose_gain`, `frame`, `reparent_head`,
#: `bounce.gravity`): they come off the clip selects or off `--set`, and they ride the export
#: because the five shark knobs are meaningless without them. A flop tuned at gain 1.0 and
#: pasted without `action` is the standing shark.
TOML_KEYS = ("model.pivot", "model.scale", "model.girth", "model.offset", "model.rotation",
             "model.action", "model.pose_gain", "model.frame", "model.reparent_head",
             "model.base_yaw",
             "bounce.height", "bounce.phase", "bounce.gravity")
assert {k.key for k in KNOBS} <= set(TOML_KEYS), "a slider is missing from TOML_KEYS"
assert set(TOML_KEYS) <= set(ac.SCHEMA), "the export names a knob the schema does not have"

#: Render options the page can set. All three are real knobs, which is why they move the
#: tuner hash: rotations -> compare.rotations, res -> render.resolution_px (0 = native
#: 384 px), shadow -> compare.show_shadow plus whether the Cycles pass runs at all.
ROTATION_CHOICES = (4, 8)
RES_CHOICES = (0, 256)
#: `reparent` is deliberately absent: it defaults to whatever the config being tuned says,
#: so `--set model.reparent_head=true` is not silently overridden by a page default. page()
#: seeds the checkbox off the committed config for the same reason.
DEFAULT_OPTS = {"rotations": 8, "res": 0, "shadow": False, "view": "wheel"}

# ----------------------------------------------------------------------------- the pose
#
# THE TWO KNOBS LANDED. Selecting a clip is `model.action` and amplifying it is
# `model.pose_gain`, both in artconfig.SCHEMA with ("body", "shadow", "mask") dependencies,
# both read in render_jamal.main() right where `model.rest_pose` is read. This page sets
# them like any other knob; `model.reparent_head` and the `bounce` table came with them.
#
# What that bought, beyond deleting a Blender launch per pose: the page can name the hash of
# the picture it is showing you (it used to be a .blend digest that did not exist until the
# bake ran), and the export is TOML you paste rather than TOML you uncomment.

#: Which of the wheel's directions the BROADSIDE view renders: 3/16, 4/16 and 5/16 of the
#: way round, which is E and E +- 22.5 deg at the shipped rotations.count of 64.
#:
#: Fractions of the wheel rather than literal indices, so this still means "broadside" if
#: rotations.count ever moves off 64. A beached shark only READS as beached from the side:
#: nose-on, the roll is invisible and the thrash is all in screen depth, so five of the
#: wheel's eight views cannot answer the question being asked. NOT a speed knob -- MEASURED,
#: three directions is 17% off a fill, because the loop is Blender launch-bound.
BROADSIDE_SIXTEENTHS = (3, 4, 5)
VIEW_CHOICES = ("wheel", "broadside")

#: PLAY's frame stride. 1 plays every frame of the clip; 6 over a 20-frame cycle is 4 frames,
#: which is where a flop stops being motion and becomes a slideshow.
STRIDE_MIN, STRIDE_MAX = 1, 6

#: The pose the page boots with: none. The committed config is the STANDING shark and the
#: shipped sprites came off it, so the tool has to open on exactly that and never surprise
#: you into tuning a pose you did not ask for.
DEFAULT_POSE = {"clip": pose.REST, "frame": 1, "gain": 1.0, "stride": 2}

#: THE C.5 FLOP, in one click: the recipe as decided, and nothing else.
#:
#: WHY A BUTTON AND NOT THE BOOT STATE. The ask was a roll slider "defaulted to 85", and the
#: page cannot boot there: it opens on the COMMITTED config, which is the standing shark the
#: shipped sprites came off, and that is load bearing twice over -- the header's paste hash
#: reads 83d6be794998 on arrival, which is the live proof that nothing about the flop has
#: touched the art that ships, and `reset to committed` has something to mean. Roll 85 with
#: no clip selected is also a pose nobody wants: a STANDING shark lying on his side.
#:
#: So: one click to the recipe, from wherever the sliders are. It sets only the six knobs the
#: flop is about and deliberately leaves scale, girth, pivot and pitch alone -- those are
#: mid-tuning values half the time, and a preset that silently reverted them would be a
#: preset nobody presses twice. `--set model.rotation=[85,0,0]` still seeds it from the CLI.
FLOP_PRESET = {
    "values": {"roll": 85.0, "bounce_height": 0.3},
    "pose": {"clip": "SWIM_FAST", "frame": 1, "gain": 1.0, "stride": 2},
    "opts": {"view": "broadside", "reparent": True},
}

#: The model's own rest-pose box in tiles at scale 1, read OUT of artconfig.derived()
#: rather than copied from it, so the page's live dimensions cannot drift from the
#: harness's. Same trick for the mount spread: it comes from sheets.LEG_MOUNTS.
_PROBE = ac.derived(ac.resolve({"model": {"scale": 1.0, "girth": 1.0}}, env={}))
MODEL_BU = [_PROBE["shark_length_tiles"], _PROBE["shark_width_tiles"],
            _PROBE["shark_height_tiles"]]
MOUNT_HALF_WIDTH = max(abs(mount[0]) for mount, _ in sheets.LEG_MOUNTS)
MOUNT_SPAN_Y = (min(mount[1] for mount, _ in sheets.LEG_MOUNTS),
                max(mount[1] for mount, _ in sheets.LEG_MOUNTS))

SHEET_NAME_RE = re.compile(r"^compare_[0-9a-f]{6,32}\.png$")


# --------------------------------------------------------------------------- config i/o


def values_of(cfg: dict) -> dict:
    """The slider values a resolved config implies."""
    return {k.id: (cfg[k.key][k.index] if k.index is not None else cfg[k.key])
            for k in KNOBS}


def apply_values(base: dict, values: dict) -> dict:
    """base + slider values -> a new resolved config. Clamped to the slider ranges, so a
    hand-rolled POST cannot ask for scale 400 and a 20-minute render."""
    cfg = {key: (list(v) if isinstance(v, list) else v) for key, v in base.items()}
    for k in KNOBS:
        if k.id not in values:
            continue
        v = float(values[k.id])
        if not math.isfinite(v):
            raise ac.ConfigError(f"{k.id}: {values[k.id]!r} is not a finite number")
        v = min(max(v, k.lo), k.hi)
        if k.index is None:
            cfg[k.key] = v
        else:
            cfg[k.key][k.index] = v
    return cfg


def apply_opts(cfg: dict, opts: dict) -> dict:
    """The three render options, as the knobs they really are."""
    cfg = {key: (list(v) if isinstance(v, list) else v) for key, v in cfg.items()}

    def choice(name, allowed):
        """Fall back, never raise. `rotations=999` already fell back and `rotations='x'`
        raised -- the same class of junk getting two different answers, and only one of
        them is an answer. The page can only send what is in the select; anything else is
        a hand-rolled POST or a tab left open across a version, and neither deserves a
        stack trace."""
        try:
            want = int(opts.get(name, DEFAULT_OPTS[name]))
        except (TypeError, ValueError):
            return DEFAULT_OPTS[name]
        return want if want in allowed else DEFAULT_OPTS[name]

    cfg["compare.rotations"] = choice("rotations", ROTATION_CHOICES)
    cfg["render.resolution_px"] = choice("res", RES_CHOICES)
    cfg["compare.show_shadow"] = bool(opts.get("shadow", False))
    cfg["model.reparent_head"] = reparent_of(cfg, opts)
    if view_of(opts) == "broadside":
        # The COUNT has to follow the view or the hash claims eight cells for a three-cell
        # sheet. Which three is not expressible as a knob (there is no "directions" knob,
        # only a count), so the page and the terminal both name them; see view_frames.
        cfg["compare.rotations"] = len(BROADSIDE_SIXTEENTHS)
    return cfg


def reparent_of(cfg: dict, opts: dict) -> bool:
    """The rig-fix checkbox, falling back to the CONFIG's own value and not to False.

    Two reasons it is not just `opts.get("reparent", False)`. `--set
    model.reparent_head=true` has to survive a POST that does not mention the checkbox, and
    the EXPORT has to carry whatever is ticked -- a block that says `reparent_head = false`
    under a picture rendered with it on is the export lying about the picture.
    """
    return bool(opts.get("reparent", cfg["model.reparent_head"]))


def view_of(opts: dict) -> str:
    """"wheel" or "broadside", falling back rather than raising -- same rule as apply_opts."""
    want = str(opts.get("view") or DEFAULT_OPTS["view"])
    return want if want in VIEW_CHOICES else DEFAULT_OPTS["view"]


def view_frames(cfg: dict, opts: dict) -> list[int]:
    """Which directions to render. The wheel's even spacing, or three broadside ones.

    ac.frame_indices() always starts at index 0 -- NORTH, nose-on -- which is the one
    direction a rolled-over shark tells you nothing from. Broadside asks for the three
    directions the flop actually reads in, which is also 3 renders instead of 8.
    """
    if view_of(opts) != "broadside":
        return ac.frame_indices(cfg, cfg["compare.rotations"])
    total = cfg["rotations.count"]
    return sorted({int(round(total * s / 16.0)) % total for s in BROADSIDE_SIXTEENTHS})


def normalize_pose(state: dict | None) -> dict:
    """The pose controls, clamped to what the model can actually do.

    Falls back, never raises, for the reason apply_opts' `choice` does: the page can only
    send what is in its own selects, so anything else is a stale tab or a hand-rolled POST,
    and neither deserves a stack trace. An unknown clip id is REST -- the standing shark --
    because that is the one fallback that cannot render something misleading.
    """
    state = state if isinstance(state, dict) else {}
    clip_id = str(state.get("clip") or pose.REST)
    if clip_id != pose.REST and pose.clip_of(clip_id) is None:
        clip_id = pose.REST
    try:
        stride = min(max(int(state.get("stride", DEFAULT_POSE["stride"])),
                         STRIDE_MIN), STRIDE_MAX)
    except (TypeError, ValueError):
        stride = DEFAULT_POSE["stride"]
    return {"clip": clip_id,
            "frame": pose.clamp_frame(clip_id, state.get("frame", 1)),
            "gain": pose.clamp_gain(state.get("gain", 1.0)),
            "stride": stride}


def posed(cfg: dict, p: dict) -> dict:
    """cfg + the page's pose state -> a cfg that RENDERS that pose. Pure knobs, no Blender.

    THREE KNOBS MOVE TOGETHER and they have to: `model.action` names the clip, `model.frame`
    picks the frame of it, `model.pose_gain` amplifies it. Set the action and leave the frame
    behind and you are looking at frame 1 of a thrash while the page's slider says 12.

    Cheap enough to call on every slider tick, which is what lets quote() report the real
    hash of the picture instead of promising one after the render.
    """
    cfg = {key: (list(v) if isinstance(v, list) else v) for key, v in cfg.items()}
    cfg["model.action"] = p["clip"]
    if p["clip"] == pose.REST:
        return cfg
    cfg["model.pose_gain"] = p["gain"]
    cfg["model.frame"] = p["frame"]
    return cfg


def pose_report(p: dict) -> dict:
    """The pose as the page reads it: the clip's real range, the loop it implies, and how
    long that loop runs. Every duration is a frame count over pose.FPS, so a number on the
    page cannot drift from the frames it is counting."""
    c = pose.clip_of(p["clip"])
    loop = pose.loop_frames(p["clip"], p["stride"])
    return {"clip": p["clip"], "frame": p["frame"], "gain": p["gain"], "stride": p["stride"],
            "posed": p["clip"] != pose.REST,
            "action": c.action if c else "",
            "lo": c.lo if c else 1, "hi": c.hi if c else 1,
            "loop": loop, "loop_ms": pose.loop_ms(p["stride"]),
            "loop_seconds": round(len(loop) * p["stride"] / pose.FPS, 3)}


def pose_warnings(cfg: dict, p: dict, committed: dict, mismatches=()) -> list[str]:
    """What is legal, posed, and will bite AND is not already in ac.warnings().

    Only two things qualify. The pivot one is the whole reason C.5 has a tuning task at all,
    and it can only be asked here because it is about the value being INHERITED from the
    committed file -- the schema has no idea what you started from. The other is the clip
    table drifting from the model, which only a render can report.
    """
    if p["clip"] == pose.REST:
        return []
    out = []
    if list(cfg["model.pivot"]) == list(committed["model.pivot"]):
        out.append(
            "model.pivot %s is the REST pose's axis, tuned by eye against the STRAIGHT "
            "shark (C.17). A posed one does not spin about the same point -- this pivot is "
            "not wrong yet, it is UNVERIFIED for the flop, and the frames will orbit the "
            "cell if it is off. Find the flop's own, the same way: watch the nose across "
            "the columns, not one frame."
            % (", ".join("%.4g" % v for v in cfg["model.pivot"])))
    out += ["clip table vs the model: " + m for m in (mismatches or ())]
    return out


def render_warnings(log: str) -> list:
    """WARN lines the RENDER itself produced, lifted out of the harness output for the box.

    Some things only a render can know, and they are the ones that bite hardest. At roll 85
    with the bounce on, the posed body reaches 0.28 tiles BELOW the ground plane -- the shadow
    catcher sits at z=0 and quietly slices him there, which reads as a bad shadow rather than
    as a body in the wrong place, and no amount of config checking can see it because it
    depends on the pose, the roll and the scale together. render_jamal prints it; art.py now
    lets it through however quiet the pass is; this puts it where the other warnings are,
    because the log panel is a <details> nobody opens while dragging a slider.

    Deduped: four jobs over two passes say the same thing four times.
    """
    seen, out = set(), []
    for line in log.splitlines():
        line = line.strip()
        if line.startswith("WARN ") and line not in seen:
            seen.add(line)
            out.append("the render says: " + line[len("WARN "):])
    return out


def _num(v: float) -> str:
    """A float as TOML. Always carries a decimal point: `0` is an INT in TOML and the
    schema would coerce it back, but a config that reads `offset = [0, 0, 0.85]` invites
    the next reader to think the knob is an integer one."""
    s = "%.6g" % v
    if "." not in s and "e" not in s and "E" not in s:
        s += ".0"
    return s


def _toml_value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_num(x) for x in v) + "]"
    return _num(v)


def seed(committed: dict, sets: dict) -> tuple[dict, dict, str, dict]:
    """`--set` -> (committed, slider start values, export note, clamped knobs).

    --set has TWO jobs, because the sliders own five of the schema's knobs and --set takes
    any of them. On one of the five it seeds that slider. On ANYTHING ELSE it used to land
    in `start`, which is read for nothing but slider values, so `--set camera.canvas_tiles=8`
    moved no pixel and printed no complaint -- a silent no-op on the flag whose whole job is
    "carry on from yesterday". Those go into `committed` instead, where every render and
    both hashes pick them up (art.py's own meaning of --set), and they come back as a note
    for the export header, because the five exported lines cannot carry them.

    Seeded PAST a slider end is the other quiet one: the page paints 1.5 in the number box,
    the range input pins itself at 1.2, and the render clamps to 1.2 -- three numbers, one
    of them a lie. Clamp here instead and return what got moved so the terminal can say so.

    AND THE EXTRAS ARE VALIDATED, which they were not until C.5 gave the schema its second
    enum. `committed` arrives already resolved, so updating a dict with `{"model.action":
    "SWIM_FASTT"}` writes straight past every check ac.resolve() does: the name is spelled
    right, so the unknown-knob suggester never sees it, and the tuner would boot, print the
    typo in its own header note, and hand you a Blender traceback on the first render. Round
    the extras back through resolve() -- one call, artconfig's own message, before the server
    binds a port. art.py has always behaved this way because its --set goes through resolve;
    this is the tuner catching up rather than a new rule.
    """
    slider_keys = {k.key for k in KNOBS}
    extra = {key: value for key, value in sets.items() if key not in slider_keys}
    if extra:
        # env={} because model.blend is already resolved in `committed` and this call is a
        # type/enum check on the extras, not a second config to render from.
        ac.resolve(ac.unflatten(extra), env={})
    committed = dict(committed)
    committed.update(extra)
    start = apply_values(committed, values_of(committed))
    for key, value in sets.items():
        if key not in extra:
            start[key] = value
    asked = values_of(start)
    start = apply_values(start, asked)            # apply_values is the clamp
    got = values_of(start)
    pinned = {k.id: (asked[k.id], got[k.id]) for k in KNOBS if asked[k.id] != got[k.id]}
    note = ""
    if extra:
        # The header hash is computed WITH these, because the render was. Say so, or the
        # block reads as "paste this, get this hash" and the hash comes back different.
        # Worded to read the same in the terminal at startup and as a comment in the block.
        note = ("also --set, in every render and in the hash but NOT in the exported "
                "[model] lines (add them by hand or the pasted hash will differ): "
                + " ".join("%s=%s" % (key, value) for key, value in sorted(extra.items())))
    return committed, start, note, pinned


def _toml_scalar(v) -> str:
    """One TOML value. Bools and strings are values too, now that the export carries
    `action = "SWIM_FAST"` and `reparent_head = true` -- `_num` on either of those is a
    TypeError, and on a bool it is the number 1."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return '"%s"' % v
    if isinstance(v, int) and not isinstance(v, float):
        return str(v)
    return _toml_value(v)


def toml_block(cfg: dict, paste_hash: str, note: str = "", p: dict | None = None,
               tuner_hash: str = "") -> str:
    """The lines to paste into render/jamaltron.toml. Nothing else, no reformatting of
    the file's comments, and NEVER `model.blend` -- that path is machine-local and
    gitignored, and pasting it would break the config for everyone else.

    GROUPED BY TABLE, because the export outgrew `[model]`: the bounce is its own table and
    emitting `height = 0.3` under `[model]` would be a fatal `unknown knob model.height` in
    the file it lands in. The groups come out in TOML_KEYS order, one header per table.

    REPLACE, do not append. Both paste modes were checked against `art.py --compare` and
    both come back with the hash in the header; appending to the end of the file does not,
    it is `tomllib.TOMLDecodeError: Cannot declare ('model',) twice` and it arrives as a
    raw traceback. Hence the second comment line -- the instruction rides WITH the lines,
    because the clipboard is the only part of this that reaches the other window.

    `p` and `tuner_hash` are still taken because the page passes them, and they still do one
    job each: the pose state is what `cfg` was posed FROM (so the block can say what clip
    this is in words), and the tuner hash rides in a comment when the picture on screen was
    rendered at tuner-only options. Neither is a knob any more -- the pose is in `cfg`.
    """
    p = normalize_pose(p)
    clip = pose.clip_of(cfg["model.action"])
    head = ["# tuned in render/tune.py %s -- config %s"
            % (time.strftime("%Y-%m-%d %H:%M"), paste_hash)]
    if clip is not None:
        head.append("# %s (%s), frame %d of %d-%d @ %d fps (%.2f s cycle), gain %s"
                    % (clip.id, clip.action, cfg["model.frame"], clip.lo, clip.hi, pose.FPS,
                       clip.seconds, _num(cfg["model.pose_gain"])))
    head.append("# REPLACE these tables in render/jamaltron.toml, or just these keys inside "
                "them. Appending is a TOML error (model declared twice).")
    if note:
        head.append("# " + note)
    table = None
    for key in TOML_KEYS:
        section, leaf = key.split(".", 1)
        if section != table:
            head.append("[%s]" % section)
            table = section
        head.append("%s = %s" % (leaf, _toml_scalar(cfg[key])))
    if tuner_hash and tuner_hash != paste_hash:
        head.append("# the picture this came off hashes %s -- the difference is the tuner's "
                    "own render options (rotations, resolution, shadow), not the pose."
                    % tuner_hash)
    return "\n".join(head) + "\n"


# ------------------------------------------------------------------------------- tuner


class Tuner:
    """Render state for one server. One render at a time, latest values win."""

    def __init__(self, committed: dict, start: dict, jobs: int, note: str = ""):
        self.committed = committed
        self.start = start
        self.jobs = jobs
        #: Rides in the exported TOML header. Non-empty when `--set` moved a knob no slider
        #: owns: that knob IS in every render and both hashes, and it is NOT in the five
        #: exported lines, so the export has to say so or the paste silently loses it.
        self.note = note
        self.render_lock = threading.Lock()
        self.seq_lock = threading.Lock()
        #: newest seq seen PER PAGE SESSION. Not one global counter: a browser refresh
        #: restarts the page's seq at 1, and against a global high-water mark every
        #: request from the reloaded page is "older" than one the previous page already
        #: sent -- so the tuner would supersede everything forever and show no image,
        #: which is the single most obvious thing a person does to an unresponsive page.
        #: Per session, two tabs also each end on their own latest values.
        self.latest_seq: dict[str, int] = {}
        self.renders = 0

    # -- the cheap path: numbers and text, no Blender ---------------------------------

    def quote(self, values: dict, opts: dict, p: dict | None = None) -> dict:
        """Everything a slider move can answer without rendering: both hashes, the derived
        dimensions, the TOML to paste, and every warning.

        IT CAN ANSWER THE TUNER HASH NOW, pose and all, because posing is setting three knobs
        rather than baking a .blend. That used to be a promise the page could only keep after
        a render.

        `paste_cfg` carries the pose and NOT the tuner's three render options, which is
        exactly the config the exported block describes; `cfg` adds the options and is what
        renders. Hence two hashes, and the header names both.
        """
        p = normalize_pose(p)
        paste_cfg = posed(apply_values(self.committed, values), p)
        # The rig fix rides with the POSE, not with the tuner's render options, because it is
        # a knob the export has to carry. apply_opts sets it again from the same opts, so the
        # two configs cannot disagree about it.
        paste_cfg["model.reparent_head"] = reparent_of(paste_cfg, opts)
        cfg = apply_opts(paste_cfg, opts)
        paste_hash = ac.config_hash(paste_cfg)
        tuner_hash = ac.config_hash(cfg)
        d = ac.derived(cfg)
        return {
            "tuner_hash": tuner_hash,
            "paste_hash": paste_hash,
            "derived": {key: d[key] for key in
                        ("shark_length_tiles", "shark_width_tiles", "shark_height_tiles",
                         "body_resolution_px", "body_px_per_tile",
                         "bounce_lift_tiles", "bounce_peak_tiles", "bounce_airtime_frames",
                         "bounce_cycle_frames", "bounce_lift_up_screen_tiles")},
            "toml": toml_block(paste_cfg, paste_hash, self.note, p, tuner_hash),
            "pose": pose_report(p),
            "view": {"name": view_of(opts), "frames": view_frames(cfg, opts)},
            "warnings": ac.warnings(cfg) + pose_warnings(cfg, p, self.committed),
        }

    # -- the expensive path ------------------------------------------------------------

    def bump(self, session: str, seq: int) -> None:
        with self.seq_lock:
            self.latest_seq[session] = max(self.latest_seq.get(session, 0), seq)

    def superseded(self, session: str, seq: int) -> bool:
        with self.seq_lock:
            return seq < self.latest_seq.get(session, 0)

    def render(self, seq: int, values: dict, opts: dict, session: str = "",
               p: dict | None = None) -> dict:
        """Render one compare sheet. Never raises -- a bad knob has to come back as text
        on the page, because a tuner that dies on a value you were curious about is worse
        than no tuner.

        SUPERSEDING, and it is checked TWICE. Once before taking the render lock (drop a
        request that was already stale when it arrived) and once after (drop one that went
        stale while an earlier render held the lock). Blender itself is not interruptible
        here -- art.run_blender is a blocking subprocess.run -- so the guarantee is "the
        image always ends on the newest values", bought by never STARTING stale work,
        not by killing work in flight. At 1.7 s a frame-set that is the right trade.
        """
        self.bump(session, seq)
        if self.superseded(session, seq):
            return {"seq": seq, "superseded": True}
        with self.render_lock:
            if self.superseded(session, seq):
                return {"seq": seq, "superseded": True}
            return self._render_locked(seq, values, opts, p)

    def _render_locked(self, seq: int, values: dict, opts: dict, p: dict | None = None) -> dict:
        t0 = time.time()
        quote = None
        buf = io.StringIO()
        try:
            quote = self.quote(values, opts, p)
            p = normalize_pose(p)
            cfg = apply_opts(posed(apply_values(self.committed, values), p), opts)
            frames = view_frames(cfg, opts)
            # stdout AND stderr: art.py reports through the first and blender's own
            # failure text goes to the second, and the failure text is the half you need.
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                bodydir, body_stats = art.render_pass(cfg, "body", frames,
                                                      cfg["render.preview_samples"],
                                                      jobs=self.jobs)
                passes = [("body", cfg["render.engine"], cfg["render.preview_samples"])]
                shadowdir = None
                if cfg["compare.show_shadow"]:
                    shadowdir, _ = art.render_pass(cfg, "shadow", frames,
                                                   cfg["render.shadow_samples"],
                                                   jobs=self.jobs)
                    passes.append(("shadow", cfg["render.shadow_engine"],
                                   cfg["render.shadow_samples"]))
                png = art.compare_sheet(cfg, bodydir, shadowdir, frames, passes)
            _, sidecar = art.sheet_paths(cfg, "compare")
            blob = json.loads(sidecar.read_text())
            cov = blob.get("mount_coverage", {})
            out = dict(quote)
            out.update({
                "seq": seq, "ok": True, "superseded": False,
                "image": "/sheet?f=" + pathlib.Path(png).name,
                "seconds": round(time.time() - t0, 2),
                "frames": frames,
                # The render's OWN warnings ride with the config's. A buried body or a
                # clipped frame is only knowable from the pixels, and it must not be a line
                # in a <details> nobody opens mid-drag.
                "warnings": (ac.warnings(cfg) + pose_warnings(cfg, p, self.committed)
                             + render_warnings(buf.getvalue())),
                # The box of what was RENDERED, in tiles, unioned over the directions on
                # screen. artconfig.derived() reports the REST box off a constant, which is
                # right for the standing shark and wrong the moment he thrashes -- and the
                # bounce grows it, so the page has to say both.
                "box_tiles": body_stats.get("box_tiles"),
                # Whether a Blender actually ran. If every frame came from the cache the box
                # was not re-measured and the render printed no warnings of its own -- the
                # page has to say that rather than leave the PREVIOUS render's box sitting
                # under a different picture. (Persisting the box per frame in the pass dir
                # would fix it properly; it needs a per-frame box out of render_jamal, which
                # is more than this phase should touch.)
                "rendered": body_stats.get("rendered", 0),
                "coverage_line": cov.get("line", ""),
                "coverage": cov.get("per_frame", []),
                "selfcheck": sheets.selfcheck_line(blob.get("mount_selfcheck", {"ran": False,
                                                            "why": "not in sidecar"})),
                "log": buf.getvalue(),
            })
        except (Exception, SystemExit) as exc:                 # SystemExit: art.py's own
            out = dict(quote or {})                            # blender-failed path
            out.update({
                "seq": seq, "ok": False, "superseded": False,
                "seconds": round(time.time() - t0, 2),
                "error": "%s: %s" % (type(exc).__name__, exc),
                "log": buf.getvalue() + "\n" + traceback.format_exc(limit=4),
            })
        self.renders += 1
        # The terminal is the other half of the tool: it gets the harness's own report,
        # the timing, and the TOML, so a value found here is one copy-paste OR one scroll
        # -back away from being committed.
        rep = out.get("pose") or {}
        sys.stdout.write("\n[tune #%d seq %d%s] %s in %.2fs\n%s"
                         % (self.renders, seq,
                            (" %s f%d x%.2f" % (rep["clip"], rep["frame"], rep["gain"]))
                            if rep.get("posed") else "",
                            "ok" if out.get("ok") else "FAILED",
                            out["seconds"], out.get("log", "")))
        if out.get("ok"):
            sys.stdout.write("  %s\n" % out.get("coverage_line", ""))
            sys.stdout.write("\n" + out.get("toml", "") + "\n")
        else:
            sys.stdout.write("  ERROR %s\n" % out.get("error"))
        sys.stdout.flush()
        return out


# -------------------------------------------------------------------------------- http


class Handler(BaseHTTPRequestHandler):
    server_version = "jamaltron-tune"

    def __init__(self, *a, tuner: Tuner = None, **kw):
        self.tuner = tuner
        super().__init__(*a, **kw)

    # The default handler log writes a line per request to stderr, which buries the
    # harness's own output -- and the harness's output is the point of the terminal half.
    def log_message(self, fmt, *args):
        pass

    # -- plumbing ---------------------------------------------------------------------

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode() or "{}")

    # -- routes -----------------------------------------------------------------------

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/":
            return self._send(200, page(self.tuner).encode(), "text/html; charset=utf-8")
        if path == "/sheet":
            return self._sheet(query)
        return self._send(404, b"no", "text/plain")

    def do_POST(self):
        path = self.path.partition("?")[0]
        # The SHAPE check belongs in here with the parse. A body of `null`, `5`, `"hi"` or
        # `[1,2]` parses fine and then blows up on `.get` -- and an exception escaping
        # do_POST is not an error page, it is a dropped connection plus a raw traceback in
        # the terminal that the harness report is supposed to own. Same for a `values` that
        # is a string: `"scale" not in "abc"` is a legal substring test, so every slider
        # silently fell back to the committed value and the page looked like it worked.
        try:
            body = self._body()
            if not isinstance(body, dict):
                raise TypeError("expected a JSON object, got %s" % type(body).__name__)
            values = body.get("values") or {}
            opts = body.get("opts") or {}
            pose_state = body.get("pose") or {}
            for name, obj in (("values", values), ("opts", opts), ("pose", pose_state)):
                if not isinstance(obj, dict):
                    raise TypeError("`%s` must be a JSON object, got %s"
                                    % (name, type(obj).__name__))
        except Exception as exc:
            return self._json({"error": "bad request body: %s" % exc}, 400)
        try:
            if path == "/quote":
                return self._json(self.tuner.quote(values, opts, pose_state))
            if path == "/toml":
                q = self.tuner.quote(values, opts, pose_state)
                sys.stdout.write("\n" + q["toml"] + "\n")
                sys.stdout.flush()
                return self._json({"toml": q["toml"]})
            if path == "/render":
                return self._json(self.tuner.render(int(body.get("seq") or 0), values, opts,
                                                    str(body.get("session") or ""),
                                                    pose_state))
        except (Exception, SystemExit) as exc:
            # Even the cheap paths report as text. The server does not get to die because
            # a slider sent something the schema hated.
            return self._json({"error": "%s: %s" % (type(exc).__name__, exc),
                               "log": traceback.format_exc(limit=4)}, 200)
        return self._send(404, b"no", "text/plain")

    def _sheet(self, query: str):
        name = ""
        for part in query.split("&"):
            key, _, value = part.partition("=")
            if key == "f":
                name = value
        if not SHEET_NAME_RE.match(name):
            return self._send(400, b"not a sheet name", "text/plain")
        path = art.out_root(self.tuner.committed) / "sheets" / name
        if not path.exists():
            return self._send(404, b"no such sheet", "text/plain")
        self._send(200, path.read_bytes(), "image/png")


# -------------------------------------------------------------------------------- page


PAGE = r"""<!doctype html>
<meta charset="utf-8"><title>jamaltron tuner</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root { color-scheme: dark; --bg:#16181a; --panel:#1e2124; --line:#2e3236; --ink:#dfe3e7;
         --dim:#8b9298; --hot:#ff40be; --warn:#ffb454; --bad:#ff6b6b; --ok:#7bd88f; }
 * { box-sizing: border-box; }
 body { margin:0; background:var(--bg); color:var(--ink);
        font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace; }
 header { padding:10px 14px; border-bottom:1px solid var(--line); display:flex;
          gap:14px; align-items:baseline; flex-wrap:wrap; }
 h1 { font-size:14px; margin:0; letter-spacing:.06em; text-transform:uppercase; }
 .wrap { display:flex; gap:14px; align-items:flex-start; padding:14px; flex-wrap:wrap; }
 .col { flex:1 1 360px; min-width:min(100%,340px); max-width:520px; }
 .grow { flex:3 1 560px; min-width:min(100%,340px); max-width:100%; }
 .panel { background:var(--panel); border:1px solid var(--line); border-radius:6px;
          padding:12px; margin-bottom:12px; }
 .k { margin-bottom:16px; }
 .k label { display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
 .k .name { font-weight:600; }
 .k .ends { display:flex; justify-content:space-between; color:var(--dim); font-size:11px;
            margin-top:2px; }
 .k input[type=range] { width:100%; margin:4px 0 0; accent-color:var(--hot); }
 .k .val { display:flex; gap:6px; align-items:center; }
 .k input[type=number] { width:88px; background:#121416; color:var(--ink);
                         border:1px solid var(--line); border-radius:4px; padding:2px 4px;
                         font:inherit; text-align:right; }
 .k .hint { color:var(--dim); font-size:11px; margin-top:4px; display:none; }
 .k.open .hint { display:block; }
 .why { background:none; border:0; color:var(--dim); cursor:pointer; font:inherit;
        padding:0 2px; }
 .opts { display:flex; gap:14px; flex-wrap:wrap; align-items:center; }
 .opts label { display:flex; gap:5px; align-items:center; cursor:pointer; }
 button { background:#2a2e32; color:var(--ink); border:1px solid var(--line);
          border-radius:4px; padding:5px 10px; font:inherit; cursor:pointer; }
 button:hover { background:#343a3f; }
 button.primary { border-color:var(--hot); }
 .row { display:flex; gap:8px; flex-wrap:wrap; }
 #img { width:100%; border-radius:4px; display:block; background:#0d0f10; }
 #img.stale { opacity:.45; }
 .num { color:var(--ok); }
 .dim { color:var(--dim); }
 .hot { color:var(--hot); }
 .bad { color:var(--bad); }
 .warnbox, .errbox { margin-top:8px; padding:8px; border-radius:4px; white-space:pre-wrap;
                     display:none; }
 .warnbox { border:1px solid var(--warn); color:var(--warn); }
 .errbox { border:1px solid var(--bad); color:var(--bad); }
 pre { margin:6px 0 0; white-space:pre-wrap; background:#121416; border:1px solid var(--line);
       border-radius:4px; padding:8px; color:var(--ink); max-height:40vh; overflow:auto; }
 table.cov { border-collapse:collapse; margin-top:6px; font-size:11px; }
 table.cov td { border:1px solid var(--line); padding:1px 5px; }
 .status { margin-left:auto; }
 .slow { color:var(--warn); }
</style>
<header>
  <h1>jamaltron tuner</h1>
  <span class="dim">tuner <span id="htuner" class="num">-</span></span>
  <span class="dim">paste <span id="hpaste" class="num">-</span></span>
  <span class="status" id="status">starting</span>
</header>
<div class="wrap">
  <div class="col">
    <div class="panel">
      <div class="opts">
        <label>clip <select id="clip"></select></label>
        <label><input type="checkbox" id="play"> <b>PLAY</b>
          <span class="dim" id="playing"></span></label>
        <label>stride <select id="stride"></select></label>
        <label>view <select id="view"></select></label>
      </div>
      <div class="dim" id="clipnote" style="margin-top:7px"></div>
      <div class="k" id="k_frame" style="margin-top:12px">
        <label><span class="name">frame <button class="why" data-k="frame">?</button></span>
          <span class="val"><input type="number" id="n_frame" step="1">
            <span class="dim" id="frameof"></span></span></label>
        <input type="range" id="r_frame" step="1">
        <div class="ends"><span id="framelo">-</span>
          <span class="dim">model.frame</span><span id="framehi">-</span></div>
        <div class="hint">Which frame of the selected clip, at 24 fps. A STILL cannot tell a
          flop from a shark swimming sideways -- frame 7 of either is the same picture -- so
          scrub it, then hit PLAY and judge the motion.</div>
      </div>
      <div class="k" id="k_gain">
        <label><span class="name">pose gain <button class="why" data-k="gain">?</button></span>
          <span class="val"><input type="number" id="n_gain"><span class="dim">x</span></span></label>
        <input type="range" id="r_gain">
        <div class="ends"><span>as bought</span>
          <span class="dim">model.pose_gain</span><span>thrashing &rarr;</span></div>
        <div class="hint">Every bone's rotation pushed away from rest by this factor. 1.0 is
          the clip as the seller shipped it and 1.0 is what SHIPS -- at roll 80-90 the bounce
          carries the thrash, so the gain a roll-30 flop needed is not needed here. The knob
          is here so gain can be ruled OUT by looking rather than assumed. MEASURED: the rig
          survives 2.6x with no mesh tearing -- past that, check the neck and the tail tip
          before you believe the frame.</div>
      </div>
      <label class="opts" style="margin-top:4px"><input type="checkbox" id="reparent">
        reparent HEAD to SPINE_01 <span class="dim">(C.18a: HEAD is a ROOT bone, so the
        snout is welded to world space until this is on)</span></label>
      <div class="dim" id="posenote"></div>
    </div>
    <div class="panel" id="knobs"></div>
    <div class="panel">
      <div class="opts">
        <label>rotations
          <select id="rotations"></select></label>
        <label>res
          <select id="res"></select></label>
        <label><input type="checkbox" id="shadow">
          shadow <span class="slow">(CYCLES, +12-15s)</span></label>
      </div>
      <div class="row" style="margin-top:10px">
        <button class="primary" id="rerender">re-render</button>
        <button id="flop" title="SWIM_FAST, roll 85, gain 1.0, bounce 0.3, HEAD reparented,
broadside. Leaves scale / girth / pivot / pitch where you have them.">flop preset</button>
        <button id="reset">reset to committed</button>
        <button id="copy">copy TOML</button>
      </div>
    </div>
    <div class="panel">
      <div class="dim">paste into render/jamaltron.toml</div>
      <pre id="toml">-</pre>
    </div>
  </div>
  <div class="grow">
    <div class="panel">
      <div id="dims"></div>
      <div id="cover" style="margin-top:4px"></div>
      <div class="warnbox" id="warn"></div>
      <div class="errbox" id="err"></div>
    </div>
    <div class="panel">
      <img id="img" alt="compare sheet">
      <div class="dim" id="shotinfo" style="margin-top:6px"></div>
      <table class="cov" id="covtable"></table>
    </div>
    <details class="panel"><summary class="dim">harness log</summary><pre id="log">-</pre></details>
  </div>
</div>
<script>
const BOOT = __BOOT__;
const $ = id => document.getElementById(id);
const values = Object.assign({}, BOOT.start);
const opts = Object.assign({}, BOOT.opts);
const posest = Object.assign({}, BOOT.pose);
// One id per page LOAD. Superseding is scoped to it, so a refresh starts a fresh count
// instead of sitting forever behind the previous page's high-water mark.
const SESSION = Math.random().toString(36).slice(2) + "-" + Date.now().toString(36);
let seq = 0, applied = 0, inflight = false, pending = false, tStart = 0, lastBox = "";

// ---- sliders -------------------------------------------------------------------------
$("knobs").innerHTML = BOOT.knobs.map(k => `
  <div class="k" id="k_${k.id}">
    <label><span class="name">${k.label} <button class="why" data-k="${k.id}">?</button></span>
      <span class="val"><input type="number" id="n_${k.id}" min="${k.lo}" max="${k.hi}"
        step="${k.step}"><span class="dim">${k.unit}</span></span></label>
    <input type="range" id="r_${k.id}" min="${k.lo}" max="${k.hi}" step="${k.step}">
    <div class="ends"><span>${k.lo_label}</span><span class="dim">${k.key}${
      k.index === null ? "" : "[" + k.index + "]"}</span><span>${k.hi_label}</span></div>
    <div class="hint">${k.hint}</div>
  </div>`).join("");
$("rotations").innerHTML = BOOT.rotation_choices.map(r =>
  `<option value="${r}">${r}</option>`).join("");
$("res").innerHTML = BOOT.res_choices.map(r =>
  `<option value="${r}">${r === 0 ? "384 (native)" : r + " (fast)"}</option>`).join("");

// ---- the pose controls ---------------------------------------------------------------
$("clip").innerHTML = [`<option value="${BOOT.rest}">rest pose (as shipped)</option>`].concat(
  BOOT.clips.map(c => `<option value="${c.id}">${c.id} &mdash; ${c.span}f, ${
    c.seconds.toFixed(2)}s</option>`)).join("");
$("stride").innerHTML = BOOT.strides.map(s =>
  `<option value="${s}">${s}</option>`).join("");
$("view").innerHTML = BOOT.view_choices.map(v =>
  `<option value="${v}">${v === "wheel" ? "wheel (all round)"
                                        : "broadside (the 3 that show a roll)"}</option>`).join("");
$("r_gain").min = $("n_gain").min = BOOT.gain.min;
$("r_gain").max = $("n_gain").max = BOOT.gain.max;
$("r_gain").step = $("n_gain").step = 0.05;

const clipOf = id => BOOT.clips.find(c => c.id === id) || null;

function rangeFrame() {
  // The frame slider's range is the CLIP's, not a constant: 20 frames of SWIM_FAST and 78 of
  // SWIM_SLOW are the same slider, and a range left over from the last clip would scrub past
  // the end and silently hold the last pose.
  const c = clipOf(posest.clip), lo = c ? c.lo : 1, hi = c ? c.hi : 1;
  posest.frame = Math.min(Math.max(posest.frame, lo), hi);
  for (const el of [$("r_frame"), $("n_frame")]) {
    el.min = lo; el.max = hi; el.value = posest.frame; el.disabled = !c;
  }
  $("framelo").textContent = "f" + lo;
  $("framehi").textContent = "f" + hi;
  $("frameof").textContent = c ? "of " + hi : "(rest)";
  $("play").disabled = !c;
  $("stride").disabled = !c;
  $("r_gain").disabled = $("n_gain").disabled = !c;
  $("clipnote").innerHTML = c
    ? `<span class="hot">${c.action}</span> &middot; bones ${c.bones}<br>${c.note}`
    : "The shipped standing shark: model.action = rest. Pick a clip to flop him.";
  paintPose();
}

function paintPose() {
  $("r_gain").value = $("n_gain").value = posest.gain;
  $("stride").value = posest.stride;
  $("clip").value = posest.clip;
  const c = clipOf(posest.clip);
  const n = c ? loopFrames().length : 0;
  const warn = posest.gain > BOOT.gain.safe ? " <span class=\"bad\">past the measured 2.6x"
                                              + " -- check the neck for tearing</span>" : "";
  $("posenote").innerHTML = c
    ? `loop <span class="num">${n}</span> frames at stride ${posest.stride} = <span
       class="num">${(n * posest.stride / BOOT.fps).toFixed(2)}</span>s per cycle, ${
       (1000 * posest.stride / BOOT.fps).toFixed(0)}ms a frame &middot; gain <span
       class="num">${posest.gain.toFixed(2)}</span>x${warn}${lastBox}`
    : "";
}

for (const k of BOOT.knobs) {
  const r = $("r_" + k.id), n = $("n_" + k.id);
  const push = (v, from) => {
    v = Math.min(Math.max(parseFloat(v), k.lo), k.hi);
    if (!isFinite(v)) return;
    values[k.id] = v;
    if (from !== "r") r.value = v;
    if (from !== "n") n.value = v;
    touched(); quote(); schedule();
  };
  r.addEventListener("input", () => push(r.value, "r"));
  n.addEventListener("change", () => push(n.value, "n"));
}
document.querySelectorAll(".why").forEach(b => b.onclick = () =>
  $("k_" + b.dataset.k).classList.toggle("open"));

function paintKnobs() {
  for (const k of BOOT.knobs) { $("r_" + k.id).value = values[k.id];
                                $("n_" + k.id).value = values[k.id]; }
  $("rotations").value = opts.rotations; $("res").value = opts.res;
  $("shadow").checked = opts.shadow; $("view").value = opts.view;
  $("reparent").checked = !!opts.reparent;
}
$("rotations").onchange = e => { opts.rotations = +e.target.value; touched(); quote(); render(); };
$("res").onchange = e => { opts.res = +e.target.value; touched(); quote(); render(); };
$("shadow").onchange = e => { opts.shadow = e.target.checked; touched(); quote(); render(); };
$("reparent").onchange = e => { opts.reparent = e.target.checked; touched(); quote(); render(); };
$("view").onchange = e => { opts.view = e.target.value; touched(); quote(); render(); };
$("rerender").onclick = () => render();
// The C.5 recipe in one click -- roll 85, SWIM_FAST, gain 1.0, bounce 0.3, HEAD reparented,
// broadside. Only those: scale, girth, pivot and pitch stay where they are, because half the
// time they are mid-tuning and a preset that reverted them is one nobody presses twice.
$("flop").onclick = () => { Object.assign(values, BOOT.flop.values);
                            Object.assign(posest, BOOT.flop.pose);
                            Object.assign(opts, BOOT.flop.opts);
                            touched(); paintKnobs(); rangeFrame(); quote(); render(); };
// Reset means the COMMITTED config, and the committed config is the standing shark -- so it
// drops the pose too. Leaving a clip selected would put you back on sliders that belong to a
// pose you just threw away.
$("reset").onclick = () => { Object.assign(values, BOOT.committed);
                             Object.assign(posest, BOOT.pose);
                             Object.assign(opts, BOOT.opts);
                             touched(); paintKnobs(); rangeFrame();
                             quote(); render(); };

// ---- the pose ------------------------------------------------------------------------
$("clip").onchange = e => {
  posest.clip = e.target.value;
  stopPlay(true); touched(); rangeFrame(); quote(); render();
};
for (const [id, key, lo, hi] of [["frame", "frame", null, null],
                                 ["gain", "gain", BOOT.gain.min, BOOT.gain.max]]) {
  const r = $("r_" + id), n = $("n_" + id);
  const push = (v, from) => {
    v = parseFloat(v);
    if (!isFinite(v)) return;
    const min = lo === null ? +r.min : lo, max = hi === null ? +r.max : hi;
    v = Math.min(Math.max(v, min), max);
    posest[key] = id === "frame" ? Math.round(v) : v;
    if (from !== "r") r.value = posest[key];
    if (from !== "n") n.value = posest[key];
    touched(); paintPose(); quote(); schedule();
  };
  r.addEventListener("input", () => push(r.value, "r"));
  n.addEventListener("change", () => push(n.value, "n"));
}
$("stride").onchange = e => {
  posest.stride = +e.target.value; paintPose(); quote();
  if ($("play").checked) { stopPlay(false); startPlay(); }     // same frames, new tempo
};
// Unticking says so out loud: a fill that is mid-flight only notices on its next answer
// (Blender is not interruptible), and until then the status line would still read "caching
// frame 2/10" at a page that has stopped.
$("play").onchange = e => { if (e.target.checked) startPlay();
                            else { stopPlay(false); setStatus("play stopped"); } };

// ---- the flop loop: render every frame once, then play it out of memory ----------------
//
// The renders are the cost (0.8 s a frame broadside, 2 s on the full wheel) and they are
// paid ONCE per set of knob values. After that the frames are object URLs in this page and
// the loop is a setInterval swapping img.src -- no network, no server, no Blender. That is
// the difference between watching a flop and waiting for one.
const blobs = new Map();
let playing = false, fillGen = 0, loopTimer = null;

function loopFrames() {
  const c = clipOf(posest.clip);
  if (!c) return [];
  const out = [];
  for (let f = c.lo; f <= c.hi; f += posest.stride) out.push(f);
  return out;
}
// The cache key is every input that moves a pixel. Anything else and a roll change would
// replay the old flop.
const poseKey = frame => JSON.stringify([values, opts, posest.clip, posest.gain, frame]);

function dropBlobs() {
  for (const url of blobs.values()) URL.revokeObjectURL(url);
  blobs.clear();
}
function stopLoop() { if (loopTimer) clearInterval(loopTimer); loopTimer = null;
                      $("playing").textContent = ""; }
function stopPlay(uncheck) { playing = false; fillGen++; stopLoop();
                             if (uncheck) $("play").checked = false; }
// Any knob move invalidates every cached frame: they were rendered at the old values. The
// loop stops and the page falls back to stills, which is what makes dragging usable -- a
// refill per slider tick would be ten renders a tick.
function touched() { if (playing) stopPlay(false); dropBlobs(); }

async function startPlay() {
  const frames = loopFrames();
  if (frames.length < 2) { stopPlay(true); setStatus("nothing to play in a rest pose"); return; }
  playing = true;
  const gen = ++fillGen;
  for (let i = 0; i < frames.length; i++) {
    const f = frames[i], key = poseKey(f);
    if (gen !== fillGen) return;                       // superseded by a knob move
    if (blobs.has(key)) continue;
    setStatus(`caching flop frame ${i + 1}/${frames.length} (f${f})`);
    let res;
    const t0 = performance.now();
    try {
      res = await post("/render", {seq: ++seq, session: SESSION,
                                   pose: Object.assign({}, posest, {frame: f})});
    } catch (e) { fail("server unreachable: " + e); stopPlay(true); return; }
    if (gen !== fillGen) return;
    if (res.error || res.superseded || !res.ok) {
      fail(res.error || "render failed while caching f" + f); stopPlay(true); return;
    }
    apply(res, (performance.now() - t0) / 1000);   // show it as it lands: the fill IS the flop
    try {
      const blob = await fetch(res.image + "&t=" + Date.now()).then(r => r.blob());
      // Checked AGAIN, because a knob can move while the bytes are arriving. The key
      // carries the values it was rendered at, so a late arrival could never be SHOWN at
      // the wrong ones -- it would just sit in the map as an object URL nobody reads.
      if (gen !== fillGen) return;
      blobs.set(key, URL.createObjectURL(blob));
    } catch (e) { /* no blob: runLoop just plays the frames that did cache */ }
  }
  if (gen !== fillGen) return;
  runLoop(frames, gen);
}

function runLoop(frames, gen) {
  stopLoop();
  const have = frames.filter(f => blobs.has(poseKey(f)));
  if (have.length < 2) { setStatus(`only ${have.length} frame(s) cached, cannot loop`, true);
                         return; }
  const ms = 1000 * posest.stride / BOOT.fps;
  let i = 0;
  setStatus(`playing ${have.length} frames, ${(have.length * posest.stride / BOOT.fps)
             .toFixed(2)}s cycle, from cache`);
  loopTimer = setInterval(() => {
    if (gen !== fillGen) { stopLoop(); return; }
    const f = have[i++ % have.length];
    const img = $("img");
    img.classList.remove("stale");
    img.src = blobs.get(poseKey(f));
    $("playing").textContent = "f" + f;
  }, ms);
}
$("copy").onclick = () => {
  // Copy SYNCHRONOUSLY from the DOM inside the click, before any await -- Safari drops a
  // clipboard write that happens after one. The POST is only the terminal echo.
  const text = $("toml").textContent;
  navigator.clipboard.writeText(text).then(
    () => flash("copied " + text.split("\n").length + " lines"),
    e => flash("clipboard refused (" + e + ") -- select the block", true));
  post("/toml").catch(() => {});
};

// ---- live numbers (no round trip): same arithmetic artconfig.derived() does -----------
function dims() {
  const s = values.scale, g = values.girth;
  const len = BOOT.model_bu[0] * s, wid = BOOT.model_bu[1] * s * g,
        hei = BOOT.model_bu[2] * s, half = wid / 2;
  const covers = half >= BOOT.mount_half_width;
  $("dims").innerHTML =
    `shark <span class="num">${len.toFixed(2)}</span> x <span class="num">${wid.toFixed(2)}
     </span> x <span class="num">${hei.toFixed(2)}</span> tiles &nbsp;
     half-width <span class="${covers ? "num" : "hot"}">${half.toFixed(3)}</span>
     vs outer mounts at <span class="dim">&plusmn;${BOOT.mount_half_width.toFixed(3)}</span>
     ${covers ? "&check; reaches" : "&mdash; short by " +
       (BOOT.mount_half_width - half).toFixed(3) + " tiles"}`;
}

// ---- transport ------------------------------------------------------------------------
function post(path, extra) {
  return fetch(path, {method: "POST", headers: {"Content-Type": "application/json"},
                      body: JSON.stringify(Object.assign({values, opts, pose: posest},
                                                        extra || {}))})
         .then(r => r.json());
}
let quoteBusy = false, quoteAgain = false;
function quote() {
  dims();
  if (quoteBusy) { quoteAgain = true; return; }
  quoteBusy = true;
  post("/quote").then(q => {
    if (q.error) return;
    $("htuner").textContent = q.tuner_hash;
    $("hpaste").textContent = q.paste_hash;
    $("toml").textContent = q.toml;
    showWarn(q.warnings || []);
  }).catch(() => {}).finally(() => {
    quoteBusy = false;
    if (quoteAgain) { quoteAgain = false; quote(); }
  });
}
let timer = null;
function schedule(ms) {              // debounce: a drag must not queue twenty renders
  clearTimeout(timer);
  timer = setTimeout(render, ms === undefined ? 220 : ms);
}
function render() {
  clearTimeout(timer);
  if (inflight) { pending = true; return; }   // single flight; the newest values win
  inflight = true; pending = false;
  const mine = ++seq;
  tStart = performance.now();
  $("img").classList.add("stale");
  setStatus("rendering seq " + mine + (opts.shadow ? " (cycles shadow, be patient)" : ""));
  post("/render", {seq: mine, session: SESSION}).then(res => {
    const rtt = (performance.now() - tStart) / 1000;
    if (res.superseded) { setStatus("seq " + res.seq + " superseded"); return; }
    if (res.seq !== undefined && res.seq < applied) return;   // late answer, older values
    applied = res.seq === undefined ? applied : res.seq;
    apply(res, rtt);
  }).catch(e => {
    fail("server unreachable: " + e);
  }).finally(() => {
    inflight = false;
    if (pending) { pending = false; render(); }
    // PLAY stays ticked across a knob drag: the still lands first (fast feedback), then the
    // loop refills behind it. Ticking it off is the only thing that stops that.
    else if ($("play").checked && !playing) startPlay();
  });
}
function apply(res, rtt) {
  if (res.tuner_hash) { $("htuner").textContent = res.tuner_hash;
                        $("hpaste").textContent = res.paste_hash;
                        $("toml").textContent = res.toml; }
  $("log").textContent = res.log || "-";
  showWarn(res.warnings || []);
  if (!res.ok) { fail(res.error || "render failed"); return; }
  $("err").style.display = "none";
  const img = $("img");
  img.onload = () => img.classList.remove("stale");
  img.src = res.image + "&t=" + Date.now();
  $("cover").innerHTML = "<span class=\"hot\">mounts</span> " + (res.coverage_line || "");
  $("covtable").innerHTML = "<tr>" + (res.coverage || []).map(c =>
      `<td>${c[0]}</td>`).join("") + "</tr><tr>" + (res.coverage || []).map(c =>
      `<td class="${c[1] === 0 ? "bad" : "num"}">${c[1]}/8</td>`).join("") + "</tr>";
  $("shotinfo").textContent =
    `seq ${res.seq} | ${res.frames.length} ${res.view ? res.view.name : "wheel"} dirs `
    + `${(res.frames || []).join(",")} @ ${res.derived.body_resolution_px}px `
    + `(${res.derived.body_px_per_tile.toFixed(1)} px/tile) | server ${res.seconds}s`
    + `, round trip ${rtt.toFixed(2)}s | ${res.rendered ? res.rendered + " frame(s) rendered"
       : "all cached"} | ${res.selfcheck.startsWith("mount self-check PASS")
       ? "selfcheck PASS" : res.selfcheck}`;
  // The box of what was RENDERED, in tiles, measured off the evaluated mesh. derived()
  // reports the REST box from a constant -- correct for the standing shark, and wrong the
  // moment he thrashes -- so say both and let the frame-box question be asked of the right
  // one. This is the number C.17's pivot session and the bounce's canvas cost both need.
  const bt = res.box_tiles;
  if (bt && bt.length === 3) {
    const size = bt.map(a => a[1] - a[0]);
    lastBox = `<br>rendered box <span class="num">${size.map(v => v.toFixed(2)).join(
      " &times; ")}</span> tiles, z ${bt[2][0].toFixed(2)}..${bt[2][1].toFixed(2)}${
      res.derived.bounce_lift_tiles > 0
        ? ` &middot; lifted <span class="hot">${res.derived.bounce_lift_tiles.toFixed(3)
          }</span> tiles this frame` : ""}`;
  } else if (res.pose && res.pose.posed) {
    // No box came back, which means no Blender ran: every frame was cached. Keeping the last
    // render's box here would put roll 90's numbers under a roll 85 picture.
    lastBox = "<br><span class=\"dim\">box not re-measured &mdash; every frame came out of "
              + "the cache, so the render printed no report of its own</span>";
  } else { lastBox = ""; }
  paintPose();
  setStatus(`ok in ${rtt.toFixed(2)}s`);
}
function showWarn(list) {
  const box = $("warn");
  box.style.display = list.length ? "block" : "none";
  box.textContent = list.map(w => "WARN " + w).join("\n\n");
}
function fail(msg) {
  const box = $("err");
  box.style.display = "block";
  box.textContent = "RENDER FAILED, image above is the last good one\n\n" + msg;
  $("img").classList.remove("stale");
  setStatus("failed", true);
}
function setStatus(t, bad) { $("status").className = "status" + (bad ? " bad" : " dim");
                             $("status").textContent = t; }
function flash(t, bad) { setStatus(t, bad); }

paintKnobs(); rangeFrame(); quote(); render();
</script>
"""


def page(tuner: Tuner) -> str:
    boot = {
        "knobs": [{"id": k.id, "key": k.key, "index": k.index, "lo": k.lo, "hi": k.hi,
                   "step": k.step, "label": k.label, "unit": k.unit,
                   "lo_label": k.lo_label, "hi_label": k.hi_label, "hint": k.hint}
                  for k in KNOBS],
        "start": values_of(tuner.start),
        "committed": values_of(tuner.committed),
        # `reparent` is seeded off the config rather than off DEFAULT_OPTS, so
        # `--set model.reparent_head=true` boots with the box ticked instead of being
        # silently turned back off by the page's own default.
        "opts": dict(DEFAULT_OPTS, reparent=tuner.committed["model.reparent_head"]),
        "rotation_choices": list(ROTATION_CHOICES),
        "res_choices": list(RES_CHOICES),
        "view_choices": list(VIEW_CHOICES),
        "model_bu": MODEL_BU,
        "mount_half_width": MOUNT_HALF_WIDTH,
        "mount_span_y": list(MOUNT_SPAN_Y),
        # The pose half. The clip table is pose.CLIPS itself, not a copy of it, so the
        # select, the frame slider's range and every duration on the page all come off the
        # same five records every posed render re-checks against the model.
        "pose": DEFAULT_POSE,
        "flop": FLOP_PRESET,
        "rest": pose.REST,
        "fps": pose.FPS,
        "clips": [{"id": c.id, "action": c.action, "lo": c.lo, "hi": c.hi, "span": c.span,
                   "seconds": round(c.seconds, 3), "bones": c.bones, "note": c.note}
                  for c in pose.CLIPS],
        "gain": {"min": pose.GAIN_MIN, "max": pose.GAIN_MAX, "safe": pose.GAIN_SAFE},
        "strides": list(range(STRIDE_MIN, STRIDE_MAX + 1)),
    }
    return PAGE.replace("__BOOT__", json.dumps(boot))


# --------------------------------------------------------------------------------- cli


def build_parser():
    p = argparse.ArgumentParser(
        prog="tune.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=None, help="config TOML (default render/jamaltron.toml)")
    p.add_argument("--set", action="append", dest="sets", metavar="key=value",
                   help="seed a knob, TOML syntax -- use it to start where you left off")
    p.add_argument("--blend", default=None, help="the .blend (or $%s)" % ac.BLEND_ENV)
    p.add_argument("--port", type=int, default=8765, help="first port to try (default 8765)")
    p.add_argument("--jobs", type=int, default=4,
                   help="parallel Blenders. MEASURED: 4 is the floor of the curve on this "
                        "machine, 8 is 14x SLOWER (Metal context thrash). Default 4")
    p.add_argument("--no-open", action="store_true", help="do not open a browser")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    # The terminal is half the tool -- the harness's own report, the timings and the TOML
    # all come out here. Python line-buffers a TTY and BLOCK-buffers a pipe, so without
    # this a `tune.py | tee log` shows nothing for minutes and looks hung.
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(line_buffering=True)
    try:
        committed, start, note, pinned = seed(ac.load(args.config), ac.parse_set(args.sets))
    except ac.ConfigError as exc:
        sys.stderr.write("tune.py: %s\n" % exc)
        return 2
    if note:
        print(note)
    for kid, (asked, got) in sorted(pinned.items()):
        print("--set %s=%s is outside the slider range, clamped to %s" % (kid, asked, got))
    if args.blend:
        committed["model.blend"] = start["model.blend"] = args.blend

    blend = art.blend_path(committed)
    if not blend.exists():
        print("WARN model not found: %s\n     the .blend is gitignored and machine-local; "
              "point at it with --blend or $%s.\n     The server starts anyway and the page "
              "will show the error." % (blend, ac.BLEND_ENV))

    tuner = Tuner(committed, start, max(1, args.jobs), note)
    httpd = None
    for port in range(args.port, args.port + 12):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, tuner=tuner))
            break
        except OSError:
            continue
    if httpd is None:
        sys.stderr.write("tune.py: no free port in %d..%d\n" % (args.port, args.port + 11))
        return 2
    httpd.daemon_threads = True
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    print("jamaltron tuner on %s   jobs=%d  shadow OFF by default (Cycles is the 12-15s)\n"
          "  frames and sheets land in %s (gitignored). Every distinct value is its own\n"
          "  cache dir: ~2.8 MB per change, ~13 MB with the shadow on. A long session is\n"
          "  hundreds of MB you can delete whenever. Ctrl-C to stop.\n"
          "  A POSE is knobs (model.action / pose_gain / frame, plus [bounce]), so a flop\n"
          "  frame caches and stamps exactly like a standing one -- nothing is written\n"
          "  outside %s and the licensed model is never copied."
          % (url, tuner.jobs, art.out_root(committed), art.out_root(committed)))
    if not args.no_open:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped after %d renders." % tuner.renders)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
