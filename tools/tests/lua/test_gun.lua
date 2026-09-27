-- His flamethrower's data stage (PLAN D.7, prototypes/gun.lua), under plain lua over a FAKE
-- data.raw: what the copy does with base's tank-flamethrower as shipped, as another mod may leave
-- it, and with it gone. That the engine then loads it is the fire harness's.
--
--   lua tools/tests/lua/test_gun.lua <repo root>
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
local logged = {}
log = function(s) logged[#logged + 1] = s end

---base's tank-flamethrower, the fields gun.lua reads (base/prototypes/item.lua:3326).
local function tank()
  return {type = "gun", name = "tank-flamethrower", icon = "__base__/graphics/icons/flamethrower.png",
          hidden = true, subgroup = "gun", stack_size = 1,
          attack_parameters = {type = "stream", ammo_category = "flamethrower", cooldown = 1,
                               gun_barrel_length = 1.4, gun_center_shift = {-0.17, -1.15},
                               range = 9, min_range = 3}}
end

---Run gun.lua over a data stage holding `gun` (nil: none) as tank-flamethrower. Returns his gun.
local function stage(gun)
  data = {raw = {gun = {["tank-flamethrower"] = gun}}}
  function data.extend(self, list)
    for _, p in ipairs(list) do
      self.raw[p.type] = self.raw[p.type] or {}
      self.raw[p.type][p.name] = p
    end
  end
  logged = {}
  dofile(root .. "/mod/jamaltron/prototypes/gun.lua")
  return data.raw.gun[C.gun]
end

local function is_his(g)
  local ap = g and g.attack_parameters
  assert(ap, "no " .. C.gun)
  assert(ap.type == "stream" and ap.ammo_category == "flamethrower", "not a flamethrower stream")
  assert(ap.gun_center_shift[1] == 0 and ap.gun_center_shift[2] == 0.15 and ap.gun_barrel_length == 0,
         "the stream no longer starts under his belly (D.7.4)")
  assert(data.raw["custom-event"][C.fired], "no firing event")
end

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end

test("base's tank-flamethrower is copied, renamed, and the stream moved under his belly", function()
  local base = tank()
  local g = stage(base)
  is_his(g)
  assert(g.attack_parameters.range == 9 and g.attack_parameters.min_range == 3)
  assert(base.attack_parameters.gun_barrel_length == 1.4, "the tank's own gun was edited")
  assert(#logged == 0, "a fallback logged with base's gun there")
end)

test("another mod's edit to a stream tank-flamethrower rides along (range 12)", function()
  local modded = tank()
  modded.attack_parameters.range = 12
  local g = stage(modded)
  is_his(g)
  assert(g.attack_parameters.range == 12, "his gun ignored the modded range")
end)

test("tank-flamethrower REMOVED by another mod: built from 2.1.17's numbers, no load failure", function()
  local g = stage(nil)
  is_his(g)
  assert(g.attack_parameters.range == 9 and g.attack_parameters.min_range == 3
         and g.attack_parameters.cooldown == 1 and g.attack_parameters.cyclic_sound, "not base's numbers")
  assert(#logged == 1, "the fallback said nothing in the log")
end)

test("tank-flamethrower turned into a projectile gun: his stays a stream", function()
  local proj = tank()
  proj.attack_parameters.type = "projectile"
  local g = stage(proj)
  is_his(g)
  assert(g.attack_parameters.range == 9)
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
