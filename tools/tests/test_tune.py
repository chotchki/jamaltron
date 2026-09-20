"""The tuner's two load-bearing promises, without a browser or a Blender in sight.

 1. THE EXPORT ROUND-TRIPS. A number found by dragging a slider has to survive the paste
    into jamaltron.toml BIT FOR BIT, or the tuner is a toy that lies about what it showed
    you. `tomllib.loads(toml_block(cfg))` back through `ac.resolve()` must land on the
    same config and therefore the same `config_hash` the page printed.
 2. NOTHING CAN SLIP OUT OF THE EXPORT. Add a slider for C.5's flop poses, forget to add
    its key to TOML_KEYS, and the tool silently stops exporting the knob you were tuning.

Everything here is pure arithmetic and string formatting, which is the half of tune.py
worth pinning down -- the HTTP half is driven by hand, and the render half is art.py's.
"""

import tomllib

from render import artconfig as ac
from render import tune


def test_every_slider_is_exported():
    """The assert in tune.py is the real gate; this is the one that names the file."""
    assert {k.key for k in tune.KNOBS} <= set(tune.TOML_KEYS)


def test_slider_ids_and_indices_address_real_knobs():
    cfg = ac.resolve(env={})
    for k in tune.KNOBS:
        assert k.key in ac.SCHEMA, k.key
        value = cfg[k.key]
        if k.index is None:
            assert not isinstance(value, list), "%s is a vector knob, needs an index" % k.key
        else:
            assert isinstance(value, list) and k.index < len(value), k.key
        assert k.lo < k.hi and k.step > 0


def test_ranges_bracket_the_shipped_values():
    """A slider whose committed value sits outside its own range snaps the moment you
    touch it, and you would never see the value you started from."""
    cfg = ac.load()
    for k, v in tune.values_of(cfg).items():
        knob = next(x for x in tune.KNOBS if x.id == k)
        assert knob.lo <= v <= knob.hi, "%s: committed %r outside %r..%r" % (
            k, v, knob.lo, knob.hi)


def test_values_clamp_to_the_slider_range():
    cfg = ac.load()
    out = tune.apply_values(cfg, {"scale": 99.0, "pivot_x": -1e6})
    assert out["model.scale"] == max(x.hi for x in tune.KNOBS if x.id == "scale")
    assert out["model.pivot"][0] == min(x.lo for x in tune.KNOBS if x.id == "pivot_x")


def test_apply_values_does_not_mutate_the_base():
    """The base config is reused by every request; a vector knob written through a shared
    list would make one slider move leak into the next render."""
    cfg = ac.load()
    before = list(cfg["model.pivot"])
    tune.apply_values(cfg, {"pivot_x": -0.3, "offset_z": 1.2})
    assert cfg["model.pivot"] == before
    assert cfg["model.offset"][2] != 1.2


def test_toml_export_round_trips_to_the_same_hash():
    """The promise the copy-TOML button makes: paste, run art.py, get this hash."""
    cfg = ac.load()
    tuned = tune.apply_values(cfg, {"pivot_x": -0.3, "offset_z": 0.72, "girth": 1.45,
                                    "scale": 0.88, "pitch": 6.5})
    text = tune.toml_block(tuned, ac.config_hash(tuned))
    pasted = ac.resolve(tomllib.loads(text), env={})
    for key in tune.TOML_KEYS:
        assert pasted[key] == tuned[key], key
    # ... and the whole config, once the knobs the block does not carry come from the
    # same file the paste lands in.
    full = ac.resolve(dict(ac.unflatten(cfg), **tomllib.loads(text)), env={})
    assert ac.config_hash(full) == ac.config_hash(tuned)


def test_toml_numbers_are_always_floats():
    """`offset = [0, 0, 0.85]` parses, but it reads as an integer knob to the next person
    and TOML's own types disagree with the schema's."""
    cfg = tune.apply_values(ac.load(), {"pitch": 0.0, "girth": 1.0})
    for line in tune.toml_block(cfg, "deadbeef").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        for number in line.partition("=")[2].strip(" []").split(","):
            assert "." in number or "e" in number, line


def test_toml_never_exports_the_machine_local_model_path():
    """model.blend is gitignored and per-machine. Pasting it breaks the config for
    everyone else, including CI."""
    text = tune.toml_block(ac.load(), "deadbeef")
    assert "blend" not in text
    assert "HAMMERHEAD" not in text


def test_opts_fall_back_instead_of_rendering_something_absurd():
    cfg = ac.load()
    for junk in ({"rotations": 999, "res": 77},          # out of range
                 {"rotations": "x", "res": "big"},       # not a number at all
                 {"rotations": None, "res": []},         # not even a scalar
                 {}):                                    # nothing at all
        out = tune.apply_opts(cfg, dict(junk, shadow=False))
        assert out["compare.rotations"] in tune.ROTATION_CHOICES, junk
        assert out["render.resolution_px"] in tune.RES_CHOICES, junk
        assert out["compare.show_shadow"] is False, junk


def test_shadow_toggle_is_a_knob_and_moves_the_hash():
    """Off is the default because Cycles is the 12-15 s, and because it is a real knob
    the two states can never be served the same cached sheet."""
    cfg = ac.load()
    off = tune.apply_opts(cfg, {"rotations": 8, "res": 0, "shadow": False})
    on = tune.apply_opts(cfg, {"rotations": 8, "res": 0, "shadow": True})
    assert tune.DEFAULT_OPTS["shadow"] is False
    assert ac.config_hash(off) != ac.config_hash(on)


def test_supersede_is_scoped_to_a_page_session():
    """A browser refresh restarts the page's seq at 1. Against a global high-water mark
    every request from the reloaded page looks stale and the tuner shows nothing, forever.
    """
    cfg = ac.load()
    t = tune.Tuner(cfg, cfg, jobs=1)
    t.bump("tab-a", 7)
    assert t.superseded("tab-a", 3)
    assert not t.superseded("tab-a", 9)
    assert not t.superseded("tab-b", 1)        # the refreshed page must not be starved


def test_live_dimensions_come_from_artconfig_not_a_copy():
    """The page multiplies MODEL_BU in javascript; if that ever stops matching
    artconfig.derived() the numbers on screen are fiction."""
    cfg = tune.apply_values(ac.load(), {"scale": 0.88, "girth": 1.45})
    d = ac.derived(cfg)
    assert abs(tune.MODEL_BU[0] * 0.88 - d["shark_length_tiles"]) < 1e-9
    assert abs(tune.MODEL_BU[1] * 0.88 * 1.45 - d["shark_width_tiles"]) < 1e-9
    assert abs(tune.MODEL_BU[2] * 0.88 - d["shark_height_tiles"]) < 1e-9


def test_page_boots_with_valid_json():
    """__BOOT__ is replaced with json the page parses at load; a stray brace here is a
    blank page, and a blank page is the failure you cannot debug from the terminal."""
    import json
    import re
    cfg = ac.load()
    html = tune.page(tune.Tuner(cfg, cfg, jobs=1))
    assert "__BOOT__" not in html
    boot = json.loads(re.search(r"const BOOT = (\{.*?\});\n", html, re.S).group(1))
    assert [k["id"] for k in boot["knobs"]] == [k.id for k in tune.KNOBS]
    assert set(boot["start"]) == set(boot["committed"]) == {k.id for k in tune.KNOBS}


def test_sheet_names_are_the_only_thing_served():
    """The image route takes a filename off the query string. It must not take a path."""
    bad = ["../../PLAN.md", "/etc/passwd", "compare_../x.png", "compare_zz.png",
           "preview_abc123abc123.png", ""]
    for name in bad:
        assert not tune.SHEET_NAME_RE.match(name), name
    assert tune.SHEET_NAME_RE.match("compare_ede8605df9c2.png")


# -------------------------------------------------------------- what the review found


def test_seed_applies_a_non_slider_set_instead_of_swallowing_it():
    """`--set camera.canvas_tiles=8` used to land in the slider-start dict and die there:
    nothing but slider values is ever read out of it, so the knob moved no pixel and the
    tool said nothing. It belongs in the config every render is built from."""
    committed, start, note, pinned = seed_of({"camera.canvas_tiles": 8.0})
    assert committed["camera.canvas_tiles"] == 8.0
    assert start["camera.canvas_tiles"] == 8.0
    assert ac.derived(committed)["body_resolution_px"] != \
        ac.derived(ac.load())["body_resolution_px"]
    assert "camera.canvas_tiles=8.0" in note, "a knob the export cannot carry must be named"
    assert "hash" in note, "the header hash includes it; the note has to admit the paste does not"
    assert not pinned


def test_seed_clamps_a_value_seeded_past_the_slider_end():
    """Otherwise the number box says 1.5, the range input says 1.2 and the render uses
    1.2 -- three numbers on one screen, two of them wrong."""
    committed, start, note, pinned = seed_of({"model.scale": 1.5})
    hi = next(k.hi for k in tune.KNOBS if k.id == "scale")
    assert start["model.scale"] == hi
    assert tune.values_of(start)["scale"] == hi
    assert pinned["scale"] == (1.5, hi)
    assert not note


def test_seed_leaves_a_plain_slider_set_alone():
    committed, start, note, pinned = seed_of({"model.girth": 1.3})
    assert tune.values_of(start)["girth"] == 1.3
    assert committed["model.girth"] == ac.load()["model.girth"]   # the paste baseline
    assert not note and not pinned


def seed_of(sets):
    return tune.seed(ac.load(), sets)


def test_export_tells_you_to_replace_and_not_append():
    """MEASURED: appending the block to jamaltron.toml is
    `tomllib.TOMLDecodeError: Cannot declare ('model',) twice`, and it surfaces as a raw
    traceback. The instruction has to ride in the clipboard, because the clipboard is the
    only part of this that reaches the other window."""
    text = tune.toml_block(ac.load(), "deadbeef")
    head = "\n".join(line for line in text.splitlines() if line.startswith("#"))
    assert "REPLACE" in head and "[model]" in head
    assert "ppend" in head, "say what goes wrong if you append it"


def test_post_refuses_a_body_that_is_not_an_object():
    """A body of `null`, `5`, `"hi"` or `[1,2]` parses as JSON and then blows up on .get --
    and an exception out of do_POST is not an error page, it is a dropped connection plus a
    traceback in the terminal the harness report is supposed to own."""
    import json
    import threading
    import urllib.error
    import urllib.request
    from functools import partial
    from http.server import ThreadingHTTPServer

    cfg = ac.load()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0),
                               partial(tune.Handler, tuner=tune.Tuner(cfg, cfg, jobs=1)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]

    def quote(raw):
        req = urllib.request.Request(base + "/quote", data=raw, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    try:
        # `{"opts": []}` is deliberately NOT here: an empty container is falsy, so
        # `body.get("opts") or {}` turns it into the defaults, which is the right answer.
        for raw in (b"null", b"5", b'"hi"', b"[1,2]", b'{"values": 5}', b'{"values": "abc"}',
                    b'{"opts": 7}'):
            code, body = quote(raw)
            assert code == 400 and "bad request body" in body["error"], (raw, code, body)
        # and a good one still works, on the same server, after all that
        code, body = quote(json.dumps({"values": {"scale": 0.9}, "opts": {}}).encode())
        assert code == 200 and body["tuner_hash"], body
    finally:
        httpd.shutdown()
        httpd.server_close()
