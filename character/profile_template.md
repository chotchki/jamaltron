# Jamal character profile — Book {N}

Source: `extracts/book{N}_jamal.txt` (N is 7 or 8; he does not appear in 1–6)

Fill each section with characterization — traits, speech patterns, reflexes,
dynamics. NOT plot summary. If a trait needs a scene to be legible, name the
scene in one clause and move on.

This file feeds the merged profile (`jamal_profile.md`, PLAN B.2), which feeds
the situation→line catalog (`character/lines.md`, PLAN B.3), which generates
the mod's strings. So write it to be machinable: concrete triggers, concrete
reactions, concrete tics. Vibes do not survive the trip to Lua.

## Copyright rules (non-negotiable, chotchki's call)

- The raw book text NEVER leaves `character/extracts/` (gitignored, and it
  stays that way). This profile goes in the repo, so it is in OUR words.
- Paraphrase everything. Characterization, not transcription: no scene
  reproduced, no paragraph pasted, no "here is the passage where…".
- Verbatim quotes go ONLY in **Exemplar lines** and the quote column of
  **What triggers what**. Limits: ≤ 1 sentence each, ≤ 6 total in this file.
  A quote longer than one sentence is a violation, not a judgment call.
- Every quote must be an EXACT substring of the extract. Verify before you
  write it: `grep -F "<the line>" extracts/book{N}_jamal.txt`. No hit means
  you misremembered it, so fix it or drop it. The extracts use curly quotes
  and curly apostrophes; match them or grep a fragment that avoids them.
- A half-remembered or smoothed quote is a FABRICATION and the verify pass
  deletes it. If you are not certain a line is exact, paraphrase it in prose
  or tag it `(original, in his voice)` — an invented line in his register is
  fine and useful, a fake quote is not.

## Voice

### The apology habit (mod-critical — PLAN D.5, E.4 spam him on a timer)

The most important thing about him for this mod. Be exhaustive.

- **Shapes**: the distinct grammatical forms the apology takes — countable
  objects, a debt, a gift, a supply he can run out of? Note the verbs he
  pairs with them. Each shape is a reusable catalog template, so list shapes,
  not just instances.
- **Escalation**: an apology at low stakes (a bump, a mild inconvenience)
  versus after real damage (hurting someone, breaking something expensive,
  setting an ally on fire). Does the register get more formal as the offense
  gets worse, or less?
- **Targets**: who gets apologized to, by name and honorific and for what.
  Note who gets the most.
- **Unprompted?**: how often he apologizes for something nobody blamed him
  for (his existence, his size, his smell, taking up room). Flag pre-emptive
  apologies separately from reactive ones; the mod needs both (idle chatter
  vs event response).
- **What he does NOT apologize for**: the exceptions are where the protest and
  defense lines come from. Note anything he defends, protests or refuses to
  be sorry about.
- **Adjacent registers**: formal protest/complaint, embarrassed confession,
  asking permission, thanking. Same voice, and they fill catalog slots the
  apology alone can't.

### Third person vs. first person (the other signature tic)

- **Default**: which one he uses for himself, and how consistently.
- **The slip**: what makes him switch, mid-sentence or mid-speech. Tie it to
  emotional state if the text supports it (sincerity? fear? grief? wanting
  something badly?). Note whether and how he corrects himself.
- **Why the mod cares**: verbosity tiers and severity can key off this —
  routine chatter in one person, the rare serious line in the other. Say
  whether the book actually supports that mapping.

### Catchphrases & verbal tics

- **Stock openers and closers**: recurring formulas, exclamations, how he
  announces himself or his emotional state out loud.
- **Honorifics and address**: exactly how he names each person he talks to,
  and whether it ever drops.
- **Self-narration**: does he report his own states in the third person like
  a status line? That is exactly a Factorio speech bubble, so collect the
  shapes.
- **Malapropisms and invented compounds**: his mangled or over-cute terms for
  equipment, body parts, situations. They are free comedy in item
  descriptions and locale strings.
- **Intensifiers and qualifiers**: which ones recur.
- **Words he would never use**: register floor and ceiling. Whether (and
  where) he swears, and what it means when he does.

### Sentence shape

- Length, clause structure, politeness scaffolding. Does he over-build a
  sentence to be courteous? Bury the news at the end?
- Does he interrupt, get interrupted, trail off, repeat himself?
- **Line length budget**: his typical utterance length. Speech bubbles are
  short, so flag which tics survive a one-line truncation and which need two
  sentences to land.

### Register & vocabulary

- The 2–4 registers he actually has in this book (e.g. formal courtly,
  excited-child, miserable-complaint, rare-sincere), each with its trigger.
  The catalog's verbosity tiers map onto these, so be crisp.
- Class/species/origin flavor: ocean words, food words, shark instinct
  bleeding through the manners.

### Exemplar lines

3–5 short direct quotes (≤ 1 sentence each, grep-verified, counted against
the 6-quote budget). Tag each with the moment — "apologizing after breaking
his legs", "excited about an upgrade", "scared", "protesting". Prefer lines
the mod can reuse over lines that are only funny in context.

## Personality

- **Core traits**: 4–6 named traits, one line of paraphrased evidence each.
- **Drives**: what he actively wants. Be specific about the small stuff; the
  mod is built out of small wants.
- **Fears & insecurities**: what frightens him, what he covers for, what he
  admits only once.
- **Trait-in-action**: 2–3 behaviors that show a trait without stating it.
  These become event lines.
- **Self-image vs. reality**: where his read on himself is wrong. Note his
  identity question if the book raises it (what he was before, whether this
  version of him counts as him). It is the one place he gets un-funny, and
  the mod needs to know the line exists so it can spend it sparingly or not
  at all.

## His legs (mod-critical — the whole conceit; PLAN E.4 breaks them)

The mod exists because of the spider legs. It needs the mechanical facts AND
his feelings about them, separately.

- **Provenance**: who built each set, in order and how each was described
  (hasty prototype, upgrade, final version, who refined it, what changed).
  Count the sets if the book counts them.
- **Mechanism**: how he controls them (voice? thought? something between, and
  did it change?), what the harness attaches to, what else is bolted on
  (weapons, tools, grabbers) and who mounted it.
- **Failure modes**: what actually breaks them, how often and whose fault
  each time — his own doing or something done to him. The mod's leg-break
  roll is on LANDING from a jump, so be precise about what the books say
  jumping does to the legs.
- **How he treats them**: careless? proud? experimental? Does he test their
  limits on purpose? Does he understand he is why they break?
- **What he says when they fail**: the exact emotional shape — apology first?
  protest first? Does he blame the builders, the quality, himself, nobody?
  This is the line pool for `legs break` and the flopping loop, so collect
  more than feels necessary.
- **What he says when they are new/upgraded**: the `built` and `repaired`
  pools.
- **Quality complaints**: any recurring bit about the legs being (or not
  being) good enough. Flag it; it is a ready-made recurring gag.

## How he moves and flops (mod-critical — drives PLAN C.4 walk, C.5 flop loop)

The art pipeline reads this section. Physical description, not feelings.

- **On legs**: gait, speed, sound, silhouette and how other characters
  describe the look. Faster or slower than people expect? Quiet or loud? Any
  tell about leg count, joint style, posture, how high the body rides.
- **Off legs**: the flop. Mechanics first (roll? tumble? lunge? something
  like a jump?), then speed. Say explicitly whether flopping is slow and
  pitiful or alarmingly effective: the mod's beached state is meant to be a
  punishment and the books may disagree.
- **Jumping and hopping**: how often, what it looks like, why he does it,
  what it costs. Height, whether he can control it, whether he can see where
  he is going, and any stated reason he shouldn't.
- **Knocked over / stuck / out of position**: what happens and what he does
  about it — ceilings, hills, being hit, being somewhere his body doesn't fit.
- **Body facts for the render**: length/weight, breathing (air, water,
  both?), proportions or attachments a sprite has to show. Only what the
  text states.
- **Excitement tells**: what he physically does when happy. These become idle
  animation and idle lines.

## Relationships

- **Who he apologizes TO** (do this first, ranked): each person, the
  honorific, and what he typically apologizes to them for. The catalog
  addresses lines at the player, so note which dynamics translate to
  "talking to the person who owns/drives me".
- **Carl**: authority figure, owner, builder or friend — whatever the text
  supports. How he takes orders; what he does when told to stay behind.
- **Donut**: what she tolerates, what she scolds him for, what he does for her.
- **Others who recur**: one line each — builders, handlers, pets, other NPCs.
  Note anyone kind to him and anyone who isn't.
- **Standing in the group**: pet, soldier, tool or person? Does it change
  during the book? How does he think about it?

## Running gags

- Recurring jokes and beats, one line each. Mark which survive as a
  REPEATABLE bit (usable on a timer) versus one that only works once.
- Note anything funny BECAUSE it repeats — that is the mod's bread and
  butter.

## What triggers what

PLAN B.3 builds the line catalog directly off this section. Concrete
stimulus → concrete reaction pairs ONLY: no summaries, no "he is generally
apologetic". If you cannot name the stimulus, it does not go here.

Table it, one row per pair:

| Stimulus (in-book) | His reaction (paraphrased) | Register | Mod event |
|---|---|---|---|

- **Stimulus**: the specific thing that happened to him or near him.
- **Reaction**: what he says/does, in our words. A grep-verified ≤1-sentence
  quote is allowed if it is the definitive instance; it counts against the
  6-quote budget.
- **Register**: which of his registers fires (formal apology, protest,
  excitement, fear, misery, sincere).
- **Mod event**: the candidate Factorio event, or blank if none fits. Use
  PLAN B.3's vocabulary so B.3 can group rows mechanically: `built`, `enter`,
  `exit`, `moving`, `idle`, `attacking`, `damaged`, `low health`, `jump`,
  `land`, `legs break`, `flopping`, `repaired`, `died`, `command done`,
  `jump refused`.
- Aim for 15+ rows; thin coverage here means a thin mod. If an event in that
  list has NO book support, say so at the bottom of the section — it tells
  B.3 which lines have to be written fresh in his voice rather than adapted,
  a decision chotchki wants to make knowingly.

## Evolution within this book

How he changes start to end: what he gains (hardware, standing, confidence),
what he loses, what facet shows up late. Note anything that makes his earlier
lines read differently in hindsight.

## Open questions / contradictions

- Anything that doesn't fit, contradicts another passage or needs a second
  read before it goes in the canonical profile.
- Anything the mod needs that the book doesn't answer — call it out as a gap
  rather than guessing. B.4 is a review conversation with chotchki, and gaps
  listed here get decided there.
