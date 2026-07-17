/**
 * K6 endings tracker, ending-screen half: "You found ending N of M! Read
 * again to find more." Mirrors ContinueSeries.tsx's pattern (fetch once on
 * mount, best-effort, absence is the only fallback for every failure or
 * miss) rather than threading the reading-history payload down from
 * ReaderPage: the ending screen is the only place in the reader that needs
 * it, so a small self-contained lookup keeps Reader.tsx's props list from
 * growing for a single consumer.
 */

import { useEffect, useState } from 'react'

import type { ReadingHistoryItem } from '../client/types.gen'

export interface EndingsProgressProps {
  profileId: string
  storybookId: string
  fetchReadingHistory: (profileId: string) => Promise<ReadingHistoryItem[]>
}

// #ASSUME: timing dependencies: this fetch fires the moment the ending
// screen mounts, which can be BEFORE the just-reached ending's completion
// POST (ReaderPage's fire-and-forget recordCompletion, see handleComplete)
// has been recorded server-side. A same-session race can under-report by
// one ending (showing last visit's count, not this one).
// #VERIFY: acceptable per the K6 spec ("best-effort... on fetch failure show
// nothing"); the count self-corrects on the next visit to this screen or the
// library shelf. Never over-reports, so a child is never told they found
// more endings than they actually have.
export function EndingsProgress({
  profileId,
  storybookId,
  fetchReadingHistory,
}: EndingsProgressProps) {
  const [item, setItem] = useState<ReadingHistoryItem | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchReadingHistory(profileId)
      .then((books) => {
        if (cancelled) return
        setItem(books.find((book) => book.storybook_id === storybookId) ?? null)
      })
      .catch((error: unknown) => {
        // #EDGE: external-resources: the tracker is best-effort; a failed
        // lookup must never break the ending screen. No text is the v1
        // fallback for every absence, including transport errors.
        // #VERIFY: EndingsProgress.test.tsx "renders nothing when the lookup fails".
        console.error('[reader] reading-history lookup failed', {
          profileId,
          storybookId,
          error,
        })
      })
    return () => {
      cancelled = true
    }
  }, [fetchReadingHistory, profileId, storybookId])

  if (!item || item.total_endings <= 1) return null
  return (
    <p className="reader-ending__endings-tracker" data-testid="endings-tracker">
      You found ending {item.endings_found} of {item.total_endings}! Read again to find more.
    </p>
  )
}
