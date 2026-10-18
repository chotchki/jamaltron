"""G.4: the tick stamp - the proof that frame file N shows tick N, for EVERY frame of a take.

    uv run --directory tools python -m video.stamp verify ../render-out/video/takes/main-<stamp>
    uv run --directory tools python -m video.stamp decode FRAME.jpg ...

WHY A STAMP AND NOT A FILE COUNT. MEASURED in the G.1 capture spike: at game speed 4 without
force_render, all 361 files of a 361-tick capture were written - and 67 of them showed a later
tick, 59 were duplicates. A count proves nothing; the director therefore draws game.tick INTO the
picture, in the same on_tick that requests the screenshot, so the stamp and the picture are one
render, and this module reads it back off every frame.

THE STAMP (tools/harness/jamaltron-video/camera.lua draws it; the five numbers below are the
same five numbers there, and tests/test_video_stamp.py pins them against the Lua source):
BITS squares of SQUARE px on a PITCH px pitch from X0, least significant bit first, then a white
and a black sentinel, centred vertically in the bottom BAND rows of the frame - rows the pump
crops away (1920x1104 -> 1920x1080). White is 1. A square is read by the mean luma of its inner
core (SQUARE - 2*INSET px across, clear of JPEG's ringing at the edges) against a mid threshold;
the sentinels must read clearly white and clearly black or the frame has no stamp at all.

WHAT verify FAILS ON (each a way a take could be silently wrong):
  * a MISMATCH: a stamp that does not decode, or decodes to a tick other than its file name's
  * a DUPLICATE: one stamp value on two files (two files holding one render)
  * a GAP: a tick between capture_start and capture_end with no frame
  * the COUNTS: frames == track.jsonl lines == capture_end - capture_start + 1, and the track's
    ticks are exactly the frames' ticks
Reported but NOT failed: IDENTICAL pictures (two consecutive frames byte-equal above the band).
The stamp already proves each file is its own tick's render - a stale render carries a stale
stamp - so an identical picture is a scene that did not move for a tick (a pinned-water loop
take can do that), not a capture fault.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import dataclasses
import hashlib
import itertools
import json
import os
import pathlib
import re
import sys
from collections.abc import Iterable, Sequence

from PIL import Image, ImageDraw

#: The stamp's geometry, in frame pixels. camera.lua holds the same numbers.
SQUARE, PITCH, X0, BITS = 16, 24, 16, 20
#: The bottom rows of the frame that carry it (the take's `band`, cropped by the pump).
BAND = 24
#: Pixels trimmed off each side of a square before it is read.
INSET = 4
#: Luma thresholds: a bit is 1 above MID; a white sentinel reads above HIGH, a black one below LOW.
MID, HIGH, LOW = 128, 200, 55

#: A frame file: f + the tick, zero-padded to 7.
FRAME_RE = re.compile(r"^f(\d{7})\.(?:jpg|png)$")


def squares(height: int) -> list[tuple[int, int, int, int]]:
    """The (left, top, right, bottom) box of every square, bits first then the two sentinels,
    for a frame `height` px tall (the band is its bottom BAND rows)."""
    top = height - BAND + (BAND - SQUARE) // 2
    return [(X0 + PITCH * i, top, X0 + PITCH * i + SQUARE, top + SQUARE) for i in range(BITS + 2)]


def draw(image: Image.Image, tick: int) -> None:
    """Paint the stamp for `tick` into `image` in place: what the director's rectangles look like
    in a frame. For tests and fake takes; the real stamp is drawn by the game."""
    if not 0 <= tick < 1 << BITS:
        raise ValueError(f"tick {tick} does not fit {BITS} bits")
    ink = ImageDraw.Draw(image)
    for i, box in enumerate(squares(image.height)):
        on = (tick >> i) & 1 if i < BITS else i == BITS
        ink.rectangle((box[0], box[1], box[2] - 1, box[3] - 1),
                      fill=(255, 255, 255) if on else (0, 0, 0))


def _levels(image: Image.Image) -> list[float]:
    """Mean luma of every square's core."""
    luma = image.convert("L")
    out = []
    for left, top, right, bottom in squares(image.height):
        core = luma.crop((left + INSET, top + INSET, right - INSET, bottom - INSET))
        data = core.tobytes()
        out.append(sum(data) / len(data))
    return out


def decode(image: Image.Image) -> int | None:
    """The tick stamped on `image`, or None when the sentinels say there is no stamp there."""
    levels = _levels(image)
    if not (levels[BITS] > HIGH and levels[BITS + 1] < LOW):
        return None
    return sum(1 << i for i in range(BITS) if levels[i] > MID)


def frame_tick(path: pathlib.Path) -> int:
    """The tick a frame file claims by its name."""
    m = FRAME_RE.match(path.name)
    if not m:
        raise ValueError(f"not a frame file name: {path.name}")
    return int(m[1])


def frame_files(frames: pathlib.Path) -> list[pathlib.Path]:
    """Every frame file in `frames`, in tick order."""
    return sorted((p for p in frames.iterdir() if FRAME_RE.match(p.name)), key=frame_tick)


@dataclasses.dataclass(frozen=True)
class Read:
    """One frame, read."""
    tick: int                 # by its file name
    stamp: int | None         # by its pixels
    digest: str               # of the picture above the band
    size: int                 # bytes on disk


def read_frame(path: pathlib.Path) -> Read:
    """A frame PIL cannot decode (truncated by a full disk or a killed game, or not a jpg at all)
    reads as NO stamp: a mismatch verify.json names, never a traceback that leaves no verify.json
    behind for video.sh's failure message to point at."""
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            picture = im.crop((0, 0, im.width, im.height - BAND)).tobytes()
            return Read(frame_tick(path), decode(im),
                        hashlib.blake2b(picture, digest_size=16).hexdigest(), path.stat().st_size)
    except (OSError, SyntaxError, ValueError):
        # OSError: truncated / unidentified image; SyntaxError: PIL's "not a JPEG file".
        return Read(frame_tick(path), None, f"unreadable:{path.name}", path.stat().st_size)


@dataclasses.dataclass
class FrameReport:
    frames: int = 0
    first: int | None = None
    last: int | None = None
    bytes: int = 0
    mismatches: list[tuple[str, int | None]] = dataclasses.field(default_factory=list)
    duplicates: list[tuple[int, list[str]]] = dataclasses.field(default_factory=list)
    gaps: list[int] = dataclasses.field(default_factory=list)
    identical: list[tuple[int, int]] = dataclasses.field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.mismatches or self.duplicates or self.gaps) and self.frames > 0


def check_reads(reads: Sequence[Read]) -> FrameReport:
    """The stamp checks over frames already read, in tick order."""
    rep = FrameReport(frames=len(reads))
    if not reads:
        return rep
    rep.first, rep.last = reads[0].tick, reads[-1].tick
    rep.bytes = sum(r.size for r in reads)
    by_stamp: dict[int, list[str]] = {}
    for r in reads:
        name = f"f{r.tick:07d}"
        if r.stamp != r.tick:
            rep.mismatches.append((name, r.stamp))
        if r.stamp is not None:
            by_stamp.setdefault(r.stamp, []).append(name)
    rep.duplicates = sorted((v, names) for v, names in by_stamp.items() if len(names) > 1)
    have = {r.tick for r in reads}
    rep.gaps = [t for t in range(rep.first, rep.last + 1) if t not in have]
    rep.identical = [(a.tick, b.tick) for a, b in itertools.pairwise(reads) if a.digest == b.digest]
    return rep


def read_all(files: Sequence[pathlib.Path], jobs: int | None = None) -> list[Read]:
    """Every frame read, in parallel (a JPEG decode is the cost: ~4000 of them a take)."""
    jobs = jobs or max(1, (os.cpu_count() or 2) - 1)
    if jobs == 1 or len(files) < 64:
        return [read_frame(p) for p in files]
    with cf.ProcessPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(read_frame, files, chunksize=32))


def _jsonl(path: pathlib.Path) -> list[dict]:
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as err:
                raise ValueError(f"{path.name}:{n}: {err}") from None
    return out


@dataclasses.dataclass
class TakeReport:
    frames: FrameReport
    track_lines: int
    captured: int | None
    problems: list[str]

    @property
    def ok(self) -> bool:
        return self.frames.ok and not self.problems

    def summary(self) -> str:
        f = self.frames
        per = f.bytes / f.frames / 1e6 if f.frames else 0.0
        verdict = "OK" if self.ok else "FAILED"
        return (f"stamp: {verdict} - {f.frames} frames (ticks {f.first}..{f.last}), "
                f"{len(f.mismatches)} mismatches, {len(f.duplicates)} duplicates, "
                f"{len(f.gaps)} gaps, {len(f.identical)} identical pictures; track {self.track_lines} "
                f"lines, captured {self.captured} ticks; {per:.2f} MB/frame, {f.bytes / 1e9:.2f} GB")

    def to_json(self) -> dict:
        f = self.frames
        return {"ok": self.ok, "frames": f.frames, "first": f.first, "last": f.last,
                "bytes": f.bytes, "mismatches": f.mismatches[:200], "mismatch_count": len(f.mismatches),
                "duplicates": f.duplicates[:200], "gaps": f.gaps[:200], "gap_count": len(f.gaps),
                "identical": f.identical[:200], "identical_count": len(f.identical),
                "track_lines": self.track_lines, "captured": self.captured, "problems": self.problems}


def verify_take(take: pathlib.Path, jobs: int | None = None) -> TakeReport:
    """Every check a take must pass before anything downstream reads it (the module docstring)."""
    problems: list[str] = []
    frames_dir = take / "frames"
    files = frame_files(frames_dir) if frames_dir.is_dir() else []
    if not files:
        problems.append(f"no frames in {frames_dir}")
    rep = check_reads(read_all(files, jobs))
    track_ticks: list[int] = []
    track = take / "track.jsonl"
    if track.is_file():
        track_ticks = [int(d["tick"]) for d in _jsonl(track)]
    else:
        problems.append("no track.jsonl")
    captured = None
    events = take / "events.jsonl"
    if events.is_file():
        evs = _jsonl(events)
        start = [int(e["tick"]) for e in evs if e.get("ev") == "capture_start"]
        end = [int(e["tick"]) for e in evs if e.get("ev") == "capture_end"]
        if len(start) != 1 or len(end) != 1:
            problems.append(f"events.jsonl has {len(start)} capture_start and {len(end)} capture_end")
        else:
            captured = end[0] - start[0] + 1
            if files and (rep.first, rep.last) != (start[0], end[0]):
                problems.append(f"frames span {rep.first}..{rep.last}, capture_start..capture_end is "
                                f"{start[0]}..{end[0]}")
        ticks = [int(e["tick"]) for e in evs]
        if ticks != sorted(ticks):
            problems.append("events.jsonl is not in tick order")
    else:
        problems.append("no events.jsonl")
    if captured is not None and not (rep.frames == len(track_ticks) == captured):
        problems.append(f"counts disagree: {rep.frames} frames, {len(track_ticks)} track lines, "
                        f"{captured} captured ticks")
    frame_ticks = [frame_tick(p) for p in files]
    if track_ticks and track_ticks != frame_ticks:
        problems.append("track.jsonl's ticks are not the frames' ticks")
    return TakeReport(rep, len(track_ticks), captured, problems)


def _print_details(rep: TakeReport, out) -> None:
    f = rep.frames
    for p in rep.problems:
        print(f"  PROBLEM {p}", file=out)
    for name, got in f.mismatches[:20]:
        print(f"  MISMATCH {name}: stamp reads {got}", file=out)
    for value, names in f.duplicates[:20]:
        print(f"  DUPLICATE stamp {value} on {', '.join(names)}", file=out)
    if f.gaps:
        print(f"  GAPS {f.gaps[:20]}{' ...' if len(f.gaps) > 20 else ''}", file=out)
    if f.identical:
        pairs = ", ".join(f"{a}={b}" for a, b in f.identical[:12])
        print(f"  identical pictures (not a failure): {pairs}{' ...' if len(f.identical) > 12 else ''}",
              file=out)


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m video.stamp",
                                 description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="check every frame of a take; writes <take>/verify.json")
    v.add_argument("take", type=pathlib.Path)
    v.add_argument("--jobs", type=int, default=None, help="decoder processes (default cores - 1)")
    d = sub.add_parser("decode", help="print the stamp of each frame file")
    d.add_argument("files", type=pathlib.Path, nargs="+")
    args = ap.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "decode":
        for p in args.files:
            with Image.open(p) as im:
                print(f"{p.name} {decode(im.convert('RGB'))}")
        return 0
    take: pathlib.Path = args.take
    if not take.is_dir():
        print(f"stamp: no take dir {take}", file=sys.stderr)
        return 2
    rep = verify_take(take, args.jobs)
    (take / "verify.json").write_text(json.dumps(rep.to_json(), indent=1) + "\n", encoding="utf-8")
    print(rep.summary())
    _print_details(rep, sys.stdout if rep.ok else sys.stderr)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
