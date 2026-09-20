#!/usr/bin/env bash
# Both Lua gates in one command: luacheck (undefined globals, dead locals, style)
# and the lua-language-server TYPE check against the FMTK Factorio defs. This is
# PLAN A.3's gate - run it before every commit, and in CI.
#
# BOTH GATES RUN FROM THE REPO ROOT, which is not cosmetic. MEASURED 2026-09-19:
# .luarc.json's workspace.library entries are workspace-relative, so aiming the
# language server at ./mod - even with --configpath - resolves neither the FMTK
# bundle nor .ls-defs/supplement, and invents 24 undefined-global warnings out of
# nothing. `lua-language-server --check .` from the root is the only invocation
# whose output means anything. .luacheckrc is found the same way.
#
# Exit status is not the whole verdict. lua-language-server exits 1 when it finds
# problems and 0 when it does not, but a run that never got as far as diagnosing
# (wrong workspace, unreadable config) has nothing to report and no reason to exit
# nonzero - so the "Diagnosis complete" summary line is parsed too, and a run with
# no verdict line fails. Same rule tools/smoke.sh applies to the game's own log.
#
# A missing lua-language-server SKIPS the type gate with a message instead of
# failing the run - it is a 30 MB binary and luacheck is the one that has to be
# everywhere. Skipping every gate is still a failure: a green that checked nothing
# is worse than a red.
#
# Not covered here: the shell scripts in this directory. shellcheck is not
# installed on this machine, so tools/*.sh has never been linted by anything.
#
# Usage: tools/lint.sh [-q] [-v]
# Env:   LUACHECK_BIN=PATH   luacheck override
#        LUALS_BIN=PATH      lua-language-server override
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

LUACHECK_BIN="${LUACHECK_BIN:-luacheck}"
LUALS_BIN="${LUALS_BIN:-lua-language-server}"
DEFS="$REPO_ROOT/.ls-defs/factorio"
QUIET=0
VERBOSE=0

usage() { sed -n '2,29p' "${BASH_SOURCE[0]}"; }
die() { echo "lint: $*" >&2; exit 2; }
say() { [ "$QUIET" -eq 1 ] || echo "lint: $*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    -q|--quiet)   QUIET=1; shift ;;
    -v|--verbose) VERBOSE=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

[ -d "$REPO_ROOT/mod" ] || die "no mod/ under $REPO_ROOT"

TMPWORK="$(mktemp -d "${TMPDIR:-/tmp}/jamaltron-lint.XXXXXX")"
cleanup() { local rc=$?; rm -rf "$TMPWORK"; exit "$rc"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# ANSI codes survive a pipe, and a log file full of them is unreadable. luacheck
# has --no-color; the language server does not, so strip on the way out.
decolor() { sed 's/\x1b\[[0-9;]*m//g'; }

fail=0
ran=0

# ---- gate 1: luacheck -------------------------------------------------------
# Exit 1 is warnings, >=2 is errors or a bad config. Both are failures here: the
# .luacheckrc already decides what is worth reporting, so anything that reaches
# stdout is something we asked to hear about.
if command -v "$LUACHECK_BIN" >/dev/null 2>&1; then
  ran=1
  rc=0
  ( cd "$REPO_ROOT" && "$LUACHECK_BIN" --no-color mod/ ) >"$TMPWORK/luacheck.txt" 2>&1 || rc=$?
  total="$(grep -E '^Total: ' "$TMPWORK/luacheck.txt" | tail -1 || true)"
  if [ "$rc" -eq 0 ]; then
    say "ok   luacheck  ${total:-clean}"
    [ "$VERBOSE" -eq 0 ] || sed 's/^/    /' "$TMPWORK/luacheck.txt"
  else
    echo "lint: FAIL luacheck (exit $rc)"
    sed 's/^/    /' "$TMPWORK/luacheck.txt"
    fail=1
  fi
else
  echo "lint: SKIP luacheck - '$LUACHECK_BIN' not on PATH (brew install luacheck)"
fi

# ---- gate 2: lua-language-server type check ---------------------------------
# The defs are gitignored and 7 MB, so a fresh clone has none - and without them the
# type gate is worse than useless. MEASURED 2026-09-19 on a tree that is otherwise
# clean: 56 problems, 35 of them undefined-global, every one of them about base-game
# API this mod never wrote. So stop, and say which command fixes it.
if command -v "$LUALS_BIN" >/dev/null 2>&1; then
  if [ ! -d "$DEFS/library" ] || [ ! -f "$DEFS/plugin.lua" ]; then
    die "$DEFS is missing or incomplete - the Factorio type defs are gitignored, generate them: tools/gen-defs.sh"
  fi
  ran=1
  rc=0
  # --logpath keeps the server's 600 KB run log out of the repo (and out of the
  # homebrew install dir). --checklevel is the default, pinned so a future default
  # cannot quietly downgrade Warnings - which is what every type mismatch is.
  ( cd "$REPO_ROOT" && "$LUALS_BIN" --check . \
      --checklevel=Warning --check_format=pretty --logpath "$TMPWORK/luals-log" ) \
    >"$TMPWORK/luals.txt" 2>&1 || rc=$?
  # The progress bar is carriage-return spam; fold it to lines and drop it, leaving
  # the diagnostics and the verdict.
  tr '\r' '\n' < "$TMPWORK/luals.txt" | decolor |
    grep -vE '^[[:space:]]*(>*[[:space:]]*[0-9]+/[0-9]+.*)?$' |
    grep -v '^Initializing' > "$TMPWORK/luals-clean.txt" || true
  verdict="$(grep -E 'Diagnosis complete' "$TMPWORK/luals-clean.txt" | tail -1 || true)"
  if [ -z "$verdict" ]; then
    echo "lint: FAIL types - lua-language-server produced no verdict line (exit $rc):"
    tail -n 20 "$TMPWORK/luals-clean.txt" | sed 's/^/    /'
    fail=1
  elif [ "$rc" -eq 0 ] && printf '%s' "$verdict" | grep -q 'no problems found'; then
    say "ok   types     $verdict (workspace $REPO_ROOT)"
    [ "$VERBOSE" -eq 0 ] || sed 's/^/    /' "$TMPWORK/luals-clean.txt"
  else
    echo "lint: FAIL types - $verdict (exit $rc)"
    sed 's/^/    /' "$TMPWORK/luals-clean.txt"
    fail=1
  fi
else
  echo "lint: SKIP types - '$LUALS_BIN' not on PATH (brew install lua-language-server)"
fi

if [ "$ran" -eq 0 ]; then
  echo "lint: FAILED - neither gate could run, so nothing was checked" >&2
  exit 1
fi
if [ "$fail" -ne 0 ]; then
  echo "lint: FAILED"
  exit 1
fi
say "PASSED"
