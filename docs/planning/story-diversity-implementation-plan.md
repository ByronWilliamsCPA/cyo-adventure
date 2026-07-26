---
schema_type: planning
title: "Story Diversity Implementation Plan"
description: "Sequenced implementation plan for the story-diversity work specified in story-diversity-plan-v2.md.
  Seven slices ordered by dependency and by what is cheapest now, with per-slice verification, rule-ID
  reservations that keep the work independent of open PR #416, and the three handoff points into the remaining
  personalization phases (P3 to P9)."
tags:
  - planning
  - generation
  - diversity
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Turn plan v2's twenty deliverables and six defects into an executable sequence, so the diversity work
  completes before the remaining personalization phases begin and without waiting on PR #416."
component: Strategy
source: "story-diversity-plan-v2.md (the specification); story-diversity-review-errata.md; ws5_floor_baseline.json;
  ADR-020 floor-recalibration amendment; adr-023-story-personalization-slots.md;
  story-personalization-implementation-plan.md; PR #416 (open, deferred by owner decision). 2026-07-26."
---

> **Specification**: [story-diversity-plan-v2.md](story-diversity-plan-v2.md). That document says *what* and
> *why*; this one says *in what order* and *how it is verified*. Where the two disagree, plan v2 governs the
> intent and this plan is corrected.

---

## 0. Sequencing decision, and what it settles

**Owner decision (2026-07-26): complete this work before the remaining phases of PR #417/#418
(personalization P3 to P9). PR #416 waits.** Three consequences follow, and each removes an
open question this plan would otherwise have to carry.

**PR #416 is not a dependency.** It stays open and unmerged, so `main` remains at `SR-7`, `PL-22`, `L2-13`. This
plan therefore reserves the IDs #416 has already implemented and tested rather than claiming them (section 4), so
neither workstream has to renumber when #416 eventually lands. One consequence to accept deliberately: `main`
will carry `SR-9` with a gap at `SR-8` until #416 merges. That is recorded in `validator-rules.md` as a
reservation, which is cheaper than the alternative of forcing a green, tested PR to renumber.

**A8 no longer waits on #416's recalibrated baseline.** That was listed as a dependency because #416's follow-up
push was to re-derive the mutation floors. It is not needed: the threshold decision is closed on measurement
against the **committed** catalog (section 1), and ADR-020's amendment already fixed `TAU_CELL` at 0.05.

**Landing A8 first means it gates #416's story push, which is the correct order.** #416's AL-014/AL-044 report two
withheld books at `structural_distance` 0.0139 against the 0.05 floor. Those books are not in `skeletons/` yet, so
they are absent from this plan's 100-pair measurement; both facts are true over different corpora. When #416's
story artifacts arrive they will fail A8, which is exactly what the gate is for. Building A8 now is what makes
that catch happen rather than discovering it after import.

### Handoff into personalization P3 to P9

Three items here are preconditions for that work, not merely adjacent to it. Stating them so the boundary is
explicit:

| This plan's item | Blocks | Why |
| --- | --- | --- |
| **A19** (ATG strips sentinels) | Any `.contract.json` declaring a `personalizable` slot | The moment a fill carries a sentinel, the ATG's masked leaf distance is deflated and biases toward false FAIL. Dormant only while zero contracts opt in |
| **A20** (backfill 16 contracts) | P6 / P9 becoming user-visible | A skeleton with no contract has no slots, so personalization cannot reach it. Shipping the toggle before A20 gives teen readers a feature inert on 43% of their catalog |
| **A11** (request-page copy, ADR-023 section 4) | P9 (the child-facing control) | ADR-023 makes the rewording a precondition on G18's flag, because the current Route A sentence becomes false under opt-in |

Nothing else in P3 to P9 depends on this plan, and this plan takes no dependency on them.

---

## 1. Corrections this plan applies to plan v2

Measured while sequencing. Each is applied in plan v2 as well; recorded here because each changed the plan.

| Finding | Effect |
| --- | --- |
| **A14's fix list is 1 node, not 37.** All 37 all-negative-valence decisions sit at **13-16 (4) and 16+ (33)**, zero at 8-11 or 10-13. A14 applies the negative-valence reading only at 8-11/10-13, so there it is preventive with nothing to fix; the `death`/`capture` reading at 13-16/16+ catches exactly **1** (`the-quiet-harbor-protocol`) | A14 drops M to S, lands blocking on day one, and the "fix 37 nodes" work item disappears |
| **A8 at `TAU_CELL` = 0.05 fails exactly 1 of 100 in-cell pairs** (the known clone at 0.00095; next-lowest 0.09123, median 0.3859) | A8 lands blocking immediately, no advisory-then-flip phase, no calibration risk |
| **A `TAU_STRUCT` gate is rejected**: it would fail 27 of 100 pairs across 19 of 28 cells, and ADR-020's amendment already made `TAU_STRUCT` documentation-only | Closes the open threshold decision in plan v2 section 6 |
| **B2 is a blocker, not a parallel docs chore.** `runtime-semantics.md` section 6 forbids a back button and requires "a revision to this document and an ADR" for any Phase-1 implementation. A12 enables that button in more states and A13b extends it to multi-hop | B2 moves ahead of A12, A13b and A18 instead of alongside them |

---

## 2. Slice order

Seven slices. The rule is: unblock cheaply first, then land gates while the violating set is one node and one
pair, then fix code correctness, then author content, then touch the reader UI last because it is the only part
needing evidence this plan cannot generate on its own.

| Slice | Contents | Gate to start | Effort |
| --- | --- | --- | --- |
| **S0** Unblock | B2, A16, B6, plan v2 corrections, PR #415 body | none | ~1 day |
| **S1** Gates while free | A19, A8, A14, B3, B5, B1 | S0 (B2 not required) | ~3-4 days |
| **S2** Similarity signal | A1, A2, A3, A4, A5 | none (parallel to S1) | ~3 days |
| **S3** Generation variety | A6, A7 | S2 (A6 consumes the signal) | ~2-3 days |
| **S4** Catalog | A9, A20 | S1 (A8 defines the failure; A16 written) | ~4-5 days |
| **S5** Reader UX | naive-ux session, A11, A12, A13b, A18, B4 | S0 (B2's ADR) + UX session | ~4 days |
| **S6** Close out | validator-rules.md, capability-register, lessons log | S1-S5 | ~1 day |

S1 and S2 are independent and can run in parallel; everything else is ordered.

---

## 3. Slice detail

### S0: unblock (docs and decisions only, no source)

1. **B2**: file the `runtime-semantics.md` section 6 revision plus a backtracking ADR. The ADR must cover what
   ships today (single-step replay-based Go back, `Reader.tsx:210`) **and** what A13b adds (bounded multi-hop to
   the nearest branching ancestor), so A13b does not require a second amendment. Record why path replay rather
   than snapshots, which section 6's own rationale already argues and four corpus sources independently support.
2. **A16**: write the rule that a non-final series book is never retired before its replacement ships in the same
   release, with the fallback of re-cutting book 1 to `is_final`. Costs nothing now and binds A9 in S4.
3. **B6**: the single ADR-016 amendment, covering ring-2 **attribution** granularity (this plan) and ring-2
   **personalization** granularity (ADR-023 section 3) in one edit. ADR-016 already carries the proposed addendum
   naming both; this replaces it with the real sentence. Do not write one half.
4. Apply the section 1 corrections to plan v2 (done) and update **PR #415's body**, which still advertises
   "eighteen deliverables", `SR-8`, and "`PL-23` is free". That body is the handoff artifact for the other
   workstreams, so a stale rule ID there actively misdirects them into the collision.

*Verification*: `markdownlint`, the no-em-dash hook, and a link check on the new ADR. No tests.

### S1: gates while enforcement is free

Order within the slice matters only for A19, which should land first so no personalizable slot can be declared
ahead of it.

1. **A19** (S): call `strip_sentinels` at the ATG's tokenising boundary in `diversity/leaf.py`. Regression test:
   a sentinel-bearing fill and its stripped equivalent produce identical `content_tokens`, masked token sets, and
   leaf distance. `diversity/leaf.py` is untouched by both #416 and #418, so this is conflict-free.
2. **A8** (S): in-cell clone audit in CI, using `structural_distance` against the **loaded** `TAU_CELL` from
   `ws5_floor_baseline.json`, never a literal. Hook into the existing `diversity` job in `ci.yml:512`, which
   already runs pure-Python diversity checks over committed fixtures. Land **blocking**; the one expected failure
   is the clone pair, which S4 fixes. Until then, quarantine that single pair with a strict xfail-equivalent
   allowlist that names it and fails if the list is not shrinking, following #416's pattern.
3. **A14** (S): `L2-14` in `validator/layer2.py`. Stated over the **reader-visible decision unit**: no reachable
   branching node may have every downstream path reach a forbidden terminal without an intervening visible choice.
   Band-scoped: negative-valence at 8-11 and 10-13, `death`/`capture` at 13-16 and 16+. This also closes the 776
   single-choice fatal corridors, which the node-scoped reading missed. One fix
   (`the-quiet-harbor-protocol`). `L2-9` already blocks zero-visible-choice configurations, so the gated case is
   covered and the `L2-12` 100,000-configuration cap is not newly constrained.
4. **B3** (M): `SR-9` in `validator/series.py`. For `carries_state=true`, every satisfying-ending state of book N
   must be an admissible entry state for book N+1. Note `series.py:210-213` checks ending **existence**, not
   reachability, so this is genuinely uncovered. Before building, confirm against #416's `SR-8` (carried-variable
   *declaration* integrity, a static comparison) that the two do not collapse into one rule; if #416's AL-038
   read-time carry audit is taken up there, B3 folds in and closes as duplicate.
5. **B5** (S): escalate `series-stress-test-findings.md` F3 from guidance to a gate-detectable defect. `SR-9`
   should be what detects it, so build after B3.
6. **B1** (M): validate `save_slots` in `validate_reading_state` (`reading.py:168-175`) or remove it from the PUT
   body. It is the only reading-state field omitted, which defeats the `#CRITICAL` anti-forgery intent two lines
   above. Inert today; a forged slot becomes a state-restoration input the moment anything restores from one.

*Verification*: `uv run pytest`, `ruff check`, `basedpyright src/`, plus a full-catalog gate run showing exactly
the expected failure set (1 for A14, 1 pair for A8, 0 new for A19).

### S2: similarity signal correctness (parallel to S1)

Pure code correctness, independent of catalog scale. Order is fixed: A1 and A2 change the vocabulary and the
measure, so A5 must re-derive `tau_theme` after both.

1. **A1** (M): two vocabularies. Freeze `_THEME_TAG_MAP` as the **echo** vocabulary, since that map *is* what a
   child sees; add a separate **similarity** vocabulary and normalise the stored side's raw `metadata.themes` into
   it instead of passing them through verbatim (`normalize.py:544`).
2. **A2** (S): a containment measure for request-versus-story, in a **new** function. Leave `jaccard_similarity`
   and its documented empty-set semantics alone (`normalize.py:470-482` records "must never register as similar to
   anything" as a deliberate WS-0 decision). This is what fixes the 0.333-versus-0.35 asymmetry.
3. **A3** (S): saturation ceiling guard. A2 pushes toward "similar", and with 3-tree cells
   `cell_theme_saturation` pins at 1.0 after three reads, which would make `_blended_weight` rank-equivalent to
   recency alone. Add an upper bound on the escalation-trigger-rate metric plus a regression test pinning
   saturation behaviour.
4. **A4** (S): a committed premise panel (pets, sports, family, school, music, invention, weather, food,
   siblings) paired with catalog themes. Publish measured coverage; assert no target in advance.
5. **A5** (S): re-derive `tau_theme` on the A4 panel and record the value with its basis.

*Verification*: the existing `diversity` CI job plus new unit tests. A3's regression test is the one that must
fail before its fix.

### S3: generation variety

1. **A6** (M): thread `DifferentiationLevel` and prior-fill context into `fill_skeleton` and `fill.md`. Pass prior
   fills' **published titles and settings** only, never prior premises, so one child's request text cannot enter a
   sibling's generation prompt. Fence at reuse.
2. **A7** (S): a variation-axis library (narrative distance, tonal register, sensory emphasis, pacing, whose
   viewpoint the scene favours), one axis drawn per request. Varies the dimension rather than sampling noise, so
   it does not trade against reading-level stability.

*Verification*: `RL-13` must not regress, since A7 changes prose character. Run the reading-level suite over
regenerated fills before and after.

### S4: catalog

1. **A9** (M): resolve the clone pair under the disposition principle, fix-or-replace, no series exemption. Bound
   by A16: these are brass-lantern books 1 and 2, so "retire one" is unavailable; the replacement must accept book
   1's carried state, which `SR-9` now gates. Shrink A8's allowlist to empty in the same change.
2. **A20** (M): backfill the 16 missing theme contracts, ordered `13-16` (6), `16+` (5), `10-13` (4), `3-5` (1).
   Write the clone pair's contracts **after** A9 settles, or the work is done twice. Declaring any slot
   `personalizable` requires A19 first, and is P3-to-P9 work rather than this plan's.

*Verification*: `check_skeleton` on every touched skeleton, the promotion gate, and A8 green with an empty
allowlist. Note #416's AL-014 warns that no hand-authored skeleton currently passes the promotion gate because
`check_promotion_bundle.py` requires a lineage sidecar unconditionally; if A20's contracts trip that, the fix
belongs to #416 and A20 should not work around it silently.

### S5: reader UX (last, because it needs evidence this plan cannot produce)

1. **Run a `naive-ux-check` session** with the current child test readers, on the three questions section 0 of
   plan v2 names: does a 3-hop rewind read as "the app took my turn" (A13b), is the lower back-chevron confusable
   with the one that exits the book (A18), does a hero-name field with a shuffle land as a toy or a restriction
   (A11). These are empirical and currently answerable; do not build A11, A13b or A18 first.
2. **A11** (M): request-page copy. Adopt ADR-023 section 4's wording verbatim rather than drafting an alternative.
   Drop the fixed-structure statement and the unnameable forbidden-theme warning from the kid surface; add "A
   grown-up reads your idea first. Then it takes a little while to write your book." Shuffle is display-only among
   generic names. Serve the guardian set off `ReasonCode` / `band_profile` / `content_nogo`; the kid response
   still omits `content_nogo` values entirely.
3. **A12** (M): enable Go back in continuation reads. `replayRecordedPath` fails closed when
   `path[0] !== start_node` (`engine.ts:288-297`), disabling the control in exactly the state-carrying series
   books where a reader has most to lose. A bug fix.
4. **A13b** (M): a second, separately labelled ending-screen affordance, "Try a different way", walking up to 3
   hops to the last node offering a real pick and falling back to one step when there is none. Availability stays
   today's `path.length > 1` and replayable, **never** "an untaken choice exists within 3 hops", which would hide
   the button at the 88 preserved climaxes. Leave the in-story one-step Go back untouched (A13a).
5. **A18** (S): give the story-level control a circular-arrow glyph distinct from the top-bar Leave chevron, and
   make the ending-screen affordance primary weight rather than ghost.
6. **B4** (S): `machine.ts:108` resets to the start node with declared initials, fabricating `has_lantern=true`
   and `vigor=5` a continuation reader never earned while discarding carried state.

*Verification*: `npm run lint`, `npm run typecheck`, `npm run test:run`, plus the Playwright mocked tier. A13b
needs a test at an ending reached through a single-choice corridor, since that is the 58-of-73 case.

### S6: close out

Update `validator-rules.md` (the catalog is lockstep-tested, so this is not optional), `capability-register.md`
(K19's copy dependency, and A11's delivered state), and append to `authoring-lessons-log.md` if #416 has merged by
then. Confirm no `PL-23`/`PL-24`/`SR-8` reference crept in.

---

## 4. Rule-ID reservations

| ID | Owner | State |
| --- | --- | --- |
| `L2-14` | this plan (A14) | Free on `main` and not claimed by #416, whose "adds L2-13" is a catalog entry for a rule already in `layer2.py`. Claim it |
| `SR-8` | **PR #416** | Implemented, tested, catalogued there. **Do not use.** Reserve |
| `SR-9` | this plan (B3) | Claim, accepting a documented gap at `SR-8` until #416 merges |
| `PL-23`, `PL-24` | **PR #416** | Implemented there (clock advisory, ending-mix shape). **Do not use.** Reserve |
| `PL-25` | this plan | Reserved only if a fail-depth floor is ever built. Plan v2 argues it probably is not needed once A13 lands |

Re-verify against #416's branch immediately before claiming any of these, per plan v2's amended method rule 5:
`main` alone is not a sufficient basis.

---

## 5. Explicitly not in this plan

Unchanged from plan v2 sections 2 and 5, restated so scope does not drift:

- **A10** (empty teen `short` cells), **A15** (retire without deleting progress), **A17** (tombstone card):
  triggered, not scheduled. Their triggers are in plan v2 section 0.
- All eight deferred items behind named prerequisites, including reading telemetry, the outcome-mix floor keyed on
  fail-kind mix, challenge mode, alternate beat phrasings, per-reader scoping, and the guardian visibility
  ceiling.
- A fail-depth floor, an open-vocabulary similarity signature, a per-topology outcome floor, and any
  snapshot-based restart mechanism. Each is refuted or deferred with reasoning in plan v2 section 2.

---

## 6. Working agreements

1. **One slice, one branch, one PR**, off `claude/story-diversity-analysis-4hdbdw` or off `main` as each slice
   lands. Do not accumulate all seven into one review.
2. **Every new threshold is calibrated against the committed corpus before it ships**, and if it flags an entire
   class the threshold is suspect, not the class. This is #416's AL-051 and it already changed two decisions in
   this plan (A8's `TAU_STRUCT` rejection, A14's band scoping).
3. **Signed commits, Conventional Commits, no em-dashes.** RAD tags on anything touching timing, external
   resources, data integrity, concurrency, security, or the safety gate.
4. **A gate lands with its expected failure set stated up front.** "0 new failures" is a claim to verify, not an
   assumption.
