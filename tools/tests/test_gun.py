"""D.7.4: where the flamethrower's stream starts, and what it draws under.

The source is ONE point under his belly: gun_center_shift {0, 0.15}, gun_barrel_length 0, so
source = shift - (0, height 1.5) - 0.008 = (0, -1.36) screen tiles for every facing and aim
(measured, prototypes/gun.lua). chotchki picked it off a picture as a point 0.373 below the leg
hub, the mounts' mean (stock's 8 mounts * C.mount_shrink - C.mount_lift). It draws UNDER him
only because prototypes/layers.lua lifts his legs to 'projectile' and his torso to 'air-object'
(W1; entity.lua lays them, compat.lua again in data-final-fixes): the stream renders above
every layer up to 'explosion'. Not 'smoke' for the torso, one layer lower: the renderer draws
that layer blurred.

Headless draws nothing, so each of these can move silently with every gate passing: a new gun
number moves the flame, a new mount ring moves his belly off it, a layer change puts the flame
back on top of him. The fire harness's O lanes hold the ENGINE to (0, -1.36); these pins hold
the numbers it depends on. When one fails: re-run the O lanes, look (tools/shot.sh, a held
target at 8 bearings; procedure in tools/harness/jamaltron-fire-harness/control.lua's header),
then update the numbers here.
"""

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
PROTO = REPO / "mod" / "jamaltron" / "prototypes"
HARNESS = REPO / "tools" / "harness" / "jamaltron-fire-harness" / "control.lua"

SHIFT = (0.0, 0.15)
HEIGHT = 1.5            # the vehicle's, copied off stock's spidertron (not in this repo)
ENGINE_OFFSET = 0.008   # measured: the source sits this much above shift - height
SOURCE = (0.0, -1.36)   # what the fire harness checks, +-0.1
# Stock spidertron mount_position y, pixels (base entities.lua:9994-10043, 2.1.17, scale 1):
# x cancels pairwise, so the hub is on the centre line.
STOCK_MOUNT_Y_PX = (-22, -10, 4, 17, -22, -10, 4, 17)
HUB_Y = -0.223
BELOW_HUB = 0.373
LAYER_LEGS, LAYER_BODY = "projectile", "air-object"


def shared(name):
    text = (PROTO / "shared.lua").read_text()
    return re.search(r"^\s*%s = ([^,\n]+),?\s*(?:--.*)?$" % name, text, re.M).group(1).strip()


def test_gun_lua_carries_the_picked_source():
    gun = (PROTO / "gun.lua").read_text()
    assert re.search(r"^ap\.gun_center_shift = \{0, 0\.15\}$", gun, re.M), "gun_center_shift moved"
    assert re.search(r"^ap\.gun_barrel_length = 0$", gun, re.M), (
        "gun_barrel_length is back: the source swings round his facing again")


def test_the_source_arithmetic_lands_where_the_harness_checks():
    y = SHIFT[1] - HEIGHT - ENGINE_OFFSET
    assert abs(y - SOURCE[1]) < 0.005, y
    harness = HARNESS.read_text()
    assert "local SOURCE = {x = 0, y = -1.36}" in harness, (
        "the fire harness checks the stream against a different point than D.7.4 picked")


def test_the_hub_the_source_was_picked_under_has_not_moved():
    shrink, lift = float(shared("mount_shrink")), float(shared("mount_lift"))
    hub = sum(y / 32 for y in STOCK_MOUNT_Y_PX) / len(STOCK_MOUNT_Y_PX) * shrink - lift
    assert abs(hub - HUB_Y) < 0.0005, (
        "the leg hub moved to %.4f (picked under %.3f): his belly moved, the flame did not - "
        "re-look (see this file's docstring)" % (hub, HUB_Y))
    assert abs(SHIFT[1] - HUB_Y - BELOW_HUB) < 0.0005
    gun = (PROTO / "gun.lua").read_text()
    for stated in ("{0, -0.223}", "0.373", "(0, -1.36)"):
        assert stated in gun, "gun.lua's header no longer states %s" % stated


def test_the_layers_that_put_the_flame_under_him():
    assert shared("layer_legs") == '"%s"' % LAYER_LEGS, "his legs left 'projectile': flame over them"
    assert shared("layer_body") == '"%s"' % LAYER_BODY, (
        "his torso left 'air-object': the flame (or his own legs) draws over him, or on 'smoke' "
        "he draws blurred")
    layers = (PROTO / "layers.lua").read_text()
    assert re.search(r"^  gs\.render_layer = C\.layer_body$", layers, re.M), "torso layer not set"
    for part in (r"lgs\.upper_part\.render_layer", r"lgs\.lower_part\.render_layer",
                 r"lgs\.joint_render_layer"):
        assert re.search(r"^  %s = C\.layer_legs$" % part, layers, re.M), part + " not set"
    entity = (PROTO / "entity.lua").read_text()
    assert re.search(r"^layers\.torso\(gs\)$", entity, re.M), "entity.lua no longer lays the torso"
    assert re.search(r"^  assert\(layers\.leg\(leg\)", entity, re.M), "entity.lua no longer lays the legs"
    compat = (PROTO / "compat.lua").read_text()
    assert re.search(r"^M\.w1_layers\(\)$", compat, re.M), (
        "compat.lua no longer lays them again in data-final-fixes: a data-updates re-skin puts "
        "the flame back on top of him")


def test_the_beached_body_keeps_its_own_layer():
    # beached copies the vehicle's graphics_set: without its override he would lie on 'air-object'
    bodies = (PROTO / "bodies.lua").read_text()
    assert re.search(r'^beached_gs\.render_layer = "object"$', bodies, re.M)


def test_his_legs_are_fire_proof():
    # D.7.5 (b): his own splash (radius 4, every force) burns any foot near the aim point and leg
    # damage lands on the body. The fire harness's P and SB lanes prove it in the engine; this
    # pins the line that does it and the merge keeping stock's other leg resistances.
    entity = (PROTO / "entity.lua").read_text()
    assert re.search(r"^  leg\.resistances = fireproof\(leg\.resistances\)$", entity, re.M), (
        "entity.lua no longer fire-proofs his legs: he burns himself again (D.7.5 (b))")
    assert 'r, found = {type = "fire", percent = 100}, true' in entity, "the fire entry is not 100%"
    # beached and airborne copy the vehicle's final legs, so they inherit it
    bodies = (PROTO / "bodies.lua").read_text()
    assert 'util.copy(data.raw["spider-leg"][spec.leg])' in bodies
    harness = HARNESS.read_text()
    assert "0 HP of self-burn" in harness, "the fire harness lost its SB lane"
