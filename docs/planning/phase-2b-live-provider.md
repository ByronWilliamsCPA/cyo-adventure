---
title: "Phase 2b: Live Provider Wiring and Generation Yield"
schema_type: planning
status: published
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

## Status: Delivered (2026-06-29)

Both acceptance criteria below are **met**, and the work package is closed:

- **Live adapters shipped** (PRs #7, #8): OpenRouter as primary with an in-provider
  fallback model, and Ollama as the homelab final fallback, both selectable purely by
  `settings.generation_provider`. The direct Anthropic SDK adapter remains intentionally
  deferred (Claude is reached via OpenRouter).
- **Yield met at 70% (14/20)** on a live OpenRouter run (`anthropic/claude-haiku-4.5`,
  2026-06-22), clearing the 60% threshold. Result recorded under
  [`yield-results/phase-2b-2026-06-22.json`](./yield-results/phase-2b-2026-06-22.json).

**Carried-forward lever (not blocking):** the run split **Tier-1 11/13 vs Tier-2 3/7**.
The dominant Tier-2 failure was L1-7 "budget" (branch depth over the band cap, ending
count off-brief). Tightening the Stage A structure prompt to state band budgets inline
and numerically (the highest-leverage, model-independent fix described under In Scope
below) is the open follow-up, tracked as GS1 in
[`r1-deferred-debt-register.md`](./r1-deferred-debt-register.md), not a Phase-3 blocker.

The remainder of this document is the original work-package specification, retained for
provenance.

## Purpose

Phase 2 delivered the `GenerationProvider` protocol, the staged orchestrator, the mock-driven
yield harness, and all backend scaffolding for async generation. Two acceptance criteria were
deliberately deferred because they require a live LLM provider:

1. Concrete HTTP-client adapters for OpenRouter (primary), Ollama, and Claude via OpenRouter
   (direct Anthropic SDK adapter deferred; see the amendment above and the In Scope section
   below).
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

- Implement `complete()` for two live providers behind the existing `GenerationProvider`
  protocol (primary/fallback roles per ADR-003 as amended 2026-06-22):
  - **OpenRouter** (HTTP, primary): target the model specified by `settings.openrouter_model`,
    with `settings.openrouter_fallback_model` as the in-provider fallback. Claude is reached
    here (`anthropic/claude-sonnet-4.6`); there is no separate Anthropic SDK adapter.
  - **Ollama** (local P40, final fallback): target the model specified by `settings.ollama_model`.
  - A direct **Anthropic SDK** adapter is **deferred** (out of scope below): the operator routes
    Claude through OpenRouter, so the standalone SDK path is unnecessary now. The seam remains for
    a trivial future add (direct Opus 4.8 + prompt caching) if a billed Anthropic account is used.
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
- Run `scripts/yield_harness.py` against the live OpenRouter adapter over a 20-story sample and
  record the result.
- **Tighten the Stage A structure prompt's budget constraints.** The 2026-06-22 probe found the
  dominant yield failure is L1-7 "budget" (`branch_depth` over the band cap, `ending_count` not
  matching the brief): the structure prompt defers these numbers to the injected drafting guide
  instead of stating them inline. State the hard band budget numerically and prominently (max
  branch depth, min/max nodes from `band_profile.py`'s band table (the single source of truth
  under ADR-011; `layer1` now delegates to it), and "produce exactly `ending_count`
  endings"). This is the highest-leverage yield lever and is model-independent. Document the
  change in the harness output per the out-of-scope note below.

### Out of scope

- Changes to the orchestrator, validator, or PII guard logic.
- New story-format features or schema changes.
- Prompt-template authoring (templates ship in Phase 2; adjust them only if yield measurement
  reveals a systematic failure pattern, and document the change in the harness output).
- Provider billing, quota, or rate-limit dashboards (operational concern, not code).
- The direct **Anthropic SDK** adapter: deferred. Claude is reached via OpenRouter
  (`anthropic/claude-sonnet-4.6`); a standalone SDK path is unnecessary while the operator routes
  Claude through OpenRouter. Revisit only if a billed Anthropic account is used directly.

---

## Acceptance Criteria

Both criteria must be met for this work package to close Phase 2 fully:

1. **Provider swap is a config change only.** Setting `settings.generation_provider` to
   `openrouter` or `ollama` selects the corresponding adapter with no code changes (the
   `claude` value stays in the enum for the deferred direct-Anthropic adapter and raises
   `ConfigurationError` until that adapter is implemented). The orchestrator, harness, and API
   endpoints are unaffected.

2. **Generation yield at least 60% over a 20-story sample.** Running
   `scripts/yield_harness.py --briefs <20-brief sample>.json --provider openrouter --threshold 0.60`
   against the live OpenRouter adapter (the primary per ADR-003 as amended 2026-06-22; model
   pinned via `settings.openrouter_model`; the sample size is the number of briefs in the file)
   produces a pass rate at or above 60% (stories that pass the full validation gate with zero
   structural edits, prose-only tweaks allowed). The harness output is committed to
   `docs/planning/yield-results/phase-2b-YYYY-MM-DD.json`. Run debug iterations against a
   `:free` model (e.g. `google/gemma-4-31b-it:free`) so paid measurement is a few confirmation
   runs only.

---

## Key Constraints and Guidelines

- **ADR-003** governs provider selection rationale and the interface contract. Any deviation
  from the interface requires an ADR amendment before implementation.
- **Timeout defaults**: 120 s per `complete()` call; configurable via
  `settings.llm_timeout_seconds`.
- **Retry policy**: 3 attempts with exponential backoff (2 s, 4 s, 8 s); on exhaustion, raise
  `ProviderError` and let the orchestrator route to `needs_revision`.
- **Unavailable-model fallback (OpenRouter roster churns weekly)**: the adapter MUST map an
  "invalid model" response (HTTP 400/404) to `ProviderError`, and `build_provider` cascades
  `openrouter_model` -> `openrouter_fallback_model` -> `ollama` so a vanished pinned model is a
  fallback trigger, not a crash. Pin first-party families (Anthropic, Google) that survive churn.
- **OpenRouter free-tier limits**: `:free` models allow 20 req/min and 50 req/day under $10 of
  purchased credits (1,000/day at >=$10). A 20-story run is ~100 calls, so a one-time $10 top-up is
  required to complete a free-model run in a day; reserve free models for debug iterations.
- **Acceptable model families (minors' content, ADR-004)**: production generation routes only to
  providers with a defensible data policy (Anthropic, Google); other OpenRouter labs are for
  local/free experimentation only.
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
