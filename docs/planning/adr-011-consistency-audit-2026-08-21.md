# ADR-011 internal-consistency audit (UW-C323)

**Date**: 2026-08-21
**Commissioned by**: owner ruling 9.1 (`live-structural-round-2026-08-21.md` section 9.1)
**Status**: complete; awaiting the owner's ruling on the amendment set in part (c)
**Method**: read-only pass over ADR-011
(`docs/planning/adr/adr-011-story-scale-framework.md`), its reconciliation sources
(`docs/planning/research/cyoa-research-reconciliation.md`, ADR-026), the validator constants
(`validator/band_profile.py`, `validator/policy.py`), and the committed catalog (84 main
skeleton files, 81 production-eligible). "Decisions per path" counts decision nodes
(outdegree >= 2) on a start-to-ending path; min is the fewest on any path to a
positive-valence ending, max the most on any path to any terminal (acyclic graphs only).
Structural counts ignore choice conditions, so min-path figures are lower bounds on the
condition-aware walk.

The finding in one line: section 6's "4-8 decisions per path" is arithmetically
unsatisfiable in 10 of 18 production cells given the ADR's own sections 3, 5 and 10; the
catalog violates it in both directions; and the validator's PL-17 breadth floor
mathematically FORCES gauntlet skeletons to break it.

## (a) Inconsistencies

### 1. Section 6's "4-8 decisions per path" is arithmetically unsatisfiable in 10 of 18 production cells (vs sections 3, 5, 10)

Quotes: section 6 "Decisions per path ~4-8 (length adds breadth, not depth; do not
inflate)"; section 5 `min->complete` column; section 3 words/node means; section 10
words-per-stop column plus "every stop ends in a choice" with "max choiceless stops in a
row 0-1" at 8-11 and up; section 10 closing "Decisions per path stay ~4-8".

Arithmetic: the shortest satisfying path must carry `min->complete x mean-words/node` words
(confirmed by section 5's own fastest-finish column, e.g. 16+ Long prose 23 x 175 = 4,025
words / 220 wpm = 18.3 min = "~18 min"). At 8-11 and up every stop ends in a choice and is
capped by the words-per-stop column, so the path needs at least
`ceil(path_words / stop_max)` stops, hence `stops - 1` decisions. Implied minimum decisions
on the SHORTEST path:

| Cell | min->complete | path words | stop max | implied min decisions | vs 4-8 |
|---|---:|---:|---:|---:|---|
| 8-11 Long prose | 14 | 1,400 | 135 | >= 10 | breaks ceiling |
| 10-13 Medium prose | 14 | 1,400 | 150 | >= 9 | breaks |
| 10-13 Long prose | 17 | 1,700 | 150 | >= 11 | breaks |
| 13-16 Medium prose | 15 | 2,100 | 200 | >= 10 | breaks |
| 13-16 Long prose | 20 | 2,800 | 200 | >= 13 | breaks |
| 13-16 Long gamebook | 32 | 2,080 | 200 | >= 10 | breaks |
| 16+ Medium prose | 18 | 3,150 | 230 | >= 13 | breaks |
| 16+ Medium gamebook | 29 | 2,320 | 230 | >= 10 | breaks |
| 16+ Long prose | 23 | 4,025 | 230 | >= 17 | breaks |
| 16+ Long gamebook | 37 | 2,960 | 230 | >= 12 | breaks |

These are floors on the FASTEST finish; typical paths (arc ceiling 2.5x,
`band_profile.py::ARC_CEILING_MULTIPLE`) sit far higher. Conversely, honoring 4-8 decisions
forces the min path into <= 9 stops averaging 450-800 words each at 16+, roughly 2-3.5x the
section 10 cap. Section 10's claim "Relationship to the locked constants of section 6:
unchanged" is therefore false for these cells: the grammar and the constant cannot both
hold.

Judgment: the envelopes are the design intent (section 2 makes words primary; every derived
column in section 5 checks out arithmetically against section 3 and the pace anchors, so
that machinery is the load-bearing part). The flat 4-8 constant is the drafting error: a
JHM anchor for ~90-120-node middle-grade books declared "research-locked, all cells" up to
750 nodes. The reconciliation (`cyoa-research-reconciliation.md` section 4.1) even warns
"Path length in nodes and decisions per path are different metrics"; ADR-011 scaled path
length in nodes (min->complete 6 to 37) while pinning decisions, which is exactly that
conflation in reverse.

### 2. Section 6 vs section 5's gamebook cells and section 7's gauntlet definition (flatly unsatisfiable)

Quotes: section 7 gauntlet = "linear spine, branch-to-fail, terminal (many),
restart-on-fail"; section 5 preamble "Gamebook endings are 'few wins + many fails' (~25-35%
of nodes are terminals)"; section 6 "~4-8", choices per decision "2-3".

Arithmetic: in a gauntlet, all decisions lie on the one spine, so decisions-per-path equals
total decisions. With <= 8 decisions and <= 3 options, off-spine fail branches number
<= 8 x 2 = 16, so terminals <= 17. Section 5's 13-16 Long gamebook cell claims 370-585
nodes at ~25-35% terminals, i.e. 92-205 terminals. 17 is nowhere near 92. Further, spending
370+ nodes across <= 16 fail branches means ~21+ nodes per fail tail, contradicting
"Fail-fast is allowed" (section 4) and gauntlet's "master the one path" reread driver. The
four gamebook cells cannot satisfy section 6 under any topology the band table permits
them.

Judgment: the gamebook cells are intent (the ADR's Consequences explicitly claims it
reproduces "the measured Fighting Fantasy node counts"; FF playthroughs carry dozens of
choices). The error is applying the prose-genre decision constant to the gamebook style at
all.

### 3. The 4-decision FLOOR is unsatisfiable at 3-5 Short (vs sections 5, 6's own setup constant, 7, and 10)

Arithmetic, three independent ways for 3-5 Short (min->complete = 6):

- Structure: 6 path nodes minus setup "~2-3 nodes" (section 6) minus 1 terminal leaves at
  most 3 decision slots. 3 < 4.
- Endings: 4 decisions x 2 options ("Options per choice: 2", section 10) with "minimal"
  reconvergence (section 7 band table) implies >= 5 terminals, above the cell's endings cap
  of 4.
- Cadence: section 10's "choice every 2nd-4th page" caps a 6-page path at ~2-3 choices.

3-5 Medium (min->complete 7, cap 6 endings) passes only degenerately (exactly 4 decisions,
zero linear nodes after setup, and the cadence still forbids it).

Judgment: the cell and grammar are intent; the floor of 4 is the drafting error at 3-5 (the
validator agrees: `band_profile.py` PL-17 sets `min_decisions=1` for 3-5).

### 4. Section 5 endings columns vs section 6's "prose ~15-22%" (both corners break)

Arithmetic at cell corners: floor side, 0.15 x 340 = 51 > 48 (10-13 Long ceiling);
0.15 x 220 = 33 > 32 (10-13 Medium); 0.15 x 45 = 7 > 6 (3-5 Medium); 0.15 x 23 = 4 = 4
(3-5 Short, degenerate). Ceiling side, 28/240 = 11.7% (8-11 Long) and 32/340 = 9.4%
(10-13 Long) fall below 15%. So a story at the top of its own node envelope cannot satisfy
both section 5 and section 6. This inversion is already documented and patched in code
(`band_profile.py::_CELL_ENDING_BOUNDS`, "This exists because section 5 and section 6
disagree and PL-17 implemented only section 6", `UW-C283`) but the ADR text was never
amended.

Judgment: section 5's columns are intent (the validator now caps by them); section 6's
15-22% should be demoted to a descriptive central tendency, not a per-cell constraint.

### 5. Section 5's "~25-35% of nodes are terminals" (gamebook) contradicts the 2026-08-18 owner ruling and the post-ruling catalog

`band_profile.py::_ENDINGS_FRACTION` records: "The gamebook fraction was 0.25 until
2026-08-18, implementing ADR-011 section 5's ASSERTION ... RULED 2026-08-18 (owner): 0.12
... 0.25 sitting ABOVE the prose fraction had the genre relationship backwards." Five
post-ruling gamebooks ship at 13.0-15.8% terminals (part b). The ADR text still asserts
25-35%.

Judgment: the ruling is intent; the ADR sentence is stale prose.

### 6. Section 10's options-per-choice (3-4) contradicts section 6's locked 2-3 while claiming section 6 is "unchanged"

Section 6: "choices per decision 2-3" (reaffirmed in the section 7 clarification). Section
10 table: "Options per choice" = 3 at 8-11/10-13 and 3-4 at 13-16/16+, followed by
"Relationship to the locked constants of section 6: unchanged." 4 > 3; the no-change claim
is false, and 8-11/10-13's fixed "3" also excludes the 2-option decisions section 6
permits.

Judgment: section 10 is the later, owner-ratified decision (D15, 2026-08-01); fix section 6
to "2-4 per the section 10 band column" and delete or re-scope the "unchanged" claim.

### 7. Section 3 per-node hard maxima exceed section 10's words-per-stop caps in every band

Section 10 says "the per-node ceilings of section 3 remain as authoring guardrails inside a
stop", but a stop can never contain a node at those ceilings: (per-node max vs stop max)
3-5: 90 vs 40; 5-8: 155 vs 70; 8-11: 220 vs 135; 10-13: 220 vs 150; 13-16 prose: 310 vs
200; 16+ prose: 385 vs 230. Worse at the page bands (where, per ADR-026, one stop = one
node): the page cap equals the section 3 MEAN exactly (40/40, 70/70), so the mandated story
mean is achievable only if every page sits at the cap, and the advisory band's upper half
(41-55, 71-95) is unusable. At flowed bands the means allow only ~1.3 mean-sized nodes per
stop, making the "flowed multi-node passage" of ADR-026 the exception rather than the
design case.

Judgment: neither table is obviously wrong alone; the missing piece is a precedence rule.
Intent (per ADR-026's framing of stops as FELT page size) is that stop sizes are soft
targets and the section 3 per-node max is the hard gate; the ADR must say so, and the
3-5/5-8 page caps should be raised to the section 3 advisory maxima (55, 95) or the
advisory bands narrowed, one or the other.

### 8. Section 1a (MVP tier) vs section 6's "all cells"

Section 6 is headed "Constants (research-locked, all cells)"; section 1a sets MVP
min-to-complete ~4 nodes and waives only the section 4 arc floor. A 4-node path cannot hold
4 decisions plus 2-3 setup nodes plus a terminal. The three MVP seeds (11/25/32 nodes)
cannot and do not comply. Minor: needs one scoping sentence.

### 9. Root cause: provenance overreach (section 9 vs sections 5-6)

Section 9 itself grades only 8-11 as high-confidence and calls 3-5/16+ "product-defined";
the reconciliation pins the measured figure at "~4-5 average, ~7 longest" for ~90-120-node
books. Declaring 4-8 "research-locked" across cells whose min-to-complete runs 6 to 37
nodes extended a local measurement far outside its support. Not a numeric contradiction on
its own, but it explains why items 1-3 exist.

Also noted in passing: section 5 silently omits Short rows for 13-16 and 16+ (section 1
states a cap only for young bands); worth one explanatory sentence.

## (b) Catalog-reality check (81 production skeletons)

- **The 4-8 window is violated in both directions, massively.** Of 60 acyclic production
  skeletons, 43 exceed 8 max decisions per path (range 2-67; gamebooks 19-67). 16 of 81
  have a fastest satisfying path with fewer than 4 decisions (as low as 2). Even in the
  measured 8-11 band, `the-tin-whistle-map.json` (8-11 Long) runs 11-15 decisions per path.
  Every `sorting_hat` skeleton sits at 2-8 (`the-cinderwick-exchange` has NO path above 3
  decisions, breaking the floor on every path), which is structural: section 7 prices
  sorting_hat as "sort + N x (track arc)", node-heavy and decision-light. Every large
  `branch_and_bottleneck`/`gauntlet` breaks the ceiling; e.g. `the-observatory-shift`
  (10-13 Medium) 21, `the-ashfall-expedition` (16+ Long gamebook) 43.
- **Nothing enforces the window.** PL-17 (`validator/policy.py`) gates TOTAL decision-node
  floors (band minima 1-4 plus `_DECISIONS_FRACTION = 0.08 x N`), never per-path counts;
  the only depth budgets (`max_depth`, 15-93) are hop counts. Sharper: for gauntlet
  topology, total decisions = per-path decisions, so the validator's own 0.08 floor (e.g.
  >= 51 at a 632-node gauntlet like `the-last-cartage`) REQUIRES breaking section 6. An
  enforced rule derived from ADR-011 forces violation of ADR-011's constant.
- **Endings envelopes:** 7 skeletons exceed their cell's endings ceiling (5 of them at 3-5,
  e.g. `the-big-cardboard-box` 18 vs cap 6, including `the-last-blue-cup`, which
  `band_profile.py` notes was authored to the strict bar, evidence the young-band columns
  are miscalibrated, not the books); `the-mapmakers-island` (10-13 Long) has 72 endings vs
  cap 48 (32% of nodes, also above section 6's 22%); `the-clockwork-menagerie` sits one
  below the 8-11 Long floor (27 vs 28).
- **Prose ending share vs section 6's 15-22%:** 0 of 62 prose skeletons fall below 15%; 15
  sit above 22% (the whole 3-5 shelf runs 29-41%).
- **Gamebook terminal share:** 14 older gamebooks at 27.6-33.3% (matching the deprecated
  25-35% text), 5 newer at 13.0-15.8% (matching the ruled 0.12 floor). The catalog now
  straddles two regimes; the ADR text describes only the abandoned one.
- **min-to-complete floors:** 10 skeletons have a structural shortest satisfying path below
  their cell floor (e.g. `the-longwinter-station` 9 vs 23; `the-hollow-sea` 9 vs 20;
  `the-winter-of-the-wolf-queen` 11 vs 17), all loop-bearing `open_map`/hub shapes. Caveat:
  computed ignoring choice conditions; a condition-aware walk may lengthen these, so treat
  as candidates, not verdicts.

## (c) Recommended amendments

Fix the constant:

1. **Section 6, decisions per path:** replace the flat "~4-8, all cells" with a derived
   per-cell window, anchored the way everything else in the ADR is anchored:
   decisions-per-path on the fastest finish ~ `ceil(min->complete_words / words-per-stop) - 1`
   (lower edge), with an upper edge tied to the arc-ceiling multiple (~2.5x) rather than a
   universal 8. Keep the true invariant explicit: decisions grow with min-to-complete, not
   with total nodes ("length adds breadth, not depth", formalized). Retain "~4-8" only as
   the historical JHM anchor for the 8-11/10-13 Short prose region it was measured in.
2. **Gamebook cells:** exempt from any single-digit window; state decisions-per-path there
   as spine-scale (catalog-measured 12-43 min, 19-67 max) and let the PL-17 breadth floor
   (0.08 x N) be the cited quantity, noting that for gauntlet total = per-path by
   construction.
3. **3-5 floor:** lower the per-path decision floor to match `band_profile`'s
   `min_decisions` (1 at 3-5, 2 at 5-8), which is what is actually enforced and what the
   cells' arithmetic permits.
4. **Young-band endings columns (section 5):** recalibrate the 3-5/5-8 ceilings upward
   against the committed strict-bar skeletons (currently 29-41% shares vs caps implying
   ~17-20%); section 9 already licenses this ("product-defined ... tunable").
5. **Section 5 gamebook preamble:** replace "~25-35% of nodes are terminals" with the ruled
   >= 12% floor (2026-08-18 ruling, `UW-C291` / `gamebook-thresholds-options.md`), noting
   the two shipped regimes.

Fix the prose:

6. **Section 6 endings fraction:** demote "prose ~15-22%" to a corpus-level descriptive
   figure and state that the section 5 per-cell columns govern (matching the shipped
   `_CELL_ENDING_BOUNDS` cap, `UW-C283`); acknowledge the corner inversions it caused.
7. **Section 10 closing paragraph:** delete or re-scope "Relationship to the locked
   constants of section 6: unchanged"; amend section 6's choices-per-decision to "2-4, per
   the section 10 band column".
8. **Sections 3 vs 10 precedence:** add one rule: the section 3 per-node max is the hard
   gate; words-per-stop is the advisory felt-page target a stop should usually meet and a
   single large node may exceed. At the page bands, raise the words-per-stop upper bounds
   to the section 3 advisory maxima (3-5: 40 -> 55; 5-8: 70 -> 95) so the required story
   mean is not pinned to the cap.
9. **Section 1a:** extend the waiver sentence so MVP shells are exempt from the section 6
   decision floor as well as the section 4 arc floor.
10. **Section 5:** one sentence stating why 13-16/16+ have no Short tier (or add the rows
    deliberately).
