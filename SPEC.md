Goal:
- Create a Factorio mod that creates a spidertron variant that is Jamal from Dungeon Crawler Carl

Character Background:
- The Jamal character details can be distilled the same way I did a different character in an earlier private project
- At a high level Jamal is a shark that came to life in the books and the characters built him a set of spider legs to move around on. He has numerous catch phrases that will be very well suited to being a modified spidertron.

3D Model Source:
- I bought a 3D model of a hammerhead shark to use in this project. I'm not selling this mod but I am not good at 3D modeling so I needed something to start with.
- The model is from here: https://www.renderhub.com/pig-scales-studio/animated-hammerhead-shark, I plan to give credit to the model maker in the credits.
- I fully expect we will need to render/tweak/scale/do stuff to the model to make it work in Factorio.
- I think to comply with the license we should only include the renders in GitHub.

Factorio Mods/Modding:
- I intend to upload the final assets of this mod onto GitHub under whatever the common license for other Factorio mods are.
- I'm pretty sure it will need to be written in Lua, but we can use any language we want for the tooling around it.
- The Factorio devs are extremely supportive of modding, https://lua-api.factorio.com/latest/

Jamaltron:
- Goal will be to inherit from the spidertron.
- If possible I want to enable it to jump, doesn't have to be far
- On jumping there should be a reasonable chance the legs break, the vehicle takes damage and Jamal is left flopping around until it's repaired
- Jamal is exceptionally annoying so spamming his catchphrase apologies in various situations will be key

Decisions (locked 2026-09-19 unless dated otherwise):
- Target Factorio 2.1.x ONLY (`factorio_version = "2.1"`), no 2.0 backport. Base game required, Space Age optional
  (jumping is disabled on space platforms).
- Jamal is in books 7 and 8 only (96 and 71 mentions, zero in 1-6). Book text (raw extracts included) NEVER enters this repo, only the distilled profile + line catalog
  do. DCC is Matt Dinniman's IP and this is non-commercial fan work: Jamal's quotes in the mod are fair use
  (chotchki's call), no voice audio in v1.
- Art: only RENDERED sprites are committed. The source model, textures and .blend stay gitignored under
  `assets/source/`. Credit Pig Scales Studio in README and the portal page (format under C.1 below).
- Mod license: MIT for the CODE only (amended 2026-09-20, was a blanket MIT). `mod/jamaltron/graphics/LICENSE` carves
  the sprites out: redistributable as part of this mod, never as standalone art. Why: the RenderHub Extended Use
  License grants no sublicense (Sec III.2 has no SUBLICENSE verb, Sec III.1 reserves every unenumerated right,
  transfers are barred), while MIT purports to grant recipients the right to "sublicense, and/or sell copies".
  chotchki can't pass on rights he was never given, so a blanket MIT over the sprites is a material BREACH that
  terminates the model license under Sec VI.2, and it separately manufactures the Sec IV competition problem by
  making an MIT-labelled PNG folder read as stock art offered for reuse. The gate is the FIRST sprite commit, not the
  public push: git history is permanent and forks survive a takedown, so a sprite committed under blanket MIT can't
  be un-granted later.
- The jump is scripted, spider-vehicles can't jump natively. Two candidates: (a) a plain teleport or (b) a swap to an
  airborne entity animated along an arc (the Jetpack-mod pattern). The spike in PLAN.md E.1 picks and the verdict
  gets recorded here.
- The jump IS the joke. Jamal is the literal personification of jumping the shark, so the jump is the punchline the
  whole mod exists to deliver, not a feature bolted onto a spidertron reskin. That sets E.1's acceptance bar: a plain
  teleport CANNOT land it (nothing visibly jumps, so no shark gets jumped over), so (b), the visible airborne arc,
  starts ahead on narrative grounds before UPS or driver control are measured. A teleport only wins if the arc proves
  genuinely unworkable. Corollaries: the arc should read showy rather than efficient, the jump line pool should know
  it's a meta-joke and the mod portal description should land it.
- Legs breaking = swap to a `jamaltron-beached` entity (flop animation, can't move, still holds everything). Repair
  packs (or bots) at full health swap him back.
- Verbatim quote banks stay LOCAL. The per-book quote banks under `character/profiles/` are ~22KB
  of tabulated Dinniman dialogue, the densest verbatim surface the pipeline produces and more than "only the distilled
  profile + line catalog" promises, so they're gitignored. What ships is `character/lines.md`, where each line is
  tagged verbatim-vs-original so the fair-use surface is countable rather than vibes.
- B.4 line-catalog answers (locked 2026-09-19, chotchki):
  - `{PLAYER}` = "Mr. Engineer". The Factorio player is canonically nameless so no real name works, and the books'
    tic is the FORM (Mister/Miss + name, never dropped, applied to everyone including a pet dinosaur), not the name.
    The profile already maps Carl's slot onto the player's, so this is the intended mapping, not a dodge. Supersedes
    the catalog's own "Gentlemen" recommendation.
  - ALL Dungeon Crawler Carl proper nouns are purged from `lines.md` (the file that ships into the game).
    `jamal_profile.md` and the per-book profiles are documents ABOUT the books and keep every name.
  - New `adapted` SOURCE tag: a real quote whose ADDRESSEE we changed and nothing else, with the untouched original
    recorded alongside. `verbatim` would lie to the fidelity checker, `original` would claim we wrote it.
  - Two output channels, not one: Jamal's SPEECH (bubble, his register, strict voice rules) and game NARRATION (third
    person, about him, e.g. "Jamal is silent... for once"). This resolves two findings: `[SILENCE]` is encoded as a
    narration note rather than as nothing, and the narrator-syntax lines the voice audit flagged ("Clack, clack, clack
    go Jamal's feet", "Up goes Jamal!") aren't off-voice, they were in the WRONG channel. D.5 gets both channels, B.5
    emits the channel per row.
  - `died` lines ship (they have real anchors: "Jamal would get smushed." is verbatim).
  - Fourth wall: keep `jump.13` (literal-minded about the idiom, stays in voice), cut `jump.14` (the mod winking).
  - `{N}`, the per-entity cumulative leg-break count, SHIPS. Needs `storage`-only state, which E.6 already requires.
  - Anti-repeat gets an explicit allow-list exception for `idle.01` -> `idle.02`, the one callback gag he performs on
    himself.
  - The sincere/identity lines STAY, behind a once-per-entity-per-save gate at their existing tiers and weights.
    Weight-1 was never a rarity mechanism: cumulative tiers made a `quiet`-tagged rare line 4x MORE likely at `quiet`
    than at `unbearable`, because it competed in a much smaller pool. A real gate lands them as a moment instead of a
    rotation, and it's free since D.5 already needs per-entity storage for `{N}`.
  - The swear is CUT (`legs_break.33`, `flopping.42`). No profanity ships, so the portal page needs no content note;
    the maximum-misery beat falls to the next-heaviest line in the pool.
  - Anti-repeat keys on a GROUP id (the first row carrying that exact string), per entity, ACROSS pools - not per id
    and not per pool. 50 strings live in more than one pool, and `legs break` -> `flopping` (the mod's centerpiece
    moment) fire back to back sharing 17 of them. Locale gets one key per id, no dedup.
  - Line chaining SHIPS (chotchki 2026-09-19, B.4 answer #14 - the catalog cited a ruling that did not exist). Nine
    rows are setup/punchline pairs that only parse with their partner, and GRP anti-repeat actively works AGAINST
    firing a pair. Semantics, pinned so B.5 and D.5 can't diverge:
      * A row may name a follow-up row id in a CHAIN column. One hop only (no chains of chains: a three-beat gag over
        a walking vehicle outlives the player's attention).
      * The follow-up fires after a per-row tick delay. It's one utterance in two beats, so it's EXEMPT from
        anti-repeat, the GRP suppression window and the say-cooldown (those gate new utterances, and the punchline
        isn't one).
      * A row that exists ONLY as a chain target is NOT independently rollable: mark it so the picker excludes it,
        or the punchline fires alone and reads as nonsense (the failure the whole mechanism exists to prevent).
      * The follow-up inherits the HEAD's tier. It must never be gated at a verbosity the head already passed, or
        the setup fires and the punchline is silently dropped.
      * CANCEL the pending follow-up if the entity dies, is swapped (D.4, including the beached swap) or is mined
        before it fires (a punchline delivered by a corpse is a bug).
      * Pending chains live in the same per-entity `storage` table as `{N}` and the once_per_save fired-set, which
        E.6 already requires for multiplayer sync.
  - The two over-60-char lines stay flagged and UNTRIMMED until chotchki measures a real speech bubble at A.7.
  - `attacking` friendly-fire subpool stays gated pending what the API can cheaply detect (D.5/D.7).
- C.1 license gate RESOLVED 2026-09-19 from the authoritative agreement text (chotchki supplied it; the model is sold
  under RenderHub's Extended Use License). Verdict: shipping renders is PERMITTED, one fix required. NOT legal advice,
  just a careful read of the controlling text.
  - Permitted: Sec V.2.d lists "Computer games and software" as a permitted use and V.2.c allows both commercial and
    non-commercial. Sec III.2 grants the right to "adapt... create derivative works" within Creations, and Sec II
    defines a Creation as "any work created by you". Sec IV.5.a/b allow redistribution exactly when the asset
    "becomes part of a larger Creation" - baked-in sprite sheets are. Keeping the .blend/.fbx/.dae/textures out of
    the repo already satisfies the no-redistributing-the-asset-itself rule.
  - The fix is to OUR license, not theirs: a blanket MIT would purport to grant everyone unrestricted reuse of the
    sprite sheets, including extracting them as standalone assets, but Sec IV.5.a lets a third party receive the
    asset ONLY in the form of a Creation, so that's a grant chotchki doesn't hold. Hence the split under Mod license
    above: MIT covers the code (Lua, Python, tooling), the rendered sprites ship under a separate asset notice
    (derived from a 3D model licensed from Pig Scales Studio via RenderHub, redistributable as part of this mod, NOT
    as standalone assets). Standard practice for game mods carrying licensed art.
  - Credit format is specified by Sec IV.4: "[product type] copyright [Seller name] via RenderHub" -> "3D model
    copyright Pig Scales Studio via RenderHub". Strictly that clause binds EDITORIAL use and ours isn't editorial,
    but chotchki wants the credit anyway, so use their exact format.
  - Sec IV.5.c (no "competitive" distribution) RESOLVED by chotchki 2026-09-19: not competing, because we ship ONLY
    sprite sheet renders. The clause's own test is whether distribution "displaces the market for the original
    Digital Asset", and 64 rotations of flattened 2D frames with baked lighting at a fixed camera and Factorio's scale
    are no substitute for a rigged, animated, textured model - a person who wants the shark can't get it from our
    sprites. The mod portal also isn't a 3D-content marketplace or a stock-media clearinghouse, the two examples the
    clause actually names. CLOSED, do not re-litigate.
  - PROVENANCE (keep, Sec IX.1 lets RenderHub request sample copies of the end use): RenderHub order (number on file,
    kept private), placed 2026-09-19, line item "Hammerhead Shark : Extended Use License", $10.00. The tier is
    CONFIRMED from the purchase record, not inferred from the listing, which settles the Editorial-Use-Only question
    by construction: Editorial is a different tier (under it Sec IV.1 would forbid commercial use entirely), and Sec
    V.2.d of Extended Use lists "Computer games and software" outright.
  - Sec VI.2 payment-reversal termination: moot (chotchki 2026-09-19), it's a $10 model and not worth a chargeback
    fight, so the license simply stays live.
  - Sec IX.12 says the Agreement version live AT PURCHASE governs. Purchase and the agreement text used for this
    analysis are both 2026-09-19, so there's no version-drift ambiguity.
  - The receipt/invoice stays OUT of this repo (it carries a name and partial card number); keep it in email or
    somewhere private. Not in `assets/source/` either: that directory exists to be gitignored, not to be a document
    safe.
- The body does NOT animate while walking (locked 2026-09-20). `frame_count = 1`, 64 directions, exactly like Wube's
  own spidertron torso, whose whole sense of motion comes from its LEGS (and nobody has ever called the spidertron
  lifeless). Reasons, heaviest first:
  - CHARACTER. He's strapped into a harness: a CARRIED shark isn't swimming, he's held rigid while somebody else's
    legs do the work. A swim cycle would read as him propelling himself, exactly what he can't do and the reason the
    legs exist. He is cargo with opinions.
  - COST. The body sheet is ~25 MiB raw and the shadow the same. An 8-frame cycle multiplies BOTH by 8: ~400 MiB raw
    for one entity, ~100 MiB after Factorio's compression. That's a mod-portal complaint about load times in exchange
    for motion nobody asked for.
  - PRECEDENT. Stock ships it this way and it works.
  The animation budget goes where stillness would be WRONG: C.5's flop loop (the one moment his body must move, and
  the comedic centrepiece) and possibly the jump arc.
  UNRESOLVED (check before anyone promises it): whether `spider-vehicle` supports separate idle and moving
  animations. If it does, a subtle parked-only tail sway is cheap; if not, this choice is binary and already made.
- Annoyance is a per-player setting (quiet / normal / unbearable) so multiplayer friends can opt out of Jamal.
