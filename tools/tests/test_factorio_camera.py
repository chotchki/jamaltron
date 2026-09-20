"""Camera and sun math. The fixtures are Factorio's own numbers, not ours.

The projection cases check against values the GAME computes at data load from
base/prototypes/entity/fire.lua's real model coordinates, so they fail if our sign
convention or our px-per-tile ever drifts from the engine's. The light cases check the
45 degree sun that C.3 derived; the stock-art ones skip when Factorio is not installed,
which is the normal state in CI.
"""

import ast
import math
import pathlib
import sys

import pytest

from render import factorio_camera as fc

REPO_TOOLS = pathlib.Path(__file__).resolve().parents[1]

# The muzzle fixture. fire.lua ships the flamethrower turret's real model:
#   tilt_pivot = {-1.68551, 0, 2.35439}   gun_tip_lowered = {4.27735, 0, 3.97644}
#   gun_tip_raised = {2.2515, 0, 7.10942} units_per_tile = 4
# and computes prepared_muzzle_animation_shift by tilting the LOWERED tip up about the
# pivot, turning it about Z, scaling by (1/upt, 1/upt, -1/upt) and projecting. The tilted
# tip lands NEAR gun_tip_raised but not on it, which is why this repeats the tilt rather
# than shortcutting to the raised coordinate. Eight of the 64 shipped values, from a
# --dump-data run against Factorio 2.1.x on 2026-09-20.
TILT_PIVOT = (-1.68551, 0.0, 2.35439)
GUN_TIP_LOWERED = (4.27735, 0.0, 3.97644)
GUN_TIP_RAISED = (2.2515, 0.0, 7.10942)
UNITS_PER_TILE = 4.0
SHIPPED_MUZZLE = {
    0:  (0.0,                  -1.6563316403554313),
    8:  (0.39870986863498736,  -1.5395522229179008),
    16: (0.5638609045811829,   -1.2576217710801225),
    24: (0.39870986863498736,  -0.9756913192423443),
    32: (0.0,                  -0.8589119018048141),
    40: (-0.39870986863498736, -0.9756913192423443),
    48: (-0.5638609045811829,  -1.2576217710801225),
    56: (-0.39870986863498736, -1.5395522229179008),
}


def _muzzle_enu(r):
    """fire.lua's own pipeline, in (east, north, up) tiles, for frame r."""
    def sub(a, b):
        return tuple(x - y for x, y in zip(a, b))

    def angle(u, v):                            # math3d.vector3.angle
        dot = sum(x * y for x, y in zip(u, v))
        return math.acos(dot / math.sqrt(sum(x * x for x in u) * sum(x * x for x in v)))

    delta = -angle((1, 0, 0), sub(GUN_TIP_RAISED, TILT_PIVOT)) \
            + angle((1, 0, 0), sub(GUN_TIP_LOWERED, TILT_PIVOT))
    x, y, z = sub(GUN_TIP_LOWERED, TILT_PIVOT)
    c, s = math.cos(delta), math.sin(delta)     # matrix.rotation_y
    x, z = c * x + s * z, -s * x + c * z
    x, y, z = x + TILT_PIVOT[0], y + TILT_PIVOT[1], z + TILT_PIVOT[2]
    phi = (r / 64.0 - 0.25) * 2 * math.pi
    c, s = math.cos(phi), math.sin(phi)         # matrix.rotation_z
    x, y = c * x - s * y, s * x + c * y
    # matrix.scale(1/upt, 1/upt, -1/upt): the model's +z points DOWN once scaled, and the
    # model's +y is south, so east/north/up for us are x/upt, -y/upt, z/upt.
    return (x / UNITS_PER_TILE, -y / UNITS_PER_TILE, z / UNITS_PER_TILE)


@pytest.mark.parametrize("r,expected", sorted(SHIPPED_MUZZLE.items()))
def test_projection_reproduces_the_shipped_muzzle_positions(r, expected):
    """Zero free parameters: their model, their rotation, OUR projection, their number.
    The tolerance is the dumped JSON's own rounding, not slack."""
    u, v = fc.project(*_muzzle_enu(r))
    ppt = fc.px_per_tile(0.5)
    assert u / ppt == pytest.approx(expected[0], abs=1e-7)
    assert v / ppt == pytest.approx(expected[1], abs=1e-7)


def test_the_muzzle_orbit_is_a_circle_of_the_declared_radius():
    # a rigid point on a body turning about Z traces a circle; its screen ellipse is that
    # circle with the north axis squashed by K. Both amplitudes at once, so a wrong K or a
    # wrong winding cannot hide.
    ppt = fc.px_per_tile(0.5)
    xs = [fc.project(*_muzzle_enu(r))[0] / ppt for r in range(64)]
    ys = [fc.project(*_muzzle_enu(r))[1] / ppt for r in range(64)]
    amp_x = (max(xs) - min(xs)) / 2
    amp_y = (max(ys) - min(ys)) / 2
    assert amp_y / amp_x == pytest.approx(fc.K, abs=2e-4)


def test_one_constant_serves_depth_and_height():
    """A tile of ground-depth and a tile of height foreshorten identically. That equality
    IS the 45 degree camera - at any other elevation sin != cos and they differ."""
    assert fc.project(0, 1, 0)[1] == pytest.approx(fc.project(0, 0, 1)[1])
    assert fc.K == pytest.approx(math.sin(math.radians(fc.CAMERA_ELEVATION_DEG)))


def test_east_axis_is_not_foreshortened():
    # screen x is world east untouched, which is what makes a sheet's east/west alpha
    # extents readable as real tile widths.
    assert fc.project(1, 0, 0) == (64.0, 0.0)
    assert fc.px_per_tile(0.5) == 64 and fc.px_per_tile(1.0) == 32


def test_origin_pixel_is_off_centre_by_half_a_pixel():
    # pixel k covers [k, k+1), so the axis at res/2 lands on the seam, not on a centre.
    assert fc.origin_pixel(384) == 191.5
    assert fc.origin_pixel(385) == 192.0


def test_shadow_of_a_raised_point_lands_one_tile_east_per_tile_up():
    """The C.3 result: sun at 45 degrees due west, so run is exactly 1.0."""
    assert (fc.LIGHT_RUN_X, fc.LIGHT_RUN_Y) == (1.0, 0.0)
    ppt = fc.px_per_tile(0.5)
    u, v = fc.project_shadow(0, 0, 1.5)
    assert u / ppt == pytest.approx(1.5)       # 1.5 tiles east
    assert v == pytest.approx(0.0)             # on the ground, so no height term left
    # and the screen smear from the point to its shadow is (h, h*K)
    pu, pv = fc.project(0, 0, 1.5)
    assert (u - pu) / ppt == pytest.approx(1.5)
    assert (v - pv) / ppt == pytest.approx(1.5 * fc.K)


def test_a_ground_point_casts_onto_itself():
    assert fc.project_shadow(1.0, -0.5, 0.0) == fc.project(1.0, -0.5, 0.0)


def test_light_direction_is_a_unit_vector_travelling_east_and_down():
    e, n, u = fc.light_direction_enu()
    assert math.hypot(e, n, u) == pytest.approx(1.0)
    assert e > 0 and u < 0 and n == pytest.approx(0.0)
    assert math.degrees(math.atan2(-u, math.hypot(e, n))) == pytest.approx(fc.SUN_ELEVATION_DEG)


def test_frame_zero_is_north_and_the_index_runs_clockwise():
    assert fc.orientation_of_frame(0) == 0.0
    assert fc.orientation_of_frame(16) == 0.25           # east
    assert fc.orientation_of_frame(16, counterclockwise=True) == 0.75
    # Blender's +Z is counter-clockwise from above, so a clockwise sheet turns the model
    # the other way.
    assert fc.model_z_rotation(16) == pytest.approx(-math.pi / 2)
    assert fc.model_z_rotation(16, counterclockwise=True) == pytest.approx(-1.5 * math.pi)


def test_stays_importable_from_blender():
    """Blender has no Pillow and no venv. factorio_camera is imported by both sides, so a
    non-stdlib import at module level breaks every render script - at render time, on
    somebody else's machine. --verify imports PIL inside the function for exactly this."""
    src = (REPO_TOOLS / "render" / "factorio_camera.py").read_text()
    tree = ast.parse(src)
    top = set()
    for node in tree.body:                      # module level only; nested is fine
        if isinstance(node, ast.Import):
            top.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            top.add(node.module.split(".")[0])
    for node in tree.body:                      # plus the guarded bpy block
        if isinstance(node, ast.Try):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Import):
                    top.update(a.name.split(".")[0] for a in sub.names)
    offenders = top - sys.stdlib_module_names - {"bpy", "mathutils"}
    assert not offenders, f"non-stdlib module-level imports: {sorted(offenders)}"


@pytest.mark.skipif(not pathlib.Path(fc.FACTORIO_DATA).is_dir(),
                    reason="Factorio not installed; the stock-art check is a local one")
def test_light_still_agrees_with_the_shipped_spidertron_art():
    """The swept spidertron torso is a solid of revolution, so its shadow sheet's west and
    east edges follow from its BODY sheet alone once Lx is fixed. At Lx = 1 they land within
    a pixel and three of a pixel; this is the check that would catch a silent constant edit."""
    assert fc.verify_against_stock_art()
