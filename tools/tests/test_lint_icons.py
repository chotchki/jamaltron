"""PLAN C.15: the icon half of lint_sprites.py. Real PNGs built with Pillow in a tmpdir
(same rule as test_lint_sprites.py: a gate tested against mocks only proves the mocks).

The last two tests run against the installed Factorio 2.1.17 (skipped without it) to prove
the icon checks do not slander Wube's own icons.
"""

import json
import pathlib
import re
import textwrap

import pytest
from PIL import Image

import lint_sprites
from lint_sprites import ERROR, WARN, ModPaths, lint, lint_detail, main

FACTORIO_DATA = pathlib.Path("/Applications/factorio.app/Contents/data")
REPO = pathlib.Path(__file__).resolve().parents[2]

needs_factorio = pytest.mark.skipif(not FACTORIO_DATA.is_dir(),
                                    reason="Factorio 2.1.17 data not installed here")


def png(root: pathlib.Path, name: str, width: int, height: int, mode: str = "RGBA") -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new(mode, (width, height)).save(path)


def manifest(root: pathlib.Path, icons: list, name: str = "icons.json") -> pathlib.Path:
    path = root / name
    path.write_text(json.dumps({"version": 1, "mod_roots": {"jamaltron": "."},
                                "sprites": [], "icons": icons}))
    return path


def findings_for(tmp_path, entry: dict, files: dict, strict: bool = True):
    """Lint one icon entry against the PNGs in `files` ({name: (w, h)})."""
    for name, (w, h) in files.items():
        png(tmp_path, name, w, h)
    found, declarations, _ = lint([manifest(tmp_path, [entry])], ModPaths(), strict=strict)
    assert declarations == 1
    return found


def codes(found) -> list[str]:
    return [f.code for f in found]


# ------------------------------------------------------------------ the arithmetic

def test_mipmap_widths_are_base_layout():
    # 64+32+16+8 = 120 is __base__/graphics/icons/spidertron.png; 480 is its tech icon.
    assert lint_sprites.mipmap_widths(64)[:4] == [64, 96, 112, 120]
    assert lint_sprites.mipmap_widths(256)[3] == 480
    assert lint_sprites.mipmap_widths(144)[:5] == [144, 216, 252, 270, 279]


def test_mipmap_widths_stop_at_an_odd_level():
    # 12 -> 6 -> 3 and then no 1.5px level exists.
    assert lint_sprites.mipmap_widths(12) == [12, 18, 21]


@pytest.mark.parametrize("w,h,levels", [(64, 64, 1), (120, 64, 4), (480, 256, 4),
                                        (128, 128, 1), (100, 64, None), (32, 64, None)])
def test_mipmap_levels_is_read_off_the_width(w, h, levels):
    assert lint_sprites.mipmap_levels(w, h) == levels


# ------------------------------------------------------------------ passing cases

@pytest.mark.parametrize("kind,size", [("icon", (120, 64)), ("technology", (480, 256)),
                                       ("minimap", (128, 128)), ("thumbnail", (144, 144))])
def test_each_kind_passes_at_base_geometry(tmp_path, kind, size):
    name = "thumbnail.png" if kind == "thumbnail" else f"{kind}.png"
    entry = {"id": kind, "kind": kind, "filename": f"__jamaltron__/{name}"}
    assert findings_for(tmp_path, entry, {name: size}) == []


def test_explicit_icon_size_and_mipmaps_override_the_kind(tmp_path):
    entry = {"id": "small", "kind": "icon", "icon_size": 32, "mipmaps": 1,
             "filename": "__jamaltron__/small.png"}
    assert findings_for(tmp_path, entry, {"small.png": (32, 32)}) == []


def test_an_icons_only_manifest_is_not_no_sprites(tmp_path, capsys):
    png(tmp_path, "icon.png", 120, 64)
    target = manifest(tmp_path, [{"id": "i", "filename": "__jamaltron__/icon.png"}])
    assert main(["--strict", str(target)]) == 0
    out = capsys.readouterr().out
    assert "PASSED" in out and "1 of the declarations are icons" in out


# ------------------------------------------------------------------ failing cases

def test_wrong_size_fails_naming_the_declared_size(tmp_path):
    entry = {"id": "item", "kind": "icon", "filename": "__jamaltron__/icon.png"}
    found = findings_for(tmp_path, entry, {"icon.png": (240, 128)})
    assert codes(found) == ["icon-size"]
    assert found[0].severity == ERROR
    assert "240x128, declared icon_size 64" in found[0].message
    assert "64 (1), 96 (2), 112 (3), 120 (4)" in found[0].detail[0]


def test_wrong_mipmap_count_fails_with_both_counts(tmp_path):
    entry = {"id": "item", "kind": "icon", "filename": "__jamaltron__/icon.png"}
    found = findings_for(tmp_path, entry, {"icon.png": (96, 64)})
    assert codes(found) == ["icon-mipmaps"]
    assert "wants 4 mipmap level(s) (120x64)" in found[0].message
    assert "holds 2 (96x64)" in found[0].message


def test_a_minimap_with_mipmaps_fails(tmp_path):
    # Base declares its minimap as a plain 128x128 Sprite: no chain.
    entry = {"id": "map", "kind": "minimap", "filename": "__jamaltron__/map.png"}
    assert codes(findings_for(tmp_path, entry, {"map.png": (192, 128)})) == ["icon-mipmaps"]


@pytest.mark.parametrize("size,phrase", [((100, 64), "neither a square 64x64 nor a mipmap chain"),
                                         ((32, 64), "narrower than it is tall")])
def test_non_square_fails(tmp_path, size, phrase):
    entry = {"id": "item", "kind": "icon", "icon_size": size[1],
             "filename": "__jamaltron__/icon.png"}
    found = findings_for(tmp_path, entry, {"icon.png": size})
    assert codes(found) == ["icon-not-square"]
    assert phrase in found[0].message


@pytest.mark.parametrize("size", [(128, 128), (256, 256), (144, 72), (216, 144)])
def test_a_thumbnail_not_144_square_fails(tmp_path, size):
    entry = {"id": "thumb", "kind": "thumbnail", "filename": "__jamaltron__/thumbnail.png"}
    found = findings_for(tmp_path, entry, {"thumbnail.png": size})
    assert codes(found) == ["thumbnail-size"]
    assert f"is {size[0]}x{size[1]}, must be 144x144" in found[0].message


def test_a_thumbnail_off_the_mod_root_fails(tmp_path):
    entry = {"id": "thumb", "kind": "thumbnail",
             "filename": "__jamaltron__/graphics/thumbnail.png"}
    found = findings_for(tmp_path, entry, {"graphics/thumbnail.png": (144, 144)})
    assert codes(found) == ["thumbnail-path"]


def test_a_missing_icon_file_fails(tmp_path):
    entry = {"id": "item", "filename": "__jamaltron__/gone.png"}
    assert codes(findings_for(tmp_path, entry, {})) == ["missing-file"]


def test_an_unknown_kind_is_an_error_not_a_default(tmp_path):
    entry = {"id": "item", "kind": "badge", "filename": "__jamaltron__/icon.png"}
    found = findings_for(tmp_path, entry, {"icon.png": (120, 64)})
    assert codes(found) == ["unresolved-icon"]
    assert "'badge' is not one of" in found[0].message


def test_an_opaque_icon_warns_and_fails_strict(tmp_path, capsys):
    Image.new("RGB", (120, 64)).save(tmp_path / "icon.png")
    target = manifest(tmp_path, [{"id": "i", "filename": "__jamaltron__/icon.png"}])
    found, _, _ = lint([target], ModPaths(), strict=False)
    assert [(f.severity, f.code) for f in found] == [(WARN, "icon-no-alpha")]
    assert main([str(target)]) == 0
    assert main(["--strict", str(target)]) == 1


def test_an_opaque_thumbnail_is_fine(tmp_path):
    # space-age/thumbnail.png is RGB. A thumbnail is shown on a panel, not over the world.
    Image.new("RGB", (144, 144)).save(tmp_path / "thumbnail.png")
    target = manifest(tmp_path, [{"id": "t", "kind": "thumbnail",
                                  "filename": "__jamaltron__/thumbnail.png"}])
    assert lint([target], ModPaths(), strict=True)[0] == []


def test_png_has_alpha_reads_palette_transparency(tmp_path):
    with_trns = Image.new("P", (8, 8))
    with_trns.info["transparency"] = 0
    with_trns.save(tmp_path / "p.png", transparency=0)
    Image.new("P", (8, 8)).save(tmp_path / "q.png")
    assert lint_sprites.png_has_alpha(tmp_path / "p.png")
    assert not lint_sprites.png_has_alpha(tmp_path / "q.png")


@pytest.mark.parametrize("mode,key", [("L", 0), ("RGB", (0, 0, 0))])
def test_png_has_alpha_reads_a_colour_key(tmp_path, mode, key):
    # tRNS on greyscale (type 0) and RGB (type 2) is a transparent colour key, not only
    # a palette thing: the PNG spec allows it on all three.
    Image.new(mode, (8, 8)).save(tmp_path / "keyed.png", transparency=key)
    Image.new(mode, (8, 8)).save(tmp_path / "plain.png")
    assert lint_sprites.png_has_alpha(tmp_path / "keyed.png")
    assert not lint_sprites.png_has_alpha(tmp_path / "plain.png")


# ------------------------------------------------------------------ the Lua front end

def test_lua_icons_are_read_with_their_sizes(tmp_path):
    png(tmp_path, "tech.png", 480, 256)
    png(tmp_path, "item.png", 120, 64)
    png(tmp_path, "layer.png", 32, 32)
    src = tmp_path / "p.lua"
    src.write_text(textwrap.dedent("""
        data:extend({
          {type = "technology", name = "t", icon = "__test__/tech.png", icon_size = 256},
          {type = "item", name = "i", icon = "__test__/item.png"},
          {type = "item", name = "j", icons = {{icon = "__test__/layer.png", icon_size = 32}}},
        })
    """))
    mods = ModPaths()
    mods.add("test", tmp_path)
    result = lint_detail([src], mods, strict=True)
    assert (result.findings, result.icons) == ([], 3)


def test_lua_does_not_impose_our_level_count(tmp_path):
    # Somebody else's 64px icon with no chain is legal; the manifest's 4 levels are OUR rule.
    png(tmp_path, "plain.png", 64, 64)
    src = tmp_path / "p.lua"
    src.write_text('data:extend({{type = "item", name = "i", icon = "__test__/plain.png"}})')
    mods = ModPaths()
    mods.add("test", tmp_path)
    assert lint([src], mods, strict=True)[0] == []


def test_lua_refuses_a_concatenated_icon_path(tmp_path):
    src = tmp_path / "p.lua"
    src.write_text('data:extend({{type = "item", name = "i", '
                   'icon = "__test__/p-" .. n .. ".png"}})')
    found, declarations, _ = lint([src], ModPaths(), strict=False)
    assert declarations == 1 and codes(found) == ["unresolved-icon"]


def test_lua_icon_size_mismatch_fails(tmp_path):
    png(tmp_path, "tech.png", 480, 256)
    src = tmp_path / "p.lua"
    src.write_text('data:extend({{type = "technology", name = "t", '
                   'icon = "__test__/tech.png", icon_size = 128}})')
    mods = ModPaths()
    mods.add("test", tmp_path)
    assert codes(lint([src], mods, strict=False)[0]) == ["icon-size"]


def lua_icons(tmp_path, body: str, files: dict):
    """Lint one Lua table constructor `body` (one line, so every origin is `p.lua:1`)
    against PNGs `files` ({name: (w, h)}) under a `__test__` root. The table is
    data:extend's first entry, so its dotted path is `1`."""
    for name, (w, h) in files.items():
        png(tmp_path, name, w, h)
    src = tmp_path / "p.lua"
    src.write_text(f"data:extend({{{{{body}}}}})")
    mods = ModPaths()
    mods.add("test", tmp_path)
    return lint_detail([src], mods, strict=True)


def test_lua_tintable_size_is_its_own_not_icon_size(tmp_path):
    """2.1.17's ItemWithEntityDataPrototype: icon_tintable_size and icon_tintable_mask_size,
    each defaulting to 64 - NOT inherited from icon_size. A 32px icon beside the 64px
    tintable pair is legal, and reading the pair against icon_size called it icon-size."""
    result = lua_icons(tmp_path, 'type = "item-with-entity-data", name = "i", '
                       'icon = "__test__/i.png", icon_size = 32, '
                       'icon_tintable = "__test__/t.png", icon_tintable_mask = "__test__/m.png"',
                       {"i.png": (32, 32), "t.png": (120, 64), "m.png": (120, 64)})
    assert (result.findings, result.icons) == ([], 3)


#: Typed out from 2.1.17's prototype-api.json, NOT read off ICON_FIELDS: a test that
#: parametrizes over the table it checks cannot notice a row going missing or wrong.
DOCUMENTED_ICON_FIELDS = [
    ("icon", "icon_size"),                                  # IconData and every prototype
    ("icon_tintable", "icon_tintable_size"),                # ItemWithEntityDataPrototype
    ("icon_tintable_mask", "icon_tintable_mask_size"),      # ItemWithEntityDataPrototype
    ("dark_background_icon", "dark_background_icon_size"),  # ItemPrototype
    ("small_icon", "small_icon_size"),                      # ShortcutPrototype
]


def test_icon_fields_are_the_documented_ones():
    assert lint_sprites.ICON_FIELDS == dict(DOCUMENTED_ICON_FIELDS)


@pytest.mark.parametrize("field,size_key", DOCUMENTED_ICON_FIELDS)
def test_lua_each_icon_field_is_read_and_sized_by_its_own_key(tmp_path, field, size_key):
    """Each field three ways: its default of 64 (a 32px file fails, naming the field), its
    own size key honoured (16 with a 16px file passes) and its own size key checked (16
    with the 32px file fails). A dropped field fails the first case; the wrong size key
    fails the second."""
    head = f'type = "item", name = "i", {field} = "__test__/f.png"'
    found = lua_icons(tmp_path, head, {"f.png": (32, 32)}).findings
    assert [(f.code, f.origin) for f in found] == [("icon-size", f"p.lua:1 1 {field} (f.png)")]
    assert "declared icon_size 64" in found[0].message

    assert lua_icons(tmp_path, f"{head}, {size_key} = 16", {"f.png": (16, 16)}).findings == []

    found = lua_icons(tmp_path, f"{head}, {size_key} = 16", {"f.png": (32, 32)}).findings
    assert [(f.code, f.origin) for f in found] == [("icon-size", f"p.lua:1 1 {field} (f.png)")]


# ------------------------------------------------------------------ multi-manifest runs

def test_each_manifest_resolves_against_its_own_roots(tmp_path):
    """Regression: manifest mod_roots used to land in ONE shared ModPaths, first come first
    served, so the second manifest's __jamaltron__ resolved into the first's directory."""
    targets = []
    for name, size in (("a", (120, 64)), ("b", (120, 64))):
        root = tmp_path / name
        png(root, "icon.png", *size)
        targets.append(manifest(root, [{"id": name, "filename": "__jamaltron__/icon.png"}]))
    (tmp_path / "b" / "icon.png").unlink()
    result = lint_detail(targets, ModPaths(), strict=True)
    assert [(f.origin, f.code) for f in result.findings] == [("b", "missing-file")]
    assert result.files == 2


# ------------------------------------------------------------------ the CI contract

def _ci_declares_sprites():
    """ci.yml's own classifier, exec'd out of the workflow - no copy of it here."""
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text()
    match = re.search(r"^( *)def declares_sprites\(path\):\n(?:\1 .*\n|\s*\n)+", ci, re.M)
    assert match, "ci.yml's declares_sprites() moved: re-point this test at it"
    namespace: dict = {}
    exec("import json, pathlib\n" + textwrap.dedent(match.group(0)), namespace)
    return namespace["declares_sprites"]


def test_ci_classifies_an_icon_manifest_as_ours(tmp_path):
    """The C.15 promise: an icons manifest carrying `"sprites": []` is picked up by the CI
    sprite job with no workflow change. If ci.yml's classifier stops recognising it the
    icons silently ship ungated, so that fails here."""
    declares = _ci_declares_sprites()
    target = manifest(tmp_path, [{"id": "i", "filename": "__jamaltron__/icon.png"}])
    assert declares(str(target))
    no_sprites_key = tmp_path / "bare.json"
    no_sprites_key.write_text(json.dumps({"icons": []}))
    assert not declares(str(no_sprites_key)), "the classifier got looser - update C.15's note"


# ------------------------------------------------------------------ calibration

@needs_factorio
def test_base_spidertron_icons_pass():
    mods = ModPaths()
    mods.add_factorio_data(FACTORIO_DATA)
    icons = [
        {"id": "item", "kind": "icon", "filename": "__base__/graphics/icons/spidertron.png"},
        {"id": "tintable", "kind": "icon",
         "filename": "__base__/graphics/icons/spidertron-tintable-mask.png"},
        {"id": "tech", "kind": "technology",
         "filename": "__base__/graphics/technology/spidertron.png"},
        {"id": "map", "kind": "minimap",
         "filename": "__base__/graphics/entity/spidertron/spidertron-map.png"},
        {"id": "sel", "kind": "minimap",
         "filename": "__base__/graphics/entity/spidertron/spidertron-map-selected.png"},
        {"id": "thumb", "kind": "thumbnail", "filename": "__base__/thumbnail.png"},
    ]
    specs = lint_sprites.icon_specs_from_manifest({"icons": icons}, pathlib.Path("x.json"))
    assert [f for s in specs for f in lint_sprites.check_icon(s, mods, strict=True)] == []


@needs_factorio
def test_every_builtin_icon_declaration_is_clean_or_honestly_unresolved():
    """1566 icons across all six built-in mods, --strict. MEASURED 2026-09-26: the literal
    ones produce nothing; the 29 others are string concatenations the reader refuses."""
    mods = ModPaths()
    mods.add_factorio_data(FACTORIO_DATA)
    files = [p for m in lint_sprites.BUILTIN_MODS for p in (FACTORIO_DATA / m).rglob("*.lua")
             if "prototypes" in p.parts]
    icons = [i for f in files for i in lint_sprites.icon_specs_from_lua(f)]
    found = [f for i in icons for f in lint_sprites.check_icon(i, mods, strict=True)]
    assert len(icons) > 1500
    assert {f.code for f in found} <= {"unresolved-icon"}, found[:3]
