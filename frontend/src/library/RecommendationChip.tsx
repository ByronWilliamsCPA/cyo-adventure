import type { RecommendationSummary } from './recommendationsUtils'

export interface RecommendationChipProps {
  summary: RecommendationSummary
}

/**
 * K17 (ADR-016 rings 1 and 2): a small warm chip naming who in the family,
 * or in a guardian-connected family, loved this book. "Cousin" only prefixes
 * a connection-ring recommender; a family-ring recommender shows by first
 * name alone. A second-or-later recommender on the same book collapses into
 * "and N more" rather than listing every name.
 *
 * The heart glyph is decorative only (aria-hidden); the visible sentence is
 * the sole accessible name, so no separate aria-label is needed.
 *
 * ADR-016: this is a read-only decoration, never a message channel. There is
 * no reply, send, or any other affordance here; tapping the chip does
 * nothing beyond whatever the surrounding card already does (open the book).
 */
export function RecommendationChip({ summary }: RecommendationChipProps) {
  const { firstName, firstRing, moreCount } = summary
  const label = firstRing === 'connection' ? `Cousin ${firstName}` : firstName
  const text = moreCount > 0 ? `${label} loved this and ${moreCount} more` : `${label} loved this`
  return (
    <p className="recommendation-chip">
      <span className="recommendation-chip__glyph" aria-hidden="true">
        ♥
      </span>
      <span className="recommendation-chip__text">{text}</span>
    </p>
  )
}
