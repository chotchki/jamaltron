-- tools/shot.sh's stager: pictures out of the REAL renderer, which headless never draws.
--
-- on_init runs once, when shot.sh --create's the fixture save, and bakes a clean pad into it:
-- chunks generated, the crash site / trees / rocks / decoratives gone from the middle, one flat
-- tile, daytime frozen at noon, peaceful. Every run after LOADS the fixture (no map generation,
-- the same ground every time); the first tick stages scene.lua's scene through the mod's own
-- code paths (a beached Jamal is a real break, airborne -> breakage.on_landing at 100%, so
-- whatever the break draws is drawn), then one screenshot per `shots` tick lands in
-- script-output/ for shot.sh to copy out.
--
-- Logs `SHOT staged` / `SHOT taken <file>` / `SHOT FAIL <why>`; shot.sh fails the run on FAIL.
-- The fixture's promises are checked, not trusted: at staging and at every shot, a crash site on
-- the pad, freeplay's intro or crash-site flags back on, clouds, a cutscene or a player
-- character in the picture is a SHOT FAIL.

local cfg = require("scene")

local H = "jamaltron-harness"
local PAD = 40
-- Tiles between Jamals in `many`. shot.sh owns the number (it frames the grid off it).
local SPACING = cfg.spacing or 9

---@param why string
local function fail(why)
  log("SHOT FAIL " .. why)
end

script.on_init(function()
  -- Freeplay drops its crash site (wreck, fires) when the first player joins, AFTER on_init.
  if remote.interfaces["freeplay"] then
    remote.call("freeplay", "set_disable_crashsite", true)
    remote.call("freeplay", "set_skip_intro", true)
  end
  local s = game.surfaces[1]
  s.request_to_generate_chunks({0, 0}, 3)
  s.force_generate_chunk_requests()
  local area = {{-PAD, -PAD}, {PAD, PAD}}
  for _, e in pairs(s.find_entities_filtered{area = area}) do
    if e.valid and e.type ~= "character" then e.destroy() end
  end
  local tiles = {}
  for x = -PAD, PAD - 1 do
    for y = -PAD, PAD - 1 do
      tiles[#tiles + 1] = {name = cfg.tile or "sand-1", position = {x, y}}
    end
  end
  s.set_tiles(tiles, true, false)
  s.destroy_decoratives{area = area}
  s.show_clouds = false     -- their shadows sweep across the pad and read as terrain
  s.freeze_daytime = true
  s.daytime = 0
  s.peaceful_mode = true
  for _, e in pairs(s.find_entities_filtered{force = "enemy", radius = 300, position = {0, 0}}) do
    e.destroy()
  end
  log("SHOT fixture pad " .. (2 * PAD) .. " tiles of " .. (cfg.tile or "sand-1"))
end)

---A standing jamaltron at `pos`.
---@param s LuaSurface
---@param pos MapPosition
---@return LuaEntity?
local function standing(s, pos)
  local j = s.create_entity{name = "jamaltron", position = pos, force = "player"}
  if not j then fail("create jamaltron at " .. serpent.line(pos)) return nil end
  j.color = {1, 0.55, 0.1}   -- a player's default orange, what chotchki's own screenshots show
  return j
end

---A beached jamaltron at `pos`, broken the way a jump breaks him: into the airborne body, then
---landed by breakage.on_landing with the break chance pinned at 100.
---@param s LuaSurface
---@param pos MapPosition
---@return LuaEntity?
local function beached(s, pos)
  local j = standing(s, pos)
  if not j then return nil end
  remote.call(H, "setting", "jamaltron-leg-break-percent", 100)
  local up = remote.call(H, "swap", j, "jamaltron-airborne", {reason = "takeoff", autopilot = false})
  if not up.body then fail("takeoff swap " .. tostring(up.status)) return nil end
  local down = remote.call(H, "land", up.body, pos, {tick = game.tick, distance = 8})
  if down.outcome ~= "broke" then fail("landing came out " .. tostring(down.outcome)) return nil end
  return down.body
end

---`n` real breaks in a near-square grid SPACING apart, one standing Jamal in a column of his own
---to the left for scale, the block centred on cfg.center. Each break is the full path, in order
---on the map rng, so every wreck is laid out differently: one shot shows the layout's spread.
---@param s LuaSurface
---@param n integer
local function many(s, n)
  local cols = math.ceil(math.sqrt(n))
  local rows = math.ceil(n / cols)
  -- Grid columns 1..cols, the standing column 0: centre the span 0..cols and 1..rows.
  local x0 = cfg.center[1] - cols * SPACING / 2
  local y0 = cfg.center[2] - (rows + 1) * SPACING / 2
  standing(s, {x0, cfg.center[2]})
  for i = 0, n - 1 do
    beached(s, {x0 + (i % cols + 1) * SPACING, y0 + (math.floor(i / cols) + 1) * SPACING})
  end
end

local SCENES = {
  beached = function(s) beached(s, cfg.center) end,
  standing = function(s) standing(s, cfg.center) end,
  both = function(s)
    standing(s, {cfg.center[1] - 6, cfg.center[2]})
    beached(s, {cfg.center[1] + 6, cfg.center[2]})
  end,
  many = function(s)
    local n = cfg.many or 6
    if n < 1 then fail("many wants at least one break, scene.lua has " .. tostring(n)) return end
    many(s, n)
  end,
}

---Every way freeplay (or the benchmark's own player) could put something in the picture that is
---not the scene. `when` names the moment for the FAIL line.
---@param s LuaSurface
---@param when string
local function check_clean(s, when)
  if remote.interfaces["freeplay"] then
    if not remote.call("freeplay", "get_disable_crashsite") then
      fail(when .. ": freeplay's crash site is enabled again")
    end
    if not remote.call("freeplay", "get_skip_intro") then
      fail(when .. ": freeplay's intro is enabled again")
    end
    for _, e in pairs(s.find_entities_filtered{area = {{-PAD, -PAD}, {PAD, PAD}}}) do
      if e.name:find("^crash%-site") then
        fail(when .. ": crash site " .. e.name .. " on the pad at " .. serpent.line(e.position))
        break
      end
    end
  end
  if s.show_clouds then fail(when .. ": clouds are on") end
  for _, player in pairs(game.players) do
    if player.character then
      fail(when .. ": player " .. player.index .. " has a character at "
           .. serpent.line(player.character.position))
    end
    if player.controller_type == defines.controllers.cutscene then
      fail(when .. ": player " .. player.index .. " is in a cutscene")
    end
  end
end

local staged_at ---@type integer?
local due = {}   ---@type table<integer, boolean>
local last = 0

script.on_event(defines.events.on_tick, function(event)
  local s = game.surfaces[1]
  if not staged_at then
    staged_at = event.tick
    local scene = SCENES[cfg.scene]
    if not scene then fail("no scene '" .. tostring(cfg.scene) .. "'") return end
    remote.call("jamaltron", "debug", false)
    -- --benchmark-graphics has a local player, and freeplay gives it a character standing at
    -- the origin: out of the picture.
    for _, player in pairs(game.players) do
      if player.character then player.character.destroy() end
    end
    scene(s)
    check_clean(s, "staging")
    for _, t in pairs(cfg.shots) do
      due[t] = true
      if t > last then last = t end
    end
    log("SHOT staged " .. cfg.scene .. " at tick " .. event.tick .. ", " .. #game.players
        .. " player(s)")
    return
  end
  local dt = event.tick - staged_at
  if due[dt] then
    check_clean(s, "shot " .. dt)
    local file = string.format("%s-%05d.png", cfg.prefix or "shot", dt)
    game.take_screenshot{surface = s, position = cfg.center, resolution = cfg.resolution,
                         zoom = cfg.zoom, path = file, show_entity_info = false, daytime = 0}
    log("SHOT taken " .. file)
  end
end)
