-- Settings stage entry point (PLAN D.3). FIRST-PASS DEFAULTS, chotchki 2026-09-24: "make
-- some reasonable choices and we'll iterate off of that". The NAMES are expensive to change -
-- a save stores a setting under its name, so a rename silently resets it for everyone - hence
-- every one prefixed and spelled out in full. The numbers are cheap to change and expected to
-- move once E.1-E.4 exist to feel them.
--
-- ONE DEPARTURE FROM THE PLAN TEXT: D.3 listed jump distance and leg-break chance as STARTUP
-- settings. Neither touches a prototype (both are read at the moment of a jump), and a startup
-- setting costs a game restart and cannot change on a running server; as runtime-global map
-- settings an admin tunes them mid-game and multiplayer stays in sync. Only the jump on/off
-- switch is startup: it decides whether the jump keybind (a custom-input PROTOTYPE, E.2)
-- exists at all.
--
-- SPEECH BUBBLES ARE NOT PER PLAYER (chotchki 2026-09-24). A bubble is a world entity everyone
-- near him sees, so what he SAYS is one map-wide choice (verbosity is runtime-global); the only
-- per-player choice is whether his lines also land in your chat. A per-player "bubbles off"
-- cannot exist, so it is not offered.

---@type data.AnyModSettingPrototype[]
local settings = {
  -- startup ------------------------------------------------------------------------------
  {
    type = "bool-setting",
    name = "jamaltron-jump-enabled",
    setting_type = "startup",
    default_value = true,
    order = "a",
  },

  -- runtime-global: map settings, one value per save, changeable by an admin mid-game ------
  {
    -- Tiles. A first guess for E.1 to feel out: far enough to read as a leap, not a hop, and
    -- inside the flamethrower's ~9-tile engage range (D.7) so one jump does not carry him out
    -- of his own fight.
    type = "int-setting",
    name = "jamaltron-jump-distance",
    setting_type = "runtime-global",
    default_value = 8,
    minimum_value = 3,
    maximum_value = 20,
    order = "a",
  },
  {
    -- Percent per landing. One in four: often enough that the break/flop/repair loop is the
    -- mod's rhythm, not an event, rare enough that jumping stays worth doing. 0 turns the gag
    -- off; 100 is every landing.
    type = "int-setting",
    name = "jamaltron-leg-break-percent",
    setting_type = "runtime-global",
    default_value = 25,
    minimum_value = 0,
    maximum_value = 100,
    order = "b",
  },
  {
    -- Seconds between jumps from one Jamaltron, counted from his takeoff. A jump refused on
    -- cooldown is itself a line (jump_refused / cooldown). DEFAULT 0 (chotchki 2026-09-26, after
    -- playtesting 5 s: "I'm good refusing while the animation is still going but 5s is too
    -- long") - the arc already refuses by itself (mid-air he is the airborne body, and the key
    -- only answers the vehicle), so 0 refuses mid-arc and never after he lands.
    type = "int-setting",
    name = "jamaltron-jump-cooldown",
    setting_type = "runtime-global",
    default_value = 0,
    minimum_value = 0,
    maximum_value = 120,
    order = "c",
  },
  {
    -- Seconds between AMBIENT lines from one Jamaltron - idle, moving, damaged, attacking,
    -- flopping, command_done (speech.lua's M.AMBIENT). Event lines always get through and
    -- still reset it. A setup/punchline chain is one line in two beats and is exempt (SPEC),
    -- so this never cuts a punchline off.
    type = "int-setting",
    name = "jamaltron-speech-cooldown",
    setting_type = "runtime-global",
    default_value = 10,
    minimum_value = 3,
    maximum_value = 300,
    order = "d",
  },
  {
    -- Seconds between apologies while he lies beached (E.4) - the base period; how verbosity
    -- scales it is E.4's call. Defaults ABOVE the speech cooldown so the cooldown does not
    -- swallow an apology, and off any multiple of the flop loop (4.9 s in the C.21 draft) so
    -- each line lands on a different flop frame.
    type = "int-setting",
    name = "jamaltron-apology-interval",
    setting_type = "runtime-global",
    default_value = 15,
    minimum_value = 2,
    maximum_value = 120,
    order = "e",
  },
  {
    -- The catalog's three tiers, and they are CUMULATIVE: quiet plays quiet rows only, normal
    -- adds normal, unbearable plays everything (character/lines.md). The values ARE the
    -- catalog's TIER strings, so the speech code compares them without a translation table.
    -- Map-wide because the bubble is (SPEECH BUBBLES ARE NOT PER PLAYER, above).
    type = "string-setting",
    name = "jamaltron-verbosity",
    setting_type = "runtime-global",
    default_value = "normal",
    allowed_values = {"quiet", "normal", "unbearable"},
    order = "f",
  },
  {
    -- Live speech bubbles map-wide (F.3, chotchki 2026-09-26: "yes cap the bubbles"). Each one
    -- costs the GPU: 0/10/25/50 live measured 1.3/5.2/7.5/8.8 ms a frame on an M3 Max. At the cap
    -- his chatter (speech.lua's M.AMBIENT) waits and an event line takes down the oldest chatter
    -- bubble - or goes up anyway, so a break or a death is never lost to it. Narration is not
    -- counted. MEASURED at 20, 100 beached + 100 driven: the flop phase went 45 -> 17 bubbles on
    -- average (94 -> 20 at peak) and 8.0-8.3 -> 4.5-5.7 ms of GPU a frame; at 50 it only trims
    -- the peak (25 -> 20). A mass break is all events, so it is not capped.
    type = "int-setting",
    name = "jamaltron-max-bubbles",
    setting_type = "runtime-global",
    default_value = 20,
    minimum_value = 1,
    maximum_value = 200,
    order = "g",
  },

  -- runtime-per-user: each player's own ---------------------------------------------------
  {
    -- Off by default: every Jamaltron on the map talking into every player's chat is the
    -- fastest way to get the mod removed. Which of them echo (the one you drive, the ones
    -- near you) is D.5's call.
    type = "bool-setting",
    name = "jamaltron-chat-echo",
    setting_type = "runtime-per-user",
    default_value = false,
    order = "a",
  },
}

data:extend(settings)
