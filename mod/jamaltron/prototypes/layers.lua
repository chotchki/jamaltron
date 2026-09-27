-- D.7.4's W1 layers (entity.lua's header has why and what they cost): his torso on C.layer_body,
-- every leg's two parts AND its knee joints on C.layer_legs, both above his flamethrower's stream.
-- Shadows and water reflections keep stock's.
--
-- One place for it because it runs twice: entity.lua in data, and compat.lua again in
-- data-final-fixes - a mod that swaps his leg or torso art in data-updates replaces the table
-- that carried the layer, and headless never shows the flame back on top of him.

local C = require("prototypes.shared")

local M = {}

---His torso over his legs and the stream.
---@param gs data.SpiderVehicleGraphicsSet
function M.torso(gs)
  gs.render_layer = C.layer_body
end

---Leg prototype `leg` over the stream. False, and nothing changed, when it has no upper and lower
---part to layer.
---@param leg data.SpiderLegPrototype
---@return boolean
function M.leg(leg)
  local lgs = leg.graphics_set
  if not (lgs and lgs.upper_part and lgs.lower_part) then return false end
  lgs.upper_part.render_layer = C.layer_legs
  lgs.lower_part.render_layer = C.layer_legs
  lgs.joint_render_layer = C.layer_legs
  return true
end

---Whether `leg` already draws where W1 wants it.
---@param leg data.SpiderLegPrototype
---@return boolean
function M.leg_ok(leg)
  local lgs = leg.graphics_set
  return lgs ~= nil and lgs.upper_part ~= nil and lgs.lower_part ~= nil
    and lgs.upper_part.render_layer == C.layer_legs and lgs.lower_part.render_layer == C.layer_legs
    and lgs.joint_render_layer == C.layer_legs
end

return M
