#!/usr/bin/env bash
# Both Lua gates in one command: luacheck (undefined globals, dead locals, style)
# and the lua-language-server TYPE check against the FMTK Factorio defs. PLAN A.3's
# gate: run it before every commit; CI runs each gate as its own job.
#
# BOTH GATES RUN FROM THE REPO ROOT. MEASURED 2026-09-19: .luarc.json's
# workspace.library entries are workspace-relative, so aiming the language server at
# ./mod (even with --configpath) resolves neither the FMTK bundle nor
# .ls-defs/supplement and invents 24 undefined-global warnings. Only
# `lua-language-server --check .` from the root means anything. .luacheckrc is found
# the same way.
#
# Exit status is not the whole verdict: lua-language-server exits 1 on problems and
# 0 otherwise, but a run that never reached diagnosis (wrong workspace, unreadable
# config) has no reason to exit nonzero. So the "Diagnosis complete" line is parsed
# too and a run without it fails - the rule tools/smoke.sh applies to the game log.
#
# A missing lua-language-server SKIPS the type gate with a message (a 30 MB binary;
# luacheck is the one that has to be everywhere). Skipping BOTH gates fails: a pass
# that checked nothing is worse than a failure.
#
# --only GATE runs one gate and makes it MANDATORY: named, a gate whose binary is
# missing FAILS instead of skipping. CI calls this (PLAN C.14), one job per gate, so
# each reports on its own and neither passes on a runner that lost its binary.
#
# Not covered: tools/*.sh. shellcheck is not installed locally or in CI, so no shell
# script here has ever been linted.
#
# Usage: tools/lint.sh [--only luacheck|types] [-q] [-v]
#   --only GATE   run one gate; it may not skip
#   -q   drop the ok/PASSED lines; SKIP, FAIL and a failing gate's output still print
#   -v   print each gate's full output even when it passes
# Env:   LUACHECK_BIN=PATH   luacheck override
#        LUALS_BIN=PATH      lua-language-server override
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

LUACHECK_BIN="${LUACHECK_BIN:-luacheck}"
LUALS_BIN="${LUALS_BIN:-lua-language-server}"
DEFS="$REPO_ROOT/.ls-defs/factorio"
ONLY=''
QUIET=0
VERBOSE=0

usage() { sed -n '2,34p' "${BASH_SOURCE[0]}"; }
die() { echo "lint: $*" >&2; exit 2; }
say() { [ "$QUIET" -eq 1 ] || echo "lint: $*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --only)
      [ $# -ge 2 ] || die "--only needs a gate: luacheck or types"
      case "$2" in
        luacheck|types) ONLY="$2" ;;
        *) die "--only takes luacheck or types, not '$2'" ;;
      esac
      shift 2 ;;
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

# ANSI codes survive a pipe and make a log unreadable. luacheck has --no-color; the
# language server does not, so strip on the way out.
decolor() { sed 's/\x1b\[[0-9;]*m//g'; }

fail=0
ran=0

# wanted <gate>: is this gate in the run at all. required <gate>: may it skip.
# One derivation from --only, so "selected" and "mandatory" cannot disagree.
wanted()   { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }
required() { [ "$ONLY" = "$1" ]; }
# A gate whose binary is missing: SKIP by default, FAIL when it was asked for by name.
missing() { # missing <gate> <bin> <install hint>
  if required "$1"; then
    echo "lint: FAIL $1 - '$2' not on PATH, and --only $1 means it may not skip ($3)"
    fail=1
  else
    echo "lint: SKIP $1 - '$2' not on PATH ($3)"
  fi
}

# ---- gate 1: luacheck -------------------------------------------------------
# Exit 1 is warnings, >=2 is errors or a bad config. Both fail here: .luacheckrc
# already decides what is worth reporting.
if ! wanted luacheck; then
  :
elif command -v "$LUACHECK_BIN" >/dev/null 2>&1; then
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
  missing luacheck "$LUACHECK_BIN" "brew install luacheck"
fi

# ---- gate 2: lua-language-server type check ---------------------------------
# The defs are gitignored (7 MB), so a fresh clone has none, and without them the
# type gate is worse than useless. MEASURED 2026-09-19 on an otherwise clean tree: 56
# problems, 35 undefined-global, all about base-game API this mod never wrote. So
# stop and name the fix.
if ! wanted types; then
  :
elif command -v "$LUALS_BIN" >/dev/null 2>&1; then
  if [ ! -d "$DEFS/library" ] || [ ! -f "$DEFS/plugin.lua" ]; then
    die "$DEFS is missing or incomplete - the Factorio type defs are gitignored, generate them: tools/gen-defs.sh"
  fi
  ran=1
  rc=0
  # --logpath keeps the server's 600 KB run log out of the repo and the homebrew
  # install dir. --checklevel is the default, pinned so a future default cannot
  # quietly drop Warnings (every type mismatch is one).
  ( cd "$REPO_ROOT" && "$LUALS_BIN" --check . \
      --checklevel=Warning --check_format=pretty --logpath "$TMPWORK/luals-log" ) \
    >"$TMPWORK/luals.txt" 2>&1 || rc=$?
  # Fold the carriage-return progress bar to lines and drop it, leaving the
  # diagnostics and the verdict.
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
  missing types "$LUALS_BIN" "brew install lua-language-server"
fi

if [ "$fail" -ne 0 ]; then
  echo "lint: FAILED"
  exit 1
fi
if [ "$ran" -eq 0 ]; then
  echo "lint: FAILED - neither gate could run, so nothing was checked" >&2
  exit 1
fi
say "PASSED${ONLY:+ (--only $ONLY)}"
