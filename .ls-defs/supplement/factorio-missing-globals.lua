---@meta _
-- Globals the Factorio docs define but the fmtk 2.0.8 LuaLS bundle does not
-- emit. It ships the FeatureFlags *type* but never declares the global that
-- holds one, so `feature_flags["quality"]` reads as undefined-global without
-- this file. Re-check the list when the bundle is regenerated against a newer
-- fmtk; drop entries that upstream starts emitting.

---A dictionary of feature flags and their status, readable in every stage.
---https://lua-api.factorio.com/2.1.17/auxiliary/data-lifecycle.html
---@type FeatureFlags
feature_flags = {}
