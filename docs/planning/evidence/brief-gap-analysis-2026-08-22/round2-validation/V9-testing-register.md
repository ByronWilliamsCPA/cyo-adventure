# V9: Testing apparatus and honesty machinery, adversarial validation

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `/home/user/cyo-adventure/.worktrees/brief-evidence/`, `/tmp/claude-0/-home-user-cyo-adventure/95fe99a0-.../scratchpad/v9/`, `scratchpad/rulespy.py`, `scratchpad/unitrun.txt`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.
>
> **Re-read the testing-ladder findings against `6cc33aa5` (#780)** before citing any of them as
> current; that 134-file commit targets exactly this subject matter. The rule arithmetic is stale
> too: 58 distinct validator rule ids on `main`, not 55. The structural findings, including the
> post-hoc pre-registration edit in `bf7cad1` and the three rows still not voided, stand.

Target: synthesis section 4.7, prior findings `C6-testing-validation.md` (all 15) and
`B3-evidence-methodology.md` (pre-registration items).

**Posture.** Every claim below was attacked before it was confirmed. Where I could construct the
violation myself I did, with a positive control to prove the checker was live. Where a number was
doing load-bearing work I recomputed it with my own resolver rather than accepting the prior count.

**Trees used.** `/home/user/cyo-adventure/.worktrees/brief-evidence/` (the full evidence branch,
HEAD `6fc2b34`) for all documents and evidence. `src/`, `tests/` and `scripts/` are **byte-identical**
between that branch and `main` HEAD (`git diff --stat` over those paths returns only two
`scripts/` additions), so the unit-suite instrumentation was run in the main checkout, which is the
only one with `pytest` installed. That substitution is safe and I verified it rather than assuming it.

**Environment caveats that bound what I could verify, stated up front because they matter to
claim 2.** The clone is **shallow** (`.git/shallow` present, 52 commits reachable) and **`gh` is not
installed**. Commit SHAs older than the graft point and all PR/issue numbers are therefore
*unverifiable here*, which is not the same as unresolvable in principle. I have kept that category
separate from "resolves to nothing" throughout, because collapsing the two is exactly how the prior
figure went wrong.

---

## Verdicts at a glance

| # | claim | verdict |
|---|---|---|
| 1 | C6-8: 54/55 rules fire; SAFE-14 cannot | **CONFIRMED** by independent instrumentation (my 53-id subset is a strict subset of theirs, no contradictions). SAFE-14 is unfireable *by construction*. I attacked their method and **withdrew the attack**: their run was serial |
| 2 | C6-4: honesty machinery gameable; 57/240 refs resolve to nothing | **MECHANISM CONFIRMED AND STRENGTHENED** (clean 2x2). **NUMBER REFUTED: 4, not 57** |
| 3 | C6-5: diversity register has zero automated checks | **CONFIRMED**, unqualified. One repo-wide hit and it is a docstring |
| 4 | C6-6/7: experiments not third-party reproducible | **CONFIRMED on provenance; framing too strong.** S-1's deterministic half reproduced exactly, 42/42, zero disagreements |
| 5 | C6-10: golden corpora assert one bit | **CONFIRMED** (two bits, not one; neither is a verdict) |
| 6 | C6-2: script returns 3.2, not 2.3 | **CONFIRMED, and worse**: 2.3 needs a *second* method change the register does not disclose |
| 7 | C6-12: e2e drives `_CANNED_STORY`; no hollow-fill test | **CONFIRMED** |
| 8 | C6-11: no recorded provider responses | **CONFIRMED**, failure mode reproduced live |

Six additional integrity holes are in **What everyone missed**, including a **realised post-hoc edit
of three completed pre-registrations** (commit `bf7cad1`) that flipped D-7b's result from "at the
noise floor" to "below the noise floor".

---

## Claim 1 (C6-8): 54 of 55 validator rules can fire; the one that cannot is SAFE-14

**Verdict: CONFIRMED by independent measurement. I attacked the prior instrumentation and then
withdrew the attack, because their run was serial and the hazard I found does not apply to it.**

### Static half, independently reproduced

```
distinct rule ids referenced in src/cyo_adventure/validator/*.py: 55
CG-1..CG-5, CH-1..CH-8 (incl. CH-3a/CH-3b), L1-1..L1-8, L2-9..L2-15,
PL-15..PL-29, RL-13, SAFE-14, SR-1..SR-9
```

55 is right.

`src/cyo_adventure/validator/safety.py` is 57 lines and its entire body is:

```python
_ = story  # Phase-3 will use the story argument; retained for call-site stability.
return ValidationReport()
```

`check_safety` therefore cannot construct a finding under any input. `GateResult.safety_flagged` is
structurally always `False`. **SAFE-14 is unfireable by construction, not by wiring**, which is a
stronger statement than the dynamic run can make and does not depend on it. The gate docstring is
honest ("Phase-2 stub, always empty"); the brief's F2 claim that "safety classification" is among
the things "checked by code before any model or human judges anything" is the thing that is wrong.

### Dynamic half: independently corroborated, and a fairness correction I owe the prior pass

**I set out to attack the prior instrumentation and ended up confirming it.** Reporting both halves.

**The hazard is real.** `scratchpad/rulespy.py` patches `ValidationFinding.__init__` and dumps to a
single path from an `atexit` hook. `pyproject.toml`'s `addopts` contains **`-n=auto`**, so
pytest-xdist is on by default. Under xdist every worker registers that hook and writes the same
filename, so workers clobber each other. I measured the damage on one module
(`tests/unit/test_corpus_layer2.py`, 15 tests) with a per-worker-sharded plugin:

```
merged across all workers : 10 ids  [L1-6 L1-7 L2-9 L2-10 L2-11 L2-12 PL-17 PL-24 PL-29 RL-13]
  dump-gw0 : 8    dump-gw1 : 6    dump-gw2 : 7    dump-gw3 : 7    dump-master : 0
```

The controller records nothing; a worker records a 60-80% subset. My own first run hit exactly this
and produced no usable dump.

**But the prior run did not hit it, and I verified that rather than assuming it.** Its log
(`scratchpad/unitrun.txt`) contains **zero** occurrences of `bringing up nodes...`, has a single
uninterrupted 72-dot progress stream, and ends `8561 passed, 9 skipped in 867.12s (0:14:27)`. That is
a serial run, as its write-up states. **The hazard did not corrupt it and I withdraw the implication
that it did.** It remains a genuine trap for anyone re-running the measurement, because `-n=auto`
makes xdist the default and the failure is silent, so it is worth recording as a reproducibility note
rather than as a defect in the finding.

**My independent measurement.** The full-suite re-run did not finish inside my window (the tail is
`test_skeleton_mutation_m1/m4`, slow property tests). I therefore ran my sharded, call-site-recording
plugin over a targeted 54-module subset covering every validator, gate, corpus, policy, band,
reading-level, character, series, skeleton, choice-grammar, topology, safety, fill, moderation,
orchestrator and publishing test module: **2,430 passed, 9 skipped in 58.8s**, roughly 28% of the
suite.

```
static rule ids in validator/          : 55
constructed during my subset run       : 53
NEVER CONSTRUCTED                      : ['L1-8', 'SAFE-14']
constructed but absent from static set : []
rules constructed ONLY from test code  : []      <-- none; every rule has a real production call site
```

Cross-checking my set against the prior pass's committed `ruledump.json` (54 ids):

```
in theirs, not mine : ['L1-8']     (fires in a module outside my selection)
in mine, not theirs : []
```

**My result is a strict subset of theirs with no contradictions.** Their 54 stands, and the one rule
that never fires anywhere is `SAFE-14`. Claim CONFIRMED by independent measurement.

**Two things my instrument adds that theirs could not.**

1. **No rule is test-only.** Because I recorded the calling file, I can state that all 53 rules
   observed were constructed at least once from a path under `src/cyo_adventure/`, never solely from
   test code. The prior instrument recorded ids without provenance, so "the rule fires" could in
   principle have meant "a test built the object directly". It does not. This *strengthens* the prior
   finding.
2. **The twelve thin rules reproduce exactly.** Construction counts, with the number of distinct
   production call sites:

   ```
   CG-5 1   CH-3a 1   PL-28 1   SR-2 1   SR-7 1
   CH-5 2   CH-7 2    PL-21 2   PL-22 2  SR-1 2   SR-4 2   SR-6 2
   ```

   Identical to the prior pass's list, from a different instrument on a different slice.
   **`PL-28`, the MVP/Test-seed firewall standing between a prototyping shell and a child-facing
   book, is constructed exactly once**, from one production site. It is proven reachable and not
   proven to discriminate: nothing shows it accepts a production seed while rejecting an MVP one at
   the boundary. That is the most consequential single line in this section.

### Net

Claim CONFIRMED on both halves, and the SAFE-14 half never needed the run at all: a function whose
body is `return ValidationReport()` cannot emit a finding, so `GateResult.safety_flagged` is
permanently `False` and the gate's safety layer contributes nothing. The brief's F2 should stop
listing "safety classification" among the things code checks before any model or human judges,
because safety is entirely `moderation/`, whose Stage 0 is two external ML services with a
documented Perspective sunset of 2026-12-31.

The one thing I would add to the prior finding is the **reproducibility note**: `-n=auto` in
`addopts` means the next person to re-run this measurement gets xdist by default and, with a
single-file dump, a silently wrong answer. The instrumentation should be committed with per-worker
sharding rather than left in a scratchpad.

---

## Claim 2 (C6-4): the honesty machinery is gameable, and "57 of 240 applied refs resolve to nothing"

**Verdict: MECHANISM CONFIRMED AND STRENGTHENED. THE NUMBER IS REFUTED, and overstated by roughly
an order of magnitude.**

### The mechanism: reproduced exactly, with a cleaner control than the prior pass used

I copied the live log, took `AL-514` (status `open`, the PL-18 topology-trap lesson), and rewrote its
last two cells to `| applied | fixed it, see the thing |`. Both checkers pass:

```
check_lessons_log.py  --log log_gamed.md
  ok: log_gamed.md is well formed
       513 lesson(s): accepted=3, applied=241, open=267, rejected=1, superseded=1

check_work_linkage.py --lessons-log log_gamed.md
  ok: unscheduled-work-register.md satisfies the work-linkage contract
```

Baseline for comparison: `applied=240, open=268`. Both figures reproduce the prior pass exactly.

The prior pass's positive control showed the linkage checker was live. I ran a full **2x2** instead,
which isolates the actual defect rather than merely proving the checker runs. I removed the
register's only citation of `AL-514` (`UW-C306`, rewritten to a dangling id) and crossed that with
the lesson's status:

| register cites AL-514 | status `open` | status `applied` |
|---|---|---|
| yes | PASS | PASS |
| **no** | **FAIL** (`lesson 'AL-514' status is not applied/rejected/superseded and is not cited by any row in cluster C`) | **PASS** |

The bottom row is the finding. The scheduling obligation is real and enforced, and **flipping one
cell to `applied` deletes it**, while the only thing standing between that and a green run is
`check_lessons_log.py:208`'s `not row["Ref"]`, a non-emptiness test. One cell edit, two green
checkers, and the lesson leaves the work register's schedule. Confirmed.

### The number: my own resolver, and why 57 is not defensible

The prior finding classified the 240 `applied` refs as "144 name a path that resolves, 34 look like a
commit/SHA, 5 name a PR or issue, and 57 are prose that resolves to nothing checkable". Note that
"look like" is a shape test, not a resolution: the 34 and the 5 were never resolved either.

I built an independent resolver over the whole repo: a `git ls-files` path index with exact and
trailing-suffix matching (so `validator/policy.py` correctly resolves to
`src/cyo_adventure/validator/policy.py`), a test-node-id index, a `git cat-file -e` SHA probe, a
row-id index over every `docs/planning/*.md` table, and a symbol index over `src/`, `scripts/`,
`tests/` and `frontend/src/`. I then scored each of the 240 refs under two explicit definitions.

**Definition 1, "the ref contains no machine-checkable anchor of any kind":**

```
4 of 240
  AL-025  this review; leads chased manually and closed
  AL-026  45 shallowest failure leaves converted to vigor-costing pass-throughs; median read 5 -> 20 ...
  AL-061  Execution plan Task R4 "CONFIRMED 2026-07-29" block; design plan section 3.4 "G1-R ..."
  AL-062  Design plan section 3.4 "VOCATIVE NUDGE MEASURED AND REJECTED 2026-07-29" block; ...
```

And of those four, `AL-061` and `AL-062` name real documents by informal title and a dated block
heading inside them, which a human can follow in one grep. The genuinely un-followable set is
**AL-025 and AL-026, two rows**.

**Definition 2, the strict one, "the ref contains no anchor that pins a specific change" (SHA, PR, or
test node id, i.e. a bare file path is not proof a lesson was applied):**

```
140 of 240
```

Neither definition produces 57. I could not construct a consistent rule that does. The prior figure
appears to have been produced by bucketing refs by surface shape and treating the residual as prose,
where the residual includes refs that name a code symbol (`skeleton_match.is_continuation_skeleton`,
`_RepairContext.max_tokens`, `_drop_offenders`, `pairwise_shared_grams`, all of which I resolved by
grep to a real definition site) and refs whose path is dotted rather than slashed.

Full tiering of the 240:

| tier | n | meaning |
|---|---|---|
| A | 212 | resolves here: an existing path, a real test node, a resolvable SHA, or a real register row |
| B | 15 | SHA- or PR-shaped, **unverifiable in a shallow clone with no `gh`**, not counted either way |
| C | 8 | resolves only to a code symbol found by grep |
| D | 1 | names an artifact that is absent |
| E | 4 | prose only (Definition 1 above) |

(212 + 15 + 8 + 1 + 4 = 240. Tier C includes `AL-045` and `AL-431`, which my first pass
mis-tiered as prose because their symbols are dotted (`skeleton_match.is_continuation_skeleton`,
`_RepairContext.max_tokens`); both resolve by grep to a real definition site, so I moved them.)

**This is where I am correcting the prior review, and it matters.** "57 of 240 applied refs resolve
to nothing" is the single most quotable number in section 4.7, it is the one an external reader would
carry away, and it is wrong by about 14x under the reading its own words invite. The *finding* it
supports is nevertheless correct and I would keep it, restated: **the checker verifies only that
`Ref` is non-empty, so the strength of the evidence is entirely a matter of author discipline, and
that discipline is in fact high**, 212 of 240 refs resolve today. The hole is that nothing prevents
the discipline from lapsing, and the two rows where it did lapse (`AL-025`, `AL-026`) are exactly
what the unchecked path produces.

### A sharper defect the prior pass missed: ref rot

21 of the 240 `applied` refs contain at least one anchor that no longer resolves. Most are artifacts
of my own path regex over globs (`out/*.filled.json` yielding `filled.json`) or of symbols that are
constants and classes rather than `def`s, and I discarded those. The genuine ones:

- **`AL-017`** cites `tests/unit/test_rule_catalog_lockstep.py`. That file exists nowhere in the
  repo; the test was renamed to `tests/unit/test_validator_rules_catalog.py`. The ref has been
  dangling since the rename and no checker noticed.
- **`AL-256`** cites `renamed_P.json`, absent from the tree.

A ref that resolved when written and rots later is strictly worse than a prose ref, because it reads
as verifiable and is not. Nothing in the contract or the checker addresses the rot direction.

---

## Claim 3 (C6-5): the diversity register has zero automated checks

**Verdict: CONFIRMED, without qualification.**

`.github/workflows/planning-linkage.yml` runs exactly three steps, and I read all three:
`check_work_linkage.py`, `check_lessons_log.py`, `check_known_vulnerabilities.py`. None takes the
diversity register as an input; none has a default path pointing at it.

Repo-wide sweep for any reference to the document from anything executable:

```
git grep -n "diversity-test-register" -- .github .pre-commit-config.yaml scripts noxfile.py Makefile
  scripts/compare_skeleton_authors.py:13:   `S-1` (`docs/planning/diversity-test-register.md` section F):
```

One hit, and it is a **docstring**. `.pre-commit-config.yaml`'s hooks are `check-work-linkage`,
`check-lessons-log`, `check-known-vulns`, `check-pytest-raises-scope`, `check-rad-citations`,
`check_no_em_dash`; none touches it.

**I prototyped the missing checker to test whether it would actually find anything.** It would,
in about forty lines. The register's preamble (lines 9-10) declares a status vocabulary:
`queued` / `running` / `done` / `blocked` / `retired`. Parsing the 30 rows in Status-bearing tables,
**7 carry a status outside it**:

```
line   71  D-2     "halted at the guard battery, not rated"
line 1100  M-2     "partially done, DETERMINISTIC PRE-TEST; the fill-and-rate half is un..."
line 1243  R2-1b   "re-specified, unblocked; cost now LOWER than proposed"
line 1244  M-3     "re-specified; blocked on a schema field, not a metric"
line 1245  R1-1    "re-specified, unblocked"
line 1246  R1-3    "re-specified; run BEFORE R2-1b"
line 1247  R2-4    "re-specified, unblocked"
```

Three undeclared states (`halted`, `partially done`, `re-specified`) have accumulated without the
preamble being updated. Id-uniqueness and falsifier-non-emptiness both pass today, which is worth
saying: the register is well maintained by hand. But "well maintained by hand" is a statement about
the current maintainer, not about the document, and the drift above is what an unenforced
vocabulary looks like after four weeks.

One nuance worth adding in the register's favour, and one against it. In its favour: the workflow's
`pull_request` trigger includes `docs/planning/**`, so editing the register *does* fire the job. The
job simply has nothing to say about the file it was woken for. Against it: the document is 1,287
lines carrying every falsifier and every pre-registered margin in the programme, and it has no
id-uniqueness check, no status-vocabulary check, and no check that a row has a falsifier at all,
while the *scheduling* register next door has a 2,909-line enforcer. The asymmetry is real and it is
backwards.

---

## Claim 4 (C6-6 / C6-7): the load-bearing experiments are not third-party reproducible

**Verdict: CONFIRMED on provenance, but the prior framing undersells what does reproduce, and I am
correcting one point in the programme's favour.**

I attempted actual reproduction on two experiments.

### Experiment 1: S-1 tool-assisted (`runs/e1r3-tools-2026-08-21`), the decision-bearing run

**What reproduces, exactly.** I re-ran `check_skeleton.py --strict --allow-mvp` over all 42 committed
shells and compared per-shell against each record's `strict_pass`:

```
re-run pass: 27  fail: 15
matched shells: 42
DISAGREEMENTS: 0
```

27 = 12 (cell A) + 15 (cell D), matching the register to the shell, with **zero per-shell
disagreements**, which is a stronger check than the aggregate the prior pass reported. The
deterministic half of S-1 is genuinely reproducible and that deserves saying plainly.

**What is missing, verified item by item.**

- **No `run.json` at all** in the tool-assisted directory. Confirmed absent. The sibling blind run
  `e1-2026-08-21/run.json` exists and carries `started_at`, `mock`, `vendors`, `cells`,
  `replicates`, `max_repair_rounds`, `max_tokens` and two absolute paths, and **no git SHA, no
  temperature, no top-p, no seed, no resolved model id**. So the better-instrumented run is still
  missing every provenance field, and the run the decision rests on has no header at all.
- **Hollow harness records.** `A__r1__claude-fable-subagent.json.record.json` has
  `latency_s = 0.0`, `input_tokens = None`, `output_tokens = None`, `finish_reasons = []`,
  `attempts = 1`, `repair_rounds = 0`. The record schema has 25 keys and none of them is a model id
  or a timestamp.
- **The prompt and the pass bar are live functions of validator code.** `_author_prompt` composes
  from a brief generated by `generate_drafting_brief.py`, which reads from `validator/band_profile.py`,
  `validator/policy.py` and `scripts/check_skeleton.py` at render time. Neither the rendered brief
  nor a hash of it is committed. `AL-309` and `UW-C306` both propose changing exactly the PL-18
  surface that three legs lost grid points to. Land either and the 42 shells were asked a different
  question against a different bar, and the reproduction I just ran would no longer return 27.

  This is the sharpest form of the finding: **my reproduction succeeded today and has an expiry date
  nobody has written down.**

### Experiment 2: the S-0 recognition pilot (`evidence/recognition-protocol-pilot/`)

Six `verdict_*.json`. Their complete key set is `per_scene`, `first_yes_position`, `same_adventure`,
`distinctness_1_to_5`, `strongest_signal`. No rater id, no model id, no timestamp, no prompt hash, no
identifier for the pair being judged; the pair is encoded only in the filename.

**Correction in the programme's favour, which the prior finding underweights.** `results.md` does
carry a labelled `> **Provenance.**` block: run date 2026-08-21, register row `S-0`, and "All six
raters are model raters: independent, blind subagent sessions of the serving frontier model (session
model id `claude-fable-5`), one prompt each, no repo access, no knowledge of arms or of the
experiment." That is recorded-elsewhere, not unrecorded, and the distinction the task asked me to
draw applies here. What remains genuinely missing is **per-verdict attribution** (which file is which
rater), any model *version* or snapshot behind the family label, sampling parameters, and a prompt
hash, which `protocol.py build` already renders and could emit for free.

**Net on claim 4:** the provenance gaps are real and correctly identified. The claim "not reproducible
by a third party" is too strong as stated: the deterministic endpoints reproduce exactly and I did it.
The accurate statement is that **the deterministic endpoints reproduce against the current validator
and nothing pins that validator, and the model-mediated endpoints are not reproducible at all.**

---

## Claim 5 (C6-10): golden corpora assert one bit and never which findings fired

**Verdict: CONFIRMED, with one small correction.**

`tests/unit/test_filled_story_corpus.py` over the 40 committed `out/*.filled.json`:

```python
result = run_gate(blob)
assert not result.blocked, ...
```

`tests/unit/test_skeleton.py` over the 149 committed skeletons: `assert not result.blocked`.

**Correction:** it is two bits per book, not one. A second parametrised test,
`test_filled_story_has_no_unfilled_directives`, asserts no leftover `<<FILL>>` marker. That does not
disturb the finding, since neither bit is a verdict.

The finding-level assertions that do exist are confined to the **known-bad** fixtures:
`test_corpus_layer2.py` and `test_character_rules.py` assert specific ids in and out of
`report.rule_ids()` (`L2-9`, `L2-10`, `L2-11`, `L2-12`, `L1-6`, `CH-5`, `CH-8`, `CH-3a/3b`, `CH-4`).
That is a real pinned-verdict corpus over 16 fixtures. Over the **189 positive artifacts** that make
up the catalog, nothing is pinned. There is no `tests/fixtures/gate_verdicts.json`; `tests/fixtures/`
holds `moderation_qa`, `moderation_reports`, `skeletons`, `storybook` and no verdict snapshot.

So a change that stops a policy or advisory rule firing across the entire catalog leaves 189 tests
green, because `not blocked` stays true. That is the `CG-4` failure mode `UW-C280` records actually
happening.

---

## Claim 6 (C6-2): `check_sibling_fills.py` still returns 3.2 on D-7b, not the published 2.3

**Verdict: CONFIRMED, and I found a second undisclosed method change the prior pass did not.**

Committed instrument on committed artifacts:

```
uv run python scripts/check_sibling_fills.py \
    docs/planning/evidence/d7b-bare-names/filled_C.json \
    docs/planning/evidence/d7b-bare-names/filled_D.json
-> shared 4-grams across 2 fills: 10 (3.2 per 1000 mean leaf words; budget 4.0)
```

3.2, the retracted figure. `_leaf_text` still does `" ".join(parts)` over every body and label.
`git grep` for a per-body implementation across `scripts/`, `src/` and the evidence tree returns
**nothing**: the corrected method is implemented in no committed code.

**The new part.** I implemented the recount myself to test whether the retraction's stated cause
actually explains the restatement:

| method | shared grams | mean words | per 1000 |
|---|---|---|---|
| joined bodies+labels (**the committed script**) | 10 | 3134 | **3.19** |
| per-body-unit, bodies **and** labels | 8 | 3134 | **2.55** |
| per-body-unit, **bodies only** | 7 | 3002 | **2.33** |

The published **2.3 is recoverable, but only under two changes, and the register discloses one.**
The D-7b restatement note says only that "the earlier figure counted 4-grams straddling body
boundaries". Fixing just that gives **2.55**, which rounds to 2.6 and would still be quoted against a
3.3 floor. Reaching 2.3 additionally requires dropping choice labels from both the numerator and the
denominator, a scope change the note does not mention. Independent confirmation that this is what
happened: commit `bf7cad1`'s body says the corrected figures are "the body-only figures", so the
scope change is real, documented in a commit message, and absent from the register cell a reader
actually reads.

`AL-309` (the lesson that diagnoses the defect, "the convergence metric manufactures four-grams that
exist in none of the text it measures") is status **`open`**, scheduled at `UW-C225`. `AL-267` (the
idiom floor) is **`open`** at `UW-C197`. There is no `tests/unit/test_check_sibling_fills.py`.

---

## Claim 7 (C6-12): the full-pipeline e2e drives `_CANNED_STORY`; no test drives a valid-but-hollow fill

**Verdict: CONFIRMED.**

`frontend/e2e-real/full-pipeline-real.spec.ts`, its own header, lines 22-28:

> The mock generation provider (generation/providers -- ENVIRONMENT=local) ignores the submitted
> brief and always returns the same canned story titled "The Forest Path"
> (generation/provider.py `_CANNED_STORY`), so every assertion below is pinned to that title, not to
> the brief this spec sends.

Grep of that spec for `skeleton`, `fill_skeleton`, `story-request` or `intake` returns only two hits,
both inside the header prose. The skeleton path is not exercised by the nightly e2e.

The hollow-fill half is confirmed structurally, and it is stronger than "no test exists": **the
production path cannot detect one.**

```
git grep -c "commissioned_words_by_node\|fill_rate" -- \
  src/cyo_adventure/generation/worker.py src/cyo_adventure/generation/orchestrator.py
  (zero hits)
```

`commissioned_words_by_node` has exactly three importers: `scripts/check_fill_integrity.py`,
`generation/skeleton.py` itself, and `tests/unit/test_fill_output_cap.py`. None is in the request
path. And neither `check_fill_integrity` nor `check_sibling_fills` appears anywhere in `.github/` or
`.pre-commit-config.yaml`. So there is no test driving a hollow fill *and* nothing for such a test to
assert against, which is why the recommended test has to be written to fail.

---

## Claim 8 (C6-11): zero recorded provider responses; a shape change misclassifies as transient

**Verdict: CONFIRMED, and I reproduced the failure mode live rather than inferring it.**

```
git grep -rln "cassette\|vcr\|respx\|httpx_mock\|pytest-recording" -- tests/ pyproject.toml
  (nothing)
ls tests/fixtures/providers
  No such file or directory
```

Every mock body is hand-authored. I then drove the real parsers with three response shapes:

```
legacy string              dig_content='hello'   finish='stop'
content-block array        dig_content=None      finish='stop'
null content + reasoning   dig_content=None      finish='stop'
```

`openrouter.py:365` sets `leg_fatal=finish_reason == "length"`. So for both modern shapes the
adapter raises `ProviderError(leg_fatal=False)`, which is the **transient** classification, and the
harness retries a leg that can never succeed. The observable symptom is "the provider is flaky" and
the entire unit suite stays green, because every mock feeds the legacy shape. Confirmed exactly as
described, and `AL-329` records the programme already paying for a closely related misclassification.

---

## What everyone missed

Six additional holes in the register/lessons/linkage system, all demonstrated, none in the prior
findings.

### M1. The "append-only" guarantee does not exist. A lesson can be deleted and both checkers pass.

`check_lessons_log.py`'s own docstring at `_check_id_sequence` states the contract:

> Ids must be unique and consecutive from 001: a gap means a row was deleted, and **the log is
> append-only precisely so a lesson cannot quietly disappear.**

The implementation is `sorted(numbers) == list(range(1, len(numbers) + 1))`, which tests
consecutiveness of whatever survives, not that nothing was removed. Two deletions, both green:

```
TEST 1  delete the newest lesson (AL-513) outright
        ok: well formed -- 512 lesson(s)                                     rc=0
TEST 2  delete a MIDDLE lesson (AL-250) and renumber the tail (AL-251..513 -> AL-250..512)
        ok: well formed -- 512 lesson(s)                                     rc=0
```

Deleting the newest lesson is undetectable by construction. Deleting any lesson is undetectable after
a renumber, which is a mechanical `sed`. The document that exists so a lesson "cannot quietly
disappear" has no mechanism preventing a lesson from quietly disappearing.

### M2. Consecutive-id enforcement actively destroys citation stability, and it has already broken a citation.

M1's renumber is not hypothetical: the contract **forces** it. When two branches each append lessons,
the ids collide and one side must be renumbered to restore consecutiveness. This repo has a commit
whose subject is literally that: `6fc2b34 chore: merge main into skeleton sourcing branch, renumber
colliding register rows`.

The consequence, demonstrated on a real citation. Commit `bf7cad1`'s message says:

> Adds AL-296 (re-derive with a control row from the same table; recompute every row a correction
> pass relabels) and AL-297 (the metric grams a joined string, so four-grams spanning a body/label
> boundary are counted as shared prose...)

Read `AL-296` and `AL-297` in the log **today** and you get two lessons about
`scripts/check_device_vocabulary.py`, entirely unrelated. The gram-boundary lesson now lives at
**`AL-309`**. Anyone following that commit message's citation lands on the wrong lesson, silently,
with no error and no redirect. The same hazard applies to every AL id cited in the research briefs,
the ADRs, the unscheduled-work register and the diversity register.

So the log's id-integrity rule buys protection against a gap and pays for it with the stability of
every external reference to the document. That trade has never been stated anywhere, and it is the
wrong way round: a gap is cosmetic, a silently-repointed citation is a correctness failure.

### M3. A register row may cite a lesson that does not exist.

`check_work_linkage.py` enforces one direction only: an open lesson must be cited by a `UW-C*` row.
It does not check that a cited id resolves. In my 2x2 I rewrote the register's `AL-514` citation to
`AL-9999` and, with the lesson flipped to `applied`, the run is clean:

```
check_work_linkage.py --register reg_nocite.md --lessons-log log_gamed.md
  ok: unscheduled-work-register.md satisfies the work-linkage contract
```

Combined with M1 and M2, the two documents can drift arbitrarily far apart while both checkers stay
green: delete a lesson, renumber, and every register citation past the deletion point now names a
different lesson, and nothing anywhere reports it.

### M4. A refuted result can be quietly re-enabled. One `sed` flips it.

The log has exactly one `rejected` lesson, `AL-249` (the decision-variance rating instrument).
Flipping it:

```
sed 's/| rejected |/| applied |/' authoring-lessons-log.md > log_unreject.md
check_lessons_log.py --log log_unreject.md
  ok: well formed -- 513 lesson(s): accepted=3, applied=241, open=268, superseded=1   rc=0
```

`rejected` and `applied` are both in `_STATUSES_NEEDING_REF` and both in `_AL_CLOSED_STATUSES`, so
the transition is invisible to both checkers, keeps the same ref, and removes the row from nothing
because it was already exempt. For the diversity register there is not even this much: with zero
checks (claim 3), a `done, NEGATIVE` row can be edited to any status at all.

### M5. Pre-registered falsifier cells HAVE been edited after their experiments produced results. Commit `bf7cad1`.

This is the post-hoc edit the task asked me to find, and I found it by diffing every row's Falsifier
cell across all 13 commits that touch the register.

**First, the finding that clears S-1**, which I want to state before the one that does not, because
it corrects `C6-3` in the programme's favour. Across every commit on the sourcing branch, the S-1
row's `Falsifier / margins (fixed at registration)` cell is **byte-identical throughout**. Only
`Status` ever changed:

```
e757869: BASELINE
86e380b .. 6fc2b34: CHANGED cells -> ['Status']    (9 commits, every one)
```

So the S-1 pre-registration was **not** tampered with. Every amendment went into the Status cell.
`C6-3`'s complaint is therefore about *presentation*, amendments buried in a ~4,000-character Status
cell where a reader looking at the Falsifier column will not find them, and not about tampering. That
is a materially weaker and fairer charge than "an experiment can substitute its primary endpoint",
and the register deserves the correction.

**Now the one that does not clear.** Commit `bf7cad1`, `fix(publishing): close the four open items
from the research-round handoff (#703)`, edits the Falsifier cells of **three rows that were already
`done`**:

| row | status at edit time | before | after |
|---|---|---|---|
| D-6 | `done, MIXED` | 16.9 per 1000; best repair 11.4 | 17.2; best repair 11.8 |
| D-7 | `done, NEGATIVE` | 12.9 per 1000 | 13.6 |
| **D-7b** | `done, POSITIVE, claim narrowed` | **3.2 per 1000, "at the 3.3 floor"** | **2.3 per 1000, "*below* the 3.3 generator idiom floor"** |

The D-7b edit **changes the result's direction**. "At the floor" means the arm is indistinguishable
from two books sharing nothing but the model and the age band. "Below the floor" is the positive
finding that F5, the architecture the programme is re-specifying around, now rests on. That flip was
made after the row was `done`, by a recount, under a scope change the cell does not fully disclose
(claim 6).

Section F's own rule is unambiguous: "amending one after its experiment has produced artifacts
**voids that experiment's pre-registration** and must be recorded here as such." None of the three
rows is marked voided. The restatement is a parenthetical inside the same cell.

**Three aggravating details.**

1. **The correction is buried in an unrelated commit.** `bf7cad1` touches 30 files and 1,337 lines:
   `publishing/service.py`, `publishing/reason_codes.py`, two SQL migrations, the privacy policy page,
   `api/approval.py`. Its subject line is a publishing fix. Nothing in the subject says three
   completed experimental results were restated. On `main`, which is squash-only, this is the
   granularity a reader gets.
2. **To its credit, the commit body is exemplary.** It explains the re-derivation, names the cause,
   confirms the control row reproduces exactly, states that "every conclusion survives", and adds two
   lessons with register rows. This is disclosure, not concealment, and I want that on the record.
   The failure is that the disclosure lives in a commit message nobody reads, was never propagated
   into the register's own amendment slot, and, per M2, the two lesson ids it cites no longer point at
   the lessons it means.
3. **The fix was never made.** `AL-309` diagnosed the metric defect on 2026-08-11. Ten days later
   `check_sibling_fills.py` still ships the broken metric and `AL-309` is still `open`. The numbers
   were corrected in the prose; the instrument that produces them was not.

By contrast, the S-3 falsifier edit in `9f97d35` happened while that row's status was
`blocked on S-0, S-1`, i.e. **before data**. That is a legitimate pre-data amendment and I am not
counting it against the programme.

### M6. Pre-registration precedence rests on branch-local commit order that this repo's merge policy destroys.

No register table has a `Registered on` column. I checked all six table headers; the only temporal
claim is section F's prose, "fixed as of this commit". So the entire evidentiary basis for "this
falsifier predates its data" is git commit ordering.

`main` is **squash-only**: `git log --merges main` returns nothing, and every commit is
`... (#NNN)`. One PR becomes one commit. The sourcing branch currently holds `e757869`
("register skeleton sourcing S-rows with fixed margins") and `2ec17e5` ("close S-1: full grid
complete") as separate commits, and `git branch --contains e757869` confirms it is not on `main`.
**When that branch merges, S-1's pre-registration and all of S-1's results land in a single commit**,
and the ordering that is the whole point of pre-registration ceases to exist in the permanent
history.

This is the deepest hole in the set, because it is not a checker gap that a script can close. Every
other finding here is "nothing verifies the claim"; this one is "after merge, the claim is not
verifiable in principle from the repository."

---

## Recommendation review

### R1. The ref-resolution hole: what makes a valid `Ref`, and how to check it without making it unenforceable

The prior recommendation ("accept a path, a `#NNN`, a SHA, or an explicit `prose:` prefix; fail on
anything else; backfill the 57") is directionally right and mis-sized: there are 4 prose refs, not
57, so the backfill is an afternoon, not a project. But it is also under-specified in the direction
that matters, because it would accept `AL-017`'s dangling path forever.

Concretely, define a ref as a **semicolon-separated list of at least one anchor**, each of which
must be one of:

| form | check | notes |
|---|---|---|
| repo-relative path | `git cat-file -e HEAD:<path>` | catches ref rot (`AL-017`); resolve `a/b.py` by unique trailing-suffix match so existing refs keep working |
| test node id `path::name` | path resolves **and** `def name`/`class name` occurs in it | the strongest cheap anchor |
| commit `[0-9a-f]{7,40}` | `git cat-file -e <sha>^{commit}` | **skip, do not fail, when `.git/shallow` exists** |
| `#NNN` | `gh api` when a token is present | **skip, do not fail, when unauthenticated** |
| register row id | the id occurs as a first cell in a `docs/planning/*.md` table | also fixes M3 in the other direction |
| `prose:<text>` | always accepted, **counted and printed** | the escape hatch, made visible |

The two "skip" rows are what keeps this enforceable. A checker that fails in a shallow clone or
without a token will be bypassed within a week, and the pre-commit hook runs on developer machines
where neither is guaranteed. Skipping-with-a-count preserves the gate where it can run and degrades
to reporting where it cannot.

The summary line becomes the actual instrument: `240 applied: 212 resolved, 15 unverifiable here,
4 prose:, 2 DANGLING`. Fail on dangling and on unprefixed-unresolvable; never fail on `prose:`.
Publishing the prose count is what makes the escape hatch self-limiting, because a number that goes
up is a number someone asks about.

**Second half, which the prior recommendation gets right and I want to reinforce:** an `applied` row
should additionally require its scheduling `UW-C*` row to be marked done. That is the only proposed
change here that checks *substance* rather than shape, and it is the one that closes the 2x2's bottom
row, since flipping to `applied` would then create a second obligation rather than deleting the first.

**Cost:** roughly 150 lines against `check_lessons_log.py`'s existing `_split_row` helpers, plus a
2-row backfill. Half a day.

### R2. Append-only or signed pre-registrations: is it worth the friction?

**Not signing. Yes to a cheap structural fix.** Signed commits are already mandatory in this repo
(`CLAUDE.md` core directives), so signatures add nothing: `bf7cad1` was signed and still rewrote three
completed results. The problem is not authorship, it is ordering and disclosure.

What is warranted, in increasing cost:

1. **A `Registered` date column and a `Falsifier (registered)` / `Amendments` column split.** Section F
   already demands the content; the row has nowhere to put it, which is why S-1's amendments ended up
   in the Status cell. This is a schema change to a markdown table and it is the single highest-value
   item in this whole review relative to its cost.
2. **A content hash of the registered cell, recorded in the row.** `check_diversity_register.py`
   recomputes it and fails when the cell changed without the `Amendments` cell gaining an entry. This
   is the append-only guarantee, and it costs one column and about 30 lines. It would have caught
   `bf7cad1`'s three edits and forced them into the `Amendments` slot where section F already says
   they belong.
3. **Preserving precedence across the squash merge (M6).** The cheap version: require the registration
   commit's SHA in the `Registered` column at registration time. Even after the squash it is a
   verifiable claim about a commit that existed, and `git cat-file -e` can check it while the branch
   lives. The thorough version is a separate `pre-registrations/` directory of one immutable file per
   row, appended-to and never edited, which survives squashing because the *file* carries the
   ordering rather than the history. I would do the cheap version now and the thorough one only if a
   pre-registration is ever actually disputed.

**Friction verdict:** items 1 and 2 add one column each and one checker. Compared to the effort
already spent hand-maintaining a 1,287-line register, this is negligible, and it is the document with
the highest ratio of external-credibility to automated-support in the repo.

### R3. Golden corpora: the exact assertion shape, and what it actually costs

Proposed shape, concretely. Commit `tests/fixtures/gate_verdicts.json`:

```json
{
  "out/baking-day-with-grandma-vole.filled.json": {
    "blocked": false,
    "rule_ids": ["PL-19", "PL-24", "RL-13"],
    "counts": {"PL-19": 2, "PL-24": 1, "RL-13": 7}
  }
}
```

Three fields, and each earns its place. `blocked` preserves today's assertion. `rule_ids` as a
**sorted set** is the loosening/tightening detector and is the point of the exercise. `counts` is
what catches the case that matters most in practice: a rule that still fires somewhere in the catalog
but stopped firing on 200 of 240 nodes, which a set comparison misses entirely.

The test becomes a single parametrised comparison per artifact against its pinned entry, with
`pytest --update-verdicts` regenerating the file so the diff is **reviewed in the PR** rather than
avoided. That regeneration path is the whole design: without it the fixture rots and gets deleted.

Guard the guard, in the style the repo already uses (`test_the_corpus_is_not_empty`): assert that
every discovered artifact has an entry and every entry has an artifact, so neither a new uncovered
book nor a stale entry passes silently.

**Work estimate.** 189 artifacts (40 fills + 149 skeletons). The generator and the test are about 80
lines together; the fixture is generated, not written. The real cost is the **first review of the
generated file**, because it will surface advisory findings nobody has looked at, and that is a
feature. Call it one day to build, plus one to triage what it reveals. This is the cheapest
high-value item in section 8 and it is not currently in section 8's list at all.

### R4. Provenance per run

Endorsed as written, with one addition and one reordering. The prior recommendation's own ranking is
right that committing the **rendered brief** is the highest-value item, and my S-1 reproduction is the
evidence: it succeeded today only because the validator has not moved since 2026-08-21, and `AL-309`
and `UW-C306` both propose moving it. A committed brief per cell converts "reproducible until someone
lands an open lesson" into "reproducible".

Addition: a `re-verify.py` that recomputes pass counts from committed shells and fails on
disagreement. I wrote a throwaway version of exactly this in twenty minutes to validate claim 4; it
found zero disagreements over 42 shells. Promoting it from throwaway to committed CI step is the
cheapest possible protection for the programme's only reproducible result, and it turns a silent
future drift into a red build.

### R5. On section 8's ranking

Items 1 and 2 of "this week" are the right two and my claim-6 work sharpens item 1: reconciling "the
two 4-gram scopes" understates it, because there are **three** (joined, per-body-with-labels,
per-body-body-only) and the published 2.3 is the third. Restating under one named scope requires
naming which of the three, and the register's own note names neither.

I would add to "this week", at a cost of under a day each: the `Falsifier (registered)`/`Amendments`
column split (R2.1) and the ref resolver (R1). Both are prerequisites for the register being worth
citing externally, which is the purpose it is being put to right now.

---

## The missing testing tier, re-ranked

`C6-15` ranked: adversarial corpus > S-5 defect corpus > prod monitoring > canaries > child
comprehension > A/B. **I disagree with two placements**, and I think the list is missing an entry.

My ranking, by value per unit cost, with the cost basis stated:

**1. Pinned-verdict regression over the existing catalog (R3). Not in the prior list.**
Cost: ~2 days, no model spend, no new corpus. Value: it is the only item that protects all 55 rules
at once, it converts every future catalog addition into free coverage, and it is the only defence
against the silent-loosening failure mode, which is the one that costs most because it is invisible
by construction and surfaces only as reviewer fatigue. The prior list ranked its near-relative
("canary books") **fourth**; it belongs first, because 189 artifacts already exist and the canary set
does not.


Supporting audit I ran for this ranking, of the fifteen script-level gate checks, by whether they
have a unit test and whether any workflow invokes them:

```
check_fill_integrity       test=yes  ci=none
check_sibling_fills        test=NO   ci=none
check_prose_craft          test=yes  ci=none
check_reading_level        test=NO   ci=none
check_graph_structure      test=NO   ci=none      <-- S-5's decision procedure
check_fill_fidelity        test=NO   ci=none
check_branch_obligations   test=NO   ci=none
check_promise_discharge    test=NO   ci=none
check_solution_transfer    test=NO   ci=none
check_narrative_contract   test=yes  ci=none
check_outcome_spread       test=yes  ci=none
check_theme_contract       test=yes  ci=skeleton-promotion.yml
check_skeleton             test=yes  ci=skeleton-promotion.yml
check_incell_clones        test=NO   ci=ci.yml
check_decision_overlap     test=NO   ci=none
```

Six of fifteen have a test; three of fifteen are wired to CI. **`check_graph_structure` has
neither**, and it is the instrument S-5 will use to decide whether unreviewed shells may reach
children. That is the specific fact that moves item 2 above item 3.

**2. Structural-defect corpus for the gate (S-5's prerequisite).** Cost: 1-2 days, deterministic, no
spend; `scripts/seed_defects.py` exists and the register says "corpus buildable now" with a
100%/90% catch floor already pre-registered. I move this **above** the adversarial safety corpus,
against the prior ranking, for a specific reason: `check_graph_structure`'s six failure classes are
what S-5 will use to decide whether **unreviewed shells may reach children**, and nothing currently
proves those six classifiers fire at all (`C6-9`). An ungated decision procedure standing between a
prototype and a child is a larger exposure than the size of the safety corpus, which is at least
gated at 100% on the classes it covers.

**3. Adversarial safety corpus expansion, 13 items to ~150.** Cost: authoring time, no
infrastructure; the tier exists, runs weekly against live classifiers, and correctly refuses to pass
vacuously without credentials. I keep it high and move it one place down only because items 1 and 2
are cheaper and currently at zero, whereas this one is at 13 rather than at zero. It is the only tier
that directly protects a child and it should not slip further than third.

**4. Provider contract fixtures (claim 8).** Not in the prior list. Cost: half a day, one captured
response per adapter. Value: I demonstrated the live failure mode above, and it is a
silent-money-burn plus a false "the provider is flaky" diagnosis. Small, but the cost/benefit is
extreme and it protects `F7`.

**5. Longitudinal production quality monitoring.** Unchanged from the prior ranking's third place in
substance; it drops here only because items 1, 2 and 4 did not exist on the prior list. The signals
already exist as product features and the alerting pattern is already in `supabase-backup.yml`.

**6. Canary books.** Demoted from fourth: it is nearly free *once* item 1 exists and largely
redundant with it, so it is a follow-on, not an independent tier.

**7. Child comprehension testing.** I agree with the prior placement and its reasoning, and I want to
underline it rather than move it: for a reading app for children the untested question is the
product's central one, and no child has been measured. `naive-ux-check` drives a *model* persona and
is a usability probe, not comprehension. Correctly a gate on the public-launch decision (ADR-008),
not on R1.

**8. A/B on real readers.** Agreed, last. The install base is one family and the register's own Q-1
result says a child exhausts a cell by roughly the fourth request, so the sample is structurally too
small. Drop until there is a population.

**Summary of my disagreement with C6-15:** it ranked by "value per unit cost" but restricted itself
to tiers someone had already named, so the two cheapest and highest-value items on the board (pinned
verdicts over 189 existing artifacts, provider contract fixtures) do not appear, and the item most
directly gating a child-safety decision (S-5's defect corpus) sits below a corpus expansion.

---

## Appendix: my artifacts, so this validation is itself reproducible

All under `/tmp/claude-0/-home-user-cyo-adventure/95fe99a0-cfc0-5263-8504-f7a4f8df5262/scratchpad/v9/`:

| file | what it is |
|---|---|
| `v9plugin.py` | the sharded, call-site-recording instrumentation plugin |
| `dumps2/` | 3 per-worker dumps from the 2,430-test targeted run |
| `testdumps/` | 5 dumps from the single-module run that demonstrates the xdist divergence |
| `analysis_sub.txt` | merged rule-firing analysis (53 ids, call-site counts) |
| `subrun.txt` | the targeted run's pytest log (`2430 passed, 9 skipped in 58.79s`) |
| `resolve.py`, `applied.json`, `resolved.json` | the independent ref resolver and its per-ref anchor evidence |
| `log_baseline.md`, `log_gamed.md`, `log_deltail.md`, `log_delmid.md`, `log_unreject.md` | the five adversarial lessons-log variants |
| `reg_nocite.md` | the register with `AL-514`'s citation dangled, for the 2x2 |
| `repro_s1.txt` | the S-1 re-verification (`27 pass / 15 fail, 0 disagreements over 42 shells`) |

Six adversarial edits were constructed and run against the live checkers. **All six pass**:

1. `applied` + `"fixed it, see the thing"` on a live open lesson.
2. Delete the newest lesson outright.
3. Delete a middle lesson and renumber the tail.
4. Flip the one `rejected` lesson to `applied`.
5. Point a register row's citation at a lesson id that does not exist.
6. Anything at all in the diversity register, which no checker reads.

Nothing was written to the repository; every edit was made on a copy under the scratchpad.
