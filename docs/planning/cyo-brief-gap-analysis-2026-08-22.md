# Gap analysis of the 2026-08-22 generation research brief

Analysis of 2026-08-22, against
[cyo-generation-research-brief-2026-08-22.md](./cyo-generation-research-brief-2026-08-22.md).

Twelve independent reviewers examined the brief, its evidence, and the code it describes, against
one question: does this framework produce high-quality choose-your-own-adventure books at a cost
the product can carry? This document synthesizes what they found, deduplicated, ranked, and with
the load-bearing claims re-verified.

> **A note on tone.** The brief is unusually honest engineering writing. It names its own failures
> (the fill-rate hole, three broken instruments, six refuted levers) and labels its evidence
> classes. Most of what follows is not "the brief is wrong"; it is "the evidence says something
> stronger or different than the brief renders it", and "the mechanism the brief describes is not
> the mechanism that is wired". Section 6 records where the brief is right and where corrections
> run in its favour.

---

## 0. Method, and how to read the confidence markers

**Three cohorts, deliberately asymmetric.**

- **Cohort A (3 reviewers), blank slate.** Given only the product goal and its constraints. They
  were barred from reading `docs/planning/` so their conclusions could not be anchored by the
  programme's history. Their output is 191 yes/no requirements, diffed against the brief in
  section 5. Where a blank-slate reviewer and a code-grounded reviewer reach the same conclusion by
  different routes, that is weighted heavily and flagged as **[convergent]**.
- **Cohort B (3 reviewers), structure.** Framework coherence, pipeline architecture, evidence and
  methodology.
- **Cohort C (6 reviewers), components.** Skeleton stage, fill stage, diversity and instruments,
  safety and human approval, cost and model selection, testing and validation.

**Confidence markers used below.**

- **[verified]** I re-ran the command or read the code myself. Reproduction is shown in section 3.
- **[code]** A reviewer grounded it in `file:line` and reported the location; not independently
  re-run here.
- **[analysis]** Reasoning or arithmetic from documents, not a code fact.

**One correction to my own setup, disclosed because it shaped the run.** This branch initially
carried only the brief, not the evidence it cites. Four reviewers concluded the cited artifacts did
not exist. That was my error. The source branch was materialized at `.worktrees/brief-evidence/`
and all affected reviewers re-ran against real data; every absence-based finding was retracted. The
correction changed the character of the review: with the raw records in hand, reviewers stopped
finding "this is undocumented" and started finding "the document says something different from what
the data says", which is the more serious class. It also produced two findings that would not
otherwise exist (B2-23, B3-4).

---

## 1. The five findings that should change a decision this week

### 1.1 F5's flagship evidence does not reproduce, and the pair it rests on shares decisions

F5 is the architectural keystone: reuse structure freely, never reuse decisions. Its headline
evidence is the D-7b stratified-plan pair at "2.3 shared 4-grams per 1000, under the 4.0 budget and
below the 3.3 generator idiom floor".

Re-running the project's own tool on the project's own committed artifacts **[verified]**:

```
shared 4-grams across 2 fills: 10 (3.2 per 1000 mean leaf words; budget 4.0)
menu frames shared by 2+ fills (same node, same choice position, same opening words): 2
  n_pendulum[1]: turn back
  n_study[1]: stay read
```

Three consequences, in increasing order of severity:

1. **The number is 3.2, not 2.3.** `check_sibling_fills.py` counts boundary-straddling grams, which
   the published figure excludes (C6-2, C3-7, both independently).
2. **The margin collapses.** The claim's force is being *below* the 3.3 idiom floor. At 2.3 the
   margin is 1.0; at 3.2 it is 0.1, against a floor whose confidence interval B3 computes as
   [-0.7, 7.2]. The result is statistically indistinguishable from generator idiom.
3. **The pair shares decisions.** Two menu frames at the same node, same choice position, same
   opening words. F5's own criterion is that decisions must never be shared. The evidence for F5
   violates F5.

Separately, all four blind raters called the *passing* D-7b pair the same adventure at scene 2,
indistinguishable from the "failing" D-7 pair (B3-1, C3-1). D-7b fires S-2's own pre-registered
falsifier at distinctness 1/5.

**Recommendation.** Treat F5 as unproven rather than established. Reconcile the two 4-gram scopes
and restate every published figure under one named scope. Before further building on the stratified
plan, run the E0 instrument validation that the sourcing test plan already gates S-2 behind.

### 1.2 The catalog is convergent across different graphs in different worlds

The brief files the recognition-protocol pilot under instruments that do not work: it "failed its
pre-registered control on 2026-08-21 (both raters called a cross-graph pair the same adventure,
partly because the control itself carried the catalog's convergent decision structure)".

The verdict artifacts say something stronger **[verified]**. The control pair was **26 nodes versus
95 nodes, different graphs, different worlds** (clocktower versus museum), same band. Both raters
answered `same_adventure: yes`, distinctness 2/5, and independently named the same causal chain:

> rooms off a hub teaching pieces of a cipher, a central mechanism set exactly-or-forced-or-guessed
> that jams when forced, a strongroom with the maker's letter, a hidden workshop behind a secret
> panel, and tell-the-town versus keep-it-secret versus take-the-treasure endings

Two raters converging on that level of specific shared structure is not a failure to discriminate.
`results.md` line 51 concedes it in the programme's own words: *"The clocktower book and the museum
book do substantially contain that chain. This is the programme's own catalog-convergence finding
appearing."*

**Read the pilot the other way and it is the programme's most direct measurement of the defect it
exists to prevent, and it is positive.** The catalog is convergent across different graphs in
different worlds, which is precisely the condition F5 assumes away.

The same pair scores 2.2 shared grams per 1000 (below the 3.3 idiom floor), structural distance
0.1239, and passes the anti-template guard at 0.925 with 0 of 26 nodes flagged (C3-3) **[code]**.
All three surviving instruments rate this pair maximally distinct while both raters call it one
book. That is a demonstrated false negative on committed data.

**Recommendation.** Re-file the pilot in the brief as evidence about the catalog, not only about the
instrument. Both readings can be stated; only one is currently stated. Then build the missing
anchor: every instrument is calibrated at the "similar" end only, and its known-different anchor is
a re-theme, which is exactly what raters merge (C3-8).

### 1.3 The authoring bar is enforced nowhere, and cosmetic choice passes the gate

Section 3.2 states `check_skeleton.py --strict` is the authoring bar and section 3.1 states CI
"re-proves every changed skeleton from scratch".

- **No caller anywhere passes `--strict`** **[verified]**. Every occurrence in the repo is a
  docstring, an argparse definition, or a comment. `generate_drafting_brief.py:265` prints the
  command as advice to a human author.
- **`skeleton-promotion.yml` calls `check_promotion_bundle.py`**, which builds
  `skeleton_argv = [str(shell_path)]` at line 322 and appends only `--allow-mvp`, never `--strict`
  **[verified]**. The promotion gate is the loose default.
- **81 of 84 shells pass the default gate; 20 of 84 pass `--strict`** (C1-1) **[code]**. The catalog
  is roughly 76% non-compliant with its own stated standard.

The quality consequence is concrete. `skeletons/10-13/the-observatory-shift.json` has **115 decision
nodes, 102 of which offer two or three differently-worded choices that all lead to a single target**
**[verified]**. Eighty-nine percent of that book's decisions are typographic, and it passes.
`validator/consequence.py` detects exactly this and gates nothing (C1-2).

This also supplies a mechanism for 1.2: if most choices are cosmetic, two books will read as the
same adventure whatever their graphs look like. The convergence finding and the false-choice finding
are likely the same finding seen from two ends.

**Recommendation.** This is the cheapest large win on the board. Pass `--strict` in
`check_promotion_bundle.py`, publish the 64-shell remediation backlog, and promote
`consequence.py` from library to gate. Expect the strict bar to need the PL-18/PL-29 fix first
(C1-4): at ages 3-5 and 5-8 an acyclic graph with any merge currently has no legal topology.

### 1.4 The economics are dominated by human review, and they do not close [convergent]

Two reviewers reached this independently, one of whom never saw the repository.

| | machine | human | all-in |
|---|---|---|---|
| ages 3-5 | | | $2.49 |
| ages 8-11 | | | $6.54 |
| ages 16+ | | | $11.68 |
| **40/40/20 mix** | **$1.45** | **$4.50** | **$5.95** |

C5's reconstruction: **$5.95 per book, 76% of it the mandatory human**. Against a $10 subscription
at 70% target margin that is over by 4 to 8.5x at 3 books per child per month, and 13 to 28x at the
shipped 10-book quota. A3, working only from the goal statement, derived a $0.58 ceiling with the
human at 71% of cost, and the impossibility result directly: reading a large book end to end is
hours of labour against a sub-dollar ceiling, so **the review surface must be O(1) in book size**.

C4 measured the current surface at **3.0 to 8.3 hours per book against ADR-005's "a few minutes",
a 35 to 100x gap** **[code]**, with all nodes dumped in DFS order, no sampling, no path view, no
risk ranking.

**The strategic consequence.** F4 (per-stage model selection) and F7 (engineer the cost) both
optimise the ~24% of the bill that is not binding. No model choice moves the constraint. Both
blank-slate cost reviewers concluded the only structure that closes is **the guardian as primary
approver, with paid staff as a risk-triggered second line** (A1, A3), which is a product and ADR-005
question, not an engineering one.

There is also **no cost-per-book number anywhere in the programme** (C5-1) and **no runtime spend
cap** (C5-2): the only `_MAX_COST_USD` is a Decimal overflow clamp at $999,999.99 protecting a
database column **[verified]**. "Cost-effective" is currently an assumption, not a measurement.

### 1.5 The skeleton-author ranking may be measuring catalog conformity, not skill

B3 derived a result that is not in the brief: across the S-1 legs, **pass rate versus
distance-from-catalog gives Spearman -0.982, exact permutation p=0.0016** **[analysis]**. The
models the brief recommends as structure authors are the models that produce the most catalog-like
graphs. The closest Opus shell scored 0.0507 against a TAU_CELL clone threshold of 0.05.

Read with 1.2, section 4.2 may not be measuring authoring skill. It may be measuring conformity to
a catalog already shown to be convergent, in which case the model recommendation actively
reinforces the defect the programme exists to remove.

**Recommendation.** Before acting on the per-stage model recipe, re-score the S-1 shells with
distance-from-catalog as a covariate, and add a novelty term to the pass criterion so an author is
not rewarded for reproducing the catalog.

---

## 2. The systemic pattern: the detector is built, and it gates nothing

The single strongest cross-cutting theme. In seven separate cases the mechanism that would catch a
defect exists, is tested, and is reachable from no gate and no production path.

| Detector | Catches | Wired to |
|---|---|---|
| `validator/consequence.py` | false choice, cosmetic branching | nothing (C1-2) |
| `validator/imitable.py` | imitable-action harm | nothing but its own unit test (C4-8) **[verified]** |
| `validator/paths.py::covering_paths`, `reader_sample_paths` | path-level evaluation | one offline script (C4-1) **[verified]** |
| `validator/safety.py::check_safety` (SAFE-14) | the gate's safety layer | called by `gate.py:213`, returns empty always (C4-5) **[verified]** |
| `scripts/check_fill_integrity.py` | the AL-490 under-delivery hole | nothing in `src/`, nothing in CI (C5-3, B2-4, B1-8, C6-1) **[verified]** |
| `scripts/check_sibling_fills.py` | sibling convergence | nothing (UW-C315, C3-6) |
| `scripts/check_solution_transfer.py` | the one measure that reproduced reader orderings | no production path; cannot even run on D-7b (section 3) |

`check_safety` is the sharpest case: it is not dead code but a live call site inside the gate's
merge chain that always contributes nothing, so `gate.py` reads as though safety is covered.

**Recommendation.** Adopt a rule with teeth: a validator module in `src/` with no gate caller is a
build failure or is deleted. C6-9's finding that 8 of 15 `check_*.py` gates have no tests, no rule
ids and no mutation coverage is the same disease in the script tier.

---

## 3. Verified directly in this review

Everything in this table I re-ran or read myself. It is the load-bearing subset.

| Claim | Result |
|---|---|
| D-7b shared 4-grams | **3.2** per 1000, not the published 2.3; plus 2 shared menu frames |
| Recognition control verdicts | both raters `same_adventure: yes`, distinctness 2/5, first-yes at scenes 41 and 12; 26 vs 95 nodes |
| `results.md` framing | line 51 concedes the two books "do substantially contain that chain" |
| `--strict` callers | zero; all occurrences are docstrings, argparse, or comments |
| Promotion CI | `check_promotion_bundle.py:322` passes only `--allow-mvp` |
| `the-observatory-shift.json` | 115 decision nodes, **102** with all choices to a single target |
| `validator/safety.py` | Phase-2 stub returning an empty report; called from `gate.py:213` |
| `validator/imitable.py` | zero importers outside `tests/unit/test_imitable.py` |
| `covering_paths` / `reader_sample_paths` | only external caller is `scripts/measure_per_path.py` |
| `has_hard_block` | read only in `moderation/`; `api/approval.py` contains no verdict check |
| `api/approval.py::approve_storybook` | raises on `publish_without_approver` only |
| `llm_timeout_seconds` | **120** (`core/config.py:507`); timeout classified transient in every provider |
| Runtime spend cap | none; `_MAX_COST_USD` is a $999,999.99 Decimal overflow clamp |
| `check_fill_integrity` in `src/` | appears only in comments and docstrings |
| Largest commissioned book | **42,233 words** at 677 nodes; catalog max 49,953 at 632 nodes |
| `check_solution_transfer.py` on D-7b | cannot run; D-7b has no `selection.json` artifact |

**Two corrections to the brief's own scale facts.** The "677-node, ~118,000-word graph at 16+"
fuses one book's node count with a word figure about 2.8x its actual commission. And the opening
census of "61 graphs and 11,458 nodes" is stale against 84 shells on both trees (B1-14, C3-15).
The word-count error propagates: A3's large-book cost and review-hour estimates are roughly 2.8x
pessimistic, so the large-book problem is real but smaller than modelled.

---

## 4. Findings by theme

Severities are the reviewers'. Only critical and high items are listed; the full set with
`file:line` loci, falsifiers and recommendations is in the twelve findings files.

### 4.1 Diversity, instruments, and F5

- **C3-4 / B3-1 (critical).** The defect definition ("readers track decisions, not tree shape")
  rests on one blind rater on one pair, plus inference. Six of seven rival hypotheses are
  undiscriminated, and two (premise, ending economy) are positively implicated by the raters' own
  words. The whole architecture rests on this premise.
- **C3-8 (high).** Common cause of all three instrument failures: every instrument is anchored only
  at the "similar" end, and the known-different anchor is a re-theme.
- **C3-5 (high).** The "wordless" shared stratum carries 473 words, 303 of them per-node, and its
  fact names enumerate decision outcomes while node ids carry scene identities.
- **C3-6 (high).** History is family-scoped where the defect is child-scoped: repeat rate 0.413
  versus 0.152 at three children. The anti-template guard is advisory, fail-open, and fires only on
  reuse the selector already avoids.
- **C3-9 (high).** Q-1 verified: N50 of 3 to 5 across cells, 18 populated cells, 4 empty. Shortfall
  is 130 skeletons at 1 book/month, 334 at 2. The only scaling mechanism (mutation) is the refuted
  S8 lever: M1 distance 0.0000, 95 of 95 parent beats byte-identical.
- **C3-13 (medium, strategically important).** Stratified generation may be the seventh lever in a
  series of six refuted ones: it solved its own metric and left recognition unmoved, exactly as S5
  and S6 did. It varies strings, not acts.
- **B3-10 (high, favourable).** Shared-4-gram rate scales as N^0.788, so "96.3 equals 24x budget" is
  about **1.15x** at realistic book length.

### 4.2 Skeleton stage

- **C1-3 (critical).** `_build_graph` collapses parallel edges (348 choices to 144 edges) while
  `max_indegree` counts them, so phantom choices satisfy PL-17/25/26 while the graph stays a tree
  for PL-18.
- **C1-4 (critical).** At ages 3-5 and 5-8, an acyclic graph with any merge has no legal topology,
  and PL-18 prints a menu PL-29 forbids. Four of fifteen tool-assisted failures, all at the
  invocation cap.
- **C1-5 (critical).** Every strict-blocking finding is labelled "advisory only", all 2,456 of them.
- **C1-8 / C1-16 (high).** TAU_STRUCT is the p25 of the corpus it gates, ratcheted four times in one
  PR; TAU_CELL 0.05 sits about 3x below the catalog's own p05 of 0.155, making it a clone detector
  rather than a diversity floor; walk floors are medians of the catalog they gate. Calibration is
  circular in several places.
- **C1-10 (high).** `time_cave`, the shape of the original CYO corpus, is banned at 10-13 and above;
  *Warlock* fails PL-17 by 16x and *Lone Wolf #1* by 2.5x. The rules would reject the canon.
- **C1-11 (high).** All 20 strict-passing shells come from one PR, one model, one session, with a
  bottleneck-coherence defect that recurred 24 hours later and no deterministic layer measures.
- **C1-7 (high).** `MONTHLY_MERGE_BUDGET` 4 plus a 30-day cooldown yields 2.7 shells per cell per
  year against exhaustion at request 4 to 6, with first repeat possible at request 2.

### 4.3 Fill stage

- **C2-4 (critical) [verified].** `llm_timeout_seconds = 120` against measured fills of 469 to
  1,874s. Timeout is classified transient in every provider, so a large fill times out, retries
  three times, and walks the cascade toward a local 14B model, with every attempt billed. Invisible
  to the gates because the output still parses.
- **C2-3 (critical).** Chunking bounds output only. The skeleton is re-sent whole per batch and
  prose accumulates: about 594k input tokens per book, last batch about 193k, over the context
  window at cap 32,768.
- **C2-2 (critical).** `drafting_guide.md`'s "no hard per-node minimum, a tense beat can run three
  words" sits in every fill system block and licenses the AL-490 shortfall.
- **C2-7 (high).** `batch_request` strips conditions and effects, so a reconverging node is written
  blind to its arrival states. The classic continuity defect is guaranteed by construction. A1
  independently called this the most common misclassification in the space: continuity is a
  compute-it problem given a typed state ledger on edges, and an intractable judge-it problem
  without one **[convergent]**.
- **C2-6 (high).** Semantic fidelity is one 512-token pass/flag verdict for a whole book, fails
  open, and never sees the premise.
- **C2-10 / C2-11 (high).** The production cascade is unpinned (`provider_order` never passed) and
  `FallbackProvider` has no `.model`, so fallback legs run under the primary's cap; `finish_reason`
  is read nowhere outside the adapter, so truncation and `content_filter` both surface as malformed
  JSON and burn the repair budget.

### 4.4 Safety and human approval

- **C4-1 (critical) [verified].** Safety is per-node only. Path-level and cumulative harm, including
  grooming-shaped narratives, is invisible by construction, while the path machinery sits unused.
  Both blank-slate reviewers predicted exactly this as the structural blind spot, because generator,
  schema and review UI are all node-shaped **[convergent]**.
- **C4-2 / B2-3 (critical) [verified].** A bright-line BLOCK is reversible in three clicks
  (`needs_revision`, `submit`, `approve`). Neither submit nor approve reads `has_hard_block`, and a
  dual-role adult can self-approve. Two reviewers found this independently.
- **C4-3 (critical).** The review surface dumps all nodes in DFS order with no sampling, ranking or
  path view; Approve carries no version and no attestation.
- **C4-4 / C4-5 / C4-8 (high).** The gating taxonomy is adult moderation. Violence intensity,
  bullying, substance use, stereotyping, grooming, imitable instruction and cover imagery are
  uncovered; ADVISORY never gates; SAFE-14 is a stub; `imitable.py` has no callers.
- **C4-9 (high).** The repair identity check is id, tier and node count only, so a repair can rewire
  the graph, and neither skeleton fidelity nor the fill-rate floor re-runs on a repaired blob.
- **C4-10 (high).** The review model is an unallowlisted free string, never persisted, pinned to no
  dated id, resting on one owner's impression for a child-safety component.
- **C4-11 (high).** The threshold flywheel raises `min_verdict` after 5 books at 80% override,
  converting an over-approving admin into hidden findings.

### 4.5 Cost and model selection

Beyond section 1.4: no per-stage cost attribution is possible in principle because `TokenUsage`
carries no stage field (C5-13); billed calls are discarded from the ledger, proven by a run record
with three billed `content_filter` responses at cost null (C5-4); `anthropic` and `modal` price as
$0.00 and cover art is unmetered (C5-6); the reading-level loop was 46% of a measured 16+ book's
bill for `in_band` 0.155 (C5-8); a measured book took 1,874s against a 1,800s RQ timeout, and the
SIGKILL orphan records no cost (C5-14); and of the four spend guards section 4.5 credits, the
credits check, the one whose absence lost 76 shells, was specified and never built (C5-15).

**C5-5 (high).** Repriced at list, the Anthropic legs cost **$33 to $126** against the DeepSeek
legs' $1.30. The "zero marginal provider cost as subagents" framing inverted the comparison that
produced the recommendation.

### 4.6 Evidence and methodology

- **B3-2 / B1-7 (critical).** The S-1 pre-registered primary endpoint was degenerate in **both**
  arms, and the tool-assisted permutation test runs on an all-zero vector. The pass counts section
  4.2 reports are pre-registered as "exploratory, decision-inert". The registered run halted at 4 of
  80 shells on exhausted credits, and the slate, cells and replicates were revised post-halt. All of
  this is disclosed in the register and none of it reaches the brief. F6 is violated inside the
  document that states F6.
- **B3-3 (critical).** The deciding tool-assisted arm ran outside the harness: all 42 records show
  `attempts=1, rounds=0, tokens=null`, with a hand-written three-field file as the actual data.
  Corroborated independently by B1-10 and C1-15. To its credit, B3 withdrew the suspicion that the
  blind arm's scaffolds were unequal; that check passed.
- **B3-7 (critical).** At n=3, only 0/6 versus 6/6 (p=0.0022) and 0/6 versus 5/6 separate. "Frontier
  Anthropic tiers converge fastest" does not survive: Kimi K3 at 5/6 versus 6/6 is p=1.00. The
  V4 Pro 0/6 result does survive.
- **B3-6 (critical).** The judge panel behind "best prose" had dialogue SD 0.00, other dimensions
  below 0.65, and an 84-verdict pool lost (AL-362). "Best judged prose" is plausibly judge
  preference.
- **B3-5 (critical).** A supplier ranking was reinstated after W5's pre-committed retraction.
- **B1-3 (critical).** The blind arm ran cell A only (`run.json cells=["A"]`), so "blind 2 of 21
  versus tool-assisted 12 of 21" compares one cell against two, and confounds regime with a 6-round
  versus 10-invocation budget. AL-512 records that the blind arm "systematically understates current
  practice".
- **B2-23 (high).** F3's tool-assisted regime, the brief's single largest measured quality lever,
  exists as code nowhere. The harness implements only the blind arm. The lever is a practice, not a
  mechanism, and cannot currently be run reproducibly or at scale.

### 4.7 Testing and validation

- **C6-8 (high).** Instrumenting all 8,561 unit tests shows 54 of 55 rules can fire. The one that
  cannot is SAFE-14, which is the gate's entire safety layer.
- **C6-4 (high).** The honesty machinery is gameable: a lesson marked `applied` with the ref
  "fixed it, see the thing" passes **both** checkers, and **57 of 240 applied refs resolve to
  nothing**.
- **C6-5 (high).** The diversity register, which holds every falsifier in the programme, has zero
  automated checks; `planning-linkage.yml` covers three other documents.
- **C6-6 / C6-7 (high).** No git SHA, seed, temperature or model snapshot in any `run.json`; the
  S-1 prompt and pass bar are live functions of validator code; recognition verdicts carry zero
  provenance. The load-bearing experiments are not reproducible by a third party.
- **C6-10 (high).** Golden corpora assert one bit (`not blocked`) and never which findings fired,
  so a validator change that loosens a rule passes silently.
- **C6-12 (medium).** The one full-pipeline e2e drives `_CANNED_STORY` and never `fill_skeleton`; no
  test anywhere drives a valid-but-hollow fill, which is the exact AL-490 defect.

---

## 5. What the blank-slate cohort required that the brief does not cover

191 requirements were produced without sight of the programme. Most map onto something the brief
has. These are the ones with no counterpart, grouped. They are the framework's blind spots as seen
by people who could not be anchored by its history.

**The reader is absent.** No principle in F1 to F8 concerns the child's experience, and the
predecessor brief's banner that no human or child has read any generated book was dropped rather
than resolved (B1-5). The blank-slate cohort required: behavioural telemetry as the arbiter when
metrics and outcomes disagree (A2-63, A1-51); completion rate, abandonment depth, re-read and
branch-exploration rates (A1-51); child think-aloud sessions per band (A2-61); perceived novelty
measured with actual children over 8 or more books with a pre-registered endpoint (A1-30); guardian
rejection and edit rates as first-class quality metrics (A1-52); and a pre-scheduled regression of
child retention on the offline quality score, so eval theatre is detected rather than assumed away
(A1-53). **There is no loop from what children actually read back into generation** (B2-17).

**Craft rules that are computable and unbuilt.** Choice-label predictiveness above chance (A2-9);
no direction-only labels (A2-7); labels naming both action and intention (A2-8); options within 30%
length and grammatically parallel (A2-11); no two options leading to the same node (A2-17); subtree
balance at 25% of largest (A2-18, A1-6); filler nodes under 15% (A2-19); **precondition dominance,
every fact asserted as known established on every path reaching that node** (A2-20, A1-8);
conditional choices offered only where the prerequisite was obtained (A2-21); callback density at
60% of choices referenced later (A2-15); a variant sentence keyed to the path taken at every
reconvergence (A2-16); protagonist agency at 60% of scene-turning actions (A2-24); endings distinct
on extracted outcome tuples rather than prose embeddings (A2-29); no moral-lesson coda (A2-34); no
reset devices (A2-35).

**A peril floor.** Over-moderation is itself a failure mode ("the Sanded Edge"), so bands need a
minimum stakes requirement expressed as a floor, not only a ceiling (A2-33, A2-11 band rules). The
brief's gates are all ceilings.

**Instrument validation as a gate on gating.** Every metric labelled in code as gating or
monitoring with the gating set closed (A1-40); a gold set of 150 to 200 books rated by three or more
trained humans (A1-41); Krippendorff alpha at or above 0.67 per dimension or the dimension is
re-specified (A1-42); Spearman against human ratings above a declared threshold before a metric may
gate (A1-43); judge test-retest stability (A1-44); a defect corpus of 15 or more injected examples
per class with 95% localised recall (A1-47, A1-48); the three negative controls
(fluent-but-agency-free, structurally-perfect-but-empty, excellent-but-off-band) (A2-57); and gold
items in every judge batch with batch discard on gold failure (A2-52). F6 states the principle; the
apparatus is not built, and the surviving instruments have not been held to it.

**Human review as a measured control.** Seeded known-bad books at 3% or more with per-reviewer catch
rates (A1-59, A2-60, A3-42), reached independently by all three blank-slate reviewers
**[convergent]**; the machine verdict revealed only after the human's judgement is recorded
(A1-58); review time measured at p50 and p90 rather than assumed (A3-44); override rate alarmed on
**both** ends of a 2 to 15% band (A3-41); queue depth in hours of work with paging thresholds
(A3-45); a written policy forbidding compression of review time as a backlog remedy (A3-46); an
approval record storing what was attested, including coverage, seed and packet version (A1-63); and
approval bound to a content hash so any change voids it (A3-34).

**Operational discipline the brief never reaches.** A tested kill switch not requiring a deploy
(A3-17); provider balance in days-of-burn with alarms (A3-18); `response.model` asserted equal to
the requested model on every call, with cost computed from the served model (A3-20, A3-21); a
shadow lane at 1 to 2% of traffic to make model migration a dashboard (A3-50); a weekly canary
regeneration of a frozen request set (A1-49); a second provider smoke-tested weekly (A3-51, A1-67);
a rehearsed safety-escape runbook including corpus-wide unpublish by content hash and a
pre-committed rule that a confirmed escape in the youngest band halts that band (A3-54, A3-55);
checkpointed chunks with a tested resume path (A3-19); and latency as p50/p95 request-to-ready with
the fraction of never-opened books tracked (A1-65). The brief has no principle for failure, retry
or latency at all (B1-13), though the live run delivered 3 of 5 books, hit a content filter on a
preschool premise, and took 1,874s on one book.

**Metering and pricing structure.** Meter the product in words rather than an unbounded book count
(A1-21, A3-4); price or ration the largest books separately (A1-22); amortise or defer cover art,
which dominates the smallest books (A1-23, A1-10); track cost-per-generated over cost-per-published
and alarm above 1.3 (A3-28); and assert in a test that input tokens grow linearly rather than
quadratically in book length (A3-8), which is precisely the C2-3 defect.

**Two structural positions worth weighing against F5.** Both A1 and A2 argue, independently, that
**variety belongs at the plan stage in code**: sample a design cell deterministically from a space
of 10^4 or more (archetype x problem type x agency model x ending family x voice x tone) with
per-family cooldown, and **amortise components rather than whole skeletons**, because a fixed
skeleton catalogue is a countdown to a plateau (A1-24 through A1-28, A1-13). A2 adds the inversion
worth testing: if a child loves a world, **hold the world constant and vary the structure**, which
is the opposite of what theme binding does. And A2's Inkle observation reframes the cost problem:
30 remembered facts referenced 200 times beats 677 unique nodes, so state beats topology.

---

## 6. Where the brief is strong, and corrections that favour it

Recorded so the ledger is honest.

- **The evidence-class discipline is real and rare.** Labelling deterministic, model-judged and
  human-gated, and calling model-judged the weak class, is better practice than most engineering
  organisations manage.
- **`recognition-protocol-pilot/results.md` reports a failed instrument as failed and refuses the
  tempting post-hoc repair** (C6, explicitly). The programme's failure to publicise its own best
  finding is a distillation problem, not a candour problem.
- **The finding that a passing gate is not quality (F2) is correct and hard-won**, and the delivery
  measurements exist because of it. The gap is wiring, not insight.
- **F3's core claim survives its confounds.** Even discounting the cell-A confound and the budget
  asymmetry, tool-assisted authoring beat blind authoring decisively. The regime insight is sound;
  what does not survive is the per-model ranking built on top of it.
- **The V4 Pro structure-authoring result (0 of 6) does survive n=3 scrutiny** (B3-7). It is the one
  model-level claim in 4.2 that is statistically safe.
- **`test_rules_can_fire.py`, the catalog lockstep test, the "guard the guard" non-empty-corpus
  assertions, and the CI diversity job's file-loaded TAU_CELL** are genuinely good testing practice
  (C6). 54 of 55 rules provably fire.
- **Corrections running in the programme's favour**: the 24x sibling-convergence figure is about
  1.15x at realistic scale (B3-10); the largest book is 42,233 words rather than 118,000, so the
  large-book cost and review burden are roughly 2.8x smaller than the brief's own figure implies;
  and the blind arm's scaffold equality held under audit.

---

## 7. Where the reviewers disagree, and what is still open

- **Is the stratified plan different in kind from the six refuted levers?** C3-13 argues it is the
  seventh in the same series. B1-6 argues the evidence is too thin to say either way. Both blank-slate
  reviewers would replace it with plan-stage combinatorial sampling. Unresolved, and it is the
  central architectural question.
- **Instrument failure or catalog convergence?** C3-2 and this synthesis favour catalog convergence;
  the brief favours instrument failure. Both readings are consistent with the data, and they imply
  opposite next actions, so E0 validation should be run before either is adopted.
- **Catalog census.** The brief says 61 graphs, reviewers measured 84 shells, and a naive glob over
  `skeletons/**` matches 147 files. These are different populations (production-eligible, draft,
  mvp). The exhaustion arithmetic in C3-9 and C1-7 depends on which is correct, so the number should
  be published with its filter.
- **B3's decisive test could not be run.** `check_solution_transfer.py` needs a `selection.json`
  per book; D-7b and D-7 have contract, decisional and filled artifacts but no selection. The
  programme's instruments do not interoperate across its own experiments. Reconstructing D-7b
  selections and running solution transfer remains the cheapest test that could overturn F5.

---

## 8. Recommended actions, ranked by value per unit cost

**This week, cheap and decisive.**

1. Reconcile the two 4-gram scopes and restate every published figure under one named scope. F5's
   headline number is currently unreproducible from the committed tool.
2. Reconstruct D-7b selections and run `check_solution_transfer.py` on the pair. Free, already
   built, and it can overturn or confirm the programme's central architectural claim.
3. Pass `--strict` in `check_promotion_bundle.py`, after fixing PL-18/PL-29 so a legal topology
   exists at 3-5 and 5-8. Publish the remediation backlog for the 64 non-compliant shells.
4. Make `api/approval.py` refuse to publish a book whose moderation report carries a hard block.
   One conditional closes a three-click bypass of the product's primary safety control.
5. Raise `llm_timeout_seconds` above the measured fill distribution and stop classifying fill
   timeouts as transient. This is billing three retries and a tier downgrade on every large book.
6. Correct the brief's scale facts (42,233 words, 84 shells) and add the S-1 pre-registration
   caveats that the register already discloses.

**This month, structural.**

7. Promote `consequence.py` to a gate, and adopt the rule that a validator module with no gate
   caller fails the build. Then work the list in section 2.
8. Wire path-level evaluation using the `covering_paths` machinery that already exists, and adopt
   A1's publish-time invariant: zero reachable nodes uncovered by any path-level evaluation.
9. Produce a cost-per-book number, add a stage field to `TokenUsage`, and enforce a runtime spend
   ceiling per book.
10. Seed known-bad books into the review queue at 3% and measure per-reviewer catch rate. Until this
    exists there is no measurement of the product's primary safety control.
11. Re-score S-1 with distance-from-catalog as a covariate before acting on the per-stage model
    recipe.

**The decision that is not an engineering decision.**

12. The review economics do not close under ADR-005 as currently implemented, by 4 to 28x. The
    options are a guardian-primary approval model with staff as a risk-triggered second line, an
    O(1) review surface, a different price or entitlement structure, or some combination. Two
    independent reviewers with no shared context reached the same conclusion. This needs an owner
    decision and probably an ADR, not a code change.

---

## Appendix: reviewer roster and finding index

| ID | Remit | Findings |
|---|---|---|
| A1 | blank-slate systems architecture, unit economics, risk | 68-item checklist |
| A2 | blank-slate children's publishing and narrative craft | 63-item checklist |
| A3 | blank-slate LLM product economics and operations | 60-item checklist |
| B1 | framework coherence, F1-F8 traceability | 16 |
| B2 | pipeline architecture, seams, scale, observability | 24 |
| B3 | evidence, statistics, pre-registration, instruments | 23 |
| C1 | skeleton development and checking | 16 |
| C2 | fill stage, selection, binding, delivery | 19 |
| C3 | diversity, decision regurgitation, instruments | 15 |
| C4 | safety, moderation, human approval | 17 |
| C5 | cost engineering and per-stage model selection | 16 |
| C6 | testing, validation, register integrity | 15 |

Full findings, each with severity, `file:line` locus, problem statement, recommendation and a
falsifier, are in the twelve reviewer files. Four reviewers issued retractions after the evidence
worktree was supplied; those retractions are recorded at the head of their files.

## Related

- [2026-08-22 research brief](./cyo-generation-research-brief-2026-08-22.md), the subject
- [2026-08-10 research brief](./cyo-generation-research-brief-2026-08-10.md)
- [Diversity test register](./diversity-test-register.md)
- `skeleton-sourcing-test-plan-2026-08-21.md` (on the sourcing branch, not this one)
- [Architecture re-specification](./architecture-respecification-2026-08-10.md)
