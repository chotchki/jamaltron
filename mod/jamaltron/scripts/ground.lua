-- The GROUND TABLE (PLAN E.2.1): what a tile does to Jamal's feet. Outside speech/ because the
-- shore stall (speech/stall.lua) and the jump refusal (E.2.6) both read it.
--
-- tile name -> false (a foot stands on it) | the fluid it blocks with | "void" (blocks, no
-- fluid: out-of-map, empty-space, and water-wube - the one misfile, no fluid and nothing
-- generates it). A tile blocks when its collision layers intersect the LEG's mask; the body
-- collides only with `trigger_target` (so it places on deep water) and answers nothing. A fluid
-- alone decides nothing: water-shallow, water-mud, the 9 Gleba wetlands and all 4 Fulgora oil
-- oceans carry one and he walks across. MEASURED 2026-09-25, all 153 tiles in 2.1.17 + Space
-- Age: agrees 153/153 with LuaTile.collides_with, count_tiles_filtered and can_place_entity on
-- the leg.
--
-- The cache is the module state speech.lua's header allows: a pure function of the prototypes,
-- identical on every peer, rebuilt lazily after a load, never saved. Modded tiles come free.

local C = require("prototypes.shared")

local M = {}

---The value of a tile that blocks a foot and carries no fluid.
M.VOID = "void"

---tile name -> false | fluid name | M.VOID. nil until first use.
---@type table<string, string|false>?
local by_tile

---Every non-false value by_tile holds: the set a GROUND reason is drawn from.
---@type table<string, true>?
local values

---Both caches off the prototypes. All eight legs share one mask (measured), so leg 1 stands in.
---@return table<string, string|false> tiles
---@return table<string, true> values
local function build()
  local leg = prototypes.entity[C.leg_name(1)].collision_mask.layers
  local tiles, seen = {}, {}
  for name, tile in pairs(prototypes.tile) do
    local value = false ---@type string|false
    for layer in pairs(tile.collision_mask.layers) do
      if leg[layer] then
        value = tile.fluid and tile.fluid.name or M.VOID
        break
      end
    end
    tiles[name] = value
    if value then
      seen[value] = true
    end
  end
  return tiles, seen
end

---What tile `name` does to a foot: false when one stands on it, else the fluid it blocks
---with (`water`, `lava`, `ammoniacal-solution`, a modded fluid), else "void". A name with no
---prototype reads false. 0.32-0.42 us including the get_tile call (measured).
---@param name string
---@return string|false
function M.of(name)
  if by_tile == nil then
    by_tile, values = build()
  end
  return by_tile[name] or false
end

---Is `cond` a value M.of can return, i.e. the GROUND stopped him? say() uses it to latch the
---shore episode on a jump refusal. jump_refused's other reasons (`blocked`, `cooldown`, ...)
---are not, nor is a fluid no blocking tile carries (heavy-oil).
---@param cond string?
---@return boolean
function M.is_ground(cond)
  if values == nil then
    by_tile, values = build()
  end
  return cond ~= nil and values[cond] == true
end

return M
