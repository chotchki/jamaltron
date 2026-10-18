"""tools/video.sh without Factorio: every argument check, the profile refusals, and the whole run's
plumbing - fixture, dry run, graphics take, the move into the take dir and the stamp verify -
against a FAKE factorio that hands back a take this suite stamped itself.

Each refusal is judged before anything is created or launched, so these point FACTORIO_BIN at a
missing path: a check that let a bad value through stops at "factorio binary not executable"
instead of its own message and fails here. The positive controls prove good arguments get as far
as the binary check.
"""

import json
import os
import pathlib
import random
import re
import shutil
import stat
import subprocess
import textwrap

import pytest
from PIL import Image
from video import stamp

REPO = pathlib.Path(__file__).resolve().parents[2]
VIDEO = REPO / "tools" / "video.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="no bash")


def video(args, tmp_path, *, video_dir=None, bin_path=None, home=None, extra_env=None):
    env = dict(os.environ,
               FACTORIO_BIN=str(bin_path or tmp_path / "no-such-factorio"),
               VIDEO_DIR=str(video_dir or tmp_path / "profile"),
               HOME=str(home or tmp_path / "home"))
    env.pop("FACTORIO", None)
    env.update(extra_env or {})
    return subprocess.run(["bash", str(VIDEO), *args], capture_output=True, text=True, env=env, check=False)


def test_help_prints_the_header_and_nothing_past_it(tmp_path):
    proc = video(["--help"], tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "Usage: tools/video.sh [--take main|loop] [--dry-run | --skip-dry] [--fresh]" in out
    for flag in ("--quality", "--out", "--skip-dry", "VIDEO_DIR", "FACTORIO_BIN"):
        assert flag in out, flag
    assert "set -euo" not in out and not any(line.startswith("#") for line in out.splitlines())


BAD = [
    (["--take", "wobbly"], "--take is main or loop, got 'wobbly'"),
    (["--take"], "--take wants a value"),
    (["--take", ""], "--take wants a value"),
    (["--bogus"], "unknown argument: --bogus"),
    (["--quality", "0"], "--quality wants a whole number 1-100, got '0'"),
    (["--quality", "101"], "--quality wants a whole number 1-100"),
    (["--quality", "90.5"], "--quality wants a whole number 1-100"),
    (["--quality", "high"], "--quality wants a whole number 1-100"),
    (["--quality", "090"], "--quality wants a whole number 1-100"),
    (["--dry-run", "--skip-dry"], "--dry-run and --skip-dry are opposites"),
    (["--dry-run", "--out", "x"], "--out is where a graphics take lands; --dry-run films nothing"),
    (["--out"], "--out wants a value"),
    # Nothing to size the take off: the dry run is what says how long the take runs.
    (["--skip-dry"], "--skip-dry sizes the take off the last dry run of 'main'"),
    (["--take", "loop", "--skip-dry"], "the last dry run of 'loop'"),
    # A 3 GB take in a tracked dir: under mod/ build.sh would copy it into the portal zip.
    (["--out", str(REPO / "mod" / "jamaltron" / "take-x")],
     "is inside the repo but not under render-out/"),
    (["--out", str(REPO / "tools" / "video" / "take-x")], "not under render-out/"),
    (["--out", str(REPO / "render-out" / ".." / "take-x")], "not under render-out/"),
]


@pytest.mark.parametrize("args,why", BAD, ids=[" ".join(a) or "empty" for a, _ in BAD])
def test_a_bad_argument_is_refused_before_anything_is_made(tmp_path, args, why):
    proc = video(args, tmp_path)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert why in proc.stderr, proc.stderr
    assert "binary not executable" not in proc.stderr
    assert not (tmp_path / "profile").exists()


def test_out_never_overwrites_a_take(tmp_path):
    (tmp_path / "taken").mkdir()
    proc = video(["--out", str(tmp_path / "taken")], tmp_path)
    assert proc.returncode == 2
    assert "already exists (a take never overwrites another)" in proc.stderr
    assert not (tmp_path / "profile").exists()


GOOD = [
    [],
    ["--take", "loop"],
    ["--dry-run"],
    ["--take", "loop", "--dry-run", "--fresh"],
    ["--quality", "1"],
    ["--quality", "100", "--out", "{tmp}/somewhere/new"],
    ["--out", str(REPO / "render-out" / "video" / "takes" / "never-made-by-this-test")],
]


@pytest.mark.parametrize("args", GOOD, ids=[" ".join(a) or "defaults" for a in GOOD])
def test_good_arguments_get_as_far_as_the_binary(tmp_path, args):
    args = [a.replace("{tmp}", str(tmp_path)) for a in args]
    proc = video(args, tmp_path)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "factorio binary not executable" in proc.stderr, proc.stderr


def _listing(path):
    """Everything under `path` (only its top level for /), or None when it is not there."""
    path = pathlib.Path(path)
    if not path.is_dir():
        return None
    if path == pathlib.Path("/"):
        return sorted(os.listdir(path))
    return sorted(str(p.relative_to(path)) for p in path.rglob("*"))


REFUSED = ["root", "home", "home-slash", "home-case", "repo", "repo-slash", "repo-dotdot",
           "repo-symlink", "repo-case", "real-profile", "real-profile-case",
           "inside-real-profile", "inside-real-profile-case"]


@pytest.mark.parametrize("which", REFUSED)
def test_video_dir_refuses_root_home_the_repo_and_the_real_profile(tmp_path, which):
    """Run from a COPY of video.sh in a fake repo, against a fake home holding a fake real profile,
    so a regression that writes before refusing lands in tmp_path (never the real tree) and is
    caught by the target's listing changing. The -case variants respell the same dirs (APFS is
    case-insensitive: .../Factorio IS the real profile)."""
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    shutil.copy(VIDEO, repo / "tools" / "video.sh")
    home = tmp_path / "home"
    profile = home / "Library" / "Application Support" / "factorio"
    (profile / "mods").mkdir(parents=True)
    (profile / "mods" / "mod-list.json").write_text('{"mods":[{"name":"my-precious-mod"}]}')
    link = tmp_path / "link-to-repo"
    link.symlink_to(repo)
    target = {
        "root": "/",
        "home": str(home),
        "home-slash": str(home) + "/",
        "home-case": str(tmp_path / "HOME"),
        "repo": str(repo),
        "repo-slash": str(repo) + "/",
        "repo-dotdot": str(repo / "tools" / ".."),
        "repo-symlink": str(link),
        "repo-case": str(tmp_path / "Repo"),
        "real-profile": str(profile),
        "real-profile-case": str(profile.parent / "Factorio"),
        "inside-real-profile": str(profile / "video"),
        "inside-real-profile-case": str(profile.parent / "FACTORIO" / "video"),
    }[which]
    watched = {p: _listing(p) for p in (target, home, repo, profile)}
    before = (profile / "mods" / "mod-list.json").read_text()
    env = dict(os.environ, FACTORIO_BIN=str(tmp_path / "no-such-factorio"), VIDEO_DIR=target,
               HOME=str(home))
    env.pop("FACTORIO", None)
    proc = subprocess.run(["bash", str(repo / "tools" / "video.sh")], capture_output=True,
                          text=True, env=env, check=False)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "refusing" in proc.stderr, proc.stderr
    assert "binary not executable" not in proc.stderr
    # Refused BEFORE anything is made: the target, home, the repo and the profile are untouched.
    assert {p: _listing(p) for p in watched} == watched
    assert (profile / "mods" / "mod-list.json").read_text() == before


# The review's repro (on copies): VIDEO_DIR pointed at .playtest, the mod source or the director
# got past the old refusals and was written into. `made` builds the target in a fake repo first.
PROFILE_RULES = [
    # (name, where, made, refused-with or None = accepted)
    ("playtest", ".playtest", "config", "inside the repo a video profile is a top-level "
                                        ".videotest* dir"),
    ("mod-source", "mod/jamaltron", "config", "inside the repo a video profile"),
    ("director", "tools/harness/jamaltron-video", "config", "inside the repo a video profile"),
    ("new-in-mod", "mod/jamaltron/profile", None, "inside the repo a video profile"),
    ("second-videotest", ".videotest2", None, None),
    ("videotest-unmarked", ".videotest", "config", "not empty and was not made by this script"),
    ("videotest-marked", ".videotest", "marked", None),
    ("outside-empty", "OUT/fresh", "empty", None),
    ("outside-unmarked", "OUT/desktop", "config", "not empty and was not made by this script"),
]


@pytest.mark.parametrize("name,where,made,why", PROFILE_RULES, ids=[r[0] for r in PROFILE_RULES])
def test_a_profile_is_ours_or_new_and_inside_the_repo_only_a_videotest_dir(tmp_path, name, where,
                                                                         made, why):
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    shutil.copy(VIDEO, repo / "tools" / "video.sh")
    target = pathlib.Path(where.replace("OUT", str(tmp_path / "elsewhere")))
    target = target if target.is_absolute() else repo / target
    if made:
        target.mkdir(parents=True)
        if made == "config":
            (target / "config.ini").write_text("[path]\nwrite-data=somebody-elses\n")
        elif made == "marked":
            (target / "config.ini").write_text("; ours\n")
            (target / ".jamaltron-videotest").touch()
    before = _listing(target)
    env = dict(os.environ, FACTORIO_BIN=str(tmp_path / "no-such-factorio"), VIDEO_DIR=str(target),
               HOME=str(tmp_path / "home"))
    env.pop("FACTORIO", None)
    proc = subprocess.run(["bash", str(repo / "tools" / "video.sh")], capture_output=True,
                          text=True, env=env, check=False)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    if why is None:
        assert "binary not executable" in proc.stderr, proc.stderr
    else:
        assert why in proc.stderr, proc.stderr
        assert "binary not executable" not in proc.stderr
    assert _listing(target) == before               # refused or not, nothing written yet


# --------------------------------------------------------------------------------------------
# The run's plumbing, against a fake factorio.
#
# --create touches the save and logs the director's fixture line; --benchmark (the headless dry
# run) drops the prepared take's logs where the director writes them; --benchmark-graphics drops
# its frames and stills too. Every call's arguments and the take.lua it was handed are kept in
# FAKE_SEEN. FAKE_DRY / FAKE_TAKE pick which prepared take each stage hands back; FAKE_FAIL puts a
# VIDEO FAIL in the dry run's log; FAKE_NOWRAP leaves the wrap line out.
FAKE = textwrap.dedent("""\
    #!/usr/bin/env bash
    config=""; mods=""; mode=""; ticks=""
    all="$*"
    while [ $# -gt 0 ]; do
      case "$1" in
        --config) config="$2"; shift 2 ;;
        --mod-directory) mods="$2"; shift 2 ;;
        --create) mode=create; save="$2"; shift 2 ;;
        --benchmark) mode=dry; shift 2 ;;
        --benchmark-graphics) mode=take; shift 2 ;;
        --benchmark-ticks) ticks="$2"; shift 2 ;;
        *) shift ;;
      esac
    done
    echo "$all" > "$FAKE_SEEN/$mode.args"
    if [ "$mode" = create ]; then
      touch "$save"
      echo "   1.000 Script @__jamaltron-video__/set.lua:1: VIDEO fixture built"
      exit 0
    fi
    lua="$mods/jamaltron-video/take.lua"
    cp "$lua" "$FAKE_SEEN/$mode-take.lua"
    cp "$mods/mod-list.json" "$FAKE_SEEN/mod-list.json"
    take="$(sed -n 's/.*take = "\\([a-z]*\\)".*/\\1/p' "$lua")"
    write="$(sed -n 's/^write-data=//p' "$config")"
    out="$write/script-output/video/$take"
    mkdir -p "$out"
    if [ "$mode" = dry ]; then src="$FAKE_DRY"; else src="$FAKE_TAKE"; fi
    cp "$src/events.jsonl" "$src/track.jsonl" "$out/"
    if [ "$mode" = take ]; then
      cp -R "$src/frames" "$out/frames"
      [ ! -d "$src/stills" ] || cp -R "$src/stills" "$out/stills"
    fi
    echo "   5.000 Script @__jamaltron-video__/story.lua:1: VIDEO capture_start at 10"
    echo "   5.001 Script @__jamaltron__/scripts/speech.lua:1: jamaltron speech 15 jump.01"
    [ "$mode" != dry ] || [ -z "${FAKE_FAIL:-}" ] || echo "   5.002 Script: VIDEO FAIL $FAKE_FAIL"
    echo "   5.333 Script @__jamaltron-video__/story.lua:1: VIDEO capture_end at 29"
    [ -n "${FAKE_NOWRAP:-}" ] || echo "   5.334 Script @__jamaltron-video__/story.lua:1: VIDEO wrap"
    """)


def prepared_take(root: pathlib.Path, *, first=10, last=29, shift_at=None) -> pathlib.Path:
    """A take as the director leaves it: stamped frames (640 wide: the stamp needs ~540), a still,
    track.jsonl and events.jsonl. `shift_at` stamps that one frame with the wrong tick."""
    rng = random.Random(first)
    (root / "frames").mkdir(parents=True)
    (root / "stills").mkdir()
    for t in range(first, last + 1):
        im = Image.new("RGB", (640, 200), (rng.randrange(256), 90, 40))
        stamp.draw(im, t + (1 if t == shift_at else 0))
        im.save(root / "frames" / f"f{t:07d}.jpg", quality=90)
    Image.new("RGB", (64, 36), (10, 120, 30)).save(root / "stills" / "beached.png")
    (root / "track.jsonl").write_text("".join(
        json.dumps({"tick": t, "cam": [0, 0], "zoom": 2, "body": "jamaltron", "pos": [0, 0],
                    "lift": [0, -1.5]}) + "\n" for t in range(first, last + 1)))
    evs = [{"tick": first, "ev": "capture_start"}, {"tick": first, "ev": "beat", "name": "establish"},
           {"tick": first + 7, "ev": "beat", "name": "hop1"}, {"tick": last, "ev": "beat", "name": "wrap"},
           {"tick": last, "ev": "capture_end"}]
    (root / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs))
    return root


@pytest.fixture
def fake(tmp_path):
    bin_dir = tmp_path / "game" / "bin"
    bin_dir.mkdir(parents=True)
    (tmp_path / "game" / "data").mkdir()
    exe = bin_dir / "factorio"
    exe.write_text(FAKE)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    seen = tmp_path / "seen"
    seen.mkdir()
    good = prepared_take(tmp_path / "src" / "good")

    def run(args, *, take=None, dry=None, **env):
        extra = {"FAKE_SEEN": str(seen), "FAKE_DRY": str(dry or good), "FAKE_TAKE": str(take or good)}
        extra.update({k.upper(): v for k, v in env.items()})
        # The real HOME: the verify step runs `uv run`, whose cache and interpreters live there.
        return video(args, tmp_path, bin_path=exe, home=os.environ["HOME"], extra_env=extra)

    run.seen = seen
    run.profile = tmp_path / "profile"
    run.tmp = tmp_path
    return run


def _lua_take(path, lua):
    """take.lua as the director's Lua reads it, or None without a lua binary."""
    if lua is None:
        return None
    probe = (f"local t = dofile([==[{path}]==]); print(t.take, t.capture, t.resolution[1], "
             "t.resolution[2], t.band, t.quality, t.dir, t.stills)")
    proc = subprocess.run([lua, "-e", probe], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.split()


def test_a_full_take_is_filmed_moved_and_verified(fake, lua_optional):
    out = fake.tmp / "takes" / "main-x"
    proc = fake(["--out", str(out), "--quality", "85"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # the fixture: the pinned seed and the no-bases map settings
    create = (fake.seen / "create.args").read_text()
    assert "--map-gen-seed 20260927" in create and "--map-gen-settings" in create
    settings = json.loads((fake.profile / "map-gen-settings.json").read_text())
    assert settings["autoplace_controls"]["enemy-base"]["size"] == 0
    # the dry run, then the take sized off its capture_end (29 + 300 + 29 // 10)
    assert "--benchmark-ticks 9300" in (fake.seen / "dry.args").read_text()
    assert "--benchmark-ticks 331" in (fake.seen / "take.args").read_text()
    assert "--disable-audio" in (fake.seen / "take.args").read_text()
    # what landed in the take dir, and the frames MOVED out of the profile
    assert sorted(p.name for p in out.iterdir()) == [
        "dry-run.log", "events.jsonl", "frames", "run.log", "stills", "take.lua", "track.jsonl",
        "verify.json"]
    assert len(list((out / "frames").iterdir())) == 20
    assert not (fake.profile / "write" / "script-output" / "video" / "main" / "frames").exists()
    assert json.loads((out / "verify.json").read_text())["ok"] is True
    assert "stamp: OK - 20 frames (ticks 10..29), 0 mismatches, 0 duplicates, 0 gaps" in proc.stdout
    assert re.search(r"^\s+establish\s+0\s+\(7 ticks\)$", proc.stdout, re.MULTILINE), proc.stdout
    assert re.search(r"^\s+hop1\s+7\s+\(12 ticks\)$", proc.stdout, re.MULTILINE), proc.stdout
    assert "57.1 UPS while filming" in proc.stdout           # 19 ticks in 0.333 s of log time
    assert "--take " in proc.stdout and "--cut video/main.toml" in proc.stdout
    # the director and the mod, as the take saw them
    mods = {m["name"]: m["enabled"] for m in json.loads((fake.seen / "mod-list.json").read_text())["mods"]}
    assert mods["jamaltron"] and mods["jamaltron-video"] and mods["space-age"]
    assert (fake.profile / "mods" / "jamaltron").is_symlink()
    assert (fake.profile / ".jamaltron-videotest").is_file()     # the marker: ours from now on
    assert (fake.profile / "mods" / "jamaltron-video" / "story.lua").is_file()
    dry, take = _lua_take(fake.seen / "dry-take.lua", lua_optional), _lua_take(fake.seen / "take-take.lua", lua_optional)
    if take is not None:
        assert dry == ["main", "false", "1920", "1104", "24", "85", "video/main", "false"]
        assert take == ["main", "true", "1920", "1104", "24", "85", "video/main", "true"]


def test_the_dry_run_alone_films_nothing(fake):
    proc = fake(["--take", "loop", "--dry-run"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "dry run ok" in proc.stdout and "establish 0  hop1 7  wrap 19" in proc.stdout
    assert not (fake.seen / "take.args").exists()
    kept = fake.profile / "dry" / "loop"
    assert sorted(p.name for p in kept.iterdir()) == ["dry.log", "events.jsonl", "track.jsonl"]


def test_skip_dry_sizes_the_take_off_the_last_dry_run(fake):
    assert fake(["--dry-run"]).returncode == 0
    (fake.seen / "dry.args").unlink()
    proc = fake(["--skip-dry", "--out", str(fake.tmp / "t")])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not (fake.seen / "dry.args").exists()
    assert "--benchmark-ticks 331" in (fake.seen / "take.args").read_text()


def test_the_fixture_is_built_once_unless_fresh(fake):
    assert fake(["--dry-run"]).returncode == 0
    (fake.seen / "create.args").unlink()
    assert fake(["--dry-run"]).returncode == 0
    assert not (fake.seen / "create.args").exists()
    assert fake(["--dry-run", "--fresh"]).returncode == 0
    assert (fake.seen / "create.args").exists()


def test_a_video_fail_in_the_dry_run_stops_before_the_take(fake):
    proc = fake([], fake_fail="beat hop1 ran 601 ticks (max 600)")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "VIDEO FAIL beat hop1 ran 601 ticks" in proc.stderr
    assert "dry run failed" in proc.stderr
    assert not (fake.seen / "take.args").exists()


def test_a_dry_run_that_never_wraps_fails(fake):
    proc = fake(["--dry-run"], fake_nowrap="1")
    assert proc.returncode == 2
    assert "dry run never reached the wrap beat" in proc.stderr


def test_a_frame_with_the_wrong_stamp_fails_the_take_and_stays_for_looking_at(fake):
    bad = prepared_take(fake.tmp / "src" / "bad", shift_at=17)
    out = fake.tmp / "takes" / "bad"
    proc = fake(["--out", str(out)], take=bad)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "FAILED verification" in proc.stderr
    assert "MISMATCH f0000017: stamp reads 18" in proc.stderr
    assert "DUPLICATE stamp 18 on f0000017, f0000018" in proc.stderr
    verdict = json.loads((out / "verify.json").read_text())
    assert verdict["ok"] is False and verdict["mismatch_count"] == 1
    assert len(list((out / "frames").iterdir())) == 20


def test_the_director_writes_what_the_contract_names():
    """The pins live in the director, where only the engine runs them (a headless dry run and a
    graphics take, measured 2026-09-27). This keeps them from being quietly deleted: the freeplay
    trio that stops graphics mode pausing at tick 750, force_render, the wait on the last shot,
    the stamp, and the speech debug switch the captions are cross-checked against."""
    d = REPO / "tools" / "harness" / "jamaltron-video"
    set_lua, cam, story = ((d / f).read_text() for f in ("set.lua", "camera.lua", "story.lua"))
    for probe in ('"set_disable_crashsite"', '"set_skip_intro"', '"set_chart_distance", 0'):
        assert probe in set_lua, probe
    for probe in ("force_render = true", "show_gui = false", "time_to_live = 1", "water_tick"):
        assert probe in cam, probe
    for probe in ('remote.call("jamaltron", "debug", true)', "set_wait_for_screenshots_to_finish",
                  '"jamaltron-speech-cooldown", 300', 'ev = "capture_start"', 'ev = "capture_end"'):
        assert probe in story, probe
    assert "leg_hit_the_ground_trigger" in (d / "data-final-fixes.lua").read_text()
    info = json.loads((d / "info.json").read_text())
    assert info["name"] == "jamaltron-video" and info["dependencies"] == ["jamaltron"]
