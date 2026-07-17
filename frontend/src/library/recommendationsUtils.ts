import type { RecommendationItem, RecommendationRing } from './recommendationsApi'

/** One book's decoration data for the K17 chip: the first recommender in feed
 * order (name and ring, which drives the "Cousin" prefix), plus a count of
 * any additional recommenders for the same book. */
export interface RecommendationSummary {
  firstName: string
  firstRing: RecommendationRing
  moreCount: number
}

/**
 * Groups a flat recommendations feed by storybook id, keeping only the first
 * recommender (feed order) plus a running count of the rest. This mirrors
 * the shape BookCard needs for the "Maya loved this and 2 more" chip; it is
 * a pure grouping step, no gating or filtering (the backend is the trust
 * boundary for which recommendations a profile is allowed to see, per
 * ADR-016's dual-guardian-consent rule for ring 2).
 */
export function summarizeRecommendations(
  items: RecommendationItem[]
): Map<string, RecommendationSummary> {
  const byBook = new Map<string, RecommendationSummary>()
  for (const item of items) {
    const existing = byBook.get(item.storybook_id)
    if (existing) {
      existing.moreCount += 1
    } else {
      byBook.set(item.storybook_id, {
        firstName: item.recommender_name,
        firstRing: item.ring,
        moreCount: 0,
      })
    }
  }
  return byBook
}
