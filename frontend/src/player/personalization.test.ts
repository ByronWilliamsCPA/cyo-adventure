import { describe, expect, it } from 'vitest'

import {
  SENTINEL_PATTERN_FALLBACK,
  resolvePersonalization,
  type ValuesPayload,
} from './personalization'

function payload(overrides: Partial<ValuesPayload> = {}): ValuesPayload {
  return {
    subject_profile_id: 'p_1',
    ring: 1,
    policy_version: 'ring1-no-consent-required',
    resolved_at: '2026-07-29T00:00:00Z',
    values: { protagonist_first_name: 'Maya' },
    sentinel_pattern: SENTINEL_PATTERN_FALLBACK,
    slot_bindings: { HERO: 'protagonist_first_name' },
    ...overrides,
  }
}

describe('resolvePersonalization', () => {
  it('substitutes a bound slot with its value', () => {
    expect(resolvePersonalization('Then {~HERO:Explorer~} ran.', payload())).toBe('Then Maya ran.')
  })

  it('substitutes every occurrence, not only the first', () => {
    expect(
      resolvePersonalization('{~HERO:Explorer~} called. {~HERO:Explorer~} waited.', payload())
    ).toBe('Maya called. Maya waited.')
  })

  it('falls back to the generic word when the payload has no value for the field', () => {
    expect(resolvePersonalization('Then {~HERO:Explorer~} ran.', payload({ values: {} }))).toBe(
      'Then Explorer ran.'
    )
  })

  it('falls back to the generic word when the slot id is not bound', () => {
    expect(resolvePersonalization('Then {~SIDEKICK:the pup~} barked.', payload())).toBe(
      'Then the pup barked.'
    )
  })

  it('falls back to the generic word on an empty-string value', () => {
    expect(
      resolvePersonalization(
        'Then {~HERO:Explorer~} ran.',
        payload({ values: { protagonist_first_name: '' } })
      )
    ).toBe('Then Explorer ran.')
  })

  it('strips every marker to its generic word when there is no payload', () => {
    expect(resolvePersonalization('Then {~HERO:Explorer~} ran.', null)).toBe('Then Explorer ran.')
  })

  it('is idempotent on already-resolved text', () => {
    const once = resolvePersonalization('Then {~HERO:Explorer~} ran.', payload())
    expect(resolvePersonalization(once, payload())).toBe(once)
  })

  it('leaves text with no markers untouched', () => {
    expect(resolvePersonalization('Nothing to resolve here.', payload())).toBe(
      'Nothing to resolve here.'
    )
  })

  it('returns the empty string unchanged', () => {
    expect(resolvePersonalization('', payload())).toBe('')
    expect(resolvePersonalization('', null)).toBe('')
  })

  it('strips a malformed marker rather than showing it to a child', () => {
    // The at-rest integrity gate fails closed on malformed tokens, so a published
    // blob cannot carry one. This is defence in depth for the one thing ADR-023
    // section 10 forbids absolutely: a marker on a kid-facing surface.
    expect(resolvePersonalization('Then {~HERO:Explorer} ran.', payload())).toBe(
      'Then Explorer ran.'
    )
  })

  it('strips a malformed marker with no colon to its inner text', () => {
    expect(resolvePersonalization('Then {~HERO} ran.', payload())).toBe('Then HERO ran.')
  })

  it('prefers the payload pattern over the fallback', () => {
    // A payload carrying a pattern that matches nothing must leave canonical
    // markers to the malformed pass rather than silently using the fallback:
    // proves the payload's pattern is the one actually compiled.
    const resolved = resolvePersonalization(
      'Then {~HERO:Explorer~} ran.',
      payload({ sentinel_pattern: 'zzz-matches-nothing' })
    )
    expect(resolved).toBe('Then Explorer ran.')
    expect(resolved).not.toContain('Maya')
  })

  it('degrades to the fallback pattern when the payload pattern is not a valid regex', () => {
    const resolved = resolvePersonalization(
      'Then {~HERO:Explorer~} ran.',
      payload({ sentinel_pattern: '(unclosed' })
    )
    expect(resolved).toBe('Then Maya ran.')
  })

  it('resolves a ring-2 payload identically to a ring-1 one', () => {
    // Design plan 8.3: one route serves both rings and the client never branches
    // on which. A resolver that read `payload.ring` would be a latent
    // divergence; this asserts it does not.
    const ring1 = payload({ ring: 1 })
    const ring2 = payload({ ring: 2, policy_version: 'ring2-2026-07' })
    const text = 'Then {~HERO:Explorer~} ran.'
    expect(resolvePersonalization(text, ring2)).toBe(resolvePersonalization(text, ring1))
  })
})
