"""Headless Blender probe: where the lower pectoral ends up, per config, on the REAL rig.

C.5.8's `model.fin_floor` arithmetic is bpy-free (pose.floor_hold, tested on a synthetic
rig in test_fin_floor.py), but its wiring -- lay_on_floor pulling the recentre's body turn
out of the rig's basis, hold_fin_to_floor writing the held matrix back -- only runs in
Blender. Either could be switched off with no synthetic test noticing, and the cache keys on
the config hash, so a broken render_jamal would never re-render to show it. This poses each
config the way render_jamal.main does, through contact, and reports the fins;
test_fin_floor.py drives it when Blender is installed.

Usage (the tests build the job; by hand, point the paths OUTSIDE the repo):
    Blender -b --python-exit-code 1 --python tools/render/fin_probe.py -- job.json out.json
job.json is {"blend": path, "configs": [artconfig.redacted(cfg), ...]}; out.json gets one
row per config: per fin its span elevation and heading (degrees, model-world, before the
direction turn), root and tip z in tiles above the floor, and which fin the hold took.

Mirrors main's posing steps instead of calling main, which also builds the camera, sun and
holdout and renders. The steps that MOVE the rig (lay_on_floor, ground_contact) are
render_jamal's own functions, so the real wiring is what gets probed.
"""

# sys.path, verbatim per tools/README.md -- see render_jamal.py.
import pathlib, sys  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
import math

import bpy

from render import artconfig as ac
from render import pose
from render import render_jamal as rj


def probe(cfg: dict) -> dict:
    scene = bpy.context.scene
    rig = bpy.data.objects.get(cfg["model.object"])
    if cfg["model.mute_nla"]:
        rj.mute_nla_tracks()
    if cfg["model.rest_pose"]:
        rj.clear_pose(rig)
    if cfg["model.drop_stale_keyframes"]:
        rj.drop_stale_final_keyframes()
    if cfg["model.reparent_head"]:
        rj.reparent_head(rig)
    if cfg["model.action"] != pose.REST:
        rj.apply_action(cfg, rig)
    rj.strip_scene(scene)
    rj.set_subdiv(cfg)
    scene.frame_set(cfg["model.frame"])
    _root, subject = rj.build_rig(scene, cfg)
    lines = rj.lay_on_floor(cfg, subject)
    if cfg["model.ground_contact"]:
        rj.ground_contact(cfg, subject)
    bpy.context.view_layer.update()
    held = [ln.split()[3] for ln in lines if ln.startswith("FIX fin floor: ")]
    mw, bones = subject.matrix_world, subject.pose.bones
    row = {"held": held[0] if held else None}
    for name in ("FIN_LEFT", "FIN_RIGHT"):
        head, tail = mw @ bones[name].head, mw @ bones[name].tail
        d = tail - head
        row[name] = {"elev": math.degrees(math.asin(max(-1.0, min(1.0, d.z / d.length)))),
                     "heading": math.degrees(math.atan2(d.y, d.x)),
                     "root_z": head.z, "tip_z": tail.z}
    return row


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    with open(argv[0]) as fh:
        job = json.load(fh)
    out = []
    for flat in job["configs"]:
        # A fresh file per config: every step above mutates the rig for good.
        bpy.ops.wm.open_mainfile(filepath=job["blend"])
        out.append(probe(ac.resolve(ac.unflatten(flat), env={})))
    with open(argv[1], "w") as fh:
        json.dump(out, fh, indent=1)


if __name__ == "__main__":
    main()
