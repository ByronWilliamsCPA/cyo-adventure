---
title: "Condition Evaluator Specification"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Specify the JSONLogic shape, whitelisted operators, exclusions, totality contract, and conformance fixture format for the in-house condition evaluator."
tags:
  - planning
  - specifications
  - architecture
component: Development-Tools
source: "tech-spec.md section 'Story DSL: condition format'; adr/adr-006-conditions-inhouse-evaluator.md"
---

# Condition Evaluator Specification

> **Status**: Draft | **Version**: 1.0 | **Updated**: 2026-06-20
> **Binding on**: Python evaluator (validator) and TypeScript evaluator (PWA player)
> **Related ADR**: [ADR-006](./adr/adr-006-conditions-inhouse-evaluator.md)

---

## Purpose

The condition evaluator is a small, total interpreter over a whitelisted subset of the
JSONLogic object shape. It runs in two implementations: Python (backend validator) and
TypeScript (PWA player). This document specifies both implementations. A divergence between
the two constitutes a conformance failure.

---

## 1. Condition Object Shape

A condition is a JSON object following the JSONLogic structural convention: a single-key
object whose key is the operator name and whose value is the operand or operand array.

```json
{ "operator": operand_or_array }
```

Conditions are stored as-is in `choice.condition` in the Storybook JSON blob. They are not
stored as strings; there is no parser. An LLM emits a JSON tree; the evaluator interprets it
directly.

**Examples**:

```json
// "you have the lantern"
{ "==": [ { "var": "has_lantern" }, true ] }

// "courage is at least 3 and you do not have the curse"
{ "and": [
  { ">=": [ { "var": "courage" }, 3 ] },
  { "!": { "var": "has_curse" } }
] }

// choice is always visible (absent condition)
// (no condition field means always true; not a JSON null)
```

---

## 2. Whitelisted Operator Table

The following operators are the complete whitelist. Any operator not in this table is rejected
by the Layer-1 validator (rule L1-6) at schema validation time, before any evaluation occurs.

| Operator | Arity | Operand form | Semantics |
|----------|-------|--------------|-----------|
| `var` | 1 | `{ "var": "name" }` | Resolve the named variable from `var_state`. Returns the stored value (bool or int). The variable must be declared in `variables`; `var` always resolves because every variable carries an `initial` value. |
| `==` | 2 | `{ "==": [a, b] }` | Strict equality. Returns true if `a` and `b` are equal by value and type. |
| `!=` | 2 | `{ "!=": [a, b] }` | Strict inequality. Returns true if `a` and `b` are not equal by value and type. |
| `<` | 2 | `{ "<": [a, b] }` | Returns true if `a` is strictly less than `b`. Both operands must resolve to numeric (int) values. |
| `<=` | 2 | `{ "<=": [a, b] }` | Returns true if `a` is less than or equal to `b`. Both operands must resolve to numeric (int) values. |
| `>` | 2 | `{ ">": [a, b] }` | Returns true if `a` is strictly greater than `b`. Both operands must resolve to numeric (int) values. |
| `>=` | 2 | `{ ">=": [a, b] }` | Returns true if `a` is greater than or equal to `b`. Both operands must resolve to numeric (int) values. |
| `and` | 2+ | `{ "and": [a, b, ...] }` | Logical conjunction. Returns true if every operand is truthy. Evaluates all operands (not short-circuit); a schema-valid condition tree has no side effects, so eager evaluation is safe and simplifies the totality contract. |
| `or` | 2+ | `{ "or": [a, b, ...] }` | Logical disjunction. Returns true if at least one operand is truthy. Evaluates all operands (not short-circuit); same rationale as `and`. |
| `!` | 1 | `{ "!": a }` | Logical negation. Returns true if `a` is falsy. The operand may be a `var` expression or a nested condition object. |

**Total operator count**: 10 (var, ==, !=, <, <=, >, >=, and, or, !).

**Note on `!` operand form**: `!` takes a single operand, not an array. `{ "!": {"var":
"has_curse"} }` is valid. `{ "!": [{"var": "has_curse"}] }` is not valid and must be rejected
by the validator.

### Comparison operand grammar

A comparison operand is exactly one of: a `{ "var": name }` reference, or a bool/int/str
literal. Three shape rules close divergence classes between the two evaluators (see
`docs/planning/evaluator-runtime-equivalence.md` for the full derivation):

1. **No nested conditions as comparison operands.** Both evaluators resolve a non-var
   object operand to literal `false` instead of evaluating it, so a construct like
   `{ "==": [{"var": "a"}, {"!": {"var": "b"}}] }` would parse but silently ignore the
   nested condition's value. The validator rejects it.
2. **Ordering operators reject boolean literals.** A bool can never resolve to a numeric
   value (ordering operands must resolve to int, per the table above), so an ordering
   comparison against a boolean literal is statically meaningless and is rejected at
   shape validation. Equality against boolean literals remains the canonical Tier-2
   shape and stays valid. At runtime both evaluators additionally fail closed (return
   `false`) if a boolean ever reaches an ordering operator through any path.
3. **Int literals are bounded to |n| <= 1,000,000,000** (`MAX_ABS_STORY_INT`). Python
   evaluates integers exactly at any size; the TypeScript player computes in IEEE-754
   doubles, exact only to 2^53 - 1. The bound (shared with variable declarations and
   effect values) keeps schema-representable literals float64-exact with a wide
   margin and materially reduces divergence risk for engine-reachable values.

---

## 3. Excluded Operators

The following operators are explicitly excluded by policy. The validator rejects any condition
tree that contains them.

| Excluded category | Excluded operators | Reason for exclusion |
|-------------------|--------------------|----------------------|
| Arithmetic | `+`, `-`, `*`, `/`, `%` | Conditions gate choices; arithmetic belongs in effects (inc/dec). Including it here would allow authors to compute derived values inside conditions, which complicates static analysis and makes bound checking harder. |
| Membership | `in` | Not needed for boolean state; adds string/array semantics the evaluator does not need to handle. |
| String operations | `cat`, `substr` | Story conditions operate on bool and int variables only. String comparison is unnecessary; string values in variables are not supported in v1. |
| Array reductions | `map`, `reduce`, `filter`, `all`, `some`, `none`, `merge` | No array-valued variables in v1; adding array ops would require a type system and widen the attack surface. |
| Conditional/ternary | `if` | `if` is a ternary that returns a value, not a boolean predicate. It would allow conditions to produce non-boolean results, violating the totality contract. Branching is already expressed by choice visibility; `if` adds nothing. |
| Missing/default | `missing`, `missing_some`, `default` | Every variable has an `initial` value, so `var` always resolves. The missing-value operators are unnecessary and mask schema errors. |

---

## 4. Totality Contract

**Every schema-valid condition must return a boolean value without raising an exception.**

This contract is maintained by:

1. **Schema validity as precondition**: the Layer-1 validator (L1-6) checks that only
   whitelisted operators appear and that every `var` reference names a declared variable,
   before any evaluation occurs.
2. **`var` always resolves**: every declared variable has an `initial` value. The evaluator
   initialises `var_state` from the Storybook's `variables` array before any node is entered.
   There is no missing-variable case for a schema-valid condition.
3. **Type agreement enforced at schema time**: the validator checks that comparison operands
   agree in type with the declared variable (L1-6). A runtime type mismatch in a schema-valid
   condition is therefore a validator bug, not a runtime case to handle gracefully.
4. **No recursion depth problem**: the JSONLogic object shape is a tree; the evaluator recurses
   over it. Arbitrary nesting depth is theoretically possible, but deeply nested conditions are
   a generator smell. The validator may optionally warn on nesting depth beyond a practical
   limit (e.g., 8 levels), but depth alone does not violate the totality contract.

**If a schema-valid condition raises at runtime**: this is an implementation bug. Log the
condition, the `var_state`, and the exception; surface it as a configuration-walk failure (L2-8)
so the story is not silently published with a broken condition.

---

## 5. Identical-Result Requirement

**The Python and TypeScript evaluators must return identical boolean results for every
schema-valid (condition, var_state) pair.**

This is not a best-effort goal. It is a correctness requirement: the validator and the player
are authoritative for different parts of the lifecycle. If they disagree, a story the validator
passes may dead-end in the player. The conformance fixture corpus (Section 6) is the
enforcement mechanism.

**Implementation note**: the only area where divergence is likely is truthiness. Both
implementations must use strict equality semantics for `==` and `!=`, not JavaScript-style
loose equality. Specifically: `true == 1` must return `false` (strict: different types);
`1 == 1` must return `true`.

---

## 6. Conformance Fixture Format

The conformance corpus is a JSON array. Each entry is an object with three required fields:

```json
[
  {
    "condition": { "==": [ { "var": "has_lantern" }, true ] },
    "var_state": { "has_lantern": false, "courage": 2 },
    "expected": false
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `condition` | Object | A schema-valid JSONLogic condition object. |
| `var_state` | Object | A complete variable state map: all declared variables with values consistent with their declared types and bounds. |
| `expected` | Boolean | The correct boolean result. Both evaluators must return this value. |

**Additional optional fields** (for test readability; not evaluated):

| Field | Type | Description |
|-------|------|-------------|
| `description` | String | Human-readable description of what the fixture tests. |
| `tags` | Array of String | Categories: e.g., `["negation", "bool"]`, `["comparison", "int"]`, `["compound"]`. |

**Corpus requirements**:

- At least one fixture per whitelisted operator.
- At least five fixtures exercising compound conditions (nested `and`/`or`/`!`).
- At least one fixture for each boundary value of a declared `int` variable (at `min`, at
  `max`, one below `min`, one above `max`; the last two confirm the variable was initialised
  in bounds).
- The corpus is pinned in the repository and both CI pipelines run it. A failure in either
  evaluator is a CI blocker.

---

## 7. Example Fixtures

The following three fixtures are normative examples. They must be included in the conformance
corpus verbatim.

**Fixture 1: simple bool equality, true case**

```json
{
  "description": "has_lantern is true; condition checks equality to true",
  "tags": ["bool", "equality"],
  "condition": { "==": [ { "var": "has_lantern" }, true ] },
  "var_state": { "has_lantern": true, "courage": 3 },
  "expected": true
}
```

**Fixture 2: integer comparison with negation, false case**

```json
{
  "description": "courage is 2, which is not >= 3; negation makes the outer condition false",
  "tags": ["int", "comparison", "negation"],
  "condition": {
    "and": [
      { ">=": [ { "var": "courage" }, 3 ] },
      { "!": { "var": "has_curse" } }
    ]
  },
  "var_state": { "has_lantern": true, "courage": 2, "has_curse": false },
  "expected": false
}
```

**Fixture 3: compound or with two false branches**

```json
{
  "description": "neither branch of the or is satisfied; result must be false",
  "tags": ["compound", "or", "bool", "int"],
  "condition": {
    "or": [
      { "==": [ { "var": "has_lantern" }, true ] },
      { ">": [ { "var": "courage" }, 4 ] }
    ]
  },
  "var_state": { "has_lantern": false, "courage": 2, "has_curse": false },
  "expected": false
}
```

---

## 8. Implementation Guidance

Both evaluators should be approximately 40 lines of pure recursive logic. Suggested structure:

```
evaluate(condition, var_state) -> bool
  op = single key of condition object
  if op == "var":    return truthy(var_state.get(condition["var"], false))
  if op == "!":      return not evaluate(condition["!"], var_state)
  if op == "and":    return all(evaluate(c, var_state) for c in condition["and"])
  if op == "or":     return any(evaluate(c, var_state) for c in condition["or"])
  # comparison operators: RESOLVE both sides (never evaluate them), apply operator
  lhs, rhs = condition[op]
  lv = resolve(lhs, var_state)   # {"var": n} -> value; literal -> itself; else false
  rv = resolve(rhs, var_state)
  return apply_comparison(op, lv, rv)

apply_comparison(op, lv, rv) -> bool
  if op == "==": return strict_eq(lv, rv)    # bool and int are distinct types
  if op == "!=": return not strict_eq(lv, rv)
  # ordering: booleans are NOT numeric (Python must exclude bool explicitly,
  # since bool subclasses int); non-int operands fail closed
  if lv or rv is boolean, or either is not an int: return false
  return ordered(op, lv, rv)
```

Comparison operands are resolved, never evaluated: a `{ "var": name }` reference resolves
to the variable's value, a literal to itself, and anything else to `false` (defensive
totality; the shape validator rejects such operands before a story is published).

Literal values (non-object operands such as `true`, `false`, `3`) evaluate to themselves.
The TypeScript implementation must use `===` for strict equality in `==` comparisons.

---

## Related Documents

- [ADR-006: In-house condition evaluator](./adr/adr-006-conditions-inhouse-evaluator.md)
- [Tech Spec: Story DSL condition format](./tech-spec.md#story-dsl-condition-format-adr-006)
- [Story Runtime Semantics v1](./runtime-semantics.md)
- [Validator Rule Catalog](./validator-rules.md)
