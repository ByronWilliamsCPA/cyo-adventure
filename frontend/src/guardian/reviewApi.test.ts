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

  it('sends back via POST /v1/storybooks/:id/send-back with a reason and reason code', async () => {
    const api = fakeAxios()
    api.post.mockResolvedValue({ data: { id: 's1', status: 'needs_revision' } })
    await makeReviewApi(api as never).sendBack('s1', 'too scary', 'safety_concern')
    expect(api.post).toHaveBeenCalledWith('/v1/storybooks/s1/send-back', {
      reason: 'too scary',
      reason_code: 'safety_concern',
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
    expect(result).toEqual({
      jobs: [
        { job_id: 'j1', title: 'The Brave Fox', status: 'queued' },
        { job_id: 'j2', title: 'A robot learns to paint...', status: 'running' },
      ],
      degraded: false,
    })
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
    expect(result.jobs).toEqual([
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
    expect(result.jobs).toEqual([{ job_id: 'j1', title: 'keep me', status: 'queued' }])
  })

  it('stillProcessing reports a 403 as a NON-degraded empty (expected admin outcome)', async () => {
    const api = fakeAxios()
    // A real axios 403: the endpoint is guardian-only and the admin reviewer
    // gets a 403, which must resolve to an empty list silently so it never
    // sinks the queue. It is the truthful answer for that caller, so it is not
    // degraded: marking it degraded would pin a permanent "could not load"
    // notice on the console's primary user.
    api.get.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const result = await makeReviewApi(api as never).stillProcessing()
    expect(result).toEqual({ jobs: [], degraded: false })
    // Deletion-sensitive: a 403 is expected and must not be logged as a failure.
    expect(errorSpy).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('stillProcessing reports a non-403 error as a DEGRADED empty and logs it', async () => {
    const api = fakeAxios()
    api.get.mockRejectedValue(new Error('network down'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const result = await makeReviewApi(api as never).stillProcessing()
    // Deletion-sensitive: the empty list alone cannot distinguish "nothing is
    // generating" from "the load failed". degraded:true is what lets the
    // console say which one it is instead of asserting the former.
    expect(result).toEqual({ jobs: [], degraded: true })
    expect(errorSpy).toHaveBeenCalledOnce()
    errorSpy.mockRestore()
  })

  it('stillProcessing reports a malformed body as a degraded empty, not a silent one', async () => {
    const api = fakeAxios()
    // `jobs` absent entirely: the `.filter` throws inside the try, which is the
    // third way this call used to produce an indistinguishable [].
    api.get.mockResolvedValue({ data: {} })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const result = await makeReviewApi(api as never).stillProcessing()
    expect(result).toEqual({ jobs: [], degraded: true })
    expect(errorSpy).toHaveBeenCalledOnce()
    errorSpy.mockRestore()
  })
})
