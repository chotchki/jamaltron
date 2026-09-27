-- D.5's speech bubble. Base's compilatron bubble under our own name, copied rather than
-- borrowed: the bubble's style and offset are what A.7's in-game measurement will tune (the
-- 60-character cap, and where it sits over a shark this tall), and a copy keeps that edit
-- here instead of reaching into base's prototype.
local C = require("prototypes.shared")

---@type data.SpeechBubblePrototype
local bubble = util.copy(data.raw["speech-bubble"]["compi-speech-bubble"])
bubble.name = C.speech_bubble

data:extend({bubble})
