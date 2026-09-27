"""tools/shot.sh without Factorio: every argument check, the profile refusals, and the run's
plumbing against a FAKE factorio.

Each refusal is judged before anything is created or launched, so these point FACTORIO_BIN at a
missing path: a check that let a bad value through stops at "factorio binary not executable"
instead of its own message and fails here. The positive controls prove good arguments get as
far as the binary check.
"""

import json
import os
import pathlib
import shutil
import stat
import subprocess
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SHOT = REPO / "tools" / "shot.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="no bash")


def shot(args, tmp_path, *, shot_dir=None, bin_path=None, home=None, extra_env=None):
    env = dict(os.environ,
               FACTORIO_BIN=str(bin_path or tmp_path / "no-such-factorio"),
               SHOT_DIR=str(shot_dir or tmp_path / "profile"),
               HOME=str(home or tmp_path / "home"))
    env.pop("FACTORIO", None)
    env.update(extra_env or {})
    return subprocess.run(["bash", str(SHOT), *args], capture_output=True, text=True, env=env)


def test_help_prints_the_header_and_nothing_past_it(tmp_path):
    proc = shot(["--help"], tmp_path)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "Usage: tools/shot.sh [--scene beached|standing|both|many]" in out
    for flag in ("--many", "--at", "--every/--count/--start", "--gif", "--stager", "SHOT_DIR"):
        assert flag in out, flag
    assert "set -euo" not in out and not any(line.startswith("#") for line in out.splitlines())


BAD = [
    (["--scene", "wobbly"], "--scene is beached, standing, both or many, got 'wobbly'"),
    (["--scene"], "--scene wants a value"),
    (["--zoom", ""], "--zoom wants a value"),
    (["--bogus"], "unknown argument: --bogus"),
    (["--res", "1600"], "--res wants WxH"),
    (["--res", "0x900"], "--res wants WxH"),
    (["--res", "1600x900x2"], "--res wants WxH"),
    (["--center", "1,"], "--center wants X,Y"),
    (["--center", "1..2,3"], "--center wants X,Y"),
    (["--center", "a,b"], "--center wants X,Y"),
    (["--zoom", "0"], "--zoom wants a number above 0"),
    (["--zoom", "-1"], "--zoom wants a number above 0"),
    (["--zoom", "1.2.3"], "--zoom wants a number above 0"),
    (["--zoom", "two"], "--zoom wants a number above 0"),
    (["--at", "60,,120"], "--at wants ticks"),
    (["--at", "0"], "--at wants ticks after staging (>= 1)"),
    # Tick 0 is the staging tick: the stager never shoots it, so the run would die ~10 s later on a
    # missing screenshot. Every tick is checked, not only the last.
    (["--at", "0,120"], "--at wants ticks after staging (>= 1)"),
    (["--every", "3", "--count", "4", "--start", "0"], "--start wants a tick after staging (>= 1)"),
    (["--every", "3"], "--every and --count want whole numbers, together"),
    (["--count", "4"], "--every and --count want whole numbers, together"),
    (["--every", "0", "--count", "3"], "--every and --count want whole numbers, together"),
    (["--gif"], "--gif wants a burst"),
    (["--gif", "--at", "60,120"], "--gif wants a burst"),
    (["--many", "4"], "--many only goes with --scene many"),
    (["--scene", "many", "--many", "0"], "--many wants a whole number 1-16"),
    (["--scene", "many", "--many", "17"], "--many wants a whole number 1-16"),
    (["--scene", "many", "--many", "3.5"], "--many wants a whole number 1-16"),
    (["--tile", 'sand"1'], "--tile wants a tile prototype name"),
    (["--stager", "/no/such/stager"], "--stager wants a directory"),
]


@pytest.mark.parametrize("args,why", BAD, ids=[" ".join(a) or "empty" for a, _ in BAD])
def test_a_bad_argument_is_refused_before_anything_is_made(tmp_path, args, why):
    proc = shot(args, tmp_path)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert why in proc.stderr, proc.stderr
    assert "binary not executable" not in proc.stderr
    assert not (tmp_path / "profile").exists()


GOOD = [
    [],
    ["--scene", "many"],
    ["--scene", "many", "--many", "16"],
    ["--scene", "standing", "--zoom", ".5", "--center", "-3.5,2"],
    ["--scene", "both", "--zoom", "2", "--res", "800x600", "--at", "60,120,60"],
    ["--every", "3", "--count", "4", "--start", "1", "--gif"],
    ["--tile", "refined-concrete", "--base-only"],
]


@pytest.mark.parametrize("args", GOOD, ids=[" ".join(a) or "defaults" for a in GOOD])
def test_good_arguments_get_as_far_as_the_binary(tmp_path, args):
    proc = shot(args, tmp_path)
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
def test_shot_dir_refuses_root_home_the_repo_and_the_real_profile(tmp_path, which):
    """Run from a COPY of shot.sh in a fake repo, against a fake home holding a fake real profile,
    so a regression that writes before refusing lands in tmp_path (never the real tree) and is
    caught by the target's listing changing. The -case variants respell the same dirs (APFS is
    case-insensitive: .../Factorio IS the real profile)."""
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    shutil.copy(SHOT, repo / "tools" / "shot.sh")
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
        "inside-real-profile": str(profile / "shots"),
        "inside-real-profile-case": str(profile.parent / "FACTORIO" / "shots"),
    }[which]
    watched = {p: _listing(p) for p in (target, home, repo, profile)}
    before = (profile / "mods" / "mod-list.json").read_text()
    env = dict(os.environ, FACTORIO_BIN=str(tmp_path / "no-such-factorio"), SHOT_DIR=target,
               HOME=str(home))
    env.pop("FACTORIO", None)
    proc = subprocess.run(["bash", str(repo / "tools" / "shot.sh")], capture_output=True,
                          text=True, env=env)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "refusing" in proc.stderr, proc.stderr
    assert "binary not executable" not in proc.stderr
    # Refused BEFORE anything is made: the target, home, the repo and the profile are untouched.
    assert {p: _listing(p) for p in watched} == watched
    assert (profile / "mods" / "mod-list.json").read_text() == before


# --create touches the save; --benchmark-graphics logs the stager's lines and writes one "PNG"
# per tick in the scene.lua it was handed, the way the stager's take_screenshot calls do.
FAKE = textwrap.dedent("""\
    #!/usr/bin/env bash
    config=""; mods=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --config) config="$2"; shift 2 ;;
        --mod-directory) mods="$2"; shift 2 ;;
        --create) touch "$2"; echo "   1.000 SHOT fixture pad"; shift 2 ;;
        --benchmark-graphics)
          cp "$mods/jamaltron-shot/scene.lua" "$FAKE_SEEN/scene.lua"
          cp "$mods/mod-list.json" "$FAKE_SEEN/mod-list.json"
          write="$(sed -n 's/^write-data=//p' "$config")"
          scene="$mods/jamaltron-shot/scene.lua"
          prefix="$(sed -n 's/.*prefix = "\\([a-z]*\\)".*/\\1/p' "$scene")"
          shots="$(sed -n 's/.*shots = {\\([0-9,]*\\)}.*/\\1/p' "$scene")"
          mkdir -p "$write/script-output"
          echo "   2.000 SHOT staged"
          [ -z "${FAKE_FAIL:-}" ] || echo "   2.001 SHOT FAIL $FAKE_FAIL"
          for t in ${shots//,/ }; do
            printf 'png' > "$write/script-output/$(printf '%s-%05d.png' "$prefix" "$t")"
          done
          shift 2 ;;
        *) shift ;;
      esac
    done
    """)


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

    def run(args, fail=""):
        return shot([*args, "--out", str(tmp_path / "out")], tmp_path, bin_path=exe,
                    extra_env={"FAKE_SEEN": str(seen), "FAKE_FAIL": fail})

    run.seen = seen
    run.out = tmp_path / "out"
    run.profile = tmp_path / "profile"
    return run


def _scene(path, lua):
    """scene.lua as the stager's Lua will read it, or None without a lua binary (conftest's
    `lua_optional`: a JAMALTRON_LUA that names a missing one has already failed the test)."""
    if lua is None:
        return None
    probe = ("local t = dofile([==[%s]==]); print(t.scene, t.many, t.zoom, t.center[1], "
             "t.center[2], t.resolution[1], t.resolution[2], #t.shots, t.tile, t.prefix)" % path)
    proc = subprocess.run([lua, "-e", probe], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.split()


def test_a_many_run_writes_valid_lua_and_copies_every_shot(fake, lua_optional):
    proc = fake(["--scene", "many", "--many", "4", "--zoom", "1.5", "--center", "-3.5,2",
                 "--at", "60,120"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert sorted(p.name for p in fake.out.iterdir()) == ["many-00060.png", "many-00120.png"]
    assert "2 screenshot(s)" in proc.stdout
    scene = _scene(fake.seen / "scene.lua", lua_optional)
    if scene is not None:
        assert scene == ["many", "4", "1.5", "-3.5", "2", "1600", "900", "2", "sand-1", "many"]
    mods = {m["name"]: m["enabled"] for m in json.loads((fake.seen / "mod-list.json").read_text())["mods"]}
    assert mods["jamaltron"] and mods["jamaltron-shot"] and mods["space-age"]
    assert (fake.profile / "mods" / "jamaltron").is_symlink()
    assert (fake.profile / "mods" / "jamaltron-shot" / "control.lua").is_file()


def _zoom(fake):
    text = (fake.seen / "scene.lua").read_text()
    return float(text.split("zoom = ", 1)[1].split(",", 1)[0])


@pytest.mark.parametrize("args,zoom,warns", [
    (["--many", "6"], 1.0, False),                      # 3x2 fits at 1: the default untouched
    (["--many", "12"], 1.0, False),                     # 4x3 still fits
    (["--many", "13"], 0.8, False),                     # 4x4: the outer rows would leave the frame
    (["--many", "16", "--res", "800x450"], 0.4, False),  # the fit follows --res
    (["--many", "16", "--zoom", "1"], 1.0, True),       # an explicit zoom is kept, and warned about
    (["--many", "16", "--zoom", "0.5"], 0.5, False),
])
def test_many_frames_its_whole_grid(fake, args, zoom, warns):
    proc = fake(["--scene", "many", *args])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _zoom(fake) == zoom
    assert ("crops the" in proc.stderr) == warns, proc.stderr


def test_every_other_scene_hands_the_stager_many_0(fake, lua_optional):
    proc = fake(["--scene", "both"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    scene = _scene(fake.seen / "scene.lua", lua_optional)
    if scene is not None:
        assert scene[:2] == ["both", "0"]


def test_a_shot_fail_from_the_stager_fails_the_run(fake):
    proc = fake(["--scene", "beached"], fail="staging: player 1 has a character at {x = 0, y = 0}")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "SHOT FAIL staging: player 1 has a character" in proc.stderr
    assert "run failed" in proc.stderr
    assert not fake.out.exists()


def test_the_stager_checks_the_fixture_it_was_promised():
    """The pins live in the stager, where only the real engine can run them (a stager mutant that
    skips freeplay's suppression or keeps the character fails the run, measured 2026-09-26).
    This keeps them from being quietly deleted."""
    src = (REPO / "tools" / "harness" / "jamaltron-shot" / "control.lua").read_text()
    assert 'check_clean(s, "staging")' in src
    assert 'check_clean(s, "shot " .. dt)' in src
    for probe in ('"get_disable_crashsite"', '"get_skip_intro"', '"^crash%-site"',
                  "player.character", "defines.controllers.cutscene", "s.show_clouds"):
        assert probe in src, probe
