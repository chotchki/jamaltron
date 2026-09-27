-- Data stage entry point: requires the prototype files under prototypes/.
--
-- require("util") for its side effect: the global `util` every prototype file deepcopies
-- with. Base already required it, so `util` exists anyway; requiring it keeps that from
-- being a load-order bet.
--
-- Order within this list does not matter: assignID resolves prototype name references
-- after the whole data stage, so the entity may name an item item.lua has not extended yet.
--
-- No ---@ annotations: the file is only requires with discarded returns, so there is no
-- declaration to hang a type on. The prototype files carry their own.

require("util")

require("prototypes.entity")
require("prototypes.gun")
require("prototypes.item")
require("prototypes.recipe")
require("prototypes.technology")
require("prototypes.speech")
require("prototypes.swap")
require("prototypes.jump")
require("prototypes.input")
require("prototypes.wreck")
