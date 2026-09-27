-- Jamal's flamethrower as his mouth sees it (PLAN D.7): the two signals the `attacking` pool
-- needs (his gun started firing; his fire hurt something of his own side) and the BURST that
-- throttles them to one line. WHETHER a line gets out is speech.say's: `attacking` is AMBIENT
-- (the cooldown) and attacking.03 holds its burst window.
--
-- THE SIGNALS, both MEASURED on 2.1.17 + Space Age:
--   * C.fired, the custom event prototypes/ammo.lua puts on flamethrower ammo's vehicle stream,
--     source_entity = the vehicle that fired. Raised when a stream STARTS, and a stream restarts
--     whenever the aim point moves: once in 894 ticks of fire at a still target, about once per
--     firing tick at anything walking (34 of 34 at a small biter, 206 of 209 at a stomper). So a
--     real fight costs ~1.1 us per firing Jamal per tick, not one call per burst. A tank raises
--     it too; the name check drops it.
--   * on_entity_damaged: `cause` is the VEHICLE that fired, `source` the stream. His stream is a
--     radius-4 splash on force "all", so friendly fire is real and not small: flaming a biter 7
--     tiles off burned a character beside it for 252 (it has 250), a chest and a pole to death;
--     a stone wall took 191 hits for 0 (100% fire resistance) and does not count. He also burns
--     HIMSELF (20-30 hits of 0.04 at a small biter 2-4 tiles off, 1300 at a behemoth 3.2 off)
--     and a squad-mate standing in it (6708 hits of 0.04 in a minute, 2 tiles past a target).
--     Both are "self": not friendly fire, and no complaint from either.
--
-- ONE LINE PER BURST. A burst opens on a stream start once the gun has been quiet for
-- speech.BURST_GAP_TICKS, and stays open while he keeps firing (a new stream, or poll() seeing
-- his ammo count move). Its line is first tried HOLD_TICKS after it opened (the 15-tick clock, or
-- a stream start past that), so the opening volley has LANDED and a friendly hit it made is in
-- the roll; then at each later sign of fire until one is SAID, then not until the burst closes.
-- A cooldown or a pending chain delays the line while the burst stays open; a fight shorter than
-- the cooldown's remainder gets none (a finished fight is not narrated). attacking.03's window
-- holds by construction: the burst that said it is the burst the window covers, and the next
-- only starts after the gap the window waits for.
--
-- QUIET IS READ OFF THE AMMO, once a second, only for a Jamal with a burst open: a stream on a
-- still target raises nothing after its start. ANY change in rounds counts, spent or not: a bot
-- refilling him or a player emptying a slot mid-fight keeps the burst open, which only ever
-- makes him quieter.
--
-- FRIENDLY FIRE (lines.md Q11) is CONFIRMED damage, and only the burst's own: his cause, fire,
-- more than 0 after resistances, on an entity of his force that is not a Jamal body, while he has
-- a burst open. It makes the three `friendly` rows eligible in THAT burst's ordinary roll (never
-- a pick of its own) and closes with it, so the next fight's opening line never apologizes for
-- this one. A hit after the line is said changes nothing: a long fight that reaches the base late
-- gets no apology. What the damage filter leaves out never counts: units (biters, and anything a
-- mod puts on his side as one), spawners, worms, trees and rocks.
--
-- THE FILTER'S FIRE HALF IS REGISTERED ONLY WHILE SOME BURST IS OPEN. Without that, a base of
-- flamethrower turrets burning its own pipes and belts ran our handler 3.1 times a tick with no
-- Jamal within 500 tiles (MEASURED, D.7 review); with it, fire on anything but his bodies reaches
-- no Lua of ours unless one of him is firing. MULTIPLAYER: the storage flag IS the registration
-- (written only beside set_event_filter, read by on_load's derive through clock.install), so a
-- client joining mid-fight derives exactly what the host has.
--
-- State: the speech record's `fire` field (as speech/stall.lua keeps the shore episode), so it
-- saves, follows speech.transfer across a swap and dies with the record.

local C = require("prototypes.shared")
local speech = require("scripts.speech")

local M = {}

---How long a new burst's line waits for the opening volley. MEASURED: his first hit lands 11-17
---ticks after the stream starts (a chest, an ally, the fire-stat lanes), so 30 puts a friendly
---hit from that volley in the roll; the line lands 30-45 ticks into the fight.
M.HOLD_TICKS = 30

---Every body Jamal can be in. Airborne fires (MEASURED, see gun.lua; D.7.2 (c)). Beached is
---disarmed (D.7.3) but stays in: a squad-mate's splash on a beached Jamal still counts as self.
---@type table<string, boolean>
local OURS = {}
for _, name in ipairs(C.family) do
  OURS[name] = true
end
M.OURS = OURS

---@class Jamaltron.FireState
---@field at integer tick of the last sign of fire
---@field due integer? tick the burst's first roll is due; nil once it has been tried
---@field said boolean the burst's line has been said
---@field rolled string? the condition it was said under ("friendly"), for the harness
---@field rounds number? rounds in his ammo slots at the last poll
---@field friendly boolean? his fire confirmed a hit on his own side during THIS burst

---Rounds left across his ammo slots: whole magazines behind the top one, plus what the top one
---has left. Nil for an entity with no ammo inventory.
---@param entity LuaEntity
---@return number?
local function rounds(entity)
  local inv = entity.get_inventory(defines.inventory.spider_ammo)
  if inv == nil then return nil end
  local n = 0
  for i = 1, #inv do
    local stack = inv[i]
    if stack.valid_for_read then
      n = n + (stack.count - 1) * stack.prototype.magazine_size + stack.ammo
    end
  end
  return n
end

---@param f Jamaltron.FireState
---@return string? the gated condition this burst's roll is made under
local function condition(f)
  return f.friendly and "friendly" or nil
end

---The damage filter both ways, built by install(): `narrow` is his bodies, `wide` adds the fire
---half. Allowed module state (clock.lua): a pure function of code and prototypes, filled by
---control.lua's main chunk before on_load runs.
local filters = {narrow = {}, wide = {}}

---Register the fire half (true) or drop it, if that changes anything.
---@param on boolean
local function widen(on)
  local r = storage.jamaltron
  if (r.fire_filter == true) == on then return end
  r.fire_filter = on or nil
  script.set_event_filter(defines.events.on_entity_damaged, on and filters.wide or filters.narrow)
end

---A sign of fire at `now`: the open burst, or a new one when the gun had been quiet a whole gap.
---@param rec Jamaltron.SpeechRecord
---@param now integer
---@return Jamaltron.FireState
local function burst(rec, now)
  local f = rec.fire
  if f == nil or f.at == nil or now - f.at >= speech.BURST_GAP_TICKS then
    f = {at = now, due = now + M.HOLD_TICKS, said = false}
    rec.fire = f
    widen(true)
  else
    f.at = now
  end
  return f
end

---The burst's one line, if it has not had it and its first roll is due.
---@param entity LuaEntity
---@param f Jamaltron.FireState
---@param now integer
---@return string?
local function speak(entity, f, now)
  if f.said or (f.due and now < f.due) then return nil end
  f.due = nil
  local cond = condition(f)
  local id = speech.say(entity, "attacking", cond)
  if id then f.said, f.rolled = true, cond end
  return id
end

---control.lua's main chunk: `ours` is the name filters of every body that exists (swap.bodies).
---Returns the narrow filter, which the main chunk registers the damage handler with.
---
---The fire half: fire that got through resistances, on anything but what his stream burns all
---day (biters, spawners, worms, trees, rocks, Gleba's spiders, demolishers), which the engine
---drops before any Lua runs. Filters read left to right, `and` binding tighter than `or`.
---@param ours EventFilter[]
---@return EventFilter[]
function M.install(ours)
  local narrow, wide = {}, {}
  for _, filter in ipairs(ours) do
    narrow[#narrow + 1] = filter
    wide[#wide + 1] = filter
  end
  wide[#wide + 1] = {filter = "damage-type", type = "fire", mode = "or"}
  wide[#wide + 1] = {filter = "final-damage-amount", comparison = ">", value = 0, mode = "and"}
  for _, type in ipairs({"unit", "unit-spawner", "turret", "tree", "simple-entity", "spider-unit",
                         "segmented-unit"}) do
    wide[#wide + 1] = {filter = "type", type = type, invert = true, mode = "and"}
  end
  filters.narrow, filters.wide = narrow, wide
  return narrow
end

---@param wide boolean
---@return EventFilter[]
function M.filter(wide)
  return wide and filters.wide or filters.narrow
end

---on_load: the registration the host has, off the flag alone - a read, never a write.
function M.derive()
  local r = storage.jamaltron
  if r and r.fire_filter then
    script.set_event_filter(defines.events.on_entity_damaged, filters.wide)
  end
end

---His gun started a stream. Returns the row said, if any.
---@param entity LuaEntity?
---@param tick integer
---@return string?
function M.fired(entity, tick)
  if not (entity and entity.valid and OURS[entity.name]) then return nil end
  local rec = speech.record(entity, true)
  if rec == nil then return nil end
  return speak(entity, burst(rec, tick), tick)
end

---The C.fired event (prototypes/ammo.lua): raised by every vehicle that starts a flamethrower
---stream, so most arrivals are tanks.
---@param event {source_entity: LuaEntity?, tick: integer}
function M.on_fired(event)
  M.fired(event.source_entity, event.tick)
end

---The 15-tick clock: every burst whose first roll has come due gets it.
---@param tick integer
function M.deliver_due(tick)
  for _, rec in pairs(speech.records()) do
    local f = rec.fire
    if f and f.due and tick >= f.due and rec.entity.valid then
      speak(rec.entity, f, tick)
    end
  end
end

---What a damage event is to him: "self" when a Jamal body burned a Jamal body of its own side,
---himself or a squad-mate (control.lua keeps it out of the `damaged` pool); "friendly" when his
---fire confirmed a hit on anything else of his side (the friendly rows join this burst's roll,
---if one is open); else nil.
---@param event EventData.on_entity_damaged
---@return string?
function M.damaged(event)
  local cause = event.cause
  if not (cause and cause.valid and OURS[cause.name]) then return nil end
  local entity = event.entity
  if entity == cause then return "self" end                -- the commonest hit, the cheapest test
  if entity.force_index ~= cause.force_index then return nil end
  if OURS[entity.name] then return "self" end
  if event.final_damage_amount <= 0 or event.damage_type.name ~= "fire" then return nil end
  local rec = speech.record(cause, false)
  local f = rec and rec.fire
  -- No burst open: the gun has been quiet a whole gap, and this is fire it left behind.
  if f and f.at and event.tick - f.at < speech.BURST_GAP_TICKS then
    f.friendly = true
    speak(cause, f, event.tick)
  end
  return "friendly"
end

---The 1 Hz clock: every Jamal with a burst open re-reads his rounds (a change keeps it open and
---gives a still-unsaid line another try); a burst quiet for a whole gap closes, taking its
---friendly fire with it. The filter's fire half goes once no burst is open.
---@param tick integer
function M.poll(tick)
  local open = false
  for _, rec in pairs(speech.records()) do
    local f = rec.fire
    local entity = rec.entity
    if f and entity.valid then
      local now = rounds(entity)
      if f.rounds and now ~= f.rounds then
        f.at = tick
        speak(entity, f, tick)
      end
      f.rounds = now
      if f.at == nil or tick - f.at >= speech.BURST_GAP_TICKS then
        rec.fire = nil
      else
        open = true
      end
    end
  end
  if not open and storage.jamaltron.fire_filter then
    widen(false)
  end
end

---@class Jamaltron.FireView: Jamaltron.FireState
---@field open boolean the gun has not been quiet a whole gap yet
---@field cond string? the condition a roll made now would be under

---HARNESS ONLY: a copy of one Jamal's fire state.
---@param entity LuaEntity
---@return Jamaltron.FireView?
function M.state(entity)
  local rec = speech.record(entity, false)
  local f = rec and rec.fire
  if f == nil then
    return nil
  end
  return {open = f.at ~= nil and game.tick - f.at < speech.BURST_GAP_TICKS, said = f.said,
          at = f.at, due = f.due, friendly = f.friendly, rolled = f.rolled, rounds = f.rounds,
          cond = condition(f)}
end

return M
