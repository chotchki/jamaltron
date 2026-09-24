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
    # env={} on both sides so the two configs differ only in the knobs the block carries.
    # It used to be load bearing for a second reason -- $JAMALTRON_BLEND is a knob and the
    # hash was taken over its PATH -- but model.blend hashes by CONTENT now, so pointing
    # the two sides at two copies of one .blend would no longer break this.
    cfg = ac.load(env={})
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


def test_every_exported_value_is_spelled_the_way_its_schema_type_reads():
    """`offset = [0, 0, 0.85]` parses, but it reads as an integer knob to the next person and
    TOML's own types disagree with the schema's -- so a float knob always carries a point.
    The export also carries a string, a bool and an INT knob now (`action`, `reparent_head`,
    `frame`), and `frame = 12.0` would be a fatal `expected an integer` in the file it is
    pasted into. One rule per type, checked against the schema rather than by eye."""
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
        else:
            for number in got.strip(" []").split(","):
                assert "." in number or "e" in number, (key, got)


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
    assert "REPLACE" in head
    assert "[model]" in text and "[bounce]" in text, "the export spans two tables now"
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


# ---------------------------------------------------------------------------- C.5: poses
#
# The flop half of the page, still with no Blender in the loop. The seam this section used to
# pin was that `model.action` and `model.pose_gain` DID NOT EXIST: the page baked the pose
# into a temp .blend and the export had to emit two COMMENTED keys so a paste would not be a
# fatal `unknown knob`. The knobs landed, so what is pinned now is the opposite promise --
# the page sets knobs, the export is TOML you paste as-is, and the hash on screen is the hash
# of the picture.


def test_pose_falls_back_instead_of_rendering_something_misleading():
    """A stale tab or a hand-rolled POST gets the REST shark, not a stack trace and not a
    clip nobody asked for. Same rule apply_opts' `choice` follows."""
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
    """normalize_pose is the only thing between a browser select and `model.action`, whose
    enum is fatal. A junk clip has to become REST before it gets there, or a stale tab is a
    500 instead of a standing shark."""
    cfg = ac.load(env={})
    out = tune.posed(cfg, tune.normalize_pose({"clip": "SWIM_FASTT", "frame": 7}))
    assert out["model.action"] == tune.pose.REST
    ac.resolve(ac.unflatten(out), env={})            # would raise on a bad enum


def test_roll_is_rotation_zero_and_pitch_is_rotation_one():
    """Swap these two and every flop is tuned against the wrong axis while the page reads
    right. The order of model.rotation is [roll, pitch, yaw]."""
    by_id = {k.id: k for k in tune.KNOBS}
    assert (by_id["roll"].key, by_id["roll"].index) == ("model.rotation", 0)
    assert (by_id["pitch"].key, by_id["pitch"].index) == ("model.rotation", 1)
    assert by_id["roll"].lo <= -90.0 and by_id["roll"].hi >= 90.0, "must reach both flanks"
    # ... and it has to reach chotchki's 80-90 call plus the 105 where he starts reading as
    # dead belly-up in water, because that is the range the sheets are judged over.
    assert by_id["roll"].hi >= 105.0 and by_id["roll"].lo <= -105.0


def test_the_roll_slider_writes_the_knob_the_renderer_reads():
    cfg = tune.apply_values(ac.load(), {"roll": 35.0, "pitch": -4.0})
    assert cfg["model.rotation"] == [35.0, -4.0, 0.0]


def test_the_bounce_sliders_write_the_bounce_knobs():
    """The height and the phase are the two C.5 asked for, and they are the two you cannot
    pick without looking -- so they are sliders and not TOML-only."""
    cfg = tune.apply_values(ac.load(), {"bounce_height": 0.3, "bounce_phase": 0.25})
    assert cfg["bounce.height"] == 0.3 and cfg["bounce.phase"] == 0.25
    by_id = {k.id: k for k in tune.KNOBS}
    assert by_id["bounce_height"].lo == 0.0, "zero must be reachable: it is the default"
    assert by_id["bounce_phase"].hi <= 1.0, "phase is a fraction of one cycle"


def test_broadside_is_three_directions_around_east():
    """The only directions a beached shark reads from. Nose-on (index 0, which is where
    ac.frame_indices always starts) tells you nothing about a roll."""
    cfg = tune.apply_opts(ac.load(), {"view": "broadside"})
    frames = tune.view_frames(cfg, {"view": "broadside"})
    assert frames == [12, 16, 20], frames
    assert [ac.compass(f, cfg["rotations.count"]) for f in frames] == ["ENE", "E", "ESE"]
    # and the count knob follows the view, or the hash claims eight cells for a three-cell
    # sheet
    assert cfg["compare.rotations"] == 3
    assert tune.view_frames(ac.load(), {"view": "wheel"}) == ac.frame_indices(ac.load(), 8)
    assert tune.view_of({"view": "sideways"}) == "wheel", "unknown view falls back"


def test_a_posed_quote_names_the_hash_of_the_picture_it_is_showing():
    """This is what landing the knobs bought. The pose used to live in a baked .blend that
    did not exist until a render had run, so the header could only say "pending bake" -- a
    tool refusing to guess at provenance. Now the pose IS the config, both hashes are
    arithmetic, and they differ only by the tuner's own render options."""
    cfg = ac.load(env={})
    tuner = tune.Tuner(cfg, cfg, jobs=1)
    values = tune.values_of(cfg)
    rest = tuner.quote(values, {}, {"clip": tune.pose.REST})
    posed = tuner.quote(values, {}, {"clip": "SWIM_FAST", "frame": 7, "gain": 2.0})
    for q in (rest, posed):
        assert len(q["tuner_hash"]) == 12 and int(q["tuner_hash"], 16) >= 0
        assert len(q["paste_hash"]) == 12 and int(q["paste_hash"], 16) >= 0
    # the pose is in BOTH hashes now -- it is in the config, not in a temp file
    assert posed["paste_hash"] != rest["paste_hash"]
    assert posed["tuner_hash"] != rest["tuner_hash"]
    # and the paste hash is exactly the hash of the block over the file it lands in, which
    # is the whole promise of the copy-TOML button
    full = ac.resolve(dict(ac.unflatten(cfg), **tomllib.loads(posed["toml"])), env={})
    assert ac.config_hash(full) == posed["paste_hash"]


def test_a_posed_quote_warns_that_the_rest_pivot_is_unverified():
    """C.17: the shipped pivot was tuned by eye against the STRAIGHT shark. Inheriting it
    for a flop is the mistake this whole tuning task exists to prevent."""
    cfg = ac.load()
    tuner = tune.Tuner(cfg, cfg, jobs=1)
    values = tune.values_of(cfg)
    assert tuner.quote(values, {}, {"clip": tune.pose.REST})["warnings"] == []
    posed = tuner.quote(values, {}, {"clip": "SWIM_FAST", "frame": 7, "gain": 2.0})
    assert any("pivot" in w and "C.17" in w for w in posed["warnings"])
    # move it off the committed value and the warning goes: it is about INHERITING the
    # number, not about the number
    moved = tuner.quote(dict(values, pivot_x=-0.9), {},
                        {"clip": "SWIM_FAST", "frame": 7, "gain": 2.0})
    assert not any("pivot" in w for w in moved["warnings"])
    # the gain and rig-fix warnings come off the SCHEMA now (ac.warnings), so they reach the
    # CLI too -- the page just shows them
    assert any("C.18a" in w for w in posed["warnings"]), "HEAD is still welded to the world"
    hard = tuner.quote(dict(values, pivot_x=-0.9), {},
                       {"clip": "SWIM_FAST", "frame": 7, "gain": 2.9})
    assert any("2.6" in w for w in hard["warnings"]), "past the measured safe gain"


def test_the_posed_export_is_toml_you_paste_not_toml_you_uncomment():
    """It used to emit `# action = "SWIM_FAST"` because the knob did not exist and an
    uncommented paste was a fatal `unknown knob`. Now the paste is the point."""
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
    """The standing shark already shipped. No clip selected has to export as the config the
    sprites came off -- which now means saying `action = "rest"` out loud rather than
    omitting the key and hoping the reader knows the default."""
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
    """`model.action`, `model.frame` and `model.pose_gain` are one change. Set the action and
    leave the frame behind and the page's slider says 12 while the render shows frame 1."""
    cfg = ac.load(env={})
    out = tune.posed(cfg, tune.normalize_pose({"clip": "SWIM_FAST", "frame": 7, "gain": 2.0}))
    assert out["model.action"] == "SWIM_FAST"
    assert out["model.frame"] == 7
    assert out["model.pose_gain"] == 2.0
    assert cfg["model.action"] == "rest", "the committed config must not be mutated"
    assert cfg["model.frame"] == 1
    # every one of them has to move the body cache, or a frame change would serve the last
    # frame's pixels
    for key in ("model.action", "model.frame", "model.pose_gain"):
        assert "body" in ac.SCHEMA[key][2] and "shadow" in ac.SCHEMA[key][2], key
    assert ac.pass_hash(cfg, "body") != ac.pass_hash(out, "body")


def test_rest_selects_no_action_and_changes_nothing_else():
    cfg = ac.load(env={})
    out = tune.posed(cfg, tune.normalize_pose({"clip": tune.pose.REST, "frame": 9,
                                               "gain": 2.5}))
    assert out["model.action"] == tune.pose.REST
    # the frame and the gain are NOT carried: with no clip they would be a hash change for a
    # picture that is identical, which is the one thing the additive knobs must never do
    assert out["model.frame"] == cfg["model.frame"]
    assert out["model.pose_gain"] == cfg["model.pose_gain"]
    assert ac.config_hash(out) == ac.config_hash(cfg)


def test_the_rig_fix_is_a_render_option_that_still_reaches_the_export():
    """The checkbox lives in `opts` (it is a render option, like the shadow toggle), but the
    EXPORT has to carry whatever is ticked or the block describes a different picture."""
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
    pose.CLIPS, not a copy of it -- a copy is a table that rots."""
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
    """A `$("reparent")` with no `id="reparent"` is a TypeError on page load and a BLANK
    PAGE -- the failure you cannot debug from the terminal, because the terminal is fine.
    Cheap to check: the page is one string, and both halves of it are in it."""
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
    """One click to C.5's pose, because the ask was a roll slider "defaulted to 85" and the
    page cannot boot there -- it opens on the committed STANDING config, which is what keeps
    `reset to committed` meaningful and the shipped hash visible in the header.

    Pinned as data rather than trusted as markup: the preset is the decided recipe (roll 85,
    SWIM_FAST, gain 1.0 ungained, bounce 0.3, HEAD reparented, broadside), and it must reach
    the real knobs the renderer reads."""
    ids = {k.id for k in tune.KNOBS}
    assert set(tune.FLOP_PRESET["values"]) <= ids, "a preset value no slider owns"
    assert set(tune.FLOP_PRESET["pose"]) == set(tune.DEFAULT_POSE), "pose keys must match"
    assert set(tune.FLOP_PRESET["opts"]) <= set(tune.DEFAULT_OPTS) | set(tune.KNOB_BOXES)
    assert tune.FLOP_PRESET["values"]["roll"] == 85.0
    assert tune.FLOP_PRESET["values"]["yaw"] == 180.0, "chotchki's framing, 2026-09-23"
    assert tune.FLOP_PRESET["values"]["phase_lock"] == 0.5, "the C.5.2 call"
    assert tune.FLOP_PRESET["values"]["bounce_phase"] == 0.5, "travels with the lock"
    assert tune.FLOP_PRESET["pose"]["gain"] == 1.0, "ungained IS the call at this roll"
    assert tune.FLOP_PRESET["pose"]["clip"] == "SWIM_FAST"
    assert tune.FLOP_PRESET["opts"]["reparent"] is True

    cfg = ac.load(env={})
    p = tune.normalize_pose(tune.FLOP_PRESET["pose"])
    out = tune.apply_opts(tune.posed(tune.apply_values(cfg, tune.FLOP_PRESET["values"]), p),
                          dict(tune.DEFAULT_OPTS, **tune.FLOP_PRESET["opts"]))
    assert out["model.rotation"][0] == 85.0 and out["model.rotation"][2] == 180.0
    assert out["model.action"] == "SWIM_FAST" and out["model.pose_gain"] == 1.0
    assert out["bounce.height"] == 0.3 and out["bounce.phase"] == 0.5
    assert out["model.phase_lock"] == 0.5
    assert out["model.reparent_head"] is True
    assert out["model.ground_contact"] is True, "C.5.4: a fixed offset z buries the flop"
    assert out["compare.rotations"] == 3, "broadside, the three directions a roll reads in"
    # and it leaves the shark's own shape where it found it -- those are mid-tuning values
    # half the time, and a preset that reverted them is one nobody presses twice.
    for key in ("model.scale", "model.girth", "model.pivot"):
        assert out[key] == cfg[key], key
    assert out["model.rotation"][1] == cfg["model.rotation"][1], "pitch is not the preset's"


def test_the_roll_slider_reaches_past_the_rail_it_warns_about():
    """artconfig owns the number and the warning; the slider has to be able to GET there or
    the warning is unreachable from the page and the limit is back to being faith."""
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
    """C.5 gave the schema its second enum, and `--set 'model.action="SWIM_FASTT"'` used to
    sail past every check: the KEY is spelled right, so the unknown-knob suggester never sees
    it, and seed() wrote it into an already-resolved dict. The tuner booted, printed the typo
    in its own header note, and handed you a Blender traceback on the first render."""
    import pytest
    with pytest.raises(ac.ConfigError) as bad:
        seed_of({"model.action": "SWIM_FASTT"})
    assert "SWIM_FASTT" in str(bad.value) and "SWIM_FAST" in str(bad.value)
    with pytest.raises(ac.ConfigError):
        seed_of({"model.frame": "twelve"})          # type, same path
    # the valid ones still land, note and all
    committed, _, note, _ = seed_of({"model.action": "SWIM_FAST"})
    assert committed["model.action"] == "SWIM_FAST" and "model.action=SWIM_FAST" in note


def test_the_renders_own_warnings_reach_the_warning_box():
    """Some things only a render knows -- that the posed body reaches below the ground plane
    at this roll, that a frame touched its canvas edge -- and they arrive as text. Four jobs
    over two passes say each of them four times."""
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
    """art.py collects the renderer's notes and used to print NONE of them unless -v, which
    made every WARN the render can only discover itself -- the buried body, a clipped frame --
    invisible in the CLI and in the tuner at the same time."""
    from render import art
    notes = ["FIX nla muted: 5", "POSE action=SWIM_FAST gain=1.00",
             "WARN the posed body reaches 0.283 tiles BELOW the ground plane (z=0)"]
    assert art.warn_notes(notes) == [notes[-1]]


def test_the_phase_lock_slider_writes_the_knob_and_survives_the_paste():
    """The standing-wave knob is judged by eye like the bounce, so it is a slider -- and a
    lock found by dragging has to come out of the export or the flop you watched is not the
    flop you pasted."""
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
    """Both rig checkboxes are KNOBS, so both have to survive the paste, fall back to the
    config rather than to False, and boot ticked when --set ticked them. Checked as a table so
    a third box cannot be half-wired."""
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
        assert tune.box_of(cfg, {}, name) is False
        boot = json.loads(tune.page(tune.Tuner(seeded, seeded, jobs=1))
                          .split("const BOOT = ", 1)[1].split(";\n", 1)[0])
        assert boot["opts"][name] is True, name
        page = tune.page(tuner)
        # each half separately: the box, the paint (so the preset and reset tick it) and the
        # handler (so clicking it does something). Any one missing is a half-wired box.
        for want in ('id="%s"' % name, '$("%s").checked = !!opts.%s' % (name, name),
                     '$("%s").onchange' % name):
            assert want in page, (name, want)


def test_ground_contact_greys_out_the_height_it_cancels():
    """Contact cancels offset z, so the height slider can move no pixel while it is ticked.
    The page greys it (and the hash drops it -- see test_art_harness); a live-looking slider
    that does nothing is the tool feeling broken."""
    page = tune.page(tune.Tuner(ac.load(env={}), ac.load(env={}), jobs=1))
    assert "function deadHeight()" in page
    assert 'const dead = !!opts.ground;' in page
    assert "offset_z" in {k.id for k in tune.KNOBS}, "deadHeight() names this slider's id"
    for caller in ("  deadHeight();\n}", "opts.ground = e.target.checked; deadHeight();"):
        assert caller in page, caller


def test_seed_only_tells_you_to_add_what_the_export_really_lacks():
    """A --set of a non-slider knob the export ALREADY writes (the rig checkboxes, gravity)
    used to land in the 'add them by hand' note -- follow it and the paste declares the key
    twice, a TOML error. Only keys outside TOML_KEYS belong there."""
    committed = ac.load(env={})
    _, _, note, _ = tune.seed(committed, {"model.ground_contact": True,
                                          "model.reparent_head": True})
    assert note == ""
    _, _, note, _ = tune.seed(committed, {"model.ground_contact": True,
                                          "camera.canvas_tiles": 8.0})
    assert "camera.canvas_tiles=8.0" in note and "ground_contact" not in note
