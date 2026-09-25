-- The D.5.4 speech harness: drives a scripted run in a headless benchmark and reports each
-- check as one log line tools/smoke.sh --harness reads.
--
--   HARNESS ok <check>                  passed
--   HARNESS FAIL <check>: <detail>      failed - smoke.sh fails the run
--   HARNESS need <ERE>                  some log line must match (grep -E, after the run)
--   HARNESS never <ERE>                 no log line may match
--   HARNESS done <n>                    the script reached the end; missing = a crash
--
-- Speech logs every line said as `jamaltron speech <unit> <row id>` while debug is on, which
-- is what the need/never lines are written against. Chance is the enemy of a test, so the
-- checks that need a particular row FORCE it (the harness remote skips the roll and the
-- gates) and the checks about the roll assert on what a roll is allowed to produce.

local lines = require("__jamaltron__/scripts/lines")

local SAY, HARNESS = "jamaltron", "jamaltron-harness"

---@param name string
---@param ok boolean
---@param detail string?
local function check(name, ok, detail)
  storage.passed = (storage.passed or 0) + (ok and 1 or 0)
  log(ok and ("HARNESS ok " .. name) or ("HARNESS FAIL " .. name .. ": " .. tostring(detail)))
end

local function state(entity)
  return remote.call(HARNESS, "state", entity)
end

local function sub_of(id)
  for _, pool in pairs(lines.pools) do
    for _, row in ipairs(pool.rows) do
      if row.id == id then return row.sub end
    end
  end
end

---A jamaltron near `x`, raising the built event only when asked.
local function spawn(x, raise)
  local surface = game.surfaces[1]
  local at = surface.find_non_colliding_position("jamaltron", {x, 0}, 40, 1) or {x, 0}
  return surface.create_entity{name = "jamaltron", position = at, force = "player",
                               raise_built = raise}
end

-- Every step runs on one tick, counted from the first tick the benchmark runs.
local steps = {}
local function at(dt, fn) steps[#steps + 1] = {dt = dt, fn = fn} end

at(0, function(s)
  remote.call(SAY, "debug", true)
  s.a = spawn(0, true)          -- built line, chains, R5
  s.b = spawn(40, false)        -- the low_health.01 window
  s.d = spawn(80, false)        -- death: R3, and a death cancels a chain
  s.e = spawn(120, false)       -- R4, once_per_save
  s.g = spawn(160, false)       -- the break: {N}, the fork, repaired
  s.t1 = spawn(200, false)      -- transfer, from
  s.t2 = spawn(240, false)      -- transfer, to
  s.c = spawn(-60, true)        -- left alone: idle has to happen by itself
  s.m = spawn(-120, true)       -- walks: moving and command_done
  -- Four legs, so the walk outlasts the cooldown his built line starts; command_done is the
  -- LAST waypoint only, so it should say it once, at the end.
  local x, y = s.m.position.x, s.m.position.y
  for _, dx in ipairs({-60, 0, -60, 0}) do
    s.m.add_autopilot_destination({x + dx, y})
  end
  s.seen_m = {}
end)

at(1, function(s)
  local a = state(s.a)
  check("built fires on raise_built", a and a.last_id and a.last_id:match("^built%.") ~= nil,
        a and a.last_id)
  check("a speech line puts up OUR bubble", a and a.bubble == "jamaltron-speech-bubble",
        a and a.bubble)
end)

at(300, function(s)                       -- clear of any chain the built line started
  check("force starts a chain", remote.call(HARNESS, "force", s.a, "idle.08") == "idle.08")
  local a = state(s.a)
  check("the chain is pending with the head's delay",
        a.pending == "idle.09" and a.pending_due == game.tick + 150, serpent.line(a))
  check("R5: a pending chain owns his speech (event)", remote.call(SAY, "say", s.a, "enter") == nil)
  check("R5: ... and ambient", remote.call(SAY, "say", s.a, "idle") == nil)
  s.chain_due = game.tick + 150
end)
at(440, function(s)
  check("the follow-up waits for its delay", state(s.a).pending == "idle.09")
end)
at(470, function(s)
  local a = state(s.a)
  check("the follow-up lands, and nothing is left pending",
        a.last_id == "idle.09" and a.pending == nil, serpent.line(a))
end)

at(5, function(s)
  remote.call(HARNESS, "force", s.b, "low_health.01")
  local b = state(s.b)
  check("low_health.01 opens a 15 s speech window", b.hush_speech_until == game.tick + 900,
        serpent.line(b))
  check("narration draws world text, not a bubble", b.note == true and b.bubble == nil,
        serpent.line(b))
  check("the window hushes speech: enter has no narration row, so nothing",
        remote.call(SAY, "say", s.b, "enter") == nil)
end)
at(906, function(s)
  check("speech comes back when the window ends", remote.call(SAY, "say", s.b, "enter") ~= nil)
end)

at(10, function(s)
  remote.call(HARNESS, "force", s.d, "idle.08")        -- a chain in flight...
  remote.call(HARNESS, "force", s.d, "low_health.01")  -- ...and a window open
  local unit = s.d.unit_number
  log("HARNESS need jamaltron speech " .. unit .. " died[.][0-9]+")
  log("HARNESS never jamaltron speech " .. unit .. " idle[.]09")
  s.d.die()
  check("died fires through the window and cancels the chain (log-checked)", true)
end)

at(15, function(s)
  check("R4: a broken landing never speaks", remote.call(SAY, "say", s.e, "land", "broke") == nil)
  remote.call(HARNESS, "force", s.e, "idle.34")
  local fired = state(s.e).fired
  check("once_per_save records the row", fired[1] == "idle.34", serpent.line(fired))
end)

at(20, function(s)
  local said = remote.call(SAY, "say", s.g, "legs_break", "self")
  local g = state(s.g)
  check("a break counts and stamps its fork", g.breaks == 1 and g.fork == "self", serpent.line(g))
  check("the break line is from its own side", said == nil or sub_of(said) == "self", said)
  remote.call(SAY, "say", s.g, "repaired")
  g = state(s.g)
  check("repaired clears the fork and keeps the count", g.fork == nil and g.breaks == 1,
        serpent.line(g))
  remote.call(SAY, "say", s.g, "legs_break", "external")
  check("the count is cumulative", state(s.g).breaks == 2)
end)
for i = 1, 4 do                            -- flopping is ambient: one per cooldown
  at(20 + 650 * i, function(s)
    local said = remote.call(SAY, "say", s.g, "flopping")
    check("flop " .. i .. " rolls the fork the break carried",
          said ~= nil and sub_of(said) ~= "self", said)
  end)
end

at(25, function(s)
  remote.call(SAY, "say", s.t1, "legs_break", "self")
  local old = s.t1.unit_number
  remote.call(HARNESS, "transfer", old, s.t2)
  local moved, gone = state(s.t2), state(s.t1)
  check("transfer moves the record to the new entity", moved and moved.breaks == 1
        and moved.fork == "self", serpent.line(moved))
  check("... and leaves nothing behind", gone == nil, serpent.line(gone))
  s.t1.destroy()
end)

at(35, function(s)                          -- a death's two render paths, on purpose
  local ok = pcall(remote.call, HARNESS, "force", s.e, "died.02", true)
  check("a dying SPEECH line draws world text (a bubble needs an entity)",
        ok and state(s.e).note == true, serpent.line(state(s.e)))
  ok = pcall(remote.call, HARNESS, "force", s.e, "died.01", true)
  check("a dying NARRATION line draws where he fell", ok and state(s.e).note == true)
end)

at(30, function(s)                          -- tools/play.sh's chat mode, then back to logging
  remote.call(SAY, "debug", "print")
  check("print-mode debug says a line without falling over",
        remote.call(HARNESS, "force", s.e, "idle.01") == "idle.01")
  remote.call(SAY, "debug", true)
end)

for dt = 60, 3600, 60 do                   -- watch the walker
  at(dt, function(s)
    local m = s.m.valid and state(s.m)
    if m and m.last_id then s.seen_m[m.last_id:match("^(.-)%.")] = true end
  end)
end

at(3700, function(s)
  local c = state(s.c)
  check("idle fires on its own while he sits undriven", c and c.last_id
        and c.last_id:match("^idle%.") ~= nil, c and c.last_id)
  check("moving fires while the autopilot walks him", s.seen_m.moving == true,
        serpent.line(s.seen_m))
  check("command_done fires when the walk ends", s.seen_m.command_done == true,
        serpent.line(s.seen_m))
  log("HARNESS done " .. tostring(storage.passed))
end)

table.sort(steps, function(x, y) return x.dt < y.dt end)

script.on_event(defines.events.on_tick, function(event)
  local s = storage
  s.start = s.start or event.tick
  local dt = event.tick - s.start
  for _, step in ipairs(steps) do
    if step.dt == dt then
      local ok, err = pcall(step.fn, s)
      if not ok then check("step at dt " .. dt .. " ran", false, err) end
    end
  end
end)
