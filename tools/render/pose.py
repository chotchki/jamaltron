#!/usr/bin/env python3
"""The five shipped clips, what each one is, and the arithmetic of a loop over one.

    from render import pose
    pose.clip_of("SWIM_FAST").span          # 20 frames
    pose.clamp_frame("SWIM_FAST", 999)      # 20 -- a slider cannot scrub past the end
    pose.loop_frames("SWIM_FAST", 2)        # [1, 3, 5, ... 19], the PLAY loop

WHAT THIS FILE IS NOW, AND WHAT IT USED TO BE. It used to bake poses: the harness had no
knob for WHICH ACTION, so this module launched Blender, evaluated one frame of one clip,
amplified it, and saved a headless copy of the model whose SAVED POSE was that frame. The
two knobs that should have done the job -- `model.action` and `model.pose_gain` -- were held
back on purpose, because `pose_gain` decides whether the bought animation ships at all and
that was chotchki's call to make off pictures, not the tuner's to pre-empt.

THE CALL IS IN (roll 80-90, gain 1.0) AND THE KNOBS LANDED, so the bake is gone. What is
left is the TABLE -- which clip is which, which bones it drives, how long it runs -- plus the
clamps and the loop arithmetic that the tuner, the schema and the renderer all read. One
path to a pose now: artconfig.SCHEMA carries the knobs, render_jamal.apply_action() applies
them inside the render that was launching anyway, and art.py's cache keys and provenance
stamps pick them up for free because they are ordinary knobs.

STDLIB ONLY, AND IT IMPORTS NO SIBLING. Not an accident and not laziness: `artconfig`
imports THIS module to resolve `model.action` against the real clip ids, so a dependency
in the other direction would be an import cycle. Everything here is arithmetic over a
table; `bpy` lives in render_jamal, on the far side of the Blender boundary, where the
bones actually move.
"""

import hashlib
import json
import math
from dataclasses import dataclass

#: The scene's own frame rate, read off the .blend by C.2. Every duration on the page is
#: this number and a frame count, so a clip's seconds cannot drift from its frames.
FPS = 24

#: What "no pose" is called on the wire, in the UI and in `model.action`. Selecting it
#: renders the REST shark exactly as the shipped config does -- no action assigned, no
#: gain, the standing sprite's own path through the renderer. The flop tuning must not be
#: able to break the sprites that already ship.
REST = "rest"


@dataclass(frozen=True)
class Clip:
    """One shipped action. `lo`/`hi` are INCLUSIVE and are the range AFTER
    render_jamal.drop_stale_final_keyframes(), because that is what the renderer plays."""

    id: str
    action: str
    lo: int
    hi: int
    bones: str
    note: str
    #: A TRAVELLING WAVE down one bone chain, which is what `model.phase_lock` needs to have
    #: a lag to cancel. The bites are not: they are a one-shot on HEAD/JAW/fins.
    wave: bool = False

    @property
    def span(self) -> int:
        return self.hi - self.lo + 1

    @property
    def seconds(self) -> float:
        return self.span / FPS


#: The five clips the model ships. C.2 found four and missed SWIM_MEDIUM.
#:
#: THE THREE SWIMS ARE ONE ANIMATION AT THREE SPEEDS -- identical lateral tail sine, 1.198 /
#: 1.199 / 1.201 BU of tail-tip sweep, the same 44 px on screen at the shipped scale 0.81.
#: Only the cycle length differs, so picking between them is picking a TEMPO and nothing
#: else. The two bites animate a disjoint set of bones from the swims, which is why they
#: compose: a swim in the spine and a bite in the fins is one pose, not a fight.
#:
#: The ranges are verified against the model on every posed render (see `verify_clips`),
#: because a hardcoded table about a file this tool opens anyway is a table that WILL rot
#: silently.
CLIPS = (
    Clip("SWIM_FAST", "ArmatureAction.002", 1, 20, "SPINE_01..07 + TAIL",
         "20-frame loop, 0.83 s. THE flop candidate. At roll 80-90 its bend plane stands "
         "up into the same plane as the bounce, so curl-up and lift-off are ONE motion.",
         wave=True),
    Clip("SWIM_MEDIUM", "ArmatureAction.004", 1, 40, "SPINE_01..07 + TAIL",
         "40-frame loop, 1.67 s. The same sweep as FAST at half the speed -- reads as "
         "labouring rather than panicking.", wave=True),
    Clip("SWIM_SLOW", "SWIM_SLOW.001", 1, 78, "SPINE_01..07 + TAIL",
         "78-frame loop, 3.3 s. The same sweep again at a quarter the speed. Too slow to "
         "read as distress on its own; useful as the tail end of a flop that is giving up.",
         wave=True),
    Clip("BITE_02", "ArmatureAction.005", 1, 50, "HEAD, JAW, FIN_LEFT, FIN_RIGHT",
         "50 frames, no loop, and MEASURED USELESS: 24 cells that are all the same picture, "
         "a 2 px jaw. Kept in the table so the table describes the model, not our taste."),
    Clip("BITE_01", "ArmatureAction.007", 1, 79, "HEAD, JAW, FIN_LEFT, FIN_RIGHT",
         "79 frames but ALL the motion is in 1-29, then a 50-frame hold. The near pectoral "
         "fin sweeps down and forward -- the only bite with anything in it."),
)

CLIPS_BY_ID = {c.id: c for c in CLIPS}

#: Every legal value of `model.action`, rest first. artconfig.ENUMS reads THIS, so a clip
#: added here is selectable from the CLI and the tuner with no second list to update.
ACTION_CHOICES = (REST,) + tuple(c.id for c in CLIPS)

#: How hard a pose may be pushed. 1.0 is the clip as bought, and 1.0 is what SHIPS -- at
#: roll 80-90 the bounce carries the thrash, so the gain that a roll-30 flop needed is not
#: needed here. The knob exists so gain can be ruled OUT deliberately rather than assumed.
#:
#: MEASURED: the rig survives 2.6x with no mesh tearing and no candy-wrapper collapse at the
#: neck, which is more than expected from a shark rig whose HEAD is an unparented root bone.
#: The ceiling is 3.0 rather than 2.6 so the slider can find where it DOES break -- that is
#: a number C.5 wants to know -- and the warnings say which side of 2.6 you are on.
GAIN_MIN, GAIN_MAX, GAIN_SAFE = 1.0, 3.0, 2.6


def clip_of(clip_id):
    """The Clip for an id, or None for REST / anything unknown. Never raises: the id
    arrives from a browser select and a stale tab is not a crash."""
    return CLIPS_BY_ID.get(clip_id)


def clamp_frame(clip_id: str, frame) -> int:
    """A frame inside the clip's own range. REST has exactly one frame and it is 1."""
    c = clip_of(clip_id)
    if c is None:
        return 1
    try:
        f = int(round(float(frame)))
    except (TypeError, ValueError):
        return c.lo
    return min(max(f, c.lo), c.hi)


def clamp_gain(gain) -> float:
    try:
        g = float(gain)
    except (TypeError, ValueError):
        return 1.0
    if g != g or g in (float("inf"), float("-inf")):      # NaN / inf: not a gain
        return 1.0
    return min(max(g, GAIN_MIN), GAIN_MAX)


def loop_frames(clip_id: str, stride: int = 1) -> list:
    """The frames a PLAY loop steps through, in order.

    Strided from `lo`, which keeps frame 1 in every loop whatever the stride -- a loop that
    skips its own first frame is a loop that stutters at the seam. The last frame is NOT
    forced in: at stride 3 over a 20-frame cycle, 19 is the last sample and 20 would land
    one frame from the start and read as a hitch.
    """
    c = clip_of(clip_id)
    if c is None:
        return [1]
    stride = max(1, min(int(stride), max(1, c.span)))
    return list(range(c.lo, c.hi + 1, stride))


def loop_ms(stride: int = 1) -> float:
    """Milliseconds a strided frame is held so the loop plays at the clip's own tempo."""
    return 1000.0 * max(1, int(stride)) / FPS


# ------------------------------------------------------------------------ phase lock
#
# THE SWIM IS A TRAVELLING WAVE AND A FLOP IS A STANDING ONE (chotchki, C.5). Same bones,
# same keyframes, different phase relationship: in the swim each joint bends a fixed lag
# behind the one in front, so the bend runs nose to tail and reads as propulsion; in a flop
# every joint bends the same way at once, the body curls, then snaps the other way.
#
# MEASURED on the bought model, SWIM_FAST, fundamental of each joint's bend angle:
#
#     joint     SPINE_01  _02   _03   _04   _05   _06   _07   TAIL
#     lag (fr)    0.00   1.50  2.99  4.49  5.49  6.99  8.50  10.00     of a 20-frame cycle
#     amp (deg)   2.99   1.52  3.75  4.56  8.09 10.54  8.26  10.82
#
# Neighbour steps are 1.0-1.5 frames (0.05-0.075 of the cycle; SPINE_04 -> _05 is the 1.0),
# and MEDIUM and SLOW carry the same lags as the same FRACTIONS of their cycle, so the knob is
# one number that means the same thing on all three. Nose-to-tail is exactly
# half a period, which is why the 09-20 spike found a front/back split at k = half a period
# measures WORSE than cancelling each joint's own lag: the wave is rear-loaded 3:1, so any
# two-group split has a seam at the split bone and needs its k re-tuned against the
# amplitude profile. Per joint it is one knob with no seam and no k.
#
# THE TAIL KEEPS ITS TIMING. Every other joint is pulled into step with it, not the other way
# round: the tail is the biggest single swing and the thing the eye tracks, so the loop's
# loudest motion stays on the frames it had. PEAK WHOLE-BODY CURL STILL MOVES, measured on
# FAST: max at f18 at lock 0, f19 at 0.5, f1 at 1 (a 2-3 frame shift). [bounce] launches on
# peak curl, so bounce.phase is re-found after the lock moves, not inherited.

#: The slider's rail. 0 is the clip as bought; 1 is every joint in step with the tail. The
#: schema does not clamp (it clamps nothing) and warnings() says what lies past either end.
LOCK_MIN, LOCK_MAX = 0.0, 1.0


def fundamental(signal) -> tuple:
    """(amplitude, phase) of the first harmonic of ONE cycle sampled evenly.

    Phase convention: a signal A*cos(2*pi*k/n + phi) comes back as (A, phi), so a joint that
    bends L frames later than another comes back with its phase 2*pi*L/n SMALLER.
    """
    n = len(signal)
    if n < 2:
        return 0.0, 0.0
    w = 2.0 * math.pi / n
    re = sum(s * math.cos(w * k) for k, s in enumerate(signal))
    im = -sum(s * math.sin(w * k) for k, s in enumerate(signal))
    return 2.0 * math.hypot(re, im) / n, math.atan2(im, re)


def wave_lags(signals, span: int) -> list:
    """Each joint's lag in frames behind the FIRST, unwrapped down the chain.

    `signals` is one signed bend-angle series per joint, in chain order (root first), each
    `span` samples of one cycle. UNWRAPPED is the point: phase is only known modulo a cycle,
    and nose-to-tail on these clips is EXACTLY half of one, so wrapping each joint on its own
    puts the tail at +10 or -10 on a coin flip of float noise. Neighbours are 1.0-1.5 frames
    apart on FAST (3 on MEDIUM, ~6 of 78 on SLOW), far inside half a cycle, so each step is
    taken as the representative nearest zero and summed down the chain, which is where the
    physics says the lag accumulates. On the real rig this is not hypothetical: SPINE_01's
    phase sits ON atan2's cut (-3.063, then +2.749 for SPINE_02), and the raw step would be
    -18.5 frames.

    A joint with no measurable swing has no phase worth reading; it inherits its
    neighbour's lag rather than injecting noise into everything behind it.
    """
    lags = []
    prev_phase = None
    for sig in signals:
        amp, ph = fundamental(sig)
        if not lags:
            lags.append(0.0)
            prev_phase = ph
            continue
        if amp < 1e-6:
            lags.append(lags[-1])
            continue
        step = (prev_phase - ph) / (2.0 * math.pi) * span
        step = (step + span / 2.0) % span - span / 2.0
        lags.append(lags[-1] + step)
        prev_phase = ph
    return lags


def lock_offsets(lags, lock: float) -> list:
    """Per-joint time offset, in frames, that pulls each joint `lock` of the way into step
    with the LAST joint of the chain (the tail). Sample joint i at frame + offset[i].

    Why that is the sign: joint i reads the wave (lag_tail - lag_i) frames AHEAD of the tail,
    so sampling it that many frames EARLIER lands it on the tail's phase. The tail's own
    offset is always 0 -- see the block above for why it is the tail that holds still.
    """
    if not lags:
        return []
    ref = lags[-1]
    return [-float(lock) * (ref - lag) + 0.0 for lag in lags]        # + 0.0: no -0.0 in a log


def wrap_time(t: float, lo: int, span: int) -> float:
    """A time inside one cycle, [lo, lo + span). Fractional on purpose: the lags are."""
    return lo + (t - lo) % span


def verify_clips(actions: dict) -> list:
    """CLIPS against what Blender just reported. A hardcoded table about a file this tool
    opens anyway is a table that rots silently, so check it at the one moment it is free.

    `actions` maps action name -> {"raw": [lo, hi], "dropped": [lo, hi]}, the second being
    the range after the stale final keyframe goes -- which is the range the renderer plays
    and therefore the only one a slider may offer.
    """
    out = []
    for c in CLIPS:
        got = actions.get(c.action)
        if got is None:
            out.append("%s: no action named %r in the model (have %s)"
                       % (c.id, c.action, ", ".join(sorted(actions)) or "none"))
            continue
        lo, hi = (int(round(v)) for v in got.get("dropped", got.get("raw", [0, 0])))
        if (lo, hi) != (c.lo, c.hi):
            out.append("%s (%s): table says frames %d-%d, model says %d-%d after the "
                       "stale-keyframe drop" % (c.id, c.action, c.lo, c.hi, lo, hi))
    return out


def table_digest(length: int = 8) -> str:
    """A digest of the table itself -- ids, actions and ranges, not the prose.

    So a report can say WHICH table it was checked against. Deliberately not part of any
    config hash: the table is knowledge about the model, not a knob, and re-wording a note
    must not throw away 64 cached frames.
    """
    blob = json.dumps([[c.id, c.action, c.lo, c.hi] for c in CLIPS], separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:length]
