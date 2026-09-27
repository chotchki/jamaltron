-- The break and the repair (PLAN E.4, E.5): scripts/breakage.lua's decisions, under plain lua,
-- over the REAL speech.lua (so R4, the fork, legs_break.18's skipped flop and the ambient
-- cooldown are the real ones) with FAKE entities, a fake force that keeps its alerts, and a FAKE
-- swap that moves the speech record the way D.4's does. What the engine does with an alert, a
-- repair pack or a real swap is the harness's and play.sh's, not this file's.
--
--   lua tools/tests/lua/test_breakage.lua <repo root>
--
-- Run by tools/tests/test_speech_lua.py, in test_pick.lua's harness shape; Lua 5.2 / 5.4+ / luajit.

local root = arg[1] or "."
package.path = root .. "/mod/jamaltron/?.lua;" .. package.path

local C = require("prototypes.shared")

defines = {direction = {north = 0, northnortheast = 1, northeast = 2, eastnortheast = 3,
  east = 4, eastsoutheast = 5, southeast = 6, southsoutheast = 7, south = 8,
  southsouthwest = 9, southwest = 10, westsouthwest = 11, west = 12, westnorthwest = 13,
  northwest = 14, northnorthwest = 15},
  alert_type = {custom = 1}}
prototypes = {entity = {[C.beached] = {}}}

local real_random = math.random
local draws = {}                     -- every math.random(a, b) call: the break roll's shape
---Pin the dice: `roll` answers math.random(1, 100), `float` math.random(); the picker's
---math.random(n) stays really random (seeded), so no test leans on which line he picks.
local function dice(t)
  math.random = function(a, b)
    if b then
      draws[#draws + 1] = {a, b}
      return t.roll or real_random(a, b)
    elseif a then
      return real_random(a)
    end
    return t.float or 0.5
  end
end

local function reset(opts)
  opts = opts or {}
  storage = {}
  draws = {}
  game = {tick = 0, connected_players = {}, print = function() end, surfaces = {}}
  settings = {startup = {["jamaltron-jump-enabled"] = {value = opts.jumping ~= false}}, global = {
    ["jamaltron-verbosity"] = {value = opts.verbosity or "normal"},
    ["jamaltron-speech-cooldown"] = {value = opts.cooldown or 10},
    ["jamaltron-leg-break-percent"] = {value = opts.percent or 25},
    ["jamaltron-apology-interval"] = {value = opts.interval or 15},
    ["jamaltron-max-bubbles"] = {value = opts.cap or 20}}}
  script = {register_on_object_destroyed = function() end}
  rendering = {draw_text = function()
    local r = {valid = true}
    r.destroy = function() r.valid = false end
    return r
  end}
  log = function() end
  math.randomseed(7)
  dice{}
end
reset()

local speech = require("scripts.speech")
local lines = require("scripts.lines")

-- A world: one surface, one force, and every alert the force holds.
local SURFACE = {valid = true}
SURFACE.create_entity = function(p)
  local b = {valid = true, name = p.name}
  b.destroy = function() b.valid = false end
  return b
end
local FORCE = {valid = true, alerts = {}, adds = 0}
FORCE.add_custom_alert = function(entity, icon, message, show_on_map)
  FORCE.adds = FORCE.adds + 1
  FORCE.alerts[#FORCE.alerts + 1] = {entity = entity, surface = entity.surface,
    x = entity.position.x, y = entity.position.y, icon = icon, message = message, show = show_on_map}
end
-- Where the engine keeps an alert is unmeasured: FORCE.live models one that follows its entity,
-- the default one that stays where it was added.
FORCE.remove_alert = function(f)
  assert(f.entity == nil or f.entity.valid, "remove_alert by an invalid entity is an engine error")
  local keep = {}
  for _, a in ipairs(FORCE.alerts) do
    local x, y = a.x, a.y
    if FORCE.live then x, y = a.entity.position.x, a.entity.position.y end
    local hit = (f.entity == nil or a.entity == f.entity)
      and (f.surface == nil or a.surface == f.surface)
      and (f.position == nil or (x == f.position.x and y == f.position.y))
      and (f.icon == nil or (a.icon.name == f.icon.name and a.icon.type == f.icon.type))
    if not hit then keep[#keep + 1] = a end
  end
  FORCE.alerts = keep
end
local function alerts_on(entity)
  local n = 0
  for _, a in ipairs(FORCE.alerts) do if a.entity == entity then n = n + 1 end end
  return n
end

local next_unit = 100
---A fake body. damage() THROWS: the thud must be a written health (it raises no event).
local function body(name, opts)
  opts = opts or {}
  next_unit = next_unit + 1
  local e = {name = name, valid = true, unit_number = next_unit, force = FORCE, surface = SURFACE,
             position = opts.position or {x = next_unit, y = 0}, max_health = opts.max or 3000}
  e.health = (opts.ratio or 1) * e.max_health
  e.get_health_ratio = function() return e.health / e.max_health end
  e.get_driver = function() return nil end
  e.get_passenger = function() return nil end
  e.damage = function() error("damage() raises on_entity_damaged: a second line on the landing") end
  return e
end

-- The fake swap: a new body where opts.position says, the health RATIO carried, the speech
-- record moved (speech.transfer, as D.4's move_all does), the old body gone. `fail[name]` makes
-- a swap into that body "failed" (old untouched) or "lost" (both gone).
local swaps, fail = {}, {}
local fake_swap = {}
function fake_swap.replace(old, name, opts)
  opts = opts or {}
  swaps[#swaps + 1] = {old = old, name = name, opts = opts}
  if not old.valid then return nil, "refused" end
  if fail[name] == "failed" then return nil, "failed" end
  if fail[name] == "lost" then
    old.valid = false
    return nil, "lost"
  end
  local new = body(name, {position = opts.position or old.position, max = old.max_health,
                          ratio = old.health / old.max_health})
  speech.transfer(old.unit_number, new)
  old.valid = false
  return new, "ok"
end
package.loaded["scripts.swap"] = fake_swap

-- Every say(), with what it returned: the spy sits on the module table breakage calls through.
local said = {}
local real_say = speech.say
speech.say = function(entity, key, cond)
  local id = real_say(entity, key, cond)
  said[#said + 1] = {entity = entity, key = key, cond = cond, id = id, tick = game.tick}
  return id
end

-- A FAKE wreck (D.1.3): the real one lays his broken legs off math.random, which the dice above
-- would count as break rolls (and answer with a pinned roll). What it draws is test_wreck.lua's;
-- here only WHEN - on every way a body becomes beached, once per body. Same contract as the real
-- ensure(): draw unless the record already holds legs drawn on THIS body.
local wrecks = {}                    -- every ensure(): {entity, drew}
local cleared = 0                    -- every clear(): a record's legs taken down
package.loaded["scripts.wreck"] = {
  ensure = function(rec, entity)
    local drew = not (rec.wreck and rec.wreck.unit == entity.unit_number)
    if drew then rec.wreck = {unit = entity.unit_number, objects = {}} end
    wrecks[#wrecks + 1] = {entity = entity, drew = drew}
    return drew
  end,
  clear = function(rec)
    if rec.wreck then cleared = cleared + 1 end
    rec.wreck = nil
  end,
  drawn = function(rec, entity)
    return rec.wreck ~= nil and rec.wreck.unit == entity.unit_number
  end,
}
local function drawn_on(entity)
  local n = 0
  for _, w in ipairs(wrecks) do if w.entity == entity and w.drew then n = n + 1 end end
  return n
end

local breakage = require("scripts.breakage")

local SUB, lines_ch = {}, {}
for _, pool in pairs(lines.pools) do
  for _, row in ipairs(pool.rows) do SUB[row.id], lines_ch[row.id] = row.sub or "-", row.ch end
end

local function start(opts)
  reset(opts)
  swaps, fail, said, wrecks = {}, {}, {}, {}
  FORCE.alerts, FORCE.adds = {}, 0
  next_unit = 100
end

---An airborne Jamal with a speech record (he has been talking), at `ratio` health.
local function airborne(ratio)
  local a = body(C.airborne, {ratio = ratio})
  speech.record(a, true)
  return a
end

local function said_by(key)
  local out = {}
  for _, s in ipairs(said) do if key == nil or s.key == key then out[#out + 1] = s end end
  return out
end

local function show(list)
  local out = {}
  for _, s in ipairs(list) do
    out[#out + 1] = s.key .. "/" .. tostring(s.cond) .. "=" .. tostring(s.id) .. "@" .. s.tick
  end
  return table.concat(out, ",")
end

local function near(a, b) return math.abs(a - b) < 1e-9 end

---Land an airborne Jamal at `spot` with the dice pinned; returns the body and outcome.
local function land(ratio, d, info)
  dice(d or {})
  local a = airborne(ratio)
  local e, outcome = breakage.on_landing(a, {x = 8, y = 3}, info or {distance = 8})
  return e, outcome, a
end

---A broken landing at tick t (100%), with legs_break.18's skipped flop cleared unless `keep18`,
---so a test of the timer is not a test of which legs_break row the dice picked.
local function broken_at(t, keep18)
  game.tick = t
  settings.global["jamaltron-leg-break-percent"].value = 100
  local e = land(1, {float = 0.5})
  if not keep18 then speech.record(e, false).skip_flops = 0 end
  return e
end

---The slow clock from tick `from` to `to`, as control.lua runs it: chains every 15, poll every 60.
local function run(from, to)
  for t = from, to, 15 do
    game.tick = t
    speech.deliver_due(t)
    if t % 60 == 0 then breakage.poll(t) end
  end
end

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end

-- ---------------------------------------------------------------------------------------

test("0%: every landing is clean - one swap to the vehicle at the spot, land/held on the body it returned", function()
  start{percent = 0}
  for _ = 1, 50 do
    swaps, said = {}, {}
    local e, outcome, a = land(1, {roll = 1})
    assert(outcome == "held" and e and e.valid and e.name == C.name, tostring(outcome))
    assert(#swaps == 1 and swaps[1].old == a and swaps[1].name == C.name
           and swaps[1].opts.reason == "landing" and swaps[1].opts.position.x == 8, #swaps)
    assert(#said == 1 and said[1].entity == e and said[1].key == "land" and said[1].cond == "held",
           show(said))
    assert(said[1].id == nil or SUB[said[1].id] == "any" or SUB[said[1].id] == "held", said[1].id)
    assert(not breakage.state(e).kept, "a clean landing keeps no beached record")
  end
  assert(#draws == 0, "0% draws no break roll")
  assert(#FORCE.alerts == 0)
end)

test("100%: every landing breaks - ONE swap straight to beached, legs_break/self on it, land never (R4)", function()
  start{percent = 100}
  for i = 1, 30 do
    swaps, said = {}, {}
    local e, outcome, a = land(1, {roll = 100})
    assert(outcome == "broke" and e and e.valid and e.name == C.beached, tostring(outcome))
    assert(not a.valid, "the airborne body is gone")
    assert(#swaps == 1 and swaps[1].name == C.beached and swaps[1].opts.reason == "break"
           and swaps[1].opts.position.x == 8 and swaps[1].opts.position.y == 3, "one swap, not two")
    assert(#said == 1 and said[1].entity == e and said[1].key == "legs_break" and said[1].cond == "self",
           show(said))
    assert(said[1].id and SUB[said[1].id] == "self", tostring(said[1].id))
    local st = speech.state(e)
    assert(st.fork == "self" and st.breaks == 1, "the fork every flop reads, and {N}")
    assert(breakage.state(e).kept and breakage.state(e).beached == i)
  end
  assert(#draws == 0, "100% draws no break roll")
end)

test("the roll: math.random(1, 100) <= jamaltron-leg-break-percent - 25 breaks at 25%, 26 does not", function()
  start{percent = 25}
  local _, outcome = land(1, {roll = 25})
  assert(outcome == "broke", outcome)
  assert(#draws == 1 and draws[1][1] == 1 and draws[1][2] == 100, "one d100 per landing")
  _, outcome = land(1, {roll = 26})
  assert(outcome == "held", outcome)
  _, outcome = land(1, {roll = 1})
  assert(outcome == "broke", outcome)
end)

test("the thud: 1-3% of max health on a clean landing at 8 tiles, linear in the jump's distance, written", function()
  start{percent = 0}
  local cases = {
    {float = 0, info = {distance = 8}, ratio = 0.99},
    {float = 1, info = {distance = 8}, ratio = 0.97},
    {float = 0.5, info = {distance = 16}, ratio = 0.96},
    {float = 0.5, info = {distance = 4}, ratio = 0.99},
    {float = 0.5, info = {}, ratio = 0.98},              -- no distance: the setting's default
  }
  for i, c in ipairs(cases) do
    local e = land(1, {float = c.float}, c.info)
    assert(near(e.get_health_ratio(), c.ratio), i .. ": " .. e.get_health_ratio())
  end
  local e = breakage.on_landing(airborne(1), nil, nil)   -- no spot, no info: the swap's own position
  assert(e and near(e.get_health_ratio(), 0.98))
end)

test("a break leaves at most half health: exactly 0.5 from full, and the thud off anything under it", function()
  start{percent = 100}
  local e = land(1, {float = 0.5})
  assert(near(e.get_health_ratio(), 0.5), e.get_health_ratio())
  e = land(0.6, {float = 0.5})
  assert(near(e.get_health_ratio(), 0.5), e.get_health_ratio())
  e = land(0.4, {float = 0.5})
  assert(near(e.get_health_ratio(), 0.38), e.get_health_ratio())
  e = land(1, {float = 0.5}, {distance = 20})
  assert(near(e.get_health_ratio(), 0.5), "a long jump still stops at half")
end)

test("the floor: no landing takes him under 5% or kills him, and none heals him already under it", function()
  for _, percent in ipairs({0, 100}) do
    start{percent = percent}
    local e = land(0.06, {float = 1})                    -- 0.06 - 0.03 would be 0.03
    assert(near(e.get_health_ratio(), 0.05), percent .. ": " .. e.get_health_ratio())
    e = land(0.03, {float = 1})
    assert(near(e.get_health_ratio(), 0.03), percent .. ": healed or hurt under the floor")
    e = land(0.001, {float = 1}, {distance = 20})
    assert(e.health > 0, "a written 0 is an unattackable shark, not a dead one")
  end
end)

test("a break whose swap fails lands him clean instead; both failing leaves him airborne and silent", function()
  start{percent = 100}
  fail[C.beached] = "failed"
  local e, outcome, a = land(1, {float = 0.5})
  assert(outcome == "held" and e.name == C.name and not a.valid, tostring(outcome))
  assert(#swaps == 2 and swaps[1].name == C.beached and swaps[2].name == C.name)
  assert(near(e.get_health_ratio(), 0.98), "no break ceiling on a landing that did not break")
  assert(#said == 1 and said[1].key == "land" and said[1].cond == "held", show(said))
  assert(not breakage.state(e).kept and #FORCE.alerts == 0)

  swaps, said = {}, {}
  fail[C.name] = "failed"
  e, outcome, a = land(1, {float = 0.5})
  assert(e == nil and outcome == "failed" and a.valid and a.name == C.airborne, tostring(outcome))
  assert(#said == 0 and breakage.state(a).beached == 0 and #FORCE.alerts == 0)

  swaps, said, fail = {}, {}, {[C.beached] = "lost"}
  e, outcome, a = land(1, {float = 0.5})
  assert(e == nil and outcome == "lost" and not a.valid and #swaps == 1, tostring(outcome))
  assert(#said == 0)

  e, outcome = breakage.on_landing(a, {x = 0, y = 0}, {})
  assert(e == nil and outcome == "refused", "an invalid airborne body")
end)

test("beached: his alert is up at once, on him, on the map, with his icon and the status wording", function()
  start{}
  local e = broken_at(600)
  assert(#FORCE.alerts == 1 and alerts_on(e) == 1)
  local a = FORCE.alerts[1]
  assert(a.show == true and a.icon.type == "item" and a.icon.name == C.name, "show_on_map, his icon")
  assert(a.message[1] == "jamaltron-status.beached", tostring(a.message[1]))
end)

test("the apology interval per verbosity: 30 / 15 / 7.5 s at 15 s, +-20% jitter, from the break", function()
  local want = {quiet = 1800, normal = 900, unbearable = 450}
  for verbosity, ticks in pairs(want) do
    start{verbosity = verbosity}
    local e = broken_at(600)
    assert(breakage.state(e).flop_at == 600 + ticks, verbosity .. ": " .. breakage.state(e).flop_at)
  end
  start{interval = 20}
  assert(breakage.state(broken_at(600)).flop_at == 600 + 1200, "the setting is the base")
  for float, ticks in pairs({[0] = 720, [1] = 1080}) do
    start{}
    game.tick = 600
    settings.global["jamaltron-leg-break-percent"].value = 100
    local e = land(1, {float = float})
    assert(breakage.state(e).flop_at == 600 + ticks, float .. ": " .. breakage.state(e).flop_at)
  end
end)

test("flops: nothing before the due poll, `flopping` on it with the break's fork, then one interval on", function()
  start{}
  local e = broken_at(60)
  said = {}
  run(75, 945)
  assert(#said_by("flopping") == 0, show(said))
  run(960, 960)
  local flops = said_by("flopping")
  assert(#flops == 1 and flops[1].entity == e and flops[1].id, show(said))
  assert(breakage.state(e).flop_at == 960 + 900, breakage.state(e).flop_at)
  run(975, 60 * 60 * 20)                                 -- twenty minutes of it
  flops = said_by("flopping")
  assert(#flops >= 75, "#" .. #flops)
  for _, f in ipairs(flops) do
    assert(f.cond == nil and f.id and SUB[f.id] ~= "external", "the external fork leaked: " .. tostring(f.id))
  end
end)

test("unbearable at the 10 s cooldown flops every 10 s, not every 15: a flop inside it waits for it", function()
  start{verbosity = "unbearable"}
  local e = broken_at(60)                               -- legs_break at 60 starts the cooldown
  said = {}
  run(75, 60 * 60 * 5)
  local flops = said_by("flopping")
  assert(#flops > 20 and flops[1].tick == 660, show(flops))  -- due 510, the cooldown ends at 660
  for i = 2, #flops do
    assert(flops[i].tick - flops[i - 1].tick == 600, show(flops))
  end
  assert(speech.state(e).fork == "self")
end)

test("another line's cooldown moves the flop to its end, not a whole interval on", function()
  start{}
  local e = broken_at(60)
  said = {}
  run(75, 900)
  game.tick = 900
  assert(speech.say(e, "damaged"), "a biter, 1 s before the flop is due")
  run(915, 1560)
  local flops = said_by("flopping")
  assert(#flops == 1 and flops[1].tick == 1500, show(said))  -- 900 + the 10 s cooldown
end)

test("at the bubble cap a due flop waits for the next free slot, like the cooldown - no lost interval", function()
  start{cap = 1}
  local e = broken_at(60)                               -- due 960; his own break bubble gone by 389
  local other = body(C.name)
  game.tick = 900
  assert(speech.say(other, "command_done"), "chatter elsewhere, standing until 900 + 300 + 29")
  said = {}
  run(915, 1215)
  assert(#said_by("flopping") == 0, "a capped flop rolled: " .. show(said))
  assert(breakage.state(e).flop_at == 1229, breakage.state(e).flop_at)
  run(1230, 1320)
  local flops = said_by("flopping")
  assert(#flops == 1 and flops[1].id and flops[1].tick == 1260, show(flops))  -- the next poll
  assert(breakage.state(e).flop_at == 2160, "the next one an interval after it SPOKE")
end)

test("more beached than the cap: the waiters are served oldest first, and none of them starves", function()
  start{cap = 3}
  local sharks = {}
  for i = 1, 12 do sharks[i] = broken_at(60 + 15 * i) end   -- due 975..1140, apart by less than a poll
  said = {}
  run(195, 30000)
  local lines_of = {}
  for _, s in ipairs(said) do
    if s.key == "flopping" and s.id then lines_of[s.entity] = (lines_of[s.entity] or 0) + 1 end
  end
  local least, most = math.huge, 0
  for i, e in ipairs(sharks) do
    local n = lines_of[e] or 0
    least, most = math.min(least, n), math.max(most, n)
    assert(n > 0, "shark " .. i .. " never apologized")
  end
  -- a flopping.23 (narration) takes no slot, so the lucky get a line or two extra
  assert(most - least <= 4, "the slots did not go round: " .. least .. ".." .. most)
end)

test("the queue is by when the flop came due, not by unit: a later-due lower unit waits its turn", function()
  start{cap = 1}
  local late = broken_at(60)                             -- the LOWER unit, due 960
  local early = broken_at(45)                            -- due 945: same poll, 15 ticks older
  local other = body(C.name)
  game.tick = 900
  assert(speech.say(other, "command_done"))              -- the one slot, until 1229
  said = {}
  run(915, 1320)
  local flops = said_by("flopping")
  assert(flops[1] and flops[1].entity == early and flops[1].tick == 1260, show(flops))
  if lines_ch[flops[1].id] == "narration" then       -- flopping.23: no bubble, so no slot taken
    assert(#flops == 2 and flops[2].entity == late and flops[2].tick == 1260, show(flops))
  else
    assert(#flops == 1, show(flops))
    assert(breakage.state(late).flop_at == 1260 + speech.SHOW_TICKS + speech.FADE_TICKS,
           "the other still waits for the NEXT slot: " .. breakage.state(late).flop_at)
  end
end)

test("legs_break.18's skipped flop costs the whole interval, never a one-second retry", function()
  start{}
  local e = broken_at(60)
  speech.record(e, false).skip_flops = 1                -- as though .18 was the row
  said = {}
  run(75, 960)
  assert(#said_by("flopping") == 1 and said_by("flopping")[1].id == nil, show(said))
  assert(breakage.state(e).flop_at == 1860, breakage.state(e).flop_at)
  run(975, 1860)
  local flops = said_by("flopping")
  assert(#flops == 2 and flops[2].id and flops[2].tick == 1860, show(flops))
end)

test("repair pack: nothing below full health; at full ONE swap to the vehicle, `repaired` on it, all cleared", function()
  start{}
  local e = broken_at(60)
  swaps, said = {}, {}
  e.health = 0.99 * e.max_health
  breakage.on_repaired{entity = e, tick = 120}
  assert(#swaps == 0 and #said == 0 and breakage.state(e).kept, "not yet")
  e.health = e.max_health
  game.tick = 180
  breakage.on_repaired{entity = e, tick = 180}
  assert(#swaps == 1 and swaps[1].old == e and swaps[1].name == C.name and swaps[1].opts.reason == "repair")
  local up = said[1] and said[1].entity
  assert(#said == 1 and said[1].key == "repaired" and up and up.valid and up.name == C.name, show(said))
  assert(breakage.state(e).beached == 0 and #FORCE.alerts == 0, "record and alert gone")
  assert(speech.state(up).fork == nil and speech.state(up).breaks == 1, "fork cleared, {N} kept")
  run(240, 60 * 60)
  assert(#said_by("flopping") == 0 and #swaps == 1, "a repaired Jamal neither flops nor gets up twice")

  local walker = body(C.name)
  breakage.on_repaired{entity = walker, tick = 200}
  assert(#swaps == 1, "only a beached body gets up")
end)

test("bots: the 60-tick poll stands him up at full health, and does not flop him on that poll", function()
  start{}
  local e = broken_at(60)
  swaps, said = {}, {}
  run(75, 900)
  e.health = e.max_health                               -- construction bots: no repair event
  run(915, 960)                                         -- 960 is also the flop's due poll
  assert(#swaps == 1 and swaps[1].name == C.name and swaps[1].opts.reason == "repair")
  assert(#said == 1 and said[1].key == "repaired", show(said))
  assert(breakage.state(e).beached == 0 and #FORCE.alerts == 0)
end)

test("a record-less beached body at full health gets up on a repair event (a playtest swap)", function()
  start{}
  local e = body(C.beached)
  breakage.on_repaired{entity = e, tick = 60}
  assert(#swaps == 1 and swaps[1].name == C.name and #said == 1 and said[1].key == "repaired")
  assert(breakage.state(e).beached == 0 and #FORCE.alerts == 0)
end)

test("a repair swap that fails leaves him beached, alerted once, and retried on the next poll", function()
  start{}
  local e = broken_at(60)
  e.health = e.max_health
  fail[C.name] = "failed"
  swaps, said = {}, {}
  run(120, 120)
  assert(#swaps == 1 and e.valid and breakage.state(e).kept and alerts_on(e) == 1 and #said == 0)
  fail = {}
  run(135, 180)
  assert(#swaps == 2 and not e.valid and #said == 1 and said[1].key == "repaired")
  assert(breakage.state(e).beached == 0 and #FORCE.alerts == 0)
end)

test("a lost repair swap: the record goes on the next poll, nobody left to repair", function()
  start{}
  local e = broken_at(60)
  e.health = e.max_health
  fail[C.name] = "lost"
  said = {}
  run(120, 300)
  assert(not e.valid and breakage.state(e).beached == 0 and #said == 0)
end)

test("the alert is re-issued once he has settled, then every 10 s, and never stacks", function()
  start{}
  local e = broken_at(60)
  local settled = 60 + breakage.SETTLE_TICKS
  for t = 75, 60 * 70, 15 do
    run(t, t)
    assert(alerts_on(e) == 1, "tick " .. t .. ": " .. alerts_on(e))
  end
  assert(FORCE.adds == 2 + math.floor((60 * 70 - settled) / 600), "adds " .. FORCE.adds)
end)

test("a body that settles after the break: alert and by-place removal both follow him (either alert model)", function()
  for _, live in ipairs({false, true}) do
    start{}
    FORCE.live = live
    local e = broken_at(60)
    assert(breakage.state(e).alert_at == 60 + breakage.SETTLE_TICKS, "the first re-issue waits for him to settle")
    e.position = {x = e.position.x + 1.5, y = e.position.y}  -- his legs re-laid beside the water (measured)
    run(75, 60 + breakage.SETTLE_TICKS)
    assert(breakage.state(e).alert_at == 60 + breakage.SETTLE_TICKS + breakage.ALERT_TICKS)
    e.valid = false                                          -- killed where he settled
    breakage.forget(e.unit_number)
    assert(#FORCE.alerts == 0, (live and "live" or "added-at") .. ": the alert outlived him")
    FORCE.live = nil
  end
end)

test("keep: a beached body made any other way is kept - half health, alert, fork self, flops, up at full", function()
  start{}
  game.tick = 600
  local e = body(C.beached)                                 -- a bare swap: full health, no record
  assert(not breakage.state(e).kept)
  assert(breakage.keep(e) == true)
  assert(breakage.state(e).kept and near(e.get_health_ratio(), 0.5), "capped at half: " .. e.get_health_ratio())
  assert(alerts_on(e) == 1 and speech.state(e).fork == "self" and speech.state(e).breaks == 0,
         "alerted, the default fork, and no break he did not have")
  e.health = 0.7 * e.max_health                              -- a pack's worth of repair
  assert(breakage.keep(e) and near(e.get_health_ratio(), 0.7), "keeping a kept one never re-caps him")
  assert(alerts_on(e) == 1, "nor stacks his alert")
  said = {}
  run(615, 600 + 1200)
  assert(#said_by("flopping") >= 1 and said_by("flopping")[1].entity == e, show(said))
  e.health = e.max_health
  run(1815, 1860)
  assert(#swaps == 1 and swaps[1].name == C.name and #said_by("repaired") == 1, "up at full on the poll")

  local low = body(C.beached, {ratio = 0.2})
  assert(breakage.keep(low) and near(low.get_health_ratio(), 0.2), "never healed")
  local ext = body(C.beached)
  speech.record(ext, true)
  speech.set_fork(ext, "external")
  assert(breakage.keep(ext) and speech.state(ext).fork == "external", "a fork already stamped stays")
  assert(breakage.keep(body(C.name)) == false and breakage.keep(nil) == false, "only a beached body")
  local gone = body(C.beached)
  gone.valid = false
  assert(breakage.keep(gone) == false)
end)

test("cleanup: a dead or destroyed beached body's record goes, and its alert with it, by place", function()
  start{}
  local e = broken_at(60)
  local f = broken_at(60)                               -- the same landing spot as e
  local g = body(C.beached, {ratio = 0.5, position = {x = 30, y = 30}})
  game.surfaces = {{find_entities_filtered = function() return {g} end}}
  breakage.adopt_all()
  assert(breakage.state(e).beached == 3 and #FORCE.alerts == 3)
  e.valid = false                                       -- died: on_object_destroyed, end of tick
  breakage.forget(e.unit_number)
  assert(breakage.state(f).beached == 2 and alerts_on(e) == 0 and alerts_on(g) == 1)
  run(120, 120)
  assert(alerts_on(f) == 1, "the neighbour on the same spot lost its alert to the by-place remove")
  breakage.forget(e.unit_number)                        -- twice, and an unknown unit: harmless
  breakage.forget(99999)
  f.valid, g.valid = false, false                       -- and the poll meets them first
  said = {}
  run(135, 1200)
  assert(breakage.state(nil).beached == 0 and #FORCE.alerts == 0 and #said == 0, show(said))
  storage = {}
  breakage.forget(1)                                    -- a save with no breakage yet
end)

test("another mod's swap: the record follows him; in a body that is not beached he waits, then resumes", function()
  start{}
  local e = broken_at(60)
  local dummy = body("some-other-mods-dummy", {ratio = 1})
  speech.transfer(e.unit_number, dummy)                 -- control.lua's replaced handler
  breakage.transfer(e.unit_number, dummy)
  e.valid = false
  assert(breakage.state(dummy).kept and #FORCE.alerts == 0, "alert down, record kept")
  swaps, said = {}, {}
  run(75, 60 * 60)
  assert(#swaps == 0 and #said_by("flopping") == 0, "a full-health dummy is not a repair")
  local back = body(C.beached, {ratio = 0.5})
  speech.transfer(dummy.unit_number, back)
  breakage.transfer(dummy.unit_number, back)
  dummy.valid = false
  assert(breakage.state(back).kept and alerts_on(back) == 1 and breakage.state(nil).beached == 1)
  run(60 * 60 + 15, 60 * 60 * 2)
  assert(#said_by("flopping") >= 1 and said_by("flopping")[1].entity == back)
  breakage.transfer(424242, back)                       -- nobody we keep: nothing moves
  assert(breakage.state(nil).beached == 1)
end)

test("state lives in storage: a reloaded module carries on mid-break", function()
  start{}
  local e = broken_at(60)
  package.loaded["scripts.breakage"] = nil
  local reloaded = require("scripts.breakage")
  said = {}
  game.tick = 960
  reloaded.poll(960)
  assert(#said_by("flopping") == 1, show(said))
  e.health = e.max_health
  reloaded.poll(1020)
  assert(#said_by("repaired") == 1)
  package.loaded["scripts.breakage"] = nil
  breakage = require("scripts.breakage")
end)

test("adopt_all keeps every beached body on the map, once, and leaves a kept one's clock alone", function()
  start{}
  local kept = broken_at(600)
  local due = breakage.state(kept).flop_at
  local a, b = body(C.beached, {ratio = 0.5}), body(C.beached, {ratio = 0.5})
  game.surfaces = {{find_entities_filtered = function(f)
    assert(f.name == C.beached)
    return {a, b, kept}
  end}}
  game.tick = 700
  breakage.adopt_all()
  breakage.adopt_all()
  assert(breakage.state(a).kept and breakage.state(nil).beached == 3)
  assert(alerts_on(a) == 1 and alerts_on(b) == 1 and alerts_on(kept) == 1)
  assert(breakage.state(kept).flop_at == due, "adopt reset a kept Jamal's apology clock")
  prototypes.entity[C.beached] = nil
  storage = {}
  breakage.adopt_all()                                  -- D.1's body not built: nothing to find
  assert(breakage.state(nil).beached == 0)
  prototypes.entity[C.beached] = {}
end)

test("jumping switched off: no landing breaks, even at 100% - no roll drawn, landed clean", function()
  start{percent = 100, jumping = false}
  for _ = 1, 10 do
    swaps, said = {}, {}
    local e, outcome = land(1, {roll = 1})
    assert(outcome == "held" and e.name == C.name, tostring(outcome))
    assert(#swaps == 1 and swaps[1].name == C.name and #said == 1 and said[1].key == "land", show(said))
  end
  assert(#draws == 0 and #FORCE.alerts == 0 and breakage.state(nil).beached == 0)
end)

test("a landing from no height (jump.adopt's stranded body, which never flew) never breaks, even at 100%", function()
  start{percent = 100}
  for _ = 1, 10 do
    swaps, said = {}, {}
    local e, outcome = land(1, {roll = 1}, {tick = 0, height = 0, distance = 0})
    assert(outcome == "held" and e.name == C.name, tostring(outcome))
    assert(#swaps == 1 and swaps[1].name == C.name and #said == 1 and said[1].key == "land", show(said))
    assert(speech.record(e, false).breaks == 0, "a jump nobody made counted toward {N}")
  end
  assert(#draws == 0 and #FORCE.alerts == 0 and breakage.state(nil).beached == 0)
  local e, outcome = land(1, {roll = 1}, {height = 1.5, distance = 8})
  assert(outcome == "broke" and e.name == C.beached, "a real arc still rolls: " .. tostring(outcome))
end)

test("jumping switched off: a Jamal beached before it gets up on the next poll, as he is, no repair needed", function()
  start{}
  local e = broken_at(60)                               -- broke while jumping was on
  local g = body(C.beached, {ratio = 0.3})              -- and one no record kept (adopt_all's)
  game.surfaces = {{find_entities_filtered = function() return {g} end}}
  settings.startup["jamaltron-jump-enabled"].value = false   -- the save loads with it off
  breakage.adopt_all()
  swaps, said = {}, {}
  run(120, 120)
  assert(#swaps == 2 and swaps[1].name == C.name and swaps[2].name == C.name
         and swaps[1].opts.reason == "repair", #swaps)
  assert(#said_by("repaired") == 2 and #said_by("flopping") == 0, show(said))
  local up = said_by("repaired")
  assert(near(up[1].entity.get_health_ratio() + up[2].entity.get_health_ratio(), 0.5 + 0.3),
         "stood up at the health he had, never healed")
  assert(breakage.state(nil).beached == 0 and #FORCE.alerts == 0, "records and alerts gone")
  run(135, 60 * 60)
  assert(#swaps == 2, "nobody gets up twice")
end)

test("his broken legs (D.1.3): drawn on every way in - break, keep, adopt_all, a transfer back - once a body", function()
  start{}
  local e = broken_at(60)
  assert(drawn_on(e) == 1, "a break draws them")
  assert(breakage.keep(e) and drawn_on(e) == 1, "keeping a kept body draws nothing more")
  game.surfaces = {{find_entities_filtered = function() return {e} end}}
  breakage.adopt_all()
  assert(drawn_on(e) == 1 and #wrecks == 3, "adopt_all asks, and draws nothing more")
  settings.global["jamaltron-leg-break-percent"].value = 0
  local clean = land(1)
  assert(clean.name == C.name and drawn_on(clean) == 0, "a clean landing draws none")

  local k = body(C.beached, {ratio = 1})                -- the playtest's bare swap
  assert(breakage.keep(k) and drawn_on(k) == 1, "keep() draws them")
  local g = body(C.beached, {ratio = 0.4})              -- a save from before breakage
  game.surfaces = {{find_entities_filtered = function() return {g} end}}
  breakage.adopt_all()
  assert(drawn_on(g) == 1, "adopt_all draws them on a body it takes in")

  local dummy = body("some-other-mods-dummy", {ratio = 1})
  cleared = 0
  breakage.transfer(e.unit_number, dummy)
  assert(drawn_on(dummy) == 0, "never on another mod's body that is not beached")
  assert(cleared == 1, "the old body's legs come down with the move, whatever that mod does with it")
  local back = body(C.beached, {ratio = 0.5})
  breakage.transfer(dummy.unit_number, back)
  assert(drawn_on(back) == 1, "a transfer back onto a beached body draws them there")
  local again = body(C.beached, {ratio = 0.5})         -- beached straight to beached, old still valid
  breakage.transfer(back.unit_number, again)
  assert(drawn_on(again) == 1, "the old body's legs - still valid this tick - do not stand in for new ones")

  local r = body(C.beached, {ratio = 1})                -- a repair event on a body nobody kept
  breakage.on_repaired({entity = r, tick = 70})
  assert(drawn_on(r) <= 1, "at most once, even on the way straight back up")
end)

test("another mod swaps him onto a beached body we ALREADY keep: one record, one set of legs", function()
  start{}
  local a = broken_at(60)
  local c = body(C.beached, {ratio = 0.5})
  assert(breakage.keep(c) and drawn_on(c) == 1 and breakage.state(nil).beached == 2)
  local legs_on_c = storage.jamaltron.breakage.beached[c.unit_number].wreck
  cleared = 0
  speech.transfer(a.unit_number, c)
  breakage.transfer(a.unit_number, c)
  a.valid = false
  local st = breakage.state(c)
  assert(st.kept and breakage.state(nil).beached == 1, "one record on C, not two")
  assert(drawn_on(c) == 1, "C's legs stand: " .. drawn_on(c) .. " sets drawn on it")
  assert(storage.jamaltron.breakage.beached[c.unit_number].wreck == legs_on_c,
         "the record now on C holds the set already drawn there")
  assert(cleared == 1, "only A's legs came down: " .. cleared)
  assert(alerts_on(c) == 1, "one alert on C: " .. alerts_on(c))
end)

test("a clone of a beached Jamal is kept at the health it was cloned at, his legs drawn on it", function()
  start{}
  local a = broken_at(60)
  local copy = body(C.beached, {ratio = 0.8})           -- the source was part repaired
  breakage.on_cloned({source = a, destination = copy, tick = 61})
  local st = breakage.state(copy)
  assert(st.kept and breakage.state(nil).beached == 2 and drawn_on(copy) == 1, show(st))
  assert(copy.health == 0.8 * copy.max_health, "a clone is not re-broken: " .. copy.health)
  breakage.on_cloned({source = a, destination = body("not-ours", {ratio = 1}), tick = 61})
  assert(breakage.state(nil).beached == 2, "only a beached body is taken")
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
