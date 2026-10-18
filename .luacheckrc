-- luacheck config for jamaltron. Factorio 2.1.x.
--
-- Stock luacheck lints for standard Lua 5.2. Factorio's Lua is 5.2.1 with
-- pieces REMOVED for determinism and pieces ADDED by the engine, and its
-- globals differ per stage. Three things this file encodes:
--   1. the sandbox: io, os, coroutine, loadfile, dofile and arg are gone, and
--      debug/package are cut down to a couple of members
--   2. the additions: string.pack family, math.log10, table.deepcopy/compare
--   3. per-stage globals -- `game` in data.lua is a crash, `data` in
--      control.lua is nil, `mods` at runtime is nil. Per-path stds catch all
--      three.
--
-- Every name below was MEASURED against Factorio 2.1.17 on 2026-09-19 by
-- probing _G/table/string/math/debug/package from a throwaway mod at both
-- stages (headless `--create` with an isolated --mod-directory), then
-- cross-checked against the shipped docs:
--   doc-html/auxiliary/libraries.html  (the sandbox and the additions)
--   doc-html/runtime-api.json          ("global_objects" = the control stage)
-- Do NOT take the fmtk LuaLS bundle as the source of truth here: it declares
-- math.tointeger/type/ult and debug.setcstacklimit, none of which exist in
-- this sandbox.

---------------------------------------------------------------------------
-- The sandbox
---------------------------------------------------------------------------

-- Removed outright. luacheck has no subtraction syntax (`std = "lua52 - os"`
-- is a hard config error), so filter stds.lua52 by hand.
local removed = {
  io = true, os = true, coroutine = true,
  loadfile = true, dofile = true,
  arg = true, -- mods are not scripts; Factorio never sets it
}

---Copy a lua52 module's field set and add Factorio's extras.
---@param name string module name in stds.lua52.read_globals
---@param extra table list of extra field names
local function extended(name, extra)
  local fields = {}
  for field, def in pairs(stds.lua52.read_globals[name].fields) do
    fields[field] = def
  end
  for _, field in ipairs(extra) do fields[field] = {} end
  return { fields = fields }
end

local sandbox = {}
for name, def in pairs(stds.lua52.read_globals) do
  if not removed[name] then sandbox[name] = def end
end

-- Backported from Lua 5.4.6 for binary struct strings (libraries.html).
sandbox.string = extended("string", { "pack", "packsize", "unpack" })

-- log10 survives here even though luacheck's lua52 std drops it as deprecated.
-- tointeger/type/ult are 5.3+ and are NOT present -- measured missing.
sandbox.math = extended("math", { "log10" })

-- core/lualib/util.lua adds these. They are present for the whole data stage
-- because the base mod requires util before any other mod loads; in control.lua
-- they only exist once YOUR file has done require("util"). luacheck cannot see
-- that require, so declaring them here trades a real (but smoke-testable)
-- runtime error for zero false positives on the deepcopy-the-spidertron
-- pattern that runs through this whole mod.
sandbox.table = extended("table", { "deepcopy", "compare" })

-- "only debug.getinfo() and debug.traceback() are available by default"
-- (libraries.html). The other 15 need a command-line flag players won't have.
sandbox.debug = { fields = { getinfo = {}, traceback = {} } }

-- Factorio ships its own package with nothing but `loaded` (measured). Mods
-- legitimately poke at it to force-reload a module, so fields stay writable.
sandbox.package = { fields = { loaded = { read_only = false, other_fields = true } } }

-- Deliberately NOT declared, though the sandbox does still carry them:
-- `unpack` and `loadstring`, the Lua 5.1 spellings. Greenfield code should use
-- table.unpack and load, so leaving them undeclared makes luacheck say so.

stds.factorio = { read_globals = sandbox }

---------------------------------------------------------------------------
-- Stage globals
---------------------------------------------------------------------------

-- Present in BOTH stages.
stds.factorio_shared = {
  read_globals = {
    "defines", "serpent",
    "log", "localised_print", "table_size", -- runtime-api.json global_functions
    -- leaked by core/lualib/util.lua, which assigns them WITHOUT `local`
    -- (verified in the shipped source). Same require caveat as table.deepcopy.
    "util",
    "gram", "grams", "kg", "tons",
    "second", "minute", "hour",
    "meter", "kilometer",
  },
  globals = {
    -- fmtk's debug adapter injects these; writable so debug hooks are fine
    "__DebugAdapter", "__Profiler",
  },
}

-- Data stage: settings*.lua, data*.lua, and everything they require.
stds.factorio_data = {
  globals = {
    -- `data.raw[...] = x` and `data:extend{}` mutate it, and in luacheck only
    -- `globals` permits field writes -- `read_globals` makes them W122.
    "data",
  },
  read_globals = {
    -- startup settings, READ-ONLY at data stage. `settings.global` and
    -- `settings.player` do not exist yet.
    "settings",
    -- data-stage only. At runtime these are nil; use script.active_mods
    -- instead of `mods`. Measured missing at control stage, and absent from
    -- runtime-api.json's global_objects.
    "mods", "feature_flags",
  },
}

-- Control stage: control.lua, scripts/, migrations/.
stds.factorio_control = {
  globals = {
    -- The 2.x save table. NOT `global`: that name is gone in 2.0+, and leaving
    -- it undeclared everywhere is deliberate, so leftover 1.1 code gets W112.
    "storage",
    -- game.speed / game.tick_paused are legitimate writes. Note `game` is nil
    -- in control.lua's own main chunk (measured) -- it only exists inside
    -- on_init/on_load/events. luacheck cannot tell those apart, so top-level
    -- `game` misuse is the smoke test's problem, not this file's.
    "game",
    -- settings.global["x"] = {value=...} is a legitimate runtime write
    "settings",
  },
  read_globals = {
    -- runtime-api.json "global_objects", minus the writable ones above
    "script", "remote", "commands", "rendering", "prototypes", "helpers",
    "rcon",
  },
}

---------------------------------------------------------------------------
-- Wiring
---------------------------------------------------------------------------

std = "factorio+factorio_shared"

-- Prototype tables are legitimately wide; 120 keeps sprite tables readable
-- without inviting 200-column one-liners.
max_line_length = 120

-- A mod is one flat namespace per stage, so an accidental mod-level global is
-- a real collision risk: leave 111/112/113 ON.
codes = true
ranges = true

files["**/settings.lua"]             = { std = "+factorio_data" }
files["**/settings-updates.lua"]     = { std = "+factorio_data" }
files["**/settings-final-fixes.lua"] = { std = "+factorio_data" }
files["**/data.lua"]                 = { std = "+factorio_data" }
files["**/data-updates.lua"]         = { std = "+factorio_data" }
files["**/data-final-fixes.lua"]     = { std = "+factorio_data" }
files["**/prototypes/**/*.lua"]      = { std = "+factorio_data" }

files["**/control.lua"]              = { std = "+factorio_control" }
files["**/scripts/**/*.lua"]         = { std = "+factorio_control" }
files["**/migrations/**/*.lua"]      = { std = "+factorio_control" }

-- The video's director (PLAN G.3) is gated like the mod: its modules are control-stage code
-- the generic patterns above do not name. MEASURED clean when first gated (0/0 in 6 files).
files["tools/harness/jamaltron-video/story.lua"]   = { std = "+factorio_control" }
files["tools/harness/jamaltron-video/camera.lua"]  = { std = "+factorio_control" }
files["tools/harness/jamaltron-video/journal.lua"] = { std = "+factorio_control" }
files["tools/harness/jamaltron-video/set.lua"]     = { std = "+factorio_control" }

-- The rest of tools/ is not gated YET: the older harness mods carried 26 warnings when the
-- director was gated (12 in jamaltron-swap-harness, MEASURED by the G review), and tests/lua is
-- plain Lua under its own runner. Listed one by one, so a NEW harness is gated by default.
exclude_files = {
  ".luacheckrc",
  "tools/tests/**",
  "tools/playtest/**",
  "tools/harness/jamaltron-harness/**",
  "tools/harness/jamaltron-fire-harness/**",
  "tools/harness/jamaltron-jump-harness/**",
  "tools/harness/jamaltron-shot/**",
  "tools/harness/jamaltron-swap-harness/**",
  "assets/source/**",
  ".ls-defs/**",
  "**/.venv/**",
}
