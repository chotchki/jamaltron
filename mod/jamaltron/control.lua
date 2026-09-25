-- Runtime stage entry point: event registration, and nothing else - the behaviour lives in
-- scripts/. D.5.3 wires the speech pools whose events exist today; the jump, landing,
-- break, flop and repair pools are E's to call through speech.say.

local C = require("prototypes.shared")
local speech = require("scripts.speech")

---Only OUR entity. Every entity event below is filtered to it, so a base with a thousand
---turrets taking damage costs this mod nothing.
local ours = {{filter = "name", name = C.name}}

script.on_init(function()
  speech.adopt_all()
end)

script.on_configuration_changed(function()
  -- A save from before speech existed has jamaltrons with no record; give them one.
  speech.adopt_all()
end)

---@param event {entity: LuaEntity}
local function built(event)
  speech.say(event.entity, "built")
end
-- One registration per event: filters only apply to a single-event registration.
for _, name in pairs({defines.events.on_built_entity, defines.events.on_robot_built_entity,
                      defines.events.script_raised_built, defines.events.script_raised_revive}) do
  script.on_event(name, built, ours)
end

---@param event EventData.on_player_driving_changed_state
script.on_event(defines.events.on_player_driving_changed_state, function(event)
  local vehicle = event.entity
  if not (vehicle and vehicle.valid and vehicle.name == C.name) then
    return
  end
  local player = game.get_player(event.player_index)
  speech.say(vehicle, (player and player.vehicle == vehicle) and "enter" or "exit")
end)

---@param event EventData.on_entity_damaged
script.on_event(defines.events.on_entity_damaged, function(event)
  if event.final_health > 0 then        -- a killing blow is on_entity_died's line, not this
    speech.damaged(event.entity)
  end
end, ours)

---@param event EventData.on_spider_command_completed
script.on_event(defines.events.on_spider_command_completed, function(event)
  local vehicle = event.vehicle
  -- The LAST waypoint only (lines.md): a patrol of twelve legs is one errand, not twelve.
  if vehicle.valid and vehicle.name == C.name and #vehicle.autopilot_destinations == 0 then
    speech.say(vehicle, "command_done")
  end
end)

---@param event EventData.on_entity_died
script.on_event(defines.events.on_entity_died, function(event)
  speech.say(event.entity, "died")
end, ours)

---@param event EventData.on_object_destroyed
script.on_event(defines.events.on_object_destroyed, function(event)
  if event.type == defines.target_type.entity then
    speech.forget(event.useful_id)
  end
end)

-- Chains land to within a quarter second (their delays are multiples of 30 ticks); the
-- slow clock - idle, moving, low-health re-arming - needs no better than a second.
script.on_nth_tick(15, function(event)
  speech.deliver_due(event.tick)
end)
script.on_nth_tick(60, function(event)
  speech.poll(event.tick)
end)

-- For E's jump/landing/break code in another file, other mods, and the D.5.4 harness.
remote.add_interface("jamaltron", {
  ---@param entity LuaEntity
  ---@param pool string
  ---@param cond string?
  ---@return string?
  say = function(entity, pool, cond)
    return speech.say(entity, pool, cond)
  end,
  ---@param on boolean|string true logs each line said; "print" also puts its row id in chat
  debug = function(on)
    speech.set_debug(on)
  end,
})

-- The D.5.4 / F.1 harness's handles on the speech state. Not for other mods: `force` skips
-- every gate the catalog's rules put in front of a line.
remote.add_interface("jamaltron-harness", {
  ---@param entity LuaEntity
  ---@param id string
  ---@param still boolean? render it the way a death does
  ---@return string?
  force = function(entity, id, still)
    return speech.force(entity, id, still)
  end,
  ---@param entity LuaEntity
  ---@return table?
  state = function(entity)
    return speech.state(entity)
  end,
  ---@param old_unit integer
  ---@param new_entity LuaEntity
  transfer = function(old_unit, new_entity)
    speech.transfer(old_unit, new_entity)
  end,
})
