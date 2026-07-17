import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@ds/components/Button'
import { ProgressBar } from '@ds/components/ProgressBar'
import { EndingsBadge } from './EndingsBadge'
import { RecommendationChip } from './RecommendationChip'
import type { LibraryItemView } from './libraryApi'
import { StarRating } from './StarRating'
import { percentComplete } from './bookCardUtils'
import { coverGradient } from './coverPalette'
import type { RecommendationSummary } from './recommendationsUtils'

export interface BookCardProps {
  item: LibraryItemView
  profileId: string
  /** Hero variant: full-width card with a labelled progress bar (wireframe 4.2). */
  hero?: boolean
  onRate: (storybookId: string, value: number) => void
  onContinue?: (item: LibraryItemView) => void
  /** K6 endings tracker: this book's reading-history row, when known. Absent
   * (undefined) whenever the profile's history fetch is still loading,
   * failed, or has no row for this book yet; EndingsBadge itself also
   * withholds a total_endings: 0 book, so a not-yet-published-metadata book
   * never shows a misleading "0 of 0". */
  endings?: { found: number; total: number }
  /** K17 recommendations feed (ADR-016 rings 1-2): this book's grouped
   * recommenders, when known. Absent (undefined) whenever the profile's
   * recommendations fetch is still loading, failed, or has no entry for this
   * book; the chip is withheld rather than shown as an error either way. */
  recommendation?: RecommendationSummary
}

export function BookCard({
  item,
  profileId,
  hero = false,
  onRate,
  onContinue,
  endings,
  recommendation,
}: BookCardProps) {
  const readTo = `/read/${profileId}/${item.id}/${item.version}`
  const pct = percentComplete(item)
  const started = item.progress !== null
  // A broken or expired cover URL falls back to the letter tile instead of
  // rendering a broken-image icon.
  const [coverError, setCoverError] = useState(false)
  const showImage = Boolean(item.cover_url) && !coverError
  return (
    <div className={hero ? 'book-card book-card--hero' : 'book-card'}>
      <Link className="book-card__link" to={readTo}>
        <div
          className={showImage ? 'book-card__tile' : 'book-card__tile book-card__tile--painted'}
          style={showImage ? undefined : { background: coverGradient(item.title) }}
          aria-hidden="true"
        >
          {showImage ? (
            <img
              className="book-card__cover"
              src={item.cover_url ?? undefined}
              alt=""
              onError={() => setCoverError(true)}
            />
          ) : (
            <span className="book-card__letter">{item.title.charAt(0).toUpperCase()}</span>
          )}
        </div>
        <h3 className="book-card__title">{item.title}</h3>
        {hero ? (
          <ProgressBar
            value={pct}
            label={
              item.progress
                ? `${item.progress.nodes_visited} of ${item.node_count} pages explored`
                : 'Not started'
            }
            showLabel
          />
        ) : started ? (
          <ProgressBar value={pct} />
        ) : (
          <div className="book-card__not-started">
            <ProgressBar value={0} />
            <span className="book-card__not-started-label">Not started</span>
          </div>
        )}
      </Link>
      {/* K6 endings tracker: only for a book the child has actually opened
          (started) or already found an ending in; a never-touched book has
          nothing to track yet. */}
      {(started || (endings && endings.found > 0)) && endings ? (
        <EndingsBadge found={endings.found} total={endings.total} />
      ) : null}
      {recommendation ? <RecommendationChip summary={recommendation} /> : null}
      <StarRating
        value={item.rating}
        onRate={(value) => onRate(item.id, value)}
        bookTitle={item.title}
      />
      {item.series_id !== null && onContinue ? (
        <Button
          variant="ghost"
          aria-label={`Ask for the next book: ${item.title}`}
          onClick={() => onContinue(item)}
        >
          Ask for the next book
        </Button>
      ) : null}
    </div>
  )
}
