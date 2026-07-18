import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { formatRelativeTime } from '../guardian/intakeApi'
import { ageBandLabel } from '../guardian/storyRequestOptions'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { makeAdminLibraryApi, type StorybookSummary } from './adminLibraryApi'
import './admin.css'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'forbidden' }
  | { kind: 'error' }
  | { kind: 'ready'; items: StorybookSummary[]; loadedAt: number }

// The lifecycle statuses an admin can filter by. 'all' passes no filter.
const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'published', label: 'Published' },
  { value: 'in_review', label: 'In review' },
  { value: 'needs_revision', label: 'Needs revision' },
  { value: 'archived', label: 'Archived' },
  { value: 'draft', label: 'Draft' },
]

const STATUS_LABELS: Record<string, string> = {
  published: 'Published',
  in_review: 'In review',
  needs_revision: 'Needs revision',
  archived: 'Archived',
  draft: 'Draft',
}

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status
}

/**
 * Admin master library (P19): browse every storybook in any lifecycle status,
 * so an admin can re-open a published, archived, or needs-revision story via
 * the existing review detail page, not only the in-review review queue.
 */
export function AdminLibraryPage() {
  const api = useApi()
  const libraryApi = useMemo(() => makeAdminLibraryApi(api), [api])
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [filter, setFilter] = useState('all')
  const [reloadKey, setReloadKey] = useState(0)
  const retry = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setState({ kind: 'loading' })
      try {
        const items = await libraryApi.list(filter === 'all' ? undefined : filter)
        if (!cancelled) setState({ kind: 'ready', items, loadedAt: Date.now() })
      } catch (err) {
        if (cancelled) return
        // A 403 means the admin capability was revoked mid-session (expected),
        // not a failure; surface a clear notice rather than a broken page.
        if (classifyApiError(err).kind === 'forbidden') {
          setState({ kind: 'forbidden' })
          return
        }
        // Log the message, never the axios error (its config carries the bearer).
        console.error(
          'admin library load failed:',
          err instanceof Error ? err.message : err
        )
        setState({ kind: 'error' })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [libraryApi, filter, reloadKey])

  if (state.kind === 'loading') {
    return (
      <section className="admin-library">
        <h1>Story library</h1>
        <div role="status" aria-live="polite">
          Loading stories…
        </div>
      </section>
    )
  }
  if (state.kind === 'forbidden') {
    return (
      <section className="admin-library">
        <h1>Story library</h1>
        <p className="console__notice cyo-text-muted">
          Your account does not have review access. The library is for the safety reviewer.
        </p>
      </section>
    )
  }
  if (state.kind === 'error') {
    return (
      <section className="admin-library">
        <h1>Story library</h1>
        <div role="alert" className="console__error">
          <p className="cyo-text-error">We could not load the story library.</p>
          <Button variant="primary" onClick={retry}>
            Try again
          </Button>
        </div>
      </section>
    )
  }

  const { items, loadedAt } = state
  return (
    <section className="admin-library">
      <h1>Story library</h1>
      <div className="admin-library__filters" role="group" aria-label="Filter by status">
        {STATUS_FILTERS.map((option) => (
          <button
            key={option.value}
            type="button"
            aria-pressed={filter === option.value}
            className={
              filter === option.value
                ? 'admin-library__filter admin-library__filter--active'
                : 'admin-library__filter'
            }
            onClick={() => setFilter(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {items.length === 0 ? (
        <EmptyState
          title="No stories here"
          description="No stories match this filter yet."
        />
      ) : (
        <ul className="console-list">
          {items.map((item) => {
            const updated =
              typeof item.updated_at === 'string'
                ? formatRelativeTime(item.updated_at, loadedAt)
                : null
            return (
              <li key={item.storybook_id} className="console-row cyo-card cyo-card--interactive">
                <Link className="console-row__link" to={`/admin/review/${item.storybook_id}`}>
                  <span className="console-row__title">{item.title}</span>
                  <span className="console-row__meta cyo-text-muted">
                    <span className="admin-library__status">{statusLabel(item.status)}</span>
                    {item.age_band ? <span> · {ageBandLabel(item.age_band)}</span> : null}
                    {updated ? <span> · Updated {updated}</span> : null}
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
