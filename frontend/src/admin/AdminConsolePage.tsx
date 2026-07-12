import { useEffect, useMemo, useState, type ReactElement } from 'react'
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
  | { kind: 'ready'; items: ReviewQueueItem[]; processing: StillProcessingItem[] }

/** A story that was never screened, or screened with at least one finding. */
function isFlagged(item: ReviewQueueItem): boolean {
  return !item.screened || item.flagged_count > 0
}

function QueueRow({ item }: { item: ReviewQueueItem }) {
  return (
    <li className="console-row cyo-card cyo-card--interactive">
      <Link className="console-row__link" to={`/admin/review/${item.storybook_id}`}>
        <span className="console-row__title">{item.title}</span>
        {!item.screened ? (
          <FlagBadge tone="unscreened" />
        ) : item.flagged_count > 0 ? (
          <FlagBadge tone="flag" label={`${item.flagged_count} flagged`} />
        ) : (
          <FlagBadge tone="clean" />
        )}
      </Link>
    </li>
  )
}

/**
 * Admin console home (C4a-4): the safety operator's severity-ordered review
 * queue, moved from the guardian console when admin functions gained their
 * own surface. Flagged stories sort to the top, then ready-to-review, then
 * still processing. The route is admin-gated (router.tsx), and the queue
 * endpoint independently requires the admin capability server-side
 * (ADR-005: the approver is the global safety reviewer, not any guardian).
 */
export function AdminConsolePage() {
  const api = useApi()
  const reviewApi = useMemo(() => makeReviewApi(api), [api])
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [items, processing] = await Promise.all([
          reviewApi.queue(),
          reviewApi.stillProcessing(),
        ])
        if (!cancelled) setState({ kind: 'ready', items, processing })
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
  }, [reviewApi])

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
    const flagged = state.items.filter(isFlagged)
    const ready = state.items.filter((item) => item.screened && item.flagged_count === 0)
    const nothingPending = state.items.length === 0 && state.processing.length === 0

    content = (
      <section className="console">
        <h1>Review queue</h1>
        {nothingPending ? (
          <EmptyState
            title="Nothing to review"
            description="New stories appear here once they finish generating."
          />
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
            <div className="console-group">
              <h2 className="console-group__heading">Still processing</h2>
              {state.processing.length === 0 ? (
                <p className="console__muted cyo-text-muted">
                  No stories are generating right now.
                </p>
              ) : (
                <ul className="console-list">
                  {state.processing.map((job) => (
                    <li key={job.job_id} className="console-row cyo-card">
                      <span className="console-row__title">{job.title}</span>
                      <FlagBadge tone="processing" />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </section>
    )
  }

  return content
}
