#!/usr/bin/env bash
# Headless smoke test for the jamaltron mod. The every-edit gate.
#
# Loads the mod in a THROWAWAY profile (own config.ini and write-data, a mod dir holding
# only our mod), never the real ~/Library/Application Support/factorio. Cheapest first:
#   1. base only   factorio --create     settings + data stage, control main chunk, on_init
#   2. Space Age   factorio --create     the same, with the DLC prototypes loaded
#   3. Space Age   factorio --benchmark  on_load plus N ticks of on_tick
#
# Exit status alone is NOT a gate: Factorio exits 0 on real failures (a malformed
# info.json silently SKIPS the mod; a typo'd prototype key is only a Warning, and only
# with --check-unused-prototype-data). Each stage is judged on exit status, zero
# Error/Warning lines and a positive "Loading mod <name>" line.
#
# Headless never loads sprites, so a missing PNG is invisible to all three stages. The
# asset preflight covers literal paths; the real graphics check is
# `factorio --dump-icon-sprites` (accurate, mac-only, ~35s).
#
# Usage: tools/smoke.sh [--mod-dir PATH|--mod-zip PATH] [--ticks N] [--keep] [-v]
#                       [--workdir PATH] [--harness DIR]
#   --harness DIR  also load a test-only mod (tools/harness/*) and judge its log: any
#                  `HARNESS FAIL` fails, `HARNESS done` must appear, every `HARNESS need
#                  <ERE>` must match a run line and no `HARNESS never <ERE>` may. --ticks
#                  defaults to 3800 with one (the idle timer needs most of a minute)
#   --keep         keep the scratch dir and its logs
# Env:   FACTORIO_BIN=/path/to/factorio   binary override (FACTORIO also accepted)
#        SMOKE_WORKDIR=PATH               scratch dir override
#        SMOKE_TIMEOUT=SECONDS            per-stage kill, 0 disables (default 120)
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

FACTORIO_BIN="${FACTORIO_BIN:-${FACTORIO:-/Applications/factorio.app/Contents/MacOS/factorio}}"
MOD_SRC="$REPO_ROOT/mod/jamaltron"
WORK="${SMOKE_WORKDIR:-$REPO_ROOT/.smoketest}"
TIMEOUT="${SMOKE_TIMEOUT:-120}"
TICKS=60
TICKS_SET=0
HARNESS_SRC=""
KEEP=0
VERBOSE=0

usage() { sed -n '2,28p' "${BASH_SOURCE[0]}"; }
die() { echo "smoke: $*" >&2; exit 2; }

while [ $# -gt 0 ]; do
  case "$1" in
    --mod-dir|--mod-zip) [ $# -ge 2 ] || die "$1 needs a path"; MOD_SRC="$2"; shift 2 ;;
    --workdir)           [ $# -ge 2 ] || die "$1 needs a path"; WORK="$2"; shift 2 ;;
    --ticks)             [ $# -ge 2 ] || die "$1 needs a number"; TICKS="$2"; TICKS_SET=1; shift 2 ;;
    --harness)           [ $# -ge 2 ] || die "$1 needs a path"; HARNESS_SRC="$2"; shift 2 ;;
    --keep)              KEEP=1; shift ;;
    -v|--verbose)        VERBOSE=1; shift ;;
    -h|--help)           usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

case "$TICKS" in ''|*[!0-9]*) die "--ticks wants a whole number, got '$TICKS'" ;; esac
HARNESS_NAME=""
if [ -n "$HARNESS_SRC" ]; then
  [ -f "$HARNESS_SRC/info.json" ] || die "no info.json in harness $HARNESS_SRC"
  HARNESS_SRC="$(cd -- "$HARNESS_SRC" && pwd)"
  HARNESS_NAME="$(basename "$HARNESS_SRC")"
  [ "$TICKS_SET" -eq 1 ] || TICKS=3800
fi
case "$TIMEOUT" in ''|*[!0-9]*) die "SMOKE_TIMEOUT wants whole seconds, got '$TIMEOUT'" ;; esac

[ -x "$FACTORIO_BIN" ] || die "factorio binary not executable: $FACTORIO_BIN (set FACTORIO_BIN=...)"
[ -e "$MOD_SRC" ] || die "mod source not found: $MOD_SRC"

READ_DATA="$(cd -- "$(dirname -- "$FACTORIO_BIN")/../data" 2>/dev/null && pwd)" ||
  die "cannot find a data dir next to $FACTORIO_BIN"
[ -d "$READ_DATA/base" ] || die "no base game data under $READ_DATA"

# info.json is parsed HERE on purpose: Factorio skips a mod with malformed metadata
# and still exits 0, and "bad info.json, here is the JSON error" beats "your mod
# never loaded, good luck".
parse_info() {
  python3 -c 'import json, sys
try:
    d = json.load(sys.stdin)
    print(d["name"], d["version"])
except Exception as exc:
    sys.exit(str(exc))'
}

info=''
ZIP_ROOT=''
case "$MOD_SRC" in
  *.zip)
    MOD_KIND=zip
    MOD_SRC="$(cd -- "$(dirname -- "$MOD_SRC")" && pwd)/$(basename -- "$MOD_SRC")"
    # One top-level folder because THIS SCRIPT needs one (info.json and the asset
    # preflight read the unpacked tree), not the engine: MEASURED 2.1.17, Factorio
    # never checks the inner folder name (see tools/build.sh).
    roots="$(unzip -Z1 "$MOD_SRC" | awk -F/ '{print $1}' | sort -u)"
    [ "$(printf '%s\n' "$roots" | grep -c .)" -eq 1 ] ||
      die "zip must hold exactly one top-level folder, found: $(printf '%s' "$roots" | tr '\n' ' ')"
    ZIP_ROOT="$roots"
    info="$(unzip -p "$MOD_SRC" "$ZIP_ROOT/info.json" | parse_info)" ||
      die "bad $ZIP_ROOT/info.json inside $(basename "$MOD_SRC") (name and version required)"
    ;;
  *)
    MOD_KIND=dir
    [ -d "$MOD_SRC" ] || die "not a directory and not a .zip: $MOD_SRC"
    [ -f "$MOD_SRC/info.json" ] || die "no info.json in $MOD_SRC"
    MOD_SRC="$(cd -- "$MOD_SRC" && pwd)"
    info="$(parse_info < "$MOD_SRC/info.json")" ||
      die "bad $MOD_SRC/info.json (name and version required)"
    ;;
esac
MOD_NAME="${info%% *}"
MOD_VER="${info##* }"

# An UNPACKED mod directory must be named <name> or <name>_<version>, case
# sensitive, or Factorio refuses it - a real engine rule, answered here in 5ms
# instead of a log hunt. A zip's INNER folder is only our convention, so the caller
# says whose rule it invokes and gets the matching complaint.
check_folder_name() { # check_folder_name <folder> <what it is> <engine|convention>
  local got="$1" what="$2" whose="${3:-engine}"
  if [ "$got" != "$MOD_NAME" ] && [ "$got" != "${MOD_NAME}_${MOD_VER}" ]; then
    if [ "$whose" = engine ]; then
      die "$what is '$got' but info.json says $MOD_NAME $MOD_VER; Factorio wants '$MOD_NAME' or '${MOD_NAME}_${MOD_VER}' (case sensitive)"
    fi
    die "$what is '$got', not '$MOD_NAME' or '${MOD_NAME}_${MOD_VER}'; the engine does not care what a zip's inner folder is called, but tools/build.sh always ships that name and a zip that disagrees was not built by it"
  fi
}

if [ "$MOD_KIND" = zip ]; then
  # The FILENAME check mirrors the engine (a zip mod's name and version come from
  # the filename, anything else is not found); the inner-folder check is ours.
  check_folder_name "$ZIP_ROOT" "the folder inside the zip" convention
  zip_base="$(basename "$MOD_SRC" .zip)"
  [ "$zip_base" = "${MOD_NAME}_${MOD_VER}" ] ||
    die "zip is named '$zip_base.zip' but Factorio reads the name and version off the filename and wants '${MOD_NAME}_${MOD_VER}.zip'"
else
  check_folder_name "$(basename "$MOD_SRC")" "the mod folder" engine
fi

case "$WORK" in
  ''|/|"$HOME") die "refusing to use '$WORK' as the scratch dir" ;;
esac
case "$MOD_SRC" in
  "$WORK"/*) die "mod source sits inside the scratch dir, which gets wiped: $MOD_SRC" ;;
esac

cleanup() {
  local rc=$?
  if [ "$KEEP" -eq 1 ]; then
    echo "smoke: workdir kept at $WORK"
  else
    rm -rf "$WORK"
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

rm -rf "$WORK"
mkdir -p "$WORK/mods" "$WORK/write"

if [ "$MOD_KIND" = zip ]; then
  cp "$MOD_SRC" "$WORK/mods/${MOD_NAME}_${MOD_VER}.zip"
  mkdir -p "$WORK/unpacked"
  unzip -q "$MOD_SRC" -d "$WORK/unpacked"
  PREFLIGHT_DIR="$WORK/unpacked/$ZIP_ROOT"
else
  ln -s "$MOD_SRC" "$WORK/mods/$MOD_NAME"   # a symlinked mod folder loads fine
  PREFLIGHT_DIR="$MOD_SRC"
fi
[ -z "$HARNESS_NAME" ] || ln -s "$HARNESS_SRC" "$WORK/mods/$HARNESS_NAME"

cat > "$WORK/config.ini" <<EOF
; throwaway profile - never point write-data at the real factorio directory
[path]
read-data=$READ_DATA
write-data=$WORK/write
[general]
locale=en
[other]
check-updates=false
enable-crash-log-uploading=false
EOF

fail=0

# ---- stage 0: asset preflight, because headless cannot see missing images ----
# Literal paths only: a concatenated path slips through, and this proves existence,
# not that the sheet is the size the prototype claims. Both belong to the sprite
# packer (tools/render/pack.py), which emits the numbers.
missing=0
while IFS= read -r ref; do
  [ -n "$ref" ] || continue
  rel="${ref#__"${MOD_NAME}"__/}"
  [ -f "$PREFLIGHT_DIR/$rel" ] || { echo "smoke: MISSING ASSET $ref"; missing=1; }
done < <(grep -rhoE "__${MOD_NAME}__/[A-Za-z0-9_./-]+\.(png|ogg|wav)" "$PREFLIGHT_DIR" \
           --include='*.lua' --include='*.json' 2>/dev/null | sort -u)
if [ "$missing" -ne 0 ]; then
  echo "smoke: FAIL assets - a prototype points at a file that is not in the mod"
  fail=1
fi

# A log line reads "<seconds> <Level> <File.cpp>:<n>: <msg>"; only Error and
# Warning fail. The leading-timestamp anchor keeps it off message bodies and paths
# containing the word. Control-stage errors print with no timestamp, hence the
# alternatives.
ERR_RE='^[[:space:]]*[0-9]+\.[0-9]+ (Error|Warning) |^-+ Error -+$|^Error([: ])|^Failed to load mod'

judge() { # judge <label> <exit status> <logfile>
  local label="$1" rc="$2" log="$3" bad=0 hits
  if [ "$rc" -ne 0 ]; then
    if [ "$rc" -eq 142 ] || [ "$rc" -eq 137 ] || [ "$rc" -eq 124 ]; then
      echo "smoke: FAIL $label - timed out after ${TIMEOUT}s (SMOKE_TIMEOUT)"
    else
      echo "smoke: FAIL $label - factorio exited $rc"
    fi
    bad=1
  fi
  # -A 3 because the matching line is almost never the one that says what broke.
  # MEASURED on 2.1.17: "Error: <mod> errored when running a required file." puts
  # "control.lua:3: unexpected symbol near <eof>" two lines later, and "Error while
  # running event <mod>::on_tick" puts the file:line one line later.
  hits="$(grep -nE -A 3 "$ERR_RE" "$log" || true)"
  if [ -n "$hits" ]; then
    echo "smoke: FAIL $label - error/warning lines in the output:"
    printf '%s\n' "$hits" | sed 's/^/    /'
    bad=1
  fi
  if ! grep -qE "^[[:space:]]*[0-9]+\.[0-9]+ Loading mod $MOD_NAME [0-9]" "$log"; then
    echo "smoke: FAIL $label - '$MOD_NAME' never loaded (a bad info.json silently skips a mod)"
    bad=1
  fi
  if [ "$bad" -eq 0 ]; then
    [ "$VERBOSE" -eq 0 ] || echo "smoke: ok   $label"
  else
    # Control-stage errors reach stdout only, never the log file, so dump the tail
    # of what we captured instead of pointing at a path.
    if [ -z "$hits" ]; then
      echo "smoke:      last 30 lines of $label:"
      tail -n 30 "$log" | sed 's/^/    /'
    fi
    fail=1
  fi
}

write_mod_list() { # write_mod_list <true|false, for the DLC mods>
  # Without this the isolated dir enables everything it discovers, and the DLC ships
  # inside the game's data dir, so the default run is Space Age. The SPEC promises
  # base-only works, so base-only gets tested every time.
  #
  # The harness entry is built OUTSIDE the heredoc. MEASURED (D.7): inside one, bash strips the
  # quotes from a ${VAR:+word} and the word's first `}` closes the expansion, so the entry came
  # out {name:jamaltron-harness,...} with a harness and the list ended `}}]}` without - invalid
  # JSON both ways, which Factorio answers by enabling everything. Every "base only" stage since
  # D.5 had run with Space Age loaded. Hence the parse below, and the base-only stage refusing
  # a log that loaded space-age.
  local dlc="$1" extra=""
  [ -z "$HARNESS_NAME" ] || extra=",
 {\"name\":\"$HARNESS_NAME\",\"enabled\":true}"
  cat > "$WORK/mods/mod-list.json" <<EOF
{"mods":[
 {"name":"base","enabled":true},
 {"name":"elevated-rails","enabled":$dlc},
 {"name":"quality","enabled":$dlc},
 {"name":"recycler","enabled":$dlc},
 {"name":"space-age","enabled":$dlc},
 {"name":"$MOD_NAME","enabled":true}$extra]}
EOF
  python3 -c 'import json, sys; json.load(open(sys.argv[1]))' "$WORK/mods/mod-list.json" ||
    die "wrote an invalid $WORK/mods/mod-list.json - Factorio would ignore it and enable every mod"
}

run_factorio() { # run_factorio <logfile> <args...>
  local log="$1"; shift
  local rc=0
  # macOS has no timeout(1). perl's alarm survives exec, so the game itself takes
  # the SIGALRM and dies with 142: a hang fails instead of blocking the terminal.
  if [ "$TIMEOUT" -gt 0 ]; then
    perl -e 'alarm shift; exec @ARGV or die' -- "$TIMEOUT" \
      "$FACTORIO_BIN" --mod-directory "$WORK/mods" --config "$WORK/config.ini" \
      --no-log-rotation --disable-audio --check-unused-prototype-data "$@" \
      >"$log" 2>&1 || rc=$?
  else
    "$FACTORIO_BIN" --mod-directory "$WORK/mods" --config "$WORK/config.ini" \
      --no-log-rotation --disable-audio --check-unused-prototype-data "$@" \
      >"$log" 2>&1 || rc=$?
  fi
  return "$rc"
}

# ---- stage 1: base only, the cheapest run and the one that catches an
#      accidental Space Age dependency --------------------------------------
write_mod_list false
rc=0
run_factorio "$WORK/create-base.log" --create "$WORK/write/base.zip" || rc=$?
judge "create (base only)" "$rc" "$WORK/create-base.log"
if grep -qE "^[[:space:]]*[0-9]+\.[0-9]+ Loading mod space-age " "$WORK/create-base.log"; then
  echo "smoke: FAIL create (base only) - space-age loaded, so the stage tested nothing base-only"
  fail=1
fi

# ---- stage 2: with Space Age ------------------------------------------------
write_mod_list true
rc=0
run_factorio "$WORK/create-sa.log" --create "$WORK/write/sa.zip" || rc=$?
judge "create (space age)" "$rc" "$WORK/create-sa.log"

# ---- stage 3: ticks, the only way to reach on_load and on_tick --------------
if [ -f "$WORK/write/sa.zip" ]; then
  rc=0
  run_factorio "$WORK/bench-sa.log" \
    --benchmark "$WORK/write/sa.zip" --benchmark-ticks "$TICKS" || rc=$?
  judge "benchmark ${TICKS}t (space age)" "$rc" "$WORK/bench-sa.log"
else
  echo "smoke: FAIL benchmark - no save was created to run"
  fail=1
fi

# ---- the harness's own verdict, off what it logged during the benchmark ----------
if [ -n "$HARNESS_NAME" ] && [ -f "$WORK/bench-sa.log" ]; then
  bench="$WORK/bench-sa.log"
  hfail="$(grep -E 'HARNESS FAIL ' "$bench" || true)"
  if [ -n "$hfail" ]; then
    echo "smoke: FAIL harness:"
    printf '%s\n' "$hfail" | sed 's/^.*HARNESS FAIL /    /'
    fail=1
  fi
  if ! grep -qE 'HARNESS done ' "$bench"; then
    echo "smoke: FAIL harness - never reached 'HARNESS done' (a crash, or --ticks too short)"
    fail=1
  fi
  # Filtered to files ONCE, never `grep -v | grep -q`: under pipefail grep -q's early exit
  # SIGPIPEs upstream once ~64 KB of log follows the match, and the 141 reads as a miss - a
  # false FAIL on need, a false PASS on never (measured, tests/test_smoke.py).
  grep -v 'HARNESS need ' "$bench" > "$WORK/harness-need.log" || true
  grep -v 'HARNESS never ' "$bench" > "$WORK/harness-never.log" || true
  while IFS= read -r pat; do
    grep -qE -- "$pat" "$WORK/harness-need.log" ||
      { echo "smoke: FAIL harness - nothing in the run matched: $pat"; fail=1; }
  done < <(sed -n 's/^.*HARNESS need //p' "$bench")
  while IFS= read -r pat; do
    if grep -qE -- "$pat" "$WORK/harness-never.log"; then
      echo "smoke: FAIL harness - the run matched what it must never: $pat"; fail=1
    fi
  done < <(sed -n 's/^.*HARNESS never //p' "$bench")
  passed="$(grep -cE 'HARNESS ok ' "$bench" || true)"
  [ "$fail" -ne 0 ] || echo "smoke: harness $HARNESS_NAME - $passed checks passed"
fi

if [ "$fail" -ne 0 ]; then
  echo "smoke: FAILED ($MOD_NAME $MOD_VER, $MOD_KIND) - rerun with --keep to inspect the logs"
  exit 1
fi
echo "smoke: PASSED ($MOD_NAME $MOD_VER, $MOD_KIND) - 3 stages, base only + space age + ${TICKS} ticks"
