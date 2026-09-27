-- Console commands for playtesting jamaltron by hand, in the isolated profile tools/play.sh
-- builds. Plain commands rather than /c, so nothing here needs the Lua console.
--
--   /jamaltron-kit             a Jamaltron and 50 flamethrower ammo (D.7: his guns take nothing
--                              else) in your inventory, and every line he says LOGGED with its
--                              catalog row id to .playtest/write/factorio-current.log - not
--                              chat (chotchki 2026-09-26: the chat echo was noise in play)
--   /jamaltron-ids [on|off]    row ids in CHAT as well, for "that one reads wrong" -> the row
--                              in character/lines.md; no argument toggles
--   /jamaltron-say <pool> [c]  he says a line from a pool, e.g. `legs_break self`,
--                              `jump_refused water`, `flopping` - the E-phase pools too
--   /jamaltron-row <id>        he says exactly that row (a setup brings its punchline)
--   /jamaltron-state           his speech record: breaks, fork, last line, pending chain
--   /jamaltron-swap <body>     D.4's body swap, straight: jamaltron | beached | airborne, in
--                              place, no jump, no refusal checks (PLAN D.4.8's checklist: what
--                              a real player's seat, held key, remotes, GUI, camera and pins do
--                              across a swap, none of it visible headless). Into beached he is
--                              also KEPT as broken (half health, alert, flops, up when
--                              repaired); for the real break, set the leg-break chance to 100
--                              in Mod settings and jump. Into airborne he lands where he is
--                              within a second
--   /jamaltron-jump-mode [m]   E.1's comparison, map-wide: `arc` (the default) or `teleport`;
--                              no argument prints the current one. A command, not /c, so the
--                              A/B does not cost the save its achievements
--
-- "He" is the Jamaltron under your cursor, else the one you are in, else the nearest within
-- 30 tiles. /jamaltron-swap finds any of his three bodies the same way.

local NAME = "jamaltron"
local BODIES = {[NAME] = NAME, beached = NAME .. "-beached", airborne = NAME .. "-airborne"}
local FAMILY = {}
for _, name in pairs(BODIES) do FAMILY[name] = true end

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
    player.insert{name = "flamethrower-ammo", count = 50}
    remote.call("jamaltron", "debug", true)
    player.print("Jamaltron and flamethrower ammo in your inventory. His lines log with their row "
                 .. "ids; /jamaltron-ids puts them in chat too. The spidertron remote is on the "
                 .. "shortcut bar.")
  end)

commands.add_command("jamaltron-ids", "[on|off] - his line row ids in chat too (no argument toggles).",
  function(cmd)
    local player = cmd.player_index and game.get_player(cmd.player_index)
    if not player then return end
    local arg = (cmd.parameter or ""):match("^%s*(%S+)")
    if arg and arg ~= "on" and arg ~= "off" then
      player.print("Usage: /jamaltron-ids [on|off]")
      return
    end
    storage.ids = (arg == "on") or (arg == nil and not storage.ids)
    remote.call("jamaltron", "debug", storage.ids and "print" or true)
    player.print("Row ids in chat: " .. (storage.ids and "on" or "off"))
  end)

-- A save where the old kit switched the chat echo on keeps it in the mod's storage, so any load
-- that changes a mod (this file included) resets it to log-only; /jamaltron-ids brings it back.
script.on_configuration_changed(function()
  storage.ids = false
  remote.call("jamaltron", "debug", true)
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

commands.add_command("jamaltron-swap", "<jamaltron|beached|airborne> - swap him into that body, in place.",
  function(cmd)
    local player = cmd.player_index and game.get_player(cmd.player_index)
    if not player then return end
    local name = BODIES[(cmd.parameter or ""):match("^%s*(%S+)") or ""]
    if not name then
      player.print("Usage: /jamaltron-swap <jamaltron|beached|airborne>")
      return
    end
    local entity = nil
    local here = {player.selected, player.vehicle}      -- not ipairs: a nil first stops it cold
    for i = 1, 2 do
      local e = here[i]
      if e and e.valid and FAMILY[e.name] then entity = e break end
    end
    if not entity then
      local names = {}
      for n in pairs(FAMILY) do names[#names + 1] = n end
      entity = player.surface.find_entities_filtered{name = names, position = player.position, radius = 30,
                                                      limit = 1}[1]
    end
    if not entity then
      player.print("No Jamaltron body under the cursor, driven, or within 30 tiles.")
      return
    end
    local r = remote.call("jamaltron-harness", "swap", entity, name, {reason = "playtest"})
    player.print(r.body and (r.status .. ": " .. r.body.name .. " #" .. r.body.unit_number)
                 or ("no swap: " .. tostring(r.status)))
    -- A bare swap to beached is a body breakage never made: no alert, no flops, and at full
    -- health nothing for a repair to do. Kept, it is a break in all but the line.
    if r.body and r.body.name == BODIES.beached and remote.call("jamaltron-harness", "keep", r.body) then
      player.print("Kept as broken: half health, the alert, the flops - repair him to stand him up.")
    end
    -- A bare swap to airborne has no arc to land it: invisible, locked, you in it, for good.
    -- Stranded, the next poll lands him where he is (within a second).
    if r.body and r.body.name == BODIES.airborne and remote.call("jamaltron-harness", "strand", r.body) then
      player.print("Stranded: he lands where he is on the next poll.")
    end
  end)

commands.add_command("jamaltron-jump-mode", "[arc|teleport] - how he jumps, map-wide (E.1's A/B).",
  function(cmd)
    local player = cmd.player_index and game.get_player(cmd.player_index)
    if not player then return end
    local mode = (cmd.parameter or ""):match("^%s*(%S+)")
    if mode and mode ~= "arc" and mode ~= "teleport" then
      player.print("Usage: /jamaltron-jump-mode [arc|teleport]")
      return
    end
    player.print("Jump mode: " .. remote.call("jamaltron", "jump_mode", mode))
  end)
