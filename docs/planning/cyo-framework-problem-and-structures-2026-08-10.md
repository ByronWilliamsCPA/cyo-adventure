# The CYO authoring framework: problem, model limits, and every structure tried (2026-08-10)

> Synthesis document. It states the problem the authoring framework exists to solve, the
> specific model limitations that rule out generating a book in one pass, and each structure
> tried against them with its measured weakness. It introduces no new proposal; every number
> here is traceable to a pilot, a lesson row, or a file in this repo.
>
> Scope caveat stated once, up front: most diversity measurements come from pilots on
> `the-clocktower-cipher`, a 26-node skeleton that is off the ADR-011 cell matrix and not
> production-eligible (`AL-176`). It was chosen because it is the only skeleton with both a
> hygiene-passed contract and a recognition baseline under an identical protocol. The
> mechanisms below are well evidenced; the catalog-level magnitudes need replication on a
> production cell.

---

## 1. What the framework has to produce

A guardian requests a story; a child reads a branching book on a tablet, offline. Between
those two events the system must produce an artifact that satisfies all of the following at
once, with no human writing prose:

| Requirement | Where it is enforced |
| --- | --- |
| Structurally valid graph: reachable, terminating, no trap loops | `validator/` Layer 1 |
| Age-band appropriate: word envelope, reading level, ending economy, arc floors | `validator/band_profile.py`, `reading_level.py` |
| Safe for the band, with content-flag ceilings and denylists | `band_profile.py`, `moderation/` |
| Condition and effect coherence across branches | `storybook/` condition evaluator, `validator/walk.py` |
| Human-approved before publication | ADR-005, non-negotiable |
| **Distinct from the other books this same child has read** | the open problem |

The first five are solved and enforced by deterministic code that does not care where a
story came from. The sixth is the subject of this document, and it is the one requirement
that cannot be checked on a single artifact: it is a property of a *pair*, relative to one
reader's memory.

**The unit of exposure is the child, not the family** (owner correction, 2026-08-09). Two
children in one household can read the same book without either noticing. One child reading
two books built from the same armature notices immediately. That is what makes diversity a
scaling constraint rather than a polish item: a skeleton is consumable within a child and
reusable across children (`AL-173`).

## 2. The scale that rules out the obvious approach

The catalog's 61 skeletons are not short:

| Band | Skeletons | Nodes (min / median / max) | Words per node | Median book |
| --- | --- | --- | --- | --- |
| 3-5 | 7 | 11 / 20 / 32 | 40 | ~800 words |
| 5-8 | 6 | 35 / 57 / 62 | 70 | ~4,000 words |
| 8-11 | 9 | 65 / 121 / 191 | 100 | ~12,100 words |
| 10-13 | 11 | 26 / 149 / 250 | 100 | ~14,900 words |
| 13-16 | 14 | 124 / 277 / 551 | 140 | ~38,800 words |
| 16+ | 14 | 33 / 248 / 677 | 175 | ~43,400 words |

Total across the catalog: 11,458 nodes. The largest skeleton is 677 nodes, which at its
band's word target is roughly **118,000 words of branching prose** whose every path must
terminate, stay in reading level, and never contradict itself at a merge.

"Decent size" in this product is not a long short story. It is a novel with a graph.

## 3. Why one call cannot do it

The original finding, which created the skeleton, was that given only a story-concept
prompt the model could not produce acceptable structure and acceptable prose at the same
time. Everything since has refined *why*, and the reasons are not all the same kind of
limit. Four are capability limits; the fifth is a property of the model that no amount of
capability fixes.

### 3.1 Two jobs competing for one budget

Structure and prose are different tasks with different failure modes, and asking for both
in one pass degrades both. This is the original observation and it still holds for a single
call. It is worth being precise that it was measured against **zero-shot, single-call**
generation, which is not the same thing as measuring the model's ceiling: agents with
checkers in the loop have since authored a 31-fact narrative contract that passed every NC
check first try, and closed a 20.4-to-1.2 convergence gap in one revision round with no
human repair. The limit is on one unaided pass, not on the model in a harness.

### 3.2 Whole-graph invariants are not locally checkable

The binding constraints are global. Reachability and termination are properties of the
whole graph. Merge-node coherence is worse: a node with several parents must be writable
from every path into it, so its author must know exactly what a reader could and could not
know on arrival, across all incoming paths. That is a must-analysis fixpoint over the
graph (the NC-1 check computes it), not something a model can evaluate while writing node
200 of 277.

### 3.3 Output length

A 39,000-word median book at 13-16, and a 118,000-word maximum at 16+, exceed what a single
generation produces. Any approach is therefore staged or chunked, which immediately
reintroduces 3.2: each chunk must be written against invariants held outside it.

### 3.4 Constraint-following degrades as constraints accumulate

The strict authoring bar (satisfying-walk floors, max-indegree caps, depth-qualified
endings) passes **2 of 61** catalog skeletons, and 0 of 11 at 10-13 (`AL-176`). Those
skeletons were largely human-reviewed. The bar is a stack of individually reasonable
constraints that are jointly very hard to satisfy, which is the regime a single generation
call is worst at.

### 3.5 Same-model idiom convergence, which is the one that matters

Two agents on the same model, given different contracts, different settings, different
device vocabularies, and no access to each other, still produce identical phrases. Measured
directly in this work: two isolated fills shared 21 verbatim 4-grams including *"a sky gone
properly dark"* and *"carry the rhythm up"*, phrases that appear in none of the input files.
After a revision round removed those, both agents independently rewrote *"Climb the spiral
stair."* to the identical *"Head up the spiral stair."*

This is not a prompting defect. It is a property of sampling the same model twice, and it
sets a floor on how different two books can be when both are written by the same model
against the same armature. It is also fixable per-pair by a gate-revise-regate loop
(`AL-165`), which is why the deterministic convergence numbers look solved while the
perceptual ones do not.

## 4. Every structure tried

Chronological. Each entry states what it bought, and the measured reason it was not
sufficient.

### S0. Zero-shot single call

**Idea.** Prompt with a story concept; get a book.
**Result.** Failed on structure and prose simultaneously. This is the finding that motivated
everything below.
**Weakness.** See section 3. Never a serious candidate at catalog scale.

### S1. Staged pipeline, no skeleton (`generate_story`)

**Idea.** Split the job across calls: Stage A builds structure, Stage B writes prose, Stage
C does bounded repair.
**Status.** Live and shipped (`generation/orchestrator.py:635`); `generation/worker.py`
routes to it whenever a job carries no `skeleton_slug`, and a storybook with
`skeleton_slug = NULL` is a first-class row. The skeleton-free path is not hypothetical.
**Weakness.** It was judged inadequate, and a later survey itemized why. The defects are
smaller and more specific than "the model cannot do structure":

1. It is validated by a **weaker bar** than skeletons are. The strict checks live in
   `scripts/check_skeleton.py`, are `--strict`-only, carry no validator rule id, and never
   run on generated stories.
2. Structural targets are **bounds, not distributions**. The gate accepts a 60-node stick
   and a 60-node bush identically.
3. Topology is **descriptive, not prescriptive**. Six labels collapse into three graph-shape
   classes and no code realizes a topology.
4. It has **no fidelity check**: `orchestrator.py` passes `stage1=None`, so the "did the
   model quietly rewrite the structure" assurance the skeleton path gets by diffing against
   its pre-fill reference does not exist.
5. There are **no per-node word targets** at construction time, so the word envelope, the
   minutes clock, and the arc floors become post-hoc rather than plannable.
6. The **differentiation machinery is skeleton-only**: the anti-repetition directive is
   built inside the `skeleton_fill` branch, and `generate_story` takes no differentiation
   parameter at all.

Note (4) and (6) especially: in any diversity comparison, the skeleton arm receives
anti-repetition help the skeleton-free arm does not, which is an arm-level confound rather
than a property of either architecture.

### S2. Pre-authored skeleton with sentence-level beats

**Idea.** A human authors the graph once; each node body carries
`<<FILL role=... words=N beats='...'>>`; the model writes only leaf prose.
**What it buys.** Three things, and only the first is a capability claim:
*cognitive offload* (the model never holds the graph), *amortized human verification* (one
reviewed artifact serves many books), and a *predictable envelope* (node count, depth, clock
known before generation). The second is a cost optimization, not a safety property, because
ADR-005 requires human approval of every finished story anyway. The third is recoverable
from a freshly built graph by existing code.
**Weakness.** The beats *are* the book. Measured prescription ratio (beat words to prose
words) is **0.83 at 3-5**, meaning the skeleton writes four fifths of a toddler book in
outline, and **0.40 catalog-wide**. Beats also caused a theme-leak class by carrying
un-slotted world facts (snow, "fireflies chirped"). And of nine historical justifications
for pinning beats at sentence level, an audit against the live gate found **two survive**:
no blocking validator rule reads a beat's semantic content.

### S3. Parameterized skeletons and theme contracts (ADR-019)

**Idea.** Give skeletons `{SLOT}` tokens in beats, ending titles, and choice labels; bind a
theme per request through a deterministic, pre-LLM slot validator.
**What it buys.** Real per-request variation on every slotted surface, checked before an LLM
call is spent.
**Weakness.** It varies exactly what is slotted and freezes everything else, byte-identically,
across every binding. Two of three ending titles were byte-identical because they carried no
slot (`AL-161`). This work found the same defect one level down and still unfixed:
**13 of 35 choice labels** in the pilot skeleton carry no slot token, so strings like
`Climb the spiral stair.` and `Spin the hands at random and hope.` are identical in every
book ever generated from it. NC-8 warns about unslotted *ending titles* and says nothing
about *choice labels* (`AL-184`), even though choice-menu semantics had already been named
as the residual recognition channel.

The general shape of the weakness: **an enumerating scheme silently exempts everything it
does not enumerate.** This recurs (section 5.4).

### S4. Narrative obligation contracts

**Idea.** Replace prescriptive beats with a per-node contract declaring what the scene is
*for*: `tier`, `function`, `entry_state`, `establishes`, `forbids`, `affect`, `beat_hint`,
`constraints`, `choice_semantics`. Prose is then free as long as the obligations land.
**What it buys.** A large, real reduction in prescription, plus machine-checkable coherence:
NC-0..NC-8 prove the fact graph closes at merges before any prose exists.
**Weakness, two of them.**
First, the ceiling moved down but did not lift: three pilots each pushed sameness one layer
lower (beats, then contract concreteness, then decision grammar) and sibling fills still read
as "same adventure, new world."
Second, and structural: **obligations are declared, proved coherent, and never verified
against the prose** (`AL-167`). A fill decoded the cipher at a node whose contract forbids
`cipher_decoded`, voiding a downstream branch, and passed every gate, because the NC checks
run pre-prose and nothing re-reads the finished text against the contract.

### S5. Per-request device pools and story bibles

**Idea.** Stop freezing props, clues, obstacles, and safeguards in the skeleton; draw them
per request from a per-binding bible, gated on Mechanic Divergence.
**Result.** **Solved, on its own terms.** MD moved from 0.41 to 0.90+; the arms in this
work scored **0.978** against a 0.34 threshold.
**Weakness.** Recognition unmoved. Changing the objects in the rooms does not change the
rooms. Separately, the metric has a blind spot: MD is **category-scoped**, so it certified
these two bibles at 0.978 while one book's `cipher_hint_carriers/pattern_in_mechanism`
("long, long, short") and the other's `cipher_forms/rhythm_code` ("read each pull as long or
short") were the same device that had merely moved category. The blind rater caught it
unaided: *"the two books' secret codes are the same code"* (`AL-185`).

### S6. Prose-level intervention (gate-revise-regate)

**Idea.** Measure verbatim convergence between sibling fills and feed it back to the author
for a revision round.
**Result.** **Solved, on its own terms**, and it works agentically in one round with no
human repair: shared 4-grams fell from **20.4 to 1.2 per 1000** (`AL-165`), and in this work
from 6.4 to 2.7 with menu frames from 4 to 0.
**Weakness.** Recognition unmoved. Two books can share almost no wording and still be the
same book.

### S7. Model tier (frontier / Sonnet / Haiku)

**Idea.** Perhaps sameness is a capability artifact that a better model escapes.
**Result.** Blind craft scores ran **4.9 / 4.0 / 2.2** across frontier, Sonnet, and Haiku,
while every tier passed every structural gate first-pass.
**Weakness.** Recognition scored **2.5 at both ends of the tier range**. Model tier moves
prose *quality* and not *sameness* (`AL-168`). Useful for cost decisions (Sonnet is the
shipping floor for prose; Haiku is fine for mechanical roles), useless for diversity.

### S8. Per-request mutation of skeletons (ADR-020)

**Idea.** Multiply the catalog by mutating a skeleton per request: sibling-subtree swap
(M1), ending remap (M2), prune/graft (M3), vary-decisions (M4), state variation (M5).
**Result.** **Refuted as a multiplier.** M1 and M2 produce `structural_distance` of exactly
0.0000 from the parent. A maximum-length three-operator chain using only the parent's own
material reached 0.0064, against a promotion floor of 0.05. The only mutant that cleared the
floor did so by grafting 32 nodes from a **different** catalog skeleton, which is
recombination of two trees rather than multiplication of one.
**Weakness, decisive.** All mutants retain **100% of the parent's authored FILL beat
directives**. Whatever the operators change, they do not change the story the author wrote;
they change where two or three edges point.

### S9. Obligation variance (executed 2026-08-10)

**Idea.** The one layer never varied. Every pilot gave each node **one fixed instruction**
shared by every fill of that skeleton; the redesign changed that instruction's *form* but
not its *constancy*. So: author N complete, individually NC-clean contracts over one
unchanged graph, in which nodes serve genuinely different narrative functions.
**Result.** **Refuted, decisively.** Recognition landed at **position 2** against a
pre-registered margin of past position 5, with distinctness **2.0** against the control's
2.5, while all six quality guards passed (so the result was not bought by degrading the
books).
**Why, and this is the useful part.** The contracts varied `choice_semantics` completely at
the landing nodes:

- v2 `n_start`: *"lead with patience / lead with self-reliance / lead with humility"*
- v3 `n_start`: *"follow the maker's own words / his handiwork / his confidant"*

The blind rater nonetheless recorded the same fork in the same order at position 2 and the
same four-room fan at position 5, because a choice's **destination is a graph edge, not
contract content**:

```
n_start  -> n_note, n_door, n_keeper
n_inside -> n_stairs, n_study, n_pendulum, n_basement
```

Whatever a contract says a choice *means*, choice 1 still leads to the note-decoding scene,
and both authors must still write a stair, a study, a catwalk, and a basement. **A reader
perceives where the choices lead, not why the contract says they are offered.**

## 5. What the whole sequence adds up to

### 5.1 One table

| Layer varied | Outcome on its own terms | Effect on recognition |
| --- | --- | --- |
| Devices (S5) | Solved: MD 0.41 to 0.978 | **Unmoved** |
| Prose (S6) | Solved: 20.4 to 1.2 grams per 1000 | **Unmoved** |
| Model tier (S7) | Moves craft 4.9 / 4.0 / 2.2 | **Unmoved** (2.5 both ends) |
| Obligations (S9) | Delivered, all guards green | **Worse or unmoved**: position 2 |
| Graph shape (S8) | Refuted: 0.0000-0.0064 vs a 0.05 floor | **Moved**, to position 3 |
| Cross-skeleton graft | Cleared the floor at 0.0726 | not separately rated |

### 5.2 The reading

Devices change the nouns in the rooms. Prose changes the wording. Model tier changes the
quality. Obligations change why the rooms matter. **None of them changes the rooms, because
the rooms are edges.** The only intervention that moved recognition at all was the one that
changed the graph, and the only mechanism that ever cleared the anti-clone floor was
recombining two graphs.

The recognition fingerprint is the **topology**: the sequence of scene functions and the
set of destinations at each fork. Everything the framework currently varies sits downstream
of it.

Stated as the practical consequence: **single-use per child is inherent to a shared
armature.** A skeleton can serve many children and should; it cannot serve one child twice.
Catalog diversity therefore comes from *more graphs*, which means catalog depth per cell and
possibly cross-skeleton recombination, not from a better format inside one graph.

### 5.3 What this does *not* say

It does not say the skeleton was a mistake. Structure-off-the-model remains correct, but the
justification has shifted: it is now a cost and review argument (amortized human
verification, predictable envelope, cheaper failure modes) rather than a claim that the
model cannot carry structure. Point 3.1's caveat matters here, and the cheapest outstanding
experiment is still to run the existing `generate_story` path against the full pilot bench
plus the strict bar, which either shows it is closer than believed or produces an itemized
defect list for the price of one run.

### 5.4 The measurement apparatus is itself a finding

Several "results" in this program turned out to be artifacts of how they were measured. This
matters more than any single intervention, because it is the part that will keep producing
false conclusions if left alone.

- **The deterministic bench cannot see the thing we care about.** The treatment pair scored
  PS 0.548 / leaf 0.095; the control pair PS 0.547 / leaf 0.094. A pair sharing its
  obligations and a pair not sharing them are indistinguishable on this bench, while a
  human rater separated them instantly. These metrics must not be used as a diversity gate.
- **A stub reported as evidence.** `validator/safety.py` SAFE-14 is a Phase-2 stub returning
  an empty report unconditionally, so `safety_flagged=False` is a constant. It was reported
  as safety evidence seven times across pilots (`AL-175`).
- **Calibrated thresholds carry a protocol stage.** The 4.0 shared-grams budget is
  calibrated on *post-revision* output. Gating un-revised output against it produced a false
  guard failure in this run; at matched stage the treatment pair (6.4) was *less* convergent
  than the control had been (9.0) (`AL-186`).
- **Enumerating bars exempt what they omit.** The variant-admissibility bar listed four
  fields and `beat_hint` was not among them, so two contracts passed at 26/26 nodes while
  their beat hints were the shipped contract's sentences with single nouns swapped. Caught
  before the run, but only by looking outside the bar (`AL-182`). This is the same failure
  shape as S3's unslotted labels.
- **Isolated review is more forgiving than comparative review.** The same books scored 2.2
  and "rewrite" in isolation versus 3.0 and "light edit" comparatively (`AL-169`). Whatever
  the approval surface shows a reviewer determines what they will approve.
- **Isolation between parallel authors leaks through the filesystem**, and identical briefs
  still produce asymmetric effort (`AL-187`).

## 6. Open questions, in the order worth answering

1. **Does catalog depth actually solve it?** A child exhausts a cell by roughly their fourth
   request at 3-4 skeletons per cell, and demand concentrates on medium length while the
   catalog is flat across lengths (`AL-174`, `AL-177`). Depth against the demand curve is the
   currently-recommended path and it is a capital question, not a research question.
2. **Is cross-skeleton recombination real?** It is the only mechanism that has ever cleared
   the anti-clone floor, and it has never been evaluated for reader-perceived distinctness or
   for coherence cost.
3. **How close is the skeleton-free path really?** Cheapest outstanding experiment; see 5.3.
4. **Can the topology finding be replicated on a production-eligible skeleton?** Everything
   above rests on n=1 with separate rater instances on an off-matrix seed. The mechanism is
   sound; the magnitudes are not yet portable.
5. **Does the fill match its contract?** S4's second weakness is unaddressed: nothing
   verifies finished prose against the node obligations it was written to satisfy.

## 7. Related documents

- [Skeleton narrative redesign proposal](./skeleton-narrative-redesign-proposal-2026-08-09.md),
  pilots 1 to 3 and the model-tier study (sections 10 to 13)
- [Alternatives to the pre-authored skeleton](./skeleton-free-alternatives-proposal-2026-08-09.md),
  the A1-A6 option set, the exposure analysis, and the mutation refutation
- [Obligation-variance experiment spec and results](./obligation-variance-experiment-spec-2026-08-09.md),
  section 12
- [Authoring lessons log](./authoring-lessons-log.md), `AL-151` onward for this program
- [Unscheduled work register](./unscheduled-work-register.md), `UW-C93` onward
- ADR-011 (story scale framework), ADR-019 (parameterized skeletons),
  ADR-020 (mutation-derived skeletons), ADR-005 (mandatory human approval)
