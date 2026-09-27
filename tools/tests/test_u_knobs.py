"""C.5.8's U: `model.recentre` and `model.amplitude_even`.

Both knobs' arithmetic lives in render/pose.py (bpy-free), tested on a synthetic spine: a
planar chain of the rig's bone lengths bent by the swim's MEASURED per-joint swing (pose.py's
table). What the knobs claim (head and tail rise together, the bend's bottom moves to the
middle) is checked on the chain's geometry, not just the return values. The render side
(render_jamal.recentre_model, the per-joint gain in apply_action) applies exactly these
numbers; the real-rig measurement is in PLAN C.5.8.
"""

import math

import pytest

from render import artconfig as ac
from render import pose
from render import sequence
from render import tune

#: pose.py's table: SWIM_FAST's measured swing per joint, SPINE_01..TAIL, degrees.
SWING = (2.99, 1.52, 3.75, 4.56, 8.09, 10.54, 8.26, 10.82)
#: The rig's spine bone lengths, SPINE_01..TAIL (x span of each bone's rest head->tail).
LENGTHS = (0.491, 0.450, 0.414, 0.415, 0.415, 0.415, 0.415, 0.414)

#: Both pins are on the shipped model's digest (conftest.shipped_model), so they hold on a
#: runner with no model and still move with any knob.
STANDING_HASH = "bd71cb367d90"
#: The shipped flop sheet: C.5.9's V5 at gain 1.25 with the bounce re-phased to land on the
#: push (chotchki 2026-09-26). Both knobs ON since C.5.8's V5 (f9c264329dc0).
BEACHED_DIGEST = "a5b3c3f1531c"


def chain(joint_deg):
    """Points of a planar chain rooted at the origin, pointing -x (nose at 0, tail at -3.4),
    each joint turning the rest of the chain by its angle. y is the bend direction."""
    pts, ang, x, y = [(0.0, 0.0)], 0.0, 0.0, 0.0
    for a, n in zip(joint_deg, LENGTHS):
        ang += math.radians(a)
        x -= n * math.cos(ang)
        y += n * math.sin(ang)
        pts.append((x, y))
    return pts


def turned(pts, axis_z, angle, about):
    """Rotate 2D points by `angle` about `about`, sign by the z of the rotation axis."""
    a = angle * (1.0 if axis_z > 0 else -1.0)
    c, s = math.cos(a), math.sin(a)
    return [(about[0] + c * (x - about[0]) - s * (y - about[1]),
             about[1] + s * (x - about[0]) + c * (y - about[1])) for x, y in pts]


def ends_vs_middle(pts):
    """(head, tail) height off the chain's middle point, along y."""
    mid = pts[len(pts) // 2][1]
    return pts[0][1] - mid, pts[-1][1] - mid


# ------------------------------------------------------------------- amplitude evening


def test_even_gains_blend_every_swing_toward_the_mean_and_keep_the_sum():
    mean = sum(SWING) / len(SWING)
    assert pose.even_gains(SWING, 0.0) == [1.0] * len(SWING), "0 is the clip as bought"
    at_one = [a * g for a, g in zip(SWING, pose.even_gains(SWING, 1.0))]
    assert all(v == pytest.approx(mean) for v in at_one)
    for even in (0.25, 0.5, 0.75, 1.0):
        swung = [a * g for a, g in zip(SWING, pose.even_gains(SWING, even))]
        assert sum(swung) == pytest.approx(sum(SWING)), "it moves the curl, it adds none"
        for a, v in zip(SWING, swung):
            assert v == pytest.approx((1 - even) * a + even * mean)
    # the rear-loading, undone: the weakest joint (SPINE_02) is pushed hardest, the tail eased
    g = pose.even_gains(SWING, 1.0)
    assert g[1] == pytest.approx(4.16, abs=0.01) and g[-1] == pytest.approx(0.58, abs=0.01)


def test_even_gains_leave_a_still_joint_alone_and_take_an_empty_chain():
    assert pose.even_gains([0.0, 2.0, 4.0], 1.0)[0] == 1.0, "no swing, nothing to scale"
    assert pose.even_gains([], 1.0) == []


def test_wave_amplitudes_read_the_swing_off_one_cycle():
    n = 20
    sigs = [[a * math.cos(2 * math.pi * k / n + 0.3 * i) + 0.1 for k in range(n)]
            for i, a in enumerate(SWING)]
    assert pose.wave_amplitudes(sigs) == pytest.approx(list(SWING), abs=1e-9)


def test_evening_moves_the_bend_bottom_to_the_middle():
    """The knob's purpose, on the chain: rear-loaded, the front half is nearly straight and
    the curl is all behind the middle (a hook, not a U). Evened, both halves bend the same."""
    def halves(joints):
        return sum(joints[:4]), sum(joints[4:])
    front, rear = halves(SWING)
    assert rear > 2.5 * front, "the measured 3:1"
    even = [a * g for a, g in zip(SWING, pose.even_gains(SWING, 1.0))]
    front, rear = halves(even)
    assert front == pytest.approx(rear)


# ------------------------------------------------------------------------- recentring


def test_counter_turn_is_the_chord_turn_undone():
    rest = (-1.0, 0.0, 0.0)
    posed = (-math.cos(0.4), math.sin(0.4), 0.0)
    axis, angle = pose.counter_turn(rest, posed, 1.0)
    assert axis == pytest.approx((0.0, 0.0, -1.0))
    assert angle == pytest.approx(-0.4)
    assert pose.counter_turn(rest, posed, 0.5)[1] == pytest.approx(-0.2)
    assert pose.counter_turn(rest, rest, 1.0) == (None, 0.0), "no turn, nothing to undo"


@pytest.mark.parametrize("even", [0.0, 1.0])
def test_recentre_one_makes_head_and_tail_rise_together(even):
    """C.5.2's measured failure and the fix, on the chain. Every joint in phase (lock 1) at
    peak curl with the root pinned: the tail swings and the nose stays, so relative to his
    middle the head goes DOWN while the tail goes UP, a seesaw that read as a tail flick
    (MEASURED on the rig: head/tail correlation -1.00). Turned back by the chord's whole
    turn about its midpoint, both ends are on the SAME side of the middle and the chord is
    level."""
    joints = [a * g for a, g in zip(SWING, pose.even_gains(SWING, even))]
    pts = chain(joints)
    head, tail = ends_vs_middle(pts)
    assert head * tail < 0, "pinned at the nose: a seesaw, not a U"
    rest = (-sum(LENGTHS), 0.0, 0.0)
    posed = (pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1], 0.0)
    axis, angle = pose.counter_turn(rest, posed, 1.0)
    mid = ((pts[0][0] + pts[-1][0]) / 2, (pts[0][1] + pts[-1][1]) / 2)
    level = turned(pts, axis[2], angle, mid)
    assert level[0][1] == pytest.approx(level[-1][1], abs=1e-9), "the chord is level"
    head, tail = ends_vs_middle(level)
    assert head * tail > 0 and min(abs(head), abs(tail)) > 0.05, "both ends rise together"
    # and the same curl the other way is the arch: both ends on the other side
    arched = chain([-j for j in joints])
    posed = (arched[-1][0] - arched[0][0], arched[-1][1] - arched[0][1], 0.0)
    axis, angle = pose.counter_turn(rest, posed, 1.0)
    mid = ((arched[0][0] + arched[-1][0]) / 2, (arched[0][1] + arched[-1][1]) / 2)
    h2, t2 = ends_vs_middle(turned(arched, axis[2], angle, mid))
    assert h2 * head < 0 and t2 * tail < 0


# ------------------------------------------------------------------ hashes and wiring


def test_both_knobs_default_off_and_out_of_every_shipped_hash(shipped_model):
    standing = shipped_model(ac.load(env={}))
    assert standing["model.recentre"] == 0.0 and standing["model.amplitude_even"] == 0.0
    assert ac.config_hash(standing) == STANDING_HASH
    view = ac.hashable(standing)
    assert "model.recentre" not in view and "model.amplitude_even" not in view
    beached = shipped_model(ac.load(ac.BEACHED_CONFIG_PATH, env={}))
    assert beached["model.recentre"] == beached["model.amplitude_even"] == 1.0, "V5 ships them"
    seq = sequence.parse(ac.load_sequence(ac.BEACHED_CONFIG_PATH), beached)
    assert seq.digest == BEACHED_DIGEST, "the shipped flop sheet's frames must not move"


@pytest.mark.parametrize("key", ["model.recentre", "model.amplitude_even"])
def test_each_knob_moves_every_pass_hash_when_on(key):
    """Off (the C+ flop, which beached.toml's bite beats still are) against on."""
    flop = dict(ac.load(ac.BEACHED_CONFIG_PATH, env={}),
                **{"model.recentre": 0.0, "model.amplitude_even": 0.0})
    moved = dict(flop, **{key: 1.0})
    assert ac.config_hash(moved) != ac.config_hash(flop)
    for name in ("body", "shadow", "mask"):
        assert ac.pass_hash(moved, name) != ac.pass_hash(flop, name), name
    back = dict(moved, **{key: 0.0})
    assert ac.config_hash(back) == ac.config_hash(flop)


def test_the_knobs_warn_where_they_do_nothing_or_run_off_the_rail():
    flop = ac.load(ac.BEACHED_CONFIG_PATH, env={})
    said = lambda cfg, key: [w for w in ac.warnings(cfg) if key in w]  # noqa: E731
    on = dict(flop, **{"model.phase_lock": 1.0, "model.recentre": 1.0,
                       "model.amplitude_even": 1.0})
    assert not said(on, "recentre") and not said(on, "amplitude_even"), "the U config is clean"
    for bad in (-0.1, 1.5):
        assert said(dict(flop, **{"model.recentre": bad}), "recentre")
        assert said(dict(flop, **{"model.amplitude_even": bad}), "amplitude_even")
    bite = dict(flop, **{"model.action": "BITE_01", "model.amplitude_even": 1.0})
    assert any("NOTHING" in w for w in said(bite, "amplitude_even"))
    rest = dict(ac.load(env={}), **{"model.recentre": 1.0})
    assert said(rest, "recentre")
    floating = dict(on, **{"model.ground_contact": False})
    assert any("ground_contact" in w for w in said(floating, "recentre"))


def test_the_tuner_exports_both_as_flop_knobs():
    for key in ("model.recentre", "model.amplitude_even"):
        assert key in tune.TOML_KEYS and key in tune.FLOP_KEYS
        assert key in ac.ADDITIVE


def test_the_recentre_chord_is_the_whole_spine():
    """The chord runs the chain the swim bends, nose root to caudal tip -- the same chain
    spine_sag's back half is cut from."""
    assert ac.RECENTRE_CHORD == ("SPINE_01", "TAIL")
    assert ac.SPINE_SAG_CHAIN[-1] == ac.RECENTRE_CHORD[-1]
