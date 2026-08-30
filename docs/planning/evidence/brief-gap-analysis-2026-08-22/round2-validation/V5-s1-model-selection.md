# V5 adversarial validation: the S-1 skeleton-author experiment and the model recipe built on it

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `scratchpad/validation/v5_stats.py`, `scratchpad/validation/shellrows.json`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.

Scope: brief section 4.2, synthesis section 1.5, prior findings B3-2/3/4/5/6/7, B1-3, C1-15.
Everything numeric below I re-derived from the committed records with my own code. No numbers were
copied from a prior finding, a `summary.md`, or the register. Scripts:
`scratchpad/validation/v5_stats.py`, `v5_deep.py`, `v5_disc.py`, `v5_size.py`, `v5_topo.py`,
`v5_fisher.py`, `v5_speed.py`. Raw per-shell frame: `scratchpad/validation/shellrows.json`.

Conventions: Spearman with average ranks; permutation tests are **exact** (7! = 5040 orderings at
leg level, 6! = 720 leave-one-out); 2x2 tests are Fisher exact two-sided; Mann-Whitney is exact
where the split count allows and 200k-resample otherwise.

Data as I read it, independently: 42 tool-assisted records (7 legs x 2 cells x 3 replicates),
21 blind records (7 legs x cell A x 3 replicates). Pass counts I recomputed from
`strict_pass` and they match the brief's table exactly: fable 6/6, opus 6/6, kimi 5/6, sonnet 4/6,
haiku 3/6, flash 3/6, pro 0/6.

---

## Claim 1 (B3-4): pass rate vs distance-from-catalog, Spearman -0.982, p=0.0016

**Verdict: the STATISTIC REPLICATES exactly. The CAUSAL INTERPRETATION does not survive, and the
finding as written in synthesis 1.5 is wrong in the direction that matters. Severity: downgrade
from critical to medium, and rewrite.**

### What I did to break it

Five independent attacks: (a) re-derive the statistic under five different definitions of
"distance-from-catalog" rather than the prior agent's one; (b) exact permutation and full
leave-one-out; (c) drop to shell level (n=38) where the outcome and predictor are measured on the
same object; (d) split the distance metric into the feature subspace the validator gate polices and
the subspace it does not, and re-run on each; (e) benchmark against the catalog's own internal
spread, which nobody had computed.

### Evidence and arithmetic

**(a) It replicates, and it is not fragile.** Per-leg pass rate against five distance definitions,
exact two-sided permutation over 5040 orderings:

| distance definition | Spearman | exact p |
|---|---|---|
| min over shells of per-shell min-to-catalog (the `summary.md` column) | -0.9274 | 0.00794 |
| **mean over shells of per-shell min-to-catalog** | **-0.9820** | **0.00159** |
| **median over shells of per-shell min-to-catalog** (the prior agent's) | **-0.9820** | **0.00159** |
| mean over shells of per-shell mean-to-catalog | -0.8729 | 0.01905 |
| median over shells of per-shell mean-to-catalog | -0.8729 | 0.01905 |

-0.9820 / p=0.00159 reproduces B3-4's -0.982 / p=0.0016 to the digit. Leave-one-out on the median
definition: rho ranges -0.971 to -0.986, every exact p <= 0.0111. On the `summary.md` definition:
rho -0.883 to -0.986, every p <= 0.0444. **No single leg drives it.** At shell level (n=38 scorable)
passing shells are closer to the catalog than failing ones: median 0.1246 vs 0.1797, permutation
Mann-Whitney p = 0.00003. Stratified: cell A 0.0999 vs 0.1719, cell D 0.1340 vs 0.2403. Within-leg
(pass vs fail inside the same leg, which removes every leg-level confound) 19 of 25 concordant
pairs. The association is real at every level of aggregation. B3-4's headline arithmetic is sound.

I also closed B3-4's own stated worry, against it: strip the topology-mismatch flag out of the
metric and renormalise, and rho is **-0.8729, exact p = 0.01905**. The self-declared topology
component is not the driver.

**(b) But at leg level the predictor is rank-identical to graph size.** Mean node count per leg:

| leg | pass rate | mean nodes | mean min-to-catalog |
|---|---|---|---|
| claude-opus | 1.000 | 37.67 | 0.1056 |
| claude-fable | 1.000 | 35.67 | 0.1085 |
| moonshot-kimi-k3 | 0.833 | 34.50 | 0.1175 |
| claude-sonnet | 0.667 | 29.33 | 0.1574 |
| deepseek-v4-flash | 0.500 | 28.75 | 0.1751 |
| claude-haiku | 0.500 | 25.67 | 0.1996 |
| deepseek-v4-pro | 0.000 | 25.50 | 0.2277 |

Spearman(distance, mean nodes) = **-1.0000 exactly**, exact p = 0.0004. Spearman(pass rate, mean
nodes) = **+0.9820, exact p = 0.00159**, numerically identical to the headline result. The partial
correlations are literally undefined (`nan`) because the two predictors are perfectly rank-collinear
at n=7. **At the resolution B3-4 and synthesis 1.5 use, "distance from catalog" and "how many nodes
the leg built" are the same variable, and no analysis of these seven points can separate them.**

**(c) The reason is a scale mismatch nobody checked.** Cell D's committed catalog skeletons carry
91, 95, 99, 101 and 105 nodes. Cell D's shells carry 17 to 45 nodes, because the run passes
`--allow-mvp` and `MVP_MAX_NODES = 45` (`validator/band_profile.py:115`), while the production
envelope for `(10-13, short, prose)` is `(90, 140, 28)`. Every cell-D shell is legally capped at
half the size of every cell-D catalog member. Over the entire admissible range [8, 45], canberra
distance on `n_nodes` to a 91-node target is strictly decreasing in node count. So in cell D
"closer to the catalog" is a mechanical restatement of "used more of the node budget". Confirmed
empirically: shell-level Spearman(nodes, distance) = -0.7195 in cell D. **The closest shell in the
whole grid is roughly half the size of the thing it is supposedly imitating.** That is not mimicry.

**(d) The discrimination test the task asked for, and it favours the benign explanation.** I split
`structural_distance` into two sub-metrics and recomputed everything from the shells:

- **Gate-constrained subspace** (n_nodes, n_endings, n_choices, mean_branching, decision_ratio,
  max_depth, min_ending_depth, reconvergence_ratio, ending-kind histogram, topology flag, every one
  of these is directly policed by L1-7 budgets, the min_endings/min_decisions floors, PL-18
  admissibility, PL-25 first-decision depth, or forbidden ending kinds): Spearman **-0.9820,
  exact p = 0.00159**; shell-level Mann-Whitney **p = 0.00023**.
- **Gate-free subspace** (n_variables, n_conditions, n_effects, valence histogram, the features the
  gate does not constrain): Spearman **-0.6728, exact p = 0.108**; shell-level Mann-Whitney
  **p = 0.076**. Not significant at either level.

The entire association lives inside the feature space the validator explicitly polices. That is the
task's alternative causal story, and it is the one the data supports: the gate says (for cell A under `--allow-mvp`) "8-45 nodes, branch depth 0..7,
>= 2 endings, >= 2 decisions, admissible topology, no DEATH or CAPTURE endings"; the catalog is made
of objects obeying those same rules; a shell that passes is therefore near the catalog *on exactly
those axes* by construction. **Passing and catalog-likeness are the same constraint measured twice,
not a reward for conformity.**

The honest caveat on my own test: for the young bands the gate-free subspace is nearly empty. Tier-1
stories are forbidden to declare variables (`Storybook` model validator: "tier 1 stories must not
declare variables"), so `n_variables = n_conditions = n_effects = 0` for all five cell-A catalog
members and for 41 of 42 shells. Three of the eleven numeric features contribute exactly zero
variance, and the gate-free test is running on a valence histogram and little else. So my
discrimination is directionally clear but under-powered by the same metric it is auditing.

**(e) No shell is a catalog clone; the closest shells are not near-clones of anything in the
catalog.** I scored all 190 shell-to-catalog pairs. **Zero** fall below `TAU_CELL = 0.05`. The global
minimum is 0.0507 (Opus, cell A, replicate 3): B3-4's "1.4% margin from the anti-clone gate" is
arithmetically correct and rhetorically misleading, because a 0.0507 pair *passes*, and it is one
pair out of 190; across the 38 per-shell minima the 5th percentile is 0.0659 and the median 0.1464, so
0.0507 is the low tail of a distribution that sits well clear of the floor, not a near-breach regime.

Two corrections to B3-4's supporting detail: Opus produced the 1st and 4th closest shells, not "two
of the three closest" (the top four are Opus 0.0507, Kimi 0.0630, Fable 0.0665, Opus 0.0671). And
four shells carry no distance at all (`shell not coercible against any of 5 peers`): flash A r1/r2,
pro D r1/r2. All four are failures, all four are DeepSeek. That is missing-not-at-random data
excluded from the distance side while remaining in the pass-rate denominator, it biases DeepSeek's
measured distance *downward*, so the correlation is conservative, but the mechanism is confounded
with the outcome and should be handled by scoring an uncoercible shell at distance 1.0, not by
dropping it.

### What does survive, and it is worth keeping

Two residues of B3-4 are real and neither is in the brief:

1. **Passing shells sit in the bottom 5% of the catalog's own diversity distribution.**
   `ws5_floor_baseline.json` records the catalog's same-cell structural spread over 145 pairs:
   min 0.000469, p05 0.154657, p25 0.298321, median 0.3799. Of the 38 scorable shells, **22 sit
   below the catalog's own p05, and 21 of those 22 passed**; of the 16 at or above p05, only 6
   passed (Fisher exact **p = 0.00015**). 37 of 38 sit below p25. Applying the programme's own
   yardstick to its own output: the gate certifies graphs that are less distinct from the catalog
   than the catalog's members are from each other. That is a statement about the *gate's admissible
   region being narrow*, which is defensible and actionable. It is not a statement about model skill
   or model mimicry, which is what synthesis 1.5 makes it.

2. **The real convergence is shell-to-shell, and it is vendor-independent.** I scored all 342
   in-cell shell-to-shell pairs. **Seven breach `TAU_CELL = 0.05`**, five in cell A, two in cell D,
   and every one is cross-vendor: Opus/Kimi at **0.0191**, Opus/Sonnet 0.0329, Fable/Kimi 0.0335,
   Opus/Fable 0.0376, Sonnet/Kimi 0.0476, Opus/Kimi 0.0395 (D), Fable/Opus 0.0478 (D). Three
   different labs, one graph. In cell D, three distinct legs independently emitted 45 nodes /
   91 choices / mean branching exactly 3.000 / decision ratio 0.968. **Zero of 190 shell-catalog
   pairs breach the floor; seven of 342 shell-shell pairs do.** The programme's stated fear,
   generated structure collapsing to a mode, is happening, but between *generations*, not toward
   the *catalog*, and it crosses vendor boundaries, which means the cause is the brief plus the
   gate, not the model. This is a better-evidenced version of what synthesis 1.5 was reaching for,
   and it points at a different fix.

### What prior review missed

B3-4 computed a correct statistic and then chose the wrong one of the two readings it itself
offered. It missed: the perfect rank-collinearity with node count (rho = -1.000) that makes the
leg-level result uninterpretable; the MVP-vs-production scale mismatch that generates that
collinearity; the gate-constrained/gate-free split that discriminates the two causal stories; the
catalog-internal baseline that turns the finding from "models mimic" into "the gate is narrow";
and the cross-vendor shell-shell floor breaches, which are the actual convergence event in the data.
It also over-read the 0.0507 margin (that pair passes; nothing in the grid is a clone) and
mis-stated which legs own the closest shells. Synthesis 1.5 then hardened B3-4's weaker reading
("the model recommendation actively reinforces the defect the programme exists to remove") into the
lead of section 1, which the evidence does not support.

---

## Claim 2 (B3-2): degenerate primary endpoint, all-zero permutation vector, post-halt revision

**Verdict: CONFIRMED in every particular. Severity: critical. This is the strongest claim in the
cluster.**

Verified directly:
- Registered primary endpoint, from register row S-1: *"repair rounds to strict pass, pooled across
  cells, permutation test over leg assignment, 10,000 permutations, alpha 0.05 ... All other
  endpoints exploratory, decision-inert."*
- Blind arm (`runs/e1r3-2026-08-21/summary.md`): statistic 2.571, **p = 1.0000**. I read all 21
  records: **19 of 21 sit at `attempts: 7, repair_rounds: 6`**, i.e. exactly the cap. Fully censored.
- Tool-assisted arm (`runs/e1r3-tools-2026-08-21/summary.md`): statistic **0.000**, p = 1.0000. I
  read all 42 records: **`attempts: 1, repair_rounds: 0` in all 42**. The permutation test that the
  registration named as the sole decision-bearing analysis is run on an all-zero vector. Confirmed.
- The halt: `runs/e1-2026-08-21/` has 20 grid-point records per cell x 4 cells but only 10 shells on
  disk; the README records 76 of 80 shells lost to OpenRouter HTTP 402 at $400.92 of $400.00.
- The revision: `run.json` for the registered run has 5 vendors x 4 cells x 4 replicates; the
  delivered arms have 7 legs x 1-2 cells x 3 replicates. Slate, cells and replicates all changed
  after the halt.

Two things I will say in the register's defence, because an adversarial review that only prosecutes
is not doing its job. The register **does** disclose all of it, at length, including the phrase
"Declared with full data contact stated: 4 completed shells' exploratory records were seen, no
primary result existed", and it explicitly labels the blind p=1.0 as censoring rather than
equivalence. The test plan's section 10 declares the budget revision with the same candour. The
defect is **the brief**, which discloses the blind degeneracy and not the tool-assisted one, and
which reports the promoted exploratory endpoint with no indication that it was pre-registered as
decision-inert. One correction to B3-2: the plan's section 10 says "2 cells x 3 replicates x 3 legs
= 18 shells" while the delivered grid is 7 legs x 42 shells, so the revision's own arithmetic does
not match what ran.

**What prior review missed:** the tool-assisted arm is *also* censored, and heavily. `tools-meta.json`
puts **14 of 42 records at exactly the 10-invocation cap, 11 of them FAIL**. The brief presents the
tool-assisted arm as the clean condition that rescued the experiment; a third of its observations
are right-censored by the same class of defect that voided the blind arm, and the brief does not say
so. Two more records have `checker_runs: null`.

---

## Claim 3 (B3-3): the deciding arm ran outside the harness on a hand-written file

**Verdict: CONFIRMED with one material correction. Severity: high, not critical.**

Confirmed: there is **no `run.json`** in `runs/e1r3-tools-2026-08-21/`; all 42 records read
`attempts: 1, repair_rounds: 0, latency_s: 0.0, input_tokens: null, output_tokens: null,
finish_reasons: []`; the only record of the iteration loop is `tools-meta.json`, a hand-maintained
dict of `checker_runs` / `reported` plus three free-text notes. No token or cost accounting exists
for the arm every conclusion comes from, which also means F7's cost claims cannot be computed from
it. Two entries have `checker_runs: null`; four records have no catalog distance.

**The correction.** `--score-shell` is a real harness mode (`compare_skeleton_authors.py:748-838`).
It re-parses the submitted shell, re-runs `check_skeleton.py --strict --allow-mvp`, runs
`check_graph_structure.py`, recomputes the catalog distances, and persists the record. So
`strict_pass` and the distances **are** harness-computed on the real artifact, not hand-entered.
I re-derived all 38 scorable `min_catalog_distance` values from the shells and got **zero mismatches**
against the committed records, and I checked all 42 `tools-meta.reported` values against
`strict_pass` and got **zero mismatches**. B3-3's phrasing "the entire record is a hand-maintained
three-field file" overstates it: the *outcome* is instrumented, the *process* is not. What is
uninstrumented is precisely the deciding endpoint the brief's table reports (checker invocations),
plus every token, latency and cost figure.

The structural asymmetry B3-3 raises stands and is the more serious half: `attempts: 1` everywhere
means the harness saw one submission per shell, so a subagent leg iterated statefully in-session
with direct CLI access while an OpenRouter or Modal leg could only receive a relayed stateless loop.
Nothing in the artifacts records which each non-Anthropic leg got. `UW-C320` concedes the mode does
not exist in the harness.

---

## Claim 4 (B3-7): power arithmetic

**Verdict: CONFIRMED. My independent arithmetic matches B3-7 to the digit. Severity: critical.
I extend it: the convergence-speed claim fails its own test too.**

All 21 pairwise Fisher exact tests on the tool-assisted pass counts (n=6 per leg), computed fresh:

| contrast | Fisher p | Bonferroni x21 |
|---|---|---|
| fable 6/6 vs pro 0/6 | **0.0022** | 0.045 |
| opus 6/6 vs pro 0/6 | **0.0022** | 0.045 |
| kimi 5/6 vs pro 0/6 | **0.0152** | 0.318 |
| sonnet 4/6 vs pro 0/6 | 0.0606 | 1.000 |
| fable/opus 6/6 vs haiku 3/6 | 0.1818 | 1.000 |
| fable/opus 6/6 vs flash 3/6 | 0.1818 | 1.000 |
| fable/opus 6/6 vs sonnet 4/6 | 0.4545 | 1.000 |
| **fable/opus 6/6 vs kimi 5/6** | **1.0000** | 1.000 |

**3 of 21 nominally significant, 2 survive Bonferroni, and all three are against v4-pro.**
0/6 vs 6/6 at p = 0.0022 is the floor: no contrast at n=6 can be smaller. 6/6 vs 3/6 cannot beat
p = 0.18 at any effect size. Power: to separate a true 50% leg from a true 100% leg needs **n >= 9**
per arm (best case p = 0.0294); n = 6 tops out at 0.18.

**"Frontier Anthropic converges fastest" fails on its own endpoint as well as on pass rate.**
Checker invocations among passing shells: permutation test across the six legs with any passes,
**p = 0.435**. Fable+Opus (median 3.5) vs Kimi (median 5), exact Mann-Whitney over 6188 splits,
**p = 0.2612**. Nothing separates. And the family is internally incoherent: Haiku is an Anthropic
tier at 3/6, worse than Kimi's 5/6, so "a tool-assisted Anthropic tier" names a set whose internal
spread (3/6 to 6/6) is as wide as the entire between-family spread.

**"The hard band is not the hard part" is not a finding, and is confounded on top of that.**
Cell A 12/21 vs cell D 15/21, Fisher **p = 0.5204**. The one large difference is checker invocations
among passers: median 6.5 at cell A vs 3.0 at cell D. But the register records cell A closing
2026-08-21 and cell D closing 2026-08-22, **cell A ran first, for every leg**. A median that halves
on the second cell run by the same operator with the same subagent tiers after a documented topology
trap was diagnosed is exactly the shape of a learning curve, and neither the register nor the brief
separates band difficulty from run order.

**What survives of 4.2, exhaustively:** (i) tool-assisted beats blind (cell A only, like for like,
2/21 vs 12/21, Fisher p = 0.0025); (ii) deepseek-v4-pro failed all 6 tool-assisted attempts and is
separated from the two 6/6 legs; (iii) nothing else. Kimi K3 on the owner's own Modal endpoint is at
parity with both frontier Anthropic tiers.

---

## Claim 5 (B1-3): the blind arm is cell A only and the regimes differ on more than regime

**Verdict: CONFIRMED and understated. Severity: high.**

`runs/e1r3-2026-08-21/run.json` reads `"cells": ["A"]`, `"replicates": 3`. I counted the records:
21, all cell A. `runs/e1r3-tools-2026-08-21/` has 42, cells A and D. So the brief's headline
"2 in 21 versus 27 of 42" compares one cell against two. Like for like on cell A it is 2/21 vs
12/21 (Fisher p = 0.0025), still a real effect, but half the advertised gap.

B1-3 names two confounds. I count **five**, and they are not separable by any analysis of these
artifacts:
1. **Regime**: harness-mediated repair vs self-service checker.
2. **Budget**: 6 repair rounds vs 10 checker invocations.
3. **Statefulness**: the harness docstring is explicit that the repair loop carries "no chat
   history ... a repair round re-sends the previous JSON plus the feedback"; the tool-assisted
   condition is defined as "iterates in one session". Stateless vs stateful is a different
   experiment from harness vs self-service.
4. **Cell coverage**: A only vs A and D.
5. **Run order**: blind ran first; the tool-assisted run was launched after its failure modes
   (the PL-18/UW-C306 trap) had been diagnosed.

The register's conclusion "the authoring regime dominates the model axis" is drawn from a comparison
with five simultaneous differences. The *direction* is large enough that I would not bet against it.
The *attribution* to "regime" specifically, and F3's claim that this is "the single largest quality
lever we have measured", are not supported by this design. Note also that the blind arm's Anthropic
subagent legs carry `output_tokens: null` too, so the blind/tool-assisted cost comparison in F7
cannot be computed for any Anthropic leg in either arm.

---

## Claim 6 (B3-6): the judge panel behind "best prose"

**Verdict: CONFIRMED on the numbers. Severity: critical. One citation correction.**

Verified in `cyo-measurement-workplan-2026-08-12.md` section 7.8, W4 table, 9 book-cells:

| criterion | mean | SD |
|---|---|---|
| `dialogue` | 3.00 | **0.00 SATURATED** |
| `age_fit` | 4.14 | 0.38 |
| `voice` | 2.97 | 0.40 |
| `engagement` | 3.86 | 0.42 |
| `imagery` | 4.28 | 0.46 |
| `ending_quality` | 3.50 | 0.47 |
| `choice_quality` | 3.25 | 0.62 |

On a 1-5 rubric, the most discriminating criterion the panel owns has SD 0.62 across nine cells and
one criterion is exactly flat. A panel with that little spread cannot rank suppliers whose true
quality differs by less than about 0.6 rubric points, and no one has established that it does not.
W7 independently flags the same criterion (`AL-385`), so the weakness is attested twice by different
methods on different corpora.

**Citation correction to B3-6 and to the task brief.** The 84-verdict pool was not lost to `AL-362`.
`AL-362` is a distinct defect: `judge_book` handed a `Completion` object to a regex and a broad
handler swallowed every scoring, so the panel emitted an empty scorecard that read as flaky
endpoints. The pool loss is **`AL-379` / `UW-C257`**: `out/vendor-comparison/` held the 32-book run
and its 84-verdict pool, "exists on no checkout", and `git ls-files out/` was never non-empty. W4's
rule named that specific artifact; it ran on a 27-verdict replacement instead, which the workplan
declares as a stated substitution. Both defects are real and both bear on the fill-model claim, but
they are different findings and attributing the pool loss to AL-362 will not survive a check.

---

## Claim 7 (B3-5): a retracted supplier ranking was reinstated

**Verdict: CONFIRMED. Severity: critical. I add an internal contradiction the prior review did not
name.**

`AL-385`, 2026-08-14: *"W5's pre-committed consequence fired on its first real run: no pair of
bootstrap intervals separated, so Part IV's ranking is retracted rather than caveated, exactly as
agreed in advance."* The lesson's own text says thinness "is not grounds to renegotiate a rule
written down precisely because this outcome was likely."

Eight days later the brief publishes, at line 184: *"DeepSeek V4 Pro emerged as the best judged
prose at roughly a fifth the cost of the premium Western legs"*, and at line 69, F4: *"The best
prose model measured (DeepSeek V4 Pro)"*. `grep -rn "retract" ` over the brief returns nothing. No
new bootstrap intervals, no pair-separation count.

**The addition.** F6 of the same brief, 115 lines below F4, reads: *"The instruments that survive
are deterministic ... plus blinded raters used to confirm, never to produce, rankings."* F4 is a
ranking produced by blinded raters. The brief states the rule and breaks it in the same section,
and the ranking it breaks the rule to publish is the first leg of the per-stage recipe.

---

# Recommendation review

## "Re-score S-1 with distance-from-catalog as a covariate"

**Low value as stated; do the shell-level version or nothing.** At leg level the covariate is
rank-identical to mean node count (rho = -1.000), so a seven-point model containing both is
unidentifiable: I tried, and the partial correlations return `nan`. A covariate that is a perfect
proxy for a variable you are not modelling does not adjust anything; it relabels it.

What is worth doing, and costs nothing because the data is committed: report the shell-level
relationship stratified by cell, with node count in the model, and with uncoercible shells scored at
distance 1.0 rather than dropped. That analysis exists in this document (cell A partial
Spearman(distance, pass | nodes) = -0.769; cell D = -0.579) and it says the association is not only
size. Then report the gate-constrained/gate-free split, because that is the analysis that decides
what the association *means*, and it is the one nobody ran.

Separately, and this is free: put `min_catalog_distance` in section 4.2's table. It is already
computed and committed. Whatever it means, hiding a pre-registered exploratory endpoint that
correlates at -0.98 with the reported one is not defensible.

## "Add a novelty term to the pass criterion"

**Do not do this. It is the wrong fix for the right worry, and it creates a metric that is trivially
gamed.** Four reasons:

1. **The gate it asks for already exists and already passes.** `TAU_CELL = 0.05` is the committed
   anti-duplication floor. Zero of 190 shell-catalog pairs breach it. Adding a catalog-novelty term
   to the pass criterion would gate on a condition no observation in the dataset violates.
2. **It targets the wrong axis.** The seven floor breaches in this data are shell-to-shell and
   cross-vendor, not shell-to-catalog. A catalog-distance term in the pass criterion would have
   caught none of them. The corpus that needs the floor applied to it is the *generated* corpus at
   admission time, against everything already admitted to the cell including other candidates from
   the same run. That mechanism also already exists (`diversity/incell.py`); it is simply not
   pointed at generated shells.
3. **It penalises gate compliance.** The association lives in the gate-constrained feature subspace
   (rho -0.982, p 0.0016) and not in the gate-free one (rho -0.673, p 0.108). A novelty term over
   `structural_distance` would therefore, in practice, reward divergence on node count, depth,
   ending count, decision ratio and topology, the five things the validator exists to constrain. It
   sets the two gates against each other and the author will discover which one is cheaper to
   satisfy.
4. **It is gameable, and cheaply.** `structural_distance` is a fixed 11-feature canberra mean plus
   two histograms plus a flag. One feature moving from 0 to non-zero contributes
   `0.5 x (1/11) = 0.0455`, nine tenths of the entire `TAU_CELL` floor, from a single edit. In
   tier-1 cells three of the eleven features (`n_variables`, `n_conditions`, `n_effects`) are
   structurally zero for the whole catalog, so those levers sit at exactly the value where one
   token of change buys the most distance. (The tier-1 no-variables validator blocks that specific
   edit today, which is luck rather than design; the topology flag at weight 0.2 is a one-word
   change worth four `TAU_CELL`s and is *self-declared by the author*.) Making a metric with those
   properties part of a pass criterion invites the author to optimise it directly, and every
   author in this experiment is a model with the metric's definition available to it.

**Do instead:** apply the existing `TAU_CELL` floor to the generated corpus against itself and
against the catalog at admission time, as a *promotion* gate rather than an authoring pass
criterion, and report the catalog p05/p25 percentiles beside every candidate. That catches the
defect that is actually present in the data and does not put a gameable number in the author's
objective.

## The brief's own recipe: "fill with V4 Pro, author with a tool-assisted Anthropic tier, review with V4 Flash"

**The per-stage recipe does not survive. One of its three legs has no live support, one names a set
its own data contradicts, and one is uncited.**

- **"Fill with V4 Pro"**: rests on a ranking that a pre-registered rule formally retracted (claim 7),
  from a panel with one saturated criterion and a maximum SD of 0.62 (claim 6), on a verdict pool
  that no longer exists on any checkout (`AL-379`). The test plan itself is more careful than the
  brief here: it *suspends* the blind quality panel as unfunded and treats V4 Pro's prose quality as
  an open assumption to be carried as a covariate. **Correct statement:** V4 Pro is the
  cost-and-delivery-selected fill model; its quality is unranked pending a funded panel or a human
  anchor.
- **"Author with a tool-assisted Anthropic tier"**: the family spans 3/6 to 6/6, and Haiku (3/6) is
  indistinguishable from Opus (6/6) at p = 0.18. Kimi K3 (5/6) is indistinguishable from both 6/6
  legs at p = 1.00 and from their convergence speed at p = 0.26, and it runs on an endpoint the
  owner controls. **Correct statement:** author with any tool-assisted leg other than v4-pro; on
  this data Kimi K3 on the owner's Modal endpoint is at parity with the frontier tiers and is the
  cheapest of the parity set. The one supported negative is: do not use v4-pro as a structure author.
- **"Review first-pass with V4 Flash"**: the brief asserts this at line 169 with no citation, and
  the test plan calls v4-flash "the tier already trusted for first-pass review" without re-evidencing
  it. In the brief's own 4.2 table, v4-flash is the leg that "lost its call budget to unparseable
  output", a JSON-discipline failure, in a role whose entire output must be machine-parsed.
  **Correct statement:** unevidenced in this cycle; cite the review-model distillation work or drop
  it from the recipe.

What *does* survive from 4.2 and should be the whole of what the brief claims: **put the checker in
the author's loop** (direction robust, magnitude not attributable given five confounds), and **do
not use deepseek-v4-pro to author structure** (0/6, two named failure modes, separated from the top
legs at Bonferroni-corrected p = 0.045). Everything else in section 4.2 is a ranking of coin flips.

## What experiment would settle model selection, and what it would cost

The binding constraint is not money. Design:

- **Legs, 3**: one frontier Anthropic tier (Opus or Fable, not both, they are indistinguishable),
  Kimi K3 on the owner's Modal endpoint, deepseek-v4-flash. Drop v4-pro from the structure arm; it
  is answered. Drop the second Anthropic tier; that comparison is answered as "no difference".
- **n, 12 per leg per cell, 2 cells** = 72 shells. 12/12 vs 6/12 reaches Fisher p = 0.0137;
  10/10 vs 5/10 reaches 0.033; the current n = 6 tops out at 0.18. Twelve is the smallest n that
  detects a halving of the pass rate with margin.
- **Order counterbalanced**: half the replicates run cell D first. Without this the band-difficulty
  claim stays unavailable, as it is today.
- **One pre-registered primary endpoint, chosen to be uncensorable**: checker invocations to first
  strict pass, with the cap raised until fewer than 10% of observations are censored, or a
  right-censored analysis (log-rank on invocations-to-pass) declared in advance so a cap is a
  modelled feature rather than a void. Today's caps censored 19/21 in one arm and 14/42 in the other.
- **The tool loop instrumented in the harness** (`UW-C320`): checker invocations, tokens, latency and
  wall-clock recorded by the harness, not by hand. This is the single change that makes the arm
  auditable and makes F7's cost claims computable.
- **Distance reported three ways**: against the catalog, against the *other shells in the same run*,
  and split into the gate-constrained and gate-free components. Uncoercible shells scored at 1.0.
- **Cost**: both DeepSeek legs together were about $1.30 across 36 shells, so 24 flash shells is
  roughly $1. The Anthropic leg is subagent, zero marginal provider cost. Kimi is on the owner's own
  Modal endpoint. **Provider credit: under $5.** The real cost is engineering the tool-assisted
  driver into the harness plus the operator hours the loop consumes, which is exactly why
  `tools-meta.json` is hand-written, and exactly what needs to be paid for.

---

# What everyone missed

1. **The strongest structural result in the S-1 data is cross-vendor mode collapse, and no one has
   reported it.** Seven of 342 in-cell shell-shell pairs breach `TAU_CELL`, versus zero of 190
   shell-catalog pairs. Opus and Kimi at 0.0191. Three labs converging on 45 nodes / 91 choices /
   branching 3.000 / decision ratio 0.968 in cell D. The brief looks for model differences and the
   review looks for catalog mimicry; the data is shouting that the brief and the gate together are
   producing one graph regardless of who writes it.
2. **The MVP/production scale mismatch invalidates cross-cell distance comparisons.** Cell D's
   catalog is 91-105 nodes; cell D's shells are capped at 45 by `MVP_MAX_NODES`. Any
   distance-to-catalog statistic pooled across cells is partly a measurement of which budget the run
   used. This affects the register's exploratory Tier-2 endpoint as well as B3-4.
3. **The tool-assisted arm is censored too.** 14 of 42 records at the 10-invocation cap, 11 of them
   failures. The brief presents this arm as the one that rescued the experiment from censoring.
4. **Cell A ran before cell D, for every leg.** The "hard band is easier" conclusion, the only
   striking effect in the checker-invocation data (median 6.5 -> 3.0), is fully confounded with run
   order and with the mid-run diagnosis of the PL-18 trap.
5. **The missing distances are not missing at random.** Four uncoercible shells, all failures, all
   DeepSeek, silently dropped from the distance column while remaining in the pass denominator.
6. **`structural_distance` is 8-dimensional, not 11, for the young bands.** Tier-1 stories may not
   declare variables, so `n_variables`, `n_conditions` and `n_effects` are identically zero across
   the cell-A catalog and 41 of 42 shells. The programme's own headline instrument is blind to
   decisional structure in exactly the band where B3-1/C3-4 say decisional structure is what readers
   track. Any "novelty term" built on it inherits that blindness.
7. **The brief contradicts itself between F4 and F6**, 115 lines apart, on whether blinded raters may
   produce a ranking. F4 does what F6 forbids, and the recipe's first leg is the thing it does.
8. **The register and the test plan are better than the brief, consistently.** Every methodological
   defect in this cluster except the tool-arm censoring is disclosed somewhere in
   `diversity-test-register.md` or `skeleton-sourcing-test-plan-2026-08-21.md`, often in the exact
   language a critic would use. The failure mode is not sloppy experimentation; it is a summarising
   document that drops the caveats its own sources wrote down. The cheapest high-value fix in this
   whole cluster is to make section 4.2 carry the register's own qualifiers verbatim.
