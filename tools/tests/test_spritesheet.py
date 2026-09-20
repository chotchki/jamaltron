"""Layout math tests. Two of them check against real Factorio 2.1.17 assets
(dimensions measured off the shipped PNGs), the rest hammer the boundaries."""

import math

import pytest

from render.spritesheet import MAX_SHEET_SIDE, SheetLayout, plan_sheet


def test_stock_spidertron_torso_is_one_sheet():
    # base/graphics/entity/spidertron/torso/spidertron-body.png is 1056x1104:
    # 64 rotations of 132x138 at 8 per row. C.3 overlays our renders on it.
    lay = plan_sheet(64, 132, 138, line_length=8)
    assert (lay.line_length, lay.lines_per_file, lay.file_count) == (8, 8, 1)
    assert lay.sheet_sizes() == [(1056, 1104)]
    # single file -> lines_per_file is noise, keep it out of the Lua
    assert lay.prototype_fields() == {
        "width": 132, "height": 138, "frame_count": 64, "line_length": 8,
    }


def test_reproduces_shipped_spitter_run_sheets():
    # spitter-run.lua: width=250 height=220 line_length=6 lines_per_file=15,
    # 3 files. On disk: 1500x3300, 1500x3300, 1500x2860 -- last one TRIMMED to
    # its 13 used rows. max_side=3300 is what pins lines_per_file to 15.
    lay = plan_sheet(256, 250, 220, max_side=3300, line_length=6)
    assert (lay.lines_per_file, lay.file_count) == (15, 3)
    assert lay.frames_in_last_file == 256 - 2 * 90
    assert lay.sheet_sizes() == [(1500, 3300), (1500, 3300), (1500, 2860)]
    assert lay.prototype_fields()["lines_per_file"] == 15


def test_default_packs_rows_as_wide_as_the_cap_allows():
    lay = plan_sheet(64, 1000, 1000)
    assert lay.line_length == 8  # 8x1000 = 8000 <= 8192, 9 would be 9000
    assert lay.file_count == 1
    assert lay.sheet_sizes() == [(8000, 8000)]


def test_exact_fill_at_the_cap():
    # 128 frames of 64px -> 8192x8192 on the nose, still one file
    lay = plan_sheet(128 * 128, 64, 64)
    assert (lay.line_length, lay.lines_per_file, lay.file_count) == (128, 128, 1)
    assert lay.sheet_sizes() == [(8192, 8192)]


def test_one_frame_past_the_cap_spills_to_a_second_file():
    lay = plan_sheet(128 * 128 + 1, 64, 64)
    assert lay.file_count == 2
    assert lay.frames_in_last_file == 1
    # second file is one row tall, not a full 8192
    assert lay.sheet_sizes() == [(8192, 8192), (8192, 64)]


def test_fewer_frames_than_a_full_row():
    lay = plan_sheet(3, 100, 100)
    assert (lay.line_length, lay.lines_per_file, lay.file_count) == (3, 1, 1)
    assert lay.sheet_sizes() == [(300, 100)]


def test_partial_last_row_still_rounds_up():
    lay = plan_sheet(65, 132, 138, line_length=8)  # 8 full rows + 1 frame
    assert lay.lines_in_file(0) == 9
    assert lay.sheet_sizes() == [(1056, 9 * 138)]


def test_no_sheet_ever_exceeds_the_cap():
    for count in (1, 7, 64, 500, 4096, 20000):
        for w, h in ((132, 138), (448, 448), (1000, 300), (8192, 1), (1, 8192)):
            lay = plan_sheet(count, w, h)
            for sw, sh in lay.sheet_sizes():
                assert sw <= MAX_SHEET_SIDE and sh <= MAX_SHEET_SIDE, (count, w, h)
            # and the grid must actually hold every frame
            assert lay.frames_per_file * lay.file_count >= count
            assert 1 <= lay.frames_in_last_file <= lay.frames_per_file


def test_every_frame_lands_in_exactly_one_slot():
    lay = plan_sheet(1000, 300, 300, max_side=1200)  # 4 cols x 4 rows = 16/file
    assert (lay.line_length, lay.lines_per_file) == (4, 4)
    assert lay.file_count == math.ceil(1000 / 16)
    total = sum(lay.lines_in_file(i) for i in range(lay.file_count)) * lay.line_length
    assert total >= 1000
    assert total - 1000 < lay.line_length  # slack only ever in the last row


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frame_count": 0, "frame_width": 10, "frame_height": 10},
        {"frame_count": -1, "frame_width": 10, "frame_height": 10},
        {"frame_count": 4, "frame_width": 0, "frame_height": 10},
        {"frame_count": 4, "frame_width": 10, "frame_height": -3},
    ],
)
def test_rejects_nonsense_sizes(kwargs):
    with pytest.raises(ValueError):
        plan_sheet(**kwargs)


def test_rejects_a_frame_bigger_than_the_sheet():
    with pytest.raises(ValueError, match="does not fit"):
        plan_sheet(4, 9000, 100)
    with pytest.raises(ValueError, match="does not fit"):
        plan_sheet(4, 100, 9000)


def test_rejects_a_line_length_that_overflows_the_sheet():
    with pytest.raises(ValueError, match="exceeds max_side"):
        plan_sheet(64, 132, 138, line_length=63)  # 63x132 = 8316 > 8192
    with pytest.raises(ValueError):
        plan_sheet(64, 132, 138, line_length=0)


def test_lines_in_file_bounds_checked():
    lay = plan_sheet(10, 10, 10)
    with pytest.raises(IndexError):
        lay.lines_in_file(1)
    with pytest.raises(IndexError):
        lay.lines_in_file(-1)


def test_layout_is_frozen():
    lay = plan_sheet(10, 10, 10)
    assert isinstance(lay, SheetLayout)
    with pytest.raises(Exception):
        lay.line_length = 3  # type: ignore[misc]
