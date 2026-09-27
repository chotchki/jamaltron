-- THE JUMP (PLAN E.2.6 input + refusals, E.1 the arc, E.3 the landing). SPEC: he is the literal
-- personification of jumping the shark, so the jump has to be SEEN: a swap into an invisible
-- airborne body carried along the ground path on the clock, his own sheets drawn lifted off it
-- and his shadow left on the ground; then breakage.on_landing decides what he lands as.
--
-- try(entity, player) is the one entry point; the key's handler (control.lua), the harness and
-- anyone else call it. It REFUSES before anything moves, and a refusal is a line with its reason
-- (jump_refused's gated split), in this order:
--   no_driver   remote-driven (get_driver() a LuaPlayer whose physical_vehicle is not him - kept
--               apart until D.4.8 measures what the swap's seat move does to one), the presser
--               a passenger, or nobody in the seat
--   autopilot   a destination is set (following sets one too)
--   platform    a Space Age platform: E.6 forbids it
--   cooldown    per body, jamaltron-jump-cooldown seconds since his last takeoff
--   <ground>    the landing tile per scripts/ground.lua - water, lava, ammoniacal-solution, void
--   blocked     a FOOT cannot stand on the landing point (the leg's collision, never the body's:
--               the body collides with trigger_target only and can be placed on deep water)
--   <ground>    no way back: see STRADDLE
-- plus three silent ones: not the vehicle (mid-arc, beached), the startup setting off (then the
-- key does not exist either), and `frozen` - another mod disabled him or locked his GUI. A jump
-- is two body changes and swap.lua's M.BODY wins on both, so he would land thawed and unlocked
-- (measured); that hold is not ours to undo. A deconstruction mark is the player's own order,
-- so it rides a clean landing (re-ordered on the body he lands as); a break drops it, the
-- beached body being not-deconstructable (D.1).
--
-- HEADING: the direction the driver HOLDS, else the torso snapped to 16 ways. MEASURED: the
-- torso turns at the prototype's 0.005 turns/tick toward the walking direction whatever the
-- input, so a 90-degree turn takes 50 ticks and a reversal 90; jumping off the torso mid-turn
-- goes where he was facing, not where he was sent. Standing still, the torso is all there is.
-- The airborne body gets the heading as its torso, so he lands facing the way he flew. 16 ways,
-- not continuous: a literal table and no trig, stall.lua's rule for anything that moves him.
--
-- THE ARC, numbers per distance d (jamaltron-jump-distance, default 8):
--   peak  H = max(PEAK_MIN, PEAK_PER_TILE * d)       8 -> 3.0 tiles   3 -> 1.5   20 -> 7.5
--   time  T = ARC_TICKS * sqrt(H / ARC_PEAK), rounded 8 -> 30 ticks    3 -> 21    20 -> 47
-- which keeps ONE gravity for every distance (g = 8H/T^2 = 0.027 tiles/tick^2) and one launch
-- angle (atan(4H/d) = 56 degrees, steeper than 45 on purpose: showy, not efficient). Ground
-- position linear in time, height h = 4H u(1-u). Drawn with the game's projection:
--   body    his standing lift plus h * K up-screen (K = 0.7071, factorio_camera.py: a tile of
--           height is 0.7071 tiles of screen)
--   shadow  his standing shadow plus h tiles EAST (the 45-degree sun: a tile of height is a tile
--           of shadow), never lifted, never rotated
--   pitch   nose up at takeoff, level at the peak, nose down at touchdown - the velocity's
--           direction, up to PITCH turns, scaled by how east-west he flies (a sprite rotated in
--           screen space reads as pitch only side-on; flying north it would read as a roll)
-- His STANDING lift and shadow are the engine's, MEASURED off graphics-benchmark screenshots of
-- the leg-less beached body against these render objects: the engine draws a spider-vehicle's
-- torso `height` (1.5) tiles UP-SCREEN, 1:1 and not 0.7071 of it, bobbing +-2-4 px, and its
-- shadow `height` tiles east (2 px). So the arc starts and ends on the pixels the entity uses.
-- Re-measured on a real jump: the takeoff frame's harness band sits 1 px from the standing one,
-- the peak 2.13 tiles above it (3 * 0.7071 = 2.12).
--
-- MODE: "arc" (the default and SPEC's lead) or "teleport" (E.1's option a: the same two swaps in
-- one tick, no arc, the same landing dust and thud). remote.call("jamaltron", "jump_mode", m)
-- flips it map-wide so chotchki can compare them; the verdict is his eye's, not this file's.
--
-- LANDING is scripts/breakage.lua's on_landing (E.4): it rolls the break, does the ONE swap
-- (airborne into the vehicle or the beached body), applies the damage, says the line and returns
-- what he is now. This file picks where (landing_spot: the planned spot, else the nearest footing
-- to it, else his takeoff point, else the nearest footing to that, else wider round the spot - a
-- foot on ground at every step; only if all of it was built over or flooded inside the 0.5 s arc
-- does he land at the takeoff unchecked, logged), raises the dust and the thud, and hands over.
-- The jump line has the arc's 30 ticks on screen before the landing line replaces it; in
-- teleport mode, none.
--
-- STRANDED: a failed landing swap (a listener killed the new body; nothing else makes
-- create_entity fail for a spider-vehicle) leaves him whole in the airborne body. Three retries a
-- second apart on the arc, then OFF the clock into storage's `stranded` set, which the 60-tick
-- poll retries in place as long as it takes: invisible, unselectable and immobile is no state to
-- leave him in, and it costs nothing per tick. His trunk is unlocked meanwhile.
--
-- STATE is storage's (storage.jamaltron.jump), so every peer flies the same arc: the arcs by
-- airborne unit (render objects included), the last takeoff by body unit, the last refusal, the
-- stranded, the mode. root() backfills what an older save lacks (E.6: a code-only update runs no
-- on_configuration_changed, measured, so nothing else would). An airborne body the code did not
-- launch (a bare swap into it) is stranded by adopt(), or it never lands. forget() drops a
-- destroyed body's entries, never an arc. The clock (scripts/clock.lua) runs tick() while any
-- arc is in the air and drops on_tick when none is; only tick() ends an arc, clock.lua's rule.
-- MEASURED: a game server-saved 10 ticks into an arc and benchmarked from that save re-registers
-- on_tick from on_load, finishes the arc and lands on the spot with his driver, nothing left
-- drawn. Module state: the constants.

local C = require("prototypes.shared")
local N = require("prototypes.jump")
local art = require("prototypes.sprites_generated")
local ground = require("scripts.ground")
local speech = require("scripts.speech")
local swap = require("scripts.swap")
local clock = require("scripts.clock")
local breakage = require("scripts.breakage")

---@class Jamaltron.JumpLanding what breakage.on_landing is told about a touchdown
---@field tick integer
---@field height number the arc's peak lift, tiles
---@field distance number tiles from takeoff to touchdown
---@field driver (LuaEntity|LuaPlayer)? who was driving at takeoff, if still valid

local M = {}

---Peak lift per tile of distance, and the floor under short hops (tiles).
M.PEAK_PER_TILE = 0.375
M.PEAK_MIN = 1.5
---The reference arc: ARC_TICKS in the air at ARC_PEAK tiles of lift. Every other arc keeps its
---gravity (T scales with sqrt of the peak).
M.ARC_TICKS = 30
M.ARC_PEAK = 3.0
---Screen tiles per tile of height: the 45-degree camera (tools/render/factorio_camera.py).
M.K = 0.7071067811865
---Most pitch mid-arc, in orientation turns (0.05 = 18 degrees), for a jump straight east or west.
M.PITCH = 0.05
---Tiles of leg-blocking ground he walks straight across (MEASURED: a 3x3 island walked home over
---4-14 tiles of deep water, not 16; E.2.4's rivers stopped him at 15 twice in 75). A landing with
---no more blocking ground than this between it and his takeoff always has a way back, so the
---default 8-tile jump never needs the check below.
M.STRADDLE = 12
---Beyond STRADDLE the landing needs a landmass, not an islet: at least a third of the tiles
---within REACH standable. MEASURED: an isolated island strands him (moved 1.1-4.8 tiles in 10 s
---on islands of 1-7 tiles, never left); the edge of a real far bank holds about half the disc.
---So a 15x15 island (225 of ~700) is refused and a 16x16 is not, the price of one cheap count.
M.REACH = 15
M.FOOTING_SHARE = 1 / 3
---Tiles to search for a place a foot can stand when the spot was built over mid-arc (round the
---spot, then round the takeoff; twice this round the spot is the last try).
M.LAND_SEARCH = 4
---Landings retried on the arc, a second apart, before he is left to the 60-tick poll.
M.RETRIES = 3
---Ticks a second refusal from the same body stays silent: a mashed key is one complaint.
M.REFUSE_GAP = 60
---Trivial smoke for the dust - the puff a spidertron foot kicks up (base's leg trigger).
M.DUST = "smoke-building"

-- defines.direction -> unit vector, as literals (stall.lua's table, and its reason: no trig on
-- anything that moves an entity).
local D45, C22, S22 = 0.70710678118654757, 0.92387953251128674, 0.38268343236508978
local DIR = {
  [0] = {0, -1}, {S22, -C22}, {D45, -D45}, {C22, -S22}, {1, 0}, {C22, S22}, {D45, D45}, {S22, C22},
  {0, 1}, {-S22, C22}, {-D45, D45}, {-C22, S22}, {-1, 0}, {-C22, -S22}, {-D45, -D45}, {-S22, -C22},
}

local SHEETS = art.sprites
local BODY_SHIFT, MASK_SHIFT, SHADOW_SHIFT = SHEETS.body.shift, SHEETS.body_mask.shift, SHEETS.shadow.shift
-- The mask hangs this far below the body's centre; the pitch turns it about that centre.
local MASK_DY = MASK_SHIFT[2] - BODY_SHIFT[2]
local TWO_PI = 6.283185307179586

---@class Jamaltron.Arc
---@field entity LuaEntity the airborne body
---@field from MapPosition where he took off
---@field to MapPosition where he lands
---@field start integer takeoff tick
---@field land integer touchdown tick
---@field peak number tiles of lift at the top
---@field dir integer the defines.direction he flies
---@field lift number his standing lift: the vehicle prototype's height
---@field driver (LuaEntity|LuaPlayer)?
---@field body LuaRenderObject?
---@field mask LuaRenderObject?
---@field shadow LuaRenderObject?
---@field retries integer? landings that came back with no body
---@field decon LuaForce? whose deconstruction order he took off under

---@class Jamaltron.Stranded an airborne body whose landing kept failing, retried on the poll
---@field entity LuaEntity
---@field info Jamaltron.JumpLanding
---@field decon LuaForce?

---@class Jamaltron.JumpRoot
---@field arcs table<integer, Jamaltron.Arc> by the airborne body's unit
---@field last table<integer, integer> body unit -> tick of his last takeoff
---@field refused table<integer, integer> body unit -> tick of his last refusal line
---@field stranded table<integer, Jamaltron.Stranded> by the airborne body's unit
---@field mode "arc"|"teleport"

---@return Jamaltron.JumpRoot
local function root()
  storage.jamaltron = storage.jamaltron or {}
  local r = storage.jamaltron
  r.jump = r.jump or {arcs = {}, last = {}, refused = {}, mode = "arc"}
  r.jump.stranded = r.jump.stranded or {}           -- the jump build's first cut had neither
  r.jump.mode = r.jump.mode or "arc"
  return r.jump
end

---@return integer
local function cooldown_ticks()
  return math.floor((tonumber(settings.global["jamaltron-jump-cooldown"].value) or 5) * 60)
end

---@return number
local function distance()
  return tonumber(settings.global["jamaltron-jump-distance"].value) or 8
end

---The arc for a jump of `d` tiles: peak lift and ticks in the air (the header's table).
---@param d number
---@return number peak
---@return integer ticks
function M.shape(d)
  local peak = math.max(M.PEAK_MIN, M.PEAK_PER_TILE * d)
  return peak, math.max(1, math.floor(M.ARC_TICKS * math.sqrt(peak / M.ARC_PEAK) + 0.5))
end

---Where the arc draws him at fraction u (0 takeoff, 1 touchdown) of a `peak`-tile jump flying
---direction `dir`, standing lift `lift`: offsets from his ground position. Pure arithmetic (the
---tests call it).
---@param u number
---@param peak number
---@param dir integer
---@param lift number
---@return {body: number[], mask: number[], shadow: number[], pitch: number, h: number}
function M.pose(u, peak, dir, lift)
  local h = 4 * peak * u * (1 - u)
  local pitch = -DIR[dir][1] * M.PITCH * (1 - 2 * u)
  local bx, by = BODY_SHIFT[1], BODY_SHIFT[2] - lift - h * M.K
  -- The mask, turned with the body about the body's centre. Screen y points down, so a
  -- clockwise turn a takes (0, r) to (-r sin a, r cos a). Taylor to a^5: within 1e-6 tile at
  -- the 18 degrees PITCH allows, and no math.sin (the header's rule).
  local a = pitch * TWO_PI
  local a2 = a * a
  local sin = a * (1 - a2 / 6 * (1 - a2 / 20))
  local cos = 1 - a2 / 2 * (1 - a2 / 12)
  return {
    body = {bx, by},
    mask = {bx + MASK_SHIFT[1] - BODY_SHIFT[1] - MASK_DY * sin, by + MASK_DY * cos},
    shadow = {SHADOW_SHIFT[1] + lift + h, SHADOW_SHIFT[2]},
    pitch = pitch,
    h = h,
  }
end

---The direction he would jump: the one the driver holds, else his torso to the nearest 16th.
---@param entity LuaEntity
---@param driver (LuaEntity|LuaPlayer)?
---@return integer defines.direction
function M.heading(entity, driver)
  if driver and driver.valid then
    local walking = driver.walking_state
    if walking and walking.walking then
      return walking.direction --[[@as integer]]
    end
  end
  return math.floor(entity.torso_orientation * 16 + 0.5) % 16
end

---The longest run of leg-blocking ground on the straight line from `from` to `to`, sampled
---every half tile, and what the first blocking sample was. Only asked past STRADDLE.
---@param surface LuaSurface
---@param from MapPosition
---@param to MapPosition
---@param d number
---@return number run tiles
---@return string? what
local function water_run(surface, from, to, d)
  local steps = math.ceil(d * 2)
  local run, best, what = 0, 0, nil
  for k = 1, steps do
    local u = k / steps
    local g = ground.of(surface.get_tile(from.x + (to.x - from.x) * u, from.y + (to.y - from.y) * u).name)
    if g then
      run = run + 0.5
      what = what or g
      if run > best then best = run end
    else
      run = 0
    end
  end
  return best, what
end

---Why he cannot jump from here, or nil and where he would land. Reads, never writes (the tests
---drive it with fakes). Order is the header's.
---@param entity LuaEntity a valid jamaltron
---@param player (LuaPlayer|LuaEntity)? who pressed the key - a player, or the character standing
---  in for one (headless has no LuaPlayer); nil for a script asking on the driver's behalf
---@param tick integer
---@return string? reason a jump_refused value
---@return MapPosition? spot
---@return integer? dir
function M.check(entity, player, tick)
  local driver = entity.get_driver()
  if driver == nil then
    return "no_driver"
  end
  if driver.object_name == "LuaPlayer" and driver.physical_vehicle ~= entity then
    return "no_driver"                                   -- remote-driven (D.4.8 decides)
  end
  if player and driver ~= player and not (driver.object_name == "LuaEntity" and driver.player == player) then
    return "no_driver"                                   -- the presser is the passenger
  end
  if entity.autopilot_destination ~= nil then
    return "autopilot"
  end
  local surface = entity.surface
  if surface.platform ~= nil then
    return "platform"
  end
  local r = storage.jamaltron and storage.jamaltron.jump
  local last = r and r.last[entity.unit_number]
  if last and tick - last < cooldown_ticks() then
    return "cooldown"
  end

  local dir = M.heading(entity, driver)
  local d = distance()
  local pos = entity.position
  local v = DIR[dir]
  local spot = {x = pos.x + v[1] * d, y = pos.y + v[2] * d}
  local g = ground.of(surface.get_tile(spot.x, spot.y).name)
  if g then
    return g
  end
  if surface.entity_prototype_collides(C.leg_name(1), spot, false) then
    return "blocked"
  end
  if d > M.STRADDLE then
    local run, what = water_run(surface, pos, spot, d)
    if run > M.STRADDLE then
      local mask = prototypes.entity[C.leg_name(1)].collision_mask.layers
      local all = surface.count_tiles_filtered{position = spot, radius = M.REACH}
      local blocked = surface.count_tiles_filtered{position = spot, radius = M.REACH, collision_mask = mask}
      if (all - blocked) < all * M.FOOTING_SHARE then
        return what
      end
    end
  end
  return nil, spot, dir
end

---Dust where his feet come down, `rings` rings of puffs.
---@param surface LuaSurface
---@param at MapPosition
---@param rings integer
local function dust(surface, at, rings)
  for ring = 1, rings do
    local r = 1.2 * ring
    for i = 0, 15 do
      local v = DIR[i]
      surface.create_trivial_smoke{name = M.DUST, position = {at.x + v[1] * r, at.y + v[2] * r}}
    end
  end
end

---`off` from ground point `at`, as a render target.
---@param at MapPosition
---@param off number[]
---@return MapPosition
local function point(at, off)
  return {x = at.x + off[1], y = at.y + off[2]}
end

---His sheets at his heading, where the airborne body stands, at takeoff's pose. The body itself
---draws as nothing (prototypes/bodies.lua), so these are all of him anyone sees.
---
---POSITION targets, re-aimed every tick, never {entity = airborne}: MEASURED off a graphics-
---benchmark screenshot, a render object targeted at a spider-vehicle is drawn from its TORSO,
---`height` tiles up the screen (body and shadow both came out 1.5 tiles high). Undocumented, so
---nothing leans on it; tick() and land() clean up what an entity target would have taken down
---with a destroyed body.
---@param arc Jamaltron.Arc
---@param color Color?
local function draw(arc, color)
  local e, frame, at = arc.entity, arc.dir * 4, arc.from
  local pose = M.pose(0, arc.peak, arc.dir, arc.lift)
  -- Shadow, then body, then harness: creation order within a layer. The shadow's layer is moot
  -- for the look: draw_as_shadow puts it under everything that stands, walls included, like
  -- every shadow in the game (screenshot).
  arc.shadow = rendering.draw_animation{animation = N.shadow, surface = e.surface,
    target = point(at, pose.shadow), animation_speed = 0, animation_offset = frame,
    render_layer = "lower-object-above-shadow"}
  arc.body = rendering.draw_animation{animation = N.body, surface = e.surface,
    target = point(at, pose.body), animation_speed = 0, animation_offset = frame,
    orientation = pose.pitch, render_layer = "air-object"}
  arc.mask = rendering.draw_animation{animation = N.mask, surface = e.surface,
    target = point(at, pose.mask), animation_speed = 0, animation_offset = frame,
    orientation = pose.pitch, render_layer = "air-object", tint = color}
end

---@param arc Jamaltron.Arc
local function undraw(arc)
  for _, key in ipairs({"shadow", "body", "mask"}) do
    local obj = arc[key]
    if obj and obj.valid then obj.destroy() end
    arc[key] = nil
  end
end

---One tick of flight: the body to its absolute point on the ground path (not a step: positions
---snap to 1/256 tile, and 30 relative steps of 0.3 land 8.906 on, measured), then the drawing
---to the pose over that point. Idempotent for a given tick.
---@param arc Jamaltron.Arc
---@param tick integer
local function fly(arc, tick)
  local u = (tick - arc.start) / (arc.land - arc.start)
  local from, to = arc.from, arc.to
  local at = {x = from.x + (to.x - from.x) * u, y = from.y + (to.y - from.y) * u}
  arc.entity.teleport(at)
  local pose = M.pose(u, arc.peak, arc.dir, arc.lift)
  if arc.body and arc.body.valid then
    arc.body.target = point(at, pose.body)
    arc.body.orientation = pose.pitch
  end
  if arc.mask and arc.mask.valid then
    arc.mask.target = point(at, pose.mask)
    arc.mask.orientation = pose.pitch
  end
  if arc.shadow and arc.shadow.valid then
    arc.shadow.target = point(at, pose.shadow)
  end
end

---Can a foot stand at `p`: ground, and no leg collision there.
---@param surface LuaSurface
---@param leg string
---@param p MapPosition
---@return boolean
local function footing(surface, leg, p)
  return not ground.of(surface.get_tile(p.x, p.y).name) and not surface.entity_prototype_collides(leg, p, false)
end

---A TILE CENTRE near `p` a foot can stand on, or nil. The engine's search is a square, not a
---disc, and not strictly nearest-first (measured: 6 and 7 tiles off at radius 8, a closer free
---tile skipped). Tile centres, not the free search: a foot is ~0.1 tile, so the free search put
---him on a wall's corner (measured, 0.7 tiles from its centre); a tile centre is at least a tile
---off it.
---@param surface LuaSurface
---@param leg string
---@param p MapPosition
---@param radius number
---@return MapPosition?
local function near_footing(surface, leg, p, radius)
  local near = surface.find_non_colliding_position(leg, p, radius, 0.5, true)
  if near and not ground.of(surface.get_tile(near.x, near.y).name) then
    return near
  end
end

---Where he comes down (the header's order): the spot, footing near it, the takeoff, footing near
---that, footing wider round the spot; only when the arc's whole neighbourhood was built over or
---flooded in its 0.5 s, the takeoff unchecked. MEASURED before the takeoff was checked: a silo on
---the spot and a wall on the takeoff landed him inside the wall, deep water on both on water.
---@param arc Jamaltron.Arc
---@return MapPosition
local function landing_spot(arc)
  local surface, spot, from = arc.entity.surface, arc.to, arc.from
  local leg = C.leg_name(1)
  if footing(surface, leg, spot) then return spot end
  local near = near_footing(surface, leg, spot, M.LAND_SEARCH)
  if near then return near end
  if footing(surface, leg, from) then return from end
  near = near_footing(surface, leg, from, M.LAND_SEARCH) or near_footing(surface, leg, spot, 2 * M.LAND_SEARCH)
  if near then return near end
  log("jamaltron jump: no footing near the spot or the takeoff, landing unit " .. arc.entity.unit_number
      .. " at the takeoff anyway")
  return from
end

---breakage's landing, plus what rides onto the body he lands as: the cooldown (re-keyed off the
---airborne unit) and a deconstruction order on a clean landing (the header). nil when the
---landing did not happen.
---@param r Jamaltron.JumpRoot
---@param unit integer the airborne body's
---@param airborne LuaEntity
---@param spot MapPosition
---@param info Jamaltron.JumpLanding
---@param decon LuaForce?
---@return LuaEntity?
local function touchdown(r, unit, airborne, spot, info, decon)
  local landed = breakage.on_landing(airborne, spot, info)
  if not (landed and landed.valid) then return nil end
  r.last[landed.unit_number --[[@as integer]]] = r.last[unit]
  r.last[unit] = nil
  if decon and decon.valid and landed.name == C.name then
    landed.order_deconstruction(decon)
  end
  return landed
end

---Touchdown: the arc leaves storage FIRST (a landing that throws must not land again every
---tick), then the drawing goes, dust and thud, and breakage does the one swap.
---@param r Jamaltron.JumpRoot
---@param unit integer the airborne body's
---@param arc Jamaltron.Arc
---@param tick integer
local function land(r, unit, arc, tick)
  r.arcs[unit] = nil
  undraw(arc)
  local airborne = arc.entity
  local surface = airborne.surface
  local spot = landing_spot(arc)
  airborne.teleport(spot)
  dust(surface, spot, 2)
  surface.play_sound{path = N.thud, position = spot}
  local driver = arc.driver
  local dx, dy = spot.x - arc.from.x, spot.y - arc.from.y
  ---@type Jamaltron.JumpLanding
  local info = {tick = tick, height = arc.peak, distance = math.sqrt(dx * dx + dy * dy),
                driver = (driver and driver.valid) and driver or nil}
  if touchdown(r, unit, airborne, spot, info, arc.decon) or not airborne.valid then
    r.last[unit] = nil                                         -- landed, or lost with the body
    return
  end
  -- The landing swap failed; he is still whole in the airborne body (another mod's listener
  -- killed the new one). Retry in a second, RETRIES times on the arc, then the poll's (header).
  local retries = (arc.retries or 0) + 1
  if retries <= M.RETRIES then
    arc.retries, arc.land, arc.to = retries, tick + 60, spot
    arc.start, arc.from = tick + 59, spot                      -- no arc left to fly: sit still
    r.arcs[unit] = arc
    clock.wake()                      -- a teleport-mode landing runs in try(), off the clock
  else
    airborne.operable = true                                   -- his trunk, while he waits
    r.stranded[unit] = {entity = airborne, info = info, decon = arc.decon}
    log("jamaltron jump: landing failed " .. retries .. " times, unit " .. unit .. " left to the poll")
  end
end

---A jump_refused line with its reason, unless he complained less than REFUSE_GAP ago.
---@param entity LuaEntity
---@param reason string
---@param tick integer
---@return string? said
local function refuse(entity, reason, tick)
  local refused = root().refused
  local unit = entity.unit_number --[[@as integer]]
  local prior = refused[unit]
  if prior and tick - prior < M.REFUSE_GAP then
    return nil
  end
  refused[unit] = tick
  return speech.say(entity, "jump_refused", reason)
end

---Trim the per-body tick tables to bodies that could still read them. Units are never reused,
---so stale entries only cost memory.
---@param r Jamaltron.JumpRoot
---@param tick integer
local function prune(r, tick)
  local cool = cooldown_ticks()
  for unit, at in pairs(r.last) do
    if tick - at >= cool and r.arcs[unit] == nil then r.last[unit] = nil end
  end
  for unit, at in pairs(r.refused) do
    if tick - at >= M.REFUSE_GAP then r.refused[unit] = nil end
  end
end

---Jump, if he can. The key's handler, the harness and other mods all come in here.
---@param entity LuaEntity
---@param player (LuaPlayer|LuaEntity)? who pressed it (see check()); nil when a script asks for
---  the driver
---@return boolean jumped
---@return string? why a jump_refused reason, or a silent one: not_vehicle, disabled, frozen,
---  busy, failed
---@return string? said the row he said about it, if any
function M.try(entity, player)
  if not (entity and entity.valid and entity.name == C.name and entity.unit_number) then
    return false, "not_vehicle"
  end
  if not settings.startup["jamaltron-jump-enabled"].value then
    return false, "disabled"
  end
  if entity.disabled_by_script or not entity.operable then
    return false, "frozen"                               -- another mod's hold (the header)
  end
  if swap.swapping(entity) then
    return false, "busy"
  end
  local tick = game.tick
  local r = root()
  prune(r, tick)
  local reason, spot, dir = M.check(entity, player, tick)
  if reason or not (spot and dir) then
    return false, reason, refuse(entity, reason --[[@as string]], tick)
  end

  local from = entity.position
  local driver = entity.get_driver()
  local lift = prototypes.entity[C.name].height or 0
  local color = entity.color
  -- The airborne body is not-deconstructable (D.1), so the swap cannot carry the mark across.
  local decon = entity.to_be_deconstructed() and entity.force --[[@as LuaForce]] or nil
  -- Takeoff drops the queue AND the follow (E.6): nothing may walk him off the landing.
  local airborne = swap.replace(entity, C.airborne, {reason = "takeoff", autopilot = false})
  if not airborne then
    return false, "failed"
  end
  airborne.torso_orientation = dir / 16          -- the landing swap carries it: he lands facing it
  local unit = airborne.unit_number --[[@as integer]]
  local peak, ticks = M.shape(distance())
  ---@type Jamaltron.Arc
  local arc = {entity = airborne, from = from, to = spot, start = tick, land = tick + ticks,
               peak = peak, dir = dir, lift = lift, driver = driver, decon = decon}
  r.last[unit] = tick
  dust(airborne.surface, from, 1)
  local said = speech.say(airborne, "jump")
  if r.mode == "teleport" then
    arc.land = tick
    land(r, unit, arc, tick)
    return true, nil, said
  end
  draw(arc, color)
  r.arcs[unit] = arc
  clock.wake()
  return true, nil, said
end

---Is an arc in the air? A read of storage, never a write: on_load calls it through the clock.
---@return boolean
function M.pending()
  local r = storage.jamaltron and storage.jamaltron.jump
  return r ~= nil and next(r.arcs) ~= nil
end

---The clock's per-tick half: every arc flies a tick, lands on its tick, or is dropped when its
---body is gone (destroyed mid-air: the drawing went with it, the rest goes here). The due list
---is taken first: a landing raises events, and a listener that jumps him again must not grow the
---table under this loop.
---@param tick integer
function M.tick(tick)
  local r = root()
  local units = {}
  for unit in pairs(r.arcs) do units[#units + 1] = unit end
  for _, unit in ipairs(units) do
    local arc = r.arcs[unit]
    if arc then
      if not arc.entity.valid then
        r.arcs[unit] = nil
        r.last[unit] = nil
        undraw(arc)
      elseif tick >= arc.land then
        land(r, unit, arc, tick)
      elseif tick > arc.start then
        fly(arc, tick)
      end
    end
  end
end

---The 60-tick slow clock: every stranded body retries its landing where it sits (no dust, no
---thud: he has been sitting there a while). The list is taken first: a landing raises events.
function M.poll()
  local r = storage.jamaltron and storage.jamaltron.jump
  local stranded = r and r.stranded
  if not (stranded and next(stranded)) then return end
  local units = {}
  for unit in pairs(stranded) do units[#units + 1] = unit end
  for _, unit in ipairs(units) do
    local st = stranded[unit]
    if st and not st.entity.valid then
      stranded[unit] = nil
    elseif st and (touchdown(r, unit, st.entity, st.entity.position, st.info, st.decon)
                   or not st.entity.valid) then
      stranded[unit] = nil
      r.last[unit] = nil
    end
  end
end

---An airborne body with neither an arc nor a stranded entry is stranded now and lands clean where
---it sits on the next poll (height 0 tells breakage.on_landing it never flew). Callers: the
---harness's `strand` (the playtest's /jamaltron-swap airborne, which swaps with no arc) and
---adopt_all. Idempotent; false for anything not airborne.
---@param entity LuaEntity
---@return boolean stranded
function M.adopt(entity)
  if not (entity and entity.valid and entity.name == C.airborne and entity.unit_number) then
    return false
  end
  local r = root()
  local unit = entity.unit_number --[[@as integer]]
  if r.arcs[unit] ~= nil then return false end        -- flying: the arc lands him
  if r.stranded[unit] == nil then
    entity.operable = true
    r.stranded[unit] = {entity = entity, info = {tick = game.tick, height = 0, distance = 0}}
  end
  return true
end

---on_configuration_changed: every airborne body on the map with no arc is stranded (adopt), and
---any arc sheet with no arc left to own it is taken down. No path in this code causes either; a
---save from before the poll existed or a migration that rebuilt storage.jump while sheets were
---up does (measured: the three stayed drawn for good, adopt landing him did not touch them).
---Speech notes are text and time out by themselves, so it sweeps only animations. Idempotent.
function M.adopt_all()
  if prototypes.entity[C.airborne] == nil then return end
  local r = root()
  for _, surface in pairs(game.surfaces) do
    for _, entity in pairs(surface.find_entities_filtered{name = C.airborne}) do
      M.adopt(entity)
    end
  end
  local drawn = {}
  for _, arc in pairs(r.arcs) do
    for _, key in ipairs({"shadow", "body", "mask"}) do
      local obj = arc[key]
      if obj and obj.valid then drawn[obj.id] = true end
    end
  end
  for _, obj in pairs(rendering.get_all_objects(script.mod_name)) do
    if obj.type == "animation" and not drawn[obj.id] then obj.destroy() end
  end
end

---on_object_destroyed: a gone body's cooldown, refusal and stranded entries. NEVER an arc: only
---tick() ends one (clock.lua), so an arc whose body died is still tick()'s to drop.
---@param unit integer
function M.forget(unit)
  local r = storage.jamaltron and storage.jamaltron.jump
  if r == nil then return end
  r.last[unit], r.refused[unit] = nil, nil
  if r.stranded then r.stranded[unit] = nil end
end

---jump_mode: "arc" | "teleport" map-wide, or nil to read it.
---@param mode string?
---@return string
function M.mode(mode)
  local r = root()
  if mode == "arc" or mode == "teleport" then
    r.mode = mode
  elseif mode ~= nil then
    error("jamaltron jump_mode: 'arc' or 'teleport', got '" .. tostring(mode) .. "'")
  end
  return r.mode
end

---HARNESS ONLY: counts to assert on, the units the per-body tables are keyed by (a harness can
---ask the game which are still alive), and one arc's pose when given its airborne body.
---@param entity LuaEntity?
---@return table
function M.state(entity)
  local r = storage.jamaltron and storage.jamaltron.jump
  local out = {arcs = 0, drawn = 0, last = 0, refused = 0, stranded = 0, pending = M.pending(),
               mode = r and r.mode or "arc", units = {}}
  if r == nil then return out end
  for _, arc in pairs(r.arcs) do
    out.arcs = out.arcs + 1
    for _, key in ipairs({"shadow", "body", "mask"}) do
      if arc[key] and arc[key].valid then out.drawn = out.drawn + 1 end
    end
  end
  for unit in pairs(r.last) do out.last, out.units[#out.units + 1] = out.last + 1, unit end
  for unit in pairs(r.refused) do out.refused, out.units[#out.units + 1] = out.refused + 1, unit end
  for _ in pairs(r.stranded or {}) do out.stranded = out.stranded + 1 end
  local arc = entity and entity.valid and entity.unit_number and r.arcs[entity.unit_number]
  if arc then
    local at = arc.entity.position
    ---Where a render object is drawn, as an offset from the body's ground position.
    local function offset(obj)
      if not (obj and obj.valid) then return nil end
      local p = obj.target.position
      return p and {x = p.x - at.x, y = p.y - at.y}
    end
    out.arc = {from = arc.from, to = arc.to, start = arc.start, land = arc.land, peak = arc.peak,
               dir = arc.dir, body = offset(arc.body), shadow = offset(arc.shadow),
               pitch = arc.body and arc.body.valid and arc.body.orientation or nil,
               frame = arc.body and arc.body.valid and arc.body.animation_offset or nil}
  end
  return out
end

---HARNESS ONLY: re-fly every arc at `tick` (the clock's writes for this tick, again) so a
---profiler can time the per-tick cost of N arcs without advancing any of them.
---@param tick integer
function M.refly(tick)
  local r = root()
  for _, arc in pairs(r.arcs) do
    if arc.entity.valid and tick > arc.start and tick < arc.land then fly(arc, tick) end
  end
end

return M
