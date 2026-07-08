import { useEffect, useMemo, useState, type ReactElement } from 'react'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { useAuth } from '../auth/useAuth'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { FlagBadge, verdictTone } from './FlagBadge'
import { RequestStoryForm } from './RequestStoryForm'
import { AGE_BANDS, LENGTHS, TEEN_BANDS } from './storyRequestOptions'
import { makeStoryRequestQueueApi, type StoryRequestView } from './storyRequestQueueApi'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'forbidden' }
  | { kind: 'error' }
  | { kind: 'ready'; requests: StoryRequestView[] }

type RowDecision = { age_band: string; length: string; narrative_style: string }

/**
 * Guardian/admin story-request review (Task 3.0). Lists pending child requests
 * with the (screened) text and redacted moderation flags; Approve builds a
 * concept and enqueues generation server-side, Decline dismisses the request.
 * Guardians also get an embedded RequestStoryForm (WS-B PR 2) above the queue
 * for authoring a pre-approved request of their own.
 */
export function RequestsPage() {
  const api = useApi()
  const { principal } = useAuth()
  const queueApi = useMemo(() => makeStoryRequestQueueApi(api), [api])
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  const [rowErrors, setRowErrors] = useState<Record<string, boolean>>({})
  const [decisions, setDecisions] = useState<Record<string, RowDecision>>({})

  function decisionFor(req: StoryRequestView): RowDecision {
    return (
      decisions[req.id] ?? {
        age_band: req.age_band,
        length: '',
        narrative_style: 'prose',
      }
    )
  }

  // #ASSUME: data-integrity: ADR-011 restricts the gamebook narrative style to
  // teen bands (13-16, 16+); a reviewer switching a row's age band away from a
  // teen band must not leave a stale gamebook selection behind.
  // #VERIFY: RequestsPage.test.tsx style-select-teen-only test.
  function setDecision(req: StoryRequestView, patch: Partial<RowDecision>) {
    setDecisions((prev) => {
      const current = prev[req.id] ?? {
        age_band: req.age_band,
        length: '',
        narrative_style: 'prose',
      }
      const next = { ...current, ...patch }
      if (!TEEN_BANDS.includes(next.age_band)) next.narrative_style = 'prose'
      return { ...prev, [req.id]: next }
    })
  }

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
        if (classifyApiError(err).kind === 'forbidden') {
          if (!cancelled) setState({ kind: 'forbidden' })
          return
        }
        // #ASSUME: external-resources: the queue read can fail (network,
        // session expiry, server error). Log the message, not the axios
        // error object (its config.headers carries the caller's bearer
        // token), and degrade to a visible error state rather than a silent
        // empty list.
        // #VERIFY: RequestsPage.test.tsx generic-error test.
        console.error('story-request queue load failed:', err instanceof Error ? err.message : err)
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

  // #CRITICAL: concurrency: a double-click (or a slow response the reviewer
  // clicks again while waiting) must not fire a second approve/decline for the
  // same row; approve enqueues a paid generation job server-side, so a
  // duplicate call risks a duplicate job. Track in-flight ids per row (not a
  // single page-level flag) so independent rows stay actionable while one is
  // pending, and disable both of a row's buttons while either of its actions
  // is in flight.
  // #VERIFY: RequestsPage.test.tsx double-click test asserts exactly one
  // adapter call and that both buttons are disabled while the promise is
  // unresolved.
  async function runRowAction(id: string, action: () => Promise<unknown>) {
    if (pendingIds.has(id)) return
    setPendingIds((prev) => new Set(prev).add(id))
    setRowErrors((prev) => {
      if (!(id in prev)) return prev
      const next = { ...prev }
      delete next[id]
      return next
    })
    try {
      await action()
      removeRow(id)
    } catch (err) {
      // #ASSUME: external-resources: approve/decline call the backend, which
      // can fail (network, session expiry, server error, a race with another
      // reviewer). Log the message, not the axios error object (its
      // config.headers carries the caller's bearer token), and keep the row
      // visible with a clear, actionable notice rather than silently
      // discarding the guardian's action.
      // #VERIFY: RequestsPage.test.tsx rejected-approve test asserts the
      // visible alert and that the row remains in the list.
      console.error('story-request action failed:', err instanceof Error ? err.message : err)
      setRowErrors((prev) => ({ ...prev, [id]: true }))
    } finally {
      setPendingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }
  }

  async function approve(req: StoryRequestView) {
    const decision = decisionFor(req)
    await runRowAction(req.id, () => queueApi.approve(req.id, decision))
  }

  async function decline(id: string) {
    await runRowAction(id, () => queueApi.decline(id))
  }

  let content: ReactElement
  if (state.kind === 'loading') {
    content = (
      <div role="status" aria-live="polite">
        Loading story requests…
      </div>
    )
  } else if (state.kind === 'forbidden') {
    content = (
      <section className="console">
        <h1>Story requests</h1>
        <p className="console__notice">
          Story requests are reviewed by your family&apos;s safety reviewer.
        </p>
      </section>
    )
  } else if (state.kind === 'error') {
    content = (
      <p role="alert" className="console__error">
        We could not load story requests. Please reload.
      </p>
    )
  } else if (state.requests.length === 0) {
    content = (
      <section className="console">
        <h1>Story requests</h1>
        <EmptyState
          title="No requests to review"
          description="New story ideas from your children appear here."
        />
      </section>
    )
  } else {
    content = (
      <section className="console">
        <h1>Story requests</h1>
        <ul className="console-list">
          {state.requests.map((req) => {
            const isInFlight = pendingIds.has(req.id)
            // Approve/Decline only transition a pending request; the backend
            // rejects the action for any other status. The queue is fetched
            // with ?status=pending so non-pending rows do not occur here in
            // practice, but gate the actions on status anyway so the state
            // machine holds if the fetch ever widens.
            const isActionable = req.status === 'pending'
            const decision = decisionFor(req)
            return (
              <li key={req.id} className="console-row" data-testid={`request-${req.id}`}>
                <div className="console-row__body">
                  {/* request_text is nulled server-side only for blocked rows,
                      which the pending queue never returns; the fallback is
                      defensive so a null still renders a safe placeholder. */}
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
                  {rowErrors[req.id] ? (
                    <p role="alert" className="console-row__error">
                      Could not update the request. Try again.
                    </p>
                  ) : null}
                </div>
                <div className="console-row__actions">
                  <label>
                    Age band
                    <select
                      value={decision.age_band}
                      onChange={(e) => setDecision(req, { age_band: e.target.value })}
                    >
                      {AGE_BANDS.map((b) => (
                        <option key={b} value={b}>
                          {b}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Story length
                    <select
                      value={decision.length}
                      onChange={(e) => setDecision(req, { length: e.target.value })}
                    >
                      <option value="">Choose…</option>
                      {LENGTHS.map((l) => (
                        <option key={l} value={l}>
                          {l}
                        </option>
                      ))}
                    </select>
                  </label>
                  {TEEN_BANDS.includes(decision.age_band) ? (
                    <label>
                      Story style
                      <select
                        value={decision.narrative_style}
                        onChange={(e) =>
                          setDecision(req, { narrative_style: e.target.value })
                        }
                      >
                        <option value="prose">prose</option>
                        <option value="gamebook">gamebook</option>
                      </select>
                    </label>
                  ) : null}
                  <Button
                    disabled={isInFlight || !isActionable || decision.length === ''}
                    onClick={() => void approve(req)}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="danger"
                    disabled={isInFlight || !isActionable}
                    onClick={() => void decline(req.id)}
                  >
                    Decline
                  </Button>
                </div>
              </li>
            )
          })}
        </ul>
      </section>
    )
  }

  return (
    <>
      {principal?.role === 'guardian' ? <RequestStoryForm mode="guardian" /> : null}
      {content}
    </>
  )
}
