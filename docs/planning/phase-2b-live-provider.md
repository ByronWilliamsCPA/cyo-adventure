---
title: "Phase 2b: Live Provider Wiring and Generation Yield"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Implement the live GenerationProvider adapters and measure real generation yield,
  closing the two acceptance criteria deferred from Phase 2."
tags:
  - planning
  - phase-2b
  - generation
component: Generation
source: "Deferred from Phase 2 (feat/phase-2-generation-gate) decision, 2026-06-22"
---

## Purpose

Phase 2 delivered the `GenerationProvider` protocol, the staged orchestrator, the mock-driven
yield harness, and all backend scaffolding for async generation. Two acceptance criteria were
deliberately deferred because they require a live LLM provider:

1. Concrete HTTP-client adapters for Claude (primary), Ollama, and OpenRouter.
2. Measured generation yield of at least 60% over a 20-story sample against a live provider.

This document defines the scope, acceptance criteria, and key constraints for the follow-up
work package that closes those two items.

---

## Existing Seams (what Phase 2 already ships)

All of the following are in place and must not be changed by this work package except through
the defined extension points:

| Seam | Location | Notes |
|------|----------|-------|
| `GenerationProvider` protocol | `src/cyo_adventure/generation/provider.py` | Defines `complete(prompt, ...)` |
| `build_provider` factory | `src/cyo_adventure/generation/provider.py` | Currently raises `ConfigurationError` for any non-mock provider |
| `settings.generation_provider` | `src/cyo_adventure/core/config.py` | Config key that selects the active provider |
| Staged orchestrator | `src/cyo_adventure/generation/orchestrator.py` | Provider-agnostic; calls `provider.complete()` |
| PII egress guard | `src/cyo_adventure/generation/pii.py` (`assert_prompt_pii_safe`) | Must run before every provider call |
| Yield harness | `scripts/yield_harness.py` | Accepts `--provider` flag; swap the provider and re-run |

---

## Scope

### In scope

- Implement `complete()` for three providers behind the existing `GenerationProvider` protocol:
  - **Claude** (Anthropic SDK, primary): target the model specified by `settings.llm_model`.
  - **Ollama** (local P40, fallback): target the model specified by `settings.ollama_model`.
  - **OpenRouter** (HTTP fallback): target the model specified by `settings.openrouter_model`.
- Wire `build_provider` so that `settings.generation_provider` returns the correct live adapter
  instead of raising `ConfigurationError`.
- Add network-level concerns per [ADR-003](./adr/adr-003-frontier-llm-generation.md):
  configurable timeout, exponential-backoff retry (max 3 attempts), and a provider-agnostic
  `ProviderError` mapped from HTTP/SDK exceptions.
- Ensure the PII guard (`pii.py`, `assert_prompt_pii_safe`) still runs before every
  `complete()` call; no adapter may call the provider SDK directly without going through the
  guard. The guard is currently a structural convention (all egress flows through the
  orchestrator's `_run_one_stage`); when adding the first live adapter, move or re-assert the
  screen at the provider boundary so a new adapter cannot bypass it.
- Run `scripts/yield_harness.py` against the live Claude adapter over a 20-story sample and
  record the result.

### Out of scope

- Changes to the orchestrator, validator, or PII guard logic.
- New story-format features or schema changes.
- Prompt-template authoring (templates ship in Phase 2; adjust them only if yield measurement
  reveals a systematic failure pattern, and document the change in the harness output).
- Provider billing, quota, or rate-limit dashboards (operational concern, not code).

---

## Acceptance Criteria

Both criteria must be met for this work package to close Phase 2 fully:

1. **Provider swap is a config change only.** Setting `settings.generation_provider` to
   `claude`, `ollama`, or `openrouter` selects the corresponding adapter with no code changes.
   The orchestrator, harness, and API endpoints are unaffected.

2. **Generation yield at least 60% over a 20-story sample.** Running
   `scripts/yield_harness.py --briefs <20-brief sample>.json --provider claude --threshold 0.60`
   against the live Claude adapter (the sample size is the number of briefs in the file)
   produces a pass rate at or above 60% (stories that pass the full validation gate with zero
   structural edits, prose-only tweaks allowed). The harness output is committed to
   `docs/planning/yield-results/phase-2b-YYYY-MM-DD.json`.

---

## Key Constraints and Guidelines

- **ADR-003** governs provider selection rationale and the interface contract. Any deviation
  from the interface requires an ADR amendment before implementation.
- **Timeout defaults**: 120 s per `complete()` call; configurable via
  `settings.llm_timeout_seconds`.
- **Retry policy**: 3 attempts with exponential backoff (2 s, 4 s, 8 s); on exhaustion, raise
  `ProviderError` and let the orchestrator route to `needs_revision`.
- **No PII in prompts**: the PII guard is the enforcement point; adapters must not construct
  prompts independently of the orchestrator.
- **MockProvider remains the default** in CI and local development until
  `settings.generation_provider` is explicitly set to a live value. This prevents accidental
  LLM calls during automated test runs.

---

## Reference

- [ADR-003: Frontier LLM for generation](./adr/adr-003-frontier-llm-generation.md)
- [Phase 2 roadmap entry](./roadmap.md#phase-2-validation-gate-and-authoring-pipeline-4-6-weeks)
- [PROJECT-PLAN.md Phase 2 section](./PROJECT-PLAN.md#phase-2-validation-gate-and-authoring-pipeline-4-6-weeks)
