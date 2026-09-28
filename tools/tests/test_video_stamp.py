"""tools/video/stamp.py without Factorio: frames stamped here with Pillow, the way the director's
rectangles land in a real frame, then decoded back - through JPEG, since that is what a take is.

The frame-level half is the proof video.sh's verify rests on: a shifted take (every file one
tick off) and a duplicated frame (one render under two names) must both FAIL, and the counts
that tie frames, track.jsonl and events.jsonl together must hold. A take's frames are 1920 wide;
these are 640 (the stamp needs ~540), which keeps the suite fast without changing the geometry.
"""

import io
import itertools
import json
import pathlib
import random
import re
import shutil

import pytest
from PIL import Image
from video import stamp

REPO = pathlib.Path(__file__).resolve().parents[2]
CAMERA_LUA = REPO / "tools" / "harness" / "jamaltron-video" / "camera.lua"
VIDEO_SH = REPO / "tools" / "video.sh"


def picture(w: int, h: int, seed: int) -> Image.Image:
    """A busy frame: blocky noise over the whole picture and band, like grass under the stamp."""
    rng = random.Random(seed)
    small = Image.new("RGB", (w // 8, h // 8))
    small.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256))
                   for _ in range((w // 8) * (h // 8))])
    return small.resize((w, h), Image.NEAREST)


def jpeg(im: Image.Image, quality: int = 90) -> Image.Image:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def test_the_geometry_is_the_directors():
    """camera.lua draws the stamp, stamp.py reads it: the same five numbers, or every frame of
    every take reads as a mismatch (or worse, decodes wrong and still looks plausible)."""
    src = CAMERA_LUA.read_text()
    m = re.search(r"M\.SQUARE, M\.PITCH, M\.X0, M\.BITS = (\d+), (\d+), (\d+), (\d+)", src)
    assert m, "camera.lua no longer declares the stamp geometry on one line"
    assert tuple(map(int, m.groups())) == (stamp.SQUARE, stamp.PITCH, stamp.X0, stamp.BITS)
    sh = VIDEO_SH.read_text()
    assert f"BAND={stamp.BAND}\n" in sh and "RES_H=1104\n" in sh


def test_the_stamp_fits_the_band_and_the_frame():
    boxes = stamp.squares(1104)
    assert len(boxes) == stamp.BITS + 2
    assert all(1104 - stamp.BAND <= top and bottom <= 1104 for _, top, _, bottom in boxes)
    assert boxes[-1][2] <= 1920
    assert all(a[2] <= b[0] for a, b in itertools.pairwise(boxes))     # no two squares touch


@pytest.mark.parametrize("tick", [0, 1, 2, 60, 1023, 3827, 65535, (1 << stamp.BITS) - 1])
def test_every_bit_round_trips(tick):
    im = picture(640, 200, tick)
    stamp.draw(im, tick)
    assert stamp.decode(im) == tick


def test_a_full_frame_round_trips_through_jpeg():
    """The real size at the real quality, and well below it: the 8x8 core of a 16 px square is
    nowhere near JPEG's ringing."""
    for tick, quality in [(3827, 90), (1234, 50), (777, 25)]:
        im = picture(1920, 1104, tick)
        stamp.draw(im, tick)
        assert stamp.decode(jpeg(im, quality)) == tick, quality


def test_a_frame_with_no_stamp_reads_none():
    assert stamp.decode(jpeg(picture(640, 200, 7))) is None
    black = Image.new("RGB", (640, 200))
    assert stamp.decode(black) is None                  # all squares dark: no white sentinel


def test_a_tick_past_the_bits_is_refused():
    with pytest.raises(ValueError):
        stamp.draw(picture(640, 200, 1), 1 << stamp.BITS)


# --------------------------------------------------------------------------------------------
# A whole take on disk


def make_take(root: pathlib.Path, first: int = 10, last: int = 29, *, same_picture=(),
              shift: int = 0) -> pathlib.Path:
    """frames/f<tick>.jpg stamped with their own tick (+ `shift`), a track line per frame, and the
    events the verify step reads. `same_picture` ticks share one background (a scene that held
    still)."""
    frames = root / "frames"
    frames.mkdir(parents=True)
    for t in range(first, last + 1):
        im = picture(640, 200, 0 if t in same_picture else t)
        stamp.draw(im, t + shift)
        im.save(frames / f"f{t:07d}.jpg", quality=90)
    (root / "track.jsonl").write_text(
        "".join(json.dumps({"tick": t, "cam": [0, 0], "zoom": 2}) + "\n" for t in range(first, last + 1)))
    evs = [{"tick": first, "ev": "capture_start"}, {"tick": first, "ev": "beat", "name": "loop"},
           {"tick": last, "ev": "beat", "name": "wrap"}, {"tick": last, "ev": "capture_end"}]
    (root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs))
    return root


def test_a_clean_take_verifies(tmp_path):
    rep = stamp.verify_take(make_take(tmp_path / "t"), jobs=1)
    assert rep.ok, rep.summary()
    assert (rep.frames.frames, rep.track_lines, rep.captured) == (20, 20, 20)
    assert "OK - 20 frames (ticks 10..29), 0 mismatches, 0 duplicates, 0 gaps" in rep.summary()


def test_a_shifted_take_fails_every_frame(tmp_path):
    """Every file showing the tick before its name - what the G.1 spike saw at game speed 4
    without force_render. The count, the names and the track are all perfect; only the stamps
    know."""
    rep = stamp.verify_take(make_take(tmp_path / "t", shift=-1), jobs=1)
    assert not rep.ok
    assert len(rep.frames.mismatches) == 20
    assert rep.frames.mismatches[0] == ("f0000010", 9)
    assert not rep.frames.duplicates and not rep.problems


def test_a_duplicated_frame_fails(tmp_path):
    """One render written under two names: the second holds the first's stamp."""
    take = make_take(tmp_path / "t")
    shutil.copy(take / "frames" / "f0000015.jpg", take / "frames" / "f0000016.jpg")
    rep = stamp.verify_take(take, jobs=1)
    assert not rep.ok
    assert rep.frames.mismatches == [("f0000016", 15)]
    assert rep.frames.duplicates == [(15, ["f0000015", "f0000016"])]
    assert (15, 16) in rep.frames.identical


def test_a_missing_frame_is_a_gap_and_a_count(tmp_path):
    take = make_take(tmp_path / "t")
    (take / "frames" / "f0000020.jpg").unlink()
    rep = stamp.verify_take(take, jobs=1)
    assert not rep.ok
    assert rep.frames.gaps == [20]
    assert any("counts disagree: 19 frames, 20 track lines, 20 captured ticks" in p for p in rep.problems)


def test_the_track_must_be_the_frames(tmp_path):
    take = make_take(tmp_path / "t")
    lines = (take / "track.jsonl").read_text().splitlines()
    (take / "track.jsonl").write_text("\n".join(lines[:-1]) + "\n")
    rep = stamp.verify_take(take, jobs=1)
    assert not rep.ok
    assert any("counts disagree" in p for p in rep.problems)
    assert any("track.jsonl's ticks are not the frames' ticks" in p for p in rep.problems)


def test_events_out_of_tick_order_fail(tmp_path):
    take = make_take(tmp_path / "t")
    evs = (take / "events.jsonl").read_text().splitlines()
    (take / "events.jsonl").write_text("\n".join([evs[2], *evs[:2], *evs[3:]]) + "\n")
    rep = stamp.verify_take(take, jobs=1)
    assert not rep.ok
    assert "events.jsonl is not in tick order" in rep.problems


def test_frames_outside_the_capture_window_fail(tmp_path):
    take = make_take(tmp_path / "t", first=10, last=29)
    evs = [{"tick": 11, "ev": "capture_start"}, {"tick": 29, "ev": "capture_end"}]
    (take / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs))
    rep = stamp.verify_take(take, jobs=1)
    assert not rep.ok
    assert any("frames span 10..29, capture_start..capture_end is 11..29" in p for p in rep.problems)


def test_a_scene_that_held_still_is_reported_not_failed(tmp_path):
    """MEASURED on the loop take (pinned water, fixed camera): consecutive frames can be pixel-
    identical above the band at the torso bob's turning points. Each still carries its own
    stamp, so each is its own tick's render: reported, never a failure."""
    rep = stamp.verify_take(make_take(tmp_path / "t", same_picture={14, 15, 16}), jobs=1)
    assert rep.ok, rep.summary()
    assert rep.frames.identical == [(14, 15), (15, 16)]


@pytest.mark.parametrize("damage", ["truncated", "not-a-jpeg"])
def test_an_unreadable_frame_is_a_mismatch_in_verify_json_not_a_traceback(tmp_path, capsys,
                                                                            damage):
    """A frame cut short (a full disk, a killed game) or not an image at all: the verdict still
    lands in verify.json, which is what video.sh's failure message points at."""
    take = make_take(tmp_path / "t")
    f = take / "frames" / "f0000015.jpg"
    data = f.read_bytes()
    f.write_bytes(data[: len(data) // 2] if damage == "truncated" else b"not a jpeg at all")
    assert stamp.main(["verify", str(take), "--jobs", "1"]) == 1
    verdict = json.loads((take / "verify.json").read_text())
    assert verdict["ok"] is False and verdict["mismatches"] == [["f0000015", None]]
    assert "MISMATCH f0000015: stamp reads None" in capsys.readouterr().err


def test_parallel_and_serial_reads_agree(tmp_path):
    take = make_take(tmp_path / "t", first=0, last=99)
    files = stamp.frame_files(take / "frames")
    assert stamp.read_all(files, jobs=1) == stamp.read_all(files, jobs=4)


def test_the_cli_writes_verify_json_and_sets_the_exit_code(tmp_path, capsys):
    good = make_take(tmp_path / "good")
    assert stamp.main(["verify", str(good), "--jobs", "1"]) == 0
    assert json.loads((good / "verify.json").read_text())["ok"] is True
    assert "stamp: OK" in capsys.readouterr().out
    bad = make_take(tmp_path / "bad")
    shutil.copy(bad / "frames" / "f0000012.jpg", bad / "frames" / "f0000013.jpg")
    assert stamp.main(["verify", str(bad), "--jobs", "1"]) == 1
    verdict = json.loads((bad / "verify.json").read_text())
    assert verdict["ok"] is False and verdict["mismatch_count"] == 1
    assert "MISMATCH f0000013: stamp reads 12" in capsys.readouterr().err
    assert stamp.main(["verify", str(tmp_path / "nope")]) == 2
