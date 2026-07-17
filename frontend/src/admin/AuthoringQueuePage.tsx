import { useEffect, useMemo, useState } from 'react'

import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import type { StoryRequestView } from '../guardian/storyRequestQueueApi'
import { AuthoringPlanDialog } from './AuthoringPlanDialog'
import { makeAuthoringPlanApi } from './authoringPlanApi'
import { makeProviderAllowlistApi } from './providerAllowlistApi'
import type { AllowlistView } from '../client/types.gen'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; requests: StoryRequestView[]; allowlistRows: AllowlistView[] }

/**
 * Admin-only queue of approved story requests awaiting an authoring plan
 * (WS-C): the step between a guardian/admin approving a request
 * (StoryRequestQueue, which sets age_band/length/narrative_style) and
 * generation actually starting. Closes the gap where
 * `POST /story-requests/{id}/authoring-plan` had a full backend + generated
 * client method but no page ever called it (2026-07-16 audit).
 */
export function AuthoringQueuePage() {
  const api = useApi()
  const authoringPlanApi = useMemo(() => makeAuthoringPlanApi(api), [api])
  const allowlistApi = useMemo(() => makeProviderAllowlistApi(api), [api])

  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [planningId, setPlanningId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [requests, allowlist] = await Promise.all([
          authoringPlanApi.listApproved(),
          allowlistApi.list(),
        ])
        if (!cancelled) {
          setState({ kind: 'ready', requests, allowlistRows: allowlist.rows })
        }
      } catch (err) {
        console.error('authoring queue load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) {
          setState({
            kind: 'error',
            message: classifyApiError(err, {
              transient: 'We could not load the authoring queue. Please reload.',
            }).message,
          })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [authoringPlanApi, allowlistApi])

  if (state.kind === 'loading') {
    return (
      <div role="status" aria-live="polite">
        Loading…
      </div>
    )
  }
  if (state.kind === 'error') {
    return (
      <p role="alert" className="console__error cyo-text-error">
        {state.message}
      </p>
    )
  }

  const { requests, allowlistRows } = state
  const planningRequest = requests.find((r) => r.id === planningId) ?? null

  return (
    <main>
      <h1>Authoring queue</h1>
      <p>
        Approved requests waiting for an authoring plan (method, mechanism, and, for an
        automated provider, the specific model). Age band, length, and style were already set
        when the request was approved and cannot be changed here.
      </p>
      {requests.length === 0 ? (
        <p className="console__muted cyo-text-muted">
          No approved requests are waiting for an authoring plan.
        </p>
      ) : (
        <ul className="console-list">
          {requests.map((req) => (
            <li key={req.id} className="console-row cyo-card" data-testid={`request-${req.id}`}>
              <div className="console-row__body">
                <p className="console-row__title">{req.request_text ?? 'Untitled request'}</p>
                <p className="console__muted cyo-text-muted">
                  {req.age_band} · {req.length ?? 'length not set'} · {req.narrative_style}
                </p>
              </div>
              <div className="console-row__actions">
                <button type="button" onClick={() => setPlanningId(req.id)}>
                  Build authoring plan
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {planningRequest ? (
        <AuthoringPlanDialog
          request={planningRequest}
          allowlistRows={allowlistRows}
          onClose={() => setPlanningId(null)}
          onSubmit={async (body) => {
            // Errors are handled inside AuthoringPlanDialog (it shows its own
            // alert and stays open on failure, matching ProfileFormDialog's
            // convention), so a rejection here just propagates uncaught and
            // this row is only removed once the plan actually succeeds.
            await authoringPlanApi.createPlan(planningRequest.id, body)
            setState((prev) =>
              prev.kind === 'ready'
                ? { ...prev, requests: prev.requests.filter((r) => r.id !== planningRequest.id) }
                : prev
            )
          }}
        />
      ) : null}
    </main>
  )
}
