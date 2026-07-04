import { isAxiosError } from 'axios'
import { useEffect, useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { useApi } from '../hooks/useApi'
import { FlagBadge, verdictTone } from './FlagBadge'
import {
  makeStoryRequestQueueApi,
  type StoryRequestView,
} from './storyRequestQueueApi'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'forbidden' }
  | { kind: 'error' }
  | { kind: 'ready'; requests: StoryRequestView[] }

/**
 * Guardian/admin story-request review (Task 3.0). Lists pending child requests
 * with the (screened) text and redacted moderation flags; Approve builds a
 * concept and enqueues generation server-side, Decline dismisses the request.
 */
export function RequestsPage() {
  const api = useApi()
  const queueApi = useMemo(() => makeStoryRequestQueueApi(api), [api])
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const requests = await queueApi.listPending()
        if (!cancelled) setState({ kind: 'ready', requests })
      } catch (err) {
        // #CRITICAL: security: a plain-guardian token is allowed into the
        // /guardian route tree but not the admin-only story-request queue
        // endpoint; a 403 is an expected role outcome, not a failure, so
        // surface a clear notice rather than the generic error state.
        // #VERIFY: RequestsPage.test.tsx asserts the notice on a 403 and the
        // generic error on a 500.
        if (isAxiosError(err) && err.response?.status === 403) {
          if (!cancelled) setState({ kind: 'forbidden' })
          return
        }
        // #ASSUME: external-resources: the queue read can fail (network,
        // session expiry, server error). Log the message, not the axios
        // error object (its config.headers carries the caller's bearer
        // token), and degrade to a visible error state rather than a silent
        // empty list.
        // #VERIFY: RequestsPage.test.tsx generic-error test.
        console.error(
          'story-request queue load failed:',
          err instanceof Error ? err.message : err
        )
        if (!cancelled) setState({ kind: 'error' })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [queueApi])

  function removeRow(id: string) {
    setState((prev) =>
      prev.kind === 'ready'
        ? { kind: 'ready', requests: prev.requests.filter((r) => r.id !== id) }
        : prev
    )
  }

  async function approve(id: string) {
    try {
      await queueApi.approve(id)
      removeRow(id)
    } catch (err) {
      console.error('approve failed', err instanceof Error ? err.message : err)
    }
  }

  async function decline(id: string) {
    try {
      await queueApi.decline(id)
      removeRow(id)
    } catch (err) {
      console.error('decline failed', err instanceof Error ? err.message : err)
    }
  }

  if (state.kind === 'loading') {
    return (
      <div role="status" aria-live="polite">
        Loading story requests…
      </div>
    )
  }
  if (state.kind === 'forbidden') {
    return (
      <section className="console">
        <h1>Story requests</h1>
        <p className="console__notice">
          Story requests are reviewed by your family&apos;s safety reviewer.
        </p>
      </section>
    )
  }
  if (state.kind === 'error') {
    return (
      <p role="alert" className="console__error">
        We could not load story requests. Please reload.
      </p>
    )
  }
  if (state.requests.length === 0) {
    return (
      <section className="console">
        <h1>Story requests</h1>
        <EmptyState
          title="No requests to review"
          description="New story ideas from your children appear here."
        />
      </section>
    )
  }
  return (
    <section className="console">
      <h1>Story requests</h1>
      <ul className="console-list">
        {state.requests.map((req) => (
          <li key={req.id} className="console-row" data-testid={`request-${req.id}`}>
            <div className="console-row__body">
              <p className="console-row__title">
                {req.request_text ?? 'Idea hidden by content check'}
              </p>
              {req.moderation_flags.length > 0 ? (
                <div className="console-row__flags">
                  {req.moderation_flags.map((flag, i) => (
                    <FlagBadge
                      key={`${req.id}-${i}`}
                      tone={verdictTone(flag.verdict)}
                      label={flag.category}
                    />
                  ))}
                </div>
              ) : null}
            </div>
            <div className="console-row__actions">
              <Button onClick={() => void approve(req.id)}>Approve</Button>
              <Button variant="danger" onClick={() => void decline(req.id)}>
                Decline
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
