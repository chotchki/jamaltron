-- The flamethrower's lines (PLAN D.7): scripts/attack.lua's burst, friendly-fire gate and damage
-- filter, under plain lua, over the REAL speech.lua, picker and generated catalog, with FAKE
-- entities whose ammo slots a test drains by hand. What the engine raises and when - a stream
-- start, a damage event's cause - is tools/harness/jamaltron-fire-harness's; this is what
-- attack.lua does with them.
--
--   lua tools/tests/lua/test_attack.lua <repo root>
--
-- Run by tools/tests/test_speech_lua.py, in test_pick.lua's harness shape; Lua 5.2 / 5.4+ / luajit.

local root = arg[1] or "."
package.path = root .. "/mod/jamaltron/?.lua;" .. package.path

local C = require("prototypes.shared")

defines = {inventory = {spider_ammo = 2}, events = {on_entity_damaged = "on_entity_damaged"},
  direction = {north = 0, northnortheast = 1, northeast = 2, eastnortheast = 3, east = 4,
  eastsoutheast = 5, southeast = 6, southsoutheast = 7, south = 8, southsouthwest = 9,
  southwest = 10, westsouthwest = 11, west = 12, westnorthwest = 13, northwest = 14,
  northnorthwest = 15}}
prototypes = {entity = {}, tile = {}}

-- Every set_event_filter call, in order: {event, filter}.
local set_filters = {}

local function reset(opts)
  opts = opts or {}
  storage = {}
  game = {tick = 0, connected_players = {}, print = function() end}
  settings = {global = {["jamaltron-verbosity"] = {value = opts.verbosity or "normal"},
                        ["jamaltron-speech-cooldown"] = {value = opts.cooldown or 10}}}
  script = {register_on_object_destroyed = function() end,
            set_event_filter = function(id, f) set_filters[#set_filters + 1] = {id, f} end}
  rendering = {draw_text = function() return {valid = true, destroy = function() end} end}
  log = function() end
  math.randomseed(11)
end
reset()

local speech = require("scripts.speech")
local lines = require("scripts.lines")

-- Every say(), with the condition it was made under and what came back.
local said = {}
local real_say = speech.say
speech.say = function(entity, key, cond)
  local id = real_say(entity, key, cond)
  said[#said + 1] = {entity = entity, key = key, cond = cond, id = id, tick = game.tick}
  return id
end

local attack = require("scripts.attack")
local OURS_FILTER = {{filter = "name", name = C.name}, {filter = "name", name = C.beached},
                     {filter = "name", name = C.airborne}}
local NARROW = attack.install(OURS_FILTER)
local WIDE = attack.filter(true)

local SUB = {}
for _, row in ipairs(lines.pools.attacking.rows) do SUB[row.id] = row.sub end

local SURFACE = {valid = true}
SURFACE.create_entity = function(p)
  local b = {valid = true, name = p.name}
  b.destroy = function() b.valid = false end
  return b
end

local next_unit = 100
---A fake entity. A Jamal (any body) carries four ammo slots, `rounds` in the first.
local function entity(name, opts)
  opts = opts or {}
  next_unit = next_unit + 1
  local e = {name = name, valid = true, unit_number = next_unit, surface = SURFACE,
             force_index = opts.force or 1, position = {x = next_unit, y = 0}}
  local slots = {}
  for i = 1, 4 do
    slots[i] = {valid_for_read = false, count = 0, ammo = 0, prototype = {magazine_size = 100}}
  end
  if opts.rounds then
    slots[1].valid_for_read, slots[1].count, slots[1].ammo = true, math.ceil(opts.rounds / 100),
      (opts.rounds - 1) % 100 + 1
  end
  e.slots = slots
  e.get_inventory = function(index)
    if index ~= defines.inventory.spider_ammo or not attack.OURS[e.name] then return nil end
    return slots
  end
  e.get_health_ratio = function() return 1 end
  e.get_driver = function() return nil end
  e.get_passenger = function() return nil end
  return e
end
---Spend `n` rounds out of his first slot (what firing does between two polls).
local function spend(e, n)
  local s = e.slots[1]
  local total = (s.count - 1) * 100 + s.ammo - n
  s.count, s.ammo = math.ceil(total / 100), (total - 1) % 100 + 1
end

local FIRE = {name = "fire"}
local function hit(cause, victim, amount, damage_type)
  return attack.damaged({cause = cause, entity = victim, final_damage_amount = amount or 1,
                         damage_type = damage_type or FIRE, tick = game.tick})
end

local function start(opts)
  reset(opts)
  said = {}
  set_filters = {}
  next_unit = 100
end

---The attacking lines actually said, as ids.
local function lines_said(e)
  local out = {}
  for _, s in ipairs(said) do
    if s.key == "attacking" and s.id and (e == nil or s.entity == e) then out[#out + 1] = s.id end
  end
  return out
end
---The say() that produced the last attacking line of `e`.
local function last_line(e)
  local out = nil
  for _, s in ipairs(said) do
    if s.key == "attacking" and s.id and s.entity == e then out = s end
  end
  return out
end

---control.lua's two clocks from `from` to `to`: deliver_due every 15 ticks, poll every 60,
---spending `per_poll` rounds before each poll when given.
local function run(e, from, to, per_poll)
  for t = from, to do
    if t % 15 == 0 then
      game.tick = t
      attack.deliver_due(t)
      if t % 60 == 0 then
        if per_poll and e then spend(e, per_poll) end
        attack.poll(t)
      end
    end
  end
end

local GAP = speech.BURST_GAP_TICKS
local HOLD = attack.HOLD_TICKS

local tests, names = {}, {}
local function test(name, fn) tests[#tests + 1] = fn; names[#names + 1] = name end

test("a stream start opens a burst; its line waits HOLD_TICKS for the volley, then comes plain", function()
  start{}
  local j = entity(C.name, {rounds = 1000})
  game.tick = 10
  assert(attack.fired(j, 10) == nil, "rolled before the opening volley landed")
  local st = attack.state(j)
  assert(st.open and not st.said and st.due == 10 + HOLD, "burst open, first roll due at +HOLD")
  run(j, 11, 10 + HOLD + 15)
  assert(#lines_said(j) == 1, "said once, on the 15-tick clock: " .. #lines_said(j))
  local s = last_line(j)
  assert(s.tick >= 10 + HOLD and s.tick < 10 + HOLD + 15, "at the first 15-tick past due: " .. s.tick)
  assert(s.cond == nil and SUB[s.id] ~= "friendly", "plain burst rolls under cond nil")
  st = attack.state(j)
  assert(st.said and st.rolled == nil and st.cond == nil)
end)

test("a stream start past due is a first try of its own (a walking target restarts it every tick)", function()
  start{}
  local j = entity(C.name, {rounds = 1000})
  for t = 0, HOLD do
    game.tick = t
    attack.fired(j, t)
  end
  assert(#lines_said(j) == 1 and last_line(j).tick == HOLD, "said at the start that came due")
end)

test("ONE line per burst: stream starts inside the gap say nothing, however long it runs", function()
  start{}
  local j = entity(C.name, {rounds = 1000})
  for t = 0, 3000, 500 do                       -- 7 starts, each well inside the gap of the last
    game.tick = t
    attack.fired(j, t)
  end
  assert(#lines_said(j) == 1, "one line in a 50 s burst, not one per cooldown: " .. #lines_said(j))
  assert(#said == 1, "the said burst does not even ask again: " .. #said)
end)

test("quiet a whole gap, and the next stream start is a new burst with its own line", function()
  start{}
  local j = entity(C.name, {rounds = 1000})
  attack.fired(j, 0)
  run(j, 1, GAP + 60)                            -- ammo untouched: the gun is quiet
  assert(attack.state(j) == nil, "burst closed after a quiet gap, state dropped")
  game.tick = GAP + 120
  attack.fired(j, GAP + 120)
  run(j, GAP + 121, GAP + 120 + HOLD + 15)
  assert(#lines_said(j) == 2, "second burst speaks: " .. #lines_said(j))
end)

test("one stream that never restarts is kept open by the ammo it spends", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  attack.fired(j, 0)
  run(j, 1, 1200, 60)                            -- 1.125 a tick, roughly: still firing
  game.tick = 1210
  attack.fired(j, 1210)                          -- next target, 1210 ticks after the first start
  run(j, 1211, 1300, 60)
  assert(#lines_said(j) == 1, "still the same burst: " .. #lines_said(j))
  -- the control: the same gap with the ammo untouched is a new burst
  local k = entity(C.name, {rounds = 5000})
  game.tick = 0
  attack.fired(k, 0)
  run(k, 1, 1200)
  game.tick = 1210
  attack.fired(k, 1210)
  run(k, 1211, 1300)
  assert(#lines_said(k) == 2, "no ammo spent, no burst: " .. #lines_said(k))
end)

test("any change in rounds keeps it open - a refill or a slot emptied mid-fight only quiets him", function()
  start{}
  local j = entity(C.name, {rounds = 500})
  attack.fired(j, 0)
  game.tick = 60; attack.poll(60)
  spend(j, -300)                                 -- bots topped him up
  game.tick = 120; attack.poll(120)
  assert(attack.state(j).at == 120, "a refill counted as activity")
end)

test("a line the cooldown held is retried while he fires and said once; a finished fight gets none", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  speech.force(j, "idle.01")                     -- cooldown until 600
  game.tick = 10
  attack.fired(j, 10)
  run(j, 11, 1500, 60)
  assert(#lines_said(j) == 1, "said once, at the first poll past the cooldown: " .. #lines_said(j))
  assert(last_line(j).tick == 600, "at the first retry past 600: " .. last_line(j).tick)
  -- the same, but the fight is over by 200: the cooldown outlasts it, and nothing is narrated
  local k = entity(C.name, {rounds = 5000})
  speech.force(k, "idle.01")
  game.tick = 10
  attack.fired(k, 10)
  run(k, 11, 180, 60)
  run(k, 181, 1500)
  assert(#lines_said(k) == 0, "a line about a fight long over: " .. table.concat(lines_said(k), ","))
end)

test("attacking.03 holds its window against every retry until the gun is quiet a gap (forced twin)", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  speech.force(j, "attacking.03")                -- the row, as if the burst had rolled it
  game.tick = 10
  attack.fired(j, 10)
  run(j, 11, 1800, 60)                           -- firing for 30 s, three cooldowns
  assert(#lines_said(j) == 0, "hushed while the gun goes: " .. table.concat(lines_said(j), ","))
  run(j, 1801, 1800 + GAP + 60)                  -- quiet a whole gap
  game.tick = 1800 + GAP + 120
  attack.fired(j, game.tick)
  run(j, game.tick + 1, game.tick + HOLD + 15)
  assert(#lines_said(j) == 1, "the next burst speaks: " .. #lines_said(j))
end)

test("friendly fire: a hit from the OPENING VOLLEY is in that burst's own roll", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  local chest = entity("wooden-chest")
  game.tick = 20
  attack.fired(j, 20)
  game.tick = 31                                 -- MEASURED: first hit 11-17 ticks after the start
  assert(hit(j, chest) == "friendly")
  assert(#lines_said(j) == 0, "the hit rolled before the hold ran out")
  local st = attack.state(j)
  assert(st.friendly and st.cond == "friendly")
  run(j, 32, 20 + HOLD + 15)
  local s = last_line(j)
  assert(s and s.cond == "friendly", "the burst's roll was made under friendly")
  assert(attack.state(j).rolled == "friendly")
end)

test("... and a friendly hit is a retry point of its own", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  local chest = entity("wooden-chest")
  speech.force(j, "idle.01")
  game.tick = 10
  attack.fired(j, 10)
  run(j, 11, 540, 60)                            -- the first try held by the cooldown; firing
  game.tick = 605                                -- the cooldown is out, the next poll is not due
  hit(j, chest)
  assert(#lines_said(j) == 1 and said[#said].cond == "friendly", "said on the hit, friendly")
end)

test("friendly fire closes with its burst: the next fight's opening roll is plain", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  local chest = entity("wooden-chest")
  attack.fired(j, 0)
  game.tick = 15
  hit(j, chest)
  run(j, 16, GAP + 60)                           -- line said under friendly; quiet a gap
  assert(last_line(j).cond == "friendly" and attack.state(j) == nil, "burst 1 friendly, closed")
  local t = GAP + 100                            -- well inside the old 30 s carry-over
  game.tick = t
  attack.fired(j, t)                             -- a biter behind him, nothing of his near it
  run(j, t + 1, t + HOLD + 15)
  local s = last_line(j)
  assert(#lines_said(j) == 2 and s.cond == nil, "the second fight apologized for the first: "
         .. tostring(s.cond))
end)

test("... even when the new burst starts before the 1 Hz poll has closed the old one", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  local chest = entity("wooden-chest")
  game.tick = 30
  attack.fired(j, 30)
  game.tick = 45
  hit(j, chest)
  run(j, 46, 600)                                -- the poll at 600 is 570 in: still open
  assert(attack.state(j) and attack.state(j).friendly, "burst 1 friendly, not yet closed")
  game.tick = 640                                -- the gap is out, the closing poll (660) is not
  attack.fired(j, 640)
  run(j, 641, 640 + HOLD + 15)
  local s = last_line(j)
  assert(#lines_said(j) == 2 and s.cond == nil, "burst 2 inherited burst 1's friendly fire")
end)

test("the friendly rows come out of the REAL roll only after a hit (200 bursts each way)", function()
  start{cooldown = 0, verbosity = "unbearable"}
  local j, k = entity(C.name, {rounds = 99999}), entity(C.name, {rounds = 99999})
  local chest = entity("wooden-chest")
  local friendly_rows, plain_rows = 0, 0
  for n = 1, 200 do
    local t = n * (GAP + 60)
    game.tick = t
    attack.fired(j, t)
    attack.fired(k, t)
    game.tick = t + 15
    hit(j, chest)                                -- confirmed, inside the hold
    game.tick = t + HOLD
    attack.deliver_due(t + HOLD)
    local a, b = lines_said(j), lines_said(k)
    if SUB[a[#a]] == "friendly" then friendly_rows = friendly_rows + 1 end
    if SUB[b[#b]] == "friendly" then plain_rows = plain_rows + 1 end
  end
  assert(#lines_said(j) == 200 and #lines_said(k) == 200, "one line per burst each")
  assert(friendly_rows > 0, "no friendly row in 200 friendly bursts")
  assert(plain_rows == 0, "a friendly row with no friendly fire: " .. plain_rows)
end)

test("a squad-mate's splash is `self`: no complaint from him, no apology from the shooter", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  local k = entity(C.name)
  local b = entity(C.beached)
  local rival = entity(C.name, {force = 2})
  attack.fired(j, 0)
  game.tick = 15
  assert(hit(j, k, 0.04) == "self", "a Jamal burning another of his side")
  assert(hit(j, b, 0.04) == "self", "... any body of him")
  assert(hit(j, rival, 0.04) == nil, "a Jamal of another force is an enemy, not a squad-mate")
  assert(not attack.state(j).friendly, "a buddy's 0.04 turned on the apology rows")
  run(j, 16, HOLD + 15)
  assert(last_line(j).cond == nil, "rolled under friendly off a squad-mate")
end)

test("fire he left behind, with no burst open, counts for nothing", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  local chest = entity("wooden-chest")
  assert(hit(j, chest) == "friendly")
  assert(speech.record(j, false) == nil, "a hit with no burst made a record")
  game.tick = 30
  attack.fired(j, 30)
  run(j, 31, 600)                                -- said; the poll at 600 is 570 in: still open
  game.tick = 635                                -- quiet a gap, the closing poll (660) not yet
  hit(j, chest)
  assert(not attack.state(j).friendly, "a hit a whole gap after the gun went quiet counted")
  run(j, 636, GAP + 120)
  local n = #said
  game.tick = GAP + 150                          -- a burning chest, the burst closed
  hit(j, chest)
  assert(attack.state(j) == nil and #said == n, "a closed burst reopened or spoke on a hit")
end)

test("what does NOT count: himself, another force, a hit for 0, not fire, not his", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  local beached = entity(C.beached, {rounds = 5000})
  local enemy = entity("small-biter", {force = 2})
  local chest = entity("wooden-chest")
  local tank = entity("tank")
  attack.fired(beached, 0)
  assert(hit(j, j) == "self", "his own splash is `self`")
  assert(hit(j, enemy) == nil, "an enemy is not friendly")
  assert(hit(j, chest, 0) == nil, "a wall's 0 is no damage")
  assert(hit(j, chest, 5, {name = "physical"}) == nil, "only his fire")
  assert(hit(tank, chest) == nil, "another vehicle's fire is not his")
  assert(attack.fired(tank, 0) == nil and speech.record(tank, false) == nil,
         "a tank's stream start makes no record")
  assert(#said == 0 and speech.record(j, false) == nil, "none of it said or kept anything")
  assert(hit(beached, chest) == "friendly" and attack.state(beached).friendly,
         "every body of his counts")
end)

test("the burst rides a body swap with his speech record", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  attack.fired(j, 0)
  local b = entity(C.beached, {rounds = 5000})
  speech.transfer(j.unit_number, b)
  j.valid = false
  game.tick = 100
  attack.fired(b, 100)
  assert(#lines_said() == 1, "same burst on the new body: " .. #lines_said())
  assert(attack.state(b).open)
end)

test("a dead entity's state is skipped by both clocks, not read", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  attack.fired(j, 0)
  j.valid = false
  j.get_inventory = function() error("read an invalid entity") end
  run(nil, 1, 180)
  assert(#said == 0, "a line for a dead Jamal")
end)

-- THE DAMAGE FILTER --------------------------------------------------------------------------

---What the engine holds for on_entity_damaged: the main chunk's narrow, then each set.
local function current()
  local f = NARROW
  for _, s in ipairs(set_filters) do
    assert(s[1] == defines.events.on_entity_damaged, "a filter set on " .. tostring(s[1]))
    f = s[2]
  end
  return f
end

test("the narrow filter is his bodies alone; the wide one adds fire that did damage", function()
  local names, fire, skip, damage = {}, false, {}, false
  for _, x in ipairs(NARROW) do
    assert(x.filter == "name", "the narrow filter hears more than his bodies: " .. x.filter)
  end
  for i, x in ipairs(WIDE) do
    if x.filter == "name" then
      assert(i == 1 or x.mode == nil or x.mode == "or", "a name filter ANDed: " .. i)
      names[x.name] = true
    elseif x.filter == "damage-type" then
      fire = x.type == "fire" and (x.mode or "or") == "or"
    elseif x.filter == "type" then
      assert(x.invert == true and x.mode == "and", "type filter " .. x.type .. " is not AND NOT")
      skip[x.type] = true
    elseif x.filter == "final-damage-amount" then
      assert(x.comparison == ">" and x.value == 0 and x.mode == "and")
      damage = true
    end
  end
  assert(names[C.name] and names[C.beached] and names[C.airborne], "a body is missing")
  assert(fire, "no fire clause")
  assert(damage, "no final-damage-amount > 0 clause: a wall's 0 would reach Lua")
  for _, t in ipairs({"unit", "unit-spawner", "turret", "tree"}) do
    assert(skip[t], t .. " is not excluded")
  end
  assert(not skip.character and not skip["spider-vehicle"], "a friendly-fire target is excluded")
end)

test("the fire half is registered ONLY while some burst is open (no Jamal firing costs nothing)", function()
  start{}
  local j, k = entity(C.name, {rounds = 5000}), entity(C.name, {rounds = 5000})
  run(nil, 1, 120)
  assert(#set_filters == 0 and current() == NARROW, "widened with nobody firing")
  game.tick = 200
  attack.fired(j, 200)
  assert(current() == WIDE and #set_filters == 1, "a burst opened and the fire half is not there")
  attack.fired(k, 200)
  attack.fired(j, 201)
  assert(#set_filters == 1, "re-registered for a burst already covered: " .. #set_filters)
  game.tick = 500
  attack.fired(k, 500)                           -- k fires on after j goes quiet
  run(nil, 201, 200 + GAP + 60)
  assert(attack.state(j) == nil and attack.state(k) ~= nil and current() == WIDE,
         "narrowed while k still had a burst open")
  run(nil, 200 + GAP + 61, 500 + GAP + 60)
  assert(attack.state(k) == nil and current() == NARROW and #set_filters == 2,
         "the last burst closed and the fire half stayed: " .. #set_filters)
end)

test("on_load derives exactly the host's filter, at every tick of a fight (a joining client)", function()
  start{}
  local j = entity(C.name, {rounds = 5000})
  local t = 0
  local function client_agrees()
    local host, n = current(), #set_filters
    attack.derive()                                -- the client's on_load, over the same storage
    local client = #set_filters > n and set_filters[#set_filters][2] or NARROW
    for i = #set_filters, n + 1, -1 do set_filters[i] = nil end
    assert(client == host, "tick " .. t .. ": the client derived a different filter")
  end
  client_agrees()
  for step = 1, 3 do
    t = step * 2000
    game.tick = t
    attack.fired(j, t)
    client_agrees()
    for u = t + 15, t + GAP + 60, 15 do
      game.tick = u
      attack.deliver_due(u)
      if u % 60 == 0 then attack.poll(u) end
      client_agrees()
    end
  end
  -- ... and the entity dying mid-burst (speech.forget) leaves the host wide until the poll
  game.tick = 9000
  attack.fired(j, 9000)
  speech.forget(j.unit_number)
  client_agrees()
  game.tick = 9060
  attack.poll(9060)
  assert(current() == NARROW, "a forgotten burst kept the fire half")
  client_agrees()
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
