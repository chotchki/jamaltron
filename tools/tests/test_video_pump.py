"""G.5: video/pump.py without Factorio - the band crop, play order and prefetch, every
compositing layer on a FAKE take (each frame's colour encodes its tick, its band is magenta),
the loop cut's crop, and the ffmpeg command lines the contract fixes (plus the keyframes)."""

from __future__ import annotations

import os
import threading
import time

import pytest
from PIL import Image, ImageStat

from video_fake import BAND_RGB, SMALL, colour_of, ev, make_take, tick_of, write_cut
from video import captions as cap
from video import cards as cards_mod
from video import pump as pm
from video import timeline as tl


@pytest.fixture(scope="module")
def fonts() -> cap.Fonts:
    try:
        return cap.Fonts.factorio()
    except cap.FontError:
        return cap.Fonts.fallback()


class ListSink:
    def __init__(self) -> None:
        self.frames: list[Image.Image] = []
        self.closed = False

    def write(self, im: Image.Image) -> None:
        self.frames.append(im.copy())

    def close(self) -> None:
        self.closed = True


def line(tick: int, row: str) -> dict[str, object]:
    return ev(tick, "line", row=row, channel="speech", forced=True, x=0, y=0)


GEO = tl.Geometry.from_capture(*SMALL)


# ------------------------------------------------------------------------------ reading

def test_the_crop_keeps_rows_above_the_stamp_band():
    im = Image.new("RGB", SMALL, (10, 20, 30))
    im.paste(BAND_RGB, (0, 108, 192, 110))
    out = pm.crop_band(im, GEO)
    assert out.size == (192, 108)
    assert BAND_RGB not in {out.getpixel((x, y)) for x in range(0, 192, 7) for y in (0, 107)}


def test_the_crop_at_full_size_is_1080_of_1104():
    g = tl.Geometry.from_capture(1920, 1104)
    im = Image.new("RGB", (1920, 1104), (0, 0, 0))
    im.paste(BAND_RGB, (0, 1080, 1920, 1104))
    out = pm.crop_band(im, g)
    assert out.size == (1920, 1080) and out.getpixel((0, 1079)) == (0, 0, 0)


def test_a_frame_of_the_wrong_size_is_refused():
    with pytest.raises(tl.TakeError, match="frame is 100x50"):
        pm.crop_band(Image.new("RGB", (100, 50)), GEO)


def test_a_missing_frame_names_its_tick(tmp_path):
    make_take(tmp_path / "t", first=0, last=3, events=[], frames=False)
    take = tl.load_take(tmp_path / "t")
    with pytest.raises(tl.TakeError, match="f0000002.jpg: missing \\(the cut shows tick 2\\)"):
        pm.load_frame(take, GEO, 2)


def test_play_order_collapses_consecutive_repeats_only():
    frames = [tl.OutFrame(s, 0) for s in (5, 5, 6, 6, 7, None, None)]
    assert pm.play_order(frames) == [5, 6, 7]
    assert pm.play_order([tl.OutFrame(s, 0) for s in (5, 6, 5)]) == [5, 6, 5]


def test_prefetch_keeps_order_and_a_bounded_window():
    live, peak, lock = 0, 0, threading.Lock()

    def slow(x: int) -> int:
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.002 * (x % 3))
        with lock:
            live -= 1
        return x * 10

    got = []
    for x, y in pm.prefetch_map(slow, range(40), workers=4, ahead=5):
        got.append((x, y))
    assert got == [(x, x * 10) for x in range(40)]
    assert peak <= 4


# --------------------------------------------------------------------------- compositing

CUT = """
[[segment]]
from = "capture_start"
to = "capture_start+30"
[[segment]]
from = "capture_start+30"
to = "capture_start+60"
speed = 5.0
tag = "5x"
[[segment]]
at = "capture_start+70"
hold = 0.1
[[overlay]]
card = "title"
from_out = 0.0
to_out = 0.1
[[card]]
card = "end"
seconds = 1.0
"""


@pytest.fixture(scope="module")
def pumped(tmp_path_factory, fonts):
    root = tmp_path_factory.mktemp("pump")
    make_take(root / "take", first=0, last=99,
              events=[line(10, "jump.01"), line(60, "land.03")])
    take = tl.load_take(root / "take")
    r = tl.resolve(tl.load_cut(write_cut(root / "c.toml", CUT)), take)
    comp = pm.composer_for(r, take, GEO, fonts)
    sink = ListSink()
    stats = pm.pump(r, take, GEO, comp, sink)
    return r, sink, stats


def _dev(im: Image.Image, box: tuple[int, int, int, int], rgb: tuple[int, int, int]) -> int:
    """How many pixels in `box` are far (> 40 levels) from the flat `rgb`."""
    crop = im.crop(box)
    return sum(1 for p in crop.get_flattened_data()
               if max(abs(a - b) for a, b in zip(p, rgb)) > 40)


CAPTION_BOX = (40, 25, 152, 54)    # above his torso at (96, 55): the bubble's home
TAG_BOX = (140, 0, 192, 16)        # top-right corner


def test_every_frame_is_the_right_source_tick_cropped(pumped):
    r, sink, stats = pumped
    assert sink.closed and len(sink.frames) == len(r.frames) == stats.frames
    for i, (f, im) in enumerate(zip(r.frames, sink.frames)):
        assert im.size == (192, 108) and im.mode == "RGB"
        if f.src is None:
            continue
        corner = im.getpixel((2, 105))
        assert tick_of(corner, f.src) == f.src, f"output frame {i}"
        assert BAND_RGB not in {im.getpixel((x, 107)) for x in range(0, 192, 5)}
    assert stats.sources == len(set(pm.play_order(r.frames)))


def test_the_caption_is_up_from_its_tick_and_never_in_a_timelapse(pumped):
    r, sink, _ = pumped
    for i, f in enumerate(r.frames):
        seg = r.segments[f.seg]
        if f.src is None:
            continue
        n = _dev(sink.frames[i], CAPTION_BOX, colour_of(f.src))
        if i >= 6 and f.src < 10:                          # before jump.01 (title gone)
            assert n == 0, i
        elif 10 <= f.src < 30:                             # jump.01 up, real time
            assert n > 20, i
        elif seg.timelapse:                                # 5x: suppressed
            assert n == 0, i
        elif seg.kind == "freeze":                         # land.03 (said at 60) held
            assert n > 20, i


def test_the_tag_shows_only_on_its_segment(pumped):
    r, sink, _ = pumped
    for i, f in enumerate(r.frames):
        if f.src is None or i < 6:
            continue
        n = _dev(sink.frames[i], TAG_BOX, colour_of(f.src))
        assert (n > 10) == (r.segments[f.seg].tag == "5x"), i


def test_the_title_is_full_on_frame_0_and_gone_after_its_window(pumped):
    _, sink, _ = pumped
    top = (0, 0, 192, 30)
    assert _dev(sink.frames[0], top, colour_of(0)) > 200     # frame 0 is the poster
    assert _dev(sink.frames[6], top, colour_of(6)) == 0


def test_the_end_card_is_the_last_frame_dimmed_after_a_crossfade(pumped):
    r, sink, _ = pumped
    card = r.segments[-1]
    first, last = sink.frames[card.out[0]], sink.frames[card.out[1] - 1]
    base = colour_of(70)
    dim = tuple(round(c * cards_mod.DIM) for c in base)
    assert max(abs(a - b) for a, b in zip(last.getpixel((2, 105)), dim)) <= 4
    def lum(im: Image.Image) -> float:
        return sum(ImageStat.Stat(im).mean)

    assert lum(sink.frames[card.out[0] - 1]) > lum(first) > lum(last)


# -------------------------------------------------------------------------------- encode

def test_master_cmd_carries_the_contract_encode():
    cmd = pm.master_cmd("ffmpeg", (1920, 1080), 60, tl.pathlib.Path("o.mp4"))
    s = " ".join(cmd)
    for part in ("-f rawvideo -pix_fmt rgb24 -s 1920x1080 -framerate 60 -i -",
                 "-c:v libx264 -preset slow -crf 20 -profile:v high -level 4.2",
                 "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
                 "-colorspace bt709 -color_primaries bt709 -color_trc bt709",
                 "-movflags +faststart", "-an"):
        assert part in s, part


def test_keyframes_land_on_segment_starts_and_the_gop_outlasts_every_hold(tmp_path):
    make_take(tmp_path / "t", first=0, last=99, events=[], frames=False)
    take = tl.load_take(tmp_path / "t")
    r = tl.resolve(tl.load_cut(write_cut(tmp_path / "c.toml", CUT.replace("hold = 0.1",
                                                                          "hold = 4.5"))), take)
    args = pm.keyframe_args(r)
    expr = args[args.index("-force_key_frames") + 1]
    starts = [s.out[0] for s in r.segments]
    assert expr == "expr:" + "+".join(f"eq(n,{f})" for f in starts)
    # the 4.5 s freeze is 270 frames, the end card 60: x264's own 250 would land inside it
    assert int(args[args.index("-g") + 1]) == 271
    cmd = pm.master_cmd("ffmpeg", (1920, 1080), 60, tl.pathlib.Path("o.mp4"), args)
    assert cmd[cmd.index("-force_key_frames") + 1] == expr


def test_a_short_cut_keeps_the_default_gop(pumped):
    r, _, _ = pumped
    assert pm.keyframe_args(r)[-2:] == ["-g", str(pm.DEFAULT_GOP)]


def test_the_loop_crop_is_applied_last_and_scaled_to_the_capture(tmp_path, fonts):
    """loop.toml's [340, 240, 1280, 720] at the fake take's 0.1 scale is 128x72 from (34, 24).
    Each fake frame is flat, so paint a marker at the crop's top-left to see where it went."""
    make_take(tmp_path / "t", first=0, last=20, events=[])
    for t in range(0, 21):
        f = tmp_path / "t" / "frames" / f"f{t:07d}.jpg"
        with Image.open(f) as im:
            im = im.convert("RGB")
        im.paste((255, 255, 255), (34, 24, 42, 32))
        im.save(f, quality=95)
    take = tl.load_take(tmp_path / "t")
    cut = 'deliver = "loop"\ncrop = [340, 240, 1280, 720]\n[[segment]]\nfrom = "capture_start"\n' \
          'to = "capture_end"\n'
    r = tl.resolve(tl.load_cut(write_cut(tmp_path / "c.toml", cut)), take)
    assert pm.crop_box(r, GEO) == (34, 24, 162, 96) and pm.out_size(r, GEO) == (128, 72)
    sink = ListSink()
    pm.pump(r, take, GEO, pm.composer_for(r, take, GEO, fonts), sink)
    assert {im.size for im in sink.frames} == {(128, 72)}
    assert min(sink.frames[5].getpixel((2, 2))) > 220          # the marker, now at the corner
    assert tick_of(sink.frames[5].getpixel((60, 60)), 5) == 5   # and the right frame


def test_a_decode_out_of_order_is_a_pump_error_not_an_assert(tmp_path, fonts, monkeypatch):
    """`python -O` strips an assert; a frame out of order would then reach a deliverable."""
    make_take(tmp_path / "t", first=0, last=20, events=[])
    take = tl.load_take(tmp_path / "t")
    r = tl.resolve(tl.load_cut(write_cut(tmp_path / "c.toml", '[[segment]]\nfrom = '
                                         '"capture_start"\nto = "capture_end"\n')), take)
    real = pm.prefetch_map

    def shuffled(fn, items, *a, **kw):
        items = list(items)
        items[3], items[4] = items[4], items[3]
        return real(fn, items, *a, **kw)

    monkeypatch.setattr(pm, "prefetch_map", shuffled)
    with pytest.raises(pm.PumpError, match="frame 3: decoded source 4, the cut wants 3"):
        list(pm.composed(r, take, GEO, pm.composer_for(r, take, GEO, fonts)))


def test_loop_cmd_has_no_audio_and_the_gif_recipe():
    cmd = pm.loop_cmd("ffmpeg", (1920, 1080), 60, tl.pathlib.Path("l.mp4"),
                      tl.pathlib.Path("l.gif"), (960, 540), 960)
    mp4_at, gif_at = cmd.index("l.mp4"), cmd.index("l.gif")
    assert "-an" in cmd[:mp4_at] and cmd.count("-map") == 2
    graph = cmd[cmd.index("-filter_complex") + 1]
    for part in ("scale=960:540", "palettegen=stats_mode=diff", "diff_mode=rectangle",
                 "setpts=N/(50*TB)", "scale=960:-1"):
        assert part in graph, part
    assert cmd[mp4_at + 1:gif_at] == ["-map", "[go]", "-r", "50", "-loop", "0", "-f", "gif"]


def test_a_named_ffmpeg_that_is_missing_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setenv(pm.FFMPEG_ENV, str(tmp_path / "no-ffmpeg"))
    with pytest.raises(pm.PumpError, match="is not an executable"):
        pm.ffmpeg()


def _have_ffmpeg() -> bool:
    try:
        pm.ffmpeg()
        return True
    except pm.PumpError:
        return False


@pytest.mark.skipif(not _have_ffmpeg(), reason="no ffmpeg")
def test_an_ffmpeg_failure_carries_its_log(tmp_path):
    sink = pm.FfmpegSink([pm.ffmpeg(), "-hide_banner", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", "4x4", "-i", "-", "-c:v", "no-such-codec", str(tmp_path / "x.mp4")],
                         (4, 4), tmp_path / "ff.log")
    with pytest.raises(pm.PumpError, match="no-such-codec|Unknown encoder"):
        for _ in range(200):
            sink.write(Image.new("RGB", (4, 4)))
        sink.close()


def test_a_wrong_sized_frame_never_reaches_ffmpeg(tmp_path):
    if not _have_ffmpeg():
        pytest.skip("no ffmpeg")
    sink = pm.FfmpegSink([pm.ffmpeg(), "-hide_banner", "-f", "rawvideo", "-pix_fmt", "rgb24",
                          "-s", "4x4", "-i", "-", "-f", "null", os.devnull], (4, 4),
                         tmp_path / "ff.log")
    with pytest.raises(pm.PumpError, match="the encoder wants RGB \\(4, 4\\)"):
        sink.write(Image.new("RGB", (5, 4)))
    sink.kill()


# ---------------------------------------------------------------------------------- cards

def test_the_card_copy_is_what_chotchki_signed_off():
    assert (cards_mod.TITLE, cards_mod.TITLE_LINE) == (
        "JAMALTRON", "Jamal is so very sorry. Jamal must jump!")
    assert cards_mod.END_LINE == ("Jamal must give his thanks, Mr. Engineer. And his sorries. "
                                  "All of them.")
    assert cards_mod.CREDITS == (
        "3D model copyright Pig Scales Studio via RenderHub",
        "Unofficial, non-commercial fan work of Matt Dinniman's Dungeon Crawler Carl. Not "
        "affiliated with or endorsed by Dinniman, his publishers or Soundbooth Theater.",
        "Factorio 2.1 mod, Space Age optional · github.com/chotchki/jamaltron",
        "Factorio by Wube Software · factorio.com")
    assert cards_mod.CREDIT_PX >= 28
    assert cards_mod.CAPTION_RGB == (255, 230, 192) and cards_mod.ORANGE_RGB == (250, 168, 56)


FULL = tl.Geometry.from_capture(1920, 1104)


def test_the_title_sits_in_the_top_third(fonts):
    layer = cards_mod.Cards(FULL, fonts).layer("title", "overlay")
    text = layer.getchannel("A").point([255 if v > 200 else 0 for v in range(256)])
    box = text.getbbox()
    assert layer.size == (1920, 1080) and box is not None and box[3] <= 360, box


def test_the_end_card_text_fits_the_frame(fonts):
    layer = cards_mod.Cards(FULL, fonts).layer("end", "card")
    box = layer.getchannel("A").getbbox()
    assert box is not None
    assert box[0] >= 100 and box[1] >= 100 and box[2] <= 1820 and box[3] <= 980, box
