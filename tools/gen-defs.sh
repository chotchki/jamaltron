#!/usr/bin/env bash
# Regenerate the FMTK LuaLS type-def bundle for the Factorio API into .ls-defs/factorio/.
#
# 1156 files and 7 MB of generated Lua, so it is gitignored - which means a fresh
# clone has NO defs and .luarc.json points at two paths that do not exist. Run this
# once after cloning, and again after a game update. tools/lint.sh refuses to run
# the type gate until you have.
#
# Two sources, same bytes. This install ships runtime-api.json + prototype-api.json
# under /Applications/factorio.app/Contents/doc-html (2.1.17), and
# `fmtk luals-addon -o <version>` pulls the same two files from
# lua-api.factorio.com - MEASURED 2026-09-19: byte-identical output. Local docs win
# when they are there, because docs shipped by the binary cannot drift from the game
# you actually launch; online is the fallback for a machine with no game installed,
# which is the CI path.
#
# The tree is REPLACED, never merged. fmtk only ever adds files, so a type renamed
# upstream would otherwise leave its stale def behind forever, and the stale one
# still type-checks. Generation happens in a temp dir and swaps in only after fmtk
# succeeds, so a failed or offline run leaves the working tree exactly as it was.
# .ls-defs/supplement/ is hand-written source (it declares the globals fmtk omits);
# this script never writes or deletes it, it only counts the files to say so.
#
# Usage: tools/gen-defs.sh [--online] [--api-version VERSION] [--docs-dir DIR]
#                          [--out DIR] [--check] [-q]
# Env:   FACTORIO_DOC_HTML=DIR   where runtime-api.json + prototype-api.json live
#        FACTORIO_BIN=PATH       game binary; doc-html is found next to it
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

OUT="$REPO_ROOT/.ls-defs/factorio"
SUPPLEMENT="$REPO_ROOT/.ls-defs/supplement"
DOCS_DIR="${FACTORIO_DOC_HTML:-}"
FACTORIO_BIN="${FACTORIO_BIN:-${FACTORIO:-/Applications/factorio.app/Contents/MacOS/factorio}}"
API_VERSION=''
FORCE_ONLINE=0
CHECK_ONLY=0
QUIET=0

usage() { sed -n '2,27p' "${BASH_SOURCE[0]}"; }
die() { echo "defs: $*" >&2; exit 2; }
say() { [ "$QUIET" -eq 1 ] || echo "defs: $*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --online)      FORCE_ONLINE=1; shift ;;
    --api-version) [ $# -ge 2 ] || die "--api-version needs a version (e.g. 2.1.17 or latest)"; API_VERSION="$2"; shift 2 ;;
    --docs-dir)    [ $# -ge 2 ] || die "--docs-dir needs a directory"; DOCS_DIR="$2"; shift 2 ;;
    --out)         [ $# -ge 2 ] || die "--out needs a directory"; OUT="$2"; shift 2 ;;
    --check)       CHECK_ONLY=1; shift ;;
    -q|--quiet)    QUIET=1; shift ;;
    -h|--help)     usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

command -v fmtk >/dev/null 2>&1 ||
  die "fmtk not on PATH - install it with: npm install -g factoriomod-debug"

# --out ends up on the wrong end of an rm -rf, so resolve it to an absolute path
# BEFORE the refusal list below gets a look at it. `--out .` from $HOME is the case
# that matters: relative, harmless-looking, and $HOME once resolved.
if [ -d "$OUT" ]; then
  OUT="$(cd -- "$OUT" && pwd)"
else
  out_parent="$(cd -- "$(dirname -- "$OUT")" 2>/dev/null && pwd)" ||
    die "--out has no existing parent directory: $OUT"
  OUT="${out_parent%/}/$(basename -- "$OUT")"
fi

# Refuse an --out that is not ours to delete, before generating anything. A
# previously generated bundle is recognised by its own config.json; anything else
# (an empty dir, or someone aiming this at .ls-defs/supplement) stops here with the
# tree untouched. --check deletes nothing, so it skips the whole question.
if [ "$CHECK_ONLY" -eq 0 ]; then
  case "$OUT" in
    ''|/|"$HOME"|"$REPO_ROOT") die "refusing to replace '$OUT'" ;;
  esac
  [ "$OUT" != "$SUPPLEMENT" ] ||
    die "refusing to replace $SUPPLEMENT - that is hand-written source, not generated"
  if [ -e "$OUT" ]; then
    [ -d "$OUT" ] || die "$OUT exists and is not a directory"
    if [ -n "$(ls -A "$OUT")" ]; then
      grep -q '"name"[[:space:]]*:[[:space:]]*"Factorio"' "$OUT/config.json" 2>/dev/null ||
        die "$OUT is not empty and does not look like an fmtk bundle - refusing to delete it"
    fi
  fi
fi

# --- where the API json comes from -------------------------------------------
# doc-html sits beside the binary in the app bundle: MacOS/factorio -> ../doc-html.
if [ -z "$DOCS_DIR" ] && [ -x "$FACTORIO_BIN" ]; then
  DOCS_DIR="$(cd -- "$(dirname -- "$FACTORIO_BIN")/../doc-html" 2>/dev/null && pwd)" || DOCS_DIR=''
fi
RUNTIME_JSON="${DOCS_DIR:+$DOCS_DIR/runtime-api.json}"
PROTO_JSON="${DOCS_DIR:+$DOCS_DIR/prototype-api.json}"
HAVE_LOCAL=0
if [ -n "$DOCS_DIR" ] && [ -f "$RUNTIME_JSON" ] && [ -f "$PROTO_JSON" ]; then
  HAVE_LOCAL=1
fi

# Both json files carry the version that produced them; that is the pin used for an
# online fetch too, so --online off this machine reproduces these exact bytes.
json_field() { # json_field <file> <key>
  python3 -c 'import json, sys
try:
    print(json.load(open(sys.argv[1]))[sys.argv[2]])
except Exception as exc:
    sys.exit(str(exc))' "$1" "$2"
}

if [ "$HAVE_LOCAL" -eq 1 ]; then
  LOCAL_VERSION="$(json_field "$RUNTIME_JSON" application_version)" ||
    die "cannot read application_version from $RUNTIME_JSON"
  PROTO_VERSION="$(json_field "$PROTO_JSON" application_version)" ||
    die "cannot read application_version from $PROTO_JSON"
  [ "$LOCAL_VERSION" = "$PROTO_VERSION" ] ||
    die "doc-html is inconsistent: runtime-api.json is $LOCAL_VERSION, prototype-api.json is $PROTO_VERSION"
fi

if [ "$HAVE_LOCAL" -eq 1 ] && [ "$FORCE_ONLINE" -eq 0 ]; then
  SOURCE="local docs $DOCS_DIR ($LOCAL_VERSION)"
  set -- -d "$RUNTIME_JSON" -p "$PROTO_JSON"
else
  # No version anywhere means "latest", which is honest but unpinned - so say which
  # one got used rather than letting a silent upgrade land in the defs.
  [ -n "$API_VERSION" ] || API_VERSION="${LOCAL_VERSION:-latest}"
  if [ "$HAVE_LOCAL" -eq 0 ] && [ "$FORCE_ONLINE" -eq 0 ]; then
    say "no local docs (looked in ${DOCS_DIR:-/Applications/factorio.app/Contents/doc-html}), falling back to online"
  fi
  # MEASURED 2026-09-19: lua-api.factorio.com serves /latest/, /stable/ and full
  # versions like /2.1.17/. There is no /2.1/ alias, so info.json's factorio_version
  # cannot be the pin - unpinned 'latest' is the only no-install default, and it says
  # so out loud rather than quietly generating defs for whatever shipped this week.
  [ "$API_VERSION" != latest ] ||
    echo "defs: WARNING - pulling 'latest', not pinned (pass --api-version 2.1.17 to pin)" >&2
  SOURCE="lua-api.factorio.com ($API_VERSION)"
  set -- -o "$API_VERSION"
fi

# --- generate into a temp dir -------------------------------------------------
# fmtk hardcodes a factorio/ prefix under the outdir it is given, so generate into
# TMP and move TMP/factorio into place; --out then means what it says.
TMPWORK="$(mktemp -d "${TMPDIR:-/tmp}/jamaltron-defs.XXXXXX")"
cleanup() { local rc=$?; rm -rf "$TMPWORK"; exit "$rc"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

say "generating from $SOURCE"
fmtk luals-addon "$@" "$TMPWORK/gen" ||
  die "fmtk luals-addon failed (online mode needs network; local mode needs both json files)"

NEW="$TMPWORK/gen/factorio"
[ -d "$NEW/library" ] && [ -f "$NEW/plugin.lua" ] && [ -f "$NEW/config.json" ] ||
  die "fmtk produced an unexpected layout under $NEW - .luarc.json wants library/ and plugin.lua"

stamp="$(python3 -c 'import json, sys
d = json.load(open(sys.argv[1]))
print(d.get("factorioVersion", "?"), d.get("bundleVersion", "?"))' "$NEW/config.json")" ||
  die "fmtk wrote a config.json we cannot parse: $NEW/config.json"
GOT_VERSION="${stamp%% *}"
BUNDLE_VERSION="${stamp##* }"

# --- check mode: prove the committed-state tree is the tree fmtk emits ---------
if [ "$CHECK_ONLY" -eq 1 ]; then
  [ -d "$OUT" ] || die "nothing to check: $OUT does not exist (run tools/gen-defs.sh)"
  if diff -r -q "$NEW" "$OUT" >"$TMPWORK/drift" 2>&1; then
    say "up to date: $OUT matches $SOURCE (factorio $GOT_VERSION, fmtk bundle $BUNDLE_VERSION)"
    exit 0
  fi
  echo "defs: DRIFT - $OUT is not what $SOURCE generates:" >&2
  sed 's/^/    /' "$TMPWORK/drift" >&2
  exit 1
fi

# --- swap it in ---------------------------------------------------------------
mkdir -p "$(dirname -- "$OUT")"
rm -rf "$OUT"
mv "$NEW" "$OUT"

FILES="$(find "$OUT" -type f | wc -l | tr -d ' ')"
SIZE="$(du -sh "$OUT" | awk '{print $1}')"
say "wrote $OUT: $FILES files, $SIZE, factorio $GOT_VERSION, fmtk bundle $BUNDLE_VERSION"
say "  library/ + plugin.lua are the two paths .luarc.json names"

# The mod says which API it targets; defs from a different major/minor type-check
# clean and still lie. Worth a warning, not a refusal - checking 2.1 code against a
# newer bundle on purpose is a legitimate thing to do.
INFO="$REPO_ROOT/mod/jamaltron/info.json"
if [ -f "$INFO" ]; then
  WANT="$(json_field "$INFO" factorio_version 2>/dev/null || true)"
  case "${WANT:-}" in
    ''|"${GOT_VERSION%.*}") ;;
    *) echo "defs: WARNING - info.json targets Factorio $WANT but these defs are $GOT_VERSION" >&2 ;;
  esac
fi

if [ -d "$SUPPLEMENT" ]; then
  say "untouched: $SUPPLEMENT ($(find "$SUPPLEMENT" -type f | wc -l | tr -d ' ') hand-written file(s))"
else
  echo "defs: WARNING - $SUPPLEMENT is missing; the globals fmtk omits are now undefined" >&2
fi
