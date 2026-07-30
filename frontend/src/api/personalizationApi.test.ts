import { describe, expect, it, vi } from 'vitest'

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

describe('makeFetchPersonalizationValues', () => {
  it('returns the payload from the values route', async () => {
    const get = vi.fn().mockResolvedValue({ data: payload })
    const fetch = makeFetchPersonalizationValues({ get } as never)

    await expect(fetch('s_demo')).resolves.toEqual(payload)
    expect(get).toHaveBeenCalledWith('/v1/storybooks/s_demo/personalization-values')
  })

  it('resolves null on any failure rather than throwing', async () => {
    const get = vi.fn().mockRejectedValue(new Error('boom'))
    const fetch = makeFetchPersonalizationValues({ get } as never)

    await expect(fetch('s_demo')).resolves.toBeNull()
  })

  it('resolves null on a transport failure so the reader still renders generic', async () => {
    const get = vi.fn().mockRejectedValue({ isAxiosError: true, response: undefined })
    const fetch = makeFetchPersonalizationValues({ get } as never)

    await expect(fetch('s_demo')).resolves.toBeNull()
  })
})
