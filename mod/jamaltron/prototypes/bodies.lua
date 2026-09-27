-- D.1's other two bodies: jamaltron-beached (legs broken, E.4 until E.5 repairs him) and
-- jamaltron-airborne (the ~30-tick jump arc, E.1). scripts/swap.lua moves Jamal between these
-- and the vehicle, so they copy THE VEHICLE, not the stock spidertron.
--
-- Loaded from data-final-fixes.lua, never data.lua: each is a deepcopy of the FINAL jamaltron,
-- so every edit another mod made to him in data or data-updates rides along (a bigger trunk, a
-- new grid, D.7's flamethrower - which beached mounts disarmed, D.7.3). Limit: a mod whose OWN
-- data-final-fixes runs after ours edits the vehicle and not these. The asserts below cannot
-- see that; the swap's stash absorbs a drifted body without losing an item (D.4 S3).
--
-- BOTH ARE SPIDER-VEHICLES (D.4.6): remote selections and quickbar remotes hold spider-vehicles
-- only, so a car-type body would drop out of both mid-jump.
--
-- BOTH ARE IMMOBILE BY PROTOTYPE (DEAD_ENGINE, the D.4.6 spike's answer), so D.4's body table
-- leaves them ENABLED: no disabled_by_script, so no frozen toolbelt, no missing vehicle_storage
-- point and no disabled airborne body landing frozen for good.
--
-- NEITHER CAN BE MADE FROM AN ITEM OR TURNED INTO ONE: no item, no recipe, no placeable_by, not
-- minable (a minable beached body would hand the player a jamaltron item to place fresh and
-- skip E.5's repair). Mining from SCRIPT still works - MEASURED: LuaEntity.mine{} empties the
-- trunk and deletes the body with no item back, and LuaEntity.minable reads true. Ask
-- prototype.mineable_properties.minable, never entity.minable, whether a body mines.

local C = require("prototypes.shared")
local disarm = require("prototypes.disarm")
-- THE FLOP (C.21's sequence, packed by pack.py --config render/beached.toml): GENERATED, so
-- every width, shift and frame_sequence comes from there and none is retyped here (entity.lua's
-- sprites_generated require has why).
local flop = require("prototypes.beached_sprites_generated")

---@type data.SpiderVehiclePrototype
local vehicle = data.raw["spider-vehicle"][C.name]
assert(vehicle, "data-final-fixes: no " .. C.name .. " left to build the other bodies from")

-- E.1's ONE LINE, true since E.1: the airborne body draws as NOTHING - body, shadow, reflection,
-- lights and its eight legs with their footfall dust and step sound - so the arc scripts/jump.lua
-- draws with `rendering` (his sheets, lifted off this body) is the only Jamal on screen for the
-- ~30 ticks he is up. false also draws the standing Jamal on the ground under it. MEASURED both
-- ways, a body made and teleported 0.3 tiles a tick from the same tick (E.1's takeoff): visible,
-- its legs re-lay against the body like a fresh vehicle's, up to 5.1 tiles over ~35 ticks - a
-- spider scrambling in mid-air; invisible, they never move against it. Blank art also pins the
-- orientation (ONE DIRECTION, under BEACHED): the heading rides on torso_orientation.
local AIRBORNE_INVISIBLE = true

---IMMOBILE BY PROTOTYPE, AND STILL ENABLED: a burner with no fuel slot can never burn, so the
---engine never gets the energy to walk. MEASURED 2.1.17 + SA, 600 ticks each, vs a plain
---jamaltron that covered 127 tiles driven and reached its 20-tile destination:
---  * 0.000 tiles with a driver holding a direction, 0.000 with an autopilot destination (still
---    set 600 ticks on). The torso does not turn either.
---  * status `no_fuel`, active = true. A disabled_by_script body in the same run lost its
---    toolbelt slots for good (trunk 80, not 90), its vehicle_storage point and its roboport
---    network, and its guns went quiet. This one kept all four: trunk 90 at t+1, both logistic
---    points, 10 robots in the network, the grid charging, and it shot a biter dead.
---Rejected in the same spike: frozen legs (movement 0 - drifts 5.2 tiles, settles 2.4 off),
---weight and friction 1e9, 1 W movement consumption (all three walk normally), no legs at all
---and an empty fuel_categories (both data-stage errors).
---
---render_no_power_icon = false kills the flashing no-fuel icon over him (the docs say it
---covers burners; headless draws nothing, so play.sh has to see it). E.4 sets custom_status,
---or the GUI says "No fuel" about a shark with broken legs. The category is moot with no slot.
---@type data.BurnerEnergySource
local DEAD_ENGINE = {type = "burner", fuel_categories = {"chemical"}, fuel_inventory_size = 0,
                     auto_refuel = false, render_no_power_icon = false}

---What a body must share with the vehicle or the swap loses things (D.4.6): the swap moves
---trunk, trash and ammo slot by slot and re-puts the grid, so a smaller trunk strands items, a
---gunless body destroys the ammo and errors on selected_gun_index, another grid fails the put.
---Guns are compared in ORDER because selected_gun_index is a position in that list, and by AMMO
---CATEGORY, not name: the slot's category decides what ammo it holds, and the beached body's
---guns are disarmed twins (D.7.3). MEASURED: renamed guns with the same categories keep every
---ammo slot and selected_gun_index across a break and a repair. Copies agree by construction;
---this is what stops an edit below from making one that does not.
---@param body data.SpiderVehiclePrototype
local function assert_holds_what_he_holds(body)
  local function same(field, a, b)
    assert(a == b, body.name .. " " .. field .. " is " .. tostring(a) .. ", " .. C.name
      .. " has " .. tostring(b) .. " - the swap would strand what does not fit (PLAN D.4.6)")
  end
  same("inventory_size", body.inventory_size, vehicle.inventory_size)
  same("trash_inventory_size", body.trash_inventory_size or 0, vehicle.trash_inventory_size or 0)
  same("equipment_grid", body.equipment_grid, vehicle.equipment_grid)
  local mine, his = body.guns or {}, vehicle.guns or {}
  same("gun count", #mine, #his)
  for i = 1, #his do
    same("gun " .. i .. " ammo categories", disarm.categories(data.raw["gun"][mine[i]]),
         disarm.categories(data.raw["gun"][his[i]]))
  end
end

---A body: the vehicle, renamed, unmade-able, immobile. Graphics and legs are the caller's.
---@param name data.EntityID
---@return data.SpiderVehiclePrototype
local function body_of(name)
  ---@type data.SpiderVehiclePrototype
  local body = util.copy(vehicle)
  body.name = name
  body.localised_name = {"entity-name." .. name}
  body.localised_description = {"entity-description." .. name}
  body.minable = nil
  -- A decon planner dragged over a beached Jamal would otherwise mark him (MEASURED: the mark
  -- takes on a non-minable body) and send bots at a body that mines into nothing. The swap's
  -- order_deconstruction onto these bodies returns false, as intended.
  local flags = body.flags or {}
  local has = {}
  for _, flag in pairs(flags) do
    has[flag] = true
  end
  for _, flag in pairs({"not-deconstructable", "not-blueprintable"}) do
    if not has[flag] then
      flags[#flags + 1] = flag
    end
  end
  body.flags = flags
  body.energy_source = util.copy(DEAD_ENGINE)
  -- Out of Factoriopedia, and anything that opens it on one of them opens Jamal's page instead.
  body.hidden = true
  body.factoriopedia_alternative = C.name
  body.factoriopedia_simulation = nil
  return body
end

---Give `body` eight legs of its own, copied from the vehicle's final legs. Own prototypes
---because leg art lives on the LEG prototype: hiding beached's legs on jamaltron's would hide
---the vehicle's. `visible = false` drops the leg art, the footfall trigger (dust + thud) and the
---step sound; the mounts and feet stay where the vehicle's are. Names: C.body_leg_name.
---@param body data.SpiderVehiclePrototype
---@param visible boolean
---@return data.SpiderLegPrototype[]
local function own_legs(body, visible)
  ---@type data.SpiderLegPrototype[]
  local legs = {}
  for i, spec in pairs(body.spider_engine.legs) do
    ---@type data.SpiderLegPrototype
    local leg = util.copy(data.raw["spider-leg"][spec.leg])
    leg.name = C.body_leg_name(body.name, i)
    if not visible then
      leg.graphics_set = nil
      leg.working_sound = nil
      spec.leg_hit_the_ground_trigger = nil
    end
    spec.leg = leg.name
    legs[#legs + 1] = leg
  end
  assert(#legs == C.leg_count, body.name .. ": expected " .. C.leg_count .. " legs, got " .. #legs)
  return legs
end

-- BEACHED -------------------------------------------------------------------------------------
local beached = body_of(C.beached)
-- A remote driver cannot steer a shark with no legs. What this does to a player ALREADY
-- remote-driving him when he breaks is D.4.8's to see.
beached.allow_remote_driving = false
-- Repair is the way back (E.5): this body must stay repairable, so no "not-repairable" flag,
-- and minable stays nil above - picking him up would hand back a whole jamaltron.
local beached_legs = own_legs(beached, false)
-- D.7.3: he does not fire while beached, by himself or for a driver still in him (chotchki
-- 2026-09-26). Each of the vehicle's guns becomes its disarmed twin (prototypes/disarm.lua has
-- what was measured); same ammo categories, so the ammo stays loaded across the break and the
-- repair. AIRBORNE KEEPS THE VEHICLE'S LIVE GUNS: it fires mid-arc (1-2 biters an arc), and
-- whether it should is D.7.2 (c), chotchki's call and still open - disarming it is these three
-- lines again on `airborne`.
local beached_guns = {}
for i, name in ipairs(vehicle.guns or {}) do beached_guns[i] = disarm.twin(name) end
beached.guns = beached_guns

-- THE FLOP, and nothing of the vehicle's art under it. animation is the body sheet ALONE,
-- shadow_animation the Cycles shadow. NO HARNESS: it broke off with his legs (chotchki
-- 2026-09-26, "the beached jamal shouldn't have the harness on it anymore"), so
-- render/beached.toml ships no tint mask and entity colour does not show on a beached Jamal
-- (D.4 still carries entity.color across the swap, so it is back on the repair).
-- 72 cells played as a 117-frame frame_sequence (heave, settle, pause, snap, release, twitch),
-- nose WEST, at the sheet's animation_speed (0.4: 24 fps; left off, the engine plays a cell a
-- tick and the 4.9 s flop ran in 117 ticks, MEASURED). A dead-engine spider-vehicle plays its
-- body animation on the GLOBAL tick (MEASURED): every beached Jamal flops in lockstep, no
-- per-entity phase (D.4.8's to mind).
-- CLEARED, because this copies the vehicle and a slot left alone draws HIS art:
--   base_animation, shadow_base_animation  nil on the vehicle already, cleared again on the
--                    word of flop.clear - the packer's own list, asserted below
--   water_reflection his is a blob of the STANDING silhouette's mean alpha, centred under a
--                    torso 1.5 tiles up: wrong shape and place for a fish lying on the
--                    ground. The flop sheet has none (pack.py: a stranded shark refuses water)
--   light, eye_light, light_positions  stock spidertron eye and headlamp positions, floating
--                    where a spidertron's eyes are
--
-- height = 0, MEASURED: `height` (1.5, copied off the vehicle) lifts the body animation, the
-- selection box and health bar, entity-targeted render objects and the gun's stream source by
-- exactly that many tiles, and NOT shadow_animation. pack.py measures its shifts from the
-- model's GROUND origin, so the flop draws where it was rendered - on its own shadow - only at 0.
-- Side effects: his stream would start 1.5 tiles lower (moot: D.7.3 disarmed his guns, see
-- beached.guns above), and a fresh break may settle further. The jump harness's DRIFT lane is
-- NOISY run to run on identical code: at 0 it slid 0.91-1.51 tiles off the landing spot (4
-- runs), at 1.5 0.96-1.23 (4 runs), always away from the water. A lean, not a law - but the
-- settle physics does see height, and D.1.3's broken legs inherit that.
-- render_layer = "object", MEASURED: the stock "under-elevated" suits a torso 1.5 tiles up, but
-- a fish lying on the ground painted OVER a tree and a character south of him (shot.sh, a
-- tree-01 at +1.6 and a character at +1.3). At "object" he sorts by y like anything else on the
-- ground and both draw in front. D.1.3's broken legs have to sort with him: re-shoot it then.
-- torso_bob_speed = 0: the stock torso bobs ~0.047 tiles on a ~40-tick period even with the
-- engine dead - a stranded shark bouncing on the sand. MEASURED in the renderer (shot.sh, zoom
-- 2, a frame every 2 ticks through the 24-tick pause beat): at 1 he moves 1-2 px frame to
-- frame, at 0 all 12 pause frames are pixel-identical.
-- alert_icon_shift: the flop body's own shift, the centre of the union of all 72 cells - on
-- his back, not 1.5 tiles over the vehicle's lifted torso. UNMEASURED: no
-- entity alert icon showed in a screenshot, even with render_no_power_icon forced on.
--
-- ONE DIRECTION PINS HIS ORIENTATION, and the flop sheet has one. MEASURED: a spider-vehicle
-- whose body art has one direction (or none) is created at orientation 0 and ignores writes to
-- it, engine live or dead; torso_orientation still takes a write. So the swap's orientation
-- write onto this body is a no-op and his heading survives a break only on torso_orientation -
-- which also sets orientation when written (measured on the vehicle), so writing torso LAST
-- puts the heading back on the repair. He lies nose west whichever way he was facing.
local beached_gs = beached.graphics_set
assert(beached_gs, C.name .. " has no graphics_set to copy")
beached_gs.animation = flop.slots.animation
beached_gs.shadow_animation = flop.slots.shadow_animation
beached_gs.base_animation, beached_gs.shadow_base_animation = nil, nil
beached_gs.water_reflection = nil
beached_gs.light, beached_gs.eye_light, beached_gs.light_positions = nil, nil, nil
beached_gs.render_layer = "object"
beached.height = 0
beached.torso_bob_speed = 0
beached.alert_icon_shift = util.copy(flop.sprites.body.shift)

-- entity.lua's three cross-checks, on the flop, plus three of its own: all against a body that
-- loads, lints and runs while drawing the wrong art, which headless never shows. (1) what
-- pack.py emits is what is wired, both ways; (2) every slot it says no sheet covers is empty;
-- (3) every sheet is ours; (4) every sheet carries its animation_speed - a sheet packed before
-- pack.py set one plays the flop 2.5x fast; (5) he draws on the ground's layer, not a torso's;
-- (6) nothing on him takes the runtime tint - a re-pack that brought the harness mask back.
local flop_wired = {animation = true, shadow_animation = true}
for slot in pairs(flop.slots) do
  assert(flop_wired[slot], "pack.py emits beached slot '" .. slot .. "' that bodies.lua never wires")
end
for slot in pairs(flop_wired) do
  assert(flop.slots[slot], "bodies.lua wires beached slot '" .. slot .. "' that pack.py no longer emits")
end
for _, slot in pairs(flop.clear) do
  assert(beached_gs[slot] == nil, C.beached .. " slot '" .. slot .. "' should be cleared but holds art")
end
for id, sprite in pairs(flop.sprites) do
  assert(string.find(sprite.filename, "^__" .. C.name .. "__/"),
    "beached sprite '" .. id .. "' is not ours: " .. sprite.filename)
  assert(sprite.animation_speed, "beached sprite '" .. id .. "' has no animation_speed: "
    .. "the engine would play a cell a tick")
  assert(not sprite.apply_runtime_tint, "beached sprite '" .. id .. "' takes the runtime tint: "
    .. "the harness broke off with his legs (render/beached.toml [sequence] passes)")
end
assert(beached_gs.render_layer == "object", C.beached .. " must draw at render_layer 'object'")

-- AIRBORNE ------------------------------------------------------------------------------------
local airborne = body_of(C.airborne)
-- 30 ticks is not long enough to click on, and a click that lands opens a GUI the landing
-- swap then has to carry. MEASURED: set_driver still seats a character in it. `operable` has no
-- prototype switch; D.4's body table writes it (the swap copies the old body's true).
airborne.selectable_in_game = false
-- For E.1's arc, MEASURED on this body: teleport carries it, its legs (rigidly - no stretch, no
-- re-lay) and its seated driver (a tick behind, still seated), 30 of 30 moves; a held key
-- never walks it. Positions snap to 1/256 tile, so aim each tick at an ABSOLUTE point on the
-- arc - 30 relative steps of 0.3 land 8.906 tiles on, not 9.
local airborne_legs = own_legs(airborne, not AIRBORNE_INVISIBLE)
if AIRBORNE_INVISIBLE then
  local gs = airborne.graphics_set
  assert(gs, C.name .. " has no graphics_set to copy")
  gs.animation, gs.shadow_animation, gs.water_reflection = nil, nil, nil
  gs.base_animation, gs.shadow_base_animation = nil, nil
  gs.light, gs.eye_light, gs.light_positions = nil, nil, nil
end

-- OTHER MODS DEPEND ON THESE as well as E.5 (E.6, each measured against the mod's zip):
--   minable = nil    Spidertron Enhancements swaps only a MINABLE spider into its dummy, and has
--                    no dummy for either body - a minable one would be swapped into a prototype
--                    that does not exist
--   hidden = true    spidertron-dock builds no docked copy of a hidden spider (it would dock him
--                    by destroying him: record lost); spider-launcher lists only mine-able ones
--   airborne unselectable  spidertron-dock skips those too
for _, body in pairs({beached, airborne}) do
  assert_holds_what_he_holds(body)
  assert(body.minable == nil, body.name .. " must not be minable")
  assert(body.hidden == true, body.name .. " must stay hidden")
end
assert(airborne.selectable_in_game == false, C.airborne .. " must stay unselectable")
for i, name in ipairs(beached.guns or {}) do
  assert(disarm.is_disarmed(data.raw["gun"][name]), C.beached .. " gun " .. i .. " (" .. name
    .. ") can fire - a beached Jamal must not (D.7.3)")
end

data:extend({beached, airborne})
data:extend(beached_legs)
data:extend(airborne_legs)
