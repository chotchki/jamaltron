-- The bubble cap in the engine (PLAN F.3, chotchki 2026-09-26: "yes cap the bubbles"). N real
-- breaks flopping with jamaltron-max-bubbles set low and the apology interval at its 2 s minimum
-- so the flops outrun the cap (8 flopping once per 10 s cooldown want ~4.4 bubbles up; 3
-- allowed), judged every tick on the ENGINE's count of our bubble entities (the GPU draws what
-- stands, not what speech.lua's registry believes), with the registry required to agree. An
-- event said at the cap still speaks and takes a chatter bubble down.
--
-- The cap is low only between control.lua's flop checks (dt 1320 and 1970), after the walker's
-- command_done and before the idler's first idle can come due (dt 2025 at the earliest): it is
-- map-wide, so while it is low every other lane's chatter waits too, and an idle or command_done
-- waiting inside it is a turn lost. The walker finishes at dt 1249-1330 depending on the map
-- (measured over 8 seeds), so the cap comes down on the first tick from 1335 that he is done, or
-- at 1500 regardless. The sharks break well before (a break's own line starts the 10 s cooldown
-- every flop waits out), and with only 8 of them the DEFAULT cap leaves room for the walker's
-- command_done and the dt 670 and 1320 flops.

local M = {}

local SAY, HARNESS = "jamaltron", "jamaltron-harness"
local BUBBLE = "jamaltron-speech-bubble"

---Ticks (dt): the sharks break one every STAGGER from BREAK (out of step, so the flops come as a
---steady stream, not one wave per cooldown); the cap comes down between FROM and FROM_LATEST
---(above) and is judged every tick from GRACE after that (chatter up before it came down has
---faded by then, 300 + 29 ticks) to UNTIL, when it all goes back. The event is said EVENT ticks
---after the watch starts.
local BREAK, STAGGER, FROM, FROM_LATEST, GRACE, EVENT, UNTIL = 40, 75, 1335, 1500, 330, 40, 1950
local CAP, SHARKS = 3, 8

---Spawn the sharks standing and the event's speaker; the apology interval to its minimum.
local function setup()
  local surface = game.surfaces[1]
  remote.call(HARNESS, "setting", "jamaltron-apology-interval", 2)
  local run = {standing = {}, beached = {}, max = 0, max_ambient = 0, ticks = 0, disagree = 0,
               over = 0, first_disagree = nil, first_over = nil, flops = 0, seen = {}}
  for i = 1, SHARKS do
    run.standing[i] = surface.create_entity{name = "jamaltron", force = "player",
                                            position = {x = (i - 1) * 12, y = -400}}
  end
  run.x = surface.create_entity{name = "jamaltron", position = {x = 0, y = -440}, force = "player"}
  storage.cap = run
end

---Break shark i for real: airborne, then landed at 100%.
---@param i integer
local function break_one(i)
  local run = storage.cap
  local e = run.standing[i]
  local pos = e.position
  remote.call(HARNESS, "setting", "jamaltron-leg-break-percent", 100)
  local up = remote.call(HARNESS, "swap", e, "jamaltron-airborne",
                         {reason = "takeoff", autopilot = false})
  local down = up.body and remote.call(HARNESS, "land", up.body, pos,
                                       {tick = game.tick, distance = 8})
  remote.call(HARNESS, "setting", "jamaltron-leg-break-percent", 25)
  if down and down.outcome == "broke" then
    run.beached[#run.beached + 1] = down.body
  end
end

---The cap comes down; every flop said from here on is counted.
---@param run table
---@param dt integer
local function lower(run, dt)
  remote.call(HARNESS, "setting", "jamaltron-max-bubbles", CAP)
  run.from = dt
  for i, e in ipairs(run.beached) do
    local st = e.valid and remote.call(HARNESS, "state", e)
    run.seen[i] = st and st.last_tick
  end
end

---The event at the cap, and what it takes down.
---@param run table
---@param check fun(name: string, ok: boolean, detail: string?)
local function event(run, check)
  -- Whether the flops have the cap full this tick is down to the dice; the check must not be.
  -- Top it up with forced chatter (force skips the cap) on sharks with nothing up.
  local surface = game.surfaces[1]
  for _, e in ipairs(run.beached) do
    local st = remote.call(HARNESS, "state", e)
    if surface.count_entities_filtered{name = BUBBLE} >= CAP and st.ambient_bubbles >= 1 then
      break
    end
    if st.bubble == nil then remote.call(HARNESS, "force", e, "flopping.02") end
  end
  local before = remote.call(HARNESS, "state", run.beached[1])
  local standing = surface.count_entities_filtered{name = BUBBLE}
  check("cap: full of chatter when the event comes (else the next check proves nothing)",
        standing >= CAP and before.ambient_bubbles >= 1,
        standing .. " standing, " .. before.ambient_bubbles .. " chatter")
  -- Chatter said straight at the cap (not a flop, whose timer waits in breakage.lua before it
  -- ever asks): it does not happen, and nothing goes up.
  local chatter = remote.call(SAY, "say", run.x, "command_done")
  check("cap: chatter said at the cap does not happen",
        chatter == nil and surface.count_entities_filtered{name = BUBBLE} == standing,
        tostring(chatter))
  local id = remote.call(SAY, "say", run.x, "enter")
  local after = remote.call(HARNESS, "state", run.beached[1])
  check("cap: an event at the cap still speaks, in a bubble",
        id ~= nil and remote.call(HARNESS, "state", run.x).bubble == BUBBLE, tostring(id))
  check("cap: ... taking one chatter bubble down for it",
        game.surfaces[1].count_entities_filtered{name = BUBBLE} == standing
          and after.ambient_bubbles == before.ambient_bubbles - 1,
        serpent.line({before = standing, after = game.surfaces[1].count_entities_filtered{name = BUBBLE},
                      chatter = {before.ambient_bubbles, after.ambient_bubbles}}))
end

---@param dt integer
function M.tick(dt)
  local run = storage.cap
  if run == nil or dt < FROM or dt >= UNTIL then return end       -- UNTIL's step runs first
  if run.from == nil then
    local m = storage.m                                           -- control.lua's walker
    if dt < FROM_LATEST and m and m.valid and #m.autopilot_destinations > 0 then return end
    lower(run, dt)
    return
  end
  for i, e in ipairs(run.beached) do                             -- every flop said under the cap
    local st = e.valid and remote.call(HARNESS, "state", e)
    if st and st.last_tick ~= run.seen[i] then
      run.seen[i] = st.last_tick
      if st.last_id and st.last_id:match("^flopping%.") then run.flops = run.flops + 1 end
    end
  end
  if dt < run.from + GRACE then return end
  if dt == run.from + GRACE + EVENT then event(run, M.check) end
  local standing = game.surfaces[1].count_entities_filtered{name = BUBBLE}
  local st = remote.call(HARNESS, "state", run.beached[1])         -- the registry is map-wide
  run.ticks = run.ticks + 1
  run.max = math.max(run.max, standing)
  run.max_ambient = math.max(run.max_ambient, st.ambient_bubbles)
  if standing ~= st.live_bubbles then
    run.disagree = run.disagree + 1
    run.first_disagree = run.first_disagree
      or string.format("dt %d: %d standing, registry %d", dt, standing, st.live_bubbles)
  end
  -- Chatter above the cap is the failure; an event's bubble over it is the design (a soft
  -- ceiling), so it is the chatter that is counted.
  if st.ambient_bubbles > CAP then
    run.over = run.over + 1
    run.first_over = run.first_over
      or string.format("dt %d: %d chatter bubbles, %d standing", dt, st.ambient_bubbles, standing)
  end
end

---Add the lane's steps to control.lua's.
---@param at fun(dt: integer, fn: fun(s: table))
---@param check fun(name: string, ok: boolean, detail: string?)
function M.register(at, check)
  M.check = check
  at(BREAK, setup)
  for i = 1, SHARKS do
    at(BREAK + i * STAGGER, function() break_one(i) end)
  end
  at(BREAK + (SHARKS + 1) * STAGGER, function(s)
    check("cap: " .. SHARKS .. " real breaks to flop", #s.cap.beached == SHARKS, #s.cap.beached)
  end)
  at(UNTIL, function(s)
    local run = s.cap
    local n = run.flops
    log(string.format("CAP down at dt %d, watched %d ticks: max %d standing, max %d chatter; %d flops from %d sharks under it",
                      run.from or -1, run.ticks, run.max, run.max_ambient, n, #run.beached))
    check("cap: the registry counts what the engine has standing, every tick",
          run.disagree == 0 and run.ticks == UNTIL - run.from - GRACE,
          run.disagree .. " of " .. run.ticks .. " ticks; first " .. tostring(run.first_disagree))
    check("cap: chatter never above the cap, " .. SHARKS .. " flopping at 2 s", run.over == 0,
          tostring(run.first_over))
    check("cap: ... and it was reached, and flops still got through",
          run.max >= CAP and n >= 1, run.max .. " standing max, " .. n .. " flops under it")
    remote.call(HARNESS, "setting", "jamaltron-max-bubbles", 20)
    remote.call(HARNESS, "setting", "jamaltron-apology-interval", 15)
    for _, e in ipairs(run.beached) do if e.valid then e.destroy() end end
    if run.x.valid then run.x.destroy() end
  end)
end

return M
