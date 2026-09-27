-- The mod's ONE per-tick clock (PLAN D.4.2), and the only file that touches on_tick or on_load.
-- A mod gets one on_tick and one on_load registration: a second script.on_event(on_tick, f)
-- OVERWRITES the first (LuaBootstrap, documented), so D.4's t+1 writes and E.1's jump arc cannot
-- each own one - the later would silently cancel the other (Jamal frozen mid-arc, or a beached
-- body never disabled). They register here as subsystems.
--
-- ZERO COST IDLE (F.3): on_tick is registered only while some subsystem's pending() is true,
-- and the handler drops it the first tick none is. MULTIPLAYER: a joining client never replays
-- the host's history, only on_load, so on_load must re-derive EXACTLY what the host has
-- registered (docs, auxiliary/data-lifecycle: "conditional registrations"). That holds while:
--   * pending() is a pure READ of storage - on_load may not write it
--   * only a subsystem's own tick() turns its pending() from true to false. A forget() that
--     deleted due work would leave the host registered and a client joining in that window not,
--     a desync. Work for a dead entity is the tick's to drop
-- A subsystem that adds work calls wake() right after; on_init and on_configuration_changed end
-- with sync() (migrations need not - see sync()).

local M = {}

---@class Jamaltron.ClockSubsystem
---@field pending fun(): boolean true while tick() has work; a read of storage, never a write
---@field tick fun(tick: integer) runs every tick while this subsystem is pending

---In registration order. The one allowed kind of module state: filled by control.lua's main
---chunk before on_load runs, so a pure function of the code, the same on every peer and load.
---@type {name: string, sub: Jamaltron.ClockSubsystem}[]
local subsystems = {}

---@return boolean
local function any_pending()
  for _, entry in ipairs(subsystems) do
    if entry.sub.pending() then
      return true
    end
  end
  return false
end

---Work added DURING this (a landing swap from inside the arc's tick) is due next tick, and keeps
---the registration by being pending when the loop ends.
---@param event EventData.on_tick
local function on_tick(event)
  for _, entry in ipairs(subsystems) do
    if entry.sub.pending() then
      entry.sub.tick(event.tick)
    end
  end
  if not any_pending() then
    script.on_event(defines.events.on_tick, nil)
  end
end

---Join the clock. Main chunk only: a subsystem registered later is one on_load never saw.
---@param name string
---@param sub Jamaltron.ClockSubsystem
function M.register(name, sub)
  for _, entry in ipairs(subsystems) do
    if entry.name == name then
      error("jamaltron clock: '" .. name .. "' registered twice")
    end
  end
  subsystems[#subsystems + 1] = {name = name, sub = sub}
end

---A subsystem just left work for a later tick. Registers on_tick only if some pending() says so:
---a stray call never leaves a registration on_load would not re-derive.
function M.wake()
  if any_pending() then
    script.on_event(defines.events.on_tick, on_tick)
  end
end

---control.lua calls this once. on_load re-derives the on_tick registration, then runs `derive`
---(the mod's one other conditional registration, attack.lua's damage filter, held to the same
---pure-read-of-storage rule) and nothing else.
---@param derive fun()?
function M.install(derive)
  script.on_load(function()
    M.wake()
    if derive then derive() end
  end)
end

---The end of on_init and on_configuration_changed: registered iff pending, BOTH ways. With
---changed mods on_load runs BEFORE on_configuration_changed, so work that handler adds (or
---drops) would leave the host holding what a later joiner does not derive - a desync. Nothing
---there touches clock work today; this keeps it true when something does. migrations/ files
---need none: MEASURED 2.1.17, Lua migrations run before on_load, which derives from their result.
function M.sync()
  script.on_event(defines.events.on_tick, any_pending() and on_tick or nil)
end

---HARNESS ONLY: the invariant the rules above protect - registered exactly while pending.
---@return {registered: boolean, pending: boolean}
function M.state()
  return {registered = script.get_event_handler(defines.events.on_tick) ~= nil,
          pending = any_pending()}
end

return M
