-- control.lua's WIRING, under plain lua: the real control.lua over fake scripts/ modules and a
-- fake bootstrap, so a lifecycle hook or an event that stops reaching the module that owns it
-- fails here instead of in a playtest. What each module then does is its own suite's.
--
--   lua tools/tests/lua/test_control.lua <repo root>
--
-- Run by tools/tests/test_speech_lua.py, in test_pick.lua's harness shape; Lua 5.2 / 5.4+ / luajit.

local root = arg[1] or "."
package.path = root .. "/mod/jamaltron/?.lua;" .. package.path

local C = require("prototypes.shared")

-- Every call a fake module takes, in order, as "module.fn".
local calls = {}
local function fake(name, fixed)
  return setmetatable(fixed or {}, {__index = function(t, fn)
    local f = function(...)
      calls[#calls + 1] = {call = name .. "." .. fn, args = {...}}
    end
    rawset(t, fn, f)
    return f
  end})
end
local function names()
  local out = {}
  for _, c in ipairs(calls) do out[#out + 1] = c.call end
  return out
end
local function show() return table.concat(names(), " ") end

package.loaded["scripts.speech"] = fake("speech")
package.loaded["scripts.swap"] = fake("swap", {
  bodies = function() return {C.name, C.beached, C.airborne} end,
  swapping = function() return false end,
})
local clock_install = nil
package.loaded["scripts.clock"] = fake("clock", {install = function(derive) clock_install = {derive} end})
package.loaded["scripts.jump"] = fake("jump")
package.loaded["scripts.breakage"] = fake("breakage")
-- D.7: what the fake attack.damaged answers, set per test; what install was handed and returned.
local verdict = nil
local NARROW, installed = {"the narrow filter"}, nil
package.loaded["scripts.attack"] = fake("attack", {
  OURS = {[C.name] = true, [C.beached] = true, [C.airborne] = true},
  damaged = function(event)
    calls[#calls + 1] = {call = "attack.damaged", args = {event}}
    return verdict
  end,
  install = function(ours) installed = ours; return NARROW end,
  derive = function() end,
})

-- An event id is its own name: handlers are keyed by it.
defines = {events = setmetatable({}, {__index = function(_, k) return k end}),
           target_type = {entity = 1, equipment = 2}, gui_type = {none = 0}}
prototypes = {entity = {[C.name] = {}, [C.beached] = {}, [C.airborne] = {}},
              custom_input = {[C.jump.input] = {}}}
local handlers, nth, lifecycle, interfaces, filters = {}, {}, {}, {}, {}
script = {
  on_event = function(id, fn, f) handlers[id] = fn; filters[id] = f end,
  on_nth_tick = function(n, fn) nth[n] = fn end,
  on_init = function(fn) lifecycle.init = fn end,
  on_configuration_changed = function(fn) lifecycle.changed = fn end,
  get_event_handler = function(id) return handlers[id] end,
}
remote = {add_interface = function(name, fns) interfaces[name] = fns end}
game = {tick = 0}

dofile(root .. "/mod/jamaltron/control.lua")

local tests, tnames = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  tnames[#tnames + 1] = name
end
local function has(call)
  for _, c in ipairs(calls) do if c.call == call then return c end end
end

test("on_init adopts, then ends with clock.sync (what on_load derives)", function()
  calls = {}
  lifecycle.init()
  local n = names()
  assert(has("speech.adopt_all") and has("breakage.adopt_all"), show())
  assert(n[#n] == "clock.sync", "not last: " .. show())
end)

test("on_configuration_changed adopts speech, breakage AND a stranded airborne body, then clock.sync last", function()
  calls = {}
  lifecycle.changed({})
  local n = names()
  assert(has("speech.adopt_all") and has("breakage.adopt_all") and has("jump.adopt_all"), show())
  assert(n[#n] == "clock.sync", "not last: " .. show())
end)

test("on_object_destroyed: every module forgets the unit - jump included - and nothing for equipment", function()
  calls = {}
  handlers.on_object_destroyed({type = defines.target_type.entity, useful_id = 42})
  for _, m in ipairs({"speech", "swap", "breakage", "jump"}) do
    local c = has(m .. ".forget")
    assert(c and c.args[1] == 42, m .. ".forget: " .. show())
  end
  calls = {}
  handlers.on_object_destroyed({type = defines.target_type.equipment, useful_id = 42})
  assert(#calls == 0, show())
end)

test("the 60-tick clock polls speech, swap, breakage and the stranded jumps", function()
  calls = {}
  nth[60]({tick = 600})
  for _, call in ipairs({"speech.poll", "swap.poll", "breakage.poll", "jump.poll", "attack.poll"}) do
    assert(has(call), call .. ": " .. show())
  end
  assert(has("breakage.poll").args[1] == 600 and has("attack.poll").args[1] == 600)
end)

test("D.7: a stream start (C.fired) goes to attack.on_fired", function()
  assert(handlers[C.fired] == package.loaded["scripts.attack"].on_fired, "C.fired not wired")
end)

test("D.7: damage - his own or a squad-mate's splash is never a complaint, his bodies' damage is", function()
  local body = {name = C.beached}
  local chest = {name = "wooden-chest"}
  local cases = {
    {verdict = "self", entity = body, health = 10, want = false},       -- himself, or a squad-mate
    {verdict = nil, entity = body, health = 10, want = true},           -- a biter, a Jamal of another force
    {verdict = nil, entity = body, health = 0, want = false},           -- a killing blow is died's
    {verdict = "friendly", entity = chest, health = 10, want = false},  -- his fire on a chest
  }
  for i, c in ipairs(cases) do
    calls, verdict = {}, c.verdict
    handlers.on_entity_damaged({entity = c.entity, final_health = c.health})
    assert(has("attack.damaged"), i .. ": attack never saw it")
    local d = has("speech.damaged")
    assert((d ~= nil) == c.want and (d == nil or d.args[1] == c.entity), i .. ": " .. show())
  end
  verdict = nil
end)

test("D.7: the damage handler is registered with attack's NARROW filter, built from every body", function()
  assert(filters.on_entity_damaged == NARROW, "not what attack.install returned")
  local names = {}
  for i, x in ipairs(installed or {}) do
    assert(x.filter == "name" and (i == 1 or x.mode == nil or x.mode == "or"), "not a name filter: " .. i)
    names[x.name] = true
  end
  assert(names[C.name] and names[C.beached] and names[C.airborne], "a body is missing")
end)

test("D.7: on_load derives attack's filter through clock.install - the one on_load there is", function()
  local attack = package.loaded["scripts.attack"]
  assert(clock_install and clock_install[1] == attack.derive, "clock.install did not get attack.derive")
end)

test("D.7: the 15-tick clock delivers speech's chains AND a burst's first line", function()
  calls = {}
  nth[15]({tick = 45})
  assert(has("speech.deliver_due") and has("speech.deliver_due").args[1] == 45, show())
  assert(has("attack.deliver_due") and has("attack.deliver_due").args[1] == 45, show())
end)

test("a quickbar slot set, or a player removed, drops that player's cached remote slots", function()
  for _, id in ipairs({"on_player_set_quick_bar_slot", "on_player_removed"}) do
    calls = {}
    assert(handlers[id], id .. " is not registered")
    handlers[id]({player_index = 7})
    local c = has("swap.quickbar_changed")
    assert(c and c.args[1] == 7, id .. ": " .. show())
  end
end)

test("the harness `keep` is breakage.keep (the playtest's /jamaltron-swap beached)", function()
  calls = {}
  local body = {}
  interfaces["jamaltron-harness"].keep(body)
  local c = has("breakage.keep")
  assert(c and c.args[1] == body, show())
end)

test("the harness `strand` is jump.adopt (the playtest's /jamaltron-swap airborne)", function()
  calls = {}
  local body = {}
  interfaces["jamaltron-harness"].strand(body)
  local c = has("jump.adopt")
  assert(c and c.args[1] == body, show())
end)

test("the repair event is registered only for the beached body, to breakage.on_repaired", function()
  assert(handlers.on_player_repaired_entity == package.loaded["scripts.breakage"].on_repaired)
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. tnames[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
