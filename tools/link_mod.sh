#!/usr/bin/env bash
# Symlink mod/jamaltron into the player's Factorio mods directory, so the game
# loads the working tree and an edit is live on the next restart (no zip, no copy).
#
# That directory is not ours: it holds real mods (a hundred on the dev machine) and a
# mod-list.json the game rewrites every launch. So this script backs mod-list.json up
# OUTSIDE the mods dir first, refuses to clobber anything but its own symlink, and
# re-checks afterwards that the list is still valid JSON naming every mod it named
# before. Its only write is the one symlink.
#
# Idempotent. Factorio appends its own enabled entry for the mod on the next launch;
# the after-check exists to prove nothing else moved.
#
# Usage: tools/link_mod.sh [--status | --unlink] [--mods-dir PATH] [--mod-dir PATH]
#   --status         report the link and mod-list.json, change nothing
#   --mod-dir PATH   mod to link (default mod/jamaltron)
# Env:   FACTORIO_MODS_DIR=PATH    mods directory override
#        LINK_BACKUP_DIR=PATH      where mod-list.json backups land
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

MOD_DIR="$REPO_ROOT/mod/jamaltron"
MODS_DIR="${FACTORIO_MODS_DIR:-$HOME/Library/Application Support/factorio/mods}"
DEFAULT_BACKUP_DIR="${TMPDIR:-/tmp}"
BACKUP_DIR="${LINK_BACKUP_DIR:-${DEFAULT_BACKUP_DIR%/}/jamaltron-modlist-backups}"
ACTION='link'

usage() { sed -n '2,18p' "${BASH_SOURCE[0]}"; }
die() { echo "link: $*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --status)   ACTION='status'; shift ;;
    --unlink)   ACTION='unlink'; shift ;;
    --mods-dir) [ $# -ge 2 ] || die "--mods-dir needs a path"; MODS_DIR="$2"; shift 2 ;;
    --mod-dir)  [ $# -ge 2 ] || die "--mod-dir needs a path"; MOD_DIR="$2"; shift 2 ;;
    -h|--help)  usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

[ -d "$MOD_DIR" ] || die "mod directory not found: $MOD_DIR"
[ -f "$MOD_DIR/info.json" ] || die "no info.json in $MOD_DIR"
MOD_DIR="$(cd -- "$MOD_DIR" && pwd)"
[ -d "$MODS_DIR" ] || die "factorio mods directory not found: $MODS_DIR"
MODS_DIR="$(cd -- "$MODS_DIR" && pwd)"

info="$(python3 -c 'import json, sys
try:
    d = json.load(open(sys.argv[1]))
    print(d["name"], d["version"])
except Exception as exc:
    sys.exit(str(exc))' "$MOD_DIR/info.json")" ||
  die "bad $MOD_DIR/info.json (name and version required)"
MOD_NAME="${info%% *}"
MOD_VER="${info##* }"

# Unversioned link name on purpose: Factorio accepts <name> as well as
# <name>_<version>, and the bare name survives a version bump.
LINK="$MODS_DIR/$MOD_NAME"
MOD_LIST="$MODS_DIR/mod-list.json"

# Dumps one mod name per line, sorted. Doubles as the JSON validity check.
list_names() { # list_names <mod-list.json>
  python3 -c 'import json, sys
try:
    mods = json.load(open(sys.argv[1]))["mods"]
    names = sorted(m["name"] for m in mods)
except Exception as exc:
    sys.exit("mod-list.json: %s" % exc)
for name in names:
    print(name)' "$1"
}

snapshot_before() {
  [ -f "$MOD_LIST" ] || { echo "link: no mod-list.json yet (factorio writes one on next launch)"; return 0; }
  list_names "$MOD_LIST" > "$BEFORE" || die "mod-list.json is not valid JSON ALREADY - stopping before touching anything: $MOD_LIST"
  mkdir -p "$BACKUP_DIR"
  BACKUP="$BACKUP_DIR/mod-list.json.$(date +%Y%m%dT%H%M%S)"
  cp "$MOD_LIST" "$BACKUP"
  echo "link: backed up mod-list.json ($(grep -c . "$BEFORE") mods) to $BACKUP"
}

verify_after() {
  [ -f "$MOD_LIST" ] || return 0
  [ -s "$BEFORE" ] || return 0
  list_names "$MOD_LIST" > "$AFTER" ||
    die "mod-list.json no longer parses. restore it: cp '$BACKUP' '$MOD_LIST'"
  local lost
  lost="$(comm -23 "$BEFORE" "$AFTER" || true)"
  if [ -n "$lost" ]; then
    echo "link: mod-list.json LOST entries: $(printf '%s ' "$lost")" >&2
    die "restore it: cp '$BACKUP' '$MOD_LIST'"
  fi
  local gained
  gained="$(comm -13 "$BEFORE" "$AFTER" || true)"
  if [ -n "$gained" ]; then
    echo "link: mod-list.json gained: $(printf '%s ' "$gained")"
  fi
  echo "link: mod-list.json still valid JSON, still lists all $(grep -c . "$BEFORE") mods"
}

TMPWORK="$(mktemp -d "${TMPDIR:-/tmp}/jamaltron-link.XXXXXX")"
BEFORE="$TMPWORK/before.txt"
AFTER="$TMPWORK/after.txt"
BACKUP=''
cleanup() { local rc=$?; rm -rf "$TMPWORK"; exit "$rc"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

describe_link() {
  if [ -L "$LINK" ]; then
    echo "link: $LINK -> $(readlink "$LINK")"
  elif [ -e "$LINK" ]; then
    echo "link: $LINK exists and is NOT a symlink"
  else
    echo "link: $LINK does not exist"
  fi
}

case "$ACTION" in
  status)
    describe_link
    if [ -f "$MOD_LIST" ]; then
      list_names "$MOD_LIST" > "$BEFORE" || die "mod-list.json is not valid JSON: $MOD_LIST"
      echo "link: mod-list.json valid, $(grep -c . "$BEFORE") mods, $MOD_NAME listed: $(grep -qx "$MOD_NAME" "$BEFORE" && echo yes || echo no)"
    else
      echo "link: no mod-list.json in $MODS_DIR"
    fi
    ;;

  link)
    if [ -L "$LINK" ]; then
      target="$(cd -- "$(dirname -- "$LINK")" && cd -- "$(readlink "$LINK")" 2>/dev/null && pwd)" || target=''
      if [ "$target" = "$MOD_DIR" ]; then
        echo "link: already linked, nothing to do ($LINK -> $MOD_DIR)"
        exit 0
      fi
      die "$LINK is a symlink to something else ($(readlink "$LINK")) - remove it yourself if that is stale"
    fi
    [ ! -e "$LINK" ] ||
      die "$LINK already exists and is not our symlink (a real mod folder?) - refusing to touch it"

    snapshot_before
    ln -s "$MOD_DIR" "$LINK"
    echo "link: created $LINK -> $MOD_DIR"
    verify_after
    echo "link: ok - $MOD_NAME $MOD_VER will load from the working tree on the next factorio launch"
    ;;

  unlink)
    if [ ! -e "$LINK" ] && [ ! -L "$LINK" ]; then
      echo "link: nothing to remove, $LINK does not exist"
      exit 0
    fi
    [ -L "$LINK" ] || die "$LINK is not a symlink - refusing to delete it"
    target="$(readlink "$LINK")"
    snapshot_before
    rm "$LINK"
    echo "link: removed $LINK (pointed at $target)"
    verify_after
    ;;
esac
