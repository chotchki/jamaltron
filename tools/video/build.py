"""G.5-G.8: a verified take + a cut file -> the deliverables, in one command.

    uv run --directory tools python -m video.build \\
        --take ../render-out/video/takes/main-<stamp> --cut video/main.toml
    uv run --directory tools python -m video.build \\
        --take ../render-out/video/takes/loop-<stamp> --cut video/loop.toml

The cut's `deliver` picks what comes out (default --out: render-out/video/out/<cut name>/):
  master  frames.json, picture.mp4 (video only), audio.m4a, jamaltron.mp4 (the 1080p60 master,
          h264 + AAC-LC 160k 48 kHz, bt709-tagged), stills/, build.json
  loop    frames.json, jamaltron-jump.mp4 (the portal loop: 960x540 60 fps, NO audio track,
          < 1 MB), jamaltron-jump.gif (the README GIF: every source frame at 2 cs, 720 wide,
          target <= 3 MB), stills/, build.json
Deliverable sizes are the spec at a 1920-wide capture and scale with it, so a test take at
192x110 builds a 96x54 loop and a 96-wide GIF through the very same code.

ORDER, cheapest refusal first: every argument, the take's two logs, the take's VERIFY.JSON
(video.sh's stamp verdict: ok, and as many frames as the track - a take whose stamps failed
stays on disk under the same takes/ naming as a good one, so the build refuses it unless
--unverified, which build.json records), the cut against them, every source frame the cut shows
on disk, the fonts, and the CAPTION CROSS-CHECK all run before ffmpeg starts. The cross-check:
every row the mod itself logged as said (`jamaltron
speech <unit> <row>` in the take's run.log; the director turns speech debug on) is a caption in
this video, or the take PROVES it never reached the screen (a `said` event: replaced by a
forced row on its own tick; or a `line` the cut drops or time-lapses, listed as a note) - and
nothing is captioned that the mod did not say. Anything else is exit 1 with every row named;
--allow-caption-mismatch builds anyway and says so in the report.

AUDIO is the audio builder's `video.mix.render(events, frames, track, out)`, imported LAZILY
and handed the picture's own install and ffmpeg (captions' $FACTORIO_DATA rule, pump.ffmpeg()),
so sound and picture never resolve different tools. A master with no sound FAILS by default:
if the module is absent, broken or raises, that is exit 1 - --allow-silent-audio builds it on a
SILENT track instead, with a banner on stderr and the reason in build.json (a picture to judge
beats a crash, but never by accident). The mixer's own report - loudness, every cue, what
aggregation and the time-lapse dropped, what landed on no frame - goes into build.json `mix`.

STAGED: everything is built into <out>/.building-<pid>/ and moved into <out> only once every
check has passed, build.json last - a build that fails late (a check, the loop over 1 MB, a
mux error) leaves the previous deliverables and THEIR build.json untouched, and the partial
outputs in the .building dir for inspection. --dry-run writes its frames.json and build.json to
<out>/dry-run/, never beside a real master.

Every output is ffprobed before the build calls itself done: the master's size, 60/1 fps,
frame count, duration, yuv420p limited range and the bt709 tags; the loop's size, fps, frame
count, bytes and the ABSENCE of any audio stream; the GIF's frame count, every delay and
width. A check that fails is exit 1.
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import importlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import traceback
from collections.abc import Callable
from typing import Any

from PIL import Image

from video import captions as cap
from video import pump as pm
from video.timeline import (CutError, Geometry, Resolved, Take, TakeError, load_cut, load_take,
                            resolve)

TOOLS = pathlib.Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
RENDER_OUT = REPO / "render-out"
DEFAULT_OUT = RENDER_OUT / "video" / "out"

MASTER, PICTURE, AUDIO = "jamaltron.mp4", "picture.mp4", "audio.m4a"
LOOP_MP4, LOOP_GIF = "jamaltron-jump.mp4", "jamaltron-jump.gif"
#: At a 1920-wide capture. The GIF is storyboard A's "~720 px wide": with loop.toml's 1280x720
#: crop (Jamal 1.5x larger than the whole frame showed him) a 960-wide GIF came out 4.88 MB,
#: 800 wide 3.40, 720 wide 2.72 (MEASURED on loop-20260927-221740; dither and a 128-colour
#: palette moved it 0-1 MB - the bytes are in the moving shark). 720 is 1:1 in a README column.
LOOP_SIZE, GIF_W = (960, 540), 720
LOOP_MAX_BYTES = 1_000_000              # the portal description autoplays it for every visitor
GIF_TARGET_BYTES = 3_000_000            # GitHub's 10 MB cap; 3 MB so the README loads fast
AUDIO_ARGS = ("-c:a", "aac", "-profile:a", "aac_low", "-b:a", "160k", "-ar", "48000")

Mixer = Callable[[pathlib.Path, pathlib.Path, pathlib.Path, pathlib.Path], object]


class BuildError(RuntimeError):
    """A check failed after the inputs were accepted (exit 1)."""


class UsageError(ValueError):
    """Bad arguments, take or cut (exit 2): nothing was built."""


def banner(msg: str) -> None:
    bar = "!" * 78
    print(f"{bar}\nbuild: {msg}\n{bar}", file=sys.stderr, flush=True)


@dataclasses.dataclass
class Report:
    take: str
    cut: str
    deliver: str
    out: str
    frames: int = 0
    duration_s: float = 0.0
    sources: int = 0
    verified: str = ""
    captions: dict[str, object] = dataclasses.field(default_factory=dict)
    audio: str = ""
    mix: dict[str, object] = dataclasses.field(default_factory=dict)
    outputs: dict[str, dict[str, object]] = dataclasses.field(default_factory=dict)
    stills: list[str] = dataclasses.field(default_factory=list)
    warnings: list[str] = dataclasses.field(default_factory=list)
    seconds: dict[str, float] = dataclasses.field(default_factory=dict)

    def warn(self, msg: str, loud: bool = False) -> None:
        self.warnings.append(msg)
        if loud:
            banner(msg)
        else:
            print(f"build: WARNING {msg}", file=sys.stderr, flush=True)

    def write(self, path: pathlib.Path) -> None:
        path.write_text(json.dumps(dataclasses.asdict(self), indent=1, default=str) + "\n",
                        encoding="utf-8")


# --------------------------------------------------------------------------------------------
# Paths


def _existing(p: pathlib.Path, *bases: pathlib.Path) -> pathlib.Path:
    """A relative path as given (against the CWD), else against each base in turn - so the
    documented `--cut video/main.toml` works from tools/ and from the repo root alike."""
    if p.is_absolute() or p.exists():
        return p.resolve()
    for b in bases:
        if (b / p).exists():
            return (b / p).resolve()
    return p.resolve()


def out_dir_for(arg: str | None, cut: pathlib.Path) -> pathlib.Path:
    """--out (relative to the CWD, like every other path); default render-out/video/out/<cut
    name>. Inside the repo it must be under render-out/ (gitignored): a 20 MB master in a
    tracked dir is one `git add -A` from history."""
    out = pathlib.Path(arg).resolve() if arg else DEFAULT_OUT / cut.stem
    if out.is_relative_to(REPO) and not out.is_relative_to(RENDER_OUT):
        raise UsageError(f"--out {out} is inside the repo but not under render-out/ "
                         "(gitignored); big outputs live there")
    return out


# --------------------------------------------------------------------------------------------
# ffprobe


def probe(path: pathlib.Path) -> dict[str, Any]:
    res = subprocess.run([pm.ffprobe(), "-v", "error", "-show_streams", "-show_format",
                          "-of", "json", str(path)], capture_output=True, text=True)
    if res.returncode != 0:
        raise BuildError(f"ffprobe {path}: {res.stderr.strip()}")
    data: dict[str, Any] = json.loads(res.stdout)
    return data


def _streams(info: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [s for s in info.get("streams", []) if s.get("codec_type") == kind]


def check_video(path: pathlib.Path, size: tuple[int, int], fps: int, frames: int,
                audio: bool) -> dict[str, object]:
    """Every property a deliverable promises, read back off the file. Returns the summary
    for build.json; raises BuildError listing every mismatch at once."""
    info = probe(path)
    v, a = _streams(info, "video"), _streams(info, "audio")
    bad: list[str] = []
    if len(v) != 1:
        raise BuildError(f"{path.name}: {len(v)} video streams")
    s = v[0]
    want = {"codec_name": "h264", "width": size[0], "height": size[1],
            "r_frame_rate": f"{fps}/1", "avg_frame_rate": f"{fps}/1", "pix_fmt": "yuv420p",
            "color_space": "bt709", "color_primaries": "bt709", "color_transfer": "bt709",
            "color_range": "tv", "nb_frames": str(frames)}
    for k, w in want.items():
        if s.get(k) != w:
            bad.append(f"{k} {s.get(k)!r}, want {w!r}")
    vdur = float(s.get("duration", "nan"))
    if not abs(vdur - frames / fps) <= 1.5 / fps:
        bad.append(f"video duration {vdur:.3f} s, want {frames / fps:.3f}")
    summary: dict[str, object] = {k: s.get(k) for k in want}
    summary.update(bytes=path.stat().st_size, duration=vdur,
                   format_duration=float(info.get("format", {}).get("duration", "nan")))
    if audio:
        if len(a) != 1:
            bad.append(f"{len(a)} audio streams, want 1")
        else:
            aw = {"codec_name": "aac", "profile": "LC", "sample_rate": "48000"}
            for k, w in aw.items():
                if a[0].get(k) != w:
                    bad.append(f"audio {k} {a[0].get(k)!r}, want {w!r}")
            summary["audio"] = {k: a[0].get(k) for k in (*aw, "channels", "bit_rate")}
    elif a:
        bad.append(f"{len(a)} audio stream(s); this deliverable must have NO audio track")
    if bad:
        raise BuildError(f"{path.name}: " + "; ".join(bad))
    return summary


def check_gif(path: pathlib.Path, width: int, frames: int) -> dict[str, object]:
    bad: list[str] = []
    with Image.open(path) as g:
        n, size, loop = getattr(g, "n_frames", 1), g.size, g.info.get("loop")
        delays = set()
        for k in range(n):
            g.seek(k)
            delays.add(g.info.get("duration"))
    want_ms = round(1000 / pm.GIF_FPS)
    if n != frames:
        bad.append(f"{n} frames, want {frames} (one per source frame)")
    if delays != {want_ms}:
        bad.append(f"delays {sorted(d for d in delays if d is not None)} ms, want only "
                   f"{want_ms}")
    if size[0] != width:
        bad.append(f"width {size[0]}, want {width}")
    if loop != 0:
        bad.append(f"loop {loop!r}, want 0 (forever)")
    if bad:
        raise BuildError(f"{path.name}: " + "; ".join(bad))
    return {"frames": n, "delay_ms": want_ms, "width": size[0], "height": size[1],
            "bytes": path.stat().st_size}


# --------------------------------------------------------------------------------------------
# Audio


def default_mixer() -> tuple[Mixer | None, str]:
    """The audio builder's mix.render, imported only now, bound to the install and the ffmpeg
    the picture uses (MEASURED by the review: with ffmpeg only on PATH, the picture built and
    the mix found nothing, so the master went out silent)."""
    try:
        mod = importlib.import_module("video.mix")
    except ModuleNotFoundError as e:
        if e.name == "video.mix":
            return None, "video/mix.py does not exist yet"
        return None, f"video.mix failed to import: {e!r}"
    except Exception as e:  # noqa: BLE001 - any import-time failure means no mixer
        return None, f"video.mix failed to import: {e!r}"
    render = getattr(mod, "render", None)
    if not callable(render):
        return None, "video.mix has no render()"
    data = pathlib.Path(os.environ.get(cap.FACTORIO_DATA_ENV) or cap.DEFAULT_FACTORIO_DATA)
    try:
        ff = pm.ffmpeg()
    except pm.PumpError as e:
        return None, str(e)
    return functools.partial(render, data_dir=data, ffmpeg=ff), ""


def silent_track(out: pathlib.Path, seconds: float) -> None:
    subprocess.run([pm.ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{seconds:.6f}",
                    *AUDIO_ARGS, str(out)], check=True, capture_output=True)


def make_audio(take: Take, frames_json: pathlib.Path, out: pathlib.Path, duration: float,
               mixer: Mixer | None, why_none: str, report: Report,
               allow_silent: bool) -> None:
    reason = why_none
    if mixer is not None:
        out.unlink(missing_ok=True)
        try:
            ret = mixer(take.root / "events.jsonl", frames_json, take.root / "track.jsonl", out)
        except Exception:  # noqa: BLE001 - the mixer is someone else's code
            reason = "mix.render raised:\n" + traceback.format_exc().rstrip()
        else:
            if out.is_file() and out.stat().st_size > 0:
                report.audio = "mix.render"
                # Its whole report - loudness, the cue list, what aggregation and the time-lapse
                # dropped, what landed on no frame - is the only record of what the sound did.
                if dataclasses.is_dataclass(ret) and not isinstance(ret, type):
                    report.mix = dataclasses.asdict(ret)
                for w in getattr(ret, "warnings", None) or []:
                    report.warn(f"mix: {w}")
                return
            reason = f"mix.render returned but wrote no {out.name}"
    if not allow_silent:
        raise BuildError(f"no audio: {reason}\n(--allow-silent-audio builds a silent master "
                         "anyway; never for anything that ships)")
    report.warn(f"SILENT AUDIO TRACK - {reason}", loud=True)
    report.audio = f"SILENT FALLBACK: {reason.splitlines()[0]}"
    silent_track(out, duration)


def mux(picture: pathlib.Path, audio: pathlib.Path, out: pathlib.Path,
        duration: float) -> None:
    """Picture + sound -> the master, video stream-copied. The sound is copied too when it
    already is AAC-LC 48 kHz (no second lossy generation), else re-encoded to that. -t cuts
    an audio tail longer than the picture; a shorter one just ends early."""
    a = _streams(probe(audio), "audio")
    if not a:
        raise BuildError(f"{audio.name}: no audio stream")
    ok = (a[0].get("codec_name"), a[0].get("profile"), a[0].get("sample_rate")) == (
        "aac", "LC", "48000")
    acodec = ["-c:a", "copy"] if ok else list(AUDIO_ARGS)
    res = subprocess.run([pm.ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                          "-i", str(picture), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                          "-c:v", "copy", *acodec, "-t", f"{duration:.6f}",
                          "-movflags", "+faststart", str(out)], capture_output=True, text=True)
    if res.returncode != 0:
        raise BuildError(f"mux: {res.stderr.strip()}")


# --------------------------------------------------------------------------------------------
# The build


def _scaled(n: int, geo: Geometry) -> int:
    """A deliverable dimension at this capture's scale, kept even for yuv420p."""
    return max(2, round(n * geo.scale / 2) * 2)


def check_frames(take: Take, resolved: Resolved) -> Geometry:
    srcs = resolved.sources()
    missing = [t for t in srcs if not take.frame_path(t).is_file()]
    if missing:
        raise UsageError(f"{len(missing)} of {len(srcs)} source frame(s) the cut shows are "
                         f"not in {take.frames_dir}, first f{missing[0]:07d}.jpg")
    with Image.open(take.frame_path(srcs[0])) as im:
        return Geometry.from_capture(*im.size)


def caption_check(take: Take, resolved: Resolved, lines: dict[str, str], report: Report,
                  allow: bool) -> None:
    track = cap.CaptionTrack.from_events(take.events, lines)
    missing = [] if take.run_log.is_file() else [
        f"no {take.run_log.name} in the take: nothing to check the captions against"]
    logged = cap.rows_logged(take.run_log) if not missing else {}
    a = cap.audit(resolved, track, take.events, logged)
    problems = missing + a.problems
    report.captions = {"shown": a.shown, "lines": a.lines, "replaced": a.replaced,
                       "logged": a.logged, "problems": problems, "notes": a.notes,
                       "overridden": bool(problems and allow)}
    for note in a.notes:
        print(f"build: caption note: {note}")
    if not problems:
        extra = sorted(set(a.logged) - set(a.shown))
        print(f"build: captions == the mod's speech log ({len(a.shown)} rows captioned: "
              f"{', '.join(sorted(a.shown)) or 'none'}"
              + (f"; never on screen, per the take: {', '.join(extra)}" if extra else "") + ")")
        return
    msg = "caption cross-check FAILED:\n  " + "\n  ".join(problems)
    if not allow:
        raise BuildError(msg + "\n(--allow-caption-mismatch builds anyway)")
    report.warn(msg + "\n(--allow-caption-mismatch: building anyway)", loud=True)


def copy_stills(take: Take, out: pathlib.Path, geo: Geometry, report: Report) -> None:
    if not take.stills_dir.is_dir():
        return
    dest = out / "stills"
    dest.mkdir(exist_ok=True)
    want = (geo.cap_w, geo.out_h)
    for p in sorted(take.stills_dir.glob("*.png")):
        shutil.copy2(p, dest / p.name)
        report.stills.append(p.name)
        with Image.open(p) as im:
            if im.size != want:
                report.warn(f"still {p.name} is {im.size[0]}x{im.size[1]}, want "
                            f"{want[0]}x{want[1]}")


def check_verified(take: Take, allow: bool, report: Report) -> None:
    """The take's stamp verdict, video.sh's verify.json: ok, and over as many frames as the
    track has lines. A missing, failed or stale one is a UsageError unless `allow`."""
    path = take.root / "verify.json"
    problem = ""
    try:
        v = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        problem = (f"no {path.name} in the take (video.sh writes it; `python -m video.stamp "
                   "verify <take>` re-runs the check)")
    except (OSError, json.JSONDecodeError) as e:
        problem = f"{path.name} is unreadable: {e}"
    else:
        if not isinstance(v, dict) or v.get("ok") is not True:
            got = v if not isinstance(v, dict) else {
                k: v.get(k) for k in ("mismatch_count", "duplicates", "gap_count", "problems")}
            problem = f"{path.name} says the take FAILED its stamp check: {got}"
        elif v.get("frames") != len(take.track):
            problem = (f"{path.name} checked {v.get('frames')} frames, the track has "
                       f"{len(take.track)} lines: it is not this take's verdict")
    if not problem:
        report.verified = f"ok: {len(take.track)} frames, stamps verified ({path.name})"
        return
    if not allow:
        raise UsageError(f"{problem} - --unverified builds from it anyway")
    report.verified = f"UNVERIFIED (--unverified): {problem}"
    report.warn(f"UNVERIFIED TAKE - {problem}", loud=True)


def promote(work: pathlib.Path, out: pathlib.Path) -> None:
    """Move a finished build from its staging dir into `out`, build.json LAST: until that
    rename, `out`'s build.json still describes whatever `out` held before."""
    items = sorted(work.iterdir(), key=lambda p: (p.name == "build.json", p.name))
    for p in items:
        dest = out / p.name
        if p.is_dir() and dest.is_dir():
            shutil.rmtree(dest)
        os.replace(p, dest)
    work.rmdir()


def run(take_dir: pathlib.Path, cut_path: pathlib.Path, out: pathlib.Path, *,
        allow_caption_mismatch: bool = False, allow_silent_audio: bool = False,
        unverified: bool = False, dry_run: bool = False, fonts: cap.Fonts | None = None,
        mixer: Mixer | None | str = "import") -> Report:
    """The whole build. `fonts` and `mixer` are injectable for tests; the CLI never passes
    them (mixer="import" = the lazy import of video.mix)."""
    t0 = time.monotonic()
    try:
        take = load_take(take_dir)
        cut = load_cut(cut_path)
        resolved = resolve(cut, take)
    except (TakeError, CutError) as e:
        raise UsageError(str(e)) from None
    report = Report(str(take.root), str(cut.path), resolved.deliver, str(out),
                    frames=len(resolved.frames), duration_s=round(resolved.duration, 3),
                    sources=len(resolved.sources()))
    check_verified(take, unverified, report)
    for w in take.warnings:
        report.warn(w)
    geo = check_frames(take, resolved)
    lines = cap.load_lines()
    if resolved.captions:
        caption_check(take, resolved, lines, report, allow_caption_mismatch)
    else:
        report.captions = {"skipped": f"deliver = {resolved.deliver}: no captions"}
    if isinstance(mixer, str):
        mix_fn, why = default_mixer() if resolved.deliver == "master" else (None, "")
    else:
        mix_fn, why = mixer, "no mixer given"
    if resolved.deliver == "master" and mix_fn is None and not allow_silent_audio:
        # Known before a minute of encoding, so refused before it. A dry run encodes nothing:
        # it reports the gap instead, and so still runs where there is no ffmpeg at all (CI's
        # runner - MEASURED, the dry-run tests failed there on the audio refusal alone).
        if not dry_run:
            raise BuildError(f"no audio: {why}\n(--allow-silent-audio builds a silent master "
                             "anyway; never for anything that ships)")
        report.warn(f"no audio: {why} (a real build refuses this without --allow-silent-audio)")

    if not dry_run:
        fonts = fonts or cap.Fonts.factorio()       # a missing font refuses before staging
    work = out / ("dry-run" if dry_run else f".building-{os.getpid()}")
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    frames_json = work / "frames.json"
    resolved.write(frames_json)
    print(f"build: {len(resolved.frames)} frames ({resolved.duration:.2f} s) from "
          f"{report.sources} source frames at {geo.cap_w}x{geo.cap_h} -> {frames_json}")
    report.seconds["resolve"] = round(time.monotonic() - t0, 2)
    if dry_run:
        report.out = str(work)
        report.write(work / "build.json")
        return report
    try:
        _encode(take, resolved, geo, work, report, fonts or cap.Fonts.factorio(), lines,
                mix_fn, why, allow_silent_audio)
    except (BuildError, pm.PumpError) as e:
        raise BuildError(f"{e}\n(partial outputs left in {work}; {out} is untouched)") from None
    report.seconds["total"] = round(time.monotonic() - t0, 2)
    report.write(work / "build.json")
    promote(work, out)
    return report


def _encode(take: Take, resolved: Resolved, geo: Geometry, out: pathlib.Path, report: Report,
            fonts: cap.Fonts, lines: dict[str, str], mix_fn: Mixer | None, why: str,
            allow_silent_audio: bool) -> None:
    """Every encode and every check on the outputs, into the staging dir `out`."""
    frames_json = out / "frames.json"
    composer = pm.composer_for(resolved, take, geo, fonts, lines)
    ff = pm.ffmpeg()
    size = pm.out_size(resolved, geo)

    def progress(i: int, n: int) -> None:
        print(f"build: frame {i}/{n}", flush=True)

    t = time.monotonic()
    if resolved.deliver == "master":
        pic = out / PICTURE
        sink = pm.FfmpegSink(pm.master_cmd(ff, size, resolved.fps, pic,
                                           pm.keyframe_args(resolved)), size,
                             out / "picture.ffmpeg.log")
        pm.pump(resolved, take, geo, composer, sink, progress)
        report.seconds["picture"] = round(time.monotonic() - t, 2)
        report.outputs[PICTURE] = check_video(pic, size, resolved.fps, len(resolved.frames),
                                              audio=False)
        t = time.monotonic()
        make_audio(take, frames_json, out / AUDIO, resolved.duration, mix_fn, why, report,
                   allow_silent_audio)
        report.seconds["audio"] = round(time.monotonic() - t, 2)
        mux(pic, out / AUDIO, out / MASTER, resolved.duration)
        report.outputs[MASTER] = check_video(out / MASTER, size, resolved.fps,
                                             len(resolved.frames), audio=True)
    else:
        loop_size = (_scaled(LOOP_SIZE[0], geo), _scaled(LOOP_SIZE[1], geo))
        gif_w = _scaled(GIF_W, geo)
        mp4, gif = out / LOOP_MP4, out / LOOP_GIF
        sink = pm.FfmpegSink(pm.loop_cmd(ff, size, resolved.fps, mp4, gif, loop_size, gif_w),
                             size, out / "loop.ffmpeg.log")
        pm.pump(resolved, take, geo, composer, sink, progress)
        report.seconds["picture"] = round(time.monotonic() - t, 2)
        report.outputs[LOOP_MP4] = check_video(mp4, loop_size, resolved.fps,
                                               len(resolved.frames), audio=False)
        if mp4.stat().st_size >= LOOP_MAX_BYTES:
            raise BuildError(f"{mp4.name} is {mp4.stat().st_size} bytes; the portal loop "
                             f"must stay under {LOOP_MAX_BYTES}")
        report.outputs[LOOP_GIF] = check_gif(gif, gif_w, len(resolved.frames))
        if gif.stat().st_size > GIF_TARGET_BYTES:
            report.warn(f"{gif.name} is {gif.stat().st_size / 1e6:.2f} MB, over the "
                        f"{GIF_TARGET_BYTES / 1e6:.0f} MB target", loud=True)
        report.audio = "none (the loop has no audio track)"

    copy_stills(take, out, geo, report)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m video.build",
                                 description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--take", required=True, help="a verified take dir (frames/, events.jsonl, "
                    "track.jsonl, run.log, stills/)")
    ap.add_argument("--cut", required=True, help="the cut file (video/main.toml, "
                    "video/loop.toml)")
    ap.add_argument("--out", help="output dir; inside the repo it must be under render-out/ "
                    "(default render-out/video/out/<cut name>)")
    ap.add_argument("--dry-run", action="store_true", help="resolve, check the frames and the "
                    "captions, write frames.json + build.json to <out>/dry-run/; encode nothing")
    ap.add_argument("--allow-caption-mismatch", action="store_true",
                    help="build even when the captions and the mod's speech log disagree")
    ap.add_argument("--allow-silent-audio", action="store_true",
                    help="build a master on a silent track when the mixer is missing or fails "
                    "(default: that is a failure)")
    ap.add_argument("--unverified", action="store_true",
                    help="build from a take whose verify.json is missing or failed (recorded "
                    "in build.json)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    ns = parse_args(argv)
    try:
        take = _existing(pathlib.Path(ns.take), REPO)
        cut = _existing(pathlib.Path(ns.cut), TOOLS, REPO)
        if not take.is_dir():
            raise UsageError(f"--take {ns.take}: not a directory")
        if not cut.is_file():
            raise UsageError(f"--cut {ns.cut}: no such file")
        out = out_dir_for(ns.out, cut)
        report = run(take, cut, out, allow_caption_mismatch=ns.allow_caption_mismatch,
                     allow_silent_audio=ns.allow_silent_audio, unverified=ns.unverified,
                     dry_run=ns.dry_run)
    except (UsageError, cap.FontError) as e:
        print(f"build: {e}", file=sys.stderr)
        return 2
    except (BuildError, pm.PumpError, TakeError) as e:
        print(f"build: FAILED: {e}", file=sys.stderr)
        return 1
    done = "dry run" if ns.dry_run else ", ".join(report.outputs) or "nothing"
    tail = f" WITH {len(report.warnings)} WARNING(S)" if report.warnings else ""
    print(f"build: done{tail}: {done} in {report.out} ({report.seconds.get('total', 0)} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
