"""The C.7 packer's arithmetic and its two output artifacts.

Nothing here launches Blender or opens the bought model: frames are drawn with Pillow,
which is the whole reason the geometry lives in pure functions. The parts that can be
quietly wrong -- a shift half a pixel off, a line_length that leaves blank cells, a Lua
table that has drifted from the manifest beside it -- are exactly the parts a render
never tells you about.

Fixtures come from somewhere real wherever one exists: the stock spidertron torso's own
132x138 frame and by_pixel(0, -19) shift, Factorio's 8192 px sheet ceiling, and
lint_sprites.py's own two front ends reading our two artifacts.
"""

import json
import pathlib
import shutil
import subprocess

import pytest
from PIL import Image

import lint_sprites as lint
from render import artconfig as ac
from render import factorio_camera as fc
from render import pack
from render import sheets
from render.spritesheet import MAX_SHEET_SIDE, plan_sheet


# ------------------------------------------------------------------------- fixtures


def make_cfg(**overrides):
    """A resolved config with no environment and no model path in play."""
    return ac.resolve(overrides, env={})


def write_frames(directory: pathlib.Path, cfg, boxes, *, canvas=128, pass_name="body",
                 samples=64, alpha=255, sidecar=True):
    """One opaque rectangle per frame, at `boxes[i]` = (x0, y0, x1, y1).

    Returns the directory. A rectangle is the right fixture here: its alpha bounding box
    is exactly the rectangle, so every geometry assertion has a closed-form answer rather
    than a measured one.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for index, box in boxes.items():
        img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
        if box is not None:
            img.paste((200, 80, 80, alpha), box)
        img.save(directory / f"frame_{index:03d}.png")
    if sidecar:
        blob = ac.stamp(cfg, {"pass": pass_name, "samples": samples,
                              "frames": sorted(boxes)})
        (directory / "config.json").write_text(json.dumps(blob, indent=2, sort_keys=True))
    return directory


def ring(count, box):
    """The same rectangle at every frame of a complete `count`-frame ring."""
    return {i: box for i in range(count)}


@pytest.fixture
def packed_tree(tmp_path):
    """A full pack run over synthetic frames: (out_root, manifest_path, packed)."""
    cfg = make_cfg(**{"rotations.count": 8})
    frames = write_frames(tmp_path / "frames", cfg, ring(8, (30, 20, 90, 70)))
    out = tmp_path / "mod"
    item = pack.pack_target(cfg, pack.TARGETS[0], out, mod_name="jamaltron",
                            explicit_dir=frames)
    manifest = out / pack.GRAPHICS_DIR / pack.MANIFEST_NAME
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(pack.manifest_blob(cfg, [item], mod_name="jamaltron")))
    lua = out / pack.PROTOTYPES_DIR / pack.LUA_NAME
    lua.parent.mkdir(parents=True, exist_ok=True)
    lua.write_text(pack.lua_blob(cfg, [item]))
    return out, manifest, lua, [item]


# --------------------------------------------------------------------------- the shift


def test_shift_reproduces_the_stock_torso_declaration():
    """The one fixture that is not ours: Wube's own spidertron torso.

    spidertron-animations.lua declares 132x138 at shift by_pixel(0, -19), which puts the
    entity origin at pixel (65.5, 106.5) of the frame. Place a crop so the origin lands
    exactly there and the packer must hand back that same shift -- otherwise our sheets
    sit somewhere else on the entity than every stock sprite they stand next to.
    """
    canvas = (384, 384)
    # 191.5 - 65.5 and 191.5 - 106.5 are both integers, so the placement is exact and the
    # test is measuring the arithmetic rather than a rounding.
    box = (126, 85, 126 + 132, 85 + 138)
    width, height, shift = pack.sheet_shift(box, canvas, fc.px_per_tile(0.5))
    assert (width, height) == (132, 138)
    assert shift == (0.0, -19.0 / 32.0)
    assert sheets.origin_in_frame(width, height, shift, fc.px_per_tile(0.5)) == (65.5, 106.5)


@pytest.mark.parametrize("box", [(100, 50, 300, 200), (0, 0, 384, 384), (191, 191, 193, 194)])
def test_shift_round_trips_through_origin_in_frame(box):
    """sheets.origin_in_frame() is the compare sheet's reader, written before this module.
    Feeding it our declaration must put the origin back where the crop actually had it."""
    canvas, ppt = (384, 384), 64.0
    width, height, shift = pack.sheet_shift(box, canvas, ppt)
    want = (fc.origin_pixel(canvas[0]) - box[0], fc.origin_pixel(canvas[1]) - box[1])
    assert sheets.origin_in_frame(width, height, shift, ppt) == pytest.approx(want)


def test_shift_is_scale_relative():
    """Halve the px-per-tile and the same crop is the same number of TILES off."""
    box, canvas = (100, 50, 300, 200), (384, 384)
    _, _, at64 = pack.sheet_shift(box, canvas, 64.0)
    _, _, at32 = pack.sheet_shift(box, canvas, 32.0)
    assert at32 == pytest.approx((at64[0] * 2, at64[1] * 2))


# ----------------------------------------------------------------------- the frame box


def test_union_box_is_the_union_not_the_first_frame():
    """A box fitted to frame 0 clips frame 32. This is the bug the union exists to stop."""
    images = [(0, _blob((10, 10, 20, 20))), (1, _blob((40, 30, 60, 50)))]
    box, per_frame = pack.union_box(images)
    assert box == (10, 10, 60, 50)
    assert [b for _, b in per_frame] == [(10, 10, 20, 20), (40, 30, 60, 50)]


def test_the_box_keeps_the_faint_fringe_the_engine_still_draws():
    """THE FIN. An antialiased edge ramp is 1..7 alpha and Factorio composites every bit of
    it, so the box has to contain it. Measuring at 8 -- which is what C.4 shipped -- puts
    the ramp OUTSIDE the box that is supposed to hold the sprite, and the crop shaves it."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    img.paste((200, 80, 80, 255), (20, 20, 30, 30))
    img.paste((200, 80, 80, 3), (30, 24, 36, 26))          # the fin tip's own ramp
    assert pack.union_box([(0, img)])[0] == (20, 20, 36, 30)
    assert pack.union_box([(0, img)], floor=8)[0] == (20, 20, 30, 30)
    assert pack.union_box.__defaults__ == (pack.SPRITE_VISIBLE_ALPHA,)


def test_a_shadow_frame_is_denoised_in_the_pixels_not_by_the_threshold():
    """Cycles scatters alpha 1..7 over the whole shadow plane, so at the visible threshold a
    RAW shadow frame's box is the canvas. The packer does not answer that with a higher
    threshold -- it ZEROES the noise first, and then one threshold governs everything."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 3))
    img.paste((0, 0, 0, 255), (20, 20, 30, 30))
    assert pack.union_box([(0, img)])[0] == (0, 0, 64, 64)
    clean = pack.blacken(img, pack.RENDER_NOISE_FLOOR)
    assert pack.union_box([(0, clean)])[0] == (20, 20, 30, 30)


def test_empty_frames_do_not_move_the_box():
    box, _ = pack.union_box([(0, _blob((10, 10, 20, 20))), (1, Image.new("RGBA", (64, 64)))])
    assert box == (10, 10, 20, 20)


@pytest.mark.parametrize("box,expect", [
    ((0, 10, 20, 20), [0]),
    ((10, 0, 20, 20), [0]),
    ((10, 10, 64, 20), [0]),
    ((10, 10, 20, 64), [0]),
    ((1, 1, 63, 63), []),
])
def test_clipped_frames_flags_every_edge(box, expect):
    _, per_frame = pack.union_box([(0, _blob(box))])
    assert pack.clipped_frames(per_frame, (64, 64)) == expect


def test_pad_is_clamped_to_the_canvas():
    assert pack.pad_box((0, 5, 60, 64), 2, (64, 64)) == (0, 3, 62, 64)


# ------------------------------------------------------------------ the finished cells


def _sheet_of(cells, frame_w, frame_h, line_length):
    """A hand-laid sheet: `cells` is [(x0,y0,x1,y1) or None] per frame, cell-relative."""
    layout = plan_sheet(len(cells), frame_w, frame_h, line_length=line_length)
    sheet = Image.new("RGBA", (line_length * frame_w,
                              layout.lines_in_file(0) * frame_h), (0, 0, 0, 0))
    for index, box in enumerate(cells):
        if box is None:
            continue
        col, row = index % line_length, index // line_length
        sheet.paste((255, 255, 255, 255),
                    (col * frame_w + box[0], row * frame_h + box[1],
                     col * frame_w + box[2], row * frame_h + box[3]))
    return [sheet], layout


def test_cell_margins_measures_every_edge_of_every_cell():
    """The margin is per CELL, so it has to survive the grid: frame 3 sits in another
    column and frame 5 on another row, and a reader of the whole sheet's bbox sees neither."""
    cells = [(5, 5, 15, 15)] * 8
    cells[3] = (1, 4, 19, 16)        # tight on the left, in column 3
    cells[5] = (4, 2, 16, 18)        # tight on the top, in row 1
    sheets_, layout = _sheet_of(cells, 20, 20, 4)
    worst, per_frame = pack.cell_margins(sheets_, layout)
    assert worst["L"] == (1, 3) and worst["T"] == (2, 5)
    assert worst["R"] == (1, 3) and worst["B"] == (2, 5)
    assert per_frame[0] == (0, (5, 5, 5, 5))
    assert len(per_frame) == 8


def test_an_empty_cell_clips_nothing():
    sheets_, layout = _sheet_of([(5, 5, 15, 15), None], 20, 20, 2)
    worst, per_frame = pack.cell_margins(sheets_, layout)
    assert per_frame[1] == (1, None)
    assert pack.tight_frames(per_frame, 1) == []
    assert worst["L"] == (5, 0)


def test_tight_frames_names_the_frames_that_lost_their_margin():
    sheets_, layout = _sheet_of([(1, 1, 19, 19), (0, 5, 15, 15)], 20, 20, 2)
    _, per_frame = pack.cell_margins(sheets_, layout)
    assert [i for i, _ in pack.tight_frames(per_frame, 1)] == [1]
    assert [i for i, _ in pack.tight_frames(per_frame, 2)] == [0, 1]
    # pad 0 makes the check vacuous, which is the honest reason DEFAULT_PAD is 1
    assert pack.tight_frames(per_frame, 0) == []


def test_a_faint_cell_edge_pixel_is_measured_like_any_other():
    """Measured at the visible threshold, so the gate cannot be fooled by the same faint
    alpha that fooled the box. The 3 here is the fin tip's own ramp."""
    sheets_, layout = _sheet_of([(5, 5, 15, 15)], 20, 20, 1)
    sheets_[0].putpixel((0, 10), (255, 255, 255, 3))
    worst, per_frame = pack.cell_margins(sheets_, layout)
    assert worst["L"] == (0, 0)
    assert [i for i, _ in pack.tight_frames(per_frame, 1)] == [0]


def _blob(box, canvas=64):
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    img.paste((255, 255, 255, 255), box)
    return img


# ------------------------------------------------------------------- the line length


@pytest.mark.parametrize("count,requested,columns,expect", [
    (64, 8, 100, 8),      # stock's own torso layout, and it divides
    (8, 8, 100, 8),
    (10, 8, 100, 5),      # 8 would leave 6 blank cells for --strict to call unused-frames
    (13, 8, 100, 1),      # prime: one column, ugly and correct
    (64, 8, 3, 2),        # a narrow sheet caps the columns before the request does
    (64, 100, 100, 64),
])
def test_choose_line_length(count, requested, columns, expect):
    chosen, note = pack.choose_line_length(count, requested, columns)
    assert chosen == expect
    assert bool(note) == (chosen != requested)


@pytest.mark.parametrize("count", range(1, 65))
def test_chosen_line_length_never_leaves_an_unused_frame(count):
    """The property --strict actually checks, run over every count we could ship.

    lint_sprites' unused-frames warning is (sheet_w // frame_w) * (sheet_h // frame_h)
    against the declared frames. Reproduce that arithmetic off the layout and it must come
    out equal, or a shipped sheet fails its own gate.
    """
    columns, _ = pack.choose_line_length(count, pack.DEFAULT_LINE_LENGTH, 1000)
    layout = plan_sheet(count, 40, 30, line_length=columns)
    width, height = layout.sheet_size(layout.file_count - 1)
    available = sum((layout.sheet_size(i)[0] // 40) * (layout.sheet_size(i)[1] // 30)
                    for i in range(layout.file_count))
    assert available == count
    assert width % 40 == 0 and height % 30 == 0      # never a ragged sheet either


def test_line_length_refuses_a_frame_too_wide_for_the_sheet():
    with pytest.raises(pack.PackError, match="no legal line_length"):
        pack.choose_line_length(8, 8, 0)


# -------------------------------------------------------------------- the sprite dict


def test_the_three_kinds_spell_the_count_differently():
    """Factorio multiplies direction_count x frame_count x variation_count, all defaulting
    to 1. 64 rotations, a 64-frame flop loop and 64 variations are the same 64 cells and
    three different declarations -- and each kind writes ONLY the field its own struct
    owns, because `direction_count` on a SpriteVariations is a field that does not exist.
    """
    layout = plan_sheet(64, 40, 30, line_length=8)
    rot = pack.sprite_fields(pack.TARGETS[0], ["a.png"], layout, (0.0, 0.0), 0.5)
    kinds = {k: pack.sprite_fields(
        pack.Target(id=k, slot="animation", order=0, pass_name="body", stem="f", kind=k),
        ["a.png"], layout, (0.0, 0.0), 0.5) for k in ("animation", "variations")}
    assert (rot["direction_count"], rot["frame_count"]) == (64, 1)
    assert kinds["animation"]["frame_count"] == 64
    assert "direction_count" not in kinds["animation"]
    assert kinds["variations"]["variation_count"] == 64
    assert not {"direction_count", "frame_count"} & set(kinds["variations"])


def test_an_unknown_kind_is_fatal():
    layout = plan_sheet(8, 40, 30, line_length=8)
    bogus = pack.Target(id="x", slot="animation", order=0, pass_name="body", stem="f",
                        kind="frames")
    with pytest.raises(pack.PackError, match="unknown kind"):
        pack.sprite_fields(bogus, ["a.png"], layout, (0.0, 0.0), 0.5)


def test_line_length_is_always_emitted():
    """Without it the engine's default depends on the prototype field being loaded and the
    linter can only check a frame budget. Every target, every count."""
    for count in (1, 8, 64):
        layout = plan_sheet(count, 40, 30,
                            line_length=pack.choose_line_length(count, 8, 1000)[0])
        for target in pack.TARGETS:
            fields = pack.sprite_fields(target, ["a.png"], layout, (0.0, 0.0), 0.5)
            assert "line_length" in fields


def test_multi_file_emits_filenames_and_lines_per_file():
    layout = plan_sheet(64, 400, 400, max_side=1700, line_length=4)
    assert layout.file_count > 1
    fields = pack.sprite_fields(pack.TARGETS[0], [f"s{i}.png" for i in range(layout.file_count)],
                                layout, (0.0, 0.0), 0.5)
    assert "filename" not in fields
    assert fields["filenames"] and fields["lines_per_file"] == layout.lines_per_file


def test_flags_ride_on_the_target_not_the_geometry():
    layout = plan_sheet(8, 40, 30, line_length=8)
    shadow = pack.sprite_fields(pack.TARGETS[2], ["a.png"], layout, (0.0, 0.0), 0.5)
    body = pack.sprite_fields(pack.TARGETS[0], ["a.png"], layout, (0.0, 0.0), 0.5)
    assert shadow["draw_as_shadow"] is True
    assert "draw_as_shadow" not in body
    assert "apply_runtime_tint" not in body


def test_field_order_is_stable():
    layout = plan_sheet(8, 40, 30, line_length=8)
    fields = pack.sprite_fields(pack.TARGETS[0], ["a.png"], layout, (0.0, 0.0), 0.5)
    assert list(fields) == [k for k in pack.FIELD_ORDER if k in fields]


# ------------------------------------------------------------------------- the targets


def test_target_ids_are_unique_and_every_slot_has_a_wrap():
    ids = [t.id for t in pack.TARGETS]
    assert len(ids) == len(set(ids))
    for target in pack.TARGETS:
        assert target.slot in pack.SLOT_WRAP, f"{target.slot} has no wrap"
        assert target.slot in pack.STOCK_ART_SLOTS, f"{target.slot} is not a stock slot"
        assert target.kind in pack.COUNT_FIELD
        assert target.reduce is None or target.reduce in pack.REDUCERS


def test_clear_names_every_stock_slot_no_sheet_covers():
    """entity.lua deepcopies the spidertron. A slot we neither fill nor clear keeps
    drawing Wube's art under ours -- which is the whole base_animation question."""
    slots = {"animation": ["body"], "shadow_animation": ["shadow"]}
    assert pack.clear_list(slots) == ["base_animation", "shadow_base_animation",
                                      "water_reflection"]
    assert pack.clear_list({s: [] for s in pack.STOCK_ART_SLOTS}) == []


def test_a_target_whose_pass_does_not_exist_yet_is_skipped_not_fatal(tmp_path, capsys):
    """A row may name a render pass nobody has written -- C.5's flop clip is the next one.
    The row documents the slot; the run says so out loud instead of failing or going quiet.
    """
    cfg = make_cfg()
    future = pack.Target(id="flop", slot="animation", order=9, pass_name="flop",
                         stem="jamaltron-flop", kind="animation")
    assert pack.frames_dir(cfg, future) is None
    assert pack.pack_target(cfg, future, tmp_path, mod_name="jamaltron") is None
    assert "does not exist yet" in capsys.readouterr().out


def test_every_shipped_target_names_a_pass_that_exists():
    """The other half. body_mask named a pass that did not exist for as long as C.4 took
    to write it, which is fine while it is a TODO and a silently empty tint layer once the
    sheets ship."""
    for target in pack.TARGETS:
        assert target.pass_name in ac.PASSES, target.id


# ------------------------------------------------------------------------ frame checks


def test_a_part_rendered_directory_is_refused(tmp_path):
    """48 of 64 frames looks identical to a finished render on disk, and packs into a
    sheet whose rotations are silently wrong."""
    cfg = make_cfg()
    frames = write_frames(tmp_path / "f", cfg, {i: (10, 10, 20, 20) for i in range(48)})
    with pytest.raises(pack.PackError, match="not a complete set"):
        pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                         explicit_dir=frames)


def test_an_evenly_spaced_subset_is_accepted(tmp_path):
    """art.py --preview renders 0, 8, 16 ... 56. Packed at direction_count 8 that is a
    coarse but CORRECT sheet."""
    cfg = make_cfg()
    frames = write_frames(tmp_path / "f", cfg, {i: (10, 10, 20, 20) for i in range(0, 64, 8)})
    item = pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                            explicit_dir=frames)
    assert item.fields["direction_count"] == 8


def test_stale_frames_are_refused(tmp_path):
    """The sidecar pins which knobs made these pixels. Moving the shark and packing the
    old frames is the failure this whole harness exists to prevent."""
    cfg = make_cfg(**{"rotations.count": 8})
    frames = write_frames(tmp_path / "f", cfg, ring(8, (10, 10, 20, 20)))
    moved = make_cfg(**{"rotations.count": 8, "model.scale": 0.9})
    with pytest.raises(pack.PackError, match="different pixels"):
        pack.pack_target(moved, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                         explicit_dir=frames)
    assert pack.pack_target(moved, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                            explicit_dir=frames, any_config=True) is not None


def test_a_missing_model_says_so_instead_of_blaming_a_knob(tmp_path):
    """model.blend is hashed by CONTENT, so "the model is not on this machine" and "a knob
    moved" produce the same mismatch and want completely different fixes. The frames here
    were written with the model present and are packed with it gone."""
    present = tmp_path / "HAMMERHEAD.blend"
    present.write_bytes(b"SHARK")
    cfg = make_cfg(**{"rotations.count": 8, "model.blend": str(present)})
    frames = write_frames(tmp_path / "f", cfg, ring(8, (10, 10, 20, 20)))
    gone = make_cfg(**{"rotations.count": 8, "model.blend": str(tmp_path / "nope.blend")})
    with pytest.raises(pack.PackError, match="The model is not where this config points"):
        pack.pack_target(gone, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                         explicit_dir=frames)


def test_clipped_frames_are_fatal_unless_allowed(tmp_path):
    cfg = make_cfg(**{"rotations.count": 8})
    frames = write_frames(tmp_path / "f", cfg, ring(8, (0, 10, 40, 50)))
    with pytest.raises(pack.PackError, match="touch the canvas edge"):
        pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                         explicit_dir=frames)
    item = pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out2", mod_name="jamaltron",
                            explicit_dir=frames, allow_clipped=True)
    assert any("CLIPPED" in n for n in item.notes)


def write_finned_frames(directory: pathlib.Path, cfg, body, fin, *, canvas=64, count=4):
    """An opaque body plus a FAINT alpha-3 fringe: the tail fin's antialiasing ramp.

    Alpha 3 is the whole fixture. Factorio composites it, so it is part of the sprite; the
    old alpha >= 8 reading could not see it at all, which is how C.4's sheets passed their
    own gate with the fin sliced off at the frame edge.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
        img.paste((200, 80, 80, 255), body)
        img.paste((200, 80, 80, 3), fin)
        img.save(directory / f"frame_{index:03d}.png")
    (directory / "config.json").write_text(json.dumps(ac.stamp(cfg, {"pass": "body"})))
    return directory


def test_a_faint_fringe_at_the_canvas_edge_is_refused(tmp_path):
    """THE REGRESSION TEST. The render ran out of canvas for pixels the engine still draws.

    At the old alpha >= 8 reading this frame is 12 px clear of the edge and packs without a
    word -- asserted below, because that is the failure being fixed, not a hypothetical.
    """
    cfg = make_cfg(**{"rotations.count": 4})
    frames = write_finned_frames(tmp_path / "f", cfg, (12, 20, 52, 44), (0, 30, 12, 34))

    images = [(i, Image.open(frames / f"frame_{i:03d}.png").convert("RGBA"))
              for i in range(4)]
    _, at_the_old_floor = pack.union_box(images, floor=pack.RENDER_NOISE_FLOOR)
    assert pack.clipped_frames(at_the_old_floor, (64, 64)) == [], \
        "the fixture has to be one the OLD gate waved through, or it proves nothing"

    with pytest.raises(pack.PackError, match="touch the canvas edge at alpha >= 1"):
        pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                         explicit_dir=frames)
    assert not list((tmp_path / "out" / pack.GRAPHICS_DIR).glob("*.png")), \
        "a refused pack must not leave a clipped sheet on disk"


def test_a_faint_fringe_inside_the_canvas_is_kept_by_the_frame_box(tmp_path):
    """C.4's actual defect: the CANVAS had 12 px to spare, so the canvas check had nothing
    to say, and the fin was cut by the FRAME BOX instead. The box has to hold the ramp."""
    cfg = make_cfg(**{"rotations.count": 4})
    frames = write_finned_frames(tmp_path / "f", cfg, (12, 20, 52, 44), (52, 30, 58, 34))
    item = pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                            explicit_dir=frames)
    assert item.box == (11, 19, 59, 45)          # union at alpha >= 1, plus the 1 px pad
    assert (item.fields["width"], item.fields["height"]) == (48, 26)
    images = [(i, Image.open(frames / f"frame_{i:03d}.png").convert("RGBA"))
              for i in range(4)]
    shaved = pack.union_box(images, floor=pack.RENDER_NOISE_FLOOR)[0]
    assert shaved[2] - shaved[0] == 40, "the old reading was 6 px narrower: the fin tip"
    assert {edge: px for edge, (px, _) in item.margins.items()} == {"L": 1, "T": 1,
                                                                   "R": 1, "B": 1}


def test_the_finished_cells_are_checked_even_when_the_box_is_wrong(tmp_path, monkeypatch):
    """THE GATE THAT WAS MISSING, and the one thing it must not lean on is the box being
    right -- a gate that shares its input with the thing it guards is how a clipped sheet
    passed. Derive the box the way C.4 did, at the noise floor, and the refusal still comes,
    because it is measured off the cells that were about to be written.
    """
    cfg = make_cfg(**{"rotations.count": 4})
    frames = write_finned_frames(tmp_path / "f", cfg, (12, 20, 52, 44), (52, 30, 58, 34))
    honest = pack.union_box
    monkeypatch.setattr(pack, "union_box",
                        lambda images, floor=None: honest(images, pack.RENDER_NOISE_FLOOR))

    with pytest.raises(pack.PackError, match="closer than the 1 px"):
        pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                         explicit_dir=frames)
    assert not list((tmp_path / "out" / pack.GRAPHICS_DIR).glob("*.png"))

    item = pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out2", mod_name="jamaltron",
                            explicit_dir=frames, allow_clipped=True)
    assert any("CLIPPED BY THE BOX" in note for note in item.notes)
    assert item.margins["R"][0] == 0


def test_every_pack_reports_its_tightest_margin(tmp_path):
    """The measurement goes in the notes on every run, clipped or not. Finding the sliced
    fin took opening the shipped PNG in a script; the tool should just hand you the number."""
    cfg = make_cfg(**{"rotations.count": 4})
    frames = write_frames(tmp_path / "f", cfg, ring(4, (20, 18, 44, 40)))
    item = pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                            explicit_dir=frames)
    assert any("tightest margin inside the 26x24 cell at alpha >= 1" in note
               for note in item.notes)


def test_mismatched_canvases_are_refused(tmp_path):
    cfg = make_cfg(**{"rotations.count": 2})
    frames = tmp_path / "f"
    write_frames(frames, cfg, {0: (10, 10, 20, 20)}, canvas=64, sidecar=True)
    write_frames(frames, cfg, {1: (10, 10, 20, 20)}, canvas=96, sidecar=False)
    with pytest.raises(pack.PackError, match="one sheet needs one canvas"):
        pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                         explicit_dir=frames)


# ---------------------------------------------------------------------- sheet building


def test_every_frame_lands_in_its_own_cell(tmp_path):
    """Frame k must be at column k % line_length, row k // line_length. A marker pixel per
    frame is the only way to catch a sheet that is correct in aggregate and shuffled."""
    cfg = make_cfg(**{"rotations.count": 8})
    frames = tmp_path / "f"
    frames.mkdir()
    for i in range(8):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        img.paste((255, 255, 255, 255), (20, 20, 40, 40))
        img.putpixel((22 + i, 22), (255, 0, 0, 255))      # a per-frame fingerprint
        img.save(frames / f"frame_{i:03d}.png")
    (frames / "config.json").write_text(json.dumps(ac.stamp(cfg, {"pass": "body"})))

    item = pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                            explicit_dir=frames, line_length=4, pad=0)
    sheet = Image.open(item.paths[0]).convert("RGBA")
    assert sheet.size == (4 * item.fields["width"], 2 * item.fields["height"])
    for i in range(8):
        cell = sheet.crop(sheets.frame_box(i, item.fields["width"], item.fields["height"], 4))
        assert cell.getpixel((2 + i, 2)) == (255, 0, 0, 255), f"frame {i} is in the wrong cell"


def test_the_declared_shift_puts_the_packed_frame_back_where_it_was(tmp_path):
    """END TO END, and the strongest claim this module makes: read the manifest's own
    width/height/shift/scale, place the packed frame on the render canvas, and the pixels
    land byte-identically on the render they came from. Nothing else in the pipeline gets
    to have an opinion about where the sprite sits."""
    from PIL import ImageChops
    cfg = make_cfg(**{"rotations.count": 4})
    boxes = {0: (20, 18, 44, 40), 1: (18, 22, 40, 44), 2: (24, 20, 46, 42),
             3: (22, 24, 42, 46)}
    frames = write_frames(tmp_path / "f", cfg, boxes)
    item = pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                            explicit_dir=frames)
    fields = item.fields
    ppt = fc.NOMINAL_PX_PER_TILE / fields["scale"]
    origin = sheets.origin_in_frame(fields["width"], fields["height"], fields["shift"], ppt)
    sheet = Image.open(item.paths[0]).convert("RGBA")
    for i in range(4):
        cell = sheet.crop(sheets.frame_box(i, fields["width"], fields["height"],
                                           fields["line_length"]))
        back = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
        back.paste(cell, (round(fc.origin_pixel(128) - origin[0]),
                          round(fc.origin_pixel(128) - origin[1])))
        original = Image.open(frames / f"frame_{i:03d}.png").convert("RGBA")
        assert ImageChops.difference(original, back).getbbox() is None


def test_shadow_frames_are_blackened_and_denoised(tmp_path):
    cfg = make_cfg(**{"rotations.count": 4})
    frames = tmp_path / "f"
    frames.mkdir()
    for i in range(4):
        img = Image.new("RGBA", (64, 64), (9, 9, 9, 3))     # Cycles noise over the plane
        img.paste((40, 30, 20, 255), (20, 20, 40, 40))      # the shadow itself
        img.save(frames / f"frame_{i:03d}.png")
    (frames / "config.json").write_text(json.dumps(ac.stamp(cfg, {"pass": "shadow"})))
    item = pack.pack_target(cfg, pack.TARGETS[2], tmp_path / "out", mod_name="jamaltron",
                            explicit_dir=frames)
    sheet = Image.open(item.paths[0]).convert("RGBA")
    colours = {px[:3] for _, px in sheet.getcolors(1 << 24) if px[3]}
    assert colours == {(0, 0, 0)}, "draw_as_shadow reads alpha only; RGB must be black"
    assert item.fields["width"] == 22 and item.fields["height"] == 22   # 20x20 + 1px pad
    assert any("shadow surgery" in n for n in item.notes)


def test_a_sheet_over_the_ceiling_splits_into_files(tmp_path):
    cfg = make_cfg(**{"rotations.count": 8})
    frames = write_frames(tmp_path / "f", cfg, ring(8, (4, 4, 60, 60)), canvas=64)
    item = pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "out", mod_name="jamaltron",
                            explicit_dir=frames, line_length=4, max_side=180)
    assert len(item.paths) == item.layout.file_count > 1
    assert item.fields["lines_per_file"] == item.layout.lines_per_file
    for index, path in enumerate(item.paths):
        assert Image.open(path).size == item.layout.sheet_size(index)
    assert max(max(Image.open(p).size) for p in item.paths) <= 180


# ------------------------------------------------------------- the two artifacts agree


def test_manifest_entry_is_the_lua_table_plus_an_id(packed_tree):
    out, manifest, _, packed = packed_tree
    blob = json.loads(manifest.read_text())
    entry = blob["sprites"][0]
    assert set(entry) - set(packed[0].fields) == {"id"}
    assert {k: entry[k] for k in packed[0].fields} == packed[0].fields


def test_the_lua_and_the_manifest_read_identically(packed_tree):
    """THE anti-drift test. lint_sprites has two independent front ends -- a JSON reader
    and a Lua table reader -- and pointing both at our two artifacts must produce the same
    normalised declaration, field for field. Two serializers of one dict cannot drift; this
    is what proves they are still two serializers of one dict."""
    out, manifest, lua, _ = packed_tree
    from_json = lint.specs_from_manifest(manifest, lint.ModPaths())
    from_lua = lint.specs_from_lua(lua)
    assert len(from_json) == len(from_lua) == 1
    for left, right in zip(from_json, from_lua):
        for attr in ("filenames", "width", "height", "x", "y", "line_length",
                     "direction_count", "frame_count", "variation_count",
                     "lines_per_file", "unmodelled", "bad_fields"):
            assert getattr(left, attr) == getattr(right, attr), attr


def test_the_generated_lua_declares_nothing_the_gate_cannot_model(packed_tree):
    _, _, lua, _ = packed_tree
    for spec in lint.specs_from_lua(lua):
        assert not spec.unmodelled and not spec.bad_fields


def test_the_manifest_passes_the_strict_gate(packed_tree):
    """The CI invocation, run here: `--strict --mod-root jamaltron=<root>`."""
    out, manifest, _, _ = packed_tree
    ok, text = pack.verify(manifest, out, strict=True)
    assert ok, text


def test_a_corrupted_number_fails_the_strict_gate(packed_tree):
    """Deliberate corruption, because a gate nobody has watched fail is not a gate.

    A wrong width is the failure mode with no other symptom: Factorio loads it, slices the
    shark across two cells and says nothing, and the linter's message is Factorio's own
    crash wording so grepping either one lands in the same place."""
    out, manifest, _, _ = packed_tree
    blob = json.loads(manifest.read_text())
    blob["sprites"][0]["width"] += 1
    manifest.write_text(json.dumps(blob))
    ok, text = pack.verify(manifest, out, strict=True)
    assert not ok
    assert "sheet-too-small" in text and "outside the actual sprite size" in text


def test_a_wrong_line_length_cannot_hide(packed_tree):
    """Changing the column count changes the row count too, so it never merely fits."""
    out, manifest, _, _ = packed_tree
    blob = json.loads(manifest.read_text())
    blob["sprites"][0]["line_length"] = 4
    manifest.write_text(json.dumps(blob))
    ok, text = pack.verify(manifest, out, strict=True)
    assert not ok and "sheet-too-small" in text


def test_the_manifest_resolves_its_own_mod_root(packed_tree):
    """`mod_roots` is relative to the manifest, so the tree lints with no flags at all --
    which is what makes the gitignored dry-run tree worth having."""
    out, manifest, _, _ = packed_tree
    findings, declarations, _ = lint.lint([manifest], lint.ModPaths(), strict=True)
    assert declarations == 1 and not findings


def test_the_manifest_is_what_ci_classifies_as_ours():
    """ci.yml recognises a manifest by CONTENT, not filename: a dict with a `sprites`
    list. Rename the output and the gate must still bite."""
    blob = pack.manifest_blob(make_cfg(), [], mod_name="jamaltron")
    assert isinstance(blob, dict) and isinstance(blob.get("sprites"), list)


# ------------------------------------------------------------------------ the Lua side


@pytest.mark.parametrize("value,expect", [
    (True, "true"), (False, "false"), (3, "3"), (0.5, "0.5"), (-0.59375, "-0.59375"),
    (2.0, "2"), ("a\"b", '"a\\"b"'), ([0.0, -0.59375], "{0, -0.59375}"),
])
def test_lua_value_forms(value, expect):
    assert pack.lua_value(value, "") == expect


def test_lua_refuses_a_value_it_cannot_spell():
    with pytest.raises(pack.PackError):
        pack.lua_value({"a": 1}, "")


def test_generated_lua_fits_the_repo_luacheck_line_limit(packed_tree):
    """.luacheckrc sets max_line_length = 120. Generated code is still code CI lints."""
    _, _, lua, _ = packed_tree
    long_lines = [line for line in lua.read_text().splitlines() if len(line) > 120]
    assert not long_lines, long_lines


def test_generated_lua_wraps_each_slot_the_way_stock_does(packed_tree):
    """`animation` is a layer stack, `shadow_animation` is a bare sprite. Getting that
    backwards is a data-stage error with a useless message."""
    cfg = make_cfg(**{"rotations.count": 8})
    _, _, _, packed = packed_tree
    shadow = pack.Packed(target=pack.TARGETS[2], fields=packed[0].fields,
                         frames=packed[0].frames, paths=packed[0].paths,
                         box=packed[0].box, layout=packed[0].layout)
    text = pack.lua_blob(cfg, [packed[0], shadow])
    assert "animation = {layers = {sprites.body}}," in text
    assert "shadow_animation = sprites.shadow," in text
    assert 'config_hash = "%s",' % ac.config_hash(cfg) in text


def test_a_bare_slot_refuses_two_layers():
    cfg = make_cfg()
    layout = plan_sheet(8, 40, 30, line_length=8)
    fields = pack.sprite_fields(pack.TARGETS[2], ["a.png"], layout, (0.0, 0.0), 0.5)
    two = [pack.Packed(target=pack.TARGETS[2], fields=fields, frames=list(range(8)),
                       paths=[], box=(0, 0, 1, 1), layout=layout),
           pack.Packed(target=pack.Target(id="other", slot="shadow_animation", order=1,
                                          pass_name="shadow", stem="s"),
                       fields=fields, frames=list(range(8)), paths=[], box=(0, 0, 1, 1),
                       layout=layout)]
    with pytest.raises(pack.PackError, match="takes one sprite"):
        pack.lua_blob(cfg, two)


@pytest.mark.skipif(shutil.which("lua") is None, reason="no lua interpreter on PATH")
def test_generated_lua_loads_and_shares_its_tables(packed_tree):
    """Run it in a real interpreter. `sprites.body` and `slots.animation.layers[1]` must be
    the SAME table, not two copies -- one dict in Python, one table in Lua, all the way to
    the data stage. Skipped where lua is not installed (CI); locally it is the only check
    that the emitted file is more than plausible-looking text."""
    _, _, lua, _ = packed_tree
    script = """
    local g = dofile("%s")
    assert(g.slots.animation.layers[1] == g.sprites.body, "layer is a copy, not the table")
    assert(g.sprites.body.line_length == 8)
    assert(#g.clear == %d, "clear list length")
    print(g.config_hash)
    """ % (lua, len(pack.clear_list({"animation": ["body"]})))
    out = subprocess.run([shutil.which("lua"), "-e", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == ac.config_hash(make_cfg(**{"rotations.count": 8}))


# ------------------------------------------------------------------------------ crush


def test_crush_says_so_when_no_optimizer_is_installed(tmp_path, monkeypatch):
    """The branch a fresh clone and CI both hit. Silence here would read as "crushed"."""
    monkeypatch.setattr(pack.shutil, "which", lambda name: None)
    lines = pack.crush([tmp_path / "x.png"])
    assert len(lines) == 1 and "SKIPPED" in lines[0] and "oxipng" in lines[0]


def test_crush_is_reverted_when_the_optimizer_is_not_lossless(tmp_path):
    """A "lossless" optimizer is a claim. This pipeline has no in-game validation to catch
    a broken one, so the bytes are compared and a changed pixel loses."""
    path = tmp_path / "sheet.png"
    Image.new("RGBA", (16, 16), (200, 30, 30, 255)).save(path)
    before = path.read_bytes()
    liar = tmp_path / "liar.sh"
    liar.write_text("#!/bin/sh\npython3 -c \"from PIL import Image; "
                    "p='$4'; i=Image.open(p); i.putpixel((0,0),(0,0,0,255)); i.save(p)\"\n")
    liar.chmod(0o755)
    lines = pack.crush([path], tool=str(liar))
    assert "REVERTED" in lines[0]
    assert path.read_bytes() == before


def test_sheet_size_ceiling_is_the_measured_one():
    """8192 is not folklore: no PNG in core/base/space-age/quality/elevated-rails exceeds
    it across 8965 files, and Factorio loads a sheet as one GPU texture."""
    assert MAX_SHEET_SIDE == 8192
    assert pack.build_parser().parse_args([]).max_side == MAX_SHEET_SIDE


# ---------------------------------------------------------------------- the reducers


def _reflection_target():
    return next(t for t in pack.TARGETS if t.reduce == "reflection")


def test_the_reflection_reduces_a_whole_ring_to_one_variation(tmp_path):
    """64 rotations in, ONE blob out, declared as a variation and not as 64 directions.

    The count field is the whole point: stock's water_reflection is variation_count 1 and
    a sheet that declared direction_count 64 over a single cell is a sprite the engine
    slices into 64 slivers.
    """
    cfg = make_cfg(**{"rotations.count": 8})
    frames = write_frames(tmp_path / "f", cfg, ring(8, (40, 40, 88, 80)), canvas=128)
    item = pack.pack_target(cfg, _reflection_target(), tmp_path / "mod",
                            mod_name="jamaltron", explicit_dir=frames)
    assert item.frames == [0]
    assert item.fields["variation_count"] == 1
    assert "direction_count" not in item.fields and "frame_count" not in item.fields
    assert item.layout.frame_count == 1 and item.layout.file_count == 1
    assert any("mean alpha of 8 rotations" in n for n in item.notes)


def test_the_reflection_grows_its_canvas_so_the_blur_cannot_clip(tmp_path):
    """A blur pushes alpha outward. Run it in place on a body that already fills the
    canvas and the packer's own clipped-frames check correctly refuses the result -- and
    the fix for THAT must not be loosening the check, which is what guards the real thing.
    """
    cfg = make_cfg(**{"rotations.count": 4, "reflection.blur_tiles": 0.3})
    # a rectangle running right up to the canvas edge: clipped as a body, fine as a blob
    frames = write_frames(tmp_path / "f", cfg, ring(4, (0, 0, 128, 128)), canvas=128)
    item = pack.pack_target(cfg, _reflection_target(), tmp_path / "mod",
                            mod_name="jamaltron", explicit_dir=frames)
    assert item.fields["width"] > 128 and item.fields["height"] > 128
    with pytest.raises(pack.PackError, match="touch the canvas edge"):
        pack.pack_target(cfg, pack.TARGETS[0], tmp_path / "mod2", mod_name="jamaltron",
                         explicit_dir=frames)


def test_recentring_puts_the_blob_on_the_entity_origin():
    """model.offset lifts the shark, so his mean alpha sits HIGH in an origin-centred
    canvas. Stock declares the spidertron's reflection at shift 0; recentring is what lets
    ours be declared the same way instead of writing the body's lift down twice."""
    lifted = Image.new("L", (129, 129), 0)
    lifted.paste(255, (40, 10, 88, 40))          # rows 10..39, centroid 24.5, origin 64.0
    moved, (dx, dy) = pack.recentre_on_origin(lifted, 8)
    assert (dx, dy) == (0, 40)
    # getbbox's upper bound is exclusive, so the last opaque ROW is box[3] - 1. Half a
    # pixel is the floor here: the offset is an integer and the centroid is not.
    box = moved.point(lambda v: 255 if v >= 8 else 0).getbbox()
    assert abs((box[1] + box[3] - 1) / 2 - fc.origin_pixel(129)) <= 0.5


def test_recentring_refuses_an_empty_blob():
    with pytest.raises(pack.PackError, match="below the alpha floor"):
        pack.recentre_on_origin(Image.new("L", (32, 32), 0), 8)


def test_an_unknown_reducer_is_fatal(tmp_path):
    cfg = make_cfg(**{"rotations.count": 4})
    frames = write_frames(tmp_path / "f", cfg, ring(4, (40, 40, 88, 80)), canvas=128)
    bogus = pack.Target(id="x", slot="water_reflection", order=0, pass_name="body",
                        stem="x", kind="variations", reduce="smoosh")
    with pytest.raises(pack.PackError, match="no reducer named"):
        pack.pack_target(cfg, bogus, tmp_path / "mod", mod_name="jamaltron",
                         explicit_dir=frames)


def test_the_reflection_is_pure_red_with_the_shape_in_the_alpha(tmp_path):
    """MEASURED off stock: every non-transparent pixel of spidertron-body-water-reflection
    .png is exactly (255, 0, 0). The engine reads the alpha; the colour is a convention,
    and a blob that carried the shark's own grey would be a different convention."""
    cfg = make_cfg(**{"rotations.count": 4})
    frames = write_frames(tmp_path / "f", cfg, ring(4, (40, 40, 88, 80)), canvas=128)
    item = pack.pack_target(cfg, _reflection_target(), tmp_path / "mod",
                            mod_name="jamaltron", explicit_dir=frames)
    sheet = Image.open(item.paths[0]).convert("RGBA")
    colours = {p[:3] for p in sheet.get_flattened_data() if p[3] > 0}
    assert colours == {(255, 0, 0)}, colours


def test_water_reflection_wraps_one_sprite_under_pictures_not_a_list():
    """`pictures` is SpriteVariations, and only its single-sheet form may carry
    variation_count. Wrapping ours in a list declares an array of Sprites instead, and a
    Sprite has no variation_count for the engine to read."""
    cfg = make_cfg(**{"rotations.count": 8})
    layout = plan_sheet(1, 40, 30, line_length=1)
    target = _reflection_target()
    fields = pack.sprite_fields(target, ["r.png"], layout, (0.0, 0.0), 0.5)
    text = pack.lua_blob(cfg, [pack.Packed(target=target, fields=fields, frames=[0],
                                           paths=[], box=(0, 0, 1, 1), layout=layout)])
    assert "water_reflection = {pictures = sprites.reflection}," in text
    assert "{pictures = {sprites" not in text


# ------------------------------------------------------------- the sheets we committed


def committed_sprites():
    """The promoted manifest's entries, or [] when nothing has been promoted yet."""
    manifest = pack.REPO / pack.PROMOTE_OUT / pack.GRAPHICS_DIR / pack.MANIFEST_NAME
    if not manifest.is_file():
        return []
    blob = json.loads(manifest.read_text())
    return [(entry["id"], manifest.parent, entry) for entry in blob["sprites"]]


@pytest.mark.parametrize("sprite_id,graphics,entry", committed_sprites(),
                         ids=[row[0] for row in committed_sprites()])
def test_the_committed_sheets_keep_a_transparent_margin(sprite_id, graphics, entry):
    """THE SHIPPED ARTIFACT, measured. Every frame of every sheet in the repo, alpha > 0,
    against its own cell -- which is the hand measurement that found the sliced tail fin.

    This runs where the other sprite gate cannot: tools/lint_sprites.py is stdlib-only and
    reads sizes out of the 24-byte IHDR, so it can check that a sheet is the size the
    prototype claims and never that the sprite inside it is whole. Here there is Pillow and
    the sheets are committed, so CI gets to look at the alpha of what actually ships.
    """
    sheet = Image.open(graphics / entry["filename"].split("/")[-1]).convert("RGBA")
    alpha = sheet.getchannel("A")
    width, height, line_length = entry["width"], entry["height"], entry["line_length"]
    count = (entry.get("direction_count") or entry.get("variation_count")
             or entry.get("frame_count") or 1)
    worst = {}
    for index in range(count):
        box = alpha.crop(sheets.frame_box(index, width, height, line_length)).getbbox()
        if box is None:
            continue
        for edge, value in zip(pack.EDGES, (box[0], box[1], width - box[2],
                                            height - box[3])):
            if edge not in worst or value < worst[edge][0]:
                worst[edge] = (value, index, box)
    assert worst, f"{sprite_id}: every one of {count} cells is empty"
    tightest = min(worst.items(), key=lambda kv: kv[1][0])
    assert tightest[1][0] >= pack.DEFAULT_PAD, (
        f"{sprite_id} is CLIPPED on the {tightest[0]} edge of frame {tightest[1][1]} "
        f"(bbox {tightest[1][2]} in a {width}x{height} cell): re-pack it")


def test_the_generated_lua_is_what_ci_classifies_as_ours(packed_tree):
    """C.16: ci.yml recognises the generated Lua by CONTENT too -- `generated_lua()` there
    requires literal substrings of the banner lua_blob writes. The JSON half of that contract
    is pinned above; this is the Lua half, and it is the file the GAME reads. Change the banner
    and CI silently stops treating the module as ours (it falls out of the gate), so read
    ci.yml's own literals rather than a copy of them, and check both the fresh pack and the
    committed module. A ci.yml this regex can no longer find the classifier in is a failure
    too: that is the tripwire."""
    import re
    ci = (pathlib.Path(__file__).resolve().parents[2] / ".github/workflows/ci.yml").read_text()
    body = re.search(r"def generated_lua\(path\):(.*?)\n\s*\n", ci, re.S)
    assert body, "ci.yml has no generated_lua() classifier any more -- re-pin this test"
    literals = re.findall(r'"([^"]+)" in text', body.group(1))
    assert any("GENERATED" in lit for lit in literals), literals
    _, _, lua, _ = packed_tree
    committed = (pathlib.Path(__file__).resolve().parents[2]
                 / "mod/jamaltron/prototypes/sprites_generated.lua")
    for text in (lua.read_text(), committed.read_text()):
        for lit in literals:
            assert lit in text, (lit, text[:120])
