---
title: "ADR-003: Frontier LLM for generation, local model as fallback"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the decision to use a frontier LLM as the primary generator behind a provider-agnostic interface."
tags:
  - planning
  - architecture
  - decisions
---

# ADR-003: Frontier LLM for generation, local model as fallback

> **Status**: Accepted (2026-07-03; amended 2026-06-22, see Amendment: OpenRouter primary;
> amended 2026-07-28, see Amendment: the production model-family limit is re-scoped)
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
- [ADR-010](./adr-010-modal-review-and-gated-generation.md): adds a self-hosted Modal
  generation leg behind the same provider seam.
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

> **Superseded in part by the [2026-07-28 amendment](#amendment-2026-07-28-the-production-model-family-limit-is-re-scoped)
> below.** The vendor-identity rule in the final sentence no longer governs; the PII-guard
> description is corrected there as well. The section is kept as written so the original
> reasoning stays contestable.

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

## Amendment (2026-07-28): the production model-family limit is re-scoped

The 2026-06-22 amendment limited production generation to the Anthropic and Google model
families on OpenRouter, on the reasoning that a vendor with "a defensible data policy" is
the thing that protects children's content. **That vendor-identity rule is replaced by two
content-and-route controls**, because the protection does not actually come from which lab
trained the model.

### First, a correction to the section above

The original text says the PII guard "strips real-child names before every egress". It does
not strip anything. `assert_prompt_pii_safe` **raises `ValidationError`** and fails the job
(`generation/pii.py:229-258`), on a registered child name or on email-, phone-, or
address-shaped text, over both the `system` and `user` blocks of a `StagePrompt`. The
distinction matters for exactly the argument being made here: a hard fail cannot silently
half-succeed the way a redactor can, so the guarantee is stronger than the original wording
claimed, not weaker.

### What changed in the system, and what did not

Nothing about the egress invariant changed, and that is the point. The guard has been the
sole chokepoint keeping real-child identifying data out of provider prompts since it was
written (`generation/pii.py:3-5`), and brief derivation has always fallen back to a literal
fictional `"Explorer"` rather than a real display name
(`story_requests/brief.py:79-81`).

What changed is that the invariant is now **settled against the one feature that could have
broken it**. [ADR-023](./adr-023-story-personalization-slots.md) resolves guardian-opt-in
personalization client-side, at render time, over generic sentinels the server always stores
and serves unchanged. The alternative it rejected (Route B, generation-time substitution)
would have sent a real child's name to every text and image provider and persisted it in
`storybook_version.blob`. So the open question "will the generation leg eventually have to
carry real child data?" is now answered no, by construction rather than by policy, and a
vendor-identity restriction that partly existed to hedge that risk no longer has to carry
the weight.

### The replacement rule

Production generation is governed by two controls, neither of which names a vendor:

1. **Content**: every assembled prompt passes `assert_prompt_pii_safe` before egress. This
   is unchanged and remains non-negotiable; no carve-out may be added to it (ADR-023,
   "Constraints").
2. **Route**: production traffic runs on a provider account configured for no data
   retention, and the model id must be present and enabled in the admin-managed
   `provider_model_allowlist` (`api/provider_allowlist.py`, ADR-022). The allowlist, not a
   sentence in this ADR, is the enforcement point, and unlike a sentence it is auditable
   (`ProviderModelAllowlistAudit`) and revocable without a doc change.

A model family is therefore no longer disqualified by which lab trained it. It is
disqualified by not being allowlisted, or by being reachable only on a retention-bearing
route. Admins gain the operational freedom this amendment is for; they also inherit the
responsibility, since the allowlist is now the whole control rather than a second layer
under a vendor rule.

### What this amendment does NOT relax

Stated explicitly, because the argument above does not stretch this far and a later reader
should not assume it does.

- **The Stage-0 classifier leg is out of scope and keeps its terms requirement.**
  Child-typed story-request text is sent to external classifiers at intake
  (`story_requests/screening.py`), and all generated prose is sent per-node during
  moderation. That is child-provided free text reaching third parties, and render-time slot
  substitution does nothing about it. See
  [ADR-018](./adr-018-childrens-privacy-compliance.md) item 6 and the narrowed Blocker 1 in
  [privacy-model.md](../privacy-model.md).
- **Briefs are identifier-free, not PII-free.** A brief still carries a coarse age band, the
  guardian's `banned_themes`, content-flag caps rendered as plain-language constraints, and
  free-typed premise text (`story_requests/brief.py:87-124`). The guard screens that free
  text for email/phone/address patterns, and its own docstring records that "general
  free-text PII detection can never be complete" (`pii.py:26-31`). **"No registered child
  identifier reaches a provider" is the claim that holds. "Nothing child-derived reaches a
  provider" is not, and must not be written into a compliance artifact.**

### Basis, and its limits

```python
# #CRITICAL: external resource: the no-retention property of the production
#            provider account is an owner attestation, not a verified term.
#            Control 2 above depends on it.
# #VERIFY: obtain written confirmation from OpenRouter that account-wide ZDR is
#          enabled and covers every downstream model it routes to; record the
#          outcome in docs/compliance/processor-dpa-checklist.md at P7-08.
```

**Recorded 2026-07-28 (account-owner attestation; not independently verified.)** The owner
attests that the provider accounts used for production generation are configured not to
retain data. It is recorded as a dated attestation rather than a verified fact because no
written confirmation has been obtained from OpenRouter, and
`docs/compliance/processor-dpa-checklist.md` still carries that item as unexecuted.

If verification later shows retention on the production route, control 2 is violated and
this amendment's premise fails. The correct response then is to revisit the re-scope, not to
patch around it.

### Related

- [ADR-023](./adr-023-story-personalization-slots.md): the render-time substitution design
  that settles the egress question permanently.
- [ADR-022](./adr-022-tiered-rls-scoping.md): `provider_model_allowlist` scoping.
- [ADR-018](./adr-018-childrens-privacy-compliance.md): the counterparty list and the
  narrowed blocker.
