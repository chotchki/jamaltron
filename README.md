# Jamaltron

Jamal is so very sorry to offer up a Jamaltron to you the loyal Factorio-playing, Dungeon Crawler Carl fan. Jamal knows you would much rather have a spidertron but Jamal must jump!

[![Jamal jumping back and forth over a creek](https://hotchkiss.io/media/file/1268681234f528723f5b90d948306548e0eaf5b2b817680493c282efb1b537ec)](https://hotchkiss.io/media/file/4c015df2c4bbe851fc7a041407a0c2e7cbc61e24fd6c07dc8b005ecad05be5ec)

Jamal has made a [film of his jumping](https://hotchkiss.io/media/file/4c015df2c4bbe851fc7a041407a0c2e7cbc61e24fd6c07dc8b005ecad05be5ec), Mr. Engineer! Jamal is so sorry it also shows the part where his legs break.

## Status

Jamal is playtesting it but it still needs the following work:

- sounds: haven't decided yet
- the recipe (it eats a whole spidertron plus a flamethrower and 10 raw fish) and the research cost are placeholders
- his legs and lights are still the stock spidertron's (his own leg sheets are not rendered yet)
- the flamethrower's tweaking
- removing the mod from a save that has him in it is not checked yet

[PLAN.md](PLAN.md) is the live task list.

## What Jamal does
- Jumps. With such joy! Mr. Engineer, you must press `Y` so Jamal may fly through the air! If Jamal cannot jump, Jamal will bring you all the sorries he has!
- Breaks. Jamal knows Jamal must jump, but if Jamal's legs aren't strong enough, they may break. Jamal will need your help to fix them!
- Burns things. Jamal has his flamethrower!

Jamal unlocks with Jamal's very own research after Spidertron and Flamethrower.

## Install

Base game 2.1 is required, Space Age is optional (no jumping on space platforms). No mod portal release yet, so from a clone either link the working tree into your Factorio [mods directory](https://wiki.factorio.com/Application_directory):

```sh
tools/link_mod.sh            # symlink mod/jamaltron into the mods directory
tools/link_mod.sh --status   # where the link points and whether mod-list.json still parses
tools/link_mod.sh --unlink   # take it back out
```

or build the zip and drop that in the same place:

```sh
tools/build.sh --verify      # writes dist/jamaltron_<version>.zip (version from info.json), then loads it headless to prove it works
```

Use the script rather than a hand-rolled `ln -s`.

## Credits

### The shark

[Animated Hammerhead Shark](https://www.renderhub.com/pig-scales-studio/animated-hammerhead-shark) by Pig Scales Studio, bought on RenderHub. Only RENDERED sprites ship in this repo - the model, its textures and any .blend derived from them stay gitignored under `assets/source/` and are never redistributed.

### Dungeon Crawler Carl

*Dungeon Crawler Carl* is Matt Dinniman's work. This is unofficial non-commercial fan work with no affiliation to or endorsement from Dinniman, his publishers or Soundbooth Theater. Jamal's dialogue quotes the books with pronouns cleaned up to fit the game.

## AI Usage
The code in this repo has been generated with Claude Code, the 3d model was purchased by me.

## License

The code is MIT. The sprites are NOT, and cannot be.

MIT, see [LICENSE](LICENSE), covers the Lua, the Python and the tooling - everything in this repo that isn't a render.

`mod/jamaltron/graphics/` is NOT MIT, and neither is `mod/jamaltron/thumbnail.png` (the mod-list picture, which Factorio only reads from the mod root) - see [their own LICENSE](mod/jamaltron/graphics/LICENSE). Those images are renders of a 3D model licensed from Pig Scales Studio via RenderHub under an Extended Use License, and that license grants no right to SUBLICENSE - so I cannot hand you MIT rights over them, because I was never given them to hand on. RenderHub's grant lets renders ship as part of a larger work, which this mod is. It does not let them be lifted out and reused as standalone art. Take the mod, fork it, ship it; do not take the shark.
