-- E.2.4's engine lanes: the shore stall (PLAN E.2.2) on hand-built terrain, judged by what
-- the REAL speech.poll says - control.lua's 1 Hz clock, say(), the latch, R5, the hush.
-- control.lua calls `register` once and `tick` every tick.
--
-- Each lane is a strip of set_tiles terrain in a band far south of control.lua's spawns, 60
-- tiles tall unless it says otherwise (the wiring probe's 25-tall strips let his legs reach
-- natural ground past the edge, and he walked off). Its jamaltron is spawned WITHOUT
-- raise_built (a built line's chain would stand in front of the shore line, R5) and gets its
-- speech record from say("land", "broke"), which R4 turns down before a word is said. A
-- driven lane's character writes walking_state EVERY tick it holds and walking = false once
-- to let go: a scripted driver's state latches (measured).
--
-- What he said is read off the harness `state` every tick: a new utterance moves last_tick, a
-- chain's follow-up changes last_id and not last_tick, so every count below is utterances and
-- shore.05 -> shore.06 is ONE line. The need/never lines back the counts with speech debug's
-- log. Nothing is logged per poll, so the log stays readable.

local lines = require("__jamaltron__/scripts/lines")

local M = {}

local SAY, HARNESS = "jamaltron", "jamaltron-harness"
local LAND = "grass-1"
local E, NE = defines.direction.east, defines.direction.northeast

---The band's top edge: 2000 tiles south of control.lua's spawns round y = 0.
local Y0 = 2000
---Columns every lane builds: a run-up west of the shoreline at x = 40, room past a far bank.
local XMIN, XMAX = -24, 128
---Ticks (dt) the lanes spawn on - dt 0 builds them - and are judged on, before control.lua's
---`HARNESS done` at 3700.
local SPAWN, JUDGE = 2, 3600
---Ticks from the torso crossing the shoreline to the line: measured 115-183, so 5 s is slack
---for a poll lost to an approach `moving` chain (R5), not room for a slow detector.
local LATENCY = 5 * 60
---The detector's gap between episodes (stall.lua M.GAP), restated so a retune shows here.
local GAP = 30 * 60

---Unit heading per driven direction: stall.lua's own values, for the foot lead below.
local HEADING = {[E] = {1, 0}, [NE] = {0.70710678118654757, -0.70710678118654757}}

---The straight lanes' shoreline: their water starts at column 40, whatever the row.
---@param x number
---@param _ number
---@return boolean
local function at_40(x, _)
  return x >= 40
end

---Every row of the lane `tile` from column `from` up to `to`.
---@param tile string
---@param from integer
---@param to integer
---@return fun(x: integer, dy: integer): string?
local function band(tile, from, to)
  return function(x, _)
    if x >= from and x < to then return tile end
  end
end
local LAKE = band("deepwater", 40, 80)

---@param id string
---@return string
local function pool_of(id)
  return (id:match("^(.-)%.%d+$"))
end

---Every row's sub and channel, by id.
local SUB, CH = {}, {}
for _, pool in pairs(lines.pools) do
  for _, row in ipairs(pool.rows) do
    SUB[row.id], CH[row.id] = row.sub, row.ch
  end
end

---Utterances (chain follow-ups left out) of pool `name`, or of any pool when nil, said in
---[from, to].
---@param r table a lane's run record
---@param name string?
---@param from integer?
---@param to integer?
---@return table[]
local function heads(r, name, from, to)
  local out = {}
  for _, x in ipairs(r.said) do
    if not x.tail and (name == nil or pool_of(x.id) == name)
        and x.tick >= (from or 0) and x.tick <= (to or math.huge) then
      out[#out + 1] = x
    end
  end
  return out
end

---What a lane said, for a detail or the log: `+` marks a chain's follow-up, and a driven
---shore line carries the foot lead it fired on (+ = a foot ahead: the 4-poll fallback).
---@param r table
---@return string
local function show(r)
  local out = {}
  for _, x in ipairs(r.said) do
    local lead = x.front and pool_of(x.id) == "shore" and string.format("/%+.2f", x.front) or ""
    out[#out + 1] = (x.tail and "+" or "") .. x.id .. "@" .. x.tick .. lead
  end
  local p = r.e.valid and r.e.position
  return "said=" .. (#out > 0 and table.concat(out, ",") or "nothing") .. " contact="
         .. tostring(r.contact) .. (p and string.format(" at=%.2f,%.2f", p.x, p.y - r.oy) or "")
end

---A lane that must never speak must never latch either: a silent episode is R6 muting
---`moving` and `idle` at a shark who is not stuck.
---@param r table
---@return boolean
local function silent(r)
  return #heads(r, "shore") == 0 and not r.opened and r.st.stall_tick == nil
end

---A river straddles the PHYSICS, not the detector: over 75 lanes each, 15 wide crossed 73 and
---16 wide stopped 71 (measured; the PLAN's 11/11 each way was a small sample). So it is judged
---on what he did (across: no line, no latch; stopped at the near bank: one line), and its
---need/never line is logged here once that is known.
---@param r table
---@param check fun(name: string, ok: boolean, detail: string?)
---@param _ table
---@param lane table
local function river(r, check, _, lane)
  local width = lane.far - 40
  local unit = "jamaltron speech " .. r.e.unit_number .. " shore[.]"
  if r.e.position.x > lane.far then
    log("HARNESS never " .. unit)
    check("shore: deep water " .. width .. " wide, straddled this run: no line, no latch",
          silent(r), show(r))
  else
    log("HARNESS need " .. unit)
    check("shore: deep water " .. width .. " wide, stopped at the bank this run: one line",
          #heads(r, "shore") == 1 and r.e.position.x < 42, show(r))
  end
end

---The lanes. `tile(x, dy)` names the tile at column x, dy rows off the lane's centre (nil
---is land); `at` is the spawn {x, dy}, {28, 0} by default; `drive` is held from spawn to the
---end unless `hold` ({from, to} ticks after spawn) or `past` (let go once east of that x)
---says otherwise; `shore(x, dy)` is true once the torso has crossed the shoreline; `lines`
---is how many shore utterances the log must show (0 = never one; nil = the judge decides);
---`judge` asserts the rest.
local LANES = {
  {key = "lake", tile = LAKE, drive = E, lines = 1,
   judge = function(r, check)
     local line = heads(r, "shore")[1]
     check("shore: a driven lake says one line within 5 s of the shoreline",
           line and r.contact and line.tick > r.contact and line.tick - r.contact <= LATENCY,
           show(r))
     check("shore: ... then nothing for 30 s, `moving` included, and one line all run",
           line and #heads(r, nil, line.tick + 1, line.tick + GAP) == 0
           and #heads(r, "shore") == 1, show(r))
     check("shore: ... latched on that line, and still holding him",
           line and r.st.stall_tick == line.tick and r.st.holding, serpent.line(r.st))
   end},
  {key = "lava", tile = band("lava", 40, 80), drive = E, lines = 1,
   judge = function(r, check)
     local all = heads(r, "shore")
     local sub = all[1] and SUB[all[1].id]
     check("shore: lava says one line, from a lava or an any row",
           #all == 1 and (sub == "lava" or sub == "any"), show(r) .. " sub=" .. tostring(sub))
   end},
  {key = "shallow", tile = band("water-shallow", 40, 70), drive = E, past = 90, lines = 0,
   judge = function(r, check)
     check("shore: water-shallow is walked - no line, no latch, he ends past the far bank",
           silent(r) and r.e.position.x > 70, show(r))
   end},
  {key = "oil", tile = band("oil-ocean-deep", 40, 70), drive = E, past = 90, lines = 0,
   judge = function(r, check)
     check("shore: oil-ocean-deep is walked - no line, no latch, he ends past the far bank",
           silent(r) and r.e.position.x > 70, show(r))
   end},
  {key = "river15", tile = band("deepwater", 40, 55), drive = E, past = 75, far = 55,
   judge = river},
  {key = "river16", tile = band("deepwater", 40, 56), drive = E, past = 76, far = 56,
   judge = river},
  -- Narrow V-inlets (the refutation spike's inletnar, and one twice as narrow): he straddles
  -- the mouth and USUALLY rests with a foot ahead of the torso, where the head-on test cannot
  -- pass and only the 4-poll fallback speaks (pull the fallback and both go silent,
  -- mutant-checked). WHICH test fires is chaotic, so the check is the count: feet ahead at the
  -- line in 58 of 58 lanes and 36 of 40, yet both head-on in one run of a build that only
  -- moved other lines around (measured). SHORE end logs the lead: + is the fallback.
  {key = "inlet", drive = E, at = {12.5, 2.5}, lines = 1,
   tile = function(x, dy)
     if x >= 40 + 2 * math.abs(dy) and x < XMAX then return "deepwater" end
   end,
   judge = function(r, check, run)
     check("shore: two V-inlets he straddles say one line each",
           #heads(r, "shore") == 1 and #heads(run.inlet4, "shore") == 1,
           show(r) .. " / " .. show(run.inlet4))
   end},
  {key = "inlet4", drive = E, at = {12.5, 2.5}, lines = 1,
   tile = function(x, dy)
     if x >= 40 + 4 * math.abs(dy) and x < XMAX then return "deepwater" end
   end,
   judge = function() end},             -- judged with `inlet`
  {key = "corner", h = 140, drive = NE, at = {28, 10}, lines = 1,
   tile = function(x, dy)
     if (x >= 40 and x < 90 and dy >= -60) or (dy < -20 and dy >= -60 and x < 90) then
       return "deepwater"
     end
   end,
   shore = function(x, dy) return x >= 40 or dy < -20 end,
   judge = function(r, check)
     check("shore: driven into an inside corner, one line", #heads(r, "shore") == 1, show(r))
   end},
  {key = "stair", h = 160, drive = NE, lines = 1,
   tile = function(x, dy)
     if x - dy >= 40 and x - dy < 110 then return "deepwater" end
   end,
   shore = function(x, dy) return x - dy >= 40 end,
   judge = function(r, check)
     check("shore: square-on into a 45-degree staircase shore, one line",
           #heads(r, "shore") == 1, show(r))
   end},
  {key = "auto", tile = LAKE, dest = {55, 0}, lines = 1, never = "idle[.]",
   judge = function(r, check)
     local st = r.st
     check("shore: autopilot into a lake, nobody aboard: one line, then no idle while stuck",
           #heads(r, "shore") == 1 and #heads(r, "idle") == 0 and st.holding
           and st.idle_at > game.tick and r.e.autopilot_destination ~= nil,
           show(r) .. " " .. serpent.line(st))
   end},
  -- Parked on dry land 17 from its target, feet ahead (+3.1, measured): the detector's own
  -- foot and ground tests keep this one quiet with or without the follow guards.
  {key = "follow", follow = {24, 0}, lines = 0,
   judge = function(r, check)
     check("shore: a follower parked 20 out from a stationary target never speaks or latches",
           silent(r) and r.e.autopilot_destination ~= nil, show(r))
   end},
  -- The target stands on the shore and the slot is 18 tiles out in the lake: he stops with
  -- his torso over the water, pushing at a slot he cannot reach - a stall in every respect
  -- but the one the target guard reads. His retry lurches (0.5-0.65 tiles) said `moving` in
  -- 7 of 16 runs before stall.pushed (measured); the approach may, 5 s past the shore may not.
  {key = "follow_shore", tile = LAKE, follow = {38, 0}, at = {20, 0}, lines = 0,
   judge = function(r, check)
     local p = r.e.position
     local under = r.e.surface.get_tile(p.x, p.y).name
     check("shore: ... nor one stuck at the shore beside a target whose slot is in the lake",
           silent(r) and under == "deepwater" and r.e.autopilot_destination ~= nil,
           show(r) .. " under=" .. under)
     check("shore: ... and its lurches there say no `moving`",
           r.contact and #heads(r, "moving", r.contact + LATENCY) == 0, show(r))
   end},
  {key = "chain", tile = LAKE, drive = E, lines = 1,
   -- idle.08 about a second before the stall is due (the 240 poll: contact 72-76, measured)
   -- and idle.09 150 ticks behind it. On a tick 15 past a poll, so neither the force nor the
   -- follow-up (45 past) shares a tick with a poll and the order is never a coin toss.
   on_tick = function(r, tick)
     if r.contact and not r.forced and tick >= r.contact + 100 and tick % 60 == 15 then
       r.forced = tick
       remote.call(HARNESS, "force", r.e, "idle.08")
     end
   end,
   judge = function(r, check, run)
     local tail, line = nil, heads(r, "shore")[1]
     for _, x in ipairs(r.said) do
       if x.id == "idle.09" then tail = x end
     end
     check("shore: a chain in flight at the shore - the shore line lands after its idle.09",
           tail and line and line.tick > tail.tick and #heads(r, "shore") == 1,
           show(r) .. " forced=" .. tostring(r.forced))
     -- The same lake under the hush spoke well before idle.09 landed here, so R5 held this
     -- line; it was not late on its own. The hush lane is the reference because nothing can
     -- stand in front of its line: `moving` has no narration row, so no approach chain
     -- (moving.10's would).
     local ref = run.hush
     local ref_line = heads(ref, "shore")[1]
     check("shore: ... and the stall was due while the chain was pending",
           tail and ref_line and ref.contact and r.contact
           and ref_line.tick - ref.contact < tail.tick - r.contact,
           "hush " .. show(ref) .. " / chain " .. show(r))
   end},
  {key = "hush", tile = LAKE, drive = E, lines = 1,
   on_spawn = function(r)
     r.hushed = game.tick
     remote.call(HARNESS, "force", r.e, "low_health.01")
   end,
   judge = function(r, check)
     local line = heads(r, "shore")[1]
     check("shore: under low_health.01's hush the shore line is narration",
           line and CH[line.id] == "narration" and line.note == true and line.bubble == nil
           and line.tick < r.hushed + 15 * 60, show(r))
   end},
  -- Held 10 s, let go 12 s - the episode ends 10 s after the last push - and pressed again
  -- for good at 22 s, back into the same lake INSIDE the gap: stuck, silent, until the poll
  -- the gap runs out, and that poll speaks (the counter kept running through the gap).
  {key = "repress", tile = LAKE, drive = E, hold = {{0, 600}, {1320, math.huge}}, lines = 2,
   judge = function(r, check)
     local all = heads(r, "shore")
     local wait = all[2] and all[2].tick - all[1].tick
     check("shore: held, let go, pressed again inside the gap: a second episode, on the poll "
           .. "the 30 s gap runs out", #all == 2 and wait >= GAP and wait < GAP + 60
           and r.st.stall_tick == all[2].tick, show(r) .. " " .. serpent.line(r.st))
   end},
}

local Y1 = Y0
for _, lane in ipairs(LANES) do
  lane.h = lane.h or 60
  lane.oy = Y1 + lane.h / 2
  Y1 = Y1 + lane.h
end

---Generate the band, clear it and lay every lane's tiles. Peaceful, and the band's biters
---gone: something killed a spawn in the stall probe's first run, and a `damaged` line is not
---a shore line.
local function build()
  local surface = game.surfaces[1]
  for x = XMIN - 32, XMAX + 32, 32 do
    for y = Y0 - 32, Y1 + 32, 32 do
      surface.request_to_generate_chunks({x, y}, 0)
    end
  end
  surface.force_generate_chunk_requests()
  surface.peaceful_mode = true
  local margin = 192
  for _, e in pairs(surface.find_entities_filtered{
      area = {{XMIN - margin, Y0 - margin}, {XMAX + margin, Y1 + margin}}, force = "enemy"}) do
    e.destroy()
  end
  local area = {{XMIN, Y0}, {XMAX, Y1}}
  for _, e in pairs(surface.find_entities_filtered{area = area}) do
    if e.valid then e.destroy() end
  end
  surface.destroy_decoratives{area = area}
  local tiles = {}
  for _, lane in ipairs(LANES) do
    for y = lane.oy - lane.h / 2, lane.oy + lane.h / 2 - 1 do
      for x = XMIN, XMAX - 1 do
        tiles[#tiles + 1] = {name = lane.tile and lane.tile(x, y - lane.oy) or LAND,
                             position = {x, y}}
      end
    end
  end
  surface.set_tiles(tiles, false, true, true)
end

---Spawn every lane's jamaltron with its driver or follow target, and log what the run must
---and must never show.
local function spawn()
  local surface = game.surfaces[1]
  local run = {}
  storage.shore = run
  for _, lane in ipairs(LANES) do
    local at = lane.at or {28, 0}
    local e = surface.create_entity{name = "jamaltron", position = {at[1], lane.oy + at[2]},
                                    force = "player"}
    assert(e, "no jamaltron for lane " .. lane.key)
    local r = {e = e, said = {}, oy = lane.oy}
    run[lane.key] = r
    remote.call(SAY, "say", e, "land", "broke")        -- a record, not a word: R4
    if lane.drive then
      r.ch = surface.create_entity{name = "character", position = {at[1] - 3, lane.oy + at[2]},
                                   force = "player"}
      e.set_driver(r.ch)
    end
    if lane.dest then
      e.autopilot_destination = {lane.dest[1], lane.oy + lane.dest[2]}
    end
    if lane.follow then
      r.target = surface.create_entity{name = "character", force = "player",
                                       position = {lane.follow[1], lane.oy + lane.follow[2]}}
      e.follow_target = r.target
      e.follow_offset = {20, 0}              -- after the target: setting one randomises it
    end
    if lane.on_spawn then lane.on_spawn(r) end
    local unit = "jamaltron speech " .. e.unit_number .. " "
    if lane.lines then
      log((lane.lines > 0 and "HARNESS need " or "HARNESS never ") .. unit .. "shore[.]")
    end
    if lane.never then
      log("HARNESS never " .. unit .. lane.never)
    end
    log("SHORE lane " .. lane.key .. " unit " .. e.unit_number)
  end
end

---Record anything new he said since the last look, and whether an episode is open.
---@param r table
---@param tick integer
local function watch(r, tick)
  local st = remote.call(HARNESS, "state", r.e)
  if st == nil then return end
  r.st = st
  if st.stall_open and not r.opened then r.opened = tick end
  if st.last_id == nil then return end
  if st.last_tick ~= r.lt then
    r.lt, r.lid = st.last_tick, st.last_id
    r.said[#r.said + 1] = {tick = st.last_tick, id = st.last_id, note = st.note,
                           bubble = st.bubble,
                           front = r.front_at == st.last_tick and r.front or nil}
  elseif st.last_id ~= r.lid then
    r.lid = st.last_id
    r.said[#r.said + 1] = {tick = tick, id = st.last_id, tail = true}
  end
end

---The frontmost foot's lead over the torso along `v`, as stall.lua measures it: under 0 is
---the head-on stall shape, 0 or more means only the 4-poll fallback can have fired.
---@param e LuaEntity
---@param v number[]
---@return number
local function front(e, v)
  local p, best = e.position, -math.huge
  for _, leg in pairs(e.get_spider_legs()) do
    local q = leg.position
    best = math.max(best, (q.x - p.x) * v[1] + (q.y - p.y) * v[2])
  end
  return best
end

---@param lane table
---@param r table
---@param rel integer ticks since spawn
---@return boolean
local function pressed(lane, r, rel)
  if lane.hold then
    for _, span in ipairs(lane.hold) do
      if rel >= span[1] and rel < span[2] then return true end
    end
    return false
  end
  if lane.past and (r.gone or r.e.position.x > lane.past) then
    r.gone = true
    return false
  end
  return true
end

---Drive, time and watch every lane for one tick. This handler runs before the mod's
---on_nth_tick ones (measured: a follow-up delivered on tick T is seen here on T + 1), so the
---foot lead taken on a poll tick is the one that poll reads.
---@param dt integer
function M.tick(dt)
  local run = storage.shore
  if run == nil or dt < SPAWN or dt > JUDGE then return end
  local rel, tick = dt - SPAWN, game.tick
  for _, lane in ipairs(LANES) do
    local r = run[lane.key]
    local e = r.e
    if e.valid then
      if r.ch and r.ch.valid then
        if pressed(lane, r, rel) then
          r.ch.walking_state = {walking = true, direction = lane.drive}
          r.down = true
        elseif r.down then
          r.ch.walking_state = {walking = false, direction = lane.drive}
          r.down = false
        end
      end
      local p = e.position
      if r.contact == nil and (lane.shore or at_40)(p.x, p.y - r.oy) then
        r.contact = tick
      end
      if lane.drive and tick % 60 == 0 then
        r.front, r.front_at = front(e, HEADING[lane.drive]), tick
      end
      watch(r, tick)
      if lane.on_tick then lane.on_tick(r, tick) end
    end
  end
end

---Add the lanes' build, spawn and judging to control.lua's steps.
---@param at fun(dt: integer, fn: fun(s: table))
---@param check fun(name: string, ok: boolean, detail: string?)
function M.register(at, check)
  at(0, build)
  at(SPAWN, spawn)
  at(JUDGE, function()
    local run = storage.shore
    for _, lane in ipairs(LANES) do
      local r = run[lane.key]
      if r.e.valid and r.st then
        local ok, err = pcall(lane.judge, r, check, run, lane)
        if not ok then check("shore lane " .. lane.key .. " judged", false, err) end
      else
        check("shore lane " .. lane.key .. " kept its jamaltron", false, show(r))
      end
      log("SHORE end " .. lane.key .. " " .. show(r))
    end
  end)
end

return M
