-- D.7: Jamal's weapon - the flamethrower he fights with in book 7 (Velma, attacking.06) - in
-- place of the stock spidertron's four rocket launchers, and the custom event its stream raises
-- when it starts (prototypes/ammo.lua hangs it on the ammo; scripts/attack.lua listens).
--
-- A named copy of base's tank-flamethrower (base/prototypes/item.lua:3326, 2.1.17): stream
-- attack, ammo_category "flamethrower", range 9, min_range 3, cooldown 1. So he loads base
-- flamethrower-ammo, and the ammo's `vehicle` AmmoType (item.lua:2857) fires base's
-- tank-flamethrower-fire-stream (entity/fire.lua:1176): a radius-4 splash of 7 fire per landing
-- on force "all" - his own side included, see scripts/attack.lua. entity.lua mounts four.
-- ANOTHER MOD may have removed tank-flamethrower, or made it something but a stream, before this
-- runs (MEASURED: either one failed the whole load, "attempt to index local 'gun'" / an assert):
-- then his is built from 2.1.17's own numbers below: his weapon is a stream flamethrower whatever
-- became of the tank's. A tank-flamethrower that is still a stream is copied as it stands,
-- another mod's range or sound included.
--
-- RANGE, MEASURED against a small biter held still at each distance (headless, 400 ticks): he
-- engages at 2, 2.5, 3, 4, 6, 8, 9, 9.5 and 10 tiles centre to centre and never at 11 or 12,
-- and every engagement killed it. min_range 3 does not stop him closer in: the engine MOVES the
-- aim point out onto a ring (min_range + the box's half-diagonal, 4.41 tiles) centred on the
-- vehicle LIFTED by its height, so 1.5 tiles up-screen - stock stream behaviour, a stock
-- spidertron with a tank-flamethrower does it too (PLAN D.7.5, MEASURED). The torso bob moves
-- that ring every tick and each move starts a new stream, which is why a still target due north
-- inside ~5 tiles takes 7-14 streams at once; the tank has no bob and no height. The splash
-- (radius 4, every force) catches a foot within ~4 tiles of the aim point - ~1 HP a minute per
-- foot on stock legs, so his legs are FIRE-PROOF (entity.lua, D.7.5 (b)): 0 self-burn at every
-- bearing, his body keeps stock's fire 15/60 (attack.lua keeps his own splash out of `damaged`).
-- Rockets reached 36; a flame Jamal has to walk up to what he burns - and SPITTERS OUTRANGE HIM
-- (D.7 review, MEASURED): parked, he never fired at a spitter wave of any size and took 774-1166
-- a minute, and Gleba's strafers stand off at 21.5 tiles. Kept at 9 as PLAN D.7 asked, pending
-- chotchki's call.
-- Auto-targeting is the stock spidertron's (no prototype field; LuaEntity
-- vehicle_automatic_targeting_parameters reads {auto_target_without_gunner = true,
-- auto_target_with_gunner = false}): he fires by himself when nobody drives him, and with a
-- driver only when the driver shoots.
--
-- WHERE THE STREAM STARTS, MEASURED (D.7.4; shot.sh + the stream entity's position read back,
-- source = 2 * stream - target, over 8 aims x 8 torso facings):
--   * source = gun_center_shift + gun_barrel_length along the TORSO's facing - (0, height) -
--     0.008, in screen tiles from his position. The barrel rides the torso, never the aim
--   * so barrel 0 is ONE PIVOT: the same point for every facing and every aim. D.7.1's snout
--     ({0, -0.45} + 1.2) swung round his head and flamed a biter behind him over his own back
--   * {0, 0.15} starts it at (0, -1.36), under his belly - chotchki's pick off a height sweep
--     (render-out/review/flame/10-below-hub-heights.png): "a little lower" than the leg hub,
--     0.373 below it. The hub is the mounts' mean, {0, -0.223} -> (0, -1.72) on screen:
--     stock's 8 mounts (y mean -2.75 px) * C.mount_shrink - C.mount_lift, entity.lua's loop.
--     A literal, not derived from the hub: it is a point on a picture, and the fire harness's
--     O lanes hold the engine to (0, -1.36) +-0.1
--   * the vehicle's height (1.5, stock's) moves it 1:1. A body re-pack does not move it - it
--     moves his belly off it, which only a look catches
-- WHERE IT DRAWS, MEASURED: the stream renders above every render layer up to 'explosion', so
-- wherever it crosses him it painted over his body and legs whatever the origin. 'projectile'
-- is the lowest layer that beats it - entity.lua lifts the torso and all eight legs above it
-- (W1, the costs are there). Range is unchanged. His own splash barely moves (a behemoth held 6
-- tiles out, 240 ticks, facing east): 8.8-9.0 HP on NE/SE/S/SW/NW as before, 0 E and W (was
-- 4.4-4.6), ~33 aimed due north - where 11-14 streams stay alive at once and the target drops to
-- 83 of 3000 (2217-2238 on every other bearing). Both north findings predate D.7.4; not fixed.
-- A re-pick is tools/tests/test_gun.py's pins, then the fire harness's O lanes and a shot.sh
-- look: headless draws nothing.

local C = require("prototypes.shared")

---base's tank-flamethrower as 2.1.17 ships it (base/prototypes/item.lua:3326), for when another
---mod left none that is a stream.
---@type data.GunPrototype
local TANK_FLAMETHROWER = {
  type = "gun",
  name = "tank-flamethrower",
  icon = "__base__/graphics/icons/flamethrower.png",
  hidden = true,
  auto_recycle = false,
  subgroup = "gun",
  order = "b[flamethrower]-b[tank-flamethrower]",
  attack_parameters =
  {
    type = "stream",
    ammo_category = "flamethrower",
    cooldown = 1,
    gun_barrel_length = 1.4,
    gun_center_shift = {-0.17, -1.15},
    range = 9,
    min_range = 3,
    cyclic_sound =
    {
      begin_sound = {filename = "__base__/sound/fight/flamethrower-start.ogg", volume = 1},
      middle_sound = {filename = "__base__/sound/fight/flamethrower-mid.ogg", volume = 1},
      end_sound = {filename = "__base__/sound/fight/flamethrower-end.ogg", volume = 1}
    }
  },
  stack_size = 1
}

local source = data.raw["gun"]["tank-flamethrower"]
if not (source and source.attack_parameters and source.attack_parameters.type == "stream") then
  log("jamaltron: tank-flamethrower is gone or no longer a stream - his flamethrower is built "
      .. "from base 2.1.17's numbers instead")
  source = TANK_FLAMETHROWER
end
---@type data.GunPrototype
local gun = util.copy(source)
gun.name = C.gun
gun.localised_name = {"item-name." .. C.gun}
-- Sorts after the stock spider launchers ("z[spider]-a[rocket-launcher]"), with the hidden
-- spider guns.
gun.order = "z[spider]-b[" .. C.gun .. "]"

local ap = gun.attack_parameters
---@cast ap data.StreamAttackParameters
ap.gun_center_shift = {0, 0.15}
ap.gun_barrel_length = 0

-- The event name is ours alone: a custom event is raised to the mods that subscribe to it, not
-- to every on_script_trigger_effect handler in the game.
---@type data.CustomEventPrototype
local fired = {type = "custom-event", name = C.fired}

data:extend({gun, fired})
