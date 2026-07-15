import { useCallback, useEffect, useMemo, useState, type ReactElement } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@ds/components/EmptyState'
import { FlagBadge } from '../guardian/FlagBadge'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import {
  makeReviewApi,
  type ReviewQueueItem,
  type StillProcessingItem,
} from '../guardian/reviewApi'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'forbidden' }
  | { kind: 'error' }
  | {
      kind: 'ready'
      items: ReviewQueueItem[]
      processing: StillProcessingItem[]
      updatedAt: Date
    }

/** A story that was never screened, or screened with at least one finding. */
function isFlagged(item: ReviewQueueItem): boolean {
  return !item.screened || item.flagged_count > 0
}

/**
 * Sort rule for the flagged bucket: hard blocks first (the safety gate
 * refused those stories outright), then by flagged-finding count descending;
 * everything else keeps the backend's queue order (Array.prototype.sort is
 * stable, so equal ranks never reshuffle). flagged_count, not summary.count,
 * is the count key: the backend guarantees flagged_count counts exactly the
 * findings the floored review detail will show (review_surface.py), while
 * summary.count includes sub-floor advisory noise.
 */
function bySeverity(a: ReviewQueueItem, b: ReviewQueueItem): number {
  const aBlock = a.summary?.hard_block === true
  const bBlock = b.summary?.hard_block === true
  if (aBlock !== bBlock) return aBlock ? -1 : 1
  return b.flagged_count - a.flagged_count
}

/** Local-clock HH:MM (24-hour), deterministic across runner locales. */
function formatUpdatedAt(at: Date): string {
  const hours = String(at.getHours()).padStart(2, '0')
  const minutes = String(at.getMinutes()).padStart(2, '0')
  return `${hours}:${minutes}`
}

/**
 * Severity cluster for one queue row, driven by the moderation summary.
 * Every badge pairs text with its tone; color is never the only signal.
 *
 * #ASSUME: data integrity: hard_block and soft_flag are mutually exclusive
 * (ModerationReport.has_soft_flag excludes blocked reports), so one primary
 * badge is exact, never lossy; "Repaired" stacks alongside because repair is
 * orthogonal to the gate verdict.
 * #VERIFY: AdminConsolePage.test.tsx asserts a hard-block row shows
 * "Hard block" with no flag count, and a repaired soft-flag row shows both
 * "N flags" and "Repaired".
 */
function SeverityBadges({ item }: { item: ReviewQueueItem }): ReactElement {
  if (!item.screened) return <FlagBadge tone="unscreened" />
  return (
    <span className="admin-severity">
      {item.summary?.hard_block ? (
        <span className="flag-badge admin-severity__hard-block">Hard block</span>
      ) : item.flagged_count > 0 ? (
        <FlagBadge
          tone="flag"
          label={item.flagged_count === 1 ? '1 flag' : `${item.flagged_count} flags`}
        />
      ) : (
        <FlagBadge tone="clean" />
      )}
      {item.summary?.repaired ? (
        <span className="flag-badge admin-severity__repaired">Repaired</span>
      ) : null}
    </span>
  )
}

function QueueRow({ item }: { item: ReviewQueueItem }) {
  return (
    <li className="console-row cyo-card cyo-card--interactive">
      <Link className="console-row__link" to={`/admin/review/${item.storybook_id}`}>
        <span className="console-row__title">{item.title}</span>
        <SeverityBadges item={item} />
      </Link>
    </li>
  )
}

/**
 * Admin console home (C4a-4): the safety operator's severity-ordered review
 * queue, moved from the guardian console when admin functions gained their
 * own surface. Flagged stories sort to the top (hard blocks first, see
 * bySeverity), then ready-to-review, then still processing. The route is
 * admin-gated (router.tsx), and the queue endpoint independently requires
 * the admin capability server-side (ADR-005: the approver is the global
 * safety reviewer, not any guardian).
 */
export function AdminConsolePage() {
  const api = useApi()
  const reviewApi = useMemo(() => makeReviewApi(api), [api])
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [refreshing, setRefreshing] = useState(false)
  const [refreshFailed, setRefreshFailed] = useState(false)
  const [query, setQuery] = useState('')

  const fetchQueue = useCallback(async () => {
    const [items, processing] = await Promise.all([
      reviewApi.queue(),
      reviewApi.stillProcessing(),
    ])
    return { items, processing }
  }, [reviewApi])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const { items, processing } = await fetchQueue()
        if (!cancelled) setState({ kind: 'ready', items, processing, updatedAt: new Date() })
      } catch (err) {
        // #CRITICAL: security: the route is admin-gated, but the backend
        // check is independent (defense in depth); a 403 here means the
        // capability was revoked mid-session, an expected outcome, not a
        // failure, so surface a clear notice.
        // #VERIFY: AdminConsolePage.test.tsx asserts the notice on a 403 and
        // the generic error on a 500.
        if (classifyApiError(err).kind === 'forbidden') {
          if (!cancelled) setState({ kind: 'forbidden' })
          return
        }
        // Log the message, not the axios error object (its config.headers
        // carries the caller's Authorization bearer token).
        console.error('review queue load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) setState({ kind: 'error' })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [fetchQueue])

  // Manual refetch only (no polling): the button disables while in flight,
  // and a failure keeps the last good queue on screen behind an inline alert
  // instead of discarding it for the full-page error state.
  // #EDGE: timing dependencies: a refresh can settle after an unmount (route
  // change mid-flight); React 18+ makes setState on an unmounted component a
  // safe no-op, so no cancellation flag is needed for this handler.
  // #VERIFY: guaranteed by React, not by this code; nothing to assert.
  async function refresh() {
    setRefreshing(true)
    setRefreshFailed(false)
    try {
      const { items, processing } = await fetchQueue()
      setState({ kind: 'ready', items, processing, updatedAt: new Date() })
    } catch (err) {
      // #ASSUME: security: a 403 on refresh means the admin capability was
      // revoked mid-session; fail closed to the same no-access notice as the
      // initial load rather than keeping the now-stale queue visible.
      // #VERIFY: AdminConsolePage.test.tsx asserts a 403 refresh swaps the
      // queue for the notice and a 500 refresh keeps the queue with an alert.
      if (classifyApiError(err).kind === 'forbidden') {
        setState({ kind: 'forbidden' })
      } else {
        // Log the message, not the axios error object (its config.headers
        // carries the caller's Authorization bearer token).
        console.error('review queue refresh failed:', err instanceof Error ? err.message : err)
        setRefreshFailed(true)
      }
    } finally {
      setRefreshing(false)
    }
  }

  let content: ReactElement
  if (state.kind === 'loading') {
    content = (
      <div role="status" aria-live="polite">
        Loading review queue…
      </div>
    )
  } else if (state.kind === 'forbidden') {
    content = (
      <section className="console">
        <h1>Review queue</h1>
        <p className="console__notice cyo-text-muted">
          Your account does not have review access. Reviews are handled by the safety reviewer.
        </p>
      </section>
    )
  } else if (state.kind === 'error') {
    content = (
      <p role="alert" className="console__error cyo-text-error">
        We could not load the review queue. Please reload.
      </p>
    )
  } else {
    const trimmedQuery = query.trim()
    const needle = trimmedQuery.toLowerCase()
    const searching = needle.length > 0
    const matchesTitle = (title: string): boolean => title.toLowerCase().includes(needle)

    // Sort before filtering so severity order is independent of the search.
    const flagged = state.items
      .filter(isFlagged)
      .sort(bySeverity)
      .filter((item) => !searching || matchesTitle(item.title))
    const ready = state.items.filter(
      (item) =>
        item.screened && item.flagged_count === 0 && (!searching || matchesTitle(item.title))
    )
    const processing = state.processing.filter((job) => !searching || matchesTitle(job.title))
    const nothingPending = state.items.length === 0 && state.processing.length === 0
    const noMatches =
      searching && flagged.length === 0 && ready.length === 0 && processing.length === 0

    content = (
      <section className="console">
        <div className="admin-console__header">
          <h1>Review queue</h1>
          <div className="admin-console__meta">
            <span className="admin-console__updated cyo-text-muted">
              Updated {formatUpdatedAt(state.updatedAt)}
            </span>
            <button
              type="button"
              className="admin-console__refresh"
              onClick={() => void refresh()}
              disabled={refreshing}
            >
              Refresh
            </button>
          </div>
        </div>
        {refreshFailed ? (
          <p role="alert" className="admin-console__refresh-error cyo-text-error">
            Refresh failed. Showing the queue from {formatUpdatedAt(state.updatedAt)}.
          </p>
        ) : null}
        {nothingPending ? (
          <EmptyState
            title="Nothing to review"
            description="New stories appear here once they finish generating."
          />
        ) : (
          <>
            <label className="admin-search cyo-field" htmlFor="admin-queue-search">
              Search by title
              <input
                id="admin-queue-search"
                type="search"
                className="cyo-field__control"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            {noMatches ? (
              <p role="status" className="admin-search__no-matches cyo-text-muted">
                No matches for &quot;{trimmedQuery}&quot;
              </p>
            ) : (
              <>
                {flagged.length > 0 ? (
                  <div className="console-group">
                    <h2 className="console-group__heading">Flagged (review carefully)</h2>
                    <ul className="console-list">
                      {flagged.map((item) => (
                        <QueueRow key={item.storybook_id} item={item} />
                      ))}
                    </ul>
                  </div>
                ) : null}
                {ready.length > 0 ? (
                  <div className="console-group">
                    <h2 className="console-group__heading">Ready to review</h2>
                    <ul className="console-list">
                      {ready.map((item) => (
                        <QueueRow key={item.storybook_id} item={item} />
                      ))}
                    </ul>
                  </div>
                ) : null}
                {searching && processing.length === 0 ? null : (
                  <div className="console-group">
                    <h2 className="console-group__heading">Still processing</h2>
                    {processing.length === 0 ? (
                      <p className="console__muted cyo-text-muted">
                        No stories are generating right now.
                      </p>
                    ) : (
                      <ul className="console-list">
                        {processing.map((job) => (
                          <li key={job.job_id} className="console-row cyo-card">
                            <span className="console-row__title">{job.title}</span>
                            <FlagBadge tone="processing" />
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </section>
    )
  }

  return content
}
