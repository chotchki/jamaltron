"""The tuner's two core promises, with no browser or Blender.

 1. THE EXPORT ROUND-TRIPS. A slider value has to survive the paste into jamaltron.toml
    BIT FOR BIT, or the tuner lies about what it showed you: `tomllib.loads(toml_block(cfg))`
    through `ac.resolve()` must land on the same config and `config_hash` the page printed.
 2. NOTHING SLIPS OUT OF THE EXPORT. A slider whose key is missing from TOML_KEYS silently
    stops exporting the knob you were tuning.

Pure arithmetic and string formatting, the half of tune.py worth pinning; the HTTP half is
driven by hand and the render half is art.py's.
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
    """A committed value outside its slider's range snaps on first touch, losing the value
    you started from."""
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
    """Every request reuses the base config; a vector knob written through a shared list
    leaks one slider move into the next render."""
    cfg = ac.load()
    before = list(cfg["model.pivot"])
    tune.apply_values(cfg, {"pivot_x": -0.3, "offset_z": 1.2})
    assert cfg["model.pivot"] == before
    assert cfg["model.offset"][2] != 1.2


def test_toml_export_round_trips_to_the_same_hash():
    """The promise the copy-TOML button makes: paste, run art.py, get this hash."""
    # env={} on both sides so the configs differ only in the knobs the block carries.
    # ($JAMALTRON_BLEND is a knob and its hash was once taken over the PATH; model.blend hashes
    # by CONTENT now, so two copies of one .blend would not break this.)
    cfg = ac.load(env={})
    tuned = tune.apply_values(cfg, {"pivot_x": -0.3, "offset_z": 0.72, "girth": 1.45,
                                    "scale": 0.88, "pitch": 6.5})
    text = tune.toml_block(tuned, ac.config_hash(tuned))
    pasted = ac.resolve(tomllib.loads(text), env={})
    for key in tune.TOML_KEYS:
        assert pasted[key] == tuned[key], key
    # ... and the whole config, with the knobs the block omits taken from the file the
    # paste lands in.
    full = ac.resolve(dict(ac.unflatten(cfg), **tomllib.loads(text)), env={})
    assert ac.config_hash(full) == ac.config_hash(tuned)


def test_every_exported_value_is_spelled_the_way_its_schema_type_reads():
    """`offset = [0, 0, 0.85]` parses but reads as an integer knob and TOML's types disagree
    with the schema's, so a float knob always carries a point. The string, bool and INT knobs
    (`action`, `reparent_head`, `frame`) get their own rule: `frame = 12.0` is a fatal
    `expected an integer` where it is pasted. One rule per type, checked against the schema."""
    cfg = tune.apply_values(ac.load(), {"pitch": 0.0, "girth": 1.0})
    lines = {line.partition("=")[0].strip(): line.partition("=")[2].strip()
             for line in tune.toml_block(cfg, "deadbeef").splitlines()
             if "=" in line and not line.startswith("#")}
    for key in tune.TOML_KEYS:
        kind = ac.SCHEMA[key][0]
        got = lines[key.split(".", 1)[1]]
        if kind is str:
            assert got.startswith('"') and got.endswith('"'), (key, got)
        elif kind is bool:
            assert got in ("true", "false"), (key, got)
        elif kind is int:
            assert got.isdigit(), (key, got)
        elif isinstance(kind, tuple) and kind[0] == "list":      # bone names, maybe none
            names = [n.strip() for n in got.strip("[]").split(",") if n.strip()]
            assert got.startswith("[") and all(n[0] == n[-1] == '"' for n in names), (key, got)
        else:
            for number in got.strip(" []").split(","):
                assert "." in number or "e" in number, (key, got)


def test_toml_never_exports_the_machine_local_model_path():
    """model.blend is gitignored and per-machine; pasting it breaks the config for everyone
    else, including CI."""
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
    """Off by default because Cycles is the 12-15 s; as a real knob the two states never
    share a cached sheet."""
    cfg = ac.load()
    off = tune.apply_opts(cfg, {"rotations": 8, "res": 0, "shadow": False})
    on = tune.apply_opts(cfg, {"rotations": 8, "res": 0, "shadow": True})
    assert tune.DEFAULT_OPTS["shadow"] is False
    assert ac.config_hash(off) != ac.config_hash(on)


def test_supersede_is_scoped_to_a_page_session():
    """A browser refresh restarts the page's seq at 1; against a global high-water mark
    every request from the reloaded page looks stale and the tuner shows nothing, forever.
    """
    cfg = ac.load()
    t = tune.Tuner(cfg, cfg, jobs=1)
    t.bump("tab-a", 7)
    assert t.superseded("tab-a", 3)
    assert not t.superseded("tab-a", 9)
    assert not t.superseded("tab-b", 1)        # the refreshed page must not be starved


def test_live_dimensions_come_from_artconfig_not_a_copy():
    """The page multiplies MODEL_BU in javascript; if it drifts from artconfig.derived() the
    numbers on screen are fiction."""
    cfg = tune.apply_values(ac.load(), {"scale": 0.88, "girth": 1.45})
    d = ac.derived(cfg)
    assert abs(tune.MODEL_BU[0] * 0.88 - d["shark_length_tiles"]) < 1e-9
    assert abs(tune.MODEL_BU[1] * 0.88 * 1.45 - d["shark_width_tiles"]) < 1e-9
    assert abs(tune.MODEL_BU[2] * 0.88 - d["shark_height_tiles"]) < 1e-9


def test_page_boots_with_valid_json():
    """__BOOT__ becomes json the page parses at load; a stray brace is a blank page, which
    you cannot debug from the terminal."""
    import json
    import re
    cfg = ac.load()
    html = tune.page(tune.Tuner(cfg, cfg, jobs=1))
    assert "__BOOT__" not in html
    boot = json.loads(re.search(r"const BOOT = (\{.*?\});\n", html, re.S).group(1))
    assert [k["id"] for k in boot["knobs"]] == [k.id for k in tune.KNOBS]
    assert set(boot["start"]) == set(boot["committed"]) == {k.id for k in tune.KNOBS}


def test_sheet_names_are_the_only_thing_served():
    """The image route takes a filename off the query string, never a path."""
    bad = ["../../PLAN.md", "/etc/passwd", "compare_../x.png", "compare_zz.png",
           "preview_abc123abc123.png", ""]
    for name in bad:
        assert not tune.SHEET_NAME_RE.match(name), name
    assert tune.SHEET_NAME_RE.match("compare_ede8605df9c2.png")


# -------------------------------------------------------------- what the review found


def test_seed_applies_a_non_slider_set_instead_of_swallowing_it():
    """`--set camera.canvas_tiles=8` used to land in the slider-start dict, which only
    slider values are read from, so it moved no pixel and the tool said nothing. It belongs
    in the config every render is built from."""
    committed, start, note, pinned = seed_of({"camera.canvas_tiles": 8.0})
    assert committed["camera.canvas_tiles"] == 8.0
    assert start["camera.canvas_tiles"] == 8.0
    assert ac.derived(committed)["body_resolution_px"] != \
        ac.derived(ac.load())["body_resolution_px"]
    assert "camera.canvas_tiles=8.0" in note, "a knob the export cannot carry must be named"
    assert "hash" in note, "the header hash includes it; the note has to admit the paste does not"
    assert not pinned


def test_seed_clamps_a_value_seeded_past_the_slider_end():
    """Otherwise the number box says 1.5 while the range input and the render use 1.2."""
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
    traceback. The instruction rides in the clipboard, the only part that reaches the other
    window."""
    text = tune.toml_block(ac.load(), "deadbeef")
    head = "\n".join(line for line in text.splitlines() if line.startswith("#"))
    assert "REPLACE" in head
    assert "[model]" in text and "[bounce]" in text, "the export spans two tables now"
    assert "ppend" in head, "say what goes wrong if you append it"


def test_post_refuses_a_body_that_is_not_an_object():
    """A body of `null`, `5`, `"hi"` or `[1,2]` parses as JSON then blows up on .get, and an
    exception out of do_POST is a dropped connection plus a traceback in the terminal the
    harness report owns, not an error page."""
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
        # `{"opts": []}` is deliberately absent: an empty container is falsy, so
        # `body.get("opts") or {}` correctly turns it into the defaults.
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


# ---------------------------------------------------------------------------- C.5: poses
#
# The flop half of the page, no Blender. `model.action` and `model.pose_gain` used to not
# exist (the page baked the pose into a temp .blend and exported them COMMENTED out); now the
# page sets knobs, the export is TOML you paste as-is and the hash on screen is the
# picture's.


def test_pose_falls_back_instead_of_rendering_something_misleading():
    """A stale tab or a hand-rolled POST gets the REST shark, not a stack trace or an
    unasked-for clip (apply_opts' `choice` rule)."""
    junk = tune.normalize_pose({"clip": "../../etc/passwd", "frame": "x", "gain": [2],
                                "stride": None})
    assert junk == {"clip": tune.pose.REST, "frame": 1, "gain": 1.0,
                    "stride": tune.DEFAULT_POSE["stride"]}
    assert tune.normalize_pose(None)["clip"] == tune.pose.REST
    assert tune.normalize_pose("not a dict")["clip"] == tune.pose.REST
    got = tune.normalize_pose({"clip": "SWIM_FAST", "frame": 999, "gain": 99, "stride": 99})
    assert got == {"clip": "SWIM_FAST", "frame": 20, "gain": tune.pose.GAIN_MAX,
                   "stride": tune.STRIDE_MAX}


def test_a_clip_the_page_cannot_render_never_reaches_the_schema():
    """normalize_pose is the only guard between a browser select and `model.action`'s fatal
    enum: a junk clip becomes REST, or a stale tab is a 500 instead of a standing shark."""
    cfg = ac.load(env={})
    out = tune.posed(cfg, tune.normalize_pose({"clip": "SWIM_FASTT", "frame": 7}))
    assert out["model.action"] == tune.pose.REST
    ac.resolve(ac.unflatten(out), env={})            # would raise on a bad enum


def test_roll_is_rotation_zero_and_pitch_is_rotation_one():
    """model.rotation is [roll, pitch, yaw]; swapped, every flop is tuned against the wrong
    axis while the page reads right."""
    by_id = {k.id: k for k in tune.KNOBS}
    assert (by_id["roll"].key, by_id["roll"].index) == ("model.rotation", 0)
    assert (by_id["pitch"].key, by_id["pitch"].index) == ("model.rotation", 1)
    assert by_id["roll"].lo <= -90.0 and by_id["roll"].hi >= 90.0, "must reach both flanks"
    # ... and reach chotchki's 80-90 call plus the 105 where he reads as dead belly-up in
    # water: the range the sheets are judged over.
    assert by_id["roll"].hi >= 105.0 and by_id["roll"].lo <= -105.0


def test_the_roll_slider_writes_the_knob_the_renderer_reads():
    cfg = tune.apply_values(ac.load(), {"roll": 35.0, "pitch": -4.0})
    assert cfg["model.rotation"] == [35.0, -4.0, 0.0]


def test_the_bounce_sliders_write_the_bounce_knobs():
    """Height and phase are C.5's two asks and can only be picked by eye, so they are
    sliders, not TOML-only."""
    cfg = tune.apply_values(ac.load(), {"bounce_height": 0.3, "bounce_phase": 0.25})
    assert cfg["bounce.height"] == 0.3 and cfg["bounce.phase"] == 0.25
    by_id = {k.id: k for k in tune.KNOBS}
    assert by_id["bounce_height"].lo == 0.0, "zero must be reachable: it is the default"
    assert by_id["bounce_phase"].hi <= 1.0, "phase is a fraction of one cycle"


def test_broadside_is_three_directions_around_east():
    """The only directions a beached shark reads from; nose-on (index 0, where
    ac.frame_indices always starts) says nothing about a roll."""
    cfg = tune.apply_opts(ac.load(), {"view": "broadside"})
    frames = tune.view_frames(cfg, {"view": "broadside"})
    assert frames == [12, 16, 20], frames
    assert [ac.compass(f, cfg["rotations.count"]) for f in frames] == ["ENE", "E", "ESE"]
    # the count knob follows the view, or the hash claims eight cells for a three-cell sheet
    assert cfg["compare.rotations"] == 3
    assert tune.view_frames(ac.load(), {"view": "wheel"}) == ac.frame_indices(ac.load(), 8)
    assert tune.view_of({"view": "sideways"}) == "wheel", "unknown view falls back"


def test_a_posed_quote_names_the_hash_of_the_picture_it_is_showing(tmp_path):
    """The pose used to live in a baked .blend that did not exist until a render ran, so
    the header said "pending bake". Now the pose IS the config, both hashes are arithmetic,
    and they differ only by the tuner's own render options."""
    cfg = ac.load(env={})
    tuner = tune.Tuner(cfg, cfg, jobs=1)
    values = tune.values_of(cfg)
    rest = tuner.quote(values, {}, {"clip": tune.pose.REST})
    posed = tuner.quote(values, {}, {"clip": "SWIM_FAST", "frame": 7, "gain": 2.0})
    for q in (rest, posed):
        assert len(q["tuner_hash"]) == 12 and int(q["tuner_hash"], 16) >= 0
        assert len(q["paste_hash"]) == 12 and int(q["paste_hash"], 16) >= 0
    # the pose is in BOTH hashes: it is in the config, not a temp file
    assert posed["paste_hash"] != rest["paste_hash"]
    assert posed["tuner_hash"] != rest["tuner_hash"]
    # the paste hash is the hash of the block over the file it lands in (the copy-TOML
    # button's promise). For a POSE that file is beached.toml (C.24); pasted over the
    # standing file it would move the shipped shark.
    assert posed["toml_file"] == "render/beached.toml"
    assert ac.config_hash(_paste_into_overlay(tmp_path, posed["toml"])) == posed["paste_hash"]
    full = ac.resolve(dict(ac.unflatten(cfg), **tomllib.loads(rest["toml"])), env={})
    assert ac.config_hash(full) == rest["paste_hash"]


def test_a_posed_quote_warns_that_the_rest_pivot_is_unverified():
    """C.17: the shipped pivot was tuned by eye against the STRAIGHT shark; inheriting it
    for a flop is the mistake this tuning task exists to prevent."""
    cfg = ac.load()
    tuner = tune.Tuner(cfg, cfg, jobs=1)
    values = tune.values_of(cfg)
    assert tuner.quote(values, {}, {"clip": tune.pose.REST})["warnings"] == []
    posed = tuner.quote(values, {}, {"clip": "SWIM_FAST", "frame": 7, "gain": 2.0})
    assert any("pivot" in w and "C.17" in w for w in posed["warnings"])
    # off the committed value the warning goes: it is about INHERITING the number
    moved = tuner.quote(dict(values, pivot_x=-0.9), {},
                        {"clip": "SWIM_FAST", "frame": 7, "gain": 2.0})
    assert not any("pivot" in w for w in moved["warnings"])
    # the gain and rig-fix warnings come off the SCHEMA (ac.warnings), so the CLI gets them
    # too; the page just shows them
    assert any("C.18a" in w for w in posed["warnings"]), "HEAD is still welded to the world"
    hard = tuner.quote(dict(values, pivot_x=-0.9), {},
                       {"clip": "SWIM_FAST", "frame": 7, "gain": 2.9})
    assert any("2.6" in w for w in hard["warnings"]), "past the measured safe gain"


def test_the_posed_export_is_toml_you_paste_not_toml_you_uncomment():
    """It used to emit `# action = "SWIM_FAST"` because the knob did not exist and an
    uncommented paste was a fatal `unknown knob`."""
    cfg = ac.load(env={})
    p = tune.normalize_pose({"clip": "SWIM_FAST", "frame": 7, "gain": 2.0})
    posed = tune.posed(cfg, p)
    text = tune.toml_block(posed, "deadbeef", "", p, "cafef00dbeef")
    assert 'action = "SWIM_FAST"' in text and "pose_gain = 2.0" in text
    assert "frame = 7" in text
    parsed = tomllib.loads(text)
    assert set(parsed["model"]) | {"bounce." + k for k in parsed["bounce"]} == {
        k.split(".", 1)[1] if k.startswith("model.") else k for k in tune.TOML_KEYS}
    ac.resolve(parsed, env={})                       # would raise on an unknown knob
    assert "TODO" not in text, "nothing is pending any more"


def test_a_rest_export_says_rest_and_nothing_else():
    """The standing shark already shipped, so with no clip selected the export is the config
    its sprites came off, saying `action = "rest"` out loud rather than omitting the default."""
    cfg = ac.load(env={})
    text = tune.toml_block(tune.posed(cfg, tune.normalize_pose({})), "deadbeef")
    assert 'action = "rest"' in text
    assert "SWIM" not in text and "BITE" not in text
    pasted = ac.resolve(dict(ac.unflatten(cfg), **tomllib.loads(text)), env={})
    assert ac.config_hash(pasted) == ac.config_hash(cfg), "a rest paste is the shipped config"


def test_the_posed_export_still_round_trips_and_leaks_no_local_path():
    cfg = ac.load(env={})
    tuned = tune.apply_values(cfg, {"roll": 85.0, "pivot_x": -0.62,
                                    "bounce_height": 0.3, "bounce_phase": 0.25})
    posed = tune.posed(tuned, tune.normalize_pose({"clip": "SWIM_FAST", "frame": 12}))
    text = tune.toml_block(posed, ac.config_hash(posed), "", None, "cafef00dbeef")
    full = ac.resolve(dict(ac.unflatten(cfg), **tomllib.loads(text)), env={})
    assert ac.config_hash(full) == ac.config_hash(posed)
    assert "HAMMERHEAD" not in text


def test_posing_moves_three_knobs_together_or_none():
    """`model.action`, `model.frame` and `model.pose_gain` are one change; leave the frame
    behind and the slider says 12 while the render shows frame 1."""
    cfg = ac.load(env={})
    out = tune.posed(cfg, tune.normalize_pose({"clip": "SWIM_FAST", "frame": 7, "gain": 2.0}))
    assert out["model.action"] == "SWIM_FAST"
    assert out["model.frame"] == 7
    assert out["model.pose_gain"] == 2.0
    assert cfg["model.action"] == "rest", "the committed config must not be mutated"
    assert cfg["model.frame"] == 1
    # each moves the body cache, or a frame change serves the last frame's pixels
    for key in ("model.action", "model.frame", "model.pose_gain"):
        assert "body" in ac.SCHEMA[key][2] and "shadow" in ac.SCHEMA[key][2], key
    assert ac.pass_hash(cfg, "body") != ac.pass_hash(out, "body")


def test_rest_selects_no_action_and_changes_nothing_else():
    cfg = ac.load(env={})
    out = tune.posed(cfg, tune.normalize_pose({"clip": tune.pose.REST, "frame": 9,
                                               "gain": 2.5}))
    assert out["model.action"] == tune.pose.REST
    # frame and gain are NOT carried: with no clip they would change the hash of an
    # identical picture, which the additive knobs must never do
    assert out["model.frame"] == cfg["model.frame"]
    assert out["model.pose_gain"] == cfg["model.pose_gain"]
    assert ac.config_hash(out) == ac.config_hash(cfg)


def test_the_rig_fix_is_a_render_option_that_still_reaches_the_export():
    """The checkbox lives in `opts` (a render option, like the shadow toggle), but the EXPORT
    carries whatever is ticked or the block describes a different picture."""
    cfg = ac.load(env={})
    tuner = tune.Tuner(cfg, cfg, jobs=1)
    values = tune.values_of(cfg)
    on = tuner.quote(values, {"reparent": True}, {"clip": "SWIM_FAST", "frame": 7})
    off = tuner.quote(values, {"reparent": False}, {"clip": "SWIM_FAST", "frame": 7})
    assert "reparent_head = true" in on["toml"]
    assert "reparent_head = false" in off["toml"]
    assert on["paste_hash"] != off["paste_hash"] != ""
    # and a POST that never mentions it keeps the CONFIG's value, so --set survives
    seeded = ac.resolve({"model": {"reparent_head": True}}, env={})
    assert tune.reparent_of(seeded, {}) is True
    assert tune.reparent_of(seeded, {"reparent": False}) is False
    assert tune.reparent_of(cfg, {}) is False


def test_the_page_boots_with_the_clip_table_itself():
    """The select, the frame slider's range and every duration on the page come off
    pose.CLIPS, not a copy that rots."""
    import json
    cfg = ac.load()
    boot = json.loads(tune.page(tune.Tuner(cfg, cfg, jobs=1))
                      .split("const BOOT = ", 1)[1].split(";\n", 1)[0])
    assert [c["id"] for c in boot["clips"]] == [c.id for c in tune.pose.CLIPS]
    for got, want in zip(boot["clips"], tune.pose.CLIPS):
        assert (got["lo"], got["hi"], got["action"]) == (want.lo, want.hi, want.action)
    assert boot["pose"]["clip"] == tune.pose.REST, "the page opens on the shipped shark"
    assert boot["fps"] == tune.pose.FPS
    assert boot["gain"]["safe"] == tune.pose.GAIN_SAFE
    # the rig-fix box boots off the CONFIG, not off a page default, or --set is overridden
    assert boot["opts"]["reparent"] == cfg["model.reparent_head"]
    seeded = ac.resolve({"model": {"reparent_head": True}}, env={})
    boot2 = json.loads(tune.page(tune.Tuner(seeded, seeded, jobs=1))
                       .split("const BOOT = ", 1)[1].split(";\n", 1)[0])
    assert boot2["opts"]["reparent"] is True


def test_every_element_the_script_reaches_for_exists_in_the_markup():
    """A `$("reparent")` with no `id="reparent"` is a TypeError on load and a BLANK PAGE,
    undebuggable from the terminal because the terminal shows nothing wrong. Cheap: the page
    is one string holding both halves."""
    import re
    cfg = ac.load()
    html = tune.page(tune.Tuner(cfg, cfg, jobs=1))
    markup, _, script = html.partition("<script>")
    have = set(re.findall(r'id="([A-Za-z0-9_]+)"', markup))
    # ids the script CREATES before reading (the slider panel is rendered from BOOT.knobs)
    have |= {p + k.id for k in tune.KNOBS for p in ("k_", "r_", "n_")}
    want = set(re.findall(r'\$\("([A-Za-z0-9_]+)"\)', script))
    want -= {p + "${k.id}" for p in ("k_", "r_", "n_")}
    missing = sorted(w for w in want if w not in have and "$" not in w)
    assert not missing, "the page script reads ids the markup never defines: %s" % missing


def test_the_flop_preset_is_the_decided_recipe_and_only_that():
    """One click to C.5's pose: the ask was a roll slider "defaulted to 85", but the page
    opens on the committed STANDING config so `reset to committed` means something and the
    shipped hash shows in the header.

    Pinned as data, not markup: the preset is the decided recipe (roll 85, SWIM_FAST, V5's
    lock 1.0 at C.5.9's gain 1.25, bounce 0.3 at phase 0.4, HEAD reparented, broadside) and
    must reach the real knobs the renderer reads."""
    ids = {k.id for k in tune.KNOBS}
    assert set(tune.FLOP_PRESET["values"]) <= ids, "a preset value no slider owns"
    assert set(tune.FLOP_PRESET["pose"]) == set(tune.DEFAULT_POSE), "pose keys must match"
    assert set(tune.FLOP_PRESET["opts"]) <= set(tune.DEFAULT_OPTS) | set(tune.KNOB_BOXES)
    assert tune.FLOP_PRESET["values"]["roll"] == 85.0
    assert tune.FLOP_PRESET["values"]["yaw"] == 180.0, "chotchki's framing, 2026-09-23"
    assert tune.FLOP_PRESET["values"]["phase_lock"] == 1.0, "V5, chotchki 2026-09-26"
    assert tune.FLOP_PRESET["values"]["bounce_phase"] == 0.4, "C.5.9: lands on the push"
    assert tune.FLOP_PRESET["pose"]["gain"] == 1.25, "C.5.9: V5 toned down, chotchki 2026-09-26"
    assert tune.FLOP_PRESET["pose"]["clip"] == "SWIM_FAST"
    assert tune.FLOP_PRESET["opts"]["reparent"] is True

    cfg = ac.load(env={})
    p = tune.normalize_pose(tune.FLOP_PRESET["pose"])
    out = tune.apply_opts(tune.posed(tune.apply_values(cfg, tune.FLOP_PRESET["values"]), p),
                          dict(tune.DEFAULT_OPTS, **tune.FLOP_PRESET["opts"]))
    assert out["model.rotation"][0] == 85.0 and out["model.rotation"][2] == 180.0
    assert out["model.action"] == "SWIM_FAST" and out["model.pose_gain"] == 1.25
    assert out["bounce.height"] == 0.3 and out["bounce.phase"] == 0.4
    assert out["model.phase_lock"] == 1.0
    assert out["model.reparent_head"] is True
    assert out["model.ground_contact"] is True, "C.5.4: a fixed offset z buries the flop"
    assert out["compare.rotations"] == 3, "broadside, the three directions a roll reads in"
    # and it leaves the shark's shape alone: those are often mid-tuning values, and a preset
    # that reverted them is one nobody presses twice.
    for key in ("model.scale", "model.girth", "model.pivot"):
        assert out[key] == cfg[key], key
    assert out["model.rotation"][1] == cfg["model.rotation"][1], "pitch is not the preset's"


def test_the_flop_preset_on_beached_toml_is_the_shipped_v5_heave_knobs():
    """C.5.8 review: the preset was still C.5.2's lock 0.5 / gain 1.0, so pressing it on
    beached.toml exported a mixture (that lock and gain with V5's U knobs). Now it reproduces
    [model] exactly there, so its export reverts nothing."""
    cfg = ac.load(ac.BEACHED_CONFIG_PATH, env={})
    p = tune.normalize_pose(tune.FLOP_PRESET["pose"])
    out = tune.apply_opts(tune.posed(tune.apply_values(cfg, tune.FLOP_PRESET["values"]), p),
                          dict(tune.DEFAULT_OPTS, **tune.FLOP_PRESET["opts"]))
    for key in tune.FLOP_KEYS:
        if key != "model.frame":
            assert out[key] == cfg[key], key


def test_the_roll_slider_reaches_past_the_rail_it_warns_about():
    """artconfig owns the number and the warning; the slider has to GET there or the warning
    is unreachable from the page."""
    roll = next(k for k in tune.KNOBS if k.id == "roll")
    assert roll.hi > ac.ROLL_BELLY_UP and roll.lo < -ac.ROLL_BELLY_UP
    cfg = tune.apply_values(ac.load(env={}), {"roll": roll.hi})
    assert any("belly-up" in w for w in ac.warnings(cfg))
    assert not any("belly-up" in w for w in
                   ac.warnings(tune.apply_values(ac.load(env={}), {"roll": 85.0})))


def test_the_page_boots_with_the_preset_the_button_presses():
    import json
    cfg = ac.load()
    boot = json.loads(tune.page(tune.Tuner(cfg, cfg, jobs=1))
                      .split("const BOOT = ", 1)[1].split(";\n", 1)[0])
    assert boot["flop"] == tune.FLOP_PRESET
    assert boot["start"]["roll"] == cfg["model.rotation"][0], "the page still opens committed"


def test_a_set_the_sliders_do_not_own_is_still_checked_by_the_schema():
    """C.5 gave the schema its second enum, and `--set 'model.action="SWIM_FASTT"'` sailed
    past every check: the KEY is right, so the unknown-knob suggester never sees it, and
    seed() wrote it into an already-resolved dict: the tuner booted, showed the typo in its
    own header note, then died with a Blender traceback on the first render."""
    import pytest
    with pytest.raises(ac.ConfigError) as bad:
        seed_of({"model.action": "SWIM_FASTT"})
    assert "SWIM_FASTT" in str(bad.value) and "SWIM_FAST" in str(bad.value)
    with pytest.raises(ac.ConfigError):
        seed_of({"model.frame": "twelve"})          # type, same path
    # the valid ones still land, note and all
    committed, _, note, _ = seed_of({"model.action": "SWIM_FAST"})
    assert committed["model.action"] == "SWIM_FAST"
    # ...and NOT in the "add by hand" note: the pose controls boot off the config (C.28), so
    # the export already carries it
    assert "model.action" not in note


def test_the_renders_own_warnings_reach_the_warning_box():
    """Some things only a render knows (the posed body below the ground plane at this roll,
    a frame touching its canvas edge) and they arrive as text, deduplicated: four jobs over
    two passes say each four times."""
    log = ("  body    3 frames in 1.4s\n"
           "   WARN the posed body reaches 0.283 tiles BELOW the ground plane (z=0)\n"
           "   WARN the posed body reaches 0.283 tiles BELOW the ground plane (z=0)\n"
           "  compare cell 6.00 tiles holds every frame\n"
           "   WARN frame 016 touches the top edge of its canvas\n")
    got = tune.render_warnings(log)
    assert len(got) == 2, got
    assert got[0].startswith("the render says: the posed body reaches 0.283 tiles BELOW")
    assert "canvas" in got[1]
    assert tune.render_warnings("nothing to see here") == []


def test_a_warning_from_blender_is_not_hidden_behind_verbose():
    """art.py printed NONE of the renderer's notes without -v, hiding every render-only WARN
    (the buried body, a clipped frame) from both the CLI and the tuner."""
    from render import art
    notes = ["FIX nla muted: 5", "POSE action=SWIM_FAST gain=1.00",
             "WARN the posed body reaches 0.283 tiles BELOW the ground plane (z=0)"]
    assert art.warn_notes(notes) == [notes[-1]]


def test_the_phase_lock_slider_writes_the_knob_and_survives_the_paste():
    """The standing-wave knob is judged by eye like the bounce, so it is a slider, and the
    export has to carry it or the flop you watched is not the flop you pasted."""
    by_id = {k.id: k for k in tune.KNOBS}
    lock = by_id["phase_lock"]
    assert (lock.lo, lock.hi) == (0.0, 1.0), "0 must be reachable: it is the swim as bought"
    cfg = ac.load(env={})
    tuned = tune.apply_values(cfg, {"roll": 85.0, "yaw": 180.0, "phase_lock": 0.75,
                                    "bounce_height": 0.3})
    assert tuned["model.phase_lock"] == 0.75
    posed = tune.posed(tuned, tune.normalize_pose({"clip": "SWIM_FAST", "frame": 19}))
    text = tune.toml_block(posed, ac.config_hash(posed))
    assert "phase_lock = 0.75" in text
    full = ac.resolve(dict(ac.unflatten(cfg), **tomllib.loads(text)), env={})
    assert ac.config_hash(full) == ac.config_hash(posed)
    assert ac.pass_hash(posed, "body") != ac.pass_hash(
        tune.apply_values(posed, {"phase_lock": 0.0}), "body"), "a lock move must re-render"


def test_every_knob_box_reaches_the_export_and_the_page():
    """Both rig checkboxes are KNOBS: they survive the paste, fall back to the config rather
    than False, and boot ticked when --set ticked them. A table, so a third box cannot be
    half-wired."""
    import json
    cfg = ac.load(env={})
    tuner = tune.Tuner(cfg, cfg, 1)
    values = tune.values_of(cfg)
    for name, key in tune.KNOB_BOXES.items():
        assert key in tune.TOML_KEYS and key in ac.ADDITIVE, key
        leaf = key.split(".", 1)[1]
        for ticked in (True, False):
            q = tuner.quote(values, {name: ticked}, {"clip": "SWIM_FAST", "frame": 7})
            assert "%s = %s" % (leaf, "true" if ticked else "false") in q["toml"], (key, ticked)
        seeded = ac.resolve(ac.unflatten({key: True}), env={})
        assert tune.box_of(seeded, {}, name) is True
        assert tune.box_of(seeded, {name: False}, name) is False
        unseeded = ac.resolve(ac.unflatten({key: False}), env={})
        assert tune.box_of(unseeded, {}, name) is False
        # and the committed config's own value, whatever it is (ground is ON since C.27)
        assert tune.box_of(cfg, {}, name) is cfg[key]
        boot = json.loads(tune.page(tune.Tuner(seeded, seeded, jobs=1))
                          .split("const BOOT = ", 1)[1].split(";\n", 1)[0])
        assert boot["opts"][name] is True, name
        page = tune.page(tuner)
        # each part separately: the box, the paint (so preset and reset tick it) and the
        # handler (so clicking it does something).
        for want in ('id="%s"' % name, '$("%s").checked = !!opts.%s' % (name, name),
                     '$("%s").onchange' % name):
            assert want in page, (name, want)


def test_ground_contact_greys_out_the_height_it_cancels():
    """Contact cancels offset z, so the height slider moves no pixel while ticked. The page
    greys it (the hash drops it, see test_art_harness); a live-looking dead slider feels
    broken."""
    page = tune.page(tune.Tuner(ac.load(env={}), ac.load(env={}), jobs=1))
    assert "function deadHeight()" in page
    assert 'const dead = !!opts.ground;' in page
    assert "offset_z" in {k.id for k in tune.KNOBS}, "deadHeight() names this slider's id"
    for caller in ("  deadHeight();\n}", "opts.ground = e.target.checked; deadHeight();"):
        assert caller in page, caller


def test_seed_only_tells_you_to_add_what_the_export_really_lacks():
    """A --set of a non-slider knob the export ALREADY writes (the rig checkboxes, gravity)
    landed in the 'add them by hand' note; following it declares the key twice, a TOML
    error. Only keys outside TOML_KEYS belong there."""
    committed = ac.load(env={})
    _, _, note, _ = tune.seed(committed, {"model.ground_contact": True,
                                          "model.reparent_head": True})
    assert note == ""
    _, _, note, _ = tune.seed(committed, {"model.ground_contact": True,
                                          "camera.canvas_tiles": 8.0})
    assert "camera.canvas_tiles=8.0" in note and "ground_contact" not in note


def test_a_set_pose_boots_the_page_on_that_pose_and_reaches_the_export():
    """C.28: `tune.py --set 'model.action="SWIM_FAST"'` booted the pose controls on REST and
    posed() writes them over the config, so the --set rendered the standing shark and
    exported `action = "rest"`. The controls boot off the config now; the committed
    standing config still boots on exactly DEFAULT_POSE."""
    import json
    cfg = ac.load(env={})
    assert tune.pose_of(cfg) == tune.DEFAULT_POSE, "the page still opens on the shipped shark"
    committed, _, _, _ = tune.seed(cfg, {"model.action": "SWIM_FAST", "model.frame": 12,
                                         "model.pose_gain": 1.5})
    tuner = tune.Tuner(committed, committed, jobs=1)
    boot = json.loads(tune.page(tuner).split("const BOOT = ", 1)[1].split(";\n", 1)[0])
    assert boot["pose"] == {"clip": "SWIM_FAST", "frame": 12, "gain": 1.5,
                            "stride": tune.DEFAULT_POSE["stride"]}
    q = tuner.quote(tune.values_of(committed), {}, boot["pose"])
    assert 'action = "SWIM_FAST"' in q["toml"] and "frame = 12" in q["toml"]
    assert "pose_gain = 1.5" in q["toml"]


# ---------------------------------------------------------- C.24: which file the export is for


def _paste_into_overlay(tmp_path, block: str) -> dict:
    """Paste an overlay block into a copy of render/beached.toml as the header says (REPLACE
    the keys) and resolve the result, [sequence] and all."""
    import tomllib
    own = tomllib.loads(ac.BEACHED_CONFIG_PATH.read_text())
    own.pop("sequence", None)
    own["base"] = str(ac.DEFAULT_CONFIG_PATH)            # absolute: the copy lives in tmp
    flat = ac.flatten({k: v for k, v in own.items() if k != "base"})
    flat.update(ac.flatten(tomllib.loads(block)))
    lines = ['base = "%s"' % own["base"]]
    for key, value in sorted(ac.unflatten(flat).items()):
        lines.append("[%s]" % key)
        lines += ["%s = %s" % (leaf, tune._toml_scalar(v)) for leaf, v in value.items()]
    path = tmp_path / "beached.toml"
    path.write_text("\n".join(lines) + "\n")
    return ac.load(path, env={})


def test_the_overlay_export_round_trips_and_carries_no_shared_knob(tmp_path):
    """Opened on beached.toml, the block is the overlay's own keys plus what moved; pasted
    back it hashes to the header's paste hash, with no scale/girth/pivot in it."""
    import tomllib
    cfg = ac.load(ac.BEACHED_CONFIG_PATH, env={})
    tuner = tune.Tuner(cfg, cfg, 1, config_path=ac.BEACHED_CONFIG_PATH)
    values = dict(tune.values_of(cfg), phase_lock=0.7)
    q = tuner.quote(values, {}, dict(tune.pose_of(cfg), frame=12))
    assert q["toml_file"] == "render/beached.toml"
    assert "REPLACE these keys in render/beached.toml" in q["toml"]
    body = ac.flatten(tomllib.loads(q["toml"]))
    assert body["model.phase_lock"] == 0.7 and body["model.frame"] == 12
    for shared in ("model.scale", "model.girth", "model.pivot", "model.offset"):
        assert shared not in body, shared
    assert "SHARED" not in q["toml"]
    assert ac.config_hash(_paste_into_overlay(tmp_path, q["toml"])) == q["paste_hash"]


def test_a_shared_knob_moved_on_the_flop_page_is_exported_and_flagged(tmp_path):
    cfg = ac.load(ac.BEACHED_CONFIG_PATH, env={})
    tuner = tune.Tuner(cfg, cfg, 1, config_path=ac.BEACHED_CONFIG_PATH)
    q = tuner.quote(dict(tune.values_of(cfg), scale=0.9), {}, tune.pose_of(cfg))
    assert "scale = 0.9" in q["toml"]
    assert "NOTE model.scale: SHARED knob" in q["toml"]
    assert ac.config_hash(_paste_into_overlay(tmp_path, q["toml"])) == q["paste_hash"]


def test_a_pose_tuned_off_the_standing_file_is_exported_for_beached_toml(tmp_path):
    """THE C.24 BUG: the flop preset on the standing page said 'REPLACE these tables in
    render/jamaltron.toml', and pasting it moved the shipped standing shark. A posed block
    now names beached.toml, is overlay-shaped and round-trips there; a rest block still
    names jamaltron.toml and is the whole-file block."""
    standing = ac.load(env={})
    tuner = tune.Tuner(standing, standing, 1)
    values = dict(tune.values_of(standing), **tune.FLOP_PRESET["values"])
    q = tuner.quote(values, tune.FLOP_PRESET["opts"], tune.FLOP_PRESET["pose"])
    assert q["toml_file"] == "render/beached.toml"
    assert "jamaltron.toml it would move the STANDING shark" in q["toml"]
    assert "pivot" not in q["toml"] and "girth" not in q["toml"]
    assert ac.config_hash(_paste_into_overlay(tmp_path, q["toml"])) == q["paste_hash"]
    rest = tuner.quote(tune.values_of(standing), {}, None)
    assert rest["toml_file"] == "render/jamaltron.toml"
    assert "REPLACE these tables in render/jamaltron.toml" in rest["toml"]
    assert "pivot = " in rest["toml"]


def test_the_page_names_the_file_the_block_is_for():
    page = tune.page(tune.Tuner(ac.load(env={}), ac.load(env={}), 1))
    assert 'id="tomlfile"' in page
    assert page.count('$("tomlfile").textContent') == 2      # quote AND render both paint it


def test_a_pose_off_some_other_whole_file_is_not_redirected(tmp_path):
    """The redirect diffs against beached.toml's BASE; off any other whole file that diff
    drops every knob the two disagree on and the paste hash lies, so it stays a whole-file
    block for the file it was opened on."""
    other = tmp_path / "other.toml"
    other.write_text(ac.DEFAULT_CONFIG_PATH.read_text().replace("scale = 0.81", "scale = 0.9"))
    cfg = ac.load(other, env={})
    tuner = tune.Tuner(cfg, cfg, 1, config_path=other)
    assert tuner.flop is None
    values = dict(tune.values_of(cfg), **tune.FLOP_PRESET["values"])
    q = tuner.quote(values, tune.FLOP_PRESET["opts"], tune.FLOP_PRESET["pose"])
    assert q["toml_file"] == "render/other.toml"
    assert "REPLACE these tables in render/other.toml" in q["toml"] and "scale = 0.9" in q["toml"]
