import { describe, expect, it } from 'vitest'
import type { RecommendationItem } from './recommendationsApi'
import { summarizeRecommendations } from './recommendationsUtils'

function item(overrides: Partial<RecommendationItem> = {}): RecommendationItem {
  return {
    storybook_id: 's1',
    title: 'The Lantern',
    cover_url: null,
    recommender_name: 'Maya',
    rating: 5,
    ring: 'family',
    ...overrides,
  }
}

describe('summarizeRecommendations', () => {
  it('returns an empty map for an empty feed', () => {
    expect(summarizeRecommendations([]).size).toBe(0)
  })

  it('summarizes a single recommendation with no "more" count', () => {
    const summary = summarizeRecommendations([item()])
    expect(summary.get('s1')).toEqual({ firstName: 'Maya', firstRing: 'family', moreCount: 0 })
  })

  it('keeps the first recommender in feed order and counts the rest', () => {
    const summary = summarizeRecommendations([
      item({ recommender_name: 'Maya' }),
      item({ recommender_name: 'Leo', ring: 'connection' }),
      item({ recommender_name: 'Priya' }),
    ])
    expect(summary.get('s1')).toEqual({ firstName: 'Maya', firstRing: 'family', moreCount: 2 })
  })

  it('groups independently per storybook id', () => {
    const summary = summarizeRecommendations([
      item({ storybook_id: 's1', recommender_name: 'Maya' }),
      item({ storybook_id: 's2', recommender_name: 'Leo', ring: 'connection' }),
    ])
    expect(summary.get('s1')).toEqual({ firstName: 'Maya', firstRing: 'family', moreCount: 0 })
    expect(summary.get('s2')).toEqual({ firstName: 'Leo', firstRing: 'connection', moreCount: 0 })
  })
})
