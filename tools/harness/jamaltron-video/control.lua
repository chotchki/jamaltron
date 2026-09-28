-- tools/video.sh's DIRECTOR (PLAN G.2-G.3): stages the gameplay video through the mod's own code
-- and films it, one stamped jpg a tick, under `factorio --benchmark-graphics` (no hands). The
-- same code runs headless first as video.sh's dry run: take_screenshot is a no-op there, every
-- beat still plays and both logs are written, so a take that cannot finish fails in ~10 s instead
-- of a minute into the graphics run.
--
--   set.lua      the fixture's on_init and the dressing, rebuilt from a table every run
--   story.lua    the event-driven beat machine, the quiet director, the detectors
--   camera.lua   the eased camera, the shot, the tick stamp, the stills
--   journal.lua  events.jsonl + track.jsonl, the builders' interface
--   take.lua     WRITTEN by video.sh (gitignored), validated there before launch - a syntax error
--                in it made the game SIGSEGV on load in the G.1 capture spike, not report it:
--                  {take = "main"|"loop", capture = bool, resolution = {1920, 1104}, band = 24,
--                   quality = 90, dir = "video/<take>", stills = bool}
--   data-final-fixes.lua  the footfall trigger on jamaltron's legs
--
-- The contract every builder codes against (the take, both logs, the cut, the captions, the
-- encode) is tools/README.md's Video section - what "the contract" means in these files; the
-- beats and staging are in story.lua's header, the logs' writer is journal.lua.
--
-- Logs `VIDEO ...` lines for people (beats, forced rows, liberties, measurements) and
-- `VIDEO FAIL <why>` for anything video.sh must fail the run on. The mod's own debug switch is
-- on: `jamaltron speech <unit> <row>` for every row he says, the captions' cross-check.

local story = require("story")
local set = require("set")

---The take's config, or a headless default so a bare load (lint, a manual run) still works.
local ok, cfg = pcall(require, "take")
if not ok or type(cfg) ~= "table" then
  cfg = {take = "main", capture = false, resolution = {1920, 1104}, band = 24, quality = 90,
         dir = "video/main", stills = false}
end

script.on_init(set.on_init)

script.on_event(defines.events.on_tick, function(event)
  if storage.video == nil then
    story.stage(cfg, event.tick)
    return
  end
  story.tick(event.tick)
end)

-- A multiple of jamaltron's 15 and 60: runs after both of its handlers on the same tick.
script.on_nth_tick(15, function()
  story.nth()
end)

script.on_event("on_spidertron_replaced", story.on_replaced)
script.on_event("jamaltron-fired", story.on_fired)
script.on_event(defines.events.on_script_trigger_effect, story.on_trigger)
script.on_event(defines.events.on_spider_command_completed, story.on_command_completed)
script.on_event(defines.events.on_entity_died, story.on_died, {{filter = "type", type = "unit"}})
script.on_event(defines.events.on_entity_damaged, story.on_damaged,
  {{filter = "name", name = "jamaltron"}, {filter = "name", name = "jamaltron-airborne"},
   {filter = "name", name = "jamaltron-beached"}})
