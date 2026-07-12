import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeChildSessionApi } from './childSessionApi'

function fakeAxios(overrides: Partial<AxiosInstance>): AxiosInstance {
  return overrides as AxiosInstance
}

describe('makeChildSessionApi', () => {
  it('posts the profile id and returns the minted session view', async () => {
    const post = vi.fn().mockResolvedValue({
      data: { token: 'tok-1', expires_at: '2026-07-11T12:00:00Z', profile_id: 'p1' },
    })
    const api = makeChildSessionApi(fakeAxios({ post }))

    const result = await api.mint('p1')

    expect(post).toHaveBeenCalledWith('/v1/child-sessions', { profile_id: 'p1' })
    expect(result).toEqual({
      token: 'tok-1',
      expires_at: '2026-07-11T12:00:00Z',
      profile_id: 'p1',
    })
  })

  it('propagates a rejection unchanged', async () => {
    const error = new Error('mint failed')
    const post = vi.fn().mockRejectedValue(error)
    const api = makeChildSessionApi(fakeAxios({ post }))

    await expect(api.mint('p1')).rejects.toBe(error)
  })
})
