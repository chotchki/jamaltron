# Contributing

**Read this part first, because it is the unusual one: you cannot regenerate a sprite from a clone of this repo.** Jamal's body is rendered from a 3D model I bought, and keeping that model out of git is a condition of the license I bought it under - so `assets/source/` is gitignored and there is nothing in the tree for Blender to open. That is not a missing-file bug and it is not secrecy. See [Sprites need your own copy of the model](#sprites-need-your-own-copy-of-the-model).

Everything else in the repo is normal. Most of it does not touch the model at all.

## What you can work on without the model

- **The Lua.** `mod/jamaltron/prototypes/` is the whole mod today; `mod/jamaltron/scripts/` is where the swap, the speech and the jump land in Phases D and E. Both Lua gates run against a plain clone.
- **The Python and the shell tooling** under `tools/` - the sprite linter, the art harness's config resolution and sheet math, the camera projection, the smoke and build scripts. The test suite is 188 tests and needs neither Blender nor the model: the render-side math is deliberately split out so it tests with `bpy` nowhere in the loop.
- **The line catalog**, `character/lines.md`. Weights, tiers, pools, chains, a line that reads wrong over a walking vehicle. This is the file the mod's dialogue actually lives in - see [The catalog is the source](#the-catalog-is-the-source-scriptslineslua-is-generated).
- **Docs**, including this one, and [tools/README.md](tools/README.md), which owns the Python and Blender detail.
- **Bug reports and playtest findings.** Genuinely useful, because PLAN F.2's checklist includes things one person with one machine cannot really test - 2-client multiplayer, Space Age platforms, how the jump FEELS at somebody else's UPS.

[PLAN.md](PLAN.md) is the live task list and [SPEC.md](SPEC.md) holds the what and why, including every locked decision and the reasoning behind it. If your change belongs to a phase, say which one; if it contradicts a locked decision in SPEC.md, say that too - some of those are load-bearing and a few are just old.

## Sprites need your own copy of the model

The body sprites are renders of [Animated Hammerhead Shark](https://www.renderhub.com/pig-scales-studio/animated-hammerhead-shark) by Pig Scales Studio, bought on RenderHub under an Extended Use License. That license lets renders ship inside a larger work (this mod). It does not let the model itself be redistributed, which is exactly why `assets/source/` is gitignored - the gitignore IS the compliance mechanism, not a tidiness preference.

So: to render, buy the model - it was $10 when I bought it. Then point the harness at your copy, because nothing assumes a path inside the repo:

```sh
export JAMALTRON_BLEND=/path/to/HAMMERHEAD.blend     # or pass --blend PATH per run
uv run --directory tools python render/art.py --compare
```

Without it `art.py` exits with `model not found: ...` and tells you both flags. Renders land in the gitignored `render-out/`; nothing is ever promoted into `mod/jamaltron/graphics/` for you.

If you cannot buy it, you can still do art work: `--show` prints the fully resolved config and every derived number without rendering, the sheet-layout and mount-coverage math is unit tested against the game's own shipped art, and a change to a knob's default in `render/jamaltron.toml` is reviewable as a diff. Send the change and I will render it.

## Never put model files in a pull request

No `.blend`, `.fbx`, `.dae`, `.obj`, no texture archives, no packed-texture .blend, nothing derived from the mesh except flattened 2D renders. `.gitignore` covers `assets/source/`, but `git add -f` beats a gitignore and a file committed once is in the history forever - a takedown does not reach forks.

**This is a real constraint rather than a preference, and the reason is worth knowing.** RenderHub's sharing clause does permit handing the model to a collaborator working on the same project - but it makes ME responsible for what that collaborator then does with it. So model files moving through a public PR are not a paperwork problem, they are my license on the line, and the license is what makes shipping Jamal's sprites legal at all. If we do end up needing you to have the model, that conversation happens by mail and the file never touches git.

The book text has the same shape for a different reason: `character/extracts/` and the per-book quote banks under `character/profiles/` are gitignored because they are Matt Dinniman's prose. Distilled profiles and the tagged catalog ship; raw extracts never do.

## Two licenses, and you need to know which half you are touching

- **Code is MIT** - the Lua, the Python, the shell, the config. [LICENSE](LICENSE), with a scope preamble saying exactly this.
- **`mod/jamaltron/graphics/` is NOT MIT.** It carries [its own LICENSE](mod/jamaltron/graphics/LICENSE): those sprites travel as part of this mod (forks included) and may not be extracted and redistributed as standalone art. The Extended Use License grants no right to sublicense, so MIT rights over the sprites are not mine to hand you.

A PR that adds or replaces a PNG under `graphics/` is therefore an asset PR, not a code PR. The carve-out travels with the file, and the gate is the COMMIT, not the release - git history is permanent, so a sprite committed under the wrong license cannot be un-granted later. If you contribute original art you drew yourself, say so in the PR and it gets its own notice rather than being swept under either of the two above.

## The dev loop

**There is no CI yet** (PLAN F.1 is the GitHub Actions job), so these run on your machine or they do not run at all. Nothing else is checking your PR.

- **`tools/smoke.sh`** - the every-edit gate. Loads the mod headless three times in a THROWAWAY profile that cannot touch your real Factorio install: `--create` base-only, `--create` with Space Age, then `--benchmark` for 60 ticks (which is the only stage that reaches `on_load` and `on_tick`). Exit status alone is not the verdict - Factorio exits 0 on a mod it silently SKIPPED - so each stage also fails on any Error or Warning line and on the mod missing from the load order. Stage 0 greps literal `__jamaltron__/...` asset paths out of the Lua and JSON and checks they exist on disk (literal paths only, and existence only - headless never loads an image, so nothing here notices a sheet that is the wrong SIZE; that is `lint_sprites.py`'s job). Needs a real Factorio binary; override with `FACTORIO_BIN=/path/to/factorio`.
- **`tools/lint.sh`** - both Lua gates: `luacheck` over `mod/` against a Factorio-shaped Lua 5.2 sandbox, and `lua-language-server --check .` at `--checklevel=Warning`. **Run it from the repo root** - `.luarc.json`'s library paths are workspace-relative, and pointing the language server at `./mod` invents 24 undefined-global warnings that are nothing but unresolved paths talking. The type gate stops outright if `.ls-defs/factorio/` is absent, which is the state of every fresh clone (the defs are 1156 generated files and gitignored): run `tools/gen-defs.sh` once. A missing binary SKIPS its gate with a message, but both gates skipping is a failure - a green that checked nothing is worse than a red.
- **`uv run --directory tools pytest`** - the Python side. `--directory`, never `--project`: the latter does not chdir, so pytest never reads `tools/pyproject.toml` and dies with `ModuleNotFoundError: No module named 'render'`. 188 tests today, no Blender or model required; the handful that read the installed game's own sprites skip cleanly when Factorio is not on the machine.
- **`tools/lint_sprites.py`** - the sprite gate, and the ONLY one there can be. MEASURED: Factorio cannot validate sprite sheets in any scriptable mode - `--dump-data` and `--create` are sprite-blind on both the mac and headless builds (exit 0 on a missing PNG *and* on a declared-vs-actual size mismatch), the headless linux build ships zero PNGs so it can never check art at all, and the only rasterizing mode is mac-only behind a modal dialog that hangs the process. So this stdlib-only script reads PNG IHDR headers and cross-checks them against the declared geometry. Two modes, and the split matters: **default** tolerates padded sheets and is what you point at base-derived declarations (11 of Wube's own 4424 shipped declarations are padded rather than torn, so `--strict` fails on stock's leg sheets with 7 warnings and that is stock's business, not a bug); **`--strict`** is for OUR generated sheets, which are always exact.

  ```sh
  python3 tools/lint_sprites.py --strict --mod-root jamaltron=mod/jamaltron build/sprites.json
  ```

`tools/link_mod.sh` symlinks the working tree into your mods directory and `tools/build.sh --verify` zips and re-smokes the result; [README.md](README.md#dev-loop) has the details on both. Typed Lua is the closest thing to a test the data stage offers - nothing else notices a renamed prototype still pointing at a base-game leg - so do not skip `lint.sh` because the change "is only data".

## The catalog is the source, `scripts/lines.lua` is generated

`character/lines.md` is the single source of truth for every string the mod speaks. `mod/jamaltron/scripts/lines.lua` and `locale/en/jamaltron-lines.cfg` are GENERATED from it by `tools/gen_lines.py` (PLAN B.5, not landed yet - so neither generated file exists in the tree today), and both will carry a header saying so.

**Editing a generated file is the wrong edit.** The next generator run eats it silently, and the diff will not tell you which side was right. Change the catalog row and regenerate.

Two things to know before you add a line: every row carries twelve columns (channel, tier, weight, anti-repeat group, gates, chains, provenance and more - the file's own "how to read the table" section is the machine contract), and every row tagged `verbatim` has been machine-verified as an exact contiguous substring of the gitignored extracts. A quote nobody can verify is a fabrication and gets deleted rather than fixed, so a new `verbatim` row needs the book text to check it against. Lines you wrote yourself are welcome and tag as `original` - that column exists so the fair-use surface stays countable instead of vibes.
