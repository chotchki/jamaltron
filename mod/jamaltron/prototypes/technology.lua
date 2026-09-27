-- PLACEHOLDER cost. Phase D.2 owns the real count and the localised strings in Jamal's
-- voice; the prerequisites, the unlock and the icon (C.6's portrait) are final.
--
-- prerequisites = {"spidertron", "flamethrower"}. The stock spidertron tech's own six
-- prerequisites (military-4, exoskeleton-equipment, fission-reactor-equipment,
-- rocketry, efficiency-module-3, radar) are transitively implied, and repeating them is
-- noise. The spidertron remote's shortcut is therefore unlocked before a jamaltron can
-- exist: no remote work to do. flamethrower is NOT implied
-- (MEASURED, D.7: outside spidertron's closure in base and Space Age), and it unlocks both
-- the flamethrower his recipe eats and the flamethrower-ammo his guns fire - without it he
-- could be researched and neither built nor armed.
--
-- The science packs match stock spidertron (all six) because Jamal IS a spidertron
-- mod; count is the only knob D.2 should be turning. Stock is 2500 at 30s.
--
-- Asymmetry with recipe.lua: technology unit.ingredients still uses the POSITIONAL
-- {"name", count} form. That is how base writes it (technology.lua :5377), not a typo -
-- data.ResearchIngredient is declared as exactly that tuple, so the ---@type below
-- type-checks the positional pairs rather than tolerating them.
--
-- Hoisted out of data:extend for recipe.lua's reason: the annotation keeps later writes
-- (D.2's cost pass) checked.

local C = require("prototypes.shared")

---@type data.TechnologyPrototype
local technology =
{
  type = "technology",
  name = C.name,
  -- OURS (C.6, tools/render/icons.py --promote): 480x256, a 256px icon and its 4-level mip
  -- chain, base's own tech layout. icon_size is required - the default is 64.
  icon = "__jamaltron__/graphics/jamaltron-technology.png",
  icon_size = 256,
  effects = {{type = "unlock-recipe", recipe = C.name}},
  prerequisites = {"spidertron", "flamethrower"},
  unit =
  {
    ingredients =
    {
      {"automation-science-pack", 1},
      {"logistic-science-pack", 1},
      {"military-science-pack", 1},
      {"chemical-science-pack", 1},
      {"production-science-pack", 1},
      {"utility-science-pack", 1}
    },
    time = 30,
    count = 500
  }
}

data:extend({technology})
