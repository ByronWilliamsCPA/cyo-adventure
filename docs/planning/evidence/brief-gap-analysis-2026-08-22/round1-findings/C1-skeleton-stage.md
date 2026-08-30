# C1, Skeleton development and skeleton checking (brief 3.1, 3.2, 4.2)

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `scratchpad/runstrict.py`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.

Component audit, 2026-08-22. Scope: `scripts/check_skeleton.py`, `scripts/check_graph_structure.py`,
`scripts/generate_drafting_brief.py`, `validator/{band_profile,policy,topology,walk,choice_grammar,
consequence,layer1,layer2}.py`, `src/cyo_adventure/mutation/`, `scripts/{mutate,parameterize}_skeleton.py`,
`scripts/check_promotion_bundle.py`, `.github/workflows/skeleton-promotion.yml`, the `skeletons/`
catalog (84 shells / 15,470 nodes), `.claude/skills/cyo-author/`, and the S-1 evidence in
`.worktrees/brief-evidence/docs/planning/evidence/skeleton-author-vendors/`.

**Retraction.** An earlier draft of this audit reported the S-1 evidence, the sourcing test plan,
`S-0`..`S-5`, and `AL-510`..`AL-514` as missing. That was an artifact of the branch I was given.
They exist, I have read them, and every finding below that touches section 4.2 is now grounded in
the run records rather than in their absence.

Everything below was measured on this tree. Reproduction commands are given per finding.

Catalog measurements used throughout (all reproduced in this session):

| Measurement | Value |
| --- | --- |
| Non-sidecar shells / nodes | 84 / 15,470 (brief says 61 / 11,458, stale) |
| Offered cells | 18; 4-6 shells each; 81 production-eligible on-matrix |
| `check_skeleton.py` **default** pass | 81 of 84 (the 3 failures are MVP seeds needing `--allow-mvp`) |
| `check_skeleton.py --strict` pass | **20 of 84** |
| Strict-blocking findings in the catalog | 2,456 (CG-3 1,965, CG-2 344, CG-1 80, PL-23 31, PL-24 30, walk floor 11, in-degree 7, PL-26 6, endings floor 1) |
| Declared choices vs distinct graph edges | 22,165 vs 21,863 (302 duplicate-target choices) |
| Fork-consequence false-choice rate (`measure_consequence.py`) | mean 18.6%, max 72.5% |
| In-cell structural distance | min 0.00047, p05 0.155, median 0.387 against `TAU_CELL` 0.05 |

---

## C1-1: `--strict`, the documented authoring bar, is enforced by no CI job, including skeleton promotion
- **Severity**: critical
- **Category**: tooling
- **Locus**: `scripts/check_promotion_bundle.py:322-330`; `.github/workflows/skeleton-promotion.yml:117-125`
- **Problem**: Brief 3.2 states "`scripts/check_skeleton.py --strict` is the authoring bar", and 3.1
  states CI "re-proves every changed skeleton from scratch". It does not. `check_promotion_bundle.py`
  builds `skeleton_argv = [str(shell_path)]` and appends only `--allow-mvp`; `--strict` is never
  passed by any caller in the repo. `grep -rn "check_skeleton" .github/` returns one workflow, which
  calls the prover, which calls the loose default. The gap is not theoretical: the committed catalog
  passes the default at 81/84 and `--strict` at 20/84. A newly authored skeleton carrying all of
  PL-19/23/24/25/26, CG-1/2/3, a 0% satisfying-walk probability, an over-cap funnel, and a failed
  depth-qualified endings floor merges green. Two further loose-gate call sites compound it:
  `mutation/acceptance.py:669` runs `run_gate(candidate)` (Stage 1) and
  `scripts/parameterize_skeleton.py:543` runs `run_gate(parameterized)`, both the non-strict gate,
  neither with `enforce_grammar=True`. So the mutation flywheel and the parameterization migration
  can each promote work that the bar rejects.
- **Why it matters for the goal**: every downstream quality argument in the brief ("the tool-assisted
  regime passes the strict bar", "CI re-proves from scratch", "promotion is a reviewed PR against the
  bar") rests on a gate that is not wired. The catalog is the product's capital; the only automated
  defence of that capital's quality is off.
- **Recommendation**: pass `--strict` in `check_promotion_bundle.py` for any shell whose path is under
  `skeletons/` and which is not in an explicit, shrink-only grandfather list (the same discipline
  `check_incell_clones.ALLOWLIST` already uses). Add the 64 currently-failing shells to that list with
  their finding counts, so the list can only shrink. Same for `mutation/acceptance.py` Stage 1 and
  `parameterize_skeleton.py` step 5.
- **How to check I'm right**: `grep -rn '\-\-strict' .github/ scripts/check_promotion_bundle.py`
  (no hit in either), then run the two totals:
  `for f in skeletons/*/*.json; do ...; done`, or reuse my harness at
  `scratchpad/runstrict.py` (`uv run python scratchpad/runstrict.py --strict` → 20 pass;
  without `--strict` → 81 pass).

---

## C1-2: nothing detects a false choice, and the catalog contains a strict-passing book that is 59% false choices
- **Severity**: critical
- **Category**: rule gap
- **Locus**: `skeletons/10-13/the-observatory-shift.json`; `src/cyo_adventure/validator/policy.py:1501-1516`
  (`_decision_node_ids`); `src/cyo_adventure/validator/consequence.py:1-27` (header, esp. :23)
- **Problem**: The checker's definition of a decision is `not node.is_ending and len(node.choices) >= 2`.
  It never reads where the choices go. `the-observatory-shift` (10-13/medium/prose, 145 nodes,
  `sorting_hat`) declares 348 choices across 115 decision nodes; **102 of those 115 nodes offer two or
  three differently-worded labels that all point at the same successor**, unconditioned:

  ```text
  a_l01  "Read the value out loud as you go."  -> a_l02
         "Copy it silently and move on."       -> a_l02
         "Double-check it a third way."        -> a_l02
  ```

  204 of its 348 choices (58.6%) are duplicate edges. It passes `--strict` with zero findings
  ("ok: skeleton passes gate and brief checks"). Catalog-wide, 11 books carry 302 such choices.
  Beyond exact-duplicate targets, `measure_consequence.py` (which does detect immediate reconvergence
  with no state delta) puts the false-choice rate at 72.5% for `the-half-hour-call`, 55.0% for
  `the-seedling-thief`, 44.0% for `the-locked-carousel`, 40.0% for `the-last-blue-cup` and
  `the-lantern-keepers-list`, and **all five of those pass `--strict`**. `the-seedling-thief` and
  `the-last-blue-cup` are the two shells the codebase cites as its reference strict-bar exemplars.
  The instrument exists and is deliberately not a gate: `consequence.py`'s own header says "This is a
  reported statistic, not a gate", it is imported only by `measure_consequence.py` and `seed_defects.py`,
  it is absent from `generate_drafting_brief.py`, and it runs in no workflow.
  Nothing anywhere measures: whether two labels on one node are semantically distinct; whether a label
  predicts its outcome; whether a branch that reconverges at the next node counts as a branch; or how
  consequence is distributed across a book's forks.
- **Why it matters for the goal**: agency is the entire product proposition of a choose-your-own
  adventure. A child reading `the-observatory-shift` makes 115 "decisions" of which 102 change nothing ,
  the purest possible illusion of choice, and every automated defence in the programme certifies it as
  the best class of shell the project produces. The brief's finding 2 ("a passing gate is not quality")
  is understated: here the gate is passed *by means of* the defect.
- **Recommendation**: two rules, both cheap and deterministic. (a) **Blocking**: a decision node's
  choices must have at least two distinct targets *or* differing conditions/effects, a node whose
  choices all lead to the same configuration is not a decision and must not be counted by PL-17/25/26.
  (b) **Strict-blocking with a per-cell budget**: cap the share of forks that `consequence.py` scores
  as false choices (distance <= 1 and empty state delta). Publish both in `generate_drafting_brief.py`.
  Re-derive PL-17's decision floor over *real* decisions after (a) lands.
- **How to check I'm right**:
  `uv run python scripts/check_skeleton.py skeletons/10-13/the-observatory-shift.json --strict` (exit 0),
  then `uv run python -c "import json;d=json.load(open('skeletons/10-13/the-observatory-shift.json'));
  print(sum(1 for n in d['nodes'] if len(n.get('choices') or [])>=2 and
  len({c['target'] for c in n['choices']})<len(n['choices'])))"` → 102. Then
  `uv run python scripts/measure_consequence.py skeletons/*/*.json | head -20`.

---

## C1-3: the topology classifier and the reconvergence cap disagree about what an edge is, and phantom choices thread exactly between them
- **Severity**: critical
- **Category**: rule gap
- **Locus**: `src/cyo_adventure/validator/policy.py:364-371` (`_build_graph`);
  `src/cyo_adventure/validator/topology.py:41-42`; `scripts/check_skeleton.py:549-571` (`max_indegree`)
- **Problem**: `_build_graph` builds an `nx.DiGraph`, which silently collapses parallel edges. For
  `the-observatory-shift`, 348 declared choices become **144 edges over 145 nodes**, a tree, with
  `reconverging == 0`, so `admissible_topologies` returns `{time_cave, gauntlet, sorting_hat}` and
  PL-18 is satisfied. Meanwhile `check_skeleton.max_indegree` *does* count parallel edges (its docstring
  says so explicitly: "two choices on one node targeting the same successor contribute 2"), and reports
  max in-degree 3 against a cap of 6, so the reconvergence rule also passes, and passes *because* the
  fan is fake. The result is a documented, exploitable seam: adding duplicate-target choices raises
  PL-17 decision breadth and lowers PL-26 nodes-per-decision density while leaving the graph a pure tree
  for PL-18/PL-29 and staying inside the in-degree cap. This is the cheapest legal way to satisfy the
  density rules at the bands where `sorting_hat`/`time_cave` are the only declarable acyclic labels, and
  the catalog shows an author found it.
- **Why it matters for the goal**: the seam converts the reader-experience rules into an incentive to
  manufacture fake agency. It also means PL-18's verdict, the rule the S-1 evidence shows costs the most
  authoring budget, is computed on a graph that is not the graph the author wrote.
- **Recommendation**: make the edge multiplicity explicit and consistent. Either build a `MultiDiGraph`
  and have `admissible_topologies` count in-degree over distinct predecessors (behaviour unchanged) while
  a new rule reports duplicate-target fans, or normalise: reject duplicate-target choice sets outright
  (C1-2a) so the two readings can never diverge. Add a test asserting
  `sum(len(n.choices)) == graph.number_of_edges()` for every committed shell.
- **How to check I'm right**:
  `uv run python -c "from cyo_adventure.validator.policy import _build_graph; from
  cyo_adventure.storybook.models import Storybook; import json;
  s=Storybook.model_validate(json.load(open('skeletons/10-13/the-observatory-shift.json')));
  g=_build_graph(s); print(g.number_of_edges(), sum(len(n.choices) for n in s.nodes),
  sum(1 for n in g if g.in_degree(n)>=2))"` → `144 348 0`.

---

## C1-4: PL-18 and PL-29 make a whole class of graph undeclarable, and PL-18's message names a set PL-29 forbids
- **Severity**: critical
- **Category**: rule gap / authoring ergonomics
- **Locus**: `src/cyo_adventure/validator/topology.py:15-71` and `:93-127` (`BAND_TOPOLOGIES`);
  `src/cyo_adventure/validator/policy.py:614-631` (PL-18 message)
- **Problem**: `admissible_topologies` is a three-way switch. Any acyclic graph with **one**
  reconverging node returns `{branch_and_bottleneck, gauntlet}`. `BAND_TOPOLOGIES` permits neither at
  3-5 or 5-8. Intersection is therefore empty: at the two youngest bands an acyclic story in which two
  branches rejoin, including one where two paths share an ending leaf, has **no legal topology label
  at all**. The author's only escapes are a pure tree (exponential node cost) or a back-edge.
  PL-18's message makes this worse rather than better: it prints the admissible set and nothing else, so
  an author at 5-8 is told `admissible: ['branch_and_bottleneck', 'gauntlet']`, a menu of which *no
  member* is band-legal. The S-1 tool-assisted records show exactly this loop terminating four of
  fifteen failures (`A__r1__claude-sonnet-subagent`, `A__r2__claude-sonnet-subagent`,
  `A__r1__moonshot-kimi-k3-modal`, `A__r2__deepseek-v4-pro`), each burning the full ten-invocation cap;
  `tools-meta.json` annotates the Sonnet pair "built reconvergent graphs while declaring time_cave...
  its terminal-convergence designs shared ending nodes, which the checker counts as reconvergence, so
  no design read as a tree". `AL-514` records the same. In the blind condition PL-18 is the joint-most
  frequent terminal rule (5 of 19 failures). The trap is not confined to the young bands: PR #730's
  own commit message records that a `sorting_hat` at 8-11/short "needs about 1,640 nodes against a
  100-node budget" (857 after the CG-2 variance allowance), i.e. the label is unbuildable there too.
- **Why it matters for the goal**: this is the single largest measured drain on skeleton-authoring
  budget, it selects against the shapes the format actually wants (`UW-C275` records the owner question:
  "the strict bar makes reconvergence effectively compulsory above 3-5, so craft deliberately rejected
  what the architecture mandates"), and it homogenises the catalog, 35 of 84 shells are
  `branch_and_bottleneck` and there is not one `time_cave` above 8-11.
- **Recommendation**: (a) Make PL-18 report the *evidence*, not the verdict: name the reconverging
  node ids (or the back-edge) that excluded the declared label, e.g. "`time_cave` requires zero
  reconvergence; nodes `e3`, `e7` have in-degree 2 (predecessors ...)". (b) Intersect with PL-29 before
  printing: never offer a topology the band forbids; when the intersection is empty say so and name the
  structural change required. (c) Reconsider the rule itself, a single shared ending leaf should not
  reclassify a tree; consider excluding ending nodes from the reconvergence count, or admitting
  `time_cave` with a small reconvergence tolerance.
- **How to check I'm right**: run my derivation ,
  for each band, intersect `admissible_topologies` output for (cyclic / pure-tree / any-merge) with
  `BAND_TOPOLOGIES[band]`; 3-5 and 5-8 give `NONE` for the any-merge class. Then read
  `.worktrees/brief-evidence/docs/planning/evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/records/A__r1__claude-sonnet-subagent.json.record.json`
  (`last_feedback` is the PL-18 line naming `branch_and_bottleneck`/`gauntlet` at a 5-8 cell) and
  `tools-meta.json`.

---

## C1-5: every strict-blocking finding tells the author it is "advisory only", 2,456 of 2,456
- **Severity**: critical
- **Category**: authoring ergonomics
- **Locus**: `scripts/check_skeleton.py:98-110` (`STRICT_BLOCKING_WARNINGS`) and `:801-808` (the strict
  escalation loop); message sites `validator/policy.py:1311,1434,1461,1477`,
  `validator/choice_grammar.py:396,426,488,513,596,659`
- **Problem**: `--strict` escalates six advisory rules to blocking by matching `finding.rule_id` against
  a set, then re-emits the finding's **own unmodified message**. Every one of those messages ends in
  "(advisory only)". Measured over the committed catalog: 2,456 strict-blocking findings, 2,456 of which
  contain the string "advisory". A single line therefore reads:
  `FAIL strict: PL-23 advisory is blocking for a newly drafted skeleton: PL-23 clock: ... (advisory only)`.
  The S-1 records show the cost. `D__r2__deepseek-v4-flash` burned all ten checker invocations and
  terminated on **PL-23 alone**, while the same checker output, two lines below the finding, printed
  `clock: declared estimated_minutes 3 vs derived 2`, i.e. the exact one-integer repair.
  `A__r3__claude-haiku-subagent` burned ten and terminated on PL-23 + PL-24 + CG-1 + CG-3, all four of
  which say "advisory only". PL-23 is the single most frequent terminal rule in the tool-assisted
  condition (6 of 15 failures) despite being pure arithmetic with the answer printed. `AL-512` records
  the sibling defect (`FAIL cell: not production_eligible`, a message "no author can fix", burning a
  whole repair budget).
- **Why it matters for the goal**: brief F3 identifies authoring regime as the largest measured quality
  lever, and F7 identifies checker-loop waste as a first-order cost. This is the cheapest available
  improvement to both: a message-formatting change plausibly recovers a third of the tool-assisted
  failures at zero risk.
- **Recommendation**: in strict mode, rewrite the escalated finding rather than quoting it, strip
  "(advisory only)", state "BLOCKING under --strict", and append the repair when it is computable
  (PL-23: "set `metadata.estimated_minutes` to N"; PL-24: "add K positive-valence endings";
  CG-3: "split stop <ids> or reduce `words=`"). Rank order for this work, from the observed terminal
  frequencies: PL-23 (6) > L1-7 (6) > PL-18 (4) > L1-3 (3) = CG-3 (3) > CG-1 (2) = PL-25 (2).
- **How to check I'm right**: `uv run python scratchpad/runstrict.py --strict` then count
  `FAIL strict:` lines containing "advisory" (2456/2456). Read
  `runs/e1r3-tools-2026-08-21/records/D__r2__deepseek-v4-flash.json.record.json`, `last_feedback`
  holds both the PL-23 failure and the derived clock that answers it.

---

## C1-6: the decisional layer is baked into the shell, so F5's "never reuse decisions" is contradicted by the artifact
- **Severity**: high
- **Category**: reuse leakage
- **Locus**: `skeletons/8-11/the-locked-carousel.json` (and every shell); `scripts/check_decision_overlap.py`;
  `.claude/skills/cyo-author/SKILL.md:41-48`
- **Problem**: measured across all 84 shells: **22,165 choice labels totalling 127,365 words**, and
  **15,470 `beats=` directives totalling 464,631 words** (mean 30 words of narrative direction per node).
  Slot tokens are **1.9% of label words and 3.2% of beat words**; 47 of 84 shells have a `.contract.json`
  and 37 have none at all. So per-request "binding" replaces roughly one word in fifty. A representative
  shell node reads
  `label: "Pull on your coat, pocket {KEEPSAKE}, and slip out into the moonlight."` and
  `beats='...{HERO} decides someone who loves {MONUMENT} should find out what is wrong with it, tonight'`.
  Every book filled from that shell offers the same decisions, in the same order, at the same positions,
  with the same stakes, the same ending mix, and the same pacing, the exact defect brief section 1
  names as the one that matters. `cyo-author/SKILL.md` forbids the author from noun-substituting
  ("prose that would fit any theme after a find-and-replace is a defect") while the theme contract makes
  noun substitution the architecture. Compounding this: `check_decision_overlap.py`, described in its own
  header as "the instrument the diversity program has been missing", reads a `decisions` block ,
  and **0 of the 47 committed contracts declare one**, so running it on any real pair prints
  "no node declares a multi-option decisions block in both contracts". The only decision-regurgitation
  instrument in the repo cannot be run on the catalog.
- **Why it matters for the goal**: F5 is the stated reuse policy and the catalog is the mechanism that
  is supposed to implement it. As built, the catalog reuses precisely the layer F5 says must never be
  reused, and the instrument that would show it is inert.
- **Recommendation**: (a) Populate the `decisions` block during parameterization (it is derivable from
  the beats + labels an author already writes) and wire `check_decision_overlap.py --check` into the
  in-cell audit alongside `check_incell_clones.py`. (b) Decide explicitly which of `beats`, `label`
  surface, and `label` action-semantic is shell capital and which is per-book, the architecture
  re-specification's stratified plan says the wordless stratum only, and 592k words of prose-bearing
  directive in `skeletons/` is not that. (c) Measure the leak before deciding: run
  `check_sibling_fills.py` on two fills of one shell (`UW-C315` already records 96.3 shared 4-grams per
  1000 against a budget of 4.0, undirected).
- **How to check I'm right**: `grep -l '"decisions"' skeletons/*/*.contract.json | wc -l` → 0;
  `uv run python scripts/check_decision_overlap.py skeletons/10-13/the-midnight-museum.contract.json
  skeletons/10-13/the-midnight-frequency.contract.json`; and the slot-share computation over
  `skeletons/*/*.json` (regex `\{[A-Z0-9_]+\}` against label and `beats='...'` word counts).

---

## C1-7: catalog economics do not close, a family exhausts a cell in 4-6 requests and the flywheel can add 2.7 shells per cell per year
- **Severity**: high
- **Category**: catalog economics
- **Locus**: `src/cyo_adventure/flywheel/strategy.py:67,85,89,94`;
  `src/cyo_adventure/generation/skeleton_match.py:552-596,673-679`; `skeletons/`
- **Problem**: The grid is 18 offered cells (`band_profile.offered_cells()`), covered at 4-6 shells each,
  81 production-eligible on-matrix shells. Supply side, all hard-coded: `MONTHLY_MERGE_BUDGET = 4`
  (net new trees per month, catalog-wide), `OPEN_PR_GLOBAL = 3`, `COOLDOWN_DAYS = 30` per cell. Ceiling
  is therefore **48 shells/year across 18 cells ≈ 2.7 per cell per year**, and each is human-merge-only
  by ADR-020 decision 4 (`skeleton-promotion.yml` actively fails a promotion PR with auto-merge enabled).
  Demand side: selection is `1/(1 + recent_count)` weighted random with an explicit never-zero floor
  ("nothing is ever fully excluded"), over a 20-row family window. With 4 candidates that puts the
  probability of an immediate armature repeat at the *second* request at ~14%, and full-cell exhaustion
  at request 4-6 (matching the brief's Q-1). Review cost is not flat: median shell is 151 nodes, 7 shells
  exceed `HAND_AUTHORING_NODE_CEILING = 460` (max 677) at which point L2-13 states the machine walk "is
  now its sole correctness guarantee", i.e. the human in the F8 loop demonstrably cannot review the
  largest shells, and the flywheel's cap is set by that human.
  A family reading a book a fortnight needs ~26 distinct armatures/year in one cell; the flywheel supplies
  2.7. Reaching 26 in a single cell takes ~8 years at the global budget, or ~2 years if the entire
  catalog-wide budget were spent on that one cell (and the 30-day cooldown caps a single cell at 12/year
  regardless), during which the other 17 cells get nothing.
- **Why it matters for the goal**: full-shell reuse is bounded by catalog depth against demand, and the
  numbers say the bound binds within the first month of a subscription. Either the shell must stop
  carrying the decisional layer (C1-6), or the catalog must grow an order of magnitude faster than the
  flywheel's own hard bounds permit, or repeat armatures must be made acceptable by construction.
- **Recommendation**: treat this as the programme's primary economic question rather than a tuning issue.
  Concretely: (a) compute and publish, per cell, "requests until first armature repeat" under the live
  selection policy, it is a closed-form calculation over `_weight` and the current candidate counts;
  (b) set the flywheel budget from that number rather than from review-queue comfort; (c) if 2.7/cell/yr
  is the real ceiling, the stratified plan (share structure, generate decisions per book) is not an
  optimisation, it is the only path, and should be scheduled as such.
- **How to check I'm right**: `grep -n "MONTHLY_MERGE_BUDGET\|OPEN_PR_GLOBAL\|COOLDOWN_DAYS"
  src/cyo_adventure/flywheel/strategy.py`; count shells per cell from `metadata`
  (`(band,length,style)` → 4,4,4,4,4,4,4,4,5,5,5,5,5,5,5,6 across 18 cells); read `_weight` and
  `_RECENT_WINDOW` in `skeleton_match.py`.

---

## C1-8: the anti-clone floors are fitted to the catalog they gate, and one of them has ratcheted looser three times
- **Severity**: high
- **Category**: threshold provenance
- **Locus**: `docs/planning/ws5_floor_baseline.json`; `src/cyo_adventure/mutation/floors.py:62-104`;
  `scripts/calibrate_mutation_floors.py`
- **Problem**: Two numbers, two distinct provenance defects.
  **`TAU_STRUCT` = 0.298321 is circular by construction**: the baseline's own `derivation` field says it
  is "the 25th percentile of same-cell hand-authored structural_distance pairs", a percentile of the
  corpus it is supposed to police. PR #730's commit message records it drifting **0.320439 → 0.312968 →
  0.304707** within one PR as shells were added, "which LOWERS the bar a mutant must clear", and the
  committed value is now 0.298321. That is a monotone ratchet: every added shell that resembles its
  siblings loosens the floor that was supposed to prevent resemblance. The project knows
  (`UW-C273` registers "the ratchet question") and has not closed it. `skeleton-promotion.yml` runs
  `calibrate_mutation_floors.py --check`, so the workflow's staleness guard actively *enforces* that the
  loosened value is committed.
  **`TAU_CELL` = 0.05 is a hand-picked duplicate detector, not a diversity floor.** The baseline's
  `clamps` field describes it as "owner-chosen fixed anti-duplication floor". The catalog's own same-cell
  distribution is min 0.00047, p05 0.155, median 0.387, so 0.05 sits **three times below the 5th
  percentile of pairs everyone already agrees are distinct**. Empirically it catches exactly one pair
  (`the-harrowstone-keep` vs `the-sunken-temple`, 0.00047, allowlisted) and would admit a shell twice as
  similar as anything a human has ever objected to. `check_outcome_spread.py` finds the same pair at
  distance 0.0000 plus five more breaches, and is **not wired into CI at all** (its own docstring says
  "NOT wired into CI yet"), including two 3-5/short pairs at 0.0000 and 0.0833.
- **Why it matters for the goal**: "the shells in a cell are structurally distinct" is the guarantee that
  makes full-shell reuse tolerable (C1-7). One floor certifies only "not byte-identical" and the other
  loosens itself as the catalog converges. Neither is evidence of the property claimed.
- **Recommendation**: (a) Freeze `TAU_STRUCT` at a dated value with a recorded rationale and make
  `calibrate_mutation_floors.py --check` fail on a *decrease* rather than on staleness (a ratchet that
  only tightens). (b) Raise `TAU_CELL` toward the observed p05 (0.155) or, better, replace the single
  scalar with the two-sided report `check_outcome_spread.py` already produces, and wire that script into
  `ci.yml` beside the A8 clone audit with the same shrink-only allowlist.
- **How to check I'm right**: `cat docs/planning/ws5_floor_baseline.json` (read `derivation`, `clamps`,
  and `stats.same_cell_structural`); `git log -1 --format=%B cc3d5f7 | grep -n "TAU_STRUCT"`;
  `uv run python scripts/check_incell_clones.py`; `uv run python scripts/check_outcome_spread.py --check`
  (6 breaches, exit 1); `grep -rn "check_outcome_spread" .github/` (no hit).

---

## C1-9: the drafting brief omits blocking constraints while advertising itself as the complete set
- **Severity**: high
- **Category**: authoring ergonomics
- **Locus**: `scripts/generate_drafting_brief.py:70-290`
- **Problem**: The generator's docstring promises "the complete constraint set an authoring agent needs
  to draft a strict-compliant skeleton for one production cell". Its 18 emitted keys omit at least six
  constraints the checker enforces:
  (1) **PL-25's first-decision window** (`band_profile._FIRST_DECISION_DEPTH`), its floor is a blocking
  ERROR and it is a terminal rule in 2 tool-assisted and 4 blind S-1 failures;
  (2) **PL-15 forbidden ending kinds** per band (`_PROFILES[...].forbidden_ending_kinds`), a blocking
  child-safety rule, and `cyo-author/SKILL.md` deliberately refuses to restate it (AL-493) on the
  correct grounds that a restated safety constant drifts, but the brief does not carry it either, so it
  is stated nowhere the author reads;
  (3) **PL-16 content-flag ceilings**, likewise blocking, likewise absent;
  (4) **CG-1's choiceless-share clause** (`_CHOICELESS_SHARE`, 0.75 at 3-5, 0.50 elsewhere), the brief
  publishes only the run cap, and the share clause is what actually fires (80 catalog findings, 2
  tool-assisted and 4 blind terminal failures);
  (5) **CG-2's variance envelope** (`_OPTIONS_HARD_FLOOR/CEILING`, `_OPTIONS_VARIANCE_SHARE = 0.20`) ,
  the brief prints the target range as if it were a hard bound, so the rhythm allowance PR #730 added is
  invisible to the author it was added for;
  (6) **CG-5** (the corridor a reader actually walks) and the per-band reading-level target.
  The brief is otherwise excellent, and its history shows the pattern is recognised: every one of its
  long explanatory notes exists because an omission previously cost an author a cycle
  (`UW-C300`, `UW-C306`).
- **Why it matters for the goal**: F3 makes the brief the author's contract. An author who satisfies
  every published constraint and then fails on an unpublished one spends invocations discovering rules
  rather than writing stories, and at 10 invocations that is the difference between a pass and a loss.
- **Recommendation**: invert the guarantee, derive the brief's key set from
  `STRICT_BLOCKING_WARNINGS` plus the blocking rule ids, and add a test that every rule id capable of
  failing `--strict` has a corresponding brief key. That makes omission a test failure rather than a
  lesson-log entry.
- **How to check I'm right**: `uv run python scripts/generate_drafting_brief.py 5-8 short prose --json |
  python3 -c "import json,sys; print(list(json.load(sys.stdin)))"`, no first-decision, no forbidden
  ending kinds, no content ceilings, no choiceless share. Compare against
  `check_skeleton.STRICT_BLOCKING_WARNINGS` and `band_profile._PROFILES`.

---

## C1-10: the rules reject the corpus they are calibrated from, and the canonical CYOA topology is banned at the bands the corpus occupies
- **Severity**: high
- **Category**: threshold provenance
- **Locus**: `src/cyo_adventure/validator/topology.py:93-127` (`BAND_TOPOLOGIES`);
  `src/cyo_adventure/validator/band_profile.py:696` (`_ENDINGS_FRACTION`), `:449-496` (PL-25 anchor)
- **Problem**: PL-25, PL-26 and `ARC_CEILING_MULTIPLE` are all anchored on Adams/Beckelhymer/Marr,
  JHM 9(2) 2019, and `band_profile.py` states that corpus "sits in the 8-11/10-13 reading range".
  `BAND_TOPOLOGIES` permits `time_cave`, Ashwell's name for exactly that corpus's shape, a branching
  tree with many endings and no bottleneck, **only at 3-5, 5-8 and 8-11**. At 10-13, 13-16 and 16+ it is
  a blocking PL-29. So the shape of every book in the anchor corpus is illegal at the band the anchor is
  drawn from. The catalog shows the consequence: 0 `time_cave` above 8-11, and 35 of 84 shells are
  `branch_and_bottleneck`.
  Testing published books against the rules (using the corpus points the codebase itself cites):
  * **Fighting Fantasy, *Warlock of Firetop Mountain***, ~400 sections, 3 endings (0.8%), as
    16+/long/gamebook: node count 400 is below the cell floor 475 (L1-7, strict-blocking); PL-17's
    gamebook endings floor is `ceil(0.12 * 400) = 48` against 3, a blocking ERROR off by 16x; and its
    dice-gated win path puts the uniform-random satisfying-walk probability at ~0 against a 2% floor.
    Three independent rejections.
  * **Lone Wolf #1**, 350 sections, 17 endings (4.9%), as 16+/medium/gamebook: node count fits, but
    PL-17 demands `ceil(0.12 * 350) = 42` endings against 17, blocking, off by 2.5x.
  * **CYOA #53 (*The Case of the Silk King*)**, ~115 pages / 19 endings, as 10-13/short/prose: clears the
    endings floor (18) and PL-25, but its structure is a pure `time_cave` tree, which PL-29 forbids at
    10-13, it would have to be mislabelled `sorting_hat`, and its many two-hops-from-a-fork deaths fail
    the strict depth-qualified endings floor (min depth `ceil(11/3) = 4`).
  The codebase is honest about most of this in comments (`_ENDINGS_FRACTION` calls the 0.12 gamebook
  value "PROVISIONAL... calibrated to the edge of an n=1 sample" and notes the two published books "are
  NOT commensurable with this rule" because they gate on dice), which is exactly right, but the rule
  still blocks, and no rule anywhere records that the genre's own exemplars are outside it.
- **Why it matters for the goal**: a bar no published exemplar of the form can clear is a bar calibrated
  to the project's own output, and it is now visibly steering the catalog toward one shape.
  Homogeneity of topology is a direct input to the reuse problem in C1-6/C1-7.
- **Recommendation**: (a) Add `time_cave` to the 10-13 (and reconsider 13-16/16+) rows, or state in
  ADR-011 section 7 why the canonical shape is excluded at the band its research covers. (b) Split the
  gamebook endings floor into a diceless-format rule and record the published corpus points as
  explicitly out of scope rather than as failing. (c) Add a regression fixture directory of
  *characterised published structures* and assert which rules they trip, so the rules' relationship to
  the genre is a test rather than a comment.
- **How to check I'm right**: `uv run python -c "from cyo_adventure.validator.topology import
  BAND_TOPOLOGIES; print({b: sorted(t.value for t in s) for b,s in BAND_TOPOLOGIES.items()})"`;
  topology census over `skeletons/*/*.json` metadata (0 time_cave above 8-11, 35 branch_and_bottleneck);
  `sed -n '648,700p' src/cyo_adventure/validator/band_profile.py` for the corpus points and the
  "not commensurable" note.

---

## C1-11: the entire strict-passing catalog is one cohort, one PR, one model, one session, and its known correlated defect is invisible to every rule
- **Severity**: high
- **Category**: failure mode
- **Locus**: commit `cc3d5f7` ("feat(catalog): cover all 18 offered cells at the strict bar", 2026-08-20);
  `docs/planning/authoring-lessons-log.md` (AL-443, AL-448)
- **Problem**: All 20 shells that pass `--strict` were added by a single PR (#730) on a single day, by a
  single model (`Co-Authored-By: Claude Opus 5`), in a single session
  (`session_01H9utokJznmXRiewWJBRn3E`). That PR's own message documents the correlated defect and its
  recurrence: "the bottleneck merged the three departments while the shared endings still carried one
  department's fingerprints, so a costume-track reader was handed the lighting track's payoff...
  Found by walking concrete reader paths, not by reading the graph.", and then, in the very next
  skeleton, one day later, by the same author holding the lesson: "a reader who spent the whole story on
  the school's server was handed 'The Rota Just Stops', which is the neighbour track's payoff...
  Three of nineteen endings still came out track-bound." AL-448 records that the remedy "remember to
  check" does not work. No deterministic layer measures track-payoff coherence, and the PR states it
  outright: "Passing --strict is not the bar. An adversarial read of the green skeleton found four
  defects no deterministic layer measures."
- **Why it matters for the goal**: this is the exact failure mode the brief's question 7 anticipates,
  already realised. A defect that survives its own author's checklist within 24 hours will be present in
  every shell that cohort produced; and because promotion review is a human reading a diff of a 145-node
  JSON graph, the reviewer cannot catch what CI cannot, the defect is only visible by *walking one
  concrete path per track*, which nothing in the promotion workflow asks anyone to do.
- **Recommendation**: (a) Make path-walking a mechanised artifact rather than a discipline: have the
  promotion bundle emit one rendered reader path per track/branch-class (the `player/` engine already
  does the traversal) and require the reviewer to sign off on those, not on the JSON. (b) Add an
  endings-coherence check with a real chance of firing: for each ending, compute which decision-node
  choices are on some path to it, and flag an ending whose `beats=` names a prop/place/actor that is
  unreachable on some of those paths. (c) Deliberately vary the authoring cohort, a second model family
  authoring a fraction of each cell is a cheap decorrelation, and the S-1 data shows at least four
  families clear the bar.
- **How to check I'm right**: `git log --diff-filter=A --format='%h %ad %s' --date=short --
  skeletons/10-13/the-observatory-shift.json skeletons/8-11/the-half-hour-call.json
  skeletons/5-8/the-seedling-thief.json skeletons/3-5/the-last-blue-cup.json` (all `cc3d5f7`);
  `git log -1 --format=%B cc3d5f7` (the two bottleneck-coherence paragraphs);
  `grep -n "AL-443\|AL-448" docs/planning/authoring-lessons-log.md`.

---

## C1-12: L1-7's branch-depth message is a bare scalar, and it is a joint-top terminal failure
- **Severity**: medium
- **Category**: authoring ergonomics
- **Locus**: `src/cyo_adventure/validator/layer1.py:992-1009` (`_l1_7_finding`, message at :1005-1008)
- **Problem**: The message is `L1-7 budget: branch_depth out of range in story 'X': 10 (allowed 0..7)`.
  No node, no path, no terminal id, and the metric is `nx.dag_longest_path_length`, the graph's longest
  simple path, while every other depth-flavoured rule the author meets (PL-20, PL-25, the ending-depth
  floor) is a shortest-path quantity. `UW-C306` records both the trap ("a single-choice detour that
  rejoins the spine adds a hop to the longest path while adding nothing any one reader walks; six of them
  took a 35-hop story to 41") and that the message fix is **still open**. It shows: L1-7 is terminal in
  6 of 15 tool-assisted failures and 5 of 19 blind failures, tied for most frequent with PL-23. The
  brief's own remedy note ("look for rejoining detours before shortening anything") is published in the
  drafting brief but not in the finding the author actually receives at the moment of failure.
- **Why it matters for the goal**: same lever as C1-5, invocations spent locating a defect are
  invocations not spent fixing it, and at a cap of 10 that is the whole budget.
- **Recommendation**: name the longest path (or at minimum its terminal node and length), the way CG-1
  and CG-3 already name their run members. `nx.dag_longest_path` is already computed; printing it costs
  one line.
- **How to check I'm right**: `sed -n '992,1010p' src/cyo_adventure/validator/layer1.py`; then across
  `runs/e1r3-tools-2026-08-21/records/*.record.json`, count `last_feedback` containing `L1-7` on
  non-passing records (6), and the same for `runs/e1r3-2026-08-21/` (5).

---

## C1-13: the mutation acceptance battery measures nothing a reader would notice, and gates on the loose bar
- **Severity**: medium
- **Category**: failure mode / tooling
- **Locus**: `src/cyo_adventure/mutation/acceptance.py:1-35,669`; `src/cyo_adventure/mutation/floors.py:277-330`;
  `src/cyo_adventure/mutation/operators.py` (4,278 lines)
- **Problem**: The battery is: preconditions → `run_gate` (non-strict, `enforce_grammar=False`) → cell
  assertion → for Tier-2 only, a configuration walk with ending coverage, a clock re-proof and a
  state-signature floor → reguide resolution → the structural anti-clone floor
  (`structural_distance` vs parent and in-cell siblings vs `TAU_CELL` 0.05) → contract acceptance →
  sample fill. Every one of those is a *structural or bookkeeping* property. None of the reader-facing
  measures the repo already owns is in the battery: not `consequence.py`, not
  `check_outcome_spread.py`, not the walk floor, not the depth-qualified endings floor, not the choice
  grammar. So a mutant differs exactly in the ways `structural_distance` notices, which is the brief's
  S8 refutation stated as a property of the code rather than as a survey result. Catalog-time use is
  still defensible, offline generation of candidate shells at zero request-path cost, under human
  promotion review, is a reasonable use of 4,278 lines, but only if the battery is upgraded, because
  the promotion gate it feeds is the one from C1-1.
- **Why it matters for the goal**: 16 of 84 shells carry a `.lineage.json`, so a fifth of the catalog is
  already mutation-derived. If the acceptance criterion is "structurally distinct enough for
  `structural_distance`", the flywheel manufactures exactly the kind of variety the brief has already
  shown readers cannot perceive, and consumes the scarce human review budget doing it.
- **Recommendation**: add to the battery, as reject-only stages (matching the existing D6 pattern):
  the `--strict` walk floor, the depth-qualified endings floor, `enforce_grammar=True`, the
  outcome-economy spread against in-cell siblings, and a false-choice-rate ceiling (C1-2b). Then re-run
  the existing lineage to see how many of the 16 committed mutants still qualify, that is the honest
  test of whether the catalog-time use pays.
- **How to check I'm right**: `sed -n '1,35p' src/cyo_adventure/mutation/acceptance.py` (the stage table);
  `grep -n "run_gate(" src/cyo_adventure/mutation/acceptance.py` (line 669, no `enforce_grammar`);
  `grep -rn "consequence\|outcome_spread\|walk_floor" src/cyo_adventure/mutation/` (no hits);
  `ls skeletons/*/*.lineage.json | wc -l` → 16.

---

## C1-14: the reader-experience floors are computed on a model that ignores the conditions the reader is subject to
- **Severity**: medium
- **Category**: rule gap
- **Locus**: `scripts/check_skeleton.py:456-547` (`satisfying_walk_probability`), `:549-571` (`max_indegree`)
- **Problem**: The satisfying-walk floor, one of the five strict-only reader-experience rules, solves a
  uniform random walk with two documented simplifications: choice `condition` gating is ignored (every
  choice counted as always available) and unknown targets are dropped from the denominator. The function's
  own RAD tags say so and argue the direction is conservative for a "Tier-2 informed reader". That is true
  for a reader who has the item; it is not true for the reader the floor exists to protect, who does not,
  and for whom the gated winning choice is invisible. It also silently returns a partial estimate if value
  iteration has not converged at 10,000 iterations, with no signal (its own `#VERIFY` says a caller "must
  not trust a result that exits the loop without having converged", and `main()` does exactly that).
  Meanwhile the rules the *gate* runs (PL-20/25/26) were migrated to the configuration graph precisely
  because the choice graph was "wrong on any story with state" (`UW-C292`), so the strict-only floors are
  now the layer left behind on the superseded model. Similarly `max_indegree` counts parallel edges while
  the topology classifier does not (C1-3), so two neighbouring rules in the same function disagree.
- **Why it matters for the goal**: "a child choosing at random still reaches a satisfying ending X% of the
  time" is a child-experience guarantee, and it is computed on a graph the child does not walk.
- **Recommendation**: run the walk over `walk_configurations` (already imported in the same file for the
  state-headroom block), report both the informed and uninformed probabilities, and fail closed when the
  walk is capped or value iteration does not converge.
- **How to check I'm right**: `sed -n '456,548p' scripts/check_skeleton.py` (read the two `#ASSUME`
  blocks and the `for _ in range(10_000)` exit), and compare with `policy._Traversal`'s docstring at
  `src/cyo_adventure/validator/policy.py:374-408`.

---

## C1-15: the ten-invocation cap is where failures go to die, and the harness records nothing about what the author changed
- **Severity**: medium
- **Category**: authoring ergonomics
- **Locus**: `.worktrees/brief-evidence/docs/planning/evidence/skeleton-author-vendors/runs/e1r3-tools-2026-08-21/{tools-meta.json,records/}`
- **Problem**: Across the 42 tool-assisted grid points: passes take a **median of 5** checker
  invocations (range 2-10); failures take a **median of 10**, the cap, with **11 of 14 measured
  failures censored at exactly 10**. The distribution is bimodal, not a tail: an author either converges
  by ~6 or never converges, which means the cap is not the constraint, the message is (C1-4, C1-5, C1-12).
  Separately, every tool-assisted record carries `"repair_rounds": 0` and null token counts, because the
  subagent ran its own loop internally; the only surviving trace of the interaction is `last_feedback`
  (the terminal message) and a hand-written `note` on 2 of 42. So the programme's largest claimed lever
  (F3) is measured by a pass/fail bit and an invocation count, with no record of which message an author
  received at each step or what it changed in response. `AL-513` records the corresponding blind-condition
  problem (the pre-registered repair-rounds endpoint was degenerate under censoring) and the tool-assisted
  condition has the same shape one level up.
- **Why it matters for the goal**: F3 is the brief's headline finding and the basis for per-stage model
  selection. It currently rests on 27/42 versus 2/21, with no instrumentation of the mechanism, so it
  cannot distinguish "tool use helps" from "these three messages are broken and tool use routes around
  them", and C1-4/C1-5 suggest the latter is a large share of it.
- **Recommendation**: have the harness capture the full checker transcript per invocation (findings in,
  diff out) as the primary artifact. Then the natural next experiment is nearly free: re-run the same
  grid with only the PL-18, PL-23 and L1-7 messages repaired, and read the delta. If the pass rate moves,
  the lever is message quality, not model tier.
- **How to check I'm right**: over
  `runs/e1r3-tools-2026-08-21/records/*.record.json` join `strict_pass` against
  `tools-meta.json[key].checker_runs`, pass median 5, fail median 10, 11 of 14 at the cap; and
  `repair_rounds` is 0 in all 42.

---

## C1-16: the strict bar's ceilings and floors collide, and the catalog documents the collisions rather than resolving them
- **Severity**: low
- **Category**: threshold provenance
- **Locus**: `src/cyo_adventure/validator/band_profile.py:648-696` (`_ENDINGS_FRACTION`), `:698-763`
  (`_CELL_ENDING_BOUNDS`), `:766-795` (`breadth_scaled_floors`); `scripts/check_skeleton.py:122-148`
  (`_WALK_FLOORS`, `_MAX_INDEGREE_CAPS`)
- **Problem**: The provenance notes in `band_profile.py` are, on the whole, the best-documented
  thresholds I have audited, most name a source, a date, an owner ruling, and a `#VERIFY` test. But
  three families are self-described as unresolved and are still blocking or near-blocking:
  (a) `_ENDINGS_FRACTION["gamebook"] = 0.12` is "PROVISIONAL... calibrated to the edge of an n=1 sample"
  (the draft clears it "by a single ending");
  (b) the PL-17 cell endings *ceiling* ships advisory-only because applying it "fails 7 committed
  skeletons, 5 of them at 3-5, including `the-last-blue-cup` which was authored to the strict bar" ,
  the correct call, but it means the floor and the ceiling were calibrated against different corpora and
  the inversion was patched with a `min()` (`UW-C283`) rather than reconciled, and the same patch had to
  be applied a second time at a missed call site (`UW-C300`);
  (c) `_MAX_INDEGREE_CAPS` and `_WALK_FLOORS` are owner rulings from a single 2026-08-09 review with the
  catalog medians recorded but no independent anchor, and the walk floors' derivation
  ("medians of 100% (3-5), 71% (5-8), 43% (8-11), 29% (10-13), 0.3% (13-16), 1.2% (16+)") is a
  measurement of the catalog they gate, the same circularity as `TAU_STRUCT` (C1-8), applied to the
  child-experience guarantee.
- **Why it matters for the goal**: floors set from the corpus they gate cannot detect corpus-wide drift,
  which is the failure mode C1-11 shows is live.
- **Recommendation**: for each of the three, record the *falsifier* rather than the value: what
  observation would move it, and who supplies it. `_ENDINGS_FRACTION` names one already ("a second
  diceless gamebook is what would settle it"), do the same for the walk floors (a reader study, or the
  JHM corpus's own win rates) and the in-degree caps.
- **How to check I'm right**: `sed -n '648,700p' src/cyo_adventure/validator/band_profile.py` and
  `sed -n '112,152p' scripts/check_skeleton.py`, every claim above is quoted from those comments.

---

## What I checked and did not find a problem with

Recorded so the absence is informative rather than an omission:

- **Layer 1 and `check_graph_structure.py`.** Reachability, termination, reference integrity, sink
  detection and the six-class repairability taxonomy are sound, well-tested, and the script is explicit
  about what it does not check ("Structural validity is necessary and nowhere near sufficient").
- **The in-cell clone audit is properly wired.** `ci.yml` runs `check_incell_clones.py --check` blocking
  against the real catalog with a shrink-only allowlist. The defect is the threshold (C1-8), not the wiring.
- **The promotion workflow's non-gate properties are good.** It fails closed on an unresolvable diff,
  proves *every* changed shell (with a documented history of why filtering upstream was wrong), announces
  every downgraded check in the log, refuses auto-merge on a promotion PR, and guards the derived
  artifacts. The single defect is the missing `--strict` (C1-1).
- **`generate_drafting_brief.py`'s reading of live sources.** It genuinely imports from
  `band_profile`, `choice_grammar`, `policy`, `topology` and `check_skeleton` rather than restating ,
  the `AL-149` lesson is properly applied. The gap is coverage (C1-9), not drift.
- **RAD discipline.** Nearly every threshold and simplification I chased carried an `#ASSUME`/`#VERIFY`
  pair naming the test. In two cases (C1-14, C1-16) the tag correctly describes a defect that was then
  not fixed, which is a scheduling failure, not a documentation one.
