-- jamaltron item: a deepcopy of the stock spidertron's item-with-entity-data.
--
-- Source: base/prototypes/item.lua :2113 (2.1.17).
--
-- Carried over on purpose: subgroup = "transport", stack_size = 1, the three
-- inventory sounds, and weight = 1 * tons. That last one is the Space Age rocket
-- capacity weight and has nothing to do with the vehicle's own weight = 1.
--
-- Space Age's bundled `recycler` mod auto-generates a jamaltron-recycling recipe from
-- this item. Wanted; set auto_recycle = false to kill it. It is NOT present in a
-- base-only game: recycler/info.json carries expansion_required = true, and --dump-data
-- confirms data.raw.recipe has no jamaltron-recycling with the DLC off.

local C = require("prototypes.shared")

-- item-with-entity-data, not item: this subtype is what preserves the entity's own
-- state (equipment grid contents, colour) across a mine and rebuild, and it is where
-- the icon_tintable pair below is declared.
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

-- STOCK icons for now, all three of them. Phase C.6 must replace icon_tintable and
-- icon_tintable_mask as well as icon: the tintable pair is what an item-with-entity-data
-- actually draws once the vehicle has a colour, so replacing only `icon` leaves the
-- spidertron silhouette in the inventory.

data:extend({item})
