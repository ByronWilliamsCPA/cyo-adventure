---
title: "External Craft-Review Benchmark Corpus: Feasibility and Scope"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Evaluates an externally-authored AI proposal to benchmark generated stories against
  professional/library/parent/reader reviews of published children's interactive fiction, and scopes
  what a first, legally sound version of that corpus would actually look like."
tags:
  - planning
  - measurement
  - moderation
  - authoring
---

# External Craft-Review Benchmark Corpus: Feasibility and Scope

## Origin

This doc evaluates a concept proposed by an external AI model (pasted into a session on
2026-08-13, no visibility into this repository): build a reference corpus from professional
children's-book reviews (Kirkus, School Library Journal), parent-oriented reviews (Common Sense
Media), reader-community ratings (Goodreads, StoryGraph), and retailer reviews, convert them into
structured craft labels, and use that corpus as an external quality benchmark for this project's
generated stories, distinct from internal graph/structure metrics.

That makes it the same kind of artifact as
[external-scope-comparison-2026-08-05.md](./external-scope-comparison-2026-08-05.md) and its
`UW-N*` register rows: an outside, LLM-generated document compared against the live project,
kept as reference material where it adds something real and discarded where it does not. It is
also a sibling to [cyoa-book-benchmark-comparison.md](./cyoa-book-benchmark-comparison.md), which
already benchmarks published CYOA/gamebooks against this project, but on the opposite axis: that
doc compares *structural mechanics* (state, conditions, topology) against the schema and
validator; this doc is about *craft quality* (character arc, choice meaningfulness, ending
payoff) as judged by external reviewers, which nothing in this repository currently benchmarks
against.

## Verdict: feasible, but as manual curation, not automated gathering

Two existing planning docs already name the gap this proposal would close, from the code side
rather than the review-corpus side:

- [story-structure-diversity-critical-analysis.md](./story-structure-diversity-critical-analysis.md)
  section 6.3 ("Measure the experience, not the graph") proposes per-path experience metrics
  (decision cadence, agency density, outcome-mix entropy) computed from deterministic walks, with
  no external reference point to calibrate them against.
- [design-review-kid-appeal-2026-08-01.md](./design-review-kid-appeal-2026-08-01.md) section 2.4
  ("Nothing in the pipeline asks for the story to be fun") found zero occurrences of humor, wonder,
  or delight across every generation template and the drafting guide, and recommended adding
  positive craft guidance from intuition, not from what published reviewers actually reward or
  penalize.

So closing this gap with an external reference corpus is worth doing. But "gather the necessary
information" cannot mean an automated pipeline: as of 2026-08-13, none of the proposal's named
sources offer a bulk or licensed API for their review text.

| Source | Access in practice | Verdict |
|---|---|---|
| Kirkus Reviews | Paywalled full reviews; ToS forbids bulk reproduction | Manual read of individual reviews only |
| School Library Journal | Subscriber-gated; same ToS posture as Kirkus | Manual read only |
| Common Sense Media | Free to browse, no bulk/licensing API | Manual read only |
| Goodreads | Public API deprecated and closed to new keys for years | Manual read of individual review pages only |
| StoryGraph | No public API at all | Manual read only |
| Retailers (Amazon, B&N, Bookshop.org) | Review scraping is against most retailers' ToS | Manual read only, lowest-priority source |

The proposal's own "Copyright and terms-of-use boundaries" section already reaches this
conclusion (store title/ISBN/source/URL plus a short derived label, never the review text
itself); the only correction needed here is to make explicit that this rules out a scraper or any
automated corpus-assembly tool from the start, not just from the production architecture. A
human has to read each review and fill in the schema below.

**Assumption (data integrity), tagged per this repo's RAD standard:** the specific titles, review
claims, and quoted findings in this doc's candidate list (Kirkus's stated criticisms of *The
Citadel of Whispers*, Common Sense Media's framing of *Violet and the Mystery Next Door*,
Goodreads rating counts for *The Cave of Time*, etc.) were recalled from the proposing model's
training data in the original session, not independently verified against a live source in this
session (no `WebFetch`/`WebSearch` was run against any of these review pages). Treat every
specific claim below as plausible, not confirmed, matching the existing hedge in
`cyoa-book-benchmark-comparison.md`'s own book-mechanic citations. **Verification required:**
before any title enters the actual corpus, re-read its source review live and correct or drop the
claim if it does not hold up.

## Craft-dimension taxonomy, mapped onto what this project already has

The proposal's 19-dimension list is good but generic. Trimmed and mapped onto vocabulary this
repository already uses, so a labeled corpus is directly actionable rather than a parallel
glossary:

| Dimension | Existing project hook |
|---|---|
| Choice meaningfulness / consequence visibility | `diversity/` structural metrics measure branch divergence today; no reviewer-grounded threshold exists for what counts as "meaningful" |
| Character depth / character change | Unmeasured; `validator/character.py` checks structural presence, not arc |
| Ending payoff | `story-structure-diversity-critical-analysis.md` section 2.7 already flags ending-valence miscoding as a related, narrower problem |
| Navigation clarity | Not applicable to this project's digital reader (no page-turn navigation), skip this dimension entirely |
| Age fit / vocabulary complexity | `validator/reading_level.py`, `validator/band_profile.py` already gate this quantitatively; a reviewer corpus could validate whether the FK-grade proxy actually tracks what reviewers call age-appropriate |
| Replayability | Untested; the app's own multi-ending structure is the mechanism, no metric exists |
| Dialogue quality / prose craft | Closest existing hook is `moderation/fidelity_review.py`'s beat-fidelity LLM judge, which checks *that* prose matches its beat, not craft quality |
| Emotional safety | Owned by `moderation/` safety classifiers already; out of scope for this corpus, do not duplicate |
| Educational integration | Not applicable; this project's skeletons are not educational-nonfiction hybrids |

Dropping the not-applicable dimensions (navigation clarity, illustration support, educational
integration) leaves six that are genuinely unmeasured today: choice meaningfulness, character
depth/change, ending payoff, replayability, dialogue/prose craft, and validating the reading-level
proxy against reviewer judgment.

## Candidate corpus (unverified, per the data-integrity assumption above)

Kept in the same four age-band groups the proposal used, trimmed to the titles most relevant to
this project's own bands (5-7, 8-10/8-11, 11-12/11-13):

| Band | Candidate titles | Note |
|---|---|---|
| 5-7 | *Endlessly Ever After*, *Jungle Adventure* | Picture-book-style branching; closest match to this project's 3-5/5-7 bands |
| 8-10 | *The Cave of Time*, *Meanwhile*, *Traitors in Space*, *Search for a Giant Squid* | Closest comparison set to the 8-11 core band |
| 11-12 | *Samurai vs. Ninja*, *Leviathan* | Closest to the 11-13 band |
| Negative-example reference | *The Citadel of Whispers*, *Eighth Grade Witch* | Kept separately: the proposal's strongest point is that a well-written negative professional review is more actionable than dozens of five-star ratings, since it names a specific failure mode rather than "my child loved it" |

This is a candidate list to re-verify and expand to roughly 30 titles during the actual curation
pass, not a finished corpus.

## Failure-mode-to-check mapping (proposed, not built)

The proposal's most useful table maps recurring review criticism to a possible check. Restated
against this project's real modules, marked proposed where nothing exists yet:

| Reviewer criticism | Possible check | Status |
|---|---|---|
| "The choices do not change the ending" | Compare reachable ending set per fork option; `diversity/` has the graph-walk primitives, no such metric is assembled today | Proposed |
| "The character does not develop" | Compare a character's tracked `Variable` state before/after major nodes | Proposed; needs an explicit "major scene" annotation the schema does not have |
| "The ending is abrupt" | Check that nodes referencing a plot thread's setup exist on the path leading to a given ending | Proposed; closest existing analogue is `validator/theme_leak.py`'s cross-node consistency checking, different purpose |
| "The options feel arbitrary" | Each choice's options express a distinct tactic/value, not near-duplicate wording | Overlaps `moderation/leaf_diversity.py` and the anti-template guard already in `story_requests/authoring_plan.py` and `generation/binding.py`; extend rather than duplicate |
| "The prose is too difficult" | Combine FK-grade with a reviewer-validated vocabulary/sentence-complexity signal | `validator/reading_level.py` already computes FK grade; the reviewer corpus's contribution would be validating the threshold, not adding a new check |

Every "Proposed" row above needs its own scoped ADR-style decision before implementation, per
this project's existing pattern (a narrow, purpose-built check, not a general rubric engine); none
of them are ready to build directly from this doc.

## What this doc is not proposing

- No scraper, crawler, or bulk-download tool against any review site.
- No storage or reproduction of review text in this repository, in prompts, or in generated
  output. Only title/ISBN/source/URL plus a short internally-authored label per the proposal's
  own schema.
- No classifier training or fine-tune. The corpus's first use, if commissioned, is prompt and
  rubric design (feeding `drafting_guide.md`'s positive-craft section, already recommended by
  `design-review-kid-appeal-2026-08-01.md` section 2.4) and possibly a new advisory LLM-judge
  reviewer alongside `moderation/fidelity_review.py`, never a gating check on day one.

## Recommendation

This is a scoping document, not committed work. If commissioned, the actual deliverable is a
person (not an unsupervised agent) reading roughly 30 reviews and filling in the label schema from
the original proposal, re-verifying every specific claim per the verification-required note above
before it enters the corpus. No schema, validator, or generation change is proposed here; the earliest
concrete use is feeding `drafting_guide.md`'s positive-craft section and, if that proves useful,
a new advisory-only reviewer module. See `UW-N11` in
[unscheduled-work-register.md](./unscheduled-work-register.md) for the phase-linkage entry this
doc's own conventions require.
