-- The shore stall WIRED (PLAN E.2.2): the real scripts/speech.lua - poll, say, transfer - over
-- the real detector, ground table, picker and generated catalog, with FAKE entities and a fake
-- game. test_stall.lua proves the detector alone; this proves what speech.lua does with it.
--
--   lua tools/tests/lua/test_speech_wiring.lua <repo root>
--
-- Run by tools/tests/test_speech_lua.py, in test_pick.lua's harness shape; Lua 5.2 / 5.4+ / luajit.

local root = arg[1] or "."
package.path = root .. "/mod/jamaltron/?.lua;" .. package.path

local C = require("prototypes.shared")

defines = {direction = {north = 0, northnortheast = 1, northeast = 2, eastnortheast = 3,
  east = 4, eastsoutheast = 5, southeast = 6, southsoutheast = 7, south = 8,
  southsouthwest = 9, southwest = 10, westsouthwest = 11, west = 12, westnorthwest = 13,
  northwest = 14, northnorthwest = 15}}

local function tile(layers, fluid)
  local set = {}
  for _, name in ipairs(layers) do set[name] = true end
  return {collision_mask = {layers = set}, fluid = fluid and {name = fluid} or nil}
end
prototypes = {
  entity = {[C.leg_name(1)] = {collision_mask = {layers = {player = true, rail = true}}}},
  tile = {
    ["grass-1"] = tile({"ground_tile"}),
    deepwater = tile({"water_tile", "resource", "item", "player", "doodad"}, "water"),
    lava = tile({"water_tile", "player", "rail"}, "lava"),
  },
}

-- The game, as much of it as speech.lua touches. `said` is every line, in order.
local said = {}
local function reset()
  storage = {}
  said = {}
  game = {tick = 0, connected_players = {}, print = function() end}
  settings = {global = {["jamaltron-verbosity"] = {value = "normal"},
                        ["jamaltron-speech-cooldown"] = {value = 10}}}
  script = {register_on_object_destroyed = function() end}
  rendering = {draw_text = function() return {valid = true, destroy = function() end} end}
  log = function(msg)
    local unit, id = msg:match("^jamaltron speech (%d+) (%S+)$")
    if id then said[#said + 1] = {tick = game.tick, id = id, unit = tonumber(unit)} end
  end
  math.randomseed(7)
end
reset()

local speech = require("scripts.speech")
local lines = require("scripts.lines")

local CH = {}
for _, pool in pairs(lines.pools) do
  for _, row in ipairs(pool.rows) do CH[row.id] = row.ch end
end

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end

local next_unit = 100
---A fake jamaltron at a shore at x = 40: land west, deepwater east (test_stall.lua's shape).
---`car` makes it no spider-vehicle: its autopilot reads throw, as the engine's do.
local function shark(opts)
  opts = opts or {}
  next_unit = next_unit + 1
  local driver = opts.driven and {walking_state = {walking = true, direction = defines.direction.east}}
  local e = {name = opts.name or C.name, type = opts.car and "car" or "spider-vehicle",
             valid = true, unit_number = next_unit,
             position = opts.position or {x = 28, y = 0}, autopilot_destination = opts.dest,
             follow_target = opts.follow,
             liquid = opts.liquid or "deepwater", legs = {}, driver = driver}
  e.get_driver = function() return e.driver end
  e.get_passenger = function() return nil end
  e.get_health_ratio = function() return 1 end
  e.get_spider_legs = function() return e.legs end
  e.surface = {
    get_tile = function(x) return {name = (x >= 40) and e.liquid or "grass-1"} end,
    create_entity = function(p) return {valid = true, name = p.name, destroy = function() end} end,
  }
  return setmetatable(e, {__index = function(_, k)
    if k == "walking_state" then error("Entity is not character.") end
    if opts.car and (k == "autopilot_destination" or k == "follow_target") then
      error("Entity is not spider-vehicle.")
    end
  end})
end

---Torso at x, feet trailing by lag (test_stall.lua's `at`).
local function at(e, x, lag)
  e.position = {x = x, y = 0}
  e.legs = {}
  for k = 1, 8 do e.legs[k] = {position = {x = x - lag - (k % 3) * 0.3, y = (k - 4.5)}} end
end

-- The measured head-on stall (test_stall.lua's `lake`): approach, overshoot, rest 0.9 out,
-- a 1.3-tile retry lurch every 13 polls.
local function lake_at(p)
  local t = {{28, -3}, {40.5, -2}, {42.5, 1.5}, {41.0, 1.0}, {40.9, 1.0}}
  if t[p] then return t[p][1], t[p][2] end
  local lunge = ((p - 5) % 13 == 0) and 1.3 or 0
  return 40.9 + lunge, 1.0 + lunge
end

---Run polls first..last at 1 Hz, delivering chains at 15-tick resolution like control.lua.
---`step(p, e)` moves the entity for poll p; default: the lake trace.
local function run(e, first, last, step)
  for p = first, last do
    for sub = 45, 0, -15 do
      game.tick = p * 60 - sub
      speech.deliver_due(game.tick)
    end
    if e.valid then
      if step then step(p, e) else at(e, lake_at(p)) end
    end
    speech.poll(game.tick)
  end
end

local function pool_of(id) return id:match("^(.-)%.%d+$") end
local function lines_from(unit, key)
  local out = {}
  for _, s in ipairs(said) do
    if s.unit == unit and (key == nil or pool_of(s.id) == key) then out[#out + 1] = s end
  end
  return out
end
local function show(list)
  local out = {}
  for _, s in ipairs(list) do out[#out + 1] = s.id .. "@" .. s.tick end
  return table.concat(out, ",")
end

-- ---------------------------------------------------------------------------------------

test("shore is an event: a driven stall right after `enter` speaks through the cooldown, once", function()
  reset()
  local e = shark{driven = true}
  speech.set_debug(true)
  game.tick = 60
  assert(speech.say(e, "enter"))                          -- starts the 10 s speech cooldown
  run(e, 2, 60)
  local shore = lines_from(e.unit_number, "shore")
  assert(#shore == 1, show(shore))
  assert(shore[1].tick == 5 * 60, show(shore))            -- 4 s after enter: inside the cooldown
  local st = speech.state(e)
  assert(st.stall_tick == 5 * 60 and st.stall_open and st.holding, "latched on the row said")
end)

test("R6: no `moving` at a retry lurch, no `idle`, while the episode holds him", function()
  reset()
  speech.set_debug(true)
  local e = shark{driven = true}
  speech.record(e, true)
  run(e, 1, 120)                                          -- lurches at 18, 31, 44, ... 109
  local after = {}
  for _, s in ipairs(lines_from(e.unit_number)) do
    if s.tick > 5 * 60 and pool_of(s.id) ~= "shore" then after[#after + 1] = s end
  end
  assert(#after == 0, show(after))
  assert(#lines_from(e.unit_number, "shore") == 1)
end)

test("R6 before the line: a lurch on the slow poll ahead of it is not `moving`", function()
  reset()
  speech.set_debug(true)
  local e = shark{driven = true}
  local rec = speech.record(e, true)
  run(e, 1, 3)                                            -- the approach, and its `moving`
  rec.moved_at, rec.last_tick, rec.pending = nil, nil, nil  -- as if all that was long ago
  run(e, 4, 6)                                            -- poll 4: 1.5 tiles, slow, over water
  assert(rec.moved_at == nil, "`moving` at a stuck spider, tick " .. tostring(rec.moved_at))
  local shore = lines_from(e.unit_number, "shore")
  assert(#shore == 1 and shore[1].tick == 5 * 60, show(shore))
end)

test("a follower by its target, lurching at a slot in the lake: no `moving`, idle still talks", function()
  reset()
  speech.set_debug(true)
  local target = {valid = true, position = {x = 38, y = 0}}  -- on the shore, the slot 20 out
  local e = shark{dest = {x = 58, y = 0}, follow = target}
  speech.record(e, true)
  run(e, 1, 240, function(p, s)                           -- a 0.6-tile lurch every 60 s
    if p <= 5 then at(s, lake_at(p)) else at(s, 40.9 + (p % 60 == 0 and 0.6 or 0), 1.0) end
  end)
  local late = {}
  for _, s in ipairs(lines_from(e.unit_number, "moving")) do
    if s.tick > 3 * 60 then late[#late + 1] = s end
  end
  assert(#late == 0, show(late))
  assert(#lines_from(e.unit_number, "shore") == 0 and not speech.state(e).holding)
  assert(#lines_from(e.unit_number, "idle") > 0, "parked by his target, he may still make small talk")
end)

test("a car a remote say gave a record: the poll never reads its autopilot, parked or rolling", function()
  reset()
  local car = shark{car = true, name = "car"}
  game.tick = 30
  assert(speech.say(car, "land", "broke") == nil)          -- a record, not a word (R4)
  run(car, 1, 5, function(_, s) at(s, 28, 0) end)
  run(car, 6, 10, function(p, s) at(s, 22 + p, 0) end)     -- rolling on, nobody aboard
end)

test("an autopilot unit stuck at a lake: one line, then no idle for two minutes, and idle_at keeps moving", function()
  reset()
  speech.set_debug(true)
  local e = shark{dest = {x = 70, y = 0}}
  speech.record(e, true)
  local due = {}
  run(e, 1, 150, function(p, s)
    at(s, lake_at(p))
    due[p] = speech.state(s).idle_at
  end)
  local all = lines_from(e.unit_number)                  -- a `moving` on the walk in is fine
  assert(pool_of(all[#all].id) == "shore" and #lines_from(e.unit_number, "shore") == 1, show(all))
  assert(speech.state(e).idle_at > 150 * 60, "idle_at pushed, not left to expire")
end)

test("the episode ending does not unleash an idle line the same poll", function()
  reset()
  speech.set_debug(true)
  local e = shark{dest = {x = 70, y = 0}}
  speech.record(e, true)
  run(e, 1, 100)                                          -- held for ~95 s: idle_at long past without R6's push
  e.autopilot_destination = nil                           -- the player gives up on him
  run(e, 101, 115, function(_, s) at(s, 40.9, 1.0) end)   -- the episode ends at 10 s quiet
  assert(not speech.state(e).holding, "the episode should be over")
  local idle = lines_from(e.unit_number, "idle")
  assert(#idle == 0, show(idle))
end)

test("R5: a chain in flight swallows the stall line; it lands after, and only then latches", function()
  reset()
  speech.set_debug(true)
  local e = shark{driven = true}
  speech.record(e, true)
  run(e, 1, 3)
  game.tick = 3 * 60 + 30
  assert(speech.force(e, "idle.08") == "idle.08")         -- idle.09 due 150 ticks later: 360
  run(e, 4, 20)
  local shore = lines_from(e.unit_number, "shore")
  assert(#shore == 1 and shore[1].tick == 6 * 60, show(shore))  -- 5 swallowed, 6 speaks
  local all = lines_from(e.unit_number)                  -- the punchline, THEN the shore line
  assert(show(all):match("idle%.08@210,idle%.09@360,shore%.%d+@360$"), show(all))
  assert(speech.state(e).stall_tick == 6 * 60)
end)

test("low_health.01's hush: the stall line is narration", function()
  reset()
  speech.set_debug(true)
  for seed = 1, 20 do
    reset()
    speech.set_debug(true)
    math.randomseed(seed)
    local e = shark{driven = true}
    speech.record(e, true)
    game.tick = 30
    speech.force(e, "low_health.01")
    run(e, 1, 10)
    local shore = lines_from(e.unit_number, "shore")
    assert(#shore == 1 and CH[shore[1].id] == "narration", show(shore))
  end
end)

test("jump_refused over water latches the episode on a row; blocked does not; a swallowed one does not", function()
  reset()
  local e = shark{driven = true}
  at(e, 39.5, -1)
  game.tick = 600
  local id = speech.say(e, "jump_refused", "water")
  assert(id and id:match("^jump_refused%."), tostring(id))
  local st = speech.state(e)
  assert(st.stall_tick == 600 and st.stall_open and st.holding, "a ground refusal opens the episode")

  local b = shark{driven = true}
  game.tick = 600
  assert(speech.say(b, "jump_refused", "blocked"))
  st = speech.state(b)
  assert(st.stall_tick == nil and not st.stall_open, "blocked is not the ground")

  local r = shark{driven = true}
  game.tick = 600
  speech.force(r, "idle.08")                              -- a chain in flight: R5
  assert(speech.say(r, "jump_refused", "lava") == nil)
  st = speech.state(r)
  assert(st.stall_tick == nil and not st.stall_open and not st.holding, "latched on the attempt")
end)

test("a refused hop and a stall at the same lake are ONE episode", function()
  reset()
  speech.set_debug(true)
  local e = shark{driven = true}
  speech.record(e, true)
  run(e, 1, 3)
  game.tick = 3 * 60 + 10
  assert(speech.say(e, "jump_refused", "water"))
  run(e, 4, 40)
  assert(#lines_from(e.unit_number, "shore") == 0, show(lines_from(e.unit_number, "shore")))
end)

test("transfer: out to beached and back at the same lake inside 30 s is ONE line", function()
  reset()
  speech.set_debug(true)
  local a = shark{driven = true}
  speech.record(a, true)
  run(a, 1, 6)
  assert(#lines_from(a.unit_number, "shore") == 1)
  -- D.4's swap out: a beached entity where he stood, the record moved whole
  local beached = shark{driven = true, name = C.name .. "-beached", position = a.position}
  speech.transfer(a.unit_number, beached)
  a.valid = false
  assert(speech.state(beached).stall_tick == 5 * 60, "the gap clock rode the transfer")
  run(beached, 7, 9, function(_, s) at(s, 40.9, 1.0) end)
  assert(not speech.state(beached).holding, "a beached shark holds no episode")
  -- and back, still pushing into the same lake
  local back = shark{driven = true, position = beached.position}
  speech.transfer(beached.unit_number, back)
  beached.valid = false
  run(back, 10, 34)                                       -- the gap runs to tick 5*60 + 1800 = poll 35
  local all = {}
  for _, s in ipairs(said) do if pool_of(s.id) == "shore" then all[#all + 1] = s end end
  assert(#all == 1, show(all))
  assert(speech.state(back).holding, "stuck inside the gap: moving and idle stay quiet")
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
