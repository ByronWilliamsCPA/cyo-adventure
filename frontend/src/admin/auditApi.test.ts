import { describe, expect, it, vi } from 'vitest'

import { makeAuditApi } from './auditApi'

function fakeAxios() {
  return {
    get: vi.fn(),
  }
}

describe('makeAuditApi', () => {
  it('lists with no filters', async () => {
    const api = fakeAxios()
    api.get.mockResolvedValue({
      data: { events: [], limit: 50, offset: 0, has_more: false },
    })
    const result = await makeAuditApi(api as never).list()
    expect(api.get).toHaveBeenCalledWith('/v1/admin/audit', {
      params: {
        kind: undefined,
        actor_id: undefined,
        storybook_id: undefined,
        profile_id: undefined,
        since: undefined,
        until: undefined,
        limit: undefined,
        offset: undefined,
      },
    })
    expect(result.events).toEqual([])
  })

  it('forwards every filter to the matching snake_case query param', async () => {
    const api = fakeAxios()
    api.get.mockResolvedValue({
      data: { events: [], limit: 25, offset: 25, has_more: true },
    })
    await makeAuditApi(api as never).list({
      kind: 'book_assigned',
      actorId: 'actor-1',
      storybookId: 'the-lighthouse-mystery',
      profileId: 'profile-1',
      since: '2026-01-01',
      until: '2026-12-31',
      limit: 25,
      offset: 25,
    })
    expect(api.get).toHaveBeenCalledWith('/v1/admin/audit', {
      params: {
        kind: 'book_assigned',
        actor_id: 'actor-1',
        storybook_id: 'the-lighthouse-mystery',
        profile_id: 'profile-1',
        since: '2026-01-01',
        until: '2026-12-31',
        limit: 25,
        offset: 25,
      },
    })
  })

  it('returns the parsed response body', async () => {
    const api = fakeAxios()
    const body = {
      events: [
        {
          id: 'evt-1',
          occurred_at: '2026-01-01T00:00:00Z',
          actor_id: 'user-1',
          actor_role: 'admin',
          entity_type: 'user',
          entity_id: 'user-2',
          event_type: 'user_managed',
          from_state: null,
          to_state: null,
          payload: { action: 'deactivate' },
        },
      ],
      limit: 50,
      offset: 0,
      has_more: false,
    }
    api.get.mockResolvedValue({ data: body })
    const result = await makeAuditApi(api as never).list()
    expect(result).toEqual(body)
  })
})
