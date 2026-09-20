"""Blender side of the C.10 harness: render N rotations of the shark, body or shadow.

Never invoked by hand. `render/art.py` resolves the config, decides which frames are
missing from the cache and shells out to one or more copies of this:

    Blender -b MODEL.blend --python tools/render/render_jamal.py -- \
        --config /tmp/resolved.json --pass body --frames 0,8,16 --out render-out/body/<hash>

It reads a fully RESOLVED config as JSON and never parses the TOML itself. One
resolution path, on the uv side, so the Blender side cannot disagree about what a knob
means -- and so the hash stamped on the output is the hash of what actually rendered.

WHAT IT FIXES BEFORE IT RENDERS (all three are C.2 findings, all three are silent):
  * FIVE UNMUTED NLA TRACKS. SWIM_FAST / SWIM_SLOW / SWIM_MEDIUM / BITE_02 / BITE_01
    all ship live, and BITE_01 blends COMBINE on top, so the shark renders mid-bite
    mid-swim with no warning that anything is being applied.
  * THE ORIGIN. It sits 1.0746 BU toward the nose and 0.387 BU below body centre, so
    rotating about it sweeps the tail through a 3.59 BU circle. A 64-frame sheet made
    that way has the shark orbiting the frame instead of spinning in place.
  * A STALE FINAL KEYFRAME on every clip, duplicating the cycle's first frame. It costs
    nothing on a static torso and it double-holds a frame in C.5's flop loop.

ENGINE, measured rather than assumed: the body pass defaults to EEVEE Next and the
shadow pass is Cycles and has no choice. Only Cycles honours `is_shadow_catcher`; EEVEE
Next accepts the attribute and renders the plane fully opaque. See the numbers in
tools/README.md and the config comments.
"""

# sys.path, verbatim per tools/README.md -- Blender puts THIS file's directory on
# sys.path[0], never tools/, and there is no installed `render` package to fall back on.
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

import json
import math
import os
import time

import bpy
import mathutils

from render import artconfig as ac
from render import factorio_camera as fc


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


def drop_stale_final_keyframes():
    """Remove each action's last keyframe -- it duplicates the cycle's first frame.

    C.2 measured SWIM_FAST at frames 1..21 for a 20-frame cycle: frame 21 IS frame 1.
    Playing 1..21 holds the pose for two frames at the seam. Only touches curves with
    at least three keys, so a two-key action is never gutted.
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
    model). Prove they cannot reach a render: report every unresolvable image and, for
    each, whether a shader node using it has any outgoing link at all."""
    findings = []
    for img in bpy.data.images:
        if img.source == "VIEWER":
            continue
        path = bpy.path.abspath(img.filepath) if img.filepath else ""
        if path and os.path.exists(path):
            continue
        wired = []
        for mat in bpy.data.materials:
            if not mat.use_nodes or not mat.node_tree:
                continue
            for node in mat.node_tree.nodes:
                if getattr(node, "image", None) is img:
                    links = [l for o in node.outputs for l in o.links]
                    wired.append("%s/%s:%d links" % (mat.name, node.name, len(links)))
        findings.append({"image": img.name, "path": img.filepath,
                         "users": img.users, "wired_into": wired})
    return findings


# -------------------------------------------------------------------------- scene prep


def strip_scene(scene):
    """Delete the cameras and lights the .blend ships with. C.2 hazard: the file has its
    own perspective camera at 50 mm and a 157 W area lamp, and inheriting either makes a
    render that looks fine and is not a Factorio sprite."""
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
    """Apply the two material knobs. Both exist because the model was authored for a
    beauty render and we are making a 132 px sprite."""
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
    +x nose north. `pose_fix` holds the art rotation IN MODEL SPACE, which is the only
    way `pitch` can keep meaning nose-up no matter what base_yaw is. And T(-pivot) sits
    innermost because the pivot was measured in the model's own units.
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
    adjust.location = tuple(cfg["model.offset"])
    adjust.rotation_euler = (0.0, 0.0, math.radians(cfg["model.base_yaw"]))
    adjust.scale = (s, s, s)

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

    scene = bpy.context.scene
    print("FIX nla muted:", mute_nla_tracks() if cfg["model.mute_nla"] else "SKIPPED")
    subject_name = cfg["model.object"]
    if cfg["model.rest_pose"]:
        print("FIX pose bones cleared to rest:",
              clear_pose(bpy.data.objects.get(subject_name)))
    if cfg["model.drop_stale_keyframes"]:
        print("FIX stale final keyframes dropped:", drop_stale_final_keyframes())
    print("FIX removed shipped cams/lights:", strip_scene(scene))
    print("CHECK unresolvable images:", json.dumps(dead_image_check()))
    print("FIX materials:", tune_materials(cfg))
    print("FIX subdiv:", set_subdiv(cfg))

    scene.frame_set(cfg["model.frame"])

    canvas = cfg["camera.shadow_canvas_tiles"] if shadow else cfg["camera.canvas_tiles"]
    res = d["shadow_resolution_px"] if shadow else d["body_resolution_px"]
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

    if shadow:
        fc.add_shadow_catcher(scene, canvas)
        # visible_camera, NOT is_holdout: a holdout punches its own silhouette out of the
        # alpha, and the smear is under a tile, so the shadow comes back bitten.
        for ob in bpy.data.objects:
            if ob.type == "MESH" and ob.name != "shadow_catcher":
                ob.visible_camera = False

    frames = args["frames"] or list(range(cfg["rotations.count"]))
    os.makedirs(args["out"], exist_ok=True)
    print("RENDER pass=%s engine=%s samples=%d res=%dpx canvas=%.2f tiles (%.3f px/tile) "
          "frames=%s" % (which, engine, samples, res, canvas, res / canvas, frames))

    times = []
    for i in frames:
        root.rotation_euler = (0.0, 0.0, fc.model_z_rotation(
            i, cfg["rotations.count"], cfg["rotations.counterclockwise"]))
        path = os.path.join(args["out"], "frame_%03d.png" % i)
        scene.render.filepath = path
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        dt = time.time() - t0
        times.append(dt)
        print("FRAME %03d %.3fs %s" % (i, dt, path))

    print("JAMALTRON_RESULT " + json.dumps({
        "pass": which, "engine": engine, "samples": samples, "resolution_px": res,
        "canvas_tiles": canvas, "frames": frames, "seconds": round(sum(times), 3),
        "seconds_per_frame": round(sum(times) / max(len(times), 1), 4),
        "blender": bpy.app.version_string,
    }))


if __name__ == "__main__":
    main()
