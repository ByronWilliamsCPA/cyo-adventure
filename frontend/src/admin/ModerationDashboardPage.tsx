import { useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import type {
  ModerationDashboardView,
  SuggestionListView,
  ThresholdChangeView,
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
 * Human-readable line for one recent threshold/noise-floor change.
 *
 * The wire payload is an untyped blob ({[key: string]: unknown}), so every
 * field is type-checked before use. Returns null when the payload lacks the
 * fields for a readable sentence, letting the caller fall back to the raw
 * event_type. The event log carries no actor field, so no author is shown.
 */
function describeChange(change: ThresholdChangeView): string | null {
  const text = (key: string): string | null => {
    const value = change.payload[key]
    return typeof value === 'string' ? value : null
  }
  const num = (key: string): number | null => {
    const value = change.payload[key]
    return typeof value === 'number' ? value : null
  }
  const floor = num('value')
  if (change.event_type === 'noise_floor_changed' && floor != null) {
    return `Admin noise floor set to ${floor}`
  }
  const category = text('category')
  const ageBand = text('age_band')
  if (category == null || ageBand == null) return null
  if (text('action') === 'delete') {
    return `${category} in ${ageBand}: override removed, the default applies again`
  }
  const verdict = text('min_verdict')
  if (verdict == null) return null
  const score = num('min_score')
  const scoreSuffix = score == null ? '' : ` (score floor ${score})`
  return `${category} in ${ageBand}: now surfaces at ${verdict}${scoreSuffix}`
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
  // #ASSUME: external resources: the post-apply refresh (reloadKey bump)
  // reuses the same load() effect as the initial mount load, so a transient
  // GET failure on that refresh must not wipe an already-rendered dashboard.
  // hasLoadedRef (not state) tracks "has a load ever succeeded" because state
  // itself is not, and must not become, a dependency of the load effect: an
  // effect depending on state would refire every time state changes, turning
  // every successful load into an infinite refetch loop.
  // #VERIFY: covered by the "keeps last-good data when a post-apply refresh
  // fails" test in ModerationDashboardPage.test.tsx.
  const hasLoadedRef = useRef(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  // #ASSUME: concurrency: multiple suggestion applies can be in flight at
  // once, so the in-flight guard is tracked per suggestion key, never as one
  // shared value (a shared value would re-enable A's button when B starts and
  // clear B's guard when A settles).
  // #VERIFY: covered by the "keeps per-suggestion apply buttons independent
  // while applies are in flight" test in ModerationDashboardPage.test.tsx.
  const [applying, setApplying] = useState<ReadonlySet<string>>(new Set())
  const [reloadKey, setReloadKey] = useState(0)
  // Suggestion awaiting confirmation. Applying a suggestion changes live
  // surfacing behavior, so the upsert only fires from the confirm dialog,
  // never straight off the list button.
  const [confirming, setConfirming] = useState<ThresholdSuggestionView | null>(null)

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
        if (!cancelled) {
          hasLoadedRef.current = true
          setRefreshError(null)
          setState({ kind: 'ready', dashboard, suggestions })
        }
      } catch (err) {
        console.error('moderation dashboard load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) {
          if (hasLoadedRef.current) {
            // A refresh after a successful apply failed: keep showing the
            // last-good dashboard/suggestions rather than replacing the whole
            // page with a full-page error, and surface a dismissible notice
            // instead.
            setRefreshError(
              classifyApiError(err, {
                transient: 'We could not refresh the dashboard; showing the last loaded data.',
                server: 'We could not refresh the dashboard; showing the last loaded data.',
              }).message
            )
          } else {
            setState({
              kind: 'error',
              message: classifyApiError(err, {
                transient: 'We could not load the moderation dashboard. Please reload.',
                server: 'We could not load the moderation dashboard. Please reload.',
              }).message,
            })
          }
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [dashboardApi, reloadKey])

  async function applySuggestion(suggestion: ThresholdSuggestionView) {
    // JSON.stringify (not a plain `${age_band}:${category}` join) because
    // category is an open-ended, provider-defined string that may itself
    // contain ':' (or any other single-character delimiter), which would let
    // two distinct suggestions collide on the same in-flight guard key.
    const key = JSON.stringify([suggestion.age_band, suggestion.category])
    // Build a new Set on every update (never mutate state in place) and add
    // or remove exactly this suggestion's key, so concurrent applies on other
    // suggestions keep their own in-flight guards.
    setApplying((prev) => new Set(prev).add(key))
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
          transient: `We could not apply the suggestion for ${suggestion.category} in ${suggestion.age_band}. Please try again.`,
          server: `We could not apply the suggestion for ${suggestion.category} in ${suggestion.age_band}. Please try again.`,
        }).message
      )
    } finally {
      setApplying((prev) => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
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
      <p role="alert" className="console__error cyo-text-error">
        {state.message}
      </p>
    )
  }

  const { dashboard, suggestions } = state
  // Strongest override evidence first; rows with no decided versions (null
  // rate) sort last. Array.prototype.sort is stable, so equal rates keep the
  // API's (age_band, category) ordering.
  const sortedInsights = [...dashboard.insights].sort(
    (a, b) => (b.override_rate ?? -1) - (a.override_rate ?? -1)
  )
  return (
    <main>
      <h1>Moderation dashboard</h1>
      {refreshError ? (
        <p role="alert" className="console__notice cyo-text-muted">
          {refreshError}{' '}
          <button
            type="button"
            className="moderation-dashboard__button"
            onClick={() => setRefreshError(null)}
            aria-label="Dismiss"
          >
            Dismiss
          </button>
        </p>
      ) : null}
      {actionError ? (
        <p role="alert" className="console__error cyo-text-error">
          {actionError}
        </p>
      ) : null}

      <section aria-labelledby="suggestions-heading">
        <h2 id="suggestions-heading">Threshold suggestions</h2>
        <p className="console__muted cyo-text-muted">
          Computed from override evidence (at least {suggestions.min_decided_versions} decided books
          and {Math.round(suggestions.min_override_rate * 100)}% released despite the finding).
          Nothing changes until you apply it.
        </p>
        {suggestions.suggestions.length === 0 ? (
          <p className="console__muted cyo-text-muted">No threshold suggestions right now.</p>
        ) : (
          <ul>
            {suggestions.suggestions.map((suggestion) => {
              // Same JSON.stringify encoding as applySuggestion's in-flight
              // guard key, so the disabled lookup below always matches.
              const key = JSON.stringify([suggestion.age_band, suggestion.category])
              return (
                <li key={key}>
                  <strong>
                    {suggestion.category} in {suggestion.age_band}
                  </strong>
                  : released {suggestion.released_versions} of {suggestion.decided_versions} times
                  despite the finding ({Math.round(suggestion.override_rate * 100)}%). Suggested new
                  surfacing level: {suggestion.suggested_min_verdict} (currently{' '}
                  {suggestion.current_min_verdict}).
                  {/*
                    #CRITICAL: security: applying a suggestion changes what
                    this band/category surfaces to families, so the button
                    only opens a confirm dialog echoing the change; the upsert
                    fires from the dialog's confirm action.
                    #VERIFY: ModerationDashboardPage.test.tsx confirm and
                    cancel tests (cancel fires no PUT; confirm fires exactly
                    one).
                  */}
                  <button
                    type="button"
                    className="moderation-dashboard__button"
                    disabled={applying.has(key)}
                    aria-label={`Apply: raise ${suggestion.category} (${suggestion.age_band}) to ${suggestion.suggested_min_verdict}`}
                    onClick={() => setConfirming(suggestion)}
                  >
                    {applying.has(key)
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
          <p className="console__muted cyo-text-muted">
            No moderated books with advisory or flag findings yet.
          </p>
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
                <th scope="col">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {sortedInsights.map((row) => {
                // At or above the gate that generates suggestions: emphasize
                // the row so gate-crossing evidence stands out at a glance.
                const atGate =
                  row.override_rate != null && row.override_rate >= suggestions.min_override_rate
                const rate =
                  row.override_rate == null ? 'n/a' : `${Math.round(row.override_rate * 100)}%`
                return (
                  <tr
                    key={`${row.age_band}:${row.category}`}
                    className={atGate ? 'moderation-insight--at-gate' : undefined}
                  >
                    <td>{row.age_band}</td>
                    <td>{row.category}</td>
                    <td>{row.advisory_findings}</td>
                    <td>{row.flag_findings}</td>
                    <td>{row.decided_versions}</td>
                    <td>{row.released_versions}</td>
                    <td>{atGate ? <strong>{rate}</strong> : rate}</td>
                    <td>{new Date(row.last_seen).toLocaleString()}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>

      <section aria-labelledby="changes-heading">
        <h2 id="changes-heading">Recent threshold changes</h2>
        {dashboard.recent_changes.length === 0 ? (
          <p className="console__muted cyo-text-muted">No threshold changes recorded.</p>
        ) : (
          <ul>
            {dashboard.recent_changes.map((change) => {
              const description = describeChange(change)
              return (
                <li key={`${change.event_type}:${change.entity_id}:${change.occurred_at}`}>
                  {description ?? (
                    <>
                      <code>{change.event_type}</code> {change.entity_id}
                    </>
                  )}{' '}
                  at {new Date(change.occurred_at).toLocaleString()}
                </li>
              )
            })}
          </ul>
        )}
      </section>

      {confirming ? (
        <Dialog
          title="Apply this threshold suggestion?"
          onClose={() => setConfirming(null)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setConfirming(null)}>
                Cancel
              </Button>
              <Button
                onClick={() => {
                  const suggestion = confirming
                  setConfirming(null)
                  void applySuggestion(suggestion)
                }}
              >
                Confirm apply
              </Button>
            </>
          }
        >
          <p>
            {confirming.category} in {confirming.age_band}: surfacing level changes from{' '}
            <strong>{confirming.current_min_verdict}</strong> to{' '}
            <strong>{confirming.suggested_min_verdict}</strong>.
          </p>
        </Dialog>
      ) : null}
    </main>
  )
}
