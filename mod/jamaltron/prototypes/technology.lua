-- PLACEHOLDER technology. Phase D.2 owns the real cost and the localised strings in
-- Jamal's voice; the prerequisite and the unlock are already final.
--
-- prerequisites = {"spidertron"} alone is correct: the stock spidertron tech's own six
-- prerequisites (military-4, exoskeleton-equipment, fission-reactor-equipment,
-- rocketry, efficiency-module-3, radar) are transitively implied, and repeating them is
-- noise. It also means the spidertron remote's shortcut is already unlocked before a
-- jamaltron can exist, so there is no remote work to do.
--
-- The science packs match stock spidertron (all six) because Jamal IS a spidertron
-- mod; count is the only knob D.2 should be turning. Stock is 2500 at 30s.
--
-- Note the asymmetry with recipe.lua: technology unit.ingredients still uses the
-- POSITIONAL {"name", count} form. That is how base writes it (technology.lua :5377),
-- not a typo - and data.ResearchIngredient is declared as exactly that tuple, so the
-- ---@type below type-checks the positional pairs rather than tolerating them.
--
-- Hoisted out of data:extend for the same reason as recipe.lua: the annotation is what
-- keeps later writes (D.2's cost pass) checked.

local C = require("prototypes.shared")

---@type data.TechnologyPrototype
local technology =
{
  type = "technology",
  name = C.name,
  -- Stock tech icon, 256px. C.6 replaces it; icon_size is required alongside icon.
  icon = "__base__/graphics/technology/spidertron.png",
  icon_size = 256,
  effects = {{type = "unlock-recipe", recipe = C.name}},
  prerequisites = {"spidertron"},
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
