-- D.1.3's broken legs: the SpritePrototypes scripts/wreck.lua lays round a beached Jamal. Cut BY
-- REFERENCE from the __base__ spidertron leg sheets - the exact art his walking legs wear - so no
-- Wube PNG is copied into this repo (graphics/LICENSE covers only our own renders).
--
-- ONE SPRITE PER SEGMENT AND KIND, not one per sheet piece: a segment's ends and its stretchable
-- middle are LAYERS of one sprite, laid the way base/prototypes/entity/spidertron-animations.lua
-- lays a leg part (its offsets and shifts, below), with the middle CROPPED to length instead of
-- stretched - a sprite has no per-axis layer scale. The origin is the joint the segment hangs
-- from and it runs +y, so LuaRendering's orientation swings it about that joint. That keeps a
-- wreck at 5 objects a leg (8 kinked) instead of the spike's 13: 11 prototypes in all.
--
-- Kinds: `art` (row 1), `tint` (row 3, the runtime-tint masks on the ends and the knee - drawn
-- tinted with his colour, since a draw tint multiplies every layer of a sprite), `shadow` (row 2,
-- draw_as_shadow). Segments: `upper` (hip to knee; no hip end - that is under him, and drawn it
-- ringed his back like a second harness; its middle runs from the hip itself), `lower` (knee to
-- foot, the knee on top), and a kinked lower's two halves `lower-a` / `lower-b`, cut from ONE
-- continuous strip of the stretchable so the kink reads as a bend in one pipe.
--
-- Lengths come from scripts/wreck.lua, which is pure and has no game state at load.

local W = require("scripts.wreck")

local SHEET = "__base__/graphics/entity/spidertron/legs/spidertron-legs-"
---Sheet pieces (spidertron-animations.lua's definitions at spidertron scale 1): size, scale,
---x shift in pixels, and which rows it has (stretchables have no tint row).
local SRC = {
  ["upper-B"] = {file = "upper-end-B", w = 38, h = 58, scale = 0.5, dx = 0.5, tint = true},
  ["upper-m"] = {file = "upper-stretchable", w = 60, h = 256, scale = 0.25, dx = -1.5},
  ["lower-A"] = {file = "lower-end-A", w = 40, h = 98, scale = 0.5, dx = 0.5, tint = true},
  ["lower-m"] = {file = "lower-stretchable", w = 50, h = 384, scale = 0.25, dx = 0.5},
  ["lower-B"] = {file = "lower-end-B", w = 34, h = 92, scale = 0.5, dx = 0, tint = true},
  knee = {file = "knee", w = 22, h = 28, scale = 0.5, dx = 0.5, tint = true},
}
local ROW = {art = 0, shadow = 1, tint = 2}

-- The stretchables' spans along a segment (W.CUT: the upper's runs from the hip itself, so its
-- cut mouth lies under him - scripts/wreck.lua's M.HUB), and where the end pieces sit (their
-- shift along the leg, spidertron-animations.lua).
local UPPER_M = {W.CUT.upper[1], W.UPPER - W.CUT.upper[2]}
local LOWER_M = {W.CUT.lower[1], W.LOWER - W.CUT.lower[2]}
local UPPER_B = W.UPPER - 9 / 32
local LOWER_A = 19.5 / 32
local LOWER_B = W.LOWER - 21 / 32

---Pixels of stretchable per tile of segment: the sheet is drawn at scale 0.25.
local PX = 32 / 0.25

---One layer: sheet piece `key` in `kind`, centred `at` tiles down the segment. A stretchable
---takes `span` = the stretch of middle it covers, in the segment's own coords, and `strip` = the
---segment coords its source strip starts at, so two halves of one lower cut one continuous strip.
---@param key string
---@param kind "art"|"tint"|"shadow"
---@param at number?
---@param span number[]?
---@param strip number[]?
---@return data.Sprite
local function layer(key, kind, at, span, strip)
  local s = SRC[key]
  local x, y, h = s.w * (W.COLUMN - 1), s.h * ROW[kind], s.h
  if span then
    strip = strip or span
    -- centre the whole middle in the sheet, then take this span's slice of it
    local whole = math.floor((strip[2] - strip[1]) * PX + 0.5)
    assert(whole <= s.h, key .. ": a middle of " .. whole .. " px is longer than the sheet's " .. s.h)
    local from = math.floor((s.h - whole) / 2 + (span[1] - strip[1]) * PX + 0.5)
    h = math.floor((span[2] - span[1]) * PX + 0.5)
    y = y + from
    at = (span[1] + span[2]) / 2
  end
  return {filename = SHEET .. s.file .. ".png", x = x, y = y, width = s.w, height = h,
          scale = s.scale, shift = {s.dx / 32, at}, flags = {"no-crop"},
          draw_as_shadow = kind == "shadow" or nil}
end

---A segment's layers in `kind`, bottom to top: the stretchable first so the ends cover its cut
---edges, then the ends, the knee last. `tint` keeps only the pieces that have a mask row.
---@param list {[1]: string, [2]: number?, [3]: number[]?, [4]: number[]?}[]
---@param kind "art"|"tint"|"shadow"
---@return data.Sprite[]
local function layers(list, kind)
  local out = {}
  for _, l in ipairs(list) do
    if kind ~= "tint" or SRC[l[1]].tint then
      out[#out + 1] = layer(l[1], kind, l[2], l[3], l[4])
    end
  end
  return out
end

local K, OV = W.KINK, W.OVERLAP
---@type table<string, {[1]: string, [2]: number?, [3]: number[]?, [4]: number[]?}[]>
local PARTS = {
  upper = {{"upper-m", nil, UPPER_M}, {"upper-B", UPPER_B}},
  lower = {{"lower-m", nil, LOWER_M}, {"lower-A", LOWER_A}, {"lower-B", LOWER_B}, {"knee", 0}},
  ["lower-a"] = {{"lower-m", nil, {LOWER_M[1], K + OV}, LOWER_M}, {"lower-A", LOWER_A}, {"knee", 0}},
  -- the far half hangs from the kink: its coords are the lower's minus K
  ["lower-b"] = {{"lower-m", nil, {-OV, LOWER_M[2] - K}, {LOWER_M[1] - K, LOWER_M[2] - K}},
                 {"lower-B", LOWER_B - K}},
}

local sprites = {}   ---@type data.SpritePrototype[]
for part, spec in pairs(W.PARTS) do
  assert(PARTS[part], "scripts/wreck.lua names a part prototypes/wreck.lua does not cut: " .. part)
  for kind in pairs(ROW) do
    if kind ~= "tint" or spec.tint then
      sprites[#sprites + 1] = {type = "sprite", name = W.sprite(part, kind),
                               layers = layers(PARTS[part], kind)}
    end
  end
end
data:extend(sprites)
