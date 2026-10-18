"""G.5-G.8: video/build.py end to end on a FAKE take, no Factorio: a real master mp4 with
sound, the loop mp4 with NO audio stream, the GIF's delays, the caption cross-check failing
before anything encodes, the verify.json gate, the silent-audio refusal and its override, the
staged outputs a late failure never half-replaces, the forced keyframes, and every CLI refusal.
Every ffprobe assertion here is independent of the build's own checks.

Skipped as a module when there is no ffmpeg (a runner without it); the CLI refusals do not
need it and live in their own tests above the skip line's reach (they fail before ffmpeg)."""

from __future__ import annotations

import dataclasses
import json
import pathlib
import subprocess
import sys

import pytest
from PIL import Image

from video_fake import ev, loop_events, make_take, write_cut
from video import build
from video import captions as cap
from video import pump as pm


def _have_ffmpeg() -> bool:
    try:
        pm.ffmpeg()
        pm.ffprobe()
        return True
    except pm.PumpError:
        return False


needs_ffmpeg = pytest.mark.skipif(not _have_ffmpeg(), reason="no ffmpeg/ffprobe")


@pytest.fixture(scope="module")
def fonts() -> cap.Fonts:
    try:
        return cap.Fonts.factorio()
    except cap.FontError:
        return cap.Fonts.fallback()


def line(tick: int, row: str) -> dict[str, object]:
    return ev(tick, "line", row=row, channel="speech", forced=True, x=0, y=0)


MAIN_EVENTS = [ev(5, "beat", name="hop1"), line(10, "jump.01"),
               ev(20, "takeoff", x=0, y=0, distance=8, land_tick=50, peak=3),
               ev(35, "apex", x=4, y=0), ev(50, "landing", x=8, y=0), line(50, "land.03")]

MAIN_CUT = """
fps = 60
[[segment]]
from = "capture_start"
to = "takeoff#1-5"
[[segment]]
from = "takeoff#1-5"
to = "landing#1+5"
speed = 0.5
[[segment]]
from = "landing#1+5"
to = "capture_end-20"
[[segment]]
at = "apex#1"
hold = 0.2
audio = "mute"
[[overlay]]
card = "title"
from_out = 0.0
to_out = 0.2
[[card]]
card = "end"
seconds = 0.3
"""


def main_take(tmp_path: pathlib.Path, **kw: object) -> pathlib.Path:
    make_take(tmp_path / "take", first=0, last=119, events=MAIN_EVENTS,
              stills=("lake-apex", "beached"), **kw)  # type: ignore[arg-type]
    return tmp_path / "take"


def ffprobe(path: pathlib.Path) -> dict:
    out = subprocess.run([pm.ffprobe(), "-v", "error", "-show_streams", "-show_format",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


class SineMixer:
    """Stands in for the audio builder's mix.render: records its arguments, writes a real
    AAC-LC 48 kHz tone as long as frames.json says."""

    def __init__(self) -> None:
        self.calls: list[tuple[pathlib.Path, ...]] = []

    def __call__(self, events, frames, track, out) -> None:
        self.calls.append((events, frames, track, out))
        d = json.loads(pathlib.Path(frames).read_text())
        secs = len(d["frames"]) / d["fps"]
        subprocess.run([pm.ffmpeg(), "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"sine=frequency=440:sample_rate=48000:duration={secs}",
                        *build.AUDIO_ARGS, str(out)], check=True)


# ------------------------------------------------------------------------------ master

@needs_ffmpeg
def test_the_master_builds_end_to_end(tmp_path, fonts):
    take, out, mixer = main_take(tmp_path), tmp_path / "out", SineMixer()
    cut = write_cut(tmp_path / "main.toml", MAIN_CUT)
    rep = build.run(take, cut, out, fonts=fonts, mixer=mixer)

    frames = json.loads((out / "frames.json").read_text())
    n = len(frames["frames"])
    assert n == rep.frames == 15 + 80 + 44 + 12 + 18
    # the mixer got the contract's four paths - frames.json and the .m4a in the staging dir
    [(events, frames_at, track, audio_at)] = mixer.calls
    assert (events, track) == (take / "events.jsonl", take / "track.jsonl")
    assert frames_at.name == "frames.json" and audio_at.name == "audio.m4a"
    assert frames_at.parent == audio_at.parent and frames_at.parent.parent == out
    assert frames_at.parent.name.startswith(".building-")
    assert rep.audio == "mix.render" and not rep.warnings

    pic = ffprobe(out / "picture.mp4")
    assert [s["codec_type"] for s in pic["streams"]] == ["video"]
    m = ffprobe(out / "jamaltron.mp4")
    v = [s for s in m["streams"] if s["codec_type"] == "video"]
    a = [s for s in m["streams"] if s["codec_type"] == "audio"]
    assert len(v) == 1 and len(a) == 1
    v, a = v[0], a[0]
    assert (v["codec_name"], v["profile"], v["width"], v["height"]) == ("h264", "High", 192, 108)
    assert v["r_frame_rate"] == "60/1" and int(v["nb_frames"]) == n
    assert (v["color_space"], v["color_primaries"], v["color_transfer"],
            v["color_range"], v["pix_fmt"]) == ("bt709", "bt709", "bt709", "tv", "yuv420p")
    assert float(v["duration"]) == pytest.approx(n / 60, abs=1 / 60)
    assert (a["codec_name"], a["profile"], a["sample_rate"]) == ("aac", "LC", "48000")
    assert float(m["format"]["duration"]) == pytest.approx(n / 60, abs=0.1)

    assert sorted(p.name for p in (out / "stills").iterdir()) == ["beached.png", "lake-apex.png"]
    report = json.loads((out / "build.json").read_text())
    assert report["captions"]["problems"] == []
    assert set(report["captions"]["shown"]) == {"jump.01", "land.03"}
    assert report["outputs"]["jamaltron.mp4"]["color_primaries"] == "bt709"
    assert report["verified"].startswith("ok: 120 frames")
    # staged, then promoted: nothing is left in a .building dir
    assert not [p for p in out.iterdir() if p.name.startswith(".building")]


def _i_frames(path: pathlib.Path) -> list[int]:
    out = subprocess.run([pm.ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "frame=pict_type", "-of", "csv=p=0", str(path)], capture_output=True,
                         text=True, check=True).stdout.split()
    return [k for k, t in enumerate(out) if t.startswith("I")]


@needs_ffmpeg
def test_every_segment_starts_on_a_keyframe_and_no_hold_has_one_inside(tmp_path, fonts):
    """MEASURED on the first master: x264's 250-frame GOP put an IDR 1.1 s into the 4.5 s freeze
    and the still frame re-grained. Here a 5 s freeze outlasts that GOP on purpose."""
    cut = write_cut(tmp_path / "m.toml", MAIN_CUT.replace("hold = 0.2", "hold = 5.0"))
    rep = build.run(main_take(tmp_path), cut, tmp_path / "out", fonts=fonts, mixer=SineMixer())
    frames = json.loads((tmp_path / "out" / "frames.json").read_text())
    i_frames = set(_i_frames(tmp_path / "out" / "jamaltron.mp4"))
    segs = frames["segments"]
    assert {s["out"][0] for s in segs} <= i_frames
    for s in segs:
        if s["kind"] in ("freeze", "card"):
            inside = {f for f in i_frames if s["out"][0] < f < s["out"][1]}
            assert not inside, (s, sorted(inside))
    assert rep.frames > 300          # the freeze alone is longer than x264's default GOP


@needs_ffmpeg
def test_a_mixer_that_raises_fails_the_master_by_default(tmp_path, fonts):
    def boom(*_: object) -> None:
        raise RuntimeError("the wind bed is missing")

    out = tmp_path / "out"
    with pytest.raises(build.BuildError, match="no audio: mix.render raised(.|\n)*"
                                               "--allow-silent-audio"):
        build.run(main_take(tmp_path), write_cut(tmp_path / "m.toml", MAIN_CUT), out,
                  fonts=fonts, mixer=boom)
    assert not (out / "jamaltron.mp4").exists()


@needs_ffmpeg
def test_allow_silent_audio_builds_a_loud_silent_track(tmp_path, fonts, capsys):
    def boom(*_: object) -> None:
        raise RuntimeError("the wind bed is missing")

    rep = build.run(main_take(tmp_path), write_cut(tmp_path / "m.toml", MAIN_CUT),
                    tmp_path / "out", fonts=fonts, mixer=boom, allow_silent_audio=True)
    assert rep.audio.startswith("SILENT FALLBACK: mix.render raised")
    err = capsys.readouterr().err
    assert "SILENT AUDIO TRACK" in err and "the wind bed is missing" in err and "!!!!" in err
    a = [s for s in ffprobe(tmp_path / "out" / "jamaltron.mp4")["streams"]
         if s["codec_type"] == "audio"]
    assert a and a[0]["codec_name"] == "aac" and a[0]["sample_rate"] == "48000"


def test_no_mixer_at_all_is_refused_before_anything_encodes(tmp_path, fonts):
    out = tmp_path / "out"
    with pytest.raises(build.BuildError, match="no audio: no mixer given"):
        build.run(main_take(tmp_path), write_cut(tmp_path / "m.toml", MAIN_CUT),
                  out, fonts=fonts, mixer=None)
    assert not out.exists()


@dataclasses.dataclass
class FakeMixReport:
    out: pathlib.Path
    unplaced: dict[str, int]
    warnings: list[str]


@needs_ffmpeg
def test_the_mixers_report_lands_in_build_json(tmp_path, fonts):
    def mixer(events, frames, track, out) -> FakeMixReport:
        SineMixer()(events, frames, track, out)
        return FakeMixReport(out, {"jamaltron-landing-thud": 1}, ["loudness: -18 LUFS"])

    out = tmp_path / "out"
    rep = build.run(main_take(tmp_path), write_cut(tmp_path / "m.toml", MAIN_CUT), out,
                    fonts=fonts, mixer=mixer)
    report = json.loads((out / "build.json").read_text())
    assert report["mix"]["unplaced"] == {"jamaltron-landing-thud": 1}
    assert report["mix"]["out"].endswith("audio.m4a")
    assert "mix: loudness: -18 LUFS" in rep.warnings


@needs_ffmpeg
def test_a_late_failure_leaves_the_previous_build_untouched(tmp_path, fonts):
    """The first cut wrote frames.json up front and build.json only at the end: a build that
    died late left new media beside the OLD build.json, which said it had passed."""
    take, cut, out = main_take(tmp_path), write_cut(tmp_path / "m.toml", MAIN_CUT), tmp_path / "o"
    build.run(take, cut, out, fonts=fonts, mixer=SineMixer())
    before = {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()}

    def boom(*_: object) -> None:
        raise RuntimeError("mixer died after the picture")

    with pytest.raises(build.BuildError, match="partial outputs left in .*building"):
        build.run(take, cut, out, fonts=fonts, mixer=boom)
    assert {p.name: p.read_bytes() for p in out.iterdir() if p.is_file()} == before
    partial = [p for p in out.iterdir() if p.name.startswith(".building-")]
    assert len(partial) == 1 and (partial[0] / "picture.mp4").is_file()


def test_a_missing_mix_module_is_a_reason_not_a_crash(monkeypatch):
    monkeypatch.setitem(sys.modules, "video.mix", None)
    fn, why = build.default_mixer()
    assert fn is None and why == "video/mix.py does not exist yet"


def test_a_mix_module_without_render_is_named(monkeypatch):
    import types
    monkeypatch.setitem(sys.modules, "video.mix", types.ModuleType("video.mix"))
    assert build.default_mixer() == (None, "video.mix has no render()")


# -------------------------------------------------------------------------------- loop

@needs_ffmpeg
def test_the_loop_builds_a_mute_mp4_and_a_50fps_gif(tmp_path, fonts):
    make_take(tmp_path / "take", first=0, last=430, events=loop_events(), said=["jump.04"])
    loop_cut = build.TOOLS / "video" / "loop.toml"
    rep = build.run(tmp_path / "take", loop_cut, tmp_path / "out", fonts=fonts)
    assert rep.captions == {"skipped": "deliver = loop: no captions"}

    info = ffprobe(tmp_path / "out" / build.LOOP_MP4)
    assert [s["codec_type"] for s in info["streams"]] == ["video"]     # NO audio track
    v = info["streams"][0]
    assert (v["width"], v["height"], v["r_frame_rate"], int(v["nb_frames"])) == (96, 54, "60/1",
                                                                                182)
    assert v["color_primaries"] == "bt709"
    assert (tmp_path / "out" / build.LOOP_MP4).stat().st_size < build.LOOP_MAX_BYTES

    with Image.open(tmp_path / "out" / build.LOOP_GIF) as g:
        assert g.n_frames == 182 and g.size[0] == 72 and g.info.get("loop") == 0   # 720 at 0.1
        delays = set()
        for k in range(g.n_frames):
            g.seek(k)
            delays.add(g.info["duration"])
    assert delays == {20}                                   # every source frame, 2 cs


# ------------------------------------------------------------------ the caption check

def test_a_caption_the_mod_never_said_fails_before_anything_encodes(tmp_path, capsys):
    take = main_take(tmp_path, said=["jump.01", "land.09"])
    out = tmp_path / "out"
    rc = build.main(["--take", str(take), "--cut", str(write_cut(tmp_path / "m.toml", MAIN_CUT)),
                     "--out", str(out)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "CAPTIONED BUT NEVER SAID: land.03" in err and "SAID BUT NOT CAPTIONED: land.09" in err
    assert "--allow-caption-mismatch" in err
    assert not (out / "picture.mp4").exists()


@needs_ffmpeg
def test_the_override_builds_and_says_so(tmp_path, fonts, capsys):
    take = main_take(tmp_path, said=["jump.01"])
    rep = build.run(take, write_cut(tmp_path / "m.toml", MAIN_CUT), tmp_path / "out",
                    fonts=fonts, mixer=SineMixer(), allow_caption_mismatch=True)
    assert rep.captions["overridden"] is True
    assert any("caption cross-check FAILED" in w for w in rep.warnings)
    assert "--allow-caption-mismatch: building anyway" in capsys.readouterr().err
    assert (tmp_path / "out" / "jamaltron.mp4").is_file()


def test_a_row_replaced_on_its_own_tick_passes_the_check(tmp_path, capsys):
    """The director's `said` event: the mod rolled land.09, the forced land.03 replaced it on
    the same tick, so land.09 is in the mod's log but was on screen for no frame."""
    evs = [*MAIN_EVENTS, ev(50, "said", row="land.09", channel="speech", replaced_by="land.03",
                            x=8, y=0)]
    make_take(tmp_path / "take", first=0, last=119, events=evs,
              said=["jump.01", "land.09", "land.03"])
    rc = build.main(["--take", str(tmp_path / "take"), "--cut",
                     str(write_cut(tmp_path / "m.toml", MAIN_CUT)), "--out",
                     str(tmp_path / "out"), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "2 rows captioned: jump.01, land.03; never on screen, per the take: land.09" in out


# -------------------------------------------------------------------------------- the CLI

def test_dry_run_resolves_and_checks_without_encoding(tmp_path, capsys):
    """Into <out>/dry-run/, never beside a real master (the first cut overwrote the real
    frames.json and build.json next to the previous mp4)."""
    take, out = main_take(tmp_path), tmp_path / "out"
    rc = build.main(["--take", str(take), "--cut", str(write_cut(tmp_path / "m.toml", MAIN_CUT)),
                     "--out", str(out), "--dry-run"])
    assert rc == 0, capsys.readouterr().err
    assert sorted(p.name for p in out.iterdir()) == ["dry-run"]
    assert sorted(p.name for p in (out / "dry-run").iterdir()) == ["build.json", "frames.json"]


def test_a_dry_run_without_ffmpeg_warns_where_a_real_build_refuses(tmp_path, capsys,
                                                                    monkeypatch):
    """No ffmpeg anywhere (a CI runner): the dry run still resolves and checks, and names the
    missing audio; the real build refuses before staging anything."""
    monkeypatch.setenv("FFMPEG", str(tmp_path / "no-ffmpeg"))
    take, out = main_take(tmp_path), tmp_path / "out"
    argv = ["--take", str(take), "--cut", str(write_cut(tmp_path / "m.toml", MAIN_CUT)),
            "--out", str(out)]
    assert build.main([*argv, "--dry-run"]) == 0, capsys.readouterr().err
    report = json.loads((out / "dry-run" / "build.json").read_text())
    assert any(w.startswith("no audio: ") for w in report["warnings"])
    capsys.readouterr()
    assert build.main(argv) != 0
    assert "no audio: " in capsys.readouterr().err
    assert sorted(p.name for p in out.iterdir()) == ["dry-run"]


@pytest.mark.parametrize("verdict,why", [
    (None, "no verify.json in the take"),
    ({"ok": False, "frames": 120, "mismatch_count": 3}, "says the take FAILED its stamp check"),
    ({"ok": True, "frames": 119}, "checked 119 frames, the track has 120 lines"),
])
def test_a_take_that_is_not_verified_is_refused_unless_told(tmp_path, capsys, verdict, why):
    """video.sh leaves a FAILED take on disk under the same takes/ naming as a good one."""
    take = main_take(tmp_path)
    if verdict is None:
        (take / "verify.json").unlink()
    else:
        (take / "verify.json").write_text(json.dumps(verdict))
    cut = write_cut(tmp_path / "m.toml", MAIN_CUT)
    argv = ["--take", str(take), "--cut", str(cut), "--out", str(tmp_path / "out"), "--dry-run"]
    assert build.main(argv) == 2
    err = capsys.readouterr().err
    assert why in err and "--unverified" in err
    assert not (tmp_path / "out").exists()
    assert build.main([*argv, "--unverified"]) == 0
    report = json.loads((tmp_path / "out" / "dry-run" / "build.json").read_text())
    assert report["verified"].startswith("UNVERIFIED (--unverified): ")
    assert any(w.startswith("UNVERIFIED TAKE") for w in report["warnings"])


@pytest.mark.parametrize("args,why", [
    (["--take", "{tmp}/nope", "--cut", "{cut}"], "--take {tmp}/nope: not a directory"),
    (["--take", "{take}", "--cut", "{tmp}/nope.toml"], "no such file"),
    (["--take", "{take}", "--cut", "{cut}", "--out", "tools/video/out"],
     "inside the repo but not under render-out/"),
    (["--take", "{take}", "--cut", "{badcut}"], "missing anchor 'break#1'"),
])
def test_cli_refusals_exit_2_before_anything_is_made(tmp_path, capsys, args, why):
    take = main_take(tmp_path)
    cut = write_cut(tmp_path / "m.toml", MAIN_CUT)
    bad = write_cut(tmp_path / "bad.toml", '[[segment]]\nfrom = "capture_start"\nto = "break#1"\n')
    sub = {"{tmp}": str(tmp_path), "{take}": str(take), "{cut}": str(cut), "{badcut}": str(bad)}
    argv = []
    for a in args:
        for k, v in sub.items():
            a = a.replace(k, v)
        argv.append(a)
    for k, v in sub.items():
        why = why.replace(k, v)
    assert build.main(argv) == 2
    assert why in capsys.readouterr().err
    assert not (build.REPO / "tools" / "video" / "out").exists()


def test_missing_source_frames_are_counted_and_named(tmp_path, capsys):
    take = main_take(tmp_path)
    (take / "frames" / "f0000033.jpg").unlink()
    rc = build.main(["--take", str(take), "--cut", str(write_cut(tmp_path / "m.toml", MAIN_CUT)),
                     "--out", str(tmp_path / "out")])
    assert rc == 2
    assert "not in" in (err := capsys.readouterr().err) and "f0000033.jpg" in err
