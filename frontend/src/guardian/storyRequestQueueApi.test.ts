import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeStoryRequestQueueApi } from './storyRequestQueueApi'

function fakeAxios(data: unknown) {
  const get = vi.fn().mockResolvedValue({ data })
  const post = vi.fn().mockResolvedValue({ data })
  return { api: { get, post } as unknown as AxiosInstance, get, post }
}

describe('makeStoryRequestQueueApi', () => {
  it('listPending returns the requests array', async () => {
    const requestData = {
      requests: [
        {
          id: 'req1',
          profile_id: 'prof1',
          status: 'pending',
          request_text: 'Please write a story about dragons',
          moderation_flags: [],
          created_at: '2026-07-04T10:00:00Z',
        },
      ],
    }
    const { api, get } = fakeAxios(requestData)
    const result = await makeStoryRequestQueueApi(api).listPending()
    expect(get).toHaveBeenCalledWith('/v1/story-requests?status=pending')
    expect(result).toEqual(requestData.requests)
  })

  it('approve posts to the approve endpoint and returns the body', async () => {
    const approveData = {
      id: 'req1',
      status: 'approved',
      concept_id: 'concept1',
      job_id: 'job123',
    }
    const { api, post } = fakeAxios(approveData)
    const result = await makeStoryRequestQueueApi(api).approve('req1')
    expect(post).toHaveBeenCalledWith('/v1/story-requests/req1/approve')
    expect(result).toEqual(approveData)
  })

  it('decline posts to the decline endpoint and returns the body', async () => {
    const declineData = { id: 'req1', status: 'declined' }
    const { api, post } = fakeAxios(declineData)
    const result = await makeStoryRequestQueueApi(api).decline('req1')
    expect(post).toHaveBeenCalledWith('/v1/story-requests/req1/decline')
    expect(result).toEqual(declineData)
  })
})
