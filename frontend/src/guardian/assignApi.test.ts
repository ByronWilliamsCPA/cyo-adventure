import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeAssignApi } from './assignApi'

function fakeAxios(data: unknown) {
  const get = vi.fn().mockResolvedValue({ data })
  const post = vi.fn().mockResolvedValue({ data })
  return { api: { get, post } as unknown as AxiosInstance, get, post }
}

describe('makeAssignApi', () => {
  it('get returns the profile_ids for a storybook', async () => {
    const { api, get } = fakeAxios({ storybook_id: 's1', profile_ids: ['p1', 'p2'] })
    const result = await makeAssignApi(api).get('s1')
    expect(get).toHaveBeenCalledWith('/v1/storybooks/s1/assignments')
    expect(result).toEqual(['p1', 'p2'])
  })

  it('add posts profile_ids and returns the full list', async () => {
    const { api, post } = fakeAxios({ storybook_id: 's1', profile_ids: ['p1', 'p2'] })
    const result = await makeAssignApi(api).add('s1', ['p2'])
    expect(post).toHaveBeenCalledWith('/v1/storybooks/s1/assignments', {
      profile_ids: ['p2'],
    })
    expect(result).toEqual(['p1', 'p2'])
  })
})

describe('makeAssignApi contentSummary', () => {
  it('gets the content summary for a storybook', async () => {
    const data = {
      storybook_id: 's1',
      version: 1,
      screened: true,
      summary: {
        count: 1,
        hard_block: false,
        soft_flag: true,
        repaired: false,
        reviewer_independent: true,
      },
      flagged_count: 2,
      findings: [{ category: 'coherence', verdict: 'advisory', message: 'disjoint' }],
    }
    const { api, get } = fakeAxios(data)
    const result = await makeAssignApi(api).contentSummary('s1')
    expect(get).toHaveBeenCalledWith('/v1/storybooks/s1/content-summary')
    expect(result.flagged_count).toBe(2)
    expect(result.findings[0].category).toBe('coherence')
  })
})
