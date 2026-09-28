"""G.6's mixer without Factorio: synthetic events.jsonl / frames.json / track.jsonl and a FAKE
install of synthetic Ogg files at the catalog's own paths.

Two tiers. The planner (onset mapping through every segment kind, aggregation in source time,
the time-lapse cap, pan, loops, the gate, input refusals, the missing-.ogg error) is pure Python
and runs everywhere. The render tests need ffmpeg + ffprobe ($FFMPEG / $FFPROBE, default the
Homebrew keg) and SKIP without them - CI has neither - and they measure the ENCODED .m4a: an
onset is found by its transient in the decoded audio, not read back from the plan.

The fake sounds are chosen so a measurement cannot pass by accident: a transient-over-body burst
at sample 0 (a thud, a biter...), the same burst 7 ticks into its file for the legs (so the
preroll is what puts it on the foot's frame), and a silent bed unless a test wants a tone.
"""

from __future__ import annotations

import array
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pytest

from video import mix

TOOLS = pathlib.Path(__file__).resolve().parents[1]
# The mixer's own resolver, so these tests find ffmpeg exactly where a build would (the first
# cut hard-coded the Homebrew path: with ffmpeg only on PATH the build tests ran and every
# render test here skipped - MEASURED by the review).
FFMPEG = mix.find_ffmpeg() or mix.FFMPEG_DEFAULT
FFPROBE = mix._ffprobe_for(FFMPEG)
HAVE_FFMPEG = shutil.which(FFMPEG) is not None and shutil.which(FFPROBE) is not None
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason=f"no ffmpeg/ffprobe at {FFMPEG}")

RATE = mix.RATE
SPF = RATE // 60  # 800 samples a frame


# ---------------------------------------------------------------------------------------------
# Synthetic takes


def cut_json(specs: Sequence[tuple], fps: int = 60) -> dict[str, object]:
    """frames.json from segment specs, with timeline.py's arithmetic (frame k of a span shows
    from + floor(k * speed); half-open ranges; a freeze is [at, at+1); a card owns none):
    ("span", from, to, speed[, audio]) | ("freeze", at, frames[, audio]) | ("card", frames)."""
    frames: list[dict[str, object]] = []
    segments: list[dict[str, object]] = []
    for i, s in enumerate(specs):
        f0 = len(frames)
        if s[0] == "span":
            a, b, speed = s[1], s[2], s[3]
            n = math.ceil((b - a) / speed)
            frames += [{"src": a + math.floor(k * speed), "seg": i} for k in range(n)]
            seg = {"kind": "span", "speed": speed, "from": a, "to": b,
                   "audio": s[4] if len(s) > 4 else "live"}
        elif s[0] == "freeze":
            frames += [{"src": s[1], "seg": i}] * s[2]
            seg = {"kind": "freeze", "speed": 0.0, "from": s[1], "to": s[1] + 1,
                   "audio": s[3] if len(s) > 3 else "live"}
        else:
            frames += [{"src": None, "seg": i}] * s[1]
            seg = {"kind": "card", "speed": 0.0, "from": 0, "to": 0, "audio": "mute"}
        segments.append({"index": i, "tag": None, "out": [f0, len(frames)], **seg})
    return {"fps": fps, "frames": frames, "segments": segments, "overlays": []}


def cut_of(specs: Sequence[tuple]) -> mix.Cut:
    d = cut_json(specs)
    frames, segs = d["frames"], d["segments"]
    assert isinstance(frames, list) and isinstance(segs, list)
    return mix.Cut(60, [f["src"] for f in frames], [f["seg"] for f in frames],
                   {s["index"]: mix.Seg(s["index"], s["kind"], s["speed"], s["from"], s["to"],
                                        s["audio"]) for s in segs})


def ev(tick: int, kind: str, line: int = 0, *, x: float | None = None, y: float | None = None,
       name: str | None = None) -> mix.Event:
    return mix.Event(line or tick, tick, kind, x, y, name)


def flat_track(last: int, cam: tuple[float, float] = (0.0, 0.0), zoom: float = 1.0,
               pos: tuple[float, float] = (0.0, 1.5)) -> mix.Track:
    return mix.Track({t: mix.View(cam, zoom, pos) for t in range(last + 1)})


#: File lengths for the pure planner: every one-shot 0.25 s unless a test says otherwise.
def lengths(overrides: Mapping[str, float] | None = None) -> Callable[[str], float]:
    table = dict(overrides or {})

    def seconds(f: str) -> float:
        for key, v in table.items():
            if key in f:
                return v
        return 0.25

    return seconds


def write_take(root: pathlib.Path, events: Sequence[Mapping[str, Any]], cut: Mapping[str, Any],
               track: Sequence[Mapping[str, Any]] | None = None) -> tuple[pathlib.Path, ...]:
    root.mkdir(parents=True, exist_ok=True)
    e, f, t = root / "events.jsonl", root / "frames.json", root / "track.jsonl"
    e.write_text("".join(json.dumps(x) + "\n" for x in events))
    f.write_text(json.dumps(cut))
    if track is None:
        last = max(int(x["tick"]) for x in events) + 20
        track = [{"tick": k, "cam": [0, 0], "zoom": 1.0, "body": "jamaltron", "pos": [0, 1.5],
                  "lift": [0, -1.5]} for k in range(last)]
    t.write_text("".join(json.dumps(x) + "\n" for x in track))
    return e, f, t


# ---------------------------------------------------------------------------------------------
# The planner, pure Python

#: The onset cut: every segment kind, a mute freeze, a replay and an end card.
ONSET_CUT = [
    ("span", 0, 120, 1.0),          # out   0..119
    ("span", 120, 180, 0.5),        # out 120..239, each source frame twice
    ("span", 180, 480, 5.0),        # out 240..299, every 5th source frame
    ("freeze", 480, 30),            # out 300..329, live
    ("span", 481, 540, 1.0),        # out 330..388
    ("freeze", 540, 30, "mute"),    # out 389..418
    ("span", 540, 600, 1.0),        # out 419..478
    ("span", 60, 90, 1.0),          # out 479..508, a replay of 60..89
    ("card", 30),                   # out 509..538
]
#: source tick -> the output frames the contract's rule puts it on.
ONSETS = {30: [30], 75: [75, 494], 130: [140], 203: [245], 480: [300], 500: [349],
          540: [419], 560: [439], 599: [478], 600: [], 90: [90], 700: []}
#: Planner-only (the render tests thud on every ONSETS tick, and a second thud on frame 300
#: would change what they measure): past the 5x span's last sample (475), an event plays where
#: the flow resumes - the live freeze at 480.
TAIL_ONSETS = {478: [300], 476: [300]}


@pytest.mark.parametrize("tick", sorted({**ONSETS, **TAIL_ONSETS}))
def test_an_event_maps_to_the_first_frame_of_each_live_segment_that_shows_it(tick):
    assert cut_of(ONSET_CUT).onsets(tick) == {**ONSETS, **TAIL_ONSETS}[tick]


def test_a_live_freeze_on_a_tick_the_span_just_showed_does_not_flam():
    # The span [100, 131) shows 130 at out 30; the freeze holds 130 right after. The contract's
    # rule alone would play the event at out 30 AND 31.
    cut = cut_of([("span", 100, 131, 1.0), ("freeze", 130, 20)])
    assert cut.onsets(130) == [30]
    # ...but a freeze on a tick the span never reached does play it, on its first held frame.
    cut = cut_of([("span", 100, 130, 1.0), ("freeze", 130, 20)])
    assert cut.onsets(130) == [30]


def test_a_time_lapse_tail_plays_where_the_flow_resumes_never_after_a_jump_cut():
    # 5x [2196, 3424) samples 2196..3421: 3422 and 3423 have no frame >= them in it.
    cut = cut_of([("span", 2100, 2196, 1.0), ("span", 2196, 3424, 5.0),
                  ("span", 3424, 3500, 1.0)])
    first_1x = 96 + 246
    assert cut.onsets(3421) == [first_1x - 1] and cut.onsets(3422) == [first_1x]
    assert cut.onsets(3423) == [first_1x]
    # a jump cut forward after the time-lapse: the event is not dragged 500 ticks late
    cut = cut_of([("span", 2196, 3424, 5.0), ("span", 3924, 4000, 1.0)])
    assert cut.onsets(3422) == []


def test_after_a_mute_freeze_the_event_plays_where_the_flow_resumes():
    # Reached during a MUTE freeze = never heard, so the resumed span plays it.
    cut = cut_of([("span", 100, 130, 1.0), ("freeze", 130, 20, "mute"), ("span", 130, 160, 1.0)])
    assert cut.onsets(130) == [50]


def test_mute_segments_and_cards_are_the_gate():
    cut = cut_of(ONSET_CUT)
    assert cut.silent_regions() == [(389, 419), (509, 539)]
    p = mix.plan([ev(30, "thud")], cut, flat_track(700), lengths())
    assert p.gate == [(389 * SPF, 419 * SPF), (509 * SPF, 539 * SPF)]
    assert cut.samples == 539 * SPF


def test_the_thud_is_placed_sample_exactly_and_nothing_else_is_invented():
    events = [ev(10, "capture_start"), ev(40, "takeoff", x=0, y=0), ev(55, "apex"),
              ev(70, "landing", x=8, y=0), ev(70, "thud", x=8, y=0), ev(71, "line", 71),
              ev(90, "repair"), ev(95, "break", x=0, y=0), ev(95, "thud", 96, x=0, y=0),
              ev(99, "biter_spawn", name="small-biter"), ev(110, "capture_end")]
    p = mix.plan(events, cut_of([("span", 0, 120, 1.0)]), flat_track(120), lengths())
    assert [(q.key, q.at) for q in p.placed] == [("jamaltron-landing-thud", 70 * SPF),
                                                 ("jamaltron-landing-thud", 95 * SPF)]
    assert not p.warnings
    for silent in ("takeoff", "apex", "landing", "line", "repair", "break", "biter_spawn"):
        assert p.silent[silent] == 1, silent


def test_every_sound_plays_at_its_prototype_volume_and_the_graph_carries_it():
    """The prototype's volume (and the legs' readable lift) must reach the pan coefficients:
    a centred sound's coefficient IS its volume. Found missing once, by measuring a mix of the
    real sounds (every sound played at 1.0, the legs 11 dB hot)."""
    events = [ev(20, "thud"), ev(40, "footfall", x=0, y=0), ev(60, "walk_start", x=0, y=0),
              ev(90, "walk_stop", x=0, y=0), ev(100, "biter_died", x=0, y=0, name="small-biter")]
    cut = cut_of([("span", 0, 200, 1.0)])
    p = mix.plan(events, cut, mix.Track({}), lengths())
    want = {"jamaltron-landing-thud": 0.7, "spidertron-leg": mix.LEG_VOLUME,
            "spidertron-activate": 0.5, "spidertron-vox": 0.35, "spidertron-deactivate": 0.5,
            "small-biter/dying": 0.5, "small-biter/gore": 0.7}
    assert {q.key: round(10 ** (q.gain_db / 20), 6) for q in p.placed} == want
    _, script = mix.graph(p, pathlib.Path("/data"))
    for k, q in enumerate(p.placed):
        line = next(x for x in script.splitlines() if x.startswith(f"[s{k}]"))
        assert f"c0={want[q.key]:.6f}*c0|c1={want[q.key]:.6f}*c1" in line, line
    assert f"volume={mix.BED.volume}," in script


def test_a_take_without_thud_events_thuds_on_landing_and_break():
    p = mix.plan([ev(20, "landing", x=0, y=0), ev(50, "break", x=0, y=0)],
                 cut_of([("span", 0, 120, 1.0)]), flat_track(120), lengths())
    assert [q.at for q in p.placed] == [20 * SPF, 50 * SPF]
    assert any("no thud events" in w for w in p.warnings)


def test_the_leg_starts_early_so_its_peak_lands_on_the_foot():
    p = mix.plan([ev(100, "footfall", x=1, y=0), ev(3, "footfall", x=1, y=0)],
                 cut_of([("span", 0, 200, 1.0)]), flat_track(200), lengths())
    legs = {q.src_tick: q for q in p.placed}
    assert legs[100].at == (100 - mix.LEG_PREROLL) * SPF and legs[100].head == 0
    # A preroll that falls before the cut's start trims the file's head instead.
    assert legs[3].at == 0 and legs[3].head == (mix.LEG_PREROLL - 3) * SPF
    assert legs[3].length == round(0.25 * RATE) - legs[3].head


def test_simultaneous_feet_never_share_a_file_and_the_pick_is_stable():
    feet = [ev(40, "footfall", 40 + k, x=k - 1.5, y=0) for k in range(4)]
    cut, trk = cut_of([("span", 0, 100, 1.0)]), flat_track(100)
    a = mix.plan(feet, cut, trk, lengths())
    b = mix.plan(list(reversed(feet)), cut, trk, lengths())
    files = [q.file for q in a.placed]
    assert len(set(files)) == 4, files
    assert sorted(files) == sorted(q.file for q in b.placed)
    assert a.placed == mix.plan(feet, cut, trk, lengths()).placed


def test_aggregation_runs_in_source_time_and_keeps_the_closest():
    # G.1's probe: 6 small biters died on one tick, 2 more 4 ticks later. dying max 3, gore
    # max 1, both still sounding 4 ticks on - so 3 deaths and 1 gore, the closest ones.
    deaths = [ev(864, "biter_died", 10 + k, x=float(10 + k), y=0, name="small-biter")
              for k in range(6)]
    deaths += [ev(868, "biter_died", 20 + k, x=1.0 + k, y=0, name="small-biter")
               for k in range(2)]
    p = mix.plan(deaths, cut_of([("span", 800, 1000, 1.0)]), flat_track(1000),
                 lengths({"biter-death": 0.8, "small-gore": 0.8}))
    dying = [q for q in p.placed if q.key == "small-biter/dying"]
    gore = [q for q in p.placed if q.key == "small-biter/gore"]
    assert len(dying) == 3 and len(gore) == 1
    assert p.dropped_aggregation == {"small-biter/dying": 5, "small-biter/gore": 7}
    # The engine's default priority is "closest": x = 10, 11, 12 of the first six.
    kept = sorted(q.pan for q in dying)
    assert kept == sorted(mix.spatial(mix.View((0, 0), 1.0, None), x, 0)[1]
                          for x in (10.0, 11.0, 12.0))


def test_aggregation_decides_before_mapping_so_slow_mo_and_a_replay_do_not_change_it():
    # Four thuds 5 ticks apart (thud max 3, 1 s long): the 4th is dropped in SOURCE time.
    thuds = [ev(100 + 5 * k, "thud", x=0, y=0) for k in range(4)]
    for speed in (1.0, 0.5):
        p = mix.plan(thuds, cut_of([("span", 50, 200, speed), ("span", 90, 130, 1.0)]),
                     flat_track(200), lengths({"cargo-pod": 1.0}))
        kept = sorted({q.src_tick for q in p.placed if q.src_tick is not None})
        assert kept == [100, 105, 110], speed
        assert p.dropped_aggregation == {"jamaltron-landing-thud": 1}
        # The replay plays the three kept ones again.
        assert len(p.placed) == 6


def test_a_time_lapse_is_never_denser_than_the_game_played_it():
    # A repairing event every 30 ticks, 1.3 s files: at 1x at most 3 sound at once (78 ticks
    # long, 30 apart). At 5x they arrive every 6 frames and would stack 13 deep.
    events = [ev(1000, "repair_start")] + [ev(1000 + 30 * k, "repairing") for k in range(40)]
    events.append(ev(2170, "repair_full"))
    p = mix.plan(events, cut_of([("span", 1000, 2200, 5.0)]), flat_track(2200),
                 lengths({"robot-repair": 1.3}))
    starts = sorted(q.at for q in p.placed)
    worst = max(sum(1 for a in starts if a <= t < a + round(1.3 * RATE)) for t in starts)
    assert worst <= 3
    assert p.dropped_timelapse["robot-repair"] > 20
    # ...and evenly: every 5th of an event every 6 output frames is one every 30 frames - the
    # game's own 30-tick spacing. The first cut let four start 0.1 s apart, then ~1.35 s of
    # nothing (MEASURED on the first master's mix plan).
    assert {b - a for a, b in zip(starts, starts[1:])} == {30 * SPF}
    # The same events at 1x keep every one.
    p1 = mix.plan(events, cut_of([("span", 1000, 2200, 1.0)]), flat_track(2200),
                  lengths({"robot-repair": 1.3}))
    assert len(p1.placed) == 40 and not p1.dropped_timelapse


def test_repairing_outside_the_repair_window_is_silent():
    events = [ev(100, "repairing"), ev(200, "repair_start"), ev(230, "repairing"),
              ev(300, "repair_full"), ev(330, "repairing")]
    p = mix.plan(events, cut_of([("span", 0, 400, 1.0)]), flat_track(400), lengths())
    assert [q.src_tick for q in p.placed] == [230]


def test_equal_power_pan_and_gentle_attenuation():
    gl, gr = mix.pan_gains(0.0)
    assert gl == pytest.approx(1.0) and gr == pytest.approx(1.0)
    for p in (-1.0, -0.4, 0.3, 1.0):
        gl, gr = mix.pan_gains(p)
        assert gl * gl + gr * gr == pytest.approx(2.0)  # equal power: constant sum of squares
    assert mix.pan_gains(-1.0)[1] == pytest.approx(0.0, abs=1e-12)
    view = mix.View((10.0, 0.0), 2.0, None)  # zoom 2: half the screen is 960/64 = 15 tiles
    assert mix.spatial(view, 25.0, 0.0) == pytest.approx((-3.0, 1.0))  # the right edge
    assert mix.spatial(view, 10.0 - 7.5, 0.0) == pytest.approx((-1.5, -0.5))
    assert mix.spatial(view, 500.0, 0.0) == pytest.approx((-mix.ATTEN_MAX_DB, 1.0))
    assert mix.spatial(None, 1.0, 1.0) == (0.0, 0.0)
    assert mix.spatial(view, None, None) == (0.0, 0.0)


def test_the_flamethrower_is_begin_then_middle_looped_then_end():
    # A burst from 100 to 400 through a 1x -> 0.5x boundary: ONE continuous middle.
    events = [ev(100, "fire_start", x=0, y=0), ev(400, "fire_stop", x=0, y=0)]
    cut = cut_of([("span", 0, 200, 1.0), ("span", 200, 500, 0.5)])
    p = mix.plan(events, cut, flat_track(500), lengths({"flamethrower-start": 0.323}))
    by = {q.key: q for q in p.placed}
    assert set(by) == {"flamethrower-start", "flamethrower-mid", "flamethrower-end"}
    assert by["flamethrower-start"].at == 100 * SPF
    mid = by["flamethrower-mid"]
    assert mid.loop and mid.at == 100 * SPF + round(0.323 * RATE)
    stop = 200 + 2 * (400 - 200)  # out frame of source 400
    assert by["flamethrower-end"].at == stop * SPF
    assert mid.at + mid.length == stop * SPF + mix.MID_TAIL * SPF
    assert all(q.duck for q in p.placed)
    assert p.ducks == [pytest.approx((100 * SPF / RATE, (stop * SPF + round(0.25 * RATE)) / RATE))]


def test_a_burst_shorter_than_its_begin_never_starts_the_middle():
    p = mix.plan([ev(100, "fire_start"), ev(110, "fire_stop")],
                 cut_of([("span", 0, 200, 1.0)]), flat_track(200),
                 lengths({"flamethrower-start": 0.323}))
    assert sorted(q.key for q in p.placed) == ["flamethrower-end", "flamethrower-start"]


def test_the_vox_loops_while_he_walks_and_a_cut_restarts_it():
    events = [ev(100, "walk_start", x=0, y=0), ev(300, "walk_stop", x=0, y=0)]
    cut = cut_of([("span", 0, 200, 1.0), ("freeze", 199, 30, "mute"), ("span", 200, 400, 1.0)])
    p = mix.plan(events, cut, flat_track(400), lengths())
    vox = [q for q in p.placed if q.key == "spidertron-vox"]
    assert [(q.at // SPF, q.length // SPF) for q in vox] == [
        (100, 100 + mix.LOOP_FADE_OUT), (230, 100 + mix.LOOP_FADE_OUT)]
    assert all(q.fade_in == mix.LOOP_FADE_IN * SPF for q in vox)
    assert {q.key for q in p.placed} == {"spidertron-activate", "spidertron-vox",
                                         "spidertron-deactivate"}


def test_biters_play_their_own_units_sounds_and_unknown_units_warn():
    events = [ev(10, "biter_attack", x=0, y=0, name="medium-biter"),
              ev(40, "biter_died", x=0, y=0, name="big-biter"),
              ev(70, "biter_died", x=0, y=0, name="small-spitter")]
    p = mix.plan(events, cut_of([("span", 0, 120, 1.0)]), flat_track(120), lengths())
    files = sorted(q.file.rsplit("/", 1)[1].rsplit("-", 1)[0] for q in p.placed)
    assert files == ["big-gore", "biter-death-big", "biter-roar-mid"]
    assert any("small-spitter" in w for w in p.warnings)


def test_the_bed_ducks_under_merged_thud_windows():
    events = [ev(100, "thud", x=0, y=0), ev(110, "thud", 111, x=0, y=0),
              ev(400, "thud", x=0, y=0)]
    p = mix.plan(events, cut_of([("span", 0, 600, 1.0)]), flat_track(600),
                 lengths({"cargo-pod": 1.0}))
    assert p.ducks == [pytest.approx((100 / 60, 110 / 60 + 1.0)),
                       pytest.approx((400 / 60, 400 / 60 + 1.0))]


def test_the_door_never_opens_before_the_packs_go_in():
    """DOOR_OPEN's INFERRED lead is -16; a bot out on the cue's own tick would have the door
    open 16 ticks before the director loaded the packs (MEASURED: 15 early on the first
    master). The lead still applies to a bot that leaves later."""
    events = [ev(500, "repair_cue"), ev(500, "bot_out", x=6, y=0), ev(900, "bot_out", x=6, y=0)]
    p = mix.plan(events, cut_of([("span", 400, 1000, 1.0)]), flat_track(1000), lengths())
    opens = sorted(q.src_tick for q in p.placed if q.key == "roboport-door-open")
    assert opens == [500, 900 + mix.DOOR_OPEN.lead]


def test_a_thud_the_cut_swallows_inside_its_source_range_is_a_warning():
    # The break thud at 150 inside a MUTE freeze's stretch: legal, but said out loud.
    cut = cut_of([("span", 100, 150, 1.0), ("freeze", 150, 30, "mute"), ("span", 151, 200, 1.0)])
    p = mix.plan([ev(150, "thud", x=0, y=0), ev(400, "thud", x=0, y=0)], cut, flat_track(400),
                 lengths())
    assert p.unplaced["jamaltron-landing-thud"] == 2
    warned = [w for w in p.warnings if "jamaltron-landing-thud" in w]
    # only the one inside 100..199; the thud after the cut's end is simply not in the video
    assert len(warned) == 1 and "source tick 150" in warned[0] and "mute" in warned[0]


def test_the_mixer_finds_ffmpeg_on_path_like_the_picture_does(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "ffmpeg"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.delenv("FFMPEG", raising=False)
    monkeypatch.setattr(mix, "FFMPEG_DEFAULT", str(tmp_path / "no-brew" / "ffmpeg"))
    monkeypatch.setenv("PATH", str(bin_dir))
    assert mix.find_ffmpeg() == str(fake)
    monkeypatch.setenv("FACTORIO_DATA", str(tmp_path))
    assert mix.default_data_dir() == tmp_path


def test_the_roboport_door_opens_before_the_bot_and_closes_after_at_the_games_speeds():
    p = mix.plan([ev(500, "bot_out", x=6, y=0)], cut_of([("span", 400, 600, 1.0)]),
                 flat_track(600), lengths())
    by = {q.key: q for q in p.placed}
    assert by["roboport-door-open"].src_tick == 500 + mix.DOOR_OPEN.lead
    assert by["roboport-door-close"].src_tick == 500 + mix.DOOR_CLOSE.lead
    for q in by.values():
        assert 1.0 <= q.speed <= 1.5
        assert q.length == round(0.25 * RATE / q.speed)


def test_every_catalogued_file_is_in_the_real_install_when_there_is_one():
    if not mix.DATA_DIR.is_dir():
        pytest.skip("no Factorio install at " + str(mix.DATA_DIR))
    missing = [f for f in mix.catalog_files() if not (mix.DATA_DIR / f).is_file()]
    assert not missing, missing


BAD_CUTS = [
    ({"fps": 7}, "fps 7 is not a whole number"),
    ({"fps": 0}, "fps wants a whole number above 0"),
    ({"frames": []}, "frames wants a non-empty list"),
    ({"frames": [{"src": 1, "seg": 9}]}, "frames[0].seg 9 names no segment"),
    ({"frames": [{"src": "x", "seg": 0}]}, "frames[0].src wants a tick or null"),
    ({"segments": [{"index": 0, "kind": "wipe", "speed": 1}]}, "kind is span, freeze or card"),
    ({"segments": [{"index": 0, "kind": "span", "speed": 1, "audio": "loud"}]},
     "audio is live or mute"),
]


@pytest.mark.parametrize("patch,why", BAD_CUTS, ids=[w for _, w in BAD_CUTS])
def test_a_bad_frames_json_is_refused_by_name(tmp_path, patch, why):
    d = cut_json([("span", 0, 10, 1.0)])
    d.update(patch)
    (tmp_path / "frames.json").write_text(json.dumps(d))
    with pytest.raises(mix.MixError, match=re.escape(why)):
        mix.load_cut(tmp_path / "frames.json")


@pytest.mark.parametrize("line,why", [
    ('{"tick": 1.5, "ev": "thud"}', "events.jsonl:2: tick is not a whole number"),
    ('{"tick": 3}', "events.jsonl:2: ev is not a name"),
    ("{nope", "events.jsonl:2: not JSON"),
    ("[1, 2]", "events.jsonl:2: not a JSON object"),
])
def test_a_bad_event_line_is_refused_with_its_line_number(tmp_path, line, why):
    (tmp_path / "events.jsonl").write_text('{"tick": 1, "ev": "thud"}\n' + line + "\n")
    with pytest.raises(mix.MixError, match=why):
        mix.load_events(tmp_path / "events.jsonl")


def test_a_bad_track_line_is_refused(tmp_path):
    (tmp_path / "track.jsonl").write_text('{"tick": 1, "cam": [0, 0], "zoom": 0}\n')
    with pytest.raises(mix.MixError, match="track.jsonl:1: a track line wants"):
        mix.load_track(tmp_path / "track.jsonl")


def test_a_missing_ogg_is_a_clear_error_before_ffmpeg_runs(tmp_path):
    """No ffmpeg needed: the install is checked before anything launches, and the message
    names every missing file."""
    data = tmp_path / "data"
    for name in mix.catalog_files():
        if "cargo-pod-ground-land-2" not in name:
            (data / name).parent.mkdir(parents=True, exist_ok=True)
            (data / name).write_bytes(b"OggS")
    e, f, t = write_take(tmp_path / "take", [{"tick": 5, "ev": "thud", "x": 0, "y": 0}],
                         cut_json([("span", 0, 60, 1.0)]))
    with pytest.raises(mix.MixError) as err:
        mix.render(e, f, t, tmp_path / "out.m4a", data_dir=data, ffmpeg="/no/such/ffmpeg")
    assert "1 sound file(s) missing" in str(err.value)
    assert "base/sound/procession/cargo-pod-ground-land-2.ogg" in str(err.value)
    assert not (tmp_path / "out.m4a").exists()
    with pytest.raises(mix.MixError, match="is not a directory"):
        mix.render(e, f, t, tmp_path / "out.m4a", data_dir=tmp_path / "nope")


# ---------------------------------------------------------------------------------------------
# Rendering through ffmpeg, measured off the encoded file


def _ff(*args: str) -> None:
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="session")
def masters(tmp_path_factory) -> dict[str, pathlib.Path]:
    """The synthetic sounds, 44.1 kHz stereo Ogg FLAC like the game's (lossless, so a
    transient is where it was put). The tone and hum are whole cycles per file so their loops
    are phase-continuous."""
    if not HAVE_FFMPEG:
        pytest.skip("no ffmpeg")
    d = tmp_path_factory.mktemp("masters")
    # A thud's shape: a 1 ms transient at 0.9 over a 100 ms body at 0.2 (1 kHz), so a limiter
    # can shave the peak without taking the loudness with it, the way it treats a real thud.
    burst = "aevalsrc='if(lt(t,0.001),0.9,0.2)*sin(2*PI*1000*t)':s=44100:d=0.1"
    st = "aformat=channel_layouts=stereo"
    out = {
        "burst": (f"{burst},apad=whole_dur=0.25,{st}"),
        "burst7": (f"{burst},adelay=delays={7 * 735}S:all=1,apad=whole_dur=0.4,{st}"),
        "silence": "anullsrc=r=44100:cl=stereo:d=0.5",
        "tone": f"sine=f=440:r=44100:d=2,volume=2,{st}",
        "hum": f"sine=f=220:r=44100:d=1,volume=2,{st}",
    }
    paths = {}
    for name, src in out.items():
        paths[name] = d / f"{name}.ogg"
        _ff("-f", "lavfi", "-i", src, "-c:a", "flac", "-f", "ogg", str(paths[name]))
    return paths


def install(root: pathlib.Path, masters: Mapping[str, pathlib.Path],
            pick: Callable[[str], str | None] | None = None) -> pathlib.Path:
    """A fake data/ holding every catalog file as a link to a master: legs are burst7, the
    loops hum, the bed silent, everything else burst - unless `pick` says otherwise."""
    for f in mix.catalog_files():
        choice = pick(f) if pick else None
        if choice is None:
            choice = ("burst7" if "spidertron-leg" in f else "hum" if f.endswith(
                ("spidertron-vox.ogg", "flamethrower-mid.ogg")) else "silence"
                if "world_base_wind" in f else "burst")
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        os.link(masters[choice], root / f)
    return root


def pcm(path: pathlib.Path, channels: int = 1) -> array.array:
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-f", "f32le", "-ac",
                          str(channels), "-ar", str(RATE), "-"], capture_output=True,
                         check=True).stdout
    a = array.array("f")
    a.frombytes(raw)
    return a


def onset(a: array.array, expect: int, window: int = round(0.03 * RATE)) -> int:
    """The first sample over 30% of the window's peak: the transient, as a listener gets it."""
    lo = max(0, expect - window)
    seg = a[lo:expect + window]
    peak = max(abs(x) for x in seg)
    assert peak > 0.01, f"nothing near sample {expect}"
    return lo + next(k for k, x in enumerate(seg) if abs(x) > 0.3 * peak)


def rms_db(a: array.array, lo: int, hi: int) -> float:
    s = sum(x * x for x in a[lo:hi]) / max(1, hi - lo)
    return 10 * math.log10(s) if s > 0 else -200.0


ONSET_EVENTS = [{"tick": t, "ev": "thud", "x": 0, "y": 0} for t in sorted(ONSETS)] + [
    {"tick": 100, "ev": "footfall", "x": 0.5, "y": 0}]


@pytest.fixture(scope="module")
def onset_render(masters, tmp_path_factory):
    root = tmp_path_factory.mktemp("onsets")
    data = install(root / "data", masters)
    e, f, t = write_take(root / "take", ONSET_EVENTS, cut_json(ONSET_CUT))
    rep = mix.render(e, f, t, root / "a.m4a", data_dir=data, ffmpeg=FFMPEG)
    return rep, root, data, (e, f, t)


@needs_ffmpeg
def test_every_onset_lands_within_2_ms_through_every_segment_kind(onset_render):
    rep, root, _, _ = onset_render
    a = pcm(root / "a.m4a")
    expected = sorted({f for fs in ONSETS.values() for f in fs} | {100})  # + the foot
    errors = {f: (onset(a, f * SPF) - f * SPF) / RATE * 1000 for f in expected}
    assert all(abs(ms) <= 2.0 for ms in errors.values()), errors
    assert rep.placed == {"jamaltron-landing-thud": len(expected) - 1, "spidertron-leg": 1}


@needs_ffmpeg
def test_onsets_hold_under_deep_limiting_and_the_ceiling_beats_the_target(onset_render,
                                                                          tmp_path):
    """-12 LUFS from sparse bursts with nothing under them is out of reach: the limiter goes to
    its MAX_LIMIT_DB floor and the true-peak ceiling wins, with a note and a quiet mix. Its
    lookahead must not move anything (alimiter's default latency=0 moves the whole track 5 ms
    late - MEASURED)."""
    _, _, data, (e, f, t) = onset_render
    rep = mix.render(e, f, t, tmp_path / "hot.m4a", data_dir=data, ffmpeg=FFMPEG,
                     target_lufs=-12.0)
    lo = rep.loudness
    assert lo.limiter_ceiling_db == pytest.approx(lo.premaster_tp - mix.MAX_LIMIT_DB)
    assert any(w.startswith("limiter: -12.0 LUFS is out of reach") for w in rep.warnings)
    assert lo.true_peak_dbtp <= mix.TP_TARGET and lo.integrated_lufs < -12.5
    assert not rep.loudness_ok
    a = pcm(tmp_path / "hot.m4a")
    expected = sorted({f for fs in ONSETS.values() for f in fs} | {100})
    errors = {f: (onset(a, f * SPF) - f * SPF) / RATE * 1000 for f in expected}
    assert all(abs(ms) <= 2.0 for ms in errors.values()), errors


@needs_ffmpeg
def test_the_limiter_shaves_peaks_and_the_gain_still_lands_on_target(masters, tmp_path):
    """A bed carries the loudness and the thuds' transients are the peaks - a real mix's shape
    - so the limiter can take the peaks down and the loudness stays reachable."""
    data = install(tmp_path / "data", masters,
                   lambda f: "tone" if "world_base_wind" in f else None)
    events = [{"tick": 60 + 90 * k, "ev": "thud", "x": 0, "y": 0} for k in range(6)]
    e, f, t = write_take(tmp_path / "take", events, cut_json([("span", 0, 600, 1.0)]))
    rep = mix.render(e, f, t, tmp_path / "l.m4a", data_dir=data, ffmpeg=FFMPEG)
    lo = rep.loudness
    assert lo.limiter_ceiling_db is not None and lo.limiter_ceiling_db < lo.premaster_tp - 1
    assert rep.loudness_ok and not rep.warnings, rep.summary()
    assert abs(lo.integrated_lufs + 16) <= 0.2 and lo.true_peak_dbtp <= mix.TP_TARGET


@needs_ffmpeg
def test_the_file_is_aac_lc_48k_stereo_exactly_as_long_as_the_cut(onset_render):
    rep, root, _, _ = onset_render
    probe = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                            "stream=codec_name,profile,sample_rate,channels,duration_ts,"
                            "time_base,bit_rate", "-of", "json", str(root / "a.m4a")],
                           capture_output=True, text=True, check=True)
    st = json.loads(probe.stdout)["streams"]
    assert len(st) == 1
    st = st[0]
    assert (st["codec_name"], st["profile"], st["sample_rate"], st["channels"]) == (
        "aac", "LC", "48000", 2)
    assert st["time_base"] == "1/48000" and int(st["duration_ts"]) == 539 * SPF
    assert len(pcm(root / "a.m4a")) == 539 * SPF  # decoded, too
    assert rep.samples == 539 * SPF and rep.duration_s == pytest.approx(539 / 60, abs=1e-9)


@needs_ffmpeg
def test_two_renders_of_the_same_take_are_byte_identical(onset_render):
    rep, root, data, (e, f, t) = onset_render
    mix.render(e, f, t, root / "b.m4a", data_dir=data, ffmpeg=FFMPEG)
    assert (root / "a.m4a").read_bytes() == (root / "b.m4a").read_bytes()


@needs_ffmpeg
def test_the_master_hits_the_target_linearly_and_reports_what_it_measured(onset_render):
    rep, root, _, _ = onset_render
    lo = rep.loudness
    assert lo.normalization == "linear"
    assert rep.loudness_ok, rep.warnings
    # Measured independently of the report.
    s = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-i", str(root / "a.m4a"), "-af",
                        "ebur128=peak=true:framelog=quiet", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    i = float(s.rsplit("I:", 1)[1].split("LUFS")[0])
    tp = float(s.rsplit("Peak:", 1)[1].split("dBFS")[0])
    assert abs(i - -16.0) <= 0.5 and tp <= mix.TP_TARGET + 0.2
    assert lo.integrated_lufs == pytest.approx(i, abs=0.05)


@needs_ffmpeg
def test_the_bed_ducks_under_the_thud_and_is_gated_in_mute_and_card(masters, tmp_path):
    # A tone for the bed and a SILENT thud: what is left under the thud is the ducked bed.
    data = install(tmp_path / "data", masters,
                   lambda f: "tone" if "world_base_wind" in f else
                   "silence" if "cargo-pod" in f else None)
    cut = cut_json([("span", 0, 300, 1.0), ("freeze", 299, 60, "mute"), ("span", 300, 400, 1.0),
                    ("card", 60)])
    e, f, t = write_take(tmp_path / "take", [{"tick": 150, "ev": "thud", "x": 0, "y": 0}], cut)
    rep = mix.render(e, f, t, tmp_path / "d.m4a", data_dir=data, ffmpeg=FFMPEG)
    a = pcm(tmp_path / "d.m4a")
    at = 150 * SPF
    free = rms_db(a, at - RATE, at - RATE // 2)
    ducked = rms_db(a, at + RATE // 10, at + 4 * RATE // 10)  # inside the 0.5 s silent thud
    assert ducked - free == pytest.approx(-mix.DUCK_DB, abs=0.5)
    ramp = round(mix.GATE_RAMP * RATE) + SPF // 10
    for a0, a1 in ((300, 360), (460, 520)):  # the mute freeze, the card
        assert rms_db(a, a0 * SPF + ramp, a1 * SPF - ramp) < free - 60, (a0, a1)
    assert rms_db(a, 362 * SPF, 372 * SPF) == pytest.approx(free, abs=0.5)  # back after it
    assert rep.loudness.normalization == "linear"


@needs_ffmpeg
def test_a_busy_take_renders_with_loops_doors_and_aggregation(masters, tmp_path):
    """Everything at once through the real graph: the vox and the flame's middle (own looped
    inputs), a door at the game's own speed (asetrate), a clump of deaths (aggregation), a
    time-lapsed repair, a noise bed (pink-ish tone) - and the middle actually sounds."""
    data = install(tmp_path / "data", masters,
                   lambda f: "tone" if "world_base_wind" in f else None)
    events = [{"tick": 20, "ev": "walk_start", "x": 0, "y": 0},
              {"tick": 140, "ev": "walk_stop", "x": 0, "y": 0}]
    events += [{"tick": 30 + 12 * k, "ev": "footfall", "x": (k % 2) - 0.5, "y": 0}
                for k in range(9)]
    events += [{"tick": 200, "ev": "fire_start", "x": 0, "y": 0},
               {"tick": 380, "ev": "fire_stop", "x": 0, "y": 0}]
    events += [{"tick": 300, "ev": "biter_died", "x": 12 + k, "y": -3, "name": "small-biter"}
               for k in range(6)]
    events += [{"tick": 420, "ev": "thud", "x": 0, "y": 0},
               {"tick": 470, "ev": "bot_out", "x": 6, "y": 0},
               {"tick": 480, "ev": "repair_start"}, {"tick": 700, "ev": "repair_full"}]
    events += [{"tick": 480 + 30 * k, "ev": "repairing"} for k in range(8)]
    cut = cut_json([("span", 0, 480, 1.0), ("span", 480, 700, 5.0), ("span", 700, 760, 1.0)])
    e, f, t = write_take(tmp_path / "take", events, cut)
    rep = mix.render(e, f, t, tmp_path / "busy.m4a", data_dir=data, ffmpeg=FFMPEG)
    # Its synthetic clicks stack to a ~26 dB crest, so -16 is out of reach; the ceiling holds.
    assert rep.loudness.normalization == "linear", rep.summary()
    assert rep.loudness.true_peak_dbtp <= mix.TP_TARGET
    assert rep.dropped_aggregation["small-biter/dying"] == 3
    assert rep.dropped_aggregation["small-biter/gore"] == 5
    assert {"spidertron-vox", "flamethrower-mid", "roboport-door-open", "roboport-door-close",
            "robot-repair"} <= rep.placed.keys()
    a = pcm(tmp_path / "busy.m4a")
    mid = [c for c in rep.cues if c.key == "flamethrower-mid"][0]
    lo = round((mid.out_s + 0.5) * RATE)
    assert rms_db(a, lo, lo + RATE // 2) > rms_db(a, 160 * SPF, 190 * SPF) + 6  # hum > bed


@needs_ffmpeg
def test_the_cli_writes_the_mix_and_its_report(onset_render, tmp_path):
    _, _, data, (e, f, t) = onset_render
    proc = subprocess.run([sys.executable, "-m", "video.mix", "--events", str(e), "--frames",
                           str(f), "--track", str(t), "--out", str(tmp_path / "c.m4a"),
                           "--data-dir", str(data), "--ffmpeg", FFMPEG,
                           "--report", str(tmp_path / "c.json")],
                          cwd=TOOLS, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "LUFS" in proc.stdout and "jamaltron-landing-thud" in proc.stdout
    rep = json.loads((tmp_path / "c.json").read_text())
    assert rep["samples"] == 539 * SPF and rep["loudness"]["normalization"] == "linear"


def test_the_cli_refuses_a_bad_take_with_exit_2(tmp_path):
    (tmp_path / "e.jsonl").write_text("{nope\n")
    (tmp_path / "f.json").write_text(json.dumps(cut_json([("span", 0, 10, 1.0)])))
    (tmp_path / "t.jsonl").write_text("")
    proc = subprocess.run([sys.executable, "-m", "video.mix", "--events", str(tmp_path / "e.jsonl"),
                           "--frames", str(tmp_path / "f.json"), "--track",
                           str(tmp_path / "t.jsonl"), "--out", str(tmp_path / "o.m4a")],
                          cwd=TOOLS, capture_output=True, text=True)
    assert proc.returncode == 2 and "e.jsonl:1: not JSON" in proc.stderr, proc.stderr
