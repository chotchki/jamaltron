# Contributing

You cannot regenerate a sprite from a clone of this repo - read this part first, it is the unusual one. Jamal's body is rendered from a 3D model I bought, and keeping that model out of git is a condition of the license I bought it under, so `assets/source/` is gitignored and there is nothing in the tree for Blender to open. That is not a missing-file bug and it is not secrecy. See [Sprites need your own copy of the model](#sprites-need-your-own-copy-of-the-model).

Everything else in the repo is normal, and most of it never touches the model.

## What you can work on without the model

- The Lua. `mod/jamaltron/prototypes/` is the data stage, `mod/jamaltron/scripts/` the runtime (the body swap, speech, the jump, the leg break, the flamethrower's lines). Both Lua gates run against a plain clone.
- The Python and the shell tooling under `tools/` - the sprite linter, the art harness's config resolution and sheet math, the camera projection, the line generator, the smoke and build scripts. The ~830-test suite needs neither Blender nor the model: the render-side math is split out on purpose so it tests with `bpy` nowhere in the loop.
- The line catalog, `character/lines.md`. Weights, tiers, pools, chains, a line that reads wrong over a walking vehicle. Every string the mod speaks lives there - see [The catalog is the source](#the-catalog-is-the-source-scriptslineslua-is-generated).
- Docs, including this one, and [tools/README.md](tools/README.md), which owns the Python and Blender detail.
- Bug reports and playtest findings. Genuinely useful, because the playtest checklist in PLAN.md includes things one person with one machine cannot really test - 2-client multiplayer, Space Age platforms, how the jump FEELS at somebody else's UPS.

[PLAN.md](PLAN.md) is the live task list (finished phases get swept to [PLAN_ARCHIVE.md](PLAN_ARCHIVE.md)) and [SPEC.md](SPEC.md) holds the what and why, including every locked decision and its reasoning. If your change belongs to a phase, say which one; if it contradicts a locked decision in SPEC.md, say that too - some have other work built on them, a few are just old.

## Sprites need your own copy of the model

The body sprites are renders of [Animated Hammerhead Shark](https://www.renderhub.com/pig-scales-studio/animated-hammerhead-shark) by Pig Scales Studio, bought on RenderHub under an Extended Use License. That license lets renders ship inside a larger work (this mod). It does not let the model itself be redistributed, which is exactly why `assets/source/` is gitignored - the gitignore IS the compliance mechanism, not a tidiness preference.

So to render, buy the model (it was $10 when I bought it; [tools/README.md](tools/README.md) covers unpacking it so he renders textured). Then point the harness at your copy, because nothing assumes a path inside the repo:

```sh
export JAMALTRON_BLEND=/path/to/HAMMERHEAD.blend     # or pass --blend PATH per run
uv run --directory tools python render/art.py --compare
```

Without it `art.py` exits with `model not found: ...` and names both flags. Renders run headless (`Blender -b`) from a script, never the GUI, so any sheet can be re-rendered from scratch. They land in the gitignored `render-out/`; nothing is ever promoted into `mod/jamaltron/graphics/` for you.

If you cannot buy it, you can still do art work: `--show` prints the fully resolved config and every derived number without rendering; the sheet-layout and mount-coverage math is unit tested against the game's own shipped art; a change to a knob's default in `render/jamaltron.toml` is reviewable as a diff. Send the change and I will render it.

## Never put model files in a pull request

No `.blend`, `.fbx`, `.dae`, `.obj`, no texture archives, no packed-texture .blend, nothing derived from the mesh except flattened 2D renders. `.gitignore` covers `assets/source/`, but `git add -f` beats a gitignore and a file committed once is in the history forever - a takedown does not reach forks.

This is a real constraint, not a preference. RenderHub's sharing clause does permit handing the model to a collaborator working on the same project - but it makes ME responsible for what that collaborator then does with it. So model files moving through a public PR are not a paperwork problem, they are my license on the line, and that license is what makes shipping Jamal's sprites legal at all. If we do end up needing you to have the model, that conversation happens by mail and the file never touches git.

The book text has the same shape for a different reason: `character/extracts/` and the per-book quote banks under `character/profiles/` are gitignored because they are Matt Dinniman's prose. Distilled profiles and the tagged catalog ship; raw extracts never do.

## Two licenses, and you need to know which half you are touching

- Code is MIT - the Lua, the Python, the shell, the config. [LICENSE](LICENSE), with a scope preamble saying exactly this.
- `mod/jamaltron/graphics/` is NOT MIT, and neither is `mod/jamaltron/thumbnail.png`. Both are covered by [the graphics LICENSE](mod/jamaltron/graphics/LICENSE) (the thumbnail sits at the mod root only because Factorio reads it from nowhere else): those renders travel as part of this mod (forks included) and may not be extracted and redistributed as standalone art. The Extended Use License grants no right to sublicense, so MIT rights over the sprites are not mine to hand you.

A PR that adds or replaces a PNG under `graphics/` (or the thumbnail) is therefore an asset PR, not a code PR. The carve-out travels with the file, and the gate is the COMMIT, not the release - git history is permanent, so a sprite committed under the wrong license cannot be un-granted later. If you contribute original art you drew yourself, say so in the PR and it gets its own notice rather than being swept under either of the two above.

## The dev loop

Factorio loads the `tools/link_mod.sh` symlink in place (install and `tools/build.sh` are in the [README](README.md#install)), so the cycle is edit, smoke test, relaunch. `tools/play.sh --new` runs the real game on an isolated profile for playtesting, never touching yours - [tools/README.md](tools/README.md) has it and its console commands.

CI runs on every PR, but it only covers what a runner CAN check - `.github/workflows/ci.yml`, whose header says what is left out and why. It runs the Python suite (with the pure-Lua unit suites inside it, under `lua5.2` because that is Factorio's dialect and your laptop's `lua` probably is not), the sprite gate and both halves of `tools/lint.sh` as separate jobs (the type check generates its own defs first, pinned to the same fmtk and API version as yours). It CANNOT run anything that needs the game or the model: `tools/smoke.sh`, the harnesses, the renders. Those run on your machine or not at all, and CI passing says nothing about them.

- `tools/smoke.sh` - the every-edit gate. Loads the mod headless three times in a THROWAWAY profile that cannot touch your real Factorio install: `--create` base-only, `--create` with Space Age, then `--benchmark` for 60 ticks (the only stage that reaches `on_load` and `on_tick`). Exit status alone is not the verdict - Factorio exits 0 on a mod it silently SKIPPED - so each stage also fails on any Error or Warning line and on the mod missing from the load order. Stage 0 greps literal `__jamaltron__/...` asset paths out of the Lua and JSON and checks they exist on disk (literal paths only, and existence only - headless never loads an image, so nothing here notices a sheet that is the wrong SIZE; that is `lint_sprites.py`'s job). Needs a real Factorio binary; override with `FACTORIO_BIN=/path/to/factorio`. `--harness DIR` adds a scripted in-engine run (the harnesses under `tools/harness/`, listed in tools/README.md).
- `tools/lint.sh` - both Lua gates: `luacheck` over `mod/` against a Factorio-shaped Lua 5.2 sandbox, and `lua-language-server --check .` at `--checklevel=Warning`. `.luacheckrc` encodes the sandbox (`io`, `os` and `coroutine` are gone, `debug` and `package` cut down to a couple of members), the engine's additions and the per-stage globals, so touching `game` in data.lua is caught as the crash it would be. Run it from the REPO ROOT - `.luarc.json`'s library paths are workspace-relative, and aiming the language server at `./mod` with `--configpath` instead invents 24 undefined-global warnings that are nothing but unresolved paths talking. The type gate stops outright if `.ls-defs/factorio/` is absent, which is every fresh clone - see [the type definitions](#the-type-definitions-are-not-in-git). A missing binary SKIPS its gate with a message, but both gates skipping is a failure - a pass that checked nothing is worse than a failure. `--only luacheck` / `--only types` runs one gate and makes it MANDATORY (a missing binary fails instead of skipping); that is what CI calls, so a failing Lua job reproduces with the exact same line locally.
- `uv run --directory tools pytest` - the Python side. `--directory`, never `--project`: the latter does not chdir, so pytest never reads `tools/pyproject.toml` and dies with `ModuleNotFoundError: No module named 'render'`. No Blender or model required; the handful of tests that read the installed game's own sprites skip cleanly when Factorio is not on the machine, and the four that render the real rig skip without Blender and the model. Every hash pin is taken on the SHIPPED model's digest (`shipped_model` in `tools/tests/conftest.py`), never off the file on disk, so a runner with no model hashes exactly what your machine does - `JAMALTRON_TEST_NO_MODEL=1` runs the suite the way a runner sees the model (missing), and it has to pass both ways. The Lua suites go through one resolver in the same conftest: `JAMALTRON_LUA=lua5.2` names the interpreter the way CI does, and a named one that is not on PATH FAILS every Lua suite rather than skipping them.
- `tools/lint_sprites.py` - the sprite gate, and the ONLY one there can be. MEASURED: Factorio cannot validate sprite sheets in any scriptable mode - `--dump-data` and `--create` are sprite-blind on both the mac and headless builds (exit 0 on a missing PNG AND on a declared-vs-actual size mismatch); the headless linux build ships zero PNGs, so it can never check art at all; the only rasterizing mode is mac-only behind a modal dialog that hangs the process. So this stdlib-only script reads PNG IHDR headers and cross-checks them against the declared geometry. Two modes, and the split matters: default tolerates padded sheets and is what you point at base-derived declarations (11 of Wube's own 4424 shipped declarations are padded rather than torn, so `--strict` fails on stock's leg sheets with 7 warnings, and that is stock's business, not a bug); `--strict` is for OUR generated sheets, which are always exact.

  ```sh
  python3 tools/lint_sprites.py --strict --mod-root jamaltron=mod/jamaltron mod/jamaltron/graphics/sprites.json
  ```

Typed Lua is the closest thing to a test the data stage offers - nothing else notices a renamed prototype still pointing at a base-game leg - so do not skip `lint.sh` because the change "is only data".

### The type definitions are not in git

`.ls-defs/factorio/` is 1156 generated files and 7 MB, so it is gitignored. A fresh clone therefore gets a `.luarc.json` naming two paths that do not exist and NO editor type support - the language server still starts, it just knows nothing about `data.raw`, `LuaEntity` or any prototype field. Run this once after cloning, and again after a game update:

```sh
tools/gen-defs.sh            # --check fails if the tree on disk is not what FMTK emits today
```

It wraps [FMTK](https://github.com/justarandomgeek/vscode-factoriomod-debug), preferring the API json your installed game ships (docs that came with the binary cannot drift from the game you launch) and falling back to `lua-api.factorio.com` when there is no game on the machine, which is the CI path. Use the fmtk version CI pins (`FMTK_VERSION` in ci.yml, 2.0.8 against Factorio 2.1.17 today): npm's latest emits a different bundle from the same API json, and a type check against different defs is a different type check.

`.ls-defs/supplement/` is hand-written and IS committed. It declares the `feature_flags` global, which the FMTK bundle gives a type but never declares - regenerating the defs does not touch it.

### The plan hooks are optional

`.claude/settings.json` wires four hooks to [claude-plan-bridge](https://github.com/chotchki/claude-plan-bridge), which keeps PLAN.md and an agent's task list in sync and reconciles hand-edits between turns (`cargo install claude-plan-bridge`). Without it the hooks fail, harmlessly and noisily - delete the file or install the binary.

### Layout

Only the parts a fresh clone does not explain (everything else is named for what it holds):

```
mod/jamaltron/       the mod - what gets symlinked and what gets zipped
  graphics/          rendered sprites and icons - NOT MIT, see its LICENSE
character/extracts/  raw book passages. gitignored, never committed
assets/source/       the bought 3D model. gitignored, never committed
.ls-defs/factorio/   generated Lua type defs. gitignored (supplement/ beside it is hand-written and committed)
dist/                build.sh output. gitignored
render-out/          art.py, shot.sh and video output (takes + deliverables). gitignored
```

## The catalog is the source, `scripts/lines.lua` is generated

`character/lines.md` is the single source of truth for every string the mod speaks. `mod/jamaltron/scripts/lines.lua` and `locale/en/jamaltron-lines.cfg` are GENERATED from it by `tools/gen_lines.py`, and both carry a header saying so.

Editing a generated file is the wrong edit. The next generator run eats it silently, and the diff will not tell you which side was right. Change the catalog row and regenerate:

```sh
uv run --directory tools python gen_lines.py --check   # validate the catalog, report whether the pair is current; writes nothing
uv run --directory tools python gen_lines.py           # the same, then write both files
```

The test suite (so CI) fails a stale pair.

Two things to know before you add a line: every row carries twelve columns (channel, tier, weight, anti-repeat group, gates, chains, provenance and more - the file's own "how to read the table" section is the machine contract), and every row tagged `verbatim` has been machine-verified as an exact contiguous substring of the gitignored extracts. A quote nobody can verify is a fabrication and gets deleted rather than fixed, so a new `verbatim` row needs the book text to check it against. Lines you wrote yourself are welcome and tag as `original` - that column exists so the fair-use surface stays countable instead of vibes.

Line ids are renumberable until just before release, when they freeze: a shipped id is a locale key and a key in players' saves, so cutting one after that leaves a permanent gap.
