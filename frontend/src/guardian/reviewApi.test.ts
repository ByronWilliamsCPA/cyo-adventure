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

  it('stillProcessing lists queued/running jobs from GET /v1/generation-jobs', async () => {
    const api = fakeAxios()
    api.get.mockResolvedValue({
      data: {
        jobs: [
          {
            id: 'j1',
            status: 'queued',
            title: 'The Brave Fox',
            premise_snippet: 'A fox sets out...',
          },
          {
            id: 'j2',
            status: 'running',
            title: null,
            premise_snippet: 'A robot learns to paint...',
          },
        ],
      },
    })
    const result = await makeReviewApi(api as never).stillProcessing()
    expect(api.get).toHaveBeenCalledWith('/v1/generation-jobs')
    expect(result).toEqual([
      { job_id: 'j1', title: 'The Brave Fox', status: 'queued' },
      { job_id: 'j2', title: 'A robot learns to paint...', status: 'running' },
    ])
  })

  it('stillProcessing falls back to premise snippet then a generic label for the title', async () => {
    const api = fakeAxios()
    api.get.mockResolvedValue({
      data: {
        jobs: [
          { id: 'j1', status: 'running', title: null, premise_snippet: 'snippet only' },
          // A malformed row missing premise_snippet exercises the final generic
          // fallback under the nullish-coalescing mapping.
          { id: 'j2', status: 'queued', title: null },
        ],
      },
    })
    const result = await makeReviewApi(api as never).stillProcessing()
    expect(result).toEqual([
      { job_id: 'j1', title: 'snippet only', status: 'running' },
      { job_id: 'j2', title: 'Untitled request', status: 'queued' },
    ])
  })

  it('stillProcessing excludes needs_review, passed, and failed jobs', async () => {
    const api = fakeAxios()
    api.get.mockResolvedValue({
      data: {
        jobs: [
          { id: 'j1', status: 'queued', title: 'keep me', premise_snippet: 'p' },
          { id: 'j2', status: 'needs_review', title: 'drop', premise_snippet: 'p' },
          { id: 'j3', status: 'passed', title: 'drop', premise_snippet: 'p' },
          { id: 'j4', status: 'failed', title: 'drop', premise_snippet: 'p' },
        ],
      },
    })
    const result = await makeReviewApi(api as never).stillProcessing()
    expect(result).toEqual([{ job_id: 'j1', title: 'keep me', status: 'queued' }])
  })

  it('stillProcessing resolves to [] on a 403 so it never sinks the console load', async () => {
    const api = fakeAxios()
    api.get.mockRejectedValue({ response: { status: 403 } })
    const result = await makeReviewApi(api as never).stillProcessing()
    expect(result).toEqual([])
  })

  it('stillProcessing resolves to [] on a generic error rather than throwing', async () => {
    const api = fakeAxios()
    api.get.mockRejectedValue(new Error('network down'))
    const result = await makeReviewApi(api as never).stillProcessing()
    expect(result).toEqual([])
  })
})
