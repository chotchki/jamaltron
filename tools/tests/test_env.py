"""Environment guards. These fail loudly if the toolchain drifts from what
A.5 established, rather than letting a Phase C script discover it at render time."""

import ast
import pathlib
import sys

REPO_TOOLS = pathlib.Path(__file__).resolve().parents[1]


def test_python_is_311_to_match_blender():
    # Blender 4.4.3 bundles CPython 3.11.11. render/spritesheet.py is imported by
    # both interpreters, so a version skew here is a real bug, not pedantry.
    assert sys.version_info[:2] == (3, 11), sys.version


def test_pillow_is_installed(tmp_path):
    # C.7's packer needs it. uv side only -- Blender does NOT bundle Pillow.
    from PIL import Image

    p = tmp_path / "frame.png"
    Image.new("RGBA", (132, 138), (0, 0, 0, 0)).save(p)
    assert Image.open(p).size == (132, 138)


def test_spritesheet_stays_stdlib_only():
    """The shared module must import in Blender, which has no Pillow and no venv.

    Anything not in the stdlib here breaks every Blender-side script that
    imports it, and it breaks at render time, silently, on somebody else's
    machine. Cheaper to assert it.
    """
    src = (REPO_TOOLS / "render" / "spritesheet.py").read_text()
    imported = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    offenders = imported - sys.stdlib_module_names
    assert not offenders, f"non-stdlib imports in render/spritesheet.py: {sorted(offenders)}"
