---
title: "ADR-015: Universal story initiation with a guardian cost gate and an admin safety gate"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the decision that a child, guardian, or admin may initiate a story request,
  that the guardian is the cost gate on generation spend, and that the admin remains the
  safety gate on the AI output, forming one canonical request-to-shelf flow."
tags:
  - planning
  - architecture
  - decisions
  - generation
  - safety
---

# ADR-015: Universal story initiation with a guardian cost gate and an admin safety gate

> **Status**: Accepted (2026-07-16)
> **Date**: 2026-07-16
> **Relates to**: [ADR-005](./adr-005-mandatory-human-approval.md) (the admin safety gate this
> flow terminates in, unchanged), [ADR-003](./adr-003-frontier-llm-generation.md) (the metered
> generation call the cost gate protects), [ADR-008](./adr-008-public-app-store-launch.md)
> (quota/credit monetization the cost gate enforces; its "children never trigger generation"
> phrasing is refined, not weakened, see below)
> **Source**: capability register decisions 1-3
> ([capability-register.md](../capability-register.md)), ratified by the project owner
> 2026-07-16

## TL;DR

Anyone in the household triad may start a story: a child expresses a wish in kid terms, a
guardian authors a brief, an admin seeds the catalog (K11, G4, A10). No request spends
generation budget until its family's guardian consents (G7), and no generated output reaches a
child until the global admin approves and publishes it (A6, ADR-005 unchanged). Initiation is
opened up; both gates stay closed by default.

## Amendment note (2026-07-16, same day): prior ratification and shipped mechanism

A same-day review of open PRs and working documents found that the three initiator flows were
already ratified by the owner on 2026-07-06 (decision 7 in
[story-lifecycle-redesign.md](../story-lifecycle-redesign.md)) and shipped in workstream B
(merged by 2026-07-10): `POST /story-requests` accepts a child token for its own profile
(screened at intake, per-profile pending cap, `initiator_role='child'`, status `pending`);
guardian approval confirms band/length/style before any concept or generation exists;
`POST /story-requests/authored` creates pre-approved guardian/admin requests, admin ones
optionally catalog-targeted with no family. The Context section's claim that no decision was
ever recorded is therefore true only of the foundational documents; the working doc recorded
it, and this ADR elevates it to ADR level. What remains genuinely new in this ADR: the
explicit budget/credit consent semantics at the guardian gate (approval today is content
consent; spend accounting is not wired to it), per-child pre-authorization envelopes (G3),
kid-facing request status and notifications shipping with the flow (K12, G10, S9), and the
ADR-008 phrasing refinement. Implementation and Testing sections below should be read with
the intake mechanism already existing.

## Context

### Problem

The foundational documents never gave children any role in story creation: concept intake was
guardian-only, and ADR-008 stated "children never trigger generation." A 2026-07-16 fresh-look
review traced this to scope inherited from the one-family era (the developer was also the
parent, admin, and author), not to a recorded decision; no ADR ever decided that children shall
have no request channel. Meanwhile the top-line project goal says kids use AI to generate new
stories "based on their interests," which the guardian-only intake only satisfies if a parent
transcribes those interests by hand.

Opening initiation raises two risks the original narrowing implicitly avoided: uncontrolled
LLM spend (a child tapping "make me a story" in a loop) and unsafe content (a child-authored
prompt steering generation). Each risk needs its own gate, owned by the persona accountable
for it.

### Constraints

- **Technical**: child tokens are deliberately narrow (reader and library endpoints only, per
  the authorization matrix); any child-facing intake must widen that scope by exactly one
  request route, not open authoring generally. The existing staged pipeline, validator,
  moderation, and publish state machine are reused unchanged.
- **Business**: generation is metered spend (ADR-003 quotas, ADR-008 credits); the payer must
  hold the spend decision.
- **Safety**: ADR-005's invariant (no story reaches a child without a recorded human approval)
  is non-negotiable and must be provably unaffected by who initiated the request.
- **Privacy**: a child-typed wish is child-provided free text; it must pass the same PII and
  prompt-injection controls as a guardian brief before any provider egress
  (see [privacy-model.md](../privacy-model.md)).

### Significance

This is the decision that makes the creation loop start at the child's imagination instead of
the guardian's keyboard, which is the largest gap between the stated project goal and the
specced system. It also fixes the separation of powers explicitly: guardian owns spend, admin
owns safety.

## Decision

**We will let a child, guardian, or admin initiate a story request; hold every request behind
a guardian cost gate before any generation spend; and keep the admin approve-and-publish
transition as the sole path to a child's shelf.**

### 1. Universal initiation (K11, G4, A10)

- **Child**: expresses a wish in kid terms (picked interests, a short free-text wish) from the
  kid surface. The child token gains exactly one new capability: create a story request for
  its own profile, rate-limited. It still cannot trigger generation, see raw model output, or
  read request queues beyond its own submissions' kid-visible status.
- **Guardian**: authors a concept brief for any profile in their family (existing intake,
  unchanged).
- **Admin**: initiates generation for catalog seeding and pipeline testing (already permitted
  by the authorization matrix; now a named capability).

### 2. The guardian is the cost gate (G7)

A request enters `awaiting_guardian` and consumes zero generation budget until a guardian of
that family consents. Consent converts the request into a concept brief (for a child wish,
the guardian sees and may edit the kid's wording before it becomes a brief) and enqueues
generation against the family's quota or credits. Per-child pre-authorization is a guardian
setting (G3): a guardian may let a specific child's requests auto-consent within a budget
envelope the guardian sets; the spend still draws from guardian-controlled budget, so
pre-authorization delegates the click, never the liability. Admin-initiated catalog requests
bypass the family cost gate because they spend platform budget, not family budget.

### 3. The admin is the safety gate (A6, ADR-005 unchanged)

The generation output flows through the deterministic validator and independent moderation
exactly as today, and the single admin approve-and-publish transition remains the only path to
`published`. Who initiated the request has no effect on gating: a child-initiated story passes
the identical gates as a guardian-initiated one.

### Canonical flow (register item S8)

```text
initiate (child K11 | guardian G4 | admin A10)
   -> guardian cost gate (G7; per-child pre-auth via G3; skipped for platform-funded
      admin requests)
   -> staged generation (ADR-003, unchanged)
   -> deterministic validation + independent moderation (unchanged)
   -> admin approve-and-publish (ADR-005, unchanged)
   -> child's shelf, with honest async status to the requester throughout (K12, G10)
```

### Refinement of ADR-008's phrasing

ADR-008's compliance posture said "children never trigger generation." The enforceable
invariant was always narrower: no child action may cause LLM spend or reach a provider without
adult consent. This ADR preserves that invariant precisely (the cost gate is an adult action)
while allowing the child to *request*. App Store review notes should describe the flow as
child-suggests, guardian-consents, admin-approves.

## Options Considered

### Option 1: Universal initiation + guardian cost gate + admin safety gate ✓

**Pros**:

- ✅ Fulfills the top-line goal (kid interests drive new stories) without weakening either
  spend control or the ADR-005 invariant.
- ✅ Clean separation of powers: requester, payer, and safety authority are distinct roles
  with distinct gates.

**Cons**:

- ❌ Two new surfaces to build and test: the kid request intake and the guardian consent
  queue, plus notification plumbing (S9) to make the loop feel alive.

### Option 2: Status quo (guardian-only intake)

**Pros**:

- ✅ Zero new attack or spend surface.

**Cons**:

- ❌ The product goal is only satisfied by parental transcription; the child has no agency in
  the creation loop. Rejected by the owner 2026-07-16.

### Option 3: Child-initiated with direct generation (no cost gate)

**Pros**:

- ✅ Most magical kid experience (instant).

**Cons**:

- ❌ Child taps become unbounded LLM spend; violates the payer-controls-spend principle and
  ADR-008's parental-gate posture. Rejected.

## Consequences

### Positive

- ✅ The creation loop starts at the child's imagination; interests flow in without an adult
  transcribing them.
- ✅ Spend and safety authority are explicit and separately testable.
- ✅ ADR-005's guarantee is untouched; the state machine gains states upstream of it, never a
  bypass.

### Trade-offs

- ⚠️ Child free text becomes pipeline input. Mitigation: the same PII guard, length limits,
  control-character stripping, and prompt-injection defenses as guardian briefs; the guardian
  sees the wish text at the cost gate before it goes anywhere; moderation remains independent
  of the generator.
- ⚠️ A pending request queue introduces waiting, and a silently pending wish is a broken
  promise to a child. Mitigation: kid-visible honest status (K12) and guardian notifications
  (G10) ship with this flow, not after it.
- ⚠️ The child token scope widens by one route. Mitigation: the authorization matrix gains the
  route explicitly with IDOR negative tests (child A cannot create or read requests for
  profile B; a child token still 403s on generate, approve, and every guardian surface).

### Technical Debt

- The request lifecycle needs states upstream of the existing GenerationJob machine
  (`awaiting_guardian -> consented -> queued ...` plus `declined`); recorded here, designed at
  implementation time.
- Notification delivery (S9) has no foundational design yet; this flow is its first consumer.

## Implementation

### Components Affected

1. **Request intake**: a kid-scoped create-request route (own profile only, rate-limited) and
   the guardian consent queue with edit-before-consent.
2. **Authorization**: child token allowlist gains the one route; matrix and IDOR suite updated
   (see the planned-amendment note in [authorization-matrix.md](../authorization-matrix.md)).
3. **Budget**: per-family quota/credit check moves to consent time; per-child pre-auth
   envelope settings (G3).
4. **Status and notifications**: kid-facing request status (K12); guardian digest/alerts
   (G10) over the event log (S9).
5. **Privacy**: PII guard applied to child wish text before egress; wish text stored
   family-scoped like brief text.

### Testing Strategy

- Authorization: the new IDOR negatives above; device tokens still 403 on request routes.
- Spend: no provider call and no budget decrement occurs before consent, proven at the
  orchestrator seam; pre-auth envelope exhaustion blocks auto-consent.
- Safety: a child-initiated adversarial wish is flagged by moderation and cannot be published
  without admin approval (extends the existing adversarial-brief suite).
- Flow: end-to-end child wish to shelf, including declined and edited-wish paths.

## Validation

### Success Criteria

- [ ] A child can submit a wish and see honest status; a guardian can consent, edit, decline,
      and pre-authorize; an admin can seed the catalog.
- [ ] Zero generation spend before guardian consent, verified by test at the provider seam.
- [ ] A child-initiated story passes gates identical to a guardian-initiated one; the ADR-005
      invariant tests stay green with the new initiation paths active.

### Review Schedule

- Initial: when the request lifecycle design lands.
- Ongoing: on any change to quotas, credits, or the publish state machine.

## Related

- [Capability register](../capability-register.md): decisions 1-3 and items K11, G3, G4, G7,
  A6, A10, S8, S9.
- [ADR-005](./adr-005-mandatory-human-approval.md): the safety gate, unchanged and reconfirmed.
- [ADR-008](./adr-008-public-app-store-launch.md): monetization and compliance posture this
  flow must respect.
- [Privacy model](../privacy-model.md): controls applied to child-provided wish text.
- [Authorization matrix](../authorization-matrix.md): the one-route child scope widening.
