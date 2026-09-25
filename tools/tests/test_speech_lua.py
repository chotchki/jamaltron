"""D.5: the speech code's contracts that Python can check, and the Lua tests it can run.

The picker's own tests are Lua (tools/tests/lua/), run here under whatever plain `lua` is on
PATH. They SKIP where there is none, which today includes CI - C.14 is the task that puts Lua
on the runner, and until it lands this is a local gate, said out loud rather than implied.

The Python half needs nothing: scripts/speech.lua hard-codes a handful of row ids and pool
keys (the silence windows, the ambient set), and ids stay renumberable until F.6. A window
keyed by a retired id is a silence the mod quietly stops honouring.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SPEECH = REPO / "mod" / "jamaltron" / "scripts" / "speech.lua"
LINES_LUA = REPO / "mod" / "jamaltron" / "scripts" / "lines.lua"
LUA = shutil.which("lua") or shutil.which("luajit")


@pytest.mark.parametrize("script", sorted((REPO / "tools" / "tests" / "lua").glob("test_*.lua")),
                         ids=lambda p: p.name)
def test_lua_suite(script):
    if LUA is None:
        pytest.skip("no lua on PATH (CI has none until C.14)")
    proc = subprocess.run([LUA, str(script), str(REPO)], capture_output=True, text=True)
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
                  "jump_refused", "low_health"):
        assert event not in ambient, event
