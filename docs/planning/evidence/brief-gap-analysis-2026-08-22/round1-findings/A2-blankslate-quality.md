# What Makes a CYO Book Good for a Child, and How You Would Know if a Machine Made It

A blank-slate assessment from children's-publishing craft and evaluation methodology.
No prior knowledge of this team's approach was used.

---

## 0. The one framing error that causes most of the others

**Quality in a branching book is a property of *walks*, not of *nodes*.**

An engineering pipeline naturally produces node-level artifacts, so it naturally builds
node-level quality checks: is this passage well written, on-level, safe, on-premise. Every node
can pass and the book can still be worthless, because the reader never experiences a node. The
reader experiences one root-to-ending path, then maybe a second, then decides whether this was a
story or a machine.

Three corollaries, which should be treated as architectural constraints, not as advice:

1. **Every root-to-ending walk must independently be a complete story** with setup, escalation,
   crisis, and resolution. A 677-node graph with 400 terminal paths is 400 short stories that
   happen to share prose, not one story with 400 exits.
2. **The evaluation unit is the path and the book, never the node.** Node-level LLM judging will
   return near-ceiling scores forever and tell you nothing.
3. **The novelty unit is the child's library**, not the book. See section 5.

Everything below elaborates these.

---

## 1. What makes CYO work as a form

### 1.1 What the reader is actually doing

A child reading a CYO book is running two loops at once.

**The story loop:** wanting to know what happens.
**The agency loop:** predicting, committing, being answered.

The agency loop is the one the form exists for, and it has a precise shape:

> situation understood → options weighed → *prediction formed* → commitment made →
> outcome revealed → prediction confirmed or productively violated → self-model updated
> ("I am the kind of reader who opens the strange door")

Agency, in Murray's sense, is the satisfying power to take meaningful action and see the results
of your decisions. Note the two halves. Most machine-generated interactive fiction delivers the
first half (an action was taken) and fails the second (the results are not legible *as results of
that action*). A consequence the reader cannot attribute to their choice is not a consequence; it
is just the next paragraph.

The critical, under-appreciated component is **prediction**. A choice the reader cannot form a
prediction about is a coin flip, and a coin flip is not agency; it is a slot machine. A choice
whose outcome the reader can predict with certainty is not agency either; it is a compliance test.
The design target is a narrow band I will call **informed uncertainty**: the reader can rank the
options by *what kind of story* each will produce, but cannot know how it will go.

### 1.2 What the canon actually teaches

- **Original Choose Your Own Adventure (Packard/Montgomery, Bantam, 1979 onward).** The durable
  insight is *ending plurality as a worldview*: 20 to 40 endings, most of them neither victory nor
  death but simply *a different life*. You become a dolphin. You stay on the island. The book's
  implicit claim is that outcomes are various, not ranked. This is the single most valuable and
  most-forgotten property of the line, and it is exactly the property an LLM pipeline destroys,
  because an LLM's prior is that stories end well and lessons get stated. The original line's
  weakness was the opposite of an LLM's: abrupt, arbitrary, sometimes nonsensical endings with no
  causal grounding. So: **inherit the plurality, fix the arbitrariness.**
- **Fighting Fantasy (Livingstone/Jackson, 1982 onward).** Gamebook, not story: one true path,
  dozens of deaths, hidden state, inventory, dice. What it teaches is the failure mode. Its
  instant-death lever-pulling is the canonical example of **choices that punish curiosity and
  reward memorised trial-and-error**. It works for a certain 11-year-old boy with a pencil; it is
  the wrong model for a subscription reading app whose success metric is a child wanting another
  book. Its genuinely good idea is *persistent state*: what you carry changes what you can do.
- **Modern parser/choice IF and the Ink/Twine craft tradition** (Inkle's *80 Days*, *Sorcery!*;
  Failbetter; Choice of Games; the Twine scene). This is where the real craft rules live, because
  these authors write branching prose for a living and have converged on techniques:
  - **The braid, not the tree.** Pure branching is combinatorially unaffordable and always was.
    Working structure is diverge-and-reconverge (Ink's "gather"), with the reconvergence *tinted*
    by what happened. Inkle's whole architecture is "weave": a spine with local divergence, plus
    variables that make the spine read differently.
  - **State beats topology.** Inkle's public position is that memory is cheaper and more effective
    than branching: a small number of remembered facts, referenced often, produces more felt agency
    than a large number of unique nodes. This is the highest-leverage design fact in the whole
    document for a cost-constrained generator. You do not need 677 unique nodes to feel personal;
    you need 30 remembered facts referenced 200 times.
  - **Choice text is a promise.** Choice of Games' house style is explicit about this: the option
    must state an action and an intention, so the reader chooses a *stance*, not a door.
  - **Quality-based narrative** (Failbetter): content gated on accumulated qualities rather than on
    position in a tree. Scales far better than branching for long books.
- **Life Is Strange / Telltale-style branching.** The commercial lesson is uncomfortable and
  important: **most of these choices reconverge, and players report high agency anyway**, because
  the game *acknowledges* choices constantly (characters remember, dialogue varies, a tally is
  shown). The backlash arrives only when acknowledgement is absent, at which point the same
  structure reads as contemptuous. Conclusion: reconvergence is not the sin. **Unacknowledged**
  reconvergence is the sin. This is good news for cost, and it dictates where the money goes:
  spend on callbacks and variant lines, not on unique subtrees.

### 1.3 The craft rules that fall out

These are stated so a machine can be held to them.

**R1. Every choice is a dilemma with a value tradeoff.** Each option must sacrifice something the
other protects (safety vs. loyalty, curiosity vs. obedience, speed vs. care, self vs. friend). If
no option costs anything, delete the choice.

**R2. No dominant option.** If a competent reader in the target band would pick the same option
more than about 80% of the time, it is not a choice.

**R3. Choice labels must be predictive and honest.** Each label names an action and its intention,
in the reader's own register, short enough to scan. "Go left" is banned. The successor node must
deliver what the label promised; a label that promises the wrong thing is a lie, and children
detect lies quickly and stop trusting the interface.

**R4. Option parity.** Options at a choice point must be comparable in length (within ~30%), in
grammatical form, and in framing valence. Longer and more vividly written options get picked
regardless of content; asymmetry is an accidental thumb on the scale.

**R5. Consequence must be observable, and its latency scales with age.** Ages 3 to 5: within the
same node. Ages 5 to 8: within one node. Ages 8 to 10: within three nodes, plus at least one
long-range payoff per path. Older: long-range allowed, but see R6.

**R6. The callback rule.** Any choice with delayed consequence must be *named* later in the prose
on the paths that took it ("the lantern you left behind", "because you told Mira the truth"). An
unnamed consequence does not exist for the reader. Minimum: at least 60% of a path's choices are
textually referenced after the fact somewhere later on that path.

**R7. Reconvergence must be tinted, never blank.** Every node reachable from more than one distinct
choice must contain at least one variant sentence keyed to which was taken. A shared node with
identical text on all incoming paths is a consequence-erasing node.

**R8. The protagonist causes the story.** The reader-character is the grammatical and causal agent
of the events that change the world. Guides, mentors, and talking animals may inform; they may not
decide. Target: at least 60% of scene-turning actions on any path are initiated by "you".

**R9. Curiosity is rewarded, not taxed.** The exploratory option may cost something, but across a
book it must not be systematically shorter, less richly written, or worse-ending than the cautious
option. The child who pokes the strange door is the reader you want; do not train them out of it.

**R10. Endings are differentiated in kind, not ranked in quality.** Aim for a spread across
outcome *types* (full success, costly success, transformation, refusal, deferral, comic reversal,
bittersweet, quiet-different-life). Avoid a single desirability ordering; avoid a hidden right
answer.

**R11. No unearned ending.** Every terminal node must be foreseeable in hindsight from information
the reader actually had on that path, and must be causally attributable to at least one choice
made. Random death is a bug.

**R12. Second reading must recontextualise the first.** Branches should reference each other's
content obliquely: a character you did not meet is mentioned; an object you did not take turns up
in someone else's hands. This is what makes the second path feel like a discovery instead of a
chore, and it is the entire economic argument for the form.

**R13. Choice cadence, not choice density.** One choice per scene beat. A choice every paragraph
destroys momentum ("clicking simulator"); a choice every 2,000 words is a novel with buttons.

**R14. The "you" is a costume with a stake.** Do not over-assign interiority the reader may not
share ("you feel terrified"); describe the stimulus and let the reader supply the feeling. But do
give "you" competence, a want, and someone to lose.

**R15. Stakes ride on a companion.** For children specifically, emotional engagement attaches to
the vulnerable other far more than to the self-as-protagonist. A dog, a younger sibling, a nervous
dragon. Books with no one to protect flatten out.

**R16. Every path terminates, every node is reachable, no progress-free cycles.** Table stakes.

---

## 2. Failure modes of branching narrative

Each is given a name, a detectable signature, and a detectability class:
**[CODE]** deterministic or embedding-computable; **[JUDGE]** requires an LLM judge over paths;
**[HUMAN]** requires an editor or a child. Many need two of the three; the class listed is the
cheapest tier that reliably fires.

### 2.1 Agency failures

**F1. Null Choice / Cosmetic Branch.** Options lead to the same node, or to nodes whose reachable
subtrees are semantically interchangeable.
*Signature:* successors converge within k ≤ 2 nodes AND embedding similarity of the divergent
content > 0.85 AND zero lexical differentiation at the reconvergence node. **[CODE]**

**F2. Vanishing Consequence / Reconvergence Amnesia.** Branches reconverge and nothing downstream
ever refers to which was taken.
*Signature:* ~~for a choice C, no node reachable only-after-C contains a lexical or entity-level
reference to C's distinguishing entity or action.~~ **Corrected 2026-08-30, and this was wrong when
written**: the nodes reachable only-after-C are exactly the branch-local ones, so a successor that
simply narrates the action just taken satisfies the rule, and the detector passes precisely the book
whose branches reconverge into an identical shared node. That is the defect this signature exists to
find, so as written it is a false negative by construction. Test the **reconvergence node** instead:
for a choice C whose branch reconverges at node R, R (and the nodes downstream of R) must carry a
path-conditioned fact, action, or variant that differs by which branch reached it. Branch-local text
before R is not evidence and must be excluded from the search. Build the callback index over
`(choice, reconvergence node)` pairs from the graph's dominator structure rather than over raw
downstream reachability. **[CODE]**, confirm **[JUDGE]**

**F3. Coin-Flip Choice.** Labels carry no predictive information.
*Signature:* **choice-label predictiveness**: embed each label and the first ~100 words of each
successor; within each choice set, measure how often the correct label-successor pairing is
recoverable. Chance is 1/n. A book at chance has no informative labels. Also flag literal
direction-only labels by pattern. **[CODE]**

**F4. Dominant Option / Compliance Test.** One option is transparently correct.
*Signature:* blind panel of judges given only the situation and the options picks the same option
> 80% of the time. Report per-choice **pick entropy**. **[JUDGE]**

**F5. Passive Protagonist.** The reader-character is acted upon; NPCs decide, explain, and rescue.
*Signature:* dependency parse ratio of volitional verbs with "you" as agent vs. "you" as
patient/recipient; count of scene-turning events initiated by NPCs. **[CODE]** as a screen,
**[JUDGE]** for confirmation.

**F6. The Rails.** The book has one real spine; all branches are excursions that rejoin within two
nodes and change nothing about the destination.
*Signature:* graph metric: fraction of choices whose two options share a dominator within 2 nodes;
number of distinct outcome tuples divided by number of choices. **[CODE]**

### 2.2 Consequence failures

**F7. Gotcha Death / Unearned Ending.** An ending arrives with no foreshadowing, no fault, and no
cue in the label that led there.
*Signature:* terminal node reached within ≤ 2 nodes of a choice whose label carried no risk cue;
negative-valence ending on a path significantly shorter than the median. Confirm with a judge given
*only the path text up to the choice*: "was this foreseeable?" **[CODE]** screen, **[JUDGE]** verdict.

**F8. Curiosity Tax.** Exploratory options systematically produce shorter paths and worse endings.
*Signature:* label each option explore/comply once with an LLM, then correlate option type with
path length and ending valence. **Important methodological point: a single book has only 10 to 30
choices, which is underpowered.** Run this as a *pipeline-level* statistic over hundreds of books,
and only as a weak per-book flag. **[CODE]** over a corpus.

**F9. Fake Stakes / The Reset.** Bad outcomes are undone: it was a dream, luckily nothing happened,
the wizard fixes it.
*Signature:* lexical pattern set ("it was all a dream", "woke up", "luckily", "just in time,
everything went back") plus ending-tuple extraction showing the world state identical to the
opening on every path. **[CODE]** + **[JUDGE]**

**F10. Ending Monoculture.** All endings are the same beat re-skinned.
*Signature:* do **not** use prose embedding distance; it is fooled by re-skinning. Extract an
**outcome tuple** per ending via LLM: (goal achieved? y/n/partial; companion state; world changed?;
protagonist changed?; cost paid?; tone). Measure distinctness on tuples. Prose-distinct,
tuple-identical endings are the exact defect. **[JUDGE]** extraction + **[CODE]** distinctness.

**F11. The Right Answer Trap.** A hidden correct moral path exists; other paths are punishment.
*Signature:* book-level. Blind judges rank all endings by desirability; if ranking is near-unanimous
AND the ordering correlates with a single behavioural axis (usually obedience or caution), flag.
**[JUDGE]**

### 2.3 Structural and craft failures

**F12. Filler Node / Corridor.** Out-degree 1, no new entity, no state change, no new information.
*Signature:* computable directly. Threshold: more than 15% of nodes are filler. **[CODE]**

**F13. Runt Branch / Branch Starvation.** One option's subtree gets 85% of the words; the other
dies in two nodes.
*Signature:* subtree word-count ratio at each choice. Rule: no option's reachable subtree below 25%
of the largest at that choice, unless explicitly declared an early-ending arm. **[CODE]**

**F14. Precondition Violation / State Drift.** A node asserts a fact ("you unlock it with the key")
that is not established on every path reaching it. Also: name drift (Mira → Mara), silently healed
wounds, time-of-day flips, an item used twice.
*Signature:* the strongest fully-computable check in this document. Extract asserted-as-known facts
per node, map each to its establishing node, and verify graph **dominance**: does every path from
root to the asserting node pass through an establishing node? Any failure is a hard defect.
**[CODE]**

**F15. Reader-Blind Difficulty.** A choice requires knowledge only available on a path not taken.
Same detector as F14, applied to choices rather than assertions. **[CODE]**

**F16. Tonal Whiplash.** Register jumps across an edge because different generation calls wrote the
two sides.
*Signature:* style-embedding or function-word-profile distance across edges; flag the top
percentile. **[CODE]** screen, **[HUMAN]** confirm.

**F17. Premise Abandonment.** The family asked for "a girl and a dragon"; the dragon appears once
and vanishes.
*Signature:* requested-entity presence per *path*, not per book, plus causal involvement of the
premise entity in the climax node of every path. **[CODE]** presence, **[JUDGE]** causal involvement.
Nearly every naive pipeline fails this on minority branches.

**F18. Moralizing Coda.** Every ending appends a stated lesson. This is the highest-prior LLM tic in
children's writing and children find it insulting.
*Signature:* final-paragraph classifier; abstract-noun density in the last 40 words ("learned",
"important", "always remember", "friendship is"). **[CODE]**

**F19. The Sanded Edge.** Safety tuning has removed all threat, so nothing is exciting. This is the
failure mode a moderation-heavy pipeline reliably produces, and it is invisible to safety metrics
because it is safety metrics winning too hard.
*Signature:* no negative-valence beat anywhere on a path; tension curve flat; no scene in which the
protagonist wants something they might not get. **[JUDGE]** + **[HUMAN]**. Requires a
*minimum* peril floor per band, deliberately expressed as a floor.

**F20. Voice Monoculture.** Every book in a child's library has the same narrator. See section 5.
*Signature:* stylometric classifier cannot separate books within one library, while it can separate
five human-authored reference books. **[CODE]** over a corpus.

**F21. Second-Person Slippage.** Narration drifts to third person; the reader-character acquires a
name, gender, or age inconsistent with the request. **[CODE]**

**F22. Ghost Content.** Nodes unreachable from root, or endings reachable by no path a real reader
would find (behind a choice never offered). **[CODE]**

### 2.4 What only a human or a child can tell you

Everything above is a defect. None of it is quality. The following are not reliably machine-detectable
today, at any price, and should be treated as the human tier's job:

- **Was it fun?** Only the child.
- **Did the reader feel like the author of what happened?** Only the child, and only via
  post-hoc free recall ("tell me what you did") rather than a rating.
- **Is the joke funny? Is the scary bit scary?** Human. Humour and dread are the two dimensions on
  which LLM judges are worst calibrated to children.
- **Is the voice charming or merely competent?** Human editor.
- **Would a parent be embarrassed by this?** Parent.
- **Does book 5 feel new?** Only a repeat reader, measured behaviourally.

---

## 3. Age-band craft differences

Beyond reading level, the variables that genuinely change are: **who operates the interface,
reversibility, time-to-consequence, threat-resolution latency, ending-valence floor, moral
determinacy, and interiority.** Branching factor is *not* one of them: **2 options at ages 3-5 and 2
to 4 thereafter** is correct, and widening beyond that makes books worse and more expensive.

*Corrected 2026-08-30, internal inconsistency present when written: this read "2 to 3 options is*
*correct at every band", which contradicts section 3.1 ("Options: exactly 2") and the monotone table*
*in 3.7 (2 at 3-5; 2-3 at 5-8 and 8-10; 2-4 at 10-13, 13-16, and 16+) in both directions at once. The*
*band-specific constraint governs; the general sentence now states the envelope rather than a range*
*that is simultaneously too wide for the youngest band and too narrow for the oldest three.*

### 3.1 Ages 3 to 5 (read-aloud; the adult is the interface)

- **Length/shape:** 400 to 1,200 words; 8 to 20 nodes; 3 to 6 choices per path; 2 to 4 endings.
- **Options:** exactly 2, always concrete physical actions, always depictable ("pat the puppy" /
  "peek behind the tree"). The child chooses by pointing; the label must be readable aloud in one
  breath.
- **Sentence craft:** 5 to 9 words, one clause, present tense, concrete nouns. **Repetition and
  refrain are features, not filler**, at this band; a recurring line the child can join in on is
  the single best craft device available. Rhythm and near-rhyme welcome.
- **Consequence latency:** zero. The result appears in the next sentence.
- **Peril:** a wobbly bridge, a lost mitten, a big noise that turns out to be a friendly thing.
  No death, no darkness-as-threat, no unresolved separation from a caregiver, no character in
  genuine danger.
- **Ending valence:** all warm; the character returns to a secure base. There is no wrong choice
  and no losing. "Different and delightful", never "worse".
- **Agency:** the choice changes what you *see*. That is enough, and it is a lot.
- **Session:** 5 to 8 minutes for a whole path; expect immediate re-reading of the other option.

### 3.2 Ages 5 to 8 (early independent; transitional readers)

- **Length/shape:** 800 to 2,500 words; 20 to 60 nodes; 2 to 3 options; 4 to 8 choices per path;
  3 to 6 endings.
- **Sentence craft:** 8 to 12 words average; simple and compound, sparing subordination; node
  bodies 60 to 120 words. Dialogue carries a lot of load and is easier than description.
  **Decodability matters:** favour words within the phonics patterns the band has been taught, plus
  high-frequency sight words.
- **Consequence latency:** ≤ 1 node.
- **Peril:** getting lost, a rule broken with proportionate consequences, a scary-looking creature
  that proves friendly, a mistake that must be fixed. Threat resolves within two nodes. No death of
  named characters.
- **Moral world:** fairness, honesty, sharing, courage. Consequences immediate and proportionate.
  Adults are reliable.
- **Ending valence:** mostly positive; one or two odd/funny endings are excellent here and teach the
  child that the book has range. No punishing endings.
- **Re-read:** an explicit design goal. Endings should gesture at the road not taken.
- **Session:** 10 to 15 minutes per path.

### 3.3 Ages 8 to 10 (the CYO sweet spot; where the original line lived)

- **Length/shape:** 5,000 to 15,000 words; 60 to 200 nodes; 2 to 3 options (4 occasionally);
  8 to 15 choices per path; 6 to 12 endings, including 1 to 3 "bad but survivable" ones.
- **Sentence craft:** 12 to 16 words; subordinate clauses fine; paragraphs 3 to 6 sentences; node
  bodies 120 to 250 words. Voice and humour start to matter more than clarity.
- **Consequence latency:** ≤ 3 nodes for the main line, **plus at least one long-range payoff per
  path** with an explicit callback. This band is where delayed consequence becomes legible and
  thrilling.
- **State:** introduce persistent state here: an object, a promise, a piece of knowledge. Two to
  four tracked variables, each referenced at least three times.
- **Peril:** genuine jeopardy, being trapped, failing, losing something that mattered. Protagonist
  death is permissible but should be *off-page and abstracted* ("and that is where your adventure
  ends"), avoidable in hindsight, and rare. Do not kill a beloved companion at this band.
- **Moral world:** mixed motives; adults who are wrong about things; the reader can be wrong and it
  is interesting rather than punished.
- **Ending valence:** mixed, with a positive plurality. Ranked endings begin to be acceptable but
  should not reduce to a single virtue axis.
- **Session:** 15 to 25 minutes per path; the book is designed to be walked 3 to 5 times.

### 3.4 Ages 10 to 13

- **Length/shape:** 15,000 to 40,000 words; 150 to 350 nodes; 2 to 4 options; 15 to 30 choices per
  path; 10 to 20 endings, genuinely mixed including bittersweet and ambiguous.
- **Sentence craft:** 14 to 20 words, deliberately varied; interiority appears (the protagonist's
  doubt, self-deception); subtext becomes available; irony is legible.
- **Consequence latency:** long-range is the norm; a node-10 choice paying off at node 120 is the
  band's signature pleasure, provided R6 (callback) holds.
- **Peril:** mortal stakes for the protagonist and for secondary characters; betrayal; grief, if
  supported; injustice as backdrop rather than as villainy.
- **Moral world:** dilemmas with no right answer. Loyalty vs. truth. The protagonist may do harm
  while meaning well.
- **Agency shift:** choices now define *who the protagonist is*, not just which corridor they walk.
  Track a values axis and let it determine the ending. This is the band where "the ending you got
  says something about you" starts working, and it is powerful.
- **Session:** 25 to 40 minutes per path.

### 3.5 Ages 13 to 16

- **Length/shape:** 30,000 to 80,000 words; 300 to 500 nodes; 2 to 4 options plus dialogue-tree
  style exchanges; 25 to 50 choices per path; 15 to 30 endings, which may be unhappy, unresolved,
  or morally costly.
- **Sentence craft:** adult syntax. Voice outranks clarity. Register may shift by scene.
- **Peril:** on-page violence with consequence, death that stays dead, romance handled with care,
  risk behaviour depicted honestly rather than moralised, mental health with accuracy.
- **Moral world:** complicity, compromise, irreversibility. The reader should sometimes be made to
  feel responsible and not let off the hook. The single worst thing you can do at this band is
  forgive the reader automatically.
- **Endings:** none arbitrary; each a legible consequence of an accumulated pattern of choices.
- **Session:** 40 to 60 minutes per path; the book is a commitment, so signposting of progress
  matters.

### 3.6 Ages 16+

- Effectively adult interactive fiction: 60,000 to 118,000 words, up to ~677 nodes, full state
  modelling, quality-based gating, unreliable narration and structural irony available, tragic and
  pyrrhic endings permissible.
- The governing constraint stops being protection and becomes **coherence at scale**: continuity,
  state consistency, and voice stability across hundreds of nodes are what fails, and they are all
  in the [CODE] tier. Spend the budget there.

### 3.7 The monotone variables, stated as a table a machine can enforce

| Variable | 3-5 | 5-8 | 8-10 | 10-13 | 13-16 | 16+ |
|---|---|---|---|---|---|---|
| Options per choice | 2 | 2-3 | 2-3 | 2-4 | 2-4 | 2-4 |
| Consequence latency (nodes) | 0 | ≤1 | ≤3 (+1 long) | long | long | long |
| Threat resolution latency | ≤1 node | ≤2 nodes | ≤5 nodes | within act | unbounded | unbounded |
| Reversibility | total | high | medium | low | very low | none |
| Ending-valence floor | warm only | positive | survivable | bittersweet ok | unhappy ok | tragic ok |
| Protagonist death | never | never | off-page, rare | off-page | on-page | any |
| Tracked state variables | 0 | 0-1 | 2-4 | 4-8 | 8+ | many |
| Moral determinacy | single right | mostly clear | mixed motives | no right answer | complicity | full |
| Interiority | none | minimal | some | substantial | central | central |
| Interface operator | adult | shared | child | child | child | child |

---

## 4. How to measure book quality

### 4.1 Architecture of the scheme

Three tiers, with different coverage and different jobs.

| Tier | Coverage | Job | Cost |
|---|---|---|---|
| **T1 Computable** | 100% of books, 100% of nodes and paths | Hard gates: structure, continuity, premise, safety-adjacent, craft-rule violations | negligible |
| **T2 LLM judge** | sampled paths (5 to 12 per book), all endings | Path-level story quality, dilemma quality, foreseeability, agency, band fit | moderate |
| **T3 Human** | sampled books (editors: all; children: n per band per quarter) | Fun, voice, humour, dread, trust; and **calibration of T1 and T2** | high |

**Do not compute a single quality score.** Gate on a small set of hard constraints and report the
rest as a profile. A scalar invites optimisation, hides tradeoffs, and will be gamed within one
pipeline iteration.

### 4.2 T1: the computable metrics

Structure and integrity (hard gates, binary):
1. All nodes reachable from root; all paths terminate; no progress-free cycles; no non-ending sinks.
2. Path count; path-length distribution (min, median, max); no path shorter than the band minimum.
3. Branch-mass balance at every choice (F13).
4. Filler-node rate (F12).
5. Precondition dominance for every asserted fact and every choice requirement (F14, F15).
6. Entity/name/attribute consistency along every path.
7. Premise-entity coverage per path and causal presence at each climax (F17).
8. Second-person and character-consistency checks (F21).

Agency and craft (scored, with thresholds):
9. **Choice-label predictiveness** (F3): within-choice-set label→successor matching accuracy vs. chance.
10. **Callback density** (F2, R6): fraction of a path's choices later named in prose on that path.
11. **Reconvergence tinting rate** (F7/R7): fraction of multi-parent nodes with path-keyed variant text.
12. **Outcome-tuple ending distinctness** (F10): pairwise distinctness over extracted tuples.
13. **Protagonist agency ratio** (F5): volitional-verb agency of "you".
14. **Cosmetic-branch rate** (F1).
15. **Explore/comply outcome asymmetry** (F8): corpus-level, not per-book.
16. **Moralizing-coda rate** (F18).
17. **Reset-device rate** (F9).
18. **Cross-edge style discontinuity** (F16).
19. **Library-level stylometric diversity** and **intra-library structural repetition** (F20, section 5).
20. Reading-level band compliance plus cohesion floor (section 7).

### 4.3 T2: making LLM judges trustworthy

This is where most evaluation programmes quietly fail. The judge is not the hard part; the
*psychometrics of the judge* is.

**Judge only paths and books. Never nodes.** Node-level judging returns ceiling scores forever.

Non-negotiable controls:

- **Blinding.** The judge never sees provenance (human vs. machine, model, pipeline version,
  prompt). Provenance leakage is the fastest way to a useless eval.
- **Randomised presentation and position counterbalancing.** LLM judges have large, measurable
  position bias in pairwise comparisons. Present both orders and report the disagreement rate as a
  bias estimate; if order flips the verdict more than ~15% of the time, the dimension is not usable.
- **Anchored rubrics.** Every scale point gets a written anchor plus two real excerpts. Unanchored
  1-to-10 scales drift across time and compress to 6-to-8.
- **Prefer forced-choice to absolute scoring.** Pairwise "which path is a better story for a
  7-year-old" is far more reliable than a Likert score. Aggregate to a rating with Bradley-Terry or
  Elo. Absolute scores are for reporting only, never for gating.
- **Gold items in every batch.** 10 to 20% of each judging batch is known-answer material:
  human-authored published CYO paths as positives, seeded-defect variants as negatives. Track judge
  accuracy on golds *per batch*. **If gold accuracy falls below a preset threshold, discard the
  batch's results.** This single control is the difference between an eval and a ritual, and it is
  almost never implemented.
- **Judge-human calibration.** Quarterly, have editors (and for some dimensions, children) rate a
  sample the judge also rated. Report Spearman correlation and Krippendorff's alpha. **Publish the
  list of dimensions the judge is NOT trusted on** and refuse to gate on them. My prior: judges will
  calibrate acceptably on coherence, foreseeability, agency, premise fidelity, and band fit; and
  badly on humour, charm, scariness, and "would a child enjoy this".
- **Inter-judge and intra-judge reliability.** Three judges with different prompts and, ideally,
  different model families. Re-run identical items to measure self-consistency. A dimension with
  self-consistency below ~0.7 cannot be used for gating, only for triage.
- **Anti-Goodhart separation.** The judge must not share a prompt lineage with the generator, and
  the rubric text must never be visible to the generator. Rotate a held-out judge that is never used
  in any training or prompt-tuning loop.
- **The Goodhart alarm.** Plot judge score and human score over pipeline versions on the same axes.
  Divergence (judge rising, human flat) means the metric is dead. This is detectable and should be a
  standing dashboard, not an afterthought.

### 4.4 T3: humans, and what only they can give you

**Editors:** every book, under the sampling protocol in section 6.

**Children, think-aloud, n = 8 to 12 per band per quarter.** Instrument:
- At each choice, *before* revealing: "what do you think happens if you pick this one?" This
  directly measures label predictiveness against the actual reader, and is the ground truth for
  metric 9.
- After an outcome: "was that fair?" Measures unearned endings (F7) against the actual reader.
- After the path: **free recall.** "Tell me what happened." Free recall completeness is the single
  best comprehension measure available and it is nearly free. It also reveals whether the child
  remembers their choices as *theirs* (agency) or as things that happened.
- "Would you go back and try the other way?" Re-read intent.
- Blind pairwise against a published human-authored book of the same band. This is the acceptance
  test that matters, and it should be run every quarter with a fixed reference set.

**Parents:** would you hand this to another child; did you skip or edit anything; did it feel
written for *your* kid.

**Behavioural telemetry, the un-gameable ground truth.** This is the layer engineers will
under-weight because it is not a "quality" metric, and it is the most valuable one:
- completion rate of a first path,
- **second-path rate within 7 days** (the form's signature behaviour),
- abandonment node (a distribution over nodes tells you exactly where books die),
- time-to-first-choice and time-on-choice (long pauses = real dilemma; instant = obvious or
  meaningless),
- re-request rate for the same world/character,
- parent re-request and subscription retention.

**Proposed north star:** *fraction of delivered books for which the child completes at least one
path AND returns for a second path within 7 days.* Every metric above is a leading indicator of
that. If a metric moves and this does not, the metric is wrong.

### 4.5 Instrument validation: the seeded-defect corpus

**No metric ships until it has been shown to discriminate.** Build a validation corpus once, and
reuse it forever:

- **Positive controls:** 20 to 40 human-authored CYO paths/books across bands (public-domain,
  licensed, or commissioned). These must score high.
- **Seeded-defect negatives:** take each positive and programmatically inject one defect at a time:
  shuffle choice labels (F3); delete callback sentences (F2); collapse a tinted reconvergence to a
  shared node (F7); duplicate an ending with paraphrase (F10); replace the protagonist's decisions
  with an NPC's (F5); insert filler corridors (F12); truncate one branch (F13); move a
  key-establishing node so dominance breaks (F14); append a moral coda (F18); insert a dream reset
  (F9).
- **Negative controls that must fail *specific* things and pass others:**
  - fluent prose, zero agency (a linear story with fake choices): must fail F1/F3/F6, pass prose and
    readability;
  - structurally perfect, semantically empty (well-formed graph, generic text): must fail novelty,
    ending distinctness, premise fidelity, pass all structural gates;
  - excellent but off-band (a YA book scored as 5-to-8): must fail band fit, pass everything else.
  A metric that fails all three, or passes all three, is measuring "is this text", not "is this good".

**Per metric, report:** sensitivity, specificity, and the minimum detectable effect at realistic
book sizes. Concrete validation designs:

| Metric | Known-answer test | Expected result |
|---|---|---|
| Choice-label predictiveness | shuffle labels within book | falls to chance; human books stay high |
| Callback density | delete callback sentences | drops; and correlates with children's recall of their own choices in think-aloud |
| Ending distinctness (tuple) | paraphrase-duplicate one ending | caught; prose-embedding version must be shown to *miss* it, proving the tuple version earns its cost |
| Precondition dominance | relocate the key-granting node | fires with zero false positives on clean books |
| Agency ratio | rewrite protagonist as passenger | separates cleanly; if not, the parse is wrong |
| Dilemma pick-entropy | constructed obvious-choice set vs. classic dilemmas | wide separation, else judge is not usable |
| Curiosity tax | synthetic books with deliberately punished exploration | detected at corpus scale; **document that it is underpowered per book** |
| Foreseeability judge | seeded gotcha deaths | detected; and agrees with children's "was that fair?" |
| Band fit | cross-band mislabelling | judge recovers true band ≥ 80% |
| Readability suite | child oral-reading fluency + comprehension | report which measures actually predict; expect FK to underperform |

### 4.6 Gating policy

- **Hard gates (auto-reject, no human time spent):** structural integrity, precondition dominance,
  entity consistency, premise coverage per path, band-boundary violations (peril/valence/death
  rules), ~~safety~~ **safety, but see the note below**.

> **Safety is not a deterministic hard gate today, noted 2026-08-30.** This framework is written as
> an implementation requirement, so listing safety alongside the structural gates reads as a
> description of a control that exists. It is not.
> [The brief](../../../cyo-generation-research-brief-2026-08-22.md) states it plainly and it is
> still true on `main`: `validator/gate.py` calls its safety seam on any story clearing Layer 1, but
> `validator/safety.py`'s body is a Phase-2 no-op returning an empty report, so
> `GateResult.safety_flagged` is structurally always `False`. **Deterministic safety classification
> is unbuilt.** What protects a child today is the moderation classifiers, the LLM reviewer, and
> mandatory human approval, which are the model-judged and human-gated classes, not this one, and
> all three cost human time. Read this bullet as the target state. Anything that schedules from it
> must schedule building the classifier first, and must not assume "no human time spent" for safety
> in the meantime. `UW-C290` records the related register defect: SAFE-14 is still in the live
> application order while the module behind it is a stub.
- **Soft gates (surfaced to the human, not auto-rejected):** label predictiveness, callback density,
  ending distinctness, agency ratio, filler rate, tinting rate, style discontinuity.
- **Report-only (never gate):** anything with judge-human alpha below 0.6, and anything the
  generator could plausibly optimise directly.

---

## 5. Repeat-reader novelty

### 5.1 What the reader is actually tracking

Not plot, and not setting. Children re-read the *same* book happily, so mere similarity is not the
enemy. What kills a subscription is a different thing: **the recurrence of shape**.

My claim, stated as a falsifiable position: **perceived novelty is dominated by the structure of the
dilemmas, the placement and existence of surprise, the pattern of the endings, the role the child
plays, and the density of unshared concrete detail; and it is only weakly moved by setting,
character names, cover art, and node count.**

The argument: a child who has read five books whose shape is "friendly guide meets you at node 2,
three trials, choose kindness, warm ending" has read one book five times, even though it was a
dragon, then a robot, then a mermaid, then a knight, then a fox. This is the **re-skinning
fallacy**, and it is exactly what a template-plus-LLM pipeline produces by construction, because
the template is the thing being held fixed and the skin is the thing being varied. Conversely, five
books with the *same* protagonist in the *same* world, but structured as a mystery, a chase, a
negotiation, a rescue, and a heist, feel like five books.

There is a further, quieter novelty killer: **voice monoculture** (F20). A single stylistic
fingerprint across a library reads as "the same book" even when everything else varies, in the way
that a series ghostwritten by one hand does. This is invisible to any per-book metric.

And a counter-nuance that matters commercially: children *want* continuity. Series appeal in the 6
to 12 range is enormous. So the rule is the inverse of the naive one:

> **Hold the world constant if the child loves it. Vary the structure.**
> The naive pipeline does the exact opposite: it varies the world and holds the structure constant.

### 5.2 Levers predicted to move perceived novelty

1. **Structural signature.** The graph's actual shape: hub-and-spoke investigation; linear
   escalating gauntlet; two-act with a mid-book reversal; time loop; parallel viewpoints; heist
   (gather then execute); siege (defend a place over time); journey with a fixed destination.
   Maintain a per-child history and enforce distance.
2. **Dilemma axis.** The value tradeoff under test. If every book tests kindness-vs-curiosity, it is
   one book. Maintain an explicit taxonomy (loyalty/truth, safety/help, self/group, now/later,
   rule/mercy, courage/prudence, honesty/kindness) and rotate.
3. **Ending pattern.** Rotate over outcome types (section 1, R10). A library where every book ends in
   full success is one book.
4. **Tone register.** Funny, spooky, wistful, procedural, absurd, tender. Tone is highly memorable
   and is a stronger novelty lever than setting by some distance.
5. **The role the child plays.** Hero, helper, trickster, investigator, caretaker, outsider,
   saboteur. Changes the felt experience far more than the costume does.
6. **Genuine surprise, with varying placement.** A reversal the reader did not predict. Templates fix
   reversal position, which is why templated books feel identical even when their content differs.
7. **Density of unshared concrete detail.** Kids remember the jar of pickled eggs, not the plot.
   Measure the rate of concrete nouns unique to this book within the child's library.

### 5.3 Levers predicted to be placebo

Stated as predictions so they can be falsified:

- **Renaming characters and swapping settings** (the re-skin). Moves nothing after book 3.
- **More nodes, more branches, longer books.** Increases cost, not novelty. Possibly negative:
  longer books lower completion.
- **More endings, if they share outcome tuples.**
- **Synonym rotation / surface vocabulary variety.** Pure noise.
- **New cover art.** Moves *opens*, not *experience*. Worth doing; do not count it as novelty, and
  measure the two separately or you will fool yourself.
- **Higher generation temperature.** Produces variance, not novelty; variance in the wrong places
  (prose) and none in the right ones (structure).

### 5.4 The experiment that settles it

Two arms, same children, books 1 to 6:
- **Arm A:** vary setting, characters, and cover only; hold structure, dilemma axis, role, tone, and
  ending pattern fixed.
- **Arm B:** vary structure, dilemma axis, role, tone, and ending pattern; hold setting and
  characters fixed (same world, same protagonist).

Measures after book 5: "was this a new adventure?" (child), second-path rate, re-request rate,
free-recall distinctiveness (can the child tell books 2 and 4 apart?).

**Prediction: B substantially beats A.** If true, it reallocates the entire generation budget from
surface variety to structural variety, and it makes series a feature rather than a risk. This is the
cheapest high-information experiment available and it should be run before scaling.

### 5.5 Measuring novelty in production

Novelty is a **library-level** property. Maintain a per-child seen-vector over: structural
signature, dilemma axes, role, tone, ending patterns, creature/antagonist types, opening move,
climax type. Then:

- **Hard constraint:** a new book must exceed a minimum distance from the child's last K books on
  the *structural* facets.
- **Soft constraint (or none):** distance on setting and characters.
- **Library stylometry benchmark:** the internal stylistic diversity of one child's library must be
  at least as large as the diversity among five books by five different human authors. This is a
  clean, known-answer benchmark with a real reference distribution, and I have never seen anyone
  run it.

---

## 6. What a human reviewer should look at

**Budget assumption:** 15 to 30 minutes per book, for books up to 677 nodes. Design to that; a
protocol that assumes more will silently degrade into rubber-stamping, and a rubber-stamping human
is worse than no human because it manufactures false assurance.

**Principle:** the reviewer reads *paths*, is given *evidence* rather than raw text, and is
*measured*.

### 6.1 The protocol

**Step 0. Nothing reaches a human until every T1 hard gate passes.** Human attention must never be
spent on a broken graph.

**Step 1. Evidence page first (3 minutes).** Before any prose, the reviewer sees:
- the request as the family wrote it, and the band;
- a one-screen structural summary: node count, path count, path-length distribution, ending count
  and their extracted outcome tuples, branch-mass balance outliers;
- the top-20 risk-ranked nodes: highest moderation scores, most negative sentiment, peril
  vocabulary, largest style discontinuity, lowest judge scores, callback failures, premise-absent
  scenes;
- every soft-gate metric that fell below threshold, with the specific node or choice that caused it.

**Step 2. Read five paths, selected adversarially, not uniformly:**
1. the **modal path** (the route a typical child most likely takes; estimate from option
   attractiveness or from telemetry once you have it),
2. the **maximum-curiosity path** (always take the exploratory option),
3. the **worst-valence path** (leads to the darkest ending),
4. the **shortest path**,
5. one **uniformly random path**.

For books under ~200 nodes, read all five in full. For 300+ node books, read the modal path in full
and the others as generated path summaries plus the flagged nodes verbatim, with the ending read in
full every time.

**Step 3. 100% coverage of endings and flagged nodes, always.** Endings are few, high-stakes, and
where safety and tone failures land. No ending ships unread by a human. Track cumulative node and
edge coverage across a book's lifetime and surface never-read high-risk nodes.

**Step 4. The blind choice audit (3 minutes).** Present 8 to 10 randomly sampled choice points in
isolation, showing only the situation and the option labels, and ask the reviewer to predict what
each option leads to. Then reveal. Score the book on reviewer prediction accuracy. This is a direct,
cheap, human measurement of R3 (label honesty) and it is also the single best calibration exercise
for the automated predictiveness metric.

**Step 5. Two closing questions.**
- "Would you give this to a specific child you know in this band?" (binary, forces commitment)
- "Which one node would you cut or rewrite?" (surfaces the worst thing in the book in one answer,
  and is far more informative than any rating)

**Step 6. Decision, not a score.** Approve / approve-with-edits / regenerate-subtree / reject-premise.
Every rejection **must** carry a defect code from the F1-to-F22 taxonomy.

### 6.2 Series and repeat books: diff review

For book N in a series or in a heavily-shared-skeleton family, show only what is *new* relative to
the shared world bible and skeleton, plus a novelty report against the child's library. This is both
a large attention saving and the correct thing to review: the risk in book N is not the world, it is
the repetition.

### 6.3 Measuring the reviewer

**Seed 5% of the review queue with known-answer books:** seeded-defect negatives and known-good
positives, indistinguishable from real queue items. Track per-reviewer catch rate and false-reject
rate as a standing operational metric.

This is the human analogue of gold items, and skipping it is what makes "a human approves every
book" theatrical rather than real. Reviewers drift, fatigue, and pattern-match; if you are not
measuring it, you do not have a human gate, you have a human-shaped delay.

### 6.4 The flywheel

Every human-caught defect that no automated check flagged becomes a candidate check. Any defect
class caught twice by humans and zero times by code gets a check built, or an explicit written
decision that it stays human-only. The rejection stream is your best evaluation dataset and should
be treated as an asset, not as exhaust.

---

## 7. Reading level and pedagogy

### 7.1 What the standard formulas do

Flesch-Kincaid, Dale-Chall, Spache, ATOS, Fry, and Lexile all reduce, essentially, to two variables:
**average sentence length** and **word difficulty** (syllable count, or presence on a familiar-word
list). They were fitted by regression against mid-20th-century comprehension tests, on continuous
expository passages, for the purpose of *ranking* texts. Within that purpose they are useful and
cheap.

### 7.2 What they do not capture, and why it matters here

1. **Cohesion and inference load.** The dominant driver of narrative comprehension difficulty is how
   much the reader must infer across sentences, not how long the words are. Measure instead
   (Coh-Metrix-style): referential overlap between adjacent sentences, causal connective density,
   pronoun-referent distance, and referent ambiguity.
2. **Syntax beyond length.** Embedding depth, left-branching, non-canonical order, passives, and
   garden-path risk. "The horse raced past the barn fell" is short and hard.
3. **Vocabulary is not syllables.** What matters is frequency and age-of-acquisition, and whether
   the word is *supported by context*. The actionable metric is **unsupported rare words per 1,000**:
   words below a child-corpus frequency band that are neither glossed by context nor repeated.
4. **Narrative load.** Number of simultaneously active characters, POV shifts, time jumps,
   flashbacks, dialogue attribution clarity, figurative-language density. All of these dominate
   sentence length in practice.
5. **Decodability**, for 5-to-8 and below. Proportion of words inside taught phonics patterns, and
   sight-word coverage. Formulas are blind to this and it is the whole ballgame for a transitional
   reader.
6. **Read-aloud quality**, for 3 to 5. Syllable rhythm, rhyme, repetition, sentence-final stress.
   Nothing standard measures it; a human reading one path aloud does, in two minutes.
7. **Interactive-format load, unique to CYO and measured by nobody.** The child must hold the
   situation in working memory, compare options, and act. Measure:
   - **choice-label reading level**, which should be *below* the body level (labels are scanned, not
     read);
   - **option length parity** (R4): longer options are picked more often regardless of content, a
     real and measurable bias;
   - **option count** and **carried-state load** ("you still have the key, the promise, and the
     map" is three things to remember).

### 7.3 The critical warning

**Optimising a readability formula downward makes comprehension worse.** An LLM told to hit grade 3
will chop sentences into staccato fragments, deleting exactly the connectives ("because", "so
that", "even though") that make causality explicit. Sentence length falls, the score improves, and
the child understands less. This is not hypothetical; it is the predictable behaviour of the
instruction.

Therefore:
- Express readability as a **band with a floor and a ceiling**, never as an objective to minimise.
- **Pair it with a cohesion floor**: causal connective density must not fall below the band's
  reference range measured on human-authored books of that band.
- Validate against children, not against the formula.

### 7.4 What to measure instead, as a suite

Per band, compute: readability band compliance (FK/Spache/Dale-Chall as a range check);
unsupported-rare-word rate; referential cohesion; causal connective density; mean and variance of
sentence length (variance matters: uniform sentence length is a machine tell and is unpleasant to
read aloud); active-character count per scene; dialogue-attribution clarity; decodability (young
bands); choice-label level and option parity; and figurative-language density.

### 7.5 Pedagogy: what to claim and what to measure

The honest pedagogical claims for this product are two, and neither is "reading level".

1. **Vocabulary stretch.** A small number of new Tier-2 words, each used at least twice, each
   supported by context, is the best-evidenced lever available. Target roughly 1 to 3 novel words per
   1,000, with in-context support and a second exposure. Measure retention with a delayed probe in
   child sessions.
2. **Causal reasoning and prediction.** This is the *format's* native gift and nobody else can claim
   it. Choices designed to be predictable-with-thought, plus callbacks that reward attention, train
   exactly the skill of forecasting consequences. Measure it directly: **does the child's prediction
   accuracy at choice points rise across a book and across books?** That is a real, publishable,
   defensible learning claim, and it falls straight out of the think-aloud instrument already
   described.

### 7.6 Validating the readability suite

Sample children per band; collect oral reading fluency (words correct per minute), free-recall
completeness, and comprehension questions on real generated paths. Regress each proposed measure
against child performance. Report which measures predict and which do not. **Expected result:
Flesch-Kincaid will be a weak within-band predictor, and unsupported-rare-word rate plus referential
cohesion will beat it.** If that is not the result, the sampling or the extraction is wrong, and
that is worth knowing too.

---

## Checklist: quality requirements a CYO generation system must satisfy

1. Every node in the book is reachable from the root node.
2. Every path from the root terminates at an ending node; there are no progress-free cycles and no non-ending sinks.
3. Every root-to-ending walk independently contains setup, escalation, crisis, and resolution, verified by a path-level judge.
4. No path is shorter than the minimum path length defined for the book's age band.
5. Every choice presents options with a genuine value tradeoff, such that no option is dominant.
6. At every choice point, a blind judge panel picks the same option less than 80% of the time.
7. No choice label is direction-only or content-free ("go left", "yes", "option A").
8. Every choice label names both an action and an intention.
9. Choice-label predictiveness (label-to-successor matching accuracy) exceeds chance by a validated margin for the book as a whole.
10. Every choice label's promise is delivered by its successor node, verified by judge and by the human blind choice audit.
11. Options within a choice set are within 30% of each other in length and are grammatically parallel.
12. Options within a choice set do not differ systematically in framing valence.
13. Number of options per choice is within the band's prescribed range (2 for ages 3-5; 2-4 above).
14. Consequence latency for every choice is within the band's prescribed maximum.
15. At least 60% of the choices on any path are textually referenced later on that path (callback density).
16. Every node with more than one incoming path contains at least one variant sentence keyed to the path taken.
17. No two options at a choice lead to the same node, or to subtrees with semantic similarity above the cosmetic-branch threshold.
18. At every choice, no option's reachable subtree is smaller than 25% of the largest, unless declared an early-ending arm.
19. Filler nodes (out-degree 1, no new entity, no state change, no new information) are under 15% of all nodes.
20. Every fact asserted as known in a node is established on every path that reaches that node (precondition dominance holds).
21. Every choice that requires knowledge or an item is only offered on paths where that knowledge or item was obtained.
22. Character names, ages, genders, appearances, and possessions are consistent along every path.
23. Narration remains in the intended person and tense throughout.
24. The reader-character is the agent of at least 60% of scene-turning actions on every path.
25. No path resolves primarily through an NPC deciding, explaining, or rescuing.
26. Every ending is foreseeable in hindsight from information available on the path that reached it.
27. Every ending is causally attributable to at least one choice the reader made.
28. No negative-valence ending is reachable in fewer nodes than the band's minimum path length.
29. Endings are distinct on extracted outcome tuples, not merely on prose.
30. The set of endings spans more than one outcome type and does not reduce to a single desirability ordering.
31. Ending valence distribution complies with the band's ending-valence floor.
32. Protagonist death and companion death comply with the band's rules, which are **not the same
    rule** and must be checked separately. *Protagonist:* never below age 8; at 8-10, off-page,
    abstracted, avoidable in hindsight, and rare. *Companion:* never below age 8; at 8-10, **a
    beloved companion is not killed at all**. *Split 2026-08-30: this item previously read
    "Protagonist and companion death comply with the band's rules (never below age 8; off-page and
    rare at 8-10)", applying one parenthetical to both and thereby licensing at 8-10 exactly what
    section 3.4 prohibits outright ("Do not kill a beloved companion at this band"). A checklist
    that permits prohibited content is worse than a missing checklist item.*
33. Peril is present: every path contains at least one beat in which the protagonist wants something they might not get.
34. No ending appends an explicitly stated moral lesson.
35. No path resolves via a reset device (dream, rewind, "luckily nothing happened").
36. Every requested premise entity appears on every path, and is causally involved in every path's climax.
37. The book's structural signature, dilemma axis, protagonist role, tone, and ending pattern exceed the minimum distance from the requesting child's last K books.
38. The book's stylistic fingerprint is distinguishable from the other books in that child's library at a rate matching the human-authored reference distribution.
39. Style discontinuity across every edge is below the flagged-percentile threshold.
40. Body-text readability falls inside the band's floor-and-ceiling range, not merely below the ceiling.
41. Causal connective density is at or above the band's human-authored reference floor.
42. Unsupported rare words per 1,000 are below the band's threshold.
43. Sentence-length variance is within the band's human-authored reference range (not uniformly short).
44. Choice-label reading level is at or below the body-text reading level.
45. Simultaneously carried state items do not exceed the band's working-memory limit.
46. For bands below age 8, decodability and sight-word coverage meet the band's threshold.
47. All T1 hard gates pass before any human reviewer sees the book.
48. A human reviewer has read the modal, maximum-curiosity, worst-valence, shortest, and one random path.
49. A human has read 100% of ending nodes and 100% of risk-flagged nodes.
50. A human has completed the blind choice audit and the book met the reviewer prediction-accuracy threshold.
51. The reviewer recorded a binary "would give to a child in this band" answer and a defect code for any rejection.
52. Every LLM judge used for gating carries gold items in each batch, and the batch's gold accuracy met threshold.
53. Every LLM judge dimension used for gating has published judge-human agreement at or above the preset bar.
54. Judge scoring is blinded to provenance and counterbalanced for position, with measured position bias below threshold.
55. No metric used for gating has been exposed to the generator's prompt or training loop.
56. Every shipped metric has documented sensitivity and specificity against the seeded-defect corpus.
57. Every shipped metric passes the three negative controls (fluent-but-agency-free, structurally-perfect-but-empty, excellent-but-off-band) by failing the intended dimension and passing the others.
58. Corpus-level curiosity-tax statistics are computed over the pipeline and show no systematic penalty for exploratory options.
59. Judge scores and human scores are tracked jointly across pipeline versions, with divergence treated as metric failure.
60. Reviewer catch rate is measured via seeded known-answer books in the review queue.
61. Child think-aloud sessions are run at the stated cadence per band, covering prediction, fairness, free recall, and re-read intent.
62. The book's band is validated by blind pairwise comparison against a fixed reference set of human-authored books of that band.
63. Behavioural telemetry (completion, second-path-within-7-days, abandonment node, re-request) is collected and is the arbiter when metrics and outcomes disagree.
