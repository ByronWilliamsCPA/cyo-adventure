import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'

import { makeFetchPersonalizationValues } from './personalizationApi'
import type { ValuesPayload } from '../player/personalization'

const payload: ValuesPayload = {
  subject_profile_id: 'p_1',
  ring: 1,
  policy_version: 'ring1-no-consent-required',
  resolved_at: '2026-07-29T00:00:00Z',
  values: { protagonist_first_name: 'Maya' },
  sentinel_pattern: "\\{~([A-Z][A-Z0-9_]*):([^{}<>'~]+)~\\}",
  slot_bindings: { HERO: 'protagonist_first_name' },
}

// Failures resolve to null silently for the child, but warn on the console so
// a persistent 500 is diagnosable; keep those warns out of test output.
let warnSpy: MockInstance
beforeEach(() => {
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
})
afterEach(() => {
  warnSpy.mockRestore()
})

describe('makeFetchPersonalizationValues', () => {
  it('returns the payload from the values route without warning', async () => {
    const get = vi.fn().mockResolvedValue({ data: payload })
    const fetch = makeFetchPersonalizationValues({ get } as never)

    await expect(fetch('s_demo')).resolves.toEqual(payload)
    expect(get).toHaveBeenCalledWith('/v1/storybooks/s_demo/personalization-values')
    expect(warnSpy).not.toHaveBeenCalled()
  })

  it('resolves null on any failure rather than throwing, and warns with the failure kind', async () => {
    const get = vi.fn().mockRejectedValue(new Error('boom'))
    const fetch = makeFetchPersonalizationValues({ get } as never)

    await expect(fetch('s_demo')).resolves.toBeNull()
    expect(warnSpy).toHaveBeenCalledTimes(1)
    const [message, detail] = warnSpy.mock.calls[0] as [string, Record<string, unknown>]
    expect(message).toContain('values fetch failed')
    expect(detail).toEqual({ storybookId: 's_demo', kind: 'non-http' })
  })

  it('resolves null on a transport failure so the reader still renders generic', async () => {
    const get = vi.fn().mockRejectedValue({ isAxiosError: true, response: undefined })
    const fetch = makeFetchPersonalizationValues({ get } as never)

    await expect(fetch('s_demo')).resolves.toBeNull()
    expect(warnSpy).toHaveBeenCalledTimes(1)
    expect(warnSpy.mock.calls[0][1]).toEqual({ storybookId: 's_demo', kind: 'network' })
  })

  it('warns with the HTTP status for a server failure, so a persistent 500 is distinguishable from not-opted-in', async () => {
    const get = vi
      .fn()
      .mockRejectedValue({ isAxiosError: true, response: { status: 500, data: payload } })
    const fetch = makeFetchPersonalizationValues({ get } as never)

    await expect(fetch('s_demo')).resolves.toBeNull()
    expect(warnSpy).toHaveBeenCalledTimes(1)
    expect(warnSpy.mock.calls[0][1]).toEqual({ storybookId: 's_demo', kind: 500 })
    // Value-free: never slot values, resolved text, or payload contents.
    expect(JSON.stringify(warnSpy.mock.calls[0])).not.toContain('Maya')
  })
})
