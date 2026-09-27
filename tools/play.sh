#!/usr/bin/env bash
# Launch the REAL Factorio GUI on an isolated, persistent playtest profile, so playtesting
# never touches your own saves, mod list, mod settings or keybinds.
#
# Everything lives under .playtest/ at the repo root (gitignored):
#   config.ini   read-data = the installed game, write-data = .playtest/write
#   write/       this profile's saves, logs and player-data.json
#   mods/        jamaltron (a SYMLINK to mod/jamaltron, so a code edit is live on the next
#                launch), jamaltron-playtest (the /jamaltron-* console commands) and the
#                mod-list.json this script writes; the game adds mod-settings.dat itself
#
# Your real profile under ~/Library/Application Support/factorio is never read or written:
# --config points at .playtest/config.ini (every path under .playtest), --mod-directory at
# .playtest/mods. Same isolation as tools/smoke.sh, but kept between runs so test saves and
# settings survive.
#
# In game: /jamaltron-kit gives you a Jamaltron and logs each line's row id (/jamaltron-ids for chat);
# /jamaltron-say, -row, -state, -swap and -jump-mode are documented at the top of
# tools/playtest/jamaltron-playtest/control.lua. His lines log to <profile>/write/factorio-current.log,
# a --new map's creation to <profile>/create.log.
#
# Usage: tools/play.sh [--new] [--base-only] [--reset] [--prepare] [-- factorio args...]
#   --new        build a fresh map in the profile and load straight into it
#   --base-only  no Space Age (default: on, like the smoke test's second stage)
#   --reset      delete the profile first - saves included - and start clean
#   --prepare    set the profile up (and build the map, with --new) but do not launch
#   -- ARGS      passed straight to factorio
#   -h, --help   this text
# Env:   FACTORIO_BIN=/path/to/factorio   binary override (FACTORIO also accepted)
#        PLAYTEST_DIR=PATH                profile location override
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

FACTORIO_BIN="${FACTORIO_BIN:-${FACTORIO:-/Applications/factorio.app/Contents/MacOS/factorio}}"
DIR="${PLAYTEST_DIR:-$REPO_ROOT/.playtest}"
MOD_SRC="$REPO_ROOT/mod/jamaltron"
KIT_SRC="$REPO_ROOT/tools/playtest/jamaltron-playtest"
MARKER=".jamaltron-playtest"          # only a directory carrying this is ours to delete
REAL_PROFILE="$HOME/Library/Application Support/factorio"
NEW=0
DLC=true
RESET=0
LAUNCH=1

usage() { sed -n '2,30p' "${BASH_SOURCE[0]}"; }
die() { echo "play: $*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --new)       NEW=1; shift ;;
    --base-only) DLC=false; shift ;;
    --reset)     RESET=1; shift ;;
    --prepare)   LAUNCH=0; shift ;;
    -h|--help)   usage; exit 0 ;;
    --)          shift; break ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

[ -x "$FACTORIO_BIN" ] || die "factorio binary not executable: $FACTORIO_BIN (set FACTORIO_BIN=...)"
READ_DATA="$(cd -- "$(dirname -- "$FACTORIO_BIN")/../data" 2>/dev/null && pwd)" ||
  die "cannot find a data dir next to $FACTORIO_BIN"
[ -d "$READ_DATA/base" ] || die "no base game data under $READ_DATA"
[ -f "$MOD_SRC/info.json" ] || die "no mod at $MOD_SRC"

# The profile must be its own directory - never your real one or a parent of it. Checked
# BEFORE anything is created (lexical path) and again after (symlinks resolved), so a bad
# PLAYTEST_DIR cannot even leave an empty folder behind.
check_dir() {
  case "$1" in
    /|"$HOME"|"$REPO_ROOT") die "refusing to use '$1' as the playtest profile" ;;
  esac
  case "$REAL_PROFILE/" in
    "$1"/*) die "refusing '$1': it contains your real Factorio profile" ;;
  esac
  case "$1/" in
    "$REAL_PROFILE"/*) die "refusing '$1': it is inside your real Factorio profile" ;;
  esac
}
DIR="$(python3 -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "$DIR")"
check_dir "$DIR"
DIR="$(mkdir -p -- "$DIR" && cd -- "$DIR" && pwd -P)"
check_dir "$DIR"

if [ "$RESET" -eq 1 ]; then
  if [ -n "$(ls -A -- "$DIR")" ] && [ ! -f "$DIR/$MARKER" ]; then
    die "--reset refused: $DIR is not empty and was not made by this script (no $MARKER)"
  fi
  rm -rf -- "$DIR"
  mkdir -p -- "$DIR"
fi
if [ -n "$(ls -A -- "$DIR")" ] && [ ! -f "$DIR/$MARKER" ]; then
  die "$DIR is not empty and was not made by this script; point PLAYTEST_DIR somewhere else"
fi
touch "$DIR/$MARKER"
mkdir -p "$DIR/write/saves" "$DIR/mods"

cat > "$DIR/config.ini" <<EOF
; tools/play.sh's isolated playtest profile - never point write-data at the real one
[path]
read-data=$READ_DATA
write-data=$DIR/write
[general]
locale=en
[other]
check-updates=false
enable-crash-log-uploading=false
EOF

link() { # link <target> <name>: our symlink, or refuse to touch what is there
  local target="$1" at="$DIR/mods/$2"
  if [ -e "$at" ] && [ ! -L "$at" ]; then
    die "$at exists and is not a symlink this script made; not touching it"
  fi
  ln -sfn "$target" "$at"
}
link "$MOD_SRC" jamaltron
link "$KIT_SRC" jamaltron-playtest

# Rewritten every launch, so --base-only is a switch and not a one-way door. The game
# appends anything else it finds; nothing else lives in this mods dir.
cat > "$DIR/mods/mod-list.json" <<EOF
{"mods":[
 {"name":"base","enabled":true},
 {"name":"elevated-rails","enabled":$DLC},
 {"name":"quality","enabled":$DLC},
 {"name":"recycler","enabled":$DLC},
 {"name":"space-age","enabled":$DLC},
 {"name":"jamaltron","enabled":true},
 {"name":"jamaltron-playtest","enabled":true}]}
EOF

ARGS=(--config "$DIR/config.ini" --mod-directory "$DIR/mods")

if [ "$NEW" -eq 1 ]; then
  save="$DIR/write/saves/playtest-$(date +%Y%m%d-%H%M%S).zip"
  echo "play: building a fresh map -> ${save#"$REPO_ROOT"/}"
  rc=0
  "$FACTORIO_BIN" "${ARGS[@]}" --disable-audio --create "$save" >"$DIR/create.log" 2>&1 || rc=$?
  if [ "$rc" -ne 0 ] || [ ! -f "$save" ] ||
     grep -qE '^[[:space:]]*[0-9]+\.[0-9]+ Error |^Error' "$DIR/create.log"; then
    grep -nE -A 3 'Error' "$DIR/create.log" | head -20 >&2 || true
    die "map creation failed (exit $rc); full log: $DIR/create.log"
  fi
  ARGS+=(--load-game "$save")
fi

echo "play: profile ${DIR#"$REPO_ROOT"/} (Space Age: $DLC), jamaltron linked from the working tree"
echo "play: in game, /jamaltron-kit; his lines log to ${DIR#"$REPO_ROOT"/}/write/factorio-current.log"
if [ "$LAUNCH" -eq 0 ]; then
  echo "play: --prepare, not launching. Launch: ${FACTORIO_BIN} ${ARGS[*]} $*"
  exit 0
fi
exec "$FACTORIO_BIN" "${ARGS[@]}" "$@"
