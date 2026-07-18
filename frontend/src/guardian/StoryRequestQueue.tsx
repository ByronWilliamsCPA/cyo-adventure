import { useCallback, useEffect, useMemo, useState, type ReactElement } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { EmptyState } from '@ds/components/EmptyState'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { useToast } from '../notifications/useToast'
import { BUDGET_EXCEEDED_MESSAGE, isBudgetExceededError, makeBudgetApi } from './budgetApi'
import { FlagBadge, verdictTone } from './FlagBadge'
import { formatRelativeTime } from './intakeApi'
import {
  AGE_BANDS,
  LENGTHS,
  TEEN_BANDS,
  ageBandLabel,
  lengthLabel,
  narrativeStyleLabel,
} from './storyRequestOptions'
import {
  makeStoryRequestQueueApi,
  STORY_REQUESTS_CHANGED_EVENT,
  type StoryRequestQueueScope,
  type StoryRequestView,
} from './storyRequestQueueApi'

// Generic fallback for a row action failure that is not the ADR-015 G7
// budget 409 (see isBudgetExceededError); unchanged from before the budget
// surfacing was added.
const GENERIC_ROW_ERROR = 'Could not update the request. Try again.'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'forbidden' }
  | { kind: 'error' }
  | { kind: 'ready'; requests: StoryRequestView[] }

type RowDecision = {
  age_band: string
  length: string
  narrative_style: string
  series_title: string
}

// Cap the quoted request text inside the decline-confirm dialog; the full
// text already renders in the row, the dialog only needs enough of it to
// identify what is being declined.
const DECLINE_PREVIEW_MAX = 160

function declinePreview(req: StoryRequestView): string {
  const text = req.request_text ?? 'Idea hidden by content check'
  return text.length > DECLINE_PREVIEW_MAX
    ? `${text.slice(0, DECLINE_PREVIEW_MAX)}…`
    : text
}

/**
 * The pending story-request review queue, shared by both adult surfaces
 * (Task 3.0). Lists pending child requests with the (screened) text and
 * redacted moderation flags; Approve builds a concept and enqueues
 * generation server-side, Decline dismisses the request.
 *
 * `scope` selects the backing list: the guardian console reviews its own
 * family's requests ('family'), the admin console reviews every family's
 * ('all', backed by the admin-only GET /v1/admin/story-requests).
 * Approve/decline are the same per-id endpoints either way.
 *
 * A server-confirmed approve or decline shows a closing toast (the removed
 * row is otherwise the only signal the action landed) and dispatches
 * STORY_REQUESTS_CHANGED_EVENT so the guardian shell's nav badge refreshes.
 */
export function StoryRequestQueue({
  scope,
  approveSuccessMessage = 'Approved! The story is being made.',
}: {
  scope: StoryRequestQueueScope
  /**
   * Toast copy for a successful Approve. The default stays neutral so the
   * shared queue is truthful on any surface; the guardian call site
   * (RequestsPage) overrides it with a family-scoped tracking hint that
   * would be wrong on the admin cross-family queue.
   */
  approveSuccessMessage?: string
}) {
  const api = useApi()
  const { showToast } = useToast()
  const queueApi = useMemo(() => makeStoryRequestQueueApi(api, scope), [api, scope])
  const budgetApi = useMemo(() => makeBudgetApi(api), [api])
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  // "Now" for the "Asked N minutes ago" provenance lines, stamped when the
  // list loads (IntakePage's jobsSyncedAt pattern): render stays pure (the
  // react-hooks/purity rule forbids Date.now() during render) and rows only
  // exist after a fetch has stamped it, so the 0 initial value never shows.
  const [loadedAt, setLoadedAt] = useState(0)
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set())
  // Message text per row (absent = no error), not a boolean: a budget-409
  // gets its own friendly copy (see runRowAction's catch) instead of the
  // generic fallback every other row failure still uses.
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({})
  const [decisions, setDecisions] = useState<Record<string, RowDecision>>({})
  // ADR-015 G7/G3 remaining-budget context for the approve action
  // ("This will use 1 of your N remaining stories this month"). Only
  // meaningful for the guardian's own family queue: an admin's 'all' scope
  // reviews requests across many families, and GET /v1/families/me/budget
  // always answers for the ADMIN's own family, not the row's -- showing it
  // there would misattribute someone else's family budget to this request.
  // #VERIFY: StoryRequestQueue.test.tsx / RequestsPage.test.tsx pin the
  // family-scope-only rendering.
  const [remaining, setRemaining] = useState<number | null>(null)
  // The request awaiting decline confirmation (null when the dialog is
  // closed). Decline is destructive from the child's point of view (the idea
  // silently disappears from the queue), so it gets a confirm step; Approve
  // stays one-click. Role-agnostic: both the guardian and admin queues share
  // this component.
  const [confirmingDecline, setConfirmingDecline] = useState<StoryRequestView | null>(null)

  function decisionFor(req: StoryRequestView): RowDecision {
    return (
      decisions[req.id] ?? {
        age_band: req.age_band,
        length: '',
        narrative_style: 'prose',
        series_title: req.proposed_series_title ?? '',
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
        series_title: req.proposed_series_title ?? '',
      }
      const next = { ...current, ...patch }
      if (!TEEN_BANDS.includes(next.age_band)) next.narrative_style = 'prose'
      return { ...prev, [req.id]: next }
    })
  }

  const [reloadKey, setReloadKey] = useState(0)
  const retry = useCallback(() => setReloadKey((k) => k + 1), [])

  // Informational only (see `remaining`'s doc): a failed fetch just leaves
  // the approve context absent, it never blocks or errors the queue itself.
  const refreshBudget = useCallback(async () => {
    if (scope !== 'family') return
    try {
      const budget = await budgetApi.get()
      setRemaining(budget.remaining)
    } catch (err) {
      console.error('budget fetch for queue failed:', err instanceof Error ? err.message : err)
    }
  }, [scope, budgetApi])

  useEffect(() => {
    void refreshBudget()
  }, [refreshBudget])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setState({ kind: 'loading' })
      try {
        const requests = await queueApi.listPending()
        if (!cancelled) {
          setLoadedAt(Date.now())
          setState({ kind: 'ready', requests })
        }
      } catch (err) {
        // #CRITICAL: security: a 403 is an expected capability outcome (e.g.
        // an adult whose admin capability was just revoked still has the
        // admin queue open), not a failure, so surface a clear notice rather
        // than the generic error state.
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
  }, [queueApi, reloadKey])

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
  //
  // Returns whether the action was confirmed by the backend, so callers can
  // attach success-only feedback (toasts) without duplicating the error
  // handling below.
  async function runRowAction(id: string, action: () => Promise<unknown>): Promise<boolean> {
    if (pendingIds.has(id)) return false
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
      // Signal passive listeners (GuardianShell's pending-count badge) to
      // refetch. Fired only after the backend confirmed the transition, so
      // the badge never drops a request the server still holds as pending.
      window.dispatchEvent(new Event(STORY_REQUESTS_CHANGED_EVENT))
      return true
    } catch (err) {
      // #ASSUME: external-resources: approve/decline call the backend, which
      // can fail (network, session expiry, server error, a race with another
      // reviewer). Log the message, not the axios error object (its
      // config.headers carries the caller's bearer token), and keep the row
      // visible with a clear, actionable notice rather than silently
      // discarding the reviewer's action.
      // #VERIFY: RequestsPage.test.tsx rejected-approve test asserts the
      // visible alert and that the row remains in the list.
      console.error('story-request action failed:', err instanceof Error ? err.message : err)
      // ADR-015 G7: an approve past the family's monthly quota 409s with a
      // distinct, friendlier message (with a hint to wait for next month)
      // instead of the generic "could not update" fallback every other row
      // failure still gets.
      // #VERIFY: RequestsPage.test.tsx "budget-exhausted approve" test.
      setRowErrors((prev) => ({
        ...prev,
        [id]: isBudgetExceededError(err) ? BUDGET_EXCEEDED_MESSAGE : GENERIC_ROW_ERROR,
      }))
      return false
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
    const title = decision.series_title.trim()
    const payload = {
      age_band: decision.age_band,
      length: decision.length,
      narrative_style: decision.narrative_style,
      ...(title.length > 0 ? { series_title: title } : {}),
    }
    const approved = await runRowAction(req.id, () => queueApi.approve(req.id, payload))
    // Success-only: a failed action keeps the row visible with its inline
    // alert (runRowAction's catch), so a toast would be contradictory noise.
    if (approved) {
      showToast(approveSuccessMessage, { tone: 'success' })
      // An approve spends 1 of the family's remaining stories; refresh so
      // the next row's approve context (and RequestsPage's/IntakePage's
      // BudgetBanner, via the STORY_REQUESTS_CHANGED_EVENT runRowAction
      // already dispatched above) reflect the new count.
      void refreshBudget()
    }
  }

  async function decline(id: string) {
    const declined = await runRowAction(id, () => queueApi.decline(id))
    // Closure for the reviewer: the row disappearing is otherwise the only
    // signal the (confirmed) decline actually landed.
    if (declined) showToast('Request declined.', { tone: 'info' })
  }

  // Close the dialog before firing so the row-level error/pending states stay
  // the single source of feedback; runRowAction's pendingIds guard still
  // covers any duplicate submission.
  function confirmDecline() {
    if (confirmingDecline === null) return
    const id = confirmingDecline.id
    setConfirmingDecline(null)
    void decline(id)
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
        <p className="console__notice cyo-text-muted">
          Story requests are reviewed by your family&apos;s safety reviewer.
        </p>
      </section>
    )
  } else if (state.kind === 'error') {
    content = (
      <div role="alert" className="console__error">
        <p className="cyo-text-error">We could not load story requests.</p>
        <Button variant="primary" onClick={retry}>
          Try again
        </Button>
      </div>
    )
  } else if (state.requests.length === 0) {
    content = (
      <section className="console">
        <h1>Story requests</h1>
        <EmptyState
          title="No requests to review"
          description={
            scope === 'all'
              ? 'New story ideas from every family appear here.'
              : 'New story ideas from your children appear here.'
          }
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
            // Approve stays disabled until a length is chosen; without a
            // visible reason that reads as a broken button, so name the one
            // missing input while that is the only thing blocking it.
            const needsLength = isActionable && !isInFlight && decision.length === ''
            const askedAgo = formatRelativeTime(req.created_at, loadedAt)
            return (
              <li key={req.id} className="console-row cyo-card" data-testid={`request-${req.id}`}>
                <div className="console-row__body">
                  {/* request_text is nulled server-side only for blocked rows,
                      which the pending queue never returns; the fallback is
                      defensive so a null still renders a safe placeholder. */}
                  <p className="console-row__title">
                    {req.request_text ?? 'Idea hidden by content check'}
                  </p>
                  {askedAgo !== null ? (
                    <p
                      className="console-row__age cyo-text-muted"
                      title={new Date(req.created_at).toLocaleString()}
                    >
                      Asked {askedAgo}
                    </p>
                  ) : null}
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
                    <p role="alert" className="console-row__error cyo-text-error">
                      {rowErrors[req.id]}
                    </p>
                  ) : null}
                </div>
                <div className="console-row__actions">
                  <label>
                    Age band
                    <select
                      value={decision.age_band}
                      disabled={req.anchor_storybook_id !== null}
                      aria-describedby={
                        req.anchor_storybook_id !== null ? `series-note-${req.id}` : undefined
                      }
                      onChange={(e) => setDecision(req, { age_band: e.target.value })}
                    >
                      {AGE_BANDS.map((b) => (
                        <option key={b} value={b}>
                          {ageBandLabel(b)}
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
                          {lengthLabel(l)}
                        </option>
                      ))}
                    </select>
                  </label>
                  {TEEN_BANDS.includes(decision.age_band) ? (
                    <label>
                      Story style
                      <select
                        value={decision.narrative_style}
                        onChange={(e) => setDecision(req, { narrative_style: e.target.value })}
                      >
                        <option value="prose">{narrativeStyleLabel('prose')}</option>
                        <option value="gamebook">{narrativeStyleLabel('gamebook')}</option>
                      </select>
                    </label>
                  ) : null}
                  {req.anchor_storybook_id === null ? (
                    <label>
                      Series title (optional)
                      <input
                        type="text"
                        value={decision.series_title}
                        maxLength={120}
                        onChange={(e) => setDecision(req, { series_title: e.target.value })}
                      />
                    </label>
                  ) : (
                    <p
                      id={`series-note-${req.id}`}
                      className="console-row__series-note cyo-text-muted"
                    >
                      Continues an existing series
                    </p>
                  )}
                  <Button
                    disabled={isInFlight || !isActionable || decision.length === ''}
                    onClick={() => void approve(req)}
                  >
                    Approve
                  </Button>
                  <Button
                    variant="danger"
                    disabled={isInFlight || !isActionable}
                    onClick={() => setConfirmingDecline(req)}
                  >
                    Decline
                  </Button>
                  {needsLength ? (
                    <p className="console-row__approve-hint cyo-text-muted">
                      Choose a length to approve
                    </p>
                  ) : scope === 'family' && remaining !== null && isActionable ? (
                    // ADR-015 G7/G3: remaining-budget context for the
                    // approve action; family-scope only, see `remaining`'s
                    // doc for why the admin cross-family queue never shows
                    // this. Approve itself deliberately stays one-click (no
                    // confirm dialog, see the comment above this component);
                    // this is context alongside the button, not a gate.
                    <p className="console-row__approve-hint cyo-text-muted">
                      This will use 1 of your {remaining}{' '}
                      {remaining === 1 ? 'remaining story' : 'remaining stories'} this month.
                    </p>
                  ) : null}
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
      {content}
      {confirmingDecline !== null ? (
        <Dialog
          title="Decline this request?"
          onClose={() => setConfirmingDecline(null)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setConfirmingDecline(null)}>
                Keep it
              </Button>
              <Button variant="danger" onClick={confirmDecline}>
                Decline request
              </Button>
            </>
          }
        >
          <p>No story will be made from this idea:</p>
          <blockquote className="decline-confirm__quote cyo-text-muted">
            {declinePreview(confirmingDecline)}
          </blockquote>
        </Dialog>
      ) : null}
    </>
  )
}
