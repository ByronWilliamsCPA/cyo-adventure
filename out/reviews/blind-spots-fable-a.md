# Blind-Spot Review: Five Passed Books (Fable pass A)

Reviewer: Claude (Fable 5), 2026-08-14.
Method: each book read as a branching experience, following every path from `start_node` to every ending,
tracking objects, characters, promises, and physical state across branches, then diffing what a child would
track against what the text delivers. Everything below is outside the 40 deterministic rules, the 7 judge
criteria, and the deterministic prose measures as described in the review brief. Where a finding extends a
declared blind spot (`information_state` in particular), that is said explicitly.

Priority order: F1 to F5 are the findings I would fix first; F6 to F12 are real but lower stakes.

---

## F1. Merge nodes assert state that was never established on the path taken (pattern, all four multi-branch books)

The strongest systemic defect in the set. Every book declares `variables: []`, all branches re-merge into
shared nodes, and the shared prose was written with one incoming branch in mind. The condition evaluator
exists in the platform but none of these books use it, so nothing forces merge-node prose to be
history-neutral.

**Flagship case: the wish that was never written (the-night-market).** From `f_steps` the reader picks
exactly one of three finale lanes: `f_paper` (write the wish), `f_lantern` (dress the lantern), or
`f_friends` (gather a crowd). The lanes never rejoin each other before the endings:

- Path `f_steps -> f_lantern -> f_string -> f_flame -> e_light_*`: the wish is never whispered, never
  written, never folded. Yet `f_string` says "Now the folded wish could hang underneath, like the clapper
  of a tiny bell," and the lantern launches. The entire premise of the book is Pip's wish; on this path a
  wishless lantern goes up and the text pretends otherwise.
- Path `f_steps -> f_friends -> f_circle -> f_countdown -> e_up_chorus`: neither the wish nor the lantern
  prep ever happens (no string tied, no flame set), yet `f_countdown` opens with "The lantern glowed in
  Pip's paws" and `e_up_chorus` says the lantern "climbed past the rooftops with the folded wish swinging
  gently below." A folded wish that no one wrote, hanging from a string no one tied, lit by a flame no one
  set.
- Conversely, only the `f_paper` lane compresses the missing steps honestly (`e_wish_pip`: "They folded it
  and tied it under the lantern. They set the flame.").

**The phantom lantern frame (the-night-market).** In `n_meet` Pip lists everything she lost: "I had a
basket. My wish paper was in it, and my golden string, and my candle. Everything I need for the ceremony."
No lantern frame is lost, and none is carried. The spares table at `f_steps` holds "spare wish paper. And
coils of golden string. And little flames in tins," and no frames. Yet `tm_gift` has Mr. Fez repair "Pip's
lantern frame" (a frame she should not have with her), and `f_lantern` opens "Milo settled the lantern
frame across his knees" with a definite article and no source on any path that skipped the toy mender.

**The teleporting acorn (baking-day-with-grandma-vole, `n_seeds_ok`).** "The shiny acorn was safe in
Grandma Vole's pocket." On the direct path (`n_seeds -> n_seeds_ok`) the acorn was last "On top" of the
seed jar; on the retry path (`n_acorn_chase -> n_acorn_back -> n_seeds -> n_seeds_ok`) it was last held
high in Pip's paws. Neither path ever shows it being pocketed. The line is written as if a scene existed
that is in no branch.

**The unowned moonbeam and the unearned "not wobbly" (the-sleepy-little-star).** `n_almost` is the merge
point of all three opening strategies, and its second choice reads "Hold a silvery moonbeam and shine all
at once." A moonbeam exists only on the `n_slide` branch; a reader arriving via the cloud (`n_peek`) or
sway (`n_sway`) branches is handed a definite object from a branch they never saw. Similarly
`n_first_sparkle` celebrates "It was not wobbly at all!" when wobbliness was established only on the wiggle
branch (`n_wiggle`: "Her light blinked like a hiccup"); via the cloud branch this answers a worry never
raised, and via `n_peek` it repeats a sparkle she already released ("My light reached somebody!").

**Why nothing catches it.** L1/L2 rules verify graph shape, not graph semantics. CG-1..4 check only that
the landed passage answers the choice just clicked, one hop back. RL/PL are per-node. The judge criteria
have no continuity dimension, and a judge shown the whole book reads it as a flat document where the wish
does get written (in a different lane). This concretely *extends* the declared `information_state` blind
spot: that label suggests reader-vs-character knowledge, but what fails here is author-vs-graph object
bookkeeping across merges, which is checkable.

**One-off or pattern.** Pattern: four separate instances in three books, plus F4's variant.

**Proposal (deterministic check).** A merge-node state lint: for every node with in-degree > 1 (and every
node whose incoming paths differ in visited-node sets), extract definite/possessive noun phrases and
prior-event references ("the folded wish", "her moonbeam", "Pip's lantern frame", "safe in X's pocket");
flag any referent whose introducing node does not dominate the merge node (i.e., is absent from at least
one incoming path). This is a graph-dominator computation plus NP extraction, no LLM needed for the graph
half; an LLM pass can do referent extraction with high recall. Secondary fix: authoring-guide rule that a
skeleton whose lanes are mutually exclusive must either gate merge prose on `variables` or keep merge prose
strictly history-neutral.

---

## F2. The setback endings quietly erase the story's central promised event (the-night-market)

The book's stake is set in `n_start`: "the best part came last, when everybody let their wish lanterns go,"
and Pip's whole problem is being ready for that ceremony. All four mishap endings (`e_ds_spill`,
`e_tc_slosh`, `e_tm_spring`, `e_mc_gong`) end the night before the ceremony with no mention of it at all:
`e_ds_spill` says "the clean-up took the whole rest of the night. 'Home time,' said Ada at last," and Pip
walks home planning "next market night."

Three distinct problems:

1. The ceremony was a fixed public event happening that night. Dozens of other lanterns went up while they
   swept dumplings; the text never shows or mentions it. A child tracking Pip's goal will ask "but did the
   lanterns go up? Did Pip at least watch?" The story has no answer; the event just vanishes.
2. It contradicts the book's own stated ethos. `f_steps` (a node these paths never reach, but the same
   world): "At the night market, nobody shy or late is ever left out," with spare paper, string, and flames
   waiting. A spilled tray does not explain why a market this generous lets Pip miss the ceremony entirely.
3. The consequence is misattributed: Milo's mishap (his tray stack, his gong whack) costs *Pip* the thing
   she was crying about at the gate, and no ending acknowledges that transfer. Pip is shown cheerfully
   waving; her established emotional stake is overwritten rather than resolved.

**Why nothing catches it.** `ending_quality` scores each ending's local satisfaction, and these endings are
locally warm and well-written. PL's ending-kind mix only counts kinds. Fork consequence distance measures
where consequences land, not whether the story's declared goal is resolved or even acknowledged. No rule
represents "the stake announced in the opening" as an object that endings must address.

**One-off or pattern.** Pattern within this book (all four setback endings share it), and it is the same
defect family as F4 in puddle-jumping-day: a stake the child is tracking is dropped by a branch.

**Proposal (judge criterion).** New criterion `stake_resolution`: "Does every ending resolve, or explicitly
acknowledge, the goal and any character-in-need established before the first fork?" Anchor 1: "At least one
ending never mentions the story's announced goal or an established character-in-need again; the reader is
left not knowing what happened to it." Anchor 5: "Every ending, including setbacks, tells the reader what
became of the announced goal and of anyone the protagonist promised to help, even if the outcome is a
loss." Run it per-ending against the pre-fork nodes, not against the whole book.

---

## F3. The escort character vanishes for the entire second act (the-night-market)

Ada, Milo's cousin and his companion for the night, is present in `n_start` ("said Milo's cousin Ada") and
`n_promise` ("The three of them walked into the lantern square"). She then appears in zero of the hub,
stall, or finale nodes: not in `n_hub`, not at any of the six stalls, not at the ceremony steps, not in any
of the nine positive endings, including the crowd scenes (`f_friends` gathers "every keeper who had waved
at them," `f_circle` lists "Aprons and spectacles and one drum"; no Ada). She rematerializes only in the
four setback endings as the authority who calls "home time."

For a 5-8 reader this is a real question ("where did Ada go?"), and for a guardian it is slightly worse:
the accompanying older relative is absent while two small characters roam a night market, handle kettles,
climb onto a stranger's shoulders (`pf_last`), and light flames.

**Why nothing catches it.** CH-1..8 evidently do not track presence-persistence of a named companion across
paths (the book passed). Judges have no criterion for cast continuity, and `voice` is about the main
character only.

**One-off or pattern.** One clear instance in this set, but it is structural: open-map hubs with many
lanes make companion-tracking failures likely in exactly this shape.

**Proposal (deterministic check).** Named-character presence tracking: any character co-located with the
protagonist at a node (introduced as accompanying) must, on every path, either be mentioned again within N
nodes or be explicitly parked ("Ada waved them off toward the stalls"). Flag characters whose last mention
precedes more than N consecutive nodes of protagonist action on any path, and especially characters who
appear in some endings but not others of the same book.

---

## F4. A creature in distress is abandoned by one branch and never mentioned again (puddle-jumping-day)

`n_wiggle` establishes a stake with real urgency for the age band: "It was a little earthworm. It wiggled
on the hard wet path, far from any soft dirt." Grandma then frames a fork: "Help the worm home? Or go look
in that big puddle?" Choosing `c_mirror` leads to `n_mirror -> n_mirror_climax -> n_splash_end`, and the
worm is never mentioned again in any of those three nodes. The child who noticed the worm was in trouble
(the text made sure they noticed) jumps in a puddle while it presumably dries out on the path, and the
adult character presented that as an equal, consequence-free fun option.

This is not a hypothetical sensitivity: 3-5 read-aloud audiences reliably fixate on the small animal. The
branch does not need to be removed; it needs one clause ("They tiptoed around the little worm's path" or a
returning "and on the way home they checked the worm had wiggled off").

**Why nothing catches it.** `choice_quality` asks whether the fork feels like a real decision (it does).
Safety rules look for harm depicted, not care omitted. CG-4 confirms `n_mirror` answers "tiptoe to the
puddle," which it does. Nothing represents "entity in need introduced pre-fork" as a thread every branch
must close. Same family as F2.

**One-off or pattern.** One-off in this set as an animal-welfare instance, but it is the pre-fork-stake
variant of F2's pattern, and the proposed `stake_resolution` criterion (F2) covers both if its anchor text
includes characters-in-need, as written above. Additionally an authoring-guide rule: "If a character or
creature in need appears before a fork, every branch from that fork must resolve or acknowledge it."

---

## F5. The balloon obeys different physics in different branches, and its rescue objects mutate (the-big-red-balloon)

Three concrete contradictions, all invisible to per-node checks:

1. **Buoyancy flips to whatever the plot needs.** When freed at `n_gust`, the balloon behaves like a helium
   balloon: "The big red balloon sailed up and away. It grew smaller and smaller." When freed at
   `n_breeze`, the same balloon in the same weather descends: `n_drift`: "The big red balloon drifted
   down. It landed softly on the water." Both nodes describe the identical event (string slips free,
   balloon unheld). A literal-minded child who reads both branches, which the app encourages, sees the
   same object fall up in one chapter and fall down in another.
2. **The string's snag migrates within a single path.** `n_ducks`: "the string got caught. It caught in
   green reeds." `n_reeds` confirms it is stuck in the reeds. Two nodes later on the same path, `n_willow`:
   "The string looped around a bendy twig. It was just too high," now high in the willow above Lila's head.
   Reeds are at water level; the snag moved ten feet up between passages with no gust or event in between.
3. **Row vs pedal.** The `n_reeds` choice label says "Wave to the paddle-boat lady"; `n_boat` says she
   "rowed to the bank"; `n_pedal` says "They pedaled and pedaled"; `n_boat_end` says "They rowed back to
   shore." One boat, two mutually exclusive propulsion systems, alternating by sentence.

**Why nothing catches it.** FK, word ceilings, sensory density, and tense stability are all satisfied by
each node individually. CG-4 passes because each landing answers its choice. The judge panel has `imagery`
(concreteness, which these nodes have in abundance) but no criterion for cross-node object consistency, and
`age_fit` does not penalize physical incoherence.

**One-off or pattern.** Pattern within this book (three instances); the mechanism (object state re-invented
per node) is the prose-level sibling of F1's graph-level problem.

**Proposal (judge criterion).** New criterion `object_continuity`: "Pick the story's focal objects. Across
all nodes, does each object keep consistent physical properties, location, and behavior unless an event
changes them?" Anchor 1: "A focal object contradicts itself between nodes a reader can visit in one
sitting (rises in one branch, sinks in another; is stuck low in one node and high in the next), with no
in-story cause." Anchor 5: "Every focal object's position and behavior can be traced node to node on every
path without contradiction." Judges should receive the story as paths, not as a node list, for this
criterion.

---

## F6. Revisitable nodes replay verbatim text that contradicts accumulated story state (pattern: all three loop/open-map books)

The gate checks reachability, orphans, and depth budget, but `loop_and_grow` and `open_map` topologies are
built on cycles, and re-entering a node replays its body unchanged:

- **the-night-market, `n_hub`**: every return to the hub replays "Pip stayed close to Milo's leg. 'Where
  now?' she whispered." A reader can arrive here immediately after `mc_gift` made Pip an "Official member
  of the band" who hummed "again, stronger," or after `tc_gift` put a warm candle-tin in her paws; the hub
  resets her to the shy whisperer from the gate. Pip's courage arc, the book's spine, is undone on every
  loop. Likewise `ds_entry` replays Auntie Mo shouting "Four more hands!" even after the reader already
  delivered every tray and collected her thank-you.
- **baking-day-with-grandma-vole**: the retry loops (`n_bowl_oops -> n_bowls`, `n_flour_oops -> n_flour`,
  `n_acorn_back -> n_seeds`, `n_peek_oops -> n_oven`) are infinitely repeatable with byte-identical text.
  A child can slide the bowl stack out five times and Grandma Vole "just chuckled" identically each time,
  after having already said "One at a time, little paws." Nothing escalates, nothing remembers, and there
  is no cap.
- **the-sleepy-little-star, `n_ready`**: returning via `c_slide_climb` ("Climb the silvery moonbeam back
  up") replays the full three-way menu including "Scoot down to peek at the world below," the exact action
  whose failure the reader just climbed back from, offered in identical words with no acknowledgement.

**Why nothing catches it.** L1-1..8 treat a cycle as legal topology; the walk validator confirms paths
terminate; per-node checks see each body once. The judge panel reads nodes once and never experiences a
revisit. `engagement` could in principle notice, but judges are not shown loop traversals.

**One-off or pattern.** Pattern: every non-linear book in the set.

**Proposal (deterministic check + authoring rule).** (a) Flag any node reachable from itself whose body
contains character-emotion or first-time assertions (whisper/shy/first/new, greeting lines, requests for
help already fulfilled on some incoming path); require either variable-gated variant text or state-neutral
hub prose. (b) For failure-retry loops, require the loop either be bounded (second failure routes to a
gentle variant or onward) or that the retry node's text acknowledge repetition. This is cheap: cycle
detection plus a lexicon pass.

---

## F7. A choice label promises sequencing the branch does not honor (the-night-market, `c_fsteps_friends`)

The label reads "Gather the stall friends around Pip **first**." "First" tells the reader the other two
tasks (wish, lantern) come after. The branch is irreversible: `f_friends -> f_circle -> f_countdown ->
launch endings`, with no wish-writing and no lantern prep ever occurring (see F1). The child who picked the
generous option believing they would still get to do the wish is taken straight to launch.

**Why nothing catches it.** CG-4 checks the landed passage answers the choice (it does: friends gather).
No rule parses sequencing adverbs in labels against actual reachability of the implied later steps.

**One-off or pattern.** One instance here, but trivially recurrent wherever labels use "first/before/then."

**Proposal (deterministic check).** Lint choice labels for sequencing adverbs ("first", "before", "then",
"start by"); if present, require that the sibling choices' target subtrees remain reachable from the chosen
branch, else fail. Pure graph reachability plus a word list.

---

## F8. Imitable hazard acts are modeled with comic, consequence-free outcomes (baking-day, the-night-market)

- **baking-day-with-grandma-vole, `n_peek_oops` / `n_funny_peek`**: the child character opens a hot oven
  door on his own initiative, twice, in both oven branches. The depicted consequence is that buns slump or
  whiskers curl "into silly squiggles," and Grandma laughs. The realistic hazard (a face-height rush of
  oven-hot air at toddler height) is not merely softened, it is affirmatively framed as a giggle with zero
  cost. For the 3-5 band, "open the oven for a tiny peek" is a directly imitable act presented as an
  appealing choice option, and the punishment is that pastry deflates.
- **the-night-market, `e_light_pip`**: the celebrated brave option is the small child-analog handling open
  flame solo: "Pip touched the flame to the wick all by herself. Her paws did not shake once," crowd
  cheers. Supervision exists nearby, which mitigates it, but the emotional payoff structure is: solo flame
  handling = courage = applause.

**Why nothing catches it.** The safety validator and `content_flags` measure depicted violence, scariness,
and peril, and there is none: nobody is hurt, nothing is frightening. That is exactly the problem: the
classic children's-media "imitable dangerous acts" standard (broadcast S&P style) is about acts a child can
copy whose real consequences are absent from the text, which is orthogonal to depicted peril. `age_fit`
judges suitability of content, and cozy baking reads as maximally suitable.

**One-off or pattern.** Pattern: three nodes across two books, all hot-surface/open-flame.

**Proposal (deterministic check routed to human review).** Keyword+agent check: {oven, stove, kettle,
flame, candle, match, taper, boiling} within a node where the child-protagonist (not an adult) is the verb
agent of {open, touch, light, grab, reach}; flag for the human reviewer with a standard question ("is the
real consequence of this act visible or is it comically absent?"). Not a block; a surfaced review item.

---

## F9. Releasing objects into nature is framed as celebration (the-big-red-balloon, the-night-market)

- **the-big-red-balloon, `e_duck_parade`**: the balloon is permanently abandoned floating on a wildlife
  pond, string trailing, ducks circling it, and the text frames this as a gift: "Her balloon led the parade
  now. What a happy trade." (No trade occurred; she simply lost it.) In the real world, balloon debris and
  trailing string in a duck pond are ingestion and entanglement hazards; the book teaches that leaving one
  there is what makes ducks happy.
- **the-night-market**: the centerpiece is a mass sky-lantern release, an actual real-world practice that
  is a documented fire and wildlife-litter hazard and banned in many jurisdictions. Rendered as fantasy it
  is defensible; rendered this warmly, with children lighting and releasing, some guardians will want to
  know before their child asks to do it.

**Why nothing catches it.** Content flags cover violence/scariness/peril. There is no taxonomy slot for
real-world-practice modeling, so a guardian filtering the library has no signal.

**One-off or pattern.** Two books of five.

**Proposal (taxonomy extension, not a gate).** Add guardian-facing content descriptors alongside
`content_flags`, e.g. `real_world_practices: ["object release outdoors", "open flame ceremony"]`, populated
by a cheap classifier pass and shown in the guardian console. Do not block; inform.

---

## F10. Protagonist names collide across the catalog: two Milos and two Pips in five books

- **Milo**: protagonist of puddle-jumping-day (a boy with a Grandma) and of the-night-market (a boy with a
  cousin Ada). Adjacent bands (3-5 and 5-8): the same child will meet both Milos within a year or two, and
  likely in the same library view.
- **Pip**: protagonist of baking-day-with-grandma-vole (a young vole, male: "He ran down the root tunnel")
  and the deuteragonist of the-night-market (a pangolin, female: "she whispered").

A five-book sample already contains two collisions, including one where the same name switches species and
gender between books. Children in this age range treat names as identities; "why is Pip a girl pangolin
now?" is a guaranteed question, and it degrades the persistent-characters feature the platform advertises
(`characters/` progression and seeding exist precisely because kids track characters).

**Why nothing catches it.** CH-1..8 are per-book. The shared four-gram convergence check is prose-level
and a name is one token. The diversity metrics are structural/lexical similarity, not onomastic identity.

**One-off or pattern.** Pattern, and at 2 collisions per 5 books the collision rate at catalog scale will
be severe, since fills evidently draw from the same small pool of cozy names (Milo, Pip, Lila, Jo).

**Proposal (deterministic check).** Catalog-level name registry: at validation time, compare each new
book's named-character list against published books in the same and adjacent bands; block protagonist-name
reuse outright, warn on secondary-character reuse unless the book is a declared series entry sharing the
same character record. Trivial to implement; also feed the registry into generation prompts as a
"names in use" exclusion list.

---

## F11. Within-path verbatim repetition and a dangling pronoun (the-big-red-balloon)

On the single path `n_pond -> n_ducks -> n_reeds -> n_boat`, the sentence "It was soft and muddy" appears
twice within three passages: `n_ducks`: "Lila and Grandpa hurried along the bank. It was soft and muddy."
and `n_boat`: "The boat lady rowed to the bank. It was soft and muddy." In the second occurrence the
nearest referent for "It" is the boat lady's action or the boat, so the read-aloud parse is briefly "the
boat was soft and muddy." A copied sentence with a broken antecedent, on one contiguous reading path.

**Why nothing catches it.** The four-gram convergence measure is *between* books; all other prose measures
are per-node. Nothing measures n-gram repetition along a single reading path within one book, and nothing
checks pronoun antecedents.

**One-off or pattern.** The verbatim-repeat is one clear instance; smaller echoes exist ("quacked with joy"
in `n_catch_end` and `n_boat_end`, different paths so harmless). Related one-off in the same family:
the-sleepy-little-star `n_moon`, "She squeezed her two points tight," gives the star a two-pointed body
that no illustration or later text supports (`n_giggle_retry` has plural unspecified "points"); confusing
body-image for a read-aloud listener.

**Proposal (deterministic check).** Extend the existing four-gram machinery to run within-book, scoped per
path: flag any 4+-gram repeated within a window of K consecutive nodes on any single path. Add a light
pronoun-lint: sentence-initial "It was/is" immediately following a sentence whose subject is animate gets
flagged for author attention.

---

## F12. The negative outcome is not caused by the choice that precedes it (the-big-red-balloon, `n_stool` -> `n_gust`)

At `n_umbrella` the child chooses between "Ask the ice-cream man to reach it" (leads to full success plus
ice cream, `n_sundae_end`) and "Climb a little step stool and try" (Grandpa holding her, i.e., depicted as
safe). On the stool path, the loss is caused by a random wind gust ("Just then, wind swept by"), not by
anything about the choice: the same gust could as easily have arrived while the ice-cream man unwound the
string loop by loop. Contrast baking-day, where every mishap is causally earned (shake the jar, seeds fly).
Here the implicit lesson is "trying it yourself brings bad luck; asking an adult brings treats," delivered
by coin-flip rather than consequence. The label also carries no risk signal at all, so the child cannot
have chosen the risk knowingly.

**Why nothing catches it.** Fork consequence distance measures *where* consequences land, not whether they
are caused by the choice. `choice_quality` asks if the fork feels like a real decision at the moment of
choosing, not whether the outcome is causally fair in hindsight. `ending_quality` finds
`e_strawberry_goodbye` genuinely satisfying as a gentle-loss ending, which locally it is.

**One-off or pattern.** One-off in this set (the night-market setbacks are all causally earned; baking-day
is exemplary here).

**Proposal (judge criterion, or fold into choice_quality's rubric).** `consequence_causality`: "For each
branch with a materially worse outcome than its sibling, is the worse outcome caused by the chosen action
itself?" Anchor 1: "A negative outcome follows a choice but is triggered by an unrelated random event that
could equally have occurred on the sibling branch." Anchor 5: "Every negative outcome traces directly to a
property of the chosen action, and the label gave the reader enough to weigh the risk."

---

## Minor notes (recorded, not argued)

- baking-day `n_start`: "A warm, toasty smell! It came from the kitchen" before anything has been baked;
  defensible as the pre-warming stove, but the hook implies finished baking on a morning when the dough
  has not been mixed yet. Marginal.
- the-sleepy-little-star: `n_ready` says Twinkle "floated to her very own spot," yet the `n_sway` exit
  choice is "Glide to her very own spot in the sky," a spot she is nominally already at. Minor spatial
  wobble of the F1 family.
- the-night-market `fs_stack`: Pip the pangolin is "like a small striped bulldozer"; pangolins are scaled,
  not striped. Cosmetic, but the book never otherwise describes her beyond "pinecone with eyes," a real
  knowledge-demand for 5-8 readers meeting an unfamiliar animal (extends the declared `knowledge_demands`
  blind spot; noted only, per the brief).
- puddle-jumping-day `n_worm_end`: "At dinner, Milo told everyone about the worm"; "everyone" is a
  household never established (the book contains only Milo and Grandma). Harmless.

## Categories checked with nothing found

- **Choice-promise vs destination (beyond F7):** checked every choice/target pair in all five books; aside
  from F7's sequencing case, landings answer their labels (as CG-4 already guarantees).
- **Age-inappropriate or unsafe content in the depicted-harm sense:** none found in any book; the safety
  gate's own territory looks clean.
- **Factual errors of the school-fact kind:** puddle-jumping-day's six-color rainbow (`n_rainbow_end`) is
  a standard simplification, not an error; no other factual claims are made anywhere in the set.
- **Metadata drift:** ending counts in metadata match actual endings in all five books (4/3/6/6/13);
  already gate territory, confirmed clean.
- **Tense or POV instability:** none observed (already measured deterministically).

## Relation to declared blind spots

F1 extends `information_state` from a rubric label into a checkable graph property (dominator-based
referent validation), which is the high-value direction the brief asked for. Nothing found here contradicts
the declared blind-spot list. The remaining findings (F2-F12) fall outside both the current coverage and
the declared blind spots.

## Suggested tooling summary (deduplicated)

| # | Type | Check |
|---|------|-------|
| F1 | deterministic | merge-node referent lint: definite NPs must be introduced on a dominating node |
| F2/F4 | judge criterion | `stake_resolution` with anchors as given |
| F3 | deterministic | companion-presence persistence across paths |
| F5 | judge criterion | `object_continuity`, judged over paths not node lists |
| F6 | deterministic | cycle re-entry staleness lint; bounded failure loops |
| F7 | deterministic | sequencing-adverb labels require sibling subtree reachability |
| F8 | deterministic -> human | imitable hazard act flag (child agent + hot/flame lexicon) |
| F9 | taxonomy | guardian-facing `real_world_practices` descriptors |
| F10 | deterministic | catalog-level character-name collision registry |
| F11 | deterministic | within-path repeated n-gram + pronoun-antecedent lint |
| F12 | judge criterion | `consequence_causality` (or extend choice_quality rubric) |

Lesson-log candidates arising from this run (not appended to the authoring lessons log because this session
is read-only outside this file; the reviewing supervisor should carry them over): F1, F6, and F10 each meet
the log's bar ("tooling let a defect through", "next person would re-learn it from scratch").
