---
schema_type: planning
title: "Research Base for the Story Scale and Structure Framework"
description: "Index and provenance for the committed research notes behind ADR-011 and the story
  structure/diversity work. Rebuilt 2026-08-02; the original notes cited by ADR-011 were never
  committed."
tags:
  - planning
  - research
status: active
owner: core-maintainer
purpose: "Give ADR-011's citations a committed, re-examinable home, per the stale-citation note in
  ADR-011 and design-review-kid-appeal-2026-08-01.md section 6 item 5."
component: Strategy
---

# Research Base for the Story Scale and Structure Framework

## Provenance

ADR-011 cites `docs/planning/research/` as the home of its empirical basis (JHM 2019 plus a
four-source reconciliation). That directory was never committed; the citation was flagged stale on
2026-08-01. This directory rebuilds the base from primary sources, fetched and verified 2026-08-02 on
branch `claude/story-structure-diversity-ba8swy`, as part of the story-structure diversity analysis
([../story-structure-diversity-critical-analysis.md](../story-structure-diversity-critical-analysis.md)).

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

## Standing rules for this directory

- Every claim carries its source with URL or DOI.
- Two tagging schemes are in deliberate use, one per note, because they answer different questions:
  the structure note tags **provenance** (MEASURED: fetched primary source or computed from one;
  REPORTED: secondhand; UNVERIFIABLE: not traceable), while the academic note grades **evidence
  strength** (STRONG: meta-analysis, replicated, or preregistered; MODERATE: well-cited or
  convergent studies; WEAK: single small study, theory piece, or gray literature). A note states
  which scheme it uses in its frontmatter or opening.
- A constant the literature cannot anchor is labeled a designer prior, and its calibration path
  (usually our own reading telemetry) is named.
- Research notes cited by an ADR are committed in the same PR as the ADR change that cites them.
