-- The take's two logs, the interface the picture and sound builders code against (the spec is
-- tools/README.md, "Video: the take's logs"; this file is its writer):
--   <dir>/events.jsonl   one event a line, in TICK ORDER (see DELAY); `tick` is when it
--                        HAPPENED - story.lua back-dates what on_tick only sees a tick later
--   <dir>/track.jsonl    one line per captured tick: tick, cam, zoom, body, pos, lift, and
--                        `sprite` (the arc sheet's raw offset, in the air only)
-- Both through helpers.write_file (script-output/<dir>/...), never scraped from the game log:
-- the log is for people, these are for code.
--
-- WHICH TRACK LINE A FRAME SHOWS. Line T is written at the END of this mod's on_tick T: after
-- jamaltron's on_tick T (a dependency's handler runs first; it moves him through an arc and
-- lands him) and after this mod's own step (which presses the jumps), but BEFORE the engine's
-- entity update T (walking) and every on_nth_tick handler (jamaltron's stand-up poll). Frame T
-- is drawn after all of it. So, MEASURED on main-20260927-204942:
--   cam, zoom   line T is exactly frame T's camera, always
--   pos, body,  frame T shows line T+1 on the ground (walking moved him in update T) and on the
--   lift        stand-up tick (line 3480 still says beached, lift 0; frame 3480 shows him up),
--               but line T in an arc and on its takeoff and landing ticks (jamaltron's on_tick
--               already moved him: line 232 holds tick 232's arc step, line 261 the landed body)
-- The contract's first wording ("line T is the state before update T, so frame T anchors on
-- T+1") holds on the ground only; captions.Anchorer implements the whole rule.
--
-- JSON by hand, not helpers.table_to_json: fixed key order (tick and ev first, so a line reads
-- at a glance and two takes diff cleanly) and numbers rounded to 1/1000 tile (0.03 px at zoom
-- 2; a position is fixed-point 1/256 anyway), where table_to_json would print 26.07421875 and
-- 0.10000000000000001.

local M = {}

---Ticks an event waits in the buffer before it is written. A few events are only KNOWN after
---they happened (fire_stop is 10 quiet ticks after the last round spent), so writing at once
---would leave the file out of tick order; waiting DELAY and sorting keeps it ordered.
M.DELAY = 16

---Track lines written per append: one write_file a second, not one a tick.
M.TRACK_BATCH = 60

---@class Video.Journal
---@field dir string
---@field events {seq: integer, rec: table}[]
---@field seq integer
---@field track string[]
---@field written integer events written so far
---@field tracked integer track lines written so far

---@param n number
---@return string
local function num(n)
  if n == math.floor(n) and n > -2 ^ 52 and n < 2 ^ 52 then
    return string.format("%d", n)
  end
  local s = string.format("%.3f", n):gsub("0+$", ""):gsub("%.$", "")
  if s == "-0" then s = "0" end
  return s
end

---@param v any
---@return string
local function encode(v)
  local t = type(v)
  if t == "number" then return num(v) end
  if t == "boolean" then return v and "true" or "false" end
  if t == "string" then return '"' .. v:gsub('[%c"\\]', function(c)
    return string.format("\\u%04x", c:byte())
  end) .. '"' end
  if t == "table" then
    if #v > 0 or next(v) == nil then                       -- an array (or an empty table)
      local parts = {}
      for i, item in ipairs(v) do parts[i] = encode(item) end
      return "[" .. table.concat(parts, ",") .. "]"
    end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = k end
    -- tick, then ev, then the rest alphabetically: stable lines, readable at a glance.
    local rank = {tick = 1, ev = 2}
    table.sort(keys, function(a, b)
      local ra, rb = rank[a] or 3, rank[b] or 3
      if ra ~= rb then return ra < rb end
      return a < b
    end)
    local parts = {}
    for i, k in ipairs(keys) do parts[i] = '"' .. k .. '":' .. encode(v[k]) end
    return "{" .. table.concat(parts, ",") .. "}"
  end
  return "null"
end
M.encode = encode

---@return Video.Journal
local function j()
  return storage.video.journal
end

---Start both files empty (append=false) - a re-run into the same profile starts clean.
---@param dir string
function M.open(dir)
  storage.video.journal = {dir = dir, events = {}, seq = 0, track = {}, written = 0, tracked = 0}
  helpers.write_file(dir .. "/events.jsonl", "", false)
  helpers.write_file(dir .. "/track.jsonl", "", false)
end

---Queue one event. `rec.tick` is when it HAPPENED (it may be in the past); `rec.ev` its name.
---@param rec table
function M.event(rec)
  local jr = j()
  jr.seq = jr.seq + 1
  jr.events[#jr.events + 1] = {seq = jr.seq, rec = rec}
end

---Write every queued event at or before `upto`, in (tick, queue order) order.
---@param upto integer
function M.flush(upto)
  local jr = j()
  local due, keep = {}, {}
  for _, e in ipairs(jr.events) do
    if e.rec.tick <= upto then due[#due + 1] = e else keep[#keep + 1] = e end
  end
  if #due == 0 then return end
  table.sort(due, function(a, b)
    if a.rec.tick ~= b.rec.tick then return a.rec.tick < b.rec.tick end
    return a.seq < b.seq
  end)
  local lines = {}
  for i, e in ipairs(due) do lines[i] = encode(e.rec) end
  helpers.write_file(jr.dir .. "/events.jsonl", table.concat(lines, "\n") .. "\n", true)
  jr.written = jr.written + #due
  jr.events = keep
end

---One captured tick's line.
---@param rec table
function M.track(rec)
  local jr = j()
  jr.track[#jr.track + 1] = encode(rec)
  if #jr.track >= M.TRACK_BATCH then M.flush_track() end
end

function M.flush_track()
  local jr = j()
  if #jr.track == 0 then return end
  helpers.write_file(jr.dir .. "/track.jsonl", table.concat(jr.track, "\n") .. "\n", true)
  jr.tracked = jr.tracked + #jr.track
  jr.track = {}
end

---Everything still buffered, now (the take is over).
function M.close()
  M.flush(math.huge)
  M.flush_track()
end

return M
