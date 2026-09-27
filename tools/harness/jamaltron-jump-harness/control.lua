-- The jump harness (PLAN E.1-E.6): THE WHOLE LOOP in the engine, through control.lua's own
-- wiring - jump.try, the arc on the clock, breakage.on_landing, the beached body's flops and
-- alert on the 60-tick poll, and the repair back to a walking jamaltron.
--   J1-J10   a driven jamaltron jumps 8 tiles and lands walking, kit intact; which way; the
--            edges (destroyed, driver out or dead mid-air, spot walled over, teleport mode, a
--            follower); JD the distance setting
--   refusals every one the engine can reach, with its reason and nothing moved - a passenger's
--            press included, through a character standing in for the player
--   B        THE LOOP: a full kit, a forced break (100%), beached, W held 10 s and not a step,
--            the status, the alert bookkeeping, legs_break then flops on the apology timer at
--            DEFAULT settings, the damage; a partial repair that is not enough, then the repair
--            event's own handler at full health - walking again, repaired, fork cleared, {N}
--            kept, kit intact - and a second break repaired by the bot poll ({N} = 2)
--   P1, P2   two break in the same tick beside B: one repaired by the poll, one dies beached
--   L1, L2   breakage.on_landing alone, profiled: one break, one clean; one repair
--   AM       D.7.3: a real break with four odd ammo slots and a driver shooting every tick -
--            beached he fires nothing and spends nothing, every slot and the selected gun come
--            back exactly on the repair, and the repaired Jamal fires for the same driver
--   X        ANOTHER mod parks the beached J9 in a body of its own and brings him back (the
--            Spidertron Enhancements pattern, raising on_spidertron_replaced): his break record
--            and alert follow him, and he neither flops nor gets up while parked
--   crowd    twenty in the air at once, profiled
--   row E    the review's fixes: K a bare swap to beached is kept (breakage.keep, the playtest
--            path) - half health, flops, up at full; F a landing a listener kills 5 times is
--            stranded off the clock, then landed by the poll; STATE another mod's frozen or
--            locked vehicle is refused, a decon mark rides the landing; MID a silo on the spot
--            AND a wall on the takeoff, water round both - never in a wall or a lake; REL a key
--            let go of mid-arc lands him standing; DRIFT a break beside water settles, and the
--            kept alert position follows him; SA a bare swap to airborne is stranded (strand, the
--            playtest path) and lands where he sits on the poll
--   W        D.1.3's broken legs: every beached body gets exactly the set its record holds - 46,
--            all on him - drawn once (a second keep adds none), on a bare swap by keep(), onto the
--            body another mod parks him back in, beached -> beached and onto a body already kept
--            (one set, never two), on a clone; adopt_all redraws a set that is gone and touches
--            no other; none left once he is repaired, dies, or moves to a body not beached
--
--   HARNESS ok <check> | HARNESS FAIL <check>: <detail> | HARNESS need/never <ERE> | HARNESS done
--   JUMP <...>   measurements, never judged
--
-- A headless run has no LuaPlayer: the key itself, remote driving, the alert on screen, a real
-- repair pack's event and everything drawn are tools/play.sh's (the E.1 look is chotchki's
-- call). The scripted character driver's walking_state LATCHES (E.2.2, measured): written once,
-- held; lanes standing in for a held key write it every tick anyway. Leg breaks are pinned to 0%
-- except the ticks a lane lands at 100%, so no check rides the break roll; the one check that
-- rides a line roll (a lake refusal saying the water row) has 48 sharks and a forced twin. Run
-- it with --ticks 4500.

local lines = require("__jamaltron__/scripts/lines")
local pick = require("__jamaltron__/scripts/speech/pick")
local art = require("__jamaltron__/prototypes/sprites_generated")

local SAY, H = "jamaltron", "jamaltron-harness"
local VEHICLE, AIRBORNE, BEACHED = "jamaltron", "jamaltron-airborne", "jamaltron-beached"
local LEG = "jamaltron-leg-1"
local K = 0.7071067811865
local ROW_J, ROW_R, ROW_W, ROW_C, ROW_B, ROW_E = 0, 120, 240, -160, -300, -420
local TRUNK, AMMO, TRASH = defines.inventory.spider_trunk, defines.inventory.spider_ammo,
  defines.inventory.spider_trash
-- THE LOOP's clock, in harness ticks (dt). Every lane that lands at 100% lands on BREAK_AT and
-- nothing else lands there; B lies beached BEACHED_FOR ticks at default settings, long enough
-- for three apology attempts at the slowest jitter (15 s * 1.2) - one may be legs_break.18's
-- skipped flop, so two flops said is the floor.
local B0 = 460                                      -- B, P1, P2 take off
local BREAK_AT = B0 + 30                            -- ... and land beached
local BEACHED_FOR = 3600
local REPAIR_AT = BREAK_AT + BEACHED_FOR            -- the repair event's path
local AGAIN_AT = REPAIR_AT + 110                    -- B's second jump, broken again
local END_AT = AGAIN_AT + 200

local function line(v) return serpent.line(v, {comment = false, nocode = true}) end
local function L(...)
  local t = {...}
  for i = 1, select("#", ...) do t[i] = tostring(t[i]) end
  log("JUMP " .. table.concat(t, " "))
end
local function check(name, ok, detail)
  storage.passed = (storage.passed or 0) + (ok and 1 or 0)
  log(ok and ("HARNESS ok " .. name) or ("HARNESS FAIL " .. name .. ": " .. tostring(detail)))
end
local function near(a, b, eps) return a ~= nil and b ~= nil and math.abs(a - b) <= (eps or 1e-6) end
local function dist(a, b) return math.sqrt((a.x - b.x) ^ 2 + (a.y - b.y) ^ 2) end
---A render object's orientation reads back in [0, 1): -0.04 is 0.96. Signed, for pitch.
local function signed(o) return (o and o > 0.5) and o - 1 or o end

---@return {jumped: boolean, why: string?, said: string?}
local function jump(entity) return remote.call(H, "jump", entity) end
local function jstate(entity) return remote.call(H, "jump_state", entity) end
local function clockstate() return remote.call(H, "clock") end
local function census() return remote.call(H, "census") end
local function set(name, value) remote.call(H, "setting", name, value) end

local SUB = {}
for _, pool in pairs(lines.pools) do
  for _, row in ipairs(pool.rows) do SUB[row.id] = row.sub or "-" end
end
---Is `row` one this refusal may say: its reason's own rows or the any rows?
local function refusal_row(row, reason)
  return row ~= nil and row:match("^jump_refused%.") ~= nil and (SUB[row] == reason or SUB[row] == "any")
end

local function paint(surface, x0, y0, x1, y1, name)
  local tiles = {}
  for x = x0, x1 do
    for y = y0, y1 do tiles[#tiles + 1] = {name = name, position = {x, y}} end
  end
  surface.set_tiles(tiles)
end

---A driven jamaltron at (x + 0.5, y + 0.5) facing `torso`, its character driver holding `hold`
---(a defines.direction) or standing still.
local function driven(x, y, torso, hold)
  local surface = game.surfaces[1]
  local e = surface.create_entity{name = VEHICLE, position = {x + 0.5, y + 0.5}, force = "player"}
  local c = surface.create_entity{name = "character", position = {x + 0.5, y + 3.5}, force = "player"}
  e.set_driver(c)
  e.torso_orientation = torso or 0.25
  if hold then c.walking_state = {walking = true, direction = hold} end
  return e, c
end

---The one jamaltron-family body within `r` of `pos` (any of the three).
local function body_at(pos, r)
  for _, e in pairs(game.surfaces[1].find_entities_filtered{position = pos, radius = r or 0.1,
                                                            type = "spider-vehicle"}) do
    if e.name == VEHICLE or e.name == AIRBORNE or e.name == BEACHED then return e end
  end
end

local function speech(e) return remote.call(H, "state", e) end
local function kept(e) return remote.call(H, "breakage_state", e) end
local function percent(p) set("jamaltron-leg-break-percent", p) end
local function row_of(e) local st = speech(e) return st and st.last_id or "" end
---Our arc drawings still up: render objects of type animation this mod owns (speech notes are
---text, and never counted).
local function animations()
  local n = 0
  for _, o in pairs(rendering.get_all_objects("jamaltron")) do
    if o.type == "animation" then n = n + 1 end
  end
  return n
end

---D.1.3: our sprites drawn on `e` - his broken legs; nothing else of ours is a sprite - sorted ids.
local function wreck_on(e)
  local ids = {}
  for _, o in pairs(rendering.get_all_objects("jamaltron")) do
    if o.type == "sprite" and o.target.entity == e then ids[#ids + 1] = o.id end
  end
  table.sort(ids)
  return ids
end
---How many of `ids` are still drawn.
local function alive(ids)
  local n = 0
  for _, id in ipairs(ids or {}) do
    if rendering.get_object_by_id(id) then n = n + 1 end
  end
  return n
end
---Does `e` lie in exactly the legs breakage keeps for him, a whole set of them?
local function wreck_kept(e)
  local want = kept(e).wreck or {}
  local ids = wreck_on(e)
  local sorted = {}
  for i, id in ipairs(want) do sorted[i] = id end
  table.sort(sorted)
  local same = #ids == #sorted and #ids == 46                -- 5 a leg, 8 for each of two kinked
  for i = 1, #ids do same = same and ids[i] == sorted[i] end
  return same, ids, #ids .. " drawn on him, record " .. line(sorted)
end

-- THE KIT: what a player with a toolbelt and a full trunk carries. The toolbelt's 10 slots exist
-- only from t+1 on every body (swap.lua), so every jump, break and repair parks them in the
-- stash for a tick - the path most likely to lose an item.
local FILLERS
local function fill(e)
  if not FILLERS then
    FILLERS = {}
    for name, proto in pairs(prototypes.item) do
      -- no robots: his own roboport would repair him and short-circuit the flop window
      if proto.type == "item" and not proto.hidden and proto.stack_size > 1 and proto.get_spoil_ticks() == 0
          and not name:find("equipment", 1, true) and not name:find("robot", 1, true) then
        FILLERS[#FILLERS + 1] = name
      end
    end
    table.sort(FILLERS)
  end
  local t, k = e.get_inventory(TRUNK), 0
  local present = {}
  for i = 1, #t do if t[i].valid_for_read then present[t[i].name] = true end end
  for i = 1, #t do
    if not t[i].valid_for_read then
      repeat k = k + 1 until not present[FILLERS[k]]
      t[i].set_stack{name = FILLERS[k], count = 1}
    end
  end
end
local function kit_grid(e)
  local g = e.grid
  g.put{name = "fission-reactor-equipment", position = {0, 0}}
  g.put{name = "personal-roboport-equipment", position = {4, 0}}
  g.put{name = "energy-shield-equipment", position = {6, 0}}
  g.put{name = "battery-mk2-equipment", position = {8, 0}, quality = "rare"}
  g.put{name = "toolbelt-equipment", position = {0, 4}}
  e.color = {r = 0.9, g = 0.2, b = 0.6, a = 0.5}
  e.entity_label = "Jamal kit"
end
---A tick after kit_grid: the toolbelt has grown the trunk, and every slot of it gets filled.
local function kit_items(e)
  local trunk = e.get_inventory(TRUNK)
  trunk[1].set_stack{name = "iron-plate", count = 100}
  trunk[2].set_stack{name = "iron-plate", count = 10, quality = "rare"}
  trunk[3].set_stack{name = "gun-turret", count = 3, health = 0.5}
  trunk[#trunk].set_stack{name = "sulfur", count = 33}          -- a toolbelt slot
  fill(e)
  -- D.7: his guns are flamethrowers, and an ammo slot refuses anything else WITHOUT an error -
  -- the rockets this used to load never went in, and "the ammo came through intact" held for an
  -- empty slot. So the load is checked, not assumed.
  local loaded = e.get_inventory(AMMO)[1].set_stack{name = "flamethrower-ammo", count = 37}
  check("kit: 37 flamethrower ammo went into his ammo slot", loaded
        and e.get_inventory(AMMO).get_item_count("flamethrower-ammo") == 37)
  e.get_inventory(TRASH)[1].set_stack{name = "stone", count = 20}
end
---Everything he carries as sorted plain lines: trunk, ammo and trash contents by name and
---quality, the grid by name, quality and place, the damaged turrets' health, trunk size.
local function kit_of(e)
  local r = {}
  for _, idx in ipairs({TRUNK, AMMO, TRASH}) do
    local inv = e.get_inventory(idx)
    for _, c in pairs(inv.get_contents()) do
      r[#r + 1] = idx .. ":" .. c.name .. "/" .. tostring(c.quality) .. "=" .. c.count
    end
  end
  for _, q in pairs(e.grid.equipment) do
    r[#r + 1] = "grid:" .. q.name .. "/" .. q.quality.name .. "@" .. q.position.x .. "," .. q.position.y
  end
  local turrets = e.get_inventory(TRUNK).find_item_stack("gun-turret")
  r[#r + 1] = "turret-health:" .. tostring(turrets and turrets.health)
  r[#r + 1] = "trunk-size:" .. #e.get_inventory(TRUNK)
  r[#r + 1] = "label:" .. tostring(e.entity_label)
  table.sort(r)
  return table.concat(r, " ")
end
local function same_kit(tag, before, e)
  local now = kit_of(e)
  check(tag .. " every trunk, ammo, trash and grid item intact, toolbelt slots included", now == before,
        "\n   was " .. before .. "\n   now " .. now)
end

local steps, every = {}, {}
local function at(dt, fn) steps[#steps + 1] = {dt = dt, fn = fn} end
---`fn(s, dt)` on every tick from `from` to `to`, after that tick's steps.
local function during(from, to, fn) every[#every + 1] = {from = from, to = to, fn = fn} end

-- A landing's damage is WRITTEN (breakage.lua): on_entity_damaged must not see it, or control.lua
-- answers with a damaged line on top of the landing line. Counted per body name.
script.on_event(defines.events.on_entity_damaged, function(event)
  storage.damaged = (storage.damaged or 0) + 1
  L("damaged", event.entity.name, event.final_damage_amount)
end, {{filter = "name", name = VEHICLE}, {filter = "name", name = BEACHED}, {filter = "name", name = AIRBORNE}})

-- SETUP -----------------------------------------------------------------------------------
at(0, function(s)
  local surface = game.surfaces[1]
  surface.request_to_generate_chunks({150, 40}, 12)
  surface.request_to_generate_chunks({150, ROW_B}, 8)
  surface.request_to_generate_chunks({200, ROW_E}, 8)
  surface.force_generate_chunk_requests()
  L("map seed", surface.map_gen_settings.seed)
  surface.peaceful_mode = true
  for _, e in pairs(surface.find_entities_filtered{force = "enemy"}) do e.destroy() end
  -- Grass and nothing else under every lane: a lane that rolls a lake or a cliff tests that.
  for _, row in ipairs({{-30, 700, ROW_J - 20, ROW_J + 20}, {-30, 400, ROW_R - 20, ROW_R + 20},
                        {-30, 60, ROW_W - 10, ROW_W + 300}, {-30, 330, ROW_C - 20, ROW_C + 20},
                        {-30, 400, ROW_B - 40, ROW_B + 20}, {-30, 420, ROW_E - 30, ROW_E + 30}}) do
    local area = {{row[1], row[3]}, {row[2], row[4]}}
    for _, e in pairs(surface.find_entities_filtered{area = area}) do
      if e.type ~= "character" then e.destroy() end
    end
    paint(surface, row[1], row[3], row[2], row[4], "grass-1")
  end
  set("jamaltron-leg-break-percent", 0)
  -- The shipped cooldown is 0 (chotchki: refuse while the arc plays, nothing after), which
  -- leaves the cooldown refusal nothing to refuse. J1 pins 5 s so the mechanism stays proven.
  local cool = prototypes.mod_setting["jamaltron-jump-cooldown"].default_value
  check("the jump cooldown ships at 0: only the arc itself refuses a jump", cool == 0, cool)
  set("jamaltron-jump-cooldown", 5)
  remote.call(SAY, "debug", true)
  local c = clockstate()
  check("idle: nothing in the air, on_tick not registered", not c.pending and not c.registered, line(c))
  local key = prototypes.custom_input["jamaltron-jump"]
  check("the jump key exists (startup setting on)", key ~= nil)
  check("its default is Y, and nothing is consumed", key and key.key_sequence == "Y" and key.consuming == "none",
        key and (key.key_sequence .. " " .. key.consuming))
  local name, desc = key and key.localised_name, key and key.localised_description
  L("the key's localised name", line(name), "description", line(desc))
  check("the controls menu looks it up under [custom-input-name] (locale/en/jamaltron.cfg)",
        type(name) == "table" and name[1] == "custom-input-name.jamaltron-jump", line(name))
  check("... and its tooltip under [custom-input-description]",
        type(desc) == "table" and desc[1] == "custom-input-description.jamaltron-jump", line(desc))
  check("the beached body exists for breakage to land him in", prototypes.entity[BEACHED] ~= nil)
  local ks = kept()
  check("nothing beached at the start", ks.beached == 0, line(ks))

  s.j1, s.j1c = driven(0, ROW_J, 0.25, defines.direction.east)     -- lands walking, kit intact
  kit_grid(s.j1)
  s.j2 = driven(60, ROW_J, 0.25, defines.direction.south)          -- held south beats torso east
  s.j3 = driven(120, ROW_J, 0.75)                                  -- standing, torso west
  s.j4 = driven(180, ROW_J)                                        -- destroyed mid-air
  s.j5, s.j5c = driven(240, ROW_J)                                 -- driver gets out mid-air
  s.j6, s.j6c = driven(300, ROW_J)                                 -- driver dies mid-air
  s.j7 = driven(360, ROW_J)                                        -- the spot walled mid-air
  s.j8 = driven(420, ROW_J)                                        -- teleport mode
  s.j9 = driven(480, ROW_J)                                        -- a break
  s.j10 = driven(540, ROW_J)                                       -- a follower
  s.lead = surface.create_entity{name = VEHICLE, position = {560.5, ROW_J + 0.5}, force = "player"}
  s.j10.follow_target = s.lead

  -- the refusals the engine can reach
  s.r_none = surface.create_entity{name = VEHICLE, position = {0.5, ROW_R + 0.5}, force = "player"}
  s.r_auto = driven(40, ROW_R)
  s.r_auto.add_autopilot_destination({40.5, ROW_R + 15.5})
  s.r_lava = driven(80, ROW_R)
  paint(surface, 86, ROW_R - 3, 92, ROW_R + 3, "lava")
  s.r_void = driven(120, ROW_R)
  paint(surface, 126, ROW_R - 3, 132, ROW_R + 3, "out-of-map")
  s.r_wall = driven(160, ROW_R)
  surface.create_entity{name = "stone-wall", position = {168.5, ROW_R + 0.5}, force = "player"}
  s.r_tree = driven(200, ROW_R)
  s.tree = surface.create_entity{name = "tree-01", position = {208.5, ROW_R + 0.5}}
  -- a passenger presses: a character stands in for the player (jump.check's same comparison)
  s.r_pass, s.r_pass_d = driven(380, ROW_R)
  s.r_pass_p = surface.create_entity{name = "character", position = {383.5, ROW_R + 0.5}, force = "player"}
  s.r_pass.set_passenger(s.r_pass_p)
  -- STRADDLE: at 16 tiles, 14 of deep water to a 3x3 islet (refused, water) or to a far bank.
  -- Water painted BEFORE the spider: set_tiles removes what collides, and a leg does (measured).
  paint(surface, 282, ROW_R - 20, 310, ROW_R + 20, "deepwater")
  paint(surface, 295, ROW_R - 1, 297, ROW_R + 1, "grass-1")
  s.r_islet = driven(280, ROW_R)
  paint(surface, 342, ROW_R - 20, 355, ROW_R + 20, "deepwater")
  s.r_bank = driven(340, ROW_R)

  -- 48 sharks at one long lake: an 8-tile hop lands in it
  s.water = {}
  paint(surface, 4, ROW_W - 5, 20, ROW_W + 295, "deepwater")
  for i = 0, 47 do s.water[#s.water + 1] = driven(-4, ROW_W + i * 6) end

  -- twenty in the air at once
  s.crowd = {}
  for i = 0, 19 do s.crowd[#s.crowd + 1] = driven(i * 15, ROW_C) end

  -- THE LOOP: B with the kit, P1 and P2 beside him, L1 and L2 for breakage alone, JD for distance
  s.b, s.bc = driven(0, ROW_B, 0.25)                                -- holds east at takeoff only
  kit_grid(s.b)
  s.p1, s.p1c = driven(60, ROW_B, 0.25)
  s.p2, s.p2c = driven(120, ROW_B, 0.25)
  s.l1, s.l1c = driven(200, ROW_B, 0.25)
  s.l2, s.l2c = driven(260, ROW_B, 0.25)
  s.jd = driven(320, ROW_B, 0)                                      -- standing, torso north

  -- ROW E: the review's fixes
  s.k, s.kc = driven(0, ROW_E)
  s.f, s.fc = driven(40, ROW_E)
  s.st = {}
  for i, kind in ipairs({"disabled", "inoperable", "decon"}) do
    local e, c = driven(40 + i * 40, ROW_E)
    if kind == "disabled" then e.disabled_by_script = true end
    if kind == "inoperable" then e.operable = false end
    if kind == "decon" then e.order_deconstruction("player") end
    s.st[kind] = {e = e, c = c, unit = e.unit_number, from = e.position}
  end
  s.mw, s.mwc = driven(200, ROW_E)                                  -- silo on the spot, wall at takeoff
  s.mb, s.mbc = driven(260, ROW_E)                                  -- deep water round both
  s.rel, s.relc = driven(300, ROW_E, 0.25, defines.direction.east)  -- lets go of the key mid-arc
  paint(surface, 350, ROW_E - 20, 378, ROW_E + 20, "deepwater")     -- DRIFT: water from spot + 2
  s.dr, s.drc = driven(340, ROW_E)
end)
at(1, function(s)
  for _, e in ipairs({s.j1, s.b}) do
    check("kit: the toolbelt grew the trunk (" .. e.unit_number .. ")",
          #e.get_inventory(TRUNK) == e.prototype.get_inventory_size(TRUNK, e.quality) + 10, #e.get_inventory(TRUNK))
    kit_items(e)
  end
  s.j1kit = kit_of(s.j1)
  L("kit", s.j1kit)
end)

-- J1: THE JUMP ----------------------------------------------------------------------------
at(10, function(s)
  local e = s.j1
  s.j1from = e.position
  s.j1unit = e.unit_number
  local r = jump(e)
  check("J1 a driven jamaltron jumps", r.jumped == true and r.why == nil, line(r))
  check("J1 he says a jump line", r.said ~= nil and r.said:match("^jump%.") ~= nil, line(r))
  local a = body_at(s.j1from)
  s.j1a = a
  check("J1 he is the airborne body now", a ~= nil and a.name == AIRBORNE and not e.valid, a and a.name)
  check("J1 his driver rides the airborne body (the camera follows)", a.get_driver() == s.j1c)
  check("J1 the airborne body is not operable", a.operable == false)
  check("J1 the airborne body faces the jump (east)", near(a.torso_orientation, 0.25), a.torso_orientation)
  local st = jstate(a)
  check("J1 one arc, three render objects", st.arcs >= 1 and st.arc ~= nil and st.drawn >= 3, line(st))
  check("J1 frame 16 is east", st.arc and st.arc.frame == 16, line(st.arc))
  local c = clockstate()
  check("J1 the clock is on while he is up", c.pending and c.registered, line(c))
  log("HARNESS never jamaltron speech " .. a.unit_number .. " (built|enter|exit|idle|moving)[.]")
end)
at(11, function(s)
  local r = jump(s.j1a)
  check("J1 a press mid-air does nothing (not the vehicle)", r.jumped == false and r.why == "not_vehicle"
        and r.said == nil, line(r))
end)
at(25, function(s)                                    -- u = 0.5: the peak
  local a = s.j1a
  check("J1 mid-arc on the absolute path (4 tiles on at u=0.5)",
        near(a.position.x, s.j1from.x + 4, 1 / 256) and near(a.position.y, s.j1from.y, 1 / 256),
        line(a.position))
  local st = jstate(a).arc
  local bs, ss = art.sprites.body.shift, art.sprites.shadow.shift
  local body, shadow = st.body, st.shadow
  -- 1/256: the body's position snaps to it and the drawing is aimed at the unsnapped path point
  check("J1 at the peak the body is up 1.5 + 3 * 0.7071", near(body.y, bs[2] - 1.5 - 3 * K, 1 / 256)
        and near(body.x, bs[1], 1 / 256), line(st.body))
  check("J1 ... and the shadow 1.5 + 3 tiles east, on the ground",
        near(shadow.x, ss[1] + 4.5, 1 / 256) and near(shadow.y, ss[2], 1 / 256), line(st.shadow))
  check("J1 level at the peak", near(signed(st.pitch), 0, 1e-3), st.pitch)
  L("J1 peak pose body", line(st.body), "shadow", line(st.shadow))
end)
at(13, function(s)
  local st = jstate(s.j1a).arc
  check("J1 nose up on the way up (east: pitch < 0)", signed(st.pitch) < 0, st.pitch)
end)
at(38, function(s)
  local st = jstate(s.j1a).arc
  check("J1 nose down on the way down", signed(st.pitch) > 0, st.pitch)
end)
at(40, function(s)                                    -- touchdown: takeoff + 30
  local spot = {x = s.j1from.x + 8, y = s.j1from.y}
  local e = body_at(spot)
  s.j1l = e
  check("J1 lands as the vehicle, exactly on the spot",
        e ~= nil and e.name == VEHICLE and e.position.x == spot.x and e.position.y == spot.y,
        e and (e.name .. " " .. line(e.position)))
  check("J1 the airborne body is gone", not s.j1a.valid)
  check("J1 his driver is back in the vehicle", e and e.get_driver() == s.j1c)
  check("J1 he lands facing the way he flew", e and near(e.torso_orientation, 0.25), e and e.torso_orientation)
  local st = jstate()
  check("J1 his drawing went with his arc: 3 render objects per arc still up, no more",
        st.drawn == 3 * st.arcs, line(st))
  log("HARNESS need jamaltron speech " .. e.unit_number .. " land[.]")
  log("HARNESS never jamaltron speech " .. e.unit_number .. " (built|enter|exit)[.]")
  s.j1spot = spot
  local ratio = e and e.get_health_ratio() or 0
  check("J1 a clean landing thuds 1-3% off a full bar", ratio >= 0.97 - 1e-6 and ratio <= 0.99 + 1e-6, ratio)
  check("J1 ... WRITTEN, not dealt: no on_entity_damaged all run so far", (storage.damaged or 0) == 0,
        storage.damaged)
  check("J1 a clean landing keeps no break record", e and not kept(e).kept)
end)
at(42, function(s) same_kit("J1 landed (t+2)", s.j1kit, s.j1l) end)
at(41, function(s)
  local c = clockstate()
  check("J1 the clock is registered exactly while something is pending (on_load's rule)",
        c.pending == c.registered, line(c))
end)
at(55, function(s)
  local r = jump(s.j1l)
  check("J1 a second jump inside the cooldown is refused: cooldown", r.jumped == false and r.why == "cooldown", line(r))
  check("J1 ... and he is still the walking body he landed as", s.j1l.valid and s.j1l.name == VEHICLE)
  check("J1 ... with a cooldown or an any row, if R5 let him speak", r.said == nil or refusal_row(r.said, "cooldown"),
        line(r))
end)
at(70, function(s)
  local e = s.j1l
  local moved = dist(s.j1spot, e.position)
  check("J1 landed WALKING on the direction he held", e.speed > 0.02 and moved > 0.5,
        "speed " .. e.speed .. " moved " .. moved)
  s.j1c.walking_state = {walking = false, direction = defines.direction.east}
end)
at(320, function(s)                                   -- takeoff + 310: past the 5 s cooldown
  local r = jump(s.j1l)
  check("J1 after the cooldown he jumps again", r.jumped == true, line(r))
end)

-- J2, J3: WHICH WAY ------------------------------------------------------------------------
at(12, function(s)
  s.j2from, s.j3from = s.j2.position, s.j3.position
  check("J2 jumps", jump(s.j2).jumped)
  check("J3 jumps", jump(s.j3).jumped)
end)
at(42, function(s)
  local b2 = body_at({x = s.j2from.x, y = s.j2from.y + 8})
  check("J2 a held direction wins: 8 tiles SOUTH while his torso faced east", b2 ~= nil and b2.name == VEHICLE,
        line(s.j2from))
  local b3 = body_at({x = s.j3from.x - 8, y = s.j3from.y})
  check("J3 standing still, his torso decides: 8 tiles WEST", b3 ~= nil and b3.name == VEHICLE, line(s.j3from))
  check("J3 ... and he lands facing west", b3 and near(b3.torso_orientation, 0.75), b3 and b3.torso_orientation)
end)

-- J4-J7: THE EDGES -------------------------------------------------------------------------
at(14, function(s)
  for _, k in ipairs({"j4", "j5", "j6", "j7"}) do
    s[k .. "from"] = s[k].position
    check(k:upper() .. " jumps", jump(s[k]).jumped)
    s[k .. "a"] = body_at(s[k .. "from"])
  end
end)
at(24, function(s)
  s.before = jstate().arcs
  s.j4a.destroy()
  s.j5a.set_driver(nil)
  s.j6c.die()
  s.j7spot = {x = s.j7from.x + 8, y = s.j7from.y}
  s.j7wall = game.surfaces[1].create_entity{name = "stone-wall", position = s.j7spot, force = "player"}
  check("J7 a wall went up on his landing spot mid-air", s.j7wall ~= nil)
end)
at(25, function(s)
  local st = jstate()
  L("state after J4's body was destroyed", line(st))
  check("J4 a body destroyed mid-air: its arc gone, no render object left over",
        st.arcs == s.before - 1 and st.drawn == 3 * st.arcs, line(st) .. " before " .. s.before)
  check("J5 his driver got out mid-air and stands somewhere", s.j5c.valid and s.j5c.vehicle == nil)
end)
at(44, function(s)
  local b5 = body_at({x = s.j5from.x + 8, y = s.j5from.y})
  check("J5 lands empty", b5 ~= nil and b5.name == VEHICLE and b5.get_driver() == nil)
  local b6 = body_at({x = s.j6from.x + 8, y = s.j6from.y})
  check("J6 lands with his dead driver gone", b6 ~= nil and b6.name == VEHICLE and b6.get_driver() == nil)
  local b7 = body_at(s.j7spot, 6)
  check("J7 never lands inside (or on the corner of) the wall", b7 ~= nil and b7.name == VEHICLE
        and dist(b7.position, s.j7spot) >= 1
        and not (b7.position.x == s.j7spot.x and b7.position.y == s.j7spot.y)
        and not game.surfaces[1].entity_prototype_collides(LEG, b7.position, false),
        b7 and line(b7.position))
  L("J7 landed at", b7 and line(b7.position), "planned", line(s.j7spot))
end)
at(95, function(s)                                    -- every lane but the crowd is down
  local st = jstate()
  check("J1-J10 and the bank: nothing left in the air or drawn", st.arcs == 0 and st.drawn == 0, line(st))
end)

-- J8: TELEPORT MODE ------------------------------------------------------------------------
at(16, function(s)
  check("J8 jump_mode reads arc by default", remote.call(SAY, "jump_mode") == "arc")
  remote.call(SAY, "jump_mode", "teleport")
  local from = s.j8.position
  local r = jump(s.j8)
  local b = body_at({x = from.x + 8, y = from.y})
  check("J8 teleport mode: landed on the same tick, nothing drawn, nothing in the air",
        r.jumped and b ~= nil and b.name == VEHICLE and jstate().drawn == jstate().arcs * 3, line(r))
  check("J8 ... and on_tick owes it nothing", jstate(b).arc == nil)
  remote.call(SAY, "jump_mode", "arc")
  check("J8 back to arc", remote.call(SAY, "jump_mode") == "arc")
end)

-- J9: A BREAK, THROUGH breakage.on_landing ---------------------------------------------------
at(18, function(s)
  set("jamaltron-leg-break-percent", 100)
  s.j9from = s.j9.position
  check("J9 jumps", jump(s.j9).jumped)
  set("jamaltron-leg-break-percent", 0)             -- read at touchdown: put it back then
end)
at(47, function(s) set("jamaltron-leg-break-percent", 100) end)
at(48, function(s)
  local b = body_at({x = s.j9from.x + 8, y = s.j9from.y})
  check("J9 at 100% he lands BEACHED - one swap, airborne to beached", b ~= nil and b.name == BEACHED,
        b and b.name)
  s.j9b = b
  if b then log("HARNESS need jamaltron speech " .. b.unit_number .. " legs_break[.]") end
  if b then log("HARNESS never jamaltron speech " .. b.unit_number .. " land[.]") end
  set("jamaltron-leg-break-percent", 0)
end)

at(49, function(s)
  local ok, ids, why = wreck_kept(s.j9b)
  check("W J9's break drew his legs: the set his record keeps, all on him", ok, why)
  s.j9wreck = ids
  L("W objects per beached Jamal", #ids)
end)

-- J10: A FOLLOWER --------------------------------------------------------------------------
at(60, function(s)
  local r = jump(s.j9b)
  check("J9 beached, the key does nothing and says nothing", r.jumped == false and r.why == "not_vehicle"
        and r.said == nil, line(r))
end)

at(20, function(s)
  local dest = s.j10.autopilot_destination
  L("J10 a driven follower's autopilot_destination:", line(dest))
  local r = jump(s.j10)
  if r.jumped then
    s.j10from = s.j10.valid and s.j10.position or nil
    check("J10 accepted with no destination set: the follow must not survive the takeoff", dest == nil, line(r))
  else
    check("J10 a follower with a destination is refused: autopilot", r.why == "autopilot" and dest ~= nil, line(r))
  end
end)

-- THE REFUSALS -----------------------------------------------------------------------------
at(30, function(s)
  local want = {{"r_none", "no_driver"}, {"r_auto", "autopilot"}, {"r_lava", "lava"}, {"r_void", "void"},
                {"r_wall", "blocked"}, {"r_tree", "blocked"}}
  for _, w in ipairs(want) do
    local e = s[w[1]]
    local was, unit = e.position, e.unit_number
    local r = jump(e)
    check("refusal " .. w[1] .. ": " .. w[2], r.jumped == false and r.why == w[2], line(r))
    check("refusal " .. w[1] .. " says its reason's row or an any row", r.said == nil
          or refusal_row(r.said, w[2]), line(r))
    -- r_auto walks to its destination on its own: the same body, not the same place
    check("refusal " .. w[1] .. " moved nothing: the same walking body, where it stood",
          e.valid and e.unit_number == unit and e.name == VEHICLE
          and (w[1] == "r_auto" or (e.position.x == was.x and e.position.y == was.y)), line(e.position))
  end
  check("the tree is one tree: a foot collides with it (chotchki's open call)",
        game.surfaces[1].entity_prototype_collides(LEG, s.tree.position, false))
  s.r_pass_at = s.r_pass.position
  local r = remote.call(H, "jump", s.r_pass, s.r_pass_p)
  check("refusal r_pass: the PASSENGER presses - no_driver", r.jumped == false and r.why == "no_driver", line(r))
  check("refusal r_pass says a no_driver or an any row", r.said == nil or refusal_row(r.said, "no_driver"), line(r))
  check("refusal r_pass moved nothing, and both still ride", s.r_pass.valid and s.r_pass.position.x == s.r_pass_at.x
        and s.r_pass.get_driver() == s.r_pass_d and s.r_pass.get_passenger() == s.r_pass_p)
end)
at(38, function(s)
  local r = remote.call(H, "jump", s.r_pass, s.r_pass_d)
  check("r_pass: his DRIVER's press, through the same character comparison, jumps", r.jumped == true, line(r))
end)
at(68, function(s)
  local b = body_at({x = s.r_pass_at.x + 8, y = s.r_pass_at.y})
  check("r_pass: lands with both - driver and passenger", b ~= nil and b.name == VEHICLE and b.get_driver() == s.r_pass_d
        and b.get_passenger() == s.r_pass_p, b and b.name)
end)
at(32, function(s)
  -- a refusal is spoken once per REFUSE_GAP: the second press is silent, the reason is not
  local r = jump(s.r_wall)
  check("a second press inside the gap: still blocked, silent", r.why == "blocked" and r.said == nil, line(r))
end)
at(34, function(s)
  set("jamaltron-jump-distance", 16)
  local ri = jump(s.r_islet)
  check("STRADDLE: 14 tiles of water to a 3x3 islet is refused as the water", ri.why == "water", line(ri))
  local rb = jump(s.r_bank)
  check("STRADDLE: 14 tiles of water to a far bank is a jump", rb.jumped == true, line(rb))
  set("jamaltron-jump-distance", 8)
  s.bankfrom = {x = 340.5, y = ROW_R + 0.5}
end)
at(90, function(s)
  -- 1.5: 50 ticks after touchdown at the water's edge his legs have re-laid and moved him (0.8)
  local b = body_at({x = s.bankfrom.x + 16, y = s.bankfrom.y}, 1.5)
  check("STRADDLE: ... and lands on the bank 16 tiles on", b ~= nil and b.name == VEHICLE, line(s.bankfrom))
end)
at(36, function(s)
  -- the platform (Space Age): a platform surface of our own
  local ok, err = pcall(function()
    local plat = game.forces.player.create_space_platform{name = "jump-harness", planet = "nauvis",
                                                         starter_pack = "space-platform-starter-pack"}
    plat.apply_starter_pack()
    local surf = plat.surface
    local tiles = {}
    for x = -15, 15 do for y = 8, 30 do tiles[#tiles + 1] = {name = "space-platform-foundation", position = {x, y}} end end
    surf.set_tiles(tiles)
    local e = surf.create_entity{name = VEHICLE, position = {0.5, 20.5}, force = "player"}
    local c = surf.create_entity{name = "character", position = {0.5, 23.5}, force = "player"}
    assert(e and c, "no jamaltron or character on a platform")
    e.set_driver(c)
    local r = jump(e)
    check("refusal on a space platform: platform", r.jumped == false and r.why == "platform", line(r))
  end)
  if not ok then
    check("the platform lane ran (Space Age is loaded in the benchmark stage)", false, err)
  end
end)

-- THE LAKE: 48 sharks, one roll each --------------------------------------------------------
at(50, function(s)
  local reasons, rows, water_rows, moved = {}, 0, 0, 0
  for _, e in ipairs(s.water) do
    local was, unit = e.position, e.unit_number
    local r = jump(e)
    if not (e.valid and e.unit_number == unit and e.name == VEHICLE and e.position.x == was.x
            and e.position.y == was.y) then
      moved = moved + 1
    end
    reasons[r.why or "jumped"] = (reasons[r.why or "jumped"] or 0) + 1
    if r.said then
      rows = rows + 1
      if not refusal_row(r.said, "water") then check("a lake refusal said " .. r.said, false, r.said) end
      if r.said == "jump_refused.08" then water_rows = water_rows + 1 end
    end
  end
  L("lake refusals", line(reasons), "rows", rows, "jump_refused.08", water_rows)
  check("48 hops into a lake: 48 refused as water", reasons.water == 48, line(reasons))
  check("... and not one of the 48 moved, swapped or left the ground", moved == 0, moved)
  local eligible = pick.eligible(lines.pools.jump_refused, tostring(settings.global["jamaltron-verbosity"].value),
                                 "water", {}, nil)
  local has = false
  for _, row in ipairs(eligible) do if row.id == "jump_refused.08" then has = true end end
  check("the water row is eligible on a water refusal (forced twin of the roll below)", has)
  log("HARNESS need jamaltron speech [0-9]+ jump_refused[.]08")
  local st = remote.call(H, "state", s.water[1])
  check("a water refusal latches the shore episode (one episode, R6)", st and st.stall_tick == game.tick, line(st))
end)

-- TWENTY AT ONCE, profiled -----------------------------------------------------------------
at(100, function(s)
  local p = helpers.create_profiler()
  local jumped = 0
  for _, e in ipairs(s.crowd) do
    if jump(e).jumped then jumped = jumped + 1 end
  end
  p.stop()
  log({"", "JUMP cost: 20 takeoffs (swap + jump line + 3 render objects each, via remote) ", p})
  check("20 jamaltrons take off in one tick", jumped == 20, jumped)
  s.crowd_from = {}
  for i = 0, 19 do s.crowd_from[#s.crowd_from + 1] = {x = i * 15 + 0.5, y = ROW_C + 0.5} end
end)
at(115, function(s)
  local st = jstate()
  check("20 in the air, 60 render objects", st.arcs == 20 and st.drawn == 60, line(st))
  log({"", "JUMP cost: 20 arcs x 10 re-flies (divide by 10 for one tick) ", remote.call(H, "jump_cost", 10)})
end)
at(128, function(s) s.quiet_p = helpers.create_profiler() end)
at(129, function(s)
  s.quiet_p.stop()
  log({"", "JUMP cost: one whole tick with 20 arcs flying (engine included) ", s.quiet_p})
  s.land_p = helpers.create_profiler()
end)
at(130, function(s)                                    -- touchdown for all twenty
  s.land_p.stop()
  log({"", "JUMP cost: the whole tick 20 land on (engine included) ", s.land_p})
  local landed = 0
  for _, from in ipairs(s.crowd_from) do
    local b = body_at({x = from.x + 8, y = from.y})
    if b and b.name == VEHICLE then landed = landed + 1 end
  end
  check("all 20 land on their spots", landed == 20, landed)
  local st = jstate()
  check("... and nothing is left in the air or drawn", st.arcs == 0 and st.drawn == 0, line(st))
end)
at(200, function(s) s.idle_p = helpers.create_profiler() end)
at(201, function(s)
  s.idle_p.stop()
  log({"", "JUMP cost: a whole tick with nothing in the air (engine baseline) ", s.idle_p})
end)

-- JD: THE DISTANCE SETTING ---------------------------------------------------------------------
at(440, function(s)
  set("jamaltron-jump-distance", 5)
  s.jdfrom = s.jd.position
  check("JD jumps at jamaltron-jump-distance 5", jump(s.jd).jumped)
  set("jamaltron-jump-distance", 8)                 -- read at takeoff: put it back straight away
end)
at(466, function(s)                                 -- 5 tiles: 1.875 up, 24 ticks
  local b = body_at({x = s.jdfrom.x, y = s.jdfrom.y - 5})
  check("JD standing, torso north: lands exactly 5 tiles NORTH, the vehicle", b ~= nil and b.name == VEHICLE,
        line(s.jdfrom))
  check("JD ... and not 8", body_at({x = s.jdfrom.x, y = s.jdfrom.y - 8}, 1) == nil)
end)

-- L1, L2: breakage.on_landing ALONE, profiled (no arc, no remote jump) -------------------------
at(445, function(s)
  s.l1a = remote.call(H, "swap", s.l1, AIRBORNE, {reason = "takeoff", autopilot = false}).body
  s.l2a = remote.call(H, "swap", s.l2, AIRBORNE, {reason = "takeoff", autopilot = false}).body
  check("L1 L2 in the airborne body", s.l1a and s.l1a.name == AIRBORNE and s.l2a and s.l2a.name == AIRBORNE)
end)
at(446, function(s)
  s.l1spot = {x = s.l1a.position.x + 8, y = s.l1a.position.y}
  percent(100)
  local p = helpers.create_profiler()
  local r = remote.call(H, "land", s.l1a, s.l1spot, {tick = game.tick, distance = 8})
  p.stop()
  percent(0)
  log({"", "JUMP cost: one BROKEN landing via remote (roll, swap to beached, health, alert, legs_break line) ", p})
  check("L1 at 100%: broke, beached, on the spot", r.outcome == "broke" and r.body and r.body.name == BEACHED
        and r.body.position.x == s.l1spot.x, line(r.outcome))
  s.l1b = r.body
end)
at(447, function(s)
  s.l2spot = {x = s.l2a.position.x + 8, y = s.l2a.position.y}
  local p = helpers.create_profiler()
  local r = remote.call(H, "land", s.l2a, s.l2spot, {tick = game.tick, distance = 8})
  p.stop()
  log({"", "JUMP cost: one CLEAN landing via remote (roll, swap to the vehicle, thud, land line) ", p})
  check("L2 at 0%: held, the vehicle, on the spot", r.outcome == "held" and r.body and r.body.name == VEHICLE
        and r.body.position.x == s.l2spot.x, line(r.outcome))
  check("L2 says a land line", r.body and row_of(r.body):match("^land%.") ~= nil, r.body and row_of(r.body))
end)
at(450, function(s)
  s.l1b.health = s.l1b.max_health
  local p = helpers.create_profiler()
  remote.call(H, "repaired", s.l1b)
  p.stop()
  log({"", "JUMP cost: one REPAIR via the repair event's handler (swap back, repaired line, alert down) ", p})
  local up = body_at(s.l1spot)
  check("L1 repaired in the event's handler: walking body on the spot, repaired line", not s.l1b.valid
        and up ~= nil and up.name == VEHICLE and row_of(up):match("^repaired%.") ~= nil, up and row_of(up))
end)

-- AM: D.7.3 - A REAL BREAK DISARMS HIM AND KEEPS EVERY ROUND ----------------------------------
-- breakage.on_landing at 100% (L1's path), a driver seated throughout. Four slots that would show
-- any slip (11, 22, 33 RARE, 44 with a 57-round partial magazine) and gun 3 selected. Beached for
-- 240 ticks with the driver shooting a biter 7 tiles east every tick: no stream, no
-- jamaltron-fired, no damage, not a round spent. Repaired: every slot and the selected gun back
-- exactly, and the same driver's first volley burns it, proving the scripted trigger works. The
-- biter sits EAST because his own splash reaches him on every other bearing (D.7.4), and the END
-- check wants no on_entity_damaged on a body of his.
local AM_AT, AM_REPAIR, AM_END = 150, 400, 470
local function slots(e)
  local inv, out = e.get_inventory(AMMO), {}
  for i = 1, #inv do
    local st = inv[i]
    out[i] = st.valid_for_read and (st.name .. "x" .. st.count .. "@" .. st.quality.name .. "+" .. st.ammo) or "-"
  end
  return table.concat(out, " ")
end
local function am_rounds(e)
  local inv, n = e.get_inventory(AMMO), 0
  for i = 1, #inv do
    local st = inv[i]
    if st.valid_for_read then n = n + (st.count - 1) * st.prototype.magazine_size + st.ammo end
  end
  return n
end
local function am_fired(e) return storage.am_fired and storage.am_fired[e.unit_number] or 0 end
at(2, function(s)
  s.am, s.amc = driven(380, ROW_B - 20, 0.25)
  local inv = s.am.get_inventory(AMMO)
  inv[1].set_stack{name = "flamethrower-ammo", count = 11}
  inv[2].set_stack{name = "flamethrower-ammo", count = 22}
  inv[3].set_stack{name = "flamethrower-ammo", count = 33, quality = "rare"}
  inv[4].set_stack{name = "flamethrower-ammo", count = 44}
  inv[4].ammo = 57
  s.am.selected_gun_index = 3
  s.am_slots0 = slots(s.am)
  check("AM loaded: 11, 22, 33 rare, 44 with 57 in the magazine, gun 3",
        s.am_slots0 == "flamethrower-ammox11@normal+100 flamethrower-ammox22@normal+100 "
        .. "flamethrower-ammox33@rare+100 flamethrower-ammox44@normal+57" and s.am.selected_gun_index == 3,
        s.am_slots0 .. " gun " .. s.am.selected_gun_index)
end)
at(AM_AT - 2, function(s)
  s.ama = remote.call(H, "swap", s.am, AIRBORNE, {reason = "takeoff", autopilot = false}).body
end)
at(AM_AT, function(s)
  s.amspot = {x = s.ama.position.x, y = s.ama.position.y}
  percent(100)
  local r = remote.call(H, "land", s.ama, s.amspot, {tick = game.tick, distance = 8})
  percent(0)
  local b = r.body
  check("AM at 100%: broke, beached, his driver still in", r.outcome == "broke" and b and b.name == BEACHED
        and b.get_driver() == s.amc, line(r.outcome))
  s.amb = b
  check("AM beached: every ammo slot exact, gun 3 still selected", b and slots(b) == s.am_slots0
        and b.selected_gun_index == 3, b and (slots(b) .. " gun " .. tostring(b.selected_gun_index)))
  s.amt = game.surfaces[1].create_entity{name = "big-biter", force = "enemy",
                                         position = {s.amspot.x + 7, s.amspot.y}}
  s.amt.disabled_by_script = true
  s.am_streams = 0
end)
at(AM_AT + 2, function(s)
  check("AM beached (t+2, the late writes in): every ammo slot exact", slots(s.amb) == s.am_slots0,
        slots(s.amb))
end)
during(AM_AT + 1, AM_REPAIR - 10, function(s)
  s.amc.shooting_state = {state = defines.shooting.shooting_enemies, position = s.amt.position}
  s.am_streams = s.am_streams + #game.surfaces[1].find_entities_filtered{type = "stream",
                                                                        position = s.amspot, radius = 12}
end)
at(AM_REPAIR - 9, function(s)
  s.amc.shooting_state = {state = defines.shooting.not_shooting}
  L("AM beached, driver shooting 240 ticks: fired", am_fired(s.amb), "streams", s.am_streams, "biter",
    s.amt.valid and s.amt.health, "slots", slots(s.amb), "gun", s.amb.selected_gun_index)
  check("AM BEACHED, a driver shooting every tick: no stream, no jamaltron-fired, the biter untouched",
        am_fired(s.amb) == 0 and s.am_streams == 0 and s.amt.valid and s.amt.health == s.amt.max_health,
        am_fired(s.amb) .. " fired, " .. s.am_streams .. " streams")
  check("AM ... and not a round spent: every slot exact", slots(s.amb) == s.am_slots0, slots(s.amb))
  check("AM ... his driver still seated", s.amb.get_driver() == s.amc)
  s.am_gun = s.amb.selected_gun_index                 -- a driver's trigger may cycle it: carried, not pinned
end)
at(AM_REPAIR, function(s)
  s.amb.health = s.amb.max_health
  remote.call(H, "repaired", s.amb)
  local up = body_at(s.amspot)
  s.amu = up
  check("AM repaired: the vehicle, on the spot, his driver in", not s.amb.valid and up ~= nil
        and up.name == VEHICLE and up.get_driver() == s.amc, up and up.name)
  check("AM repaired: every ammo slot exact and the selected gun carried", up and slots(up) == s.am_slots0
        and up.selected_gun_index == s.am_gun, up and (slots(up) .. " gun " .. up.selected_gun_index
        .. " vs " .. tostring(s.am_gun)))
  s.am_r0 = up and am_rounds(up)
end)
during(AM_REPAIR + 1, AM_END - 1, function(s)
  if s.amt.valid then
    s.amc.shooting_state = {state = defines.shooting.shooting_enemies, position = s.amt.position}
  end
end)
at(AM_END, function(s)
  s.amc.shooting_state = {state = defines.shooting.not_shooting}
  local up = s.amu
  L("AM repaired, driver shooting 69 ticks: fired", am_fired(up), "rounds", s.am_r0, "->", am_rounds(up),
    "biter", s.amt.valid and s.amt.health or "dead")
  check("AM the REPAIRED Jamal fires for the same driver: a stream, rounds spent, the biter burned",
        am_fired(up) > 0 and am_rounds(up) < s.am_r0 and (not s.amt.valid or s.amt.health < s.amt.max_health),
        am_fired(up) .. " fired")
  if s.amt.valid then s.amt.destroy() end
end)
script.on_event("jamaltron-fired", function(event)
  local src = event.source_entity
  if src and src.valid and src.unit_number then
    storage.am_fired = storage.am_fired or {}
    storage.am_fired[src.unit_number] = (storage.am_fired[src.unit_number] or 0) + 1
  end
end)

-- B: THE LOOP --------------------------------------------------------------------------------
at(B0, function(s)
  s.bkit = kit_of(s.b)
  s.bfrom, s.bunit0 = s.b.position, s.b.unit_number
  s.p1from, s.p2from = s.p1.position, s.p2.position
  s.bc.walking_state = {walking = true, direction = defines.direction.east}
  local p = helpers.create_profiler()
  local r = jump(s.b)
  p.stop()
  log({"", "JUMP cost: one takeoff via remote (checks, swap to airborne, jump line, dust, 3 render objects) ", p})
  check("B jumps (held east, a full kit)", r.jumped, line(r))
  check("P1 and P2 jump in the same tick", jump(s.p1).jumped and jump(s.p2).jumped)
end)
at(B0 + 10, function(s)
  local st = jstate()
  check("B P1 P2 all three in the air at once: 3 arcs, 9 render objects", st.arcs == 3 and st.drawn == 9
        and animations() == 9, line(st) .. " animations " .. animations())
end)
at(BREAK_AT - 1, function(s)
  percent(100)
  s.dmg_before = storage.damaged or 0
  s.break_p = helpers.create_profiler()
end)
at(BREAK_AT, function(s)
  s.break_p.stop()
  log({"", "JUMP cost: the whole tick three land BROKEN on (engine included) ", s.break_p})
  percent(0)
  local tick = game.tick
  local spot = {x = s.bfrom.x + 8, y = s.bfrom.y}
  local b = body_at(spot)
  s.bb, s.bspot, s.btick = b, spot, tick
  check("B lands BEACHED, exactly on the spot 8 tiles east", b ~= nil and b.name == BEACHED
        and b.position.x == spot.x and b.position.y == spot.y, b and (b.name .. " " .. line(b.position)))
  if not b then return end
  check("B his driver is still seated", b.get_driver() == s.bc)
  check("B facing the way he flew (torso east)", near(b.torso_orientation, 0.25, 1e-5), b.torso_orientation)
  check("B TOOK THE DAMAGE: half his bar from a full one", near(b.get_health_ratio(), 0.5, 1e-6), b.get_health_ratio())
  check("B ... written, not dealt: no on_entity_damaged on the landing tick", (storage.damaged or 0) == s.dmg_before,
        (storage.damaged or 0) - s.dmg_before)
  local cs = b.custom_status
  check("B the beached custom status, red", cs ~= nil and type(cs.label) == "table" and cs.label[1] == "jamaltron-status.beached"
        and cs.diode == defines.entity_status_diode.red, line(cs))
  local st = speech(b)
  check("B says legs_break on the landing, fork self, {N} = 1", st and st.last_id:match("^legs_break%.") ~= nil
        and st.fork == "self" and st.breaks == 1, line(st))
  s.b_last_tick, s.b_break_row = st and st.last_tick, st and st.last_id
  local k = kept(b)
  check("B kept: the first apology 12-18 s out (15 s +-20%, normal)", k.kept and k.flop_at >= tick + 720
        and k.flop_at <= tick + 1080, line(k))
  check("B his alert is up, re-issued once he has settled (3 s) and every 10 s after (bookkeeping - "
        .. "headless has no player to hold one)", k.alert_at == tick + 180, line(k))
  s.b_alert0, s.b_flop_at = k.alert_at, k.flop_at
  s.flops, s.attempts, s.others = {}, {}, {}
  local p1, p2 = body_at({x = s.p1from.x + 8, y = s.p1from.y}), body_at({x = s.p2from.x + 8, y = s.p2from.y})
  check("P1 P2 landed beached in the same tick, each his own", p1 and p2 and p1.name == BEACHED and p2.name == BEACHED
        and p1 ~= p2)
  s.p1b, s.p2b = p1, p2
  check("four kept map-wide: J9, B, P1, P2", kept().beached == 4, line(kept()))
  local js = jstate()
  check("the arcs' render objects are all gone after landing", js.arcs == 0 and js.drawn == 0 and animations() == 0,
        line(js) .. " animations " .. animations())
  for _, e in ipairs({b, p1, p2}) do
    if e then log("HARNESS need jamaltron speech " .. e.unit_number .. " legs_break[.]") end
  end
  log("HARNESS need jamaltron speech " .. b.unit_number .. " flopping[.]")
  log("HARNESS never jamaltron speech " .. b.unit_number .. " (land|idle|moving|built|enter|exit|damaged)[.]")
end)
at(BREAK_AT + 2, function(s) same_kit("B beached (t+2)", s.bkit, s.bb) end)
at(BREAK_AT + 1, function(s)
  local sets = {}
  for _, who in ipairs({"bb", "p1b", "p2b"}) do
    local ok, ids, why = wreck_kept(s[who])
    check("W " .. who .. " broke in the same tick as two others: his own set of legs, on him", ok, why)
    sets[who] = ids
  end
  s.bwreck, s.p2wreck = sets.bb, sets.p2b
  -- the same tick, three breaks off the map's generator: three layouts (count, then offsets)
  local function sig(e)
    local out = {}
    for _, id in ipairs(wreck_on(e)) do
      local o = rendering.get_object_by_id(id)
      local off = o and o.target.offset
      out[#out + 1] = off and string.format("%.3f,%.3f", off.x or off[1], off.y or off[2]) or "?"
    end
    return table.concat(out, ";")
  end
  local a, b, c = sig(s.bb), sig(s.p1b), sig(s.p2b)
  check("W three breaks in one tick lay three different wrecks", a ~= b and b ~= c and a ~= c)
end)

-- W held for ten seconds, written every tick as a player's key would be: not one step.
during(BREAK_AT + 1, BREAK_AT + 600, function(s)
  s.bc.walking_state = {walking = true, direction = defines.direction.north}
end)
at(BREAK_AT + 601, function(s)
  local moved = dist(s.bb.position, s.bspot)
  check("B beached with W held 10 s: moved 0 tiles, speed 0", s.bb.valid and moved < 1e-6 and s.bb.speed == 0,
        "moved " .. moved .. " speed " .. s.bb.speed)
  check("B still beached, still kept", s.bb.name == BEACHED and kept(s.bb).kept)
end)

-- Every tick he lies there: each NEW utterance (a changed last_tick - a chain's follow-up changes
-- only last_id) and each apology attempt (a changed flop_at).
during(BREAK_AT + 1, REPAIR_AT - 1, function(s, dt)
  local b = s.bb
  if not b.valid then return end
  local st = speech(b)
  if st and st.last_tick ~= s.b_last_tick then
    s.b_last_tick = st.last_tick
    local list = st.last_id:match("^flopping%.") and s.flops or s.others
    list[#list + 1] = {dt = dt, tick = game.tick, id = st.last_id}
  end
  local k = kept(b)
  if k.flop_at ~= s.b_flop_at then
    s.attempts[#s.attempts + 1] = {tick = game.tick, next = k.flop_at}
    s.b_flop_at = k.flop_at
  end
end)
at(BREAK_AT + 700, function(s)
  local k = kept(s.bb)
  check("B his alert was re-issued after its 10 s", k.alert_at > s.b_alert0, line(k) .. " first " .. s.b_alert0)
end)

-- P2 dies beached; P1 is healed and the BOT path - the 60-tick poll, no event - stands him up.
at(BREAK_AT + 70, function(s) s.p2unit = s.p2b.unit_number s.p2b.die() end)
at(BREAK_AT + 71, function(s)
  check("P2 died beached: its record and alert went with it", not s.p2b.valid and kept().beached == 3, line(kept()))
  check("W P2 died beached: not one of his broken legs is left drawn", #s.p2wreck > 0 and alive(s.p2wreck) == 0,
        alive(s.p2wreck) .. " of " .. #s.p2wreck)
  local cs = census()
  check("P2 ... and no speech record on a dead body", cs.dead == 0 and cs.mismatched == 0, line(cs))
end)
at(BREAK_AT + 710, function(s)
  s.p1spot = s.p1b.position
  s.p1b.health = s.p1b.max_health
  s.p1_healed = game.tick
end)
during(BREAK_AT + 711, BREAK_AT + 790, function(s)
  if not s.p1b.valid and not s.p1_up then s.p1_up = game.tick end
end)
at(BREAK_AT + 791, function(s)
  check("P1 the bot path: up within one poll of a full bar", s.p1_up ~= nil and s.p1_up - s.p1_healed <= 60,
        tostring(s.p1_up) .. " healed " .. s.p1_healed)
  local up = body_at(s.p1spot)
  check("P1 a walking jamaltron where he lay, his driver seated", up ~= nil and up.name == VEHICLE
        and up.get_driver() == s.p1c, up and up.name)
  if not up then return end
  local st = speech(up)
  check("P1 repaired said, fork cleared, {N} kept at 1", st and st.last_id:match("^repaired%.") ~= nil
        and st.fork == nil and st.breaks == 1, line(st))
  check("P1 no status, not kept", up.custom_status == nil and not kept(up).kept)
  log("HARNESS need jamaltron speech " .. up.unit_number .. " repaired[.]")
end)

-- The flops, judged before the repair: at DEFAULT settings (normal, 15 s apologies, 10 s speech
-- cooldown) every attempt is 12-18 s after the last, and only legs_break.18 may eat one.
at(REPAIR_AT - 1, function(s)
  L("B flops", line(s.flops), "attempts", line(s.attempts), "other lines", line(s.others), "break row", s.b_break_row)
  check("B said nothing but flops while beached (a chain's punchline aside)", #s.others == 0, line(s.others))
  local timer, prev = true, s.btick
  for _, a in ipairs(s.attempts) do
    local gap = a.next - a.tick
    if gap < 719 or gap > 1081 or a.tick - prev < 719 then timer = false end
    prev = a.tick
  end
  check("B at least three apology attempts in " .. BEACHED_FOR / 60 .. " s", #s.attempts >= 3, #s.attempts)
  check("B every attempt on the apology timer: 12-18 s apart", timer, line(s.attempts))
  local skip = s.b_break_row == "legs_break.18" and 1 or 0
  check("B one flop said per attempt, less legs_break.18's one skipped", #s.flops >= #s.attempts - skip
        and #s.flops <= #s.attempts, #s.flops .. " of " .. #s.attempts .. " skip " .. skip)
  check("B at least two flops said", #s.flops >= 2, #s.flops)
  local spaced = true
  for i = 2, #s.flops do
    if s.flops[i].tick - s.flops[i - 1].tick < 600 then spaced = false end
  end
  check("B no two flops inside the 10 s speech cooldown", spaced, line(s.flops))
end)

-- The REPAIR EVENT's path: the handler control.lua registers, called with the event it reads.
at(REPAIR_AT, function(s)
  local b = s.bb
  b.health = b.max_health * 0.9
  remote.call(H, "repaired", b)
  check("B a repair short of full: still beached, still kept", b.valid and b.name == BEACHED and kept(b).kept)
  b.health = b.max_health
  local p = helpers.create_profiler()
  remote.call(H, "repaired", b)
  p.stop()
  log({"", "JUMP cost: B's repair via the repair event's handler (a full kit) ", p})
  check("B repaired to full: the beached body is gone", not b.valid)
  local up = body_at(s.bspot)
  s.b2 = up
  check("B a WALKING jamaltron exactly where he lay", up ~= nil and up.name == VEHICLE and up.position.x == s.bspot.x
        and up.position.y == s.bspot.y, up and (up.name .. " " .. line(up.position)))
  if not up then return end
  local st = speech(up)
  check("B says repaired; the fork is cleared; {N} kept at 1", st and st.last_id:match("^repaired%.") ~= nil
        and st.fork == nil and st.breaks == 1, line(st))
  check("B not kept any more: the alert is down (bookkeeping)", not kept(up).kept and kept().beached == 1, line(kept()))
  check("B no custom status, full health, facing east", up.custom_status == nil and near(up.get_health_ratio(), 1)
        and near(up.torso_orientation, 0.25, 1e-5), line(up.custom_status))
  check("B his driver is back in the walking body", up.get_driver() == s.bc)
  log("HARNESS need jamaltron speech " .. up.unit_number .. " repaired[.]")
end)
at(REPAIR_AT + 2, function(s) same_kit("B repaired (t+2)", s.bkit, s.b2) end)
at(REPAIR_AT + 1, function(s)
  check("W B repaired: his broken legs went with the beached body, none on the walking one",
        #s.bwreck > 0 and alive(s.bwreck) == 0 and s.b2 and #wreck_on(s.b2) == 0,
        alive(s.bwreck) .. " of " .. #s.bwreck)
end)
during(REPAIR_AT + 1, REPAIR_AT + 60, function(s)
  s.bc.walking_state = {walking = true, direction = defines.direction.north}
end)
at(REPAIR_AT + 61, function(s)
  local moved = dist(s.b2.position, s.bspot)
  check("B repaired walks again: W held a second moves him", moved > 0.5, moved)
  s.bc.walking_state = {walking = false, direction = defines.direction.north}
end)

-- A second break, repaired by the poll: {N} counts it.
at(AGAIN_AT - 1, function(s) s.bc.walking_state = {walking = true, direction = defines.direction.east} end)
at(AGAIN_AT, function(s)
  s.b2from = s.b2.position
  local r = jump(s.b2)
  check("B jumps again", r.jumped, line(r))
end)
at(AGAIN_AT + 29, function(s) percent(100) end)
at(AGAIN_AT + 30, function(s)
  percent(0)
  s.bc.walking_state = {walking = false, direction = defines.direction.east}
  local b = body_at({x = s.b2from.x + 8, y = s.b2from.y})
  s.bb2 = b
  check("B broken again: beached", b ~= nil and b.name == BEACHED, b and b.name)
  local st = b and speech(b)
  check("B {N} = 2 - the count rode every body he has been", st and st.breaks == 2
        and st.last_id:match("^legs_break%.") ~= nil, line(st))
end)
at(AGAIN_AT + 40, function(s)
  s.bb2spot = s.bb2.position
  s.bb2.health = s.bb2.max_health
end)
at(AGAIN_AT + 101, function(s)
  local up = body_at(s.bb2spot)
  check("B the poll stood him up the second time", not s.bb2.valid and up ~= nil and up.name == VEHICLE,
        up and up.name)
  local st = up and speech(up)
  check("B repaired again, {N} still 2, fork cleared", st and st.last_id:match("^repaired%.") ~= nil
        and st.breaks == 2 and st.fork == nil, line(st))
  check("B his driver rode all of it", up and up.get_driver() == s.bc)
end)

-- X: ANOTHER MOD PARKS HIM (J9, beached since dt 48) ------------------------------------------
---What Spidertron Enhancements does: its own body where he stands, the community event, the old
---one destroyed.
local function park(old, name)
  local new = old.surface.create_entity{name = name, position = old.position, force = old.force}
  script.raise_event("on_spidertron_replaced", {old_spidertron = old, new_spidertron = new})
  old.destroy()
  return new
end
at(600, function(s)
  local count = kept().beached
  s.x1 = park(s.j9b, "spidertron")
  local k = kept(s.x1)
  check("X parked in another mod's body: his break record follows him, one record not two",
        k.kept and k.beached == count, line(k) .. " before " .. count)
  local st = speech(s.x1)
  check("X ... and so does his speech record ({N} 1, fork self)", st and st.breaks == 1 and st.fork == "self", line(st))
  s.x1_flop_at = k.flop_at
end)
at(601, function(s)
  check("W X parked in a body that is not beached: J9's legs gone with the beached body, none on the dummy",
        #s.j9wreck > 0 and alive(s.j9wreck) == 0 and #wreck_on(s.x1) == 0, alive(s.j9wreck) .. " " .. #wreck_on(s.x1))
  local cs = census()
  check("X the old beached body forgot nothing it should keep", cs.dead == 0 and cs.mismatched == 0, line(cs))
end)
at(600 + 1800, function(s)                          -- 30 s parked: two apologies' worth
  local k = kept(s.x1)
  check("X parked 30 s: still kept, the apology clock never ran (no flops in a body not beached)",
        k.kept and k.flop_at == s.x1_flop_at, line(k))
  s.x1.health = s.x1.max_health                     -- full health in the parking body: not a repair
end)
at(600 + 1901, function(s)
  local ok, ids, why = wreck_kept(s.j9b)
  check("W X parked back in a beached body: a fresh set of legs on it", ok, why)
  s.j9wreck = ids
end)
at(600 + 1900, function(s)
  check("X full health while parked does not stand him up", s.x1.valid and kept(s.x1).kept)
  s.j9b = park(s.x1, BEACHED)
  s.j9b.health = s.j9b.max_health * 0.5             -- another mod's fresh body starts full
  local k = kept(s.j9b)
  check("X back in a beached body: kept, and his alert re-issued on it", k.kept and k.alert_at == game.tick + 600,
        line(k))
  local st = speech(s.j9b)
  check("X ... his speech record came home ({N} 1, fork self)", st and st.breaks == 1 and st.fork == "self", line(st))
end)

-- W: J9, beached again since 2500, moved beached -> beached by another mod, then onto a beached
-- body that is ALREADY kept, then cloned.
at(2600, function(s)
  local before, count = s.j9wreck, kept().beached
  s.j9b = park(s.j9b, BEACHED)
  s.j9b.health = s.j9b.max_health * 0.5
  local ok, ids, why = wreck_kept(s.j9b)
  check("W beached -> beached: one fresh set on the new body", ok, why)
  check("W ... none left of the old body's", #before > 0 and alive(before) == 0, alive(before))
  check("W ... one record, not two", kept().beached == count, kept().beached .. " vs " .. count)
  s.j9wreck = ids
end)
at(2700, function(s)
  local surface = s.j9b.surface
  local spot = surface.find_non_colliding_position(BEACHED, {x = s.j9b.position.x, y = s.j9b.position.y + 12}, 20, 0.5)
  local c = surface.create_entity{name = BEACHED, position = spot, force = s.j9b.force}
  check("W a second beached body kept first", c ~= nil and remote.call(H, "keep", c) == true)
  local count = kept().beached
  local _, cids = wreck_kept(c)
  local old = s.j9wreck
  script.raise_event("on_spidertron_replaced", {old_spidertron = s.j9b, new_spidertron = c})
  s.j9b.destroy()
  s.j9b = c
  local ok, ids, why = wreck_kept(c)
  check("W moved onto a body already kept: ONE set on it, the one it had", ok and line(ids) == line(cids), why)
  check("W ... J9's own set gone with his old body, one record where there were two",
        alive(old) == 0 and kept().beached == count - 1, alive(old) .. " " .. kept().beached .. " vs " .. count)
  s.j9wreck = ids
end)
at(2800, function(s)
  local surface = s.j9b.surface
  local spot = surface.find_non_colliding_position(BEACHED, {x = s.j9b.position.x + 12, y = s.j9b.position.y}, 20, 0.5)
  s.jcount = kept().beached
  local copy = s.j9b.clone{position = spot, surface = surface}
  check("W a clone is kept, his legs drawn on it", copy ~= nil and kept(copy).kept and (wreck_kept(copy)),
        copy and select(3, wreck_kept(copy)))
  check("W ... at the health it was cloned at", copy and near(copy.health, s.j9b.health, 1e-3),
        copy and (copy.health .. " vs " .. s.j9b.health))
  check("W ... and the source's legs untouched", line(wreck_on(s.j9b)) == line(s.j9wreck))
  s.jclone = copy
  s.jclonewreck = copy and wreck_on(copy)
  if copy then copy.destroy() end
end)
at(2801, function(s)
  check("W the clone destroyed: its legs and its record gone with it", #(s.jclonewreck or {}) > 0
        and alive(s.jclonewreck) == 0 and kept().beached == s.jcount,
        alive(s.jclonewreck or {}) .. " " .. kept().beached .. " vs " .. tostring(s.jcount))
end)

-- ROW E: THE REVIEW'S FIXES ------------------------------------------------------------------

-- STATE: another mod's hold on him is not undone by a jump; the player's decon order rides it.
at(12, function(s)
  for _, kind in ipairs({"disabled", "inoperable", "decon"}) do
    local m = s.st[kind]
    m.r = jump(m.e)
  end
  for _, kind in ipairs({"disabled", "inoperable"}) do
    local m = s.st[kind]
    check("STATE " .. kind .. ": refused, silently (frozen)", m.r.jumped == false and m.r.why == "frozen"
          and m.r.said == nil, line(m.r))
    check("STATE " .. kind .. ": the same body, its hold intact", m.e.valid and m.e.unit_number == m.unit
          and m.e.name == VEHICLE and (kind ~= "disabled" or m.e.disabled_by_script)
          and (kind ~= "inoperable" or not m.e.operable))
  end
  check("STATE decon: a marked jamaltron still jumps", s.st.decon.r.jumped == true, line(s.st.decon.r))
end)
at(43, function(s)
  local m = s.st.decon
  local b = m.c.vehicle
  check("STATE decon: lands the vehicle, still marked for deconstruction", b ~= nil and b.name == VEHICLE
        and b.position.x == m.from.x + 8 and b.to_be_deconstructed(), b and b.name)
end)

-- MID: the spot AND the takeoff built over mid-arc, or both flooded.
at(14, function(s)
  s.mwfrom, s.mbfrom = s.mw.position, s.mb.position
  check("MID silo+wall jumps", jump(s.mw).jumped)
  check("MID water-at-both jumps", jump(s.mb).jumped)
end)
at(29, function(s)                                    -- u = 0.5
  local surface = game.surfaces[1]
  s.silo = surface.create_entity{name = "rocket-silo", position = {s.mwfrom.x + 8, s.mwfrom.y}, force = "player"}
  s.mwall = surface.create_entity{name = "stone-wall", position = s.mwfrom, force = "player"}
  check("MID a silo on the spot and a wall on the takeoff, mid-arc", s.silo ~= nil and s.mwall ~= nil)
  local fx, fy = math.floor(s.mbfrom.x), math.floor(s.mbfrom.y)
  local tiles = {}
  for x = fx - 6, fx + 14 do
    for y = fy - 6, fy + 6 do tiles[#tiles + 1] = {name = "deepwater", position = {x, y}} end
  end
  surface.set_tiles(tiles, true, false)               -- false: the airborne body's legs stay
end)
at(45, function(s)
  local surface = game.surfaces[1]
  local b = s.mwc.vehicle
  local p = b and b.position
  L("MID silo+wall landed at", p and line(p), "took off at", line(s.mwfrom))
  check("MID silo+wall: lands the vehicle beside the wall, never in it", b ~= nil and b.name == VEHICLE
        and not surface.entity_prototype_collides(LEG, p, false) and dist(p, s.mwfrom) <= 5
        and s.mwall.valid and s.silo.valid, p and line(p))
  local w = s.mbc.vehicle
  local q = w and w.position
  local tile = q and surface.get_tile(q.x, q.y).name
  L("MID water-at-both landed at", q and line(q), "on", tile)
  check("MID water-at-both: lands on ground, never on the lake", w ~= nil and w.name == VEHICLE
        and not tile:find("water", 1, true), tostring(tile))
end)

-- REL: the key held at takeoff and let go of at the peak - a scripted driver's state latches, so
-- this is exactly what the swap reads at touchdown.
at(16, function(s)
  check("REL jumps holding east", jump(s.rel).jumped)
end)
at(31, function(s) s.relc.walking_state = {walking = false, direction = defines.direction.east} end)
at(47, function(s)
  local b = s.relc.vehicle
  s.relb, s.relspot = b, b and b.position
  check("REL landed the vehicle", b ~= nil and b.name == VEHICLE, b and b.name)
end)
at(107, function(s)
  local moved = s.relb and s.relb.valid and dist(s.relb.position, s.relspot) or -1
  check("REL a key let go of mid-arc lands him STANDING (a second later he has not walked)",
        moved >= 0 and moved < 0.3, moved)
end)

-- DRIFT: beached with water 1.5 tiles ahead; lands with J9 at 100%.
at(18, function(s)
  s.drfrom = s.dr.position
  check("DRIFT jumps", jump(s.dr).jumped)
end)
at(49, function(s)
  local b = s.drc.vehicle
  s.drb, s.drt = b, game.tick - 1
  check("DRIFT lands beached beside the water", b ~= nil and b.name == BEACHED, b and b.name)
  local k = b and kept(b)
  check("DRIFT his first alert re-issue waits 3 s for him to settle", k and k.alert_at == s.drt + 180, line(k))
end)
at(290, function(s)
  local b, k = s.drb, kept(s.drb)
  local spot = {x = s.drfrom.x + 8, y = s.drfrom.y}
  L("DRIFT settled", dist(b.position, spot), "tiles from the spot; kept position", line(k.position))
  check("DRIFT after the settle re-issue, the kept alert position is where he lies",
        k.kept and k.alert_at > s.drt + 180 and dist(k.position, b.position) < 0.01,
        line(k) .. " body " .. line(b.position))
  b.health = b.max_health                             -- up on the poll: gone before B's counts
end)
at(380, function(s)
  local up = s.drc.vehicle
  check("DRIFT up again by the poll", up ~= nil and up.name == VEHICLE and not s.drb.valid, up and up.name)
end)

-- F: a listener kills his landing body 5 times - the landing, 3 retries, one poll.
script.on_event("on_spidertron_replaced", function(event)
  local old, new = event.old_spidertron, event.new_spidertron
  if storage.f_unit and old and old.valid and old.unit_number == storage.f_unit and (storage.f_left or 0) > 0
      and new and new.valid then
    storage.f_left = storage.f_left - 1
    storage.f_kills = (storage.f_kills or 0) + 1
    new.destroy()
  end
end)
at(700, function(s)
  s.ffrom = s.f.position
  check("F jumps", jump(s.f).jumped)
  local a = s.fc.vehicle
  s.fa = a
  storage.f_unit, storage.f_left = a and a.unit_number, 5
end)
at(911, function(s)                                   -- landing 730, retries 790 850 910
  local a = s.fa
  local st, c = jstate(a), clockstate()
  check("F after 4 killed landings: stranded, whole, his driver in, trunk unlocked", storage.f_kills == 4
        and a.valid and a.name == AIRBORNE and a.operable == true and s.fc.vehicle == a and st.stranded == 1,
        tostring(storage.f_kills) .. " " .. line(st))
  check("F ... and off the clock: nothing per tick for him", st.arc == nil and not c.pending and not c.registered,
        line(c))
end)
at(1100, function(s)
  local b = s.fc.vehicle
  check("F the poll landed him once the listener stopped: the vehicle, his driver seated, nothing stranded",
        storage.f_kills == 5 and b ~= nil and b.name == VEHICLE and not s.fa.valid and jstate().stranded == 0,
        tostring(storage.f_kills) .. " " .. tostring(b and b.name))
  check("F ... where he sat, 8 tiles on", b and dist(b.position, {x = s.ffrom.x + 8, y = s.ffrom.y}) < 0.01,
        b and line(b.position))
  storage.f_unit = nil
end)

-- K: /jamaltron-swap beached, as the playtest does it - the bare swap, then keep.
at(1300, function(s)
  local r = remote.call(H, "swap", s.k, BEACHED, {reason = "playtest"})
  local b = r.body
  s.kb, s.kspot = b, b and b.position
  check("K the bare swap alone is not kept (the limbo keep() exists for)", b ~= nil and b.name == BEACHED
        and not kept(b).kept and near(b.get_health_ratio(), 1), r.status)
  check("W K a bare swap draws no legs by itself", #wreck_on(b) == 0, #wreck_on(b))
  check("K keep() takes him", remote.call(H, "keep", b) == true)
  local ok, ids, why = wreck_kept(b)
  check("W K keep() drew his legs", ok, why)
  s.kwreck = ids
  local k, st = kept(b), speech(b)
  check("K kept: capped at half health, alert up, first re-issue once settled", k.kept
        and near(b.get_health_ratio(), 0.5) and k.alert_at == game.tick + 180, line(k))
  check("K the default fork (self), and no break counted he did not have", st and st.fork == "self"
        and st.breaks == 0, line(st))
  log("HARNESS need jamaltron speech " .. b.unit_number .. " flopping[.]")
end)
at(1301, function(s)                                 -- a second adopt: after K's own alert checks
  check("W K a second keep() of a kept body draws nothing more", remote.call(H, "keep", s.kb) == true
        and line(wreck_on(s.kb)) == line(s.kwreck), #wreck_on(s.kb))
end)
at(2450, function(s) s.kb.health = s.kb.max_health end)
at(2520, function(s)
  local up = s.kc.vehicle
  check("K full health: the poll stood him up, repaired, not kept", up ~= nil and up.name == VEHICLE
        and not s.kb.valid and not kept(up).kept and row_of(up):match("^repaired%.") ~= nil, up and row_of(up))
  check("W K stood up by the poll: none of his broken legs left", #s.kwreck > 0 and alive(s.kwreck) == 0,
        alive(s.kwreck) .. " of " .. #s.kwreck)
end)

-- W: on_configuration_changed's pass (adopt_all) redraws a set that is gone - the path an update
-- that re-cut the sprites takes (wreck.lua's geometry stamp) - and leaves every other set alone.
---Every sprite of ours NOT on `e`, sorted: the other bodies' legs.
local function sprites_but(e)
  local ids = {}
  for _, o in pairs(rendering.get_all_objects("jamaltron")) do
    if o.type == "sprite" and o.target.entity ~= e then ids[#ids + 1] = o.id end
  end
  table.sort(ids)
  return ids
end
at(1350, function(s)
  local others = sprites_but(s.kb)
  check("W adopt_all runs with other beached Jamals' legs on the map", #others >= 46, #others)
  for _, id in ipairs(wreck_on(s.kb)) do rendering.get_object_by_id(id).destroy() end
  check("W K's legs taken down by hand", #wreck_on(s.kb) == 0 and alive(s.kwreck) == 0, #wreck_on(s.kb))
  remote.call(H, "adopt_all")
  local ok, ids, why = wreck_kept(s.kb)
  check("W adopt_all redrew exactly one set on K, the one his record keeps", ok, why)
  check("W ... and not one other body's legs moved", line(sprites_but(s.kb)) == line(others),
        #sprites_but(s.kb) .. " vs " .. #others)
  s.kwreck = ids
  s.kothers = others
end)
at(1351, function(s)
  remote.call(H, "adopt_all")
  check("W a second adopt_all draws nothing and takes nothing down",
        line(wreck_on(s.kb)) == line(s.kwreck) and line(sprites_but(s.kb)) == line(s.kothers))
end)

-- SA: /jamaltron-swap airborne, as the playtest does it - the bare swap, then strand (E.6: with
-- no arc and no stranded entry he stayed invisible and locked, his driver in, for good).
at(1390, function(s) s.sa, s.sac = driven(400, ROW_E) end)
at(1400, function(s)
  local r = remote.call(H, "swap", s.sa, AIRBORNE, {reason = "playtest"})
  local a = r.body
  s.saa, s.saspot = a, a and a.position
  check("SA the bare swap alone is neither flying nor stranded", a ~= nil and a.name == AIRBORNE
        and jstate().stranded == 0 and jstate(a).arc == nil and a.operable == false, r.status)
  check("SA strand() takes him, and again (idempotent)", remote.call(H, "strand", a) == true
        and remote.call(H, "strand", a) == true and jstate().stranded == 1 and a.operable == true, line(jstate()))
end)
at(1462, function(s)                                 -- a 60-tick poll has run since
  local b = s.sac.vehicle
  check("SA the poll landed him where he sat: the vehicle, his driver in, nothing stranded",
        b ~= nil and b.name == VEHICLE and not s.saa.valid and dist(b.position, s.saspot) < 0.01
        and jstate().stranded == 0, b and (b.name .. " " .. line(b.position)))
end)

-- THE END ------------------------------------------------------------------------------------
at(END_AT, function(s)
  local k = kept()
  check("END one kept map-wide: J9, left beached on purpose", k.beached == 1 and s.j9b and s.j9b.valid
        and kept(s.j9b).kept, line(k))
  check("END no render object of ours is an arc drawing", animations() == 0, animations())
  local sprites = 0
  for _, o in pairs(rendering.get_all_objects("jamaltron")) do
    if o.type == "sprite" then sprites = sprites + 1 end
  end
  local ok, ids, why = wreck_kept(s.j9b)
  check("END every broken leg drawn is J9's, the one Jamal still beached: no orphans", ok and sprites == #ids
        and line(ids) == line(s.j9wreck), sprites .. " sprites; " .. why)
  check("END no landing, break or repair ever raised on_entity_damaged", (storage.damaged or 0) == 0, storage.damaged)
  local c = clockstate()
  check("END the clock is idle", not c.pending and not c.registered, line(c))
  local st = jstate()
  check("END no arc, no drawing", st.arcs == 0 and st.drawn == 0, line(st))
  local cs = census()
  check("END no speech record on a dead body or under the wrong unit", cs.dead == 0 and cs.mismatched == 0,
        line(cs))
  local sw = remote.call(H, "swap_state")
  check("END no stash left behind", sw.stash == 0, line(sw))
  local dead = {}
  for _, unit in ipairs(st.units) do
    if not game.get_entity_by_unit_number(unit) then dead[#dead + 1] = unit end
  end
  check("END no cooldown or refusal tick kept for a body that is gone (jump.forget)", #dead == 0,
        line(dead) .. " of " .. #st.units)
  check("END nothing stranded", st.stranded == 0, line(st))
  L("END jump state", line(st))
  log("HARNESS done " .. tostring(storage.passed))
end)

table.sort(steps, function(x, y) return x.dt < y.dt end)

script.on_event(defines.events.on_tick, function(event)
  local s = storage
  s.start = s.start or event.tick
  local dt = event.tick - s.start
  for _, step in ipairs(steps) do
    if step.dt == dt then
      local ok, err = pcall(step.fn, s)
      if not ok then check("step at dt " .. dt .. " ran", false, err) end
    end
  end
  for _, hook in ipairs(every) do
    if dt >= hook.from and dt <= hook.to then
      local ok, err = pcall(hook.fn, s, dt)
      if not ok and not s.hook_failed then
        s.hook_failed = true                            -- one line, not one per tick
        check("per-tick hook from dt " .. hook.from .. " ran", false, err)
      end
    end
  end
end)
