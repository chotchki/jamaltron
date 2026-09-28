# tools/

Python side of the mod: Blender render driver, sprite packer, line-catalog codegen and the
gameplay-video pipeline ([The video](#the-video)). A `uv` project, not a package - nothing
here is published, so `pyproject.toml` sets `package = false` and carries no build backend.

Python is pinned to 3.11 (`.python-version`) to match the 3.11.11 CPython Blender 4.4.3
bundles. `uv.lock` is committed; `uv sync --frozen` rebuilds the exact venv.

## The art loop

Change a knob, look at a picture, repeat:

```sh
uv run --directory tools python render/art.py --compare --set model.scale=0.85
```

That renders 8 rotations of the body (EEVEE) and the shadow (Cycles), composites the shark
beside the shipped spidertron at matched rotations with the eight leg mounts drawn on both,
and writes `render-out/sheets/compare_<hash>.png`. MEASURED cold on a 12-core M-series,
shipped knobs: 1.5 s for the eight body frames, 12.8 s for the eight Cycles shadow frames,
14 s total. Cycles IS the loop time, so `--preview` (body only) is the 1.5 s
knob-twiddling pass and `--compare` is the one you run for the answer. Cached frames are
instant. Every knob lives in `render/jamaltron.toml` with a comment giving its default and
what it does to the picture; a misspelled knob is a hard error with a `did you mean`, not a
no-op.

Every `--compare` reports four things, on stdout and in the sheet's footer:

* the mount self-check - do the eight markers land on stock's `base_animation` plate. 8/8
  means this module reads `mount_position` correctly. It checks the SHEET, not the shark.
* the shark's own mount coverage - how many of the eight his silhouette covers, per
  rotation, worst rotation named. That settled the sizing question: at the C.13 harness
  ratio the shipped shark covers 512/512 samples over all 64 rotations, none below 8/8, so
  `base_animation` ships empty. There are two rings: the self-check uses STOCK's declared
  mount positions (it checks stock's art), everything on the jamaltron row uses the 0.45
  ratio entity.lua ships, read out of `shared.lua` so the two cannot drift. At the unshrunk
  ring the same render covers 171/512, which is why stock draws a plate.
  CAVEAT (PLAN F.3, measured in the engine): `sheets.mount_markers` / `mount_coverage` hold
  the mounts still while the shark turns, which is the PINNED rig stock ships. Jamal ships
  `base_animation` nil, so in game his whole leg rig turns WITH him (a rotating rig costs
  ~1.1 us/tick per driven Jamal, and chotchki kept it), and what matters is the
  orientation-0 placement carried round to every rotation. The two agree only at north, so
  512/512 never sampled the in-game mounts at the other 63 headings.
* a canvas warning when any frame's alpha touches its render canvas edge - a clipped frame
  looks like a flat-topped shark, not an error. MEASURED on the shipped knobs: the union of
  all 64 rotations is 5.59 x 4.48 tiles of the 6 (2.68 above the entity origin, 1.81
  below), leaving 0.31 tiles of headroom at the top and 0.20 at each SIDE. The side is the
  tight edge: it starts cutting frames 16 and 48 at `model.scale` 0.87, against a shipped
  0.81.
* a cell-fit line, the same check for the compare CELL. An adversarial review caught the
  old 4.6-tile cell cropping 32 px off each side and 50 off the bottom of every frame,
  silently (a cropped cell reads as tight framing). The cell is `camera.canvas_tiles` wide
  now, so it cannot cut what the render did not, and the line says what it holds or exactly
  what to raise.

Drop `--set` for the shipped values; `--show` prints the resolved config without rendering.
The model is gitignored, so point at your copy with `--blend PATH` or `$JAMALTRON_BLEND`.
Sheets land in `render-out/` (gitignored) and nothing is promoted into
`mod/jamaltron/graphics/` for you - that directory carries the licence carve-out.

### Getting the model on disk

The bought model ships as ONE zip holding ANOTHER, and where the inner one lands decides
whether he renders textured. From the repo root, with the RenderHub download at
`assets/source/hammerhead_shark.zip`:

```sh
cd assets/source
unzip -n hammerhead_shark.zip                  # -> FILES/HAMMERHEAD.blend (+ .fbx, .dae)
unzip -n FILES/HAMMERHEAD_TEXTURES.zip         # -> TEX/, a SIBLING of FILES/, not inside it
```

The .blend reads its textures at `//../TEX/HAMMERHEAD_*.png`, so the second zip has to be
unpacked from `assets/source/`. Unzip it inside `FILES/` and you get `FILES/TEX/` and a
MAGENTA shark (Blender's missing-texture colour, MEASURED mean RGB 239/19/239). Nothing
fails, but every render WARNs, naming HAMMERHEAD_COLOR and _NORMAL. Read that WARN even
AFTER fixing the layout: textures are not in the cache key, so the magenta frames sit under
the same hash a correct render produces and keep being served. The WARN replays on those
cache hits (C.23) and says so; clear them with `--force` or by deleting the pass directory.
The two GREATWHITE images the `CHECK unresolvable images` line always lists are the seller's
other model, wired to nothing and never WARN. All of `assets/source/` is gitignored, which
is the condition the licence turns on.

## Sliders, when you do not know the number yet

`--compare` answers "is this value right". For "which value IS right", moving one number by
0.1 and looking again, use the tuner:

```sh
uv run --directory tools python render/tune.py            # opens a browser at 127.0.0.1:8765
```

Eleven sliders (pivot fore/aft, height, girth, scale, pitch, yaw, base yaw, roll, phase
lock, bounce height, bounce phase) drive the SAME `ac.load -> art.render_pass ->
art.compare_sheet` path as the CLI: same cache, same sheet, same coverage count, same hash.
The page shows the shark's dimensions and the leg-mount coverage as you drag, and a copy
TOML button emits the exact lines to paste into `jamaltron.toml` - the hash it prints is the
hash `art.py --compare` stamps after the paste, so there is no transcription step. `--set`
seeds it with `art.py`'s syntax, which is how you carry on from yesterday.

MEASURED, and why the defaults are what they are: 1.8 s per slider change (8 body
rotations, EEVEE, 16 samples, 384 px, 4 jobs), 0.2 s cached, 17 s with the shadow toggle
on. Cycles is the whole difference, so shadow is OFF until you ask. Four rotations is NOT
faster than eight (the loop is Blender launch-bound, not pixel-bound), and `--jobs 8` is 14x
SLOWER than `--jobs 4` on this machine: eight simultaneous Blenders thrash the Metal
context.

It is a local tool: stdlib `http.server`, one file, no dependency, bound to 127.0.0.1 only.
A failed render leaves the last good image up and puts the error on the page, so a value you
were curious about cannot kill the session.

### Flopping him

The same page picks one of the model's five shipped clips (SWIM_FAST / SWIM_MEDIUM /
SWIM_SLOW / BITE_01 / BITE_02, or the rest pose), scrubs a frame, amplifies it with pose
gain and PLAYS the loop. Play matters because a flop is a MOTION: frame 7 of a thrash and
frame 7 of a shark swimming sideways are the same picture. The loop renders once, then plays
out of the browser's own memory, so every later cycle is free.

MEASURED, ten frames cold: 15.1 s to fill broadside (1.51 s a frame), 18.1 s on the full
wheel, 0.13 s a frame to re-tick PLAY afterwards (zero in the browser, which is where it
plays). 256 px is not faster than 384 - launch-bound at both ends, same as `--jobs`. The
broadside view is not a speed knob either (17%, i.e. nothing): a beached shark only reads as
beached from the side. Nose-on the roll is invisible and the thrash is all in screen depth,
so five of the wheel's eight views cannot answer the question.

MEASURED by driving it (every earlier call on this pose was made off still frames): stride 1
plays 23.40 fps against the 24.00 target (mean 42.7 ms a frame, min 40.4, max 43.4) over
seven clean wrapping passes of f1..f20; stride 2 plays 11.80 against 12.00. The 2.5%
shortfall is `setInterval`'s own drift - no network and no render in the loop, just an
`img.src` swap to an object URL. The fill is paid once: 15.2 s for 20 frames, 0.10 s to
re-tick the whole loop afterwards. A still is 1.37-1.42 s round trip, and 16 renders with one knob moved each came
back 16 DIFFERENT sheets - no slider on the page is decorative.

The flop preset button is the C.5 recipe in one click: SWIM_FAST, roll 85, yaw 180, gain
1.25, phase lock 1.0, bounce 0.3 at phase 0.4, HEAD reparented, ground contact on,
broadside. It leaves scale, girth, pivot and pitch alone, because half the time those are
mid-tuning. Yaw 180 is chotchki's call of 2026-09-23, lock 1.0 is C.5.8's V5, gain 1.25 and
phase 0.4 are C.5.9's (2026-09-26). The U's own knobs (recentre, amplitude_even), fin_floor
and the seat list are NOT on the button - they ride from the config, so open the page on
`render/beached.toml` for V5. The page still OPENS on the committed standing config (the
header's `paste` hash reads `bd71cb367d90` on arrival, live proof the flop work has not
touched the shipped art), which is why 85 is a button and not a boot value.

The roll slider runs 15 deg past 105, where sheet B says he stops reading as beached and
starts reading as dead, belly-up, in WATER; `artconfig.warnings()` says so from 105 on
(`art.py --set 'model.rotation=[140,0,0]'` used to render that in silence). A warning and not
a clamp on purpose: C.5 is judged by eye, so you get to look past the edge.

The flop is all KNOBS, so everything above works from the CLI too:

```sh
uv run --directory tools python render/art.py --compare \
    --set 'model.action="SWIM_FAST"' --set model.frame=12 --set model.pose_gain=1.0 \
    --set model.reparent_head=true --set 'model.rotation=[85,0,0]' \
    --set bounce.height=0.3 --set bounce.phase=0.25
```

| knob | what it does |
| --- | --- |
| `model.action` | which of the five clips, or `"rest"` for the standing shark. A misspelled id is a fatal `not one of` - the enum IS `render/pose.py`'s table |
| `model.frame` | which frame of that clip, clamped to its range |
| `model.pose_gain` | every bone's rotation scaled away from rest. 1.25 ships since C.5.9 (C.5.8's V5 went to 2.0 so the U read in a still, and in motion that was cartoon - chotchki 2026-09-26; 1.0 was enough for the lock-0.5 sine). The rig survives 2.6x, measured |
| `model.phase_lock` | 0 is the swim's TRAVELLING wave as bought, 1 plays every spine joint in step with the tail - the standing wave a beached fish makes. See below |
| `model.ground_contact` | C.5.4: the posed body's LOWEST vertex sits on the floor every frame, plus the bounce lift; `offset` z drops out. See below |
| `model.ground_ignore` / `.ground_sink` / `.fin_fold` / `.spine_sag` | C.5.6 bedding-in: which bones the floor may NOT hold him up on, how far he presses into it, how far the lower pectoral folds up, how far his back half sags onto the sand. Whatever goes under z=0 is held out. See below |
| `model.fin_floor` | C.5.8: the lower pectoral keeps its REST-spine orientation (no chest swing, no recentre turn) before `fin_fold` lays it flat, so the U cannot swing it into a spike. Orientation only, not contact. See below |
| `model.recentre` / `.amplitude_even` | C.5.8's U: turn the body back against its curl so head and tail rise together, and even the swing down the spine so the bend bottoms out in his middle |
| `model.reparent_head` | C.18a rig fix, applied in memory - HEAD ships as a ROOT bone, so the snout is welded to world space until this is on |
| `bounce.height` / `.phase` / `.gravity` | the ballistic lift: how high, where in the cycle he pushes off and the `g` that fixes the airtime |

They are ordinary schema knobs, so a flop frame caches, hashes and stamps like a standing
one: the tuner's header names the hash of the picture on screen, pose included (it used to
say `pending bake`, when the pose lived in a temp `.blend` that only existed after a render
ran). They are hash-neutral at their defaults (`ac.ADDITIVE`), so adding them did not move
the `83d6be794998` the shipped sheets carried then; off its default a knob is in the hash
like any other. `ground_contact` is the one the standing config moved on purpose (C.27,
`bd71cb367d90`).

### The curl: phase lock

chotchki's standing-wave call. The swims are a TRAVELLING wave - each spine joint bends a
fixed lag behind the one in front, so the bend runs nose to tail and reads as propulsion. A
beached fish makes a STANDING one, the whole body curling one way at once. Same bones, same
keyframes, different phase relationship, so `model.phase_lock` re-times each joint instead of
authoring anything. The renderer measures the lags off the clip every run (fundamental of
each joint's bend over one cycle, sign-matched in armature space, unwrapped down the chain).

MEASURED on the bought model, SWIM_FAST (MEDIUM and SLOW give the same fractions of the
cycle):

| joint | SPINE_01 | 02 | 03 | 04 | 05 | 06 | 07 | TAIL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lag, frames of 20 | 0.00 | 1.50 | 2.99 | 4.49 | 5.49 | 6.99 | 8.50 | 10.00 |
| swing, deg | 2.99 | 1.52 | 3.75 | 4.56 | 8.09 | 10.54 | 8.26 | 10.82 |

The lock was checked by re-measuring its OWN output: at 1.0 every joint's lag comes back
0.00 +-0.01 and every joint correlates with the tail at >= 0.998 (travelling, SPINE_01 sits
at -0.993). At 0 the pose is bit-identical to the pre-knob renderer over 30 poses, so it is
hash-neutral AND pixel-neutral. The loop still wraps at the clip's own length, which needed a
hand-bridged seam: with the stale final key dropped the curves extrapolate CONSTANT, so a
joint shifted into (20, 21) would freeze for a frame and pop. At lock 1 the f20 -> f1 step is
under the largest interior step on every joint. At lock 0 it is NOT on SPINE_04/05 (1.49 vs
1.38 deg, 2.64 vs 2.45) - that is the bought clip's own seam, because the "stale" key was up
to 1.0 deg off frame 1 rather than a copy of it, and lock 0 is the bought clip bit for bit.
SWIM_SLOW has a real hitch there: its true period is 80, not 78 (PLAN C.26).

The lock also MOVES peak curl - SWIM_FAST's whole-body curl peaks at f18 at lock 0, f19 at
0.5, f1 at 1 - and `[bounce]` is timed off the curl (since C.5.9 it lands on it, see below),
so re-find `bounce.phase` after moving the lock. The tail keeps its own timing; that is not
the same thing.

The lags and offsets land in the render's output as a `FIX phase_lock ...` line (`art.py -v`,
the tuner's harness log) and in the pass's JAMALTRON_RESULT. A lock that could not apply (a
bite, or a clip with no single bone chain) is a `WARN`, because it moved the hash and no
pixel.

The lock ALONE does not make a U. Lock 1 is a coherent curl - 50.8 deg peak nose to tail
against 32.8 travelling - but it reads as a big tail flick. Two measured reasons: the wave is
rear-loaded 3:1 (the front four joints carry 12.8 deg of it), and SPINE_01 is a root bone at
the nose, so the curl hinges at his head and the front never leaves the floor. C.5.8 fixed
that with `model.recentre` (C.5.3's counter-rotation by part of the curl, so head and tail
rise together) and `model.amplitude_even`. And without ground contact he is BURIED, which the
lock worsens but did not start: worst lowest vertex over the loop at roll 85 is -0.389 tiles
at lock 0 (`offset` z 0.5 was tuned for the STANDING shark), -0.697 at 0.5 and -0.841 at 1,
because the down-curling half of the cycle drives the tail into the floor. A real fish on its
side cannot curl into the ground; the ground turns that half into an arch. (These replace
-0.455 / -0.804 / -0.950, taken off a bounding box that ran up to 0.108 tiles too deep - see
below.) The ground half is C.5.4, next.

### Ground contact (C.5.4)

`model.ground_contact = true` evaluates the posed mesh, finds its LOWEST vertex and moves the
model so that vertex sits at exactly this frame's bounce lift - on the floor at landing,
`lift` above it in the air. `offset` z drops out (added, then cancelled) on purpose: it
places the model's ORIGIN, right for the standing shark riding his legs and wrong for a
thrashing body whose lowest point moves every frame. At the C.5.2 call without contact he was
under the floor on all 20 frames, 0.105-0.430 tiles - invisible in the tuner (the body pass
draws no floor) and sliced by the shadow catcher. Since offset z cannot move a pixel while
contact is on, `artconfig.hashable()` pins it out of the key (x and y stay in) and the tuner
greys its height slider; otherwise every drag re-rendered the same picture under a new hash.

MEASURED at the call (lock 0.5, bounce phase 0.5, roll 85, yaw 180):

* the lowest vertex lands on the lift to 0.00007 tiles on all 20 frames, at three wheel
  directions (the wheel spins about world z, so one measurement per frame holds for all 64)
* 0 of 40 forced renders (20 frames x body + shadow) warn buried; without contact all 20
  frames are past the WARN's threshold
* the shadow comes back WHOLE. Without contact the catcher cut the down-curled tail out of
  it, on exactly the frames where the tail is what touches the ground
* it costs TOP headroom: he sits up to 31 px higher (+0.697 tiles x 0.707 x 64, f18), and
  the tightest top margin over the loop at dir 16 drops from 82 px to 68. The tightest margin
  overall is 13 px on the RIGHT edge, contact or not. No broadside frame clips (dirs
  12/16/20: 24/13/8 px); NOSE-ON ones do: at f8 dirs 61-63 and 0-8 touch the top of the
  6-tile canvas with contact (dirs 0-4 already did without). Moot while the beached sheet is
  ONE broadside direction (C.5's budget); a full-wheel flop needs a taller canvas
* watch at 24 fps: the shift runs +0.280..+0.697 tiles across the loop. Its biggest step is
  the loop SEAM, -0.221 f20 -> f1 (the top edge drops 12 px, against 2 without contact), then
  +0.19 f16 -> f17, where the curl flips which part of him is lowest. Physically right (the
  down-curl arches his middle up), but those two are the frames most likely to read as a
  hitch

The standing shark has it on TOO (C.27, chotchki 2026-09-24). At offset z 0.5 his belly sat
0.260 tiles under the floor at all 64 rotations, so the shipped shadow was cast from a partly
buried body. Contact raises him 0.2602 tiles, which the 45-degree camera draws 0.184 tiles
higher - and that alone drops the leg mounts off him: 412/512 mount samples land on the shark
without a fix, worst 5/8 at N. So the mounts ride up the same screen offset
(`mount_lift = 0.184` in `mod/jamaltron/prototypes/shared.lua`, read by `entity.lua` AND the
compare sheet's coverage count, one number in one place) and coverage is 512/512 again, every
rotation (pinned-rig numbers, see the caveat under the art loop). The feet stay put; his legs
are 6 px longer. Config `83d6be794998` -> `bd71cb367d90`, all four sheets re-rendered fresh
(which also retires the 09-20 cache drift C.27 found).

It is exact because `world_box()` is now exact: it walks the evaluated vertices instead of
transforming each mesh's LOCAL bound box, whose corners hang up to 0.109 tiles below anything
the mesh reaches once he is rolled 85 and curled (six of the call's 20 frames, f01 and
f16-f20). That also corrects the buried-body WARN, which overstated by the same amount.
Standing renders are untouched bit for bit: the new renderer and the one before it produce
identical IDAT for the committed config.

### Bedding in (C.5.6)

Lowest-vertex contact is exact and WRONG on his side. chotchki off the `caed815d2940` draft:
"only the tip of his side fin is touching the ground which isn't realistic since that would
bend and his main mass would be touching. it may be better to clip him into the ground."
MEASURED over all 72 beached configs: the lower pectoral's tip (FIN_RIGHT at roll 85 / yaw
180) is the lowest vertex on every ground frame and his trunk hovers 0.46-0.57 tiles over it,
the shadow a body-width off him. Leaving only the fin out of contact is not enough: he moves
onto the hammer's lower tip and the trunk still hovers 0.14-0.22. Five knobs, all hash-neutral
at their defaults, all on in `beached.toml` only:

* `ground_ignore = ["FIN_LEFT", "FIN_RIGHT", "HEAD", "JAW"]` - contact seats the lowest vertex
  NOT dominated by one of these deform bones (a name the rig lacks is fatal). The trunk seats
  him on the ground frames, the caudal lobe on the tail flicks, so the push-off still pushes
  off. TAIL stays off the list: ignoring it buries the caudal 0.32-0.54 on the flick frames
* `ground_sink = 0.04` - pressed that far in on every frame, so the hop's arc stays the same
  arc
* `fin_fold = 50` - the lower pectoral swings about its root toward straight up, in the
  vertical plane through its own span (a WORLD axis, because the two fins' bone axes are not
  mirror images). At ~50 the span lies level: a fin splayed on the sand, the same shape all
  cycle. At 0 it stabs into the floor on every landing and dangles on every hop
* `fin_floor = true` (C.5.8) - the fold starts wherever the POSE left the fin, which is
  level only while the chest it hangs off sits near rest. V5's U breaks that twice: the
  evened, doubled curl swings the chest (the fin dives 25-62 deg before the fold, 46-52 on
  C+) and the recentre turns the whole body up to 60 deg more. MEASURED on V5's heave with
  the fixed fold: elevation -13..+23 deg and the heading swung round to due SOUTH at the U's
  bottom - a fin pointing at the camera, 51 px of white spike straight down the screen
  (chotchki: "fix it"). A level fin pointing south is the same spike, so levelling the span
  alone would not do. The hold pins the fin's whole ORIENTATION to its rest-spine, unturned
  one (`pose.floor_hold`: turn^-1 x rest x its own basis - a bite still flaps it) and the
  fold runs from there: -3.8 deg and one heading on all 20 heave frames, 25.6 px on screen.
  The root still rides the chest, so on the arch frames (his middle up to a tile off the
  sand) the fin sticks out level at chest height rather than reaching down, which would be
  the spike again. It holds orientation, NOT contact: the tip is 0.01-0.17 tiles off the
  floor on the U frames and up to ~1 tile on the arch frames. It also takes out the chest's
  swing with recentre off (heave f11 at recentre 0: +21.4 deg unheld, -3.8 held), so
  "unchanged at recentre 0" is not a property it has; only a rest spine with no turn leaves
  the fin as it was. The bite beats (rest spine, recentre 0) leave it off and keep their C+
  cells; the pause (gain 0.2, recentre 0, fin_floor on) is a new cell. `render/fin_probe.py`
  is the real-rig measurement (Blender, a job JSON in, the fins' elevation / heading / root
  and tip z out); `test_fin_floor.py` drives it when Blender and the model are on disk and
  skips otherwise
* `spine_sag` - SPINE_04..TAIL each bend this much further toward the floor, about the axis
  the swim bends them, on top of the pose. The sculpt's spine is straight and level (SPINE_01
  0.838 tiles up, the TAIL tip 0.852), so with the trunk seated the tail's underside still
  hung 0.27 tiles over his trunk's level at rest and 0.38 at the pause. Set PER BEAT, not
  once - see below

What goes under z=0 is not drawn: the body and mask passes add a camera-only HOLDOUT plane
there (the shadow pass's catcher already is one). MEASURED against a render at the same height
with no plane: 0 of 9191 shared opaque pixels move by more than 1 level - it hides, it does
not light. At the shipped values the trunk sits at -0.040 on every ground frame; what goes
deeper is the fin root (-0.085..-0.162, the fold's own flange) and the hammer's lower tip
(-0.18..-0.26), which on the snap frames leaves a short flat edge under his chin.

Why the sag is per beat: the tail comes down to his trunk's level at 2.57 deg a joint on the
rest shape (snap / release) and at 4.23 on the pause, so no one value lays both - the best
single number, 3.25, leaves the rest trunk 0.05 up on its tail and the pause tail 0.07 up.
And it is NOT free: on any frame the tail already seats him, a sag cannot lower the tail,
only raise everything else - at 3.25 the trunk rides 0.33-0.41 tiles higher on every
tail-seated frame of the heave and he lands heave f3 on his tail with the trunk 0.22 up. So
`beached.toml` gives the heave none (its cells stay the C.5.2 call), ramps it 0 -> 4 through
the settle into the pause (tail 0.03 over the trunk's level), holds 2.5 on the snap / release
(0.01 over) and ramps it back out 2.0 -> 0 through the twitch. The price is settle f6-f7, the
two frames after its seat-list cut where the sagged tail takes his weight: the trunk rides
0.13 / 0.06 tiles higher than with no sag (MEASURED at C.5.9; every other settle frame seats
on the hammer or his trunk either way, so the sag moves only the tail). The settle has no
landing of its own any more - at bounce phase 0.7 it never leaves the sand.

### What the bounce is for

The shadow. The shadow pass is a real Cycles render with the game's own 45-degree sun and a
catcher at z=0, so lifting the model separates the shadow by itself. MEASURED at 0.3 tiles,
one direction, one clip frame, the lift the only difference between two renders: the shadow's
alpha centroid moves +19.12 px east (0.2987 tiles against 0.300 predicted, a pure
translation) while the body rises exactly 14 px up-screen (0.219 against 0.212 predicted).
That separation is what reads as airborne; a lift without it looks like the sprite growing.
It costs 8 px of the body canvas's 84 px of headroom over the whole loop.

The fall is a PARABOLA, not a sine, and the airtime is derived from the height and gravity
rather than authored (`artconfig.bounce_lift` has the argument). A sine hangs at both
extremes and reads as floating; ballistic flight leaves at full speed and comes back
accelerating, which is what being pulled looks like. Ground contact is a hard floor, so the
frames he is not airborne are frames spent lying on the ground - where the landing, and the
joke, lives.

The phase is set by the PUSH, not the curl (C.5.9, chotchki 2026-09-26: "he should be lowest
as he starts to push down with his midsection"). The first cut launched off the U's peak
(phase 0.5, f11) and landed on f3 - two frames after his middle started driving down, so the
push happened in the air. MEASURED at gain 1.25, his trunk against the hammer-tail chord tops
out on f1 and drives down to the U on f11, 94% of it by f9; 0.3 tiles of hop is 11.9 frames
of air, which leaves 9 on the sand. Phase 0.4 spends them on the push: he lands ON f1, pushes
f1-f9 with the mid-trunk taking the floor from f7, launches on f9 and curls back up into the
arch in the air. The measurement lives in `beached.toml`'s `[bounce]` notes and
`test_sequence.py` pins the ground/air split.

### The beached sheet: a sequence of beats (C.21, C.24)

The flop has its OWN config, an overlay: `render/beached.toml` says `base = "jamaltron.toml"`
and then only what the flop changes - the clip, roll 85 / yaw 180, the U (lock 1, recentre 1,
amplitude_even 1 - C.5.8's V5 - at C.5.9's gain 1.25), bounce 0.3 at 0.4, HEAD reparented,
contact. It overrides keys, never whole tables, so every shared knob (scale, girth, pivot,
sun, camera, mask) lives in exactly ONE file and the standing and beached sheets cannot drift
apart. Every tool takes it with `--config`:

```sh
uv run --directory tools python render/tune.py --config render/beached.toml   # boots on the flop
uv run --directory tools python render/art.py --config render/beached.toml --sequence --preview
uv run --directory tools python render/pack.py --config render/beached.toml --preview
```

The tuner's export knows the difference. Opened on the overlay it writes only the overlay's
own keys plus whatever you moved off the base, and it FLAGS a shared knob you moved on the
flop page (a scale tuned there and pasted into beached.toml makes him a different size lying
down). Opened on the standing file with a POSE selected, it writes the block for
`render/beached.toml` instead: the old export told you to paste a flop over the standing
shark, which re-dates the shipped sheets.

One frame is still ONE config, so pack.py, which wants N frames in one directory, could not
assemble a flop whose every frame lives in its own. The `[sequence]` table fixes that: a list
of BEATS, each a run of one clip's frames with knob overrides on top of the file's own
(`set`), linear ramps across the beat (`ramp`), a `stride`, a `hold` and frames that can run
backwards. `render/sequence.py` expands it into unique per-frame configs plus a play order.
`art.py --sequence` renders each unique config once per pass at the one direction (one
Blender per frame per pass, `--jobs` of them at a time), then writes
`render-out/sheets/sequence_<name>_<digest>.gif` - THAT is how you watch it, at 24 fps, every
frame labelled with its beat: `open -a Safari render-out/sheets/sequence_beached_*.gif`.
`pack.py --config render/beached.toml` gathers the same frames out of the same cache dirs,
checks each against ITS OWN config's pass hash and packs one sheet per pass as an
`animation` with a Factorio `frame_sequence`.

WHICH passes is `[sequence] passes` (default body, mask, shadow). `beached.toml` ships
`["body", "shadow"]`: NO harness on a beached Jamal, it broke off with his legs (chotchki
2026-09-26). art.py then launches no mask Blender for it, and pack.py packs none and deletes a
mask sheet an earlier pack left in `graphics/`. It is a `[sequence]` key and not a `[mask]`
knob on purpose: no pass hash moves, so the drop re-packed from the cache. The price is the
entity colour, which a beached Jamal no longer shows; D.4 carries `color` across the swap, so
it is back on the repair.

Repeats are FREE, which is what makes a long varied cycle affordable: identical configs are
one render and one cell, `frame_sequence` plays a cell as often as the beats ask and the
engine loads a repeated cell into VRAM once. The committed draft plays 117 frames (4.9 s) off
72 cells - heave, heave, settle, pause, snap at nothing, let go, try again - and is promoted
and wired as `jamaltron-beached`'s art in `prototypes/bodies.lua`:

* config `a5b3c3f1531c` (C.5.9: V5 at gain 1.25, bounce re-phased, the bite's cells pinned
  back to their C+ hashes), after `f9c264329dc0` (C.5.8's V5) and `897cda204427` (D.1.2)
* height 0 and render_layer `object`: he lies ON the ground, so he sorts by y like anything
  else on it (at the stock `under-elevated` he painted over a tree south of him)
* body 2264x1548 + shadow 2528x1089, 1878 KiB crushed, 23.87 MiB raw, lint `--strict` clean.
  C.5.9's smaller curl shrank the body cell to 283x172 (V5 at gain 2.0 was 304x189 and 26.51
  MiB, +2.57 over C+'s 23.94; C+ was 26.24 with the harness mask's 464x1296, dropped
  2026-09-26, and 34.02 before that mask got the shadow's alpha floor)
* every sheet carries its own `animation_speed` (0.4, 24 fps over 60 ticks). Left to the
  consumer it was not set, and the engine played the 4.9 s flop in 117 ticks

`lint_sprites.py` checks the frame_sequence itself: 1-based indices inside frame_count,
Factorio's 255-frame cap and under `--strict` a cell the sequence never plays.

The seams are the HARD part, and they are tested, not eyeballed. At bounce phase 0.4 the
heave's 0.495 s flight runs to its own last frame (launch f9, f20 at 0.08 tiles, lands ON
f1), so the beat after a heave has to start on that landing (the settle's phase 0.7 puts its
half-tempo launch 12 frames before f1, like the heave's) and the beat before one has to be
falling the same way. `test_sequence.py` fails any seam in the committed cycle whose lift
step is bigger than the heave's own biggest in-loop step, and requires the last frame to hand
back to the first. Two beats are CUT IN TWO for V5's seat list (HEAD may seat him on the
arches, never near rest, where the hammer's lower tip props him 0.14-0.22 up):

* the twitch at f9/f10, where both lists seat him on the same vertex (MEASURED)
* the settle at f5/f6, where at gain 1.25 no frame agrees - a `ground_sink` ramp 0.04 ->
  0.1766 over f1-f5 seats f5 where the other list would, so the cut is pose alone

`test_sequence.py` holds each split to ONE straight ramp (the sink excepted, pinned on its
own). MEASURED over the whole 1.25 cycle, every seam moves the trunk, hammer and tail by 4.0
px or less on screen except the twitch's f9/f10 split (5.9 px, which is also its launch), all
under the 9.8 px inside the heave itself. Direction: wheel index 16 is east, but yaw 180
turns him round - nose WEST, belly and mouth to the camera (chotchki's call).

## Shipping a sheet

`art.py` answers "does he look right". `pack.py` turns the frames that answered it into the
two files the mod and CI read:

```sh
uv run --directory tools python render/pack.py            # dry run into render-out/pack
uv run --directory tools python render/pack.py --promote --crush   # into mod/jamaltron
```

`--out` names a MOD ROOT, mod-shaped either way: `<out>/graphics/` gets the sheets and
`sprites.json`, `<out>/prototypes/` gets `sprites_generated.lua`. The shape matters because
`.github/workflows/ci.yml` derives `--strict` from the manifest's PATH, matching
`mod/jamaltron/graphics`. A manifest anywhere else is linted in the tolerant mode or trips the
stray-manifest tripwire, and sheets committed with no manifest beside them fail CI on purpose.
So the default is a gitignored dry run, lintable IN PLACE, and `--promote` is the deliberate
act that writes into the tree carrying the sprite licence carve-out.

Every number - width, height, line_length, direction_count, frame_count, lines_per_file,
scale, shift - is computed ONCE into one dict and serialized twice, as a Lua table and as a
manifest entry with the same field names plus an `id`. There is no translation layer for them
to drift across, and `test_pack.py` reads both back through `lint_sprites.py`'s two
independent front ends and asserts they normalise identically. pack.py then runs that gate
over its own output before it exits, so a sheet that would fail CI fails the packer first.

MEASURED on the shipped config (`bd71cb367d90`, C.27), crushed, four sheets out of three
passes:

| sheet | frame | cells | grid | on disk | VRAM raw | stock's own |
| --- | --- | --- | --- | --- | --- | --- |
| `jamaltron-body` | 362x289 | 64 dir | 2896x2312, 8x8 | 1685 KiB | 25.54 MiB | 1308 KiB / 4.45 MiB |
| `jamaltron-body-mask` | 166x121 | 64 dir | 1328x968, 8x8 | 323 KiB | 4.90 MiB | 1012 KiB / 3.17 MiB |
| `jamaltron-body-shadow` | 408x256 | 64 dir | 3264x2048, 8x8 | 266 KiB | 25.50 MiB | 99 KiB / 4.41 MiB |
| `jamaltron-body-water-reflection` | 378x295 | 1 var | 378x295 | 13 KiB | 0.43 MiB | 5 KiB / 0.77 MiB |
| total | | | | 2287 KiB | 56.37 MiB | 2425 KiB / 12.8 MiB |

The mask frame is 20 px shorter than the body's box is tall because the harness stops below
the dorsal fin, so the union of its 64 rotations no longer reaches up the blade. The NEXT
standing pack's mask comes out 166x120, not 121: the mask now gets the shadow's alpha floor
(< 8 zeroed before the box), which trims the band's 1 px antialiasing ramp. No specks on the
standing mask; nothing else moves.

The rotating frames are the UNION of all 64 rotations' alpha, which for a rotating body is a
disc of radius "furthest point from the turn axis" - so a 4.07-tile shark needs a 5.6-tile
box where the stock torso needs 2.06, and the pixel count goes as the SQUARE of that. That is
the whole 4.4x VRAM gap, and it is why we come out SMALLER on disk than stock while being four
times the texture: our sheets are mostly transparent. 56 MiB of raw sprite for one entity is
real; Factorio's own sprite compression takes it to about a quarter of that, and the lever if
it ever matters is `model.scale`, not the packer.

The two non-obvious sheets:

* the mask is `apply_runtime_tint`, the layer the entity colour picker drives; without one
  the picker does nothing at all (and D.4's preservation of `color` across the beached swap
  would be dead code). STANDING ONLY: the beached flop ships no mask, his harness broke off
  with his legs. It is its own render pass - same camera, same canvas, one flat grey shader
  whose ALPHA is a harness band in the model's own local coordinates - and it tints the
  HARNESS, not the whole fish. The band is a saddle between two girth straps, floored AND
  ceilinged in the model's local z: without the ceiling the tallest thing between the straps
  is the dorsal fin, and the first shipped mask painted it base to tip (a colour picker that
  tints a shark's fin). Stock's mask is a shaded greyscale copy of the entire torso at alpha
  224, which turns a machine into the player's colour and would turn a hammerhead into a
  lozenge. See the `[mask]` block in `jamaltron.toml`; `mask.mode = "silhouette"` is stock's
  approach kept as a one-line escape hatch, and the harness warns you if you pick it.
* the water reflection is built by the packer out of the body frames, because there is
  nothing to render. MEASURED off stock: one frame, `variation_count` 1, shift 0, every pixel
  pure red (255,0,0) with the shape entirely in the alpha, a soft blurred ellipse 1.7x the
  torso sprite's own footprint. Ours is the mean alpha of all 64 rotations (rotationally
  symmetric by construction), gained, blurred, recentred on the origin and forced to red.
  Stock's 448x448 canvas is Wube not cropping a 5.5 KiB palette PNG, not a number to match.

### PNG crushing

Worth it, with the tool that is here. `pngcrush` and `optipng` are not installed on this
machine; `oxipng` is (`brew install oxipng`). `--crush` runs `oxipng -o 4`, then re-opens
every sheet and compares RGBA bytes against the original before keeping the result - this
pipeline has no in-game validation to catch a "lossless" optimizer that isn't. MEASURED:
-29.2% on the body sheet, -40.4% on the shadow, -18.5% on the mask, -30.6% on the reflection,
-29.3% over the four, 8.2 s. Pillow's own `optimize=True` gets -24.4% and -1.0% for
comparable time, so the gap is almost entirely oxipng's colour-type reduction: it turns the
black-plus-alpha shadow sheet into a palette PNG, which is exactly what Wube ships their own
shadow sheets as. Metadata is NOT stripped - the config-hash text chunk is the provenance, and
`--strip safe` would quietly take it. Off by default because the iteration loop should not
pay 7 s.

### What a shipped sheet carries

Four text chunks: `jamaltron:config_hash`, the per-pass hashes, the fully resolved config and
the derived numbers. `model.blend` inside that config is a CONTENT digest (`sha256:` + 16
hex), never a path, and the hash is taken over the same substitution. That fixes two things.
Hashing the path made the stamp a fact about one laptop - three copies of one `.blend` hashed
to `e7de16fab859` / `335119bf9c46` / `2da921d030cb` for pixel-identical sheets, and the
shipped value reproduced on exactly zero other machines. And the path is not ours to publish:
on the machine that rendered these it was an absolute scratch directory, heading into a
public repo, in the one tree the licence carve-out governs. Check a sheet against your own
copy with `shasum -a 256 HAMMERHEAD.blend | cut -c1-16`; resolve the stamped config, re-hash
it and you get the `config_hash` it claims.

### Sprites that are not renders

D.1.3's broken legs round a beached Jamal ship no PNG and never touch this pipeline:
`prototypes/wreck.lua` cuts the stock spidertron leg sheets BY REFERENCE from `__base__` (the
art his walking legs wear - Wube's pixels stay out of the repo, and `graphics/LICENSE` stays
about our renders), one layered sprite per leg segment, and `scripts/wreck.lua` lays eight
bent legs off the map rng on every break. Judge them with `tools/shot.sh --scene both`; the
layout's rules are pinned by `lua/test_wreck.lua`. Every leg hangs off ONE hub behind his
gills - the only patch his body covers in all 72 flop frames, so no pipe end ever shows on
the sand mid-leap - and `test_wreck_cover.py` measures that off the packed beached sheet: a
re-render that moves him off the hub fails there, not on screen (move `M.HUB`, check a leap
burst: `shot.sh --every 3 --count 12 --start 262`).

## Icons (C.6 candidates, C.15 gate)

```sh
uv run --directory tools python render/icons.py              # every candidate, 64 samples, ~18 s cold
uv run --directory tools python render/icons.py --only legs  # one of them
python3 tools/lint_sprites.py --strict render-out/review/icons/*/icons.json   # the gate
uv run --directory tools python render/icons.py --promote portrait   # ship the picked one
```

`icons.py` renders every icon the mod needs FROM THE MODEL, through `art.render_pass` (same
cache, same knobs, 1536 px bodies). A render writes candidates to `render-out/review/icons/`
and NOWHERE else - picking the look is chotchki's, and promoting one into `mod/jamaltron/` is
its own deliberate step, `--promote NAME`. The shapes are base's spidertron's, MEASURED off
2.1.17:

* item icon 120x64 (64+32+16+8, top-aligned, no `icon_size` needed - 64 is the default)
* tech icon 480x256 (256+128+64+32, `icon_size = 256`)
* minimap 128x128, declared `size = {128, 128}, flags = {"icon"}, scale = 0.5` with no chain
* thumbnail 144x144 at the mod root

Each candidate dir holds `icon.png`, the `icon-tintable` / `icon-tintable-mask` pair item.lua
has to replace alongside it (harnessed candidates only), `technology.png`, `minimap.png` +
`minimap-selected.png` (base's flat style: white fill, rim `(255,0,0)` / `(141,127,122)`, read
off the stock PNGs' histograms), `thumbnail.png` and an `icons.json` the gate reads (with the
`samples` it was rendered at). `00-icon-candidates.png` puts them all at 1x and 2x
(nearest-neighbour, so the 2x is the real pixels); `01-context-<name>.png` drops each item
icon into dark and light slots at 100% UI (the 32 px level in a 40 px slot) and 200%, with
stock's spidertron icon beside it for scale - review only, never written anywhere that ships.

### Shipped: the portrait, everywhere

chotchki's C.6 call. `--promote portrait` renders NOTHING - it copies the reviewed files byte
for byte, so what was looked at is what ships. It refuses before touching the mod when the
candidate's `icons.json` records fewer than 64 samples (a `--preview`, or a render from before
samples were recorded), when a file is missing (a harnessless candidate has no tintable pair,
and item.lua wires one) or when the candidate fails `lint_sprites.py --strict` where it sits.
Then it renames into the mod and writes `graphics/icons.json` (`"sprites": []`, one entry per
file with its `kind`), which CI's sprite job and `test_icon_coverage.py` read:

| file | size | wired in |
| --- | --- | --- |
| `graphics/jamaltron-icon.png` | 120x64 | item.lua `icon` (harness pre-tinted player orange); entity.lua `icon` |
| `graphics/jamaltron-icon-tintable.png` | 120x64 | item.lua `icon_tintable` (harness untinted) |
| `graphics/jamaltron-icon-tintable-mask.png` | 120x64 | item.lua `icon_tintable_mask` (harness alone, tinted by the vehicle's colour) |
| `graphics/jamaltron-technology.png` | 480x256 | technology.lua `icon`, `icon_size = 256` |
| `graphics/jamaltron-minimap.png` | 128x128 | entity.lua `minimap_representation` |
| `graphics/jamaltron-minimap-selected.png` | 128x128 | entity.lua `selected_minimap_representation` |
| `thumbnail.png` (mod root) | 144x144 | nothing - the engine reads it by name |

Every size key is written out (`icon_size`, `icon_tintable_size`, `icon_tintable_mask_size`,
all 64): none inherits another. The layered forms (`icons`, `icon_tintables`,
`icon_tintable_masks`) are nil'd, because either would beat ours if a mod that loaded first
left one on the stock item. The Lua paths sit in ONE table literal per file, then get copied
onto the prototype - `lint_sprites.py`'s Lua reader sees literals only, so a bare
`item.icon = "..."` would slip past gap (a) below; `test_icons.py` fails if any shipped path
stops being a literal it can see. beached and airborne copy the vehicle in bodies.lua and keep
its icon and map marker: a marker says WHERE he is, and the beached body is the one a player
has to go find. The thumbnail is a render too, so graphics/LICENSE's carve-out names it; it
sits outside graphics/ only because the engine looks nowhere else.

Two honest limits. A hammerhead is four tiles of mostly tail, so boxing the whole of him
leaves the head a third of a 64 px square; `square_box(core=N)` measures the crop on the alpha
ERODED by N px, so anything thinner than 2N (the tail's last third, a fin tip) may run off the
edge. And the model has no legs: the `legs` candidate draws its own, vector strokes from the
harness's REAL mount ring (`sheets.mount_markers` with shared.lua's shrink and lift) to a
knee and a foot pulled in to half the real stance - stock's leg pixels are Wube's and cannot
be copied into anything we ship.

### The gate (C.15)

The sprite checks cannot read an icon - a 120x64 file declared as a 64 px icon is its mipmap
chain, and the engine counts the levels off the WIDTH (`icon_mipmaps` is gone in 2.x) - so
`lint_sprites.py` has an icon half. A manifest's optional `icons` list (`kind` = `icon` /
`technology` / `minimap` / `thumbnail`, which sets the default size and level count) is
checked for:

* `icon-size` - not `icon_size` tall
* `icon-not-square` - the width is neither the height nor a valid chain
* `icon-mipmaps` - a valid chain with the wrong level count
* `thumbnail-size` / `thumbnail-path` - not 144x144, not `<mod root>/thumbnail.png`
* `icon-no-alpha` - WARN, fails `--strict`; an alpha channel, or a `tRNS` colour key on a
  grey, RGB or palette PNG, all count

The Lua front end reads `icon` / `icon_size` (and the tintable pair, `icons = {{...}}` layers,
`dark_background_icon`, `small_icon`) as literals, each against its OWN size key -
`icon_tintable_size`, `icon_tintable_mask_size`, `dark_background_icon_size`,
`small_icon_size`, every one defaulting to 64 on its own, never inherited from `icon_size`
(2.1.17's prototype-api.json). It checks size and chain validity WITHOUT our level count:
somebody else's 64 px icon with no mipmaps is legal. CALIBRATED against every prototype file
of the six built-in mods, `--strict`: 1566 icon declarations, the 1537 literal ones produce
ZERO findings, the other 29 are string concatenations it refuses as `unresolved-icon`.

CI picks it up with NO workflow change, as long as the icons ride a manifest that carries
`"sprites": [...]` (an icons-only one says `"sprites": []`) under `mod/jamaltron/graphics/`.
ci.yml recognises manifests by that key and lints them `--strict`, and `test_lint_icons.py`
execs ci.yml's own `declares_sprites()` against an icon manifest, so a classifier change that
would drop icons out of the gate fails there. The thumbnail is declared in the same manifest
(`"filename": "__jamaltron__/thumbnail.png"`), because ci.yml's classifier only looks for
manifests.

The two holes the CI job cannot see are closed by `test_icon_coverage.py`, which the `tests`
job runs like the rest:

* (a) a HAND-WRITTEN prototype's icon - `icon = "__jamaltron__/..."` in item.lua is neither a
  manifest nor generated Lua, so the sprite job never lints it. The test runs the Lua icon
  reader over every `.lua` under the mod, keeps the `__jamaltron__` ones (a concat that
  visibly builds one too, as `unresolved-icon`; `__base__` is skipped, a runner has no
  `--factorio-data`) and checks them `--strict` against `--mod-root jamaltron=mod/jamaltron`.
  Gap (a) has a sprite twin: a hand-written SPRITE table of ours (entity.lua's minimap pair)
  is no CI target either, so every `__jamaltron__` sprite declaration in non-generated Lua
  lints `--strict` there too
* (b) an UNDECLARED icon PNG - `thumbnail.png` at the mod root must be declared with
  `kind: thumbnail` in a manifest under the strict tree, and any PNG under the mod named like
  an icon (`icon` / `thumbnail` / `technology` / `minimap` in the name, or under an `icons/`
  or `technology/` directory) must be declared by such a manifest or by a Lua icon field

Since the promote both have real work (item.lua's three, technology.lua's one, entity.lua's
one, all seven PNGs); both are proven failing on planted bad cases in a tmpdir. Honest
limit: an icon path built from a variable (`DIR .. "x.png"`) with no `__jamaltron__` in the
expression slips (a), though its PNG still has to clear (b).

## Commands

| command | what it does |
| --- | --- |
| `cd tools && uv sync` | create `.venv` and install Pillow + pytest |
| `cd tools && uv run pytest` | run the unit tests |
| `uv run --directory tools pytest` | same, from the repo root |
| `JAMALTRON_TEST_NO_MODEL=1 uv run --directory tools pytest` | the suite as a CI runner sees it: the model under `assets/` reads as missing and `$JAMALTRON_BLEND` is dropped (the file is never touched). Passes both ways, or a pin is taking the model's digest off disk instead of `shipped_model` |
| `JAMALTRON_LUA=lua5.2 uv run --directory tools pytest` | the Lua suites under a NAMED interpreter, as CI runs them - one that is not on PATH fails every Lua suite, it never skips |
| `uv lock --check` | non-zero if `pyproject.toml` and `uv.lock` have drifted |
| `Blender -b --python tools/render/blender_check.py` | prove the Blender entry point still works |
| `uv run --directory tools python render/factorio_camera.py` | print the camera and sun constants |
| `uv run --directory tools python render/factorio_camera.py --verify` | re-derive both constants off the installed game's own sprites |
| `Blender -b MODEL.blend --python tools/render/model_inspect.py -- --out report.json` | dump mesh, rig, clips and materials from a model |

The art harness (C.10), all from the repo root (`--set` takes TOML values, repeatable):

| command | what it does |
| --- | --- |
| `uv run --directory tools python render/art.py --compare` | THE image to look at: stock / jamaltron / overlay at 8 matched rotations, shadow composited, leg mounts drawn, mount self-check printed |
| `uv run --directory tools python render/art.py --preview` | 8 body rotations + a contact sheet. The fast loop |
| `uv run --directory tools python render/art.py --full` | all 64 rotations + a contact sheet |
| `uv run --directory tools python render/art.py --shadow` | the Cycles shadow-catcher pass on its own |
| `uv run --directory tools python render/art.py --mask` | the runtime-tint pass (the harness) on its own; add `--full` for all 64 |
| `uv run --directory tools python render/art.py --show` | print the resolved config, the derived numbers and the hashes; render nothing |
| `... --config render/beached.toml --sequence [--preview]` | C.21: every unique frame of the `[sequence]` through the passes it ships (`[sequence] passes`; beached: body and shadow) at its one direction, then a 24 fps GIF of the whole cycle in `render-out/sheets/` |
| `... --set model.scale=0.85 --set 'model.rotation=[0,6,0]'` | override knobs for one run |
| `... --blend /path/to/HAMMERHEAD.blend` | the model, or set `$JAMALTRON_BLEND` |
| `... --force` / `--jobs N` / `-v` | ignore the cache / parallel Blenders (default 4) / echo Blender's own report |
| `uv run --directory tools python render/tune.py` | the slider UI: eleven sliders, the five shipped clips with a PLAY loop that holds 23.4 of 24 fps, the flop preset, the rig-fix and ground-contact toggles, live coverage count, copy-TOML button; shadow off by default |
| `... --port N` / `--no-open` / `--set model.girth=1.3` | pick the port / do not launch a browser / start from a knob you already found |
| `... --config render/beached.toml` | boot on the flop overlay; the export then writes overlay-shaped blocks for that file |

The packer (C.7) and everything else, also from the repo root:

| command | what it does |
| --- | --- |
| `uv run --directory tools python render/pack.py` | frames -> sheets + manifest + Lua, into the gitignored `render-out/pack` |
| `... --promote` | the same, into `mod/jamaltron`, which is the tree CI lints with `--strict` |
| `... --crush` | oxipng afterwards, kept only if the bytes come back identical |
| `... --preview` | pack the preview-samples body cache (8 rotations) instead of the full one |
| `... --line-length N` / `--pad N` / `--max-side N` | columns per row (reduced to a divisor of the frame count) / margin around the union alpha box / sheet ceiling |
| `... --targets body,shadow` / `--frames-dir body=DIR` | pack a subset (ids: `body`, `body_mask`, `shadow`, `reflection`) / point one target somewhere else |
| `... --allow-clipped` / `--any-config` / `--no-verify` | pack frames that are CUT / frames from another config / skip the strict lint of our own output |
| `... --config render/beached.toml` | pack the `[sequence]`: one frame out of each config's own cache dir, one `animation` sheet per pass with a `frame_sequence`, written beside the standing pair as `jamaltron-beached-*.png` + `beached-sprites.json` + `beached_sprites_generated.lua` |
| `python3 tools/lint_sprites.py --strict --mod-root jamaltron=mod/jamaltron mod/jamaltron/graphics/sprites.json` | the sprite gate, exactly as CI runs it |
| `uv run --directory tools python render/icons.py [--only NAME] [--preview]` | C.6: icon candidates from the model into `render-out/review/icons/` - item, tintable pair, tech, minimap pair, thumbnail, the review sheets and an `icons.json` per candidate. Never writes into `mod/` |
| `uv run --directory tools python render/icons.py --promote NAME` | C.6: copy the reviewed candidate NAME into `mod/jamaltron` (renders nothing; refuses a preview render or a candidate the strict lint fails) and write `graphics/icons.json` |
| `python3 tools/lint_sprites.py --strict render-out/review/icons/*/icons.json` | C.15: the icon gate over the candidates. Each manifest resolves against its own `mod_roots` |
| `tools/play.sh --new` | playtest: the real game on its own profile in `.playtest/` (gitignored) - its own saves, mod list and settings, jamaltron symlinked from the working tree, a fresh map loaded straight in. Your real Factorio profile is never read or written (measured: zero files changed in it across a run). In game: `/jamaltron-kit` (row ids to the log; `/jamaltron-ids` for chat), `/jamaltron-say <pool> [cond]`, `/jamaltron-row <id>`, `/jamaltron-state`. Plain `tools/play.sh` reopens the profile at the main menu; `--base-only` drops Space Age; `--reset` starts it clean |
| `tools/shot.sh --scene both --zoom 2` | C.30: screenshots out of the REAL renderer, no play session. See [Screenshots](#screenshots-toolsshotsh) |
| `tools/video.sh [--take main\|loop]` | G.4: film a take of the gameplay video - a headless dry run of the director, then `--benchmark-graphics` with one stamped jpg a tick, then every frame's stamp decoded (0 mismatches or it fails) - into `render-out/video/takes/`. Its own profile in `.videotest/`; `--dry-run`, `--skip-dry`, `--fresh`, `--out`, `--quality`. See [The video](#the-video) |
| `uv run --directory tools python -m video.build --take ../render-out/video/takes/main-<stamp> --cut video/main.toml` | G.5-G.8: a verified take + a cut -> the master mp4, the stills (and `--cut video/loop.toml`: the portal loop mp4 + the README GIF) in `render-out/video/out/`. `--dry-run`, `--unverified`, `--allow-silent-audio`, `--allow-caption-mismatch` |
| `uv run --directory tools python -m video.stamp verify <take>` | re-run a take's stamp check; writes its `verify.json` |
| `tools/smoke.sh --harness tools/harness/jamaltron-harness` | D.5.4: the smoke test plus a scripted in-engine run (3800 ticks) of the speech rules - chains, windows, R3/R4/R5, the fork and {N}, transfer, idle, moving, command_done - E.2.4's shore lanes (`shore.lua`) and F.3's bubble cap (`cap.lua`: 8 real breaks flopping under `jamaltron-max-bubbles` 3, the engine's bubble count checked against speech.lua's registry every tick, an event at the cap still speaking). Fails on any `HARNESS FAIL` line |
| `tools/smoke.sh --harness tools/harness/jamaltron-fire-harness --ticks 2300` | D.7: the flamethrower - four guns on the vehicle and airborne, four disarmed twins on beached (D.7.3: he fires nothing beached, by himself or for a seated driver, against a standing control whose driver does; the ammo across a real break and repair is `jamaltron-jump-harness --ticks 4500`'s AM lane), the stream leaving ONE point under his belly, (0, -1.36), at 8 aims and 8 facings (D.7.4), range (fires at 6/9/10 tiles, never 11/12), one `attacking` line per burst, attacking.03's window, friendly fire confirmed and not (a first burst rolls under it, the next fight does not inherit it), his own splash and a squad-mate's kept out of `damaged`, 0 HP of self-burn at a behemoth 6 tiles out on 16 bearings (D.7.5 (b): all 24 legs fire-proof, pinned on the prototypes too), the damage filter's fire half registered only while he fires, his research requiring flamethrower, 20 Jamaltrons in a fight profiled. Its header has the graphics re-run that shows the source; the LOOK (flame under his legs and body, W1's layers) is `tools/shot.sh`'s |
| `uv run --directory tools python gen_lines.py --check` | B.5: validate `character/lines.md` against its own contract (and against the gitignored book extracts when they are on this machine) and report whether the generated `scripts/lines.lua` + `locale/en/jamaltron-lines.cfg` are current. Writes nothing |
| `uv run --directory tools python gen_lines.py` | the same, then WRITES both files. Run it after every catalog edit - CI fails a stale pair. Generating is NOT the id freeze: ids stay renumberable through playtesting, and freezing them is PLAN F.6, just before release |

`Blender` is `/Applications/Blender.app/Contents/MacOS/Blender` on this machine.
`blender_check.py` prints the Blender and bundled-Python versions plus the usable render
engines, and exits non-zero if Cycles is missing.

### Screenshots: tools/shot.sh

`--benchmark-graphics` on a fixture save built once in `.shottest/` (gitignored: a flat sand
pad at noon, no crash site, no intro, no clouds, no character). The game window flashes up
for ~10 s, and `tools/harness/jamaltron-shot` stages the scene through the mod's own code on
load, so an edit shows on the next run with no rebuild. Lands in `render-out/shots/`.

* `--scene beached` is a real break (airborne, landed by `breakage.on_landing` at 100%);
  also `standing`, `both` and `many` (`--many N`, 1-16, default 6): N real breaks in a grid
  9 tiles apart plus one standing for scale. Each break lays its legs out off the map rng, so
  one shot shows the wreck layout's spread. The grid is framed WHOLE, so with no `--zoom` 13+
  drops the zoom below 1 at 1600x900, and a `--zoom` that crops it warns
* `--at T,T` for stills, `--every K --count N [--gif]` for a burst, `--stager DIR` to load a
  spike's own copy of the stager (its own `data.lua` + drawing code, the mod untouched),
  `SHOT_DIR=` for a second profile when two runs overlap
* the stager CHECKS the fixture instead of trusting it: a crash-site entity on the pad,
  freeplay's intro or crash-site flag back on, clouds, a cutscene or a player character at
  staging or at any shot is a `SHOT FAIL`
* every argument (every shot tick >= 1 - tick 0 is spent staging and never shot) and the
  `SHOT_DIR` refusals (/, home, the repo, anywhere in the real profile - checked on the
  resolved path, case-folded since APFS reads `.../Factorio` as the real profile, before
  anything is created) run before the binary is touched
* `tests/test_shot.py` covers all of that (the refusals from a copy of `shot.sh` in a fake
  repo, asserting nothing under the target changed) plus the run's plumbing and the `many`
  framing against a fake factorio

### Traps

1. `uv run --project tools pytest` FAILS with `ModuleNotFoundError: No module named
   'render'`. `--project` does not change directory, so pytest takes the repo root as
   rootdir, never reads `tools/pyproject.toml` as its config and silently ignores
   `pythonpath = ["."]`. Use `--directory tools` (which does chdir) or plain `cd tools`.
2. Every entry-point script under `render/` opens with

   ```python
   import pathlib, sys
   sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
   ```

   because Python puts the SCRIPT's directory on `sys.path[0]`, never the CWD, and
   `package = false` means there is no installed `render` to fall back on. Blender does the
   same to `--python` scripts. Those two lines cannot be factored into a helper module -
   importing the helper is the thing that needs the path fixed. Repeat them.
3. The corollary of 2: because `render/` is on `sys.path[0]`, a file in it named after a
   STDLIB module shadows that module for every sibling script. `render/inspect.py` did
   exactly this: `dataclasses` imports `inspect`, so `from dataclasses import dataclass` in
   `spritesheet.py` imported a module that does `import bpy`, and both
   `uv run python render/spritesheet.py` and `blender_check.py` exited 1 while checked in
   and "working". It is now `model_inspect.py`, and `test_art_harness.py` fails the suite if
   any file under `render/` takes a stdlib name again. Rename the file; do not solve this
   with a sys.path guard.

## The Blender boundary

A script running inside Blender uses Blender's interpreter and does NOT see `tools/.venv`.
Blender 4.4.3 bundles numpy 1.26.4, requests and zstandard, but not Pillow. So the split is
enforced by convention:

| side | may import | runs as |
| --- | --- | --- |
| Blender | stdlib, `bpy`, bundled numpy | `Blender -b <file> --python render/x.py -- args` |
| uv | stdlib, Pillow | `uv run python render/x.py` |
| both | stdlib only (`render/spritesheet.py`) | either |

Data crosses as JSON, either a sentinel line on stdout or a path handed in after `--`. The
payoff is `render/spritesheet.py`: the projection and sheet math, the part most likely to be
wrong, gets unit tests with Blender nowhere in the loop.

Injecting the venv into Blender does work
(`sys.path.append('tools/.venv/lib/python3.11/site-packages')`, then `from PIL import Image`)
and is the documented break-glass move if a render pass genuinely needs Pillow inside a `bpy`
context. Use `append`, not `insert(0)`, so Blender's own numpy keeps winning. We do not build
on it: it hard-couples the pipeline to Blender's exact CPython minor and makes the
Blender-side code untestable without Blender.

## Rendering

Body is EEVEE Next. Shadow is Cycles and has no choice. That is what the shipped config does
(`render.engine`, `render.shadow_engine`), because:

- the shadow pass is not a choice. Only Cycles honours `object.is_shadow_catcher`. The
  attribute exists under EEVEE Next too, so a naive script looks like it works, but EEVEE
  renders the catcher plane fully opaque across the frame and the pass comes back as a grey
  square. Factorio's `shadow_animation` needs the alpha. Move `render.shadow_engine` off
  `"CYCLES"` and the harness prints a WARN.
- the body pass is a choice, and EEVEE wins it. Measured on the real model, 8 rotations at
  384 px / 16 samples / 4 jobs: EEVEE 1.47 s wall, 4.6 s CPU; Cycles CPU 2.01 s wall, 13.3 s
  CPU. Same picture for a third of the CPU, and Cycles is the noisy one at low sample counts,
  which is exactly where the fast loop lives.
- the two pictures really are the SAME. Mean absolute difference across those 8 frames:
  0.31/255 over the whole RGBA frame, 6.1/255 over the pixels either render puts ink on.
  Almost all of it is the antialiased silhouette edge - 19.3/255 on partial-alpha fringe
  pixels against 2.7/255 on the fully opaque interior.
- CPU, not GPU, for Cycles. A sprite-size tile is pure launch overhead for a GPU: Metal costs
  a 39 s one-time kernel compile and then MORE per frame than CPU. `GPU` exists in the config
  for when the canvas grows.

The mask pass rides the body's engine, canvas and resolution, and differs only in the
material - one flat grey shader whose alpha is the harness band. Deliberately: its frames
have to crop against the same origin pixel the body's do, or the two layers of `animation`
slide apart in game. It is DITHERED (hashed alpha) with backfaces culled, not BLENDED:
alpha-blended EEVEE geometry writes no depth, so the strap on his far flank draws straight
through his back.

Flip `render.engine` to `"CYCLES"` for a final sheet if you want the model's Cycles-only
features; at 132 px you will not see them, which is why `render.use_subsurface` is off.
Re-measure both engines if the geometry or the canvas changes. The shadow-catcher requirement
does not move either way.

MEASURED, the full 64-rotation set cold, 4 jobs, shipped knobs, 12-core M-series: body 6.1 s,
mask 5.7 s, shadow 86.6 s, so 98 s of Blender and 10 s more for `pack.py --promote --crush`.
Cycles is 90% of it and always will be. Re-rendering the whole set reproduces the pixels to
within 1/255, and every difference that turns up is a single LSB: across two runs of the same
knobs, 0 then 1 of 64 body frames differed and 54 then 50 of 64 shadow frames. That is what
makes a cached frame safe to ship, and why re-packing an untouched pass moves a couple of
hundred bytes of PNG.

`gpu.platform.backend_type_get()` raises `SystemError` in background mode. Do not probe the
`gpu` module headless - rendering is fine, that one call is not.

## The video

PLAN Phase G. The gameplay video is SCRIPTED: `tools/video.sh` films a take out of the real
renderer under `--benchmark-graphics`, no hands, one stamped jpg a tick; `python -m
video.build` cuts it, draws the captions and cards, rebuilds the sound from the game's own
files and encodes the deliverables. This section is the interface between the pieces (the
"contract" the code's comments cite). The director (`harness/jamaltron-video`) writes the
take; `video/timeline.py`, `video/pump.py`, `video/captions.py` and `video/mix.py` read it.
Change a format here and in the code together.

```sh
tools/video.sh --take main          # dry run (headless, 4 s), then the take: 88 s wall at 60 UPS
tools/video.sh --take loop          # the creek hop the GIF and the portal loop come from (26 s)
uv run --directory tools python -m video.build \
    --take ../render-out/video/takes/main-<stamp> --cut video/main.toml    # 39 s
uv run --directory tools python -m video.build \
    --take ../render-out/video/takes/loop-<stamp> --cut video/loop.toml    # 1.2 s
```

Always in that order: a build reads a take, it never films one. A cut edit is a rebuild off the
same take; re-film only when the director, the set or the mod changed. The times are MEASURED
on main-20260927-221640 + loop-20260927-221740 with the machine to itself (the build times
from build.json's `seconds`).

Deliverables land in `render-out/video/out/<cut>/` (gitignored, like the takes). NEVER in git:
Wube's policy allows their sounds IN a video, never as files (`data/eula.txt`), and nothing
from the install - .ogg, Titillium Web - is ever copied into the repo; both are read from
`/Applications/factorio.app/Contents/data` (or `$FACTORIO_DATA`) at build time.

### The take

`render-out/video/takes/<take>-<stamp>/`, written by `video.sh` and nothing else:

| file | what |
| --- | --- |
| `frames/f<tick:07d>.jpg` | one per captured tick, 1920x1104 q90 (~0.85 MB each on grass + live water, ~3.1 GB a main take - MEASURED G.4): the 1080 rows the video keeps plus a 24-px band carrying the TICK STAMP |
| `events.jsonl`, `track.jsonl` | the director's two logs (below) |
| `run.log`, `dry-run.log` | the game's logs; `jamaltron speech <unit> <row>` lines are the captions' cross-check (the director turns the mod's debug on) |
| `take.lua` | the director's config for that run (below) |
| `stills/<name>.png` | gallery PNGs, 1920x1080, no band, centred on him |
| `verify.json` | the stamp verdict: `ok`, `frames`, mismatches, duplicates, gaps. `video.build` refuses a take without an ok one (`--unverified` overrides and says so in build.json) |

THE STAMP: 20 bits of `game.tick` as 16-px squares on a 24-px pitch from x=16, least
significant first, then a white and a black sentinel, drawn as world rectangles in the same
on_tick that requests the shot. `video/stamp.py` reads it off EVERY frame: 0 mismatches, 0
duplicates, 0 gaps or the take fails. A file count proves nothing (G.1: at game speed 4
without `force_render`, all 361 files landed and 67 showed the wrong tick).

`take.lua` is Lua source video.sh writes from validated values (a syntax error in it SIGSEGVs
the game on load, MEASURED G.1): `return {take = "main"|"loop", capture = bool, resolution =
{1920, 1104}, band = 24, quality = 90, dir = "video/<take>", stills = bool}`. `capture =
false` is the headless dry run: every beat plays, both logs are written, nothing is shot.

### The take's logs

`events.jsonl`, one object a line in TICK ORDER. `tick` is when it HAPPENED: what the director
only sees a tick later (on_tick T reads what update T-1 did - his speed, the ammo, the
roboport's robots, his health) is dated back to T-1. Ordinals count an `ev` in tick order
(`takeoff#3` is the third takeoff).

| ev | fields | when |
| --- | --- | --- |
| `capture_start` / `capture_end` | | the first / last captured tick |
| `beat` | `name` | a beat begins. Main: establish board hop1 hop2 wave report lake_jump beached apology repair stand encore wrap. Loop: loop_pre loop wrap |
| `takeoff` | `x y distance land_tick peak` | the director's press, off the arc the mod built |
| `apex` | `x y` | takeoff + round((land_tick - takeoff) / 2) |
| `landing` / `break` | `x y` | `on_spidertron_replaced` reason landing (clean) / break (beached) |
| `thud` | `x y` | the landing thud, the same tick as its landing or break |
| `repair` | `x y` | the stand-up swap (jamaltron's 60-tick poll) |
| `line` | `row channel forced x y n` | a SPEECH row on screen from this tick (forced, or the mod's roll left standing); `n` = his break count, the `__1__` some rows carry |
| `said` | `row channel x y` + `replaced_by` (speech) or `hidden: true` (narration) | a row the mod said that is on screen for NO frame: a speech roll a forced row replaced on its own tick, or narration world text the director hides |
| `footfall` | `x y` | the director's script trigger on jamaltron's legs |
| `walk_start` / `walk_stop` | `x y` | his speed crosses 0.01 tiles/tick |
| `fire_start` / `fire_stop` | `x y` | a firing run (the fired event + the ammo diff); stop = 10 quiet ticks after the last round |
| `biter_spawn` / `biter_attack` / `biter_died` | `x y name` | spawned / first damage to him / died |
| `wave_clear` | | the last spawned biter died |
| `repair_cue` | | repair packs into the roboport |
| `bot_out` | `x y` | a construction robot leaves the roboport |
| `repair_start` / `repair_full` / `repairing` | | his health first rises / reaches max / every 30 ticks while it rises |
| `still` | `name` | a gallery PNG was taken |
| `liberty` | `what` | anything a player would not see happen: a setting write, a heal, peaceful mode, a cancelled chain. Forcing a row is the method, not a liberty |

`track.jsonl`, one line per captured tick: `{"tick", "cam": [x, y], "zoom", "body":
"jamaltron|jamaltron-airborne|jamaltron-beached", "pos": [x, y], "lift": [dx, dy],
"sprite": [x, y]}` - `lift` is where his DRAWN torso sits off `pos` (standing 0,-1.5; beached
0,0; in the air the arc's own offset), `sprite` the arc sheet's raw offset (in the air only).

WHICH LINE A FRAME SHOWS, MEASURED on main-20260927-204942 (the first contract said "frame T
anchors on line T+1", which holds on the ground only). Line T is written at the end of the
director's on_tick T: after jamaltron's on_tick (it moves him through an arc and lands him)
and the director's own press, before the entity update (walking) and every on_nth_tick (the
stand-up). So:
* `cam`, `zoom`: line T is frame T's camera, always
* `pos`, `body`, `lift`: frame T shows line T+1 on the ground and on the stand-up tick (line
  3480 still says beached, lift 0; frame 3480 shows him up), line T in an arc and on its
  takeoff and landing ticks (line 232 already holds tick 232's arc step, line 261 the landed
  body)

`captions.Anchorer` implements it; `journal.lua` (the writer) carries the same note.

### The cut

A cut file (`video/main.toml`, `video/loop.toml`) is written in EVENTS, never ticks - the
director is event-driven, and headless and graphics runs drift by up to a 60-tick poll - so a
cut re-resolves against every new take with no edits.

```toml
fps = 60                          # must be 60: one frame per tick at 60 UPS
deliver = "master"                # master | loop (no captions, no audio track)
crop = [340, 240, 1280, 720]      # loop only: [x, y, w, h] of the kept 1920x1080, 16:9
[[segment]]                       # a span
from = "takeoff#1"                # <ev>[#n] or beat:<name>, then +N / -N ticks
to = "landing#1"                  # HALF-OPEN [from, to): shared anchors show no tick twice
speed = 0.3333333333              # source ticks per output frame: 1/3 = each frame x3, 5 = every 5th
tag = "5x"                        # a corner marker while it plays (<= 8 chars)
audio = "live"                    # live | mute
caption = "below"                 # lines SAID in this range are captioned under his feet
[[segment]]                       # a freeze: one source frame held
at = "apex#4"
hold = 4.5                        # seconds
audio = "mute"
[[overlay]]                       # a card over the live picture, in output seconds
card = "title"
from_out = 0.0
to_out = 3.0
[[card]]                          # a full-frame card after the segments, over the last frame dimmed
card = "end"
seconds = 7.0
```

A bare `<ev>` needs exactly one in the take; a missing or ambiguous anchor is a hard error
naming it. Speeds are exact fractions (0.3333 means 1/3, so a long span never drifts), frame
REPETITION not interpolation. The resolver writes `frames.json`, which the pump and the mixer
both read: `{"fps", "deliver", "captions", "crop", "frames": [{"src": T|null, "seg": i}],
"segments": [{"index", "kind": "span|freeze|card", "speed", "from", "to", "tag", "audio",
"out": [f0, f1], "card", "caption"}], "overlays": [{"card", "from_out", "to_out", "out"}]}`.

### Liberties

A liberty is anything the video does that a player would not see the game do. Every one is
TAGGED where somebody checking the video can find it, in the take's logs or on screen:

* in the engine, a `liberty` event (`what` says what and WHY, e.g. `setting
  jamaltron-leg-break-percent 100: the break is the beat`), echoed to run.log as `VIDEO liberty
  ...`. `grep '"liberty"' <take>/events.jsonl` lists them. main-20260927-221640 carries 14: the
  three pins at tick 0 (speech cooldown 300 s, break chance 0, distance 8), the lake jump's
  distance 20 + break 100 and their resets, the encore's distance 20, peaceful mode off and on
  round the wave, one cancelled chain (hop1's own roll was land.11, a chain head; forcing
  land.03 over it would still have delivered its punchline land.04 later) and a heal after
  each clean landing. The loop's 7 are the pins and 4 heals. The heals hide a MOD bug, not a
  look: the thud's health bar rides the next arc along the ground (G.12)
* on screen, the edit: the time-lapse draws its `tag` (`5x`) for as long as it plays and the
  freeze is muted. Slow-mo carries NO tag (storyboard A tags only the time-lapse) and neither
  does the 0.5 s poster hold at the top, which plays live sound under a still frame
* in the sound, the two readability calls under [Sound](#sound), both constants in mix.py

NOT liberties: forcing a row (the method - every row shown is a catalog row from the pool the
mod speaks from at that moment; where the mod rolled its own on the same tick, `said ...
replaced_by` records it), staging whose result is ordinary play (the engineer walking in and
boarding, a biter wave sent at him, the repair packs put in the roboport) and the post
captions standing in for his GUI bubble. The mod's narration world text is hidden every tick
and each hidden row logged `said ... hidden: true`, so the cross-check accounts for it. Two
honest gaps: the apology TIMING is the director's (break+270 / +570, which the mod only gets
near at speech-cooldown <= 5 s, apology-interval <= 10 s and unbearable - storyboard A's
reading of breakage.lua) and no event says so, and build.json names the take, not its
liberties - follow its `take` to the events.

### Captions

Post captions, drawn in Pillow from the mod's OWN locale string by row id
(`locale/en/jamaltron-lines.cfg`, `__1__` = the line event's `n`), because his speech bubble is
GUI and never reaches a `show_gui=false` frame (G.1). Styled after the compilatron bubble:
Titillium Web SemiBold 44 px at 1080p, text {255, 246, 113}, a dark translucent slanted box.
* timing is the game's fade-out: up 300 ticks from the tick said, fading 29 (speech.lua's
  SHOW/FADE_TICKS), replaced on the spot by the next line - mid-fade included, at the alpha
  its own fade had reached. In SOURCE ticks: a 1/3 span shows a caption three times as long.
  The pop-in is a choice (the game very likely fades in too; unmeasured - see captions.py)
* none during a time-lapse, none in a loop cut
* anchored on his drawn torso (the rule above), clear of his legs by body (standing 2.6
  tiles, beached 2.2, airborne 1.0 - MEASURED knee and broken-leg heights); in an arc it
  RATCHETS - holds the pre-takeoff height until he rises to it, rides up to the peak, holds
  there to the landing - so it never bobs; `caption = "below"` hangs it 4.8 tiles under the
  torso (the feet reach 4.3-4.6). Clamped inside the frame
* THE CROSS-CHECK, before anything encodes: every `jamaltron speech <unit> <row>` in run.log
  is a caption in this cut, or the take PROVES it never reached the screen (a `said` that
  checks out: a speech row's `replaced_by` is a line on the same tick, a narration row is
  `hidden`; or a `line` the cut drops or time-lapses). Anything else fails the build
  (`--allow-caption-mismatch` builds anyway and records it)

### Sound

Rebuilt from the events (Factorio cannot export its audio): each event becomes the sound the
game plays for it, read from the install at mix time, at the prototype's own volume, with two
readability calls - the legs lifted to 0.28 and the wind bed ducked 7.5 dB under the thud and
the flame - and no invented takeoff, break or flop sound. An event at source tick s plays on
the first frame of each LIVE segment whose [from, to) holds it with `src >= s`; a segment that
continues the flow does not re-trigger; a time-lapse's tail past its last sample plays where
the flow resumes. Pitch never shifts. The engine's aggregation is emulated in source time; a
time-lapse plays every round(speed)-th instance of each sound. Two-pass LINEAR normalisation to
-16 LUFS under -1.5 dBTP, measured with one meter (ebur128) both ways. mix.py's docstring has
every MEASURED number; `build.json`'s `mix` has the whole report of a build (loudness, cues,
drops, anything on no live frame).

### Encode

* master: rgb24 rawvideo from the pump -> `libx264 -preset slow -crf 20 -profile:v high -level
  4.2`, `scale=out_color_matrix=bt709:out_range=tv,format=yuv420p` + `setparams` (the
  `-color_*` flags alone do NOT reach the stream on ffmpeg 9.0.2, MEASURED), tagged bt709. An
  IDR on every segment start and a GOP longer than the longest hold: x264's 250 put one 1.1 s
  into the freeze and the still re-grained (MEASURED). Sound: AAC-LC 160k 48 kHz, muxed `-c:v
  copy`. A master with no sound FAILS (`--allow-silent-audio` to build one anyway)
* loop: one pass -> the portal mp4 (960x540 60 fps, NO audio track, < 1 MB) and the README GIF
  (every source frame at 2 cs = 50 fps, 720 wide, palette per diff, Bayer dither; 60 is
  unrepresentable and 25/30 judder)
* every output is ffprobed before the build calls itself done; everything is built into
  `<out>/.building-<pid>/` and moved in only when every check passed, so a late failure never
  leaves new media beside an old build.json. `--dry-run` writes to `<out>/dry-run/`

`tests/test_video_*.py` cover all of it without Factorio: fake takes (`tests/video_fake.py`,
each frame's colour encoding its tick), a fake factorio for video.sh, and real ffmpeg when it
is installed.

### Known limits

v0 as built from main-20260927-221640 (MEASURED unless it says otherwise). The look and the
mix are G.9's, chotchki's eye; what follows is what the pipeline itself does not do yet.

* the master is 78.2 MB (crf 20, 10.1 Mbit/s of grass and live water) against GitHub's 10 MB
  free-plan cap on a README video, so publishing needs a web encode (G.10). The master is the
  source, not the upload
* a take films at 60 UPS only with the machine to itself: with another Factorio running the
  main take filmed at 28.9 UPS (217 s wall) and the master built in 347 s, not 39. Every stamp
  still verified - load costs time, never frames
* 3.1 GB a main take (0.83 MB a frame), 0.3 GB a loop, and nothing deletes old ones. Keep the
  takes a build.json names
* Mac defaults: the game at `/Applications/factorio.app` (`FACTORIO_BIN`, `FACTORIO_DATA`
  otherwise), ffmpeg from Homebrew's keg (`FFMPEG` / `FFPROBE`, else PATH). A Steam or Linux
  install is covered by a unit test with a fake PATH ffmpeg, never run end to end
* captions keep the game's own 300 + 29 ticks, so some outlive their moment: land.03 over
  hop2, attacking.01 on the walk to the lake, repaired.07 through the encore's pull-out.
  `below`'s 4.8 tiles is measured on the standing body only
* the first 4.85 s is wind only (the engineer's footsteps are real game sounds with no event
  to hang them on), and the mix spans 28 LU (-16.1 LUFS, -1.9 dBTP). Nobody has listened to
  it critically yet
* the mod, on camera (G.12): the shadow's tail draws a thin line ~3 tiles right of a standing
  body (it crosses the creek in every loop frame), the d=20 apex shadow lands ~10 tiles right
  and 7 down of him on the grass while he is over water. The health-bar bug is hidden by the
  heals (see Liberties), not fixed
* the GIF plays 3.03 s of game in 3.64 s: 50 fps is the closest GIF delay to 60, and 25/30
  judder. 720 wide because 960 came out 4.88 MB against the ~3 MB target (`build.GIF_W`)
* `tools/lint.sh` gates the director's Lua; the other five harness mods under `harness/` are
  still outside it (26 luacheck warnings)

## Layout

```
pyproject.toml      deps + pytest config
.python-version     3.11, matches Blender's bundled CPython
uv.lock             committed
gen_lines.py        entry point (B.5): character/lines.md -> scripts/lines.lua (the picker's
                    table, no strings) + locale/en/jamaltron-lines.cfg (every string, one key
                    per id). Validates the catalog's whole machine contract first, and the
                    book fidelity when the gitignored extracts are on this machine
render/
  jamaltron.toml       EVERY art knob, with its default and what it does to the picture.
                       The one file you edit while iterating
  beached.toml         the flop (C.24): an OVERLAY on jamaltron.toml holding only what the
                       beached shark changes, plus the [sequence] of beats its sheet plays
  sequence.py          C.21: a [sequence] table -> unique per-frame configs + the order
                       they play in. Pure arithmetic; art.py renders it, pack.py packs it
  art.py               entry point, uv side. THE art harness (C.10): resolves the config,
                       decides which frames are missing, shells out to N Blenders, builds
                       the compare and contact sheets, stamps provenance on everything
  artconfig.py         the knob SCHEMA, resolution, validation, derived numbers and the
                       per-pass cache hashes. stdlib only, so both sides import it
  render_jamal.py      entry point, Blender side. Takes a resolved config, fixes the C.2 and
                       C.18a hazards (NLA, pivot, stale keyframes, shipped cams/lights, HEAD
                       parented to nothing), poses the rig from model.action, lifts it from
                       [bounce], renders N rotations of the body, shadow or mask pass
  pose.py              the five shipped clips: which action, which frames, which bones and
                       the arithmetic of a loop over one. `model.action`'s enum reads this
                       table, and every posed render re-checks it against the model. stdlib
                       only and imports no sibling -- artconfig imports IT
  tune.py              entry point, uv side. The slider UI (127.0.0.1, stdlib http.server):
                       drives the same ac.load -> render_pass -> compare_sheet path art.py
                       does, plus the flop's clip select, frame scrub and PLAY loop
  sheets.py            compare/contact sheet layout and compositing, plus the mount
                       self-check. Pure arithmetic above the Pillow import, so it tests
                       without rendering
  spritesheet.py       sheet layout math. stdlib ONLY, imported from both sides
  factorio_camera.py   the projection, the rotation order and the sun, with the provenance
                       of every constant. stdlib at import time (Pillow is imported inside
                       --verify), so both sides can use it. Runs three ways: print, --verify,
                       or as a Blender script
  icons.py             entry point, uv side. C.6 icon candidates: renders through art.py,
                       crops, builds base-shaped mipmap strips, minimap silhouettes, the
                       review sheets and a lint manifest. Renders write to render-out/ only;
                       --promote copies a reviewed candidate into the mod
  pack.py              entry point, uv side. THE packer (C.7): union frame box, shift,
                       sheet grid, then the SAME dict written out as Lua and as the JSON
                       manifest CI lints. Verifies its own output before it exits
  model_inspect.py     entry point, headless model triage (C.2): dimensions, origin, axes,
                       rig, animation clips, materials, texture sizes, hazards
  blender_check.py     entry point, proves headless Blender works
tests/
  conftest.py               the ONE Lua resolver (`lua` / `lua_optional` fixtures: JAMALTRON_LUA
                            or FAIL, else lua then luajit, skip only with neither), the
                            `shipped_model` digest every hash pin is taken on and
                            JAMALTRON_TEST_NO_MODEL=1 - this machine as a runner sees the model
  test_env.py               python version, Pillow present, spritesheet.py still stdlib-only
  test_art_harness.py       the C.10 harness's pure logic: knob resolution, cache keys,
                            sheet geometry and the mount self-check against stock art
  test_spritesheet.py       layout math, incl. two cases checked against shipped Factorio assets
  test_factorio_camera.py   projection against 8 muzzle positions the GAME computes, the sun
                            and the guard that keeps the module importable inside Blender
  test_pose.py              the clip table: its own consistency, the checker that catches
                            the model moving under it and the loop arithmetic
  test_tune.py              the tuner's two promises: the TOML export round-trips to the hash
                            the page printed, and nothing can slip out of the export
  test_pack.py              the packer: shift against the stock torso's own declaration,
                            the union box, the line_length divisor property over every
                            count, a byte-exact place-it-back round trip and the two
                            artifacts read through both of lint_sprites.py's front ends
  test_gen_lines.py         the line generator: the staleness gate CI runs, one test per
                            contract refusal, emission, fidelity and main()'s exit codes
  test_sequence.py          C.21/C.24: the overlay loader, beat expansion, the committed
                            cycle's seams, sequence packing and the frame_sequence lint
  test_mod_settings.py      D.3: every setting and dropdown value has its locale string
  test_speech_lua.py        D.5: runs tests/lua/ under conftest's `lua` (skips without one; FAILS
                            without the one JAMALTRON_LUA names - CI sets lua5.2), and pins
                            the row ids speech.lua hard-codes against the catalog
  test_ci.py                C.14: ci.yml's contracts with the scripts it calls - SHA-pinned
                            actions, every lint gate called by name, one Lua variable read in
                            one place (a bare `shutil.which("lua")` anywhere else fails, and a
                            bogus JAMALTRON_LUA is run for real: every Lua suite fails, none
                            skipped), the fmtk/API pins agreeing with gen-defs.sh and info.json
  test_lint_icons.py        C.15: the icon gate - every kind at base geometry, one test per
                            failure, the Lua front end, per-manifest roots, ci.yml's own
                            classifier exec'd against an icon manifest, base calibration
  test_icon_coverage.py     C.15: what CI's sprite job cannot see - hand-written Lua icons and
                            sprite tables of ours linted --strict, every icon-looking PNG in
                            the mod declared where a gate checks it; each proven failing on a
                            planted tmpdir mod
  test_icons.py             C.6: icons.py's pure half - crop, mip strip, silhouette, legs,
                            each candidate's manifest clean under the gate, --promote's copy
                            and refusals and every shipped path a Lua literal the readers see
  test_gun.py               D.7.4: the stream source, the leg hub it was picked under, W1's layers
                            (legs 'projectile', torso 'air-object' - 'smoke' draws him blurred)
  test_wreck_cover.py       D.1.3: every broken leg's mouth under an opaque pixel of every
                            frame the beached sheet plays (conftest's `lua`)
  lua/test_pick.lua         the D.5.1 picker against the real generated catalog
  lua/test_speech_cap.lua   F.3: the map-wide bubble cap - chatter at the cap never happens (no
                            bubble, echo, cooldown or anti-repeat), an event takes down the oldest
                            chatter bubble or goes up anyway, punchlines always land, slots free
                            at lifetime + fade-out, the setting read live, no roll at the cap
                            and a capped idle line waits in a queue, oldest due first (flops:
                            test_breakage.lua's, where a pairs() queue starved 31 of 100)
  lua/test_attack.lua       D.7: one attacking line per burst, the window, the friendly gate,
                            the damage filter switched with the bursts and derived on load
  lua/test_gun.lua          D.7: his gun built from base's tank-flamethrower, or without it
  lua/test_disarm.lua       D.7.3: the beached body's disarmed twin - same ammo categories,
                            every lever that stops it firing, made once, another mod's gun too
  lua/test_wreck.lua        D.1.3: his broken legs - every leg one piece (checked off the drawn
                            sprites), bent, inside ~6 tiles, off his face, rarely across another,
                            varied, 46 objects, redrawn when an update re-cuts the sprites
  video_fake.py             G.5-G.8: a FAKE take (frames whose colour encodes their tick, both
                            logs, run.log, verify.json) at any size, and the storyA/loop events
  test_video_timeline.py    the take's logs, the anchor grammar, every cut-file refusal, the
                            resolver and the shipped cut files against storyA-shaped takes
  test_video_stamp.py       the tick stamp: geometry pinned to camera.lua, JPEG round trips, a
                            shifted, duplicated, missing or unreadable frame failing verify
  test_video_captions.py    the text by row id, the game's timing (mid-fade replacement), the
                            anchor (T/T+1, the arc ratchet, below), the cross-check, the bubble
  test_video_pump.py        the band crop, play order, every compositing layer, the loop crop,
                            the encode and keyframe command lines
  test_video_mix.py         the soundtrack: onsets through every segment kind, aggregation,
                            the time-lapse thinning, loops, the gate, and real renders
  test_video_build.py       end to end on a fake take: the master and the loop through real
                            ffmpeg, the verify gate, staging, the audio refusal, the CLI
  test_video_sh.py          video.sh against a fake factorio: every argument, the profile and
                            --out refusals, the plumbing, the stamp verify
video/                G.5-G.8 (PLAN Phase G): a verified take + a cut file -> the deliverables.
                      The formats between these files are "The video" above
  timeline.py         the take's logs, the anchor grammar, the cut resolver -> frames.json
  stamp.py            the tick stamp: decode + verify every frame of a take (video.sh calls it)
  captions.py         the caption text, timing, anchor and bubble; the speech-log cross-check
  cards.py            the title and end cards (Titillium Web from the install)
  pump.py             frames -> crop, captions, tag, cards -> rgb24 -> ONE ffmpeg process
  mix.py              events + frames.json -> the mastered AAC, from the install's .oggs
  build.py            the CLI: take + cut -> checked, staged deliverables + build.json
  main.toml           the main take's cut (storyboard A)
  loop.toml           the loop take's cut (the README GIF + the portal loop)
harness/jamaltron-harness/  test-only mod smoke.sh --harness loads (D.5.4; grows into F.1)
harness/jamaltron-fire-harness/  D.7's flamethrower in the engine (--ticks 2300)
harness/jamaltron-video/  G.2-G.3: the video's DIRECTOR - the set, the event-driven beat
                      machine, the camera, the stamped capture and the two logs video.sh reads
playtest/jamaltron-playtest/  the /jamaltron-* console commands tools/play.sh loads
play.sh             the isolated playtest profile launcher
video.sh            G.4: the video's capture driver, its own profile in .videotest/
smoke.sh, build.sh  shell, not part of the uv project (PLAN A.2)
```
