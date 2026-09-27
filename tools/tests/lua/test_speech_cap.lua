-- The bubble cap (PLAN F.3, chotchki 2026-09-26: "yes cap the bubbles"): the real
-- scripts/speech.lua over the real picker and catalog, with FAKE sharks whose bubbles die when
-- destroyed, the way the engine's do. What the cap is FOR is the GPU (a bubble costs frame time),
-- so every test here counts bubbles actually standing, not what the registry believes.
--
--   lua tools/tests/lua/test_speech_cap.lua <repo root>
--
-- Run by tools/tests/test_speech_lua.py, in test_pick.lua's harness shape; Lua 5.2 / 5.4+ / luajit.

local root = arg[1] or "."
package.path = root .. "/mod/jamaltron/?.lua;" .. package.path

local C = require("prototypes.shared")

defines = {direction = {north = 0, northnortheast = 1, northeast = 2, eastnortheast = 3,
  east = 4, eastsoutheast = 5, southeast = 6, southsoutheast = 7, south = 8,
  southsouthwest = 9, southwest = 10, westsouthwest = 11, west = 12, westnorthwest = 13,
  northwest = 14, northnorthwest = 15}}
prototypes = {entity = {[C.leg_name(1)] = {collision_mask = {layers = {player = true}}}}, tile = {}}

local said, made, prints = {}, {}, 0

-- One surface for every shark. A bubble is standing while `valid`; the engine's own lifetime
-- is NOT modelled (a fake bubble outlives it), so a slot freed on time is the registry's doing.
local SURFACE = {}
SURFACE.create_entity = function(p)
  local b = {valid = true, name = p.name, source = p.source, lifetime = p.lifetime, tick = game.tick}
  b.destroy = function() b.valid = false end
  made[#made + 1] = b
  return b
end

local function reset(cap)
  storage = {}
  said, made, prints = {}, {}, 0
  game = {tick = 0, print = function() end, connected_players = {{
    mod_settings = {["jamaltron-chat-echo"] = {value = true}},
    position = {x = 0, y = 0}, print = function() prints = prints + 1 end}}}
  game.connected_players[1].surface = SURFACE    -- within echo range of every shark here
  settings = {global = {["jamaltron-verbosity"] = {value = "normal"},
                        ["jamaltron-speech-cooldown"] = {value = 10},
                        ["jamaltron-max-bubbles"] = {value = cap or 3}}}
  script = {register_on_object_destroyed = function() end}
  rendering = {draw_text = function()
    local r = {valid = true}
    r.destroy = function() r.valid = false end
    return r
  end}
  log = function(msg)
    local unit, id = msg:match("^jamaltron speech (%d+) (%S+)$")
    if id then said[#said + 1] = {tick = game.tick, id = id, unit = tonumber(unit)} end
  end
  math.randomseed(11)
end
reset()

local speech = require("scripts.speech")
local lines = require("scripts.lines")

local CH = {}
for _, pool in pairs(lines.pools) do
  for _, row in ipairs(pool.rows) do CH[row.id] = row.ch end
end

local next_unit = 100
local function shark(x)
  next_unit = next_unit + 1
  local e = {name = C.name, type = "spider-vehicle", valid = true, unit_number = next_unit,
             position = {x = x or 0, y = 0}, surface = SURFACE}
  e.get_driver = function() return nil end
  e.get_passenger = function() return nil end
  e.get_health_ratio = function() return 1 end
  return e
end

---Bubbles standing on the fake map, all of them (the engine's truth, not the registry's).
local function standing()
  local n = 0
  for _, b in ipairs(made) do if b.valid then n = n + 1 end end
  return n
end

---Did `e` say row `id`?
local function said_by(e, id)
  for _, l in ipairs(said) do
    if l.unit == e.unit_number and l.id == id then return true end
  end
  return false
end

---The bubble standing on `e`, if any.
local function bubble_of(e)
  for i = #made, 1, -1 do
    local b = made[i]
    if b.valid and b.source == e then return b end
  end
end

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end

---n sharks, each saying one AMBIENT line that is always a bubble and never a chain head
---(command_done: 12 speech rows, no narration, no follow-ups), so no punchline lands mid-test.
local function chatter(n)
  local out = {}
  for i = 1, n do
    local e = shark(i)
    assert(speech.say(e, "command_done"), "chatter " .. i .. " under the cap")
    out[i] = e
  end
  return out
end

-- ---------------------------------------------------------------------------------------

test("at the cap an ambient line does not happen: no bubble, no echo, nothing recorded", function()
  reset(3)
  speech.set_debug(true)
  chatter(3)
  assert(standing() == 3 and speech.live_bubbles(0) == 3)
  local d = shark(9)
  speech.record(d, true)
  local before = speech.state(d)
  local echoes, lines_said = prints, #said
  for _, key in ipairs({"idle", "flopping", "moving", "damaged", "attacking", "command_done"}) do
    assert(speech.say(d, key) == nil, key .. " spoke at the cap")
  end
  local after = speech.state(d)
  assert(standing() == 3 and #made == 3, "a bubble went up")
  assert(prints == echoes and #said == lines_said, "echoed or logged a line that never happened")
  assert(after.last_tick == nil and after.last_id == nil and after.recent == 0, "counted as said")
  assert(#after.fired == 0 and after.pending == nil, "burned a once_per_save or started a chain")
  assert(after.idle_at == before.idle_at, "say() moved the idle clock")   -- poll()'s: see below
end)

test("an idle line due at the cap waits with its clock unmoved, and the oldest due goes first", function()
  reset(1)
  speech.set_debug(true)
  chatter(1)                                              -- the one slot, until 329
  local low, high = shark(1), shark(2)                    -- low: the lower unit, due LATER
  speech.record(low, true).idle_at = 120
  speech.record(high, true).idle_at = 60
  speech.poll(120)
  assert(#said == 1, "an idle line at the cap")
  assert(speech.state(low).idle_at == 120 and speech.state(high).idle_at == 60,
         "a capped idle spent its interval: " .. speech.state(low).idle_at)
  game.tick = 330
  speech.poll(330)
  assert(said_by(high, said[2] and said[2].id or "?") and #said == 2, "the older wait did not go first")
  assert(speech.state(low).idle_at == 120, "the younger wait lost its place")
  assert(speech.state(high).idle_at > 330, "the one that spoke was not re-armed")
  game.tick = 660
  speech.poll(660)
  assert(said[3] and said_by(low, said[3].id), "the next slot did not go to the one still waiting")
end)

test("an event whose speaker holds the oldest chatter takes down SOMEONE ELSE's: never over the cap", function()
  reset(3)
  local a = chatter(1)[1]                                 -- the oldest chatter, his own
  game.tick = 5
  local b = chatter(1)[1]
  game.tick = 10
  local c = chatter(1)[1]
  settings.global["jamaltron-max-bubbles"].value = 2      -- 3 up, his own not counted: full
  game.tick = 20
  assert(speech.say(a, "exit"))
  assert(bubble_of(a) and bubble_of(b) == nil and bubble_of(c), "not the oldest OTHER chatter")
  assert(standing() == 2, standing() .. " standing under a cap of 2")
end)

test("a transferred chatter bubble keeps its AGE: older than another chatter, it goes first", function()
  reset(2)
  local a = chatter(1)[1]                                 -- born 0
  game.tick = 10
  local b = chatter(1)[1]                                 -- born 10
  game.tick = 20
  local a2 = shark(1)
  speech.transfer(a.unit_number, a2)                      -- re-hung at 20, still born 0
  a.valid = false
  game.tick = 30
  assert(speech.say(shark(3), "exit"))
  assert(bubble_of(a2) == nil and bubble_of(b), "the transfer made the old bubble young")
end)

test("a punchline is its head's kind: an ambient head's may be taken down, an event head's not", function()
  reset(1)
  local a = shark(1)
  assert(speech.force(a, "idle.08") == "idle.08")         -- ambient head, idle.09 at 150
  game.tick = 150
  speech.deliver_due(150)
  game.tick = 160
  assert(speech.say(shark(2), "exit"))
  assert(bubble_of(a) == nil and standing() == 1, "an ambient head's punchline was not chatter")

  reset(1)
  a = shark(1)
  assert(speech.force(a, "built.05") == "built.05")       -- event head, built.03 at 180
  game.tick = 180
  speech.deliver_due(180)
  game.tick = 190
  assert(speech.say(shark(2), "exit"))
  assert(bubble_of(a) and standing() == 2, "an event head's punchline was taken down")
end)

test("ambient_free_at is now while hushed at the cap: his line would be narration, which is uncapped", function()
  reset(1)
  settings.global["jamaltron-speech-cooldown"].value = 3
  chatter(1)                                              -- full until 329
  local d = shark(9)
  assert(speech.force(d, "low_health.01") == "low_health.01")   -- hushed until 900
  assert(speech.ambient_free_at(d, 200) == 200, speech.ambient_free_at(d, 200))
end)

test("narration takes no slot, so it makes no room: an event's, or a punchline's", function()
  reset(1)
  local a = chatter(1)[1]
  local d = shark(9)
  assert(speech.force(d, "low_health.01") == "low_health.01")   -- the hush: speech -> narration
  game.tick = 10
  local id = speech.say(d, "jump")
  assert(id and CH[id] == "narration", "the hushed jump line: " .. tostring(id))
  assert(bubble_of(a), "an event's narration took down chatter")

  reset(1)
  a = chatter(1)[1]
  d = shark(9)
  speech.record(d, true).pending = {id = "low_health.01", due = 10, ambient = false}
  game.tick = 10
  speech.deliver_due(10)
  assert(bubble_of(a), "a narration punchline took down chatter")
end)

test("two chatter bubbles born the same tick: the event takes the LOWER unit's", function()
  reset(2)
  local sharks = chatter(2)                               -- both born 0; sharks[1] the lower
  game.tick = 10
  assert(speech.say(shark(3), "exit"))
  assert(bubble_of(sharks[1]) == nil and bubble_of(sharks[2]), "the tie-break is not the lower unit")
end)

test("an event evicts the OLDEST ambient bubble, and only one", function()
  reset(3)
  local sharks = {}
  for i = 1, 3 do
    game.tick = i * 10
    sharks[i] = chatter(1)[1]
  end
  game.tick = 40
  local d = shark(9)
  assert(speech.say(d, "exit"), "an event at the cap")
  assert(bubble_of(sharks[1]) == nil, "the oldest chatter is still up")
  assert(bubble_of(sharks[2]) and bubble_of(sharks[3]) and bubble_of(d))
  assert(standing() == 3 and speech.live_bubbles(40) == 3)
end)

test("an event never evicts another EVENT's bubble: every live bubble an event's, it goes up anyway", function()
  reset(2)
  local a, b = shark(1), shark(2)
  assert(speech.say(a, "exit") and speech.say(b, "enter"))
  local c = shark(3)
  assert(speech.say(c, "exit"), "the cap swallowed an event")
  assert(bubble_of(a) and bubble_of(b) and bubble_of(c) and standing() == 3)
  assert(speech.say(shark(4), "idle") == nil, "and chatter still waits above the cap")
end)

test("mixed: an event takes the ambient one even when it is not the oldest bubble", function()
  reset(2)
  local a = shark(1)
  game.tick = 5
  assert(speech.say(a, "exit"))                          -- oldest, but an event's
  game.tick = 10
  local b = chatter(1)[1]
  game.tick = 20
  local c = shark(3)
  assert(speech.say(c, "enter"))
  assert(bubble_of(a) and bubble_of(b) == nil and bubble_of(c) and standing() == 2)
end)

test("his own bubble is no extra slot: at the cap a shark already talking may replace his line", function()
  reset(2)
  local a, b = shark(1), shark(2)
  assert(speech.say(a, "exit") and speech.say(b, "exit"))
  game.tick = 60                                          -- a's cooldown still runs: event only
  assert(speech.say(a, "enter"), "an event replacing his own bubble")
  assert(standing() == 2 and bubble_of(b), "evicted someone for a slot he already held")
end)

test("a chain's punchline is never dropped: it replaces its head, or makes room like an event", function()
  reset(2)
  speech.set_debug(true)
  local a = shark(1)
  assert(speech.force(a, "idle.08") == "idle.08")         -- an ambient head, idle.09 due in 150
  local b = chatter(1)[1]
  game.tick = 150
  speech.deliver_due(150)
  assert(said_by(a, "idle.09"), "the punchline")
  assert(standing() == 2 and bubble_of(b), "it replaced its head, nothing else")

  -- the head's bubble taken down by an event before the punchline: it needs a slot of its own
  reset(2)
  speech.set_debug(true)
  a = shark(1)
  assert(speech.force(a, "idle.08") == "idle.08")
  game.tick = 10
  b = chatter(1)[1]
  game.tick = 20
  local c = shark(3)
  assert(speech.say(c, "exit"))                          -- evicts a's head, the oldest ambient
  assert(bubble_of(a) == nil)
  game.tick = 150
  speech.deliver_due(150)
  assert(said_by(a, "idle.09") and bubble_of(a), "the punchline was dropped")
  assert(bubble_of(b) == nil and bubble_of(c) and standing() == 2, "no room made for it")

  -- and when there is no chatter left to take down, it goes up over the cap
  reset(1)
  speech.set_debug(true)
  a = shark(1)
  assert(speech.force(a, "idle.08") == "idle.08")
  game.tick = 20
  c = shark(3)
  assert(speech.say(c, "exit"))
  game.tick = 150
  speech.deliver_due(150)
  assert(said_by(a, "idle.09") and bubble_of(a) and bubble_of(c) and standing() == 2)
end)

test("expired bubbles free their slot on time, and a bubble gone early frees it at once", function()
  reset(2)
  local sharks = chatter(2)                               -- up at tick 0, faded out at 329
  local c = shark(3)
  local gone = speech.SHOW_TICKS + speech.FADE_TICKS
  game.tick = gone - 1
  assert(speech.say(c, "idle") == nil, "a slot freed while its bubble was still fading out")
  game.tick = gone
  assert(speech.say(c, "idle"), "an expired bubble still holds its slot")
  assert(speech.live_bubbles(game.tick) == 1)

  reset(2)
  sharks = chatter(2)
  bubble_of(sharks[1]).destroy()                          -- gone with its shark, say
  game.tick = 60
  assert(speech.say(shark(3), "idle"), "an invalid bubble still holds its slot")
end)

test("the setting is read live: raising it lets chatter back in, lowering it holds it out", function()
  reset(2)
  chatter(2)
  local c = shark(3)
  assert(speech.say(c, "idle") == nil)
  settings.global["jamaltron-max-bubbles"].value = 3
  assert(speech.say(c, "idle"), "the raised cap was not read")
  settings.global["jamaltron-max-bubbles"].value = 1
  assert(speech.say(shark(4), "idle") == nil, "the lowered cap was not read")
  assert(speech.say(shark(5), "exit"), "an event under a lowered cap")
  assert(standing() == 3, "an event evicts ONE, it does not trim the map to a lowered cap")
end)

test("narration is not capped and never counted; a hushed Jamal's narration gets through", function()
  reset(1)
  settings.global["jamaltron-speech-cooldown"].value = 3
  local d = shark(9)
  assert(speech.force(d, "low_health.01") == "low_health.01")   -- narration: a 15 s speech hush
  assert(standing() == 0 and speech.live_bubbles(0) == 0, "narration took a slot")
  game.tick = 200                                         -- past d's cooldown, inside the hush
  chatter(1)                                              -- the cap is full until 500
  game.tick = 250
  local id = speech.say(d, "damaged")                     -- the one narration row it has
  assert(id and CH[id] == "narration", "a hushed Jamal's narration was capped: " .. tostring(id))
  assert(standing() == 1 and speech.live_bubbles(250) == 1)
end)

test("transfer keeps the bubble's slot, age and kind: an event still evicts it", function()
  reset(2)
  local a = chatter(1)[1]
  game.tick = 10
  local b = shark(2)
  assert(speech.say(b, "exit"))
  game.tick = 20
  local a2 = shark(1)
  speech.transfer(a.unit_number, a2)
  a.valid = false
  assert(standing() == 2 and bubble_of(a2) and speech.live_bubbles(20) == 2, "the re-hung bubble")
  assert(speech.say(shark(3), "enter"))
  assert(bubble_of(a2) == nil and bubble_of(b), "the transferred chatter lost its kind or its age")
end)

test("ambient_free_at: the cooldown's end, else the tick the next slot frees, else now", function()
  reset(2)
  local sharks = chatter(2)                               -- both gone at SHOW_TICKS + FADE_TICKS
  local c = shark(3)
  speech.record(c, true)
  game.tick = 60
  assert(speech.ambient_free_at(c, 60) == speech.SHOW_TICKS + speech.FADE_TICKS,
         speech.ambient_free_at(c, 60))
  assert(speech.ambient_free_at(sharks[1], 60) == 600, "a shark in his cooldown waits for IT")
  settings.global["jamaltron-max-bubbles"].value = 3
  assert(speech.ambient_free_at(c, 60) == 60, "under the cap: now")
end)

test("200 waiting at the cap cost one count a tick and no roll, not a scan and a pick each", function()
  reset(20)
  chatter(20)
  local waiting = {}
  for i = 1, 200 do waiting[i] = shark(100 + i) end
  local reads = 0
  for _, b in ipairs(made) do
    setmetatable(b, {__index = function(t, k)
      if k == "valid" then reads = reads + 1 return rawget(t, "_valid") end
    end})
    b._valid, b.valid = b.valid, nil
    b.destroy = function() b._valid = false end
  end
  local pick = require("scripts.speech.pick")
  local real_pick, rolls = pick.pick, 0
  pick.pick = function(...) rolls = rolls + 1 return real_pick(...) end
  game.tick = 61
  for _, e in ipairs(waiting) do assert(speech.say(e, "damaged") == nil) end
  pick.pick = real_pick
  assert(reads <= 20, "valid read " .. reads .. " times for 200 capped lines")
  assert(rolls == 0, rolls .. " rolls for lines the cap had already ruled out")
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
