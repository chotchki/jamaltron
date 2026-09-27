-- D.7: "his gun just started firing", for the `attacking` pool (scripts/attack.lua). The one place
-- this mod edits a prototype that is not its own, and it only ADDS to it: every ammo his gun
-- takes gets a script effect on the stream its VEHICLE AmmoType fires, raising the C.fired custom
-- event (prototypes/gun.lua) with source_entity = the vehicle.
--
-- WHY THE AMMO, all MEASURED 2.1.17 + Space Age (d7 probe, 22 lanes, 400 ticks):
--   * a gun's own attack_parameters.ammo_type is IGNORED for a gun that takes ammo items - a
--     script effect on jamaltron-flamethrower's never fired once in 400 ticks of fire
--   * the stream's created_effect fires with the STREAM as source and cause: nothing leads back
--     to who fired it
--   * the stream's action fires per landing (~30 a second) and its "direct" target reads {0, 0}
--   * the ammo's action runs once per STREAM START, cycling guns or not - and a stream restarts
--     whenever its aim point moves. Against a target held still that is once for 400 ticks of
--     fire at a behemoth (443 rounds spent); against anything walking it is about once per
--     firing tick (D.7 review: 34 of 34 ticks at a small biter, 206 of 209 at a stomper, 1027 in
--     1066 in a jump lane). attack.lua turns either into one burst, at ~1.1 us per firing Jamal
--     per tick
--
-- WHAT IT COSTS EVERYONE ELSE: every vehicle firing flamethrower ammo raises C.fired too (in base,
-- the tank), per stream start as above, and attack.lua drops it on one name check. It is a CUSTOM
-- event, so no other mod's on_script_trigger_effect handler sees it. Handheld flamethrowers and
-- flamethrower turrets are untouched: characters fire the `default` AmmoType, and a turret the
-- ammo_type in its own attack_parameters.
--
-- SHAPE KEPT: the effect goes into the existing stream delivery's source_effects, so `action`
-- and `action_delivery` stay the single tables they were, and a mod reading
-- ammo_type[i].action.action_delivery.stream still finds it. Added once per delivery table
-- however many ammo items share it (a mod building several from one table would otherwise
-- raise the event twice per start).
--
-- data-final-fixes, so ammo another mod adds or rewrites in data or data-updates is covered.
-- LIMIT: a mod whose data-final-fixes runs after ours and REPLACES the ammo_type drops the
-- effect, and he goes quiet in a fight - never wrong. An ammo whose vehicle attack is not a
-- stream is skipped: his gun is a stream gun.

local C = require("prototypes.shared")

local M = {}

---The effect every hooked stream delivery carries.
---@type data.ScriptTriggerEffectItem
M.EFFECT = {type = "script", effect_id = C.fired, custom_event = C.fired}

---Ammo categories his gun takes, off the FINAL gun (another mod may have added one).
---@return table<string, boolean>
local function categories()
  local ap = data.raw["gun"][C.gun].attack_parameters
  local out = {}
  if ap.ammo_category then out[ap.ammo_category] = true end
  for _, category in pairs(ap.ammo_categories or {}) do out[category] = true end
  return out
end

---A single prototype value or a list of them, as a list. Every Trigger, TriggerDelivery and
---TriggerEffect field takes either; a single one is a table with a `type`.
---@param v table?
---@return table[]
local function each(v)
  if v == nil then return {} end
  if v.type ~= nil then return {v} end
  return v
end

---The AmmoType a VEHICLE fires `ammo` with: a plain ammo_type applies to everything, else the
---`vehicle` entry, else the first (AmmoSourceType: "the first defined AmmoType ... is used").
---@param ammo data.AmmoItemPrototype
---@return data.AmmoType?
local function vehicle_type(ammo)
  local at = ammo.ammo_type
  if at == nil or at[1] == nil then
    return at --[[@as data.AmmoType?]]
  end
  for _, t in ipairs(at) do
    if t.source_type == "vehicle" then return t end
  end
  return at[1]
end

---Put M.EFFECT on every stream delivery of `trigger` that lacks it. Returns how many carry it.
---@param trigger data.Trigger?
---@return integer
local function hook(trigger)
  local n = 0
  for _, item in ipairs(each(trigger)) do
    for _, delivery in ipairs(each(item.action_delivery)) do
      if delivery.type == "stream" then
        local effects = each(delivery.source_effects)
        local has = false
        for _, effect in ipairs(effects) do
          if effect.type == "script" and effect.effect_id == C.fired then has = true end
        end
        if not has then
          local list = {}
          for i, effect in ipairs(effects) do list[i] = effect end
          list[#list + 1] = util.copy(M.EFFECT)
          delivery.source_effects = list
        end
        n = n + 1
      end
    end
  end
  return n
end

---Hook every ammo his gun takes. Returns the ammo names that carry the signal.
---@return string[]
function M.hook_all()
  local wanted = categories()
  local done = {}
  for name, ammo in pairs(data.raw["ammo"]) do
    local at = wanted[ammo.ammo_category] and vehicle_type(ammo)
    if at and hook(at.action) > 0 then
      done[#done + 1] = name
    end
  end
  table.sort(done)
  return done
end

M.hooked = M.hook_all()

return M
