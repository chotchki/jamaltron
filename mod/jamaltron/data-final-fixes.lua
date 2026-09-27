-- Data-final-fixes entry point: D.1's beached and airborne bodies (prototypes/bodies.lua) and
-- D.7's firing signal on the flamethrower ammo (prototypes/ammo.lua).
--
-- HERE, not data.lua, because the bodies are copies of the FINAL jamaltron: by data-final-fixes
-- every mod's data and data-updates edits to him are in, so the copies inherit them and hold
-- exactly what he holds - the one thing the D.4 swap needs from them.
--
-- prototypes/compat.lua goes FIRST: the copies must inherit its edits to him too (E.6's guards
-- for other spider mods, D.7.4's layers laid again over any re-skin). prototypes/ammo.lua is
-- here for the reverse reason: another mod's ammo from data and data-updates has to be in first.
--
-- require("util") for data.lua's reason: the copies deepcopy with it.

require("util")

require("prototypes.compat")
require("prototypes.bodies")
require("prototypes.ammo")
