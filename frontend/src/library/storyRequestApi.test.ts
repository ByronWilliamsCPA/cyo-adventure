import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeKidStoryRequestApi } from './storyRequestApi'

function fakeAxios(data: unknown) {
  const get = vi.fn().mockResolvedValue({ data })
  const post = vi.fn().mockResolvedValue({ data })
  return { api: { get, post } as unknown as AxiosInstance, get, post }
}

describe('makeKidStoryRequestApi', () => {
  it('create posts a story request and returns id and status', async () => {
    const { api, post } = fakeAxios({ id: 'req1', status: 'pending' })
    const result = await makeKidStoryRequestApi(api).create('p1', 'Please write a dragon story')
    expect(post).toHaveBeenCalledWith('/v1/story-requests', {
      profile_id: 'p1',
      request_text: 'Please write a dragon story',
    })
    expect(result).toEqual({ id: 'req1', status: 'pending' })
  })

  it('listForProfile gets the requests for a profile and returns the list', async () => {
    const { api, get } = fakeAxios({
      requests: [
        { id: 'req1', status: 'pending' },
        { id: 'req2', status: 'approved' },
      ],
    })
    const result = await makeKidStoryRequestApi(api).listForProfile('p1')
    expect(get).toHaveBeenCalledWith('/v1/story-requests?profile_id=p1')
    expect(result).toEqual([
      { id: 'req1', status: 'pending' },
      { id: 'req2', status: 'approved' },
    ])
  })

  it('listForProfile handles an empty request list', async () => {
    const { api, get } = fakeAxios({ requests: [] })
    const result = await makeKidStoryRequestApi(api).listForProfile('p1')
    expect(get).toHaveBeenCalledWith('/v1/story-requests?profile_id=p1')
    expect(result).toEqual([])
  })

  it('create handles declined status', async () => {
    const { api } = fakeAxios({ id: 'req3', status: 'declined' })
    const result = await makeKidStoryRequestApi(api).create('p2', 'Another story idea')
    expect(result.status).toBe('declined')
  })

  it('listForProfile includes all possible statuses', async () => {
    const { api } = fakeAxios({
      requests: [
        { id: 'req1', status: 'pending' },
        { id: 'req2', status: 'approved' },
        { id: 'req3', status: 'declined' },
        { id: 'req4', status: 'blocked' },
      ],
    })
    const result = await makeKidStoryRequestApi(api).listForProfile('p1')
    expect(result).toHaveLength(4)
    expect(result.map((r) => r.status)).toEqual([
      'pending',
      'approved',
      'declined',
      'blocked',
    ])
  })
})
