import { describe, expect, it, vi } from 'vitest'
import type { AxiosInstance } from 'axios'
import { makeLibraryApi } from './libraryApi'

function fakeAxios(overrides: Partial<AxiosInstance>): AxiosInstance {
  return overrides as AxiosInstance
}

describe('makeLibraryApi', () => {
  it('lists the library for a profile', async () => {
    const get = vi.fn().mockResolvedValue({
      data: {
        stories: [
          {
            id: 's1',
            title: 'The Lantern',
            version: 2,
            age_band: '6-8',
            tier: 1,
            reading_level_target: 2,
            node_count: 12,
            rating: 4,
            progress: {
              current_node: 'n2',
              nodes_visited: 3,
              updated_at: '2026-07-01T00:00:00Z',
            },
            series_id: 'ser1',
            book_index: 2,
          },
        ],
      },
    })
    const api = makeLibraryApi(fakeAxios({ get }))
    const items = await api.list('p1')
    expect(get).toHaveBeenCalledWith('/v1/library', { params: { profile_id: 'p1' } })
    expect(items[0].title).toBe('The Lantern')
    expect(items[0].progress?.nodes_visited).toBe(3)
    expect(items[0].series_id).toBe('ser1')
    expect(items[0].book_index).toBe(2)
  })

  it('posts a rating upsert', async () => {
    const post = vi.fn().mockResolvedValue({
      data: {
        child_profile_id: 'p1',
        storybook_id: 's1',
        value: 5,
        rated_at: '2026-07-02T00:00:00Z',
        updated_at: '2026-07-02T00:00:00Z',
      },
    })
    const api = makeLibraryApi(fakeAxios({ post }))
    const view = await api.rate('p1', 's1', 5)
    expect(post).toHaveBeenCalledWith('/v1/ratings', {
      profile_id: 'p1',
      storybook_id: 's1',
      value: 5,
    })
    expect(view.value).toBe(5)
  })

  describe('history (K6 endings tracker)', () => {
    it('fetches the reading-history rows for a profile', async () => {
      const get = vi.fn().mockResolvedValue({
        data: {
          profile_id: 'p1',
          books: [
            {
              storybook_id: 's1',
              title: 'The Lantern',
              endings_found: 2,
              ending_ids: ['e1', 'e2'],
              total_endings: 5,
              in_progress: true,
              last_activity_at: '2026-07-01T00:00:00Z',
            },
          ],
        },
      })
      const api = makeLibraryApi(fakeAxios({ get }))
      const rows = await api.history('p1')
      expect(get).toHaveBeenCalledWith('/v1/reading-history/p1')
      expect(rows).toHaveLength(1)
      expect(rows[0]).toMatchObject({ storybook_id: 's1', endings_found: 2, total_endings: 5 })
    })

    it('degrades to an empty list when the response has no books array', async () => {
      const get = vi.fn().mockResolvedValue({ data: { profile_id: 'p1' } })
      const api = makeLibraryApi(fakeAxios({ get }))
      const rows = await api.history('p1')
      expect(rows).toEqual([])
    })
  })
})
