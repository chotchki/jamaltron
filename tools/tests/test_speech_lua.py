"""D.5: the speech code's contracts that Python can check, and the Lua tests it can run.

The picker's own tests are Lua (tools/tests/lua/), run here under conftest's `lua` fixture:
JAMALTRON_LUA names the interpreter and makes it MANDATORY (a named interpreter that is
missing FAILS), else plain `lua` or `luajit`, SKIPPED where there is neither. CI sets it to
lua5.2, Factorio's dialect (PLAN C.14), so a runner that loses its Lua fails instead of
passing on skips.

The Python half needs nothing: scripts/speech.lua hard-codes a handful of row ids and pool
keys (the silence windows, the ambient set, the pools poll() says from), and ids stay
renumberable until F.6. A window keyed by a retired id is a silence the mod quietly stops
honouring; a say() on a missing pool is an error on the 1 Hz clock.
"""

import pathlib
import re
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "mod" / "jamaltron" / "scripts"
SPEECH = SCRIPTS / "speech.lua"
LINES_LUA = SCRIPTS / "lines.lua"
CONTROL = REPO / "mod" / "jamaltron" / "control.lua"


@pytest.mark.parametrize("script", sorted((REPO / "tools" / "tests" / "lua").glob("test_*.lua")),
                         ids=lambda p: p.name)
def test_lua_suite(script, lua):
    proc = subprocess.run([lua, str(script), str(REPO)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert re.fullmatch(r"ok \d+", proc.stdout.strip()), proc.stdout


def catalog():
    """{row id: (pool, channel)} and the pool keys, off the generated table's text."""
    text = LINES_LUA.read_text()
    rows, pool = {}, None
    for line in text.splitlines():
        head = re.match(r"^    (\w+) = \{$", line)
        if head:
            pool = head.group(1)
        row = re.search(r'\{id = "([^"]+)", grp = "[^"]+", ch = "(\w+)"', line)
        if row:
            rows[row.group(1)] = (pool, row.group(2))
    return rows, {p for p, _ in rows.values()}


def lua_table(name: str, nested: bool = False) -> str:
    """The body of `M.<name> = {...}`. A flat table closes on its first `}`; a nested one on
    the `}` that starts a line."""
    close = r"^\}" if nested else r"\}"
    body = re.search(r"^M\.%s = \{(.*?)%s" % (name, close), SPEECH.read_text(), re.S | re.M)
    assert body, "speech.lua has no M.%s table" % name
    return body.group(1)


def test_every_silence_window_is_keyed_by_a_live_row_of_the_right_kind():
    """lines.md's silence table: low_health.01, attacking.03 and legs_break.18 each open a
    window, all three are NARRATION rows naming a silence, and each is keyed here by id."""
    rows, _ = catalog()
    keys = re.findall(r'\["([^"]+)"\]\s*=', lua_table("WINDOWS", nested=True))
    assert sorted(keys) == ["attacking.03", "legs_break.18", "low_health.01"]
    for key in keys:
        assert key in rows, "%s is not in the catalog -- retired or renumbered?" % key
        assert rows[key][1] == "narration", key


def test_every_ambient_pool_exists():
    _, pools = catalog()
    ambient = re.findall(r"(\w+) = true", lua_table("AMBIENT"))
    assert ambient and set(ambient) <= pools, set(ambient) - pools
    # and the events that must never be swallowed by a cooldown are not in it
    for event in ("built", "enter", "exit", "jump", "land", "legs_break", "repaired", "died",
                  "jump_refused", "low_health", "shore"):
        assert event not in ambient, event


def test_every_pool_said_by_name_exists():
    """say() errors on an unknown pool, and poll() says `shore`, `moving` and `idle` every
    second, so a pool renamed in lines.md but not in the code that says it is a crash, not a
    quiet line. The jump loop's pools are said from jump.lua and breakage.lua, the
    flamethrower's from attack.lua (D.7)."""
    _, pools = catalog()
    said = set()
    for path in (SPEECH, CONTROL, SCRIPTS / "jump.lua", SCRIPTS / "breakage.lua",
                 SCRIPTS / "attack.lua"):
        said |= set(re.findall(r'\bsay\([\w.]+, "(\w+)"', path.read_text()))
    assert {"shore", "moving", "idle", "built", "died"} <= said, said
    assert {"jump", "jump_refused", "land", "legs_break", "flopping", "repaired"} <= said, said
    assert "attacking" in said, said
    assert said <= pools, said - pools


@pytest.mark.parametrize("path", [SCRIPTS / "speech" / "stall.lua", SCRIPTS / "ground.lua"],
                         ids=lambda p: p.name)
def test_the_stall_names_prototypes_through_shared_lua(path):
    """Leg and body names come from prototypes/shared.lua (C.name, C.leg_name), never a
    literal: the ground table reads the LEG's mask, and a typo'd name there is a nil index on
    the first stall, not a load error."""
    text = path.read_text()
    assert "jamaltron-leg" not in text
    code = re.sub(r"--.*", "", text)
    assert not re.search(r"""["']jamaltron""", code), "a literal prototype name"
    assert "prototypes.shared" in code
