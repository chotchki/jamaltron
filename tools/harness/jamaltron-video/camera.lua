-- THE CAMERA and THE CAPTURE: one screenshot per captured tick, the tick stamp, the stills.
--
-- CAMERA. take_screenshot's position and zoom ARE the camera (per call; no player view is
-- involved - show_gui=false never draws one). An eased follow: every tick the unrounded camera
-- moves `k` of the way to its target and the zoom `kz` of the way to its own. The picture is shot
-- from that camera ROUNDED TO THE PIXEL GRID (1/(32*zoom) tiles): a sub-pixel centre would make
-- a slow pan shimmer. Kept unrounded internally, or a step under half a pixel would never move.
--
-- EASE IN, TOO. That follow alone is an ease-OUT: from rest its first tick moves the full `k` of
-- the gap, a one-frame kick at every new shot - MEASURED on the first main take, first-tick
-- steps from a still camera of 19.7 px (the wave), 23.0 (the report), 11 (the repair and the
-- stand-up) and 42.6 (the encore pull-out). So a NEW SHOT (aim() with a different `shot` name)
-- or a released x-lock restarts a RAMP: the ease gain climbs linearly from 1/RAMP to 1 over RAMP
-- ticks, then it is the plain follow again. An `abrupt` shot skips it: the break's crash zoom is
-- storyboard A's "1.2 to 2.2 in 0.4 s, eased out" - a kick on purpose.
--
-- LOCKS. y is held while he is in the air (the contract's "y locked during arcs": the lift reads
-- against a still horizon). x can be held too, for an arc the cut SLOWS: MEASURED, hop1's follow
-- panned 1-16 px a tick through its arc, and at the cut's 1/3 each source frame shows three times,
-- so the whole picture stepped every third frame (a 20 Hz judder over the opening hook). Any speed
-- under 1 over a moving camera step-prints the pan.
--
-- ONE JPG A TICK at 1920x1104: the 1080 rows the video keeps plus a 24-px band under them that
-- carries the TICK STAMP and is cropped away by the pump. MEASURED (G.1 capture agent): under
-- --benchmark-graphics a 1080p screenshot every tick holds 60 UPS; force_render=true is what
-- makes frame N show tick N (without it, at game speed 4, 67 of 361 files showed a later tick
-- while the file count was perfect - a count proves nothing); a request on the LAST benchmark
-- tick is never written, so video.sh runs past the last capture tick and the director calls
-- set_wait_for_screenshots_to_finish() on it.
--
-- THE STAMP, drawn in the same on_tick that requests the shot, so it is part of the same render:
-- BITS squares for game.tick, least significant first, then a white and a black sentinel. World
-- rectangles placed from the SAME camera and zoom as the shot, so they land on fixed pixels:
-- SQUARE px on a PITCH px pitch from X0, centred in the band. tools/video/stamp.py holds the
-- same five numbers and decodes every frame of every take (video.sh's verify step): the stamp,
-- not the file name, is the proof of which tick a frame shows. 20 bits: a take is ~4000 ticks,
-- the capture spike's 12 would have wrapped at 4095. time_to_live = 1 is enough: MEASURED (G.3,
-- two main and three loop takes, every frame decoded) the rectangles drawn in on_tick T are in
-- frame T and gone from T+1 - no frame carried a second stamp.
--
-- STILLS (the portal gallery): a lossless 1920x1080 PNG, no band, centred on Jamal's drawn body
-- at the camera's zoom or STILL_ZOOM, whichever is closer in (the portal shows them as 288 px
-- centre crops). Taken in the same tick as that tick's frame, so the stamp's rectangles exist in
-- the world then: a still whose bottom edge would reach them is nudged up until it does not, and
-- the nudge is logged. MEASURED on the first take: centred at the frame camera's own zoom, the
-- wave's camera (led 4 tiles up toward the biters) nudged the flame still ~4 tiles, off Jamal;
-- at 1.6 it clears.

local M = {}

M.SQUARE, M.PITCH, M.X0, M.BITS = 16, 24, 16, 20

---A still is shot at least this close in.
M.STILL_ZOOM = 1.6

---@class Video.Cam
---@field x number unrounded centre
---@field y number
---@field z number zoom
---@field tx number target
---@field ty number
---@field tz number
---@field k number position ease per tick (0..1]
---@field kz number zoom ease per tick
---@field lock_y number? held y while he is in the air (the contract's "y locked during arcs")
---@field lock_x number? held x through an arc the cut slows (see LOCKS)
---@field shot string? the current aim's name: a new one restarts the ramp
---@field abrupt boolean? this shot skips the ramp
---@field ramp integer ticks since the ramp restarted

---Ticks the ease-in ramp takes to reach the full follow gain.
M.RAMP = 12

---@param x number
---@param y number
---@param z number
---@return Video.Cam
function M.new(x, y, z)
  return {x = x, y = y, z = z, tx = x, ty = y, tz = z, k = 0.1, kz = 0.08, ramp = M.RAMP}
end

---Point the camera somewhere; `k`/`kz` default to the gentle follow. Called every tick with the
---same `shot` while a shot follows him; a different `shot` restarts the ease-in ramp.
---@param cam Video.Cam
---@param x number
---@param y number
---@param z number?
---@param k number?
---@param kz number?
---@param shot string?
---@param abrupt boolean? no ramp: the move starts at full gain (the crash zoom)
function M.aim(cam, x, y, z, k, kz, shot, abrupt)
  cam.tx, cam.ty = x, y
  if z then cam.tz = z end
  cam.k = k or 0.1
  cam.kz = kz or 0.08
  if shot ~= cam.shot then
    cam.shot, cam.ramp = shot, 0
  end
  cam.abrupt = abrupt or false
end

---Hold y (and x, when `hold_x`) where the camera is now; `false` lets both go. Releasing an x
---lock restarts the ramp: the camera was at rest on that axis and would kick into the follow.
---@param cam Video.Cam
---@param on boolean
---@param hold_x boolean?
function M.lock(cam, on, hold_x)
  if on then
    cam.lock_y = cam.lock_y or cam.y
    if hold_x then cam.lock_x = cam.lock_x or cam.x end
  else
    if cam.lock_x then cam.ramp = 0 end
    cam.lock_x, cam.lock_y = nil, nil
  end
end

---Jump straight to the target (a cut, or the first frame).
---@param cam Video.Cam
function M.cut(cam)
  cam.x, cam.y, cam.z = cam.tx, cam.ty, cam.tz
end

---One tick of easing, through the ramp.
---@param cam Video.Cam
function M.step(cam)
  cam.ramp = math.min((cam.ramp or M.RAMP) + 1, M.RAMP)
  local g = cam.abrupt and 1 or cam.ramp / M.RAMP
  local tx = cam.lock_x or cam.tx
  local ty = cam.lock_y or cam.ty
  cam.x = cam.x + (tx - cam.x) * cam.k * g
  cam.y = cam.y + (ty - cam.y) * cam.k * g
  cam.z = cam.z + (cam.tz - cam.z) * cam.kz * g
end

---The shot's centre and zoom: the camera on the pixel grid of its own zoom. The zoom itself is
---rounded to 1/1000 so the logged value is the one the shot used.
---@param cam Video.Cam
---@return number x
---@return number y
---@return number z
function M.snapped(cam)
  local z = math.floor(cam.z * 1000 + 0.5) / 1000
  local ppt = 32 * z
  return math.floor(cam.x * ppt + 0.5) / ppt, math.floor(cam.y * ppt + 0.5) / ppt, z
end

---@param s LuaSurface
---@param cx number
---@param cy number
---@param z number
---@param w integer
---@param h integer
---@param band integer
---@param tick integer
local function stamp(s, cx, cy, z, w, h, band, tick)
  local ppt = 32 * z
  local y0 = h - band + (band - M.SQUARE) / 2
  local top = cy + (y0 - h / 2) / ppt
  local bottom = cy + (y0 + M.SQUARE - h / 2) / ppt
  for i = 0, M.BITS + 1 do
    local on
    if i < M.BITS then
      on = math.floor(tick / 2 ^ i) % 2 == 1
    else
      on = i == M.BITS                              -- white sentinel, then black
    end
    local x0 = M.X0 + M.PITCH * i
    rendering.draw_rectangle{surface = s, filled = true, color = on and {1, 1, 1} or {0, 0, 0},
      left_top = {cx + (x0 - w / 2) / ppt, top},
      right_bottom = {cx + (x0 + M.SQUARE - w / 2) / ppt, bottom},
      time_to_live = 1}
  end
end

---The world box the stamp covers this tick (for keeping stills off it).
---@param cx number
---@param cy number
---@param z number
---@param w integer
---@param h integer
---@param band integer
---@return number left
---@return number top
---@return number right
local function stamp_box(cx, cy, z, w, h, band)
  local ppt = 32 * z
  local y0 = h - band + (band - M.SQUARE) / 2
  return cx + (M.X0 - w / 2) / ppt, cy + (y0 - h / 2) / ppt,
         cx + (M.X0 + M.PITCH * (M.BITS + 1) + M.SQUARE - w / 2) / ppt
end

---@class Video.CaptureCfg
---@field resolution integer[] {1920, 1104}
---@field band integer
---@field quality integer
---@field dir string

---Frame `tick`: the stamp, then the shot. `water_tick` pins the water animation (the loop take).
---@param cfg Video.CaptureCfg
---@param s LuaSurface
---@param cam Video.Cam
---@param tick integer
---@param water_tick integer
function M.shoot(cfg, s, cam, tick, water_tick)
  local x, y, z = M.snapped(cam)
  local w, h = cfg.resolution[1], cfg.resolution[2]
  stamp(s, x, y, z, w, h, cfg.band, tick)
  game.take_screenshot{surface = s, position = {x, y}, zoom = z, resolution = {w, h},
    path = cfg.dir .. "/frames/f" .. string.format("%07d", tick) .. ".jpg", quality = cfg.quality,
    show_gui = false, show_entity_info = false, force_render = true, hide_clouds = true,
    daytime = 0, water_tick = water_tick}
end

---A gallery still `name` centred on `at`, kept clear of this tick's stamp.
---@param cfg Video.CaptureCfg
---@param s LuaSurface
---@param cam Video.Cam
---@param name string
---@param at MapPosition
---@param water_tick integer
---@return MapPosition centre
---@return number zoom
---@return integer nudge px the still moved up off the stamp
function M.still(cfg, s, cam, name, at, water_tick)
  local x, y, z = M.snapped(cam)
  local w, h = cfg.resolution[1], cfg.resolution[2]
  local sz = math.max(z, M.STILL_ZOOM)
  local sh = h - cfg.band
  local ppt = 32 * sz
  local cx, cy = at.x, at.y
  local left, top, right = stamp_box(x, y, z, w, h, cfg.band)
  local half_w, half_h = w / 2 / ppt, sh / 2 / ppt
  local nudge = 0
  if cx - half_w < right and cx + half_w > left and cy + half_h > top then
    local to = top - half_h - 1 / ppt                -- its bottom row just above the stamp
    nudge = math.floor((cy - to) * ppt + 0.5)
    cy = to
  end
  cx, cy = math.floor(cx * ppt + 0.5) / ppt, math.floor(cy * ppt + 0.5) / ppt
  game.take_screenshot{surface = s, position = {cx, cy}, zoom = sz, resolution = {w, sh},
    path = cfg.dir .. "/stills/" .. name .. ".png", show_gui = false, show_entity_info = false,
    force_render = true, hide_clouds = true, daytime = 0, water_tick = water_tick}
  return {x = cx, y = cy}, sz, nudge
end

return M
