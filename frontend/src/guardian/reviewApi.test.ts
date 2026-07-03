import { describe, expect, it, vi } from 'vitest'

import { makeReviewApi } from './reviewApi'

function fakeAxios() {
  return {
    get: vi.fn(),
    post: vi.fn(),
  }
}

describe('makeReviewApi', () => {
  it('lists the queue from GET /v1/review-queue', async () => {
    const api = fakeAxios()
    api.get.mockResolvedValue({ data: { items: [{ storybook_id: 's1' }] } })
    const result = await makeReviewApi(api as never).queue()
    expect(api.get).toHaveBeenCalledWith('/v1/review-queue')
    expect(result).toEqual([{ storybook_id: 's1' }])
  })

  it('fetches the surface with a version param when given', async () => {
    const api = fakeAxios()
    api.get.mockResolvedValue({ data: { storybook_id: 's1', version: 2 } })
    await makeReviewApi(api as never).surface('s1', 2)
    expect(api.get).toHaveBeenCalledWith('/v1/storybooks/s1/review', {
      params: { version: 2 },
    })
  })

  it('fetches the surface with no config when version is omitted', async () => {
    const api = fakeAxios()
    api.get.mockResolvedValue({ data: { storybook_id: 's1', version: 1 } })
    await makeReviewApi(api as never).surface('s1')
    expect(api.get).toHaveBeenCalledWith('/v1/storybooks/s1/review', undefined)
  })

  it('approves via POST /v1/storybooks/:id/approve', async () => {
    const api = fakeAxios()
    api.post.mockResolvedValue({ data: { id: 's1', status: 'published' } })
    const result = await makeReviewApi(api as never).approve('s1')
    expect(api.post).toHaveBeenCalledWith('/v1/storybooks/s1/approve')
    expect(result.status).toBe('published')
  })

  it('sends back via POST /v1/storybooks/:id/send-back with a reason', async () => {
    const api = fakeAxios()
    api.post.mockResolvedValue({ data: { id: 's1', status: 'needs_revision' } })
    await makeReviewApi(api as never).sendBack('s1', 'too scary')
    expect(api.post).toHaveBeenCalledWith('/v1/storybooks/s1/send-back', {
      reason: 'too scary',
    })
  })

  it('stillProcessing returns an empty list until C4a-5 wires the jobs endpoint', async () => {
    const api = fakeAxios()
    const result = await makeReviewApi(api as never).stillProcessing()
    expect(result).toEqual([])
    expect(api.get).not.toHaveBeenCalled()
  })
})
