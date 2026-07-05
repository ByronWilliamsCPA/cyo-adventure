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

  it('create strips guardian-facing fields from the full wire response', async () => {
    // The create endpoint returns the same full row shape as the list endpoint;
    // the adapter must strip it at runtime, not just hide it behind a type cast.
    const { api } = fakeAxios({
      id: 'req1',
      status: 'pending',
      profile_id: 'p1',
      request_text: 'Please write a dragon story',
      created_at: '2026-07-04T12:00:00Z',
      moderation_flags: [{ category: 'language', verdict: 'clean', message: '' }],
    })
    const result = await makeKidStoryRequestApi(api).create('p1', 'Please write a dragon story')
    // Returned object must carry ONLY the kid-safe keys.
    expect(Object.keys(result).sort()).toEqual(['id', 'status'])
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

  it('listForProfile strips guardian-facing fields from full wire response', async () => {
    // Realistic full wire fixture with all backend fields
    const { api } = fakeAxios({
      requests: [
        {
          id: 'req1',
          status: 'pending',
          profile_id: 'p1',
          request_text: 'Please write a dragon story',
          created_at: '2026-07-04T12:00:00Z',
          moderation_flags: [
            { category: 'language', verdict: 'clean', message: '' },
          ],
        },
        {
          id: 'req2',
          status: 'approved',
          profile_id: 'p1',
          request_text: 'Can you make a wizard adventure',
          created_at: '2026-07-04T12:15:00Z',
          moderation_flags: [],
        },
      ],
    })
    const result = await makeKidStoryRequestApi(api).listForProfile('p1')
    // Verify returned objects contain ONLY id and status keys
    expect(result).toHaveLength(2)
    expect(Object.keys(result[0]).sort()).toEqual(['id', 'status'])
    expect(Object.keys(result[1]).sort()).toEqual(['id', 'status'])
    // Verify the safe fields are present
    expect(result[0]).toEqual({ id: 'req1', status: 'pending' })
    expect(result[1]).toEqual({ id: 'req2', status: 'approved' })
  })
})
