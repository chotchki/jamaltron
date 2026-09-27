#!/usr/bin/env python3
"""B.5: character/lines.md -> scripts/lines.lua + locale/en/jamaltron-lines.cfg.

    uv run --directory tools python gen_lines.py            # write both files
    uv run --directory tools python gen_lines.py --check    # exit 1 if either is stale

THE CATALOG IS THE SINGLE SOURCE, and this is the only thing allowed to turn it into something
the mod reads. It parses the machine contract the catalog documents in its "How to read the
table" section (each `## <event>` section carries a `**key:**` line, a `**split:**` line and ONE
twelve-column table), validates all of it, and emits two files that say GENERATED on line 1.

TWO FILES, ONE KEY BETWEEN THEM. The locale file holds every string, one key per ID and NO
dedup (the catalog's ruling: ID is for the locale, GRP is for the picker, and a reused line
stays free to diverge per pool later). The Lua file holds everything the picker needs and no
strings: weights, tiers, channels, the SUB each row answers to, the once-per-save gate, the
chains with their delays and the anti-repeat group. D.5 renders a row as the LocalisedString
{"jamaltron-line.<id>", count}.

THE LOCALE FILE IS ITS OWN FILE, not locale/en/jamaltron.cfg as PLAN B.5's one-liner says.
That one is hand-written (entity, item and setting names; its header says the speech lines
"land in their own file"), and a generator owning half a file would eat the other half on its
first run. Factorio loads every .cfg in locale/en/.

DOTTED KEYS ARE FINE, MEASURED because base Factorio ships none: a throwaway mod on 2.1 logged
{"x.idle.01"} as its string, {"x.legs_break.17", 3} with the count substituted, and an unknown
key as `Unknown key: "..."`. So `jamaltron-line.<id>` ships exactly as the catalog writes it.

REFUSES, loudly and all at once (stopping at the first problem turns one pass of fixes into ten):
  * a table row that is not twelve cells, a missing cell, an unknown CH / SOURCE / TIER /
    GATE value, a non-integer weight, a duplicate ID or an ID outside its section's keys
  * a SUB its section's `split:` line does not name. The split line is the WHOLE SUB contract:
    `none` makes SUB advisory (dropped), `required` makes every row pick a listed side,
    `gated` makes `-` and `any` the same always-eligible value
  * a CHAIN that is not `-`, `tail`, `tail-only` or `<id>@<ticks>`; a head whose target is
    missing, in another pool or not marked as a tail; a tail no head names; a head in a pool
    whose own event cancels it (the swaps legs_break and repaired, and died); a delay that is
    not the catalog's formula applied to the head
  * a GRP that is not the ID of the first row carrying the same string (COMPUTED; this only
    checks the column agrees)
  * any token but {N}; an ASCII apostrophe in a Line (the ruled glyph is U+2019); a SPEECH
    line over the 60-character bubble cap with {N} at three digits, except the two rows B.4
    Q8 ruled stay long until a real bubble is measured
  * when character/extracts/ is present: a `verbatim` Line, or a quote behind `ORIGINAL:` or
    `TRIMMED (...) of` in a Note, that is not an exact substring of its book. The catalog rules
    a miss a FABRICATION, deleted not fixed, so generation stops. The extracts are gitignored,
    so CI cannot run this half and says so instead of passing
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import re
import sys

TOOLS = pathlib.Path(__file__).resolve().parent
REPO = TOOLS.parent
CATALOG = REPO / "character" / "lines.md"
EXTRACTS = REPO / "character" / "extracts"
MOD = REPO / "mod" / "jamaltron"
LUA_OUT = MOD / "scripts" / "lines.lua"
CFG_OUT = MOD / "locale" / "en" / "jamaltron-lines.cfg"

#: The twelve columns, in the catalog's order. The header row must be exactly this.
COLUMNS = ("ID", "Line", "CH", "SOURCE", "BK", "W", "TIER", "SUB", "GATE", "CHAIN", "GRP",
           "Note")
CHANNELS = ("speech", "narration")
SOURCES = ("verbatim", "adapted", "original")
#: Cumulative, lowest first: a `normal` player hears quiet + normal.
TIERS = ("quiet", "normal", "unbearable")
GATES = ("-", "once_per_save")

LOCALE_SECTION = "jamaltron-line"
#: The only surviving token. The catalog substitutes it; Factorio spells the parameter __1__.
TOKEN_N = "{N}"
LOCALE_N = "__1__"
#: {N} is the entity's cumulative leg-break count; the cap is measured at three digits.
N_WORST = "999"

#: Speech-bubble width, measured on the shipping string. Narration renders outside a bubble.
BUBBLE_CAP = 60
#: B.4 Q8: over the cap and deliberately NOT trimmed until chotchki measures a real bubble.
#: The ruling is about THESE strings at THESE lengths, not a free pass for the ids: a rewrite
#: is a new line (the catalog's rule) and gets the cap like any other.
OVER_CAP_RULED = {"flopping.38": 61, "jump_refused.19": 64}

#: Pools whose event IS a swap to or from jamaltron-beached. A swap cancels pending chains,
#: so a chain headed here could never deliver (the catalog's reachability rule).
SWAP_POOLS = ("legs_break", "repaired")
#: Every pool a chain cannot be headed in: the swaps plus `died` (the locked semantics cancel a
#: pending follow-up on death, and died IS the death). The catalog states the rule for swaps;
#: death is the same cancel, derived not invented.
NO_CHAIN_POOLS = SWAP_POOLS + ("died",)

#: Lua's reserved words: a pool key becomes a bare identifier in the emitted table.
LUA_KEYWORDS = frozenset("and break do else elseif end false for function goto if in local "
                         "nil not or repeat return then true until while".split())

#: The one ordered repeat the anti-repeat mechanism must never learn to suppress (B.4 Q13).
ALLOW_REPEAT = (("idle.01", "idle.02"),)

ID_RE = re.compile(r"^([a-z_]+)\.(\d+)$")
HEAD_RE = re.compile(r"^([a-z_]+\.\d+)@(\d+)$")
QUOTE_RE = re.compile(r'(?:ORIGINAL:|TRIMMED \([^)]*\) of)\s*"([^"]+)"')
ORIGINAL_RE = re.compile(r'ORIGINAL:\s*"([^"]+)"')
TRIM_RE = re.compile(r'TRIMMED \([^)]*\) of\s*"([^"]+)"')
#: Straight double quotes in a Note MEAN PROVENANCE AND NOTHING ELSE (the catalog's rule), so
#: every one of them is a book string the checker validates.
STRAIGHT_RE = re.compile(r'"([^"]+)"')
KEY_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
TOKEN_RE = re.compile(r"\{[^}]*\}")
TICK_LIST = re.compile(r"`([^`]+)`")


class CatalogError(ValueError):
    """Everything wrong with the catalog, one problem per line."""


@dataclasses.dataclass
class Row:
    id: str
    line: str
    ch: str
    source: str
    bk: str
    w: int
    tier: str
    sub: str
    gate: str
    chain: str
    grp: str
    note: str
    lineno: int


@dataclasses.dataclass
class Section:
    title: str
    keys: list
    split: str                  # none | required | gated
    dimension: str | None
    values: list
    rows: list
    lineno: int


# ------------------------------------------------------------------------------ parsing


def _values(text: str) -> list:
    return [v.strip() for v in TICK_LIST.findall(text)]


def parse_split(text: str, lineno: int, errors: list):
    """`none ...` | `required — `a` | `b`...` | `gated — `dim`: `a` | `b`...`."""
    text = text.strip()
    if re.match(r"^none\b", text):
        return "none", None, []
    m = re.match(r"^required\s+—\s+((?:`[^`]+`\s*\|\s*)*`[^`]+`)", text)
    if m:
        return "required", None, _values(m.group(1))
    m = re.match(r"^gated\s+—\s+`([^`]+)`:\s*((?:`[^`]+`\s*\|\s*)*`[^`]+`)", text)
    if m:
        return "gated", m.group(1), _values(m.group(2))
    errors.append("line %d: split line is not none / required / gated: %r" % (lineno, text[:80]))
    return "none", None, []


def parse(text: str) -> list:
    """Every pool section in the catalog, validated only as far as its SHAPE. Raises
    CatalogError with every shape problem found. build() uses parse_collect() instead, so
    shape and contract problems come back together."""
    sections, errors = parse_collect(text)
    if errors:
        raise CatalogError("\n".join(errors))
    return sections


def parse_collect(text: str):
    """(sections, shape errors) -- everything that parsed, and everything that did not.

    Splits on \\n ONLY. str.splitlines() also breaks on U+2028, U+0085 and form feed, so a
    cell carrying one would be cut in half and the second half silently dropped."""
    errors, sections = [], []
    current = None
    lines = [line.rstrip("\r") for line in text.split("\n")]
    for n, raw in enumerate(lines, 1):
        if raw.startswith("## "):
            current = {"title": raw[3:].strip(), "lineno": n, "keys": None, "split": None,
                       "header": False, "rows": []}
            sections.append(current)
            continue
        if current is None:
            continue
        if raw.startswith("**key:**"):
            head = raw[len("**key:**"):].split(" — ", 1)[0]
            current["keys"] = _values(head)
        elif raw.startswith("**split:**"):
            current["split"] = (raw[len("**split:**"):], n)
        elif raw.startswith("| ID |"):
            cells = [c.strip() for c in raw.strip().strip("|").split("|")]
            if tuple(cells) != COLUMNS:
                errors.append("line %d: table header is %s, want %s" % (n, cells, list(COLUMNS)))
            current["header"] = True
        elif current["header"] and raw.lstrip().startswith("|") \
                and not raw.lstrip().startswith("|---"):
            cells = [c.strip() for c in raw.strip().strip("|").split("|")]
            if len(cells) != len(COLUMNS):
                errors.append("line %d: %d cells, want %d: %s" % (n, len(cells), len(COLUMNS),
                                                                   raw[:60]))
                continue
            current["rows"].append((n, cells))
        elif current["header"] and not raw.lstrip().startswith("|"):
            current["header"] = False       # the table ended; prose follows
            current["ended"] = n
        elif not current["header"] and current.get("ended") \
                and re.match(r"^\s*\|\s*[a-z_]+\.\d+\s*\|", raw):
            # A row AFTER its table ended (a blank or indented line broke the table). Markdown
            # may still render it; without this the parser would drop it silently.
            errors.append("line %d: a line row after the table ended at line %d (a blank or "
                          "non-table line splits the table): %s" % (n, current["ended"], raw[:60]))
    out = []
    for s in sections:
        if s["keys"] is None:
            if s["rows"]:
                errors.append("line %d: section %r has a line table but no **key:** line"
                              % (s["lineno"], s["title"]))
            continue                        # header prose, coverage summary, rulings
        if s["split"] is None:
            errors.append("line %d: section %r has no **split:** line" % (s["lineno"], s["title"]))
            continue
        if not s["rows"]:
            errors.append("line %d: section %r has no rows" % (s["lineno"], s["title"]))
            continue
        kind, dim, values = parse_split(s["split"][0], s["split"][1], errors)
        rows = []
        for n, c in s["rows"]:
            # Every FUNCTIONAL cell must be filled. Note is commentary and 14 rows have none;
            # requiring one would be this generator inventing a rule the catalog never made.
            missing = [COLUMNS[i] for i, v in enumerate(c) if v == "" and COLUMNS[i] != "Note"]
            if missing:
                errors.append("line %d: %s has empty %s" % (n, c[0] or "?", ", ".join(missing)))
                continue
            try:
                w = int(c[5])
            except ValueError:
                errors.append("line %d: %s weight %r is not an integer" % (n, c[0], c[5]))
                continue
            rows.append(Row(id=c[0], line=c[1], ch=c[2], source=c[3], bk=c[4], w=w, tier=c[6],
                            sub=c[7], gate=c[8], chain=c[9], grp=c[10], note=c[11], lineno=n))
        out.append(Section(title=s["title"], keys=s["keys"], split=kind, dimension=dim,
                           values=values, rows=rows, lineno=s["lineno"]))
    return out, errors


# ---------------------------------------------------------------------------- validation


def chain_delay(head_line: str) -> int:
    """The catalog's formula, recomputed rather than trusted: 3.5 ticks per character of the
    HEAD's string, rounded to the nearest 30 (halves up), floor 60."""
    return max(60, int((3.5 * len(head_line) + 15) // 30) * 30)


def shipped_length(line: str) -> int:
    """Width of the string as it renders at its widest -- {N} at three digits."""
    return len(line.replace(TOKEN_N, N_WORST))


def validate(sections: list) -> list:
    """Every contract problem across the whole catalog, as one list of messages."""
    errors = []
    by_id, first_with, key_home = {}, {}, {}
    for s in sections:
        for key in s.keys:
            if not KEY_RE.match(key) or key in LUA_KEYWORDS:
                errors.append("line %d: pool key %r cannot be a bare Lua identifier"
                              % (s.lineno, key))
            if key in key_home:
                errors.append("line %d: pool key %r is already the key of section %r"
                              % (s.lineno, key, key_home[key]))
            key_home[key] = s.title
    for s in sections:
        for r in s.rows:
            if r.id in by_id:
                errors.append("line %d: duplicate ID %s (first at line %d)"
                              % (r.lineno, r.id, by_id[r.id][1].lineno))
            by_id[r.id] = (s, r)
            first_with.setdefault(r.line, r.id)
    for s in sections:
        partitioned = s.split == "required" and sorted(s.values) == sorted(s.keys)
        for r in s.rows:
            where = "line %d: %s" % (r.lineno, r.id)
            m = ID_RE.match(r.id)
            if not m or m.group(1) not in s.keys:
                errors.append("%s is not <key>.<nn> for this section's keys %s" % (where, s.keys))
            if r.ch not in CHANNELS:
                errors.append("%s CH %r not in %s" % (where, r.ch, CHANNELS))
            if r.source not in SOURCES:
                errors.append("%s SOURCE %r not in %s" % (where, r.source, SOURCES))
            if r.source == "original" and r.bk != "-":
                errors.append("%s is original but BK is %r, want -" % (where, r.bk))
            if r.source != "original" and r.bk not in ("7", "8"):
                errors.append("%s is %s but BK is %r, want 7 or 8" % (where, r.source, r.bk))
            if r.w <= 0:
                errors.append("%s weight %d is not positive" % (where, r.w))
            if r.tier not in TIERS:
                errors.append("%s TIER %r not in %s" % (where, r.tier, TIERS))
            if r.gate not in GATES:
                errors.append("%s GATE %r not in %s" % (where, r.gate, GATES))
            if s.split == "required" and r.sub not in s.values:
                errors.append("%s SUB %r is not a side of this required split %s"
                              % (where, r.sub, s.values))
            if partitioned and m and r.sub != m.group(1):
                errors.append("%s SUB %r does not match its own pool %s" % (where, r.sub,
                                                                             m.group(1)))
            if s.split == "gated" and r.sub not in set(s.values) | {"-", "any"}:
                errors.append("%s SUB %r is not a %s value %s" % (where, r.sub, s.dimension,
                                                                  s.values))
            if r.grp != first_with[r.line]:
                errors.append("%s GRP %r, but the first row with this Line is %s"
                              % (where, r.grp, first_with[r.line]))
            tokens = set(TOKEN_RE.findall(r.line)) - {TOKEN_N}
            if tokens:
                errors.append("%s carries token(s) %s; {N} is the only one" % (where,
                                                                               sorted(tokens)))
            if "'" in r.line:
                errors.append("%s has an ASCII apostrophe; the ruled glyph is U+2019" % where)
            # Factorio's locale layer REWRITES these (MEASURED): a literal backslash-n becomes a
            # newline and __WORD__...__ is a macro. The Line is "the string, exactly as it should
            # render", so neither may reach the cfg. {N} becomes __1__ AFTER this check.
            if "\\" in r.line or "__" in r.line:
                errors.append("%s carries a backslash or `__`, which Factorio's locale layer "
                              "rewrites" % where)
            if r.ch == "speech" and shipped_length(r.line) > BUBBLE_CAP:
                ruled = OVER_CAP_RULED.get(r.id)
                if ruled is None or shipped_length(r.line) > ruled:
                    errors.append("%s is %d characters over the %d bubble cap%s"
                                  % (where, shipped_length(r.line) - BUBBLE_CAP, BUBBLE_CAP,
                                     "" if ruled is None else
                                     " and longer than the %d B.4 Q8 ruled on" % ruled))
            if r.source == "adapted" and not ORIGINAL_RE.search(r.note):
                errors.append("%s is `adapted` with no ORIGINAL: \"...\" in its Note -- the "
                              "marker is the machine contract its provenance rests on" % where)
            for trim in TRIM_RE.findall(r.note):
                if r.source == "verbatim" and r.line not in trim:
                    errors.append("%s's Line is not inside the full quote its TRIMMED note "
                                  "names -- every trim is a contiguous substring" % where)
            if r.bk == "-" and STRAIGHT_RE.search(r.note):
                errors.append("%s is original (BK -) but its Note carries a straight-quoted "
                              "string, which the catalog reserves for book provenance" % where)
    # chains: grammar, targets, one hop, reachability, delay
    named = {}
    for s in sections:
        for r in s.rows:
            where = "line %d: %s" % (r.lineno, r.id)
            if r.chain in ("-", "tail", "tail-only"):
                continue
            m = HEAD_RE.match(r.chain)
            if not m:
                errors.append("%s CHAIN %r is not -, tail, tail-only or <id>@<ticks>"
                              % (where, r.chain))
                continue
            target, delay = m.group(1), int(m.group(2))
            if target not in by_id:
                errors.append("%s chains to %s, which does not exist" % (where, target))
                continue
            ts, tr = by_id[target]
            head_pool = ID_RE.match(r.id).group(1) if ID_RE.match(r.id) else None
            if ts is not s or ID_RE.match(target).group(1) != head_pool:
                errors.append("%s chains to %s in another pool; a chain stays in its pool"
                              % (where, target))
            if tr.chain not in ("tail", "tail-only"):
                errors.append("%s chains to %s, whose CHAIN is %r, not tail / tail-only"
                              % (where, target, tr.chain))
            if head_pool in NO_CHAIN_POOLS:
                errors.append("%s heads a chain in %s, whose own event cancels it before it "
                              "can land (a swap, or the death)" % (where, head_pool))
            if delay != chain_delay(r.line):
                errors.append("%s delay %d is not the formula's %d for a %d-character head"
                              % (where, delay, chain_delay(r.line), len(r.line)))
            named.setdefault(target, r.id)
    for s in sections:
        for r in s.rows:
            if r.chain in ("tail", "tail-only") and r.id not in named:
                errors.append("line %d: %s is %s but no head names it" % (r.lineno, r.id,
                                                                          r.chain))
    for pair in ALLOW_REPEAT:
        for rid in pair:
            if rid not in by_id:
                errors.append("allow-repeat pair %s names %s, which does not exist" % (pair, rid))
    for rid in OVER_CAP_RULED:
        if rid not in by_id:
            errors.append("OVER_CAP_RULED names %s, which does not exist" % rid)
    return errors


def verify_extracts(sections: list, extracts: pathlib.Path) -> list:
    """The catalog's fidelity rule: every verbatim Line, and every book quote a Note stands
    behind, is an exact substring of that book's extract. [] when all hold."""
    books, errors = {}, []
    for bk in ("7", "8"):
        path = extracts / ("book%s_jamal.txt" % bk)
        if not path.is_file():
            return ["%s is missing while the other extract is present -- a half-unpacked "
                    "extracts directory checks nothing honestly" % path]
        books[bk] = path.read_text(encoding="utf-8")
    for s in sections:
        for r in s.rows:
            if r.bk not in books:
                continue
            text = books[r.bk]
            if r.source == "verbatim" and r.line not in text:
                errors.append("line %d: %s is `verbatim` and NOT in book %s -- a fabrication: "
                              "%r" % (r.lineno, r.id, r.bk, r.line))
            for quote in STRAIGHT_RE.findall(r.note):
                if quote not in text:
                    errors.append("line %d: %s's Note quotes %r, which is NOT in book %s"
                                  % (r.lineno, r.id, quote, r.bk))
    return errors


# ------------------------------------------------------------------------------- emitting


def pools(sections: list) -> list:
    """(pool key, section, split, dimension, values, rows) in catalog order. A `required`
    split whose sides ARE the section's keys (enter/exit) is two pools; any other section is
    one."""
    out = []
    for s in sections:
        if s.split == "required" and sorted(s.values) == sorted(s.keys):
            for key in s.keys:
                rows = [r for r in s.rows if ID_RE.match(r.id).group(1) == key]
                out.append((key, s, "none", None, [], rows))
        else:
            out.append((s.keys[0], s, s.split, s.dimension, s.values, s.rows))
    return out


def _lua_str(v: str) -> str:
    return '"%s"' % v.replace("\\", "\\\\").replace('"', '\\"')


def _lua_list(values) -> str:
    return "{" + ", ".join(_lua_str(v) for v in values) + "}"


#: .luacheckrc's max_line_length. Generated code is still code CI lints.
LUA_WIDTH = 120


def lua_row(r: Row, split: str, indent: str = "        ") -> str:
    """One row table, wrapped at LUA_WIDTH on field boundaries -- a chained, gated, counted
    row carries enough fields to cross it, and luacheck fails the file."""
    fields = ["id = %s" % _lua_str(r.id), "grp = %s" % _lua_str(r.grp),
              "ch = %s" % _lua_str(r.ch), "w = %d" % r.w, "tier = %s" % _lua_str(r.tier)]
    if split == "required":
        fields.append("sub = %s" % _lua_str(r.sub))
    elif split == "gated":
        fields.append("sub = %s" % _lua_str("any" if r.sub in ("-", "any") else r.sub))
    if r.gate != "-":
        fields.append("gate = %s" % _lua_str(r.gate))
    if TOKEN_N in r.line:
        fields.append("count = true")
    m = HEAD_RE.match(r.chain)
    if m:
        fields.append("follow = %s, delay = %d" % (_lua_str(m.group(1)), chain_delay(r.line)))
    elif r.chain == "tail":
        fields.append("tail = true")
    elif r.chain == "tail-only":
        fields.append("tail_only = true")
    lines, current = [], indent + "{"
    for i, f in enumerate(fields):
        piece = f + (", " if i < len(fields) - 1 else "},")
        if len(current) + len(piece.rstrip()) > LUA_WIDTH and current.strip() != "{":
            lines.append(current.rstrip())
            current = indent + " " + piece
        else:
            current += piece
    lines.append(current)
    return "\n".join(lines)


def lua_list_wrapped(prefix: str, values: list, indent: str = "        ") -> str:
    """`<prefix>{"a", "b", ...},` wrapped at LUA_WIDTH on element boundaries -- a gated split
    that names every refusal reason crosses it, and luacheck fails the file."""
    if not values:
        return prefix + "{},"
    items = [_lua_str(v) for v in values]
    lines, current = [], prefix + "{"
    for i, item in enumerate(items):
        piece = item + (", " if i < len(items) - 1 else "},")
        if len(current) + len(piece.rstrip()) > LUA_WIDTH and not current.endswith("{"):
            lines.append(current.rstrip())
            current = indent + piece
        else:
            current += piece
    lines.append(current)
    return "\n".join(lines)


GENERATED = ("GENERATED by tools/gen_lines.py from character/lines.md. DO NOT EDIT -- the next "
             "run eats the edit.")


def emit_lua(sections: list) -> str:
    rows = [r for s in sections for r in s.rows]
    out = [
        "-- " + GENERATED,
        "-- Regenerate: uv run --directory tools python gen_lines.py",
        "--",
        "-- The picker's half of the catalog: no strings live here. A row renders as the",
        '-- LocalisedString {"%s.<id>"} (plus the leg-break count when `count`),' % LOCALE_SECTION,
        "-- from locale/en/jamaltron-lines.cfg. Field meanings are the catalog's columns:",
        "--   grp       anti-repeat group, per ENTITY, across pools (B.4 Q13)",
        "--   ch        speech | narration (narration renders with D.5's 'Game Note: ' prefix)",
        "--   w, tier   relative weight within the eligible set; tiers are CUMULATIVE",
        "--   sub       required split: the side; gated split: `any` or the value it needs",
        "--   gate      once_per_save: once per entity per save",
        "--   follow    chain head: schedule that row after `delay` ticks, same entity. A",
        "--             delivered follow-up INHERITS the head's tier and skips anti-repeat,",
        "--             windows and cooldown (SPEC); its own `tier` only matters when a `tail`",
        "--             rolls alone",
        "--   tail_only never rolled on its own; tail may also roll normally",
        "--   count     pass the entity's leg-break count as the string's one parameter",
        "-- Per pool: event is the catalog heading, swap marks an event that swaps entities",
        "-- (a pending chain on that entity is cancelled by it).",
        "-- %d rows, %d pools, %d chains." % (
            len(rows), len(pools(sections)), sum(1 for r in rows if HEAD_RE.match(r.chain))),
        "",
        "return {",
        "  locale_section = %s," % _lua_str(LOCALE_SECTION),
        "  tiers = %s," % _lua_list(TIERS),
        "  -- ordered pairs a near-duplicate suppressor must never block (the callback gag)",
        "  allow_repeat = {%s}," % ", ".join(_lua_list(p) for p in ALLOW_REPEAT),
        "  pools = {",
    ]
    for key, s, split, dim, values, prows in pools(sections):
        out.append("    %s = {" % key)
        out.append("      event = %s," % _lua_str(s.title))
        out.append("      split = %s," % _lua_str(split))
        if split == "required":
            out.append("      sides = %s," % _lua_list(values))
        if split == "gated":
            out.append("      dimension = %s," % _lua_str(dim))
            out.append(lua_list_wrapped("      values = ", [v for v in values
                                                        if v not in ("-", "any")]))
        out.append("      swap = %s," % ("true" if key in SWAP_POOLS else "false"))
        out.append("      rows = {")
        for r in prows:
            out.append(lua_row(r, split))
        out.append("      },")
        out.append("    },")
    out += ["  },", "}", ""]
    return "\n".join(out)


def emit_cfg(sections: list) -> str:
    out = ["# " + GENERATED,
           "# One key per ID, NO dedup (the catalog's ruling). {N} is __1__, the leg-break count.",
           "", "[%s]" % LOCALE_SECTION]
    for s in sections:
        for r in s.rows:
            out.append("%s=%s" % (r.id, r.line.replace(TOKEN_N, LOCALE_N)))
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------------- main


def report(sections: list) -> list:
    rows = [r for s in sections for r in s.rows]
    strings = {}
    for r in rows:
        strings.setdefault(r.line, set()).add(ID_RE.match(r.id).group(1))
    multi = [line for line, pl in strings.items() if len(pl) > 1]
    narr = [r for r in rows if r.ch == "narration"]
    speech = [r for r in rows if r.ch == "speech"]
    longest = max(speech, key=lambda r: shipped_length(r.line)) if speech else None
    ruled = {r.id: shipped_length(r.line) for r in rows if r.id in OVER_CAP_RULED}
    widest = max((len(r.line) for r in narr), default=0)
    return [
        "%d rows in %d pools: %d speech, %d narration" % (
            len(rows), len(pools(sections)), len(rows) - len(narr), len(narr)),
        "%d distinct strings, %d of them in more than one pool (%d rows)" % (
            len(strings), len(multi), sum(1 for r in rows if r.line in multi)),
        "%d chains (%d tail, %d tail-only), %d once_per_save rows, %d rows carry {N}" % (
            sum(1 for r in rows if HEAD_RE.match(r.chain)),
            sum(1 for r in rows if r.chain == "tail"),
            sum(1 for r in rows if r.chain == "tail-only"),
            sum(1 for r in rows if r.gate == "once_per_save"),
            sum(1 for r in rows if TOKEN_N in r.line)),
        "longest speech %s at %d (cap %d; over by ruling: %s)" % (
            longest.id if longest else "-", shipped_length(longest.line) if longest else 0,
            BUBBLE_CAP, ", ".join("%s %d" % kv for kv in sorted(ruled.items())) or "none"),
        "longest narration %d + 11 for 'Game Note: ' = %d" % (widest, widest + 11),
    ]


def build(text: str, extracts: pathlib.Path | None):
    """(lua, cfg, report lines, notes). Raises CatalogError on any problem."""
    sections, errors = parse_collect(text)
    errors = errors + validate(sections)
    notes = []
    if extracts is not None and any((extracts / ("book%s_jamal.txt" % bk)).is_file()
                                    for bk in ("7", "8")):
        errors += verify_extracts(sections, extracts)
        notes.append("fidelity: every verbatim Line and every Note quote checked against the "
                     "extracts")
    else:
        notes.append("fidelity NOT checked: %s is absent (gitignored; it lives on chotchki's "
                     "machine only)" % (extracts or EXTRACTS))
    if errors:
        raise CatalogError("\n".join(errors))
    return emit_lua(sections), emit_cfg(sections), report(sections), notes


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="gen_lines.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--catalog", type=pathlib.Path, default=CATALOG)
    p.add_argument("--extracts", type=pathlib.Path, default=EXTRACTS)
    p.add_argument("--check", action="store_true",
                   help="write nothing; exit 1 if either generated file is stale")
    args = p.parse_args(argv)
    try:
        lua, cfg, lines, notes = build(args.catalog.read_text(encoding="utf-8"), args.extracts)
    except CatalogError as exc:
        sys.stderr.write("gen_lines.py: the catalog does not meet its own contract:\n%s\n" % exc)
        return 1
    for line in lines + notes:
        print("  " + line)
    stale = [path for path, text in ((LUA_OUT, lua), (CFG_OUT, cfg))
             if not path.is_file() or path.read_text(encoding="utf-8") != text]
    if args.check:
        for path in stale:
            if path.is_file():
                print("  STALE %s -- run gen_lines.py" % path.relative_to(REPO))
            else:
                print("  NOT GENERATED %s -- run gen_lines.py (generating is not the id "
                      "freeze; that is PLAN F.6, after playtesting)" % path.relative_to(REPO))
        return 1 if stale else 0
    for path, text in ((LUA_OUT, lua), (CFG_OUT, cfg)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print("  wrote %s%s" % (path.relative_to(REPO), "" if path in stale else " (unchanged)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
