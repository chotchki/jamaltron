"""tools/smoke.sh's harness verdict, against a FAKE factorio that prints a canned log.

The need/never checks grep the benchmark log. Under `set -o pipefail`, `grep -v | grep -q`
returns 141 once grep -q has matched and quit with more than a pipe buffer (~64 KB) still to
come, so a `never` whose forbidden line sat near the top PASSED and a `need` near the top
FAILED (measured: 0 of 20 flagged at 220 KB). The real harness log is ~21 KB, so it stayed
latent; these logs are 400 KB.
"""

import os
import pathlib
import shutil
import stat
import subprocess
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SMOKE = REPO / "tools" / "smoke.sh"

FAKE = textwrap.dedent("""\
    #!/usr/bin/env bash
    # --create PATH writes a save; --benchmark prints the canned harness log.
    echo "   0.100 Loading mod jamaltron 0.1.0 (data.lua)"
    while [ $# -gt 0 ]; do
      case "$1" in
        --create) touch "$2"; shift 2 ;;
        --benchmark) cat "$FAKE_BENCH_LOG"; shift 2 ;;
        *) shift ;;
      esac
    done
    """)


@pytest.fixture
def fake(tmp_path):
    if shutil.which("bash") is None:
        pytest.skip("no bash")
    bin_dir = tmp_path / "game" / "bin"
    bin_dir.mkdir(parents=True)
    (tmp_path / "game" / "data" / "base").mkdir(parents=True)
    exe = bin_dir / "factorio"
    exe.write_text(FAKE)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    mod = tmp_path / "src" / "jamaltron"
    mod.mkdir(parents=True)
    (mod / "info.json").write_text('{"name": "jamaltron", "version": "0.1.0"}')
    harness = tmp_path / "src" / "jamaltron-harness"
    harness.mkdir()
    (harness / "info.json").write_text('{"name": "jamaltron-harness", "version": "0.1.0"}')

    def run(head: list) -> subprocess.CompletedProcess:
        filler = ["   1.000 Script log: filler %06d %s" % (i, "x" * 40) for i in range(6000)]
        log = tmp_path / "bench.log"
        log.write_text("\n".join(head + filler + ["   2.000 HARNESS done at 3700"]) + "\n")
        env = dict(os.environ, FACTORIO_BIN=str(exe), FAKE_BENCH_LOG=str(log),
                   SMOKE_TIMEOUT="0")
        return subprocess.run(["bash", str(SMOKE), "--mod-dir", str(mod), "--harness",
                               str(harness), "--workdir", str(tmp_path / "work")],
                              capture_output=True, text=True, env=env)

    return run


def test_a_never_line_near_the_top_of_a_big_log_fails_the_run(fake):
    proc = fake(["   0.500 HARNESS never jamaltron speech 42 idle[.]",
                 "   0.600 jamaltron speech 42 idle.03"])
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "the run matched what it must never: jamaltron speech 42 idle[.]" in proc.stdout


def test_a_need_line_near_the_top_of_a_big_log_passes_the_run(fake):
    proc = fake(["   0.500 HARNESS need jamaltron speech 42 shore[.]",
                 "   0.600 jamaltron speech 42 shore.04",
                 "   0.700 HARNESS ok shore: one line"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "1 checks passed" in proc.stdout


FAKE_LIST = textwrap.dedent("""\
    #!/usr/bin/env bash
    # Records the mod-list.json each --create ran under, then behaves like FAKE.
    echo "   0.100 Loading mod jamaltron 0.1.0 (data.lua)"
    dir=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --mod-directory) dir="$2"; shift 2 ;;
        --create) cp "$dir/mod-list.json" "$FAKE_LISTS/$(basename "$2").json"; touch "$2"; shift 2 ;;
        --benchmark) echo "   2.000 HARNESS done at 1"; shift 2 ;;
        *) shift ;;
      esac
    done
    """)


@pytest.mark.parametrize("with_harness", [False, True], ids=["plain", "harness"])
def test_the_mod_list_is_json_and_the_base_stage_disables_the_dlc(tmp_path, with_harness):
    """D.7 found every "base only" stage since D.5 running with Space Age: the heredoc's
    ${HARNESS_NAME:+...} wrote invalid JSON both ways (quotes stripped with a harness, a stray
    `}` without), and Factorio enables every mod it finds when mod-list.json does not parse."""
    import json
    if shutil.which("bash") is None:
        pytest.skip("no bash")
    bin_dir = tmp_path / "game" / "bin"
    bin_dir.mkdir(parents=True)
    (tmp_path / "game" / "data" / "base").mkdir(parents=True)
    exe = bin_dir / "factorio"
    exe.write_text(FAKE_LIST)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    mod = tmp_path / "src" / "jamaltron"
    mod.mkdir(parents=True)
    (mod / "info.json").write_text('{"name": "jamaltron", "version": "0.1.0"}')
    lists = tmp_path / "lists"
    lists.mkdir()
    args = ["bash", str(SMOKE), "--mod-dir", str(mod), "--workdir", str(tmp_path / "work")]
    if with_harness:
        harness = tmp_path / "src" / "jamaltron-harness"
        harness.mkdir()
        (harness / "info.json").write_text('{"name": "jamaltron-harness", "version": "0.1.0"}')
        args += ["--harness", str(harness)]
    env = dict(os.environ, FACTORIO_BIN=str(exe), FAKE_LISTS=str(lists), SMOKE_TIMEOUT="0")
    proc = subprocess.run(args, capture_output=True, text=True, env=env)
    base = json.loads((lists / "base.zip.json").read_text())
    sa = json.loads((lists / "sa.zip.json").read_text())
    enabled = {m["name"]: m["enabled"] for m in base["mods"]}
    assert enabled["space-age"] is False and enabled["quality"] is False, enabled
    assert {m["name"]: m["enabled"] for m in sa["mods"]}["space-age"] is True
    assert enabled.get("jamaltron-harness") is (True if with_harness else None), enabled
    assert "invalid" not in proc.stdout + proc.stderr, proc.stdout + proc.stderr
