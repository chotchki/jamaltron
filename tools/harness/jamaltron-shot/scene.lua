-- The scene tools/shot.sh stages. shot.sh OVERWRITES this in its profile's copy of the mod on
-- every run; this committed one is only the default a bare load gets.
return {
  scene = "beached",       -- beached | standing | both | many
  shots = {120},           -- ticks after staging, one screenshot each
  zoom = 1,
  resolution = {1600, 900},
  center = {0, 0},
  tile = "sand-1",
  prefix = "shot",
  many = 6,                -- breaks in the `many` grid (plus one standing for scale)
  spacing = 9,             -- tiles between them
}
