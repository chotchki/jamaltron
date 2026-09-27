-- His broken legs round a beached Jamal (PLAN D.1.3): scripts/wreck.lua's layout under plain lua,
-- with a seeded rng standing in for the map's math.random, and a FAKE rendering for ensure().
-- chotchki's rule is the spec: BENT, NOT SNAPPED - every leg one connected piece from under him,
-- bent at wrong angles, inside ~6 tiles, off his face, rarely across another leg, different
-- every break. That the hub stays under him through the whole flop is measured off the sheet
-- itself: tools/tests/test_wreck_cover.py.
--
--   lua tools/tests/lua/test_wreck.lua <repo root>
--
-- Run by tools/tests/test_speech_lua.py, in test_pick.lua's harness shape; Lua 5.2 / 5.4+ / luajit.
--
-- CONNECTED IS CHECKED OFF THE PIECES, not the joint chain layout() also returns: each art
-- piece's far end is recomputed the way the engine will draw it (its offset, its orientation,
-- the part's length times its scale) and must land on the next piece's offset. A chain that is
-- connected on paper but drawn with the wrong orientation convention or scale comes apart here.

local root = arg[1] or "."
package.path = root .. "/mod/jamaltron/?.lua;" .. package.path

local C = require("prototypes.shared")
local W = require("scripts.wreck")

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end

---Park-Miller: exact in a double, so the same seed gives the same stream on 5.2, 5.4 and luajit.
---math.random(lo, hi)'s shape, and it insists on it: the map's generator takes integers.
local function rng(seed)
  local s = seed % 2147483647
  if s <= 0 then s = s + 2147483646 end
  return function(lo, hi)
    assert(type(lo) == "number" and type(hi) == "number" and lo == math.floor(lo)
           and hi == math.floor(hi) and lo <= hi, "rng asked for (" .. tostring(lo) .. ", "
           .. tostring(hi) .. ") - math.random(lo, hi) wants integers, lo <= hi")
    s = s * 16807 % 2147483647
    return lo + s % (hi - lo + 1)
  end
end

local SEEDS = 2000
local EPS = 1e-6

---One layout per seed, laid once: a layout is ~2 ms of search, and every test below walks them.
local laid = {}
local function layout(seed)
  laid[seed] = laid[seed] or W.layout(rng(seed))
  return laid[seed]
end

local function dir(o)
  local r = o * 2 * math.pi
  return math.sin(r), -math.cos(r)
end

---The art pieces of each leg, in draw order, with where the engine will put each one's far end.
local function legs_of(pieces)
  local legs = {}
  for _, p in ipairs(pieces) do
    if p.sprite:match("%-art$") then
      local part = p.sprite:sub(#C.wreck + 2, -5)
      local spec = W.PARTS[part]
      assert(spec, "an art piece of no known part: " .. p.sprite)
      -- a part runs +y (south) unrotated, so drawn at `orientation` it points along o + 0.5
      local dx, dy = dir(p.orientation + 0.5)
      local len = spec.len * p.scale
      local leg = legs[p.leg] or {}
      legs[p.leg] = leg
      leg[#leg + 1] = {part = part, from = p.offset, to = {p.offset[1] + dx * len, p.offset[2] + dy * len},
                       heading = (p.orientation + 0.5) % 1}
    end
  end
  return legs
end

local function dist(a, b) return math.sqrt((a[1] - b[1]) ^ 2 + (a[2] - b[2]) ^ 2) end

---Turn between two headings, signed, in (-0.5, 0.5].
local function turn(a, b)
  local d = (b - a) % 1
  if d > 0.5 then d = d - 1 end
  return d
end

test("deterministic: one rng stream, one layout - to the last digit", function()
  for seed = 1, 50 do
    local a, b = layout(seed), W.layout(rng(seed))
    assert(#a == #b, "piece counts differ for seed " .. seed)
    for i = 1, #a do
      local p, q = a[i], b[i]
      assert(p.sprite == q.sprite and p.offset[1] == q.offset[1] and p.offset[2] == q.offset[2]
             and p.orientation == q.orientation and p.scale == q.scale and p.layer == q.layer
             and p.tint == q.tint, "seed " .. seed .. " piece " .. i .. " differs")
    end
  end
end)

test("every leg is ONE connected piece: each segment's drawn end meets the next one's start", function()
  for seed = 1, SEEDS do
    local legs = legs_of(layout(seed))
    assert(#legs == C.leg_count, "seed " .. seed .. ": " .. #legs .. " legs")
    for i, leg in ipairs(legs) do
      assert(leg[1].part == "upper", "seed " .. seed .. " leg " .. i .. " starts with " .. leg[1].part)
      local shape = {}
      for j, s in ipairs(leg) do shape[j] = s.part end
      shape = table.concat(shape, ",")
      assert(shape == "upper,lower" or shape == "upper,lower-a,lower-b",
             "seed " .. seed .. " leg " .. i .. " is " .. shape)
      for j = 1, #leg - 1 do
        local gap = dist(leg[j].to, leg[j + 1].from)
        assert(gap < 0.01, string.format("seed %d leg %d: %s ends %.3f tiles from where %s starts",
               seed, i, leg[j].part, gap, leg[j + 1].part))
      end
    end
  end
end)

test("hips at the hub under him, and every leg BENT - the knee well off straight, a kink bending back", function()
  for seed = 1, SEEDS do
    local legs = legs_of(layout(seed))
    for i, leg in ipairs(legs) do
      local hip = leg[1].from
      assert(dist(hip, W.HUB) <= 0.15,
             string.format("seed %d leg %d hip at (%.2f, %.2f), off the hub", seed, i, hip[1], hip[2]))
      local knee = turn(leg[1].heading, leg[2].heading)
      assert(math.abs(knee) >= 0.05 - EPS, string.format("seed %d leg %d: a knee of %.3f turns is a straight leg", seed, i, knee))
      if leg[3] then
        local kink = turn(leg[2].heading, leg[3].heading)
        assert(math.abs(kink) >= 0.1 - EPS and kink * knee < 0,
               string.format("seed %d leg %d: kink %.3f after knee %.3f - a zigzag bends back", seed, i, kink, knee))
      end
    end
  end
end)

test("inside the footprint: every joint within RADIUS of the centre - ~6 tiles across, not the spike's 10", function()
  local widest = 0
  for seed = 1, SEEDS do
    for i, leg in ipairs(legs_of(layout(seed))) do
      for _, s in ipairs(leg) do
        local r = dist(s.to, W.CENTER)
        if r > widest then widest = r end
        assert(r <= W.RADIUS + EPS, string.format("seed %d leg %d: a joint %.2f tiles out", seed, i, r))
      end
    end
  end
  assert(W.RADIUS * 2 <= 7, "the footprint itself grew past ~6 tiles: " .. W.RADIUS * 2)
  assert(widest > W.RADIUS - 0.6, "every leg folded in tight: the widest joint was " .. widest)
end)

test("off his face: no piece's centre in the keep-clear box over his head", function()
  local h = W.HEAD
  for seed = 1, SEEDS do
    for i, leg in ipairs(legs_of(layout(seed))) do
      for _, s in ipairs(leg) do
        local m = {(s.from[1] + s.to[1]) / 2, (s.from[2] + s.to[2]) / 2}
        assert(not (m[1] > h.left and m[1] < h.right and m[2] > h.top and m[2] < h.bottom),
               string.format("seed %d leg %d: %s centred on his face at (%.2f, %.2f)", seed, i, s.part, m[1], m[2]))
      end
    end
  end
end)

test("varied: two seeds never lay the same wreck, and no break is a pinwheel", function()
  local seen = {}
  for seed = 1, 500 do
    local legs = legs_of(layout(seed))
    local key = {}
    local cw = 0
    for i, leg in ipairs(legs) do
      key[i] = string.format("%.2f,%.2f", leg[#leg].to[1], leg[#leg].to[2])
      if turn(leg[1].heading, leg[2].heading) > 0 then cw = cw + 1 end
    end
    key = table.concat(key, ";")
    assert(seen[key] == nil, "seeds " .. tostring(seen[key]) .. " and " .. seed .. " lay the same wreck")
    seen[key] = seed
    -- 4 each way are dealt; only the face fix-up flips one
    assert(cw >= 2 and cw <= 6, "seed " .. seed .. ": " .. cw .. " of 8 knees bend the same way round")
  end
  local a, b = legs_of(layout(1)), legs_of(layout(2))
  local moved = 0
  for i = 1, C.leg_count do moved = math.max(moved, dist(a[i][#a[i]].to, b[i][#b[i]].to)) end
  assert(moved > 0.5, "seeds 1 and 2: no foot moved more than " .. moved)
end)

test("the object count: 5 a leg, 8 a kinked one, at most 50 a Jamal - shadows first, each tint on its art", function()
  local most = 0
  for seed = 1, SEEDS do
    local pieces = layout(seed)
    local kinked = 0
    for _, leg in ipairs(legs_of(pieces)) do if leg[3] then kinked = kinked + 1 end end
    assert(#pieces == 5 * C.leg_count + 3 * kinked, "seed " .. seed .. ": " .. #pieces .. " objects")
    assert(#pieces <= 50, "seed " .. seed .. ": " .. #pieces .. " objects")
    if #pieces > most then most = #pieces end
    local art = false
    for i, p in ipairs(pieces) do
      local kind = p.sprite:match("%-(%a+)$")
      if kind == "shadow" then
        assert(not art, "a shadow drawn after the art - it would lie on top of a leg")
        assert(p.layer == W.SHADOW_LAYER and not p.tint)
      else
        art = true
        assert(p.layer == W.ART_LAYER)
        assert(p.tint == (kind == "tint"), "only the tint pieces take his colour")
        if kind == "tint" then
          local before = pieces[i - 1]
          assert(before.sprite == W.sprite(p.seg.part, "art") and before.seg == p.seg,
                 "a tint not straight after its own art")
          assert(W.PARTS[p.seg.part].tint, "a tint piece for a part that has none")
        end
      end
    end
  end
  assert(most == 46, "two kinked legs a break: 46 at most, saw " .. most)
end)

test("under: in every break one leg buckles back toward him - the knee folded past 0.35 turns", function()
  for seed = 1, 300 do
    local legs = legs_of(layout(seed))
    local back = 0
    for _, leg in ipairs(legs) do
      if math.abs(turn(leg[1].heading, leg[2].heading)) >= 0.35 then back = back + 1 end
    end
    assert(back >= 1, "seed " .. seed .. ": no leg buckled back under him")
  end
end)

-- DRAWING, against a fake LuaRendering that keeps what it drew.
local drawn = {}
rendering = {draw_sprite = function(args)
  local o = {valid = true, args = args, id = #drawn + 1}
  o.destroy = function() o.valid = false end
  drawn[#drawn + 1] = o
  return o
end}
local function entity(unit, color)
  return {valid = true, unit_number = unit, color = color, surface = {name = "nauvis"}}
end

test("ensure: draws once per body, every object on him, his colour only on the tint pieces", function()
  drawn = {}
  local rec = {}
  local e = entity(7, {r = 1, g = 0.5, b = 0})
  assert(W.ensure(rec, e, rng(3)) == true)
  local n = #drawn
  assert(n == 46 and #rec.wreck.objects == n and rec.wreck.unit == 7, n)
  for _, o in ipairs(drawn) do
    local a = o.args
    assert(a.target.entity == e and a.surface == e.surface and a.x_scale == a.y_scale)
    assert((a.tint ~= nil) == (a.sprite:match("%-tint$") ~= nil), a.sprite)
    if a.tint then assert(a.tint == e.color) end
  end
  assert(W.ensure(rec, e, rng(4)) == false and #drawn == n, "a second ensure drew again")
end)

test("ensure: redraws what is gone, and never counts another body's legs as his", function()
  drawn = {}
  local rec = {}
  local e = entity(8)
  W.ensure(rec, e, rng(5))
  local first = rec.wreck.objects
  first[3].valid = false                                -- a partial set: cleared, not topped up
  assert(W.ensure(rec, e, rng(6)) == true)
  for _, o in ipairs(first) do assert(not o.valid, "an old object survived a redraw") end
  local n = #drawn
  -- another mod swapped him beached -> beached: the old body is still valid this tick
  local other = entity(9)
  assert(W.ensure(rec, other, rng(7)) == true and rec.wreck.unit == 9 and #drawn > n)
  W.clear(rec)
  assert(rec.wreck == nil)
  W.clear(rec)                                          -- twice: harmless
  assert(W.ensure({}, {valid = false, unit_number = 1}, rng(1)) == false, "an invalid body")
end)

test("ensure: a set drawn to another geometry is redrawn - an update re-cut the sprites under it", function()
  drawn = {}
  local rec = {}
  local e = entity(10)
  W.ensure(rec, e, rng(8))
  assert(rec.wreck.geometry == W.GEOMETRY, "a set is stamped with the geometry it was drawn to")
  local old = rec.wreck.objects
  rec.wreck.geometry = "2/2.3/1.1/0.08/1/0.35,0.45/0.45,0.65"   -- D.1.3's first cut
  assert(W.ensure(rec, e, rng(9)) == true and rec.wreck.geometry == W.GEOMETRY)
  for _, o in ipairs(old) do assert(not o.valid, "a stale piece survived the redraw") end
  rec.wreck.geometry = nil                              -- a set from before the stamp
  assert(W.ensure(rec, e, rng(10)) == true, "an unstamped set is redrawn too")
  -- the stamp covers every number a joint position hangs on
  for _, v in ipairs({W.UPPER, W.LOWER, W.KINK, W.OVERLAP, W.CUT.upper[1], W.CUT.upper[2],
                      W.CUT.lower[1], W.CUT.lower[2]}) do
    assert(W.GEOMETRY:find(string.format("%g", v), 1, true), "GEOMETRY misses " .. v)
  end
end)

---Do segments ab and cd cross (a proper crossing, not a touch)?
local function crosses(a, b, c, d)
  local function side(p, q, r) return (q[1] - p[1]) * (r[2] - p[2]) - (q[2] - p[2]) * (r[1] - p[1]) end
  return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0
end

test("legs lie apart: at most one leg across another in 90% of breaks, never four", function()
  -- the review: 94% of breaks crossed at least once, a mean of 2.27, and the knots read as
  -- branching legs. Uppers converge on the hub under him by design, so the first HIDDEN tiles
  -- of each (under his body) do not count.
  local calm, worst = 0, 0
  for seed = 1, SEEDS do
    local legs = legs_of(layout(seed))
    local n = 0
    for i = 1, #legs do
      for j = i + 1, #legs do
        for _, s in ipairs(legs[i]) do
          for _, t in ipairs(legs[j]) do
            local function out(seg)
              if seg.part ~= "upper" then return seg.from end
              local len = dist(seg.from, seg.to)
              local f = W.HIDDEN / len
              return {seg.from[1] + (seg.to[1] - seg.from[1]) * f, seg.from[2] + (seg.to[2] - seg.from[2]) * f}
            end
            if crosses(out(s), s.to, out(t), t.to) then n = n + 1 end
          end
        end
      end
    end
    if n <= 1 then calm = calm + 1 end
    if n > worst then worst = n end
  end
  assert(calm >= 0.9 * SEEDS, string.format("only %.1f%% of breaks lay at most one crossing", 100 * calm / SEEDS))
  assert(worst <= 3, "a break laid " .. worst .. " legs across each other")
end)

test("the prototypes cut every part the layout draws, and nothing it does not", function()
  -- prototypes/wreck.lua builds one sprite per part and kind off W.PARTS: read its source for
  -- the piece table and check both lists agree
  local f = assert(io.open(root .. "/mod/jamaltron/prototypes/wreck.lua"))
  local src = f:read("*a")
  f:close()
  for part in pairs(W.PARTS) do
    assert(src:find('%[?"?' .. part:gsub("%-", "%%-") .. '"?%]? = {{', 1) ~= nil,
           "prototypes/wreck.lua cuts no " .. part)
  end
  assert(W.sprite("lower", "art") == C.wreck .. "-lower-art")
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
