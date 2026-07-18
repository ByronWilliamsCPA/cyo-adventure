---
title: "Generation Pipeline"
schema_type: common
status: published
owner: core-maintainer
purpose: "Architecture of the staged LLM story generation pipeline with provider fallback."
tags:
  - architecture
  - automation
---

CYO Adventure generates stories through a three-stage pipeline that turns a
`ConceptBrief` (built at the guardian cost gate from a child wish, a guardian brief, or
an admin catalog seed) into a validated `Storybook` JSON document.
The pipeline runs asynchronously in an RQ worker process so long-running LLM
calls do not block the API.

## Component View

![Generation Pipeline Components](diagrams/component-generation.svg)

## Generation Sequence

The sequence below traces the full lifecycle from a guardian POST to job completion,
matching the `generate_story()` docstring in `generation/orchestrator.py` exactly.

![Generation Sequence](diagrams/seq-generation.svg)

## Stage Pipeline (Structure -> Prose -> Repair)

The orchestrator (`generation/orchestrator.py`) drives three stages:

### Stage A: Structure

1. `build_structure_prompt(brief)` assembles a `StagePrompt` (system + user blocks).
2. `assert_prompt_pii_safe()` runs on **both** blocks before any external call. A real
   child's display name in the brief text aborts generation with `ValidationError`;
   the provider is never called.
3. `provider.complete()` calls the LLM (via `FallbackProvider`).
4. `json.loads(raw)` parses the response; a non-dict or parse error synthesizes a
   blocked gate result (`L1-1` finding) without raising.
5. `run_gate(doc)` validates the structure.

If Stage A is **blocked**: skip Stage B and go directly to the repair loop.
If Stage A is **clean**: proceed to Stage B.

### Stage B: Full Prose

Same flow as Stage A but using `build_prose_prompt(skeleton_json, brief)` and a higher
`max_tokens` ceiling (32,000). The Stage A skeleton is passed so the LLM expands it
with full narrative prose without restructuring the graph.

### Stage C: Bounded Repair Loop

While the gate is blocked and `attempts < max_repairs` (default 3):

1. `build_repair_prompt(current_json, failing_findings)` targets the ERROR-severity
   findings by rule ID and message.
2. PII guard runs again.
3. `provider.complete()` returns a repaired document.
4. Gate runs on the new document.
5. **No-progress check**: if the set of ERROR findings AND the SHA-256 hash of the
   document are identical to the previous attempt, further repairs cannot help and the
   loop aborts early (`repair:no_progress_abort`).

### Outcome Mapping

| Gate result | Doc present | Outcome |
|-------------|-------------|---------|
| clean, not safety_flagged | yes | `"passed"` |
| clean, safety_flagged | yes | `"needs_review"` |
| blocked after exhausting repairs | yes | `"needs_review"` |
| blocked, no doc produced | no | `"failed"` |

## Skeleton Fill (alternate method)

Fresh three-stage generation (`generate_story()`) is one of two methods. The other,
`fill_skeleton()` (`orchestrator.py`, driven by `worker.py::_run_skeleton_fill`), fills a
pre-authored skeleton library file's `<<FILL ...>>` directives instead of building a
story graph from scratch. It runs its own bounded Stage-1 fidelity gate and repair loop
(a fidelity violation downgrades the outcome), then hands off to the same validator gate
and the same outcome mapping above. The worker selects the method per job; the cell-aware
skeleton *selection* happens earlier, at plan time in
`story_requests/authoring_plan.py`. A `mechanism="skill"` skeleton-fill job is parked at
`awaiting_manual_fill` for an offline human/skill fill and resumed later via
`generation/import_story.py`. See
[component-generation](diagrams/component-generation.svg) for both methods.

## Provider Fallback Cascade

The provider is a three-layer failure model:

**Layer 1 (per adapter):** Each `OpenRouterProvider` or `OllamaProvider` retries
transient failures (connection errors, HTTP 429, HTTP 5xx) against the **same** model
with exponential backoff. Leg-fatal errors (HTTP 400/401/402/403/404 for OpenRouter, where
404 is a churned/unavailable model, the case the fallback leg exists for) are not retried.

**Layer 2 (`FallbackProvider`):** The cascade holds an ordered list of legs. On a
`ProviderError` from one leg, it fails over to the next. Leg-fatal errors mark the
leg dead for the rest of the run (circuit breaker). A global per-run attempt cap
(default 30) prevents pathological retry storms.

**Layer 3 (orchestrator repair loop):** A gate-blocked but valid response is a
**content** failure, not a provider failure. The repair loop handles it; `FallbackProvider`
never sees it as an error.

**PII invariant:** The orchestrator wraps the resolved provider in a
`PiiGuardedProvider` (`generation/guarded.py`), so `assert_prompt_pii_safe()` runs on the
prompt blocks of every `complete()` call structurally, not as a separate orchestrator
step. A `ValidationError` from the PII guard propagates straight through
`FallbackProvider` uncaught (only `ProviderError` is caught). This means a PII violation
can never be retried or failed over.

## Guardian-Only Authoring Endpoints

The generation router exposes six endpoints. Five require the guardian role
(`POST /concepts`, `POST /concepts/{id}/generate`, `GET /generation-jobs`,
`GET /generation-jobs/{id}`, `POST /storybooks/{id}/versions/{v}/validate`); a sixth,
`POST /admin/generation-jobs/{id}/force-fail`, requires the admin capability. On
`GET /generation-jobs/{id}` the raw validator report is returned only to admins (a plain
guardian sees `report=null`). Child tokens receive 403 before any DB access.

**Family cost gate (ADR-015).** Before any spend, `enqueue_concept_generation` calls
`enforce_family_quota`: the family's monthly count of `approved` story requests is checked
against `family.monthly_story_quota` (platform default when NULL) and a 409 is returned
when it is exceeded; admins bypass the gate (platform budget). A
`MAX_ACTIVE_JOBS_PER_FAMILY = 2` throttle bounds concurrent jobs. The same gate guards the
`approve_story_request` and authored-request paths.

`POST /concepts` screens the brief text for real child display names (fetched from
`child_profile.display_name` for the family) before persisting the `Concept` row.

`POST /concepts/{id}/generate` creates a `GenerationJob` row (`status='queued'`) and
schedules a **background task** to enqueue it on Redis. Running the enqueue after the
commit ensures the worker never races a not-yet-durable row. If Redis is unreachable,
the row is still created and a 202 is returned (the job can be recovered by a sweeper).

## Key Source Files

| File | Purpose |
|------|---------|
| `src/cyo_adventure/generation/orchestrator.py` | `generate_story()` (three-stage) + `fill_skeleton()` (skeleton method) |
| `src/cyo_adventure/generation/prompts.py` | `build_structure/prose/repair_prompt()` |
| `src/cyo_adventure/generation/pii.py` | `assert_prompt_pii_safe()`, `PiiContext` |
| `src/cyo_adventure/generation/guarded.py` | `PiiGuardedProvider` (structural PII wrapper) |
| `src/cyo_adventure/generation/providers/fallback.py` | `FallbackProvider` cascade |
| `src/cyo_adventure/generation/providers/openrouter.py` | OpenRouter adapter (Layer 1) |
| `src/cyo_adventure/generation/providers/ollama.py` | Ollama adapter (Layer 1) |
| `src/cyo_adventure/generation/queue.py` | `enqueue_generation()` |
| `src/cyo_adventure/generation/worker.py` | RQ worker entry point |
| `src/cyo_adventure/api/generation.py` | API routers: concepts, jobs, validate |
| `src/cyo_adventure/generation/concept.py` | `ConceptBrief` Pydantic model |

## Related ADRs

- ADR-003: [Frontier LLM Story Generation](../planning/adr/adr-003-frontier-llm-generation.md)
- ADR-005: [Mandatory Human Approval](../planning/adr/adr-005-mandatory-human-approval.md)
- ADR-006: [Conditions: In-House Evaluator](../planning/adr/adr-006-conditions-inhouse-evaluator.md)
