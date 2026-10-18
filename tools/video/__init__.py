"""G.5-G.8: the gameplay-video pipeline - a verified take (one jpg a tick plus the director's
event and track logs) -> a cut -> the picture, the sound and the deliverables.

The Factorio half is tools/video.sh and tools/harness/jamaltron-video; everything here runs
without the game (it reads the install's fonts and sounds at build time, never copies them).
The formats between the pieces - the "contract" the comments here cite - are written down in
tools/README.md's Video section; each module's docstring says which part it owns.
"""
