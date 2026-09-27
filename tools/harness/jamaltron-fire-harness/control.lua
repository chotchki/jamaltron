-- The flamethrower harness (PLAN D.7): his guns, where the stream leaves him, what he engages,
-- and the `attacking` lines through control.lua's own wiring - C.fired, the damage filter and
-- the 1 Hz poll into scripts/attack.lua and speech.say.
--   P        prototypes: four jamaltron-flamethrowers on the vehicle and airborne, four
--            disarmed twins on beached (D.7.3: his ammo, range 0, never warm), the signal on
--            flamethrower ammo's vehicle stream, the flamethrower in the recipe and its research
--            among his prerequisites, his research on spidertron's science packs (Space
--            Age's eight: Gleba's agricultural pack among them) and all three bodies on
--            spidertron's surface conditions (Space Age's one gravity: no platform placing)
--   FL       the damage filter's fire half: absent before anyone fires, there while he does
--   O        where the stream starts (D.7.4): ONE point under his belly, (0, -1.36) screen tiles
--            from his position, +-0.1, read back off the stream entity - at 8 aims with him
--            facing east, 8 facings each aimed along its own facing, and facing north / south
--            with the target east (prototypes/gun.lua has the measurement and chotchki's pick).
--            Plus a BEACHED Jamal facing north, a behemoth 7 tiles east - inside the live gun's
--            3-9: he starts no stream at all (D.7.3)
--   R, L     range: a small biter held still at 6, 9, 10, 11 and 12 tiles - fired on and burned
--            inside, left alone outside, one line each that fired; three live ones walking in
--   B1       ONE LINE PER BURST: a behemoth burned for ~900 ticks (one stream start, the burst
--            held open by the ammo alone), then a second target - still one line; quiet a gap,
--            a third target - a second line
--   B2       attacking.03's window, forced: said before the fight, held through every retry of
--            a 15 s burst, lifted once the gun is quiet a gap
--   S        his own splash at 3.2 tiles: hits himself, never says `damaged` about it
--   SB       ...and at 6 tiles, 8 bearings facing the target and 8 facing east: 0 HP lost to it -
--            his legs are fire-proof (D.7.5 (b)); P pins the resistance on all 24 legs
--   F1,F2,Pl friendly fire: a steel chest by the target makes `friendly` the roll's condition
--            and puts attacking.11 in the eligible set; the plain lane's does neither. F1's line
--            waits for the opening volley, so its FIRST burst rolls under friendly; F2's is held
--            by a cooldown well past the first hit. F1's next fight, a biter behind him with
--            nothing of his near it, inside the old 30 s carry-over: rolled plain
--   P2       a squad-mate: an unarmed Jamal 2 tiles past A's target takes A's splash and says no
--            `damaged` about it, and A's burst does not roll under friendly for it
--   T        a tank's stream raises the event and makes no record; a character's does not raise it
--   D        a BEACHED Jamal does not fire, by himself or for a seated driver shooting every
--            tick - against a standing one whose scripted driver does fire, so the shooting is
--            proven to work - and spends no round (D.7.3); an airborne one does fire (D.7.2 (c),
--            chotchki's open call). The ammo across a REAL break and repair is the jump
--            harness's AM lane
--   X        20 Jamaltrons in a fight with 80 biters, 1000 ticks: every event his wiring sees,
--            and each handler's cost per call, timed through what control.lua registered
--
--   HARNESS ok <check> | HARNESS FAIL <check>: <detail> | HARNESS need/never <ERE> | HARNESS done
--   FIRE <...>   measurements, never judged
--
-- Run with --ticks 2300. Headless draws nothing: the stream's LOOK (under his legs and body,
-- entity.lua's W1 layers) is tools/shot.sh's job. TO SEE THE SOURCE (tests/test_gun.py sends
-- you here when a gun number or a layer moves), run with --keep --workdir W, then load the same
-- save with graphics; the O lanes screenshot themselves at dt 60 with a red ring on the point
-- the check uses (a no-op headless):
--   factorio --mod-directory W/mods --config W/config.ini --window-size 800x600
--            --benchmark-graphics W/write/sa.zip --benchmark-ticks 65
-- and read W/write/script-output/jamaltron-fire/origin-*.png: the flame starting on the ring,
-- under his belly.

local lines = require("__jamaltron__/scripts/lines")
local pick = require("__jamaltron__/scripts/speech/pick")

local SAY, H = "jamaltron", "jamaltron-harness"
local VEHICLE, BEACHED, AIRBORNE = "jamaltron", "jamaltron-beached", "jamaltron-airborne"
local GUN, FIRED = "jamaltron-flamethrower", "jamaltron-fired"
local BROKEN = "jamaltron-flamethrower-broken"
local FAMILY = {[VEHICLE] = true, [BEACHED] = true, [AIRBORNE] = true}
local AMMO = defines.inventory.spider_ammo
local GAP = 600                                 -- speech.BURST_GAP_TICKS

local function line(v) return serpent.line(v, {comment = false, nocode = true}) end
local function L(...)
  local t = {...}
  for i = 1, select("#", ...) do t[i] = tostring(t[i]) end
  log("FIRE " .. table.concat(t, " "))
end
local function check(name, ok, detail)
  storage.passed = (storage.passed or 0) + (ok and 1 or 0)
  log(ok and ("HARNESS ok " .. name) or ("HARNESS FAIL " .. name .. ": " .. tostring(detail)))
end
local function f3(x) return string.format("%.3f", x) end
---A technology's science packs as "name x amount,...", in its order.
local function packs(tech)
  local out = {}
  for _, i in ipairs(prototypes.technology[tech].research_unit_ingredients) do
    out[#out + 1] = i.name .. " x" .. i.amount
  end
  return table.concat(out, ",")
end
---An entity's surface conditions as "property min..max,...", in its order ("" for none).
local function conds(name)
  local out = {}
  for _, c in ipairs(prototypes.entity[name].surface_conditions or {}) do
    out[#out + 1] = c.property .. " " .. tostring(c.min) .. ".." .. tostring(c.max)
  end
  return table.concat(out, ",")
end

local function paint(surface, x0, y0, x1, y1)
  local tiles = {}
  for x = x0, x1 do
    for y = y0, y1 do tiles[#tiles + 1] = {name = "grass-1", position = {x, y}} end
  end
  surface.set_tiles(tiles)
end

---A Jamal (or another body) at (x + 0.5, y + 0.5) facing `torso`, `ammo` flamethrower ammo in
---slot 1. Never raise_built: a built line would start the speech cooldown.
local function jamal(x, y, torso, ammo, name)
  local s = game.surfaces[1]
  local e = s.create_entity{name = name or VEHICLE, position = {x + 0.5, y + 0.5}, force = "player"}
  e.torso_orientation = torso or 0.25
  if (ammo or 0) > 0 then e.get_inventory(AMMO)[1].set_stack{name = "flamethrower-ammo", count = ammo} end
  return e
end
---An enemy held still (disabled_by_script) `d` tiles from `e` along orientation `o`.
local function target(e, d, o, name)
  local a = (o or 0.25) * 2 * math.pi
  local b = game.surfaces[1].create_entity{name = name or "small-biter", force = "enemy",
    position = {e.position.x + d * math.sin(a), e.position.y - d * math.cos(a)}}
  b.disabled_by_script = true
  return b
end

-- Who said what: every tracked Jamal's speech state is read each tick and a new last_tick is a
-- new utterance. storage.said[unit] = {{tick, id}, ...}
local function track(e, tag)
  storage.tracked[#storage.tracked + 1] = {e = e, tag = tag, unit = e.unit_number}
  storage.said[e.unit_number] = {}
  storage.tag[e.unit_number] = tag
end
local function said(e_or_unit, prefix)
  local unit = type(e_or_unit) == "number" and e_or_unit or e_or_unit.unit_number
  local out = {}
  for _, s in ipairs(storage.said[unit] or {}) do
    if prefix == nil or s[2]:find("^" .. prefix) then out[#out + 1] = s end
  end
  return out
end
local function ids(list)
  local out = {}
  for _, s in ipairs(list) do out[#out + 1] = s[2] .. "@" .. s[1] end
  return table.concat(out, ",")
end
local function fired(e) return (storage.starts[e.unit_number] or {}) end
local function astate(e) return remote.call(H, "attack_state", e) end

local steps = {}
local function at(dt, fn) steps[#steps + 1] = {dt = dt, fn = fn} end

-- SETUP ---------------------------------------------------------------------------------------
script.on_init(function()
  -- Logged at --create too, so the base-only stage records it as well as Space Age.
  local seen, stack = {}, {"jamaltron"}
  while #stack > 0 do
    local n = table.remove(stack)
    if not seen[n] then
      seen[n] = true
      for p in pairs(prototypes.technology[n].prerequisites) do stack[#stack + 1] = p end
    end
  end
  L("tech: jamaltron's prerequisite closure has flamethrower =", seen["flamethrower"] == true,
    "(space-age loaded:", script.active_mods["space-age"] ~= nil, ")")
  L("tech: jamaltron's packs", packs("jamaltron"), "| spidertron's", packs("spidertron"))
  L("surface: jamaltron's", conds("jamaltron"), "| spidertron's", conds("spidertron"))
end)

at(0, function(s)
  local surface = game.surfaces[1]
  for _, c in ipairs({{300, 60}, {300, 300}, {300, -80}}) do
    surface.request_to_generate_chunks(c, 14)
  end
  surface.force_generate_chunk_requests()
  surface.always_day = true
  surface.peaceful_mode = false
  for _, e in pairs(surface.find_entities_filtered{force = "enemy"}) do e.destroy() end
  for _, row in ipairs({{-40, 640, -120, 220}, {-60, 100, 250, 350}}) do
    for _, e in pairs(surface.find_entities_filtered{area = {{row[1], row[3]}, {row[2], row[4]}}}) do
      if e.type ~= "character" then e.destroy() end
    end
    paint(surface, row[1], row[3], row[2], row[4])
  end
  s.tracked, s.said, s.tag, s.starts, s.dmg, s.last_friendly = {}, {}, {}, {}, {}, {}
  remote.call(SAY, "debug", true)
  -- The R lanes (ticks 2-400) each need their ONE attacking line while ~22 other Jamals talk:
  -- at the shipped bubble cap (20) the cap is full and those short bursts rightly lose their
  -- line (F.3). So the cap is lifted for the R window only, and put back before X (1000-2000)
  -- profiles 20 Jamaltrons under the shipped cap.
  remote.call(H, "setting", "jamaltron-max-bubbles", 200)
end)
at(401, function()
  remote.call(H, "setting", "jamaltron-max-bubbles",
              prototypes.mod_setting["jamaltron-max-bubbles"].default_value)
end)

-- P: PROTOTYPES -------------------------------------------------------------------------------
at(1, function()
  for name in pairs(FAMILY) do
    local proto = prototypes.entity[name]
    local want = name == BEACHED and BROKEN or GUN
    local guns = {}
    for i, g in ipairs(proto.indexed_guns or {}) do guns[i] = g.name end
    check("P " .. name .. " mounts four " .. want, #guns == 4 and guns[1] == want and guns[2] == want
          and guns[3] == want and guns[4] == want, line(guns))
  end
  local bp = prototypes.item[BROKEN]
  local broken = bp and bp.attack_parameters
  check("P the beached gun takes his ammo and cannot fire (D.7.3)", broken
        and #broken.ammo_categories == 1 and broken.ammo_categories[1] == "flamethrower"
        and broken.range == 0 and broken.min_range == 0 and broken.warmup >= 4000000000
        and broken.ammo_consumption_modifier == 0, line(broken))
  check("P ... hidden, and named after his gun (out of action)", bp and bp.hidden
        and bp.localised_name[1] == "item-name.jamaltron-broken-gun"
        and bp.localised_name[2][1] == "item-name." .. GUN, bp and line(bp.localised_name))
  local gun = prototypes.item[GUN]
  local ap = gun.attack_parameters
  check("P the gun is a stream on flamethrower ammo, range 9", ap and ap.type == "stream"
        and ap.range == 9 and ap.ammo_categories and ap.ammo_categories[1] == "flamethrower", line(ap))
  local at_ = prototypes.item["flamethrower-ammo"].get_ammo_type("vehicle")
  local hooked = false
  for _, item in pairs(at_ and at_.action or {}) do
    for _, d in pairs(item.action_delivery or {}) do
      for _, fx in pairs(d.source_effects or {}) do
        if d.type == "stream" and fx.type == "script" then hooked = true end
      end
    end
  end
  check("P flamethrower-ammo's vehicle stream carries the firing signal", hooked, line(at_))
  local handheld = prototypes.item["flamethrower-ammo"].get_ammo_type("player")
  local clean = true
  for _, item in pairs(handheld and handheld.action or {}) do
    for _, d in pairs(item.action_delivery or {}) do
      if d.source_effects and #d.source_effects > 0 then clean = false end
    end
  end
  check("P ... and the handheld one does not", clean, line(handheld))
  local recipe = prototypes.recipe[VEHICLE]
  local has = false
  for _, ing in pairs(recipe.ingredients) do if ing.name == "flamethrower" then has = true end end
  check("P the recipe takes a flamethrower", has, line(recipe.ingredients))
  check("P the firing event exists", prototypes.custom_event[FIRED] ~= nil)
  local pre = prototypes.technology[VEHICLE].prerequisites
  check("P his research requires flamethrower (his recipe's gun, his guns' ammo)",
        pre["flamethrower"] ~= nil, line(pre))
  -- compat.lua's copy: the same packs in the same order, and the run is Space Age (the benchmark
  -- stage always is), so equal has to mean Gleba's pack - base's six on both sides would pass
  local mine, stock = packs(VEHICLE), packs("spidertron")
  check("P his research costs spidertron's packs, Gleba's among them (Space Age)",
        mine == stock and script.active_mods["space-age"] ~= nil
        and mine:find("agricultural-science-pack", 1, true) ~= nil
        and mine:find("space-science-pack", 1, true) ~= nil, mine .. " vs " .. stock)
  -- compat.lua's M.surface: all three bodies (bodies.lua copies the vehicle after it) where the
  -- spidertron can go, and under Space Age that is one gravity - never empty, so a refactor that
  -- drops them can't pass as "none on both"
  local where = conds("spidertron")
  for _, body in ipairs({VEHICLE, BEACHED, AIRBORNE}) do
    check("P " .. body .. " on spidertron's surface conditions (no space platform)",
          conds(body) == where and where:find("gravity", 1, true) ~= nil, conds(body) .. " vs " .. where)
  end
  -- D.7.5 (b): every body's eight legs fire-proof (beached and airborne copy the vehicle's), the
  -- rest of stock's leg resistances kept, and the vehicle's own untouched (stock fire 15/60)
  local function pct(r, want) return r ~= nil and math.abs(r.percent - want) < 1e-4 end  -- floats
  local bad = {}
  for name in pairs(FAMILY) do
    for i = 1, 8 do
      local leg = prototypes.entity[name .. "-leg-" .. i]
      local r = leg and leg.resistances or {}
      if not (pct(r.fire, 1) and pct(r.explosion, 1) and pct(r.physical, 0.6)) then
        bad[#bad + 1] = name .. "-leg-" .. i .. " " .. line(r)
      end
    end
  end
  check("P all 24 legs are fire-proof, stock's other leg resistances kept (D.7.5 (b))", #bad == 0,
        table.concat(bad, "; "))
  local vr = prototypes.entity[VEHICLE].resistances or {}
  check("P ... his body is not: stock's fire 15/60", pct(vr.fire, 0.6) and vr.fire.decrease == 15,
        line(vr))
end)

-- FL: THE DAMAGE FILTER -----------------------------------------------------------------------
---Does the filter the engine holds for his damage handler carry the fire half?
local function wide()
  for _, f in ipairs(remote.call(H, "damage_filter") or {}) do
    if f.filter == "damage-type" then return true end
  end
  return false
end
at(1, function()
  check("FL nobody has fired: his damage handler hears his bodies and nothing else", not wide(),
        line(remote.call(H, "damage_filter")))
end)
at(100, function()
  check("FL bursts open: the fire half is registered", wide(), line(remote.call(H, "damage_filter")))
end)

-- O: WHERE THE STREAM STARTS -----------------------------------------------------------------
-- The stream entity sits at the midpoint of its source and its target (read off the probes: a
-- target moved along the aim moves it half as far), so source = 2 * stream - target. Barrel 0:
-- the source is gun_center_shift - (0, height 1.5) - 0.008 whatever he faces or aims at.
local SOURCE = {x = 0, y = -1.36}
local ORIGIN = {}
for k = 0, 7 do ORIGIN[#ORIGIN + 1] = {torso = 0.25, aim = k / 8} end           -- every aim
for k = 0, 7 do
  if k ~= 2 then ORIGIN[#ORIGIN + 1] = {torso = k / 8, aim = k / 8} end         -- every facing
end
ORIGIN[#ORIGIN + 1] = {torso = 0, aim = 0.25}        -- facing north, target due east
ORIGIN[#ORIGIN + 1] = {torso = 0.5, aim = 0.25}      -- facing south, target due east
ORIGIN[#ORIGIN + 1] = {torso = 0, aim = 0.25, body = BEACHED}
at(2, function(s)
  s.origin = {}
  for i, o in ipairs(ORIGIN) do
    local e = jamal((i - 1) * 32, -80, o.torso, 5)
    if o.body then
      e = remote.call(H, "swap", e, o.body).body
      e.torso_orientation = o.torso
    end
    s.origin[i] = {e = e, b = target(e, 7, o.aim, "behemoth-biter"), o = o}
  end
end)
at(60, function(s)                              -- see the header: a no-op without graphics
  for i, l in ipairs(s.origin) do
    local e = l.e
    local at_ = {e.position.x + SOURCE.x, e.position.y + SOURCE.y}
    rendering.draw_circle{color = {1, 0, 0}, radius = 0.1, width = 2, filled = false, target = at_,
                          surface = e.surface, time_to_live = 30}
    game.take_screenshot{surface = e.surface, position = {e.position.x, e.position.y - 1},
      resolution = {384, 384}, zoom = 2, path = "jamaltron-fire/origin-" .. i .. ".png", daytime = 0,
      hide_clouds = true, hide_fog = true, force_render = true, show_entity_info = false}
  end
end)
at(62, function(s)
  local worst = 0
  for _, l in ipairs(s.origin) do
    local e, b, o = l.e, l.b, l.o
    local st = game.surfaces[1].find_entities_filtered{type = "stream", position = e.position, radius = 10}
    if o.body then
      -- D.7.3: a beached Jamal has no stream to start anywhere
      check("O a BEACHED Jamal starts no stream", #st == 0 and b.valid and b.health == b.max_health, #st)
    elseif #st == 0 or not b.valid then
      check("O torso " .. o.torso .. " aim " .. o.aim .. ": a stream to read", false, #st)
    else
      local src = {x = 2 * st[1].position.x - b.position.x - e.position.x,
                   y = 2 * st[1].position.y - b.position.y - e.position.y}
      local miss = math.sqrt((src.x - SOURCE.x) ^ 2 + (src.y - SOURCE.y) ^ 2)
      worst = math.max(worst, miss)
      L("origin torso", o.torso, "aim", o.aim, "source", f3(src.x), f3(src.y), "miss", f3(miss),
        "streams", #st)
      check("O torso " .. o.torso .. " aim " .. o.aim .. ": the stream leaves from under his belly "
            .. "(0, -1.36) (<0.1)", miss < 0.1, f3(src.x) .. "," .. f3(src.y))
    end
  end
  L("origin worst miss", f3(worst))
  for _, l in ipairs(s.origin) do
    if l.b.valid then l.b.destroy() end
    l.e.destroy()
  end
end)

-- R, L: RANGE ---------------------------------------------------------------------------------
local RANGE = {6, 9, 10, 11, 12}
at(2, function(s)
  s.range = {}
  for i, d in ipairs(RANGE) do
    local e = jamal((i - 1) * 60, 0, 0.25, 10)
    track(e, "R" .. d)
    s.range[i] = {e = e, b = target(e, d), d = d}
  end
  s.live = jamal(330, 0, 0.75, 10)
  track(s.live, "L")
end)
at(5, function(s)
  s.live_biters = {}
  for i = 1, 3 do
    local b = game.surfaces[1].create_entity{name = "small-biter", force = "enemy",
      position = {s.live.position.x + 20, s.live.position.y + (i - 2) * 3}}
    b.commandable.set_command{type = defines.command.attack, target = s.live}
    s.live_biters[i] = b
  end
end)
at(400, function(s)
  for _, l in ipairs(s.range) do
    local inside = l.d <= 10
    local starts, burned = #fired(l.e), (not l.b.valid) or l.b.health < l.b.max_health
    L("range", l.d, "stream starts", starts, "target", l.b.valid and ("hp " .. l.b.health) or "dead",
      "lines", ids(said(l.e, "attacking")))
    if inside then
      check("R " .. l.d .. " tiles: he fires", starts > 0, starts)
      check("R " .. l.d .. " tiles: the stream kills it", not l.b.valid, l.b.valid and l.b.health)
      check("R " .. l.d .. " tiles: one attacking line", #said(l.e, "attacking") == 1, ids(said(l.e)))
    else
      check("R " .. l.d .. " tiles: out of range, never fires", starts == 0 and not burned, starts)
      check("R " .. l.d .. " tiles: and says nothing about it", #said(l.e, "attacking") == 0, ids(said(l.e)))
    end
  end
  local dead = 0
  for _, b in ipairs(s.live_biters) do if not b.valid then dead = dead + 1 end end
  L("live: first hit on a walking biter at", s.live_first and f3(s.live_first) or "never", "tiles;",
    dead, "of 3 dead; lines", ids(said(s.live)))
  check("L three biters walking in are burned before they reach him", dead == 3, dead)
  check("L ... first hit inside 10.5 tiles", s.live_first ~= nil and s.live_first <= 10.5, s.live_first)
end)

-- B1: ONE LINE PER BURST ---------------------------------------------------------------------
at(2, function(s)
  s.b1 = jamal(0, 60, 0.25, 50)
  track(s.b1, "B1")
  s.b1t = {target(s.b1, 6, 0.25, "behemoth-biter")}
end)
at(700, function(s)
  s.b1t[2] = target(s.b1, 6, 0, "big-biter")
end)
at(1900, function(s)
  local st = astate(s.b1)
  local starts = fired(s.b1)
  local gaps = {}
  for i = 2, #starts do gaps[#gaps + 1] = starts[i] - starts[i - 1] end
  L("B1 stream starts at", line(starts), "gaps", line(gaps), "lines", ids(said(s.b1)))
  check("B1 both targets burned", not s.b1t[1].valid and not s.b1t[2].valid)
  check("B1 the fight started more than one stream", #starts >= 2, line(starts))
  local long = false
  for _, g in ipairs(gaps) do if g >= GAP then long = true end end
  check("B1 ... with a gap between starts longer than the burst gap (the ammo held it open)", long,
        line(gaps))
  check("B1 ONE attacking line for the whole burst", #said(s.b1, "attacking") == 1,
        ids(said(s.b1, "attacking")))
  check("B1 the burst has closed after a quiet gap", st == nil or not st.open, line(st))
  s.b1t[3] = target(s.b1, 6, 0.5)
end)
at(2100, function(s)
  check("B1 the next fight is a new burst, with a line", #said(s.b1, "attacking") == 2,
        ids(said(s.b1, "attacking")))
end)

-- B2: ATTACKING.03'S WINDOW, FORCED ---------------------------------------------------------------
at(2, function(s)
  s.b2 = jamal(80, 60, 0.25, 50)
  track(s.b2, "B2")
  remote.call(H, "force", s.b2, "attacking.03")
  s.b2t = target(s.b2, 6, 0.25, "behemoth-biter")
end)
at(1800, function(s)
  local st = astate(s.b2)
  L("B2 stream starts", line(fired(s.b2)), "lines", ids(said(s.b2)), "state", line(st))
  check("B2 the behemoth burned down (a 15 s burst)", not s.b2t.valid)
  check("B2 no attacking line while attacking.03's window held, cooldown long over",
        #said(s.b2, "attacking") == 1 and said(s.b2, "attacking")[1][2] == "attacking.03",
        ids(said(s.b2)))
  check("B2 the burst closed quiet", st == nil or not st.open, line(st))
  s.b2t = target(s.b2, 6, 0.5)
end)
at(2000, function(s)
  check("B2 the next fight speaks", #said(s.b2, "attacking") == 2, ids(said(s.b2)))
end)

-- S: HIS OWN SPLASH ---------------------------------------------------------------------------
at(2, function(s)
  s.self = jamal(160, 60, 0.25, 50)
  track(s.self, "S")
  s.selft = target(s.self, 3.2, 0.25, "behemoth-biter")
end)
at(700, function(s)
  local hits = storage.dmg["self:" .. s.self.unit_number] or 0
  L("S self hits", hits, "HP lost", f3(s.self.max_health - s.self.health), "lines", ids(said(s.self)))
  check("S he splashes himself at 3.2 tiles", hits > 0, hits)
  check("S ... and never complains about it", #said(s.self, "damaged") == 0
        and #said(s.self, "low_health") == 0, ids(said(s.self)))
end)

-- SB: NO SELF-BURN AT RANGE (D.7.5 (b)) --------------------------------------------------------
-- A behemoth held 6 tiles out on 8 bearings, twice: him facing it (stock legs: 15.5 HP north,
-- 4.5 NE/SW/W in 240 ticks) and him facing east aiming round (33 N, ~9 diagonals and S). Every
-- one of those burns was his splash on his own feet. Health is read off the body, so a burn
-- counts however the engine routes it; "fired and hurt it" is checked first, so a gun that
-- never fires cannot pass.
local SB0, SB1 = 2, 262                         -- 240 ticks of fire, the diagnosis' window
at(SB0, function(s)
  s.sb = {}
  for k = 0, 7 do
    for j, torso in ipairs({k / 8, 0.25}) do
      local e = jamal((k * 2 + j - 1) * 28, -110, torso, 10)
      s.sb[#s.sb + 1] = {e = e, b = target(e, 6, k / 8, "behemoth-biter"), torso = torso, aim = k / 8}
    end
  end
end)
at(SB1, function(s)
  local hot = {}
  for _, l in ipairs(s.sb) do
    local e, b = l.e, l.b
    local lost = e.max_health - e.health
    local tag = "torso " .. l.torso .. " aim " .. l.aim
    L("SB", tag, "stream starts", #fired(e), "self HP lost", f3(lost), "self hits",
      storage.dmg["self:" .. e.unit_number] or 0, "target", b.valid and b.health or "dead")
    check("SB " .. tag .. ": he fired and burned the behemoth",
          #fired(e) > 0 and (not b.valid or b.health < b.max_health), #fired(e))
    if lost > 0 then hot[#hot + 1] = tag .. " -" .. f3(lost) end
    if b.valid then b.destroy() end
    e.destroy()
  end
  check("SB 16 bearings, a behemoth 6 tiles out: 0 HP of self-burn (fire-proof legs)", #hot == 0,
        table.concat(hot, "; "))
end)

-- F: FRIENDLY FIRE ----------------------------------------------------------------------------
local ATTACK = lines.pools.attacking
local function eligible_has(cond, id)
  for _, row in ipairs(pick.eligible(ATTACK, "normal", cond)) do
    if row.id == id then return true end
  end
  return false
end
at(2, function(s)
  s.f = {}
  for i, key in ipairs({"F1", "F2", "Pl"}) do
    local e = jamal((i - 1) * 80, 120, 0.25, 50)
    track(e, key)
    local b = target(e, 7, 0.25, "behemoth-biter")
    local chest = nil
    if key ~= "Pl" then
      chest = game.surfaces[1].create_entity{name = "steel-chest", force = "player",
        position = {b.position.x + 1, b.position.y + 1.5}}
    end
    if key == "F2" then remote.call(H, "force", e, "idle.01") end     -- cooldown past the first hit
    s.f[key] = {e = e, b = b, chest = chest}
  end
end)
at(700, function(s)
  for key, l in pairs(s.f) do
    local st = astate(l.e)
    L(key, "state", line(st), "chest", l.chest and l.chest.valid and l.chest.health, "friendly hits",
      storage.dmg["friendly:" .. l.e.unit_number] or 0, "lines", ids(said(l.e)))
  end
  local f1, f2, pl = astate(s.f.F1.e), astate(s.f.F2.e), astate(s.f.Pl.e)
  check("F1 his stream damaged the steel chest beside the target (confirmed, not assumed)",
        (storage.dmg["friendly:" .. s.f.F1.e.unit_number] or 0) > 0 and s.f.F1.chest.health < s.f.F1.chest.max_health)
  check("F1 a confirmed hit makes `friendly` the roll's condition", f1 and f1.friendly ~= nil
        and f1.cond == "friendly", line(f1))
  check("F1 ... which puts attacking.11 in the eligible set", f1 and eligible_has(f1.cond, "attacking.11"))
  check("F1 the FIRST burst's own line was rolled under friendly (it waited for the volley)",
        f1 and f1.said and f1.rolled == "friendly" and #said(s.f.F1.e, "attacking") == 1, line(f1))
  check("Pl a plain burst: no friendly hit, no condition", pl and pl.friendly == nil and pl.cond == nil,
        line(pl))
  check("Pl ... and attacking.11 is not eligible", pl and not eligible_has(pl.cond, "attacking.11"))
  check("F2 a line held past the first hit is still one line", #said(s.f.F2.e, "attacking") == 1,
        ids(said(s.f.F2.e)))
  check("F2 ... rolled after the hit, under friendly", f2 and f2.rolled == "friendly"
        and said(s.f.F2.e, "attacking")[1] ~= nil and f2.friendly ~= nil, line(f2))
end)
at(1900, function(s)
  local l = s.f.F1
  local st = astate(l.e)
  L("F1 before its next fight: target", l.b.valid and l.b.health or "dead", "state", line(st),
    "last friendly hit at", storage.last_friendly[l.e.unit_number])
  check("F1 the first fight is over and its burst closed", not l.b.valid and (st == nil or not st.open),
        line(st))
  l.b2 = target(l.e, 6, 0.75)                     -- behind him; the chest is ~14 tiles off
end)
at(2100, function(s)
  local l = s.f.F1
  local st = astate(l.e)
  L("F1 next fight: lines", ids(said(l.e, "attacking")), "state", line(st), "last friendly hit at",
    storage.last_friendly[l.e.unit_number])
  check("F1 the next fight has its line", #said(l.e, "attacking") == 2, ids(said(l.e, "attacking")))
  check("F1 ... rolled PLAIN: no apology carried over from the chest ~1000 ticks ago",
        st and st.said and st.rolled == nil and not st.friendly, line(st))
end)

-- P2: A SQUAD-MATE IN THE SPLASH ---------------------------------------------------------------
at(2, function(s)
  local a = jamal(240, 60, 0.25, 50)
  track(a, "P2-A")
  local b = target(a, 7, 0.25, "behemoth-biter")
  local buddy = jamal(249, 60, 0.75, 0)            -- unarmed, 2 tiles past the target
  track(buddy, "P2-B")
  s.p2 = {a = a, b = b, buddy = buddy}
end)
at(700, function(s)
  local p = s.p2
  local hits = storage.dmg["buddy:" .. p.a.unit_number] or 0
  local st = astate(p.a)
  L("P2 buddy hits", hits, "buddy health", p.buddy.valid and p.buddy.health, "buddy lines", ids(said(p.buddy)),
    "A state", line(st), "A lines", ids(said(p.a)))
  check("P2 A's splash reached the squad-mate (measured, not assumed)", hits > 0, hits)
  check("P2 ... who says nothing about it", #said(p.buddy, "damaged") == 0
        and #said(p.buddy, "low_health") == 0, ids(said(p.buddy)))
  check("P2 ... and A's burst does not count it as friendly fire", st and st.said and not st.friendly
        and st.rolled == nil, line(st))
end)

-- T: NOT HIS -----------------------------------------------------------------------------------
at(2, function(s)
  local surface = game.surfaces[1]
  s.tank = surface.create_entity{name = "tank", position = {0.5, 180.5}, force = "player"}
  s.tank.get_inventory(defines.inventory.car_ammo)[3].set_stack{name = "flamethrower-ammo", count = 5}
  s.tank.selected_gun_index = 3
  s.tankc = surface.create_entity{name = "character", position = {0.5, 183.5}, force = "player"}
  s.tank.set_driver(s.tankc)
  s.tankt = target(s.tank, 6)
  s.hand = surface.create_entity{name = "character", position = {60.5, 180.5}, force = "player"}
  s.hand.get_inventory(defines.inventory.character_guns)[1].set_stack{name = "flamethrower"}
  s.hand.get_inventory(defines.inventory.character_ammo)[1].set_stack{name = "flamethrower-ammo", count = 5}
  s.handt = target(s.hand, 6)
end)
for dt = 3, 120 do
  at(dt, function(s)
    if s.tankt.valid then s.tankc.shooting_state = {state = defines.shooting.shooting_enemies, position = s.tankt.position} end
    if s.handt.valid then s.hand.shooting_state = {state = defines.shooting.shooting_enemies, position = s.handt.position} end
  end)
end
at(300, function(s)
  local tank_starts = #fired(s.tank)
  L("T tank stream starts", tank_starts, "target", s.tankt.valid and s.tankt.health or "dead",
    "handheld target", s.handt.valid and s.handt.health or "dead", "handheld starts", #fired(s.hand))
  if not s.tankt.valid or s.tankt.health < s.tankt.max_health then
    check("T a tank's flamethrower stream raises the event", tank_starts > 0, tank_starts)
    check("T ... and makes no speech record", remote.call(H, "state", s.tank) == nil)
  else
    L("T the scripted tank gunner never fired - tank lane not judged")
  end
  if not s.handt.valid or s.handt.health < s.handt.max_health then
    check("T a character's flamethrower does not raise it", #fired(s.hand) == 0, #fired(s.hand))
  else
    L("T the scripted character never fired - handheld lane not judged")
  end
end)

-- D: THE OTHER BODIES --------------------------------------------------------------------------
at(2, function(s)
  local b = remote.call(H, "swap", jamal(120, 180, 0.25, 10), BEACHED)
  s.beached = b.body
  remote.call(H, "keep", s.beached)
  track(s.beached, "Db")
  s.beachedt = target(s.beached, 6, 0.25)
  -- ... and one with a character seated in him, shooting the biter every tick
  local d = jamal(120, 200, 0.25, 10)
  s.bdc = game.surfaces[1].create_entity{name = "character", position = {120.5, 203.5}, force = "player"}
  d.set_driver(s.bdc)
  s.bdriven = remote.call(H, "swap", d, BEACHED).body
  remote.call(H, "keep", s.bdriven)
  s.bdrivent = target(s.bdriven, 5, 0.25)
  -- ... and the control: a STANDING one, the same driver script, the same biter 5 tiles off
  s.sdriven = jamal(150, 200, 0.25, 10)
  s.sdc = game.surfaces[1].create_entity{name = "character", position = {150.5, 203.5}, force = "player"}
  s.sdriven.set_driver(s.sdc)
  s.sdrivent = target(s.sdriven, 5, 0.25)
  local a = remote.call(H, "swap", jamal(180, 180, 0.25, 10), AIRBORNE)
  s.air = a.body
  s.airt = target(s.air, 6, 0.25)
end)
at(40, function(s)
  L("D beached stream starts", #fired(s.beached), "target", s.beachedt.valid and s.beachedt.health or "dead",
    "| airborne stream starts", s.air.valid and #fired(s.air) or "gone", "target",
    s.airt.valid and s.airt.health or "dead")
  local function rounds(e)
    local inv, n = e.get_inventory(AMMO), 0
    for i = 1, #inv do if inv[i].valid_for_read then n = n + inv[i].count * 100 - (100 - inv[i].ammo) end end
    return n
  end
  check("D a BEACHED Jamal does not fire by himself (D.7.3)", #fired(s.beached) == 0
        and s.beachedt.valid and s.beachedt.health == s.beachedt.max_health and rounds(s.beached) == 1000,
        #fired(s.beached) .. " " .. rounds(s.beached))
  L("D driver control: standing stream starts", #fired(s.sdriven), "rounds", rounds(s.sdriven), "target",
    s.sdrivent.valid and s.sdrivent.health or "dead", "| beached-driven", #fired(s.bdriven), rounds(s.bdriven))
  check("D control: the same scripted driver in a STANDING Jamal does fire",
        #fired(s.sdriven) > 0 and rounds(s.sdriven) < 1000, #fired(s.sdriven) .. " " .. rounds(s.sdriven))
  check("D ... nor for a driver shooting from inside him", s.bdriven.get_driver() == s.bdc
        and #fired(s.bdriven) == 0 and s.bdrivent.valid and s.bdrivent.health == s.bdrivent.max_health
        and rounds(s.bdriven) == 1000, #fired(s.bdriven) .. " " .. rounds(s.bdriven))
  check("D ... and opens no burst, either of them", astate(s.beached) == nil and astate(s.bdriven) == nil)
  check("D an AIRBORNE Jamal still fires (D.7.2 (c) open: chotchki's call)", s.air.valid and #fired(s.air) > 0,
        s.air.valid and #fired(s.air) or "gone")
end)

for dt = 3, 39 do
  at(dt, function(s)
    for _, d in ipairs({{s.bdc, s.bdrivent}, {s.sdc, s.sdrivent}}) do
      if d[1].valid and d[2].valid then
        d[1].shooting_state = {state = defines.shooting.shooting_enemies, position = d[2].position}
      end
    end
  end)
end

-- X: 20 IN A FIGHT, PROFILED -----------------------------------------------------------------
local X0, X1 = 1000, 2000
at(2, function(s)
  s.crowd = {}
  for i = 0, 19 do
    local e = jamal(-10 + (i % 5) * 6, 290 + math.floor(i / 5) * 6, 0.25 * (i % 4), 100)
    s.crowd[#s.crowd + 1] = e
    track(e, "X" .. i)
  end
end)
at(X0, function(s)
  local surface = game.surfaces[1]
  for i = 1, 80 do
    local a = i / 80 * 2 * math.pi
    local b = surface.create_entity{name = i % 4 == 0 and "big-biter" or "medium-biter", force = "enemy",
      position = {2 + 26 * math.cos(a), 299 + 26 * math.sin(a)}}
    b.commandable.set_command{type = defines.command.attack_area, destination = {2, 299}, radius = 16}
  end
  s.xcount = {starts = 0, events = {}}
  s.counting = true
end)
at(X1, function(s)
  s.counting = false
  local c = s.xcount
  local ticks = X1 - X0
  local per_jamal, total, most = {}, 0, 0
  for _, e in ipairs(s.crowd) do
    if e.valid then
      local n = 0
      for _, x in ipairs(said(e, "attacking")) do if x[1] >= X0 then n = n + 1 end end
      per_jamal[#per_jamal + 1] = n
      total, most = total + n, math.max(most, n)
    end
  end
  local left = #game.surfaces[1].find_entities_filtered{force = "enemy", position = {2, 299}, radius = 60}
  L("X", ticks, "ticks, 20 Jamaltrons,", 80 - left, "of 80 biters dead; stream starts", c.starts,
    "(" .. f3(c.starts / ticks) .. "/tick); attacking lines", total, "per Jamal", line(per_jamal))
  L("X damage events his handler received:", line(c.events))
  local n = 0
  for _, v in pairs(c.events) do n = n + v end
  L("X ... total", n, "(" .. f3(n / ticks) .. "/tick)")
  check("X no Jamal says more than two attacking lines in 1000 ticks of fighting", most <= 2,
        line(per_jamal))
  -- The cost per call, through what control.lua registered.
  local chest = game.surfaces[1].create_entity{name = "wooden-chest", position = {-50.5, 340.5},
                                               force = "player"}
  local cost = remote.call(H, "attack_cost", s.crowd[1], chest, s.tank, s.crowd[2], 10000)
  for key, p in pairs(cost) do
    log({"", "FIRE cost x10000 ", key, " ", p})
  end
end)
at(2250, function()                              -- after every lane's last check (2100)
  log("HARNESS done " .. tostring(storage.passed))
end)

-- EVENTS --------------------------------------------------------------------------------------
script.on_event(FIRED, function(event)
  local src = event.source_entity
  if src and src.valid and src.unit_number then
    local list = storage.starts[src.unit_number] or {}
    list[#list + 1] = event.tick - (storage.t0 or 0)
    storage.starts[src.unit_number] = list
  end
  if storage.counting and src and src.valid and FAMILY[src.name] then
    storage.xcount.starts = storage.xcount.starts + 1
  end
end)

-- What control.lua's filter lets through (its damage handler), replicated to count it, plus the
-- live lane's first hit. No filter here: the harness sees everything.
local SKIP = {unit = true, ["unit-spawner"] = true, turret = true, tree = true, ["simple-entity"] = true,
              ["spider-unit"] = true, ["segmented-unit"] = true}
script.on_event(defines.events.on_entity_damaged, function(event)
  local s = storage
  local entity, cause = event.entity, event.cause
  local cause_ours = cause and cause.valid and FAMILY[cause.name]
  if s.live and cause == s.live and not s.live_first then
    s.live_first = math.sqrt((entity.position.x - cause.position.x) ^ 2 + (entity.position.y - cause.position.y) ^ 2)
  end
  local ours = FAMILY[entity.name]
  local passes = ours or (event.damage_type.name == "fire" and event.final_damage_amount > 0
                          and not SKIP[entity.type])
  if not passes then return end
  local kind
  if cause_ours and cause == entity then
    kind = "self"
  elseif cause_ours and entity.force_index == cause.force_index and event.damage_type.name == "fire" then
    kind = ours and "friendly-jamal" or "friendly"
  elseif ours then
    kind = "bitten"
  else
    kind = "other"
  end
  if cause_ours then
    local key = (kind == "friendly-jamal" and "buddy" or kind) .. ":" .. cause.unit_number
    s.dmg[key] = (s.dmg[key] or 0) + 1
    if kind == "friendly" then s.last_friendly[cause.unit_number] = event.tick - (s.t0 or 0) end
  end
  if s.counting then s.xcount.events[kind] = (s.xcount.events[kind] or 0) + 1 end
end)

table.sort(steps, function(x, y) return x.dt < y.dt end)

script.on_event(defines.events.on_tick, function(event)
  local s = storage
  s.t0 = s.t0 or event.tick
  local dt = event.tick - s.t0
  for _, step in ipairs(steps) do
    if step.dt == dt then
      local ok, err = pcall(step.fn, s)
      if not ok then check("step at dt " .. dt .. " ran", false, err) end
    end
  end
  for _, t in ipairs(s.tracked or {}) do
    if t.e.valid then
      local st = remote.call(H, "state", t.e)
      if st and st.last_tick and st.last_tick ~= t.last then
        t.last = st.last_tick
        local list = s.said[t.unit]
        list[#list + 1] = {st.last_tick - s.t0, st.last_id}
      end
    end
  end
end)
