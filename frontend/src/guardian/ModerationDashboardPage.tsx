import { useEffect, useMemo, useState } from 'react'

import type {
  ModerationDashboardView,
  SuggestionListView,
  ThresholdSuggestionView,
} from '../client/types.gen'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { makeModerationDashboardApi } from './moderationDashboardApi'
import { makeThresholdsApi } from './moderationThresholdsApi'

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | {
      kind: 'ready'
      dashboard: ModerationDashboardView
      suggestions: SuggestionListView
    }

/**
 * Admin-only moderation dashboard (WS-F): override evidence per age band and
 * category, computed threshold suggestions, and a recent-changes feed. The
 * apply control reuses the existing thresholds upsert (moderationThresholdsApi,
 * WS-F decision F3): there is no separate write path for suggestions, only a
 * pre-filled call into the same admin endpoint an admin could hit by hand from
 * the thresholds page. Registered admin-only in router.tsx, mirroring
 * ModerationThresholdsPage.
 */
export function ModerationDashboardPage() {
  const api = useApi()
  const dashboardApi = useMemo(() => makeModerationDashboardApi(api), [api])
  const thresholdsApi = useMemo(() => makeThresholdsApi(api), [api])
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [actionError, setActionError] = useState<string | null>(null)
  const [applying, setApplying] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  // Mount-time (and post-apply) load, matching ModerationThresholdsPage's
  // cancelled-guard idiom so an unmount before the request resolves never
  // calls setState on a gone component. Bumping reloadKey after a successful
  // apply re-runs this same effect rather than a separate refresh function,
  // since both GETs here are part of one page-readiness check.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [dashboard, suggestions] = await Promise.all([
          dashboardApi.dashboard(),
          dashboardApi.suggestions(),
        ])
        if (!cancelled) setState({ kind: 'ready', dashboard, suggestions })
      } catch (err) {
        console.error('moderation dashboard load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) {
          setState({
            kind: 'error',
            message: classifyApiError(err, {
              transient: 'We could not load the moderation dashboard. Please reload.',
            }).message,
          })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [dashboardApi, reloadKey])

  async function applySuggestion(suggestion: ThresholdSuggestionView) {
    const key = `${suggestion.age_band}:${suggestion.category}`
    setApplying(key)
    setActionError(null)
    try {
      await thresholdsApi.upsert(suggestion.age_band, suggestion.category, {
        min_verdict: suggestion.suggested_min_verdict,
        min_score: suggestion.current_min_score ?? null,
      })
      setReloadKey((k) => k + 1)
    } catch (err) {
      console.error('threshold suggestion apply failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not apply that suggestion. Please try again.',
        }).message
      )
    } finally {
      setApplying(null)
    }
  }

  if (state.kind === 'loading') {
    return (
      <div role="status" aria-live="polite">
        Loading…
      </div>
    )
  }
  if (state.kind === 'error') {
    return (
      <p role="alert" className="console__error">
        {state.message}
      </p>
    )
  }

  const { dashboard, suggestions } = state
  return (
    <main>
      <h1>Moderation dashboard</h1>
      {actionError ? (
        <p role="alert" className="console__error">
          {actionError}
        </p>
      ) : null}

      <section aria-labelledby="suggestions-heading">
        <h2 id="suggestions-heading">Threshold suggestions</h2>
        <p className="console__muted">
          Computed from override evidence (at least {suggestions.min_decided_versions} decided books
          and {Math.round(suggestions.min_override_rate * 100)}% released despite the finding).
          Nothing changes until you apply it.
        </p>
        {suggestions.suggestions.length === 0 ? (
          <p className="console__muted">No threshold suggestions right now.</p>
        ) : (
          <ul>
            {suggestions.suggestions.map((suggestion) => {
              const key = `${suggestion.age_band}:${suggestion.category}`
              return (
                <li key={key}>
                  <strong>
                    {suggestion.category} in {suggestion.age_band}
                  </strong>
                  : released {suggestion.released_versions} of {suggestion.decided_versions} times
                  despite the finding ({Math.round(suggestion.override_rate * 100)}%). Suggested new
                  surfacing level: {suggestion.suggested_min_verdict} (currently{' '}
                  {suggestion.current_min_verdict}).
                  <button
                    type="button"
                    disabled={applying === key}
                    onClick={() => void applySuggestion(suggestion)}
                  >
                    {applying === key
                      ? 'Applying…'
                      : `Apply: raise to ${suggestion.suggested_min_verdict}`}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="insights-heading">
        <h2 id="insights-heading">Override evidence</h2>
        {dashboard.insights.length === 0 ? (
          <p className="console__muted">No moderated books with advisory or flag findings yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th scope="col">Age band</th>
                <th scope="col">Category</th>
                <th scope="col">Advisories</th>
                <th scope="col">Flags</th>
                <th scope="col">Decided</th>
                <th scope="col">Released</th>
                <th scope="col">Override rate</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.insights.map((row) => (
                <tr key={`${row.age_band}:${row.category}`}>
                  <td>{row.age_band}</td>
                  <td>{row.category}</td>
                  <td>{row.advisory_findings}</td>
                  <td>{row.flag_findings}</td>
                  <td>{row.decided_versions}</td>
                  <td>{row.released_versions}</td>
                  <td>
                    {row.override_rate == null ? 'n/a' : `${Math.round(row.override_rate * 100)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section aria-labelledby="changes-heading">
        <h2 id="changes-heading">Recent threshold changes</h2>
        {dashboard.recent_changes.length === 0 ? (
          <p className="console__muted">No threshold changes recorded.</p>
        ) : (
          <ul>
            {dashboard.recent_changes.map((change) => (
              <li key={`${change.event_type}:${change.entity_id}:${change.occurred_at}`}>
                <code>{change.event_type}</code> {change.entity_id} at{' '}
                {new Date(change.occurred_at).toLocaleString()}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  )
}
