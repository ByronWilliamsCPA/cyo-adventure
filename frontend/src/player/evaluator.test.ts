import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import fc from 'fast-check'
import { describe, expect, it } from 'vitest'

import { type Condition, evaluate, type VarState } from './evaluator'

// Read the single shared conformance corpus from the repo root so the TypeScript
// and Python evaluators are tested against the exact same fixtures (no copy).
const here = path.dirname(fileURLToPath(import.meta.url))
const conformancePath = path.resolve(here, '../../../schema/conformance/conditions.json')

interface ConformanceCase {
  name: string
  condition: Condition
  var_state: VarState
  expected: boolean
}

const corpus = JSON.parse(readFileSync(conformancePath, 'utf-8')) as {
  cases: ConformanceCase[]
}

describe('condition evaluator conformance', () => {
  it.each(corpus.cases.map((c) => [c.name, c] as const))(
    'matches expected for %s',
    (_name, testCase) => {
      expect(evaluate(testCase.condition, testCase.var_state)).toBe(testCase.expected)
    }
  )

  it('covers every whitelisted operator', () => {
    const blob = readFileSync(conformancePath, 'utf-8')
    for (const op of ['var', '==', '!=', '<', '<=', '>', '>=', 'and', 'or', '!']) {
      expect(blob).toContain(op)
    }
  })
})

describe('strict equality divergence', () => {
  it('treats true and 1 as not equal (matches Python type-distinct equality)', () => {
    expect(evaluate({ '==': [{ var: 'flag' }, 1] }, { flag: true })).toBe(false)
    expect(evaluate({ '==': [{ var: 'n' }, 1] }, { n: 1 })).toBe(true)
  })
})

// --- Totality property (mirrors the Python Hypothesis test) -------------------

const varNames = ['a', 'b', 'courage', 'trust']

const varState: fc.Arbitrary<VarState> = fc
  .tuple(...varNames.map(() => fc.oneof(fc.boolean(), fc.integer({ min: 0, max: 5 }))))
  .map((values) => Object.fromEntries(varNames.map((n, i) => [n, values[i]])))

const operand: fc.Arbitrary<unknown> = fc.oneof(
  fc.constantFrom(...varNames).map((n) => ({ var: n })),
  fc.boolean(),
  fc.integer({ min: -1, max: 6 })
)

const comparison: fc.Arbitrary<Condition> = fc
  .tuple(fc.constantFrom('==', '!=', '<', '<=', '>', '>='), operand, operand)
  .map(([op, lhs, rhs]) => ({ [op]: [lhs, rhs] }))

const condition: fc.Arbitrary<Condition> = fc.letrec<{ node: Condition }>((tie) => ({
  node: fc.oneof(
    { depthSize: 'small' },
    fc.constantFrom(...varNames).map((n) => ({ var: n })),
    comparison,
    tie('node').map((c) => ({ '!': c })),
    fc.array(tie('node'), { minLength: 2, maxLength: 3 }).map((cs) => ({
      and: cs,
    })),
    fc.array(tie('node'), { minLength: 2, maxLength: 3 }).map((cs) => ({
      or: cs,
    }))
  ),
})).node

describe('evaluator totality', () => {
  it('always returns a boolean for schema-valid conditions', () => {
    fc.assert(
      fc.property(condition, varState, (cond, state) => {
        expect(typeof evaluate(cond, state)).toBe('boolean')
      })
    )
  })
})
