---
schema_type: planning
title: "Research Notes: CYOA Structure Taxonomy and Published-Book Measurements"
description: "Committed, citable structural research base for ADR-011: the Ashwell pattern taxonomy as
  actually published, the verified JHM 2019 graph-theory study behind ADR-011's headline constants,
  Swinehart's One Book Many Readings, gamebook digraph measurements including an original Lone Wolf
  measurement, and the word-count evidence. Rebuilt 2026-08-02 to replace the never-committed
  docs/planning/research/ originals."
tags:
  - planning
  - research
  - storybook
status: active
owner: core-maintainer
authors:
  - name: "Claude (research rebuild, branch claude/story-structure-diversity-ba8swy)"
purpose: "Make every structural constant in ADR-011 traceable to a primary source or explicitly labeled
  as a designer prior, and record the taxonomy mapping between Ashwell's published patterns and the
  project's Topology enum."
component: Strategy
source: "External research pass, 2026-08-02. All URLs accessed 2026-08-02. Evidence tags: MEASURED
  (taken from a fetched source or computed from fetched primary text), REPORTED (secondhand),
  UNVERIFIABLE (not traceable to a primary source)."
---

# Research Notes: CYOA Structure Taxonomy and Published-Book Measurements

Companion note: [choice-agency-pacing-and-failure.md](choice-agency-pacing-and-failure.md) covers the
human side (agency, pacing, reading rates, fail states). See the README for provenance.

## 1. The Ashwell taxonomy, as actually published (MEASURED)

Sam Kabo Ashwell, "Standard Patterns in Choice-Based Games," *These Heterogenous Tasks*, 2015-01-26:
<https://heterogenoustasks.wordpress.com/2015/01/26/standard-patterns-in-choice-based-games/>.
Framed as "a non-exhaustive look" derived from his 2011-2012 per-book "CYOA Structures" analyses; the
patterns "aren't discrete categories."

Ashwell defines **eight named patterns plus three variant groups** (deadly/friendly gauntlets,
invisible bottlenecks, spoke-and-hub), not six patterns:

1. **Time Cave**: heavily branching, choices of roughly equal significance, little or no re-merging,
   no state, "many, many endings"; short playthroughs, broad rather than long, strong replay.
2. **Gauntlet**: long rather than broad; a relatively linear central thread pruned by branches ending
   in death, backtracking, or quick rejoining; one "anointed story"; rarely state-dependent.
   Variants: **deadly** (prunes with failure) vs **friendly** (prunes with short-range rejoins,
   dominant in the Twine era). "Perhaps the easiest structure to author."
3. **Branch and Bottleneck**: branches regularly rejoin around events common to all versions, almost
   always with heavy state-tracking ("if a game doesn't do this, chances are you are dealing with a
   gauntlet"); reflects character growth; "has to be used in a fairly large piece." Variant:
   **invisible bottlenecks**.
4. **Quest**: distinct branches rejoining toward a small number of winning endings (often one);
   modular geography-organized clusters; needs state; "the minimal size for a quest is relatively
   large." Examples: Fighting Fantasy, Lone Wolf, 80 Days.
5. **Open Map**: reversible travel over static geography; state drives progress; slower-paced,
   parser-IF-like.
6. **Sorting Hat**: the early game branches AND rejoins heavily, then assigns the reader to one of a
   few largely linear major branches; state-tracked early; "the author may end up effectively having
   to write several different games."
7. **Floating Modules**: no tree, no central plot; modules unlocked by state; computer-only; collapses
   into linearity without a large content mass; ties to quality-based narrative and storylets.
8. **Loop and Grow**: a central thread looping to the same point with state unlocking new options.
   Variant: **Spoke and Hub** (branches all originating from and returning to a central node).

Academic corroboration: Millard, "Strange Patterns" (University of Southampton eprint,
<https://eprints.soton.ac.uk/458014/1/Strange_Patterns.pdf>) treats Ashwell as the canonical
eight-pattern macro taxonomy; Analog Game Studies' gamebook framework (2023,
<https://analoggamestudies.org/2023/09/studying-gamebooks-a-framework-for-analysis/>) quotes the
quest/map definitions when analyzing gamebooks.

### Mapping to the project's `Topology` enum (record of deltas)

| Ashwell | Project | Delta |
| --- | --- | --- |
| time_cave, gauntlet, branch_and_bottleneck, open_map, sorting_hat, loop_and_grow | same | kept |
| quest | folded into `branch_and_bottleneck` | Loses Ashwell's distinguishing axes: quest is geography-organized modular clusters with few winning endings and a large size floor; B and B is time-organized character growth. Worth a comment where quest-like skeletons are matched. |
| floating_modules | deferred | Consistent with Ashwell's own warning (needs large content mass). |
| spoke_and_hub (variant) | implicit under `loop_and_grow` | Faithful (it is an Ashwell variant), but unrecorded in code. |
| deadly vs friendly gauntlet (variants) | not encoded | This is exactly the axis the age-gated fail-state policy moves along; naming it would let the policy cite the taxonomy. |

One divergence to keep honest: the project formalizes `sorting_hat` as never-reconverging parallel
tracks; Ashwell's sorting hat *rejoins heavily in the early game* before assigning a track. The
stricter formalization is fine but should not be attributed to Ashwell verbatim.

## 2. JHM 2019: found, verified (MEASURED, full PDF read)

ADR-011's "JHM 2019" is the *Journal of Humanistic Mathematics*:

> D'Andre Adams, Daniela Beckelhymer and Alison Marr, "Choose Your Own Adventure: An Analysis of
> Interactive Gamebooks Using Graph Theory," *Journal of Humanistic Mathematics* 9(2), July 2019,
> pp. 44-59. DOI 10.5642/jhummath.201902.05. Open access:
> <https://scholarship.claremont.edu/jhm/vol9/iss2/5>. Companion digraph collection (all 40 book
> graphs): <https://www.alisonmarr.com/cyoa.html>.

Method: 40 books (Chooseco's "Whole Enchilada" boxed set, explicitly ages 9-12) hand-converted to
digraphs (nodes = pages, arcs = commands); 24 structural properties computed.

Verification of ADR-011's quoted constants against the paper's Table 4:

| ADR-011 claim | Paper | Verdict |
| --- | --- | --- |
| ~90-120 page-nodes | Text pages: 88 / Q1 94 / median 98 / Q3 103 / max 115 (mean 99.6). Total pages incl. art: 108-137 (mean 121) | Supported (fair gloss) |
| median ~20 endings (11-42) | Endings: min 11, median 20, max 42, mean 21.18 | Supported, exact |
| essentially a tree (max indegree 1.5) | Mean of per-book max indegree 1.50 (median 1, max 3); over 50% of books acyclic; majority tree-structured | Supported (1.5 is the mean of per-book maxima) |
| ~5 decisions/playthrough (7-8 longest) | Not stated. Derivable: avg story 20.26 pages / 3.32 pages between decisions = ~6.1 typical; longest ~8.3. Bratton's single-book dissection: avg 4.68, range 2-6 | Approximately supported; flag as DERIVED, not stated |

Additional Table 4 values worth carrying: decision pages mean 20.43 (max 47); max outdegree mean 2.58
(max 4: choices are 2-3-way, occasionally 4); distinct paths mean 31.45 (median 20, max 202);
shortest story mean 11.8 pages; pages to first decision mean 5.98; pictures mean 21.35/book.

Trends over time (Table 6, pre-1998 subset, Pearson r): endings -.743, decision pages -.783, average
story length +.798, independently confirming Swinehart's endings-decline finding. Bonus: 5 of 40
books had wrong advertised ending counts on their covers; cover blurbs are not ground truth.

**Recommendation**: rewrite the ADR-011 reference to the full citation with DOI, and restate the
decisions-per-playthrough constant as "~5-6 typical, ~8 longest (derived from JHM Table 4; single-book
dissection 4.68)".

## 3. Swinehart, "One Book, Many Readings" (2009) (MEASURED)

Christian Swinehart, <https://samizdat.co/cyoa/>. Corpus: 12 gamebooks 1979-1986, each page
hand-classified (choice / linear / ending; endings graded catastrophic to great). Findings stated on
the page:

- A gradual decline in the number of endings across the series; later books favor a single "best"
  ending.
- A decline in the number of choices over time; late books have more linear pages than decisions and
  endings combined.
- Early books discouraged optimization: best endings distributed fairly evenly across branches, so
  early choices do not foreclose good outcomes. Single-ideal-ending design belonged to non-CYOA
  gamebooks (Time Machine, Zork books).
- Best endings cluster in the backmost pages; worst endings appear early and peak about two thirds
  through.
- *Inside UFO 54-40*'s "Ultima" ending has no inbound path (reachable only by breaking the
  page-turn rules), corroborated at <https://davidnunez.com/choose-your-own-adventure>.

No cross-book numeric summary is published there; Swinehart is the structural/qualitative source, JHM
2019 is the numeric one. The "many endings come from breadth, not depth" reconciliation finding is
supported by both.

## 4. Gamebook digraph measurements

- **Boyles, "Choose Your Own Analysis"** (<https://sboyles.github.io/cyoa/cyoa.html>, MEASURED):
  per-book stats for classic CYOA #1-23: endings 14-44; distinct acyclic paths 20 to 47,358 (the
  outlier has 7 cycles); longest paths 14-42 pages; average path 7.4-17.6 pages; most books 0-1
  cycles; a random-play "difficulty" score 1.18-3.34. Consistent with JHM 2019 where they overlap.
- **Lone Wolf #1, Flight from the Dark (Dever 1984), measured for this note** from Project Aon's
  licensed full text (<https://www.projectaon.org/en/xhtml/lw/01fftd/>, 350 sections crawled):
  350 nodes; outdegree distribution 0:17, 1:157, 2:135, 3:36, 4:5 (50% of sections offer a real
  choice, 2-4 way); **17 endings, 16 failures and 1 victory**; 29,624 words total, mean 84.6
  words/section (median 76, min 16, max 428). Matches Demian's Gamebook Web Page
  (<https://www.gamebooks.org/lonewolf.htm>, REPORTED).
- **Fighting Fantasy** (REPORTED): standard format 400 sections, single victory section; *The Warlock
  of Firetop Mountain* has only 3 instant-failure sections (not counting stat death). Full digraph
  fan extractions exist (Outspaced Shrine SVG flowcharts; announcement:
  <http://worldoffightingfantasy.blogspot.com/2013/11/fighting-fantasy-svgs.html>); current hosting
  unresolved from this environment, kept as a lead.
- **Bratton, "Dissecting a Choose Your Own Adventure Book"** (2017,
  <https://gregorybratton.wordpress.com/2017/01/13/dissecting-a-choose-your-own-adventure-book/>,
  MEASURED): CYOA #53, *The Case of the Silk King*: 115 pages, 19 endings; playthroughs 11-25 pages
  (avg 18.68); choices per playthrough 2-6 (avg 4.68); ~61% chance of a bad ending under random play;
  ~22% of the book is full-page illustration.

Quantified contrast worth keeping: CYOA is ~100 nodes with ~20 endings and ~5-6 decisions per read
(breadth); FF/LW are ~350-400 nodes with 1 victory and heavy fail density (length). That is Ashwell's
time-cave-vs-quest distinction in numbers, and it is the axis the app's prose-vs-gamebook style split
encodes.

## 5. Word counts (largely UNVERIFIABLE; measured bounds only)

- MEASURED: Lone Wolf #1 at 84.6 words/section mean (see above); JHM 2019 gives ~99.6 text pages and
  ~21 full-page illustrations per book but no word counts.
- MEASURED (negative result): Accelerated Reader and Lexile index no classic CYOA titles; the
  standard educational word-count databases do not cover branching books.
- REPORTED (weak): readinglength.com's ~28,750-word estimate for *The Cave of Time* is an explicit
  algorithmic guess (~250 words/page) that ignores large type and art density; treat as an upper
  bound, not data.
- Derived sanity check: 100-150 words per text page x ~100 text pages gives 10-15k words per book;
  a ~20-page playthrough gives 2-3k words per sitting.

**Implications for ADR-011**: "words/node ~100-150" and "total words ~8-15k at 8-11" are
UNVERIFIABLE from indexed sources; internally consistent with format arithmetic, bounded below by the
Lone Wolf measurement, but no primary source has counted words in a classic CYOA book. Either measure
2-3 physical copies (a short exercise) or keep both constants flagged as designer priors with the
derivation shown. The note should also separate *total content words* (~10-15k) from *words per
playthrough* (~2-3k); ADR-011's current phrasing conflates them.

## 6. Consolidated implications for ADR-011

| Constant / claim | Verdict |
| --- | --- |
| "Ashwell vocabulary" of six topologies | Supported with caveat: Ashwell defines 8 patterns + 3 variant groups; six is a deliberate subset (quest merged, floating_modules deferred, spoke-and-hub implicit). Record the mapping (section 1). |
| ~90-120 page-nodes | Supported (JHM Table 4). |
| Median ~20 endings (11-42) | Supported, exact (JHM Table 4). |
| Max indegree 1.5, essentially a tree | Supported (mean of per-book maxima; majority of books tree-structured). |
| ~5 decisions/playthrough (7-8 longest) | Approximately supported, but DERIVED (JHM does not state it); restate as ~5-6 typical, ~8 longest. |
| Choices per decision 2-3 | Supported (JHM max outdegree mean 2.58, max 4). |
| Endings from breadth, not depth | Supported (Swinehart + JHM trends). |
| Age-gated fail-state policy | Directionally supported (fail density varies by series/audience: Warlock 3 instant fails vs Lone Wolf 16/17 fail endings vs CYOA ~61% bad-ending random play); no source states an age gradient; remains a design inference. |
| Words/node ~100-150; total ~8-15k | Unverifiable; designer priors with a shown derivation; fix the total-vs-playthrough conflation. |

## Source list

1. Ashwell 2015, Standard Patterns in Choice-Based Games:
   <https://heterogenoustasks.wordpress.com/2015/01/26/standard-patterns-in-choice-based-games/>
2. Adams, Beckelhymer and Marr 2019, JHM 9(2):44-59, DOI 10.5642/jhummath.201902.05:
   <https://scholarship.claremont.edu/jhm/vol9/iss2/5>
3. Marr, CYOA digraph collection: <https://www.alisonmarr.com/cyoa.html>
4. Swinehart 2009, One Book Many Readings: <https://samizdat.co/cyoa/>
5. Boyles, Choose Your Own Analysis: <https://sboyles.github.io/cyoa/cyoa.html>
6. Bratton 2017, Dissecting a Choose Your Own Adventure Book:
   <https://gregorybratton.wordpress.com/2017/01/13/dissecting-a-choose-your-own-adventure-book/>
7. Project Aon, Flight from the Dark: <https://www.projectaon.org/en/xhtml/lw/01fftd/>
8. Demian's Gamebook Web Page, Lone Wolf: <https://www.gamebooks.org/lonewolf.htm>
9. Titannica, The Warlock of Firetop Mountain:
   <https://fightingfantasy.fandom.com/wiki/The_Warlock_of_Firetop_Mountain_(book)>
10. World of Fighting Fantasy, Fighting Fantasy SVGs:
    <http://worldoffightingfantasy.blogspot.com/2013/11/fighting-fantasy-svgs.html>
11. Wikipedia, Choose Your Own Adventure: <https://en.wikipedia.org/wiki/Choose_Your_Own_Adventure>
12. Millard, Strange Patterns: <https://eprints.soton.ac.uk/458014/1/Strange_Patterns.pdf>
13. Analog Game Studies 2023, Studying Gamebooks:
    <https://analoggamestudies.org/2023/09/studying-gamebooks-a-framework-for-analysis/>
14. davidnunez.com on UFO 54-40: <https://davidnunez.com/choose-your-own-adventure>
15. readinglength.com, The Cave of Time estimate: <https://www.readinglength.com/work/W1MTmXI>
16. Unretrieved leads, kept honestly: r/gamebooks deadliest-FF table and optimal-FF-walkthrough blog
    (unfetchable through the proxy); Outspaced Shrine current URL.
