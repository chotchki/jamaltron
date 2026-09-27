#!/usr/bin/env bash
# Screenshots of jamaltron out of the REAL renderer, no hands (headless draws nothing; the
# alternative is a play.sh session and chotchki's eye). Loads a fixture save in
# `factorio --benchmark-graphics` (a real window with real sprites and render layers, for
# exactly as many ticks as the shots need), lets tools/harness/jamaltron-shot stage a scene
# through the mod's own code, and copies the game's screenshots out. ~10 s a run.
#
# THE FIXTURE is a custom save, built once and loaded every run after (chotchki 2026-09-26:
# "loading a custom save will probably be best to iterate on quickly"): a clean flat pad at
# noon, no crash site, no biters. TERRAIN ONLY: the scene is staged fresh on every load, so a
# mod edit shows on the next run with no rebuild. --fresh rebuilds it (--tile and --base-only
# imply it); needed when the current mod set cannot load the old save.
#
# Isolated like smoke.sh: own config.ini, write-data and mod dir under .shottest/ (never your
# real profile), jamaltron SYMLINKED from the working tree, the stager COPIED in beside the
# scene.lua this script writes.
#
# Usage: tools/shot.sh [--scene beached|standing|both|many] [--many N] [--at T,T,...]
#                      [--every K --count N] [--start T] [--zoom Z] [--res WxH] [--center X,Y]
#                      [--out DIR] [--gif] [--tile NAME] [--base-only] [--fresh] [--stager DIR]
#   --scene    what to stage (default beached: a real break, airborne -> landed at 100%);
#              many is N real breaks in a grid 9 tiles apart plus one standing for scale (each
#              break draws its own legs off the map rng, so one shot shows the layout's spread)
#   --many     N for --scene many, 1-16 (default 6). The grid is framed whole: with no --zoom
#              the zoom drops below 1 when it has to (13+ at 1600x900); a --zoom that crops it
#              warns
#   --at       screenshot ticks after staging, each >= 1 (default 120 - past the landing's dust)
#   --every/--count/--start   a burst instead: N shots K ticks apart from --start (default 120, >= 1)
#   --zoom     1 is the game's default zoom; 2 is close up (default 1)
#   --center   X,Y in tiles the scene is staged around (default 0,0)
#   --tile     the fixture's ground tile (default sand-1)
#   --res      pixels (default 1600x900)
#   --out      where the PNGs land (default render-out/shots/<scene>-<stamp>/)
#   --gif      also assemble the burst into shots.gif at the game's 60 ticks/s
#   --stager   a copy of tools/harness/jamaltron-shot to load instead (a spike's own data.lua
#              and drawing code, with the mod untouched); it keeps the name jamaltron-shot
# Env:   FACTORIO_BIN=/path/to/factorio   binary override (FACTORIO also accepted)
#        SHOT_DIR=PATH                    profile location override
#
# Every argument is checked before anything is created or launched; tools/tests/test_shot.py
# runs them all without Factorio.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FACTORIO_BIN="${FACTORIO_BIN:-${FACTORIO:-/Applications/factorio.app/Contents/MacOS/factorio}}"
DIR="${SHOT_DIR:-$REPO_ROOT/.shottest}"
MOD_SRC="$REPO_ROOT/mod/jamaltron"
STAGER_SRC="$SCRIPT_DIR/harness/jamaltron-shot"

SCENE=beached
MANY=""
AT="120"
EVERY=""
COUNT=""
START=120
ZOOM=1
ZOOM_SET=0
SPACING=9   # tiles between Jamals in `many` (a wreck spans ~6, a break drifts ~1.5)
RES="1600x900"
CENTER="0,0"
OUT=""
GIF=0
TILE="sand-1"
DLC=true
FRESH=0

# The header above, up to the first line that is not a comment.
usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"; }
die() { echo "shot: $*" >&2; exit 2; }
# `--flag VALUE`: a missing or empty VALUE is a usage error, not bash's "2: parameter null".
val() { [ -n "${2:-}" ] || die "$1 wants a value (try --help)"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --scene)     val "$@"; SCENE="$2"; shift 2 ;;
    --many)      val "$@"; MANY="$2"; shift 2 ;;
    --at)        val "$@"; AT="$2"; shift 2 ;;
    --every)     val "$@"; EVERY="$2"; shift 2 ;;
    --count)     val "$@"; COUNT="$2"; shift 2 ;;
    --start)     val "$@"; START="$2"; shift 2 ;;
    --zoom)      val "$@"; ZOOM="$2"; ZOOM_SET=1; shift 2 ;;
    --res)       val "$@"; RES="$2"; shift 2 ;;
    --center)    val "$@"; CENTER="$2"; shift 2 ;;
    --out)       val "$@"; OUT="$2"; shift 2 ;;
    --gif)       GIF=1; shift ;;
    --tile)      val "$@"; TILE="$2"; FRESH=1; shift 2 ;;
    --base-only) DLC=false; FRESH=1; shift ;;
    --fresh)     FRESH=1; shift ;;
    --stager)    val "$@"; STAGER_SRC="$(cd -- "$2" 2>/dev/null && pwd)" ||
                   die "--stager wants a directory, got '$2'"
                 shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

# Everything below lands in scene.lua as Lua source, so nothing reaches it unvalidated.
NUM='-?([0-9]+(\.[0-9]*)?|\.[0-9]+)'
case "$SCENE" in beached|standing|both|many) ;; *) die "--scene is beached, standing, both or many, got '$SCENE'" ;; esac
if [ "$SCENE" = many ]; then
  MANY="${MANY:-6}"
  [[ "$MANY" =~ ^[1-9][0-9]*$ ]] && [ "$MANY" -le 16 ] ||
    die "--many wants a whole number 1-16, got '$MANY'"
else
  [ -z "$MANY" ] || die "--many only goes with --scene many"
  MANY=0
fi
[[ "$RES" =~ ^([1-9][0-9]*)x([1-9][0-9]*)$ ]] || die "--res wants WxH in pixels, got '$RES'"
RES_W="${BASH_REMATCH[1]}"
RES_H="${BASH_REMATCH[2]}"
RES_LUA="{$RES_W, $RES_H}"
[[ "$CENTER" =~ ^$NUM,$NUM$ ]] || die "--center wants X,Y in tiles, got '$CENTER'"
[[ "$ZOOM" =~ ^$NUM$ && ! "$ZOOM" =~ ^- ]] && awk -v z="$ZOOM" 'BEGIN { exit !(z > 0) }' ||
  die "--zoom wants a number above 0, got '$ZOOM'"
[[ "$TILE" =~ ^[a-z0-9-]+$ ]] || die "--tile wants a tile prototype name, got '$TILE'"

# Tick 0 is spent staging: a shot there is never taken, and the run would only report it after
# the whole launch, as a missing screenshot.
TICKS='[1-9][0-9]*'
if [ -n "$EVERY$COUNT" ]; then
  [[ "$EVERY" =~ ^$TICKS$ && "$COUNT" =~ ^$TICKS$ ]] ||
    die "--every and --count want whole numbers, together"
  [[ "$START" =~ ^$TICKS$ ]] || die "--start wants a tick after staging (>= 1), got '$START'"
  AT="$(python3 -c 'import sys; s, k, n = map(int, sys.argv[1:]); print(",".join(str(s + k * i) for i in range(n)))' "$START" "$EVERY" "$COUNT")"
fi
[[ "$AT" =~ ^$TICKS(,$TICKS)*$ ]] || die "--at wants ticks after staging (>= 1) like 60,120, got '$AT'"
LAST="$(printf '%s\n' "${AT//,/$'\n'}" | sort -n | tail -1)"
[ "$GIF" -eq 0 ] || [ -n "$EVERY" ] || die "--gif wants a burst (--every/--count)"

# `many` frames its whole grid: the largest zoom that fits the stager's layout (a near-square
# grid plus the standing column, SPACING apart, ~4 tiles of wreck past each centre - measured off
# a 6-break shot; 32 px a tile at zoom 1) into --res. No --zoom takes min(1, that); a --zoom past
# it crops, and says so.
if [ "$SCENE" = many ]; then
  FIT="$(python3 -c '
import math, sys
n, s, w, h = map(int, sys.argv[1:])
cols = math.ceil(math.sqrt(n))
rows = math.ceil(n / cols)
half_w, half_h = cols * s / 2 + 4, (rows - 1) * s / 2 + 4
print(math.floor(100 * min(w / (64 * half_w), h / (64 * half_h))) / 100)' "$MANY" "$SPACING" "$RES_W" "$RES_H")"
  if [ "$ZOOM_SET" -eq 0 ]; then
    ZOOM="$(awk -v f="$FIT" 'BEGIN { print (f < 1 ? f : 1) }')"
  elif awk -v z="$ZOOM" -v f="$FIT" 'BEGIN { exit !(z > f) }'; then
    echo "shot: --zoom $ZOOM crops the $MANY-break grid at ${RES_W}x$RES_H (it fits at <= $FIT)" >&2
  fi
fi

# The profile gets files written and mods/jamaltron-shot + write/script-output deleted, so it is
# never /, home, the repo or anywhere in the real profile. Judged BEFORE anything is created (a
# refused path is left as it was): on the RESOLVED path (trailing slash, `..`, symlink),
# case-folded (APFS is case-insensitive, so .../Factorio IS the real profile) and by inode where
# both ends exist. A case-only difference is refused on a case-sensitive disk too - a false
# refusal, the safe side.
DIR="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$DIR")"
why="$(python3 -c '
import os, sys
d, home, repo, profile = (os.path.realpath(p) for p in sys.argv[1:])
def same(a, b):
    if a.casefold() == b.casefold():
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False
if any(same(d, bad) for bad in ("/", home, repo)):
    print(f"refusing to use {d!r} as the shot profile (SHOT_DIR wants a dir of its own)")
else:
    p = d
    while True:
        if same(p, profile):
            print(f"refusing {d!r}: it is inside your real Factorio profile")
            break
        if p == os.path.dirname(p):
            break
        p = os.path.dirname(p)
' "$DIR" "$HOME" "$REPO_ROOT" "$HOME/Library/Application Support/factorio")"
[ -z "$why" ] || die "$why"

[ -x "$FACTORIO_BIN" ] || die "factorio binary not executable: $FACTORIO_BIN (set FACTORIO_BIN=...)"
READ_DATA="$(cd -- "$(dirname -- "$FACTORIO_BIN")/../data" 2>/dev/null && pwd)" ||
  die "cannot find a data dir next to $FACTORIO_BIN"
mkdir -p "$DIR/write" "$DIR/mods"

cat > "$DIR/config.ini" <<EOF
; tools/shot.sh's throwaway profile - never point write-data at the real one
[path]
read-data=$READ_DATA
write-data=$DIR/write
[general]
locale=en
[other]
check-updates=false
enable-crash-log-uploading=false
EOF

ln -sfn "$MOD_SRC" "$DIR/mods/jamaltron"
rm -rf "$DIR/mods/jamaltron-shot"
cp -R "$STAGER_SRC" "$DIR/mods/jamaltron-shot"
PREFIX="$SCENE"
cat > "$DIR/mods/jamaltron-shot/scene.lua" <<EOF
-- written by tools/shot.sh
return {scene = "$SCENE", shots = {$AT}, zoom = $ZOOM, resolution = $RES_LUA,
        center = {$CENTER}, tile = "$TILE", prefix = "$PREFIX", many = $MANY,
        spacing = $SPACING}
EOF
cat > "$DIR/mods/mod-list.json" <<EOF
{"mods":[
 {"name":"base","enabled":true},
 {"name":"elevated-rails","enabled":$DLC},
 {"name":"quality","enabled":$DLC},
 {"name":"recycler","enabled":$DLC},
 {"name":"space-age","enabled":$DLC},
 {"name":"jamaltron","enabled":true},
 {"name":"jamaltron-shot","enabled":true}]}
EOF

ARGS=(--config "$DIR/config.ini" --mod-directory "$DIR/mods" --disable-audio)
FIXTURE="$DIR/fixture.zip"
if [ "$FRESH" -eq 1 ] || [ ! -f "$FIXTURE" ]; then
  echo "shot: building the fixture save (tile $TILE, Space Age $DLC)"
  rm -f "$FIXTURE"
  "$FACTORIO_BIN" "${ARGS[@]}" --create "$FIXTURE" >"$DIR/create.log" 2>&1 || true
  [ -f "$FIXTURE" ] && ! grep -qE ' Error |SHOT FAIL' "$DIR/create.log" ||
    { grep -nE -A3 'Error|SHOT FAIL' "$DIR/create.log" | head -20 >&2; die "fixture build failed: $DIR/create.log"; }
fi

rm -rf "$DIR/write/script-output"
LOG="$DIR/run.log"
rc=0
"$FACTORIO_BIN" "${ARGS[@]}" --benchmark-graphics "$FIXTURE" --benchmark-ticks "$((LAST + 10))" \
  >"$LOG" 2>&1 || rc=$?
if [ "$rc" -ne 0 ] || grep -qE 'SHOT FAIL| Error ' "$LOG"; then
  grep -nE -A3 'SHOT FAIL| Error ' "$LOG" | head -20 >&2 || true
  die "run failed (exit $rc): $LOG"
fi
grep -q "SHOT staged" "$LOG" || die "the stager never ran (mod not loaded?): $LOG"

[ -n "$OUT" ] || OUT="$REPO_ROOT/render-out/shots/$SCENE-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
n=0
for f in "$DIR/write/script-output/$PREFIX"-*.png; do
  [ -f "$f" ] || continue
  cp "$f" "$OUT/"
  n=$((n + 1))
done
want="$(printf '%s\n' "${AT//,/$'\n'}" | sort -u | grep -c .)"
[ "$n" -eq "$want" ] || die "$n of $want screenshots written (the window may have closed first): $LOG"

if [ "$GIF" -eq 1 ]; then
  uv run --directory "$REPO_ROOT/tools" python - "$OUT" "$EVERY" <<'EOF'
import sys
from pathlib import Path
from PIL import Image
out, every = Path(sys.argv[1]), int(sys.argv[2])
frames = [Image.open(p).convert("RGB") for p in sorted(out.glob("*.png"))]
frames[0].save(out / "shots.gif", save_all=True, append_images=frames[1:],
               duration=round(1000 * every / 60), loop=0)
print(f"shot: {len(frames)} frames -> {out / 'shots.gif'}")
EOF
fi
echo "shot: $n screenshot(s) -> ${OUT#"$REPO_ROOT"/}"
