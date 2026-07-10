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

  it('approves via POST /v1/storybooks/:id/approve with the chosen visibility', async () => {
    const api = fakeAxios()
    api.post.mockResolvedValue({ data: { id: 's1', status: 'published' } })
    const result = await makeReviewApi(api as never).approve('s1', 'family')
    expect(api.post).toHaveBeenCalledWith('/v1/storybooks/s1/approve', {
      visibility: 'family',
    })
    expect(result.status).toBe('published')
  })

  it('approves with catalog visibility when selected', async () => {
    const api = fakeAxios()
    api.post.mockResolvedValue({ data: { id: 's1', status: 'published' } })
    await makeReviewApi(api as never).approve('s1', 'catalog')
    expect(api.post).toHaveBeenCalledWith('/v1/storybooks/s1/approve', {
      visibility: 'catalog',
    })
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
          // A reachable backend row: title null AND premise_snippet "" (the
          // backend default is `str = ""`). The `|| 'Untitled request'` fallback
          // must catch the empty string so the console never renders a blank row.
          { id: 'j2', status: 'queued', title: null, premise_snippet: '' },
          // An empty-string title (not null) must also fall through: title is
          // chained with `||`, not `??`, so "" does not render a blank row.
          { id: 'j3', status: 'running', title: '', premise_snippet: 'from snippet' },
        ],
      },
    })
    const result = await makeReviewApi(api as never).stillProcessing()
    expect(result).toEqual([
      { job_id: 'j1', title: 'snippet only', status: 'running' },
      { job_id: 'j2', title: 'Untitled request', status: 'queued' },
      { job_id: 'j3', title: 'from snippet', status: 'running' },
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

  it('stillProcessing resolves to [] on a 403 without logging (expected admin outcome)', async () => {
    const api = fakeAxios()
    // A real axios 403: the endpoint is guardian-only and the admin reviewer
    // gets a 403, which must resolve to [] silently so it never sinks the queue.
    api.get.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const result = await makeReviewApi(api as never).stillProcessing()
    expect(result).toEqual([])
    // Deletion-sensitive: a 403 is expected and must not be logged as a failure.
    expect(errorSpy).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('stillProcessing resolves to [] on a non-403 error but logs it (not silent)', async () => {
    const api = fakeAxios()
    api.get.mockRejectedValue(new Error('network down'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const result = await makeReviewApi(api as never).stillProcessing()
    expect(result).toEqual([])
    // Deletion-sensitive: a 500/network failure must surface in the log rather
    // than degrade to an indistinguishable "nothing generating" with no trace.
    expect(errorSpy).toHaveBeenCalledOnce()
    errorSpy.mockRestore()
  })
})
