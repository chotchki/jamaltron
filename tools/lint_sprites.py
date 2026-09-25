#!/usr/bin/env python3
"""Sprite-sheet gate: cross-check declared sprite geometry against the real PNGs.

This is the ONLY sprite validation that can run in CI, because Factorio itself has
none. MEASURED 2026-09-19 against 2.1.17:

  * `--dump-data` and `--create` are sprite-BLIND on both the mac full build and the
    headless build. Both exit 0 with a PNG missing entirely AND with a declared-size
    vs actual-size mismatch. They load the data stage, not the graphics.
  * the headless linux build ships ZERO PNGs, so it can never check sprites at all -
    which is exactly the build GitHub Actions runs (PLAN F.1).
  * the only mode that rasterizes, `--dump-icon-sprites`, is mac-only and reports
    errors through a MODAL DIALOG that hangs the process. Unusable from a script.

So a wrong `line_length` ships silently and surfaces in-game as a shark sliced across
two frames, with no error text anywhere. This script is the gate that catches it.

Stdlib only, on purpose: CI runs `python3 tools/lint_sprites.py ...` with no venv and
no Pillow. PNG dimensions come out of the 24-byte IHDR header, which is also far
cheaper than decoding the image. The tests use Pillow to BUILD fixtures - that is a
dev-time dependency, not a runtime one.

WHAT IT CHECKS (every one of these is a real Factorio failure mode)

  sheet-too-small   the declared rectangle does not fit the file. Mirrors Factorio's
                    own wording, so grepping a real crash lands you here:
                    "The given sprite rectangle (left_top=0x0, right_bottom=64x64) is
                    outside the actual sprite size (left_top=0x0, right_bottom=32x32)"
                    For a multi-frame sheet the message also spells out the frame
                    arithmetic - frames needed, line_length, rows, rows available -
                    because that is the actionable half when the culprit is a wrong
                    line_length rather than a wrong width.
  missing-file      a referenced PNG is not on disk.
  sheet-too-big     a file (or a declared layout) over 8192 px on a side.
  ragged-sheet      WARN. A multi-frame sheet whose pixel dimensions are not an exact
                    multiple of the frame size: leftover pixels mean the render and the
                    declaration disagree about the frame. A warning rather than an error
                    because the engine loads it anyway, and MEASURED, 11 of 4424 shipped
                    declarations are padded like that (pump-north.png carries 9 spare
                    pixel rows). `--strict` fails on it, which is what our own sheets get.
  frame-shortfall   the fallback when `line_length` is absent AND frame_count is 1, where
                    the engine's default row width depends on which prototype field is
                    being loaded and a bare table does not say. See SpriteSpec.columns.
  file-count        `filenames` + `lines_per_file` do not add up to the frame count.
  frame-sequence    a `frame_sequence` (the play order C.21's sequence sheets carry) that
                    names a frame the sheet does not have - it is 1-BASED, so frame_count
                    itself is legal and 0 is not - or plays past Factorio's 255-frame cap
                    on an animation's played length. `--strict` also calls a cell that the
                    sequence never plays `unused-frames`: it still ships in the PNG.
  unresolved-*      the declaration could not be read as literal numbers. Reported as
                    an ERROR, never skipped: a green run that checked nothing is worse
                    than a red one (same rule tools/lint.sh applies to its two gates).

WHY line_length ERRORS CANNOT HIDE: changing the column count changes the row count
too, so both a too-large and a too-small `line_length` push the declared rectangle
outside the file. 64 frames of 132x138 living in a 1056x1104 sheet need exactly
line_length 8; declare 16 and the rect is 2112 px wide, declare 4 and it is 2208 px
tall. Either way `sheet-too-small` fires.

WHAT IT CANNOT CHECK, stated plainly:
  * a `line_length` that is wrong but still fits (declare 32 of the 64 rotations and
    the rect is merely shorter). `--strict` adds `unused-frames` for that, which is a
    smell in art you generated and NORMAL in art you share - see the note on that
    check for why it cannot be a default.
  * whether the pixels inside a frame are the right pixels. That is C.3's overlay and
    F.2's eyeball, not a lint.
  * icons. `__base__/graphics/icons/spidertron.png` is 120x64 for a 64 px icon because
    mipmaps are packed horizontally and auto-detected from the width, so an icon gate
    needs mipmap inference it would be wrong to fake here. C.6's output is NOT covered.

HOW IT READS THE DECLARATIONS - and why the JSON manifest is the real input

Two front ends, and the choice between them is the whole design argument.

`--` A JSON MANIFEST (`*.json`) is the CI path and the one C.7's pack.py must emit.
pack.py already computes every number it puts in the Lua (it owns
render/spritesheet.plan_sheet), so it serializes the SAME dict twice - once as a Lua
table, once as a manifest entry, same field names, no translation layer. Two artefacts
from one source cannot drift. Nothing has to be parsed, so the gate has no failure mode
of its own and needs no game install.

`--` LUA (`*.lua`) is a calibration front end, not the gate. It tokenizes the file and
reads table constructors with a small recursive-descent reader, resolving ONLY literals
and refusing to guess at anything else. It exists so this script can be pointed at
Wube's shipped declarations and proved not to slander them.

Reading real Factorio Lua to find out what the engine loads is IMPOSSIBLE by design,
and base's own spidertron proves it three separate ways:

  1. `util.sprite_load(path, opts)` (core/lualib/util.lua:684) pulls width, height and
     line_length out of a `require`d SIBLING .lua file and mutates the caller's table.
     spitter-animations.lua:92 declares `frame_count = 16, direction_count = 16` and no
     geometry at all; spitter-run.lua declares the geometry and no frame count. Neither
     file is checkable alone, and no regex crosses that boundary.
  2. spidertron-animations.lua's leg sprites are SYNTHESIZED.
     create_leg_sprite_layer_definition (:4-21) deepcopies the literal template, sets
     `x = width * (column - 1)` and `y = height * (row - 1)`, then OVERWRITES
     line_length and direction_count with 1. The literal that a reader can see
     (line_length 8, direction_count 8) is never what the engine gets.
  3. every `scale` and `shift` in that file is an expression over a `spidertron_scale`
     argument, so a reader that resolves literals only cannot see them either.

Hence the split, and hence the honesty rule in the reader: geometry that is not a
literal is an ERROR naming the expression, never a silent skip. The Lua front end
verifies TEMPLATES - which is the right and only claim it can make.

THE MANIFEST, which is C.7's half of the contract

    {
      "version": 1,
      "mod_roots": {"jamaltron": "../mod/jamaltron"},   // relative to the manifest
      "sprites": [
        {
          "id": "jamaltron.animation.layers[1]",        // free text, appears in findings
          "filename": "__jamaltron__/graphics/torso/jamaltron-body.png",
          "width": 132, "height": 138,
          "line_length": 8, "direction_count": 64
        },
        {
          "id": "jamaltron.shadow_animation",
          "filenames": ["__jamaltron__/graphics/torso/shadow-1.png",
                        "__jamaltron__/graphics/torso/shadow-2.png"],
          "width": 192, "height": 94, "line_length": 8,
          "direction_count": 64, "lines_per_file": 5
        }
      ]
    }

Sprite entries take the SAME field names the Lua table takes - filename, filenames,
width, height, size, x, y, position, line_length, direction_count, frame_count,
variation_count, lines_per_file - so pack.py builds one dict per sprite and writes it
out twice, once as Lua and once here. `id` is the only addition and the only field this
gate needs that Lua does not have. A bare JSON list of sprite entries is accepted too.
`--mod-root` and `--factorio-data` win over `mod_roots`, so CI can relocate a tree
without editing the manifest. ALWAYS EMIT `line_length`: without it the engine's default
depends on the prototype field and this gate can only check a frame budget (see
SpriteSpec.columns).

RESOLVING `__mod__/path` FILENAMES
  --factorio-data DIR   maps __core__, __base__, __space-age__, __quality__ and
                        __elevated-rails__ to DIR/<name>
  --mod-root NAME=DIR   maps one mod, e.g. --mod-root jamaltron=mod/jamaltron

SEVERITY: ERROR is "Factorio will not load this or will draw it wrong". WARN is "this
loads, but it is not what a generated sheet should look like" - a smell in art you
rendered, normal in art you share. `--strict` fails on warnings and adds two more, and is
how this repo lints its own manifest. Default mode is what you point at somebody else's
art without slandering it.

EXIT STATUS: 0 clean, 1 findings, 2 bad usage or unreadable input. Zero declarations
found is a FAILURE, not a pass.

USAGE
  tools/lint_sprites.py --strict --mod-root jamaltron=mod/jamaltron build/sprites.json
  tools/lint_sprites.py --factorio-data /Applications/factorio.app/Contents/data \\
      /Applications/factorio.app/Contents/data/base/prototypes/entity/spidertron-animations.lua
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import struct
import sys
from dataclasses import dataclass, field
from typing import Any, Iterator

from render.spritesheet import MAX_SHEET_SIDE, SheetLayout

ERROR = "ERROR"
WARN = "WARN"

#: Mod names Factorio's own data directory provides. Mapped from --factorio-data.
BUILTIN_MODS = ("core", "base", "space-age", "quality", "elevated-rails")

#: Layout features this gate does not model. Present in a declaration means the frame
#: arithmetic below would be wrong, so the declaration is reported and NOT checked.
#: Our pack.py emits none of them; base uses `stripes` in places.
UNMODELLED_FIELDS = ("stripes", "back_equals_front", "axially_symmetrical", "dice",
                     "dice_x", "dice_y", "frames", "slice", "slice_x", "slice_y")

#: Sounds and haptics carry a `filename` too and are NOT sprites. Without this, a sweep
#: over base + core + space-age reports 900 broken sprites that are all .ogg files.
NON_IMAGE_SUFFIXES = (".ogg", ".wav", ".mp3", ".voc", ".flac", ".bnvib", ".ogv", ".webm")


# --------------------------------------------------------------------- findings

@dataclass(frozen=True)
class Finding:
    """One problem, already attributed to a declaration and a file."""

    severity: str
    code: str
    origin: str
    message: str
    detail: tuple[str, ...] = ()

    def render(self) -> str:
        head = f"  {self.severity:5s} {self.code:17s} {self.origin}\n         {self.message}"
        return "\n".join([head] + [f"         {line}" for line in self.detail])


# ------------------------------------------------------------------- PNG header

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def png_size(path: pathlib.Path) -> tuple[int, int]:
    """(width, height) from a PNG's IHDR. No decode, no Pillow, 24 bytes read.

    Raises:
        ValueError: not a PNG, truncated, or a zero dimension.
    """
    with open(path, "rb") as handle:
        head = handle.read(24)
    if len(head) < 24:
        raise ValueError(f"truncated: {len(head)} bytes, a PNG header needs 24")
    if head[:8] != _PNG_MAGIC:
        raise ValueError("not a PNG (bad signature)")
    if head[12:16] != b"IHDR":
        raise ValueError("not a PNG (first chunk is not IHDR)")
    width, height = struct.unpack(">II", head[16:24])
    if width == 0 or height == 0:
        raise ValueError(f"degenerate size {width}x{height}")
    return width, height


# -------------------------------------------------------------- mod path lookup

class ModPaths:
    """Resolves `__mod__/relative/path.png` to a real path on disk."""

    def __init__(self) -> None:
        self._roots: dict[str, pathlib.Path] = {}

    def add(self, name: str, root: pathlib.Path) -> None:
        self._roots[name.strip("_")] = root

    def add_factorio_data(self, data_dir: pathlib.Path) -> None:
        for mod in BUILTIN_MODS:
            candidate = data_dir / mod
            if candidate.is_dir():
                self.add(mod, candidate)

    @property
    def known(self) -> list[str]:
        return sorted(self._roots)

    def resolve(self, filename: str) -> pathlib.Path:
        """Raises KeyError naming the mod when the root was never registered."""
        match = re.match(r"^__([^_/][^/]*?)__/(.+)$", filename)
        if match is None:
            return pathlib.Path(filename)
        mod, rest = match.group(1), match.group(2)
        try:
            root = self._roots[mod]
        except KeyError:
            raise KeyError(mod) from None
        return root / rest


# ------------------------------------------------------------------ Lua reading

class Unresolved:
    """A value the reader refused to guess at: an expression, a call, a concat.

    Carries the raw source text so the finding can name what it choked on. Never
    coerced to a number - that is the whole point.
    """

    __slots__ = ("raw",)

    def __init__(self, raw: str) -> None:
        self.raw = raw

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Unresolved({self.raw!r})"


class LuaTable(dict):
    """A parsed table constructor. Positional entries get integer keys from 1.

    `line` is the source line of its opening brace, which is what a human needs to
    go fix it.
    """

    line: int = 0


@dataclass(frozen=True)
class _Token:
    kind: str  # "num" | "str" | "name" | "op"
    value: Any
    line: int


_WS_RE = re.compile(r"\s+")
_COMMENT_RE = re.compile(r"--[^\n]*")
_LONG_OPEN_RE = re.compile(r"\[(=*)\[")
_NUMBER_RE = re.compile(r"0[xX][0-9a-fA-F]+|(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?")
_NAME_RE = re.compile(r"[A-Za-z_]\w*")
_STRING_RE = re.compile(r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'')
_OP_RE = re.compile(r"\.\.\.|\.\.|==|~=|<=|>=|//|::|[-+*/%^#&~|<>=(){}\[\];:,.]")
_TERMINATORS = (",", ";", "}")


def _tokenize(src: str) -> list[_Token]:
    """Lua tokens, comments dropped. Long brackets `[==[ ]==]` handled for both
    strings and comments, because entity.lua's factoriopedia_simulation uses them."""
    tokens: list[_Token] = []
    pos, line, end = 0, 1, len(src)
    while pos < end:
        char = src[pos]
        match = _WS_RE.match(src, pos)
        if match:
            line += src.count("\n", pos, match.end())
            pos = match.end()
            continue
        if src.startswith("--", pos):
            long_open = _LONG_OPEN_RE.match(src, pos + 2)
            if long_open:
                pos, line = _skip_long_bracket(src, long_open, line)
            else:
                pos = _COMMENT_RE.match(src, pos).end()  # type: ignore[union-attr]
            continue
        if char == "[":
            long_open = _LONG_OPEN_RE.match(src, pos)
            if long_open:
                start_line = line
                stop, line = _skip_long_bracket(src, long_open, line)
                tokens.append(_Token("str", src[long_open.end():stop], start_line))
                pos = stop
                continue
        match = _STRING_RE.match(src, pos)
        if match:
            tokens.append(_Token("str", _unquote(match.group(0)), line))
            pos = match.end()
            continue
        match = _NUMBER_RE.match(src, pos)
        if match:
            tokens.append(_Token("num", _to_number(match.group(0)), line))
            pos = match.end()
            continue
        match = _NAME_RE.match(src, pos)
        if match:
            tokens.append(_Token("name", match.group(0), line))
            pos = match.end()
            continue
        match = _OP_RE.match(src, pos)
        if match:
            tokens.append(_Token("op", match.group(0), line))
            pos = match.end()
            continue
        pos += 1  # a byte no Lua lexer would accept; ignore it and keep going
    return tokens


def _skip_long_bracket(src: str, open_match: re.Match[str], line: int) -> tuple[int, int]:
    """Returns (index of the closing bracket, updated line number)."""
    closer = "]" + open_match.group(1) + "]"
    stop = src.find(closer, open_match.end())
    stop = len(src) if stop < 0 else stop
    line += src.count("\n", open_match.start(), stop + len(closer))
    return stop + len(closer) if stop < len(src) else len(src), line


def _unquote(raw: str) -> str:
    body = raw[1:-1]
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t", "r": "\r"}.get(m.group(1), m.group(1)), body)


def _to_number(raw: str) -> int | float:
    if raw[:2] in ("0x", "0X"):
        return int(raw, 16)
    value = float(raw)
    return int(value) if value.is_integer() and "." not in raw and "e" not in raw.lower() else value


def _entry_end(tokens: list[_Token], start: int) -> int:
    """Index of the token ending the entry that begins at `start`: a comma, a
    semicolon, or the table's own closing brace, at bracket depth 0."""
    depth, index = 0, start
    while index < len(tokens):
        token = tokens[index]
        if token.kind == "op":
            if token.value in "({[":
                depth += 1
            elif token.value in ")]":
                depth -= 1
            elif token.value == "}":
                if depth == 0:
                    return index
                depth -= 1
            elif token.value in (",", ";") and depth == 0:
                return index
        index += 1
    return index


def _parse_value(tokens: list[_Token], index: int) -> tuple[Any, int]:
    """One table value. A literal is only a literal if a terminator follows it -
    `scale = 0.5 * spidertron_scale` must NOT read as 0.5."""
    token = tokens[index]
    if token.kind == "op" and token.value == "{":
        table, after = _parse_table(tokens, index)
        if _is_terminated(tokens, after):
            return table, after
        return _unresolved(tokens, index)
    literal: Any = None
    after = index
    if token.kind == "num":
        literal, after = token.value, index + 1
    elif token.kind == "str":
        literal, after = token.value, index + 1
    elif token.kind == "name" and token.value in ("true", "false", "nil"):
        literal = {"true": True, "false": False, "nil": None}[token.value]
        after = index + 1
    elif token.kind == "op" and token.value in ("-", "+") and tokens[index + 1: index + 2] \
            and tokens[index + 1].kind == "num":
        literal = -tokens[index + 1].value if token.value == "-" else tokens[index + 1].value
        after = index + 2
    else:
        return _unresolved(tokens, index)
    if _is_terminated(tokens, after):
        return literal, after
    return _unresolved(tokens, index)


def _is_terminated(tokens: list[_Token], index: int) -> bool:
    return (index >= len(tokens)
            or (tokens[index].kind == "op" and tokens[index].value in _TERMINATORS))


def _unresolved(tokens: list[_Token], index: int) -> tuple[Unresolved, int]:
    stop = _entry_end(tokens, index)
    raw = " ".join(str(t.value) for t in tokens[index:stop])
    return Unresolved(raw.strip()), stop


def _parse_table(tokens: list[_Token], index: int) -> tuple[LuaTable, int]:
    """`tokens[index]` is `{`. Returns the table and the index just past its `}`."""
    table = LuaTable()
    table.line = tokens[index].line
    index += 1
    positional = 0
    while index < len(tokens):
        token = tokens[index]
        if token.kind == "op" and token.value == "}":
            return table, index + 1
        if token.kind == "op" and token.value in (",", ";"):
            index += 1
            continue
        key: Any
        if (token.kind == "name" and tokens[index + 1: index + 2]
                and tokens[index + 1].kind == "op" and tokens[index + 1].value == "="):
            key, index = token.value, index + 2
        elif token.kind == "op" and token.value == "[":
            close = _matching_bracket(tokens, index)
            inner = tokens[index + 1:close]
            key = inner[0].value if len(inner) == 1 else f"[{index}]"
            index = close + 1
            if tokens[index: index + 1] and tokens[index].kind == "op" and tokens[index].value == "=":
                index += 1
        else:
            positional += 1
            key = positional
        value, index = _parse_value(tokens, index)
        table[key] = value
    return table, index


def _matching_bracket(tokens: list[_Token], index: int) -> int:
    depth = 0
    while index < len(tokens):
        token = tokens[index]
        if token.kind == "op":
            if token.value == "[":
                depth += 1
            elif token.value == "]":
                depth -= 1
                if depth == 0:
                    return index
        index += 1
    return index


def read_lua_tables(src: str) -> list[LuaTable]:
    """Every table constructor in the source, outermost first (nests live inside)."""
    tokens = _tokenize(src)
    tables: list[LuaTable] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.kind == "op" and token.value == "{":
            table, index = _parse_table(tokens, index)
            tables.append(table)
        else:
            index += 1
    return tables


def iter_sprite_tables(table: LuaTable, path: str = "") -> Iterator[tuple[str, LuaTable]]:
    """Yield (dotted path, table) for every nested table declaring a file.

    Depth-first, parents before children, so a `layers` wrapper is visited before its
    layers. A table is a sprite declaration when it has `filename` or `filenames`.
    """
    if "filename" in table or "filenames" in table:
        yield path, table
    for key, value in table.items():
        if key == "stripes":
            # The parent already got an unmodelled-layout warning naming `stripes`.
            # Stripe entries carry a filename and width_in_frames/height_in_frames
            # instead of width/height, so visiting them separately only manufactures
            # no-geometry errors about art nobody claimed to check.
            continue
        if isinstance(value, LuaTable):
            child = f"{path}.{key}" if path else str(key)
            yield from iter_sprite_tables(value, child)


# ------------------------------------------------------------------ sprite specs

@dataclass
class SpriteSpec:
    """One declaration, normalised. Every count defaults the way Factorio defaults it."""

    origin: str
    filenames: list[str] = field(default_factory=list)
    width: int | None = None
    height: int | None = None
    x: int = 0
    y: int = 0
    line_length: int = 0  # 0 = Factorio's "all frames in one line"
    direction_count: int = 1
    frame_count: int = 1
    variation_count: int = 1
    lines_per_file: int | None = None
    frame_sequence: tuple[int, ...] | None = None
    unmodelled: tuple[str, ...] = ()
    bad_fields: tuple[tuple[str, str], ...] = ()

    @property
    def slots(self) -> int:
        """Frames the sheet must physically hold.

        direction_count x frame_count x variation_count, every one defaulting to 1, so
        one formula covers Sprite, RotatedSprite, Animation, RotatedAnimation and
        SpriteVariations. `repeat_count` is deliberately absent: it replays frames, it
        does not add pixels (core/lualib/util.lua's empty_animation relies on that -
        repeat_count N over a 1x1 png).

        MEASURED against 2.1.17: spitter-run is direction_count 16 x frame_count 16 =
        256 frames packed CONTINUOUSLY at line_length 6, which is what puts 43 rows in
        3 files of lines_per_file 15 and trims the last to 13. A per-direction row
        break would need 4 files. tests/test_spritesheet.py pins the same numbers.
        """
        return self.direction_count * self.frame_count * self.variation_count

    @property
    def columns(self) -> int | None:
        """Frames per row. None means the layout is genuinely unknowable - see below.

        `line_length` when declared. Otherwise it DEFAULTS TO frame_count, which the
        Factorio docs describe as "0 means all frames in one line" and which is the same
        statement only when there is one direction and one variation. MEASURED across
        base + core + space-age 2.1.17, every declaration with no line_length whose
        geometry reads as literals:

          * frame_count > 1: cols == frame_count in 49/49 rotated sheets (character
            level1_idle.png is 2024x928 = 22 frames x 8 directions), 54/54 plain
            animations, and every variation sheet (metal-particle-big.png is 600x440 =
            12 frames x 10 variations). One rule, no exceptions found.
          * frame_count == 1 with direction_count or variation_count > 1: NO DEFAULT
            EXISTS at this level. The engine's default depends on which prototype field
            is being loaded, and a bare table does not say. small-electric-pole.png is
            288x220 = 4 directions in ONE ROW (RotatedSprite, line_length defaults to
            direction_count); car-remnants-mask.png is 196x584 = 4 directions in ONE
            COLUMN (RotatedAnimation, line_length defaults to frame_count = 1). 8 of the
            first shape, 5 of the second, same fields, opposite layouts.

        So this returns None for that second case and the gate falls back to a frame
        budget it CAN prove. pack.py always emits line_length, so the manifest never
        lands here - which is one more reason the manifest is the real input.
        """
        if self.line_length > 0:
            return self.line_length
        if self.frame_count > 1:
            return self.frame_count
        if self.direction_count * self.variation_count > 1:
            return None
        return 1


_COUNT_FIELDS = {
    "line_length": "line_length",
    "direction_count": "direction_count",
    "frame_count": "frame_count",
    "variation_count": "variation_count",
}


def spec_from_table(origin: str, table: dict[Any, Any]) -> SpriteSpec:
    """Normalise one declaration. Anything unreadable lands in `bad_fields` rather
    than being guessed at or dropped."""
    spec = SpriteSpec(origin=origin)
    bad: list[tuple[str, str]] = []

    def integer(key: str, raw: Any) -> int | None:
        if isinstance(raw, Unresolved):
            bad.append((key, f"not a literal: {raw.raw}"))
            return None
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            bad.append((key, f"not a number: {raw!r}"))
            return None
        if isinstance(raw, float) and not raw.is_integer():
            bad.append((key, f"not a whole number of pixels: {raw}"))
            return None
        return int(raw)

    raw_names = table.get("filenames", table.get("filename"))
    if isinstance(raw_names, Unresolved):
        bad.append(("filename", f"not a literal: {raw_names.raw}"))
    elif isinstance(raw_names, str):
        spec.filenames = [raw_names]
    elif isinstance(raw_names, dict):
        for key in sorted(k for k in raw_names if isinstance(k, int)):
            entry = raw_names[key]
            if isinstance(entry, str):
                spec.filenames.append(entry)
            else:
                bad.append((f"filenames[{key}]", f"not a literal string: {entry!r}"))

    if "size" in table:
        # Two legal shapes. `size = {w, h}` is not decoration: the spidertron's own
        # minimap_representation and selected_minimap_representation use it
        # (entities.lua:9958, 9965, both 128x128), and those are C.6's deliverable.
        raw_size = table["size"]
        if isinstance(raw_size, dict):
            spec.width = integer("size[1]", raw_size.get(1))
            spec.height = integer("size[2]", raw_size.get(2))
        else:
            spec.width = spec.height = integer("size", raw_size)
    for key, attr in (("width", "width"), ("height", "height")):
        if key in table:
            setattr(spec, attr, integer(key, table[key]))
    if "position" in table and isinstance(table["position"], dict):
        position = table["position"]
        spec.x = integer("position[1]", position.get(1, 0)) or 0
        spec.y = integer("position[2]", position.get(2, 0)) or 0
    for key in ("x", "y"):
        if key in table:
            setattr(spec, key, integer(key, table[key]) or 0)
    for key, attr in _COUNT_FIELDS.items():
        if key in table and table[key] is not None:
            value = integer(key, table[key])
            if value is not None:
                setattr(spec, attr, value)
    if table.get("lines_per_file") is not None:
        spec.lines_per_file = integer("lines_per_file", table["lines_per_file"])
    if table.get("frame_sequence") is not None:
        raw_seq = table["frame_sequence"]
        dense = isinstance(raw_seq, dict) and all(
            isinstance(k, int) and not isinstance(k, bool) for k in raw_seq) and sorted(
            raw_seq) == list(range(1, len(raw_seq) + 1))
        if isinstance(raw_seq, dict) and not dense:
            # {[1]=1, [3]=2} has a HOLE the engine would see, and a string key is not a frame
            # at all; compacting either would be the guess this gate refuses to make.
            bad.append(("frame_sequence",
                        f"not a dense 1..n list: keys {sorted(map(str, raw_seq))[:8]}"))
        elif isinstance(raw_seq, dict):
            played = [integer(f"frame_sequence[{k}]", raw_seq[k]) for k in sorted(raw_seq)]
            if all(v is not None for v in played):
                spec.frame_sequence = tuple(v for v in played if v is not None)
        else:
            bad.append(("frame_sequence", f"not a list of frame indices: {raw_seq!r}"))

    spec.unmodelled = tuple(k for k in UNMODELLED_FIELDS if table.get(k) not in (None, False))
    spec.bad_fields = tuple(bad)
    return spec


# ---------------------------------------------------------------------- checking

def check_spec(spec: SpriteSpec, mods: ModPaths, *, strict: bool) -> list[Finding]:
    """Every finding for one declaration. Stops early only when it must: you cannot
    do frame arithmetic without a width, or measure a file that is not there."""
    out: list[Finding] = []

    for key, why in spec.bad_fields:
        out.append(Finding(ERROR, "unresolved-field", spec.origin,
                           f"cannot read `{key}`: {why}",
                           ("this gate refuses to guess at geometry - feed it C.7's JSON "
                            "manifest, or make the value a literal",)))
    if spec.unmodelled:
        out.append(Finding(WARN, "unmodelled-layout", spec.origin,
                           f"not checked, declares {', '.join(spec.unmodelled)}",
                           ("these change the frame layout in ways this gate does not "
                            "model; pack.py emits none of them",)))
        return out
    if not spec.filenames:
        # A filename we could not READ is already reported above as unresolved-field;
        # saying it twice is noise. This is the other case: no filename key at all.
        if not any(key.startswith("filename") for key, _ in spec.bad_fields):
            out.append(Finding(ERROR, "no-filename", spec.origin,
                               "declares no readable filename"))
        return out
    if all(name.lower().endswith(NON_IMAGE_SUFFIXES) for name in spec.filenames):
        return out  # a sound or haptic table, not a sprite
    if spec.width is None or spec.height is None:
        out.append(Finding(ERROR, "no-geometry", spec.origin,
                           f"missing width/height (width={spec.width}, height={spec.height})"))
        return out
    if spec.width < 1 or spec.height < 1:
        out.append(Finding(ERROR, "bad-geometry", spec.origin,
                           f"frame size must be positive, got {spec.width}x{spec.height}"))
        return out
    if spec.slots < 1:
        out.append(Finding(ERROR, "bad-geometry", spec.origin,
                           f"needs at least one frame, got direction_count="
                           f"{spec.direction_count} frame_count={spec.frame_count} "
                           f"variation_count={spec.variation_count}"))
        return out
    if spec.x < 0 or spec.y < 0:
        out.append(Finding(ERROR, "bad-geometry", spec.origin,
                           f"negative sheet offset x={spec.x} y={spec.y}"))
        return out
    if spec.frame_sequence is not None:
        out.extend(_check_frame_sequence(spec, strict=strict))

    for name in spec.filenames:
        if not name.lower().endswith(".png"):
            out.append(Finding(WARN, "not-a-png", spec.origin,
                               f"{name} is not a .png; Factorio loads PNG only"))

    paths: list[pathlib.Path] = []
    for name in spec.filenames:
        try:
            paths.append(mods.resolve(name))
        except KeyError as exc:
            out.append(Finding(ERROR, "unknown-mod", spec.origin,
                               f"no root registered for __{exc.args[0]}__ in {name}",
                               (f"known: {', '.join(mods.known) or 'none'}. Pass "
                                f"--mod-root {exc.args[0]}=DIR or --factorio-data DIR",)))
            return out

    columns = spec.columns
    if columns is None:
        out.extend(_check_frame_budget(spec, paths, strict=strict))
        return out

    rows_needed = math.ceil(spec.slots / columns)
    lines_per_file = spec.lines_per_file if len(paths) > 1 else rows_needed
    if len(paths) > 1 and not lines_per_file:
        out.append(Finding(ERROR, "file-count", spec.origin,
                           f"{len(paths)} filenames but no lines_per_file, so the engine "
                           f"cannot tell which frame lives in which file"))
        return out
    assert lines_per_file is not None
    if lines_per_file < 1:
        out.append(Finding(ERROR, "bad-geometry", spec.origin,
                           f"lines_per_file must be >= 1, got {lines_per_file}"))
        return out

    files_needed = math.ceil(spec.slots / (columns * lines_per_file))
    if files_needed != len(paths):
        out.append(Finding(ERROR, "file-count", spec.origin,
                           f"{spec.slots} frames at line_length {columns} and "
                           f"lines_per_file {lines_per_file} need {files_needed} "
                           f"file(s), {len(paths)} declared"))
    layout = SheetLayout(frame_count=spec.slots, frame_width=spec.width,
                         frame_height=spec.height, line_length=columns,
                         lines_per_file=lines_per_file, file_count=files_needed)
    if len(paths) > 1 and (spec.x or spec.y):
        out.append(Finding(WARN, "offset-with-filenames", spec.origin,
                           f"x={spec.x} y={spec.y} alongside {len(paths)} filenames; "
                           f"the offset is checked against the first file only"))

    for index, path in enumerate(paths[:files_needed]):
        out.extend(_check_file(spec, layout, index, path, strict=strict))
    if spec.line_length and spec.line_length > spec.slots:
        out.append(Finding(WARN, "line-length-unused", spec.origin,
                           f"line_length {spec.line_length} exceeds the {spec.slots} "
                           f"frame(s) declared, so a row can never fill"))
    return out


#: Factorio's cap on an animation's PLAYED length (AnimationFrameSequence, 2.1.17): "There
#: is a limit for (actual) animation length of 255 frames."
MAX_PLAYED_FRAMES = 255


def _check_frame_sequence(spec: SpriteSpec, *, strict: bool) -> list[Finding]:
    """The play order against the frames it plays. The sheet's own geometry is checked as
    usual; this is only the list of indices on top of it."""
    out: list[Finding] = []
    played = spec.frame_sequence or ()
    if not played:
        out.append(Finding(ERROR, "frame-sequence", spec.origin,
                           "frame_sequence is empty, so the animation plays nothing"))
        return out
    bad = [v for v in played if not 1 <= v <= spec.frame_count]
    if bad:
        out.append(Finding(ERROR, "frame-sequence", spec.origin,
                           f"frame_sequence names frame(s) {sorted(set(bad))[:8]} against "
                           f"frame_count {spec.frame_count}",
                           ("frame_sequence is 1-BASED: 1..frame_count, so 0 is off the front "
                            "and frame_count itself is the last frame",)))
    if len(played) > MAX_PLAYED_FRAMES:
        out.append(Finding(ERROR, "frame-sequence", spec.origin,
                           f"frame_sequence plays {len(played)} frames; Factorio caps an "
                           f"animation's played length at {MAX_PLAYED_FRAMES}"))
    unplayed = sorted(set(range(1, spec.frame_count + 1)) - set(played))
    if strict and unplayed:
        out.append(Finding(WARN, "unused-frames", spec.origin,
                           f"frame(s) {unplayed[:8]}{'...' if len(unplayed) > 8 else ''} are "
                           f"in the sheet but frame_sequence never plays them",
                           ("Factorio skips loading them, but they still ship in the PNG",)))
    return out


def _check_frame_budget(spec: SpriteSpec, paths: list[pathlib.Path], *, strict: bool
                        ) -> list[Finding]:
    """The only claim available when the grid shape is unknowable: does the art exist.

    Counts whole frames of the declared size across every file and compares to the
    frames the declaration needs. It cannot catch a wrong `line_length` (there is no
    declared line_length to be wrong) and it over-counts on a shared sheet, so it never
    false-positives - it only catches a file that is outright too small for its
    declaration. `--strict` asks for the line_length that would make a real check
    possible; C.7's pack.py always emits one.
    """
    out: list[Finding] = []
    available = 0
    for index, path in enumerate(paths):
        label = spec.origin if len(paths) == 1 else f"{spec.origin} [{index + 1}]"
        if not path.is_file():
            out.append(Finding(ERROR, "missing-file", label, f"no such file: {path}"))
            continue
        try:
            actual_w, actual_h = png_size(path)
        except (OSError, ValueError) as exc:
            out.append(Finding(ERROR, "bad-png", label, f"{path}: {exc}"))
            continue
        if actual_w > MAX_SHEET_SIDE or actual_h > MAX_SHEET_SIDE:
            out.append(Finding(ERROR, "sheet-too-big", label,
                               f"{path.name} is {actual_w}x{actual_h}, over the "
                               f"{MAX_SHEET_SIDE}px per-side limit"))
        available += (actual_w // spec.width) * (actual_h // spec.height)
    if any(f.code in ("missing-file", "bad-png") for f in out):
        return out
    if available < spec.slots:
        out.append(Finding(
            ERROR, "frame-shortfall", spec.origin,
            f"{spec.slots} frame(s) needed (direction_count {spec.direction_count} x "
            f"frame_count {spec.frame_count} x variation_count {spec.variation_count}) "
            f"but the file(s) hold at most {available} whole {spec.width}x{spec.height} "
            f"frame(s)"))
    elif strict:
        out.append(Finding(
            WARN, "no-line-length", spec.origin,
            f"no line_length, and with frame_count 1 the engine's default depends on the "
            f"prototype field, so only the frame budget was checked "
            f"({available} available, {spec.slots} needed)",
            ("declare line_length to get the real geometry check",)))
    return out


def _check_file(spec: SpriteSpec, layout: SheetLayout, index: int, path: pathlib.Path,
                *, strict: bool) -> list[Finding]:
    out: list[Finding] = []
    label = spec.origin if len(spec.filenames) == 1 else f"{spec.origin} [{index + 1}]"
    if not path.is_file():
        return [Finding(ERROR, "missing-file", label, f"no such file: {path}")]
    try:
        actual_w, actual_h = png_size(path)
    except (OSError, ValueError) as exc:
        return [Finding(ERROR, "bad-png", label, f"{path}: {exc}")]

    rows = layout.lines_in_file(index)
    # line_length is a row WIDTH LIMIT, not a claim that the row is full: a 1-frame
    # sprite declared alongside line_length 4 occupies one column, not four. Wube leans
    # on this - space-age's oil-refinery-frozen.png is a 4-direction 1304x444 sheet whose
    # four Sprite4Way entries each declare line_length 4 and slice one 326px column with
    # x. Multiplying by line_length invents a 1630px rectangle that is not there.
    frames_here = (layout.frames_in_last_file if index == layout.file_count - 1
                   else layout.frames_per_file)
    need_w = spec.x + min(layout.line_length, frames_here) * spec.width
    need_h = spec.y + rows * spec.height

    if actual_w > MAX_SHEET_SIDE or actual_h > MAX_SHEET_SIDE:
        out.append(Finding(ERROR, "sheet-too-big", label,
                           f"{path.name} is {actual_w}x{actual_h}, over the "
                           f"{MAX_SHEET_SIDE}px per-side limit"))
    if need_w > MAX_SHEET_SIDE or need_h > MAX_SHEET_SIDE:
        out.append(Finding(ERROR, "sheet-too-big", label,
                           f"the declared layout wants {need_w}x{need_h}, over the "
                           f"{MAX_SHEET_SIDE}px per-side limit",
                           ("raise line_length to trade rows for columns, or split the "
                            "animation with filenames + lines_per_file",)))

    if actual_w < need_w or actual_h < need_h:
        detail: list[str] = [f"{path}"]
        if spec.slots > 1:
            available = (actual_w // spec.width) * (actual_h // spec.height)
            detail.append(
                f"{spec.slots} frame(s) needed (direction_count {spec.direction_count} "
                f"x frame_count {spec.frame_count} x variation_count "
                f"{spec.variation_count}) at line_length {layout.line_length} = "
                f"{rows} row(s) of {spec.height}px; the file gives "
                f"{actual_h // spec.height} row(s) x {actual_w // spec.width} "
                f"column(s) = {available} frame(s)")
        out.append(Finding(
            ERROR, "sheet-too-small", label,
            f"The given sprite rectangle (left_top={spec.x}x{spec.y}, "
            f"right_bottom={need_w}x{need_h}) is outside the actual sprite size "
            f"(left_top=0x0, right_bottom={actual_w}x{actual_h})",
            tuple(detail)))
        return out  # a sheet that does not fit makes every count below meaningless

    # Leftover pixels mean a torn frame - but ONLY on a grid. A single-frame sprite has
    # no last frame to tear, and padding around it is normal: core/graphics/empty.png is
    # 64x64 declared as 1x1, and base's 64px icons are 120px wide because mipmaps pack
    # horizontally. Both would false-positive if this ran on single-slot declarations.
    # Offsets mean a shared sheet sliced by x/y, where the remainder is someone else's
    # art, so skip those too.
    if spec.slots > 1 and not spec.x and not spec.y:
        remainder_w, remainder_h = actual_w % spec.width, actual_h % spec.height
        if remainder_w or remainder_h:
            out.append(Finding(
                WARN, "ragged-sheet", label,
                f"{path.name} is {actual_w}x{actual_h}, not a whole multiple of the "
                f"{spec.width}x{spec.height} frame ({remainder_w}px over horizontally, "
                f"{remainder_h}px vertically)",
                ("leftover pixels mean the render and the declaration disagree on "
                 "the frame size, so the last frame is torn. WARN not ERROR because the "
                 "engine loads it anyway: MEASURED, 11 of 4424 shipped declarations are "
                 "padded like this (pump-north.png carries 9 spare pixel rows), none of "
                 "them torn. --strict makes it fail, which is what our own sheets get.",)))

    # --strict only, and that is a measured decision, not timidity: base slices ONE
    # shared file per leg index (spidertron-legs-lower-end-A.png is 320x294 = 8 leg
    # columns x 3 render passes) so unused frames are normal in art you share and a
    # smell only in art you generated. It fires on 7 of the 24 stock spidertron sheets.
    if strict and spec.slots > 1 and not spec.x and not spec.y:
        available = (actual_w // spec.width) * (actual_h // spec.height)
        if available > spec.slots:
            out.append(Finding(WARN, "unused-frames", label,
                               f"{path.name} holds {available} frame(s), the declaration "
                               f"uses {spec.slots}; {available - spec.slots} frame(s) of "
                               f"art will never be drawn"))
    return out


# ------------------------------------------------------------------- front ends

def specs_from_lua(path: pathlib.Path) -> list[SpriteSpec]:
    """Literal-only. See the module docstring for why this checks TEMPLATES, not what
    the engine actually loads."""
    source = path.read_text(encoding="utf-8", errors="replace")
    specs: list[SpriteSpec] = []
    for table in read_lua_tables(source):
        for dotted, sprite in iter_sprite_tables(table):
            suffix = f" {dotted}" if dotted else ""
            specs.append(spec_from_table(f"{path.name}:{sprite.line}{suffix}", sprite))
    return specs


def specs_from_manifest(path: pathlib.Path, mods: ModPaths) -> list[SpriteSpec]:
    """C.7's manifest: {"version": 1, "mod_roots": {...}, "sprites": [ {...} ]}.

    Sprite entries use the SAME field names as the Lua table, because pack.py
    serializes one dict into both. A bare list of sprites is accepted too.
    """
    document = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(document, list):
        sprites, roots = document, {}
    elif isinstance(document, dict):
        sprites = document.get("sprites", [])
        roots = document.get("mod_roots", {}) or {}
        if not isinstance(sprites, list):
            raise ValueError(f"{path}: 'sprites' must be a list, got {type(sprites).__name__}")
    else:
        raise ValueError(f"{path}: expected an object or a list, got {type(document).__name__}")
    for name, root in roots.items():
        # Manifest roots are relative to the manifest, and the CLI still wins: add()
        # only fills names --mod-root and --factorio-data have not already claimed.
        if name.strip("_") not in mods.known:
            mods.add(name, (path.parent / root).resolve())
    specs: list[SpriteSpec] = []
    for index, entry in enumerate(sprites):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: sprites[{index}] must be an object")
        origin = str(entry.get("id") or f"{path.name}:sprites[{index}]")
        specs.append(spec_from_table(origin, _jsonify(entry)))
    return specs


def _jsonify(entry: dict[str, Any]) -> dict[Any, Any]:
    """JSON lists become 1-based dicts so spec_from_table sees the same shape a Lua
    table constructor gives it."""
    out: dict[Any, Any] = {}
    for key, value in entry.items():
        out[key] = {i + 1: v for i, v in enumerate(value)} if isinstance(value, list) else value
    return out


# ------------------------------------------------------------------------- main

def lint(targets: list[pathlib.Path], mods: ModPaths, *, strict: bool
         ) -> tuple[list[Finding], int, int]:
    """(findings, declarations checked, files referenced)."""
    findings: list[Finding] = []
    specs: list[SpriteSpec] = []
    for target in targets:
        if target.suffix == ".json":
            found = specs_from_manifest(target, mods)
        elif target.suffix == ".lua":
            found = specs_from_lua(target)
        else:
            raise ValueError(f"{target}: expected a .lua declaration or a .json manifest")
        if not found:
            findings.append(Finding(ERROR, "no-sprites", str(target),
                                    "no sprite declarations found",
                                    ("a gate that checked nothing is worse than a red one",)))
        specs.extend(found)
    for spec in specs:
        findings.extend(check_spec(spec, mods, strict=strict))
    files = len({name for spec in specs for name in spec.filenames})
    return findings, len(specs), files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lint_sprites.py",
        description="Cross-check declared Factorio sprite geometry against the real PNGs.",
        epilog="Exit 0 clean, 1 findings, 2 bad usage. See the module docstring for the "
               "list of checks and for why the JSON manifest is the CI input.")
    parser.add_argument("targets", nargs="+", type=pathlib.Path,
                        metavar="TARGET", help=".json manifest (C.7) or .lua declaration")
    parser.add_argument("--factorio-data", type=pathlib.Path, metavar="DIR",
                        help=f"maps {', '.join('__%s__' % m for m in BUILTIN_MODS)}")
    parser.add_argument("--mod-root", action="append", default=[], metavar="NAME=DIR",
                        help="map one mod, e.g. --mod-root jamaltron=mod/jamaltron")
    parser.add_argument("--strict", action="store_true",
                        help="warnings fail the run, and add the unused-frames smell check")
    parser.add_argument("-q", "--quiet", action="store_true", help="only print failures")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="list every declaration and the file it resolved to")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mods = ModPaths()
    for pair in args.mod_root:
        name, _, root = pair.partition("=")
        if not name or not root:
            print(f"lint-sprites: --mod-root wants NAME=DIR, got {pair!r}", file=sys.stderr)
            return 2
        mods.add(name, pathlib.Path(root))
    if args.factorio_data:
        if not args.factorio_data.is_dir():
            print(f"lint-sprites: --factorio-data {args.factorio_data} is not a directory",
                  file=sys.stderr)
            return 2
        mods.add_factorio_data(args.factorio_data)

    try:
        findings, declarations, files = lint(args.targets, mods, strict=args.strict)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"lint-sprites: {exc}", file=sys.stderr)
        return 2

    if args.verbose:
        for target in args.targets:
            print(f"lint-sprites: read {target}")
    errors = [f for f in findings if f.severity == ERROR]
    warnings = [f for f in findings if f.severity == WARN]
    for finding in errors + warnings:
        print(finding.render())
    tally = (f"{declarations} declaration(s), {files} file(s), "
             f"{len(errors)} error(s), {len(warnings)} warning(s)")
    if errors or (warnings and args.strict):
        print(f"lint-sprites: FAILED  {tally}")
        return 1
    if not args.quiet:
        print(f"lint-sprites: PASSED  {tally}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
