# Jamal — situation → line catalog

**THIS FILE IS THE SINGLE SOURCE OF TRUTH FOR EVERY STRING THE MOD SPEAKS.** `scripts/lines.lua` and `locale/en/jamaltron.cfg` are GENERATED from it by `tools/gen_lines.py` (PLAN B.5). Both generated files carry a header saying so. **Never hand-edit the generated files** — the next generator run silently eats the edit, and the diff will not tell you which side is right.

Built from [`jamal_profile.md`](jamal_profile.md) and its 125-line verified quote bank, which in turn came from the two per-book profiles. Characterization and every `original` line below are OURS. The book text itself never leaves the gitignored `extracts/`.

## Copyright posture (chotchki's locked call, SPEC.md)

Verbatim lines are **short single-sentence-or-less utterances of one character**, gathered under the non-commercial fan-work fair-use call. No scene, paragraph or exchange is reproduced anywhere. **B.4 IS NOW LOCKED IN FULL (2026-09-19, chotchki), so every `SOURCE: verbatim` row below is a shipping decision rather than a candidate flag.** Two of the rulings have copyright or distribution consequences: the player is *Mr. Engineer* and every Dungeon Crawler Carl proper noun is out of the `Line` column (Q1/Q5 — the ruling that created the third `SOURCE` tag below), and **the one profanity line is CUT** (Q2), so no shipping string in this file contains profanity and the mod portal page needs no content note.

**Every line marked `verbatim` in this file has been machine-verified as an exact substring of the matching extract** (106 distinct strings across 162 rows, plus every full quote quoted in a `Note` cell and every `ORIGINAL:` quote standing behind an `adapted` row; all exact, zero fabrications). Re-verify before B.5 generates anything — a miss is a fabrication and gets deleted, not fixed:

```sh
cd character/extracts && grep -qF -- "<the line>" book7_jamal.txt   # or book8_jamal.txt
```

**Trimmed lines are still verbatim, because every trim is a CONTIGUOUS substring** — a prefix, a suffix, or a whole inner clause. Nothing was cut out of the middle and stitched back together, because that produces a sentence he never said while still passing a careless eyeball check. The `Note` column carries the full quote wherever a trim exists.

**`adapted` is the third provenance tag and it exists for exactly one move: a real quote whose PERSON-REFERENCE we changed.** Chotchki's B.4 Q1/Q5 ruling swaps the book's addressee for *Mr. Engineer*, and at `repaired.08` drops a third-party attribution that has nobody left to point at. Such a line is neither of the other two tags — calling it `original` claims we wrote it, calling it `verbatim` lies to the fidelity checker. So: **`adapted` means the provenance is a real quote, the ONLY thing changed is the person-reference, and the untouched original is recorded in the `Note` cell behind the literal marker `ORIGINAL:` in straight double quotes.** That marker is a machine contract, not decoration — the checker greps it and validates the source line exactly as it validates a `verbatim` row, so an adapted row stays as traceable as the day it was a quote. 14 rows carry it. Everything in the paragraph below still applies to every word around the swapped name.

**Smoothing a quote is fabricating it.** His double plurals (*sticky feets*), his ellipses, his em-dash interruption, his curly apostrophes and his trailing dialogue-tag commas are the signal, and they are reproduced character for character. Where a line reads like a fragment (`Gentlemen,` / `I must give you an apology`) that is because the book punctuates it that way.

## How to read the table (the machine contract for B.5)

Every section is `## <event>`, then a `key:` line naming the Lua table key, then a `split:` line, then a `fires:` note, then ONE table with these **eleven** columns in this order:

| Column | Meaning |
|---|---|
| `ID` | stable, unique across the whole file. Becomes the locale key `jamaltron-line.<id>`. Never renumber an ID that has shipped |
| `Line` | the string, exactly as it should render. **Every row has one** — there is no longer any such thing as a pool entry with no string (see the channels section) |
| `CH` | `speech` \| `narration` — **which of the mod's two output channels this row goes to.** Newest column and the most load-bearing one; see the channels section immediately below |
| `SOURCE` | `verbatim` (exact substring of an extract), `adapted` (a real quote with only the person-reference changed; the untouched original sits in `Note` behind `ORIGINAL:`), or `original` (written by us in his voice). **Load-bearing — do not blur these** |
| `BK` | `7` or `8` for verbatim, `-` for original |
| `W` | integer relative weight WITHIN this pool. Not a probability, not normalized — the picker sums the eligible rows and rolls |
| `TIER` | `quiet` \| `normal` \| `unbearable` |
| `SUB` | subpool or tag, or `-`. **What it MEANS is set by the section's `split:` line, never inferred from this column** — see below |
| `GATE` | `-` or `once_per_save` — a hard once-per-entity-per-save eligibility gate, orthogonal to `W` and `TIER`. 9 rows carry it; see the gate section |
| `GRP` | anti-repeat group: the ID of the FIRST row in this file carrying that exact `Line`. A unique string is its own group. **Computed, never hand-assigned.** D.5 keys anti-repeat on this, per ENTITY, across pools |
| `Note` | why the line is here, the full quote when trimmed, the `ORIGINAL:` quote when adapted, and the B.4 ruling where one applies |

**IDs were renumbered twice, both on 2026-09-19, and that door is now CLOSED.** Renumbering was legal for exactly one reason: **nothing references these ids yet** — `scripts/lines.lua` and `locale/en/jamaltron.cfg` do not exist until B.5 generates them. **The moment B.5 runs, an id becomes a locale key, a locale key is a public contract, and a cut row leaves a GAP whose id is retired forever.**

- **Pass 1, the Q5 proper-noun purge, cut three rows.** `command_done`'s two were the tail of its own pool so it simply got shorter; OLD `idle.25` was mid-pool, so `idle` was renumbered — old `idle.26`–`.39` became `idle.25`–`.38`. **`idle.25` therefore names two different rows depending on which side of this pass you are reading, and pass 3 has now retired the second one. That is the whole case against renumbering in one id**, and it is why the pass-3 cuts left gaps instead.
- **Pass 2, the B.4 cuts, cut six rows** (Q2, Q3 and Q12). Four were pool tails and cost nothing: `attacking.15`, `jump.14`, `legs_break.33`, `flopping.42`. Two were mid-pool, so both pools were renumbered: `damaged` old `.09`–`.16` are now `.08`–`.15`, and `flopping` old `.38`–`.41` are now `.37`–`.40`.
- **Pass 3, the voice-audit cuts, cut three rows — AND THIS IS THE PASS THAT LEFT GAPS, ON PURPOSE.** `idle.24` and `jump_refused.18` (one string, *You need to remain in the garage.*, reused in two pools: it reads as Jamal ORDERING the engineer, which he never does, into a garage Factorio does not have) and `idle.25` (*He’s still very sad about his friends.* — social reporting with no possible referent in single-player). **Nothing was renumbered and nothing will be.** `idle` now runs `.01`–`.23` then `.26`–`.38`, `jump_refused` skips `.18`, and those three ids are retired. This is the door in the paragraph above working as designed rather than an exception to it.

**Every in-file cross-reference moved with the rows both times, and that is the step that bites.** Pass 1 shipped with a stale id range that had to be hand-fixed afterwards; pass 2's movers were `flopping.39` → `flopping.38` (the over-cap row, referenced from the length note and from Q8) and `flopping.41` → `flopping.40` (referenced twice from the Q5 swap list). **If a third renumber is ever proposed, the answer is no** — it is now cheaper to live with a gap than to re-audit the references.

### The two output channels — `CH` (chotchki's B.4 ruling, and it is structural)

**The mod has TWO output channels, not one.** `CH` says which one a row belongs to, and it is the first thing a generator should read after `Line`.

- **`speech` — Jamal talking.** Renders as a speech bubble over the entity. **Strict register:** he puts himself in the SUBJECT slot (`Jamal is <verb>ing`), the honorific never drops, and there is no irony and no wordplay outside his own malapropisms. **262 rows.**
- **`narration` — the GAME describing him.** Third person, ABOUT him rather than BY him, and **this is where the books' own narration voice legitimately lives** — the dry aside, the footfall onomatopoeia, the flagged silence. Renders as something visibly not a bubble (floating text or a chat line; D.5 picks). **12 rows.**

**One column, two findings closed, which is why chotchki's framing beats the six separate fixes it replaced.** The rows a voice audit flagged as *off-voice narrator syntax* — `moving.03` *Clack, clack, clack go Jamal's feet.*, `jump.04` *Up goes Jamal!*, `land.08` — were never off-voice. **They were in the WRONG CHANNEL.** A fronted verb makes him the OBJECT of a sportscast, which is wrong in his mouth and exactly right in the narrator's, and the footfall onomatopoeia is the book's narrator looking at him from outside in the first place. Nothing needed cutting; three rows needed moving. **The later voice audit found the ruling had under-applied itself** — two more rows sat in the wrong channel on the identical diagnosis (`flopping.23`, whose own Note called it a caption, and `moving.11`, which uses the narration's *whir* in the pool `moving.03` had just been moved out of), and `died.08` is mis-channelled for a different reason: a past-tense verdict on his whole self is an EPITAPH, and only a survivor utters one. And `[SILENCE]` stops meaning *emit nothing* and becomes a narration note, which is the other half of the same ruling.

**B.5 emits `CH` per row and D.5 renders on it.** A generator that flattens the channel ships twelve rows as Jamal saying things about himself in a voice he demonstrably does not have — the exact failure the audit caught, reintroduced by the tooling.

**The `split:` line is the whole `SUB` contract, and it has exactly three values.** `SUB` is overloaded on purpose — three incompatible meanings in one column — so the `split:` line is what disambiguates them, and a generator MUST read it before it reads the table:

- `none` — every row is in one pool. Any non-`-` `SUB` here is an ADVISORY tag for B.4 (`sincere`, `meta`); it changes nothing about the roll. **This is the common case: 12 of the 15 sections.**
- `required — a | b` — a real fork. The mod knows which side fired before it rolls, and rolls inside that side only. Two sections: `enter/exit` and `legs break`.
- `gated — <tag>` — conditional eligibility. Tagged rows are excluded unless the mod has confirmed the condition, and included in the ordinary roll when it has. One section: `attacking` (`friendly`).

**A generator that treats every non-`-` `SUB` as a fork silently breaks three pools** — it would make `idle`'s four weight-1 sincere lines a coin flip against the other 32 rows, and it would make `jump.13`, the single surviving `meta` row, either half of all jumps or unreachable. This paragraph exists because that is the single easiest way to get B.5 wrong. **Note that `SUB = sincere` is now doubly advisory:** those rows are gated by the `GATE` column, not by `SUB`, so a generator that ignores `SUB` entirely on a `split: none` section is CORRECT and one that forks on it is wrong twice.

**Tiers are CUMULATIVE.** `quiet` plays quiet only. `normal` plays quiet + normal. `unbearable` plays everything. So a `quiet` line is not a quiet line, it is a line good enough to survive a friend opting mostly out — those are the best ones, and `unbearable` is where the apology spam lives.

**Tiers key off REGISTER, not just volume** — this is the profile's most machinable finding and the one most likely to get flattened by accident. His escalation is INVERTED: formality is inversely proportional to actual severity, so the routine events get the baroque politeness and the rare serious events get the plain short words. A tier system that only prunes frequency loses the joke.

**Tokens** (the generator substitutes, the locale file uses `__1__` style parameters):

- `{PLAYER}` — **GONE. RESOLVED 2026-09-19 (chotchki): the player is *Mr. Engineer*, and the literal string is baked into all 26 rows that carried the token.** Reason: Factorio's engineer is canonically NAMELESS — that is Wube's own position, so there is no real name to use — and Jamal's honorific tic is about the FORM, not the name: *Mister* / *Mr.* / *Miss* + given name, never dropped, applied to literally everyone including a pet dinosaur. *Mr. Engineer* satisfies the form and is canonical Factorio. **Baked rather than left as a token because there is no per-player variance left to represent**, and baking it makes the authored character counts in this file TRUE — B.5 substitutes nothing and re-measures nothing. *Gentlemen* stays where the book used it (`legs_break.32`, `flopping.25`), because he addresses groups that way regardless of who is actually present.
- `{N}` — this entity's cumulative leg-break count. **SHIPS (B.4 Q9).** Both books count hardware out loud and book 7 counts it in protest; the mod already knows the number, so the gag gets better every time it fires. **Cheapest high-value feature in the character.** 4 rows use it — `legs_break.17`, `legs_break.27`, `flopping.30`, `repaired.06` — and they top out at 50 characters even with a three-digit count.

  **Storage cost, stated precisely so E.6 can price it:** `{N}` needs `storage`-only per-entity state, which E.6 already requires for multiplayer sync, so this is a table keyed by `unit_number` holding an integer — plus, in the same table, the `once_per_save` fired-set the `GATE` column needs. **No mutable module-level state, no per-tick work, one entry per jamaltron.** The entry is created lazily on the first break and removed on `on_entity_died` / `on_object_destroyed`, or it leaks one small record per destroyed entity for the life of the save.

**`[SILENCE]` IS GONE. The six silence rows are now NARRATION rows with real strings (B.4 Q7).** The old encoding was *the picker selects this row and emits nothing*, and it was wrong twice over: a speech mod is structurally bad at silence, and an emitted absence is indistinguishable from a mod that failed to fire. **In both books his going quiet is how the text says something is badly wrong, and both narrations FLAG it as the anomaly** — so the mod flags it too, in the channel built for exactly that.

chotchki's wording for the shape is *Jamal is silent... for once*. **Each of the six carries its own per-pool wording rather than that one string six times**, because a silence at `died` and a silence at `low_health` are not the same moment even though the books use his silence as the distress signal in both:

| Row | String | The moment |
|---|---|---|
| `attacking.03` | Jamal has stopped apologizing. Jamal is feeding. | bk 7's berserker frenzy switches the manners off entirely |
| `damaged.02` | Jamal makes a noise that is not a word. | damage is a NOISE in both books, never a sentence |
| `low_health.01` | Jamal has gone quiet. That is never a good sign. | the distress signal — still deliberately the heaviest row in the file |
| `legs_break.18` | The legs come apart. Jamal says nothing at all. | bk 8's break is wordless; the event happens and he says nothing |
| `repaired.13` | Jamal is silent... for once. | the contented come-down, and the one pool that earns the dry *for once* |
| `died.01` | Jamal does not get up. | mercy. Nobody in two books is ever cruel to him, so no punchline |

All six are `SOURCE = original`, `BK = -`, `CH = narration`, at their previous weights and tiers. `died.01` reads *Jamal does not get up.* rather than *Jamal is quiet now.* since the voice audit — see below.

**THE PREFIX SHIPS, AND D.5 APPLIES IT AT RENDER TIME.** chotchki's Q7 wording specified the encoding literally — *Game Note: <Jamal is silent ... for once>* — and this file recorded the comment, dropped the prefix and deferred to D.5 without recording that it had deferred anything. That is how a stated encoding goes missing. **So, decided and written down: every `narration` row renders as `Game Note: ` + the row's string, and the prefix lives in the RENDERER, not in the `Line` column.** One place instead of twelve, because twelve cells is twelve chances to typo the same eleven characters; the length cap and the fidelity checker should measure the string we actually authored and nothing else; and a wrapper D.5 owns changes once, in one file, when chotchki looks at real floating text in-game.

Two consequences, stated rather than discovered later:

- **The ≤ 60 cap is a speech-BUBBLE constraint and narration does not render in a bubble**, so the wrapper costs nothing against it. D.5's own width budget is the longest narration string plus the wrapper: **48 + 11 = 59 characters** today (`low_health.01` and `attacking.03` tie for longest).
- **The angle brackets are read as chotchki's placeholder notation for the row's string, not as literal characters to print.** That is the one interpretation call in this ruling, it is flagged here rather than buried, and it is cheap to flip — one line here and one line in D.5 — if he wants the brackets rendered.

**THREE OF THESE ROWS ASSERT AN ONGOING SILENCE, AND A NAMED SILENCE THE MOD BREAKS INSIDE A TICK IS A SHRUG.** The profile's version of him going quiet is a SUSTAINED absence — hours hanging off a ceiling saying nothing, a whole feeding frenzy, a wordless break — and naming the silence and then talking straight over it is worse than never naming it, because the player learns the narration lies. **D.5 MUST HONOUR A SUPPRESSION WINDOW on these three.** Each has a boundary the mod already computes, so this is bookkeeping and not a new subsystem:

| Row | The window | The boundary the mod already has |
|---|---|---|
| `attacking.03` | the rest of the current combat burst | the `attacking` throttle — no row fires again until the gun has been quiet long enough to re-arm the pool |
| `legs_break.18` | the first `flopping` interval | the apology timer's first tick is skipped, which is also bk 8's actual beat: the break, and only then the flopping |
| `low_health.01` | 15 s of `speech` on that entity (suggested — A.7 can tune it against a real bubble) | one timestamp per entity, in the same `storage` record as `{N}` and the `once_per_save` fired-set |

**Scope, so nobody has to guess at it:** the window is per ENTITY, it suppresses the `speech` channel only (the narrator is not him, so narration still fires), and it SUPPRESSES rather than re-rolls — emitting a second-choice line is the exact failure this ruling exists to prevent. **It gates BEFORE the roll, which is the detail that keeps the paragraph below true:** the picker still has no emit-nothing branch, because a suppressed event never reaches the picker at all. **`damaged.02`, `repaired.13` and `died.01` need no window and ship as they are:** a noise is not a silence, a wreck has nothing left to contradict it, and the come-down at `repaired.13` is the only one of the three that could earn a window later, if in-game the bubble after it reads as the mod stepping on its own beat.

**This changes the Lua shape B.5 emits**, and in the simplifying direction: there is no longer a pool entry with no string, so the generator has no absent-string branch at all and D.5's picker has no "emit nothing" path to get wrong. The only new conditional is which channel to render in.

**Line length.** Hard target ≤ 60 characters — it renders over a walking vehicle in a Factorio speech bubble. Two shipped lines sit slightly over (61 and 64) and are flagged in place with a trim offered; everything else fits. Median line length here is 38 characters, which matches him: his median usable utterance across two books is 5–9 words.

**The cap is now measured on the SHIPPING string, because there is nothing left to substitute into it.** Baking *Mr. Engineer* in killed the old caveat: the token was 8 characters and the literal is 12, and at that width the longest affected rows are `repaired.03` and `repaired.16` at **58**. **Zero rows cross 60 as a result of the bake, so the authored lengths in this file are the real lengths and B.5 does not have to re-measure** (the two rows that were already over are below). The only token left is `{N}`, 1–3 characters, and the four rows carrying it top out at **51** even with a three-digit count (`legs_break.17`, `legs_break.27`, `flopping.30`, `repaired.06`). **The two rows over the cap (`flopping.38` at 61, `jump_refused.19` at 64) stay UNTRIMMED, by ruling (B.4 Q8).** They were over before any of this, both have a trim written into their `Note` cell, and neither trim gets taken on a guess — **chotchki measures a real speech bubble in-game at A.7 and the number decides.** Trimming now would spend *reverse psychologicalize*, his best malaprop, to satisfy a cap nobody has verified exists at 60. These two are also the only over-cap rows this file will ever have: *Mr. Engineer* is baked in, the longest row it touches lands at 58, and `{N}` tops out at 51.

## Anti-repeat — the `GRP` contract (B.4 Q13, locked)

**Anti-repeat keys on `GRP`, per ENTITY, ACROSS pools. Not on `ID`, and not per pool.** 214 distinct strings fill 274 rows and **47 of those strings live in more than one pool**, so per-pool suppression is blind precisely where it matters most: `legs break` and `flopping` fire back to back — the break, then the apology timer — and **they share 16 strings.** A per-pool suppressor cannot see that `flopping` is about to re-say the break line the player read two seconds ago, at the mod's centerpiece moment. Same shape, smaller, for `built` ∩ `repaired` (6 shared), and *Jamal must protest!* / *Nothing is wrong.* each span four pools.

`GRP` is **the ID of the FIRST row in this file carrying that exact `Line`**; a row whose string is unique is its own group. **It is computed, never hand-assigned** — hand-assignment is how the same sentence lands in two groups and the mechanism silently stops working while still looking correct in review.

**The locale file is NOT deduplicated: one key per `ID`, always.** It costs a few hundred bytes, it keeps ID→key total, and it leaves a reused line free to diverge per pool later. **`GRP` is for the picker, `ID` is for the locale**, and conflating them is the one way to get this wrong in both directions at once.

**One canonical exception, recorded as an explicit allow-list.** `idle.01` → `idle.02` is the same observation said once and then repeated later verbatim with *indeed* bolted on; he is the only character in the books who quotes himself, and a system allowed to repeat that one succession reproduces a gag he performs on himself. Two honest notes on it: the pair is two different strings and therefore two different groups, so **a strictly group-keyed suppressor already permits it** — the allow-list exists so a later near-duplicate heuristic cannot silently kill the gag, and so D.5 has a hook if it ever wants to CHAIN the pair deliberately rather than merely permit it. And record it as an **ordered** pair, not a symmetric one: the callback only works in that direction.

### `GATE = once_per_save` (B.4 Q6, locked)

**Nine sincere/identity rows are gated to once per entity per save, at their existing tiers and weights, unchanged:** `idle.33`, `idle.34`, `idle.35`, `idle.38`, `low_health.10`–`.13`, `jump_refused.20`.

**Weight 1 was never a rarity mechanism, and that is the whole argument.** Tiers are cumulative and weights are relative WITHIN the eligible set, so tagging a row `quiet` SHRINKS the pool it competes in — which means a `quiet`-tagged weight-1 row is roughly **3.6x MORE likely to fire for the player who asked for the least Jamal than for the player who asked for the most.** The arithmetic is under `idle`. Weight 1 was not rare, it was just quiet, and no tier or weight can fix an inversion that tiers and weights created.

A hard gate can. **`once_per_save` makes the identity material land as a MOMENT instead of a rotation** — the one thing it has to do, because it is the only place in two books where he stops being funny. D.5 stores the fired-set per entity in `storage`, in the same record as `{N}`, so the mechanism costs nothing it was not already paying for.

---

## built

**key:** `built`
**split:** none
**fires:** entity created — placed by a player, built by a bot, or revived from a ghost. Once, on creation.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| built.01 | Jamal has eight hoppers again, Mr. Engineer! | speech | original | - | 8 | quiet | - | - | built.01 | *hoppers* is HIS word for the legs (bk 7). The natural item-description word too |
| built.02 | Jamal is very excited about this | speech | verbatim | 7 | 7 | quiet | - | - | built.02 | bouncing on a fresh set of legs. Trailing comma dropped (still a prefix substring) |
| built.03 | It is a very robust excitement that he has. | speech | verbatim | 7 | 6 | normal | - | - | built.03 | the same emotion restated in third person — quantified affect, his signature |
| built.04 | Jamal will only flame on purpose from now on. | speech | verbatim | 7 | 6 | quiet | - | - | built.04 | the promise. He breaks it within pages |
| built.05 | Jamal is quite excited to battle with his new upgrades | speech | verbatim | 7 | 5 | normal | - | - | built.05 | first deployment on new legs + weapon. Trailing comma dropped |
| built.06 | Top quality, they told Jamal. We shall see. | speech | original | - | 5 | normal | - | - | built.06 | plants the running gag at t=0 so every later break can call back to it |
| built.07 | Rest assured, Mr. Engineer. | speech | adapted | 7 | 4 | normal | - | - | built.07 | the reassurance formula. Addressee swapped, honorific spelling is the source's. ORIGINAL: "Rest assured, Mr. Carl." |
| built.08 | Jamal was testing his legs. | speech | verbatim | 8 | 4 | normal | - | - | built.08 | the unasked-for experiment, announced flatly after the fact |
| built.09 | It is quite primed and ready | speech | verbatim | 8 | 4 | normal | - | - | built.09 | TRIMMED (prefix) of "It is quite primed and ready to cause much melty inconvenience to any nasty cars who attempt to get to the finish line before us." (129 ch) |
| built.10 | Jamal is assembled and quite ready for commissions. | speech | original | - | 4 | normal | - | - | built.10 | *commission* is his register for a job order — duty restatement, bk 8 |
| built.11 | Oh yes, Mr. Engineer. | speech | adapted | 8 | 3 | normal | - | - | built.11 | the eager affirmative, asked whether his weapon works. Addressee swapped. ORIGINAL: "Oh yes, Mr. Carl." |
| built.12 | Any previous flamings were purely accidental | speech | verbatim | 7 | 3 | unbearable | - | - | built.12 | TRIMMED (prefix) of "Any previous flamings were purely accidental and such a thing will never repeat." (80 ch). *flamings* as a countable noun is his |
| built.13 | the new and improved sticky feets Jamal has | speech | verbatim | 8 | 3 | unbearable | - | - | built.13 | TRIMMED (inner clause) of "Jamal wished to see if he could walk upside down on the ceiling with the new and improved sticky feets Jamal has" (112 ch). *sticky feets* is a double plural and it stays |
| built.14 | Jamal would like to hop. Later. Mayhaps. | speech | original | - | 3 | unbearable | - | - | built.14 | states the drive on turn one. *Mayhaps* is his (bk 7, single-hit — seasoning, not backbone) |

## enter/exit

**key:** `enter` and `exit` — ONE section because PLAN B.3 names the event that way, TWO pools because the mod fires them separately.
**split:** required — `enter` | `exit`. The mod always knows which of the two fired, so it always knows which subpool to roll. Never pick across them.
**fires:** `on_player_driving_changed_state`. `enter` when a driver mounts, `exit` when they dismount.

**Thin in both books — nobody ever rides him**, so most of this is written fresh. The closest canonical analogue to being mounted is being SUMMONED (he hops off whatever wall he was parked on, delighted), and the analogue to being dismounted is being BENCHED — his flat *What?*, then negotiation, then staying put and sulking.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| enter.01 | Oh boy, Jamal is quite excited | speech | verbatim | 8 | 8 | quiet | enter | - | enter.01 | summoned by someone he likes; hops off the wall he was parked on. Trailing comma dropped |
| enter.02 | Jamal is here! | speech | verbatim | 7 | 7 | quiet | enter | - | enter.02 | the four-word status-readout shape, announced mid-battle with no legs at all |
| enter.03 | Mr. Engineer is aboard! Jamal is most honored. | speech | original | - | 6 | quiet | enter | - | enter.03 | he is delighted to be used as equipment (bk 8 — people ride his head) |
| enter.04 | Where shall Jamal take you, Mr. Engineer? | speech | original | - | 5 | normal | enter | - | enter.04 | permission-seeking register; he negotiates rather than obeys |
| enter.05 | This is quite exciting | speech | verbatim | 7 | 5 | normal | enter | - | enter.05 | given a dangerous solo assignment. Trailing comma dropped |
| enter.06 | My goodness, Mr. Engineer. | speech | adapted | 8 | 4 | quiet | enter | - | enter.06 | his stock exclamation with the honorific welded on. Addressee swapped. ORIGINAL: "My goodness, Mr. Carl." |
| enter.07 | Jamal has been waiting. Jamal is very good at waiting. | speech | original | - | 4 | unbearable | enter | - | enter.07 | repetition-with-variation is his emphasis mechanism |
| enter.08 | Mind the head, Mr. Engineer. It is quite wide. | speech | original | - | 3 | unbearable | enter | - | enter.08 | hammerhead, stated as a courteous technical finding |
| exit.01 | Jamal will hold this position, Mr. Engineer. | speech | original | - | 7 | quiet | exit | - | exit.01 | duty restatement — he receives every parking as a solemn commission |
| exit.02 | Jamal will keep them safe. | speech | verbatim | 7 | 6 | quiet | exit | - | exit.02 | accepting a guard order |
| exit.03 | What? | speech | verbatim | 7 | 5 | quiet | exit | - | exit.03 | his ENTIRE response to being told he is staying behind |
| exit.04 | Jamal will wait here. Jamal always waits here. | speech | original | - | 5 | quiet | exit | - | exit.04 | *everyone parks Jamal* is a bk 8 running gag and basically the mod's idle state |
| exit.05 | I would very much like to stay outside for the moment. | speech | verbatim | 7 | 4 | normal | exit | - | exit.05 | polite refusal of an order given for his own safety |
| exit.06 | Oh, are the others coming back? | speech | verbatim | 7 | 4 | unbearable | exit | - | exit.06 | asking a question nobody wants to answer honestly |
| exit.07 | Mayhaps you will return soon? | speech | original | - | 4 | unbearable | exit | - | exit.07 | permission-seeking; never defiant, never resentful |
| exit.08 | Jamal will not hop while you are gone, Mr. Engineer. | speech | original | - | 3 | unbearable | exit | - | exit.08 | he is unteachable by consequence and the mod should say so early. **The undercutting tag (*Probably.*) went at the voice audit:** the promise he cannot keep is funnier delivered straight, because then the audience gets the joke over his head instead of with him — the same test `jump.13` passes and cut `jump.14` failed. `built.04` is the verbatim shape |

## moving

**key:** `moving`
**split:** none
**fires:** driving state changes to moving, or the autopilot/remote picks up a destination. Heavily throttled — this pool can fire constantly, so cooldown does the work, not the weights.

**Thinnest pool in the character.** He is richly DESCRIBED in motion in both books (legs whir, feet click-clack and clank on hard floors, he keeps pace with motorcycles over ten miles) and he almost never narrates it himself. Written mostly fresh on the `Jamal is <state>` backbone, which is the shape that generates faithful lines indefinitely. **Being richly described is why this pool has TWO narration rows** — `moving.03` (the footfalls) and `moving.11` (the whir), both of them the book's outside-in description words, the second one caught at the voice audit after the first had already been moved.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| moving.01 | Jamal is walking. Jamal is quite good at walking. | speech | original | - | 8 | quiet | - | - | moving.01 | the backbone shape plus his repetition tic. *quite* is the one-word voice marker |
| moving.02 | Oh yes, this excitement level I have is something else. | speech | verbatim | 7 | 6 | quiet | - | - | moving.02 | bouncing around hard enough that bystanders dodge |
| moving.03 | Clack, clack, clack go Jamal's feet. | narration | original | - | 6 | normal | - | - | moving.03 | **NARRATION.** Both books describe the footfalls in exactly these words — the onomatopoeia is the book's narrator looking at him from outside, which is the whole reason it never worked in his mouth. He was built to be QUIET and audibly is not |
| moving.04 | This is quite exciting | speech | verbatim | 7 | 6 | normal | - | - | enter.05 | trailing comma dropped |
| moving.05 | The legs are told where to go, and they go. | speech | original | - | 5 | quiet | - | - | moving.05 | **voice control is canon** (bk 7) — he calls out to the legs. This is also why they obey a stupid order |
| moving.06 | Jamal is keeping pace, Mr. Engineer! | speech | original | - | 5 | normal | - | - | moving.06 | he keeps up with motor vehicles over ten miles. Do NOT nerf his speed below stock spidertron |
| moving.07 | Jamal is most certainly ready to drive! | speech | verbatim | 8 | 5 | quiet | - | - | moving.07 | volunteering for something he physically cannot do |
| moving.08 | I must admit, it is giving me untold levels of energy. | speech | verbatim | 7 | 4 | normal | - | - | moving.08 | quantified affect; person mixes mid-utterance and that is correct |
| moving.09 | Jamal could go faster if Jamal were allowed to hop. | speech | original | - | 4 | normal | - | - | moving.09 | every conversation routes back to the hopping grievance (bk 7 running gag) |
| moving.10 | I will attempt driving with my legs. | speech | verbatim | 8 | 3 | normal | - | - | moving.10 | TRIMMED (suffix) of "I would wish for someone to turn Jamal around, and I will attempt driving with my legs." (87 ch) |
| moving.11 | Jamal's legs are whirring most robustly. | narration | original | - | 4 | unbearable | - | - | moving.11 | **NARRATION, a channel move the voice audit caught that B.4 missed.** *whir* is the book's narration word for the legs running — not his — and it was sitting in the very pool `moving.03` was re-channeled out of for the same diagnosis. The intensifier is his, which is why it reads as the narrator's caption rather than a bulletin |
| moving.12 | Is this far enough? Jamal can go farther. | speech | original | - | 3 | unbearable | - | - | moving.12 | compulsively useful, never asks why, always offers more |
| moving.13 | Maybe my mouth. | speech | verbatim | 8 | 2 | unbearable | - | - | moving.13 | he proposes his own mouth as a backup vehicle control surface. Non sequitur on purpose |

## idle

**key:** `idle`
**split:** none — `SUB = sincere` is an ADVISORY tag, not a subpool. Those rows sit in the ordinary `idle` roll
**fires:** idle timer while nobody is driving and nothing is happening. The largest pool by a distance and the one a player hears most, so it carries the widest register spread.

The profile's most over-anchored event. Note the deliberate inclusion of lines from the sincere monologue at weight 1–2: **the identity material is where he stops being funny, so it is spent rarely and never on a timer alone.** B.4 ruled that it ships, with a `GATE = once_per_save` on each of those rows rather than a trust in weight.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| idle.01 | This is a most unexpected development | speech | verbatim | 7 | 3 | normal | - | - | idle.01 | deadpan-at-atrocity: an entire army is mind-controlled and frozen. **Anti-repeat exception A** — see idle.02. Trailing comma dropped |
| idle.02 | A most unexpected development indeed | speech | verbatim | 7 | 2 | normal | - | - | idle.02 | **Anti-repeat exception B.** The same line again, later, with *indeed* bolted on. He is the only character who quotes himself — the picker should be ALLOWED to fire this right after idle.01 |
| idle.03 | Jamal is idle. Jamal is quite good at idle. | speech | original | - | 6 | quiet | - | - | idle.03 | backbone shape + the repetition tic; literal-minded optimism about doing nothing |
| idle.04 | Jamal will stand in the shade. | speech | verbatim | 7 | 5 | normal | - | - | idle.04 | reporting a trivial intention nobody asked about. Heat bothers him |
| idle.05 | It is getting quite toasty indeed. | speech | verbatim | 7 | 5 | quiet | - | - | idle.05 | *toasty* is a genuine cross-book coinage root; *indeed* is his stock closer |
| idle.06 | Did you know I used to be an apex predator? | speech | verbatim | 7 | 5 | quiet | - | - | idle.06 | opening the lost-glory argument. He volunteers his résumé unprompted |
| idle.07 | And after that, I was a terror who could fly? | speech | verbatim | 7 | 4 | normal | - | - | idle.07 | escalating it — he used to FLY, which is why he wants to hop |
| idle.08 | Do you know how many clowns I have consumed? | speech | verbatim | 7 | 4 | normal | - | - | idle.08 | credentials measured in prey. Genuinely dangerous, stated as small talk |
| idle.09 | How many lemurs? | speech | verbatim | 7 | 3 | unbearable | - | - | idle.09 | the follow-up beat. Pairs with idle.08 |
| idle.10 | It’s a great yearning Jamal has. | speech | verbatim | 7 | 5 | normal | - | - | idle.10 | third-person summary of his own desire |
| idle.11 | Jamal is not doing anything. Jamal could hop. | speech | original | - | 5 | normal | - | - | idle.11 | the hopping grievance, routed in from nothing at all |
| idle.12 | Oh. Please excuse Jamal and Velma. | speech | verbatim | 7 | 4 | quiet | - | - | idle.12 | after the flamethrower goes off by itself. **Velma is the flamethrower's proper name** (bk 7). Pairs with the canonical idle flame-leak effect |
| idle.13 | I was once one of the most feared warriors of all the seas. | speech | verbatim | 7 | 4 | quiet | - | - | idle.13 | defending his dignity, unprompted, to nobody |
| idle.14 | There is nothing to guard, so Jamal guards nothing. | speech | original | - | 4 | normal | - | - | idle.14 | *everyone parks Jamal* received as a solemn commission |
| idle.15 | jumping is what Jamal... I mean it is what I wish to do. | speech | verbatim | 7 | 3 | quiet | - | - | idle.15 | TRIMMED (suffix) of "I tell you, jumping is what Jamal... I mean it is what I wish to do." (68 ch). **The third-person slip caught mid-sentence — keep the ellipsis, it IS the tic.** 56 ch, so it fits in one bubble after all (B.4 Q8, the cap deferral — the citation said Q9 until the voice audit checked it) |
| idle.16 | It is my yearning that makes me forget myself, you see. | speech | verbatim | 7 | 3 | normal | - | - | idle.16 | excusing the verbal tic, not any damage. Best paired after idle.15 |
| idle.17 | Sometimes Jamal is very much happy he can no longer smell. | speech | verbatim | 7 | 3 | normal | - | - | idle.17 | cheerfully grateful for a disability. Deadpan observer register |
| idle.18 | I suspect it’s quite unpleasant. | speech | verbatim | 7 | 3 | unbearable | - | - | idle.18 | understatement at an ally-wide vomiting event |
| idle.19 | Quite unpleasant indeed. | speech | verbatim | 7 | 3 | unbearable | - | - | idle.19 | doubled, his emphasis mechanism |
| idle.20 | Jamal’s sense of smell was once greatly enhanced | speech | verbatim | 7 | 3 | normal | - | - | idle.20 | TRIMMED (prefix) of "Jamal’s sense of smell was once greatly enhanced, but that sense of smell is not working at all anymore." (104 ch) |
| idle.21 | Not even one little bit. | speech | verbatim | 7 | 2 | unbearable | - | - | idle.21 | the emphasis beat after naming a loss |
| idle.22 | It is quite thoroughly gone... Just like his ability to hop. | speech | verbatim | 7 | 3 | normal | - | - | idle.22 | 60 ch exactly. **Steering ANY topic back to the hopping grievance** — the most portable gag he has |
| idle.23 | We have been tasked with— | speech | verbatim | 8 | 3 | normal | - | - | idle.23 | cut off mid-sentence by a pet shoving past him. **A line that ends in an em-dash is a legitimate one-shot bubble gag** |
| idle.26 | How far can you hop with those feet? | speech | verbatim | 8 | 3 | normal | - | - | idle.26 | sincerely curious about a person's hopping range. Guileless |
| idle.27 | It appears you have fallen. | speech | verbatim | 8 | 2 | normal | - | - | idle.27 | announcing the obvious with mild astonishment to a man flat on the floor |
| idle.28 | I would very much like to see a goddess | speech | verbatim | 7 | 2 | normal | - | - | idle.28 | TRIMMED (prefix) of "I would very much like to see a goddess like Eileithyia." (56 ch) — the name was the only book-bound word. *A goddess* needs no more setting than *apex predator* or *the seas* do (idle.06, idle.13). Star-struck gossip, mid-campaign |
| idle.29 | I have heard she is quite beautiful. | speech | verbatim | 7 | 2 | unbearable | - | - | idle.29 | the gossip register. Sincere, not leering |
| idle.30 | Jamal is much too quick-witted for such tricks. | speech | verbatim | 7 | 2 | unbearable | - | - | idle.30 | self-assessment. He falls for it immediately |
| idle.31 | Mr. Engineer? Jamal has a thought about hopping. | speech | original | - | 4 | unbearable | - | - | idle.31 | socially undeterred — he keeps talking and keeps looking for someone to talk to |
| idle.32 | Jamal's excitement is leaking out of Velma again. | speech | original | - | 3 | unbearable | - | - | idle.32 | **little tendrils of flame leak out when he is excited (bk 7)** — canonical idle particle effect, and this line is its caption |
| idle.33 | he wishes he could just go back to the ocean. | speech | verbatim | 8 | 1 | quiet | sincere | once_per_save | idle.33 | TRIMMED (suffix) of "Jamal is happy to have his legs, but he wishes he could just go back to the ocean." (82 ch). Opening of the one sincere monologue. **The trim was INVERTED and got fixed at the voice audit:** it used to ship the contentment half, which says nothing `repaired.01` does not already say, and spent the save's one gated emotional moment saying it. The yearning is the beat |
| idle.34 | I am so scared of what I might lose. | speech | verbatim | 8 | 1 | quiet | sincere | once_per_save | idle.34 | TRIMMED (suffix) of "I want to be Jamal, but now I am up here and I can see it all, I am so scared of what I might lose." (99 ch). **Re-trimmed at the voice audit.** The old trim (*he could see everything all at once.*) kept the vantage point and dropped the cost, and the cost is the point — profile register 5: sustained first person, short clause, no scaffolding, no honorific. The trigger table names the two beats this pool owes, *the ocean* and *a fear of losing everything*; `idle.33` is the first and this is the second |
| idle.35 | He was so brave, but he was not me. | speech | verbatim | 8 | 1 | quiet | sincere | once_per_save | idle.35 | **The identity line, and the only un-funny thing he says in two books.** Spend once or not at all — B.4 rules |
| idle.36 | I have, I mean. | speech | verbatim | 7 | 2 | normal | - | - | idle.36 | **catching and correcting his own third-person slip.** Its partner is `idle.10` — in the book this sentence lands directly on *It’s a great yearning Jamal has.* and corrects the *Jamal* in it. (The note said `idle.15` until the voice audit checked the extract; `idle.15` is a DIFFERENT slip and it carries its own correction inside one bubble, which is why that row ships alone and this one cannot.) **This row only parses after its partner and the mod has no mechanism to deliver one — line chaining is answered by NO B.4 ruling** (the old citation pointed at Q9, which is the `{N}` ruling). Nine rows share the problem; OPEN for chotchki, and nothing here invents a mechanism |
| idle.37 | Oh, what a wish. | speech | verbatim | 7 | 3 | unbearable | - | - | idle.37 | wistful closer |
| idle.38 | Jamal used to do before when he was... when he was real. | speech | verbatim | 8 | 1 | quiet | sincere | once_per_save | idle.38 | TRIMMED (suffix) of "It’s what Jamal used to do before when he was... when he was real." (66 ch). **The slip in the sincere register — uncorrected, and he never comes back from it.** Keep the ellipsis. **Re-trimmed at the voice audit:** the old trim was a bare subordinate clause, 56 ch buys back the subject and he is in it by NAME, which is the tic the slip is measured against |

`SUB = sincere` on `idle.33`–`.35` and `idle.38` is advisory, not a separate pool: they sit in the same `idle` roll at weight 1. **What actually makes them rare is `GATE = once_per_save`, added at B.4, because weight 1 did the OPPOSITE of rare.** Tiers are cumulative and weights are relative WITHIN the eligible set, so tagging a row `quiet` shrinks the pool it competes in. The pool sums to 112 weight (quiet 31 + normal 56 + unbearable 25), so these four are 4 of 31 weight at `quiet` (**12.9%** of idle rolls) against 4 of 112 at `unbearable` (**3.6%**) — **the player who asked for the least Jamal was 3.6 times more likely to get the sad identity material than the player who asked for the most.** (Both figures moved at the voice audit, which recomputed them: the total was stated as 119 when the pool summed to 117, and the two `idle` cuts took it to 112.) Same inversion, smaller, on `low_health.10`–`.13` and `jump_refused.20`, and all nine now carry the gate. Weight could not fix this and neither could a tier; **the arithmetic is why B.4 Q6 was a mechanic question rather than a taste question.**

## attacking

**key:** `attacking`
**split:** gated on `friendly` — those rows are eligible ONLY when the mod has confirmed friendly-fire damage; when it has, they join the ordinary roll. Never a separate pick
**fires:** the gun starts shooting, throttled hard so a sustained fight does not turn into a monologue.

Note the deliberate weight on `attacking.03`, the narration row: **book 7 gives him a berserker feeding-frenzy state in which the manners switch off ENTIRELY** — no speech at all, just crunching, whooping and barrel rolls. A wordless attack is more faithful than any line, some of the time, and narration is how the mod says so out loud.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| attacking.01 | Jamal is firing his flamethrower! | speech | verbatim | 7 | 9 | quiet | - | - | attacking.01 | narrating the attack he is currently performing. **Self-narration as a status readout is the mod's single biggest win** |
| attacking.02 | There are big ones coming! | speech | verbatim | 7 | 6 | quiet | - | - | attacking.02 | escalation warning in nursery vocabulary |
| attacking.03 | Jamal has stopped apologizing. Jamal is feeding. | narration | original | - | 6 | quiet | - | - | attacking.03 | **NARRATION, the former `[SILENCE]` row.** Book 7's berserker feeding frenzy switches the manners off ENTIRELY — no speech, just crunching, whooping and barrel rolls. The narrator says the thing a bubble cannot: the politeness stopped. **CARRIES A SILENCE WINDOW (see the header): the rest of the current combat burst is wordless**, or the next `attacking` roll falsifies this row inside one throttle interval |
| attacking.04 | Some of the doggies are different than others! | speech | verbatim | 7 | 5 | quiet | - | - | attacking.04 | threat report. *doggies* is his word for lethal military automatons — it lands perfectly on biter variants |
| attacking.05 | a taste of my toasty emissions. | speech | verbatim | 8 | 5 | normal | - | - | attacking.05 | TRIMMED (suffix) of "They do not like it when they get a taste of my toasty emissions." (65 ch) |
| attacking.06 | Velma is quite primed, Mr. Engineer! | speech | original | - | 5 | normal | - | - | attacking.06 | Velma = the flamethrower, named in bk 7 |
| attacking.07 | ready to cause much melty inconvenience | speech | verbatim | 8 | 4 | normal | - | - | attacking.07 | TRIMMED (inner clause) of the 129 ch weapon-status line. *melty inconvenience* is his coinage |
| attacking.08 | Jamal is applying toasty disrespect! | speech | original | - | 4 | normal | - | - | attacking.08 | recombination of his own compounds — *toasty disrespect* (bk 7) put in a new sentence, so ORIGINAL, not verbatim |
| attacking.09 | Do you know how many clowns I have consumed? | speech | verbatim | 7 | 3 | normal | - | - | idle.08 | credentials, mid-fight, at nobody |
| attacking.10 | Jamal has consumed worse than this. | speech | original | - | 3 | normal | - | - | attacking.10 | apex-predator résumé, deadpan |
| attacking.11 | My goodness, what a bungle Jamal has made! | speech | verbatim | 7 | 2 | normal | friendly | - | attacking.11 | immediately after nearly setting an ally on fire. **Gate on actual friendly-fire damage if D.5 can detect it** |
| attacking.12 | My apologies to you and your family | speech | verbatim | 7 | 2 | unbearable | friendly | - | attacking.12 | TRIMMED (prefix) of "My apologies to you and your family for any unintended, toasty disrespect." (74 ch). The apology extends to the victim's RELATIVES |
| attacking.13 | Any previous flamings were purely accidental | speech | verbatim | 7 | 2 | unbearable | friendly | - | built.12 | TRIMMED (prefix), full quote at built.12 |
| attacking.14 | Maybe my mouth. | speech | verbatim | 8 | 3 | unbearable | - | - | moving.13 | he kills things with his mouth in both books, so this is not the non sequitur it looks like |

`SUB = friendly` rows should only be eligible when the mod knows he hit something on his own force. If D.5 cannot detect that cheaply, drop the three rows rather than firing them blind — an unprompted apology for damage that did not happen is the one way this pool reads as broken rather than annoying. **Still open, deliberately: B.4 Q11 defers to what the API turns out to provide at D.5/D.7.**

**`attacking.15` was CUT at B.4** (*They will not enjoy Jamal's emissions.*): a flat paraphrase of verbatim `attacking.05` sitting in the same pool, minus *toasty*, which is the entire coinage. Tail of the pool, so no renumber.

## damaged

**key:** `damaged`
**split:** none
**fires:** `on_entity_damaged`, throttled to at most one line every N seconds regardless of how much is chewing on him.

**Damage is a NOISE in both books, not a sentence** — hit by a flung mob or a child's spear he YELPS, hit by a thrown wrench he lets out a small wordless shout. Neither book gives him a body complaint at all, only leg complaints. So the verbal slot is spent on leg-quality griping and protest, not on pain, and the noise itself goes to `damaged.02` in the narration channel where it can actually be rendered.

**Two B.4 cuts landed here.** `damaged.08`'s leading *Ow.* is gone (a spelled-out yelp fights the pool's own premise; the protest that followed it survives), and the old `damaged.08` *Jamal did not care for that.* was DROPPED outright rather than rewritten — deadpan understatement is register 4, which fires at catastrophe happening to OTHER people, and everything the row was reaching for is already carried in-register by `damaged.03` (protest), `damaged.09` (hardware denial) and `damaged.10` (lament). The pool was renumbered: old `.09`–`.16` are now `.08`–`.15`.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| damaged.01 | Oh my goodness. | speech | verbatim | 7 | 8 | quiet | - | - | damaged.01 | his stock exclamation, clean full sentence, 15 ch. The workhorse of this pool |
| damaged.02 | Jamal makes a noise that is not a word. | narration | original | - | 7 | quiet | - | - | damaged.02 | **NARRATION, the former `[SILENCE]` row.** Damage is a NOISE in both books and never a sentence — a yelp, a small wordless shout. Narration can render that; a speech bubble is structurally unable to, which is the entire reason this row exists |
| damaged.03 | Jamal must protest! | speech | verbatim | 7 | 6 | quiet | - | - | damaged.03 | formal protest, used when wronged. Courtroom-flavored, two words and a verb |
| damaged.04 | Jamal is dented, Mr. Engineer. | speech | original | - | 6 | normal | - | - | damaged.04 | backbone `Jamal is <state>` shape as a status readout |
| damaged.05 | Oh, goodness, | speech | verbatim | 7 | 5 | normal | - | - | damaged.05 | trailing comma is the book's (a dialogue tag follows). B.5 MAY strip it — the prefix is still an exact substring — but must never swap in a different mark |
| damaged.06 | And I was led to believe they were top quality. | speech | verbatim | 7 | 5 | quiet | - | - | damaged.06 | the quality complaint. Fires here because his body complaints are always LEG complaints |
| damaged.07 | Top quality! | speech | verbatim | 7 | 5 | normal | - | - | damaged.07 | repeated as its own sentence, bitterly |
| damaged.08 | That is quite unkind. | speech | original | - | 5 | normal | - | - | damaged.08 | B.4 CUT the leading *Ow.* and kept the protest. This pool's premise is that damage is a wordless NOISE — which is why `damaged.02` is the narration row — and a spelled-out yelp fights that premise in the same pool |
| damaged.09 | Nothing is wrong. | speech | verbatim | 8 | 4 | quiet | - | - | damaged.09 | **defending the hardware against the suggestion that it failed.** Said while visibly on fire, it is the best joke in the pool |
| damaged.10 | Such woe! | speech | verbatim | 7 | 4 | normal | - | - | damaged.10 | pure content-free lament, repeatable forever |
| damaged.11 | Jamal is fine. The legs are fine. Everything is fine. | speech | original | - | 4 | normal | - | - | damaged.11 | he would rather confess cowardice than let anyone conclude his hardware failed |
| damaged.12 | Jamal's paint was not top quality either. | speech | original | - | 4 | normal | - | - | damaged.12 | the running gag, escalated to cosmetics |
| damaged.13 | This is a most unexpected development | speech | verbatim | 7 | 3 | normal | - | - | idle.01 | deadpan, trailing comma dropped |
| damaged.14 | That is twice now. Jamal is counting. | speech | original | - | 3 | unbearable | - | - | damaged.14 | he counts hardware out loud. Uses the same counter as `{N}` if D.5 wants it |
| damaged.15 | Jamal will endure, Mr. Engineer. Jamal always endures. | speech | original | - | 3 | unbearable | - | - | damaged.15 | bother-aversion past the point of self-harm — he stayed silent on a ceiling for hours rather than inconvenience anyone. **REWRITTEN at the voice audit:** *Please continue, Mr. Engineer.* addressed the endurance to the engineer, which in a pool that fires on biter damage made the player the one doing the chewing. Repetition with a one-word variation is his emphasis mechanism and it carries the same beat without naming a culprit |

## low health

**key:** `low_health`
**split:** none — `SUB = sincere` is advisory, see `idle`
**fires:** health ratio crosses a threshold downward (suggest 0.35 and again at 0.15, one line each, not a repeating timer).

**The highest-weight member of this pool is the silence row, and that is the whole point.** Neither book gives him a complaint about his BODY — he complains about legs, never about himself — and in both books his going quiet is how the narration signals real trouble. **A critically-damaged jamaltron that stops talking is more faithful than anything we could write**, so `low_health.01` stays the heaviest row in the file — at weight 12 of the 29 eligible at `quiet` it is **41% of the quiet-tier roll**, which is the number that makes the window below non-negotiable — now as narration that NAMES the silence instead of an absence the player has to infer, and, since the voice audit, one that BUYS the silence it names: 15 s of no speech on that entity (the header carries the requirement).

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| low_health.01 | Jamal has gone quiet. That is never a good sign. | narration | original | - | 12 | quiet | - | - | low_health.01 | **NARRATION, the former `[SILENCE]` row, and still deliberately the heaviest row in the file.** Both books use his going quiet as the distress signal and both narrations flag it as the anomaly — so the narrator flags it here too, which beats emitting nothing and hoping the player reads the absence. **CARRIES A SILENCE WINDOW (see the header): 15 s of no speech on this entity.** The profile's version of this is a SUSTAINED absence; without the window the `damaged` pool answers it within a tick and the heaviest row in the file becomes a shrug |
| low_health.02 | Jamal is feeling woozy. | speech | verbatim | 8 | 9 | quiet | - | - | low_health.02 | status readout, third person. Reports affect the way a UI reports a meter — which is literally what this event is |
| low_health.03 | Mister Engineer, I do fear I require assistance. | speech | adapted | 7 | 6 | quiet | - | - | low_health.03 | over-built courtesy scaffolding around the plain word *help*, delivered face-down. Addressee swapped, *Mister* spelling is the source's. ORIGINAL: "Mister Carl, I do fear I require assistance." |
| low_health.04 | Jamal would get smushed. | speech | verbatim | 7 | 5 | normal | - | - | low_health.04 | TRIMMED (suffix) of "And if you and Donut both die, that saferoom will go away, and Jamal would get smushed." (87 ch). He explains his own expected death CHEERFULLY, which is worse |
| low_health.05 | Jamal is not feeling top quality, Mr. Engineer. | speech | original | - | 5 | normal | - | - | low_health.05 | maps the body complaint onto the leg-quality gag, which is the only complaint register he has |
| low_health.06 | There are big ones coming! | speech | verbatim | 7 | 4 | normal | - | - | attacking.02 | he reports the THREAT, not the injury |
| low_health.07 | Jamal requires assistance. Jamal is asking properly. | speech | original | - | 4 | normal | - | - | low_health.07 | the bk 8 resolution: he was told outright not to be scared to say when he is in trouble |
| low_health.08 | I have a great amount of shame and regret. | speech | verbatim | 7 | 3 | normal | - | - | low_health.08 | self-reported emotional status line |
| low_health.09 | Jamal will keep walking. Jamal is quite sturdy. | speech | original | - | 3 | unbearable | - | - | low_health.09 | he does not believe he is entitled to be a problem |
| low_health.10 | I know that, but I want to be brave. | speech | verbatim | 8 | 2 | quiet | sincere | once_per_save | low_health.10 | uncorrected first person, no honorific, no scaffolding. **Deep tier — B.4 rules whether it ships** |
| low_health.11 | Everything will just stop. | speech | verbatim | 8 | 2 | normal | sincere | once_per_save | low_health.11 | the annihilation fact, plainly. Six words, no honorific — inverted escalation at its floor |
| low_health.12 | if you die, we die. | speech | verbatim | 8 | 2 | normal | sincere | once_per_save | low_health.12 | TRIMMED (suffix) of "Miss Hedy says if you die, we die." (34 ch) — the name was the only book-bound word in it, and the trim leaves the fact that actually terrified him. Sits with low_health.11 and .13, its own neighbours in the monologue. **Still verbatim, because a trim beats an adaptation whenever one is available** |
| low_health.13 | We won’t even know. | speech | verbatim | 8 | 2 | unbearable | sincere | once_per_save | low_health.13 |  |

## jump

**key:** `jump`
**split:** none — `SUB = meta` is an ADVISORY flag for B.4 (fourth wall), not a subpool
**fires:** the jump input is accepted and the arc starts (PLAN E.2). Once per jump, at takeoff.

**THE JUMP IS THE JOKE** (SPEC.md): Jamal is the literal personification of jumping the shark, so this pool knows it is a meta-joke. **B.4 ruled on the fourth wall and split the two rows.** `jump.13` stays: it is literal-minded about the idiom, which keeps it inside his voice — *he* does not get the joke, which is why the row works. `jump.14` (*Watch Jamal be jumped over!*) was CUT: that one is the mod winking at the audience over his head, and nothing else in the file does that. Tail of the pool, so no renumber. `jump.04` moved to the narration channel rather than being cut — see `CH`.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| jump.01 | Jamal is hopping! | speech | original | - | 9 | quiet | - | - | jump.01 | **ORIGINAL despite looking like a quote** — the backbone `Jamal is <verb>ing` template applied to his own word *hop*. Do not let the shape fool a verifier |
| jump.02 | I wish to hop across the battlefield. | speech | verbatim | 7 | 7 | quiet | - | - | jump.02 | the tactical version of the want |
| jump.03 | I do wish to feel the wind in my gills. | speech | verbatim | 7 | 7 | quiet | - | - | jump.03 | the sincere version. **He breathes air and still has gills** — a land animal that looks like a sea animal |
| jump.04 | Up goes Jamal! | narration | original | - | 7 | normal | - | - | jump.04 | **NARRATION.** The fronted verb makes him the OBJECT of a sportscast, which is wrong for his mouth and exactly right for the game's. Nothing about the line was broken, so weight 7 survives the channel move intact |
| jump.05 | Only a little hop, Mr. Engineer! | speech | original | - | 6 | normal | - | - | jump.05 | he ALWAYS minimizes it — *a little hop* is his own framing, every time |
| jump.06 | It is something Jamal always wished to do. | speech | verbatim | 7 | 5 | normal | - | - | jump.06 | justifying the hop that broke the legs, immediately after apologizing for it |
| jump.07 | Oh, I do. | speech | verbatim | 7 | 4 | normal | - | - | jump.07 | agreeing, too eagerly, that he wants to jump |
| jump.08 | he doesn’t have time to see how high he is | speech | verbatim | 8 | 4 | normal | - | - | jump.08 | TRIMMED (inner clause) of "When Jamal jumps, he doesn’t have time to see how high he is because he always falls down again." (96 ch) |
| jump.09 | Jamal does not look down. Jamal is already falling. | speech | original | - | 4 | normal | - | - | jump.09 | **the courage was never courage, it was insufficient airtime.** Funniest and saddest single fact about him |
| jump.10 | jumping is what Jamal... I mean it is what I wish to do. | speech | verbatim | 7 | 4 | quiet | - | - | idle.15 | TRIMMED, full quote at idle.15. The person-slip, 56 ch |
| jump.11 | Jamal's yearning is quite satisfied! | speech | original | - | 4 | unbearable | - | - | jump.11 | *yearning* is his word for the drive (bk 7) |
| jump.12 | What a wish I have. | speech | verbatim | 7 | 3 | unbearable | - | - | jump.12 | the doubling tic — one-word variation is how he emphasizes |
| jump.13 | Jamal does not know the idiom, but Jamal will hop! | speech | original | - | 2 | unbearable | meta | - | jump.13 | **FOURTH WALL.** Literal-minded enough to stay just inside his voice. B.4 rules |

## land

**key:** `land`
**split:** none
**fires:** the arc resolves and he is back on the ground — BEFORE the leg-break roll, so a successful landing and a broken one both start here.

**On legs he lands WELL**, in both books: real leaps landing *deftly*, a midair ballerina twirl that Donut calls elegant, jump-landings used as an offensive attack. So the airborne pose in C.5 should read deliberate and this pool should read pleased with itself. **He is good at this — the book-7 legs just cannot take it twice.** Note that *deftly* is the NARRATION's word for it and it stays there: `land.03` used to launder it into his own mouth as self-assessment and was replaced at the voice audit.

`land.08` is the pool's one narration row, moved there at B.4 rather than cut.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| land.01 | Jamal has landed. Nothing came apart! | speech | original | - | 8 | quiet | - | - | land.01 | says the quiet part; sets up every break line that follows |
| land.02 | I just did a little hop | speech | verbatim | 7 | 7 | quiet | - | - | land.02 | TRIMMED (prefix) of "I just did a little hop, and then the metal pieces did break again." (67 ch) — the second clause lives at legs_break.04 |
| land.03 | I did feel the wind in my gills! | speech | original | - | 6 | quiet | - | - | land.03 | **REPLACED at the voice audit.** *Quite deftly done, if Jamal says so.* failed three ways at once: no subject at all, so he is out of the subject slot he occupies in every self-narration in two books; *deftly* is the book NARRATION's word for his landings, laundered into self-assessment; and *if Jamal says so* is the modesty-boast idiom, i.e. irony, against a zero-irony profile and against `jump.13`'s own premise that he does not do idioms. `land.09` already does the borrowed-compliment job correctly, so there was nothing left for a rewrite to say. This is the arc's payoff instead — the emphatic *did*, first person for feeling and possession per the profile's person split, and it collects verbatim `jump.03`'s want |
| land.04 | he always falls down again. | speech | verbatim | 8 | 5 | normal | - | - | land.04 | TRIMMED (suffix) of the 96 ch never-time-to-look-down line |
| land.05 | Jamal landed. Jamal is checking his hoppers. | speech | original | - | 5 | normal | - | - | land.05 |  |
| land.06 | The legs held! Top quality after all. | speech | original | - | 5 | quiet | - | - | land.06 | the gag, inverted — this is the ONE time it comes true |
| land.07 | Jamal would like to do that again, Mr. Engineer. | speech | original | - | 5 | unbearable | - | - | land.07 | **incorrigible: he agrees with you, apologizes sincerely, and does it again.** The trait PLAN E is built on |
| land.08 | Jamal has found the ground. It was never far. | narration | original | - | 4 | normal | - | - | land.08 | **NARRATION**, and the bare-noun *Ground!* went with the channel move — a narrator shouting a noun reads as oddly as he did saying it. The second clause is new and it is the narrator's own callback to `jump.09`: **he never gets high enough to look down** |
| land.09 | That was elegant. Jamal was told so once. | speech | original | - | 4 | normal | - | - | land.09 | Donut called his midair twirl elegant and he clearly kept it |
| land.10 | Jamal's landing was only slightly a blunder. | speech | original | - | 3 | unbearable | - | - | land.10 | *blunder* is one of his two nouns for a screwup |
| land.11 | Jamal is quite pleased with that landing. | speech | original | - | 4 | normal | - | - | land.11 | quantified affect |

## legs break

**key:** `legs_break`
**split:** required — `self` | `external`. The mod already knows whose fault it was, so it always knows which subpool to roll. **Never pick across them.**
**fires:** the break roll succeeds on landing (PLAN E.4) and he swaps to `jamaltron-beached`. Once, at the moment of the break. The apology timer that follows is `flopping`, not this.

**`SUB = self`** — the player pressed jump, so it is HIS doing. He eats it: exclamation → self-narrated blunder in the third person → apology-as-inventory → a formal request for help → and only THEN the unrepentant defense of hopping. Shame is claimed and never acted on. **No quality complaint on this branch, ever.**

**`SUB = external`** — a biter, a train, a rock, anything the player did not order. He does not apologize at all: formal protest to the whole group, a COUNT of how many sets he has been given, and the top-quality grievance. **The one register break in two books used to sit at the bottom of this fork and B.4 CUT it** (old `legs_break.33`, the triple-*Fuck*): no profanity ships, so the portal page needs no content note. It was the pool tail, so nothing renumbered. **The maximum-misery beat now falls to `legs_break.31`** *This was not Jamal's doing.* — the fork's ONLY remaining `unbearable` row, and the closest thing left to a register break, because the grievance there is finally legitimate. (It shipped as *This was not Jamal's doing. For once.* until the voice audit cut the aside: *for once* is a narrator move that needs a self-awareness of his own track record the profile denies him, and it is ruled narration-only at `died.01`. Six plain words at the bottom of the register is what inverted escalation asks for anyway.) Note where the lament weight actually sits though: higher up the pool at `legs_break.28` / `.29` (*Such woe!* / *Such woe I have!*), which is where a player will mostly hear the misery.

The fork matters more than any individual line. Book 7 hands us both branches explicitly; book 8 only ever shows the his-fault branch, which is exactly why it shows no complaint. **When fault is ambiguous, default to `self` and defend the hardware** — he would rather confess cowardice than let anyone conclude his legs failed.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| legs_break.01 | It appears Jamal has made another blunder. | speech | verbatim | 7 | 9 | quiet | self | - | legs_break.01 | announcing his own leg failure, third-person and PASSIVE, as though reading someone else's bulletin. The single best line in the file |
| legs_break.02 | Oh, goodness, | speech | verbatim | 7 | 8 | quiet | self | - | damaged.05 | **the first sound out of him when the legs blow apart**, before he explains anything. Trailing comma is the book's |
| legs_break.03 | Oh my goodness. | speech | verbatim | 7 | 8 | quiet | self | - | damaged.01 | same beat, doubled. Doubling is how he escalates |
| legs_break.04 | and then the metal pieces did break again. | speech | verbatim | 7 | 7 | quiet | self | - | legs_break.04 | TRIMMED (suffix) of "I just did a little hop, and then the metal pieces did break again." (67 ch). **Agentless, no technical noun, and *again*** |
| legs_break.05 | Jamal has so many sorries to give | speech | verbatim | 7 | 7 | quiet | self | - | legs_break.05 | TRIMMED (prefix) of "Jamal has so many sorries to give, and Jamal is giving you all of them." (71 ch). Peak apology-as-inventory |
| legs_break.06 | Mister Engineer, I do fear I require assistance. | speech | adapted | 7 | 7 | quiet | self | - | low_health.03 | the formal rescue request, face-down in the dirt. Addressee swapped. ORIGINAL: "Mister Carl, I do fear I require assistance." |
| legs_break.07 | I don’t see why Jamal shouldn’t be able to hop. | speech | verbatim | 7 | 6 | quiet | self | - | legs_break.07 | **refusing the rule he had just finished proving.** The whole character in one move |
| legs_break.08 | I just did a little hop | speech | verbatim | 7 | 6 | normal | self | - | land.02 | TRIMMED (prefix), full quote at legs_break.04's note |
| legs_break.09 | I must give you an apology | speech | verbatim | 7 | 6 | normal | self | - | legs_break.09 | note the modal — an obligation discharged, not a feeling had |
| legs_break.10 | I have a great amount of shame and regret. | speech | verbatim | 7 | 6 | normal | self | - | low_health.08 | quantified affect applied to remorse |
| legs_break.11 | Jamal's hoppers have come apart, Mr. Engineer. | speech | original | - | 6 | normal | self | - | legs_break.11 |  |
| legs_break.12 | Jamal is giving you all of them. | speech | verbatim | 7 | 5 | normal | self | - | legs_break.12 | TRIMMED (suffix) of the 71 ch sorries line. Pairs after legs_break.05 |
| legs_break.13 | Jamal did only a little hop. Jamal is sorry. | speech | original | - | 5 | normal | self | - | legs_break.13 | minimization plus apology, his standard order |
| legs_break.14 | Jamal is stuck! | speech | verbatim | 8 | 5 | normal | self | - | legs_break.14 | the four-word status readout — the whole news, surrendered only after a direct question |
| legs_break.15 | Still, Mr. Engineer. | speech | adapted | 7 | 4 | normal | self | - | legs_break.15 | **the pivot word.** The apology ends here and the defense of hopping begins. Addressee swapped. ORIGINAL: "Still, Mr. Carl." |
| legs_break.16 | now Jamal has found himself in quite the inverted conundrum. | speech | verbatim | 8 | 4 | normal | self | - | legs_break.16 | 60 ch. The actual emergency, delivered LAST, as a subordinate clause |
| legs_break.17 | That was set {N}. Jamal is sorry about set {N}. | speech | original | - | 4 | normal | self | - | legs_break.17 | uses the break counter. The gag improves every time the number goes up |
| legs_break.18 | The legs come apart. Jamal says nothing at all. | narration | original | - | 3 | normal | self | - | legs_break.18 | **NARRATION, the former `[SILENCE]` row.** Book 8's break is WORDLESS — the event happens and he says nothing at all. Naming the silence keeps the beat legible; emitting nothing just looked like the mod had failed to fire. **CARRIES A SILENCE WINDOW (see the header): D.5 skips the FIRST `flopping` interval.** The apology timer starts one tick after the break, so without the window this row is contradicted before the player finishes reading it |
| legs_break.19 | Nothing is wrong. | speech | verbatim | 8 | 3 | normal | self | - | damaged.09 | defending the hardware while lying in pieces. Absurd on purpose |
| legs_break.20 | The legs are quite strong, Mr. Engineer. Jamal is too heavy. | speech | original | - | 3 | unbearable | self | - | legs_break.20 | **REWRITTEN TWICE — B.4, then again at the voice audit.** The content was right both times: **he corrects the diagnosis and takes the blame himself rather than let anyone conclude the hardware failed** (bk 8). The FORM was not. *The legs did not fail, Mr. Engineer. Jamal did.* is an antithetical epigram with an elliptical punch — structurally the same negate-then-snap as *They are merely apart.*, the row B.4 replaced. The profile's own instantiation of this move names a concrete humiliating cause (*Jamal is afraid of heights.*) and his sentence shape buries the news at the END instead of snapping it, so: defend the hardware, then hand over the humiliating fact last. 60 ch |
| legs_break.21 | Jamal will accept any amount of blame, Mr. Engineer. | speech | original | - | 3 | unbearable | self | - | legs_break.21 | bother-aversion, not manners |
| legs_break.22 | Jamal must protest! | speech | verbatim | 7 | 9 | quiet | external | - | damaged.03 | the not-his-fault fork opens with protest, never with an apology |
| legs_break.23 | And I was led to believe they were top quality. | speech | verbatim | 7 | 8 | quiet | external | - | damaged.06 | **the running gag that never once comes true** |
| legs_break.24 | Top quality! | speech | verbatim | 7 | 7 | quiet | external | - | damaged.07 | spat as its own sentence |
| legs_break.25 | Jamal did NOT hop! Jamal wishes this noted. | speech | original | - | 6 | quiet | external | - | legs_break.25 | the fork, stated out loud so the player can tell which branch fired. **`quiet` because it is the only row that tells the player WHICH branch fired** — that is information, not flavor, and it must survive opting out |
| legs_break.26 | These were the fifth set of legs Jamal has been given! | speech | verbatim | 7 | 5 | normal | external | - | legs_break.26 | keeping count out loud. Ships as-is OR templated — see legs_break.27 |
| legs_break.27 | That was set {N}, Mr. Engineer. Jamal is counting. | speech | original | - | 5 | normal | external | - | legs_break.27 | the templated version of legs_break.26. **ORIGINAL, because substituting the count into a quote fabricates it** |
| legs_break.28 | Such woe! | speech | verbatim | 7 | 5 | normal | external | - | damaged.10 |  |
| legs_break.29 | Such woe I have! | speech | verbatim | 7 | 5 | normal | external | - | legs_break.29 | the possessive-form variant. One-word variation is his emphasis mechanism |
| legs_break.30 | Jamal protests the quality of these hoppers. | speech | original | - | 4 | normal | external | - | legs_break.30 |  |
| legs_break.31 | This was not Jamal's doing. | speech | original | - | 4 | unbearable | external | - | legs_break.31 | the fork's only `unbearable` row and B.4's designated maximum-misery beat after the swear was cut. **The voice audit dropped *For once.* and the sentence is better for it:** the dry aside is a narrator move, it needs causal self-awareness of his own track record that the profile says he does not have, and `died.01`'s Note already rules *for once* narration-only. What is left is five plain words at the bottom of the register, which is exactly what inverted escalation prescribes — the rare serious event gets the short flat ones |
| legs_break.32 | Gentlemen, | speech | verbatim | 7 | 3 | normal | external | - | legs_break.32 | opening an address to the whole party while flopping in misery. **He uses it regardless of who is actually present** |

## flopping

**key:** `flopping`
**split:** none
**fires:** repeating timer while he is `jamaltron-beached` (PLAN E.4), interval scaled by verbosity tier. **The comedic centerpiece of the whole mod** and the only pool designed to be heard dozens of times in a row.

**The punishment is not immobility, it is INDIGNITY.** Freshly wrecked he is slow and pitiful in both books, he complains loudly and continuously while flopping, and he keeps addressing the group as if he were still mid-conversation. The apology spam IS the penalty — so this pool is the biggest in the file and the tier split does real work: at `quiet` he is sympathetic, at `unbearable` he is a war crime. **One row moved channel at the voice audit:** `flopping.23` watches his head-waving from outside, which is the narrator's job and not his — he reports affect as a meter reading, never as observed body language.

**Two B.4 cuts, and the pool was renumbered** (old `.38`–`.41` are now `.37`–`.40`):

- **The swear is gone** (old `flopping.42`, the same string as old `legs_break.33`). Pool tail, so it cost no ids. **The maximum-misery beat now falls to `flopping.38`** *It is not Jamal's intention to add any hair-pulling distress.* — not the heaviest row in the pool (the metronome apologies outweigh it several times over) but the DEEPEST one left: it denies INTENT rather than fault, which prices a baseline of distress from him in and claims only the surplus. Bleaker than the swear, and it was already shipping.
- **The old `flopping.37`** *Jamal is not a burden. Jamal is merely horizontal.* **was DROPPED, not rewritten.** It is the best-written original in the file and the furthest out of register: the wit is the WRITER's, about his condition, and he does not do wit about himself. Everything it was carrying — bother-aversion stated flatly, the thing that keeps the player annoyed rather than resentful — is already carried in register by `flopping.37` (formerly `.38`) *Jamal is sorry to be a bother. Jamal is a bother.*, where the joke is that he agrees with the accusation. **Writing a replacement would have been filler; fewer originals beats flat ones.**

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| flopping.01 | Jamal is sorry, Mr. Engineer. | speech | original | - | 9 | normal | - | - | flopping.01 | the metronome of the pool |
| flopping.02 | Mister Engineer, I do fear I require assistance. | speech | adapted | 7 | 8 | quiet | - | - | low_health.03 | Addressee swapped. ORIGINAL: "Mister Carl, I do fear I require assistance." |
| flopping.03 | Such woe! | speech | verbatim | 7 | 7 | quiet | - | - | damaged.10 | pure content-free misery, repeatable forever. **The best beached idle line in either book** |
| flopping.04 | Jamal is stuck! | speech | verbatim | 8 | 7 | quiet | - | - | legs_break.14 |  |
| flopping.05 | Jamal apologizes. Again. Still. | speech | original | - | 7 | unbearable | - | - | flopping.05 |  |
| flopping.06 | Top quality! | speech | verbatim | 7 | 6 | quiet | - | - | damaged.07 |  |
| flopping.07 | Such woe I have! | speech | verbatim | 7 | 6 | normal | - | - | legs_break.29 |  |
| flopping.08 | I must give you an apology | speech | verbatim | 7 | 6 | normal | - | - | legs_break.09 |  |
| flopping.09 | I have a great amount of shame and regret. | speech | verbatim | 7 | 6 | normal | - | - | low_health.08 |  |
| flopping.10 | I have found more apologies | speech | verbatim | 7 | 6 | normal | - | - | flopping.10 | TRIMMED (prefix) of "I have found more apologies, and now they are yours, Miss Donut." (64 ch). **He runs OUT of apologies and restocks** — the resupply shape |
| flopping.11 | Jamal has so many sorries to give | speech | verbatim | 7 | 6 | normal | - | - | legs_break.05 | TRIMMED, full quote at legs_break.05 |
| flopping.12 | Jamal has more apologies if you would like them. | speech | original | - | 6 | unbearable | - | - | flopping.12 | the inventory metaphor, offered as a transaction |
| flopping.13 | Jamal is flopping. It is quite undignified. | speech | original | - | 6 | normal | - | - | flopping.13 | backbone shape + the actual penalty named |
| flopping.14 | And I was led to believe they were top quality. | speech | verbatim | 7 | 5 | normal | - | - | damaged.06 |  |
| flopping.15 | Jamal has been stuck for quite a bit, I fear. | speech | verbatim | 8 | 5 | normal | - | - | flopping.15 | sentence-final *I fear* is his hedge, and he only ever hedges FACTS |
| flopping.16 | It is with great embarrassment that I admit this. | speech | verbatim | 8 | 5 | normal | - | - | flopping.16 | the confession gets its own sentence of scaffolding before any content arrives |
| flopping.17 | they are much too small for Jamal! | speech | verbatim | 7 | 5 | normal | - | - | flopping.17 | TRIMMED (suffix) of "I have seen the cybernetics in your workshop, and they are much too small for Jamal!" (84 ch). **The parts-are-too-small lament, which is a WOUND, not a shrug** |
| flopping.18 | I don’t see why Jamal shouldn’t be able to hop. | speech | verbatim | 7 | 5 | quiet | - | - | legs_break.07 | still arguing the point, from the ground, with no legs |
| flopping.19 | Mayhaps someone could turn Jamal over? | speech | original | - | 5 | normal | - | - | flopping.19 | permission-seeking: he negotiates, politely, persistently, never defiantly |
| flopping.20 | Jamal's sorries are not yet exhausted. | speech | original | - | 5 | unbearable | - | - | flopping.20 |  |
| flopping.21 | Jamal is giving you all of them. | speech | verbatim | 7 | 5 | unbearable | - | - | legs_break.12 | TRIMMED, full quote at legs_break.05 |
| flopping.22 | It appears Jamal has made another blunder. | speech | verbatim | 7 | 5 | normal | - | - | legs_break.01 |  |
| flopping.23 | Jamal waves his head about most miserably. | narration | original | - | 4 | normal | - | - | flopping.23 | **NARRATION, a channel move the voice audit caught that B.4 missed — the Note already called it a caption, and a caption IS narration.** He waves his whole head back and forth to express misery (bk 8) and the hammerhead shape is the expressive organ, but he reports affect as a METER reading and never as observed body language. Somebody outside him is watching him do this. Caption for the C.5 flop-loop beat |
| flopping.24 | Jamal is feeling woozy. | speech | verbatim | 8 | 4 | normal | - | - | low_health.02 |  |
| flopping.25 | Gentlemen, | speech | verbatim | 7 | 4 | normal | - | - | legs_break.32 | addressing a party that is not there |
| flopping.26 | Jamal must protest! | speech | verbatim | 7 | 4 | normal | - | - | damaged.03 |  |
| flopping.27 | Nothing is wrong. | speech | verbatim | 8 | 4 | quiet | - | - | damaged.09 | said face-down with his legs in pieces. Inverted escalation at full stretch |
| flopping.28 | It is my yearning that makes me forget myself, you see. | speech | verbatim | 7 | 4 | normal | - | - | idle.16 |  |
| flopping.29 | now Jamal has found himself in quite the inverted conundrum. | speech | verbatim | 8 | 4 | normal | - | - | legs_break.16 | 60 ch |
| flopping.30 | Set {N} was not top quality either, Mr. Engineer. | speech | original | - | 4 | normal | - | - | flopping.30 | uses the break counter |
| flopping.31 | Jamal will wait. Jamal is quite good at waiting. | speech | original | - | 4 | normal | - | - | flopping.31 | he waits where he is put, every time, without being asked twice |
| flopping.32 | Jamal is still here, Mr. Engineer. In case you forgot. | speech | original | - | 4 | unbearable | - | - | flopping.32 | protest-at-being-overlooked is a real bk 8 beat — he objects to being left out of a tally |
| flopping.33 | I am piling up my apologies to you, Mr. Engineer, | speech | adapted | 8 | 4 | unbearable | - | - | flopping.33 | the accumulating-pile form, implying a running balance he owes. Addressee swapped, and *Miss* → *Mr.* with it — the player is Mr. Engineer, so this is the one swap that moves the honorific as well as the name. Trailing comma is the book's. ORIGINAL: "I am piling up my apologies to you, Miss Donut," |
| flopping.34 | Jamal is afraid of heights. | speech | verbatim | 8 | 3 | normal | - | - | flopping.34 | **volunteered to clear the hardware of blame.** He takes the humiliation so the legs do not take the accusation |
| flopping.35 | I am quite snug! | speech | verbatim | 8 | 3 | unbearable | - | - | flopping.35 |  |
| flopping.36 | I cannot reach! | speech | verbatim | 8 | 3 | unbearable | - | - | flopping.36 |  |
| flopping.37 | Jamal is sorry to be a bother. Jamal is a bother. | speech | original | - | 3 | quiet | - | - | flopping.37 | the trait the entire apology tic is actually made of |
| flopping.38 | It is not Jamal’s intention to add any hair-pulling distress. | speech | verbatim | 8 | 3 | unbearable | - | - | flopping.38 | **61 ch — one over the soft cap, shipped anyway.** Denies INTENT rather than fault, apologizing only for the surplus distress. Trim to "It is not Jamal’s intention" (27 ch) if the bubble clips |
| flopping.39 | I would very much like to stay outside for the moment. | speech | verbatim | 7 | 2 | unbearable | - | - | exit.05 | polite refusal of an order given for his own good — reads as delusional while legless, which is the joke |
| flopping.40 | Oh, yes, Mr. Engineer. | speech | adapted | 8 | 2 | unbearable | - | - | flopping.40 | cheerfully confirming a humiliating detail. Addressee swapped, *Miss* → *Mr.* with it (see flopping.33). ORIGINAL: "Oh, yes, Miss Donut." |

## repaired

**key:** `repaired`
**split:** none
**fires:** a beached jamaltron reaches full health and swaps back to walking (PLAN E.5), whether by repair pack or by bot.

Book 7's anticipation material is the spine here, and it contains the single best beat in the whole repair cycle: **he negotiates the schedule of his own repair.** Book 8 contributes the emotional model — when he is comforted and put back together he says NOTHING, hops down with a midair flip and settles on the floor — which is why `repaired.13` is in this pool at a real weight. **It is the one silence row where the quiet is contentment rather than distress**, so it is the one that carries chotchki's *for once*.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| repaired.01 | Jamal has hoppers again! Jamal is most grateful. | speech | original | - | 8 | quiet | - | - | repaired.01 |  |
| repaired.02 | Jamal is very excited about this | speech | verbatim | 7 | 7 | quiet | - | - | built.02 | bouncing on a new set. Trailing comma dropped |
| repaired.03 | Top quality this time, Mr. Engineer? Jamal shall find out. | speech | original | - | 6 | quiet | - | - | repaired.03 | the gag, forward-looking. He is about to find out |
| repaired.04 | It is a very robust excitement that he has. | speech | verbatim | 7 | 6 | normal | - | - | built.03 |  |
| repaired.05 | Jamal will only flame on purpose from now on. | speech | verbatim | 7 | 5 | normal | - | - | built.04 | the promise, renewed, having just broken it |
| repaired.06 | Set {N} is fitted. Jamal will be careful this time. | speech | original | - | 5 | normal | - | - | repaired.06 | uses the break counter. **The undercutting tag (*Mostly.*) went at the voice audit.** What replaces it is the reassurance register — a guarantee he cannot keep, forward-looking, delivered straight, exactly as verbatim `built.04` does it. *This time* is the counting-awareness `{N}` already gives him, and he does not hear the irony because there is none in his mouth |
| repaired.07 | Jamal would like to test them immediately. | speech | original | - | 5 | normal | - | - | repaired.07 | **recklessly experimental, and he does not connect testing to consequences** — the bk 8 shape, which is how this whole loop restarts |
| repaired.08 | Jamal’s new hoppers will be ready soon. | speech | adapted | 7 | 4 | normal | - | - | repaired.08 | the third-party leg-builder evaporates: in the mod the engineer occupies that role, so the attribution has nobody left to point at. Reworded only as far as dropping the name forced. ORIGINAL: "Miss Katia says she will make Jamal’s new hoppers soon." |
| repaired.09 | Mayhaps when Jamal gets back from the fighting? | speech | verbatim | 7 | 4 | normal | - | - | repaired.09 | politely negotiating the schedule of his own repair |
| repaired.10 | they are much too small for Jamal! | speech | verbatim | 7 | 4 | normal | - | - | flopping.17 | TRIMMED, full quote at flopping.17. **He complains about the parts to the face of the person fitting them** |
| repaired.11 | Jamal was testing his legs. | speech | verbatim | 8 | 4 | normal | - | - | built.08 |  |
| repaired.12 | Rest assured, Mr. Engineer. | speech | adapted | 7 | 4 | normal | - | - | built.07 | Addressee swapped. ORIGINAL: "Rest assured, Mr. Carl." |
| repaired.13 | Jamal is silent... for once. | narration | original | - | 3 | quiet | - | - | repaired.13 | **NARRATION, the former `[SILENCE]` row, and chotchki's own wording for the shape.** Bk 8's wordless come-down: comforted and put back together he flips down and settles without a word. **This is the one pool where the silence is CONTENTMENT**, so it is the one row that earns the dry *for once* |
| repaired.14 | Nothing is wrong. | speech | verbatim | 8 | 3 | unbearable | - | - | damaged.09 |  |
| repaired.15 | the new and improved sticky feets Jamal has | speech | verbatim | 8 | 3 | unbearable | - | - | built.13 | TRIMMED, full quote at built.13 |
| repaired.16 | Thank you, Mr. Engineer. Jamal owes you an apology anyway. | speech | original | - | 4 | unbearable | - | - | repaired.16 | the apology-as-DEBT shape: he thinks he owes, with or without an offense |

## died

**key:** `died`
**split:** none
**fires:** `on_entity_died`. Once, and the player is probably already upset, so the default is mercy.

**He never dies in either book and is explicitly alive after losing his legs in book 8, so the SITUATION is invented no matter what we do here.** Two strings survive as real quotes anyway, and this is worth flagging because the profile's open question #3 says this pool has zero anchor: it does not. *Jamal would get smushed.* is an exact contiguous substring of his own cheerful explanation of how he expects to die, and *Everything will just stop.* is an exact substring of the bk 8 annihilation material. **The lines are verbatim; the event is ours.** **B.4 ruled they SHIP** — a faithful quote fired at a fabricated moment was the call that needed making, and chotchki made it.

`died.01` is the heaviest row on purpose. **Nobody in two books is ever cruel to him, and a joke over the wreck is the mod being cruel to him** — so it is the flattest of the six former silence rows, with no *for once* and no punchline. It reads *Jamal does not get up.* since the voice audit: *Jamal is quiet now.* was the same observation as `low_health.01`, which fires on the way down seconds earlier, and roughly two in three `quiet`-tier deaths printed both. Naming the wreck instead of the silence differentiates them in CONTENT rather than in wording, which is the only kind of difference `GRP` cannot help with. **This pool has a second narration row now** — `died.08`, the *top quality* verdict, which is an epitaph and therefore not an utterance he owns.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| died.01 | Jamal does not get up. | narration | original | - | 10 | quiet | - | - | died.01 | **NARRATION, the former `[SILENCE]` row, and the merciful default.** Nobody in two books is ever cruel to him, so there is no punchline over the wreck — and no *for once* either. That joke belongs in `repaired`, not here. **REWRITTEN at the voice audit:** *Jamal is quiet now.* and `low_health.01` were the same observation fired ~20 seconds apart, and `GRP` cannot see it because the strings differ. This one names the wreck instead of the silence, in the mod's own vocabulary — every other time he goes down he flops and gets back up |
| died.02 | Jamal would get smushed. | speech | verbatim | 7 | 5 | normal | - | - | low_health.04 | TRIMMED (suffix), full quote at low_health.04. **He predicted this, cheerfully, unprompted** |
| died.03 | Everything will just stop. | speech | verbatim | 8 | 4 | normal | - | - | low_health.11 | six words, no honorific, no scaffolding — inverted escalation at its absolute floor |
| died.04 | Oh my goodness. | speech | verbatim | 7 | 4 | normal | - | - | damaged.01 | his stock exclamation, which he uses for everything including this |
| died.05 | Oh. | speech | original | - | 4 | normal | - | - | died.05 |  |
| died.06 | We won’t even know. | speech | verbatim | 8 | 3 | normal | - | - | low_health.13 |  |
| died.07 | Jamal has been smushed, Mr. Engineer. | speech | original | - | 3 | normal | - | - | died.07 | self-narrated, third person, passive — the shape he uses for his own catastrophes |
| died.08 | Jamal was not top quality. | narration | original | - | 2 | normal | - | - | died.08 | **NARRATION, moved at the voice audit.** The running gag landed on himself — but a past-tense verdict on his whole self is an EPITAPH, and an epitaph is an utterance form only a SURVIVOR has. `low_health.05` does the identical gag correctly in his mouth, as a meter reading in the present tense. The narrator is the survivor, and the verdict lands on the *top quality* claim other people made about him at `built.06` rather than on him. **Cut this if it reads mean rather than sad** |
| died.09 | Jamal is sorry about this also. | speech | original | - | 2 | unbearable | - | - | died.09 | apologizing for his own death is the apology tic's logical terminus |

## remote command done

**key:** `command_done`
**split:** none
**fires:** `on_spider_command_completed` — the autopilot queue empties, or a remote-driving waypoint is reached. Throttle to the LAST waypoint of a queue, not every leg of it.

Richly anchored by book 8, where he is handed chores and reports back on each like a duty log. Two shapes carry the pool: **the commission** (an order restated as an institutional posting, first person plural, pure guard-bot flavor) and **the honestly-downgraded victory** (reports a win, then volunteers the true count without noticing it undercuts him).

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| command_done.01 | Jamal has arrived where he was told, Mr. Engineer. | speech | original | - | 8 | quiet | - | - | command_done.01 | duty log, third person, unprompted |
| command_done.02 | Jamal has kept the bugs away, Mr. Engineer | speech | adapted | 8 | 7 | quiet | - | - | command_done.02 | reporting on a guard shift. **The word *bugs* lands on biters by pure accident and it is free.** Addressee swapped. ORIGINAL: "Jamal has kept the bugs away, Mr. Carl" |
| command_done.03 | It was only one bug, but he has not been back! | speech | verbatim | 8 | 7 | quiet | - | - | command_done.03 | the same report, one breath later. **He downgrades his own victory honestly and does not notice** |
| command_done.04 | The commission is discharged, Mr. Engineer. | speech | original | - | 6 | quiet | - | - | command_done.04 | his institutional register for finishing a chore |
| command_done.05 | Jamal will keep them safe. | speech | verbatim | 7 | 6 | normal | - | - | exit.02 | accepting the NEXT order before being given one |
| command_done.06 | Jamal went there. Jamal only hopped a little. | speech | original | - | 5 | normal | - | - | command_done.06 | **REWRITTEN at the voice audit**, which named a failure shape the earlier passes missed: the one-word undercutting tag (*Much.*) makes him joke about his own unreliability, and his emphasis mechanism is repetition with a one-word VARIATION, which ADDS. This is the shape he actually has — the honest downgrade, one sentence, volunteered without noticing it is a confession (`command_done.03` is the verbatim instance). *A little hop* is his own minimization, every time |
| command_done.07 | It was only a small task, but Jamal did it. | speech | original | - | 5 | normal | - | - | command_done.07 | literal-minded optimism, our words, bk 8's shape |
| command_done.08 | This is quite exciting | speech | verbatim | 7 | 5 | normal | - | - | enter.05 | his response to a dangerous solo assignment. Trailing comma dropped |
| command_done.09 | Jamal awaits his next commission. | speech | original | - | 5 | normal | - | - | command_done.09 | **compulsively useful: accepts every task instantly and never asks why** |
| command_done.10 | Rest assured, Mr. Engineer. | speech | adapted | 7 | 5 | normal | - | - | built.07 | Addressee swapped. ORIGINAL: "Rest assured, Mr. Carl." |
| command_done.11 | Jamal walked the whole way. Jamal could have hopped. | speech | original | - | 4 | unbearable | - | - | command_done.11 | every conversation routes back to the hopping grievance |
| command_done.12 | Jamal does protest | speech | verbatim | 8 | 3 | unbearable | - | - | command_done.12 | objecting to being left out of a tally, in a weak cracking voice, from wherever he is stuck |
| command_done.13 | Mayhaps when Jamal gets back from the fighting? | speech | verbatim | 7 | 3 | unbearable | - | - | repaired.09 |  |

## jump refused

**key:** `jump_refused`
**split:** none — `SUB = sincere` is advisory, see `idle`
**fires:** the jump input is rejected — water, a cliff, no valid landing spot, on cooldown, on a space platform (A.6/E.6), or already beached.

**The best-anchored non-obvious pool in the character**, because book 7 spends a whole argument on being denied the hop and book 8 supplies the flat acceptance that makes the argument funny. The two registers fork cleanly: **he LAMENTS when the parts or the rules insult him, and he ACCEPTS flatly when the geometry simply does not fit.** Both are canon and the flat version is funnier.

Canon cover for the mechanic itself: he is explicitly forbidden from jumping off a tower, with the stated reason that the legs are strong but not THAT strong.

| ID | Line | CH | SOURCE | BK | W | TIER | SUB | GATE | GRP | Note |
|---|---|---|---|---|---|---|---|---|---|---|
| jump_refused.01 | Now I can’t even do a little hop? | speech | verbatim | 7 | 8 | quiet | - | - | jump_refused.01 | **the grievance, stated as a question.** The single most reusable line in the pool |
| jump_refused.02 | I don’t see why Jamal shouldn’t be able to hop. | speech | verbatim | 7 | 7 | quiet | - | - | legs_break.07 |  |
| jump_refused.03 | Jamal's legs are strong, but not THAT strong. | speech | original | - | 7 | quiet | - | - | jump_refused.03 | our wording of the book's own stated reason for forbidding a tower jump |
| jump_refused.04 | I very much yearn for it, Mister Engineer. | speech | adapted | 7 | 6 | normal | - | - | jump_refused.04 | stating the want plainly. Addressee swapped, *Mister* spelling is the source's. ORIGINAL: "I very much yearn for it, Mister Carl." |
| jump_refused.05 | Jamal must not hop here, Mr. Engineer. | speech | original | - | 6 | normal | - | - | jump_refused.05 |  |
| jump_refused.06 | Jamal is afraid of heights. | speech | verbatim | 8 | 5 | quiet | - | - | flopping.34 | **he would rather confess cowardice than let anyone conclude his legs failed** |
| jump_refused.07 | What? | speech | verbatim | 7 | 5 | normal | - | - | exit.03 | his entire response to being benched. Five characters, complete performance |
| jump_refused.08 | There is water there. Jamal does not swim anymore. | speech | original | - | 5 | normal | - | - | jump_refused.08 | **he breathes AIR and cannot breathe water.** The ocean is nostalgia, not physiology |
| jump_refused.09 | Jamal must protest! | speech | verbatim | 7 | 5 | normal | - | - | damaged.03 |  |
| jump_refused.10 | And after that, I was a terror who could fly? | speech | verbatim | 7 | 4 | normal | - | - | idle.07 | lost-glory credentials produced as an argument for jump privileges |
| jump_refused.11 | Jamal is too big for that landing, I fear. | speech | original | - | 4 | normal | - | - | jump_refused.11 | **flat acceptance of geometry**, the bk 8 register — no complaint, which is why it is funnier. **The hedge was in the wrong person and the voice audit caught it:** third person is for himself-as-actor, first person for intent, possession and feeling, and sentence-final *I fear* is the anchored form (bk 8, twice, both softening bad news he is responsible for). `flopping.15` had it right all along |
| jump_refused.12 | Jamal accepts this. Jamal does not like it. | speech | original | - | 4 | normal | - | - | jump_refused.12 |  |
| jump_refused.13 | Not here, Mr. Engineer? Mayhaps over there? | speech | original | - | 4 | unbearable | - | - | jump_refused.13 | permission-seeking: he negotiates rather than obeys |
| jump_refused.14 | It will not work. | speech | verbatim | 7 | 3 | normal | - | - | jump_refused.14 | flat refusal |
| jump_refused.15 | It is quite thoroughly gone... Just like his ability to hop. | speech | verbatim | 7 | 3 | normal | - | - | idle.22 | 60 ch |
| jump_refused.16 | I cannot reach! | speech | verbatim | 8 | 3 | normal | - | - | flopping.36 | wedged and asked to operate a control. Plain first-person panic — short and funny, unlike the long sincere first person |
| jump_refused.17 | I am quite snug! | speech | verbatim | 8 | 3 | normal | - | - | flopping.35 | same beat, immediately after |
| jump_refused.19 | Jamal feels as if you’re trying to reverse psychologicalize him. | speech | verbatim | 7 | 3 | unbearable | - | - | jump_refused.19 | **64 ch — over the cap.** *reverse psychologicalize* is his malaprop and it is worth the overflow. Trim to "trying to reverse psychologicalize him." (39 ch) if the bubble clips |
| jump_refused.20 | I’m scared to come down | speech | verbatim | 8 | 2 | quiet | sincere | once_per_save | jump_refused.20 | TRIMMED (prefix) of "I’m scared to come down, because if I do, maybe I won’t ever see it again." (74 ch). Deep tier — B.4 rules |

---

## Coverage summary

Computed from the tables above, not counted by hand.

| Event | Lines | verbatim | adapted | original | speech | narration | quiet | normal | unbearable |
|---|---|---|---|---|---|---|---|---|---|
| built | 14 | 8 | 2 | 4 | 14 | 0 | 3 | 8 | 3 |
| enter/exit | 16 | 7 | 1 | 8 | 16 | 0 | 8 | 3 | 5 |
| moving | 13 | 6 | 0 | 7 | 11 | 2 | 4 | 6 | 3 |
| idle | 36 | 31 | 0 | 5 | 36 | 0 | 10 | 17 | 9 |
| attacking | 14 | 10 | 0 | 4 | 13 | 1 | 4 | 7 | 3 |
| damaged | 15 | 8 | 0 | 7 | 14 | 1 | 5 | 8 | 2 |
| low health | 13 | 8 | 1 | 4 | 12 | 1 | 4 | 7 | 2 |
| jump | 13 | 7 | 0 | 6 | 12 | 1 | 4 | 6 | 3 |
| land | 11 | 2 | 0 | 9 | 10 | 1 | 4 | 5 | 2 |
| legs break | 32 | 20 | 2 | 10 | 31 | 1 | 11 | 18 | 3 |
| flopping | 40 | 26 | 3 | 11 | 39 | 1 | 7 | 22 | 11 |
| repaired | 16 | 8 | 2 | 6 | 15 | 1 | 4 | 9 | 3 |
| died | 9 | 4 | 0 | 5 | 7 | 2 | 1 | 7 | 1 |
| remote command done | 13 | 5 | 2 | 6 | 13 | 0 | 4 | 6 | 3 |
| jump refused | 19 | 12 | 1 | 6 | 19 | 0 | 5 | 12 | 2 |
| **total** | **274** | **162** | **14** | **98** | **262** | **12** | | | |

**274 rows across 15 sections — 16 pools, since `enter`/`exit` is one section and two — 162 verbatim, 14 adapted, 98 original; 262 speech and 12 narration; median length 38 characters.** Every pool clears the 5–8 minimum; `flopping` and `legs break` carry the load as PLAN E.4 requires, and `idle` is second because it fires on a timer forever.

**Three 2026-09-19 passes cost twelve rows in total (286 → 274), and exactly one replacement line was written across all three** — `land.03`, at the voice audit, because cutting it would have dropped `land` below the four-distinct-string floor at `quiet`.

- **The Q5 proper-noun purge cost three** (286 → 283): `idle` 39 → 38, `command_done` 15 → 13.
- **The B.4 rulings cost six** (283 → 277): the swear ×2 rows (Q2), `jump.14` (Q3), and `attacking.15` + two of the *merely* cluster (Q12). `attacking` 15 → 14, `damaged` 16 → 15, `jump` 14 → 13, `legs break` 33 → 32, `flopping` 42 → 40.
- **The voice audit cost three** (277 → 274): `idle.24` / `jump_refused.18` (one string, two rows) and `idle.25`, all referent flips that only a reader of the books could parse. `idle` 38 → 36, `jump refused` 20 → 19. **These are the first cuts to leave GAPS** — the door on renumbering shut before this pass, so `idle.24`, `idle.25` and `jump_refused.18` are retired ids and not free slots.

**No pool crossed the distinct-string floor as a result** — check the table below against the old one: the smallest survivors are `damaged` at `normal` (14 → 13) and `flopping` at `quiet` (8 → 7), both comfortably above the floor of four, and the two pools that sit below it were already there on purpose. The voice audit's cuts took `idle` at `normal` from 29 to 27 and `jump refused` at `unbearable` from 20 to 19, nowhere near the floor — and `land` held at 4 at `quiet` only because `land.03` was REPLACED rather than cut, which is most of the reason it was replaced. **Writing filler to hold a row count is the failure mode this file refuses**, and chotchki's standing rule is the reason: fewer originals beats flat ones.

**But total pool size is the wrong number, because nobody plays at "all three tiers".** Tiers are cumulative, so what a given player actually has is the DISTINCT strings eligible at their setting — and the two real subpool forks divide their sections on top of that. Counted that way (narration rows count as members, and the nine `once_per_save` rows are counted here even though a given save spends each of them once):

| Pool | quiet | normal | unbearable |
|---|---|---|---|
| built | 3 | 11 | 14 |
| enter/exit [enter] | 4 | 6 | 8 |
| enter/exit [exit] | 4 | 5 | 8 |
| moving | 4 | 10 | 13 |
| idle | 10 | 27 | 36 |
| attacking | 4 | 11 | 14 |
| damaged | 5 | 13 | 15 |
| low health | 4 | 11 | 13 |
| jump | 4 | 10 | 13 |
| land | 4 | 9 | 11 |
| legs break [self] | 7 | 19 | 21 |
| legs break [external] | 4 | 10 | 11 |
| flopping | 7 | 29 | 40 |
| repaired | 4 | 13 | 16 |
| died | 1 | 8 | 9 |
| remote command done | 4 | 10 | 13 |
| jump refused | 5 | 17 | 19 |

**Four distinct strings is the floor, and it was deliberately raised to get there.** Anti-repeat plus a two-member pool is not randomness, it is strict alternation, which a player notices faster than repetition — and `moving`, `land`, `enter`, `exit`, `attacking`, `repaired`, `command_done` and the `external` break fork all sat at two or three. Thirteen rows the notes already called standouts were moved `normal` → `quiet` to fix it, rather than writing filler: `enter.03`, `enter.06`, `exit.03`, `exit.04`, `moving.05`, `moving.07`, `attacking.04`, `damaged.06`, `land.03`, `land.06`, `legs_break.25`, `repaired.03`, `command_done.04`. **`legs_break.25` in particular is not flavor** — it is the only row that tells the player which break fork fired, and a `quiet` player needs that as much as anyone.

Two pools are deliberately below the floor and stay there: **`built` at 3** fires exactly once per entity, so a player never hears it twice in a row anyway, and **`died` at 1** is silence on purpose (see below).

Verbatim rows reuse strings across pools wherever the situation genuinely repeats, so rows are not distinct quotes: **106 distinct verbatim strings drawn from 112 of the bank's 125 lines, plus 10 distinct adapted strings across 14 rows** (a few appear at more than one trim). All 162 verbatim rows, every full quote embedded in a `Note`, and every `ORIGINAL:` quote behind an adapted row were machine-verified as exact substrings of the matching extract — zero failures, zero fabrications.

**13 bank lines go unused** (#16, #32, #33, #79, #86, #87, #92, #93, #94, #95, #105, #116, #124) and they stay in the profile appendix rather than getting forced into a pool. Most are scene-bound in a way Factorio cannot carry — an ally-wide vomiting event, two gods ranked by looks, a missing NPC's location, hours before a race, a drunk pet dinosaur, brushing a cat — or interior to the sincere monologue, where the surrounding sentences do the work and the fragment alone says nothing. **#32, #33 and #94 joined on the Q5 purge** (the three rows a reader would have needed the books to parse at all), and **#16 joined on the B.4 Q2 ruling** — that is the triple-*Fuck*, the only register break in two books, and it is unused because it is CUT rather than because it did not fit. **#93 and #95 joined at the voice audit**, the last two cuts: #95 (*You need to remain in the garage.*) put him in the position of issuing an order, which he never does, and pointed at a building Factorio does not have; #93 (*He’s still very sad about his friends.*) is social reporting, which is a real register of his and has no referent at all in single-player. **Both were verbatim, and a verbatim line with nothing to point at is still a non-sequitur** — which is the Q5 standard applied to a common noun instead of a proper one.

Token usage: **`{N}` in 4 rows is the only token left, and there are no `[SILENCE]` placeholders at all any more** — the six silence rows carry real narration strings. The player is named as *Mr. Engineer* / *Mister Engineer* in **41 rows** — 26 from baking the retired `{PLAYER}` token, 13 addressee swaps, one picked up by the `legs_break.20` rewrite and one by the `exit.08` rewrite at the voice audit — and it is a literal in every one of them, so B.5 substitutes nothing.

**`died` at the `quiet` tier is the one narration row and nothing else.** That is deliberate, not a coverage gap: a player who asked for less Jamal and then watched him blow up gets the explosion, one flat narration line, and no punchline.

**Channel spread, for D.5's renderer.** 12 narration rows across 10 pools — `moving.03`, `moving.11`, `attacking.03`, `damaged.02`, `low_health.01`, `jump.04`, `land.08`, `legs_break.18`, `flopping.23`, `repaired.13`, `died.01`, `died.08`. **Six are the former `[SILENCE]` rows, five are channel moves** (three at B.4, then `flopping.23` and `moving.11` at the voice audit, which found the same diagnosis under-applied) **and one, `died.08`, is an utterance form he cannot own** — an epitaph needs a survivor. `moving` and `died` carry two each. **`died` and `low_health` are the two pools where the narration row at `quiet` is also the heaviest row in the pool**, so the renderer's narration path is not a rare branch that can rot untested — it is the most likely thing a player sees at the two moments that matter most. Three of the twelve additionally carry a suppression window D.5 must honour; the header names them.

**Group spread, for D.5's anti-repeat.** 214 groups over 274 rows, so `GRP` collapses 60 rows onto a string another row already owns. Every narration string is unique, so each of the twelve is its own group — which is also why `GRP` could never have caught the `low_health.01` / `died.01` near-duplicate the voice audit found: two rows saying the same thing in different words are two groups, and differentiating them is an editorial job, not a mechanical one.

## B.4 rulings (all locked 2026-09-19, chotchki)

**Every question below is answered. Two are answered with a DEFERRAL to a later phase, which is a ruling too** — Q8 waits on a real bubble measurement at A.7 and Q11 waits on what the Factorio API turns out to expose at D.5/D.7. Nothing in the thirteen is still waiting on chotchki. **The voice audit that ran after they locked did open new questions, and they are flagged where they bite rather than answered here** — line chaining above all (nine rows only parse after a partner line, and no ruling covers delivering one; the old citation to Q9 was wrong, Q9 is `{N}`), plus whether the `Game Note:` wrapper prints literal angle brackets. His own words are preserved verbatim under each one as `- Comment:`; the prose above each is the ruling written out and traced to the rows it changed.

Ordered by how much downstream work each one unblocked.

1. **`{PLAYER}` — what does he call the player? RESOLVED 2026-09-19 (chotchki): *Mr. Engineer*, baked in as a literal.** Factorio's engineer is canonically nameless — Wube's own position — so none of the three options on the table could supply a real name. The tic was never the name anyway: it is the FORM (*Mister* / *Mr.* / *Miss* + given name, never dropped), and *Mr. Engineer* satisfies the form while staying canonical Factorio. **The mod inherits the Carl relationship wholesale** — the player assigns the jobs, owns the vehicle, asks whether the weapon works, and gets the status reports — so Carl's slot IS the player's slot and this is the intended mapping, not a workaround. B.5 is unblocked and gets easier: no token, no substitution, no post-substitution length check. **All 26 rows carry the literal, and zero cross 60 characters.**

2. **Does the swear ship? RESOLVED: NO. CUT.** Old `legs_break.33` and old `flopping.42`, one string (*And... Fuck! Fuck! Fuck my life!*), the funniest thing he says in two books and the only register break in either. **Both rows are gone and bank line #16 is now unused.** Consequences, all of them good for the ship: **no profanity in any shipping string, so the mod portal page needs no content note** and the mod carries no age gating of its own. Both rows were pool tails, so nothing renumbered. The maximum-misery beat falls to `legs_break.31` on the external fork and to `flopping.38` in the flop pool — see those sections; **the honest read is that neither replacement is as good, and that is the price of the ruling rather than an argument against it.**
- Comment: Trim won't land well in game

3. **The two fourth-wall lines. RESOLVED: keep `jump.13`, cut `jump.14`.** SPEC says the jump pool should know it is a meta-joke; **the character emphatically does not know, and that asymmetry is the whole test.** `jump.13` *Jamal does not know the idiom, but Jamal will hop!* passes it — he is being literal-minded about an idiom he has not understood, which is exactly his register, and the audience gets the joke over his head rather than with him. `jump.14` *Watch Jamal be jumped over!* fails it — that is the mod winking, and nothing else in 277 rows does that. Cut; it was the pool tail, so no renumber. `SUB = meta` survives on `jump.13` as an advisory tag.
- Comment: I'm okay with that

4. **`died` has a real anchor after all. RESOLVED: SHIP.** The profile's open question #3 said this pool had zero anchor; it does not. *Jamal would get smushed.* and *Everything will just stop.* are both exact contiguous substrings — and the first one is **him cheerfully explaining, unprompted, how he expects to die.** The lines are verbatim, the event is ours, and chotchki ruled that the combination is fine. All 9 rows ship, `died.01` stays the heaviest row and is now the flattest of the six narration rows: mercy first, no punchline over the wreck.
- Comment: ship them

5. **Verbatim honorifics stay unmodified? RESOLVED 2026-09-19 (chotchki): no — every Dungeon Crawler Carl proper noun is purged from the `Line` column.** A player who has never read the books must hit ZERO non-sequiturs, so each name was swapped, trimmed away, or the row died. What happened:

    - **13 rows swapped their addressee to *Mr. Engineer* and retagged `verbatim` → `adapted`:** `built.07`, `built.11`, `enter.06`, `low_health.03`, `legs_break.06`, `legs_break.15`, `flopping.02`, `flopping.33`, `flopping.40`, `repaired.12`, `command_done.02`, `command_done.10`, `jump_refused.04`. The *Mr.* / *Mister* spelling is whichever one the source used, because that variation is real. `flopping.33` and `flopping.40` are the two that also move the honorific (*Miss Donut* → *Mr. Engineer*) — unavoidable once the player is a mister.
    - **`repaired.08` lost a third-party attribution rather than an addressee.** Katia built his legs; in the mod the engineer occupies that role, so *Miss Katia says she will make...* has nobody left to point at and collapses to *Jamal's new hoppers will be ready soon.* Tagged `adapted`, original in the note.
    - **Two rows the ruling did not list were rescued as TRIMS and stay `verbatim`:** `low_health.12` dropped *Miss Hedy says* (leaving *if you die, we die.*, which is the fact that actually terrified him and which sits beside its own monologue neighbours at `.11` and `.13`), and `idle.28` dropped *like Eileithyia*. **A trim beats an adaptation whenever one is available**, because the string stays a machine-verifiable substring instead of needing a provenance note.
    - **3 rows were cut outright** for needing the books to parse at all: old `idle.25` (*No, Mr. Mongo,* — a drunk pet dinosaur; the id was reused by this pass's renumber and retired for good at the voice audit), `command_done.14` and `command_done.15` (the cat-grooming scene, including his funniest beat in book 8; it is gone and that is the price).

    **Scope: the purge covers the `Line` column and nothing else.** `Note` cells still carry the untouched originals ON PURPOSE — that is the provenance chain the fidelity checker greps, and deleting it would make every adapted row unverifiable. The section commentary likewise still names Carl and Donut where it explains where a line came from. None of that text reaches the generator, which reads `Line` and stops.

6. **The sincere lines. RESOLVED: they STAY, and they get a real gate.** `idle.33`–`.35`, `idle.38`, `low_health.10`–`.13`, `jump_refused.20` — nine rows, `SUB = sincere`, now `GATE = once_per_save` **at their existing tiers and weights, both unchanged.** They stay because the alternative is a character who is only a joke. They get gated because **weight 1 was never a rarity mechanism**: cumulative tiers shrink the pool a `quiet` row competes in, so a `quiet`-tagged weight-1 row was ~4x MORE likely to fire for the player who asked for the least Jamal than for the player who asked for the most. The arithmetic is under `idle`; the mechanic is under the `GATE` section. **A hard gate makes them land as a moment instead of a rotation**, and D.5 stores the fired-set per entity next to `{N}`, so it costs nothing new.
- Comment: I think we keep them

7. **`[SILENCE]` as a weighted pool member. RESOLVED: it is not a silence at all, it is a NARRATION row.** 6 rows across 6 pools, heaviest at `low_health` and `died`. chotchki's encoding — a game note rather than an absence — is strictly better than the old one on three counts: **an emitted absence is indistinguishable from a mod that failed to fire**; a speech mod is structurally bad at silence in the first place; and **both books' narrations explicitly FLAG his going quiet as the anomaly**, so naming it is the faithful move and not a concession. Each of the six carries its own per-pool wording rather than one string six times — the table is in the header. **Two things this ruling said that the file then dropped, both restored at the voice audit:** the `Game Note: ` prefix is real and now belongs to D.5 at render time rather than to twelve `Line` cells (the header carries the decision, the width budget and the one bracket-shaped interpretation call), and **a named silence has to actually be silent** — three of the rows assert an ongoing quiet that the next roll falsified inside a tick, so they now carry suppression windows with boundaries the mod already computes. **The Lua shape gets SIMPLER, not more complex:** no pool entry lacks a string, so the generator has no absent-string branch and the picker has no emit-nothing path to get wrong. The only new conditional is `CH`.
- Comment: I would encode it as "Game Note: <Jamal is silent ... for once>"

8. **Two lines exceed the 60-char cap. RESOLVED AS A DEFERRAL: both stay UNTRIMMED pending a real measurement at A.7.** `flopping.38` at 61 and `jump_refused.19` at 64, each with a trim already written into its `Note` cell — and **neither trim gets taken on a guess.** `jump_refused.19` is the one that makes the deferral worth it: trimming it spends *reverse psychologicalize*, his best malaprop, to satisfy a cap nobody has verified exists at 60. **Not coupled to anything else any more:** *Mr. Engineer* is baked in (longest affected row: 58), `{N}` tops out at 50, and **these two are the only over-cap rows this file will ever have.** A.7 measures a bubble over a moving vehicle; the number either raises the cap or takes the two trims.
- Comment: I'll test

9. **The break counter `{N}`. RESOLVED: SHIPS.** 4 rows use it — `legs_break.17`, `legs_break.27`, `flopping.30`, `repaired.06` — and they top out at 51 characters with a three-digit count (50 until the voice audit rewrote `repaired.06`). **Storage is `storage`-only per-entity state, which E.6 already requires for multiplayer sync**: one table keyed by `unit_number` holding an integer, and the `once_per_save` fired-set Q6 needs rides in the same record. No mutable module-level state, no per-tick work, one entry per jamaltron, created lazily on the first break. **The one thing that will actually bite: clean the entry up on `on_entity_died` / `on_object_destroyed`**, or the save accumulates one small dead record per destroyed jamaltron forever.
- Comment: Yes keep it

10. **Anti-repeat exception for `idle.01` → `idle.02`. RESOLVED: explicit allow-list, ordered pair.** He is the only character in the books who quotes himself, and the callback only works in one direction, so the allow-list holds the ordered pair and not a symmetric one. **Two honest caveats worth recording rather than glossing:** the two rows are different strings and therefore different `GRP` groups, so a strictly group-keyed suppressor already permits the succession — **the allow-list is insurance against a later near-duplicate heuristic silently killing the gag**, plus a hook if D.5 ever wants to CHAIN the pair deliberately instead of merely permitting it. Everything else suppresses recent picks normally, keyed on `GRP`, per entity, across pools.
- Comment: I'm good with it

11. **`attacking` friendly-fire subpool. RESOLVED AS A DEFERRAL: the gate stays, the decision moves to D.5/D.7.** `attacking.11`–`.13` are eligible only when the mod KNOWS he hit something on his own force. **If the API cannot tell us that cheaply, the three rows get cut rather than fired blind** — an unprompted apology for damage that did not happen is the one failure mode in this file that reads as broken rather than annoying, and it lands on his single best verbatim material, which makes it worse and not better. chotchki's framing is the right one: Factorio is mostly single-player, so friendly fire is an edge case and the rows are a bonus, not a load-bearing part of the pool. **If they go, `attacking` drops to 11 rows and needs no replacements.**
- Comment: Since factorio is mainly single player, we'll have to see what the api provides

12. **Six `original` rows flagged off-voice. RESOLVED — and the ruling reframed the finding rather than accepting it.** Held against the profile's own rules, not against taste. **Three rows were never off-voice at all: they were in the WRONG CHANNEL**, which is the finding chotchki's two-channel ruling produced and the reason `CH` exists. Of the other three, one was rewritten and two were dropped. Net: **three rows moved, one rewritten, three cut** (counting `attacking.15`). Two failure shapes were alleged; only one of them turned out to be real:

    - **Narrator syntax in his mouth — NOT A DEFECT, A MIS-ROUTING. All three rows kept, moved to `CH = narration`.** `jump.04` *Up goes Jamal!* (weight 7, second-heaviest in the jump pool), `land.08`, and `moving.03` *Clack, clack, clack go Jamal's feet.* do all use fronted verbs that make him the OBJECT of a sportscast, and his own self-narration does put himself in the subject slot — `Jamal is <verb>ing` — every time, in both books. **But the diagnosis stopped one step short: the footfall onomatopoeia IS the book's narration describing him from outside, which is not a flaw in the line, it is a statement about who is speaking it.** Once the mod has a narration channel, all three rows are correct where the audit found them wrong, at their existing weights and tiers. One real edit survived the reframe: `land.08`'s bare-noun *Ground!* went, because a narrator shouting a noun reads as oddly as he did saying it — the row is now *Jamal has found the ground. It was never far.*, with a second clause that is the narrator's own callback to `jump.09`. **The audit was right about the text and wrong about the fix, and that is worth recording**: the reflex on an off-voice line is to cut it, and cutting three good rows here would have been the expensive mistake.
    - Comment: I had added a game narration to one of my comments above, that plus this may need to be considered
    - **The *merely* cluster — REAL, and this one held up. One rewritten, two dropped.** Register 4 in the profile (deadpan observer) fires on catastrophe happening to OTHER people; **turned on himself he does misery, formal protest, or flat hardware denial** — *Nothing is wrong.* is the canonical move and it is absurd rather than clever, not wry. The three rows were judged one at a time, because "rewrite in register" is only the right answer when the register has something left to say in that pool:

        - **`legs_break.20` REWRITTEN** → *The legs did not fail, Mr. Engineer. Jamal did.* (47 ch). *They are merely apart.* was the writer being funny about him. The replacement is the profile's own documented move instead: **when someone assumes the legs broke, he corrects the diagnosis and takes the blame himself rather than let anyone conclude the hardware failed** (bk 8). Flat, in register, and it lands on the `self` fork, which is precisely where blame-claiming belongs and where the file already forbids a quality complaint. **Rewritten AGAIN at the voice audit** — see the postscript.

    **POSTSCRIPT — the voice audit, run after this ruling locked, and what it actually found.** The reframe held: no row moved back, and the narration channel is now load-bearing in ten pools. What it got wrong was the SCOPE. **Two more rows were in the wrong channel on the identical diagnosis** — `flopping.23`, whose own Note called it a caption when a caption IS narration, and `moving.11`, which uses the narration's *whir* in the very pool `moving.03` had just been moved out of — and `died.08` is mis-channelled for a different reason entirely, because a past-tense verdict on his whole self is an epitaph and an epitaph needs a survivor to speak it. **`legs_break.20` was rewritten a second time:** the content was the documented blame-claiming move both times, but *The legs did not fail, Mr. Engineer. Jamal did.* kept the negate-then-snap FORM of *They are merely apart.*, the row it replaced, and his sentence shape buries the news at the END rather than snapping it — so it now defends the hardware and hands over a concrete humiliating fact last, the way the profile's own instantiation (*Jamal is afraid of heights.*) does.

    **And it named a FOURTH failure shape none of the earlier passes had: the one-word undercutting tag.** *For once.* / *Much.* / *Mostly.* / *Probably.* — four rows ending in a one-word retraction. His emphasis mechanism is repetition with a one-word VARIATION, which ADDS (*Such woe! Such woe I have!*); the tag SUBTRACTS, and it makes him joke about his own unreliability, which is wit about himself and the exact thing this ruling dropped `flopping.37` for. **His real self-undercut is the honest downgrade — one sentence, volunteered, and he does not notice it is a confession** (verbatim `command_done.03`). All four rows kept their beat without the tag: `legs_break.31`, `command_done.06`, `repaired.06`, `exit.08`. Three more rows were rewritten for referent flips the earlier cuts created (`damaged.15`, `jump_refused.11`, and `land.03`, the only replacement written in any of the three passes) and three were cut outright.
        - **`flopping.37` DROPPED** (*Jamal is not a burden. Jamal is merely horizontal.*). The best-written original in the file and the furthest out of register — both at once, which is exactly why it survived this long. **Everything it carried is already carried in register** by the row directly beneath it, now `flopping.37` *Jamal is sorry to be a bother. Jamal is a bother.*, where the joke is that he AGREES with the accusation. A rewrite would have been a second copy of that.
        - **`damaged.08` DROPPED** (*Jamal did not care for that.*). Understatement about his own injury, and the pool already covers every register he actually has for being hurt: protest at `damaged.03`, hardware denial at `damaged.09`, lament at `damaged.10`. **Nothing was left for a replacement to say, so nothing was written** — chotchki's standing rule is that fewer originals beats flat ones, and two drops against one rewrite is what taking that rule seriously looks like.

    Two more, smaller, both actioned as recommended. **The leading *Ow.* is cut** from the row that is now `damaged.08`, leaving *That is quite unkind.* — the pool's premise is that damage is a wordless NOISE, which is what `damaged.02` is for, and a spelled-out yelp fought that premise from inside the same pool. **`attacking.15` is cut entirely** (*They will not enjoy Jamal's emissions.*): a flat paraphrase of verbatim `attacking.05` in the same pool, minus *toasty*, which is the whole coinage.

    **One correction to the audit's own evidence, recorded because the claim was checkable and wrong.** `attacking.15` was described as *the only row in the file with an empty Note*. It was not — **35 rows had empty `Note` cells** at the time, mostly in `flopping` and `jump_refused` where a reused string's note lives at its first occurrence. `attacking.15` was the only empty note in its OWN pool, which is a real signal and a much weaker one. **The row still deserved cutting on the paraphrase argument alone**, so the conclusion survives its bad supporting stat — but a stat that specific should have been counted before it was asserted, and this file's whole claim to trustworthiness is that its numbers are computed rather than eyeballed.

13. **Pool reuse across events. RESOLVED: `GRP` for the picker, one key per `ID` for the locale, no dedup anywhere.** Reuse is heavier than any single table shows: **214 distinct strings fill 274 rows, and 47 of those strings live in more than one pool, occupying 107 rows** (*Jamal must protest!* ×4, *Nothing is wrong.* ×4, *Rest assured, Mr. Engineer.* ×3, *This is quite exciting* ×3, *Oh my goodness.* ×3). **The locale file gets one key per ID with no deduplication** — a few hundred bytes, ID→key stays total, and a reused line stays free to diverge per pool later.

**And the `GRP` column is the other half, because anti-repeat has to know two IDs are the same sentence.** `legs break` and `flopping` fire back to back — the break, then the apology timer — and **they share 16 strings**, so per-pool suppression is blind at the mod's centerpiece moment: it cannot see that `flopping` is about to re-say the break line the player read two seconds ago. Per firing the odds are small (2–4% depending on tier and fork, worst at `quiet` where the pools are tightest) but the moment is the one the whole mod is built to deliver, and the same shape holds for `built` ∩ `repaired` (6 shared) and for *Nothing is wrong.* / *Jamal must protest!* across four pools each. **So `GRP` is now a real column, computed as the ID of the first row carrying that exact string, and D.5 keys anti-repeat on the group, per ENTITY, ACROSS pools.** One extra field in the generated table; 216 groups over 277 rows, and the full contract is in the header.
