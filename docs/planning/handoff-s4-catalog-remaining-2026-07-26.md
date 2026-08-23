---
purpose: What remains in slice S4 of the story-diversity work (A9 item 2, A20's 14 uncontracted skeletons), with the measurements already taken so the next session does not re-derive them
component: skeletons/, validator/theme_leak.py, scripts/parameterize_skeleton.py, docs/planning/story-diversity-plan-v2.md
source: PR #415 session 2026-07-26
---

# Handoff: S4 catalog work, what remains

Written 2026-07-26, at the close of the session that delivered A21, A9 item 1,
and the first two A20 slices. S4 is the one slice of the diversity plan that is
partially done. Everything left in it is **authoring**, not engineering, and no
decision from the owner is outstanding: the disposition question was settled
during this session (see A9 below).

Read alongside `story-diversity-plan-v2.md` (the A9 and A20 correction notes)
and `story-diversity-implementation-plan.md` section 3 (the slice table).

---

> **Catalog counts are dated.** Every skeleton, node and choice count below was measured on 2026-07-26,
> when the catalog held 61 skeletons; on 2026-08-23 it holds 84 skeletons and 15,470 nodes
> ([catalog census](./catalog-census.md), `UW-G24`). They are left as measured, because each one records
> what a procedure returned on that date rather than describing the catalog today.

## 1. State at handoff

| Item | State |
| --- | --- |
| A21 residual retired-theme leak scan | **Delivered.** Check landed, all 273 leaks drained, quarantine opened and emptied |
| A9 item 1, the 14 SR-9 findings | **Delivered.** One root cause, one node; series errors 14 -> 0 |
| A9 item 2, the structural twinning | **Open.** Spec below. Effort L |
| A20 theme-contract backfill | **47 of 61 skeletons contracted.** 14 remain, 4,305 FILL nodes |

Full suite at handoff: 5002 passed, 990 skipped, 0 failed, 0 xfailed.

---

## 2. A9 item 2: restructure `the-sunken-temple`'s shape

### What the defect actually is

Not what the plan originally said. "Clone pair" was wrong, and the correction
matters because it inverts the economics.

The **prose is genuinely distinct**: 1,326 of 1,503 slotted surfaces differ, the
two books declare different variables, and their `structure_fingerprint`s are
unequal. The **shape is a carbon copy**: every `structure_features` field is
identical (550 nodes, 152 endings, 801 choices, `max_depth` 58, same ending-kind
and valence histograms, `branch_and_bottleneck` both) except `n_effects`, and the
out-degree histograms are byte-identical
(`{0:152, 1:185, 2:114, 3:48, 4:25, 5:14, 6:10, 7:2}`) with 324 of 550 node ids
simply renamed (`a0_*` -> `g0_*`).

So book 2 is book 1's skeleton re-skinned. The writing is not the substandard
part; the design is. **Replacing book 2 would discard 1,326 distinct authored
surfaces to fix a problem that is not in them.** Restructure, do not replace.

### What was ruled out, and why

**Deletion cannot work. Proved exhaustively, not argued.** Every subset of up to
five prunable groups (`w0`-`w7`, `g1`-`g4`, 12 candidates) was simulated: zero
are simultaneously gate-clean and above `tau_cell` (0.05). The blocker is always
`PL-17`, whose ending floor scales at ~25% of node count while book 2 sits at
27.6% (152/550). Every removable group is ending-dense (`w3` is 62% endings, `w4`
58%, `w2` 46%), so pruning the bail-out fan undershoots the floor before it moves
the metric. Best case, dropping `w2,w3,w4,w6`: distance 0.0549 at 439 nodes, but
`PL-17` wants 110 endings and it has 94.

**Metric-gaming is rejected, and it is unusually tempting here.** The topology
classifier admits `{BRANCH_AND_BOTTLENECK, GAUNTLET}` for any reconverging
acyclic graph, so relabelling `metadata.topology` to `gauntlet` would pass PL-18
with **no rewiring at all** and jump the distance to 0.2, four times the floor.
Do not do this. It changes a field, not a book.

### The target, with numbers

Distance is `0.5 * numeric_canberra_mean + 0.3 * histogram + 0.2 * topology`.
Measured options:

| Change | Distance |
| --- | --- |
| Today | 0.00047 |
| Ending remix alone (35 `capture` -> `setback`) | 0.0350 |
| State layer alone (6 vars, 40 conditions, 120 effects) | 0.0601 |
| **5 vars, 20 conditions, 75 effects + 35-ending remix** | **0.0710** |

The combined row is the recommended target: 42% margin over the floor, and the
cheapest of the three in total authoring.

**`L2-12` is not a constraint.** Book 2 currently walks **3,668 configurations in
0.19s** against a 100,000 cap, and each added bool roughly doubles it (7,130 at
+1). Three more bools land near 29k.

### Why this session stopped, and the trap to avoid

The state layer is honest only if each gate and cost sits where the fiction
already supports it. A prose-grounded scan found 103 nodes with exertion language
and 77 candidate choices, but **three of the first eight candidates were false
positives**: `Push too hard when he hesitates` is social pressure, not physical
exertion. Placing 33 conditions and 72 effects by pattern match would produce
gates that pass every checker and mean nothing to a reader, which is
metric-gaming with extra steps.

Finishing this means reading book 2's **324-node spine** (`g0`-`g4`) and placing
each cost and gate deliberately. Budget a session for this book alone.

### Suggested design, if the narrative supports it on reading

Book 1 is an exploration of a keep; book 2 is a marsh expedition. Making `vigor`
genuinely load-bearing in book 2 (costs on hard crossings, gates on demanding
actions) is a real, felt difference and fits the fiction. The 35 ending
conversions are `capture` -> `setback`, turning "taken by the drowned choir" into
"driven back", which is also the right shape for a **non-final** book that must
hand off to book 3 (see SR-5 and SR-9). Verify each on reading; do not assume.

### Definition of done

1. `run_gate(the-sunken-temple).blocked is False`
2. `validate_series([book1, book2])` still reports **0** errors (do not regress A9 item 1)
3. `structural_distance` > 0.05 with margin, and
   `scripts/check_incell_clones.py --check` reports the pair no longer breaching
4. **Remove the allowlist entry** in `src/cyo_adventure/diversity/incell.py`.
   The stale-entry check will fail until you do, which is intentional
5. Configuration count under the `L2-12` cap
6. Derived artifacts regenerated (see section 4)
7. Full suite green

### The standing alternative

A16 forbids retiring book 2 alone, but not the whole chain. If the owner would
rather not spend a session restructuring what the plan calls a series
stress-test artifact, **retiring the entire `brass-lantern` series** closes A9
items 1 and 2 and removes 1,100 nodes from A20's remainder, at the cost of book
1's prose, which is not defective. This is the owner's call, not the next
session's.

---

## 3. A20: 14 skeletons, 4,305 FILL nodes

Scope was corrected this session: the plan estimated **M**, the measurement is
**4,341 nodes across 16 skeletons, every one with zero pre-existing `{SLOT}`
tokens**, so there is no partial migration anywhere. Two are delivered
(`the-lost-mitten` 11 nodes / 16 slots, `the-clocktower-cipher` 25 / 26).

The remainder splits sharply, and the halves want different treatment:

### Templated (5 skeletons, 2,090 nodes) - build a generator first

| Nodes | Skeleton | id-repeat |
| --- | --- | --- |
| 677 | `the-tenfold-siege` | 97% |
| 530 | `the-serpent-vaults` | 58% |
| 453 | `the-cinder-bazaar` | 87% |
| 277 | `the-iron-spire-trial` | 65% |
| 153 | `the-quiet-harbor-protocol` | 63% |

`the-tenfold-siege` is 677 nodes but **240 of them are one node family**
(`a#_g#_f#_c#`) and 120 another; 80% of its beats share a six-word opening. This
is why `the-pale-road` needs only 28 slots for ~1,000 nodes.

**Build a family-based plan generator** (engineering, ~half a session): group
nodes by id-family, derive one slotting plan per family, hand-check the families
rather than the nodes, then feed the result to the existing
`scripts/parameterize_skeleton.py`. This converts the larger half into a review
pass.

### Bespoke (9 skeletons, 2,215 nodes) - per-node authoring, no tool helps

| Nodes | Skeleton | id-repeat |
| --- | --- | --- |
| 550 | `the-sunken-temple` | 39% |
| 550 | `the-harrowstone-keep` | 39% |
| 250 | `the-winter-of-the-wolf-queen` | 4% |
| 248 | `the-longwinter-station` | 9% |
| 197 | `the-hollow-sea` | 12% |
| 155 | `the-flooded-quarter` | 0% |
| 128 | `the-undertow-season` | 0% |
| 105 | `the-glass-comet` | 5% |
| 32 | `the-sunken-signal` | 0% |

`the-flooded-quarter` has 155 beats across 155 distinct id-families and **0%
shared beat openings**: every node is one of a kind. Work smallest-first.

### Ordering dependency

`the-sunken-temple` and `the-harrowstone-keep` are **1,100 of the 4,305 nodes
AND they are A9's pair**. Restructuring book 2 changes its slot surfaces, so
contracting them first risks rework. **Do A9 item 2 first, or skip those two
until it lands** - which also removes the two largest bespoke trees, leaving
1,115 bespoke nodes.

---

## 4. Per-skeleton definition of done

Settled over the two slices delivered this session. Steps 5-7 are where this
session got caught three times; they are not optional.

1. **Author the slotting plan.** Two conventions, both learned the hard way:
   - The **article lives inside the slot value** (`THRESHOLD` = "the old town
     clocktower"), matching all 47 existing contracts. That makes a
     sentence-initial slot a defect, because the rendered beat opens lowercase.
     Four of `the-clocktower-cipher`'s beats did on the first pass. Verify with a
     zero-count check over rendered surfaces, not by eye.
   - A **theme-bearing ending title gets its own `ENDING`-scope `*_TITLE` slot**,
     not an inline token: `The {CIPHER} Revealed` renders as "The cipher
     Revealed". Generic titles stay literal, though the script still requires a
     `titles` entry for every ending.
2. `uv run python scripts/parameterize_skeleton.py <skeleton> <plan> --out <out>`
   - enforces byte-preserved `role=`/`words=`, unchanged `structure_fingerprint`,
     and an unblocked gate.
3. Author the contract sidecar (`<slug>.contract.json`). All slots `kind: theme`;
   no contract in the catalog declares a `personalizable` slot yet, and doing so
   here would land ADR-023 content migration inside a diversity slice.
4. `uv run python scripts/check_theme_contract.py <skeleton>` - **all 7 checks**,
   including the A21 leak scan added this session.
5. **Regenerate the diagrams**: `PYTHONPATH=. uv run python
   scripts/render_skeleton_diagrams.py`. The freshness gate
   (`tests/integration/test_skeleton_diagrams_fresh.py`) checks `.puml` **only**,
   but `docs/architecture/story-skeletons.md` links the `.svg`. **`graphviz` must
   be installed**: without `dot`, PlantUML renders structurally *empty* SVGs and
   exits 0. Verify a re-render kept its node groups (`grep -c 'g id='`) before
   staging any SVG. A full re-render also rewrites all 61 SVGs from layout
   coordinate jitter alone; keep only the ones whose label text actually changed.
6. **Regenerate `docs/planning/ws5_floor_baseline.json`** if structure moved
   (`scripts/calibrate_mutation_floors.py`), and **diff it rather than trust it**:
   confirm `TAU_STRUCT`, `TAU_CELL` and `TAU_STATE` are unchanged and only
   observed statistics moved. A threshold shift would silently re-baseline every
   gate that reads the file.
7. **Run the full suite.** Both stale-derived-artifact failures this session were
   caught by a full run and by nothing else.

---

## 5. Suggested order

1. A9 item 2 (one dedicated session) - unblocks 1,100 A20 nodes
2. A20 family-based plan generator (~half a session)
3. The 5 templated trees
4. The 7 remaining bespoke trees, smallest first (32, 105, 128, 155, 197, 248, 250)
5. The clone pair's contracts last
