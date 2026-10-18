"""G.5: video/timeline.py without Factorio - the logs, the anchor grammar, every cut-file
refusal, the resolver's frame arithmetic and frames.json, and the SHIPPED cut files resolved
against a storyA-shaped event log."""

from __future__ import annotations

import json
import pathlib
from fractions import Fraction

import pytest

from video_fake import ev, loop_events, make_take, story_events, write_cut
from video import timeline as tl

TOOLS = pathlib.Path(__file__).resolve().parents[1]


def take_of(tmp_path: pathlib.Path, events: list[dict[str, object]], first: int = 0,
            last: int = 400) -> tl.Take:
    make_take(tmp_path / "take", first=first, last=last, events=events, frames=False)
    return tl.load_take(tmp_path / "take")


HOPS = [ev(10, "beat", name="hop1"), ev(20, "takeoff"), ev(35, "apex"), ev(50, "landing"),
        ev(100, "takeoff"), ev(115, "apex"), ev(130, "landing"), ev(200, "repair_cue"),
        ev(240, "beat", name="wrap")]


# --------------------------------------------------------------------------------- the logs

def test_events_come_back_in_tick_order_with_ordinals(tmp_path):
    t = take_of(tmp_path, [ev(100, "takeoff"), ev(20, "takeoff"), ev(20, "line", row="x")])
    offs = t.of("takeoff")
    assert [(e.tick, e.ordinal) for e in offs] == [(20, 1), (100, 2)]
    # same-tick events keep file order (the order the director saw them)
    assert [e.ev for e in t.events if e.tick == 20] == ["takeoff", "line"]


@pytest.mark.parametrize("line,why", [
    ("{not json", "not JSON"),
    ('{"ev": "beat"}', "'tick' must be a whole number"),
    ('{"tick": -1, "ev": "beat"}', "'tick' must be a whole number"),
    ('{"tick": 1.5, "ev": "beat"}', "'tick' must be a whole number"),
    ('{"tick": 3}', "'ev' must be a non-empty string"),
    ('[1, 2]', "want a JSON object"),
])
def test_a_bad_event_line_names_its_file_and_line(tmp_path, line, why):
    p = tmp_path / "events.jsonl"
    p.write_text('{"tick": 0, "ev": "capture_start"}\n' + line + "\n")
    with pytest.raises(tl.TakeError, match=why) as e:
        tl.load_events(p)
    assert "events.jsonl:2" in str(e.value)


def _track(tmp_path, rows):
    p = tmp_path / "track.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def _row(t, **kw):
    r = {"tick": t, "cam": [0, 0], "zoom": 2, "body": "jamaltron", "pos": [0, 0],
         "lift": [0, -1.5]}
    r.update(kw)
    return r


def test_track_accepts_lua_shaped_positions(tmp_path):
    tr = tl.load_track(_track(tmp_path, [_row(5, pos={"x": 1, "y": 2}), _row(6)]))
    assert tr[5].pos == (1.0, 2.0) and tr[6].lift == (0.0, -1.5)


@pytest.mark.parametrize("rows,why", [
    ([_row(1), _row(3)], "1 captured tick\\(s\\) missing, first 2"),
    ([_row(1), _row(1)], "tick 1 logged twice"),
    ([_row(1, body="spidertron")], "body 'spidertron'"),
    ([_row(1, zoom=0)], "zoom must be > 0"),
    ([_row(1, cam=[1])], "bad or missing cam"),
    ([_row(1, lift=None)], "bad or missing lift"),
    ([], "empty"),
])
def test_a_bad_track_is_refused(tmp_path, rows, why):
    with pytest.raises(tl.TakeError, match=why):
        tl.load_track(_track(tmp_path, rows))


def test_capture_markers_that_disagree_with_the_track_warn(tmp_path):
    make_take(tmp_path / "t", first=10, last=20, events=[], frames=False)
    p = tmp_path / "t" / "events.jsonl"
    p.write_text(p.read_text().replace('"tick": 10, "ev": "capture_start"',
                                       '"tick": 11, "ev": "capture_start"'))
    take = tl.load_take(tmp_path / "t")
    assert any("capture_start at [11]" in w for w in take.warnings)


# ------------------------------------------------------------------------------ geometry

def test_geometry_is_the_contract_capture_or_that_aspect_scaled():
    g = tl.Geometry.from_capture(1920, 1104)
    assert (g.out_size, g.band, g.scale) == ((1920, 1080), 24, 1.0)
    s = tl.Geometry.from_capture(192, 110)
    assert (s.out_size, s.band) == ((192, 108), 2)
    with pytest.raises(tl.TakeError, match="the capture is 1920x1104"):
        tl.Geometry.from_capture(1920, 1080)


def test_screen_projection_centres_the_camera_on_the_whole_capture():
    g = tl.Geometry.from_capture(1920, 1104)
    # centre row is 552 (1104/2), not 540: the crop is bottom-only
    assert g.to_screen((3, -1.5), (3, -1.5), 2) == (960, 552)
    assert g.to_screen((4, -1.5), (3, -1.5), 2) == (960 + 64, 552)


# ------------------------------------------------------------------------------- anchors

@pytest.mark.parametrize("text,want", [
    ("takeoff", ("takeoff", None, None, 0)),
    ("takeoff#3", ("takeoff", None, 3, 0)),
    ("takeoff#3-20", ("takeoff", None, 3, -20)),
    ("landing#1 + 60", ("landing", None, 1, 60)),
    ("beat:lake_jump+5", (None, "lake_jump", None, 5)),
    ("repair_full-30", ("repair_full", None, None, -30)),
])
def test_anchor_grammar(text, want):
    a = tl.Anchor.parse(text)
    assert (a.ev, a.beat, a.n, a.offset) == want


@pytest.mark.parametrize("text", ["", "takeoff#0", "takeoff#03", "takeoff#", "#3",
                                  "takeoff+", "takeoff*2", "Takeoff", "beat:", "beat:a b+",
                                  "takeoff#1#2", "takeoff-1.5"])
def test_a_malformed_anchor_is_refused(text):
    with pytest.raises(tl.CutError, match="is not an anchor"):
        tl.Anchor.parse(text)


def test_anchors_resolve_against_the_take(tmp_path):
    t = take_of(tmp_path, HOPS)

    def r(s: str) -> int:
        return tl.Anchor.parse(s).resolve(t)

    assert r("takeoff#2-20") == 80
    assert r("landing#1+10") == 60
    assert r("repair_cue+30") == 230
    assert r("beat:hop1") == 10
    assert r("capture_start") == 0


@pytest.mark.parametrize("text,why", [
    ("takeoff", "this take has 2 takeoff events; say which \\(takeoff#1 .. takeoff#2\\)"),
    ("takeoff#3", "missing anchor 'takeoff#3': the take has only 2 takeoff"),
    ("break#1", "missing anchor 'break#1': the take has no break event"),
    ("takof#1", "'takof' is not an event the director logs - did you mean 'takeoff'"),
    ("beat:lake", "no beat named 'lake' \\(its beats: hop1, wrap\\)"),
])
def test_a_missing_or_ambiguous_anchor_is_a_hard_error_naming_it(tmp_path, text, why):
    t = take_of(tmp_path, HOPS)
    with pytest.raises(tl.CutError, match=why):
        tl.Anchor.parse(text).resolve(t)


def test_a_beat_that_starts_twice_is_ambiguous(tmp_path):
    t = take_of(tmp_path, [ev(5, "beat", name="hop"), ev(9, "beat", name="hop")])
    with pytest.raises(tl.CutError, match="starts 2 times"):
        tl.Anchor.parse("beat:hop").resolve(t)


# ------------------------------------------------------------------------------ cut file

SPAN = '[[segment]]\nfrom = "takeoff#1-10"\nto = "landing#1+10"\n'


def cut(tmp_path, text: str) -> tl.Cut:
    return tl.load_cut(write_cut(tmp_path / "c.toml", text))


@pytest.mark.parametrize("text,why", [
    ("fps = 60\n", "no \\[\\[segment\\]\\]s"),
    ("fps = 30\n" + SPAN, "fps must be 60"),
    ("fps = true\n" + SPAN, "fps must be 60"),
    ('deliver = "gif"\n' + SPAN, "deliver must be 'master' or 'loop'"),
    ("speeed = 1\n" + SPAN, "unknown key 'speeed'"),
    (SPAN + "sped = 0.5\n", "segment 1 \\(a span: from \\+ to\\): unknown key 'sped' - did you "
                            "mean 'speed'"),
    ('[[segment]]\nfrom = "takeoff#1"\n', "segment 1: missing 'to'"),
    ('[[segment]]\nto = "takeoff#1"\n', "segment 1: missing 'from'"),
    ('[[segment]]\nfrom = 5\nto = "apex#1"\n', "from must be a non-empty string"),
    ('[[segment]]\nfrom = "takeoff#0"\nto = "apex#1"\n', "from: 'takeoff#0' is not an anchor"),
    (SPAN + "speed = 0\n", "speed 0.0 is outside"),
    (SPAN + "speed = -2\n", "speed -2.0 is outside"),
    (SPAN + "speed = 100\n", "speed 100.0 is outside"),
    (SPAN + 'speed = "fast"\n', "speed must be a number"),
    (SPAN + "speed = true\n", "speed must be a number"),
    (SPAN + "speed = nan\n", "speed must be a number"),
    (SPAN + 'audio = "loud"\n', "audio must be 'live' or 'mute'"),
    (SPAN + 'tag = ""\n', "tag must be a non-empty string"),
    (SPAN + 'tag = "timelapse!"\n', "keep it to 8 characters"),
    ('[[segment]]\nat = "apex#1"\n', "segment 1: missing 'hold'"),
    ('[[segment]]\nat = "apex#1"\nhold = 0\n', "hold must be a number > 0"),
    ('[[segment]]\nat = "apex#1"\nhold = 2\nspeed = 1\n', "a freeze: at \\+ hold\\): unknown "
                                                          "key 'speed'"),
    ('[[segment]]\nat = "apex#1"\nhold = 2\nto = "apex#2"\n', "unknown key 'to'"),
    (SPAN + '[[card]]\ncard = "credits"\nseconds = 3\n', "card must be one of title, end"),
    (SPAN + '[[card]]\ncard = "end"\n', "card 1: missing 'seconds'"),
    (SPAN + '[[card]]\ncard = "end"\nseconds = -1\n', "seconds must be a number > 0"),
    (SPAN + '[[overlay]]\ncard = "title"\nfrom_out = 3\nto_out = 3\n', "want 0 <= from_out < "
                                                                       "to_out"),
    (SPAN + '[[overlay]]\ncard = "title"\nfrom_out = -1\nto_out = 3\n', "want 0 <= from_out"),
    (SPAN + '[[overlay]]\ncard = "title"\nto_out = 3\n', "missing 'from_out'"),
    ("segment = 5\n", "segment must be an array of tables"),
    ("fps = \n", "not TOML"),
    (SPAN + 'caption = "left"\n', "caption must be 'above' or 'below', got 'left'"),
    ('[[segment]]\nat = "apex#1"\nhold = 2\ncaption = "below"\n', "unknown key 'caption'"),
    ("crop = [340, 240, 1280, 720]\n" + SPAN, "crop is for loop cuts"),
    ('deliver = "loop"\ncrop = [0, 0, 1280]\n' + SPAN, "crop wants \\[x, y, width, height\\]"),
    ('deliver = "loop"\ncrop = [0, 0, 1280.5, 720]\n' + SPAN, "crop wants"),
    ('deliver = "loop"\ncrop = [700, 400, 1280, 720]\n' + SPAN, "inside 1920x1080"),
    ('deliver = "loop"\ncrop = [0, 0, 1280, 700]\n' + SPAN, "must be even and 16:9"),
])
def test_every_cut_file_error_is_hard_and_names_the_problem(tmp_path, text, why):
    with pytest.raises(tl.CutError, match=why):
        cut(tmp_path, text)


def test_a_missing_cut_file_is_named(tmp_path):
    with pytest.raises(tl.CutError, match="missing"):
        tl.load_cut(tmp_path / "nope.toml")


def test_speeds_are_exact_fractions():
    assert tl._speed("x", 0.3333) == Fraction(1, 3)
    assert tl._speed("x", 5) == 5
    assert tl._speed("x", 0.5) == Fraction(1, 2)


# ------------------------------------------------------------------------------ resolver

def resolve(tmp_path, text: str, events=HOPS, last=400) -> tl.Resolved:
    return tl.resolve(cut(tmp_path, text), take_of(tmp_path, events, last=last))


def test_half_speed_shows_every_source_frame_twice(tmp_path):
    r = resolve(tmp_path, '[[segment]]\nfrom = "takeoff#1"\nto = "takeoff#1+3"\nspeed = 0.5\n')
    assert [f.src for f in r.frames] == [20, 20, 21, 21, 22, 22]


def test_five_x_shows_every_fifth_source_frame(tmp_path):
    r = resolve(tmp_path, '[[segment]]\nfrom = "repair_cue"\nto = "repair_cue+11"\n'
                          'speed = 5.0\ntag = "5x"\n')
    assert [f.src for f in r.frames] == [200, 205, 210]
    s = r.segments[0]
    assert (s.kind, s.speed, s.tag, s.timelapse) == ("span", 5.0, "5x", True)


def test_a_third_speed_never_drifts():
    srcs = tl.span_sources(0, 3000, Fraction(1, 3))
    assert len(srcs) == 9000 and all(srcs[3 * k: 3 * k + 3] == [k] * 3 for k in range(3000))


def test_spans_are_half_open_so_shared_anchors_show_no_tick_twice(tmp_path):
    r = resolve(tmp_path, '[[segment]]\nfrom = "takeoff#1-3"\nto = "takeoff#1"\n'
                          '[[segment]]\nfrom = "takeoff#1"\nto = "takeoff#1+2"\n')
    assert [f.src for f in r.frames] == [17, 18, 19, 20, 21]
    assert [(s.start, s.stop, s.out) for s in r.segments] == [(17, 20, (0, 3)), (20, 22, (3, 5))]


def test_to_not_after_from_is_refused(tmp_path):
    with pytest.raises(tl.CutError, match="segment 1: to = 'takeoff#1' \\(tick 20\\) is not "
                                          "after from = 'landing#1' \\(tick 50\\)"):
        resolve(tmp_path, '[[segment]]\nfrom = "landing#1"\nto = "takeoff#1"\n')
    with pytest.raises(tl.CutError, match="is not after"):
        resolve(tmp_path, '[[segment]]\nfrom = "landing#1"\nto = "landing#1"\n')


def test_a_span_outside_the_capture_is_refused(tmp_path):
    with pytest.raises(tl.CutError, match="resolves to tick 450, outside the capture"):
        resolve(tmp_path, '[[segment]]\nfrom = "landing#2"\nto = "landing#2+320"\n')
    with pytest.raises(tl.CutError, match="resolves to tick -5"):
        resolve(tmp_path, '[[segment]]\nfrom = "capture_start-5"\nto = "landing#1"\n')
    # to is exclusive: ending one past the last captured tick is the whole capture
    r = resolve(tmp_path, '[[segment]]\nfrom = "landing#2"\nto = "capture_end+1"\n')
    assert r.frames[-1].src == 400


def test_a_freeze_holds_one_frame_for_hold_times_fps(tmp_path):
    r = resolve(tmp_path, SPAN + '[[segment]]\nat = "apex#2"\nhold = 4.5\naudio = "mute"\n')
    frz = r.segments[1]
    assert (frz.kind, frz.start, frz.stop, frz.audio, frz.speed) == ("freeze", 115, 116,
                                                                     "mute", 0.0)
    held = [f for f in r.frames if f.seg == 1]
    assert len(held) == 270 and {f.src for f in held} == {115}


def test_a_card_has_no_source_mutes_and_backs_onto_the_last_frame(tmp_path):
    r = resolve(tmp_path, SPAN + '[[segment]]\nat = "apex#2"\nhold = 1\n'
                                 '[[card]]\ncard = "end"\nseconds = 7\n')
    c = r.segments[-1]
    assert (c.kind, c.card, c.audio, c.start, c.stop) == ("card", "end", "mute", 115, 115)
    tail = r.frames[c.out[0]:]
    assert len(tail) == 420 and all(f.src is None and f.seg == 2 for f in tail)
    assert r.frames[c.out[0] - 1].src == 115


def test_an_overlay_maps_to_output_frames_and_must_fit(tmp_path):
    r = resolve(tmp_path, SPAN + '[[overlay]]\ncard = "title"\nfrom_out = 0.0\nto_out = 0.5\n')
    assert r.overlays[0].out == (0, 30)
    assert tl.overlays_at(r, 29) and not tl.overlays_at(r, 30)
    with pytest.raises(tl.CutError, match="overlay 1: 0.0..3.0 s is not inside the cut's 0.83"):
        resolve(tmp_path, SPAN + '[[overlay]]\ncard = "title"\nfrom_out = 0\nto_out = 3\n')


def test_frames_json_is_the_contract_shape_and_round_trips(tmp_path):
    r = resolve(tmp_path, SPAN + '[[segment]]\nat = "apex#2"\nhold = 0.5\naudio = "mute"\n'
                                 '[[overlay]]\ncard = "title"\nfrom_out = 0\nto_out = 0.2\n'
                                 '[[card]]\ncard = "end"\nseconds = 0.5\n')
    p = tmp_path / "frames.json"
    r.write(p)
    d = json.loads(p.read_text())
    assert d == r.to_json()
    assert d["fps"] == 60 and d["deliver"] == "master" and d["captions"] is True
    assert d["frames"][0] == {"src": 10, "seg": 0} and d["frames"][-1] == {"src": None, "seg": 2}
    assert set(d["segments"][0]) >= {"index", "kind", "speed", "from", "to", "tag", "audio"}
    assert [s["kind"] for s in d["segments"]] == ["span", "freeze", "card"]
    assert d["crop"] is None and d["segments"][0]["caption"] == "above"
    assert tl.Resolved.load(p) == r


def test_a_loop_crop_and_a_below_span_round_trip(tmp_path):
    r = resolve(tmp_path, 'deliver = "loop"\ncrop = [340, 240, 1280, 720]\n' + SPAN
                + 'caption = "below"\n')
    assert r.crop == (340, 240, 1280, 720) and r.segments[0].caption == "below"
    assert r.caption_side(r.segments[0].start) == "below"
    assert r.caption_side(r.segments[0].stop) == "above"          # half-open, like everything
    p = tmp_path / "frames.json"
    r.write(p)
    assert json.loads(p.read_text())["crop"] == [340, 240, 1280, 720]
    assert tl.Resolved.load(p) == r


# ------------------------------------------------------------------- the shipped cut files

def test_the_shipped_main_cut_resolves_against_a_storyA_take(tmp_path):
    t = take_of(tmp_path, story_events(), last=4547)
    r = tl.resolve(tl.load_cut(TOOLS / "video" / "main.toml"), t)
    kinds = [(s.kind, s.speed, s.tag, s.audio, s.caption) for s in r.segments]
    assert kinds == [("freeze", 0.0, None, "live", "above"), ("span", 1.0, None, "live", "above"),
                     ("span", pytest.approx(1 / 3), None, "live", "above"),
                     ("span", 1.0, None, "live", "above"),
                     ("span", 1.0, None, "live", "below"),             # the wave
                     ("span", 1.0, None, "live", "above"),
                     ("span", 0.25, None, "live", "above"), ("span", 1.0, None, "live", "above"),
                     ("span", 5.0, "5x", "live", "above"), ("span", 1.0, None, "live", "above"),
                     ("freeze", 0.0, None, "mute", "above"), ("card", 0.0, None, "mute", "above")]
    assert (r.segments[0].start, r.segments[0].out) == (0, (0, 30))  # the poster, 0.5 s
    spans = [(s.start, s.stop) for s in r.segments[1:10]]
    assert spans == [(0, 200), (200, 230), (230, 960), (960, 1260), (1260, 1900), (1900, 1947),
                     (1947, 2787 + 59), (2787 + 59, 4130), (4130, 4464)]
    # the three 1x spans between hop1 and the lake play as one: contiguous, same speed
    assert [r.frames[r.segments[k].out[0]].src for k in (4, 5)] == [960, 1260]
    # attacking.01 (fire_start#1 + 20) is captioned below him; the rest above
    assert r.caption_side(980) == "below" and r.caption_side(1500) == "above"
    # the storyboard's slow-mos: hop1's 30-tick arc x3, the lake's 47-tick arc x4
    assert [s.out[1] - s.out[0] for s in (r.segments[2], r.segments[6])] == [90, 188]
    # the break is the FIRST frame of a 1x segment: the thud and the beached body land on it
    assert r.frames[r.segments[7].out[0]].src == 1947
    # flopping.02 (break+570) has faded out before the time-lapse starts: 300 + 29 ticks
    assert r.segments[8].start == 2517 + 300 + 29
    assert r.segments[10].start == 4464                      # the freeze is apex#4
    assert r.overlays[0].out == (0, 180)                     # title over the first 3 s
    assert len([f for f in r.frames if f.seg == 11]) == 420  # 7 s end card
    assert r.captions and r.deliver == "master"


def test_the_shipped_loop_cut_resolves_to_one_seamless_span(tmp_path):
    t = take_of(tmp_path, loop_events(), last=430)
    r = tl.resolve(tl.load_cut(TOOLS / "video" / "loop.toml"), t)
    assert r.deliver == "loop" and not r.captions and not r.overlays
    assert r.crop == (340, 240, 1280, 720)                   # storyboard A's 1280x720
    assert [f.src for f in r.frames] == list(range(181, 363))
    # ON the 2nd landing (at A) to the 4th (at A), as story.lua stages it: 182 frames, 3.03 s
    landings = [e.tick for e in t.of("landing")]
    assert (r.frames[0].src, r.frames[-1].src + 1) == (landings[1], landings[3])
