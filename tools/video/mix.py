"""G.6: the soundtrack - a take's event log + the cut's frames.json -> a mastered AAC .m4a.

    from video import mix
    report = mix.render(take / "events.jsonl", cut / "frames.json", take / "track.jsonl",
                        out / "main.m4a")
    uv run --directory tools python -m video.mix --events E --frames F --track T --out O

Factorio cannot export its audio (no CLI or API path; a --benchmark-graphics screenshot carries
none), so the sound is REBUILT: each event the director logged becomes the sound the game plays
for it, read from the install's own .ogg files at mix time, placed on the output timeline
through the cut, then mastered. Nothing from the install is copied anywhere: the premaster is a
temp file, deleted, and only the final .m4a remains (Wube's video policy, data/eula.txt:75-78,
allows their sounds IN a video and forbids distributing them separately - no stems, ever).

READABLE, GAME-ONLY (chotchki 2026-09-27). Only sounds the game plays at those events, at the
prototype's own volume, with two readability calls on top: the legs are lifted from the game's
0.1 x 0.8 to LEG_VOLUME (in game a step sits ~30 dB under the thud and vanishes under the
wind), and the wind bed ducks DUCK_DB under the landing thud and the flamethrower. No takeoff
sound (the mod plays none, scripts/jump.lua:594), no break or flop sound (both silent in game),
no invented cue. Speech bubbles are silent in game and here. Where the game's choice depends on
the unit (a medium biter roars roar-mid, dies to medium-gore) the unit's own sound plays.

TIMING. An event at source tick s plays at the first output frame f of each LIVE segment whose
source range [from, to) contains s with frames[f].src >= s (the contract's rule): a 0.5x span
places it on the first of its doubled frames, a 5x span on the next sampled frame (<= 4 source
ticks late), a live freeze on its first held frame, and a replayed range plays it again. Two
refinements the contract does not spell out: a segment that CONTINUES the flow (its first src is
not behind the previous frame's, and that frame was live and already at or past s) does not
re-trigger - a live freeze on a tick the span just showed would otherwise flam; and an event in
a time-lapse's last few source ticks, past its last sampled frame (5x [2196, 3424) samples up to
3421, so 3422-3423 have no frame >= them), plays on the first frame of the live segment that
continues the flow right after it, instead of on no frame at all. Pitch is never
shifted by speed: a sound plays at its natural length in output time whatever the segment's
speed. Mute and card frames are silent, the bed included (gated after the mix, the fades
inside the silent region so a live frame is never attenuated).

AGGREGATION is the engine's `remove = true, count_already_playing = true` rule, emulated in
SOURCE time before mapping: an instance is dropped while `max_count` of its sound are still
sounding, simultaneous ones kept closest-to-camera first (the engine's default priority
"closest"). A time-lapse then gets one more rule in OUTPUT time: at 5x, a sound fires five
times as often and would stack ~13 robot-repair files deep, so an instance mapped into a
speed > 1 segment is THINNED: only every round(speed)-th instance of each sound in that
segment plays, so at 5x one repairing in five - the game's own spacing in output time. The
first cut instead dropped an instance while its source-time peak was sounding, which let a
peak's worth start 0.1 s apart and then went silent ~1.35 s (MEASURED: robot-repair in clumps
of four, three times over the repair). The peak cap stays behind the thinning as a backstop.
Never denser than the game played it; 1x and slow-mo untouched.

MASTER: -6 dB pre-gain, then a two-pass LINEAR normalisation to target_lufs / TP_TARGET: pass 1
measures the premaster (ebur128, true peak), a lookahead limiter shaves its peaks until the gain
fits under the ceiling with TP_MARGIN left for the AAC encode's overshoot, pass 2 applies ONE
static gain and encodes. The result is then measured off the encoded file (ebur128 +
volumedetect + ffprobe) and reported, never assumed. WHY NOT ffmpeg's loudnorm (the G.1 plan):
its linear mode is exactly this static gain, but (a) it silently falls back to a dynamic AGC
when the measured LRA exceeds its LRA target or TP + gain exceeds its TP target, and an SFX
track's LRA is ~23 LU - the AGC pumps the bed up between thuds; (b) its own meter disagrees
with ebur128 on sparse material: 1.15 LU on the G.1 probe mix (16.7 s), 0.7 LU on a 9.7 s test
take, agreeing only on the dense 60 s stress mix (MEASURED, ffmpeg 9.0.2) - so a "correct"
linear loudnorm verified by ebur128 missed its target by that much. One meter for measure and
verify removes the disagreement by construction.

MEASURED here (ffmpeg 9.0.2, 2026-09-27): an Ogg burst placed with adelay survives resample
44.1->48 k, amix, the limiter, a static gain and AAC-LC 160 k within 0.07 ms (3 samples);
the .m4a's duration_ts is the exact sample count. alimiter WITHOUT latency=1 delays everything
by exactly its 5 ms attack (the G.1 spike's mixer had that bug). A per-sample aeval envelope
costs 13.7 s per 65 s of audio; volume eval=frame on 40-sample chunks costs 0.3 s.
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

#: Output sample rate. 48 kHz is 800 samples a frame at 60 fps, so every onset and every gate
#: edge is a whole sample; the game's 44.1 kHz files are resampled on input.
RATE = 48_000
#: Where the game's sounds are read from at mix time, never copied from: $FACTORIO_DATA, else
#: the Mac install - the same rule captions.Fonts reads the fonts by, so picture and sound never
#: disagree about which install they are built from.
FACTORIO_DATA_ENV = "FACTORIO_DATA"
DATA_DIR = Path("/Applications/factorio.app/Contents/data")
FFMPEG_DEFAULT = "/opt/homebrew/opt/ffmpeg/bin/ffmpeg"
FFPROBE_DEFAULT = "/opt/homebrew/opt/ffmpeg/bin/ffprobe"


def default_data_dir() -> Path:
    return Path(os.environ.get(FACTORIO_DATA_ENV) or DATA_DIR)


def find_ffmpeg(explicit: str | None = None) -> str | None:
    """pump.tool's order: explicit, $FFMPEG, Homebrew's keg, then PATH. None when none is
    there. (The first cut had no PATH step, so a Linux or Intel Mac build mixed a SILENT master
    while the picture, which does look on PATH, built fine - MEASURED by the review.)"""
    for cand in (explicit, os.environ.get("FFMPEG"), FFMPEG_DEFAULT):
        if cand and shutil.which(cand):
            return shutil.which(cand)
    return shutil.which("ffmpeg")

#: The spidertron leg's in-game step is 0.1 (sounds.lua spidertron_leg) x 0.8
#: (walking_sound_volume_modifier) = 0.08: ~30 dB under the thud, under the 0.3 wind bed.
#: chotchki's READABLE call lifts it to the 0.25-0.3 band. MEASURED on a storyboard-shaped
#: take of the real sounds, mastered: walking (legs + vox) -24 dBFS RMS over the bed's -40, the
#: break thud -17 (its first 0.4 s), the fight -13.
LEG_VOLUME = 0.28
#: A leg file's peak sits 6-7 ticks in (G.1, MEASURED per-tick envelope), so it starts this
#: many OUTPUT frames early and the hiss peaks on the frame the foot lands.
LEG_PREROLL = 7
#: The bed's duck under the thud and the flame: chotchki's 6-9 dB band, its middle. Pre-ducks
#: DUCK_ATTACK s ahead (offline, so lookahead is free) and recovers over DUCK_RELEASE s.
DUCK_DB = 7.5
DUCK_ATTACK = 0.03
DUCK_RELEASE = 0.35
#: The screen is 1920 px wide and a tile is 32 px at zoom 1, so half the screen is
#: 960 / (32 * zoom) tiles. Pan is equal-power from (x - cam.x) over that half-width.
HALF_WIDTH_PX = 960
TILE_PX = 32
#: Gentle distance attenuation, in half-screen-widths from the camera: -3 dB at the screen's
#: edge, capped at -9 dB. Factorio's own curve is undocumented (G.1 sfx research), and a
#: biter off-screen should still read.
ATTEN_DB_PER_HALF_WIDTH = 3.0
ATTEN_MAX_DB = 9.0
#: MainSound's defaults (prototype-api: fade_in_ticks 8, fade_out_ticks 20) for the vox loop;
#: the flame's middle loop cross-fades into its end over MID_TAIL frames.
LOOP_FADE_IN = 8
LOOP_FADE_OUT = 20
MID_TAIL = 3
#: Mute/card gate: the fades sit INSIDE the silent region, so a live frame is never touched.
GATE_RAMP = 0.005
#: Gain envelopes are evaluated per GAIN_CHUNK samples (volume eval=frame); 40 divides the
#: 800-sample frame, so a gate edge on a frame edge is a chunk edge.
GAIN_CHUNK = 40
PRE_GAIN_DB = -6.0
TP_TARGET = -1.5
#: Headroom kept under TP_TARGET for the AAC encode's overshoot: MEASURED +0.3 dB after 5.5 dB
#: of limiting, +1.0 dB after 8 (the storyboard-shaped take). The encoded file is re-measured
#: and any excess comes off the gain, so this only saves that second encode.
TP_MARGIN = 0.8
#: The most the limiter may shave off the premaster's true peak; past it the mix comes out
#: quiet (with a warning) rather than crushed. MEASURED on a storyboard-shaped take of the real
#: sounds: the peaks are the fight (the flame's middle at 1.0 under stacked deaths and gore,
#: not the thud) and -16 LUFS needs 5.5 dB of it with main.toml's 5x repair; with the repair
#: at 1x (21 s of wind and one bot) it would need ~9.5 and comes out 1.4 LU short instead.
MAX_LIMIT_DB = 8.0
#: What the verify step accepts before it warns: +-0.5 LU of target, TP_TARGET + 0.2 dB.
LUFS_TOLERANCE = 0.5
TP_TOLERANCE = 0.2
AAC_BITRATE = "160k"


class MixError(Exception):
    """A take, a cut or an install that cannot be mixed. The message names the file (and line)
    or the missing sound."""


# ---------------------------------------------------------------------------------------------
# The catalog: what the game plays, from its own prototypes (base 2.1.17 + the mod)


@dataclasses.dataclass(frozen=True)
class Sound:
    """One sound as the game declares it (its file variations, volume and aggregation) plus
    this mix's readability knobs."""

    key: str
    files: tuple[str, ...]  # relative to data_dir
    volume: float
    max_count: int = 0  # AggregationSpecification, remove + count_already_playing; 0 = none
    lead: int = 0  # SOURCE ticks from the logged event to where the game starts it
    preroll: int = 0  # OUTPUT frames started early so the file's peak lands on the frame
    duck: bool = False  # the wind bed ducks under it
    speed: tuple[float, float] = (1.0, 1.0)  # the game's own min_speed/max_speed per play


def _variations(stem: str, n: int) -> tuple[str, ...]:
    """core/lualib/sound-util.lua sound_variations: stem-1.ogg .. stem-n.ogg."""
    return tuple(f"{stem}-{i}.ogg" for i in range(1, n + 1))


_S = "base/sound/"

# The mod's legs are util.copy clones of spidertron-leg-N and keep its working_sound
# (mod/jamaltron/prototypes/entity.lua; base entities.lua make_spidertron_leg).
LEG = Sound("spidertron-leg", _variations(_S + "spidertron/spidertron-leg", 5), LEG_VOLUME,
            preroll=LEG_PREROLL)
# The spider-vehicle's working_sound (base entities.lua create_spidertron): activate/deactivate
# around the vox loop. SpiderVehicle has no driving_sound, so this is ALL the body plays.
ACTIVATE = Sound("spidertron-activate", (_S + "spidertron/spidertron-activate.ogg",), 0.5)
DEACTIVATE = Sound("spidertron-deactivate", (_S + "spidertron/spidertron-deactivate.ogg",), 0.5)
VOX = Sound("spidertron-vox", (_S + "spidertron/spidertron-vox.ogg",), 0.35)
# The mod's only play_sound (scripts/jump.lua land(), prototypes/jump.lua): three cargo-pod
# landings at 0.7, aggregation max 3. Its transient is at ticks 0-1 of the file.
THUD = Sound("jamaltron-landing-thud", _variations(_S + "procession/cargo-pod-ground-land", 3),
             0.7, max_count=3, duck=True)
# jamaltron-flamethrower's cyclic_sound (prototypes/gun.lua): begin once, middle looped after
# it, end once. His stream makes no ground fire, so there is no burning sound.
FLAME_BEGIN = Sound("flamethrower-start", (_S + "fight/flamethrower-start.ogg",), 1.0, duck=True)
FLAME_MID = Sound("flamethrower-mid", (_S + "fight/flamethrower-mid.ogg",), 1.0, duck=True)
FLAME_END = Sound("flamethrower-end", (_S + "fight/flamethrower-end.ogg",), 1.0, duck=True)
# The construction robot's repairing_sound (base flying-robots.lua): no aggregation.
ROBOT_REPAIR = Sound("robot-repair", _variations(_S + "robot-repair", 6), 0.6)
# The roboport's open/close_door_trigger_effect (base sounds.lua roboport_door_open/close).
# TIMING INFERRED, not measured: the door (door_animation_up, 16 frames) opens before a robot
# leaves, and closes request_to_open_door_timeout = 15 ticks after (base entities.lua
# roboport). The director logs bot_out when the roboport's count drops.
DOOR_OPEN = Sound("roboport-door-open", (_S + "roboport-door.ogg",), 0.3, max_count=3, lead=-16,
                  speed=(1.0, 1.5))
DOOR_CLOSE = Sound("roboport-door-close", (_S + "roboport-door-close.ogg",), 0.2, max_count=3,
                   lead=15, speed=(1.0, 1.5))
# Nauvis persistent_ambient_sounds base_ambience (base planet.lua), looped under the whole cut.
BED = Sound("world-base-wind", (_S + "world/world_base_wind.ogg",), 0.3)


@dataclasses.dataclass(frozen=True)
class Biter:
    roar: Sound  # attack_parameters.sound: once at the start of an attack
    dying: Sound  # dying_sound
    gore: Sound  # its dying_explosion's play-sound (biter-die-effects.lua)


def _biter(name: str, roar: tuple[str, int, float, int], dying: tuple[str, int, float],
           gore: tuple[str, int, float]) -> Biter:
    return Biter(
        Sound(f"{name}/roar", _variations(_S + "creatures/" + roar[0], roar[1]), roar[2],
              max_count=roar[3]),
        Sound(f"{name}/dying", _variations(_S + "creatures/" + dying[0], dying[1]), dying[2],
              max_count=3),
        Sound(f"{name}/gore", _variations(_S + "particles/" + gore[0], gore[1]), gore[2],
              max_count=1))


#: base enemies.lua + sounds.lua (biter_roars*, biter_dying*, *_gore). The aggregation key is
#: per unit and property (a small and a medium biter's dying_sound are separate definitions);
#: how the engine keys it is INFERRED.
BITERS: Mapping[str, Biter] = {
    "small-biter": _biter("small-biter", ("biter-roar", 6, 0.35, 2), ("biter-death", 5, 0.5),
                          ("small-gore", 6, 0.7)),
    "medium-biter": _biter("medium-biter", ("biter-roar-mid", 7, 0.73, 2),
                           ("biter-death", 5, 0.6), ("medium-gore", 5, 0.8)),
    "big-biter": _biter("big-biter", ("biter-roar-big", 5, 0.37, 1), ("biter-death-big", 5, 0.45),
                        ("big-gore", 5, 0.6)),
    "behemoth-biter": _biter("behemoth-biter", ("biter-roar-behemoth", 9, 0.65, 1),
                             ("biter-death-big", 5, 0.52), ("behemoth-gore", 5, 0.6)),
}

#: Events that play a one-shot at their own tick (+ the sound's lead).
ONE_SHOTS: Mapping[str, tuple[Sound, ...]] = {
    "footfall": (LEG,),
    "walk_start": (ACTIVATE,),
    "walk_stop": (DEACTIVATE,),
    "thud": (THUD,),
    "fire_start": (FLAME_BEGIN,),
    "fire_stop": (FLAME_END,),
    "bot_out": (DOOR_OPEN, DOOR_CLOSE),
    "repairing": (ROBOT_REPAIR,),
}

#: Events the game plays nothing for, and why - so an unknown `ev` is a warning, not silence.
SILENT: Mapping[str, str] = {
    "capture_start": "bookkeeping", "capture_end": "bookkeeping", "beat": "bookkeeping",
    "takeoff": "the jump plays no takeoff sound (scripts/jump.lua:594 is dust only)",
    "apex": "computed, not a game moment",
    "landing": "its sound is the thud event on the same tick",
    "break": "breakage plays nothing; its sound is the thud event on the same tick",
    "repair": "the stand-up swap plays nothing; the re-planted legs log footfalls",
    "line": "speech bubbles are silent",
    "said": "speech bubbles are silent (the director's log of every row the mod said)",
    "biter_spawn": "biter calls are random (1 in 720 a tick), not at an event",
    "wave_clear": "bookkeeping", "repair_cue": "bookkeeping",
    "repair_start": "bounds the repairing window", "repair_full": "bounds the repairing window",
    "still": "bookkeeping", "liberty": "bookkeeping",
    "biter_attack": "(played per unit name)", "biter_died": "(played per unit name)",
}


def catalog_files() -> list[str]:
    """Every file this mixer can ever read, relative to data_dir."""
    sounds: list[Sound] = [s for group in ONE_SHOTS.values() for s in group]
    sounds += [VOX, FLAME_MID, BED]
    for b in BITERS.values():
        sounds += [b.roar, b.dying, b.gore]
    return sorted({f for s in sounds for f in s.files})


# ---------------------------------------------------------------------------------------------
# Inputs: events.jsonl, frames.json, track.jsonl (formats: tools/README.md, Video)


@dataclasses.dataclass(frozen=True)
class Event:
    line: int
    tick: int
    ev: str
    x: float | None = None
    y: float | None = None
    name: str | None = None


@dataclasses.dataclass(frozen=True)
class View:
    """One track.jsonl line: where the camera looked at a tick, and where he stood."""

    cam: tuple[float, float]
    zoom: float
    pos: tuple[float, float] | None


def _num(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _int(v: object) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():  # a Lua number that serialised as 120.0
        return int(v)
    return None


def _pair(v: object) -> tuple[float, float] | None:
    if isinstance(v, (list, tuple)) and len(v) == 2:
        a, b = _num(v[0]), _num(v[1])
        if a is not None and b is not None:
            return (a, b)
    return None


def _jsonl(path: Path) -> Iterable[tuple[int, dict[str, object]]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise MixError(f"{path}: {e.strerror or e}") from None
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as e:
            raise MixError(f"{path}:{n}: not JSON ({e.msg})") from None
        if not isinstance(d, dict):
            raise MixError(f"{path}:{n}: not a JSON object")
        yield n, d


def load_events(path: Path) -> list[Event]:
    out: list[Event] = []
    for n, d in _jsonl(path):
        tick, ev = _int(d.get("tick")), d.get("ev")
        if tick is None:
            raise MixError(f"{path}:{n}: tick is not a whole number: {d.get('tick')!r}")
        if not isinstance(ev, str) or not ev:
            raise MixError(f"{path}:{n}: ev is not a name: {d.get('ev')!r}")
        name = d.get("name")
        out.append(Event(n, tick, ev, _num(d.get("x")), _num(d.get("y")),
                         name if isinstance(name, str) else None))
    return out


class Track:
    """track.jsonl by tick; a tick it lacks reads the nearest line (the director writes one per
    CAPTURED tick, and an event's lead can land a few ticks outside the capture)."""

    def __init__(self, views: Mapping[int, View]) -> None:
        self._ticks = sorted(views)
        self._views = dict(views)

    def __len__(self) -> int:
        return len(self._ticks)

    def at(self, tick: int) -> View | None:
        if not self._ticks:
            return None
        if tick in self._views:
            return self._views[tick]
        i = bisect.bisect_left(self._ticks, tick)
        near = [t for t in self._ticks[max(0, i - 1):i + 1]]
        return self._views[min(near, key=lambda t: (abs(t - tick), t))]


def load_track(path: Path) -> Track:
    views: dict[int, View] = {}
    for n, d in _jsonl(path):
        tick, cam, zoom = _int(d.get("tick")), _pair(d.get("cam")), _num(d.get("zoom"))
        if tick is None or cam is None or zoom is None or zoom <= 0:
            raise MixError(f"{path}:{n}: a track line wants tick, cam [x, y] and zoom > 0")
        views[tick] = View(cam, zoom, _pair(d.get("pos")))
    return Track(views)


@dataclasses.dataclass(frozen=True)
class Seg:
    index: int
    kind: str  # span | freeze | card
    speed: float
    start: int | None  # source range [start, stop), half-open (timeline.py)
    stop: int | None
    audio: str  # live | mute


class Cut:
    """frames.json: the source tick of every output frame and the segment it belongs to."""

    def __init__(self, fps: int, src: Sequence[int | None], seg: Sequence[int],
                 segments: Mapping[int, Seg]) -> None:
        self.fps = fps
        self.src = tuple(src)
        self.seg = tuple(seg)
        self.segments = dict(segments)
        self.spf = RATE // fps
        self.samples = len(self.src) * self.spf
        # Each live segment's frames in output order, with their sources, for the onset rule.
        self._frames: dict[int, tuple[list[int], list[int]]] = {}
        for f, (s, i) in enumerate(zip(self.src, self.seg)):
            if self.live(f):
                fs, ss = self._frames.setdefault(i, ([], []))
                fs.append(f)
                ss.append(s)  # type: ignore[arg-type]  # live() => s is not None
        self._order = sorted(self._frames, key=lambda i: self._frames[i][0][0])
        self._sorted = {i: all(a <= b for a, b in zip(ss, ss[1:]))
                        for i, (_, ss) in self._frames.items()}

    def __len__(self) -> int:
        return len(self.src)

    def live(self, f: int) -> bool:
        s = self.segments[self.seg[f]]
        return self.src[f] is not None and s.kind != "card" and s.audio == "live"

    def _range(self, i: int) -> tuple[int, int]:
        s, (_, ss) = self.segments[i], self._frames[i]
        if s.start is not None and s.stop is not None and s.stop > s.start:
            return s.start, s.stop
        return min(ss), max(ss) + 1

    def _continues(self, i: int, tick: int) -> bool:
        """Does segment i pick up where a LIVE previous frame already reached `tick`? Then the
        event was heard there, and replaying it one frame later would flam."""
        f0 = self._frames[i][0][0]
        if f0 == 0 or not self.live(f0 - 1):
            return False
        prev, first = self.src[f0 - 1], self.src[f0]
        assert prev is not None and first is not None
        return first >= prev >= tick

    def onsets(self, tick: int) -> list[int]:
        """The output frames an event at source `tick` plays on: the first frame of each live
        segment whose range contains it with src >= tick."""
        out: list[int] = []
        for i in self._order:
            lo, hi = self._range(i)
            if not lo <= tick < hi:
                continue
            fs, ss = self._frames[i]
            if self._sorted[i]:
                k = bisect.bisect_left(ss, tick)
                found = k if k < len(ss) else None
            else:
                found = next((k for k, s in enumerate(ss) if s >= tick), None)
            if found is None:
                # Past the last sampled frame of a time-lapse: play it where the flow resumes -
                # the very next output frame, when it is live and CONTIGUOUS (its source is at
                # or after the event and no later than this range's end: never a jump cut
                # forward, which would place it hundreds of ticks late, and never a replay),
                # and its own segment does not already place it.
                nf = fs[-1] + 1
                if (nf < len(self.src) and self.live(nf) and self.seg[nf] != i
                        and (nxt := self.src[nf]) is not None and tick <= nxt <= hi):
                    lo2, hi2 = self._range(self.seg[nf])
                    if not lo2 <= tick < hi2:
                        out.append(nf)
            elif not self._continues(i, tick):
                out.append(fs[found])
        return out

    def runs(self, start: int, stop: int) -> list[tuple[int, int]]:
        """Maximal [f0, f1) runs of consecutive live frames whose src is in [start, stop): where
        a looped state (walking, firing) is audible in the output."""
        out: list[tuple[int, int]] = []
        f0: int | None = None
        for f, s in enumerate(self.src):
            on = self.live(f) and s is not None and start <= s < stop
            if on and f0 is None:
                f0 = f
            elif not on and f0 is not None:
                out.append((f0, f))
                f0 = None
        if f0 is not None:
            out.append((f0, len(self.src)))
        return out

    def silent_regions(self) -> list[tuple[int, int]]:
        """Merged [f0, f1) runs of mute, card and blank frames."""
        out: list[tuple[int, int]] = []
        for f in range(len(self.src)):
            if self.live(f):
                continue
            if out and out[-1][1] == f:
                out[-1] = (out[-1][0], f + 1)
            else:
                out.append((f, f + 1))
        return out

    def speed_at(self, f: int) -> float:
        s = self.segments[self.seg[f]]
        return s.speed if s.kind == "span" else 1.0


def load_cut(path: Path) -> Cut:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise MixError(f"{path}: {e.strerror or e}") from None
    except json.JSONDecodeError as e:
        raise MixError(f"{path}: not JSON ({e.msg} at line {e.lineno})") from None
    if not isinstance(d, dict):
        raise MixError(f"{path}: not a JSON object")
    fps = _int(d.get("fps"))
    if fps is None or fps <= 0:
        raise MixError(f"{path}: fps wants a whole number above 0, got {d.get('fps')!r}")
    if RATE % fps:
        raise MixError(f"{path}: fps {fps} is not a whole number of {RATE} Hz samples a frame, "
                       "so no onset could land on a frame edge")
    segments: dict[int, Seg] = {}
    raw_segs = d.get("segments")
    if not isinstance(raw_segs, list) or not raw_segs:
        raise MixError(f"{path}: segments wants a non-empty list")
    for k, s in enumerate(raw_segs):
        where = f"{path}: segments[{k}]"
        if not isinstance(s, dict):
            raise MixError(f"{where}: not an object")
        index, kind, audio = _int(s.get("index")), s.get("kind"), s.get("audio", "live")
        speed = _num(s.get("speed", 1.0))
        if index is None or index in segments:
            raise MixError(f"{where}: index wants a unique whole number, got {s.get('index')!r}")
        if kind not in ("span", "freeze", "card"):
            raise MixError(f"{where}: kind is span, freeze or card, got {kind!r}")
        if audio not in ("live", "mute"):
            raise MixError(f"{where}: audio is live or mute, got {audio!r}")
        if speed is None or speed < 0:
            raise MixError(f"{where}: speed wants a number >= 0, got {s.get('speed')!r}")
        segments[index] = Seg(index, kind, speed, _int(s.get("from")), _int(s.get("to")), audio)
    frames = d.get("frames")
    if not isinstance(frames, list) or not frames:
        raise MixError(f"{path}: frames wants a non-empty list")
    src: list[int | None] = []
    seg: list[int] = []
    for k, fr in enumerate(frames):
        if not isinstance(fr, dict):
            raise MixError(f"{path}: frames[{k}] is not an object")
        s_raw, i = fr.get("src"), _int(fr.get("seg"))
        s = None if s_raw is None else _int(s_raw)
        if s_raw is not None and s is None:
            raise MixError(f"{path}: frames[{k}].src wants a tick or null, got {s_raw!r}")
        if i is None or i not in segments:
            raise MixError(f"{path}: frames[{k}].seg {fr.get('seg')!r} names no segment")
        src.append(s)
        seg.append(i)
    return Cut(fps, src, seg, segments)


# ---------------------------------------------------------------------------------------------
# Planning: events -> source-time instances -> aggregation -> output placements (pure Python)


def pan_gains(pan: float) -> tuple[float, float]:
    """Equal-power (L, R), unity at centre: cos/sin of (pan+1)*pi/4, times sqrt 2."""
    theta = (max(-1.0, min(1.0, pan)) + 1.0) * math.pi / 4.0
    return math.cos(theta) * math.sqrt(2.0), math.sin(theta) * math.sqrt(2.0)


def spatial(view: View | None, x: float | None, y: float | None) -> tuple[float, float]:
    """(gain dB, pan) for a sound at world (x, y) in the frame `view` shot: pan from x - cam.x
    over half the screen in tiles at that zoom, attenuation from the distance. No position, or
    no track: centre, full level."""
    if view is None or x is None or y is None:
        return 0.0, 0.0
    half = HALF_WIDTH_PX / (TILE_PX * view.zoom)
    dx, dy = x - view.cam[0], y - view.cam[1]
    pan = max(-1.0, min(1.0, dx / half))
    gain = -min(ATTEN_MAX_DB, ATTEN_DB_PER_HALF_WIDTH * math.hypot(dx, dy) / half)
    return gain, pan


def _vol_db(sound: Sound) -> float:
    return 20.0 * math.log10(sound.volume)


def _hash(*parts: object) -> int:
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "big")


@dataclasses.dataclass(frozen=True)
class Shot:
    """A one-shot in SOURCE time: what the game would have started, and when."""

    sound: Sound
    file: str
    tick: int
    event: Event
    speed: float
    gain_db: float  # the sound's volume + distance attenuation
    pan: float
    distance: float  # from the camera, tiles: the engine's "closest" priority


@dataclasses.dataclass(frozen=True)
class Placed:
    """A sound on the OUTPUT timeline, in samples at RATE."""

    key: str
    file: str
    src_tick: int | None
    at: int  # onset sample
    head: int  # samples trimmed off the file's start (a preroll that fell before 0)
    length: int  # samples it plays (the file's, or the loop run's)
    loop: bool
    gain_db: float  # the sound's volume + distance attenuation
    pan: float
    speed: float
    fade_in: int = 0
    fade_out: int = 0
    duck: bool = False


@dataclasses.dataclass
class Plan:
    cut: Cut
    placed: list[Placed]
    gate: list[tuple[int, int]]  # silent [a, b) in samples
    ducks: list[tuple[float, float]]  # merged [start, end] in seconds, before attack/release
    events: int
    dropped_aggregation: Counter[str]
    dropped_timelapse: Counter[str]
    unplaced: Counter[str]  # shots whose tick no live frame shows
    silent: Counter[str]  # events the game plays nothing for
    warnings: list[str]


def sounds_for(events: Sequence[Event]) -> list[Sound]:
    """Every Sound these events can play, plus the bed: what the install must hold."""
    out: dict[str, Sound] = {BED.key: BED}
    kinds = {e.ev for e in events}
    for k in kinds & ONE_SHOTS.keys():
        for s in ONE_SHOTS[k]:
            out[s.key] = s
    if "walk_start" in kinds:
        out[VOX.key] = VOX
    if "fire_start" in kinds:
        out[FLAME_MID.key] = FLAME_MID
    if "thud" not in kinds and kinds & {"landing", "break"}:
        out[THUD.key] = THUD
    for e in events:
        b = BITERS.get(e.name or "") if e.ev in ("biter_attack", "biter_died") else None
        if b is not None:
            for s in (b.roar, b.dying, b.gore):
                out[s.key] = s
    return list(out.values())


def _pairs(events: Sequence[Event], on: str, off: str, last: int) -> list[tuple[Event, int]]:
    """(start event, stop tick) of each on..off state; an unclosed one runs to `last`."""
    out: list[tuple[Event, int]] = []
    open_: Event | None = None
    for e in sorted(events, key=lambda e: (e.tick, e.line)):
        if e.ev == on and open_ is None:
            open_ = e
        elif e.ev == off and open_ is not None:
            out.append((open_, e.tick))
            open_ = None
    if open_ is not None:
        out.append((open_, max(last, open_.tick + 1)))
    return out


def plan(events: Sequence[Event], cut: Cut, track: Track,
         seconds: Callable[[str], float]) -> Plan:
    """Place every sound. `seconds(file)` is a file's natural length (ffprobe in render(), a
    table in the tests): aggregation, loops and ducks all need it."""
    warnings: list[str] = []
    silent: Counter[str] = Counter()
    evs = sorted(events, key=lambda e: (e.tick, e.line))
    kinds = {e.ev for e in evs}
    thud_from = {"thud"}
    if "thud" not in kinds and kinds & {"landing", "break"}:
        # The contract logs the thud as its own event; a take without it still thuds where the
        # mod plays it, on the landing / break swap's tick.
        thud_from = {"landing", "break"}
        warnings.append("no thud events: the landing thud plays on landing/break instead")
    window: tuple[int, int] | None = None
    starts = [e.tick for e in evs if e.ev == "repair_start"]
    fulls = [e.tick for e in evs if e.ev == "repair_full"]
    if starts and fulls:
        window = (min(starts), max(fulls))

    # The roboport's door cannot open before the packs that let a bot out went in: DOOR_OPEN's
    # INFERRED lead would otherwise start it before repair_cue (MEASURED on the first master:
    # 15 ticks early, the effect heard before its cause).
    cues = sorted(e.tick for e in evs if e.ev == "repair_cue")

    # 1. Events -> source-time shots, variation picked from the event (stable re-mixes).
    shots: list[Shot] = []
    ordinal: Counter[tuple[int, str, str]] = Counter()
    for e in evs:
        if e.ev in thud_from:
            sounds: tuple[Sound, ...] = (THUD,)
        elif e.ev in ONE_SHOTS:
            sounds = ONE_SHOTS[e.ev]
        elif e.ev in ("biter_attack", "biter_died"):
            b = BITERS.get(e.name or "")
            if b is None:
                warnings.append(f"events line {e.line}: {e.ev} for unit {e.name!r} - no sound "
                                "catalogued for it, left silent")
                continue
            sounds = (b.roar,) if e.ev == "biter_attack" else (b.dying, b.gore)
        else:
            if e.ev not in SILENT:
                warnings.append(f"events line {e.line}: unknown event {e.ev!r}, left silent")
            silent[e.ev] += 1
            continue
        if e.ev == "repairing" and window and not window[0] <= e.tick <= window[1]:
            silent["repairing (outside repair_start..repair_full)"] += 1
            continue
        view = track.at(e.tick)
        x, y = e.x, e.y
        if x is None and view is not None and view.pos is not None:
            x, y = view.pos  # a positionless event (repairing) sounds where he is
        gain_db, pan = spatial(view, x, y)
        dist = (math.hypot(x - view.cam[0], y - view.cam[1])
                if view is not None and x is not None and y is not None else 0.0)
        for s in sounds:
            k = ordinal[(e.tick, e.ev, s.key)]
            ordinal[(e.tick, e.ev, s.key)] += 1
            # (hash + ordinal) % n: simultaneous feet never share a file, so four legs landing
            # on one tick never sum one waveform coherently (+12 dB).
            v = s.files[(_hash(e.tick, e.ev, s.key) + k) % len(s.files)]
            lo, hi = s.speed
            speed = lo + (hi - lo) * (_hash(e.tick, e.ev, s.key, k, "speed") / 2.0 ** 64)
            at = e.tick + s.lead
            if s is DOOR_OPEN and cues:
                k_cue = bisect.bisect_right(cues, e.tick) - 1
                if k_cue >= 0:
                    at = max(at, cues[k_cue])
            shots.append(Shot(s, v, at, e, speed, gain_db + _vol_db(s), pan, dist))

    # 2. The engine's aggregation, in source time. Ends are in ticks at natural speed.
    def ticks(shot: Shot) -> float:
        return seconds(shot.file) / shot.speed * 60.0

    kept: list[Shot] = []
    dropped_agg: Counter[str] = Counter()
    playing: dict[str, list[float]] = {}
    peak: Counter[str] = Counter()
    for shot in sorted(shots, key=lambda s: (s.tick, s.distance, s.event.line)):
        live = [end for end in playing.get(shot.sound.key, []) if end > shot.tick]
        if shot.sound.max_count and len(live) >= shot.sound.max_count:
            dropped_agg[shot.sound.key] += 1
            playing[shot.sound.key] = live
            continue
        live.append(shot.tick + ticks(shot))
        playing[shot.sound.key] = live
        peak[shot.sound.key] = max(peak[shot.sound.key], len(live))
        kept.append(shot)

    # 3. Map to output. Pitch is never shifted: a sound's length in samples is its file's.
    spf = cut.spf
    placed: list[Placed] = []
    unplaced: Counter[str] = Counter()
    candidates: list[tuple[Placed, float, int]] = []
    shown = [s for s in cut.src if s is not None]
    lo_src, hi_src = (min(shown), max(shown)) if shown else (0, -1)
    for shot in kept:
        frames = cut.onsets(shot.tick)
        if not frames:
            unplaced[shot.sound.key] += 1
            if shot.sound.duck and lo_src <= shot.tick <= hi_src:
                # A thud or the flame INSIDE the stretch of game the cut shows, on no live
                # frame: a mute segment or a gap swallowed it. Legal, but never silently.
                warnings.append(f"{shot.sound.key} at source tick {shot.tick} "
                                f"({shot.event.ev}, events line {shot.event.line}) is inside "
                                f"the cut's source range {lo_src}..{hi_src} but on no live "
                                "frame - a mute segment or a gap between segments")
        n = round(seconds(shot.file) * RATE / shot.speed)
        for f in frames:
            at = f * spf - shot.sound.preroll * spf
            head = max(0, -at)
            if head >= n:
                continue
            candidates.append((Placed(shot.sound.key, shot.file, shot.tick, at + head, head,
                                      n - head, False, shot.gain_db, shot.pan, shot.speed,
                                      duck=shot.sound.duck), cut.speed_at(f), cut.seg[f]))
    # 3b. A time-lapse plays every round(speed)-th instance of each sound (the game's spacing
    # in output time), and never more at once than the game ever had (its source peak).
    dropped_tl: Counter[str] = Counter()
    sounding: dict[str, list[int]] = {}
    nth: Counter[tuple[int, str]] = Counter()
    for p, speed, seg in sorted(candidates, key=lambda c: (c[0].at, c[0].key, c[0].file)):
        ends = [end for end in sounding.get(p.key, []) if end > p.at]
        if speed > 1.0:
            k = nth[(seg, p.key)]
            nth[(seg, p.key)] += 1
            if k % max(1, round(speed)) or len(ends) >= max(1, peak[p.key]):
                dropped_tl[p.key] += 1
                sounding[p.key] = ends
                continue
        ends.append(p.at + p.length)
        sounding[p.key] = ends
        placed.append(p)

    # 4. Looped states: the vox while he walks, the flame's middle while he fires.
    last = max((s for s in cut.src if s is not None), default=0) + 1
    begins = {(p.src_tick, p.at) for p in placed if p.key == FLAME_BEGIN.key}
    for sound, on, off in ((VOX, "walk_start", "walk_stop"), (FLAME_MID, "fire_start",
                                                             "fire_stop")):
        for start_ev, stop in _pairs(evs, on, off, last):
            view = track.at(start_ev.tick)
            gain_db, pan = spatial(view, start_ev.x, start_ev.y)
            for f0, f1 in cut.runs(start_ev.tick, stop):
                at, end = f0 * spf, f1 * spf
                if sound is FLAME_MID:
                    if (start_ev.tick, at) in begins:
                        # CyclicSound: the middle starts when the begin has played out.
                        at += round(seconds(FLAME_BEGIN.files[0]) * RATE)
                        fade_in = round(0.002 * RATE)
                    else:
                        fade_in = LOOP_FADE_IN * spf  # a cut into a burst already going
                    fade_out = MID_TAIL * spf
                else:
                    fade_in, fade_out = LOOP_FADE_IN * spf, LOOP_FADE_OUT * spf
                length = end - at + fade_out
                if end - at <= 0:
                    continue  # a burst shorter than its begin: the middle never starts
                placed.append(Placed(sound.key, sound.files[0], start_ev.tick, at, 0, length,
                                     True, gain_db + _vol_db(sound), pan, 1.0,
                                     min(fade_in, length // 2), min(fade_out, length // 2),
                                     sound.duck))

    placed.sort(key=lambda p: (p.at, p.key, p.file))
    gate = [(a * spf, b * spf) for a, b in cut.silent_regions()]
    return Plan(cut, placed, gate, _merge_ducks(placed), len(events), dropped_agg, dropped_tl,
                unplaced, silent, warnings)


def _merge_ducks(placed: Sequence[Placed]) -> list[tuple[float, float]]:
    spans = sorted((p.at / RATE, (p.at + p.length) / RATE) for p in placed if p.duck)
    out: list[tuple[float, float]] = []
    for a, b in spans:
        if out and a - DUCK_ATTACK <= out[-1][1] + DUCK_RELEASE:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


# ---------------------------------------------------------------------------------------------
# Rendering: one ffmpeg graph -> a float premaster -> two-pass linear normalisation -> AAC


def _fmt(x: float) -> str:
    return f"{x:.6f}".rstrip("0").rstrip(".") if x != int(x) else str(int(x))


def _db(db: float) -> float:
    return 10.0 ** (db / 20.0)


def _gate_filters(gate: Sequence[tuple[int, int]], total: int) -> list[str]:
    """One volume envelope per silent region: 1 at its first chunk, fading to 0 over
    GATE_RAMP, back to 1 at its last - so both fades sit inside the region."""
    out: list[str] = []
    r = _fmt(GATE_RAMP)
    for a, b in gate:
        A, B = _fmt(a / RATE), _fmt(b / RATE)
        down = f"(({A})+{r}-t)/{r}" if a > 0 else "0"
        up = f"(t-(({B})-{r}))/{r}" if b < total else "0"
        out.append(f"volume=eval=frame:volume='if(between(t,{A},{B}),"
                   f"clip(max({down},{up}),0,1),1)'")
    return out


def _duck_filters(ducks: Sequence[tuple[float, float]]) -> list[str]:
    g = _fmt(1.0 - _db(-DUCK_DB))
    out = []
    for a, b in ducks:
        A, B = _fmt(a - DUCK_ATTACK), _fmt(b + DUCK_RELEASE)
        out.append(f"volume=eval=frame:volume='1-{g}*clip(min((t-({A}))/{_fmt(DUCK_ATTACK)},"
                   f"(({B})-t)/{_fmt(DUCK_RELEASE)}),0,1)'")
    return out


def _chain(p: Placed) -> list[str]:
    c: list[str] = []
    if p.speed != 1.0:  # the game's own per-play speed (roboport doors), not the cut's
        c.append(f"asetrate={_fmt(RATE * p.speed)},aresample={RATE}")
    if p.head:
        c.append(f"atrim=start_sample={p.head},asetpts=PTS-STARTPTS")
    c.append(f"atrim=end_sample={p.length}")
    if p.fade_in:
        c.append(f"afade=t=in:ss=0:ns={p.fade_in}")
    if p.fade_out:
        c.append(f"afade=t=out:ss={p.length - p.fade_out}:ns={p.fade_out}")
    gl, gr = pan_gains(p.pan)
    g = _db(p.gain_db)
    c.append(f"pan=stereo|c0={g * gl:.6f}*c0|c1={g * gr:.6f}*c1")
    c.append(f"adelay=delays={p.at}S:all=1")
    return c


def graph(pl: Plan, data_dir: Path) -> tuple[list[str], str]:
    """(ffmpeg input args, filter_complex script) for the premaster. One -i per unique one-shot
    file fanned out by asplit (1000 steps open 5 files, not 1000); each loop and the bed get
    their own -stream_loop input so an infinite stream is never fanned out to a branch that is
    still waiting on its delay."""
    fmt = f"aresample={RATE},aformat=sample_fmts=fltp:sample_rates={RATE}:channel_layouts=stereo"
    n = pl.cut.samples
    args = ["-f", "lavfi", "-i", f"anullsrc=r={RATE}:cl=stereo"]
    lines = [f"[0:a]atrim=end_sample={n}[base]"]
    labels = ["[base]"]
    shots: dict[str, list[int]] = {}
    for k, p in enumerate(pl.placed):
        if not p.loop:
            shots.setdefault(p.file, []).append(k)
    inp = 1
    for file, ks in shots.items():
        args += ["-i", str(data_dir / file)]
        outs = "".join(f"[s{k}]" for k in ks)
        lines.append(f"[{inp}:a]{fmt}" + (f",asplit={len(ks)}{outs}" if len(ks) > 1 else outs))
        inp += 1
    for k, p in enumerate(pl.placed):
        if p.loop:
            args += ["-stream_loop", "-1", "-i", str(data_dir / p.file)]
            lines.append(f"[{inp}:a]{fmt}[s{k}]")
            inp += 1
        lines.append(f"[s{k}]" + ",".join(_chain(p)) + f"[p{k}]")
        labels.append(f"[p{k}]")
    args += ["-stream_loop", "-1", "-i", str(data_dir / BED.files[0])]
    bed = [fmt, f"atrim=end_sample={n}", f"asetnsamples=n={GAIN_CHUNK}:p=0",
           f"volume={_fmt(BED.volume)}", *_duck_filters(pl.ducks)]
    lines.append(f"[{inp}:a]" + ",".join(bed) + "[bed]")
    labels.insert(1, "[bed]")
    master = [f"amix=inputs={len(labels)}:duration=first:normalize=0",
              f"asetnsamples=n={GAIN_CHUNK}:p=0", *_gate_filters(pl.gate, n),
              f"volume={_fmt(PRE_GAIN_DB)}dB", f"atrim=end_sample={n}"]
    lines.append("".join(labels) + ",".join(master) + "[out]")
    return args, ";\n".join(lines) + "\n"


@dataclasses.dataclass
class Loudness:
    integrated_lufs: float
    true_peak_dbtp: float
    lra_lu: float
    max_volume_db: float
    normalization: str  # linear (one static gain) | none (a silent mix)
    limiter_ceiling_db: float | None  # premaster-domain ceiling, None = not needed
    gain_db: float | None  # the static gain after the limiter
    premaster_lufs: float  # the premaster (after the -6 dB pre-gain), before the limiter
    premaster_tp: float


@dataclasses.dataclass
class Cue:
    key: str
    file: str
    src_tick: int | None
    out_s: float
    seconds: float
    gain_db: float
    pan: float


@dataclasses.dataclass
class MixReport:
    out: Path
    fps: int
    frames: int
    samples: int  # the encoded stream's own count (ffprobe duration_ts), == frames * RATE / fps
    duration_s: float
    events: int
    placed: dict[str, int]
    dropped_aggregation: dict[str, int]
    dropped_timelapse: dict[str, int]
    unplaced: dict[str, int]
    silent: dict[str, int]
    loudness: Loudness
    warnings: list[str]
    cues: list[Cue]
    elapsed_s: float

    @property
    def loudness_ok(self) -> bool:
        """The ENCODED file is within LUFS_TOLERANCE of the target and under the TP ceiling (+
        TP_TOLERANCE). A limiter that ran out of depth is a note; its result is judged here."""
        return not any(w.startswith("loudness:") for w in self.warnings)

    def summary(self) -> str:
        lo = self.loudness
        lines = [
            f"mix: {self.out} - {self.duration_s:.3f} s ({self.frames} frames at {self.fps} fps, "
            f"{self.samples} samples), {sum(self.placed.values())} sounds placed from "
            f"{self.events} events in {self.elapsed_s:.1f} s",
            f"  loudness {lo.integrated_lufs:+.1f} LUFS, true peak {lo.true_peak_dbtp:+.1f} dBTP, "
            f"LRA {lo.lra_lu:.1f} LU, max {lo.max_volume_db:+.1f} dB ({lo.normalization}"
            + ("" if lo.gain_db is None else f" {lo.gain_db:+.2f} dB")
            + f"; premaster {lo.premaster_lufs:+.1f} LUFS / {lo.premaster_tp:+.1f} dBTP, limiter "
            + ("off" if lo.limiter_ceiling_db is None
               else f"{lo.premaster_tp - lo.limiter_ceiling_db:.1f} dB deep")
            + ")",
            "  placed: " + (", ".join(f"{k} {v}" for k, v in sorted(self.placed.items()))
                            or "nothing"),
        ]
        for what, d in (("dropped by aggregation", self.dropped_aggregation),
                        ("dropped in time-lapse", self.dropped_timelapse),
                        ("not in any live frame", self.unplaced)):
            if d:
                lines.append(f"  {what}: " + ", ".join(f"{k} {v}" for k, v in sorted(d.items())))
        lines += [f"  WARNING {w}" for w in self.warnings]
        return "\n".join(lines)


def _run(cmd: Sequence[str], what: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(list(cmd), capture_output=True, text=True)
    if proc.returncode:
        tail = "\n".join(proc.stderr.strip().splitlines()[-12:])
        raise MixError(f"{what} failed (exit {proc.returncode}):\n{tail}")
    return proc


def _ffprobe_for(ffmpeg: str) -> str:
    env = os.environ.get("FFPROBE")
    if env:
        return env
    sibling = Path(ffmpeg).with_name("ffprobe")
    if sibling.is_file():
        return str(sibling)
    return FFPROBE_DEFAULT if Path(FFPROBE_DEFAULT).is_file() else "ffprobe"


def _tool(path: str, what: str) -> str:
    found = shutil.which(path)
    if found is None:
        raise MixError(f"{what} not found: {path!r} (set {what.upper()} or install ffmpeg)")
    return found


@dataclasses.dataclass(frozen=True)
class R128:
    """One ebur128 reading: integrated LUFS, true peak dBTP (4x oversampled), LRA LU."""

    lufs: float
    tp: float
    lra: float


def _r128(stderr: str) -> R128:
    def grab(pattern: str) -> float:
        found = re.findall(pattern, stderr)
        return float(found[-1]) if found else float("nan")

    return R128(grab(r"\bI:\s+(-?[\d.]+|-inf) LUFS"), grab(r"Peak:\s+(-?[\d.]+|-inf) dBFS"),
                grab(r"LRA:\s+(-?[\d.]+) LU\b"))


def _limiter(ceiling_db: float | None) -> list[str]:
    """Shave the premaster's peaks to ceiling_db. alimiter's own limit bottoms out at -24 dB,
    so the signal is scaled to put the ceiling at 0 dBFS and back. latency=1 or the whole
    track moves 5 ms late (MEASURED); level=0 or it re-normalises its output."""
    if ceiling_db is None:
        return []
    return [f"volume={_fmt(-ceiling_db)}dB",
            "alimiter=limit=1:level=0:latency=1:attack=5:release=50",
            f"volume={_fmt(ceiling_db)}dB"]


def _measure(ffmpeg: str, src: Path, pre: Sequence[str]) -> R128:
    af = ",".join([*pre, "ebur128=peak=true:framelog=quiet"])
    proc = _run([ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-i", str(src), "-af", af,
                 "-f", "null", "-"], "ebur128 measure")
    return _r128(proc.stderr)


#: AAC-LC 160 kbps 48 kHz stereo, bit-exact (no encoder version string, no metadata) so two
#: renders of one take are byte-identical.
ENCODE = ("-c:a", "aac", "-profile:a", "aac_low", "-b:a", AAC_BITRATE, "-ar", str(RATE), "-ac",
          "2", "-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact")


def _encode(ffmpeg: str, pre: Path, out: Path, chain: Sequence[str]) -> None:
    af = ["-af", ",".join(chain)] if chain else []
    _run([ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-y", "-i", str(pre), *af, *ENCODE,
          str(out)], "master + AAC encode")


def _master(ffmpeg: str, pre: Path, out: Path, target: float,
            warnings: list[str]) -> tuple[str, float | None, float | None, R128]:
    """Two-pass LINEAR normalisation -> AAC: measure, shave peaks until the gain fits under
    the ceiling, one static gain, encode - then measure the ENCODED true peak and, if the AAC
    overshoot beat TP_MARGIN, take the excess off the gain and encode again. Returns
    (normalization, limiter ceiling, gain, the premaster's reading)."""
    first = _measure(ffmpeg, pre, [])
    if not math.isfinite(first.lufs) or first.lufs <= -69.9:
        warnings.append("loudness: the mix is silent, nothing to normalise")
        _encode(ffmpeg, pre, out, [])
        return "none", None, None, first
    m, ceiling = first, None
    floor = first.tp - MAX_LIMIT_DB  # the deepest the limiter may shave
    for _ in range(5):
        room = TP_TARGET - TP_MARGIN - (target - m.lufs)  # the premaster TP the gain lands on
        if m.tp <= room + 0.05 or (ceiling is not None and ceiling <= floor):
            break
        # Tighten against the ORIGINAL premaster by the overshoot still left; limiting lowers
        # the loudness a little, which raises the gain, so this takes 2-3 rounds. Where the
        # loudness IS the peaks (nothing under them) every dB shaved costs a dB of loudness and
        # this never converges - hence the floor.
        ceiling = max(floor, room if ceiling is None else ceiling - (m.tp - room))
        m = _measure(ffmpeg, pre, _limiter(ceiling))
    # The true-peak ceiling wins over the loudness target: a quiet mix is a warning, a clipped
    # one is a broken deliverable.
    gain = round(min(target - m.lufs, TP_TARGET - TP_MARGIN - m.tp), 2)  # what volume= applies
    if gain < target - m.lufs - 0.05:
        warnings.append(f"limiter: {target} LUFS is out of reach under {TP_TARGET} dBTP with "
                        f"at most {MAX_LIMIT_DB} dB of limiting - {target - m.lufs - gain:.1f} "
                        "LU short")
    for _ in range(3):
        _encode(ffmpeg, pre, out, [*_limiter(ceiling), f"volume={gain:.2f}dB"])
        tp = _measure(ffmpeg, out, []).tp
        if not math.isfinite(tp) or tp <= TP_TARGET:
            break
        # The encode overshot by more than TP_MARGIN (MEASURED up to +1.0 dB after 8 dB of
        # limiting: a limited signal is all near-ceiling peaks for the codec to ring on).
        gain = round(gain - (tp - TP_TARGET + 0.1), 2)
    return "linear", ceiling, gain, first


def _verify(ffmpeg: str, ffprobe: str, out: Path, samples: int, target: float,
            warnings: list[str]) -> tuple[int, R128, float]:
    """Measure the ENCODED file: (samples, its ebur128 reading, volumedetect max dB). The
    sample count is a hard contract (picture and sound mux by length), so a mismatch raises."""
    probe = _run([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                  "stream=codec_name,profile,sample_rate,channels,duration_ts,time_base",
                  "-of", "json", str(out)], "ffprobe")
    st = json.loads(probe.stdout)["streams"][0]
    got = int(st["duration_ts"])
    if st.get("time_base") != f"1/{RATE}":
        got = round(got * RATE * _frac(st.get("time_base", f"1/{RATE}")))
    if (st.get("codec_name"), st.get("profile"), int(st.get("sample_rate", 0)),
            int(st.get("channels", 0))) != ("aac", "LC", RATE, 2):
        raise MixError(f"{out}: not AAC-LC {RATE} Hz stereo: {st}")
    if got != samples:
        raise MixError(f"{out}: {got} samples, the cut wants exactly {samples}")
    proc = _run([ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-i", str(out), "-af",
                 "ebur128=peak=true:framelog=quiet,volumedetect", "-f", "null", "-"], "verify")
    r = _r128(proc.stderr)
    found = re.findall(r"max_volume:\s+(-?[\d.]+|-inf) dB", proc.stderr)
    mx = float(found[-1]) if found else float("nan")
    if not (math.isfinite(r.lufs) and abs(r.lufs - target) <= LUFS_TOLERANCE):
        warnings.append(f"loudness: {r.lufs} LUFS measured, target {target} +-{LUFS_TOLERANCE}")
    if not (math.isfinite(r.tp) and r.tp <= TP_TARGET + TP_TOLERANCE):
        warnings.append(f"loudness: true peak {r.tp} dBTP, ceiling {TP_TARGET}")
    return got, r, mx


def _frac(tb: str) -> float:
    a, b = tb.split("/")
    return int(a) / int(b)


def _durations(ffprobe: str, data_dir: Path, files: Iterable[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for f in sorted(set(files)):
        proc = _run([ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                     "stream=duration_ts,sample_rate,time_base:format=duration", "-of", "json",
                     str(data_dir / f)], f"ffprobe {f}")
        d = json.loads(proc.stdout)
        st = (d.get("streams") or [{}])[0]
        if st.get("duration_ts") is not None and st.get("time_base"):
            out[f] = int(st["duration_ts"]) * _frac(st["time_base"])
        else:
            out[f] = float(d["format"]["duration"])
        if out[f] <= 0:
            raise MixError(f"{data_dir / f}: no audio in it")
    return out


def render(events: Path, frames: Path, track: Path, out: Path, *,
           data_dir: Path | None = None, ffmpeg: str | None = None, target_lufs: float = -16.0,
           work_dir: Path | None = None) -> MixReport:
    """Mix a take's events through a resolved cut into `out` (AAC-LC 160 kbps 48 kHz stereo,
    exactly len(frames)/fps long), mastered to target_lufs. `data_dir` defaults to
    $FACTORIO_DATA, then the Mac install; `ffmpeg` to find_ffmpeg()'s order; ffprobe is
    $FFPROBE, then the one beside ffmpeg. build.py passes both from the picture's own resolvers.
    `work_dir` keeps the filter script and the float premaster for a listen (default: a temp
    dir, deleted)."""
    t0 = time.monotonic()
    evs, cut, trk = load_events(events), load_cut(frames), load_track(track)
    data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
    if not data_dir.is_dir():
        raise MixError(f"data_dir {data_dir} is not a directory - is Factorio installed there?")
    needed = sorted({f for s in sounds_for(evs) for f in s.files})
    missing = [f for f in needed if not (data_dir / f).is_file()]
    if missing:
        raise MixError(f"{len(missing)} sound file(s) missing under {data_dir}: "
                       + ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else ""))
    ff = _tool(find_ffmpeg(ffmpeg) or ffmpeg or FFMPEG_DEFAULT, "ffmpeg")
    fp = _tool(_ffprobe_for(ff), "ffprobe")
    lengths = _durations(fp, data_dir, needed)
    pl = plan(evs, cut, trk, lambda f: lengths[f])
    warnings = list(pl.warnings)
    if not len(trk):
        warnings.append("track.jsonl is empty: every sound is centred at full level")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Beside `out` (render-out/, gitignored) so the finished file is renamed into place: a
    # failed verify never leaves a half-right .m4a where the builder expects a good one.
    with tempfile.TemporaryDirectory(prefix=".mix-", dir=out.parent) as tmp:
        work = Path(work_dir) if work_dir is not None else Path(tmp)
        work.mkdir(parents=True, exist_ok=True)
        args, script = graph(pl, data_dir)
        (work / "mix.filter.txt").write_text(script, encoding="utf-8")
        pre, enc = work / "premaster.wav", Path(tmp) / out.name
        _run([ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args,
              "-/filter_complex", str(work / "mix.filter.txt"), "-map", "[out]",
              "-c:a", "pcm_f32le", "-f", "wav", str(pre)], "mix")
        kind, ceiling, gain, before = _master(ff, pre, enc, target_lufs, warnings)
        samples, after, mx = _verify(ff, fp, enc, cut.samples, target_lufs, warnings)
        os.replace(enc, out)
    placed = Counter(p.key for p in pl.placed)
    return MixReport(
        out=out, fps=cut.fps, frames=len(cut), samples=samples, duration_s=samples / RATE,
        events=pl.events, placed=dict(placed), dropped_aggregation=dict(pl.dropped_aggregation),
        dropped_timelapse=dict(pl.dropped_timelapse), unplaced=dict(pl.unplaced),
        silent=dict(pl.silent),
        loudness=Loudness(after.lufs, after.tp, after.lra, mx, kind, ceiling, gain, before.lufs,
                          before.tp),
        warnings=warnings,
        cues=[Cue(p.key, p.file, p.src_tick, p.at / RATE, p.length / RATE, round(p.gain_db, 2),
                  round(p.pan, 3)) for p in pl.placed],
        elapsed_s=time.monotonic() - t0)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m video.mix",
                                 description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--events", type=Path, required=True, help="the take's events.jsonl")
    ap.add_argument("--frames", type=Path, required=True, help="the resolved cut's frames.json")
    ap.add_argument("--track", type=Path, required=True, help="the take's track.jsonl")
    ap.add_argument("--out", type=Path, required=True, help="the .m4a to write")
    ap.add_argument("--data-dir", type=Path, default=None,
                    help=f"Factorio's data/ (read only; default ${FACTORIO_DATA_ENV}, then "
                    f"{DATA_DIR})")
    ap.add_argument("--ffmpeg", default=None,
                    help=f"default $FFMPEG, then {FFMPEG_DEFAULT}, then PATH")
    ap.add_argument("--target-lufs", type=float, default=-16.0)
    ap.add_argument("--work-dir", type=Path, default=None,
                    help="keep the filter script and premaster here (never commit them)")
    ap.add_argument("--report", type=Path, default=None, help="write the MixReport as JSON")
    a = ap.parse_args(argv)
    try:
        rep = render(a.events, a.frames, a.track, a.out, data_dir=a.data_dir, ffmpeg=a.ffmpeg,
                     target_lufs=a.target_lufs, work_dir=a.work_dir)
    except MixError as e:
        print(f"mix: {e}", file=sys.stderr)
        return 2
    print(rep.summary())
    if a.report is not None:
        d = dataclasses.asdict(rep)
        a.report.write_text(json.dumps(d, indent=1, default=str) + "\n", encoding="utf-8")
    return 0 if rep.loudness_ok else 1


if __name__ == "__main__":
    sys.exit(main())
