"""C.14: the contracts ci.yml keeps with the scripts it calls, checked where a push is not needed.

Each is a way for CI to PASS WHILE CHECKING NOTHING, which is worse than failing: a gate
called bare (so a missing binary skips it), an interpreter installed under one name and
tested under another, a workflow pin disagreeing with the scripts' pin, a script path that
no longer exists. ci.yml is read as text, as test_pack reads its classifier (no YAML
dependency for one file).
"""

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
CI = REPO / ".github" / "workflows" / "ci.yml"
LINT = REPO / "tools" / "lint.sh"
GEN_DEFS = REPO / "tools" / "gen-defs.sh"
TESTS = REPO / "tools" / "tests"
CONFTEST = TESTS / "conftest.py"
INFO = REPO / "mod" / "jamaltron" / "info.json"


def ci_text() -> str:
    return CI.read_text()


def ci_code() -> str:
    """ci.yml minus its comments, so a path or flag named in prose cannot satisfy a check."""
    return "\n".join(re.sub(r"(^|\s)#.*", "", line) for line in ci_text().splitlines())


def pin(name: str) -> str:
    found = re.findall(r'^  %s: "?([^"\s]+)"?\s*$' % name, ci_text(), re.M)
    assert len(found) == 1, "ci.yml should set %s exactly once at workflow level: %r" % (name, found)
    return found[0]


def lint_gates() -> set:
    """The gate names lint.sh's --only accepts, off its own case arm."""
    arm = re.search(r"^\s*([\w|]+)\) ONLY=\"\$2\" ;;", LINT.read_text(), re.M)
    assert arm, "lint.sh has no --only case arm any more -- re-pin this test"
    return set(arm.group(1).split("|"))


def test_every_action_is_pinned_to_a_commit_sha():
    uses = re.findall(r"^\s*(?:- )?uses: (\S+)(.*)$", ci_text(), re.M)
    assert uses
    for ref, comment in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", ref), "not SHA-pinned: " + ref
        assert re.fullmatch(r"\s+# v\d+(\.\d+)*", comment), "SHA without its version tag: " + ref


def test_every_script_ci_calls_exists_and_is_executable():
    code = ci_code()
    paths = set(re.findall(r"\btools/[\w./-]+\.(?:sh|py)\b", code))
    assert {"tools/lint.sh", "tools/gen-defs.sh", "tools/lint_sprites.py"} <= paths, paths
    index = subprocess.run(["git", "ls-files", "-s", "--", "tools"], cwd=REPO, check=True,
                           capture_output=True, text=True).stdout
    modes = {row[3]: row[0] for row in (line.split(None, 3) for line in index.splitlines())}
    for path in sorted(paths):
        assert (REPO / path).is_file(), path + " is called by ci.yml and does not exist"
        # Called as `tools/x.sh`, not `bash tools/x.sh`: the INDEX mode is what the runner
        # checks out, and a 100644 script is `Permission denied` on the first push.
        if path.endswith(".sh") and re.search(r"(^|[\s;&|])%s\b" % re.escape(path), code, re.M):
            assert modes.get(path) == "100755", "%s is not committed executable (%s)" % (
                path, modes.get(path, "untracked"))


def test_each_lua_gate_is_called_by_name_so_it_cannot_skip():
    """Bare, lint.sh SKIPS a gate whose binary is missing. CI must call each gate with
    --only, and between them cover every gate lint.sh has."""
    calls = re.findall(r"tools/lint\.sh([^\n]*)", ci_code())
    assert calls, "ci.yml no longer runs tools/lint.sh"
    named = set()
    for args in calls:
        only = re.fullmatch(r"\s+--only (\w+)\s*", args)
        assert only, "tools/lint.sh called without --only: %r" % args
        named.add(only.group(1))
    assert named == lint_gates(), (named, lint_gates())


@pytest.mark.parametrize("gate,env", [("luacheck", "LUACHECK_BIN"), ("types", "LUALS_BIN")])
def test_a_named_gate_with_no_binary_fails_instead_of_skipping(gate, env):
    proc = subprocess.run([str(LINT), "--only", gate], capture_output=True, text=True,
                          env={**os.environ, env: "/nonexistent/" + gate})
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "may not skip" in proc.stdout and "SKIP" not in proc.stdout, proc.stdout


def test_an_unknown_gate_is_a_usage_error():
    proc = subprocess.run([str(LINT), "--only", "shellcheck"], capture_output=True, text=True)
    assert proc.returncode == 2 and "luacheck or types" in proc.stderr, proc.stderr


def test_the_lua_interpreter_is_one_variable():
    """Installed as lua$LUA_VERSION, tested as JAMALTRON_LUA=lua$LUA_VERSION, and
    conftest.py's resolver is that variable's one reader; rename either side and this fails.
    The two tests below hold every Lua-running suite to the resolver."""
    assert re.fullmatch(r"5\.\d", pin("LUA_VERSION"))
    code = ci_code()
    assert re.search(r'apt-get install [^\n]*"lua\$LUA_VERSION"', code)
    assert re.search(r'JAMALTRON_LUA="lua\$LUA_VERSION" uv run --directory tools pytest', code)
    text = CONFTEST.read_text()
    assert 'LUA_ENV = "JAMALTRON_LUA"' in text and "os.environ.get(LUA_ENV" in text
    assert sorted((TESTS / "lua").glob("test_*.lua")), "no Lua suites to run"


# Suites that find lua by bare name and SKIP without it instead of going through conftest's
# resolver (which fails when JAMALTRON_LUA names a missing interpreter). Such a suite passed
# in CI only because apt's lua5.2 registers /usr/bin/lua through update-alternatives; without
# that link it passes on a skip. A ratchet that only shrinks, EMPTY now and staying empty:
# take the `lua` fixture (or `lua_optional`) instead of adding a name here.
BARE_LUA_KNOWN: set = set()
BARE_LUA = re.compile(r"""shutil\.which\(\s*["']lua(?:jit)?["']\s*\)""")


def test_no_new_suite_finds_lua_by_bare_name():
    bare = {f.name for f in TESTS.glob("*.py")
            if f != CONFTEST and BARE_LUA.search(f.read_text())}
    new = bare - BARE_LUA_KNOWN
    assert not new, "%s find lua by bare name and skip without it - take conftest's `lua` " \
        "fixture, which fails when JAMALTRON_LUA names a missing interpreter" % sorted(new)
    fixed = BARE_LUA_KNOWN - bare
    assert not fixed, "%s no longer find lua by bare name - drop them from BARE_LUA_KNOWN" \
        % sorted(fixed)


#: One Lua-running test per suite that runs Lua, as pytest node ids from tools/.
LUA_USERS = (
    "tests/test_speech_lua.py::test_lua_suite",
    "tests/test_pack.py::test_generated_lua_loads_and_shares_its_tables",
    "tests/test_shot.py::test_every_other_scene_hands_the_stager_many_0",
    "tests/test_wreck_cover.py::test_every_leg_mouth_is_under_him_in_every_flop_frame",
)


def test_a_named_lua_that_is_missing_fails_every_lua_suite_instead_of_skipping():
    """The resolver's purpose, run for real: CI's JAMALTRON_LUA naming nothing must fail
    every suite that runs Lua, never skip. It fails as a setup ERROR (the fixture fails), and
    pytest exits 1 on those exactly as on a FAILED."""
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rfEs", "-p", "no:cacheprovider",
                           *LUA_USERS], cwd=REPO / "tools", capture_output=True, text=True,
                          env={**os.environ, "JAMALTRON_LUA": "/nonexistent/lua5.2"})
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert "skipped" not in out and "SKIPPED" not in out, out
    for node in LUA_USERS:
        assert re.search(r"^(FAILED|ERROR) %s\b" % re.escape(node), out, re.M), node
    assert "may not skip" in out, out


def test_the_defs_pins_agree_with_the_mod_and_the_script():
    api = pin("FACTORIO_API_VERSION")
    assert re.fullmatch(r"\d+\.\d+\.\d+", api), "a full version: the API site has no x.y alias"
    target = json.loads(INFO.read_text())["factorio_version"]
    assert api.startswith(target + "."), "defs for %s, mod targets %s" % (api, target)
    fmtk = pin("FMTK_VERSION")
    assert "factoriomod-debug@%s " % fmtk in GEN_DEFS.read_text(), \
        "gen-defs.sh's install hint names a different fmtk than ci.yml pins"
    assert re.search(r'gen-defs\.sh --online --api-version "\$FACTORIO_API_VERSION"', ci_code())


def test_the_language_server_is_pinned_by_hash():
    assert re.fullmatch(r"\d+\.\d+\.\d+", pin("LUALS_VERSION"))
    assert re.fullmatch(r"[0-9a-f]{64}", pin("LUALS_SHA256"))
    assert re.search(r'sha256sum -c -', ci_code())
