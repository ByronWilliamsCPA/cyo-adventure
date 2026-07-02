---
schema_type: planning
title: "Validator-Runtime Equivalence: divergence audit and closure argument"
description: "Systematic enumeration of every input class where the Python and
  TypeScript condition evaluators and player engines could disagree, the fixes
  and grammar rules that close each class, and the residual risks."
tags:
  - planning
  - research
  - validator
  - conformance
status: active
owner: core-maintainer
purpose: "Record the operator-by-operand-type divergence matrix behind the
  fix/evaluator-runtime-parity change set, so future evaluator or engine edits
  can check themselves against the full input space instead of rediscovering it."
component: Validator
source: "2026-07-01 equivalence audit of storybook/evaluator.py,
  frontend/src/player/evaluator.ts, player/engine.py, frontend/src/player/engine.ts,
  condition-evaluator-spec.md, and schema/conformance/*.json"
---

> **Status**: Active | **Created**: 2026-07-01
> **Companion change set**: branch `fix/evaluator-runtime-parity`

## Why this document exists

The product's keystone guarantee ("every published story provably reaches an
ending") holds only if three components agree about every condition and every
effect: the Python evaluator/engine (used by the Layer-2 validation walk), and
the TypeScript evaluator/engine (used by the child's browser). ADR-006 calls
identical semantics a hard requirement. This audit enumerated the full input
space, found one real divergence (shipped), one silent semantic trap, and one
open divergence class, and closed all three. The conformance corpus at
`schema/conformance/conditions.json` now pins every cell of the matrix below.

## The divergence matrix

Cells marked AGREE were verified identical by construction and pinned by a
conformance case where the behavior is non-obvious. Cells marked DIVERGED or
TRAP are the findings; each names its closure.

### Condition evaluator, by operator and operand type

| Operator | Operand situation | Python (before) | TypeScript | Verdict and closure |
|----------|-------------------|-----------------|------------|---------------------|
| `var` | declared bool/int/str | truthiness via `bool()` | truthiness via `Boolean()` | AGREE (`truthy_int_zero_is_false`, `truthy_nonzero_int_is_true`; `""` falsy, `"0"` truthy on both) |
| `var` | missing variable | `False` default | `false` default | AGREE (`bare_missing_var_is_false`); story-level validation rejects undeclared references, so this is defensive-domain only |
| `!`, `and`, `or` | any, incl. empty list | `not` / `all` / `any` | `!` / `.every` / `.some` | AGREE; even `all([])`/`[].every` match (`true`/`false`), and the shape validator requires length >= 2 anyway |
| `==` `!=` | same types | `_strict_eq` | `===` | AGREE |
| `==` `!=` | bool vs int | `False` (boolness check) | `false` | AGREE (`eq_bool_int_is_false`); this aliasing was already fixed for equality before this audit |
| `==` `!=` | int vs str, bool vs str | `False` | `false` | AGREE (`eq_across_types_is_false`) |
| `< <= > >=` | int vs int | exact comparison | float64 comparison | AGREE within the literal bound (see class 3) |
| `< <= > >=` | **bool anywhere** (literal, bool-valued var, or missing-var default) | **treated as 0/1** because `bool` subclasses `int` | `false` (fail closed) | **DIVERGED (the shipped bug).** Closed three ways: `_ordered` now rejects bools explicitly; the shape validator rejects boolean literals under ordering operators; conformance cases `lt_bool_var_left_is_false`, `gt_bool_var_left_is_false`, `ge_bool_vars_both_sides_is_false`, `le_bool_var_right_is_false`, `lt_missing_var_is_false`, `defensive_lt_false_literal_is_false`, `defensive_gt_true_literal_is_false` pin every route |
| any comparison | str vs int under ordering | `False` | `false` | AGREE (`ordering_on_string_is_false`) |
| any comparison | **nested condition as operand** | resolved to literal `False`, never evaluated | same | **TRAP (agreeing but silently wrong vs author intent).** The spec's old pseudocode even suggested evaluating nested operands, which neither implementation did. Closed: the shape grammar now restricts dict operands to exactly `{"var": name}`; `defensive_nested_condition_operand_is_literal_false_not_evaluated` pins the defensive agreement |
| any comparison | non-literal operand (null, list) | `False` | `false` | AGREE (defensive; shape-invalid) |
| `==` `!=` `< <= > >=` | **int magnitude > 2^53** | exact | rounds to nearest double | **DIVERGED (open class).** Example: var holds 2^53, literal 2^53 + 1: Python `False`, TS `true`. Closed at the gate: every story int literal (condition literals, `Variable.initial/min/max`, `Effect.value`) is now bounded to \|n\| <= 1,000,000,000 (`MAX_ABS_STORY_INT`), and the reading-state save floor rejects submitted values above 2^53 - 1 |

### Player engine, cross-implementation

The engines already share a trace-conformance corpus
(`schema/conformance/player_traces.json`). The audit checked the cells that
corpus cannot express:

| Situation | Python engine | TS engine | Verdict |
|-----------|---------------|-----------|---------|
| `set` with bool value on bounded var | not clamped (bool excluded explicitly) | not clamped (`typeof !== 'number'`) | AGREE |
| `inc`/`dec` with bool value | would treat as 0/1 (`isinstance(value, int)`) | treats as 0 | Differs only defensively; `Effect._check_value` rejects bool values for inc/dec, so the input is unrepresentable |
| `inc`/`dec` on a bool-valued variable | base would be 0/1 | base 0 | Differs only defensively; L1-6 rejects effect/type mismatches before publish |
| clamp semantics (declared min/max) | clamp on set/inc/dec | clamp on set/inc/dec | AGREE |
| arithmetic beyond 2^53 | exact | float64 | Bounded by the same `MAX_ABS_STORY_INT` closure; see residual risks |

## The closure, in one view

1. **Runtime fix** (`storybook/evaluator.py::_ordered`): booleans are not
   numeric for ordering; both implementations now fail closed identically on
   every route (bool literal, bool-valued variable, missing-variable default).
2. **Grammar tightening** (`storybook/condition.py`): comparison operands are
   exactly literals or `{"var": name}` references; ordering operators reject
   boolean literals; int literals bounded to `MAX_ABS_STORY_INT`. Statically
   meaningless or divergence-capable conditions are now unrepresentable, which
   is the same design stance as the rest of the gate.
3. **Schema bounds** (`storybook/models.py`): `Variable.initial/min/max` and
   `Effect.value` share the `MAX_ABS_STORY_INT` bound.
4. **Save floor** (`player/replay.py`): submitted reading-state values above
   2^53 - 1 are rejected, closing the forged-save route into float64 territory
   for unbounded variables.
5. **Corpus** (`schema/conformance/conditions.json`): 27 -> 42 cases; every
   matrix row above that is not obviously identical is pinned by name.

## Why the remaining space cannot diverge

The evaluators are total functions over (condition, var_state). Post-closure:

- **Operator space**: 10 operators, all enumerated above. Unknown operators
  cannot reach the evaluators (shape whitelist) and both fail closed if one did.
- **Operand type space**: `{bool, int, str}` literals, var references (which
  resolve to `{bool, int, str}` or the `False` default), and the defensive
  `False` for anything else. Every ordered pair of resolved types appears in
  the matrix. The only type-coercion asymmetries between the languages are
  bool-as-int (Python) and cross-type `==` looseness (JS); the first is now
  excluded in `_ordered` and was already excluded in `_strict_eq`, the second
  never applies because TS uses `===`.
- **Value space**: int identity is the only value-level divergence channel
  (float64 rounding). All schema-representable ints are within +/-1e9; the
  worst-case engine-reachable magnitude is bounded by
  `initial + path_length x max_effect_value`. Reaching 2^53 from a 1e9 bound
  requires roughly nine million maximum-size effect applications in a single
  session, which is not a realistic user path (see residual risks). Forged
  saves, the only way to inject a large value directly, are rejected at
  2^53 - 1 by the structural floor.
- **Recursion depth**: both evaluators recurse per nesting level. Python's
  recursion limit (~1000) would raise on a pathologically deep condition, but
  `validate_condition` recurses the same structure first, so such a story
  fails validation server-side and can never be published; the TS evaluator
  only ever sees published (validated) stories. Depth is therefore bounded
  before either evaluator runs. A future explicit depth cap in
  `validate_condition` would make this failure graceful instead of a 500 and
  ties into the unimplemented L2-8 walk-failure rule (tracked separately in
  the full-repo review).

## Residual risks, stated honestly

1. **Organic float64 drift on unbounded int variables.** A variable with no
   declared min/max can legitimately exceed 1e9 through repeated effects; the
   engines do not saturate. Magnitude ~9.0e15 (where doubles lose exactness)
   requires ~9,000,000 max-size increments in one session, so this is
   documented rather than coded away. Engine-level saturation at 2^53 - 1 in
   both engines was considered and rejected as over-engineering; revisit only
   if unbounded accumulator variables become a real story pattern.
2. **String variables are tolerated but out of spec.** The spec says string
   variables are not supported in v1, yet both evaluators handle them (and
   agree, including truthiness and cross-type equality). If v1 ever tightens
   this, do it at the schema (Variable model), not in the evaluators.
3. **The corpus is finite.** The matrix argument above is the completeness
   claim; the corpus pins representatives of each cell, not the whole space.
   Any new operator, literal type, or resolution rule MUST add its row to the
   matrix and its cases to the corpus in the same change.

## Maintenance contract

Any PR touching `storybook/evaluator.py`, `storybook/condition.py`,
`frontend/src/player/evaluator.ts`, either engine's effect application, or
`MAX_ABS_STORY_INT` must update the matrix above and add conformance cases for
any new cell. The corpus runs in both CI suites
(`tests/unit/test_evaluator.py`, `frontend/src/player/evaluator.test.ts`)
against the single physical fixture file; that shared file is the enforcement
mechanism, this document is the map.
