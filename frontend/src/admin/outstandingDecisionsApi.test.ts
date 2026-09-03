import { describe, expect, it, vi } from 'vitest'

import { makeOutstandingDecisionsApi } from './outstandingDecisionsApi'

function fakeAxios() {
  return {
    get: vi.fn(),
    post: vi.fn(),
  }
}

describe('makeOutstandingDecisionsApi', () => {
  it('unwraps the view envelope to the items array', async () => {
    const api = fakeAxios()
    api.get.mockResolvedValue({
      data: {
        items: [
          {
            kind: 'moderation',
            storybook_id: 'the-lighthouse-mystery',
            title: 'The Lighthouse Mystery',
            status: 'published',
            version: 3,
            family_id: 'fam-1',
            age_band: '8-11',
            version_created_at: '2026-07-01T12:00:00Z',
            recallable: true,
            moderation: null,
            cover: null,
          },
        ],
      },
    })
    const items = await makeOutstandingDecisionsApi(api as never).list()
    expect(api.get).toHaveBeenCalledWith('/v1/admin/outstanding-decisions')
    expect(items).toHaveLength(1)
    expect(items[0]?.storybook_id).toBe('the-lighthouse-mystery')
  })

  it('posts the recall to the storybook path with the reason code in the body', async () => {
    const api = fakeAxios()
    api.post.mockResolvedValue({
      data: { storybook_id: 'the-lighthouse-mystery', status: 'in_review' },
    })
    const result = await makeOutstandingDecisionsApi(api as never).recall(
      'the-lighthouse-mystery',
      'threshold_change'
    )
    // The reason code is a body field, not a query param: the API records it on
    // the state-transition event, so a client that sent it as ?reason_code=
    // would publish a recall with no recorded reason.
    expect(api.post).toHaveBeenCalledWith('/v1/storybooks/the-lighthouse-mystery/recall', {
      reason_code: 'threshold_change',
    })
    expect(result.status).toBe('in_review')
  })

  it('lets a failed call reject rather than resolving to an empty list', async () => {
    const api = fakeAxios()
    api.get.mockRejectedValue(new Error('boom'))
    // Pinned because an adapter that swallowed the error would make the page
    // render "Nothing outstanding" during an outage, which is the exact false
    // all-clear this whole surface exists to prevent.
    await expect(makeOutstandingDecisionsApi(api as never).list()).rejects.toThrow('boom')
  })
})
