---
title: "Phase 3 Slice 2: Staged Content-Moderation Review Pipeline (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "2026-06-29-phase-3-safety-review-design.md section 4, publishing/state_machine.py + service.py (slice 1, merged via PR #34), generation/provider.py + guarded.py, validator/gate.py + reading_level.py + band_profile.py, db/models.py StorybookVersion + GenerationJob, brainstorming decisions 2026-06-30"
purpose: "Design for the CYO-native staged moderation review pipeline that screens generated stories between the deterministic gate and guardian review: a deterministic classifier pre-filter, an LLM safety hard gate, two LLM soft quality gates, and an LLM advisory pass, all behind an independence-enforcing review provider."
tags:
  - planning
  - architecture
  - project
---

> Branch: `feat/phase-3-slice-2-review-pipeline` (to be created) | Date: 2026-06-30 | Author: Byron Williams (with Claude)
> Builds on: [Phase 3 design section 4](2026-06-29-phase-3-safety-review-design.md), slice 1 (approval spine, merged PR #34).
> Implements: [roadmap Phase 3](../../planning/roadmap.md#phase-3-safety-and-review-workflow-3-4-weeks-overlaps-phase-2),
> [ADR-005 mandatory human approval](../../planning/adr/adr-005-mandatory-human-approval.md).

## 1. Problem and scope

Slice 1 made the kids-facing guarantee enforceable: no story reaches a child profile without a
recorded guardian approval. But slice 1 left the path from generation to the guardian's queue
empty. A freshly generated story that passes the deterministic validator gate lands at
`storybook.status = "draft"` and nothing moves it forward. The guardian, when the review UI
arrives (Phase 4a), would face raw generator output with no machine pre-screening: no
age-relative safety judgment, no readability check, no cross-branch coherence verdict.

Slice 2 fills that gap with a **staged content-moderation review pipeline**. It runs after the
deterministic gate passes, screens the story across five stages, persists structured findings,
and drives the slice-1 state machine: a clean or auto-repaired story is submitted to
`in_review` for the guardian with its findings attached; a hard-blocked story is auto-rejected
to `needs_revision` without ever reaching a human.

**In scope:** the five-stage pipeline; a deterministic classifier pre-filter (Stage 0); one LLM
safety hard gate (Stage 1); two LLM soft quality gates (Stages 2-3); one LLM advisory pass
(Stage 4); the `ReviewProvider` abstraction with reviewer-independence enforcement; the
`service.auto_reject` state-machine wrapper; classifier and review-provider configuration;
persistence on `storybook_version.moderation_report`.

**Out of scope:** the guardian review-surface read API (slice 3); any frontend (Phase 4a); the
deferred reading-state-validation slice (red-team Finding 2); direct Anthropic/Gemini/Perplexity
review adapters (the keys are wired into `.env.example` as documented future hooks, but reviews
flow through OpenRouter, Ollama, and Modal only).

## 2. Pipeline placement (architectural decision)

The pipeline is a **separate async stage that runs after `run_gate` passes**, not a replacement
for the synchronous `SAFE-14` stub inside the deterministic gate.

The deterministic gate (`validator/gate.py::run_gate`) is synchronous, pure, and network-free,
and the orchestrator calls it on every repair iteration. The moderation pipeline is async, makes
LLM and classifier network calls, and should run once per story, not per repair attempt. Folding
it into `check_safety`/`run_gate` would force the entire deterministic gate async and fire LLM
calls inside the tight repair loop. Section 4 of the Phase 3 design names both placements
loosely ("replaces the SAFE-14 stub" in its intro, "runs between generation and `in_review`
after the deterministic gate" in its body); this spec resolves the contradiction in favor of the
separate post-gate stage. The synchronous `SAFE-14` stub in `validator/safety.py` stays a
deterministic no-op; it is not where LLM review lives.

Flow:

```
generation orchestrator
  -> run_gate (deterministic; structural + policy + reading-level RL-13)
     -> pass  => storybook.status = "draft"
        -> moderation pipeline (NEW, async, this slice)
           -> Stage 0 classifier pre-filter
           -> Stage 1 LLM safety hard gate
           -> Stage 2 LLM readability soft gate
           -> Stage 3 LLM branch-coherence soft gate
           -> Stage 4 LLM engagement advisory
           -> aggregate -> persist moderation_report
              -> hard block  => service.auto_reject -> needs_revision (no human)
              -> clean/repaired => service.submit -> in_review (guardian queue)
```

## 3. State-machine wiring

The `(draft, auto_reject) -> needs_revision` hop already exists in
`publishing/state_machine.py::LEGAL_TRANSITIONS`; slice 1 built it deliberately with no caller
so this slice could route hard blocks. `publishing/service.py` has `submit`, `approve`,
`send_back`, `archive` but **no `auto_reject` wrapper**. This slice adds one:

```python
async def auto_reject(session: AsyncSession, storybook: Storybook) -> None:
    """Route a hard-blocked story to needs_revision without human review.

    Driven by the slice-2 moderation pipeline on a Stage-0 bright-line hit or a
    Stage-1 ``block``. No principal: the rejector is the machine, not a guardian.
    """
    # #CRITICAL: security: this is the machine-side rejection path; it must never
    # set status="published" and must only fire on a recorded hard-block finding.
    # #VERIFY: pipeline calls auto_reject only when moderation_report has a block.
    storybook.status = assert_transition(storybook.status, "auto_reject")
    await session.flush()
```

`submit` already accepts a `draft` story, so the clean/repaired path reuses it unchanged. The
orchestrator's internal `GenerationResult.status == "needs_review"` string is a separate
vocabulary (a generation outcome, not a `storybook.status`); the pipeline does not touch it.

## 4. Module structure

New package `src/cyo_adventure/moderation/`:

| File | Responsibility |
|------|----------------|
| `__init__.py` | Public surface: `run_moderation_pipeline`, `ModerationReport`. |
| `pipeline.py` | Orchestration: run stages in order, short-circuit on hard block, aggregate findings, drive `service.submit` / `service.auto_reject`, persist `moderation_report`. |
| `classifiers.py` | Stage 0 adapters: OpenAI Moderation (`omni-moderation-latest`) and Google Perspective. Each returns findings or skips if its key is unset. |
| `review_provider.py` | `ReviewProvider` protocol mirroring `GenerationProvider`; `build_review_provider(settings, *, generator_backend, generator_model)` enforcing reviewer independence; wraps every provider in `PiiGuardedProvider`. |
| `stages.py` | The four LLM stages (safety, readability, coherence, engagement): prompt construction and verdict parsing. |
| `report.py` | Finding dataclass, severity/verdict enums, aggregation into the persisted report shape. |

Edits: `core/config.py` (classifier + review-provider settings), `publishing/service.py`
(`auto_reject`), and the orchestrator/worker seam that invokes the pipeline after a clean gate
result. `.env.example` reconciles the duplicate `OPENAI_API_KEY` (it appears at both line 76 and
in the later added block).

## 5. The five stages

### Stage 0: classifier pre-filter (deterministic)

Run OpenAI Moderation (`OPENAI_API_KEY`) and Google Perspective (`PERSPECTIVE_API_KEY`) over
each node's prose. Categories split by role (the section-4.1 table is the starting map, verified
against live API responses at integration time, RAD external-resource):

- **Hard-block categories** (any band): OpenAI `sexual`, `sexual/minors`, `self-harm/instructions`,
  `self-harm/intent`, `illicit/violent`, `hate/threatening`, `harassment/threatening`; Perspective
  `SEXUALLY_EXPLICIT`. A hit routes straight to `auto_reject` with no LLM spend.
- **Graded categories**: violence, non-instructional self-harm, hate/harassment, toxicity,
  profanity. These do not auto-block; their scores are passed forward as inputs to Stage 1.

Each classifier result becomes a finding `(source, category, score, node_id)`.

**Configuration posture (decision):** at least one classifier is required in **all**
environments. A single missing key skips only that classifier; if **both** `OPENAI_API_KEY` and
`PERSPECTIVE_API_KEY` are unset, the pipeline raises `ConfigurationError` at startup,
everywhere. There is no environment in which generated children's content reaches review with
zero deterministic pre-filtering.

### Stage 1: safety and age-policy review (LLM, hard gate)

An independent LLM reviewer takes each node's prose plus the Stage-0 graded signals plus the
`band_profile` ceilings (`content_ceiling`, `forbidden_ending_kinds`, and the structural bounds
on the `BandProfile` dataclass), and returns a per-node verdict (`safe` / `flag` / `block`). It
scores against the band's content ceiling and applies a small set of values red-lines for
children's content (cruelty rewarded as the "good" outcome; self-harm or dangerous real-world
acts modeled as achievable), the age-relative judgment a fixed-taxonomy classifier cannot make.
Any `block`, or an unresolved `flag`, forces human review. This is the only hard safety gate;
nothing here can auto-publish.

### Stage 2: age-fit and readability (LLM, soft gate)

Vocabulary, sentence complexity, and thematic maturity fit. **Reading-level source correction:**
the deterministic RL-13 validator (`validator/reading_level.py`) already computes Flesch-Kincaid
grade per node against `story.metadata.reading_level.target ± tolerance`. Stage 2's LLM pass is
**additive** to RL-13 and uses the same `metadata.reading_level.target` source, not a
`band_profile.reading_level_cap` field. That field does not exist on `BandProfile`;
`reading_level_cap` exists only as a column on `ChildProfile`. The Phase 3 design's section 4.3
and 4.8 references to `band_profile.reading_level_cap` are errors corrected here. Reading level
is a quality property, not a safety property, so a far-off result is a soft gate: one bounded
auto-repair pass, then surface to the guardian.

### Stage 3: narrative and branch coherence (LLM, soft gate)

The CYO keystone review. Across all paths: plot, character, setting, and tracked state stay
consistent; each choice's stated consequence follows; no branch contradicts an earlier passage;
every ending is reachable in tone for the path that led to it. The deterministic Layer-2
validator proves the graph is structurally sound (reachable, terminating, no traps); this stage
judges whether the prose is semantically coherent across that graph. Severe incoherence is a
soft gate (auto-repair once, then surface); minor inconsistencies are flagged.

### Stage 4: engagement, choice quality, and voice (LLM, advisory)

Are choices meaningful, distinct, and consequential; is pacing and stakes appropriate for the
band; does the prose read as written-for-children rather than generic AI boilerplate. Advisory
to the guardian; may feed a regeneration request but never gates on its own.

## 6. Aggregation, gating, and remediation

All five stages append to one findings list persisted on `storybook_version.moderation_report`
(the column already exists; **no migration**). Gating by stage role:

- **Hard safety gate.** Stage 0 bright-line hit **or** Stage 1 `block` => `service.auto_reject`
  to `needs_revision` immediately, no human spend.
- **Soft quality gates.** Stage 1 `flag`, Stage 2 far-off reading level, or Stage 3 severe
  incoherence => one bounded auto-repair pass (reuse the orchestrator's existing 3-attempt cap
  and no-progress abort), then `service.submit` to `in_review` with findings attached.
- **Advisory.** Stage 4 findings and minor Stage 2/3 flags never gate; they ride in the report.
- A clean or repaired story is `submit`-ed to `in_review`, never `published`. The guardian is
  always the final gate (ADR-005); the pipeline only decides what to surface and pre-flag.

One finding shape:
`{ stage, source: openai|perspective|llm_safety|llm_readability|llm_coherence|llm_engagement, category, score|severity, node_id, verdict: block|flag|advisory|pass, message }`.

## 7. Review provider abstraction and independence

The four LLM stages run behind a `ReviewProvider` protocol mirroring `GenerationProvider`
(`async def complete(self, *, system: str, prompt: str, max_tokens: int) -> str`). Backends:
**local Ollama, OpenRouter, and Modal** (Modal.com serverless GPU auto-endpoints, as in
`2026-06-23-modal-generation-tiers-design.md`). No direct Anthropic/Gemini/Perplexity adapters
this slice.

`build_review_provider` enforces **reviewer != generator** (decision: prefer-different,
degrade-with-warning):

1. Prefer a **different backend** from the generator (compared against `storybook_version.model`
   and `generation_job.provider` / `.model`, both of which exist on the models).
2. If no different backend is configured, prefer a **different model on the same backend**.
3. As a last resort, allow the same model but emit a loud `reviewer_not_independent` finding into
   `moderation_report` so the guardian knows the review was not independent.

Every review prompt flows through the existing PII egress guard (`generation/guarded.py`) before
any external call, exactly as generation does. The reviewer is constructed already wrapped in
`PiiGuardedProvider`.

```python
# #CRITICAL: security: a model reviewing its own output is not an independent check;
# build_review_provider must never silently return the generator's exact backend+model.
# #VERIFY: when forced to reuse, a reviewer_not_independent finding is recorded.
```

## 8. Configuration additions (`core/config.py`)

New Settings fields (none exist today):

- `openai_api_key: str | None` (validation alias `OPENAI_API_KEY`) — Stage 0 OpenAI Moderation.
- `perspective_api_key: str | None` (validation alias `PERSPECTIVE_API_KEY`) — Stage 0 Perspective.
- `review_provider: Literal["mock", "ollama", "openrouter", "modal"]` — review backend selector,
  defaulting to a mock for tests (mirrors `generation_provider`'s `"mock"` default).
- Review model fields per backend (review-side analogues of `openrouter_model` / `ollama_model`)
  and Modal endpoint config.

A startup validator enforces the Stage-0 posture: `ConfigurationError` if both classifier keys
are unset. The `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `PERPLEXITY_API_KEY` keys in `.env.example`
are documented future hooks and are **not** added as Settings fields this slice.

## 9. Testing strategy

- **Stage 0 classifiers** (`classifiers.py`): unit tests with stubbed HTTP, Docker-independent.
  Bright-line hit => hard-block finding; graded => forwarded score; missing one key => skip;
  both keys missing => `ConfigurationError`.
- **Review provider independence** (`review_provider.py`): unit tests for all three independence
  tiers, including the `reviewer_not_independent` finding on forced reuse.
- **Pipeline orchestration** (`pipeline.py`): unit tests with stubbed stages proving the gating
  matrix (hard block => `auto_reject`; soft fail => one repair then `submit`; clean => `submit`),
  Docker-independent, asserting the resulting `storybook.status` and `moderation_report`.
- **State machine** (`service.auto_reject`): unit test for the legal hop and the illegal-state
  raise, matching the slice-1 service test pattern.
- **PII guard**: assert review prompts are routed through `assert_prompt_pii_safe` before any
  external call.
- Declare the new modules in `[tool.test-coverage-agent] critical_modules`, consistent with
  slice 1. Coverage stays at or above the 80% gate; targeted unit coverage of the new safety
  modules is Docker-independent.

## 10. Resolved decisions and remaining integration-time questions

**Resolved (brainstorming 2026-06-30):** full five-stage scope; classifier required in all
environments (both keys missing => `ConfigurationError`); reviewer independence
prefer-different-degrade-with-warning; review backends via OpenRouter + Ollama + Modal;
reading-level source corrected to `metadata.reading_level.target ± tolerance` additive to RL-13;
`moderation_report` and `model` columns already exist (no migration); duplicate `OPENAI_API_KEY`
in `.env.example` reconciled.

**Deferred to integration time (RAD external-resource, verify against live APIs):**

1. Exact OpenAI/Perspective category-to-dimension thresholds (the section-5 map is the starting
   point; confirm against real classifier responses).
2. Exact Flesch-Kincaid tolerance bands per reading-level target for Stage 2's LLM pass relative
   to RL-13's existing tolerance.
3. Modal review-endpoint provisioning specifics (model image, cold-start budget), aligned with
   the Modal generation-tiers design.

## 11. Out of scope

Slice 3 (guardian review-surface read API), Phase 4a (guardian review UI), the
reading-state-validation slice (red-team Finding 2), direct Anthropic/Gemini/Perplexity review
adapters, and any change to the deterministic gate's structural or policy layers.
