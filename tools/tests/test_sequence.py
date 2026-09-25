"""C.21 and C.24: the beached flop's config home and the sequence it packs from.

Three layers, tested bottom up, none of them launching Blender:

  * artconfig's OVERLAY loader (C.24) -- render/beached.toml is jamaltron.toml plus only
    what the flop changes, key by key
  * render/sequence.py -- beats in, unique per-frame configs and a play order out
  * pack.py's sequence mode -- one frame out of each config's own cache dir, one sheet, a
    frame_sequence, and lint_sprites checking that frame_sequence like any other field

Plus the committed draft itself: whatever beats chotchki settles on, a seam that makes him
jump in one frame is a bug in the file, and it is cheap to catch here rather than by eye.
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
    """`[model] action = ...` in the overlay changes the action and KEEPS the base's scale.
    A table-level replace would silently reset every shared knob to its schema default."""
    write(tmp_path / "base.toml", "[model]\nscale = 0.6\ngirth = 1.4\n[bounce]\nheight = 0.1\n")
    top = write(tmp_path / "top.toml", 'base = "base.toml"\n[model]\naction = "SWIM_FAST"\n'
                                       "[bounce]\nheight = 0.3\n")
    cfg = ac.load(top, env={})
    assert cfg["model.scale"] == 0.6 and cfg["model.girth"] == 1.4
    assert cfg["model.action"] == "SWIM_FAST" and cfg["bounce.height"] == 0.3
    # and the base alone is untouched by the overlay existing
    assert ac.load(tmp_path / "base.toml", env={})["model.action"] == "rest"


def test_an_overlay_hashes_exactly_like_the_same_knobs_in_one_file(tmp_path):
    """The hash is over resolved knobs, not over how many files they came from -- so a frame
    rendered off the overlay and one rendered off a pasted single file share a cache dir."""
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
    """[sequence] is the one non-knob table a config file may carry. It must not trip the
    unknown-knob check, and it does not merge key by key -- a frame list is one statement."""
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
    assert beached["model.phase_lock"] == 0.5 and beached["bounce.phase"] == 0.5
    assert beached["bounce.height"] == 0.3
    assert beached["model.reparent_head"] and beached["model.ground_contact"]
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
    """THE SEAM CHECK. At bounce phase 0.5 the heave's flight wraps the loop, so a beat that
    hands into or out of it has to meet it mid-air. The largest lift step anywhere in the
    cycle -- wrap included -- must be one the heave itself already makes inside its own loop:
    anything bigger is him jumping between two frames that were meant to be continuous."""
    lifts = [ac.bounce_lift(beached.configs[k]) for k in beached.order]
    heave = [ac.bounce_lift(dict(beached.configs[0], **{"model.frame": f}))
             for f in range(1, 21)]
    in_loop = max(abs(heave[i] - heave[i - 1]) for i in range(20))
    steps = [abs(lifts[i] - lifts[i - 1]) for i in range(len(lifts))]
    worst = max(range(len(steps)), key=steps.__getitem__)
    assert steps[worst] <= in_loop + 1e-9, (worst, beached.played[worst - 1],
                                            beached.played[worst], steps[worst], in_loop)


def test_the_cycle_ends_where_it_starts(beached):
    """The last played frame hands to the first: same clip, next frame, same gain -- so the
    loop Factorio plays forever has no seam of its own."""
    first, last = beached.configs[beached.order[0]], beached.configs[beached.order[-1]]
    assert first["model.action"] == last["model.action"] == "SWIM_FAST"
    assert first["model.pose_gain"] == last["model.pose_gain"]
    clip = pose.clip_of("SWIM_FAST")
    assert (last["model.frame"] % clip.span) + 1 == first["model.frame"]


# ------------------------------------------------------------- pack: gather + lint


def fake_render(seq):
    """Synthetic frames in each unique config's OWN cache dir, at exactly the path art.py
    would have written them, for all three passes at preview samples."""
    for k, c in enumerate(seq.configs):
        for which, _, _ in art.SEQUENCE_PASSES:
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
    """The PNG chunk is the provenance. For a sequence it used to be frame 0's config -- one
    of N, and a different id from the manifest and the Lua. Now all three say the digest, and
    the chunk holds every frame's hash, the order and the samples."""
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
