---
schema_type: planning
title: "Research Base for the Story Scale and Structure Framework"
description: "Index and provenance for the committed research notes behind ADR-011 and the story
  structure/diversity work. Rebuilt 2026-08-02 because the original notes cited by ADR-011 were not
  committed; one of those originals, the four-source reconciliation, was recovered and committed
  2026-08-03."
tags:
  - planning
  - research
status: active
owner: core-maintainer
purpose: "Give ADR-011's citations a committed, re-examinable home, per the stale-citation note in
  ADR-011 and design-review-kid-appeal-2026-08-01.md section 6 item 5."
component: Strategy
source: "Index only; it makes no claims of its own. Every substantive claim lives in the three notes it
  indexes, cyoa-structure-measurements.md (external research pass, 2026-08-02),
  choice-agency-pacing-and-failure.md (external literature pass, 2026-08-02), and
  cyoa-research-reconciliation.md (four-source cross-check written 2026-06-23, committed 2026-08-03),
  each of which carries its own grading scheme. Provenance for the rebuild itself: ADR-011's stale
  citation note and design-review-kid-appeal-2026-08-01.md section 6 item 5."
---

# Research Base for the Story Scale and Structure Framework

## Provenance

ADR-011 cites `docs/planning/research/` as the home of its empirical basis (JHM 2019 plus a
four-source reconciliation). That directory was not committed; the citation was flagged stale on
2026-08-01. This directory rebuilds the base from primary sources, fetched and verified 2026-08-02 on
branch `claude/story-structure-diversity-ba8swy`, as part of the story-structure diversity analysis
([../story-structure-diversity-critical-analysis.md](../story-structure-diversity-critical-analysis.md)).

**Update (2026-08-03).** The four-source reconciliation ADR-011 cites was not lost: the original
2026-06-23 document was recovered and is now committed here as
[cyoa-research-reconciliation.md](cyoa-research-reconciliation.md). ADR-011's citation of it is
therefore live, not stale. Read it with its dated status notes: it was written before ADR-011, its
Section 7 "net deltas" made claims about a generator that has since changed, and the corrections are
recorded inline rather than by rewriting the original text. The rebuild above stands on its own and is
not superseded by the recovery; the two overlap on JHM and reach compatible conclusions.

Key outcome of the rebuild: the "JHM 2019" citation is real and verified. Full citation:
Adams, Beckelhymer and Marr, "Choose Your Own Adventure: An Analysis of Interactive Gamebooks Using
Graph Theory," *Journal of Humanistic Mathematics* 9(2), 2019, DOI 10.5642/jhummath.201902.05
(open access). Per-constant verdicts against the paper's Table 4: the endings median (20, range
11-42) holds exactly; the ~90-120 page-node range and the max-indegree 1.5 are supported as fair
glosses of the paper's distributions; ~5 decisions/playthrough is derived from the paper's figures,
not stated by it. Two further ADR-011 constants (words/node, total words) remain unverifiable from
any indexed source and are labeled designer priors.

## Notes in this directory

- [cyoa-structure-measurements.md](cyoa-structure-measurements.md): the Ashwell pattern taxonomy as
  published (eight patterns plus variants, with the mapping to the project's six-topology enum), the
  verified JHM 2019 study, Swinehart's One Book Many Readings, gamebook digraph measurements
  (including an original 350-section Lone Wolf measurement), and the word-count evidence.
- [choice-agency-pacing-and-failure.md](choice-agency-pacing-and-failure.md): the academic base for
  choice design and perceived agency, children's interactive e-book meta-analyses, reading-rate norms
  by age (with an audit of the per-band wpm constants), failure and persistence by age, and
  branching-structure/replay research. Ends with a consolidated constants table and an explicit list
  of seven silences where the literature offers no anchor.
- [cyoa-research-reconciliation.md](cyoa-research-reconciliation.md): the four-source cross-check
  ADR-011 cites. Reconciles three commissioned deep-research reports against the peer-reviewed JHM
  (2019) primary source, resolving conflicts to best-estimate values with confidence grades, and
  isolates the metric mislabel (path-length reported as decisions) that would otherwise miscalibrate
  the depth budget. Written 2026-06-23, committed 2026-08-03, with dated status notes marking the
  claims later overtaken by shipped code.

## Standing rules for this directory

- Every claim carries its source with URL or DOI. **One documented exception:** the three commissioned
  reports R1-R3 behind `cyoa-research-reconciliation.md` exist only as gitignored local artifacts and
  carry neither a URL nor a DOI, so they cannot satisfy this rule retroactively. That note states the
  gap explicitly and grades anything resting on them as unverifiable secondary synthesis.
- Three tagging schemes are in deliberate use, one per note, because they answer different questions.
  The structure note tags **provenance** (MEASURED: fetched primary source or computed from one;
  REPORTED: secondhand; UNVERIFIABLE: not traceable). The academic note grades **evidence
  strength** (STRONG: meta-analysis, replicated, or preregistered; MODERATE: well-cited or
  convergent studies; WEAK: single small study, theory piece, or gray literature). The reconciliation
  note grades **measurement support** (Very high: two or more independent measured sources agree;
  High: one measured source; Medium-High: narrow sample or inferred neighbour; Medium: no measurement).
  A note states which scheme it uses in its frontmatter or opening.
- A constant the literature cannot anchor is labeled a designer prior, and its calibration path
  (usually our own reading telemetry) is named.
- Research notes cited by an ADR are committed in the same PR as the ADR change that cites them.
