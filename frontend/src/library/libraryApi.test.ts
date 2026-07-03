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
          },
        ],
      },
    })
    const api = makeLibraryApi(fakeAxios({ get } as Partial<AxiosInstance>))
    const items = await api.list('p1')
    expect(get).toHaveBeenCalledWith('/v1/library', { params: { profile_id: 'p1' } })
    expect(items[0].title).toBe('The Lantern')
    expect(items[0].progress?.nodes_visited).toBe(3)
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
    const api = makeLibraryApi(fakeAxios({ post } as Partial<AxiosInstance>))
    const view = await api.rate('p1', 's1', 5)
    expect(post).toHaveBeenCalledWith('/v1/ratings', {
      profile_id: 'p1',
      storybook_id: 's1',
      value: 5,
    })
    expect(view.value).toBe(5)
  })
})
