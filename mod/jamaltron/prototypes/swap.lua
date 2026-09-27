-- D.4: the community's "this spidertron was replaced by another entity" event. Spidertron
-- Enhancements defines it; Spidertron Patrols, SpidertronHunter and ESIR listen for it. Raising
-- it on every body swap moves THEIR per-spider state (patrol routes, path renders, dock links)
-- across a jump for free. Defined here as well because nothing guarantees Enhancements is
-- loaded, and a bare custom-event defined by both mods is the same prototype either way.
if not (data.raw["custom-event"] or {})["on_spidertron_replaced"] then
  data:extend({{type = "custom-event", name = "on_spidertron_replaced"}})
end
