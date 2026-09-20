"""Prove the Phase C entry point works before Phase C depends on it.

    /Applications/Blender.app/Contents/MacOS/Blender -b --python tools/render/blender_check.py

Prints Blender's version, its bundled Python, which render engines are actually
usable, and whether render/spritesheet.py imports over there. Exits non-zero if
CYCLES is unusable -- Cycles is not a preference, it is the only engine that
honours `is_shadow_catcher`, and Factorio needs a shadow-only sheet (C.4). EEVEE
Next silently renders the catcher plane fully opaque instead.

Runs under plain `uv run python render/blender_check.py` too; it reports bpy as
absent and skips the engine probe, which is how you tell the two contexts apart.
"""

# These two lines cannot live in a helper module -- importing the helper is the
# very thing that needs sys.path fixed. Blender and `python render/x.py` both put
# THIS file's directory on sys.path[0], never tools/. Repeat them verbatim in
# every entry point under render/.
import pathlib, sys  # noqa: E401
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from render.spritesheet import MAX_SHEET_SIDE, plan_sheet  # noqa: E402

try:
    import bpy
except ImportError:
    bpy = None

# Built-ins that ship with Blender 4.4. Hardcoded on purpose: in background mode
# RenderSettings.engine.enum_items reports ONLY BLENDER_EEVEE_NEXT (measured on
# 4.4.3), so trusting the enum makes Workbench and Cycles look absent.
BUILTIN_ENGINES = ("BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH")


def usable_engines() -> list[str]:
    """Engine ids this Blender will actually accept, found by assigning them.

    Assignment is the only probe that tells the truth: the enum under-reports
    headless, and RenderEngine.__subclasses__() over-reports (it includes the
    abstract HydraRenderEngine, which has no bl_idname and cannot be set).
    """
    candidates = dict.fromkeys(BUILTIN_ENGINES)
    candidates.update(dict.fromkeys(
        e.identifier
        for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    ))
    candidates.update(dict.fromkeys(
        cls.bl_idname for cls in bpy.types.RenderEngine.__subclasses__()
        if hasattr(cls, "bl_idname")
    ))

    render = bpy.context.scene.render
    was = render.engine
    usable = []
    for name in candidates:
        try:
            render.engine = name
        except TypeError:
            continue
        usable.append(name)
    render.engine = was
    return usable


def main() -> int:
    print(f"python      {sys.version.split()[0]} ({sys.executable})")

    # The shared math has to work HERE, not just under pytest. 64 rotations of
    # the stock torso frame is the exact shape C.4 will ask for.
    lay = plan_sheet(64, 132, 138, line_length=8)
    print(f"spritesheet ok, 64 frames of 132x138 -> {lay.sheet_sizes()} cap={MAX_SHEET_SIDE}")

    if bpy is None:
        print("bpy         ABSENT (running outside Blender, engine probe skipped)")
        return 0

    print(f"blender     {bpy.app.version_string} (built {bpy.app.build_date.decode()})")

    engines = usable_engines()
    print(f"engines     {', '.join(engines)}")

    if "CYCLES" not in engines:
        print("FAIL: CYCLES unusable -- no shadow-catcher pass, C.4 is dead in the water")
        return 1

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    # CPU deliberately: measured 0.16s/frame at 256px vs Metal GPU's 39s one-time
    # kernel compile PLUS a higher per-frame cost at sprite resolutions. Re-measure
    # in C.4 on real geometry -- the crossover may move, the shadow requirement won't.
    scene.cycles.device = "CPU"
    print(f"cycles      device={scene.cycles.device} samples={scene.cycles.samples}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
