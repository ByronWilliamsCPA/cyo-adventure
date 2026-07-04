---
title: "ADR-010: Modal for moderation review and an evidence-gated generation leg"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Record the decision to build the deferred slice-2b moderation review backend on
  Modal, add a Modal-served generation leg behind the GenerationProvider seam as an
  experiment, and promote it to primary only if it clears the yield gate at acceptable
  cost per story."
tags:
  - planning
  - architecture
  - decisions
  - generation
  - moderation
---

# ADR-010: Modal for moderation review and an evidence-gated generation leg

> **Status**: Proposed
> **Date**: 2026-07-02
> **Amends**: [ADR-003](./adr-003-frontier-llm-generation.md) (provider strategy: adds a
> self-hosted review backend and an experimental generation leg; the frontier-primary
> decision stands until the promotion gate below is cleared)

## TL;DR

Build the moderation review backend (already reserved as `review_provider = "modal"`,
deferred at slice 2b) on Modal-served open-weight models, and add a `ModalProvider`
generation leg behind the existing `GenerationProvider` seam to test vLLM
guided/constrained decoding against the known Tier-2 structural failures. OpenRouter
(Claude) remains the generation primary; the Modal leg is promoted to primary only if it
clears the existing 20-brief, >=60% yield gate at an acceptable measured cost per story.

## Context

Modal offers arbitrary code at the inference endpoint (any open-weight model, vLLM
guided decoding that can force schema-valid JSON at the decoder level) and volume-cached
model weights for tolerable cold starts. Two facts frame how to use that:

- **The generation primary is measured, not assumed.** Phase 2b recorded 70% yield
  (14/20) on `anthropic/claude-haiku-4.5` via OpenRouter at cents per story, with
  Tier-2 the residual weakness (3/7, structural failures). Replacing a measured
  primary with self-hosted open weights re-opens the yield question and makes a solo
  operator the inference owner on the revenue path, against ADR-009's
  minimize-operations thesis. Self-hosted GPU-seconds per story also plausibly cost
  10-50x Haiku's token bill, and generation is metered revenue (credit packs), so cost
  per story is margin.
- **The review leg is where self-hosting is a design win.** The reviewer should be a
  different model family than the generator (independent blind spots); review is
  bursty, suiting scale-to-zero serverless GPU; quality demands are lower than
  generation; and self-hosting means no additional third-party model vendor ever sees
  children's content in review, strengthening the privacy-model posture. The config
  seam for this already exists and currently raises as deferred.

## Decision

1. **Moderation review backend on Modal (executes the deferred slice 2b).** Implement
   the `review_provider = "modal"` backend in `moderation/review_provider.py` against a
   Modal-served open-weight reviewer; weights prestaged on a Modal volume. The
   OpenRouter reviewer remains the configured fallback. Stage-0 deterministic
   classifiers stay mandatory (existing config invariant).
2. **Experimental `ModalProvider` generation leg, not on the public path.** A new
   adapter behind `GenerationProvider`, using vLLM guided decoding targeted at the
   Tier-2 structural failure modes. It runs offline experiments only.
3. **Promotion gate.** The Modal leg may become generation primary only after: (a) the
   20-brief yield harness re-run clears >=60% overall with Tier-2 no worse than the
   incumbent, and (b) measured cost per accepted story is recorded and accepted against
   credit-pack pricing. Promotion itself is a config change (`generation_provider`),
   per ADR-003's config-pinned model policy.
4. **Worker hosting**: Modal is a candidate, alongside the container host, in the
   time-boxed P9-03 evaluation. No commitment now.

## Consequences

- ✅ Reviewer independence and child-content privacy improve; the Tier-2 yield lever
  gets a real experiment with decoder-level structure enforcement.
- ✅ The revenue path keeps its measured 70% provider until evidence says otherwise.
- ⚠️ Modal is a second serverless vendor. Mitigation: review usage is bursty (near-zero
  idle cost), and the OpenRouter reviewer fallback covers Modal outages.
- ⚠️ The experiment can stall without a deadline. Mitigation: it is explicitly
  non-blocking for launch; it lives in the post-launch backlog with the gate attached.

## Validation

- [ ] Modal review backend passes the moderation pipeline integration tests and runs in
      production config with the OpenRouter reviewer as fallback.
- [ ] Yield harness re-run recorded under `docs/planning/yield-results/` for any
      promotion decision, with cost per accepted story.
- [x] Generation leg smoke test: `ModalProvider` deployed against a live Modal Auto
      Endpoint (Standard tier, `google/gemma-4-26B-A4B-it`) and exercised end to end with
      one real 8-11-band brief. Result recorded at
      `docs/planning/yield-results/modal-standard-smoke-test.json` (2026-07-04): 1/1 story
      passed all gates, 100% pass rate, 25.5s latency. This is one measured data point
      toward the promotion gate above, not the gate itself; the endpoint was stopped
      immediately after the test to halt billing.

## Related

- [ADR-003](./adr-003-frontier-llm-generation.md): the provider strategy this amends.
- [ADR-009](./adr-009-supabase-platform.md): the vendor-minimization thesis the
  promotion gate protects.
- [Phase 2b results](../phase-2b-live-provider.md): the incumbent yield measurement and
  the Tier-2 residual lever.
