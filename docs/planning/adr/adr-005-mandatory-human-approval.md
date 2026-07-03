---
title: "ADR-005: Mandatory human approval before any story reaches a child"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the decision to gate every story behind a guardian approval state, enforced by a state machine."
tags:
  - planning
  - architecture
  - decisions
---

# ADR-005: Mandatory human approval before any story reaches a child

> **Status**: Accepted (2026-07-03; amended 2026-06-30, see Amendment below)
> **Date**: 2026-06-20

## Amendment (2026-06-30): the approver is a global admin, not the child's parent

In Phase 3 slice 1 the recorded human approver is a dedicated **global admin** (the backend
safety operator) rather than the child's own parent/guardian. This is an intentional design
evolution, confirmed by the project owner, of the original "a parent approves it" framing
below.

The admin screens content **cross-family**: the approval router requires `principal.is_admin`
(child and guardian tokens receive 403), and `authorize_family` is intentionally not called
on approval routes because the safety-review authority spans families. Guardians retain their
own family-scoped powers elsewhere; they are simply not the publish approver in this phase.

The core invariant is **unchanged and in fact strengthened**: no story reaches a child
without a recorded human approval, encoded in a state machine with no bypass to a child
profile, with the approver stamped per published version (`storybook_version.approved_by`).
Centralizing the screen in a trained safety operator raises the floor on review consistency
versus a per-parent approval, while keeping the human-in-the-loop guarantee absolute. Where
the sections below say "parent" or "guardian" as the approver, read "global admin (safety
operator)"; the structural guarantee they describe is otherwise as written.

## TL;DR

A story can enter a child's library only after a human approves it, encoded as a state
machine with no path from generation to a child profile that bypasses the recorded
admin-approval step, because automated moderation helps but cannot be the only line for
machine-generated content read by children.

## Context

### Problem

The content is machine-generated and read by children. Automated moderation reduces
risk but cannot be the sole safeguard; a person who knows the child must make the
publish decision.

### Constraints

- **Technical**: the guarantee must be structural, not a convention a future code
  change can erode.
- **Business**: at family volume a manual step per story is acceptable; the design
  should also future-proof a possible move beyond one family.

### Significance

This is the central child-safety guarantee. Getting it wrong means a generated story
could reach a child unreviewed.

## Decision

**We will allow a story to enter a child's library only after a guardian approves it,
encoded as a publish state machine with no bypass path to a child profile, because
defense in depth requires an irreplaceable human layer.** Automated moderation and the
validation gate run first and gate entry to review; they do not replace the human step.

### Rationale

The irreplaceable layer is a person who knows the child. Automated classifiers reduce
what reaches review and flag riskier passages, but the publish decision stays human.
This matches a sound child-safety stance and future-proofs the design if the app is
ever shared beyond the family.

## Options Considered

### Option 1: State machine with a mandatory guardian approval transition ✓

**Pros**:

- ✅ A hard guarantee that a parent saw every story.
- ✅ A clean audit trail (who approved which version, by which model and prompt).

**Cons**:

- ❌ A manual step per story. Acceptable at family volume; the Phase 3 review UI makes
  it a few minutes.

### Option 2: Automated moderation only

**Pros**:

- ✅ Zero manual effort.

**Cons**:

- ❌ No human who knows the child in the loop; a single classifier miss reaches a kid.
  Rejected on child-safety grounds.

## Consequences

### Positive

- ✅ A guaranteed parent review of every story, with provenance recorded per version.

### Trade-offs

- ⚠️ The publish state machine and an approver role are core, not optional. Mitigation:
  the review surface (Phase 3) keeps each approval to a few minutes.

### Technical Debt

- Automated checks (validator plus moderation) run on the GenerationJob
  (`running -> passed | needs_review | failed`) and gate whether a Storybook may enter
  `in_review`; the approve action then moves the Storybook directly to `published` (there
  is no separate `approved` resting state), and a rejected review routes to
  `needs_revision`. A story is visible to a child only in `published`.

## Implementation

### Components Affected

1. **Two lifecycles, not one pipeline**: a **GenerationJob** state machine
   (`queued -> running -> passed | needs_review | failed`) drives generation and the
   automated gate, and a separate **Storybook** state machine
   (`draft -> in_review -> published | needs_revision | archived`) drives review and
   publication. There is no single `approved` resting state: `approved` is collapsed into
   the approve action, which publishes in one step. A story is visible to a child only in
   the Storybook `published` state.
2. **Authorization**: the approver is a **global admin** (`principal.is_admin`) who
   screens cross-family; child and guardian tokens cannot approve or publish.
3. **Provenance**: model, provider, prompt version, and approver persisted per
   published version.

### Testing Strategy

- Integration: attempt every transition path and verify no route reaches a child
  profile without a recorded guardian approval.
- Safety: adversarial briefs are flagged and cannot be auto-published.

## Validation

### Success Criteria

- [x] No story reaches a child profile without a recorded guardian approval (no auto-publish
  path; verified by the state machine and the published-requires-approver invariant).
- [~] Adversarial briefs are flagged and cannot be auto-published. "Cannot auto-publish"
  holds; the import and admin-submit paths no longer reach a publishable state unmoderated
  (closed structurally: the import path now runs moderation before returning, and `approve`
  refuses to publish a version with no moderation report). What remains unmet is the flagging
  half for the model-dependent classes, which has no live-model run yet, see
  [adversarial-safety-evaluation.md](../safety/adversarial-safety-evaluation.md).

### Review Schedule

- Initial: Phase 3 acceptance.
- Ongoing: on any change to the publish or authorization model.

## Related

- [ADR-001](./adr-001-story-format-json-storybook.md): the validatable format the gate
  depends on.
- [ADR-003](./adr-003-frontier-llm-generation.md): the generator whose output this
  gate reviews.
- [Adversarial safety evaluation](../safety/adversarial-safety-evaluation.md): the failure
  taxonomy, the structural bypass findings, and the status of the adversarial-brief criterion
  above.
- [Tech Spec: Publish state machine](../tech-spec.md#publish-state-machine)
