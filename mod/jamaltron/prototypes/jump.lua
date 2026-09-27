-- E.1's arc art and E.3's thud, plus every name the jump draws or plays with.
--
-- LOADED TWICE: data.lua requires it to extend the prototypes below; the runtime's
-- scripts/jump.lua requires it for the NAMES alone (`data` is nil there, so nothing is
-- extended). The names themselves are prototypes/shared.lua's C.jump, beside the body names.
--
-- THE ARC ANIMATIONS are his own standing sheets re-declared as 64-FRAME animations: a 64-
-- direction sheet and a 64-frame animation share one layout (8 per row, frame 0 north, clockwise
-- - tools/render/factorio_camera.py), so frame i IS direction i and scripts/jump.lua picks his
-- heading with animation_offset at animation_speed 0, the Jetpack mod's pattern. The body is
-- drawn as rendering, not as an entity, because an entity cannot be lifted off its own position:
-- the airborne body is invisible (prototypes/bodies.lua, AIRBORNE_INVISIBLE) and these are the
-- only Jamal on screen mid-jump.
--
-- SHIFT IS ZERO on all three, and the runtime adds the sheet's shift itself (read from the same
-- sprites_generated.lua). A rotated render object turns about its target, so a zero shift makes
-- that the sprite's own centre - the pitch jump.lua gives him mid-arc then turns body and mask
-- about ONE point instead of each about wherever its shift left it. Whether the engine rotates a
-- prototype shift with the sprite is not documented; with zero there is nothing to rotate.
--
-- VRAM (INFERRED, headless loads no sprites): the same files and rectangles as the vehicle's
-- graphics_set. If the engine keys its sprite atlas on file + rectangle these cost nothing; if not
-- they cost what the airborne body's visible art cost before AIRBORNE_INVISIBLE cleared it (~26
-- MiB body + ~26 shadow + ~5 mask raw). F.2 reads the real number.

local C = require("prototypes.shared")
local art = require("prototypes.sprites_generated")

local N = C.jump

---A 64-direction sheet as a 64-frame animation, shift zeroed (see the header).
---@param sprite table a sprites_generated.lua sheet
---@param name string
---@return data.AnimationPrototype
local function frames(sprite, name)
  ---@type data.AnimationPrototype
  local anim = {
    type = "animation",
    name = name,
    filename = sprite.filename,
    width = sprite.width,
    height = sprite.height,
    line_length = sprite.line_length,
    frame_count = sprite.direction_count,
    scale = sprite.scale,
  }
  if sprite.draw_as_shadow then
    anim.draw_as_shadow = true
  end
  return anim
end

if data then
  data:extend({
    frames(art.sprites.body, N.body),
    frames(art.sprites.body_mask, N.mask),
    frames(art.sprites.shadow, N.shadow),
    -- PLACEHOLDER until D.6's CC0 thud: base's cargo pod hitting the ground (the same three files
    -- base plays for a pod landing), which is a heavy thing arriving from the sky - close enough
    -- to a shark. Aggregated so twenty jamaltrons landing on one tick are not twenty thuds.
    {
      type = "sound",
      name = N.thud,
      category = "game-effect",
      variations = {
        {filename = "__base__/sound/procession/cargo-pod-ground-land-1.ogg", volume = 0.7},
        {filename = "__base__/sound/procession/cargo-pod-ground-land-2.ogg", volume = 0.7},
        {filename = "__base__/sound/procession/cargo-pod-ground-land-3.ogg", volume = 0.7},
      },
      aggregation = {max_count = 3, remove = true, count_already_playing = true},
    },
  })
end

return N
