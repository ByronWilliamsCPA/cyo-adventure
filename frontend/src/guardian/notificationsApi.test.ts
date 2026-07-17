import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeNotificationsApi } from './notificationsApi'

function fakeAxios(data: unknown) {
  const get = vi.fn().mockResolvedValue({ data })
  return { api: { get } as unknown as AxiosInstance, get }
}

const ITEM = {
  id: 'evt-1',
  occurred_at: '2026-07-15T12:00:00Z',
  kind: 'story_ready',
  severity: 'info' as const,
  title: 'A story is ready',
  body: 'It has been published.',
  storybook_id: 's1',
  request_id: null,
  profile_id: 'p1',
}

describe('makeNotificationsApi list', () => {
  it('gets the notification feed with no params', async () => {
    const { api, get } = fakeAxios({ notifications: [ITEM] })
    const result = await makeNotificationsApi(api).list()
    expect(get).toHaveBeenCalledWith('/v1/notifications', {
      params: { since: undefined, limit: undefined },
    })
    expect(result).toEqual([ITEM])
  })

  it('passes since and limit through as query params', async () => {
    const { api, get } = fakeAxios({ notifications: [] })
    await makeNotificationsApi(api).list({ since: '2026-07-15T00:00:00Z', limit: 30 })
    expect(get).toHaveBeenCalledWith('/v1/notifications', {
      params: { since: '2026-07-15T00:00:00Z', limit: 30 },
    })
  })

  it('degrades a malformed body to an empty array', async () => {
    const { api } = fakeAxios({})
    const result = await makeNotificationsApi(api).list()
    expect(result).toEqual([])
  })
})
