import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeRescreenApi } from './rescreenApi'

function fakeAxios(data: unknown) {
  const post = vi.fn().mockResolvedValue({ data })
  const api = { post } as unknown as AxiosInstance
  return { api, post }
}

const SUMMARY = {
  checked: 1,
  passed: 0,
  flagged: 1,
  errored: 0,
  results: [
    {
      storybook_id: 's1',
      version: 3,
      outcome: 'flagged',
      reasons: ['band_profile: reading level exceeds threshold'],
      error: null,
    },
  ],
}

describe('makeRescreenApi', () => {
  it('scopes the sweep to a single storybook id', async () => {
    const { api, post } = fakeAxios(SUMMARY)
    const result = await makeRescreenApi(api).triggerForStorybook('s1')
    expect(post).toHaveBeenCalledWith('/v1/admin/rescreen', { storybook_ids: ['s1'] })
    expect(result).toEqual(SUMMARY)
  })

  it('propagates a backend rejection to the caller', async () => {
    const post = vi.fn().mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    const api = { post } as unknown as AxiosInstance
    await expect(makeRescreenApi(api).triggerForStorybook('s1')).rejects.toMatchObject({
      response: { status: 403 },
    })
  })
})
