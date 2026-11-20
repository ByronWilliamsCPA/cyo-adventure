import { useEffect, useRef, useState } from 'react'

import { logApiError } from '../hooks/logApiError'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { StarRating } from '../library/StarRating'
import '../library/library.css'

export interface EndingRatingProps {
  storybookId: string
  /** Kid-facing title, for the star group's accessible label. */
  bookTitle: string
  /** The rating the shelf last knew, or null when unrated or unknown. */
  initialRating: number | null
  rate: (storybookId: string, value: number) => Promise<number>
}

/**
 * The library card's star row, offered again at the moment the feeling is
 * strongest (design review 2026-08-01 section 4.4). Same component, same
 * POST /v1/ratings, and the same rules as BookCard/LibraryPage:
 *
 * - offline, the stars are withheld entirely (the POST needs the network and
 *   a failed save keeps the old value, so an offline tap would silently do
 *   nothing; LibraryPage withholds them on its offline shelf for the same
 *   reason);
 * - the shown value changes only after the save lands, so StarRating's
 *   "got it" pulse means saved;
 * - a failed save keeps the previous value and logs the redacted shape only.
 *
 * Fire-and-forget: nothing on the ending screen waits on this. A slow or
 * failing save never blocks "Try a different choice", "Read again", or
 * leaving.
 */
export function EndingRating({ storybookId, bookTitle, initialRating, rate }: EndingRatingProps) {
  const online = useOnlineStatus()
  const [saved, setSaved] = useState<number | null>(null)
  // `initialRating` can arrive late (the cached shelf lookup resolves after
  // mount); until the child rates here, show whatever the shelf knows.
  const value = saved ?? initialRating
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  if (!online) return null
  return (
    <div className="reader-ending__rating" data-testid="ending-rating">
      <p className="reader-ending__rating-prompt">How did you like this story?</p>
      <StarRating
        value={value}
        bookTitle={bookTitle}
        onRate={(next) => {
          // #ASSUME: timing dependencies: the child can leave (or rewind) the
          // ending screen before the POST settles; the save still completes
          // server-side, and the mounted check keeps a late resolution from
          // setting state on an unmounted component.
          // #VERIFY: Reader.moments.test.tsx "keeps the previous rating when
          // the save fails" and "never blocks the other ending actions while a save
          // is pending".
          rate(storybookId, next)
            .then((stored) => {
              if (mountedRef.current) setSaved(stored)
            })
            .catch((err: unknown) => {
              logApiError('rating save failed', err)
            })
        }}
      />
    </div>
  )
}
