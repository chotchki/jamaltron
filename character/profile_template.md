# Jamal character profile — Book {N}

Source: `extracts/book{N}_jamal.txt` (N is 7 or 8; he does not appear in 1–6)

Fill each section with *characterization* — traits, speech patterns, reflexes,
dynamics. **Not plot summary.** If a scene has to be named to make a trait
legible, name it in one clause and move on.

This file feeds the merged canonical profile (`jamal_profile.md`, PLAN B.2),
which feeds the situation→line catalog (`character/lines.md`, PLAN B.3), which
generates the mod's actual strings. So everything here is written to be
*machinable*: concrete triggers, concrete reactions, concrete tics. Vibes do
not survive the trip to Lua.

## Copyright rules (non-negotiable, chotchki's call)

- The raw book text NEVER leaves `character/extracts/` — that directory is
  gitignored and stays that way. This profile goes in the repo, so it is
  written in OUR OWN WORDS.
- Paraphrase everything. Characterization, not transcription. No scene
  reproduced, no paragraph pasted, no "here is the passage where…".
- Verbatim quotes are allowed ONLY in **Exemplar lines** and in the quote
  column of **What triggers what**. Limits: **≤ 1 sentence each**, **≤ 6
  total in this file**. A quote longer than one sentence is a violation,
  not a judgment call.
- **Every quote must be an exact substring of the extract file.** Verify it
  before you write it: `grep -F "<the line>" extracts/book{N}_jamal.txt`. No
  hit means you misremembered it — either fix it or drop it. Beware the
  extracts use curly quotes and curly apostrophes; match them or grep on a
  fragment that avoids them.
- A half-remembered or smoothed-out quote is a FABRICATION. The verify pass
  deletes those. If you are not certain a line is exact, write it as a
  paraphrase in prose instead, or tag it `(original, in his voice)` — an
  invented line in his register is FINE and useful, a fake quote is not.

## Voice

### The apology habit (mod-critical — PLAN D.5, E.4 spam him on a timer)

This is the single most important thing about him for this mod. Be exhaustive.

- **Shapes**: catalog the distinct grammatical forms the apology takes —
  does he treat apologies as countable objects, as a debt, as a gift, as a
  supply he can run out of? Note the verbs he pairs with them. Each distinct
  shape is a reusable line template for the catalog, so list shapes, not
  just instances.
- **Escalation**: what does an apology look like at low stakes (a bump, a
  mild inconvenience) versus after real damage (hurting someone, breaking
  something expensive, setting an ally on fire)? Does the register get more
  formal as the offense gets worse, or less?
- **Targets**: who gets apologized to, by name and honorific, and for what.
  Note who gets the most.
- **Unprompted?**: how often does he apologize for something nobody blamed
  him for — his own existence, his size, his smell, taking up room? Flag
  pre-emptive apologies separately from reactive ones; the mod needs both
  (idle chatter vs. event response).
- **What he does NOT apologize for**: the exceptions are load-bearing. Note
  anything he defends, protests, or refuses to be sorry about.
- **Adjacent registers**: formal protest/complaint, embarrassed confession,
  asking permission, thanking. These sit next to the apology in the same
  voice and fill catalog slots the apology alone can't.

### Third person vs. first person (the other signature tic)

- **Default**: which does he use for himself, and how consistently.
- **The slip**: what makes him switch, mid-sentence or mid-speech. Tie it to
  emotional state if the text supports it (sincerity? fear? grief? wanting
  something badly?). Note whether he corrects himself when he slips, and how.
- **Why the mod cares**: verbosity tiers and situation severity can key off
  this — routine chatter in one grammatical person, the rare serious line in
  the other. Say whether the book actually supports that mapping or not.

### Catchphrases & verbal tics

- **Stock openers and closers**: recurring formulas, exclamations, the way he
  announces himself or his own emotional state out loud.
- **Honorifics and address**: exactly how he names each person he talks to.
  Note whether it ever drops.
- **Self-narration**: does he report his own feelings/states in the third
  person as if reading a status line? This is gold for a Factorio speech
  bubble — collect the shapes.
- **Malapropisms and invented compounds**: his mangled or over-cute terms for
  equipment, body parts, situations. List them; they are free comedy in item
  descriptions and locale strings.
- **Intensifiers and qualifiers**: which ones recur.
- **Words he would never use**: register floor and ceiling. Note where (and
  whether) he swears, and what it means when he does.

### Sentence shape

- Length, clause structure, politeness scaffolding. Does he over-build a
  sentence to be courteous? Does he bury the actual news at the end?
- Does he interrupt, get interrupted, trail off, repeat himself?
- **Line length budget**: note his typical utterance length. Speech bubbles
  are short — flag which tics survive a one-line truncation and which need
  two sentences to land.

### Register & vocabulary

- Name the 2–4 distinct registers he actually has in this book (e.g. formal
  courtly, excited-child, miserable-complaint, rare-sincere) with the trigger
  for each. The catalog's verbosity tiers map onto these, so be crisp.
- Note anything that reads as class/species/origin flavor: ocean words, food
  words, shark instinct bleeding through the manners.

### Exemplar lines

3–5 short direct quotes (**≤ 1 sentence each**, grep-verified, counted
against the 6-quote budget). Tag each with the kind of moment —
"apologizing after breaking his legs", "excited about an upgrade",
"scared", "protesting". Prefer lines that are reusable in the mod over
lines that are merely funny in context.

## Personality

- **Core traits**: 4–6 named traits, one line of evidence each, paraphrased.
- **Drives**: what he actively wants. Be specific about the small stuff — the
  mod is built out of small wants.
- **Fears & insecurities**: what frightens him, what he covers for, what he
  admits only once.
- **Trait-in-action**: 2–3 behaviors that demonstrate a trait without stating
  it. These become event lines.
- **Self-image vs. reality**: where his read on himself is wrong. Note his
  identity question if the book raises it (what he was before, whether this
  version of him counts as him) — it is the one place he gets un-funny, and
  the mod needs to know that line exists so it can be used sparingly or not
  at all.

## His legs (mod-critical — the whole conceit; PLAN E.4 breaks them)

The spider legs are why this mod exists. The mod needs the mechanical facts
AND his feelings about them, separately.

- **Provenance**: who built each set, in order, and how each one was
  described — hasty prototype, upgrade, final version, who refined it, what
  changed between them. Count the sets if the book counts them.
- **Mechanism**: how he controls them. Voice? Thought? Something in between,
  and did that change? What the harness attaches to, what else is bolted on
  (weapons, tools, grabbers), who mounted it.
- **Failure modes**: what actually breaks them, and how often. Whose fault it
  is each time. Whether the break is his own doing or something done to him —
  the mod's leg-break roll is on *landing from a jump*, so be precise about
  what the books say jumping does to the legs.
- **How he treats them**: careless? proud? experimental? Does he test their
  limits on purpose? Does he understand he is the reason they break?
- **What he says when they fail**: the exact emotional shape — apology first?
  protest first? Does he blame the builders, the quality, himself, nobody?
  This is the line pool for the `legs break` event and for the flopping loop,
  so collect more here than feels necessary.
- **What he says when they are new/upgraded**: the `built` and `repaired`
  event pools.
- **Quality complaints**: any recurring bit about the legs being (or not
  being) good enough. Flag it — it is a ready-made recurring gag for the mod.

## How he moves and flops (mod-critical — drives PLAN C.4 walk, C.5 flop loop)

The art pipeline reads this section. Physical description, not feelings.

- **On legs**: gait, speed, sound, silhouette. How other characters describe
  the look of it. Does he move faster or slower than people expect? Is he
  quiet or loud? Any tell about leg count, joint style, posture, how high the
  body rides.
- **Off legs**: the flop. How he gets around with no legs at all — mechanics
  first (roll? tumble? lunge? something that resembles a jump?), then speed.
  Note explicitly whether flopping is *slow and pitiful* or *alarmingly
  effective*, because the mod's beached state is meant to be a punishment and
  the books may disagree.
- **Jumping and hopping**: how often, what it looks like, why he does it, what
  it costs. Note height, whether he can control it, whether he can see where
  he is going, and any stated reason he shouldn't.
- **Knocked over / stuck / out of position**: what happens and what he does
  about it. Includes ceilings, hills, being hit by things, being somewhere his
  body doesn't fit.
- **Body facts for the render**: length/weight, breathing (air, water, both?),
  anything about proportions or attachments that a sprite has to show. Keep
  this to what the text states.
- **Excitement tells**: the physical things he does when happy — these become
  idle animation and idle lines.

## Relationships

- **Who he apologizes TO** (do this first, ranked): each person, the honorific
  he uses, and what he typically apologizes to them for. The mod's line
  catalog addresses lines at the *player*, so note which of these dynamics
  translates to "talking to the person who owns/drives me".
- **Carl**: authority figure, owner, builder, or friend — pick what the text
  supports. How he takes orders. What he does when told to stay behind.
- **Donut**: what she tolerates, what she scolds him for, what he does for her.
- **Others who recur**: one line each — builders, handlers, pets, other NPCs.
  Note anyone who is kind to him and anyone who isn't.
- **Standing in the group**: is he a pet, a soldier, a tool, a person? Does
  that change during the book? How does he think about it?

## Running gags

- Jokes and beats that recur within this book, each in one line. Mark any that
  survive as a *repeatable* bit (usable on a timer in the mod) versus one that
  only works once.
- Note anything that is reliably funny *because* it repeats — those are the
  mod's bread and butter.

## What triggers what

The most load-bearing section: PLAN B.3 builds the line catalog directly off
it. **Concrete stimulus → concrete reaction pairs only.** No summaries, no
"he is generally apologetic". If you cannot name the stimulus, it does not go
here.

Table it. One row per pair:

| Stimulus (in-book) | His reaction (paraphrased) | Register | Mod event |
|---|---|---|---|

- **Stimulus**: the specific thing that happened to him or near him.
- **Reaction**: what he says/does, in our words. A grep-verified ≤1-sentence
  quote is allowed here if it is the definitive instance — count it against
  the 6-quote budget.
- **Register**: which of his registers fires (formal apology, protest,
  excitement, fear, misery, sincere).
- **Mod event**: the candidate Factorio event, or blank if none fits. Use this
  vocabulary (from PLAN B.3) so B.3 can group rows mechanically:
  `built`, `enter`, `exit`, `moving`, `idle`, `attacking`, `damaged`,
  `low health`, `jump`, `land`, `legs break`, `flopping`, `repaired`, `died`,
  `command done`, `jump refused`.
- Aim for 15+ rows. Thin coverage here means a thin mod. If an event in that
  list has NO book support, say so explicitly at the bottom of the section —
  that tells B.3 which lines have to be written fresh in his voice rather than
  adapted, which is a decision chotchki wants to make knowingly.

## Evolution within this book

How he changes start to end: what he gains (hardware, standing, confidence),
what he loses, what new facet shows up late. Note anything that makes his
earlier lines read differently in hindsight.

## Open questions / contradictions

- Anything that doesn't fit, contradicts another passage, or needs a second
  read before it goes in the canonical profile.
- Anything the mod needs that the book simply doesn't answer — call it out as
  a gap rather than guessing. B.4 is a review conversation with chotchki;
  gaps listed here get decided there.
