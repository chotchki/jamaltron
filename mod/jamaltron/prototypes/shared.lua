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
  -- on the ground (ground contact): at the tuned shark that raised the body 0.2602
  -- tiles of world height, which the 45-degree camera draws 0.2602 * 0.7071 = 0.184
  -- tiles up-screen. The mounts follow so they land on the same pixels of him C.13
  -- measured. Re-measure (art.py --compare, coverage line) if scale or girth move.
  mount_lift = 0.184,
  remnants = "jamaltron-remnants",
  explosion = "jamaltron-explosion",
}

---Prototype name of leg `index`.
---
---Returns data.EntityID rather than string - same type, but it says the string is a
---prototype reference, which is what entity.lua assigns to SpiderLegSpecification.leg.
---@param index integer 1..C.leg_count
---@return data.EntityID
function C.leg_name(index)
  return C.name .. "-leg-" .. index
end

return C
