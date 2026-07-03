---
title: "ADR-001: Story format is a versioned JSON Storybook graph"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the decision to use a custom versioned JSON Storybook schema as the canonical story format."
tags:
  - planning
  - architecture
  - decisions
---

# ADR-001: Story format is a versioned JSON Storybook graph

> **Status**: Accepted (2026-07-03)
> **Date**: 2026-06-20

## TL;DR

Define a custom, versioned JSON "Storybook" schema as the canonical story format and
build a small deterministic player over it, because constrained JSON is a far more
reliable LLM target and far easier to validate with hard guarantees than a full
narrative scripting language.

## Context

### Problem

The format is the keystone: both the reader and the generator depend on it, and
changing it later is expensive. The candidates are a custom JSON schema we control,
Ink (Inkle's narrative scripting language, with the `inkjs` browser runtime), and
Twine/Twee (the hypertext interactive-fiction standard).

### Constraints

- **Technical**: the format must be reliably emitted by an LLM, statically
  validatable for safety properties (every choice target exists, every node
  reachable, every variable declared), and playable by clients in any language.
- **Business**: the readers are children, so the format sits directly under a
  child-safety bar; the cost of a malformed or unvalidatable story is high.

### Significance

Both halves of the system (generator and reader) bind to the format. Getting it
wrong means rebuilding both. This is the highest-reversal-cost decision in the
project.

## Decision

**We will define a custom, versioned JSON Storybook schema and build a small
deterministic player over it, because a model emits constrained JSON far more
reliably than a scripting language and constrained JSON is far easier to validate
with hard guarantees.** Treat Ink export as a possible future feature, not a
dependency.

### Rationale

The deciding factor is LLM reliability against a children's-safety bar. Ink is
genuinely excellent for human authors and gives save/restore and rich state for free,
but having the model emit valid Ink, then compiling it (the `inklecate` compiler is a
separate .NET toolchain), adds a failure surface exactly where we can least afford
one. Twine is author-friendly but built around a visual editor and HTML output, a
poor fit for an automated pipeline.

## Options Considered

### Option 1: Custom JSON Storybook ✓

**Pros**:
- ✅ Total control; trivial to validate with hard guarantees.
- ✅ Reliable LLM target; client-agnostic; small enough to cache offline.

**Cons**:
- ❌ We own the runtime and edge cases (state, conditional text, save).

### Option 2: Ink + inkjs

**Pros**:
- ✅ Mature runtime, rich state, save/restore, human-readable source.

**Cons**:
- ❌ LLM emission is error-prone; extra .NET compile toolchain.
- ❌ Harder to statically validate every safety property.

### Option 3: Twine / Twee

Author-friendly with a large community, but visual-editor centric with HTML output,
awkward to generate and lint programmatically. Wrong shape for an automated pipeline.

## Consequences

### Positive

- ✅ A hard validation gate becomes straightforward.
- ✅ The format is small enough to reason about and to cache for offline play.
- ✅ Clients in any language can play it.

### Trade-offs

- ⚠️ We build the player and state evaluator ourselves (a few hundred lines) rather
  than inheriting Ink's. Mitigated by keeping the state model deliberately small.

### Technical Debt

- Schema versioning: current policy pins to schema version `2.0` and rejects any other
  version outright (exactly one accepted version); the read-time upcaster chain is not
  built. If multiple concurrent schema versions ever need to coexist, an in-memory
  upcaster keyed by `schema_version` with a golden fixture per version is the intended
  path, but it is deliberately deferred while a single version is enforced.
- Storage: story blobs are stored inline in Postgres JSONB (`storybook_version.blob`) at
  launch per [ADR-009](./adr-009-supabase-platform.md); object storage via `blob_ref` is
  deferred until catalog size warrants externalizing blobs.

## Implementation

### Components Affected

1. **Schema**: defined once in Pydantic, exported to JSON Schema, shared by generator,
   validator, reader, and editor.
2. **Player**: a deterministic traversal honoring Runtime Semantics v1.
3. **Backend read path**: the loader validates `schema_version` and rejects any blob not
   at the single accepted version (`2.0`); no upcaster chain runs.

### Testing Strategy

- Unit: schema round-trip (Pydantic to JSON Schema to instance validation); rejection of
  any blob whose `schema_version` is not the single accepted version.
- Integration: a valid and a known-bad fixture corpus (see the tech spec testing
  strategy).

## Validation

### Success Criteria

- [ ] A "hello world" Storybook validates against the `2.0` JSON Schema.
- [ ] Round-trip validation and version-rejection tests pass.

### Review Schedule

- Initial: Phase 0 exit gate.
- Ongoing: on every `schema_version` bump.

## Related

- [ADR-005](./adr-005-mandatory-human-approval.md): the safety gate that the format
  makes validatable.
- [ADR-006](./adr-006-conditions-inhouse-evaluator.md): the condition logic carried
  inside the format.
- [ADR-009](./adr-009-supabase-platform.md): story blobs are stored inline in Postgres
  JSONB at launch; object storage via `blob_ref` is deferred.
- [Tech Spec: Data Model](../tech-spec.md#data-model)
