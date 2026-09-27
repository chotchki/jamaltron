"""C.21 and C.24: the beached flop's config home and the sequence it packs from.

Three layers, bottom up, no Blender:

  * artconfig's OVERLAY loader (C.24) -- render/beached.toml is jamaltron.toml plus only
    what the flop changes, key by key
  * render/sequence.py -- beats in, unique per-frame configs and a play order out
  * pack.py's sequence mode -- one frame out of each config's own cache dir, one sheet, a
    frame_sequence, and lint_sprites checking that frame_sequence like any other field

Plus the committed draft: whatever beats chotchki settles on, a seam that makes him jump
in one frame is a bug in the file, cheaper caught here than by eye.
"""

import json
import pathlib

import pytest
from PIL import Image

import lint_sprites as lint
from render import art
from render import artconfig as ac
from render import pack
from render import pose
from render import sequence


def write(path: pathlib.Path, text: str) -> pathlib.Path:
    path.write_text(text)
    return path


# ------------------------------------------------------------------ C.24: the overlay


def test_an_overlay_replaces_keys_not_tables(tmp_path):
    """`[model] action = ...` in the overlay changes the action and KEEPS the base's scale; a
    table-level replace would silently reset every shared knob to its schema default."""
    write(tmp_path / "base.toml", "[model]\nscale = 0.6\ngirth = 1.4\n[bounce]\nheight = 0.1\n")
    top = write(tmp_path / "top.toml", 'base = "base.toml"\n[model]\naction = "SWIM_FAST"\n'
                                       "[bounce]\nheight = 0.3\n")
    cfg = ac.load(top, env={})
    assert cfg["model.scale"] == 0.6 and cfg["model.girth"] == 1.4
    assert cfg["model.action"] == "SWIM_FAST" and cfg["bounce.height"] == 0.3
    # and the base alone is untouched by the overlay existing
    assert ac.load(tmp_path / "base.toml", env={})["model.action"] == "rest"


def test_an_overlay_hashes_exactly_like_the_same_knobs_in_one_file(tmp_path):
    """The hash is over resolved knobs, not the files they came from, so frames rendered off
    the overlay and off a pasted single file share a cache dir."""
    write(tmp_path / "base.toml", "[model]\nscale = 0.6\n")
    top = write(tmp_path / "top.toml", 'base = "base.toml"\n[model]\nphase_lock = 0.5\n')
    one = write(tmp_path / "one.toml", "[model]\nscale = 0.6\nphase_lock = 0.5\n")
    assert ac.config_hash(ac.load(top, env={})) == ac.config_hash(ac.load(one, env={}))


def test_a_typo_in_an_overlay_names_the_file_it_is_in(tmp_path):
    write(tmp_path / "base.toml", "[model]\nscale = 0.6\n")
    top = write(tmp_path / "top.toml", 'base = "base.toml"\n[model]\nscal = 0.7\n')
    with pytest.raises(ac.ConfigError, match=r"model.scal.*top.toml.*did you mean model.scale"):
        ac.load(top, env={})


def test_a_base_cycle_and_a_missing_base_are_errors_not_hangs(tmp_path):
    write(tmp_path / "a.toml", 'base = "b.toml"\n')
    write(tmp_path / "b.toml", 'base = "a.toml"\n')
    with pytest.raises(ac.ConfigError, match="cycle"):
        ac.load(tmp_path / "a.toml", env={})
    write(tmp_path / "c.toml", 'base = "gone.toml"\n')
    with pytest.raises(ac.ConfigError, match="gone.toml"):
        ac.load(tmp_path / "c.toml", env={})


def test_sequence_is_not_a_knob_and_comes_from_the_topmost_file(tmp_path):
    """[sequence] is the one non-knob table a config file may carry: it skips the
    unknown-knob check and does not merge key by key (a frame list is one statement)."""
    write(tmp_path / "base.toml", '[sequence]\nname = "a"\ndirection = 0\n')
    top = write(tmp_path / "top.toml", 'base = "base.toml"\n[sequence]\nname = "b"\n')
    assert ac.load_sequence(top) == {"name": "b"}
    assert ac.load_sequence(tmp_path / "base.toml")["name"] == "a"
    ac.load(top, env={})                      # no unknown-knob error for [sequence]


def test_overlay_of_gives_the_base_and_the_overlays_own_keys(tmp_path):
    write(tmp_path / "base.toml", "[model]\nscale = 0.6\n")
    top = write(tmp_path / "top.toml", 'base = "base.toml"\n[model]\nphase_lock = 0.5\n'
                                       '[sequence]\nname = "x"\n')
    base, own = ac.overlay_of(top)
    assert base["model.scale"] == 0.6 and base["model.phase_lock"] == 0.0
    assert own == {"model.phase_lock": 0.5}
    assert ac.overlay_of(tmp_path / "base.toml") is None


def test_the_committed_beached_config_is_the_c52_call_on_the_standing_shark():
    """render/beached.toml is jamaltron.toml plus the flop: every shared knob comes from the
    base (so the two sheets cannot drift), and the flop knobs are chotchki's calls."""
    standing = ac.load(env={})
    beached = ac.load(ac.BEACHED_CONFIG_PATH, env={})
    for key in ("model.scale", "model.girth", "model.pivot", "sun.azimuth", "camera.pitch",
                "mask.mode", "render.samples"):
        assert beached[key] == standing[key], key
    assert beached["model.action"] == "SWIM_FAST"
    assert beached["model.rotation"] == [85.0, 0.0, 180.0]
    # C.5.8's V5 (chotchki 2026-09-26): the standing wave (lock + recentre + evened swing),
    # lower fin held to the floor so the U does not swing it into a spike. C.5.9 toned it to
    # gain 1.25 and re-phased the bounce to land where the midsection starts to push
    assert beached["model.phase_lock"] == 1.0 and beached["bounce.phase"] == 0.4
    assert beached["model.recentre"] == beached["model.amplitude_even"] == 1.0
    assert beached["model.pose_gain"] == 1.25
    assert beached["model.fin_floor"] and not standing["model.fin_floor"]
    assert beached["bounce.height"] == 0.3
    assert beached["model.reparent_head"] and beached["model.ground_contact"]
    # C.5.6: he lies on his body, not a fin tip, and the standing shark does not
    assert beached["model.ground_ignore"] and not standing["model.ground_ignore"]
    assert not standing["model.spine_sag"]
    _, own = ac.overlay_of(ac.BEACHED_CONFIG_PATH)
    assert "model.scale" not in own and "model.girth" not in own


# --------------------------------------------------------------- C.21: the sequence


def base_cfg(**over):
    cfg = ac.resolve({"model": {"action": "SWIM_FAST", "reparent_head": True,
                                "ground_contact": True},
                      "bounce": {"height": 0.3, "phase": 0.5}}, env={})
    cfg.update(over)
    return cfg


def table(*beats, name="flop", direction=16):
    return {"name": name, "direction": direction, "beat": list(beats)}


def test_a_beat_defaults_to_the_whole_clip():
    seq = sequence.parse(table({"name": "heave"}), base_cfg())
    assert [f for _, f in seq.played] == list(range(1, 21))
    assert [c["model.frame"] for c in seq.configs] == list(range(1, 21))
    assert seq.frame_sequence() is None          # plays straight through: frame_count says it


def test_repeats_and_holds_are_free_cells():
    """Two heaves and a held frame: 20 + 20 + 5 played, still 20 unique renders."""
    seq = sequence.parse(table({"name": "heave"}, {"name": "heave"},
                               {"name": "hold", "frames": [7, 7], "hold": 5}), base_cfg())
    assert len(seq.order) == 45 and len(seq.configs) == 20
    fs = seq.frame_sequence()
    assert fs[:20] == fs[20:40] == list(range(1, 21))
    assert fs[40:] == [7] * 5


def test_a_backwards_beat_reuses_the_forward_cells():
    seq = sequence.parse(table(
        {"name": "snap", "frames": [1, 9], "stride": 2},
        {"name": "release", "frames": [7, 1], "stride": 2}), base_cfg())
    assert [f for _, f in seq.played] == [1, 3, 5, 7, 9, 7, 5, 3, 1]
    assert len(seq.configs) == 5


def test_a_ramp_is_linear_across_the_beat_and_rounded_to_dedupe():
    seq = sequence.parse(table({"name": "settle", "frames": [1, 5],
                                "ramp": {"model.pose_gain": [1.0, 0.2]}}), base_cfg())
    assert [c["model.pose_gain"] for c in seq.configs] == [1.0, 0.8, 0.6, 0.4, 0.2]


def test_per_beat_sets_override_the_file_and_resolve_like_knobs():
    seq = sequence.parse(table({"name": "bite", "frames": [1, 3],
                                "set": {"model.action": "BITE_01", "bounce.height": 0.0}}),
                         base_cfg())
    assert {c["model.action"] for c in seq.configs} == {"BITE_01"}
    assert {c["bounce.height"] for c in seq.configs} == {0.0}


@pytest.mark.parametrize("bad,match", [
    ({"name": "x", "frames": [1, 21]}, "outside SWIM_FAST's 1-20"),
    ({"name": "x", "frames": [0, 5]}, "outside"),
    ({"name": "x", "strid": 2}, "unknown key"),
    ({"frames": [1, 2]}, "needs a name"),
    ({"name": "x", "set": {"model.scal": 1.0}}, "did you mean model.scale"),
    ({"name": "x", "set": {"model.frame": 3}}, "through `frames`"),
    ({"name": "x", "ramp": {"model.action": ["a", "b"]}}, "not a number knob"),
    ({"name": "x", "ramp": {"model.pose_gain": [1.0]}}, r"\[start, end\]"),
    ({"name": "x", "set": {"model.pose_gain": 1.0}, "ramp": {"model.pose_gain": [1, 2]}},
     "both set and ramped"),
    ({"name": "x", "hold": 0}, "hold"),
    ({"name": "x", "set": {"model.action": "SWIM_FASTT"}}, "not one of"),
])
def test_a_bad_beat_is_refused_and_named(bad, match):
    with pytest.raises(ac.ConfigError, match=match):
        sequence.parse(table(bad), base_cfg())


def test_the_sequence_table_itself_is_checked():
    with pytest.raises(ac.ConfigError, match="direction"):
        sequence.parse(table({"name": "x"}, direction=64), base_cfg())
    with pytest.raises(ac.ConfigError, match="name"):
        sequence.parse(table({"name": "x"}, name="has space"), base_cfg())
    with pytest.raises(ac.ConfigError, match="at least one"):
        sequence.parse({"name": "x", "direction": 0, "beat": []}, base_cfg())
    with pytest.raises(ac.ConfigError, match="unknown key"):
        sequence.parse(dict(table({"name": "x"}), fps=24), base_cfg())


def test_factorios_255_frame_cap_is_enforced():
    beats = [{"name": "h%d" % i} for i in range(13)]              # 260 played
    with pytest.raises(ac.ConfigError, match="255"):
        sequence.parse(table(*beats), base_cfg())


def test_the_digest_moves_with_any_frame_or_the_order():
    one = sequence.parse(table({"name": "heave"}), base_cfg())
    lock = sequence.parse(table({"name": "heave", "frames": [1, 20],
                                 "set": {"model.phase_lock": 0.25}}), base_cfg())
    rev = sequence.parse(table({"name": "heave", "frames": [20, 1]}), base_cfg())
    assert len({one.digest, lock.digest, rev.digest}) == 3


# ---------------------------------------------------- the committed draft, seam by seam


@pytest.fixture(scope="module")
def beached():
    return sequence.load(ac.BEACHED_CONFIG_PATH)


def test_the_committed_sequence_expands_inside_factorios_limits(beached):
    assert beached.name == "beached" and beached.direction == 16
    assert len(beached.order) <= sequence.MAX_PLAYED
    assert len(beached.configs) < len(beached.order)        # repeats are doing their job
    for cfg in beached.configs:
        assert not ac.warnings(cfg), (ac.config_hash(cfg), ac.warnings(cfg))


def test_no_seam_in_the_committed_sequence_pops_the_bounce(beached):
    """THE SEAM CHECK. At bounce phase 0.4 the heave's flight ends on its last frame and he
    lands on f1, so a beat handing into a heave falls the same way and a beat following one
    starts on the ground. No lift step in the cycle (wrap included) may exceed the heave's
    own in-loop step; anything bigger is a jump between frames meant to be continuous."""
    lifts = [ac.bounce_lift(beached.configs[k]) for k in beached.order]
    heave = [ac.bounce_lift(dict(beached.configs[0], **{"model.frame": f}))
             for f in range(1, 21)]
    in_loop = max(abs(heave[i] - heave[i - 1]) for i in range(20))
    steps = [abs(lifts[i] - lifts[i - 1]) for i in range(len(lifts))]
    worst = max(range(len(steps)), key=steps.__getitem__)
    assert steps[worst] <= in_loop + 1e-9, (worst, beached.played[worst - 1],
                                            beached.played[worst], steps[worst], in_loop)


def test_the_tail_sags_only_where_he_lies_still(beached):
    """C.5.6: model.spine_sag lays the tail on the sand, but where the tail ALREADY seats him
    it only stands the rest of him up (MEASURED, 0.33-0.41 tiles of trunk on the heave's
    flicks at 3.25). So the heave carries none (its cells stay chotchki's C.5.2 call), the
    lying beats carry it, and every value is inside the rail."""
    by_beat = {}
    for k, (name, _) in zip(beached.order, beached.played):
        by_beat.setdefault(name, set()).add(beached.configs[k]["model.spine_sag"])
    assert by_beat["heave"] == {0.0}
    assert by_beat["pause"] == {4.0} and by_beat["snap"] == by_beat["release"] == {2.5}
    assert min(by_beat["settle"]) == 0.0 and max(by_beat["settle"]) == 4.0, "ramps into the pause"
    assert max(by_beat["twitch"]) <= 2.5 and min(by_beat["twitch"]) == 0.0, "ramps back out"
    for cfg in beached.configs:
        assert 0.0 <= cfg["model.spine_sag"] <= ac.SPINE_SAG_LEVEL


#: C.5.8 V5's seat lists. HEAD takes his weight on the ARCHES; on a flat beat the lowest thing
#: HEAD owns is the hammer's lower tip, and seating on it props him 0.14-0.22 up (C.5.6).
V5_SEAT = ["FIN_LEFT", "FIN_RIGHT", "JAW"]
FLAT_SEAT = ["FIN_LEFT", "FIN_RIGHT", "HEAD", "JAW"]


def test_v5_lets_the_head_seat_only_on_the_arching_frames(beached):
    """The heave, the settle's first five frames (carrying the heave's arch in) and the
    twitch from f10 take the V5 list; everything nearer rest keeps the C+ one. At the switch
    frames (twitch f9/f10, gain 1.25) BOTH lists seat him on the same vertex (MEASURED in
    Blender, not checkable here), so this pins the cut where it was measured. The settle's
    f5/f6 has no such frame below gain 2.0; the ground_sink ramp closes that gap instead
    (test_the_settle_sinks_across_its_seat_switch)."""
    seat = {}
    for k, (name, f) in zip(beached.order, beached.played):
        seat.setdefault((name, f), beached.configs[k]["model.ground_ignore"])
    for (name, f), got in seat.items():
        arch = (name == "heave" or (name == "settle" and f <= 5)
                or (name == "twitch" and f >= 10))
        assert got == (V5_SEAT if arch else FLAT_SEAT), (name, f, got)


@pytest.mark.parametrize("beat,first,last", [("settle", 1, 20), ("twitch", 3, 20)])
def test_a_split_beat_is_still_one_ramp(beached, beat, first, last):
    """The settle and twitch are cut in two for the seat list, each half with its own
    hand-written ramp that could kink at the cut. Every ramped knob across both halves lies
    on ONE line from first frame to last (inside the 4-place rounding) -- except the
    settle's ground_sink, a deliberate per-half seat correction owned by
    test_the_settle_sinks_across_its_seat_switch."""
    by_frame = {}
    for k, (name, f) in zip(beached.order, beached.played):
        if name == beat:
            by_frame[f] = beached.configs[k]
    assert sorted(by_frame) == list(range(first, last + 1))
    ramped = set()
    for b in beached.beats:
        if b.name == beat:
            ramped |= set(b.ramps)
    assert ramped, beat
    for key in sorted(ramped - {"model.ground_sink"}):
        a, z = by_frame[first][key], by_frame[last][key]
        for f, cfg in by_frame.items():
            want = a + (z - a) * (f - first) / (last - first)
            assert cfg[key] == pytest.approx(want, abs=2e-4), (beat, key, f)


def test_the_u_runs_down_into_the_c_plus_pause_and_the_bite_carries_none_of_it(beached):
    """MEASURED: at V5's knobs the pause stood 0.11 tiles higher on its tail than the snap's
    rest shape and the hammer dropped 7 px into the bite; the C+ pause meets it within 0.01.
    So the settle ramps the U out and the pause is C+'s. The bite has no curl or body turn
    for the U to act on, so snap and release are the C+ renders, hash for hash (bounce.phase
    pinned to C+'s 0.5 there: at height 0 it moves no pixel, but it is in the hash)."""
    pause = {beached.configs[k]["model.phase_lock"] for k, (n, _) in
             zip(beached.order, beached.played) if n == "pause"}
    assert pause == {0.5}
    for k, (name, _) in zip(beached.order, beached.played):
        cfg = beached.configs[k]
        if name in ("pause", "snap", "release"):
            assert cfg["model.recentre"] == cfg["model.amplitude_even"] == 0.0, name
        if name in ("snap", "release"):
            assert not cfg["model.fin_floor"] and cfg["model.phase_lock"] == 0.0, name
    settle = [beached.configs[k] for k, (n, _) in zip(beached.order, beached.played)
              if n == "settle"]
    assert settle[0]["model.recentre"] == 1.0 and settle[-1]["model.recentre"] == 0.0
    assert settle[0]["model.pose_gain"] == beached.configs[0]["model.pose_gain"] == 1.25, \
        "it starts where the heave is"
    # the pause IS the settle's last frame, and the twitch's f20 IS the heave's: no new render
    idx = {(n, f): k for k, (n, f) in zip(beached.order, beached.played)}
    assert idx[("pause", 20)] == idx[("settle", 20)]
    assert idx[("twitch", 20)] == idx[("heave", 20)]


def test_the_bite_cells_are_the_c_plus_renders_whatever_the_bounce_does(shipped_model):
    """C.5.9's re-phase moved every snap/release hash (same pixels, 15 redundant renders)
    because they inherited [bounce].phase at height 0. Now pinned: re-phasing or
    re-heighting the bounce leaves the bite alone and its ends are the C+ cells. Hashed on
    the shipped model's digest, so a runner with no model matches this machine."""
    def bite(overrides=None):
        base = shipped_model(ac.load(ac.BEACHED_CONFIG_PATH, overrides, env={}))
        seq = sequence.parse(ac.load_sequence(ac.BEACHED_CONFIG_PATH), base)
        return {(n, f): ac.pass_hash(seq.configs[k], "body")
                for k, (n, f) in zip(seq.order, seq.played) if n in ("snap", "release")}
    shipped = bite()
    assert shipped[("snap", 1)] == "0ebbaa54d210" and shipped[("snap", 29)] == "d011942b99a0"
    assert bite({"bounce.phase": 0.33, "bounce.height": 0.5}) == shipped


def test_the_twitch_starts_from_the_release_rest_shape(beached):
    """V5's f3 is the deep arch, so a twitch opening at any real gain starts on a pose the
    release never passed through (MEASURED at the draft's 0.8: 0.45 tiles, 23 px, of trunk
    in one frame). At gain 0 it is the rest shape the release ends on."""
    first = next(beached.configs[k] for k, (n, _) in zip(beached.order, beached.played)
                 if n == "twitch")
    assert first["model.pose_gain"] == 0.0
    assert first["model.ground_ignore"] == FLAT_SEAT


def test_the_heave_lands_on_the_push_and_leaves_off_it(beached):
    """C.5.9, chotchki 2026-09-26: "he should be lowest as he starts to push down with his
    midsection". MEASURED at gain 1.25 (Blender, the trunk against the hammer-tail chord):
    the midsection tops out on f1 and drives down f1 -> f11, 94% of it by f9. So the heave
    is on the sand f1-f9 (landing ON the onset) and airborne f10-f20. At the old 0.5 he
    launched off the U (f11) and landed on f3, pushing in mid-air."""
    heave = [ac.bounce_lift(dict(beached.configs[0], **{"model.frame": f}))
             for f in range(1, 21)]
    assert heave[:9] == [0.0] * 9, "on the sand from the landing through the push"
    assert all(h > 0.0 for h in heave[9:]), "airborne from f10 until he lands on f1"
    assert max(heave) == pytest.approx(beached.configs[0]["bounce.height"], abs=1e-3)


def test_the_settle_starts_on_the_heaves_landing_and_never_launches(beached):
    """SWIM_MEDIUM is the swim at half tempo, a 40-frame cycle; bounce.phase 0.7 puts its
    launch on f29, 12 frames before f1 like the heave's f9, so the settle opens on the same
    landing and its own launch falls past the beat's last frame."""
    for k, (name, _) in zip(beached.order, beached.played):
        if name in ("settle", "pause"):
            assert ac.bounce_lift(beached.configs[k]) == 0.0, name


def test_the_settle_sinks_across_its_seat_switch(beached):
    """Below gain 2.0 the settle's f5/f6 has no frame where both seat lists agree: at 1.25 the
    V5 list seats f5 on the hammer 0.1366 below where the C+ list seats it on the tail
    (MEASURED), a 0.219-tile trunk jump. So ground_sink ramps 0.04 -> 0.04 + 0.1366 over
    f1-f5 (f1 still the heave's 0.04) and f6 continues from f5; the hammer sinks that much
    under the sand at f5, hidden by the holdout ground."""
    sink = {}
    for k, (name, f) in zip(beached.order, beached.played):
        if name == "settle":
            sink[f] = beached.configs[k]["model.ground_sink"]
    base = beached.configs[0]["model.ground_sink"]
    assert sink[1] == base == 0.04
    assert sink[5] == pytest.approx(base + 0.1366, abs=1e-4)
    assert [sink[f] for f in range(1, 6)] == sorted(sink[f] for f in range(1, 6))
    assert all(sink[f] == base for f in range(6, 21))


def test_the_cycle_ends_where_it_starts(beached):
    """The last played frame hands to the first (same clip, next frame, same gain), so the
    loop Factorio plays forever has no seam."""
    first, last = beached.configs[beached.order[0]], beached.configs[beached.order[-1]]
    assert first["model.action"] == last["model.action"] == "SWIM_FAST"
    assert first["model.pose_gain"] == last["model.pose_gain"]
    assert first["model.spine_sag"] == last["model.spine_sag"]
    clip = pose.clip_of("SWIM_FAST")
    assert (last["model.frame"] % clip.span) + 1 == first["model.frame"]


# ------------------------------------------------------------- pack: gather + lint


def fake_render(seq):
    """Synthetic frames in each unique config's OWN cache dir, at art.py's exact path, for
    every pass the sequence ships at preview samples."""
    for k, c in enumerate(seq.configs):
        for which, _, _ in art.SEQUENCE_PASSES:
            if which not in seq.passes:
                continue
            samples = art.sequence_samples(c, which, True)
            d = art.pass_dir(c, which, samples)
            d.mkdir(parents=True)
            px = 384 if which != "shadow" else 704
            img = Image.new("RGBA", (px, px), (0, 0, 0, 0))
            img.paste((200, 90, 90, 255), (150 + 4 * k, 150, 230 + 4 * k, 200))
            img.save(d / ("frame_%03d.png" % seq.direction))
            (d / "config.json").write_text(json.dumps(ac.stamp(c, {"pass": which})))
    return seq


@pytest.fixture
def rendered(tmp_path):
    """A 3-unique / 5-played sequence, fake-rendered."""
    cfg = base_cfg(**{"output.dir": str(tmp_path / "render-out")})
    seq = sequence.parse(table({"name": "a", "frames": [1, 3]},
                               {"name": "b", "frames": [2, 1]}, direction=5), cfg)
    return fake_render(seq), tmp_path


def test_pack_gathers_one_frame_per_config_and_plays_them_in_order(rendered):
    seq, tmp = rendered
    out = tmp / "mod"
    packed = pack.pack_sequence(seq, out, mod_name="jamaltron", preview=True)
    assert [p.target.id for p in packed] == ["body", "body_mask", "shadow"]
    for item in packed:
        assert item.fields["frame_count"] == 3
        assert item.fields["frame_sequence"] == [1, 2, 3, 2, 1]
        assert "direction_count" not in item.fields
        # end to end, not just sprite_fields: without it the engine plays a cell a tick
        assert item.fields["animation_speed"] == pack.sequence_speed()
        assert item.paths[0].name.startswith("jamaltron-flop-")
    # and the linter reads the frame_sequence it was handed, through BOTH front ends
    manifest = out / "graphics" / "flop-sprites.json"
    manifest.write_text(json.dumps(pack.manifest_blob(seq.configs[0], packed,
                                                      mod_name="jamaltron", seq=seq)))
    lua = out / "prototypes" / "flop_sprites_generated.lua"
    lua.parent.mkdir(parents=True)
    lua.write_text(pack.lua_blob(seq.configs[0], packed, seq=seq, origin="render/x.toml"))
    mods = lint.ModPaths()
    mods.add("jamaltron", out)
    findings, declarations, _ = lint.lint([manifest, lua], mods, strict=True)
    assert declarations == 6 and not findings, [f.render() for f in findings]
    assert seq.digest in lua.read_text() and "GENERATED by tools/render/pack.py" in lua.read_text()


def test_pack_names_every_missing_frame_at_once(rendered):
    seq, _ = rendered
    body = art.pass_dir(seq.configs[1], "body", art.sequence_samples(seq.configs[1], "body", True))
    (body / "frame_005.png").unlink()
    with pytest.raises(pack.PackError, match=r"(?s)1 of 3 sequence frames.*\[1\].*--sequence --preview"):
        pack.pack_sequence(seq, rendered[1] / "mod", mod_name="jamaltron", preview=True)


def test_pack_refuses_a_stale_frame_anywhere_in_the_sequence(rendered):
    """Each directory is checked against ITS OWN config: one stale sidecar in 72 stops it."""
    seq, _ = rendered
    c = seq.configs[2]
    d = art.pass_dir(c, "shadow", art.sequence_samples(c, "shadow", True))
    moved = dict(c, **{"sun.energy": 99.0})
    (d / "config.json").write_text(json.dumps(ac.stamp(moved, {"pass": "shadow"})))
    with pytest.raises(pack.PackError, match="pass hash"):
        pack.pack_sequence(seq, rendered[1] / "mod", mod_name="jamaltron", preview=True)


def test_a_long_number_list_wraps_under_luachecks_120_columns():
    text = pack.lua_value(list(range(1, 118)), "  ")
    assert max(len(line) for line in text.splitlines()) <= 120
    assert text.count("\n") >= 5
    assert pack.lua_value([1, 2, 3], "") == "{1, 2, 3}"


def spec(**fields):
    base = {"filename": "__m__/x.png", "width": 10, "height": 10, "line_length": 3,
            "frame_count": 3}
    base.update(fields)
    return lint.spec_from_table("t", lint._jsonify(base))


@pytest.mark.parametrize("played,code", [
    ([1, 2, 3, 2], None),
    ([0, 1, 2, 3], "frame-sequence"),                 # 1-based: 0 is off the front
    ([1, 2, 3, 4], "frame-sequence"),                 # past frame_count
    ([], "frame-sequence"),
    ([1] * 256 + [2, 3], "frame-sequence"),           # Factorio's 255 cap
    ([1, 2, 1], "unused-frames"),                     # frame 3 never plays (--strict)
])
def test_lint_checks_the_frame_sequence(tmp_path, played, code):
    img = Image.new("RGBA", (30, 10), (0, 0, 0, 255))
    img.save(tmp_path / "x.png")
    mods = lint.ModPaths()
    mods.add("m", tmp_path)
    codes = {f.code for f in lint.check_spec(spec(frame_sequence=played), mods, strict=True)}
    assert codes == ({code} if code else set()), codes


# --------------------------------------------------------------- art: the fan-out


def test_render_sequence_is_every_config_times_every_pass_at_one_direction(monkeypatch):
    seq = sequence.parse(table({"name": "a", "frames": [1, 3]},
                               {"name": "b", "frames": [2, 2], "hold": 4}, direction=9),
                         base_cfg())
    calls = []

    def fake(cfg, which, frames, samples, **kw):
        calls.append((ac.config_hash(cfg), which, tuple(frames), samples, kw["quiet"]))
        return None, {"rendered": 1, "cached": 0}

    monkeypatch.setattr(art, "render_pass", fake)
    stats = art.render_sequence(seq, preview=True, jobs=3)
    assert len(calls) == 3 * 3                                 # unique configs x passes
    assert {c[2] for c in calls} == {(9,)}
    assert {c[4] for c in calls} == {True}
    cfg = seq.configs[0]
    assert {(c[1], c[3]) for c in calls} == {
        ("body", cfg["render.preview_samples"]), ("mask", cfg["render.preview_samples"]),
        ("shadow", cfg["render.shadow_samples"])}
    assert stats["body"]["rendered"] == 3


def test_the_preview_gif_plays_every_played_frame_at_24fps(rendered):
    seq, _ = rendered
    path = art.sequence_gif(seq, preview=True)
    gif = Image.open(path)
    assert gif.n_frames == len(seq.order) == 5
    delays = []
    for i in range(gif.n_frames):
        gif.seek(i)
        delays.append(gif.info["duration"])
    assert delays == [40, 40, 40, 40, 40]
    assert sum(art.GIF_DELAYS_MS) / len(art.GIF_DELAYS_MS) == pytest.approx(1000 / pose.FPS, abs=0.01)
    side = json.loads(path.with_suffix(".json").read_text())
    assert side["digest"] == seq.digest and side["order"] == list(seq.order)


# ------------------------------------------------------- the review's findings, pinned


def test_a_sequence_sheet_is_stamped_with_the_sequence_not_one_frame(rendered):
    """The PNG chunk is the provenance. For a sequence it was frame 0's config (one of N, a
    different id from the manifest and the Lua); now all three say the digest and the chunk
    holds every frame's hash, the order and the samples."""
    seq, tmp = rendered
    packed = pack.pack_sequence(seq, tmp / "mod", mod_name="jamaltron", preview=True)
    text = Image.open(packed[0].paths[0]).text
    assert text["jamaltron:config_hash"] == seq.digest
    stamp = json.loads(text["jamaltron:sequence"])
    assert stamp["frame_hashes"] == list(seq.hashes) and stamp["order"] == list(seq.order)
    assert stamp["samples"]["body"] == seq.configs[0]["render.preview_samples"]
    assert [b["name"] for b in stamp["beats"]] == ["a", "b"]
    assert "jamaltron:config" not in text          # no one config made this sheet


def test_pack_main_warns_on_a_preview_sequence_and_names_its_config_truly(tmp_path, capsys):
    tmp = tmp_path
    flop = tmp / "flop.toml"
    rows = ['base = "%s"' % ac.DEFAULT_CONFIG_PATH,
            '[model]', 'action = "SWIM_FAST"', "reparent_head = true",
            "ground_contact = true", '[bounce]', "height = 0.3", "phase = 0.5",
            '[output]', 'dir = "%s"' % (tmp / "render-out"),
            '[sequence]', 'name = "flop"', "direction = 5",
            '[[sequence.beat]]', 'name = "a"', "frames = [1, 3]",
            '[[sequence.beat]]', 'name = "b"', "frames = [2, 1]"]
    flop.write_text("\n".join(rows) + "\n")
    fake_render(sequence.load(flop))
    assert pack.main(["--config", str(flop), "--preview", "--out", str(tmp / "mod"),
                      "--no-verify"]) == 0
    out = capsys.readouterr().out
    assert "WARN packed at PREVIEW samples" in out
    lua = (tmp / "mod" / "prototypes" / "flop_sprites_generated.lua").read_text()
    assert "from %s." % flop in lua                 # outside tools/ and the repo: as given
    manifest = json.loads((tmp / "mod" / "graphics" / "flop-sprites.json").read_text())
    assert manifest["sequence"]["samples"]["body"] == 16
    assert pack.config_label(ac.BEACHED_CONFIG_PATH) == "render/beached.toml"


@pytest.mark.parametrize("beat,match", [
    ({"name": "x", "set": ["model.action"]}, "`set` is a table"),
    ({"name": "x", "ramp": "model.pose_gain"}, "`ramp` is a table"),
    ({"name": "x", "set": {"model.scal": 1.0}}, r"unknown knob 'model.scal' in set"),
])
def test_a_malformed_beat_is_a_config_error_not_a_traceback(beat, match):
    with pytest.raises(ac.ConfigError, match=match):
        sequence.parse(table(beat), base_cfg())


def test_lint_refuses_a_sparse_or_keyed_lua_frame_sequence(tmp_path):
    for body, why in (("{[1] = 1, [3] = 2}", "hole"), ('{[1] = 1, x = 2}', "string key")):
        (tmp_path / "s.lua").write_text(
            'local s = {filename = "__m__/x.png", width = 10, height = 10, line_length = 3, '
            "frame_count = 3, frame_sequence = %s}\n" % body)
        specs = lint.specs_from_lua(tmp_path / "s.lua")
        assert any(k == "frame_sequence" for k, _ in specs[0].bad_fields), why


# ------------------------------------------- the harness broke off with his legs (2026-09-26)


def test_a_sequence_ships_all_three_passes_unless_it_says_less():
    seq = sequence.parse(table({"name": "a", "frames": [1, 2]}), base_cfg())
    assert seq.passes == sequence.PASSES == ("body", "mask", "shadow")
    some = sequence.parse(dict(table({"name": "a", "frames": [1, 2]}),
                               passes=["shadow", "body"]), base_cfg())
    assert some.passes == ("body", "shadow")                   # PASSES order, not the file's
    assert some.provenance()["passes"] == ["body", "shadow"]


@pytest.mark.parametrize("passes,match", [
    (["body", "harness"], "unknown pass"),
    (["shadow"], "must include body"),
    (["body", "body"], "twice"),
    ([], "list of pass names"),
    ("body", "list of pass names"),
])
def test_a_bad_passes_list_is_refused(passes, match):
    with pytest.raises(ac.ConfigError, match=match):
        sequence.parse(dict(table({"name": "a"}), passes=passes), base_cfg())


def test_dropping_a_pass_moves_no_hash():
    """Why it is config-level: the body and shadow frames that stay are the SAME cache
    entries, so dropping the harness re-packs with no Blender launch."""
    raw = table({"name": "a", "frames": [1, 3]})
    every = sequence.parse(raw, base_cfg())
    fewer = sequence.parse(dict(raw, passes=["body", "shadow"]), base_cfg())
    assert fewer.hashes == every.hashes and fewer.digest == every.digest
    for a, b in zip(every.configs, fewer.configs):
        for which in ("body", "shadow"):
            assert ac.pass_hash(a, which) == ac.pass_hash(b, which)


def test_the_committed_beached_sequence_ships_no_harness(beached):
    """chotchki 2026-09-26: "the beached jamal shouldn't have the harness on it anymore"."""
    assert beached.passes == ("body", "shadow")
    assert [t.id for t in pack.sequence_targets(beached.name, beached.passes)] == [
        "body", "shadow"]


def test_render_sequence_renders_only_the_passes_it_ships(monkeypatch):
    seq = sequence.parse(dict(table({"name": "a", "frames": [1, 3]}, direction=9),
                              passes=["body", "shadow"]), base_cfg())
    calls = []

    def fake(cfg, which, frames, samples, **kw):
        calls.append(which)
        return None, {"rendered": 1, "cached": 0}

    monkeypatch.setattr(art, "render_pass", fake)
    stats = art.render_sequence(seq, preview=True, jobs=2)
    assert sorted(calls) == ["body"] * 3 + ["shadow"] * 3
    assert "mask" not in stats


@pytest.fixture
def unharnessed(tmp_path):
    """The `rendered` sequence shipping body + shadow, with NO mask frame on disk at all."""
    cfg = base_cfg(**{"output.dir": str(tmp_path / "render-out")})
    seq = sequence.parse(dict(table({"name": "a", "frames": [1, 3]},
                                    {"name": "b", "frames": [2, 1]}, direction=5),
                              passes=["body", "shadow"]), cfg)
    return fake_render(seq), tmp_path


def test_a_sequence_that_ships_no_mask_packs_none_and_lints_clean(unharnessed):
    seq, tmp = unharnessed
    out = tmp / "mod"
    packed = pack.pack_sequence(seq, out, mod_name="jamaltron", preview=True)
    assert [p.target.id for p in packed] == ["body", "shadow"]
    assert pack.slot_map(packed) == {"animation": ["body"], "shadow_animation": ["shadow"]}
    assert not any(p.fields.get("apply_runtime_tint") for p in packed)
    manifest = out / "graphics" / "flop-sprites.json"
    manifest.write_text(json.dumps(pack.manifest_blob(
        seq.configs[0], packed, mod_name="jamaltron", seq=seq,
        samples=pack.sequence_samples_of(seq, True))))
    blob = json.loads(manifest.read_text())
    assert blob["sequence"]["passes"] == ["body", "shadow"]
    assert set(blob["sequence"]["samples"]) == {"body", "shadow"}
    lua = out / "prototypes" / "flop_sprites_generated.lua"
    lua.parent.mkdir(parents=True)
    lua.write_text(pack.lua_blob(seq.configs[0], packed, seq=seq, origin="render/x.toml"))
    assert "body_mask" not in lua.read_text()
    mods = lint.ModPaths()
    mods.add("jamaltron", out)
    findings, declarations, _ = lint.lint([manifest, lua], mods, strict=True)
    assert declarations == 4 and not findings, [f.render() for f in findings]


def test_drop_unshipped_takes_the_dropped_sheet_and_nothing_else(unharnessed):
    seq, tmp = unharnessed
    graphics = tmp / "mod" / "graphics"
    graphics.mkdir(parents=True)
    keep = ["jamaltron-flop-body.png", "jamaltron-flop-body-shadow.png",
            "jamaltron-flop-body-2.png", "jamaltron-flop-body-mask-x.png",
            "jamaltron-body-mask.png"]                    # the STANDING mask is not ours
    drop = ["jamaltron-flop-body-mask.png", "jamaltron-flop-body-mask-2.png"]
    for name in keep + drop:
        (graphics / name).write_bytes(b"x")
    gone = pack.drop_unshipped(seq, tmp / "mod")
    assert sorted(p.name for p in gone) == sorted(drop)
    assert sorted(p.name for p in graphics.iterdir()) == sorted(keep)
    everything = sequence.parse(dict(table({"name": "a"})), base_cfg())
    assert pack.drop_unshipped(everything, tmp / "mod") == []      # ships all: drops nothing


def test_pack_main_removes_the_mask_sheet_a_harnessless_sequence_left(tmp_path, capsys):
    flop = tmp_path / "flop.toml"
    rows = ['base = "%s"' % ac.DEFAULT_CONFIG_PATH,
            '[model]', 'action = "SWIM_FAST"',
            '[output]', 'dir = "%s"' % (tmp_path / "render-out"),
            '[sequence]', 'name = "flop"', "direction = 5", 'passes = ["body", "shadow"]',
            '[[sequence.beat]]', 'name = "a"', "frames = [1, 3]"]
    flop.write_text("\n".join(rows) + "\n")
    fake_render(sequence.load(flop))
    stale = tmp_path / "mod" / "graphics" / "jamaltron-flop-body-mask.png"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"from an earlier pack")
    assert pack.main(["--config", str(flop), "--preview", "--out", str(tmp_path / "mod")]) == 0
    out = capsys.readouterr().out
    assert not stale.exists() and "removed" in out and "body+shadow" in out
    manifest = json.loads((tmp_path / "mod" / "graphics" / "flop-sprites.json").read_text())
    assert [s["id"] for s in manifest["sprites"]] == ["body", "shadow"]
    assert manifest["slots"] == {"animation": ["body"], "shadow_animation": ["shadow"]}
