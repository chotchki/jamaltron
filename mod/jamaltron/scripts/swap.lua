-- Jamal changes bodies (PLAN D.4). ONE Jamal, three spider-vehicle prototypes (jamaltron,
-- jamaltron-beached, jamaltron-airborne); replace() moves everything that makes him HIM from one
-- to the next. A jump is two swaps ~30 ticks apart (takeoff, landing), a break on landing ONE
-- (airborne -> beached), a repair one.
--
-- CREATE-FIRST: B is built on top of A, filled, the people moved across while A still holds
-- them, and only then is A destroyed. Nobody is left behind: a character's `vehicle` goes
-- straight from A to B, or over water out of A's seat and into B's in one call (seat()), where
-- destroy-first ejects and displaces them.
--
-- ATOMIC ONLY UP TO THE MOVE, and the second return value says which side a failure fell on:
--   B,   "ok"
--   nil, "refused"  A invalid, no unit number, or already mid-swap. A untouched
--   nil, "failed"   B could not be created, or died (another mod's handler) before anything
--                   but the people left A. B is gone, the people are back in A: A is whole
--   nil, "lost"     B died AFTER the trunk moved into it. A is destroyed too, so no empty Jamal
--                   is ever left standing: he is gone, as with any vehicle a mod destroys. Also
--                   a listener destroying A itself mid-swap: B goes with it
-- An ERROR thrown inside (a listener that throws) is unwound the same way (before the move back
-- into A, after it forward into B) and re-raised. E must never pcall-and-continue around
-- replace(): listeners that already heard on_spidertron_replaced are not told.
--
-- CARRIED, and how (every row measured on 2.1.17 by the D.4 spikes and harness unless marked):
--   position, force, quality      create_entity. Quality scales the trunk 80/128/200 and max
--                                 health 3000/4800/7500; force defaults to ENEMY
--   color, label, gunner, gun     create_entity params: they raise no events, where writing
--   index, targeting, logistics   color or label afterwards raises on_entity_color_changed
--   while moving                  and on_entity_renamed
--   torso                         written after create, which spawns facing 0.375. A spider's
--                                 `orientation` IS its torso's, quantized to the body's sprite
--                                 directions: writing one rewrites the other, and D.1's
--                                 one-direction beached body reads 0 whatever is written
--   health                        the RATIO times B's max
--   name_tag, last_user, destructible, minable_flag, rotatable, protected, tooltip fields,
--   allow_dispatching_robots, request_from_buffers                                  written
--   disabled_by_script, operable, M.BODY - the TARGET's, not A's. disabled at t+1, and only
--   custom_status                 onto a body that could walk without it
--   deconstruction mark           order_deconstruction, before minable_flag (refused after)
--   logistic sections             B's default section removed, each re-added by group
--   logistic point flags          enabled + trash_not_requested at t+0 AND t+1
--   grid                          put by quality and position: ghosts, removal marks, energy,
--                                 shield, inhibit_movement_bonus. NEVER create_entity{grid=}:
--                                 it segfaults 2.1.17. Burner-equipment fuel slot by slot
--                                 (modded only, vanilla has none - UNMEASURED)
--   trunk, ammo, trash            filters, then swap_stack slot by slot: quality, item
--                                 health, spoilage, blueprints, nested labels, item_number
--   pending bot deliveries        A's proxies' plans written into B's own proxy
--   queue, patrol, follow         follow XOR queue - each clears the other
--   spiders following him         re-pointed, offsets kept
--   proxy containers on him       re-pointed, target inventory kept: Spidertron Patrols' dock
--                                 moves its own record on on_spidertron_replaced and never the
--                                 dock's target, which went nil for good (measured, E.6)
--   driver, passenger             set_driver/set_passenger while A holds them - which needs
--                                 ground to step out onto (see seat()). A REMOTE driver is NOT
--                                 seated (see read())
--   held direction                set_driver RESETS the driver's walking_state (measured:
--                                 walking = false on the airborne body right after takeoff).
--                                 Written back onto the DRIVER in the vehicle and in a transit
--                                 body (airborne, which cannot walk on it - D.1), and read off
--                                 the driver again at the landing: held, he lands walking; let
--                                 go mid-arc, he lands standing (scripted driver, measured)
--   stickers                      re-created with their own force and time left
--   speech record                 speech.transfer - the pending chain does not ride
--   player side                   remote selection, quickbar remotes, pins, an open GUI, the
--                                 remote-view camera - UNMEASURED, no LuaPlayer headless. The
--                                 quickbar is scanned once per player and cached (remote_slots)
-- LOST, by physics, not omission:
--   * momentum: speed is not writable, so he stops dead and re-accelerates
--   * the leg pose: B's legs spawn in one fixed pose whatever B faces and walk back over ~40
--     ticks; nothing re-lays them
--   * unit_number and the grid's unique_id - re-keyed here, told to other mods through
--     on_spidertron_replaced
--   * an upgrade mark (its target names A's prototype), sticker damage attribution
--   * fuel in a burner equipment that does not fit B's grid (only a drifted prototype)
-- A TICK LATE, hence a clock subsystem:
--   * a toolbelt's +10 trunk slots exist only from t+1, so t+0 overflow waits in a STASH
--   * disabled_by_script written on the swap tick stops those slots (and the vehicle_storage
--     logistic point) from EVER arriving, so it is written at t+1. Every swap into a disabled
--     body leaves it ENABLED for that one tick, and the grid, the autopilot and a held key all
--     run in it: E.4/E.5 must never read `speed == 0` as stopped. D.1's immobile-by-prototype
--     bodies skip all of this (nothing is disabled)
--
-- EVENTS, in the order the world sees them, every one raised INSIDE replace():
--   on_marked_for_deconstruction     B, when A carried the mark
--   on_equipment_inserted            one per grid.put - the engine's, unavoidable
--   on_spidertron_replaced           {old_spidertron, new_spidertron, jamaltron_reason}, both
--                                    valid, B not yet filled - Spidertron Enhancements' own
--                                    order, and the one point where a listener killing B
--                                    costs nothing (A is still whole)
--   on_player_driving_changed_state  set_driver/set_passenger, a real player (DOCUMENTED)
--   on_gui_opened / closed           a player who had A open gets B (UNMEASURED)
--   script_raised_destroy            A, still valid and already empty - unless A is SILENT
--   script_raised_built              B, full and seated - unless B is SILENT
--   on_object_destroyed              A's unit, at the end of the tick, after all of it
-- The airborne body is SILENT: to a mod that only knows built/destroy a jump reads as "Jamal
-- left, a Jamal landed", and a 30-tick body never enters anyone's tables. control.lua's built,
-- driving and replaced handlers ask M.swapping first (a body change is not a build or a
-- boarding); that guard only sees swaps through THIS module instance, so E requires
-- scripts.swap and other mods go through the remote interface.

local C = require("prototypes.shared")
local speech = require("scripts.speech")
local clock = require("scripts.clock")

local M = {}

---Bodies no built/destroy event ever announces.
M.SILENT = {[C.airborne] = true}

---What each body IS, written onto it whatever A was (D.4.1): carrying A's state was once the
---default, and a disabled airborne body LANDED FROZEN for good (measured: 0 tiles in 60 ticks
---with a destination). A's own value rides only when the name does not change (another mod's
---disable survives that mod swapping him) or into a body not listed here; opts beats all.
---  still          he must not walk in it. D.1 builds beached and airborne IMMOBILE BY
---                 PROTOTYPE (a burner with no fuel slot, measured: still enabled, toolbelt,
---                 logistics and guns intact), and such a body is left enabled. A body that
---                 CAN walk (a harness stand-in, a D.1 that changed tack) is held with
---                 disabled_by_script instead, written at t+1 (see the header)
---  operable       airborne's GUI is a 30-tick window the landing would have to carry
---  custom_status  false clears it; beached needs one, since the engine's own says "No fuel"
---  transit        he is only passing through: a held direction is written back onto his
---                 driver for the landing to read. A break is not transit: he stops, and a
---                 repair minutes later must not walk off on a key let go of long ago
---@type table<string, {still: boolean, operable: boolean, custom_status: CustomEntityStatus|false, transit: boolean?}>
M.BODY = {
  [C.name] = {still = false, operable = true, custom_status = false},
  [C.beached] = {still = true, operable = true,
                 custom_status = {diode = defines.entity_status_diode.red,
                                  label = {"jamaltron-status.beached"}}},
  [C.airborne] = {still = true, operable = false, custom_status = false, transit = true},
}

local INVENTORIES = {defines.inventory.spider_trunk, defines.inventory.spider_ammo,
                     defines.inventory.spider_trash}

---Units whose swap is on the stack RIGHT NOW. Module state, multiplayer-safe for one reason
---only: it is non-empty strictly inside replace(), and every event it guards is delivered
---synchronously inside that call, so no tick boundary, save or join lands while it holds
---anything, and every peer and reloaded save sees it empty. Do NOT read it from
---on_object_destroyed: that fires at the end of the tick, after the call returned.
---@type table<integer, true>
local swapping = {}

---@class Jamaltron.SwapOpts
---@field reason string? break | repair | takeoff | landing; rides on on_spidertron_replaced
---@field position MapPosition? where B stands; A's position when nil (a landing passes the spot)
---@field autopilot boolean? false drops the waypoint queue AND the follow target (a takeoff, E.6)
---@field disabled boolean? B's disabled_by_script over M.BODY's (whatever the prototype)
---@field custom_status (CustomEntityStatus|false)? over M.BODY's; false clears it

---@class Jamaltron.StashPart
---@field inv LuaInventory stacks kept at the slot index they had in the body they left
---@field filters table<integer, ItemFilter>

---@class Jamaltron.Stash
---@field entity LuaEntity the body it belongs to, re-pointed every swap
---@field surface LuaSurface where it spills if that body is destroyed first
---@field position MapPosition
---@field parts table<defines.inventory, Jamaltron.StashPart>

---@class Jamaltron.Due
---@field entity LuaEntity
---@field tick integer
---@field points table<defines.logistic_member_index, {enabled: boolean, trash_not_requested: boolean}>
---@field disabled boolean

---@class Jamaltron.SwapCtx one replace() call, shared with the unwind that may follow it
---@field old LuaEntity
---@field old_unit integer
---@field old_name string
---@field name string
---@field opts Jamaltron.SwapOpts
---@field held integer[] units this call put in `swapping`
---@field s table? read(old)
---@field new LuaEntity?
---@field phase ("made"|"seated"|"moved"|"done")? how far it got
---@field status string?
---@field fallback ItemStackDefinition[] equipment B's grid had no room for, as items
---@field burners {src: LuaEquipment, dst: LuaEquipment}[]
---@field rekeyed true?
---@field fell true?
---@field transferred true?

---@class Jamaltron.SwapRoot
---@field due table<integer, Jamaltron.Due> t+1 work, by the unit it is for
---@field stash table<integer, Jamaltron.Stash>
---@field remotes table<integer, integer[][]> by player index, the quickbar slots ({page, index})
---  holding a spidertron remote - see remote_slots

---@return Jamaltron.SwapRoot
local function root()
  storage.jamaltron = storage.jamaltron or {}
  local r = storage.jamaltron
  r.swap = r.swap or {due = {}, stash = {}}
  r.swap.remotes = r.swap.remotes or {}
  return r.swap
end

---Every spider-vehicle prototype name, for game.get_vehicles. A pure function of the
---prototypes: the same on every peer, never saved.
---@type string[]?
local spider_names = nil

---Body name -> it cannot walk by construction: D.1's dead engine, a burner with no fuel slot.
---Same kind of cache as spider_names.
---@type table<string, boolean>
local dead_engine = {}

---@param name string
---@return boolean
local function immobile(name)
  local known = dead_engine[name]
  if known == nil then
    local burner = prototypes.entity[name].burner_prototype
    known = burner ~= nil and burner.fuel_inventory_size == 0
    dead_engine[name] = known
  end
  return known
end

---@return string[]
local function spiders()
  if spider_names == nil then
    spider_names = {}
    for name in pairs(prototypes.get_entity_filtered{{filter = "type", type = "spider-vehicle"}}) do
      spider_names[#spider_names + 1] = name
    end
  end
  return spider_names
end

---The family members D.1 has built so far, for event filters (an unbuilt name is an error in a
---filter).
---@return string[]
function M.bodies()
  local names = {}
  for _, name in ipairs(C.family) do
    if prototypes.entity[name] then names[#names + 1] = name end
  end
  return names
end

---Is this entity one side of a swap in progress? For control.lua's built, driving and replaced
---handlers: a body change is neither a build nor a boarding.
---@param entity LuaEntity?
---@return boolean
function M.swapping(entity)
  return entity ~= nil and entity.valid and entity.unit_number ~= nil
    and swapping[entity.unit_number --[[@as integer]]] == true
end

---Is there t+1 work waiting? A read, never a write: on_load calls it through the clock.
---@return boolean
function M.pending()
  local r = storage.jamaltron and storage.jamaltron.swap
  return r ~= nil and next(r.due) ~= nil
end

---The stash part for one inventory of `unit`, created on first use.
---@param r Jamaltron.SwapRoot
---@param unit integer
---@param entity LuaEntity
---@param index defines.inventory
---@param size integer
---@return Jamaltron.StashPart
local function stash_part(r, unit, entity, index, size)
  local st = r.stash[unit]
  if st == nil then
    st = {entity = entity, surface = entity.surface, position = entity.position, parts = {}}
    r.stash[unit] = st
  end
  local part = st.parts[index]
  if part == nil then
    part = {inv = game.create_inventory(size), filters = {}}
    st.parts[index] = part
  elseif #part.inv < size then
    part.inv.resize(size)
  end
  return part
end

---Park one stack in the stash at slot `i`, or anywhere in it if an older stash holds that slot.
---@param part Jamaltron.StashPart
---@param i integer
---@param stack LuaItemStack
local function park(part, i, stack)
  local slot = part.inv[i]
  if slot.valid_for_read then
    local spare = part.inv.find_empty_stack()
    if spare == nil then
      part.inv.resize(#part.inv + 1)
      spare = part.inv[#part.inv]
    end
    slot = spare
  end
  slot.swap_stack(stack)
end

---Move one inventory slot by slot: filters first (a filtered slot refuses anything else), then
---each stack with swap_stack, which keeps what name + count would lose (quality, item health,
---spoil progress, a blueprint, a nested vehicle's label, even the item_number). NOT
---transfer_from_inventory: it compacts the layout. Whatever B has no slot for goes to the stash.
---Idempotent: a second pass over an emptied source moves nothing.
---@param src LuaInventory
---@param dst LuaInventory?
---@param stash fun(size: integer): Jamaltron.StashPart
local function move(src, dst, stash)
  local size = #src
  if src.supports_filters() then
    for i = 1, size do
      local filter = src.get_filter(i)
      if filter then
        if dst and i <= #dst and dst.supports_filters() then
          dst.set_filter(i, filter)
        else
          stash(size).filters[i] = filter
        end
      end
    end
  end
  for i = 1, size do
    local stack = src[i]
    if stack.valid_for_read and not (dst and i <= #dst and not dst[i].valid_for_read
                                     and dst[i].swap_stack(stack)) then
      park(stash(size), i, stack)
    end
  end
end

---Hand back whatever the stash holds that `entity` has room for now: the slot it came from if
---that exists and is free, else the first free slot (an active spider re-sorts his trunk every
---tick anyway; only filtered slots and ammo keep their places). Idempotent.
---@param r Jamaltron.SwapRoot
---@param unit integer
local function settle(r, unit)
  local st = r.stash[unit]
  if st == nil or not st.entity.valid then return end
  local entity = st.entity
  st.surface, st.position = entity.surface, entity.position
  for index, part in pairs(st.parts) do
    local dst = entity.get_inventory(index)
    if dst then
      for i, filter in pairs(part.filters) do
        if i <= #dst then
          dst.set_filter(i, filter)
          part.filters[i] = nil
        end
      end
      for i = 1, #part.inv do
        local stack = part.inv[i]
        if stack.valid_for_read then
          local slot = i <= #dst and dst[i] or nil
          if not (slot and not slot.valid_for_read and slot.swap_stack(stack)) then
            slot = dst.find_empty_stack({name = stack.name, quality = stack.quality})
            if slot then slot.swap_stack(stack) end
          end
        end
      end
    end
    if next(part.filters) == nil and part.inv.is_empty() then
      part.inv.destroy()
      st.parts[index] = nil
    end
  end
  if next(st.parts) == nil then
    r.stash[unit] = nil
  end
end

---Everything about A that B cannot be created with, read before anything moves.
---
---The DRIVER is classified here. get_driver() is a character, or a LuaPlayer: one with no
---character sitting in A (physical_vehicle is A), or one REMOTE-driving A from elsewhere. What
---set_driver does with a remote player is unmeasured and could drag their character across the
---map, so a remote driver is kept apart and never seated (D.4.8 measures it; until then E.2
---refuses a jump while remote-driven).
---@param a LuaEntity
---@return table
local function read(a)
  local s = {
    torso = a.torso_orientation, ratio = a.get_health_ratio(),
    name_tag = a.name_tag, last_user = a.last_user, tooltip = a.get_tooltip_fields(),
    disabled = a.disabled_by_script, custom_status = a.custom_status,
    destructible = a.destructible, minable_flag = a.minable_flag, operable = a.operable,
    rotatable = a.rotatable, protected = a.protected,
    dispatching = a.allow_dispatching_robots, from_buffers = a.request_from_buffers,
    decon = a.to_be_deconstructed() and a.force or nil,
    destinations = a.autopilot_destinations, patrol = a.autopilot_patrol_size,
    follow = a.follow_target, follow_offset = a.follow_offset,
    driver = a.get_driver(), passenger = a.get_passenger(),
    points = {}, sections = {}, equipment = {}, stickers = {}, followers = {},
  }
  local driver = s.driver
  if driver and driver.object_name == "LuaPlayer" and driver.physical_vehicle ~= a then
    s.remote, s.driver = driver, nil
  end
  for _, point in pairs(a.get_logistic_point() or {}) do
    s.points[point.logistic_member_index] = {enabled = point.enabled,
                                              trash_not_requested = point.trash_not_requested}
  end
  local sections = a.get_logistic_sections()
  for _, section in pairs(sections and sections.sections or {}) do
    if section.is_manual then
      -- A grouped section's filters belong to the force-wide group: the name brings them.
      s.sections[#s.sections + 1] = {group = section.group, active = section.active,
        multiplier = section.multiplier, filters = section.group == "" and section.filters or nil}
    end
  end
  local grid = a.grid
  if grid then
    s.inhibit = grid.inhibit_movement_bonus
    for _, eq in pairs(grid.equipment) do
      local ghost = eq.type == "equipment-ghost"
      s.equipment[#s.equipment + 1] = {
        name = ghost and eq.ghost_name or eq.name, quality = eq.quality, position = eq.position,
        ghost = ghost, energy = not ghost and eq.energy or nil,
        shield = (not ghost and eq.max_shield > 0) and eq.shield or nil, removal = eq.to_be_removed,
        src = (not ghost and eq.burner) and eq or nil}
    end
  end
  for _, sticker in pairs(a.stickers or {}) do
    s.stickers[#s.stickers + 1] = {name = sticker.name, ttl = sticker.time_to_live,
                                   force = sticker.force}
  end
  -- No API lists who follows an entity. get_vehicles scans every spider-vehicle on the surface:
  -- 0.004 ms on an empty map, 0.38 ms with 1000 (measured), the swap's one per-map cost.
  for _, vehicle in pairs(game.get_vehicles{surface = a.surface, type = spiders()}) do
    if vehicle ~= a and vehicle.follow_target == a then
      s.followers[#s.followers + 1] = {entity = vehicle, offset = vehicle.follow_offset}
    end
  end
  -- Bots delivering to his trunk or grid. A proxy sits exactly on its target, so radius 1
  -- finds them all (0.003 ms; a surface-wide scan was 0.41 ms).
  for _, proxy in pairs(a.surface.find_entities_filtered{name = "item-request-proxy",
                                                         position = a.position, radius = 1}) do
    if proxy.proxy_target == a then
      s.plans = s.plans or {insert = {}, removal = {}}
      for _, plan in pairs(proxy.insert_plan) do s.plans.insert[#s.plans.insert + 1] = plan end
      for _, plan in pairs(proxy.removal_plan) do s.plans.removal[#s.plans.removal + 1] = plan end
    end
  end
  driver = s.driver
  s.walking = driver and driver.valid and driver.walking_state or nil
  return s
end

---Replace `old` with `new` in `list`; nil when it was not in the list.
---@param list LuaEntity[]?
---@param old LuaEntity
---@param new LuaEntity
---@return LuaEntity[]?
local function repoint(list, old, new)
  local hit = false
  for i, entity in pairs(list or {}) do
    if entity == old then
      list[i], hit = new, true
    end
  end
  return hit and list or nil
end

---The quickbar slots of `player` that hold a spidertron remote, as {page, index}. A scan is 100
---get_quick_bar_slot calls, and carry_saved runs for EVERY player of his force, offline included,
---twice a jump, so a long-lived server paid players-ever-joined x 100 calls a swap (UNMEASURED:
---headless has no LuaPlayer; ~0.5 us a call puts 100 players at ~5 ms). Scanned once, kept in
---storage (same on every peer) until M.quickbar_changed drops it: the engine raises
---on_player_set_quick_bar_slot for any slot a player sets, emptied included. A mod writing a
---remote slot by script raises nothing (INFERRED) and is missed until that player's next change;
---at worst a quickbar remote that lost him, same as a guarded() failure.
---@param player LuaPlayer
---@return integer[][]
local function remote_slots(player)
  local r = root()
  local known = r.remotes[player.index]
  if known == nil then
    known = {}
    for page = 1, 10 do
      for index = 1, 10 do
        local slot = player.get_quick_bar_slot(page, index)
        if slot and slot.type == "remote" then known[#known + 1] = {page, index} end
      end
    end
    r.remotes[player.index] = known
  end
  return known
end

---Tiles round A searched for proxy containers aimed at him. A dock only takes a spider standing
---on it (Patrols: the dock's box plus 0.4), so this is generous.
M.PROXY_RADIUS = 4

---Every proxy container near A whose target is A now targets B, on the same inventory. Vanilla
---builds none on a spider; Spidertron Patrols' dock does, and a dock whose target died with A
---stayed empty while Patrols still believed him docked (measured). A write, never an event, so
---no listener runs here.
---@param surface LuaSurface
---@param old LuaEntity
---@param new LuaEntity
local function carry_proxies(surface, old, new)
  for _, proxy in pairs(surface.find_entities_filtered{type = "proxy-container", position = old.position,
                                                       radius = M.PROXY_RADIUS}) do
    if proxy.proxy_target_entity == old then
      local inventory = proxy.proxy_target_inventory
      proxy.proxy_target_entity = new
      proxy.proxy_target_inventory = inventory
    end
  end
end

---A player's SAVED hold on him (quickbar remote slots, pins), which an offline teammate still
---has on return, so every player of his force, connected or not.
---@param player LuaPlayer
---@param old LuaEntity
---@param new LuaEntity
local function carry_saved(player, old, new)
  for _, at in ipairs(remote_slots(player)) do
    local slot = player.get_quick_bar_slot(at[1], at[2])
    if slot and slot.type == "remote" and repoint(slot.selection, old, new) then
      player.set_quick_bar_slot(at[1], at[2], slot)
    end
  end
  for _, pin in pairs(player.get_pins()) do
    local targets = repoint(pin.targets, old, new)
    if targets then pin.targets = targets end
  end
end
M.carry_saved = carry_saved                        -- for tools/tests/lua/test_swap_quickbar.lua

---on_player_set_quick_bar_slot and on_player_removed: that player's remote slots are scanned
---again on the next swap.
---@param player_index integer
function M.quickbar_changed(player_index)
  local r = storage.jamaltron and storage.jamaltron.swap
  if r and r.remotes then r.remotes[player_index] = nil end
end

---A player's VIEW of him (remote selection, an open GUI, the remote-view camera), which only a
---connected player has.
---@param player LuaPlayer
---@param old LuaEntity
---@param new LuaEntity
local function carry_view(player, old, new)
  local selection = repoint(player.spidertron_remote_selection, old, new)
  if selection then player.spidertron_remote_selection = selection end
  if player.opened == old then player.opened = new end
  if player.centered_on == old then player.centered_on = new end
end

---The player-side half is UNMEASURED (headless has no LuaPlayer), so each player is wrapped and
---a failure logged instead of failing the swap, until the D.4.8 play.sh pass has watched every
---branch work.
---@param fn fun(player: LuaPlayer, old: LuaEntity, new: LuaEntity)
---@param player LuaPlayer
---@param old LuaEntity
---@param new LuaEntity
local function guarded(fn, player, old, new)
  local ok, err = pcall(fn, player, old, new)
  if not ok then
    log("jamaltron swap: player-side carry failed for " .. player.name .. ": " .. tostring(err))
  end
end

---Move one of A's people into B's seat. set_driver moves a character straight out of A only
---when there is ground to step out onto: over `water` or `deepwater` it is refused SILENTLY, the
---character stays in A, and A's destroy drops it in the lake (measured; he straddles lakes, and
---rests with his body over one at every shore stall). Emptying A's seat first drops the
---character where it sits, no ground needed, and seating it from there works, B 8 tiles away
---included (measured, all three tiles). On ground the direct move takes; the fallback never runs.
---@param old LuaEntity
---@param new LuaEntity
---@param who LuaEntity|LuaPlayer
---@param driver boolean the driver's seat, else the passenger's
local function seat(old, new, who, driver)
  if driver then new.set_driver(who) else new.set_passenger(who) end
  if not new.valid then return end
  local got
  if driver then got = new.get_driver() else got = new.get_passenger() end
  if got == who then return end
  if driver then old.set_driver(nil) else old.set_passenger(nil) end
  if new.valid then
    if driver then new.set_driver(who) else new.set_passenger(who) end
  end
end

---Modded burner equipment's fuel and burnt results, slot by slot, then what is burning.
---Idempotent: only a filled source slot over an empty target moves.
---@param src LuaEquipment
---@param dst LuaEquipment
local function carry_burner(src, dst)
  local a, b = src.burner, dst.burner
  if not (a and b) then return end
  for _, pair in ipairs({{a.inventory, b.inventory}, {a.burnt_result_inventory, b.burnt_result_inventory}}) do
    local from, to = pair[1], pair[2]
    for i = 1, math.min(#from, #to) do
      if from[i].valid_for_read and not to[i].valid_for_read then to[i].swap_stack(from[i]) end
    end
  end
  b.currently_burning = a.currently_burning
  b.remaining_burning_fuel = a.remaining_burning_fuel
  b.heat = a.heat
end

---B's disabled_by_script, custom_status and operable: opts, else M.BODY's for a body change,
---else A's.
---@param ctx Jamaltron.SwapCtx
---@return boolean disabled
---@return CustomEntityStatus? custom_status
---@return boolean operable
local function body_state(ctx)
  local s, opts = ctx.s --[[@as table]], ctx.opts
  local body = ctx.old_name ~= ctx.name and M.BODY[ctx.name] or nil
  local disabled, status = opts.disabled, opts.custom_status
  if disabled == nil then
    if body then
      disabled = body.still and not immobile(ctx.name)
    else
      disabled = s.disabled
    end
  end
  if status == nil then
    if body then status = body.custom_status else status = s.custom_status or false end
  end
  local operable = s.operable
  if body then operable = body.operable end
  return disabled, status or nil, operable
end

---Leave the t+1 half on the clock: the storage point's flags, the stash's first chance at a
---toolbelt's slots, and disabled_by_script.
---@param ctx Jamaltron.SwapCtx
local function schedule(ctx)
  local r, new = root(), ctx.new --[[@as LuaEntity]]
  local new_unit = new.unit_number --[[@as integer]]
  local disabled = body_state(ctx)
  r.due[new_unit] = {entity = new, tick = game.tick + 1, points = ctx.s.points, disabled = disabled}
  clock.wake()
end

---The trunk half: an older stash re-keyed to B BEFORE this swap's own overflow joins it (the
---other order orphaned it), every inventory slot by slot, burner fuel, then the equipment B's
---grid had no room for (AFTER the slots, or the slot-by-slot move carried it into A and destroyed
---it with A, measured), then the speech record. Safe to run twice: the error path re-runs it to
---finish a swap forward.
---@param ctx Jamaltron.SwapCtx
local function move_all(ctx)
  local r, old, new = root(), ctx.old, ctx.new --[[@as LuaEntity]]
  local new_unit = new.unit_number --[[@as integer]]
  if not ctx.rekeyed then
    ctx.rekeyed = true
    local stashed = r.stash[ctx.old_unit]
    if stashed then
      r.stash[ctx.old_unit], r.stash[new_unit] = nil, stashed
      stashed.entity = new
    end
  end
  if old.valid then
    for _, index in ipairs(INVENTORIES) do
      local src = old.get_inventory(index)
      if src then
        move(src, new.get_inventory(index), function(size)
          return stash_part(r, new_unit, new, index, size)
        end)
      end
    end
    for _, pair in ipairs(ctx.burners) do
      if pair.src.valid and pair.dst.valid then carry_burner(pair.src, pair.dst) end
    end
  end
  if not ctx.fell then
    ctx.fell = true
    for _, stack in ipairs(ctx.fallback) do
      if new.insert(stack) == 0 then
        new.surface.spill_item_stack{position = new.position, stack = stack, enable_looted = true,
                                     allow_belts = false}
      end
    end
  end
  settle(r, new_unit)
  if not ctx.transferred then
    ctx.transferred = true
    -- D.5's hand-off: his record (breaks, fired-set, fork, shore gap) follows him; a pending
    -- chain does not. The note is re-pinned and the bubble said again on B.
    speech.transfer(ctx.old_unit, new)
  end
end

---Back to ONE Jamal after B died or an error cut the swap short. Before the trunk moved, A is
---still him: B goes, the people come home, A gets its name_tag back ("failed"). After it, B is
---him: on the error path B is finished and A goes quietly (a listener that just threw is not
---called again); when B is dead, A goes too instead of standing there empty ("lost").
---@param ctx Jamaltron.SwapCtx
---@return LuaEntity?
local function unwind(ctx)
  local old, new, s = ctx.old, ctx.new, ctx.s
  if ctx.phase == nil or ctx.phase == "made" or ctx.phase == "seated" then
    if new and new.valid then
      new.destroy{raise_destroy = false}             -- ejects whoever it held, beside A
    end
    if not old.valid then                            -- a listener destroyed A itself
      ctx.status = "lost"
      return nil
    end
    if s then
      if s.driver and s.driver.valid and old.get_driver() == nil then old.set_driver(s.driver) end
      if s.passenger and s.passenger.valid and old.get_passenger() == nil then
        old.set_passenger(s.passenger)
      end
      if s.name_tag and old.name_tag == nil then old.name_tag = s.name_tag end
    end
    ctx.status = "failed"
    return nil
  end
  if new and new.valid then
    if ctx.phase ~= "done" then
      move_all(ctx)
      if old.valid then old.destroy{raise_destroy = false} end
      schedule(ctx)
      ctx.phase = "done"
    end
    ctx.status = "ok"
    return new
  end
  if old.valid then old.destroy{raise_destroy = not M.SILENT[ctx.old_name]} end
  ctx.status = "lost"
  return nil
end

---@param ctx Jamaltron.SwapCtx
---@return LuaEntity?
local function replace(ctx)
  local r, old, name, opts = root(), ctx.old, ctx.name, ctx.opts
  local surface = old.surface
  local s = read(old)
  ctx.s = s
  -- A second swap inside one tick reads the first one's t+1 intent, not the body: the storage
  -- point does not exist yet and disabled has not been written. READ, never taken (the entry
  -- stays with A and the tick drops it once A is gone), so a failed follow-up leaves the first
  -- swap's t+1 standing (measured: taking it dropped a beached body's disable), and pending()
  -- never falls outside tick() (clock.lua's rule).
  local prior = r.due[ctx.old_unit]
  if prior then
    s.disabled = prior.disabled
    for member, point in pairs(prior.points) do
      if s.points[member] == nil then s.points[member] = point end
    end
  end

  local new = surface.create_entity{
    name = name, position = opts.position or old.position, force = old.force,
    quality = old.quality, snap_to_grid = false, create_build_effect_smoke = false,
    raise_built = false, color = old.color, label = old.entity_label,
    driver_is_main_gunner = old.driver_is_gunner, selected_gun_index = old.selected_gun_index,
    automatic_targeting_parameters = old.vehicle_automatic_targeting_parameters,
    enable_logistics_while_moving = old.enable_logistics_while_moving}
  if new == nil then
    ctx.status = "failed"                          -- A untouched: create-first's whole point
    return nil
  end
  ctx.new, ctx.phase = new, "made"
  local new_unit = new.unit_number --[[@as integer]]
  ctx.held[#ctx.held + 1] = new_unit
  swapping[new_unit] = true
  -- Before anything can go wrong: whatever kills B from here, forget() spills a stash re-keyed
  -- to it instead of leaking the script inventory.
  script.register_on_object_destroyed(new)

  -- A deconstruction mark first: order_deconstruction is refused once minable_flag is false.
  -- D.1's bodies are not-deconstructable, so a mark does not ride a jump or a break.
  if s.decon then
    new.order_deconstruction(s.decon)
    if not new.valid then return unwind(ctx) end   -- on_marked_for_deconstruction's listeners
  end
  new.torso_orientation = s.torso
  if s.ratio then new.health = s.ratio * new.max_health end
  if s.name_tag then new.name_tag = s.name_tag end -- unique map-wide: this takes it off A
  if s.last_user then new.last_user = s.last_user end
  new.destructible = s.destructible
  new.minable_flag = s.minable_flag                -- `minable` is read-only and lies when occupied
  new.rotatable = s.rotatable
  new.protected = s.protected
  local _, status, operable = body_state(ctx)
  new.custom_status = status
  new.operable = operable
  for _, field in pairs(s.tooltip) do new.set_tooltip_field(field) end
  new.allow_dispatching_robots = s.dispatching
  new.request_from_buffers = s.from_buffers    -- a script-built spider defaults it to false

  -- Logistic sections: B starts with one empty section of its own, which goes.
  local sections = new.get_logistic_sections()
  if sections then
    for i = sections.sections_count, 1, -1 do sections.remove_section(i) end
    for _, section in ipairs(s.sections) do
      local added = sections.add_section(section.group ~= "" and section.group or nil)
      if added then
        if section.filters then added.filters = section.filters end
        added.multiplier = section.multiplier
        added.active = section.active
      end
    end
  end

  -- The grid BEFORE the inventories: a toolbelt's slots follow the grid, a tick late. COPIED, so
  -- A's is whole until A goes; burner fuel moves with the trunk, below.
  local grid = new.grid
  ctx.fallback, ctx.burners = {}, {}
  for _, eq in ipairs(s.equipment) do
    local put = grid and grid.put{name = eq.name, quality = eq.quality, position = eq.position,
                                  ghost = eq.ghost}
    if not new.valid then return unwind(ctx) end   -- on_equipment_inserted's listeners
    if grid and put then
      if eq.energy then put.energy = eq.energy end
      if eq.shield then put.shield = eq.shield end
      if eq.removal then grid.order_removal(put) end
      if eq.src then ctx.burners[#ctx.burners + 1] = {src = eq.src, dst = put} end
    elseif not eq.ghost then
      -- No room on B's grid: a prototype drifted from D.4.6's assert. The item survives, its
      -- charge does not.
      local item = prototypes.equipment[eq.name].take_result
      if item then
        ctx.fallback[#ctx.fallback + 1] = {name = item.name, quality = eq.quality, count = 1}
      end
    end
  end
  if grid and s.inhibit ~= nil then grid.inhibit_movement_bonus = s.inhibit end
  for member, point in pairs(s.points) do
    local target = new.get_logistic_point(member) --[[@as LuaLogisticPoint?]]
    if target then
      target.enabled, target.trash_not_requested = point.enabled, point.trash_not_requested
    end
  end

  -- Both bodies valid, B not yet filled: Enhancements' own order. A listener that kills B here
  -- leaves A whole ("failed"); raised after the move, the same listener destroyed the trunk and
  -- left an empty Jamal standing (measured).
  script.raise_event("on_spidertron_replaced",
                     {old_spidertron = old, new_spidertron = new, jamaltron_reason = opts.reason})
  if not (new.valid and old.valid) then return unwind(ctx) end

  -- The people, while A still holds them: set_driver moves a seated character across in one
  -- call. Before the trunk, so a listener killing B on the driving event costs nothing.
  ctx.phase = "seated"
  if s.driver and s.driver.valid then seat(old, new, s.driver, true) end
  if not new.valid then return unwind(ctx) end
  if s.passenger and s.passenger.valid then seat(old, new, s.passenger, false) end
  if not new.valid then return unwind(ctx) end
  -- set_driver just RESET his held direction (measured). It goes back onto the driver in the
  -- vehicle, which restarts him, and in a transit body, which cannot walk on it (D.1) and only
  -- holds it for the landing, where read() takes it off the driver again: a key let go mid-arc
  -- lands him standing, a held one walking (both MEASURED on a scripted driver, whose state
  -- latches; a real player's release is an input that overwrites the write - INFERRED, D.4.8's
  -- play.sh). Beached is neither: a break stops him.
  local driver, walking, target = s.driver, s.walking, M.BODY[name]
  if walking and walking.walking and driver and driver.valid
      and (name == C.name or (target and target.transit)) then
    local control = driver.object_name == "LuaEntity" and driver.player or driver
    control.walking_state = walking
  end

  ctx.phase = "moved"
  move_all(ctx)

  -- The grid ghosts above already made B a proxy. Give it A's whole plan, never a second proxy,
  -- and never destroy one: that cancels the grid's ghosts and removal marks.
  if s.plans then
    local proxy = new.item_request_proxy
    if proxy then
      proxy.insert_plan = s.plans.insert
      proxy.removal_plan = s.plans.removal
    else
      surface.create_entity{name = "item-request-proxy", position = new.position, target = new,
                            force = new.force, modules = s.plans.insert,
                            removal_plan = s.plans.removal}
    end
  end

  -- Follow XOR queue (each clears the other); the patrol size only after the waypoints and only
  -- when > 0 (writing 0 clears a follow; more than the queue holds is an error).
  if opts.autopilot ~= false then
    if s.follow and s.follow.valid then
      new.follow_target = s.follow
      if s.follow_offset then new.follow_offset = s.follow_offset end -- re-randomized by the target
    else
      for _, destination in pairs(s.destinations) do new.add_autopilot_destination(destination) end
      if s.patrol > 0 and s.patrol <= #s.destinations then new.autopilot_patrol_size = s.patrol end
    end
  end
  for _, follower in ipairs(s.followers) do
    if follower.entity.valid then
      follower.entity.follow_target = new
      if follower.offset then follower.entity.follow_offset = follower.offset end
    end
  end
  if old.valid then carry_proxies(surface, old, new) end

  local remote_driver = s.remote
  if remote_driver and remote_driver.valid then
    guarded(function(player) player.centered_on = new end, remote_driver, old, new)
  end
  for _, player in pairs(game.players) do
    if player.force == new.force then guarded(carry_saved, player, old, new) end
  end
  for _, player in pairs(game.connected_players) do
    guarded(carry_view, player, old, new)
  end
  if not new.valid then return unwind(ctx) end     -- on_gui_opened's listeners

  if old.valid then
    old.destroy{raise_destroy = not M.SILENT[ctx.old_name]}
  end
  if not new.valid then return unwind(ctx) end
  if not M.SILENT[name] then
    script.raise_script_built{entity = new}
    if not new.valid then return unwind(ctx) end
  end

  -- Stickers die with A a tick later. Re-made with their own force and remaining time; the
  -- cause is unreadable, so damage attribution resets.
  for _, sticker in ipairs(s.stickers) do
    local made = surface.create_entity{name = sticker.name, position = new.position, target = new,
                                       force = sticker.force}
    if made and sticker.ttl then made.time_to_live = sticker.ttl end
  end

  schedule(ctx)
  ctx.phase, ctx.status = "done", "ok"
  return new
end

---Put Jamal in body `name`. Returns the new entity and "ok", or nil and why not (the header's
---status table): "refused" and "failed" leave him whole in `old`, "lost" means he is gone. A
---swap already in progress on `old` is refused, so a listener reacting to one of our events
---cannot recurse into it.
---@param old LuaEntity
---@param name string
---@param opts Jamaltron.SwapOpts?
---@return LuaEntity?
---@return "ok"|"refused"|"failed"|"lost"
function M.replace(old, name, opts)
  if not (old and old.valid and old.unit_number) or swapping[old.unit_number] then
    return nil, "refused"
  end
  local unit = old.unit_number --[[@as integer]]
  ---@type Jamaltron.SwapCtx
  local ctx = {old = old, old_unit = unit, old_name = old.name, name = name, opts = opts or {},
               held = {unit}, fallback = {}, burners = {}}
  swapping[unit] = true
  local ok, result = xpcall(replace, debug.traceback, ctx)
  if not ok then
    -- Under the guard still: putting the people back raises driving events of its own.
    local fine, err = pcall(unwind, ctx)
    if not fine then
      log("jamaltron swap: unwinding after an error failed too: " .. tostring(err))
    end
  end
  -- Cleared on the error path too. A unit left in `swapping` would silence his lines on this
  -- peer and not on one that joins later: a desync, not a cosmetic bug.
  for _, held in ipairs(ctx.held) do swapping[held] = nil end
  if not ok then
    error(result, 0)
  end
  return result, ctx.status --[[@as "ok"|"refused"|"failed"|"lost"]]
end

---The t+1 half, on the clock: the storage point's flags, the stash's first chance at a
---toolbelt's slots, then disabled_by_script (last, since a disabled body's trunk never grows).
---Entries for a body already gone (a follow-up swap, a death) are dropped here and only here.
---@param tick integer
function M.tick(tick)
  local r = root()
  for unit, due in pairs(r.due) do
    if due.tick <= tick then
      r.due[unit] = nil
      local entity = due.entity
      if entity.valid then
        for member, point in pairs(due.points) do
          local target = entity.get_logistic_point(member) --[[@as LuaLogisticPoint?]]
          if target then
            target.enabled, target.trash_not_requested = point.enabled, point.trash_not_requested
          end
        end
        settle(r, unit)
        entity.disabled_by_script = due.disabled
      end
    end
  end
end

---The slow clock: a stash that outlived t+1 (a deconstruction mark also holds the toolbelt slots
---back) gets another try and keeps a current position to spill at. Empty is free.
function M.poll()
  local r = storage.jamaltron and storage.jamaltron.swap
  if r == nil then return end
  for unit in pairs(r.stash) do
    settle(r, unit)
  end
end

---on_object_destroyed: a body that died holding a stash spills it where it was last seen (a
---miner gets the trunk, the ground the stash; over a lake the engine carries it to the nearest
---dry ground - measured 35 tiles out, none lost). Due work is NOT touched (the tick drops it), or
---the on_tick registration drifts from what on_load re-derives (clock.lua).
---@param unit integer
function M.forget(unit)
  local r = storage.jamaltron and storage.jamaltron.swap
  if r == nil then return end
  local st = r.stash[unit]
  if st == nil then return end
  r.stash[unit] = nil
  for _, part in pairs(st.parts) do
    if st.surface.valid then
      for i = 1, #part.inv do
        if part.inv[i].valid_for_read then
          st.surface.spill_item_stack{position = st.position, stack = part.inv[i],
                                      enable_looted = true, allow_belts = false}
        end
      end
    end
    part.inv.destroy()
  end
end

---HARNESS ONLY: counts to assert on, for one body if given, else the whole map. `due` counts
---every entry, `due_live` those whose body still exists.
---@param entity LuaEntity?
---@return {due: integer, due_live: integer, stash: integer, stashed_items: integer, pending: boolean}
function M.state(entity)
  local r = storage.jamaltron and storage.jamaltron.swap
  local out = {due = 0, due_live = 0, stash = 0, stashed_items = 0, pending = M.pending()}
  if r == nil then return out end
  local only = entity and entity.valid and entity.unit_number or nil
  for unit, due in pairs(r.due) do
    if only == nil or unit == only then
      out.due = out.due + 1
      if due.entity.valid then out.due_live = out.due_live + 1 end
    end
  end
  for unit, st in pairs(r.stash) do
    if only == nil or unit == only then
      out.stash = out.stash + 1
      for _, part in pairs(st.parts) do
        out.stashed_items = out.stashed_items + part.inv.get_item_count()
      end
    end
  end
  return out
end

return M
