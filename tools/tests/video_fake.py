"""A FAKE take for the video tests: frames/, events.jsonl, track.jsonl, run.log, stills/ and
verify.json, shaped exactly as the contract says video.sh leaves a verified take, at any size.

Each frame is one flat colour that ENCODES its tick (flat regions survive JPEG to +-2 levels,
so `tick_of` reads it back), with the bottom band painted pure magenta - a pump that forgets
to crop shows magenta, and a pump that shows the wrong tick reads back the wrong colour.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
from collections.abc import Callable, Sequence

from PIL import Image

BAND_RGB = (255, 0, 255)

#: The contract's capture aspect scaled by 0.1: 192x110 keeps 192x108, band 2.
SMALL = (192, 110)


def colour_of(tick: int) -> tuple[int, int, int]:
    """256 distinct ticks, 16 levels apart per channel: far outside JPEG's error."""
    return (tick % 16) * 16 + 8, (tick // 16) % 16 * 16 + 8, 72


def tick_of(rgb: tuple[int, ...], near: int) -> int:
    """The tick a frame's colour encodes, chosen among the 256 ticks around `near`."""
    best = min(range(max(0, near - 128), near + 128),
               key=lambda t: sum(abs(a - b) for a, b in zip(colour_of(t), rgb[:3])))
    return best


@dataclasses.dataclass
class Fake:
    root: pathlib.Path
    first: int
    last: int
    size: tuple[int, int]


def ev(tick: int, kind: str, /, **fields: object) -> dict[str, object]:
    return {"tick": tick, "ev": kind, **fields}


def make_take(root: pathlib.Path, *, first: int, last: int, events: Sequence[dict[str, object]],
              size: tuple[int, int] = SMALL,
              body: Callable[[int], str] = lambda t: "jamaltron",
              pos: Callable[[int], tuple[float, float]] = lambda t: (0.0, 0.0),
              lift: Callable[[int], tuple[float, float]] = lambda t: (0.0, -1.5),
              cam: Callable[[int], tuple[float, float]] = lambda t: (0.0, -1.5),
              zoom: float = 2.0, said: Sequence[str] | None = None,
              stills: Sequence[str] = (), frames: bool = True, verified: bool = True) -> Fake:
    """Write a take. `said` = the rows the mod's run.log claims (default: the rows of the
    line events, so the cross-check passes). `verified` writes the passing verify.json
    video.sh's stamp step leaves (the pixels here carry no stamp to check)."""
    root.mkdir(parents=True, exist_ok=True)
    w, h = size
    out_h = round(w * 1080 / 1920)
    if frames:
        (root / "frames").mkdir(exist_ok=True)
        for t in range(first, last + 1):
            im = Image.new("RGB", size, colour_of(t))
            im.paste(BAND_RGB, (0, out_h, w, h))
            im.save(root / "frames" / f"f{t:07d}.jpg", quality=95)
    evs = [ev(first, "capture_start"), *events, ev(last, "capture_end")]
    (root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs))
    track = []
    for t in range(first, last + 1):
        track.append({"tick": t, "cam": list(cam(t)), "zoom": zoom, "body": body(t),
                      "pos": list(pos(t)), "lift": list(lift(t))})
    (root / "track.jsonl").write_text("".join(json.dumps(x) + "\n" for x in track))
    rows = said if said is not None else [str(e["row"]) for e in events if e["ev"] == "line"]
    log = ["   0.000 2026-09-27 12:00:00; Factorio 2.1.17 (build 1, mac-arm64, steam)"]
    log += [f"  {1 + k:.3f} Script @__jamaltron__/scripts/speech.lua:367: jamaltron speech "
            f"{40 + k} {r}" for k, r in enumerate(rows)]
    (root / "run.log").write_text("\n".join(log) + "\n")
    if verified:
        n = last - first + 1
        (root / "verify.json").write_text(json.dumps(
            {"ok": True, "frames": n, "first": first, "last": last, "mismatch_count": 0,
             "gap_count": 0, "duplicates": [], "track_lines": n, "captured": n,
             "problems": []}) + "\n")
    if stills:
        (root / "stills").mkdir(exist_ok=True)
        for name in stills:
            Image.new("RGB", (w, out_h), (10, 20, 30)).save(root / "stills" / f"{name}.png")
    return Fake(root, first, last, size)


def write_cut(path: pathlib.Path, text: str) -> pathlib.Path:
    path.write_text(text)
    return path


# The storyA shape the shipped main.toml is written against, with the director's measured
# spacings (30-tick d=8 arcs, a 47-tick d=20 arc, the repair ~21 s) squeezed where the tests
# do not care. Ticks only - no frames are written for this one.
def story_events() -> list[dict[str, object]]:
    e: list[dict[str, object]] = []

    def beat(t: int, n: str) -> None:
        e.append(ev(t, "beat", name=n))

    beat(0, "establish")
    beat(150, "board")
    beat(200, "hop1")
    e += [ev(200, "takeoff", x=0, y=0, distance=8, land_tick=230, peak=3),
          ev(200, "line", row="jump.01", channel="speech", forced=True, x=0, y=0),
          ev(215, "apex", x=4, y=0), ev(230, "landing", x=8, y=0), ev(230, "thud", x=8, y=0),
          ev(230, "line", row="land.03", channel="speech", forced=True, x=8, y=0)]
    beat(500, "hop2")
    e += [ev(500, "takeoff", x=8, y=0, distance=8, land_tick=530, peak=3),
          ev(515, "apex", x=12, y=0), ev(530, "landing", x=16, y=0),
          ev(530, "line", row="land.06", channel="speech", forced=True, x=16, y=0)]
    beat(900, "wave")
    e += [ev(960, "fire_start", x=16, y=0),
          ev(980, "line", row="attacking.01", channel="speech", forced=True, x=16, y=0),
          ev(1250, "fire_stop", x=16, y=0), ev(1260, "wave_clear")]
    beat(1300, "report")
    e += [ev(1500, "line", row="command_done.02", channel="speech", forced=True, x=30, y=0)]
    beat(1900, "lake_jump")
    e += [ev(1900, "takeoff", x=30, y=0, distance=20, land_tick=1947, peak=7.5),
          ev(1900, "line", row="jump.05", channel="speech", forced=True, x=30, y=0),
          ev(1924, "apex", x=40, y=0), ev(1947, "break", x=50, y=0), ev(1947, "thud", x=50, y=0)]
    beat(1947, "beached")
    e += [ev(1947, "line", row="legs_break.01", channel="speech", forced=True, x=50, y=0)]
    beat(2217, "apology")
    e += [ev(2217, "line", row="flopping.12", channel="speech", forced=True, x=50, y=0),
          ev(2517, "line", row="flopping.02", channel="speech", forced=True, x=50, y=0)]
    beat(2787, "repair")
    e += [ev(2787, "repair_cue"), ev(2850, "bot_out", x=52, y=3), ev(2900, "repair_start"),
          ev(4160, "repair_full"), ev(4200, "repair", x=50, y=0)]
    beat(4200, "stand")
    e += [ev(4200, "line", row="repaired.07", channel="speech", forced=True, x=50, y=0)]
    beat(4440, "encore")
    e += [ev(4440, "takeoff", x=50, y=0, distance=20, land_tick=4487, peak=7.5),
          ev(4440, "line", row="jump.13", channel="speech", forced=True, x=50, y=0),
          ev(4464, "apex", x=40, y=0), ev(4487, "landing", x=30, y=0)]
    beat(4547, "wrap")
    return e


def loop_events() -> list[dict[str, object]]:
    """The director's loop take (story.lua loop_step, as MEASURED in loop-20260927-205144):
    loop_pre hops A -> B (landing#1, B) and B -> A (landing#2, A); `loop` begins ON that
    landing, presses 61 ticks later, lands at B (#3), presses 61 after, lands at A (#4) and
    `wrap` begins on that tick. The loop is [181, 363): 182 ticks, the seam a landing at A."""
    t = [ev(0, "beat", name="loop_pre")]
    for k, (up, side) in enumerate(((60, 12), (151, 4), (242, 12), (333, 4))):
        t += [ev(up, "takeoff", x=16 - side, y=0, distance=8, land_tick=up + 30, peak=3),
              ev(up + 15, "apex", x=8, y=0), ev(up + 30, "landing", x=side, y=0)]
        if k == 1:
            t.append(ev(181, "beat", name="loop"))
    return t + [ev(363, "beat", name="wrap")]
