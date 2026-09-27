"""render/icons.py's pure half: cropping, the mipmap strip, the minimap silhouette, the legs,
and that what it writes is what the C.15 icon gate accepts. No Blender, no model."""

import json

import pytest
from PIL import Image, ImageDraw

import lint_sprites
from render import icons


def disc(size=256, r=80, rgb=(255, 255, 255)) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r],
                                fill=rgb + (255,))
    return img


def test_mip_strip_is_base_layout():
    strip = icons.mip_strip(disc(), 64, 4)
    assert strip.size == (120, 64)
    assert lint_sprites.mipmap_levels(*strip.size) == 4
    # Top-aligned: the 8px level sits at x=112, y 0..7, and nothing below it.
    assert strip.crop((112, 0, 120, 8)).getchannel("A").getextrema()[1] > 0
    assert strip.crop((112, 8, 120, 64)).getchannel("A").getextrema() == (0, 0)


def test_tech_strip_is_base_layout():
    assert icons.mip_strip(disc(512, 160), 256, 4).size == (480, 256)


def test_mip_widths_refuses_a_fractional_level():
    with pytest.raises(ValueError):
        icons.mip_widths(12, 4)


def test_premultiplied_resize_leaves_no_dark_halo():
    """A property, not a mutation check: Pillow's plain RGBA resize passes too (it
    premultiplies internally). Here so a switch to a resampler that does not fails."""
    small = icons.premul_resize(disc(), (32, 32))
    edge = [px for px in small.get_flattened_data() if 0 < px[3] < 255]
    assert edge, "no antialiased edge to test"
    assert min(min(px[:3]) for px in edge) >= 250


def test_square_box_core_lets_a_thin_tail_run_off():
    img = disc(512, 60)
    ImageDraw.Draw(img).line([(256, 256), (256, 10)], fill=(255, 255, 255, 255), width=6)
    whole = icons.square_box(img, margin=0.0)
    core = icons.square_box(img, margin=0.0, core=10)
    assert whole[2] > 240 and core[2] <= 122
    assert icons.cut(img, core).size == (core[2], core[2])


def test_square_box_refuses_an_empty_image():
    with pytest.raises(ValueError):
        icons.square_box(Image.new("RGBA", (16, 16)), margin=0.0)


@pytest.mark.parametrize("rim", [icons.MAP_RIM, icons.MAP_RIM_SELECTED])
def test_silhouette_is_flat_base_style(rim):
    out = icons.silhouette(disc(), icons.MINIMAP, rim)
    assert out.size == (128, 128)
    colours = {px for px in out.get_flattened_data()}
    assert colours <= {icons.MAP_FILL, rim, (0, 0, 0, 0)}
    assert rim in colours and icons.MAP_FILL in colours
    # The rim is inside the canvas: the outermost ring of pixels stays transparent.
    assert out.getpixel((0, 64))[3] == 0 and out.getpixel((127, 64))[3] == 0


def test_leg_segments_put_south_feet_in_front_and_knees_up():
    mounts = [((10.0, -5.0), (100.0, -80.0)), ((10.0, 5.0), (100.0, 80.0))]
    segs = icons.leg_segments(mounts, stance=0.5, knee_lift_px=30.0)
    (m0, k0, f0, front0), (m1, k1, f1, front1) = segs
    assert (front0, front1) == (False, True)
    assert f1 == (50.0, 40.0)
    # The knee sits above the straight mount-to-foot line.
    t = icons.leg_segments(mounts, stance=0.5, knee_lift_px=0.0)[1][1]
    assert k1[1] == pytest.approx(t[1] - 30.0)


def test_candidates_are_at_least_three_distinct_looks():
    names = [c.name for c in icons.CANDIDATES]
    assert len(names) >= 3 and len(set(names)) == len(names)
    assert any(c.legs for c in icons.CANDIDATES)
    assert any("beached" in c.icon.config for c in icons.CANDIDATES)


@pytest.mark.parametrize("cand", icons.CANDIDATES, ids=lambda c: c.name)
def test_candidate_manifest_passes_the_gate_at_the_sizes_build_writes(tmp_path, cand):
    """Every file the manifest names, at the geometry build() produces it, lints clean
    --strict. The same manifest then gates the real renders in render-out/."""
    icons.write_manifest(tmp_path, cand)
    blob = json.loads((tmp_path / "icons.json").read_text())
    sizes = {"icon": (120, 64), "technology": (480, 256), "minimap": (128, 128),
             "thumbnail": (144, 144)}
    for entry in blob["icons"]:
        name = entry["filename"].split("/", 1)[1]
        Image.new("RGBA", sizes[entry["kind"]]).save(tmp_path / name)
    result = lint_sprites.lint_detail([tmp_path / "icons.json"], lint_sprites.ModPaths(),
                                      strict=True)
    assert result.findings == []
    assert result.icons == (7 if cand.harness else 5)


def test_build_writes_nothing_under_the_mod():
    """chotchki picks the look first: a render's only output root is render-out/. --promote
    is the one writer into the mod, and it renders nothing."""
    assert icons.OUT.parts[-3:] == ("render-out", "review", "icons")
    assert "mod" not in icons.OUT.relative_to(icons.REPO).parts


# ------------------------------------------------------------------------- promote

SIZES = {"icon": (120, 64), "technology": (480, 256), "minimap": (128, 128),
         "thumbnail": (144, 144)}


def candidate(root, name="portrait", samples=64, skip=(), sizes=None):
    """A rendered-looking candidate dir: every file build() writes, distinct pixels each, and
    the manifest build() writes beside them."""
    cand = next(c for c in icons.CANDIDATES if c.name == name)
    d = root / name
    d.mkdir(parents=True)
    icons.write_manifest(d, cand, samples)
    for i, (src, _, _, kind) in enumerate(icons.SHIPPED):
        if src not in skip:
            size = (sizes or {}).get(src, SIZES[kind])
            Image.new("RGBA", size, (i, 2 * i, 3 * i, 200)).save(d / src)
    return d


def test_promote_ships_the_reviewed_bytes_and_a_manifest_the_gates_read(tmp_path):
    import test_icon_coverage as coverage
    src = candidate(tmp_path / "review")
    mod = tmp_path / "mod"
    (mod / "graphics").mkdir(parents=True)
    written = icons.promote("portrait", tmp_path / "review", mod)
    assert len(written) == len(icons.SHIPPED) + 1
    for name, dest, _, _ in icons.SHIPPED:
        assert (mod / dest).read_bytes() == (src / name).read_bytes(), dest
    assert (mod / "thumbnail.png").is_file()
    blob = json.loads((mod / icons.SHIPPED_MANIFEST).read_text())
    assert blob == icons.shipped_manifest("portrait", 64)
    assert blob["mod_roots"] == {"jamaltron": ".."} and blob["sprites"] == []
    # Linted in place (manifest's own mod_roots), and seen by both C.15 gaps' tests.
    result = lint_sprites.lint_detail([mod / icons.SHIPPED_MANIFEST], lint_sprites.ModPaths(),
                                      strict=True)
    assert result.findings == [] and result.icons == len(icons.SHIPPED)
    assert coverage._ci_declares_sprites()(str(mod / icons.SHIPPED_MANIFEST))
    assert coverage.undeclared_icon_pngs(mod) == []


@pytest.mark.parametrize("samples", [None, 16])
def test_promote_refuses_a_preview_render_and_touches_nothing(tmp_path, samples):
    candidate(tmp_path / "review", samples=samples)
    mod = tmp_path / "mod"
    with pytest.raises(icons.PromoteError, match="samples"):
        icons.promote("portrait", tmp_path / "review", mod)
    assert not mod.exists()


def test_promote_refuses_a_candidate_without_the_tintable_pair(tmp_path):
    candidate(tmp_path / "review", skip=("icon-tintable.png", "icon-tintable-mask.png"))
    with pytest.raises(icons.PromoteError, match="tintable"):
        icons.promote("portrait", tmp_path / "review", tmp_path / "mod")
    assert not (tmp_path / "mod").exists()


def test_promote_refuses_a_candidate_that_fails_the_strict_lint(tmp_path):
    candidate(tmp_path / "review", sizes={"technology.png": (256, 256)})
    with pytest.raises(icons.PromoteError, match="icon-mipmaps"):
        icons.promote("portrait", tmp_path / "review", tmp_path / "mod")
    assert not (tmp_path / "mod").exists()


def test_the_shipped_set_is_promoted_and_wired_where_the_readers_see_it():
    """The real mod: graphics/icons.json is --promote's output (not hand-edited), and every
    shipped file but the thumbnail (the engine finds that one by name) is named by a Lua
    literal the C.15 readers see - an icon field for icons, a sprite table for the minimap.
    A path left on __base__, or moved into a non-literal, fails here."""
    import test_icon_coverage as coverage
    mod = icons.PROMOTE_ROOT
    blob = json.loads((mod / icons.SHIPPED_MANIFEST).read_text())
    assert blob == icons.shipped_manifest(blob["candidate"], blob["samples"])
    assert blob["candidate"] == "portrait" and blob["samples"] >= icons.SHIP_SAMPLES
    lua_icons = {spec.filename for _, spec in coverage.our_lua_icons(mod)[1]}
    lua_sprites = {f for path in mod.rglob("*.lua")
                   for spec in lint_sprites.specs_from_lua(path) for f in spec.filenames}
    for _, dest, ident, kind in icons.SHIPPED:
        name = f"__jamaltron__/{dest}"
        if kind == "thumbnail":
            assert dest == "thumbnail.png" and (mod / dest).is_file()
        elif kind == "minimap":
            assert name in lua_sprites, f"{ident}: {name} is not a sprite literal in the mod"
        else:
            assert name in lua_icons, f"{ident}: {name} is not an icon literal in the mod"


def minimap_declarations(mod) -> dict[str, list[tuple[str, tuple, object]]]:
    """Every Lua sprite table in `mod` naming a shipped minimap file, as (where, size, scale).
    The strict lint only catches a declaration LARGER than the file; a smaller one passes it."""
    files = {f"__jamaltron__/{dest}": dest for _, dest, _, kind in icons.SHIPPED
             if kind == "minimap"}
    found: dict[str, list[tuple[str, tuple, object]]] = {dest: [] for dest in files.values()}
    for path in sorted(mod.rglob("*.lua")):
        source = path.read_text(encoding="utf-8", errors="replace")
        for table in lint_sprites.read_lua_tables(source):
            for _, sprite in lint_sprites.iter_sprite_tables(table):
                if sprite.get("filename") in files:
                    size = sprite.get("size")
                    size = (size.get(1), size.get(2)) if isinstance(size, dict) else (size, size)
                    found[files[sprite["filename"]]].append(
                        (f"{path.name}:{sprite.line}", size, sprite.get("scale")))
    return found


def minimap_findings(mod) -> list[str]:
    """Base's shape: the whole file declared (size == its pixels, x/y unset) at scale 0.5.
    An under-declared size draws only the top-left of the marker and no other gate sees it."""
    out = []
    for dest, decls in minimap_declarations(mod).items():
        if not decls:
            out.append(f"{dest}: no sprite literal names it")
        with Image.open(mod / dest) as img:
            pixels = img.size
        for where, size, scale in decls:
            if size != pixels:
                out.append(f"{where}: {dest} declares size {size}, file is {pixels}")
            if scale != 0.5:
                out.append(f"{where}: {dest} scale {scale}, base's minimap is 0.5")
    return out


def test_the_minimap_pair_declares_the_whole_file_at_base_scale():
    assert minimap_findings(icons.PROMOTE_ROOT) == []


def test_an_under_declared_minimap_is_caught(tmp_path):
    """The planted case the strict lint passes: size {64, 64} over the 128x128 file."""
    mod = tmp_path / "mod"
    for _, dest, _, kind in icons.SHIPPED:
        if kind == "minimap":
            (mod / dest).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", SIZES["minimap"], (255, 255, 255, 255)).save(mod / dest)
    lua = (icons.PROMOTE_ROOT / "prototypes" / "entity.lua").read_text()
    assert lua.count("size = {128, 128}") == 2
    (mod / "entity.lua").write_text(lua.replace("size = {128, 128}", "size = {64, 64}", 1))
    found = minimap_findings(mod)
    assert len(found) == 1 and "declares size (64, 64), file is (128, 128)" in found[0]
    (mod / "entity.lua").write_text(lua.replace("scale = 0.5", "scale = 1", 1))
    found = minimap_findings(mod)
    assert len(found) == 1 and "scale 1" in found[0]
