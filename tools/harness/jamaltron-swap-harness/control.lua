-- The D.4 swap harness (PLAN D.4.7): a fully kitted Jamal through every swap the mod will make
-- - a break and a repair, a jump (takeoff, a 30-tick arc, a landing 8 tiles on), a drifted
-- body, two swaps in one tick - each hop asserted field by field at t+0 and again at t+1, when
-- the late writes land. Then what the verifiers broke: a disabled airborne body landing, a
-- listener killing the new body, an error after the trunk moved, a failed second swap, a grid
-- too small, another mod swapping him back, 200 swaps one a tick, and the cost lines. E.6 adds
-- P1: a proxy container aimed at him (Spidertron Patrols' dock) follows him across a swap.
--
--   HARNESS ok <check> | HARNESS FAIL <check>: <detail> | HARNESS need/never <ERE> | HARNESS done
--   SWAP <...>   measurements (events seen, costs, what a driver reads), never judged
--
-- It judges what a body DOES, never how the swap stopped it: D.1's beached and airborne are
-- immobile by prototype and stay enabled, this harness's stand-ins (data-final-fixes.lua) are
-- plain clones held with disabled_by_script, and both must pass. disabled_by_script itself is
-- asserted where the swap owns it: another mod's disable carried vehicle to vehicle (S4) and
-- an explicit opts.disabled (F1, J3).
--
-- A headless run has no LuaPlayer, so nothing here reaches the player-side half of the swap
-- (remote selections, an open GUI, pins, a real driver's key, remote driving). That is D.4.8's
-- play.sh pass. The scripted character driver's walking_state LATCHES (E.2.2, measured), so a
-- landing that walks proves the rewrite, not what a player holding W sees.

local SAY, H = "jamaltron", "jamaltron-harness"
local TRUNK, AMMO, TRASH = defines.inventory.spider_trunk, defines.inventory.spider_ammo,
  defines.inventory.spider_trash
local INVS = {TRUNK, AMMO, TRASH}
local VEHICLE, BEACHED, AIRBORNE = "jamaltron", "jamaltron-beached", "jamaltron-airborne"
local SMALL, SMALLGRID = "jamaltron-swaptest-small", "jamaltron-swaptest-smallgrid"
local BURNER = "jamaltron-swaptest-burner"
local FAMILY = {[VEHICLE] = true, [BEACHED] = true, [AIRBORNE] = true, [SMALL] = true,
                [SMALLGRID] = true}
-- lanes: A the design's S1-S8, B the verifiers' cases, C costs and the 200-swap run
local ROW_A, ROW_B, ROW_C = 40, 140, 240

local function line(v) return serpent.line(v, {comment = false, nocode = true}) end
local function L(...)
  local t = {...}
  for i = 1, select("#", ...) do t[i] = tostring(t[i]) end
  log("SWAP " .. table.concat(t, " "))
end
local function check(name, ok, detail)
  storage.passed = (storage.passed or 0) + (ok and 1 or 0)
  log(ok and ("HARNESS ok " .. name) or ("HARNESS FAIL " .. name .. ": " .. tostring(detail)))
end
local function who(x)
  if x == nil then return "nil" end
  if type(x) ~= "userdata" and type(x) ~= "table" then return tostring(x) end
  if x.object_name == "LuaEntity" then
    return x.valid and (x.name .. "#" .. tostring(x.unit_number)) or "<invalid>"
  end
  return tostring(x.object_name)
end
local function near(a, b, eps) return a ~= nil and b ~= nil and math.abs(a - b) <= (eps or 1e-6) end
local function eqv(a, b) return line(a) == line(b) end
local function dist(a, b) return math.sqrt((a.x - b.x) ^ 2 + (a.y - b.y) ^ 2) end

---@return LuaEntity?, string
local function swap(entity, name, opts)
  local r = remote.call(H, "swap", entity, name, opts)
  return r.body, r.status
end
local function state(e) return remote.call(H, "swap_state", e) end
local function speech(e) return remote.call(H, "state", e) end
local function census() return remote.call(H, "census") end
local function clockstate() return remote.call(H, "clock") end

---------------------------------------------------------------------------------------------
-- READ: plain data for asserting on
local function item_of(st)
  if not (st and st.valid_for_read) then return nil end
  local r = {name = st.name, q = st.quality.name, n = st.count, health = st.health,
             item_number = st.item_number}
  local ok, spoil = pcall(function() return st.spoil_tick end)
  if ok then r.spoil_tick = spoil end
  if st.is_blueprint then r.bp = #st.export_stack(); r.bp_label = st.label end
  if st.is_item_with_entity_data then r.ent_label = st.entity_label end
  return r
end
local function inv_of(inv)
  local r = {size = #inv, slots = {}, filters = {}}
  for i = 1, #inv do
    if inv.supports_filters() then r.filters[i] = inv.get_filter(i) end
    r.slots[i] = item_of(inv[i])
  end
  return r
end
---Every stack in the three inventories as a sorted list of lines: what must survive a swap
---whatever slot the engine re-sorts it into.
local function bag(e)
  local r = {}
  for _, idx in ipairs(INVS) do
    local inv = e.get_inventory(idx)
    for i = 1, #inv do
      if inv[i].valid_for_read then r[#r + 1] = idx .. ":" .. line(item_of(inv[i])) end
    end
  end
  table.sort(r)
  return r
end
local function total(e)
  local n = 0
  for _, idx in ipairs(INVS) do n = n + e.get_inventory(idx).get_item_count() end
  return n
end
local function ground(pos, r, name)
  local n = 0
  for _, it in pairs(game.surfaces[1].find_entities_filtered{name = "item-on-ground", position = pos, radius = r}) do
    if name == nil or it.stack.name == name then n = n + it.stack.count end
  end
  return n
end
local function bodies_at(pos, r)
  local out = {}
  for _, f in pairs(game.surfaces[1].find_entities_filtered{position = pos, radius = r, type = "spider-vehicle"}) do
    if FAMILY[f.name] then out[#out + 1] = f end
  end
  return out
end
local function proxies(e)
  local out = {}
  for _, p in pairs(e.surface.find_entities_filtered{name = "item-request-proxy", position = e.position, radius = 1}) do
    if p.proxy_target == e then out[#out + 1] = p end
  end
  return out
end
local function energies(e)
  local r = {}
  for _, q in pairs(e.grid.equipment) do
    if q.type ~= "equipment-ghost" then
      r[#r + 1] = {q.name, q.position.x, q.position.y, math.floor(q.energy), q.max_shield > 0 and q.shield or nil}
    end
  end
  table.sort(r, function(a, b) return a[3] * 100 + a[2] < b[3] * 100 + b[2] end)
  return r
end
local function snapshot(e)
  local s = {name = e.name, unit = e.unit_number, quality = e.quality.name, force = e.force.name,
             position = e.position, orientation = e.orientation, torso = e.torso_orientation,
             ratio = e.get_health_ratio(), max_health = e.max_health,
             driver = e.get_driver(), passenger = e.get_passenger(),
             dig = e.driver_is_gunner, sgi = e.selected_gun_index,
             tgt = e.vehicle_automatic_targeting_parameters, color = e.color, label = e.entity_label,
             name_tag = e.name_tag, elwm = e.enable_logistics_while_moving,
             adr = e.allow_dispatching_robots, rfb = e.request_from_buffers,
             destructible = e.destructible, minable_flag = e.minable_flag, operable = e.operable,
             rotatable = e.rotatable, protected = e.protected,
             disabled = e.disabled_by_script, custom_status = e.custom_status,
             tooltip = e.get_tooltip_fields(), dests = e.autopilot_destinations,
             patrol = e.autopilot_patrol_size, follow = e.follow_target,
             follow_offset = e.follow_offset, decon = e.to_be_deconstructed(),
             points = {}, sections = {}, inv = {}, eq = {}, stickers = {}, plan = {}}
  for _, p in pairs(e.get_logistic_point() or {}) do
    s.points[p.logistic_member_index] = {p.enabled, p.trash_not_requested}
  end
  for _, sec in pairs(e.get_logistic_sections().sections) do
    s.sections[#s.sections + 1] = {sec.group, sec.active, sec.multiplier, sec.filters}
  end
  for _, idx in ipairs(INVS) do s.inv[idx] = inv_of(e.get_inventory(idx)) end
  s.inhibit = e.grid.inhibit_movement_bonus
  for _, q in pairs(e.grid.equipment) do
    local ghost = q.type == "equipment-ghost"
    s.eq[#s.eq + 1] = {name = ghost and q.ghost_name or q.name, ghost = ghost, q = q.quality.name,
                       pos = q.position, removal = q.to_be_removed,
                       energy = not ghost and q.energy or nil,
                       shield = (not ghost and q.max_shield > 0) and q.shield or nil}
  end
  table.sort(s.eq, function(a, b) return a.pos.y * 100 + a.pos.x < b.pos.y * 100 + b.pos.x end)
  for _, x in pairs(e.stickers or {}) do s.stickers[#s.stickers + 1] = {x.name, x.time_to_live} end
  local ins = {}
  for _, p in ipairs(proxies(e)) do
    for _, x in ipairs(p.insert_plan or {}) do ins[#ins + 1] = line(x) end
    for _, x in ipairs(p.removal_plan or {}) do ins[#ins + 1] = "rm " .. line(x) end
  end
  table.sort(ins)
  s.plan = ins
  s.speech = speech(e)
  s.walking = s.driver and s.driver.valid and s.driver.walking_state or nil
  return s
end

---Hop asserts. `skip` names fields this hop changes on purpose; `t0` relaxes the known t+1 lags
---(storage point, disabled, trunk slots a toolbelt has not grown yet) - those get their own
---t+1 checks. Grid energy is compared at t0 only (exact copies); after that the one enabled
---tick, or an enabled body, legitimately moves it (S4 measures it).
local function compare(tag, a, b, opts)
  opts = opts or {}
  local skip = opts.skip or {}
  local function c(key, ok, detail)
    if not skip[key] then check(tag .. " " .. key, ok, detail) end
  end
  c("position", a.position.x == b.position.x and a.position.y == b.position.y,
    line(a.position) .. " => " .. line(b.position))
  -- A spider's orientation IS its torso's, quantized to the body's sprite directions (measured:
  -- D.1's one-direction beached body reads 0 whatever is written, and so does the airborne body
  -- since E.1 drew it as nothing), so the torso is the state.
  if a.name ~= BEACHED and b.name ~= BEACHED and a.name ~= AIRBORNE and b.name ~= AIRBORNE then
    c("orientation", near(a.orientation, b.orientation), a.orientation .. " => " .. b.orientation)
  end
  c("torso", near(a.torso, b.torso, 1e-5), a.torso .. " => " .. b.torso)
  c("quality", a.quality == b.quality, a.quality .. " => " .. b.quality)
  c("force", a.force == b.force)
  c("health ratio", near(a.ratio, b.ratio, 1e-5), a.ratio .. " => " .. b.ratio)
  c("driver", a.driver == b.driver, who(a.driver) .. " => " .. who(b.driver))
  c("passenger", a.passenger == b.passenger, who(a.passenger) .. " => " .. who(b.passenger))
  for _, k in ipairs({"dig", "sgi", "tgt", "color", "label", "name_tag", "elwm", "adr", "rfb",
                      "destructible", "minable_flag", "operable", "rotatable", "protected",
                      "custom_status", "tooltip", "sections", "decon", "plan", "inhibit"}) do
    c(k, eqv(a[k], b[k]), line(a[k]):sub(1, 300) .. " => " .. line(b[k]):sub(1, 300))
  end
  if not opts.t0 then
    c("disabled", a.disabled == b.disabled, tostring(a.disabled) .. " => " .. tostring(b.disabled))
    c("points", eqv(a.points, b.points), line(a.points) .. " => " .. line(b.points))
  end
  local function bagof(inv)
    local r = {}
    for _, it in pairs(inv.slots) do r[#r + 1] = line(it) end
    table.sort(r)
    return r
  end
  for _, idx in ipairs(INVS) do
    local x, y = a.inv[idx], b.inv[idx]
    if opts.bag and idx ~= AMMO then
      -- layout is the engine's to re-sort; what must hold is every item and every filter
      c("inventory " .. idx .. " (items + filters)", eqv(bagof(x), bagof(y)) and eqv(x.filters, y.filters),
        line(bagof(x)):sub(1, 300) .. " => " .. line(bagof(y)):sub(1, 300))
    else
      local lim = (opts.t0 and idx == TRUNK) and y.size or math.max(x.size, y.size)
      local bad = {}
      for i = 1, lim do
        if not eqv(x.slots[i], y.slots[i]) then
          bad[#bad + 1] = i .. ":" .. line(x.slots[i]) .. "=>" .. line(y.slots[i])
        end
        if not eqv(x.filters[i], y.filters[i]) then bad[#bad + 1] = "f" .. i end
      end
      c("inventory " .. idx, #bad == 0, table.concat(bad, " "):sub(1, 600))
    end
  end
  local energy = opts.t0 and not opts.noenergy
  local function shape(eq)
    local r = {}
    for i, x in ipairs(eq) do
      r[i] = {x.name, x.ghost, x.q, x.pos, x.removal, energy and x.energy or nil, energy and x.shield or nil}
    end
    return r
  end
  c("grid", eqv(shape(a.eq), shape(b.eq)),
    line(shape(a.eq)):sub(1, 400) .. " => " .. line(shape(b.eq)):sub(1, 400))
  if a.follow then
    c("follow", b.follow == a.follow and eqv(a.follow_offset, b.follow_offset),
      who(a.follow) .. line(a.follow_offset) .. " => " .. who(b.follow) .. line(b.follow_offset))
  else
    c("autopilot", eqv(a.dests, b.dests) and a.patrol == b.patrol,
      line(a.dests) .. "/" .. a.patrol .. " => " .. line(b.dests) .. "/" .. b.patrol)
  end
  local ttl = #a.stickers == #b.stickers
  for i, x in ipairs(a.stickers) do
    local y = b.stickers[i]
    ttl = ttl and y ~= nil and x[1] == y[1] and near(x[2], y[2], 2)
  end
  c("stickers", ttl, line(a.stickers) .. " => " .. line(b.stickers))
  if a.speech and not skip.speech then
    local x, y = a.speech, b.speech or {}
    table.sort(x.fired); table.sort(y.fired or {})
    c("speech record", x.breaks == y.breaks and x.fork == y.fork and eqv(x.fired, y.fired)
      and x.recent == y.recent and x.last_id == y.last_id, line(x) .. " => " .. line(y))
  end
end

---------------------------------------------------------------------------------------------
-- EVENTS other mods would see, per swap. The same handlers play the hostile listener:
-- storage.kill = kind destroys the new body when that event arrives, storage.boom = kind
-- throws from it, storage.reenter tries to swap both bodies from inside the swap.
local function capture(kind)
  return function(e)
    if not storage.label then return end
    local r = {kind = kind, label = storage.label, tick = e.tick}
    local function body(x)
      if not (x and x.valid) then return {valid = false} end
      return {valid = true, name = x.name, unit = x.unit_number, driver = who(x.get_driver()),
              items = x.get_inventory(TRUNK).get_item_count()}
    end
    if kind == "replaced" then
      r.old, r.new, r.reason = body(e.old_spidertron), body(e.new_spidertron), e.jamaltron_reason
      if storage.reenter then
        storage.reenter = nil
        local _, a = swap(e.old_spidertron, BEACHED)
        local _, b = swap(e.new_spidertron, BEACHED)
        storage.reenter_old, storage.reenter_new = a, b
      end
    else
      r.entity = body(e.entity)
    end
    storage.events[#storage.events + 1] = r
    if not storage.quiet then L("EVT", storage.label, kind, line(r)) end
    if storage.kill == kind then
      storage.kill = nil
      local victim = kind == "replaced" and e.new_spidertron or e.entity
      L("EVT", storage.label, "the harness destroys", who(victim), "from", kind)
      victim.destroy()
    end
    if storage.boom == kind then
      storage.boom = nil
      error("harness boom from " .. kind)
    end
  end
end
script.on_event("on_spidertron_replaced", capture("replaced"))
script.on_event(defines.events.script_raised_built, capture("built"))
script.on_event(defines.events.script_raised_destroy, capture("destroy"))
local function events(label, kind)
  local out = {}
  for _, r in ipairs(storage.events) do
    if r.label == label and r.kind == kind then out[#out + 1] = r end
  end
  return out
end

---Swap with the events labelled, and the speech log checked for a built line on the new body.
local function hop(label, entity, name, opts)
  storage.label = label
  local b, status = swap(entity, name, opts)
  storage.label = nil
  if b then log("HARNESS never jamaltron speech " .. b.unit_number .. " built[.]") end
  return b, status
end

---------------------------------------------------------------------------------------------
-- THE KIT
local FILLERS
---Fill every empty trunk slot with one of a DIFFERENT item each, none of them already in the
---trunk: an active spider re-sorts and merges his trunk every tick, and only distinct items
---keep a full trunk full.
local function fill(e)
  if not FILLERS then
    FILLERS = {}
    for name, proto in pairs(prototypes.item) do
      if proto.type == "item" and not proto.hidden and proto.stack_size > 1 and proto.get_spoil_ticks() == 0
          and name ~= "fission-reactor-equipment" and name ~= "exoskeleton-equipment" then
        FILLERS[#FILLERS + 1] = name
      end
    end
    table.sort(FILLERS)
  end
  local t, n, k = e.get_inventory(TRUNK), 0, 0
  local present = {}
  for i = 1, #t do
    if t[i].valid_for_read then present[t[i].name] = true end
  end
  for i = 1, #t do
    if not t[i].valid_for_read and not t.get_filter(i) then
      repeat k = k + 1 until not present[FILLERS[k]]
      n = n + 1
      t[i].set_stack{name = FILLERS[k], count = 1}
    end
  end
  return n
end
local function mk(name, x, y)
  local s = game.surfaces[1]
  return s.create_entity{name = name, position = s.find_non_colliding_position(name, {x, y}, 20, 0.5) or {x, y},
                         force = "player"}
end
local function spawn(x, y, q)
  local s = game.surfaces[1]
  local at = s.find_non_colliding_position(VEHICLE, {x, y}, 40, 1) or {x, y}
  return s.create_entity{name = VEHICLE, position = at, force = "player", quality = q or "normal"}
end

---Everything the swap claims to carry. kit.toolbelt fills a slot that only exists from t+1.
local function populate(a, kit)
  local surface = a.surface
  a.color = {r = 0.1, g = 0.8, b = 0.3, a = 1}
  a.entity_label = "Jamal " .. kit.tag
  a.name_tag = "jamal-" .. kit.tag
  a.health = a.max_health * 0.37
  a.torso_orientation = 0.55
  local c1, c2 = mk("character", a.position.x + 3, a.position.y), mk("character", a.position.x - 3, a.position.y)
  a.set_driver(c1)
  a.set_passenger(c2)
  a.driver_is_gunner = false
  a.selected_gun_index = 3
  a.vehicle_automatic_targeting_parameters = {auto_target_without_gunner = false, auto_target_with_gunner = true}
  a.enable_logistics_while_moving = false
  a.allow_dispatching_robots = false
  a.request_from_buffers = true
  local ls = a.get_logistic_sections()
  local s1 = ls.get_section(1)
  s1.set_slot(1, {value = {name = "iron-plate", quality = "normal"}, min = 50, max = 100})
  s1.set_slot(2, {value = {name = "flamethrower-ammo", quality = "rare", comparator = "="}, min = 10})
  s1.multiplier = 2
  ls.add_section("jamal-group").set_slot(1, {value = "copper-plate", min = 10})
  local s3 = ls.add_section()
  s3.set_slot(1, {value = "stone", min = 0, max = 0})
  s3.active = false
  local g = a.grid
  local bat = g.put{name = "battery-mk2-equipment", position = {0, 0}, quality = "rare"}
  local sh = g.put{name = "energy-shield-equipment", position = {1, 0}}
  g.put{name = "fission-reactor-equipment", position = {3, 0}}
  local exo = g.put{name = "exoskeleton-equipment", position = {7, 0}}
  local rp = g.put{name = "personal-roboport-equipment", position = {1, 2}}
  if kit.toolbelt then g.put{name = "toolbelt-equipment", position = {0, 4}} end
  g.put{name = "solar-panel-equipment", position = {9, 0}, ghost = true}
  bat.energy = bat.max_energy * 0.37
  sh.energy = sh.max_energy
  sh.shield = sh.max_shield * 0.25
  rp.energy = rp.max_energy * 0.5
  g.order_removal(exo)
  g.inhibit_movement_bonus = true
  local trunk, ammo, trash = a.get_inventory(TRUNK), a.get_inventory(AMMO), a.get_inventory(TRASH)
  trunk[1].set_stack{name = "iron-plate", count = 100}
  trunk[3].set_stack{name = "iron-plate", count = 10, quality = "rare"}
  trunk[5].set_stack{name = "gun-turret", count = 3, health = 0.5}
  trunk[7].set_stack{name = "yumako", count = 20}
  trunk[7].spoil_percent = 0.4
  trunk[9].set_stack{name = "blueprint"}
  trunk[9].set_blueprint_entities({{entity_number = 1, name = "iron-chest", position = {0.5, 0.5}}})
  trunk[9].label = "bp-jamal"
  trunk[11].set_stack{name = "car"}
  trunk[11].entity_label = "nested-car"
  trunk.set_filter(15, {name = "iron-plate", quality = "rare", comparator = "="})
  trunk.set_filter(78, "iron-gear-wheel")
  trunk[78].set_stack{name = "iron-gear-wheel", count = 42}
  trunk[70].set_stack{name = "copper-plate", count = 77}      -- beyond a half-size trunk
  trunk.set_filter(68, "coal")                                -- a filter beyond it too
  -- D.7: flamethrower ammo, the only thing his guns take. An ammo slot refuses anything else
  -- WITHOUT an error - the rockets this used to load never went in, and every "ammo carried"
  -- check held for four empty slots - so the load is checked, not assumed.
  local loaded = ammo[1].set_stack{name = "flamethrower-ammo", count = 37}
  loaded = ammo[2].set_stack{name = "flamethrower-ammo", count = 5, quality = "rare"} and loaded
  loaded = ammo.set_filter(4, {name = "flamethrower-ammo", quality = "rare", comparator = "="}) and loaded
  check(kit.tag .. " fixture: flamethrower ammo in slots 1 and 2, a filter on 4", loaded
        and ammo[1].count == 37 and ammo[2].count == 5 and ammo[2].quality.name == "rare"
        and ammo.get_filter(4) ~= nil, line({loaded, ammo.get_contents(), ammo.get_filter(4)}))
  trash[2].set_stack{name = "stone", count = 20}
  trash[18].set_stack{name = "wood", count = 9}               -- beyond a half-size trash
  for _, p in pairs(a.get_logistic_point() or {}) do
    if p.logistic_member_index == defines.logistic_member_index.spidertron_provider then
      p.trash_not_requested = true
    end
  end
  surface.create_entity{name = "slowdown-sticker", position = a.position, target = a, force = "enemy"}
  a.set_tooltip_field{name = "Legs broken", value = "1"}
  a.custom_status = {diode = defines.entity_status_diode.yellow, label = "Test status"}
  surface.create_entity{name = "item-request-proxy", target = a, position = a.position, force = a.force,
    modules = {{id = {name = "iron-gear-wheel"},
                items = {in_inventory = {{inventory = TRUNK, stack = 20, count = 5}}}}}}
  remote.call(SAY, "say", a, "legs_break", "self")          -- a count and a fork to carry
  remote.call(H, "force", a, "idle.34")                     -- a once_per_save row
  return c1, c2
end

---------------------------------------------------------------------------------------------
local steps = {}
local function at(dt, fn) steps[#steps + 1] = {dt = dt, fn = fn} end

at(0, function(s)
  local surface = game.surfaces[1]
  surface.request_to_generate_chunks({200, 100}, 12)
  surface.force_generate_chunk_requests()
  -- Nothing may shoot at the kits: a biter's bite is a health-ratio FAIL that is not the swap's.
  surface.peaceful_mode = true
  for _, e in pairs(surface.find_entities_filtered{force = "enemy"}) do e.destroy() end
  -- Grass and nothing else under every ordinary lane: the map is random per run, and a lane
  -- that rolls a lake or a cliff tests that, not what the lane is about (found twice: X1's crew,
  -- S7's spill). Water is tested on purpose, in W1's and W2's own lakes.
  local tiles = {}
  for _, lane in ipairs({{-20, 480, ROW_A}, {-20, 420, ROW_B}, {-20, 380, ROW_C}}) do
    for x = lane[1], lane[2] do
      for y = lane[3] - 14, lane[3] + 20 do tiles[#tiles + 1] = {name = "grass-1", position = {x, y}} end
    end
    local area = {{lane[1], lane[3] - 14}, {lane[2], lane[3] + 20}}
    for _, e in pairs(surface.find_entities_filtered{area = area, type = {"tree", "cliff", "simple-entity"}}) do
      e.destroy()
    end
  end
  surface.set_tiles(tiles)
  storage.events = {}
  remote.call(SAY, "debug", true)
  check("the family exists (stand-ins or D.1's)", prototypes.entity[BEACHED] ~= nil
        and prototypes.entity[AIRBORNE] ~= nil)
  local burner = prototypes.entity[BEACHED].burner_prototype
  L("bodies:", (burner and burner.fuel_inventory_size == 0) and "D.1's, immobile by prototype"
    or "the harness's stand-ins, held with disabled_by_script")
  local c = clockstate()
  check("idle: nothing due, on_tick not registered", not c.pending and not c.registered, line(c))

  -- S1 BREAK + REPAIR: rare, full kit, toolbelt, walking a 3-leg patrol, a follower
  s.a1 = spawn(0, ROW_A, "rare")
  populate(s.a1, {tag = "S1", toolbelt = true})
  local p = s.a1.position
  for _, d in ipairs({{p.x - 12, p.y}, {p.x - 12, p.y + 12}, {p.x, p.y + 12}}) do s.a1.add_autopilot_destination(d) end
  s.a1.autopilot_patrol_size = 3
  s.f1 = spawn(30, ROW_A)
  s.f1.follow_target = s.a1
  s.f1.follow_offset = {3, 3}

  -- S2 JUMP: takeoff to airborne, a 30-tick arc, landing 8 tiles on. Driver holding a
  -- direction, a follower, a narration note and a bubble on screen, a chain pending.
  s.a2 = spawn(100, ROW_A)
  s.c2 = populate(s.a2, {tag = "S2", toolbelt = true})
  s.f2 = spawn(130, ROW_A)
  s.f2.follow_target = s.a2
  s.f2.follow_offset = {-2, 4}
  -- S2b: a jump under autopilot drops the queue (autopilot = false)
  s.a2b = spawn(160, ROW_A)
  s.a2b.add_autopilot_destination({s.a2b.position.x + 30, s.a2b.position.y})

  -- S3 DRIFT: a half-size body. S4 TWO SWAPS IN ONE TICK vehicle to vehicle, disabled by
  -- "another mod", toolbelt grown. S4b jamaltron -> beached -> jamaltron in one tick.
  s.a3 = spawn(200, ROW_A)
  populate(s.a3, {tag = "S3"})
  s.a4 = spawn(260, ROW_A)
  populate(s.a4, {tag = "S4", toolbelt = true})
  s.a4b = spawn(300, ROW_A)
  populate(s.a4b, {tag = "S4b", toolbelt = true})

  -- S5 FILTERS: a beached body takes damage and speaks. S6 RE-ENTRY. S7 SPILL.
  s.a7, s.a8, s.a9 = spawn(340, ROW_A), spawn(380, ROW_A), spawn(420, ROW_A)
  L("fillers placed in S7's trunk", fill(s.a9))

  -- the verifiers' cases, row B
  s.k1, s.k2 = spawn(0, ROW_B), spawn(40, ROW_B)
  s.k1c = populate(s.k1, {tag = "K1"})
  s.k2c = populate(s.k2, {tag = "K2"})
  s.e1, s.e2 = spawn(80, ROW_B), spawn(120, ROW_B)
  s.e1c = populate(s.e1, {tag = "E1"})
  s.e2c = populate(s.e2, {tag = "E2"})
  s.f1a, s.f1b = spawn(160, ROW_B), spawn(200, ROW_B)
  populate(s.f1a, {tag = "F1a", toolbelt = true})
  populate(s.f1b, {tag = "F1b", toolbelt = true})
  s.x6 = spawn(240, ROW_B)
  populate(s.x6, {tag = "X6"})
  s.bb = spawn(280, ROW_B)
  s.j3 = spawn(320, ROW_B)
  s.om = spawn(360, ROW_B)
end)

at(1, function(s)
  for _, e in ipairs({s.a1, s.a2, s.a4, s.a4b, s.f1a, s.f1b}) do
    local t = e.get_inventory(TRUNK)
    check("kit: the toolbelt grew the trunk (" .. e.entity_label .. ")",
          #t == e.prototype.get_inventory_size(TRUNK, e.quality) + 10, #t)
    t[#t].set_stack{name = "sulfur", count = 33}             -- only a toolbelt slot holds this
  end
  -- FULL trunks: a body whose toolbelt has not grown yet has no room for the last 10 slots.
  L("fillers placed: S1", fill(s.a1), "S4", fill(s.a4), "S4b", fill(s.a4b), "F1a", fill(s.f1a),
    "F1b", fill(s.f1b), "X6", fill(s.x6))
  s.c2.walking_state = {walking = true, direction = defines.direction.south}
end)
at(2, function(s) s.a4.disabled_by_script = true end)

-- S1: BREAK -------------------------------------------------------------------------------
at(30, function(s)
  local before = snapshot(s.a1)
  local st
  s.b1, st = hop("S1 break", s.a1, BEACHED, {reason = "break"})
  check("S1 break returned the new body", s.b1 ~= nil and s.b1.valid and s.b1.name == BEACHED and st == "ok",
        who(s.b1) .. " " .. tostring(st))
  check("S1 old body gone", not s.a1.valid)
  compare("S1 break t+0", before, snapshot(s.b1), {t0 = true, skip = {custom_status = true}})
  local cs = s.b1.custom_status
  check("S1 break t+0 custom_status is the beached body's own, not the one he had",
        cs ~= nil and type(cs.label) == "table" and cs.label[1] == "jamaltron-status.beached", line(cs))
  check("S1 break t+0 NOT disabled (a toolbelt needs the tick, and D.1's body never is)",
        s.b1.disabled_by_script == false)
  check("S1 break t+0 the 10 toolbelt slots wait in the stash", state(s.b1).stash == 1
        and #s.b1.get_inventory(TRUNK) == 128, line(state(s.b1)) .. " trunk " .. #s.b1.get_inventory(TRUNK))
  local c = clockstate()
  check("S1 break t+0 t+1 work is armed on the clock", c.pending and c.registered, line(c))
  local fo = s.f1.follow_offset
  check("S1 follower re-pointed, offset kept", s.f1.follow_target == s.b1
        and (fo.x or fo[1]) == 3 and (fo.y or fo[2]) == 3,
        who(s.f1.follow_target) .. line(fo))
  local rep, des, bui = events("S1 break", "replaced"), events("S1 break", "destroy"), events("S1 break", "built")
  check("S1 on_spidertron_replaced once, both bodies valid, B not yet filled, reason carried",
        #rep == 1 and rep[1].old.valid and rep[1].new.valid and rep[1].new.items == 0
        and rep[1].old.items > 0 and rep[1].reason == "break", line(rep))
  check("S1 script_raised_destroy: old body, still valid, already empty", #des == 1 and des[1].entity.valid
        and des[1].entity.name == VEHICLE and des[1].entity.items == 0, line(des))
  check("S1 script_raised_built: the beached body, seated and full", #bui == 1 and bui[1].entity.name == BEACHED
        and bui[1].entity.driver ~= "nil" and bui[1].entity.items > 0, line(bui))
  s.s1 = before
end)
at(31, function(s)
  local b = snapshot(s.b1)
  check("S1 break t+1 trunk grew to 138 and the stash emptied", #s.b1.get_inventory(TRUNK) == 138
        and state(s.b1).stash == 0, #s.b1.get_inventory(TRUNK) .. " " .. line(state(s.b1)))
  check("S1 break t+1 storage point flags", eqv(s.s1.points, b.points), line(s.s1.points) .. " => " .. line(b.points))
  check("S1 break t+1 inventories whole", eqv(s.s1.inv, b.inv))
  check("S1 break t+1 speech record survived on_object_destroyed(old)", b.speech ~= nil and b.speech.breaks == 1)
  local c = clockstate()
  check("S1 break t+1 nothing due, on_tick dropped", not c.pending and not c.registered, line(c))
  s.p1 = s.b1.position
end)
at(59, function(s)
  local moved = dist(s.p1, s.b1.position)
  check("S1 the beached body does not walk his patrol (28 ticks, queue carried)", moved < 0.3
        and #s.b1.autopilot_destinations > 0, moved)
end)
-- S1: REPAIR ------------------------------------------------------------------------------
at(60, function(s)
  local before = snapshot(s.b1)
  s.r1 = hop("S1 repair", s.b1, VEHICLE, {reason = "repair"})
  compare("S1 repair t+0", before, snapshot(s.r1), {t0 = true, skip = {custom_status = true}})
  check("S1 repair clears the beached status", s.r1.custom_status == nil, line(s.r1.custom_status))
  check("S1 repair: follower now on the repaired body", s.f1.follow_target == s.r1)
  check("S1 repair raised destroy(beached) + built(jamaltron)", #events("S1 repair", "destroy") == 1
        and #events("S1 repair", "built") == 1)
end)
at(61, function(s)
  local b = snapshot(s.r1)
  check("S1 repair t+1 enabled", s.r1.disabled_by_script == false)
  -- the round trip against the jamaltron that broke 31 ticks ago
  compare("S1 ROUND TRIP", s.s1, b, {skip = {position = true, orientation = true, autopilot = true,
          stickers = true, grid = true, torso = true, custom_status = true}})
  check("S1 ROUND TRIP patrol intact", b.patrol == 3 and #b.dests >= 1, line(b.dests) .. "/" .. b.patrol)
end)
at(120, function(s)
  local sp = s.r1.speed
  check("S1 walking his patrol again", sp > 0.05, sp)
end)

-- S2: THE JUMP ----------------------------------------------------------------------------
at(29, function(s)
  remote.call(H, "force", s.a2, "jump.04")                   -- narration: the note
  remote.call(H, "force", s.a2, "idle.08")                   -- speech: a bubble, idle.09 pending
end)
at(30, function(s)
  local a = s.a2
  local before = snapshot(a)
  check("S2 kit: note, bubble and a pending chain up", before.speech.note == true
        and before.speech.bubble ~= nil and before.speech.pending == "idle.09", line(before.speech))
  s.b2 = hop("S2 takeoff", a, AIRBORNE, {reason = "takeoff", autopilot = false})
  local b = snapshot(s.b2)
  compare("S2 takeoff t+0", before, b, {t0 = true, skip = {speech = true, operable = true, custom_status = true}})
  check("S2 takeoff: airborne is not operable and shows no status", b.operable == false and b.custom_status == nil,
        tostring(b.operable) .. " " .. line(b.custom_status))
  check("S2 takeoff: the note follows him", b.speech.note == true, line(b.speech))
  check("S2 takeoff: the bubble is said again on the new body",
        b.speech.bubble == "jamaltron-speech-bubble", line(b.speech))
  check("S2 takeoff: the chain is cancelled", b.speech.pending == nil)
  L("S2 takeoff: the driver's walking_state on the airborne body:", line(b.walking))
  check("S2 takeoff: the held direction is written back on his driver for the landing to read",
        b.walking and b.walking.walking == true and b.walking.direction == defines.direction.south, line(b.walking))
  check("S2 takeoff: SILENT airborne - destroy raised, built not", #events("S2 takeoff", "destroy") == 1
        and #events("S2 takeoff", "built") == 0, line(storage.events))
  check("S2 takeoff: the follower tracks the airborne body", s.f2.follow_target == s.b2)
  log("HARNESS never jamaltron speech " .. s.b2.unit_number .. " idle[.]09")
  s.b2b = hop("S2b takeoff", s.a2b, AIRBORNE, {reason = "takeoff", autopilot = false})
  check("S2b a takeoff drops the autopilot queue", #s.b2b.autopilot_destinations == 0
        and s.b2b.follow_target == nil)
end)
at(31, function(s)
  local b = speech(s.b2)
  check("S2 t+1 bubble and note still up (the old ones died with the old body)",
        b.bubble ~= nil and b.note == true, line(b))
  s.p2 = s.b2.position
end)
at(59, function(s)
  local moved = dist(s.p2, s.b2.position)
  check("S2 the airborne body does not walk under the held key (28 ticks)", moved < 0.3, moved)
  L("S2 the driver's walking_state before the landing:", line(s.c2.walking_state))
end)
at(60, function(s)
  local a = s.b2
  local before = snapshot(a)
  local spot = {x = a.position.x + 8, y = a.position.y}
  s.l2 = hop("S2 landing", a, VEHICLE, {reason = "landing", position = spot})
  local b = snapshot(s.l2)
  s.spot2 = spot
  check("S2 landing: exactly on the spot", b.position.x == spot.x and b.position.y == spot.y, line(b.position))
  compare("S2 landing t+0", before, b, {t0 = true, skip = {position = true, operable = true}})
  check("S2 landing: operable again", b.operable == true)
  check("S2 landing: SILENT airborne - built raised, destroy not", #events("S2 landing", "destroy") == 0
        and #events("S2 landing", "built") == 1 and events("S2 landing", "built")[1].entity.items > 0)
  check("S2 landing: the follower is back on the vehicle", s.f2.follow_target == s.l2)
  check("S2 landing: the driver still holds it in the vehicle", s.c2.walking_state.walking == true
        and s.c2.walking_state.direction == defines.direction.south, line(s.c2.walking_state))
end)
at(61, function(s)
  check("S2 landing t+1 ENABLED", s.l2.disabled_by_script == false)
end)
at(90, function(s)
  local moved = dist(s.spot2, s.l2.position)
  check("S2 landed and walking on the held direction", s.l2.speed > 0.02 and moved > 0.5,
        "speed " .. s.l2.speed .. " moved " .. moved)
end)

-- J3: A DISABLED AIRBORNE BODY LANDS ENABLED (the refuter's landing trap: the prototype
-- carried A's disable and he landed frozen for good). opts.disabled forces it whatever D.1 does.
at(100, function(s)
  s.j3a = hop("J3 takeoff", s.j3, AIRBORNE, {reason = "takeoff", autopilot = false, disabled = true})
end)
at(102, function(s)
  check("J3 the airborne body is disabled from t+1", s.j3a.disabled_by_script == true)
end)
at(130, function(s)
  local p = s.j3a.position
  s.j3l = hop("J3 landing", s.j3a, VEHICLE, {reason = "landing", position = {x = p.x + 8, y = p.y}})
end)
at(132, function(s)
  check("J3 the landed jamaltron is ENABLED at t+2", s.j3l.disabled_by_script == false)
  s.j3l.add_autopilot_destination({s.j3l.position.x + 30, s.j3l.position.y})
  s.j3p = s.j3l.position
end)
at(192, function(s)
  local moved = dist(s.j3p, s.j3l.position)
  check("J3 ... and walks to a destination (60 ticks)", moved > 2, moved)
end)

-- S3: DRIFT -------------------------------------------------------------------------------
at(30, function(s)
  s.s3 = snapshot(s.a3)
  s.b3 = hop("S3 drift", s.a3, SMALL, {reason = "test"})
  -- Stacks with no slot in the small body take its free slots; only the FILTERS for slots it
  -- lacks (68, 78) have nowhere to go but the stash.
  check("S3 the small body keeps every item, the stash only the missing slots' filters",
        state(s.b3).stash == 1 and state(s.b3).stashed_items == 0
        and s.b3.get_inventory(TRUNK).get_item_count("iron-gear-wheel") == 42, line(state(s.b3)))
  check("S3 a body the table does not list carries A's custom_status",
        s.b3.custom_status ~= nil and s.b3.custom_status.label == "Test status", line(s.b3.custom_status))
end)
at(60, function(s)
  s.r3 = hop("S3 back", s.b3, VEHICLE, {reason = "test"})
end)
at(61, function(s)
  compare("S3 ROUND TRIP through a drifted body", s.s3, snapshot(s.r3), {bag = true,
          skip = {position = true, orientation = true, autopilot = true, stickers = true, grid = true,
                  custom_status = true}})
end)

-- S4: TWO SWAPS IN ONE TICK, vehicle to vehicle, disabled by another mod, toolbelt grown --
at(30, function(s)
  s.s4 = snapshot(s.a4)
  s.s4e = energies(s.a4)
  check("S4 kit: disabled with a grown toolbelt", s.s4.disabled and s.s4.inv[TRUNK].size == 90, s.s4.inv[TRUNK].size)
  local b = hop("S4 first", s.a4, VEHICLE, {reason = "test"})
  s.b4 = hop("S4 second", b, VEHICLE, {reason = "test"})
  compare("S4 double swap t+0", s.s4, snapshot(s.b4), {t0 = true})
end)
at(31, function(s)
  local b = snapshot(s.b4)
  compare("S4 double swap t+1", s.s4, b, {skip = {stickers = true}})
  local e1 = energies(s.b4)
  L("S4 grid energy: kit", line(s.s4e), "t+1 (one enabled tick)", line(e1))
  s.s4e1 = e1
end)
at(41, function(s)
  -- MEASURED, not judged: exact at t+0 (the compare above), moved by the one enabled tick at
  -- t+1, and still moving at t+11 - a disabled_by_script body's grid keeps running.
  L("S4 grid energy t+11 (disabled since t+1)", line(energies(s.b4)))
end)
-- S4b: jamaltron -> beached -> jamaltron in ONE tick: the target's state wins over the first
-- swap's pending t+1
at(30, function(s)
  local b = hop("S4b first", s.a4b, BEACHED, {reason = "break"})
  s.b4b = hop("S4b second", b, VEHICLE, {reason = "repair"})
end)
at(31, function(s)
  check("S4b t+1 lands as the vehicle: enabled, no status, operable, trunk 90, stash home",
        s.b4b.disabled_by_script == false and s.b4b.custom_status == nil and s.b4b.operable
        and #s.b4b.get_inventory(TRUNK) == 90 and state(s.b4b).stash == 0,
        tostring(s.b4b.disabled_by_script) .. " " .. line(s.b4b.custom_status) .. " "
        .. #s.b4b.get_inventory(TRUNK) .. " " .. line(state(s.b4b)))
end)

-- S5: A BEACHED BODY SPEAKS WHEN HURT (the event filter covers the family) ----------------
at(40, function(s)
  s.b7 = hop("S5", s.a7, BEACHED, {reason = "break"})
end)
at(45, function(s)
  s.b7.damage(100, "enemy")
  local st = speech(s.b7)
  check("S5 a beached Jamal gets his damaged line", st and st.last_id and
        (st.last_id:match("^damaged%.") or st.last_id:match("^low_health%.")) ~= nil, st and st.last_id)
end)

-- S6: RE-ENTRY ----------------------------------------------------------------------------
at(50, function(s)
  storage.reenter = true
  local b, st = hop("S6", s.a8, BEACHED, {reason = "test"})
  check("S6 a handler cannot re-swap either body mid-swap", b ~= nil and b.valid and st == "ok"
        and storage.reenter_old == "refused" and storage.reenter_new == "refused",
        tostring(storage.reenter_old) .. " " .. tostring(storage.reenter_new))
end)

-- S7: A DESTROYED BODY SPILLS ITS STASH ---------------------------------------------------
at(55, function(s)
  s.b9 = hop("S7", s.a9, SMALL, {reason = "test"})
  s.p9 = s.b9.position
  check("S7 the 40 slots a half-size trunk lacks are stashed", state(s.b9).stashed_items == 40, line(state(s.b9)))
  s.stashes = state().stash
  s.b9.destroy()
end)
at(57, function(s)
  local n = ground(s.p9, 30)
  check("S7 destroyed with a stash: all 40 on the ground", n == 40, n)
  check("S7 ... and its stash is gone", state().stash == s.stashes - 1, s.stashes .. " => " .. line(state()))
end)

-- S8: AN ERROR BEFORE CREATE LEAVES NO GUARD BEHIND (a stuck one would desync a joining client)
at(65, function(s)
  s.a10 = spawn(460, ROW_A)
  local ok, err = pcall(remote.call, H, "swap", s.a10, "no-such-body", {reason = "test"})
  check("S8 a bad target errors loudly", not ok and tostring(err):find("no-such-body", 1, true) ~= nil, err)
  check("S8 ... and leaves the old body whole", s.a10.valid)
  local b = hop("S8", s.a10, BEACHED, {reason = "test"})
  check("S8 ... and the next swap of it is not refused", b ~= nil and b.valid)
end)

-- K1: A LISTENER KILLS THE NEW BODY at on_spidertron_replaced - before anything left A -----
at(70, function(s)
  local a = s.k1
  local pos, n0, bag0 = a.position, total(a), bag(a)
  storage.kill = "replaced"
  local b, st = hop("K1", a, BEACHED, {reason = "break"})
  storage.kill = nil
  check("K1 the swap reports it FAILED, harmless (not lost)", b == nil and st == "failed", who(b) .. " " .. tostring(st))
  check("K1 A is whole: every stack, both people, the record, the name_tag", a.valid and total(a) == n0
        and eqv(bag(a), bag0) and a.get_driver() == s.k1c and a.get_passenger() ~= nil
        and speech(a) ~= nil and speech(a).breaks == 1 and a.name_tag == "jamal-K1",
        a.valid and (total(a) .. "/" .. n0 .. " driver " .. who(a.get_driver()) .. " tag " .. tostring(a.name_tag)
                     .. " speech " .. line(speech(a))) or "A invalid")
  local here = bodies_at(pos, 5)
  check("K1 no second body, nothing spilled", #here == 1 and here[1] == a and ground(pos, 8) == 0,
        #here .. " bodies, ground " .. ground(pos, 8))
  s.k1_pos = pos
end)
at(72, function(s)
  local b, st = hop("K1 after", s.k1, BEACHED, {reason = "break"})
  check("K1 ... no guard left behind: the next swap goes", b ~= nil and st == "ok", tostring(st))
end)

-- K2: A LISTENER KILLS THE NEW BODY at script_raised_built - after the trunk moved ---------
at(75, function(s)
  local a = s.k2
  local pos = a.position
  storage.kill = "built"
  local b, st = hop("K2", a, BEACHED, {reason = "break"})
  storage.kill = nil
  check("K2 the swap reports him LOST", b == nil and st == "lost", who(b) .. " " .. tostring(st))
  local here = bodies_at(pos, 5)
  check("K2 no empty Jamal left standing", not a.valid and #here == 0, #here .. " bodies")
  check("K2 the people are out, not destroyed", s.k2c.valid and s.k2c.vehicle == nil)
  L("K2 items on the ground after a listener destroyed the full body (none expected - they go with it):",
    ground(pos, 8))
end)
at(77, function(s)
  local c = census()
  check("K2 t+2 no speech record points at a dead body", c.dead == 0 and c.mismatched == 0, line(c))
end)

-- E1: AN ERROR AFTER THE TRUNK MOVED (a script_raised_destroy listener throws) -------------
at(80, function(s)
  local a = s.e1
  local pos, n0, bag0 = a.position, total(a), bag(a)
  storage.label, storage.boom = "E1", "destroy"
  local ok, err = pcall(remote.call, H, "swap", a, BEACHED, {reason = "break"})
  storage.label, storage.boom = nil, nil
  check("E1 the error reaches the caller", not ok and tostring(err):find("harness boom", 1, true) ~= nil, err)
  local here = bodies_at(pos, 5)
  local b = here[1]
  check("E1 ONE Jamal: the new body, finished forward, holding everything",
        #here == 1 and b.name == BEACHED and not a.valid and total(b) == n0 and eqv(bag(b), bag0)
        and b.get_driver() == s.e1c and speech(b) ~= nil and speech(b).breaks == 1,
        #here .. " bodies " .. (b and (who(b) .. " " .. total(b) .. "/" .. n0 .. " " .. who(b.get_driver())) or ""))
  s.e1b = b
end)
at(81, function(s)
  local b = s.e1b
  check("E1 t+1 ran for it (stash home, nothing due)", b and b.valid and state(b).stash == 0 and state(b).due == 0,
        b and line(state(b)))
  local nb, st = hop("E1 after", b, VEHICLE, {reason = "repair"})
  check("E1 ... no guard left behind: the next swap goes", nb ~= nil and st == "ok", tostring(st))
end)
-- E2: AN ERROR BEFORE THE MOVE (an on_spidertron_replaced listener throws) -----------------
at(85, function(s)
  local a = s.e2
  local pos, n0 = a.position, total(a)
  storage.label, storage.boom = "E2", "replaced"
  local ok, err = pcall(remote.call, H, "swap", a, BEACHED, {reason = "break"})
  storage.label, storage.boom = nil, nil
  check("E2 the error reaches the caller", not ok and tostring(err):find("harness boom", 1, true) ~= nil, err)
  local here = bodies_at(pos, 5)
  check("E2 ONE Jamal: A, untouched", #here == 1 and here[1] == a and total(a) == n0
        and a.get_driver() == s.e2c and a.name_tag == "jamal-E2", #here .. " bodies")
end)

-- F1: A FAILED SECOND SWAP IN THE SAME TICK KEEPS THE FIRST ONE'S t+1 ---------------------
at(90, function(s)
  s.f1ab = hop("F1a first", s.f1a, BEACHED, {reason = "break", disabled = true})
  local ok = pcall(remote.call, H, "swap", s.f1ab, "no-such-body", {reason = "test"})
  check("F1a the second swap errored", not ok)
  s.f1bb = hop("F1b first", s.f1b, BEACHED, {reason = "break", disabled = true})
  storage.kill = "replaced"
  local b, st = hop("F1b second", s.f1bb, VEHICLE, {reason = "repair"})
  storage.kill = nil
  check("F1b the second swap failed", b == nil and st == "failed", tostring(st))
end)
at(91, function(s)
  for _, k in ipairs({"f1ab", "f1bb"}) do
    local e = s[k]
    check("F1 " .. k .. " t+1 still landed: disabled, trunk 90, stash home", e.valid and e.disabled_by_script == true
          and #e.get_inventory(TRUNK) == 90 and state(e).stash == 0,
          e.valid and (tostring(e.disabled_by_script) .. " " .. #e.get_inventory(TRUNK) .. " " .. line(state(e))) or "invalid")
  end
end)

-- X6: EQUIPMENT THAT DOES NOT FIT A SMALLER GRID, WITH A FULL TRUNK -----------------------
at(94, function(s)
  -- the re-sort moved the rare iron into its filtered slot and freed one: top it up
  L("X6 top-up fillers", fill(s.x6))
end)
at(95, function(s)
  local a = s.x6
  local pos, bag0 = a.position, bag(a)
  check("X6 kit: the trunk is full", a.get_inventory(TRUNK).count_empty_stacks() == 0)
  local b = hop("X6", a, SMALLGRID, {reason = "test"})
  s.x6b, s.x6p, s.x6bag = b, pos, bag0
  check("X6 t+0 every stack of trunk, ammo and trash is in the new body", eqv(bag(b), bag0),
        #bag0 .. " => " .. #bag(b))
  local fr, ex = ground(pos, 30, "fission-reactor-equipment"), ground(pos, 30, "exoskeleton-equipment")
  check("X6 t+0 the reactor and exoskeleton that did not fit are on the ground beside him (a full trunk)",
        fr == 1 and ex == 1, "reactor " .. fr .. " exo " .. ex .. " grid " .. #b.grid.equipment)
end)
at(97, function(s)
  local now = bag(s.x6b)
  ---on the ground, or looted by his crew (spill_item_stack{enable_looted} lets a character in a
  ---seat pick it up - measured: both were in a pocket within 2 ticks)
  local function found(name)
    local n = ground(s.x6p, 30, name)
    for _, c in ipairs({s.x6b.get_driver(), s.x6b.get_passenger()}) do
      if c and c.object_name == "LuaEntity" then
        n = n + c.get_main_inventory().get_item_count(name)
      end
    end
    return n
  end
  local fr, ex = found("fission-reactor-equipment"), found("exoskeleton-equipment")
  local have, missing, extra = {}, {}, {}
  for _, x in ipairs(now) do have[x] = (have[x] or 0) + 1 end
  for _, x in ipairs(s.x6bag) do
    if (have[x] or 0) > 0 then have[x] = have[x] - 1 else missing[#missing + 1] = x end
  end
  for x, n in pairs(have) do if n > 0 then extra[#extra + 1] = x end end
  L("X6 t+2 on the ground: reactor", ground(s.x6p, 30, "fission-reactor-equipment"), "exo",
    ground(s.x6p, 30, "exoskeleton-equipment"))
  check("X6 t+2 still whole (the two items on the ground or in his crew's pockets)", #missing == 0 and #extra == 0 and fr == 1 and ex == 1,
        "missing " .. line(missing):sub(1, 300) .. " extra " .. line(extra):sub(1, 300) .. " reactor " .. fr .. " exo " .. ex)
end)

-- BURN: MODDED BURNER EQUIPMENT KEEPS ITS FUEL -------------------------------------------
at(100, function(s)
  local a = s.bb
  local eq = a.grid.put{name = BURNER, position = {0, 0}}
  local burner = eq.burner
  burner.inventory[1].set_stack{name = "coal", count = 5}
  burner.inventory[2].set_stack{name = "wood", count = 3}
  burner.currently_burning = "coal"
  burner.remaining_burning_fuel = burner.remaining_burning_fuel / 2
  local want = {remaining = burner.remaining_burning_fuel, heat = burner.heat}
  local b = hop("BURN", a, BEACHED, {reason = "break"})
  local got
  for _, q in pairs(b.grid.equipment) do if q.name == BURNER then got = q end end
  local gb = got and got.burner
  local cb = gb and gb.currently_burning
  local cbname = cb and (type(cb.name) == "string" and cb.name or cb.name.name)
  check("BURN fuel slots, what is burning and how much is left all rode", gb ~= nil
        and gb.inventory[1].valid_for_read and gb.inventory[1].name == "coal" and gb.inventory[1].count == 5
        and gb.inventory[2].valid_for_read and gb.inventory[2].name == "wood" and gb.inventory[2].count == 3
        and cbname == "coal" and near(gb.remaining_burning_fuel, want.remaining, 1),
        gb and (line(item_of(gb.inventory[1])) .. line(item_of(gb.inventory[2])) .. " " .. tostring(cbname) .. " "
                .. gb.remaining_burning_fuel .. " vs " .. want.remaining) or "no burner on the new body")
end)

-- OM: ANOTHER MOD SWAPS HIM ITS OWN WAY (create with raise_built, raise the event, destroy) --
at(105, function(s)
  local a = s.om
  remote.call(H, "force", a, "idle.08")                     -- a bubble up on him
  local new = a.surface.create_entity{name = VEHICLE, position = a.position, force = a.force, raise_built = true}
  local fresh = speech(new)
  L("OM the other mod's body got its own record from our built line:", fresh and fresh.last_id)
  script.raise_event("on_spidertron_replaced", {old_spidertron = a, new_spidertron = new})
  a.destroy()
  local st = speech(new)
  local bubbles = new.surface.count_entities_filtered{name = "jamaltron-speech-bubble", position = new.position, radius = 10}
  check("OM his record moved onto the other mod's body, and ONE bubble is on him",
        st ~= nil and st.breaks == 0 and st.last_id == "idle.08" and bubbles == 1, line(st) .. " bubbles " .. bubbles)
end)

-- P1: A PROXY CONTAINER AIMED AT HIM FOLLOWS HIM (E.6: Spidertron Patrols' dock is one, and its
-- target went nil for good on a swap while Patrols believed him docked). Base's hidden
-- proxy-container stands in, on his trunk; a second one aimed at a chest beside him must not move.
local P_X, P_Y = 400, ROW_B
at(106, function(s)
  local surface = game.surfaces[1]
  s.p = surface.create_entity{name = VEHICLE, position = {P_X + 0.5, P_Y + 0.5}, force = "player"}
  s.pchest = surface.create_entity{name = "wooden-chest", position = {P_X + 2.5, P_Y + 0.5}, force = "player"}
  s.pdock = surface.create_entity{name = "proxy-container", position = {P_X + 0.5, P_Y + 0.5}, force = "player"}
  s.pother = surface.create_entity{name = "proxy-container", position = {P_X + 1.5, P_Y + 1.5}, force = "player"}
  s.pdock.proxy_target_entity, s.pdock.proxy_target_inventory = s.p, TRUNK
  s.pother.proxy_target_entity, s.pother.proxy_target_inventory = s.pchest, defines.inventory.chest
  check("P1 kit: one proxy on his trunk, one on the chest beside him",
        s.pdock.proxy_target_entity == s.p and s.pother.proxy_target_entity == s.pchest)
end)
for i, h in ipairs({{BEACHED, "break"}, {VEHICLE, "repair"}}) do
  at(106 + i, function(s)
    local b, st = hop("P1 " .. h[2], s.p, h[1], {reason = h[2]})
    check("P1 " .. h[2] .. ": the proxy on him now targets the new body's trunk",
          b ~= nil and st == "ok" and s.pdock.proxy_target_entity == b and s.pdock.proxy_target_inventory == TRUNK,
          who(b) .. " " .. tostring(st) .. " target " .. who(s.pdock.proxy_target_entity) .. " inv "
          .. tostring(s.pdock.proxy_target_inventory))
    check("P1 " .. h[2] .. ": a proxy aimed elsewhere is left alone",
          s.pother.proxy_target_entity == s.pchest and s.pother.proxy_target_inventory == defines.inventory.chest,
          who(s.pother.proxy_target_entity))
    s.p = b or s.p
  end)
end

-- W1: OVER DEEP WATER. He straddles lakes and rests with his body over one at every shore
-- stall, and there set_driver cannot move a character straight across - no ground to step out
-- onto - so it is refused silently (measured: a random map put X1 over a lake once in ~15 runs
-- and his crew was left standing in it). A lake of its own, so this never rides the map roll.
local W_X, W_Y = 460, ROW_B
at(110, function(s)
  local surface = game.surfaces[1]
  local tiles = {}
  for x = W_X - 16, W_X + 16 do
    for y = W_Y - 16, W_Y + 16 do
      tiles[#tiles + 1] = {name = x > W_X + 14 and "grass-1" or "deepwater", position = {x, y}}
    end
  end
  surface.set_tiles(tiles)
  s.w = surface.create_entity{name = VEHICLE, position = {W_X + 0.5, W_Y + 0.5}, force = "player"}
  s.wd = surface.create_entity{name = "character", position = {W_X + 16, W_Y}, force = "player"}
  s.wp = surface.create_entity{name = "character", position = {W_X + 16, W_Y + 2}, force = "player"}
  s.w.set_driver(s.wd)
  s.w.set_passenger(s.wp)
  check("W1 kit: over deep water, crew aboard", surface.get_tile(s.w.position.x, s.w.position.y).name == "deepwater"
        and s.w.get_driver() == s.wd and s.w.get_passenger() == s.wp)
end)
local W_HOPS = {
  {BEACHED, {reason = "break"}},
  {VEHICLE, {reason = "repair"}},
  {AIRBORNE, {reason = "takeoff", autopilot = false}},
  {VEHICLE, {reason = "landing", position = {W_X + 20.5, W_Y + 0.5}}},  -- onto the grass
}
for i, h in ipairs(W_HOPS) do
  at(110 + i, function(s)
    local b, st = hop("W1 " .. h[2].reason, s.w, h[1], h[2])
    check("W1 " .. h[2].reason .. " over deep water: driver and passenger seated in the new body",
          b ~= nil and st == "ok" and b.get_driver() == s.wd and b.get_passenger() == s.wp,
          who(b) .. " " .. tostring(st) .. " driver " .. who(b and b.get_driver()) .. " passenger "
          .. who(b and b.get_passenger()) .. " | " .. who(s.wd) .. " in " .. who(s.wd.vehicle))
    s.w = b or s.w
  end)
end
-- W2: A BODY DIES OVER A LAKE HOLDING A STASH. forget() spills where he was last seen, and
-- over water the engine carries it to the nearest free ground however far that is - measured
-- in a 71x71 lake of its own at two distances from its edge, counted SURFACE-WIDE because the
-- random map around the lake can be water too (one roll put the nearest ground 80.6 tiles out).
local L2_X, L2_Y, L2_R = 540, ROW_B, 35
at(112, function()
  local tiles = {}
  for x = L2_X - L2_R, L2_X + L2_R do
    for y = L2_Y - L2_R, L2_Y + L2_R do tiles[#tiles + 1] = {name = "deepwater", position = {x, y}} end
  end
  game.surfaces[1].set_tiles(tiles)
end)
for k, out in ipairs({10, L2_R}) do
  at(116 + 4 * k, function(s)                         -- spilled a tick later, apart
    local e = game.surfaces[1].create_entity{name = VEHICLE, force = "player",
                                              position = {L2_X - L2_R + out + 0.5, L2_Y + 0.5}}
    fill(e)
    local b = hop("W2 " .. k, e, SMALL, {reason = "test"})
    local stashed = state(b).stashed_items
    local p = b.position
    for _, it in pairs(game.surfaces[1].find_entities_filtered{name = "item-on-ground"}) do
      it.destroy()                                     -- every earlier lane's spill is judged by now
    end
    b.destroy()
    s["w2_" .. k] = {p = p, stashed = stashed}
  end)
  at(118 + 4 * k, function(s)
    local w = s["w2_" .. k]
    local surface = game.surfaces[1]
    local far, n, wet = 0, 0, 0
    for _, it in pairs(surface.find_entities_filtered{name = "item-on-ground"}) do
      n = n + it.stack.count
      far = math.max(far, dist(w.p, it.position))
      if surface.get_tile(it.position.x, it.position.y).name == "deepwater" then wet = wet + it.stack.count end
      it.destroy()                                     -- the next W2 counts only its own
    end
    L("W2", k, "died", out, "tiles from the lake's edge holding", w.stashed, "stashed: on the ground:", n,
      "farthest", string.format("%.1f", far), "on deepwater:", wet)
    check("W2 " .. k .. " nothing stashed is lost when he dies " .. out .. " tiles into a lake",
          w.stashed == 40 and n == 40, w.stashed .. " stashed, " .. n .. " found")
    check("W2 " .. k .. " ... and all of it came ashore", wet == 0, wet .. " on deep water")
  end)
end

at(115, function(s)
  local wet = 0
  for _, c in pairs(game.surfaces[1].find_entities_filtered{name = "character", position = {W_X, W_Y}, radius = 22}) do
    if c.vehicle == nil then wet = wet + 1 end
  end
  check("W1 nobody left standing in the lake", wet == 0, wet)
end)

-- COST: a jump is two swaps; one a tick here, a body each, profiled --------------------------
local COST_N = 40
at(130, function(s)
  s.cost = {light = spawn(0, ROW_C), rare = spawn(40, ROW_C, "rare"), bare = spawn(80, ROW_C)}
  populate(s.cost.light, {tag = "cost-light"})
  populate(s.cost.rare, {tag = "cost-rare", toolbelt = true})
  s.prof = {}
end)
at(131, function(s)
  L("cost: rare trunk filled with", fill(s.cost.rare), "more stacks")
  for kind in pairs(s.cost) do s.prof[kind] = helpers.create_profiler(true) end
end)
for i = 1, COST_N do
  at(131 + i, function(s)
    storage.quiet = true
    for kind, e in pairs(s.cost) do
      local p = helpers.create_profiler()
      local b = swap(e, e.name == VEHICLE and AIRBORNE or VEHICLE, {reason = "cost"})
      p.stop()
      s.prof[kind].add(p)
      s.cost[kind] = b
    end
    storage.quiet = nil
  end)
end
at(132 + COST_N, function(s)
  local names = {light = "light kit (~11 stacks, normal)", rare = "rare full trunk (138 slots, toolbelt)",
                 bare = "bare"}
  for kind, p in pairs(s.prof) do
    p.divide(COST_N)
    log({"", "SWAP COST ", names[kind], " per swap: ", p})
  end
end)

-- X1: 200 SWAPS, ONE A TICK - no drift, no leaks -----------------------------------------
local X1_AT = 180
at(X1_AT, function(s)
  s.x1 = spawn(200, ROW_C, "rare")
  populate(s.x1, {tag = "X1", toolbelt = true})
  local p = s.x1.position
  for _, d in ipairs({{p.x - 12, p.y}, {p.x - 12, p.y + 12}, {p.x, p.y + 12}}) do s.x1.add_autopilot_destination(d) end
  s.x1.autopilot_patrol_size = 3
  s.x1f = spawn(p.x + 10, p.y + 10)
  s.x1f.follow_target = s.x1
  s.x1f.follow_offset = {3, -3}
end)
at(X1_AT + 1, function(s)
  local t = s.x1.get_inventory(TRUNK)
  t[#t].set_stack{name = "sulfur", count = 33}
  fill(s.x1)
end)
at(X1_AT + 28, function(s)
  remote.call(H, "force", s.x1, "jump.04")
  remote.call(H, "force", s.x1, "idle.08")
end)
local function scriptinvs()
  local n = 0
  for _, list in pairs(game.get_script_inventories("jamaltron")) do
    for _, inv in pairs(list) do if inv.valid then n = n + 1 end end
  end
  return n
end
at(X1_AT + 29, function(s)
  s.x1_before = snapshot(s.x1)
  s.x1_bag = bag(s.x1)
  s.x1_units = {s.x1.unit_number}
  s.x1_said, s.x1_bad = {}, {}
  s.x1_crew = {s.x1.get_driver(), s.x1.get_passenger()}
  s.x1_prof = helpers.create_profiler(true)
  check("X1 kit: note, bubble, pending chain, sticker up", s.x1_before.speech.note and s.x1_before.speech.bubble
        and s.x1_before.speech.pending == "idle.09" and #s.x1_before.stickers == 1, line(s.x1_before.speech))
end)
local X1_CYCLE = {
  {BEACHED, {reason = "break"}},
  {VEHICLE, {reason = "repair"}},
  {AIRBORNE, {reason = "takeoff"}},        -- the queue rides: this is the carry, not E's takeoff
  {VEHICLE, {reason = "landing"}},
}
for i = 1, 200 do
  at(X1_AT + 29 + i, function(s)
    local step = X1_CYCLE[(i - 1) % 4 + 1]
    local old = s.x1
    storage.quiet, storage.label = true, "X1"
    local before = speech(old)
    local p = helpers.create_profiler()
    local b, st = swap(old, step[1], step[2])
    p.stop()
    storage.quiet, storage.label = nil, nil
    s.x1_prof.add(p)
    if b and b.valid then
      local sp = speech(b)
      if sp and sp.last_tick == game.tick and (before == nil or before.last_tick ~= game.tick) then
        s.x1_said[#s.x1_said + 1] = i .. ":" .. sp.last_id
      end
    end
    if b and b.valid and not s.x1_crew_lost
        and (b.get_driver() ~= s.x1_crew[1] or b.get_passenger() ~= s.x1_crew[2]) then
      local d, c = s.x1_crew[1], s.x1_crew[2]
      s.x1_crew_lost = i .. ":" .. step[1] .. " driver " .. who(b.get_driver()) .. " passenger "
        .. who(b.get_passenger()) .. " | " .. who(d) .. " in " .. who(d.valid and d.vehicle or nil)
        .. " at " .. line(d.valid and d.position or nil) .. ", " .. who(c) .. " in "
        .. who(c.valid and c.vehicle or nil) .. " | body at " .. line(b.position)
      L("X1 the crew left him at swap", s.x1_crew_lost)
    end
    if not (b and b.valid and b.name == step[1] and st == "ok" and not old.valid) then
      s.x1_bad[#s.x1_bad + 1] = i .. ":" .. who(b) .. ":" .. tostring(st)
    else
      s.x1 = b
      s.x1_units[#s.x1_units + 1] = b.unit_number
    end
  end)
end
at(X1_AT + 231, function(s)
  local e = s.x1
  local after = snapshot(e)
  s.x1_prof.divide(200)
  log({"", "SWAP COST X1, rare full trunk + patrol + follower + sticker + proxy + note + bubble, per swap (200, one a tick): ",
       s.x1_prof})
  check("X1 all 200 swaps returned the right body and killed the old one", #s.x1_bad == 0, line(s.x1_bad))
  check("X1 driver and passenger rode all 200", s.x1_crew_lost == nil, s.x1_crew_lost)
  check("X1 no speech line said DURING any of the 200 swaps (the built guard)", #s.x1_said == 0,
        #s.x1_said .. " lines: " .. line(s.x1_said):sub(1, 400))
  compare("X1 after 200 swaps", s.x1_before, after, {skip = {position = true, orientation = true, torso = true,
          stickers = true, custom_status = true, speech = true, autopilot = true}})
  check("X1 every stack still his", eqv(bag(e), s.x1_bag), #s.x1_bag .. " => " .. #bag(e))
  check("X1 custom_status cleared by the last landing", after.custom_status == nil, line(after.custom_status))
  check("X1 patrol intact (3 waypoints, patrol 3)", after.patrol == 3 and #after.dests == 3,
        line(after.dests) .. "/" .. after.patrol)
  check("X1 trunk 128+10 after 200 swaps", after.inv[TRUNK].size == 138, after.inv[TRUNK].size)
  local x, y = s.x1_before.speech, after.speech or {}
  table.sort(x.fired); table.sort(y.fired or {})
  check("X1 speech record carried (breaks, fork, fired, recent, last_id)", x.breaks == y.breaks and x.fork == y.fork
        and eqv(x.fired, y.fired) and x.recent == y.recent and x.last_id == y.last_id, line(x) .. " => " .. line(y))
  check("X1 the chain died at the first swap and never came back", y.pending == nil, line(y))
  local ttl0 = s.x1_before.stickers[1] and s.x1_before.stickers[1][2]
  local ttl1 = after.stickers[1] and after.stickers[1][2]
  check("X1 exactly one slowdown sticker survives", #after.stickers == 1, line(after.stickers))
  check("X1 sticker ttl ran down with the clock (+-5 over 202 ticks)", ttl0 and ttl1 and math.abs((ttl0 - 202) - ttl1) <= 5,
        tostring(ttl0) .. " -> " .. tostring(ttl1))
  local c = census()
  check("X1 no dead or mis-keyed speech records", c.dead == 0 and c.mismatched == 0, line(c))
  local live = {}
  for _, u in ipairs(c.units) do live[u] = true end
  local stale = 0
  for k = 1, #s.x1_units - 1 do if live[s.x1_units[k]] then stale = stale + 1 end end
  check("X1 none of the 200 dead bodies keeps a speech record, the live one does", stale == 0 and live[e.unit_number] == true,
        "stale " .. stale .. " live " .. tostring(live[e.unit_number]))
  local bubbles = e.surface.count_entities_filtered{name = "jamaltron-speech-bubble", position = e.position, radius = 30}
  check("X1 at most one speech bubble on him", bubbles <= 1, bubbles)
  local mine = 0
  for _, ro in pairs(rendering.get_all_objects("jamaltron")) do
    local t = ro.target
    if t and t.entity == e then mine = mine + 1 end
  end
  check("X1 exactly one narration note on him", mine == 1, mine)
  local fams = 0
  for _, f in ipairs(bodies_at(e.position, 20)) do
    if f ~= s.x1f then fams = fams + 1 end
  end
  check("X1 exactly one Jamal body left near him (besides his follower)", fams == 1, fams)
  check("X1 exactly one item-request-proxy on him", #proxies(e) == 1, #proxies(e))
  check("X1 nothing spilled", ground(e.position, 20) == 0, ground(e.position, 20))
  local fo = s.x1f.follow_offset
  check("X1 follower on the final body, offset kept", s.x1f.follow_target == e and (fo.x or fo[1]) == 3
        and (fo.y or fo[2]) == -3, who(s.x1f.follow_target) .. line(fo))
  check("X1 grid equipment count unchanged", #after.eq == #s.x1_before.eq, #s.x1_before.eq .. " => " .. #after.eq)
  local st = state(e)
  check("X1 no due/stash left on him", st.due == 0 and st.stash == 0, line(st))
  local alt = table.concat(s.x1_units, "|")
  log("HARNESS never jamaltron speech (" .. alt .. ") idle[.]09")
  log("HARNESS never jamaltron speech (" .. alt .. ") built[.]")
end)

-- COST AT SCALE: 1000 spiders on the surface - the follower scan is per-map ------------------
local BIG_AT = X1_AT + 240
at(BIG_AT, function(s)
  local surface = game.surfaces[1]
  local n = 0
  for i = 0, 31 do
    for j = 0, 31 do
      if n < 1000 then
        surface.create_entity{name = "spidertron", position = {-48 + i * 3, -240 + j * 3}, force = "player"}
        n = n + 1
      end
    end
  end
  L("spiders spawned", n)
  s.big = spawn(320, ROW_C)
end)
at(BIG_AT + 2, function(s)
  local names = {}
  for name in pairs(prototypes.get_entity_filtered{{filter = "type", type = "spider-vehicle"}}) do names[#names + 1] = name end
  local p = helpers.create_profiler()
  local hits = 0
  for _ = 1, 20 do
    for _, v in pairs(game.get_vehicles{surface = game.surfaces[1], type = names}) do
      if v.follow_target == s.big then hits = hits + 1 end
    end
  end
  p.stop(); p.divide(20)
  log({"", "SWAP COST the follower scan alone, 1000 spiders on the surface, per swap: ", p})
  s.big_prof = helpers.create_profiler(true)
end)
for i = 1, COST_N do
  at(BIG_AT + 2 + i, function(s)
    local p = helpers.create_profiler()
    local b = swap(s.big, s.big.name == VEHICLE and AIRBORNE or VEHICLE, {reason = "cost"})
    p.stop()
    s.big_prof.add(p)
    s.big = b
  end)
end
at(BIG_AT + 3 + COST_N, function(s)
  s.big_prof.divide(COST_N)
  log({"", "SWAP COST bare, 1000 spiders on the surface, per swap: ", s.big_prof})
end)

-- THE END: nothing left behind anywhere ----------------------------------------------------
at(BIG_AT + 10 + COST_N, function(s)
  local st = state()
  local c = clockstate()
  check("END no script inventory left behind (every stash destroyed when empty)", scriptinvs() == 0, scriptinvs())
  check("END no due entries, no stashes", st.due == 0 and st.stash == 0 and not st.pending, line(st))
  check("END on_tick dropped", not c.registered and not c.pending, line(c))
  local k = census()
  check("END no dead or mis-keyed speech records", k.dead == 0 and k.mismatched == 0, line(k))
  check("END the clock was registered exactly while work was pending, every tick and every "
        .. "on_object_destroyed (" .. tostring(s.clock_seen) .. " looks)", (s.clock_bad or 0) == 0,
        tostring(s.clock_bad) .. " misses, first: " .. tostring(s.clock_first))
  log("HARNESS done " .. tostring(storage.passed))
end)

---The clock invariant (clock.lua): on_tick registered exactly while something is pending. A
---save or a join can land between any two events, so it must hold at every one we can see.
local function look(where)
  local c = clockstate()
  storage.clock_seen = (storage.clock_seen or 0) + 1
  if c.registered ~= c.pending then
    storage.clock_bad = (storage.clock_bad or 0) + 1
    storage.clock_first = storage.clock_first or (where .. " tick " .. game.tick .. " " .. line(c))
  end
end
script.on_event(defines.events.on_object_destroyed, function()
  look("on_object_destroyed")
end)

table.sort(steps, function(x, y) return x.dt < y.dt end)
script.on_event(defines.events.on_tick, function(event)
  local s = storage
  s.start = s.start or event.tick
  local dt = event.tick - s.start
  look("on_tick")
  for _, step in ipairs(steps) do
    if step.dt == dt then
      local ok, err = pcall(step.fn, s)
      if not ok then check("step at dt " .. dt .. " ran", false, err) end
    end
  end
end)
