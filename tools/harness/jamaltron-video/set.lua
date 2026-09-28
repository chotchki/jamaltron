-- THE SET (PLAN G.2): the fixture's once-only prep and the dressing, rebuilt from the table below
-- on the first tick of EVERY run, so an edit here shows on the next take with no --fresh.
--
-- THE FIXTURE is tools/video.sh's --create with a PINNED --map-gen-seed and no enemy bases
-- (map-gen-settings), so the ground outside the pad and every map-rng roll after it are the same
-- on every machine that builds it. on_init() below is all the fixture keeps of this file:
--   * freeplay's crash site, intro AND chart distance off. MEASURED (G.1 scene agent): a
--     graphics run of a save without them stops simulating at tick 750 - the crash-site cutscene
--     (450+150+150 ticks) ends in show_message_dialog, which pauses single-player. The shot
--     stager's two calls are not enough; set_chart_distance(0) is the third
--   * the chunks under the pad generated, nothing enemy left on them, no pollution or expansion
--
-- THE GEOMETRY, one row a storyboard beat depends on (the story runs west -> east along y=0.5):
--   A      -43.5  start; the creek's west bank, 2.5 tiles from the water
--   creek  3 wide, deepwater, the pad's full height, meandering 2 tiles either way over 56 rows -
--          straight on the jump row (tiles -41..-39 at y=0): hop1 and the loop cross it there
--   B      -35.5  hop1's landing, A + 8 (the default jump), 2.5 tiles past the creek
--   C      -27.5  hop2's landing, B + 8 over grass: the fight happens here
--   E      -15.5  the report's autopilot mark, 5.5 tiles from the lake. MEASURED: an autopilot
--                 order overshoots its mark by ~1.5-2 tiles (G.1 scene agent: 18.5 at completion,
--                 settled 22 on a 20-tile order), so he stops >= 3 tiles from the water, where no
--                 shore stall can fire (an EVENT line that would bypass the quiet director)
--   lake   a tilted ellipse (24 x 10, 62 degrees) with two harmonics on its rim, so it reads as a
--          lake and not a pool (the first take's upright raster ellipse looked dug): its row at
--          y=0 is tiles -9..1, 11 wide. <= 12 on purpose: jump.lua's STRADDLE (12) skips the
--          landmass check for a run of water that short. The d=20 jump from ~E lands ~4 tiles
--          past its far shore
--   F      ~ E' + 20, where E' is where he really stopped; check() logs the planned landing
--   roboport (11, -4): ~6.7 tiles from F. 5 construction bots, NO packs (the cue brings them)
--   power  big poles at (14, -4) and (46, -4), 32 apart (the pole's reach), the EEI beside the
--          second: the lake and repair frames end at x ~21 and ~27, so it never shows; the wire
--          does, leading off-frame as a real base's would
--   spawn  C + (21, -21): the wave comes in from the north-east, north of the lake's tip (y -11)
-- Friendly entities stay > 10 tiles from where biters die (his splash burns them): the fight is
-- at C, the nearest friendly (the roboport) ~39 tiles east.
--
-- check() MEASURES what the jumps need off the built surface and logs it; a violation is a
-- VIDEO FAIL, which fails the dry run before any graphics take is spent on a set that cannot work.

local M = {}

---The pad and what is painted on it, in tile coordinates (a box's right_bottom is exclusive).
M.PAD = {left_top = {-96, -96}, right_bottom = {96, 96}, tile = "grass-1"}

---@class Video.Strip a band of water running north-south, shifted round(amp*sin(2 pi y/period))
---@field x0 integer its west edge on row 0
---@field width integer
---@field amp number
---@field period number

---@class Video.Blob an ellipse turned `rot` degrees, its rim scaled by 1 + sum(a*sin(k*theta+ph))
---@field centre number[]
---@field axes number[] semi-axes, tiles
---@field rot number
---@field wobble number[][] {a, k, ph} each

---@class Video.Water
---@field name string
---@field tile string
---@field strip Video.Strip?
---@field blob Video.Blob?

---@type Video.Water[]
M.WATER = {
  {name = "creek", tile = "deepwater", strip = {x0 = -41, width = 3, amp = 2, period = 56}},
  {name = "lake", tile = "deepwater",
   blob = {centre = {-3.5, 0.5}, axes = {12, 5}, rot = 62, wobble = {{0.07, 3, 0.4}, {0.05, 7, 2.0}}}},
}

---Where things happen (positions, tiles).
M.MARKS = {
  A = {x = -43.5, y = 0.5},
  B = {x = -35.5, y = 0.5},
  C = {x = -27.5, y = 0.5},
  E = {x = -15.5, y = 0.5},
  engineer = {x = -57.5, y = 2.0},   -- off the establish frame's left edge (A.x - 13 at zoom 2)
  spawn = {x = -6.5, y = -20.5},      -- C + (21, -21)
  creek_centre = {x = -39.5, y = 0.5},
}

---The dressing: built in this order (the poles before the EEI they power).
M.ENTITIES = {
  {name = "roboport", position = {11, -4}, robots = 5},
  {name = "big-electric-pole", position = {14, -4}},
  {name = "big-electric-pole", position = {46, -4}},
  {name = "electric-energy-interface", position = {48, -4}},
}

---The area cleared and painted: the pad.
---@return BoundingBox
local function pad_area()
  return {M.PAD.left_top, M.PAD.right_bottom}
end

---Is tile (x, y) this water? Trig here is fine: it paints tiles once a run, it never moves him.
---@param w Video.Water
---@param x integer
---@param y integer
---@return boolean
local function wet(w, x, y)
  local st = w.strip
  if st then
    local off = math.floor(st.amp * math.sin(2 * math.pi * y / st.period) + 0.5)
    return x >= st.x0 + off and x < st.x0 + off + st.width
  end
  local b = w.blob --[[@as Video.Blob]]
  local px, py = x + 0.5 - b.centre[1], y + 0.5 - b.centre[2]
  local c, s = math.cos(math.rad(b.rot)), math.sin(math.rad(b.rot))
  local u = (px * c + py * s) / b.axes[1]
  local v = (-px * s + py * c) / b.axes[2]
  local theta = math.atan2(v, u)
  local rim = 1
  for _, h in ipairs(b.wobble) do rim = rim + h[1] * math.sin(h[2] * theta + h[3]) end
  return u * u + v * v <= rim * rim
end

---on_init, i.e. only when tools/video.sh --create builds the fixture.
function M.on_init()
  if remote.interfaces["freeplay"] then
    remote.call("freeplay", "set_disable_crashsite", true)
    remote.call("freeplay", "set_skip_intro", true)
    remote.call("freeplay", "set_chart_distance", 0)
  end
  local s = game.surfaces[1]
  s.request_to_generate_chunks({0, 0}, 5)          -- 5 chunks = 160 tiles each way: the pad + margin
  s.force_generate_chunk_requests()
  for _, e in pairs(s.find_entities_filtered{force = "enemy"}) do
    e.destroy()
  end
  game.map_settings.enemy_expansion.enabled = false
  game.map_settings.pollution.enabled = false
  s.show_clouds = false                            -- their shadows sweep the ground (shot stager)
  s.freeze_daytime = true
  s.daytime = 0                                    -- noon
  s.peaceful_mode = true                           -- until the wave beat
  log("VIDEO fixture built: crash site, intro and chart distance off; chunks generated")
end

---The dressing, on the first tick of a run: the pad cleared and painted, the water, the
---roboport and its power. Deterministic: the same fixture and table give the same set.
---@param s LuaSurface
---@return table<string, LuaEntity> built entities by role (roboport, ...)
function M.build(s)
  local area = pad_area()
  for _, e in pairs(s.find_entities_filtered{area = area}) do
    if e.valid and e.type ~= "character" then e.destroy() end
  end
  s.destroy_decoratives{area = area}
  local tiles = {}
  for x = M.PAD.left_top[1], M.PAD.right_bottom[1] - 1 do
    for y = M.PAD.left_top[2], M.PAD.right_bottom[2] - 1 do
      local name = M.PAD.tile
      for _, w in ipairs(M.WATER) do
        if wet(w, x, y) then name = w.tile break end
      end
      tiles[#tiles + 1] = {name = name, position = {x, y}}
    end
  end
  s.set_tiles(tiles, true, false)
  local built = {}
  local poles = {}
  for _, spec in ipairs(M.ENTITIES) do
    local e = s.create_entity{name = spec.name, position = spec.position, force = "player"}
    if not e then
      log("VIDEO FAIL set: could not create " .. spec.name .. " at " .. serpent.line(spec.position))
    else
      if spec.name == "roboport" then
        built.roboport = e
        local robots = e.get_inventory(defines.inventory.roboport_robot)
        if robots and spec.robots then robots.insert{name = "construction-robot", count = spec.robots} end
      elseif spec.name == "big-electric-pole" then
        poles[#poles + 1] = e
      elseif spec.name == "electric-energy-interface" then
        built.power = e
      end
    end
  end
  -- Wire the poles in a chain. Script-built poles may auto-connect; connect_to on a pair that is
  -- already wired is a no-op.
  for i = 2, #poles do
    local a = poles[i - 1].get_wire_connector(defines.wire_connector_id.pole_copper, true)
    local b = poles[i].get_wire_connector(defines.wire_connector_id.pole_copper, true)
    a.connect_to(b, false)
  end
  return built
end

---The first tile coordinate along +x from `x0` at row `y` whose tile is water, else nil.
---@param s LuaSurface
---@param x0 number
---@param x1 number
---@param y number
---@return integer water tiles crossed between x0 and x1 on row y
local function water_between(s, x0, x1, y)
  local n = 0
  local lo, hi = math.min(x0, x1), math.max(x0, x1)
  for x = math.floor(lo), math.floor(hi) do
    local t = s.get_tile(x, y)
    if t.collides_with("water_tile") then n = n + 1 end
  end
  return n
end

---@param s LuaSurface
---@param p MapPosition
---@return boolean
local function land(s, p)
  return not s.get_tile(p.x, p.y).collides_with("water_tile")
end

---MEASURE the set against what the storyboard needs (the default 8-tile hops from A, the 20-tile
---lake jump from E); log it, and FAIL what cannot work.
---@param s LuaSurface
---@param built table<string, LuaEntity>
function M.check(s, built)
  local m = M.MARKS
  local problems = {}
  local function need(ok, what) if not ok then problems[#problems + 1] = what end end
  local b, c = {x = m.A.x + 8, y = m.A.y}, {x = m.A.x + 16, y = m.A.y}
  local creek = water_between(s, m.A.x, b.x, m.A.y)
  need(land(s, m.A) and land(s, b) and land(s, c), "A, A+8 and A+16 must be land")
  need(creek == 3, "hop1 crosses the 3-wide creek (crossed " .. creek .. ")")
  need(water_between(s, b.x, c.x, m.A.y) == 0, "hop2 is over open grass")
  local lake = water_between(s, m.E.x, m.E.x + 20, m.E.y)
  need(lake >= 8 and lake <= 12, "the lake jump crosses 8-12 tiles of water (crossed " .. lake .. ")")
  need(land(s, {x = m.E.x + 20, y = m.E.y}), "E+20 is land")
  local shore = m.E.x
  while land(s, {x = shore, y = m.E.y}) and shore < m.E.x + 20 do shore = shore + 0.5 end
  need(shore - m.E.x >= 5, "E sits >= 5 tiles from the lake (" .. (shore - m.E.x) .. ")")
  -- Anything the clear missed (a decorative on the pad shows in every frame that passes it).
  local area = pad_area()
  local decos = s.find_decoratives_filtered{area = area}
  local ents = s.find_entities_filtered{area = area, type = {"character", "spider-vehicle", "roboport",
    "electric-pole", "electric-energy-interface"}, invert = true}
  local names = {}
  for i = 1, math.min(#decos, 5) do names[#names + 1] = decos[i].decorative.name .. "@" ..
    serpent.line(decos[i].position) end
  for i = 1, math.min(#ents, 5) do names[#names + 1] = ents[i].name .. "@" .. serpent.line(ents[i].position) end
  log("VIDEO set: " .. #decos .. " decoratives, " .. #ents .. " stray entities left on the pad "
      .. table.concat(names, " "))
  local robo = built.roboport
  need(robo ~= nil and robo.valid, "the roboport stands")
  local powered = robo and robo.valid and robo.is_connected_to_electric_network()
  need(powered == true, "the roboport is on the network")
  log(string.format("VIDEO set: pad %dx%d %s; creek %d tiles on hop1; lake %d tiles on E->E+20; "
      .. "E %.1f tiles from the water; roboport at %s powered %s",
      M.PAD.right_bottom[1] - M.PAD.left_top[1], M.PAD.right_bottom[2] - M.PAD.left_top[2],
      M.PAD.tile, creek, lake, shore - m.E.x, robo and serpent.line(robo.position) or "none",
      tostring(powered)))
  for _, p in ipairs(problems) do log("VIDEO FAIL set: " .. p) end
  return #problems == 0
end

return M
