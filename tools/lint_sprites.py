#!/usr/bin/env python3
"""Sprite-sheet gate: cross-check declared sprite geometry against the real PNGs.

The ONLY sprite validation that can run in CI, because Factorio itself has none.
MEASURED 2026-09-19 against 2.1.17:

  * `--dump-data` and `--create` are sprite-BLIND on both the mac full build and the
    headless build: both exit 0 with a PNG missing entirely AND with a declared-size
    vs actual-size mismatch. They load the data stage, not the graphics.
  * the headless linux build ships ZERO PNGs, so it can never check sprites - and it
    is the build GitHub Actions runs (PLAN F.1).
  * the only mode that rasterizes, `--dump-icon-sprites`, is mac-only and reports
    errors through a MODAL DIALOG that hangs the process. Unusable from a script.

So a wrong `line_length` ships silently and shows up in-game as a shark sliced across
two frames, with no error text anywhere.

Stdlib only, on purpose: CI runs `python3 tools/lint_sprites.py ...` with no venv and
no Pillow. PNG dimensions come from the 24-byte IHDR header, far cheaper than decoding.
The tests use Pillow to BUILD fixtures, a dev-time dependency only.

WHAT IT CHECKS (each is a real Factorio failure mode)

  sheet-too-small   the declared rectangle does not fit the file. Mirrors Factorio's
                    own wording, so grepping a real crash lands you here:
                    "The given sprite rectangle (left_top=0x0, right_bottom=64x64) is
                    outside the actual sprite size (left_top=0x0, right_bottom=32x32)"
                    A multi-frame sheet also gets the frame arithmetic (frames
                    needed, line_length, rows, rows available), the actionable half
                    when the culprit is a wrong line_length, not a wrong width.
  missing-file      a referenced PNG is not on disk.
  sheet-too-big     a file (or a declared layout) over 8192 px on a side.
  ragged-sheet      WARN. A multi-frame sheet whose pixel dimensions are not an exact
                    multiple of the frame size: leftover pixels mean the render and the
                    declaration disagree about the frame. WARN because the engine loads
                    it anyway, and MEASURED, 11 of 4424 shipped declarations are padded
                    like that (pump-north.png carries 9 spare pixel rows). `--strict`
                    fails on it, and our own sheets get --strict.
  frame-shortfall   the fallback when `line_length` is absent AND frame_count is 1: the
                    engine's default row width then depends on which prototype field is
                    loaded, and a bare table does not say. See SpriteSpec.columns.
  file-count        `filenames` + `lines_per_file` do not add up to the frame count.
  frame-sequence    a `frame_sequence` (the play order C.21's sequence sheets carry) that
                    names a frame the sheet does not have (1-BASED: frame_count itself is
                    legal, 0 is not), or plays past Factorio's 255-frame cap on an
                    animation's played length. `--strict` also flags a cell the sequence
                    never plays as `unused-frames`: it still ships in the PNG.
  icon-*            PLAN C.15, icons, which the frame arithmetic cannot read: a 2.x
                    icon file is its mipmap chain side by side, largest first, and the
                    engine counts the levels off the WIDTH (`icon_mipmaps` is gone).
                    `__base__/graphics/icons/spidertron.png` is 120x64 = 64+32+16+8.
                    icon-size: the file is not icon_size tall. icon-not-square: the width
                    is neither the height nor a valid chain for it. icon-mipmaps: a valid
                    chain with the wrong level count (manifest only - see ICON_KINDS).
                    thumbnail-size / thumbnail-path: not 144x144, or not at the mod root.
                    icon-no-alpha: WARN, an icon that will draw as an opaque square.
                    CALIBRATED 2026-09-26, --strict, every prototype file of all six
                    built-in mods: 1566 icon declarations, the 1537 literal ones ZERO
                    findings, the other 29 `unresolved-icon` string concatenations.
  unresolved-*      the declaration could not be read as literal numbers. An ERROR,
                    never skipped: a pass that checked nothing is worse than a failure
                    (tools/lint.sh's rule for its two gates).

WHY line_length ERRORS CANNOT HIDE: the column count sets the row count, so both a
too-large and a too-small `line_length` push the declared rectangle outside the file.
64 frames of 132x138 in a 1056x1104 sheet need exactly line_length 8; declare 16 and
the rect is 2112 px wide, declare 4 and it is 2208 px tall. Either way
`sheet-too-small` fires.

WHAT IT CANNOT CHECK:
  * a `line_length` that is wrong but still fits (declare 32 of the 64 rotations and
    the rect is merely shorter). `--strict` adds `unused-frames` for that, which cannot
    be a default (see SEVERITY).
  * whether the pixels inside a frame are the right pixels. That is C.3's overlay and
    F.2's eyeball, not a lint.
  * what an icon LOOKS like. The icon checks below are geometry only.

HOW IT READS THE DECLARATIONS: two front ends, and the JSON manifest is the real input.

`--` A JSON MANIFEST (`*.json`) is the CI path and what C.7's pack.py emits. pack.py
already computes every number it puts in the Lua (it owns render/spritesheet.plan_sheet),
so it serializes the SAME dict twice - a Lua table and a manifest entry, same field
names, no translation layer - so a full pack writes two agreeing files. Nothing has to be
parsed, so the gate has no failure mode of its own and needs no game install.

`--` LUA (`*.lua`) tokenizes the file and reads table constructors with a small
recursive-descent reader, resolving ONLY literals and refusing to guess at anything
else. Built to calibrate against Wube's shipped declarations (proving this script does
not slander them); CI also points it at pack.py's generated prototypes/*_generated.lua,
because a subset pack can leave that file and its manifest describing different layers.

Reading arbitrary Factorio Lua to find out what the engine loads is IMPOSSIBLE, and
base's own spidertron shows it three ways:

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

Hence the honesty rule in the reader: non-literal geometry is an ERROR naming the
expression, never a silent skip. The Lua front end verifies TEMPLATES, the only claim
it can make.

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

ICONS go in an optional top-level `icons` list beside `sprites`:

      "icons": [
        {"id": "item", "kind": "icon", "filename": "__jamaltron__/graphics/icons/jamaltron.png"},
        {"id": "tech", "kind": "technology", "filename": "__jamaltron__/graphics/tech.png"},
        {"id": "map", "kind": "minimap", "filename": "__jamaltron__/graphics/jamaltron-map.png"},
        {"id": "thumb", "kind": "thumbnail", "filename": "__jamaltron__/thumbnail.png"}
      ]

`kind` sets the default `icon_size` and `mipmaps` level count (icon 64/4, technology
256/4, minimap 128/1, thumbnail 144/1 - base's spidertron, measured); either can be
given explicitly. An icons-only manifest still carries `"sprites": []`: that key is
what ci.yml's content classifier recognises, so CI lints the file --strict with no
workflow change.

Sprite entries take the Lua table's field names (filename, filenames, width, height,
size, x, y, position, line_length, direction_count, frame_count, variation_count,
lines_per_file, frame_sequence) plus `id`, the one field this gate needs that Lua does
not have. A bare JSON list of sprite entries is accepted too. `--mod-root` and
`--factorio-data` win over `mod_roots`, so CI can relocate a tree without editing the
manifest. ALWAYS EMIT `line_length`: without it the engine's default depends on the
prototype field and this gate can only check a frame budget (see SpriteSpec.columns).

RESOLVING `__mod__/path` FILENAMES
  --factorio-data DIR   maps __core__, __base__, __space-age__, __quality__ and
                        __elevated-rails__ to DIR/<name>
  --mod-root NAME=DIR   maps one mod, e.g. --mod-root jamaltron=mod/jamaltron

SEVERITY: ERROR is "Factorio will not load this or will draw it wrong". WARN is "this
loads, but it is not what a generated sheet should look like" - a smell in art you
rendered, normal in art you share. `--strict` fails on warnings and adds two more; this
repo lints its own manifest with it. Default mode is for somebody else's art.

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
#: `recycler` is its own mod in the 2.1.17 data dir (space-age's recipe.lua names
#: __recycler__/graphics/icons/recycling.png; C.15's icon sweep caught it missing here).
BUILTIN_MODS = ("core", "base", "space-age", "quality", "elevated-rails", "recycler")

#: Layout features this gate does not model: the frame arithmetic would be wrong, so a
#: declaration carrying one is reported and NOT checked. pack.py emits none; base uses
#: `stripes` in places.
UNMODELLED_FIELDS = ("stripes", "back_equals_front", "axially_symmetrical", "dice",
                     "dice_x", "dice_y", "frames", "slice", "slice_x", "slice_y")

#: Sounds and haptics carry a `filename` too and are NOT sprites; without this a sweep over
#: base + core + space-age reports 900 broken sprites that are all .ogg files.
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

    def copy(self) -> "ModPaths":
        out = ModPaths()
        out._roots = dict(self._roots)
        return out

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
    coerced to a number.
    """

    __slots__ = ("raw",)

    def __init__(self, raw: str) -> None:
        self.raw = raw

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Unresolved({self.raw!r})"


class LuaTable(dict):
    """A parsed table constructor. Positional entries get integer keys from 1.

    `line` is the source line of its opening brace, for the finding.
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
            # Stripe entries carry a filename but width_in_frames/height_in_frames, not
            # width/height, so visiting them only manufactures no-geometry errors.
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
        256 frames packed CONTINUOUSLY at line_length 6: 43 rows in 3 files of
        lines_per_file 15, the last trimmed to 13. A per-direction row break would need
        4 files. tests/test_spritesheet.py pins the same numbers.
        """
        return self.direction_count * self.frame_count * self.variation_count

    @property
    def columns(self) -> int | None:
        """Frames per row. None means the layout is unknowable (below).

        `line_length` when declared. Otherwise it DEFAULTS TO frame_count; the Factorio
        docs say "0 means all frames in one line", the same statement only with one
        direction and one variation. MEASURED across base + core + space-age 2.1.17,
        every declaration with no line_length whose geometry reads as literals:

          * frame_count > 1: cols == frame_count in 49/49 rotated sheets (character
            level1_idle.png is 2024x928 = 22 frames x 8 directions), 54/54 plain
            animations, and every variation sheet (metal-particle-big.png is 600x440 =
            12 frames x 10 variations). One rule, no exceptions found.
          * frame_count == 1 with direction_count or variation_count > 1: NO DEFAULT
            EXISTS at this level. The engine's default depends on which prototype field
            is loaded, and a bare table does not say. small-electric-pole.png is
            288x220 = 4 directions in ONE ROW (RotatedSprite, line_length defaults to
            direction_count); car-remnants-mask.png is 196x584 = 4 directions in ONE
            COLUMN (RotatedAnimation, line_length defaults to frame_count = 1). 8 of the
            first shape, 5 of the second, same fields, opposite layouts.

        So the second case returns None and the gate falls back to a frame budget it
        CAN prove. pack.py always emits line_length, so the manifest never lands here.
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
        # Two legal shapes. `size = {w, h}` is used by the spidertron's own
        # minimap_representation and selected_minimap_representation (entities.lua:9958,
        # 9965, both 128x128), which are C.6's deliverable.
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
    """Every finding for one declaration. Stops early only when it must: no frame
    arithmetic without a width, no measuring a file that is not there."""
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
        # An unreadable filename is already an unresolved-field above; this is the
        # other case, no filename key at all.
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
    """The play order against the frames it plays; the sheet's geometry is checked as
    usual."""
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

    Counts whole frames of the declared size across every file against the frames the
    declaration needs. It cannot catch a wrong `line_length` (none is declared) and it
    over-counts on a shared sheet, so it never false-positives - it only catches a file
    outright too small for its declaration. `--strict` asks for the line_length that
    would make a real check possible; C.7's pack.py always emits one.
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
    # sprite declared with line_length 4 occupies one column, not four. Wube relies on
    # this - space-age's oil-refinery-frozen.png is a 4-direction 1304x444 sheet whose
    # four Sprite4Way entries each declare line_length 4 and slice one 326px column with
    # x. Multiplying by line_length would invent a 1630px rectangle.
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

    # Leftover pixels mean a torn frame, but ONLY on a grid. A single-frame sprite has no
    # last frame to tear and padding around it is normal (core/graphics/empty.png is 64x64
    # declared as 1x1; base's 64px icons are 120px wide because mipmaps pack
    # horizontally). Offsets mean a shared sheet sliced by x/y, where the remainder is
    # someone else's art, so skip those too.
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

    # --strict only, MEASURED: base slices ONE shared file per leg index
    # (spidertron-legs-lower-end-A.png is 320x294 = 8 leg columns x 3 render passes), so
    # unused frames are normal in art you share and a smell only in art you generated.
    # It fires on 7 of the 24 stock spidertron sheets.
    if strict and spec.slots > 1 and not spec.x and not spec.y:
        available = (actual_w // spec.width) * (actual_h // spec.height)
        if available > spec.slots:
            out.append(Finding(WARN, "unused-frames", label,
                               f"{path.name} holds {available} frame(s), the declaration "
                               f"uses {spec.slots}; {available - spec.slots} frame(s) of "
                               f"art will never be drawn"))
    return out


# ------------------------------------------------------------------------ icons
#
# PLAN C.15. Icons are not sprite sheets: a Factorio 2.x icon file is its mipmap chain
# side by side, largest first, and the engine infers the level count from the WIDTH
# (`icon_mipmaps` is gone in 2.0). So a 64px icon with base's four levels is 64+32+16+8
# = 120 px wide and 64 tall (__base__/graphics/icons/spidertron.png, measured), and a
# 256px technology icon is 256+128+64+32 = 480x256 (__base__/graphics/technology/
# spidertron.png). The declaration only says `icon_size`; the file says the rest.

#: Default (icon_size, levels) per icon kind in THIS repo's manifest. Every row is base's
#: spidertron, measured 2026-09-26 against 2.1.17 - item icon
#: 120x64, tech icon 480x256, minimap 128x128 declared `size = {128, 128}` with
#: `flags = {"icon"}` and no chain, thumbnail 144x144 (base, quality, elevated-rails and
#: space-age all ship exactly that). A manifest entry may override either number.
ICON_KINDS: dict[str, tuple[int, int]] = {
    "icon": (64, 4),
    "technology": (256, 4),
    "minimap": (128, 1),
    "thumbnail": (144, 1),
}

#: Lua keys that name an icon file, and the key that carries ITS size. Every size key is
#: its own and defaults to 64 on its own - none inherits icon_size. Read off 2.1.17's
#: prototype-api.json: ItemWithEntityDataPrototype has icon_tintable_size and
#: icon_tintable_mask_size, ItemPrototype dark_background_icon_size, ShortcutPrototype
#: small_icon_size, each `default: 64`. So `icon_size = 32` beside a 64px tintable is right.
ICON_FIELDS = {
    "icon": "icon_size",
    "icon_tintable": "icon_tintable_size",
    "icon_tintable_mask": "icon_tintable_mask_size",
    "dark_background_icon": "dark_background_icon_size",
    "small_icon": "small_icon_size",
}

#: PNG colour types that carry alpha outright (grey+alpha, RGBA).
_ALPHA_COLOUR_TYPES = (4, 6)
#: Colour types a tRNS chunk makes transparent: greyscale (0), RGB (2) and palette (3).
_TRNS_COLOUR_TYPES = (0, 2, 3)


def mipmap_widths(size: int, limit: int = 8) -> list[int]:
    """Strip widths for 1..n levels of a `size` px icon: 64 -> [64, 96, 112, 120, 124, ...].

    Stops when the next level would not be a whole number of pixels (a 3px icon has no
    1.5px mipmap).
    """
    widths, total, level = [], 0, size
    while len(widths) < limit and level >= 1:
        total += level
        widths.append(total)
        if level % 2:
            break
        level //= 2
    return widths


def mipmap_levels(width: int, height: int) -> int | None:
    """How many mipmap levels a `width` x `height` file holds, or None if it is not a
    chain at all. The base level is square, so its size IS the height."""
    widths = mipmap_widths(height)
    return widths.index(width) + 1 if width in widths else None


def png_has_alpha(path: pathlib.Path) -> bool:
    """True when the PNG carries transparency: an alpha channel, or a tRNS chunk on a
    greyscale, RGB or palette image (a colour key is transparency too).

    Walks chunk headers only and stops at the first IDAT, because tRNS must precede it.
    """
    with open(path, "rb") as handle:
        head = handle.read(33)
        if len(head) < 26 or head[:8] != _PNG_MAGIC:
            return False
        colour = head[25]
        if colour in _ALPHA_COLOUR_TYPES:
            return True
        if colour not in _TRNS_COLOUR_TYPES:
            return False
        handle.seek(8)
        while True:
            chunk = handle.read(8)
            if len(chunk) < 8:
                return False
            length, kind = struct.unpack(">I4s", chunk)
            if kind == b"tRNS":
                return True
            if kind == b"IDAT":
                return False
            handle.seek(length + 4, 1)


@dataclass
class IconSpec:
    """One icon declaration. `levels` None means "any valid chain": the Lua front end
    reads art that is not ours and must not impose our house layout on it."""

    origin: str
    filename: str | None
    kind: str = "icon"
    size: int = 64
    levels: int | None = None
    bad_fields: tuple[tuple[str, str], ...] = ()


def _icon_int(key: str, raw: Any, bad: list[tuple[str, str]]) -> int | None:
    if isinstance(raw, Unresolved):
        bad.append((key, f"not a literal: {raw.raw}"))
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or (
            isinstance(raw, float) and not raw.is_integer()) or raw < 1:
        bad.append((key, f"not a positive whole number: {raw!r}"))
        return None
    return int(raw)


def iter_icon_tables(table: LuaTable, path: str = "") -> Iterator[tuple[str, str, LuaTable]]:
    """Yield (dotted path, icon field, table) for every icon a table names, nested
    `icons = {{icon = ...}}` layers included."""
    for key in ICON_FIELDS:
        if key in table:
            yield path, key, table
    for key, value in table.items():
        if isinstance(value, LuaTable):
            child = f"{path}.{key}" if path else str(key)
            yield from iter_icon_tables(value, child)


def icon_specs_from_lua(path: pathlib.Path) -> list[IconSpec]:
    """Literal-only, like specs_from_lua. Checks that each file is a valid chain whose
    base level matches the declared size; it does NOT impose a level count, because
    somebody else's 64px icon with two levels is legal, just not ours."""
    source = path.read_text(encoding="utf-8", errors="replace")
    specs: list[IconSpec] = []
    for table in read_lua_tables(source):
        for dotted, key, owner in iter_icon_tables(table):
            bad: list[tuple[str, str]] = []
            raw = owner[key]
            name = raw if isinstance(raw, str) else None
            if name is None:
                shown = raw.raw if isinstance(raw, Unresolved) else repr(raw)
                bad.append((key, f"not a literal string: {shown}"))
            size_key = ICON_FIELDS[key]
            size = _icon_int(size_key, owner[size_key], bad) if size_key in owner else 64
            suffix = f" {dotted}" if dotted else ""
            specs.append(IconSpec(origin=f"{path.name}:{owner.line}{suffix} {key}",
                                  filename=name, size=size or 64, levels=None,
                                  bad_fields=tuple(bad)))
    return specs


def icon_specs_from_manifest(document: Any, path: pathlib.Path) -> list[IconSpec]:
    """The manifest's optional `icons` list. Each entry:

        {"id": "item", "kind": "icon", "filename": "__jamaltron__/graphics/icons/x.png"}

    `kind` is one of ICON_KINDS and sets the default `icon_size` and `mipmaps` (the
    level count, 1 = no chain); either may be overridden. Unlike the Lua front end the
    level count IS enforced: this is our own art, and a 64px icon that lost its 8px
    level still loads but goes to mush in a zoomed-out slot.
    """
    if not isinstance(document, dict) or "icons" not in document:
        return []
    icons = document["icons"]
    if not isinstance(icons, list):
        raise ValueError(f"{path}: 'icons' must be a list, got {type(icons).__name__}")
    specs: list[IconSpec] = []
    for index, entry in enumerate(icons):
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: icons[{index}] must be an object")
        origin = str(entry.get("id") or f"{path.name}:icons[{index}]")
        bad: list[tuple[str, str]] = []
        kind = entry.get("kind", "icon")
        if kind not in ICON_KINDS:
            bad.append(("kind", f"{kind!r} is not one of {', '.join(ICON_KINDS)}"))
            kind = "icon"
        default_size, default_levels = ICON_KINDS[kind]
        name = entry.get("filename")
        if not isinstance(name, str):
            bad.append(("filename", f"not a string: {name!r}"))
            name = None
        size = _icon_int("icon_size", entry["icon_size"], bad) if "icon_size" in entry \
            else default_size
        levels = _icon_int("mipmaps", entry["mipmaps"], bad) if "mipmaps" in entry \
            else default_levels
        specs.append(IconSpec(origin=origin, filename=name, kind=kind,
                              size=size or default_size, levels=levels or default_levels,
                              bad_fields=tuple(bad)))
    return specs


def _chain_hint(size: int) -> str:
    widths = mipmap_widths(size)
    return ", ".join(f"{w} ({i + 1})" for i, w in enumerate(widths))


def check_icon(spec: IconSpec, mods: ModPaths, *, strict: bool) -> list[Finding]:
    """Every finding for one icon. `strict` only promotes the alpha WARN; the geometry
    checks are ERRORs in both modes because the engine draws a wrong one wrong."""
    out: list[Finding] = []
    for key, why in spec.bad_fields:
        out.append(Finding(ERROR, "unresolved-icon", spec.origin, f"cannot read `{key}`: {why}",
                           ("this gate refuses to guess - make the value a literal, or "
                            "declare the icon in the manifest's `icons` list",)))
    if spec.filename is None:
        return out
    name = spec.filename
    if spec.kind == "thumbnail" and not re.match(r"^__[^/]+__/thumbnail\.png$", name):
        out.append(Finding(ERROR, "thumbnail-path", spec.origin,
                           f"{name} is not <mod root>/thumbnail.png",
                           ("the game and the mod portal look for exactly that file and "
                            "nothing else - a thumbnail anywhere else is never shown",)))
    if not name.lower().endswith(".png"):
        out.append(Finding(WARN, "not-a-png", spec.origin,
                           f"{name} is not a .png; Factorio loads PNG only"))
    try:
        path = mods.resolve(name)
    except KeyError as exc:
        out.append(Finding(ERROR, "unknown-mod", spec.origin,
                           f"no root registered for __{exc.args[0]}__ in {name}",
                           (f"known: {', '.join(mods.known) or 'none'}. Pass "
                            f"--mod-root {exc.args[0]}=DIR or --factorio-data DIR",)))
        return out
    if not path.is_file():
        out.append(Finding(ERROR, "missing-file", spec.origin, f"{name} -> {path} not found"))
        return out
    try:
        width, height = png_size(path)
    except ValueError as exc:
        out.append(Finding(ERROR, "bad-png", spec.origin, f"{path.name}: {exc}"))
        return out
    label = f"{spec.origin} ({path.name})"

    if spec.kind == "thumbnail":
        if (width, height) != (144, 144):
            out.append(Finding(
                ERROR, "thumbnail-size", label,
                f"thumbnail.png is {width}x{height}, must be 144x144",
                ("144x144 is what base, quality, elevated-rails and space-age ship and what "
                 "the in-game mod list and the portal display. Wube's own recycler ships "
                 "256x256, so another size loads - this is OUR rule: an off-size thumbnail "
                 "is a render that skipped its crop step.",)))
        return out

    levels = mipmap_levels(width, height)
    if height != spec.size:
        out.append(Finding(
            ERROR, "icon-size", label,
            f"{path.name} is {width}x{height}, declared icon_size {spec.size}: the base "
            f"level must be {spec.size}px tall",
            (f"a {spec.size}px icon is {spec.size} tall at any level count; widths "
             f"(levels): {_chain_hint(spec.size)}",)))
        return out
    if width < height:
        out.append(Finding(ERROR, "icon-not-square", label,
                           f"{path.name} is {width}x{height}: narrower than it is tall, so "
                           f"its base level is not square",
                           (f"widths (levels) for a {height}px icon: {_chain_hint(height)}",)))
        return out
    if levels is None:
        out.append(Finding(
            ERROR, "icon-not-square", label,
            f"{path.name} is {width}x{height}: neither a square {height}x{height} nor a "
            f"mipmap chain of one",
            (f"the engine infers the level count from the width, so a stray column of "
             f"padding makes it read garbage. Widths (levels): {_chain_hint(height)}",)))
        return out
    if spec.levels is not None and levels != spec.levels:
        widths = mipmap_widths(spec.size)
        want = widths[spec.levels - 1] if spec.levels <= len(widths) else None
        want_text = f"{want}x{spec.size}" if want else "no valid width"
        out.append(Finding(
            ERROR, "icon-mipmaps", label,
            f"{spec.kind} wants {spec.levels} mipmap level(s) ({want_text}), "
            f"{path.name} holds {levels} ({width}x{height})",
            ("base's 64px icons carry 4 levels (64, 32, 16, 8 side by side); fewer and the "
             "icon aliases in a zoomed-out slot or on the map, more and the manifest is "
             "describing a different file from the one on disk",)))
    if not png_has_alpha(path):
        out.append(Finding(WARN, "icon-no-alpha", label,
                           f"{path.name} has no alpha channel, so it draws as an opaque "
                           f"square", ("legal, and never what a rendered icon means",)))
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
        # Manifest roots are relative to the manifest, and the CLI wins: only names
        # --mod-root and --factorio-data have not claimed are added.
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

@dataclass
class LintResult:
    findings: list[Finding]
    sprites: int
    icons: int
    files: int


def lint_detail(targets: list[pathlib.Path], mods: ModPaths, *, strict: bool) -> LintResult:
    """Sprites and icons from every target, checked. An icon counts as a declaration: a
    manifest holding only `icons` is not `no-sprites`, it is an icon manifest.

    Each manifest resolves against its OWN `mod_roots`; a single shared ModPaths (first
    come first served) used to resolve a second manifest's `__jamaltron__` against the
    first's directory and report its files missing (C.15, three icon candidates in one
    run; CI lints one target per run and never saw it). The CLI's --mod-root / --factorio-data
    still win over every manifest.
    """
    findings: list[Finding] = []
    sprites = icons = 0
    files: set[tuple[str, str]] = set()
    for target in targets:
        scoped = mods.copy()
        if target.suffix == ".json":
            found = specs_from_manifest(target, scoped)
            found_icons = icon_specs_from_manifest(
                json.loads(target.read_text(encoding="utf-8")), target)
        elif target.suffix == ".lua":
            found = specs_from_lua(target)
            found_icons = icon_specs_from_lua(target)
        else:
            raise ValueError(f"{target}: expected a .lua declaration or a .json manifest")
        if not found and not found_icons:
            findings.append(Finding(ERROR, "no-sprites", str(target),
                                    "no sprite or icon declarations found",
                                    ("a gate that checked nothing is worse than a red one",)))
        for spec in found:
            findings.extend(check_spec(spec, scoped, strict=strict))
        for icon in found_icons:
            findings.extend(check_icon(icon, scoped, strict=strict))
        # Keyed by the resolved root too: two manifests' `__jamaltron__/icon.png` are two files.
        root = tuple(sorted((k, str(v)) for k, v in scoped._roots.items()))
        files |= {(str(root), name) for spec in found for name in spec.filenames}
        files |= {(str(root), icon.filename) for icon in found_icons if icon.filename}
        sprites += len(found)
        icons += len(found_icons)
    return LintResult(findings, sprites, icons, len(files))


def lint(targets: list[pathlib.Path], mods: ModPaths, *, strict: bool
         ) -> tuple[list[Finding], int, int]:
    """(findings, declarations checked, files referenced). Declarations include icons."""
    result = lint_detail(targets, mods, strict=strict)
    return result.findings, result.sprites + result.icons, result.files


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
        result = lint_detail(args.targets, mods, strict=args.strict)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"lint-sprites: {exc}", file=sys.stderr)
        return 2

    if args.verbose:
        for target in args.targets:
            print(f"lint-sprites: read {target}")
    findings, files = result.findings, result.files
    declarations = result.sprites + result.icons
    errors = [f for f in findings if f.severity == ERROR]
    warnings = [f for f in findings if f.severity == WARN]
    for finding in errors + warnings:
        print(finding.render())
    tally = (f"{declarations} declaration(s), {files} file(s), "
             f"{len(errors)} error(s), {len(warnings)} warning(s)")
    if result.icons:
        tally += f" - {result.icons} of the declarations are icons"
    if errors or (warnings and args.strict):
        print(f"lint-sprites: FAILED  {tally}")
        return 1
    if not args.quiet:
        print(f"lint-sprites: PASSED  {tally}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
