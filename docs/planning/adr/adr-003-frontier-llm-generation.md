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
