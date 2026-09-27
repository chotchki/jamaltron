#!/usr/bin/env python3
"""C.21: a flop sheet is a SEQUENCE of configs, one per animation frame.

    from render import sequence
    seq = sequence.load("render/beached.toml")        # None for a config with no [sequence]
    seq.configs    # the UNIQUE per-frame configs -- one render each, per pass
    seq.order      # per played frame, which of those it shows
    seq.frame_sequence()                              # Factorio's 1-based frame_sequence

WHY A SEQUENCE AND NOT A CLIP RANGE. One animation frame is one config is one pass hash is
one cache directory; that makes a frame traceable to its knobs, and is why pack.py could not
assemble a flop (it wanted N frames in one directory). C.5's budget wants a LONG cycle of
VARIED BEATS (heave, settle, pause, snap, twitch), each a different clip, gain, bounce or
lock. A clip range cannot say that; a list of per-frame knob sets can, and every frame is
still exactly one config.

A BEAT is a run of one clip's frames with knob overrides on top of the file's own knobs:

    [[sequence.beat]]
    name = "settle"
    frames = [1, 20]              # clip frames, inclusive; default the whole clip.
                                  # [20, 1] plays it BACKWARDS -- and costs nothing if the
                                  # forward frames are already in the sheet
    stride = 1                    # every Nth clip frame
    hold = 1                      # each rendered frame plays this many times
    set = { "model.action" = "SWIM_MEDIUM", "bounce.height" = 0.0 }
    ramp = { "model.pose_gain" = [1.0, 0.4] }     # linear across the beat's frames

WHICH LAYERS SHIP is the [sequence] table's `passes` (default body, mask, shadow). The
beached flop ships body + shadow: his harness broke off with his legs (chotchki 2026-09-26),
so no tint mask is rendered, packed or promoted for it.

REPEATS ARE FREE, which makes a long varied cycle affordable. Frames whose configs hash the
same are ONE render and ONE sheet cell; the play order is Factorio's `frame_sequence`
(1-based, max 255 played frames, a frame referenced twice loads into VRAM once -- see
AnimationFrameSequence in the prototype docs). A held pause costs one cell; a beat that
comes back later costs nothing.

Pure arithmetic over artconfig, no Blender and no Pillow. art.py renders this expansion and
pack.py packs it -- the SAME expansion, so the frames the preview plays are the frames the
sheet holds.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass

# sys.path, verbatim per tools/README.md -- Python and Blender both put THIS file's own
# directory on sys.path[0], never tools/, and `package = false` means there is no installed
# `render` to fall back on.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from render import artconfig as ac  # noqa: E402
from render import pose  # noqa: E402

#: Factorio's cap on an animation's PLAYED length (AnimationFrameSequence, 2.1.17 docs):
#: "There is a limit for (actual) animation length of 255 frames."
MAX_PLAYED = 255

#: Every key a [sequence] table and a beat may carry. Anything else is a typo, and a typo'd
#: key silently doing nothing is what artconfig exists to prevent.
SEQUENCE_KEYS = ("name", "direction", "passes", "beat")

#: The render passes a sequence sheet CAN ship, in pack order, and the default when the
#: table names none: body, runtime-tint mask, shadow (the standing layers). A `passes` list
#: picks a subset; `body` is never optional. Dropping a pass is config-level, not a knob: no
#: pass hash moves, so the cache still serves the passes that stay, and art.py never
#: launches Blender for the dropped one.
PASSES = ("body", "mask", "shadow")
BEAT_KEYS = ("name", "frames", "stride", "hold", "set", "ramp")

#: Ramped values are rounded to this many places so a ramp that lands on a value another
#: beat uses exactly (0.4 and 0.4000000001) dedupes into one render instead of two.
RAMP_PLACES = 4


@dataclass(frozen=True)
class Beat:
    """One beat as written, validated. `frames` is the clip frames it renders, in order."""

    name: str
    frames: tuple
    hold: int
    sets: dict
    ramps: dict


@dataclass(frozen=True)
class Sequence:
    """A validated, expanded sequence. `configs[order[i]]` is played frame i."""

    name: str
    direction: int
    beats: tuple
    configs: tuple
    order: tuple
    #: (beat name, clip frame) per PLAYED frame, for labels and logs.
    played: tuple
    #: The file's own resolved knobs, which every beat starts from.
    base: dict
    #: The render passes this sheet ships (a subset of PASSES, in PASSES order). art.py
    #: renders only these and pack.py packs only these.
    passes: tuple = PASSES

    @property
    def hashes(self) -> tuple:
        return tuple(ac.config_hash(c) for c in self.configs)

    @property
    def digest(self) -> str:
        """One id for the whole sheet: the direction, every unique frame's config hash and the
        order they play in. Moves if ANY frame's knobs move, or the order does."""
        blob = json.dumps([self.name, self.direction, list(self.hashes), list(self.order)])
        return hashlib.sha256(blob.encode()).hexdigest()[:12]

    def frame_sequence(self):
        """Factorio's 1-based frame_sequence, or None when the sheet plays straight through
        (no repeats, no holds) -- in which case frame_count alone says it."""
        if list(self.order) == list(range(len(self.configs))):
            return None
        return [i + 1 for i in self.order]

    def seconds(self) -> float:
        return len(self.order) / pose.FPS

    def provenance(self, samples: dict | None = None) -> dict:
        """Everything that made a sequence sheet, for its PNG stamp and manifest. No ONE
        config is behind a sequence, so: the base knobs every beat starts from, each beat's
        overrides, every frame's config hash (each has its full sidecar in its cache dir)
        and the play order."""
        return {"name": self.name, "digest": self.digest, "direction": self.direction,
                "passes": list(self.passes),
                "fps": pose.FPS, "played": len(self.order), "unique": len(self.configs),
                "samples": samples or {}, "frame_hashes": list(self.hashes),
                "order": list(self.order),
                "beats": [{"name": b.name, "frames": list(b.frames), "hold": b.hold,
                           "set": b.sets, "ramp": {k: list(v) for k, v in b.ramps.items()}}
                          for b in self.beats],
                "base_config": ac.unflatten(ac.redacted(self.base))}


def _int(where: str, value, lo: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < lo:
        raise ac.ConfigError(f"{where}: expected an integer >= {lo}, got {value!r}")
    return value


def _beat(where: str, raw: dict, base: dict) -> tuple:
    """(Beat, [resolved config per rendered frame]) for one [[sequence.beat]]."""
    if not isinstance(raw, dict):
        raise ac.ConfigError(f"{where}: a beat is a table, got {raw!r}")
    unknown = sorted(set(raw) - set(BEAT_KEYS))
    if unknown:
        raise ac.ConfigError(f"{where}: unknown key(s) {', '.join(unknown)}; a beat takes "
                             f"{', '.join(BEAT_KEYS)}")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ac.ConfigError(f"{where}: every beat needs a name")
    where = f"{where} ({name})"
    for field in ("set", "ramp"):
        if not isinstance(raw.get(field, {}), dict):
            raise ac.ConfigError(f"{where}: `{field}` is a table of knob = value, got "
                                 f"{raw[field]!r}")
    sets = ac.flatten(raw.get("set") or {})
    for key in sets:
        if key not in ac.SCHEMA:
            raise ac.ConfigError(f"{where}: unknown knob {key!r} in set{ac.suggest(key)}")
    for key in ("model.frame",):
        if key in sets:
            raise ac.ConfigError(f"{where}: set {key} through `frames`, not `set`")
    ramps = ac.flatten(raw.get("ramp") or {})
    for key, ends in ramps.items():
        spec = ac.SCHEMA.get(key)
        if spec is None:
            raise ac.ConfigError(f"{where}: unknown knob {key!r} in ramp{ac.suggest(key)}")
        if spec[0] is not float:
            raise ac.ConfigError(f"{where}: ramp {key} is not a number knob; only float "
                                 f"knobs ramp")
        if (not isinstance(ends, list) or len(ends) != 2
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                           for v in ends)):
            raise ac.ConfigError(f"{where}: ramp {key} wants [start, end], got {ends!r}")
        if key in sets:
            raise ac.ConfigError(f"{where}: {key} is both set and ramped")
    try:
        beat_cfg = ac.resolve(base, sets, env={})
    except ac.ConfigError as exc:
        raise ac.ConfigError(f"{where}: {exc}") from None

    clip = pose.clip_of(beat_cfg["model.action"])
    lo, hi = (clip.lo, clip.hi) if clip else (1, 1)
    frames = raw.get("frames", [lo, hi])
    if (not isinstance(frames, list) or len(frames) != 2
            or not all(isinstance(f, int) and not isinstance(f, bool) for f in frames)):
        raise ac.ConfigError(f"{where}: frames wants [first, last], got {frames!r}")
    first, last = frames
    if not (lo <= min(first, last) and max(first, last) <= hi):
        # NOT clamped: a clamp plays a frame nobody wrote down. The renderer's clamp is for
        # a slider; a sequence is a file somebody typed.
        raise ac.ConfigError(f"{where}: frames {frames} are outside %s's %d-%d"
                             % (beat_cfg["model.action"], lo, hi))
    stride = _int(f"{where} stride", raw.get("stride", 1))
    hold = _int(f"{where} hold", raw.get("hold", 1))
    # Backwards is a first frame after the last. A one-shot clip that does not return to its
    # start (BITE_01 ends with the head still turned) gets its way back free: every frame
    # of the return is a config the forward half already rendered.
    step = stride if last >= first else -stride
    clip_frames = tuple(range(first, last + step // abs(step), step))

    out = []
    n = len(clip_frames)
    for i, f in enumerate(clip_frames):
        per = dict(sets)
        per["model.frame"] = f
        for key, (a, b) in ramps.items():
            t = i / (n - 1) if n > 1 else 0.0
            per[key] = round(a + (b - a) * t, RAMP_PLACES)
        out.append(ac.resolve(base, per, env={}))
    return Beat(name, clip_frames, hold, sets, {k: tuple(v) for k, v in ramps.items()}), out


def parse(table: dict, base: dict) -> Sequence:
    """A raw [sequence] table + the file's own resolved knobs -> a Sequence. Raises
    ConfigError, naming the beat, for anything it will not render."""
    if not isinstance(table, dict):
        raise ac.ConfigError(f"[sequence] must be a table, got {table!r}")
    unknown = sorted(set(table) - set(SEQUENCE_KEYS))
    if unknown:
        raise ac.ConfigError(f"[sequence]: unknown key(s) {', '.join(unknown)}; it takes "
                             f"{', '.join(SEQUENCE_KEYS)}")
    name = table.get("name")
    if not isinstance(name, str) or not name.replace("-", "").isalnum():
        raise ac.ConfigError(f"[sequence] name must be a plain word (it names the sheets), "
                             f"got {name!r}")
    direction = table.get("direction")
    if (isinstance(direction, bool) or not isinstance(direction, int)
            or not 0 <= direction < base["rotations.count"]):
        raise ac.ConfigError(f"[sequence] direction must be a wheel index 0..%d, got %r"
                             % (base["rotations.count"] - 1, direction))
    passes = _passes(table.get("passes", list(PASSES)))
    raws = table.get("beat")
    if not isinstance(raws, list) or not raws:
        raise ac.ConfigError("[sequence] needs at least one [[sequence.beat]]")

    beats, configs, order, played, index = [], [], [], [], {}
    for n, raw in enumerate(raws):
        beat, cfgs = _beat(f"[[sequence.beat]] #{n + 1}", raw, base)
        beats.append(beat)
        for f, cfg in zip(beat.frames, cfgs):
            key = ac.config_hash(cfg)
            if key not in index:
                index[key] = len(configs)
                configs.append(cfg)
            order.extend([index[key]] * beat.hold)
            played.extend([(beat.name, f)] * beat.hold)
    if len(order) > MAX_PLAYED:
        raise ac.ConfigError(f"[sequence] plays {len(order)} frames; Factorio caps an "
                             f"animation at {MAX_PLAYED}")
    return Sequence(name, direction, tuple(beats), tuple(configs), tuple(order),
                    tuple(played), dict(base), passes)


def _passes(raw) -> tuple:
    """A [sequence] `passes` list -> the passes it ships, in PASSES order."""
    if (not isinstance(raw, list) or not raw
            or not all(isinstance(p, str) for p in raw)):
        raise ac.ConfigError(f"[sequence] passes wants a list of pass names out of "
                             f"{', '.join(PASSES)}, got {raw!r}")
    unknown = sorted(set(raw) - set(PASSES))
    if unknown:
        raise ac.ConfigError(f"[sequence] passes: unknown pass(es) {', '.join(unknown)}; a "
                             f"sequence ships {', '.join(PASSES)}")
    if len(set(raw)) != len(raw):
        raise ac.ConfigError(f"[sequence] passes names a pass twice: {raw!r}")
    if "body" not in raw:
        raise ac.ConfigError("[sequence] passes must include body -- a sheet with no body "
                             "draws nothing")
    return tuple(p for p in PASSES if p in raw)


def load(path=None, overrides: dict | None = None):
    """The Sequence a config file carries (or inherits), or None when it has none.

    `overrides` are --set knobs: they land under every beat, so a beat that sets the same
    key still wins -- the file's beat list is the more specific statement.
    """
    table = ac.load_sequence(path)
    if table is None:
        return None
    return parse(table, ac.load(path, overrides))


def describe(seq: Sequence) -> list:
    """The sequence as report lines: one per beat, then the totals."""
    lines = []
    at = 0
    for beat in seq.beats:
        n = len(beat.frames) * beat.hold
        what = " ".join("%s=%s" % (k, v) for k, v in sorted(beat.sets.items()))
        ramp = " ".join("%s %s->%s" % (k, a, b) for k, (a, b) in sorted(beat.ramps.items()))
        step = beat.frames[1] - beat.frames[0] if len(beat.frames) > 1 else 1
        lines.append("  %-8s played %3d-%-3d  clip f%d-%d%s%s  %s %s"
                     % (beat.name, at + 1, at + n, beat.frames[0], beat.frames[-1],
                        " stride %d" % abs(step) if abs(step) > 1 else "",
                        " hold %d" % beat.hold if beat.hold > 1 else "", what, ramp))
        at += n
    lines.append("  %d played frames (%.2f s at %d fps), %d unique -> %d renders per pass "
                 "(%s), direction %d (%s)"
                 % (len(seq.order), seq.seconds(), pose.FPS, len(seq.configs),
                    len(seq.configs), " + ".join(seq.passes), seq.direction,
                    ac.compass(seq.direction, seq.configs[0]["rotations.count"])))
    return lines
