-- The data-stage guards for other spider mods (PLAN E.6, prototypes/compat.lua), under plain lua
-- over a FAKE data.raw: what each guard does with and without the other mod loaded. That the
-- engine then refuses the buoy is the compat scratch run's (measured against the mod's zip),
-- not this file's.
--
--   lua tools/tests/lua/test_compat.lua <repo root>
--
-- Run by tools/tests/test_speech_lua.py, in test_pick.lua's harness shape; Lua 5.2 / 5.4+ / luajit.

local root = arg[1] or "."
package.path = root .. "/mod/jamaltron/?.lua;" .. package.path

local C = require("prototypes.shared")

local function deepcopy(t)
  if type(t) ~= "table" then return t end
  local out = {}
  for k, v in pairs(t) do out[k] = deepcopy(v) end
  return out
end
util = {copy = deepcopy}

---A data stage with his vehicle on the stock spidertron's grid, as buoyant's data-updates leaves
---it (a `buoyant` category added), and optionally Enhancements' dummy of him.
local function stage(opts)
  opts = opts or {}
  local grid = {type = "equipment-grid", name = "spidertron-equipment-grid", width = 10, height = 6,
                equipment_categories = {"armor", "buoyant"}}
  local raw = {
    ["equipment-grid"] = {[grid.name] = grid},
    technology = {},
    ["spider-vehicle"] = {
      [C.name] = {name = C.name, equipment_grid = (not opts.no_grid) and grid.name or nil},
      spidertron = {name = "spidertron", equipment_grid = grid.name},
    },
  }
  if opts.dummy then
    raw["spider-vehicle"]["spidertron-enhancements-dummy-" .. C.name] =
      {name = "spidertron-enhancements-dummy-" .. C.name, equipment_grid = grid.name}
  end
  data = {raw = raw}
  function data.extend(self, list)
    for _, p in ipairs(list) do
      self.raw[p.type] = self.raw[p.type] or {}
      self.raw[p.type][p.name] = p
    end
  end
  mods = opts.mods or {base = "2.1.17"}
  return raw
end

stage()
local compat = require("prototypes.compat")
local layers = require("prototypes.layers")

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end
local function has(list, x)
  for _, v in ipairs(list) do if v == x then return true end end
  return false
end
local function read(path)
  local f = assert(io.open(root .. "/" .. path, "r"))
  local text = f:read("*a")
  f:close()
  return text
end

test("without buoyant-spidertrons: nothing changes, no grid is made", function()
  local raw = stage({dummy = true})
  assert(compat.no_buoys() == nil)
  assert(raw["spider-vehicle"][C.name].equipment_grid == "spidertron-equipment-grid")
  assert(raw["equipment-grid"][C.grid] == nil)
end)

test("with it: his own grid without `buoyant`, he and Enhancements' dummy on it, the stock grid untouched", function()
  local raw = stage({dummy = true, mods = {base = "2.1.17", ["buoyant-spidertrons"] = "1.0.13"}})
  local grid = compat.no_buoys()
  assert(grid and grid.name == C.grid and raw["equipment-grid"][C.grid] == grid, "extended")
  assert(has(grid.equipment_categories, "armor") and not has(grid.equipment_categories, "buoyant"))
  assert(grid.width == 10 and grid.height == 6, "the same shape: the swap re-puts by position")
  assert(raw["spider-vehicle"][C.name].equipment_grid == C.grid)
  assert(raw["spider-vehicle"][compat.ENHANCEMENTS_DUMMY].equipment_grid == C.grid,
         "a buoy in the dummy's grid would swap it for a -buoyant twin that does not exist")
  local stock = raw["equipment-grid"]["spidertron-equipment-grid"]
  assert(has(stock.equipment_categories, "buoyant"), "the stock spidertron keeps its buoys")
  assert(raw["spider-vehicle"].spidertron.equipment_grid == "spidertron-equipment-grid")
end)

test("with it and no Enhancements, or a vehicle with no grid: fine", function()
  local raw = stage({mods = {["buoyant-spidertrons"] = "1.0.13"}})
  assert(compat.no_buoys() and raw["spider-vehicle"][C.name].equipment_grid == C.grid)
  stage({no_grid = true, mods = {["buoyant-spidertrons"] = "1.0.13"}})
  assert(compat.no_buoys() == nil, "a mod took his grid away: nothing to guard")
end)

---A stage with his vehicle and eight legs where data.lua (entity.lua) left them, on W1's layers -
---and `reskin` applied to it, the way another mod's data-updates would.
local function w1_stage(reskin)
  local raw = stage()
  local vehicle = raw["spider-vehicle"][C.name]
  vehicle.graphics_set = {render_layer = C.layer_body}
  vehicle.spider_engine = {legs = {}}
  raw["spider-leg"] = {}
  for i = 1, C.leg_count do
    local leg = {name = C.leg_name(i), graphics_set = {upper_part = {}, lower_part = {}}}
    layers.leg(leg)
    raw["spider-leg"][leg.name] = leg
    vehicle.spider_engine.legs[i] = {leg = leg.name}
  end
  if reskin then reskin(raw, vehicle) end
  return raw, vehicle
end

test("W1 layers: nothing re-skinned, nothing to fix", function()
  w1_stage()
  assert(compat.w1_layers() == 0)
end)

test("W1 layers: a data-updates re-skin of his legs and torso gets the layers back", function()
  local raw, vehicle = w1_stage(function(raw, vehicle)
    -- the review probe's shape: stock art copied over each leg, stock's layers (nil) with it
    for i = 1, C.leg_count do
      raw["spider-leg"][C.leg_name(i)].graphics_set = {upper_part = {}, lower_part = {}}
    end
    vehicle.graphics_set = {animation = {}}
  end)
  assert(compat.w1_layers() == 1 + C.leg_count, "torso + eight legs")
  assert(vehicle.graphics_set.render_layer == C.layer_body)
  for i = 1, C.leg_count do
    assert(layers.leg_ok(raw["spider-leg"][C.leg_name(i)]), C.leg_name(i))
  end
  assert(compat.w1_layers() == 0, "idempotent")
end)

test("W1 layers: a leg he was re-pointed at is someone else's and stays as they made it", function()
  local raw = w1_stage(function(raw, vehicle)
    raw["spider-leg"]["their-leg"] = {name = "their-leg", graphics_set = {upper_part = {}, lower_part = {}}}
    vehicle.spider_engine.legs[3].leg = "their-leg"
  end)
  assert(compat.w1_layers() == 0)
  assert(raw["spider-leg"]["their-leg"].graphics_set.upper_part.render_layer == nil)
end)

test("W1 layers: a leg with no parts to layer, or no vehicle, is skipped, not an error", function()
  w1_stage(function(raw)
    raw["spider-leg"][C.leg_name(2)].graphics_set = nil
  end)
  assert(compat.w1_layers() == 0)
  local raw = stage()
  raw["spider-vehicle"][C.name] = nil
  assert(compat.w1_layers() == 0)
end)

---A stage with his research and, unless `no_stock`, spidertron's - costing `packs`, the way Space
---Age's data.lua leaves it.
local function tech_stage(packs, no_stock)
  local raw = stage()
  raw.technology = {
    [C.name] = {name = C.name, unit = {count = 500, time = 30, ingredients = {{"automation-science-pack", 1}}}},
  }
  if not no_stock then
    raw.technology.spidertron = {name = "spidertron", unit = {count = 2500, time = 30, ingredients = packs}}
  end
  return raw
end

test("science: his packs become a COPY of spidertron's, his count and time kept", function()
  local sa = {{"automation-science-pack", 1}, {"space-science-pack", 1}, {"agricultural-science-pack", 1}}
  local raw = tech_stage(sa)
  local got = compat.science()
  local mine = raw.technology[C.name]
  assert(got == mine.unit.ingredients and #got == 3, "set")
  for i, pack in ipairs(sa) do assert(got[i][1] == pack[1] and got[i][2] == pack[2], pack[1]) end
  assert(got ~= sa and got[3] ~= sa[3], "a copy: a later edit to spidertron's must not move his")
  assert(mine.unit.count == 500 and mine.unit.time == 30, "D.2's knobs untouched")
end)

test("science: no spidertron tech, or one with no unit (a trigger tech): he keeps his own", function()
  local raw = tech_stage(nil, true)
  assert(compat.science() == nil)
  assert(raw.technology[C.name].unit.ingredients[1][1] == "automation-science-pack")
  raw = tech_stage(nil)
  raw.technology.spidertron.unit = nil
  assert(compat.science() == nil)
  assert(#raw.technology[C.name].unit.ingredients == 1)
end)

test("surface: his conditions become a COPY of spidertron's, even after a data-updates edit to them", function()
  local raw = stage()
  local stock = raw["spider-vehicle"].spidertron
  stock.surface_conditions = {{property = "gravity", min = 1}}
  raw["spider-vehicle"][C.name].surface_conditions = {{property = "gravity", min = 1}}
  stock.surface_conditions[2] = {property = "pressure", min = 10}  -- a later mod's edit
  local got = compat.surface()
  local mine = got and got.surface_conditions
  assert(got == raw["spider-vehicle"][C.name] and mine and #mine == 2, "set")
  assert(mine[2].property == "pressure" and mine[2].min == 10)
  assert(mine ~= stock.surface_conditions and mine[1] ~= stock.surface_conditions[1], "a copy")
end)

test("surface: base (none on spidertron) leaves him none; no spidertron: he keeps his own", function()
  local raw = stage()
  raw["spider-vehicle"][C.name].surface_conditions = {{property = "gravity", min = 1}}
  assert(compat.surface() and raw["spider-vehicle"][C.name].surface_conditions == nil)
  raw = stage()
  raw["spider-vehicle"][C.name].surface_conditions = {{property = "gravity", min = 1}}
  raw["spider-vehicle"].spidertron = nil
  assert(compat.surface() == nil)
  assert(raw["spider-vehicle"][C.name].surface_conditions[1].min == 1)
end)

test("data-final-fixes runs compat BEFORE bodies: the beached and airborne copies inherit the grid", function()
  local text = read("mod/jamaltron/data-final-fixes.lua")
  local a = text:find('require("prototypes.compat")', 1, true)
  local b = text:find('require("prototypes.bodies")', 1, true)
  assert(a and b and a < b, "order")
end)

test("info.json: the three mods compat.lua orders against are HIDDEN optional dependencies", function()
  local text = read("mod/jamaltron/info.json")
  for _, name in ipairs({"SpidertronEnhancements", "spidertron-dock", "buoyant-spidertrons"}) do
    assert(text:find('"(?) ' .. name .. '"', 1, true), name)
  end
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
