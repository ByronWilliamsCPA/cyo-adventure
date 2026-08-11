# Experiment spec: does obligation variance break single-use? (2026-08-09)

> Owner-requested after the mutation pilot refuted per-request mutation as a catalog
> multiplier. This is the decisive test of whether a skeleton must be single-use per child.

## 1. The question

A child who reads two fills of one skeleton reaches the same-book verdict by node 3 or 4.
Every intervention tried so far has failed to move that. **Is single-use inherent to a
shared armature, or is it an artifact of the one layer we have never varied?**

## 2. What is already ruled out

Do not re-test these. Each was measured on this project's own protocol:

| Layer varied | Result | Recognition |
| --- | --- | --- |
| Devices (props, clues, obstacles, safeguards) | Solved: MD 0.41 to 0.90+, all clue margins pass | Unmoved |
| Prose (wording, labels, titles) | Solved: 20.4 to 1.2 shared grams per 1000, 0 menu frames | Unmoved |
| Graph shape (M1/M2/M4 mutation) | Refuted: distances 0.0000 to 0.0064 against a 0.05 floor | Landed at position 3 |
| Model tier (frontier / Sonnet / Haiku) | Moves prose quality (4.9 / 4.0 / 2.2), not sameness | 2.5 at both ends |

## 3. The untested layer

In every pilot, each node carried **one fixed instruction**, shared by every fill of that
skeleton. The redesign changed the instruction's *form* (from `beats='...'` to a contract
entry carrying `beat_hint`, `establishes`, `forbids`, `choice_semantics`, `constraints`),
but not its *constancy*. Two fills of one skeleton were always told the same thing about
what each scene is for.

That is the remaining candidate fingerprint, and it explains the otherwise puzzling
results: mutants read as the same book despite different graphs (they preserved 100% of
the parent's beats), and isolated authors converged despite different devices (they shared
the obligations).

**The reason to expect this to work is that the same treatment already succeeded one level
down.** Devices were frozen; making them a per-request draw from a pool moved MD from 0.41
to 0.90. Ending mechanisms were frozen; making them a per-request draw passed every
distinctness margin. The obligations themselves were never given that treatment.

## 4. Design

**Intervention: N complete contract variants over one unchanged skeleton graph.**

Per-node independent pools are rejected: NC-1 merge closure is a whole-graph property, so
independently drawn per-node obligations would not compose into a coherent fact graph. The
unit of variation is therefore a **complete, individually NC-clean contract** over the same
nodes and edges, in which nodes serve different narrative functions.

A variant is only admissible if it changes what nodes are *for*, not how they are worded.
Two criteria, both enforced per node and per contract pair by
`docs/planning/evidence/obligation-variance/check_variant_divergence.py --check`:

1. **Field divergence.** A given node must differ in at least two of `establishes`,
   `choice_semantics`, `affect`, and its `function` label. Rewording a `beat_hint` while
   keeping the same establishes and semantics is a paraphrase, not a variant.
2. **Beat-hint divergence.** `beat_hint` similarity must stay below 0.60 (difflib ratio),
   against every other variant including the shipped v1.

**Criterion 2 was added after the first draft passed criterion 1 and was rejected anyway**
(AL-182). That draft's `beat_hint` strings were v1's sentences with single nouns swapped:
byte-identical at `n_end_library` across all three variants, at or above 0.85 at 10 of 26
nodes against v1, and above 0.60 at 22 of 26. Criterion 1 could not see it because
`beat_hint` is not one of its four fields, an omission in the original bar rather than a
finding about the draft. That matters because `beat_hint` is the most direct instruction a
fill agent reads: holding it constant leaves the intervention largely undelivered, and
would make the most likely outcome uninterpretable, since "obligation variance does not
work" could not then be separated from "the obligations were never varied."

**Arms.**

| Arm | Skeleton | Contract | Binding | Source |
| --- | --- | --- | --- | --- |
| Control A | the-clocktower-cipher | variant 1 (shipped) | harbor observatory | `filled_H_a.json`, already measured |
| Control B | the-clocktower-cipher | variant 1 (shipped) | carousel pavilion | `filled_H_b.json`, already measured |
| Treatment C | the-clocktower-cipher | **variant 2 (new)** | river lock-house | new fill |
| Treatment D | the-clocktower-cipher | **variant 3 (new)** | a fourth binding | new fill |

The control pair costs nothing: it was rated in the third pilot at **recognition node 4,
score 2.5**, under this exact protocol and rubric. The treatment pair varies binding *and*
obligations where the control varied binding alone, so the contrast isolates the
obligation effect.

**Why this skeleton.** It is not production-eligible and sits off the ADR-011 cell matrix
(AL-176), which disqualifies it for catalog-level conclusions. It is nonetheless the right
choice here because it is the only skeleton with a hygiene-passed contract **and** a
measured recognition baseline under the identical protocol. A within-subject comparison
against a known number is far stronger at n=1 than a fresh skeleton with no anchor.
Generalization to a production cell requires replication and is out of scope.

## 5. Held fixed

Skeleton graph, node ids, edges, ending kinds and valences, band (10-13), the fill protocol
(agent authors from files), the rater rubric and its anchors, and the deterministic bench.

## 6. Pre-registered margins

| Outcome | Margin | Control baseline |
| --- | --- | --- |
| **Recognition landing (primary)** | past `n_inside` (position 5), or no landing | node 4 |
| Five-point distinctness | > 2.5 | 2.5 |
| NC-0..NC-8 on each new contract | clean, errors 0 | clean |
| Fill integrity (`--allow-title-rewrite`) | exit 0 both fills | met |
| Full validator gate | not blocked, both fills | met |
| Sibling grams per 1000 | <= 4.0 | 1.2 |
| Menu frames shared | 0 | 0 |
| Prose craft (`--check`) | exit 0 both fills | met |

The last four are **quality guards, not success criteria**: they exist so the experiment
cannot buy diversity by degrading the book. A treatment arm that beats the recognition
margin while failing a guard is a failure.

## 7. Independence protocol (AL-181)

The mutation pilot's sibling-gram figure was invalidated because one author wrote both
arms. This spec fixes that:

1. One agent authors contract variants 2 and 3. It must see variant 1 in order to diverge
   from it deliberately; that is acceptable because contracts are the *intervention*, not
   the measurement.
2. **Two isolated fill agents**, one per treatment arm. Each sees only its own contract,
   binding, bible, and selection. Neither sees the other arm, the other contract, or any
   existing fill.
3. **The rater is a separate agent, blind to the design.** It is told only that the books
   share a skeleton lineage, and is given the same rubric and the same 2.0 / 2.5 anchors
   used in prior runs.

## 8. Model assignment, and one deliberate exception

Generative work runs on Sonnet: it is this project's measured shipping floor for prose
(blind craft 4.0, ship-with-light-edit) and the realistic production tier, so results
transfer.

**The rater does not run on Sonnet.** The 2.5 baseline was produced by a frontier rater,
and changing rater tier would confound the one comparison the experiment exists to make.
The rater therefore inherits the session tier. This is a deliberate exception to the
Sonnet directive, made to preserve comparability with the anchor.

## 9. Outcomes and what each means

- **Recognition lands past the hub, guards green.** Single-use is not inherent. Obligation
  variance is the lever, and the format question reopens: a skeleton becomes an N-use asset
  at the cost of N contracts. Next step is the economics, N contracts per graph versus N
  graphs.
- **Recognition improves but does not clear the margin** (say node 5-6, score 3.0). Partial
  lever. Worth combining with the Layer 1 items (relaxing CG-2, varying scene-function
  order) before judging.
- **Recognition unmoved at node 3-4.** Single-use is inherent to a shared armature. Stop
  looking for a format fix; the answer is volume (catalog depth) plus possibly
  cross-skeleton recombination, the one mechanism that cleared the anti-clone floor.
- **Any guard fails.** The arm is void regardless of its recognition score.

## 10. Known limitations, stated in advance

- n=1 skeleton, one rated pair per condition, one pass. The deterministic numbers replicate;
  the recognition number does not, by construction.
- The control pair's rating and the treatment pair's rating are separate rater instances.
  Inter-rater reliability on this rubric is unmeasured (`UW-C105`), so a difference of less
  than one full position on the landing node should not be treated as signal.
- Off-matrix skeleton, so catalog-level conclusions do not follow without replication.
- **Not a confound here, contrary to an earlier claim:** `templates/drafting_guide.md` is
  spliced into the *production* Stage A and Stage B prompts, but the pilot protocol has
  agents author from contract files directly, so the guide is not in this loop. It remains a
  confound for any experiment run through `generate_story` or `fill_skeleton`.

## 11. Cost

Four agent runs: one contract author, two isolated fills, one rater. Plus the deterministic
battery, which is already scripted. No production code changes.

---

## 12. Results (2026-08-10)

**The intervention failed decisively, and the failure identifies the actual fingerprint.**

### 12.1 Primary outcome

| Measure | Margin | Control (A/B) | Treatment (C/D) |
| --- | --- | --- | --- |
| Recognition landing | past position 5, or none | node 4 | **position 2** |
| Five-point distinctness | > 2.5 | 2.5 | **2.0** |

Recognition landed three positions earlier than the control and scored half a point lower.
The margin was missed in the wrong direction, so obligation variance is refuted as the lever.

Whether the treatment is genuinely *worse* than the control is not established: the two
ratings come from separate rater instances and inter-rater reliability on this rubric is
unmeasured (`UW-C105`). The defensible claim is that varying obligations did not move
recognition later, not that it moved it earlier.

### 12.2 Quality guards, all met

The arm is valid: it did not buy its result by degrading the books.

| Guard | Margin | Result |
| --- | --- | --- |
| Fill integrity (`--allow-title-rewrite`) | exit 0 both | met |
| Full validator gate | not blocked both | met |
| Prose craft (`--check`) | exit 0 both | met, 0 tense-unstable nodes, 0 moral tags, 0 told-emotion phrases |
| Sibling grams per 1000 | <= 4.0 | 2.7 |
| Menu frames shared | 0 | 0 |
| Em-dashes | 0 | 0 |

Sibling convergence had to be read at a matched protocol stage, because the 4.0 budget is
calibrated on post-revision output (`AL-165`): control pre-revision 9.0, treatment
pre-revision 6.4, control post-revision 0.3, treatment post-revision 2.7. The treatment pair
began *less* convergent than the control did.

### 12.3 Why it failed: obligations are downstream of topology

The contracts varied `choice_semantics` completely at both landing nodes:

- `n_start`, v2: "lead with patience / lead with self-reliance / lead with humility"
- `n_start`, v3: "follow the maker's own words / his handiwork / his confidant"

The blind rater nonetheless recorded the same fork in the same order at position 2, and the
same four-room fan at position 5. The reason is that a choice's *destination* is graph
structure, not contract content:

```
n_start  -> n_note, n_door, n_keeper
n_inside -> n_stairs, n_study, n_pendulum, n_basement
```

Whatever a contract says a choice *means*, choice 1 still leads to the note-decoding scene,
choice 2 to the find-another-way-in scene, choice 3 to the keeper scene. Both authors must
still write a stair, a study, a catwalk, and a basement. **A reader perceives where the
choices lead, not why the contract says they are offered.**

This unifies every prior null result rather than adding another. Devices change the nouns in
the rooms; prose changes the wording; model tier changes the quality; obligations change why
the rooms matter. None of them changes the rooms, because the rooms are edges. The only
intervention that ever moved recognition at all was mutation, which changes the graph, and
the only mechanism that ever cleared the anti-clone floor was cross-skeleton grafting, which
is recombination of two graphs.

### 12.4 Conclusion

Outcome three of section 9 obtains. **Single-use is inherent to a shared armature.** Stop
looking for a format fix inside one graph. Catalog diversity comes from more graphs: catalog
depth per cell (`UW-C110`, `UW-C113`), and possibly cross-skeleton recombination.

### 12.5 Two defects surfaced in passing, both independent of the outcome

1. **Unslotted choice labels are an unchecked recognition channel.** 13 of the skeleton's 35
   choice labels carry no slot token, so they are byte-identical across every binding
   (`Climb the spiral stair.`, `Spin the hands at random and hope.`, ...). NC-8 warns about
   unslotted *ending* titles and says nothing about choice labels, even though choice-menu
   semantics was already named as a residual leak (`AL-166`). Observed live: both isolated
   authors rewrote `Climb the spiral stair.` to `Head up the spiral stair.`
2. **Mechanic Divergence is category-scoped and blind to cross-category collisions.** MD
   scored these bibles 0.978 with no within-category kind overlap, while arm C's
   `cipher_hint_carriers/pattern_in_mechanism` ("long, long, short") and arm D's
   `cipher_forms/rhythm_code` ("read each pull as long or short") are the same device. The
   rater caught it unaided: "the two books' secret codes are the same code."

### 12.6 Limitations, as pre-registered

n=1 skeleton, one rated pair per condition, separate rater instances, and an off-matrix
skeleton (`AL-176`), so catalog-level conclusions require replication. One asymmetry arose
from agent discretion rather than design: arm D volunteered a sentence-splitting pass that
cut its reading-level warnings from 19 to 2 while arm C left its 20 standing, so the books
differ in sentence rhythm for reasons unrelated to the treatment.
