# Remediation plan: gap analysis of the 2026-08-22 generation research brief

Plan of 2026-08-22. Companion to
[cyo-brief-gap-analysis-2026-08-22.md](./cyo-brief-gap-analysis-2026-08-22.md); raw reports in
[evidence/brief-gap-analysis-2026-08-22/](./evidence/brief-gap-analysis-2026-08-22/README.md).

> ## Supersession notice, 2026-08-30
>
> **This plan was written on 2026-08-22 against a tree that has since moved 45 commits. Read
> [the gap analysis's supersession notice](./cyo-brief-gap-analysis-2026-08-22.md#supersession-notice-2026-08-30)
> before planning any item below.** In short: `GA-D1` is largely answered by the ADR-005 amendments
> of 2026-08-25 and 2026-08-28 (#764, #769, #776, #778), leaving only three residuals; the economics
> items are superseded by [unit-cost-model.md](./unit-cost-model.md) (#784); `W1` is half fixed
> (`api/generation.py:181` now passes `rq_job_id`, `api/story_requests.py:107` still does not); the
> body-only gram scope `W3` asks for already exists in three committed callers; and V11's dead second
> sweep is fixed. The decision ids here are namespaced `GA-D1` and `GA-D2` so they cannot be confused
> with the `D1`..`D4` in
> [generation-review-workstream-plan-2026-08-22.md](./generation-review-workstream-plan-2026-08-22.md),
> which schedules the parallel `R-1`..`R-14` review track; sequence the two together, not separately.
> Items that still stand unweakened: the unwired `validator/blind_spots.py` and `validator/imitable.py`,
> the strict-bar recalibration, the cross-vendor `TAU_CELL` breaches, `UW-C290`'s false done marking,
> and the three un-voided pre-registration rows.

> **Two items are superseded by the live structural round (PR #737).** `W5`'s rationale was wrong:
> the 0.6 floor blocks zero *committed* pairs but current v4-pro fills span 42.9% to 65.2%, so
> wiring it is enforcement, not instrumentation. And the differentiation directive is now measured
> and refuted as a lever (96.3 to 110.7 per 1000, the wrong way). See
> [the reconciliation](./cyo-brief-review-reconciliation-2026-08-22.md).

One plan per item that survived adversarial validation. Retracted findings are not planned here;
see the correction log (synthesis section 2) for why each was dropped.

> **Effort** is relative: **S** under a day, **M** a few days, **L** a week or more. **Blast radius**
> is what changes for the catalog, in-flight requests, or published books.

---

## 0. Sequencing

```text
GA-D1 hard-block ruling ──────────► GA-D1's own accountability requirements (no W item owns them)
GA-D2 F5 architecture ruling ─────► W10 settling experiment, and any stratified-plan work

W1 job lifecycle ──── prerequisite ► W2 reading-level cap      (timeout/occupancy interact)
W3 gram scope (UW-C225) ──────────► W10, and any convergence claim
W4 content-filter terminal ───────► independent, ship anytime
W5 battery runnable ──────────────► W6 walk floor (needs a runner to enforce anything)
W8 CG recalibration ──────────────► ANY --strict work (blocks it entirely)
W9 register integrity ────────────► GA-D2's voiding step is safer after this
```

**Two hard orderings.** `W1` before `W2`, because changing fill-call behaviour while jobs can be
double-enqueued multiplies the leak. `W8` before any `--strict` enforcement, because enforcing today
collapses selection from 74 shells to 20.

> **Correction, 2026-08-30.** The first line of the sequencing block read
> `GA-D1 hard-block ruling ──────────► W7 approval guard (shape depends on the ruling)`. That
> dependency pointed at the wrong item: `W7` is *Wire the two genuinely unwired detectors*
> (`validator/blind_spots.py` and `validator/imitable.py`), which has nothing to do with the
> approval path. No `W` item in this plan owns the approval-guard work, so the arrow now points at
> GA-D1's own five accountability requirements, which are where that work is actually specified.
> Anyone scheduling it should treat those five requirements as the work item and give them a ledger
> row of their own; see the status note under GA-D1 below for which of the five `main` has since
> closed.

---

## P0. Decisions that are not code changes

### GA-D1. Rule on the hard-block publish override

**Problem.** A book carrying a moderation hard block can be published in two clicks: edit any node
of an `in_review` book (the fresh BLOCK merges, status stays `in_review`), then Approve.
`publishing/service.py:412` guards only `moderation_report is None`. `has_hard_block` is read at
eight sites, all inside `moderation/`. No DB constraint exists across the 67 migrations on `main` as of 2026-08-30 (63 when written). The frontend
gates on status alone while rendering a "Hard block" badge.

**This is deliberate.** It is commented `#CRITICAL` in `node_edit.py` as an intentional ADR-005
position ("surfaced, never rejects the write"), locked by a passing test
(`tests/unit/test_node_edit.py:846`), and the service comment states the invariant as "no
*unmoderated* path reaches published", which is screened-ness, not block-freeness. So the plan is a
ruling, not a patch.

**Step 0, before anything else.** Query production for published versions with
`summary.hard_block: true`. **Nonzero means this is a live incident, not a latent gap**, and the
plan changes to incident response. This could not be run from the analysis session: the `supabase`
MCP server is unauthenticated and needs authorising via claude.ai connector settings, or
`claude mcp` / `/mcp` in an interactive session.

**The ruling to make.** Either (a) hard block becomes a publish-blocking condition, or (b) override
stays and becomes accountable. The review recommends (b), because (a) contradicts a twice-affirmed
ADR and removes a legitimate admin escape hatch.

**If (b), the accountability requirements** (these are the real defects, and they hold under either
ruling):

1. A typed override reason on `ApproveBody`, required when `has_hard_block` is true.
2. The blocking finding ids copied onto the approval record at approve time, so the override is
   reconstructable after a later re-moderation changes the report.
3. A version hash pinned in `ApproveBody`, so approval binds to the exact artifact reviewed.
4. Separation of duties: an adult holding both guardian and admin may not approve a hard-blocked
   book for their own family.
5. An `override` event in `events/` and a distinct admin-dashboard surface, so overrides are
   countable.

**Acceptance.** A hard-blocked publish is impossible without a stored reason, finding ids, and a
version hash; overrides are countable; a dual-role self-approval of a blocked book is refused.
**Falsifier.** Any code path reaching `published` with `has_hard_block` true and no override record.

**Effort** M. **Blast radius** none for existing books; new required field on approve.

> **Status of the five requirements as of 2026-08-30.** Two of the five have since been closed on
> `main` by the ADR-005 amendment of 2026-08-25 (gate D2), so this section is preserved as the
> record of what the analysis found on 2026-08-22, not as an open work list. Re-verified against
> `main`:
>
> | # | Requirement | Status on `main` |
> |---|---|---|
> | 1 | Typed override reason, required when the report carries a block | **Met.** `ApproveBody.override_reason` is required whenever `severe_finding_counts()` reports a block or a high-severity flag; `publishing/service.py` raises `BusinessLogicError(rule="approve_requires_override_reason")` on a missing or whitespace-only reason. |
> | 2 | Blocking finding *ids* copied onto the approval record | **Open.** The audit payload carries `overridden_block_count` and `overridden_high_count`, which are counts, not ids, so an override still cannot be reconstructed after a later re-moderation rewrites the report. |
> | 3 | Version hash pinned in `ApproveBody` | **Open.** Approval still binds to a version row, not to a hash of the artifact reviewed. |
> | 4 | Separation of duties for a dual-role adult | **Open**, and see the note below. |
> | 5 | A countable override event and an admin surface | **Partly met.** The approval emits a `storybook_approved_over_severe_finding` log line and the RELEASED event payload carries the two override counts, so overrides are countable from the event log. There is no distinct admin-dashboard surface. |
>
> **On requirement 4, stated precisely.** `api/approval.py::_load_admin_story` authorises on
> `ctx.principal.is_admin` alone and deliberately does not call `authorize_family`, because admin
> authority is cross-family by design. An adult who holds the guardian base role plus the
> orthogonal `is_admin` capability can therefore approve a book belonging to their own family,
> including over a hard block, provided they supply an override reason. `Principal.acting_role()`
> returns `ADMIN` only when the target family differs from the principal's own, so the audit event
> stamps such a self-approval as `guardian`: the act is *distinguishable* in the log but not
> *prevented*. Four-eyes approval is not an existing invariant of this system, and ADR-005 names
> this the owner-as-admin exception. What the 2026-08-25 amendment retired is the framing this
> section used elsewhere, "two clicks, untraced, unversioned": the override is now refused without a
> reason and the reason is recorded. What survives is separation of duties, and only that.
**Rollback** the guard is one conditional plus a nullable column; revert is clean.

### GA-D2. Rule on what F5 actually claims, and void the edited register rows

**Problem, in three parts.**

1. **The shared stratum is the decision space.** `world_recipe.requires` is byte-identical across
   both D-7b contracts and is a closed, enumerated menu of narrative decisions with draw counts
   (`cipher_forms` 1 of 5, `access_details` 3 of 7, `remedies` 1 of 6, and six more). F5 says
   "never reuse decisions". D-7b reuses the decision menu and generates only its realisation.
2. **The evidence was strengthened after the fact.** Commit `bf7cad1` (2026-08-12, PR #703) rewrote
   three already-`done` Falsifier cells, flipping D-7b from "at the 3.3 floor" to "*below* the 3.3
   floor" without the voiding the register's own section F requires. The published 2.3 needs two
   method changes; one is disclosed.
3. **The floor does not survive a control.** 148 unrelated pairs at matched scale give mean 1.94,
   CI [1.25, 2.64], P(mean >= 3.3) = 0.0008. The published 3.3 is the 80th percentile of the null;
   D-7b at 2.33 sits at the 66th.

Also unreported in the brief: the D-7b **recognition verdicts** (`first_yes_position: 2`,
`distinctness 1/5`, both raters naming an identical three-way opening act) are the programme's own
pre-registered falsifier firing on F5's flagship artifact.

**The ruling to make.** Sharing a closed decision menu across books may well be the right
architecture. It is simply not what F5 says. Decide which of these F5 means, and restate it:

- **F5-a**: share topology only, generate the decision menu per book. Expensive, matches the current
  wording.
- **F5-b**: share topology and the decision menu, generate the realisation per book. Cheap, matches
  what D-7b actually tested, and needs a different variety argument because the menu is the thing a
  reader tracks.

**Plan steps.**

1. Void and re-close D-6, D-7 and D-7b per section F, recording the method change and the two-part
   scope correction explicitly.
2. Rebuild the idiom floor from the matched-scale control (`V1` has the method) and republish every
   figure that cites it, including the ones the correction favours.
3. Put the recognition verdicts into the F5 decision record.
4. Restate F5 as F5-a or F5-b in the brief.

**Do not** reconstruct D-7b selections to run `check_solution_transfer.py`. Tier 1 of that tool is a
text-similarity test, so whoever writes the reconstruction sets the answer, a larger degree of
freedom than the category choice its own docstring warns about.

**Acceptance.** F5's wording matches the architecture actually in use; no published convergence
figure cites the 3.3 floor without its CI. **Falsifier.** A matched-scale control that puts D-7b
below the rebuilt floor would restore the original claim.

**Effort** M, mostly writing. **Blast radius** documentation and the register only.

---

## P1. Code items

### W1. Fix the job lifecycle (the only live money leak)

**Problem.** `queued->running` is never committed in its own transaction, so one sweep is dead and
another re-enqueues live jobs; the story_requests enqueue omits `rq_job_id`. Result: double spend on
the family path, and a data-integrity bug.

**Change.** Commit the `queued->running` transition in its own transaction before work begins; pass
`rq_job_id` at `api/story_requests.py:107`; widen the stale-claim window to exceed the longest
observed fill (measured runs reach 1,874s against a 1,800s RQ timeout, so the job timeout needs
raising in the same change).

**Files.** `generation/queue.py`, `generation/worker.py`, `api/story_requests.py`, RQ config.

**Tests.** A test that a job observed mid-run is not re-enqueued by either sweep; a test that the
enqueue records `rq_job_id`; a test that a job exceeding the old 1,800s bound is not killed
mid-fill.

**Blast radius** none for the catalog; in-flight jobs at deploy should be drained first.
**Rollback** clean. **Effort** S-M. **Dependency** none, and it blocks `W2`.

**Acceptance.** No duplicate RQ job for one story request under a forced restart.
**Falsifier.** A double-enqueue reproducible after the change.

### W2. Cap the reading-level loop

**Problem.** The loop is **38%, 51% and 59%** of a book's bill across three measured books, with an
uncapped call count, for an `in_band` result of 0.155. This is the single largest recoverable cost
item; every other fill-stage fix totals $0.05-0.08 per book.

**Change.** A hard per-book call cap plus an early-exit when successive passes stop improving
`in_band`. Record the achieved `in_band` on the book so the quality cost of the cap is visible
rather than assumed.

**Files.** the reading-level pass in `generation/`, `generation/usage.py` for attribution.

**Tests.** A test that the cap binds; a test that `in_band` is recorded; a fixture asserting cost
attribution per stage.

**Blast radius.** Band compliance may fall. Measure `in_band` before and after on the same books and
publish the trade. Do not ship the cap without that number.
**Rollback** config value. **Effort** S. **Dependency** `W1`.

**Acceptance.** Median book cost falls by the predicted share with `in_band` no worse than an agreed
floor. **Falsifier.** `in_band` degrades materially at the chosen cap.

### W3. Land `UW-C225`: make the gate and the calibration measure the same thing

**Problem.** `check_sibling_fills.py` grams a joined string, so 4-grams spanning a body/label
boundary count as shared prose. It returns 3.2 on D-7b where the published body-only figure is 2.3.
`run_guard_battery.py` gates on the label-inclusive scope against body-only calibration. The row
already exists with a proposed fix and pre-established regression counts (48 / 34 / 37 / 9), status
`unscheduled`.

**Change.** Compute grams per unit and union the sets, per the registered fix. Name the scope in
every output line so a figure can never again be quoted without it. Publish both scopes side by
side rather than silently switching.

**Files.** `scripts/check_sibling_fills.py`, its tests, and every doc quoting a convergence figure.

**Tests.** The register's pre-established expected counts as a regression test, not "no body-only
figure moves" (the register notes `diverge` legitimately moves 38 to 37, 13.6 to 13.2).

**Blast radius.** Published figures change. That is the point; do it in one commit that restates all
of them. **Effort** S. **Dependency** none, and `GA-D2` and `W10` both depend on it.

**Acceptance.** Gate scope equals calibration scope; every published rate names its scope.
**Falsifier.** Any remaining figure whose scope cannot be determined from its own output.

### W4. Classify content-filter failures as terminal, and fix the infinite-retry path

**Problem.** Two distinct bugs with one symptom. A content filter can be **deterministic for a
(skeleton, brief) pair** (`AL-492`: book 0 failed 7 of 7, including a re-run at 397.59s against
397.96s), and is reported as a generic transient failure, so the harness retries what can never
succeed. Separately, a validator drove the parsers live and showed a content-block response yields
`dig_content=None` with `finish_reason='stop'`, classified transient, **retried forever**.

**Change.** Read `finish_reason` outside the adapter and map it: `content_filter` terminal with a
distinct error, `length` a truncation error that triggers continuation rather than restart, `stop`
with empty content a hard error rather than a transient. Surface a "billed but empty" counter.

**Files.** `generation/providers/*`, `generation/orchestrator.py`, `generation/usage.py`.

**Tests.** A parser test per provider for each `finish_reason` including the empty-content-with-stop
case; a test that a terminal classification does not retry.

**Blast radius.** Some currently-retried requests will fail faster and visibly. That is the
improvement, but it will look like a regression in success rate; announce it.
**Effort** S-M. **Dependency** none.

**Acceptance.** A deterministic content-filter pair fails once, not seven times.
**Falsifier.** Any response shape still reaching an unbounded retry.

### W5. Make the guard battery runnable, then run it

**Problem.** `run_guard_battery.py` is the registry, and it is invoked by nothing but its own test.
`check_fill_integrity` and `check_sibling_fills` are correctly registered `gating=True` inside it. So
the first-round framing ("unwired detectors") was wrong; the defect is one level up. **`AL-305`
already states this rule and names this registry.** Run today, the battery would fail 28 of 31 books
for a missing `--allow-title-rewrite` and a `{PLACEHOLDER}` blind spot in `_defers_titles`, neither
of which is a real defect.

**Change.** Fix the two false-failure causes, add a runner (CI job over committed pairs, plus a
make/nox target), and ship the fill-rate leg as `needs_review` rather than a block: **0 of 43
committed pairs fail at 0.6** (tightest good 0.634), so blocking buys nothing today while
`needs_review` starts producing signal.

**Files.** `scripts/run_guard_battery.py`, `scripts/check_fill_integrity.py`, a CI workflow, `noxfile.py`.

**Tests.** A test that the battery runs clean over the committed corpus; a test per false-failure fix.

**Blast radius.** None while the fill-rate leg is advisory. **Effort** M. **Dependency** none, and
`W6` needs it.

**Acceptance.** The battery runs in CI and passes on the committed corpus for real reasons.
**Falsifier.** A book failing the battery for a cause unrelated to its content.

### W6. Split the walk floor by form and enforce it for prose CYO

**Problem.** Verified across the 84 real graphs: **five shells have exactly P(satisfying ending)
= 0.0000** on a random walk, eight at or below 0.00005, and 11 selectable shells breach the floor.
All are 13-16 and 16+.

```text
0.0000  the-labyrinth-of-glass (13-16)   0.0000  the-tenfold-siege (16+)
0.0000  the-ashfall-expedition (16+)     0.0000  the-drowned-court (16+)
0.0000  the-pale-road (16+)              0.0000  the-thornwood-trial (13-16)
0.0000  the-red-meridian-run (16+)       0.0000  the-iron-spire-trial (13-16)
```

**The honest caveat.** 16+ is gamebook-form, where a punishing win rate is a genre convention and the
cell median is 0.0000 by design. The defensible position is not "raise the floor everywhere" but
"the rule currently applies to a form it was not written for, and is unenforced everywhere".

**Change.** Make the floor form-aware: enforce it for prose CYO, and declare an explicit,
documented gamebook exemption with its own (lower, non-zero) floor. Then enforce it via `W5`.
Separately, `satisfying_walk_probability` ignores choice conditions and can silently return a
non-converged estimate; fix or declare that before enforcing.

**Files.** `scripts/check_skeleton.py`, `validator/band_profile.py`, `validator/walk.py`.

**Blast radius.** The three 13-16 shells at zero become non-compliant and need repair or retirement.
Check cell depth first: retiring them must not empty a cell.
**Effort** M. **Dependency** `W5`.

**Acceptance.** No prose-CYO shell is selectable below its band floor; gamebook exemption is written
down. **Falsifier.** A prose-band shell at P=0 still selectable.

### W7. Wire the two genuinely unwired detectors

**Problem.** After validation, only two of the original seven cases are genuine.

- **`validator/imitable.py`**: zero callers outside its own test. It screens the one harm class the
  programme discovered itself (a child imitating an action). Partially covered: Stage 1 carries
  `real_world_danger` as a BLOCK criterion. Reproduced at 13 of 167 across 6 books, 0 blocks.
  `UW-C264`'s present-tense claim that it "routes 13 of 167" is false.
- **`validator/blind_spots.py`**: zero callers outside its own test. It is the module built to make
  gate silence legible, and it is itself silent.

**Change.** Register both in `run_guard_battery.py` (advisory first), measure the finding rate over
the committed corpus, then decide the gating threshold from that measurement rather than up front.
Correct `UW-C264`'s status.

**Blast radius.** None while advisory. **Effort** S. **Dependency** `W5`.

**Acceptance.** Both produce findings on the corpus and their rates are published.
**Falsifier.** Either fires on nothing across the whole corpus, which would mean it is not a
detector at all.

---

## P2. Larger items

### W8. Recalibrate CG-1/2/3 against a non-circular anchor (blocks all `--strict` work)

**Problem.** **97% of strict findings are CG-1/2/3**, a rule family calibrated to an internal
designer table while everything else is calibrated to the JHM corpus. CG-2 demands 3-way decisions
where JHM's *maximum* outdegree averages 2.58. Enforcing `--strict` today collapses selection from
**74 shells to 20, one per cell in 16 of 18 cells**, which causes a worse variety problem than it
solves. Separately, CG-2 has no hub exemption, so enforcement deletes `open_map` (2 of 13 pass) and
`time_cave` (0 of 9) from the catalog entirely.

**Change, and it is free.** Run `check_skeleton.py` over the 40 JHM digraphs the repo already cites
and set a two-sided policy: admit at least X% of the anchor corpus, reject 100% of a seeded-defect
corpus. That replaces circular calibration (several thresholds are percentiles of the corpus they
gate) at zero data cost. Add a hub exemption to CG-2. Then re-measure how many shells fail
`--strict` and decide enforcement on the new number.

**Also settle two rule defects found alongside.** `_build_graph` collapses parallel edges while
`max_indegree` counts them, so phantom choices satisfy PL-17/25/26 while the graph stays a tree for
PL-18; and every strict-blocking finding currently prints "advisory only" (2,456 of 2,456).

**Blast radius.** Potentially large and in the right direction: recalibration should *raise* the
number of compliant shells. **Effort** L. **Dependency** none, blocks any `--strict` decision.

**Acceptance.** A published two-sided calibration with anchor admit rate and seeded-defect recall.
**Falsifier.** The anchor corpus failing the recalibrated rules would mean the rules encode
something other than the form.

### W9. Harden the honesty machinery

**Problem.** Six holes, each demonstrated against the live checkers.

1. The lessons log's "append-only" docstring is false: deleting the newest lesson, or any lesson
   plus a tail renumber, passes.
2. The consecutive-id rule *forces* renumbering, which has already broken a real citation
   (`bf7cad1` cites AL-296/297 for content now at AL-309). **This plan hit the same hazard: this
   branch ends at AL-508 while the sourcing branch holds AL-509..513, so no lesson can be appended
   here without either failing the checker or colliding on merge.**
3. A register row may cite a nonexistent lesson.
4. A `rejected` lesson can be flipped to `applied` with one `sed`.
5. The diversity register, which holds every falsifier in the programme, has zero automated checks.
6. Pre-registration precedence rests on branch-local commit order, which this squash-only repo
   destroys at merge. The sourcing branch will collapse S-1's registration and its results into one
   commit.

**Change.** Content-hash prior rows rather than relying on id order; extend `check_work_linkage.py`
to the diversity register; require a machine-checkable anchor for `applied` (SHA, PR, or test node
id) and forbid `rejected -> applied` without one; record a pre-registration timestamp in the row
itself so precedence survives squash.

**On the `applied`-ref recount.** The first-round figure of 57 unresolvable refs is **wrong**. An
independent resolver gives **4** under "no machine-checkable anchor of any kind" and **140** under
"no anchor pinning a specific change". No consistent definition yields 57. The *mechanism* is
confirmed: `applied` simultaneously satisfies the ref test and deletes the scheduling obligation.

**Effort** M. **Acceptance.** Each of the six edits is rejected by a checker.
**Falsifier.** Any of the six still passing.

> **Disposition for `UW-C290`, added 2026-08-30.** The supersession notice lists `UW-C290`'s false
> `done` marking among the items that stand unweakened, and this plan carried no remediation,
> exclusion, or ledger binding for it. It is scoped here as an instance of `W9`, not as a new item:
> it is exactly the failure mode `W9` exists to close, a register row marked `done` whose subject
> was never built. Re-verified against `main` on 2026-08-30: `src/cyo_adventure/validator/safety.py`
> is still the 57-line Phase-2 stub whose `check_safety` returns an empty `ValidationReport()`, and
> `src/cyo_adventure/validator/gate.py:269` still calls it (`merged.extend(check_safety(story))`),
> so the gate merges an empty report on every run and no deterministic safety rule is enforced
> there. Nothing about the finding has been overtaken. The `W9` change that closes it is the
> requirement that `applied` and `done` carry a machine-checkable anchor: a row claiming this one is
> done has no SHA, PR, or test node id that could satisfy that requirement, because no such change
> exists. Owner action needed: bind `UW-C290` to `W9`'s ledger row rather than leaving it
> unscheduled.

### W10. Settle model selection properly

**Problem.** Of the brief's per-stage recipe, only **"checker in the author's loop"** and **"not
v4-pro for structure"** (0/6, p=0.0022) survive scrutiny. "Frontier Anthropic converges fastest"
fails: Kimi K3 at 5/6 versus 6/6 is p=1.00, and the endpoint test gives p=0.435 across legs.
"Fill with V4 Pro" rests on a judge panel with dialogue SD 0.00 and a formally retracted ranking.
"Review with V4 Flash" is uncited. The tool-assisted arm is also censored (14 of 42 at the
invocation cap) and has **no blind cell D**, so the 15/21 headline has no control arm.

**A related result worth its own row.** **7 of 342 shell-shell pairs breach TAU_CELL, all
cross-vendor** (Opus and Kimi at 0.0191), with three separate labs independently emitting 45 nodes,
91 choices, branching exactly 3.000, while **zero of 190 shell-catalog pairs breach it**. Models
converge on each other, not on the catalog. This bears directly on whether model diversity can serve
as a variety lever, and nobody had reported it.

**Change.** Run the settling experiment: 3 legs x 12 replicates x 2 counterbalanced cells, an
uncensorable primary endpoint (not repair rounds, which degenerate under the cap), and a
harness-instrumented loop so no arm is hand-recorded. **Under $5 of credit**; the cost is engineering
time.

**Do not add a novelty term to the pass criterion.** TAU_CELL already exists, nothing breaches it
against the catalog, it targets the wrong axis, it penalises gate compliance, and one feature moving
off zero buys 0.0455 against a 0.05 floor.

**Effort** M. **Dependency** `W3` for any convergence measurement.
**Acceptance.** A primary endpoint that cannot degenerate, with every arm instrumented.

---

## Do not do

Each was proposed in round 1 and refuted in round 2. Recorded so it is not re-proposed.

| Proposal | Why not |
|---|---|
| Enforce `--strict` as-is | Collapses selection 74 to 20; deletes `open_map` and `time_cave`. Do `W8` first. |
| Gate `consequence.py` | **`UW-C181` is an owner ruling rejecting it** (loop-back exploration is a convention of the form). It also returns `None` for 48 of 84 books and 69 have no variables. Self-labelled "a reported statistic, not a gate". |
| Add a novelty term to the pass criterion | See `W10`. |
| Build path-level evaluation now | Building it before the instrument question is settled is the F6 failure the review otherwise criticises. Cost is known and affordable (271 covering paths on the 677-node book, 100% edge coverage, 1.22s; about $0.46 per book batched on Haiku), so it is a sequencing call, not a feasibility one. |
| Reconstruct D-7b selections for solution transfer | The reconstructor sets the answer. |
| A blanket "validator module with no gate caller fails the build" | Unimplementable: 6 of 22 validator modules have no gate caller and every one is a documented KEEP. Use a declared DISPOSITION field enforced by the existing catalog lockstep. `AL-305` already states the better version. |
| Guardian-primary approval as the economics fix | ADR-005's 2026-06-30 amendment moved the approver *to* admin, owner-confirmed and re-ratified 2026-07-16; `visibility=catalog` publishes cross-family. The binding constraint is ADR-008's Kids Category "pre-moderated pipeline" commitment, not COPPA/KWS. |

---

## Ledger rows, as allocated

**Allocated, not draft.** These rows land in `docs/planning/authoring-lessons-log.md` and
`docs/planning/unscheduled-work-register.md` on `docs/consolidate-landing-ledger`, which is the
single allocation point for the five parallel landings; the ids below are the real ones. The
lessons log is gapless, so ids could not be allocated on this branch: when this plan was first
written it ended at `AL-508` while the sourcing branch held `AL-509..513`, and appending here would
have failed `check_lessons_log.py` or collided on merge. That is `W9` hazard 2 occurring in
practice, and the consolidation branch is the workaround.

**Four of the fifteen proposals were already covered** by rows the consolidation branch or `main`
holds, so they are cross-references rather than new work. They are marked *bound* below.

### Authoring lessons (`| ID | Date | Source | Category | Lesson | Proposed change | Status | Ref |`)

| ID | Category | Lesson | Proposed change |
|---|---|---|---|
| `AL-732` | process | A published figure was quoted from a tool that computes a superseded scope; three reviewers and the synthesis author all reproduced 3.2 against a published 2.3 without checking that the tool matched the publication. | Make every convergence tool print its scope on every line, and forbid quoting a rate without it (`W3`). |
| `AL-733` | process | `bf7cad1` rewrote three already-`done` Falsifier cells, flipping D-7b from at the floor to below it, with the method change disclosed only in the commit body. | Require section F voiding for any edit to a closed pre-registered row, enforced by a checker (`W9`). |
| `AL-734` | validator | A calibration floor (3.3 shared grams) was published without a matched-scale control; the control puts it at the 80th percentile of the null, inverting the claim it supported. | Every calibrated threshold ships with its control and CI, or is marked provisional (`W8`). |
| `AL-726` *(bound)* | tooling | `run_guard_battery.py` is the gate registry and is invoked by nothing; two checks registered `gating=True` therefore gate nothing, and the failure was misread as the checks being unwired. | Already recorded. `AL-726` states the same defect and terminates the chain at a workflow or nox session; `UW-C453` is its work row and carries the CI runner (`W5`). |
| `AL-735` | validator | Five catalog shells give a random-walking reader exactly zero probability of a satisfying ending; the rule that forbids this exists and is enforced nowhere. | Make the walk floor form-aware and enforce it through the battery (`W6`). |
| `AL-736` | process | A review run under a find-gaps instruction produced 63% criticality inflation and 40% absence-framed findings, at least 24 restating existing owner rulings or UW rows. | Any future review pass pairs each finding with a refutation attempt and a register lookup before it is reported. `AL-479` records the adjacent habit; this row adds the measured framing bias. |

### Unscheduled work (Cluster E `| ID | Item | Phase | Status |`, Cluster L `| ID | Item | Issue | Status |`)

| ID | Cluster | Item | Status |
|---|---|---|---|
| `UW-E17` | E (security/safety) | `GA-D1`: hard-block publish override is untraced, unversioned, and self-approvable by a dual-role adult. Blocked on the production `summary.hard_block` query and an owner ruling. | decision |
| `UW-C451` *(bound)* | C (lessons linkage) | `W1`: `queued->running` uncommitted and `rq_job_id` omitted cause double enqueue and double spend. Already recorded, from `AL-724`'s side; `UW-C451` names `api/story_requests.py:107` as the omitting call site and carries this plan's `W1` second leg explicitly, so it is one defect and not two. | unscheduled |
| `UW-L09` | L (live defects) | `W4` second leg: an empty-content response with `finish_reason: 'stop'` is classified transient and retried without bound. The content-filter leg of `W4` is already `UW-C309`, so `UW-L09` carries only the uncovered arm plus the single `finish_reason` mapping the two share. | unscheduled |
| `UW-G26` | G (diversity/catalog) | `W6`: 11 selectable shells breach the walk floor, 5 at exactly zero. | unscheduled |
| `UW-G27` | G (diversity/catalog) | `W8`: CG-1/2/3 calibrated to an internal table while the rest is calibrated to JHM; recalibrate against the 40 JHM digraphs before any `--strict` enforcement. | unscheduled |
| `UW-F58` | F (test/quality) | `W9`: four of the six demonstrated integrity holes. The other two, the lessons log's false append-only claim and the renumbering its consecutive-id rule forces, are already `UW-C266`. | unscheduled |
| `UW-C445` *(bound)* | C (lessons linkage) | `W10`: cross-vendor structural convergence, 7 of 342 shell-shell pairs breaching TAU_CELL while 0 of 190 shell-catalog pairs do. Already recorded, with the caveat that the statistics rest on an uncommitted harness and re-deriving them is part of the work. | unscheduled |
| `UW-K22` | K (documentation) | `GA-D2`: restate F5 as F5-a or F5-b; the shared stratum is byte-identical and enumerates the decision menu. | decision |
| `UW-C450` *(bound)* | C (lessons linkage) | Correct `UW-C264`: `imitable.py` has zero callers, so its present-tense "routes 13 of 167" is false. Already recorded, and it frames the correction as a decision rather than a copy-edit: wire the screen where its output reaches a human, or restate the row in the past tense with the module named as unwired. | unscheduled |

Each new lesson above is open, so each is cited by a cluster C row per the linkage contract:
`UW-C457` (`AL-732`), `UW-C458` (`AL-733`), `UW-C459` (`AL-734`), `UW-C460` (`AL-735`) and
`UW-C461` (`AL-736`). Those rows carry the reporting discipline; the deliverables sit in the
cluster each item's own description names.

---

## Resolution locality and spend

Every item classified as resolvable **locally** (no paid model calls) or requiring **OpenRouter**
spend. Estimates are anchored on measured runs, not list-price arithmetic.

**Anchors, all from committed run records.** The 2026-08-21 live structural round cost **$3.28
metered** in total: Run A (2 directed fills) $0.719, Run B (10 books, 92,870 words, ~206k in /
~186k out) $2.432, Run C (2 books, chunked v3.2) $0.070 to $0.133, endpoint probes (~12 x 32
tokens) $0.05, against a $2.85 estimate and a $5.70 stop rule. That gives **~$0.24 per book at
v4-pro** on a mid-band grid. The sonnet-5 comparison pair cost $3.27 for two books (**~$1.64 per
book**, $2.43 for the 13-16 gamebook alone). Per-band v4-pro fills measured $0.047 / $0.350 /
$0.538 / $1.064 at 3-5 / 8-11 / 13-16 / 16+.

**Anthropic tiers run as subagents cost $0 marginal** against the owner subscription. That is what
made the original vendor comparison non-comparable, so any design using subagent legs is cheap but
must be shadow-priced before its cost is quoted.

### Local only, no model spend

| Item | Why local | Cost |
| --- | --- | --- |
| `W1` job lifecycle | Pure code plus an RQ config change | $0 |
| `W3` gram scope (`UW-C225`) | Recompute over committed artifacts; the register already carries the expected regression counts | $0 |
| `W5` guard battery runner | Runs over the committed corpus | $0 |
| `W6` walk floor | Pure graph computation; the breaching set is already measured | $0 |
| `W7` wire `imitable` and `blind_spots` | Advisory registration plus a corpus measurement | $0 |
| `W8` CG recalibration | Run `check_skeleton.py` over the 40 JHM digraphs. Needs one web fetch, no model calls | $0 |
| `W9` register integrity | Checker code and a content-hash scheme | $0 |
| `GA-D1` hard-block ruling | Code plus **one production database query** for `summary.hard_block`. Needs Supabase authorisation, which is not OpenRouter and not available in a non-interactive session | $0 |
| New: `UW-C07` row-body vs status defect | Documentation fix | $0 |

**Nine of twelve items are free.** Everything on the current critical path except validation work is
local.

### Local to implement, small spend to validate

| Item | What needs spend | Estimate |
| --- | --- | --- |
| `W2` reading-level cap | The cap is local. Proving the `in_band` trade-off needs re-fills at two cap settings. 6 books x 2 conditions at mid-band; capped runs are *cheaper* than today's uncapped loop | **$3 to $5** |
| `W4` content-filter terminal | Classification is local. Confirming it needs probes against a known deterministic trigger, and `AL-492` names one (`the-last-cartage` plus its brief, failed 7 of 7). Probe-sized calls | **under $0.10** |

### Requires OpenRouter

| Item | Design | Estimate |
| --- | --- | --- |
| `W10` model-selection settling experiment | 3 legs x 12 replicates x 2 counterbalanced cells = 72 shells. Skeleton authoring is far cheaper than filling: the register budgets cheap cells at 5-20k tokens per shell and the hard cell at 100-350k. A validator costed this at **under $5**; allow headroom if a frontier leg runs at list price rather than as a subagent | **$5 to $15** |
| `GA-D2` cross-family reuse lever | **Now the expensive one.** Owner rulings 1 and 6 exclude both the differentiation directive and per-request mutation, so there is no surviving candidate lever and any replacement needs measuring from scratch. Budget on the Run A pattern (a book pair per arm at $0.72): roughly 4 candidate levers x 3 pairs x 2 books = 24 books | **$10 to $25** |
| Cross-vendor convergence follow-up (section 1.6 of the reconciliation) | Shells from 3 or more vendors to confirm the 7-of-342 TAU_CELL breaches replicate. About 30 shells, authoring not filling | **$3 to $6** |
| Path-level safety, **if adopted** | Measured at 271 covering paths on the 677-node book, 100% edge coverage in 1.22s. About **$0.46 per book batched on Haiku**, $2.77 on Sonnet 4.6. A 20-book validation pass | **$9** (validation), then $0.46 per book ongoing |

### Total

- **Immediate remediation (the whole P0 and P1 list): $0.** Every ruled and code-level item is local.
- **Validating `W2` and `W4`: under $6.**
- **All open experiments together: $27 to $55**, dominated by `GA-D2`.

For scale, the entire live structural round that produced the decision-grade directive result cost
**$3.28**. Spend is not the constraint on this programme; engineering time and owner decisions are.

**One caveat on every estimate.** There is still no runtime per-book spend cap (`C5-2`, the only
`_MAX_COST_USD` is a $999,999.99 Decimal overflow clamp), so a pathological run cannot be bounded by
the system. Until `W1` and a spend ceiling ship, every figure above depends on the stop-rule
discipline the live round used manually, which worked: $3.28 measured against a $5.70 stop.

## Related

- [Handoff](./cyo-brief-remediation-handoff-2026-08-22.md) for a team planning this work
- [Gap analysis](./cyo-brief-gap-analysis-2026-08-22.md), the findings these plans address
- [Evidence](./evidence/brief-gap-analysis-2026-08-22/README.md), all 24 raw reports
- [2026-08-22 research brief](./cyo-generation-research-brief-2026-08-22.md), the subject
- [Unscheduled work register](./unscheduled-work-register.md) and
  [authoring lessons log](./authoring-lessons-log.md), where the draft rows land
