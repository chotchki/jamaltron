#!/usr/bin/env python3
"""The Factorio camera and sun, derived from the game rather than from folklore.

RUN, three ways:
    uv run --directory tools python render/factorio_camera.py            # print the constants
    uv run --directory tools python render/factorio_camera.py --verify   # re-measure them off the shipped art
    /Applications/Blender.app/Contents/MacOS/Blender -b --python tools/render/factorio_camera.py

Importable from both sides of the Blender boundary: everything above the `bpy` guard is
stdlib-only arithmetic, so the projection can be unit-tested and reused by the packer, and
`--verify` imports Pillow lazily so a Blender-side import never touches it.

THE PROJECTION, and where it comes from
---------------------------------------
Factorio ships its own projection in `core/lualib/math3d.lua`:

    math3d.projection_constant = 0.7071067811865          -- 1/sqrt(2)
    function math3d.project_vec3(vec3)
      return { vec3[1], (vec3[2] + vec3[3]) * math3d.projection_constant }
    end

Screen x is the world east axis untouched; screen y is (ground-depth + height) scaled by
one shared constant. ONE constant for both terms is the whole story: it is an ORTHOGRAPHIC
camera at exactly 45 degrees elevation, the unique angle where sin == cos, so a tile of
ground-depth and a tile of height foreshorten identically.

That is not a reading of the source, it is the number the game shipped. base/prototypes/
entity/fire.lua runs the flamethrower turret's real model coordinates
(gun_tip_raised = {2.2515, 0, 7.10942}, units_per_tile = 4) through project_vec3 and bakes
the 64 results into the prototype. fire.lua also pins the sign convention: it scales the
model by (1/upt, 1/upt, -1/upt) before projecting, so the model's +z is DOWN and the
projected y is (south - up) * K, which is exactly this module's project().

SCALE
-----
1 world tile = 32/scale source pixels. At the scale every stock sprite uses, 0.5, that is
64 px per tile. Proven two ways: base terrain declares size-1/2/4 tile variants at
scale 0.5 in 64/128/256 px cells, and `spidertron-animations.lua` comments its leg offsets
"offset length in tiles (= px / 32)".

Only the EAST-WEST axis is 64 px per tile. North-south ground and height both land at
64 * 0.7071 = 45.25 px per tile, because that is what the 45 degree camera does.

ROTATION
--------
64 directions, frame 0 = north, index increasing CLOCKWISE, 8 frames per row. Measured off
the stock tank turret (tracking the muzzle across its 64 frames walks top -> right ->
bottom -> left) and confirmed by Wube's own code: fire.lua rotates the model by
`phi = (r/N - 0.25) * 2pi` about Z, and its model faces +X, so frame 0 points north and
frame 1 has already moved east. A sheet that wants the other direction sets
`counterclockwise = true` - the flamethrower turret gun does, the spidertron torso does not.

Rotate the MODEL, never the camera: the sun is fixed in world space, so rotating the camera
would drag the shadows around with it.

ORIGIN PIXEL
------------
The camera axis lands on pixel INDEX (res-1)/2, not res/2 - pixel k covers [k, k+1), so the
continuous centre res/2 falls on the seam between pixels 191 and 192 of a 384 px render.
Getting this wrong is a clean half-pixel bias in every shift the packer emits. It showed up
as exactly that in both validations below before it was fixed - the reference-box run read
1.49 px instead of 0.99 px, and the muzzle run could not get under half a pixel at all.

THE SUN: 45 DEGREES, DUE WEST, RUN 1.0
--------------------------------------
A point at height h drops its shadow exactly h tiles due EAST. On screen that is a smear of
(h, h*K) - the same 1/sqrt(2) as the camera, because the sun sits at the same 45 degrees
the camera does. Five independent lines of evidence, listed with what each one can and
cannot show:

 1. THE SPIDERTRON'S OWN SHEETS, with no shape assumption whatsoever - the sharpest test
    and the one that matters most, because C.4 replaces exactly this sprite. Take the UNION
    of all 64 rotations: the swept solid is a solid of revolution with SOME radius profile
    r(z), whatever the torso actually looks like, and that is free rather than assumed.
    Screen x is world east untouched, so over the 64 frames:
        body   east/west extent  = +- max_z r(z)              = +-1.0312
        body   south extent      = K * max_z(r(z) - z)        = +0.4688
        body   north extent      = -K * max_z(r(z) + z)       = -1.6562
        shadow west extent       = -max_z(r(z) - z*Lx)        = -0.6719
        shadow east extent       = +max_z(r(z) + z*Lx)        = +2.2969
    At Lx = 1 the shadow terms COLLAPSE onto the body terms - shadow_W = -body_S/K and
    shadow_E = -body_N/K - so the sun predicts both shadow edges from the body sheet alone,
    with nothing fitted and r(z) never evaluated:
        shadow west  predicted -0.6629   measured -0.6719   err -0.6 px
        shadow east  predicted +2.3423   measured +2.2969   err -2.9 px
    (the east residual is a thin antenna: the body's north-most pixel is a spike that loses
    alpha as a shadow, and it errs SHORT, which is the direction a fading tip errs.)
    No other Lx predicts anything without first pinning where on the profile the extremes
    live. Grant it the friendliest reading - the widest ring r = 1.0312 is the one attaining
    both, so it sits at z = 0.3683 on the south side and z = 1.3110 on the north - and:
        Lx = 0.8165 (the poles)   west +3.8 px   east +12.5 px
        Lx = 0.7457 (cannon)      west +5.4 px   east +18.4 px
        Lx = 0.70   (old proof)   west +6.5 px   east +22.3 px
 2. THE FLAMETHROWER TURRET GUN vs its own shadow sheet. fire.lua ships the muzzle's 3D
    model coordinate, so its height (7.10942/4 = 1.7774 tiles) is KNOWN - which is what
    breaks the degeneracy every other raster measurement suffers from (a 2D sprite can only
    ever give you north+height, never either alone). On the nine frames where the barrel
    points east, the muzzle rim provably attains BOTH the gun sheet's east extent and the
    shadow sheet's east extent (the rim point maximising `e` also maximises `e + z*Lx` for
    any Lx < 1.2), so differencing the two sheets' east-most alpha cancels the edge
    convention exactly:
        smear = (1.6615, 1.1806) tiles, dy/dx = 0.7106 against K = 0.7071
        -> Lx = 0.98 +- 0.03 for a muzzle rim radius of 0.10..0.16 tiles
 3. THE SUBSTATION'S AUTHORED wire/shadow CONNECTION POINTS. Each terminal declares both
    where the wire meets the pole and where that same point's shadow lands, so the
    difference is the screen smear with no silhouette guesswork. Its copper terminal (on
    the axis, identical in all 4 orientations) gives dy/dx = 0.7069 -> Lx = 1.0003.
 4. THE ENGINE ITSELF: utility-constants ships
    `train_on_elevated_rail_shadow_shift_multiplier = {1.41421356237, 1}` = (1/K, 1). What
    the engine multiplies by is not documented, so this corroborates the DIRECTION only -
    but a screen smear whose dy/dx is exactly K is Lx = 1, Ly = 0 and nothing else.
 5. THE CANVASES THEMSELVES. A shadow sprite's frame is cut to hold its shadow, so on a
    tall entity the frame width measures the shadow's length. Every tall stock shadow is
    cut off by its own frame - alpha in the last pixel column - and Lx = 1.0 lands the tip
    at that edge while 0.8165 leaves half a tile to a whole tile of empty canvas, which is
    not how Wube cuts sheets (derive/clip_test.py):
        entity                top U    shadow alpha E   frame E   Lx=1.0   Lx=0.8165
        small-electric-pole   3.757        3.578         3.594     3.757     3.067
        medium-electric-pole  4.530        3.938         3.953     4.530     3.699
        big-electric-pole     5.436        5.406         5.438     5.436     4.438
        substation            3.867        4.797         4.828     4.898     4.188
    The big pole is the cleanest: its frame's east edge is +5.438 and a 45 degree sun puts
    the tip at +5.436.

LIGHT_RUN_Y is 0.0 because nothing measurable disagrees with due east: the spidertron's
shadow sheet is symmetric north/south to 1.7 px and 0.3 px, and its shadow shift is
by_pixel(26, 0.5) - half a pixel south against 26 east.

DISSENTERS, recorded so nobody re-derives them and thinks they are news
-----------------------------------------------------------------------
* THE THREE ELECTRIC POLES' CONNECTION POINTS, which is where this module's previous
  LIGHT_RUN_X of 0.82 came from. Same method as (3) and just as tight - dy/dx = 0.866
  +- 0.005 over 36 terminals (small 0.8672, medium 0.8660, big 0.8588), i.e. Lx = 0.8165
  and a 50.8 degree sun. It is WRONG, and (5) says why: on a mast, a 45 degree sun puts the
  wire's true shadow off the end of the canvas, so the artist put the wire-shadow
  attachment somewhere readable on the visible shadow instead. The small pole's declared
  copper shadow point sits at +3.078 while its own drawn shadow reaches +3.578 and is still
  clipped - the declared point is half a tile short of art that is itself cut off. Tight
  scatter across four orientations of the same pole is consistency, not accuracy. The same
  method survives on the SUBSTATION because a squat entity's shadow fits in frame.
* `cannon_barrel_light_direction = {0.5976251, -0.0242053, -0.8014102}` (ENU), declared on
  the artillery turret and wagon: run 0.746 east / 0.030 south, a 53.3 degree sun. It is
  the light used to SHADE a recoil-shifted barrel at runtime, not a shadow-casting
  direction. It misses the spidertron's shadow edge by 5.4 px and leaves more empty canvas
  than 0.8165 does on every sprite in (5). Worth knowing it exists - it is the only 3D
  light vector the game declares anywhere - but the shadow ART does not obey it.
* SILHOUETTE-BBOX DIFFERENCING on poles (body east extent vs shadow east extent over the
  body's own screen height) gives 0.69-0.70. It is structurally biased low: it assumes the
  widest part of the caster is also its top, and on a pole the crossarm sits below the tip.
  The 0.70 burned into the earlier C3_shadow_proof.png came from this method.

VALIDATED
---------
* PROJECTION, zero free parameters: a marker at Factorio's own gun_tip_raised, rendered
  through this camera at all 64 rotations, reproduces the 64 shipped muzzle positions to
  max 0.19 px / mean 0.08 px (verify_muzzle.py).
* PROJECTION, second opinion: the 11 authored light groups in spidertron-light-positions.lua
  are rigid points, and their first-harmonic amplitude ratios give sin(elevation) =
  0.718 +- 0.009, i.e. 45.9 degrees, with every u/v harmonic pair 90 +- 1 degrees apart
  (light_positions_fit.py). Authored by eye, so this is a sanity check, not the proof.
* CAMERA + LIGHT against the renderer: an asymmetric 2.24 x 1.00 x 0.90 tile proxy box
  (shark proportions, so its silhouette AND its shadow change on every one of the 64
  rotations - a square box or a round blob gives the same bbox every frame, which is one
  measurement dressed up as 64), Cycles CPU at 64 px/tile. Rendered body bbox vs the
  projected corners: max 0.76 px, mean 0.47 px. Rendered shadow bbox vs the SHEARED
  corners: max 0.97 px, mean 0.63 px. Both at an alpha threshold of 32; across thresholds
  8..128 the worst edge moves between 0.76 and 1.71 px, and that spread IS the error bar,
  because a rendered edge is a ramp - about a pixel is the antialiased fringe and it is the
  floor, not an error.
* THE RENDERER against stock art: a caster lathed to the swept envelope above (every corner
  of its profile taken from the BODY sheet) lands its rendered shadow on the stock shadow
  sprite's swept extents to W +0.0, E +1.0, N -1.0, S +0.0 px. Read the claim correctly:
  this is the same arithmetic as (1) with Blender in the loop, so it tests the RENDER, not
  the light. Per FRAME it does not match and cannot - the stock torso is not a solid of
  revolution, its shadow's east extent swings 1.438..2.297 tiles across the 64 frames.

The verification kit that produces those numbers (render_proxy / verify_proxy /
render_torso / shadow_proof / camera_proof / render_muzzle / verify_muzzle /
light_positions_fit) is C.3 scratchpad work and is not in the repo; what IS in the repo is
`--verify` here, which re-derives both constants off the installed game's own sprites, and
tools/tests/test_factorio_camera.py, which checks the projection against eight muzzle
positions the game itself computes.

ENGINE
------
Cycles CPU for anything needing a shadow pass - MEASURED 2026-09-19, EEVEE Next IGNORES
`is_shadow_catcher` on Blender 4.4.3: the catcher plane renders as a solid opaque plane
(1024x1024 fully opaque) where Cycles gives the 181 px shadow strip. EEVEE is fine for the
body pass and cheaper (64 frames of 384px: EEVEE 14.3 s wall / 2.2 s CPU on Metal, Cycles
CPU 14.2 s wall / 60 s CPU at 24 samples), but the shadow_animation pass has no EEVEE path.
"""

import math
import os

PROJECTION_CONSTANT = 0.7071067811865   # core/lualib/math3d.lua, == sin(45deg) == cos(45deg)
K = PROJECTION_CONSTANT
NOMINAL_PX_PER_TILE = 32                # Factorio's internal unit: a tile is 32 px at scale 1
CAMERA_ELEVATION_DEG = 45.0             # the unique angle where sin == cos, which is what
                                        # one shared projection constant means

# Stock spidertron torso, measured off the real PNGs and cross-checked against the
# prototype (spidertron-animations.lua: 132x138 frames, line_length 8, 64 directions,
# scale 0.5, shift by_pixel(0,-19)); the file is an exact 8x8 grid of 1056x1104.
STOCK = dict(frame_w=132, frame_h=138, line_length=8, direction_count=64,
             scale=0.5, shift_px=(0.0, -19.0), sheet=(1056, 1104))

# THE SUN. A point at height Z drops its shadow at ground (Z*LIGHT_RUN_X, Z*LIGHT_RUN_Y)
# tiles, i.e. on screen at (Z*LIGHT_RUN_X, Z*(1+LIGHT_RUN_Y)*K) from where the point is
# drawn. See "THE SUN" above for the four derivations and the two dissenters; the short
# version is that the spidertron's own shadow sheet predicts its west edge to 0.6 px at
# run 1.0 and misses by 3.8 px at 0.82.
LIGHT_RUN_X = 1.0          # tiles east per tile of height
LIGHT_RUN_Y = 0.0          # tiles south per tile of height - measured as zero
SUN_ELEVATION_DEG = 45.0   # degrees(atan2(1, hypot(run_x, run_y)))
SUN_AZIMUTH_DEG = 90.0     # compass bearing the shadow RUNS toward; the sun sits due west


def origin_pixel(resolution):
    """Pixel INDEX the camera axis (the entity origin) falls on. See ORIGIN PIXEL above."""
    return (resolution - 1) / 2.0


def px_per_tile(scale=0.5):
    """Source pixels per world tile along the EAST-WEST axis."""
    return NOMINAL_PX_PER_TILE / scale


def project(x_tiles, y_north_tiles, z_tiles, scale=0.5):
    """World tiles (east, north, up) -> source pixel offset from the entity origin.

    Returns (px_right, px_down). North and up both move the point up-screen; the shared
    0.7071 is the 45 degree camera."""
    ppt = px_per_tile(scale)
    return (x_tiles * ppt, -(y_north_tiles + z_tiles) * K * ppt)


def project_shadow(x_tiles, y_north_tiles, z_tiles, scale=0.5):
    """Same point's SHADOW: drop it on the ground along the sun, then project that.

    Ground point is (east + z*run_x, north - z*run_y); it has no height term left, which
    is why a shadow's screen y is pure ground depth."""
    return project(x_tiles + z_tiles * LIGHT_RUN_X,
                   y_north_tiles - z_tiles * LIGHT_RUN_Y, 0.0, scale)


def light_direction_enu():
    """Unit vector the sunlight TRAVELS, in (east, north, up) tiles. Down is negative up."""
    v = (LIGHT_RUN_X, -LIGHT_RUN_Y, -1.0)
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def orientation_of_frame(index, direction_count=64, counterclockwise=False):
    """Frame index -> Factorio orientation (0 = north, 0.25 = east, clockwise)."""
    o = index / direction_count
    return (-o) % 1.0 if counterclockwise else o


def model_z_rotation(index, direction_count=64, counterclockwise=False):
    """Blender Z rotation in RADIANS for a model whose rest pose faces +Y (north).

    Blender's +Z rotation is counter-clockwise seen from above and Factorio's frames run
    clockwise, so the sign is negative for the default sheet."""
    turns = orientation_of_frame(index, direction_count, counterclockwise)
    return -2.0 * math.pi * turns


# --------------------------------------------------------------------------------------
try:
    import bpy, mathutils
except ImportError:
    bpy = None

if bpy is not None:

    def reset_scene():
        bpy.ops.wm.read_factory_settings(use_empty=True)
        return bpy.context.scene

    def setup_render(scene, canvas_tiles, scale=0.5, engine="CYCLES", samples=64,
                     transparent=True):
        """Square canvas `canvas_tiles` tiles wide, at exactly 32/scale px per tile."""
        ppt = px_per_tile(scale)
        res = int(round(canvas_tiles * ppt))
        r = scene.render
        r.engine = engine
        r.resolution_x = res
        r.resolution_y = res
        r.resolution_percentage = 100
        r.film_transparent = transparent
        r.image_settings.file_format = "PNG"
        r.image_settings.color_mode = "RGBA"
        r.image_settings.color_depth = "8"
        r.image_settings.compression = 0          # crush later, in the packer
        r.filter_size = 1.2                       # Blender default; keeps edges crisp
        if engine == "CYCLES":
            scene.cycles.device = "CPU"
            scene.cycles.samples = samples
            scene.cycles.use_denoising = True
            scene.cycles.film_transparent_glass = False
        else:
            scene.eevee.taa_render_samples = samples
        # Factorio art is plain sRGB. AgX (Blender 4.x default) and Filmic both crush
        # highlights and desaturate, which reads as washed-out next to stock sprites.
        try:
            scene.view_settings.view_transform = "Standard"
            scene.view_settings.look = "None"
        except Exception as e:                     # older/newer OCIO configs
            print("WARN could not set view transform:", e)
        scene.display_settings.display_device = "sRGB"
        return res

    def setup_camera(scene, canvas_tiles):
        """Orthographic, 45 degrees elevation, aimed at the world origin.

        Blender camera at rotation_euler=(45deg,0,0) looks along (0, sin45, -cos45) with up
        (0, cos45, sin45). Screen-down for a point becomes -(Y*cos45 + Z*sin45), which is
        Factorio's -(north + up) * 0.7071 exactly - that equality is what pins 45 degrees.
        """
        cam_data = bpy.data.cameras.new("factorio_cam")
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = canvas_tiles
        cam_data.sensor_fit = "HORIZONTAL"     # ortho_scale means the WIDTH, whatever the aspect
        cam_data.clip_start = 0.01
        cam_data.clip_end = 1000.0
        cam = bpy.data.objects.new("factorio_cam", cam_data)
        scene.collection.objects.link(cam)
        d = 100.0
        cam.location = (0.0, -d * K, d * K)     # back off along the view axis, origin centred
        cam.rotation_euler = (math.radians(45.0), 0.0, 0.0)
        scene.camera = cam
        return cam

    def setup_sun(scene, energy=3.0, angle_deg=1.0):
        """Sun matching the stock shadow direction: 45 degrees up, due west.

        The light TRAVELS toward SUN_AZIMUTH_DEG, so the sun sits on the opposite bearing.
        `angle` is the angular diameter - stock shadows are not razor sharp."""
        sd = bpy.data.lights.new("sun", type="SUN")
        sd.energy = energy
        sd.angle = math.radians(angle_deg)
        sun = bpy.data.objects.new("sun", sd)
        scene.collection.objects.link(sun)
        e, n, u = light_direction_enu()          # direction the light travels, ENU tiles
        d = mathutils.Vector((e, n, u))
        sun.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
        sun.location = (0.0, 0.0, 20.0)
        return sun

    def add_shadow_catcher(scene, size_tiles):
        bpy.ops.mesh.primitive_plane_add(size=size_tiles * 2, location=(0, 0, 0))
        plane = bpy.context.active_object
        plane.name = "shadow_catcher"
        plane.is_shadow_catcher = True
        return plane

    def render_rotations(scene, subject, out_dir, count=64, counterclockwise=False,
                         prefix="frame"):
        os.makedirs(out_dir, exist_ok=True)
        paths = []
        for i in range(count):
            subject.rotation_euler = (0.0, 0.0,
                                      model_z_rotation(i, count, counterclockwise))
            p = os.path.join(out_dir, "%s_%02d.png" % (prefix, i))
            scene.render.filepath = p
            bpy.ops.render.render(write_still=True)
            paths.append(p)
        return paths


# --------------------------------------------------------------------------------------
# Provenance you can re-run. `--verify` re-measures both constants off the installed game's
# own PNGs, so the numbers in the docstring above are checkable rather than asserted.

FACTORIO_DATA = "/Applications/factorio.app/Contents/data/"


def _sheet_extents(path, w, h, shift_tiles, count=64, line_length=8, alpha=10):
    """Per-frame alpha bbox of a sprite sheet, in tiles from the entity origin."""
    from PIL import Image                       # uv side only; Blender has no Pillow
    im = Image.open(path).convert("RGBA")
    ppt = px_per_tile(0.5)
    out = []
    for i in range(count):
        x0, y0 = (i % line_length) * w, (i // line_length) * h
        cell = im.crop((x0, y0, x0 + w, y0 + h))
        bb = cell.getchannel("A").point(lambda v: 255 if v > alpha else 0).getbbox()
        out.append(((bb[0] - w / 2) / ppt + shift_tiles[0], (bb[2] - w / 2) / ppt + shift_tiles[0],
                    (bb[1] - h / 2) / ppt + shift_tiles[1], (bb[3] - h / 2) / ppt + shift_tiles[1]))
    return out


def verify_against_stock_art():
    """Re-derive LIGHT_RUN_X from the spidertron and the flamethrower turret. Returns True
    on pass. Needs Factorio installed and Pillow; skips (pass) if the game is missing."""
    ppt = px_per_tile(0.5)
    if not os.path.isdir(FACTORIO_DATA):
        print("SKIP  Factorio not installed at %s" % FACTORIO_DATA)
        return True
    ok = True

    # --- 1. spidertron body vs shadow: two zero-parameter predictions ------------------
    t = FACTORIO_DATA + "base/graphics/entity/spidertron/torso/"
    body = _sheet_extents(t + "spidertron-body.png", 132, 138, (0 / 32, -19 / 32))
    shad = _sheet_extents(t + "spidertron-body-shadow.png", 192, 94, (26 / 32, 0.5 / 32))
    R = max(max(abs(f[0]) for f in body), max(abs(f[1]) for f in body))
    bN = min(f[2] for f in body); bS = max(f[3] for f in body)
    sW = min(f[0] for f in shad); sE = max(f[1] for f in shad)
    # The union over 64 rotations is a solid of revolution r(z) by construction, so
    # max(r - z) and max(r + z) come straight off the body sheet's south and north edges.
    m_lo, m_hi = bS / K, -bN / K
    z_lo, z_hi = R - m_lo, m_hi - R          # heights of those rings IF they are the widest
    pW, pE = -(R - z_lo * LIGHT_RUN_X), R + z_hi * LIGHT_RUN_X
    eW, eE = (sW - pW) * ppt, (sE - pE) * ppt
    print("spidertron swept torso: R %.4f  max(r-z) %.4f  max(r+z) %.4f   (BODY sheet only)"
          % (R, m_lo, m_hi))
    print("  shadow west  predicted %+.4f  measured %+.4f  err %+.2f px" % (pW, sW, eW))
    print("  shadow east  predicted %+.4f  measured %+.4f  err %+.2f px" % (pE, sE, eE))
    if abs(eW) > 1.5 or abs(eE) > 4.0:
        print("  FAIL shadow edges do not follow from the body sheet at this LIGHT_RUN_X"); ok = False

    # --- 2. flamethrower gun vs its shadow: absolute, because the muzzle height is shipped
    g = FACTORIO_DATA + "base/graphics/entity/flamethrower-turret/"
    Z = 7.10942 / 4                  # fire.lua gun_tip_raised.z / units_per_tile
    gun = _sheet_extents(g + "flamethrower-turret-gun.png", 158, 128, (-1 / 32, -25 / 32), alpha=32)
    gsh = _sheet_extents(g + "flamethrower-turret-gun-shadow.png", 182, 116, (31 / 32, -1 / 32), alpha=32)
    east = [(gsh[i][1] - gun[i][1]) for i in range(44, 53)]   # barrel points east here
    dx = sum(east) / len(east)
    print("flamethrower gun: east-extent smear over the 9 east-pointing frames %.4f tiles" % dx)
    for rho in (0.10, 0.16):
        print("    muzzle rim radius %.2f -> z_rim %.3f -> Lx %.3f" % (rho, Z - 0.638 * rho, dx / (Z - 0.638 * rho)))
    lo, hi = dx / (Z - 0.638 * 0.16), dx / Z
    if not (lo - 0.08 <= LIGHT_RUN_X <= hi + 0.08):
        print("  FAIL LIGHT_RUN_X %.3f outside the rim-radius band %.3f..%.3f" % (LIGHT_RUN_X, hi, lo)); ok = False

    print("VERIFY %s   (LIGHT_RUN_X = %.4f, LIGHT_RUN_Y = %.4f)"
          % ("PASS" if ok else "FAIL", LIGHT_RUN_X, LIGHT_RUN_Y))
    return ok


def _main():
    import sys
    if "--verify" in sys.argv:
        return 0 if verify_against_stock_art() else 1
    print("Factorio camera: orthographic, %.1f deg elevation, %.0f source px per tile at scale 0.5"
          % (CAMERA_ELEVATION_DEG, px_per_tile(0.5)))
    print("  projection constant K = %.13f   (core/lualib/math3d.lua)" % K)
    print("  north-south and height both foreshorten to %.2f px per tile" % (px_per_tile(0.5) * K))
    print("  sun: run (%.3f east, %.3f south) per tile of height, elevation %.1f deg, "
          "shadow bearing %.0f deg" % (LIGHT_RUN_X, LIGHT_RUN_Y, SUN_ELEVATION_DEG, SUN_AZIMUTH_DEG))
    print("  light travels (east, north, up) = (%+.4f, %+.4f, %+.4f)" % light_direction_enu())
    print()
    print("%-34s %10s %10s" % ("world point (east, north, up) tiles", "px right", "px down"))
    for pt in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 1.5)):
        u, v = project(*pt)
        su, sv = project_shadow(*pt)
        print("%-34s %10.2f %10.2f      shadow %8.2f %8.2f" % (str(pt), u, v, su, sv))
    print()
    print("frame 0 faces north; frame 16 is %.2f turns clockwise (%s)"
          % (orientation_of_frame(16), "east"))
    print("model z rotation for frame 16: %.4f rad" % model_z_rotation(16))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main())
