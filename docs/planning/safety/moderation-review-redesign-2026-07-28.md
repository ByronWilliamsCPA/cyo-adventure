---
title: "Moderation Review Redesign: Decisions, Not Flags"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Propose the replacement review model (bounded, ranked, deduplicated decision surface), the post-Perspective Stage-0 architecture, the Stage-2 readability disposition, and the catalog remediation plan, staged for owner approval before implementation."
tags:
  - planning
  - safety
  - moderation
component: Safety-Pipeline
source: "Gap report docs/planning/safety/moderation-review-current-state-2026-07-28.md; owner constraints from the 2026-07-28 handoff; digests of tmp_cleanup/Perspective API Replacement Survey.md (Gemini) and tmp_cleanup/deep-research-report (9).md (ChatGPT); live Supabase measurements 2026-07-28"
---

# Moderation Review Redesign: Decisions, Not Flags

> **Status**: Draft design for owner approval. No implementation has started.
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
| `concern` | short slug from a fixed taxonomy (e.g. `real_world_danger`, `too_mature`, `frightening_content`, `cruelty`, `reviewer_unavailable`) | The dedup/merge key. Free-text `message` remains for detail. |
| `node_ids` | `list[str]` (replaces single `node_id` on merged findings; `node_id` kept for compat) | One finding can now reference every node it applies to. |
| `structural` | `bool`, default false | Marks pipeline-condition findings (parse failure, unknown verdict, degraded classifier) so dashboards and surfaces can class them separately from content findings. |

PASS is no longer persisted as rows. The report gains an aggregate block:
`{"nodes_reviewed": N, "pass_counts": {"safety": n1, ...}}`. This removes
roughly half of all stored findings (6,430 PASS rows in live data) and fixes
`summary.count` badge inflation. Audit needs are covered by the aggregate
plus the existing `moderation_completed` event counts.

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
   batching by default.
3. **Merge stage (deterministic, post-review).** After all stages run, a new
   `moderation/synthesis.py` groups content findings by
   `(category, concern)`, merges each group into one finding carrying
   `node_ids`, the max severity, a representative message, and the count.
   Live example: `sk_hollow_lighthouse`'s 12 identical above-band
   readability flags become one finding listing 12 nodes. The merge is
   plain code, not an LLM call; an optional whole-story LLM synthesis
   ("decision card" prose) can be layered later without changing storage.

### 2.3 Structural-failure collapse (the flood killer)

`_parse_verdict` failures no longer create per-node findings. The stage
counts them and, if any occurred, emits **one** story-level finding:
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
mock-moderated report is self-identifying forever. This closes G1: 22 of 29
live books carry reports that look real but prove nothing.

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
  rejected (already ratified in the 2026-07-28 handoff).

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
vendor's marketing blog or a wrong-entity privacy policy.

### 3.2 Recommended posture

1. **At sunset, drop the Perspective axis; do not replace it
   like-for-like.** It contributes zero findings to live data today, and
   its taxonomy is domain-mismatched. Stage-0 remains OpenAI
   omni-moderation (already the enforced minimum since `43bfc72`) plus the
   LLM Stage-1 hard gate.
2. **Run the baseline capture now** (while Perspective answers):
   `PYTHONPATH=. uv run python scripts/capture_stage0_baseline.py
   --env-file .env --out docs/planning/safety/stage0-baseline-2026-07-28.json`.
   This preserves the calibration oracle whether or not a successor is
   adopted.
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
5. **`Source.PERSPECTIVE` retirement**: stop emitting at sunset; keep the
   enum member for JSONB read-compat. Zero perspective rows exist in the
   measured environment; verify the other environment(s) before deleting
   anything. Config already refuses Perspective-only deployments.

Privacy note (verified this session): moderation egress carries stripped,
un-personalized text (sentinels stripped at `pipeline.py:736`; per-node PII
guard at `pipeline.py:746-747`; reviewer wrapped in `PiiGuardedProvider`),
so a cloud-hosted classifier is justifiable. Residual risk: pattern-based
free-text PII screening is defense-in-depth, not a guarantee; a retaining
provider remains a tradeoff to surface per the owner's stated posture.

## 4. Catalog remediation

The 22 mock-moderated books carry reports that are evidence of nothing.
After Stages A and B land (below):

1. Add a small admin-triggered "re-moderate" entry point that re-runs
   `run_moderation_pipeline` on an existing version (the pipeline already
   supports repeat invocation; the entry point is routing plus permissions,
   akin to `rescreen` but running the full pipeline, and stamping a
   re-moderation event).
2. Re-moderate the 22 books with the real reviewer under the new model.
   With chunked Stage-1 calls this is ~50-80 review calls per large book
   instead of ~1,500.
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
| **C: Stage-0 successor** | Baseline capture run, Modal guard-model eval, calibration report, Perspective emission retirement at sunset | Experiment + small PRs | capture ASAP; rest independent of A/B |
| **D: catalog remediation** | Re-moderate entry point + the 22-book sweep | Small PR + ops run | A, B |
| **QA corpus (staging)** | Labeled storybook fixtures (section 5), staging seed script + containment guards, scorecard diff | Repo fixtures + small PR | authored anytime; seeded before B's UI QA; feeds C's eval |

Stage A is deliberately shippable alone: it prevents every future flood and
makes the failure class visible, even if B's surface redesign takes longer.

## 7. Decisions requested from the owner

1. **Stage-2 disposition**: option (a) retire + surface RL-13 (recommended),
   (b) whole-story LLM readability, or (c) keep per-node.
2. **Severity scale**: three-level enum (recommended: maps cleanly to
   surfaces and prompts) vs numeric 0-1.
3. **Guardian summary contract**: merged concern list (recommended) vs
   verdict-only.
4. **Modal guard-model experiment**: **DECIDED 2026-07-28: approved.**
   Owner basis: $30/mo in Modal free credits; current per-second GPU pricing
   keeps an eval sweep nowhere near that cap (see 3.2 item 3).
5. **Remediation timing**: sweep the 22 books right after B, or batch with
   the first real catalog refresh.
6. **Moderation QA corpus** (section 5): owner-proposed 2026-07-28; the
   design above (repo ground truth, staging-only seeding, containment
   layers) awaits confirmation alongside decisions 1-3.

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
  staging e2e assertion that no `mqa_` book is kid-visible.
