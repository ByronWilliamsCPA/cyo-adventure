import { useEffect, useMemo, useState, type ReactElement } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@ds/components/EmptyState'
import { useAuth } from '../auth/useAuth'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { FlagBadge } from './FlagBadge'
import { RequestStoryForm } from './RequestStoryForm'
import { makeReviewApi, type ReviewQueueItem, type StillProcessingItem } from './reviewApi'

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
    <li className="console-row">
      <Link className="console-row__link" to={`/guardian/review/${item.storybook_id}`}>
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
 * Guardian console (C4a-4): the safety operator's severity-ordered review
 * queue. Flagged stories sort to the top, then ready-to-review, then still
 * processing. The queue endpoint is admin-only; a plain-guardian token gets a
 * 403 and sees a notice rather than a broken page (ADR-005: the approver is the
 * global safety reviewer, not any guardian).
 */
export function ConsolePage() {
  const api = useApi()
  const { principal } = useAuth()
  const reviewApi = useMemo(() => makeReviewApi(api), [api])
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  // #ASSUME: data integrity: /v1/profiles returns { profiles: [...] }. On any
  // failure childCount stays null and the onboarding nudge simply does not
  // render, so a first-time guardian is nudged but a load hiccup is silent.
  // #VERIFY: ConsolePage.test.tsx nudge / no-nudge cases.
  const [childCount, setChildCount] = useState<number | null>(null)

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
        // #CRITICAL: security: a plain-guardian token is allowed into the
        // /guardian route tree but not the admin-only queue endpoint; a 403 is
        // an expected role outcome, not a failure, so surface a clear notice.
        // #VERIFY: ConsolePage.test.tsx asserts the notice on a 403 and the
        // generic error on a 500.
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

  // Separate, non-blocking read: a first-time guardian with zero children needs
  // a nudge toward profile creation, independent of the admin-only queue state.
  useEffect(() => {
    let cancelled = false
    async function loadChildren() {
      try {
        const res = await api.get<{ profiles?: unknown[] }>('/v1/profiles')
        const profiles = res.data.profiles ?? []
        if (!cancelled) setChildCount(profiles.length)
      } catch {
        if (!cancelled) setChildCount(null)
      }
    }
    void loadChildren()
    return () => {
      cancelled = true
    }
  }, [api])

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
        <p className="console__notice">
          Reviews are handled by your family&apos;s safety reviewer. You do not need to
          approve stories here.
        </p>
      </section>
    )
  } else if (state.kind === 'error') {
    content = (
      <p role="alert" className="console__error">
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
            actions={
              childCount === 0 ? (
                <Link className="console__cta" to="/guardian/profiles">
                  Add a child profile to get started
                </Link>
              ) : undefined
            }
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
                <p className="console__muted">No stories are generating right now.</p>
              ) : (
                <ul className="console-list">
                  {state.processing.map((job) => (
                    <li key={job.job_id} className="console-row">
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

  return (
    <>
      {principal?.role === 'admin' ? <RequestStoryForm mode="admin" /> : null}
      {content}
    </>
  )
}
