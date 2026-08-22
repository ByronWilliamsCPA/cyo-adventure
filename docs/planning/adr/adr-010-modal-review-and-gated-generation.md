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
   > **Superseded 2026-08-22**: see the
   > [2026-08-22 amendment](#amendment-2026-08-22-modal-is-cascade-leg-3-not-primary)
   > below. Modal is now cascade leg 3 in production whenever `MODAL_BASE_URL` and
   > `MODAL_MODEL` are both set; it is no longer offline-only, and the promotion gate in
   > Decision 3 below governs only the primary role, not this backstop one.
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

## Amendment (2026-08-22): Modal is cascade leg 3, not primary

### What changed

Modal generation is no longer an offline-only experiment. `build_provider`
(`generation/provider.py`) includes Modal as the fallback cascade's **leg 3**, ranked after
both OpenRouter legs, whenever `settings.modal_leg_configured` is true (both
`MODAL_BASE_URL` and `MODAL_MODEL` set); when it is not set, the cascade degrades to the
two OpenRouter legs and logs `generation.cascade_single_vendor` at WARNING. This is the
same change ADR-003's [2026-08-18 amendment][adr003-amend] records: that amendment
retires the local Ollama leg (which this ADR's original text never mentions, since Ollama
had not yet been superseded when this ADR was written) and puts Modal in the vacated
third-leg slot.

[adr003-amend]: ./adr-003-frontier-llm-generation.md#amendment-2026-08-18-the-ollama-leg-is-retired-and-modal-takes-leg-3

### The promotion gate is retired for the backstop role, not for primary

Decision 3 above sets a gate for making Modal **generation primary**: a 20-brief yield
harness re-run clearing >=60% overall with Tier-2 no worse than the incumbent, plus an
accepted measured cost per accepted story. That gate is unmet, and nothing here claims
otherwise. What changed is the role Modal now occupies without having cleared it:
**backstop**, not **primary**. A leg that receives traffic only after both OpenRouter
legs have already failed carries a materially different risk posture than a leg serving
every request: cascade-wide yield exposure to Modal's own quality is bounded by how often
both OpenRouter legs fail together, not by Modal's per-story success rate against the
full request population. Retiring the gate for this narrower backstop role is therefore
not the same claim as clearing it for primary. **If Modal is ever proposed as primary,
Decision 3's yield and cost bars still apply in full and remain outstanding**; this
amendment does not touch them.

### What is not yet satisfied

Two gaps, recorded honestly rather than closed by assertion:

- **No Modal pricing row exists in `core/pricing.py`, and this is deliberate rather than a
  simple omission.** Modal Auto Endpoints bill GPU-seconds for a rented container, not
  tokens against a published per-MTok rate, and a Modal response carries no `cost` field,
  so there is no vendor figure to record and no derived guess belongs in a table whose
  value is that every row is dated and sourced. `price_for("modal", ...)` therefore
  returns `None`, and a Modal-served completion reports `CostEstimate(complete=False)`.
  That is the correct, honest answer while true GPU-second cost per accepted story is
  unmeasured; it is not scheduled to close in this change set, and closing it properly
  means recording measured Modal billing data first.
- **`generation/providers/modal.py`'s handling of `finish_reason` is being brought in
  line with the OpenRouter adapter in this same change set**, so a `length` stop is
  marked `leg_fatal` the same way it already is on the OpenRouter legs. Confirm this
  landed before treating it as closed; it was still in progress as this amendment was
  written.

### Amendment direction, stated both ways

This ADR's header records "Amends: ADR-003". ADR-003's 2026-08-18 amendment now
supersedes this ADR's Decision 2 ("offline experiments only") and narrows Decision 3's
promotion gate to the primary role only, as described above. Read together: ADR-003
amends this ADR on that point, and this ADR continues to amend ADR-003 on every other
point it originally addressed (the review backend, the vendor-minimization framing).
Neither document silently governs the other's every claim after this pair of edits; each
amendment states which of the other's claims it changes.

### Status unchanged

This ADR's `status: proposed` frontmatter is not changed by this amendment. This
amendment records what has already shipped despite that status; it does not itself
promote the ADR to Accepted.

### Related

- [ADR-003](./adr-003-frontier-llm-generation.md#amendment-2026-08-18-the-ollama-leg-is-retired-and-modal-takes-leg-3):
  the amendment this one is the ADR-010 side of.
- [ADR-004](./adr-004-homelab-first-deployment.md#amendment-2026-08-22): the
  homelab-to-Vultr move that is why the Ollama leg needed retiring at all.
