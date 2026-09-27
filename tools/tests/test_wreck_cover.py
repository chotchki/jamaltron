"""D.1.3: his broken legs stay ATTACHED through the flop, measured off the flop sheet itself.

Each leg's upper is a cropped pipe whose cut mouth sits at its hip (scripts/wreck.lua M.CUT),
and the legs are static offsets while the body over them heaves ~0.6 tiles north and curls
~0.6 south. A mouth left uncovered in ANY played frame is an open pipe end on the sand beside
him, the severed read chotchki ruled out (the review's leap burst: ~15 ticks of every cycle,
all four south legs). So every mouth the layout lays, over many breaks, must be under an
opaque pixel of EVERY frame the beached sheet plays.

The mask comes from the packed sheet and its manifest, so a re-render that moves his body off
the hub (M.HUB) fails here rather than on screen. The mouth's corners (a pipe is ~0.45 wide)
are not held to every frame: the always-covered patch is narrower than a pipe, and a corner at
his edge for a frame reads as a pipe going under him, not a gap (shot.sh leap bursts).
"""

import json
import pathlib
import subprocess

from PIL import Image, ImageChops

REPO = pathlib.Path(__file__).resolve().parents[2]
MOD = REPO / "mod" / "jamaltron"
MANIFEST = MOD / "graphics" / "beached-sprites.json"
SEEDS = 400
ALPHA = 40  # a pixel this opaque hides a pipe end under it

# Every leg's upper mouth - where its cropped middle starts - over SEEDS breaks, off the same
# Park-Miller stream test_wreck.lua uses.
DUMP = r"""
package.path = arg[1] .. "/mod/jamaltron/?.lua;" .. package.path
local W = require("scripts.wreck")
local s = 1
local function rng(lo, hi) s = s * 16807 % 2147483647; return lo + s % (hi - lo + 1) end
for seed = 1, tonumber(arg[2]) do
  s = seed
  for i, leg in ipairs(W.legs(rng)) do
    local u = leg[1]
    local t = W.CUT.upper[1] / W.UPPER
    print(seed, i, u.from[1] + (u.to[1] - u.from[1]) * t, u.from[2] + (u.to[2] - u.from[2]) * t)
  end
end
"""


def body_mask():
    """covered(x, y), tiles from the entity: opaque in every frame the sheet plays."""
    manifest = json.loads(MANIFEST.read_text())
    body = next(s for s in manifest["sprites"] if s["id"] == "body")
    sheet = Image.open(MOD / "graphics" / pathlib.PurePosixPath(body["filename"]).name).getchannel("A")
    w, h, per_line = body["width"], body["height"], body["line_length"]
    played = sorted(set(body.get("frame_sequence") or range(1, body["frame_count"] + 1)))
    mask = None
    for frame in played:
        col, row = (frame - 1) % per_line, (frame - 1) // per_line
        cell = sheet.crop((col * w, row * h, (col + 1) * w, (row + 1) * h))
        cell = cell.point(lambda a: 255 if a > ALPHA else 0)
        mask = cell if mask is None else ImageChops.darker(mask, cell)
    px = 32 / body["scale"]
    sx, sy = body["shift"]

    def covered(x, y):
        c, r = round((x - sx) * px + w / 2), round((y - sy) * px + h / 2)
        return 0 <= c < w and 0 <= r < h and mask.getpixel((c, r)) == 255

    return covered, played


def test_every_leg_mouth_is_under_him_in_every_flop_frame(lua):
    covered, played = body_mask()
    assert len(played) > 1, "the beached sheet plays one frame: nothing moves, nothing to hold"
    proc = subprocess.run([lua, "-", str(REPO), str(SEEDS)], input=DUMP, capture_output=True,
                          text=True)
    assert proc.returncode == 0, proc.stderr
    rows = [line.split("\t") for line in proc.stdout.splitlines()]
    assert len(rows) == SEEDS * 8, len(rows)
    bare = [(r[0], r[1], float(r[2]), float(r[3])) for r in rows
            if not covered(float(r[2]), float(r[3]))]
    assert not bare, (f"{len(bare)} of {len(rows)} leg mouths lie where some flop frame leaves "
                      f"sand, e.g. seed {bare[0][0]} leg {bare[0][1]} at "
                      f"({bare[0][2]:.2f}, {bare[0][3]:.2f}) - move M.HUB under him")


def test_the_mask_is_not_trivially_everything():
    """A mask that covered everything would pass the test above for any hub."""
    covered, _ = body_mask()
    assert not covered(-0.27, -1.5) and not covered(2.5, 0.5) and not covered(0, 3)
