---
title: "ADR-006: Conditions use the JSONLogic shape with an in-house whitelisted evaluator"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the decision to keep the JSONLogic object shape but evaluate it with small in-house interpreters."
tags:
  - planning
  - architecture
  - decisions
---

# ADR-006: Conditions use the JSONLogic shape with an in-house whitelisted evaluator

> **Status**: Accepted (2026-07-03; revises the earlier revision-2 tech-spec decision to depend on third-party JSONLogic libraries)
> **Date**: 2026-06-20

## TL;DR

Keep the JSONLogic object shape as the on-disk condition format, but evaluate it with a
small interpreter we write ourselves (one in Python, one in TypeScript) covering only a
whitelisted ten-operator subset, because a roughly 40-line evaluator is easier to test
exhaustively and carries no supply-chain risk between a child and machine-generated
content.

## Context

### Problem

Tier-2 stories gate choices on conditions like "you have the lantern." The conditions
come from an LLM, so they are untrusted, and the same condition must evaluate
identically on the Python backend (validation) and in the TypeScript PWA (play). The
whitelist is ten operators (var, !, and, or, ==, !=, <, <=, >, >=).

### Constraints

- **Technical**: backend and client must never disagree on a condition's truth value;
  conditions are untrusted input and must never be executed as code.
- **Business**: this sits directly between a child and generated content, so dependency
  health and divergence risk matter more than saving a few lines of code.

### Significance

A divergence between the validator's and the player's evaluation is exactly the class of
bug nobody tests until a child hits it. The evaluator is small but load-bearing.

## Decision

**We will keep the JSONLogic object shape as the interchange format but evaluate it with
two small in-house interpreters (Python and TypeScript) over a whitelisted subset,
because owning roughly 40 lines twice is safer than a stale dependency for ten
operators.** No string parsing, no custom grammar, no third-party logic library, no
`eval`. Content is data, never executed.

### Rationale

The earlier call to lean on `json-logic-js` and a PyPI JSONLogic package does not hold
up: the JavaScript package has sat near-dormant for roughly two years, and the Python
package naming is muddled across stale and forked variants. The shape (for example,
`{"==": [{"var": "has_lantern"}, true]}`) is still the right interchange format: an LLM
emits a JSON tree more reliably than an expression string, and it needs no parser.
Because every variable carries an `initial` value, published stories should not expose
a missing-variable case; the runtime still falls back to false defensively for
malformed state.

## Options Considered

### Option 1: JSONLogic shape + in-house evaluator ✓

**Pros**:

- ✅ No parser; JSON-native; tiny surface; no dependency; we control semantics on both
  sides.

**Cons**:

- ❌ We write and test roughly 40 lines twice and must keep them in lockstep.

### Option 2: Third-party JSONLogic libraries

**Pros**:

- ✅ No code to write.

**Cons**:

- ❌ `json-logic-js` roughly two years stale; PyPI naming muddled; two implementations
  can disagree on truthiness. Dependency risk and divergence for ten operators.

### Option 3: Custom string DSL (lark/PEG) or CEL

A custom grammar adds a parser and drift risk between backend and client parsers for no
gain over JSON. CEL is more expressive and sandboxed but a heavier runtime than the
stories need; kept as a future escape hatch, not v1.

## Consequences

### Positive

- ✅ No parser, no logic dependency, no code-execution surface.
- ✅ Conditions stay statically checkable (operator membership, declared-variable
  references, type agreement).

### Trade-offs

- ⚠️ We own two small evaluators and must keep them in lockstep. Mitigation: a pinned
  conformance fixture set (condition plus `var_state` to expected boolean) runs through
  both evaluators and asserts identical results.

### Technical Debt

- Whitelisted operators: `var`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `and`, `or`, `!`.
  Everything else is rejected by the validator. Each evaluator must be total: any
  schema-valid condition returns a boolean without raising.

## Implementation

### Components Affected

1. **Python evaluator**: used by the validator.
2. **TypeScript evaluator**: used by the PWA player.
3. **Conformance corpus**: shared fixtures asserting identical results across both.

### Testing Strategy

- Unit: property-test each evaluator (Hypothesis in Python, fast-check in TypeScript)
  for totality on schema-valid trees.
- Conformance: the shared fixture set keeps the validator and player from diverging.

## Validation

### Success Criteria

- [ ] Both evaluators return identical results on the full conformance corpus.
- [ ] Any non-whitelisted operator is rejected by the validator.

### Review Schedule

- Initial: Phase 0 (PL-06 conformance fixtures) and Phase 1 player.
- Ongoing: if the operator whitelist ever changes.

## Related

- [ADR-001](./adr-001-story-format-json-storybook.md): the format that carries
  conditions.
- [Tech Spec: Story DSL condition format](../tech-spec.md#story-dsl-condition-format-adr-006)
