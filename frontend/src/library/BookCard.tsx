import { useState } from 'react'
import { Link } from 'react-router'
import { Button } from '@ds/components/Button'
import { ProgressBar } from '@ds/components/ProgressBar'
import { EndingsBadge } from './EndingsBadge'
import { RecommendationChip } from './RecommendationChip'
import type { LibraryItemView } from './libraryApi'
import { StarRating } from './StarRating'
import { isRecentlyPublished, percentComplete } from './bookCardUtils'
import { coverGradient } from './coverPalette'
import type { RecommendationSummary } from './recommendationsUtils'

export interface BookCardProps {
  item: LibraryItemView
  profileId: string
  /** Hero variant: full-width card with a labelled progress bar (wireframe 4.2). */
  hero?: boolean
  onRate: (storybookId: string, value: number) => void
  onContinue?: (item: LibraryItemView) => void
  /**
   * False when the app is offline and this book is not in the local cache, so
   * tapping it could only fail (UX-K1). The card renders as a non-interactive
   * "not downloaded" tile instead of a dead link.
   */
  downloaded?: boolean
  /**
   * Guardian preview-as-child mode (frontend/src/guardian/PreviewAsChildPage.tsx):
   * the cover no longer links into the real kid-token-gated Reader route (a
   * guardian bearer is refused there, see useApi.ts's isKidTokenRoute), and
   * rating is hidden rather than wired to a no-op, so nothing here can write
   * data under the previewed child's identity.
   */
  readOnly?: boolean
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
  /**
   * False on the offline shelf (UX-K1 family): a rating tap there could only
   * fail silently (the POST needs the network and transient failures keep
   * the old value), so the stars are withheld entirely, consistent with the
   * offline suppression of the request affordances.
   */
  ratable?: boolean
  /** W3.2: true once every declared ending in this book has been found
   * (`BookProgressCard.every_path_walked` from `GET /me/progress`).
   * Outranks the plain "Finished!" ribbon with its own warmer state. Absent
   * (undefined/false) whenever the profile's progress fetch is still
   * loading, failed, or this book has not been fully explored. */
  everyPathWalked?: boolean
  /** W3.2: opens the Endings Gallery for this book. Omitted entirely (no
   * button rendered) when the caller has no gallery wired yet, mirroring
   * `onContinue`'s own optional pattern. */
  onOpenGallery?: (storybookId: string) => void
  /**
   * ADR-028 / gate-rework: true when opening this book must show
   * CharacterCreator first (LibraryPage.tsx owns the actual condition:
   * `item.accepts_character === true` and the profile's active character
   * status is exactly `'none'`; this prop is only the resolved boolean, so
   * BookCard never has to know about character state itself). False for
   * every other combination, including `accepts_character` undefined.
   */
  needsCharacter?: boolean
  /**
   * Called instead of navigating when `needsCharacter` is true. The card
   * still renders as a real `<Link>` either way (never a `<button>`): the
   * e2e smoke discovers books with `getByRole('link', { name })`, and a
   * gated book failing to render as a link would break that the same way an
   * ungated one would. The click is intercepted with `preventDefault`
   * instead, so LibraryPage can show the creator first and continue into
   * `readTo` itself once one exists.
   */
  onNeedsCharacter?: (readTo: string, readState?: { personalizationEligible: boolean }) => void
}

export function BookCard({
  item,
  profileId,
  hero = false,
  onRate,
  onContinue,
  downloaded = true,
  readOnly = false,
  endings,
  recommendation,
  ratable = true,
  everyPathWalked = false,
  onOpenGallery,
  needsCharacter = false,
  onNeedsCharacter,
}: BookCardProps) {
  const readTo = `/read/${profileId}/${item.id}/${item.version}`
  // ADR-023 Task D8 (closes Stage C open question 2): thread the library's
  // own personalization_eligible read into the reader's router location
  // state, the same channel ContinueSeries.tsx already uses for its
  // `continuation` key. Undefined (an offline-cached item saved before this
  // field existed) carries no key at all rather than an explicit `false`;
  // ReaderRoute's parser treats an absent key as "unknown", which keeps its
  // values fetch attempted exactly as it was before this field existed.
  const readState =
    item.personalization_eligible === undefined
      ? undefined
      : { personalizationEligible: item.personalization_eligible }
  const pct = percentComplete(item)
  const started = item.progress !== null
  // A broken or expired cover URL falls back to the letter tile instead of
  // rendering a broken-image icon.
  const [coverError, setCoverError] = useState(false)
  const showImage = Boolean(item.cover_url) && !coverError
  // K9 shelf presentation, "what's new" leg: independent of progress state,
  // so it can appear alongside "Not started" or a fresh hero alike.
  const isNew = isRecentlyPublished(item)
  const inner = (
    <>
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
            loading="lazy"
            decoding="async"
            onError={() => setCoverError(true)}
          />
        ) : (
          <span className="book-card__letter">{item.title.charAt(0).toUpperCase()}</span>
        )}
      </div>
      <h3 className="book-card__title">{item.title}</h3>
      {isNew ? <p className="book-card__new-badge">New</p> : null}
      {hero ? (
        <ProgressBar
          // A finished book fills the bar and reads "Finished!" instead of a
          // misleading "N of M pages explored" that under-reports a branching
          // story (a branch touches only a fraction of all nodes) (UX-K5).
          // W3.2: "Every path walked!" outranks the plain "Finished!" once
          // every declared ending has been found.
          value={item.progress?.completed || everyPathWalked ? 100 : pct}
          label={
            everyPathWalked
              ? 'Every path walked!'
              : item.progress?.completed
                ? 'Finished!'
                : item.progress
                  ? `${item.progress.nodes_visited} pages explored`
                  : 'Not started'
          }
          showLabel
        />
      ) : everyPathWalked ? (
        <div className="book-card__every-path">
          <ProgressBar value={100} />
          <span className="book-card__every-path-label">Every path walked!</span>
        </div>
      ) : item.progress?.completed ? (
        <div className="book-card__finished">
          <ProgressBar value={100} />
          <span className="book-card__finished-label">Finished!</span>
        </div>
      ) : started ? (
        <ProgressBar value={pct} />
      ) : (
        <div className="book-card__not-started">
          <ProgressBar value={0} />
          <span className="book-card__not-started-label">Not started</span>
        </div>
      )}
    </>
  )
  return (
    <div className={hero ? 'book-card book-card--hero' : 'book-card'}>
      {readOnly ? (
        <div className="book-card__link book-card__link--offline" aria-disabled="true">
          {inner}
          <span className="book-card__offline-note">Preview only</span>
        </div>
      ) : downloaded ? (
        <Link
          className="book-card__link"
          to={readTo}
          state={readState}
          onClick={
            needsCharacter
              ? (event) => {
                  event.preventDefault()
                  onNeedsCharacter?.(readTo, readState)
                }
              : undefined
          }
        >
          {inner}
        </Link>
      ) : (
        <div className="book-card__link book-card__link--offline" aria-disabled="true">
          {inner}
          <span className="book-card__offline-note">Needs internet to open</span>
        </div>
      )}
      {/* K6 endings tracker: only for a book the child has actually opened
          (started) or already found an ending in; a never-touched book has
          nothing to track yet. */}
      {(started || (endings && endings.found > 0)) && endings ? (
        <EndingsBadge found={endings.found} total={endings.total} />
      ) : null}
      {/* W3.2: the Endings Gallery entry point. Only offered once there is
          something to show (mirrors the endings badge's own started/found
          gate above); omitted entirely when the caller has no gallery
          wired (onOpenGallery undefined). */}
      {onOpenGallery && (started || (endings && endings.found > 0)) && endings ? (
        <button
          type="button"
          className="book-card__gallery-button"
          data-testid="open-endings-gallery"
          onClick={() => onOpenGallery(item.id)}
        >
          See your endings
        </button>
      ) : null}
      {recommendation ? <RecommendationChip summary={recommendation} /> : null}
      {readOnly || !ratable ? null : (
        <StarRating
          value={item.rating}
          onRate={(value) => onRate(item.id, value)}
          bookTitle={item.title}
        />
      )}
      {!readOnly && item.series_id !== null && onContinue ? (
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
