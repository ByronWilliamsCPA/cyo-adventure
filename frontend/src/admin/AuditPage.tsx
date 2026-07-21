import { useEffect, useMemo, useRef, useState } from 'react'

import { LoadingStatus } from '@ds/components/LoadingStatus'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { makeAuditApi, type AuditEventView, type AuditListView } from './auditApi'

const PAGE_SIZE = 50

// Mirrors cyo_adventure.events.models.EventType's value vocabulary -- the
// closed set the backend's `kind` filter validates against (a 422 for
// anything outside it). Kept in sync by hand, the same convention this
// frontend already uses for AGE_BANDS (profiles/profilesApi.ts) and VERDICTS
// (ModerationThresholdsPage.tsx): none of these cross-boundary enums are
// generated from the OpenAPI schema today.
const EVENT_KINDS = [
  'request_created',
  'request_approved',
  'request_declined',
  'plan_assigned',
  'generation_started',
  'generation_finished',
  'moderation_completed',
  'repair_applied',
  'sent_back',
  'released',
  'threshold_changed',
  'noise_floor_changed',
  'book_assigned',
  'rated',
  'kid_flagged',
  'flag_resolved',
  'user_managed',
  'family_managed',
  'family_connection_changed',
  'node_edited',
] as const

interface FilterState {
  kind: string
  storybookId: string
  profileId: string
  since: string
  until: string
}

const EMPTY_FILTERS: FilterState = {
  kind: '',
  storybookId: '',
  profileId: '',
  since: '',
  until: '',
}

type LoadState =
  { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; data: AuditListView }

/** Human-readable "actor" cell: role plus id, or "system" for an unattributed row. */
function actorLabel(event: AuditEventView): string {
  if (event.actor_id === null) return 'system'
  return `${event.actor_role} (${event.actor_id})`
}

/** Human-readable "entity" cell: type plus id, mirroring events/writer.py's entity_type/entity_id pair. */
function entityLabel(event: AuditEventView): string {
  return `${event.entity_type}: ${event.entity_id}`
}

/** Human-readable "transition" cell, or an em-dash-free placeholder when the event carries no state change. */
function transitionLabel(event: AuditEventView): string {
  if (event.from_state === null && event.to_state === null) return 'n/a'
  return `${event.from_state ?? '(none)'} -> ${event.to_state ?? '(none)'}`
}

/**
 * Admin-only audit view over the append-only pipeline event log (register
 * A13, the view half; M5 / Phase 5 deliverable). Answers "who did what to
 * child-linked data": every filter (event kind, storybook id, profile id,
 * and an occurred_at date range) composes with AND against
 * `GET /v1/admin/audit`, and the result is a limit/offset page, newest
 * first. Registered admin-only in router.tsx, mirroring
 * ModerationThresholdsPage and ModerationDashboardPage: the backend
 * re-checks the admin role on every call regardless of what this page does.
 */
export function AuditPage() {
  const api = useApi()
  const auditApi = useMemo(() => makeAuditApi(api), [api])

  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [appliedFilters, setAppliedFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [offset, setOffset] = useState(0)
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  // #ASSUME: timing dependencies: a filter/page change re-runs the same load
  // effect as the initial mount load, so a transient GET failure (or just the
  // in-flight gap) on a refetch must not blank out an already-rendered table;
  // hasLoadedRef (not state) tracks "has a load ever succeeded" because state
  // itself is not, and must not become, a dependency of the load effect: an
  // effect depending on state would refire on every state change, turning
  // every successful load into an infinite refetch loop. Mirrors
  // ModerationDashboardPage's identical idiom.
  // #VERIFY: AuditPage.test.tsx "keeps the last page visible while a
  // subsequent page change is loading" and "shows a refresh-error banner
  // without discarding the last-good page on a refetch failure".
  const hasLoadedRef = useRef(false)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (hasLoadedRef.current) {
        setRefreshing(true)
      } else {
        setState({ kind: 'loading' })
      }
      try {
        const data = await auditApi.list({
          kind: appliedFilters.kind || undefined,
          storybookId: appliedFilters.storybookId.trim() || undefined,
          profileId: appliedFilters.profileId.trim() || undefined,
          since: appliedFilters.since || undefined,
          until: appliedFilters.until || undefined,
          limit: PAGE_SIZE,
          offset,
        })
        if (!cancelled) {
          hasLoadedRef.current = true
          setRefreshError(null)
          setState({ kind: 'ready', data })
        }
      } catch (err) {
        console.error('audit log load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) {
          const message = classifyApiError(err, {
            forbidden: 'Admin access is required to view the audit log.',
            transient: 'We could not load the audit log. Please try again.',
            server: 'We could not load the audit log. Please try again.',
          }).message
          if (hasLoadedRef.current) {
            setRefreshError(message)
          } else {
            setState({ kind: 'error', message })
          }
        }
      } finally {
        if (!cancelled) {
          setRefreshing(false)
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [auditApi, appliedFilters, offset])

  const canGoPrevious = offset > 0 && !refreshing
  const canGoNext = state.kind === 'ready' && state.data.has_more && !refreshing

  return (
    <main>
      <h1>Audit log</h1>
      <p className="console__muted cyo-text-muted">
        Every recorded action on child-linked data: who did it, what changed, and when. Newest
        first.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          setOffset(0)
          setAppliedFilters(filters)
        }}
      >
        <label>
          Event kind
          <select
            value={filters.kind}
            onChange={(e) => setFilters({ ...filters, kind: e.target.value })}
            aria-label="Filter by event kind"
          >
            <option value="">All kinds</option>
            {EVENT_KINDS.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <label>
          Storybook id
          <input
            type="text"
            value={filters.storybookId}
            onChange={(e) => setFilters({ ...filters, storybookId: e.target.value })}
            aria-label="Filter by storybook id"
          />
        </label>
        <label>
          Profile id
          <input
            type="text"
            value={filters.profileId}
            onChange={(e) => setFilters({ ...filters, profileId: e.target.value })}
            aria-label="Filter by profile id"
          />
        </label>
        <label>
          Since
          <input
            type="date"
            value={filters.since}
            onChange={(e) => setFilters({ ...filters, since: e.target.value })}
            aria-label="Filter events since this date"
          />
        </label>
        <label>
          Until
          <input
            type="date"
            value={filters.until}
            onChange={(e) => setFilters({ ...filters, until: e.target.value })}
            aria-label="Filter events until this date"
          />
        </label>
        <button type="submit">Apply filters</button>
        <button
          type="button"
          onClick={() => {
            setFilters(EMPTY_FILTERS)
            setAppliedFilters(EMPTY_FILTERS)
            setOffset(0)
          }}
        >
          Clear filters
        </button>
      </form>

      {state.kind === 'loading' ? <LoadingStatus /> : null}

      {state.kind === 'error' ? (
        <p role="alert" className="console__error cyo-text-error">
          {state.message}
        </p>
      ) : null}

      {refreshError ? (
        <p role="alert" className="console__notice cyo-text-muted">
          {refreshError}{' '}
          <button type="button" onClick={() => setRefreshError(null)} aria-label="Dismiss">
            Dismiss
          </button>
        </p>
      ) : null}

      {refreshing && state.kind === 'ready' ? <LoadingStatus>Refreshing…</LoadingStatus> : null}

      {state.kind === 'ready' && state.data.events.length === 0 ? (
        <p className="console__muted cyo-text-muted">No matching audit events.</p>
      ) : null}

      {state.kind === 'ready' && state.data.events.length > 0 ? (
        <>
          <table>
            <thead>
              <tr>
                <th scope="col">Occurred at</th>
                <th scope="col">Event kind</th>
                <th scope="col">Actor</th>
                <th scope="col">Entity</th>
                <th scope="col">Transition</th>
                <th scope="col">Payload</th>
              </tr>
            </thead>
            <tbody>
              {state.data.events.map((event) => (
                <tr key={event.id}>
                  <td>{new Date(event.occurred_at).toLocaleString()}</td>
                  <td>{event.event_type}</td>
                  <td>{actorLabel(event)}</td>
                  <td>{entityLabel(event)}</td>
                  <td>{transitionLabel(event)}</td>
                  <td>
                    <code>{JSON.stringify(event.payload)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            <button
              type="button"
              disabled={!canGoPrevious}
              onClick={() => setOffset((prev) => Math.max(0, prev - PAGE_SIZE))}
            >
              Previous page
            </button>
            <button
              type="button"
              disabled={!canGoNext}
              onClick={() => setOffset((prev) => prev + PAGE_SIZE)}
            >
              Next page
            </button>
          </p>
        </>
      ) : null}
    </main>
  )
}
