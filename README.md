# Jamaltron

A Factorio 2.1 mod adding Jamal from Matt Dinniman's *Dungeon Crawler Carl* as a spidertron variant. In the books Jamal is a hammerhead shark who ends up with a set of mechanical spider legs bolted to him, which makes him an almost unfair fit for a spidertron re-skin. He also never stops apologizing, and here that is a feature.

**Status: Phase A. It loads, there is nothing to play.** What exists is 14 prototypes - the `jamaltron` spider-vehicle, its 8 legs, remnants, a dying explosion, plus the item, recipe and technology - deepcopied off the stock spidertron family and wired tech to recipe to item to entity. It passes the headless smoke test base-only, again with Space Age and through 60 ticks, and it zips into a portal-shaped `jamaltron_0.1.0.zip` that loads the same way. (15 prototypes with Space Age on, because the DLC's `recycler` auto-generates a recycling recipe from the item. That one is wanted.)

What it does NOT have is anything that makes it Jamal. He wears the stock spidertron's sprites, says nothing and cannot jump, so right now he is a spidertron with a different name and a fish in the recipe. Everything under [The plan](#the-plan) except the clone itself is still ahead. [PLAN.md](PLAN.md) is the live task list and [SPEC.md](SPEC.md) holds the what and why.

Phase A is not closed, and the open boxes are worth knowing before you run it:

- **A.3, typing and lint.** Both linters are clean on the mod today (`no problems found` from lua-language-server, zero warnings from luacheck), but the box stays open until the whole gate is wired - and the type definitions it leans on are generated rather than committed (see [below](#the-type-definitions-are-not-in-git))
- **A.4 and A.7, does he actually walk.** Nothing visual has been checked by anyone. Headless Factorio never draws a frame, so "it loads and ticks" is the ceiling on what `--create` and `--benchmark` can prove; somebody has to launch the GUI client and look at him. The rest of the open work lives in [PLAN.md](PLAN.md)

## The plan

- **A spidertron variant.** Cloned off the stock spidertron prototype and re-skinned with sprites rendered from a real hammerhead model (64 rotations plus shadow and water-reflection passes) so the shark sits correctly on the stock legs
- **A jump, which is the entire joke.** Jamal is the literal personification of jumping the shark, so the jump is the punchline the mod exists to deliver, not a feature bolted onto a reskin. Spider-vehicles cannot jump natively so it has to be scripted - either a plain teleport or a swap to an airborne entity animated along an arc (the Jetpack mod's trick). The arc leads on those grounds, since a teleport means nothing visibly jumps and there is no shark to jump over; the spike in PLAN E.1 settles it and it is the one genuine unknown in the whole project
- **Broken legs.** Landing rolls against a break chance. Snap them and he swaps to a beached variant that flops in place and holds onto every item, every equipment slot and both seats until somebody turns up with a repair pack (bots count)
- **A flamethrower** instead of the four rocket launchers, because that is what he carries in the books
- **Apologies.** Weighted line pools per situation behind a per-player verbosity setting (quiet / normal / unbearable) so your multiplayer friends can opt out of Jamal entirely

## Install

No mod portal release yet - that is PLAN F.5, and there is little reason to want one until there is art and a jump. To run what is here, either link the working tree into your Factorio [mods directory](https://wiki.factorio.com/Application_directory):

```sh
tools/link_mod.sh            # symlink mod/jamaltron into the mods directory
tools/link_mod.sh --status   # where the link points and whether mod-list.json still parses
tools/link_mod.sh --unlink   # take it back out
```

or build the zip and drop that in the same place:

```sh
tools/build.sh --verify      # writes dist/jamaltron_<version>.zip, then loads it headless to prove it works
```

Use the script rather than a hand-rolled `ln -s`. That directory is not ours - mine holds 94 real mods and a `mod-list.json` the game rewrites on every launch - so `link_mod.sh` copies that list somewhere OUTSIDE the mods directory before touching anything, refuses to overwrite anything that is not the symlink it made itself and re-reads the list afterwards to prove it still parses and still names every mod it named before. The only write it ever performs is the one symlink, and running it twice is a no-op.

Base game 2.1 is required, Space Age is optional (`"? space-age"`). Jumping will be disabled on space platforms.

## Dev loop

Factorio loads that symlink in place, so the cycle is edit, smoke test, relaunch.

| command | what it does |
| --- | --- |
| `tools/link_mod.sh` | symlink the working tree into the mods directory (`--status`, `--unlink`) |
| `tools/smoke.sh` | the every-edit gate: headless `--create` base-only, again with Space Age, then `--benchmark` for 60 ticks, all in a throwaway profile that cannot touch your real one. Exit status is not trusted on its own - Factorio exits 0 on a mod it silently skipped, so each stage also fails on any Error or Warning line and on the mod missing from the load order |
| `tools/build.sh` | zips `mod/jamaltron` into `dist/<name>_<version>.zip`, version read straight out of info.json. `--verify` runs the finished zip back through `smoke.sh`, which is the only way to know the thing you are about to upload loads |
| `tools/gen-defs.sh` | regenerate the Factorio type definitions, see below. `--check` fails if the tree on disk is not what FMTK emits today |
| `lua-language-server --check .` | type-check the mod. Run it from the REPO ROOT: `.luarc.json`'s library paths resolve against the workspace, and aiming it at `./mod` with `--configpath` instead invents 24 undefined-global warnings that are nothing but the unresolved paths talking |
| `luacheck mod/jamaltron` | lint against a Factorio-shaped Lua 5.2. `.luacheckrc` encodes the sandbox (`io`, `os` and `coroutine` are gone, `debug` and `package` cut down to a couple of members), the engine's additions and the per-stage globals, so touching `game` in data.lua is caught here as the crash it would be |
| `uv run --directory tools pytest` | the Python side: Blender render driver, sprite packer, line generator. `--directory`, NEVER `--project` - the latter fails with `ModuleNotFoundError: No module named 'render'` because it does not chdir, so pytest never reads `tools/pyproject.toml`. [tools/README.md](tools/README.md) owns the rest of the Python and Blender detail |

Typed Lua is the closest thing to a test the data stage offers - nothing else notices a renamed prototype still pointing at a base-game leg. Sprites come out of Blender headless (`Blender -b`) driven by a script, never the GUI, so any sheet can be re-rendered from scratch.

### The type definitions are not in git

`.ls-defs/factorio/` is 1156 generated files and 7 MB, so it is gitignored. A fresh clone therefore gets a `.luarc.json` naming two paths that do not exist and NO editor type support at all - the language server still starts, it just knows nothing about `data.raw`, `LuaEntity` or any prototype field you can name. Run this once after cloning, and again after a game update:

```sh
tools/gen-defs.sh
```

It wraps [FMTK](https://github.com/justarandomgeek/vscode-factoriomod-debug), preferring the API json your installed game ships (docs that came with the binary cannot drift from the game you actually launch) and falling back to `lua-api.factorio.com` when there is no game on the machine, which is the CI path. The current tree is FMTK bundle 2.0.8 against Factorio 2.1.17.

`.ls-defs/supplement/` is hand-written and IS committed. It declares the `feature_flags` global, which the FMTK bundle gives a type but never actually declares - regenerating the defs does not touch it.

## Layout

```
mod/jamaltron/       the mod - what gets symlinked and what gets zipped
  prototypes/        entity, item, recipe, technology (the data stage)
  scripts/           empty until Phase D lands the runtime code
  locale/en/         names and descriptions, placeholders until D.2
tools/               uv project plus the shell scripts, see tools/README.md
character/           per-book profiles distilled into one; the line catalog lands here at B.3
  extracts/          raw book passages. gitignored, never committed
assets/source/       the bought 3D model. gitignored, never committed
.ls-defs/            Lua type defs: factorio/ is generated and gitignored, supplement/ is hand-written and committed
dist/                build.sh output. gitignored
```

## Credits

**The shark.** [Animated Hammerhead Shark](https://www.renderhub.com/pig-scales-studio/animated-hammerhead-shark) by **Pig Scales Studio**, bought on RenderHub. It is a genuinely great model and I cannot model worth a damn, so every pixel of Jamal's body starts there and the credit belongs to them. Only RENDERED sprites ship in this repo - the model, its textures and any .blend derived from them stay gitignored under `assets/source/` and are never redistributed. Pig Scales Studio, if any of this reads wrong to you, mail me and it comes down.

**Dungeon Crawler Carl** is Matt Dinniman's work. This is unofficial non-commercial fan work with no affiliation to or endorsement from Dinniman, his publishers or Soundbooth Theater. Jamal's dialogue quotes the books - my own call on fair use, quotes only, in-character lines - and the raw book text NEVER enters this repo: the extraction pipeline writes to `character/extracts/`, which is gitignored on purpose. No audiobook audio either, ever. Those clips carry a separate sound-recording copyright plus the narrator's likeness on top of Dinniman's text, which is a much weaker case than a quoted line.

**Sound effects.** None yet - SFX are PLAN D.6. Every sound that ships gets listed here with its source and license before it ships.

## License

MIT, see [LICENSE](LICENSE). That covers this repo's code and the sprites rendered here. It does NOT cover the underlying 3D model (Pig Scales Studio's, licensed to me and not sublicensed onward) or the *Dungeon Crawler Carl* characters and quotes (Dinniman's).
