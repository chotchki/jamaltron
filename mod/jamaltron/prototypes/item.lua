-- jamaltron item: a deepcopy of the stock spidertron's item-with-entity-data.
--
-- Source: base/prototypes/item.lua :2113 (2.1.17).
--
-- Carried over on purpose: subgroup = "transport", stack_size = 1, the three
-- inventory sounds and weight = 1 * tons (Space Age rocket capacity, unrelated to the
-- vehicle's own weight = 1).
--
-- Space Age's bundled `recycler` mod auto-generates a jamaltron-recycling recipe from
-- this item. Wanted; auto_recycle = false would kill it. Absent in a base-only game:
-- recycler/info.json carries expansion_required = true, and --dump-data confirms
-- data.raw.recipe has no jamaltron-recycling with the DLC off.

local C = require("prototypes.shared")

-- item-with-entity-data, not item: this subtype preserves the entity's own state
-- (equipment grid contents, colour) across a mine and rebuild, and declares the
-- icon_tintable pair below.
---@type data.ItemWithEntityDataPrototype
local item = util.copy(data.raw["item-with-entity-data"]["spidertron"])
item.name = C.name
-- place_result is the whole item -> entity link. Ghosts, blueprints and
-- deconstruction resolve the other direction from it, which is why no placeable_by
-- is needed. Left as "spidertron" it builds a spidertron, silently.
item.place_result = C.name
-- Stock is "b[personal-transport]-c[spidertron]-a[spider]". Two items sharing a
-- subgroup and an order sort nondeterministically, so this has to differ.
item.order = "b[personal-transport]-c[spidertron]-b[" .. C.name .. "]"
item.localised_name = {"item-name." .. C.name}
item.localised_description = {"item-description." .. C.name}

-- OUR ICONS, all three (C.6, the portrait: tools/render/icons.py --promote). The tintable
-- pair is what an item-with-entity-data draws once the vehicle has a colour - the plain body,
-- then the harness mask tinted with it - so replacing only `icon` would leave the stock
-- spidertron in a coloured Jamal's slot. `icon` is the harness pre-tinted player orange, for
-- an item with no colour. Each file is 120x64, a 64px icon with its 4-level mip chain beside
-- it, and each size key is its OWN (icon_tintable_size does not inherit icon_size), so all
-- three are written out even at the default 64.
--
-- ONE LITERAL, then copied field by field: tools/lint_sprites.py's Lua reader sees table
-- literals only, so `item.icon = "..."` would slip past the size check test_icon_coverage.py
-- runs on every icon of ours (test_icons.py fails if these three stop being visible to it).
--
-- The layered forms are cleared: `icons` beats `icon` and `icon_tintables` beats
-- `icon_tintable`, so one left on the stock item by a mod that loaded before us would draw
-- over ours.
local art =
{
  icon = "__jamaltron__/graphics/jamaltron-icon.png",
  icon_size = 64,
  icon_tintable = "__jamaltron__/graphics/jamaltron-icon-tintable.png",
  icon_tintable_size = 64,
  icon_tintable_mask = "__jamaltron__/graphics/jamaltron-icon-tintable-mask.png",
  icon_tintable_mask_size = 64
}
item.icon, item.icon_size = art.icon, art.icon_size
item.icon_tintable, item.icon_tintable_size = art.icon_tintable, art.icon_tintable_size
item.icon_tintable_mask, item.icon_tintable_mask_size = art.icon_tintable_mask, art.icon_tintable_mask_size
item.icons, item.icon_tintables, item.icon_tintable_masks = nil, nil, nil

data:extend({item})
