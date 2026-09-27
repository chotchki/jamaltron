"""Shared test plumbing: the one Lua resolver, the shipped-model stamp, and a runner's-eye view.

THE LUA RESOLVER. Every suite that shells out to Lua takes the `lua` fixture (or
`lua_optional` for a bonus check on top of a Python test). $JAMALTRON_LUA names the
interpreter and makes it MANDATORY: a name that resolves to nothing FAILS, never skips. CI
sets it to lua5.2 (Factorio's dialect), so a runner that loses its Lua fails instead of
passing on skips. Unset, it is `lua` then `luajit`; a machine with neither skips.
test_ci.py fails any suite that goes back to `shutil.which("lua")` on its own.

THE SHIPPED MODEL. Hash pins are over configs whose `model.blend` is the SHIPPED model's
content digest, substituted in (`shipped_model`), never the file on disk: the model is bought,
gitignored and absent on every runner, where the digest reads "absent" and every pin moves.
artconfig.hashable() passes an already-digested value through (the property that lets a
stamp read off a PNG re-hash to itself), so a pin holds on a runner and still catches a
moved knob with or without the model.

A RUNNER'S VIEW. JAMALTRON_TEST_NO_MODEL=1 makes this machine look like a CI runner for the
model: anything that resolves under the repo's assets/ reads as missing, and $JAMALTRON_BLEND
is dropped. It redirects artconfig.blend_path (the one choke point every digest and every
Blender launch goes through) and never touches the file itself.
"""

import os
import shutil

import pytest

from render import artconfig as ac

#: What the shipped sheets carry as `model.blend`, read off their own PNG text chunks: the
#: sha256 of the bought HAMMERHEAD.blend, truncated as artconfig.blend_digest truncates it.
SHIPPED_BLEND_DIGEST = "sha256:0431897ccc701717"

LUA_ENV = "JAMALTRON_LUA"
NO_MODEL_ENV = "JAMALTRON_TEST_NO_MODEL"


def _runner_view():
    """Install the runner's view of the model when asked. Runs at conftest import, before
    any test module, so module-level skipifs see it too."""
    if not os.environ.get(NO_MODEL_ENV):
        return
    os.environ.pop(ac.BLEND_ENV, None)
    real, assets = ac.blend_path, ac.REPO / "assets"

    def blend_path(cfg):
        p = real(cfg)
        return assets / "not-on-a-runner" / p.name if p.is_relative_to(assets) else p

    ac.blend_path = blend_path


_runner_view()


def lua_interpreter():
    """The interpreter path, or None when none is named and neither lua nor luajit exists.
    A NAMED interpreter that is missing fails the calling test outright."""
    named = os.environ.get(LUA_ENV, "")
    if named:
        found = shutil.which(named)
        if found is None:
            pytest.fail("%s=%r is not on PATH - a named interpreter may not skip"
                        % (LUA_ENV, named))
        return found
    return shutil.which("lua") or shutil.which("luajit")


@pytest.fixture
def lua():
    """A Lua interpreter or the test does not run: fail when $JAMALTRON_LUA names a missing
    one, skip when it is unset and there is none."""
    found = lua_interpreter()
    if found is None:
        pytest.skip("no lua or luajit on PATH (%s=<interpreter> makes this a failure)" % LUA_ENV)
    return found


@pytest.fixture
def lua_optional():
    """Same resolution, but None instead of a skip - for a Lua check layered on a test whose
    Python half is worth running anyway. A named-but-missing interpreter still fails."""
    return lua_interpreter()


@pytest.fixture
def shipped_model():
    """cfg -> the same cfg on the shipped model's digest. Every hash pin goes through this."""
    return lambda cfg: dict(cfg, **{"model.blend": SHIPPED_BLEND_DIGEST})
