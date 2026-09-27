-- swap.lua's quickbar carry (the player side of a swap): each player's remote slots are scanned
-- ONCE and kept in storage, not 100 get_quick_bar_slot calls per player per swap. The real
-- scripts/swap.lua with fake players; headless has no LuaPlayer, so this is the only gate on it
-- until a play.sh pass.
--
--   lua tools/tests/lua/test_swap_quickbar.lua <repo root>
--
-- Run by tools/tests/test_speech_lua.py, in test_pick.lua's harness shape; Lua 5.2 / 5.4+ / luajit.

local root = arg[1] or "."
package.path = root .. "/mod/jamaltron/?.lua;" .. package.path

defines = {entity_status_diode = {red = 1},
           inventory = {spider_trunk = 1, spider_ammo = 2, spider_trash = 3}}
package.loaded["scripts.speech"] = {}
package.loaded["scripts.clock"] = {}
storage = {}

local swap = require("scripts.swap")

local OLD, NEW, OTHER = {name = "old"}, {name = "new"}, {name = "someone else"}

---A player whose quickbar holds `slots` ({[page * 100 + index] = slot}), counting reads.
local function player(index, slots)
  local p = {index = index, gets = 0, sets = {}, pins = {}}
  p.get_quick_bar_slot = function(page, i)
    p.gets = p.gets + 1
    return slots[page * 100 + i]
  end
  p.set_quick_bar_slot = function(page, i, slot) p.sets[#p.sets + 1] = {page = page, index = i, slot = slot} end
  p.get_pins = function() return p.pins end
  return p
end

local function kit()
  return player(1, {
    [103] = {type = "remote", selection = {OTHER, OLD}},      -- page 1 slot 3: holds him
    [907] = {type = "remote", selection = {OTHER}},           -- page 9 slot 7: a remote, not his
    [204] = {type = "item", item = {}},
  })
end

local tests, names = {}, {}
local function test(name, fn)
  tests[#tests + 1] = fn
  names[#names + 1] = name
end

test("the first swap scans all 100 slots and re-points the remote that held him, only that one", function()
  storage = {}
  local p = kit()
  swap.carry_saved(p, OLD, NEW)
  assert(p.gets >= 100, "scanned " .. p.gets)
  assert(#p.sets == 1 and p.sets[1].page == 1 and p.sets[1].index == 3, "one slot written")
  local sel = p.sets[1].slot.selection
  assert(sel[1] == OTHER and sel[2] == NEW, "re-pointed in place, the rest kept")
end)

test("every later swap reads only the remote slots - 2 calls, not 100", function()
  storage = {}
  local p = kit()
  swap.carry_saved(p, OLD, NEW)
  p.gets, p.sets = 0, {}
  swap.carry_saved(p, NEW, OLD)
  assert(p.gets == 2, "read " .. p.gets)
  assert(#p.sets == 1 and p.sets[1].slot.selection[2] == OLD, "and still re-points")
end)

test("a player with no remote slot costs nothing after the first scan", function()
  storage = {}
  local p = player(2, {[101] = {type = "item", item = {}}})
  swap.carry_saved(p, OLD, NEW)
  p.gets = 0
  for _ = 1, 10 do swap.carry_saved(p, OLD, NEW) end
  assert(p.gets == 0 and #p.sets == 0, "read " .. p.gets)
end)

test("quickbar_changed drops that player's slots: the next swap scans again and finds a new remote", function()
  storage = {}
  local slots = {}
  local p = player(3, slots)
  swap.carry_saved(p, OLD, NEW)
  slots[505] = {type = "remote", selection = {OLD}}          -- the player made a remote of him
  swap.quickbar_changed(4)                                   -- someone else's change
  p.gets = 0
  swap.carry_saved(p, OLD, NEW)
  assert(p.gets == 0 and #p.sets == 0, "another player's change rescanned this one")
  swap.quickbar_changed(3)
  swap.carry_saved(p, OLD, NEW)
  assert(p.gets >= 100 and #p.sets == 1 and p.sets[1].page == 5, "his own change is seen")
  storage = {}
  swap.quickbar_changed(3)                                   -- no swap state yet: harmless
end)

test("the slots live in storage: a reloaded module (a save, a joining peer) does not rescan", function()
  storage = {}
  local p = kit()
  swap.carry_saved(p, OLD, NEW)
  package.loaded["scripts.swap"] = nil
  local again = require("scripts.swap")
  p.gets = 0
  again.carry_saved(p, NEW, OLD)
  assert(p.gets == 2, "read " .. p.gets)
end)

test("a slot that stopped being a remote is skipped, not written", function()
  storage = {}
  local slots = {[103] = {type = "remote", selection = {OLD}}}
  local p = player(5, slots)
  swap.carry_saved(p, OLD, NEW)
  slots[103] = nil                                           -- emptied with no event (a mod)
  p.sets = {}
  swap.carry_saved(p, NEW, OLD)
  assert(#p.sets == 0)
end)

test("pins are re-pointed on every swap, cached slots or not", function()
  storage = {}
  local p = kit()
  local pin = {targets = {OLD}}
  p.pins = {pin}
  swap.carry_saved(p, OLD, NEW)
  assert(pin.targets[1] == NEW)
  swap.carry_saved(p, NEW, OLD)
  assert(pin.targets[1] == OLD)
end)

for i, fn in ipairs(tests) do
  local ok, err = pcall(fn)
  if not ok then
    io.stderr:write("FAIL " .. names[i] .. ": " .. tostring(err) .. "\n")
    os.exit(1)
  end
end
print("ok " .. #tests)
