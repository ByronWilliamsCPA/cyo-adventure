# Review-process blind spots: findings from five passed books

Reviewer: Fable B. Scope: the five books named in the brief, read branch-by-branch as a child would
experience them. Everything below is outside the 40 deterministic rules, the 7 judge criteria, the
listed prose measures, and the five declared blind spots, except where a finding contradicts or
extends a claimed coverage (marked as such). Branch paths cited as "reachable" were verified
mechanically against the choice graph, not eyeballed.

Severity ordering: findings 1 through 4 would visibly confuse or shortchange a real child;
5 through 8 would matter to a guardian; 9 through 13 are lower-stakes but cheap to fix.

---

## 1. Endings that narrate a rescue history the reader did not have (tide-pool)

**Book / nodes / quotes.** `the-tide-pool-rescue`, endings `e_tide_snail`, `e_tide_star`,
`e_story`, `e_names`, `e_toast`, `e_song`.

- `e_tide_snail`: "Three rescues by you, and one by the tide," Gran said. This ending is reachable
  after **one** rescue: `n_start -> n_walk -> n_meet -> t_fi_cr -> ... -> cr_thanks ->
  c_cr_rest -> e_tide_snail` (verified against the graph). A reader who went straight to Pinch the
  crab and then sat down with Gran is told they performed three rescues.
- `e_tide_star`: "The water reached Flick, and his puddle grew into a lake. It unwrapped Pinch from
  his seaweed. ... 'One rescue by you, and three by the tide.'" Reachable after rescuing Flick
  *first* and Stella second (`fi_thanks -> n_meet -> st_... -> st_thanks -> c_st_rest`). On that
  path Flick is already in the big pool; the ending re-strands him so the tide can rescue him
  again, and the "one rescue by you" count is wrong (it was two).
- `e_story`: "Milo told Gran the whole story of the rescue day. Stella was stranded ... Flick was
  trapped in his shrinking puddle. Pinch was tangled up in slippery seaweed. And there was the
  long, slow ride home, for the littlest shell of all." Reachable after rescuing only Stella
  (`st_thanks -> c_st_done -> n_alldone -> n_tide -> n_picnic -> e_story`). Milo narrates three
  rescues that never happened on this playthrough.
- `e_names` / `e_toast` / `e_song`: Milo greets or toasts "Stella, Flick, Pinch, and Winnie" by
  name on paths where he never met three of them and never learned their names.

**What is wrong.** The book is `loop_and_grow` with `variables: []`. The hub allows any subset of
the four rescues in any order, but six of twelve endings hard-code a specific rescue count, order,
or full roster. A child who did one rescue is told a materially different story about their own
choices. This is the exact failure "an ending that contradicts an earlier branch," in the worst
form: it contradicts the branch the reader actually walked.

**Why nothing catches it.** L1/L2 check reachability and shape, not text-vs-path semantics. RL, PL,
CH, CG all evaluate a node (or a choice/destination pair) in isolation. Fork consequence distance
measures where paths diverge, not whether an ending's claims hold on every incoming path. The judge
panel scores `ending_quality` on the ending's own satisfaction; each of these endings reads as
lovely in isolation. Nothing in the pipeline ever evaluates an ending *conditioned on the set of
paths that can reach it*.

**One-off or pattern.** Pattern within the book (6 of 12 endings) and the mechanism recurs in every
hub book in the batch (see finding 2). Also in `the-night-market`: `f_string` ("The golden string
went on with a loop, loop, pull") replays the knot lesson from `fs_bundle` on paths where the fruit
stand was never visited; not a contradiction, but the same path-blindness.

**Proposal (deterministic check).** A *walk-consistency* gate: for every ending node, compute the
set of ancestor nodes common to **all** root-to-ending paths; extract named entities and count
words ("one", "two", "three", "four", "whole", "every") from the ending body; fail if the ending
names an entity or asserts a count whose introducing node is not in the common-ancestor set.
Cheap on graphs this size, and it would have flagged all six endings above with the exact
offending token. Companion authoring rule: a skeleton whose topology is `open_map` or
`loop_and_grow` and whose endings enumerate sub-quests MUST declare variables and condition the
ending text, or keep endings roster-free.

---

## 2. Hubs that reset resolved crises on re-entry (tide-pool, night-market)

**Book / nodes / quotes.**

- `the-tide-pool-rescue`, `n_meet`: "A sea star was stuck on a bare ledge. A fish was trapped in a
  shrinking puddle. A crab was tangled in the seaweed. A periwinkle was stranded on a sunny rock."
  Every return trip (`c_st_back`, `c_fi_back`, `c_cr_back`, `c_pw_back` all target `n_meet`)
  re-asserts that all four friends are stuck, including the one the reader just carried home, and
  re-offers the stale choice label "Hurry to the sea star on the high ledge" after Stella is
  already back in her pool. Choosing it replays the entire rescue verbatim.
- `the-night-market`, `n_hub`: each gift node returns to the hub, and the hub re-offers every
  stall. Re-entering `pf_entry` after fixing the paper stall shows "His basket had tipped over.
  Squares of red and gold and blue were drifting away down the lane" all over again; Auntie Plum's
  pyramid re-collapses; Auntie Mo needs "four more hands" again after the trays were delivered.

**What is wrong.** State a seven-year-old is proudly tracking (I saved her, I fixed that) is
denied by the very next screen. Replaying a resolved crisis verbatim reads as a broken toy, and in
the tide-pool case it contradicts the story's central promise that helping matters.

**Why nothing catches it.** Orphan/dead-end/reachability checks treat cycles as legal (they are).
No rule asks whether a node inside a cycle asserts a state that a sibling branch resolves. Judges
see prose, not the revisit experience.

**One-off or pattern.** Pattern: both hub-topology books in the batch. The two `time_cave` books
are immune only because their topology forbids revisits, which suggests the defect will appear in
every future hub book until checked.

**Proposal.** Deterministic: for every node reachable via a cycle, and for every entity that node
asserts to be in a "problem" state (extractable from the skeleton's sub-quest structure: the entry
node of each spoke), verify the spoke cannot have been completed before re-entry, or require the
hub body/choice labels to be revisit-neutral (no assertions about spoke-internal state). Simplest
enforceable version: **hub nodes and hub choice labels may not restate spoke-internal problem
state**; a lint that diffs hub-body noun phrases against spoke-entry noun phrases would catch both
books. Alternatively: block `variables: []` when topology is `open_map`/`loop_and_grow` and any
spoke changes world state.

---

## 3. An ending that contradicts a fact the same book established (school-garden, night-market)

**Book / nodes / quotes.**

- `the-school-garden-mystery`: `cc_tunnel` establishes "a fresh little tunnel, dug right under the
  garden fence! The hole was round and smooth, just the size of a loaf of bread." The `r_fence`
  branch then builds "a knee-high fence around the lettuce beds," and `e_fence` declares "The
  little fence worked just right. It kept the lettuce safe." The book itself proved these rabbits
  dig under fences; the celebrated solution is a fence, and a low one. A bright reader who visited
  the compost corner will catch the story contradicting its own clue. (Reachable on one path:
  `cc_tunnel -> cc_peek -> wc_approach -> ... -> wc_reveal -> r_fence`.)
- `the-night-market`: `f_steps` states a world rule: "At the night market, nobody shy or late is
  ever left out." Yet all four setback endings (`e_ds_spill`, `e_tc_slosh`, `e_tm_spring`,
  `e_mc_gong`) send Pip home with no lantern that night: "Home time," said Ada at last. "I'll save
  you a lantern," Auntie Mo called. "Next market night." The shy newcomer is exactly the person
  the rule says is never left out, and she is left out because Milo whacked a gong. The
  consequence also lands on the wrong character: Milo errs, Pip loses her one wish.

**What is wrong.** Cross-node factual/thematic contradiction. In the garden case it is a logic
hole in the mystery's solution; in the market case a stated world rule is falsified by four
endings, and the emotional cost is misassigned in a way a child will feel as unfair.

**Why nothing catches it.** No deterministic rule compares one node's assertion against another's.
`ending_quality` scores each ending alone; `e_fence` and `e_ds_spill` are individually warm and
well-written. The declared blind spot `information_state` covers who *knows* what, not whether the
world's stated facts stay true.

**One-off or pattern.** Two books, three-plus nodes; call it an emerging pattern. Related physical
instance in `the-big-red-balloon`: the balloon behaves as strongly buoyant everywhere ("Up, up it
floated, past her fingers", `n_slip`; it climbs to kite height in `n_top`) except in `n_drift`,
where it "drifted down. It landed softly on the water" and floats on the pond indefinitely. Same
object, opposite physics, chosen per branch for plot convenience.

**Proposal (judge criterion, `world_consistency`).** Judge the assembled book, not nodes: "Do
facts, rules, and object behaviors established anywhere in the book hold everywhere else,
including endings?" Anchor 1: "An ending's solution or claim is directly falsified by a clue,
rule, or physical behavior the book itself established; a child could quote the two passages at
each other." Anchor 5: "Every stated rule and established behavior survives every branch; where a
branch bends one, the text acknowledges the bend." Feed the judge the full node list plus the
specific fork ancestry per ending.

---

## 4. Props appear from nowhere and gifts vanish (snow-day, night-market, school-garden)

**Book / nodes / quotes.**

- `the-snow-day-expedition`: `n_gear` enumerates the expedition inventory precisely ("A dented
  silver pot of cocoa. The flat metal shovel. The notebook with the pencil on a string. A bag of
  small orange carrots."). At the summit, `m_4` produces "Nadia held up the broom handle. Her red
  mitten was tied to the end of it" with a definite article, as if established: no broom handle
  was packed, and nothing shows her removing a mitten in "the coldest cold." `m_s1` lines the sled
  up at the summit though nothing hauled it up the climb from `m_1`, where it was parked at the
  foot. `p_2` invokes "the ice scraper," never introduced. `p_3` produces "Nadia's spare scarf."
- `the-night-market`: Pip's inciting loss is total: "I had a basket. My wish paper was in it, and
  my golden string, and my candle. Everything I need for the ceremony" (`n_meet`). Yet `tm_gift`
  has Mr. Fez repair "Pip's lantern frame": an object she should not possess, never introduced.
  Conversely, the gifts the reader collects (Granny Osha's candle tin, Auntie Plum's golden
  string, the paper folder's wish paper) are never mentioned again: `f_steps` supplies table
  spares ("spare wish paper. And coils of golden string. And little flames in tins") and the
  finale draws from the table on every path. The emotional payoff of each stall's "exactly like
  the one she lost" gift is silently discarded.
- `the-school-garden-mystery`: `wc_offer`: "She held out a green lettuce leaf." On any path that
  skipped the tool shed there is no acquisition of a lettuce leaf anywhere; it materializes.

**What is wrong.** Object continuity errors in both directions: used-but-never-acquired, and
acquired-but-never-used where the acquisition was the scene's whole point. Children track
inventory obsessively; "where did the broom come from?" and "why didn't Pip use HER candle?" are
exactly the questions these books provoke.

**Why nothing catches it.** No rule tracks props. CG checks that a destination answers its choice;
PL checks lengths and FILL residue; nothing models acquisition/use across a path.

**One-off or pattern.** Pattern: three of five books, five-plus instances.

**Proposal (deterministic check).** A prop-ledger lint per path: (a) flag first mentions of
concrete portable nouns that arrive with a definite article or possessive ("the broom handle",
"Pip's lantern frame") when no indefinite introduction exists on any incoming path; (b) for books
with an explicit packing/inventory node (detectable: a node enumerating 3+ portable objects),
flag act-3 use of portable objects absent from the list, and flag listed or gifted objects never
referenced after acquisition. (a) is regex-plus-parse cheap and would have caught the broom
handle, the lantern frame, and the ice scraper by itself.

---

## 5. Two of the five books have a protagonist named Milo (cross-book)

**Book / nodes / quotes.** `the-night-market` `n_start`: "said Milo's cousin Ada. Milo nodded
hard." `the-tide-pool-rescue` `n_start`: "It was low tide, Milo's favorite time." Both are band
5-8, same batch, same library shelf. One Milo goes to a night market with cousin Ada; the other
goes tide-pooling with Gran; they are plainly not the same boy, but nothing tells a child that.

**What is wrong.** A reader who meets both books will assume one character and be confused (why
does Milo's Gran not know about Pip? why does Milo talk to fish here and not there?). For a
catalog that also runs *persistent* characters as a feature, an accidental name collision between
unrelated protagonists is a real product defect, not a nicety.

**Why nothing catches it.** CH-1..CH-8 are per-book. The only cross-book measure in use is shared
four-gram convergence, which normalizes away or simply does not target proper names. Nothing
compares character rosters across books in a band or batch.

**One-off or pattern.** One collision in five books, but with a five-book sample and a small kid-
name lexicon LLMs favor (Milo, Pip, Nadia, Priya, Lila are all top-of-distribution), collisions
will recur as the catalog grows. Note this batch also has two shy small-animal sidekicks named
with P (Pip the pangolin, Pinch the crab) and two grandparent chaperones; the name pool is already
visibly narrow.

**Proposal (deterministic check).** Catalog-level roster check at import: extract named characters
per book (already needed for CH rules); fail or warn when a *protagonist* name matches any
existing protagonist in the same age band, and warn on any named-character collision within a
batch. Trivial to implement against the existing import path.

---

## 6. Safety rules score depicted peril, not imitable practice (all five books, worst in snow-day)

The `content_flags` and safety validators ask "does anything bad happen to a character?" In all
five books nothing bad happens, and they pass. Nobody asks "what does this teach a child to go do
this afternoon?" That question is a guardian's first question.

**Instances, strongest first.**

- `the-snow-day-expedition` `i_f2` / `e_i_tunnel`: two children dig an enclosed crawl tunnel
  through snow ("They dug from both ends at once. ... The tunnel was dark and cold in the middle")
  and then repeatedly crawl it ("Nadia crawled the whole tunnel first. ... Then Theo. Then both of
  them again, just because"), with the only adult inside the house. Snow tunnel and snow fort
  collapse is the canonical winter suffocation hazard that schools and parks services warn about
  every year, and this book presents it as the triumphant "Greatest fort ever" ending. Same book,
  `m_1`-`m_4`: climbing the plow bank at the driveway edge ("a snowbank loomed by the driveway
  ... taller than the car") while snow machinery is audibly operating ("Far away a machine gave a
  long roar and threw up a white plume", `m_2`).
- `the-night-market` `f_flame` / `e_light_pip`: children handle open flame and release a burning
  sky lantern; the bravest-framed option is the smallest character lighting it "all by herself."
  Sky lantern releases are banned as fire and wildlife hazards in much of the app's likely market;
  the book presents release as pure wonder with no adult hand on the flame in one branch.
- `the-big-red-balloon` `e_duck_parade`: the lost balloon settles onto the duck pond and is
  celebrated as staying there ("Her balloon led the parade now. What a happy trade"). Balloon
  debris on waterfowl ponds is a well-documented wildlife killer; `e_strawberry_goodbye` likewise
  cheerfully waves off a flyaway. Also `n_boat`: a preschooler boards a small boat with no
  mention of a life vest.
- `the-school-garden-mystery` `wc_offer` / `r_patch`: hand-feeding a wild rabbit ("She held out a
  green lettuce leaf") and institutionalizing a feeding station for wild animals, contrary to the
  leave-wildlife-wild guidance schools actually teach. (The snow-day book gets this right: the
  carrot is placed "a polite way off" and they back away.)
- `the-tide-pool-rescue`: Gran's stated rule "Stay on the dry rocks" (`n_walk`) is then
  contradicted by nearly all of the action, which happens kneeling among wet pools as the tide
  comes in; and the whole premise is handling and relocating tide-pool animals, against the
  look-don't-touch etiquette of real tide-pooling programs (softened, admittedly, by the animals
  verbally requesting help).

**Why nothing catches it.** `content_flags` grade violence/scariness/peril *experienced in the
story*: everything above is zero-peril in-story. `age_fit` judges suitability of content, and a
cozy snow fort is suitable content. No criterion asks whether the modeled behavior is safe to
imitate, which is the axis guardians actually police.

**One-off or pattern.** Pattern: all five books, varying severity. The tide-pool book also shows
the fix is compatible with charm (its "unsafe" choices are the punished ones).

**Proposal (new judge criterion, `imitable_practice`).** "Would a guardian be comfortable with a
child imitating what the protagonist is rewarded for doing, in the real-world analog of this
setting?" Anchor 1: "A rewarded, ending-level behavior is one that safety organizations
specifically warn children against (enclosed snow tunnels, solo open flame, unsupervised water),
with no in-story mitigation." Anchor 5: "Rewarded behaviors are safe to imitate or are explicitly
supervised/mitigated in-text; risky options exist only as gently corrected missteps." Supplement
with a small deterministic keyword screen (tunnel+snow, flame+child+alone, boat without vest,
feed+wild) to route books to human attention; the classifier list is short and stable.

---

## 7. One untelegraphed instant-loss choice, in a batch that otherwise telegraphs fairly (school-garden)

**Book / node / quote.** `the-school-garden-mystery` `cc_tunnel`, choice `c_cc_dig`: "Dig through
the compost corner for buried clues." Target `e_set_compost` is a terminal setback: the tidy-up
bell rings, day over, mystery unsolved.

**What is wrong.** Every other setback fork in these five books telegraphs its risk in the label
or the preceding body: "Stack three trays high" after being offered slow-and-steady, "Give the big
gong one mighty whack," "Pour warm cocoa over the ice. But then our only fuel would be gone,"
"Lean way out over the water," "Dash over for a quick peek" after two explicit slow-down lessons.
Digging the compost for clues carries no such signal; it is a reasonable detective action framed
identically to the two productive siblings (`cc_peek`, `cc_fence`), yet it is the only one that
ends the book. To a child this is a trapdoor, not a decision; it punishes engagement with the
mystery rather than haste or greed.

**Why nothing catches it.** CG-4-style checks confirm the destination answers the choice (it
does: she digs). `choice_quality` asks whether branch points feel like real decisions, not whether
failure is fairly signposted. Fork consequence distance measures how far consequences are, not
whether their sign was inferable.

**One-off or pattern.** One-off in this batch; every other terminal setback is fairly telegraphed,
which is exactly why this one stands out and why a rule is worth writing before the pattern decays.

**Proposal (deterministic check).** For every choice whose target is an ending (or reaches one in
one step) with `kind: setback`: require a risk cue in the choice label or its source-node body,
from a small lexicon (excess: "three", "whole", "mighty", "as far as it can go"; haste: "dash",
"quick", "right away"; explicit stated cost: "only fuel would be gone"; overreach: "way out",
"one more inch"). Flag setback-bound choices with no cue for human review. All eleven other
setback-bound choices in this batch pass such a lexicon; `c_cc_dig` alone fails.

---

## 8. Ending metadata contradicts ending text, and two ending titles carry template-fill artifacts

**Book / nodes / quotes.**

- `the-tide-pool-rescue` `e_tide_star` and `e_tide_snail` are tagged `valence: neutral, kind:
  setback`, yet the text is a warm success: "'One rescue by you, and three by the tide,' Gran
  said. 'What a fine team.'" Choosing rest-with-Gran is a legitimate, kind resolution the book
  itself endorses; a completionist child seeing a "setback" badge on it (endings-collected UIs
  surface kinds) is told the cozy choice was a failure.
- `the-snow-day-expedition` `e_m_retreat` is `kind: setback` while its own text argues the
  opposite: "'This is not quitting,' Nadia said. 'Explorers call this regrouping.'" The metadata
  flatly disagrees with the story's stated moral.
- Title artifacts, same book: `end_m_retreat` title "Turned Back at the snow-swirl storm" and
  `end_p_retreat` title "Turned Back at a cocoa-melting mishap". The casing and the interchangeable
  tail read as a skeleton template "Turned Back at {obstacle}" whose slot was filled without title
  casing or article cleanup. These strings surface in the endings UI.

**Why nothing catches it.** PL checks the ending-kind *mix*, not agreement between a kind label
and the body text. The retained-FILL check (PL-27) scans node bodies; `ending.title` is outside
its scope, so template residue in titles ships.

**One-off or pattern.** Kind/text disagreement: three endings across two books. Title residue: two
endings, one book, but it is the mechanically-rebound book, so the same bug likely exists in the
skeleton family.

**Proposal.** Two cheap deterministic checks: (a) extend the FILL-residue/format scan to
`ending.title` (title-case violation plus slot-shaped lowercase tails); (b) a valence-agreement
check: run the existing told-emotion/sentiment machinery over ending bodies and flag endings whose
body sentiment is strongly positive while `kind` is `setback` (and vice versa) for human
relabeling. Also add an authoring-guide rule: `kind: setback` means the reader's goal was not met,
not "the branch was shorter"; resting while the tide finishes the job met the goal.

---

## 9. The chaperone evaporates (night-market)

**Book / nodes / quotes.** `the-night-market`. Ada is established as Milo's companion and enters
the market with him: "The three of them walked into the lantern square" (`n_promise`). She then
does not exist in the hub, any of the six stall arcs, or any of the nine ceremony-path nodes and
endings; Pip and Milo operate as a duo all evening. Ada rematerializes only in the four setback
endings, solely to end the evening ("'Home time,' said Ada at last", `e_ds_spill`). In the nine
good endings she is never seen again, including the finale where "the whole circle" is enumerated.

**What is wrong.** A named companion walks into the square and vanishes without an exit line. A
child asks "where did Ada go?"; a guardian notices that a young boy roams a crowded night market
alone for the whole book, and that the cousin exists only when the plot needs a ride home.

**Why nothing catches it.** CH rules evidently validate character introduction/consistency per
mention, not scene co-presence over time. Judges score `voice` and `dialogue`, not whether the
cast list stays conserved.

**One-off or pattern.** Strong in night-market; mild echo in school-garden (Ms. Flores and the
cheering class vanish between `n_start` and the endings, though "class garden jobs" plausibly
covers it, and `ts_marco` shows a classmate at work). Snow-day (Mom at the window in every act)
and tide-pool (Gran present in nearly every node) prove the authors can do this well.

**Proposal (deterministic check).** Co-presence tracking: for each named character, mark nodes of
explicit presence; if a character is textually co-located with the protagonist at node X ("the
three of them walked"), require either a presence mention or an explicit parking line ("Ada waved
them off toward ...") within the next N nodes on every outgoing path before a long absence. The
presence extraction is already half-built if CH rules identify character mentions per node.

---

## 10. Threads the book opens and no branch ever closes (night-market, school-garden)

**Book / nodes / quotes.**

- `the-night-market`: the inciting mystery is a *lost basket*: "I had a basket. ... Now I can't
  find it anywhere" (`n_meet`). Thirteen endings; not one finds the basket, explains it, or even
  lampshades it. The market replaces the contents, which resolves the ceremony but not the
  question the book actually posed. Mystery-minded readers notice.
- `the-school-garden-mystery`: on shed paths, Marco is revealed as the secret kind feeder
  ("I left lettuce so it would not go hungry," `ts_marco`). No ending mentions Marco again; in
  `r_patch` "The class loved Priya's plan" institutionalizes exactly what Marco was doing, with
  Priya taking the bow. The kid who was kind first gets no acknowledgment in any ending.

**Why nothing catches it.** Every listed check is node- or pair-scoped. `ending_quality` asks if
an ending satisfies, not whether it answers the questions act one raised. The declared blind spot
`information_state` is about knowledge asymmetry, not open-thread bookkeeping.

**One-off or pattern.** Two of five books; likely endemic to fill-based authoring, since the
skeleton carries the plot promise but each node is filled locally.

**Proposal (authoring-guide rule plus cheap LLM pass).** At fill time, extract explicit open
questions and debts from act-one nodes (lost objects, unexplained events, characters owed credit);
require each to be resolved or deliberately lampshaded in at least one ending, and any character
whose secret contribution is revealed mid-book to be referenced in every ending downstream of the
reveal. This is a one-prompt check over a book-sized context.

---

## 11. Real-world connotation screen: a pangolin at a night market

**Book / nodes / quotes.** `the-night-market` `n_meet`: "Behind the barrel was a pangolin."

**What is wrong.** Nothing in the text itself; Pip is a lovely character. But pangolins are the
most-trafficked mammal on earth, and the real-world place they are notoriously sold is night
markets. "Lost pangolin at a night market, alone, being handed between adults" is a collocation
that a zoologically-aware parent, teacher, or journalist will notice instantly, and not kindly.
The book also builds a generic pan-Asian market (dumplings, paper cranes, wish lanterns) staffed
by a grab-bag of names (Auntie Mo, Mr. Fez, Granny Osha), which compounds the sense that no one
looked at the real-world referents.

**Why nothing catches it.** Safety classifiers screen for harmful *content*; this is harmless
content with an unfortunate real-world shadow. No rule or judge criterion looks up what a chosen
species, setting, or pairing means outside the book.

**One-off or pattern.** One clear instance in five books, but species selection is exactly the
kind of choice generation makes cheaply and repeatedly; the next draw could be an elephant at an
ivory stall.

**Proposal.** Add a "real-world referent scan" step to moderation for anthropomorphic or exotic
species: one LLM question per named species/setting pair ("Does this species have a sensitive
real-world association with this setting or activity: trafficking, consumption, extinction,
cultural or religious significance?") with a human-review routing on yes. Deterministic fallback:
a short denylist of species-x-context pairs (pangolin/market, shark-fin/soup, elephant/ivory).

---

## 12. A grammar defect shipped inside a choice label, which CG nominally covers (contradicts claimed coverage)

**Book / node / quote.** `the-tide-pool-rescue` `cr_thanks`, choice `c_cr_rest`:
"Watch from **Gran's her towel** while the tide fetches the periwinkle."

**What is wrong.** A doubled possessive in a tappable UI string. Choice labels are the highest-
visibility text in the product: they are read aloud, and re-read while deciding.

**Why this is reportable despite `language_conventionality` being a declared blind spot.** The
declared blind spot covers prose. Choice labels are claimed territory: CG-1..CG-4 are described as
"choice grammar." This book passes all 40 rules, so CG's "grammar" evidently means answer-match
between choice and destination, not well-formedness of the label itself. That gap is worth naming
precisely because the rule's name will make everyone assume it is covered. Related lower-stakes
mechanics the band-3-5 book shipped: `the-big-red-balloon` `n_boat` opens "The boat lady rowed to
the bank. It was soft and muddy." (the nearest antecedent for "It" is the boat lady; the sentence
pair is also copied verbatim from `n_ducks`), and the same book's boat is rowed in `n_boat` but
pedaled in `n_pedal` under a choice label calling it a "paddle-boat": three propulsion systems in
four nodes.

**One-off or pattern.** The doubled possessive is a one-off; label-level mechanical defects
escaping CG is structural.

**Proposal (deterministic check).** Run choice labels (and ending titles, per finding 8) through
the same conventionality tooling planned for bodies, plus a trivial doubled-determiner/possessive
regex (`\b(\w+'s|my|her|his|their|your)\s+(her|his|their|my|your)\b`) which catches this exact
class for free today, ahead of any larger language_conventionality effort.

---

## 13. `safety_scope` tagging is vestigial and misleading (metadata, tide-pool)

**Book / nodes.** Across all five books, exactly two nodes carry a `safety_scope` field:
`the-tide-pool-rescue` `fi_scene` and `fi_meet`, both `["peril"]` (the fish in the shrinking
puddle). The drying sea star on the hot ledge (`st_scene`: "The ledge is getting warm"), the
incoming tide throughout, the snow-day tunnel, and the night-market open flame are untagged.
All five books declare `variables: []` (which is the root enabler of findings 1 and 2).

**What is wrong.** If `safety_scope` feeds anything downstream (moderation weighting, guardian
display, rescreen targeting), two-nodes-in-five-books coverage is worse than none: it implies the
untagged nodes were assessed peril-free. If it feeds nothing, it is residue that will mislead the
next tool author.

**Why nothing catches it.** The 40 rules validate declared clock, topology label, and ending mix;
none validates `safety_scope` coverage or consistency, and no rule requires variables for
state-bearing topologies.

**One-off or pattern.** Batch-wide metadata pattern.

**Proposal.** Either remove `safety_scope` from the fill output, or add a deterministic
consistency rule: if any node in a book is tagged, every node matching the same content_flag
trigger class must be tagged or explicitly cleared; and (per findings 1-2) reject
`variables: []` for `loop_and_grow` skeletons whose spokes mutate world state.

---

## Categories searched with nothing to report

Stated plainly, per the brief:

- **Age-inappropriate or frightening content missed by safety rules**: none found. All five books
  are tonally safe in-story; the risks are imitation-side (finding 6), not depiction-side.
- **Accessibility of the text itself** (onomatopoeia, all-caps, sound-dependent gags): nothing
  that rises to a finding; "SPROING"/"BWOOOONNNG" are screen-reader-awkward but conventional for
  the band.
- **Choice-promise breaks of the direct kind** (label says X, destination does Y): none found;
  the CG answer-match rule appears genuinely effective at what it actually checks.
- **Tense stability, told-emotion, dialogue naturalness**: nothing beyond what the existing
  deterministic measures already claim; no findings invented to fill the space.
- **Snow-day theme binding**: judged on its own terms as instructed; its imagination frame
  (backyard-as-White-Wild) is handled consistently and is the batch's best-executed conceit. Its
  defects are the cross-cutting ones above (findings 4, 6, 8), not the rebind.

## The one-sentence version

The pipeline validates nodes, pairs, and graphs; every high-value defect found here lives in the
relationships the pipeline never looks at: ending-vs-path (1), node-vs-revisit (2), node-vs-node
fact (3), object-vs-path (4), book-vs-book (5), story-vs-real-world (6, 11), and label-vs-metadata
(7, 8, 13).
