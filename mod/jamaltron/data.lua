-- Data stage entry point: requires the prototype files under prototypes/.
--
-- require("util") is here for the side effect - it installs the global `util` that
-- every prototype file below deepcopies with. Base already required it, so `util`
-- happens to exist without asking; requiring it anyway is what keeps that from being
-- a load-order bet.
--
-- Order within this list does not matter. Prototype name references are resolved by
-- assignID after the whole data stage finishes, so the entity may name an item that
-- item.lua has not extended yet.
--
-- No ---@ annotations: the file is five requires whose returns are all discarded, so
-- there is no declaration to hang a type on. The prototypes themselves are annotated
-- in the files below.

require("util")

require("prototypes.entity")
require("prototypes.item")
require("prototypes.recipe")
require("prototypes.technology")
