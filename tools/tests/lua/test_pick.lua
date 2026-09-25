-- The D.5.1 picker against the REAL generated catalog, under plain lua.
--
--   lua tools/tests/lua/test_pick.lua <repo root>
--
-- tools/tests/test_speech_lua.py runs this. No framework: each test is a function, a failed
-- assert names itself, and the last line is `ok <n>` for the wrapper to check. Factorio is
-- Lua 5.2; this file and the picker stick to what 5.2 and 5.4+ share.

local root = arg[1] or "."
local catalog = dofile(root .. "/mod/jamaltron/scripts/lines.lua")
local pick = dofile(root .. "/mod/jamaltron/scripts/speech/pick.lua")
local pools = catalog.pools

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end

local function ids(rows)
  local out = {}
  for _, row in ipairs(rows) do
    out[row.id] = true
  end
  return out
end

local function count(t)
  local n = 0
  for _ in pairs(t) do
    n = n + 1
  end
  return n
end

---A deterministic rng: hands back the queued values in turn.
local function queue(...)
  local values, i = {...}, 0
  return function(n)
    i = i + 1
    local v = values[i]
    assert(v and v >= 1 and v <= n, "queued roll " .. tostring(v) .. " outside 1.." .. n)
    return v
  end
end

test("tiers are cumulative", function()
  local q = ids(pick.eligible(pools.idle, "quiet"))
  local n = ids(pick.eligible(pools.idle, "normal"))
  local u = ids(pick.eligible(pools.idle, "unbearable"))
  for id in pairs(q) do assert(n[id], id .. " is quiet but not normal") end
  for id in pairs(n) do assert(u[id], id .. " is normal but not unbearable") end
  assert(count(q) < count(n) and count(n) < count(u), "each tier must add rows")
  for _, row in ipairs(pools.idle.rows) do
    if row.tier == "unbearable" then assert(not n[row.id], row.id .. " leaked below its tier") end
  end
  -- an unknown verbosity plays as normal rather than as silence or as everything
  assert(count(ids(pick.eligible(pools.idle, "loud"))) == count(n))
end)

test("tail-only rows never roll, at any tier", function()
  local tails = 0
  for _, pool in pairs(pools) do
    local u = ids(pick.eligible(pool, "unbearable", "self"))
    for _, row in ipairs(pool.rows) do
      if row.tail_only then
        tails = tails + 1
        assert(not u[row.id], row.id .. " is tail-only and rolled")
      end
    end
  end
  assert(tails == 7, "the catalog says 7 tail-only rows, found " .. tails)
end)

test("once_per_save rows leave the roll once fired", function()
  local before = ids(pick.eligible(pools.idle, "unbearable"))
  assert(before["idle.34"] and before["idle.35"])
  local after = ids(pick.eligible(pools.idle, "unbearable", nil, {["idle.34"] = true}))
  assert(not after["idle.34"] and after["idle.35"])
end)

test("a required split rolls only the side reported, and nothing without one", function()
  assert(#pick.eligible(pools.legs_break, "unbearable") == 0, "no side, no row")
  for _, side in ipairs(pools.legs_break.sides) do
    local rows = pick.eligible(pools.legs_break, "unbearable", side)
    assert(#rows > 0, side)
    for _, row in ipairs(rows) do assert(row.sub == side, row.id) end
  end
end)

test("a gated split always rolls `any` and adds only the value reported", function()
  local base = pick.eligible(pools.flopping, "unbearable")
  for _, row in ipairs(base) do assert(row.sub == "any", row.id .. " rolled with no fork") end
  local self = ids(pick.eligible(pools.flopping, "unbearable", "self"))
  local ext = ids(pick.eligible(pools.flopping, "unbearable", "external"))
  for _, row in ipairs(pools.flopping.rows) do
    if row.sub == "self" and not row.tail_only then assert(self[row.id] and not ext[row.id], row.id) end
    if row.sub == "external" and not row.tail_only then assert(ext[row.id] and not self[row.id], row.id) end
  end
  -- attacking predates `any` and spells it both ways (lines.md): both must roll unreported
  assert(#pick.eligible(pools.attacking, "normal") > 0)
end)

test("a hushed channel leaves only the other one", function()
  local rows = pick.eligible(pools.low_health, "unbearable", nil, nil, "narration")
  assert(#rows == 1 and rows[1].id == "low_health.01", "low_health's only narration row")
  assert(#pick.eligible(pools.enter, "unbearable", nil, nil, "narration") == 0)
end)

test("anti-repeat drops recent groups ACROSS pools", function()
  -- flopping.02 carries low_health.03's string: saying the low_health row must hide it
  local rows = pick.eligible(pools.flopping, "unbearable")
  local fresh = ids(pick.fresh(rows, {"low_health.03"}, "low_health.03", catalog.allow_repeat))
  assert(not fresh["flopping.02"], "a shared string came straight back from another pool")
  assert(fresh["flopping.03"])
end)

test("anti-repeat relaxes instead of going silent, and never to the last line if it can help it", function()
  local rows = pick.eligible(pools.enter, "quiet")
  local recent = {}
  for _, row in ipairs(rows) do recent[#recent + 1] = row.grp end
  local last = rows[#rows]
  local loose = pick.fresh(rows, recent, last.id, catalog.allow_repeat)
  assert(#loose == #rows - 1, "every group recent: drop only the last one")
  assert(not ids(loose)[last.id])
  local only = {rows[1]}
  assert(#pick.fresh(only, {rows[1].grp}, rows[1].id) == 1, "one row left: say it anyway")
end)

test("the idle.01 -> idle.02 callback is exempt, and only in that order", function()
  local two = {}
  for _, row in ipairs(pools.idle.rows) do
    if row.id == "idle.02" then two[1] = row end
  end
  assert(two[1])
  local recent = {two[1].grp, "idle.01"}
  assert(#pick.fresh(two, recent, "idle.01", catalog.allow_repeat) == 1, "callback blocked")
  -- the other way round is not a callback: idle.02's group recent, idle.02 after idle.02
  local strict = pick.fresh({two[1], pools.idle.rows[3]}, {two[1].grp}, "idle.03",
    catalog.allow_repeat)
  assert(not ids(strict)["idle.02"])
end)

test("the roll honours W", function()
  local rows = {{id = "a", w = 3}, {id = "b", w = 1}}
  assert(pick.roll(rows, queue(1)).id == "a")
  assert(pick.roll(rows, queue(3)).id == "a")
  assert(pick.roll(rows, queue(4)).id == "b")
  assert(pick.roll({{id = "z", w = 0}}, queue()) == nil, "no weight, no row")
  math.randomseed(7)
  local hits = {a = 0, b = 0}
  for _ = 1, 20000 do
    local row = pick.roll(rows, math.random)
    hits[row.id] = hits[row.id] + 1
  end
  local share = hits.a / 20000
  assert(share > 0.73 and share < 0.77, "3:1 weights gave " .. share)
end)

test("remember keeps the most recent M.RECENT groups", function()
  local recent = {}
  for i = 1, pick.RECENT + 3 do pick.remember(recent, "g" .. i) end
  assert(#recent == pick.RECENT and recent[1] == "g4" and recent[#recent] == "g" .. (pick.RECENT + 3))
end)

test("pick() end to end: a fork, a fired gate and anti-repeat together", function()
  local seen = {}
  local opts = {verbosity = "unbearable", cond = "external", fired = {}, recent = {}}
  math.randomseed(11)
  for _ = 1, 200 do
    local row = pick.pick(catalog, pools.flopping, opts, math.random)
    assert(row and row.sub ~= "self", "the external fork said a self line")
    seen[row.id] = true
    pick.remember(opts.recent, row.grp)
    opts.last_id = row.id
  end
  assert(count(seen) > 10, "anti-repeat should spread 200 rolls over the pool")
end)

test("every chain head names a row in its own pool", function()
  local heads = 0
  for key, pool in pairs(pools) do
    local here = ids(pool.rows)
    for _, row in ipairs(pool.rows) do
      if row.follow then
        heads = heads + 1
        assert(here[row.follow], key .. ": " .. row.id .. " -> " .. row.follow)
        assert(row.delay and row.delay >= 60, row.id)
      end
    end
  end
  assert(heads == 9, "the catalog says 9 chains, found " .. heads)
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
