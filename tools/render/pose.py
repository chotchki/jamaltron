#!/usr/bin/env python3
"""The five shipped clips, what each one is, and the arithmetic of a loop over one.

    from render import pose
    pose.clip_of("SWIM_FAST").span          # 20 frames
    pose.clamp_frame("SWIM_FAST", 999)      # 20 -- a slider cannot scrub past the end
    pose.loop_frames("SWIM_FAST", 2)        # [1, 3, 5, ... 19], the PLAY loop

IT USED TO BAKE POSES. The harness had no knob for WHICH ACTION, so this module launched
Blender, evaluated one frame of one clip, amplified it and saved a headless copy of the
model posed at that frame. `model.action` and `model.pose_gain` were held back on purpose:
`pose_gain` decided whether the bought animation ships at all, and that was chotchki's call
off pictures, not the tuner's to pre-empt.

THE CALL IS IN (roll 80-90, gain 1.0), the knobs landed and the bake is gone. Left: the
TABLE (which clip, which bones, how long) plus the clamps and loop arithmetic the tuner,
the schema and the renderer read. One path to a pose: artconfig.SCHEMA carries the knobs,
render_jamal.apply_action() applies them inside the render already launching, and art.py's
cache keys and provenance stamps cover them as ordinary knobs.

STDLIB ONLY, NO SIBLING IMPORTS: `artconfig` imports THIS module to resolve `model.action`
against the real clip ids, so the reverse import would be a cycle. Everything here is
arithmetic over the table; `bpy` lives in render_jamal, across the Blender boundary, where
the bones actually move.
"""

import hashlib
import json
import math
from dataclasses import dataclass

#: The scene's own frame rate, read off the .blend by C.2. Every duration is this and a
#: frame count, so a clip's seconds cannot drift from its frames.
FPS = 24

#: What "no pose" is called on the wire, in the UI and in `model.action`. Renders the REST
#: shark exactly as the shipped config does (no action, no gain, the standing sprite's own
#: renderer path), so flop tuning cannot break the sprites that already ship.
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
    #: A TRAVELLING WAVE down one bone chain, the lag `model.phase_lock` cancels. The bites
    #: are not: they are a one-shot on HEAD/JAW/fins.
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
#: Only the cycle length differs, so picking one is picking a TEMPO. The bites animate bones
#: disjoint from the swims, so they compose: a swim in the spine and a bite in the fins is
#: one pose.
#:
#: `verify_clips` checks the ranges against the model on every posed render; a hardcoded
#: table about a file this tool opens anyway WILL rot silently.
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

#: Every legal `model.action`, rest first. artconfig.ENUMS reads THIS, so a clip added here
#: is selectable from the CLI and the tuner with no second list to update.
ACTION_CHOICES = (REST,) + tuple(c.id for c in CLIPS)

#: How hard a pose may be pushed. 1.0 is the clip as bought and what SHIPS: at roll 80-90
#: the bounce carries the thrash, so the gain a roll-30 flop needed is not needed. The knob
#: exists so gain is ruled OUT deliberately, not assumed.
#:
#: MEASURED: the rig survives 2.6x with no mesh tearing and no candy-wrapper collapse at the
#: neck, more than expected of a rig whose HEAD is an unparented root bone. The ceiling is
#: 3.0, not 2.6, so the slider can find where it DOES break (a number C.5 wants); the
#: warnings say which side of 2.6 you are on.
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

    Strided from `lo`, so frame 1 is in every loop whatever the stride -- a loop that skips
    its own first frame stutters at the seam. The last frame is NOT forced in: at stride 3
    over a 20-frame cycle, 19 is the last sample and 20 would land one frame from the start
    and read as a hitch.
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
# THE SWIM IS A TRAVELLING WAVE AND A FLOP IS A STANDING ONE (chotchki, C.5). Same bones and
# keyframes, different phase: in the swim each joint bends a fixed lag behind the one in
# front, so the bend runs nose to tail and reads as propulsion; in a flop every joint bends
# the same way at once, the body curls, then snaps the other way.
#
# MEASURED on the bought model, SWIM_FAST, fundamental of each joint's bend angle:
#
#     joint     SPINE_01  _02   _03   _04   _05   _06   _07   TAIL
#     lag (fr)    0.00   1.50  2.99  4.49  5.49  6.99  8.50  10.00     of a 20-frame cycle
#     amp (deg)   2.99   1.52  3.75  4.56  8.09 10.54  8.26  10.82
#
# Neighbour steps are 1.0-1.5 frames (0.05-0.075 of the cycle; SPINE_04 -> _05 is the 1.0),
# and MEDIUM and SLOW carry the same lags as the same FRACTIONS of their cycle, so the knob is
# one number meaning the same on all three. Nose-to-tail is exactly half a period, which is
# why the 09-20 spike's front/back split at k = half a period measures WORSE than cancelling
# each joint's own lag: the wave is rear-loaded 3:1, so any two-group split has a seam at the
# split bone and needs k re-tuned against the amplitude profile. Per joint it is one knob
# with no seam and no k.
#
# THE TAIL KEEPS ITS TIMING and every other joint is pulled into step with it: the tail is
# the biggest single swing and what the eye tracks, so the loop's loudest motion stays on
# its frames. PEAK WHOLE-BODY CURL STILL MOVES, measured on FAST: max at f18 at lock 0, f19
# at 0.5, f1 at 1 (a 2-3 frame shift). [bounce] launches on peak curl, so re-find
# bounce.phase after moving the lock; do not inherit it.

#: The slider's rail. 0 is the clip as bought; 1 is every joint in step with the tail. The
#: schema clamps nothing; warnings() says what lies past either end.
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

    `signals` is one signed bend-angle series per joint, chain order (root first), each
    `span` samples of one cycle. UNWRAPPED is the point: phase is only known modulo a cycle,
    and nose-to-tail on these clips is EXACTLY half of one, so wrapping each joint alone puts
    the tail at +10 or -10 on a coin flip of float noise. Neighbours are 1.0-1.5 frames apart
    on FAST (3 on MEDIUM, ~6 of 78 on SLOW), far inside half a cycle, so each step is taken as
    the representative nearest zero and summed down the chain, where the physics accumulates
    the lag. Not hypothetical on the real rig: SPINE_01's phase sits ON atan2's cut (-3.063,
    then +2.749 for SPINE_02), and the raw step would be -18.5 frames.

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
    """Per-joint time offset in frames that pulls each joint `lock` of the way into step with
    the LAST joint of the chain (the tail). Sample joint i at frame + offset[i].

    The sign: joint i reads the wave (lag_tail - lag_i) frames AHEAD of the tail, so sampling
    it that much EARLIER lands it on the tail's phase. The tail's offset is always 0 (the
    block above says why the tail holds still).
    """
    if not lags:
        return []
    ref = lags[-1]
    return [-float(lock) * (ref - lag) + 0.0 for lag in lags]        # + 0.0: no -0.0 in a log


# ------------------------------------------------------------------- amplitude evening
#
# THE LOCK TIMES THE WAVE AND DOES NOT SHAPE IT. At lock 1 every joint bends with the tail,
# but the swing is REAR-LOADED 3:1 (table above: front four 12.8 deg, rear four 37.7), so the
# coherent curl still hinges at the pinned nose and reads as a big tail flick, not a U
# (C.5.2, measured). `model.amplitude_even` blends each joint's swing toward the chain's MEAN:
# at 1 every joint swings the same, the curl spreads evenly down the body and the U has its
# bottom in the middle. The SUM of the swings is unchanged at any setting (it moves the curl,
# adds none), so pose_gain stays the one knob for how hard he thrashes.
#
# ONE NUMBER, NOT A PER-JOINT GAIN LIST. Amplitudes are measured off the clip every render,
# like the lags, so one knob means the same on all three swims on one 0..1 rail; eight gains
# would be eight sliders pinned to this rig's current profile.


def wave_amplitudes(signals) -> list:
    """Each joint's swing: the amplitude of its bend signal's fundamental, same units in."""
    return [fundamental(sig)[0] for sig in signals]


def even_gains(amps, even: float) -> list:
    """Per-joint gain that takes each amplitude `even` of the way to the chain's mean.

    new_amp = (1 - even) * amp + even * mean, so the gain is that over amp. A joint with no
    measurable swing keeps gain 1: there is nothing to scale, and mean / 0 is not a gain.
    """
    amps = [float(a) for a in amps]
    if not amps:
        return []
    mean = sum(amps) / len(amps)
    e = float(even)
    return [1.0 if a < 1e-9 else (1.0 - e) + e * mean / a for a in amps]


# ------------------------------------------------------------------------- recentring
#
# SPINE_01 IS A ROOT AT THE NOSE, so every degree of curl shows as the tail swinging off a
# pinned head (C.5.2: lock 1's coherent 50.8 deg curl read as a TAIL FLICK). `model.recentre`
# turns the whole posed body back against the curl by `amount` of the nose-to-tail chord's
# turn off rest: at 1 the chord keeps its rest direction, so head and tail rise TOGETHER (the
# U); at 0.5 half the tilt stays. The arithmetic lives here, bpy-free and testable;
# render_jamal.recentre_model applies it to the armature object.


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def counter_turn(rest, posed, amount: float) -> tuple:
    """(unit axis, radians) of the rotation that takes the POSED chord `amount` of the way back
    to the REST chord's direction; (None, 0.0) when they already agree.

    The minimal rotation, about rest x posed -- for a planar bend that is the bend axis, so
    the counter-turn stays in the bend plane. The angle comes back NEGATIVE about that axis
    (it undoes the turn), so apply it as-is.
    """
    c = _cross(rest, posed)
    n = math.sqrt(sum(v * v for v in c))
    dot = sum(a * b for a, b in zip(rest, posed))
    if n < 1e-12:
        return None, 0.0
    return tuple(v / n for v in c), -float(amount) * math.atan2(n, dot)


# ----------------------------------------------------------------- the fin on the floor
#
# C.5.6's fin_fold turns the lower pectoral a FIXED angle from wherever the pose left it,
# which lands it level only while the chest it hangs off (SPINE_02) sits near rest -- true of
# the lock-0.5 heave, where the fin dives 46-52 deg before the fold. C.5.8's U breaks that
# twice: amplitude_even at gain 2 swings the chest itself (MEASURED 25-62 deg of dive before
# any recentre), and the recentre turns the whole body up to ~60 deg more. The fin's heading
# swings with it, east-south-east on C+'s frames to due SOUTH at the U's bottom, and a fin
# pointing at the camera is the long white spike under his chest. `model.fin_floor` pins the
# fin's ORIENTATION to what it would be on a rest spine with no body turn (its own clip
# rotation kept, so a bite still flaps it), so the fixed fold works from the orientation it
# was tuned on. The root still rides the chest.


def _matmul3(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _transpose3(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def floor_hold(bone_rest, basis, body_turn) -> list:
    """The ARMATURE-space rotation (3x3, row lists) pinning a bone's orientation to the floor:
    what it would be with every parent at rest and `body_turn` (model.recentre's rigid turn of
    the whole armature, in its own space) taken back out.

    `bone_rest` is the bone's rest matrix_local rotation, `basis` its own pose rotation (the
    clip's, gain included). A posed bone's rotation is parents' pose x rest x basis; dropping
    the parents leaves rest x basis. The world sees body_turn x that, so pre-multiplying by
    its inverse (a rotation's transpose) leaves rest x basis exactly -- the rest-spine
    orientation, unturned. With no parent motion and no turn this IS the posed rotation: the
    hold changes nothing it does not have to."""
    return _matmul3(_transpose3(body_turn), _matmul3(bone_rest, basis))


def wrap_time(t: float, lo: int, span: int) -> float:
    """A time inside one cycle, [lo, lo + span). Fractional on purpose: the lags are."""
    return lo + (t - lo) % span


def verify_clips(actions: dict) -> list:
    """CLIPS against what Blender just reported. A hardcoded table about a file this tool
    opens anyway rots silently, so check it at the one moment it is free.

    `actions` maps action name -> {"raw": [lo, hi], "dropped": [lo, hi]}; "dropped" is the
    range after the stale final keyframe goes, the range the renderer plays and so the only
    one a slider may offer.
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
    """A digest of the table itself (ids, actions and ranges, not the prose), so a report can
    say WHICH table it was checked against.

    Deliberately in no config hash: the table is knowledge about the model, not a knob, and
    rewording a note must not throw away 64 cached frames.
    """
    blob = json.dumps([[c.id, c.action, c.lo, c.hi] for c in CLIPS], separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:length]
