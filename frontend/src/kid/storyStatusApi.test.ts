import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeStoryStatusApi } from './storyStatusApi'

function fakeAxios(overrides: Partial<AxiosInstance>): AxiosInstance {
  return overrides as AxiosInstance
}

describe('makeStoryStatusApi', () => {
  it('fetches the bulk status list and returns it as-is', async () => {
    const statuses = [
      { profile_id: 'p1', has_new_story: true },
      { profile_id: 'p2', has_new_story: false },
    ]
    const get = vi.fn().mockResolvedValue({ data: { statuses } })
    const api = makeStoryStatusApi(fakeAxios({ get }))

    const result = await api.list()

    expect(get).toHaveBeenCalledWith('/v1/profiles/story-status')
    expect(result).toEqual(statuses)
  })

  it('returns an empty list when there are no listable profiles', async () => {
    const get = vi.fn().mockResolvedValue({ data: { statuses: [] } })
    const api = makeStoryStatusApi(fakeAxios({ get }))

    await expect(api.list()).resolves.toEqual([])
  })

  it('tolerates a missing statuses array (degrades to no pills, never throws)', async () => {
    const get = vi.fn().mockResolvedValue({ data: {} })
    const api = makeStoryStatusApi(fakeAxios({ get }))

    await expect(api.list()).resolves.toEqual([])
  })

  it('propagates a rejection unchanged', async () => {
    const error = new Error('story status fetch failed')
    const get = vi.fn().mockRejectedValue(error)
    const api = makeStoryStatusApi(fakeAxios({ get }))

    await expect(api.list()).rejects.toBe(error)
  })
})
