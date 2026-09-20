#!/usr/bin/env python3
"""Sliders for the five knobs you actually tune by eye. Local page, no dependency.

    uv run --directory tools python render/tune.py            # opens a browser
    uv run --directory tools python render/tune.py --set model.girth=1.3

WHY THIS EXISTS. `art.py --compare` is the right tool for "is this value correct" and the
wrong one for "which value is correct" -- three round trips of render / open the PNG /
describe what is wrong burns ten minutes to move one number by 0.1. This drives the SAME
harness (ac.load -> ac.resolve -> art.render_pass -> art.compare_sheet), so a value found
here is the same value there: same cache, same sheet, same coverage count, same hash.

MEASURED ON THIS MACHINE, and the numbers picked the defaults:

  * 8 body frames, EEVEE Next, 16 samples, 384 px, 4 jobs: 1.5 s render, 1.7 s wall.
  * 4 body frames, same: 1.8-2.3 s. NOT FASTER. The slider loop is Blender LAUNCH-bound,
    not pixel-bound -- four processes cost the same second to start whether they render one
    frame each or two. So `rotations` defaults to 8 (more picture for the same second) and
    the 4 option is there for when you have made him big enough that pixels start to matter.
  * 8 jobs: 21.3 s, a 14x REGRESSION. Eight simultaneous Blenders thrash the Metal context.
    Do not raise --jobs above 4 on this machine looking for speed; you will find the
    opposite, and the tool will feel broken rather than slow.
  * the shadow pass is Cycles and costs 12-15 s. That is the entire reason --compare feels
    slow, so it is OFF here and behind a toggle that says so.

TWO HASHES, ON PURPOSE. The tuner renders with shadow off (and possibly 4 rotations, and
possibly a reduced resolution), and all three of those are knobs, so the hash of what you
are LOOKING AT is not the hash you get after pasting the TOML and running `art.py
--compare`. The page shows both: `tuner` is provenance for the image on screen, `paste` is
what the CLI will stamp once the five model knobs are committed. A tool that showed one
hash would be lying about one of them.

ONE CAVEAT ON `paste`, inherited from artconfig and not fixable here: `model.blend` is in
the config, so it is in the hash, so the paste hash is only reproducible under the SAME
$JAMALTRON_BLEND. MEASURED: one config, 6fa699a20345 with the env var unset and
adce61e09b13 with it set. Same shark either way -- the path is in the key, not the pixels.
Your own shell is consistent, so the round trip holds; a hash mailed to someone else does
not. art.py has always had this, the tuner just promises a hash out loud.

THROWAWAY BUT NOT DISPOSABLE: C.5 needs the same loop for the flop poses, so the slider
list is data (KNOBS) and not markup. Add a row, and the TOML export, the reset button and
the round-trip all pick it up -- TOML_KEYS asserts at import that a new slider cannot
silently fall out of the export.
"""

# sys.path, verbatim per tools/README.md -- Python and Blender both put THIS file's own
# directory on sys.path[0], never tools/, and `package = false` means there is no installed
# `render` to fall back on. Cannot be factored into a helper: importing the helper is the
# thing that needs the path fixed.
import pathlib, sys  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse  # noqa: E402
import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import re  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
import webbrowser  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from functools import partial  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

from render import art  # noqa: E402
from render import artconfig as ac  # noqa: E402
from render import sheets  # noqa: E402


@dataclass(frozen=True)
class Knob:
    """One slider. `key`/`index` address the real knob -- no parallel config format."""

    id: str
    key: str
    index: int | None
    lo: float
    hi: float
    step: float
    label: str
    unit: str
    lo_label: str
    hi_label: str
    hint: str


#: The five knobs you tune by eye, in the order they matter. Ranges bracket the shipped
#: values wide enough to find the answer and narrow enough that a drag is not a lottery.
KNOBS = [
    Knob("pivot_x", "model.pivot", 0, -2.0, 0.5, 0.02,
         "rotation axis, fore/aft", "BU", "&larr; TAIL", "NOSE &rarr;",
         "The point the 64 frames spin about, in model units along the body. MORE NEGATIVE "
         "moves the axis BACK toward the tail; LESS NEGATIVE moves it FORWARD toward the "
         "nose. Wrong and he orbits the cell instead of spinning in place: watch the nose "
         "across N / E / S / W, not one frame."),
    Knob("offset_z", "model.offset", 2, 0.0, 1.6, 0.01,
         "height above ground", "tiles", "&darr; sunk", "floating &uarr;",
         "World height, before the 45-degree camera turns it into 0.707x that much "
         "up-screen lift. 0.85 is the measured match to stock's own torso shift. Too high "
         "and he floats off his legs, too low and the legs grow out of his back."),
    Knob("girth", "model.girth", None, 1.0, 2.0, 0.05,
         "girth (width only)", "x", "as sculpted", "chonk &rarr;",
         "Width multiplier, length and height untouched. The canon way to make him bigger "
         "-- the books call him overweight, never longer -- and the cheapest way to cover "
         "the leg mounts at &plusmn;0.78 tiles transverse."),
    Knob("scale", "model.scale", None, 0.5, 1.2, 0.01,
         "overall scale", "x", "&larr; smaller", "bigger &rarr;",
         "Uniform. Watch the canvas warning: the 6-tile body canvas starts CUTTING him "
         "around 1.1, and a clipped frame reads as a flat-topped shark, not as an error."),
    Knob("pitch", "model.rotation", 1, -20.0, 20.0, 0.5,
         "pitch (nose up/down)", "deg", "nose down", "nose up",
         "A few degrees of nose-up reads as swimming rather than dead-fish-on-a-stick. "
         "C.5's jump arc wants a lot more."),
]

#: Keys the TOML export writes. Every KNOBS entry must land in one of these or the export
#: would quietly drop a value you spent an afternoon finding -- asserted at import, not
#: documented and hoped for.
TOML_KEYS = ("model.pivot", "model.scale", "model.girth", "model.offset", "model.rotation")
assert {k.key for k in KNOBS} <= set(TOML_KEYS), "a slider is missing from TOML_KEYS"

#: Render options the page can set. All three are real knobs, which is why they move the
#: tuner hash: rotations -> compare.rotations, res -> render.resolution_px (0 = native
#: 384 px), shadow -> compare.show_shadow plus whether the Cycles pass runs at all.
ROTATION_CHOICES = (4, 8)
RES_CHOICES = (0, 256)
DEFAULT_OPTS = {"rotations": 8, "res": 0, "shadow": False}

#: The model's own rest-pose box in tiles at scale 1, read OUT of artconfig.derived()
#: rather than copied from it, so the page's live dimensions cannot drift from the
#: harness's. Same trick for the mount spread: it comes from sheets.LEG_MOUNTS.
_PROBE = ac.derived(ac.resolve({"model": {"scale": 1.0, "girth": 1.0}}, env={}))
MODEL_BU = [_PROBE["shark_length_tiles"], _PROBE["shark_width_tiles"],
            _PROBE["shark_height_tiles"]]
MOUNT_HALF_WIDTH = max(abs(mount[0]) for mount, _ in sheets.LEG_MOUNTS)
MOUNT_SPAN_Y = (min(mount[1] for mount, _ in sheets.LEG_MOUNTS),
                max(mount[1] for mount, _ in sheets.LEG_MOUNTS))

SHEET_NAME_RE = re.compile(r"^compare_[0-9a-f]{6,32}\.png$")


# --------------------------------------------------------------------------- config i/o


def values_of(cfg: dict) -> dict:
    """The slider values a resolved config implies."""
    return {k.id: (cfg[k.key][k.index] if k.index is not None else cfg[k.key])
            for k in KNOBS}


def apply_values(base: dict, values: dict) -> dict:
    """base + slider values -> a new resolved config. Clamped to the slider ranges, so a
    hand-rolled POST cannot ask for scale 400 and a 20-minute render."""
    cfg = {key: (list(v) if isinstance(v, list) else v) for key, v in base.items()}
    for k in KNOBS:
        if k.id not in values:
            continue
        v = float(values[k.id])
        if not math.isfinite(v):
            raise ac.ConfigError(f"{k.id}: {values[k.id]!r} is not a finite number")
        v = min(max(v, k.lo), k.hi)
        if k.index is None:
            cfg[k.key] = v
        else:
            cfg[k.key][k.index] = v
    return cfg


def apply_opts(cfg: dict, opts: dict) -> dict:
    """The three render options, as the knobs they really are."""
    cfg = {key: (list(v) if isinstance(v, list) else v) for key, v in cfg.items()}

    def choice(name, allowed):
        """Fall back, never raise. `rotations=999` already fell back and `rotations='x'`
        raised -- the same class of junk getting two different answers, and only one of
        them is an answer. The page can only send what is in the select; anything else is
        a hand-rolled POST or a tab left open across a version, and neither deserves a
        stack trace."""
        try:
            want = int(opts.get(name, DEFAULT_OPTS[name]))
        except (TypeError, ValueError):
            return DEFAULT_OPTS[name]
        return want if want in allowed else DEFAULT_OPTS[name]

    cfg["compare.rotations"] = choice("rotations", ROTATION_CHOICES)
    cfg["render.resolution_px"] = choice("res", RES_CHOICES)
    cfg["compare.show_shadow"] = bool(opts.get("shadow", False))
    return cfg


def _num(v: float) -> str:
    """A float as TOML. Always carries a decimal point: `0` is an INT in TOML and the
    schema would coerce it back, but a config that reads `offset = [0, 0, 0.85]` invites
    the next reader to think the knob is an integer one."""
    s = "%.6g" % v
    if "." not in s and "e" not in s and "E" not in s:
        s += ".0"
    return s


def _toml_value(v) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(_num(x) for x in v) + "]"
    return _num(v)


def seed(committed: dict, sets: dict) -> tuple[dict, dict, str, dict]:
    """`--set` -> (committed, slider start values, export note, clamped knobs).

    --set has TWO jobs, because the sliders own five of the schema's knobs and --set takes
    any of them. On one of the five it seeds that slider. On ANYTHING ELSE it used to land
    in `start`, which is read for nothing but slider values, so `--set camera.canvas_tiles=8`
    moved no pixel and printed no complaint -- a silent no-op on the flag whose whole job is
    "carry on from yesterday". Those go into `committed` instead, where every render and
    both hashes pick them up (art.py's own meaning of --set), and they come back as a note
    for the export header, because the five exported lines cannot carry them.

    Seeded PAST a slider end is the other quiet one: the page paints 1.5 in the number box,
    the range input pins itself at 1.2, and the render clamps to 1.2 -- three numbers, one
    of them a lie. Clamp here instead and return what got moved so the terminal can say so.
    """
    slider_keys = {k.key for k in KNOBS}
    extra = {key: value for key, value in sets.items() if key not in slider_keys}
    committed = dict(committed)
    committed.update(extra)
    start = apply_values(committed, values_of(committed))
    for key, value in sets.items():
        if key not in extra:
            start[key] = value
    asked = values_of(start)
    start = apply_values(start, asked)            # apply_values is the clamp
    got = values_of(start)
    pinned = {k.id: (asked[k.id], got[k.id]) for k in KNOBS if asked[k.id] != got[k.id]}
    note = ""
    if extra:
        # The header hash is computed WITH these, because the render was. Say so, or the
        # block reads as "paste this, get this hash" and the hash comes back different.
        # Worded to read the same in the terminal at startup and as a comment in the block.
        note = ("also --set, in every render and in the hash but NOT in the exported "
                "[model] lines (add them by hand or the pasted hash will differ): "
                + " ".join("%s=%s" % (key, value) for key, value in sorted(extra.items())))
    return committed, start, note, pinned


def toml_block(cfg: dict, paste_hash: str, note: str = "") -> str:
    """The lines to paste into render/jamaltron.toml. Nothing else, no reformatting of
    the file's comments, and NEVER `model.blend` -- that path is machine-local and
    gitignored, and pasting it would break the config for everyone else.

    REPLACE, do not append. Both paste modes were checked against `art.py --compare` and
    both come back with the hash in the header; appending to the end of the file does not,
    it is `tomllib.TOMLDecodeError: Cannot declare ('model',) twice` and it arrives as a
    raw traceback. Hence the second comment line -- the instruction rides WITH the lines,
    because the clipboard is the only part of this that reaches the other window.
    """
    head = ["# tuned in render/tune.py %s -- config %s"
            % (time.strftime("%Y-%m-%d %H:%M"), paste_hash),
            "# REPLACE the [model] table in render/jamaltron.toml, or just these five keys "
            "inside it. Appending is a TOML error (model declared twice)."]
    if note:
        head.append("# " + note)
    head.append("[model]")
    for key in TOML_KEYS:
        head.append("%s = %s" % (key.split(".", 1)[1], _toml_value(cfg[key])))
    return "\n".join(head) + "\n"


# ------------------------------------------------------------------------------- tuner


class Tuner:
    """Render state for one server. One render at a time, latest values win."""

    def __init__(self, committed: dict, start: dict, jobs: int, note: str = ""):
        self.committed = committed
        self.start = start
        self.jobs = jobs
        #: Rides in the exported TOML header. Non-empty when `--set` moved a knob no slider
        #: owns: that knob IS in every render and both hashes, and it is NOT in the five
        #: exported lines, so the export has to say so or the paste silently loses it.
        self.note = note
        self.render_lock = threading.Lock()
        self.seq_lock = threading.Lock()
        #: newest seq seen PER PAGE SESSION. Not one global counter: a browser refresh
        #: restarts the page's seq at 1, and against a global high-water mark every
        #: request from the reloaded page is "older" than one the previous page already
        #: sent -- so the tuner would supersede everything forever and show no image,
        #: which is the single most obvious thing a person does to an unresponsive page.
        #: Per session, two tabs also each end on their own latest values.
        self.latest_seq: dict[str, int] = {}
        self.renders = 0

    # -- the cheap path: numbers and text, no Blender ---------------------------------

    def quote(self, values: dict, opts: dict) -> dict:
        """Everything a slider move can answer without rendering: hashes, the derived
        dimensions, the TOML to paste, and the standing knob warnings."""
        paste_cfg = apply_values(self.committed, values)
        cfg = apply_opts(paste_cfg, opts)
        paste_hash = ac.config_hash(paste_cfg)
        d = ac.derived(cfg)
        return {
            "tuner_hash": ac.config_hash(cfg),
            "paste_hash": paste_hash,
            "derived": {key: d[key] for key in
                        ("shark_length_tiles", "shark_width_tiles", "shark_height_tiles",
                         "body_resolution_px", "body_px_per_tile")},
            "toml": toml_block(paste_cfg, paste_hash, self.note),
            "warnings": ac.warnings(cfg),
        }

    # -- the expensive path ------------------------------------------------------------

    def bump(self, session: str, seq: int) -> None:
        with self.seq_lock:
            self.latest_seq[session] = max(self.latest_seq.get(session, 0), seq)

    def superseded(self, session: str, seq: int) -> bool:
        with self.seq_lock:
            return seq < self.latest_seq.get(session, 0)

    def render(self, seq: int, values: dict, opts: dict, session: str = "") -> dict:
        """Render one compare sheet. Never raises -- a bad knob has to come back as text
        on the page, because a tuner that dies on a value you were curious about is worse
        than no tuner.

        SUPERSEDING, and it is checked TWICE. Once before taking the render lock (drop a
        request that was already stale when it arrived) and once after (drop one that went
        stale while an earlier render held the lock). Blender itself is not interruptible
        here -- art.run_blender is a blocking subprocess.run -- so the guarantee is "the
        image always ends on the newest values", bought by never STARTING stale work,
        not by killing work in flight. At 1.7 s a frame-set that is the right trade.
        """
        self.bump(session, seq)
        if self.superseded(session, seq):
            return {"seq": seq, "superseded": True}
        with self.render_lock:
            if self.superseded(session, seq):
                return {"seq": seq, "superseded": True}
            return self._render_locked(seq, values, opts)

    def _render_locked(self, seq: int, values: dict, opts: dict) -> dict:
        t0 = time.time()
        quote = None
        buf = io.StringIO()
        try:
            quote = self.quote(values, opts)
            cfg = apply_opts(apply_values(self.committed, values), opts)
            frames = ac.frame_indices(cfg, cfg["compare.rotations"])
            # stdout AND stderr: art.py reports through the first and blender's own
            # failure text goes to the second, and the failure text is the half you need.
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                bodydir, _ = art.render_pass(cfg, "body", frames,
                                             cfg["render.preview_samples"], jobs=self.jobs)
                passes = [("body", cfg["render.engine"], cfg["render.preview_samples"])]
                shadowdir = None
                if cfg["compare.show_shadow"]:
                    shadowdir, _ = art.render_pass(cfg, "shadow", frames,
                                                   cfg["render.shadow_samples"],
                                                   jobs=self.jobs)
                    passes.append(("shadow", cfg["render.shadow_engine"],
                                   cfg["render.shadow_samples"]))
                png = art.compare_sheet(cfg, bodydir, shadowdir, frames, passes)
            _, sidecar = art.sheet_paths(cfg, "compare")
            blob = json.loads(sidecar.read_text())
            cov = blob.get("mount_coverage", {})
            out = dict(quote)
            out.update({
                "seq": seq, "ok": True, "superseded": False,
                "image": "/sheet?f=" + pathlib.Path(png).name,
                "seconds": round(time.time() - t0, 2),
                "frames": frames,
                "coverage_line": cov.get("line", ""),
                "coverage": cov.get("per_frame", []),
                "selfcheck": sheets.selfcheck_line(blob.get("mount_selfcheck", {"ran": False,
                                                            "why": "not in sidecar"})),
                "log": buf.getvalue(),
            })
        except (Exception, SystemExit) as exc:                 # SystemExit: art.py's own
            out = dict(quote or {})                            # blender-failed path
            out.update({
                "seq": seq, "ok": False, "superseded": False,
                "seconds": round(time.time() - t0, 2),
                "error": "%s: %s" % (type(exc).__name__, exc),
                "log": buf.getvalue() + "\n" + traceback.format_exc(limit=4),
            })
        self.renders += 1
        # The terminal is the other half of the tool: it gets the harness's own report,
        # the timing, and the TOML, so a value found here is one copy-paste OR one scroll
        # -back away from being committed.
        sys.stdout.write("\n[tune #%d seq %d] %s in %.2fs\n%s"
                         % (self.renders, seq, "ok" if out.get("ok") else "FAILED",
                            out["seconds"], out.get("log", "")))
        if out.get("ok"):
            sys.stdout.write("  %s\n" % out.get("coverage_line", ""))
            sys.stdout.write("\n" + out.get("toml", "") + "\n")
        else:
            sys.stdout.write("  ERROR %s\n" % out.get("error"))
        sys.stdout.flush()
        return out


# -------------------------------------------------------------------------------- http


class Handler(BaseHTTPRequestHandler):
    server_version = "jamaltron-tune"

    def __init__(self, *a, tuner: Tuner = None, **kw):
        self.tuner = tuner
        super().__init__(*a, **kw)

    # The default handler log writes a line per request to stderr, which buries the
    # harness's own output -- and the harness's output is the point of the terminal half.
    def log_message(self, fmt, *args):
        pass

    # -- plumbing ---------------------------------------------------------------------

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode() or "{}")

    # -- routes -----------------------------------------------------------------------

    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path == "/":
            return self._send(200, page(self.tuner).encode(), "text/html; charset=utf-8")
        if path == "/sheet":
            return self._sheet(query)
        return self._send(404, b"no", "text/plain")

    def do_POST(self):
        path = self.path.partition("?")[0]
        # The SHAPE check belongs in here with the parse. A body of `null`, `5`, `"hi"` or
        # `[1,2]` parses fine and then blows up on `.get` -- and an exception escaping
        # do_POST is not an error page, it is a dropped connection plus a raw traceback in
        # the terminal that the harness report is supposed to own. Same for a `values` that
        # is a string: `"scale" not in "abc"` is a legal substring test, so every slider
        # silently fell back to the committed value and the page looked like it worked.
        try:
            body = self._body()
            if not isinstance(body, dict):
                raise TypeError("expected a JSON object, got %s" % type(body).__name__)
            values = body.get("values") or {}
            opts = body.get("opts") or {}
            for name, obj in (("values", values), ("opts", opts)):
                if not isinstance(obj, dict):
                    raise TypeError("`%s` must be a JSON object, got %s"
                                    % (name, type(obj).__name__))
        except Exception as exc:
            return self._json({"error": "bad request body: %s" % exc}, 400)
        try:
            if path == "/quote":
                return self._json(self.tuner.quote(values, opts))
            if path == "/toml":
                q = self.tuner.quote(values, opts)
                sys.stdout.write("\n" + q["toml"] + "\n")
                sys.stdout.flush()
                return self._json({"toml": q["toml"]})
            if path == "/render":
                return self._json(self.tuner.render(int(body.get("seq") or 0), values, opts,
                                                    str(body.get("session") or "")))
        except (Exception, SystemExit) as exc:
            # Even the cheap paths report as text. The server does not get to die because
            # a slider sent something the schema hated.
            return self._json({"error": "%s: %s" % (type(exc).__name__, exc),
                               "log": traceback.format_exc(limit=4)}, 200)
        return self._send(404, b"no", "text/plain")

    def _sheet(self, query: str):
        name = ""
        for part in query.split("&"):
            key, _, value = part.partition("=")
            if key == "f":
                name = value
        if not SHEET_NAME_RE.match(name):
            return self._send(400, b"not a sheet name", "text/plain")
        path = art.out_root(self.tuner.committed) / "sheets" / name
        if not path.exists():
            return self._send(404, b"no such sheet", "text/plain")
        self._send(200, path.read_bytes(), "image/png")


# -------------------------------------------------------------------------------- page


PAGE = r"""<!doctype html>
<meta charset="utf-8"><title>jamaltron tuner</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 :root { color-scheme: dark; --bg:#16181a; --panel:#1e2124; --line:#2e3236; --ink:#dfe3e7;
         --dim:#8b9298; --hot:#ff40be; --warn:#ffb454; --bad:#ff6b6b; --ok:#7bd88f; }
 * { box-sizing: border-box; }
 body { margin:0; background:var(--bg); color:var(--ink);
        font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace; }
 header { padding:10px 14px; border-bottom:1px solid var(--line); display:flex;
          gap:14px; align-items:baseline; flex-wrap:wrap; }
 h1 { font-size:14px; margin:0; letter-spacing:.06em; text-transform:uppercase; }
 .wrap { display:flex; gap:14px; align-items:flex-start; padding:14px; flex-wrap:wrap; }
 .col { flex:1 1 360px; min-width:min(100%,340px); max-width:520px; }
 .grow { flex:3 1 560px; min-width:min(100%,340px); max-width:100%; }
 .panel { background:var(--panel); border:1px solid var(--line); border-radius:6px;
          padding:12px; margin-bottom:12px; }
 .k { margin-bottom:16px; }
 .k label { display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
 .k .name { font-weight:600; }
 .k .ends { display:flex; justify-content:space-between; color:var(--dim); font-size:11px;
            margin-top:2px; }
 .k input[type=range] { width:100%; margin:4px 0 0; accent-color:var(--hot); }
 .k .val { display:flex; gap:6px; align-items:center; }
 .k input[type=number] { width:88px; background:#121416; color:var(--ink);
                         border:1px solid var(--line); border-radius:4px; padding:2px 4px;
                         font:inherit; text-align:right; }
 .k .hint { color:var(--dim); font-size:11px; margin-top:4px; display:none; }
 .k.open .hint { display:block; }
 .why { background:none; border:0; color:var(--dim); cursor:pointer; font:inherit;
        padding:0 2px; }
 .opts { display:flex; gap:14px; flex-wrap:wrap; align-items:center; }
 .opts label { display:flex; gap:5px; align-items:center; cursor:pointer; }
 button { background:#2a2e32; color:var(--ink); border:1px solid var(--line);
          border-radius:4px; padding:5px 10px; font:inherit; cursor:pointer; }
 button:hover { background:#343a3f; }
 button.primary { border-color:var(--hot); }
 .row { display:flex; gap:8px; flex-wrap:wrap; }
 #img { width:100%; border-radius:4px; display:block; background:#0d0f10; }
 #img.stale { opacity:.45; }
 .num { color:var(--ok); }
 .dim { color:var(--dim); }
 .hot { color:var(--hot); }
 .bad { color:var(--bad); }
 .warnbox, .errbox { margin-top:8px; padding:8px; border-radius:4px; white-space:pre-wrap;
                     display:none; }
 .warnbox { border:1px solid var(--warn); color:var(--warn); }
 .errbox { border:1px solid var(--bad); color:var(--bad); }
 pre { margin:6px 0 0; white-space:pre-wrap; background:#121416; border:1px solid var(--line);
       border-radius:4px; padding:8px; color:var(--ink); max-height:40vh; overflow:auto; }
 table.cov { border-collapse:collapse; margin-top:6px; font-size:11px; }
 table.cov td { border:1px solid var(--line); padding:1px 5px; }
 .status { margin-left:auto; }
 .slow { color:var(--warn); }
</style>
<header>
  <h1>jamaltron tuner</h1>
  <span class="dim">tuner <span id="htuner" class="num">-</span></span>
  <span class="dim">paste <span id="hpaste" class="num">-</span></span>
  <span class="status" id="status">starting</span>
</header>
<div class="wrap">
  <div class="col">
    <div class="panel" id="knobs"></div>
    <div class="panel">
      <div class="opts">
        <label>rotations
          <select id="rotations"></select></label>
        <label>res
          <select id="res"></select></label>
        <label><input type="checkbox" id="shadow">
          shadow <span class="slow">(CYCLES, +12-15s)</span></label>
      </div>
      <div class="row" style="margin-top:10px">
        <button class="primary" id="rerender">re-render</button>
        <button id="reset">reset to committed</button>
        <button id="copy">copy TOML</button>
      </div>
    </div>
    <div class="panel">
      <div class="dim">paste into render/jamaltron.toml</div>
      <pre id="toml">-</pre>
    </div>
  </div>
  <div class="grow">
    <div class="panel">
      <div id="dims"></div>
      <div id="cover" style="margin-top:4px"></div>
      <div class="warnbox" id="warn"></div>
      <div class="errbox" id="err"></div>
    </div>
    <div class="panel">
      <img id="img" alt="compare sheet">
      <div class="dim" id="shotinfo" style="margin-top:6px"></div>
      <table class="cov" id="covtable"></table>
    </div>
    <details class="panel"><summary class="dim">harness log</summary><pre id="log">-</pre></details>
  </div>
</div>
<script>
const BOOT = __BOOT__;
const $ = id => document.getElementById(id);
const values = Object.assign({}, BOOT.start);
const opts = Object.assign({}, BOOT.opts);
// One id per page LOAD. Superseding is scoped to it, so a refresh starts a fresh count
// instead of sitting forever behind the previous page's high-water mark.
const SESSION = Math.random().toString(36).slice(2) + "-" + Date.now().toString(36);
let seq = 0, applied = 0, inflight = false, pending = false, tStart = 0;

// ---- sliders -------------------------------------------------------------------------
$("knobs").innerHTML = BOOT.knobs.map(k => `
  <div class="k" id="k_${k.id}">
    <label><span class="name">${k.label} <button class="why" data-k="${k.id}">?</button></span>
      <span class="val"><input type="number" id="n_${k.id}" min="${k.lo}" max="${k.hi}"
        step="${k.step}"><span class="dim">${k.unit}</span></span></label>
    <input type="range" id="r_${k.id}" min="${k.lo}" max="${k.hi}" step="${k.step}">
    <div class="ends"><span>${k.lo_label}</span><span class="dim">${k.key}${
      k.index === null ? "" : "[" + k.index + "]"}</span><span>${k.hi_label}</span></div>
    <div class="hint">${k.hint}</div>
  </div>`).join("");
$("rotations").innerHTML = BOOT.rotation_choices.map(r =>
  `<option value="${r}">${r}</option>`).join("");
$("res").innerHTML = BOOT.res_choices.map(r =>
  `<option value="${r}">${r === 0 ? "384 (native)" : r + " (fast)"}</option>`).join("");

for (const k of BOOT.knobs) {
  const r = $("r_" + k.id), n = $("n_" + k.id);
  const push = (v, from) => {
    v = Math.min(Math.max(parseFloat(v), k.lo), k.hi);
    if (!isFinite(v)) return;
    values[k.id] = v;
    if (from !== "r") r.value = v;
    if (from !== "n") n.value = v;
    quote(); schedule();
  };
  r.addEventListener("input", () => push(r.value, "r"));
  n.addEventListener("change", () => push(n.value, "n"));
}
document.querySelectorAll(".why").forEach(b => b.onclick = () =>
  $("k_" + b.dataset.k).classList.toggle("open"));

function paintKnobs() {
  for (const k of BOOT.knobs) { $("r_" + k.id).value = values[k.id];
                                $("n_" + k.id).value = values[k.id]; }
  $("rotations").value = opts.rotations; $("res").value = opts.res;
  $("shadow").checked = opts.shadow;
}
$("rotations").onchange = e => { opts.rotations = +e.target.value; quote(); render(); };
$("res").onchange = e => { opts.res = +e.target.value; quote(); render(); };
$("shadow").onchange = e => { opts.shadow = e.target.checked; quote(); render(); };
$("rerender").onclick = () => render();
$("reset").onclick = () => { Object.assign(values, BOOT.committed); paintKnobs();
                             quote(); render(); };
$("copy").onclick = () => {
  // Copy SYNCHRONOUSLY from the DOM inside the click, before any await -- Safari drops a
  // clipboard write that happens after one. The POST is only the terminal echo.
  const text = $("toml").textContent;
  navigator.clipboard.writeText(text).then(
    () => flash("copied " + text.split("\n").length + " lines"),
    e => flash("clipboard refused (" + e + ") -- select the block", true));
  post("/toml").catch(() => {});
};

// ---- live numbers (no round trip): same arithmetic artconfig.derived() does -----------
function dims() {
  const s = values.scale, g = values.girth;
  const len = BOOT.model_bu[0] * s, wid = BOOT.model_bu[1] * s * g,
        hei = BOOT.model_bu[2] * s, half = wid / 2;
  const covers = half >= BOOT.mount_half_width;
  $("dims").innerHTML =
    `shark <span class="num">${len.toFixed(2)}</span> x <span class="num">${wid.toFixed(2)}
     </span> x <span class="num">${hei.toFixed(2)}</span> tiles &nbsp;
     half-width <span class="${covers ? "num" : "hot"}">${half.toFixed(3)}</span>
     vs outer mounts at <span class="dim">&plusmn;${BOOT.mount_half_width.toFixed(3)}</span>
     ${covers ? "&check; reaches" : "&mdash; short by " +
       (BOOT.mount_half_width - half).toFixed(3) + " tiles"}`;
}

// ---- transport ------------------------------------------------------------------------
function post(path, extra) {
  return fetch(path, {method: "POST", headers: {"Content-Type": "application/json"},
                      body: JSON.stringify(Object.assign({values, opts}, extra || {}))})
         .then(r => r.json());
}
let quoteBusy = false, quoteAgain = false;
function quote() {
  dims();
  if (quoteBusy) { quoteAgain = true; return; }
  quoteBusy = true;
  post("/quote").then(q => {
    if (q.error) return;
    $("htuner").textContent = q.tuner_hash;
    $("hpaste").textContent = q.paste_hash;
    $("toml").textContent = q.toml;
    showWarn(q.warnings || []);
  }).catch(() => {}).finally(() => {
    quoteBusy = false;
    if (quoteAgain) { quoteAgain = false; quote(); }
  });
}
let timer = null;
function schedule(ms) {              // debounce: a drag must not queue twenty renders
  clearTimeout(timer);
  timer = setTimeout(render, ms === undefined ? 220 : ms);
}
function render() {
  clearTimeout(timer);
  if (inflight) { pending = true; return; }   // single flight; the newest values win
  inflight = true; pending = false;
  const mine = ++seq;
  tStart = performance.now();
  $("img").classList.add("stale");
  setStatus("rendering seq " + mine + (opts.shadow ? " (cycles shadow, be patient)" : ""));
  post("/render", {seq: mine, session: SESSION}).then(res => {
    const rtt = (performance.now() - tStart) / 1000;
    if (res.superseded) { setStatus("seq " + res.seq + " superseded"); return; }
    if (res.seq !== undefined && res.seq < applied) return;   // late answer, older values
    applied = res.seq === undefined ? applied : res.seq;
    apply(res, rtt);
  }).catch(e => {
    fail("server unreachable: " + e);
  }).finally(() => {
    inflight = false;
    if (pending) { pending = false; render(); }
  });
}
function apply(res, rtt) {
  if (res.tuner_hash) { $("htuner").textContent = res.tuner_hash;
                        $("hpaste").textContent = res.paste_hash;
                        $("toml").textContent = res.toml; }
  $("log").textContent = res.log || "-";
  showWarn(res.warnings || []);
  if (!res.ok) { fail(res.error || "render failed"); return; }
  $("err").style.display = "none";
  const img = $("img");
  img.onload = () => img.classList.remove("stale");
  img.src = res.image + "&t=" + Date.now();
  $("cover").innerHTML = "<span class=\"hot\">mounts</span> " + (res.coverage_line || "");
  $("covtable").innerHTML = "<tr>" + (res.coverage || []).map(c =>
      `<td>${c[0]}</td>`).join("") + "</tr><tr>" + (res.coverage || []).map(c =>
      `<td class="${c[1] === 0 ? "bad" : "num"}">${c[1]}/8</td>`).join("") + "</tr>";
  $("shotinfo").textContent =
    `seq ${res.seq} | ${res.frames.length} rotations @ ${res.derived.body_resolution_px}px `
    + `(${res.derived.body_px_per_tile.toFixed(1)} px/tile) | server ${res.seconds}s, `
    + `round trip ${rtt.toFixed(2)}s | ${res.selfcheck.startsWith("mount self-check PASS")
       ? "selfcheck PASS" : res.selfcheck}`;
  setStatus(`ok in ${rtt.toFixed(2)}s`);
}
function showWarn(list) {
  const box = $("warn");
  box.style.display = list.length ? "block" : "none";
  box.textContent = list.map(w => "WARN " + w).join("\n\n");
}
function fail(msg) {
  const box = $("err");
  box.style.display = "block";
  box.textContent = "RENDER FAILED, image above is the last good one\n\n" + msg;
  $("img").classList.remove("stale");
  setStatus("failed", true);
}
function setStatus(t, bad) { $("status").className = "status" + (bad ? " bad" : " dim");
                             $("status").textContent = t; }
function flash(t, bad) { setStatus(t, bad); }

paintKnobs(); quote(); render();
</script>
"""


def page(tuner: Tuner) -> str:
    boot = {
        "knobs": [{"id": k.id, "key": k.key, "index": k.index, "lo": k.lo, "hi": k.hi,
                   "step": k.step, "label": k.label, "unit": k.unit,
                   "lo_label": k.lo_label, "hi_label": k.hi_label, "hint": k.hint}
                  for k in KNOBS],
        "start": values_of(tuner.start),
        "committed": values_of(tuner.committed),
        "opts": DEFAULT_OPTS,
        "rotation_choices": list(ROTATION_CHOICES),
        "res_choices": list(RES_CHOICES),
        "model_bu": MODEL_BU,
        "mount_half_width": MOUNT_HALF_WIDTH,
        "mount_span_y": list(MOUNT_SPAN_Y),
    }
    return PAGE.replace("__BOOT__", json.dumps(boot))


# --------------------------------------------------------------------------------- cli


def build_parser():
    p = argparse.ArgumentParser(
        prog="tune.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=None, help="config TOML (default render/jamaltron.toml)")
    p.add_argument("--set", action="append", dest="sets", metavar="key=value",
                   help="seed a knob, TOML syntax -- use it to start where you left off")
    p.add_argument("--blend", default=None, help="the .blend (or $%s)" % ac.BLEND_ENV)
    p.add_argument("--port", type=int, default=8765, help="first port to try (default 8765)")
    p.add_argument("--jobs", type=int, default=4,
                   help="parallel Blenders. MEASURED: 4 is the floor of the curve on this "
                        "machine, 8 is 14x SLOWER (Metal context thrash). Default 4")
    p.add_argument("--no-open", action="store_true", help="do not open a browser")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    # The terminal is half the tool -- the harness's own report, the timings and the TOML
    # all come out here. Python line-buffers a TTY and BLOCK-buffers a pipe, so without
    # this a `tune.py | tee log` shows nothing for minutes and looks hung.
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(line_buffering=True)
    try:
        committed, start, note, pinned = seed(ac.load(args.config), ac.parse_set(args.sets))
    except ac.ConfigError as exc:
        sys.stderr.write("tune.py: %s\n" % exc)
        return 2
    if note:
        print(note)
    for kid, (asked, got) in sorted(pinned.items()):
        print("--set %s=%s is outside the slider range, clamped to %s" % (kid, asked, got))
    if args.blend:
        committed["model.blend"] = start["model.blend"] = args.blend

    blend = art.blend_path(committed)
    if not blend.exists():
        print("WARN model not found: %s\n     the .blend is gitignored and machine-local; "
              "point at it with --blend or $%s.\n     The server starts anyway and the page "
              "will show the error." % (blend, ac.BLEND_ENV))

    tuner = Tuner(committed, start, max(1, args.jobs), note)
    httpd = None
    for port in range(args.port, args.port + 12):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, tuner=tuner))
            break
        except OSError:
            continue
    if httpd is None:
        sys.stderr.write("tune.py: no free port in %d..%d\n" % (args.port, args.port + 11))
        return 2
    httpd.daemon_threads = True
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    print("jamaltron tuner on %s   jobs=%d  shadow OFF by default (Cycles is the 12-15s)\n"
          "  frames and sheets land in %s (gitignored). Every distinct value is its own\n"
          "  cache dir: ~2.8 MB per change, ~13 MB with the shadow on. A long session is\n"
          "  hundreds of MB you can delete whenever. Ctrl-C to stop."
          % (url, tuner.jobs, art.out_root(committed)))
    if not args.no_open:
        threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped after %d renders." % tuner.renders)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
