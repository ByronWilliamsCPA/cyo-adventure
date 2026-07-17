import { describe, expect, it, vi } from 'vitest'
import type { AxiosInstance } from 'axios'
import { makeRecommendationsApi } from './recommendationsApi'

function fakeAxios(overrides: Partial<AxiosInstance>): AxiosInstance {
  return overrides as AxiosInstance
}

describe('makeRecommendationsApi', () => {
  it('fetches the recommendations feed for a profile', async () => {
    const get = vi.fn().mockResolvedValue({
      data: {
        items: [
          {
            storybook_id: 's1',
            title: 'The Lantern',
            cover_url: 'https://cdn/lantern.webp',
            recommender_name: 'Maya',
            rating: 5,
            ring: 'family',
          },
        ],
      },
    })
    const api = makeRecommendationsApi(fakeAxios({ get }))
    const items = await api.list('p1')
    expect(get).toHaveBeenCalledWith('/v1/recommendations/p1')
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({
      storybook_id: 's1',
      recommender_name: 'Maya',
      ring: 'family',
    })
  })

  it('degrades to an empty list when the response has no items array', async () => {
    const get = vi.fn().mockResolvedValue({ data: {} })
    const api = makeRecommendationsApi(fakeAxios({ get }))
    const items = await api.list('p1')
    expect(items).toEqual([])
  })

  it('degrades to an empty list when items is not an array', async () => {
    const get = vi.fn().mockResolvedValue({ data: { items: 'not-an-array' } })
    const api = makeRecommendationsApi(fakeAxios({ get }))
    const items = await api.list('p1')
    expect(items).toEqual([])
  })
})
