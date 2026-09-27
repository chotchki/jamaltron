#!/usr/bin/env bash
# Package mod/jamaltron as a mod-portal zip.
#
# The version comes from info.json only (never a flag or this script), so bumping
# info.json is the whole release ceremony.
#
# The engine enforces less than the portal docs imply. For a ZIP mod Factorio reads
# name and version off the ZIP FILENAME, so <name>_<version>.zip is mandatory.
# MEASURED 2.1.17: the folder inside the zip is never checked - a
# jamaltron_0.1.0.zip whose only top-level folder is wrongroot/ loads clean. The
# naming rule that does bite is for an UNPACKED mod: a directory in mods/ must be
# <name> or <name>_<version>, or the game refuses it ("Directory name of mod ...
# doesn't match the expected ...").
#
# Ships <name>_<version>/ inside anyway: it is the one inner name still legal if
# someone unzips into mods/ (and the portal convention, at no cost).
#
# Output lands in dist/ (gitignored). --verify loads the finished zip in headless
# Factorio via tools/smoke.sh, the only proof the upload actually works.
#
# Usage: tools/build.sh [--out DIR] [--mod-dir DIR] [--verify] [-q]
#   --out DIR, --mod-dir DIR   override dist/ and mod/jamaltron
#   -q                         drop progress lines; the zip path still prints last
#   -h, --help                 this text
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

MOD_DIR="$REPO_ROOT/mod/jamaltron"
OUT_DIR="$REPO_ROOT/dist"
VERIFY=0
QUIET=0

usage() { sed -n '2,24p' "${BASH_SOURCE[0]}"; }
die() { echo "build: $*" >&2; exit 2; }
say() { [ "$QUIET" -eq 1 ] || echo "build: $*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --out)      [ $# -ge 2 ] || die "--out needs a directory"; OUT_DIR="$2"; shift 2 ;;
    --mod-dir)  [ $# -ge 2 ] || die "--mod-dir needs a directory"; MOD_DIR="$2"; shift 2 ;;
    --verify)   VERIFY=1; shift ;;
    -q|--quiet) QUIET=1; shift ;;
    -h|--help)  usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

[ -d "$MOD_DIR" ] || die "mod directory not found: $MOD_DIR"
[ -f "$MOD_DIR/info.json" ] || die "no info.json in $MOD_DIR"
MOD_DIR="$(cd -- "$MOD_DIR" && pwd)"

info="$(python3 -c 'import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d["name"], d["version"])
except Exception as exc:
    sys.exit(str(exc))' "$MOD_DIR/info.json")" ||
  die "bad $MOD_DIR/info.json (name and version required)"
MOD_NAME="${info%% *}"
MOD_VER="${info##* }"
FOLDER="${MOD_NAME}_${MOD_VER}"
ZIP="$OUT_DIR/$FOLDER.zip"

mkdir -p "$OUT_DIR"
OUT_DIR="$(cd -- "$OUT_DIR" && pwd)"
ZIP="$OUT_DIR/$FOLDER.zip"
STAGE="$OUT_DIR/.stage"

cleanup() { local rc=$?; rm -rf "$STAGE"; exit "$rc"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

rm -rf "$STAGE"
mkdir -p "$STAGE/$FOLDER"
# Copy then prune, so the staged tree IS the shipped tree and can be inspected.
# zip -x is a backstop for anything the prune list misses.
cp -R "$MOD_DIR/." "$STAGE/$FOLDER/"
find "$STAGE" \( \
  -name '.DS_Store' -o -name '._*' -o -name '.gitkeep' -o -name '.gitignore' -o \
  -name '.git' -o -name '*.orig' -o -name '*.rej' -o -name '*~' -o \
  -name '__pycache__' -o -name 'Thumbs.db' \) -exec rm -rf {} +
# Sweep directories the prune emptied: one held only by a .gitkeep would otherwise
# ship as an empty entry (harmless to Factorio, still not meant to ship). -delete
# implies -depth, so nested empties collapse in one pass.
find "$STAGE/$FOLDER" -mindepth 1 -type d -empty -delete

[ -f "$STAGE/$FOLDER/info.json" ] || die "staging lost info.json, refusing to ship"

rm -f "$ZIP"
( cd "$STAGE" && zip -q -r -X "$ZIP" "$FOLDER" \
    -x '*.DS_Store' -x '*/._*' -x '*/.git/*' ) ||
  die "zip failed"

# Verify the shipped layout instead of trusting the code above. The zip FILENAME
# is the engine's gate ($FOLDER.zip by construction); the single inner root is this
# project's rule (header), checked because a staging bug is otherwise silent.
roots="$(unzip -Z1 "$ZIP" | awk -F/ '{print $1}' | sort -u)"
[ "$roots" = "$FOLDER" ] ||
  die "zip root is '$(printf '%s ' "$roots")' but this build ships exactly '$FOLDER/'"
unzip -Z1 "$ZIP" | grep -Fxq "$FOLDER/info.json" ||
  die "no $FOLDER/info.json inside the zip"

bytes="$(wc -c < "$ZIP" | tr -d ' ')"
files="$(unzip -Z1 "$ZIP" | grep -vc '/$' || true)"
human="$(awk -v b="$bytes" 'BEGIN{
  split("B KiB MiB GiB", u, " "); i=1
  while (b >= 1024 && i < 4) { b /= 1024; i++ }
  printf (i == 1 ? "%d %s" : "%.1f %s"), b, u[i]
}')"

if [ "$VERIFY" -eq 1 ]; then
  say "verifying the zip loads in headless factorio"
  "$SCRIPT_DIR/smoke.sh" --mod-zip "$ZIP" || die "the zip does not load, not shipping it"
fi

say "$FOLDER.zip  $human ($bytes bytes), $files files, root $FOLDER/"
echo "$ZIP"
