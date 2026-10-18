"""G.5: frames.json + the take -> composited RGB frames -> ONE ffmpeg process.

STREAMING, never a frame list: a 65 s master is ~3900 frames x 6.2 MB of RGB = 24 GB, so
each output frame is read, composited, written to ffmpeg's stdin and dropped. Source jpgs are
decoded AHEAD on a small thread pool (Pillow's JPEG decoder releases the GIL; a 1920x1104
decode is the pump's single biggest cost) in play order, with consecutive repeats collapsed:
a 0.5x span or a 4.5 s freeze decodes its frame once and hands the same image on.

Per frame, in order:
  1. the source jpg, cropped to rows 0..out_h-1 - the bottom band is the director's tick
     stamp, verified by video.sh and never shown
  2. the caption up at that SOURCE tick (captions.CaptionTrack), bubble anchored above his
     torso (or under his feet, where the cut says `caption = "below"`) - unless the cut is
     captionless or the segment is a time-lapse
  3. the segment's tag ('5x') in the top-right corner
  4. any overlay card whose output window covers the frame (the title)
  5. the cut's `crop` (loop cuts), last, so everything above works in full-frame pixels
  and a card segment is the last source frame dimmed + blurred with the card over it,
  crossfading in from the last composed frame.

ENCODE (the contract's flags): rgb24 rawvideo on stdin ->
`libx264 -preset slow -crf 20 -profile:v high -level 4.2`, converted to bt709 limited range
in the scaler (`scale=out_color_matrix=bt709:out_range=tv,format=yuv420p`) and TAGGED bt709,
so a player neither guesses bt601 (the SD default, a visible hue shift on the orange) nor
full range. The loop take's two deliverables come out of the same single process: a
filter_complex splits the RGB stream into the 960x540 portal mp4 and the README GIF.

KEYFRAMES (the master): an IDR is forced on every segment's first frame and the GOP is longer
than the longest HOLD (a freeze or a card), so no IDR lands inside a still picture. MEASURED
on the first master: x264's default 250-frame GOP put one at out 2999, 1.1 s into the 4.5 s
freeze, and the frozen grass visibly re-grained (1.748 mean abs against <= 0.133 for every
other freeze step; 4.2% of pixels moved >= 4 levels). In a live span an IDR is invisible.
"""

from __future__ import annotations

import collections
import dataclasses
import itertools
import os
import pathlib
import shutil
import subprocess
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from typing import IO, Protocol, TypeVar

from PIL import Image

from video import captions as cap
from video.cards import Cards, scaled_lut
from video.timeline import Geometry, OutFrame, Resolved, Take, TakeError, overlays_at

FFMPEG_ENV, FFPROBE_ENV = "FFMPEG", "FFPROBE"
#: Homebrew's keg-only ffmpeg: not on PATH on chotchki's machine (G.1). It has libx264 and
#: palettegen, and no drawtext/libass/freetype - which is why the captions are Pillow's.
BREW_BIN = pathlib.Path("/opt/homebrew/opt/ffmpeg/bin")

X264 = ("-c:v", "libx264", "-preset", "slow", "-crf", "20", "-profile:v", "high",
        "-level", "4.2")
#: setparams because the contract's -color_primaries/-color_trc flags alone do NOT reach the
#: stream: MEASURED on ffmpeg 9.0.2, the scaler's frames carry "unspecified" primaries and
#: transfer and those win over the encoder options (ffprobe: color_space bt709, primaries and
#: transfer absent). Stamping them on the frames makes both paths agree.
TO_BT709 = ("scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
            "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")
BT709_TAGS = ("-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
              "-color_range", "tv")

#: The README GIF: every source frame at 2 cs (50 fps; browsers clamp <= 1 cs to 10 cs, so 60
#: is unrepresentable and 25/30 judder - G.8). Bayer dither is ordered, so a pixel that did
#: not change dithers the same way every frame and diff_mode=rectangle only re-encodes the
#: part of the frame that moved (error diffusion ripples the whole frame on any change).
GIF_FPS = 50
GIF_PALETTE = "palettegen=stats_mode=diff"
GIF_USE = "paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle"

#: Decode ahead this many distinct source frames on this many threads. MEASURED on
#: chotchki's M3 Max: 4.8 ms to decode + crop one 1920x1104 q90 jpg (0.40 MB) on one thread,
#: against x264 -preset slow's ~8 ms a 1080p frame (G.1: 361 frames in 3.05 s) - serial
#: decode + compose + pipe would be the bottleneck, so it runs ahead on a pool.
PREFETCH, WORKERS = 12, 4


class PumpError(RuntimeError):
    """ffmpeg died, or a frame is not what the take promised."""


def tool(env: str, name: str) -> str:
    """ffmpeg/ffprobe: $FFMPEG/$FFPROBE, else Homebrew's keg, else PATH. A named binary that
    is missing is an error, never a silent fall-through to some other build."""
    named = os.environ.get(env)
    if named:
        if not (os.path.isfile(named) and os.access(named, os.X_OK)):
            raise PumpError(f"${env}={named!r} is not an executable")
        return named
    brew = BREW_BIN / name
    if brew.is_file() and os.access(brew, os.X_OK):
        return str(brew)
    found = shutil.which(name)
    if found is None:
        raise PumpError(f"no {name}: install ffmpeg or set ${env}=/path/to/{name}")
    return found


def ffmpeg() -> str:
    return tool(FFMPEG_ENV, "ffmpeg")


def ffprobe() -> str:
    return tool(FFPROBE_ENV, "ffprobe")


# --------------------------------------------------------------------------------------------
# Reading


def crop_band(im: Image.Image, geo: Geometry) -> Image.Image:
    """Keep rows 0..out_h-1: the bottom `band` rows carry the tick stamp."""
    if im.size != (geo.cap_w, geo.cap_h):
        raise TakeError(f"frame is {im.size[0]}x{im.size[1]}, the take is "
                        f"{geo.cap_w}x{geo.cap_h}")
    return im.crop((0, 0, geo.cap_w, geo.out_h))


def load_frame(take: Take, geo: Geometry, tick: int) -> Image.Image:
    path = take.frame_path(tick)
    try:
        with Image.open(path) as im:
            out = crop_band(im.convert("RGB"), geo)
    except FileNotFoundError:
        raise TakeError(f"{path}: missing (the cut shows tick {tick})") from None
    except TakeError as e:
        raise TakeError(f"{path}: {e}") from None
    out.load()
    return out


T = TypeVar("T")
R = TypeVar("R")


def prefetch_map(fn: Callable[[T], R], items: Iterable[T], workers: int = WORKERS,
                 ahead: int = PREFETCH) -> Generator[tuple[T, R], None, None]:
    """(item, fn(item)) in order, with up to `ahead` calls in flight. Bounded: never more
    than `ahead` results held."""
    with ThreadPoolExecutor(max_workers=workers) as ex:
        it = iter(items)
        q: collections.deque[tuple[T, Future[R]]] = collections.deque(
            (x, ex.submit(fn, x)) for x in itertools.islice(it, ahead))
        while q:
            x, fut = q.popleft()
            for nxt in itertools.islice(it, 1):
                q.append((nxt, ex.submit(fn, nxt)))
            yield x, fut.result()


def play_order(frames: Sequence[OutFrame]) -> list[int]:
    """Source ticks in the order the output needs them, consecutive repeats collapsed."""
    return [k for k, _ in itertools.groupby(f.src for f in frames if f.src is not None)]


# --------------------------------------------------------------------------------------------
# Compositing


@dataclasses.dataclass
class Composer:
    """Turns (output frame, its source image) into the finished RGB frame."""

    resolved: Resolved
    geo: Geometry
    fonts: cap.Fonts
    captions: cap.CaptionTrack | None
    anchorer: cap.Anchorer | None
    cards: Cards
    _last: Image.Image | None = None

    def compose(self, i: int, base: Image.Image | None) -> Image.Image:
        f = self.resolved.frames[i]
        seg = self.resolved.segments[f.seg]
        if seg.kind == "card":
            if base is None:
                raise PumpError(f"frame {i}: a card with no source frame before it")
            assert seg.card is not None
            return self.cards.card(seg.card, seg.start, base, self._last,
                                   i - seg.out[0], self.resolved.fps)
        assert base is not None and f.src is not None
        out = base
        drawn = False

        if (self.captions is not None and self.anchorer is not None
                and self.resolved.captions and not seg.timelapse):
            up = self.captions.at(f.src)
            if up is not None:
                caption, alpha = up
                bubble = cap.render_bubble(caption.text, self.fonts, self.geo.scale)
                xy = cap.place(bubble.image.size, bubble.anchor_for(caption.side),
                               self.anchorer.anchor(f.src, caption.side), self.geo)
                out, drawn = out.copy(), True
                _paste(out, bubble.image, xy, alpha)

        if seg.tag:
            tag = cap.render_tag(seg.tag, self.fonts, self.geo.scale)
            if not drawn:
                out, drawn = out.copy(), True
            _paste(out, tag, cap.tag_position(tag.size, self.geo), 1.0)

        for o in overlays_at(self.resolved, i):
            a = self.cards.overlay_alpha(i, o.out[0], o.out[1], self.resolved.fps)
            out = self.cards.overlay(out, o.card, a)

        self._last = out
        return out


def _paste(dst: Image.Image, src: Image.Image, xy: tuple[int, int], alpha: float) -> None:
    """Straight-alpha `src` (RGBA) over `dst` (RGB) at `xy`, scaled by `alpha`."""
    if alpha >= 1:
        dst.paste(src, xy, src)
    elif alpha > 0:
        mask = src.getchannel("A").point(scaled_lut(alpha))
        dst.paste(src.convert("RGB"), xy, mask)


def composer_for(resolved: Resolved, take: Take, geo: Geometry, fonts: cap.Fonts,
                 lines: dict[str, str] | None = None) -> Composer:
    track = anchorer = None
    if resolved.captions:
        track = cap.CaptionTrack.from_events(take.events, lines or cap.load_lines(),
                                             resolved.caption_side)
        anchorer = cap.Anchorer(take, geo)
    return Composer(resolved, geo, fonts, track, anchorer, Cards(geo, fonts))


def crop_box(resolved: Resolved, geo: Geometry) -> tuple[int, int, int, int] | None:
    """The cut's crop in this capture's pixels (left, top, right, bottom), even-sized."""
    if resolved.crop is None:
        return None
    x, y, w, h = (round(v * geo.scale) for v in resolved.crop)
    w, h = max(2, w - w % 2), max(2, h - h % 2)
    return x, y, x + w, y + h


def out_size(resolved: Resolved, geo: Geometry) -> tuple[int, int]:
    """What the encoder is fed: the kept frame, or the cut's crop of it."""
    box = crop_box(resolved, geo)
    return geo.out_size if box is None else (box[2] - box[0], box[3] - box[1])


def composed(resolved: Resolved, take: Take, geo: Geometry,
             composer: Composer) -> Iterator[Image.Image]:
    """Every output frame, in order, streamed."""
    decoded = prefetch_map(lambda t: load_frame(take, geo, t), play_order(resolved.frames))
    box = crop_box(resolved, geo)
    cur_src: int | None = None
    cur: Image.Image | None = None
    try:
        for i, f in enumerate(resolved.frames):
            if f.src is not None and f.src != cur_src:
                got_src, cur = next(decoded)
                # Not an assert: `python -O` strips those, and a frame out of order is a
                # wrong picture in a deliverable.
                if got_src != f.src:
                    raise PumpError(f"frame {i}: decoded source {got_src}, the cut wants "
                                    f"{f.src}")
                cur_src = f.src
            im = composer.compose(i, cur)
            yield im if box is None else im.crop(box)
    finally:
        decoded.close()         # a failed encode must not leave decodes running


# --------------------------------------------------------------------------------------------
# Writing


class Sink(Protocol):
    def write(self, im: Image.Image) -> None: ...
    def close(self) -> None: ...


class FfmpegSink:
    """One ffmpeg process fed rgb24 on stdin. stderr goes to a log file (a pipe would fill
    and deadlock a long encode); its tail is in any error."""

    def __init__(self, cmd: Sequence[str], size: tuple[int, int], log: pathlib.Path) -> None:
        self.cmd, self.size, self.log = list(cmd), size, log
        self._err: IO[bytes] = open(log, "wb")  # noqa: SIM115 - closed in close()
        self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=self._err)
        self.frames = 0

    def _tail(self) -> str:
        self._err.flush()
        return self.log.read_text(errors="replace")[-2000:].strip()

    def write(self, im: Image.Image) -> None:
        if im.size != self.size or im.mode != "RGB":
            raise PumpError(f"frame {self.frames} is {im.mode} {im.size}, the encoder wants "
                            f"RGB {self.size}")
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.write(im.tobytes())
        except BrokenPipeError:
            self.proc.wait()
            raise PumpError(f"ffmpeg quit at frame {self.frames} (exit "
                            f"{self.proc.returncode}): {self._tail()}") from None
        self.frames += 1

    def close(self) -> None:
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.close()
        except BrokenPipeError:
            pass
        rc = self.proc.wait()
        tail = self._tail()
        self._err.close()
        if rc != 0:
            raise PumpError(f"ffmpeg exit {rc}: {tail}")

    def kill(self) -> None:
        self.proc.kill()
        self.proc.wait()
        self._err.close()


def raw_input(size: tuple[int, int], fps: int) -> list[str]:
    return ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}",
            "-framerate", str(fps), "-i", "-"]


#: x264's default GOP; raised only as far as the longest hold needs.
DEFAULT_GOP = 250


def keyframe_args(resolved: Resolved) -> list[str]:
    """IDR on every segment's first output frame, and a GOP longer than any hold (freeze or
    card) so the encoder's own cadence never puts one inside a still (module docstring)."""
    starts = sorted({s.out[0] for s in resolved.segments if s.out[1] > s.out[0]})
    holds = [s.out[1] - s.out[0] for s in resolved.segments if s.kind in ("freeze", "card")]
    gop = max([DEFAULT_GOP, *(h + 1 for h in holds)])
    expr = "+".join(f"eq(n,{f})" for f in starts) or "eq(n,0)"
    return ["-force_key_frames", f"expr:{expr}", "-g", str(gop)]


def master_cmd(ff: str, size: tuple[int, int], fps: int, out: pathlib.Path,
               keyframes: Sequence[str] = ()) -> list[str]:
    """The video-only master picture; build.py muxes the sound on with -c:v copy.
    `keyframes` is keyframe_args(resolved)."""
    return [ff, "-hide_banner", "-nostdin", "-y", *raw_input(size, fps), "-an", *X264,
            *keyframes, "-vf", TO_BT709, *BT709_TAGS, "-movflags", "+faststart", str(out)]


def loop_cmd(ff: str, size: tuple[int, int], fps: int, mp4: pathlib.Path, gif: pathlib.Path,
             loop_size: tuple[int, int], gif_w: int) -> list[str]:
    """The portal loop (no audio track at all - `-an`, and the input has none) and the
    README GIF, from ONE rgb stream. setpts=N/50 re-times every source frame to 2 cs, and
    `-r 50` keeps ffmpeg from dropping or duplicating any to fit its own idea of the rate."""
    lw, lh = loop_size
    graph = (f"[0:v]split=2[m][g];"
             f"[m]scale={lw}:{lh}:flags=lanczos,{TO_BT709}[mo];"
             f"[g]scale={gif_w}:-1:flags=lanczos,setpts=N/({GIF_FPS}*TB),split=2[g1][g2];"
             f"[g1]{GIF_PALETTE}[p];[g2][p]{GIF_USE}[go]")
    return [ff, "-hide_banner", "-nostdin", "-y", *raw_input(size, fps),
            "-filter_complex", graph,
            "-map", "[mo]", "-an", *X264, *BT709_TAGS, "-movflags", "+faststart", str(mp4),
            "-map", "[go]", "-r", str(GIF_FPS), "-loop", "0", "-f", "gif", str(gif)]


@dataclasses.dataclass(frozen=True)
class PumpStats:
    frames: int
    sources: int


def pump(resolved: Resolved, take: Take, geo: Geometry, composer: Composer, sink: Sink,
         progress: Callable[[int, int], None] | None = None) -> PumpStats:
    """Stream every output frame into `sink`. On any failure the sink is killed if it can
    be, so no half-written ffmpeg lingers."""
    n = len(resolved.frames)
    try:
        for i, im in enumerate(composed(resolved, take, geo, composer)):
            sink.write(im)
            if progress is not None and (i % 240 == 0 or i == n - 1):
                progress(i + 1, n)
    except BaseException:
        kill = getattr(sink, "kill", None)
        if kill is not None:
            kill()
        raise
    sink.close()
    return PumpStats(n, len(set(play_order(resolved.frames))))
