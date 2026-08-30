# V10, adversarial validation: skeleton rule thresholds, catalog economics, reuse leakage

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `/home/user/cyo-adventure`, `scratchpad/canon/`, `scratchpad/canon/build_canon.py`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.
>
> **Census arithmetic is settled elsewhere.** Cite
> [catalog-census.md](../../../catalog-census.md) (#740): 84 shells, 15,470 nodes, 81 declaring
> production-eligible, 74 reachable in an offered cell, 18 offered cells all covered. Any "86 shells"
> figure in this evidence set reflects a failure to exclude `.narrative.json` sidecars.

Scope: synthesis 4.2 cluster (C1-6, C1-7, C1-8, C1-10, C1-11, C1-13, C1-16; C3-9, C3-12) plus the
census question. `--strict` wiring and cosmetic choice are another validator's; I touch `--strict`
only where enforcing it changes this cluster's arithmetic.

Everything below was recomputed on this tree at `/home/user/cyo-adventure` (HEAD includes `cc3d5f7`).
Reproduction commands are given per claim. Working files:
`scratchpad/canon/` (the reconstructed published books), `/tmp/strictres.json` (the 84-shell
strict/default matrix).

**Headline corrections, before the per-claim detail:**

1. **The production-eligible number is 74, not 84 and not 81.** Every prior denominator is wrong.
2. **The "4 empty cells" do not exist.** All 18 offered cells are populated; the 4 are off-matrix.
3. **`TAU_STRUCT` gates nothing.** C1-8's central noun ("the corpus it gates") is false; the value
   is dead code, which the baseline file, `floors.py` and the PR message all state. C3-12 got this
   right and C1-8 contradicts it. The ratchet is real but harmless; what the ratchet *measures*
   (catalog convergence) is the real finding and neither report drew it out.
4. **`MONTHLY_MERGE_BUDGET` binds the flywheel only, not the catalog.** Hand-authored shells are
   invisible to it and to the 30-day cooldown. C1-7's "2.7 shells/cell/year, catalog-wide" is wrong
   about the scope; PR #730 added 20 shells in one day through the same promotion workflow.
5. **The canon verdict splits by form.** The prose canon *passes the production gate* and is
   rejected only by `--strict` and by PL-29's band rows. The gamebook canon fails the production
   gate outright, but on a rule whose own source comment already declares those two books
   non-commensurable. C1-10 is right about PL-29 and overstated everywhere else.
6. **New, and the most consequential thing in this file:** all 20 `--strict` passers are one per
   cell in 16 of 18 cells. Enforcing `--strict` on the catalog (synthesis recommendation 3) without
   first growing it collapses the selectable pool from 74 to 20, i.e. **pool size 1 per cell**, and
   every child gets the same armature every time. Nobody has stated this interaction.
7. **New:** 11 of the 74 selectable shells breach the `--strict` walk floor today, including 5 of
   the 8 `16+/gamebook` shells at P(satisfying under uniform random) = **0.0000**. The
   `16+/gamebook` cell *median* is 0.0000.
8. **New:** no mutation operator changes a single parent beat. All three pilot mutants, including
   the M3 graft, retain **95/95 parent FILL beats byte-identical**. The flywheel cannot produce a
   book that reads differently, by construction, not by calibration.

---

## Claim 9 (taken first, because 4 and 5 depend on it): the census

**Verdict: all three prior numbers are wrong. The settled figure is 74.**

`skeletons/` holds **149 files**, all `.json`:

| class | count | filter |
| --- | --- | --- |
| skeleton graphs | **84** | basename has exactly one `.` |
| `*.contract.json` theme contracts | 47 | sidecar |
| `*.lineage.json` mutation records | 16 | sidecar |
| `*.narrative.json` | 2 | sidecar |

The "147" glob figure is a glob artifact (149 files; a `**` that misses two, or a stale tree). "61
graphs / 11,458 nodes" in the brief is stale by 23 graphs. "84 shells" is the graph count and is
right as a *file* count but is not the production number. Total nodes across the 84: **15,470**.

Applying the live selector (`generation/skeleton_match.candidates_for_cell`, which is the function
the request path actually calls), the 84 reduce as follows:

| filter | removed | remaining |
| --- | --- | --- |
| all graphs | | 84 |
| `production_eligible is False` (3 MVP seeds, no `length`/`narrative_style`) | 3 | 81 |
| `metadata.deprecated` (ADR-011 D11 retirement) | 6 | 75 |
| mid-series continuation (`series.book_index > 1`: `the-sunken-temple`) | 1 | **74** |

**Production-eligible, on-matrix, auto-pickable: 74.** Draft/MVP: 3. Deprecated-but-retained: 6.
Series continuations: 1. The C1 audit's "81 production-eligible on-matrix" counts the 6 deprecated
shells the matcher refuses; C3-9's "84" counts all four excluded classes.

```sh
.venv/bin/python -c "
from cyo_adventure.generation.skeleton_match import candidates_for_cell
from cyo_adventure.validator.band_profile import offered_cells
print(sum(len(candidates_for_cell(*c)) for c in offered_cells()))"   # -> 74
```

**The offered grid is 18 cells and all 18 are populated.** C3-9's "22 cells, 18 populated, 4 empty
(`3-5/long`, `5-8/long`, `13-16/short`, `16+/short`)" reads `analyze_sibling_exposure.py`'s 22-row
band x length cross-product as if it were the production matrix. It is not.
`band_profile.offered_cells()` returns 18 and those four combinations are not members; the same
script's own comments say a request naming one of them "422s on the auto-pick path, not a repeat".
**C3-9 recommendation (2), "fill the four empty cells first", is refuted: filling them would put
shells in cells the API cannot route to.** That recommendation should be struck.

Per-cell pools (all 18, live selector):

```text
10-13 long/med/short prose  4 5 5      3-5  med/short prose   3 3
13-16 long gb/prose         5 4        5-8  med/short prose   4 3
13-16 med  gb/prose         5 4        8-11 long/med/short    4 4 4
16+   long gb/prose         4 4
16+   med  gb/prose         4 5
```

min 3, median 4.0, max 5. The three thinnest cells are the two 3-5 cells and `5-8/short`, i.e. the
youngest readers have the shallowest catalog. Neither prior report noted that the depth gradient
runs the wrong way against band tenure (a 3-5 reader stays in band ~2 years).

---

## Claim 1 (C1-8): TAU_STRUCT ratchet, TAU_CELL as clone detector, circular calibration

**Verdict: the arithmetic reproduces exactly; the framing is materially wrong on the most
load-bearing word. PARTIALLY UPHELD, with the charge's target misidentified.**

### The ratchet: confirmed, and traced

Committed values across the file's whole three-commit history:

| commit | date | `tau_struct` | n_pairs | p05 | median |
| --- | --- | --- | --- | --- | --- |
| `0463fdd` | 2026-08-10 | 0.331600 | 67 | 0.230462 | 0.390376 |
| `a26718b` | 2026-08-17 | 0.320439 | 76 | 0.192388 | 0.388805 |
| `cc3d5f7` | 2026-08-20 | 0.298321 | 145 | 0.154657 | 0.379906 |

PR #730's message additionally records the two intra-PR intermediates: 0.320439 -> 0.312968 ->
0.304707 -> 0.298321. So the claim's "0.3204 -> 0.3130 -> 0.3047 -> 0.2983 in one PR" is exact.
Monotone decrease, four steps, one PR. Confirmed.

### But TAU_STRUCT gates nothing, so "the corpus it gates" is false

```sh
grep -rn "TAU_STRUCT" --include=*.py src/ scripts/ | grep -E ">=|<|if "
```
returns no comparison anywhere. The only live consumers are the docstring of
`check_promotion_bundle._floor_reason` (which is **stale**: it says the shell must differ from its
parent `>= TAU_STRUCT`, then calls `structural_floor_reason`, which uses only `TAU_CELL`) and
`floors.py`'s own explanation of why it was retired. `ws5_floor_baseline.json` states it directly:
`"DOCUMENTATION ONLY as of the ADR-020 floor-recalibration amendment ... No longer gates mutants"`.

C3-12 reports this correctly; C1-8 does not, and the synthesis 4.2 bullet propagates C1-8's wording.
**The two findings contradict each other and the synthesis carries the wrong one.** A reader of
section 4.2 would conclude a live gate is loosening itself. Nothing is.

The "staleness guard enforces the loosened value" leg is technically true (`skeleton-promotion.yml`
line 136 runs `calibrate_mutation_floors.py --check`) and materially empty: it enforces freshness
of a documentation constant.

### What the ratchet actually shows, and nobody said it

The interesting series is not `tau_struct`, it is the **p05 column: 0.2305 -> 0.1924 -> 0.1547**, a
**33% fall while the catalog grew 67 -> 145 pairs**. The median barely moved (0.3904 -> 0.3799).
That is the signature of a catalog whose *tail* is converging: the new shells are landing close to
existing ones even though the bulk distribution is stable. That is a direct, already-collected
measurement of the homogenisation risk section 1.2 argues for on other grounds, and it is sitting
unread in a file the project regenerates every promotion. **Recommendation: publish p05 (not
`tau_struct`) as the catalog-convergence metric and alarm on a fall.** That is a free instrument.

### TAU_CELL: the "3x below p05" charge is right about the number and wrong about the inference

Recomputed on the **74 selectable** shells (119 in-cell pairs, not the baseline's 145, which
includes deprecated and series shells):

```text
min 0.060110  p05 0.153704  p25 0.320965  median 0.387233  max 0.605791
pairs below TAU_CELL 0.05:      0
pairs below TAU_STRUCT 0.2983: 26  (22%)
```

So `TAU_CELL` = 0.05 is 3.07x below p05, as claimed. But two corrections:

- **On the selectable catalog, no pair falls below 0.05 at all**, the minimum is 0.0601. The
  0.000469 pair (`the-harrowstone-keep` / `the-sunken-temple`) is *not selectable*: `the-sunken-temple`
  is series book 2 and cell matching excludes it. **C3-12's leg 3 is refuted: a child in
  `13-16/long/gamebook` cannot be served that pair through cell matching.** It remains reachable
  through the series flow, which is a different and much weaker exposure.
- The reason `TAU_CELL` is low is stated in `floors.py:277-290` and is sound *for its scope*: it is
  applied to a **mutant's distance from its own parent**, and a sibling-pair percentile applied
  there rejects every bounded mutant. Calling it a "clone detector sold as a diversity floor" is
  fair as a description of its effect and unfair as an accusation of confusion; the code says
  exactly what it is.

The residual criticism stands and is worth keeping: clause 2 also compares the mutant to *every
in-cell sibling*, and a mutant admitted at 0.06 becomes a permanently-served catalog member 2.5x
closer to a sibling than the closest pair a human has ever produced. **The floor's scope should be
split**: keep 0.05 for the parent leg, raise the sibling leg toward the observed p05.

### The topology-weight defect (C3-12 leg 2): confirmed and quantified

`_TOPOLOGY_WEIGHT = 0.2` on a self-declared metadata string. Measured over the 119 selectable
in-cell pairs:

| | n | median distance |
| --- | --- | --- |
| same declared topology | 32 | 0.2396 |
| different declared topology | 87 | 0.4174 |
| **topology-free (recomputed)** | 119 | **0.2821** (raw median 0.3872) |

So **27% of the reported median in-cell distance is a metadata label**, and the entire apparent
gap between "similar" and "diverse" in-cell pairs is that one field. Confirmed. Practical impact is
smaller than "4x TAU_CELL" implies, though: topology-free, the minimum is still 0.0510 and nothing
breaches 0.05. The defect is that the *instrument* is not measuring shape, not that the gate is
currently being evaded.

### Is the calibration circular?

For `TAU_STRUCT`: yes by construction, and irrelevant because it gates nothing.
For `TAU_CELL`: no, it is an owner-chosen constant, explicitly not a percentile.
For the walk floors: **no, and this is where the synthesis is most wrong** (see claim 8).

---

## Claim 2 (C1-10): would the rules reject the canon?

**Verdict: PARTIALLY UPHELD, and the surviving part is sharper than stated. C1-10 is right about
PL-29 and wrong or unproven on four of its five other legs.**

This is the only claim in the cluster I could test empirically rather than by reading thresholds, so
I did. I reconstructed four published structures as skeletons and ran `check_skeleton.py` on them.

### Method and honesty about it

Builders: `scratchpad/canon/build_canon.py` (gamebooks), `build_cyoa.py` (prose). Inputs come from
this repo's own research note, `docs/planning/research/cyoa-structure-measurements.md` s.2 and s.4:

| book | source tag | node count | outdegree histogram | endings | words/node |
| --- | --- | --- | --- | --- | --- |
| Lone Wolf #1 | **MEASURED** (this project's own 2026-08-02 Project Aon crawl) | 350 | 0:17, 1:157, 2:135, 3:36, 4:5 | 17 (16 fail, 1 win) | 84.6 |
| Warlock of Firetop Mountain | REPORTED (secondhand) | 400 | inferred FF 2-way-dominant | 4 (1 win, 3 instant-fail) | ~110 |
| CYOA #53 *Silk King* | **MEASURED** (Bratton 2017) | 115 | tree | 19 | ~125 |
| JHM 2019 median book | **MEASURED** (Table 4, n=40) | 98 | tree, max-outdeg mean 2.58 | 20 | ~125 |

Preserved exactly: node count, outdegree histogram, ending count, ending valence mix, words/node.
**Synthesized: the edge placement**, because the true edge lists are not obtainable here. I therefore
mark every verdict by whether it turns on the measured marginals (placement-independent) or on my
layout. Fidelity check on the one dimension I can validate: my *Silk King* reconstruction gives
P(satisfying | uniform random) = 0.305 against Bratton's measured ~0.39. Close; the prose builder is
faithful. My gamebook builder is **not** faithful on that dimension (it gives LW P(win) = 0.264
against a true value near zero), so I report no walk-floor verdict for the gamebooks.

### Results

| book | cell | default gate | `--strict` | blocking rule(s) | placement-dependent? |
| --- | --- | --- | --- | --- | --- |
| CYOA #53 | 8-11/med/prose/`time_cave` | **PASS** | FAIL | PL-24, CG-1, CG-2, CG-3, PL-23 | PL-23 only |
| CYOA #53 | 10-13/short/prose/`time_cave` | **FAIL** | FAIL | **PL-29 topology** | no |
| JHM median | 8-11/med/prose/`time_cave` | **PASS** | FAIL | L1-7 (98 vs 100), PL-25, PL-24, CG-1/2/3 | L1-7, PL-25 |
| JHM median | 10-13/short/prose | FAIL | FAIL | **PL-29 topology** | no |
| Lone Wolf #1 | 13-16/med/gamebook | FAIL | FAIL | **PL-17** (17 vs 42), PL-20 arc | PL-20 only |
| Warlock | 13-16/long/gamebook | FAIL | FAIL | **PL-17** (4 vs 48), PL-20 arc | PL-20 only |

Verbatim, the decisive line:

```text
ERROR PL-29 topology: band '10-13' may not declare 'time_cave'
      (allowed: ['branch_and_bottleneck','open_map','sorting_hat'])
```
and, at 8-11 where `time_cave` is legal:
```text
ok: skeleton passes gate and brief checks     # CYOA #53, exit 0
```

### What survives of C1-10

**UPHELD, and it is the whole finding: PL-29 bans the canonical CYOA shape at 10-13 and above, and
that is the *sole* blocking failure of a book that clears node count, the endings floor, the arc
floor and the walk floor.** The canonical prose book is one metadata row away from legal. The
catalog census shows the consequence: zero `time_cave` among the 74 selectable shells above 8-11,
and 32 of 74 (43%) are `branch_and_bottleneck`.

**REFUTED: Warlock's node-count failure.** C1-10 places it in `16+/long/gamebook` (floor 475) and
reports 400 as below the floor. `13-16/long/gamebook` is 370-585 and 400 sits comfortably inside it,
and 13-16 is the more honest band for Fighting Fantasy anyway. One of C1-10's "three independent
rejections" is a cell-assignment artifact of the reviewer's own choosing.

**UNPROVEN, the walk-floor leg.** C1-10 asserts Warlock's "uniform-random satisfying-walk
probability is ~0 against a 2% floor". Plausible, untestable from published data (it depends on
edge placement and on dice, which the graph does not encode), and in any case the teen gamebook floor
was set at 0.02 precisely to keep the lethal style legal, the code comment says so. Drop this leg.

**SUSTAINED BUT ALREADY ANSWERED, the PL-17 gamebook endings floor.** 17 vs 42 (2.5x) and 4 vs 48
(12x) reproduce exactly and are placement-independent. But `band_profile.py:648-696` already argues,
in the source, that these two books are "NOT commensurable with this rule: both kill the reader
mainly through dice, so their graphs carry only the failures their authors chose to make structural.
This format has no dice ... Their shares are a lower bound on what a diceless book needs, not a
target." **That is a correct and sufficient defence, and C1-10 quotes it and then presents the
failure as a finding anyway.** A diceless port of Lone Wolf, in which each of its ~20 combats
becomes a terminal, lands near the floor. The finding here is not "the rules reject the canon"; it
is "the rules block a comparison the code already documents as invalid", which is a **messaging**
defect, not a calibration one. The fix is a one-line refusal (`narrative_style: gamebook` +
`dice_gated: true` -> the rule reports rather than blocks), not a threshold change.

**NEW, and the strongest version of C1-10's underlying thesis, the choice-grammar rules contradict
their own cited corpus.** This is placement-independent and neither report found it:

| rule | value | JHM 2019 Table 4, the corpus ADR-011 anchors on | gap |
| --- | --- | --- | --- |
| CG-1 `_CHOICELESS_SHARE` at 8-11/10-13 | max 50% single-choice non-ending nodes | decision pages mean 20.43 of ~78 non-ending text pages -> **~74% single-choice** | rule is ~1.5x stricter than the corpus |
| CG-2 `_OPTIONS_BOUNDS["10-13"]` | target exactly **[3, 3]**, 20% variance allowance | **max** outdegree mean 2.58 (median max 2, ceiling 4) -> the *typical* decision is 2-way | rule mandates 3-way where the corpus is 2-way |
| CG-3 `_WORDS_PER_STOP_CEILING` 8-11 | 135 words | ~125 words/page x runs of 5-12 linear pages | corpus routinely 2-10x over |

My *Silk King* run fires all three: `80 of 96 non-ending nodes are single-choice, above band 8-11's
50% allowance of 48`; `14 of 16 decision nodes vary from band '10-13' target [3,3]`. And
`choice_grammar.py:127-162` states the derivation: **ADR-011 section 10's own cadence column**, a
designer table, not the corpus. So the choice-grammar family is calibrated against an internal
document while the endings and node-count families are calibrated against JHM. Two rule families,
two incompatible anchors, no reconciliation.

### The defensible verdict on "too narrow or correctly narrow"

**Correctly narrow on stakes and shape; wrongly narrow on cadence and topology, and for two
different reasons.**

- *Correctly narrow:* PL-17's prose endings fraction, the arc floor, the walk floors and the
  ending-mix ceiling all reject the gamebook canon, and they should. A 16-death, 1-win, dice-gated
  quest is not the product; ADR-011's own genre split says so, and the app has no dice. The
  gamebook canon is out of scope by design, not by miscalibration. The rules are right and the
  *message* is wrong.
- *Wrongly narrow, kind 1 (topology):* PL-29's 10-13 row excludes the single most-studied shape in
  the medium, at the band the anchor research covers, with no recorded rationale. C1-10 is right.
  The band rows should be justified in ADR-011 s.7 or `time_cave` restored at 10-13.
- *Wrongly narrow, kind 2 (cadence):* CG-1/CG-2/CG-3 are 1.5-2x tighter than the corpus and are
  `--strict`-blocking. They are the reason a faithful CYOA book cannot be authored to the bar. They
  are the largest single contributor to the 2,456 strict findings (CG-3 1,965 + CG-2 344 + CG-1 80 =
  2,389 of 2,456, i.e. **97%**). Any plan to enforce `--strict` must reconcile these first.

Gamebooks are indeed a different form and the bands may legitimately differ; that concession is
already in the code. It does not cover PL-29 or the CG family, which are prose rules failing prose
canon.

---

## Claim 3 (C1-6): what a shell freezes

**Verdict: numbers reproduce exactly; the chosen metric (words) is the wrong one and understates
the finding. UPHELD on substance, restated.**

Exact reproduction over all 84 graphs:

```text
labels 22,165  label_words 127,365   slot tokens 2,440 (1.92% of label words)
beats  15,470  beat_words  464,631   slot tokens 14,999 (3.23% of beat words)
contracts 47   with a `decisions` block: 0
```

`check_decision_overlap.py` on a real pair prints `no node declares a multi-option decisions block
in both contracts`. Contract keys are `contract_version, skeleton_slug, age_band, legacy_lexicon,
default_binding, slots` in all 47. Inert, as claimed.

### Why "% of words" is the wrong denominator

`.claude/skills/cyo-author/SKILL.md:41-45` says the opposite of what the word metric implies:

> each choice label is rewritten into final choice text in the theme's vocabulary while preserving
> the original label's action-semantic (**labels are leaf content; their meaning is frozen, their
> surface is not**).

So no reader ever sees a `beats=` string, and the label *words* are rewritten per theme. The
1.9%/3.2% slot share measures how much of the **authoring directive** is parameterised, not how much
of the **book** varies. C1-6's headline ("22,165 labels and 464,631 words are frozen in shells")
is literally true of the artifact and misleading about the reader, and the skill's own sentence is a
stronger citation than the word count is.

### The right metric, measured

Take `skeletons/8-11/the-locked-carousel.json` (71 nodes, 13 endings, 47 contract slots). Over 2,000
uniform-random reader walks:

- **median 9 decisions per read, median 14 nodes per read, 13 reachable endings.**

Of what the reader perceives on that read, held constant across **every** book ever filled from this
shell:

| reader-perceptible element | count per median read | varies per book? |
| --- | --- | --- |
| decision points, and their positions in the arc | 9 | **no** |
| options offered at each (1,1,1,7,2,2,...) | ~15 | **no** |
| action-semantic of each option | ~15 | **no** (skill: "meaning is frozen") |
| scene-by-scene plot direction (`beats=`) | 14 | **no** |
| ending reached, its valence and its kind | 1 of 13 | **no** |
| pacing (words between decisions) | fixed by node budget | **no** |
| proper nouns bound by the theme contract | 47 slots | **yes** |
| prose surface | ~1,800 words | **yes** |

So the honest statement is: **on a median read, 100% of the decisional and structural experience is
frozen and 0% varies; what varies is word choice and 47 proper nouns.** And the slots do not even
free the nouns' roles, the contract fixes those too:

```json
{"id":"ANCESTOR","meaning":"The hero's deceased grandmother, the maker whose legacy
  drives the mystery.","guidance":"A beloved relative-maker, gone a year; ..."}
```

Every book from this shell is *a child sneaks out at night to investigate a padlocked heirloom her
dead maker-grandmother built, guided by an old caravan-dwelling guardian*. A sample beat:

> `beats='the door opens before her knuckles land twice; {GUARDIAN}, wiry and white-whiskered,
> looks at the girl on his step at midnight and does not even blink'`

That is the scene, written. The theme brief changes the guardian's name. This is exactly the
find-and-replace the skill's next bullet forbids the author from producing ("prose that would fit any
theme after a find-and-replace is a defect"), made architectural one paragraph earlier.

**Restate C1-6 as: a shell freezes 100% of the reader's decisional experience and the entire scene
sequence; the theme contract varies 47 nouns whose semantic roles are themselves fixed.** That is
both more accurate and much harder to argue with than 1.9%.

---

## Claim 4 (C1-7): catalog economics

**Verdict: the demand side is UPHELD and slightly tighter than claimed. The supply side is
MISCHARACTERISED, the cap binds the flywheel, not the catalog.**

### Demand side: confirmed, recomputed on 74

20,000 trials per cell through the real `select_skeleton_for_cell` with real `1/(1+recent_count)`
weighting:

| cell (pool) | P(repeat by req 2) | P(repeat by req 4) | P(repeat by req 6) | N50 | E[distinct after 6] |
| --- | --- | --- | --- | --- | --- |
| 3-5/short (3) | 0.200 | **1.000** | 1.000 | 3 | 2.96 |
| 3-5/medium (3) | 0.201 | 1.000 | 1.000 | 3 | 2.95 |
| 5-8/short (3) | 0.199 | 1.000 | 1.000 | 3 | 2.95 |
| 8-11/short (4) | 0.141 | 0.768 | 1.000 | 4 | 3.71 |
| 10-13/short (5) | 0.114 | 0.619 | 1.000 | 4 | 4.21 |
| 13-16/long/gb (5) | 0.109 | 0.618 | 1.000 | 4 | 4.21 |

Claim 4 said "~14% at the second request with 4 candidates", measured 0.141-0.146. Exact. "Cell
exhaustion at request 4-6", measured: repeat is **certain by request 4** in the three-pool cells and
by request 6 everywhere; N50 is **3-4**, not C3-9's "3-5". After six requests in the thinnest cells a
child has seen **2.95 distinct armatures**. Upheld and tightened.

### Supply side: the cap does not do what the claim says

Constants confirmed: `OPEN_PR_GLOBAL = 3`, `COOLDOWN_DAYS = 30`, `MONTHLY_MERGE_BUDGET = 4`
(`flywheel/strategy.py:85,89,94`). The arithmetic 4/mo x 12 / 18 cells = **2.67 shells/cell/yr** is
right *as arithmetic*. But:

- The only enforcement point is `flywheel.cadence.select_growable_cells`, called only by
  `scripts/flywheel_cycle.py`. No workflow enforces it.
- `flywheel_cycle._merge_history` counts a merge only `if addition.slug in lineage_slugs`, i.e.
  **only shells carrying a `.lineage.json`, which means only flywheel mutants.** Hand-authored
  additions are invisible to both the monthly budget and the per-cell cooldown.
- `skeleton-promotion.yml` triggers on `paths: skeletons/**` and gates *quality*. It imposes no rate
  limit at all, and its own header says a hand-authored original "still faces gate/cell/envelope"
  with "only the two parent-relative legs skipped".

Direct disproof of the ceiling: **`cc3d5f7` added 20 shells on one day**, five months of "catalog-wide
budget" in a single PR, through this exact workflow.

So C1-7's ceiling is the *mutation flywheel's* ceiling. Since claim 5 independently shows mutants are
perceptual no-ops, the flywheel's budget is not the binding constraint on variety, **human authoring
throughput is**, and that is unmeasured and unbounded by any constant in the repo. C1-7 should be
rewritten to name the real constraint. Its recommendation (b) "set the flywheel budget from the
repeat number" is aimed at the wrong dial.

The review-cost leg is sound: median selectable shell is 157 nodes, 6 exceed
`HAND_AUTHORING_NODE_CEILING = 460` (max 677), and `layer2.py` says the machine walk is then "its
sole correctness guarantee".

---

## Claim 5 (C3-9): the 130-334 shortfall

**Verdict: UPHELD on arithmetic (and computed on the correct denominator all along), REFUTED on two
of its framing facts and on one recommendation. The "refuted lever" conclusion is UPHELD and
strengthened.**

`analyze_sibling_exposure.py --section sizing` reproduces exactly: shortfall **32 / 130 / 334 / 742**
at 0.5 / 1 / 2 / 4 books per month, summed over bands. Crucially, its `have/cell` column already uses
the 74-shell pools (3,3 / 3,4 / 4,4,4 / 5,5,4 / 4,5,4,5 / 5,4,4,4 = 74), so **the shortfall numbers
were computed on the right denominator even though C3-9's prose says 84.** No revision needed.

Two framing corrections (see claim 9): "22 cells, 18 populated, 4 empty" is not the production
matrix, and recommendation (2) should be struck.

One methodological caveat C3-9 does not state: the model is "one skeleton serves each child once",
i.e. **zero reuse tolerance across a child's whole band lifetime**. That is an upper bound, not a
requirement. A child who meets the same armature 14 months and a different world later may not
perceive a repeat. The programme has never measured reuse tolerance and it is the single cheapest
number that would move this estimate by an order of magnitude in either direction.

### The scaling mechanism: refuted more strongly than C3-9 states

The pilot table (`docs/planning/evidence/mutation-per-request-pilot/README.md`) reproduces: M1
d(parent) = **0.0000** with 95/95 nodes and 95/95 FILL beats byte-identical; M4 = 0.0038; the M3
graft chain X = 0.0726. But read the columns C3-9 skipped: **mutant X also keeps 95/95 parent nodes
and 95/95 parent FILL beats byte-identical.** The graft *appends* 33 nodes; it does not recompose
anything.

Cross-checked against the code: `grep -rn "beats" src/cyo_adventure/mutation/` shows no operator
that edits a beat. **In 4,278 lines of operators there is no mechanism that changes what a scene is
about.** So the refutation is not empirical-and-contingent ("the mutants we tried were no-ops"); it
is **structural**: a mutant is definitionally its parent's story with the graph moved. Given claim 3
(the beats *are* the story), the flywheel cannot ever produce a different adventure. C3-9's
recommendation (4), state in ADR-020 that mutation is a coverage mechanism, not a variety
mechanism, is correct and should be strengthened to a design statement, not a caveat.

### Is the shortfall survivable without abandoning whole-skeleton reuse?

Four candidate levers, priced:

1. **Grow the catalog by hand.** S-1 shows a tool-assisted tier authors strict-passing shells at ~4-6
   checker runs and near-zero provider cost. If that holds, 130 shells is a throughput and
   *human-promotion-review* problem, not a money problem. This is the only lever that survives
   scrutiny at the current architecture, but see the review-economics finding in synthesis 1.4, and
   note that promotion review is a human reading a 151-node JSON diff.
2. **Mutation.** Refuted structurally, above. It buys coverage of thin cells at zero variety.
3. **Raise reuse tolerance instead of supply.** Unmeasured. If a family tolerates an armature repeat
   at 12+ books' distance, the requirement drops from 130 to roughly the cell pool needed to hold a
   12-book cooldown, i.e. ~12/cell = 216 total, worse, not better, for thin cells. If tolerance is
   at 6 books, ~108. This lever does **not** rescue the arithmetic; it reprices it. Worth measuring,
   not worth hoping for.
4. **Move the varying layer off the shell** (the stratified plan / the blank-slate proposal). Only
   lever that changes the exponent rather than the constant. Reviewed in the next section.

**Answer: no, not by any means that exists today.** Hand authoring can supply 130 shells over some
number of quarters, but claim 3 shows 130 shells is 130 *fixed adventures*, which is a linear buy
against a demand that grows linearly with subscribers x months. The catalog approach cannot amortise.

---

## Claim 6 (C1-11): one PR, one model, one session

**Verdict: FULLY UPHELD, and materially worse than reported.**

Measured in-process across all 84 shells (`/tmp/strictres.json`):

```text
strict pass 20   default pass (with --allow-mvp) 84   of 84
strict-passers by add-commit: [('cc3d5f7 2026-08-20', 20)]
```

All 20, one commit. That commit's message carries 55 `Claude-Session:` lines, all
`session_01H9utokJznmXRiewWJBRn3E`, and one `Co-Authored-By: Claude Opus 5`. One PR, one model, one
session: confirmed on all three axes.

**What C1-11 missed, and it is the most important number in this file:**

| cell | strict-passers |
| --- | --- |
| 16 of the 18 offered cells | **1** |
| `10-13/medium/prose`, `13-16/medium/gamebook` | 2 |

Topologies among the 20: `branch_and_bottleneck` 13, `gauntlet` 2, `loop_and_grow` 2, `open_map` 2,
`sorting_hat` 1, **`time_cave` 0**, even though `time_cave` is legal at three bands and four
selectable shells use it.

Consequence, which no report states: **synthesis recommendation 3 (pass `--strict` in
`check_promotion_bundle.py`) applied to the existing catalog would reduce the selectable pool from 74
to 20, one shell per cell in 16 of 18 cells.** Every request in those cells would return the same
armature, forever, authored by one model in one session on one day, carrying whatever correlated
defect that cohort has. The synthesis's own recommendation 3 already carries a prerequisite ("after
fixing PL-18/PL-29"); it needs a second one: **`--strict` must be enforced on *new* shells only,
with the 54 non-compliant selectable shells grandfathered on a shrink-only list, and it must not be
allowed to change the selection set.** Without that, the fix for finding 1.3 causes a worse instance
of finding 1.2.

The correlated-defect leg (bottleneck/track coherence recurring within 24 hours, AL-443/AL-448) is
quoted accurately from `cc3d5f7`'s message and I confirm no deterministic layer measures it:
`grep -rn "track\|payoff" src/cyo_adventure/validator/` finds nothing of the kind.

---

## Claim 7 (C1-13): the mutation acceptance battery

**Verdict: UPHELD, exactly as stated.**

`mutation/acceptance.py:669` is `gate = run_gate(candidate)`, the default gate, no
`enforce_grammar`, no `--strict` escalation set. `grep -rn "enforce_grammar" src/ scripts/` shows the
only caller that passes `True` is `check_skeleton.py:784` behind `args.strict`.
`grep -rn "consequence\|outcome_spread\|walk_floor" src/cyo_adventure/mutation/` returns nothing.

So the battery's reader-facing content is: nothing. Every stage is structural or bookkeeping. 16 of
84 shells carry a `.lineage.json`.

Two additions to the finding:

- Given claim 5's structural result (no operator touches a beat), upgrading the battery would not
  make mutants varied; it would only stop them being *worse*. The recommendation is still right,
  add the walk floor, the depth-qualified endings floor, `enforce_grammar=True` and the outcome
  spread as reject-only stages, but it should be framed as **quality containment**, not as making
  the flywheel a variety mechanism.
- `check_promotion_bundle._floor_reason`'s docstring is stale (claims a `>= TAU_STRUCT` parent
  clause that no longer exists). One-line doc fix, worth doing because it is the document a promotion
  reviewer reads.

---

## Claim 8 (C1-16): provisional floors and catalog-derived walk floors

**Verdict: the `_ENDINGS_FRACTION` leg is UPHELD; the walk-floor circularity leg is REFUTED, and
what is actually true about the walk floors is far more alarming.**

### `_ENDINGS_FRACTION["gamebook"] = 0.12`: upheld

The source comment says it outright: `"PROVISIONAL, and the register row says so: the draft clears
0.12 by a single ending, so this is calibrated to the edge of an n=1 sample. A second diceless
gamebook is what would settle it."` n=1, blocking, and it is the rule that rejects both published
gamebooks. Upheld verbatim.

### The walk floors are not "medians of the catalog they gate"

The comment records 2026-08-09 catalog medians of 100% / 71% / 43% / 29% / 0.3% / 1.2% and the
ratified floors are 0.60 / 0.40 / 0.25 / 0.15 / (prose 0.10, gamebook 0.02). Those are 55-60% of the
then-median at the child bands, and at 13-16 the floor of 0.02 was set **above** the then-catalog
median of 0.003, i.e. deliberately against the catalog rather than from it. Calling them "medians of
the catalog they gate" is wrong, and it is the sentence the synthesis 4.2 bullet carries.

### What I measured instead, and it should be its own finding

P(reaching a positive- or neutral-valence ending under uniform random play), 4,000 walks per shell,
over all **74 selectable** shells:

| band / style | n | median P(satisfying) | floor | ratio |
| --- | --- | --- | --- | --- |
| 3-5 prose | 6 | 1.0000 | 0.60 | 1.67x |
| 5-8 prose | 7 | 1.0000 | 0.40 | 2.50x |
| 8-11 prose | 12 | 0.8932 | 0.25 | 3.57x |
| 10-13 prose | 14 | 0.7120 | 0.15 | 4.75x |
| 13-16 prose | 8 | 0.6836 | 0.10 | 6.84x |
| 13-16 gamebook | 10 | 0.0882 | 0.02 | 4.41x |
| 16+ prose | 9 | 0.5128 | 0.10 | 5.13x |
| **16+ gamebook** | **8** | **0.0000** | **0.02** | **0.00x** |

**11 of the 74 selectable shells breach the floor**, and five of them sit at exactly 0.0000:
`the-pale-road`, `the-drowned-court`, `the-tenfold-siege`, `the-ashfall-expedition`,
`the-red-meridian-run` (plus `the-iron-spire-trial`, `the-labyrinth-of-glass`,
`the-thornwood-trial` at 13-16, and `the-blackwood-sanatorium` at 0.0008, `the-vanishing-orchard` at
0.033, `the-smugglers-cut` at 0.0073).

The `16+/gamebook` **cell median is 0.0000**: for the majority of that cell, a reader choosing at
random never reaches a satisfying ending. These are selectable today, because the walk floor is
`--strict`-only and `--strict` is enforced nowhere. Caveat stated fairly: a real reader reads the
labels and does not choose uniformly, so this understates a purposeful reader's win rate, but it is
the rule as written, and the rule was ratified by an owner as the child-experience guarantee.

This is a concrete, reader-facing consequence of the `--strict`-not-wired finding and it belongs in
section 1.3 rather than buried under threshold provenance.

---

# Recommendation review

## Synthesis section 8, against what I measured

| # | recommendation | my verdict |
| --- | --- | --- |
| 3 | Pass `--strict` in `check_promotion_bundle.py` after fixing PL-18/PL-29 | **Right, with a second prerequisite it does not state.** Enforcing it collapses selection 74 -> 20, one shell per cell in 16 of 18 (claim 6). It must be scoped to *newly added* shells with a shrink-only grandfather list, and must never gate `candidates_for_cell`. Also: **97% of the 2,456 strict-blocking findings are CG-1/2/3** (CG-3 1,965, CG-2 344, CG-1 80; the rest are PL-23 31, PL-24 30, PL-26 6 -- recounted this session; the C1 audit's itemisation of the same total is wrong), and claim 2 shows the CG family is 1.5-2x tighter than the corpus it claims to serve. **Reconcile the CG family against JHM Table 4 before enforcing, or the bar will exclude the canon and admit only PR #730's house style.** |
| 6 | Correct the brief's scale facts to "84 shells" | **Insufficient.** 84 is the file count. The production number is **74**, and the "4 empty cells" do not exist. Correct to: 149 files / 84 graphs / 74 selectable / 18 offered cells, all populated, pools 3-5. |
| 7 | Promote `consequence.py` to a gate; a validator module with no gate caller fails the build | **Endorsed, and extend it.** `check_outcome_spread.py` (`grep -rn check_outcome_spread .github/` -> no hit) and `check_decision_overlap.py` (0 of 47 contracts carry the block it reads) are two more. The build rule should be "a checker with no caller **or no data to read** fails the build", an inert instrument and an unwired one are the same defect. |
| 11 | Re-score S-1 with distance-from-catalog as a covariate | **Endorsed and now urgent.** Claim 6 shows the strict bar is one cohort's house style, and claim 2 shows the CG family is the bulk of it. "Strict-passing" and "resembles PR #730" are currently near-synonyms. |
| - | *missing* | **Publish the `ws5_floor_baseline.json` p05 series as the catalog-convergence alarm.** It has already fallen 33% (0.2305 -> 0.1547) across 78 added pairs while the median held. Free instrument, already regenerated on every promotion, currently unread. |
| - | *missing* | **The 11 walk-floor breaches, including 5 shells at P(satisfying) = 0.0000, are selectable now.** Either grandfather them explicitly or fix them; do not leave them undeclared. |

## The blank-slate alternative: components + a 10^4 design cell sampled at plan time

Taken seriously, this is the strongest architectural argument in the whole review set, and the
evidence I gathered supports it more than the blank-slate reviewers could have known.

**The argument they made:** a fixed catalogue is a countdown to a plateau; sample a design cell
(archetype x problem x agency model x ending family x voice x tone, ~10^4-10^5) deterministically in
code with a per-family cooldown, and amortise *components* (beat modules, ending kits, choice
archetypes) rather than whole skeletons. A1-24..28, A1-13; A2 independently.

**Three things I can add that make it stronger:**

1. **The current architecture already IS a design-cell sampler; its design space is 74.** The offered
   matrix collapses archetype, problem, agency model, ending family, voice and tone into one draw
   from a pool of 3-5. The blank-slate proposal is not a new mechanism; it is the same mechanism with
   the space widened by ~3 orders of magnitude. That reframing makes migration a *scaling* question
   rather than a *rewrite* question, and it is the honest way to put it to an owner.
2. **The plateau is not a projection; it is measured.** N50 = 3-4 requests (claim 4); certain repeat
   by request 4-6; 2.95 distinct armatures after six requests in the thin cells. The countdown has
   already run out.
3. **The catalog cannot be saved by its own growth mechanism, structurally.** No mutation operator
   changes a beat (claim 5). This is not a tuning failure; there is no code path.

**Three things that cut against it, which the blank-slate reviewers could not see:**

1. **Human approval is per-artifact and is the binding cost (synthesis 1.4).** A composed skeleton is
   a *new* graph every request, so it cannot inherit a promotion review. The catalog's real economic
   function is not amortising *authoring* cost, it is amortising **structural review** cost: 74
   reviewed graphs stand behind unlimited books. Component composition moves review from
   O(catalog) to O(books) unless the *composition rule* can be reviewed instead of the composition.
   **That is the crux, and no reviewer in any cohort has addressed it.** A component library is only
   cheaper if you can prove a property of every assembly from properties of the parts, i.e. if the
   validator becomes compositional. It currently is not: `run_gate` reads whole graphs.
2. **`--strict` is 97% choice-grammar rules calibrated to a designer table (claim 2).** Composing
   from components will violate CG-1/2/3 at least as often as hand-authoring does, because those
   rules constrain *global* cadence properties that no local component can guarantee. Migration
   therefore requires the CG reconciliation anyway.
3. **The 3-5 and 5-8 bands may not want it.** Their shells are 10-86 nodes with 2-6 endings and
   walk probability 1.0. At that scale the design space is genuinely small and a preschooler's
   tolerance for repetition is famously high. Compose at 8-11 and above; leave the young bands on
   the catalog.

**Which is right for this product?** The component model, at 8-11 and above, **conditional on making
the gate compositional**. The catalog model is correct only if reuse tolerance turns out to be much
higher than assumed, and that is measurable for the price of one study.

**Migration cost, concretely.** Not a rewrite; four pieces, each independently useful:

| piece | cost | already exists? |
| --- | --- | --- |
| a) Decompose the 74 shells into beat modules / ending kits / choice archetypes | weeks; `mutation/operators.py` already has subtree extract + graft (M3) | half-built, mislabeled |
| b) A composition rule + explicit design space with documented cardinality | days; it is a data file plus a sampler, and `flywheel/strategy.py` already has cooldown machinery | no |
| c) **Compositional validation**: prove `run_gate` verdicts from component properties + assembly invariants | **the hard one, months**; this is the load-bearing item | no |
| d) Review the *composition rule* under ADR-005 instead of each graph; ADR amendment | owner decision | no |
| e) Populate the `decisions` block during parameterization so `check_decision_overlap.py` can run | days; the data is derivable from beats + labels | script exists, data does not |

(c) is the whole risk. **Recommend spending two weeks establishing whether (c) is tractable for the
existing rule set before committing to (a).** Concretely: take the ~15 blocking rules and classify
each as local (checkable per component: PL-15, PL-16, CG-2), assembly-invariant (checkable from
counts: PL-17, L1-7), or global (requires the whole graph: PL-18/PL-29 topology, the walk floor,
PL-20 arc, PL-25 first-decision, CG-1 share, CG-3 stops). If the global set is small and each
member admits a compositional bound, the migration is real. If it does not, the component model
does not save review cost and the answer is to grow the catalog and measure reuse tolerance.

## If thresholds are circularly calibrated, what is the non-circular way?

Only one of the three families is genuinely circular (`TAU_STRUCT`, which gates nothing), so the
question is better posed as: *what is the non-circular anchor available today?* There are three, all
free, all already cited by the repo, none ever run against the rules.

1. **The JHM 2019 digraph collection: 40 real books, real digraphs, ages 9-12, published at
   `alisonmarr.com/cyoa.html`.** The project cites the paper and has never run `check_skeleton.py`
   over the corpus. This is the single highest-value item in this file. Concretely:
   - Import the 40 digraphs as skeleton fixtures (structure only; no prose needed for L1-7, PL-17,
     PL-18/29, PL-25, PL-26, CG-1, CG-2, the in-degree cap and the walk floor).
   - Publish a **corpus pass rate per rule**. Any prose-band rule that rejects more than a stated
     fraction of the corpus is miscalibrated until the divergence is justified in writing.
   - Set the calibration policy as a two-sided constraint: **a rule must admit >= X% of the anchor
     corpus and reject 100% of the seeded defect corpus.** That is non-circular by construction,
     because neither reference set is the project's own output.
   - My claim-2 runs predict what this will find: CG-1 and CG-2 will reject most of the 40.
2. **Project Aon's Lone Wolf series: 28 books, licensed XHTML, already crawled once.** This directly
   retires `_ENDINGS_FRACTION`'s "PROVISIONAL, n=1" caveat. The comment names the falsifier ("a
   second diceless gamebook is what would settle it") and the corpus supplies 27 more of the *same*
   dice-gated kind, which is itself the answer: it will show the gamebook fraction is not
   measurable from dice-gated books, and that the diceless rule needs a diceless corpus that does not
   exist. **Then the honest move is to make the gamebook endings floor advisory until one exists**,
   rather than blocking on n=1.
3. **Boyles' per-book stats for CYOA #1-23** (endings 14-44, distinct acyclic paths 20-47,358,
   longest paths 14-42, a random-play difficulty score) as an independent cross-check on the walk
   floors, which currently have no anchor at all outside a single owner ruling.

And the standing rule that prevents recurrence: **a threshold derived from `skeletons/` must carry a
`falsifier:` field naming the external observation that would move it and who supplies it.**
`_ENDINGS_FRACTION` already does this informally and is the model; the walk floors and the in-degree
caps do not. C1-16's recommendation is right; this is how to operationalise it.

---

# What everyone missed

1. **The production number is 74 and every report used a different wrong one.** Every economics
   argument in the review set inherits it.
2. **Enforcing `--strict` collapses selection to one shell per cell.** The fix for finding 1.3
   causes a severe instance of finding 1.2. This interaction appears in no report.
3. **Five selectable shells have P(satisfying) = 0.0000 and the `16+/gamebook` cell median is
   0.0000.** A reader-facing property of the shipped catalog, measurable in twenty lines, unmeasured
   by anyone.
4. **97% of strict findings are choice-grammar, and choice-grammar is calibrated against an internal
   designer table while the rest of the rule set is calibrated against JHM.** Two anchors, never
   reconciled. This is the reason the canon fails `--strict`, and it is not a topology problem.
5. **CG-2 at 10-13 demands exactly 3 choices where the anchor corpus's *maximum* outdegree averages
   2.58.** The rule mandates a fan the corpus does not have.
6. **No mutation operator changes a beat.** 4,278 lines, three pilot mutants, 95/95 parent beats
   byte-identical in all three including the graft. The flywheel's refutation is structural, not
   empirical, and that is a much stronger statement than "the mutants we measured were no-ops".
7. **The catalog's real economic function is amortising *structural review*, not authoring.** This
   is the argument against the component model and no cohort made it. It is also the thing to test
   before migrating.
8. **The `ws5_floor_baseline.json` p05 series is a free, already-collected catalog-convergence
   alarm** and it has already fallen 33% while the median held.
9. **The four "empty cells" are off-matrix**, and C3-9's recommendation to fill them would put shells
   where the API cannot route.
10. **The 0.000469 structural-twin pair is not selectable** (series book 2), so C3-12's exposure
    claim overstates a real but much narrower problem.
11. **The youngest bands have the thinnest pools (3) and the longest band tenure.** The catalog's
    depth gradient runs backwards against exposure.
12. **`analyze_sibling_exposure.py` and `check_skeleton.py` disagree with `skeleton_match.py` about
    what a cell is** (22 rows with pooled styles vs 18 offered cells). Three definitions of the
    product's core partition, in one repo. That is how the census got lost.

---

## Reproduction index

| item | command |
| --- | --- |
| census | `.venv/bin/python -c "from cyo_adventure.generation.skeleton_match import candidates_for_cell; from cyo_adventure.validator.band_profile import offered_cells; print(sum(len(candidates_for_cell(*c)) for c in offered_cells()))"` |
| strict/default matrix | in-process driver over `scripts/check_skeleton.py`, results at `/tmp/strictres.json` |
| canon reconstructions | `scratchpad/canon/build_canon.py`, `build_cyoa.py`; then `check_skeleton.py <file> [--strict]` |
| repeat simulation | 20k trials through `select_skeleton_for_cell` per cell |
| walk probabilities | 4k uniform walks per shell over the 74 selectable |
| in-cell distances | `structural_distance` over `itertools.combinations(candidates_for_cell(*c), 2)` |
| threshold history | `git show <sha>:docs/planning/ws5_floor_baseline.json` for `0463fdd`, `a26718b`, `cc3d5f7` |
| flywheel cap scope | `scripts/flywheel_cycle.py:237-242` (`if addition.slug not in lineage_slugs: continue`) |
