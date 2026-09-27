"""Headless Blender triage for the bought hammerhead model.

Dumps one JSON report plus a human summary so C.3-C.7 plan against real numbers, not
impressions. Nothing here writes into the repo.

Usage, from the repo root (`Blender` is /Applications/Blender.app/Contents/MacOS/Blender):
    Blender -b FILE.blend --python tools/render/model_inspect.py -- --out report.json
    Blender -b --factory-startup --python tools/render/model_inspect.py -- --import FILE.fbx --out report.json

Point --out somewhere OUTSIDE the repo. The model lives under the gitignored assets/source/
and the licence turns on it staying there; a report is derived from it, so treat it the same.

The --import form starts from an empty scene and imports fbx/dae/obj/gltf -- C.2's
.blend / .fbx / .dae comparison is the same script on three inputs.

NAMED model_inspect on purpose: `render/inspect.py` SHADOWS the stdlib's `inspect` for every
sibling in this directory, because Python and Blender both put the running script's
directory on sys.path[0]. `dataclasses` imports `inspect`, so the shadow turned
`from dataclasses import dataclass` in a sibling into `import bpy` and killed
spritesheet.py and blender_check.py outside Blender. Do not rename it back, and give no
file under render/ a stdlib module's name -- test_art_harness.py fails the suite if you do.

What it measures, and why each number matters downstream:
  * bbox dimensions + origin placement -> Factorio renders at fixed camera rotations,
    so an origin at the tail makes the shark swing instead of spin (C.3/C.4).
  * forward / up axis, inferred from geometry rather than trusted -> the caudal fin is
    vertical and a hammerhead's cephalofoil is horizontal, which pins both axes and
    which END is the nose.
  * every action with its frame range -> C.5 needs the swim cycle specifically.
  * n-gons, non-manifold edges, negative scale, UV count -> the things that bite a
    render pipeline silently.
"""

import json
import math
import os
import struct
import sys
import traceback

import bpy
import bmesh
from mathutils import Matrix, Vector

AXES = ("x", "y", "z")


# --------------------------------------------------------------------------- args


def parse_args():
    argv = sys.argv
    args = argv[argv.index("--") + 1 :] if "--" in argv else []
    out = {"out": None, "import": None, "label": None, "sample_frames": 12}
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--out", "--import", "--label"):
            out[a[2:]] = args[i + 1]
            i += 2
        elif a == "--sample-frames":
            out["sample_frames"] = int(args[i + 1])
            i += 2
        else:
            i += 1
    return out


# ------------------------------------------------------------------ image headers


def image_header(path):
    """Read dimensions straight off disk. Blender reports 0x0 for an image it has not
    loaded, and loading a 4k texture headless just for its size is waste, so parse the
    container."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(64)
        size = os.path.getsize(path)
    except OSError as exc:
        return {"error": str(exc)}
    info = {"bytes_on_disk": size}
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", head[16:24])
        ctype = {0: "gray", 2: "RGB", 3: "indexed", 4: "gray+A", 6: "RGBA"}.get(head[25], head[25])
        info.update(format="PNG", width=w, height=h, bit_depth=head[24], color_type=ctype)
    elif head[:2] == b"\xff\xd8":
        info.update(format="JPEG")
        with open(path, "rb") as fh:
            fh.read(2)
            while True:
                b = fh.read(1)
                if not b:
                    break
                if b != b"\xff":
                    continue
                marker = fh.read(1)
                while marker == b"\xff":
                    marker = fh.read(1)
                if marker[0] in range(0xC0, 0xD0) and marker[0] not in (0xC4, 0xC8, 0xCC):
                    fh.read(3)
                    h, w = struct.unpack(">HH", fh.read(4))
                    info.update(width=w, height=h)
                    break
                ln = struct.unpack(">H", fh.read(2))[0]
                fh.seek(ln - 2, 1)
    elif head[:4] in (b"II*\x00", b"MM\x00*"):
        info.update(format="TIFF")
    else:
        info.update(format="unknown")
    return info


# ------------------------------------------------------------------------- import


def do_import(path):
    # Purge the factory-startup cube/camera/light AND their orphaned datablocks. Otherwise
    # the counts report a default grey "Material" and a stray mesh from Blender, not the
    # file under test, which wrecks a format comparison.
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras, bpy.data.lights,
                 bpy.data.images, bpy.data.armatures, bpy.data.actions):
        for db in list(coll):
            if db.users == 0 or (db.users == 1 and db.use_fake_user):
                try:
                    coll.remove(db, do_unlink=True)
                except Exception:
                    pass
    ext = os.path.splitext(path)[1].lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".dae":
        bpy.ops.wm.collada_import(filepath=path)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    else:
        raise SystemExit("unhandled import extension: " + ext)


# -------------------------------------------------------------------- mesh probes


def mesh_topology(obj):
    """Raw (pre-modifier) topology, counted on a bmesh copy so nothing is mutated."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    tris = quads = ngons = 0
    ngon_max = 0
    for f in bm.faces:
        n = len(f.verts)
        if n == 3:
            tris += 1
        elif n == 4:
            quads += 1
        else:
            ngons += 1
            ngon_max = max(ngon_max, n)
    boundary = wire = nonman_edges = 0
    for e in bm.edges:
        nf = len(e.link_faces)
        if nf == 0:
            wire += 1
        elif nf == 1:
            boundary += 1
        elif nf > 2:
            nonman_edges += 1
    loose_verts = sum(1 for v in bm.verts if not v.link_edges)
    nonman_verts = sum(1 for v in bm.verts if not v.is_manifold)
    nonman_coords = [[round(c, 5) for c in v.co] for v in bm.verts if not v.is_manifold][:20]
    tri_count = sum(len(f.verts) - 2 for f in bm.faces)
    bm.free()
    return {
        "verts": len(me.vertices),
        "edges": len(me.edges),
        "faces": len(me.polygons),
        "tris_if_triangulated": tri_count,
        "tri_faces": tris,
        "quad_faces": quads,
        "ngon_faces": ngons,
        "largest_ngon_verts": ngon_max,
        "boundary_edges": boundary,
        "wire_edges": wire,
        "nonmanifold_edges_3plus_faces": nonman_edges,
        "nonmanifold_verts": nonman_verts,
        "nonmanifold_vert_coords_local": nonman_coords,
        "loose_verts": loose_verts,
        "watertight": boundary == 0 and nonman_edges == 0 and nonman_verts == 0,
        "uv_layers": [l.name for l in me.uv_layers],
        "color_attributes": [c.name for c in getattr(me, "color_attributes", [])],
        "material_slots": [m.name if m else None for m in me.materials],
        "has_custom_split_normals": me.has_custom_normals,
        "shade_smooth_faces": sum(1 for p in me.polygons if p.use_smooth),
        "shape_keys": [k.name for k in me.shape_keys.key_blocks] if me.shape_keys else [],
        "vertex_groups": [g.name for g in obj.vertex_groups],
    }


def bbox_world(obj, depsgraph=None):
    """World-space AABB. Uses the evaluated object when a depsgraph is handed in, so
    modifiers and armature deformation are included."""
    src = obj.evaluated_get(depsgraph) if depsgraph else obj
    mat = src.matrix_world
    pts = [mat @ Vector(c) for c in src.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def axis_report(obj):
    """Infer forward/up from the geometry, not the exporter's axis convention. The caudal
    fin is a tall vertical blade and the cephalofoil a wide horizontal bar, so the TAIL
    slice is tall-and-narrow and the HEAD slice wide-and-short -- which names the up axis,
    the width axis and which end is the nose."""
    me = obj.data
    mat = obj.matrix_world
    co = [mat @ v.co for v in me.vertices]
    if not co:
        return {"error": "no vertices"}
    lo = Vector((min(c.x for c in co), min(c.y for c in co), min(c.z for c in co)))
    hi = Vector((max(c.x for c in co), max(c.y for c in co), max(c.z for c in co)))
    dims = hi - lo
    order = sorted(range(3), key=lambda i: dims[i], reverse=True)
    long_axis = order[0]
    others = [i for i in range(3) if i != long_axis]

    def slice_extents(pred):
        sub = [c for c in co if pred(c)]
        if not sub:
            return None
        out = {}
        for i in others:
            vals = [c[i] for c in sub]
            out[AXES[i]] = max(vals) - min(vals)
        out["_n"] = len(sub)
        return out

    span = dims[long_axis]
    lo_end = slice_extents(lambda c: c[long_axis] <= lo[long_axis] + 0.08 * span)
    hi_end = slice_extents(lambda c: c[long_axis] >= hi[long_axis] - 0.08 * span)
    mid = slice_extents(lambda c: abs(c[long_axis] - (lo[long_axis] + hi[long_axis]) / 2) <= 0.08 * span)

    def taller_axis(ext):
        if not ext:
            return None
        a, b = others
        return AXES[a] if ext[AXES[a]] > ext[AXES[b]] else AXES[b]

    # The end whose cross-section is TALLER than it is wide by the biggest margin is the
    # caudal fin. Ratio, not absolute size, because the head is bigger overall.
    def ratio(ext):
        if not ext:
            return 0.0
        a, b = others
        va, vb = ext[AXES[a]], ext[AXES[b]]
        hi_, lo_ = max(va, vb), min(va, vb)
        return hi_ / lo_ if lo_ > 1e-9 else float("inf")

    tail_end, head_end = ("min", "max") if ratio(lo_end) > ratio(hi_end) else ("max", "min")
    tail_ext = lo_end if tail_end == "min" else hi_end
    up_axis = taller_axis(tail_ext)
    width_axis = [AXES[i] for i in others if AXES[i] != up_axis][0] if up_axis else None

    # Dorsal fin points away from the body centre further than the belly does.
    up_sign = None
    if up_axis:
        ui = AXES.index(up_axis)
        centre = sum(c[ui] for c in co) / len(co)
        up_sign = 1 if (hi[ui] - centre) >= (centre - lo[ui]) else -1

    forward = None
    if head_end == "max":
        forward = "+" + AXES[long_axis]
    elif head_end == "min":
        forward = "-" + AXES[long_axis]

    return {
        "world_bbox_min": list(lo),
        "world_bbox_max": list(hi),
        "world_dimensions": list(dims),
        "axis_by_size_desc": [AXES[i] for i in order],
        "length_axis": AXES[long_axis],
        "inferred_forward_nose": forward,
        "inferred_up": ("+" if up_sign == 1 else "-") + up_axis if up_axis else None,
        "inferred_width_axis": width_axis,
        "tail_end_of_length_axis": tail_end,
        "cross_sections": {
            "min_end_8pct": lo_end,
            "mid_8pct": mid,
            "max_end_8pct": hi_end,
        },
        "note": "tail slice is tall+narrow (caudal fin), head slice is wide+short (cephalofoil)",
    }


def origin_report(obj):
    me = obj.data
    if not me.vertices:
        return {"error": "no vertices"}
    lo = Vector((min(v.co.x for v in me.vertices), min(v.co.y for v in me.vertices), min(v.co.z for v in me.vertices)))
    hi = Vector((max(v.co.x for v in me.vertices), max(v.co.y for v in me.vertices), max(v.co.z for v in me.vertices)))
    dims = hi - lo
    frac = []
    for i in range(3):
        frac.append(None if dims[i] < 1e-9 else float((0.0 - lo[i]) / dims[i]))
    centroid = Vector((0, 0, 0))
    for v in me.vertices:
        centroid += v.co
    centroid /= len(me.vertices)
    return {
        "object_location_world": list(obj.location),
        "local_bbox_min": list(lo),
        "local_bbox_max": list(hi),
        "local_dimensions": list(dims),
        "origin_normalised_in_bbox": frac,
        "origin_offset_from_bbox_centre_local": list(-(lo + hi) / 2),
        "vertex_centroid_local": list(centroid),
        "comment": "0.5 on an axis means the origin is centred on it; 0 or 1 means it sits on a face of the bbox",
    }


def modifier_detail(m):
    d = {"name": m.name, "type": m.type, "show_viewport": m.show_viewport, "show_render": m.show_render}
    if m.type == "SUBSURF":
        d.update(subdivision_type=m.subdivision_type, viewport_levels=m.levels,
                 render_levels=m.render_levels, use_limit_surface=m.use_limit_surface)
    if m.type == "ARMATURE":
        d.update(armature=m.object.name if m.object else None, use_vertex_groups=m.use_vertex_groups,
                 use_bone_envelopes=m.use_bone_envelopes)
    if m.type == "MIRROR":
        d.update(use_axis=list(m.use_axis))
    return d


def evaluated_report(obj, arm_objs):
    """What the RENDERER sees. The raw mesh is 2.6k quads, but a live Subdivision modifier
    makes the rendered surface a different object, and bound_box already reflects the
    posed+subdivided result (hence raw vertex bbox and obj.dimensions disagree). Both are
    wanted: rest dims size the sprite, posed dims size the render frame."""
    out = {}
    dg = bpy.context.evaluated_depsgraph_get()

    def counts():
        dg2 = bpy.context.evaluated_depsgraph_get()
        dg2.update()
        ev = obj.evaluated_get(dg2)
        me = ev.to_mesh()
        try:
            lo, hi = bbox_world(obj, dg2)
            return {"verts": len(me.vertices), "faces": len(me.polygons),
                    "tris": sum(len(p.vertices) - 2 for p in me.polygons),
                    "bbox_dims": [round(c, 5) for c in (hi - lo)],
                    "bbox_min": [round(c, 5) for c in lo], "bbox_max": [round(c, 5) for c in hi]}
        finally:
            ev.to_mesh_clear()

    out["as_opened_viewport_eval"] = counts()

    subsurfs = [m for m in obj.modifiers if m.type == "SUBSURF"]
    saved = [(m, m.levels) for m in subsurfs]
    for m, _ in saved:
        m.levels = m.render_levels
    out["render_level_eval"] = counts()
    for m, lv in saved:
        m.levels = lv

    prev = [(a, a.data.pose_position) for a in arm_objs]
    for a, _ in prev:
        a.data.pose_position = "REST"
    out["rest_pose_eval"] = counts()
    for a, p in prev:
        a.data.pose_position = p
    dg.update()
    return out


def transform_report(obj):
    loc, rot, scale = obj.matrix_world.decompose()
    basis_is_identity = all(
        abs(obj.matrix_basis[r][c] - (1.0 if r == c else 0.0)) < 1e-6 for r in range(4) for c in range(4)
    )
    det = obj.matrix_world.to_3x3().determinant()
    return {
        "location": list(obj.location),
        "rotation_mode": obj.rotation_mode,
        "rotation_euler_deg": [math.degrees(a) for a in obj.rotation_euler],
        "rotation_quaternion": list(obj.rotation_quaternion),
        "scale": list(obj.scale),
        "delta_location": list(obj.delta_location),
        "delta_rotation_euler_deg": [math.degrees(a) for a in obj.delta_rotation_euler],
        "delta_scale": list(obj.delta_scale),
        "world_matrix_determinant": det,
        "mirrored_negative_scale": det < 0,
        "uniform_scale": max(obj.scale) - min(obj.scale) < 1e-6,
        "matrix_basis_is_identity": basis_is_identity,
        "transforms_applied": basis_is_identity,
        "parent": obj.parent.name if obj.parent else None,
        "parent_type": obj.parent_type if obj.parent else None,
        "modifiers": [modifier_detail(m) for m in obj.modifiers],
        "constraints": [{"name": c.name, "type": c.type} for c in obj.constraints],
    }


# ---------------------------------------------------------------------- materials


def walk_material(mat):
    out = {
        "name": mat.name,
        "use_nodes": mat.use_nodes,
        "blend_method": getattr(mat, "blend_method", None),
        "backface_culling": getattr(mat, "use_backface_culling", None),
        "users": mat.users,
        "shaders": [],
        "texture_bindings": [],
        "unconnected_image_nodes": [],
        "node_types": {},
    }
    if not mat.use_nodes or not mat.node_tree:
        return out
    nodes = mat.node_tree.nodes
    for n in nodes:
        out["node_types"][n.bl_idname] = out["node_types"].get(n.bl_idname, 0) + 1
    for n in nodes:
        if n.type in ("BSDF_PRINCIPLED", "BSDF_DIFFUSE", "BSDF_GLOSSY", "EMISSION", "BSDF_GLASS", "SUBSURFACE_SCATTERING"):
            entry = {"node": n.name, "type": n.type, "constant_inputs": {}}
            for sock in n.inputs:
                if sock.is_linked:
                    continue
                try:
                    val = sock.default_value
                    entry["constant_inputs"][sock.name] = (
                        list(val) if hasattr(val, "__len__") else float(val)
                    )
                except (AttributeError, TypeError):
                    pass
            out["shaders"].append(entry)

    def upstream_images(sock, depth=0, via=None):
        """Chase a shader input back through Normal Map / Bump / Mix / Separate nodes to
        the image that feeds it. The question is whether it is wired up, not topology."""
        via = via or []
        found = []
        if not sock.is_linked or depth > 8:
            return found
        for link in sock.links:
            n = link.from_node
            if n.type == "TEX_IMAGE":
                found.append({"image_node": n.name, "image": n.image.name if n.image else None,
                              "via": list(via), "interpolation": n.interpolation,
                              "extension": n.extension,
                              "colorspace": n.image.colorspace_settings.name if n.image else None})
            else:
                for inp in n.inputs:
                    found += upstream_images(inp, depth + 1, via + [n.type])
        return found

    for sh in out["shaders"]:
        node = nodes.get(sh["node"])
        for sock in node.inputs:
            imgs = upstream_images(sock)
            for im in imgs:
                out["texture_bindings"].append({"shader_input": sock.name, **im})
    out["links"] = [
        {"from": f"{l.from_node.name}.{l.from_socket.name}", "to": f"{l.to_node.name}.{l.to_socket.name}"}
        for l in mat.node_tree.links
    ]
    out["node_settings"] = {}
    for n in nodes:
        if n.type == "MIX":
            out["node_settings"][n.name] = {
                "type": n.type, "data_type": getattr(n, "data_type", None),
                "blend_type": getattr(n, "blend_type", None),
                "clamp_factor": getattr(n, "clamp_factor", None),
                "unlinked_inputs": {
                    i.name + f"[{k}]": (list(i.default_value) if hasattr(i.default_value, "__len__") else i.default_value)
                    for k, i in enumerate(n.inputs) if not i.is_linked and hasattr(i, "default_value")
                },
            }
        if n.type == "NORMAL_MAP":
            out["node_settings"][n.name] = {"type": n.type, "space": n.space, "uv_map": n.uv_map,
                                            "strength": n.inputs["Strength"].default_value}
    bound = {b["image_node"] for b in out["texture_bindings"]}
    for n in nodes:
        if n.type == "TEX_IMAGE" and n.name not in bound:
            out["unconnected_image_nodes"].append(
                {"node": n.name, "image": n.image.name if n.image else None,
                 "outputs_linked": any(o.is_linked for o in n.outputs)}
            )
    return out


def image_report(img):
    raw = img.filepath
    try:
        abspath = bpy.path.abspath(img.filepath, library=img.library)
    except Exception:
        abspath = raw
    exists = os.path.isfile(abspath) if abspath else False
    rec = {
        "name": img.name,
        "source": img.source,
        "filepath_raw": raw,
        "filepath_resolved": abspath,
        "exists_on_disk": exists,
        "packed_into_blend": bool(img.packed_file) or bool(img.packed_files),
        "packed_file_size": img.packed_file.size if img.packed_file else None,
        "blender_reported_size": list(img.size),
        "has_data_loaded": img.has_data,
        "file_format": img.file_format,
        "depth_bits": img.depth,
        "channels": img.channels,
        "colorspace": img.colorspace_settings.name,
        "alpha_mode": img.alpha_mode,
        "users": img.users,
    }
    if exists:
        rec["disk_header"] = image_header(abspath)
    return rec


# --------------------------------------------------------------------------- rigs


def armature_report(arm_obj, mesh_objs):
    arm = arm_obj.data
    bones = arm.bones
    roots = [b.name for b in bones if b.parent is None]

    def depth(b):
        d = 0
        while b.parent:
            b = b.parent
            d += 1
        return d

    deform = [b.name for b in bones if b.use_deform]
    skinned = []
    for mo in mesh_objs:
        mods = [m for m in mo.modifiers if m.type == "ARMATURE" and m.object == arm_obj]
        vg = {g.name for g in mo.vertex_groups}
        bn = {b.name for b in bones}
        overlap = sorted(vg & bn)
        weighted = 0
        if overlap:
            idx = {g.index for g in mo.vertex_groups if g.name in overlap}
            for v in mo.data.vertices:
                if any(g.group in idx and g.weight > 0 for g in v.groups):
                    weighted += 1
        skinned.append({
            "mesh": mo.name,
            "armature_modifier": bool(mods),
            "parented_to_armature": mo.parent == arm_obj,
            "vertex_groups": len(vg),
            "vertex_groups_matching_bones": len(overlap),
            "vertex_groups_without_bone": sorted(vg - bn),
            "verts_with_weight": weighted,
            "verts_total": len(mo.data.vertices),
            "fully_skinned": weighted == len(mo.data.vertices) and bool(mods),
        })
    posed = []
    for pb in arm_obj.pose.bones:
        m = pb.matrix_basis
        dev = max(abs(m[r][c] - (1.0 if r == c else 0.0)) for r in range(4) for c in range(3))
        if dev > 1e-5:
            posed.append({"bone": pb.name, "deviation": dev})
    return {
        "armature_object": arm_obj.name,
        "armature_data": arm.name,
        "bone_count": len(bones),
        "deform_bone_count": len(deform),
        "root_bones": roots,
        "max_hierarchy_depth": max((depth(b) for b in bones), default=0),
        "bone_names": [b.name for b in bones],
        "bone_rest_layout": [
            {"name": b.name, "parent": b.parent.name if b.parent else None,
             "head_local": [round(c, 5) for c in b.head_local],
             "tail_local": [round(c, 5) for c in b.tail_local],
             "length": round(b.length, 5), "use_deform": b.use_deform,
             "children": [c.name for c in b.children]}
            for b in bones
        ],
        "bones_with_nonrest_pose_at_current_frame": posed[:40],
        "bones_posed_count": len(posed),
        "in_rest_position_flag": arm.pose_position,
        "skinning": skinned,
        "object_transform": transform_report(arm_obj),
    }


# ---------------------------------------------------------------------- animation


def assign_action(obj, act):
    """4.4 actions are slotted; a bare `animation_data.action = act` can land with no slot
    and then evaluates to nothing. Bind the first suitable slot when one exists."""
    if obj.animation_data is None:
        obj.animation_data_create()
    ad = obj.animation_data
    ad.action = act
    try:
        if getattr(ad, "action_slot", None) is None:
            slots = list(getattr(ad, "action_suitable_slots", []) or [])
            if slots:
                ad.action_slot = slots[0]
    except Exception:
        pass
    return ad


def action_report(act):
    try:
        fr = list(act.frame_range)
    except Exception:
        fr = None
    curves = []
    try:
        curves = list(act.fcurves)
    except Exception:
        pass
    if not curves:  # slotted layout, 4.4+
        for layer in getattr(act, "layers", []):
            for strip in getattr(layer, "strips", []):
                for cb in getattr(strip, "channelbags", []):
                    curves += list(cb.fcurves)
    paths = {}
    bones = set()
    key_frames = set()
    for fc in curves:
        dp = fc.data_path
        paths[dp.split('"')[-1] if '"' in dp else dp] = paths.get(dp.split('"')[-1] if '"' in dp else dp, 0) + 1
        if dp.startswith("pose.bones["):
            bones.add(dp.split('"')[1])
        for kp in fc.keyframe_points:
            key_frames.add(round(kp.co[0], 3))
    ks = sorted(key_frames)
    return {
        "name": act.name,
        "id_root": act.id_root,
        "frame_range": fr,
        "frame_span": (fr[1] - fr[0]) if fr else None,
        "fcurve_count": len(curves),
        "animated_bone_count": len(bones),
        "animated_bones_sample": sorted(bones)[:12],
        "keyframe_count_unique_times": len(ks),
        "first_keyframes": ks[:8],
        "last_keyframes": ks[-8:],
        "use_frame_range_manual": getattr(act, "use_frame_range", None),
        "use_cyclic": getattr(act, "use_cyclic", None),
        "users": act.users,
        "is_fake_user": act.use_fake_user,
    }


def sample_action(arm_obj, act, mesh_objs, n_samples=12):
    """Measure what an action does: tail-tip travel per frame (a swim cycle sweeps
    laterally, a flop does not), whether first and last pose match (clean loop for C.5)
    and the animated bbox (render framing).

    MUTES the NLA stack first. The file ships with all five tracks unmuted, so an unmuted
    sample is the stack plus the active action, not the clip -- every clip then reports
    the same tail sweep."""
    fr = act.frame_range
    f0, f1 = int(round(fr[0])), int(round(fr[1]))
    scene = bpy.context.scene
    prev_action = None
    muted = []
    if arm_obj.animation_data:
        prev_action = arm_obj.animation_data.action
        for t in arm_obj.animation_data.nla_tracks:
            muted.append((t, t.mute))
            t.mute = True
    assign_action(arm_obj, act)
    arm_obj.data.pose_position = "POSE"

    # tail-tip bone: rest head furthest along the length axis away from the head end
    bones = arm_obj.data.bones
    if not bones:
        return {"error": "no bones"}
    mat = arm_obj.matrix_world
    heads = {b.name: mat @ b.head_local for b in bones}
    xs = [v.x for v in heads.values()]
    ys = [v.y for v in heads.values()]
    zs = [v.z for v in heads.values()]
    spans = [max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs)]
    la = spans.index(max(spans))
    tail_bone = min(heads, key=lambda k: heads[k][la])
    nose_bone = max(heads, key=lambda k: heads[k][la])

    if f1 - f0 <= 260:  # every frame: periodicity and the loop seam need real resolution
        frames = list(range(f0, f1 + 1))
    else:
        frames = sorted(set([f0 + round(i * (f1 - f0) / max(1, n_samples - 1)) for i in range(n_samples)] + [f0, f1]))
    samples = []
    poses = {}
    dims_hint = max(spans) if spans else 1.0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for f in frames:
        scene.frame_set(f)
        depsgraph.update()
        arm_eval = arm_obj.evaluated_get(depsgraph)
        tb = arm_eval.pose.bones.get(tail_bone)
        nb = arm_eval.pose.bones.get(nose_bone)
        rec = {"frame": f}
        if tb:
            rec["tail_head_world"] = [round(c, 5) for c in (arm_eval.matrix_world @ tb.head)]
        if nb:
            rec["nose_head_world"] = [round(c, 5) for c in (arm_eval.matrix_world @ nb.head)]
        if mesh_objs:
            lo, hi = bbox_world(mesh_objs[0], depsgraph)
            rec["mesh0_bbox_dims"] = [round(c, 5) for c in (hi - lo)]
            rec["mesh0_bbox_min"] = [round(c, 5) for c in lo]
        poses[f] = [
            tuple(round(x, 6) for row in pb.matrix_basis for x in row)
            for pb in sorted(arm_eval.pose.bones, key=lambda b: b.name)
        ]
        samples.append(rec)

    def dev(a, b):
        if a not in poses or b not in poses or len(poses[a]) != len(poses[b]):
            return None
        return max((max(abs(x - y) for x, y in zip(m0, m1)) for m0, m1 in zip(poses[a], poses[b])), default=0.0)

    # Two loop conventions in the wild: last frame IS the repeat of the first (f1 matches
    # f0) or the frame BEFORE the wrap (f1+1 would match f0, and the f1-1..f0 gap is one
    # step). Test both.
    loop_dev = dev(f0, f1)
    loop_dev_minus1 = dev(f0, f1 - 1)

    def travel(key, axis):
        vals = [s[key][axis] for s in samples if key in s]
        return (max(vals) - min(vals)) if vals else None

    # Periodicity: count sign changes in the tail's lateral velocity. A swim cycle is a
    # sinusoidal sweep, so 2 reversals per period; a bite or a lunge is not periodic.
    lat = None
    reversals = None
    lateral_axis = [i for i in range(3) if i != la]
    series = {}
    for ax in lateral_axis:
        vals = [s["tail_head_world"][ax] for s in samples if "tail_head_world" in s]
        series[AXES[ax]] = [round(v, 5) for v in vals]
    if series:
        lat = max(series, key=lambda k: (max(series[k]) - min(series[k])) if series[k] else 0)
        v = series[lat]
        d = [b - a for a, b in zip(v, v[1:])]
        reversals = sum(1 for a, b in zip(d, d[1:]) if a * b < 0)

    # True cycle length by autocorrelation on the tail sweep. Two guards: a clip that never
    # moves the tail (the BITE clips) has a constant series that correlates at EVERY
    # period, and a baked strip drifts a few tenths of a percent through interpolation, so
    # the tolerance is relative to the sweep amplitude, not an absolute epsilon.
    period = period_resid = None
    if lat and series.get(lat) and len(series[lat]) > 6:
        ser = series[lat]
        amp = max(ser) - min(ser)
        if amp > 0.01 * max(1e-6, dims_hint):
            tol = 0.01 * amp
            for drop in (1, 0):  # drop the last frame first: on a cyclic action it is the
                s2 = ser[: len(ser) - drop] if drop else ser  # stale duplicate/neutral key
                n2 = len(s2)
                for pp in range(3, n2 // 2 + 1):
                    resid = max((abs(a - b) for a, b in zip(s2[: n2 - pp], s2[pp:])), default=None)
                    if resid is not None and resid < tol:
                        period, period_resid = pp, resid
                        break
                if period:
                    break

    out = {
        "action": act.name,
        "frame_range": [f0, f1],
        "frames_sampled": len(samples),
        "detected_loop_period_frames": period,
        "detected_loop_period_residual": period_resid,
        "loop_frames_to_render": [f0, f0 + period - 1] if period else None,
        "last_frame_is_outside_cycle": (period is not None and (f1 - f0) != period),
        "tail_bone_sampled": tail_bone,
        "nose_bone_sampled": nose_bone,
        "length_axis_index": la,
        "tail_travel_per_axis": [travel("tail_head_world", i) for i in range(3)],
        "nose_travel_per_axis": [travel("nose_head_world", i) for i in range(3)],
        "dominant_tail_sweep_axis": lat,
        "tail_sweep_series": series.get(lat) if lat else None,
        "tail_velocity_sign_reversals": reversals,
        "pose_deviation_first_vs_last_frame": loop_dev,
        "pose_deviation_first_vs_last_minus_one": loop_dev_minus1,
        "loops_cleanly": (loop_dev is not None and loop_dev < 1e-4)
        or (loop_dev_minus1 is not None and loop_dev_minus1 < 1e-4),
        "samples": samples,
    }
    if prev_action is not None:
        assign_action(arm_obj, prev_action)
    for t, m in muted:
        t.mute = m
    return out


def nla_report(obj):
    ad = obj.animation_data
    if not ad:
        return None
    tracks = []
    for t in ad.nla_tracks:
        tracks.append({
            "track": t.name,
            "mute": t.mute,
            "strips": [{
                "name": s.name,
                "action": s.action.name if s.action else None,
                "strip_frames": [s.frame_start, s.frame_end],
                "action_frames": [s.action_frame_start, s.action_frame_end],
                "repeat": s.repeat,
                "blend_type": s.blend_type,
                "extrapolation": s.extrapolation,
                # The authoritative cycle length when repeat > 1: the strip plays the action
                # span this many times and maps strip frame (start + span) back to
                # action_frame_start, so the action's LAST frame never plays and rendering
                # it puts a pop in the loop.
                "frames_per_cycle": (s.frame_end - s.frame_start) / s.repeat if s.repeat else None,
                "action_span": s.action_frame_end - s.action_frame_start,
                "render_frames_for_one_cycle": [s.action_frame_start, s.action_frame_end - 1]
                if s.repeat and s.repeat > 1 else None,
            } for s in t.strips],
        })
    return {
        "active_action": ad.action.name if ad.action else None,
        "action_slot": getattr(getattr(ad, "action_slot", None), "name_display", None),
        "nla_tracks": tracks,
        "drivers": len(ad.drivers),
    }


# -------------------------------------------------------------------------- build


def build_report(args):
    scene = bpy.context.scene
    rep = {
        "input": {
            "blend_filepath": bpy.data.filepath,
            "imported_from": args["import"],
            "label": args["label"] or (args["import"] or bpy.data.filepath),
            "blender_version": bpy.app.version_string,
        },
        "scene": {
            "name": scene.name,
            "fps": scene.render.fps,
            "fps_base": scene.render.fps_base,
            "effective_fps": scene.render.fps / scene.render.fps_base,
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
            "frame_current": scene.frame_current,
            "render_engine": scene.render.engine,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage],
            "unit_system": scene.unit_settings.system,
            "unit_scale_length": scene.unit_settings.scale_length,
            "length_unit": scene.unit_settings.length_unit,
            "objects_in_scene": len(scene.objects),
            "timeline_markers": [{"name": m.name, "frame": m.frame} for m in scene.timeline_markers],
            "world": scene.world.name if scene.world else None,
        },
        "datablock_counts": {
            "objects": len(bpy.data.objects),
            "meshes": len(bpy.data.meshes),
            "materials": len(bpy.data.materials),
            "images": len(bpy.data.images),
            "armatures": len(bpy.data.armatures),
            "actions": len(bpy.data.actions),
            "cameras": len(bpy.data.cameras),
            "lights": len(bpy.data.lights),
            "collections": len(bpy.data.collections),
            "node_groups": len(bpy.data.node_groups),
        },
        "objects": [],
        "cameras": [],
        "lights": [],
        "materials": [],
        "images": [],
        "armatures": [],
        "actions": [],
        "animation_samples": [],
        "hazards": [],
    }

    mesh_objs = [o for o in bpy.data.objects if o.type == "MESH"]
    arm_objs = [o for o in bpy.data.objects if o.type == "ARMATURE"]

    for ob in bpy.data.objects:
        entry = {
            "name": ob.name,
            "type": ob.type,
            "data_name": ob.data.name if ob.data else None,
            "in_scene": ob.name in scene.objects,
            "visible": not ob.hide_render,
            "collections": [c.name for c in ob.users_collection],
            "transform": transform_report(ob),
            "dimensions": list(ob.dimensions),
            "animation": nla_report(ob),
        }
        if ob.type == "MESH":
            entry["topology"] = mesh_topology(ob)
            try:
                entry["evaluated"] = evaluated_report(ob, arm_objs)
            except Exception as exc:
                entry["evaluated"] = {"error": repr(exc)}
            entry["origin"] = origin_report(ob)
            entry["axes"] = axis_report(ob)
            lo, hi = bbox_world(ob)
            entry["world_bbox"] = {"min": list(lo), "max": list(hi), "dims": list(hi - lo)}
        if ob.type == "CAMERA":
            cam = ob.data
            rep["cameras"].append({
                "object": ob.name, "type": cam.type, "lens_mm": cam.lens,
                "ortho_scale": cam.ortho_scale, "sensor": [cam.sensor_width, cam.sensor_height],
                "clip": [cam.clip_start, cam.clip_end],
                "location": list(ob.matrix_world.translation),
                "rotation_deg": [math.degrees(a) for a in ob.matrix_world.to_euler()],
            })
        if ob.type == "LIGHT":
            li = ob.data
            rep["lights"].append({
                "object": ob.name, "type": li.type, "energy": li.energy,
                "color": list(li.color), "location": list(ob.matrix_world.translation),
            })
        rep["objects"].append(entry)

    for mat in bpy.data.materials:
        rep["materials"].append(walk_material(mat))
    for img in bpy.data.images:
        rep["images"].append(image_report(img))
    for ao in arm_objs:
        rep["armatures"].append(armature_report(ao, mesh_objs))
    for act in bpy.data.actions:
        rep["actions"].append(action_report(act))

    if arm_objs:
        for act in bpy.data.actions:
            if act.id_root not in ("ARMATURE", "OBJECT", "UNKNOWN"):
                continue
            try:
                rep["animation_samples"].append(
                    sample_action(arm_objs[0], act, mesh_objs, args["sample_frames"])
                )
            except Exception as exc:
                rep["animation_samples"].append({"action": act.name, "error": repr(exc),
                                                 "traceback": traceback.format_exc()})

    # -------------------------------------------------------------- hazard pass
    h = rep["hazards"]
    for e in rep["objects"]:
        t = e.get("topology")
        if t:
            if t["ngon_faces"]:
                h.append(f"{e['name']}: {t['ngon_faces']} n-gon faces (largest {t['largest_ngon_verts']}-gon)")
            if t["nonmanifold_edges_3plus_faces"]:
                h.append(f"{e['name']}: {t['nonmanifold_edges_3plus_faces']} edges with 3+ faces (non-manifold)")
            if t["boundary_edges"]:
                h.append(f"{e['name']}: {t['boundary_edges']} boundary/open edges - not watertight")
            if t["loose_verts"]:
                h.append(f"{e['name']}: {t['loose_verts']} loose vertices")
            if len(t["uv_layers"]) != 1:
                h.append(f"{e['name']}: {len(t['uv_layers'])} UV maps {t['uv_layers']}")
            if t["shape_keys"]:
                h.append(f"{e['name']}: {len(t['shape_keys'])} shape keys - a second animation system to reconcile")
        tr = e["transform"]
        if tr["mirrored_negative_scale"]:
            h.append(f"{e['name']}: negative world-matrix determinant - mirrored geometry, normals flip on render")
        if not tr["uniform_scale"]:
            h.append(f"{e['name']}: non-uniform scale {tr['scale']}")
        if not tr["transforms_applied"]:
            h.append(f"{e['name']}: unapplied object transform (loc {[round(v,4) for v in tr['location']]} "
                     f"rot {[round(v,2) for v in tr['rotation_euler_deg']]} scale {[round(v,4) for v in tr['scale']]})")
        for m in tr["modifiers"]:
            h.append(f"{e['name']}: modifier {m['name']} ({m['type']}) still live")
    for im in rep["images"]:
        dh = im.get("disk_header") or {}
        w = dh.get("width") or (im["blender_reported_size"][0] if im["blender_reported_size"] else 0)
        if w and w >= 4096:
            h.append(f"image {im['name']}: {dh.get('width')}x{dh.get('height')} "
                     f"({(dh.get('bytes_on_disk') or 0)/1e6:.1f} MB) - huge for a 64px sprite")
        if not im["exists_on_disk"] and not im["packed_into_blend"] and im["source"] != "GENERATED":
            h.append(f"image {im['name']}: MISSING - path {im['filepath_raw']!r} does not resolve and is not packed")
    for m in rep["materials"]:
        if not m["texture_bindings"] and m["users"]:
            h.append(f"material {m['name']}: no texture wired into any shader input")
        for u in m["unconnected_image_nodes"]:
            h.append(f"material {m['name']}: image node {u['node']} ({u['image']}) not reaching a shader")
    for a in rep["armatures"]:
        if a["in_rest_position_flag"] == "REST":
            h.append(f"armature {a['armature_object']}: pose_position is REST - animation will not evaluate until set to POSE")
        for s in a["skinning"]:
            if not s["fully_skinned"]:
                h.append(f"{s['mesh']}: {s['verts_with_weight']}/{s['verts_total']} verts weighted, "
                         f"armature modifier={s['armature_modifier']}")
    if not rep["actions"]:
        h.append("no actions in the file - the 'animated' product may only carry animation in the fbx")
    if rep["cameras"]:
        h.append(f"{len(rep['cameras'])} camera(s) already in the file - C.3 must build its own, not inherit these")
    return rep


# ------------------------------------------------------------------ human summary


def fmt(v, n=4):
    if isinstance(v, float):
        return f"{v:.{n}f}"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(fmt(x, n) for x in v) + "]"
    return str(v)


def summarise(rep):
    L = []
    w = L.append
    inp = rep["input"]
    w("=" * 78)
    w(f"MODEL TRIAGE: {inp['label']}")
    w(f"  blender {inp['blender_version']}  blend={inp['blend_filepath'] or '(none)'}  import={inp['imported_from']}")
    s = rep["scene"]
    w(f"  scene '{s['name']}' fps={s['effective_fps']:.3f} frames {s['frame_start']}..{s['frame_end']} "
      f"engine={s['render_engine']} units={s['unit_system']} scale_length={s['unit_scale_length']}")
    w(f"  datablocks: {rep['datablock_counts']}")
    w("")
    w("-- MESH " + "-" * 70)
    for e in rep["objects"]:
        if e["type"] != "MESH":
            continue
        t, o, ax = e["topology"], e["origin"], e["axes"]
        w(f"  {e['name']}  ({e['type']}, data={e['data_name']}, in_scene={e['in_scene']})")
        w(f"    verts={t['verts']}  faces={t['faces']}  tris_if_triangulated={t['tris_if_triangulated']}  "
          f"quads={t['quad_faces']} tris={t['tri_faces']} ngons={t['ngon_faces']}")
        w(f"    world dims (BU) = {fmt(e['world_bbox']['dims'])}   obj.dimensions = {fmt(e['dimensions'])}")
        w(f"    local dims (BU) = {fmt(o['local_dimensions'])}")
        w(f"    origin: world loc {fmt(o['object_location_world'])}  normalised in bbox {fmt(o['origin_normalised_in_bbox'])}")
        w(f"            offset from bbox centre (local) {fmt(o['origin_offset_from_bbox_centre_local'])}")
        w(f"    axes: length={ax.get('length_axis')}  nose/forward={ax.get('inferred_forward_nose')}  "
          f"up={ax.get('inferred_up')}  width={ax.get('inferred_width_axis')}")
        w(f"          cross-sections {json.dumps(ax.get('cross_sections'))}")
        tr = e["transform"]
        w(f"    transform: applied={tr['transforms_applied']} scale={fmt(tr['scale'])} "
          f"rot_deg={fmt(tr['rotation_euler_deg'],2)} det={fmt(tr['world_matrix_determinant'])} "
          f"mirrored={tr['mirrored_negative_scale']} parent={tr['parent']}")
        w(f"    uv={t['uv_layers']}  mats={t['material_slots']}  vgroups={len(t['vertex_groups'])}  "
          f"shapekeys={len(t['shape_keys'])}  custom_normals={t['has_custom_split_normals']}")
        w(f"    topology health: boundary_edges={t['boundary_edges']} nonmanifold_edges={t['nonmanifold_edges_3plus_faces']} "
          f"nonmanifold_verts={t['nonmanifold_verts']} at {t.get('nonmanifold_vert_coords_local')} "
          f"loose_verts={t['loose_verts']} watertight={t['watertight']}")
        w(f"    modifiers={json.dumps(tr['modifiers'])}")
        ev = e.get("evaluated") or {}
        for k in ("as_opened_viewport_eval", "render_level_eval", "rest_pose_eval"):
            v = ev.get(k)
            if isinstance(v, dict) and "verts" in v:
                w(f"    eval[{k}]: verts={v['verts']} faces={v['faces']} tris={v['tris']} "
                  f"bbox_dims={fmt(v['bbox_dims'])} bbox_min={fmt(v['bbox_min'])}")
            elif v:
                w(f"    eval[{k}]: {v}")
    w("")
    w("-- MATERIALS " + "-" * 65)
    for m in rep["materials"]:
        w(f"  {m['name']}  users={m['users']} nodes={m['use_nodes']} shaders={[sh['type'] for sh in m['shaders']]}")
        for b in m["texture_bindings"]:
            w(f"    {b['shader_input']:<16} <- {b['image']}  (via {b['via']}, colorspace={b['colorspace']})")
        for u in m["unconnected_image_nodes"]:
            w(f"    UNWIRED image node {u['node']} -> {u['image']}")
        for k, v in (m.get("node_settings") or {}).items():
            w(f"    node {k}: {json.dumps(v, default=str)}")
        if m.get("links"):
            w(f"    links: {'; '.join(l['from'] + ' -> ' + l['to'] for l in m['links'])}")
        for sh in m["shaders"]:
            keys = {k: v for k, v in sh["constant_inputs"].items()
                    if k in ("Base Color", "Roughness", "Metallic", "Specular IOR Level", "IOR", "Alpha", "Subsurface Weight")}
            w(f"    constants {json.dumps({k: (fmt(v,3) if not isinstance(v,list) else fmt(v,3)) for k,v in keys.items()})}")
    w("")
    w("-- IMAGES " + "-" * 68)
    for im in rep["images"]:
        dh = im.get("disk_header") or {}
        w(f"  {im['name']}  src={im['source']} packed={im['packed_into_blend']} exists={im['exists_on_disk']}")
        w(f"    raw path  {im['filepath_raw']!r}")
        w(f"    resolved  {im['filepath_resolved']!r}")
        w(f"    disk: {dh.get('format')} {dh.get('width')}x{dh.get('height')} "
          f"{dh.get('color_type')} bitdepth={dh.get('bit_depth')} "
          f"{(dh.get('bytes_on_disk') or 0)/1e6:.1f} MB | blender size={im['blender_reported_size']} "
          f"colorspace={im['colorspace']} users={im['users']}")
    w("")
    w("-- RIG " + "-" * 71)
    if not rep["armatures"]:
        w("  no armature")
    for a in rep["armatures"]:
        w(f"  {a['armature_object']} (data={a['armature_data']}) bones={a['bone_count']} "
          f"deform={a['deform_bone_count']} depth={a['max_hierarchy_depth']} roots={a['root_bones']} "
          f"pose_position={a['in_rest_position_flag']}")
        w(f"    bones: {a['bone_names']}")
        for b in a.get("bone_rest_layout", []):
            w(f"      {b['name']:<12} parent={str(b['parent']):<12} head={fmt(b['head_local'],3)} "
              f"tail={fmt(b['tail_local'],3)} len={b['length']:.3f} children={b['children']}")
        w(f"    posed-off-rest bones at current frame: {a['bones_posed_count']}")
        for sk in a["skinning"]:
            w(f"    skin {sk['mesh']}: armature_mod={sk['armature_modifier']} parented={sk['parented_to_armature']} "
              f"vgroups={sk['vertex_groups']} matching_bones={sk['vertex_groups_matching_bones']} "
              f"weighted_verts={sk['verts_with_weight']}/{sk['verts_total']} full={sk['fully_skinned']}")
    w("")
    w("-- ACTIONS / CLIPS " + "-" * 59)
    if not rep["actions"]:
        w("  none")
    for a in rep["actions"]:
        w(f"  {a['name']:<28} root={a['id_root']:<10} frames {a['frame_range']} (span {a['frame_span']}) "
          f"fcurves={a['fcurve_count']} bones={a['animated_bone_count']} keys={a['keyframe_count_unique_times']} "
          f"users={a['users']}")
    for smp in rep["animation_samples"]:
        if "error" in smp:
            w(f"  sample {smp['action']}: ERROR {smp['error']}")
            continue
        w(f"  sample {smp['action']}: frames {smp['frame_range']} ({smp.get('frames_sampled')} sampled) "
          f"tail travel xyz={fmt(smp['tail_travel_per_axis'])} nose travel xyz={fmt(smp['nose_travel_per_axis'])}")
        w(f"      LOOP: detected period={smp.get('detected_loop_period_frames')} frames "
          f"(resid {smp.get('detected_loop_period_residual')}) -> render frames {smp.get('loop_frames_to_render')}; "
          f"last_frame_outside_cycle={smp.get('last_frame_is_outside_cycle')}")
        w(f"      sweep axis={smp.get('dominant_tail_sweep_axis')} velocity_reversals={smp.get('tail_velocity_sign_reversals')} "
          f"loop_dev(f0,f1)={smp['pose_deviation_first_vs_last_frame']} "
          f"loop_dev(f0,f1-1)={smp.get('pose_deviation_first_vs_last_minus_one')} loops={smp['loops_cleanly']}")
        if smp.get("tail_sweep_series"):
            w(f"      tail sweep: {smp['tail_sweep_series']}")
    for e in rep["objects"]:
        an = e.get("animation")
        if an and (an["nla_tracks"] or an["active_action"]):
            w(f"  {e['name']} animdata: action={an['active_action']} slot={an['action_slot']} "
              f"drivers={an['drivers']} nla={json.dumps(an['nla_tracks'])}")
    w("")
    w("-- CAMERAS / LIGHTS " + "-" * 58)
    for c in rep["cameras"]:
        w(f"  cam {c['object']} type={c['type']} lens={fmt(c['lens_mm'],2)} ortho_scale={fmt(c['ortho_scale'],3)} "
          f"loc={fmt(c['location'],3)} rot_deg={fmt(c['rotation_deg'],2)}")
    for li in rep["lights"]:
        w(f"  light {li['object']} type={li['type']} energy={fmt(li['energy'],1)} loc={fmt(li['location'],2)}")
    w("")
    w("-- HAZARDS " + "-" * 67)
    if not rep["hazards"]:
        w("  none flagged")
    for x in rep["hazards"]:
        w(f"  ! {x}")
    w("=" * 78)
    return "\n".join(L)


def main():
    args = parse_args()
    if args["import"]:
        do_import(args["import"])
    rep = build_report(args)
    text = summarise(rep)
    print("\n" + text + "\n")
    if args["out"]:
        os.makedirs(os.path.dirname(os.path.abspath(args["out"])), exist_ok=True)
        with open(args["out"], "w") as fh:
            json.dump(rep, fh, indent=2, default=str)
        with open(os.path.splitext(args["out"])[0] + ".txt", "w") as fh:
            fh.write(text + "\n")
        print(f"[model_inspect] wrote {args['out']} and {os.path.splitext(args['out'])[0] + '.txt'}")


main()
