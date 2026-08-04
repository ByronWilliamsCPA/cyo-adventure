---
schema_type: planning
title: "CYOA Research Reconciliation: Four Sources Cross-Checked"
description: "Cross-checks three deep-research reports on commercial CYOA/gamebook structure against
  each other and against the peer-reviewed JHM (2019) primary source, reconciling conflicting metrics
  to best-estimate values with confidence levels. Written 2026-06-23 on branch
  feat/modal-generation-tiers, ahead of the story-scale framework later formalized in ADR-011.
  Section 5 item 3's reconvergent-leaves finding was later superseded for this repo's own corpus;
  see the 2026-08-03 correction note in that section and ADR-011 section 7."
tags:
  - planning
  - research
  - storybook
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams (with Claude)"
purpose: "Give the architecture-revision team a reconciled, confidence-graded set of structural and
  pacing constants from four independent CYOA research sources, ahead of calibrating the generator's
  depth, node-size, and ending-count budgets."
component: Strategy
source: "Four sources cross-checked 2026-06-23. One is fully citable: JHM (Adams, Beckelhymer & Marr,
  2019, J. Humanistic Mathematics 9(2):44-59, DOI 10.5642/jhummath.201902.05). The other three are
  commissioned deep-research reports R1, R2, R3, held only as gitignored local artifacts with no URL or
  DOI; Section 9 lists their paths and states plainly that they cannot be re-fetched. The four are not
  fully independent: all three reports cite JHM and/or UCSB, so some of their agreement is restatement
  of shared underlying data rather than corroboration (Section 2). Rule applied: measured sources win
  over estimate-based reports on structural metrics where they conflict."
---

# CYOA Research Reconciliation: Four Sources Cross-Checked

Audience: architecture-revision team. Companion to `commercial-cyoa-graph-theory-handoff.md` (never
committed to this repository; no copy exists in git history, so the reference is informational, not a
link).

## 1. Purpose

Three deep-research reports were commissioned on commercial CYOA / gamebook structure. This document
cross-checks them against each other and against the peer-reviewed primary source, resolves the conflicts to
best-estimate values with confidence levels, and surfaces the architecture-relevant dimensions the reports
add beyond the graph-theory paper. Read this before treating any single number from the reports as ground
truth; several disagree, and one (R2) mislabels a metric in a way that would directly miscalibrate the
generator's depth budget.

Bottom line up front: all four sources converge on one thesis, though not independently (all three reports
cite JHM and/or UCSB, so part of the convergence is shared data restated; see Section 2). **Commercial kids'
CYOA is short, shallow, and binary; its many endings come from many short reconvergent leaves, not deep
trees; and the genre raises age by escalating theme and tone, not branch depth.** Calibrate the generator to
that shape.

**Correction pointer (2026-08-03):** the "reconvergent leaves" clause above is what the four sources found
about the commercial corpus, and is left as written for that reason. It is **refuted as a design target for
this repository's own corpus.** Read the Section 5 item 3 correction before calibrating anything from this
summary: our endings are single-parent terminals, and the ending share comes from breadth off a branchy
spine, not from folding paths into shared endings.

## 2. The four sources and their evidence tiers

| ID | Source | Tier | Trust for... |
| --- | --- | --- | --- |
| **JHM** | Adams, Beckelhymer & Marr (2019), *J. Humanistic Mathematics* 9(2):44-59 | Primary, measured (40 books, hand-computed digraphs, ages 9-12) | Corpus-level structural distributions, applied to 8-11 / 10-13 as an **adjacent-band proxy**: the measured cohort is 9-12, which straddles both bands and matches neither exactly |
| **R3** | `tmp/deep-research-report (7).md` | Secondary, but cites a second measured source (UCSB Transverse Reading Gallery graph logs + Boyles path stats) | Per-title measured node counts, path lengths, reading-level framing, edition conflicts |
| **R1** | `tmp/compass_artifact_wf-7721d44d-...text_markdown.md` | Secondary synthesis | Themes, digital tier, exposure ratio, per-title CYOA specifics |
| **R2** | `tmp/CYOA Gamebook Structural Analysis.md` | Secondary synthesis | Age-band matrix shape, fail-state design, reconvergence/state tiering |

Rule applied throughout: when measured sources (JHM, UCSB-via-R3) and an estimate-based report conflict on a
structural metric, the measured value wins. Reports win for what measurement does not cover (digital tier,
reading levels, themes, fail-state policy, exposure economics, edition history). All three reports cite JHM
and/or UCSB, so several "findings" are restatements of the same underlying data, occasionally imprecise.

## 3. Conflicts resolved (core 8-11 / middle-grade band)

**Tagging scheme used by this note.** The "Conf." column below, and the per-row confidences in Section 6,
grade **measurement support**, a third scheme alongside the provenance and evidence-strength schemes the
directory README describes. **Very high** = two or more independent measured sources agree. **High** = one
measured source, corroborated in direction by the estimate-based reports. **Medium-High** = measured on a
narrow sample, or measured for one metric and inferred for a neighbouring one. **Medium** = no measurement
at all; reconciled from estimate-based reports only. Every grade refers only to the four sources in
Section 2; nothing here draws on a source outside them.

| Metric | JHM (measured) | UCSB via R3 (measured) | R1 | R2 | Reconciled | Conf. |
| --- | --- | --- | --- | --- | --- | --- |
| Node count (text pages) | mean 99.6 (88-115) | Cave 103, Journey 98 | ~110-120 | 100-140 | **~90-120 nodes** | Very high |
| Words per node (beat) | not measured | implied ~85-115 | ~250 | 150-200 | **~100-150 words** | Medium |
| Total words per book | not measured | ~8-11k (est.) | 20-30k | ~15k | **~8-15k words** | Medium |
| Number of endings | mean 21.2, median 20 (11-42) | Cave 40, Journey 42, House of Danger 20 | early 30-44, late 7-20 | "20-40" | **median ~20 (11-42); declines over time 44 -> 7** | High |
| Choices per decision | max outdegree mean 2.58 (2-4) | avg degree 2.0-2.2; rare nodes 4-12 | 2-3 | 2 (mode) | **2-3 typical; rare mystery hubs 5-12** | High |
| Decisions per playthrough | derived ~5 avg, ~7-8 longest | Boyles 8.7-14.5 pages read (~3-7 decisions) | Silk King avg 4.68 (2-6) | "8-15" (mislabeled) | **~4-5 avg, ~7 longest** | High |
| Longest path (in nodes) | mean 27.6, max 45 | diameters 14-18 (early titles) | Chimney Rock 9-21 | per-title 14/24/42 | **~14 (short) to ~28 (avg longest), 45 max** | High |
| Reconvergence | max indegree 1.5; >50% pure trees | "meaningful," rising with time-travel themes | ~2 links early | tree at 8-11 | **tree-dominant; light reconvergence, rising with age** | High / Med |
| Reading level (core CYOA) | not measured | ~500-700L framing | 660-710L | 400-700L | **~500-710L** | Med-High |

Cross-validation worth noting: JHM (88-115 nodes) and UCSB (Cave 103, Journey 98) were produced by separate
teams using different tooling and agree. That makes the 8-11 node-count range the most trustworthy number in
this entire body of research.

## 4. The errors that would mislead an architecture decision

### 4.1 R2 labels node-path-length as "decisions" (highest impact, now confirmed by R3)

R2's matrix gives "8-15 decisions" for middle grade, and its appendix column "Max Depth (Decisions)" lists
14, 24, and 42. Those are **longest path length in page-nodes**, not decisions. R3 independently confirms the
distinction: Boyles's measured runs are 8.7-14.5 **pages read** per playthrough, and R3 states plainly these
are "page-read counts, not raw node totals." The genuine decisions-per-path figure is **~4-5 average, ~7
longest**, now triangulated by three independent derivations (JHM-derived ~5/7-8; R1 Silk King 4.68; R3/Boyles
8.7-14.5 pages divided by ~3.3 pages-between-decisions).

Why it matters: if the team reads R2's "8-15 decisions" or "42," they will conclude the generator's depth
budget is 2-7x too shallow and inflate it. Do not. **Path length in nodes and decisions per path are
different metrics.**

**Status (2026-08-03).** This paragraph originally continued: "the generator's `max_depth` budget
(6 / 8 / 10) is calibrated in decisions and is already correct against the genre, sitting near the genre's
longest-path end." That sentence was wrong on all three of its claims, and it committed the very conflation
the rest of this section warns against, so it is corrected here rather than left to mislead:

- **Unit: hops, not decisions.** `validator/layer1.py::_branch_depth` returns `nx.dag_longest_path_length`
  over the subgraph reachable from the start node, which is an **edge count** on the longest start-to-ending
  path (nodes minus one). Nothing in the gate counts decisions.
- **Layer: 6 / 8 / 10 is the fallback, not the enforced budget.** Those are band-level values in
  `validator/band_profile.py::_PROFILES` (8-11, 10-13, 13-16). For any matrix cell ADR-011 actually offers,
  `_PRODUCTION_CELLS` supersedes them; its `max_depth` runs 15 to 93, and 8-11 prose is 23 / 30 / 35 for
  short / medium / long.
- **Provenance: not research-derived.** `band_profile.py` says of `max_depth` in terms: "It is NOT from
  research; treat it as tunable." It is a product guardrail set near 2.5x the cell's fastest-finish floor,
  chosen to catch a runaway near-linear chain. Calling it "confirmed correct against the genre" asserted a
  validation that was never performed.

Compared like with like the production budgets do land in the genre's range: 8-11 prose at 23-35 hops is
24-36 nodes, against JHM's measured longest path of mean 27.6 and max 45 nodes. Note that as agreement of
scale, not as the calibration the original sentence claimed.

### 4.2 Physical pages vs text nodes are conflated

R2 lists *The Cave of Time* at 144 pages; R1 and R3 list 115-117. 144 is the modern reissue's **physical page
count** (text + full-page art + front matter); ~100-115 is the measured **text-node count** (JHM max text
pages = 115; UCSB Cave = 103). Use text-node counts (~90-120) for graph sizing, never physical page counts.

### 4.3 Advertised / per-edition ending counts drift

*Journey Under the Sea* appears as 41 (JHM, corrected), 42 (R1, R3), and 43 (R2). JHM documented that the
advertised 42 was a publisher error; treat **41** as the verified value, and never seed thresholds from
cover-advertised counts. R3 adds a deeper version of this: the same title differs across editions (see 5.5).

## 5. Dimensions the reports add (absorb these into the architecture)

JHM is purely structural. The reports contribute five dimensions it lacks, each with a direct project
implication:

1. **Exposure ratio = a generation-cost metric** (R1, R3). A single CYOA playthrough exposes only ~15-20% of
   the text (R1: ~2.5-3k of ~8-15k words; R3 and Choice of Games cite ~20%). For a per-token budget this is
   the waste fraction: ~80% of generated prose is unseen on any one read. **Action:** add exposure ratio to
   the modal-tiers cost model; higher reconvergence raises exposure, lowering waste.
2. **Fail-state policy must be age-gated (child-safety, not style)** (R1, R2, R3). 5-8: zero death, "never too
   scary," use try-again loops (Dragonlarks, Time Machine). 8-11: failure/entrapment common but
   adventure-forward. 10-13 horror: ending-variety and jump-scares (Goosebumps). 13-16: lethal,
   resource-based. **Action:** enforce a per-band fail-state rule, especially a no-death constraint on the
   youngest tier. Not currently a structural gate.

   **Status (2026-08-03): landed.** It is a structural gate now.
   `BandProfile.forbidden_ending_kinds` holds `{DEATH, CAPTURE}` for 3-5 and 5-8 and `{DEATH}` for 8-11,
   enforced as a blocking ERROR by PL-15 (`validator/policy.py`). 10-13 and 13-16 are unrestricted, which
   matches the horror-variety and lethal rows of the Section 6 matrix.
3. **Reconvergent bottlenecks are the coherence and ending-inflation tool** (R2, R3). R3's key structural
   finding: the large ending counts that "make covers sparkle" come from **many short reconvergent leaves**,
   not deep trees. **Action:** to get a bigger-feeling story, add more short leaves and reconvergence, not
   depth. Keep 8-11 tree-dominant; introduce more reconvergence at 10-13+.

   **Correction (2026-08-03):** this finding does not hold for this repository's own skeleton corpus and
   must not be treated as a design target here. A measurement of the shipped corpus (61 skeletons) found
   that 54 of 61 have every ending at indegree exactly 1: endings are single-parent terminals, not
   reconvergent leaves, and the ~15-22% ending share is achieved by breadth (many terminals off a branchy
   spine), not by folding paths into shared endings. Reconvergence is real, but it concentrates at internal
   bottleneck/hub nodes, not at endings. Resolution: ADR-011 section 7 ("Clarification (2026-07-27):
   reconvergence and endings"), landed via PR #425 (merged 2026-07-28, commit "docs(adr-011): clarify
   reconvergence sits at internal bottlenecks not endings"). Decision: no per-band reconvergence magnitude
   gate (`BandProfile.reconvergence_ceiling` stays `None`); choices-per-decision 2-3 remains an authoring
   guideline, not a hard gate. The original claim above is left in place, not deleted, because this
   document's purpose is cross-checking sources; treat this item's "Action" sentence as refuted for this
   repo. **Two other passages actually restate the refuted claim** and are corrected by this note: the
   **"Bottom line up front" summary** at the top (the most prominent, and the one a skimmer hits first) and
   **Section 7 item 3**. Two further passages are about reconvergence as *topology* and never assert that
   endings arise from reconvergent leaves, so they are not restatements and carry a pointer only for
   context: Section 7 item 5 (a general topology guideline) and the Section 8 "Reconvergence rate" bullet
   (the unresolved per-tier rate, and the decision to leave `reconvergence_ceiling` unset).
4. **Reading level tracks age, not branch complexity; education lines are hi-lo** (R1, R2, R3). R3's rule:
   "branch density can increase before sentence difficulty needs to increase," and "prose grade and graph
   complexity should not scale in lockstep." Lexile national bands for reference: grade 1 ~190-530L, grades
   2-3 ~420-820L, grades 4-5 ~740-1010L, grades 6-8 ~925-1185L. Title anchors: core CYOA ~500-710L; Give
   Yourself Goosebumps ~480-490L; You Choose 590-720L; Dragonlarks ~480-570L / GRL L-O. **Action:** set the
   Flesch-Kincaid / Lexile gate by age band independently of graph size; move age up via premise, tone, and
   ending harshness before branch depth.
5. **Edition-family anchoring (new from R3).** The same title is a different production object across
   editions: *Your Very Own Robot* is 80pp / 9 endings in modern Chooseco metadata but 52-54pp / 12 endings
   in historical references. **Action:** calibrate against the specific edition family you want to emulate
   (modern Chooseco reissue vs vintage Bantam), not the title label. This also means published structural
   numbers should be tagged with their edition before they enter any config.

A useful vocabulary the team may want (R1, via Sam Kabo Ashwell): **Time Cave** (early CYOA: max branching,
many endings), **Gauntlet** (one anointed path; Fighting Fantasy, Time Machine), **Branch-and-Bottleneck**
(reconvergent; Lone Wolf, 10-13 lines), plus Sorting Hat / Open Map / Quest / Loop-and-Grow. Naming the target
topology per tier removes ambiguity from the spec.

## 6. Corrected master matrix by age band

Reconciled across all four sources. "Decisions/path" and "longest path (nodes)" are listed separately to
prevent the Section 4.1 error. Measured anchors are noted.

| Band | Total words | Nodes | Endings | Choices/decision | Decisions/path | Reading level | Topology | State | Fail-state |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5-8 early | ~3k-5.5k | **~42-46** (UCSB-measured) | 9-12 | 2 | ~3-6 | ~480-570L / GRL L-O | pure/near-pure tree | none | **no death; loops, comic** |
| 8-11 core | ~8k-15k | **~90-120** (JHM + UCSB) | ~20 (11-42); declining | 2-3; rare hubs 5-12 | ~4-5 (max ~7) | ~500-710L | tree-dominant, light reconvergence | none | failure/entrapment, adventure-forward |
| 10-13 | ~9k-16k | ~110-180 (many page-turn, fewer mapped) | ~19-28 branching; 1 for guided sim (Time Machine) | 2-3 | ~5-10 | ~490-720L | branch-and-bottleneck | light (item/flag/databank) | horror variety; logical |
| 13-16 | ~16k-32k | 350-456 sections | 1 win + many fails (e.g. City of Thieves: 10 instant deaths) | 2-3; many forced continuations | ~12-25 section hops | ~middle-grade prose, but mechanics raise fit | gauntlet / B&B | full (stats, inventory, dice, combat) | resource-based, lethal |

Confidence by row: 5-8 now Medium-High (UCSB-measured node counts); 8-11 High (two measured sources); 10-13
Medium (mix of measured and page-turn metadata); 13-16 Medium (publisher/archival, no graph-theory anchor,
and gamebooks are a different product class).

## 7. Net deltas to the project parameters (vs the JHM-only handoff)

**Read the status notes before acting on any item here.** Sections 2 through 6 record what the sources say
and age well. This section does not: it is six claims about *this repository* and six instructions to the
team, written 2026-06-23 against the generator as it stood before ADR-011. Four of the six now describe a
codebase that no longer exists, and following them as written would mean re-deciding settled questions or
building gates that already exist. Each item keeps its original text, with a dated status note appended, so
that the 2026-06-23 recommendation and its actual outcome both stay legible.

1. **Depth budgets: unchanged and confirmed correct, now triangulated three ways.** Ignore R2's inflated
   "decisions" figures. Do not lengthen paths.

   **Status (2026-08-03): the recommendation stands, its stated basis does not.** "Do not lengthen paths"
   is still right. But the budget this item claims to confirm is enforced in hops rather than decisions, the
   6 / 8 / 10 values are a band-level fallback superseded by `_PRODUCTION_CELLS` for every offered cell, and
   `band_profile.py` states the number is not research-derived. Full correction in the Section 4.1 status
   note.
2. **Reconsider node word-size (stronger now).** The genre beat is ~100-150 words, not 250; the orchestrator's
   250-word node is roughly **1.7-2.5x the genre's readable beat**, spacing choices much further apart than
   classic CYOA. Decide deliberately: keep 250 (fewer, longer, richer beats, a modern-prose choice) or move
   toward ~150 (genre-faithful flip-and-choose cadence). This interacts with endings: smaller nodes at the
   same word budget yield more nodes, hence room for more leaves.

   **Status (2026-08-03): decided, past both options this item offered.** There is no 250-word node;
   `generation/prompts.py` contains no such constant, and reads its budget from
   `band_profile.words_per_node_profile`. `_WORDS_PER_NODE` (recorded in ADR-011 section 3) sets 8-11 and
   10-13 prose to `(mean 100, advisory 70-135, per-node max 220)`, enforced by PL-19: the per-node wall as a
   blocking ERROR on every story, the story mean as a WARNING on scale-classified stories. The choice posed
   here, keep 250 or move toward ~150, resolved past both to a mean of 100, at the low end of the ~100-150
   band Section 3 reconciled.
3. **Endings floor remains the key recommendation, now quadruple-confirmed.** All four sources agree endings
   are a defining, commercially-valued property achieved through many shallow reconvergent leaves, exactly
   what the genre traded away over time under the pressure your yield loop faces. Confirm whether any
   validator layer gates ending count; if not, add a floor, and prefer "more short leaves" over "deeper tree"
   when raising it. **See the Section 5 item 3 correction (2026-08-03):** the "reconvergent leaves" mechanism
   is refuted for this repo's corpus; raise the floor by breadth off single-parent endings, per ADR-011
   section 7.

   **Status (2026-08-03): landed; the confirmation this item asks for is done.** A validator layer does gate
   ending count. PL-17 (`validator/policy.py`) checks endings and decision nodes against
   `BandProfile.min_endings` and `min_decisions`, breadth-scaled for larger stories, as a blocking ERROR.
   The floors run from 2 endings / 1 decision at 3-5 to 3 / 3 from 8-11 upward. Do not re-open this as an
   open question; raising the floors is a tuning decision, not a missing gate.
4. **Add exposure ratio to the cost model and an age-gated no-death rule for the 5-8 tier.** Neither exists in
   the current validator/budget design.

   **Status (2026-08-03): half landed, and the open half is the only still-actionable item in this
   section.** The no-death rule exists: `forbidden_ending_kinds` is `{DEATH, CAPTURE}` for both 3-5 and 5-8
   (and `{DEATH}` for 8-11), enforced by PL-15. **Exposure ratio is still absent** from the cost model, and
   remains genuinely open as written.
5. **Introduce more reconvergence at 10-13+, keep 8-11 tree-dominant.** Per the Section 5 item 3 correction,
   this is a general topology guideline, not an endings mechanism; see ADR-011 section 7.
6. **Tag any imported structural number with its edition family** (R3's caveat); modern Chooseco and vintage
   Bantam are not interchangeable.

## 8. Conflicts and gaps left open (flag for the team)

- **Total word count (~8k vs ~30k).** Narrowed to ~8-15k here, but it rests on the unmeasured words-per-node
  figure; no source measured vintage CYOA word counts. If precise budgeting matters, measure 3-5 sample
  titles directly against the edition you intend to emulate.
- **Reconvergence rate.** JHM (measured, 40 books) says tree-dominant with shallow merges (max indegree 1.5);
  R3 emphasizes "meaningful reconvergence" from a few UCSB samples. Reconciled to "tree-dominant, light and
  rising with age," but the exact per-tier reconvergence target is not pinned down. This gap is now closed
  for this repo by ADR-011 section 7: no per-band magnitude gate is set (`BandProfile.reconvergence_ceiling`
  stays `None`); see the Section 5 item 3 correction (2026-08-03).
- **Choice-spike outliers.** R3 documents a 12-choice node in *Who Killed Harlowe Thrombey?*, above JHM's
  measured max outdegree of 4. Likely a mystery-hub pattern in titles outside JHM's sample. Treat 5-12-choice
  hubs as a rare, premise-specific pattern, not a default.
- **5-8 and 13-16 fine detail.** The 5-8 node counts are now UCSB-measured, but endings/word counts remain
  estimates; the 13-16 band has no graph-theory anchor and is a different product class.
- **Per-title figures from UCSB / sboyles.github.io** are verified for the sampled edition/encoding only, not
  guaranteed universal across reprints.

## 9. Sources

- JHM paper: Adams, D., Beckelhymer, D., & Marr, A. (2019). DOI 10.5642/jhummath.201902.05.
  <https://scholarship.claremont.edu/jhm/vol9/iss2/5>
- R1: commissioned deep-research report, local artifact only:
  `tmp/compass_artifact_wf-7721d44d-abcd-4de7-8cb2-d99406f9eba5_text_markdown.md`
- R2: commissioned deep-research report, local artifact only: `tmp/CYOA Gamebook Structural Analysis.md`
- R3: commissioned deep-research report, local artifact only: `tmp/deep-research-report (7).md`. Cites two
  sources that ARE retrievable: UCSB Transverse Reading Gallery graph logs, and S. Boyles's CYOA statistics
  (<https://sboyles.github.io/cyoa/cyoa.html>).
- Companion handoff (JHM data, unmodified): `commercial-cyoa-graph-theory-handoff.md`. **Not a resolvable
  path.** As the note under the title says, that file was never committed here and no copy exists in git
  history; the reference names the document, it does not link to one.

**Retrievability of R1, R2, and R3 (read before citing any of them).** All three are commissioned
deliverables that exist only as local files under `tmp/`, which is gitignored. Those paths resolve on no
clone but the machine that ran the research, and none of the three carries a URL or DOI, so they cannot be
re-fetched or independently re-examined. This directory's standing rule that every claim carry a source with
URL or DOI is therefore **unmet for R1-R3 by construction**, and cannot be met retroactively. That gap is
the reason the Section 2 evidence tiers exist and the reason the "measured sources win over estimate-based
reports" rule is applied throughout. Treat any figure sourced only to R1, R2, or R3 as unverifiable
secondary synthesis; a figure traceable to JHM or to Boyles/UCSB is not affected.
