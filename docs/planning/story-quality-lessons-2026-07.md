---
title: "Story Quality and Author Feedback: Lessons from the Wyrmreach Build"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Turn the three-book ceiling-scale authoring run into concrete changes to the validator, the authoring loop, and the reader-feedback path."
tags:
  - planning
  - validation
  - authoring
  - quality
component: Development-Tools
source: "wyrmreach-series-report.md"
---

# Story Quality and Author Feedback: Lessons from the Wyrmreach Build

> **Status**: Proposed | **Date**: 2026-07-25
> **Evidence**: [wyrmreach-series-report.md](./wyrmreach-series-report.md),
> [wyrmreach-series-design.md](./wyrmreach-series-design.md)

## Purpose and method

Building three production 16+ gamebooks (305 / 305 / 746 nodes, 77,218 words, one of them at the
top of the largest cell ADR-011 defines) exercised the authoring path end to end for the first time
at series scale. Every item below is a **defect or gap observed while building**, not a speculative
improvement, and each one names the file that would change. Severity is about reader impact and
about whether the current tooling would let the problem ship again.

Two of these are already-shipped defects that were fixed while writing this document; they are
marked **fixed**. The rest are proposals awaiting a decision.

---

## Summary table

| # | Finding | Severity | Surface |
| --- | --- | --- | --- |
| A | A hand-authored skeleton cannot pass the `skeleton-promotion` CI gate at all | **Blocking** | `.github/workflows/skeleton-promotion.yml`, `scripts/check_promotion_bundle.py` |
| B | `estimated_minutes` is unvalidated author-declared metadata that readers see | **High** (fixed in these books) | `validator/policy.py`, `mutation/identity.py` |
| C | No reader-outcome feedback ever reaches an author | **High** | `db/models.py::Completion`, new dashboard |
| D | The words-per-node advisory rewards the floor, not the cell's target | **High** (fixed in these books) | `validator/policy.py`, `validator/band_profile.py` |
| E | RL-13 scores `<<FILL>>` directives, so every skeleton emits one warning per node | Medium | `validator/reading_level.py` |
| F | No within-story ending-mix advisory: 51% death endings passes clean | Medium | `validator/policy.py` |
| G | The rule catalog is missing L2-13 and misstates RL-13's implementation | Medium | `docs/planning/validator-rules.md` |
| H | Authoring-time headroom feedback lives in a series-only script | Medium | `scripts/check_skeleton.py` |
| I | L2-11 reports the symptom, never the cause | Low-Medium | `validator/layer2.py` |
| J | Integrity checks must compare independently derived artifacts | Process | `scripts/check_fill_integrity.py` |

---

## A. A hand-authored skeleton cannot pass the promotion gate (blocking)

`.github/workflows/skeleton-promotion.yml` fires on any PR touching `skeletons/**` and runs
`scripts/check_promotion_bundle.py` over every added or modified skeleton. That prover requires a
`<slug>.lineage.json` sidecar unconditionally (`check_promotion_bundle.py:260-262`), because it was
built to re-prove **flywheel-derived mutants** against their parent's content hash.

There is no lineage sidecar anywhere in `skeletons/`. Verified:

```text
$ uv run python scripts/check_promotion_bundle.py skeletons/16+/the-{vault-of-nine-iron,sunless-march,ninth-hand}.json
ok: skeleton passes gate and brief checks     (x3)
FAIL promotion-bundle proof:
  - the-ninth-hand.json: missing lineage sidecar the-ninth-hand.lineage.json
  - the-sunless-march.json: missing lineage sidecar the-sunless-march.lineage.json
  - the-vault-of-nine-iron.json: missing lineage sidecar the-vault-of-nine-iron.lineage.json
```

So the three Wyrmreach skeletons cannot land on `main` through this gate, and neither can a
one-word fix to any of the thirteen hand-authored skeletons already in the catalog. Those thirteen
are green today only because CI proves *changed* files and none of them has been touched since the
workflow landed. The gate is latent, not satisfied.

This is a genuine hole in the automation boundary rather than a nuisance: ADR-020's intent is that
nothing enters the catalog unproven, and a hand-authored skeleton is currently *unprovable* rather
than *proven*. The fix is to give the hand-authoring path its own proof obligation instead of
exempting it.

**Recommended fix.** Teach `check_promotion_bundle.py` two bundle kinds:

- *derived* (lineage sidecar present): today's behaviour, unchanged, including the parent-hash check.
- *authored* (no lineage sidecar): require an `<slug>.origin.json` sidecar naming the author, the
  declared cell, and the source spec path, then run `check_skeleton`, the theme contract when
  present, and the WS-5 anti-clone floor against the live in-cell catalog. The anti-clone floor is
  the check that actually matters for catalog health, and it applies to authored shells just as well
  as derived ones.

Fail closed on a third case: a skeleton with neither sidecar stays a failure, so the gate never
silently degrades to "no proof required".

---

## B. `estimated_minutes` is unvalidated metadata the reader sees (high, fixed here)

ADR-011 section 4 defines three clocks, and `metadata.estimated_minutes` is specifically the
**fastest-finish** one: words on the shortest satisfying path divided by the band pace anchor.
`mutation/identity.py::recompute_estimated_minutes` already implements exactly that, and it is
applied on mutation resync. **Nothing validates it at the gate**, so on any hand-authored or
imported book the field is whatever the author typed.

All three Wyrmreach books declared it wrong, by 3-6x:

| Book | Declared (before) | Canonical fastest-finish | ADR-011 cell target |
| --- | --- | --- | --- |
| The Vault of Nine Iron | 40 | **8** | ~11 min |
| The Sunless March | 40 | **8** | ~11 min |
| The Ninth Hand | 90 | **14** | ~14 min |

I had been declaring engagement time, not the fastest-finish clock. **Fixed**: the three specs now
declare 8 / 8 / 14, matching `recompute_estimated_minutes` exactly, and all three books re-gate clean.

**Recommended fix (two parts).**

1. Add a PL-series advisory that compares declared `estimated_minutes` against
   `recompute_estimated_minutes(story)` and warns past a tolerance (say 25%). This is pure reuse:
   the derivation exists and is unit-tested; only the gate wiring is new. Advisory, not blocking,
   because a deliberately padded estimate is an editorial call.
2. Decide what the library card should actually show. "14 min" on a 746-node, 42,085-word gamebook
   whose whole-world clock is **3.2 hours** is technically the fastest-finish number and
   practically a broken promise to a kid choosing a book. ADR-011 already defines the whole-world
   clock (`total_words / reading_pace`); the Storybook schema surfaces only one field. Proposal:
   add `estimated_minutes_whole_world` alongside it, derive both, and let the kid and guardian
   surfaces show "about 15 minutes to finish, hours to explore". This is the single highest-value
   reader-facing change in this document.

---

## C. No reader outcome ever reaches an author (high)

This is the biggest structural gap, and most of the data already exists.

- `db/models.py::Completion` records `(child_profile_id, storybook_id, version, ending_id, found_at)`:
  exactly which endings readers actually reach.
- `db/models.py::ReadingState.path` records the route a reader took, node by node.
- `db/models.py::Rating` records a 1-5 score per child per book.
- `StorybookVersion.skeleton_slug` already links a published version back to the skeleton it was
  filled from.

`Completion` is read in exactly five places (`api/me.py`, `api/reading.py`, `api/reading_history.py`),
and every one of them is a **per-child** read for that child's own history. Nothing aggregates
across readers, so nobody can currently answer:

- Which of The Ninth Hand's 232 endings has any reader ever reached? (Plausibly a small fraction.)
- Where do readers stop? A node that ends 40% of sessions is either a difficulty cliff or a
  confusing passage, and it is invisible today.
- Do readers rate books filled from one skeleton lower than another? `skeleton_slug` makes this a
  single join, and it is the only signal that could tell us a *skeleton* is weak rather than a
  particular fill.

**Recommended fix.** A read-only story-quality dashboard, modelled directly on the existing
`api/moderation_dashboard.py` + `moderation/insights.py` pair, which already does this shape of work
(aggregate persisted records into evidence plus suggestions, read-only, admin-gated). Concretely:

- `analytics/story_insights.py` (pure, unit-testable): given completions, reading states, and
  ratings for a version, return ending-reach counts, unreached-ending list, session-stop histogram
  by node, and rating distribution.
- `api/story_insights.py`: admin-gated read-only routes, per version and aggregated per
  `skeleton_slug`.
- Feed the same aggregate into the WS-8 flywheel as a second trigger signal. Today
  `flywheel_scan.py` reads only `CELL_SATURATED`, which is **request-time demand**. Reader outcomes
  are the missing **quality** signal: a cell whose books are read once and abandoned needs different
  catalog work than a cell with unmet demand.

**Privacy constraint, non-negotiable.** Per ADR-018 and `privacy-model.md`, these aggregates must be
computed over counts only, never over child-identifying rows, and must respect the same CASCADE
purge as the underlying tables. An ending-reach count is a story property; a named child's route is
not. Any endpoint here should be aggregate-only by construction, with a minimum-cohort floor before
a figure is returned, so a single-child family cannot be re-identified from its own aggregate.

---

## D. The words advisory rewards the floor, not the target (high, fixed here)

PL-19 for `(16+, gamebook)` declares mean 80 words/node as the target and 55-110 as the advisory
band. Because the gate only reports in-band or out-of-band, **55 reads as "pass"** and there is no
signal that 55 is 31% below the cell's design intent. I authored all three books to the floor:

| Book | Mean words | Target | Whole-world clock | ADR-011 cell whole-world |
| --- | --- | --- | --- | --- |
| The Vault of Nine Iron | 55.7 | 80 | 77 min | ~110-175 min |
| The Sunless March | 59.5 | 80 | 82 min | ~110-175 min |
| The Ninth Hand | 56.4 | 80 | 3.2 hr | ~2.9-4.6 hr |

Books 1 and 2 land **below** their cell's intended whole-world range, and it is not a structural
problem, it is 24 words per passage. Book 3 only lands in range because its node count compensates.
At mean 80, book 3 would be roughly 59,700 words rather than 42,085.

This is the mechanism behind finding B: a lean word mean drags the fastest-finish clock down, which
is why the canonical estimate came out at 8 minutes for a cell whose target is ~11.

**Recommended fix.** Make the report state distance from target, not just band membership:
`PL-19 words: story mean 55.7/node is 30% below the (16+, gamebook) target of 80 (advisory band
55-110)`. One message change in `validator/policy.py`, and it converts a silent pass into
actionable feedback. Optionally add a tighter two-sided production band (say target +/- 25%) for
`production_eligible` stories, keeping the wide band for MVP/test tiers.

---

## E. RL-13 scores FILL directives (medium)

`validator/policy.py:272` already special-cases skeleton bodies: if the body contains `<<FILL`, PL-19
reads the declared `words=N` instead of counting tokens. `validator/reading_level.py` has no such
guard, so RL-13 computes a Flesch-Kincaid grade over the FILL directive's own beat text, which is a
single run-on clause and therefore always out of band. Result: **one guaranteed warning per node** on
every skeleton (305 per medium book, 746 for The Ninth Hand). That is 746 warnings carrying zero
signal, which trains the reader of the report to ignore RL-13 entirely.

**Recommended fix.** In `check_reading_level`, skip any body containing `_FILL_MARKER`, exactly as
PL-19 does. Six lines, and it makes skeleton-stage RL-13 output meaningful (empty) instead of noise.
The marker constant should move somewhere both modules import rather than being duplicated.

---

## F. No within-story ending-mix advisory (medium)

PL-15 forbids specific ending *kinds* per band and PL-17 enforces an endings *count* floor. Nothing
looks at the mix. The Ninth Hand is **118 death endings out of 232 (51%)** and gates clean at 16+,
where no kind is forbidden. A book that was 95% death would also gate clean.

The ingredients exist: `diversity/structure.py` already computes normalised `ending_kind_hist` and
`valence_hist`, but only as features for *between-story* anti-clone distance, never as a
*within-story* health check.

**Recommended fix.** A PL-series advisory over the existing histograms: warn when any single ending
kind exceeds a per-band share, or when positive-valence endings fall below a floor. For a 16+
gamebook, "few wins and many fails" is the declared intent (ADR-011 section 5), so the threshold
should be generous, perhaps 60% for one kind. The point is that the number becomes visible to a
reviewer rather than being an unexamined consequence of how many failure leaves the author happened
to write.

---

## G. The rule catalog has drifted from the code (medium)

`docs/planning/validator-rules.md` states in its Purpose section that "adding, removing, or
renumbering a rule requires a revision to this document". Two violations:

1. **L2-13 is absent.** It exists in `validator/layer2.py`
   (`HAND_AUTHORING_NODE_CEILING`, `_l2_13_finding`), it is the single finding a 746-node book
   produces, and it is described in `ws5-structure-state-variation-design.md` and
   `pathfinder-structure-exploration.md`, but the catalog's Layer 2 table stops at L2-12 and its
   header still says "Version 1.2, Updated 2026-07-16". The catalog is the document a reviewer
   consults when a finding appears; a rule that fires in production and is missing from it is a
   real gap.
2. **RL-13's entry says the grade is "computed by textstat".** It is not:
   `validator/reading_level.py` deliberately vendors `_flesch_kincaid_grade` to avoid a heavy NLP
   dependency, and the module docstring explains why. `textstat` is not in `pyproject.toml`. Anyone
   reasoning about score stability from the catalog would reach the wrong conclusion.

**Recommended fix.** Add the L2-13 row with its real message template, correct the RL-13 entry to
name the vendored implementation and its 20-word floor (`_MIN_WORDS_FOR_FK`, which is itself
undocumented and materially changes which nodes get scored), and bump the catalog version. Consider
a test that asserts every `rule_id` the validator can emit appears in the catalog, so this class of
drift cannot recur silently.

---

## H. Authoring-time headroom feedback lives in a series-only script (medium)

The thing that made ceiling-scale authoring tractable was a **budget headroom report**: nodes
against the cell, endings and decisions against the PL-17 floors, word mean against the envelope,
depth against the cap, fastest satisfying finish against the PL-20 arc floor, and the ending mix.
It made hitting the depth ceiling and the arc floor a tuning exercise instead of a rewrite.

That report is `scripts/build_series_book.py --check`, which only understands the Wyrmreach spec
format. `scripts/check_skeleton.py` is the general tool, and on a passing skeleton it prints only:

```text
stats: nodes=746 endings=232 fill_nodes=746 cell=(16+, long, gamebook) topology=branch_and_bottleneck tier=2
ok: skeleton passes gate and brief checks
```

No depth, no fastest-finish, no floor margins. An author is told pass or fail with no sense of how
close to an edge they are.

**Recommended fix.** Move the headroom report into `check_skeleton.py` behind a `--headroom` flag
(or make it the default on success), computed from the typed Storybook rather than from a spec
format. Every input it needs is already available to that script, and it would serve the generation
pipeline and the guardian editor as well as hand authors.

---

## I. L2-11 reports the symptom, never the cause (low-medium)

L2-11's message is `choice '{choice_id}' on node '{node_id}' is never visible in any reachable
configuration (condition always false)`. True, and it does not say why. Across this build every
single L2-11 had one of exactly two causes:

1. **Carried-variable polarity.** In a `carries_state: true` continuation a carried variable
   initialises `true`, so any `== false` condition on it is unsatisfiable. This is finding F3 of the
   13-16 stress test, hit again in book 2.
2. **Grant-order.** A gate on a new variable placed earlier in the graph than any node that grants
   it, hit at `a1_scout` in book 2 and repeatedly while wiring book 3.

Both are mechanically detectable at the point the finding is raised. The walk already knows the
variable's declared initial value and which nodes carry granting effects.

**Recommended fix.** Extend the finding message with a cause hint when one of these two patterns
matches: `... (condition always false; 'iron_key' initialises true in a carries_state continuation,
so '== false' is unsatisfiable)` or `... (no node granting 'deep_charts' precedes this gate)`. This
also directly improves the Stage C repair prompt, which receives these findings verbatim: a repair
model told the cause fixes the right thing, and a model told only the symptom tends to delete the
branch.

---

## J. Integrity checks must compare independently derived artifacts (process)

A real bug in my own tooling: when `--skeleton` and `--prose` were passed together, the builder
wrote the *prose* story to the skeleton path. Both artifacts came from the same in-memory object, so
`check_fill_integrity.py` compared a file against itself and reported success. The check was
**vacuous, while passing**, and it had silently made book 2's earlier verification meaningless. It
was caught only because the two files had suspiciously identical byte sizes.

The generalisable lesson: a comparison check is only as good as the independence of its two inputs,
and a check that cannot fail is worse than no check because it manufactures confidence.

**Recommended fix.** Give `check_fill_integrity.py` a self-test: assert the two inputs are not the
same file and that the skeleton input actually contains `<<FILL` markers while the filled input
contains none. Both conditions hold for every legitimate pair and both would have failed loudly on
the drift bug. The same reasoning is worth applying to the `contract` CI job's OpenAPI drift check
and to any future proof that compares two generated files.

---

## Recommended sequencing

Grouped by what unblocks what, not by severity alone.

**Do first (unblocks landing work, small and self-contained):**

1. **A**, the promotion gate's authored-bundle path. Without it no hand-authored skeleton can reach
   `main`, including the three books just built.
2. **E**, skip FILL bodies in RL-13. Six lines, removes 746 noise warnings per ceiling-scale book.
3. **G**, the rule-catalog revision, plus the test that pins emitted rule ids to the catalog.
4. **J**, the fill-integrity self-test.

**Then (author-facing feedback quality):**

5. **D**, distance-from-target in the PL-19 message.
6. **H**, the headroom report in `check_skeleton.py`.
7. **I**, cause hints on L2-11, which also improves Stage C repair.
8. **F**, the ending-mix advisory.

**Then (reader-facing, the largest piece):**

9. **B**, the `estimated_minutes` advisory, then the whole-world clock decision and the kid and
   guardian surfaces that show it.
10. **C**, the story-quality insights module, the admin dashboard, and the flywheel's second
    trigger signal.

Items 1-8 are validator and tooling work that fits Phase 4b (Editor+UX) or Phase 5 (Hardening)
without new data model. Items 9-10 need a schema addition and a new read surface, and item 10 needs
a privacy review against `privacy-model.md` before any endpoint is designed.

## Related documents

- [ADR-011: Story scale framework](./adr/adr-011-story-scale-framework.md), the three clocks and the cell table
- [ADR-020: Mutation-derived skeletons and catalog growth](./adr/adr-020-mutation-derived-skeletons-and-catalog-growth.md)
  and the [WS-8 catalog flywheel design](./ws8-catalog-flywheel-design.md), the automation boundary finding A sits inside
- [ADR-018: Children's privacy compliance](./adr/adr-018-childrens-privacy-compliance.md), with `privacy-model.md`, the constraint on finding C
- [Validation Rule Catalog](./validator-rules.md), the target of finding G
- [Privacy model](./privacy-model.md), the constraint on finding C
- [Series stress test findings](./series-stress-test-findings.md), F1 and F3, both re-confirmed here
