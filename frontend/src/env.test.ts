import { describe, expect, it, vi } from 'vitest'

import { flagEnabled, isPersonalizationEnabled } from './env'

// flagEnabled exists to dodge the Boolean("false") === true trap: Vite exposes
// every env var as a string, so a bare Boolean() coercion treats the literal
// "false" as on. The implemented contract is deliberately narrow: ONLY the exact
// lowercase string "true" is on. It is case-SENSITIVE ("TRUE"/"True" are off)
// and does NOT honor the common truthy aliases "1"/"yes"/"on". These cases
// mirror the source exactly (value === 'true'); they are not aspirational.
describe('flagEnabled', () => {
  it.each([
    ['true', true],
    ['false', false],
    // "1" is a truthy alias in many flag systems; this one rejects it.
    ['1', false],
    ['0', false],
    // Case-sensitive: only the lowercase literal counts.
    ['TRUE', false],
    ['True', false],
    // Aliases that other flag conventions accept but this one does not.
    ['yes', false],
    ['on', false],
    // Empty string and unset both read as off (no accidental truthiness).
    ['', false],
    [undefined, false],
    // Any unrelated value is off.
    ['enabled', false],
    ['  true  ', false],
  ] as const)('flagEnabled(%o) -> %s', (value, expected) => {
    expect(flagEnabled(value)).toBe(expected)
  })
})

describe('isPersonalizationEnabled', () => {
  it('is off when the flag is unset', () => {
    expect(isPersonalizationEnabled()).toBe(false)
  })

  it('is off for the string "false"', () => {
    vi.stubEnv('VITE_FEATURE_PERSONALIZATION', 'false')
    try {
      expect(isPersonalizationEnabled()).toBe(false)
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it('is on only for the literal string "true"', () => {
    vi.stubEnv('VITE_FEATURE_PERSONALIZATION', 'true')
    try {
      // Guard: the helper reads import.meta.env (see src/test/setup.ts), so
      // confirm the stub landed there and not only on process.env. Copied from
      // LoginPage.test.tsx's VITE_ENABLE_APPLE_OAUTH guard, which exists for the
      // same reason.
      expect(import.meta.env.VITE_FEATURE_PERSONALIZATION).toBe('true')
      expect(isPersonalizationEnabled()).toBe(true)
    } finally {
      vi.unstubAllEnvs()
    }
  })
})
