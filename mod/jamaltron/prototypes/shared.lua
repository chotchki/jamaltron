-- Prototype names for the whole jamaltron family, in one place.
--
-- entity.lua has to rewrite eight leg cross-references by hand and a typo in any of
-- them is SILENT (the vehicle happily walks on the stock spidertron's legs), so the
-- names come from here or not at all.

-- Deliberately NOT `(exact)`. Exact on a class attached to a table literal makes
-- lua-language-server reject the literal's own fields unless every one is repeated as
-- a ---@field, and the duplicate list rots. Plain ---@class already buys the check
-- that matters: C.leg_cuont is an undefined-field warning at the use site.
---@class Jamaltron.Names
local C = {
  -- The vehicle, item, recipe and technology all share this name. Factorio keys
  -- prototypes per type, so one string covers four prototypes with no collision.
  name = "jamaltron",
  -- Stock spidertron mounts 8 legs; the Phase C sprite work assumes 8 mount points.
  leg_count = 8,
  -- See entity.lua: measured largest mount ring that keeps all 8 legs on the
  -- shark's silhouette at every rotation. C.13.
  mount_shrink = 0.45,
  -- Tiles of SCREEN offset every mount moves UP, after the shrink. C.27 put his belly
  -- on the ground (model.ground_contact): at the tuned shark that raised the body 0.2602
  -- tiles of world height, which the 45-degree camera draws 0.2602 * 0.7071 = 0.184 tiles
  -- up-screen. The mounts follow so they land on the same pixels of him C.13 measured.
  -- Re-measure (art.py --compare, coverage line) if scale or girth move.
  mount_lift = 0.184,
  -- D.7.4 (W1, entity.lua's header): the render layers that put his flamethrower's stream UNDER
  -- him. Legs on 'projectile', the lowest layer that beats the stream; the torso above them so it
  -- still beats the legs - on 'air-object', NOT 'smoke' between them, which the renderer draws
  -- BLURRED (measured). bodies.lua's beached body overrides its torso to 'object';
  -- prototypes/layers.lua applies both, again in data-final-fixes.
  layer_legs = "projectile",
  layer_body = "air-object",
  remnants = "jamaltron-remnants",
  -- D.5: his speech bubble, a named copy of base's compilatron bubble (prototypes/speech.lua)
  speech_bubble = "jamaltron-speech-bubble",
  explosion = "jamaltron-explosion",
  -- D.1's other two bodies. scripts/swap.lua moves Jamal between these and `name`, so the
  -- swap, the event filters and the harness all spell them from here.
  beached = "jamaltron-beached",
  airborne = "jamaltron-airborne",
  -- His own equipment grid, made ONLY when buoyant-spidertrons is loaded (prototypes/compat.lua):
  -- otherwise he shares the vehicle's grid as copied.
  grid = "jamaltron-equipment-grid",
  -- D.7: his gun (prototypes/gun.lua), and the custom event a flamethrower stream raises when
  -- it STARTS (prototypes/ammo.lua puts it on the ammo; scripts/attack.lua listens).
  gun = "jamaltron-flamethrower",
  -- D.7.3: its disarmed twin, on the beached body (prototypes/disarm.lua).
  gun_broken = "jamaltron-flamethrower-broken",
  fired = "jamaltron-fired",
  -- E.1-E.3's jump: the key (prototypes/input.lua), the arc's three 64-frame animations and the
  -- landing thud (prototypes/jump.lua), all drawn or played by scripts/jump.lua.
  jump = {
    input = "jamaltron-jump",
    body = "jamaltron-arc-body",
    mask = "jamaltron-arc-mask",          -- tinted with his colour at runtime
    shadow = "jamaltron-arc-shadow",
    thud = "jamaltron-landing-thud",
  },
  -- D.1.3: the broken legs lying round a beached Jamal, SpritePrototypes cut by reference from
  -- the __base__ leg sheets (prototypes/wreck.lua), drawn by scripts/wreck.lua. C.wreck_sprite.
  wreck = "jamaltron-wreck",
}

---Every body Jamal can be in, the vehicle first. Runtime code filters it through
---`prototypes.entity` (swap.bodies), because a name that is not built is an error in an
---event filter.
C.family = {C.name, C.beached, C.airborne}

---Prototype name of leg `index`.
---
---Returns data.EntityID rather than string - same type, but it says the string is a
---prototype reference, which is what entity.lua assigns to SpiderLegSpecification.leg.
---@param index integer 1..C.leg_count
---@return data.EntityID
function C.leg_name(index)
  return C.body_leg_name(C.name, index)
end

---Prototype name of leg `index` of body `body`. D.1's beached and airborne bodies own eight legs
---each (leg art lives on the leg prototype, so hiding theirs must not hide the vehicle's).
---@param body string one of C.family
---@param index integer 1..C.leg_count
---@return data.EntityID
function C.body_leg_name(body, index)
  return body .. "-leg-" .. index
end

---Sprite name of one broken-leg piece: segment `part` (upper, lower, or a kinked lower's halves
---lower-a and lower-b) in `kind` (art, its runtime-tinted ends, or its shadow).
---@param part string
---@param kind "art"|"tint"|"shadow"
---@return string
function C.wreck_sprite(part, kind)
  return C.wreck .. "-" .. part .. "-" .. kind
end

return C
