-- Runtime stage entry point: event registration only, the behaviour lives in scripts/. D.5.3
-- wires the speech pools whose events exist today; E.2.2's shore stall rides speech.poll's
-- clock. D.4's body swap raises its own built, driving and replaced events, so the three
-- handlers that would take one for a build, a boarding or another mod's swap ask
-- swap.swapping first. on_tick and on_load belong to scripts/clock.lua alone.
-- THE JUMP LOOP: the key lands in jump.try (E.2.6), the arc flies on the clock (E.1), the
-- touchdown is breakage.on_landing (E.3/E.4) - clean or beached. A beached Jamal flops and
-- keeps his alert on the 60-tick clock (breakage.poll) and gets up at full health: a repair
-- pack's event here, construction bots (no event) on that same poll (E.5).
-- THE FLAMETHROWER (D.7): a stream start raises C.fired (prototypes/ammo.lua), his fire on his
-- own side arrives with the damage events, and scripts/attack.lua turns both into one
-- `attacking` line per burst - first tried on the 15-tick clock once the opening volley has
-- landed, the burst kept open off his ammo on the 60-tick clock.

local C = require("prototypes.shared")
local speech = require("scripts.speech")
local swap = require("scripts.swap")
local clock = require("scripts.clock")
local jump = require("scripts.jump")
local breakage = require("scripts.breakage")
local attack = require("scripts.attack")

---Every Jamal body that exists. The entity events below are filtered to them, so a base with a
---thousand turrets taking damage costs this mod nothing.
local ours = {}
for _, name in ipairs(swap.bodies()) do
  ours[#ours + 1] = {filter = "name", name = name}
end
---Building is the vehicle's alone: nobody places a beached shark.
local vehicle_only = {{filter = "name", name = C.name}}

---Damage: every body of his - and, only while one of him has a burst open, fire on his own side
---(attack.lua's friendly-fire gate: a chest, a turret, a character). attack.lua owns the fire
---half and switches it; the main chunk registers without it, and on_load derives it.
local damaged = attack.install(ours)

clock.register("swap", {pending = swap.pending, tick = swap.tick})
-- After swap: a landing swap made inside jump's tick leaves its t+1 work for the next tick.
clock.register("jump", {pending = jump.pending, tick = jump.tick})
clock.install(attack.derive)

-- The jump key (prototypes/input.lua), which exists only while jamaltron-jump-enabled is on. A
-- press with a GUI open is not a jump: a GUI may use whatever key it is bound to (Shift-click in
-- his own trunk, if rebound there). player.vehicle is the vehicle; a player remote-driving him
-- should get him there too (API: `vehicle` is the one driven, `physical_vehicle` the one sat
-- in - UNMEASURED headless) and jump.try refuses that by name.
if prototypes.custom_input[C.jump.input] then
  ---@param event EventData.CustomInputEvent
  script.on_event(C.jump.input, function(event)
    local player = game.get_player(event.player_index)
    if player and player.opened_gui_type == defines.gui_type.none and player.vehicle then
      jump.try(player.vehicle, player)
    end
  end)
end

-- Both end in clock.sync(): nothing registers on_tick for on_init (on_load never runs before it),
-- on_load's registration predates what on_configuration_changed changes, and a joining client
-- derives on_tick from the storage they leave (clock.lua).
script.on_init(function()
  speech.adopt_all()
  breakage.adopt_all()
  clock.sync()
end)

-- STORAGE OVER TIME (E.6). Three layers; the engine decides which runs (all MEASURED 2.1.17):
--   * a code-only update at the same version, no migration file added, runs NEITHER - only the
--     main chunk and on_load. So every module's root() lazily backfills what an older save
--     lacks, and a per-record field it cannot backfill must read nil as none
--   * a one-time reshape goes in migrations/<date>-<what>.lua. The engine runs each file ONCE
--     per save (reloaded, it did not run again), BEFORE on_load - so on_load re-derives the clock
--     from what it left, and it needs no clock.sync() - with the same module instances as this
--     file. It runs at the same version too, where no on_configuration_changed follows: one that
--     drops records whose bodies still stand ends with the adopt_all() calls below. Never drop
--     storage.jamaltron.swap without spilling its stashes: they are script inventories, and
--     nothing else holds the items
--   * this, on a version bump, a mod added or removed, a startup setting changed or a prototype
--     added - re-deriving from the MAP, never from a version number (the engine already keeps
--     which migrations a save has had, so storage holds none)
-- Removal needs nothing: the engine deletes his bodies, bubbles, sheets and script inventories,
-- drops his drivers where they sat (off water), and tells other mods through on_object_destroyed.
script.on_configuration_changed(function()
  -- A jamaltron from before speech existed gets a record. A beached one from before breakage
  -- existed (a playtest swap) gets his alert, flops and repair; an airborne one with no arc
  -- left lands on the next poll. Jumping switched off leaves arcs flying and bodies stranded:
  -- they land clean, and a beached one gets up (breakage.lua).
  speech.adopt_all()
  breakage.adopt_all()
  jump.adopt_all()
  clock.sync()
end)

---@param event {entity: LuaEntity}
local function built(event)
  -- A landing or a repair raises script_raised_built so other mods see him again; to him it
  -- is the body he had a moment ago, not a build.
  if swap.swapping(event.entity) then
    return
  end
  speech.say(event.entity, "built")
end
-- One registration per event: filters only apply to a single-event registration.
for _, name in pairs({defines.events.on_built_entity, defines.events.on_robot_built_entity,
                      defines.events.script_raised_built, defines.events.script_raised_revive}) do
  script.on_event(name, built, vehicle_only)
end

---@param event EventData.on_player_driving_changed_state
script.on_event(defines.events.on_player_driving_changed_state, function(event)
  local vehicle = event.entity
  -- A swap seats his driver in the new body with set_driver, which raises this: not a boarding.
  if not (vehicle and vehicle.valid and vehicle.name == C.name) or swap.swapping(vehicle) then
    return
  end
  local player = game.get_player(event.player_index)
  speech.say(vehicle, (player and player.vehicle == vehicle) and "enter" or "exit")
end)

---@param event EventData.on_entity_damaged
script.on_event(defines.events.on_entity_damaged, function(event)
  -- His own flames, or a squad-mate's, splash him at close range: attack.lua's "self", and never
  -- a complaint.
  if attack.damaged(event) == "self" then
    return
  end
  -- A killing blow is on_entity_died's line, not this.
  if attack.OURS[event.entity.name] and event.final_health > 0 then
    speech.damaged(event.entity)
  end
end, damaged)

-- Every flamethrower stream a vehicle starts, tanks included; attack.lua keeps his.
script.on_event(C.fired, attack.on_fired)

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
    -- After a swap this is the OLD body, at the end of the tick: the swap already moved his
    -- record and stash, so both find nothing.
    speech.forget(event.useful_id)
    swap.forget(event.useful_id)
    breakage.forget(event.useful_id)            -- a beached one takes his alert with him
    jump.forget(event.useful_id)                -- his cooldown and refusal ticks, never an arc
  end
end)

-- swap.lua keeps each player's quickbar remote slots between swaps (remote_slots): a slot the
-- player sets, or the player leaving the save, drops that player's.
---@param event {player_index: integer}
local function quickbar_changed(event)
  swap.quickbar_changed(event.player_index)
end
script.on_event(defines.events.on_player_set_quick_bar_slot, quickbar_changed)
script.on_event(defines.events.on_player_removed, quickbar_changed)

-- ANOTHER mod moving Jamal to a body of its own (Spidertron Enhancements parks a spider in a
-- dummy while its driver rides something else) takes his record along. Our own swaps raise
-- this BEFORE they move anything and hand the record over themselves once the trunk is
-- across - a transfer here would put it on a body a listener may still kill. Enhancements'
-- quick toggle into the engineer destroys him with no event at all and builds him back later,
-- so it costs his break count and once-per-save lines, like mining and re-placing him (E.6).
---@param event {old_spidertron: LuaEntity?, new_spidertron: LuaEntity?}
script.on_event("on_spidertron_replaced", function(event)
  local old, new = event.old_spidertron, event.new_spidertron
  if old and old.valid and new and new.valid and old.unit_number and not swap.swapping(old) then
    speech.transfer(old.unit_number --[[@as integer]], new)
    breakage.transfer(old.unit_number --[[@as integer]], new)
  end
end)

-- Chains land to within a quarter second (their delays are multiples of 30 ticks); the
-- slow clock - the shore stall, idle, moving, low-health re-arming, a stash that outlived
-- its t+1 - needs no better than a second (the stall detector's thresholds are per 1 Hz
-- poll: change this, retune those).
script.on_nth_tick(15, function(event)
  speech.deliver_due(event.tick)
  attack.deliver_due(event.tick)                -- a burst's first line, once its volley landed
end)
script.on_nth_tick(60, function(event)
  speech.poll(event.tick)
  swap.poll()
  breakage.poll(event.tick)
  jump.poll()                                   -- a landing that kept failing, tried again
  attack.poll(event.tick)
end)

-- E.5: a repair pack taking a beached Jamal to full health stands him up inside its own event;
-- bots raise none and are breakage.poll's. The handler REPLACES the event's entity; a real
-- repair reaches it only under play.sh (headless has no LuaPlayer). If that misbehaves,
-- on_repaired returns early and the poll stands him up within a second. A filter on an unbuilt
-- name is an error, hence the guard.
if prototypes.entity[C.beached] then
  script.on_event(defines.events.on_player_repaired_entity, breakage.on_repaired,
                  {{filter = "name", name = C.beached}})
  -- A clone copies the body, not his record or his broken legs: kept from now (the filter is on
  -- the source, which has the same name).
  script.on_event(defines.events.on_entity_cloned, breakage.on_cloned,
                  {{filter = "name", name = C.beached}})
end

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
  ---E.1's comparison switch, map-wide: "arc" (default) or "teleport"; nil reads it.
  ---@param mode string?
  ---@return string
  jump_mode = function(mode)
    return jump.mode(mode)
  end,
})

-- The D.5.4 / D.4.7 / E / F.1 harnesses' handles on the speech, swap, jump and break state. Not
-- for other mods: `force` skips every gate the catalog's rules put in front of a line, `swap`
-- and `land` every check jump.try puts in front of a body change.
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
  ---@return table
  census = function()
    return speech.census()
  end,
  ---A remote call returns one value, so the swap's two come back as one table.
  ---@param entity LuaEntity
  ---@param name string
  ---@param opts Jamaltron.SwapOpts?
  ---@return {body: LuaEntity?, status: string}
  swap = function(entity, name, opts)
    local body, status = swap.replace(entity, name, opts)
    return {body = body, status = status}
  end,
  ---@param entity LuaEntity?
  ---@return table
  swap_state = function(entity)
    return swap.state(entity)
  end,
  ---@return {registered: boolean, pending: boolean}
  clock = function()
    return clock.state()
  end,
  ---What the jump key does, for a harness with no LuaPlayer: the driver's jump when `presser`
  ---is nil, else a press by that player index or by that CHARACTER standing in for a player (a
  ---passenger's press is refused on the same comparison a real one is). Returns jump.try's
  ---three values as one table.
  ---@param entity LuaEntity
  ---@param presser (integer|LuaEntity)?
  ---@return {jumped: boolean, why: string?, said: string?}
  jump = function(entity, presser)
    local who = type(presser) == "number" and game.get_player(presser) or presser
    local jumped, why, said = jump.try(entity, who --[[@as (LuaPlayer|LuaEntity)?]])
    return {jumped = jumped, why = why, said = said}
  end,
  ---@param entity LuaEntity?
  ---@return table
  jump_state = function(entity)
    return jump.state(entity)
  end,
  ---Write one of OUR runtime-global settings. Only the mod that owns a setting may (measured:
  ---"Settings can only be changed by the owning player or the mod that made the setting"), so a
  ---harness that pins the leg-break roll or the jump distance comes through here.
  ---@param name string
  ---@param value boolean|number|string
  setting = function(name, value)
    assert(name:find("^jamaltron%-"), "not a jamaltron setting: " .. tostring(name))
    settings.global[name] = {value = value}
  end,
  ---E.3/E.4 without the arc: land an airborne body the way jump.lua's touchdown does (the
  ---break roll, the one swap, the thud, the line). One table back, as `swap`.
  ---@param airborne LuaEntity
  ---@param spot MapPosition?
  ---@param info {tick: integer?, height: number?, distance: number?, driver: (LuaEntity|LuaPlayer)?}?
  ---@return {body: LuaEntity?, outcome: string}
  land = function(airborne, spot, info)
    local body, outcome = breakage.on_landing(airborne, spot, info)
    return {body = body, outcome = outcome}
  end,
  ---@param entity LuaEntity?
  ---@return {kept: boolean, flop_at: integer?, alert_at: integer?, position: MapPosition?, beached: integer}
  breakage_state = function(entity)
    return breakage.state(entity)
  end,
  ---on_configuration_changed's breakage half, on demand: every beached body on the map kept, and
  ---any legs gone or drawn to another geometry redrawn.
  adopt_all = function()
    breakage.adopt_all()
  end,
  ---A beached body `swap` made (the playtest's /jamaltron-swap beached): kept by breakage from
  ---now, capped at half health, so its alert, flops and repair run as after a real break.
  ---@param entity LuaEntity
  ---@return boolean
  keep = function(entity)
    return breakage.keep(entity)
  end,
  ---An airborne body `swap` made (the playtest's /jamaltron-swap airborne) has no arc, and without
  ---this it stays invisible, locked and unlandable until on_configuration_changed (measured over
  ---1300 ticks): stranded now, it lands where it sits on the next poll. False when it is flying.
  ---@param entity LuaEntity
  ---@return boolean
  strand = function(entity)
    return jump.adopt(entity)
  end,
  ---The repair-pack path with no LuaPlayer: whatever handler this file REGISTERED for
  ---on_player_repaired_entity, called with the fields it reads (entity, tick) - so a lost
  ---registration fails the harness too. The event's name filter is not exercised. The harness
  ---sets the health first, as a pack would have.
  ---@param entity LuaEntity
  repaired = function(entity)
    local handler = script.get_event_handler(defines.events.on_player_repaired_entity)
    assert(handler, "nothing is registered for on_player_repaired_entity")
    handler({entity = entity, tick = game.tick, name = defines.events.on_player_repaired_entity,
             player_index = 0})
  end,
  ---D.7: one Jamal's gun state, attack.lua's.
  ---@param entity LuaEntity
  ---@return table?
  attack_state = function(entity)
    return attack.state(entity)
  end,
  ---D.7: the damage filter the engine holds for this mod right now - the fire half is there only
  ---while some burst is open.
  ---@return EventFilter[]?
  damage_filter = function()
    return script.get_event_filter(defines.events.on_entity_damaged)
  end,
  ---D.7's cost per event through what this file REGISTERED - the C.fired handler and the damage
  ---handler - `n` calls each, with the fields they read: `entity` starting a stream mid-burst
  ---(line already said), `entity` burning `victim` (friendly: record, burst, no line), `other`
  ---burning `entity` (fire that is not his: speech.damaged's path, through the cooldown), and
  ---`other` starting a stream (a tank), `entity` splashing himself or `buddy`; attack.poll's 1 Hz
  ---pass over every record there is, and the 15-tick deliver_due's. The engine's own dispatch is
  ---not in it.
  ---@param entity LuaEntity
  ---@param victim LuaEntity of his force, not a Jamal
  ---@param other LuaEntity a vehicle that is not his
  ---@param buddy LuaEntity another Jamal of his force
  ---@param n integer
  ---@return table<string, LuaProfiler>
  attack_cost = function(entity, victim, other, buddy, n)
    local on_fired = script.get_event_handler(C.fired)
    local on_damaged = script.get_event_handler(defines.events.on_entity_damaged)
    assert(on_fired and on_damaged, "D.7's handlers are not registered")
    local tick, fire = game.tick, prototypes.damage["fire"]
    attack.fired(entity, tick)                            -- open his burst, its line said
    local rec = speech.record(entity, false)
    if rec and rec.fire then rec.fire.said, rec.fire.due = true, nil end
    local cases = {
      fired = {on_fired, {source_entity = entity, tick = tick}},
      tank = {on_fired, {source_entity = other, tick = tick}},
      friendly = {on_damaged, {cause = entity, entity = victim, final_damage_amount = 1,
                               final_health = 99, damage_type = fire, tick = tick}},
      bitten = {on_damaged, {cause = other, entity = entity, final_damage_amount = 1,
                             final_health = 2999, damage_type = fire, tick = tick}},
      self = {on_damaged, {cause = entity, entity = entity, final_damage_amount = 0.04,
                           final_health = 2999, damage_type = fire, tick = tick}},
      buddy = {on_damaged, {cause = entity, entity = buddy, final_damage_amount = 0.04,
                            final_health = 2999, damage_type = fire, tick = tick}},
      poll = {attack.poll, tick},
      deliver = {attack.deliver_due, tick},
    }
    local out = {}
    for key, case in pairs(cases) do
      local profiler = helpers.create_profiler()
      for _ = 1, n do case[1](case[2]) end
      profiler.stop()
      out[key] = profiler
    end
    return out
  end,
  ---The per-tick cost of every arc in the air: `n` re-flies of this tick's writes, timed.
  ---@param n integer
  ---@return LuaProfiler
  jump_cost = function(n)
    local profiler = helpers.create_profiler()
    for _ = 1, n do jump.refly(game.tick) end
    profiler.stop()
    return profiler
  end,
})
