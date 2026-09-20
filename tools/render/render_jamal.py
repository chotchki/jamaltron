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

THREE PASSES, and the third one is the odd one. `body` and `shadow` differ in engine and
canvas; `mask` differs in MATERIAL. It throws the shark's textures away, puts one flat grey
shader on every mesh, and drives that shader's ALPHA from a band function of the model's
own local coordinates -- so what lands on disk is the harness and nothing else, at the same
camera and the same canvas as the body pass. That is the layer Factorio tints with the
player's colour (C.4b); see the [mask] block in jamaltron.toml for why it is the harness
and not the whole fish.
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


# --------------------------------------------------------------------------- mask pass


def _band(nt, source, centre: float, width: float, edge: float, x: int, y: int):
    """A soft window on one scalar socket: 1 inside `centre +- width/2`, 0 outside.

    Three nodes, built as |v - centre| run through a smoothstep, because the symmetric
    form needs one Map Range where two one-sided ramps need two plus a multiply. `edge` is
    the ramp width in the SOURCE's units (BU here), so a config comment can state it in
    pixels and be right.
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
    code path and no sign convention to get backwards.
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

    OBJECT coordinates, not world: the band has to stay put on his body while the rig spins
    under the camera, and Texture Coordinate -> Object is the mesh's own rest space, which
    is the space C.2 measured the bounding box in and the space `model.pivot` is stated in.
    World coordinates would sweep the straps around him once per sheet.

    DITHERED, not BLENDED, and backfaces culled. Alpha-blended EEVEE geometry writes no
    depth, so the strap on his far flank draws THROUGH his back -- a mask with a ghost strap
    on it, which is the kind of defect that survives all the way to a screenshot. Hashed
    alpha writes depth per accepted sample, so the sorting is right and the 2 px ramp
    resolves against the TAA samples the body pass already pays for.
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
    # TWO LIDS, AND THE UPPER ONE IS NOT OPTIONAL. With only a floor the plate is
    # "everything in the span above plate_z", and the tallest thing in the span is the
    # DORSAL FIN -- x -0.62..0.20 carries body up to z 0.54 and fin all the way to 1.44,
    # so an unbounded plate tints the fin base to tip and the colour picker paints his
    # fin. The band has to close: a saddle stops where the back stops.
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
    # girth widens the WIDTH axis only, leaving length and height alone. The model's
    # length is +x and its width is y (C.2 measured it: the -x cross-section is the
    # vertical caudal fin, the +x end is the cephalofoil), so girth multiplies y.
    # Canon, not a fudge: the profile has him "17 feet long, described as overweight
    # and oversized". A uniform scale makes an overweight shark LONGER, which is the
    # one thing the books do not say about him.
    g = cfg["model.girth"]
    adjust.location = tuple(cfg["model.offset"])
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

    # The mask rides the BODY canvas exactly -- same tiles, same resolution, same camera --
    # because its frames have to crop against the same origin pixel the body's do.
    canvas = cfg["camera.shadow_canvas_tiles"] if shadow else cfg["camera.canvas_tiles"]
    # The RENDER size, which is the stamped size times render.supersample. art.py Lanczos
    # -downsamples these frames to *_resolution_px afterwards, because Blender has no
    # Pillow; render at the stamped size instead and supersampling silently does nothing.
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

    if mask:
        print("FIX mask material:", apply_mask_material(cfg))

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
        "pass": which, "engine": engine, "samples": samples, "render_px": res,
        "resolution_px": final, "supersample": d["supersample"],
        "canvas_tiles": canvas, "frames": frames, "seconds": round(sum(times), 3),
        "seconds_per_frame": round(sum(times) / max(len(times), 1), 4),
        "blender": bpy.app.version_string,
    }))


if __name__ == "__main__":
    main()
