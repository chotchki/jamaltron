"""The C.10 harness's pure logic: config resolution, hashing, and sheet layout.

None of this launches Blender or opens the model. That split is deliberate -- the parts
most likely to be quietly wrong (a knob that resolves to the wrong value, a cache key
that does not change when it should, a crop that is half a pixel off) are exactly the
parts that a render never tells you about. A wrong sprite just looks a bit off.

Fixtures come from somewhere real wherever one exists: the stock spidertron's declared
frame size and shift, the leg mount positions out of entities.lua, Factorio's own
projection constant.
"""

import hashlib
import json
import pathlib
import re

import pytest

from render import artconfig as ac
from render import factorio_camera as fc
from render import sheets

TOML = pathlib.Path(ac.DEFAULT_CONFIG_PATH)


# --------------------------------------------------------------------- config resolve


def test_defaults_resolve_without_a_file():
    cfg = ac.resolve(env={})
    assert cfg["model.scale"] == 0.75
    assert cfg["rotations.count"] == 64
    assert set(cfg) == set(ac.SCHEMA)


def test_shipped_toml_loads_and_covers_every_knob():
    """The config file is the interface. A knob that exists in the schema but not in the
    file is a knob nobody will ever find."""
    cfg = ac.load(TOML, env={})
    assert set(cfg) == set(ac.SCHEMA)
    import tomllib
    raw = ac.flatten(tomllib.loads(TOML.read_text()))
    missing = sorted(set(ac.SCHEMA) - set(raw))
    assert not missing, f"jamaltron.toml never mentions: {missing}"
    extra = sorted(set(raw) - set(ac.SCHEMA))
    assert not extra, f"jamaltron.toml sets knobs the schema does not have: {extra}"


def _toml_default(value):
    """Render a schema default the way jamaltron.toml's comments spell it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"%s"' % value
    if isinstance(value, list):
        return "[" + ", ".join(_toml_default(v) for v in value) + "]"
    return repr(value)


def test_every_knob_comment_states_its_real_default():
    """`# default 0.75` above a line that says 0.8 is fine -- the default IS 0.75 and the
    current value is 0.8, which is the whole reason both are written down. `# default 0.7`
    is a lie, and a lie in a comment is worse than no comment, because it is the thing you
    reach for when you want to put a knob back."""
    text = TOML.read_text().splitlines()
    section = None
    seen = set()
    for i, line in enumerate(text):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1]
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=", s)
        if not m or section is None:
            continue
        key = f"{section}.{m.group(1)}"
        if key not in ac.SCHEMA:
            continue
        seen.add(key)
        block = []
        for prev in reversed(text[:i]):
            if not prev.strip():
                break
            block.append(prev.strip())
        want = "default " + _toml_default(ac.SCHEMA[key][1])
        assert any(want in c for c in block), (
            f"{key}: comment block does not say {want!r}\n  " + "\n  ".join(block))
    assert seen == set(ac.SCHEMA)


def test_unknown_knob_is_fatal_and_suggests_the_real_one():
    with pytest.raises(ac.ConfigError) as e:
        ac.resolve({"model": {"scal": 0.8}}, env={})
    assert "model.scal" in str(e.value)
    with pytest.raises(ac.ConfigError) as e:
        ac.resolve({"render": {"samples": 1}, "modle": {"scale": 1}}, env={})
    assert "modle.scale" in str(e.value)


def test_typo_that_lands_on_a_real_leaf_name_gets_a_hint():
    with pytest.raises(ac.ConfigError) as e:
        ac.resolve({"render": {"scale": 0.8}}, env={})
    assert "did you mean model.scale?" in str(e.value)


@pytest.mark.parametrize("typo,want", [
    ("model.scal", "model.scale"),              # the 9am typo: leaf off by one letter
    ("modle.scale", "model.scale"),             # section off by one letter
    ("render.supersampel", "render.supersample"),
    ("camera.canvas_tile", "camera.canvas_tiles"),
    ("output.directory", "output.dir"),
])
def test_misspelled_knob_is_suggested_by_edit_distance(typo, want):
    """An exact-leaf-match hint only fires on the typo you would have spotted anyway.

    `model.scal` is a fat finger on the knob you actually reach for most, and the original
    hint said nothing about it. Both entry points have to answer, because `--set` is the
    one you type while iterating.
    """
    assert ac.suggest(typo) == f"; did you mean {want}?"
    section, leaf = typo.split(".")
    with pytest.raises(ac.ConfigError) as e:
        ac.resolve({section: {leaf: 1}}, env={})
    assert want in str(e.value)
    with pytest.raises(ac.ConfigError) as e:
        ac.parse_set([f"{typo}=1"])
    assert want in str(e.value)


@pytest.mark.parametrize("nonsense", ["model.zzz", "zzz.yyy", "render.wobble"])
def test_a_knob_nothing_is_close_to_gets_no_hint(nonsense):
    """A wrong suggestion costs more than none. At cutoff 0.6 the shared `model.` prefix
    alone was enough to make `model.zzz` come back as "did you mean model.scale?"."""
    assert ac.suggest(nonsense) == ""
    with pytest.raises(ac.ConfigError) as e:
        ac.parse_set([f"{nonsense}=1"])
    assert "did you mean" not in str(e.value)


@pytest.mark.parametrize("bad", [
    {"model": {"scale": "big"}},          # string where a number goes
    {"model": {"mute_nla": 1}},           # int where a bool goes
    {"render": {"samples": 12.5}},        # float where an int goes
    {"model": {"pivot": [1.0, 2.0]}},     # wrong-length vector
    {"model": {"offset": 1.5}},           # scalar where a vector goes
])
def test_wrong_types_are_fatal(bad):
    with pytest.raises(ac.ConfigError):
        ac.resolve(bad, env={})


def test_int_is_accepted_where_a_float_is_declared():
    # TOML writes `energy = 16` readily enough; coercing keeps the hash stable whichever
    # way it was spelled.
    cfg = ac.resolve({"sun": {"energy": 16}}, env={})
    assert cfg["sun.energy"] == 16.0
    assert isinstance(cfg["sun.energy"], float)
    assert ac.config_hash(cfg) == ac.config_hash(ac.resolve({"sun": {"energy": 16.0}}, env={}))


def test_bool_is_not_an_int():
    # Python says True == 1. A config parser that agrees will happily take
    # `samples = true` and render one sample.
    with pytest.raises(ac.ConfigError):
        ac.resolve({"render": {"samples": True}}, env={})


def test_overrides_beat_the_file_and_env_beats_both():
    cfg = ac.resolve({"model": {"scale": 0.5}}, {"model.scale": 0.9},
                     env={ac.BLEND_ENV: "/tmp/x.blend"})
    assert cfg["model.scale"] == 0.9
    assert cfg["model.blend"] == "/tmp/x.blend"


def test_parse_set_uses_toml_syntax():
    got = ac.parse_set(["model.scale=0.8", 'render.engine="CYCLES"',
                        "model.offset=[0, 0, 1.25]", "compare.grid=false"])
    assert got == {"model.scale": 0.8, "render.engine": "CYCLES",
                   "model.offset": [0.0, 0.0, 1.25], "compare.grid": False}


@pytest.mark.parametrize("bad", ["model.scale", "nope.key=1", "model.scale=not_toml"])
def test_parse_set_rejects_junk(bad):
    with pytest.raises(ac.ConfigError):
        ac.parse_set([bad])


def test_resolve_does_not_share_vector_state_between_calls():
    a = ac.resolve(env={})
    a["model.offset"][2] = 99.0
    assert ac.resolve(env={})["model.offset"][2] == 0.85


# ----------------------------------------------------------------------------- hashing


def test_config_hash_is_stable_and_order_independent():
    a = ac.resolve({"model": {"scale": 0.8}, "sun": {"energy": 9.0}}, env={})
    b = ac.resolve({"sun": {"energy": 9.0}, "model": {"scale": 0.8}}, env={})
    assert ac.config_hash(a) == ac.config_hash(b)
    assert ac.config_hash(a) == hashlib.sha256(ac.canonical(a).encode()).hexdigest()[:12]


def test_config_hash_moves_when_any_knob_moves():
    base = ac.resolve(env={})
    seen = {ac.config_hash(base)}
    for key, spec in ac.SCHEMA.items():
        cfg = dict(base)
        cfg[key] = _nudge(spec[0], base[key])
        seen.add(ac.config_hash(cfg))
    assert len(seen) == len(ac.SCHEMA) + 1, "two different configs hash the same"


def _nudge(kind, value):
    if isinstance(kind, tuple):
        return [v + 1 for v in value]
    if kind is bool:
        return not value
    if kind is str:
        return value + "_x"
    return value + 1


def test_pass_hash_ignores_knobs_that_cannot_change_that_pass():
    """The cache key is the whole point of the harness feeling fast. Re-colouring the
    compare background must not throw away 64 Cycles shadow frames."""
    base = ac.resolve(env={})
    recoloured = dict(base, **{"compare.background": [0, 0, 0]})
    assert ac.pass_hash(base, "body") == ac.pass_hash(recoloured, "body")
    assert ac.pass_hash(base, "shadow") == ac.pass_hash(recoloured, "shadow")
    assert ac.pass_hash(base, "compare") != ac.pass_hash(recoloured, "compare")


def test_pass_hash_moves_when_the_geometry_moves():
    base = ac.resolve(env={})
    bigger = dict(base, **{"model.scale": 0.9})
    for p in ("body", "shadow"):
        assert ac.pass_hash(base, p) != ac.pass_hash(bigger, p)


def test_body_only_knobs_leave_the_shadow_cache_alone():
    # The shadow pass is the expensive one (Cycles, 704 px). Fiddling with the body's
    # normal map must not cost 85 seconds.
    base = ac.resolve(env={})
    other = dict(base, **{"render.normal_strength": 0.9, "render.use_subsurface": True,
                          "camera.canvas_tiles": 7.0})
    assert ac.pass_hash(base, "shadow") == ac.pass_hash(other, "shadow")
    assert ac.pass_hash(base, "body") != ac.pass_hash(other, "body")


def test_a_forced_resolution_makes_the_shadow_hash_follow_the_body_canvas():
    """The hole that served stale pixels. With render.resolution_px set, camera.canvas_tiles
    -- declared body-only -- sets the SHADOW pass's resolution too: 6.0 -> 4.5 takes it from
    704 px / 64.00 px-per-tile to 939 px / 85.36. The pass hash has to move with it, or the
    next --compare composites shadow frames rendered at a different pixel scale."""
    base = ac.resolve({"render": {"resolution_px": 384}}, env={})
    narrow = dict(base, **{"camera.canvas_tiles": 4.5})
    assert ac.derived(base)["shadow_resolution_px"] == 704
    assert ac.derived(narrow)["shadow_resolution_px"] == 939
    assert ac.pass_hash(base, "shadow") != ac.pass_hash(narrow, "shadow")
    assert ac.pass_hash(base, "body") != ac.pass_hash(narrow, "body")


def test_a_body_canvas_change_still_spares_the_shadow_cache_by_default():
    """The other half: without a forced resolution the shadow pass genuinely does not care
    about the body canvas, and paying 85 s of Cycles to widen the body canvas would make
    the harness feel exactly as slow as it was built to not be."""
    base = ac.resolve(env={})
    wider = dict(base, **{"camera.canvas_tiles": 7.0})
    assert ac.derived(base)["shadow_resolution_px"] == ac.derived(wider)["shadow_resolution_px"]
    assert ac.pass_hash(base, "shadow") == ac.pass_hash(wider, "shadow")
    assert ac.pass_hash(base, "body") != ac.pass_hash(wider, "body")


def test_supersample_moves_both_cache_keys():
    base = ac.resolve(env={})
    ss2 = dict(base, **{"render.supersample": 2})
    for p in ("body", "shadow"):
        assert ac.pass_hash(base, p) != ac.pass_hash(ss2, p)


def test_pass_derived_names_real_derived_keys_for_every_pass():
    d = ac.derived(ac.resolve(env={}))
    assert set(ac.PASS_DERIVED) == set(ac.PASSES)
    for names in ac.PASS_DERIVED.values():
        assert names, "a pass with no derived dependency should say so explicitly"
        for k in names:
            assert k in d, k


def test_every_pass_has_knobs_and_every_knob_is_reachable():
    for p in ac.PASSES:
        assert ac.pass_keys(p), f"pass {p} depends on nothing"
    with pytest.raises(ac.ConfigError):
        ac.pass_keys("bogus")


def test_stamp_round_trips_through_json():
    blob = ac.stamp(ac.resolve(env={}), {"pass": "body"})
    again = json.loads(json.dumps(blob))
    assert again["config_hash"] == blob["config_hash"]
    assert ac.config_hash(ac.resolve(again["config"], env={})) == blob["config_hash"]


# --------------------------------------------------------------------------- rotations


def test_preview_frames_are_a_subset_of_the_full_wheel():
    """If they are not, a preview is a different picture from the sheet it previews and
    the cache can never share a frame between --preview and --full."""
    cfg = ac.resolve(env={})
    full = ac.frame_indices(cfg)
    assert full == list(range(64))
    for n in (1, 2, 4, 8, 16, 32, 64):
        assert set(ac.frame_indices(cfg, n)) <= set(full)
    assert ac.frame_indices(cfg, 8) == [0, 8, 16, 24, 32, 40, 48, 56]


def test_frame_indices_are_evenly_spaced_for_a_non_divisor():
    cfg = ac.resolve(env={})
    got = ac.frame_indices(cfg, 6)
    assert len(got) == 6 and got[0] == 0 and max(got) < 64
    gaps = [b - a for a, b in zip(got, got[1:])]
    assert max(gaps) - min(gaps) <= 1


@pytest.mark.parametrize("n", [0, -1, 65])
def test_frame_indices_rejects_impossible_counts(n):
    with pytest.raises(ac.ConfigError):
        ac.frame_indices(ac.resolve(env={}), n)


def test_compass_labels_track_the_clockwise_wheel():
    assert ac.compass(0) == "N"
    assert ac.compass(16) == "E"
    assert ac.compass(32) == "S"
    assert ac.compass(48) == "W"


# ----------------------------------------------------------------------------- derived


def test_derived_resolution_keeps_one_tile_at_64_px():
    cfg = ac.resolve(env={})
    d = ac.derived(cfg)
    assert d["body_resolution_px"] == 384                 # 6 tiles at 64 px
    assert d["body_px_per_tile"] == pytest.approx(64.0)
    assert d["shadow_px_per_tile"] == pytest.approx(64.0)


def test_supersample_renders_big_and_stamps_what_lands_on_disk():
    """supersample renders 2x and art.py downsamples back, so the STAMP must say 384.

    It said 768 at 128 px-per-tile, which is neither the file's size nor its scale, and
    the compare sheet then resampled the frame to half size to "correct" for a px-per-tile
    the frame never had.
    """
    d = ac.derived(ac.resolve({"render": {"supersample": 2}}, env={}))
    assert d["body_render_px"] == 768                    # what Blender is asked for
    assert d["body_resolution_px"] == 384                # what lands on disk
    assert d["body_px_per_tile"] == pytest.approx(64.0)  # and its real scale
    assert d["supersample"] == 2


def test_render_px_is_always_the_stamped_px_times_supersample():
    for ss in (1, 2, 3):
        for forced in (0, 256, 384):
            d = ac.derived(ac.resolve(
                {"render": {"supersample": ss, "resolution_px": forced}}, env={}))
            for pass_name in ("body", "shadow"):
                assert (d[f"{pass_name}_render_px"]
                        == d[f"{pass_name}_resolution_px"] * ss), (ss, forced, pass_name)


def test_forced_resolution_puts_both_passes_on_one_px_per_tile():
    """The compare sheet overlays body and shadow, so a forced resolution has to carry the
    shadow canvas with it -- 384 px over 6 tiles is 64 px/tile, and 11 tiles of shadow
    canvas at 64 px/tile is 704 px."""
    d = ac.derived(ac.resolve({"render": {"resolution_px": 384}}, env={}))
    assert (d["body_resolution_px"], d["shadow_resolution_px"]) == (384, 704)
    assert d["body_px_per_tile"] == pytest.approx(d["shadow_px_per_tile"])
    # ... and supersample still means the same thing on top of it.
    d2 = ac.derived(ac.resolve(
        {"render": {"resolution_px": 384, "supersample": 2}}, env={}))
    assert (d2["body_render_px"], d2["body_resolution_px"]) == (768, 384)
    assert (d2["shadow_render_px"], d2["shadow_resolution_px"]) == (1408, 704)


def test_the_stamped_size_is_the_size_of_the_png_that_lands_on_disk(tmp_path):
    """The one claim the whole harness rests on, walked end to end with Blender stubbed.

    Blender's contribution is exactly "write a *_render_px square PNG"; everything after
    that is ours. Stamp 384 px next to a 192 px file once and every sheet in render-out/
    becomes unciteable, which is the opposite of what a provenance stamp is for.
    """
    Image = pytest.importorskip("PIL.Image")
    from render import art

    cfg = ac.resolve({"render": {"resolution_px": 384, "supersample": 2}}, env={})
    d = ac.derived(cfg)
    frames = [0, 8]
    for i in frames:                                     # what render_jamal.py writes
        Image.new("RGBA", (d["body_render_px"], d["body_render_px"]),
                  (0, 0, 0, 0)).save(tmp_path / f"frame_{i:03d}.png")
    art.downsample(tmp_path, frames, d["body_resolution_px"])

    stamp = ac.stamp(cfg)
    for i in frames:
        got = Image.open(tmp_path / f"frame_{i:03d}.png").size
        assert got == (stamp["derived"]["body_resolution_px"],) * 2, got
        assert got[0] / cfg["camera.canvas_tiles"] == pytest.approx(
            stamp["derived"]["body_px_per_tile"])


def test_derived_shark_size_uses_the_measured_rest_box():
    d = ac.derived(ac.resolve({"model": {"scale": 1.0}}, env={}))
    assert d["shark_length_tiles"] == pytest.approx(5.0272)
    assert d["shark_width_tiles"] == pytest.approx(1.9682)


def test_defaults_are_the_games_own_camera_and_sun():
    d = ac.derived(ac.resolve(env={}))
    assert d["camera_is_factorio_default"] and d["sun_is_factorio_default"]
    assert d["light_run_east"] == pytest.approx(1.0)      # 45 deg sun, due west
    assert d["light_run_south"] == pytest.approx(0.0, abs=1e-12)
    assert not ac.warnings(ac.resolve(env={}))


@pytest.mark.parametrize("knob,value,needle", [
    ({"camera": {"pitch": 50.0}}, None, "OFF the game's own projection"),
    ({"sun": {"elevation": 30.0}}, None, "off the measured stock shadow direction"),
    ({"render": {"shadow_engine": "BLENDER_EEVEE_NEXT"}}, None, "is_shadow_catcher"),
    ({"rotations": {"preview": 7}}, None, "does not divide"),
])
def test_dangerous_but_legal_knobs_warn(knob, value, needle):
    got = " ".join(ac.warnings(ac.resolve(knob, env={})))
    assert needle in got


# ------------------------------------------------------------------------ sheet layout


def test_origin_in_frame_matches_the_stock_torso():
    """Cross-checked against the measured art: factorio_camera's --verify reads the stock
    body's alpha at -1.6562 .. +0.4688 tiles, so the entity sits 1.6562*64 = 106 px below
    the frame's top edge. Landing on 106.5 is the (n-1)/2 pixel-index convention, and the
    half pixel is the convention, not an error."""
    ox, oy = sheets.origin_in_frame(132, 138, (0.0, -19 / 32), 64.0)
    assert ox == pytest.approx(65.5)
    assert oy == pytest.approx(106.5)


def test_origin_in_frame_matches_the_stock_shadow():
    ox, oy = sheets.origin_in_frame(192, 94, (26 / 32, 0.5 / 32), 64.0)
    assert ox == pytest.approx(95.5 - 52.0)
    assert oy == pytest.approx(46.5 - 1.0)


def test_frame_box_walks_left_to_right_then_down():
    assert sheets.frame_box(0, 132, 138, 8) == (0, 0, 132, 138)
    assert sheets.frame_box(7, 132, 138, 8) == (924, 0, 1056, 138)
    assert sheets.frame_box(8, 132, 138, 8) == (0, 138, 132, 276)
    assert sheets.frame_box(63, 132, 138, 8) == (924, 966, 1056, 1104)


def test_cell_anchor_biases_down_so_a_lifted_body_fits():
    assert sheets.cell_anchor(100, 0.5) == (49.5, 49.5)
    assert sheets.cell_anchor(100, 0.78)[1] == pytest.approx(77.22)
    # x stays centred whatever the vertical bias is
    assert sheets.cell_anchor(100, 0.78)[0] == sheets.cell_anchor(100, 0.1)[0]


def test_centred_crop_is_the_right_size_and_reports_its_residual():
    box, resid = sheets.centred_crop((106.5, 106.5), 200, 0.5)
    assert box[2] - box[0] == 200 and box[3] - box[1] == 200
    assert max(abs(r) for r in resid) <= 0.5
    box2, _ = sheets.centred_crop((106.5, 106.5), 200, 0.78)
    assert box2[1] < box[1], ("an anchor lower in the CELL has to take more of the source "
                              "from ABOVE the origin, which is the whole point of it")


def test_centred_crop_may_run_off_the_source_edge():
    # Pillow pads a crop outside the image with transparency, which is what keeps a
    # near-the-edge entity from silently shifting inside its cell.
    box, _ = sheets.centred_crop((10.0, 10.0), 200, 0.5)
    assert box[0] < 0 and box[1] < 0


def test_mount_markers_agree_with_the_prototype():
    m = sheets.mount_markers(64.0)
    assert len(m) == 8
    mount, ground = m[0]                                  # by_pixel(15, -22)
    assert mount == pytest.approx((30.0, -44.0))
    # ground_position {2.25, -2.5} is a WORLD point: east untouched, north-south
    # foreshortened by the 45 degree camera.
    assert ground[0] == pytest.approx(2.25 * 64)
    assert ground[1] == pytest.approx(-2.5 * 64 * fc.K)


def test_mount_extents_are_the_footprint_c4_has_to_cover():
    hw, north, south = sheets.mount_extents(64.0)
    assert hw / 64.0 == pytest.approx(25 / 32)            # +-0.78 tiles transverse
    assert north / 64.0 == pytest.approx(-22 / 32)
    assert south / 64.0 == pytest.approx(17 / 32)


def test_grid_layout_arithmetic():
    lay = sheets.GridLayout(cols=8, rows=3, cell=294, gutter=6, left=78, top=26,
                            bottom=34, right=8)
    assert lay.width == 78 + 8 * 294 + 7 * 6 + 8
    assert lay.height == 26 + 3 * 294 + 2 * 6 + 34
    assert lay.cell_origin(0, 0) == (78, 26)
    assert lay.cell_origin(1, 0) == (78 + 300, 26)
    assert lay.cell_origin(0, 2) == (78, 26 + 600)
    assert lay.footer_origin()[1] < lay.height


@pytest.mark.parametrize("col,row", [(-1, 0), (8, 0), (0, 3)])
def test_grid_layout_rejects_cells_outside_itself(col, row):
    with pytest.raises(IndexError):
        sheets.GridLayout(cols=8, rows=3, cell=100).cell_origin(col, row)


def test_contact_grid_mirrors_the_stock_sheet_shape():
    assert sheets.contact_grid(64) == (8, 8)              # exactly the stock torso sheet
    assert sheets.contact_grid(8) == (8, 1)
    assert sheets.contact_grid(9) == (8, 2)
    assert sheets.contact_grid(1) == (1, 1)
    with pytest.raises(ValueError):
        sheets.contact_grid(0)


def test_stock_sprite_specs_match_the_prototype():
    # spidertron-animations.lua, spidertron_torso_graphics_set(1).
    assert sheets.STOCK_BODY["width"] == 132 and sheets.STOCK_BODY["height"] == 138
    assert sheets.STOCK_BODY["line_length"] == 8 and sheets.STOCK_BODY["direction_count"] == 64
    assert sheets.STOCK_SHADOW["width"] == 192 and sheets.STOCK_SHADOW["height"] == 94
    w, h, ll = (sheets.STOCK_BODY[k] for k in ("width", "height", "line_length"))
    assert (w * ll, h * (64 // ll)) == (1056, 1104)       # the file on disk


def test_stock_base_is_the_non_rotating_plate_the_legs_attach_to():
    """spidertron-animations.lua:313-320, base_animation layer 1. direction_count = 1 is
    the load-bearing field: one frame for all 64 rotations, drawn UNDER the torso, and it
    is what the eight leg mounts land on."""
    b = sheets.STOCK_BASE
    assert b["path"].endswith("spidertron-body-bottom.png")
    assert (b["width"], b["height"]) == (126, 106)
    assert b["direction_count"] == 1 and b["line_length"] == 1
    assert b["scale"] == 0.5 and b["shift"] == (0.0, 0.0)
    # 126 x 106 px at 64 px/tile: the plate is 1.97 tiles wide, so its half-width 0.98
    # tiles clears the outer mounts at 0.78 with room. The 2.06-tile TORSO does not.
    assert b["width"] / 64.0 / 2 > 25 / 32


def test_footer_height_fits_every_line_it_is_given():
    """GridLayout's default 34 px bottom fits exactly two footer lines, and the compare
    sheet draws four. The leg-mount footprint line -- the one number on the sheet that
    answers "how big is he" -- used to render two pixels tall, off the bottom edge."""
    for n in range(1, 6):
        h = sheets.footer_height(n)
        lay = sheets.GridLayout(cols=1, rows=1, cell=100, bottom=h)
        top = lay.footer_origin()[1]
        # last baseline plus the 12 px glyph box still inside the canvas
        assert top + (n - 1) * sheets.FOOTER_LEADING + 12 <= lay.height, (n, h)
    assert sheets.footer_height(0) >= 0
    assert sheets.footer_height(3) > sheets.footer_height(2)
    with pytest.raises(ValueError):
        sheets.footer_height(-1)


# ------------------------------------------------------------------ the sheet's own check


def _skip_without_factorio(spec):
    if not pathlib.Path(spec["path"]).exists():
        pytest.skip("Factorio not installed here: " + spec["path"])
    pytest.importorskip("PIL.Image")


def test_the_mount_markers_land_on_the_stock_base_plate():
    """The self-check the docstring promises, run for real.

    This is the sheet's claim about ITSELF: mount_position read as a SCREEN offset (not a
    world position at body height) puts the markers on the layer the legs attach to. 8 of 8
    on opaque plate, each 0.707 px from a fully opaque pixel -- which is the half-pixel
    diagonal forced by the (n-1)/2 origin convention and is the floor, not a miss.
    """
    _skip_without_factorio(sheets.STOCK_BASE)
    res = sheets.mount_selfcheck()
    assert res["ran"] and res["ok"], sheets.selfcheck_line(res)
    assert res["on_layer"] == res["total"] == 8
    assert res["worst_gap_px"] == pytest.approx(0.707, abs=0.01)
    assert all(s["alpha"] == 255 for s in res["samples"]), res["samples"]
    assert "PASS" in sheets.selfcheck_line(res)


def _write_frame(d, index, size, box):
    """One synthetic render frame: transparent, with `box` opaque."""
    Image = pytest.importorskip("PIL.Image")
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste((200, 200, 200, 255), box)
    img.save(d / ("frame_%03d.png" % index))


def test_a_render_that_runs_out_of_canvas_is_reported(tmp_path, capsys):
    """The shipped 6-tile body canvas already cuts the nose at model.scale 1.1, which is
    the first thing anyone reaches for. A clipped frame reads as a shark with a flat
    dorsal fin, not as an error, so the harness has to say so itself.
    """
    from render import art
    cfg = ac.resolve(env={})
    inside, edge = tmp_path / "in", tmp_path / "edge"
    inside.mkdir(); edge.mkdir()
    _write_frame(inside, 0, 64, (10, 10, 50, 50))     # clear of every edge
    _write_frame(edge, 0, 64, (10, 0, 50, 50))        # touching the top

    assert art.warn_if_clipped(cfg, inside, [0], "body") == []
    assert "WARN" not in capsys.readouterr().out

    assert art.warn_if_clipped(cfg, edge, [0], "body") == [0]
    out = capsys.readouterr().out
    assert "TOUCH THE CANVAS EDGE" in out
    assert "camera.canvas_tiles" in out


def test_the_clipping_warning_names_the_pass_it_can_actually_fix(tmp_path):
    """The shadow pass rides its own canvas knob. Telling someone to raise the body's
    would have them turning a knob that changes nothing about the frame they are looking at.
    """
    from render import art
    cfg = ac.resolve(env={})
    d = tmp_path / "s"
    d.mkdir()
    _write_frame(d, 0, 64, (0, 10, 50, 50))
    assert art.CANVAS_KNOB["shadow"] == "camera.shadow_canvas_tiles"
    assert art.warn_if_clipped(cfg, d, [0], "shadow") == [0]


def test_shadow_sampling_noise_does_not_read_as_a_clipped_frame(tmp_path, capsys):
    """MEASURED on a real 704 px Cycles shadow frame: the catcher plane carries alpha 1..7
    over the WHOLE canvas, so getbbox() with no threshold is the full frame and every
    shadow render reports as clipped. A warning that fires on all eight frames of a
    correct render is one you turn off. The floor is the same 8 sheets.py samples at.
    """
    from render import art
    Image = pytest.importorskip("PIL.Image")
    cfg = ac.resolve(env={})
    d = tmp_path / "noise"
    d.mkdir()
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 3))          # sub-threshold everywhere
    img.paste((0, 0, 0, 255), (20, 20, 40, 40))              # the actual shadow, inset
    img.save(d / "frame_000.png")
    assert img.getchannel("A").getbbox() == (0, 0, 64, 64)   # the naive read says clipped
    assert art.warn_if_clipped(cfg, d, [0], "shadow") == []
    assert "WARN" not in capsys.readouterr().out
    # and it is a threshold, not a blanket exemption: push the noise over the floor
    assert art.warn_if_clipped(cfg, d, [0], "shadow", floor=1) == [0]


def test_a_missing_or_empty_frame_is_not_a_clipping_report(tmp_path, capsys):
    """getbbox() returns None for a fully transparent frame. Reading that as "clipped"
    would fire the warning on the one case where nothing rendered at all."""
    from render import art
    Image = pytest.importorskip("PIL.Image")
    cfg = ac.resolve(env={})
    d = tmp_path / "e"
    d.mkdir()
    Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(d / "frame_000.png")
    assert art.warn_if_clipped(cfg, d, [0, 7], "body") == []   # frame 7 does not exist
    assert "WARN" not in capsys.readouterr().out


def test_mount_coverage_counts_only_opaque_pixels_of_our_own_render():
    """The number the compare sheet's headline question turns on, exercised without Blender.

    Synthetic frames rather than a render, because the claim being tested is "an opaque
    pixel under a marker counts and a transparent one does not", and a real shark makes
    that a fact about the shark instead of about the counter.
    """
    Image = pytest.importorskip("PIL.Image")
    cell, ppt, oy = 294, 64.0, 0.78
    blank = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
    assert sheets.mount_coverage(blank, ppt, oy) == 0

    solid = Image.new("RGBA", (cell, cell), (255, 255, 255, 255))
    assert sheets.mount_coverage(solid, ppt, oy) == len(sheets.LEG_MOUNTS)

    # One mount, one opaque pixel under it: the count is a point sample, not a blob test.
    ax, ay = sheets.cell_anchor(cell, oy)
    (mx, my), _ = sheets.mount_markers(ppt)[0]
    one = blank.copy()
    one.putpixel((int(round(ax + mx)), int(round(ay + my))), (255, 255, 255, 255))
    assert sheets.mount_coverage(one, ppt, oy) == 1

    # Below the alpha threshold is not coverage. A leg on a 4/255 fringe is a leg in air.
    faint = blank.copy()
    faint.putpixel((int(round(ax + mx)), int(round(ay + my))), (255, 255, 255, 4))
    assert sheets.mount_coverage(faint, ppt, oy) == 0


def test_coverage_line_names_the_worst_rotation():
    """An average hides the frame you need to see: a leg that floats at one heading floats
    in the game. The worst rotation is the one that has to be on the sheet."""
    line = sheets.coverage_line([("00 N", 2), ("08 NE", 3), ("32 S", 0)])
    assert "5/24" in line
    assert "worst 0/8 at 32 S" in line
    assert "best 3/8 at 08 NE" in line
    assert sheets.coverage_line([]) == "shark mount coverage: no frames"


def test_the_rotating_torso_is_the_wrong_layer_to_check_against():
    """Why the check aims at base_animation. Point it at the rotating torso and it fails --
    not because the reading is wrong but because Wube's torso is narrower than the leg
    spread. 230 of 512 mount samples over the 64 frames sit on transparent pixels. Aiming
    the self-check there would make it cry wolf forever, so it would get ignored.
    """
    _skip_without_factorio(sheets.STOCK_BODY)
    res = sheets.mount_selfcheck(sheets.STOCK_BODY)
    assert res["ran"] and not res["ok"]
    assert res["on_layer"] < res["total"]


def test_a_one_frame_layer_ignores_the_frame_index():
    """base_animation has one frame; asking it for frame 24 would crop 24 rows below a
    106 px file and hand back transparency, which reads as "the plate vanished"."""
    _skip_without_factorio(sheets.STOCK_BASE)
    Image = pytest.importorskip("PIL.Image")
    a = sheets.load_sheet_frame(sheets.STOCK_BASE, 0, 200, 64.0, 0.78)
    for i in (1, 24, 63):
        b = sheets.load_sheet_frame(sheets.STOCK_BASE, i, 200, 64.0, 0.78)
        assert Image.core is not None
        assert a.tobytes() == b.tobytes(), i
    assert a.getchannel("A").getextrema()[1] == 255, "the plate should have opaque pixels"


def test_no_module_under_render_shadows_the_stdlib():
    """render/inspect.py cost two checked-in scripts their exit code.

    Python and Blender both put the running script's own directory on sys.path[0], so a
    file named after a stdlib module hijacks that import for every sibling. `dataclasses`
    imports `inspect`, so `from dataclasses import dataclass` in spritesheet.py became
    `import bpy` and `uv run python render/spritesheet.py` exited 1 -- as did
    blender_check.py. Four modules grew a bespoke sys.path guard; the file got renamed to
    model_inspect.py instead. This test is what makes the rename stick.
    """
    import sys
    render_dir = pathlib.Path(ac.__file__).resolve().parent
    clashes = sorted(f.stem for f in render_dir.glob("*.py")
                     if f.stem in sys.stdlib_module_names)
    assert not clashes, (
        "these files under render/ shadow stdlib modules for every sibling script: "
        + ", ".join(clashes))


def test_artconfig_stays_importable_inside_blender():
    """Blender has no venv and no Pillow. artconfig and sheets are imported by the
    Blender-side script, so a third-party import here breaks the render, not the tests."""
    import ast
    src = pathlib.Path(ac.__file__).read_text()
    allowed = {"__future__", "difflib", "hashlib", "json", "math", "os", "pathlib",
               "sys", "tomllib", "render"}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] in allowed, a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            assert node.module.split(".")[0] in allowed, node.module
