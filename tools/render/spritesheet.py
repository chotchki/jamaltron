"""Sprite-sheet layout math: frame count + frame size -> the numbers Factorio wants.

Stdlib only, no bpy and no Pillow, so it imports in BOTH interpreters (uv's 3.11
and Blender's bundled 3.11) and unit-tests without launching Blender. That split
is the whole point -- see tools/README.md.

Factorio packs an animation as a grid of equal-size frames: `line_length` frames
per row, read left-to-right then top-to-bottom. Past one file you switch to
`filenames` + `lines_per_file`, and the engine derives the file index from the
frame index. The last file may be SHORT; every earlier file must be full.

Measured against Factorio 2.1.17's shipped assets, not inferred from docs:
  - no PNG in core/base/space-age/quality/elevated-rails exceeds 8192 px on
    either side (8965 files checked), hence MAX_SHEET_SIDE
  - base/graphics/entity/spitter/spitter-run.lua declares width=250 height=220
    line_length=6 lines_per_file=15 over 3 files, and the files on disk are
    1500x3300, 1500x3300, 1500x2860 -- the last one trimmed to its 13 used rows.
    test_spritesheet.py reproduces exactly that.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Hard ceiling per sheet side, in pixels. Factorio loads a sheet as one GPU
#: texture; go over and you are gambling on the player's hardware.
MAX_SHEET_SIDE = 8192


@dataclass(frozen=True)
class SheetLayout:
    """A solved grid. `prototype_fields()` is what goes in the Lua."""

    frame_count: int
    frame_width: int
    frame_height: int
    line_length: int  # frames per row
    lines_per_file: int  # rows per file; the last file may use fewer
    file_count: int

    @property
    def frames_per_file(self) -> int:
        return self.line_length * self.lines_per_file

    @property
    def frames_in_last_file(self) -> int:
        return self.frame_count - (self.file_count - 1) * self.frames_per_file

    def lines_in_file(self, index: int) -> int:
        """Rows actually used by file `index` (0-based)."""
        if not 0 <= index < self.file_count:
            raise IndexError(f"file {index} out of range (file_count={self.file_count})")
        if index < self.file_count - 1:
            return self.lines_per_file
        return math.ceil(self.frames_in_last_file / self.line_length)

    def sheet_size(self, index: int) -> tuple[int, int]:
        """(width, height) in pixels of file `index`. Trims the last file."""
        return (self.line_length * self.frame_width,
                self.lines_in_file(index) * self.frame_height)

    def sheet_sizes(self) -> list[tuple[int, int]]:
        """Every file's pixel size, in `filenames` order. The C.8 lint gate
        compares these against the real PNGs on disk."""
        return [self.sheet_size(i) for i in range(self.file_count)]

    def prototype_fields(self) -> dict[str, int]:
        """The layout half of a Factorio Animation/RotatedAnimation table.

        Caller supplies the rest: `filename`/`filenames`, `shift`, `scale`,
        `direction_count`, flags. `lines_per_file` is emitted only when it is
        load-bearing, i.e. when the animation spans more than one file.
        """
        fields = {
            "width": self.frame_width,
            "height": self.frame_height,
            "frame_count": self.frame_count,
            "line_length": self.line_length,
        }
        if self.file_count > 1:
            fields["lines_per_file"] = self.lines_per_file
        return fields


def plan_sheet(
    frame_count: int,
    frame_width: int,
    frame_height: int,
    *,
    max_side: int = MAX_SHEET_SIDE,
    line_length: int | None = None,
) -> SheetLayout:
    """Solve the grid: widest legal rows first, then as many rows per file as fit.

    Args:
        frame_count: total frames in the animation (>= 1).
        frame_width: per-frame width in px (>= 1).
        frame_height: per-frame height in px (>= 1).
        max_side: per-sheet ceiling per side. Lower it to force multi-file output
            or to reproduce a layout somebody else picked.
        line_length: force the column count (8 mirrors the stock spidertron
            torso, whose 64 frames of 132x138 make one 1056x1104 sheet). Default
            packs rows as wide as `max_side` allows.

    Raises:
        ValueError: on a non-positive argument, or a single frame that cannot fit
            inside `max_side` -- that needs a smaller frame, not a smarter grid.
    """
    if frame_count < 1:
        raise ValueError(f"frame_count must be >= 1, got {frame_count}")
    if frame_width < 1 or frame_height < 1:
        raise ValueError(f"frame size must be positive, got {frame_width}x{frame_height}")
    if max_side < 1:
        raise ValueError(f"max_side must be >= 1, got {max_side}")
    if frame_width > max_side or frame_height > max_side:
        raise ValueError(
            f"one {frame_width}x{frame_height} frame does not fit in a "
            f"{max_side}px sheet; shrink the frame or raise max_side"
        )

    columns_that_fit = max_side // frame_width
    if line_length is None:
        columns = min(frame_count, columns_that_fit)
    else:
        if line_length < 1:
            raise ValueError(f"line_length must be >= 1, got {line_length}")
        if line_length > columns_that_fit:
            raise ValueError(
                f"line_length={line_length} x {frame_width}px = "
                f"{line_length * frame_width}px exceeds max_side={max_side}"
            )
        columns = line_length

    lines_needed = math.ceil(frame_count / columns)
    lines_per_file = min(lines_needed, max_side // frame_height)
    file_count = math.ceil(frame_count / (columns * lines_per_file))

    return SheetLayout(
        frame_count=frame_count,
        frame_width=frame_width,
        frame_height=frame_height,
        line_length=columns,
        lines_per_file=lines_per_file,
        file_count=file_count,
    )
