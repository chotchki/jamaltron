-- Jamal talks (PLAN D.5.2). The SAYER: whether he speaks at all, on which channel, and what it
-- costs him afterwards. WHAT he says is scripts/speech/pick.lua; the lines are the generated
-- scripts/lines.lua; every rule below is character/lines.md's, cited by section.
--
-- ONE RECORD PER JAMALTRON, in `storage`, keyed by unit_number: the leg-break count ({N}), the
-- once_per_save fired-set, the recent groups anti-repeat reads, the `flopping` fork, a pending
-- chain, the silence windows, the shore episode and his current bubble. No module-level state
-- but caches that are a pure function of code and prototypes (ROWS below, scripts/ground.lua's
-- table), so multiplayer stays in sync and a save round-trips (E.6).
--
-- WHEN HE MAY SPEAK, in the order say() checks it:
--   * R4 - on a broken landing `land` never speaks: `legs_break` is the landing line
--   * R5 - a pending chain owns his speech until it lands; death and the two swap pools cancel
--     it instead (a punchline delivered by a corpse, or across a swap, is a bug)
--   * attacking.03's burst window, ahead of the cooldown so every call inside it pushes it on
--   * the speech cooldown gates AMBIENT pools only. An event line (boarding, a jump, a break, a
--     death) always gets through and still resets the clock, so ambient chatter waits
--   * the other silence windows, keyed by the ROW that opened them (lines.md, the silence table)
--   * the BUBBLE CAP (F.3): jamaltron-max-bubbles live speech bubbles map-wide, since each costs
--     the GPU (measured 0/10/25/50 live -> 1.3/5.2/7.5/8.8 ms a frame). At the cap an ambient
--     line does not happen at all (checked BEFORE the roll, so nothing is recorded and a capped
--     fight costs no picks); an event line takes down the oldest live AMBIENT bubble to make
--     room, or goes up anyway when every live bubble is an event's (a soft ceiling). A chain's
--     punchline is part of its head's utterance and always lands. Narration is not capped
--   * R3 - `died` ignores all of the above except the chain it cancels
-- A speech window hushes the speech CHANNEL before the roll (narration still fires), and
-- suppresses instead of re-rolling: a second-choice line is the failure the window exists for.
-- R6 is poll()'s: while a shore holds him (speech/stall.lua: stuck over blocking ground, the line
-- pending or said) `moving` and `idle` stay quiet and idle's clock keeps being pushed; a follower
-- lurching at a slot in a lake says no `moving`; say() latches an episode only on a line SAID.

local lines = require("scripts.lines")
local pick = require("scripts.speech.pick")
local stall = require("scripts.speech.stall")
local ground = require("scripts.ground")
local C = require("prototypes.shared")

local M = {}

---Ticks a bubble or a narration note stays up: a 60-character line reads twice in five seconds;
---a chain's follow-up replaces the bubble well inside it.
M.SHOW_TICKS = 5 * 60

---Ticks a bubble keeps standing (and drawing) after its lifetime: the fade-out, compi's
---fade_in_out_ticks (30), which our copy inherits. MEASURED 2.1.17: a bubble with lifetime 300
---leaves count_entities_filtered 329 ticks after it went up. The cap counts to then; destroy()
---takes one down at once.
M.FADE_TICKS = 29

---Tiles within which a player who asked for chat echo gets his lines: about where his bubble is
---readable on screen at default zoom. The driver and passenger always get them.
M.ECHO_RADIUS = 40

---Pools the speech cooldown gates. The rest are EVENTS (once per boarding, jump, break, repair,
---shore stall, death), and a cooldown swallowing one is a line nobody hears again.
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

---How long the gun must be quiet before attacking.03's window ends.
M.BURST_GAP_TICKS = 10 * 60

---Health ratios that fire `low_health` on the way DOWN, one line each (lines.md suggests
---0.35 and 0.15), each re-armed once he is healed back above it by LOW_REARM.
M.LOW_HEALTH = {0.35, 0.15}
M.LOW_REARM = 0.1

---Seconds between idle lines while undriven and still, per verbosity. A first pass: idle is the
---pool a player hears most, so `quiet` should mean it.
M.IDLE_SECONDS = {quiet = 90, normal = 45, unbearable = 25}

---`moving` is the pool that can fire constantly: at most one line per this many cooldowns.
M.MOVING_COOLDOWNS = 3

---jamaltron-max-bubbles where the setting cannot be read (a unit test's fake game): its default.
M.MAX_BUBBLES = 20

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
---@field pending {id: string, due: integer, ambient: boolean?}? a chain follow-up waiting to land
---@field hush_speech_until integer?
---@field burst_until integer?
---@field skip_flops integer
---@field low boolean[] which LOW_HEALTH thresholds are armed
---@field idle_at integer? tick the next idle line is due
---@field moved_at integer? tick of his last `moving` line
---@field pos MapPosition? where he was at the last poll
---@field stall Jamaltron.StallState? the shore episode, speech/stall.lua's; nil until a poll
---@field bubble LuaEntity?
---@field bubble_id string? the row the bubble shows, so a body swap can say it again
---@field bubble_until integer? tick the bubble times out
---@field note LuaRenderObject?
---@field fire Jamaltron.FireState? the gun's burst and friendly fire, scripts/attack.lua's

---One live speech bubble, in the map-wide registry the cap counts (keyed by the unit of the
---shark it hangs on - one bubble per shark).
---@class Jamaltron.BubbleSlot
---@field bubble LuaEntity
---@field born integer tick it went up; a transfer keeps it, so the oldest stays the oldest
---@field ends integer tick it is gone from the map: its lifetime and its fade-out
---@field ambient boolean chatter, which an event line may take down

---@class Jamaltron.SpeechRoot
---@field speech table<integer, Jamaltron.SpeechRecord>
---@field bubbles table<integer, Jamaltron.BubbleSlot>
---@field bubbles_at integer? the tick `bubbles_n`/`bubbles_amb`/`bubbles_next` hold for; nil = recount
---@field bubbles_n integer? entries in `bubbles` - while `bubbles_at` is this tick, exactly
---@field bubbles_amb integer? how many of them are ambient
---@field bubbles_next integer? the earliest `ends` among them, or earlier (a slot taken out since)
---@field debug (boolean|string)?

---@return Jamaltron.SpeechRoot
local function root()
  storage.jamaltron = storage.jamaltron or {}
  local r = storage.jamaltron
  r.speech = r.speech or {}
  r.bubbles = r.bubbles or {}     -- lazy: a save from before the cap starts counting from here
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
local function max_bubbles()
  local s = settings.global["jamaltron-max-bubbles"]
  return s and tonumber(s.value) or M.MAX_BUBBLES
end

---How many bubbles are up, and the tick the next one runs out (nil: none up). A bubble past its
---lifetime or no longer valid (taken down, or gone with its shark) frees its slot here. Counted
---ONCE a tick; after that set_slot() keeps the count current through every bubble this file puts
---up or takes down, so a poll of a hundred waiting flops reads one number and a mass break of 200
---is 200 updates, not 200 rescans (before: 18915 .valid reads for 200 events in a tick,
---measured). A bubble the ENGINE takes down mid-tick is counted until the next tick: the cap
---errs high by one tick. Never a surface scan.
---@param now integer
---@return integer, integer?
local function live(now)
  local r = root()
  if r.bubbles_at ~= now then
    local n, amb, next_free = 0, 0, nil
    for unit, slot in pairs(r.bubbles) do
      if slot.ends <= now or not slot.bubble.valid then
        r.bubbles[unit] = nil                        -- clearing a key mid-pairs is allowed
      else
        n = n + 1
        if slot.ambient then amb = amb + 1 end
        if next_free == nil or slot.ends < next_free then next_free = slot.ends end
      end
    end
    r.bubbles_at, r.bubbles_n, r.bubbles_amb, r.bubbles_next = now, n, amb, next_free
  end
  return r.bubbles_n, r.bubbles_next
end

---Put `slot` (nil: none) under `unit` in the registry, keeping this tick's count exact.
---@param r Jamaltron.SpeechRoot
---@param unit integer
---@param slot Jamaltron.BubbleSlot?
---@param now integer
local function set_slot(r, unit, slot, now)
  local old = r.bubbles[unit]
  r.bubbles[unit] = slot
  if r.bubbles_at ~= now then return end            -- no count this tick: the next live() makes one
  if old then
    r.bubbles_n = r.bubbles_n - 1
    if old.ambient then r.bubbles_amb = r.bubbles_amb - 1 end
  end
  if slot then
    r.bubbles_n = r.bubbles_n + 1
    if slot.ambient then r.bubbles_amb = r.bubbles_amb + 1 end
    if r.bubbles_next == nil or slot.ends < r.bubbles_next then r.bubbles_next = slot.ends end
  end
end

---Is the cap reached for a new bubble from `rec`? His own live bubble does not count: a new line
---replaces it, so the number on screen does not grow. Also returns the tick the next slot frees.
---@param rec Jamaltron.SpeechRecord
---@param now integer
---@return boolean, integer?
local function full(rec, now)
  local n, next_free = live(now)
  if root().bubbles[rec.entity.unit_number] then
    n = n - 1                                        -- counted, since live() just ran this tick
  end
  return n >= max_bubbles(), next_free
end

---An event line (or a punchline) needs a slot: at the cap, take down the oldest live AMBIENT
---bubble that is not his own. With none to take (every live bubble is an event's) it goes up
---anyway: the cap is a soft ceiling for events. Age ties go to the lower unit, so every peer
---evicts the same one.
---@param rec Jamaltron.SpeechRecord
---@param now integer
local function make_room(rec, now)
  if not full(rec, now) then
    return
  end
  local r = root()
  if r.bubbles_amb == 0 then
    return                                           -- nothing to take down: skip the scan
  end
  local own = rec.entity.unit_number
  local oldest, born = nil, nil
  for unit, slot in pairs(r.bubbles) do
    if unit ~= own and slot.ambient and slot.ends > now and slot.bubble.valid
        and (born == nil or slot.born < born or (slot.born == born and unit < oldest)) then
      oldest, born = unit, slot.born
    end
  end
  if oldest then
    r.bubbles[oldest].bubble.destroy()
    set_slot(r, oldest, nil, now)
  end
end

---@return integer
local function idle_ticks()
  local seconds = M.IDLE_SECONDS[verbosity()] or M.IDLE_SECONDS.normal
  -- +-25%, so a yard of parked jamaltrons does not speak in unison
  return math.floor(seconds * 60 * (0.75 + 0.5 * math.random()))
end

---This entity's record, created on first use when `create`. nil for an invalid entity or one
---with no unit number.
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
    -- The one cleanup path: mined, died, destroyed by another mod all land in
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

---Put one row on screen. `still` is a line said by something about to stop existing (a death):
---it cannot follow him, so it is drawn where he fell. A speech BUBBLE cannot: the engine
---refuses one with nothing to hang on ("Need entity target", found by the D.5.4 harness on a
---death that rolled a speech row), and the wreck only exists by on_post_entity_died, after his
---record's entity is gone. So a dying speech line is plain white world text, no prefix, beside
---narration's grey "Game Note:".
---
---Every bubble goes into the registry the cap counts; `ambient` marks one an event may take down.
---@param rec Jamaltron.SpeechRecord
---@param row table
---@param still boolean
---@param ambient boolean
local function render(rec, row, still, ambient)
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
    local now = game.tick
    rec.bubble = entity.surface.create_entity{
      name = C.speech_bubble, position = entity.position, text = text, source = entity,
      lifetime = M.SHOW_TICKS}
    rec.bubble_id, rec.bubble_until = row.id, now + M.SHOW_TICKS
    set_slot(root(), entity.unit_number, rec.bubble and {bubble = rec.bubble, born = now,
      ends = rec.bubble_until + M.FADE_TICKS, ambient = ambient}, now)
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

---A NEW utterance, after the roll: on screen, then everything saying it costs (the cooldown
---clock, the idle clock, a once_per_save gate, the window this row opens, the chain it starts).
---@param rec Jamaltron.SpeechRecord
---@param row table
---@param key string the pool it came from
---@param dying boolean
---@return string
local function commit(rec, row, key, dying)
  local now = game.tick
  local ambient = M.AMBIENT[key] == true
  render(rec, row, dying, ambient)
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
  if row.follow and not dying and not lines.pools[key].swap then
    -- The follow-up inherits the head's tier by being delivered unconditionally below, and the
    -- head's kind: an ambient head's punchline is chatter an event may later take down.
    rec.pending = {id = row.follow, due = now + row.delay, ambient = ambient}
  end
  return row.id
end

---Jamal says a line from pool `key`. Returns the row id said, or nil when he stays quiet (often
---the RIGHT answer; see the gate order in the header).
---
---For the swap pools (`legs_break`, `repaired`) call this AFTER D.4's swap, on the entity that
---now exists, or the bubble follows a shark about to be deleted.
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
  local ambient = M.AMBIENT[key] == true

  -- State the event CARRIES is kept whether or not he gets a word in: the count and the fork
  -- belong to the break, not the line about it (R2). A break or a repair also ends whatever the
  -- LAST break's silence was still skipping, or an earlier legs_break.18 eats this one's first
  -- flop.
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
    -- attacking.03's window BEFORE the cooldown: every call inside it is the gun still going and
    -- must push it on. Behind the cooldown (D.5's order) the window never saw a call (the row
    -- resets the cooldown, and both run 10 s), so it lapsed mid-fight (D.7).
    if key == "attacking" and rec.burst_until then
      if now < rec.burst_until then
        rec.burst_until = now + M.BURST_GAP_TICKS       -- the burst is still going
        return nil
      end
      rec.burst_until = nil
    end
    if ambient and rec.last_tick and now - rec.last_tick < cooldown_ticks() then
      return nil
    end
    if key == "flopping" and rec.skip_flops > 0 then
      rec.skip_flops = rec.skip_flops - 1
      return nil
    end
    if rec.hush_speech_until and now < rec.hush_speech_until then
      channel = "narration"
    elseif ambient and full(rec, now) then
      -- The cap, before the roll: chatter that did not happen (no cooldown, anti-repeat,
      -- once_per_save, chain or echo). Before, because a capped fight calls this on every hit
      -- and a roll costs ~8 us; the cost is that the few ambient NARRATION rows (flopping 1 of
      -- 38, damaged 1 of 14, attacking 1 of 13, moving 2 of 13) wait too.
      return nil
    end
  end

  local row = pick.pick(lines, pool, {verbosity = verbosity(), cond = cond, fired = rec.fired,
                                      recent = rec.recent, last_id = rec.last_id,
                                      channel = channel}, math.random)
  if row == nil then
    return nil
  end
  if not (ambient or dying) and row.ch ~= "narration" then
    make_room(rec, now)                        -- an event always speaks; a dying line is no bubble
  end
  local id = commit(rec, row, key, dying)
  -- A line about the ground under him opens the shore episode (R6), here only, so it follows a
  -- row SAID: a refused hop and a stall at one lake are one episode.
  if key == "shore" or (key == "jump_refused" and ground.is_ground(cond)) then
    stall.latch(rec, now)
  end
  return id
end

---Deliver every due chain follow-up. Exempt from anti-repeat, the windows, the cooldown (SPEC)
---and the bubble cap: it is the second half of an utterance already in flight, so it makes room
---the way an event does. Mostly it needs none: every chain lands inside its head's bubble
---lifetime and replaces it.
---@param tick integer
function M.deliver_due(tick)
  for _, rec in pairs(root().speech) do
    local pending = rec.pending
    if pending and pending.due <= tick then
      rec.pending = nil
      local row = ROWS[pending.id]
      if row and rec.entity.valid then
        if row.ch ~= "narration" then make_room(rec, tick) end
        render(rec, row, false, pending.ambient == true)
      end
    end
  end
end

---Stamp the flopping fork by hand. say("legs_break", side) already does; this is for E.4 if the
---break and its line ever come apart.
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

---D.4's swap: the record follows him to the entity that replaces him (count, fired-set, fork,
---recent groups, the shore gap clock); the pending chain does not (SPEC: a swap cancels it).
---That suits a JUMP too: the takeoff clears the floor for the jump line R5 would swallow, the
---jump pool has no chain heads, and land.11's chain starts after the landing swap.
---
---What he is saying stays up: the narration note is re-pinned to the new body (a render target
---is writable), and a bubble (whose source is not) is said again on it for the rest of its time.
---Call it while the old body is still valid, or the bubble died with it.
---
---The shore EPISODE ends with the body and its gap clock rides (E.2.2: a swap out and back at one
---lake is one line); a body change is no walk, so the next poll starts from the new body.
---@param old_unit integer
---@param new_entity LuaEntity
function M.transfer(old_unit, new_entity)
  local recs = root().speech
  local rec = recs[old_unit]
  if rec == nil or not (new_entity.valid and new_entity.unit_number) then
    return
  end
  local new_unit = new_entity.unit_number --[[@as integer]]
  -- A record the new body already has goes first, with what it drew: another mod swapping him
  -- back with raise_built got one from our built line and left two bubbles on him (measured).
  local stale = recs[new_unit]
  if stale and stale ~= rec then
    if stale.bubble and stale.bubble.valid then stale.bubble.destroy() end
    if stale.note and stale.note.valid then stale.note.destroy() end
  end
  local r, now = root(), game.tick
  local slot = r.bubbles[old_unit]                 -- the bubble's place in the cap moves with it
  set_slot(r, old_unit, nil, now)
  set_slot(r, new_unit, nil, now)
  recs[old_unit] = nil
  rec.entity = new_entity
  rec.pending = nil
  rec.pos = nil
  local st = rec.stall
  if st then
    rec.stall = {n = 0, spoke = st.spoke}
  end
  local note = rec.note
  local target = note and note.valid and note.target
  if note and target and target.entity then       -- a death line is pinned to a spot: left be
    note.target = {entity = new_entity, offset = target.offset}
  end
  local bubble = rec.bubble
  rec.bubble = nil
  if bubble and bubble.valid then
    bubble.destroy()
    local row = rec.bubble_id and ROWS[rec.bubble_id]
    local left = (rec.bubble_until or 0) - game.tick
    if row and left > 0 then
      rec.bubble = new_entity.surface.create_entity{
        name = C.speech_bubble, position = new_entity.position, text = text_of(rec, row),
        source = new_entity, lifetime = left}
      if rec.bubble then                           -- same age and kind: the same line, re-hung
        set_slot(r, new_unit, {bubble = rec.bubble, born = slot and slot.born or now,
                               ends = rec.bubble_until + M.FADE_TICKS,
                               ambient = slot ~= nil and slot.ambient}, now)
      end
    end
  end
  recs[new_unit] = rec
  script.register_on_object_destroyed(new_entity)
end

---When an AMBIENT line from `entity` can next pass the two gates about TIME, not taste (the
---speech cooldown and the bubble cap), so breakage.lua's flop and poll()'s idle wait for it
---instead of losing a whole interval. `tick` or earlier means now. No promise he speaks then (the
---roll, R5 and the windows still decide). At the cap it is the tick the next slot frees, told to
---every waiting Jamal at once, and the first to ask then gets it: the CALLER must ask oldest
---first, or the same few win every slot.
---@param entity LuaEntity
---@param tick integer
---@return integer
function M.ambient_free_at(entity, tick)
  local rec = M.record(entity, false)
  if rec == nil then
    return tick
  end
  if rec.last_tick then
    local free = rec.last_tick + cooldown_ticks()
    if tick < free then return free end
  end
  if not (rec.hush_speech_until and tick < rec.hush_speech_until) then   -- hushed = narration
    local capped, next_free = full(rec, tick)
    if capped then return next_free or tick end
  end
  return tick
end

---Live speech bubbles the cap is counting right now.
---@param tick integer
---@return integer
function M.live_bubbles(tick)
  return (live(tick))
end

---Every record, by unit number: scripts/attack.lua's poll walks them, its burst living on the
---record as speech/stall.lua's shore episode does.
---@return table<integer, Jamaltron.SpeechRecord>
function M.records()
  return root().speech
end

---Forget an entity: on_object_destroyed calls this with the unit number. Does NOT destroy a death
---line still on screen: those are drawn pinned and time out by themselves.
---@param unit integer
function M.forget(unit)
  root().speech[unit] = nil
end

---What damage just did: a low-health line on the way through a threshold, else the
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

---Oldest idle_at first, then the lower unit: every peer sorts the same.
---@param a Jamaltron.SpeechRecord
---@param b Jamaltron.SpeechRecord
---@return boolean
local function idle_before(a, b)
  if a.idle_at ~= b.idle_at then return a.idle_at < b.idle_at end
  return a.entity.unit_number < b.entity.unit_number
end

---The slow clock (D.5.3, E.2.2): the shore stall, low-health re-arming, `moving` and `idle`.
---Called about once a second; a parked, empty jamaltron costs seven reads past `valid` (name,
---position, driver, passenger, stall's own name and autopilot destination, health); the stall
---probes further only on a slow poll.
---
---An idle line due while the cap (or the cooldown) holds WAITS with idle_at unchanged, instead of
---spending a 34-56 s interval on a line that never happened. Due idle lines go oldest idle_at
---first, so a freed slot goes round the yard, not to whoever pairs() reaches first (breakage.poll
---does the same for flops, where it measured 31 of 100 starved).
---@param tick integer
function M.poll(tick)
  local moving_gap = cooldown_ticks() * M.MOVING_COOLDOWNS
  local idle = nil
  for _, rec in pairs(root().speech) do
    local entity = rec.entity
    if entity.valid then
      -- D.4.4: the shore, `moving` and `idle` are the VEHICLE's, ONE gate for all three. A
      -- beached Jamal has no feet to stall on and flops on E.4's clock; an airborne one is
      -- mid-arc, where `moving` is true and the wrong line. It also keeps autopilot_destination
      -- (throws on anything but a spider-vehicle) off a car a remote say gave a record.
      if entity.name == C.name then
        local pos = entity.position
        local occupied = entity.get_driver() ~= nil or entity.get_passenger() ~= nil
        -- The stall FIRST, on this poll's own reads: say() latches the episode on a row said.
        local shore = stall.check(rec, tick, pos, occupied)
        if shore then
          M.say(entity, "shore", shore)
        end
        local moved = rec.pos ~= nil and dist2(pos, rec.pos) > 0.25
        rec.pos = pos
        if stall.holding(rec) then
          -- R6: a retry lurch is not walking and a lake is not idle. PUSHED, not skipped, or idle
          -- fires the poll the episode ends.
          rec.idle_at = tick + idle_ticks()
        elseif moved then
          rec.idle_at = tick + idle_ticks()
          if not stall.pushed(rec)
              and (occupied or entity.autopilot_destination ~= nil)
              and (rec.moved_at == nil or tick - rec.moved_at >= moving_gap)
              and M.say(entity, "moving") then
            rec.moved_at = tick
          end
        elseif not occupied and rec.idle_at and tick >= rec.idle_at then
          idle = idle or {}
          idle[#idle + 1] = rec
        end
      end
      local ratio = entity.get_health_ratio()        -- every body: a repair re-arms them
      if ratio then
        for i, threshold in ipairs(M.LOW_HEALTH) do
          if not rec.low[i] and ratio > threshold + M.LOW_REARM then rec.low[i] = true end
        end
      end
    end
  end
  if idle then
    if #idle > 1 then table.sort(idle, idle_before) end
    for _, rec in ipairs(idle) do
      if M.ambient_free_at(rec.entity, tick) <= tick then
        rec.idle_at = tick + idle_ticks()
        M.say(rec.entity, "idle")
      end
    end
  end
end

---Track every jamaltron already on the map (from a save predating this code, or placed by the
---map editor). Idempotent.
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

---HARNESS ONLY: say one named row as a new utterance, skipping every gate and the roll, so a
---test can open a window or start a chain on purpose instead of waiting for the dice. `still`
---renders it as a death does, reaching both of a death's render paths (speech and narration)
---on purpose. A forced shore row opens no shore episode: that latch is say()'s, on the reason
---the event reported.
---@param entity LuaEntity
---@param id string
---@param still boolean?
---@return string?
function M.force(entity, id, still)
  local rec, row = M.record(entity, true), ROWS[id]
  if rec == nil or row == nil then
    return nil
  end
  return commit(rec, row, id:match("^(.-)%.%d+$"), still == true)
end

---HARNESS ONLY: every record, for leak checks: how many, their units, and how many point at a
---dead entity or sit under a unit that is not their entity's.
---@return {records: integer, units: integer[], dead: integer, mismatched: integer}
function M.census()
  local out = {records = 0, units = {}, dead = 0, mismatched = 0}
  for unit, rec in pairs(root().speech) do
    out.records = out.records + 1
    out.units[#out.units + 1] = unit
    if not rec.entity.valid then
      out.dead = out.dead + 1
    elseif rec.entity.unit_number ~= unit then
      out.mismatched = out.mismatched + 1
    end
  end
  return out
end

---HARNESS ONLY: a copy of one record's scalars to assert on. The shore episode: `stall_tick` is
---the gap clock (tick of the last line that latched), `stall_open` an episode not yet over,
---`holding` and `pushed` what poll() reads for R6. The map-wide cap's registry: `live_bubbles`
---it counts, `ambient_bubbles` of them an event may take down.
---@param entity LuaEntity
---@return table?
function M.state(entity)
  local rec = M.record(entity, false)
  if rec == nil then
    return nil
  end
  local fired = {}
  for id in pairs(rec.fired) do fired[#fired + 1] = id end
  local st = rec.stall
  local now = game.tick
  local bubbles, ambient = live(now), 0
  for _, slot in pairs(root().bubbles) do
    if slot.ambient and slot.ends > now and slot.bubble.valid then ambient = ambient + 1 end
  end
  return {breaks = rec.breaks, fork = rec.fork, last_id = rec.last_id, last_tick = rec.last_tick,
          pending = rec.pending and rec.pending.id, pending_due = rec.pending and rec.pending.due,
          hush_speech_until = rec.hush_speech_until, skip_flops = rec.skip_flops,
          fired = fired, recent = #rec.recent, idle_at = rec.idle_at,
          stall_tick = st and st.spoke, stall_open = st ~= nil and st.at ~= nil,
          holding = stall.holding(rec), pushed = stall.pushed(rec),
          bubble = rec.bubble ~= nil and rec.bubble.valid and rec.bubble.name or nil,
          note = rec.note ~= nil and rec.note.valid or false,
          live_bubbles = bubbles, ambient_bubbles = ambient}
end

return M
