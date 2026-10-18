-- THE BEAT MACHINE (PLAN G.3). EVENT-DRIVEN, never absolute ticks: a beat starts off a position
-- (the engineer reaching him), a swap reason (takeoff / landing / break / repair, off
-- on_spidertron_replaced), the autopilot's completion, the last biter dying, or a fixed hold
-- AFTER one of those. MEASURED (G.1 scene agent): headless and --benchmark-graphics drift apart
-- by up to a 60-tick poll on the same save, so a tick schedule written against the dry run would
-- miss in the take; events hold in both.
--
-- THE QUIET DIRECTOR. jamaltron-speech-cooldown 300 s keeps every AMBIENT pool (idle, moving,
-- damaged, flopping, attacking, command_done) silent for the whole take once he has spoken; the
-- EVENT pools still roll (jump, land, legs_break, repaired), and every row the cut shows is
-- FORCED over the roll on the event's own tick, AFTER the mod has said its own line:
--   takeoff    right after remote jump returns (the mod says its jump line inside try())
--   landing,   in this mod's on_tick of the same tick: jamaltron's on_tick runs first (it is a
--   break      dependency) and lands him from its clock
--   repair     in this mod's on_nth_tick(15): the stand-up is breakage.poll on jamaltron's
--              on_nth_tick(60), which runs after every mod's on_tick (MEASURED in the G.1 story
--              run: a poll-tick stand-up was first seen by an on_tick one tick later) and before
--              this mod's nth-tick (MEASURED here: repair and repaired.07 share tick 3480)
-- on_spidertron_replaced only QUEUES the force: it is raised inside swap.replace before the new
-- body is filled or has his speech record, and before the mod says its line - a row forced there
-- would be replaced by that line.
--
-- WHAT HE SAID, for the captions and the cross-check against the mod's own debug log:
--   line   a SPEECH row that went on screen (forced, or the mod's own roll left standing), its
--          tick, channel, forced, position, and n = his break count (the {N} some rows carry)
--   said   a row the mod said that is on screen for no frame: one a forced row replaced IN THE
--          SAME TICK (replaced_by), or a narration row the director hid (hidden). Both are in
--          the mod's `jamaltron speech <unit> <row>` log. So the mod's log equals line + said, in
--          (tick, said-before-line) order - MEASURED equal, 20 of 20 rows, on the main takes
-- A forced row over a CHAIN HEAD (land.11 schedules a punchline) would still get the punchline
-- delivered over it later: the chain is cancelled with the harness's `transfer` onto his own
-- body (speech.transfer drops `pending`, keeps everything else, re-hangs the bubble), and that is
-- logged as a liberty.
--
-- LIBERTIES are logged as `liberty` events: every setting write, every heal, a cancelled chain,
-- peaceful mode toggled. Forcing a row is the method, not a liberty.

local camera = require("camera")
local journal = require("journal")
local set = require("set")

-- Another mod's files, so by `__jamaltron__/`: the type gate sees the same files the mod requires
-- as scripts.lines / prototypes.*, which is exactly right here.
---@diagnostic disable-next-line: different-requires
local lines = require("__jamaltron__/scripts/lines")
---@diagnostic disable-next-line: different-requires
local flop = require("__jamaltron__/prototypes/beached_sprites_generated")

local M = {}

local H = "jamaltron-harness"
local VEHICLE, AIRBORNE, BEACHED = "jamaltron", "jamaltron-airborne", "jamaltron-beached"
local FOOTFALL = "jamaltron-video-footfall"
local EAST, WEST = defines.direction.east, defines.direction.west
local ORANGE = {1, 0.55, 0.1}           -- a player's default colour, what chotchki's shots show

---Ticks. Every hold is AFTER an event, never a clock time.
M.T = {
  settle = 60,          -- staging -> capture_start: his legs walk out of their spawn pose
  engineer_walk = 45,   -- establish -> the engineer sets off (frame 0 is the poster)
  board_hold = 45,      -- boarding -> hop1's press
  hop1_read = 200,      -- hop1 landing -> hop2 press: land.03 (32 ch) reads in ~3.3 s
  hop2_read = 150,      -- hop2 landing -> the first biter group
  groups = 4,           -- 4 groups of 5 every 60 ticks: MEASURED a ~5.3 s fight, 0 HP lost
  group_gap = 60,
  attacking_after = 20, -- fire_start#1 -> attacking.01 forced
  flame_still = 90,     -- fire_start#1 -> the "flame" still
  clear_hold = 60,      -- wave_clear -> the report order
  report_read = 210,    -- command completed -> the lake press, once he has stopped
  beached_still = 90,
  flop1 = 270,          -- break -> flopping.12 (the contract's director timing)
  flop2 = 570,          -- break -> flopping.02
  cue = 840,            -- break -> repair packs into the roboport
  stand_still = 60,
  stand_hold = 240,     -- stand-up -> the encore press (~4 s)
  wrap_after = 60,      -- encore landing -> wrap
  loop_pre_hold = 60,   -- loop take: spawn -> the first hop (legs settled)
  loop_settle = 60,     -- loop take: landing -> the next press is at +settle+1; the loop is
                        -- 2 * (settle + 31) = 182 ticks, 3.03 s (see the loop section)
  limit = 9000,         -- a take that has not wrapped by staging + this FAILS
}

---Most ticks a beat may take before the take is failed (a stuck machine, not a slow one).
M.MAX = {
  establish = 400, board = 200, hop1 = 600, hop2 = 600, wave = 1500, report = 900,
  lake_jump = 200, beached = 400, apology = 700, repair = 4200, stand = 500, encore = 300,
  loop_pre = 600, loop = 600,
}

---The wave, per group: MEASURED 2 small + 2 medium + 1 big dies in the flame with 0 HP lost.
M.WAVE = {"small-biter", "small-biter", "medium-biter", "medium-biter", "big-biter"}

---@class Video.State
---@field take string
---@field cfg table
---@field s LuaSurface
---@field staged integer
---@field capture_start integer?
---@field capture_end integer?
---@field capturing boolean
---@field wrapped boolean
---@field body LuaEntity
---@field driver LuaEntity
---@field roboport LuaEntity?
---@field cam Video.Cam
---@field beat string?
---@field beat_at integer
---@field seen {id: string?, tick: integer?}
---@field queue {row: string?, heal: boolean?, reason: string}[]
---@field want table<string, string>
---@field heal boolean
---@field count table<string, integer>
---@field last table<string, integer>
---@field arc table?
---@field walking boolean
---@field ammo number?
---@field fire {on: boolean, last: integer?, first: integer?}
---@field biters table<integer, LuaEntity>
---@field spawned integer
---@field groups integer
---@field bots integer?
---@field hp {last: number?, start: integer?, full: integer?, beat: integer?, rise: integer?}
---@field bitten boolean
---@field hidden integer
---@field stills table<integer, string>
---@field flags table<string, integer|boolean>
---@field water_tick integer?
---@field speech_debug boolean

---@return Video.State
local function S()
  return storage.video
end

---@param p MapPosition
---@return number
---@return number
local function xy(p)
  return p.x, p.y
end

---@param why string
function M.fail(why)
  log("VIDEO FAIL " .. why)
  local st = S()
  if st then st.flags.failed = true end
end

---@param rec table
local function ev(rec)
  rec.tick = rec.tick or game.tick
  journal.event(rec)
end

---@param what string
local function liberty(what)
  ev{ev = "liberty", what = what}
  log("VIDEO liberty " .. what)
end

---@param name string
---@param value boolean|number|string
---@param why string
local function setting(name, value, why)
  remote.call(H, "setting", name, value)
  liberty("setting " .. name .. " " .. tostring(value) .. ": " .. why)
end

---The row's channel, off the mod's own catalog (the captions are speech; narration is hidden).
local CHANNEL = {}
for _, pool in pairs(lines.pools) do
  for _, row in ipairs(pool.rows) do CHANNEL[row.id] = row.ch end
end

---Every text the mod drew goes invisible: post owns all text (his narration notes are world
---text and DO land in show_gui=false frames - MEASURED G.1; his bubbles are GUI and never do).
---Sprites and animations (the arc sheets, the broken legs) are left alone. MEASURED (G.3): a
---mod may write .visible on another mod's render object (it reads back false, headless and
---graphics), and the note is gone from the frames - hop2's rolled "Game Note: Up goes Jamal!"
---(jump.04) is nowhere in its arc. Run after anything that can make him speak in a tick: this
---on_tick, the nth-tick pass, every force.
---The write is READ BACK: a hide that does not stick FAILS the take (once), because everything
---downstream trusts it - the captions' cross-check accepts a `said ... hidden` row as never on
---screen, and a narration note burned into every frame would pass it.
local function hide_texts()
  local st = S()
  for _, o in pairs(rendering.get_all_objects("jamaltron")) do
    if o.type == "text" and o.visible then
      o.visible = false
      if o.visible then
        if not st.flags.unhidable then
          st.flags.unhidable = true
          M.fail("cannot hide jamaltron text object " .. o.id .. ": .visible reads back true "
                 .. "after the write, so his narration would be in the frames")
        end
      else
        st.hidden = st.hidden + 1
        if st.hidden == 1 then
          log("VIDEO measured: another mod CAN write .visible on a jamaltron text object (id "
              .. o.id .. " reads back visible=" .. tostring(o.visible) .. ")")
        end
      end
    end
  end
end

---The speech record's view of him right now.
---@return table?
local function speech_state()
  local st = S()
  if not (st.body and st.body.valid) then return nil end
  return remote.call(H, "state", st.body) --[[@as table?]]
end

---A row on screen: forced by the director over whatever the mod rolled this tick.
---@param row string
function M.force(row)
  local st = S()
  local b = st.body
  if not (b and b.valid) then return M.fail("force " .. row .. ": no body") end
  local tick = game.tick
  local before = speech_state()
  -- The mod's own roll THIS tick, not yet logged as a line: it goes under the forced row unseen.
  -- (The same row rolled and forced is still two entries in the mod's log.)
  -- A SPEECH roll is replaced by the forced row (one bubble per shark: replaced_by is the proof
  -- the captions' audit checks); a NARRATION roll is its own channel's world text, never
  -- replaced, and is off screen because hide_texts hides it (hidden).
  if before and before.last_tick == tick and before.last_id
      and not (st.seen.id == before.last_id and st.seen.tick == before.last_tick) then
    local channel = CHANNEL[before.last_id] or "speech"
    if channel == "speech" then
      ev{ev = "said", row = before.last_id, channel = channel, replaced_by = row,
         x = b.position.x, y = b.position.y}
    else
      ev{ev = "said", row = before.last_id, channel = channel, hidden = true,
         x = b.position.x, y = b.position.y}
    end
  end
  local said = remote.call(H, "force", b, row)
  if said ~= row then return M.fail("force " .. row .. " said " .. tostring(said)) end
  local after = speech_state() or {}
  if after.pending then
    remote.call(H, "transfer", b.unit_number, b)
    liberty("cancel chain " .. tostring(after.pending) .. ": its head was replaced by " .. row)
  end
  local x, y = xy(b.position)
  ev{ev = "line", row = row, channel = CHANNEL[row] or "speech", forced = true, x = x, y = y,
     n = after.breaks or 0}
  st.seen = {id = row, tick = tick}
  log("VIDEO line " .. row .. " forced at " .. tick)
  hide_texts()
end

---A row the mod said by itself that stays up (nothing forced over it this tick), or a chain's
---punchline: logged as a `line` at the tick it went up. A NARRATION row is world text the
---director hides (hide_texts), so it is on screen for no frame: `said`, flagged hidden - and,
---as in the game, it does not take down the speech line already up (narration is its own
---channel; speech.lua's render() leaves the bubble be). MEASURED on the second main take: hop2's
---unforced roll was jump.04, "Game Note: Up goes Jamal!", and logged as a line it would have cut
---land.03's caption short and failed the caption builder's speech-only check.
function M.observe()
  local st = S()
  local s = speech_state()
  if not (s and s.last_id) then return end
  if s.last_id == st.seen.id and s.last_tick == st.seen.tick then return end
  local tick = (s.last_tick ~= st.seen.tick and s.last_tick) or game.tick
  local x, y = xy(st.body.position)
  local channel = CHANNEL[s.last_id] or "speech"
  if channel == "speech" then
    ev{tick = tick, ev = "line", row = s.last_id, channel = channel, forced = false, x = x, y = y,
       n = s.breaks or 0}
    log("VIDEO line " .. s.last_id .. " rolled at " .. tick)
  else
    ev{tick = tick, ev = "said", row = s.last_id, channel = channel, hidden = true, x = x, y = y}
    log("VIDEO said " .. s.last_id .. " (" .. channel .. ", hidden) at " .. tick)
  end
  st.seen = {id = s.last_id, tick = s.last_tick}
end

---Forces and heals the swaps queued (see the header for why they wait).
function M.flush_queue()
  local st = S()
  local q = st.queue
  if #q == 0 then return end
  st.queue = {}
  for _, item in ipairs(q) do
    if item.row then M.force(item.row) end
    if item.heal and st.body.valid and st.body.health < st.body.max_health then
      st.body.health = st.body.max_health
      liberty("heal after the " .. item.reason .. ": the thud's health bar would ride the next "
              .. "arc on the ground (G.12)")
    end
  end
end

---@param name string
---@param tick integer
local function beat(name, tick)
  local st = S()
  st.beat, st.beat_at = name, tick
  ev{ev = "beat", name = name}
  log("VIDEO beat " .. name .. " at " .. tick)
end

---His drawn torso relative to his position (the contract's `lift`): the prototype's `height`
---standing or beached (1.5 / 0: the engine draws the torso that many tiles up-screen), the arc's
---own drawing in the air. The arc's raw offset is the sheet's centre (it includes the sheet's
---shift), so it is taken relative to the takeoff tick's, where the arc starts on the standing
---torso: lift is continuous across takeoff and landing. `sprite` is the raw offset.
---@return number[] lift
---@return number[]? sprite
local function lift()
  local st = S()
  local b = st.body
  if b.name == AIRBORNE and st.arc and st.arc.sprite0 then
    local js = remote.call(H, "jump_state", b) --[[@as table]]
    local o = js.arc and js.arc.body
    if o then
      local s0 = st.arc.sprite0
      return {o.x - s0.x, -st.arc.height + (o.y - s0.y)}, {o.x, o.y}
    end
  end
  return {0, -(prototypes.entity[b.name].height or 0)}, nil
end
M.lift = lift

---The driver's jump, and the takeoff logged off the arc the mod built.
---@param label string
---@return boolean
local function press(label)
  local st = S()
  local b = st.body
  if b.autopilot_destination then b.autopilot_destination = nil end
  local r = remote.call(H, "jump", b) --[[@as {jumped: boolean, why: string?, said: string?}]]
  if not r.jumped then
    M.fail(label .. " refused: " .. tostring(r.why))
    return false
  end
  local tick = game.tick
  local js = remote.call(H, "jump_state", st.body) --[[@as table]]
  local arc = js.arc
  if not arc then
    M.fail(label .. ": jumped but no arc on " .. st.body.name)
    return false
  end
  local dx, dy = arc.to.x - arc.from.x, arc.to.y - arc.from.y
  local apex = arc.start + math.floor((arc.land - arc.start) / 2 + 0.5)
  st.arc = {start = arc.start, land = arc.land, peak = arc.peak, apex = apex, from = arc.from,
            to = arc.to, sprite0 = arc.body, height = prototypes.entity[VEHICLE].height or 0}
  st.count.takeoff = st.count.takeoff + 1
  st.last.takeoff = tick
  ev{ev = "takeoff", x = arc.from.x, y = arc.from.y, distance = math.sqrt(dx * dx + dy * dy),
     land_tick = arc.land, peak = arc.peak}
  log(string.format("VIDEO takeoff #%d (%s) at %d: %.2f,%.2f -> %.2f,%.2f, land %d, peak %.2f",
      st.count.takeoff, label, tick, arc.from.x, arc.from.y, arc.to.x, arc.to.y, arc.land, arc.peak))
  M.flush_queue()                       -- the takeoff row, over the one try() just rolled
  M.observe()
  hide_texts()
  return true
end

---@param dir defines.direction?
local function hold(dir)
  local st = S()
  if dir then
    st.driver.walking_state = {walking = true, direction = dir}
  else
    st.driver.walking_state = {walking = false, direction = EAST}
  end
end

-- ---------------------------------------------------------------------------------------------
-- on_spidertron_replaced: the one place a body change is seen. Logs it and queues its row.

---@param event {tick: integer, old_spidertron: LuaEntity?, new_spidertron: LuaEntity?, jamaltron_reason: string?}
function M.on_replaced(event)
  local st = S()
  if not st or st.wrapped then return end
  local old, new, reason = event.old_spidertron, event.new_spidertron, event.jamaltron_reason
  if not (new and new.valid and old and old.valid and old == st.body) then return end
  st.body = new
  if reason == nil then return end
  if reason ~= "takeoff" then
    local x, y = xy(new.position)
    st.count[reason] = (st.count[reason] or 0) + 1
    st.last[reason] = event.tick
    if reason == "landing" or reason == "break" then
      ev{ev = reason, x = x, y = y}
      ev{ev = "thud", x = x, y = y}
      st.arc = nil
    else
      ev{ev = reason, x = x, y = y}
    end
    log(string.format("VIDEO %s #%d at %d: %.2f,%.2f", reason, st.count[reason], event.tick, x, y))
  end
  local item = {reason = reason, row = st.want[reason]}
  st.want[reason] = nil
  if reason == "landing" and st.heal then item.heal = true end
  if item.row or item.heal then st.queue[#st.queue + 1] = item end
end

-- ---------------------------------------------------------------------------------------------
-- Per-tick detectors: what the audio and the cut anchor on. Read in on_tick T, i.e. the state
-- the entity update of T-1 left (the frame of T shows the update of T), so EVERY change they see
-- happened at T-1 and is logged there: his speed crossing 0.01 (walk_start/stop), the ammo diff
-- (fire_start), the roboport's robot count (bot_out) and his health (repair_start/repairing/
-- repair_full). MEASURED on the first main take: his speed crossed 0.01 during update 1014 (line
-- 1015's x moved 0.012), frame 1014 is the first to show it, and walk_start said 1015 - every
-- sound on these events started one frame (16.7 ms) late. The journal's DELAY keeps back-dated
-- lines in order. The swap events (takeoff/landing/break/repair) and the apex are not these:
-- jamaltron's own handlers make them happen in the tick they are logged at.

---@param b LuaEntity
---@return number
local function ammo_total(b)
  local inv = b.get_inventory(defines.inventory.spider_ammo)
  if not inv then return 0 end
  local n = 0
  for i = 1, #inv do
    local stack = inv[i]
    if stack.valid_for_read then
      local mag = prototypes.item[stack.name].magazine_size or 1
      n = n + (stack.count - 1) * mag + stack.ammo
    end
  end
  return n
end

---A round spent at `tick` (the fired event, or an ammo drop seen a tick later).
---@param tick integer
local function spent(tick)
  local st = S()
  local f = st.fire
  if not f.on then
    f.on = true
    f.first = f.first or tick
    local x, y = xy(st.body.position)
    ev{tick = tick, ev = "fire_start", x = x, y = y}
    st.count.fire_start = (st.count.fire_start or 0) + 1
    log("VIDEO fire_start at " .. tick)
  end
  if not f.last or tick > f.last then f.last = tick end
end
M.spent = spent

---@param tick integer
local function detect(tick)
  local st = S()
  local b = st.body
  local was = tick - 1                  -- when what this tick reads happened (the header above)
  -- walking: his speed crossing 0.01 tiles/tick; a body that cannot walk reads 0
  local speed = (b.name == VEHICLE) and b.speed or 0
  if not st.walking and speed > 0.01 then
    st.walking = true
    local x, y = xy(b.position)
    ev{tick = was, ev = "walk_start", x = x, y = y}
  elseif st.walking and speed <= 0.01 then
    st.walking = false
    local x, y = xy(b.position)
    ev{tick = was, ev = "walk_stop", x = x, y = y}
  end
  -- firing: the ammo diff, and 10 ticks with none spent ends a run
  local ammo = ammo_total(b)
  if st.ammo and ammo < st.ammo - 1e-6 then spent(tick - 1) end
  st.ammo = ammo
  local f = st.fire
  if f.on and f.last and tick - f.last > 10 then
    f.on = false
    local x, y = xy(b.position)
    ev{tick = f.last + 1, ev = "fire_stop", x = x, y = y}
    log("VIDEO fire_stop at " .. (f.last + 1))
  end
  -- the roboport: a bot leaving is its robot count dropping
  local robo = st.roboport
  if robo and robo.valid then
    local inv = robo.get_inventory(defines.inventory.roboport_robot)
    local n = inv and inv.get_item_count() or 0
    if st.bots and n < st.bots then
      local bots = st.s.find_entities_filtered{type = "construction-robot", position = robo.position,
                                               radius = 4}
      local p = bots[1] and bots[1].position or robo.position
      for _ = 1, st.bots - n do ev{tick = was, ev = "bot_out", x = p.x, y = p.y} end
    end
    st.bots = n
  end
  -- the repair: his health rising on the beached body, every 30 ticks while it does
  local hp = st.hp
  if b.name == BEACHED and st.flags.cue then
    local h = b.health
    if hp.last and h > hp.last + 1e-3 then
      hp.rise = was
      if not hp.start then
        hp.start = was
        ev{tick = was, ev = "repair_start"}
        log("VIDEO repair_start at " .. was)
      end
      if not hp.beat or was - hp.beat >= 30 then
        hp.beat = was
        ev{tick = was, ev = "repairing"}
      end
    end
    if not hp.full and h >= b.max_health then
      hp.full = was
      ev{tick = was, ev = "repair_full"}
      log("VIDEO repair_full at " .. was)
    end
    hp.last = h
  end
  -- the arc's apex (and the lake jump's still)
  local arc = st.arc
  if arc and tick == arc.apex then
    local x, y = xy(b.position)
    ev{ev = "apex", x = x, y = y}
    if st.take == "main" and st.count.takeoff == 3 then st.stills[tick] = "lake-apex" end
  end
end

-- ---------------------------------------------------------------------------------------------
-- The wave.

---@param st Video.State
local function spawn_group(st)
  local m = set.MARKS
  st.groups = st.groups + 1
  for i, name in ipairs(M.WAVE) do
    local p = {x = m.spawn.x + (i % 3) * 1.5 + st.groups * 0.25, y = m.spawn.y + (i - 3) * 1.5}
    local e = st.s.create_entity{name = name, position = p, force = "enemy"}
    if e and e.unit_number and e.commandable then
      e.commandable.set_command{type = defines.command.attack, target = st.body,
                                distraction = defines.distraction.by_enemy}
      st.biters[e.unit_number] = e
      st.spawned = st.spawned + 1
      ev{ev = "biter_spawn", x = e.position.x, y = e.position.y, name = name}
    else
      M.fail("wave: could not spawn " .. name)
    end
  end
end

---Tiles out to which a player holding fire would be shooting: the gun's range + 1 (MEASURED D.7:
---he fires at 6/9/10 tiles, never 11/12). Past it a held `shooting_enemies` at a biter's position
---still starts a stream, landing at max range on empty grass (MEASURED here: fire_start 1 tick
---after the first group spawned 30 tiles out) - which no player defending would do.
---@return number
local function reach()
  local gun = prototypes.item["jamaltron-flamethrower"]
  local ap = gun and gun.attack_parameters
  return ((ap and ap.range) or 9) + 1
end

---What a player holding fire does, every tick: shoot at the nearest biter once one is in range.
---@param st Video.State
local function shoot(st)
  local nearest, best = nil, reach() ^ 2
  local p = st.body.position
  for _, e in pairs(st.biters) do
    if e.valid then
      local dx, dy = e.position.x - p.x, e.position.y - p.y
      local d = dx * dx + dy * dy
      if d < best then nearest, best = e, d end
    end
  end
  if nearest then
    st.driver.shooting_state = {state = defines.shooting.shooting_enemies, position = nearest.position}
  else
    st.driver.shooting_state = {state = defines.shooting.not_shooting, position = p}
  end
end

---@param event EventData.on_entity_died
function M.on_died(event)
  local st = S()
  if not (st and st.capturing) then return end
  local e = event.entity
  local unit = e.unit_number
  if not (unit and st.biters[unit]) then return end
  st.biters[unit] = nil
  ev{tick = event.tick, ev = "biter_died", x = e.position.x, y = e.position.y, name = e.name}
  if st.groups >= M.T.groups and next(st.biters) == nil then
    ev{tick = event.tick, ev = "wave_clear"}
    st.last.wave_clear = event.tick
    log("VIDEO wave_clear at " .. event.tick)
  end
end

---@param event EventData.on_entity_damaged
function M.on_damaged(event)
  local st = S()
  if not (st and st.capturing) or st.bitten then return end
  local cause = event.cause
  if cause and cause.valid and cause.type == "unit" then
    st.bitten = true
    local x, y = xy(event.entity.position)
    ev{tick = event.tick, ev = "biter_attack", x = x, y = y, name = cause.name}
    log("VIDEO biter_attack at " .. event.tick .. " by " .. cause.name)
  end
end

---@param event {tick: integer, source_entity: LuaEntity?}
function M.on_fired(event)
  local st = S()
  if st and st.capturing and event.source_entity == st.body then spent(event.tick) end
end

---@param event EventData.on_script_trigger_effect
function M.on_trigger(event)
  local st = S()
  if not (st and st.capturing) or event.effect_id ~= FOOTFALL then return end
  local p = event.target_position or (event.source_entity and event.source_entity.position)
  if p then ev{tick = event.tick, ev = "footfall", x = p.x, y = p.y} end
end

---@param event EventData.on_spider_command_completed
function M.on_command_completed(event)
  local st = S()
  if not st or event.vehicle ~= st.body or st.beat ~= "report" or st.last.command then return end
  st.last.command = event.tick
  M.force("command_done.02")
end

-- ---------------------------------------------------------------------------------------------
-- The main take's beats. enter(st, tick) runs once; step(st, tick) every tick after.

---@param name string
---@param tick integer
local function go(name, tick)
  beat(name, tick)
  local enter = M.ENTER[name]
  if enter then enter(S(), tick) end
end
M.go = go

---Since the beat began, did `what` happen, and when (the last time)?
---@param st Video.State
---@param what string
---@return integer?
local function since(st, what)
  local t = st.last[what]
  if t and t >= st.beat_at then return t end
  return nil
end

M.ENTER = {}
M.STEP = {}
local ENTER, STEP = M.ENTER, M.STEP

STEP.establish = function(st, tick)
  -- Written every tick while he walks: a scripted DRIVER's walking_state latches (MEASURED,
  -- E.2.2), an unseated character's is not measured.
  if tick - st.beat_at >= M.T.engineer_walk then hold(EAST) end
  if st.driver.position.x >= set.MARKS.A.x - 2 then go("board", tick) end
end

ENTER.board = function(st)
  st.body.set_driver(st.driver)
  hold(nil)                             -- seated, a latched walk would drive HIM
  if st.driver.vehicle ~= st.body then M.fail("board: the engineer is not in the seat") end
end
STEP.board = function(st, tick)
  if tick - st.beat_at >= M.T.board_hold then go("hop1", tick) end
end

ENTER.hop1 = function(st)
  st.want.takeoff, st.want.landing = "jump.01", "land.03"
  press("hop1")
end
STEP.hop1 = function(st, tick)
  local landed = since(st, "landing")
  if landed and tick >= landed + M.T.hop1_read then go("hop2", tick) end
end

ENTER.hop2 = function(st)
  st.want.landing = "land.06"
  press("hop2")
end
STEP.hop2 = function(st, tick)
  local landed = since(st, "landing")
  if landed and tick >= landed + M.T.hop2_read then go("wave", tick) end
end

ENTER.wave = function(st)
  st.s.peaceful_mode = false
  liberty("peaceful_mode off for the wave")
  spawn_group(st)
end
STEP.wave = function(st, tick)
  local rel = tick - st.beat_at
  if st.groups < M.T.groups and rel > 0 and rel % M.T.group_gap == 0 then spawn_group(st) end
  if not st.last.wave_clear then shoot(st) end
  local first = st.fire.first
  if first and not st.flags.attacking and tick >= first + M.T.attacking_after then
    st.flags.attacking = true
    M.force("attacking.01")
  end
  if first and tick == first + M.T.flame_still then st.stills[tick] = "flame" end
  local clear = st.last.wave_clear
  if clear and not st.flags.calm then
    st.flags.calm = true
    st.driver.shooting_state = {state = defines.shooting.not_shooting, position = st.body.position}
    st.s.peaceful_mode = true
    liberty("peaceful_mode back on after the wave")
  end
  if clear and tick >= clear + M.T.clear_hold then go("report", tick) end
end

ENTER.report = function(st)
  st.body.autopilot_destination = set.MARKS.E
end
STEP.report = function(st, tick)
  local done = st.last.command
  if done and not st.walking and tick >= done + M.T.report_read then go("lake_jump", tick) end
end

ENTER.lake_jump = function(st)
  setting("jamaltron-jump-distance", 20, "the biggest jump the setting allows, over the lake")
  setting("jamaltron-leg-break-percent", 100, "the break is the beat")
  st.want.takeoff, st.want["break"] = "jump.05", "legs_break.01"
  hold(EAST)
  press("lake")
end
STEP.lake_jump = function(st, tick)
  if since(st, "break") then go("beached", tick) end
end

ENTER.beached = function(st, tick)
  hold(nil)
  setting("jamaltron-leg-break-percent", 0, "one break a take")
  setting("jamaltron-jump-distance", 8, "back to the default between the lake jumps")
  st.flags.break_at = tick
end
STEP.beached = function(st, tick)
  local rel = tick - (st.flags.break_at --[[@as integer]])
  if rel == M.T.beached_still then st.stills[tick] = "beached" end
  if rel >= M.T.flop1 then go("apology", tick) end
end

ENTER.apology = function()
  M.force("flopping.12")
end
STEP.apology = function(st, tick)
  local rel = tick - (st.flags.break_at --[[@as integer]])
  if rel == M.T.flop2 then M.force("flopping.02") end
  if rel >= M.T.cue then go("repair", tick) end
end

ENTER.repair = function(st)
  local robo = st.roboport
  if not (robo and robo.valid) then return M.fail("repair: no roboport") end
  local mat = robo.get_inventory(defines.inventory.roboport_material)
  local n = mat and mat.insert{name = "repair-pack", count = 5} or 0
  if n < 5 then return M.fail("repair: only " .. n .. " packs went into the roboport") end
  st.flags.cue = true
  st.hp.last = st.body.health
  ev{ev = "repair_cue"}
  st.want.repair = "repaired.07"
end
STEP.repair = function(st, tick)
  if since(st, "repair") then go("stand", tick) end
end

STEP.stand = function(st, tick)
  local rel = tick - st.beat_at
  if rel == M.T.stand_still then st.stills[tick] = "stand" end
  if rel >= M.T.stand_hold then go("encore", tick) end
end

---Ticks before the encore's press the camera starts out to the lake frame: MEASURED on the
---first take, easing out only from the press left the takeoff at the stand's zoom 2.
M.T.encore_lead = 90

ENTER.encore = function(st)
  setting("jamaltron-jump-distance", 20, "the encore, back over the same lake")
  st.want.takeoff = "jump.13"
  hold(WEST)
  press("encore")
  st.flags.release = game.tick + 1      -- let go mid-arc: he lands standing
end
STEP.encore = function(st, tick)
  if st.flags.release == tick then hold(nil) end
  local landed = since(st, "landing")
  if landed and tick >= landed + M.T.wrap_after then go("wrap", tick) end
end

-- The loop take (the README GIF + portal loop): A -> B -> A over the creek, twice, fixed camera,
-- water pinned. THE SEAM IS THE LANDING AT A: `loop` begins on the tick he lands back at A and
-- `wrap` on the next such tick, so the cut's [beat:loop, beat:wrap) ends one frame before the
-- picture it began on. MEASURED (two loop takes, 182- and 240-tick cycles): the two landing
-- frames differ by 0.075 mean abs (0-255) - under the 0.02-0.16 a settled Jamal moves tick to
-- tick - because a fresh body's legs spawn in one fixed pose; from +20 on the two re-lays drift
-- apart (0.52 at +20, 0.60 at +60, identically at both cycle lengths, so not tick phase), which
-- is why the contract's first cut point, +60, would twitch every leg at the seam.

---@param st Video.State
---@param dir defines.direction
---@param label string
local function hop(st, dir, label)
  hold(dir)
  press(label)
  st.flags.release = game.tick + 1
end

---The shared loop step: press east `first_hold` into the beat, press west settle+1 after the
---landing at B, and end the beat ON the landing back at A (seen the tick it happens: jamaltron's
---on_tick lands him before this one runs).
---@param st Video.State
---@param tick integer
---@param next_beat string
local function loop_step(st, tick, next_beat)
  if st.flags.release == tick then hold(nil) end
  local landed = since(st, "landing")
  local n = st.flags.hops --[[@as integer]]
  local pressed = st.flags.pressed --[[@as integer]]
  if n == 0 and tick - st.beat_at >= (st.flags.first_hold or 0) then
    st.flags.hops, st.flags.pressed = 1, tick
    hop(st, EAST, st.beat .. " east")
  elseif n == 1 and landed and landed > pressed and tick == landed + M.T.loop_settle + 1 then
    st.flags.hops, st.flags.pressed = 2, tick
    hop(st, WEST, st.beat .. " west")
  elseif n == 2 and landed and landed > pressed then
    go(next_beat, tick)
  end
end

ENTER.loop_pre = function(st)
  st.flags.hops, st.flags.pressed, st.flags.first_hold = 0, 0, M.T.loop_pre_hold
end
STEP.loop_pre = function(st, tick) loop_step(st, tick, "loop") end

ENTER.loop = function(st, tick)
  st.flags.hops, st.flags.pressed, st.flags.first_hold = 0, tick, M.T.loop_settle + 1
end
STEP.loop = function(st, tick) loop_step(st, tick, "wrap") end

-- ---------------------------------------------------------------------------------------------
-- The camera, per beat (the contract's "Camera" paragraph). Each aim names its SHOT: a new name
-- eases in (camera.lua), the break's crash zoom is the one abrupt move. hop1's arc also holds x:
-- main.toml plays it at 1/3, and a follow under a slow-mo steps the whole picture every third
-- frame (camera.lua LOCKS) - so the camera waits on the board shot, still, while he flies out of
-- its centre (he lands 6 tiles right of it, ~380 px at zoom 2) and eases after him on landing.

---The lake frame: both banks, the whole d=20 arc (its 7.5-tile peak draws 5.3 tiles up-screen
---over the 1.5 standing lift).
local LAKE_FRAME = {x = set.MARKS.E.x + 10, y = set.MARKS.E.y - 3}

---@param st Video.State
local function direct(st)
  local cam, b = st.cam, st.body
  local p = b.position
  local now = st.beat
  if st.take == "loop" then return end                       -- fixed on the creek
  if now == "establish" or now == "board" then
    camera.aim(cam, set.MARKS.A.x + 2, set.MARKS.A.y - 1.5, 2.0, nil, nil, "establish")
  elseif now == "hop1" or now == "hop2" then
    camera.aim(cam, p.x + 1, p.y - 1.5, 2.0, nil, nil, now)
  elseif now == "wave" then
    camera.aim(cam, set.MARKS.C.x + 6, set.MARKS.C.y - 5.5, 1.1, 0.05, 0.04, "wave")
  elseif now == "report" or now == "lake_jump" then
    camera.aim(cam, LAKE_FRAME.x, LAKE_FRAME.y, 1.2, 0.04, 0.04, "lake")
  elseif now == "beached" or now == "apology" then
    -- On the flop sheet's own centre (the beached body has no lift; its art is drawn off a shift):
    -- the crash zoom, then a slow push in through the apologies.
    local fs = flop.sprites.body.shift
    if now == "beached" then
      camera.aim(cam, p.x + fs[1], p.y + fs[2], 2.2, 0.2, 0.2, "crash", true)
    else
      camera.aim(cam, p.x + fs[1], p.y + fs[2], 2.4, 0.1, 0.002, "apology")
    end
  elseif now == "repair" then
    local r = st.roboport and st.roboport.valid and st.roboport.position or p
    camera.aim(cam, (p.x + r.x) / 2, (p.y + r.y) / 2 - 0.5, 1.6, 0.05, 0.04, "repair")
  elseif now == "stand" and game.tick - st.beat_at >= M.T.stand_hold - M.T.encore_lead then
    camera.aim(cam, LAKE_FRAME.x, LAKE_FRAME.y, 1.2, 0.06, 0.06, "encore")
  elseif now == "stand" then
    camera.aim(cam, p.x, p.y - 1.5, 2.0, 0.08, 0.06, "stand")
  elseif now == "encore" or now == "wrap" then
    -- the same shot as the pull-out that leads into it: no second ease-in at the press
    camera.aim(cam, LAKE_FRAME.x, LAKE_FRAME.y, 1.2, 0.08, 0.08, "encore")
  end
  camera.lock(cam, b.name == AIRBORNE, now == "hop1")
end

-- ---------------------------------------------------------------------------------------------
-- Staging and the tick.

---@param cfg table take.lua
---@param tick integer
function M.stage(cfg, tick)
  local s = game.surfaces[1]
  storage.video = {
    take = cfg.take, cfg = cfg, s = s, staged = tick, capturing = false, wrapped = false,
    beat_at = tick, seen = {}, queue = {}, want = {}, heal = true, count = {takeoff = 0},
    last = {}, walking = false, fire = {on = false}, biters = {}, spawned = 0, groups = 0,
    hp = {}, bitten = false, hidden = 0, stills = {}, flags = {},
    water_tick = cfg.take == "loop" and 0 or nil,
  }
  local st = S()
  journal.open(cfg.dir)
  -- --benchmark-graphics has a local player, and freeplay gave it a character: out of the set.
  for _, player in pairs(game.players) do
    if player.character then player.character.destroy() end
  end
  local built = set.build(s)
  st.roboport = built.roboport
  if not set.check(s, built) then M.fail("the set does not measure up (see VIDEO set)") end

  local m = set.MARKS
  local b = s.create_entity{name = VEHICLE, position = m.A, force = "player"}
  if not b then return M.fail("stage: no jamaltron") end
  b.color = ORANGE
  b.torso_orientation = cfg.take == "loop" and 0.75 or 0.25
  local ammo = b.get_inventory(defines.inventory.spider_ammo)
  if ammo then
    for i = 1, #ammo do ammo[i].set_stack{name = "flamethrower-ammo", count = 20} end
  end
  st.body = b
  local at = cfg.take == "loop" and {x = m.A.x, y = m.A.y + 2} or m.engineer
  local c = s.create_entity{name = "character", position = at, force = "player"}
  if not c then return M.fail("stage: no engineer") end
  st.driver = c
  if cfg.take == "loop" then b.set_driver(c) end

  remote.call("jamaltron", "debug", true)          -- `jamaltron speech <unit> <row>` in the log
  setting("jamaltron-speech-cooldown", 300, "the quiet director: no ambient line all take")
  setting("jamaltron-leg-break-percent", 0, "the hops land clean (default 25%)")
  setting("jamaltron-jump-distance", 8, "the default, pinned")

  local cx, cy, z
  if cfg.take == "loop" then
    cx, cy, z = m.creek_centre.x, m.creek_centre.y - 1.5, 1.5
  else
    cx, cy, z = m.A.x + 2, m.A.y - 1.5, 2.0
  end
  st.cam = camera.new(cx, cy, z)
  st.ammo = ammo_total(b)
  log(string.format("VIDEO staged %s at tick %d, %d player(s), capture %s", cfg.take, tick,
      #game.players, tostring(cfg.capture)))
end

---@param tick integer
function M.tick(tick)
  local st = S()
  local cfg = st.cfg
  if st.wrapped then return end                 -- the take is over: nothing more is logged
  if not (st.body and st.body.valid) then
    if not st.flags.lost then st.flags.lost = true; M.fail("no body at " .. tick) end
    return
  end
  M.flush_queue()
  M.observe()
  if not st.capturing and not st.wrapped and tick >= st.staged + M.T.settle then
    st.capturing = true
    st.capture_start = tick
    ev{ev = "capture_start"}
    log("VIDEO capture_start at " .. tick)
    go(st.take == "loop" and "loop_pre" or "establish", tick)
  end
  if st.capturing then
    detect(tick)
    local step = STEP[st.beat]
    if step then step(st, tick) end
    local max = M.MAX[st.beat]
    if max and tick - st.beat_at > max then
      M.fail("beat " .. st.beat .. " ran " .. (tick - st.beat_at) .. " ticks (max " .. max .. ")")
    end
    if tick > st.staged + M.T.limit and st.beat ~= "wrap" then
      M.fail("no wrap by tick " .. tick)
    end
    -- A failed take WRAPS on the tick it failed, whatever failed it (a refused press, a force,
    -- a beat over its limit, an unhidable text): it is judged failed anyway, and a graphics run
    -- left to the benchmark's end would shoot ~4450 more frames (~3.7 GB, MEASURED 0.83 MB a
    -- frame) of a machine stuck in its beat. The first cut kept the per-beat limits only while
    -- nothing had failed yet, so a refused hop1 press waited for staging + 9000.
    if st.flags.failed and st.beat ~= "wrap" then
      go("wrap", tick)
    end
  end
  hide_texts()
  if st.capturing then
    direct(st)
    camera.step(st.cam)
    local x, y, z = camera.snapped(st.cam)
    local b = st.body
    local l, sprite = lift()
    local water = st.water_tick or tick
    if cfg.capture then camera.shoot(cfg, st.s, st.cam, tick, water) end
    journal.track{tick = tick, cam = {x, y}, zoom = z, body = b.name, pos = {b.position.x, b.position.y},
                  lift = l, sprite = sprite}
    local still = st.stills[tick]
    if still then
      -- On his drawn body: the torso standing or in the air, the flop sheet's own centre beached.
      local off = b.name == BEACHED and flop.sprites.body.shift or l
      local c = {x = b.position.x + off[1], y = b.position.y + off[2]}
      local detail = ""
      if cfg.capture and cfg.stills then
        local at, sz, nudge = camera.still(cfg, st.s, st.cam, still, c, water)
        detail = string.format(": zoom %.2f at %.2f,%.2f, nudged %d px off the stamp", sz, at.x, at.y,
                               nudge)
      end
      ev{ev = "still", name = still}
      log("VIDEO still " .. still .. " at " .. tick .. detail)
    end
    if st.beat == "wrap" then
      st.capturing, st.wrapped = false, true
      st.capture_end = tick
      ev{ev = "capture_end"}
      if cfg.capture then game.set_wait_for_screenshots_to_finish() end
      journal.close()
      log(string.format("VIDEO capture_end at %d: %d ticks captured, %d texts hidden", tick,
          tick - st.capture_start + 1, st.hidden))
      log("VIDEO wrap")
      return
    end
  end
  journal.flush(tick - journal.DELAY)
end

---The nth-tick pass: the stand-up (breakage.poll) and chain punchlines (deliver_due) happen on
---jamaltron's 15/60-tick clock, after every on_tick.
function M.nth()
  local st = S()
  if not (st and st.capturing and st.body and st.body.valid) then return end
  M.flush_queue()
  M.observe()
  hide_texts()
  -- The stand-up is this tick's: the beat starts on it, not on the next on_tick.
  if st.beat == "repair" and since(st, "repair") then go("stand", game.tick) end
end

return M
