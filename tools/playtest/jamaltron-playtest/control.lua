-- Console commands for playtesting jamaltron by hand, in the isolated profile tools/play.sh
-- builds. Plain commands rather than /c, so nothing here needs the Lua console.
--
--   /jamaltron-kit             a Jamaltron in your inventory, and every line he says gets its
--                              catalog row id printed in chat (so "that one reads wrong" maps
--                              straight to character/lines.md)
--   /jamaltron-say <pool> [c]  he says a line from a pool, e.g. `legs_break self`,
--                              `jump_refused water`, `flopping` - the E-phase pools too
--   /jamaltron-row <id>        he says exactly that row (a setup brings its punchline)
--   /jamaltron-state           his speech record: breaks, fork, last line, pending chain
--
-- "He" is the Jamaltron under your cursor, else the one you are in, else the nearest within
-- 30 tiles.

local NAME = "jamaltron"

---@param player LuaPlayer
---@return LuaEntity?
local function target(player)
  for _, entity in ipairs({player.selected, player.vehicle}) do
    if entity and entity.valid and entity.name == NAME then
      return entity
    end
  end
  return player.surface.find_entities_filtered{name = NAME, position = player.position,
                                               radius = 30, limit = 1}[1]
end

---@param cmd CustomCommandData
---@return LuaPlayer?, LuaEntity?
local function who(cmd)
  local player = cmd.player_index and game.get_player(cmd.player_index)
  if not player then
    return nil, nil
  end
  local entity = target(player)
  if not entity then
    player.print("No Jamaltron under the cursor, driven, or within 30 tiles.")
  end
  return player, entity
end

commands.add_command("jamaltron-kit", "Give yourself a Jamaltron, and print every line's row id in chat.",
  function(cmd)
    local player = cmd.player_index and game.get_player(cmd.player_index)
    if not player then return end
    player.insert{name = NAME, count = 1}
    remote.call("jamaltron", "debug", "print")
    player.print("Jamaltron in your inventory. Row ids print in chat from now on. "
                 .. "The spidertron remote is on the shortcut bar.")
  end)

commands.add_command("jamaltron-say", "<pool> [condition] - he says a line from that pool.",
  function(cmd)
    local player, entity = who(cmd)
    if not (player and entity) then return end
    local pool, cond = (cmd.parameter or ""):match("^%s*(%S+)%s*(%S*)")
    if not pool then
      player.print("Usage: /jamaltron-say <pool> [condition], e.g. /jamaltron-say legs_break self")
      return
    end
    local ok, said = pcall(remote.call, "jamaltron", "say", entity, pool, cond ~= "" and cond or nil)
    if not ok then
      player.print(tostring(said))
    elseif said == nil then
      player.print(pool .. ": nothing - a cooldown, a silence window or a pending punchline held him")
    end
  end)

commands.add_command("jamaltron-row", "<row id> - he says exactly that row.",
  function(cmd)
    local player, entity = who(cmd)
    if not (player and entity) then return end
    local id = (cmd.parameter or ""):match("^%s*(%S+)")
    if not (id and remote.call("jamaltron-harness", "force", entity, id)) then
      player.print("No such row: " .. tostring(id))
    end
  end)

commands.add_command("jamaltron-state", "His speech record.",
  function(cmd)
    local player, entity = who(cmd)
    if not (player and entity) then return end
    player.print(serpent.line(remote.call("jamaltron-harness", "state", entity)))
  end)
