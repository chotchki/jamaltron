Goal: 
- Create a Factorio mod that creates a spidertron variant that is Jamal from Dungeon Crawler Carl

Character Background:
- The Jamal character details can be distilled the same way I did a different character in an earlier private project
- At a high level Jamal is a shark that came to life in the books and the characters built him a set of spiderlegs to move around on. He has numerous catch phrases that will be very well suited to being a modified spidertron.

3d Model Source:
- I bought a 3d model of a hammerhead shark to use in this project. I'm not selling this mod but I am not good at 3d modeling so I needed something to start with.
- The model is from here: https://www.renderhub.com/pig-scales-studio/animated-hammerhead-shark, I plan to give credit to the model maker in the credits.
- I fully expect we will need to render/tweak/scale/do stuff to the model to make it work in factorio.
- I think to comply with the license we should only include the renders in github.

Factorio Mods/Modding:
- I intend to upload the final assets of this mod onto github under whatever the common license for other factorio mods are.
- I'm pretty sure it will need to be written in Lua, but we can use any language we want for the tooling around it.
- The Factorio Devs, are extremely supportive of modding, https://lua-api.factorio.com/latest/

Jamaltron:
- Goal will be to inherit from the spidertron.
- If possible I want to enable it to jump, doesn't have to be far
- On jumping there should be a reasonable chance the legs break, the vehicle takes damage and jamal is left flopping around until its repaired
- Jamal is exceptionally annoying so spamming his catchphrase apologies in various situations will be key

Decisions (locked 2026-09-19):
- Target Factorio 2.1.x ONLY (`factorio_version = "2.1"`), no 2.0 backport. Base game required, Space Age optional (jumping is disabled on space platforms).
- Jamal is in books 7 and 8 only (96 and 71 mentions, zero in 1-6). Book text never enters this repo, only the distilled profile + line catalog do.
- Art: only RENDERED sprites are committed. The source model, textures and .blend stay gitignored under `assets/source/`. Credit Pig Scales Studio in README and the portal page.
- Mod license MIT (the portal default). DCC is Matt Dinniman's IP, this is non-commercial fan work: Jamal's quotes in the mod are fair use (chotchki's call), the raw book extracts NEVER land in the repo, no voice audio in v1.
- THE JUMP IS THE JOKE. Jamal is the literal personification of jumping the shark, so the jump is not a
  feature bolted onto a spidertron reskin, it is the punchline the whole mod exists to deliver. This sets the
  acceptance bar for the E.1 spike: a plain teleport CANNOT land it (nothing visibly jumps, so there is no
  shark being jumped over), which means option (b) the visible airborne arc starts ahead on narrative grounds
  before UPS or driver-control are measured. A teleport only wins if the arc proves genuinely unworkable.
  Corollaries: the arc wants to read as showy rather than efficient, the jump line pool should know it is a
  meta-joke, and the mod portal description should land it.
- Jump is scripted, spider-vehicles can't do it natively. Two candidates, a plain teleport or a swap to an airborne entity animated along an arc (the Jetpack-mod pattern), the spike in PLAN.md E.1 picks and the verdict gets recorded here.
- Legs breaking = swap to a `jamaltron-beached` entity (flop animation, can't move, still holds everything). Repair packs (or bots) at full health swap him back.
- Verbatim quote banks stay LOCAL (locked 2026-09-19). The per-book quote banks under `character/profiles/`
  are ~22KB of tabulated Dinniman dialogue - the densest verbatim surface the pipeline produces, and more than
  "only the distilled profile + line catalog" promises. They are gitignored. What ships is `character/lines.md`,
  where each line is tagged verbatim-vs-original so the fair-use surface is countable rather than vibes.
- B.4 line-catalog answers (locked 2026-09-19, chotchki):
  - `{PLAYER}` = **"Mr. Engineer"**. The Factorio player is canonically nameless so no real name works, and the
    tic in the books is the FORM (Mister/Miss + name, never dropped, applied to everyone including a pet
    dinosaur) not the name itself. The profile already maps Carl's slot onto the player's, so this is the
    intended mapping rather than a dodge. Supersedes the catalog's own *Gentlemen* recommendation.
  - ALL Dungeon Crawler Carl proper nouns are purged from `lines.md` (the file that ships into the game).
    `jamal_profile.md` and the per-book profiles are documents ABOUT the books and keep every name.
  - New `adapted` SOURCE tag: a real quote whose ADDRESSEE we changed and nothing else, with the untouched
    original recorded alongside. `verbatim` would lie to the fidelity checker, `original` would claim we wrote it.
  - TWO OUTPUT CHANNELS, not one. Jamal's SPEECH (bubble, his register, strict voice rules) and GAME NARRATION
    (third person, about him, e.g. *Jamal is silent... for once*). This resolves two separate findings at once:
    `[SILENCE]` is encoded as a narration note rather than as nothing, and the narrator-syntax lines the voice
    audit flagged (*Clack, clack, clack go Jamal's feet*, *Up goes Jamal!*) are not off-voice, they were simply
    in the WRONG CHANNEL. D.5 gets both channels, B.5 emits the channel per row.
  - `died` lines ship (they turned out to have real anchors: *Jamal would get smushed.* is verbatim).
  - Fourth wall: keep `jump.13` (literal-minded about the idiom, stays in voice), cut `jump.14` (the mod winking).
  - `{N}`, the per-entity cumulative leg-break count, SHIPS. Needs `storage`-only state, which E.6 already requires.
  - Anti-repeat gets an explicit allow-list exception for `idle.01` -> `idle.02`, the one callback gag he
    performs on himself.
  - The sincere/identity lines STAY, fixed with a ONCE-PER-ENTITY-PER-SAVE gate at their existing tiers and
    weights. Weight-1 was never a rarity mechanism - cumulative tiers made a `quiet`-tagged rare line 4x MORE
    likely at `quiet` than at `unbearable`, because it competed in a much smaller pool. A real gate makes them
    land as a moment instead of a rotation, and D.5 already needs per-entity storage for `{N}` so it is free.
  - The swear is CUT (`legs_break.33`, `flopping.42`). No profanity ships, so the portal page needs no content
    note. The maximum-misery beat falls to the next-heaviest line in the pool.
  - Anti-repeat keys on a GROUP ID (the first row carrying that exact string), per ENTITY, ACROSS pools - not
    per ID and not per pool. 50 strings live in more than one pool and `legs break` -> `flopping` fire back to
    back sharing 17 of them, which is the mod's centerpiece moment. Locale gets one key per ID, no dedup.
  - LINE CHAINING SHIPS (chotchki 2026-09-19, B.4 answer #14 - the catalog cited a ruling that did not exist).
    Nine rows are setup/punchline pairs that only parse with their partner, and GRP anti-repeat actively works
    AGAINST firing a pair. Semantics, pinned so B.5 and D.5 cannot diverge:
      * A row may name a follow-up row id in a CHAIN column. One hop only - no chains of chains, because a
        three-beat gag over a walking vehicle outlives the player's attention.
      * The follow-up fires after a per-row tick delay. It is ONE utterance in two beats, so it is EXEMPT from
        anti-repeat, from the GRP suppression window and from the say-cooldown - those gate new utterances, and
        the punchline is not one.
      * A row that exists ONLY as a chain target is NOT independently rollable. Mark it so the picker excludes
        it, or the punchline fires alone and reads as nonsense. This is the failure the whole mechanism exists
        to prevent.
      * The follow-up inherits the HEAD's tier. It must never be gated at a verbosity the head already passed,
        or the setup fires and the punchline is silently dropped.
      * CANCEL the pending follow-up if the entity dies, is swapped (D.4, including the beached swap), or is
        mined before it fires. A punchline delivered by a corpse is a bug, not a joke.
      * Pending chains live in the same per-entity `storage` table as `{N}` and the once_per_save fired-set,
        which E.6 already requires for multiplayer sync.
  - The two over-60-char lines stay flagged and UNTRIMMED until chotchki measures a real speech bubble at A.7.
  - `attacking` friendly-fire subpool stays gated pending what the API can cheaply detect (D.5/D.7).
- C.1 LICENSE GATE RESOLVED 2026-09-19 from the authoritative agreement text (chotchki supplied it; the model is
  sold under RenderHub's EXTENDED USE LICENSE). Verdict: SHIPPING RENDERS IS PERMITTED, ONE FIX REQUIRED.
  - Permitted: Sec V.2.d lists "Computer games and software" as a permitted use and V.2.c allows both commercial
    and non-commercial. Sec III.2 grants the right to "adapt... create derivative works" within Creations, and
    Sec II defines a Creation as "any work created by you". Sec IV.5.a/b allow redistribution exactly when the
    asset "becomes part of a larger Creation" - baked-in sprite sheets are. Keeping the .blend/.fbx/.dae/textures
    out of the repo already satisfies the no-redistributing-the-asset-itself rule.
  - THE FIX, and it is about OUR license not theirs: a blanket MIT over the repo would purport to grant everyone
    unrestricted reuse of the sprite sheets, including extracting them as standalone assets. Sec IV.5.a permits a
    third party to receive the asset ONLY in the form of a Creation, so that is a grant chotchki does not hold.
    SPLIT THE LICENSING: MIT covers the CODE (Lua, python, tooling); the rendered sprites ship under a separate
    asset notice - derived from a 3D model licensed from Pig Scales Studio via RenderHub, redistributable as part
    of this mod, NOT as standalone assets. Standard practice for game mods carrying licensed art.
  - Credit format is specified by Sec IV.4: "[product type] copyright [Seller name] via RenderHub" ->
    "3D model copyright Pig Scales Studio via RenderHub". Strictly that clause binds EDITORIAL use and ours is
    not editorial, but chotchki wants the credit anyway so use their exact format.
  - Sec IV.5.c (no "competitive" distribution) RESOLVED by chotchki 2026-09-19: not competing, because we ship
    ONLY sprite sheet renders. The clause's own test is whether distribution "displaces the market for the
    original Digital Asset", and 64 rotations of flattened 2D frames with baked lighting at a fixed camera and
    Factorio's scale is not a substitute for a rigged, animated, textured model - a person who wants the shark
    cannot obtain it from our sprites. The mod portal is also not a 3D-content marketplace or a stock-media
    clearinghouse, which are the two examples the clause actually names. CLOSED, do not re-litigate.
  - Housekeeping: confirm the product is NOT flagged "Editorial Use Only" (Sec IV.1 would then forbid commercial
    use entirely); chotchki 2026-09-19 on the Sec VI.2 payment-reversal termination: moot, it is a $10 model and
    not worth a chargeback fight, so the license simply stays live; Sec IX.1 lets RenderHub request sample copies of the end use.
  - PROVENANCE (keep, Sec IX.1 lets RenderHub request proof of the end use): RenderHub order (number on file, kept private), placed
    2026-09-19, line item "Hammerhead Shark : Extended Use License", $10.00.
    The tier is CONFIRMED from the purchase record, not inferred from the listing, which also settles the
    Editorial-Use-Only question by construction - Editorial is a different tier and Sec V.2.d of Extended Use
    lists "Computer games and software" outright.
  - Sec IX.12 says the Agreement version live AT PURCHASE governs. Purchase and the agreement text used for this
    analysis are both 2026-09-19, so there is no version-drift ambiguity.
  - The receipt/invoice stays OUT of this repo - it carries a name and partial card number. Keep it in email or
    somewhere private; nothing in `assets/source/` either, since that directory exists to be gitignored, not to
    be a document safe.
  - NOT LEGAL ADVICE. This is a careful read of the controlling text, not counsel.
- Annoyance is a per-player setting (quiet / normal / unbearable) so multiplayer friends can opt out of Jamal.
