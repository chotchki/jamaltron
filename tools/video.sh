#!/usr/bin/env bash
# Films a take of the gameplay video out of the REAL renderer, no hands (PLAN G.4): a headless
# dry run of the director first, then the same take under `factorio --benchmark-graphics` with
# one stamped jpg a tick, then EVERY frame's stamp decoded before anything downstream may read it.
#
# THE DIRECTOR is tools/harness/jamaltron-video (G.2 the set, G.3 the beats): copied into the
# profile beside the take.lua this script writes, jamaltron SYMLINKED from the working tree, so a
# mod edit shows on the next take. It stages everything through the mod's own code and writes
# events.jsonl + track.jsonl (the builders' interface) beside the frames.
#
# THE FIXTURE is built once by `--create` with a PINNED seed (SEED below) and no enemy bases, and
# loaded every run after; the set is rebuilt from the director's table on every load, so only a
# change to the map itself needs --fresh. MEASURED (G.1): the same save gives byte-identical takes
# in one mode, but headless and graphics drift by up to a 60-tick poll - the dry run proves the
# beat machine finishes and sizes the graphics run, the TAKE's own logs are what the cut and the
# sound sync to.
#
# THE DRY RUN (headless, 3-4 s MEASURED) must reach the `wrap` beat with no VIDEO FAIL; its
# capture_end sets the graphics run's --benchmark-ticks (plus a margin for the drift: a request
# on the last benchmark tick is never written, MEASURED G.1). The graphics take runs in real
# time (60 UPS is the ceiling under --benchmark-graphics, MEASURED G.1), under caffeinate so the
# Mac does not sleep a minute into it, with the game's audio off.
#
# THE VERIFY: frames == track.jsonl lines == captured ticks, and tools/video/stamp.py reads the
# tick back off every frame - 0 mismatches, 0 duplicates, 0 gaps, or the take FAILS (a file count
# proves nothing: at game speed 4 all 361 files of a G.1 spike landed and 67 showed the wrong
# tick). A failed take stays on disk with its verify.json, for looking at.
#
# Isolated like shot.sh: own config.ini, write-data and mod dir under .videotest/ (gitignored,
# never your real profile). Like play.sh, a profile dir must be empty or carry this script's
# marker file, so a mistyped VIDEO_DIR can never overwrite .playtest's config, the mod source or
# the director itself; inside the repo it must be a top-level .videotest* dir (the gitignored
# ones). Frames are MOVED out of the profile into the take dir (render-out/, gitignored; ~0.85
# MB a frame at q90, ~3.1 GB a main take - MEASURED G.4 on grass + live water).
#
# Usage: tools/video.sh [--take main|loop] [--dry-run | --skip-dry] [--fresh] [--out DIR]
#                       [--quality Q]
#   --take      which take (default main): main is the storyboard, loop the creek hop for the
#               README GIF and the portal loop
#   --dry-run   the headless run only: prove every beat plays, print the beats, film nothing
#   --skip-dry  straight to the graphics take, sized off the LAST dry run of this take (there
#               must be one; a changed director wants a new one)
#   --fresh     rebuild the fixture save (the seed is pinned, so it comes back the same)
#   --out       the take dir (default render-out/video/takes/<take>-<stamp>/); must not exist,
#               and inside the repo must be under render-out/ (a 3 GB take anywhere else is
#               one `git add -A` - or, under mod/, one build.sh - from shipping)
#   --quality   jpg quality 1-100 (default 90: ~0.85 MB a 1080p frame of grass + live water,
#               MEASURED G.4; G.1's 0.50 was a plainer scene)
# Env:   FACTORIO_BIN=/path/to/factorio   binary override (FACTORIO also accepted)
#        VIDEO_DIR=PATH                   profile location override (a second profile for a
#                                         take running alongside another: .videotest2/ in the
#                                         repo, or anywhere outside it)
#
# Every argument is checked before anything is created or launched; tools/tests/test_video_sh.py
# runs them all without Factorio.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FACTORIO_BIN="${FACTORIO_BIN:-${FACTORIO:-/Applications/factorio.app/Contents/MacOS/factorio}}"
DIR="${VIDEO_DIR:-$REPO_ROOT/.videotest}"
MOD_SRC="$REPO_ROOT/mod/jamaltron"
DIRECTOR_SRC="$SCRIPT_DIR/harness/jamaltron-video"
MARKER=".jamaltron-videotest"          # only a directory carrying this is ours to write into

# The map's seed, pinned: the fixture (and every map-rng roll the take makes) is the same on any
# machine that builds it. Picked once, 2026-09-27; changing it re-rolls every line and leg layout.
SEED=20260927
# The frame: 1920x1080 kept + a 24-px stamp band the pump crops (tools/README.md, Video).
RES_W=1920
RES_H=1104
BAND=24
# Headless ticks for the dry run: the director FAILS a take that has not wrapped by staging +
# 9000 (story.lua's T.limit), so this always sees the verdict.
DRY_TICKS=9300

TAKE=main
DRY_ONLY=0
SKIP_DRY=0
FRESH=0
OUT=""
QUALITY=90

# The header above, up to the first line that is not a comment.
usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"; }
die() { echo "video: $*" >&2; exit 2; }
# `--flag VALUE`: a missing or empty VALUE is a usage error, not bash's "2: parameter null".
val() { [ -n "${2:-}" ] || die "$1 wants a value (try --help)"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --take)      val "$@"; TAKE="$2"; shift 2 ;;
    --dry-run)   DRY_ONLY=1; shift ;;
    --skip-dry)  SKIP_DRY=1; shift ;;
    --fresh)     FRESH=1; shift ;;
    --out)       val "$@"; OUT="$2"; shift 2 ;;
    --quality)   val "$@"; QUALITY="$2"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

# Everything below lands in take.lua as Lua source, so nothing reaches it unvalidated.
case "$TAKE" in main|loop) ;; *) die "--take is main or loop, got '$TAKE'" ;; esac
[[ "$QUALITY" =~ ^[1-9][0-9]*$ ]] && [ "$QUALITY" -le 100 ] ||
  die "--quality wants a whole number 1-100, got '$QUALITY'"
[ "$DRY_ONLY" -eq 0 ] || [ "$SKIP_DRY" -eq 0 ] || die "--dry-run and --skip-dry are opposites"
[ "$DRY_ONLY" -eq 0 ] || [ -z "$OUT" ] || die "--out is where a graphics take lands; --dry-run films nothing"
# Path rules, judged in Python on RESOLVED paths (trailing slash, `..`, symlink), case-folded
# (APFS is case-insensitive, so .../Factorio IS the real profile) and by inode where both ends
# exist - shot.sh's rule. `inside A B`: is A B or under it.
PATHS_PY='
import os, sys
def same(a, b):
    if a.casefold() == b.casefold():
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False
def inside(a, b):
    p = a
    while True:
        if same(p, b):
            return True
        if p == os.path.dirname(p):
            return False
        p = os.path.dirname(p)
'
if [ -n "$OUT" ]; then
  OUT="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$OUT")"
  [ ! -e "$OUT" ] || die "--out $OUT already exists (a take never overwrites another)"
  why="$(python3 -c "$PATHS_PY"'
out, repo = (os.path.realpath(p) for p in sys.argv[1:])
if inside(out, repo) and not inside(out, os.path.join(repo, "render-out")):
    print(f"--out {out} is inside the repo but not under render-out/ (gitignored): a take there "
          "is one `git add -A` from history, and under mod/ one build.sh from the portal zip")
' "$OUT" "$REPO_ROOT")"
  [ -z "$why" ] || die "$why"
fi

# The profile gets files written and mods/jamaltron-video + write/script-output deleted, so it
# is never /, home, the repo or anywhere in the real profile; inside the repo it is a top-level
# .videotest* dir (gitignored) and nothing else - mod/jamaltron, the director or .playtest would
# all be overwritten (MEASURED by the review, on copies). Judged BEFORE anything is created (a
# refused path is left as it was).
DIR="$(python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$DIR")"
why="$(python3 -c "$PATHS_PY"'
d, home, repo, profile = (os.path.realpath(p) for p in sys.argv[1:])
if any(same(d, bad) for bad in ("/", home, repo)):
    print(f"refusing to use {d!r} as the video profile (VIDEO_DIR wants a dir of its own)")
elif inside(d, profile):
    print(f"refusing {d!r}: it is inside your real Factorio profile")
elif inside(d, repo) and not (same(os.path.dirname(d), repo)
                              and os.path.basename(d).casefold().startswith(".videotest")):
    print(f"refusing {d!r}: inside the repo a video profile is a top-level .videotest* dir "
          "(gitignored); put it there or outside the repo")
' "$DIR" "$HOME" "$REPO_ROOT" "$HOME/Library/Application Support/factorio")"
[ -z "$why" ] || die "$why"
# play.sh's rule: a non-empty dir without our marker was not made by this script.
if [ -d "$DIR" ] && [ -n "$(ls -A -- "$DIR")" ] && [ ! -f "$DIR/$MARKER" ]; then
  die "$DIR is not empty and was not made by this script (no $MARKER);" \
      "point VIDEO_DIR somewhere else"
fi

DRY_KEEP="$DIR/dry/$TAKE"
if [ "$SKIP_DRY" -eq 1 ] && [ ! -f "$DRY_KEEP/events.jsonl" ]; then
  die "--skip-dry sizes the take off the last dry run of '$TAKE', and there is none in $DRY_KEEP (run once without it)"
fi

[ -x "$FACTORIO_BIN" ] || die "factorio binary not executable: $FACTORIO_BIN (set FACTORIO_BIN=...)"
READ_DATA="$(cd -- "$(dirname -- "$FACTORIO_BIN")/../data" 2>/dev/null && pwd)" ||
  die "cannot find a data dir next to $FACTORIO_BIN"
[ -f "$DIRECTOR_SRC/control.lua" ] || die "no director at $DIRECTOR_SRC"
mkdir -p "$DIR/write" "$DIR/mods"
touch "$DIR/$MARKER"

cat > "$DIR/config.ini" <<EOF
; tools/video.sh's throwaway profile - never point write-data at the real one
[path]
read-data=$READ_DATA
write-data=$DIR/write
[general]
locale=en
[other]
check-updates=false
enable-crash-log-uploading=false
EOF

# No enemy bases, no cliffs: the pad is dressed on load, but the wide wave shot sees past it.
cat > "$DIR/map-gen-settings.json" <<EOF
{"autoplace_controls": {"enemy-base": {"frequency": 0, "size": 0, "richness": 0}},
 "cliff_settings": {"richness": 0}}
EOF

ln -sfn "$MOD_SRC" "$DIR/mods/jamaltron"
rm -rf "$DIR/mods/jamaltron-video"
cp -R "$DIRECTOR_SRC" "$DIR/mods/jamaltron-video"
cat > "$DIR/mods/mod-list.json" <<EOF
{"mods":[
 {"name":"base","enabled":true},
 {"name":"elevated-rails","enabled":true},
 {"name":"quality","enabled":true},
 {"name":"recycler","enabled":true},
 {"name":"space-age","enabled":true},
 {"name":"jamaltron","enabled":true},
 {"name":"jamaltron-video","enabled":true}]}
EOF

# take.lua, from values validated above. A Lua syntax error in it SIGSEGVs the game on load
# (MEASURED G.1) instead of reporting, so it is syntax-checked here when a luac is around - a
# 5.4/5.5 luac, not Factorio's 5.2, but the file is a table of literals either dialect reads.
write_take() { # write_take CAPTURE STILLS
  local take_lua="$DIR/mods/jamaltron-video/take.lua"
  cat > "$take_lua" <<EOF
-- written by tools/video.sh
return {take = "$TAKE", capture = $1, resolution = {$RES_W, $RES_H}, band = $BAND,
        quality = $QUALITY, dir = "video/$TAKE", stills = $2}
EOF
  if command -v luac >/dev/null 2>&1; then
    luac -p "$take_lua" || die "take.lua does not parse: $take_lua"
  fi
}

ARGS=(--config "$DIR/config.ini" --mod-directory "$DIR/mods" --disable-audio)
FIXTURE="$DIR/fixture.zip"
SRC="$DIR/write/script-output/video/$TAKE"

# judge LOG RC WHAT: fail the run on a non-zero exit, an engine Error or a VIDEO FAIL line.
judge() {
  if [ "$2" -ne 0 ] || grep -qE ' Error |VIDEO FAIL' "$1"; then
    grep -nE -A3 ' Error |VIDEO FAIL' "$1" | head -30 >&2 || true
    die "$3 failed (exit $2): $1"
  fi
}

# capture_end off an events.jsonl, or nothing.
capture_end() {
  python3 -c '
import json, sys
for line in open(sys.argv[1]):
    e = json.loads(line)
    if e.get("ev") == "capture_end":
        print(e["tick"])
' "$1"
}

# The beats and their ticks from capture_start, one line.
beats() {
  python3 -c '
import json, sys
evs = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
start = next((e["tick"] for e in evs if e["ev"] == "capture_start"), 0)
print("  ".join("%s %d" % (e["name"], e["tick"] - start) for e in evs if e["ev"] == "beat"))
' "$1"
}

write_take false false
if [ "$FRESH" -eq 1 ] || [ ! -f "$FIXTURE" ]; then
  echo "video: building the fixture save (seed $SEED)"
  rm -f "$FIXTURE"
  rc=0
  "$FACTORIO_BIN" "${ARGS[@]}" --create "$FIXTURE" --map-gen-seed "$SEED" \
    --map-gen-settings "$DIR/map-gen-settings.json" >"$DIR/create.log" 2>&1 || rc=$?
  judge "$DIR/create.log" "$rc" "fixture build"
  [ -f "$FIXTURE" ] && grep -q "VIDEO fixture built" "$DIR/create.log" ||
    die "fixture build failed (no save, or the director's on_init never ran): $DIR/create.log"
fi

if [ "$SKIP_DRY" -eq 0 ]; then
  echo "video: dry run ($TAKE, headless)"
  rm -rf "$SRC"
  rc=0
  t0=$SECONDS
  "$FACTORIO_BIN" "${ARGS[@]}" --benchmark "$FIXTURE" --benchmark-ticks "$DRY_TICKS" \
    >"$DIR/dry.log" 2>&1 || rc=$?
  judge "$DIR/dry.log" "$rc" "dry run"
  grep -q "VIDEO wrap" "$DIR/dry.log" && [ -f "$SRC/events.jsonl" ] ||
    die "dry run never reached the wrap beat: $DIR/dry.log"
  rm -rf "$DRY_KEEP"
  mkdir -p "$DRY_KEEP"
  cp "$SRC/events.jsonl" "$SRC/track.jsonl" "$DRY_KEEP/"
  cp "$DIR/dry.log" "$DRY_KEEP/dry.log"
  echo "video: dry run ok in $((SECONDS - t0)) s: $(beats "$DRY_KEEP/events.jsonl")"
fi
LAST="$(capture_end "$DRY_KEEP/events.jsonl")"
[[ "$LAST" =~ ^[0-9]+$ ]] || die "no capture_end in $DRY_KEEP/events.jsonl"
if [ "$DRY_ONLY" -eq 1 ]; then
  echo "video: dry run only; logs in ${DRY_KEEP#"$REPO_ROOT"/}"
  exit 0
fi

# The graphics run drifts from the dry run by up to a poll (60 ticks, MEASURED G.1) and a repair
# can land a poll either side: 300 ticks + 10% of the take covers it, and the last capture tick
# must be >= 10 before the end or its screenshot is never written.
TICKS=$((LAST + 300 + LAST / 10))
write_take true true
rm -rf "$SRC"
LOG="$DIR/run.log"
CAFF=()
if command -v caffeinate >/dev/null 2>&1; then CAFF=(caffeinate -di); fi
echo "video: filming $TAKE (${TICKS} ticks, ~$((TICKS / 60 + 20)) s with startup)"
rc=0
t0=$SECONDS
${CAFF[@]+"${CAFF[@]}"} "$FACTORIO_BIN" "${ARGS[@]}" --benchmark-graphics "$FIXTURE" \
  --benchmark-ticks "$TICKS" >"$LOG" 2>&1 || rc=$?
WALL=$((SECONDS - t0))
judge "$LOG" "$rc" "graphics take"
grep -q "VIDEO wrap" "$LOG" || die "the take never reached the wrap beat: $LOG"
[ -f "$SRC/events.jsonl" ] && [ -d "$SRC/frames" ] || die "the take wrote no frames or events: $SRC"
END="$(capture_end "$SRC/events.jsonl")"
[[ "$END" =~ ^[0-9]+$ ]] && [ "$END" -le $((TICKS - 10)) ] ||
  die "capture_end ${END:-missing} is not >= 10 ticks before the run's end ($TICKS): $LOG"

[ -n "$OUT" ] || OUT="$REPO_ROOT/render-out/video/takes/$TAKE-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
mv "$SRC/frames" "$OUT/frames"
[ ! -d "$SRC/stills" ] || mv "$SRC/stills" "$OUT/stills"
cp "$SRC/events.jsonl" "$SRC/track.jsonl" "$OUT/"
cp "$LOG" "$OUT/run.log"
cp "$DIR/mods/jamaltron-video/take.lua" "$OUT/take.lua"
[ ! -f "$DRY_KEEP/dry.log" ] || cp "$DRY_KEEP/dry.log" "$OUT/dry-run.log"

echo "video: verifying every frame's stamp"
rc=0
uv run --directory "$REPO_ROOT/tools" python -m video.stamp verify "$OUT" || rc=$?
[ "$rc" -eq 0 ] || die "the take FAILED verification (see $OUT/verify.json); it stays on disk for looking at"

python3 - "$OUT" "$WALL" "$REPO_ROOT/tools" "$TAKE" <<'EOF'
import json, os, pathlib, re, sys
out, wall = pathlib.Path(sys.argv[1]), int(sys.argv[2])
tools, take = sys.argv[3], sys.argv[4]
evs = [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines() if l.strip()]
start = next(e["tick"] for e in evs if e["ev"] == "capture_start")
end = next(e["tick"] for e in evs if e["ev"] == "capture_end")
beats = [e for e in evs if e["ev"] == "beat"]
print("video: beats (tick from capture_start):")
for b, nxt in zip(beats, beats[1:] + [None]):
    until = (nxt["tick"] if nxt else end) - b["tick"]
    print(f"  {b['name']:<10} {b['tick'] - start:>6}  ({until} ticks)")
# Wall-clock UPS over the capture window, off the log's own timestamps.
stamps = {}
for line in (out / "run.log").read_text(errors="replace").splitlines():
    m = re.match(r"\s*(\d+\.\d+) .*VIDEO (capture_start|capture_end) at (\d+)", line)
    if m:
        stamps[m[2]] = float(m[1])
ups = ""
if len(stamps) == 2 and stamps["capture_end"] > stamps["capture_start"]:
    ups = f", {(end - start) / (stamps['capture_end'] - stamps['capture_start']):.1f} UPS while filming"
v = json.loads((out / "verify.json").read_text())
print(f"video: {v['frames']} frames, {v['bytes'] / v['frames'] / 1e6:.2f} MB/frame, "
      f"{v['bytes'] / 1e9:.2f} GB; {wall} s wall{ups}")
print(f"video: take -> {out}")
print(f"video: next  uv run --directory tools python -m video.build --take "
      f"{os.path.relpath(out, tools)} --cut video/{take}.toml")
EOF
