-- jamaltron spider-vehicle, its 8 legs, its corpse and its dying explosion:
-- deepcopies of the stock spidertron family, STOCK graphics and sounds.
-- Phase C swaps the sprite sheets, Phase D the sounds, guns and the beached variant.
--
-- Source of truth: /Applications/factorio.app/Contents/data/base/prototypes/entity/
-- entities.lua (create_spidertron at :9875, make_spidertron_leg at :91), remnants.lua
-- :3060, explosions.lua :5864. Verified against 2.1.17.
--
-- util.copy is load-bearing. `local body = data.raw[...]["spidertron"]` then
-- `body.name = "jamaltron"` would RENAME the base game's prototype in place and
-- corrupt the spidertron for every other mod.
--
-- Left pointing at shared base prototypes on purpose - correct until Phase D:
--   * equipment_grid = "spidertron-equipment-grid" (10x6; only clone it if the size
--     changes, and D.4's lossless swap needs jamaltron-beached to keep the same one)
--   * guns = the 4 spidertron rocket launchers (D.7 replaces them with a
--     flamethrower; the entry count is what sets the ammo inventory size)
--   * every icon path, including the item's icon_tintable pair (see item.lua)
--
-- The ---@type on each copy names the data.raw slot it came from. util.copy is
-- generic, so lua-language-server already infers these; writing them down is what
-- makes a copy re-pointed at the wrong raw type fail here instead of downstream.

local C = require("prototypes.shared")

---@type data.SpiderVehiclePrototype
local body = util.copy(data.raw["spider-vehicle"]["spidertron"])
body.name = C.name
-- minable.result is the one rename that HARD ERRORS when it dangles ("item with name
-- 'jamaltron' does not exist"); left as "spidertron" it silently hands you the wrong
-- item when mined. item.lua supplies the target.
body.minable.result = C.name
body.corpse = C.remnants
body.dying_explosion = C.explosion
body.localised_name = {"entity-name." .. C.name}
body.localised_description = {"entity-description." .. C.name}

-- The Factoriopedia entity name lives inside a Lua source STRING, so no amount of
-- grepping for `name =` finds it and a copy renders a stock spidertron on Jamal's page.
body.factoriopedia_simulation =
{
  init =
  [[
    game.simulation.camera_zoom = 1.3
    game.simulation.camera_position = {0, -1}
    game.surfaces[1].create_entity{name = "]] .. C.name .. [[", position = {0, 0}}
  ]]
}

-- The one annotation here that is not just documentation: an empty table literal
-- infers as an untyped table, so unannotated `legs[i] = <anything>` is accepted and
-- data:extend(legs) checks against `any`.
---@type data.SpiderLegPrototype[]
local legs = {}
for i = 1, C.leg_count do
  ---@type data.SpiderLegPrototype
  local leg = util.copy(data.raw["spider-leg"]["spidertron-leg-" .. i])
  leg.name = C.leg_name(i)
  -- make_spidertron_leg hardcodes {"entity-name.spidertron-leg"} because the leg
  -- prototype names have no locale keys of their own. Inherited, it reads
  -- "Spidertron leg" in every tooltip. `hidden = true` comes along in the copy and
  -- stays - 8 leg entries in Factoriopedia is noise.
  leg.localised_name = {"entity-name." .. C.name .. "-leg"}
  legs[i] = leg
  body.spider_engine.legs[i].leg = leg.name
  -- HARNESS, NOT CHASSIS. Stock mounts the legs to the corners of a machine
  -- (widest pair at +-25 px = +-0.781 tiles). Jamal's legs are strapped to him,
  -- so they emerge from a band around his girth and splay out to the ground.
  --
  -- 0.45 is MEASURED, not chosen: at the tuned shark (config 137972136a75, 4.07 x
  -- 2.47 tiles) it is the LARGEST ring where all 8 mounts land on his silhouette
  -- at all 16 sampled rotations. 0.50 leaves one mount off at one rotation.
  -- ground_position is deliberately NOT scaled - that is where the feet LAND, and
  -- shrinking it too would give him a mincing little stance instead of the
  -- splayed-from-a-harness silhouette. Narrow mounts, stock-width footprint.
  local mount = body.spider_engine.legs[i].mount_position
  mount[1], mount[2] = mount[1] * C.mount_shrink, mount[2] * C.mount_shrink
end

-- Cheap insurance on the cross-reference that breaks silently: a vehicle pointing at
-- spidertron-leg-N loads, spawns and walks, with our eight leg prototypes registered
-- and unused. Nothing tells you until Phase D puts shark legs in the sheets and a
-- spidertron leg shows up on screen.
for i, spec in pairs(body.spider_engine.legs) do
  assert(spec.leg == C.leg_name(i), "leg " .. i .. " still points at " .. spec.leg)
end
assert(#body.spider_engine.legs == C.leg_count,
  "expected " .. C.leg_count .. " legs, base gave " .. #body.spider_engine.legs)

---@type data.CorpsePrototype
local remnants = util.copy(data.raw["corpse"]["spidertron-remnants"])
remnants.name = C.remnants
remnants.localised_name = {"entity-name." .. C.remnants}

-- Cloned rather than shared because the spidertron-die-vox sound is played from the
-- explosion's created_effect, not from the entity - D.6 has to swap it here.
---@type data.ExplosionPrototype
local explosion = util.copy(data.raw["explosion"]["spidertron-explosion"])
explosion.name = C.explosion
-- Stock carries localised_name = {"dying-explosion-name", {"entity-name.spidertron"}},
-- which a copy renders as "Spidertron (dying explosion)". Reuse base's own template key
-- with our entity substituted in - caught by --dump-prototype-locale, invisible otherwise.
explosion.localised_name = {"dying-explosion-name", {"entity-name." .. C.name}}

data:extend({body, remnants, explosion})
data:extend(legs)
