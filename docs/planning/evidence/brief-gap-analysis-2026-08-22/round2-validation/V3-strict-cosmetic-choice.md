# V3, adversarial validation: the structural authoring bar and cosmetic choice

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `/home/user/cyo-adventure`, `scratchpad/v3run.py`, `scratchpad/d0.py`, `scratchpad/out_strict.txt`, `scratchpad/rc_strict.json`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.

Adversarial re-verification of C1-1..C1-5 and B2-6, 2026-08-22, tree `/home/user/cyo-adventure`
(clean `main`, not the `brief-evidence` worktree). Every number below was recomputed in this
session with my own harness; none is quoted from the prior review. Harness and raw output:
`scratchpad/v3run.py`, `scratchpad/d0.py`, `scratchpad/out_strict.txt`, `scratchpad/rc_strict.json`.

**Headline.** Claim 4 survives everything I threw at it *for `the-observatory-shift`*, and I found
a stronger proof than the review had. It does **not** survive as a catalog-wide characterisation:
64 of the 302 duplicate-target choices are legitimate state-carrying convergence, exactly the
design the brief asked me to test for, and 204 of the remaining 238 are one shell. The review's
flagship exhibit is real and is an extreme outlier, and the recommendation built on it is
mis-sequenced and under-scoped in ways that would have caused a bad rollout.

---

## Claim 1: no caller anywhere passes `check_skeleton.py --strict`

- **Verdict**: CONFIRMED.
- **Severity**: critical.
- **What I did to break it**: grepped every file type that could carry an invocation
  (`.py .yml .yaml .md .sh .toml`) across the whole tree, not just `.github/` and `scripts/`,
  hoping to find a composite action, a Makefile, a pre-commit hook, or a nox session that
  supplies the flag. I also checked `.pre-commit-config.yaml` (its `--strict` at line 274 is
  `actionlint`), `noxfile.py` (`mkdocs build --strict`), and `fips-compatibility.yml`
  (`check_fips_compatibility.py --strict`).
- **Evidence**: every `--strict` token that is adjacent to `check_skeleton` is a docstring
  (`scripts/check_skeleton.py:5,17,33,91,154`), the argparse declaration (`:770`), a prose
  reference in `validator/{choice_grammar,policy,topology}.py`, `generation/skeleton.py:75`, the
  drafting brief's *advice to the author* (`scripts/generate_drafting_brief.py:265`), tests, ADR
  and lessons-log text. Not one is an invocation by anything that runs in CI or in a hook.
- **What the prior review missed**: two further loose-gate call sites it named but did not press
  on. `mutation/acceptance.py:669` is `gate = run_gate(candidate)` and
  `scripts/parameterize_skeleton.py:543` is `gate_result = run_gate(parameterized)`; both omit
  `enforce_grammar=True`, which is the parameter `load_skeleton` exists to forward
  (`generation/skeleton.py:64-77`). This matters for the recommendation: a `--strict` promotion
  gate that leaves these two loose is **bypassable by routing new work through the mutation
  flywheel or the parameterization migration** instead of through a hand-authored PR.

---

## Claim 2: `skeleton-promotion.yml` -> `check_promotion_bundle.py:322` never appends `--strict`

- **Verdict**: CONFIRMED.
- **Severity**: critical.
- **What I did to break it**: read the workflow end to end looking for a second prover invocation,
  an env var, or a matrix leg that adds the flag; read `check_promotion_bundle.py`'s argv
  construction and its `_run_check_skeleton` helper.
- **Evidence**: `.github/workflows/skeleton-promotion.yml:117-125` is the only call site and
  passes only the changed-file list. `check_promotion_bundle.py:322` is literally
  `skeleton_argv = [str(shell_path)]`, and `:323-324` appends `--allow-mvp` when
  `not declares_production_eligible(shell_doc)`. Nothing else is ever appended.
- **What the prior review missed** (and this is probably the root cause of the whole defect):
  the code's own comment block calls the non-strict production envelope "the strict check".
  `check_promotion_bundle.py:311-312`: *"#VERIFY: tests/unit/test_ws8_promotion.py asserts both
  directions -- a seed proves clean, and flipping the same shell's flag to true re-arms the
  strict check."* There is a test asserting that "strict" is re-armed, and it passes, because
  "strict" here means "without `--allow-mvp`". The vocabulary collision manufactures a green
  test and a confident comment for a gate that does not run the bar. Any remediation must
  rename this, or the same confusion will recur.

---

## Claim 3: 81/84 pass the default gate; 20/84 pass `--strict`

- **Verdict**: CONFIRMED for `--strict` (exactly 20/84). **REFUTED as stated for the default**,
  in the direction that makes the finding worse.
- **Severity**: high (the correction strengthens B2-6/C1-1).
- **What I did to break it**: enumerated shells structurally rather than by filename, requiring
  top-level `nodes` and `start_node`, which correctly separates 84 shells from 65 sidecars
  (`.contract.json`, `.lineage.json`, `.narrative.json`). Then ran `check_skeleton.main()`
  in-process over all 84 twice, **replicating `check_promotion_bundle.py`'s exact argv policy**
  (append `--allow-mvp` iff `metadata.production_eligible` is false) rather than a bare
  invocation.
- **Evidence**:

  | Run | Pass | Fail |
  | --- | --- | --- |
  | Default, promotion-bundle argv semantics | **84 / 84** | 0 |
  | Default, bare argv (no `--allow-mvp`) | 81 / 84 | 3 MVP seeds |
  | `--strict`, promotion-bundle argv semantics | **20 / 84** | 64 |

  The "81/84" figure is an artifact of invoking the checker by hand. **The gate as actually wired
  passes 100% of the catalog.** It has never rejected a committed shell and, on this evidence,
  cannot.
- **Strict failure profile** (2,475 `FAIL` lines total, my count): CG-3 1,965, CG-2 344, CG-1 80,
  PL-23 31, PL-24 30, PL-26 6 (= 2,456 strict-escalated), plus walk floor 11, in-degree 7,
  endings floor 1. Identical to the prior review's breakdown, independently derived.
- **What the prior review missed**: the strict bar is not topology-neutral, and this is the single
  most consequential thing I found about it.

  | Topology | Shells | Strict-pass |
  | --- | --- | --- |
  | `branch_and_bottleneck` | 35 | 13 |
  | `open_map` | 13 | **2** (both max fan-out 3, i.e. not hubs) |
  | `sorting_hat` | 10 | 1 |
  | `loop_and_grow` | 9 | 2 |
  | `gauntlet` | 8 | 2 |
  | `time_cave` | 9 | **0** |

  Every `open_map` shell with an actual hub (fan-out >= 5) fails `--strict` on CG-2, whose global
  envelope is `[2, 4]` options (`choice_grammar.py:178-179`) with no hub exemption:
  `the-blackwood-sanatorium` fan 10, `the-hollow-sea` 8, `the-flooded-quarter` 7,
  `the-winter-of-the-wolf-queen` 7, `the-locked-carousel` 7, `the-longwinter-station` 7,
  `the-undertow-season` 7, `the-hundred-door-hotel` 6, `the-midnight-frequency` 6,
  `the-school-garden-mystery` 6. This is precisely the mistake `AL-144` documented and fixed for
  the in-degree cap (topology-aware, hub topologies exempted) and never propagated to CG-2. Under
  `--strict`, **a hubbed `open_map` shell is not buildable and `time_cave` has a 0% demonstrated
  pass rate**, which combined with PL-29's band table (3-5 may declare only `loop_and_grow` or
  `time_cave`) leaves the youngest band almost no proven ground. Corrected 2026-08-30: this read
  "`open_map` is not buildable", which the table three lines above refutes on its own terms, since 2
  of 13 `open_map` shells do pass `--strict`, and the same sentence that introduces them says both
  have max fan-out 3, that is, no hub. The claim is true of the hubbed subset and only of it: every
  `open_map` shell with fan-out >= 5 fails CG-2, and CG-2's `[2, 4]` envelope carries no hub
  exemption. The `time_cave` half of the sentence is unaffected, since that pass count is 0 of 9.

---

## Claim 4: `the-observatory-shift` has 115 decision nodes, 102 offering >=2 choices all pointing at one target, and it passes

- **Verdict**: **CONFIRMED for this shell, and I found a stronger proof than the review had.
  SUBSTANTIALLY OVERGENERALISED as a statement about the catalog.**
- **Severity**: critical for the shell; the catalog-level framing is medium and needs correcting
  in the brief.

### What I did to break it

I ran all four exculpatory hypotheses the brief named.

**(a) "The choices carry effects or conditions."** Every one of the 348 choices in
`the-observatory-shift` has exactly three keys: `id`, `label`, `target`. Not one carries
`condition` or `effects`. This is not a schema limitation: `storybook/models.py:616-625` gives
`Choice` both fields, and `Node` an `on_enter` effect list (`:646`). The shell uses none of them,
and `"variables": []` is empty, so there is nothing in the story for a choice to set or read even
in principle. Zero conditions, zero effects, zero `on_enter`, zero variables.

**(b) "A gather node where flavour options converge by design."** Refuted by the shape. The 102
nodes are not gathers. Node ids run `a_l01 -> a_l02 -> ... -> a_l10`, three identical arms
(`a`/`b`/`c`), each a straight corridor where **every** node offers three labels pointing at the
next corridor node, which does the same:

```text
a_l01  "Read the value out loud as you go."   -> a_l02
       "Copy it silently and move on."        -> a_l02
       "Double-check it a third way."         -> a_l02
a_l02  "Sketch the curve by hand first."      -> a_l03
       "Trust the software's own plot."       -> a_l03
       "Plot it twice to be sure."            -> a_l03
```

Of 118 non-ending nodes, **13 have two or more distinct targets** (`n_first`, `a_split`,
`a_c1..3`, and the `b`/`c` mirrors). 105 have exactly one distinct target; 102 of those dress it
in a menu. 306 of the 348 choices (87.9%) sit in single-target fans; 204 are pure duplicates.

**(c) "The target branches on accumulated state."** Impossible here: all members of a fan share
one target, so the target's `on_enter` is identical whichever label is tapped, and the shell has
no `on_enter` anyway.

**(d) The mechanical proof the review did not have.** `player/state.py:76-82`: `ReadingState`
holds `current_node`, `var_state`, `path` (node ids), `visit_set`, `version`. **The chosen
choice id is recorded nowhere.** `player/engine.py:174-212` `choose()` applies
`choice.effects` (none exist here) and sets `current_node = choice.target`. Two choices with the
same target and no effects therefore produce a **bit-identical** `ReadingState`. This is not an
interpretive judgement about reader experience; the runtime provably cannot distinguish them.

### The decisive experiment the review did not run

I collapsed every single-target fan in `the-observatory-shift` to one choice, changing nothing
else, and re-ran `--strict`:

| | Choices | `--strict` exit | Findings | Reported max in-degree |
| --- | --- | --- | --- | --- |
| As committed | 348 | **0 (clean)** | 0 | 3 (cap 6) |
| Duplicates removed | 144 | **1** | ~30 (CG-1, CG-3) | 1 |

**The phantom choices are load-bearing.** Removing them and nothing else surfaces
`CG-1 grammar: node 'c_l01' starts a run of 10 consecutive single-choice nodes in band '10-13'
(cap 6)`, `105 of 118 non-ending nodes are single-choice, above band '10-13's 50% allowance`, and
CG-3 composed stops of ~945 and ~1155 words against a 150-word ceiling. The book is a corridor
that CG-1 and CG-3 exist to catch, and the duplicate choices are exactly what defeats them:
`choice_grammar.py:265` is `not node.is_ending and len(node.choices) == 1`, which counts
**choices, not distinct targets**. Add a second label to the same target and the node stops being
"single-choice", the run breaks, and the stop never composes.

### The reader-side consequence, which nobody has stated

`player/stops.py:170-177` uses the same predicate: `if len(choices) != 1: return Stop(...,
"branch")`. So the phantom choices do not merely fool the validator's model of the reader, they
**change what the child actually sees**. Without them, one flowed 1,155-word stop. With them,
eleven separate screens, each ending in a three-button menu where all three buttons are the same
button. That is worse than the design CG-1/CG-3 forbid, not a cosmetic difference in how it is
scored.

### Where the review overgeneralised

Catalog-wide I measured 22,165 declared choices and 302 duplicate-target choices (1.36%),
matching the review. But I then asked the question the review did not: do the duplicates in the
*other* shells carry differing `condition`/`effects`?

| Shell | Dup choices | Differentiated by condition/effects | Identical (cosmetic) |
| --- | --- | --- | --- |
| `the-observatory-shift` | 204 | **0** | 204 |
| `the-hollow-crown-gambit` | 15 | 0 | 15 |
| `the-saltmarsh-run` | 12 | 0 | 12 |
| `the-tenfold-siege` | 38 | **38** | 0 |
| `the-serpent-vaults` | 8 | **8** | 0 |
| `the-longwinter-station` | 6 | **6** | 0 |
| `the-sunken-signal` | 6 | **6** | 0 |
| `the-harrowstone-keep` | 5 | 2 | 3 |
| `the-sunken-temple` | 5 | 2 | 3 |
| `the-winter-of-the-wolf-queen` | 2 | 1 | 1 |
| `the-flooded-quarter` | 1 | 1 | 0 |
| **Total** | **302** | **64** | **238** |

**64 of 302 duplicate-target choices are legitimate convergent design**, and they are good:

```text
the-tenfold-siege  a01_m -> a01_res  (3 labels, one target)
  "Spend everything on this stand"   effects: supplies -2, morale +1
  "Spend only what the moment demands" effects: supplies -1
  "Hold the stores back"              effects: morale -1
```

and that state is read downstream: `the-tenfold-siege` has 33 conditions referencing `supplies`
(17), `morale` (12), `breach` (4); `the-serpent-vaults` 17; `the-sunken-signal` 8. Via
`engine.py:277-289` `_is_visible` -> `storybook.condition.evaluate`, those variables gate which
choices are *shown* later. Same next passage, materially different book. This is the pattern the
brief hypothesised, it exists, it works, and four shells use it exclusively.

So the correct statement is: **238 of 22,165 choices (1.07%) are cosmetic, and 85.7% of those are
one shell.** `the-observatory-shift` is not a symptom of a catalog-wide illusion-of-choice
problem; it is a single machine-templated shell (three identical `a`/`b`/`c` arms, uniform
`words=105`) that found the seam. The review's own recommendation text (C1-2a) does say "distinct
targets *or* differing conditions/effects", so the proposed rule is right; the surrounding
narrative is not, and if the brief ships the narrative the team will go looking for a systemic
problem that is not there and will miss the templating problem that is.

`the-hollow-crown-gambit` (15) and `the-saltmarsh-run` (12) are a third, milder case worth keeping
separate: 4-choice nodes with 3 distinct targets where two labels share one **ending leaf**. At
1.7% and 1.9% of their choices that is incidental, and "these two approaches fail the same way"
is defensible; it is also exactly the shape C1-4 shows the topology rules punish.

---

## Claim 5: `validator/consequence.py` detects this and gates nothing

- **Verdict**: CONFIRMED as a statement of fact. The implied conclusion, that it should therefore
  become a gate, is **REFUTED**.
- **Severity**: the fact is medium; promoting it as recommended would be a high-severity mistake.
- **What I did to break it**: read all 322 lines, then ran `scripts/measure_consequence.py` over
  all 84 shells (25.9s) and separately instrumented `measure_consequence` to split forks by
  reconvergence distance.

### What it measures

Two independent quantities per fork *pair*, never pooled: **distance** (nodes on the longer branch
before rejoin, over the *configuration* graph from `walk_configurations`, so state-differentiated
paths stay distinct) and **state delta** (variable names differing on arrival). `is_false_choice`
requires `outcome == "reconverged" and distance <= 1 and not state_delta` (`:118-123`). The
horizon is 12; a fork that does not rejoin within it reports `distance=None` and makes the whole
report `complete=False`; `false_choice_rate` returns `None` for an incomplete report rather than
a number (`:143-155`). The module header states its own status: *"This is a reported statistic,
not a gate... promoting a measure to a rule that blocks a book requires evidence that a reader is
affected, which is W12's job. AL-337 is the record of what happens when a number becomes a gate on
the strength of being computable."* Its only importers are `scripts/measure_consequence.py` and
`scripts/seed_defects.py`. Confirmed: it runs in no workflow.

### Would it flag `the-observatory-shift`? Only in the weakest possible sense

It scores 306 false of 345 forks, median distance **0.0**. But the report is `complete=False`, so
**`false_choice_rate` withholds a number for the flagship exhibit**. The script's own output line
excludes it: *"48 book(s) reported incomplete and are excluded from the verdict."* A gate cannot
be built on a measure that declines to produce a value for 48 of 84 books.

### Why it is not fit to be a gate as proposed

1. **It returns nothing for 57% of the catalog.** 48 of 84 incomplete.
2. **69 of 84 shells declare no variables at all**, so `state_delta` is empty *by construction*
   and `is_false_choice` degenerates to "distance <= 1". The script prints this caveat itself.
   For those books the measure is a statement about graph shape, which PL-18/topology already
   governs.
3. **Its false positives are exactly the shapes `AL-144` already carved out.** The highest scorers
   are hub and loop designs where reconvergence *is* the declared topology:

   | Book | Rate | Topology | Why the score is not a defect |
   | --- | --- | --- | --- |
   | `the-blackwood-sanatorium` | 152/203 (75%) | `open_map` | `AL-144` names this shell: "every room re-enters the hub by design", in-degree 126, deliberately exempted from the in-degree cap |
   | `the-half-hour-call` | 100/138 (72.5%) | `branch_and_bottleneck` | bottleneck merges are the label |
   | `the-seedling-thief` | 33/60 (55%) | `open_map` | cited by the repo as a strict-bar exemplar; a 5-8 hub |
   | `the-last-blue-cup` | 4/10 (40%) | `loop_and_grow` | a loop reconverges; that is what the word means |
   | `the-hundred-door-hotel` | 71/186 (38%) | `open_map` | hub |

   The review cites `the-seedling-thief` at 55% and `the-last-blue-cup` at 40% as evidence that
   the *reference exemplars* are riddled with cosmetic choice. They are not. They are an
   `open_map` and a `loop_and_grow`, and their reconvergence is the band-mandated design.
   `AL-144` established with measurements that a corpus-wide structural threshold blind to
   topology encodes the assumption that one mechanism produced the distribution. The
   recommendation's "per-cell budget" is the wrong axis: `the-blackwood-sanatorium` (75%,
   `open_map`, legitimate) and `the-long-thaw` (248/492 = 50%, `branch_and_bottleneck`, probably
   not) sit in the **same cell** (16+/medium). A per-cell budget cannot separate them; only a
   per-topology one can, and that is the lesson already paid for.

### The narrow rule that *is* safe, which nobody proposed

Split the measure by distance. I instrumented this:

| Signal | Forks | Books affected |
| --- | --- | --- |
| distance **0**, no state delta (both options target the same node) | **352** | **9** |
| distance **1**, no state delta | 2,430 | 58 |

The distance-0 signal is surgical, unambiguous, and needs no horizon, no walk, and no
completeness caveat: it is decidable from the raw JSON. 306 of the 352 are
`the-observatory-shift`. **Gate on distance-0-with-no-state-delta (equivalently, C1-2a's
duplicate-target rule); never gate on the pooled `false_choice_rate`.** The distance-1 population
is where every legitimate hub, loop, and bottleneck lives.

---

## Claim 6 (C1-3): `_build_graph` collapses parallel edges while `max_indegree` counts them

- **Verdict**: CONFIRMED, and sharper than stated.
- **Severity**: critical.
- **What I did to break it**: executed both functions on the shell and read both sources.
- **Evidence**: `policy.py:364-371` `_build_graph` returns an `nx.DiGraph` (not `MultiDiGraph`),
  so `graph.add_edge(node.id, choice.target)` is idempotent. Measured on
  `the-observatory-shift`: **144 edges over 145 nodes from 348 declared choices**, and
  **0 nodes with graph in-degree >= 2**, i.e. a pure tree. `topology.admissible_topologies`
  branches on `reconverging = sum(1 for n in graph if graph.in_degree(n) >= 2)` and therefore
  returns `{TIME_CAVE, GAUNTLET, SORTING_HAT}`; declared `sorting_hat` passes PL-18. Meanwhile
  `check_skeleton.max_indegree` counts raw choice targets and its docstring says so explicitly:
  *"Parallel edges count separately: two choices on one node targeting the same successor
  contribute 2, because each is a corridor funnelling in."* It reports 3 against a cap of 6.
- **The sharpening the review missed**: the two rules do not merely disagree, **the checker prints
  both contradictory readings in the same report**. On the committed shell it prints
  `reconvergence: max in-degree 3 (hard cap 6 for 10-13 sorting_hat)` while PL-18 is satisfied by
  `reconverging == 0`. After my dedupe the same line reads `max in-degree 1`. The reported
  in-degree of 3 was **100% phantom**, and the cap of 6 means an author has room for up to six
  duplicate labels per node before anything notices. There is no test asserting
  `sum(len(n.choices)) == graph.number_of_edges()`; I looked.

---

## Claim 7 (C1-4): at 3-5 and 5-8 an acyclic graph with any merge has no legal topology

- **Verdict**: CONFIRMED by construction, and **worse than stated in a way that changes the
  recommendation's sequencing**.
- **Severity**: critical.
- **What I did to break it**: I did not reason from the tables. I built the artifact. Starting
  from `skeletons/3-5/the-clover-and-the-butterfly.json` (a 3-5 `time_cave` that passes the
  default gate cleanly), I made the single mildest possible merge: re-pointed one choice so that
  **two paths share one ending leaf**, and deleted the now-orphaned ending. 19 nodes, still
  acyclic, no other change. Then I declared each of the six topologies in turn and ran the
  checker.

| Declared topology | Result |
| --- | --- |
| `time_cave` | BLOCKED, PL-18 (`admissible: ['branch_and_bottleneck', 'gauntlet']`) |
| `loop_and_grow` | BLOCKED, PL-18 |
| `open_map` | BLOCKED, PL-29 + PL-18 |
| `branch_and_bottleneck` | BLOCKED, PL-29 (`band '3-5' may not declare ...`) |
| `gauntlet` | BLOCKED, PL-29 |
| `sorting_hat` | BLOCKED, PL-29 + PL-18 |

Six for six. `admissible_topologies` returns `{BRANCH_AND_BOTTLENECK, GAUNTLET}`;
`BAND_TOPOLOGIES['3-5']` is `{LOOP_AND_GROW, TIME_CAVE}`; the intersection is empty. PL-18's
message prints the admissible set verbatim, so the author is handed a two-item menu of which
neither item is legal at their band, exactly as the review said.

I then verified the escape: add a **back-edge** (`n_gate -> n_grass`), making the graph cyclic,
declare `loop_and_grow`, and it exits **0, clean**. So the rules actively push a 3-5 picture-book
author to put a *loop* in the story rather than let two paths share an ending.

- **What the prior review missed, and it is important**: **this is a DEFAULT-gate trap, not a
  `--strict` one.** PL-18 and PL-29 are `Severity.ERROR` and produce `FAIL gate`, exit 1, on a
  bare invocation. Confirmed: my merged shell exits 1 with no flags. Consequently PL-18/PL-29
  appear **zero times** in the 64 strict failures I collected, because every committed shell
  already satisfies them. That has a direct consequence for the recommendation, below.

---

## Claim 8 (C1-5): every strict-blocking finding is labelled "advisory only", 2,456 of 2,456

- **Verdict**: CONFIRMED, exactly.
- **Severity**: high, and it is the cheapest fix in the cluster.
- **What I did to break it**: counted mechanically over my own strict run rather than trusting a
  quoted figure, and checked whether any escalated finding had been rewritten.
- **Evidence**: 2,475 `FAIL` lines total; 2,456 are `FAIL strict:`; **2,456 of 2,456 contain the
  string "advisory"**. `check_skeleton.py:801-808` re-emits `finding.message` unmodified after
  matching `finding.rule_id` against `STRICT_BLOCKING_WARNINGS`. Representative line, verbatim
  from my run:

  ```text
  FAIL strict: CG-1 advisory is blocking for a newly drafted skeleton: CG-1 grammar: node
  'c_l01' starts a run of 10 consecutive single-choice nodes in band '10-13' (cap 6) in story
  'sk_observatory_shift' (advisory only, new-content grammar per ADR-011 section 10); composed
  stop is ~1155 words, above the 150-word words-per-stop ceiling
  ```

  One line saying "is blocking" and "advisory only" about the same rule.
- **What the prior review missed**: nothing material. This one is solid and I could not dent it.

---

# Recommendation review

> "Pass `--strict` in `check_promotion_bundle.py` after fixing PL-18/PL-29; publish the 64-shell
> remediation backlog; promote `consequence.py` to a gate."

## Sequencing: the stated prerequisite is factually wrong

Fixing PL-18/PL-29 is **not** a prerequisite for landing `--strict`, and believing it is will
delay a zero-risk change behind a hard one.

- PL-18 and PL-29 are ERROR-severity rules in the **default** gate. They already block, today,
  in `check_promotion_bundle.py`. Verified by construction above (exit 1, no flags).
- `--strict` escalates a disjoint set: PL-19/23/24/25/26, L1-7, CG-1..CG-3, the random-walk
  satisfying-ending floor, the in-degree cap, the depth-qualified endings floor.
- Empirically: **PL-18 and PL-29 appear zero times in the 64 strict failures.** The two changes
  do not interact at all on the committed catalog.

They are independent workstreams. PL-18/PL-29 is an **authoring-cost** fix (the review's own S-1
evidence shows it terminating four of fifteen tool-assisted runs); `--strict` is a **merge-bar**
fix. Nothing breaks if `--strict` lands first.

## What actually breaks if `--strict` lands first, and what does not

The review implies a catastrophe it did not verify. I checked the scoping.

**Does not break.** `.github/workflows/skeleton-promotion.yml:92-113` computes
`git diff --name-only --diff-filter=AM ... -- 'skeletons/**'` and passes only changed shells. The
prover **never runs over the catalog**. So landing `--strict`:

- does not delist, unpublish, or invalidate a single committed shell;
- does not empty a single cell (verified: 18 production cells, all still populated 4-6);
- does not touch matching, `production_eligible`, or any in-flight request, because
  `story_requests/authoring_plan.py` matches on catalog metadata and has no notion of the
  checker's exit code;
- does not affect any already-published book.

**Does break, and this is the real hazard the review understated.** Any PR that touches one of
the 64 grandfathered shells becomes unmergeable. That includes exactly the maintenance the repo
already does: the 2026-08-01 valence re-tag (named in `check_promotion_bundle.py`'s own comments),
theme-contract fixes, cover backfills, a typo in a `<<FILL>>` directive. A one-character edit to
`the-ashfall-expedition` would demand clearing **100 findings** first.

**And the backlog is not a backlog.** I profiled all 64:

- **CG-3 fires in 64 of 64.** CG-2 in 55, CG-1 in 33.
- **Zero** of the 64 fail only on arithmetic/metadata rules (PL-23 clock, PL-24 ending mix).
  There is no cheap tier.
- Median 36 findings per shell; worst `the-ashfall-expedition` 100,
  `the-winter-of-the-wolf-queen` 90, `the-skyrail-heist` 80.
- CG-3 is a words-per-stop ceiling and CG-2 an options-per-fork envelope; clearing them means
  re-cutting the node graph and re-budgeting words, i.e. re-authoring, not editing.

A rule that rejects 100% of the corpus it governs deserves the same scrutiny the corpus gets.
Two things are true at once here, and the recommendation should say both: `choice_grammar.py:195-217`
records that the 3-5 and 5-8 CG-3 ceilings were added **2026-08-18, four days ago**, knowing it
cost "160 findings across the committed young bands", justified because two shells authored to the
bar sit exactly at the ceiling. So the failure is substantially **"the bar was raised after the
catalog was built and the catalog was never migrated"**, not "64 books are defective". That is the
honest framing and it is the one that makes the rollout decision. Separately, CG-2 has a genuine
calibration defect (no hub exemption; see Claim 3), and demanding remediation against a defective
rule would destroy legitimate `open_map` designs.

## The rollout I would actually run

**Phase 0, this week, zero risk, no gate change.** Fix the C1-5 message formatting. In strict mode
rewrite the escalated finding instead of quoting it: strip "(advisory only)", say "BLOCKING under
--strict", and append the computable repair (PL-23: "set `metadata.estimated_minutes` to N";
PL-24: "add K positive-valence endings"). This is a formatting change to
`check_skeleton.py:801-808` that plausibly recovers a third of observed tool-assisted authoring
failures. It should not be sequenced behind anything.

**Phase 1, the flagship quality win, and it does not need `--strict` at all.** Add the
duplicate-target rule as **blocking in the default gate**: a non-ending node's choices must have
>= 2 distinct targets, or differ in `condition`/`effects`. **Blast radius under the proposed rule:
4 of 84 shells**, three of them with a one-node fix. The **9 shells, 352 fork-pairs, 87% of them
one shell** measured here is the *raw duplicate-target signal*, before the rule's own
condition/effect exemption is applied, and is not the number of shells that would fail: exclude the
64 legitimate differentiated choices by construction and `the-tenfold-siege`,
`the-serpent-vaults`, `the-sunken-signal` and `the-longwinter-station` are untouched. Corrected
2026-08-30: the pre-filter figure was being reported as the blast radius. The post-filter number
comes from V6, which measures 11 of 84 shells carrying duplicate-target choices and **4 of 84**
failing once "two distinct targets *or* differing conditions/effects" is applied. Note that V6's
pre-filter count is 11 shells and this report's is 9; the two are measuring different units
(V6 counts shells carrying duplicate-target *choices*, this report counts shells carrying
duplicate-target *fork-pairs*) and the discrepancy wants one recomputation under a single stated
unit rather than a choice between them. Then fix or delist `the-observatory-shift`, and re-derive
PL-17's decision floor over real decisions. For the structural half, switch `_build_graph` to a
`MultiDiGraph` with `admissible_topologies` counting distinct predecessors, so the two readings
cannot diverge again. Do **not** add `sum(len(n.choices)) == graph.number_of_edges()` as an
invariant test: this same report documents 64 legitimate parallel choices that differ in
`condition`/`effects`, and every one of them makes that equality false by construction, so the test
would fail on a correct catalog. It was proposed here and is withdrawn as of 2026-08-30; the
`MultiDiGraph` change is the part that actually closes the seam.

**Phase 2, `--strict` on ADDED shells only.** `git diff --diff-filter=A` for brand-new shells gets
`--strict` unconditionally. Blast radius: **zero**, because no committed shell is added. This is
literally what the flag was built for ("the bar for NEWLY DRAFTED skeletons",
`check_skeleton.py:17`) and it closes the hole immediately. Modified shells stay on the default
gate in this phase.

**Phase 3, `--strict` on MODIFIED shells behind a shrink-only allowlist.** Pin each of the 64
shells to its current finding count (I have the per-shell numbers) and fail any PR that raises a
shell's count. The `check_incell_clones.ALLOWLIST` discipline already in the repo. This makes the
catalog monotonically non-worsening without blocking maintenance, which is the property that
actually matters.

**Phase 4, before demanding remediation, fix the rules that are wrong.** Give CG-2 a hub exemption
mirroring `AL-144`'s in-degree treatment, or `open_map` is dead. Resolve PL-18/PL-29 (report the
reconverging node ids rather than a verdict; intersect with PL-29 before printing; and seriously
consider excluding **ending** nodes from the reconvergence count, which by itself would fix my
constructed 3-5 case and the `hollow-crown-gambit`/`saltmarsh-run` shared-ending duplicates).
Only then publish a remediation backlog, ordered by findings-per-shell, and expect re-authoring
rather than editing.

**Phase 5, close the bypasses.** `mutation/acceptance.py:669` and
`scripts/parameterize_skeleton.py:543` must pass `enforce_grammar=True` at the same time as the
promotion gate, or new work routes around it.

**Never, until cell coverage recovers.** Do not gate `production_eligible` or request matching on
strict. Measured: every one of the 18 production cells falls from 4-6 shells to **1-2**. Given
C1-7's finding that a family exhausts a cell in 4-6 requests, this would exhaust a cell in one or
two and turn the anti-clone floors into a hard denial of service. This distinction, promotion gate
versus eligibility gate, is absent from the recommendation and is the single most dangerous thing
about it.

## Is promoting `consequence.py` to a blocking gate safe? No, not as written

Rejected for the reasons in Claim 5: it returns `None` for 48 of 84 books, `state_delta` is empty
by construction for 69 of 84, and its top scorers are legitimate `open_map` and `loop_and_grow`
designs including a shell `AL-144` already exempted by name. A per-cell budget cannot separate
`the-blackwood-sanatorium` from `the-long-thaw` because they share a cell.

**Threshold I would accept**: none on the pooled rate. Gate on the **distance-0, no-state-delta**
sub-signal only (352 forks, 9 books, decidable from raw JSON, no horizon, no completeness caveat),
which is the same rule as Phase 1's duplicate-target check arrived at from the other direction.
Keep the pooled `false_choice_rate` as a **reported statistic segmented by topology**, and revisit
promotion only when W12 supplies reader evidence, which is precisely what
`consequence.py:22-27` already says and what `AL-337` is the scar tissue for. The module is right
about itself.

---

# What everyone missed

1. **The gate as wired passes 84/84, not 81/84.** The "3 MVP seed failures" only exist under a
   bare invocation; `check_promotion_bundle.py` supplies `--allow-mvp` for exactly those shells.
   The promotion gate has never rejected a committed skeleton.

2. **`check_promotion_bundle.py` calls its non-strict path "the strict check"** (`:311-312`), with
   a passing test asserting that "strict" is re-armed. The vocabulary collision is the likely
   reason a missing `--strict` survived review, and renaming it is part of the fix.

3. **CG-2 has no hub exemption, so `--strict` kills `open_map`.** Every `open_map` shell with a
   hub fan >= 5 fails; the only two that pass have max fan 3. `time_cave` is 0 for 9. `AL-144`
   solved exactly this problem for the in-degree cap and the lesson was never propagated. Landing
   `--strict` without fixing CG-2 does not raise the bar, it deletes two topologies.

4. **C1-4's trap is in the default gate, not `--strict`,** so it is not a prerequisite for the
   `--strict` change and should be scheduled on its own merits. Conversely it is *already*
   costing authors today, which makes it more urgent than the review implies, not less.

5. **The phantom choices change what the child sees, not just what the validator computes.**
   `player/stops.py:170` uses `len(choices) != 1`, so `the-observatory-shift` renders as 11
   corridor screens each with three identical buttons instead of one flowed passage. The defect
   is in the product, not only in the measurement.

6. **`ReadingState` records no choice id** (`player/state.py:76-82`), which converts "these
   choices are cosmetic" from a critical opinion into a mechanical fact about the runtime. This
   is the strongest single piece of evidence in the cluster and it was not used.

7. **64 of 302 duplicate-target choices are good design, and four shells depend on it.** Any rule
   written to the review's *narrative* rather than its *stated rule text* would break
   `the-tenfold-siege`, `the-serpent-vaults`, `the-sunken-signal` and `the-longwinter-station`.

8. **The semantic-distinctness instrument the review says does not exist is half-built.**
   `scripts/check_decision_overlap.py` reads a `decisions` block from contract sidecars carrying
   `action`, `action_family`, `target_role`, `tradeoff`, `consequence` per choice id, with
   bipartite option alignment already implemented. It scores repetition *between* books; pointing
   the same taxonomy at options *within* one fork is a small change to existing code, not a new
   rule. `the-observatory-shift` has no contract sidecar, which is why it is invisible to it, and
   that is itself worth a rule: a `production_eligible: true` shell with no contract sidecar
   (already flagged in `AL-151`/`UW-C88` and still open).

9. **`the-observatory-shift` is machine-templated and no rule notices.** Three byte-identical arm
   structures (`a`/`b`/`c`), uniform `words=105`, corridor ids `*_l01..l10`, `*_s1_01..08`. The
   in-cell clone and structural-distance checks compare *across* shells; nothing measures a
   shell's *internal* self-similarity. That is the defect class this shell actually represents,
   and it is a better target than "cosmetic choice" because it is what produced the cosmetic
   choice.

10. **Nobody has asked what happens to books already generated from an affected shell.** The
    duplicate-target rule is a skeleton-stage rule. Any published Storybook bound to
    `the-observatory-shift` inherits its dead menus, and no path re-runs the skeleton gate over
    shipped inventory: `api/remoderate.py:83` states that re-moderation *reports* on a published
    book rather than re-gating it. I did not query a live database, so I cannot say how many such
    books exist; the point is that the recommendation contains no answer for the case where the
    number is greater than zero, and a catalog-only fix would leave them in readers' hands.
