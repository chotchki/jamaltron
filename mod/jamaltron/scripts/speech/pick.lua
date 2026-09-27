-- The line PICKER (PLAN D.5.1): which row of a pool Jamal says next. Pure arithmetic over the
-- generated catalog (scripts/lines.lua) and one entity's speech record, no game API, so
-- tools/tests runs it under plain lua against the real table.
--
-- The rules are character/lines.md's; each function names the section it implements. This
-- decides WHAT he says. WHETHER (cooldowns, silence windows, a pending chain) is speech.lua's,
-- gated before this runs.

local M = {}

---Cumulative tiers (lines.md, "Tiers are CUMULATIVE"): a row plays at its own tier and
---every tier above it.
M.TIER_RANK = {quiet = 1, normal = 2, unbearable = 3}

---How many recent lines (by GRP) anti-repeat remembers per entity. `legs_break` and `flopping`
---share 15 strings and fire back to back, so the window must outlast a break plus a few
---apology ticks; eight lines is ~two minutes of flopping at the defaults.
M.RECENT = 8

---Does `row` answer the condition this roll was made under? (lines.md, "The `split:` line
---is the whole `SUB` contract".)
---  none     - SUB is advisory, never a fork
---  required - the side the mod reported, exactly; no side reported means no row
---  gated    - `any` (or `-`) always; a value only when the mod reported exactly that value
---@param pool table
---@param row table
---@param cond string?
---@return boolean
local function answers(pool, row, cond)
  if pool.split == "required" then
    return row.sub == cond
  end
  if pool.split == "gated" then
    return row.sub == nil or row.sub == "any" or row.sub == "-" or row.sub == cond
  end
  return true
end
M.answers = answers

---Every row the roll MAY choose, before anti-repeat.
---@param pool table the catalog's pools[key]
---@param verbosity string quiet | normal | unbearable (anything else plays as normal)
---@param cond string? the condition the event reported, for a split pool
---@param fired table<string, boolean>? once_per_save ids this entity has already said
---@param channel string? when set, only rows on this channel (a silence window hushes the other)
---@return table[]
function M.eligible(pool, verbosity, cond, fired, channel)
  local rank = M.TIER_RANK[verbosity] or M.TIER_RANK.normal
  local out = {}
  for _, row in ipairs(pool.rows) do
    if not row.tail_only                                   -- never rolled on its own
        and (M.TIER_RANK[row.tier] or 99) <= rank
        and not (row.gate == "once_per_save" and fired and fired[row.id])
        and (channel == nil or row.ch == channel)
        and answers(pool, row, cond) then
      out[#out + 1] = row
    end
  end
  return out
end

---Anti-repeat (lines.md, "Anti-repeat - the GRP contract"): drop rows whose GROUP this entity
---said recently, in any pool. When that empties a small pool it RELAXES, first to "just not the
---last line", then to anything: a pool of four at `quiet` cannot promise eight lines of variety,
---and saying nothing is the failure the silence rows were rewritten to avoid.
---Exempt: the idle.01 -> idle.02 callback (`allow_repeat`, ordered) when its first half was the
---last thing said.
---@param rows table[] eligible rows
---@param recent string[] this entity's recent groups, oldest first
---@param last_id string? the id of the last row he said
---@param allow table[]? the catalog's allow_repeat pairs
---@return table[]
function M.fresh(rows, recent, last_id, allow)
  local seen, last_grp = {}, recent[#recent]
  for _, grp in ipairs(recent) do
    seen[grp] = true
  end
  local exempt = {}
  for _, pair in ipairs(allow or {}) do
    if pair[1] == last_id then
      exempt[pair[2]] = true
    end
  end
  local strict, loose = {}, {}
  for _, row in ipairs(rows) do
    if exempt[row.id] or not seen[row.grp] then
      strict[#strict + 1] = row
    end
    if exempt[row.id] or row.grp ~= last_grp then
      loose[#loose + 1] = row
    end
  end
  if #strict > 0 then
    return strict
  end
  if #loose > 0 then
    return loose
  end
  return rows
end

---Weighted roll. `W` is relative within the eligible set, not a probability
---(lines.md, the `W` column).
---@param rows table[]
---@param rng fun(n: integer): integer returns 1..n uniformly (math.random in the game)
---@return table?
function M.roll(rows, rng)
  local total = 0
  for _, row in ipairs(rows) do
    total = total + row.w
  end
  if total <= 0 then
    return nil
  end
  local at = rng(total)
  for _, row in ipairs(rows) do
    at = at - row.w
    if at <= 0 then
      return row
    end
  end
  return rows[#rows]
end

---Remember a said row's group, keeping the most recent M.RECENT.
---@param recent string[]
---@param grp string
function M.remember(recent, grp)
  recent[#recent + 1] = grp
  while #recent > M.RECENT do
    table.remove(recent, 1)
  end
end

---The whole pick for one event: eligible -> fresh -> roll. nil when nothing can be said, a real
---outcome (a gated sub nobody reports, a hushed channel with no narration).
---@param catalog table the whole generated table (for allow_repeat)
---@param pool table
---@param opts {verbosity: string, cond: string?, fired: table?, recent: string[], last_id: string?, channel: string?}
---@param rng fun(n: integer): integer
---@return table?
function M.pick(catalog, pool, opts, rng)
  local rows = M.eligible(pool, opts.verbosity, opts.cond, opts.fired, opts.channel)
  if #rows == 0 then
    return nil
  end
  return M.roll(M.fresh(rows, opts.recent, opts.last_id, catalog.allow_repeat), rng)
end

return M
