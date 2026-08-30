# V6: adversarial validation of synthesis section 2, "the detector is built, and it gates nothing"

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `/home/user/cyo-adventure`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.

Adversarial pass over the seven claimed cases, C6-9's count, and the proposed rule.
Everything below was re-run or re-read against `/home/user/cyo-adventure` at HEAD on 2026-08-22.
Where I disagree with the prior review I say so; where the prior review is right I say that too.

## Headline

**The cluster's central fact is true and its central framing is wrong.** Every one of the seven
modules really does lack a production caller. But the seven are not one pattern. They fall into
three classes that carry completely different obligations:

| Class | Cases | Obligation |
|---|---|---|
| **Instrument / infrastructure, deliberately not a gate** | 1 (`consequence.py`), 3 (`paths.py`) | none, a documented, dated KEEP decision. Wiring them would violate a pre-committed rule. |
| **Registered gate whose *runner* is unrun** | 5 (`check_fill_integrity`), 6 (`check_sibling_fills`) | one fix, not two: run `scripts/run_guard_battery.py`. |
| **Genuinely finished, genuinely unconnected** | 2 (`imitable.py`), 4 (`safety.py`), 7 (`check_solution_transfer`), **8 (`blind_spots.py`, missed)** | wire, or delete honestly. |

Two of the seven (5 and 6) are **factually refuted as stated**: both are registered `gating=True`
in `scripts/run_guard_battery.py`, with a unit test asserting the registration. Two more (1 and 3)
are **deliberate documented decisions**, not defects. One case the review missed
(`validator/blind_spots.py`) is the most damning instance in the repo. And the review's own
recommendation was **already adopted by this project a month ago** (AL-305) at the tier where it
matters most, the synthesis proposes as new a rule that exists and misses that its registry has
no runner.

Search method used before concluding "unwired" on any case: direct imports, `from X import Y`,
`importlib`/`pkgutil`/`import_module`/`__subclasses__`/`getattr` dynamic dispatch (none exist in
`src/` or `scripts/` outside `importlib.resources` template loading), `[project.scripts]` and
`[project.entry-points]` in `pyproject.toml` (**neither table exists**), all 38 workflow files,
`.pre-commit-config.yaml`, all 20 `noxfile.py` sessions, the `cyo-author` skill, and
script-to-script indirection (which is where I found the two refutations).

---

## Case 1: `validator/consequence.py` (false choice / cosmetic branching)

**Verdict: fact CONFIRMED, framing REFUTED.** Importers are exactly
`scripts/measure_consequence.py:48`, `scripts/seed_defects.py:59`, `tests/unit/test_consequence.py:21`.
No gate caller, no workflow, no nox session, no battery registration.

**Defect vs staged: STAGED, twice, in writing, with a pre-committed promotion rule.**
- The module's own docstring, lines 23-27: *"**This is a reported statistic, not a gate.**
  `BandProfile.reconvergence_ceiling` exists and is unenforced, and it stays that way: promoting a
  measure to a rule that blocks a book requires evidence that a reader is affected, which is W12's
  job. `AL-337` is the record of what happens when a number becomes a gate on the strength of being
  computable."*
- `docs/planning/cyo-measurement-workplan-2026-08-12.md` line 547, the W-series decision table:
  `| W3 consequence distance | D | yes, validator/consequence.py | yes, 61-book catalogue | **KEEP as a reported statistic** |`
- Section "W3, fork consequence: KEEP as a reported statistic" (line 701) records the outcome:
  mean 14.5% false choices, spread 0.190 across 23 complete books; it discriminates, which was the
  stage-one bar; stage two (blocking) is explicitly gated on W12 (child + expert read), which
  `docs/planning/cyo-measurement-workplan-2026-08-12.md:556` shows blocked on ADR-018 consent
  scoping.

Calling this "a detector that gates nothing" is unfair. It is a measure the project deliberately
refused to promote, for a reason it wrote down, applying a lesson (AL-337) it paid for.

**Residual risk: real, but it is a DIFFERENT defect than the one the table names.** C1-2's actual
finding survives and is stronger than the consequence statistic: nothing gates a **duplicate-target
choice set**, which needs no reader evidence at all because it is a structural fact. I reproduced
C1-2's census exactly: **11 of 84 shells carry 302 duplicate-target choices**, led by
`the-observatory-shift` at 102 of 115 decision nodes / 204 of 348 choices. Partial coverage
elsewhere: `scripts/check_decision_overlap.py` gates `worst_fork_consequence_rate`, but it is an
experiment script (referenced only from `docs/planning/evidence/`), scores annotator-assigned
labels rather than the graph, and is in no workflow and no battery. So the coverage is nil.

**Wiring action: do NOT wire `consequence.py`. Wire the duplicate-target rule instead**, a new
`PL-*` in `validator/policy.py`: a decision node whose choices are identical in
`(target, condition, effects)` is not a decision. This also closes the C1-3 seam
(`_build_graph`'s `DiGraph` collapsing parallel edges while `check_skeleton.max_indegree` counts
them), because the two readings can no longer diverge.

**Blast radius, measured, and much smaller than the review implies.** Under C1-2's own proposed
wording ("two distinct targets *or* differing conditions/effects"), only **4 of 84 shells** fail,
not 11: 7 of the 11 duplicate-target books differentiate by condition or effect and are legal.

```text
the-observatory-shift.json          102 offending nodes   <- rewrite
the-winter-of-the-wolf-queen.json     1
the-harrowstone-keep.json             1
the-sunken-temple.json                1
```

Three books need a one-node fix each. One book is a rewrite. Published books: none blocked (this
is a skeleton-tier rule; `skeleton-promotion.yml` would enforce it on change).

**What the prior review missed:** the 11/302 figure is the duplicate-*target* count, not the count
under its own recommended rule. The real blast radius is 4 shells, which makes this the cheapest
structural fix in the report and it is buried under a module that must not be wired.

---

## Case 2: `validator/imitable.py` (imitable-action harm)

**Verdict: CONFIRMED.** `grep` for `validator.imitable` / `screen_for_review` / `HazardCue` across
`src/`, `scripts/`, `frontend/`, `.github/`, `noxfile.py`, `.pre-commit-config.yaml` and the
`cyo-author` skill returns only the module and `tests/unit/test_imitable.py:17`.

**Defect vs staged: DEFECT, and the work register states its status falsely.** The module was
built to have a caller, its docstring says *"A routing screen, not a rule and not a classifier.
It decides nothing and blocks nothing. It selects the small set of endings a person should look
at."* A router with no consumer is not staged, it is unfinished. `UW-C264`
(`unscheduled-work-register.md:516`) says in the present tense: *"**Screen half done 2026-08-15
(`AL-405`)**: `validator/imitable.py` routes 13 of 167 young-band endings to human attention"*.
It routes nothing anywhere. That status line is wrong and should be corrected regardless of whether
the wiring happens.

**Residual risk: partially covered, more than the review allows.** Stage 1 of the moderation
pipeline (`moderation/stages.py:89`) carries **"real-world danger modeled as achievable"** as a
`block`-tier criterion in `_SAFETY_RUBRIC`, applied per passage on every book, and
`real_world_danger` is a live concern slug in `_CONTENT_CONCERNS` and `report.py:64`. So the harm
class is not unscreened in production; it is screened by an LLM against a *different construct*.
The genuine gap is AL-397's: the criterion asks whether the act looks doable, not whether the
protagonist is **rewarded** for doing it, and endings are where reward lives. That is a narrower,
more defensible claim than "a named, measured harm class is unscreened".

**Wiring action:** call `screen_for_review(story)` from `moderation/pipeline.py` (or `run_gate`
under `context="fill_result"`) and emit one `ADVISORY` `Finding` per cue with
`concern="real_world_danger"`. ~15 lines. Risk: near zero, advisory only, no verdict changes.

**Blast radius, reproduced today over the 31 committed fills: 13 findings across 6 books,
against 167 young-band ending nodes** (`the-cave-of-echoes`, `the-clockwork-menagerie`,
`the-lantern-festival`, `the-night-market`, `the-school-garden-mystery`,
`the-snow-day-expedition`). Zero books blocked; +13 paragraphs of approver reading, six of them in
one lantern-festival book, which the module documents as its expected failure mode.

**What the prior review missed:** that Stage 1 already carries a real-world-danger BLOCK criterion,
which weakens "uncovered in production" to "covered by a different construct". Also missed: the
figure is stable, the corpus grew and the screen still returns exactly 13/167.

---

## Case 3: `validator/paths.py::covering_paths` / `reader_sample_paths`

**Verdict: fact CONFIRMED, classification REFUTED.** Only external caller is
`scripts/measure_per_path.py:51`, plus `tests/unit/test_paths.py`.

**Defect vs staged: NEITHER, this is not a detector.** `paths.py` detects nothing. It enumerates
root-to-ending readings so that other measures can be re-unitted from book to path. The workplan
says so in its first line for W1: **"Infrastructure, not a candidate. Five items depend on it."**
Its decision rule was feasibility only ("ship if the covering set computes in under 2 seconds for a
101-node book"), met with three orders of magnitude of headroom (61/61 books at
`edge_coverage == 1.0`, 2.666 s whole catalogue). The workplan's status line is `| none, shipped |`.

Listing an enumeration library alongside `check_safety` as "a detector that gates nothing" is a
category error, and it inflates the count from a defensible five to seven.

**Residual risk: the real gap is a missing consumer, not a missing wire (C4-1).** There is no
path-scoped safety pass, so path-cumulative harm and grooming-shaped narrative arcs are uncovered:
`moderation/` screens per passage, `validator/` screens per node and per book. The substrate for
the fix exists and cost nothing to keep. That is a *good* outcome for infrastructure, not a defect.

**Wiring action: none applies.** The action is to *build* a consumer, a path-scoped safety /
reading-level pass over `covering_paths`, which is new feature work, not wiring. Note the W2
outcome already closed one such consumer as a dead end: the told-emotion band is arithmetically
inert at path scale (AL-342), so a naive re-unit of existing measures is known not to work.

**Blast radius:** unknown and unmeasurable until a consumer exists. Cost of the enumeration itself
on the current catalogue is 2.666 s, so runtime is not the constraint.

**What the prior review missed:** W1's own "infrastructure, not a candidate" header, and that
`paths.py` cannot "gate" anything by construction.

---

## Case 4: `validator/safety.py::check_safety` (SAFE-14)

**Verdict: CONFIRMED, and it is the sharpest *code* case.** `safety.py` is 57 lines; the body is
`_ = story; return ValidationReport()`. `gate.py:213` calls it inside the merge chain;
`gate.py:220` computes `safety_flagged = any(f.rule_id == "SAFE-14" ...)`, and no code path anywhere
emits a `SAFE-14` finding, so the flag is a provable constant `False`. It has five live readers:
`generation/worker.py:1369`, `generation/orchestrator.py:527` and `:771`,
`mutation/acceptance.py:672`, `scripts/run_story_gate.py:106`.

**Defect vs staged: STAGED, adjudicated, and loudly annotated, the synthesis's sharpest sentence
is refuted by the docs.** The synthesis says *"`gate.py` reads as though safety is covered."* The
project's own rule catalogue says the opposite, in bold, twice:

- `docs/planning/validator-rules.md:152`, *"SAFE-14 | Safety | **NOT IMPLEMENTED IN THE GATE**
  (`validator/safety.py` is a stub returning an empty report; the live screening is
  `moderation/pipeline.py`, outside the gate)."*
- `validator-rules.md:288-295`, application order step 7, *"**NOT IMPLEMENTED IN THE GATE.** …
  listing it here as a live step read as coverage the gate does not have … Keep this entry so the
  intended order survives, but do not count it when reasoning about what the gate enforces today."*
- `docs/planning/rule-system-charter.md:83-89` adjudicates it by name, *"**SAFE-14's phantom
  entry.** … Either implement it or take it out of the order. A catalogued rule that cannot fire is
  worse than no rule, because it reads as coverage. **DONE by annotation, not removal.**"*
- `gate.py:212` itself: `# --- SAFE-14: safety check (Phase-2 stub, always empty) ---`.

The one honest complaint that survives is the **field**, not the module: `safety_flagged` is a dead
boolean read at five live sites and annotated nowhere near them.

**Residual risk: much smaller than "the deterministic gate contributes zero safety" implies.**
Safety coverage in production is Stage 0 (`moderation/classifiers.py`: OpenAI omni-moderation +
Perspective, bright-line categories → hard `BLOCK` with no LLM spend) plus Stage 1's per-passage
LLM safety verdict. Roadmap line 635 records Phase 3 delivered *"behind the SAFE-14 seam"*, the
replacement landed, in `moderation/`, not in `check_safety`. The genuine residual is the set of
paths that call `run_gate` **without** moderation: `moderation/pipeline.py::_repair_is_adoptable`
(which the C4-9 finding shows *does* fully re-moderate, so this one is covered),
`api/node_edit.py`, `mutation/acceptance.py`, and `scripts/check_skeleton.py`. Skeleton-tier and
node-edit-tier safety is genuinely uncovered by any deterministic rule.

**Bonus defect found: the annotation's own cross-reference is broken.** `validator-rules.md:291`
cites `UW-C292` as the record for SAFE-14's non-implementation. `UW-C292`
(`unscheduled-work-register.md:544`) is about `policy._build_graph` ignoring `choice.condition`
in PL-20/25/26 and is marked `done`. There is no UW row tracking SAFE-14. The mechanism designed
to keep the phantom rule honest points at the wrong row.

**Wiring action, two options, and the cheap one is deletion:**
(a) *Cheap and honest (~30 min):* delete `check_safety`, `safety.py`, the `safety_flagged` field
and its five reads, the `gate.py` docstring references, and add `content_safety` to
`blind_spots.UNOBSERVED`. Callers that currently route on `safety_flagged` route on the moderation
verdict instead, which is where the real signal already is.
(b) *Real work:* implement SAFE-14 as C4-6's declared-vs-measured content-flag check plus a
band-scoped lexicon plus case 2's imitable screen. This is a phase of work and needs an ADR,
because a lexicon-based safety ERROR inside the gate is exactly the class of rule AL-337 warns
about.

**Blast radius:** (a) zero. (b) unknown; a declared-vs-measured check would need calibration
against the 31 fills before any threshold could be defended, and `the-tenfold-siege` (16+,
`violence: moderate, scariness: intense, peril: intense`) is the obvious calibration ceiling.

**What the prior review missed:** the three bold "NOT IMPLEMENTED IN THE GATE" annotations and the
charter ruling, which together refute "reads as though safety is covered"; and the broken
`UW-C292` citation, which is a real find in its own right.

---

## Case 5: `scripts/check_fill_integrity.py` (the AL-490 delivery floor)

**Verdict: REFUTED AS STATED. It is registered as a gate.**
`scripts/run_guard_battery.py:117` runs it per book with `gating=True`:

```python
("check_fill_integrity.py", (skeleton, book)),
```

and `tests/unit/test_guard_gating.py` asserts the registration, including that
`check_fill_integrity` is invoked **without** `--check` (because its `main()` already ends
`return 1 if failed else 0`), a distinction AL-293 paid for. It also has its own unit test file,
`tests/unit/test_check_fill_integrity.py`, and a documented cross-module contract with
`generation/skeleton.py::commissioned_words_by_node` (which exists solely to serve it).

What is true: no CI job, no `src/` caller, no `noxfile` session. But the correct statement of the
defect is **one level up**: `scripts/run_guard_battery.py`, the project's own registry, written
*"because invoking the guards by hand failed twice in one working day"*, **has zero callers
outside its own unit test**. It is in no workflow, no nox session, no pre-commit hook, and the
`cyo-author` skill's step 6 validates with `import_cli` only. Ten registered gating guards
(`check_graph_structure`, `check_fill_integrity`, `run_story_gate`, `check_prose_craft`,
`check_reading_level`, `check_label_template`, `check_promise_discharge`,
`check_device_vocabulary`, `check_sibling_fills`, `check_device_collision`) are all unrun for the
same single reason.

**Defect vs staged: DEFECT, and a compound one.** Three separate failures stack:
1. The battery has no runner.
2. **The battery is broken and would fail 28 of 31 books if run today.** Measured: bare invocation
   `check_fill_integrity.py <skeleton> <filled>` over all 31 committed pairs → 28 FAIL, 3 pass, all
   on the *structural* leg. Cause: committed shells carry theme placeholders in ending titles
   (`{B1_PRIZE}`, `{ANIMAL}`, `{ROUTE_A_KEEPER}`). `_defers_titles()` only detects `<<FILL` titles,
   not `{PLACEHOLDER}` ones, and `run_guard_battery.py` does not pass `--allow-title-rewrite`.
3. **12 of 31 committed skeleton/fill pairs have genuinely drifted structurally.** With
   `--allow-title-rewrite`: 19 pass, 12 still FAIL on node-set differences. Example verified:
   `skeletons/5-8/the-night-market.json` has 60 nodes with `n_hub2`/`n_hub3`; `out/the-night-market.filled.json`
   has 59 with `n_promise`. The shell was edited 2026-08-20 (PR #730, "cover all 18 offered cells at
   the strict bar"); the fill was committed 2026-08-16. **The corpus is already inconsistent and the
   unwired detector is exactly the one that would have caught it.**

**Residual risk: the fill-rate leg is uncovered and nothing else covers it.** `import_story.py`
runs `run_gate` (`:155`), `run_stage1_gate` fidelity (`:32`), and `check_sentinel_integrity_at_rest`
(`:692`). None measures delivered-over-commissioned words. `validator/policy.py`'s only hard word
rule is a *ceiling* (PL-19 words-per-node), which is why AL-490's 39-53% delivery passed cleanly.

**Wiring action:** split the two legs. Put the **fill-rate floor** in `import_story.py` beside the
Stage-1 fidelity gate (`commissioned_words_by_node` is already importable from `src/`, ~10 lines).
Wire the **structural leg** only after fixing `_defers_titles` to detect `{PLACEHOLDER}` titles and
after reconciling the 12 drifted pairs. Then add a CI job that runs `run_guard_battery.py` over the
committed pairs, and add it to `cyo-author` step 6.

**Blast radius, measured, and it is the decisive number in this whole report:**
**the 0.6 fill-rate floor passes 31 of 31 committed books.** Wiring it today blocks **zero** books.

```text
lowest four: the-lantern-festival 66.8%  |  the-sunken-signal 80.1%
             the-sky-ship-stowaway 80.2% |  the-cave-of-echoes 80.4%
highest:     the-thornwood-trial 119.0% (100.0% once per-node surplus is discounted)
```

The structural leg, by contrast, would block **28 of 31** bare and **12 of 31** with the flag,
which is almost certainly *why* nobody wired it, and the review does not know this.

**What the prior review missed:** the battery registration, the battery's own missing runner, the
`--allow-title-rewrite` defect in that registration, the 12 drifted corpus pairs, and the fact
that the fill-rate floor has zero blast radius, the single strongest argument for acting.

---

## Case 6: `scripts/check_sibling_fills.py` (sibling convergence)

**Verdict: REFUTED AS STATED.** `scripts/run_guard_battery.py:162` runs it with `--check` and
`gating=True` whenever two or more siblings are supplied, and records an explicit
`gating=False, scope="skipped"` Result with the reason *"one book given; convergence is a property
of a set"* when they are not, which is exactly the honesty the synthesis says is missing. Second
caller: `scripts/compare_vendors.py:1170` imports `pairwise_shared_grams`. It also has a test:
`tests/unit/test_bplus_checks.py:9` imports and exercises `shared_grams`.

**Defect vs staged: STAGED and correctly tracked; the review over-reads UW-C315.** `UW-C315`
(register line 567, phase `4b`, `unscheduled`) says *"**Still open:** the delta measurement, the
lever decision it feeds, and the **pipeline** wiring of `check_sibling_fills.py`"*, the automated
generation pipeline, at Phase 4b, blocked on an OpenRouter preflight that a network policy refused.
"Not wired" is not what that row says.

**Residual risk: low and shared with case 5.** The check is registered and gating; it does not run
because the battery does not run. There is partial production coverage of the same defect class:
`diversity/` runs an anti-template guard at request time (`story_requests/authoring_plan.py`,
`generation/binding.py`, `generation/worker.py`) and `moderation/leaf_diversity.py` runs inside the
pipeline, though C3-6 correctly notes the guard is advisory, fail-open, and family-scoped where
the defect is child-scoped.

**Wiring action: none specific to this script.** Fix case 5's battery runner and this closes for
free. If the automated pipeline is wanted, that is UW-C315's Phase-4b work.

**Blast radius:** measurable only per sibling set. The synthesis's own verified re-run of the D-7b
pair (3.2 shared 4-grams per 1000 against a budget of 4.0) shows the flagship pair **passes** the
existing budget, so the current threshold blocks nothing in the corpus. B3-10's N^0.788 scaling
finding further weakens any claim that the budget bites at realistic book length.

**What the prior review missed:** the battery registration, the second importer, the existing test,
and that UW-C315's open item is *pipeline* wiring at Phase 4b, not wiring at all.

---

## Case 7: `scripts/check_solution_transfer.py`

**Verdict: CONFIRMED, and it is the weakest of the seven.** Zero references in `tests/`, zero in
`.github/workflows/`, zero in `noxfile.py`, zero in `.pre-commit-config.yaml`, not in
`run_guard_battery.py`, no importer in `src/` or `scripts/`.

**Defect vs staged: NEITHER, it is a plan-time series instrument with a scope mismatch.** Its
signature is `<contract.json> <selection.json> <selection.json>`. It scores **device bindings
across two books of a series before a word of prose exists**. It cannot be a book gate; it does not
take a book. "Cannot even run on D-7b" is therefore not a wiring failure: D-7b has no
`selection.json` because it is not a device-bound series pair. That sentence in the synthesis reads
as evidence of neglect and is actually evidence of a category mismatch.

**Residual risk: LOW, because its strongest tier is already gated elsewhere.** Its own docstring:
tier 1 (answer transfer) *"is fully deterministic and carries no assumption beyond the collision
signals already calibrated in `check_device_collision.py`"*, and `check_device_collision.py` **is**
registered `gating=True` in `run_guard_battery.py:180`. Tiers 2 and 3 rest on a hand-declared
taxonomy, and the script itself flags the gerrymandering risk: *"Naming those categories is the
single hand-set input here, and it is where this measure could be gerrymandered."*

**Wiring action: NONE. Do not wire this.** Keep it as an evidence script. If anything, give it the
missing unit tests before it is cited in another result.

**Blast radius:** zero, because it cannot run on the corpus as constituted.

**What the prior review missed:** that tier 1 is already covered by a registered gating guard, and
that its input contract makes it structurally incapable of gating a book.

---

## Case 8 (NEW, missed by the review): `validator/blind_spots.py`

**Verdict: the worst instance in the repository, and the table omits it.**

`grep -rn "blind_spots" --include=*.py src/ scripts/ tests/` returns **only**
`tests/unit/test_blind_spots.py` and one comment in `tests/unit/test_information_state_probe.py`.
Zero callers in `src/`, zero in `scripts/`, zero in CI, zero in the battery.

This is the module whose one-line purpose is: *"Say what the gate did NOT look at, so its silence
stops reading as a pass."* It is the W6 KEEP (`workplan:550`, *"KEEP: declarations are drift-proof
by witness"*), built specifically as the cure for AL-325 and AL-337, the exact disease synthesis
section 2 documents. It is itself the disease, in its most acute form: **the detector built to
detect undetected things is undetected.**

Concretely, three consequences:
- `blind_spots(context)` output is never persisted into `validation_report`, so the review surface
  cannot render *"this verdict did not examine: content safety / levels of meaning / knowledge
  demands"* to the approving guardian.
- `verify_declarations()`, the witness battery that makes the manifest drift-proof, which is the
  entire reason W6 said KEEP rather than "put it in prose", runs only inside a unit test.
- C4-5 notes that **safety appears in neither** the OBSERVED nor the UNOBSERVED list, so even if it
  were wired, its manifest is presently incomplete on the dimension that matters most.

**Defect vs staged: DEFECT.** Nothing stages it. The workplan says KEEP; the module says its whole
value is reaching a verdict a human sees.

**Wiring action:** persist `blind_spots(context)` into the `GateResult` / `validation_report` blob
and render it in the review surface's summary strip; add `content_safety` to `UNOBSERVED`; run
`verify_declarations()` in CI. ~20 lines plus a review-surface field.

**Blast radius: zero blocks.** It adds one honest sentence to every approval screen.

Related modules I checked and deliberately do **not** count:
- `validator/continuity.py` (src=0, scripts=0, tests=1), same shape, but its docstring
  pre-commits: *"This is a reported statistic, not a gate … and unlike that module it is not a gate
  candidate either"*, with the measured reason (the exact formulation flags 3,815 of 4,472 nodes;
  the lexical one scores 1 true positive in 6). Counting it would be wrong.
- `validator/dialogue.py` (script-only), an instrument built to correct the judge's `dialogue`
  criterion, not a gate candidate.
- `diversity/panel.py` (src=0, scripts=1), wrapped by `scripts/run_diversity_eval.py`, which **is**
  in `.github/workflows/` and in `nox -s diversity_eval`. Properly wired.
- `diversity/incell.py`, reached via `scripts/check_incell_clones.py`, which runs in `ci.yml:580`.
  Properly wired.

---

## C6-9's count, verified: "8 of 15 have no tests" is **inflated; the true figure is 5 of 15**

C6-9 names eight: `check_sibling_fills`, `check_solution_transfer`, `check_reading_level`,
`check_branch_obligations`, `check_promise_discharge`, `check_graph_structure`,
`check_fill_fidelity`, `check_incell_clones`. Checking each against `tests/`:

| Script | Claim | Reality |
|---|---|---|
| `check_reading_level` | no tests | **FALSE.** `tests/unit/test_guard_gating.py` loads it by `importlib` and holds two *discriminating* tests: `test_reading_level_unscorable_book_fails_check` and `test_reading_level_in_band_book_passes_check` (AL-294). |
| `check_sibling_fills` | no tests | **FALSE.** `tests/unit/test_bplus_checks.py:9`: `from scripts.check_sibling_fills import shared_grams`. Core function covered; CLI/gating path is not. |
| `check_incell_clones` | no tests | **CONCEDED by C6-9 itself**: `tests/unit/test_incell_clone_audit.py` exists. |
| `check_solution_transfer` | no tests | **TRUE**, zero references. |
| `check_branch_obligations` | no tests | **TRUE**, zero references. |
| `check_promise_discharge` | no tests | **TRUE**, zero references. |
| `check_graph_structure` | no tests | **TRUE**, zero references. |
| `check_fill_fidelity` | no tests | **TRUE**, zero references. |

**Corrected: 5 of 15 have zero test coverage; 2 have partial or indirect coverage; 1 claim is
wrong.** The direction of C6-9 holds and its recommendation is right; the number is 60% inflated,
and `check_graph_structure` (six named failure classes, the corpus S-5 will use) is correctly the
most alarming of the five.

The rest of C6-9 verifies clean: `[tool.mutmut] only_mutate` covers `storybook`, `validator`,
`player`, `publishing`, `moderation`, `events`, `story_requests`, `core/exceptions.py` and **not**
`generation/`, `diversity/`, `mutation/`, `measurement/`, `flywheel/` or `scripts/`; and the
script gates emit ad-hoc text with no stable rule ids.

---

## Recommendation review

> *"Adopt a rule with teeth: a validator module in `src/` with no gate caller is a build failure or
> is deleted."*

### As written, it cannot work. Three reasons.

**1. Its false-positive rate on today's tree is roughly 27%, and every false positive is a
documented KEEP.** Six of the 22 modules in `validator/` have no gate caller:
`consequence.py` (W3 KEEP, statistic), `paths.py` (W1 infrastructure), `continuity.py` (W6
follow-on, explicitly "not a gate candidate"), `dialogue.py` (W4 instrument), `blind_spots.py`
(W6 KEEP, router), `imitable.py` (router). The rule would delete or red-build all six. Four of
them are load-bearing evidence for claims the brief itself makes.

**2. "Gate caller" is undefined at the tier where most of the enforced quality now lives.** Five of
the seven cases are, or depend on, `scripts/check_*.py`. A rule scoped to `src/` cannot see them.

**3. The project already adopted the right version of this rule, and the synthesis does not know
it.** `AL-305` (2026-08-12): *"**A checker that nothing invokes is not a gate, however complete it
is.** … Registering a checker in `run_guard_battery.py` is part of shipping it, not a follow-up, and
the registration itself needs a test: assert the script is invoked, that it is invoked with the flag
that makes it able to fail, and that its Result is recorded gating."* It is enforced by
`tests/unit/test_guard_gating.py`, and it is why cases 5 and 6 are refuted. The synthesis proposes
as new a rule that exists, and misses the actual failure, which is that **the registry AL-305
created has no runner**.

### The implementable replacement: three parts, all deterministic, no model spend.

**(a) Declared disposition, enforced by the existing lockstep test.** Every module under
`validator/`, `moderation/`, `diversity/` and every `scripts/check_*.py` declares a module-level
`DISPOSITION: Final = "gate" | "router" | "instrument" | "infrastructure"`. Extend
`tests/unit/test_validator_rules_catalog.py` (which already scans `validator/*.py` and fails on
code/doc disagreement in either direction) to also fail when:

- a module has no `DISPOSITION`;
- `DISPOSITION == "gate"` and no call path reaches it from `run_gate` or `run_guard_battery.battery`;
- `DISPOSITION == "router"` and no consumer renders or persists its output;
- `DISPOSITION in {"instrument","infrastructure"}` and it names no workplan row / ADR / UW row that
  licensed it (`consequence`→W3, `paths`→W1, `continuity`→W6, `dialogue`→W4).

Run against today's tree this fails on exactly **two** modules: `imitable.py` (router, no consumer)
and `blind_spots.py` (router, no consumer). That is the correct answer, and it is the whole point,
a rule that fires on 2 real defects and 0 documented decisions is implementable; one that fires on
8 including 6 decisions is not.

**(b) Run the registry.** Add a CI job invoking `scripts/run_guard_battery.py` over the committed
skeleton/fill pairs, and make `cyo-author` step 6 invoke it. This is the single highest-leverage
action in the whole section: it converts ten already-registered gating guards from theoretical to
real. It has two hard preconditions, both found in this pass and neither previously known:
the `--allow-title-rewrite` / `{PLACEHOLDER}` defect, and the 12 drifted corpus pairs.

**(c) Adopt C6-9's rule ids as written.** Give the script gates stable ids (`FI-*`, `GS-*`, `SF-*`),
emit through `ValidationFinding`, add to `validator-rules.md`, widen `_VALIDATOR_DIR` to
`scripts/check_*.py`. One change brings them under catalog lockstep, entry-point firing, and
mutation scoring at once. Extend `only_mutate` to `generation/` and `scripts/`.

### Which of the seven should NOT be wired

| | Why not |
|---|---|
| **1 `consequence.py`** | Promotion is pre-committed to W12 by AL-337. Wiring it *is* the failure AL-337 records. Wire the duplicate-target rule instead. |
| **3 `paths.py`** | Nothing to wire; it is a library. The action is building a consumer, which is feature work. |
| **7 `check_solution_transfer.py`** | Tier 1 is already gated by `check_device_collision`; tiers 2-3 rest on a taxonomy the script itself calls gerrymanderable; zero tests; input contract cannot take a book. |
| **4 `check_safety` (the *implement* branch)** | Do not add a lexicon-based safety ERROR to the gate without an ADR. **Do** take the delete branch: remove `safety_flagged` and its five dead reads, and declare `content_safety` in `blind_spots.UNOBSERVED`. |

### Ranked by value per unit effort

| # | Action | Effort | Blast radius today | Why here |
|---|---|---|---|---|
| 1 | **Case 5, fill-rate leg only** → `import_story.py` | ~10 lines | **0 books blocked** (31/31 pass; min 66.8%) | Catches a measured 39-53% waste mode, costs nothing, blocks nobody. |
| 2 | **Case 8, `blind_spots` → `validation_report`** | ~20 lines + one UI field | 0 blocks | The meta-fix. Makes every other gap in this report visible to the approver instead of silent. |
| 3 | **Case 2, `imitable` → moderation pipeline** | ~15 lines | 0 blocks, +13 endings of review across 6 books | Cheapest real safety gain; corrects a false `UW-C264` status line. |
| 4 | **Case 1's duplicate-target rule** (not `consequence.py`) | one `PL-*` rule | **4 of 84 shells**, 3 with a one-node fix | Closes the C1-3 seam too; needs no reader evidence. |
| 5 | **Run `run_guard_battery.py` in CI + `cyo-author`** | one job + 2 bug fixes + 12 corpus repairs | 10 guards go live; 12 drifted pairs must be reconciled first | Unblocks cases 5 and 6 together and honours AL-305. |
| 6 | **Case 4, delete `safety_flagged`** | ~30 min | 0 | Removes five dead reads and one phantom rule; fix the `UW-C292` mis-citation while there. |
| 7 | **Case 3, build a path-scoped safety consumer** | feature work | unknown | Real coverage gap (C4-1), but new construction, and W2 shows naive re-unitting fails. |
| 8 | **Case 7** | - | 0 | Do not wire. |

---

## What everyone missed

1. **`scripts/run_guard_battery.py` exists, registers ten gating guards, and nothing runs it.**
   This single fact refutes two of the seven cases and replaces them with one better finding. The
   review searched for callers of the *leaves* and never found the *registry*.
2. **The battery would fail 28 of 31 books if run today**, on a flag/placeholder defect in its own
   `check_fill_integrity` registration, which is the most likely reason nobody runs it, and is
   exactly the AL-293 class of defect one level on.
3. **12 of 31 committed skeleton/fill pairs have already drifted structurally** (verified:
   `the-night-market` shell edited 2026-08-20 in PR #730, fill committed 2026-08-16; shell has
   `n_hub2`/`n_hub3`, fill has `n_promise`). The corpus is silently inconsistent, and the unwired
   detector is precisely the one that would have caught it. Nobody reported this.
4. **The fill-rate floor has zero blast radius**, 31/31 pass, minimum 66.8%. The strongest
   argument for the report's top recommendation was available by running the tool and was not run.
5. **`validator/blind_spots.py` is the eighth and worst case**, and it is the module built to
   prevent this exact failure. Omitting it from the table is the review's largest miss.
6. **The duplicate-target blast radius is 4 shells, not 11.** Seven of the eleven differentiate by
   condition or effect and are legal under C1-2's own proposed wording.
7. **AL-305 already states the recommendation**, and states it better (it names the registry and
   requires a test of the registration). The synthesis reinvents it without the registry.
8. **The `UW-C292` citation in `validator-rules.md:291` is wrong**, that row is about
   `_build_graph` and PL-20/25/26, and is `done`. No UW row tracks SAFE-14.
9. **Stage 1 already carries `real_world_danger` as a BLOCK-tier criterion**, so case 2's harm class
   is covered by a different construct rather than unscreened; and **`check_device_collision` is
   registered gating**, so case 7's tier-1 signal is already enforced. Both weaken their findings.
10. **`pyproject.toml` has no `[project.scripts]` and no `[project.entry-points]`**, and the only
    `importlib` use in `src/` is `importlib.resources` template loading. There is no plugin
    indirection anywhere in this codebase. Every "unwired" verdict here is safe from that objection.
