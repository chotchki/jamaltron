"""The pose baker's promises, with no Blender and no model anywhere in the loop.

Three of them are load bearing and the rest is arithmetic:

 1. THE CLIP TABLE CANNOT LIE FOR LONG. It is hardcoded knowledge about a file this repo
    does not ship, so pose.verify_clips() checks it against what Blender reports on every
    bake. These tests pin the checker, because a checker that cannot fail is decoration.
 2. A BAKED POSE NEVER LANDS IN THE REPO. It is the licensed mesh with its bones moved --
    derived, still licensed -- and the one rule the model has is that it does not enter the
    repo. That is one assert, and it is the most important one in this file.
 3. A LOOP STARTS WHERE THE CLIP STARTS. Every stride keeps frame 1, or the loop stutters
    at the seam that the stale-final-keyframe drop exists to remove.
"""

import pathlib

from render import artconfig as ac
from render import pose

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_the_clip_table_is_internally_consistent():
    assert len({c.id for c in pose.CLIPS}) == len(pose.CLIPS), "duplicate clip id"
    assert len({c.action for c in pose.CLIPS}) == len(pose.CLIPS), "two clips, one action"
    for c in pose.CLIPS:
        assert c.lo >= 1 and c.hi >= c.lo, c.id
        assert c.span == c.hi - c.lo + 1
        assert abs(c.seconds - c.span / pose.FPS) < 1e-9
        assert c.id != pose.REST, "a clip cannot be called rest; rest means no clip"


def test_verify_clips_catches_a_range_that_moved_under_it():
    """The whole point of the check: the model gets re-exported, a cycle grows a frame, and
    the frame slider would quietly offer a frame that does not exist."""
    good = {c.action: {"raw": [c.lo, c.hi + 1], "dropped": [c.lo, c.hi]} for c in pose.CLIPS}
    assert pose.verify_clips(good) == []

    moved = dict(good)
    moved["ArmatureAction.002"] = {"raw": [1, 26], "dropped": [1, 25]}
    out = pose.verify_clips(moved)
    assert len(out) == 1 and "SWIM_FAST" in out[0] and "1-25" in out[0]

    gone = {k: v for k, v in good.items() if k != "SWIM_SLOW.001"}
    assert any("SWIM_SLOW" in m and "no action" in m for m in pose.verify_clips(gone))


def test_verify_clips_reads_the_dropped_range_not_the_raw_one():
    """render_jamal drops each action's duplicate final keyframe before anything is played,
    so the range a slider may offer is the DROPPED one. Checking `raw` would report every
    clip as off by one, every run, and the check would get turned off."""
    raw_only = {c.action: {"raw": [c.lo, c.hi + 1], "dropped": [c.lo, c.hi]}
                for c in pose.CLIPS}
    assert pose.verify_clips(raw_only) == []


def test_a_baked_pose_never_lands_in_the_repo(monkeypatch):
    """The model is licensed and gitignored. A baked pose is the same mesh with its bones
    moved, so it lives in $TMPDIR and nowhere near here."""
    monkeypatch.delenv(pose.CACHE_ENV, raising=False)
    cfg = ac.resolve(env={})
    p = pose.baked_path(cfg, "SWIM_FAST", 7, 2.0)
    assert REPO not in p.parents, p
    assert pose.cache_root() not in REPO.parents
    assert p.suffix == ".blend" and "SWIM_FAST" in p.name and "f007" in p.name


def test_the_bake_key_moves_for_everything_the_POSE_depends_on():
    base = ("sha256:abc", "ArmatureAction.002", 7, 2.0, "HAMMERHEAD_RIG", True)
    key = pose.bake_key(*base)
    for i, other in enumerate(("sha256:def", "ArmatureAction.004", 8, 2.5, "OTHER_RIG",
                               False)):
        args = list(base)
        args[i] = other
        assert pose.bake_key(*args) != key, "argument %d does not move the key" % i
    assert pose.bake_key(*base) == key, "not deterministic"


def test_the_bake_key_does_not_move_for_anything_applied_at_render_time():
    """Roll, scale, girth, pivot and the camera are build_rig's job, not the bake's. If they
    keyed a baked file, every drag of the roll slider would throw away the whole loop."""
    cfg = ac.resolve(env={})
    rolled = dict(cfg, **{"model.rotation": [30.0, 0.0, 0.0], "model.scale": 0.9,
                          "model.girth": 1.8, "model.pivot": [-0.9, 0.0, 0.4]})
    assert pose.baked_path(cfg, "SWIM_FAST", 7, 2.0) == pose.baked_path(rolled, "SWIM_FAST",
                                                                       7, 2.0)


def test_clamp_frame_holds_the_clips_own_range():
    assert pose.clamp_frame("SWIM_FAST", 999) == 20
    assert pose.clamp_frame("SWIM_FAST", -5) == 1
    assert pose.clamp_frame("SWIM_FAST", 7.6) == 8
    assert pose.clamp_frame("SWIM_FAST", "nope") == 1
    assert pose.clamp_frame("SWIM_SLOW", 78) == 78
    # REST has exactly one frame, whatever a stale page asks for.
    assert pose.clamp_frame(pose.REST, 40) == 1
    assert pose.clamp_frame("NOT_A_CLIP", 40) == 1


def test_clamp_gain_refuses_the_values_that_are_not_gains():
    assert pose.clamp_gain(2.0) == 2.0
    assert pose.clamp_gain(99) == pose.GAIN_MAX
    assert pose.clamp_gain(0.1) == pose.GAIN_MIN
    for junk in ("x", None, [2.0], float("nan"), float("inf"), float("-inf")):
        assert pose.clamp_gain(junk) == 1.0, junk


def test_a_loop_starts_at_the_clips_first_frame_at_every_stride():
    for c in pose.CLIPS:
        for stride in range(1, 7):
            frames = pose.loop_frames(c.id, stride)
            assert frames[0] == c.lo, (c.id, stride)
            assert frames[-1] <= c.hi, (c.id, stride)
            assert frames == sorted(set(frames))
            assert all(b - a == stride for a, b in zip(frames, frames[1:]))


def test_a_rest_loop_is_one_frame_and_cannot_play():
    assert pose.loop_frames(pose.REST) == [1]
    assert pose.loop_frames("NOT_A_CLIP", 3) == [1]


def test_the_loop_plays_at_the_clips_own_tempo():
    """Ten frames of a 20-frame cycle at stride 2, each held 2/24 s, is the 0.83 s the clip
    runs at 24 fps. A loop that plays at the wrong speed is a different animation."""
    frames = pose.loop_frames("SWIM_FAST", 2)
    assert len(frames) == 10
    assert abs(len(frames) * pose.loop_ms(2) / 1000.0 - pose.clip_of("SWIM_FAST").seconds) < 1e-9


def test_prune_drops_the_oldest_and_keeps_the_rest(tmp_path):
    import os
    root = tmp_path / "cache" / "abc123"
    root.mkdir(parents=True)
    made = []
    for i in range(10):
        p = root / ("f%02d.blend" % i)
        p.write_bytes(b"x")
        os.utime(p, (1_600_000_000 + i, 1_600_000_000 + i))
        made.append(p)
    gone = pose.prune(tmp_path / "cache", keep=4)
    assert [p.name for p in gone] == [p.name for p in made[:6]]
    assert sorted(p.name for p in root.glob("*.blend")) == [p.name for p in made[6:]]
    assert pose.prune(tmp_path / "cache", keep=4) == [], "a second prune has nothing to do"
    assert pose.prune(tmp_path / "does-not-exist") == []


def test_rest_bakes_nothing_and_never_launches_blender(monkeypatch):
    """Selecting the rest pose has to be the shipped render, byte for byte -- no temp file,
    no bake, nothing between the committed config and the sprites that already ship."""
    monkeypatch.setattr(pose.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("rest must not launch Blender")))
    out = pose.ensure(ac.resolve(env={}), pose.REST, [1, 2, 3], gain=2.0)
    assert out.paths == {} and out.baked == [] and out.clip_id == pose.REST
    assert out.ok
