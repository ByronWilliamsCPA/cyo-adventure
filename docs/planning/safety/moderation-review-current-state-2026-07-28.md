---
title: "Moderation Review: Current-State Analysis and Gap Report"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Document what the moderation pipeline emits, what admins and guardians actually see, and why the review surface is unusable (hundreds of flags per book), as the evidence base for the post-Perspective Stage-0 architecture and the review-model redesign."
tags:
  - planning
  - safety
  - moderation
component: Safety-Pipeline
source: "Owner complaint 2026-07-28 (hundreds of useless flags per book); live moderation_report data queried via Supabase MCP 2026-07-28; moderation pipeline at src/cyo_adventure/moderation/ as of commit 43bfc72"
---

# Moderation Review: Current-State Analysis and Gap Report

> **Status**: Draft for owner review. This is deliverable 2 of the moderation
> redesign track. Deliverable 3 (the recommended post-Perspective architecture
> and review model) builds on the gaps identified here and is a separate
> document.

## 1. Context and scope

Two problems arrived together and are deliberately separated:

1. **Google Perspective sunsets 2026-12-31** with no migration path. The
   config-layer risk is already closed (commit `43bfc72`: only
   `OPENAI_API_KEY` now satisfies the classifier-presence invariant), and a
   raw-score baseline capture script exists so a successor can be calibrated
   rather than guessed.
2. **The review surface is unusable.** In the owner's words: "Most stories
   have hundreds of flags that arent useful. We need to develop a more useful
   process for both admins and guardians so that they can make effective
   decisions."

Live data proves these are independent: **Perspective contributes zero
findings to the current corpus**, so replacing it changes nothing the owner is
complaining about. Usability leads; the Perspective successor is a follow-on
decision.

## 2. Pipeline anatomy (what runs today)

`run_moderation_pipeline` (`src/cyo_adventure/moderation/pipeline.py`) runs
after draft persistence and drives every story to `submit` (in_review) or
`auto_reject` (needs_revision). Guardian approval remains the final gate
(ADR-005); the pipeline never publishes.

| Stage | Module | Granularity | Verdicts | Gate |
|---|---|---|---|---|
| 0: OpenAI Moderation | `classifiers.py` | per node | BLOCK (7 bright-line categories) / ADVISORY (score >= 0.01 floor) / dropped | hard |
| 0: Perspective | `classifiers.py` | per node | BLOCK (SEXUALLY_EXPLICIT >= 0.8) / ADVISORY (>= 0.01) / dropped | hard |
| 1: LLM safety | `stages.py::run_safety_stage` | per node | BLOCK / FLAG / PASS | hard (BLOCK), soft (FLAG) |
| 2: LLM readability | `stages.py::run_readability_stage` | per node | FLAG / PASS | soft |
| 3: LLM coherence | `stages.py::run_coherence_stage` | whole story | FLAG / PASS | soft |
| 4: LLM engagement | `stages.py::run_engagement_stage` | whole story | ADVISORY / PASS | advisory |

Key structural facts:

- **Stages 1 and 2 persist one `Finding` per node unconditionally**, PASS
  included (`stages.py:196-216`, `:247-268`). An N-node book stores at least
  2N LLM findings before any content concern exists.
- **`Finding.score` exists (`report.py:64`) but only Stage-0 classifiers set
  it.** Every LLM-stage finding is constructed without a score and persists as
  `score: null`.
- **Verdict parsing fails safe** (`stages.py::_parse_verdict`). Unparseable or
  unknown reviewer output maps to FLAG for Stage 1 (a garbled safety verdict
  must never silently pass) and PASS for stages 2-4. This asymmetry is
  deliberate and correct; its interaction with the mock reviewer is the
  dominant noise source (section 4).
- **A soft FLAG triggers one bounded auto-repair** then a single re-moderation
  pass; routing then proceeds on whichever report stands.
- The review provider is selected by `settings.review_provider`
  (`"mock" | "ollama" | "openrouter" | "modal"-deferred`), default **mock**
  (`core/config.py:556`). The mock returns the literal string `"{}"` for every
  call (`review_provider.py:77-78`).

## 3. What the live data shows

Source: the MCP-connected Supabase project, queried 2026-07-28. 29
`storybook_version` rows carry a non-null `moderation_report`; 11,932 findings
total; the largest single book stores 1,494 findings (`sk_ninth_hand`).

### 3.1 Findings by source and verdict

| Source | Verdict | Findings | Books | Of which fail-safe message |
|---|---|---:|---:|---:|
| llm_readability | pass | 5,703 | 29 | 5,048 |
| llm_safety | flag | 5,056 | 22 | **5,048** |
| llm_safety | pass | 674 | 11 | 0 |
| openai | advisory | 414 | 9 | 0 |
| llm_coherence | pass | 29 | 29 | 18 |
| llm_readability | flag | 27 | 4 | 0 |
| llm_engagement | pass | 24 | 24 | 18 |
| llm_engagement | advisory | 5 | 5 | 0 |
| **perspective** | any | **0** | 0 | 0 |

"Fail-safe message" counts findings whose message is exactly
`unknown verdict; defaulted to fail-safe`, the string emitted by exactly one
code path (`stages.py:164-166`).

### 3.2 The flood, per book

Every mass-flagged book shows the same signature: flag count equals node
count, and every message is the identical fail-safe string.

| Book | llm_safety FLAGs | Message |
|---|---:|---|
| sk_ninth_hand | 746 | unknown verdict; defaulted to fail-safe |
| sk_harrowstone_keep | 550 | unknown verdict; defaulted to fail-safe |
| sk_sunken_temple | 550 | unknown verdict; defaulted to fail-safe |
| sk_ashfall_expedition | 505 | unknown verdict; defaulted to fail-safe |
| sk_thornwood_trial | 375 | unknown verdict; defaulted to fail-safe |
| (13 more books) | 32-314 each | same |

By contrast, 11 books carry genuine reviewer output: real PASS reasons
("Gentle adventure narrative with no mature, dangerous, or inappropriate
content") and exactly **8 genuine safety FLAGs** across the whole corpus (the
beehive and wild-berries observations sampled in the 2026-07-28 handoff are
from this set).

### 3.3 Correction to the prior working hypothesis

The 2026-07-28 handoff, sampling messages before the message-level breakdown
existed, concluded "the individual flags are not wrong; expect the fix to be
triage and synthesis, not a stricter threshold." The message-level data
revises that: **99.8% of safety FLAGs (5,048 of 5,056) are not reviewer
judgments at all.** They are the structural fail-safe of a reviewer that
cannot answer. Triage and synthesis remain necessary (section 6), but the
first-order fact is that the flooded books were moderated by the mock backend.

### 3.4 Resolved data anomaly

`s_c250490d-80f7-499c-8490-47901fb09c9b` carries 143 openai findings with
scores far below the 0.01 advisory floor (4.45e-8 to 6.1e-4). Explanation:
that book was moderated 2026-07-06 02:38 UTC; the advisory floor merged the
same day (`899db43`, PR #141). The book predates the floor. Historical
artifact, not a live bug; no other book shows sub-floor scores.

## 4. Root cause of the flood

Three links, each individually defensible, jointly pathological:

1. **The mock reviewer returns `"{}"`** for every call
   (`review_provider.py:77-78`). `review_provider="mock"` is the config
   default and is what the catalog seed/import operations ran with.
2. **`"{}"` parses but answers nothing.** `json.loads` succeeds, the verdict
   key is absent, the mapping lookup returns None, and `_parse_verdict`
   returns the stage's fail-safe with the fingerprint message. For Stage 1
   the fail-safe is FLAG; for stages 2-4 it is PASS. That is why only
   `llm_safety` floods while `llm_readability` silently stores 5,048
   fail-safe PASSes.
3. **Stage 1 persists one finding per node unconditionally**, so N nodes
   become N identical FLAGs with no collapse, no dedup, and no score.

The hard gate behaved correctly: it refused to treat a non-answer as safe.
What failed is everything around it: an operational path pointed a hard
safety gate at a reviewer that structurally cannot answer, and no layer
collapses, ranks, suppresses, or even counts the resulting identical
failures.

## 5. What reviewers actually see

### 5.1 Admin

`api/review_surface.py` builds the admin view; PASS findings are filtered
out (`review_surface.py:82`), everything else surfaces. The only volume
control is the noise floor (`thresholds.py:184-219`, default 0.05, DB row
`admin_noise_floor`):

```python
return not (
    verdict is Verdict.ADVISORY and score is not None and score < noise_floor
)
```

All three conjuncts must hold to suppress, so the floor **only ever hides
scored Stage-0 ADVISORYs**. It can never hide a FLAG, and never hides an
unscored finding. Every LLM finding is an unscored FLAG or ADVISORY, so the
one denoise lever that exists cannot touch the noise that dominates the
surface.

The frontend (`frontend/src/admin/ReviewDetailPage.tsx:473-519`) renders
every flagged passage and every finding within it: no cap, no pagination, no
grouping by category or source. The only aggregation anywhere is a
block/flag/advisory severity tally. An admin opening `sk_ninth_hand` faces
746 identical line items.

Additionally, persisted PASS rows (roughly half of all stored findings)
inflate `summary.count`, so dashboard badges overstate even what the filtered
view will show.

### 5.2 Guardian

The guardian path (`build_content_summary`, `review_surface.py:51-59`,
`:428-432`) uses `ThresholdPolicy` with `min_verdict` defaulting to FLAG and
a `min_score` that short-circuits on unscored findings
(`thresholds.py:118-122`). Unscored FLAGs therefore pass through to
guardians too. The flood reaches both audiences; neither has a lever against
it.

### 5.3 Moderation dashboard

`moderation/insights.py` aggregates strictly by `(age_band, category)`. A
fail-safe FLAG carries `category="safety"`, so 5,048 structural failures are
indistinguishable from genuine safety concerns in every dashboard metric.

## 6. Gap register

| ID | Gap | Evidence |
|---|---|---|
| G1 | An operational/seed path can run the hard safety gate against the mock reviewer and persist the result as a real moderation report. Nothing marks the report as "reviewed by a backend that cannot answer". | 22 of 29 live books; `review_provider.py:77-78` |
| G2 | Fail-safe verdicts are invisible as a class. `verdict_parse_failed` / `verdict_unknown` are log-only warnings (`stages.py:162`, `:165`); no metric, event, dashboard, or finding field distinguishes a structural fail-safe from a genuine flag. The message string is the only discriminator and nothing parses it. | Survey of logs/dashboards; `insights.py:154-254` |
| G3 | N identical structural failures persist as N findings. No collapse of repeated identical (category, message) pairs into one story-level finding. | 746 identical rows on `sk_ninth_hand` |
| G4 | The noise floor structurally cannot suppress LLM findings: it requires ADVISORY plus a non-null score, and all LLM findings are unscored FLAGs/ADVISORYs. | `thresholds.py:217-219`; `stages.py:207` et al. |
| G5 | No severity ranking, deduplication, or story-level synthesis exists for genuine findings either. Even a real reviewer on a 746-node book yields an unranked flat list; concerns repeated across nodes (same hazard in many passages) are not merged. | `ReviewDetailPage.tsx:473-519`; handoff samples |
| G6 | PASS rows are persisted (roughly half of all findings), inflating storage and `summary.count` badges while adding no review value. | 5,703 + 674 + 29 + 24 PASS rows of 11,932 |
| G7 | Guardians receive the same unsuppressed FLAG stream as admins; the guardian threshold policy's score lever is inert against unscored findings. | `thresholds.py:118-122`; `review_surface.py:428-432` |
| G8 | No test covers markdown-fenced (or otherwise decorated) reviewer output through `_parse_verdict`. Fence stripping lives only in the provider adapters; a reviewer model or adapter regression that emits unparseable output would flood every book exactly like the mock does, with only a log line as signal. | `stages.py:133-167`; provider-layer tests only |
| G9 | Perspective is dead weight: zero live findings, sunset 2026-12-31. `Source.PERSPECTIVE` is persisted-JSONB-coupled (`review_surface.py` raises on unrecognized sources at rest), so retirement needs a read-compat plan even though this environment holds zero rows. Verify staging and prod row counts before removal. | Section 3.1; handoff item 5 |
| G10 | Stage-2 readability duplicates a deterministic check. LLM-judged reading level is approximate by its own RAD tag, while the validator already computes band-profile/reading-level deterministically. 5,703 stored rows bought 27 flags in 4 books. | `stages.py:244-246`; `validator/reading_level.py` |

## 7. Requirements the redesign must satisfy

Derived from the gaps; the design document will propose mechanisms.

1. **A reviewer that cannot answer must produce one story-level outcome, not
   N per-node findings.** Structural failure (parse failure, unknown verdict,
   mock backend in a non-local environment) is a pipeline condition, not
   content findings.
2. **Fail-safe verdicts must be observable as a class**: counted, dashboarded,
   and distinguishable from genuine flags without string-matching messages.
3. **The review surface must present a bounded, ranked, deduplicated set of
   decisions.** The owner's acceptance bar: an approving reviewer reads
   decisions, not per-node line items. Identical or near-identical concerns
   across nodes merge into one finding with affected-node references.
4. **Every gating signal should carry a severity/confidence the surfaces can
   filter on**, closing the unscored-FLAG blind spot instead of adding another
   special case to the noise floor.
5. **PASS need not persist as rows** (an aggregate suffices), or if retained
   for audit, must not count toward surfaced totals.
6. **Guardian and admin surfaces need distinct volume contracts**; guardians
   decide from a summary, admins from ranked detail.
7. **Stage-0 successor** (post-Perspective) is chosen against the captured
   raw-score baseline, not swapped like-for-like; the comment-toxicity axis is
   domain-mismatched to children's fiction (PG-STORY: Perspective/Detoxify
   unsafe F1 57.8 vs 96.9 for a task-specific model).
8. **Catalog remediation**: the 22 flooded books need re-moderation with a
   real reviewer once the new model lands; their current reports are
   evidence of nothing except the mock path.

## 8. Measurement provenance

All counts in section 3 were queried 2026-07-28 via the read-only Supabase
MCP (`execute_sql`) against the project this repo's MCP config targets, the
same environment the 2026-07-28 handoff measured (its `sk_ninth_hand` = 746
matches exactly). Query shapes: `jsonb_array_elements` over
`storybook_version.moderation_report->'findings'`, grouped by source,
verdict, and message. Numbers will drift as books are added; re-run before
citing in the design doc.
