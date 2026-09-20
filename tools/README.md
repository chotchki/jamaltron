# tools/

Python side of the mod: Blender render driver, sprite packer, line-catalog codegen.
A `uv` project, not a package - nothing here is ever published, so `pyproject.toml`
sets `package = false` and carries no build backend.

Python is pinned to **3.11** (`.python-version`) to match the **3.11.11** CPython
that Blender 4.4.3 bundles. `uv.lock` is committed; `uv sync --frozen` rebuilds the
exact venv.

## Commands

| command | what it does |
| --- | --- |
| `cd tools && uv sync` | create `.venv` and install Pillow + pytest |
| `cd tools && uv run pytest` | run the unit tests |
| `uv run --directory tools pytest` | same, from the repo root |
| `uv lock --check` | non-zero if `pyproject.toml` and `uv.lock` have drifted |
| `Blender -b --python tools/render/blender_check.py` | prove the Blender entry point still works |

`Blender` is `/Applications/Blender.app/Contents/MacOS/Blender` on this machine.
`blender_check.py` prints the Blender and bundled-Python versions plus the usable
render engines, and exits non-zero if Cycles is missing.

**Trap:** `uv run --project tools pytest` FAILS with `ModuleNotFoundError: No module
named 'render'`. `--project` does not change directory, so pytest takes the repo root
as rootdir, never reads `tools/pyproject.toml` as its config, and silently ignores
`pythonpath = ["."]`. Use `--directory tools` (which does chdir) or plain `cd tools`.

**Second trap:** every entry-point script under `render/` opens with

```python
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
```

because Python puts the SCRIPT's directory on `sys.path[0]`, never the CWD, and
`package = false` means there is no installed `render` to fall back on. Blender does
the same thing to `--python` scripts. Those two lines cannot be factored into a helper
module - importing the helper is the thing that needs the path fixed. Repeat them.

## The Blender boundary

A script running inside Blender uses **Blender's** interpreter and does **not** see
`tools/.venv`. Blender 4.4.3 bundles numpy 1.26.4, requests and zstandard. It does
**not** bundle Pillow. So the split is enforced by convention:

| side | may import | runs as |
| --- | --- | --- |
| Blender | stdlib, `bpy`, bundled numpy | `Blender -b <file> --python render/x.py -- args` |
| uv | stdlib, Pillow | `uv run python render/x.py` |
| both | stdlib only (`render/spritesheet.py`) | either |

Data crosses as JSON, either a sentinel line on stdout or a path handed in after `--`.
The payoff is `render/spritesheet.py`: the projection and sheet math, the part most
likely to be wrong, gets unit tests with Blender nowhere in the loop.

Injecting the venv into Blender does work (`sys.path.append('tools/.venv/lib/python3.11/site-packages')`,
then `from PIL import Image`) and it is the documented break-glass move if some render
pass genuinely needs Pillow inside a `bpy` context. Use `append`, not `insert(0)`, so
Blender's own numpy keeps winning. We do not build on it: it hard-couples the pipeline
to Blender's exact CPython minor, and it makes the Blender-side code untestable without
Blender.

## Rendering

**Cycles, CPU, every pass.** Not a preference:

- only Cycles honours `object.is_shadow_catcher`. The attribute exists under EEVEE
  Next too, so a naive script looks like it works, but EEVEE renders the catcher plane
  fully opaque across the frame. Factorio's `shadow_animation` needs the alpha.
- Cycles CPU is also the fastest here - 0.16s/frame at 256px, vs EEVEE's 0.20s and
  Metal GPU's 39s one-time kernel compile plus a HIGHER per-frame cost. A sprite-size
  tile is pure launch overhead for a GPU.

Both numbers come off a default cube. Real geometry with textures and subsurface
scattering will cost more, possibly a lot; re-measure in C.4, including Metal GPU at
higher sample counts. The shadow-catcher requirement does not move either way.

`gpu.platform.backend_type_get()` raises `SystemError` in background mode. Do not
probe the `gpu` module headless - rendering is fine, that one call is not.

## Layout

```
pyproject.toml      deps + pytest config
.python-version     3.11, matches Blender's bundled CPython
uv.lock             committed
render/
  spritesheet.py    sheet layout math. stdlib ONLY, imported from both sides
  blender_check.py  entry point, proves headless Blender works
tests/
  test_spritesheet.py   layout math, incl. two cases checked against shipped Factorio assets
  test_env.py           python version, Pillow present, spritesheet.py still stdlib-only
smoke.sh, build.sh  shell, not part of the uv project (PLAN A.2)
```
