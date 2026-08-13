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

**Assumption (data integrity), tagged per this repo's RAD standard, updated 2026-08-13 after a
first sourcing pass:** the original draft of this doc flagged every specific claim as recalled
from a proposing model's training data, unverified against a live source. That first pass is now
done for 10 of the proposal's named titles (see the next section); every claim in the corpus data
file below is backed by a real `WebSearch` result rather than recollection. One title from the
original proposal, *Violet and the Mystery Next Door* (cited only for its Common Sense Media
framing, not put through this session's research batch), remains unverified in the sense the
original draft described; drop or verify it before citing it anywhere. **Methodology caveat that
held across all 10 research runs:** `WebFetch` was blocked by this session's network egress
policy for every review-site domain attempted (kirkusreviews.com, goodreads.com,
commonsensemedia.org, slj.com, thestorygraph.com, amazon.com, and others), with no exceptions
across ten independent agent runs. Every finding below is therefore reconstructed from
`WebSearch`'s snippet-level synthesis of those pages, not a first-hand page read; confidence is
capped accordingly in the data file. This is real signal (multiple independent runs converged on
the same specific claims for the same book), not equivalent to opening the page directly, and it
is worth stating plainly here since a future curation session on different infrastructure should
expect to try a direct fetch before assuming it will fail the same way.

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

## First sourced batch: 10 of ~30 titles (2026-08-13)

The full sourced entries, each with real citations, paraphrased evidence, and per-source
confidence, live in
[`data/craft-benchmark-corpus.yaml`](./data/craft-benchmark-corpus.yaml). This section summarizes
what that batch actually found; treat the YAML file as authoritative on any conflict with the
summary below.

| Band | Title | What held up vs. the original proposal | Craft-label headline |
|---|---|---|---|
| 5-7 | *Endlessly Ever After* | Confirmed real (Snyder/Santat, Chronicle, 2022); age-fit conflicts across sources (SLJ: PreS-Gr3; Horn Book/parents: one-on-one only, dark endings) | Strong choices/replayability; character depth not addressed by any source found |
| 5-7 | *Jungle Adventure* | High title-collision risk resolved to a specific book (Murray/Kimpimäki, words & pictures); "personalized" claim was a partial fit, not a real-child-name product | Mixed choice meaningfulness; strong replayability |
| 8-10 | *The Cave of Time* | Confirmed; found the most quantified craft data point in the whole batch (a historian's count: 39 choice points, 40 endings, 18 good/16 bad/6 ambiguous) | Weak character depth/dialogue; strong replayability; choices sometimes read as arbitrary |
| 8-10 | *Meanwhile* | Confirmed; Kirkus explicitly names shallow/circular branch plots alongside praising the construction | Strong choice consequence, weak character depth: an explicit, named trade-off |
| 8-10 | *Traitors in Space* | Held up almost exactly against Kirkus's actual starred review (replayability praised, character development explicitly secondary) | Strong replayability; weak character depth |
| 8-10 | *Search for a Giant Squid* | Real book, but not the guessed series (Chronicle's "Science Explorers," not Capstone's "You Choose") | Strong educational integration and replayability; thinnest failure-mode signal of the batch |
| 11-12 | *Samurai vs. Ninja* | Confirmed (Shiga, Abrams Fanfare); positive-example framing holds at the professional tier, more mixed at the reader tier (series fatigue) | Strong choice consequence and ending payoff; character depth never addressed |
| 11-12 | *Leviathan* | Required active disambiguation from Westerfeld's unrelated non-interactive novel of the same title | Readers directly disagree on replayability (two endings vs. none); navigation called both a strength and a weakness |
| Negative-example reference | *The Citadel of Whispers* | Confirmed word-for-word in substance: Kirkus names six distinct failure modes in one review (limited character growth, haphazard paths, under-contextualized decisions, abrupt endings, stilted dialogue, anachronistic diction, clunky exposition) | The single richest negative-craft source in the batch |
| Negative-example reference | *Eighth Grade Witch* | Confirmed, but the claimed defects split across two distinct editions (2012 prose original vs. 2021 graphic-novel adaptation) rather than one review set | Weak choice meaningfulness and ending payoff |

**Cross-cutting findings worth acting on, not just filing:**

- **Character depth is the format's default weak point, not this project's weak point alone.**
  6 of 10 titles score `weak` or `not_reported` on character depth/change; none score `strong`.
  That's independent, external corroboration of
  [design-review-kid-appeal-2026-08-01.md](./design-review-kid-appeal-2026-08-01.md) section 2.4's
  finding from the opposite direction: a craft rubric built from this corpus should calibrate
  "weak-to-absent character arc" as typical for the format, not as a uniquely damning finding
  against generated stories, while still treating a genuinely `strong` result as the differentiator
  worth chasing.
- **Replayability is a weak differentiator by itself.** 7 of 10 titles score `strong`; it is
  close to a format universal, not a craft signal. The two titles where reviewers actively
  *disagree* with each other on replayability (*Leviathan*) are more informative than the seven
  where everyone agrees it's good.
- **One well-sourced negative professional review outperforms a pile of five-star ratings**, as
  the original proposal claimed. *The Citadel of Whispers*'s single Kirkus review produced more
  distinct, actionable failure modes than the other nine titles' reader-review aggregates
  combined.
- **Title-collision risk is real, not hypothetical.** 2 of 10 titles required active
  disambiguation to avoid citing the wrong book entirely (*Leviathan* vs. Westerfeld's novel;
  *Search for a Giant Squid* vs. a guessed-wrong series). Any future curation pass needs the same
  "confirm the specific ISBN/edition before trusting a title match" discipline this batch used.

Twenty titles remain to reach the ~30-title target; the next batch should skew toward filling the
still-empty 3-5 band (this batch has none) and toward titles that, like *The Citadel of Whispers*,
have a substantive professional review rather than reader-aggregate-only coverage, since that is
where the actionable failure-mode signal actually came from.

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

This started as a scoping document; as of 2026-08-13 it also has real, sourced data behind it, not
just a plan. 10 of a roughly 30-title target are sourced in
[`data/craft-benchmark-corpus.yaml`](./data/craft-benchmark-corpus.yaml), each citation backed by
an actual `WebSearch` result rather than recollection. What remains genuinely unscheduled work,
still awaiting the owner decision `UW-N11` names, is:

1. **Scaling to ~30 titles**, prioritizing the 3-5 band (currently empty) and
   professional-review-backed titles over reader-aggregate-only ones, per the cross-cutting
   findings above.
2. **Deciding where the corpus feeds in**: `drafting_guide.md`'s positive-craft section (already
   recommended by `design-review-kid-appeal-2026-08-01.md` section 2.4) is the lowest-risk
   consumer and needs no owner sign-off beyond normal doc editing; a new advisory-only reviewer
   module alongside `moderation/fidelity_review.py` is the higher-cost option and does need one,
   since it is a new LLM-judge call in the generation path.
3. **No schema, validator, or generation change is proposed here regardless of that decision.**

See `UW-N11` in [unscheduled-work-register.md](./unscheduled-work-register.md) for the
phase-linkage entry this doc's own conventions require, updated with this batch's completion.
