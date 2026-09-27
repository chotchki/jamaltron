-- E.2.6: the jump key, a custom-input that exists only while the startup setting
-- jamaltron-jump-enabled is on - off, the key is not in the controls menu at all, as "off removes
-- jumping" promises (settings.lua). control.lua registers its handler only when it exists.
--
-- DEFAULT KEY `Y`, rebindable in Settings > Controls. Chosen because it is the one key within a
-- WASD hand's reach that no default control uses (wiki Controls page, 2026-03 revision, plus the
-- 2.1.0 changelog; the binary keeps its defaults as data, not strings, so this is READ, not
-- measured - play.sh checks the controls menu shows no conflict). What it is not, and why:
--   SPACE   shoot enemy; SHIFT + SPACE shoot selected - his own guns
--   LSHIFT  chotchki's 2026-09-25 candidate. Bare SHIFT is `activate-tooltip`, and Shift is the
--           modifier of shoot selected, select quickbar 1-10, stack transfer, build ghost and a
--           dozen more: a custom input fires on the Shift press itself, so SHIFT + 2 to change
--           quickbar page would jump him first. Rebind to it and every one of those jumps
--   J, K    connect / disconnect train
-- The handler also ignores a press while the player has a GUI open, so a rebind to any key a
-- GUI uses (Shift-click among them) cannot jump him from inside his own trunk.

local N = require("prototypes.jump")

if settings.startup["jamaltron-jump-enabled"].value then
  data:extend({
    {
      type = "custom-input",
      name = N.input,
      key_sequence = "Y",
      -- "none": the key's other uses (if chotchki rebinds onto one) still happen
      consuming = "none",
    },
  })
end
