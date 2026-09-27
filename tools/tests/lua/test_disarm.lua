-- D.7.3's disarmed twin (prototypes/disarm.lua), under plain lua over a FAKE data.raw: the gun a
-- beached Jamal mounts keeps each slot's ammo categories and can never go off. That the engine
-- then fires nothing and keeps every round is the fire harness's D and O lanes and the jump
-- harness's AM lane.
--
--   lua tools/tests/lua/test_disarm.lua <repo root>
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

---His gun as gun.lua leaves it: the fields disarm.lua reads or must not touch.
local function his_gun()
  return {type = "gun", name = C.gun, localised_name = {"item-name." .. C.gun}, hidden = true,
          attack_parameters = {type = "stream", ammo_category = "flamethrower", cooldown = 1, range = 9,
                               min_range = 3, gun_center_shift = {0, -0.45}, gun_barrel_length = 1.2,
                               cyclic_sound = {begin_sound = {filename = "x"}}}}
end

---A fresh data stage holding his gun, and a fresh disarm module over it.
local function stage()
  data = {raw = {gun = {[C.gun] = his_gun()}}}
  function data.extend(self, list)
    for _, p in ipairs(list) do
      self.raw[p.type] = self.raw[p.type] or {}
      self.raw[p.type][p.name] = p
    end
  end
  package.loaded["prototypes.disarm"] = nil
  return require("prototypes.disarm")
end

local function count(t)
  local n = 0
  for _ in pairs(t) do n = n + 1 end
  return n
end

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end

test("his gun's twin keeps the ammo category and cannot fire", function()
  local disarm = stage()
  local name = disarm.twin(C.gun)
  assert(name == C.gun_broken, "twin named " .. tostring(name))
  local g = data.raw.gun[name]
  assert(disarm.categories(g) == "flamethrower", "categories " .. disarm.categories(g))
  assert(disarm.categories(g) == disarm.categories(data.raw.gun[C.gun]), "categories differ")
  local ap = g.attack_parameters
  assert(ap.range == 0 and ap.min_range == 0 and ap.warmup == disarm.NEVER
         and ap.ammo_consumption_modifier == 0, "a lever is off")
  assert(disarm.is_disarmed(g), "twin can fire")
  assert(ap.cyclic_sound == nil and ap.sound == nil, "a pulled trigger would still roar")
  assert(g.hidden == true and g.auto_recycle == false, "the twin shows up somewhere")
  assert(ap.type == "stream" and ap.gun_center_shift[2] == -0.45, "the rest of the gun was not copied")
end)

test("the vehicle's own gun is untouched and still armed", function()
  local disarm = stage()
  disarm.twin(C.gun)
  local src = data.raw.gun[C.gun]
  assert(not disarm.is_disarmed(src), "the vehicle's gun was disarmed")
  assert(src.attack_parameters.range == 9 and src.attack_parameters.min_range == 3
         and src.attack_parameters.warmup == nil and src.attack_parameters.cyclic_sound, "the source was edited")
end)

test("made once however many slots ask", function()
  local disarm = stage()
  local first = disarm.twin(C.gun)
  local made = data.raw.gun[first]
  for _ = 2, 4 do assert(disarm.twin(C.gun) == first) end
  assert(count(data.raw.gun) == 2, count(data.raw.gun) .. " guns")
  assert(rawequal(data.raw.gun[first], made), "slots 2-4 re-made the twin over the first")
end)

test("another mod's gun on him gets a twin of its own, every category kept", function()
  local disarm = stage()
  data.raw.gun["laser-thing"] = {type = "gun", name = "laser-thing", attack_parameters = {type = "beam",
    ammo_categories = {"laser", "battery"}, range = 20, cooldown = 10}}
  local name = disarm.twin("laser-thing")
  assert(name == "jamaltron-broken-laser-thing", name)
  assert(disarm.categories(data.raw.gun[name]) == "battery,laser", disarm.categories(data.raw.gun[name]))
  assert(disarm.is_disarmed(data.raw.gun[name]))
  assert(disarm.twin(C.gun) == C.gun_broken and count(data.raw.gun) == 4, "his own twin collided")
  local ln = data.raw.gun[name].localised_name
  assert(ln[1] == "item-name.jamaltron-broken-gun" and ln[2][1] == "item-name.laser-thing",
         "an unnamed gun's twin should wrap item-name.<its name>")
end)

test("ammo_category and ammo_categories compare as the same slot", function()
  local disarm = stage()
  local one = {attack_parameters = {ammo_category = "flamethrower"}}
  local list = {attack_parameters = {ammo_categories = {"flamethrower"}}}
  assert(disarm.categories(one) == disarm.categories(list))
  assert(disarm.categories(one) ~= disarm.categories({attack_parameters = {ammo_category = "rocket"}}))
end)

test("every lever is required: undo any one and it is not disarmed (each was measured to leak)", function()
  local disarm = stage()
  local base = {range = 0, min_range = 0, warmup = disarm.NEVER, ammo_consumption_modifier = 0}
  assert(disarm.is_disarmed({attack_parameters = deepcopy(base)}))
  for _, lever in ipairs({{"range", 9}, {"min_range", 3}, {"warmup", 1}, {"ammo_consumption_modifier", 1}}) do
    local ap = deepcopy(base)
    ap[lever[1]] = lever[2]
    assert(not disarm.is_disarmed({attack_parameters = ap}), lever[1] .. " " .. lever[2] .. " passed")
  end
  local ap = deepcopy(base)
  ap.warmup, ap.ammo_consumption_modifier = nil, nil
  assert(not disarm.is_disarmed({attack_parameters = ap}), "range 0 alone passed")
end)

test("NEVER fits the prototype's uint32 warmup", function()
  local disarm = stage()
  assert(disarm.NEVER <= 4294967295 and disarm.NEVER >= 60 * 60 * 60 * 24 * 365, disarm.NEVER)
end)

test("a gun that is not there fails the load by name", function()
  local disarm = stage()
  local ok, err = pcall(disarm.twin, "no-such-gun")
  assert(not ok and tostring(err):find("no%-such%-gun"), tostring(err))
end)

test("the locale keys it names are in locale/en/jamaltron.cfg", function()
  local f = assert(io.open(root .. "/mod/jamaltron/locale/en/jamaltron.cfg"))
  local text, section, have = f:read("*a"), nil, {}
  f:close()
  for l in text:gmatch("[^\n]+") do
    local sec = l:match("^%[([%w%-]+)%]$")
    if sec then section = sec end
    local key = l:match("^([%w%-]+)=")
    if key and section then have[section .. "." .. key] = true end
  end
  local disarm = stage()
  local g = data.raw.gun[disarm.twin(C.gun)]
  assert(have[g.localised_name[1]], g.localised_name[1] .. " missing")
  assert(have[g.localised_description[1]], g.localised_description[1] .. " missing")
  assert(have[g.localised_name[2][1]], g.localised_name[2][1] .. " missing")
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
