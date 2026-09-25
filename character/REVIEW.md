# Jamal line catalog — decisions for chotchki

**2026-09-20, written for the morning read.** Everything below is a call that is yours and not ours: taste on your own character, plus two phase gates. Nothing here is a bug report — the objective defects are closed (see the next section), and this pass edited no rows.

**Convention in this file:** exact `Line` cell text appears in tables plainly and inline in curly quotes “like this”. Straight double quotes still mean PROVENANCE — the only one in this file is a verbatim book string inside the fenced command block at the end, so a checker that greps the repo for them stays honest.

---

## State, in three sentences

`character/lines.md` is **259 rows across 15 event pools** — 203 distinct strings, 153 `verbatim` / 14 `adapted` / 92 `original`, 247 `speech` / 12 `narration` — and it is the only place any string the mod speaks exists. **The mechanical half is verified and held this pass, independently of the passes that wrote it:** every `verbatim` `Line` is an exact substring of its own extract, all 41 straight-quoted `Note` strings verify against the books, all 14 `adapted` rows carry their `ORIGINAL:`, the 12-column schema and every column domain is intact, all 9 chains are one-hop / same-pool / not scheduled by a swap with delays that recompute exactly from the head, `GRP` equals the first-row id of its string on all 259 rows, and the file's own counted numbers (43 applied trims, 14 lower-case starts over 10 strings, 7 gates, 2 over-cap rows, 0 ASCII apostrophes, 0 DCC proper nouns outside the *Velma* / *Gentlemen* carve-outs) all reproduce from the table. **What is NOT settled is voice on nine rows plus two shapes, four empty refusal sub-pools, and two one-way doors that are yours alone: the B.5 id freeze and the C.4 shark scale.**

## What this pass did and did not touch

**No row was edited.** The brief was objective defects only; I re-derived every invariant above from the table and the extracts and found nothing broken — no row contradicting mod state, no chain that cannot fire, no provenance rule stated and violated, no computed number stale. Three findings I looked hard at and classified **taste, not broken**, so they are decisions below rather than edits: `legs_break.15` (D8.5), `jump_refused.20` (D8, marginals), `jump_refused.10` (D8.3).

**Four audits have now failed four voice passes. The remaining findings are the ones only you can settle**, so they are written as A/B choices with the arithmetic attached. Your answer to each is one letter.

---

## D1 — `moving.01`, the house template at `quiet`

> **Jamal is walking. Jamal is quite good at walking.** — `speech` `original` W8 `quiet`, 49 ch

**The charge.** `Jamal <verbs>. Jamal is quite good at <verbing>.` filled seven rows across six pools; the voice-editor pass ruled it is not his mechanism (his is repetition with a ONE-WORD variation on the SAME clause — *Such woe! Such woe I have!* — which ADDS, where the template swaps the predicate and bolts on a competence claim he never makes). Four were rewritten, two cut, **and this one was kept as-is** because `moving` has only four distinct strings at `quiet` and this is the cleanest instance. It is also **the single most-heard row in its pool: 8 of 24 weight, 33% of every `moving` line a `quiet` player hears** (15% at `normal`, 14% at `unbearable`).

| | |
|---|---|
| **FOR keeping** | It is the pool's anchor row and the only one that states the backbone shape plainly; `moving` is the thinnest pool in the character; the template reads as him, even if it is not his documented mechanism; and the file's rule is *where a defect and a floor collide, rewrite in register* — which means do not cut, not do not keep. |
| **AGAINST** | It is the last survivor of a shape the file has already ruled against six times, sitting at 1-in-3 of the quiet player's `moving` rolls. The quiet tier is defined as *lines good enough to survive a friend opting mostly out*, and this is the first line that friend hears when Jamal starts walking. |

**Options.** **A** keep. **B** rewrite in register, keeping four distinct strings at `quiet` (the fix `idle.03`, `exit.04`, `enter.07`, `damaged.15` all took) — candidate: “Jamal is walking. Jamal is walking most briskly.” (48 ch; *most* is his #2 marker, the variation is one word on the same clause). **C** cut — not available, `moving` at `quiet` is exactly on the four-string floor.

**Recommendation: B.** The row is not wrong, it is the one place the ruled-against shape is loudest, and B costs nothing but a string you have to like.

## D2 — `repaired.03`, “Jamal shall find out.”

> **Top quality this time, Mr. Engineer? Jamal shall find out.** — `speech` `original` W6 `quiet`, 58 ch, 25% of `repaired` at `quiet`

**The charge.** This is the construction `built.06` lost at the voice-editor pass. There, *We shall see.* was cut (the row kept its id and got *Top quality indeed!*) because skepticism about *top quality* lets him in on his own gag: *top quality* is **a promise he believes he was made**, he is unteachable by consequence, and the audience is supposed to get the joke over his head.

| | |
|---|---|
| **FOR keeping** | The precedent does not transfer, and this is the whole argument: `built.06`'s skepticism was illegitimate because it fires at t=0, **before a single set has broken in this save**, so it needed cross-book knowledge. `repaired` fires only after a break — the evidence is in-save and earned. And “Jamal shall find out” is not skepticism, it is the profile's *recklessly experimental, does not connect testing to consequences*: he is about to go test them. `repaired.07` (“Jamal would like to test them immediately.”) is the same beat. |
| **AGAINST** | Read as a wink, it is the same wink, and the running gag is funnier if he never once suspects. |
| **Cost** | Cutting is off the table: `repaired` at `quiet` is exactly on the four-string floor and this row is one of the thirteen moved `normal` → `quiet` to get it there. Trimming to “Top quality this time, Mr. Engineer?” (36 ch) is free. |

**Options.** **A** keep. **B** trim the tag.

**Recommendation: A, keep.** He is not being wry, he is volunteering to run the experiment that breaks the legs again — which is the loop the mod is built out of.

## D3 — `died.08`, the epitaph

> **Jamal was not top quality.** — `narration` `original` W2 `normal`, 6% of `died` at `normal`

**The charge.** The voice audit moved this to `narration` because a past-tense verdict on his whole self is an EPITAPH and only a survivor utters one. **The move arguably made the MOD the cruel party.** The profile is explicit (`jamal_profile.md:150`): *Nobody is ever cruel to him. Exasperated, yes. Cruel, no — in two books. Preserve this in the mod's tone: the player should be annoyed, never encouraged to resent him.* In his own mouth the line was him doing the gag on himself; in the narrator's it is the game grading a wreck. The row's own `Note` already says **cut this if it reads mean rather than sad**.

| | |
|---|---|
| **FOR keeping** | The verdict lands on the *top quality* claim other people made about him at `built.06`, not on him, which is the reading the `Note` argues for; and `died.01` (“Jamal does not get up.”) already sets the pool's tone to mercy, so this is the one dry beat in it. |
| **AGAINST** | The player cannot hear that distinction over a corpse. The gag is already carried correctly in his mouth at `low_health.05` (“Jamal is not feeling top quality, Mr. Engineer.”) as a present-tense meter reading, so nothing is lost. `died` at `quiet` is 1 row by design, so the floor is not in play. |

**Options.** **A** keep as `narration`. **B** cut (id retired, gap left). **C** back to `speech` as last words.

**Recommendation: B, cut.** The pool exists to be merciful, the gag has a correct home one event earlier, and C re-opens the epitaph problem the audit closed.

## D4 — `flopping.37`, un-gated sincere material on the apology metronome

> **Jamal is sorry to be a bother. Jamal is a bother.** — `speech` `original` W3 `quiet` `self`, GATE `-`

**The charge.** `flopping` is the one pool designed to be heard dozens of times in a row, on a repeating interval scaled by verbosity. This row is a flat verdict on his own worth, and it carries **no gate** — 3 of 34 weight on the `self` fork at `quiet` is ~1 in 11 apology ticks, i.e. **a 24% chance of hearing it inside the first three intervals**. Every other row in this register is gated: all seven `once_per_save` rows (`idle.34`, `idle.35`, `low_health.10`–`.13`, `jump_refused.20`) exist because B.4 Q6 found that weight-1 was not a rarity mechanism. This row is the eighth of that kind and was never enumerated.

| | |
|---|---|
| **FOR keeping as-is** | It names the trait the whole apology tic is made of (`jamal_profile.md:146`, bother-averse past the point of self-harm), and it is the only row in the file that does. `low_health.09` was cut partly because this row already carries the beat. |
| **AGAINST** | Nothing in two books has him call himself a bother — the trait is that he FEARS being one. Repeated on a metronome, the one line where he knows what he is becomes wallpaper, which is exactly the failure Q6 fixed for the other seven. |

**Options.** **A** keep. **B** add `GATE = once_per_save` — extends your own Q6 ruling to an eighth row, costs nothing (the `storage` record already holds the fired-set), and leaves 5 distinct strings in the `quiet` `self`+`any` cell, above the floor of four. **C** trim to “Jamal is sorry to be a bother.” (30 ch), which makes it an ordinary apology row and redundant with the metronome. **D** cut.

**Recommendation: B.** It is the mechanism you already invented for exactly this material, and it is the only option that makes the line land as a moment without writing or losing anything.

## D5 — `built.14`, two clipped tags on his one drive

> **Jamal would like to hop. Later. Mayhaps.** — `speech` `original` W3 `unbearable`, 5% of `built`

**The charge.** Two defects in one row. (1) **Two one-word undercutting tags back to back** — the fourth failure shape (*For once.* / *Much.* / *Mostly.* / *Probably.*), and `flopping.05` was CUT for precisely *two one-word undercutting tags in a row*. (2) **It hedges the drive.** `jamal_profile.md:93`: sentence-final *I fear* is his hedge, used twice, *both softening bad news he is responsible for — he hedges facts, never opinions*. Wanting to hop is the opinion, the drive, and the engine of the whole mod; he states it flat everywhere else (`jump_refused.04` “I very much yearn for it, Mister Engineer.”, `idle.11`, `moving.09`).

| | |
|---|---|
| **FOR keeping** | *Mayhaps* is his (bk 7), and the row can be read as permission-seeking politeness rather than hedging — he wants it, he is not going to push right now. That register is canon. |
| **AGAINST** | It is the only row in `built` that states the drive at t=0, and it states it at half volume. `flopping.05`'s cut is the precedent for the form. |

**Options.** **A** keep. **B** trim to “Jamal would like to hop.” (24 ch) — the drive stated plainly on turn one; `built` at `unbearable` has 13 distinct strings so there is no floor risk, and the row is ours so there is no provenance cost. **C** cut — loses the drive from `built` entirely.

**Recommendation: B.** The file's own rule: defect plus floor means rewrite, defect plus redundancy means cut. Nothing else in `built` carries the hop, so trim it, do not lose it.

## D6 — `moving.11`: the audit is wrong, and here is the line that says so

> **The legs whir. They were built to be quiet.** — `narration` `original` W4 `unbearable`

**The charge was:** register fixed but content invented — asserts a leg-design fact the profile does not carry.

**Checked, and the charge does not survive.** `jamal_profile.md:232`, verbatim: *Legs WHIR when running and the feet CLICK-CLACK on hard floors [7] … **He was built to be quiet as well as quick — Carl's stated reason for the whole rig — and he audibly is not.*** The profile carries both halves of this row — the narration word *whir* and the design intent — and names the intent as the builder's own stated reason. The row is the book's joke, in the narrator's voice, which is the channel that joke lives in.

**The one live question, which is small:** in the mod the builder is Mr. Engineer, who had no such intent, so the narrator asserts a backstory the player was not party to. That is equally true of *the fifth set of legs*, the apex-predator résumé and the lost sense of smell, and `narration` is where outside-in facts legitimately live.

**Options.** **A** keep (recommended). **B** soften to *meant to be quiet*. **C** cut.

**Recommendation: A, keep, and the finding is closed as refuted.** Worth recording why this one happened: the audit checked the string against the row's `Note`, and the `Note` does not cite the profile line. That is a documentation gap, not a content defect.

## D7 — the two ALL-CAPS rows

| ID | Line | Fields | Job |
|---|---|---|---|
| `legs_break.25` | Jamal did NOT hop! Jamal wishes this noted. | `speech` `original` W6 `quiet` `external` | the **only** row that tells the player which break fork fired — information, not flavor, which is why it is `quiet`. 20% of the external fork at `quiet` |
| `jump_refused.03` | Jamal’s legs are strong, but not THAT strong. | `speech` `original` W7 `quiet` `any` | our wording of the book's own stated reason for forbidding a tower jump. 24% of the `any` rows at `quiet` |

**The charge.** ALL-CAPS is not one of his devices. Measured against the extracts: **across 282 quoted dialogue spans in the two books, zero use ALL-CAPS for emphasis** (the one caps token inside a quote is the acronym *FUPA*). His documented emphasis mechanism is repetition with a one-word variation. Both caps rows are `original` — this is our device, not his.

| | |
|---|---|
| **FOR keeping** | A speech bubble has no italics, and caps is the only stress marker available. Both rows hinge on stress: `legs_break.25` is a protest whose whole content is the negation, and `jump_refused.03` is a contrast. |
| **AGAINST** | A device the character never uses, in the two rows a `quiet` player hears most in their pools, in a file that reproduces his punctuation character for character. |

**Options.** **A** keep both. **B** drop both to lower case (“Jamal did not hop! …”, 43 ch; “… but not that strong.”, 45 ch). **C** split: keep `legs_break.25`, lower-case `jump_refused.03`.

**Recommendation: C.** `legs_break.25` is doing a job no other row does and the caps is the signal that carries it in a 43-character bubble; `jump_refused.03`'s contrast is already carried by *but*, so the caps there is decoration.

## D8 — Shape 6: deixis with no referent the pool can supply

**What the shape is.** A row that points at something — *she*, *them*, *after that*, *such tricks*, *Still* — where the antecedent lived one sentence earlier in the book and the mod's pool has no way to put it on screen. **Distinct from the bare-pronoun rule already in the file** (that one is narrow: a pronoun standing in for *Jamal* himself). **Almost every member is `verbatim`**, so the cost of cutting is provenance and the fix, where one exists, is a CHAIN — the same move that saved `built.03`, `moving.13` and `flopping.21`.

**Note on numbering:** the file's own postscript already uses *sixth shape* for *a channel label cannot change a voice*. If you want these recorded in `lines.md`, they are the seventh and eighth shapes, not the sixth and seventh.

| # | Row(s) | Line | Fields | What it points at | Can the pool supply it? | Fix |
|---|---|---|---|---|---|---|
| 8.1 | `idle.29` | I have heard she is quite beautiful. | `verbatim` 7, W2 `unbearable` | *she* = a goddess (`idle.28`) | no — `idle.28` is unchained, and the odds of hearing them in order are nil | **chain `idle.28` → `idle.29` `tail-only` at 150 ticks.** The two sentences are 18 characters apart in the book — one dialogue tag |
| 8.2 | `idle.07` | And after that, I was a terror who could fly? | `verbatim` 7, W4 `normal` | *after that* = the apex-predator boast (`idle.06`) | no, but `idle.06` is in-pool | **chain `idle.06` → `idle.07` `tail-only` at 150 ticks.** The two sentences are 1 character apart in the book — consecutive, same breath |
| 8.3 | `jump_refused.10` | And after that, I was a terror who could fly? | `verbatim` 7, W4 `normal` `any` | same | **never** — nothing in that pool can set it up, ever | cut (precedent: `attacking.14`, `jump_refused.15`), or accept it as a bare credential boast |
| 8.4 | `idle.30` | Jamal is much too quick-witted for such tricks. | `verbatim` 7, W2 `unbearable` | *such tricks* = a trick played on him | no, and nothing in `idle` could | keep (idiomatic dismissal, reads as a general boast) or cut |
| 8.5 | `legs_break.15` | Still, Mr. Engineer. | `adapted` 7, W4 `normal` `self` | a concession to pivot from — in the book it is the hinge between the apology and the defence of hopping | **never** — `legs_break` fires exactly one line per break, and by your locked semantics it can carry no chain at all (a swap cancels a pending follow-up) | cut, or keep as a politeness noise |
| 8.6 | `exit.02`, `command_done.05` | Jamal will keep them safe. | `verbatim` 7, W6 `quiet` / W6 `normal` | *them* = whatever he was told to guard | partly — parking him IS the order, in spirit | keep |

**Marginals, checked and cleared, listed so nobody re-raises them:** `jump.07` (“Oh, I do.” — the key press is the question), `died.09` (*also* is satisfied by a save's worth of prior apologies), `flopping.17` / `repaired.10` (*they* = the legs, present at both events), `idle.26` (*those feet* — the player has feet), `idle.12` (an apology for the flame leak, which is his default state), `jump_refused.20` (“I’m scared to come down” reads as fear of the descent, which is why he will not hop — `jump_refused.06` is right beside it), `built.06` / `moving.05` / `moving.11` / `damaged.06` / `flopping.12` / `repaired.07` (antecedent in-row or supplied by the event), *Such woe!* (intensifier, not deixis).

**Recommendation: wire 8.1 and 8.2 as chains, cut 8.3, keep 8.4 and 8.6, cut 8.5.** The two chains are free and provenance-honest — the book runs both pairs as one utterance — and they take `idle` from four chains to six of a then-eleven total, which is concentrated but it is also the only pool that fires on a bare timer with room for two beats. 8.3 and 8.5 are the two rows where the setup can never arrive, which is the standard that already retired `idle.22`, `jump_refused.15` and `attacking.14`.

## D9 — Shape 7: the writer's pity

**What the shape is.** Rows where the sorrow is OURS rather than his — the mod feeling sorry for him, or him grading his own pathetic condition, in a character whose defining trait is that his self-read never catches up (`jamal_profile.md:150`, and the tone rule: *the player should be annoyed, never encouraged to resent him*).

**The finding that decides most of this in one stroke: all seven candidates are `original`. Not one is `verbatim`.** Every sincere row that came out of a book is gated `once_per_save` (`idle.34`, `idle.35`, `low_health.10`–`.13`, `jump_refused.20`). **So the split is authorship, not register: pathos he actually says is gated and fine; pathos we wrote is the thing to look at.** Checking each against an anchor clears four of the seven.

| # | Row | Line | Fields | Verdict |
|---|---|---|---|---|
| 9.1 | `flopping.37` | Jamal is sorry to be a bother. Jamal is a bother. | W3 `quiet` `self` | **pity.** Nothing in two books has him call himself a bother; the trait is that he fears being one. Un-gated on the metronome — this is D4 |
| 9.2 | `died.08` | Jamal was not top quality. | W2 `normal` `narration` | **pity, and the mod's own.** This is D3 |
| 9.3 | `flopping.23` | Jamal’s head sways back and forth. That is grief. | W4 `normal` `narration` | **pity.** The observation is canon (he waves his whole head to express misery, bk 8); *That is grief.* is the narrator telling the player how to feel about it. A dry gloss that NAMES the feeling is the one narrator move that editorializes |
| 9.4 | `flopping.13` | Jamal is flopping. It is quite undignified. | W6 `normal` `any` | **anchored — clear it.** `flopping.16` is verbatim bk 8: *It is with great embarrassment that I admit this.* He does comment on his own dignity, in exactly this register |
| 9.5 | `damaged.15` | Jamal will endure. Jamal will endure quietly. | W3 `unbearable` | **anchored — clear it.** `jamal_profile.md:146`, bother-averse past the point of self-harm: hours stuck and woozy and silent rather than inconvenience anyone. *quietly* is the promise not to be a bother, not a competence claim |
| 9.6 | `flopping.32` | Jamal is still here. Jamal wishes to be counted. | W4 `unbearable` `any` | **anchored — clear it.** Formal protest at being miscounted in a tally is a real bk 8 beat; `command_done.12` (*Jamal does protest*) is the verbatim instance |
| 9.7 | `died.09` | Jamal is sorry about this also. | W2 `unbearable` | **anchored — clear it.** Apologizing for his own death is the apology-as-inventory tic running to its terminus, which is the gag and not a lament |

**Options.** **A** keep all seven. **B** act on 9.1–9.3 only (D4 gates one, D3 cuts one, and 9.3 wants either a cut of the second sentence — “Jamal’s head sways back and forth.” at 34 ch — or nothing). **C** treat all seven as pity and strip the register, which would cost `flopping` and `damaged` their `unbearable` escalation.

**Recommendation: B.** Three rows, one gate, one cut, one optional trim. The other four are him, with an anchor each.

## D10 — the staffing gap: four refusal reasons with zero lines

`jump_refused` is `gated` on `reason`, and PLAN B.6 asks for **one sub-pool per reason E.2 enumerates**. Live counts over 18 rows:

| Reason | Rows | Detection | Fires when |
|---|---|---|---|
| `any` | 13 | always eligible | everything falls through here |
| `water` | 1 — `jump_refused.08` at W12 `quiet`, tied heaviest in the file | `tile.prototype.fluid ~= nil` | the best joke in the mod |
| `blocked` | 4 — `.11`, `.13`, `.16`, `.17` | `find_non_colliding_position` returns nil | cliffs, buildings, trees |
| `platform` | **0** | SA; E.6 forbids the jump outright | **every SA player who presses the key on a space platform** |
| `cooldown` | **0** | a tick stamp | the one refusal a player triggers on purpose, repeatedly |
| `autopilot` | **0** | `autopilot_destination` is set | remote-driving |
| `no_driver` | **0** | empty seat | nobody is there to read it |

**The file's current position** is that the four zeroes are a finding rather than an omission: they fall through to thirteen generic complaints, which is correct behaviour and needs no code, and a line written to fill a cell would be filler — the thing this catalog refuses.

**The case for writing lines anyway, and it is strongest for `platform`.** A shark refusing to jump **in space** is a better gag than the water one, and unlike `water` it is guaranteed to fire: SPEC locks jumping OFF on space platforms, so for any Space Age player that refusal is not an edge case, it is the whole feature on that surface. `cooldown` is second on different grounds — it is the only reason a player triggers deliberately and repeatedly, so it is where a generic wears out fastest. `autopilot` and `no_driver` are genuinely better unstaffed (`no_driver` should probably not speak at all — nobody is in the seat).

**Options.** **A** falling through is fine, close the finding. **B** write `platform` only (2–3 rows). **C** write `platform` + `cooldown` (4–6 rows). **D** staff all four.

**Recommendation: B, and it has to happen before B.5.** One reason, two or three rows, and it is the only zero cell whose refusal is guaranteed rather than incidental. Everything new has to be written — there is nothing in the pool to reassign — so this is the one decision on this page that costs you new strings.

---

## Blocked on you

### B.5 — generated, and NOT frozen. The freeze moved to F.6.

**chotchki, 2026-09-24: "I'm not freezing IDs until very late in this build since play testing will be a big determining factor."** That splits what this section used to treat as one event. `tools/gen_lines.py` has run and both files are committed, so every `ID` is a locale key IN THE REPO, and CI fails a stale pair from here on. But a locale key only becomes a public contract when it SHIPS: until F.5 the only things that hold an id are playtest saves (the per-entity fired-set and pending chains in `storage`), and breaking those is what playtest saves are for. So cuts and renumbers stay legal through playtesting; each one is an edit to `lines.md`, a regenerate and a commit. **The one-way door is now PLAN F.6, the last thing before release** — after it, a cut leaves a permanent gap and the id is retired forever. Every cut on this page (D3, D5C, D8.3, D8.5, D9) is still free until then.

Also still open ahead of the freeze, and both are already in the file: the two over-cap rows (`flopping.38` at 61 and `jump_refused.19` at 64) stay untrimmed **by your B.4 Q8 ruling until you measure a real speech bubble at A.7**, and the `Game Note: ` prefix for the 12 `narration` rows renders in D.5, not in the `Line` column, with one interpretation call flagged (your angle brackets read as placeholder notation, not literal characters).

### C.4 — the shark scale.

Two candidate values from the C.3 camera work: **0.410** (the shark matched to the stock torso footprint, ±1.03 tiles) and **~0.597** (reads as a whole shark). **The constraint nobody measured until C.3 is the leg mounts:** `create_spidertron` declares them `by_pixel(±15,−22) (±23,−10) (±25,+4) (±15,+17)` — **±0.78 tiles transverse** — against a model that is a **2.24:1 body**.

The arithmetic, with its assumption stated plainly (that 0.410 matches the torso's 2.06-tile extent along the shark's LONG axis):

| Scale | Body length | Body half-width | Gap between flank and leg mount |
|---|---|---|---|
| 0.410 | 2.06 tiles | 0.46 | **0.32 tiles of air** |
| 0.597 | 3.00 tiles | 0.67 | **0.11 tiles of air** |
| 0.695 | 3.49 tiles | 0.78 | flush |

**Neither candidate puts the legs on the shark.** A 2.24:1 body wide enough to grow legs at ±0.78 is ~3.5 tiles long, i.e. 1.7x the stock footprint fore-and-aft — and that overhang is FAITHFUL: the books' silhouette is a 17-foot shark riding HIGH on eight legs, and the profile reads him as a vehicle-scale entity (`jamal_profile.md:230`–`235`).

**The thing most likely to be missed: `mount_position` is ours.** `mod/jamaltron/prototypes/entity.lua` deep-copies the stock body, so `body.spider_engine.legs[i].mount_position` comes along in the copy and is one edit per leg. **±0.78 is an inherited default, not a limit** — so the real question is not *which scale fits the mounts* but *do you want a shark-sized shark with the mounts moved out, or a spidertron-sized shark with the mounts left alone*.

**Options.** **A** 0.410, stock mounts — legs correct, shark reads stubby, zero prototype changes. **B** ~0.60, stock mounts — best compromise, legs float 0.11 tiles, which is ~7 px at C.3's 64 px/tile and may or may not read on screen. **C** ~0.70 with the mounts pushed to ±0.78 — shark correct, flush legs, 3.5 tiles long, and D.4's swap plus the collision box want a second look at that size.

**Recommendation: B for the first render pass, and decide between B and C off the image, not off this table.** C.10's compare mode renders 8 rotations beside the stock spidertron in under a minute, which answers it better than any arithmetic here.

---

## Next steps, one command each

```sh
cd /Users/chotchki/workspace/factorio_jamal

# see any row exactly as it ships, with all 12 columns
grep -n '^| moving\.01 ' character/lines.md

# see a whole tier cell before deciding a cut (example: moving at quiet)
awk -F'|' '$2 ~ /moving\./ && $8 ~ /quiet/ {print $2, $7, $8, $3}' character/lines.md

# confirm a verbatim string still verifies after any edit (the header's own check)
cd character/extracts && grep -qF -- "I have heard she is quite beautiful." book7_jamal.txt && echo ok

# the prototype that makes the leg mounts ours to move (C.4 option C)
grep -n 'spider_engine' mod/jamaltron/prototypes/entity.lua
```

The two shark scales get compared in C.10's own compare mode (8 rotations beside the stock spidertron), which does not exist yet — that harness is C.10's deliverable, so the command lands with it rather than here.

**To apply the taste calls:** reply with one letter per decision — `D1 B, D2 A, D3 B, D4 B, D5 B, D6 A, D7 C, D8 wire 8.1+8.2 / cut 8.3+8.5, D9 B, D10 B` is the full set of recommendations above. Row edits go into `character/lines.md` only, no renumbering, cuts leave gaps, and every cross-reference and computed number in the header gets regenerated in the same pass.

**Then, in order:** D10's new `platform` lines (the only decision that needs writing) → regenerate `scripts/lines.lua` + `locale/en/jamaltron-lines.cfg` (they exist since 2026-09-24; every catalog edit regenerates them) → A.7 measures a real bubble and settles the two over-cap rows → playtesting → **F.6 freezes the ids**. (C.4's scale was picked off a render on 2026-09-20.)
