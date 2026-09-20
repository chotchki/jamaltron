"""Gate tests for lint_sprites.py. Every failure mode gets a real PNG built with
Pillow in a tmpdir, because a linter tested against mocks only proves the mocks work.

Two tests run against shipped Factorio 2.1.17 assets and skip when the game is not
installed - they are the ones that prove this gate does not slander Wube's own art.
"""

import ast
import json
import pathlib
import sys

import pytest
from PIL import Image

import lint_sprites
from lint_sprites import ERROR, WARN, ModPaths, SpriteSpec, check_spec, lint, main, png_size

FACTORIO_DATA = pathlib.Path("/Applications/factorio.app/Contents/data")
TOOLS = pathlib.Path(__file__).resolve().parents[1]

needs_factorio = pytest.mark.skipif(not FACTORIO_DATA.is_dir(),
                                    reason="Factorio 2.1.17 data not installed here")


# ------------------------------------------------------------------- fixtures

@pytest.fixture
def sheets(tmp_path):
    """Builds PNGs under a `__test__` mod root and lints declarations against them."""

    class Sheets:
        root = tmp_path
        mods = ModPaths()

        def __init__(self):
            self.mods.add("test", tmp_path)

        def png(self, name: str, width: int, height: int) -> str:
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (width, height), (0, 0, 0, 0)).save(path)
            return f"__test__/{name}"

        def check(self, strict: bool = False, **fields) -> list:
            spec = lint_sprites.spec_from_table("unit-test", lint_sprites._jsonify(fields))
            return check_spec(spec, self.mods, strict=strict)

        def codes(self, **kwargs) -> list[str]:
            return [f.code for f in self.check(**kwargs)]

    return Sheets()


def only(findings, severity=ERROR):
    return [f for f in findings if f.severity == severity]


# ---------------------------------------------------------------- passing cases

def test_single_frame_sprite_is_clean(sheets):
    name = sheets.png("plate.png", 126, 106)
    assert sheets.check(filename=name, width=126, height=106,
                        line_length=1, direction_count=1) == []


def test_64_rotation_sheet_is_clean(sheets):
    """The stock spidertron torso's exact shape: 64 frames of 132x138, 8 per row."""
    name = sheets.png("body.png", 1056, 1104)
    assert sheets.check(filename=name, width=132, height=138,
                        line_length=8, direction_count=64) == []


def test_rotated_animation_multiplies_directions_by_frames(sheets):
    # 4 directions x 3 frames = 12 slots, 4 per row = 3 rows of 10px
    name = sheets.png("flop.png", 40, 30)
    assert sheets.check(filename=name, width=10, height=10,
                        line_length=4, direction_count=4, frame_count=3) == []


def test_line_length_zero_means_one_row(sheets):
    """Factorio's documented default, for the one-direction one-variation case where it
    is the same statement as "line_length defaults to frame_count"."""
    name = sheets.png("strip.png", 100, 10)
    assert sheets.check(filename=name, width=10, height=10, frame_count=10) == []


def test_missing_line_length_defaults_to_frame_count_not_to_one_row(sheets):
    """The stock character: level1_idle.png is 2024x928 = 22 frames x 8 directions, NOT
    176 frames in one 16192px row. MEASURED 49/49 rotated sheets in base + core +
    space-age. Reading this as one row invents a sheet-too-big on Wube's own art."""
    name = sheets.png("idle.png", 22 * 92, 8 * 116)
    assert sheets.check(filename=name, width=92, height=116,
                        frame_count=22, direction_count=8) == []


def test_variations_get_a_row_each_too(sheets):
    """metal-particle-big.png is 600x440 = 12 frames x 10 variations. Same rule."""
    name = sheets.png("particle.png", 12 * 50, 10 * 44)
    assert sheets.check(filename=name, width=50, height=44,
                        frame_count=12, variation_count=10) == []


def test_variation_count_counts_as_frames(sheets):
    name = sheets.png("variations.png", 60, 20)
    assert sheets.check(filename=name, width=20, height=20,
                        line_length=3, variation_count=3) == []


def test_repeat_count_does_not_demand_pixels(sheets):
    """core/lualib/util.lua's empty_animation is repeat_count N over a 1x1 png. Counting
    repeat_count as frames would fail every empty animation in the game."""
    name = sheets.png("empty.png", 1, 1)
    assert sheets.check(filename=name, width=1, height=1,
                        repeat_count=60, direction_count=1) == []


# ------------------------------- declared size vs actual image dimensions

def test_declared_bigger_than_the_file_uses_factorios_own_wording(sheets):
    """The requirement's literal example: 64x64 declared over a 32x32 file."""
    name = sheets.png("small.png", 32, 32)
    findings = only(sheets.check(filename=name, width=64, height=64))
    assert [f.code for f in findings] == ["sheet-too-small"]
    assert findings[0].message == (
        "The given sprite rectangle (left_top=0x0, right_bottom=64x64) is outside the "
        "actual sprite size (left_top=0x0, right_bottom=32x32)")


def test_offset_is_part_of_the_rectangle(sheets):
    """x/y push the rectangle right and down - base slices shared leg sheets that way."""
    name = sheets.png("shared.png", 320, 294)
    assert sheets.check(filename=name, width=40, height=98, x=280, y=196) == []
    findings = only(sheets.check(filename=name, width=40, height=98, x=281, y=196))
    assert [f.code for f in findings] == ["sheet-too-small"]


# ------------- frame count vs line_length vs direction_count vs real pixels

def test_line_length_too_wide_is_caught(sheets):
    """A wrong line_length cannot hide: more columns means a wider rectangle."""
    name = sheets.png("body.png", 1056, 1104)
    findings = only(sheets.check(filename=name, width=132, height=138,
                                 line_length=16, direction_count=64))
    assert [f.code for f in findings] == ["sheet-too-small"]
    assert "right_bottom=2112x552" in findings[0].message


def test_line_length_too_narrow_is_caught(sheets):
    """...and fewer columns means a taller one. Both directions fail loudly."""
    name = sheets.png("body.png", 1056, 1104)
    findings = only(sheets.check(filename=name, width=132, height=138,
                                 line_length=4, direction_count=64))
    assert [f.code for f in findings] == ["sheet-too-small"]
    assert "right_bottom=528x2208" in findings[0].message


def test_more_frames_than_the_sheet_holds_spells_out_the_arithmetic(sheets):
    name = sheets.png("half.png", 1056, 552)
    findings = only(sheets.check(filename=name, width=132, height=138,
                                 line_length=8, direction_count=64))
    assert [f.code for f in findings] == ["sheet-too-small"]
    detail = " ".join(findings[0].detail)
    assert "64 frame(s) needed" in detail
    assert "8 row(s) of 138px" in detail
    assert "4 row(s) x 8 column(s) = 32 frame(s)" in detail


def test_last_row_may_be_partly_empty(sheets):
    """65 frames at 8 per row is 9 rows with 7 unused slots - legal, not an error."""
    name = sheets.png("body.png", 1056, 9 * 138)
    assert only(sheets.check(filename=name, width=132, height=138,
                             line_length=8, direction_count=65)) == []


# ------------------------------- no knowable layout: the frame-budget fallback

def test_frame_count_one_with_directions_has_no_knowable_layout(sheets):
    """MEASURED: small-electric-pole.png is 288x220, 4 directions in ONE ROW, while
    car-remnants-mask.png is 196x584, 4 directions in ONE COLUMN. Same declared fields,
    opposite layouts, because the engine's default comes from the prototype field being
    loaded. So both must pass, and neither can get a real geometry check."""
    row = sheets.png("pole.png", 4 * 72, 220)
    column = sheets.png("remnants.png", 196, 4 * 146)
    assert sheets.check(filename=row, width=72, height=220, direction_count=4) == []
    assert sheets.check(filename=column, width=196, height=146, direction_count=4) == []


def test_the_fallback_still_catches_a_file_that_is_simply_too_small(sheets):
    name = sheets.png("pole.png", 2 * 72, 220)  # room for 2 of the 4 directions
    findings = only(sheets.check(filename=name, width=72, height=220, direction_count=4))
    assert [f.code for f in findings] == ["frame-shortfall"]
    assert "hold at most 2 whole 72x220 frame(s)" in findings[0].message


def test_strict_asks_for_the_line_length_that_would_allow_a_real_check(sheets):
    name = sheets.png("pole.png", 4 * 72, 220)
    fields = dict(filename=name, width=72, height=220, direction_count=4)
    assert sheets.check(**fields) == []
    warnings = only(sheets.check(strict=True, **fields), WARN)
    assert [f.code for f in warnings] == ["no-line-length"]


def test_the_fallback_reports_a_missing_file_not_a_shortfall(sheets):
    findings = only(sheets.check(filename="__test__/gone.png", width=72, height=220,
                                 direction_count=4))
    assert [f.code for f in findings] == ["missing-file"]


# ------------------------------------------------------ the 8192px sheet limit

def test_sheet_over_the_limit_is_rejected(sheets):
    name = sheets.png("huge.png", 8300, 64)
    codes = [f.code for f in only(sheets.check(filename=name, width=100, height=64,
                                               line_length=83, direction_count=83))]
    # both halves fire: the file itself is over, and so is the layout that wants it
    assert codes.count("sheet-too-big") == 2


def test_layout_over_the_limit_is_rejected_even_before_the_file(sheets):
    name = sheets.png("body.png", 1056, 1104)
    codes = [f.code for f in only(sheets.check(filename=name, width=132, height=138,
                                               line_length=1, direction_count=64))]
    assert "sheet-too-big" in codes  # 64 rows x 138 = 8832px tall


def test_right_at_the_limit_is_fine(sheets):
    name = sheets.png("edge.png", 8192, 64)
    assert only(sheets.check(filename=name, width=64, height=64,
                             line_length=128, direction_count=128)) == []


# ------------------------------------------------------------- missing files

def test_missing_file(sheets):
    findings = only(sheets.check(filename="__test__/nope.png", width=10, height=10))
    assert [f.code for f in findings] == ["missing-file"]
    assert "nope.png" in findings[0].message


def test_unknown_mod_root_names_the_flag(sheets):
    findings = only(sheets.check(filename="__jamaltron__/x.png", width=10, height=10))
    assert [f.code for f in findings] == ["unknown-mod"]
    assert "--mod-root jamaltron=DIR" in " ".join(findings[0].detail)


def test_a_file_that_is_not_a_png(sheets, tmp_path):
    (tmp_path / "fake.png").write_bytes(b"GIF89a not really a png at all!!")
    findings = only(sheets.check(filename="__test__/fake.png", width=10, height=10))
    assert [f.code for f in findings] == ["bad-png"]


def test_png_size_rejects_junk(tmp_path):
    truncated = tmp_path / "t.png"
    truncated.write_bytes(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ValueError, match="truncated"):
        png_size(truncated)
    wrong = tmp_path / "w.png"
    wrong.write_bytes(b"x" * 40)
    with pytest.raises(ValueError, match="signature"):
        png_size(wrong)


# --------------------------------------------- ragged sheets (a torn last frame)

def test_leftover_pixels_on_a_grid_are_a_torn_frame(sheets):
    """1060x1110 fits a 1056x1104 grid but carries 4x6px of slop: the render and the
    declaration disagree about the frame size.

    WARN, not ERROR - the engine loads a padded sheet, and MEASURED, 11 of 4424 shipped
    declarations are padded. `--strict` is what turns it into a failure, and `--strict`
    is what our own manifest gets.
    """
    name = sheets.png("ragged.png", 1060, 1110)
    fields = dict(filename=name, width=132, height=138, line_length=8, direction_count=64)
    assert only(sheets.check(**fields)) == []
    warnings = only(sheets.check(**fields), WARN)
    assert [f.code for f in warnings] == ["ragged-sheet"]
    assert "4px over horizontally, 6px vertically" in warnings[0].message


def test_padding_around_a_single_frame_is_not_ragged(sheets):
    """core/graphics/empty.png is 64x64 and declared 1x1, and base's 64px icons are
    120px wide because mipmaps pack horizontally. A single frame has nothing to tear."""
    name = sheets.png("empty.png", 64, 64)
    assert sheets.check(filename=name, width=1, height=1) == []
    icon = sheets.png("icon.png", 120, 64)
    assert sheets.check(filename=icon, size=64) == []


def test_size_accepts_both_shapes(sheets):
    """`size = 64` and `size = {w, h}` are both legal. The second is what the stock
    spidertron's minimap_representation uses, and what C.6 has to emit."""
    square = sheets.png("map.png", 128, 128)
    assert sheets.check(filename=square, size=128) == []
    assert sheets.check(filename=square, size=[128, 128]) == []
    oblong = sheets.png("loco.png", 20, 40)
    assert sheets.check(filename=oblong, size=[20, 40]) == []
    findings = only(sheets.check(filename=oblong, size=[40, 20]))
    assert [f.code for f in findings] == ["sheet-too-small"]


def test_a_sliced_shared_sheet_is_not_ragged(sheets):
    """x/y means the remainder is another prototype's art, so the check stands down."""
    name = sheets.png("shared.png", 320, 294)
    assert sheets.check(filename=name, width=40, height=98,
                        line_length=8, direction_count=8, y=98) == []


# --------------------------------------------------------- multi-file animations

def test_filenames_and_lines_per_file(sheets):
    """The shipped spitter-run shape, shrunk: 256 frames of 250x220 at line_length 6
    over 3 files of 15 rows, the last trimmed to its 13 used rows."""
    names = [sheets.png(f"run-{i}.png", 6 * 25, rows * 22)
             for i, rows in ((1, 15), (2, 15), (3, 13))]
    assert sheets.check(filenames=names, width=25, height=22, line_length=6,
                        lines_per_file=15, direction_count=16, frame_count=16) == []


def test_wrong_number_of_files(sheets):
    names = [sheets.png(f"run-{i}.png", 150, 330) for i in (1, 2)]
    findings = only(sheets.check(filenames=names, width=25, height=22, line_length=6,
                                 lines_per_file=15, direction_count=16, frame_count=16))
    assert "file-count" in [f.code for f in findings]
    assert "need 3 file(s), 2 declared" in findings[0].message


def test_filenames_without_lines_per_file(sheets):
    names = [sheets.png(f"run-{i}.png", 150, 330) for i in (1, 2)]
    findings = only(sheets.check(filenames=names, width=25, height=22,
                                 line_length=6, frame_count=180))
    assert [f.code for f in findings] == ["file-count"]


def test_a_short_middle_file_is_caught(sheets):
    """Only the LAST file may be trimmed. A short file 1 is a torn animation."""
    names = [sheets.png("a.png", 150, 22 * 14), sheets.png("b.png", 150, 22 * 15),
             sheets.png("c.png", 150, 22 * 13)]
    findings = only(sheets.check(filenames=names, width=25, height=22, line_length=6,
                                 lines_per_file=15, direction_count=16, frame_count=16))
    assert [f.code for f in findings] == ["sheet-too-small"]
    assert findings[0].origin.endswith("[1]")


# ------------------------------------------------------------- nonsense inputs

@pytest.mark.parametrize("fields, code", [
    ({"width": 0, "height": 10}, "bad-geometry"),
    ({"width": 10, "height": -4}, "bad-geometry"),
    ({"width": 10, "height": 10, "direction_count": 0}, "bad-geometry"),
    ({"width": 10, "height": 10, "x": -1}, "bad-geometry"),
    ({"width": 10}, "no-geometry"),
    ({}, "no-geometry"),
])
def test_rejects_nonsense(sheets, fields, code):
    name = sheets.png("any.png", 64, 64)
    assert [f.code for f in only(sheets.check(filename=name, **fields))] == [code]


def test_a_declaration_with_no_file_is_an_error(sheets):
    spec = SpriteSpec(origin="unit-test", width=10, height=10)
    assert [f.code for f in check_spec(spec, sheets.mods, strict=False)] == ["no-filename"]


def test_an_unreadable_filename_is_reported_once_not_twice(tmp_path, sheets):
    """base computes filenames by concatenation all over the place (entities.lua:75 is
    `path .. name .. ".png"`). One cause, one finding."""
    (tmp_path / "c.lua").write_text('return { filename = p .. ".png", width = 8, height = 8 }')
    findings, _, _ = lint([tmp_path / "c.lua"], sheets.mods, strict=False)
    assert [f.code for f in findings] == ["unresolved-field"]


def test_a_sound_table_is_not_a_sprite(tmp_path, sheets):
    """A sound carries `filename` and no geometry. MEASURED: without this, a sweep over
    base + core + space-age reports 863 .ogg files and 37 .bnvib files as broken
    sprites."""
    (tmp_path / "s.lua").write_text("""
      return {
        working_sound = { filename = "__base__/sound/spidertron/spidertron-vox.ogg",
                          volume = 0.6 },
        haptic = { filename = "__base__/sound/x.bnvib" },
      }
    """)
    findings, declarations, _ = lint([tmp_path / "s.lua"], sheets.mods, strict=False)
    assert declarations == 2  # both were read...
    assert findings == []     # ...and neither was mistaken for art


def test_line_length_does_not_claim_a_row_it_does_not_fill(sheets):
    """MEASURED: space-age's oil-refinery-frozen.png is a 1304x444 four-direction sheet
    whose Sprite4Way entries each declare line_length 4 and slice ONE 326px column with
    x. Multiplying by line_length invents a 1630px rectangle that is not there."""
    name = sheets.png("refinery.png", 4 * 326, 444)
    for column in range(4):
        assert only(sheets.check(filename=name, width=326, height=444,
                                 line_length=4, x=326 * column)) == [], column


# ------------------------------------------------------------------- warnings

def test_unused_frames_is_strict_only(sheets):
    """MEASURED: this fires on 7 of the 24 stock spidertron sheets, because base packs
    one shared file per leg index. Normal in shared art, a smell in generated art - so
    it cannot be a default finding."""
    name = sheets.png("body.png", 1056, 1104)
    fields = dict(filename=name, width=132, height=138, line_length=8, direction_count=32)
    assert sheets.check(**fields) == []
    warnings = only(sheets.check(strict=True, **fields), WARN)
    assert [f.code for f in warnings] == ["unused-frames"]
    assert "holds 64 frame(s), the declaration uses 32" in warnings[0].message


def test_line_length_wider_than_the_animation_warns(sheets):
    name = sheets.png("strip.png", 80, 10)
    findings = sheets.check(filename=name, width=10, height=10,
                            line_length=8, frame_count=3)
    assert [f.code for f in findings] == ["line-length-unused"]
    assert all(f.severity == WARN for f in findings)


def test_unmodelled_layout_is_reported_not_guessed_at(sheets):
    """`stripes` and the mirroring flags change the frame layout. Saying so beats
    doing the arithmetic wrong and passing."""
    name = sheets.png("body.png", 1056, 1104)
    findings = sheets.check(filename=name, width=132, height=138,
                            direction_count=64, line_length=8, back_equals_front=True)
    assert [f.code for f in findings] == ["unmodelled-layout"]


def test_stripe_children_are_not_visited_separately(tmp_path, sheets):
    """The parent already says `stripes` is unmodelled. Walking into the stripe entries
    manufactures no-geometry errors about art nobody claimed to check - 20 of them in
    base's character animations alone."""
    (tmp_path / "s.lua").write_text("""
      return {
        mining_tool = {
          width = 178, height = 176, frame_count = 26, direction_count = 8,
          filename = "__test__/unused.png",
          stripes = {
            { filename = "__test__/tool-1.png", width_in_frames = 13, height_in_frames = 8 },
            { filename = "__test__/tool-2.png", width_in_frames = 13, height_in_frames = 8 },
          },
        },
      }
    """)
    findings, declarations, _ = lint([tmp_path / "s.lua"], sheets.mods, strict=False)
    assert declarations == 1, [f.origin for f in findings]
    assert [f.code for f in findings] == ["unmodelled-layout"]


def test_not_a_png_warns(sheets, tmp_path):
    (tmp_path / "art.dds").write_bytes(b"whatever")
    findings = sheets.check(filename="__test__/art.dds", width=10, height=10)
    assert "not-a-png" in [f.code for f in findings]


# ------------------------------------------------------------- the Lua front end

LUA_SAMPLE = """
-- a comment mentioning filename = "__test__/decoy.png" that must not be read
--[==[ a long comment with a { brace } in it ]==]
local scale = 0.5
function torso(spidertron_scale)
return
{
  animation =
  {
    layers =
    {
      {
        filename = "__test__/body.png",
        width = 132,
        height = 138,
        line_length = 8,
        direction_count = 64,
        scale = 0.5 * spidertron_scale,       -- an expression, not geometry
        shift = util.by_pixel(0, -19 * scale) -- a call
      }
    }
  },
  water_reflection =
  {
    pictures =
    {
      filename = "__test__/reflection.png",
      width = 48,
      height = 48,
      variation_count = 1
    }
  }
}
end
"""


def test_lua_reader_finds_nested_layers(sheets, tmp_path):
    sheets.png("body.png", 1056, 1104)
    sheets.png("reflection.png", 48, 48)
    (tmp_path / "torso.lua").write_text(LUA_SAMPLE)
    specs = lint_sprites.specs_from_lua(tmp_path / "torso.lua")
    origins = [s.origin for s in specs]
    assert len(specs) == 2, origins
    assert any("animation.layers.1" in o for o in origins)
    assert any("water_reflection.pictures" in o for o in origins)
    findings, declarations, files = lint([tmp_path / "torso.lua"], sheets.mods, strict=False)
    assert (findings, declarations, files) == ([], 2, 2)


def test_lua_reader_never_resolves_an_expression_as_a_literal(tmp_path):
    """`width = 64 * 2` reading as 64 would be worse than not reading it at all."""
    (tmp_path / "bad.lua").write_text("""
      return { filename = "x.png", width = 64 * 2, height = 138, direction_count = n }
    """)
    spec, = lint_sprites.specs_from_lua(tmp_path / "bad.lua")
    assert spec.width is None
    keys = dict(spec.bad_fields)
    assert "not a literal: 64 * 2" in keys["width"]
    assert "not a literal: n" in keys["direction_count"]
    assert spec.height == 138  # a real literal still reads


def test_unreadable_geometry_is_an_error_never_a_skip(sheets, tmp_path):
    (tmp_path / "bad.lua").write_text(
        'return { filename = "__test__/body.png", width = w, height = 138 }')
    sheets.png("body.png", 1056, 1104)
    findings, _, _ = lint([tmp_path / "bad.lua"], sheets.mods, strict=False)
    codes = [f.code for f in findings]
    assert codes.count("unresolved-field") == 1
    assert all(f.severity == ERROR for f in findings if f.code == "unresolved-field")


def test_lua_reader_handles_concat_negatives_and_size(tmp_path):
    (tmp_path / "s.lua").write_text("""
      return {
        filename = "__base__/x" .. ".png",   -- concat: unreadable
        size = 64,
        x = -8,
        y = 0x10,
      }
    """)
    spec, = lint_sprites.specs_from_lua(tmp_path / "s.lua")
    assert (spec.width, spec.height, spec.x, spec.y) == (64, 64, -8, 16)
    assert dict(spec.bad_fields)["filename"].startswith("not a literal")


def test_lua_reader_survives_long_strings(tmp_path):
    """entity.lua's factoriopedia_simulation is a `[[ ]]` block full of braces."""
    (tmp_path / "e.lua").write_text("""
      local body = {}
      body.factoriopedia_simulation = { init = [[
        game.surfaces[1].create_entity{name = "jamaltron", position = {0, 0}}
      ]] }
      return { filename = "a.png", width = 4, height = 4 }
    """)
    specs = lint_sprites.specs_from_lua(tmp_path / "e.lua")
    assert [s.width for s in specs] == [4]


# ------------------------------------------------------ the JSON manifest front end

def test_manifest_round_trip(sheets, tmp_path):
    sheets.png("body.png", 1056, 1104)
    manifest = tmp_path / "sprites.json"
    manifest.write_text(json.dumps({
        "version": 1,
        "sprites": [{
            "id": "jamaltron.animation",
            "filename": "__test__/body.png",
            "width": 132, "height": 138, "line_length": 8, "direction_count": 64,
        }],
    }))
    findings, declarations, files = lint([manifest], sheets.mods, strict=False)
    assert (findings, declarations, files) == ([], 1, 1)


def test_manifest_accepts_a_bare_list_and_carries_its_own_roots(tmp_path):
    (tmp_path / "graphics").mkdir()
    Image.new("RGBA", (40, 40)).save(tmp_path / "graphics" / "a.png")
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({
        "mod_roots": {"jamaltron": "."},
        "sprites": [{"filename": "__jamaltron__/graphics/a.png", "size": 40}],
    }))
    findings, declarations, _ = lint([manifest], ModPaths(), strict=False)
    assert (findings, declarations) == ([], 1)


def test_manifest_ids_reach_the_finding(sheets, tmp_path):
    sheets.png("small.png", 32, 32)
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"id": "torso.layer1",
                                     "filename": "__test__/small.png",
                                     "width": 64, "height": 64}]))
    findings, _, _ = lint([manifest], sheets.mods, strict=False)
    assert [f.origin for f in findings] == ["torso.layer1"]


def test_a_broken_manifest_is_a_usage_error(tmp_path, capsys):
    (tmp_path / "m.json").write_text("{not json")
    assert main([str(tmp_path / "m.json")]) == 2
    assert "lint-sprites:" in capsys.readouterr().err


def test_a_manifest_with_no_sprites_fails(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"version": 1, "sprites": []}))
    findings, declarations, _ = lint([manifest], ModPaths(), strict=False)
    assert [f.code for f in findings] == ["no-sprites"]
    assert declarations == 0


def test_an_unknown_extension_is_a_usage_error(tmp_path, capsys):
    (tmp_path / "sprites.yaml").write_text("nope")
    assert main([str(tmp_path / "sprites.yaml")]) == 2


# ---------------------------------------------------------------------- the CLI

def _manifest(tmp_path, **fields):
    manifest = tmp_path / "sprites.json"
    manifest.write_text(json.dumps({"sprites": [dict(id="torso", **fields)]}))
    return str(manifest)


def test_cli_passes_and_prints_a_tally(sheets, tmp_path, capsys):
    sheets.png("body.png", 1056, 1104)
    target = _manifest(tmp_path, filename="__test__/body.png", width=132, height=138,
                       line_length=8, direction_count=64)
    assert main(["--mod-root", f"test={tmp_path}", target]) == 0
    out = capsys.readouterr().out
    assert "PASSED" in out and "1 declaration(s), 1 file(s), 0 error(s)" in out


def test_cli_quiet_says_nothing_when_clean(sheets, tmp_path, capsys):
    sheets.png("body.png", 1056, 1104)
    target = _manifest(tmp_path, filename="__test__/body.png", width=132, height=138,
                       line_length=8, direction_count=64)
    assert main(["-q", "--mod-root", f"test={tmp_path}", target]) == 0
    assert capsys.readouterr().out == ""


def test_cli_fails_on_an_error(sheets, tmp_path, capsys):
    sheets.png("small.png", 32, 32)
    target = _manifest(tmp_path, filename="__test__/small.png", width=64, height=64)
    assert main(["--mod-root", f"test={tmp_path}", target]) == 1
    assert "FAILED" in capsys.readouterr().out


def test_cli_strict_turns_a_warning_into_a_failure(sheets, tmp_path, capsys):
    sheets.png("body.png", 1056, 1104)
    target = _manifest(tmp_path, filename="__test__/body.png", width=132, height=138,
                       line_length=8, direction_count=32)
    argv = ["--mod-root", f"test={tmp_path}", target]
    assert main(argv) == 0
    assert main(["--strict"] + argv) == 1
    assert "unused-frames" in capsys.readouterr().out


def test_cli_rejects_a_malformed_mod_root(tmp_path, capsys):
    assert main(["--mod-root", "bogus", str(tmp_path / "x.json")]) == 2
    assert "NAME=DIR" in capsys.readouterr().err


def test_cli_rejects_a_missing_factorio_data_dir(tmp_path, capsys):
    assert main(["--factorio-data", str(tmp_path / "nope"), str(tmp_path / "x.json")]) == 2
    assert "not a directory" in capsys.readouterr().err


# ----------------------------------------------------------- environment guards

def test_lint_sprites_stays_stdlib_only():
    """CI runs this with no venv and no Pillow: `python3 tools/lint_sprites.py ...`.
    The only non-stdlib import allowed is our own render package, which is also
    stdlib-only (test_env.py pins that)."""
    source = (TOOLS / "lint_sprites.py").read_text()
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    offenders = imported - sys.stdlib_module_names - {"render"}
    assert not offenders, f"non-stdlib imports in lint_sprites.py: {sorted(offenders)}"


# --------------------------------------------------- reality: Wube's shipped art

@needs_factorio
def test_the_stock_spidertron_declarations_are_clean():
    """A linter that flags Wube's own shipped art is wrong. 25 declarations across 22
    files, including the 1056x1104 64-rotation torso and the shared 320x294 leg sheets."""
    mods = ModPaths()
    mods.add_factorio_data(FACTORIO_DATA)
    target = FACTORIO_DATA / "base/prototypes/entity/spidertron-animations.lua"
    findings, declarations, files = lint([target], mods, strict=False)
    assert findings == [], "\n".join(f.render() for f in findings)
    assert (declarations, files) == (25, 22)
    # --strict adds exactly the 7 documented unused-frames warnings and nothing else:
    # base packs one shared file per leg index (320x294 = 8 leg columns x 3 render
    # passes), so every leg and knee sheet holds more frames than one declaration slices.
    # Zero ragged-sheet and zero no-line-length, i.e. every stock spidertron sheet is an
    # exact multiple of its frame and every one of them declares its line_length.
    strict, _, _ = lint([target], mods, strict=True)
    assert sorted({f.code for f in strict}) == ["unused-frames"], \
        "\n".join(f.render() for f in strict)
    assert len(strict) == 7
    assert all(f.severity == WARN for f in strict)


@needs_factorio
def test_the_stock_spidertron_minimap_declarations_are_clean():
    """These live in entities.lua's create_spidertron, not in spidertron-animations.lua,
    and they are the `size = {128, 128}` shape. C.6 emits the jamaltron equivalents."""
    mods = ModPaths()
    mods.add_factorio_data(FACTORIO_DATA)
    specs = [s for s in lint_sprites.specs_from_lua(
                 FACTORIO_DATA / "base/prototypes/entity/entities.lua")
             if s.filenames and "spidertron-map" in s.filenames[0]]
    assert len(specs) == 2, [s.origin for s in specs]
    assert {(s.width, s.height) for s in specs} == {(128, 128)}
    for spec in specs:
        assert check_spec(spec, mods, strict=True) == []


@needs_factorio
def test_the_stock_torso_sheet_is_measured_not_assumed():
    """Pins the numbers the rest of Phase C is calibrated against (C.3's overlay)."""
    body = FACTORIO_DATA / "base/graphics/entity/spidertron/torso/spidertron-body.png"
    assert png_size(body) == (1056, 1104) == (8 * 132, 8 * 138)
