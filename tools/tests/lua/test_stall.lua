-- The shore-stall detector (PLAN E.2.2) and the ground table it reads (E.2.1), under plain lua,
-- with FAKE entities replaying the shapes the 2026-09-25 shore spikes measured in the engine.
--
--   lua tools/tests/lua/test_stall.lua <repo root>
--
-- Run by tools/tests/test_speech_lua.py, in test_pick.lua's harness shape; Lua 5.2 / 5.4+ / luajit.
-- The detector touches the game only through the entity handle, `defines` and `prototypes`,
-- so fakes are enough.

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

-- Layers after the tile report's measured table (2.1.17 + Space Age); the leg is {player, rail}.
prototypes = {
  entity = {[C.leg_name(1)] = {collision_mask = {layers = {player = true, rail = true}}}},
  tile = {
    ["grass-1"] = tile({"ground_tile"}),
    water = tile({"water_tile", "resource", "item", "player", "doodad"}, "water"),
    deepwater = tile({"water_tile", "resource", "item", "player", "doodad"}, "water"),
    ["water-shallow"] = tile({"ground_tile", "water_tile"}, "water"),
    ["water-mud"] = tile({"ground_tile", "water_tile"}, "water"),
    ["wetland-blue-slime"] = tile({"ground_tile"}, "water"),
    ["oil-ocean-deep"] = tile({"water_tile", "resource"}, "heavy-oil"),
    lava = tile({"water_tile", "player", "rail"}, "lava"),
    ["ammoniacal-ocean"] = tile({"water_tile", "player", "item"}, "ammoniacal-solution"),
    ["brash-ice"] = tile({"water_tile", "player"}, "ammoniacal-solution"),
    ["out-of-map"] = tile({"ground_tile", "player", "rail", "item"}),
    ["empty-space"] = tile({"ground_tile", "player", "item"}),
    ["water-wube"] = tile({"water_tile", "player"}),
    ["modded-goo"] = tile({"rail"}, "goo"),        -- blocks on the leg's OTHER layer only
  },
}

local ground = require("scripts.ground")
local stall = require("scripts.speech.stall")

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end

---A fake jamaltron at a shore at x = 40: land west of it, `liquid` east of it (e.liquid, so a
---test can change the ground under him). Reading the vehicle's own walking_state throws, as
---the engine does; `car` makes it no spider-vehicle, and its autopilot reads throw too.
local function shark(opts)
  local driver = opts.driven and {walking_state = {walking = false, direction = defines.direction.east}}
  local e = {name = opts.name or C.name, valid = true, position = {x = 28, y = 0},
             autopilot_destination = opts.dest, follow_target = opts.follow,
             liquid = opts.liquid or "deepwater", legs = {}, driver = driver,
             occupied = driver ~= nil or opts.passenger == true}
  e.get_driver = function() return driver end
  e.get_spider_legs = function() return e.legs end
  e.surface = {get_tile = function(x) return {name = (x >= 40) and e.liquid or "grass-1"} end}
  return setmetatable(e, {__index = function(_, k)
    if k == "walking_state" then error("Entity is not character.") end
    if opts.car and (k == "autopilot_destination" or k == "follow_target") then
      error("Entity is not spider-vehicle.")
    end
  end})
end

---Move the torso to x; feet trail it by `lag` (negative lag = feet ahead, i.e. walking).
local function at(e, x, lag)
  e.position = {x = x, y = 0}
  e.legs = {}
  for k = 1, 8 do e.legs[k] = {position = {x = x - lag - (k % 3) * 0.3, y = (k - 4.5)}} end
end

---Poll once a second over a trace of {x, lag, walking}; returns the fires and the record.
---`o.say` stands in for speech.say (a row id, or nil when R5 or a hush swallowed it) and the
---caller latches only on a row, as speech.poll will. `o.before(i, e)` / `o.after(i, rec)` run
---around each poll.
local function replay(e, trace, o)
  o = o or {}
  local rec, fired = {entity = e}, {}
  for i, s in ipairs(trace) do
    at(e, s[1], s[2])
    if e.driver then e.driver.walking_state.walking = s[3] ~= false end
    if o.before then o.before(i, e) end
    local cond = stall.check(rec, i * 60, e.position, e.occupied)
    if cond and (o.say == nil or o.say(i)) then
      fired[#fired + 1] = {tick = i * 60, cond = cond}
      stall.latch(rec, i * 60)
    end
    if o.after then o.after(i, rec) end
  end
  return fired, rec
end

-- MEASURED shape of a head-on stall (driven spike): 12.8 t/s approach, torso overshoots
-- 2.3-2.6 tiles past the shore, springs back to rest 0.67-1.26 past it, feet on the last land
-- column (torso ahead of every foot), a 1.1-1.5 tile lunge now and then. `walking(poll)`
-- releases the key where it returns false.
local function lake(n, walking)
  local t = {{28, -3}, {40.5, -2}, {42.5, 1.5}, {41.0, 1.0}, {40.9, 1.0}}
  for p = 6, n do
    local lunge = ((p - 5) % 13 == 0) and 1.3 or 0
    t[p] = {40.9 + lunge, 1.0 + lunge, walking == nil or walking(p)}
  end
  return t
end

local function ticks(fired)
  local out = {}
  for _, f in ipairs(fired) do out[#out + 1] = f.tick end
  return table.concat(out, ",")
end

-- ---- the spike's twelve ---------------------------------------------------------------

test("holding W into a lake for a minute is ONE line, and it names the water", function()
  local fired = replay(shark{driven = true}, lake(60))
  assert(#fired == 1, ticks(fired))
  -- the SECOND slow poll (the spring-back is the first): POLLS = 2, about 2-3 s after contact
  assert(fired[1].cond == "water" and fired[1].tick == 5 * 60, fired[1].tick)
end)

test("the ground names the line: lava, void; walkable liquids never stall", function()
  assert(replay(shark{driven = true, liquid = "lava"}, lake(20))[1].cond == "lava")
  assert(replay(shark{driven = true, liquid = "out-of-map"}, lake(20))[1].cond == "void")
  assert(#replay(shark{driven = true, liquid = "water-shallow"}, lake(20)) == 0)
  assert(#replay(shark{driven = true, liquid = "oil-ocean-deep"}, lake(20)) == 0)
end)

test("a slide along the shore (5.2-5.7 t/s, measured) never fires", function()
  local e = shark{driven = true}
  local rec = {entity = e}
  for i = 1, 30 do
    at(e, 40.8 + (i % 2) * 0.9, -2.0)                  -- x wobbles 40.7-41.8
    e.position.y = -5.5 * i
    for _, leg in ipairs(e.legs) do leg.position.y = leg.position.y - 5.5 * i end
    e.driver.walking_state.walking = true
    assert(stall.check(rec, i * 60, e.position, true) == nil, i)
  end
end)

test("a crossing with one slow poll (feet ahead) does not fire", function()
  local t = {{28, -3}, {40.9, -3}, {42.0, -4}, {44.1, -4}, {49.5, -5}, {59, -5}, {70, -5}}
  assert(#replay(shark{driven = true}, t) == 0)
end)

test("three slow polls over deep water with the feet AHEAD (a crossing pause) do not fire", function()
  local t = {{28, -3}, {40.9, -3}, {41.5, -6}, {41.9, -6}, {42.2, -6}, {55, -5}, {68, -5}}
  assert(#replay(shark{driven = true}, t) == 0)
end)

test("a line swallowed by R5 or a hush is retried next poll, not lost", function()
  local fired = replay(shark{driven = true}, lake(20), {say = function(i) return i >= 8 end})
  assert(#fired == 1 and fired[1].tick == 8 * 60, ticks(fired))
end)

test("release for 10 s re-arms, but not inside 30 s of the last line", function()
  local off35 = function(p) return not (p >= 15 and p < 50) end   -- let go for 35 s
  local fired = replay(shark{driven = true}, lake(75, off35))
  assert(#fired == 2, ticks(fired))
  local tap = function(p) return (p - 5) % 8 ~= 0 end              -- 1 s taps: one episode
  assert(#replay(shark{driven = true}, lake(75, tap)) == 1)
end)

test("stall, 16 tiles along the coast, stall again inside 30 s: one line until the gap ends", function()
  local e = shark{driven = true}
  local rec, n = {entity = e}, 0
  for i = 1, 40 do
    local y = (i <= 10) and 0 or 16                      -- one jump along the shore at poll 11
    at(e, (i == 1) and 28 or 40.9, (i == 1) and -3 or 1.0)
    e.position.y = y
    for _, leg in ipairs(e.legs) do leg.position.y = leg.position.y + y end
    e.driver.walking_state.walking = true
    if stall.check(rec, i * 60, e.position, true) then n = n + 1; stall.latch(rec, i * 60) end
    if i == 25 then assert(n == 1, "a second line inside the 30 s gap") end
  end
  assert(n == 2, "the gap ends and the second stall speaks, got " .. n)
end)

test("an autopilot stall fires; a follower by its target is not told to go", function()
  assert(#replay(shark{dest = {x = 100, y = 0}}, lake(20)) == 1)
  -- folshore, measured: the target stands on the shore 4.9 tiles off, its slot (offset 12) is
  -- in the lake 7.1 tiles out - past the slot guard, so the TARGET guard is what holds
  local target = {valid = true, position = {x = 36, y = 0}}
  local fired, rec = replay(shark{dest = {x = 48, y = 0}, follow = target}, lake(20))
  assert(#fired == 0 and not stall.holding(rec))
end)

test("nobody driving, nothing queued: a passenger by the lake is silent", function()
  local fired, rec = replay(shark{passenger = true}, lake(20))
  assert(#fired == 0 and not stall.holding(rec))
end)

test("the beached entity is never checked and holds no episode", function()
  local fired, rec = replay(shark{driven = true, name = C.name .. "-beached"}, lake(20))
  assert(#fired == 0 and rec.stall.at == nil and not stall.holding(rec))
end)

test("stopped by entities on dry land: latched silently, holding - and no gap after it", function()
  local e = shark{driven = true, liquid = "grass-1"}
  local fired, rec = replay(e, lake(10))
  assert(#fired == 0 and stall.holding(rec))
  -- the silence was not a line: once that episode ends (key up 10 s), a lake speaks without
  -- waiting 30 s. e.liquid flips to stand in for driving to a real shore.
  local off = function(p) return not (p >= 10 and p < 22) end
  local held = {}
  fired = replay(shark{driven = true, liquid = "grass-1"}, lake(30, off), {
    before = function(i, s) if i == 22 then s.liquid = "deepwater" end end,
    after = function(i, r) held[i] = stall.holding(r) end})
  assert(held[5] and held[19] and not held[21], "the silent episode, then its end")
  assert(#fired == 1 and fired[1].tick == 23 * 60, ticks(fired))
end)

-- ---- one per verified fix -------------------------------------------------------------

test("ground: the LEG's mask decides, a fluid alone decides nothing", function()
  local want = {
    water = "water", deepwater = "water", lava = "lava",
    ["ammoniacal-ocean"] = "ammoniacal-solution", ["brash-ice"] = "ammoniacal-solution",
    ["out-of-map"] = "void", ["empty-space"] = "void", ["water-wube"] = "void",
    ["modded-goo"] = "goo",
    ["grass-1"] = false, ["water-shallow"] = false, ["water-mud"] = false,
    ["wetland-blue-slime"] = false, ["oil-ocean-deep"] = false, ["no-such-tile"] = false,
  }
  for name, value in pairs(want) do
    assert(ground.of(name) == value, name .. " -> " .. tostring(ground.of(name)))
  end
  for _, cond in ipairs({"water", "lava", "ammoniacal-solution", "void", "goo"}) do
    assert(ground.is_ground(cond), cond)
  end
  -- heavy-oil is a fluid, but no tile carrying it blocks a foot; the rest are jump_refused's
  for _, cond in ipairs({"heavy-oil", "blocked", "cooldown", "platform", "any"}) do
    assert(not ground.is_ground(cond), cond)
  end
  assert(not ground.is_ground(nil))
end)

test("fast path: a 0.48-tile crossing poll with the stall signature, then feet ahead (POLLS = 2)", function()
  -- measured on a 15-wide river: one poll as slow as a stall's with the torso over deepwater
  -- ahead of every foot, and the next poll the feet have crossed. POLLS = 1 fires here.
  local t = {{28, -3}, {40.52, -2}, {41.0, 1.5}, {43.6, -2}, {49, -3}, {60, -3}, {70, -3}}
  local fired = replay(shark{driven = true}, t)
  assert(#fired == 0, ticks(fired))
  -- and the other probe: torso still over land, the blocking tile one ahead (a staircase
  -- shore) is the water line, not the silent entity latch
  local stair = {{28, -3}, {38.5, -2}, {39.2, 1.0}, {39.5, 1.0}, {39.5, 1.0}}
  fired = replay(shark{driven = true}, stair)
  assert(#fired == 1 and fired[1].cond == "water" and fired[1].tick == 4 * 60, ticks(fired))
end)

test("fallback: 4 slow polls with a foot ahead fire over water, and neither fire nor latch on land", function()
  -- a straddled inlet: frozen with the frontmost foot +1 ahead of the torso
  local t = {{28, -3}, {40.9, -1}}
  for p = 3, 20 do t[p] = {40.9 + (p % 2) * 0.1, -1} end
  local fired = replay(shark{driven = true}, t)
  assert(#fired == 1 and fired[1].cond == "water" and fired[1].tick == 6 * 60, ticks(fired))
  local dry, rec = replay(shark{driven = true, liquid = "grass-1"}, t)
  assert(#dry == 0 and rec.stall.at == nil and not stall.holding(rec))
end)

test("follow and arrival guards: a follower at offset 20 never fires, plain autopilot inside 3", function()
  local far = {valid = true, position = {x = 11, y = 0}}        -- 17+ tiles off: target guard idle
  local parked = {{28, -1.5}}
  for p = 2, 20 do parked[p] = {28, -1.5} end
  local fired, rec = replay(shark{dest = {x = 31, y = 0}, follow = far}, parked)
  assert(#fired == 0 and not stall.holding(rec) and not stall.pushed(rec), "parked on land by its slot")
  -- its slot in the lake 1.1 tiles past where he stalled, the target 19 tiles back on land
  local target = {valid = true, position = {x = 22, y = 0}}
  fired, rec = replay(shark{dest = {x = 42, y = 0}, follow = target}, lake(30))
  assert(#fired == 0 and not stall.holding(rec), "a follower whose slot is in the lake")
  -- plain autopilot: 1.6 short of the destination has arrived, 4.1 short is stuck
  assert(#replay(shark{dest = {x = 42.5, y = 0}}, lake(20)) == 0)
  assert(#replay(shark{dest = {x = 45, y = 0}}, lake(20)) == 1)
end)

test("swap out to beached and back at the same lake inside 30 s is ONE line", function()
  local e = shark{driven = true}
  local swap = function(i)
    if i == 6 then e.name = C.name .. "-beached" end        -- D.4 swap out, transfer keeps rec
    if i == 8 then e.name = C.name end                      -- back, still pushing into the lake
  end
  local held = {}
  local fired = replay(e, lake(34), {before = swap, after = function(i, rec) held[i] = stall.holding(rec) end})
  assert(#fired == 1 and fired[1].tick == 5 * 60, ticks(fired))
  assert(not held[6] and not held[7], "the beached shark held an episode")
end)

test("re-arm fires on the poll the gap expires, not one later", function()
  -- line at poll 5; key released polls 10-21 (the episode ends at 10 s quiet), pressed again
  -- from 22 and still stuck: the gap runs out at tick 5*60 + 1800 = poll 35
  local off = function(p) return not (p >= 10 and p < 22) end
  local fired = replay(shark{driven = true}, lake(40, off))
  assert(#fired == 2 and fired[2].tick == 35 * 60, ticks(fired))
  -- an episode that ENDS past the gap falls through too: W held 35 s after the line, then a
  -- grinding slide (1.9 tiles a poll, measured 1.3-2.8 on natural coasts) carries him 10
  -- tiles from the latch point at poll 42 - that poll speaks, not the next
  local e = shark{driven = true}
  local grind = function(i, s)
    if i > 36 then
      local y = 1.9 * (i - 36)
      s.position.y = y
      for _, leg in ipairs(s.legs) do leg.position.y = leg.position.y + y end
    end
  end
  fired = replay(e, lake(44), {before = grind})
  assert(#fired == 2 and fired[1].tick == 5 * 60 and fired[2].tick == 42 * 60, ticks(fired))
end)

test("holding: true stuck before the line and again inside the gap, false while he gets somewhere", function()
  local e = shark{driven = true}
  local rec, fired, held = {entity = e}, {}, {}
  for i = 1, 36 do
    local y = (i <= 10) and 0 or (i < 30) and 16 or 32   -- 16 tiles along the coast at 11 and 30
    at(e, (i == 1) and 28 or 40.9, (i == 1) and -3 or 1.0)
    e.position.y = y
    for _, leg in ipairs(e.legs) do leg.position.y = leg.position.y + y end
    e.driver.walking_state.walking = true
    if stall.check(rec, i * 60, e.position, true) then fired[#fired + 1] = i; stall.latch(rec, i * 60) end
    held[i] = stall.holding(rec)
  end
  assert(fired[1] == 4 and fired[2] == 34, table.concat(fired, ","))
  assert(held[3], "the slow poll before the line: a lurch there is not `moving` either")
  assert(held[5] and held[10], "the open episode")
  assert(not held[11] and not held[30], "a poll he moved 16 tiles is not stuck")
  for i = 12, 33 do
    if i ~= 30 then assert(held[i], "stuck inside the gap at poll " .. i) end
  end
end)

test("stuck inside the gap reads the line's own probe: a staircase torso over land still holds", function()
  -- the fast-path test's staircase: the line at poll 4 off the tile AHEAD; key up 8-19 (the
  -- episode ends at 10 s quiet), down again from 20 at the same spot, inside the gap
  local stair = {{28, -3}, {38.5, -2}, {39.2, 1.0}, {39.5, 1.0}}
  for p = 5, 40 do stair[p] = {39.5, 1.0, not (p >= 8 and p < 20)} end
  local held = {}
  local fired = replay(shark{driven = true}, stair, {after = function(i, r) held[i] = stall.holding(r) end})
  assert(#fired == 2 and fired[1].tick == 4 * 60 and fired[2].tick == 34 * 60, ticks(fired))
  assert(not held[19], "the episode ended")
  for i = 20, 33 do assert(held[i], "stuck inside the gap at poll " .. i) end
end)

test("aboard but off the keys, the autopilot is the heading: a passenger, or a driver not steering", function()
  -- a player riding along while the remote sends him into a lake
  local fired = replay(shark{passenger = true, dest = {x = 100, y = 0}}, lake(20))
  assert(#fired == 1 and fired[1].cond == "water" and fired[1].tick == 5 * 60, ticks(fired))
  fired = replay(shark{driven = true, dest = {x = 100, y = 0}}, lake(20),
                 {before = function(_, e) e.driver.walking_state.walking = false end})
  assert(#fired == 1 and fired[1].cond == "water" and fired[1].tick == 5 * 60, ticks(fired))
end)

test("a follower by its target lurching at a slot in the lake: pushed, never a line, never held", function()
  -- the target on the shore, the slot 18 out in the lake (the harness's follow_shore lane)
  local target = {valid = true, position = {x = 38, y = 0}}
  local pushed = {}
  local fired, rec = replay(shark{dest = {x = 58, y = 0}, follow = target}, lake(40),
                            {after = function(i, r) pushed[i] = stall.pushed(r) end})
  assert(#fired == 0 and not stall.holding(rec) and rec.stall.at == nil, ticks(fired))
  assert(not pushed[2] and not pushed[3], "still getting somewhere")
  for i = 4, 40 do assert(pushed[i], "pushing at the lake at poll " .. i) end
end)

test("a record on a car (a remote say gave it one) never reads an autopilot it does not have", function()
  -- the engine throws on a car's autopilot_destination - on the 1 Hz clock, for good
  for _, driven in ipairs({false, true}) do
    local fired, rec = replay(shark{name = "car", car = true, driven = driven}, lake(10))
    assert(#fired == 0 and not stall.holding(rec) and not stall.pushed(rec))
  end
end)

test("cost: a parked, empty jamaltron with nowhere to go reads two things and stops", function()
  local reads = {}
  local real = {name = C.name, surface = {}, get_driver = function() end,
                get_spider_legs = function() return {} end}
  local e = setmetatable({}, {__index = function(_, k)
    reads[#reads + 1] = k
    return real[k]
  end})
  local rec = {entity = e}
  for i = 1, 5 do
    reads = {}
    assert(stall.check(rec, i * 60, {x = 28, y = 0}, false) == nil)
    assert(#reads == 2 and reads[1] == "name" and reads[2] == "autopilot_destination",
           table.concat(reads, ","))
  end
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
