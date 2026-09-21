#!/usr/bin/env python3
"""Pick one of the five shipped clips, one frame of it, and amplify it. For C.5's flop.

    from render import pose
    baked = pose.ensure(cfg, "SWIM_FAST", [1, 3, 5], gain=2.0)   # -> {frame: .blend}
    cfg["model.blend"] = str(baked.paths[3])                     # render it like any model

WHY THIS FILE EXISTS AT ALL. The harness has no knob for WHICH ACTION. `model.rest_pose =
false` does not select one, it unmutes all five NLA tracks at once, and `model.frame` then
scrubs whatever that soup evaluates to. C.5 has to look at ONE clip at a time, amplified,
so something has to do the selecting. The two knobs that SHOULD do it -- `model.action` and
`model.pose_gain` -- are held back on purpose (see the TODO in tune.py: pose_gain is the
knob that decides whether the bought animation ships at all, and that is chotchki's call).

SO IT BAKES INSTEAD. One Blender launch opens the model, assigns the action, evaluates the
frame, amplifies each bone's basis away from rest, drops the animation entirely and saves a
COPY. What comes out is a .blend whose SAVED POSE *is* the frame you asked for, with no
animation data left to argue with it. The rest of the pipeline then treats it as any other
model: `model.rest_pose = false` (true would clear the pose we just baked), `mute_nla` moot
because there is nothing left to mute, and art.py's cache, both hashes and the provenance
stamp all keep working because `model.blend` is hashed by its CONTENT -- a different pose is
a different digest is a different cache dir, for free and without a schema change.

THE BAKE IS INDEPENDENT OF EVERY OTHER KNOB, which is what makes this cheap enough to drag
a slider against. Roll, scale, girth, pivot, offset and the camera are all applied at RENDER
time by render_jamal.build_rig, so a roll sweep re-renders and never re-bakes. Only
(model, action, frame, gain) key a baked file, so the eight frames of a loop bake ONCE and
then survive every other slider you touch.

MEASURED on this machine (M-series, Blender 4.4.3, 1.7 MiB model):
  * one launch, ten poses saved: 6.6 s total -- 2.6 s of it is Blender starting up and
    0.40 s per pose after that. So ALWAYS batch a loop into one ensure() call; ten separate
    calls would pay the 2.6 s ten times.
  * a baked file is 1.7 MiB, same as the source. Ten frames of one clip is 17 MiB.
  * bake a REST pose (no action, gain 1.0) and render it, and the body frames come back
    BYTE-IDENTICAL to the same render off the source .blend. That is the test that the save
    keeps every texture path, material and modifier intact; see tools/tests/test_pose.py
    for the pure half and the C.5 notes for the pixel half.

WHERE THE FILES GO, AND WHY NOT render-out/. A baked .blend is MODEL SOURCE -- derived, but
still the licensed mesh -- and model source does not enter the repo, gitignored or not. So
the cache lives under $TMPDIR (override with $JAMALTRON_POSE_CACHE) and prunes itself by
mtime. Deleting it costs one re-bake and nothing else.

Stdlib only on the host side, and `bpy` is imported nowhere but the Blender half, so this
module imports on BOTH sides of the Blender boundary -- same split the rest of tools/ keeps.
"""

# sys.path, verbatim per tools/README.md -- Python and Blender both put THIS file's own
# directory on sys.path[0], never tools/, and `package = false` means there is no installed
# `render` to fall back on.
import pathlib, sys  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402

from render import artconfig as ac  # noqa: E402

#: The scene's own frame rate, read off the .blend by C.2. Every duration on the page is
#: this number and a frame count, so a clip's seconds cannot drift from its frames.
FPS = 24

#: What "no pose" is called on the wire and in the UI. Selecting it renders the REST shark
#: exactly as the shipped config does -- no bake, no temp file, the standing sprite's own
#: path. The flop tuning must not be able to break the sprites that already ship.
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
#: The ranges are verified against the model on every bake (see `mismatches`), because a
#: hardcoded table about a file this tool opens anyway is a table that WILL rot silently.
CLIPS = (
    Clip("SWIM_FAST", "ArmatureAction.002", 1, 20, "SPINE_01..07 + TAIL",
         "20-frame loop, 0.83 s. THE flop candidate: amplify it and the body whips through "
         "a big screen-plane arc off a head that never moves."),
    Clip("SWIM_MEDIUM", "ArmatureAction.004", 1, 40, "SPINE_01..07 + TAIL",
         "40-frame loop, 1.67 s. The same sweep as FAST at half the speed -- reads as "
         "labouring rather than panicking."),
    Clip("SWIM_SLOW", "SWIM_SLOW.001", 1, 78, "SPINE_01..07 + TAIL",
         "78-frame loop, 3.3 s. The same sweep again at a quarter the speed. Too slow to "
         "read as distress on its own; useful as the tail end of a flop that is giving up."),
    Clip("BITE_02", "ArmatureAction.005", 1, 50, "HEAD, JAW, FIN_LEFT, FIN_RIGHT",
         "50 frames, no loop. Tail dead, head cranes SIDEWAYS. Disjoint from the swims, so "
         "it composes with one."),
    Clip("BITE_01", "ArmatureAction.007", 1, 79, "HEAD, JAW, FIN_LEFT, FIN_RIGHT",
         "79 frames but ALL the motion is in 1-29, then a 50-frame hold. Fins flare and the "
         "jaw drops -- the pectoral half of the flop."),
)

CLIPS_BY_ID = {c.id: c for c in CLIPS}

#: How hard a pose may be pushed. 1.0 is the clip as bought.
#:
#: MEASURED: the rig survives 2.6x with no mesh tearing and no candy-wrapper collapse at the
#: neck, which is more than expected from a shark rig whose HEAD is an unparented root bone.
#: The ceiling is 3.0 rather than 2.6 so the slider can find where it DOES break -- that is
#: a number C.5 wants to know -- and the page says which side of 2.6 you are on.
GAIN_MIN, GAIN_MAX, GAIN_SAFE = 1.0, 3.0, 2.6

#: Baked files kept before the oldest are pruned. 96 x 1.7 MiB is about 165 MB, which is
#: roughly every frame of all three swims plus a bite -- more than one session needs.
CACHE_MAX = 96

#: Overrides the cache directory. $TMPDIR by default; NEVER anywhere in the repo.
CACHE_ENV = "JAMALTRON_POSE_CACHE"

BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
THIS = pathlib.Path(__file__).resolve()


# ------------------------------------------------------------------------------ host side


def clip_of(clip_id: str):
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


def loop_frames(clip_id: str, stride: int = 1) -> list[int]:
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


def cache_root() -> pathlib.Path:
    """Where baked .blends live. $TMPDIR, not the repo -- a baked file is model source."""
    override = os.environ.get(CACHE_ENV)
    root = pathlib.Path(override) if override else pathlib.Path(tempfile.gettempdir())
    return root if override else root / "jamaltron-pose"


def bake_key(source_digest: str, action: str, frame: int, gain: float,
             obj: str, drop_stale: bool) -> str:
    """Everything the baked POSE depends on, and nothing else.

    Not the whole config on purpose. Roll, scale, girth, pivot, offset, camera, sun and
    samples are applied at RENDER time, so folding them in here would throw away a 0.4 s
    bake every time a slider moved by 0.01 -- and worse, would make the cache lie about
    what it is keyed by.
    """
    blob = json.dumps([source_digest, action, int(frame), round(float(gain), 6), obj,
                       bool(drop_stale)], separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def baked_path(cfg: dict, clip_id: str, frame: int, gain: float) -> pathlib.Path:
    """Where the bake of one (model, clip, frame, gain) lands. Deterministic, so a second
    session reuses the first one's files."""
    digest = ac.blend_digest(ac.blend_path(cfg))
    c = clip_of(clip_id)
    action = c.action if c else ""
    key = bake_key(digest, action, frame, gain, cfg["model.object"],
                   cfg["model.drop_stale_keyframes"])
    short = digest.split(":")[-1][:8] or "absent"
    name = "%s_f%03d_g%s_%s.blend" % (clip_id or REST, int(frame),
                                      ("%.2f" % gain).replace(".", "p"), key)
    return cache_root() / short / name


def prune(root: pathlib.Path | None = None, keep: int = CACHE_MAX) -> list[pathlib.Path]:
    """Drop the oldest baked files past `keep`. Returns what went.

    By mtime, and the bake TOUCHES a file it serves from cache, so a pose you keep coming
    back to survives while the one-off sweep you did an hour ago is what gets dropped.
    """
    root = root or cache_root()
    if not root.exists():
        return []
    files = sorted(root.rglob("*.blend"), key=lambda p: p.stat().st_mtime)
    gone = []
    for p in files[:max(0, len(files) - keep)]:
        try:
            p.unlink()
            gone.append(p)
        except OSError:
            pass
    return gone


def cache_bytes(root: pathlib.Path | None = None) -> int:
    root = root or cache_root()
    if not root.exists():
        return 0
    return sum(p.stat().st_size for p in root.rglob("*.blend"))


@dataclass
class Baked:
    """What one ensure() did. `paths` is the answer; the rest is what the page reports."""

    clip_id: str
    gain: float
    paths: dict = field(default_factory=dict)          # frame -> pathlib.Path
    baked: list = field(default_factory=list)          # frames that actually ran
    cached: list = field(default_factory=list)         # frames that were already there
    seconds: float = 0.0
    actions: dict = field(default_factory=dict)        # name -> [raw range, dropped range]
    mismatches: list = field(default_factory=list)     # CLIPS vs the model, per clip
    box_bu: dict = field(default_factory=dict)         # frame -> posed bbox dims in BU
    log: str = ""

    @property
    def ok(self) -> bool:
        return not self.paths or all(p.exists() for p in self.paths.values())


def verify_clips(actions: dict) -> list[str]:
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


def ensure(cfg: dict, clip_id: str, frames, gain: float = 1.0, *,
           blender: str | None = None, keep: int = CACHE_MAX, verbose: bool = False) -> Baked:
    """Bake every (clip, frame, gain) that is not already cached. ONE Blender launch.

    Returns a Baked whose `paths[frame]` is a .blend to hand the renderer as `model.blend`.
    REST bakes nothing and returns no paths -- the caller renders the source model with
    `model.rest_pose = true`, exactly as the shipped sprites were rendered.

    Batch the whole loop in one call. The launch is 2.6 s of the 6.6 s a ten-frame bake
    costs; ten calls would pay it ten times.
    """
    gain = clamp_gain(gain)
    c = clip_of(clip_id)
    out = Baked(clip_id=REST if c is None else c.id, gain=gain)
    if c is None:
        return out

    wanted = []
    for f in frames:
        f = clamp_frame(c.id, f)
        if f not in wanted:
            wanted.append(f)
    for f in wanted:
        out.paths[f] = baked_path(cfg, c.id, f, gain)

    todo = []
    for f in wanted:
        p = out.paths[f]
        if p.exists():
            out.cached.append(f)
            os.utime(p, None)              # LRU by mtime: a hit is a use, not a fossil
        else:
            todo.append(f)
    if not todo:
        return out

    blend = ac.blend_path(cfg)
    if not blend.exists():
        raise SystemExit(
            "model not found: %s\n  the .blend is gitignored and machine-local. Point at "
            "it with --blend /path/to/HAMMERHEAD.blend or $%s=..." % (blend, ac.BLEND_ENV))

    for f in todo:
        out.paths[f].parent.mkdir(parents=True, exist_ok=True)
    spec = {
        "object": cfg["model.object"],
        "drop_stale": bool(cfg["model.drop_stale_keyframes"]),
        "jobs": [{"action": c.action, "frame": f, "gain": gain, "out": str(out.paths[f])}
                 for f in todo],
    }
    jobs_path = out.paths[todo[0]].parent / ("jobs_%s.json" % bake_key(
        ac.blend_digest(blend), c.action, todo[0], gain, cfg["model.object"], spec["drop_stale"]))
    jobs_path.write_text(json.dumps(spec, indent=1))

    cmd = [blender or BLENDER, "-b", str(blend), "--python", str(THIS), "--",
           "--jobs", str(jobs_path)]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out.seconds = round(time.time() - t0, 2)
    out.baked = todo
    keep_lines = [ln for ln in proc.stdout.splitlines()
                  if ln.startswith(("POSE ", "FIX ", "WARN ", "Error", "Traceback"))]
    out.log = "\n".join(keep_lines if not verbose else proc.stdout.splitlines())
    if proc.returncode != 0:
        raise SystemExit("pose bake failed (%d)\n%s\n%s"
                         % (proc.returncode, proc.stdout[-4000:], proc.stderr[-3000:]))
    for line in proc.stdout.splitlines():
        if line.startswith("POSE_ACTIONS "):
            out.actions = json.loads(line.split(" ", 1)[1])
        elif line.startswith("POSE_RESULT "):
            for job in json.loads(line.split(" ", 1)[1]):
                out.box_bu[int(job["frame"])] = job.get("box_bu", [])
    out.mismatches = verify_clips(out.actions)
    missing = [f for f in todo if not out.paths[f].exists()]
    if missing:
        raise SystemExit("pose bake wrote nothing for frames %s\n%s"
                         % (missing, proc.stdout[-3000:]))
    jobs_path.unlink(missing_ok=True)
    prune(keep=keep)
    return out


# --------------------------------------------------------------------------- blender side


def _blender_main():
    """Runs INSIDE Blender: `Blender -b MODEL.blend --python pose.py -- --jobs jobs.json`.

    Reuses render_jamal wholesale for the C.2 fixes, so a baked pose sits on exactly the
    rig the shipped sprites came off. The only thing added here is selection and gain.
    """
    import bpy
    import mathutils as mu

    from render import render_jamal as rj

    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if "--jobs" not in args:
        raise SystemExit("pose.py (Blender side) needs --jobs jobs.json")
    spec = json.loads(pathlib.Path(args[args.index("--jobs") + 1]).read_text())

    print("POSE nla muted:", rj.mute_nla_tracks())
    raw = {a.name: [float(v) for v in a.frame_range] for a in bpy.data.actions}
    if spec.get("drop_stale", True):
        print("POSE stale final keyframes dropped:", rj.drop_stale_final_keyframes())
    dropped = {a.name: [float(v) for v in a.frame_range] for a in bpy.data.actions}
    print("POSE_ACTIONS " + json.dumps(
        {name: {"raw": raw[name], "dropped": dropped.get(name, raw[name])} for name in raw}))

    # Absolute image paths BEFORE the save: the textures live next to the SOURCE .blend and
    # the copy lands in $TMPDIR, so a relative `//TEX/...` would resolve to nothing and the
    # bake would quietly render an untextured shark. Once, not per job.
    try:
        bpy.ops.file.make_paths_absolute()
    except Exception as exc:                                   # pragma: no cover
        print("WARN make_paths_absolute:", exc)

    subject = bpy.data.objects.get(spec["object"])
    if subject is None:
        raise SystemExit("no object named %r" % spec["object"])
    subject.data.pose_position = "POSE"

    results = []
    for job in spec["jobs"]:
        gain = float(job.get("gain", 1.0))
        frame = int(job["frame"])
        ad = subject.animation_data or subject.animation_data_create()
        # Clear FIRST, every job. frame_set only writes the bones the action animates, so
        # without this the previous job's amplified HEAD would ride along into this one.
        for track in ad.nla_tracks:
            track.mute = True
        ad.action = None
        rj.clear_pose(subject)

        act = bpy.data.actions.get(job["action"])
        if act is None:
            raise SystemExit("no action %r; have %s"
                             % (job["action"], [a.name for a in bpy.data.actions]))
        _assign_action(subject, act)
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()

        posed = 0
        if gain != 1.0:
            # BAKE THEN AMPLIFY. Read the evaluated basis, drop the animation so nothing
            # overwrites it, then push each bone's rotation away from rest by `gain`.
            # AXIS-ANGLE, not slerp: slerp refuses a factor above 1.0 and above 1.0 is the
            # only interesting direction -- the question C.5 is asking is whether the
            # bought curve can be pushed far enough to read as thrashing.
            baked = {pb.name: pb.matrix_basis.copy() for pb in subject.pose.bones}
            ad.action = None
            for pb in subject.pose.bones:
                loc, rot, scl = baked[pb.name].decompose()
                axis, angle = rot.to_axis_angle()
                if abs(angle) > 1e-9 or loc.length > 1e-9:
                    posed += 1
                pb.matrix_basis = (mu.Matrix.Translation(loc * gain)
                                   @ mu.Quaternion(axis, angle * gain).to_matrix().to_4x4()
                                   @ mu.Matrix.Diagonal(scl).to_4x4())
            bpy.context.view_layer.update()
        else:
            # Gain 1.0 still has to lose its animation, or `model.frame` downstream would
            # scrub the pose out from under a file that claims to BE the pose.
            baked = {pb.name: pb.matrix_basis.copy() for pb in subject.pose.bones}
            ad.action = None
            for pb in subject.pose.bones:
                pb.matrix_basis = baked[pb.name]
                if pb.matrix_basis != mu.Matrix.Identity(4):
                    posed += 1
            bpy.context.view_layer.update()

        for track in list(ad.nla_tracks):
            ad.nla_tracks.remove(track)

        box = _posed_box(bpy, rj)
        bpy.ops.wm.save_as_mainfile(filepath=job["out"], copy=True,
                                    relative_remap=False, compress=False)
        results.append({"frame": frame, "gain": gain, "action": job["action"],
                        "bones_posed": posed, "box_bu": box, "out": job["out"]})
        print("POSE baked %s@%d gain %.2f -- %d bones posed, box %s BU -> %s"
              % (job["action"], frame, gain, posed,
                 " x ".join("%.3f" % v for v in box), job["out"]))

    print("POSE_RESULT " + json.dumps(results))


def _assign_action(obj, act):
    """4.4 actions are slotted; a bare `animation_data.action = act` can land with no slot
    and evaluate to NOTHING -- a silent rest pose wearing a clip's name. Bind the first
    suitable slot. Same fix model_inspect.assign_action carries, and the reason it is copied
    rather than imported is that model_inspect pulls in the whole 1100-line report harness.
    """
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


def _posed_box(bpy, rj) -> list:
    """The POSED mesh's own bounding box in Blender units, before any harness transform.

    artconfig.derived() reports the REST box from a measured constant, which is correct for
    the standing shark and WRONG the moment he thrashes -- so measure the real one here and
    let the page say both. Evaluated depsgraph, so subdiv and the armature deform count.
    """
    lo = [1e9] * 3
    hi = [-1e9] * 3
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in bpy.data.objects:
        if ob.type != "MESH" or ob.name == "shadow_catcher":
            continue
        ev = ob.evaluated_get(dg)
        mw = ev.matrix_world
        for corner in ev.bound_box:
            w = mw @ rj.mathutils.Vector(corner)
            for i in range(3):
                lo[i] = min(lo[i], w[i])
                hi[i] = max(hi[i], w[i])
    return [round(hi[i] - lo[i], 4) for i in range(3)]


if __name__ == "__main__":
    _blender_main()
