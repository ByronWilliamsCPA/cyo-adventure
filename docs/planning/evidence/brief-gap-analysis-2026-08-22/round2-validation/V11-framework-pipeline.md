# V11. Adversarial validation: framework coherence and pipeline seams

> **Reproducibility notice, 2026-08-30.** Figures in this report were computed by harnesses that
> were never committed, and it cites paths that do not exist in this repository: `/home/user/cyo-adventure`, `/home/user/cyo-adventure/.worktrees/brief-evidence`, `/home/user/cyo-adventure/.worktrees/brief-evidence/scripts/modal_kimi_leg.py`.
> **Treat every number that rests on them as unreproducible from this branch**, and re-derive
> before citing. This is the same failure mode `AL-510` and `UW-C317` record, and that this
> evidence set criticises elsewhere, so it is disclosed rather than left implicit.

**Remit**: refute-first validation of ten claims from `B1-framework-coherence.md` and
`B2-pipeline-architecture.md`, plus a set-level review of synthesis section 8.
**Trees**: `/home/user/cyo-adventure` (branch `claude/cyo-brief-analysis-jys942`, HEAD `7337b23`) and
`/home/user/cyo-adventure/.worktrees/brief-evidence` (detached `6fc2b34`).
**Date**: 2026-08-22.

## 0. Tree identity: independently confirmed

B2 asserts `src/` is byte-identical across trees; several findings depend on it. Verified
independently, not taken on trust:

```
diff -rq src/ .worktrees/brief-evidence/src/ -x '__pycache__'   -> no output
239 .py files on each tree
sha256 over sorted per-file sha256 (path-normalised):
  ee8f7829f8ac95e127055ada40ad3058b6207b2f5f5ce74a7b48aa4e20602d0e  (this tree)
  ee8f7829f8ac95e127055ada40ad3058b6207b2f5f5ce74a7b48aa4e20602d0e  (evidence tree)
```

**Confirmed.** Every claim below marked "(a) identical on both trees" is safe on that point. What
differs between trees is `scripts/` (two files only: `compare_skeleton_authors.py`,
`modal_kimi_leg.py`) and `docs/planning/`. That two-file scripts delta is exactly where claim 2 dies.

---

## Claim 1 (B1-1): F5 has no pipeline mechanism; `choice_semantics` appears nowhere in `src/`

**Verdict: CONFIRMED on the load-bearing half, PARTLY REFUTED on the literal wording.**

The literal search claim is over-stated. `choice_semantics` appears in **three committed scripts on
both trees**, which B1 missed:

- `scripts/check_promise_discharge.py:42,153,202`
- `scripts/check_narrative_contract.py:383`
- `scripts/build_prose_review_worklist.py:115`

So "appears nowhere in `src/` on either tree" is exactly true (`grep -rn choice_semantics --include='*.py' src/` = 0
hits) but "appears nowhere" is not. The distinction matters, because one of those three
(`check_promise_discharge`) **is** registered as a gating guard: `scripts/run_guard_battery.py:133-135`,
`gating=True`.

The claim survives anyway, because of where that guard lives. `run_guard_battery.py` is a manual
CLI ("Usage: uv run python scripts/run_guard_battery.py <skeleton.json> <contract.json>
<filled.json>..."), and I could find no caller:

```
grep -rn 'run_guard_battery\|check_promise_discharge' .github/ .pre-commit-config.yaml noxfile.py  -> nothing
grep -rn 'run_guard_battery' src/                                                                  -> nothing
```

It is invoked by an author, by hand, at authoring time. It is not in CI, not in `src/`, not in the
request path. And the `choice_semantics` it reads comes from a **catalog-time `.contract.json`
sidecar**, i.e. authored once per skeleton, which is the opposite of F5's actual prescription
("generate `choice_semantics`, beats, devices, and stakes **per book**"). So the one place the
decisional layer is represented in code represents it as a *shared* artefact, which is the failure
mode F5 exists to prevent.

**Recalibrated statement**: F5's decisional-layer stratum exists as a data format and one manual
authoring-time guard, and as nothing at request time. The only request-time differentiation lever
is `build_differentiation_directive` (`generation/prompts.py:480`, wired at `worker.py:853`), whose
effect §4.1 itself records as unmeasured (`AL-498`). B1-1's conclusion stands; its evidence
statement should be narrowed to "nowhere in `src/`; only in catalog-time authoring scripts driven
by hand".

---

## Claim 2 (B2-23): F3's tool-assisted regime "exists as CODE nowhere"

**Verdict: REFUTED.** This was the claim I was asked to attack hardest, and it does not survive.

### The code exists, on the source branch, with a CLI flag

`/home/user/cyo-adventure/.worktrees/brief-evidence/scripts/modal_kimi_leg.py`:

| Locus | What it is |
|---|---|
| `:261` | `_TOOLS_CHECKER_CAP = 10`, the brief's "ten-invocation cap", as a constant |
| `:272-297` | `_full_check()`, runs `check_skeleton.py --strict --allow-mvp` with the cell's band/length/style, returns **full untruncated** stdout ("the blind path's 120-line truncation stays blind-only") |
| `:300-338` | `_complete_messages()`, streamed completion over an explicit **persistent** message history |
| `:341-412` | `run_grid_point_tools()`, the loop: author → parse → run checker → feed verbatim output back → iterate, capped at 10 checker runs and 12 LLM calls, breaking on pass |
| `:418` | `--mode` with `choices=["blind", "tools"]` |
| `:454-457` | dispatch: `if args.mode == "tools": run_grid_point_tools(...)` |

That is a bounded agentic loop with an invocation cap and per-round state, precisely what B2-23's
own recommendation asks someone to build ("give the author model a `check_skeleton --strict` tool
with an invocation cap and per-round state, so the §4.2 condition is a code path"). It already is
one, for every API leg: Kimi-K3 on the owner Modal endpoint, deepseek-v4-pro (Modal and OpenRouter
presets), deepseek-v4-flash (`_PRESETS`, `:52-70`).

B2-23 cited `compare_skeleton_authors.py` only and concluded from its `emit-prompts`/`score-shell`
docstrings that the whole regime was manual. It named `modal_kimi_leg.py` in B2-0 as a file that
exists, then never opened it.

### "Cannot be run reproducibly or at scale": tested specifically, and false

The synthesis's stronger phrasing fails on three counts:

1. **Reproducibly.** `uv run python scripts/modal_kimi_leg.py --endpoint kimi --mode tools --cell A
   --replicates 3 --prompts <dir> --out-dir <dir>` is a single deterministic command. Prompts come
   from `compare_skeleton_authors.py --emit-prompts`, briefs are generated at run time from
   `generate_drafting_brief.build_brief`, premises are allocated from the frozen S-0 file.
2. **At scale.** The loop is unattended and per-grid-point; scale is a `--replicates` integer and
   provider credit.
3. **Verifiably.** I cross-checked all 42 tool-condition grid points in
   `runs/e1r3-tools-2026-08-21/`: the hand-maintained `tools-meta.json` `reported` value agrees
   with the harness's own deterministic `--score-shell` `strict_pass` in **42 of 42** cases, zero
   mismatches. The pass/fail column of §4.2 is machine-scored, not self-reported.

I also reproduced the brief's arithmetic from the records: cell A 12/21, cell D 15/21, per-leg
counts and checker-run ranges all match the §4.2 table exactly. Blind arm: 2/21 confirmed from
`runs/e1r3-2026-08-21/`.

### What is genuinely true, and is a smaller finding

- **The winning legs were driven by hand.** The four `claude-*-subagent` legs (fable and opus at
  3/3 in both cells) ran through `--emit-prompts` / `--score-shell` with a human or session agent
  relaying feedback. There is no committed run book for that procedure, no skill, no script, no
  section of the test plan describing the subagent tools protocol step by step.
- **`--mode tools` is not in the main harness.** It lives only in the API-leg driver.
  `compare_skeleton_authors.py` has no tools mode. **The project already knows this**: `UW-C320`
  says in as many words "add a labeled tool-assisted condition to `compare_skeleton_authors.py`'s
  subagent driver", status `unscheduled`. B2-23 issued that recommendation without noticing it is
  an existing tracked row.
- **It is a forced-critic loop, not native tool use.** The model does not emit tool calls and does
  not decide when to check; the driver checks every parseable draft. F3's slogan ("Structure
  authoring is tool-use, not text generation") over-describes what the API legs did. For the
  subagent legs it is accurate, because those agents did hold the tool.

### The mis-attribution that caused the confusion, and a brief defect nobody caught

B2-23 says the regime lives in "the `cyo-author` skill plus a human driver". I read
`.claude/skills/cyo-author/SKILL.md` in full. **It is a fill skill, not a skeleton-authoring
skill.** Step 1: *"It is already a valid story graph; you only write prose. Never change `id`,
`choices[].target`, `start_node`, node ids… Changing structure is a bug."* It cannot author a
skeleton and never claims to.

This is not B2's error alone. The brief propagates it:

- `docs/planning/cyo-generation-research-brief-2026-08-22.md:110-112`, *"Today skeletons are
  authored in tool-assisted LLM sessions (the `cyo-author` skill mechanism): the author drafts the
  full graph with `<<FILL>>` directives and runs the strict checker against its own draft until it
  passes."* The named skill does the opposite: it consumes a graph that already has the directives.
- `docs/planning/authoring-lessons-log.md:592` (`AL-513`), *"The production authoring mechanism
  (cyo-author skill sessions) authors WITH checker access"*. Same error, and it is the stated
  justification for adding the tools condition.

**New finding V11-N1 (medium)**: §3.1 and `AL-513` both attribute skeleton authoring to a skill
whose own contract forbids structural change. The real skeleton-authoring procedure is undocumented
ad-hoc session practice. Fix §3.1 and `AL-513`, or write the run book the brief claims exists.

**Verdict summary**: option (c) in the task's framing, implemented in the S-1 harness on the source
branch, for every API leg, with a real cap, real persistence and machine scoring. Option (b) for
the four Anthropic subagent legs, and there the workflow is legitimate but undocumented. Option (a),
"genuinely unimplemented", is false. **B2-23 should be withdrawn and replaced** by two narrower
findings: the undocumented subagent protocol, and V11-N1's skill mis-attribution.

### A better finding sits in the same place, which everyone missed

**New finding V11-N2 (high)**: the tools arm's pre-registered primary endpoint is structurally
uncomputable, and the headline is an exploratory column.

`runs/e1r3-tools-2026-08-21/summary.md` reads, verbatim:

```
Primary endpoint (S-1): between-leg statistic 0.000, p = 1.0000 (10000 permutations, seed 20260821).
Everything below is exploratory.
| leg | ... | mean repair rounds | output tokens | ... |
| claude-fable-subagent | 6 | 0 | 6 | 6 | 0.00 | 0 | 0.066 |
```

`mean repair rounds 0.00` and `output tokens 0` for **every leg**, because `--score-shell` records
only the final draft (`attempts == 1` in all 42 records). The pre-registered endpoint, repair
rounds to strict pass, permutation test, cannot exist in this condition. Every number in §4.2's
tools table therefore comes from the exploratory strict-pass column plus a **hand-maintained**
`tools-meta.json` for the checker-run counts. Pass/fail is machine-verified (I checked); the
checker-run counts are not independently reproducible from harness output.

Compounding it: **there is no blind cell D**. `runs/e1r3-2026-08-21/records/` contains 21 cell-A
records and zero cell-D records. F3's sentence, *"the same models with permission to run the
validator themselves passed 12 of 21 at ages 5-8 and 15 of 21 at ages 10-13"*, reads as two
contrasts against the 2/21 blind baseline. Only the first has one. The 15/21 figure has **no
control arm at all**, and it is the figure the brief uses to argue "the hard band is not the hard
part once the regime is right".

The register (`diversity-test-register.md:1292`) does disclose the endpoint substitution honestly
("the blind primary endpoint is superseded by censoring… the decision-bearing results are the
tool-assisted pass counts") and declares the tools condition as an owner-directed pre-run addition.
So this is a disclosure gap in the *brief*, not fabrication in the register. But an F6 framework
that says "pre-register everything" is being carried by a headline whose pre-registered endpoint
returned p=1.0 and whose decision-bearing endpoint was declared after first data contact, against a
control that exists for one of two cells.

---

## Claim 3 (B2-1): `queued->running` never committed; sweep 2 dead; story_requests omits `rq_job_id`

**Verdict: CONFIRMED**, including the concurrency consequence. One sub-claim needs softening.

### Verified mechanics

- `src/cyo_adventure/generation/worker.py:1751-1752`: `job_row.status = "running"` then
  `await session.flush()`. No commit.
- `worker.py:2455`: the only happy-path `session.commit()`, after the whole pipeline.
- `queue.py:233-268` (sweep 2) selects `GenerationJob.status == "running"`. No committed `"running"`
  row can exist on the production path, so it never matches. Its own docstring describes rows
  *"hard-killed… after committing the `queued -> running` transition"*, a commit that does not
  happen.
- `queue.py:218-232` (sweep 1) selects `status == "queued"` older than `DEFAULT_STALE_AFTER`
  (`queue.py:56` = 30 min) and re-enqueues. A live job's row is *visibly* `"queued"` with a stale
  `updated_at` (the flush is invisible to other sessions), so a healthy long-running job is
  sweep-1-eligible.
- `core/config.py:404`: `generation_job_timeout_seconds = 1800` = exactly 30 minutes. Queued-stale
  window equals job timeout, confirmed.
- `api/story_requests.py:107`: `enqueue_generation(job_id, settings)`, **no `rq_job_id`**, so
  `unique=rq_job_id is not None` (`queue.py`, the `queue.enqueue(...)` call) evaluates False.
  `api/generation.py:181` does pass it. Two enqueue paths, one unguarded, and the unguarded one is
  the family-initiated story-request flow.

### The false comment is worse than the bug

`worker.py:1737-1740`, inside the claim guard:

> *"Concurrent (not merely sequential) redelivery is additionally prevented upstream: **every**
> enqueue path now shares one RQ identity with unique=True (see api/generation.py::_enqueue_safely
> and generation/queue.py::enqueue_generation), so RQ never admits two jobs for one row in the first
> place."*

`queue.py`'s own `#CRITICAL` block repeats it: *"A caller that passes `rq_job_id=None` (none in
production today) opts out."* There is one in production today, at `api/story_requests.py:107`.
Both comments assert an invariant that the family path violates, which is why the defect has
survived: a reader auditing the claim guard is told upstream already handles it.

### Exact triggering sequence (family-initiated book)

1. Guardian request approved → `POST` handler creates `GenerationJob(status="queued")`, commits,
   background-tasks `_enqueue_safely` → `enqueue_generation(job_id, settings)` with `unique=False`.
   RQ assigns a random job id.
2. Worker W1 picks it up, `_load_and_start_job` reads `status == "queued"`, sets `"running"`,
   flushes. **Not committed.** `updated_at` is unchanged as far as any other session can see.
3. Fill runs long (a large chunked book, or an Ollama leg) and passes minute 30.
4. Any worker process starts, deploy, scale-out, OOM restart, and runs `requeue_stranded_jobs()`.
   Sweep 1 selects the row (`status == "queued"`, `updated_at < now - 30min`) and calls
   `enqueue_generation(row_id, settings, rq_job_id=row_id)`. The original carries a *different*
   random RQ id, so no `DuplicateJobError` is raised. A second RQ job is admitted.
5. Worker W2 runs `_load_and_start_job`, reads `status == "queued"` from a fresh session (W1's claim
   is uncommitted), passes the guard at `worker.py:1743`, and starts a second paid fill.
6. Both reach `persist_storybook` with `story_id = f"s_{job_id}"` → primary-key collision; the
   loser's outcome is discarded after being paid for, and the cost record (one row, two runs) is
   corrupt.

Step 5 remains **inferred** at the isolation level, as B2 flagged: under READ COMMITTED, W2's own
`UPDATE` blocks on W1's row lock until W1 commits, then overwrites the terminal status back to
`"running"`. The read that admits W2 is not inferred, it is what an uncommitted flush means.

### Demonstration available without a live provider

`tests/integration/test_queue_reclaim.py:147` constructs `GenerationJob(concept_id=..., status="running")`
**by hand**. Every `"running"` row in the whole test suite is a hand-built fixture
(`test_series_link.py:740,835`, `test_worker.py:1131`, `test_generation_api_unit.py:642`). No test
anywhere produces a committed `"running"` row through the worker's own path, which is exactly what
you would expect if that state is unreachable. Sweep 2 is tested only against a state production
cannot create, a green test over dead code.

### Softening

B2 wrote *"even with the id, RQ uniqueness cannot collide with a job that has already left the
queue and is executing."* That is probably wrong for rq ≥ 2.10 (`pyproject.toml:77`): an executing
job's hash persists in the StartedJobRegistry, so a `unique=True` enqueue during execution is likely
to raise `DuplicateJobError` and no-op. If so, `api/generation.py`'s path is protected and the
exposure is **specific to `api/story_requests.py:107`**, the family path, not general. That makes
the finding narrower and the fix even cheaper, not less serious.

---

## Claim 4 (B2-2): transient review failure destroys a completed paid fill; no retry, no dead-letter

**Verdict: CONFIRMED, fully.**

- `worker.py:1663-1700`: `except Exception` around `run_moderation_pipeline` / `embed_series_block`
  → `await session.rollback()` → re-fetch row → `_record_failure(...)` → `raise`. The rollback
  discards the persisted (paid-for) storybook version. The comment is explicit that this is
  deliberate: *"Roll back the unreviewed storybook persist first: the per-job story_id (`f"s_{job_id}"`)
  would otherwise collide **on an RQ retry of this same job**."*
- **There is no RQ retry.** `queue.py`'s `queue.enqueue(...)` passes
  `_WORKER_ENTRYPOINT, job_id, job_timeout=..., job_id=..., unique=...` and nothing else.
  `grep -n 'Retry\|retry=' src/cyo_adventure/generation/queue.py` → no hits. The rollback's stated
  justification is a mechanism that does not exist.
- **No dead-letter, no re-drive route.** No retry endpoint exists on `api/generation.py`,
  `api/approval.py`, or `api/rescreen.py`. `api/rescreen.py:11-26` documents at length why it is
  sync-only and explicitly declines to build job re-drive plumbing ("Building that plumbing… is a
  second feature, not a clean reuse").

Triggering sequence: fill completes and is billed → `persist_storybook` writes the version →
review backend returns a 503 / times out / 401s on a rotated key → `ProviderError` propagates →
rollback → row `"failed"`, `error` = the truncated exception → RQ marks the job failed → nothing
re-enqueues it. The guardian sees a failed request. The only recovery is a fresh request, which
pays for the whole fill again.

The combination with claim 3 is the real hazard: the *one* transition that would make this
recoverable (a durable `"running"` claim plus a real `retry=Retry(max=N)`) is the same transition
claim 3 shows is never committed.

---

## Claim 5 (B2-5): all fill-stage evidence ran `stage1_gate="skipped"`, unbound and undirected

**Verdict: CONFIRMED on the gate; NARROWED on "undirected"; CONFIRMED on "unbound". The
"measures a pipeline section 3 does not describe" framing is over-stated.**

Which runs, exactly:

- `scripts/compare_vendors.py:942` hardcodes `stage1_gate="skipped"` at the sole `fill_skeleton`
  call. Every book in `docs/planning/vendor-comparison/runs/**`, the entire §4.1 evidence base,
  including the DeepSeek V4 Pro live fill, was produced ungated.
- `scripts/measure_sentinel_survival.py:274`, same, so the sentinel-survival evidence too.
- Production is gated: `generation/worker.py` passes `settings` at both call sites and
  `orchestrator.py:1384` resolves posture `auto` → armed.

Three things stop this from invalidating the fill-stage conclusions:

1. **It is declared, in advance, in the run plan.** `deepseek-v4-pro-live-fill-plan-2026-08-20.md`
   section 2, under the heading *"Explicitly out of scope, and why"*: *"The Stage 1 fidelity gate
   does not run… So this run measures the deterministic gate, not the fidelity gate."* Carried again
   as open item F5 at `:631`.
2. **It is stamped in the data.** `orchestrator.py:603` writes `report["stage1_gate"]` =
   `"armed"`/`"skipped"` on every outcome. This exists *because* of `AL-324`, the lesson recording
   the exact failure B2-5 is describing (three Sonnet 5 books recorded `status='passed'` with every
   `<<FILL>>` directive intact). The posture argument and the stamp are the applied fix.
3. **"Undirected" is a run condition, not a harness limit.** `compare_vendors.py:508-601` loads and
   renders per-brief differentiation directives via `build_differentiation_directive` and passes
   them at `:943-945`. The 96.3 shared-4-grams-per-1000 result is explicitly the *no-directive* arm,
   and §4.1 says so.

"Unbound" is real: no `bind_theme` / slot-binding anywhere in `compare_vendors.py`.

**Recalibrated statement**: the fill-stage model ranking was measured on a path that omits the
Stage-1 fidelity gate and theme binding, both declared. It therefore **narrows** rather than
invalidates: the ranking is valid for raw prose idiom under a deterministic gate, and does not
transfer without argument to the production path, where a fidelity gate can reject and a bound theme
constrains the prose. The one conclusion that should carry a caveat is the delivery-floor finding,
the fill-rate hole (38.9-52.9%) was discovered on the ungated path, which is precisely the path where
an undelivered fill is invisible.

---

## Claim 6 (B2-9): review queue: no limit, no order, no claim, full blobs, `needs_revision` invisible

**Verdict: SPLIT. Three sub-claims confirmed, two refuted.**

`api/approval.py:394-520`, `get_review_queue`:

| Sub-claim | Verdict | Evidence |
|---|---|---|
| No `limit` | **Confirmed** | `select(Storybook).where(Storybook.status == _IN_REVIEW)`, unbounded |
| No `order_by` | **Confirmed** | same statement; ordering is DB-arbitrary |
| No claim / lease | **Confirmed** | nothing marks a row as being worked; two admins can open the same book. (The `FOR UPDATE` lock at `_load_admin_story` is a write-time race guard, not a queue lease) |
| "full blobs" | **REFUTED for the response** | `ReviewQueueItem` (`api/schemas.py:2006-2031`) is a compact projection: `storybook_id, title, status, version, screened, flagged_count, summary, age_band, waiting_since, themes, content_flags`. No blob. Server-side it *does* load whole `StorybookVersion` rows including the blob JSON, so the memory cost is real; the payload cost is not |
| "`needs_revision` is invisible" | **REFUTED** | `GET /api/v1/admin/storybooks?status=needs_revision` (`api/approval.py:711-745`) is admin-only, cross-family, "Newest activity… first", and its docstring names `needs_revision` explicitly as a status an admin re-opens through it |

The queue also already carries `waiting_since` as a documented triage field (UX-A3), so ordering is
achievable client-side today. The finding should be restated as: *the review queue has no server-side
bound, order or lease, which is an O(n) surface that degrades with catalog size*, dropping the blob
and `needs_revision` assertions, both of which are wrong.

---

## Claim 7 (B2-10): the flywheel is scheduled by nothing; an empty cell 422s with no demand event

**Verdict: CONFIRMED.**

`scripts/flywheel_cycle.py:2-29` calls itself *"WS-8 scheduled cadence runner"* and *"a scheduled
(weekly) run"*, then states the mechanism: *"a typical invocation is an operator cron or a scheduled
job"*, with a sample crontab line **in a comment** (`# crontab: Mondays 09:00 UTC, dry-run report
only`). Searching the repo for anything that would run it:

```
grep -rln 'flywheel' .github/workflows/   ->  skeleton-promotion.yml  (a PR gate, not the cycle)
grep -rn 'flywheel' src/cyo_adventure/api/ src/cyo_adventure/generation/  ->  comments only
```

There is no workflow, no scheduler entry, no systemd unit, no Routine. The catalog-growth loop's
schedule exists as documentation of a crontab line someone would have to install by hand. Combined
with B2-22's confirmed structural boundary (the flywheel reaches production through nothing), the
catalog is grown by a loop that nothing starts.

The empty-cell path is confirmed at `generation/skeleton_match.py:64`: *"nothing (returns an empty
list, surfaced by the caller as a 422, not a…)"*, the demand signal that should feed the flywheel's
saturation reading is discarded as an HTTP error.

---

## Claim 8 (B1-5): no F1-F8 principle concerns the reader; the predecessor's banner was dropped

**Verdict: CONFIRMED, and stronger than B1 stated.**

The 2026-08-10 brief carries the disclosure four times, including as a top-of-document banner:

- `:31-32`, *"the judgments reported here, in all four parts, were produced by **LLM agent
  instances**. **No human and no child has read or rated any generated book.**"*
- `:2162`, *"No human and no child has read any of it."*
- `:2461`, *"No human and no child has read any of these books either."*
- `:2811`, `:2834`, a risk table row: *"No human or child has read a single generated book |
  evaluation validity | unknown, and that is the point"*

The 2026-08-22 brief carries none of it. Within F1-F8, `child` appears once (F8, *"a book a child
can see"*, the child as an object of approval, not a reader) and `reader` appears once outside F8,
in F6's *"ranked book pairs opposite to readers (D-3)"*.

**That second occurrence is the sharper finding.** The "readers" whose orderings D-3/D-4 are
validated against are themselves LLM raters, the register describes D-1/D-3 as *"2 raters"*,
*"3 annotators"*, and the sourcing test plan states *"raters are session subagents (free)"*. So
F6, *"trust no instrument until it survives a known-answer test"*, supplies its known answers
from an unvalidated LLM panel. D-4/solution transfer is described in §4.4 as *"the only computed
measure that reproduced reader orderings"*; what it reproduced is another model's orderings.

**New finding V11-N3 (high)**: dropping the banner while continuing to use "readers" as the
validation ground truth converts a disclosed limitation into an undisclosed circularity. The
2026-08-22 brief should restore the banner verbatim and, wherever "readers" means LLM raters, say
so: F6's own principle demands it of everyone else's instruments.

---

## Claim 9 (B1-11 / C5-7): the shipped config inverts the 4.2 recipe

**Verdict: SUBSTANTIALLY WEAKENED. The `review_provider=mock` half is a category error.**

The defaults are as claimed (`src/cyo_adventure/core/config.py`):

- `:459` `openrouter_model = "anthropic/claude-haiku-4.5"` (fill)
- `:460` `openrouter_fallback_model = "anthropic/claude-sonnet-4.6"`
- `:490` `anthropic_model = "claude-sonnet-4-6"`
- `:611` `review_provider = "mock"`; `:612` `review_openrouter_model = "anthropic/claude-sonnet-4.6"`

But `review_provider="mock"` cannot reach any non-local deployment:

- `config.py:1769-1785`, `_require_real_reviewer_outside_local`: raises `ConfigurationError` when
  `review_provider == "mock"` and `environment != "local"` and `not allow_mock_review`. The process
  refuses to boot.
- `config.py:658-667`: the escape hatch `allow_mock_review` exists, is `False` by default, and
  setting it *also* stamps `reviewer_independent=false` plus a structural advisory finding on every
  report it produces, "so a mock-moderated report stays self-identifying forever".
- `.env.staging.example:24-32` leaves the hatch **deliberately commented out**, with a paragraph
  explaining why: *"Setting the hatch here would boot a SERVING process with mock moderation against
  the staging database, which is exactly the condition that produced the original flood of
  structural fail-safe flags."* It is documented as a per-command flag for seed scripts only.

That is careful, layered design, not a shipped inversion. Similarly, `.env.staging.example:125` pins
`CYO_ADVENTURE_GENERATION_PROVIDER=ollama`, *"stays unbilled on staging… so test runs place no
billed LLM calls"*, so the OpenRouter fill default is not staging's fill model either.

**What is actually true, and is a better finding.** `docker-compose.prod.yml` sets **no** model or
provider environment variable at all (`grep -n 'MODEL\|PROVIDER'` → nothing), and no file in the
repo encodes §4.2's recipe. Per-request model selection does exist:
`story_requests/authoring_plan.py` carries `mechanism` (`skill` / `automated_provider`), `provider`,
`model`, and `prep_model`, validated against the provider allowlist, but `GenerationJob` has one
`model` and one `provider` per row, and the review model is a **global** setting
(`review_openrouter_model`), not per-request.

**Recalibrated statement**: the recipe "fill with V4 Pro, review first-pass with V4 Flash" has no
configuration home. Fill model is per-job and admin-chosen; review model is global; skeleton
authoring has no model field because it is not a service. F4's own §4.2 sentence concedes it
("per-stage model selection in the authoring plan is the enabling change"). The defect is a missing
mechanism, not an inverted setting, and the `review_provider` half of the claim should be dropped,
it accuses a genuinely well-built safety guard of being the hazard it prevents.

---

## Claim 10 (B2-19 / B2-13): selection is random-with-replacement not LRU; 44% of shells lack a theme contract

**Verdict: B2-13 CONFIRMED exactly. B2-19 REFUTED as described, and the true behaviour is worse
than either B2 or the brief says.**

### B2-13: confirmed

```
find skeletons -name '*.json' | by suffix:  84 PLAIN, 47 contract, 16 lineage, 2 narrative
```

84 shells, 47 `.contract.json` sidecars = 56% coverage, **44% with no theme contract**. Exact.

### B2-19: the mechanism is not random-with-replacement

`generation/skeleton_match.py`:

- `:552-564` `_weight(recent_count) = 1 / (1 + recent_count)`, inverse-frequency, *"strictly
  decreasing but never zero… nothing is ever fully excluded"* (decision C-4).
- `:577-594` `_blended_weight(recent, similar) = 1 / (1 + recent + 3*similar)`, adds a theme-reuse
  penalty.
- `:600-670` `select_skeleton_for_cell`, weighted-random over those weights, with an injected
  `random.Random` for determinism in tests.

So it is a *soft* LRU: recency-weighted, never-excluding. B2-19's "random with replacement" is
wrong (uniform it is not), and §3.3's *"picks with recency weighting so a family sees the least
recently used armature"* is also wrong (it does not guarantee LRU).

### Quantifying the gap: the finding both sides missed

Monte Carlo over the actual weight function (200k trials per cell depth, `1/(1+n)` weights, k draws
from a k-shell cell):

| Shells in cell | Expected distinct armatures after k requests | P(a repeat within the first k requests) |
|---|---|---|
| 3 | 2.37 of 3 | 60.1% |
| 4 | 3.09 of 4 | **77.0%** |
| 5 | 3.82 of 5 | 87.1% |
| 6 | 4.54 of 6 | 93.1% |
| with strict LRU | k of k | 0% |

**New finding V11-N4 (high)**: §4.3's capital fact, *"a child exhausts a cell by roughly the fourth
request at 3-4 skeletons per cell (Q-1), so full-skeleton reuse is bounded by depth against demand"*,
**overstates the catalog's effective depth**. At 4 shells per cell, a family has a 77% chance of
being handed a repeated armature *before* exhausting the cell, and sees only 3.09 distinct armatures
in its first four books. The depth bound is not 4; it is closer to 3. The fix is one function:
strict LRU (or LRU with a tie-break) instead of never-zero inverse-frequency weighting. Decision C-4
chose the never-zero floor deliberately, so this needs an owner call, not a silent change, but the
brief should not be quoting a depth the selector does not deliver, and this makes the diversity
problem the whole programme is chasing measurably harder than stated.

---

## What everyone missed: framework-level gaps in neither the brief nor B1/B2

Beyond V11-N1 through V11-N4 above:

**V11-N5 (high), no principle covers series or continuity across books.** F1-F8 are all
single-book properties. Yet the codebase has `_series_chain_docs`, `validate_series`, SR-1/SR-2
contiguity gates, `embed_series_block`, a grandfather rule for pre-WS-G chains, and a
`characters/progression.py` persistent-character system with a CH-1..CH-8 validator envelope
(ADR-028). The hardest continuity problem in the product, a returning reader whose character state
must be consistent across books authored months apart by different models, is governed by no
principle at all. F5 ("never reuse decisions") is stated for sibling books in a cell; it says
nothing about a *sequel*, where reusing decisions is the point. The framework and the code disagree
about whether a book is the unit.

**V11-N6 (high), latency is not a product property anywhere in F1-F8.** The framework optimises
quality and cost. Nothing addresses the interval between a child asking for a book and a child being
able to read one, and the architecture makes it long by construction: staged fill, then a
deterministic gate, then a moderation pipeline, then a **human approval that may take days** (F8),
across a queue with a 1800s job timeout and no server-side ordering (claim 6). For a reading app for
kids, "your book will be ready when an adult reviews it" is the dominant UX fact, and it is absent
from the principles, from §3, and from every reviewer's findings. Latency also interacts with claim
4: a failed fill costs the child the whole wait, not just the money.

**V11-N7 (medium-high), catalog cold-start is unaddressed.** Q-1 says a child exhausts a cell by
the fourth request (V11-N4: sooner). A *new family* in a cell with 4 shells hits the reuse floor
within a month. The flywheel that would grow that cell is scheduled by nothing (claim 7) and its
demand signal is thrown away as a 422 (claim 7). There is no principle, and no code, covering the
regime where demand for a cell exceeds catalog depth, which is the ordinary steady state, not an
edge case.

**V11-N8 (medium-high), nothing describes what a family experiences when generation fails
repeatedly.** Claim 4 establishes a transient review error consumes a paid fill with no retry.
There is no backoff, no cap on consecutive failures, no notification path, no degraded mode. A
family whose review backend is having a bad afternoon gets N failed requests, each of which
consumed the per-family active-job cap slot (`MAX_ACTIVE_JOBS_PER_FAMILY`, which counts `queued`
and `running`) until a sweep that cannot see `running` rows clears it. The failure envelope is
undefined at exactly the seam most likely to fail.

**V11-N9 (medium), no principle covers deprecation of a pinned model.** The entire evidence base is
model-pinned by construction: §4.1's legs are "backend-pinned with fallbacks disabled", §4.2's grid
is per-model, F4 mandates per-stage model selection, and `generation/allowlist.py` plus the
provider-allowlist admin surface pin provider/model pairs. Every one of DeepSeek V4 Pro, V4 Flash,
Kimi-K3, Haiku 4.5 and Sonnet 4.6 will be retired. There is no principle stating what happens then:
whether a published book's provenance survives, whether the S-1/§4.1 rankings must be re-run,
whether a pinned model's disappearance invalidates the gate calibrations (`TAU_CELL`, the 4-gram
budget, the 3.3 generator idiom floor) that were measured on its output. F6 says pre-register
everything; nothing says re-validate when the substrate moves. Given the brief's own headline is a
model-selection recipe, the recipe has no stated shelf life.

**V11-N10 (medium), the evidence README does not describe the runs the headline rests on.**
`docs/planning/evidence/skeleton-author-vendors/README.md` documents `smoke`, `smoke2` and the
halted `e1` run. It documents **neither** `e1r3-2026-08-21` (the blind arm, 2/21) **nor**
`e1r3-tools-2026-08-21` (the tools arm, the entire §4.2 table). A reader following the brief's
"Related" pointer to that directory finds a README about three superseded runs.

---

## Recommendation review: synthesis section 8 as a set

### Sequencing errors

1. **#4 is mis-ranked and should be #1.** I verified its premise directly:
   `publishing/service.py:411-414` checks only `version_row.moderation_report is None`
   ("never screened"), then proceeds. There is **no** `has_hard_block` check anywhere in `approve()`.
   `auto_reject` (`service.py:155-177`) only fires on the `draft -> needs_revision` hop from the
   moderation pipeline, so a story that reached `in_review` by another route (the guard's own comment
   at `:406-410` names `api/approval.py::submit_storybook` as able to move a draft straight to
   `in_review` without moderation) and was later screened with a hard block sits in the queue and is
   approvable. The fix is one conditional plus one test. It has no dependency on any other item, no
   measurement prerequisite, and it closes a bypass of the product's primary safety control. Ranking
   it behind three measurement chores is the single clearest error in the list.
2. **#9 feeds #12 and is ranked five places below it.** "Produce a cost-per-book number" is the
   input to "the review economics do not close, by 4 to 28x". The owner cannot make the #12 decision
   on a range that wide. #9's first half (a cost-per-book number and a `stage` field on `TokenUsage`)
   must precede #12, not follow it.
3. **#3 conflates two different fixes and hides a blocking dependency in a subordinate clause.**
   "Pass `--strict` in `check_promotion_bundle.py`, **after fixing PL-18/PL-29 so a legal topology
   exists at 3-5 and 5-8**" is not a this-week item. `AL-514`'s PL-18 fix is a *message* improvement
   (name the first reconverging node). "So a legal topology exists at 3-5 and 5-8" is a *policy*
   change to the admissible set, a different, larger decision with catalog-wide consequences. Split
   into 3a (PL-18 message, this week, cheap, safe, and per `AL-514` the highest-yield validator fix
   on the board, three legs lost grid points to it) and 3b (topology policy + `--strict` +
   remediating 64 shells, this month, and only after 3a).
4. **#11 gates a decision nobody can execute.** "Re-score S-1 with distance-from-catalog as a
   covariate before acting on the per-stage model recipe" presumes the recipe is actionable. Per
   claim 9, there is no per-stage model configuration to act on. #11 should follow the mechanism, not
   precede it.

### Conflicts within the set

- **#7 vs #3b vs #12, the gate/economics conflict.** #7 adopts "a validator module with no gate
  caller fails the build", #3b turns on `--strict` against a catalog where 64 shells are
  non-compliant. Both increase rejection. Rejection increases regeneration, regeneration increases
  fill spend, and #12 already establishes the economics miss by 4-28x. Turning on three gate classes
  before the cost-per-book number of #9 exists means the economics decision in #12 gets made against
  numbers that are about to move. **Do #9's instrumentation first, then gates.**
- **#10 vs #12, seeding adds load to the surface that is already over budget.** Seeding known-bad
  books at 3% into the review queue adds 3% review volume to a human-review process the same list
  says does not close economically. It is also the only way to measure the control, so it must
  happen, but the rate should be set *after* #12's model decision (a guardian-primary model has a
  different reviewer population and a different seeding rate than a staff-primary one), or run
  time-boxed at 3% over a fixed window rather than as standing load.
- **#5 vs claim 3, an unnoticed hazard.** Raising `llm_timeout_seconds` above the measured fill
  distribution lengthens the window during which a healthy job's row is visibly `"queued"` with a
  stale `updated_at`. `DEFAULT_STALE_AFTER` is 30 minutes and `generation_job_timeout_seconds` is
  1800s, already equal. **Raising the timeout without raising the stale window first makes the
  claim-3 double-enqueue strictly more likely.** #5 must not ship before the missing recommendation
  below.
- **#1 vs #2, ordering is right, coupling is unstated.** #2 (reconstruct D-7b, run solution
  transfer) is analysed under whatever 4-gram scope #1 settles. Running #2 first means re-reporting
  it. They are correctly ordered but should be stated as one work item.

### Cheap-and-safe vs cheap-but-risky

| | Items |
|---|---|
| **Cheap and safe** | #4 (one conditional + test), #6 (documentation), #1 (tooling scope + restatement), #9's `stage` field, new 3a (PL-18 message) |
| **Cheap but risky** | #5 (worsens claim 3 unless sequenced), #3b (`--strict` can red-line promotion CI over 64 shells), #7's blanket build rule (will fail the build over modules that are deliberately advisory, e.g. RL-13 warnings) |
| **Expensive and safe** | #2, #8 (path-level eval), #10 |
| **Expensive and contested** | #12 (a decision, not a change), #11 |

### Re-ranked list, by (impact x certainty) / (effort x risk)

| New | Old | Item | Why moved |
|---|---|---|---|
| 1 | #4 | Refuse to publish a hard-blocked report | Verified live safety hole; one conditional; zero dependencies; highest certainty on the board |
| 2 | **new** | **Commit the `queued->running` claim; pass `rq_job_id` on the story-request path; widen the stale window** | See below, a live money leak and a blocker for #5 |
| 3 | #3a | PL-18 finding names the first reconverging node | `AL-514`: three legs lost grid points to an unactionable message; message-only, no policy change |
| 4 | #6 | Correct the brief's scale facts; add S-1 caveats | Free; and per V11-N2 the caveats needed are larger than "the register already discloses" |
| 5 | #9a | Cost-per-book number + `stage` on `TokenUsage` | Prerequisite for #12 and for judging the cost of every gate below |
| 6 | #1+#2 | Reconcile 4-gram scopes, then reconstruct D-7b and run solution transfer | One work item; can overturn the central architectural claim; free |
| 7 | #5 | Raise `llm_timeout_seconds` | Unchanged in value, now safe because #2 shipped |
| 8 | #10 | Seed known-bad books, rate set with #12 | The only measurement of the primary safety control |
| 9 | #12 | The review-economics decision | Now informed by #5's number |
| 10 | #7 | `consequence.py` to a gate; no-gate-caller build rule | After #9a, so the cost of increased rejection is visible |
| 11 | #3b | `--strict` + topology policy + 64-shell remediation | After #3a and #7 |
| 12 | #8 | Path-level evaluation via `covering_paths` | Correct but large; no dependents |
| 13 | #11 | Re-score S-1 with distance covariate | Gated on a per-stage mechanism that does not exist |

### The missing recommendation that belongs in the top five

**Commit the `queued -> running` claim in its own transaction (a conditional
`UPDATE … WHERE status='queued'` returning row count), pass `rq_job_id=job_id` at
`api/story_requests.py:107`, delete the two comments that assert an invariant the family path
violates, and set the queued-stale window strictly greater than
`generation_job_timeout_seconds + margin`.**

Why it belongs in the top five and nothing on the current list substitutes for it:

- **It is the only live money leak on the board.** Every other economics item on the list
  *measures* cost (#9), *reasons* about cost (#12), or *increases* it (#3b, #7). This one stops
  paying twice for the same book, on the family-initiated path, whenever a deploy or restart
  coincides with a long fill.
- **It is a correctness bug, not a judgement call.** The double execution ends in a
  `persist_storybook` primary-key collision on `f"s_{job_id}"` and a corrupted cost record, a
  silent data-integrity failure, verified in code, on the path every family uses.
- **It unblocks #5.** Raising `llm_timeout_seconds` without it makes the bug more frequent, so the
  list's current #5 is unsafe as written.
- **It revives a dead recovery mechanism.** Sweep 2 has never been reachable in production; the only
  tests that exercise it construct the state by hand. One durable transition makes an entire tested
  code path real.
- **Effort is ~20 lines** across `worker.py`, `queue.py`, `story_requests.py`, plus assertions in an
  existing `tests/integration/test_queue_reclaim.py`.

**Runner-up, and the strongest genuinely new finding**: replace inverse-frequency weighted selection
with strict LRU (`skeleton_match.py:552-670`). One function, and it recovers roughly one full
armature of catalog depth per cell, a 77% chance of an early repeat drops to zero. It needs an owner
call because decision C-4 chose the never-zero floor on purpose, which is the only reason it is not
the #2 item.

---

## Verdict summary

| # | Claim | Verdict |
|---|---|---|
| 1 | B1-1 F5 has no pipeline mechanism | Confirmed (evidence narrowed: `choice_semantics` is in 3 offline scripts) |
| 2 | B2-23 tool-assisted regime is code nowhere | **Refuted**: `modal_kimi_leg.py:341-412`, `--mode tools`, cap 10 |
| 3 | B2-1 uncommitted claim, dead sweep 2, missing `rq_job_id` | Confirmed (isolation step remains inferred; exposure is the family path) |
| 4 | B2-2 transient review error destroys a paid fill | Confirmed in full |
| 5 | B2-5 fill evidence ran ungated | Confirmed on the gate; narrowed, declared, stamped, and directives were supported |
| 6 | B2-9 review queue defects | Split, no limit/order/lease confirmed; "full blobs" and "`needs_revision` invisible" refuted |
| 7 | B2-10 flywheel scheduled by nothing | Confirmed |
| 8 | B1-5 no reader principle; banner dropped | Confirmed, and strengthened (the "readers" are LLM raters) |
| 9 | B1-11/C5-7 config inverts the recipe | Substantially weakened: `review_provider=mock` cannot boot outside local |
| 10 | B2-19/B2-13 selection and contract coverage | 44% confirmed exactly; "random with replacement" refuted; true behaviour is worse (77% early repeat) |

New findings: **V11-N1** (cyo-author mis-attributed as the skeleton-authoring mechanism, in the
brief and in `AL-513`), **V11-N2** (tools arm's pre-registered endpoint degenerate; no blind cell D
control), **V11-N3** (banner dropped while LLM raters are still called "readers"), **V11-N4**
(selector delivers less depth than Q-1 claims), **V11-N5** (no series/continuity principle),
**V11-N6** (latency absent from the framework), **V11-N7** (catalog cold-start), **V11-N8**
(repeated-failure envelope undefined), **V11-N9** (no model-deprecation principle), **V11-N10**
(evidence README omits the two runs the headline rests on).
