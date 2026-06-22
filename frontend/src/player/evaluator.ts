/**
 * Total evaluator for the whitelisted condition DSL (ADR-006).
 *
 * This is the TypeScript side of the cross-implementation contract. It must
 * return the identical boolean to the Python evaluator
 * (`src/cyo_adventure/storybook/evaluator.py`) for every schema-valid
 * `(condition, varState)` pair; the shared conformance corpus at
 * `schema/conformance/conditions.json` proves it.
 *
 * The evaluator is total: every schema-valid condition returns a boolean and
 * never throws. Equality is strict (`===`), so `true === 1` is `false`, matching
 * the Python evaluator's type-distinct equality. Ordering comparisons on
 * non-numeric operands return `false` rather than throwing.
 */

export type VarValue = boolean | number | string
export type VarState = Record<string, VarValue>

/** A JSONLogic condition node restricted to the whitelisted operators. */
export type Condition = Record<string, unknown>

const BOOLEAN_NARY = new Set(['and', 'or'])

/**
 * Evaluate a shape-validated condition against a variable state.
 *
 * @param condition - A shape-validated condition object.
 * @param varState - The current value of every declared variable.
 * @returns The boolean value of the condition.
 */
export function evaluate(condition: Condition, varState: VarState): boolean {
  const [operator, operand] = Object.entries(condition)[0]
  if (operator === 'var') {
    return truthy(lookup(operand as string, varState))
  }
  if (operator === '!') {
    return !evaluate(operand as Condition, varState)
  }
  if (BOOLEAN_NARY.has(operator)) {
    const clauses = operand as Condition[]
    const results = clauses.map((clause) => evaluate(clause, varState))
    return operator === 'and' ? results.every(Boolean) : results.some(Boolean)
  }
  const [lhs, rhs] = operand as unknown[]
  return compare(operator, resolve(lhs, varState), resolve(rhs, varState))
}

/** Read a variable's value, defaulting to `false` when absent. */
function lookup(name: string, varState: VarState): VarValue {
  return Object.prototype.hasOwnProperty.call(varState, name) ? varState[name] : false
}

/** Coerce a variable value to a boolean. */
function truthy(value: VarValue): boolean {
  return Boolean(value)
}

/**
 * Resolve a comparison operand to a concrete value: a `{var}` reference resolves
 * to the variable's value, a literal resolves to itself, anything else to
 * `false` (preserving totality).
 */
function resolve(operand: unknown, varState: VarState): VarValue {
  if (operand !== null && typeof operand === 'object') {
    const name = (operand as Record<string, unknown>).var
    if (typeof name === 'string') {
      return lookup(name, varState)
    }
    return false
  }
  if (typeof operand === 'boolean' || typeof operand === 'number' || typeof operand === 'string') {
    return operand
  }
  return false
}

/** Apply a comparison operator with strict equality and numeric-only ordering. */
function compare(operator: string, left: VarValue, right: VarValue): boolean {
  if (operator === '==') {
    return left === right
  }
  if (operator === '!=') {
    return left !== right
  }
  return ordered(operator, left, right)
}

/** Apply an ordering operator, returning `false` on non-numeric operands. */
function ordered(operator: string, left: VarValue, right: VarValue): boolean {
  if (typeof left !== 'number' || typeof right !== 'number') {
    return false
  }
  switch (operator) {
    case '<':
      return left < right
    case '<=':
      return left <= right
    case '>':
      return left > right
    case '>=':
      return left >= right
    default:
      // Unknown operator: fail closed (matches the Python evaluator) rather than
      // computing an arbitrary comparison.
      return false
  }
}
