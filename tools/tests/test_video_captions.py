"""G.5: video/captions.py without Factorio - the text by row id, the game's timing and
replacement (mid-fade included), the torso anchor (T+1 on the ground, T in an arc, the arc's
ratchet, the below side), the clamp, the cross-check against the mod's speech log (and what
makes a `said` proof), and the bubble itself.

The fonts are the install's Titillium Web when this machine has Factorio, else Pillow's
bundled face (a runner): nothing here asserts a glyph shape, only geometry and colour."""

from __future__ import annotations

import re

import pytest
from PIL import Image

from video_fake import ev, make_take
from video import captions as cap
from video import timeline as tl


@pytest.fixture(scope="module")
def fonts() -> cap.Fonts:
    try:
        return cap.Fonts.factorio()
    except cap.FontError:
        return cap.Fonts.fallback()


def line(tick: int, row: str, **kw: object) -> dict[str, object]:
    return ev(tick, "line", row=row, channel="speech", forced=True, x=0, y=0, **kw)


def events_of(evs: list[dict[str, object]]) -> tuple[tl.Event, ...]:
    return tuple(tl.Event(e["tick"], e["ev"], {k: v for k, v in e.items()  # type: ignore
                                               if k not in ("tick", "ev")}, 1, k)
                 for k, e in enumerate(evs, 1))


# ------------------------------------------------------------------- the mod's own numbers

def test_timing_constants_are_speech_lua_s():
    src = cap.SPEECH_LUA.read_text()
    for name, want in (("SHOW_TICKS", cap.SHOW_TICKS), ("FADE_TICKS", cap.FADE_TICKS)):
        m = re.search(rf"^M\.{name} = ([\d\s*]+)$", src, re.M)
        assert m, f"speech.lua no longer sets M.{name} plainly - re-pin"
        assert eval(m[1], {"__builtins__": {}}) == want, name  # noqa: S307 - digits and *


def test_the_log_pattern_is_the_line_speech_lua_writes():
    src = cap.SPEECH_LUA.read_text()
    assert 'log("jamaltron speech " .. tostring(entity.unit_number) .. " " .. row.id)' in src
    assert cap.SPEECH_LOG.search("  3.2 Script @__jamaltron__/x.lua:1: jamaltron speech 42 "
                                 "jump.13")[2] == "jump.13"


# --------------------------------------------------------------------------------- the text

def test_the_real_locale_has_every_row_the_storyboard_forces():
    lines = cap.load_lines()
    for row in ("jump.01", "land.03", "land.06", "attacking.01", "command_done.02", "jump.05",
                "legs_break.01", "flopping.12", "flopping.02", "repaired.07", "jump.13"):
        assert row in lines, row
    assert lines["jump.13"] == "Jamal does not know the idiom, but Jamal will hop!"
    assert "’" in lines["moving.03"]          # the catalog's ruled apostrophe survives


def test_load_lines_reads_only_its_section(tmp_path):
    p = tmp_path / "x.cfg"
    p.write_text("# c\n[other]\njump.01=nope\n[jamaltron-line]\n; c\njump.01=Hop = yes\n\n"
                 "x.02=two\\nlines\n")
    assert cap.load_lines(p) == {"jump.01": "Hop = yes", "x.02": "two\nlines"}


def test_row_text_substitutes_the_break_count():
    lines = {"legs_break.17": "That was set __1__. Jamal is sorry about set __1__.",
             "a.01": "plain", "b.01": "__2__"}
    assert cap.row_text(lines, "legs_break.17", 3) == ("That was set 3. Jamal is sorry about "
                                                       "set 3.")
    assert cap.row_text(lines, "a.01", None) == "plain"
    with pytest.raises(tl.TakeError, match="says __1__ .* carries no n"):
        cap.row_text(lines, "legs_break.17", None)
    with pytest.raises(tl.TakeError, match="'nope.01' is not in"):
        cap.row_text(lines, "nope.01", None)
    with pytest.raises(tl.TakeError, match="__2__"):
        cap.row_text(lines, "b.01", 1)


# ------------------------------------------------------------------------------- the timing

LINES = {"a.01": "first", "b.01": "second", "c.01": "third"}


def test_a_line_is_up_300_ticks_then_fades_29():
    t = cap.CaptionTrack.from_events(events_of([line(100, "a.01")]), LINES)
    assert t.at(99) is None
    assert t.at(100) == (t.captions[0], 1.0)
    assert t.at(399)[1] == 1.0
    assert 0 < t.at(400)[1] < 1 and t.at(428)[1] < t.at(400)[1]
    assert t.at(429) is None


def test_the_next_line_replaces_on_the_spot():
    t = cap.CaptionTrack.from_events(events_of([line(100, "a.01"), line(250, "b.01"),
                                                line(560, "c.01")]), LINES)
    assert t.at(249)[0].row == "a.01" and t.at(250)[0].row == "b.01"
    assert t.at(549)[1] == 1.0                     # b's full 300 ends at 550...
    assert t.at(559)[0].row == "b.01" and 0 < t.at(559)[1] < 1   # ...fading when c cuts it
    assert t.at(560) == (t.captions[2], 1.0)


def test_a_line_replaced_mid_fade_keeps_its_own_fade_until_it_goes():
    """The first cut took the alpha off the gone_at the NEXT line had cut short: attacking.01
    (said 754, replaced 1069) went 1.0 -> 0.5 in one frame at 1054. Its own fade says 29/30."""
    t = cap.CaptionTrack.from_events(events_of([line(754, "a.01"), line(1069, "b.01")]), LINES)
    assert t.at(1053) == (t.captions[0], 1.0)
    assert t.at(1054)[1] == pytest.approx(29 / 30)
    assert t.at(1068)[1] == pytest.approx(15 / 30)
    assert t.at(1069) == (t.captions[1], 1.0)
    # every step of a fade is the game's 1/30, never a jump
    alphas = [t.at(k)[1] for k in range(1053, 1069)]
    assert max(a - b for a, b in zip(alphas, alphas[1:])) == pytest.approx(1 / 30)


def test_same_tick_lines_the_last_said_wins():
    t = cap.CaptionTrack.from_events(events_of([line(100, "a.01"), line(100, "b.01")]), LINES)
    assert t.at(100)[0].row == "b.01"


@pytest.mark.parametrize("bad,why", [
    (ev(5, "line", channel="speech"), "no row"),
    (ev(5, "line", row="a.01", channel="narration"), "channel 'narration'; captions are "
                                                     "speech only"),
    (ev(5, "line", row="zzz.01", channel="speech"), "'zzz.01' is not in"),
])
def test_a_bad_line_event_is_named(bad, why):
    with pytest.raises(tl.TakeError, match=why) as e:
        cap.CaptionTrack.from_events(events_of([bad]), LINES)
    assert "line event at tick 5" in str(e.value)


# ------------------------------------------------------------------------------- the anchor

def anchored_take(tmp_path, **kw) -> tl.Take:
    make_take(tmp_path / "t", first=0, last=60, events=[], frames=False, **kw)
    return tl.load_take(tmp_path / "t")


GEO = tl.Geometry.from_capture(1920, 1104)


def test_a_grounded_frame_is_track_line_t_plus_1(tmp_path):
    take = anchored_take(tmp_path, pos=lambda t: (t * 0.25, 0.0), cam=lambda t: (0.0, 0.0),
                         lift=lambda t: (0.0, -1.5 - t * 0.01))
    a = cap.Anchorer(take, GEO)
    x, y = a.torso(10)
    assert x == pytest.approx(960 + 11 * 0.25 * 64)            # pos of T+1
    assert y == pytest.approx(552 + (-1.5 - 0.11) * 64)        # and its lift
    # the last frame has no T+1: its own line
    assert a.torso(60)[0] == pytest.approx(960 + 60 * 0.25 * 64)


def test_the_stand_up_frame_shows_the_standing_body(tmp_path):
    # breakage.poll swaps him on jamaltron's nth-tick, AFTER the director read line 30 (still
    # beached, lift 0): frame 30 draws him standing, so it takes line 31's body and lift.
    take = anchored_take(tmp_path, cam=lambda t: (0.0, 0.0),
                         body=lambda t: "jamaltron-beached" if t <= 30 else "jamaltron",
                         lift=lambda t: (0.0, 0.0 if t <= 30 else -1.5))
    a = cap.Anchorer(take, GEO)
    assert a.torso(29)[1] == pytest.approx(552)
    assert a.torso(30)[1] == pytest.approx(552 - 1.5 * 64)
    assert a.anchor(29)[1] == pytest.approx(552 - (cap.CLEAR_TILES["jamaltron-beached"] * 64
                                                   + cap.CLEAR_PX))
    assert a.anchor(30)[1] == pytest.approx(552 - 1.5 * 64 - (cap.CLEAR_TILES["jamaltron"] * 64
                                                              + cap.CLEAR_PX))


def test_the_caption_clears_his_legs_by_body(tmp_path):
    take = anchored_take(tmp_path, cam=lambda t: (0.0, -1.5))
    a = cap.Anchorer(take, GEO)
    assert a.torso(5) == (960, 552)
    assert a.anchor(5) == (960, 552 - (cap.CLEAR_TILES["jamaltron"] * 64 + cap.CLEAR_PX))
    # the knees stand ~2.4 tiles over the torso; the arc draws no legs
    assert cap.CLEAR_TILES["jamaltron"] > 2.4 > cap.CLEAR_TILES["jamaltron-airborne"]


def test_during_an_arc_the_caption_ratchets_up_and_never_bobs(tmp_path):
    # As the director logs it: line 20 (the takeoff tick) is already airborne at the standing
    # torso's height, line 40 (the landing) is the landed body. A parabola of lift, peak at 30
    # (5.5 tiles over the standing torso).
    arc = range(20, 40)
    take = anchored_take(
        tmp_path, cam=lambda t: (0.0, 0.0),
        body=lambda t: "jamaltron-airborne" if t in arc else "jamaltron",
        pos=lambda t: (0.3 * t, 0.0),
        lift=lambda t: (0.0, -1.5 - (0.055 * (100 - (t - 30) ** 2) if t in arc else 0)))
    a = cap.Anchorer(take, GEO)
    assert not a.in_arc(19) and a.in_arc(20) and a.in_arc(39) and not a.in_arc(40)
    # in the arc, frame T is line T: jamaltron's on_tick already moved him (no T+1 lead)
    assert a.torso(25)[0] == pytest.approx(960 + 0.3 * 25 * 64)
    assert a.torso(39)[0] == pytest.approx(960 + 0.3 * 39 * 64)
    assert a.torso(19)[0] == pytest.approx(960 + 0.3 * 19 * 64)  # the frame before takeoff
    ys = [a.anchor(t)[1] for t in range(19, 40)]
    stand = cap.CLEAR_TILES["jamaltron"] * 64 + cap.CLEAR_PX
    air = cap.CLEAR_TILES["jamaltron-airborne"] * 64 + cap.CLEAR_PX
    # it holds the pre-takeoff height (no drop to the smaller airborne clearance at takeoff)...
    assert ys[0] == pytest.approx(a.torso(19)[1] - stand)
    assert ys[1] == ys[0] and ys[2] == ys[0]
    # ...rides up with him once his torso would reach it, and holds the peak to the landing
    # screen y grows down: over the whole arc it only ever rises or holds
    assert all(later <= earlier + 1e-9 for earlier, later in zip(ys, ys[1:]))
    assert ys[1 + 25 - 20] < ys[0]                             # risen by tick 25
    peak = a.torso(30)[1] - air
    assert ys[30 - 19] == pytest.approx(peak)
    assert {round(y, 6) for y in ys[30 - 19:]} == {round(peak, 6)}
    assert a.anchor(25)[0] != a.anchor(35)[0]                  # x still follows him
    assert a.anchor(40)[1] == pytest.approx(a.torso(40)[1] - stand)


def test_a_below_caption_hangs_under_his_feet(tmp_path):
    take = anchored_take(tmp_path, cam=lambda t: (0.0, -1.5))
    a = cap.Anchorer(take, GEO)
    assert a.anchor(5, "below") == (960, 552 + cap.BELOW_TILES * 64 + cap.CLEAR_PX)
    # MEASURED: a standing body's lowest foot reaches 4.3-4.6 tiles under the torso centre
    assert cap.BELOW_TILES > 4.6


def test_the_cut_decides_the_side_by_the_tick_a_line_was_said(tmp_path):
    evs = [line(10, "jump.01"), line(60, "attacking.01")]
    take, r = resolved_for(tmp_path, '[[segment]]\nfrom = "capture_start"\nto = "line#2"\n'
                                     '[[segment]]\nfrom = "line#2"\nto = "capture_end"\n'
                                     'caption = "below"\n', evs)
    t = cap.CaptionTrack.from_events(take.events, cap.load_lines(), r.caption_side)
    assert [c.side for c in t.captions] == ["above", "below"]
    # the side goes with the LINE: attacking.01 is still below at tick 300, whatever plays then
    assert t.at(300)[0].side == "below"


def test_the_bubble_hangs_from_its_top_when_below(fonts):
    b = cap.render_bubble("Jamal is firing his flamethrower!", fonts, 1.0)
    assert b.anchor_for("above") == b.anchor and b.anchor_for("below") == b.top
    assert b.top[1] == 0 and b.top[0] > b.anchor[0]           # the slant leans the top right


@pytest.mark.parametrize("at", [(-500, -500), (5000, 5000), (0, 540), (1920, 0), (960, 2000)])
def test_placement_is_clamped_inside_the_kept_frame(at):
    size, anchor = (700, 120), (350, 120)
    x, y = cap.place(size, anchor, at, GEO)
    m = cap.MARGIN_PX
    assert m <= x <= 1920 - m - 700 and m <= y <= 1080 - m - 120


def test_placement_centres_the_bubble_bottom_on_the_anchor():
    assert cap.place((200, 60), (100, 60), (960, 400), GEO) == (860, 340)


# --------------------------------------------------------------------- shown vs said

def resolved_for(tmp_path, cut_text: str, evs):
    make_take(tmp_path / "r", first=0, last=400, events=evs, frames=False)
    take = tl.load_take(tmp_path / "r")
    (tmp_path / "c.toml").write_text(cut_text)
    return take, tl.resolve(tl.load_cut(tmp_path / "c.toml"), take)


def test_rows_shown_skips_timelapse_and_captionless_cuts(tmp_path):
    evs = [line(10, "jump.01"), line(100, "land.03"), line(200, "flopping.12")]
    take, r = resolved_for(tmp_path, '[[segment]]\nfrom = "capture_start"\nto = "line#2"\n'
                                     '[[segment]]\nfrom = "line#2"\nto = "line#3"\nspeed = 5\n',
                           evs)
    track = cap.CaptionTrack.from_events(take.events, cap.load_lines())
    assert cap.rows_shown(r, track) == {"jump.01": 10}
    loop = tl.Resolved(r.fps, "loop", False, r.frames, r.segments, r.overlays)
    assert cap.rows_shown(loop, track) == {}


def test_rows_logged_counts_every_row_the_mod_said(tmp_path):
    make_take(tmp_path / "t", first=0, last=3, events=[], frames=False,
              said=["jump.01", "land.09", "land.03", "jump.01"])
    assert cap.rows_logged(tmp_path / "t" / "run.log") == {"jump.01": 2, "land.09": 1,
                                                           "land.03": 1}


AUDIT_CUT = ('[[segment]]\nfrom = "capture_start"\nto = "capture_start+100"\n'
             '[[segment]]\nfrom = "capture_start+100"\nto = "capture_start+200"\nspeed = 5\n')


def audit_of(tmp_path, evs, logged):
    take, r = resolved_for(tmp_path, AUDIT_CUT, evs)
    track = cap.CaptionTrack.from_events(take.events, cap.load_lines())
    return cap.audit(r, track, take.events, logged)


def test_the_audit_passes_when_every_logged_row_is_captioned_or_proven_unseen(tmp_path):
    evs = [ev(10, "said", row="land.09", channel="speech", replaced_by="land.03", x=0, y=0),
           ev(10, "said", row="land.08", channel="narration", hidden=True, x=0, y=0),
           line(10, "land.03"),                       # captioned
           line(150, "flopping.12"),                  # inside the 5x: never on screen
           line(300, "repaired.07"),                  # past the cut's end
           line(320, "land.03")]                      # a captioned row, said again off-cut
    a = audit_of(tmp_path, evs, {"land.09": 1, "land.08": 1, "land.03": 2, "flopping.12": 1,
                                 "repaired.07": 1})
    assert a.problems == []
    assert a.shown == {"land.03": 10} and a.replaced == {"land.09": 1, "land.08": 1}
    assert a.notes == [
        "not on screen in this cut: flopping.12 (line at tick 150, during a time-lapse)",
        "not on screen in this cut: repaired.07 (line at tick 300, outside every segment)",
        "not on screen in this cut: land.03 (line at tick 320, outside every segment)"]


def test_the_audit_names_every_disagreement(tmp_path):
    evs = [line(10, "jump.01"), line(50, "jump.13")]
    a = audit_of(tmp_path, evs, {"jump.01": 1, "land.09": 2})
    assert a.problems == [
        "CAPTIONED BUT NEVER SAID: jump.13 (first drawn at 0.83 s) - the mod's log has no "
        "'jamaltron speech <unit> jump.13'",
        "SAID BUT NOT CAPTIONED: land.09 (logged 2x) - the take has no line or said event for "
        "it: a bubble the game showed that this video cannot caption (an ambient line the "
        "director did not quiet?)"]


def test_a_line_the_mod_never_said_fails_even_off_screen(tmp_path):
    a = audit_of(tmp_path, [line(150, "jump.13")], {})
    assert a.problems == ["A LINE THE MOD NEVER SAID: jump.13 - the take logs it as said, the "
                          "mod's log does not"]


@pytest.mark.parametrize("said,why", [
    # a speech row "replaced" by a line that is not there on that tick: its bubble was up
    (ev(10, "said", row="land.09", channel="speech", replaced_by="land.06", x=0, y=0),
     "UNPROVEN SAID: land.09 (speech, tick 10) - no line land.06 on the same tick"),
    (ev(10, "said", row="land.09", channel="speech", x=0, y=0),
     "no line (replaced_by missing) on the same tick"),
    (ev(10, "said", row="land.08", channel="narration", x=0, y=0),
     "UNPROVEN SAID: land.08 (narration, tick 10) - not speech and not flagged hidden"),
])
def test_a_said_event_is_only_proof_when_it_checks_out(tmp_path, said, why):
    """A director that mislabelled a real ambient bubble as `said` would otherwise pass."""
    a = audit_of(tmp_path, [said, line(10, "land.03")],
                 {said["row"]: 1, "land.03": 1})
    assert len(a.problems) == 1 and why in a.problems[0], a.problems


def test_count_differences_are_noted_not_failed(tmp_path):
    a = audit_of(tmp_path, [line(10, "jump.01")], {"jump.01": 2})
    assert a.problems == [] and a.notes == [
        "jump.01: the mod logged it 2x, the take has 1 line/said event(s)"]


# -------------------------------------------------------------------------------- drawing

def test_wrap_balances_two_lines(fonts):
    font = fonts.get("semibold", 44)
    text = "Jamal does not know the idiom, but Jamal will hop!"
    rows = cap.wrap(text, font, 820)
    assert len(rows) == 2 and " ".join(rows) == text
    w = [font.getlength(r) for r in rows]
    assert max(w) <= 820 and min(w) / max(w) > 0.75             # balanced, no widow
    assert cap.wrap("Jamal is hopping!", font, 820) == ["Jamal is hopping!"]


def test_the_bubble_is_the_game_s_colours_anchored_at_its_bottom_centre(fonts):
    b = cap.render_bubble("Jamal is hopping!", fonts, 1.0)
    w, h = b.image.size
    assert b.image.mode == "RGBA" and b.anchor[1] == h
    assert w > b.anchor[0] * 2 - 1                                # the slant widens the top
    px = [p for p in b.image.get_flattened_data() if p[3] == 255]
    assert any(abs(p[0] - 255) < 8 and abs(p[1] - 246) < 8 and abs(p[2] - 113) < 20
               for p in px), "no text in the game's bubble yellow"
    box = b.image.getpixel((b.anchor[0], h - 3))
    assert box[3] == pytest.approx(cap.BOX_RGBA[3], abs=40) and max(box[:3]) < 60


def test_the_bubble_scales_with_the_capture(fonts):
    big = cap.render_bubble("Jamal is hopping!", fonts, 1.0).image.size
    small = cap.render_bubble("Jamal is hopping!", fonts, 0.5).image.size
    assert small[0] == pytest.approx(big[0] / 2, rel=0.15)


def test_the_tag_sits_in_the_top_right_corner(fonts):
    t = cap.render_tag("5x", fonts, 1.0)
    x, y = cap.tag_position(t.size, GEO)
    assert x + t.size[0] == 1920 - cap.TAG_INSET and y == cap.TAG_INSET
    assert any(p[3] == 255 and p[0] > 240 and 150 < p[1] < 185 for p in t.get_flattened_data())


def test_missing_fonts_are_an_error_naming_the_path(tmp_path, monkeypatch):
    monkeypatch.delenv(cap.FACTORIO_DATA_ENV, raising=False)
    with pytest.raises(cap.FontError, match="TitilliumWeb-SemiBold.ttf"):
        cap.Fonts.factorio(tmp_path)


def test_fonts_are_read_from_the_install_never_the_repo():
    """G.7: nothing from the install enters the repo - no .ttf anywhere under tools/video."""
    root = cap.REPO / "tools" / "video"
    assert not [p for p in root.rglob("*") if p.suffix.lower() in (".ttf", ".otf", ".ogg")]
    assert cap.DEFAULT_FACTORIO_DATA.is_absolute()
    assert not cap.DEFAULT_FACTORIO_DATA.is_relative_to(cap.REPO)


def test_a_caption_image_composites_where_place_says(fonts):
    frame = Image.new("RGB", (1920, 1080), (200, 160, 90))
    b = cap.render_bubble("I did feel the wind in my gills!", fonts, 1.0)
    xy = cap.place(b.image.size, b.anchor, (960, 400), GEO)
    frame.paste(b.image, xy, b.image)
    inside = frame.getpixel((960, 400 - 5))
    assert max(inside) < 120                                   # the dark box, just above anchor
    assert frame.getpixel((960, 400 + 20)) == (200, 160, 90)   # nothing below it
