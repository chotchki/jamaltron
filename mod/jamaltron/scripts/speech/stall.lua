-- STALLED AT THE SHORE (PLAN E.2.2): the detector. Jamal walks into a lake and stops, and the
-- engine says nothing: no event, `on_spider_command_completed` never fires, the autopilot
-- destination stays set, and the autopilot walks straight at water instead of round it. So this
-- reads the stall off motion, once per record on speech.poll's 1 Hz clock, nothing per tick.
-- It decides only that a stall happened; WHETHER he gets the line is say()'s.
--
-- A STALL, as measured: somebody is telling him to go, he moved under 2 tiles since the last
-- poll, and EITHER
--   * 2 such polls with the torso AHEAD of every foot along the heading - the head-on stall:
--     the body rests 0.67-1.26 tiles out over the blocking tile, every foot on the last land
--     column - probing the tile under the torso, then one tile ahead; OR
--   * 4 such polls with a blocking tile under the torso - a straddled V-inlet or a natural
--     shore can leave a foot ahead (5 of 106 natural stalls, 13 of 24 inlets)
-- and scripts/ground.lua names what stopped him. Head-on with DRY ground under and ahead of the
-- torso means ENTITIES hold him (a wall or pipe mat 16+ deep): latched, silent (*nothing to
-- stand on* would be a lie over a wall), and no gap since nothing was said.
--
-- ONE LINE PER EPISODE. speech.say latches it (M.latch) only on a row it said: R5 or a hush
-- returns nil and the next poll retries. The episode ends 10 tiles from the latch or 10 s after
-- anyone last told him to go; no new line within 30 s of the last, a gap that survives a D.4
-- swap. R6 (M.holding) covers every slow poll over blocking ground, including those before the
-- line; M.pushed covers a follower lurching at a slot in a lake.
--
-- State: the speech record's `stall` field, in storage, so it saves and follows transfer().
-- DIR is a constant, not state.

local C = require("prototypes.shared")
local ground = require("scripts.ground")

local M = {}

---Squared tiles per poll under which he is not getting anywhere. A retry lurch moves 1.1-1.5;
---one crossing poll can dip to 0.48 (POLLS covers that). A grinding slide along a natural coast
---(1.3-2.8) does fire, so no shore line may claim he stopped.
M.STEP2 = 2 * 2

---Slow polls in a row before the head-on probe. STAYS 2: a 15-wide crossing holds the torso
---ahead of every foot for ~146 ticks, and POLLS = 1 false-fires on 26 of 270 replayed crossings.
M.POLLS = 2

---Slow polls in a row before a stall with a foot still ahead counts, on the tile under the
---torso alone. Caught every head-on miss (106/106 natural, 24/24 inlets), no false fire across
---170+ other lanes (rivers and all of Fulgora included).
M.POLLS_FEET = 4

---Squared tiles from the latch point that end an episode. Stall motion measured under 4:
---overshoot 2.6, lunge 1.5, pull-back on release 3.8.
M.LEAVE2 = 10 * 10

---Ticks with nobody telling him to go that end an episode: he gave up on that shore.
M.QUIET_TICKS = 10 * 60

---Ticks after a line before the next episode may speak. W held into a lake is one line anyway;
---this covers a bump-and-slide coastline and a release-and-re-press.
M.GAP = 30 * 60

---Squared tiles: a follower this close to its target has arrived, whatever the destination.
M.FOLLOW2 = 10 * 10

---Squared tiles: a follower this close to its destination (target + randomised follow_offset)
---has arrived. Parked followers measured 12-30 tiles from the target, up to 3.5 from the slot;
---the target guard alone let a follower with its slot in a lake fire.
M.FOLLOW_DEST2 = 5 * 5

---Squared tiles: plain autopilot this close to its destination has arrived. The engine calls
---~1.9 arrived, and the shortest stall measured stopped 5.4 short.
M.ARRIVED2 = 3 * 3

-- defines.direction -> unit vector, as literals: no trig at runtime, nothing to desync.
local D45, C22, S22 = 0.70710678118654757, 0.92387953251128674, 0.38268343236508978
local D = defines.direction
---@type table<defines.direction, number[]>
local DIR = {
  [D.north] = {0, -1}, [D.northnortheast] = {S22, -C22}, [D.northeast] = {D45, -D45},
  [D.eastnortheast] = {C22, -S22}, [D.east] = {1, 0}, [D.eastsoutheast] = {C22, S22},
  [D.southeast] = {D45, D45}, [D.southsoutheast] = {S22, C22}, [D.south] = {0, 1},
  [D.southsouthwest] = {-S22, C22}, [D.southwest] = {-D45, D45}, [D.westsouthwest] = {-C22, S22},
  [D.west] = {-1, 0}, [D.westnorthwest] = {-C22, -S22}, [D.northwest] = {-D45, -D45},
  [D.northnorthwest] = {-S22, -C22},
}

---@class Jamaltron.StallState
---@field n integer slow polls in a row with somebody telling him to go
---@field pos MapPosition? where he was at the last poll
---@field at MapPosition? where the open episode latched; nil when none is open
---@field quiet integer? tick nobody has told him to go since, while an episode is open
---@field spoke integer? tick of the last line that latched: the gap clock
---@field stuck true? a slow poll over blocking ground, line or no line, as of this poll
---@field pushed true? a follower by its target, lurching at blocking ground, as of this poll

---@param a MapPosition
---@param b MapPosition
---@return number
local function dist2(a, b)
  local dx, dy = a.x - b.x, a.y - b.y
  return dx * dx + dy * dy
end

---Which way he is being told to go, as a unit vector; nil when nobody is. The driver's input
---first (get_driver() is a character or a LuaPlayer, both LuaControl; the VEHICLE's own
---walking_state throws), else the autopilot, which following sets too.
---@param entity LuaEntity
---@param pos MapPosition
---@param occupied boolean
---@param dest MapPosition? the autopilot destination, when the caller has read it (unoccupied)
---@return number? hx
---@return number? hy
---@return true? beside nil heading because a follower has arrived, not because nobody is asking
local function heading(entity, pos, occupied, dest)
  if occupied then
    local driver = entity.get_driver()
    if driver then
      local walking = driver.walking_state
      if walking.walking then
        local v = DIR[walking.direction]
        return v[1], v[2]
      end
    end
    dest = entity.autopilot_destination
  end
  if dest == nil then
    return nil
  end
  local dx, dy = dest.x - pos.x, dest.y - pos.y
  local len2 = dx * dx + dy * dy
  local target = entity.follow_target
  if target and target.valid then
    if len2 < M.FOLLOW_DEST2 or dist2(target.position, pos) < M.FOLLOW2 then
      return nil, nil, true
    end
  elseif len2 < M.ARRIVED2 then
    return nil
  end
  local len = math.sqrt(len2)
  return dx / len, dy / len
end

---The frontmost foot's lead over the torso along (hx, hy): negative when the torso is ahead
---of every foot. 4.7-4.8 us (measured), so only on a candidate poll.
---@param entity LuaEntity
---@param pos MapPosition
---@param hx number
---@param hy number
---@return number
local function front_foot(entity, pos, hx, hy)
  local front = -math.huge
  for _, leg in pairs(entity.get_spider_legs()) do
    local q = leg.position
    local ahead = (q.x - pos.x) * hx + (q.y - pos.y) * hy
    if ahead > front then
      front = ahead
    end
  end
  return front
end

---One poll. Returns the ground that stopped him (`water`, `lava`, `ammoniacal-solution`,
---`void`, a modded fluid) when a NEW episode should speak, else nil. Does not latch: M.latch
---does, on a returned row only.
---
---`pos` and `occupied` are the poll's own reads, reused. A parked, empty jamaltron with no
---autopilot destination and no open episode costs two API reads here, name and destination
---(re-reading them DOUBLED the poll at 1000 parked units).
---@param rec Jamaltron.SpeechRecord its entity valid (speech.poll checks)
---@param tick integer
---@param pos MapPosition the entity's position this poll
---@param occupied boolean a driver or a passenger
---@return string?
function M.check(rec, tick, pos, occupied)
  local entity = rec.entity
  local st = rec.stall
  if st == nil then
    st = {n = 0}
    rec.stall = st
  end
  local last = st.pos
  st.pos = pos
  st.stuck, st.pushed = nil, nil

  if entity.name ~= C.name then
    -- Beached or airborne (D.4): no feet to stall on. FIRST, because anything a remote say gave
    -- a record reaches here too, and autopilot_destination THROWS on anything but a
    -- spider-vehicle (a car: every poll, for good - the record is in storage). The episode goes,
    -- the gap clock stays: dropping it made a swap-and-back at one lake speak twice in 7 s.
    st.n, st.at, st.quiet = 0, nil, nil
    return nil
  end
  local dest = nil
  if not occupied then
    dest = entity.autopilot_destination
    if dest == nil and st.at == nil then
      st.n = 0
      return nil
    end
  end

  local hx, hy, beside = heading(entity, pos, occupied, dest)
  local slow = last ~= nil and dist2(pos, last) < M.STEP2
  if hx and slow then
    st.n = st.n + 1
  else
    st.n = 0
  end
  if beside and slow and ground.of(entity.surface.get_tile(pos.x, pos.y).name) then
    st.pushed = true                   -- no stall (he has arrived), but not walking either
  end

  if st.at then
    if hx then
      st.quiet = nil
    elseif st.quiet == nil then
      st.quiet = tick
    end
    if dist2(pos, st.at) < M.LEAVE2 and not (st.quiet and tick - st.quiet >= M.QUIET_TICKS) then
      return nil                                            -- spoken for
    end
    st.at, st.quiet = nil, nil  -- over: fall through, so a stall already counted fires this poll
  end
  if not (hx and hy) or st.n == 0 then
    return nil
  end
  -- Stuck, line or no line, on the probe the line fires on: holding() reads it, so a lurch
  -- before the line (1-3 polls) or inside the gap does not say `moving` at a stuck spider.
  local surface = entity.surface
  local under = ground.of(surface.get_tile(pos.x, pos.y).name)
  local g = under or ground.of(surface.get_tile(pos.x + hx, pos.y + hy).name)
  if g then
    st.stuck = true
  end
  if st.spoke and tick - st.spoke < M.GAP then
    return nil
  end
  if st.n < M.POLLS then
    return nil
  end

  if front_foot(entity, pos, hx, hy) < 0 then
    if not g then
      st.at = pos                                           -- held by entities: silent
      return nil
    end
    return g
  end
  if st.n >= M.POLLS_FEET and under then
    return under
  end
  return nil                  -- a slow crossing, a parked follower, or feet ahead on dry land
end

---Mark the episode spoken for and start the gap, after say() returned a row for `shore` or for
---a `jump_refused` whose reason is ground.is_ground. Never on the attempt: a line swallowed by
---R5 or a hush would leave the stall silent for good.
---@param rec Jamaltron.SpeechRecord
---@param tick integer
function M.latch(rec, tick)
  local st = rec.stall
  if st == nil then
    st = {n = 0}
    rec.stall = st
  end
  st.at, st.quiet, st.spoke = rec.entity.position, nil, tick
end

---True while a shore holds him: an open episode, or a slow poll over blocking ground before the
---line (it lands 1-3 polls later) or inside the gap. speech.poll keeps `moving` and `idle` quiet
---meanwhile: a retry lurch moves him 1.1-1.5 tiles and fired `moving.05` at a stuck spider, and
---a stuck autopilot unit said 44 idle lines in 30 min (both measured). Cost: a slow crossing
---poll over deep water skips `moving` too.
---@param rec Jamaltron.SpeechRecord
---@return boolean
function M.holding(rec)
  local st = rec.stall
  return st ~= nil and (st.at ~= nil or st.stuck == true)
end

---True when a follower by its target lurches at blocking ground (its slot is out in the lake).
---Not a stall (the follow guard says he has arrived, so no line) and not holding() (idle talk by
---his target is fine), but the lurch is not walking, so speech.poll says no `moving` (7 `moving`
---lines over 16 lake-slot follower runs, measured).
---@param rec Jamaltron.SpeechRecord
---@return boolean
function M.pushed(rec)
  local st = rec.stall
  return st ~= nil and st.pushed == true
end

return M
