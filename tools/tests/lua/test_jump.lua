-- The jump (PLAN E.1-E.3, E.2.6): the refusal ORDER, the arc arithmetic, and the flight's
-- bookkeeping, under plain lua with FAKE entities and a fake game. The real scripts/jump.lua,
-- speech.lua, ground.lua, picker and catalog; swap, clock and breakage are fakes, so a takeoff
-- and a landing are counted, not performed (tools/harness/jamaltron-jump-harness does them for
-- real).
--
--   lua tools/tests/lua/test_jump.lua <repo root>
--
-- Run by tools/tests/test_speech_lua.py, in test_pick.lua's harness shape; Lua 5.2 / 5.4+ / luajit.

local root = arg[1] or "."
local MOD_PATH = root .. "/mod/jamaltron/?.lua;"
package.path = MOD_PATH .. package.path

local C = require("prototypes.shared")
local N = require("prototypes.jump")
local art = require("prototypes.sprites_generated")

defines = {
  direction = {north = 0, northnortheast = 1, northeast = 2, eastnortheast = 3, east = 4,
    eastsoutheast = 5, southeast = 6, southsoutheast = 7, south = 8, southsouthwest = 9,
    southwest = 10, westsouthwest = 11, west = 12, westnorthwest = 13, northwest = 14,
    northnorthwest = 15},
  gui_type = {none = 0},
}

local function tile(layers, fluid)
  local set = {}
  for _, name in ipairs(layers) do set[name] = true end
  return {collision_mask = {layers = set}, fluid = fluid and {name = fluid} or nil}
end
prototypes = {
  entity = {[C.leg_name(1)] = {collision_mask = {layers = {player = true, rail = true}}},
            [C.name] = {height = 1.5}},
  tile = {
    ["grass-1"] = tile({"ground_tile"}),
    deepwater = tile({"water_tile", "resource", "item", "player", "doodad"}, "water"),
    lava = tile({"water_tile", "player", "rail"}, "lava"),
    ["out-of-map"] = tile({"ground_tile", "player", "rail", "item"}),
  },
}

-- FAKES -----------------------------------------------------------------------------------
local calls                                     -- what the fakes were asked to do, by kind
local next_unit = 100
local function count(kind) return #(calls[kind] or {}) end
local function note(kind, v)
  calls[kind] = calls[kind] or {}
  calls[kind][#calls[kind] + 1] = v
  return v
end

---Every render object drawn since reset(), for rendering.get_all_objects.
local drawn_objects = {}
---A render object: dot-called methods, as the engine's are, an id and a type.
local function render_object(params, kind)
  local o = {valid = true, target = params.target, orientation = params.orientation,
             animation = params.animation, animation_offset = params.animation_offset,
             id = #drawn_objects + 1, type = kind}
  o.destroy = function() o.valid = false end
  drawn_objects[#drawn_objects + 1] = o
  return o
end

---A surface whose ground is `ground(x, y) -> tile name` (grass by default); `blocked(x, y)` says
---where a foot collides; `land_share` what count_tiles_filtered reports standable; `near` what
---find_non_colliding_position answers - a position, or fn(center, radius) -> position?.
local function surface(opts)
  opts = opts or {}
  local s = {platform = opts.platform, name = "nauvis"}
  s.get_tile = function(x, y)
    note("tile", true)
    return {name = (opts.ground and opts.ground(x, y)) or "grass-1"}
  end
  s.entity_prototype_collides = function(name, pos)
    assert(name == C.leg_name(1), "the LEG decides, never the body: " .. tostring(name))
    return opts.blocked ~= nil and opts.blocked(pos.x, pos.y) == true
  end
  s.count_tiles_filtered = function(f)
    note("count", f)
    if f.collision_mask then return math.floor(700 * (1 - (opts.land_share or 1))) end
    return 700
  end
  s.find_non_colliding_position = function(name, center, radius)
    note("near", {name = name, center = center, radius = radius})
    if type(opts.near) == "function" then return opts.near(center, radius) end
    return opts.near
  end
  s.create_trivial_smoke = function(p) note("smoke", p) end
  s.play_sound = function(p) note("sound", p) end
  s.create_entity = function(p)   -- speech bubbles
    return {valid = true, name = p.name, destroy = function() end}
  end
  return s
end

local function character(dir, player)
  return {object_name = "LuaEntity", valid = true, player = player,
          walking_state = {walking = dir ~= nil, direction = dir or 0}}
end

local FORCE = {valid = true, name = "player"}

---A driven jamaltron at (0.5, 0.5) facing east, on grass. `frozen` / `locked` stand for another
---mod's disabled_by_script / operable = false; `decon` a deconstruction mark by FORCE.
local function shark(opts)
  opts = opts or {}
  next_unit = next_unit + 1
  local e = {name = opts.name or C.name, valid = true, unit_number = next_unit,
             position = opts.position or {x = 0.5, y = 0.5}, torso_orientation = opts.torso or 0.25,
             autopilot_destination = opts.dest, color = {r = 1, g = 0.5, b = 0, a = 0.5},
             surface = opts.surface or surface(), driver = opts.driver, passenger = opts.passenger,
             force = FORCE, disabled_by_script = opts.frozen == true, operable = opts.locked ~= true,
             decon = opts.decon and FORCE or nil}
  e.to_be_deconstructed = function() return e.decon ~= nil end
  e.order_deconstruction = function(force)
    note("decon", {unit = e.unit_number, force = force})
    e.decon = force
    return true
  end
  if opts.driven ~= false and e.driver == nil and not opts.no_driver then
    e.driver = character(opts.hold)
  end
  e.get_driver = function() return e.driver end
  e.get_passenger = function() return e.passenger end
  e.get_health_ratio = function() return 1 end
  e.teleport = function(p)
    e.position = {x = p[1] or p.x, y = p[2] or p.y}
    note("teleport", {unit = e.unit_number, x = e.position.x, y = e.position.y})
    return true
  end
  return e
end

-- swap, clock and breakage: counted, never performed.
local fake_swap = {swapping_units = {}, fail = nil}
function fake_swap.swapping(e) return fake_swap.swapping_units[e.unit_number] == true end
function fake_swap.replace(old, name, opts)
  local rec = note("swap", {from = old.name, to = name, opts = opts})
  if fake_swap.fail then return nil, fake_swap.fail end
  local new = shark({name = name, position = opts.position or old.position, surface = old.surface,
                     torso = old.torso_orientation, driven = false})
  new.driver = old.driver
  if name == C.airborne then new.operable = false end        -- M.BODY's, as the real swap writes
  old.valid = false
  rec.new = new
  return new, "ok"
end
local fake_clock = {}
function fake_clock.wake() note("wake", true) end
local fake_breakage = {result = "held"}
function fake_breakage.on_landing(airborne, spot, info)
  note("landing", {airborne = airborne, spot = spot, info = info})
  if fake_breakage.result == "throw" then error("a listener threw") end
  if fake_breakage.result == "failed" then return nil, "failed" end
  if fake_breakage.result == "lost" then
    airborne.valid = false
    return nil, "lost"
  end
  local body = fake_swap.replace(airborne, fake_breakage.result == "broke" and C.beached or C.name,
                                 {position = spot})
  return body, fake_breakage.result
end

local said
local speech
local function reset(opts)
  opts = opts or {}
  storage = {}
  if speech then speech.set_debug(true) end         -- say() logs each row, which `said` reads
  calls, said = {}, {}
  game = {tick = 1000, connected_players = {}, print = function() end}
  settings = {
    startup = {["jamaltron-jump-enabled"] = {value = opts.disabled ~= true}},
    global = {["jamaltron-verbosity"] = {value = "unbearable"},
              ["jamaltron-speech-cooldown"] = {value = 10},
              ["jamaltron-jump-cooldown"] = {value = opts.cooldown or 5},
              ["jamaltron-jump-distance"] = {value = opts.distance or 8}}}
  script = {register_on_object_destroyed = function() end, mod_name = "jamaltron"}
  drawn_objects = {}
  rendering = {
    draw_text = function(p) return render_object(p, "text") end,
    draw_animation = function(p) return note("draw", render_object(p, "animation")) end,
    get_all_objects = function(mod)
      assert(mod == "jamaltron", "his own objects only: " .. tostring(mod))
      local out = {}
      for _, o in ipairs(drawn_objects) do if o.valid then out[#out + 1] = o end end
      return out
    end,
  }
  log = function(msg)
    local unit, id = msg:match("^jamaltron speech (%d+) (%S+)$")
    if id then said[#said + 1] = {tick = game.tick, id = id, unit = tonumber(unit)} end
    if not id then note("log", msg) end
  end
  fake_swap.fail, fake_breakage.result = nil, "held"
  math.randomseed(11)
end
reset()

package.loaded["scripts.swap"] = fake_swap
package.loaded["scripts.clock"] = fake_clock
package.loaded["scripts.breakage"] = fake_breakage
speech = require("scripts.speech")
reset()
local jump = require("scripts.jump")
local lines = require("scripts.lines")
local SUB = {}
for _, pool in pairs(lines.pools) do
  for _, row in ipairs(pool.rows) do SUB[row.id] = row.sub or "-" end
end

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end
local function near(a, b, eps) return math.abs(a - b) <= (eps or 1e-9) end

-- THE ARC ARITHMETIC ------------------------------------------------------------------------

test("shape: the documented numbers - 8 tiles is 3.0 up for 30 ticks, 3 is 1.5/21, 20 is 7.5/47", function()
  local p, t = jump.shape(8)
  assert(p == 3.0 and t == 30, p .. " " .. t)
  p, t = jump.shape(3)
  assert(p == 1.5 and t == 21, p .. " " .. t)
  p, t = jump.shape(20)
  assert(p == 7.5 and t == 47, p .. " " .. t)
end)

test("shape: one gravity for every distance (8H/T^2 within the tick rounding)", function()
  local p8, t8 = jump.shape(8)
  local g = 8 * p8 / (t8 * t8)
  for d = 3, 20 do
    local p, t = jump.shape(d)
    local gd = 8 * p / (t * t)
    assert(math.abs(gd - g) / g < 0.1, d .. ": " .. gd .. " vs " .. g)
  end
end)

test("pose: takeoff and touchdown sit on the engine's standing pose (lift up, lift east)", function()
  local bs, ss = art.sprites.body.shift, art.sprites.shadow.shift
  for _, u in ipairs({0, 1}) do
    local p = jump.pose(u, 3, 4, 1.5)
    assert(near(p.h, 0), u .. " h " .. p.h)
    assert(near(p.body[1], bs[1]) and near(p.body[2], bs[2] - 1.5), u .. " body")
    assert(near(p.shadow[1], ss[1] + 1.5) and near(p.shadow[2], ss[2]), u .. " shadow")
  end
end)

test("pose: at the peak the body rises h*0.7071 and the shadow runs h east (45-degree sun)", function()
  local bs, ss = art.sprites.body.shift, art.sprites.shadow.shift
  local p = jump.pose(0.5, 3, 4, 1.5)
  assert(near(p.h, 3), p.h)
  assert(near(p.body[2], bs[2] - 1.5 - 3 * 0.7071067811865), p.body[2])
  assert(near(p.shadow[1], ss[1] + 1.5 + 3), p.shadow[1])
  assert(near(p.shadow[2], ss[2]), "the shadow never lifts")
end)

test("pose: pitch follows the velocity - nose up, level, nose down - east-west only", function()
  local east0, east_mid, east1 = jump.pose(0, 3, 4, 1.5), jump.pose(0.5, 3, 4, 1.5), jump.pose(1, 3, 4, 1.5)
  assert(east0.pitch < 0 and near(east_mid.pitch, 0) and east1.pitch > 0,
         "east: CCW lifts a nose that points right")
  assert(near(east0.pitch, -jump.PITCH), east0.pitch)
  local west0 = jump.pose(0, 3, 12, 1.5)
  assert(west0.pitch > 0, "west: CW lifts a nose that points left")
  for _, dir in ipairs({0, 8}) do
    for _, u in ipairs({0, 0.25, 1}) do
      assert(near(jump.pose(u, 3, dir, 1.5).pitch, 0), "no roll flying north/south")
    end
  end
end)

test("pose: the harness mask turns WITH the body - fixed distance, Taylor within 1e-6 of trig", function()
  local r = art.sprites.body_mask.shift[2] - art.sprites.body.shift[2]
  for _, dir in ipairs({2, 4, 6, 12}) do
    for u = 0, 1, 0.125 do
      local p = jump.pose(u, 3, dir, 1.5)
      local dx, dy = p.mask[1] - p.body[1], p.mask[2] - p.body[2]
      local a = p.pitch * 2 * math.pi
      assert(near(dx, -r * math.sin(a), 1e-6) and near(dy, r * math.cos(a), 1e-6),
             dir .. "@" .. u .. ": " .. dx .. "," .. dy)
    end
  end
end)

test("heading: a held direction wins over a torso still turning (0.005 turns/tick, measured)", function()
  local e = shark({torso = 0.10, hold = defines.direction.south})
  assert(jump.heading(e, e.get_driver()) == defines.direction.south)
end)

test("heading: standing still, the torso snaps to the nearest 16th, wrapping at north", function()
  local cases = {{0.25, 4}, {0.99, 0}, {0.0312, 0}, {0.0313, 1}, {0.5, 8}, {0.72, 12}}
  for _, c in ipairs(cases) do
    local e = shark({torso = c[1]})
    local got = jump.heading(e, e.get_driver())
    assert(got == c[2], c[1] .. " -> " .. got .. ", want " .. c[2])
  end
end)

-- THE REFUSAL ORDER -------------------------------------------------------------------------

test("check: the order is the header's - no_driver, autopilot, platform, cooldown, ground, blocked", function()
  reset()
  local P1, P2 = {object_name = "LuaPlayer", valid = true}, {object_name = "LuaPlayer", valid = true}
  local function build(stage)
    local s = surface({
      platform = stage <= 3 and {} or nil,
      ground = function(x, y)
        if math.floor(x) == 8 and math.floor(y) == 0 then
          if stage <= 5 then return "deepwater" end
          if stage == 6 then return "lava" end
          if stage == 7 then return "out-of-map" end
        end
      end,
      blocked = function(x) return stage <= 8 and math.floor(x) == 8 end})
    local e = shark({surface = s, dest = stage <= 2 and {x = 50, y = 0} or nil, torso = 0.25})
    if stage == 0 then e.driver = nil end
    if stage == 1 then e.driver = character(nil, P1) end            -- P2 presses: a passenger
    if stage <= 4 then storage.jamaltron = {jump = {last = {[e.unit_number] = game.tick - 10},
                                                    arcs = {}, refused = {}, mode = "arc"}} end
    return e
  end
  local want = {[0] = "no_driver", "no_driver", "autopilot", "platform", "cooldown", "water", "lava",
                "void", "blocked"}
  for stage = 0, 8 do
    storage = {}
    local e = build(stage)
    local reason = jump.check(e, stage == 1 and P2 or nil, game.tick)
    assert(reason == want[stage], "stage " .. stage .. ": " .. tostring(reason) .. ", want " .. want[stage])
  end
  storage = {}
  local reason, spot, dir = jump.check(build(9), nil, game.tick)
  assert(reason == nil and spot.x == 8.5 and spot.y == 0.5 and dir == 4, tostring(reason))
end)

test("check: a remote driver (a LuaPlayer not sitting in him) is no_driver, a seated one is not", function()
  reset()
  local e = shark({no_driver = true})
  e.driver = {object_name = "LuaPlayer", valid = true, physical_vehicle = nil,
              walking_state = {walking = false, direction = 0}}
  assert(jump.check(e, e.driver, game.tick) == "no_driver")
  e.driver.physical_vehicle = e
  assert(jump.check(e, e.driver, game.tick) == nil)
end)

test("check: the presser must be the driver - the driver's own character passes", function()
  reset()
  local P1 = {object_name = "LuaPlayer", valid = true}
  local e = shark({driver = character(nil, P1)})
  assert(jump.check(e, P1, game.tick) == nil)
end)

test("check: a CHARACTER presser (the harness's stand-in for a player) - driver passes, passenger no_driver", function()
  reset()
  local driver, passenger = character(nil), character(nil)
  local e = shark({driver = driver, passenger = passenger})
  assert(jump.check(e, driver, game.tick) == nil)
  assert(jump.check(e, passenger, game.tick) == "no_driver")
end)

test("check: cooldown is per body and runs out at jamaltron-jump-cooldown", function()
  reset()
  local e = shark()
  storage.jamaltron = {jump = {last = {[e.unit_number] = game.tick - 299}, arcs = {}, refused = {},
                               mode = "arc"}}
  assert(jump.check(e, nil, game.tick) == "cooldown")
  game.tick = game.tick + 1
  assert(jump.check(e, nil, game.tick) == nil)
  assert(jump.check(shark(), nil, game.tick) == nil, "another body is not on his cooldown")
end)

test("check: cooldown 0 (the shipped default) never refuses - not even the tick he lands", function()
  reset{cooldown = 0}
  local e = shark()
  storage.jamaltron = {jump = {last = {[e.unit_number] = game.tick}, arcs = {}, refused = {},
                               mode = "arc"}}
  assert(jump.check(e, nil, game.tick) == nil)
end)

test("check: reads, never writes - storage is exactly as it was", function()
  reset()
  storage = {}
  jump.check(shark(), nil, game.tick)
  assert(next(storage) == nil, "check created storage")
end)

test("check: the default 8-tile jump never counts tiles, even over 7 tiles of water", function()
  reset()
  local s = surface({ground = function(x) if x > 1 and x < 8 then return "deepwater" end end})
  calls = {}
  assert(jump.check(shark({surface = s}), nil, game.tick) == nil)
  assert(count("count") == 0, "counted " .. count("count"))
  assert(count("tile") == 1, "the landing tile and nothing else: read " .. count("tile"))
end)

test("check: past STRADDLE a wide lake to an islet is refused as the water, a far bank is not", function()
  reset({distance = 20})
  local lake = function(x) if x > 2 and x < 19 then return "deepwater" end end
  local islet = surface({ground = lake, land_share = 0.05})
  assert(jump.check(shark({surface = islet}), nil, game.tick) == "water")
  local bank = surface({ground = lake, land_share = 0.5})
  assert(jump.check(shark({surface = bank}), nil, game.tick) == nil)
  local narrow = surface({ground = function(x) if x > 2 and x < 12 then return "deepwater" end end,
                          land_share = 0.05})
  calls = {}
  assert(jump.check(shark({surface = narrow}), nil, game.tick) == nil,
         "9 tiles of water is walkable back: no count needed")
  assert(count("count") == 0)
end)

-- TRY: THE ENTRY POINT ----------------------------------------------------------------------

test("try: a refusal says jump_refused on its reason's side of the split", function()
  reset()
  local s = surface({ground = function(x) if math.floor(x) == 8 then return "deepwater" end end})
  local e = shark({surface = s})
  local ok, why, row = jump.try(e, nil)
  assert(ok == false and why == "water" and row ~= nil, tostring(why) .. " " .. tostring(row))
  assert(row:match("^jump_refused%.") and (SUB[row] == "water" or SUB[row] == "any"), row .. " " .. SUB[row])
  assert(count("swap") == 0, "nothing moves on a refusal")
end)

test("try: a mashed key is one complaint - silent for REFUSE_GAP, then speaks again", function()
  reset()
  local e = shark({dest = {x = 9, y = 9}})
  local _, why, row = jump.try(e, nil)
  assert(why == "autopilot" and row, "first")
  game.tick = game.tick + jump.REFUSE_GAP - 1
  _, why, row = jump.try(e, nil)
  assert(why == "autopilot" and row == nil, "inside the gap: " .. tostring(row))
  game.tick = game.tick + 400                     -- clear of the ambient cooldown too
  _, why, row = jump.try(e, nil)
  assert(why == "autopilot" and row ~= nil, "after the gap")
end)

test("try: silent refusals - not the vehicle, the setting off, a swap in progress", function()
  reset()
  local ok, why = jump.try(shark({name = C.beached}), nil)
  assert(not ok and why == "not_vehicle")
  reset({disabled = true})
  ok, why = jump.try(shark(), nil)
  assert(not ok and why == "disabled")
  reset()
  local e = shark()
  fake_swap.swapping_units[e.unit_number] = true
  ok, why = jump.try(e, nil)
  fake_swap.swapping_units[e.unit_number] = nil
  assert(not ok and why == "busy")
  assert(#said == 0, "said " .. #said)
end)

test("try: another mod's hold - disabled_by_script or operable = false - is frozen: silent, nothing moves", function()
  for _, opts in ipairs({{frozen = true}, {locked = true}, {frozen = true, locked = true}}) do
    reset()
    local e = shark(opts)
    local ok, why, row = jump.try(e, nil)
    assert(not ok and why == "frozen" and row == nil, tostring(why))
    assert(count("swap") == 0 and #said == 0 and e.valid, "a frozen vehicle took off or spoke")
  end
end)

---Take off east from (0.5, 0.5) and land; returns the body he landed as and every swap made.
local function jump_and_land(opts)
  local e = shark(opts)
  assert(jump.try(e, nil), "refused")
  local _, T = jump.shape(8)
  game.tick = game.tick + T
  jump.tick(game.tick)
  return calls.swap[#calls.swap].new
end

test("a deconstruction mark rides a clean landing, re-ordered by the same force; none is invented", function()
  reset()
  local landed = jump_and_land({decon = true})
  assert(landed.name == C.name and count("decon") == 1 and calls.decon[1].unit == landed.unit_number
         and calls.decon[1].force == FORCE, "the mark came down with him")
  reset()
  jump_and_land()
  assert(count("decon") == 0, "an unmarked jamaltron landed marked")
  reset()
  fake_breakage.result = "broke"
  landed = jump_and_land({decon = true})
  assert(landed.name == C.beached and count("decon") == 0, "a break keeps no mark: beached is not-deconstructable")
end)

---Take off east from (0.5, 0.5) and return the airborne body.
local function takeoff(opts)
  local e = shark(opts)
  local ok, why = jump.try(e, nil)
  assert(ok, "refused: " .. tostring(why))
  local swaps = calls.swap
  return e, swaps[#swaps].new, swaps
end

test("try: takeoff is ONE swap into the airborne body, queue dropped, jump line, drawn, clock woken", function()
  reset()
  local _, body, swaps = takeoff()
  assert(#swaps == 1 and swaps[1].to == C.airborne and swaps[1].opts.autopilot == false
         and swaps[1].opts.reason == "takeoff")
  assert(body.torso_orientation == 4 / 16, "he flies facing east: " .. body.torso_orientation)
  assert(#said == 1 and said[1].id:match("^jump%.") and said[1].unit == body.unit_number,
         "the jump line, on the body the swap returned")
  assert(count("draw") == 3 and count("wake") == 1)
  local frames = {}
  for _, o in ipairs(calls.draw) do frames[o.animation] = o.animation_offset end
  assert(frames[N.body] == 16 and frames[N.mask] == 16 and frames[N.shadow] == 16,
         "east is frame 16 on all three")
  assert(jump.pending(), "pending while in the air")
end)

test("tick: flies on absolute points, lands exactly on the spot at T, hands breakage the landing", function()
  reset()
  local e, body = takeoff()
  local t0, from = game.tick, {x = 0.5, y = 0.5}
  local _, T = jump.shape(8)
  for t = t0 + 1, t0 + T - 1 do
    game.tick = t
    jump.tick(t)
    local u = (t - t0) / T
    assert(near(body.position.x, from.x + 8 * u, 1e-9) and near(body.position.y, 0.5, 1e-9),
           "t+" .. (t - t0) .. " at " .. body.position.x)
  end
  local peak_body = nil
  for _, o in ipairs(calls.draw) do if o.animation == N.body then peak_body = o end end
  assert(peak_body.valid, "drawn until touchdown")
  game.tick = t0 + T
  jump.tick(game.tick)
  assert(count("landing") == 1, "breakage asked once")
  local l = calls.landing[1]
  assert(l.airborne == body and l.spot.x == 8.5 and l.spot.y == 0.5, "the planned spot")
  assert(near(l.info.distance, 8) and l.info.height == 3 and l.info.tick == t0 + T)
  assert(body.position.x == 8.5, "teleported onto the spot before the swap")
  for _, o in ipairs(calls.draw) do assert(not o.valid, "every render object destroyed") end
  assert(count("sound") == 1 and count("smoke") > 0, "thud and dust")
  assert(not jump.pending(), "nothing left in the air")
  assert(e.valid == false)
end)

test("fly: the drawing is aimed at POSITIONS over the path point - an entity target draws from the torso", function()
  reset()
  takeoff()
  local t0 = game.tick
  game.tick = t0 + 15                                 -- u = 0.5
  jump.tick(game.tick)
  local want = jump.pose(0.5, 3, 4, 1.5)
  local by = {}
  for _, o in ipairs(calls.draw) do by[o.animation] = o end
  for name, off in pairs({[N.body] = want.body, [N.mask] = want.mask, [N.shadow] = want.shadow}) do
    local t = by[name].target
    assert(t.entity == nil and t.x ~= nil, name .. ": not a position target")
    assert(near(t.x, 4.5 + off[1], 1e-9) and near(t.y, 0.5 + off[2], 1e-9), name .. " at " .. t.x .. "," .. t.y)
  end
  assert(near(by[N.body].orientation, 0) and near(by[N.mask].orientation, 0), "level at the peak")
end)

test("tick: the cooldown rides to the body he landed as", function()
  reset()
  local _, _, _ = takeoff()
  local t0 = game.tick
  local _, T = jump.shape(8)
  game.tick = t0 + T
  jump.tick(game.tick)
  local landed = calls.swap[#calls.swap].new
  local last = storage.jamaltron.jump.last
  local n = 0
  for _ in pairs(last) do n = n + 1 end
  assert(n == 1 and last[landed.unit_number] == t0, "one entry, the takeoff tick, on the landed unit")
end)

test("tick: a body destroyed mid-air drops its arc and its drawing, and the clock goes idle", function()
  reset()
  local _, body = takeoff()
  game.tick = game.tick + 5
  jump.tick(game.tick)
  body.valid = false
  game.tick = game.tick + 1
  jump.tick(game.tick)
  assert(not jump.pending())
  for _, o in ipairs(calls.draw) do assert(not o.valid) end
  assert(count("landing") == 0)
  assert(next(storage.jamaltron.jump.last) == nil, "no cooldown left for a body that is gone")
end)

test("tick: a spot built over mid-arc lands on the nearest footing, else back at takeoff", function()
  reset()
  local wall = false
  local s = surface({blocked = function(x) return wall and math.floor(x) == 8 end, near = {x = 10.5, y = 0.5}})
  takeoff({surface = s})
  wall = true
  local _, T = jump.shape(8)
  game.tick = game.tick + T
  jump.tick(game.tick)
  assert(calls.landing[1].spot.x == 10.5, "the nearest footing")
  reset()
  wall = false
  s = surface({blocked = function(x) return wall and math.floor(x) == 8 end, near = nil})
  takeoff({surface = s})
  wall = true
  game.tick = game.tick + T
  jump.tick(game.tick)
  assert(calls.landing[1].spot.x == 0.5 and calls.landing[1].spot.y == 0.5, "back where he took off")
end)

test("landing_spot: the takeoff is checked too - footing near it, then wider round the spot, then logged", function()
  local SPOT, FROM = {x = 8.5, y = 0.5}, {x = 0.5, y = 0.5}
  local function run(opts)
    reset()
    local walls = false
    local s = surface({blocked = function(x, y) return walls and opts.blocked(x, y) end, near = opts.near})
    takeoff({surface = s})
    walls = true
    local _, T = jump.shape(8)
    game.tick = game.tick + T
    jump.tick(game.tick)
    return calls.landing[1].spot
  end
  local function at(p, q) return p.x == q.x and p.y == q.y end
  -- the spot built over, nothing free near it, the takeoff free: back where he took off
  local got = run{blocked = function(x) return math.floor(x) == 8 end, near = function() return nil end}
  assert(at(got, FROM), "the takeoff")
  -- the spot AND the takeoff built over: the nearest footing to the takeoff, never the wall
  got = run{blocked = function(x) return math.floor(x) == 8 or math.floor(x) == 0 end,
            near = function(c) if at(c, FROM) then return {x = -1.5, y = 0.5} end end}
  assert(at(got, {x = -1.5, y = 0.5}), "footing near the takeoff, got " .. got.x)
  -- nothing near either within LAND_SEARCH: wider round the spot
  got = run{blocked = function(x) return math.floor(x) == 8 or math.floor(x) == 0 end,
            near = function(c, r) if at(c, SPOT) and r > jump.LAND_SEARCH then return {x = 15.5, y = 0.5} end end}
  assert(at(got, {x = 15.5, y = 0.5}), "wider round the spot, got " .. got.x)
  -- nothing anywhere: the takeoff unchecked, and said so in the log
  got = run{blocked = function(x) return math.floor(x) == 8 or math.floor(x) == 0 end,
            near = function() return nil end}
  local logged = false
  for _, msg in ipairs(calls.log or {}) do logged = logged or msg:find("no footing", 1, true) ~= nil end
  assert(at(got, FROM) and logged, "the takeoff, logged")
  -- water on the takeoff counts the same as a wall there
  reset()
  local flood = false
  local s = surface({ground = function(x) if flood and (math.floor(x) == 8 or math.floor(x) == 0) then return "deepwater" end end,
                     near = function(c) if at(c, FROM) then return {x = 2.5, y = 0.5} end end})
  takeoff({surface = s})
  flood = true
  local _, T = jump.shape(8)
  game.tick = game.tick + T
  jump.tick(game.tick)
  assert(at(calls.landing[1].spot, {x = 2.5, y = 0.5}), "a flooded takeoff is not footing")
end)

test("tick: a landing that fails is retried 3 times a second apart, then stranded for the poll", function()
  reset()
  takeoff()
  fake_breakage.result = "failed"
  local _, T = jump.shape(8)
  game.tick = game.tick + T
  jump.tick(game.tick)
  assert(jump.pending() and count("landing") == 1, "retry queued")
  for i = 2, 4 do
    game.tick = game.tick + 60
    jump.tick(game.tick)
    assert(count("landing") == i, "attempt " .. i)
  end
  local air = calls.landing[1].airborne
  assert(not jump.pending(), "off the clock after 3 retries: nothing per tick")
  assert(jump.state().stranded == 1 and air.valid and air.operable == true, "stranded, his trunk unlocked")
  jump.poll()
  assert(count("landing") == 5 and jump.state().stranded == 1, "the poll tries again, and keeps him")
  fake_breakage.result = "held"
  jump.poll()
  local landed = calls.swap[#calls.swap].new
  assert(count("landing") == 6 and landed.name == C.name and jump.state().stranded == 0, "landed on the poll")
  assert(calls.landing[6].spot.x == air.position.x, "where he sat")
  assert(storage.jamaltron.jump.last[landed.unit_number] ~= nil and storage.jamaltron.jump.last[air.unit_number] == nil,
         "the cooldown rode to the body he landed as")
  jump.poll()
  assert(count("landing") == 6, "nothing left to land")
end)

test("poll: a stranded body that is destroyed, or lost on its landing, is dropped", function()
  reset()
  takeoff()
  fake_breakage.result = "failed"
  local _, T = jump.shape(8)
  game.tick = game.tick + T
  for _ = 1, 4 do jump.tick(game.tick) game.tick = game.tick + 60 end
  local air = calls.landing[1].airborne
  assert(jump.state().stranded == 1)
  fake_breakage.result = "lost"
  jump.poll()
  assert(jump.state().stranded == 0 and not air.valid, "lost with his body")
  reset()
  takeoff()
  fake_breakage.result = "failed"
  game.tick = game.tick + T
  for _ = 1, 4 do jump.tick(game.tick) game.tick = game.tick + 60 end
  calls.landing[1].airborne.valid = false
  local n = count("landing")
  jump.poll()
  assert(jump.state().stranded == 0 and count("landing") == n, "a destroyed one is not landed")
end)

test("forget: a destroyed body's cooldown, refusal and stranded entries go - an arc NEVER does", function()
  reset()
  local _, air = takeoff()
  local r = storage.jamaltron.jump
  local unit = air.unit_number
  r.refused[unit], r.stranded[unit] = game.tick, {entity = air, info = {}}
  r.last[999], r.refused[999] = 1, 1
  jump.forget(unit)
  assert(r.last[unit] == nil and r.refused[unit] == nil and r.stranded[unit] == nil)
  assert(r.arcs[unit] ~= nil and jump.pending(), "the arc is tick()'s to drop (clock.lua)")
  assert(r.last[999] == 1 and r.refused[999] == 1, "another unit's are kept")
  storage = {}
  jump.forget(1)                                                -- no jump state yet: harmless
end)

test("adopt_all: an airborne body with no arc is stranded (and unlocked); one in the air is not", function()
  reset()
  local _, flying = takeoff()
  local orphan = shark({name = C.airborne, driven = false})
  orphan.operable = false
  prototypes.entity[C.airborne] = {}
  game.surfaces = {{find_entities_filtered = function(f)
    assert(f.name == C.airborne)
    return {flying, orphan}
  end}}
  jump.adopt_all()
  jump.adopt_all()
  local r = storage.jamaltron.jump
  assert(jump.state().stranded == 1 and r.stranded[orphan.unit_number] and orphan.operable == true)
  assert(r.stranded[flying.unit_number] == nil and r.arcs[flying.unit_number], "the flying one is the arc's")
  prototypes.entity[C.airborne] = nil
  storage = {}
  jump.adopt_all()                                              -- no airborne prototype: nothing
  assert(storage.jamaltron == nil)
end)

test("adopt: a bare swap into airborne (no arc) is stranded, unlocked, and lands where it sits on the poll", function()
  reset()
  local orphan = shark({name = C.airborne, driven = false, position = {x = 3.5, y = 4.5}})
  orphan.operable = false
  assert(jump.adopt(orphan) == true and jump.adopt(orphan) == true, "stranded, idempotently")
  assert(jump.state().stranded == 1 and orphan.operable == true, "his trunk unlocked")
  jump.poll()
  local l = calls.landing and calls.landing[1]
  assert(count("landing") == 1 and l.airborne == orphan and l.spot.x == 3.5 and l.spot.y == 4.5,
         "landed where he sits")
  assert(jump.state().stranded == 0 and not orphan.valid)
  local _, flying = takeoff()
  assert(jump.adopt(flying) == false and jump.state().stranded == 0, "a flying body is the arc's")
  assert(jump.adopt(shark()) == false and jump.adopt(nil) == false, "only an airborne body")
  local gone = shark({name = C.airborne, driven = false})
  gone.valid = false
  assert(jump.adopt(gone) == false and jump.state().stranded == 0)
end)

test("adopt_all: arc sheets with no arc left to own them come down; a flying arc's and speech's text stay", function()
  reset()
  local _, a = takeoff()
  local _, b = takeoff()
  local sheets = {}
  for i, o in ipairs(calls.draw) do sheets[i] = o end
  assert(#sheets == 6)
  storage.jamaltron.jump.arcs[b.unit_number] = nil     -- a migration that rebuilt jump mid-arc
  local note = rendering.draw_text({target = {x = 0, y = 0}})
  prototypes.entity[C.airborne] = {}
  game.surfaces = {{find_entities_filtered = function() return {a, b} end}}
  jump.adopt_all()
  for i = 1, 3 do assert(sheets[i].valid, "the flying arc's sheet " .. i .. " came down") end
  for i = 4, 6 do assert(not sheets[i].valid, "an orphan sheet " .. i .. " stayed up") end
  for _, o in ipairs(rendering.get_all_objects("jamaltron")) do
    assert(o.type == "text" or o.type == "animation", tostring(o.type))
  end
  assert(note.valid, "a note is speech's, and times out by itself")
  assert(jump.state().stranded == 1 and storage.jamaltron.jump.stranded[b.unit_number], "the body is stranded")
  jump.adopt_all()
  assert(sheets[1].valid and jump.state().stranded == 1, "idempotent")
  prototypes.entity[C.airborne] = nil
end)

test("an older save's jump table - no stranded, no mode - is backfilled, and arcs fly", function()
  reset()
  storage.jamaltron = {jump = {arcs = {}, last = {}, refused = {}}}
  assert(jump.mode() == "arc", tostring(jump.mode()))
  local _, body = takeoff()
  assert(storage.jamaltron.jump.arcs[body.unit_number] and jump.state().stranded == 0)
  jump.poll()                                                   -- a poll over the backfilled set
end)

test("tick: a landing that THROWS leaves the air first - it is not landed again every tick", function()
  reset()
  takeoff()
  fake_breakage.result = "throw"
  local _, T = jump.shape(8)
  game.tick = game.tick + T
  assert(not pcall(jump.tick, game.tick), "the error reaches the clock")
  fake_breakage.result = "held"
  game.tick = game.tick + 1
  jump.tick(game.tick)
  assert(count("landing") == 1 and not jump.pending(), "landed " .. count("landing") .. " times")
end)

test("tick: two jamaltrons in the air at once fly and land independently", function()
  reset()
  local _, a = takeoff()
  game.tick = game.tick + 10
  local _, b = takeoff({position = {x = 100.5, y = 0.5}})
  local _, T = jump.shape(8)
  game.tick = game.tick - 10 + T
  jump.tick(game.tick)
  assert(count("landing") == 1 and calls.landing[1].airborne == a, "a first")
  assert(jump.pending())
  game.tick = game.tick + 10
  jump.tick(game.tick)
  assert(count("landing") == 2 and calls.landing[2].airborne == b and calls.landing[2].spot.x == 108.5)
  assert(not jump.pending())
end)

test("teleport mode: both swaps in try(), nothing drawn, nothing left on the clock", function()
  reset()
  assert(jump.mode("teleport") == "teleport")
  local e = shark()
  local ok = jump.try(e, nil)
  assert(ok and count("landing") == 1 and count("draw") == 0 and not jump.pending())
  assert(calls.landing[1].spot.x == 8.5)
  jump.mode("arc")
  assert(not pcall(jump.mode, "hop"), "an unknown mode is an error")
end)

test("a breakage that fails to LOAD is an error, not a silent stand-in", function()
  package.loaded["scripts.jump"], package.loaded["scripts.breakage"] = nil, nil
  package.preload["scripts.breakage"] = function() error("boom in breakage") end
  local ok, err = pcall(require, "scripts.jump")
  package.preload["scripts.breakage"] = nil
  package.loaded["scripts.breakage"] = fake_breakage
  assert(not ok and tostring(err):find("boom in breakage", 1, true), tostring(err))
end)

test("a MISSING breakage is a load error too: no clean landing stands in for the break", function()
  package.loaded["scripts.jump"], package.loaded["scripts.breakage"] = nil, nil
  -- Every module jump.lua needs is loaded already; with no path left, only breakage is missing.
  local saved, saved_c = package.path, package.cpath
  package.path, package.cpath = "", ""
  local ok, err = pcall(dofile, root .. "/mod/jamaltron/scripts/jump.lua")
  package.path, package.cpath = saved, saved_c
  package.loaded["scripts.breakage"] = fake_breakage
  assert(not ok and tostring(err):find("scripts.breakage", 1, true), tostring(err))
end)

local passed = 0
for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    error("FAIL " .. names[i] .. ": " .. tostring(err), 0)
  end
  passed = passed + 1
end
print("ok " .. passed)
