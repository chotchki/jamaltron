-- jamaltron spider-vehicle, its 8 legs, its corpse and its dying explosion: deepcopies
-- of the stock spidertron family wearing OUR rendered body sheets, still on STOCK legs
-- with STOCK lights and sounds. The graphics_set block below says which layer is whose -
-- C.5 re-renders the legs, Phase D takes the sounds, the guns and the beached variant.
--
-- Source of truth: /Applications/factorio.app/Contents/data/base/prototypes/entity/
-- entities.lua (create_spidertron at :9875, make_spidertron_leg at :91), remnants.lua
-- :3060, explosions.lua :5864. Verified against 2.1.17.
--
-- util.copy, never a bare reference: `local body = data.raw[...]["spidertron"]` then
-- `body.name = "jamaltron"` would RENAME the base game's prototype in place and
-- corrupt the spidertron for every other mod.
--
-- Left pointing at shared base prototypes on purpose - correct until Phase D:
--   * equipment_grid = "spidertron-equipment-grid" (10x6; only clone it if the size
--     changes, and D.4's lossless swap needs jamaltron-beached to keep the same one)
--   * every icon path, including the item's icon_tintable pair (see item.lua)
--
-- The ---@type on each copy names the data.raw slot it came from. util.copy is
-- generic, so lua-language-server already infers these; writing them down is what
-- makes a copy re-pointed at the wrong raw type fail here instead of downstream.

local C = require("prototypes.shared")
local layers = require("prototypes.layers")
-- GENERATED: tools/render/pack.py measured every number in it off the frames it packed,
-- and it and the JSON manifest beside the sheets are one dict serialized twice (what
-- tools/lint_sprites.py gates in CI). Requiring it keeps widths out of this file - a
-- number retyped here could drift from the PNG and nothing in the game would say so
-- (Factorio is sprite-blind in every scriptable mode; tools/lint_sprites.py's header has
-- the measurements).
local art = require("prototypes.sprites_generated")

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

-- OUR ART GOES ON HERE, one assignment per slot rather than a loop because graphics_set
-- is an (exact) class: a slot named by a string variable type-checks against nothing,
-- these five names check against the prototype definition at lint time.
--
-- OURS, rendered from the hammerhead (config hash in sprites_generated.lua's header):
--   animation        64 rotations of body + the runtime-tint harness mask
--   shadow_animation the Cycles shadow-catcher pass, 64 rotations
--   water_reflection built by the packer out of the body frames - there is nothing
--                    to render, stock's is a blurred red-in-alpha blob and so is ours
--
-- CLEARED, the half that bites: assigning a graphics_set slot REPLACES that layer
-- stack wholesale, so a slot we never touch keeps WUBE'S ART and draws it.
--   base_animation, shadow_base_animation  the stock under-plate and its shadow. Not
--     missing, DECIDED: C.13 pulled the leg mounts in to 0.45 of stock, and at that
--     ring the shark's own silhouette covers all 8 mounts at every one of the 64
--     rotations (512/512 samples, measured by the packer). Nothing is left for a
--     plate to cover, and a stock plate would draw a machine's belly under a fish.
--     CAVEAT: that count holds the mounts still while the shark turns - stock's pinned
--     ring. nil here makes the engine turn the ring WITH the torso (below), so in game
--     the mounts at every heading but north are positions the packer never sampled.
--
-- STILL INHERITED - all stock spidertron art, all of it known and phased:
--   the eight LEG prototypes built below. C.5 owns the leg sheets and has not run,
--     so Jamal currently walks on spidertron legs and looks like it.
--   light, eye_light, light_positions. 11 light groups x 64 authored offsets, which
--     puts Jamal's eye lights where a SPIDERTRON's eyes are (the C.4c finding). The
--     camera can project his real eyes through the same matrix, it just has not yet.
--   base_render_layer (nothing draws on it - base_animation is cleared) and the
--     autopilot destination visualisations, which are geometry-free.
--
-- RE-LAYERED, NOT INHERITED (D.7.4, "W1"): his flamethrower's stream draws above every
-- render layer up to 'explosion', so at stock's 'under-elevated' (torso) and
-- 'higher-object-above' / 'train-stop-top' (leg parts / joints) it painted OVER him wherever it
-- crossed him. chotchki wants it to come from under him and draw under his legs and body:
-- 'projectile' is the lowest layer that beats it, and in a same-layer tie the legs still beat
-- the stream. So legs 'projectile' (the loop below) and the torso above them at 'air-object' -
-- on the legs' layer the legs drew over the shark, and on 'smoke' between the two the renderer
-- draws him BLURRED at every zoom (MEASURED, mean |Laplacian| over his body at zoom 1: 36.9 stock
-- and air-object, 28.3 smoke). Shadows and water reflections keep stock's. prototypes/layers.lua
-- sets them; compat.lua sets them again in data-final-fixes, over any data-updates re-skin.
-- ACCEPTED COSTS, chotchki 2026-09-26 ("Ship W1"), all MEASURED in the renderer: he draws over
-- elevated-rail bridges and the trains on them (whole, not torn); explosions draw under all of
-- him; in a DENSE smoke cloud his body floats over it with no legs. FOUND IN REVIEW, same
-- renderer, not yet put to chotchki: his body AND legs cover alt-mode icons, a machine he
-- stands over loses its recipe icon whole; his legs and body draw over a stock spidertron (or
-- any stock-layered spider) standing SOUTH of him, in front - no layer above 'explosion' avoids
-- that. Flying robots share his layer and sort by position: behind him (north) they now pass
-- under his body, in front over it.
local gs = body.graphics_set
-- Narrowing, not paranoia: graphics_set is optional on SpiderVehiclePrototype, so
-- without this every assignment below is a field write into a possibly-nil value.
assert(gs, "base spidertron has no graphics_set to replace")
gs.animation = art.slots.animation
gs.shadow_animation = art.slots.shadow_animation
gs.water_reflection = art.slots.water_reflection
-- nil also decides the leg rig, MEASURED (F.3, 2.1.17): with no base_animation the engine turns
-- the base orientation and all 8 leg mounts with the torso; a 1-direction sprite here, even a
-- 1x1 blank, pins them north like stock. The turning rig costs SpiderVehicle ~1.1 us/tick per
-- DRIVEN Jamal and ~0.35 per Jamal walking on autopilot over stock; 0 idle or beached (the flop
-- sheet has one direction, so it pins itself), unmeasured airborne (a 30-tick arc).
-- Pinning buys that back but moves his legs, his own flame splash and the jump harness geometry.
gs.base_animation = nil
gs.shadow_base_animation = nil
-- W1, above: over his legs' 'projectile', both over the stream's. MEASURED (shot.sh,
-- 8 bearings + a walking burst): the flame passes under the whole shark.
layers.torso(gs)

-- Three cross-checks, all guarding the SAME failure mode: a mod that loads, lints and
-- runs while still drawing a spidertron. No error ever shows it - headless never
-- rasterizes a sprite - so it is asserted here or not at all.
--
-- (1) the wiring above against what pack.py actually emitted, BOTH directions. A new
--     slot in the generated table that nobody assigns is stock art on screen; a slot
--     assigned from a table pack.py stopped emitting is nil, i.e. invisible.
local wired = {animation = true, shadow_animation = true, water_reflection = true}
for slot in pairs(art.slots) do
  assert(wired[slot], "pack.py emits graphics slot '" .. slot .. "' that entity.lua never wires")
end
for slot in pairs(wired) do
  assert(art.slots[slot], "entity.lua wires graphics slot '" .. slot .. "' that pack.py no longer emits")
end
-- (2) every slot the packer says NO sheet of ours covers really is empty after the
--     nils above - that list is where a stock layer would survive unnoticed.
for _, slot in pairs(art.clear) do
  assert(gs[slot] == nil, "graphics slot '" .. slot .. "' should be cleared but still holds art")
end
-- (3) every sheet resolves inside OUR mod. A filename left pointing at __base__ is
--     the literal shape of the bug: valid, loadable, and a spidertron on screen.
for id, sprite in pairs(art.sprites) do
  assert(string.find(sprite.filename, "^__" .. C.name .. "__/"),
    "sprite '" .. id .. "' is not ours: " .. sprite.filename)
end

-- The one annotation here that is not just documentation: an empty table literal
-- infers as an untyped table, so unannotated `legs[i] = <anything>` is accepted and
-- data:extend(legs) checks against `any`.
---@type data.SpiderLegPrototype[]
local legs = {}

---D.7.5 (b), chotchki's call: FIRE-PROOF LEGS. His own stream's landing splash (radius 4, force
---"all") catches any foot within ~4 tiles of the aim point and leg damage lands on the body -
---~1 HP a minute a foot, lopsided by where his feet happened to plant (MEASURED: 15.5 HP in 240
---ticks at a behemoth 6 tiles north; fire-immune legs, 0 at every bearing and distance). Cost:
---his legs shrug off EVERYONE's fire, a flamethrower turret's too; the torso keeps stock's
---fire 15/60 and still burns. Merges: stock's fire entry (15/60) becomes 100%, its other
---resistances stand, and a leg with no fire entry gets one.
---@param resistances data.Resistance[]?
---@return data.Resistance[]
local function fireproof(resistances)
  local out, found = {}, false
  for _, r in ipairs(resistances or {}) do
    if r.type == "fire" then
      r, found = {type = "fire", percent = 100}, true
    end
    out[#out + 1] = r
  end
  if not found then out[#out + 1] = {type = "fire", percent = 100} end
  return out
end

for i = 1, C.leg_count do
  ---@type data.SpiderLegPrototype
  local leg = util.copy(data.raw["spider-leg"]["spidertron-leg-" .. i])
  leg.name = C.leg_name(i)
  -- make_spidertron_leg hardcodes {"entity-name.spidertron-leg"} because the leg
  -- prototype names have no locale keys of their own. Inherited, it reads
  -- "Spidertron leg" in every tooltip. `hidden = true` comes along in the copy and
  -- stays - 8 leg entries in Factoriopedia is noise.
  leg.localised_name = {"entity-name." .. C.name .. "-leg"}
  -- bodies.lua's beached and airborne legs are copies of these, so they inherit it.
  leg.resistances = fireproof(leg.resistances)
  legs[i] = leg
  body.spider_engine.legs[i].leg = leg.name
  -- HARNESS, NOT CHASSIS. Stock mounts the legs to the corners of a machine
  -- (widest pair at +-25 px = +-0.781 tiles); Jamal's are strapped to him, so they
  -- emerge from a band around his girth and splay out to the ground.
  --
  -- 0.45 is MEASURED, not chosen: at the tuned shark (config 137972136a75, 4.07 x
  -- 2.47 tiles) it is the LARGEST ring where all 8 mounts land on his silhouette
  -- at all 16 sampled rotations. 0.50 leaves one mount off at one rotation.
  -- ground_position is NOT scaled: that is where the feet LAND, and shrinking it too
  -- would give him a mincing little stance instead of legs splayed from a harness.
  --
  -- Then UP by mount_lift (screen y is south-positive, so up is minus). C.27 sat his
  -- belly on the ground, which drew the whole body 0.184 tiles higher; the mounts ride
  -- with him or the tail-down rotations lose their rear legs (52/64 measured without it).
  local mount = body.spider_engine.legs[i].mount_position
  mount[1], mount[2] = mount[1] * C.mount_shrink, mount[2] * C.mount_shrink - C.mount_lift
  -- W1 (header): both segments AND the knee joints over the stream, so the flame draws under
  -- his legs. MEASURED (the spike's red-tinted joints): stock's joint layer 'train-stop-top' is
  -- under the stream too, so parts alone left it painting over every knee. Shadows and water
  -- reflections are untouched, as picked.
  assert(layers.leg(leg), "stock " .. leg.name .. " has no upper/lower part to re-layer")
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

-- W1's cross-check, same failure mode as the art checks - headless never shows it: every leg
-- and the torso on their layers, and the torso NOT on the legs' (the legs then draw over the
-- shark). Which layer beats the stream is the renderer's; test_gun.py pins the two names. This
-- only sees data.lua - compat.lua lays them again in data-final-fixes, after data-updates.
assert(gs.render_layer == C.layer_body and C.layer_body ~= C.layer_legs,
  "his torso must draw above his legs (W1, D.7.4)")
for _, leg in pairs(legs) do
  assert(layers.leg_ok(leg), leg.name .. " must draw on " .. C.layer_legs .. " (W1, D.7.4)")
end

-- D.7: FOUR flamethrowers, the same gun four times (prototypes/gun.lua), in the rocket
-- launchers' place. The count is what sizes the ammo inventory - one slot per gun - so four
-- keeps a spidertron's four ammo slots (400 flamethrower ammo, 40,000 rounds; one gun would be
-- 10,000) and the stock automatic_weapon_cycling that drains them evenly. It buys NO damage,
-- MEASURED against a behemoth 6 tiles off for 400 ticks: four cycling, four not cycling and one
-- gun each spent 443.9 rounds for 1337 damage, because a stream is one stream whichever gun
-- feeds it (one stream start for the whole 400 ticks, either way). The books give him one gun;
-- the other three are magazine. Swapping to fewer changes the ammo slots D.4's swap moves.
body.guns = {C.gun, C.gun, C.gun, C.gun}

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
