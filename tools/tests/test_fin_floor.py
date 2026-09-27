"""C.5.8's fin spike: `model.fin_floor` and pose.floor_hold.

chotchki 2026-09-26, off V4/V5's U: a long white spike under his chest, "fix it". C.5.6's
fin_fold turns the lower pectoral a FIXED 50 deg from wherever the pose left it, and the U
moves that twice: the evened, doubled curl swings the chest the fin hangs off, and the
recentre turns the whole body. The hold pins the fin to its orientation on a REST spine
with no body turn, and the fold works from there.

The arithmetic is bpy-free (pose.floor_hold), tested on a synthetic rig: the real
FIN_RIGHT's rest span, the beached framing's roll and yaw, a chest swing and a recentre turn
both about the swim's bend axis (armature z), and C.5.6's fold in plain vectors. The
real-rig numbers (the spike at 51 px down-screen at the U's bottom, the held fin at -3.8 deg
on every heave frame) are in PLAN C.5.8; the last section re-measures them through
render_jamal (render/fin_probe.py) when Blender and the model are on disk. The wiring
(lay_on_floor pulling the body turn out, the hold applied at all) has no bpy-free stand-in,
and the cache keys on the config hash, so a regression there would never re-render to show.

WHAT THE HOLD IS NOT, on the record: it holds the fin's ORIENTATION, not its contact (the tip
rides a lifted chest up to ~1 tile), and it acts on any POSED frame whether or not recentre
is on. chotchki's "unchanged when recentre is 0" holds only for a rest spine with no turn.
"""

import json
import math
import pathlib
import subprocess

import pytest

from render import art
from render import artconfig as ac
from render import pose
from render import sequence

#: On the shipped model's digest (conftest.shipped_model): holds on a runner with no model.
STANDING_HASH = "bd71cb367d90"

#: FIN_RIGHT's rest span on the rig (tail_local - head_local), armature space.
FIN_SPAN = (-0.399, -0.629, -0.295)


def rot(axis, deg):
    """3x3 rotation (row lists) about a unit axis."""
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z)
    x, y, z = x / n, y / n, z / n
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    t = 1 - c
    return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]


def mul(*ms):
    out = ms[0]
    for m in ms[1:]:
        out = pose._matmul3(out, m)
    return out


def apply(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def frame_with_y(y):
    """A rest matrix_local rotation whose Y (a bone's length axis) is `y`."""
    y = unit(y)
    x = unit(cross(y, (0.0, 0.0, 1.0)))
    z = cross(x, y)
    return [[x[i], y[i], z[i]] for i in range(3)]


IDENTITY = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
FIN_REST = frame_with_y(FIN_SPAN)
#: Armature -> world at the beached framing: base_yaw 90 over pose_fix's XYZ euler (roll 85,
#: then yaw 180 -- Blender applies X first, so the matrix is Rz . Rx). Rotation only: the
#: girth scale sits above the rig, and the hold works under it.
WORLD = mul(rot((0, 0, 1), 90.0), rot((0, 0, 1), 180.0), rot((1, 0, 0), 85.0))
#: The swim bends about armature z (spine along x, bend in x-y), as does the recentre's
#: counter-turn (rest chord x posed chord, both in x-y).
BEND = (0.0, 0.0, 1.0)
#: A bite's own rotation on the fin (BITE_01 turns FIN_RIGHT up to 47 deg), about its X.
BITE = rot((1.0, 0.0, 0.0), 30.0)


def world_span(chest_deg, turn_deg, basis=IDENTITY, hold=False, fold=0.0):
    """The lower fin's span in WORLD after the chest swings `chest_deg`, the body turns
    `turn_deg`, the hold (optional) and C.5.6's fold of `fold` degrees -- which turns it about
    span x up, measured in armature space, exactly as render_jamal.fold_lower_fin does."""
    turn = rot(BEND, turn_deg)
    if hold:
        arm = pose.floor_hold(FIN_REST, basis, turn)
    else:
        arm = mul(rot(BEND, chest_deg), FIN_REST, basis)
    span = apply(arm, (0.0, 1.0, 0.0))
    to_world = mul(WORLD, turn)
    if fold:
        up = apply([list(r) for r in zip(*to_world)], (0.0, 0.0, 1.0))  # inverse = transpose
        span = apply(rot(cross(span, up), fold), span)
    return unit(apply(to_world, span))


def elevation(v):
    return math.degrees(math.asin(max(-1.0, min(1.0, v[2]))))


#: A heave's worth of chest swing and body turn, V5-sized: MEASURED on the rig the evened,
#: doubled curl swings the fin through 25-62 deg of dive and the recentre turns up to ~60.
HEAVE = [(25.0 * math.sin(2 * math.pi * i / 20), 60.0 * math.sin(2 * math.pi * i / 20 + 0.3))
         for i in range(20)]


# ------------------------------------------------------------------------ the arithmetic


def test_the_hold_is_the_pose_itself_on_a_rest_spine_with_no_turn():
    """With nothing to take out the hold changes nothing: the bite frames (no spine bone
    moves, recentre 0) get exactly C+'s fold."""
    for basis in (IDENTITY, BITE):
        held = pose.floor_hold(FIN_REST, basis, IDENTITY)
        assert sum(held, []) == pytest.approx(sum(mul(FIN_REST, basis), []))
        for fold in (0.0, 50.0):
            assert world_span(0.0, 0.0, basis, hold=True, fold=fold) == pytest.approx(
                world_span(0.0, 0.0, basis, hold=False, fold=fold))


@pytest.mark.parametrize("chest,turn", [(-25.0, 0.0), (0.0, 58.0), (18.0, -40.0), (-9.0, 60.0)])
def test_the_hold_takes_out_the_chest_swing_and_the_body_turn(chest, turn):
    """The world sees body_turn x held == rest x basis: the orientation of a rest spine that
    never turned, whatever the curl and the recentre did."""
    rest = world_span(0.0, 0.0)
    assert world_span(chest, turn, hold=True) == pytest.approx(rest, abs=1e-12)
    assert world_span(chest, turn, hold=False) != pytest.approx(rest, abs=1e-3)


def test_the_hold_keeps_the_fins_own_rotation():
    """A bite still flaps the fin: only the PARENTS' motion and the body turn come out."""
    flapped = world_span(20.0, 40.0, BITE, hold=True)
    assert flapped == pytest.approx(world_span(0.0, 0.0, BITE), abs=1e-12)
    assert flapped != pytest.approx(world_span(0.0, 0.0), abs=1e-3)


def test_the_fixed_fold_swings_through_a_heave_and_the_held_one_lies_still():
    """Bug and fix on one sweep. Folded a fixed 50 deg from wherever the U left it, the fin's
    world elevation and heading wander tens of degrees over a heave (the spike). Held first,
    the folded fin has ONE elevation and ONE heading on every frame: the rest spine's (C+'s
    level fin)."""
    def heading(v):
        return math.degrees(math.atan2(v[1], v[0]))
    fixed = [world_span(c, t, fold=50.0) for c, t in HEAVE]
    held = [world_span(c, t, hold=True, fold=50.0) for c, t in HEAVE]
    spread = lambda vals: max(vals) - min(vals)  # noqa: E731
    assert spread([elevation(v) for v in fixed]) > 20.0
    assert spread([heading(v) for v in fixed]) > 20.0
    assert spread([elevation(v) for v in held]) < 1e-9
    assert spread([heading(v) for v in held]) < 1e-9
    assert elevation(held[0]) == pytest.approx(elevation(world_span(0.0, 0.0, fold=50.0)))
    # ...and on the rest spine that fold lays the real fin within a few degrees of level
    assert abs(elevation(held[0])) < 10.0


# -------------------------------------------------------------------- knob and wiring


def test_the_knob_is_off_by_default_and_out_of_the_standing_hash(shipped_model):
    standing = shipped_model(ac.load(env={}))
    assert standing["model.fin_floor"] is False
    assert "model.fin_floor" in ac.ADDITIVE
    assert "model.fin_floor" not in ac.hashable(standing)
    assert ac.config_hash(standing) == STANDING_HASH


def test_the_knob_moves_every_pass_hash_when_on_and_back_when_off():
    flop = dict(ac.load(ac.BEACHED_CONFIG_PATH, env={}), **{"model.fin_floor": False})
    on = dict(flop, **{"model.fin_floor": True})
    for name in ("body", "shadow", "mask"):
        assert ac.pass_hash(on, name) != ac.pass_hash(flop, name), name
    assert ac.config_hash(dict(on, **{"model.fin_floor": False})) == ac.config_hash(flop)


def test_the_beached_overlay_holds_the_fin_and_says_so():
    beached = ac.load(ac.BEACHED_CONFIG_PATH, env={})
    assert beached["model.fin_floor"] is True and beached["model.fin_fold"] == 50.0
    assert not [w for w in ac.warnings(beached) if "fin_floor" in w]
    assert "fin_fold 50 (floor)" in art.bedding_note(beached)
    assert "(floor)" not in art.bedding_note(dict(beached, **{"model.fin_floor": False}))


def test_the_knob_warns_where_it_does_nothing_or_leaves_the_fin_diving():
    flop = ac.load(ac.BEACHED_CONFIG_PATH, env={})
    said = lambda cfg: [w for w in ac.warnings(cfg) if "fin_floor" in w]  # noqa: E731
    assert said(dict(flop, **{"model.fin_fold": 0.0})), "held at its rest dive, never laid flat"
    rest = dict(ac.load(env={}), **{"model.fin_floor": True, "model.fin_fold": 50.0})
    assert any("NOTHING" in w for w in said(rest))
    assert not said(dict(rest, **{"model.recentre": 1.0, "model.ground_contact": True}))


# ------------------------------------------------------------- the real rig, in Blender
#
# render/fin_probe.py poses each config as render_jamal.main does (lay_on_floor, contact)
# and reports the fins. ONE Blender for the lot (~3 s): heave frames across the U with the
# hold on and off, and the U's bottom at recentre 0 both ways.

PROBE = pathlib.Path(__file__).resolve().parents[1] / "render" / "fin_probe.py"
#: The heave frames probed: the arch (f1, f18), the U's walls and its bottom (f7-f11, where
#: the unheld fin pointed at the camera), and the way back up.
HEAVE_FRAMES = (1, 4, 7, 9, 11, 13, 15, 18)
U_FRAMES = (7, 9, 11)


def _heave():
    seq = sequence.load(ac.BEACHED_CONFIG_PATH)
    got = {}
    for i, (beat, frame) in enumerate(seq.played):
        if beat == "heave":
            got.setdefault(frame, seq.configs[seq.order[i]])
    return got


def _blender_ready():
    cfg = ac.load(ac.BEACHED_CONFIG_PATH, env={})
    return pathlib.Path(art.BLENDER).is_file() and ac.blend_path(cfg).is_file()


needs_blender = pytest.mark.skipif(not _blender_ready(),
                                   reason="no Blender or no model on disk (CI has neither)")


@pytest.fixture(scope="module")
def probed(tmp_path_factory):
    """{(frame, fin_floor, recentre): row} off one Blender run."""
    heave = _heave()
    cfgs = []
    for f in HEAVE_FRAMES:
        for held in (True, False):
            cfgs.append(dict(heave[f], **{"model.fin_floor": held}))
    for held in (True, False):
        cfgs.append(dict(heave[11], **{"model.fin_floor": held, "model.recentre": 0.0}))
    assert all(c["model.recentre"] == 1.0 for c in cfgs[:-2]), "V5's heave is fully recentred"
    work = tmp_path_factory.mktemp("fin_probe")
    job, out = work / "job.json", work / "out.json"
    job.write_text(json.dumps({"blend": str(ac.blend_path(cfgs[0])),
                               "configs": [ac.redacted(c) for c in cfgs]}))
    proc = subprocess.run([art.BLENDER, "-b", "--python-exit-code", "1", "--python",
                           str(PROBE), "--", str(job), str(out)],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-3000:]
    rows = json.loads(out.read_text())
    return {(c["model.frame"], c["model.fin_floor"], c["model.recentre"]): r
            for c, r in zip(cfgs, rows)}


def _spread(vals):
    return max(vals) - min(vals)


@needs_blender
def test_on_the_real_rig_the_held_fin_has_one_orientation_through_the_heave(probed):
    """The acceptance measurement, through render_jamal's lay_on_floor: FIN_RIGHT (the lower
    one) is held on every frame at one elevation and heading within half a degree, near
    level. Kills both wiring mutations the review found surviving the suite: the body turn
    read as identity (the recentre's turn stays in) and the hold skipped."""
    held = [probed[(f, True, 1.0)] for f in HEAVE_FRAMES]
    assert {r["held"] for r in held} == {"FIN_RIGHT"}
    elev = [r["FIN_RIGHT"]["elev"] for r in held]
    heading = [r["FIN_RIGHT"]["heading"] for r in held]
    assert _spread(elev) < 0.5, elev
    assert _spread(heading) < 0.5, heading
    assert abs(elev[0]) < 10.0, "the fold lays the held fin near level"


@needs_blender
def test_on_the_real_rig_the_unheld_fin_swings_so_the_probe_can_see_the_spike(probed):
    """Without the hold the same frames wander tens of degrees (the 51 px spike at the U's
    bottom). If this fails the probe no longer measures what renders and the test above
    proves nothing."""
    free = [probed[(f, False, 1.0)]["FIN_RIGHT"] for f in HEAVE_FRAMES]
    assert _spread([r["elev"] for r in free]) > 10.0
    assert _spread([r["heading"] for r in free]) > 10.0


@needs_blender
def test_the_hold_acts_without_a_recentre_on_a_posed_spine(probed):
    """chotchki asked for 'the fold is unchanged when recentre is 0'. It is not; this pins
    what IS true: at recentre 0 the hold still takes the chest's swing out, landing on the
    recentred frame's orientation. Unchanged holds only on a rest spine with no turn
    (test_the_hold_is_the_pose_itself_on_a_rest_spine_with_no_turn)."""
    held0, free0 = probed[(11, True, 0.0)]["FIN_RIGHT"], probed[(11, False, 0.0)]["FIN_RIGHT"]
    held1 = probed[(11, True, 1.0)]["FIN_RIGHT"]
    assert held0["elev"] == pytest.approx(held1["elev"], abs=0.5)
    assert held0["heading"] == pytest.approx(held1["heading"], abs=0.5)
    assert abs(free0["elev"] - held0["elev"]) > 10.0


@needs_blender
def test_the_hold_is_orientation_not_contact(probed):
    """ON THE RECORD, not a goal: chotchki's second test was 'the fin tip's height above the
    floor across the heave stays within a small band', and it does NOT. The tip keeps a fixed
    offset from its root (orientation held) and sits on the sand on the U frames, but rides
    his lifted chest on the arch; reaching it down would point it back at the camera. A later
    fix that pulls the tip down changes this test."""
    rows = {f: probed[(f, True, 1.0)]["FIN_RIGHT"] for f in HEAVE_FRAMES}
    drop = [r["tip_z"] - r["root_z"] for r in rows.values()]
    assert _spread(drop) < 0.005 and all(d < 0 for d in drop), drop
    for f in U_FRAMES:
        assert -0.05 <= rows[f]["tip_z"] <= 0.25, (f, rows[f]["tip_z"])
    assert max(r["tip_z"] for r in rows.values()) > 0.5, "the arch lifts it: not a band"
