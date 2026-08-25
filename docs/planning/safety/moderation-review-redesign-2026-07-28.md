---
title: "Moderation Review Redesign: Decisions, Not Flags"
schema_type: planning
status: approved
owner: core-maintainer
purpose: "Propose the replacement review model (bounded, ranked, deduplicated decision surface), the post-Perspective Stage-0 architecture, the Stage-2 readability disposition, and the catalog remediation plan, staged for owner approval before implementation."
tags:
  - planning
  - safety
  - moderation
component: Safety-Pipeline
source: "Gap report docs/planning/safety/moderation-review-current-state-2026-07-28.md; live Supabase measurements 2026-07-28; digests of two external research reports (a Gemini Perspective API Replacement Survey and a ChatGPT deep-research report), restated inline in section 3.1 since their source files under tmp_cleanup/ are gitignored and unreachable in the repo"
---

# Moderation Review Redesign: Decisions, Not Flags

> **Status**: APPROVED by the owner 2026-07-29; all open decisions in
> section 7 are now recorded. Per-stage status against section 6's staged
> delivery plan, verified against the code: **Stage A done** (2026-07-30,
> commit `8ca8d1b3`, PR #496). **Stage B done** (schema/PASS aggregation
> PR #521, structured verdicts plus chunking PR #527, admin surfaces
> PR #528; all merged to `main` ahead of this branch, which layers the
> unusable-report approval gate, override-reason audit trail, and tiered
> queue/detail UI on top). **Stage C partial**: the baseline capture and
> the QA-corpus containment layers are done (2026-08-01, section 3.2 item 2
> and section 5). The Perspective classifier's outbound call leg is fully
> retired ahead of the 2026-12-31 sunset (section 3.2 item 5): `run_classifiers`
> no longer calls Perspective's API, and the `perspective_key` parameter is
> gone from every call site. Retirement stops at the call leg, by design: the
> `Source.PERSPECTIVE` enum member (so a historical persisted finding still
> deserializes), the `perspective_api_key` config field (retained only so an
> existing deployment does not fail to boot; see the runbook's secrets
> inventory, section 8), and explanatory comments across
> `moderation/classifiers.py`, `moderation/pipeline.py`,
> `moderation/rescreen.py`, `api/node_edit.py`, and `core/config.py` all
> remain. "The call leg is retired" and "Perspective still appears in the
> code" are therefore both true and not in tension. The Modal guard-model
> eval and its calibration report (section 3.2 item 3) have
> not started. **Stage D partial**: the re-moderate entry point and
> `scripts/remoderate_books.py` sweep script are done and on `main`; the
> 18-book sweep itself has not run (deferred, pending deploy). See the
> reviewer SOP ([reviewer-sop.md](../../operations/reviewer-sop.md)) for
> how a reviewer works the resulting surfaces day to day.
> Companion gap report:
> [moderation-review-current-state-2026-07-28.md](moderation-review-current-state-2026-07-28.md).
> Acceptance bar (owner, verbatim intent): a reviewer approving a book reads
> a bounded, ranked, deduplicated set of decisions, not one flag per node.

## 1. Design principles

1. **Fail-safe is preserved, relocated.** A reviewer that cannot answer still
   forces human review; it does so through one story-level condition, never
   N per-node findings. Structural failure is a pipeline state, not content.
2. **Everything surfaced is ranked and bounded.** Every finding that reaches
   a human carries a severity the surfaces can sort and filter on; identical
   concerns merge; the surface has a size contract.
3. **Two audiences, two contracts.** Admins get ranked detail with
   affected-node drill-down; guardians get a story-level summary sufficient
   for an approve/decline decision (ADR-005 unchanged: guardian remains the
   final gate; the pipeline never publishes).
4. **Deterministic before generative.** Signals the validator computes
   exactly (reading level, structure, budgets) are surfaced from the
   validator, not re-estimated by an LLM per node.
5. **Measured before swapped.** No Stage-0 successor ships without
   calibration against the captured raw-score baseline and an eval on a
   labeled child-story corpus.

## 2. The review model

### 2.1 Finding schema changes

Extend `moderation/report.py::Finding` (persisted JSONB is additive-safe;
readers must tolerate absent new fields on old reports):

| Field | Type | Purpose |
| --- | --- | --- |
| `severity` | `high \| medium \| low`, required on FLAG/ADVISORY | The ranking key surfaces sort on. LLM stages emit it from a rubric in the prompt; Stage-0 maps score bands to it. |
| `concern` | short slug from a fixed taxonomy (e.g. `real_world_danger`, `too_mature`, `frightening_content`, `cruelty`, `reviewer_unavailable`) | Part of the dedup/merge key (see 2.2 item 3 for the full key). Validated against `CONCERN_TAXONOMY` at construction, so an off-taxonomy value cannot form its own merge group; parse boundaries degrade to `other`. Free-text `message` remains for detail. |
| `node_ids` | `list[str]` (populated on every merged finding, including a group of one; `node_id` kept for compat and names only the FIRST covered node) | One finding can now reference every node it applies to. Readers must fan out across `node_ids` when present. |
| `structural` | `bool`, default false | Marks pipeline-condition findings (parse failure, unknown verdict, degraded classifier) so dashboards and surfaces can class them separately from content findings. |

`severity` also applies to the two Stage-0 whole-story findings
(`classifier_degraded`, `classifier_coverage_incomplete`; gap report section
2 addendum): both are `score: null` by construction, so they need a fixed
default mapping (for example, degraded -> medium, coverage-incomplete ->
high) rather than a score-derived one.

PASS is no longer persisted as rows. The report gains an aggregate block:
`{"nodes_reviewed": N, "pass_counts": {"safety": n1, ...}}`. This removes
roughly half of all stored findings (6,430 PASS rows in live data) and fixes
`summary.count` badge inflation. Audit needs are covered by the aggregate
plus the existing `moderation_completed` event counts.

`nodes_reviewed` is a coverage measurement, not a restatement of the node
count, and it is assigned past the last stage rather than beside the node
list. Once PASS rows stop being persisted it is the only signal separating
"reviewed everything and found nothing" from "never got that far": a run that
short-circuits (entry rejection, a Stage-0 bright-line block, a Stage-1 block)
keeps the 0 default, which reads correctly as no complete coverage and matches
the empty `pass_counts` beside it. #CRITICAL: data-integrity: setting it beside
the node list would persist full coverage for a story whose safety reviewer
never ran, and the aggregate is what the dashboard and flywheel read. #VERIFY:
tests/unit/test_moderation_pipeline.py::test_nodes_reviewed_zero_when_stage0_block_short_circuits
and ::test_nodes_reviewed_counts_every_node_on_a_complete_pass.

### 2.2 Stage 1 (safety) redesign

Per-node review remains the hard gate (a BLOCK must still name its node),
with three changes:

1. **Structured verdicts.** The prompt returns
   `{"verdict", "concern", "severity", "reason"}`. Unknown `concern` or
   `severity` degrades to `other`/`high` respectively; the verdict fail-safe
   mapping is unchanged.
2. **Chunked calls.** Nodes are reviewed in batches (target ~10-20 nodes per
   call, one JSON array back, per-node verdicts). A 746-node book drops from
   746 review calls to ~50 without losing per-node attribution. A batch
   whose response cannot be parsed per-node falls back to one structural
   finding for that batch (see 2.3), never to per-node fail-safe spam.
   #ASSUME: external-resources: batched verdicts may be less accurate than
   single-node calls on long nodes. #VERIFY: run both modes over the
   adversarial corpus (tests/llm_eval) and compare recall before enabling
   batching by default. **Resolved 2026-08-01 (Gate 3): the owner ran
   `scripts/adversarial_harness.py --batch-size 1 --batch-size 4
   --batch-size 8` twice against the openrouter reviewer; both runs were
   identical, with zero item-level recall regressions vs size 1 on every
   scored class and zero structural-collapse (parse-failure) findings
   (artifact: `batch-sweep-results-2026-08-01.json` in this directory).
   `review_batch_size` now defaults to 8. The E-class misses (E2/E3
   reviewer-injection) exist at the size-1 baseline and are unchanged by
   batching; they are tracked as a separate reviewer-hardening issue
   (#542), not a batching regression. Re-run the sweep after any
   reviewer-model or batch-prompt change.**
   **Read that evidence with two limits in view.** (a) *Requested 8,
   realized 6.* The corpus's largest age band holds 6 Stage-1 nodes, and a
   chunk is `min(batch_size, nodes_in_band)`, so no call in either run
   carried 8 nodes and sizes 4 and 8 were identical in 3 of the 4 bands.
   The ratified value is one step past what was measured. The harness now
   records `realized_chunk_sizes` per size so a later run cannot repeat
   this ambiguity silently. (b) *Binary scoring hid a softening.* Recall
   was scored with `is_caught` (observed max verdict >= `expected_min`), so
   `C2-aggregate-stranger-10-13` going `block` -> `flag` at sizes 4 and 8
   scored as no regression because `flag` still cleared its
   `expected_min`. The harness now reports severity downgrades and verdict
   drift separately from the pass/fail comparison.
   **Confidence limit.** Per-node verdicts are NOT stable across sizes in the
   committed artifact, and they drift in both directions:
   `A2-lost-alone-night-3-5` goes `flag` -> `block` at size 8;
   `C1-aggregate-fire-8-11` node 3 goes `flag` -> `block` at sizes 4 and 8;
   `C2-aggregate-stranger-10-13` node 2 goes `block` -> `flag` at sizes 4 and 8.
   Class-level recall stays flat only because each drifted verdict still clears
   its expected rank floor. With 13 corpus items, 6 of them scored, one sweep
   per size, and visible reviewer nondeterminism, this evidence supports
   "no recall regression was observed" and does NOT support "batching is
   recall-neutral". Only one artifact is committed; the second run agreed but
   was not retained, so the agreement is an unverifiable claim rather than
   evidence. Treat re-running the sweep after a reviewer-model or batch-prompt
   change as mandatory, not advisory, and retain every run's artifact.
3. **Merge stage (deterministic, post-review).** After all stages run, a new
   `moderation/synthesis.py` groups content findings by every field the
   merged finding takes from a single survivor: `(category, concern, source,
   verdict, severity, message)`. Each group becomes one finding carrying
   `node_ids`, the shared verdict/severity/message, the max score, and the
   count. Live example: `sk_hollow_lighthouse`'s 12 identical above-band
   readability flags become one finding listing 12 nodes. The merge is
   plain code, not an LLM call; an optional whole-story LLM synthesis
   ("decision card" prose) can be layered later without changing storage.

   **Why the key is the full tuple and not `(category, concern)`.** The
   original spec named `(category, concern)`, which is a prefix of this key,
   so everything the worked example intends to merge still merges. The
   narrower key is only lossless when group members are interchangeable, and
   that does not hold in the order these items ship: item 1 supplies
   `concern`, so until it lands Stage 1 emits none and `(category, concern)`
   degenerates to `(category,)`. Every distinct safety reason in a book would
   then collapse into one row whose surviving message is whichever finding
   happened to sort first, with the rest discarded and no per-finding raw
   output to recover them from. Widening the key keeps the merge a display
   compression rather than a lossy edit to a safety record.
   #CRITICAL: security: the guardian reading the merged row is the final gate
   under ADR-005; a merged row must never attribute a verdict, severity, or
   message to a node that did not produce it. #VERIFY:
   tests/unit/test_moderation_synthesis.py covers distinct messages, mixed
   verdicts, and mixed severities all staying separate.

   Readers must fan out across `node_ids`, not group on `node_id`: `node_id`
   names only the FIRST covered node and exists for pre-Stage-B readers.
   #CRITICAL: security: grouping a merged finding by `node_id` renders one
   affected passage and leaves the rest of the flagged prose looking clean.
   #VERIFY: tests/unit/test_review_surface.py::
   test_merged_finding_fans_out_across_every_affected_node.

### 2.3 Structural-failure collapse (the flood killer)

`_parse_verdict` failures no longer create per-node findings. This covers
Stage 1's LLM fail-safe only; the Stage-0 malformed-payload fail-open (gap
report G11) is a separate, currently-silent path handled in 2.5. The stage
counts `_parse_verdict` failures and, if any occurred, emits **one**
story-level finding:
`category="pipeline"`, `concern="reviewer_unavailable"`, `structural=true`,
`verdict=FLAG`, `severity=high`, message carrying the affected-node count.
The fail-safe posture is intact (the story still cannot pass to a guardian
without human review); the surface cost drops from N rows to one.

The same collapse applies to the mock reviewer by construction: mock output
parses to unknown-verdict on every node, producing exactly one
`reviewer_unavailable` finding per story.

### 2.4 Mock-reviewer environment guard

New config validator, mirroring `_require_classifier_when_reviewing`:
`review_provider="mock"` with `environment` not `local` raises
`ConfigurationError` at boot. Seed/ops scripts that intentionally moderate
with the mock (catalog seeding) must set an explicit
`CYO_ADVENTURE_ALLOW_MOCK_REVIEW=1` escape hatch, which also stamps the
report (`reviewer_independent=false` plus a `structural` advisory) so a
mock-moderated report is self-identifying forever. This closes G1: 18 of 29
live books are mock-moderated and carry reports that look real but prove
nothing (18, not the 22-book any-safety-FLAG count; see the gap report's
3.1 for the distinction).

### 2.5 Observability for fail-safe verdicts

- New pipeline event payload field on `moderation_completed`:
  `counts.structural` (int). The allowlist stays enum/int-only, so no PII
  surface changes.
- `moderation/insights.py` gains a structural-vs-content split so 5,048
  structural fail-safes can never again read as "safety concerns" in the
  dashboard.
- A regression test feeds markdown-fenced JSON through `_parse_verdict`'s
  callers via a provider stub (G8): today fence-stripping exists only in the
  provider adapters and nothing proves the review path survives an adapter
  regression.
- Stage-0 malformed-payload fail-open (G11): `_run_openai`/`_run_perspective`
  (`classifiers.py:465-527`, `:530-577`) returning `[]` on a shape change
  needs the same `structural=true` accounting as a `_parse_verdict` failure;
  today it produces no finding at all, so a provider response-shape change
  reads as a clean screen. #VERIFY before Stage A ships.
- Threshold-flywheel containment (G2a), in Stage A scope because it is the
  same indistinguishability defect pointed at the safety gate itself:
  `suggest_thresholds` (`insights.py:272-317`) counts a mock-moderated book's
  fail-safe FLAG as override evidence like any other. Once the structural
  split above exists, structural fail-safes must be excluded from
  `decided_versions` and `override_rate` so the flywheel can never propose
  `safety` FLAG -> BLOCK on the strength of the flood, which would suppress
  genuine safety FLAGs from guardian and kid surfaces. Before Stage A ships,
  measure the current per-band `decided_versions` and `override_rate` for
  `(band, "safety")`: the gates (5 decided, 0.8 override rate) may or may not
  be met today, and no suggestion should be applied until that is known.
  **Measured 2026-07-29** (live Supabase, SQL mirror of `attribute_outcome`
  semantics; per-band safety flag counts sum to 5,056, matching the known
  llm_safety FLAG total, which validates the query): 10-13 = 1 decided /
  1 released; 13-16 = 1/1; 16+ = 4/4; 3-5, 5-8, 8-11 = 0/0. No band meets
  the gates today, but **16+ is one released decision away** (4 of 5
  decided, override rate 1.0, on 2,575 flag findings that are almost
  entirely mock fail-safe rows), so the flywheel exclusion must land
  before the next 16+ book is released, not merely "before Stage A ships".

### 2.6 Surfaces

**Admin** (`review_surface.py` + `ReviewDetailPage.tsx`): renders merged
findings ranked by (verdict, severity, node count), structural findings in
their own visually distinct block, per-finding node drill-down on demand.
The noise-floor mechanism is superseded by severity filtering (default:
show all FLAG/BLOCK, collapse `low` ADVISORY behind a toggle); the
`admin_noise_floor` row remains honored for Stage-0 scored advisories.

**Guardian** (`build_content_summary`): story-level summary only: overall
verdict, merged concern list (concern, severity, node count), repaired flag,
reviewer-independence. No per-node rows at all.

### 2.7 Stage 2 (LLM readability): disposition options

Evidence (gap report G10 plus this session's measurements):

- Stage 2's prompt asks the LLM to estimate the same Flesch-Kincaid
  grade-vs-target comparison RL-13 computes exactly and deterministically.
- Cost: one call per node, one persisted row per node (5,703 PASS rows
  bought 27 flags), and any single readability FLAG triggers the full
  auto-repair plus complete re-moderation (2N+2 more calls).
- RL-13 fires 285 warnings across 12 live books and is **completely
  invisible**: `validation_report` is written and never read by any API or
  surface; even repair adoption reads only `.blocked`.
- **The two signals disagree on live data in both directions.** The 4
  genuinely-reviewed books with 27 LLM flags have zero RL-13 warnings on
  those nodes (the LLM cites rare vocabulary and figurative language,
  which syllable-count FK partially misses); the 12 RL-13-warned books have
  no genuine LLM readability signal (they are mock-moderated). Neither
  signal has ground truth against a human judgment.

Options for the owner:

- **(a) Retire Stage 2; surface RL-13/PL-19 (recommended).** Drop the
  per-node LLM stage; make validator reading-level and words-per-node
  findings visible on both surfaces (they currently gate nothing and show
  nowhere). Add a one-line readability note to the existing whole-story
  engagement call so holistic vocabulary concerns keep a channel at 1/N of
  the cost. Accept: sub-20-word nodes and rare-vocabulary detection lose
  per-node LLM coverage.
- **(b) Keep Stage 2 whole-story.** Replace N per-node calls with one
  whole-story readability call (like coherence). Keeps the LLM lens,
  loses per-node attribution.
- **(c) Keep Stage 2 as is** with the 2.1/2.2 schema and merge changes
  (flags merge to one finding, PASS not persisted). Highest cost, no
  repair-amplification fix.

## 3. Post-Perspective Stage-0 architecture

### 3.1 What the research supports

Both research reports (Gemini survey; ChatGPT deep-research) agree on the
core negative results, from different evidence:

- The comment-toxicity taxonomy (Perspective, Detoxify) transfers badly to
  children's fiction **in both directions**: cited PG-STORY numbers show
  Perspective and Detoxify at ~41% unsafe recall, 57.8 unsafe F1, 67.1
  macro F1, vs 96.9 macro F1 for a task-specific model.
- Neither report identifies an actually obtainable task-specific
  child-safety classifier (the 96.9 model is unnamed and unreleased; the
  one named commercial product is uncited). The off-the-shelf market for
  this exact need does not exist yet.
- A like-for-like Detoxify swap reproduces a known-bad detector and is
  rejected (ratified in section 7, decision 7, on the evidence above, not
  on a separate handoff document).

Critical premise gap found in both reports: **neither evaluated serverless
GPU hosting (Modal), which the owner explicitly offered.** Both rejected
the modern guard-model class (Llama Guard, ShieldGemma, Qwen3Guard, Granite
Guardian) on a CPU-only homelab premise. Modal invalidates that premise:
book creation is infrequent, latency is near-irrelevant, and Modal is
already a supported provider in `generation/providers/`.

Load-bearing but unverified claims to check before any ADR cites them:
the PG-STORY figures come from one source and report byte-identical
Perspective/Detoxify scores (verify the primary paper); Gemini's
"Detoxify is the exact Perspective model" claim is uncited and contradicted
by ChatGPT's read; several pricing/retention cells trace to a competing
vendor's marketing blog or a wrong-entity privacy policy. The two source
reports themselves are not reachable in the repo: `tmp_cleanup/*` is
gitignored (`.gitignore:301`), so the Gemini survey and ChatGPT
deep-research files are not committed; this paragraph and the summary above
are the only durable record of their claims.

### 3.2 Recommended posture

1. **At sunset, drop the Perspective axis; do not replace it
   like-for-like.** It contributes zero findings to live data today, and
   its taxonomy is domain-mismatched. Stage-0 remains OpenAI
   omni-moderation (the enforced minimum as of this PR) plus the
   LLM Stage-1 hard gate.
2. **Run the baseline capture now** (while Perspective answers):
   `PYTHONPATH=. uv run python scripts/capture_stage0_baseline.py
   --env-file .env --out "docs/planning/safety/stage0-baseline-$(date +%F).json"`.
   This preserves the calibration oracle whether or not a successor is
   adopted.

   **Resolved 2026-08-01.** This supersedes the 2026-07-30 owner deferral
   previously recorded here.

   - *Command:* the one above, run against the tree at `6682ec17` with both
     `CYO_ADVENTURE_PERSPECTIVE_API_KEY` and the OpenAI key configured.
   - *Result:* 135 records (120 clean node passages, 15 corpus items), zero
     provider errors, `text_sha256` on every record.
   - *Artifact:* `docs/planning/safety/stage0-baseline-2026-08-01.json`,
     committed and re-derivable from the `reproduction` parameters it carries.
   - *Consequent change:* the capture **refutes** the `~6e-4` clean-prose
     ceiling that justified `_ADVISORY_SCORE_FLOOR = 0.01` in
     `moderation/classifiers.py`. All 120 clean passages score at or above the
     floor on at least one attribute, and the clean maximum (0.397
     `SEXUALLY_EXPLICIT`) exceeds the adversarial maximum (0.161); only
     `SEVERE_TOXICITY` (0.0153) and `IDENTITY_ATTACK` (0.0276) stay near
     `~6e-4`. The stale rationale is corrected in the same PR. The floor value
     is deliberately unchanged: advisories never gate, so this is review-surface
     noise, and moving it is a behavior change needing its own tests.
   - *Known gaps:* the capture predates #532, which rewrote 7 of the 25
     clean-source `out/*.filled.json` files, so a seeded re-run at a later head
     samples a different pool. All 120 sampled node bodies were verified
     byte-identical at both commits, so the recorded scores stand, but
     bit-identical reproduction is not guaranteed. Separately, 2 of the 13
     corpus items (`D1-import-bypass`, `D2-admin-submit-bypass`) are
     `"executable": false` call-graph controls with no text to score and are
     absent by construction.
   - *Re-run trigger:* any change to the clean corpus or the classifier set,
     and in any case before the 2026-12-31 sunset makes the scores
     unobtainable.
3. **Evaluate guard models on Modal as a candidate second axis**, scoped as
   an experiment, not a commitment: Qwen3Guard (0.6B/4B, Apache-2.0-family),
   ShieldGemma, Llama Guard 4, and Granite Guardian HAP-125M (CPU-viable,
   Apache-2.0, adds an explicit profanity head). Eval harness: the
   adversarial corpus (true positives) plus sampled filled-skeleton prose
   (true negatives), scored against the captured baseline; per-category
   calibration (Platt for sparse categories, isotonic only above ~1,000
   dual-scored samples); rank-correlation sanity check first.
   **APPROVED (owner, 2026-07-28).** Cost basis: the account carries $30/mo
   in Modal free credits; an eval sweep over the corpus with these model
   sizes is a few GPU-hours on per-second billing, and production Stage-0
   traffic is infrequent book creation, so both phases sit well inside the
   credit allowance. #ASSUME: external-resources: pricing and credit terms
   as of 2026-07-28. #VERIFY: re-check Modal's current per-second GPU rates
   and the credit grant when the eval harness is implemented.
4. **Age-appropriateness is a distinct axis from platform harm** (both
   reports converge here). If the guard-model eval underwhelms, the honest
   fallback is a small labeled eval set of our own story passages by band
   (a few hundred, human-labeled) and a fine-tune later; not a toxicity
   drop-in.
5. **`Source.PERSPECTIVE` retirement, hard-gated to the 2026-12-31 sunset.**
   The operative action is unsetting `PERSPECTIVE_API_KEY`
   (`core/config.py:564`) in every environment, or removing the Perspective
   call leg from `classifiers.py` outright, no later than 2026-12-31; stop
   emitting at sunset and keep the `Source.PERSPECTIVE` enum member for
   JSONB read-compat. This is not optional cleanup: a dead endpoint past
   sunset raises `ClassifierUnavailable` (`classifiers.py:556`) on every
   call, opens the circuit breaker after `_MAX_CONSECUTIVE_FAILURES = 3`
   (`classifiers.py:82`), and emits a `classifier_coverage_incomplete` FLAG
   (`classifiers.py:375-376`) that soft-gates every book into repair plus
   full re-moderation (`pipeline.py:300-304`) for an infrastructure reason,
   not a content one, on every book, forever. The retirement touches every
   call site that passes `perspective_key`, not just the main pipeline
   (`moderation/pipeline.py:758`): `story_requests/screening.py` (intake,
   `report_coverage=False`), `api/node_edit.py:545`,
   `api/story_requests.py:409`, `:674`, `:1020`, and
   `moderation/rescreen.py:457` all need the same change. Zero perspective
   rows exist in the measured environment; verify the other environment(s)
   before deleting anything. Config already refuses Perspective-only
   deployments.

Privacy note (verified this session): moderation egress carries stripped,
un-personalized text (sentinels stripped at `pipeline.py:736`; per-node PII
guard at `pipeline.py:746-747`; reviewer wrapped in `PiiGuardedProvider`),
so a cloud-hosted classifier is justifiable. Residual risk: pattern-based
free-text PII screening is defense-in-depth, not a guarantee; a retaining
provider remains a tradeoff to surface per the owner's stated posture.

## 4. Catalog remediation

The 18 mock-moderated books (see the gap report's 3.1; not the 22-book
any-safety-FLAG count) carry reports that are evidence of nothing. After
Stages A and B land (below):

1. Add a small admin-triggered "re-moderate" entry point that re-runs
   `run_moderation_pipeline` on an existing version (the pipeline already
   supports repeat invocation; the entry point is routing plus permissions,
   akin to `rescreen` but running the full pipeline, and stamping a
   re-moderation event).
2. Re-moderate the 18 books with the real reviewer under the new model.
   With chunked Stage-1 calls this is ~50-80 review calls per large book
   instead of ~1,500, assuming Stage 2 is retired per option (a) in 2.7.
   Under option (c) (keep Stage 2 per-node), `sk_ninth_hand` stays near
   ~800 combined Stage-1+Stage-2 calls even after chunking Stage 1, since
   Stage 2 remains one call per node.
3. Published books among them stay published while re-moderation runs
   (ADR-005: rescreen never auto-unpublishes; the same posture applies);
   new reports replace the mock ones and route through normal review.

## 5. Moderation QA corpus (staging)

Owner-proposed (2026-07-28): a set of test stories in the staging
environment for moderation testing, so inappropriate content never needs to
exist in production. Design:

1. **Ground truth lives in the repo, not a table.** Extend the existing
   labeled-corpus pattern (`adversarial-corpus.json`: 13 passages with
   `expected_min_verdict` / `age_band` / `target_stage` labels) to whole
   storybooks with per-node prose and per-node/story expected labels, so
   verdict expectations are versioned, reviewable, and diffable when the
   model changes.
2. **Seeded into staging as real `storybook` rows**, not a parallel table:
   the value is end-to-end fidelity (worker, queue, classifiers, reviewer,
   repair, routing, surfaces all process a known-bad book). A dedicated
   table would need parallel plumbing and would test a copy of the
   pipeline, not the pipeline.
3. **Containment layers** (#CRITICAL: security: QA content must be
   unreachable from production and from kid surfaces in any environment):
   - the seed script hard-refuses `ENVIRONMENT=production` (same posture
     as the existing seeders);
   - ids are namespaced (`mqa_` prefix) and rows belong to a dedicated
     Moderation QA family, never assigned to real profiles;
   - the existing read gate (approved AND assigned) already makes
     unapproved test books invisible to kid surfaces;
   - `publishing/service.py` refuses to approve/publish an `mqa_`-prefixed
     story outside staging (defense in depth against an admin misclick).
   - #VERIFY: seed-script env-guard test; publishing-guard unit test; a
     staging e2e assertion that no `mqa_` book is kid-visible.
     **All three exist as of 2026-08-01**: the e2e half is
     `frontend/e2e-staging/moderation-qa-invisibility.spec.ts` (daily
     e2e-staging workflow), which anchors on an admin presence check of all
     six corpus ids so a staging reset turns the assertion loudly red
     instead of vacuously green, then asserts the kid library API payload
     and rendered DOM are `mqa_`-free from a real device-grant session.
4. **Scorecard**: after moderation runs over the seeded set, compare stored
   reports against expected labels and emit a pass/fail diff. This is the
   Stage B UI QA fixture (admins inspect a known-bad book's merged decision
   cards), the Stage C eval/calibration set, and the regression harness for
   any reviewer-model or prompt change.
5. **Authoring guideline**: depth goes to band-borderline content (too
   mature for one band, acceptable for a higher one), which is where the
   review model must discriminate; a handful of bright-line BLOCK cases
   suffices. Production needs no unsafe content at any point: prod's
   catalog was audited clean (2026-07-24) and Stage D only re-moderates
   those existing books.

## 6. Staged delivery plan

| Stage | Content | Size | Depends on |
| --- | --- | --- | --- |
| **A: stop the bleeding** | Structural-failure collapse (2.3), mock environment guard (2.4), observability (2.5), fenced-JSON regression test | Small PR, no schema change readers must migrate for | nothing |
| **B: the review model** | Finding schema (2.1), structured verdicts + chunking (2.2), merge stage, surfaces (2.6), RL-13/PL-19 visibility, Stage-2 disposition per owner choice (2.7) | The main PR series | A |
| **C: Stage-0 successor** | Baseline capture run, Modal guard-model eval, calibration report, Perspective emission retirement (unset `PERSPECTIVE_API_KEY` / remove the leg, all call sites per 3.2 item 5) | Experiment + small PRs | capture DONE 2026-08-01 (see 3.2 item 2), unblocking the Modal eval; rest independent of A/B |
| **D: catalog remediation** | Re-moderate entry point + the 18-book sweep | Small PR + ops run | A, B |
| **QA corpus (staging)** *(design confirmed 2026-07-29, decision 6)* | Labeled storybook fixtures (section 5), staging seed script + containment guards, scorecard diff | Repo fixtures + small PR | authored anytime; seeded before B's UI QA; feeds C's eval |

Stage A is deliberately shippable alone: it prevents every future flood and
makes the failure class visible, even if B's surface redesign takes longer.

### 6.1 Delivery status as of 2026-08-25

Read against live source at `bfd47f54` and live production data. This table
records what has landed, not what was intended.

| Stage | Status | Evidence |
| --- | --- | --- |
| **A** | Delivered | Per-node fail-safe collapse into one story-level structural finding (`moderation/stages.py`, the `reviewer_unavailable` concern in `CONCERN_TAXONOMY`); `reviewer_independent` written by the pipeline rather than assumed (`moderation/pipeline.py`) |
| **B** | Delivered | `moderation/synthesis.py` (deterministic post-review merge), `api/review_surface.py` (PASS filtered before ranking, verdict-then-severity-then-node-count order, structural / low-advisory / ranked split, admin-only noise floor), `_VALIDATOR_RULE_IDS = {RL-13, PL-19}` per decision 1 |
| **C** | Partly delivered | Stage-0 baseline captured 2026-08-01 (`safety/stage0-baseline-2026-08-01.json`). Perspective emission is NOT retired: `perspective` still appears in `core/config.py`, `moderation/pipeline.py`, `story_requests/screening.py`, `api/story_requests.py`, `api/reading_time.py`. The Modal guard-model eval was not verified in this pass |
| **D** | Code half delivered, ops run pending | Entry point `api/remoderate.py` (#753, widened to `in_review`), sweep selection `scripts/remoderate_books.py` (`--in-review`, `--book-id`, dry-run default). **The sweep has never run:** production's newest `storybook_version` row is dated 2026-07-28 and all seventeen reports still date from 2026-07-21 |
| **QA corpus** | Fixtures authored | `safety/moderation-qa-corpus.json`, `scripts/seed_moderation_qa.py`, `scripts/moderation_qa_scorecard.py`. Whether it has been seeded into staging was not verified here |

**What the delivered stages do not yet buy.** A and B change what a reviewer is
shown, and the seventeen stored reports predate both, so nothing a reviewer sees
today reflects them. The census in
[moderation-review-current-state-2026-08-25.md](./moderation-review-current-state-2026-08-25.md)
also shows the backlog's dominant problem is not flood but absence: twelve books
carry no real verdicts at all. Stage D's ops run, not further surface work, is
what converts the delivered redesign into a reviewable backlog.

## 7. Decisions requested from the owner

1. **Stage-2 disposition**: **DECIDED 2026-07-29: option (a).** Retire the
   per-node LLM readability stage and surface the validator's deterministic
   RL-13/PL-19 readability findings instead. Note for the record: the
   section 4 remediation call-count math (~50-80 calls per large book)
   assumed option (a); this decision is what keeps decision 5's immediate
   sweep cheap.
2. **Severity scale**: DECIDED by design in section 2.1: three-level enum
   (`high | medium | low`). **Confirmed by the owner 2026-07-29;** stands
   as designed.
3. **Guardian summary contract**: DECIDED by design in section 2.6:
   story-level summary with a merged concern list, repaired flag, and
   reviewer-independence; no per-node rows. **Confirmed by the owner
   2026-07-29;** stands as designed.
4. **Modal guard-model experiment**: **DECIDED 2026-07-28: approved.**
   Owner basis: $30/mo in Modal free credits; current per-second GPU pricing
   keeps an eval sweep nowhere near that cap (see 3.2 item 3).
5. **Remediation timing**: **DECIDED 2026-07-29: re-moderate the 18
   mock-moderated books right after Stage B lands** (not batched with the
   first catalog refresh). Cost basis per section 4: ~50-80 real review
   calls per large book under the retired-Stage-2 pipeline from decision 1.
6. **Moderation QA corpus** (section 5): owner-proposed 2026-07-28;
   **design CONFIRMED by the owner 2026-07-29** as written: repo ground
   truth, staging-only `mqa_` seeding, four containment layers.
7. **Perspective-axis retirement** (section 3.2 item 1): RATIFIED by the
   evidence in this document, not a separate owner decision: Perspective
   contributes zero findings to live data (gap report section 3) and its
   comment-toxicity taxonomy is domain-mismatched to children's fiction
   (section 3.1 above); no like-for-like replacement is proposed. Recorded
   here for visibility since it is the largest architectural call in this
   document.

## 8. RAD summary

- #CRITICAL: security: the Stage-1 fail-safe (unparseable safety verdict
  never passes) is preserved through every change above; 2.3 changes its
  shape, not its effect. #VERIFY: adversarial-corpus tests
  (tests/unit/test_ai_security_corpus.py) must pass unchanged against the
  collapsed representation.
- #ASSUME: data-integrity: old persisted reports (no severity/concern
  fields, per-node fail-safe rows) must render on the new surfaces.
  #VERIFY: reader-compat tests over a fixture captured from live JSONB
  before migration.
- #ASSUME: external-resources: chunked review accuracy is unproven.
  #VERIFY: corpus comparison per 2.2 before default-on.
- #EDGE: concurrency: re-moderation of a published book racing a guardian
  action reuses the existing FOR UPDATE lock in `run_moderation_pipeline`.
  #VERIFY: existing lock test covers the re-moderate entry point too.
- #CRITICAL: security: QA corpus content must never reach production or any
  kid surface (section 5 containment layers: seed script env refusal,
  `mqa_` namespace + dedicated family, read gate, publishing guard).
  #VERIFY: seed-script env-guard test, publishing-guard unit test, and a
  staging e2e assertion that no `mqa_` book is kid-visible (all three exist
  as of 2026-08-01; e2e =
  `frontend/e2e-staging/moderation-qa-invisibility.spec.ts`).
