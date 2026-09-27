-- His broken legs, lying round the beached body (PLAN D.1.3). chotchki 2026-09-26: "we need broken
-- legs around jamal", then "I think doing bent legs will look better but he's not destroyed so the
-- stock corpse doesn't fit". So: BENT, NOT SNAPPED. Eight legs, each ONE connected piece still
-- under him (the hub behind his gills, where every flop frame covers it), buckled at wrong angles
-- (a knee folded back or sideways, a kink mid-segment, one under him, one splayed). Nothing
-- severed, no gaps, no debris, no leg laid across another where a give avoids it. Broken but
-- repairable.
--
-- THE ART IS HIS OWN: the stock spidertron leg sheets his walking legs use, cut by reference from
-- __base__ (prototypes/wreck.lua), so no Wube PNG ships in this repo. One segment is ONE layered
-- sprite (ends + a cropped stretchable middle, the knee on the lower), which LuaRendering rotates
-- as a unit about its origin (rotate_shift off: MEASURED 2.1.17, with it the shifts turn twice).
-- Draw tint multiplies EVERY layer (measured), so the runtime-tinted ends are a second sprite
-- (not on the upper - see M.PARTS) and the shadow a third, offset where the sun puts it: 5
-- objects a leg, 8 a kinked one, 46 a Jamal (always two kinked legs a break).
--
-- TWO HALVES. layout() is pure (an rng in, a list of pieces out), so tools/tests/lua/test_wreck.lua
-- proves the geometry under plain lua. draw()/ensure() are the only functions that touch the game.
-- In game the rng is math.random, the MAP's generator: synced and saved, so every peer draws the
-- same wreck (the break roll already rides it).
--
-- LIFECYCLE: every object targets the beached ENTITY, so it dies with him (LuaRendering's docs:
-- "if an entity target of an object is destroyed ... the object is also destroyed"; measured
-- invalid the tick he is destroyed) on a repair, a death, another mod's swap, and persists across
-- save/load (measured). breakage.lua calls ensure() on every way a body becomes beached and keeps
-- the objects on its per-unit record; ensure() draws only when that record lacks a full set still
-- valid on THIS body drawn to today's M.GEOMETRY (an update that re-cut the sprites redraws on its
-- configuration change; the saved offsets would not meet). MOD REMOVAL: the docs say nothing
-- about a removed mod's objects as such, but removal deletes every beached body (its prototype is
-- ours), taking these with it by the rule above, and E.6.1 measured every render object of ours
-- gone. Nothing here runs per tick.

local C = require("prototypes.shared")

local M = {}

---Leg-sheet column every piece is cut from. The eight columns are the eight stock legs, lit for
---where each hangs; cut flat on the ground, one column reads the same as eight (the spike).
M.COLUMN = 1

---Segment lengths in tiles at spidertron scale 1 (his standing legs' scale). The upper runs from
---the hub under his girth, so ~0.7 of it is always under him; what shows keeps the wreck ~6 tiles
---across (the spike's full-length legs splayed ~10 and dwarfed him).
M.UPPER = 2.35
M.LOWER = 2.1
---A kinked lower bends this far from the knee: the middle of its stretchable part.
M.KINK = 1.0
---Stretchable halves of a kinked lower overlap by this much past the kink, so no wedge of sand
---shows through the outside of the bend.
M.OVERLAP = 0.08
---Where each segment's stretchable middle starts and stops, tiles in from its two joints
---(prototypes/wreck.lua cuts by these). The upper's starts AT the hip: its cut mouth is the hip,
---which his body covers in every flop frame (M.HUB).
M.CUT = {upper = {0, 0.45}, lower = {0.45, 0.65}}

---Where the pieces lie. Shadows under everything else on the ground; the art just above them,
---still under his body ("object"), so a leg buckled under him goes under him.
M.ART_LAYER = "lower-object-above-shadow"
M.SHADOW_LAYER = "lower-object"
---The shadow's offset: a flat pipe casts a thin one, down-sun (the spike's soft edge).
M.SHADOW = {0.12, 0.08}

---The hub every hip hangs from: behind his gills, the one patch his body covers in EVERY frame
---of the flop (tools/tests/test_wreck_cover.py measures it off the sheet's alpha: the heave lifts
---him ~0.6 tiles north, the curl drops his middle ~0.6 south, only this ridge stays under him
---through both). Hips spread along his flank left open pipe mouths on the sand for ~15 ticks of
---every leap (the review's burst, ticks 280-292); from here a leg is one pipe running out from
---under him in every frame. Each side's four hips sit M.HIP_STEP apart along the ridge, M.RIDGE
---its direction.
M.HUB = {-0.27, -0.13}
M.RIDGE = {0.8, 0.6}
M.HIP_STEP = 0.06
---Where the wreck is centred and how far any joint may lie from it: ~6 tiles across.
M.CENTER = {0.15, 0}
M.RADIUS = 3.4
---His face. No piece's centre may sit in it: legs round him, never over his eyes.
M.HEAD = {left = -1.6, top = -0.75, right = -0.45, bottom = 0.65}

---Headings (turns, 0 = north, clockwise) of the north-side legs west to east, then the south
---side. The two by his head lean back off it.
M.FAN = {0.85, 0.94, 0.03, 0.12, 0.65, 0.56, 0.47, 0.38}

---How each leg gave out: the knee's turn off straight (turns; which way is dealt, four each), and
---for a kink the lower's own bend (the other way: a zigzag, not a curl). `reach` scales the leg
---uniformly. One `under` and one `splayed` per break; the other six dealt M.REST.
---@type table<string, {knee: number[], kink: number[]?, reach: number[]?}>
M.KINDS = {
  folded = {knee = {0.22, 0.29}},                    -- knee folded back hard
  sideways = {knee = {0.14, 0.21}},                  -- knee bent flat out to one side
  kinked = {knee = {0.05, 0.10}, kink = {0.10, 0.15}},  -- a lower that bent in the middle
  under = {knee = {0.40, 0.45}, reach = {0.8, 0.9}},    -- buckled back under him
  splayed = {knee = {0.06, 0.11}, reach = {0.9, 1.0}},  -- flung out, hyperextended
}
M.REST = {"folded", "folded", "sideways", "sideways", "kinked", "kinked"}

---Legs apart: identical pipe art crossing on one layer knots into a tangle no leg can be traced
---through, and an X reads as a branching leg (the review: 94% of breaks crossed at least once).
---Two legs' segments closer than CLEAR tiles (a pipe is ~0.45 wide) are in contact; an upper's
---first HIDDEN tiles lie under him and converge on the hub by design, so they never count.
M.CLEAR = 0.3
M.HIDDEN = 0.9

---The pieces: one prototype per segment and kind (prototypes/wreck.lua builds them from M.PARTS).
---@param part "upper"|"lower"|"lower-a"|"lower-b"
---@param kind "art"|"tint"|"shadow"
---@return string
function M.sprite(part, kind)
  return C.wreck_sprite(part, kind)
end

---Each segment part, its origin the joint it hangs from, running +y (south) unrotated, so a part
---drawn at orientation `o` points along heading o + 0.5. `len` is origin to far joint. `tint`: it
---has a runtime-tinted piece worth an object. The upper's (its end at the knee) lies under the
---knee and the lower's end: 999 of 1.44M pixels at zoom 2, none visible (measured).
---@type table<string, {len: number, tint: boolean}>
M.PARTS = {
  upper = {len = M.UPPER, tint = false},
  lower = {len = M.LOWER, tint = true},
  ["lower-a"] = {len = M.KINK, tint = true},
  ["lower-b"] = {len = M.LOWER - M.KINK, tint = true},
}

---Everything a drawn segment's JOINTS depend on. The render objects keep their drawn offsets
---across save/load, while the sprites are re-cut from these numbers at every load: an update that
---moved one would leave every beached Jamal in a save with his legs pulled apart at the knee
---(measured: M.UPPER 2.0 -> 1.6, 92 objects kept byte-identical). ensure() redraws a set stamped
---with any other value. Anything prototypes/wreck.lua cuts by goes in.
M.GEOMETRY = string.format("%g/%g/%g/%g/%d/%g,%g/%g,%g", M.UPPER, M.LOWER, M.KINK, M.OVERLAP,
                           M.COLUMN, M.CUT.upper[1], M.CUT.upper[2], M.CUT.lower[1], M.CUT.lower[2])

-- LAYOUT -------------------------------------------------------------------------------------

---@alias Jamaltron.WreckRng fun(lo: integer, hi: integer): integer

---A uniform number in [lo, hi] off an integer rng (math.random(lo, hi)'s shape, so the map's
---generator and a test's seeded one plug in alike).
---@param rng Jamaltron.WreckRng
---@param lo number
---@param hi number
---@return number
local function uniform(rng, lo, hi)
  return lo + (hi - lo) * rng(0, 4096) / 4096
end

---orientation (turns, 0 = north, clockwise) -> unit vector in map space (+y south)
---@param h number
---@return number, number
local function dir(h)
  local r = h * 2 * math.pi
  return math.sin(r), -math.cos(r)
end

---@param p number[]
---@param h number heading
---@param len number
---@return number[]
local function step(p, h, len)
  local dx, dy = dir(h)
  return {p[1] + dx * len, p[2] + dy * len}
end

---@param p number[]
---@return boolean
local function in_head(p)
  local h = M.HEAD
  return p[1] > h.left and p[1] < h.right and p[2] > h.top and p[2] < h.bottom
end

---@param p number[]
---@return number
local function from_center(p)
  return math.sqrt((p[1] - M.CENTER[1]) ^ 2 + (p[2] - M.CENTER[2]) ^ 2)
end

---@class Jamaltron.WreckSegment
---@field part "upper"|"lower"|"lower-a"|"lower-b"
---@field from number[] the joint it hangs from, tiles from the entity
---@field to number[] its far joint
---@field heading number turns
---@field scale number its size over the part's own (the leg's `reach`, uniform)

---One leg's joint chain: hip -> knee (-> kink) -> foot, as segments.
---@param hip number[]
---@param h number the upper's heading
---@param knee number the lower's turn off it
---@param kink number? a kinked lower's own turn at M.KINK
---@param reach number length scale
---@return Jamaltron.WreckSegment[]
local function chain(hip, h, knee, kink, reach)
  local segs = {}
  local k = step(hip, h, M.UPPER * reach)
  segs[1] = {part = "upper", from = hip, to = k, heading = h % 1, scale = reach}
  local h2 = (h + knee) % 1
  if kink then
    local bend = step(k, h2, M.KINK * reach)
    segs[2] = {part = "lower-a", from = k, to = bend, heading = h2, scale = reach}
    local h3 = (h2 + kink) % 1
    segs[3] = {part = "lower-b", from = bend, to = step(bend, h3, (M.LOWER - M.KINK) * reach),
               heading = h3, scale = reach}
  else
    segs[2] = {part = "lower", from = k, to = step(k, h2, M.LOWER * reach), heading = h2,
               scale = reach}
  end
  return segs
end

---Does this leg keep off his face and inside the footprint? Every joint inside M.RADIUS, and no
---segment's midpoint (where its sprite sits thickest) on his face.
---@param segs Jamaltron.WreckSegment[]
---@return boolean clear
---@return boolean inside
local function fits(segs)
  local clear, inside = true, true
  for _, s in ipairs(segs) do
    local mid = {(s.from[1] + s.to[1]) / 2, (s.from[2] + s.to[2]) / 2}
    if in_head(mid) or in_head(s.to) then clear = false end
    if from_center(s.to) > M.RADIUS then inside = false end
  end
  return clear, inside
end

---The part of a segment that shows: an upper less its first M.HIDDEN tiles.
---@param s Jamaltron.WreckSegment
---@return number[] from
---@return number[] to
local function shown(s)
  if s.part ~= "upper" then return s.from, s.to end
  local len = M.UPPER * s.scale
  local t = math.min(M.HIDDEN / len, 1)
  return {s.from[1] + (s.to[1] - s.from[1]) * t, s.from[2] + (s.to[2] - s.from[2]) * t}, s.to
end

---Distance from point p to segment ab.
---@param p number[]
---@param a number[]
---@param b number[]
---@return number
local function to_segment(p, a, b)
  local dx, dy = b[1] - a[1], b[2] - a[2]
  local l2 = dx * dx + dy * dy
  local t = l2 > 0 and ((p[1] - a[1]) * dx + (p[2] - a[2]) * dy) / l2 or 0
  t = math.max(0, math.min(1, t))
  local ex, ey = a[1] + dx * t - p[1], a[2] + dy * t - p[2]
  return math.sqrt(ex * ex + ey * ey)
end

---Do segments ab and cd cross?
---@return boolean
local function crosses(a, b, c, d)
  local function side(p, q, r) return (q[1] - p[1]) * (r[2] - p[2]) - (q[2] - p[2]) * (r[1] - p[1]) end
  return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0
end

---Distance between segments ab and cd (0 when they cross).
---@return number
local function between(a, b, c, d)
  if crosses(a, b, c, d) then return 0 end
  return math.min(to_segment(a, c, d), to_segment(b, c, d), to_segment(c, a, b), to_segment(d, a, b))
end

---Contacts between one leg and the legs already laid: a crossing counts five, a touch one.
---@param segs Jamaltron.WreckSegment[]
---@param placed Jamaltron.WreckSegment[][]
---@return number
local function contacts(segs, placed)
  local n, r = 0, M.CLEAR
  for _, s in ipairs(segs) do
    local a, b = shown(s)
    for _, other in ipairs(placed) do
      for _, t in ipairs(other) do
        local c, d = shown(t)
        -- boxes apart by CLEAR or more cannot touch: most pairs stop here
        if math.max(c[1], d[1]) > math.min(a[1], b[1]) - r and math.min(c[1], d[1]) < math.max(a[1], b[1]) + r
            and math.max(c[2], d[2]) > math.min(a[2], b[2]) - r and math.min(c[2], d[2]) < math.max(a[2], b[2]) + r then
          local gap = between(a, b, c, d)
          if gap == 0 then n = n + 5 elseif gap < r then n = n + 1 end
        end
      end
    end
  end
  return n
end
M.contacts = contacts

---Does this leg's knee turn clockwise?
---@param segs Jamaltron.WreckSegment[]
---@return boolean
local function clockwise(segs)
  local d = (segs[2].heading - segs[1].heading) % 1
  return d > 0 and d < 0.5
end

---One leg's chain, off his face and inside the footprint. Off his face: bend the other way, then
---turn off it. Inside the footprint: shorten the leg, then fold the knee further (folding first
---curled every long leg in - seen, iteration 4). Bounded; no rng spent.
---@param north boolean the leg lies north of him (his face is WEST: north legs turn clockwise off it)
---@return Jamaltron.WreckSegment[] segs
---@return boolean fits
local function settle(hip, h, knee, kink, reach, north)
  local segs = chain(hip, h, knee, kink, reach)
  local clear, inside = fits(segs)
  if not clear then
    knee = -knee
    if kink then kink = -kink end
    segs = chain(hip, h, knee, kink, reach)
    clear, inside = fits(segs)
  end
  for _ = 1, 32 do
    if clear and inside then break end
    if not clear then
      h = h + (north and 0.02 or -0.02)
    elseif reach > 0.8 then
      reach = reach * 0.95
    elseif math.abs(knee) < 0.45 then
      knee = knee + (knee < 0 and -0.03 or 0.03)
    else
      h = h + (north and 0.02 or -0.02)       -- folded all it can: swing it round
    end
    segs = chain(hip, h, knee, kink, reach)
    clear, inside = fits(segs)
  end
  return segs, clear and inside
end

---The ways a leg may give to keep off the legs already laid, cheapest first: turned a little
---either way, bent less, drawn in shorter, and last bent the other way (it tips the balance of
---knees toward a pinwheel). The cheapest that touches least wins, so the search stops at the
---first give costing more than the best found.
---@type {flip: boolean, dh: number, bend: number, reach: number, cost: number, order: integer?}[]
M.GIVES = {}
for _, flip in ipairs({false, true}) do
  for _, reach in ipairs({1, 0.88}) do
    for _, bend in ipairs({1, 0.7, 0.5}) do
      for _, dh in ipairs({0, 0.03, -0.03, 0.06, -0.06, 0.09, -0.09}) do
        M.GIVES[#M.GIVES + 1] = {flip = flip, dh = dh, bend = bend, reach = reach,
                                 cost = (flip and 2.5 or 0) + (1 - bend) * 3
                                   + (reach < 1 and 1 or 0) + math.abs(dh) * 15}
      end
    end
  end
end
for i, g in ipairs(M.GIVES) do g.order = i end
table.sort(M.GIVES, function(a, b)
  if a.cost ~= b.cost then return a.cost < b.cost end
  return a.order < b.order
end)

---One break's wreck: the eight legs as joint chains. Deterministic for a given rng; every leg is
---connected (each segment starts where the previous ends), bent, inside M.RADIUS, off his face,
---and clear of the legs before it where any give in M.GIVES allows. The rng is only asked for
---integers (math.random(lo, hi)), the same number of times every break.
---
---VARIATION, all off the rng: the whole fan turned a little, mirrored north-south or not, which
---leg buckles under and which splays out, the rest dealt folded / sideways / kinked, and each
---leg's hip, heading, bend angles, bend side and length jittered.
---@param rng Jamaltron.WreckRng
---@return Jamaltron.WreckSegment[][]
function M.legs(rng)
  local turn = uniform(rng, -0.025, 0.025)
  local mirror = rng(0, 1) == 1
  -- deal the kinds: `under` and `splayed` somewhere, the rest shuffled into the other six
  local kinds = {}
  local rest = {}
  for i, k in ipairs(M.REST) do rest[i] = k end
  for i = #rest, 2, -1 do
    local j = rng(1, i)
    rest[i], rest[j] = rest[j], rest[i]
  end
  local under = rng(1, 8)
  local splayed = rng(1, 7)
  if splayed >= under then splayed = splayed + 1 end
  local r = 0
  for i = 1, C.leg_count do
    if i == under then kinds[i] = "under"
    elseif i == splayed then kinds[i] = "splayed"
    else r = r + 1; kinds[i] = rest[r] end
  end
  -- Which way each knee gave, per side of him, west to east: the first `k` toward his head, the
  -- rest toward his tail. Two neighbours bending INTO each other cross (the review: 94% of breaks
  -- crossed with the four-and-four deal), so each side's legs only part in the middle, never
  -- meet. The two sides' splits stay within one of each other: north all tailward with south all
  -- headward turns every knee one way round, a pinwheel (seen, iterations 2-4).
  local split_n = rng(0, 4)
  local split_s = rng(math.max(0, split_n - 1), math.min(4, split_n + 1))
  local sides = {}
  for j = 1, 4 do
    -- a knee turning clockwise sends a north leg's lower east, a south leg's west
    sides[j] = j <= split_n and -1 or 1
    sides[j + 4] = j <= split_s and 1 or -1
  end

  -- knees laid clockwise so far, and still to come as dealt (a mirror turns every one round)
  local cw = 0
  local function dealt_cw(i)
    local n = 0
    for j = i + 1, C.leg_count do
      if (sides[j] > 0) ~= mirror then n = n + 1 end
    end
    return n
  end

  local legs = {}
  for i = 1, C.leg_count do
    local kind = M.KINDS[kinds[i]]
    -- the hub is not mirrored: it is where his body covers, whichever side a leg lies
    local along = ((i - 1) % 4 - 1.5) * M.HIP_STEP + uniform(rng, -0.02, 0.02)
    local hip = {M.HUB[1] + M.RIDGE[1] * along, M.HUB[2] + M.RIDGE[2] * along}
    local h = M.FAN[i] + turn + uniform(rng, -0.035, 0.035)
    local side = sides[i]
    local knee = side * uniform(rng, kind.knee[1], kind.knee[2])
    local kink = kind.kink and -side * uniform(rng, kind.kink[1], kind.kink[2]) or nil
    local reach = kind.reach and uniform(rng, kind.reach[1], kind.reach[2])
      or uniform(rng, 0.85, 1.0)
    local north = i <= 4
    if mirror then
      h, knee, north = 0.5 - h, -knee, not north
      if kink then kink = -kink end
    end
    -- Every give, settled onto his face and footprint rules, scored on the legs already laid and
    -- the knees' balance: 2-6 each way round is a hard floor, 3-5 what a flip may leave and any
    -- give should (the face's own flip, by his head, tipped 1 break in 170 to 1-7).
    local best, best_cost, best_cw = nil, math.huge, 0
    for _, give in ipairs(M.GIVES) do
      if give.cost >= best_cost then break end
      local s = give.flip and -1 or 1
      local k = s * math.max(math.abs(knee) * give.bend, kind.knee[1]) * (knee < 0 and -1 or 1)
      local segs, ok = settle(hip, h + give.dh, k, kink and s * kink or nil, reach * give.reach, north)
      local way = clockwise(segs) and 1 or 0
      local balance = cw + way + dealt_cw(i)
      local cost = give.cost + 10 * contacts(segs, legs) + (ok and 0 or 1000)
        + ((balance < 2 or balance > 6) and 500 or 0)
        + ((balance < 3 or balance > 5) and (give.flip and 500 or 20) or 0)
      if cost < best_cost then best, best_cost, best_cw = segs, cost, way end
    end
    cw = cw + best_cw
    legs[i] = best --[[@as Jamaltron.WreckSegment[] ]]
  end
  return legs
end

---@class Jamaltron.WreckPiece
---@field sprite string
---@field offset number[] from the entity position, tiles
---@field orientation number
---@field scale number both axes: the engine scales a rotated sprite in SCREEN axes (measured: a
---lone y_scale on a leg lying east-west squashed its width and split its layers), so only a
---uniform scale keeps a segment in one piece
---@field layer string
---@field tint boolean take the entity's colour
---@field leg integer
---@field seg Jamaltron.WreckSegment

---The draw list for a set of legs: every shadow first (under everything), then each leg's art,
---segment by segment from the hip out, each followed by its tint, so the lower (knee on top) lies
---over the upper's end and a later leg over an earlier one.
---@param legs Jamaltron.WreckSegment[][]
---@return Jamaltron.WreckPiece[]
function M.pieces(legs)
  local out = {}
  local function add(leg, s, kind, layer, dx, dy)
    out[#out + 1] = {sprite = M.sprite(s.part, kind), offset = {s.from[1] + dx, s.from[2] + dy},
                     orientation = (s.heading - 0.5) % 1, scale = s.scale, layer = layer,
                     tint = kind == "tint", leg = leg, seg = s}
  end
  for i, segs in ipairs(legs) do
    for _, s in ipairs(segs) do add(i, s, "shadow", M.SHADOW_LAYER, M.SHADOW[1], M.SHADOW[2]) end
  end
  for i, segs in ipairs(legs) do
    for _, s in ipairs(segs) do
      add(i, s, "art", M.ART_LAYER, 0, 0)
      if M.PARTS[s.part].tint then add(i, s, "tint", M.ART_LAYER, 0, 0) end
    end
  end
  return out
end

---One break's pieces off `rng`.
---@param rng Jamaltron.WreckRng
---@return Jamaltron.WreckPiece[]
function M.layout(rng)
  return M.pieces(M.legs(rng))
end

-- DRAWING ------------------------------------------------------------------------------------

---Draw `pieces` on `entity`. The tint pieces take his colour, like his standing legs' tinted ends
---(a body with no colour leaves them the mask's own grey).
---@param entity LuaEntity
---@param pieces Jamaltron.WreckPiece[]
---@return LuaRenderObject[]
function M.draw(entity, pieces)
  local objects = {}
  local color = entity.color
  for _, p in ipairs(pieces) do
    objects[#objects + 1] = rendering.draw_sprite{
      sprite = p.sprite, target = {entity = entity, offset = p.offset}, surface = entity.surface,
      orientation = p.orientation, x_scale = p.scale, y_scale = p.scale, render_layer = p.layer,
      tint = p.tint and color or nil,
    }
  end
  return objects
end

---@class Jamaltron.Wreck
---@field unit integer the body they were drawn on
---@field geometry string? the M.GEOMETRY they were drawn to (nil: before it was stamped)
---@field objects LuaRenderObject[]

---Destroy whatever `rec.wreck` still holds, and forget it.
---@param rec {wreck: Jamaltron.Wreck?}
function M.clear(rec)
  local w = rec.wreck
  rec.wreck = nil
  if w == nil then return end
  for _, o in ipairs(w.objects) do
    if o.valid then o.destroy() end
  end
end

---Are the legs `rec` holds drawn on `entity`, to today's geometry, every one still there?
---@param rec {wreck: Jamaltron.Wreck?}
---@param entity LuaEntity
---@return boolean
function M.drawn(rec, entity)
  local w = rec.wreck
  if w == nil or w.unit ~= entity.unit_number or w.geometry ~= M.GEOMETRY or #w.objects == 0 then
    return false
  end
  for _, o in ipairs(w.objects) do
    if not o.valid then return false end
  end
  return true
end

---breakage.lua, on every way a body becomes beached and every configuration change (adopt_all):
---draw his legs on `entity` unless `rec` already holds a full set on it drawn to today's
---M.GEOMETRY. A partial set (never seen; they die together) or one whose sprites an update re-cut
---is cleared and redrawn as a fresh layout, never topped up. `rng` defaults to the map's
---math.random.
---@param rec {wreck: Jamaltron.Wreck?}
---@param entity LuaEntity
---@param rng Jamaltron.WreckRng?
---@return boolean drew
function M.ensure(rec, entity, rng)
  if not (entity.valid and entity.unit_number) or M.drawn(rec, entity) then return false end
  M.clear(rec)
  rec.wreck = {unit = entity.unit_number --[[@as integer]], geometry = M.GEOMETRY,
               objects = M.draw(entity, M.layout(rng or math.random))}
  return true
end

return M
