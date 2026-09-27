-- The legs give out, and get put back (PLAN E.4, E.5). SPEC: "on jumping there should be a
-- reasonable chance the legs break, the vehicle takes damage and Jamal is left flopping around
-- until it's repaired". This owns the landing's outcome, the beached state and the repair; the
-- arc is scripts/jump.lua's, the body change scripts/swap.lua's, the words speech.lua's.
--
-- THE LANDING, in the order R1 needs (lines.md: the break roll resolves before any landing line
-- is picked): roll, ONE swap out of the airborne body (to jamaltron, or jamaltron-beached on a
-- break - never airborne -> jamaltron -> beached), the thud written onto the body the swap
-- RETURNED, then that body's line: `land`/held clean, `legs_break`/self broken. R4: `land` never
-- speaks on a break; legs_break stamps the fork every flop reads (R2).
--
-- BEACHED: the red "Legs broken" status is swap.lua's body table. Here: a force alert on him
-- (show_on_map is his map presence; a chart tag would outlive the mod, and E.6 says removal
-- leaves no orphans), the apology timer and the repair. All on control.lua's 60-tick slow clock
-- over a storage SET of beached units, never a surface scan, nothing per tick: seconds are enough
-- for an apology and for noticing a full health bar. A body joins the set on a broken landing, a
-- repair event, adopt_all, or keep() (the way in for a beached body this file did not make). All
-- go through adopt(), which draws his broken legs (scripts/wreck.lua, D.1.3) once per body, kept
-- on the record.
--
-- ONE RECORD PER BEACHED JAMAL, in `storage`, keyed by unit_number, so multiplayer and a save
-- round-trip hold (E.6). No module-level state but constants.
--
-- JUMPING OFF (the startup setting) means no broken legs, as its tooltip promises: a landing
-- never rolls, and poll() stands up every kept body as if repaired. A save that flips it off
-- mid-break gets everyone up within a second of loading (adopt_all keeps them, the poll stands
-- them); nothing swaps inside on_configuration_changed.

local C = require("prototypes.shared")
local speech = require("scripts.speech")
local swap = require("scripts.swap")
local wreck = require("scripts.wreck")

local M = {}

---Every landing thuds for this fraction of max health, rolled uniformly, at a jump of
---THUD_DISTANCE tiles and linear in the jump's distance (the setting runs 3-20, so 0.4-7.5%).
---A small tax on hopping for its own sake; the real damage is the break.
M.THUD = {0.01, 0.03}
M.THUD_DISTANCE = 8

---A break leaves him at most this fraction of max health (after the thud), so a repair always
---has half his bar to do: 1500 HP on a normal-quality body, 2.5 repair packs (600 HP each).
M.BROKEN_AT_MOST = 0.5

---No landing takes him below this fraction, and none heals him if he is already under it.
---Death is combat's job: a landing that killed him would skip the flop (the joke), and a written
---health of 0 is not death anyway - the engine makes a 0-health entity unattackable.
M.FLOOR = 0.05

---jamaltron-apology-interval (15 s default) times this, per verbosity, shaped like speech.lua's
---IDLE_SECONDS. At defaults: 30 / 15 / 7.5 s. `flopping` is AMBIENT, so the speech cooldown (10 s
---default) is the real floor under unbearable: the timer waits it out instead of losing a turn
---(see flop()), making unbearable 10 s at defaults, not normal's 15.
M.APOLOGY_SCALE = {quiet = 2, normal = 1, unbearable = 0.5}

---+-20% on every interval: two beached Jamals drift out of unison, and the lines drift across
---the flop loop (C.5: 2.5 s, which 15 s is an exact multiple of).
M.APOLOGY_JITTER = 0.2

---Ticks between re-issues of his alert. add_custom_alert reaches only players connected when it
---runs, so this is also how soon a player joining mid-break is told. Removed before every re-add
---so a refresh never stacks a second copy. How the engine ages or dedups a custom alert is
---UNMEASURED: headless has no players to hold one (a play.sh item).
M.ALERT_TICKS = 10 * 60

---A freshly beached body is not still yet: beside water or lava its legs re-lay from the spawn
---pose and slide it 1.2-1.5 tiles over ~2 s (measured; 0.000 on open ground). So the first
---re-issue comes this soon after the break, putting the alert AND the place forget() takes it
---down by where he settled, whether the engine pins an alert to where it was added or to where
---its entity is now (unmeasured, no players headless).
M.SETTLE_TICKS = 3 * 60

---The alert's picture: his item icon.
---@type SignalID
M.ICON = {type = "item", name = C.name}
---Reuses the GUI status string (locale [jamaltron-status]): one wording for one state.
M.MESSAGE = {"jamaltron-status.beached"}

---@class Jamaltron.Beached
---@field entity LuaEntity
---@field flop_at integer tick the next `flopping` line is due
---@field due_since integer? tick the flop he is waiting on first came due: his place in the queue
---@field alert_at integer tick the alert is next re-issued
---@field force LuaForce? whose players hold the alert, for taking it down
---@field surface LuaSurface where he lies: an alert on a destroyed body is removed by place
---@field position MapPosition as of his last alert: he cannot walk (D.1), but settles for ~2 s
---@field wreck Jamaltron.Wreck? his broken legs' render objects (scripts/wreck.lua)

---@return table<integer, Jamaltron.Beached>
local function beached()
  storage.jamaltron = storage.jamaltron or {}
  local r = storage.jamaltron
  r.breakage = r.breakage or {beached = {}}
  return r.breakage.beached
end

---@param key string
---@return number
local function setting(key)
  return tonumber(settings.global[key].value) or 0
end

---jamaltron-jump-enabled. Read here rather than asked of jump.lua, which requires this file.
---@return boolean
local function jumping()
  return settings.startup["jamaltron-jump-enabled"].value == true
end

---Ticks to the next apology, per verbosity, with jitter.
---@return integer
local function apology_ticks()
  local scale = M.APOLOGY_SCALE[tostring(settings.global["jamaltron-verbosity"].value)] or 1
  local jitter = 1 - M.APOLOGY_JITTER + 2 * M.APOLOGY_JITTER * math.random()
  return math.max(60, math.floor(setting("jamaltron-apology-interval") * 60 * scale * jitter))
end

---Does this landing break his legs? jamaltron-leg-break-percent, rolled on math.random: in game
---that is the MAP's generator (deterministic, identical on every peer, saved with the map -
---auxiliary/libraries.html), the one speech.lua already rolls lines on. A LuaRandomGenerator
---would be one more object in storage for nothing. 0 and 100 draw nothing.
---@return boolean
local function roll_break()
  local percent = setting("jamaltron-leg-break-percent")
  return percent >= 100 or (percent > 0 and math.random(1, 100) <= percent)
end

---The health ratio he lands at: the thud off `ratio`, capped at BROKEN_AT_MOST on a break, and
---never under FLOOR unless he already was (then where he was: a landing never heals).
---@param ratio number
---@param thud number
---@param broke boolean
---@return number
local function landing_ratio(ratio, thud, broke)
  local target = ratio - thud
  if broke and target > M.BROKEN_AT_MOST then target = M.BROKEN_AT_MOST end
  return math.max(target, math.min(ratio, M.FLOOR))
end

---Take his alert down: by entity while the body exists, by place once it is gone (forget()
---runs from on_object_destroyed, after the body is invalid).
---@param rec Jamaltron.Beached
local function unalert(rec)
  local force = rec.force
  if not (force and force.valid) then return end
  local custom = defines.alert_type.custom
  if rec.entity.valid then
    force.remove_alert{entity = rec.entity, type = custom, icon = M.ICON}
  elseif rec.surface.valid then
    force.remove_alert{surface = rec.surface, position = rec.position, type = custom, icon = M.ICON}
  end
end

---Put his alert up (again) for every connected player of his force.
---@param rec Jamaltron.Beached
---@param tick integer
local function alert(rec, tick)
  unalert(rec)
  local entity = rec.entity
  rec.force, rec.surface, rec.position = entity.force --[[@as LuaForce]], entity.surface, entity.position
  rec.force.add_custom_alert(entity, M.ICON, M.MESSAGE, true)
  rec.alert_at = tick + M.ALERT_TICKS
end

---@param entity LuaEntity
---@param tick integer
---@return Jamaltron.Beached
local function new_record(entity, tick)
  return {entity = entity, flop_at = tick + apology_ticks(), alert_at = tick,
          force = entity.force --[[@as LuaForce]], surface = entity.surface,
          position = entity.position}
end

---Start keeping a beached body: the apology clock from now, the alert now and again once he has
---settled, his broken legs round him unless already there. Keeps an existing record.
---@param entity LuaEntity
---@param tick integer
---@return Jamaltron.Beached?
local function adopt(entity, tick)
  local unit = entity.unit_number
  if unit == nil then return nil end
  local set = beached()
  local rec = set[unit]
  local fresh = rec == nil
  if fresh then
    rec = new_record(entity, tick)
    set[unit] = rec
    -- swap and speech register him already; this module does not lean on that
    script.register_on_object_destroyed(entity)
  end
  alert(rec, tick)
  if fresh then rec.alert_at = tick + M.SETTLE_TICKS end
  wreck.ensure(rec, entity)
  return rec
end

---@param unit integer
---@param rec Jamaltron.Beached
local function drop(unit, rec)
  local set = beached()
  set[unit] = nil
  unalert(rec)
  if rec.entity.valid then return end
  -- By place takes down every alert on that spot, and two landings on one spot beach two
  -- Jamals there: re-issue the other's on the next poll.
  local p = rec.position
  for _, other in pairs(set) do
    if other.surface == rec.surface and other.position.x == p.x and other.position.y == p.y then
      other.alert_at = 0
    end
  end
end

---One apology, if due. The gates stay say()'s; this only avoids WASTING a turn on the two that
---are about time, not taste: a flop due inside the ambient cooldown, or while the map is at its
---bubble cap (F.3), waits for speech.ambient_free_at instead of a whole interval, keeping
---`due_since` (poll() serves the oldest first). R5 needs no wait of its own today: every chain
---lands within 180 ticks of its head, and the head started a cooldown of at least 180 (the
---setting's minimum). Anything else that says nothing (legs_break.18's skipped flop, a hush)
---costs the full interval - that is what it is FOR.
---@param rec Jamaltron.Beached
---@param tick integer
local function flop(rec, tick)
  local free = speech.ambient_free_at(rec.entity, tick)
  if tick < free then
    rec.flop_at = free
    return
  end
  rec.due_since = nil
  speech.say(rec.entity, "flopping")                -- the fork is on his record (R2)
  rec.flop_at = tick + apology_ticks()
end

---Oldest wait first, then the lower unit: every peer sorts the same.
---@param a Jamaltron.Beached
---@param b Jamaltron.Beached
---@return boolean
local function queued_before(a, b)
  if a.due_since ~= b.due_since then return a.due_since < b.due_since end
  return a.entity.unit_number < b.entity.unit_number
end

---Back on his feet: alert down, ONE swap to the vehicle, then `repaired` on the body the swap
---returned (it clears the fork). A failed swap leaves him beached at full health, the alert back
---up and the poll retrying every second; a lost one leaves the record to the next poll or
---forget(), like any body that is gone.
---@param unit integer
---@param rec Jamaltron.Beached
---@param tick integer
---@return LuaEntity?
local function stand(unit, rec, tick)
  local body = rec.entity
  unalert(rec)
  local walking = swap.replace(body, C.name, {reason = "repair"})
  if walking then
    beached()[unit] = nil
    speech.say(walking, "repaired")
  elseif body.valid then
    alert(rec, tick)
  end
  return walking
end

---jump.lua, when the arc comes down at `spot`: roll the break, land him in ONE swap, thud, and
---say the landing line on the body that now exists. Returns that body and "held" | "broke", or
---nil and swap.replace's status: "failed" leaves him in the airborne body (both landings were
---refused; the caller must not leave him there), "lost" and "refused" as swap.lua says. A break
---whose swap fails lands him clean instead: a shark stranded in a 30-tick body is worse than a
---lucky jump. Nothing is rolled (he lands clean) with jumping switched off (an arc or stranded
---body that outlived the setting), nor from no height (info.height == 0): a body jump.adopt
---stranded never flew (a playtest swap, an orphan from an older save), and a roll there broke
---his legs and bumped his {N} for a jump nobody made (measured at 100%).
---@param airborne LuaEntity
---@param spot MapPosition?
---@param info {tick: integer?, height: number?, distance: number?, driver: (LuaEntity|LuaPlayer)?}?
---@return LuaEntity?
---@return "held"|"broke"|"refused"|"failed"|"lost"
function M.on_landing(airborne, spot, info)
  if not (airborne and airborne.valid) then return nil, "refused" end
  local ratio = airborne.get_health_ratio() or 1
  local broke = jumping() and not (info and info.height == 0) and roll_break()
  local distance = info and info.distance or M.THUD_DISTANCE
  local thud = (M.THUD[1] + (M.THUD[2] - M.THUD[1]) * math.random()) * distance / M.THUD_DISTANCE
  local landed, status
  if broke then
    landed, status = swap.replace(airborne, C.beached, {reason = "break", position = spot})
    if landed == nil and status == "failed" then broke = false end
  end
  if not broke then
    landed, status = swap.replace(airborne, C.name, {reason = "landing", position = spot})
  end
  if landed == nil then return nil, status --[[@as "refused"|"failed"|"lost"]] end

  -- WRITTEN, not dealt: entity.damage() raises on_entity_damaged, which control.lua answers with
  -- a damaged / low_health line this same tick, on top of the landing line (the mod's
  -- centerpiece). It also runs resistances (the number would depend on armor and quality) and
  -- can kill. A written health raises nothing (on_entity_damaged's own docs).
  landed.health = landing_ratio(ratio, thud, broke) * landed.max_health

  if broke then
    adopt(landed, game.tick)
    speech.say(landed, "legs_break", "self")      -- the player pressed jump: his doing
    return landed, "broke"
  end
  speech.say(landed, "land", "held")
  return landed, "held"
end

---on_player_repaired_entity (filter the beached name): a repair pack took a beached Jamal to
---FULL health, so he gets up now, not on the next poll. A beached body with no record (a
---playtest swap) is adopted and gets up too: full health is repaired, whoever broke him.
---@param event EventData.on_player_repaired_entity
function M.on_repaired(event)
  local entity = event.entity
  if not (entity and entity.valid and entity.name == C.beached and entity.unit_number)
      or entity.health < entity.max_health then
    return
  end
  local unit = entity.unit_number --[[@as integer]]
  local rec = beached()[unit] or adopt(entity, event.tick)
  if rec then stand(unit, rec, event.tick) end
end

---Keep a beached body we did not make: its fork defaulted, capped first when `cap` and not kept.
---@param entity LuaEntity
---@param cap boolean
---@return boolean kept
local function take(entity, cap)
  if not (entity and entity.valid and entity.name == C.beached and entity.unit_number) then
    return false
  end
  if cap and beached()[entity.unit_number] == nil then
    local most = M.BROKEN_AT_MOST * entity.max_health
    if entity.health > most then entity.health = most end
  end
  local srec = speech.record(entity, true)
  if srec and srec.fork == nil then speech.set_fork(entity, "self") end
  return adopt(entity, game.tick) ~= nil
end

---A beached body that got there other than by a landing (the playtest's /jamaltron-swap, another
---mod) is kept from now: alert, apologies, up at full health. Without this it lies in limbo
---(measured: no alert, no flop in 1890 ticks, a full bar never stood it up). A body not yet kept
---is capped at BROKEN_AT_MOST first (never healed): swapped in at full health, the next poll
---would stand him straight back up. His fork defaults to `self` if nothing stamped one, lines.md's
---rule for a break of unknown fault. Idempotent.
---@param entity LuaEntity
---@return boolean kept
function M.keep(entity)
  return take(entity, true)
end

---on_entity_cloned (filter the beached name): a clone (entity.clone, surface.clone_area, a mod
---that moves things by cloning) copies the body but neither its render objects nor our record
---(measured: no legs, no alert, never stood up). Kept from now like any beached body we did not
---make, at its cloned health (a half-repaired Jamal's clone is not re-broken); the source keeps
---its own record until destroyed.
---@param event EventData.on_entity_cloned
function M.on_cloned(event)
  take(event.destination, false)
end

---The 60-tick slow clock: every beached Jamal gets up at full health (construction bots, which
---raise no repair event, or anything else that healed him), or at any health once jumping is
---switched off (the header); else flops and keeps his alert current. A record whose body is gone
---is dropped. A record on a body that is NOT beached (another mod parked him in a dummy of its
---own - transfer) just waits.
---
---Due flops go FIRST COME FIRST SERVED, not in pairs() order: at the bubble cap a freed slot goes
---to whoever asks first, and pairs() asks the same Jamals first every poll - measured 31 of 100
---beached never apologizing in 6 minutes at cap 20, against min 11 lines each served
---oldest-first. Sorting is k log k in the flops due this poll, 0-2 off the cap.
---@param tick integer
function M.poll(tick)
  local set = beached()
  if next(set) == nil then return end
  local healed_all = not jumping()
  local up, due = nil, nil
  for unit, rec in pairs(set) do
    local entity = rec.entity
    if not entity.valid then
      drop(unit, rec)                                -- clearing a key mid-pairs is allowed
    elseif entity.name == C.beached then
      if healed_all or entity.health >= entity.max_health then
        up = up or {}
        up[#up + 1] = unit
      else
        if tick >= rec.alert_at then alert(rec, tick) end
        if tick >= rec.flop_at then
          rec.due_since = rec.due_since or rec.flop_at
          due = due or {}
          due[#due + 1] = rec
        end
      end
    end
  end
  if due then
    if #due > 1 then table.sort(due, queued_before) end
    for _, rec in ipairs(due) do flop(rec, tick) end
  end
  -- After the walk: a swap raises events, and a listener that beached another Jamal from one
  -- would add a key to `set` mid-pairs, which Lua leaves undefined.
  for _, unit in ipairs(up or {}) do
    local rec = set[unit]
    if rec and rec.entity.valid then stand(unit, rec, tick) end
  end
end

---on_object_destroyed, beside speech.forget and swap.forget: a beached Jamal that died, was
---mined or was destroyed by another mod takes his record and his alert with him.
---@param unit integer
function M.forget(unit)
  local set = storage.jamaltron and storage.jamaltron.breakage and storage.jamaltron.breakage.beached
  local rec = set and set[unit]
  if rec then drop(unit, rec) end
end

---control.lua's on_spidertron_replaced, beside speech.transfer: ANOTHER mod moved him to a body
---of its own. The record follows him; its alert and his broken legs move only onto a beached body
---(drawn afresh, a new layout), and poll() leaves him alone in any other until he comes back.
---@param old_unit integer
---@param new_entity LuaEntity
function M.transfer(old_unit, new_entity)
  local set = beached()
  local rec = set[old_unit]
  if rec == nil or not (new_entity.valid and new_entity.unit_number) then return end
  unalert(rec)
  -- the old body's legs: destroyed with it after this event, but a beached new body would see
  -- them still valid before that and skip its own
  wreck.clear(rec)
  set[old_unit] = nil
  -- A body we already keep (a beached one kept before the swap landed on it): ONE record, so its
  -- alert comes down and its legs stay his - never a second set drawn over them (measured: 92).
  local new_unit = new_entity.unit_number --[[@as integer]]
  local prior = set[new_unit]
  if prior and prior ~= rec then
    unalert(prior)
    if wreck.drawn(prior, new_entity) then rec.wreck = prior.wreck else wreck.clear(prior) end
  end
  rec.entity = new_entity
  set[new_unit] = rec
  script.register_on_object_destroyed(new_entity)
  if new_entity.name == C.beached then
    alert(rec, game.tick)
    wreck.ensure(rec, new_entity)
  end
end

---on_init and on_configuration_changed: keep every beached body already on the map (a save with
---one from before this code, a playtest swap) and redraw any legs an update re-cut
---(wreck.ensure's geometry stamp). One at full health gets up on the next poll. Idempotent; a
---no-op while D.1's body is not built.
function M.adopt_all()
  if prototypes.entity[C.beached] == nil then return end
  for _, surface in pairs(game.surfaces) do
    for _, entity in pairs(surface.find_entities_filtered{name = C.beached}) do
      adopt(entity, game.tick)
    end
  end
end

---HARNESS ONLY: one body's record (nil when it is not kept) and how many are kept map-wide.
---`wreck` is his broken legs' render objects as the record holds them (ids, drawn on `wreck_unit`).
---@class Jamaltron.BreakageState
---@field kept boolean
---@field flop_at integer?
---@field alert_at integer?
---@field position MapPosition?
---@field beached integer
---@field wreck integer[]?
---@field wreck_unit integer?

---@param entity LuaEntity?
---@return Jamaltron.BreakageState
function M.state(entity)
  local set, count = beached(), 0
  for _ in pairs(set) do count = count + 1 end
  local rec = entity and entity.valid and entity.unit_number and set[entity.unit_number] or nil
  local ids = nil
  if rec and rec.wreck then
    ids = {}
    for i, o in ipairs(rec.wreck.objects) do ids[i] = o.valid and o.id or 0 end   -- 0: gone
  end
  return {kept = rec ~= nil, flop_at = rec and rec.flop_at, alert_at = rec and rec.alert_at,
          position = rec and rec.position, beached = count, wreck = ids,
          wreck_unit = rec and rec.wreck and rec.wreck.unit}
end

return M
