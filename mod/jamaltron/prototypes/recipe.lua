-- PLACEHOLDER recipe. Phase D.2 owns the real one (spidertron + raw fish + whatever
-- reads funny, rebalanced); this exists to prove tech -> recipe -> item -> entity is
-- wired end to end. The shape is already the eventual target, only the numbers are
-- throwaway.
--
-- 2.0+ shapes, not interchangeable with pre-2.0 snippets: `ingredients` entries are
-- tagged tables ({type=, name=, amount=}), never the positional {"name", n} form, and
-- results is always a list - `result`/`result_count` are gone.
--
-- Hoisted out of the data:extend call to carry a ---@type. Inline, the literal is
-- still checked (`type = "recipe"` resolves data.AnyPrototype to this one member), but
-- a bare local is not: `recipe.energy_required = "ten"` written afterwards sails
-- through an unannotated table. D.2 will be editing exactly those fields.

local C = require("prototypes.shared")

---@type data.RecipePrototype
local recipe =
{
  type = "recipe",
  name = C.name,
  -- The technology unlocks it. Base's own spidertron recipe does the same.
  enabled = false,
  energy_required = 10,
  ingredients =
  {
    {type = "item", name = "spidertron", amount = 1},
    {type = "item", name = "raw-fish", amount = 10}
  },
  results = {{type = "item", name = C.name, amount = 1}}
}

data:extend({recipe})
