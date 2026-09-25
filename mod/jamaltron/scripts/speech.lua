-- Jamal talks (PLAN D.5.2). The SAYER: whether he speaks at all, which channel, and what it
-- costs him afterwards. WHAT he says is scripts/speech/pick.lua; the lines are the generated
-- scripts/lines.lua, and every rule below is character/lines.md's, cited by section.
--
-- ONE RECORD PER JAMALTRON, in `storage`, keyed by unit_number: the leg-break count ({N}),
-- the once_per_save fired-set, the recent groups anti-repeat reads, the `flopping` fork, a
-- pending chain, the silence windows and his current bubble. No module-level state, so
-- multiplayer stays in sync and a save round-trips (E.6).
--
-- WHEN HE MAY SPEAK, in the order say() checks it:
--   * R4 - on a broken landing `land` never speaks: `legs_break` is the landing line
--   * R5 - a pending chain owns his speech until it lands; death and the two swap pools
--     cancel it instead (a punchline delivered by a corpse, or across a swap, is a bug)
--   * the speech cooldown gates AMBIENT pools only. An event line (boarding, a jump, a break,
--     a death) always gets through and still resets the clock, so ambient chatter waits
--   * the silence windows, keyed by the ROW that opened them (lines.md, the silence table)
--   * R3 - `died` ignores all of the above except the chain it cancels
-- A speech window hushes the speech CHANNEL before the roll (narration still fires), and it
-- suppresses rather than re-rolls - a second-choice line is the failure the window exists for.

local lines = require("scripts.lines")
local pick = require("scripts.speech.pick")
local C = require("prototypes.shared")

local M = {}

---Ticks a bubble or a narration note stays up. Five seconds reads a 60-character line
---twice; a chain's follow-up replaces the bubble well inside it.
M.SHOW_TICKS = 5 * 60

---Tiles within which a player who asked for chat echo gets his lines: about the distance his
---bubble is readable on screen at default zoom. The driver and passenger always get them.
M.ECHO_RADIUS = 40

---Pools the speech cooldown gates. The rest are EVENTS - once per boarding, jump, break,
---repair, death - and a cooldown swallowing one of those is a line nobody hears again.
M.AMBIENT = {idle = true, moving = true, attacking = true, damaged = true, flopping = true,
             command_done = true}

---The silence windows (lines.md: "THREE OF THESE ROWS ASSERT AN ONGOING SILENCE"), keyed by
---the row that names the silence. Per entity, and only ever the speech side.
---  speech_ticks - no SPEECH for this long; narration still fires (low_health.01, 15 s)
---  burst        - `attacking` is hushed until the gun has been quiet for BURST_GAP_TICKS
---  skip_flops   - the next N `flopping` ticks say nothing (bk 8: the break, and only then
---                 the flopping)
M.WINDOWS = {
  ["low_health.01"] = {speech_ticks = 15 * 60},
  ["attacking.03"] = {burst = true},
  ["legs_break.18"] = {skip_flops = 1},
}

---How long the gun has to have been quiet before attacking.03's window ends.
M.BURST_GAP_TICKS = 10 * 60

---Health ratios that fire `low_health` on the way DOWN, one line each (lines.md suggests
---0.35 and 0.15), each re-armed once he is healed back above it by LOW_REARM.
M.LOW_HEALTH = {0.35, 0.15}
M.LOW_REARM = 0.1

---Seconds between idle lines while undriven and still, per verbosity. A first pass: the idle
---pool is the one a player hears most, so `quiet` should mean it.
M.IDLE_SECONDS = {quiet = 90, normal = 45, unbearable = 25}

---`moving` is the pool that can fire constantly: at most one line per this many cooldowns.
M.MOVING_COOLDOWNS = 3

---Every row by id, for chain delivery.
---@type table<string, table>
local ROWS = {}
for _, pool in pairs(lines.pools) do
  for _, row in ipairs(pool.rows) do
    ROWS[row.id] = row
  end
end
M.ROWS = ROWS

---@class Jamaltron.SpeechRecord
---@field entity LuaEntity
---@field breaks integer cumulative leg breaks, the {N} in four rows
---@field fired table<string, boolean> once_per_save row ids already said
---@field recent string[] groups of his recent lines, oldest first
---@field last_id string? the last row he said
---@field last_tick integer? tick of his last NEW utterance (a chain follow-up is not one)
---@field fork string? self | external, stamped by the break, read by every flopping tick
---@field pending {id: string, due: integer}? a chain follow-up waiting to land
---@field hush_speech_until integer?
---@field burst_until integer?
---@field skip_flops integer
---@field low boolean[] which LOW_HEALTH thresholds are armed
---@field idle_at integer? tick the next idle line is due
---@field moved_at integer? tick of his last `moving` line
---@field pos MapPosition? where he was at the last poll
---@field bubble LuaEntity?
---@field note LuaRenderObject?

---@return {speech: table<integer, Jamaltron.SpeechRecord>, debug: (boolean|string)?}
local function root()
  storage.jamaltron = storage.jamaltron or {}
  local r = storage.jamaltron
  r.speech = r.speech or {}
  return r
end

---@return string
local function verbosity()
  return tostring(settings.global["jamaltron-verbosity"].value)
end

---@return integer
local function cooldown_ticks()
  return math.floor((tonumber(settings.global["jamaltron-speech-cooldown"].value) or 10) * 60)
end

---@return integer
local function idle_ticks()
  local seconds = M.IDLE_SECONDS[verbosity()] or M.IDLE_SECONDS.normal
  -- +-25%, so a yard of parked jamaltrons does not speak in unison
  return math.floor(seconds * 60 * (0.75 + 0.5 * math.random()))
end

---This entity's record, created on first use when `create`. nil for an invalid entity or
---one with no unit number.
---@param entity LuaEntity
---@param create boolean?
---@return Jamaltron.SpeechRecord?
function M.record(entity, create)
  if not (entity and entity.valid and entity.unit_number) then
    return nil
  end
  local recs = root().speech
  local unit = entity.unit_number --[[@as integer]]
  local rec = recs[unit]
  if rec == nil and create then
    rec = {entity = entity, breaks = 0, fired = {}, recent = {}, skip_flops = 0,
           low = {true, true}, idle_at = game.tick + idle_ticks()}
    recs[unit] = rec
    -- The one cleanup path: mined, died, destroyed by another mod - all of it lands in
    -- on_object_destroyed with the unit number, so no record outlives its shark.
    script.register_on_object_destroyed(entity)
  end
  return rec
end

---The LocalisedString for a row: its locale key, plus the break count where it counts.
---@param rec Jamaltron.SpeechRecord
---@param row table
---@return LocalisedString
local function text_of(rec, row)
  if row.count then
    return {lines.locale_section .. "." .. row.id, rec.breaks}
  end
  return {lines.locale_section .. "." .. row.id}
end

---@param a MapPosition
---@param b MapPosition
---@return number
local function dist2(a, b)
  local dx, dy = a.x - b.x, a.y - b.y
  return dx * dx + dy * dy
end

---Chat echo for the players who asked for it (jamaltron-chat-echo) and can see him.
---@param entity LuaEntity
---@param message LocalisedString
local function echo(entity, message)
  local r2 = M.ECHO_RADIUS * M.ECHO_RADIUS
  for _, player in pairs(game.connected_players) do
    if player.mod_settings["jamaltron-chat-echo"].value == true
        and (player.vehicle == entity
             or (player.surface == entity.surface and dist2(player.position, entity.position) <= r2)) then
      player.print(message)
    end
  end
end

---Put one row on screen. `still` is a line said by something about to stop existing (a
---death): it cannot follow him, so it is drawn where he fell. A speech BUBBLE cannot do that
---- the engine refuses one with nothing to hang on ("Need entity target", found by the D.5.4
---harness on a death that rolled a speech row), and the wreck only exists by
---on_post_entity_died, after his record's entity is gone - so a dying speech line is plain
---white world text, no prefix, beside narration's grey "Game Note:".
---@param rec Jamaltron.SpeechRecord
---@param row table
---@param still boolean
local function render(rec, row, still)
  local entity = rec.entity
  local text = text_of(rec, row)
  if still and row.ch ~= "narration" then
    if rec.note and rec.note.valid then rec.note.destroy() end
    rec.note = rendering.draw_text{
      text = text, surface = entity.surface, target = entity.position,
      color = {r = 1, g = 1, b = 1, a = 1}, scale = 1.4, alignment = "center",
      vertical_alignment = "middle", time_to_live = M.SHOW_TICKS}
    echo(entity, {"jamaltron-speech.chat", text})
  elseif row.ch == "narration" then
    -- The game describing him, so visibly NOT a bubble. The "Game Note: " prefix lives here
    -- and nowhere else (lines.md: THE PREFIX SHIPS, AND D.5 APPLIES IT AT RENDER TIME).
    local note = {"jamaltron-speech.narration", text}
    if rec.note and rec.note.valid then
      rec.note.destroy()
    end
    rec.note = rendering.draw_text{
      text = note, surface = entity.surface,
      target = still and entity.position or {entity = entity, offset = {0, -3.5}},
      color = {r = 0.85, g = 0.85, b = 0.8, a = 1}, scale = 1.4, alignment = "center",
      vertical_alignment = "middle", time_to_live = M.SHOW_TICKS}
    echo(entity, note)
  else
    if rec.bubble and rec.bubble.valid then
      rec.bubble.destroy()                -- one bubble per shark: a new line replaces the old
    end
    rec.bubble = entity.surface.create_entity{
      name = C.speech_bubble, position = entity.position, text = text, source = entity,
      lifetime = M.SHOW_TICKS}
    echo(entity, {"jamaltron-speech.chat", text})
  end
  pick.remember(rec.recent, row.grp)
  rec.last_id = row.id
  local debug = root().debug
  if debug then
    log("jamaltron speech " .. tostring(entity.unit_number) .. " " .. row.id)
    if debug == "print" then
      game.print("[jamaltron] " .. row.id)            -- playtesting: the row behind the bubble
    end
  end
end

---A NEW utterance, after the roll: on screen, then everything saying it costs - the
---cooldown clock, the idle clock, a once_per_save gate, the window this row opens and the
---chain it starts.
---@param rec Jamaltron.SpeechRecord
---@param row table
---@param pool table
---@param dying boolean
---@return string
local function commit(rec, row, pool, dying)
  local now = game.tick
  render(rec, row, dying)
  rec.last_tick = now
  rec.idle_at = now + idle_ticks()                  -- anything he says resets the idle clock
  if row.gate == "once_per_save" then
    rec.fired[row.id] = true
  end
  local window = M.WINDOWS[row.id]
  if window then
    if window.speech_ticks then rec.hush_speech_until = now + window.speech_ticks end
    if window.burst then rec.burst_until = now + M.BURST_GAP_TICKS end
    if window.skip_flops then rec.skip_flops = window.skip_flops end
  end
  if row.follow and not dying and not pool.swap then
    -- The follow-up inherits the head's tier by being delivered unconditionally below.
    rec.pending = {id = row.follow, due = now + row.delay}
  end
  return row.id
end

---Jamal says a line from pool `key`. Returns the row id said, or nil when he stays quiet -
---which is often the RIGHT answer, see the gate order at the top of the file.
---
---For the swap pools (`legs_break`, `repaired`) call this AFTER D.4's swap, on the entity
---that now exists, or the bubble follows a shark that is about to be deleted.
---@param entity LuaEntity
---@param key string a pool in scripts/lines.lua
---@param cond string? what the event reports for a split pool: the side of a required split
---  (`self` / `external`), or the value of a gated dimension (`blocked`, `held`, ...)
---@return string?
function M.say(entity, key, cond)
  local pool = lines.pools[key]
  if pool == nil then
    error("jamaltron speech: no pool '" .. tostring(key) .. "'")
  end
  local rec = M.record(entity, true)
  if rec == nil then
    return nil
  end
  local now = game.tick
  local dying = key == "died"

  -- State the event CARRIES is kept whether or not he gets a word in: the count and the fork
  -- belong to the break, not to the line about it (R2).
  -- A break or a repair also ends whatever the LAST break's silence was still skipping, or a
  -- legs_break.18 from an earlier break eats the first flop of this one.
  if key == "legs_break" then
    rec.breaks = rec.breaks + 1
    rec.fork = cond
    rec.skip_flops = 0
  end
  if key == "repaired" then
    rec.fork = nil
    rec.skip_flops = 0
  end
  if key == "flopping" and cond == nil then
    cond = rec.fork
  end

  if key == "land" and cond == "broke" then
    return nil                                                            -- R4
  end
  if rec.pending then                                                     -- R5
    if dying or pool.swap then
      rec.pending = nil
    else
      return nil
    end
  end
  local channel = nil
  if not dying then                                                       -- R3
    if M.AMBIENT[key] and rec.last_tick and now - rec.last_tick < cooldown_ticks() then
      return nil
    end
    if key == "attacking" and rec.burst_until then
      if now < rec.burst_until then
        rec.burst_until = now + M.BURST_GAP_TICKS       -- the burst is still going
        return nil
      end
      rec.burst_until = nil
    end
    if key == "flopping" and rec.skip_flops > 0 then
      rec.skip_flops = rec.skip_flops - 1
      return nil
    end
    if rec.hush_speech_until and now < rec.hush_speech_until then
      channel = "narration"
    end
  end

  local row = pick.pick(lines, pool, {verbosity = verbosity(), cond = cond, fired = rec.fired,
                                      recent = rec.recent, last_id = rec.last_id,
                                      channel = channel}, math.random)
  if row == nil then
    return nil
  end
  return commit(rec, row, pool, dying)
end

---Deliver every chain follow-up that is due. Exempt from anti-repeat, the windows and the
---cooldown (SPEC): it is the second half of an utterance already in flight.
---@param tick integer
function M.deliver_due(tick)
  for _, rec in pairs(root().speech) do
    local pending = rec.pending
    if pending and pending.due <= tick then
      rec.pending = nil
      local row = ROWS[pending.id]
      if row and rec.entity.valid then
        render(rec, row, false)
      end
    end
  end
end

---Stamp the flopping fork by hand. say("legs_break", side) already does; this is for E.4
---if the break and its line ever come apart.
---@param entity LuaEntity
---@param fork string? self | external | nil to clear
function M.set_fork(entity, fork)
  local rec = M.record(entity, true)
  if rec then rec.fork = fork end
end

---Drop a pending follow-up without delivering it.
---@param entity LuaEntity
function M.cancel(entity)
  local rec = M.record(entity, false)
  if rec then rec.pending = nil end
end

---D.4's swap: the record follows him to the entity that replaces him - count, fired-set,
---fork, recent groups - and the pending chain does not (SPEC: a swap cancels it).
---@param old_unit integer
---@param new_entity LuaEntity
function M.transfer(old_unit, new_entity)
  local recs = root().speech
  local rec = recs[old_unit]
  if rec == nil or not (new_entity.valid and new_entity.unit_number) then
    return
  end
  recs[old_unit] = nil
  rec.entity = new_entity
  rec.pending = nil
  rec.bubble, rec.note = nil, nil       -- both were attached to the old entity and go with it
  recs[new_entity.unit_number --[[@as integer]]] = rec
  script.register_on_object_destroyed(new_entity)
end

---Forget an entity: on_object_destroyed calls this with the unit number. Does NOT destroy
---a death line still on screen - those were drawn pinned and time out by themselves.
---@param unit integer
function M.forget(unit)
  root().speech[unit] = nil
end

---Whatever damage just did: a low-health line on the way through a threshold, otherwise the
---(cooldown-throttled) damaged pool.
---@param entity LuaEntity
---@return string?
function M.damaged(entity)
  local rec = M.record(entity, true)
  if rec == nil then return nil end
  local ratio = entity.get_health_ratio()
  if ratio then
    for i = #M.LOW_HEALTH, 1, -1 do                -- the deepest threshold crossed wins
      if rec.low[i] and ratio <= M.LOW_HEALTH[i] then
        for j = 1, i do rec.low[j] = false end     -- one hit through both is one line
        return M.say(entity, "low_health")
      end
    end
  end
  return M.say(entity, "damaged")
end

---The slow clock (D.5.3): low-health re-arming, `moving`, and `idle`. Called about once a
---second; costs one position read per jamaltron.
---@param tick integer
function M.poll(tick)
  local moving_gap = cooldown_ticks() * M.MOVING_COOLDOWNS
  for _, rec in pairs(root().speech) do
    local entity = rec.entity
    if entity.valid then
      local ratio = entity.get_health_ratio()
      if ratio then
        for i, threshold in ipairs(M.LOW_HEALTH) do
          if not rec.low[i] and ratio > threshold + M.LOW_REARM then rec.low[i] = true end
        end
      end
      local pos = entity.position
      local moved = rec.pos ~= nil and dist2(pos, rec.pos) > 0.25
      rec.pos = pos
      local occupied = entity.get_driver() ~= nil or entity.get_passenger() ~= nil
      if moved then
        rec.idle_at = tick + idle_ticks()
        if (occupied or entity.autopilot_destination ~= nil)
            and (rec.moved_at == nil or tick - rec.moved_at >= moving_gap)
            and M.say(entity, "moving") then
          rec.moved_at = tick
        end
      elseif not occupied and rec.idle_at and tick >= rec.idle_at then
        rec.idle_at = tick + idle_ticks()
        M.say(entity, "idle")
      end
    end
  end
end

---Track every jamaltron already on the map: a save that predates this code, or one the map
---editor placed. Idempotent.
function M.adopt_all()
  for _, surface in pairs(game.surfaces) do
    for _, entity in pairs(surface.find_entities_filtered{name = C.name}) do
      M.record(entity, true)
    end
  end
end

---@param on boolean|string true logs every line said (the D.5.4 harness); "print" also puts
---each row id in chat (tools/play.sh's /jamaltron-kit); false stops both
function M.set_debug(on)
  root().debug = on
end

---HARNESS ONLY: say one named row as a new utterance, skipping every gate and the roll -
---so a test can open a window or start a chain on purpose instead of waiting for the dice.
---`still` renders it the way a death does, so the harness reaches both of a death's render
---paths (speech and narration) on purpose instead of by the roll.
---@param entity LuaEntity
---@param id string
---@param still boolean?
---@return string?
function M.force(entity, id, still)
  local rec, row = M.record(entity, true), ROWS[id]
  if rec == nil or row == nil then
    return nil
  end
  local pool = lines.pools[(id:match("^(.-)%.%d+$"))]
  return commit(rec, row, pool, still == true)
end

---HARNESS ONLY: a copy of one record's scalars, for asserting on.
---@param entity LuaEntity
---@return table?
function M.state(entity)
  local rec = M.record(entity, false)
  if rec == nil then
    return nil
  end
  local fired = {}
  for id in pairs(rec.fired) do fired[#fired + 1] = id end
  return {breaks = rec.breaks, fork = rec.fork, last_id = rec.last_id, last_tick = rec.last_tick,
          pending = rec.pending and rec.pending.id, pending_due = rec.pending and rec.pending.due,
          hush_speech_until = rec.hush_speech_until, skip_flops = rec.skip_flops,
          fired = fired, recent = #rec.recent,
          bubble = rec.bubble ~= nil and rec.bubble.valid and rec.bubble.name or nil,
          note = rec.note ~= nil and rec.note.valid or false}
end

return M
