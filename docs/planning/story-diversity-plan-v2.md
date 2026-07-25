---
schema_type: planning
title: "Story Diversity Plan v2"
description: "Rebuilt diversity plan, grounded only in measurements that survived a seven-reviewer adversarial
  pass and a 98-document corpus survey. Fourteen near-term deliverables, six independent defects, eight items deferred
  behind named prerequisites, five resolved owner decisions and no open questions. Replaces two
  superseded plans."
tags:
  - planning
  - generation
  - diversity
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give the diversity work a plan that stands on verified evidence. The previous two plans were
  superseded because their measurements held but much of the reasoning built on them did not; this rebuild
  separates the two explicitly and records what is deliberately NOT claimed."
component: Strategy
source: "story-diversity-analysis.md (measurements, as corrected); story-diversity-review-errata.md (the
  refutations and the corpus survey); runtime-semantics.md; validator-rules.md; pathfinder-structure-exploration.md;
  admin-guardian-dual-roles-plan.md; authorization-matrix.md; series-stress-test-findings.md;
  r1-deferred-debt-register.md; docs/compliance/coppa-gdpr-remediation-plan.md; PR #413. 2026-07-25."
---

> **Replaces** [story-diversity-remediation-plan.md](story-diversity-remediation-plan.md) and
> [story-diversity-execution-plan.md](story-diversity-execution-plan.md), both superseded.
> [story-diversity-analysis.md](story-diversity-analysis.md) remains the measurement record;
> [story-diversity-review-errata.md](story-diversity-review-errata.md) records what was refuted and why.

---

## 1. Basis: what is established

Each of these was re-derived independently, from source, by a reviewer instructed to refute it. Nothing else in
this document is treated as established.

| Fact | How verified |
| --- | --- |
| 61 skeletons, 58 production-eligible | `is_sidecar` + `_production_candidates` |
| 24 `(band, length, style)` cells, 6 empty, and **15 of 18 non-empty cells hold exactly three trees** | `candidates_for_cell`; forced by 15x3 + 2x4 + 1x5 = 58 |
| **No `short` skeleton exists for `13-16` or `16+` in either style**, so those requests have zero candidates | cell enumeration |
| P(a reader's second story reuses the first's tree) in a 3-cell is **exactly 1/5**; general form 1/(2n-1) | closed form, plus 4M trials against the real `select_skeleton_for_cell` |
| `the-harrowstone-keep` and `the-sunken-temple` are **graph-isomorphic** (start- and ending-kind-preserving, 550 nodes, 796 edges), in one cell, both production-eligible | colour refinement + pruned `DiGraphMatcher`; WL hashes equal |
| `structure_fingerprint` cannot detect that pair (355 of 550 node ids differ) | direct comparison |
| The catalog declares **132 curated `metadata.themes`**; **zero** are values in `_THEME_TAG_MAP` (which is 67 keys to 12 values) | enumeration |
| The similarity comparison is **asymmetric**: the stored side is premise tags union raw curated themes, the request side is premise only, so symmetric Jaccard scores a byte-identical premise at **0.333** against `tau_theme` 0.35 and it does not register as similar | `history.py:190` vs `query.py:197`; reproduced |
| `DifferentiationLevel` never reaches `fill_skeleton`; it reaches a warning, a log line, and the flywheel trigger | call-graph trace |
| The ATG is advisory, fail-open, single-partner, with an empty per-band threshold table | `moderation/leaf_diversity.py`, `diversity/leaf.py` |
| Ending **count** and satisfying **path mass** are decoupled (Spearman weak, and negative under 3 of 4 reader models) | 4 reader models; walker validated in lockstep against `StoryEngine`, 0 divergences in 1,800 walks |
| Topology does **not** key satisfying path mass (4 of 6 classes hold zero gamebooks; the 2 populated classes do not separate, eta-squared 0.367, and the direction is reversed). The **fail-kind mix** does (eta-squared 0.636) | per-skeleton measurement |
| 1,778 gamebook endings; 178 sit below 33% of `min_complete`, splitting 104 `setback` / 73 `death`+`capture` / 1 `discovery`; scoped to foreclosing terminals, **no** skeleton breaches `min_endings` | BFS depth + `_effective_floors` |
| The **shared opening spine is 1 to 6 nodes** (median 3), and within-cell opening-content Jaccard is median 0.089, so two books in a cell were never confusable at the opening | dominator intersection; pairwise content Jaccard |
| **Go back ships, works at an ending node, and is disabled for continuation reads** | `engine.ts:325-347` (`back` has no ending guard, requires only `path.length > 1`); `engine.ts:288-297` fails closed when `path[0] !== start_node` |
| Of the 73 shallow foreclosing terminals, **only 15 are escapable by a single Go back**; the other 58 are reached from single-choice corridors, so backing up one step re-presents the same fatal choice | per-terminal predecessor analysis |
| **All 73 are within 3 Go-back hops** of a node offering a real alternative (15 need one hop, 58 need exactly three; max 3) | back-walk to nearest branching ancestor |
| Across 58 production-eligible skeletons there are **2,668 decision nodes** (non-ending, 2+ choices). **144** have every option terminating, but those sit at **median 90% of the tree's max depth** and **88 of them offer a positive ending**: they are climaxes. **37** are all-negative-valence. **1** has every option a `death`/`capture` terminal (`the-quiet-harbor-protocol`) | per-node target classification |
| Separately, **776 single-choice nodes** lead only to a `death`/`capture` terminal. These are not decisions; they are the corridor pattern A13 addresses | per-node scan |
| `save_slots` is client-writable, server-persisted, and **omitted from `validate_reading_state`** | `schemas.py:80`, `reading.py:412`, `reading.py:168-175` |
| **129 of 132 catalog themes pass the echo floor at band `3-5`** | ran the real `_echo_floor` at all six bands |
| Reading telemetry does not exist: `ReadingState` is one mutable row with `path` overwritten; `Completion`'s key includes `ending_id` with one `found_at`, so re-reads and depth-at-terminal are unrecorded | `db/models.py:725-793` |
| Difficulty, win-arc count, and reading telemetry are unspecified corpus-wide | 98-document survey |

## 2. What this plan does NOT claim

Recorded so these are not re-derived. Full reasoning in the errata.

- **No funnel argument.** The shared spine is 1 to 6 nodes and same-cell openings are already distinct, so
  "a reader who exits early has read only the shared opening" is false. Any depth floor must be justified as a
  **difficulty** decision, not a diversity one.
- **No fraction is recommended for a depth floor.** The 33% figure came from a circular proxy.
- **No per-topology outcome floor.** Not calibratable.
- **No claim that a satisfying-path-mass figure near zero is a defect.** Under a competent reader it is
  1.3% to 34.9% (median ~9%), and two or three plies of foresight move 13 of 14 skeletons to 41-100%.
- **No claim that `save_slots` lacks a producer**, that `LEGAL_TRANSITIONS` has no exit from `published`, or that
  the COPPA remediation plan is missing. All three were false.
- **No new snapshot-based restart mechanism.** `runtime-semantics.md` section 6 defers backtracking by normative
  rule, and its rationale rejects snapshots for exactly this. Path replay already ships.
- **No `min_positive_endings` floor**, and no assertion that any coverage target is achievable before it is
  measured.

## 3. Track A: near-term, grounded

Each item traces to a fact in section 1. Effort: S under a day, M a few days, L a sprint or more.

| ID | Deliverable | Effort |
| --- | --- | --- |
| **A1** | **Two vocabularies, not one grown map.** Freeze `_THEME_TAG_MAP` as the echo vocabulary and add a separate similarity vocabulary; normalise the stored side's raw `metadata.themes` into the similarity vocabulary rather than passing them through verbatim. The previous plan proposed growing the shared map, which would have changed what a child sees, because the echo signature *is* that map. | M |
| **A2** | **A containment measure for request-versus-story**, in a new function. The request is a short statement of intent and the story carries a fuller set, so symmetric Jaccard structurally penalises a match. Leave `jaccard_similarity` and its documented empty-set semantics untouched: `normalize.py:470-482` records that an empty signature "must never register as similar to anything" as a deliberate WS-0 decision. Handle unknown inside the new function. | S |
| **A3** | **A saturation ceiling guard.** A2 pushes toward "similar"; with 3-tree cells, `cell_theme_saturation` pins at 1.0 after three reads, the ladder sits permanently at `LEAF`/`CATALOG`, and `_blended_weight` becomes rank-equivalent to recency alone. That is the mirror image of the defect this plan exists to fix. Add an upper bound to the escalation-trigger-rate metric and a regression test that pins saturation behaviour. | S |
| **A4** | **A committed premise panel, and publish the measured coverage.** Realistic requests (pets, sports, family, school, music, invention, weather, food, siblings) paired with catalog themes. State the number; assert no target in advance. | S |
| **A5** | **Re-derive `tau_theme`** on the A4 panel, since A1 and A2 change both the vocabulary size and the measure. Record the value with its basis. | S |
| **A6** | **Thread `DifferentiationLevel` and prior-fill context into `fill_skeleton` and `fill.md`.** Pass the prior fills' **published titles and settings** (content the family already has), never prior premises, so one child's request text cannot enter a sibling's generation prompt. Fence at reuse. | M |
| **A7** | **A variation-axis library**: authored axes (narrative distance, tonal register, sensory emphasis, pacing, whose viewpoint the scene favours), one drawn per request. Varies the dimension rather than the sampling noise, so it does not trade against reading-level stability. | S |
| **A8** | **In-cell clone audit in CI**, using `structural_distance` (not `structure_fingerprint`, which cannot see a renamed clone) against the **loaded** `TAU_CELL` from `ws5_floor_baseline.json`, not a hardcoded 0.05. `floors.py:62-64` documents `TAU_CELL` as the anti-duplication floor, so it is the right threshold. | S |
| **A9** | **Resolve the in-cell duplicate**, pending the decision in section 6.1: `the-harrowstone-keep` and `the-sunken-temple` are brass-lantern books 1 and 2, a deliberate series stress-test artifact, so "retire one" is not available. | M |
| **A10** | **Make the empty teen `short` cells fail gracefully or fill them.** A `13-16/short` or `16+/short` request has zero candidates today and 422s. Pending the decision in section 6.2. | M |
| **A11** | **State the request restrictions before submission.** `RequestStory.tsx` shows one prompt and no restrictions. `_ELEMENT_MUST_BE_NULL` spans `SAFETY_POLICY`, `PERSONAL_DETAILS` and `IDENTITY_PROTECTION`, so for the three most surprising restrictions the WS-7 echo can name the reason but structurally cannot show what was dropped. Serve the restriction set from the API off `ReasonCode` / `band_profile` / the profile's `content_nogo`, never hand-written copy. Kid surface omits the `content_nogo` values entirely and its copy stays invariant to their contents. Note `capability-register.md:133` marks K19 delivered; update it. | M |
| **A12** | **Enable Go back in continuation reads.** `replayRecordedPath` fails closed when `path[0] !== start_node`, disabling Go back in exactly the state-carrying series books where a reader has most to lose. A bug fix, not a feature. | M |
| **A13** | **Make Go back walk to the nearest node with an untaken choice**, up to a small bound. Today it is single-step, and only **15 of 73** shallow foreclosing terminals are reached from a node offering an alternative; the other 58 sit at the end of single-choice corridors, so one hop re-presents the same fatal choice. **All 73 are within 3 hops.** This replaces a fail-depth floor plus 73 ending relocations with one player change and zero skeleton edits. **Bound: 3 hops** (owner, 2026-07-25), to be re-evaluated as stories are developed. Interacts with `runtime-semantics.md` section 6, so it needs B2's revision first. | M |
| **A14** | **`L2-14`: no decision may offer only fatal options.** Owner rule (2026-07-25): a reader must never be shown option A and option B where both end in death. Stated over **visible** choices in every reachable configuration, not declared choices, because a condition-gated survivable option is invisible to a reader who lacks the state and the decision then presents as all-fatal. That places it in the **Layer 2** stateful walk beside `L2-9`/`L2-11`, not the static policy layer: `validate_policy(story)` sees only declared structure. **`L2-14`** is the next free L2 id (`L2-13` is the current maximum); an earlier draft called this `PL-23`, which was the wrong layer. Scope: no decision node may have **all** visible choices leading to negative-valence terminals, which is **37** of 2,668 nodes at declared scope today and adds no further violations from gating (verified). Register in `validator-rules.md` in the same PR. Pairs with A13, which covers the 776 single-choice corridors that end fatally and are not decisions. | M |

## 4. Track B: defects found by the review, independent of this plan

Each stands on its own and does not wait on Track A.

| ID | Defect | Effort |
| --- | --- | --- |
| **B1** | `save_slots` is the only reading-state field omitted from `validate_reading_state` (`reading.py:168-175`), defeating the `#CRITICAL` anti-forgery intent two lines above. Inert while nothing restores from a slot; a forged slot becomes a state-restoration input the moment anything does. Validate it or remove it from the PUT body. | M |
| **B2** | `runtime-semantics.md` section 6 states there is no back button in v1 and that any implementation "requires a revision to this document and an ADR". `Reader.tsx:210` ships one. File the revision and the ADR. | S |
| **B3** | **SR-8** (the ID is free; `SR-7` is the current maximum): for `carries_state=true`, every satisfying-ending state of book N must be an admissible entry state for book N+1. L2 only ever walks from `start_node` with declared initials, so continuation entry state is outside every existing rule's view. | M |
| **B4** | `machine.ts:108` resets to the start node with declared initials, so "Read again" in a continuation read fabricates `has_lantern=true` and `vigor=5` the reader never earned and discards carried state. | S |
| **B5** | Escalate `series-stress-test-findings.md` **F3** from authoring guidance to a gate-detectable defect: book 2 with `has_lantern=false` returns `blocked=True` with two `L2-11` errors, and all four of book 1's win endings are reachable with it false. `vigor` is monotone in these books (68 `dec`, zero `inc`), so no restart can restore state never earned. | S |
| **B6** | **Closed as working-as-intended** (section 6): sharing a child's first name with a connected family is sanctioned by mutual guardian consent. Residual: add a sentence to ADR-016 recording ring-2 attribution granularity, which it does not currently specify. | S |

## 5. Deferred, each behind a named prerequisite

Not "later" in the abstract. Each has one thing that must happen first.

| Item | Prerequisite |
| --- | --- |
| Reading telemetry (depth reached, early-exit rate, real satisfying rate) | A schema design for durable per-session reading data plus a child-behaviour privacy review. `r1-deferred-debt-register.md` U5 already registers this as Phase 4b with an owner; extend that, do not duplicate it. |
| A fail-depth floor (`PL-23` is free; `PL-22` is taken) | **Probably not needed at all** if A13 lands: a multi-step Go back fixes all 73 shallow foreclosing terminals with no skeleton edits, where a floor needs 73 relocations and a fraction with no non-circular basis. Revisit only if A13 is rejected or telemetry shows a residual problem. |
| An outcome-mix floor keyed on the fail-kind mix | Telemetry. Do not key it on topology. |
| Challenge mode / permadeath | B2's ADR, since it is a backtracking-semantics change; plus a per-(profile, series) row, which does not exist. |
| Alternate beat phrasings | Its own design doc and ADR. The evidence for it is weaker than stated (the illustrating quotation was wrong), though the byte-frozen-beat constraint is real. Also bounded by the `L2-12` 100,000-configuration cap, which permanently caps declared variables near five. |
| Per-reader (`profile_id`) scoping, and ATG against the k nearest same-tree fills with calibrated thresholds | A1 through A5, since both consume the similarity signal. |
| A guardian visibility ceiling | A first-class ceiling column on `Storybook` (no `Storybook` to `StoryRequest` join exists; `GenerationJob.storybook_id` is deliberately not a foreign key), plus an explicit amendment to the `#CRITICAL` invariant at `publishing/service.py:309-317` that visibility "must never be settable outside an admin-gated approve". If built, enforce on an explicitly passed acting capacity per `admin-guardian-dual-roles-plan.md`, not on `acting_role`, which returns `GUARDIAN` for a same-family admin approve. |
| Growing the small cells past three trees | WS-8's flywheel owns the automated path; A8 must gate every addition. |

## 6. Decisions required

**Resolved (owner, 2026-07-25): catalog disposition.** No book or skeleton is required to be kept. Retire and
replace, or fix; substandard work is not carried. This is a standing principle, not a one-off ruling on
brass-lantern, and it has three consequences:

- **A9** takes the fix-or-replace path. A same-series exemption from the in-cell clone rule is **off the table**:
  two books of one series sharing an isomorphic tree is substandard regardless of the narrative continuity that
  explains it.
- **A8 gains teeth.** The audit may require replacement rather than negotiate an exemption, which makes a
  stricter threshold viable: `TAU_CELL` (0.05) is the anti-duplication floor, while `TAU_STRUCT` (0.33 in the
  committed baseline) is described in `floors.py` as the bar for "a genuinely new tree". Under this principle,
  auditing hand-authored trees at `TAU_STRUCT` is defensible; note `13-16/medium/gamebook` sits at 0.091 and
  would fail it. Recommend starting at `TAU_CELL` to fix the known duplicate, then evaluating the `TAU_STRUCT`
  bar as a separate decision with the failing set measured first.
- **A10** leans to authoring the missing teen `short` skeletons rather than degrading the surface, since a cell
  that 422s is itself substandard. Still needs a call on sequencing, because this is content authoring with
  nothing to fix.

**Resolved (owner, 2026-07-25): difficulty.** Adopt A13 with a **3-hop** bound, re-evaluated as stories are
developed, rather than a fail-depth floor. And a new rule: **no decision may offer only fatal options; at least
one must allow advancing or looping back.** That becomes A14 (`L2-14`, see section 6.1 for why Layer 2).

**Resolved (owner, 2026-07-25): ring-2 attribution.** Sharing the child's first name with a connected family is
fine, because both guardians have agreed. Keep `display_name` as the attribution; B6 closes as
working-as-intended. The basis is recorded here so it is not re-raised: mutual connection consent is the
control, `coppa-compliance-audit.md:129` establishes that `display_name` is a first name or nickname and the
only stored child name, and the disclosure is inventoried in `gdpr-compliance-review.md:160`. ADR-016 should
gain a sentence stating ring-2 attribution granularity, since it currently defines the rings but not this.

**Resolved (owner, 2026-07-25): A14's scope.** The intent is that a reader is never shown option A and option B
where both result in death. Confirmed at the negative-valence reading below, which is a superset of that concern.

### 6.1 How A14's scope was chosen, and why it is a Layer 2 rule

The rule reads naturally as three different tests, and the measurement separates them:

| Reading of "only fatal options" | Violations of 2,668 decisions | Assessment |
| --- | --- | --- |
| Every option is a `death`/`capture` terminal | **1** | The clear floor. Too narrow to be the whole rule. |
| Every option is a **negative-valence** terminal (doomed whatever you pick) | **37** | **Recommended.** Matches the intent: the reader is offered a decision with no good outcome. |
| Every option terminates at all | 144 | **Not implementable as stated.** These sit at median 90% of max tree depth and 88 of them offer a positive ending: they are climaxes. Forbidding them would make it impossible to end a story on a choice. |

The middle reading is adopted. The literal phrase "advancing or loop back" points at the third, which the
climax measurement rules out: a story must be able to end on a choice.

**Two findings from checking the gated case**, which the declared-choice count would have missed:

- **No skeleton has "unconditional options all fatal with the survivable one gated."** Of 107 decision nodes
  carrying a conditional choice, none degrades that way, so A14 adds no violations beyond the 37.
- **18 decision nodes have every choice conditional** (in `the-cinder-bazaar`, `the-quiet-harbor-protocol`,
  `the-iron-spire-trial`, `the-glass-comet`, and the brass-lantern pair). That shape is already covered:
  **`L2-9`** blocks "any reachable non-ending configuration with zero visible choices", so a reader can never
  face an empty decision, and these skeletons pass the gate today.

Together those two are why A14 belongs in Layer 2 and must be written over visible choices. Nothing violates it
through gating today, and stating it that way costs nothing while closing the loophole permanently. `L2-9` and
`L2-11` already walk the same configuration space, so the `L2-12` cap is not a new constraint.

## 7. Method rules for this document

Carried from the errata, because the previous plans failed on all six.

1. Measurement and inference are separated. Section 1 is measurement; section 2 states what is not claimed.
2. Any invented proxy is declared as invented, with its free parameters and a sensitivity sweep, or it decides
   nothing.
3. One metric, one definition per table.
4. A later section may not quietly erase an earlier section's evidence. If it does, the earlier section is
   edited, not left standing.
5. Rule IDs, ADR numbers, and "this is unaddressed" claims are checked against `validator-rules.md` and the
   98-document corpus before being written.
6. Source text is quoted verbatim with its file path, or not quoted.
