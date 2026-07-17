import type { AxiosInstance } from 'axios'
import { describe, expect, it, vi } from 'vitest'

import { makeReadingApi } from './readingApi'

function fakeAxios(data: unknown) {
  const get = vi.fn().mockResolvedValue({ data })
  return { api: { get } as unknown as AxiosInstance, get }
}

describe('makeReadingApi familySummary', () => {
  it('gets the family reading summary and returns the children array', async () => {
    const children = [
      {
        profile_id: 'p1',
        display_name: 'Reader A',
        books_started: 3,
        books_finished: 1,
        total_endings_found: 2,
        last_activity_at: '2026-07-15T12:00:00Z',
      },
    ]
    const { api, get } = fakeAxios({ children })
    const result = await makeReadingApi(api).familySummary()
    expect(get).toHaveBeenCalledWith('/v1/families/me/reading-summary')
    expect(result).toEqual(children)
  })

  it('returns an empty array for a childless family', async () => {
    const { api } = fakeAxios({ children: [] })
    const result = await makeReadingApi(api).familySummary()
    expect(result).toEqual([])
  })
})

describe('makeReadingApi history', () => {
  it('gets one profile reading history and returns the books array', async () => {
    const books = [
      {
        storybook_id: 's1',
        title: 'The Lantern',
        endings_found: 1,
        ending_ids: ['end-a'],
        total_endings: 3,
        in_progress: true,
        last_activity_at: '2026-07-15T12:00:00Z',
      },
    ]
    const { api, get } = fakeAxios({ profile_id: 'p1', books })
    const result = await makeReadingApi(api).history('p1')
    expect(get).toHaveBeenCalledWith('/v1/reading-history/p1')
    expect(result).toEqual(books)
  })
})
