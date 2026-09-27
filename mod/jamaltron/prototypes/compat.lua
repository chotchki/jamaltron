-- Other spider mods, at the data stage (PLAN E.6). Loaded from data-final-fixes.lua BEFORE
-- prototypes/bodies.lua, so the beached and airborne copies inherit whatever this does to him.
-- Every guard is keyed on `mods[...]` and is a no-op without that mod - except W1's layers
-- (M.w1_layers, D.7.4), which answer ANY mod that re-skins him and are a no-op when none did.
--
-- LOAD ORDER is info.json's: SpidertronEnhancements, spidertron-dock and buoyant-spidertrons are
-- hidden optional dependencies, so their data-final-fixes always runs before ours - they build
-- their per-spider copies while the vehicle is the only Jamal there is. MEASURED without them: a
-- base-only game loaded us first and Enhancements built dummies for beached and airborne (never
-- used - it only swaps minable spiders - but unwanted prototypes), and this file's dummy fix
-- below depended on which order a game happened to pick.
--
-- buoyant-spidertrons (1.0.13): its data-updates gives every non-hidden spider with a grid a
-- `<name>-buoyant` twin and puts a `buoyant` category on that grid, and at runtime a buoy going
-- into ANY grid swaps the spider for `<name>-buoyant` with a plain destroy - no replaced event,
-- no raise_built. MEASURED: on the vehicle he became jamaltron-buoyant with no speech record and
-- stopped jumping; on a beached body there is no jamaltron-beached-buoyant, and the game ended
-- ("non-recoverable error", on_equipment_inserted) - by hand or by bots filling a ghost after he
-- broke. So he gets his own copy of the grid without the category: a buoy cannot go in, nothing
-- is swapped. It suits him - the shark that will not go near water does not float either. A save
-- that had him on the shared grid comes back on this one with his equipment where it was
-- (measured). LIMIT: while buoyant is loaded, a later mod's data-final-fixes edit to the
-- spidertron grid no longer reaches him.

local C = require("prototypes.shared")
local layers = require("prototypes.layers")

local M = {}

---The dummy Spidertron Enhancements parks him in while his driver rides a car. Its
---data-final-fixes copies his grid by name before ours runs, so the dummy follows him onto his.
M.ENHANCEMENTS_DUMMY = "spidertron-enhancements-dummy-" .. C.name

---Give the vehicle (and Enhancements' dummy of him) a grid with no `buoyant` category. Returns the
---grid it made, or nil when there was nothing to do.
---@return data.EquipmentGridPrototype?
function M.no_buoys()
  if not mods["buoyant-spidertrons"] then return nil end
  local vehicle = data.raw["spider-vehicle"][C.name]
  local shared = vehicle and vehicle.equipment_grid and data.raw["equipment-grid"][vehicle.equipment_grid]
  if not shared then return nil end
  ---@type data.EquipmentGridPrototype
  local grid = util.copy(shared)
  grid.name = C.grid
  local categories = {}
  for _, category in pairs(grid.equipment_categories or {}) do
    if category ~= "buoyant" then categories[#categories + 1] = category end
  end
  grid.equipment_categories = categories
  data:extend({grid})
  vehicle.equipment_grid = C.grid
  local dummy = data.raw["spider-vehicle"][M.ENHANCEMENTS_DUMMY]
  if dummy then dummy.equipment_grid = C.grid end
  return grid
end

---D.7.4's W1 layers AGAIN (prototypes/layers.lua), over whatever data-updates left. A mod that
---re-skins his legs or torso in data-updates replaces the graphics_set that carried entity.lua's
---layers, and the flame is back on top of him with every gate passing - MEASURED (review probe:
---util.copy of spidertron-leg-1's graphics_set onto each jamaltron-leg-N left upper, lower and
---joint layers nil, stock's, under the stream). Re-applied, not asserted: the new art still
---loads, just on W1's layers. Only HIS legs: if a mod re-pointed him at another leg prototype
---that one is theirs, shared with their spider, and stays as they made it. Runs before bodies.lua,
---so beached and airborne copy the result (beached then lays its own torso on 'object').
---Returns how many prototypes it had to fix.
---LIMIT: a mod whose OWN data-final-fixes runs after ours still gets the last word.
---@return integer
function M.w1_layers()
  local vehicle = data.raw["spider-vehicle"][C.name]
  if not vehicle then return 0 end
  local fixed = 0
  local gs = vehicle.graphics_set
  if gs and gs.render_layer ~= C.layer_body then
    layers.torso(gs)
    fixed = fixed + 1
  end
  for i, spec in pairs(vehicle.spider_engine and vehicle.spider_engine.legs or {}) do
    local leg = spec.leg == C.leg_name(i) and (data.raw["spider-leg"] or {})[spec.leg]
    if leg and not layers.leg_ok(leg) and layers.leg(leg) then fixed = fixed + 1 end
  end
  return fixed
end

M.no_buoys()
M.w1_layers()

return M
