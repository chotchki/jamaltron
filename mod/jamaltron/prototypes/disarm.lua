-- D.7.3: a BEACHED JAMAL DOES NOT FIRE - not by himself, not for a driver still seated in him -
-- and his ammo stays where it was. bodies.lua mounts a disarmed twin of each of the vehicle's
-- guns on the beached body: same ammo categories, so the swap moves every ammo slot across
-- untouched (quality, partial magazine, selected_gun_index), and a gun that can never go off.
--
-- MEASURED 2.1.17 + SA on the real break path (PLAN D.7.3's spike: 300 ticks beached, a big
-- biter held 5 tiles off, a scripted driver shooting it every tick, ammo 11/22/33 rare/44 with a
-- 57-round partial):
--   * range 0 alone: he never auto-fires, but a DRIVER still burns the biter to death at 5 tiles
--     - range does not bound a gunner's aim
--   * min_range above range: he auto-fires anyway, 337 rounds into nothing
--   * cooldown 1e9: one stream per break, 17 damage
--   * warmup 4e9 (no shot until 2 years of held trigger): no stream, no event, no damage, but the
--     trigger spends 1.125 rounds the first time it is pulled
--   * + ammo_consumption_modifier 0: that 1.125 goes too. 0 rounds over 15 clicks, a 120-tick
--     gap and a gun switch per second. ALONE it is free ammo: he fires as normal and spends none
--   * a category no ammo has: nothing fires, but every round leaves the slots for the swap's
--     stash - empty slots in his GUI, back on the repair, spilled on the ground if he dies
--   * runtime auto-targeting off: stops him, not a driver; the player can tick it back on in
--     the GUI, and the swap carries it onto the repaired vehicle, who then never auto-fires again
-- range 0 stays on top of the warmup: auto-targeting then never picks a target at all.
-- Sounds are dropped so a pulled trigger does not start a flamethrower loop.
-- Limit: a mod whose data-final-fixes runs after ours can rewrite the twin, and bodies.lua's
-- is_disarmed assert has already run. MEASURED (probe mods editing every gun): range + 5 still
-- fires nothing, the warmup holds; ammo_consumption_modifier = 0.5 re-arms the COST only - the
-- first pull (a driver's, or auto-targeting once range is back) spends 0.5625 rounds, 0 streams.
-- A mod that MULTIPLIES the modifier keeps 0 at 0.

local C = require("prototypes.shared")

local M = {}

---No shot until this many ticks of trigger (~2.1 years at 60 UPS). uint32 in the prototype.
M.NEVER = 4000000000

---A gun's ammo categories as one comparable string: what decides which ammo its slot takes.
---@param gun data.GunPrototype
---@return string
function M.categories(gun)
  local ap = gun.attack_parameters
  local list = {}
  if ap.ammo_category then list[#list + 1] = ap.ammo_category end
  for _, c in pairs(ap.ammo_categories or {}) do list[#list + 1] = c end
  table.sort(list)
  return table.concat(list, ",")
end

---@param gun data.GunPrototype
---@return boolean
function M.is_disarmed(gun)
  local ap = gun.attack_parameters
  return ap.range == 0 and (ap.min_range or 0) == 0 and (ap.warmup or 0) >= M.NEVER
    and ap.ammo_consumption_modifier == 0
end

---The disarmed twin of gun `name`, made once. Returns its name.
---@param name data.ItemID
---@return data.ItemID
function M.twin(name)
  local twin = name == C.gun and C.gun_broken or ("jamaltron-broken-" .. name)
  if data.raw["gun"][twin] then return twin end
  local source = data.raw["gun"][name]
  assert(source, "no gun " .. tostring(name) .. " to disarm")
  ---@type data.GunPrototype
  local gun = util.copy(source)
  gun.name = twin
  gun.localised_name = {"item-name.jamaltron-broken-gun", source.localised_name or {"item-name." .. name}}
  gun.localised_description = {"item-description.jamaltron-broken-gun"}
  gun.hidden = true
  gun.auto_recycle = false
  local ap = gun.attack_parameters
  ap.range, ap.min_range = 0, 0
  ap.warmup = M.NEVER
  ap.ammo_consumption_modifier = 0
  ap.sound, ap.cyclic_sound = nil, nil
  data:extend({gun})
  return twin
end

return M
