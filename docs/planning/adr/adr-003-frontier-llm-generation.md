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
> amended 2026-07-28, see Amendment: the production model-family limit is re-scoped;
> amended 2026-08-18, see Amendment: the Ollama leg is retired and Modal takes leg 3)
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
- **Deferred at the time**: a direct Anthropic SDK adapter. Not implemented in Phase 2b
  (OpenRouter covers Claude); described then as a trivial future add via the existing seam if
  direct Opus 4.8 or prompt caching without the OpenRouter markup is ever wanted.
  **Corrected 2026-07-28: it is no longer deferred, it is built.** `AnthropicProvider`
  (`generation/providers/anthropic.py`) is a real Layer-1 adapter; `build_anthropic_leg`
  (`generation/provider.py:381`) is dispatched from `build_provider` whenever the resolved
  provider is `anthropic` (`generation/provider.py:659-660`); `anthropic` is an accepted value
  of `settings.generation_provider` (`core/config.py:361-363`); and the admin-managed allowlist
  both permits the provider and seeds two direct-Anthropic models
  (`generation/allowlist.py:25` and `DEFAULT_ALLOWLIST`). The processor record already lists
  "Anthropic (direct)" as a live recipient of request text
  (`docs/compliance/records-of-processing-activities.md`, Section 3 row 3 and Section 4). The
  direct leg is therefore credentialed and admin-selectable, and it routes around the
  OpenRouter guardrail this ADR's 2026-07-28 amendment relies on. See
  [BYOK is the better answer than routing traffic onto the direct leg](#byok-is-the-better-answer-than-routing-traffic-onto-the-direct-leg)
  for why the two motivations above are better reached without sending more traffic that way.

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
(`generation/pii.py:229-289`), on a registered child name or on email-, phone-, or
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

What changed is that the one feature that could have broken the invariant now has a **proposed**
answer. [ADR-023](./adr-023-story-personalization-slots.md) proposes resolving guardian-opt-in
personalization client-side, at render time, over generic sentinels the server always stores
and serves unchanged. Two qualifications belong here rather than in a footnote:

- **ADR-023 is Proposed, not Accepted, and no code exists for it yet.** Its frontmatter carries
  `status: proposed`, counsel sign-off "remains open", and its Source line records "no code
  exists for this feature yet". So the answer below is a design commitment, not a shipped
  property. **If ADR-023 is not adopted, this narrowing's premise lapses** and the re-scope has
  to be re-argued rather than patched around.
- **ADR-023 is not the rejected Route B.** It says so itself: "This ADR is not Route B. It is a
  third route the remediation plan did not consider." Route B (generation-time substitution,
  which would have sent a real child's name to every text and image provider and persisted it in
  `storybook_version.blob`) was rejected by
  [coppa-gdpr-remediation-plan.md](../../compliance/coppa-gdpr-remediation-plan.md), Section 5's
  "Self-naming" question, lines 741-759.

So the open question "will the generation leg eventually have to carry real child data?" has a
proposed answer of no, by construction rather than by policy, and a vendor-identity restriction
that partly existed to hedge that risk no longer has to carry the weight.

### The replacement rule

Production generation is governed by two controls, neither of which disqualifies a model by
which lab trained it:

1. **Content**: every assembled prompt passes `assert_prompt_pii_safe` before egress. This
   is unchanged and remains non-negotiable; no carve-out may be added to it (ADR-023,
   "Constraints").
2. **Route**: OpenRouter traffic is confined to endpoints that enforce zero data retention
   and do not train on or publish request data. This is enforced at the provider platform,
   not by this document, and is described in "Basis" below.

**Control 2's scope, stated honestly: it governs the OpenRouter route, not all production
generation.** The guardrail is a property of a specific workspace and a specific key at a
specific vendor, so it reaches only the legs that go through that vendor. The direct-Anthropic
leg is built and admin-selectable (see the corrected bullet in the 2026-06-22 amendment above)
and inherits none of it. Confining production generation to the guarded route is therefore an
**open item**, not an existing control, and this ADR does not claim otherwise:

```python
# #CRITICAL: security: generation_provider="anthropic" and the two seeded
#            direct-Anthropic allowlist rows let production generation bypass the
#            OpenRouter ZDR guardrail entirely. Nothing in code restricts the direct
#            leg to non-production tiers, in the same way nothing rejects
#            generation_provider="mock" outside local (core/config.py's mock note).
# #VERIFY: decide whether the direct leg may be production-selectable at all, then
#          enforce that decision rather than relying on convention: a Settings
#          model_validator rejecting non-guarded providers outside local, and/or
#          disabling the "anthropic" allowlist rows in deployed tiers. Until that
#          exists, confirm every deployed .env sets
#          CYO_ADVENTURE_GENERATION_PROVIDER=openrouter and that no production
#          allowlist row with provider="anthropic" is enabled.
```

There is also a third, unrelated control that should not be confused with either: the
admin-managed `provider_model_allowlist` (`api/provider_allowlist.py`, ADR-022) bounds
**which model ids this app will call at all**. Its stated purpose is keeping free-string
model ids out of billing, and it is auditable (`ProviderModelAllowlistAudit`). It is an
operational and cost control that happens to also narrow the blast radius; it is not the
data-policy control, and the two must not be conflated when reasoning about either.

A model family is therefore no longer disqualified by which lab trained it. It is
disqualified by failing the platform's data-policy guardrail, or by not being allowlisted
for this app's own operational reasons.

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
- **Briefs are identifier-free, not PII-free.** A brief still carries the guardian's
  `banned_themes` and content-flag caps rendered as plain-language constraints
  (`story_requests/brief.py:87-124`), plus a coarse age band and the requester's free-typed
  premise text carried through verbatim (`story_requests/brief.py:176-203`, where
  `premise=request.request_text`). The guard screens that free
  text for email/phone/address patterns, and its own docstring records that "general
  free-text PII detection can never be complete" (`pii.py:26-31`). **"No registered child
  identifier reaches a provider" is the claim that holds. "Nothing child-derived reaches a
  provider" is not, and must not be written into a compliance artifact.**

### Basis: how control 2 is actually enforced

**Configured 2026-07-28.** Control 2 is not a policy this document asks an operator to
honour. It is a platform guardrail on a **dedicated OpenRouter workspace created for this
project**, with a **new API key scoped to that workspace**, so enforcement is bound to the
credential the app actually uses rather than asserted account-wide. The guardrail is set as
follows.

**Zero Data Retention**, which OpenRouter applies to provider routing:

| Toggle | State | Routing effect |
|---|---|---|
| Non-frontier | ON | All non-frontier model requests require ZDR endpoints |
| Anthropic | ON | First-party Anthropic endpoints disabled; Bedrock and Vertex remain |
| OpenAI | ON | First-party OpenAI endpoints disabled; Azure remains |
| Google | ON | AI Studio endpoints disabled; Vertex remains |
| xAI | ON | xAI endpoints that retain data disabled |

**Data training**, which OpenRouter treats as a separate axis from retention, all three
disabled: paid endpoints that train on request data, free endpoints that train on request
data, and free endpoints that publish prompts and completions to public datasets.

No specific provider or model is individually blocked, and deliberately so. Eligibility is
determined by the data policy an endpoint enforces, which is precisely the re-scope this
amendment records: a lab is not disqualified by identity, and does not need to be, because
the guardrail rejects the endpoint rather than the vendor.

**The plugins-and-tools carve-out does not apply to this app, and that is verifiable rather
than asserted.** OpenRouter states that the ZDR guardrail "only applies to provider routing,
does not apply to plugins and tools you choose to enable". This app enables none: the
request body assembled in `generation/providers/openrouter.py:154-164` contains exactly
`model`, `messages`, `max_tokens`, and an optional `reasoning` effort. There is no `plugins`
key and no `tools` key on the generation path. A future contributor adding either would
silently reopen this hole, so it belongs in review criteria for that file.

### Key-level egress controls: a second chokepoint, and why two of them are off

Also configured 2026-07-28, at API-key level, is request-side **Sensitive Info Detection**
in redact mode for five patterns: email address, phone number, Social Security number,
credit card number, and IP address. This is genuinely a **second, independent chokepoint**,
sitting outside our process, after `assert_prompt_pii_safe` has already run and failed the
job on the overlapping patterns. The overlap is deliberate defense-in-depth, exactly as
`pii.py`'s own docstring frames it, and it has a useful diagnostic property: because our
guard hard-fails on email, phone, and address *before* egress, the platform's redactor
firing on those patterns would mean our guard missed something. SSN, credit card, and IP are
**not** in our guard, so those are net-new coverage, though they are silently redacted rather
than failing the job.

**Two patterns are deliberately left off, and both would be actively harmful here.** This is
recorded so a later reviewer does not read the unchecked boxes as an oversight and "fix"
them:

- **Person name** would redact the *fictional* protagonist name, which is intentional story
  content and the entire point of `ConceptBrief.Protagonist`. Turning it on would corrupt
  generation output while protecting nothing: real child names are already blocked upstream
  by a hard fail, not by redaction. It also carries a latency cost and is Beta.
- **Address** is already a hard fail in our own guard, and story prose legitimately contains
  fictional places. Redaction here would be redundant against real addresses and damaging
  against fictional ones.

**Prompt-injection detection is available and currently disabled.** OpenRouter offers a
free, no-added-latency, OWASP-inspired regex scan with an allow-list escape hatch. The
privacy model already names concept brief text as untrusted input and lists the defenses
against it, all of which are ours. This would be a cheap fourth layer. It is not enabled as
of this record, and the reason to think before enabling is false positives: a children's
adventure brief can legitimately contain instruction-shaped phrasing, and a blocked
generation is a visible product failure. Recommended as a candidate to trial with the
allow-list in reach, not as an obvious yes. Tracked in
[privacy-model.md](../privacy-model.md), Prompt-Injection Defense.

### Consequence: routing through OpenRouter is now the preferred path, not merely the incumbent

The 2026-06-22 amendment recorded a direct Anthropic SDK adapter as **deferred**, "a trivial
future add via the existing seam" if direct access or cheaper prompt caching were ever
wanted. That characterization is now wrong twice over: the adapter was built (WS-C PR1, see
the corrected bullet in the 2026-06-22 amendment above), and the trade is no longer
cost-neutral.

The controls above (ZDR routing, training and publishing disabled, key-level sensitive-info
redaction, and optionally injection scanning) are properties of **the OpenRouter path
specifically**. The direct-Anthropic leg inherits none of them: selecting it moves generation
traffic onto a leg where the only egress control is our own PII guard. Because that leg is
already built, credentialed, and admin-selectable, this is a live configuration question and
not a future build decision: **selecting it removes a defense layer**, and that trade has to be
argued on the record rather than treated as a pure cost optimization. Prefer OpenRouter as the
default egress path for that reason, independent of price. The same reasoning applies to any
future provider leg added behind `GenerationProvider`: legs that bypass the guardrail layer
inherit a higher bar.

**The Modal leg (ADR-010) is not an exception to this, and an earlier draft of this section
wrongly said it was.** Modal is a hosted third-party vendor, and ADR-010 says so in its own
consequences ("Modal is a second serverless vendor"). The leg targets Modal Auto Endpoints over
the network with proxy credentials (`core/config.py:529-554`), and `generation_provider="modal"`
is dispatched to a live adapter (`generation/provider.py:676-677`). (The review-side
`review_provider="modal"` is an accepted config value but still raises at build time,
`moderation/review_provider.py`.) What is true is narrower: the model weights are
self-hosted rather than a vendor's, so no model vendor is added; the platform hosting them still
is one. Modal is currently absent from `docs/compliance/processor-dpa-checklist.md`, from
[ADR-018](./adr-018-childrens-privacy-compliance.md) item 6, and from
[privacy-model.md](../privacy-model.md). That is a pre-existing gap in the processor record,
recorded here as an open item; it is not a finding that Modal is out of scope.

```python
# #ASSUME: external resource: Modal is a hosted third-party platform that would
#          receive prompt content on any tier where the Modal leg is selected, yet
#          it appears in no processor record.
# #VERIFY: before the Modal leg is enabled on any deployed tier, add a Modal row to
#          docs/compliance/processor-dpa-checklist.md, ADR-018 item 6, and
#          privacy-model.md's counterparty list; confirm no deployed .env currently
#          sets CYO_ADVENTURE_GENERATION_PROVIDER or CYO_ADVENTURE_REVIEW_PROVIDER
#          to "modal".
```

#### BYOK is the better answer than routing traffic onto the direct leg

OpenRouter supports bring-your-own-key. The operator already holds an Anthropic API key
(noted in the 2026-06-22 amendment), so that key can be supplied to OpenRouter rather than
exercised through the direct `AnthropicProvider` leg. This matters because it **dominates**
selecting that leg rather than merely competing with it:

- Traffic stays on the OpenRouter path, so the ZDR routing guardrail, the key-level
  sensitive-info redaction, and any future injection scan all still apply.
- The model call is nevertheless billed to, and governed by, the operator's own direct
  Anthropic relationship and its terms tier.
- No traffic moves onto a leg whose only egress control is our own PII guard.

The two motivations the 2026-06-22 amendment gave for a direct adapter, direct model access
and prompt caching without the OpenRouter markup, are therefore both reachable **without**
giving up a defense layer. That strengthens the preceding section's conclusion rather than
qualifying it: since the direct leg already exists, the live question is not whether to build
it but whether to ever select it, and BYOK removes the remaining reason to.

**Not adopted as of this record, and one interaction must be resolved first.** BYOK is
described here as the evaluated path, not the configured one. The open question is a direct
conflict with the guardrail above:

```python
# #CRITICAL: security: the Anthropic ZDR toggle disables FIRST-PARTY Anthropic
#            endpoints, which is exactly where a BYOK Anthropic key routes. BYOK
#            and that toggle may be mutually exclusive.
# #VERIFY: test a BYOK Anthropic request against the live guardrail before
#          adopting. If it is refused, do NOT relax the toggle to make it work
#          without first confirming ZDR on the Anthropic account itself.
```

The trap is that "add my own key" reads as strictly additive and may not be. Anthropic's
first-party API retains request data for a bounded abuse-monitoring window unless a
zero-retention arrangement exists on that account, which is why OpenRouter's ZDR toggle
disables those endpoints in the first place. So BYOK-to-first-party-Anthropic without
account-level ZDR would be a **worse** retention posture than the Bedrock and Vertex routing
the guardrail currently forces, while feeling like an upgrade because a contractual
relationship was added. Contract and retention are separate axes here, and only one of them
improves by default.

Three consequences if BYOK is later adopted:

1. **The terms-tier question stops being hypothetical.**
   `docs/compliance/processor-dpa-checklist.md` flags that the Anthropic row needs
   confirmation the account is on commercial terms, since the DPA does not apply to consumer
   accounts. Under BYOK that becomes load-bearing rather than a tidy-up item.
2. **The counterparty list moves again.** Anthropic-direct returns to
   [ADR-018](./adr-018-childrens-privacy-compliance.md) item 6 for whatever share of traffic
   BYOK carries, and Bedrock or Vertex correspondingly leaves it. The processor record has to
   follow the routing, in whichever direction it moves.
3. **Retention posture must be established on the Anthropic account itself**, not inherited
   from the OpenRouter guardrail, because on that leg the guardrail is no longer choosing the
   endpoint.

### What this basis does not establish

```python
# #CRITICAL: external resource: a platform guardrail is a routing control, not a
#            contract. No DPA has been executed with OpenRouter.
# #VERIFY: execute the DPA / enterprise terms at P7-08 and record it in
#          docs/compliance/processor-dpa-checklist.md; re-confirm the guardrail
#          state at the same checkpoint, since console settings can drift.
```

Three limits, stated so the record does not overclaim:

1. **A configured control is not an executed contract.** The guardrail governs how requests
   route today. It is not a data processing agreement, and `processor-dpa-checklist.md`
   still carries the OpenRouter row as unexecuted. Both are needed; neither substitutes for
   the other.
2. **Console state can drift.** Guardrails, workspaces, and keys are mutable. The state
   above is a dated snapshot, not a permanent property, and should be re-confirmed at P7-08
   and on any credential rotation.
3. **The counterparty set moved, and the processor record has to follow.** Disabling
   first-party Anthropic, OpenAI, and Google AI Studio endpoints does not remove those model
   families; it routes them through **AWS Bedrock, Microsoft Azure, and Google Vertex**
   instead. Those platforms now receive generation prompts as OpenRouter's sub-processors.
   This is a genuine improvement in retention posture and simultaneously a change to who is
   in scope for [ADR-018](./adr-018-childrens-privacy-compliance.md) item 6, which is
   updated accordingly.

If a later check shows retention on the OpenRouter route, control 2 is violated and this
amendment's premise fails. The correct response then is to revisit the re-scope, not to
patch around it.

### Two documents are deliberately left stale

`docs/compliance/gdpr-compliance-review.md` and `docs/compliance/coppa-compliance-audit.md` still
describe the pre-amendment posture, and that is intentional rather than drift. Both are **dated
audit findings**: they record what was true when the audit was run, and rewriting them would
destroy the record of what the audit actually found. Read them as history, and read this
amendment, [ADR-018](./adr-018-childrens-privacy-compliance.md) item 6, and
[privacy-model.md](../privacy-model.md)'s Blocker 1 for the current posture. Every other live
document that carried the retired vendor-identity rule was updated with this amendment
(`docs/compliance/information-security-program.md` Section 4,
`docs/compliance/coppa-gdpr-remediation-plan.md` Phase 5b,
`docs/compliance/processor-dpa-checklist.md`, `docs/planning/phase-2b-live-provider.md`, and the
model-pinning comment in `core/config.py`).

### Related

- [ADR-023](./adr-023-story-personalization-slots.md): the render-time substitution design
  that settles the egress question permanently.
- [ADR-022](./adr-022-tiered-rls-scoping.md): `provider_model_allowlist` scoping.
- [ADR-018](./adr-018-childrens-privacy-compliance.md): the counterparty list and the
  narrowed blocker.

## Amendment (2026-08-18): the Ollama leg is retired and Modal takes leg 3

### What changed

The local Ollama leg is removed. The `OllamaProvider` adapter, the `OLLAMA_*` configuration
surface, the `ollama` member of `settings.generation_provider` and `settings.review_provider`,
and the `ollama` provider allowlist row and CHECK-constraint value are all deleted. The
**Modal** leg takes its place as the cascade's third leg.

Revised cascade: OpenRouter primary (`settings.openrouter_model`) -> OpenRouter fallback
(`settings.openrouter_fallback_model`) -> **Modal** (`settings.modal_base_url` /
`settings.modal_model`).

### Why

The homelab-to-Vultr migration removes the hardware the leg depended on. Ollama was free
because a GPU we already owned served it; in the cloud tier that same leg is a rented GPU
priced far above what a fallback-of-a-fallback justifies. Retiring it ahead of the move keeps
the migration itself a compute lift with no local-service dependency left in the worker
(see [ADR-004](./adr-004-homelab-first-deployment.md), whose homelab premise the move amends).

### The availability property being preserved

Ollama's value in this cascade was never quality; it was that **it did not share a failure
domain with OpenRouter**. Legs 1 and 2 are the same vendor on the same account, so an
OpenRouter outage, billing lapse, or account suspension takes both at once. Dropping to a
two-leg single-vendor cascade would have quietly removed the only thing Layer 2 protects
against at the vendor level.

Modal preserves that property: it is a separately-deployed, separately-credentialed endpoint.
It is a weaker backstop than a frontier model on quality, which is the same trade Ollama
always made.

### Degradation, and why it is deliberate

`build_modal_leg` raises `ConfigurationError` when the endpoint is unset, which is the state
of every local dev run, every CI run, and any deploy that has not stood up an Auto Endpoint.
Including the leg unconditionally would convert all of those into hard generation failures, so
`build_provider` includes it only when `settings.modal_leg_configured` is true and otherwise
builds the two-leg cascade.

That degraded shape is a real availability regression, not a neutral default, so it is
**logged, not silent**: `build_provider` emits `generation.cascade_single_vendor` at WARNING
naming the reason. Configuring Modal is what restores two-vendor failover, and any deployment
whose uptime matters should set `MODAL_BASE_URL` and `MODAL_MODEL`.

### Consequences

- **Staging is now billed.** Staging ran `generation_provider=ollama` specifically so its test
  runs placed no metered LLM calls. It now runs `openrouter` against a cheap pinned model
  (`.env.staging.example`), so staging generation costs real money and needs its own
  spend-limited `OPENROUTER_API_KEY`.
- **Moderation review loses a backend.** `review_provider` no longer accepts `ollama`; with
  `modal` still deferred to slice 2b, `openrouter` is the only live review backend.
- **Modal is no longer offline-only.** Earlier text in this ADR and in
  [ADR-010](./adr-010-modal-review-and-gated-generation.md) describes the Modal generation leg
  as an offline experiment never wrapped in the production cascade. That is superseded here.
- **Historical cost data is retained.** The `("ollama", "qwen2.5:14b")` row stays in
  `core/pricing.py`: pre-retirement `GenerationJob` rows still carry `provider="ollama"`, and
  deleting the price would make them unpriceable rather than making them free.
- **One less private-CA trust path.** The leg carried its own `OLLAMA_CA_BUNDLE` trust store
  and a reversible HTTP Basic credential; both are gone, so every remaining egress leg verifies
  against the public CA store and authenticates with a header credential over TLS
  (`docs/security/crypto-inventory.md`).

### Not decided here

The **primary model** is unchanged by this amendment. `settings.openrouter_model` remains
`anthropic/claude-haiku-4.5`, pinned by the 2026-06-22 yield run. Replacing it is a separate
decision with its own yield evidence and its own amendment.

### Related

- [ADR-004](./adr-004-homelab-first-deployment.md): the homelab premise this retirement
  precedes the amendment of.
- [ADR-010](./adr-010-modal-review-and-gated-generation.md): the Modal leg, no longer
  offline-only for generation.
