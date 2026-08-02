/**
 * K6 endings tracker, ending-screen half: "You found ending N of M! Read
 * again to find more." W0.3 (design review 2026-08-01 section 3.4): renders
 * directly from the reached ending's POST /completions response
 * (`completionOutcome`) when the caller tracks one, instead of racing a
 * second GET against that POST. A 'ready' outcome also distinguishes a
 * first find ("You found a NEW ending!") from a repeat visit via `is_new`.
 * A caller that omits `completionOutcome` entirely (or whose POST comes
 * back 'unavailable', e.g. offline) keeps the original best-effort
 * `fetchReadingHistory` lookup, unchanged.
 */

import { useEffect, useState } from 'react'

import type { CompletionOutcome } from '../api/readerApi'
import type { ReadingHistoryItem } from '../client/types.gen'
import { allEndingsFoundLine, isLargeEndingCatalog, milestoneLine } from './endingsFraming'

/**
 * The tracker line for a known (found, total) pair (W1.3, AL-028). Shared by
 * both render paths below (the W0.3 completion-response path and the
 * fetchReadingHistory fallback) so the three states -- all found, milestone,
 * ordinary "N of M" -- are computed identically regardless of which data
 * source answered. `isNew` is only meaningful for the completion-response
 * path (the fallback lookup carries no first-find/repeat-visit signal), so
 * the fallback call site always passes `false`, which only affects the
 * below-threshold branch's wording.
 */
function trackerText(found: number, total: number, isNew: boolean): string {
  if (found >= total) {
    return allEndingsFoundLine(total)
  }
  if (isLargeEndingCatalog(total)) {
    return milestoneLine(found, isNew)
  }
  return isNew
    ? `You found a NEW ending! ${found} of ${total} found so far.`
    : `You found ending ${found} of ${total}! Read again to find more.`
}

export interface EndingsProgressProps {
  profileId: string
  storybookId: string
  fetchReadingHistory: (profileId: string) => Promise<ReadingHistoryItem[]>
  /**
   * The outcome of this ending's POST /completions call, when the caller
   * tracks one (ReaderPage does; a caller that omits this prop gets the
   * pre-W0.3 fetch-only behavior unconditionally, same as before). 'pending'
   * renders nothing and does not fetch (the POST is still in flight;
   * fetching now would race it and risk showing a stale count). 'ready'
   * renders directly from the response, no fetch. 'unavailable' (the POST
   * rejected) falls back to fetchReadingHistory exactly as before.
   */
  completionOutcome?: CompletionOutcome
}

// #ASSUME: timing dependencies: this fallback fetch fires the moment the
// ending screen mounts, which can be BEFORE the just-reached ending's
// completion POST (ReaderPage's recordCompletion, see handleComplete) has
// been recorded server-side, and can under-report by one ending (showing
// last visit's count, not this one) if it wins the race. This path only
// runs at all when `completionOutcome` is undefined (a caller with no
// POST-outcome tracking, e.g. a test that renders EndingsProgress directly)
// or 'unavailable' (the POST rejected); a caller wired for W0.3 with a
// 'pending' or 'ready' outcome never reaches this fetch branch, so the race
// is structurally avoided for the normal (online, POST succeeds) case.
// #VERIFY: acceptable per the K6 spec ("best-effort... on fetch failure show
// nothing"); the count self-corrects on the next visit to this screen or the
// library shelf. Never over-reports, so a child is never told they found
// more endings than they actually have.
export function EndingsProgress({
  profileId,
  storybookId,
  fetchReadingHistory,
  completionOutcome,
}: EndingsProgressProps) {
  const [item, setItem] = useState<ReadingHistoryItem | null>(null)

  // #ASSUME: data integrity: the fallback fetch below runs only when there is
  // no POST-derived answer to trust yet: `completionOutcome` omitted (legacy
  // caller) or explicitly 'unavailable' (the POST rejected). A 'pending'
  // outcome intentionally does NOT trigger it; the effect re-runs once
  // ReaderPage settles completionOutcome to 'ready' or 'unavailable'
  // (it is an effect dependency), re-evaluating this guard at that point.
  // #VERIFY: EndingsProgress.test.tsx "does not fetch while the completion
  // outcome is pending" / "fetches when the outcome is unavailable".
  // #EDGE: data integrity: a 'ready' outcome whose found/total are not finite
  // numbers (a stale mock, a proxy mangling the body, an old server without
  // W0.3's fields) must never render "undefined of undefined" to a child;
  // treat it exactly like 'unavailable' and use the fallback fetch.
  // #VERIFY: EndingsProgress.test.tsx "falls back to the fetch when a ready
  // result is malformed".
  const readyResult =
    completionOutcome?.status === 'ready' &&
    Number.isFinite(completionOutcome.result.found) &&
    Number.isFinite(completionOutcome.result.total)
      ? completionOutcome.result
      : null
  const shouldFetch =
    completionOutcome === undefined ||
    completionOutcome.status === 'unavailable' ||
    (completionOutcome.status === 'ready' && readyResult === null)

  useEffect(() => {
    if (!shouldFetch) return
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
  }, [fetchReadingHistory, profileId, storybookId, shouldFetch])

  if (completionOutcome?.status === 'pending') return null

  if (readyResult !== null) {
    const { is_new, found, total } = readyResult
    if (total <= 1) return null
    return (
      <p className="reader-ending__endings-tracker" data-testid="endings-tracker">
        {trackerText(found, total, is_new)}
      </p>
    )
  }

  if (!item || item.total_endings <= 1) return null
  return (
    <p className="reader-ending__endings-tracker" data-testid="endings-tracker">
      {trackerText(item.endings_found, item.total_endings, false)}
    </p>
  )
}
