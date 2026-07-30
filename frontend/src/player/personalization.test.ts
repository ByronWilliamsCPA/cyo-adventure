import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'

import {
  SENTINEL_PATTERN_FALLBACK,
  resolvePersonalization,
  stripSentinels,
  type ValuesPayload,
} from './personalization'

// The malformed-residue pass warns (value-free) whenever it strips anything;
// silence it here so residue tests stay quiet, and assert on the spy where the
// warn itself is under test.
let warnSpy: MockInstance
beforeEach(() => {
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
})
afterEach(() => {
  warnSpy.mockRestore()
})

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

  it('strips an unterminated marker at end of text', () => {
    expect(resolvePersonalization('Then {~HERO:Explorer~', payload())).toBe('Then Explorer')
  })

  it('strips an unterminated marker mid-text without eating the surrounding prose', () => {
    expect(resolvePersonalization('Then {~HERO:Explorer~ ran.', payload())).toBe(
      'Then Explorer ran.'
    )
  })

  it('strips a missing-opening-tilde marker', () => {
    expect(resolvePersonalization('Then {HERO:Explorer~} ran.', payload())).toBe(
      'Then Explorer ran.'
    )
  })

  it('strips a brace-embedded forgery without leaving the closer behind', () => {
    // The backend treats this as one whole malformed span (sentinels.py::
    // _closer_end tolerates an embedded balanced brace pair). Before the
    // residue pattern matched it, the span fell through to the unterminated
    // branch, which stops at the inner `{`, so a raw `~}` reached the child.
    const resolved = resolvePersonalization('Then {~HERO:El{evated}~} ran.', payload())
    expect(resolved).not.toMatch(/\{~|~\}/)
    expect(resolved).toBe('Then El{evated} ran.')
  })

  it('strips a brace-embedded forgery that also drops its closing tilde', () => {
    const resolved = resolvePersonalization('Then {~HERO:El{evated}} ran.', payload())
    expect(resolved).not.toMatch(/\{~|~\}/)
    expect(resolved).toBe('Then El{evated} ran.')
  })

  it('leaves an ordinary prose brace span without tildes untouched', () => {
    expect(resolvePersonalization('Pack {not a marker} of gear.', payload())).toBe(
      'Pack {not a marker} of gear.'
    )
  })

  it('is lossy on a near-miss that was never a sentinel (documented, not lossless)', () => {
    // The residue strip keeps only the text after the LAST colon of the
    // interior, so a brace-and-tilde span that was never a sentinel collapses.
    // This asserts the documented lossy behavior so readers cannot assume the
    // strip is lossless.
    expect(resolvePersonalization('A {~note: he waited~} B', payload())).toBe('A  he waited B')
  })

  it('warns once per call, value-free, when malformed residue is stripped', () => {
    resolvePersonalization('Then {~HERO:Explorer} and {~HERO:Explorer} ran.', payload())
    expect(warnSpy).toHaveBeenCalledTimes(1)
    const [message, detail] = warnSpy.mock.calls[0] as [string, Record<string, unknown>]
    expect(message).toContain('malformed sentinel residue')
    expect(detail).toEqual({ residues: 2 })
    // Never the residue text, slot values, resolved text, or payload contents.
    expect(JSON.stringify(warnSpy.mock.calls[0])).not.toContain('Explorer')
    expect(JSON.stringify(warnSpy.mock.calls[0])).not.toContain('Maya')
  })

  it('does not warn when nothing malformed was stripped', () => {
    resolvePersonalization('Then {~HERO:Explorer~} ran.', payload())
    resolvePersonalization('Nothing here.', null)
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('ignores a payload pattern that differs from the pinned constant', () => {
    // Wire-pattern trust: the payload's pattern is honored only when it is
    // character-identical to SENTINEL_PATTERN_FALLBACK (which the backend pin
    // test guarantees in production); any other string is ignored in favor of
    // the constant, so resolution still works and no wire regex is compiled.
    const resolved = resolvePersonalization(
      'Then {~HERO:Explorer~} ran.',
      payload({ sentinel_pattern: 'zzz-matches-nothing' })
    )
    expect(resolved).toBe('Then Maya ran.')
  })

  it('treats an empty-string payload pattern like the fallback (no match-everywhere corruption)', () => {
    const resolved = resolvePersonalization(
      'Then {~HERO:Explorer~} ran.',
      payload({ sentinel_pattern: '' })
    )
    expect(resolved).toBe('Then Maya ran.')
  })

  it('resolves via the fallback when the payload pattern is not a valid regex', () => {
    const resolved = resolvePersonalization(
      'Then {~HERO:Explorer~} ran.',
      payload({ sentinel_pattern: '(unclosed' })
    )
    expect(resolved).toBe('Then Maya ran.')
  })

  it('never compiles a catastrophic-backtracking payload pattern', () => {
    // '(a+)+$' against a long non-matching subject is the classic ReDoS shape;
    // if the wire pattern were compiled and used, this call would hang. It
    // returns promptly with the fallback's resolution instead.
    const text = `Then {~HERO:Explorer~} saw ${'a'.repeat(64)}b.`
    const resolved = resolvePersonalization(text, payload({ sentinel_pattern: '(a+)+$' }))
    expect(resolved).toBe(`Then Maya saw ${'a'.repeat(64)}b.`)
  })

  it('treats a payload with malformed values as absent', () => {
    // The payload arrives from an unvalidated axios cast and from IndexedDB;
    // a junk shape must degrade to the generic read, not throw inside render.
    const bad = { ...payload(), values: 'junk' } as unknown as ValuesPayload
    expect(resolvePersonalization('Then {~HERO:Explorer~} ran.', bad)).toBe('Then Explorer ran.')
  })

  it('treats a payload with malformed slot_bindings as absent, and still strips residue', () => {
    const bad = { ...payload(), slot_bindings: null } as unknown as ValuesPayload
    expect(resolvePersonalization('Then {~HERO:Explorer~} ran. {~HERO:Explorer}', bad)).toBe(
      'Then Explorer ran. Explorer'
    )
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

describe('stripSentinels', () => {
  it('strips canonical markers to their generic words without a payload', () => {
    expect(stripSentinels('Follow {~HERO:Explorer~} now.')).toBe('Follow Explorer now.')
  })

  it('strips malformed residue too', () => {
    expect(stripSentinels('Follow {~HERO:Explorer} now.')).toBe('Follow Explorer now.')
  })

  it('leaves clean text untouched', () => {
    expect(stripSentinels('Follow the path.')).toBe('Follow the path.')
  })
})
