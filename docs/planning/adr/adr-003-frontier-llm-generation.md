---
title: "ADR-003: Frontier LLM for generation, local model as fallback"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Record the decision to use a frontier LLM as the primary generator behind a provider-agnostic interface."
tags:
  - planning
  - architecture
  - decisions
---

# ADR-003: Frontier LLM for generation, local model as fallback

> **Status**: Proposed
> **Date**: 2026-06-20

## TL;DR

Use a frontier model (Anthropic Claude) as the primary generator behind a
provider-agnostic interface, with the local stack (Ollama/Tesla P40) and OpenRouter as
fallback and development targets, because frontier models hold branching structure far
better and generation is infrequent enough that API cost is negligible.

## Context

### Problem

Generation quality matters most on the structure-heavy task of branching coherence
with state callbacks and convergence. The available options are a capable local stack
(Tesla P40, Ollama, Qwen3/Gemma), OpenRouter, or a frontier API.

### Constraints

- **Technical**: a 7-to-14B local model is weaker on long-range structure and state.
- **Business**: generation is infrequent (generate a story occasionally, then it is
  static), so per-call cost is small relative to the quality gain. Minors' content is
  involved, so the provider's data handling matters (see ADR-004 and the privacy
  controls).

### Significance

Provider lock-in would be costly, and frontier model names and rankings shift on a
roughly monthly cadence, so the integration must keep swapping cheap.

## Decision

**We will use a frontier model (Anthropic Claude) as the primary generator behind a
`GenerationProvider` interface because branching coherence is where quality matters
most and frontier models hold that structure best.** The local stack and OpenRouter
remain as fallback and development targets inside the same interface.

### Rationale

A branching story with state callbacks and convergence is hard; frontier models hold
that structure far better than a small local model. Because generation is infrequent,
API cost is small relative to the quality gain. The provider interface keeps us free to
switch, and the local path stays useful for cheap iteration and for any story to keep
entirely in-house.

## Options Considered

### Option 1: Frontier API (Claude) primary ✓

**Pros**:
- ✅ Strongest branching coherence; staged prompting works well.

**Cons**:
- ❌ Per-call cost and an external dependency on the primary path.

### Option 2: Local only (Ollama / P40)

**Pros**:
- ✅ Free, fully private.

**Cons**:
- ❌ Weaker on long-range structure and state. Kept as fallback, not primary.

### Option 3: OpenRouter

Model flexibility through one integration, but still external and quality varies by
model. Useful fallback inside the provider abstraction.

## Consequences

### Positive

- ✅ Best story quality where it counts; flexibility retained.

### Trade-offs

- ⚠️ A small recurring cost and an external call for the primary path. Mitigation: a
  per-family generation quota and asynchronous, cached generation.

### Technical Debt

- The model id is pinned in configuration, not in code or this spec, so a model swap is
  a config change. Frontier rankings shift monthly; the interface exists precisely for
  this.

## Implementation

### Components Affected

1. **Provider interface**: a `GenerationProvider` abstraction with Claude, Ollama, and
   OpenRouter implementations.
2. **Generation orchestrator**: drives staged passes through the interface.
3. **Configuration**: model id and provider selected per environment.

### Testing Strategy

- Integration: the pipeline with a mocked provider returning canned and deliberately
  malformed outputs, proving the repair loop and no-progress abort.

## Validation

### Success Criteria

- [ ] At least 60% of generated stories pass the full gate with zero structural edits
      over a 20-story sample.
- [ ] A provider swap requires only a configuration change.

### Review Schedule

- Initial: Phase 2 acceptance.
- Ongoing: whenever a stronger or cheaper model appears.

## Related

- [ADR-004](./adr-004-homelab-first-deployment.md): the privacy posture for an external
  generator call.
- [ADR-005](./adr-005-mandatory-human-approval.md): the human gate after generation.
- [Tech Spec: Authoring pipeline](../tech-spec.md#authoring-pipeline-staged-generation)

## Amendment (2026-06-22): OpenRouter primary

The original decision named Anthropic Claude (via the Anthropic SDK, billed to a
dedicated Anthropic API account) as the primary generator. This amendment changes the
primary provider to **OpenRouter** behind the same `GenerationProvider` interface. The
decision driver is access and cost, not quality: the project does not provision a
separate Anthropic API account, and one OpenRouter key reaches many model families
(including free `:free` endpoints and `anthropic/claude-sonnet-4.6`) through a single
integration. The operator holds an Anthropic API key but routes Claude through OpenRouter
generally, so Claude is reached at `anthropic/claude-sonnet-4.6` via OpenRouter, not a
separate SDK adapter. (A claude.ai chat subscription cannot serve API calls and is not a
provider path.)

Revised provider posture:

- **Primary**: OpenRouter (`settings.openrouter_model`); Claude is reached here.
- **Fallback cascade**: on `ProviderError`, route OpenRouter primary model -> OpenRouter
  fallback model (`settings.openrouter_fallback_model`) -> local Ollama. The interface
  already isolates this swap.
- **Deferred**: a direct Anthropic SDK adapter. Not implemented in Phase 2b (OpenRouter
  covers Claude); a trivial future add via the existing seam if direct Opus 4.8 or prompt
  caching without the OpenRouter markup is ever wanted.

### Model availability is weekly-volatile, not monthly

Two snapshots of the OpenRouter roster three days apart (2026-06-19, 2026-06-22) shared
only ~14% of their working model IDs. The "frontier rankings shift monthly" note above
understates it: model IDs appear and disappear weekly. Consequences pinned into scope:

1. Pin **first-party model families** (Anthropic, Google) that survive roster churn, not
   the exotic top-scorers that vanish.
2. The adapter MUST map "model unavailable" (HTTP 400/404 invalid-model) to
   `ProviderError` so the orchestrator treats a vanished model as a fallback trigger, not
   an unhandled crash. This widens the Phase 2b retry policy beyond network failures.

### Minors' content data-handling constraint

Per [ADR-004](./adr-004-homelab-first-deployment.md), the provider's data handling
matters because the app generates children's content. The PII guard
(`generation/pii.py`) strips real-child names before every egress, but the *choice of
OpenRouter model* still has a governance dimension. Acceptable model families for
production generation are limited to those with a defensible data policy (Anthropic,
Google); arbitrary third-party labs on OpenRouter are for local/free experimentation
only, never production.

### Empirical findings (2026-06-22 model probe)

A direct-OpenRouter probe fed the real Stage A/B prompts to four reachable models and
scored outputs with `run_gate`:

- **Free models are viable**: `google/gemma-4-26b-a4b-it:free` produced a complete,
  gate-clean, genuinely safe Tier-1 story in one pass (cost $0).
- **The yield bottleneck is L1-7 "budget", not model quality**: blocked outputs failed on
  `branch_depth` over the band cap of 6 (Sonnet built depth 12) or `ending_count` over the
  brief's value (Qwen made 3 of an asked-for 2). Frontier models overshoot *more* because
  they build richer trees. This is a prompt-constraint fix (state the numeric budget
  inline in the structure prompt), and is the highest-leverage yield lever, independent of
  model choice.
- **Quality vs validity gap**: a four-lens review panel rated the free-model story safe
  (5/5) and structurally valid but narratively bland (narrative 2/5: formulaic prose,
  cosmetic choices, absent protagonist/theme). `run_gate` cannot see this; ADR-005's human
  gate must. Whether a frontier model is materially better on prose quality is untested
  (no frontier model completed a full story in the probe).

### Cost (measured, OpenRouter)

Generation remains negligible: one Sonnet-4.6 Stage-A call billed $0.077; a full clean
story is ~$0.13-0.16 on Sonnet and $0 on free Gemma. Phase 2b completion (debug on free,
measure on a paid model) is well under $20. The schema embedded in every prompt (~5k
tokens) is a static prefix that prompt caching would discount ~90% on the paid path.

### Phase 2b implementation note: R1 prompt restructure (interface-adjacent)

ADR-003 records that deviations from the staged-generation interface require an
amendment. Phase 2b R1 makes one such deviation, approved for this phase, and notes it
here:

- **Budget stated inline (the yield fix).** `build_structure_prompt` now injects the
  brief-specific L1-7 limits (node-count band, max branch depth, exact ending count) into
  the Stage A user block, read from a single source of truth,
  `validator.layer1.band_budget`, so the prompt promises exactly what the gate enforces.
  A 2026-06-22 re-probe confirmed the lift: Sonnet and gemma-4-31b Stage A, previously
  blocked on L1-7 budget overshoot, now pass the budget dimension cleanly.
- **System/user split for prompt caching.** The three stage builders now return a
  `StagePrompt(system, user)`: static reference content (role, JSON Schema, drafting
  guide, fixed instructions) sits in the cacheable `system` block, and per-job volatile
  content (brief, budget, skeleton, repair payload) sits in the `user` block. The
  orchestrator forwards these to the unchanged `GenerationProvider.complete(system,
  prompt)` protocol, and the PII guard now runs on both blocks before egress. This
  positions the static schema (~5k tokens) for the Anthropic `cache_control` discount the
  cost section anticipates, without changing the provider protocol.
