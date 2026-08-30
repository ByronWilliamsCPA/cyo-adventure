---
title: "External Craft-Review Benchmark Corpus: Feasibility and Scope"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Evaluates an externally-authored AI proposal to benchmark generated stories against
  professional/library/parent/reader reviews of published children's interactive fiction, and scopes
  what a first, legally sound version of that corpus would actually look like. Re-verified against
  live primary sources and against current main on 2026-08-30; the corpus's consumer is now the
  LLM quality panel in cyo-measurement-workplan-2026-08-12.md."
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
payoff) as judged by external reviewers.

**Scope note added 2026-08-30.** This document was drafted on 2026-08-13 and said that nothing in
this repository benchmarked craft quality. That framing needs re-anchoring:
[cyo-measurement-workplan-2026-08-12.md](./cyo-measurement-workplan-2026-08-12.md) landed after
this doc's merge base and does benchmark craft quality, through deterministic detectors plus an LLM
quality panel with pre-registered decision rules, and
[story-quality-technique-review-2026-08-15.md](./story-quality-technique-review-2026-08-15.md)
surveys the technique families. What none of that supplies is an **external** reference point: an
answer to "what score is good", as opposed to "does this instrument discriminate". That narrower
gap is what remains, and this document should be read as addressing it rather than as addressing an
absence of craft measurement.

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

  > **That gap is closed, as of 2026-08-30.** This document was drafted on 2026-08-13 against a
  > tree where it was open, and the closure changes what the corpus is for. Verified on current
  > main: `src/cyo_adventure/generation/templates/drafting_guide.md` now carries a **"Craft for
  > Delight"** section (line 277), cross-referenced twice from the reading-level table above it,
  > and `src/cyo_adventure/generation/variation.py` defines the axes `running_joke`,
  > `awestruck_wonder`, `playful_figurative`, and `mischievous_narrator`. The pipeline does now ask
  > for the story to be fun. What it still does not have is any evidence that its intuitions about
  > *how* match what published reviewers reward, which is a **validation** need rather than a
  > creation need. The corpus's job moved accordingly: it is no longer the source of the
  > drafting guide's positive-craft section, it is the external check on one that already exists.
  > That is a smaller job and a better-defined one.

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
conclusion; the correction needed here is to make explicit that this rules out a scraper or any
automated corpus-assembly tool from the start, not just from the production architecture. A human
has to read each review and fill in the schema below. The proposal states its own storage posture
as "title/ISBN/source/URL plus a short derived label, never the review text itself"; that is **not**
what the data file does, and the accurate description is given under
[What the data file actually holds](#what-the-data-file-actually-holds-stated-accurately) below.

**Assumption (data integrity), tagged per this repo's RAD standard.** The original draft flagged
every specific claim as recalled from a proposing model's training data. A first sourcing pass on
2026-08-13 replaced recollection with `WebSearch` results for 10 of the proposal's named titles.
A second pass on **2026-08-30** re-ran those checks from a session with working network egress and
read the cited pages directly. One title from the original proposal, *Violet and the Mystery Next
Door* (cited only for its Common Sense Media framing, never put through either research batch),
remains unverified in the sense the original draft described; drop or verify it before citing it
anywhere.

**What the second pass found, and why the first pass's caveat was not enough.** The 2026-08-13 pass
carried a blanket caveat: `WebFetch` was blocked by that session's egress policy for every
review-site domain attempted, on all ten agent runs, so every finding was snippet synthesis rather
than a first-hand read, with confidence capped accordingly. That caveat was honest and it was
insufficient, because it treated the risk as uniform. It is not. Re-reading the pages directly
promoted 14 source rows across 9 of the 10 titles to `primary_source_fetch` and **falsified three
claims that the first pass had recorded at `confidence: high`**:

| Claim | Recorded as | Direct read |
|---|---|---|
| *Traitors in Space* carries a Kirkus **starred review** | `confidence: high` | No star on the page. Struck. The "45+ endings" figure is also Kirkus's, not SLJ's |
| *Leviathan* carries a Kirkus **starred review** | `confidence: high` | No star on the page. Struck |
| Kirkus called *The Citadel of Whispers*'s supporting cast (Zara, Saeed, Arjun) "interesting" | `confidence: high` | The names appear, but only in the review's plot summary. It does not praise the cast. "Intriguing" is applied to the magic system and the political machinations, and hedged with "lightly developed" |

The pattern is specific and worth carrying forward: **snippet synthesis reproduced review substance
faithfully and invented accolades.** Every criticism paraphrase that was re-checked held up, in the
*Citadel* case close to verbatim. What did not hold up was a star, a star, and a compliment. Those
are the claims a summary is most likely to confabulate, because they are the claims a search
snippet's surrounding marketing copy is most likely to supply. A future curation pass should treat
accolades (stars, awards, "best of" placements) as a separate verification class from evaluative
substance, and should not accept a bare publication homepage as a citation for one, which is how
the batch's one *surviving* star claim was cited before this pass replaced the URL.

Two starred-review claims did survive: *Endlessly Ever After* (SLJ) and *Search for a Giant Squid*
(Booklist), both now cited to the publisher's own review round-up, which prints the star and names
the awarding publication. Both trade publications' own sites return HTTP 403 to an unauthenticated
fetch, so an interested secondary source is the best available citation and is labeled as such.

## Craft-dimension taxonomy, mapped onto what this project already has

The proposal's 19-dimension list is good but generic. Trimmed and mapped onto vocabulary this
repository already uses, so a labeled corpus is directly actionable rather than a parallel
glossary:

> **Re-derived against current main, 2026-08-30.** The version of this table written on 2026-08-13
> said "unmeasured" of three dimensions this project has since built deterministic instruments for.
> The rows below name what exists now; each was confirmed by reading the module, not by grepping
> for a filename.

| Dimension | Existing project hook |
|---|---|
| Choice meaningfulness / consequence visibility | **Built, as a reported statistic.** `validator/consequence.py` (W3) measures, per fork, rejoin distance and the set of variable names whose values differ on arrival, over the configuration graph rather than the node graph, and reports the two separately because they fail independently. Its own docstring records that it is deliberately not a gate and that `BandProfile.reconvergence_ceiling` stays unenforced. What is still missing is exactly what this corpus offers: a reviewer-grounded threshold for what counts as "meaningful" |
| Character depth / character change | Still unmeasured as an arc. `validator/character.py` checks structural presence |
| Ending payoff | Partly reachable through `validator/continuity.py` (below); `story-structure-diversity-critical-analysis.md` section 2.7 flags ending-valence miscoding as a related, narrower problem |
| Navigation clarity | Not applicable to this project's digital reader (no page-turn navigation), skip this dimension entirely |
| Age fit / vocabulary complexity | `validator/reading_level.py`, `validator/band_profile.py` already gate this quantitatively; a reviewer corpus could validate whether the FK-grade proxy actually tracks what reviewers call age-appropriate |
| Replayability | Untested; the app's own multi-ending structure is the mechanism, no metric exists |
| Dialogue quality / prose craft | **Built.** `validator/prose_craft.py` holds the shared self-repetition and narrative-person definitions, wired onto the request path by `moderation/prose_craft.py` (advisory, deliberately not a `Verdict.FLAG`, since neither defect is repairable by the pipeline's bounded auto-repair) and run offline by `scripts/check_prose_craft.py`. `validator/dialogue.py` detects tagged as well as quoted speech, after three prior implementations counted quote marks and scored a book with fifteen unquoted spoken lines at 0.000. The 2026-08-13 version of this row named `moderation/fidelity_review.py` as the closest hook; that is now out of date |
| Emotional safety | Owned by `moderation/` safety classifiers already; out of scope for this corpus, do not duplicate |
| Educational integration | Not applicable; this project's skeletons are not educational-nonfiction hybrids |

Dropping the not-applicable dimensions (navigation clarity, illustration support, educational
integration) leaves six the proposal wanted labeled. Of those, three now have deterministic
instruments on main and three do not, and the split changes what the corpus is asked to supply:

- **Instrumented, needing calibration**: choice meaningfulness (`validator/consequence.py`),
  dialogue/prose craft (`validator/prose_craft.py`, `validator/dialogue.py`), and the reading-level
  proxy (`validator/reading_level.py`, `validator/band_profile.py`). For these the corpus supplies
  a threshold, not a measurement. A number exists; nothing says what value of it is good.
- **Still unmeasured**: character depth/change, ending payoff, and replayability. For these the
  corpus supplies the prior evidence that would justify building an instrument at all, and its
  cross-cutting findings below argue against building two of the three.

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
| 8-10 | *The Cave of Time* | Confirmed. The batch's most quantified craft claim (39 choice points, 40 endings, an 18/16/6 good/bad/ambiguous split, 114 pages) **did not survive the 2026-08-30 direct read**: the cited history states forty endings and describes the balance only qualitatively. Forty endings and the hand-drawn 1969 branch diagram stand; the other three figures are withdrawn | Weak character depth/dialogue; strong replayability; choices sometimes read as arbitrary |
| 8-10 | *Meanwhile* | Confirmed; Kirkus explicitly names shallow/circular branch plots alongside praising the construction | Strong choice consequence, weak character depth: an explicit, named trade-off |
| 8-10 | *Traitors in Space* | Substance held up almost exactly against Kirkus (replayability praised, character development and scene-setting explicitly secondary to side quests), but the claimed **Kirkus star does not exist** and was struck 2026-08-30; the "45+ endings" figure is Kirkus's, not SLJ's | Strong replayability; weak character depth |
| 8-10 | *Search for a Giant Squid* | Real book, but not the guessed series (Chronicle's "Science Explorers," not Capstone's "You Choose") | Strong educational integration and replayability; thinnest failure-mode signal of the batch |
| 11-12 | *Samurai vs. Ninja* | Confirmed (Shiga, Abrams Fanfare); positive-example framing holds at the professional tier, more mixed at the reader tier (series fatigue) | Strong choice consequence and ending payoff; character depth never addressed |
| 11-12 | *Leviathan* | Required active disambiguation from Westerfeld's unrelated non-interactive novel of the same title; a claimed **Kirkus star does not exist** and was struck 2026-08-30 | Readers directly disagree on replayability (two endings vs. none); navigation called both a strength and a weakness |
| Negative-example reference | *The Citadel of Whispers* | Confirmed close to word-for-word on the 2026-08-30 direct read: Kirkus names the failure modes as recorded (limited character growth, haphazard paths, under-contextualized decisions, abrupt and disjointed endings, stilted dialogue, anachronistic diction, clunky infodumps). One *positive* signal was struck: the review names Zara, Saeed, and Arjun only in its plot summary and never praises the supporting cast | The single richest negative-craft source in the batch, and the only entry that came out of re-verification stronger |
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
  combined, and it is the only entry in the batch that came out of the 2026-08-30 re-verification
  pass stronger than it went in.
- **Accolades and substance need separate verification, added 2026-08-30.** Across the ten titles,
  every re-checked criticism paraphrase held up and three of four checked accolades did not (two
  fabricated Kirkus stars, one compliment relocated from a plot summary). A curation process that
  spot-checks by asking "does the review say something like this" will pass all three. The check
  has to be "does the page show the star", asked separately.
- **Title-collision risk is real, not hypothetical.** 2 of 10 titles required active
  disambiguation to avoid citing the wrong book entirely (*Leviathan* vs. Westerfeld's novel;
  *Search for a Giant Squid* vs. a guessed-wrong series). Any future curation pass needs the same
  "confirm the specific ISBN/edition before trusting a title match" discipline this batch used.

Twenty titles remain against the original ~30-title target, but see the Recommendation below:
scaling is no longer the first thing to do with this batch, and the 2026-08-30 re-verification pass
is the reason. If a next batch is commissioned, it should skew toward filling the still-empty 3-5
band (this batch has none) and toward titles that, like *The Citadel of Whispers*, have a
substantive professional review rather than reader-aggregate-only coverage, since that is where the
actionable failure-mode signal actually came from.

## Failure-mode-to-check mapping (mostly built, re-derived 2026-08-30)

The proposal's most useful table maps recurring review criticism to a possible check. The
2026-08-13 version of this table marked every row **Proposed**. That is no longer true of most of
it, and the correction is not cosmetic: a scoping doc whose value rests on naming unbuilt work is
worth much less if the work is built. Each status below was confirmed by reading the module.

| Reviewer criticism | Check | Status on main |
|---|---|---|
| "The choices do not change the ending" | Per-fork rejoin distance and state delta over the configuration graph | **Built.** `validator/consequence.py` (W3), reported separately rather than pooled, and explicitly not a gate |
| "The character does not develop" | Compare a character's tracked `Variable` state before/after major nodes | **Still proposed**, and still needs a "major scene" annotation the schema does not have. The only row of the five that is genuinely open |
| "The ending is abrupt" / a node presupposes state the path never established | Name the content a node cannot presuppose on the taken path | **Built.** `validator/continuity.py` (W6 follow-on), on the provable instance of a book whose endings count three rescues on a path holding one. Its docstring records that it is exact but flags 3,815 of 4,472 nodes, so it is a reported statistic and explicitly *not* a gate candidate |
| "The options feel arbitrary" | Each choice's options express a distinct tactic/value, not near-duplicate wording | Overlaps `moderation/leaf_diversity.py` and the anti-template guard in `story_requests/authoring_plan.py` and `generation/binding.py`; extend rather than duplicate. Unchanged |
| "The prose is too difficult" / prose craft generally | FK grade, plus self-repetition and narrative-person detectors | **Built.** `validator/reading_level.py` for FK grade; `validator/prose_craft.py` for the shared self-repetition and narrative-person definitions, wired on the request path by `moderation/prose_craft.py`. The corpus's contribution is validating the threshold, not adding a check |
| *(not anticipated by the proposal)* "Who is that?": a proper noun a reader meets before the prose introduces it | Introduction check scoped to proper nouns, where the general definite-noun-phrase rule was unusable | **Built.** `validator/naming.py` (PN-1), on a book that names a companion in all 65 of its 65 nodes and never says he is a dog |

One row of six is still open, and one row exists that the proposal never anticipated. Both facts
argue the same way: **this project's craft-check design is now ahead of the external proposal that
prompted this document, and the corpus's remaining value is calibration rather than ideation.**
`validator/naming.py` is the sharpest illustration. It exists because the general form of the check
(require an introduction for every definite noun phrase) measures 3.48 findings per node and is
unusable, and because proper nouns are a decidable subset where the same question can be asked
soundly. No amount of reviewer labeling would have produced that narrowing; it came from measuring
a failed formulation. Any row this doc still marks proposed needs its own scoped decision before
implementation, per this project's existing pattern of a narrow, purpose-built check rather than a
general rubric engine.

## What this doc is not proposing

- No scraper, crawler, or bulk-download tool against any review site.
- No classifier training or fine-tune. The corpus's first use, if commissioned, is calibration:
  validating `drafting_guide.md`'s existing "Craft for Delight" guidance and supplying thresholds
  to the quality panel described in
  [cyo-measurement-workplan-2026-08-12.md](./cyo-measurement-workplan-2026-08-12.md), never a
  gating check on day one.

### What the data file actually holds, stated accurately

The 2026-08-13 version of this section said the corpus stores "only title/ISBN/source/URL plus a
short internally-authored label", and "never the review text itself". **That was not what the data
file did**, and the discrepancy is corrected here rather than left for a reader who trusts the
stated posture and never audits the fields. Several `positive_signals` and `negative_signals`
entries in [`data/craft-benchmark-corpus.yaml`](./data/craft-benchmark-corpus.yaml) are short
verbatim or near-verbatim fragments of the reviews they cite, several of them paywalled. The honest
description is:

- **Short attributed quotation plus derived labels.** Brief phrases, each attached to a named
  publication and a URL, alongside craft labels this project wrote. Quoting "stilted dialogue" is
  better evidence than paraphrasing it, and the 2026-08-30 re-verification pass depended on the
  quotations being checkable against the pages, so the practice is kept and the description is
  fixed to match it.
- **Still excluded, and this is the line that matters:** no review reproduced whole or in
  substantial part, and no review text routed into a prompt, a generation input, or a training set.
  A quotation long enough to substitute for reading the review does not belong in the file.

Short attributed quotation for the purpose of commentary is very likely fair use, and the point of
restating the posture is not that the old one was legally wrong. It is that a stated posture
stricter than the practice is worse than an accurate one: it discourages the audit that would have
caught the mismatch, and it is the same failure the licensing register's `green` definition had, in
which the written rule and the stored data disagreed and only the data was machine-readable.

## Recommendation

This started as a scoping document; it now has real, sourced data behind it, 10 titles in
[`data/craft-benchmark-corpus.yaml`](./data/craft-benchmark-corpus.yaml), re-read against primary
sources on 2026-08-30.

**The consumer question is answered, and it is not the one this doc originally named.**
[cyo-measurement-workplan-2026-08-12.md](./cyo-measurement-workplan-2026-08-12.md) did not exist at
this document's merge base and now governs how this project measures story quality. It runs an LLM
**quality panel** with per-criterion instruments, and it does not take a criterion on faith:
**W4** (per-criterion instrument variance) flags a criterion whose spread across cells is too
narrow to discriminate, and caught the `dialogue` criterion at a spread of 0.088; **W7** (the
known-bad seeded-defect battery, the workplan's designated blocking item) retires any criterion
that fails to detect its own seeded defect or that fires on a clean control; **W12** and **W13**
add a human comprehension read and an age-appropriateness rubric.

That panel is this corpus's actual consumer, and the fit is close. A panel criterion needs a
threshold, and nothing internal can supply one: W7 establishes that a criterion *discriminates*,
not what score is *good*. That is precisely what external calibration provides, and it is the one
thing in this document that main's own measurement machinery does not already do better. The
advisory LLM-judge module this doc originally floated alongside `moderation/fidelity_review.py`
should be considered **withdrawn**: the panel is that module, better specified, already governed by
pre-registered decision rules, and already funded in the workplan's sequencing.

What remains genuinely unscheduled work, still awaiting the owner decision proposed as `UW-N11`:

1. **Calibrate the quality panel's thresholds against the 10 titles already sourced.** This is the
   deliverable, and it is a smaller job than the one originally proposed. The two cross-cutting
   findings above are the substance: character depth is a format norm rather than a defect unique
   to generated stories, and replayability is close to a format universal and therefore a poor
   discriminator. Both are threshold-shaped inputs to a panel that currently has none, and both
   are independent of every licensing question in the companion document.
2. **Only then, whether to scale toward ~30 titles**, prioritizing the 3-5 band (currently empty)
   and professional-review-backed titles over reader-aggregate-only ones. Twenty further
   reader-aggregate rows would not have changed either cross-cutting finding, and the 2026-08-30
   re-verification pass is an argument for depth over breadth: three high-confidence claims in ten
   titles did not survive a direct read, and re-checking what exists costs less than sourcing more.
3. **No schema, validator, or generation change is proposed here regardless of that decision.**

**Register linkage.** This doc's own conventions require a row in
[unscheduled-work-register.md](./unscheduled-work-register.md), and `UW-N11` is the id proposed for
it: main's `UW-N` cluster currently stops at `UW-N10`, so the id is free. The row is deliberately
**not** added by the change that landed this document. Register ids collide when two branches
allocate from the same cluster concurrently, and the resolution is a renumber plus merge rather
than a text merge, so rows from separate workstreams are batched into a single consolidation
change. Until that lands, treat `UW-N11` as proposed rather than assigned, and do not cite it as
though the row exists. Its proposed scope is item 1 above, calibrating the quality panel's
thresholds against the ten titles already sourced, with scaling to ~30 titles as a dependent
follow-on rather than the headline.
