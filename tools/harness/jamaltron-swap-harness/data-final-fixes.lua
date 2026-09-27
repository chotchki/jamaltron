-- The swap harness's test bodies. data-final-fixes, after jamaltron's own (a dependency runs
-- first), so every clone is of the FINAL jamaltron - the same thing D.1 clones.
--
--   jamaltron-beached, -airborne  STAND-INS, made only when D.1's real bodies do not exist:
--                                 plain clones, so they can WALK, and the swap holds them with
--                                 disabled_by_script. The harness judges what a body does
--                                 (stays put, lands walking), never how it was stopped, so it
--                                 passes before D.1 and after
--   jamaltron-swaptest-small      a DRIFTED body: half the health, trunk and trash
--   jamaltron-swaptest-smallgrid  the same trunk on a 6x4 grid: equipment that cannot fit
--   jamaltron-swaptest-burner     a 1x1 generator equipment with a burner, because vanilla has
--                                 no burner equipment and the swap claims to carry its fuel
local base = data.raw["spider-vehicle"]["jamaltron"]
assert(base, "jamaltron not loaded")

---@param name string
---@param edit fun(t: table)?
local function clone(name, edit)
  if data.raw["spider-vehicle"][name] then return end
  local t = util.copy(base)
  t.name = name
  t.hidden = true
  t.factoriopedia_simulation = nil
  t.localised_name = name
  if edit then edit(t) end
  data:extend({t})
end

clone("jamaltron-beached")
clone("jamaltron-airborne")
clone("jamaltron-swaptest-small", function(t)
  t.max_health = base.max_health / 2
  t.inventory_size = base.inventory_size / 2
  t.trash_inventory_size = base.trash_inventory_size / 2
end)

local grid = util.copy(data.raw["equipment-grid"][base.equipment_grid])
grid.name = "jamaltron-swaptest-grid"
grid.width, grid.height = 6, 4
data:extend({grid})
clone("jamaltron-swaptest-smallgrid", function(t)
  t.equipment_grid = "jamaltron-swaptest-grid"
end)

local burner = util.copy(data.raw["generator-equipment"]["fission-reactor-equipment"])
burner.name = "jamaltron-swaptest-burner"
burner.shape = {width = 1, height = 1, type = "full"}
burner.burner = {type = "burner", fuel_categories = {"chemical"}, fuel_inventory_size = 2,
                 burnt_inventory_size = 1}
burner.power = "10kW"
burner.localised_name = burner.name
local item = util.copy(data.raw["item"]["fission-reactor-equipment"])
item.name = "jamaltron-swaptest-burner"
item.place_as_equipment_result = "jamaltron-swaptest-burner"
item.hidden = true
item.localised_name = item.name
data:extend({burner, item})
