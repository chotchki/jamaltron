"""G.5: his lines as post captions - the text, when each is up, where it sits, what it looks
like.

WHY POST CAPTIONS. His speech bubble is GUI, and a `show_gui=false` screenshot never has it
(G.1, MEASURED); the show_gui route puts it on the retina drawable's corner and needs a
per-tick player teleport to land it, at ~9 px in a README column. So every line is drawn here,
in Python, from the mod's OWN locale string by row id - the caption is the shipping text, not
a transcription.

THE TEXT: mod/jamaltron/locale/en/jamaltron-lines.cfg, section [jamaltron-line], one key per
row id; `__1__` is his break count, logged on the line event as `n` when the row needs it. A
row missing from the locale, or an `__1__` row with no `n`, is an error, never a blank bubble.

THE TIMING is the game's fade-OUT: a line is up from the tick it was said for SHOW_TICKS
(300), then fades over FADE_TICKS (29) - both read off scripts/speech.lua, which the tests pin
- and the next line REPLACES it on the spot (speech.lua destroys the old bubble: one bubble per
shark), mid-fade included: the old caption keeps the alpha its own fade had reached, then goes.
Timing is in SOURCE ticks, so a caption in a 0.5x span is up twice as long on screen, and a
freeze holds whatever was up on its frame.
THE POP-IN IS A CHOICE, not the game's: a caption is at full alpha on its first frame. The
bubble prototype declares fade_in_out_ticks = 30 (base entities.lua compi-speech-bubble, which
prototypes/speech.lua copies), so the game very likely fades IN too - INFERRED from the field,
never measured (the bubble is GUI and no show_gui=false frame carries it) - and speech.transfer
re-creates the bubble on every body swap, so a line still up at a takeoff or landing would
fade in AGAIN there, and one already fading at a swap is dropped. A 0.5 s fade-in over
hop1's 1.5 s slow-mo arc, and a dip at every swap, cost the reading more than they add; G.9's
eye can overrule.

THE ANCHOR is his drawn torso, not his entity: pos + lift off the track line the frame shows -
T+1 on the ground (the frame shows the state after update T), T in an arc (jamaltron's on_tick
moves him before the director reads; see Anchorer) - and clear of his legs, by body. During an
arc the caption RATCHETS: it holds where it stood before the takeoff until his rising torso
would reach it, rides up with him to the peak, and holds there until the landing - so it never
bobs down with the jump, and never floats 6 tiles over a shark still on the launch pad (the
first cut pinned it over the peak from the takeoff frame on). x follows him throughout. A cut
segment may put the captions of lines SAID in it BELOW him instead (`caption = "below"`, the
wave: above him sat on the flame stream and the biters in melee, MEASURED on o0784). Clamped
inside the frame.

THE LOOK is the game's compilatron bubble, the one prototypes/speech.lua copies: Titillium
Web (read from the install, never copied - G.7), text colour {255, 246, 113} (core
style.lua, compilatron_speech_bubble label_style.font_color), a dark translucent box, and the
`compilatron-hologram` effect's slant and faint scanlines, matched by eye against
render-out/video/research/01-standing-bubble-z2-uiscale2.png. SemiBold rather than the
game's Regular, and a darker box than the game's: judgment calls for text that must read after
h264 at README width, not measured - G.9's eye has the last word.
"""

from __future__ import annotations

import bisect
import dataclasses
import functools
import math
import os
import pathlib
import re
from collections.abc import Callable, Iterable, Mapping

from PIL import Image, ImageDraw, ImageFont

from video.timeline import AIRBORNE, Event, Geometry, Resolved, Take, TakeError

REPO = pathlib.Path(__file__).resolve().parents[2]
LOCALE = REPO / "mod" / "jamaltron" / "locale" / "en" / "jamaltron-lines.cfg"
SPEECH_LUA = REPO / "mod" / "jamaltron" / "scripts" / "speech.lua"
SECTION = "jamaltron-line"

#: speech.lua M.SHOW_TICKS / M.FADE_TICKS (test_video_captions pins them to the file).
SHOW_TICKS = 300
FADE_TICKS = 29

#: How speech.lua logs a line when debug is on: `log("jamaltron speech " .. unit .. " " .. id)`.
SPEECH_LOG = re.compile(r"\bjamaltron speech (\d+) (\S+)")

FACTORIO_DATA_ENV = "FACTORIO_DATA"
DEFAULT_FACTORIO_DATA = pathlib.Path("/Applications/factorio.app/Contents/data")
FONT_FILES = {"regular": "TitilliumWeb-Regular.ttf",
              "semibold": "TitilliumWeb-SemiBold.ttf",
              "bold": "TitilliumWeb-Bold.ttf"}

# The bubble, in px at 1080p (everything scales with Geometry.scale).
TEXT_PX = 44
TEXT_RGB = (255, 246, 113)          # style.lua compilatron_speech_bubble font_color
BOX_RGBA = (18, 18, 22, 172)        # dark, ~67% - the game's reads lighter, but it is on the
                                    # GUI layer at UI scale 2; over a busy frame this one must
                                    # carry 44 px text on its own
SCANLINE_RGBA = (0, 0, 0, 34)       # the hologram's horizontal lines, every SCANLINE_PX
SCANLINE_PX = 4
SHADOW_RGBA = (0, 0, 0, 150)        # 2 px drop under the text: a luma edge survives 4:2:0
                                    # where a yellow-on-grey chroma edge smears
PAD_X, PAD_Y = 26, 14
RADIUS = 12
WRAP_PX = 820                       # text width cap: the longest row (50 ch, 959 px) breaks
                                    # in two; the game's own cap is 500 at UI scale 1
LINE_GAP = 1.18                     # line height, x TEXT_PX
SHEAR = 0.12                        # the hologram's slant: top edge this x height to the right
#: Bubble bottom this far above the torso centre, in tiles, by the body the frame shows. MEASURED
#: on main-20260927-204942 (1/2/2.5/3-tile guides drawn over standing and beached frames at
#: zoom 1.2-2.3): a standing body's knee caps reach ~2.4 tiles above the torso centre, and at
#: the first cut's 1.0 the ~67%-opaque box sat on them; the beached body's broken legs stick
#: up ~2.1. In the air no legs are drawn, so the arc keeps 1.0 over its peak.
CLEAR_TILES: Mapping[str, float] = {"jamaltron": 2.6, "jamaltron-beached": 2.2,
                                    AIRBORNE: 1.0}
#: A `below` caption's TOP this far under the torso centre, in tiles. MEASURED on
#: main-20260927-204942 (guides 2-5 tiles under the torso, frames 200 at zoom 2 and 760/840/
#: 1000 in the wave at zoom 1.1): a standing body's lowest foot reaches 4.3-4.6 tiles down.
#: Measured standing only - the wave, where it is used, is all standing.
BELOW_TILES = 4.8
CLEAR_PX = 8                        # plus this, so zoomed out he still gets air
MARGIN_PX = 16                      # clamp: never closer to a frame edge than this

# The time-lapse tag, top-right.
TAG_PX = 50
TAG_RGB = (250, 168, 56)            # style.lua gui orange {0.98, 0.66, 0.22}
TAG_INSET = 36


class FontError(FileNotFoundError):
    """Titillium Web is not where the Factorio install keeps it."""


# --------------------------------------------------------------------------------------------
# The text


def load_lines(path: pathlib.Path = LOCALE) -> dict[str, str]:
    """[jamaltron-line] of a Factorio locale file -> {row id: string}. Factorio's cfg: `key=
    value` lines under `[section]`, `#`/`;` comments; a value runs to the end of the line."""
    lines: dict[str, str] = {}
    section = None
    for i, raw in enumerate(pathlib.Path(path).read_text(encoding="utf-8").splitlines(), 1):
        s = raw.strip()
        if not s or s[0] in "#;":
            continue
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1]
            continue
        if section != SECTION:
            continue
        key, eq, value = raw.partition("=")
        if not eq:
            raise TakeError(f"{path}:{i}: not key=value: {raw!r}")
        lines[key.strip()] = value.replace("\\n", "\n")
    if not lines:
        raise TakeError(f"{path}: no [{SECTION}] rows")
    return lines


def row_text(lines: Mapping[str, str], row: str, n: int | None) -> str:
    if row not in lines:
        raise TakeError(f"row {row!r} is not in [{SECTION}] of {LOCALE.name}")
    text = lines[row]
    if "__1__" in text:
        if n is None:
            raise TakeError(f"row {row!r} says __1__ (his break count) but its line event "
                            "carries no n")
        text = text.replace("__1__", str(n))
    left = re.findall(r"__\d+__", text)
    if left:
        raise TakeError(f"row {row!r}: {left} has no value (only __1__ = n is logged)")
    return text


# --------------------------------------------------------------------------------------------
# The timing


@dataclasses.dataclass(frozen=True)
class Caption:
    row: str
    text: str
    tick: int
    full_until: int     # exclusive: full alpha on [tick, full_until)
    gone_at: int        # exclusive: fading on [full_until, gone_at)
    fade_end: int       # where its OWN fade would reach 0: the alpha runs off this, not off a
                        # gone_at the next line cut short (else a replaced caption drops to half
                        # in one frame - MEASURED at src 1053->1054 of the first master)
    side: str = "above"  # above | below him (the cut's `caption` key, by the tick it was said)

    def alpha(self, tick: int) -> float:
        if tick < self.full_until:
            return 1.0
        return (self.fade_end - tick) / (FADE_TICKS + 1)


class CaptionTrack:
    """Which line is up at each SOURCE tick, exactly as the game shows it."""

    def __init__(self, captions: Iterable[Caption]) -> None:
        self.captions = tuple(sorted(captions, key=lambda c: c.tick))
        self._ticks = [c.tick for c in self.captions]

    @classmethod
    def from_events(cls, events: Iterable[Event], lines: Mapping[str, str],
                    side_at: Callable[[int], str] | None = None) -> CaptionTrack:
        """`side_at(tick)` is the cut's caption side for a line said at `tick` (default above)."""
        said = [e for e in events if e.ev == "line"]
        out = []
        for k, e in enumerate(said):
            where = f"line event at tick {e.tick} (events.jsonl:{e.line})"
            row, channel = e.text("row"), e.text("channel")
            if row is None:
                raise TakeError(f"{where}: no row")
            if channel != "speech":
                # Narration is world text the director hides; a caption drawn for it would be
                # a bubble the game never shows.
                raise TakeError(f"{where}: channel {channel!r}; captions are speech only")
            try:
                text = row_text(lines, row, e.int_("n"))
            except TakeError as err:
                raise TakeError(f"{where}: {err}") from None
            nxt = said[k + 1].tick if k + 1 < len(said) else None
            full = e.tick + SHOW_TICKS
            fade_end = full + FADE_TICKS
            gone = fade_end
            if nxt is not None:
                full, gone = min(full, nxt), min(gone, nxt)
            out.append(Caption(row, text, e.tick, full, gone, fade_end,
                               side_at(e.tick) if side_at else "above"))
        return cls(out)

    def at(self, tick: int) -> tuple[Caption, float] | None:
        """(caption, alpha) up at source `tick`, or None."""
        k = bisect.bisect_right(self._ticks, tick) - 1
        # Same-tick lines: the LAST one said wins (it replaced the others on that tick).
        if k < 0:
            return None
        c = self.captions[k]
        if tick < c.gone_at:
            return c, c.alpha(tick)
        return None


def captions_shown(resolved: Resolved, track: CaptionTrack) -> dict[tuple[str, int], int]:
    """{(row, tick said): first output frame it is drawn on}, per utterance."""
    shown: dict[tuple[str, int], int] = {}
    if not resolved.captions:
        return shown
    for i, f in enumerate(resolved.frames):
        seg = resolved.segments[f.seg]
        if f.src is None or seg.timelapse:
            continue
        up = track.at(f.src)
        if up is not None:
            shown.setdefault((up[0].row, up[0].tick), i)
    return shown


def rows_shown(resolved: Resolved, track: CaptionTrack) -> dict[str, int]:
    """{row: first output frame it is drawn on} - what the viewer actually sees captioned."""
    shown: dict[str, int] = {}
    for (row, _), i in sorted(captions_shown(resolved, track).items(), key=lambda kv: kv[1]):
        shown.setdefault(row, i)
    return shown


def rows_logged(run_log: pathlib.Path) -> dict[str, int]:
    """{row: times said} off speech.lua's debug log lines in the take's run.log."""
    said: dict[str, int] = {}
    for m in SPEECH_LOG.finditer(pathlib.Path(run_log).read_text(encoding="utf-8",
                                                                  errors="replace")):
        said[m[2]] = said.get(m[2], 0) + 1
    return said


def _count(events: Iterable[Event], ev: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in events:
        row = e.text("row")
        if e.ev == ev and row is not None:
            out[row] = out.get(row, 0) + 1
    return out


@dataclasses.dataclass(frozen=True)
class SpeechAudit:
    """What the viewer is shown against what the mod says it said.

    The contract asks for captioned == logged. The director's log makes that exact rather
    than approximate: every `jamaltron speech <unit> <row>` in run.log must be EITHER a
    caption in this cut, OR a row the take proves never reached the screen - a `said` event
    (the mod rolled it and a forced row replaced it on the same tick: zero frames in the game)
    or a `line` this cut does not show (inside a time-lapse, or outside every segment; each
    is listed in `notes`). Anything else is a problem, and problems fail the build.

    A `said` is only proof when it checks out: a SPEECH row needs a `line` on the same tick
    whose row is its replaced_by (the replacement that took its bubble); any other channel is
    world text the director hides every tick, and must say so (hidden: true - story.lua's
    hide_texts fails the take if a hide does not stick). A `said` that is neither is an
    UNPROVEN SAID: a real bubble mislabelled as never-shown would otherwise pass."""

    shown: dict[str, int]       # row -> first output frame it is captioned on
    lines: dict[str, int]       # row -> `line` events in the take
    replaced: dict[str, int]    # row -> `said` events (replaced on their own tick)
    logged: dict[str, int]      # row -> times in run.log
    problems: list[str]
    notes: list[str]


def audit(resolved: Resolved, track: CaptionTrack, events: Iterable[Event],
          logged: Mapping[str, int]) -> SpeechAudit:
    events = tuple(events)
    utterances = captions_shown(resolved, track)
    shown = rows_shown(resolved, track)
    lines, replaced = _count(events, "line"), _count(events, "said")
    fps, problems, notes = resolved.fps, [], []
    for row in sorted(set(shown) - set(logged)):
        problems.append(f"CAPTIONED BUT NEVER SAID: {row} (first drawn at "
                        f"{shown[row] / fps:.2f} s) - the mod's log has no 'jamaltron speech "
                        f"<unit> {row}'")
    for row in sorted(set(lines) - set(logged) - set(shown)):
        problems.append(f"A LINE THE MOD NEVER SAID: {row} - the take logs it as said, the "
                        "mod's log does not")
    for row in sorted(set(logged) - set(lines) - set(replaced)):
        problems.append(f"SAID BUT NOT CAPTIONED: {row} (logged {logged[row]}x) - the take has "
                        "no line or said event for it: a bubble the game showed that this "
                        "video cannot caption (an ambient line the director did not quiet?)")
    lines_at = {(e.tick, e.text("row")) for e in events if e.ev == "line"}
    for e in events:
        if e.ev != "said":
            continue
        row, channel, by = e.text("row") or "?", e.text("channel"), e.text("replaced_by")
        if channel == "speech":
            if by is None or (e.tick, by) not in lines_at:
                problems.append(f"UNPROVEN SAID: {row} (speech, tick {e.tick}) - no line "
                                f"{by or '(replaced_by missing)'} on the same tick replaced "
                                "it, so its bubble may have been on screen")
        elif e.data.get("hidden") is not True:
            problems.append(f"UNPROVEN SAID: {row} ({channel or 'no channel'}, tick {e.tick}) "
                            "- not speech and not flagged hidden: nothing says it was off "
                            "screen")
    for e in events:
        row = e.text("row")
        if e.ev != "line" or row is None or (row, e.tick) in utterances:
            continue
        where = [s for s in resolved.segments if s.start <= e.tick < s.stop]
        why = ("during a time-lapse" if any(s.timelapse for s in where) else
               "outside every segment" if not where else "replaced before the cut shows it")
        notes.append(f"not on screen in this cut: {row} (line at tick {e.tick}, {why})")
    for row in sorted(set(logged) & (set(lines) | set(replaced))):
        n = lines.get(row, 0) + replaced.get(row, 0)
        if n != logged[row]:
            notes.append(f"{row}: the mod logged it {logged[row]}x, the take has {n} "
                         "line/said event(s)")
    return SpeechAudit(shown, lines, replaced, dict(logged), problems, notes)


# --------------------------------------------------------------------------------------------
# The anchor


class Anchorer:
    """Where his drawn torso is on each frame, and where a caption sits above it.

    WHICH TRACK LINE A FRAME SHOWS. Line T is read in the director's on_tick T: after
    jamaltron's own on_tick T (a dependency's handler runs first), before the rest of tick T -
    the engine's entity update (walking moves him) and the on_nth_tick handlers (the stand-up
    is breakage.poll on jamaltron's 60-tick clock). The frame shows the state after ALL of it.
    So a grounded frame is line T+1's body, pos and lift (the contract's rule; on the stand-up
    tick line T still says beached, lift 0, while the frame shows him standing). But an arc is
    driven from jamaltron's on_tick - it teleports him a step and lands him there - so line
    T+1 is already one step (0.27 tiles at d=8, 0.43 at d=20, ~16 px) and on the landing tick
    one body ahead of frame T: a frame in an arc, or on either edge of one, is line T's
    (director-MEASURED, G.3: mid-arc pos read in on_tick T is where frame T draws him). On
    the takeoff tick line T is already the airborne body at the standing torso's height."""

    def __init__(self, take: Take, geo: Geometry) -> None:
        self.take, self.geo = take, geo
        self._torso: dict[int, tuple[float, float]] = {}
        self._body: dict[int, str] = {}
        self._arc: dict[int, float] = {}        # tick -> world y of an arc caption's bottom
        run: list[int] = []
        for t in range(take.first, take.last + 1):
            now, nxt = take.track[t], take.track_at(t + 1)
            shown = now if AIRBORNE in (now.body, nxt.body) else nxt
            self._torso[t] = (shown.pos[0] + shown.lift[0], shown.pos[1] + shown.lift[1])
            self._body[t] = shown.body
            if shown.body == AIRBORNE:
                run.append(t)
                continue
            self._close(run)
            run = []
        self._close(run)

    def _above(self, t: int) -> float:
        """World y a caption's bottom sits at above frame t's torso, by the body it shows."""
        return self._torso[t][1] - CLEAR_TILES[self._body[t]]

    def _close(self, run: list[int]) -> None:
        """The ratchet over one arc: hold the pre-takeoff height, then the highest the torso
        has reached so far (+ the airborne clearance). World y grows DOWN, so 'highest' is min.
        The camera's y is locked during an arc (story.lua), so level in the world is level on
        screen."""
        if not run:
            return
        before = run[0] - 1
        y = self._above(before) if before in self._torso else math.inf
        for t in run:
            y = min(y, self._above(t))
            self._arc[t] = y

    def in_arc(self, tick: int) -> bool:
        return tick in self._arc

    def torso(self, tick: int) -> tuple[float, float]:
        """His drawn torso on frame `tick`, in frame pixels."""
        now = self.take.track[tick]
        return self.geo.to_screen(self._torso[tick], now.cam, now.zoom)

    def anchor(self, tick: int, side: str = "above") -> tuple[float, float]:
        """The point a caption sits on for frame `tick`: its bottom-centre above the torso (the
        ratchet while he is in the air), or for side "below" its TOP-centre under his feet."""
        now = self.take.track[tick]
        x, y = self._torso[tick]
        if side == "below":
            sx, sy = self.geo.to_screen((x, y + BELOW_TILES), now.cam, now.zoom)
            return sx, sy + CLEAR_PX * self.geo.scale
        y = self._arc[tick] if tick in self._arc else self._above(tick)
        sx, sy = self.geo.to_screen((x, y), now.cam, now.zoom)
        return sx, sy - CLEAR_PX * self.geo.scale


# --------------------------------------------------------------------------------------------
# Fonts


class Fonts:
    """Titillium Web at any weight and size, read from the Factorio install at build time
    (G.7: nothing from the install enters the repo). `fallback()` is Pillow's bundled face,
    for tests on a machine without the game - never for a real build."""

    def __init__(self, files: Mapping[str, pathlib.Path] | None) -> None:
        self.files = dict(files) if files is not None else None

    @classmethod
    def factorio(cls, data: pathlib.Path | None = None) -> Fonts:
        root = pathlib.Path(data or os.environ.get(FACTORIO_DATA_ENV) or DEFAULT_FACTORIO_DATA)
        files = {w: root / "core" / "fonts" / f for w, f in FONT_FILES.items()}
        missing = [str(p) for p in files.values() if not p.is_file()]
        if missing:
            raise FontError(f"Titillium Web not found: {', '.join(missing)} (set "
                            f"{FACTORIO_DATA_ENV}= to the install's data dir)")
        return cls(files)

    @classmethod
    def fallback(cls) -> Fonts:
        return cls(None)

    @property
    def real(self) -> bool:
        return self.files is not None

    @functools.lru_cache(maxsize=64)  # noqa: B019 - a Fonts lives for the whole build
    def get(self, weight: str, px: int) -> ImageFont.FreeTypeFont:
        px = max(1, px)
        if self.files is None:
            font = ImageFont.load_default(size=px)
            assert isinstance(font, ImageFont.FreeTypeFont)
            return font
        return ImageFont.truetype(str(self.files[weight]), px)


def wrap(text: str, font: ImageFont.FreeTypeFont, max_w: float) -> list[str]:
    """Break `text` into as few lines as fit `max_w`, then BALANCE them: the narrowest width
    that still gives that many lines, so a two-line caption is two similar lines instead of a
    full line and a widow."""
    words = text.split()
    if not words:
        return [""]

    def greedy(w: float) -> list[str]:
        lines, cur = [], words[0]
        for word in words[1:]:
            trial = cur + " " + word
            if font.getlength(trial) <= w:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        return lines + [cur]

    best = greedy(max_w)
    if len(best) == 1:
        return best
    lo, hi = max(font.getlength(w) for w in words), max_w
    while hi - lo > 1:
        mid = (lo + hi) / 2
        if len(greedy(mid)) <= len(best):
            hi = mid
        else:
            lo = mid
    return greedy(hi)


# --------------------------------------------------------------------------------------------
# Drawing


@dataclasses.dataclass(frozen=True)
class Bubble:
    image: Image.Image                  # RGBA
    anchor: tuple[int, int]             # the box's bottom-centre, in image px
    top: tuple[int, int]                # its top-centre (the slant moves it right): a
                                        # `below` caption hangs from here

    def anchor_for(self, side: str) -> tuple[int, int]:
        return self.top if side == "below" else self.anchor


def _text_box(lines: list[str], font: ImageFont.FreeTypeFont) -> tuple[int, int, int]:
    """(width, cap height, descender) of a block of lines at this font."""
    width = max(round(font.getlength(s)) for s in lines)
    cap = round(-font.getbbox("H", anchor="ls")[1])
    desc = round(font.getbbox("gjpqy,", anchor="ls")[3])
    return width, cap, desc


@functools.lru_cache(maxsize=32)
def render_bubble(text: str, fonts: Fonts, scale: float) -> Bubble:
    """One caption's bubble, drawn once and cached for the ~300+ frames it is up."""
    px = round(TEXT_PX * scale)
    font = fonts.get("semibold", px)
    line_h = round(px * LINE_GAP)
    lines = wrap(text, font, WRAP_PX * scale)
    tw, cap, desc = _text_box(lines, font)
    pad_x, pad_y = round(PAD_X * scale), round(PAD_Y * scale)
    w = tw + 2 * pad_x
    h = pad_y * 2 + cap + (len(lines) - 1) * line_h + desc
    w, h = max(w, 2), max(h, 2)

    # The box at 4x, downsampled: ImageDraw's rounded corners are not antialiased.
    ss = 4
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1),
                                          radius=max(1, round(RADIUS * scale * ss)),
                                          fill=BOX_RGBA)
    box = big.resize((w, h), Image.Resampling.LANCZOS)
    lines_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    step = max(2, round(SCANLINE_PX * scale))
    d = ImageDraw.Draw(lines_img)
    for y in range(step - 1, h, step):
        d.line((0, y, w, y), fill=SCANLINE_RGBA)
    # Scanlines only where the box is: its alpha, scaled, is their mask.
    lines_img.putalpha(Image.composite(lines_img.getchannel("A"),
                                       Image.new("L", (w, h), 0), box.getchannel("A")))
    img = Image.alpha_composite(box, lines_img)

    d = ImageDraw.Draw(img)
    drop = max(1, round(2 * scale))
    for k, s in enumerate(lines):
        base = pad_y + cap + k * line_h
        d.text((w / 2, base + drop), s, font=font, fill=SHADOW_RGBA, anchor="ms")
        d.text((w / 2, base), s, font=font, fill=TEXT_RGB + (255,), anchor="ms")

    # The hologram slant: row y shifts right by SHEAR * (h - y), so the bottom edge (where
    # the anchor is) stays put and the top leans right, like the game's.
    dx = round(SHEAR * h)
    slanted = img.transform((w + dx, h), Image.Transform.AFFINE,
                            (1, SHEAR, -SHEAR * h, 0, 1, 0),
                            resample=Image.Resampling.BICUBIC)
    return Bubble(slanted, (w // 2, h), (w // 2 + dx, 0))


def place(size: tuple[int, int], anchor_in_img: tuple[int, int], at: tuple[float, float],
          geo: Geometry) -> tuple[int, int]:
    """Top-left for an image of `size` whose `anchor_in_img` should land on `at`, clamped so
    the whole image stays inside the kept frame with MARGIN_PX to spare."""
    m = round(MARGIN_PX * geo.scale)
    left = round(at[0] - anchor_in_img[0])
    top = round(at[1] - anchor_in_img[1])
    left = min(max(left, m), geo.cap_w - m - size[0])
    top = min(max(top, m), geo.out_h - m - size[1])
    return left, top


@functools.lru_cache(maxsize=8)
def render_tag(tag: str, fonts: Fonts, scale: float) -> Image.Image:
    """The time-lapse marker: a fast-forward double chevron and the factor ('5x'), orange on
    the bubble's dark box. An honest edit marker, so it reads at a glance, not decoratively.
    The chevrons are polygons: Titillium has no U+25B6."""
    px = round(TAG_PX * scale)
    font = fonts.get("bold", px)
    cap = round(-font.getbbox("H", anchor="ls")[1])
    tw = round(font.getlength(tag))
    pad_x, pad_y = round(PAD_X * scale), round(PAD_Y * scale)
    chev_w = round(cap * 0.62)
    overlap = round(chev_w * 0.72)          # the second chevron starts this far after the first
    chevs = overlap + chev_w
    gap = round(px * 0.18)
    w = pad_x * 2 + chevs + gap + tw
    h = pad_y * 2 + cap
    ss = 4
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1),
                        radius=max(1, round(RADIUS * scale * ss)), fill=BOX_RGBA)
    top = pad_y * ss
    for x in (pad_x * ss, (pad_x + overlap) * ss):
        d.polygon([(x, top), (x + chev_w * ss, top + cap * ss / 2), (x, top + cap * ss)],
                  fill=TAG_RGB + (255,))
    img = big.resize((w, h), Image.Resampling.LANCZOS)
    ImageDraw.Draw(img).text((pad_x + chevs + gap, pad_y + cap), tag, font=font,
                             fill=TAG_RGB + (255,), anchor="ls")
    return img


def tag_position(size: tuple[int, int], geo: Geometry) -> tuple[int, int]:
    inset = round(TAG_INSET * geo.scale)
    return geo.cap_w - inset - size[0], inset
