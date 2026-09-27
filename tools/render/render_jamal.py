"""Blender side of the C.10 harness: render N rotations of the shark, body or shadow.

Never invoked by hand. `render/art.py` resolves the config, works out which frames the
cache is missing and shells out to one or more copies of this:

    Blender -b MODEL.blend --python tools/render/render_jamal.py -- \
        --config /tmp/resolved.json --pass body --frames 0,8,16 --out render-out/body/<hash>

It reads a fully RESOLVED config as JSON and never parses the TOML. One resolution path,
on the uv side, so the Blender side cannot disagree about what a knob means and the
stamped hash is the hash of what actually rendered.

WHAT IT FIXES BEFORE IT RENDERS (the first three are C.2 findings, all silent):
  * FIVE UNMUTED NLA TRACKS. SWIM_FAST / SWIM_SLOW / SWIM_MEDIUM / BITE_02 / BITE_01 all
    ship live, and BITE_01 blends COMBINE on top, so the shark renders mid-bite mid-swim
    with no warning.
  * THE ORIGIN sits 1.0746 BU toward the nose and 0.387 BU below body centre, so rotating
    about it sweeps the tail through a 3.59 BU circle: a 64-frame sheet has the shark
    orbiting the frame instead of spinning in place.
  * A STALE FINAL KEYFRAME on every clip duplicates the cycle's first frame. Harmless on a
    static torso; it double-holds a frame in C.5's flop loop.
  * HEAD IS A ROOT BONE (C.18a) no swim clip touches, so the snout is welded to world
    space and a thrashing spine cannot lift his head off the ground. `reparent_head` hangs
    it off SPINE_01 where the rest geometry says it belongs. OFF by default (the shipped
    sheets came off the rig as bought).
  All four run against the bought model IN MEMORY: the licence means there is no committed
  rig to fix.

AND WHAT IT POSES. `model.action` picks one of the five shipped clips (or `rest`),
`model.frame` a frame of it, and `model.pose_gain` amplifies every bone's rotation about
rest. `model.phase_lock` takes the swim's travelling wave toward a standing one (every
spine joint pulled into step with the tail: the flop's curl-and-snap, not propulsion).
`model.amplitude_even` evens the swing down the spine so the curl bottoms in the middle,
and `model.recentre` turns the whole body back against the curl so head and tail rise
together instead of the tail swinging off a pinned nose (C.5.8's U). `bounce.*` adds a
per-frame ballistic lift, which the shadow pass turns into real shadow separation for
free. All ordinary knobs, so cache keys and provenance stamps cover a flop frame exactly as
a standing one.

ENGINE, measured not assumed: the body pass defaults to EEVEE Next; the shadow pass must be
Cycles. Only Cycles honours `is_shadow_catcher`; EEVEE Next accepts the attribute and
renders the plane fully opaque. Numbers in tools/README.md and the config comments.

THREE PASSES. `body` and `shadow` differ in engine and canvas; `mask` differs in MATERIAL.
It drops the shark's textures, puts one flat grey shader on every mesh and drives its
ALPHA from a band function of the model's own local coordinates, so what lands on disk is
the harness alone, at the body pass's camera and canvas. Factorio tints that layer with the
player's colour (C.4b); the [mask] block in jamaltron.toml says why it is the harness and
not the whole fish.
"""

# sys.path, verbatim per tools/README.md -- Python and Blender both put THIS file's own
# directory on sys.path[0], never tools/, and `package = false` means there is no installed
# `render` to fall back on. Cannot be factored into a helper: importing the helper is the
# thing that needs the path fixed.
import pathlib, sys  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
import math
import os
import time

import bpy
import mathutils
import numpy as np

from render import artconfig as ac
from render import factorio_camera as fc
from render import pose


# --------------------------------------------------------------------------------- args


def parse_args():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    out = {"config": None, "pass": "body", "frames": None, "out": None}
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--config", "--pass", "--frames", "--out"):
            out[a[2:]] = args[i + 1]
            i += 2
        else:
            i += 1
    if not out["config"] or not out["out"]:
        raise SystemExit("render_jamal.py needs --config and --out")
    out["frames"] = [int(x) for x in out["frames"].split(",")] if out["frames"] else None
    return out


# ------------------------------------------------------------------------- C.2 fixes


def mute_nla_tracks():
    """Silence every NLA track and clear the active action. Returns what it muted."""
    muted = []
    for ob in bpy.data.objects:
        ad = ob.animation_data
        if not ad:
            continue
        for track in ad.nla_tracks:
            if not track.mute:
                muted.append("%s/%s" % (ob.name, track.name))
            track.mute = True
        ad.action = None
    return muted


def clear_pose(obj):
    """Put an armature in its rest pose. Muting NLA is not enough -- the pose bones keep
    whatever basis the file was saved with, and `pivot` was measured on the REST box."""
    if obj is None or obj.type != "ARMATURE":
        return 0
    n = 0
    for pb in obj.pose.bones:
        if pb.matrix_basis != mathutils.Matrix.Identity(4):
            n += 1
        pb.matrix_basis = mathutils.Matrix.Identity(4)
    return n


def reparent_head(obj, child: str = "HEAD", parent: str = "SPINE_01") -> str:
    """C.18a: give HEAD a parent, IN MEMORY, before anything is posed. Returns what it did.

    THE RIG SHIPS THE SNOUT WELDED TO WORLD SPACE. HEAD is a root bone no swim clip touches,
    so at roll 80-90 (where the bend plane stands up into the bounce's plane and the pose is
    a curl-up) his head cannot leave the ground whatever the spine does. Six spine bones fold
    and the face stays nailed down: a shark bolted to the floor, not one trying to get off it.

    The rest geometry agrees with the fix: HEAD's head sits at x 0.708 and SPINE_01's at
    0.577, so HEAD is the next link forward on the chain SPINE_02..TAIL already form.
    Parenting without connecting keeps its rest position to the float, so a REST render is
    untouched.

    MEASURED, because silently doing nothing is the failure mode here. Two renders of dir 16
    at roll 85, this knob the only difference:
      * AT REST the two PNGs' IDAT streams are byte-identical (only Blender's render-time
        tEXt differs), so the fix cannot disturb the shipped sheets.
      * PLAYING SWIM_FAST it moves 1448 px at frame 7 and 2555 px at frame 20 (1.0% and
        1.7% of the canvas), all inside a 60 px box on the head. It took.
      * IT IS SMALLER THAN C.18a HOPED: the snout travels at most 0.056 BU (2.9 px at 64
        px/tile) and the ALPHA BOX does not move, so at gain 1.0 the head shifts WITHIN his
        outline rather than lifting clear of the ground. Structural: SPINE_01 is itself a
        root bone and, on a wave rear-loaded 3:1, the first joint rotates least (~4.3 deg
        here). The travel is almost pure model-space Y (-0.0559 y against +0.0002 z): the
        swim bends laterally and the ROLL stands that plane up, which is why 80-90 is the
        pose. So this is necessary and NOT sufficient: it stops the neck stretching against
        a pinned skull, and the lift comes from the bounce.

    IT HAS TO RUN AT RENDER TIME. The .blend is the bought model under a licence whose one
    condition is that the source never ships, so there is no committed rig fix (the same
    reason the NLA mute, the stale-keyframe drop and the re-pivot live in this file).
    `model.reparent_head` defaults off because the sheets in mod/jamaltron/graphics/ came
    off the rig as bought.

    Raises if either bone is missing: a silent no-op would look exactly like a pose that did
    not need the fix.
    """
    if obj is None or obj.type != "ARMATURE":
        raise SystemExit("reparent_head: %r is not an armature" % (obj and obj.name))
    bones = obj.data.bones
    for name in (child, parent):
        if name not in bones:
            raise SystemExit("reparent_head: no bone %r on %s; have %s"
                             % (name, obj.name, [b.name for b in bones]))
    was = bones[child].parent.name if bones[child].parent else None
    if was == parent:
        return "%s was ALREADY parented to %s -- nothing to do" % (child, parent)
    head_x = tuple(round(v, 4) for v in bones[child].head_local)
    parent_x = tuple(round(v, 4) for v in bones[parent].head_local)

    # Bone parenting is an EDIT-MODE edit; no pose-mode or data-level path sets it. In
    # background mode the operator needs an active object, left in OBJECT mode afterwards or
    # the armature modifier evaluates against an edit-mode copy.
    bpy.context.view_layer.objects.active = obj
    prev_mode = obj.mode
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        eb = obj.data.edit_bones
        eb[child].parent = eb[parent]
        # KEEP OFFSET, not connect: connecting would snap HEAD's root onto SPINE_01's tip
        # and move the snout 0.13 BU back into his own skull.
        eb[child].use_connect = False
    finally:
        bpy.ops.object.mode_set(mode=prev_mode if prev_mode != "EDIT" else "OBJECT")

    now = bones[child].parent.name if bones[child].parent else None
    if now != parent:
        raise SystemExit("reparent_head: asked for %s -> %s and the rig still says %s -> %s"
                         % (child, parent, child, now))
    moved = tuple(round(v, 4) for v in bones[child].head_local)
    return ("%s parent %s -> %s, rest head %s (was %s, %s sits at %s)"
            % (child, was, parent, moved, head_x, parent, parent_x))


def apply_action(cfg, obj):
    """Put the rig on ONE frame of ONE clip, amplified `model.pose_gain` about rest.

    This is what `model.action` MEANS. Without an action, `model.rest_pose = false` does not
    pick a clip: it unmutes all five NLA tracks at once and `model.frame` scrubs whatever
    that soup evaluates to (BITE_01 blends COMBINE on top, so the shark renders mid-bite
    mid-swim). One action, assigned explicitly, on a cleared pose.

    BAKE THEN AMPLIFY. Read every bone's evaluated basis, drop the animation so nothing can
    overwrite it, then push each bone's rotation away from rest by `gain`. AXIS-ANGLE, not
    slerp: slerp refuses a factor above 1.0, the only interesting direction while gain was
    still open. Dropping the action first is what lets the pose survive the render's later
    `scene.frame_set`.

    Returns (note, wave): the note is the log line (action, frame, how many bones moved) and
    `wave` is what `model.phase_lock` did, None when it is 0 (phase_locked lists its keys).
    Zero bones moved is a failure, not a quiet success: the action evaluated to nothing.
    """
    if obj is None or obj.type != "ARMATURE":
        raise SystemExit("model.action=%s needs model.object to be the ARMATURE; %r is %s"
                         % (cfg["model.action"], cfg["model.object"],
                            "missing" if obj is None else obj.type))
    action_id = cfg["model.action"]
    clip = pose.clip_of(action_id)
    if clip is None:
        raise SystemExit("model.action=%r is not a clip; expected one of %s"
                         % (action_id, ", ".join(pose.ACTION_CHOICES)))
    act = bpy.data.actions.get(clip.action)
    if act is None:
        raise SystemExit("model.action=%s wants action %r; the model has %s"
                         % (clip.id, clip.action, [a.name for a in bpy.data.actions]))
    frame = pose.clamp_frame(clip.id, cfg["model.frame"])
    gain = float(cfg["model.pose_gain"])
    lock = float(cfg["model.phase_lock"])
    even = float(cfg["model.amplitude_even"])

    obj.data.pose_position = "POSE"
    ad = obj.animation_data or obj.animation_data_create()
    for track in ad.nla_tracks:
        track.mute = True
    ad.action = None
    clear_pose(obj)

    assign_action(obj, act)
    baked = _bake_at(obj, clip, frame)
    wave = None
    if (lock or even) and clip.wave:
        # Only the joints the wave runs through move off `frame`; everything else -- HEAD
        # after the reparent, the fins, the jaw -- stays exactly where the plain path put it.
        baked, wave = phase_locked(obj, clip, frame, lock, baked, even)
    elif lock or even:
        knobs = " / ".join(n % v for n, v in (("phase_lock %.2f", lock),
                                               ("amplitude_even %.2f", even)) if v)
        wave = {"skipped": True,
                "note": "%s SKIPPED: %s is not a wave, so there is no lag to cancel and no "
                        "swing to even -- the knob moved the hash and nothing else"
                        % (knobs, clip.id)}
    # Per-joint gain on top of pose_gain: model.amplitude_even's, empty at 0 so the plain
    # path multiplies by exactly `gain`.
    joint_gain = (wave or {}).get("gains") or {}
    ad.action = None
    posed = []
    for pb in obj.pose.bones:
        loc, rot, scl = baked[pb.name].decompose()
        axis, angle = rot.to_axis_angle()
        if abs(angle) > 1e-9 or loc.length > 1e-9:
            posed.append(pb.name)
        g = gain * joint_gain[pb.name] if pb.name in joint_gain else gain
        pb.matrix_basis = (mathutils.Matrix.Translation(loc * g)
                           @ mathutils.Quaternion(axis, angle * g).to_matrix().to_4x4()
                           @ mathutils.Matrix.Diagonal(scl).to_4x4())
    bpy.context.view_layer.update()
    if not posed:
        raise SystemExit(
            "model.action=%s frame %d posed NOTHING. The action exists and evaluated to the "
            "rest pose, which on Blender 4.4 usually means it landed with no action slot "
            "bound (see assign_action)." % (clip.id, frame))
    return ("%s (%s) frame %d of %d-%d, gain %.2f, on a CLEARED pose (so model.rest_pose "
            "stops meaning anything) -- %d bones posed: %s"
            % (clip.id, clip.action, frame, clip.lo, clip.hi, gain, len(posed),
               ", ".join(sorted(posed)))), wave


def _bake_at(obj, clip, t: float) -> dict:
    """Every bone's basis with the assigned action evaluated at time `t` of `clip`; `t` may
    be FRACTIONAL and anywhere in [lo, lo + span).

    THE SEAM IS WHY THIS IS NOT ONE frame_set. drop_stale_final_keyframes() removed the final
    key and the curves extrapolate CONSTANT, so Blender evaluates all of (hi, hi + 1) as a
    frozen copy of hi -- MEASURED, the TAIL reads 10.178 deg at 20.00, 20.25, 20.50, 20.75
    and 21.00, then 10.993 at frame 1. A joint shifted into that last frame would hold for a
    frame and pop, once per loop. So that interval is bridged by hand, hi -> lo: the loop
    plays lo after hi, so that is the step a shifted joint must make to stay on its loop.

    WHAT THE BRIDGE IS NOT (measured in review): the bought curve. The dropped key was never
    an exact copy of lo (up to 1.0 deg off, SWIM_FAST SPINE_06), and linear/slerp against the
    bought Bezier across that frame is off by up to 0.47 deg (2.2% of that joint's swing) on
    FAST, 0.18 on MEDIUM, 0.73 on SLOW. SWIM_SLOW is worse than one frame: it is MEDIUM
    retimed 2x with its first key left at frame 1, so its true period is 80 and the table's
    78 squeezes two frames of motion into this one -- a hitch the bought loop already plays
    at 78 -> 1, which a lock spreads across joints rather than adds to (PLAN C.26).
    """
    t = pose.wrap_time(t, clip.lo, clip.span)
    if t <= clip.hi:
        whole = int(math.floor(t))
        bpy.context.scene.frame_set(whole, subframe=t - whole)
        bpy.context.view_layer.update()
        return {pb.name: pb.matrix_basis.copy() for pb in obj.pose.bones}
    w = t - clip.hi
    a, b = _bake_at(obj, clip, clip.hi), _bake_at(obj, clip, clip.lo)
    out = {}
    for name, ma in a.items():
        la, ra, sa = ma.decompose()
        lb, rb, sb = b[name].decompose()
        out[name] = (mathutils.Matrix.Translation(la.lerp(lb, w))
                     @ ra.slerp(rb, w).to_matrix().to_4x4()
                     @ mathutils.Matrix.Diagonal(sa.lerp(sb, w)).to_4x4())
    return out


def wave_chain(obj, samples: dict) -> list:
    """The joints the clip moves, root first -- or [] if they are not ONE parent chain.

    Chain order is what makes the lags mean anything (they accumulate joint to joint), and
    it is read off the rig, not bone names. A clip whose moving bones branch has no single
    "down the body" to measure along, so it is refused rather than guessed at.
    """
    moving = {name for name in samples[next(iter(samples))]
              if any(m[name].to_quaternion().angle > 1e-6 for m in samples.values())}
    bones = obj.data.bones
    chain = sorted(moving, key=lambda n: len(bones[n].parent_recursive))
    for prev, name in zip(chain, chain[1:]):
        if bones[name].parent is None or bones[name].parent.name != prev:
            return []
    return chain


def bend_signals(obj, chain: list, samples: dict) -> list:
    """One SIGNED bend angle per joint per frame, in radians.

    Each joint's rotation over the cycle is (nearly) about one axis -- MEASURED 0.99-1.00 of
    local x on every spine joint -- so the signal is the rotation vector projected on that
    joint's dominant axis. THE SIGN IS THE TRAP: an axis and its negative are the same axis,
    and the wrong pick reads as half a cycle of lag. So each axis is compared in ARMATURE
    space and flipped to agree with the joint in front (physically, "bends the same way");
    comparing bone-local axes would be fooled by any change of bone roll along the chain.
    """
    frames = sorted(samples)
    out, prev_axis = [], None
    for name in chain:
        vecs = []
        for f in frames:
            axis, angle = samples[f][name].to_quaternion().to_axis_angle()
            vecs.append(mathutils.Vector(axis) * angle)
        mean = sum(vecs, mathutils.Vector()) / len(vecs)
        centred = [v - mean for v in vecs]
        cov = mathutils.Matrix([[sum(v[i] * v[j] for v in centred) for j in range(3)]
                                for i in range(3)])
        axis = mathutils.Vector((1.0, 1.0, 1.0))
        for _ in range(64):                       # power iteration: 3x3, converges fast
            nxt = cov @ axis
            if nxt.length < 1e-12:
                break
            axis = nxt.normalized()
        arm_axis = obj.data.bones[name].matrix_local.to_3x3() @ axis
        if prev_axis is not None and arm_axis.dot(prev_axis) < 0.0:
            axis, arm_axis = -axis, -arm_axis
        prev_axis = arm_axis
        out.append([v.dot(axis) for v in vecs])
    return out


def phase_locked(obj, clip, frame: int, lock: float, baked: dict, even: float = 0.0) -> tuple:
    """`baked` with every wave joint re-sampled `lock` of the way into step with the tail.

    C.5.8: `even` (model.amplitude_even) rides the same measurement. Each joint's swing comes
    off the same bend signals as its lag, and pose.even_gains turns it into a per-joint gain
    apply_action multiplies into pose_gain (`wave["gains"]`, absent at 0 so the lock-only
    path C.5.1 verified is untouched).

    THE KNOB C.5's STANDING WAVE NEEDED (chotchki: a beached fish bends head and tail the
    SAME way at once, so the body curls into a U and snaps back, where the swim runs its bend
    nose to tail). Same bones and keyframes, different phase, so this reads the clip's own
    lag per joint and plays each joint from its own offset. pose.py's phase-lock block has
    the measured lags and why the TAIL holds still.

    MEASURED, NOT ASSUMED: the lags come off the clip every render, from the fundamental of
    each joint's bend over one cycle. They come back as data (chain / lags / offsets) and a
    note, and main() records both: a `FIX phase_lock` line for `-v` and the tuner's log, and
    the pass's JAMALTRON_RESULT. A skip is a WARN, because a skipped lock moved the hash and
    no pixel.
    """
    samples = {f: _bake_at(obj, clip, f) for f in range(clip.lo, clip.hi + 1)}
    chain = wave_chain(obj, samples)
    if len(chain) < 2:
        return baked, {"skipped": True,
                       "note": "phase_lock %.2f SKIPPED: %s moves no single bone chain to run "
                               "a wave down -- the knob moved the hash and nothing else"
                               % (lock, clip.id)}
    signals = bend_signals(obj, chain, samples)
    lags = pose.wave_lags(signals, clip.span)
    offsets = pose.lock_offsets(lags, lock)
    out = dict(baked)
    if lock:
        by_time = {}
        for name, off in zip(chain, offsets):
            t = round(pose.wrap_time(frame + off, clip.lo, clip.span), 6)
            if t not in by_time:
                by_time[t] = _bake_at(obj, clip, t)
            out[name] = by_time[t][name]
    note = ("phase_lock %.2f down %s: lag %s frames -> offset %s"
            % (lock, "/".join(chain), "/".join("%.2f" % v for v in lags),
               "/".join("%+.2f" % v for v in offsets)))
    wave = {"skipped": False, "chain": chain,
            "lags": [round(v, 4) for v in lags], "offsets": [round(v, 4) for v in offsets]}
    if even:
        amps = pose.wave_amplitudes(signals)
        gains = pose.even_gains(amps, even)
        wave["amps_deg"] = [round(math.degrees(a), 3) for a in amps]
        wave["gains"] = {name: g for name, g in zip(chain, gains)}
        note += ("; amplitude_even %.2f: swing %s deg -> gain %s"
                 % (even, "/".join("%.2f" % math.degrees(a) for a in amps),
                    "/".join("%.2f" % g for g in gains)))
    wave["note"] = note
    return out, wave


def assign_action(obj, act):
    """4.4 actions are SLOTTED; a bare `animation_data.action = act` can land with no slot
    and evaluate to NOTHING, a silent rest pose wearing a clip's name. Bind the first
    suitable slot. model_inspect.py carries its own copy because importing this one would
    drag in the whole 1100-line report harness."""
    if obj.animation_data is None:
        obj.animation_data_create()
    ad = obj.animation_data
    ad.action = act
    try:
        if getattr(ad, "action_slot", None) is None:
            slots = list(getattr(ad, "action_suitable_slots", []) or [])
            if slots:
                ad.action_slot = slots[0]
    except Exception:                                          # pragma: no cover
        pass
    return ad


def action_ranges():
    """Every action's frame range, raw and after the stale-keyframe drop. pose.verify_clips
    reads this to check the hardcoded clip table against the model on every posed render."""
    return {a.name: [float(v) for v in a.frame_range] for a in bpy.data.actions}


#: The holdout ground's object name. Skipped by every measurement, like the catcher.
HOLDOUT_NAME = "ground_holdout"


def world_box(skip=("shadow_catcher", HOLDOUT_NAME)):
    """The rendered geometry's world bounding box, in TILES (1 BU = 1 m = 1 tile).

    Measured off the EVALUATED depsgraph (subdivision and armature deform count) and AFTER
    build_rig, so it is the box the CANVAS has to hold, not the model's own.
    artconfig.derived() reports the REST box from a measured constant: right for the
    standing shark, wrong the moment he thrashes. This is the number C.17 needs and the one
    the bounce grows.

    EVERY VERTEX, NOT THE BOUND BOX. `ob.bound_box` is the mesh's LOCAL axis-aligned box, and
    eight corners of a box rolled 85 deg hang below anything the mesh reaches. MEASURED on
    the C.5.2 flop: up to 0.109 tiles too deep on the six frames where the curl tilts that
    local box (f01 and f16-f20, the back quarter of the loop), within 0.001 on the rest -- so
    the buried-body WARN overstated, and ground contact placed off it would float him. 10337
    verts at subdiv 1, ~1 ms through numpy.
    """
    lo, hi = None, None
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in bpy.data.objects:
        if ob.type != "MESH" or ob.name in skip:
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        try:
            n = len(me.vertices)
            if not n:
                continue
            co = np.empty(n * 3, dtype=np.float64)
            me.vertices.foreach_get("co", co)
            mw = np.array(ev.matrix_world, dtype=np.float64)
            world = co.reshape(n, 3) @ mw[:3, :3].T + mw[:3, 3]
        finally:
            ev.to_mesh_clear()
        a, b = world.min(axis=0), world.max(axis=0)
        lo = a if lo is None else np.minimum(lo, a)
        hi = b if hi is None else np.maximum(hi, b)
    if lo is None:
        return None
    return [[round(float(lo[i]), 4), round(float(hi[i]), 4)] for i in range(3)]


def _dominant_bones(ob, me):
    """Per vertex of `me` (ob's EVALUATED mesh), the deform bone weighting it hardest, or None
    for a vertex no bone moves. Returns (names, the rig's deform bones).

    DEFORM BONES ONLY. The model carries a TEETH group with no bone behind it; every vertex in
    it also carries bone weight (MEASURED), so reading bones alone files the teeth under the
    JAW or HEAD that actually move them, and ground_ignore can only name things that exist.
    Subdivision interpolates the weights onto the new vertices, so the evaluated mesh's own
    groups are the ones to read (its vertex order is not the base mesh's).
    """
    arm = next((m.object for m in ob.modifiers if m.type == "ARMATURE" and m.object), None)
    if arm is None or arm.type != "ARMATURE":
        return [None] * len(me.vertices), set()
    bones = {b.name for b in arm.data.bones if b.use_deform}
    names = {g.index: g.name for g in ob.vertex_groups}
    out = []
    for v in me.vertices:
        best, weight = None, 0.0
        for g in v.groups:
            name = names.get(g.group)
            if name in bones and g.weight > weight:
                best, weight = name, g.weight
        out.append(best)
    return out, bones


def ground_seat(ignore=()):
    """(seat, lowest) of the posed mesh in world tiles, each {"z", "bone", "object"}: `seat` is
    the lowest vertex NOT dominated by a bone in `ignore`, `lowest` the lowest of all.

    WHY CONTACT NEEDS A CHOICE OF VERTEX (chotchki, 2026-09-25, off the C.5.5 draft: "only the
    tip of his side fin is touching the ground which isn't realistic since that would bend and
    his main mass would be touching"). MEASURED over all 72 cells of the beached cycle: seated
    on his lowest vertex, the lower pectoral tip (FIN_RIGHT) props him on EVERY ground frame,
    0.24-0.42 tiles above the next seat. Ignore the pectorals alone and he drops onto the lower
    tip of the hammer (HEAD), trunk still 0.14-0.22 up; ignore HEAD/JAW too and the TRUNK
    FLANK seats him, while the caudal lobe stays eligible and still takes the flick frames'
    push-off. Everything ignored goes under z=0, which add_ground_holdout hides.

    Dominant bone, not "any weight": MEASURED on all 73 beached configs, skipping verts a fin
    bone dominates and skipping any vert with fin weight >= 0.01 seat him identically, and
    dominance cannot eat a strip of flank the fin root merely tugs on.

    Rounded to 4 places as world_box() rounds, so a seat that ignores nothing lands where
    plain contact does (MEASURED byte-identical, holdout floor and all). Unrounded, the 5e-5
    tile difference alone moved 631 edge pixels at the pause.

    Raises on a name that is not a deform bone: a typo would read as a rule that happened to
    change nothing.
    """
    ignore = set(ignore)
    dg = bpy.context.evaluated_depsgraph_get()
    seat = lowest = None
    known = set()
    for ob in bpy.data.objects:
        if ob.type != "MESH" or ob.name in ("shadow_catcher", HOLDOUT_NAME):
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        try:
            n = len(me.vertices)
            if not n:
                continue
            co = np.empty(n * 3, dtype=np.float64)
            me.vertices.foreach_get("co", co)
            mw = np.array(ev.matrix_world, dtype=np.float64)
            z = (co.reshape(n, 3) @ mw[:3, :3].T + mw[:3, 3])[:, 2]
            dom, bones = _dominant_bones(ob, me)
        finally:
            ev.to_mesh_clear()
        known |= bones
        i = int(np.argmin(z))
        zi = round(float(z[i]), 4)
        if lowest is None or zi < lowest["z"]:
            lowest = {"z": zi, "bone": dom[i], "object": ob.name}
        ok = np.array([d not in ignore for d in dom], dtype=bool)
        if ok.any():
            j = int(np.flatnonzero(ok)[np.argmin(z[ok])])
            zj = round(float(z[j]), 4)
            if seat is None or zj < seat["z"]:
                seat = {"z": zj, "bone": dom[j], "object": ob.name}
    if ignore - known:
        raise SystemExit("model.ground_ignore names %s, which %s no deform bone; the rig has %s"
                         % (sorted(ignore - known), "is" if len(ignore - known) == 1 else "are",
                            sorted(known)))
    if seat is None:
        raise SystemExit("ground_seat: every vertex is under an ignored bone (%s) -- nothing "
                         "is left to stand on" % sorted(ignore))
    return seat, lowest


def hold_fin_to_floor(rig, body_turn) -> tuple:
    """C.5.8, `model.fin_floor`: pin the LOWER pectoral's orientation to the floor (what it
    has on a rest spine with no body turn), keeping its own clip rotation and letting its
    root ride the chest. Returns (bone name, log line). Call after the recentre and before
    the fold; `body_turn` is the recentre's rotation in armature space (identity without one).

    WHY (chotchki 2026-09-26, "fix it", off the V4/V5 U: a long white spike under his chest).
    C.5.6's fold turns the fin a fixed 50 deg from wherever the pose left it, which lands it
    level only while the chest it hangs off (SPINE_02) sits near rest. MEASURED on V5's heave:
    the evened, doubled curl swings the chest so the fin dives 25-62 deg before any recentre
    (C+'s heave: 46-52), the recentre turns it up to 60 deg more, and after the fold its
    heading has swung from C+'s east-south-east round to due SOUTH at the U's bottom
    (f10-f11): a fin pointing at the camera, 51 px of spike straight down the screen.
    Levelling the span alone would not fix that, since a level fin pointing south is the
    same spike. Holding the whole orientation does, and it is what a fin pressed flat on the
    sand does anyway: the body curls above it, the fin stays where the floor put it.

    ORIENTATION, NOT CONTACT: the tip is not pulled down to z=0, so where the chest lifts off
    the sand (V5's arch frames, up to ~1 tile) the level fin lifts with it. The parents' pose
    is dropped whether or not a recentre ran: any posed spine changes the fin, only a rest
    spine with no turn leaves it as it was. fin_probe.py measures both on the real rig.

    WHICH FIN is decided off the HELD orientation, so the pick cannot flip frame to frame with
    the curl. Worked in ARMATURE space, like the fold, so build_rig's girth scale above the
    rig cannot shear it; the arithmetic is pose.floor_hold."""
    if rig is None or rig.type != "ARMATURE":
        raise SystemExit("model.fin_floor: %r is not an armature" % (rig and rig.name))
    fins = [n for n in ("FIN_LEFT", "FIN_RIGHT") if n in rig.pose.bones]
    if not fins:
        raise SystemExit("model.fin_floor: no FIN_LEFT / FIN_RIGHT bone on %s" % rig.name)
    bpy.context.view_layer.update()
    mw = rig.matrix_world
    turn = [list(r) for r in body_turn]
    held = {}
    for n in fins:
        pb = rig.pose.bones[n]
        rot = pose.floor_hold([list(r) for r in pb.bone.matrix_local.to_3x3()],
                              [list(r) for r in pb.matrix_basis.to_3x3()], turn)
        m3 = mathutils.Matrix(rot)
        tail = pb.head + m3 @ mathutils.Vector((0.0, pb.bone.length, 0.0))
        held[n] = (m3, (mw @ tail).z)
    name = min(fins, key=lambda n: held[n][1])
    pb = rig.pose.bones[name]

    def elev():
        d = (mw @ pb.tail) - (mw @ pb.head)
        return math.degrees(math.asin(max(-1.0, min(1.0, d.z / d.length))))

    was = elev()
    m4 = held[name][0].to_4x4()
    m4.translation = pb.head.copy()
    pb.matrix = m4
    bpy.context.view_layer.update()
    return name, ("%s held to the floor (rest orientation, body turn taken out): span "
                  "elevation %.1f -> %.1f deg" % (name, was, elev()))


def fold_lower_fin(rig, degrees: float, name: str | None = None) -> str:
    """C.5.6: fold whichever pectoral fin is LOWER up off the floor by `degrees`. Returns the
    log line. Call after build_rig: "lower" and "up" are world facts.

    WHY. On his side the lower pectoral's tip is the lowest vertex on every ground frame
    (MEASURED, FIN_RIGHT at roll 85 / yaw 180, 0.46-0.57 tiles under his trunk), so plain
    contact stands 400 kg of shark on one fin tip. A real fin taking that weight would bend;
    this is the bend.

    WHICH WAY is a world fact, not a bone axis: the two fins' local axes are NOT mirror
    images (FIN_LEFT's X is FIN_RIGHT's Z, near enough), so no one local axis folds both. The
    tip swings about the root, in the vertical plane through the fin's own span, toward
    straight up: the axis is span x up, which lifts the tip fastest per degree. At `degrees`
    equal to the span's dive the fin lies level; past it the tip climbs into his flank.
    Worked in ARMATURE space, where the bone is rigid: the rig sits under build_rig's girth
    scale, and a world-space rotation would shear it.

    Every frame folds by the same angle from wherever the clip put the fin, so a bite that
    swings the fins (BITE_01 turns FIN_RIGHT up to 47 deg) still folds from its own pose.
    That is also its limit: "wherever the clip put it" includes the chest's own swing and any
    body turn, and C.5.8's U has both; `model.fin_floor` (hold_fin_to_floor, which passes
    `name`) takes them out first.
    """
    if rig is None or rig.type != "ARMATURE":
        raise SystemExit("model.fin_fold: %r is not an armature" % (rig and rig.name))
    fins = [n for n in ("FIN_LEFT", "FIN_RIGHT") if n in rig.pose.bones]
    if not fins:
        raise SystemExit("model.fin_fold: no FIN_LEFT / FIN_RIGHT bone on %s" % rig.name)
    bpy.context.view_layer.update()
    mw = rig.matrix_world
    if name is None:
        name = min(fins, key=lambda n: (mw @ rig.pose.bones[n].tail).z)
    pb = rig.pose.bones[name]
    head, tail = pb.head.copy(), pb.tail.copy()                       # armature space
    span = tail - head
    # World up, pulled back into armature space as a DIRECTION.
    up = (mw.to_3x3().inverted() @ mathutils.Vector((0.0, 0.0, 1.0))).normalized()
    axis = span.cross(up)
    if axis.length < 1e-9:
        return "%s points straight down or up -- no plane to fold it in, left alone" % name
    dive = math.degrees(math.asin(max(-1.0, min(1.0, -span.normalized().dot(up)))))
    rot = mathutils.Matrix.Rotation(math.radians(degrees), 4, axis.normalized())
    pb.matrix = (mathutils.Matrix.Translation(head) @ rot
                 @ mathutils.Matrix.Translation(-head) @ pb.matrix)
    bpy.context.view_layer.update()
    tip_was, tip_now = (mw @ tail).z, (mw @ pb.tail).z
    return ("%s folded %.1f deg (its span dived %.1f deg in armature space): tip z %.3f -> %.3f"
            % (name, degrees, dive, tip_was, tip_now))


def chord_turn(rig, amount: float = 1.0) -> tuple:
    """(axis, radians, midpoint) of pose.counter_turn for the nose-to-tail chord
    (artconfig.RECENTRE_CHORD), in ARMATURE space: the turn that takes the posed chord
    `amount` of the way back to its rest direction, and the posed chord's midpoint. At
    amount 1 the angle is minus the chord's whole turn off rest."""
    first, last = ac.RECENTRE_CHORD
    bones = rig.data.bones
    missing = [n for n in (first, last) if n not in bones]
    if missing:
        raise SystemExit("model.recentre: no bone %s on %s; have %s"
                         % (missing, rig.name, [b.name for b in bones]))
    bpy.context.view_layer.update()
    rest = bones[last].tail_local - bones[first].head_local
    a, b = rig.pose.bones[first].head, rig.pose.bones[last].tail
    axis, angle = pose.counter_turn(tuple(rest), tuple(b - a), amount)
    return axis, angle, (a + b) / 2.0


def recentre_model(rig, amount: float) -> str:
    """C.5.8 / C.5.3: turn the whole posed model back AGAINST its curl by `amount` of the
    chord's turn, about the chord's own midpoint. Returns the log line. Call after build_rig
    and apply_action, and BEFORE the sag, the fold and contact.

    WHY. SPINE_01 is a ROOT bone at the nose, so every degree of curl the clip adds shows as
    the tail swinging while the nose stays pinned -- MEASURED at lock 1 (C.5.2) a coherent
    50.8 deg curl that reads as a tail flick hinged at his head, not a U. A beached fish's U
    closes symmetrically, head and tail rising TOGETHER. At 1 this holds the chord level
    (nose and tail tip at the same relative height as at rest), the symmetric U; the curl
    itself is untouched -- this moves the body, not a bone.

    WHERE. On the armature OBJECT, in its own space, so it is a rigid turn of the posed body
    inside build_rig's girth scale: the space the clip bends in, so the counter-turn lies in
    the bend plane. About the chord MIDPOINT rather than the pivot, so his middle stays put
    on the canvas; contact re-seats him vertically afterwards anyway.

    BEFORE THE SAG: the chord is read off the clip's pose alone. The sag bends the back half
    DOWN on purpose (C.5.6), and measured after it the recentre would undo half of that
    every frame.
    """
    axis, angle, mid = chord_turn(rig, amount)
    if axis is None or abs(angle) < 1e-9:
        return "chord on its rest direction -- nothing to counter-rotate"
    turn = mathutils.Quaternion(axis, angle).to_matrix().to_4x4()
    rig.matrix_basis = (rig.matrix_basis @ mathutils.Matrix.Translation(mid) @ turn
                        @ mathutils.Matrix.Translation(-mid))
    bpy.context.view_layer.update()
    return ("chord %s->%s turned off rest; model turned back %.2f deg (recentre %.2f) about "
            "axis %s through the chord midpoint"
            % (ac.RECENTRE_CHORD[0], ac.RECENTRE_CHORD[-1], -math.degrees(angle), amount,
               "/".join("%+.2f" % v for v in axis)))


def sag_spine(rig, degrees: float) -> str:
    """Lay the back half of him DOWN: bend every joint of artconfig.SPINE_SAG_CHAIN (SPINE_04
    .. TAIL) `degrees` further toward the floor, on top of the clip's pose. Returns the log
    line. Call after build_rig: "toward the floor" is a world fact.

    WHY. Contact seats his trunk, but the model's spine is straight and LEVEL -- MEASURED at
    rest on his side, SPINE_01 0.838 tiles up, SPINE_04 0.839, the TAIL tip 0.852 -- so the
    spine rides at the trunk's half-thickness and the tapered tail cannot reach the floor
    however he is seated: its underside hangs 0.27 tiles over his trunk at rest, 0.38 at the
    pause. A real fish that size on sand lies along its whole length.

    WHICH AXIS. Each joint's bone-local X, the axis the swim itself bends about (MEASURED
    0.99-1.00 of local x on every spine joint), pre-multiplied onto the clip's basis so it
    turns about the joint's REST X. At roll 85 that bend plane stands within 5 deg of
    vertical, which is why a sideways bend can lay the tail down at all. The SIGN is found per
    joint off the REST geometry in world space (the way +X swings the tail tip), so "+
    droops" holds on whichever flank he lies and cannot flip frame to frame with the curl.
    """
    if rig is None or rig.type != "ARMATURE":
        raise SystemExit("model.spine_sag: %r is not an armature" % (rig and rig.name))
    missing = [n for n in ac.SPINE_SAG_CHAIN if n not in rig.pose.bones]
    if missing:
        raise SystemExit("model.spine_sag: no bone %s on %s; have %s"
                         % (missing, rig.name, [b.name for b in rig.data.bones]))
    bpy.context.view_layer.update()
    mw = rig.matrix_world
    m3 = mw.to_3x3()
    bones = rig.data.bones
    last = ac.SPINE_SAG_CHAIN[-1]
    tip_rest = bones[last].tail_local
    tip_was = (mw @ rig.pose.bones[last].tail).z
    signs = []
    for name in ac.SPINE_SAG_CHAIN:
        b = bones[name]
        x_axis = b.matrix_local.to_3x3().col[0]
        # Where +X swings the tip, in WORLD: a linear map carries a velocity exactly, girth too.
        swing = m3 @ x_axis.cross(tip_rest - b.head_local)
        sign = -1.0 if swing.z > 0.0 else 1.0
        signs.append(sign)
        pb = rig.pose.bones[name]
        pb.matrix_basis = (mathutils.Matrix.Rotation(math.radians(sign * degrees), 4, "X")
                           @ pb.matrix_basis)
    bpy.context.view_layer.update()
    tip_now = (mw @ rig.pose.bones[last].tail).z
    return ("%s bent %.1f deg each toward the floor (about local %sX): tail tip z %.3f -> %.3f"
            % ("/".join(ac.SPINE_SAG_CHAIN), degrees,
               "+" if all(v > 0 for v in signs) else
               "-" if all(v < 0 for v in signs) else "mixed-sign ", tip_was, tip_now))


def lay_on_floor(cfg, rig) -> list:
    """The posed rig's floor fixes in the ONE order they must run: recentre, sag, fin hold,
    fin fold. Returns the log lines. main() calls it between build_rig and contact, and a
    measuring script that calls it poses exactly what renders.

    The recentre goes FIRST, off the clip's pose alone: the sag bends him on purpose and must
    not be levelled away (recentre_model says why). All of it goes BEFORE contact, because
    the sag and the fold both move what contact measures. The fin hold follows the recentre
    because its job is taking the body turn back out, and precedes the fold because the fold
    was tuned on the orientation it restores.
    """
    lines = []
    before = rig.matrix_basis.copy()
    if cfg["model.recentre"]:
        lines.append("FIX recentre: " + recentre_model(rig, cfg["model.recentre"]))
    if cfg["model.spine_sag"]:
        lines.append("FIX spine sag: " + sag_spine(rig, cfg["model.spine_sag"]))
    fin = None
    if cfg["model.fin_floor"]:
        # The recentre's turn is a right-multiply on the basis, so this is exactly it.
        turn = (before.inverted() @ rig.matrix_basis).to_3x3()
        fin, note = hold_fin_to_floor(rig, turn)
        lines.append("FIX fin floor: " + note)
    if cfg["model.fin_fold"]:
        lines.append("FIX fin fold: " + fold_lower_fin(rig, cfg["model.fin_fold"], fin))
    return lines


def add_ground_holdout(scene, size_tiles):
    """A plane at z=0 that PUNCHES OUT whatever is under it, for the body and mask passes.

    The shadow pass needs none: its catcher is already an opaque plane at z=0 to the camera,
    and geometry below it casts nothing onto its upper face. The other two draw no ground, so
    without this a sunk shark renders whole and the shadow looks slid out from under him.
    CAMERA-ONLY on purpose: it must hide, not light (no shadow, no bounce light, no probe),
    so every pixel of him above the floor is the pixel he had without it.
    """
    bpy.ops.mesh.primitive_plane_add(size=size_tiles * 2, location=(0, 0, 0))
    plane = bpy.context.active_object
    plane.name = HOLDOUT_NAME
    mat = bpy.data.materials.new("jamaltron_ground_holdout")
    mat.use_nodes = True
    nt = mat.node_tree
    for node in list(nt.nodes):
        if node.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(node)
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    hold = nt.nodes.new("ShaderNodeHoldout")
    nt.links.new(hold.outputs[0], out.inputs["Surface"])
    plane.data.materials.append(mat)
    for attr in ("visible_shadow", "visible_diffuse", "visible_glossy",
                 "visible_transmission", "visible_volume_scatter"):
        if hasattr(plane, attr):
            setattr(plane, attr, False)
    for attr in ("hide_probe_volume", "hide_probe_sphere", "hide_probe_plane"):
        if hasattr(plane, attr):
            setattr(plane, attr, True)
    return plane


def ground_contact(cfg, subject) -> float:
    """C.5.4: put the posed body's LOWEST VERTEX on the ground, plus this frame's bounce lift.
    Returns the world-z shift it applied, in tiles.

    C.5.6 bends the rule two ways, both off by default. `model.ground_ignore` names bones
    whose verts do not count (ground_seat), so the floor can hold him on his trunk and let a
    fin or the hammer go under. `model.ground_sink` then lowers him that much more, belly
    pressed in. Whatever ends up under z=0 the holdout ground hides (add_ground_holdout; the
    shadow pass's catcher already does).

    `model.offset` z places the model's ORIGIN: right for the standing shark, who rides his
    legs at a set height, wrong for a posed one, whose lowest point moves every frame. At the
    C.5.2 call (roll 85, lock 0.5) a fixed offset z of 0.5 left him 0.105-0.430 tiles UNDER
    the floor on all 20 frames, invisible in the tuner (the body pass draws no ground) and
    sliced by the shadow pass's catcher. So this measures instead: evaluate the posed mesh,
    find its lowest vertex, move `adjust` so that vertex sits at exactly bounce_lift(cfg).
    Offset z drops out entirely (added in build_rig, cancelled here), which is why
    artconfig.hashable() pins it out of the cache key while this is on.

    Beyond "not buried": the half of the curl that bends DOWN now lifts his middle off the
    floor, the arch a fish on its side actually makes, and the bounce is measured from where
    he touches, so the landing frame is a real landing.

    The wheel's per-direction spin is about world z, so one measurement holds for every
    direction this process renders. Same code in all three passes, so body, shadow and mask
    stay stacked.
    """
    adjust = subject.parent.parent if subject.parent else None
    # split("."): Blender suffixes a repeated name .001 (a second build_rig in one session
    # does this); it is still build_rig's adjust empty and still the thing to move.
    if adjust is None or adjust.name.split(".")[0] != "jamaltron_adjust":
        raise SystemExit("ground_contact: %r is not under build_rig's adjust empty" % subject.name)
    bpy.context.view_layer.update()
    if cfg["model.ground_ignore"]:
        floor = ground_seat(cfg["model.ground_ignore"])[0]["z"]
    else:
        box = world_box()
        if box is None:
            raise SystemExit("ground_contact: no mesh to put on the ground")
        floor = box[2][0]
    shift = ac.bounce_lift(cfg) - cfg["model.ground_sink"] - floor
    adjust.location.z += shift
    bpy.context.view_layer.update()
    return shift


def drop_stale_final_keyframes():
    """Remove each action's last keyframe -- it duplicates the cycle's first frame.

    C.2 measured SWIM_FAST at frames 1..21 for a 20-frame cycle: frame 21 IS frame 1, so
    playing 1..21 holds the pose two frames at the seam. Only touches curves with at least
    three keys, so a two-key action is never gutted.
    """
    dropped = []
    for action in bpy.data.actions:
        curves = [fcu for slot in _fcurve_groups(action) for fcu in slot]
        if not curves:
            continue
        last = max(kp.co[0] for fcu in curves for kp in fcu.keyframe_points)
        removed = 0
        for fcu in curves:
            if len(fcu.keyframe_points) < 3:
                continue
            for kp in list(fcu.keyframe_points):
                if abs(kp.co[0] - last) < 1e-6:
                    fcu.keyframe_points.remove(kp)
                    removed += 1
            fcu.update()
        if removed:
            dropped.append("%s@%g (%d curves)" % (action.name, last, removed))
    return dropped


def _fcurve_groups(action):
    """Blender 4.4 keeps fcurves on layered slots; 4.2 and earlier on action.fcurves.
    Yield whichever this build actually has so the fix works on both."""
    if hasattr(action, "layers") and len(action.layers):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in getattr(strip, "channelbags", ()):
                    yield bag.fcurves
    elif hasattr(action, "fcurves"):
        yield action.fcurves


def dead_image_check():
    """C.2 flagged two GREATWHITE image refs that do not resolve (the seller's other
    model). Prove they cannot reach a render: report every unresolvable image and whether
    any shader node using it has an outgoing link."""
    findings = []
    for img in bpy.data.images:
        if img.source == "VIEWER":
            continue
        path = bpy.path.abspath(img.filepath) if img.filepath else ""
        if path and os.path.exists(path):
            continue
        wired, live = [], False
        for mat in bpy.data.materials:
            if not mat.use_nodes or not mat.node_tree:
                continue
            for node in mat.node_tree.nodes:
                if getattr(node, "image", None) is img:
                    links = [l for o in node.outputs for l in o.links]
                    wired.append("%s/%s:%d links" % (mat.name, node.name, len(links)))
                    live = live or bool(links)
        findings.append({"image": img.name, "path": img.filepath,
                         "users": img.users, "wired_into": wired, "live": live})
    return findings


# --------------------------------------------------------------------------- mask pass


def _band(nt, source, centre: float, width: float, edge: float, x: int, y: int):
    """A soft window on one scalar socket: 1 inside `centre +- width/2`, 0 outside.

    Three nodes, |v - centre| through a smoothstep: the symmetric form needs one Map Range
    where two one-sided ramps need two plus a multiply. `edge` is the ramp width in the
    SOURCE's units (BU here), so a config comment can state it in pixels and be right.
    """
    sub = nt.nodes.new("ShaderNodeMath")
    sub.operation = "SUBTRACT"
    sub.location = (x, y)
    sub.inputs[1].default_value = centre
    nt.links.new(source, sub.inputs[0])

    absolute = nt.nodes.new("ShaderNodeMath")
    absolute.operation = "ABSOLUTE"
    absolute.location = (x + 170, y)
    nt.links.new(sub.outputs[0], absolute.inputs[0])

    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.data_type = "FLOAT"
    ramp.interpolation_type = "SMOOTHSTEP"
    ramp.clamp = True
    ramp.location = (x + 340, y)
    nt.links.new(absolute.outputs[0], ramp.inputs[0])
    ramp.inputs[1].default_value = width / 2.0            # From Min: still fully inside
    ramp.inputs[2].default_value = width / 2.0 + edge     # From Max: fully outside
    ramp.inputs[3].default_value = 1.0                    # To Min
    ramp.inputs[4].default_value = 0.0                    # To Max
    return ramp.outputs[0]


def _lid(nt, source, off: float, on: float, x: int, y: int):
    """A one-sided smooth step on one coordinate: 0 at `off`, 1 at `on`.

    Direction is carried by which of the two is larger, so the same node builds the
    plate's floor (0 below, 1 above) and its ceiling (1 below, 0 above) with no second
    code path or sign convention to get backwards.
    """
    ramp = nt.nodes.new("ShaderNodeMapRange")
    ramp.data_type, ramp.interpolation_type, ramp.clamp = "FLOAT", "SMOOTHSTEP", True
    ramp.location = (x, y)
    nt.links.new(source, ramp.inputs[0])
    ramp.inputs[1].default_value = off
    ramp.inputs[2].default_value = on
    ramp.inputs[3].default_value = 0.0
    ramp.inputs[4].default_value = 1.0
    return ramp.outputs[0]


def _math(nt, operation: str, a, b, x: int, y: int):
    node = nt.nodes.new("ShaderNodeMath")
    node.operation = operation
    node.location = (x, y)
    nt.links.new(a, node.inputs[0])
    nt.links.new(b, node.inputs[1])
    return node.outputs[0]


def build_mask_material(cfg):
    """One flat grey shader whose alpha is the harness. Returns (material, note).

    OBJECT coordinates, not world: the band must stay put on his body while the rig spins
    under the camera, and Texture Coordinate -> Object is the mesh's own rest space (where
    C.2 measured the bounding box and `model.pivot` is stated). World coordinates would
    sweep the straps around him once per sheet.

    DITHERED, not BLENDED, and backfaces culled. Alpha-blended EEVEE geometry writes no
    depth, so the strap on his far flank draws THROUGH his back: a ghost strap that survives
    all the way to a screenshot. Hashed alpha writes depth per accepted sample, so sorting is
    right and the 2 px ramp resolves against the TAA samples the body pass already pays for.
    """
    mat = bpy.data.materials.new("jamaltron_mask")
    mat.use_nodes = True
    mat.use_backface_culling = True
    note = "BLENDED/legacy"
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = "DITHERED"
        note = "DITHERED"
    elif hasattr(mat, "blend_method"):
        mat.blend_method = "HASHED"
        note = "HASHED"

    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    grey = cfg["mask.grey"]
    bsdf.inputs["Base Color"].default_value = (grey, grey, grey, 1.0)
    for name, value in (("Metallic", 0.0), ("Roughness", 0.55),
                        ("Specular IOR Level", 0.2)):
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.0

    if cfg["mask.mode"] == "silhouette":
        bsdf.inputs["Alpha"].default_value = 1.0
        return mat, "%s, silhouette (the WHOLE shark tints)" % note

    fore, aft = cfg["mask.strap_fore"], cfg["mask.strap_aft"]
    width, edge = cfg["mask.strap_width"], cfg["mask.edge"]

    coords = nt.nodes.new("ShaderNodeTexCoord")
    coords.location = (-1400, 0)
    split = nt.nodes.new("ShaderNodeSeparateXYZ")
    split.location = (-1200, 0)
    nt.links.new(coords.outputs["Object"], split.inputs[0])

    strap_a = _band(nt, split.outputs["X"], fore, width, edge, -1020, 240)
    strap_b = _band(nt, split.outputs["X"], aft, width, edge, -1020, 40)
    # The plate spans strap centre to strap centre, so it meets both straps rather than
    # leaving a two-pixel gap that reads as a printing error.
    span = _band(nt, split.outputs["X"], (fore + aft) / 2.0, abs(fore - aft), edge,
                 -1020, -160)
    # TWO LIDS; THE UPPER ONE IS NOT OPTIONAL. With only a floor the plate is "everything in
    # the span above plate_z", and the tallest thing in the span is the DORSAL FIN (x
    # -0.62..0.20 carries body up to z 0.54 and fin to 1.44), so an unbounded plate tints the
    # fin base to tip and the colour picker paints his fin. A saddle stops where the back
    # stops.
    floor_lid = _lid(nt, split.outputs["Z"], cfg["mask.plate_z"],
                     cfg["mask.plate_z"] + edge, -680, -360)
    ceil_lid = _lid(nt, split.outputs["Z"], cfg["mask.plate_top_z"],
                    cfg["mask.plate_top_z"] - edge, -680, -560)

    plate = _math(nt, "MULTIPLY", span, floor_lid, -480, -260)
    plate = _math(nt, "MULTIPLY", plate, ceil_lid, -380, -300)
    straps = _math(nt, "MAXIMUM", strap_a, strap_b, -480, 140)
    total = _math(nt, "MAXIMUM", straps, plate, -300, 0)
    nt.links.new(total, bsdf.inputs["Alpha"])
    return mat, ("%s, harness straps x=%+.2f/%+.2f w=%.2f, plate z=%.2f..%.2f, "
                 "edge %.3f BU"
                 % (note, fore, aft, width, cfg["mask.plate_z"],
                    cfg["mask.plate_top_z"], edge))


def apply_mask_material(cfg):
    """Put the mask material on every mesh, replacing whatever was there."""
    mat, note = build_mask_material(cfg)
    used = []
    for ob in bpy.data.objects:
        if ob.type != "MESH":
            continue
        ob.data.materials.clear()
        ob.data.materials.append(mat)
        used.append(ob.name)
    return "%s on %s" % (note, ", ".join(used) or "NOTHING -- no mesh in the scene")


# -------------------------------------------------------------------------- scene prep


def strip_scene(scene):
    """Delete the cameras and lights the .blend ships with. C.2 hazard: the file has its
    own 50 mm perspective camera and a 157 W area lamp, and inheriting either makes a render
    that looks fine and is not a Factorio sprite."""
    removed = []
    for ob in list(bpy.data.objects):
        if ob.type in ("CAMERA", "LIGHT"):
            removed.append("%s(%s)" % (ob.name, ob.type))
            bpy.data.objects.remove(ob, do_unlink=True)
    return removed


def setup_world(scene, ambient):
    world = bpy.data.worlds.new("jamaltron_world")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
    bg.inputs[1].default_value = ambient
    return world


def tune_materials(cfg):
    """Apply the two material knobs; both exist because the model was authored for a beauty
    render and this is a 132 px sprite."""
    notes = []
    for mat in bpy.data.materials:
        if not mat.use_nodes or not mat.node_tree:
            continue
        for node in mat.node_tree.nodes:
            if node.type == "BSDF_PRINCIPLED" and "Subsurface Weight" in node.inputs:
                want = 1.0 if cfg["render.use_subsurface"] else 0.0
                if abs(node.inputs["Subsurface Weight"].default_value - want) > 1e-6:
                    notes.append("%s subsurface %.2f -> %.2f"
                                 % (mat.name, node.inputs["Subsurface Weight"].default_value, want))
                node.inputs["Subsurface Weight"].default_value = want
            if node.type == "NORMAL_MAP":
                want = cfg["render.normal_strength"] if cfg["render.use_normal_map"] else 0.0
                if abs(node.inputs["Strength"].default_value - want) > 1e-6:
                    notes.append("%s normal strength %.2f -> %.2f"
                                 % (mat.name, node.inputs["Strength"].default_value, want))
                node.inputs["Strength"].default_value = want
    return notes


def set_subdiv(cfg):
    notes = []
    for ob in bpy.data.objects:
        for mod in getattr(ob, "modifiers", ()):
            if mod.type == "SUBSURF":
                if mod.render_levels != cfg["model.subdiv_render_levels"]:
                    notes.append("%s subdiv render_levels %d -> %d"
                                 % (ob.name, mod.render_levels, cfg["model.subdiv_render_levels"]))
                mod.render_levels = cfg["model.subdiv_render_levels"]
                mod.levels = cfg["model.subdiv_render_levels"]
    return notes


def build_rig(scene, cfg):
    """root -> adjust -> pose_fix -> the model, and why it is three empties deep.

        world = Rz(frame) . T(offset) . Rz(base_yaw) . [Ry(-pitch) Rx(roll) Rz(yaw)] .
                S(scale) . T(-pivot) . model

    `root` is the only thing the frame loop touches, so a rotation is one assignment.
    `adjust` holds the scale, the world-space offset and the quarter turn that points a
    +x nose north. `pose_fix` holds the art rotation IN MODEL SPACE, the only way `pitch`
    keeps meaning nose-up whatever base_yaw is. T(-pivot) sits innermost because the pivot
    was measured in the model's own units.
    """
    subject = bpy.data.objects.get(cfg["model.object"])
    if subject is None:
        raise SystemExit("no object named %r; scene has %s"
                         % (cfg["model.object"], [o.name for o in bpy.data.objects]))

    root = bpy.data.objects.new("jamaltron_root", None)
    adjust = bpy.data.objects.new("jamaltron_adjust", None)
    pose_fix = bpy.data.objects.new("jamaltron_pose", None)
    for e in (root, adjust, pose_fix):
        scene.collection.objects.link(e)
        e.empty_display_size = 0.2

    adjust.parent = root
    pose_fix.parent = adjust
    subject.parent = pose_fix
    for ob in (adjust, pose_fix, subject):
        ob.matrix_parent_inverse = mathutils.Matrix.Identity(4)

    s = cfg["model.scale"]
    # girth widens the WIDTH axis only. The model's length is +x and its width is y (C.2
    # measured it: the -x cross-section is the vertical caudal fin, the +x end is the
    # cephalofoil), so girth multiplies y. Canon, not a fudge: the profile has him "17 feet
    # long, described as overweight and oversized". A uniform scale makes an overweight
    # shark LONGER, the one thing the books do not say about him.
    g = cfg["model.girth"]
    # THE BOUNCE rides on the height offset in the same world-z units: both are how far off
    # the ground he is this frame. Pure root transform (no rig work, no keyframes), and the
    # shadow pass, a real Cycles render with a real sun and a catcher at z=0, picks it up
    # for free.
    east, north, up = cfg["model.offset"]
    adjust.location = (east, north, up + ac.bounce_lift(cfg))
    adjust.rotation_euler = (0.0, 0.0, math.radians(cfg["model.base_yaw"]))
    adjust.scale = (s, s * g, s)

    roll, pitch, yaw = cfg["model.rotation"]
    # Pitch is NOSE-UP positive. The nose is +x and a positive rotation about +y takes
    # +x toward -z, so nose-up is a negative y rotation. The sign lives here, once, so
    # the config comment stays true.
    pose_fix.rotation_euler = (math.radians(roll), -math.radians(pitch), math.radians(yaw))

    subject.location = tuple(-c for c in cfg["model.pivot"])
    subject.rotation_euler = (0.0, 0.0, 0.0)
    subject.scale = (1.0, 1.0, 1.0)
    return root, subject


def setup_sun(scene, cfg, d):
    """Default path calls factorio_camera's own sun so the derived direction has exactly
    one definition. Off-default builds the equivalent lamp and says so."""
    if d["sun_is_factorio_default"]:
        sun = fc.setup_sun(scene, energy=cfg["sun.energy"],
                           angle_deg=cfg["sun.angular_size"])
        return sun, "factorio_camera.setup_sun (derived 45deg / due west)"
    el = math.radians(cfg["sun.elevation"])
    az = math.radians(cfg["sun.azimuth"])
    # Direction the light TRAVELS, in (east, north, up).
    travel = mathutils.Vector((math.cos(el) * math.sin(az),
                               -math.cos(el) * math.cos(az),
                               -math.sin(el)))
    sd = bpy.data.lights.new("sun", type="SUN")
    sd.energy = cfg["sun.energy"]
    sd.angle = math.radians(cfg["sun.angular_size"])
    sun = bpy.data.objects.new("sun", sd)
    scene.collection.objects.link(sun)
    sun.rotation_euler = travel.to_track_quat("-Z", "Y").to_euler()
    sun.location = (0.0, 0.0, 20.0)
    return sun, "CUSTOM sun az=%.1f el=%.1f (OFF the game's measured direction)" % (
        cfg["sun.azimuth"], cfg["sun.elevation"])


def setup_camera(scene, cfg, canvas_tiles, d):
    if d["camera_is_factorio_default"]:
        return fc.setup_camera(scene, canvas_tiles), "factorio_camera.setup_camera (45deg ortho)"
    pitch = cfg["camera.pitch"]
    cam_data = bpy.data.cameras.new("factorio_cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = canvas_tiles
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.clip_start = 0.01
    cam_data.clip_end = 1000.0
    cam = bpy.data.objects.new("factorio_cam", cam_data)
    scene.collection.objects.link(cam)
    dist = 100.0
    p = math.radians(pitch)
    cam.location = (0.0, -dist * math.cos(p), dist * math.sin(p))
    cam.rotation_euler = (math.radians(90.0 - pitch), 0.0, 0.0)
    scene.camera = cam
    return cam, "CUSTOM camera pitch=%.2f deg (OFF the game's 45)" % pitch


# ------------------------------------------------------------------------------- main


def main():
    args = parse_args()
    with open(args["config"]) as fh:
        blob = json.load(fh)
    cfg = ac.flatten(blob["config"]) if "config" in blob else blob
    cfg = ac.resolve(ac.unflatten(cfg), env={})
    d = ac.derived(cfg)
    which = args["pass"]
    shadow = which == "shadow"
    mask = which == "mask"

    scene = bpy.context.scene
    print("FIX nla muted:", mute_nla_tracks() if cfg["model.mute_nla"] else "SKIPPED")
    subject_name = cfg["model.object"]
    rig = bpy.data.objects.get(subject_name)
    if cfg["model.rest_pose"]:
        print("FIX pose bones cleared to rest:", clear_pose(rig))
    raw = action_ranges()
    if cfg["model.drop_stale_keyframes"]:
        print("FIX stale final keyframes dropped:", drop_stale_final_keyframes())
    # AFTER the drop, because the drop is what makes the table's ranges true.
    mismatches = []
    posed = cfg["model.action"] != pose.REST
    if posed:
        dropped = action_ranges()
        mismatches = pose.verify_clips(
            {name: {"raw": raw[name], "dropped": dropped.get(name, raw[name])} for name in raw})
        for m in mismatches:
            print("WARN clip table vs the model: " + m)
    # The rig fix goes BEFORE the pose: reparenting changes how every frame of every clip
    # evaluates, so doing it after would pose the rig as bought and then move the bones'
    # parents under the result.
    if cfg["model.reparent_head"]:
        print("FIX head reparent:", reparent_head(rig))
    wave = None
    if posed:
        note, wave = apply_action(cfg, rig)
        print("FIX pose:", note)
        if wave is not None:
            # Its OWN line, with a prefix art.run_blender keeps: that filter drops an indented
            # continuation of the pose note, and this is the only record of the lags. A skip
            # is a WARN, which the harness prints however quiet the pass is.
            print(("WARN " if wave["skipped"] else "FIX ") + wave["note"])
    print("FIX removed shipped cams/lights:", strip_scene(scene))
    dead = dead_image_check()
    print("CHECK unresolvable images:", json.dumps(dead))
    # A missing image a shader actually USES is a MAGENTA shark (Blender's missing-texture
    # colour; measured 239/19/239 with TEX/ unpacked in the wrong place). A WARN, not a
    # CHECK: a CHECK only shows under -v, and the spoiled frames cache under the same hash a
    # correct layout produces (textures are not in the key), so this line, recorded and
    # replayed on every cache hit (art.py, C.23), is what tells you the cache is serving
    # magenta. The GREATWHITE refs are wired to nothing.
    for img in dead:
        if img["live"]:
            print("WARN texture %s is USED by %s but does not resolve (%s): these frames render "
                  "MAGENTA. See tools/README 'Getting the model on disk', then re-render with "
                  "--force -- a fixed layout does not change the cache key"
                  % (img["image"], ", ".join(img["wired_into"]), img["path"]))
    print("FIX materials:", tune_materials(cfg))
    print("FIX subdiv:", set_subdiv(cfg))

    scene.frame_set(cfg["model.frame"])

    # The mask rides the BODY canvas exactly (tiles, resolution, camera) because its frames
    # must crop against the same origin pixel the body's do.
    canvas = cfg["camera.shadow_canvas_tiles"] if shadow else cfg["camera.canvas_tiles"]
    # The RENDER size: the stamped size times render.supersample. art.py Lanczos-downsamples
    # these frames to *_resolution_px afterwards because Blender has no Pillow; render at the
    # stamped size instead and supersampling silently does nothing.
    res = d["shadow_render_px"] if shadow else d["body_render_px"]
    final = d["shadow_resolution_px"] if shadow else d["body_resolution_px"]
    engine = cfg["render.shadow_engine"] if shadow else cfg["render.engine"]
    samples = cfg["render.shadow_samples"] if shadow else blob.get("samples", cfg["render.samples"])

    fc.setup_render(scene, canvas, scale=cfg["camera.sprite_scale"], engine=engine,
                    samples=samples, transparent=True)
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    if engine == "CYCLES":
        scene.cycles.device = cfg["render.device"]
    try:
        scene.view_settings.view_transform = cfg["render.view_transform"]
        scene.view_settings.look = cfg["render.look"]
    except Exception as exc:
        print("WARN view transform:", exc)

    cam, cam_note = setup_camera(scene, cfg, canvas, d)
    sun, sun_note = setup_sun(scene, cfg, d)
    setup_world(scene, cfg["sun.ambient"])
    print("CAM ", cam_note)
    print("SUN ", sun_note)

    root, subject = build_rig(scene, cfg)
    for line in lay_on_floor(cfg, subject):
        print(line)
    ground_shift = None
    seated = None
    if cfg["model.ground_contact"]:
        ground_shift = ground_contact(cfg, subject)
        ignore = cfg["model.ground_ignore"]
        print("FIX ground contact: %s placed at z=%.3f (the bounce lift%s) by a %+.3f "
              "tile shift -- model.offset z %.2f cancelled"
              % ("lowest vertex not under %s" % "/".join(ignore) if ignore else "lowest vertex",
                 ac.bounce_lift(cfg) - cfg["model.ground_sink"],
                 " less a %.3f sink" % cfg["model.ground_sink"] if cfg["model.ground_sink"] else "",
                 ground_shift, cfg["model.offset"][2]))
    if ac.bedded_in(cfg):
        # Measured AFTER the shift, off the posed mesh, rather than trusted from the arithmetic:
        # the record of what took his weight and what went under the floor.
        seat, lowest = ground_seat(cfg["model.ground_ignore"])
        seated = {"seat_z": seat["z"], "seat_bone": seat["bone"],
                  "lowest_z": lowest["z"], "lowest_bone": lowest["bone"]}
        print("FIX ground seat: on %s at z=%+.3f; lowest vertex %s at z=%+.3f%s"
              % (seat["bone"], seat["z"], lowest["bone"], lowest["z"],
                 "" if lowest["z"] >= 0 else " -- %s hides it"
                 % ("the shadow catcher" if shadow else "the holdout ground")))

    if mask:
        print("FIX mask material:", apply_mask_material(cfg))

    # AFTER the mask material, which goes on every mesh and would paint over the holdout.
    if ac.bedded_in(cfg) and not shadow:
        add_ground_holdout(scene, canvas)
        print("FIX ground holdout at z=0: whatever contact put under the floor is not drawn")

    if shadow:
        fc.add_shadow_catcher(scene, canvas)
        # visible_camera, NOT is_holdout: a holdout punches its own silhouette out of the
        # alpha, and the smear is under a tile, so the shadow comes back bitten.
        for ob in bpy.data.objects:
            if ob.type == "MESH" and ob.name != "shadow_catcher":
                ob.visible_camera = False

    frames = args["frames"] or list(range(cfg["rotations.count"]))
    os.makedirs(args["out"], exist_ok=True)
    print("RENDER pass=%s engine=%s samples=%d res=%dpx -> %dpx after x%d downsample "
          "canvas=%.2f tiles (%.3f px/tile final) frames=%s"
          % (which, engine, samples, res, final, d["supersample"], canvas,
             final / canvas, frames))

    if posed or d["bounce_lift_tiles"]:
        print("POSE action=%s gain=%.2f phase_lock=%.2f frame=%d  reparent_head=%s  "
              "ground_contact=%s  bounce lift %.3f tiles (peak %.3f, %.1f of %d frames airborne, "
              "%.3f tiles up-screen, %.3f tiles of shadow east at peak)"
              % (cfg["model.action"], cfg["model.pose_gain"], cfg["model.phase_lock"],
                 cfg["model.frame"], cfg["model.reparent_head"], cfg["model.ground_contact"],
                 d["bounce_lift_tiles"], d["bounce_peak_tiles"],
                 d["bounce_airtime_frames"], d["bounce_cycle_frames"],
                 d["bounce_lift_up_screen_tiles"], d["bounce_peak_shadow_east_tiles"]))

    times = []
    box = None
    for i in frames:
        root.rotation_euler = (0.0, 0.0, fc.model_z_rotation(
            i, cfg["rotations.count"], cfg["rotations.counterclockwise"]))
        path = os.path.join(args["out"], "frame_%03d.png" % i)
        scene.render.filepath = path
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        dt = time.time() - t0
        times.append(dt)
        # Box of what was just rendered, unioned over this process's frames. Measured here,
        # not up front, because it turns with the wheel: broadside is the wide one, nose-on
        # the tall one, and the canvas has to hold both.
        seen = world_box()
        if seen is not None:
            box = seen if box is None else [[min(box[k][0], seen[k][0]),
                                            max(box[k][1], seen[k][1])] for k in range(3)]
        print("FRAME %03d %.3fs %s" % (i, dt, path))

    # HE SANK. Only a render can measure this (the box depends on pose, roll and scale
    # together), and it is invisible in the body pass, which draws no ground: the shadow
    # pass's catcher at z=0 quietly slices whatever is under it. The BOUNCE cannot fix it
    # (its floor is the lift, not the body). For a POSED body the fix is model.ground_contact,
    # which re-measures every frame; offset z is one number and a thrashing body's lowest
    # point is not. The standing shark ships with contact on too (C.27). With contact on this
    # cannot fire.
    if box is not None and box[2][0] < -0.01 and ac.bedded_in(cfg):
        # ON PURPOSE: the seat or the sink put it there and the holdout / catcher hides it.
        print("POSE bedded in: %.3f tiles of him under the floor at the deepest (ignoring %s, "
              "sink %.3f), hidden by the %s"
              % (-box[2][0], "/".join(cfg["model.ground_ignore"]) or "nothing",
                 cfg["model.ground_sink"],
                 "shadow catcher" if shadow else "holdout ground"))
    elif box is not None and box[2][0] < -0.01:
        print("WARN the %s body reaches %.3f tiles BELOW the ground plane (z=0) at this "
              "roll. The shadow catcher cuts through him there and in game he is buried to "
              "that depth. %s"
              % ("posed" if posed else "standing", -box[2][0],
                 "Set model.ground_contact = true -- a fixed model.offset z (now %.2f) cannot "
                 "follow a body whose lowest point moves every frame" % cfg["model.offset"][2]
                 if posed else
                 "The shipped standing config fixes it with model.ground_contact = true (C.27), "
                 "which also moves the leg mounts: mount_lift in shared.lua has to follow "
                 "whatever raise this needs (offset z is now %.2f)"
                 % cfg["model.offset"][2]))

    print("JAMALTRON_RESULT " + json.dumps({
        "pass": which, "engine": engine, "samples": samples, "render_px": res,
        "resolution_px": final, "supersample": d["supersample"],
        "canvas_tiles": canvas, "frames": frames, "seconds": round(sum(times), 3),
        "seconds_per_frame": round(sum(times) / max(len(times), 1), 4),
        "blender": bpy.app.version_string,
        # What the pose and the bounce actually did, so a cached frame's own report says so.
        "action": cfg["model.action"], "pose_gain": cfg["model.pose_gain"],
        "phase_lock": cfg["model.phase_lock"],
        "ground_contact": cfg["model.ground_contact"],
        "ground_shift_tiles": None if ground_shift is None else round(ground_shift, 5),
        "ground_ignore": list(cfg["model.ground_ignore"]), "ground_sink": cfg["model.ground_sink"],
        "fin_fold": cfg["model.fin_fold"], "fin_floor": cfg["model.fin_floor"],
        "spine_sag": cfg["model.spine_sag"],
        "recentre": cfg["model.recentre"], "amplitude_even": cfg["model.amplitude_even"],
        "ground_seat": seated, "ground_holdout": ac.bedded_in(cfg) and not shadow,
        "wave": ({k: wave[k] for k in ("chain", "lags", "offsets", "amps_deg") if k in wave}
                 if wave and not wave["skipped"] else None),
        "model_frame": cfg["model.frame"], "reparent_head": cfg["model.reparent_head"],
        "bounce_lift_tiles": round(d["bounce_lift_tiles"], 5),
        # WHICH clip table this was checked against, so a report three weeks old still says.
        "clip_table": pose.table_digest(), "clip_mismatches": mismatches,
        "box_tiles": box,
    }))


if __name__ == "__main__":
    main()
