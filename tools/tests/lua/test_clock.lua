-- The mod's one per-tick clock (PLAN D.4.2), scripts/clock.lua, under plain lua with a fake
-- `script`: on_tick registered EXACTLY while some subsystem is pending, and on_load deriving
-- the same answer - the invariant a joining client depends on.
--
--   lua tools/tests/lua/test_clock.lua <repo root>
--
-- Run by tools/tests/test_speech_lua.py, in test_pick.lua's harness shape; Lua 5.2 / 5.4+ / luajit.

local root = arg[1] or "."
package.path = root .. "/mod/jamaltron/?.lua;" .. package.path

local ON_TICK = 1
defines = {events = {on_tick = ON_TICK}}

local handlers, on_load
script = {
  on_event = function(event, fn) handlers[event] = fn end,
  on_load = function(fn) on_load = fn end,
  get_event_handler = function(event) return handlers[event] end,
}

---A fresh clock module and a fresh fake bootstrap: the registry is module state, filled once
---per load, exactly like a peer's.
local function fresh()
  handlers, on_load = {}, nil
  package.loaded["scripts.clock"] = nil
  return require("scripts.clock")
end

---A subsystem with a work counter; tick() does one unit of work.
local function counter(work)
  local sub = {work = work or 0, ticks = 0}
  sub.pending = function() return sub.work > 0 end
  sub.tick = function() sub.ticks = sub.ticks + 1; sub.work = sub.work - 1 end
  return sub
end

local function fire(n)
  for t = 1, n or 1 do
    local h = handlers[ON_TICK]
    if h then h({tick = t}) end
  end
end

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end

test("idle costs nothing: install and on_load register no on_tick", function()
  local clock = fresh()
  clock.register("swap", counter(0))
  clock.install()
  assert(on_load, "install registers on_load")
  on_load()
  assert(handlers[ON_TICK] == nil)
  local st = clock.state()
  assert(st.registered == false and st.pending == false)
end)

test("on_load runs install's derive hook after the clock's own (attack.lua's damage filter)", function()
  local clock = fresh()
  local sub = counter(1)
  clock.register("swap", sub)
  local order = {}
  clock.install(function()
    order[#order + 1] = handlers[ON_TICK] ~= nil and "after wake" or "before wake"
  end)
  on_load()
  assert(#order == 1 and order[1] == "after wake", table.concat(order, ","))
end)

test("wake registers only while something is pending", function()
  local clock = fresh()
  local sub = counter(0)
  clock.register("swap", sub)
  clock.wake()
  assert(handlers[ON_TICK] == nil, "a stray wake registered with nothing pending")
  sub.work = 1
  clock.wake()
  assert(handlers[ON_TICK] ~= nil)
end)

test("the handler runs the work and drops itself the tick nothing is pending", function()
  local clock = fresh()
  local sub = counter(2)
  clock.register("swap", sub)
  clock.wake()
  fire(1)
  assert(sub.ticks == 1 and handlers[ON_TICK] ~= nil, "still pending after one tick")
  fire(1)
  assert(sub.ticks == 2 and handlers[ON_TICK] == nil, "dropped once idle")
  fire(3)
  assert(sub.ticks == 2, "nothing runs while dropped")
end)

test("only pending subsystems tick, and one's work keeps the clock for all", function()
  local clock = fresh()
  local swap, arc = counter(1), counter(3)
  clock.register("swap", swap)
  clock.register("arc", arc)
  clock.wake()
  fire(4)
  assert(swap.ticks == 1, "swap ticked while idle: " .. swap.ticks)
  assert(arc.ticks == 3 and handlers[ON_TICK] == nil)
end)

test("work one subsystem adds for another during the tick keeps the registration", function()
  local clock = fresh()
  local swap = counter(0)
  local arc = counter(1)
  local inner = arc.tick
  arc.tick = function(t) inner(t); swap.work = swap.work + 1 end   -- the landing swap, mid-arc
  clock.register("swap", swap)
  clock.register("arc", arc)
  clock.wake()
  fire(1)
  assert(handlers[ON_TICK] ~= nil, "the landing's t+1 would be lost")
  fire(1)
  assert(swap.ticks == 1 and handlers[ON_TICK] == nil)
end)

test("on_load re-derives exactly the host's registration, every tick of a run", function()
  local clock = fresh()
  local sub = counter(0)
  clock.register("swap", sub)
  clock.install()
  local host = handlers
  local seen = {}
  for step = 1, 12 do
    if step % 5 == 1 then sub.work = sub.work + 2; clock.wake() end
    fire(1)
    local registered = host[ON_TICK] ~= nil
    seen[registered] = true
    -- a client joining now: the same code and the same storage (sub.work), a fresh bootstrap
    local client = fresh()
    client.register("swap", counter(sub.work))
    client.install()
    on_load()
    local joined = handlers[ON_TICK] ~= nil
    handlers = host                                 -- back to the host
    package.loaded["scripts.clock"] = clock
    assert(joined == registered, "step " .. step .. ": host " .. tostring(registered)
           .. ", client " .. tostring(joined))
  end
  assert(seen[true] and seen[false], "the run should see both states")
end)

test("sync (end of on_init / on_configuration_changed) leaves exactly what on_load would derive", function()
  local clock = fresh()
  local sub = counter(0)
  clock.register("jump", sub)
  clock.install()
  -- a migration ADDED work after on_load registered nothing: sync registers
  sub.work = 2
  clock.sync()
  assert(handlers[ON_TICK] ~= nil, "work added in on_configuration_changed left on_tick unregistered")
  -- and one that DROPPED the work on_load registered for: sync unregisters, where wake cannot
  sub.work = 0
  clock.wake()
  assert(handlers[ON_TICK] ~= nil, "wake never unregisters (by design)")
  clock.sync()
  assert(handlers[ON_TICK] == nil, "a registration nothing needs outlived on_configuration_changed")
  local host = handlers[ON_TICK] ~= nil
  local client = fresh()
  client.register("jump", counter(sub.work))
  client.install()
  on_load()
  assert((handlers[ON_TICK] ~= nil) == host, "a joining client derives the same")
end)

test("a name registered twice is an error, not a silent second subsystem", function()
  local clock = fresh()
  clock.register("swap", counter(0))
  local ok = pcall(clock.register, "swap", counter(0))
  assert(not ok)
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
