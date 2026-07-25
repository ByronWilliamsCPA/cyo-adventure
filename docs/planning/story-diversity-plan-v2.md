---
schema_type: planning
title: "Story Diversity Plan v2"
description: "Rebuilt diversity plan, grounded only in measurements that survived a seven-reviewer adversarial
  pass and a 98-document corpus survey. Eighteen near-term deliverables, six independent defects, eight items deferred
  behind named prerequisites, five resolved owner decisions, and a child-reader review folded in. Replaces two
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
| **A11** | **Set expectations on the request page, affirmatively, and drop two of the three restrictions.** `RequestStory.tsx` is one prompt and a 500-character box today. Per the child-reader review (section 6.1): **drop** the fixed-structure statement from the kid surface (no child under about eleven has that model; keep it on guardian intake) and **drop** "some themes are off for this family" (unnameable on the kid surface, so it is a pre-emptive accusation with nothing to act on; the existing blocked-status copy handles the real event kindly). **Reshape** the naming rule from a prohibition into a mechanism: a "Who's the hero?" field pre-filled with a made-up name and a shuffle control, which sets the expectation without ever saying "you cannot be the hero" -- the project already has the right sentence in `interpretation.py` ("Heroes in our stories always have made-up names, so we chose one for you!"). One affirmative line covers PII: "Everyone in the story gets a made-up name, even your friends." **Add** the expectation the review found matters most to a child and that was on nobody's list: "A grown-up reads your idea first. Then it takes a little while to write your book." Net effect is zero new blocks of rules text. Serve the guardian-facing set from the API off `ReasonCode` / `band_profile` / `content_nogo`; the kid-surface response still omits `content_nogo` values entirely. Update `capability-register.md:133`, which marks K19 delivered. | M |
| **A12** | **Enable Go back in continuation reads.** `replayRecordedPath` fails closed when `path[0] !== start_node`, disabling Go back in exactly the state-carrying series books where a reader has most to lose. A bug fix, not a feature. | M |
| **A13a** | **Leave the in-story Go back exactly as it is: one step, always available.** `Reader.tsx:210` states its purpose, "Kids mis-tap constantly; Go back undoes just the last choice." A multi-hop rewind bound to that button would move a mis-tapping 4-year-old three passages upstream and erase prose they were enjoying. At 3-5 and 5-8 that is pure loss, since `_PROFILES` forbids `death` and `capture` at both bands so there is no fatal corridor to rescue, and a 3-5 story is 10-45 nodes, making 3 hops up to a third of the book. **No change to `back()` or `canGoBack()`.** | none |
| **A13b** | **Add a second, separately labelled affordance at the ending screen only: "Try a different way."** Walks up to **3 hops** to the last node where the reader had a real pick, and **falls back to one step when there is none**. Availability stays exactly today's `path.length > 1` and replayable: it must never become "an untaken choice exists within 3 hops", because that hides the button at precisely the 88 preserved climaxes (take option A, die, go back, take option B, win: on that second ending there is no untaken fork nearby and a button the child just learned would vanish). "Untaken" is defined against the current read only, and the walk stops at the **first branching ancestor** regardless of whether its other options were used, so the destination is always "the last place you got to pick" rather than a distance that varies per press. Captures the full measured benefit (the 58 corridor terminals) without repurposing a learned affordance. | M |
| **A14** | **`L2-14`: no decision may offer only fatal options, band-scoped, and stated so it cannot be dodged.** Owner rule: a reader must never be shown option A and option B where both end in death. Two corrections from the child-reader review (section 6.2). **(a) Band-scope it.** `Valence.NEGATIVE` includes `setback`, so a single negative-valence rule would forbid a 15-year-old from ever facing a lose-lose dilemma, which is exactly what a `gauntlet` reader seeks and what ADR-011 sanctions from 13-16 up. Enforce the negative-valence reading at **8-11 and 10-13**, and the `death`/`capture` reading at **13-16 and 16+**. **(b) State it over the reader-visible decision unit, not the node**, or an author can comply by splitting an all-fatal decision into two single-choice corridors that each end fatally: the rule passes and the child now gets a page with one button that kills them. So: no reachable branching node may have every downstream path reach a forbidden terminal without an intervening visible choice. That also folds in the 776 single-choice fatal corridors, which are the larger agency problem and which the node-scoped rule missed entirely. Layer 2 (`L2-14`) because it is about visible choices in reachable configurations. | M |
| **A15** | **Retire-for-quality must not delete a child's progress.** `archive` is the only exit from `published`, `library.py` filters on published status, `reconcileOfflineCache` purges the local copy, and `reading_history.py::_history_item` degrades a version-less book to a storybook **id** as its title with `total_endings = 0`. So a retired book takes the shelf card, the in-progress read, the offline copy and the "6 of 7 endings found" badge with it, silently. Distinguish **unsafe** (archive now, the urgency justifies it) from **substandard** (no new readers: stop assigning, keep it readable for any profile with progress or completions, let it age out). Interim before the deferred visibility work exists: unassign only from profiles with no activity. Fix `_history_item`'s degraded row to show a friendly retired label, not a UUID. | M |
| **A16** | **Never retire a non-final series book before its replacement ships in the same release.** `Reader.tsx:313-320` offers "Continue the series" on a satisfying ending of a non-final book; if book 2 changes or goes, that promise goes quiet with no in-product account, after a teen spent hours in a 550-node book and earned carried state. The replacement must accept book 1's carried state, which is exactly what B3 gates. If it cannot, re-cut book 1 to `is_final` so the continuation is never promised. Binds A9. | S |
| **A17** | **A retired book leaves a tombstone, not a hole**: title, endings the child found, and one line ("This one has gone back to the workshop. Your 6 endings are still yours."). Children infer causes, and a card that vanishes next to a `StarRating` they cannot clear invites "did I lose it because I rated it 2 stars?". | S |
| **A18** | **Differentiate the two back-chevrons.** `Reader.tsx` renders Go back as a ghost button with a chevron visually identical to the top-bar "Leave" chevron, one of which exits the book. A13b makes the lower one more consequential. Give the story-level control a circular-arrow glyph, and make the ending-screen affordance primary weight rather than ghost, since there it is a headline action. | S |

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
one must allow advancing or looping back.** That becomes A14 (`L2-14`, see section 6.2 for why Layer 2).

**Resolved (owner, 2026-07-25): ring-2 attribution.** Sharing the child's first name with a connected family is
fine, because both guardians have agreed. Keep `display_name` as the attribution; B6 closes as
working-as-intended. The basis is recorded here so it is not re-raised: mutual connection consent is the
control, `coppa-compliance-audit.md:129` establishes that `display_name` is a first name or nickname and the
only stored child name, and the disclosure is inventoried in `gdpr-compliance-review.md:160`. ADR-016 should
gain a sentence stating ring-2 attribution granularity, since it currently defines the rings but not this.

**Resolved (owner, 2026-07-25): A14's scope.** The intent is that a reader is never shown option A and option B
where both result in death. Confirmed at the negative-valence reading below, which is a superset of that concern.

### 6.1 Child-reader review (2026-07-25)

A subagent evaluated A11, A13, A14 and the disposition principle purely from the reader's side, grounded in the
shipped reader UI and the ADR-011 band tables. It found the rules mostly right and the **wording** mostly not the
child's. Eight findings argued a rule was wrong; seven argued it needed different presentation. The substantive
ones are folded into A11, A13a/A13b, A14, and A15 through A18 above. Three worth keeping visible:

- **Band spread.** A13 and A14 both key on `death`/`capture`, which `_PROFILES` forbids at 3-5 and 5-8 and
  partially at 8-11. So the two youngest bands get **zero benefit** from either while carrying A13's downside if
  the multi-hop had been bound to the in-story button. A11 is where those bands live or die.
- **A coupling to watch.** A13 and A14 both make the world safer, and landing both unscoped at 13-16/16+ is the
  fastest route to a teen concluding the book cannot hurt them. Band-scoping A14 (above) is what prevents that.
- **The actionability test for any kid-facing restriction**: if a child cannot act on it, it is anxiety, not
  information. That is why the unnameable forbidden-theme warning is dropped rather than reworded.

### 6.2 How A14's scope was chosen, and why it is a Layer 2 rule

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
