"""G.5: a take's logs, the cut file, and the resolver that turns them into frames.json.

A CUT IS WRITTEN IN EVENTS, NEVER TICKS. The director is event-driven (a beat starts when the
last biter dies, not at tick 4200), so the same staging drifts by a poll or two between runs
and between headless and graphics. An anchor like `takeoff#3-20` survives that; a tick does
not. The resolver reads the take's OWN events.jsonl, so a cut re-resolves against every new
take with no edits.

THE ANCHOR GRAMMAR: `<ev>[#n]` or `beat:<name>`, then an optional `+N` / `-N` in ticks.
`takeoff#3` is the third takeoff in tick order (1-based). A bare `<ev>` is allowed only when
the take has exactly ONE of it: `apex` on a take with four apexes would silently mean the
first, which is never what a cut that says `apex` wanted.

SOURCE RANGES ARE HALF-OPEN, [from, to). Consecutive segments share an anchor (`to =
"takeoff#1-20"`, next `from = "takeoff#1-20"`) and must not show that tick twice; a loop cut
`landing#1+60 -> landing#3+60` must end one tick BEFORE the state it wraps round to. A freeze
is [at, at+1); a card owns no source ticks, [backdrop, backdrop).

SPEED IS SOURCE TICKS PER 60 OUTPUT FRAMES: 0.5 shows each source frame twice, 5.0 every 5th.
Output frame k of a span shows `from + floor(k * speed)` (exact rational arithmetic, so 1/3
does not drift a frame over a long span). Frame repetition, not interpolation: G.9 is where
chotchki picks minterpolate or not, and a repeated real frame is honest.

frames.json (the contract's format, read by pump.py AND the audio builder's mix.py):
    {"fps": 60, "frames": [{"src": T|null, "seg": i}, ...],
     "segments": [{"index": i, "kind": "span|freeze|card", "speed": s, "from": T0, "to": T1,
                   "tag": str|null, "audio": "live|mute", "out": [f0, f1], "card": str|null,
                   "caption": "above|below"}],
     "overlays": [{"card": "title", "from_out": 0.0, "to_out": 3.0, "out": [f0, f1]}],
     "deliver": "master|loop", "captions": bool, "crop": [x, y, w, h]|null}
`out`, `card`, `caption`, `deliver`, `captions` and `crop` are additions a consumer may
ignore; `out` is the segment's output frames, half-open like everything else.

TWO KEYS BEYOND THE CONTRACT'S EXAMPLE (both added at the fixer pass, 2026-09-27):
  caption = "below"   on a span: the captions of lines SAID in its source range hang under his
                      feet instead of over his head (captions.py; the wave's flame and biters
                      are above him). By the tick said, so a caption never switches sides.
  crop = [x, y, w, h] top level, loop cuts only: the part of the kept 1920x1080 frame the
                      deliverables show, in 1080p pixels, 16:9 so the fixed 960x540 output
                      scales it evenly - storyboard A's "zoom 1.5, cropped to 1280x720" GIF.

Every problem in a cut file is a CutError naming the segment and the key; every problem in a
take's logs is a TakeError naming the file and the line. Nothing is guessed.
"""

from __future__ import annotations

import dataclasses
import difflib
import json
import math
import pathlib
import re
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from fractions import Fraction
from typing import Literal

#: The capture is one frame per game tick and --benchmark-graphics is locked at 60 UPS
#: (G.1, MEASURED: 360 ticks in 6.00 s with a 1080p screenshot every tick).
SOURCE_UPS = 60

#: The contract's event vocabulary. An anchor on a name outside it is a typo until proven
#: otherwise (did-you-mean); a name inside it that this take lacks is a MISSING anchor.
KNOWN_EVENTS = frozenset({
    "capture_start", "capture_end", "beat", "takeoff", "apex", "landing", "break", "thud",
    "repair", "line", "footfall", "walk_start", "walk_stop", "fire_start", "fire_stop",
    "biter_spawn", "biter_attack", "biter_died", "wave_clear", "repair_cue", "bot_out",
    "repair_start", "repair_full", "repairing", "still", "liberty",
    # Not in the contract's table; the director logs it (a row the mod rolled that a forced
    # row replaced on the same tick - in the mod's speech log, on screen for no frame).
    "said",
})

#: The body names track.jsonl carries. The airborne one is what makes a tick part of an arc.
BODIES = frozenset({"jamaltron", "jamaltron-airborne", "jamaltron-beached"})
AIRBORNE = "jamaltron-airborne"

#: The capture: 1920x1104 with the tick stamp in the bottom 24 px, which the pump crops.
#: 1104 = 1080 + 24 so the kept 1920x1080 is exactly 16:9 and the stamp never needs masking.
CAPTURE_W, CAPTURE_H, BAND = 1920, 1104, 24
OUT_H = CAPTURE_H - BAND

#: Speed bounds. Below 1/16 a "slow-mo" is a slideshow (each frame 16+ times); above 60 a
#: time-lapse drops more than a second of source per output frame.
MIN_SPEED, MAX_SPEED = Fraction(1, 16), Fraction(60)

AudioMode = Literal["live", "mute"]
Deliver = Literal["master", "loop"]
SegmentKind = Literal["span", "freeze", "card"]
CARDS = ("title", "end")


class TakeError(ValueError):
    """A take directory or one of its logs is not what the contract says."""


class CutError(ValueError):
    """A cut file, or one of its anchors against this take, is wrong. The message names it."""


# --------------------------------------------------------------------------------------------
# The take


@dataclasses.dataclass(frozen=True)
class Event:
    """One events.jsonl line. `data` is every field but tick and ev; `ordinal` is this event's
    1-based position among its own `ev` in tick order (what `takeoff#3` addresses)."""

    tick: int
    ev: str
    data: Mapping[str, object]
    ordinal: int
    line: int

    def text(self, key: str) -> str | None:
        v = self.data.get(key)
        return v if isinstance(v, str) else None

    def int_(self, key: str) -> int | None:
        v = self.data.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v):
            return None
        return int(v)


@dataclasses.dataclass(frozen=True)
class TrackLine:
    """One track.jsonl line: what the director's on_tick T read. On the ground `pos` is the
    state BEFORE update T and the frame shows the state after it, so frame T anchors on line
    T+1; in an arc jamaltron's on_tick has already moved him, so it anchors on line T (see
    captions.Anchorer)."""

    tick: int
    cam: tuple[float, float]
    zoom: float
    body: str
    pos: tuple[float, float]
    lift: tuple[float, float]


@dataclasses.dataclass(frozen=True)
class Geometry:
    """The capture's pixel size and what the pump keeps of it. Production is 1920x1104 ->
    1920x1080; a test take may be any size with the same aspect (192x110 -> 192x108), and
    every pixel quantity downstream (fonts, margins, deliverable sizes) scales by `scale`."""

    cap_w: int
    cap_h: int
    out_h: int

    @classmethod
    def from_capture(cls, w: int, h: int) -> Geometry:
        want_h = w * CAPTURE_H / CAPTURE_W
        if w < 16 or abs(h - want_h) > 1:
            raise TakeError(f"frames are {w}x{h}; the capture is {CAPTURE_W}x{CAPTURE_H} "
                            f"(or that aspect scaled: {w}x{round(want_h)})")
        out_h = round(w * OUT_H / CAPTURE_W)
        if out_h % 2 or w % 2:
            raise TakeError(f"frames are {w}x{h}: the kept {w}x{out_h} must be even both ways "
                            "for yuv420p")
        return cls(w, h, out_h)

    @property
    def scale(self) -> float:
        return self.cap_w / CAPTURE_W

    @property
    def band(self) -> int:
        return self.cap_h - self.out_h

    @property
    def out_size(self) -> tuple[int, int]:
        return self.cap_w, self.out_h

    def to_screen(self, world: tuple[float, float], cam: tuple[float, float],
                  zoom: float) -> tuple[float, float]:
        """World tiles -> pixels in the (cropped or not - the crop is bottom-only) frame. The
        screenshot is centred on `cam` over the WHOLE 1104-tall capture, so the centre row is
        cap_h/2 = 552, not 540. 32 px a tile at zoom 1 (take_screenshot draws 32*zoom; the
        capture spike's track_sprite.py matched the shark's centroid this way to 2.5 px)."""
        ppt = 32 * zoom * self.scale
        return (self.cap_w / 2 + (world[0] - cam[0]) * ppt,
                self.cap_h / 2 + (world[1] - cam[1]) * ppt)


@dataclasses.dataclass
class Take:
    """A verified take: frames/, events.jsonl, track.jsonl, run.log, stills/."""

    root: pathlib.Path
    events: tuple[Event, ...]
    track: dict[int, TrackLine]
    first: int
    last: int
    warnings: list[str] = dataclasses.field(default_factory=list)
    _by_ev: dict[str, list[Event]] = dataclasses.field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for e in self.events:
            self._by_ev.setdefault(e.ev, []).append(e)

    @property
    def frames_dir(self) -> pathlib.Path:
        return self.root / "frames"

    @property
    def run_log(self) -> pathlib.Path:
        return self.root / "run.log"

    @property
    def stills_dir(self) -> pathlib.Path:
        return self.root / "stills"

    def frame_path(self, tick: int) -> pathlib.Path:
        return self.frames_dir / f"f{tick:07d}.jpg"

    def of(self, ev: str) -> list[Event]:
        return self._by_ev.get(ev, [])

    def track_at(self, tick: int) -> TrackLine:
        """Track line `tick`, clamped into the captured range (the last frame has no T+1)."""
        return self.track[min(max(tick, self.first), self.last)]


def _num(v: object) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        return None
    return float(v)


def _pair(v: object) -> tuple[float, float] | None:
    """[x, y] as the contract writes it, or {"x":..,"y":..} as Lua tables sometimes arrive."""
    if isinstance(v, list) and len(v) == 2:
        a, b = _num(v[0]), _num(v[1])
    elif isinstance(v, dict) and set(v) == {"x", "y"}:
        a, b = _num(v["x"]), _num(v["y"])
    else:
        return None
    return None if a is None or b is None else (a, b)


def _tick(v: object) -> int | None:
    n = _num(v)
    return int(n) if n is not None and n == int(n) and n >= 0 else None


def _jsonl(path: pathlib.Path) -> Iterable[tuple[int, dict[str, object]]]:
    if not path.is_file():
        raise TakeError(f"{path}: missing")
    for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as e:
            raise TakeError(f"{path}:{i}: not JSON ({e.msg})") from None
        if not isinstance(obj, dict):
            raise TakeError(f"{path}:{i}: want a JSON object, got {type(obj).__name__}")
        yield i, obj


def load_events(path: pathlib.Path) -> tuple[Event, ...]:
    """events.jsonl -> events in tick order (stable: same-tick events keep file order, which
    is the order the director saw them), each with its ordinal among its own ev."""
    raw: list[tuple[int, str, dict[str, object], int]] = []
    for i, obj in _jsonl(path):
        tick, ev = _tick(obj.get("tick")), obj.get("ev")
        if tick is None:
            raise TakeError(f"{path}:{i}: 'tick' must be a whole number >= 0, got "
                            f"{obj.get('tick')!r}")
        if not isinstance(ev, str) or not ev:
            raise TakeError(f"{path}:{i}: 'ev' must be a non-empty string, got {ev!r}")
        raw.append((tick, ev, {k: v for k, v in obj.items() if k not in ("tick", "ev")}, i))
    raw.sort(key=lambda r: r[0])
    seen: dict[str, int] = {}
    out = []
    for tick, ev, data, line in raw:
        seen[ev] = seen.get(ev, 0) + 1
        out.append(Event(tick, ev, data, seen[ev], line))
    return tuple(out)


def load_track(path: pathlib.Path) -> dict[int, TrackLine]:
    """track.jsonl -> {tick: line}. One line per captured tick, contiguous: a gap is a frame
    the pump could not anchor a caption on, so it is refused here rather than guessed."""
    track: dict[int, TrackLine] = {}
    for i, obj in _jsonl(path):
        tick = _tick(obj.get("tick"))
        cam, pos, lift = _pair(obj.get("cam")), _pair(obj.get("pos")), _pair(obj.get("lift"))
        zoom, body = _num(obj.get("zoom")), obj.get("body")
        bad = [k for k, v in (("tick", tick), ("cam", cam), ("zoom", zoom), ("pos", pos),
                              ("lift", lift)) if v is None]
        if bad:
            raise TakeError(f"{path}:{i}: bad or missing {', '.join(bad)}")
        assert tick is not None and cam is not None and pos is not None and lift is not None
        assert zoom is not None
        if zoom <= 0:
            raise TakeError(f"{path}:{i}: zoom must be > 0, got {zoom}")
        if body not in BODIES:
            raise TakeError(f"{path}:{i}: body {body!r} is not one of {sorted(BODIES)}")
        if tick in track:
            raise TakeError(f"{path}:{i}: tick {tick} logged twice")
        track[tick] = TrackLine(tick, cam, zoom, str(body), pos, lift)
    if not track:
        raise TakeError(f"{path}: empty")
    ticks = sorted(track)
    gaps = [t for t in range(ticks[0], ticks[-1] + 1) if t not in track]
    if gaps:
        raise TakeError(f"{path}: {len(gaps)} captured tick(s) missing, first {gaps[0]} "
                        "(one line per captured tick, contiguous)")
    return track


def load_take(root: pathlib.Path) -> Take:
    """Read a take's two logs and check them against each other. Frames are checked by the
    build (it knows which ticks the cut uses); run.log by the caption cross-check."""
    root = pathlib.Path(root)
    if not root.is_dir():
        raise TakeError(f"{root}: not a directory")
    events = load_events(root / "events.jsonl")
    track = load_track(root / "track.jsonl")
    first, last = min(track), max(track)
    take = Take(root, events, track, first, last)
    for ev, want in (("capture_start", first), ("capture_end", last)):
        got = take.of(ev)
        if not got:
            take.warnings.append(f"no {ev} event; the track's own range {first}..{last} is used")
        elif len(got) > 1 or got[0].tick != want:
            take.warnings.append(f"{ev} at {[e.tick for e in got]} but the track "
                                 f"{'starts' if ev == 'capture_start' else 'ends'} at {want}")
    return take


# --------------------------------------------------------------------------------------------
# Anchors


_ANCHOR = re.compile(r"(?:beat:(?P<beat>[A-Za-z0-9_]+)|(?P<ev>[a-z][a-z0-9_]*)(?:#(?P<n>\d+))?)"
                     r"(?P<off>[+-]\d+)?")


@dataclasses.dataclass(frozen=True)
class Anchor:
    text: str
    ev: str | None
    beat: str | None
    n: int | None
    offset: int

    @classmethod
    def parse(cls, text: str) -> Anchor:
        """Whitespace is ignored (`takeoff#1 - 20` reads as `takeoff#1-20`)."""
        m = _ANCHOR.fullmatch(re.sub(r"\s+", "", text))
        if m is None or m["n"] == "0" or (m["n"] or "1").startswith("0"):
            raise CutError(f"{text!r} is not an anchor (want <ev>[#n] or beat:<name>, n >= 1, "
                           "then optional +N/-N ticks, e.g. 'takeoff#3-20')")
        return cls(text, m["ev"], m["beat"], int(m["n"]) if m["n"] else None,
                   int(m["off"] or 0))

    def resolve(self, take: Take) -> int:
        if self.beat is not None:
            beats = [e for e in take.of("beat") if e.text("name") == self.beat]
            if not beats:
                names = sorted({e.text("name") or "?" for e in take.of("beat")})
                raise CutError(f"missing anchor {self.text!r}: the take has no beat named "
                               f"{self.beat!r} (its beats: {', '.join(names) or 'none'})")
            if len(beats) > 1:
                raise CutError(f"anchor {self.text!r}: beat {self.beat!r} starts "
                               f"{len(beats)} times, at ticks {[e.tick for e in beats]}")
            return beats[0].tick + self.offset
        assert self.ev is not None
        found = take.of(self.ev)
        if not found:
            if self.ev not in KNOWN_EVENTS:
                near = difflib.get_close_matches(self.ev, sorted(KNOWN_EVENTS), n=1)
                hint = f" - did you mean {near[0]!r}?" if near else ""
                raise CutError(f"anchor {self.text!r}: {self.ev!r} is not an event the "
                               f"director logs{hint}")
            raise CutError(f"missing anchor {self.text!r}: the take has no {self.ev} event")
        if self.n is None:
            if len(found) > 1:
                raise CutError(f"anchor {self.text!r}: this take has {len(found)} {self.ev} "
                               f"events; say which ({self.ev}#1 .. {self.ev}#{len(found)})")
            return found[0].tick + self.offset
        if self.n > len(found):
            raise CutError(f"missing anchor {self.text!r}: the take has only {len(found)} "
                           f"{self.ev} event(s)")
        return found[self.n - 1].tick + self.offset


# --------------------------------------------------------------------------------------------
# The cut file


@dataclasses.dataclass(frozen=True)
class SpanSpec:
    index: int
    start: Anchor
    stop: Anchor
    speed: Fraction
    tag: str | None
    audio: AudioMode
    caption: str = "above"


@dataclasses.dataclass(frozen=True)
class FreezeSpec:
    index: int
    at: Anchor
    hold: float
    tag: str | None
    audio: AudioMode


@dataclasses.dataclass(frozen=True)
class CardSpec:
    index: int
    card: str
    seconds: float


@dataclasses.dataclass(frozen=True)
class OverlaySpec:
    index: int
    card: str
    from_out: float
    to_out: float


@dataclasses.dataclass(frozen=True)
class Cut:
    path: pathlib.Path
    fps: int
    deliver: Deliver
    segments: tuple[SpanSpec | FreezeSpec, ...]
    cards: tuple[CardSpec, ...]
    overlays: tuple[OverlaySpec, ...]
    crop: tuple[int, int, int, int] | None = None

    @property
    def captions(self) -> bool:
        """The loop take is captionless by design (it reads as the joke with the sound off,
        and a caption on a 3 s loop reads as a stutter)."""
        return self.deliver == "master"


_TOP_KEYS = {"fps", "deliver", "segment", "overlay", "card", "crop"}
_SPAN_KEYS = {"from", "to", "speed", "tag", "audio", "caption"}
SIDES = ("above", "below")
_FREEZE_KEYS = {"at", "hold", "tag", "audio"}
_CARD_KEYS = {"card", "seconds"}
_OVERLAY_KEYS = {"card", "from_out", "to_out"}


def _unknown(where: str, keys: Iterable[str], allowed: set[str]) -> None:
    for k in keys:
        if k not in allowed:
            near = difflib.get_close_matches(k, sorted(allowed), n=1)
            hint = f" - did you mean {near[0]!r}?" if near else ""
            raise CutError(f"{where}: unknown key {k!r}{hint} (allowed: "
                           f"{', '.join(sorted(allowed))})")


def _need(where: str, table: Mapping[str, object], key: str) -> object:
    if key not in table:
        raise CutError(f"{where}: missing {key!r}")
    return table[key]


def _positive(where: str, key: str, v: object) -> float:
    n = _num(v)
    if n is None or n <= 0:
        raise CutError(f"{where}: {key} must be a number > 0, got {v!r}")
    return n


def _string(where: str, key: str, v: object) -> str:
    if not isinstance(v, str) or not v.strip():
        raise CutError(f"{where}: {key} must be a non-empty string, got {v!r}")
    return v


def _anchor(where: str, key: str, v: object) -> Anchor:
    text = _string(where, key, v)
    try:
        return Anchor.parse(text)
    except CutError as e:
        raise CutError(f"{where}: {key}: {e}") from None


def _audio(where: str, v: object) -> AudioMode:
    if v == "live":
        return "live"
    if v == "mute":
        return "mute"
    raise CutError(f"{where}: audio must be 'live' or 'mute', got {v!r}")


def _tag(where: str, table: Mapping[str, object]) -> str | None:
    if "tag" not in table:
        return None
    tag = _string(where, "tag", table["tag"])
    if len(tag) > 8:
        raise CutError(f"{where}: tag {tag!r} is a corner marker, keep it to 8 characters")
    return tag


def _speed(where: str, v: object) -> Fraction:
    n = _num(v)
    if n is None:
        raise CutError(f"{where}: speed must be a number, got {v!r}")
    # limit_denominator: 0.3333 means 1/3, and exact thirds keep a long span from drifting.
    s = Fraction(n).limit_denominator(1000)
    if not MIN_SPEED <= s <= MAX_SPEED:
        raise CutError(f"{where}: speed {n} is outside {float(MIN_SPEED)}..{float(MAX_SPEED)} "
                       "(0.5 = each source frame twice, 5.0 = every 5th)")
    return s


def load_cut(path: pathlib.Path) -> Cut:
    """Parse and validate a cut file. Structure only: anchors are checked against a take by
    resolve()."""
    path = pathlib.Path(path)
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CutError(f"{path}: missing") from None
    except tomllib.TOMLDecodeError as e:
        raise CutError(f"{path}: not TOML ({e})") from None
    name = path.name
    _unknown(name, doc, _TOP_KEYS)

    fps = doc.get("fps", SOURCE_UPS)
    if fps != SOURCE_UPS or isinstance(fps, bool):
        # Speeds are written against one frame per tick; 50 or 30 would silently resample
        # every span. The GIF's 50 fps is a delay trick on the loop's frames, not a cut fps.
        raise CutError(f"{name}: fps must be {SOURCE_UPS} (the capture is one frame per tick "
                       f"at {SOURCE_UPS} UPS), got {fps!r}")
    deliver = doc.get("deliver", "master")
    if deliver not in ("master", "loop"):
        raise CutError(f"{name}: deliver must be 'master' or 'loop', got {deliver!r}")

    def tables(key: str) -> list[Mapping[str, object]]:
        v = doc.get(key, [])
        if not isinstance(v, list) or not all(isinstance(t, dict) for t in v):
            raise CutError(f"{name}: {key} must be an array of tables ([[{key}]])")
        return v

    segments: list[SpanSpec | FreezeSpec] = []
    for i, t in enumerate(tables("segment"), start=1):
        where = f"{name} segment {i}"
        if "at" in t:
            _unknown(where + " (a freeze: at + hold)", t, _FREEZE_KEYS)
            segments.append(FreezeSpec(
                i, _anchor(where, "at", t["at"]),
                _positive(where, "hold", _need(where, t, "hold")),
                _tag(where, t), _audio(where, t.get("audio", "live"))))
        else:
            _unknown(where + " (a span: from + to)", t, _SPAN_KEYS)
            side = t.get("caption", "above")
            if side not in SIDES:
                raise CutError(f"{where}: caption must be 'above' or 'below', got {side!r}")
            segments.append(SpanSpec(
                i, _anchor(where, "from", _need(where, t, "from")),
                _anchor(where, "to", _need(where, t, "to")),
                _speed(where, t.get("speed", 1.0)), _tag(where, t),
                _audio(where, t.get("audio", "live")), str(side)))
    if not segments:
        raise CutError(f"{name}: no [[segment]]s")

    cards: list[CardSpec] = []
    for i, t in enumerate(tables("card"), start=1):
        where = f"{name} card {i}"
        _unknown(where, t, _CARD_KEYS)
        card = _need(where, t, "card")
        if card not in CARDS:
            raise CutError(f"{where}: card must be one of {', '.join(CARDS)}, got {card!r}")
        cards.append(CardSpec(i, str(card), _positive(where, "seconds",
                                                      _need(where, t, "seconds"))))

    overlays: list[OverlaySpec] = []
    for i, t in enumerate(tables("overlay"), start=1):
        where = f"{name} overlay {i}"
        _unknown(where, t, _OVERLAY_KEYS)
        card = _need(where, t, "card")
        if card not in CARDS:
            raise CutError(f"{where}: card must be one of {', '.join(CARDS)}, got {card!r}")
        a, b = _num(_need(where, t, "from_out")), _num(_need(where, t, "to_out"))
        if a is None or b is None or a < 0 or b <= a:
            raise CutError(f"{where}: want 0 <= from_out < to_out (output seconds), got "
                           f"{t.get('from_out')!r} .. {t.get('to_out')!r}")
        overlays.append(OverlaySpec(i, str(card), a, b))

    crop = _crop(name, doc["crop"], deliver) if "crop" in doc else None
    return Cut(path, SOURCE_UPS, deliver, tuple(segments), tuple(cards), tuple(overlays), crop)


def _crop(name: str, v: object, deliver: str) -> tuple[int, int, int, int]:
    """[x, y, w, h] in kept-frame (1920x1080) pixels, inside it, even, 16:9."""
    want = f"{name}: crop wants [x, y, width, height] in 1080p pixels"
    if deliver != "loop":
        raise CutError(f"{name}: crop is for loop cuts; the master is the whole 1920x1080 frame")
    if not (isinstance(v, list) and len(v) == 4
            and all(isinstance(n, int) and not isinstance(n, bool) for n in v)):
        raise CutError(f"{want}, got {v!r}")
    x, y, w, h = v
    if not (x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= CAPTURE_W and y + h <= OUT_H):
        raise CutError(f"{want} inside 1920x1080, got {v!r}")
    if w % 2 or h % 2 or w * 9 != h * 16:
        raise CutError(f"{name}: crop {w}x{h} must be even and 16:9 (the loop scales to 960x540)")
    return x, y, w, h


# --------------------------------------------------------------------------------------------
# The resolver


@dataclasses.dataclass(frozen=True)
class OutFrame:
    src: int | None
    seg: int


@dataclasses.dataclass(frozen=True)
class Segment:
    index: int
    kind: SegmentKind
    speed: float
    start: int
    stop: int
    tag: str | None
    audio: AudioMode
    out: tuple[int, int]
    card: str | None = None
    caption: str = "above"

    @property
    def timelapse(self) -> bool:
        """No caption during a time-lapse: at 5x a line is up for a second and reads as a
        flash, and the tag already says the clock is not real."""
        return self.kind == "span" and self.speed > 1


@dataclasses.dataclass(frozen=True)
class Overlay:
    card: str
    from_out: float
    to_out: float
    out: tuple[int, int]


@dataclasses.dataclass(frozen=True)
class Resolved:
    fps: int
    deliver: Deliver
    captions: bool
    frames: tuple[OutFrame, ...]
    segments: tuple[Segment, ...]
    overlays: tuple[Overlay, ...]
    crop: tuple[int, int, int, int] | None = None

    @property
    def duration(self) -> float:
        return len(self.frames) / self.fps

    def sources(self) -> list[int]:
        """Every distinct source tick the output shows, in first-use order."""
        seen: dict[int, None] = {}
        for f in self.frames:
            if f.src is not None:
                seen.setdefault(f.src, None)
        return list(seen)

    def to_json(self) -> dict[str, object]:
        return {
            "fps": self.fps,
            "deliver": self.deliver,
            "captions": self.captions,
            "frames": [{"src": f.src, "seg": f.seg} for f in self.frames],
            "segments": [{"index": s.index, "kind": s.kind, "speed": s.speed,
                          "from": s.start, "to": s.stop, "tag": s.tag, "audio": s.audio,
                          "out": list(s.out), "card": s.card, "caption": s.caption}
                         for s in self.segments],
            "overlays": [{"card": o.card, "from_out": o.from_out, "to_out": o.to_out,
                          "out": list(o.out)} for o in self.overlays],
            "crop": list(self.crop) if self.crop else None,
        }

    def caption_side(self, tick: int) -> str:
        """The side a line said at source `tick` is captioned on: the first span (in cut
        order) whose range holds it decides; outside every span, above."""
        for s in self.segments:
            if s.kind == "span" and s.start <= tick < s.stop:
                return s.caption
        return "above"

    def write(self, path: pathlib.Path) -> None:
        # One frame per line: 4000 frames stay diffable and greppable without a pretty-printer.
        d = self.to_json()
        frames = d.pop("frames")
        assert isinstance(frames, list)
        head = json.dumps(d, indent=1)[:-2]
        body = ",\n".join("  " + json.dumps(f) for f in frames)
        path.write_text(f'{head},\n "frames": [\n{body}\n ]\n}}\n', encoding="utf-8")

    @classmethod
    def load(cls, path: pathlib.Path) -> Resolved:
        d = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        return cls(
            d["fps"], d.get("deliver", "master"), d.get("captions", True),
            tuple(OutFrame(f["src"], f["seg"]) for f in d["frames"]),
            tuple(Segment(s["index"], s["kind"], s["speed"], s["from"], s["to"], s["tag"],
                          s["audio"], tuple(s["out"]), s.get("card"),  # type: ignore[arg-type]
                          s.get("caption", "above"))
                  for s in d["segments"]),
            tuple(Overlay(o["card"], o["from_out"], o["to_out"], tuple(o["out"]))
                  for o in d["overlays"]),
            tuple(d["crop"]) if d.get("crop") else None)  # type: ignore[arg-type]


def span_sources(start: int, stop: int, speed: Fraction, fps: int = SOURCE_UPS) -> list[int]:
    """The source tick of every output frame of a [start, stop) span. step = speed source
    ticks per output frame at 60 fps; frame k shows start + floor(k * step)."""
    step = speed * SOURCE_UPS / fps
    n = math.ceil((stop - start) / step)
    return [start + math.floor(k * step) for k in range(n)]


def resolve(cut: Cut, take: Take) -> Resolved:
    frames: list[OutFrame] = []
    segments: list[Segment] = []

    def in_capture(where: str, what: str, tick: int, anchor: Anchor, last: int) -> None:
        if not take.first <= tick <= last:
            raise CutError(f"{where}: {what} = {anchor.text!r} resolves to tick {tick}, outside "
                           f"the capture ({take.first}..{take.last})")

    for i, spec in enumerate(cut.segments):
        where = f"{cut.path.name} segment {spec.index}"
        f0 = len(frames)
        if isinstance(spec, SpanSpec):
            a, b = spec.start.resolve(take), spec.stop.resolve(take)
            in_capture(where, "from", a, spec.start, take.last)
            in_capture(where, "to", b, spec.stop, take.last + 1)   # exclusive
            if b <= a:
                raise CutError(f"{where}: to = {spec.stop.text!r} (tick {b}) is not after "
                               f"from = {spec.start.text!r} (tick {a})")
            frames += [OutFrame(s, i) for s in span_sources(a, b, spec.speed, cut.fps)]
            segments.append(Segment(i, "span", float(spec.speed), a, b, spec.tag, spec.audio,
                                    (f0, len(frames)), None, spec.caption))
        else:
            t = spec.at.resolve(take)
            in_capture(where, "at", t, spec.at, take.last)
            n = round(spec.hold * cut.fps)
            if n < 1:
                raise CutError(f"{where}: hold {spec.hold} s is under one frame")
            frames += [OutFrame(t, i)] * n
            segments.append(Segment(i, "freeze", 0.0, t, t + 1, spec.tag, spec.audio,
                                    (f0, len(frames))))

    backdrop = frames[-1].src
    assert backdrop is not None
    for spec in cut.cards:
        i, f0 = len(segments), len(frames)
        frames += [OutFrame(None, i)] * round(spec.seconds * cut.fps)
        # A card shows the last source frame dimmed, and plays no game audio: mute, and an
        # empty source range so no event can map into it.
        segments.append(Segment(i, "card", 0.0, backdrop, backdrop, None, "mute",
                                (f0, len(frames)), spec.card))

    overlays: list[Overlay] = []
    for o in cut.overlays:
        a, b = round(o.from_out * cut.fps), round(o.to_out * cut.fps)
        if b > len(frames) or a >= b:
            raise CutError(f"{cut.path.name} overlay {o.index}: {o.from_out}..{o.to_out} s "
                           f"is not inside the cut's {len(frames) / cut.fps:.2f} s")
        overlays.append(Overlay(o.card, o.from_out, o.to_out, (a, b)))

    return Resolved(cut.fps, cut.deliver, cut.captions, tuple(frames), tuple(segments),
                    tuple(overlays), cut.crop)


def segment_of(resolved: Resolved, frame: int) -> Segment:
    return resolved.segments[resolved.frames[frame].seg]


def overlays_at(resolved: Resolved, frame: int) -> Sequence[Overlay]:
    return [o for o in resolved.overlays if o.out[0] <= frame < o.out[1]]
