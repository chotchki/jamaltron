"""The clip table's promises, with no Blender and no model anywhere in the loop.

Three of them are load bearing and the rest is arithmetic:

 1. THE TABLE CANNOT LIE FOR LONG. It is hardcoded knowledge about a file this repo does not
    ship, so pose.verify_clips() checks it against what Blender reports on every posed
    render. These tests pin the checker, because a checker that cannot fail is decoration.
 2. THE SCHEMA AND THE TABLE AGREE ON WHAT A CLIP IS CALLED. `model.action` takes its legal
    values from ACTION_CHOICES; a clip that is in the table and not in the enum is a clip you
    cannot select, and one in the enum and not the table is a fatal render halfway through.
 3. A LOOP STARTS WHERE THE CLIP STARTS. Every stride keeps frame 1, or the loop stutters at
    the seam that the stale-final-keyframe drop exists to remove.

This module used to bake poses into temp .blends because the harness had no knob for which
action. The knobs landed (artconfig.SCHEMA: model.action / model.pose_gain), so the bake and
its cache are gone and the tests that pinned "a baked pose never lands in the repo" went with
them -- there is nothing to write any more. The rule they protected is now structural: the
only thing that ever opens the model is Blender, and it opens the bought file read-only.
"""

from render import artconfig as ac
from render import pose


def test_the_clip_table_is_internally_consistent():
    assert len({c.id for c in pose.CLIPS}) == len(pose.CLIPS), "duplicate clip id"
    assert len({c.action for c in pose.CLIPS}) == len(pose.CLIPS), "two clips, one action"
    for c in pose.CLIPS:
        assert c.lo >= 1 and c.hi >= c.lo, c.id
        assert c.span == c.hi - c.lo + 1
        assert abs(c.seconds - c.span / pose.FPS) < 1e-9
        assert c.id != pose.REST, "a clip cannot be called rest; rest means no clip"


def test_the_schema_offers_exactly_the_clips_the_table_knows():
    """Two lists of the same thing is one list that rots. `model.action`'s enum IS this
    table, so a clip added here is selectable from the CLI and the tuner the same minute."""
    assert ac.ENUMS["model.action"] is pose.ACTION_CHOICES
    assert list(pose.ACTION_CHOICES) == [pose.REST] + [c.id for c in pose.CLIPS]
    assert ac.SCHEMA["model.action"][1] == pose.REST, "the schema must default to no pose"
    for name in pose.ACTION_CHOICES:
        ac.resolve({"model": {"action": name}}, env={})          # would raise on a bad enum


def test_an_action_the_table_does_not_know_is_fatal_not_silent():
    """A misspelled clip that rendered the rest shark would be the worst outcome: the sheet
    looks plausible and the footer names a pose that never happened."""
    import pytest
    with pytest.raises(ac.ConfigError) as exc:
        ac.resolve({"model": {"action": "SWIM_FASTT"}}, env={})
    assert "SWIM_FAST" in str(exc.value)


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


def test_the_table_digest_moves_for_a_range_and_not_for_a_comment():
    """It is a label for reports, so it has to track what the table CLAIMS about the model
    and ignore how the claim is worded -- a re-worded note must not look like a new table."""
    before = pose.table_digest()
    reworded = pose.Clip("SWIM_FAST", "ArmatureAction.002", 1, 20, "SPINE", "different prose")
    moved = pose.Clip("SWIM_FAST", "ArmatureAction.002", 1, 21, "SPINE", "x")
    original = pose.CLIPS
    try:
        pose.CLIPS = (reworded,) + original[1:]
        assert pose.table_digest() == before
        pose.CLIPS = (moved,) + original[1:]
        assert pose.table_digest() != before
    finally:
        pose.CLIPS = original
    assert pose.table_digest() == before


def test_pose_imports_no_sibling_and_needs_no_blender():
    """artconfig imports pose (for the action enum), so pose importing artconfig would be a
    cycle -- and `bpy` in here would make the schema unloadable outside Blender."""
    source = (pose.__file__ and open(pose.__file__).read()) or ""
    body = "\n".join(line for line in source.splitlines()
                     if line.startswith(("import ", "from ")))
    assert "bpy" not in body and "mathutils" not in body
    assert "render" not in body, "pose.py must not import a sibling; artconfig imports IT"


# ------------------------------------------------------------------------ phase lock

import math  # noqa: E402

#: SWIM_FAST as MEASURED off the bought model (render_jamal's own sampler, 2026-09-23):
#: per-joint lag in frames of a 20-frame cycle and fundamental amplitude in degrees.
MEASURED_LAGS = [0.00, 1.50, 2.99, 4.49, 5.49, 6.99, 8.50, 10.00]
MEASURED_AMPS = [2.99, 1.52, 3.75, 4.56, 8.09, 10.54, 8.26, 10.82]


def _travelling(lags, amps, span, phi=0.7, t0=0.0):
    """One cycle of a wave that reaches joint i `lags[i]` frames after the first."""
    return [[math.radians(a) * math.cos(2 * math.pi * (k + t0 - lag) / span + phi)
             for k in range(span)] for a, lag in zip(amps, lags)]


def test_fundamental_reads_back_the_amplitude_and_phase_it_was_given():
    for n in (20, 40, 78):
        sig = [1.7 * math.cos(2 * math.pi * k / n + 0.9) + 0.3 for k in range(n)]
        amp, ph = pose.fundamental(sig)
        assert abs(amp - 1.7) < 1e-9 and abs(ph - 0.9) < 1e-9, n     # the DC is not in it
    assert pose.fundamental([]) == (0.0, 0.0)


def test_wave_lags_recovers_the_measured_swim():
    for span in (20, 40, 78):
        scale = span / 20.0
        lags = [lag * scale for lag in MEASURED_LAGS]
        got = pose.wave_lags(_travelling(lags, MEASURED_AMPS, span), span)
        assert all(abs(g - w) < 1e-6 for g, w in zip(got, lags)), (span, got)


def test_wave_lags_survive_the_atan2_cut_wherever_the_cycle_starts():
    """The neighbour-step wrap is the line that decides the answer ON THE REAL RIG: SPINE_01's
    fundamental phase sits right on atan2's +-pi cut (MEASURED -3.063 then +2.749 for
    SPINE_02 on FAST, -3.142 on MEDIUM, +3.139 on SLOW), so the raw first step comes out
    -18.5 frames instead of +1.5 and every lag behind it is garbage. A synthetic wave at one
    comfortable phase never crosses the cut and cannot catch that -- so sweep the start phase
    round the whole circle, the cut included."""
    for i in range(64):
        phi = -math.pi + 2 * math.pi * i / 64
        for span in (20, 40, 78):
            lags = [lag * span / 20.0 for lag in MEASURED_LAGS]
            got = pose.wave_lags(_travelling(lags, MEASURED_AMPS, span, phi=phi), span)
            assert all(abs(g - w) < 1e-6 for g, w in zip(got, lags)), (phi, span, got)


def test_the_tail_at_exactly_half_a_cycle_is_not_a_coin_flip():
    """Nose-to-tail on these clips is EXACTLY half a period, so the tail's lag is +10 or -10
    depending on which side of the wrap float noise lands. Wrapped per joint, that flips the
    tail's offset by a whole half-cycle and the lock pulls it to the wrong side. Unwrapped
    down the chain it cannot: neighbour steps are 1.0-1.5 frames."""
    for nudge in (-1e-7, 0.0, 1e-7):
        lags = MEASURED_LAGS[:-1] + [10.0 + nudge]
        got = pose.wave_lags(_travelling(lags, MEASURED_AMPS, 20), 20)
        assert abs(got[-1] - (10.0 + nudge)) < 1e-6, (nudge, got)


def test_a_joint_that_does_not_move_inherits_its_neighbours_lag():
    """No swing, no phase worth reading -- and a garbage phase would shift every joint
    behind it, because the lags accumulate down the chain."""
    sig = _travelling([0.0, 1.5, 3.0], [5.0, 5.0, 5.0], 20)
    sig[1] = [0.0] * 20
    got = pose.wave_lags(sig, 20)
    assert got[1] == got[0] == 0.0
    assert abs(got[2] - 3.0) < 1e-6


def test_lock_offsets_hold_the_tail_still_and_pull_the_rest_in():
    assert pose.lock_offsets(MEASURED_LAGS, 0.0) == [0.0] * 8
    full = pose.lock_offsets(MEASURED_LAGS, 1.0)
    assert full[-1] == 0.0 and str(full[-1]) == "0.0", "the tail holds; and no -0.0 in a log"
    assert abs(full[0] + 10.0) < 1e-9, "the nose is sampled half a cycle EARLIER"
    half = pose.lock_offsets(MEASURED_LAGS, 0.5)
    assert all(abs(h - f / 2) < 1e-12 for h, f in zip(half, full))
    assert pose.lock_offsets([], 1.0) == []


def test_lock_one_turns_the_travelling_wave_into_a_standing_one():
    """THE property, end to end: play each joint from its offset and every joint's
    fundamental lands on the tail's phase. Lock 0.5 lands them halfway."""
    span = 20
    offsets = pose.lock_offsets(MEASURED_LAGS, 1.0)
    locked = [_travelling([lag], [amp], span, t0=off)[0]
              for lag, amp, off in zip(MEASURED_LAGS, MEASURED_AMPS, offsets)]
    assert all(abs(lag) < 1e-6 for lag in pose.wave_lags(locked, span)), \
        pose.wave_lags(locked, span)
    offsets = pose.lock_offsets(MEASURED_LAGS, 0.5)
    halfway = [_travelling([lag], [amp], span, t0=off)[0]
               for lag, amp, off in zip(MEASURED_LAGS, MEASURED_AMPS, offsets)]
    got = pose.wave_lags(halfway, span)
    assert all(abs(g - lag / 2) < 1e-6 for g, lag in zip(got, MEASURED_LAGS)), got


def test_wrap_time_keeps_a_shifted_joint_inside_one_cycle():
    assert pose.wrap_time(20.5, 1, 20) == 20.5, "the seam interval (hi, hi+1) is IN the cycle"
    assert pose.wrap_time(21.0, 1, 20) == 1.0
    assert pose.wrap_time(-9.0, 1, 20) == 11.0          # frame 1 minus ten frames
    assert pose.wrap_time(1.0 - 10.0, 1, 20) == 11.0
    for t in (-37.25, -1.0, 0.0, 1.0, 19.99, 20.0, 20.999, 41.5):
        w = pose.wrap_time(t, 1, 20)
        assert 1 <= w < 21 and abs(((w - t) / 20) - round((w - t) / 20)) < 1e-9, t


def test_only_the_swims_carry_a_wave_to_lock():
    waves = {c.id for c in pose.CLIPS if c.wave}
    assert waves == {"SWIM_FAST", "SWIM_MEDIUM", "SWIM_SLOW"}
    assert pose.LOCK_MIN == 0.0 and pose.LOCK_MAX == 1.0
