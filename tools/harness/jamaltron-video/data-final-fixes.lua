-- FOOTFALLS, the one prototype edit the director makes (PLAN G.3): a script trigger appended to
-- every leg of the VEHICLE body's leg_hit_the_ground_trigger, raising on_script_trigger_effect
-- with the foot's position - the audio's step onsets. There is no runtime touchdown event.
-- MEASURED by the G.1 api agent (a probe mod doing exactly this): 108 events in 300 ticks of
-- walking, in 4-leg groups every ~11-12 ticks, tick-exact against the foot trace, a few
-- duplicates in the first ~12 ticks after a start. The shipped mod is untouched (this runs in a
-- throwaway profile only) and the trigger draws nothing: the take looks exactly like the game.
--
-- data-final-fixes, after jamaltron's own (a dependency loads first), so the legs are final.
-- The airborne and beached bodies are copies made in jamaltron's data stage, before this runs:
-- they stay silent, which is right - the airborne legs are hidden and the beached has none.

local EFFECT_ID = "jamaltron-video-footfall"

local vehicle = data.raw["spider-vehicle"]["jamaltron"]
assert(vehicle, "jamaltron-video: no jamaltron spider-vehicle to hear the feet of")
local legs = vehicle.spider_engine.legs
if legs.leg then legs = {legs} end              -- a single SpiderLegSpecification, not a list
for _, spec in pairs(legs) do
  local item = {type = "script", effect_id = EFFECT_ID}
  local trigger = spec.leg_hit_the_ground_trigger
  if trigger == nil then
    spec.leg_hit_the_ground_trigger = {item}
  elseif trigger.type then                      -- one effect, not a list of them
    spec.leg_hit_the_ground_trigger = {trigger, item}
  else
    table.insert(trigger, item)
  end
end
