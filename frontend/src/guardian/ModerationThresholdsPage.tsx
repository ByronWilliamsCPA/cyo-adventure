import { useEffect, useState } from 'react'

import { classifyApiError } from '../hooks/classifyApiError'
import { AGE_BANDS, type AgeBandValue } from '../profiles/profilesApi'
import {
  deleteThresholdApiV1AdminModerationThresholdsAgeBandCategoryDelete as deleteThreshold,
  listThresholdsApiV1AdminModerationThresholdsGet as listThresholds,
  upsertThresholdApiV1AdminModerationThresholdsAgeBandCategoryPut as upsertThreshold,
} from '../client/sdk.gen'
import type { ThresholdListView } from '../client/types.gen'

const VERDICTS = ['advisory', 'flag', 'block'] as const
type VerdictValue = (typeof VERDICTS)[number]

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; data: ThresholdListView }

/**
 * Per-call options for the generated OpenAPI client on this page.
 *
 * Every other guardian page reaches the backend through `useApi()`'s axios
 * instance, which already carries a same-origin base URL (dev proxy / prod
 * reverse proxy both forward `/api/*` from the page's own origin) and an
 * Authorization interceptor. This page is the first to call the generated
 * client (`src/client/sdk.gen.ts`) directly, and that client's own default
 * instance (`src/client/client.gen.ts`) has neither: its base URL is a
 * hardcoded `http://localhost:8000` baked in at generation time, and it has
 * no auth interceptor at all.
 *
 * #CRITICAL: security: without an explicit Authorization header every call
 * from this admin-only page would go out unauthenticated and 401 outside a
 * developer's own machine; without the baseURL override every call would
 * bypass the dev/prod reverse proxy and hit a literal `localhost:8000`.
 * #VERIFY: ModerationThresholdsPage.test.tsx asserts each generated call
 * receives an explicit Authorization header sourced from `auth_token`.
 */
function requestOptions() {
  const token = localStorage.getItem('auth_token')
  return {
    baseURL: window.location.origin,
    throwOnError: true as const,
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  }
}

/**
 * Admin-only editor for age-band moderation surfacing thresholds (WS-A Task 7).
 *
 * Lists the code default plus every stored (age_band, category) override and
 * lets an admin add, update, or remove one. Registered admin-only in
 * router.tsx: guardians who are not admins never reach this page, and the
 * backend re-checks the admin role on every call regardless.
 */
export function ModerationThresholdsPage() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [band, setBand] = useState<AgeBandValue>(AGE_BANDS[0])
  const [category, setCategory] = useState('')
  const [verdict, setVerdict] = useState<VerdictValue>('advisory')
  const [score, setScore] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  // Mount-time load, matching ReviewDetailPage's cancelled-guard idiom so an
  // unmount before the request resolves never calls setState on a gone
  // component. refreshList() below (used after save/remove, from event
  // handlers rather than an effect) is a separate function on purpose: an
  // effect body must not call an outside setState-calling function directly
  // (react-hooks/set-state-in-effect), so the initial load is inlined here.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await listThresholds(requestOptions())
        if (!cancelled) setState({ kind: 'ready', data: res.data })
      } catch (err) {
        // Log the message, not the axios error object (its config.headers
        // carries the caller's Authorization bearer token).
        console.error('threshold list load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) {
          setState({
            kind: 'error',
            message: classifyApiError(err, {
              transient: 'We could not load moderation thresholds. Please reload.',
            }).message,
          })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [])

  async function refreshList() {
    try {
      const res = await listThresholds(requestOptions())
      setState({ kind: 'ready', data: res.data })
    } catch (err) {
      console.error('threshold list load failed:', err instanceof Error ? err.message : err)
      setState({
        kind: 'error',
        message: classifyApiError(err, {
          transient: 'We could not load moderation thresholds. Please reload.',
        }).message,
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
      <p role="alert" className="console__error">
        {state.message}
      </p>
    )
  }

  const { data } = state
  const trimmedCategory = category.trim()
  const scoreValid = score === '' || (Number(score) >= 0 && Number(score) <= 1)
  const canSave = trimmedCategory.length > 0 && scoreValid && !submitting

  async function save() {
    if (!canSave) return
    setSubmitting(true)
    setActionError(null)
    try {
      await upsertThreshold({
        ...requestOptions(),
        path: { age_band: band, category: trimmedCategory },
        body: {
          min_verdict: verdict,
          min_score: score === '' ? null : Number(score),
        },
      })
      setCategory('')
      setScore('')
      await refreshList()
    } catch (err) {
      console.error('threshold upsert failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not save that override. Please try again.',
        }).message
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function remove(rowBand: string, rowCategory: string) {
    setSubmitting(true)
    setActionError(null)
    try {
      // The delete endpoint returns the full refreshed list view, so no
      // separate refreshList() round-trip is needed after a successful removal.
      const res = await deleteThreshold({
        ...requestOptions(),
        path: { age_band: rowBand, category: rowCategory },
      })
      setState({ kind: 'ready', data: res.data })
    } catch (err) {
      console.error('threshold delete failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not remove that override. Please try again.',
        }).message
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main>
      <h1>Moderation thresholds</h1>
      <p>
        Default: findings surface to families at <strong>{data.default_min_verdict}</strong> and
        above. Overrides below change that for one age band and category.
      </p>
      {actionError ? (
        <p role="alert" className="console__error">
          {actionError}
        </p>
      ) : null}
      {data.rows.length === 0 ? (
        <p className="console__muted">
          No overrides yet. Every age band and category uses the default above.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Age band</th>
              <th scope="col">Category</th>
              <th scope="col">Surfaces at</th>
              <th scope="col">Score floor</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={`${row.age_band}:${row.category}`}>
                <td>{row.age_band}</td>
                <td>{row.category}</td>
                <td>{row.min_verdict}</td>
                <td>{row.min_score ?? '-'}</td>
                <td>
                  <button
                    type="button"
                    disabled={submitting}
                    onClick={() => void remove(row.age_band, row.category)}
                  >
                    Remove {row.category} override for {row.age_band}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h2>Add or update an override</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void save()
        }}
      >
        <label>
          Age band
          <select value={band} onChange={(e) => setBand(e.target.value as AgeBandValue)}>
            {AGE_BANDS.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </label>
        <label>
          Category
          <input
            list="known-categories"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            required
          />
          <datalist id="known-categories">
            {data.known_categories.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </label>
        <label>
          Surfaces at
          <select value={verdict} onChange={(e) => setVerdict(e.target.value as VerdictValue)}>
            {VERDICTS.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Score floor (0-1, optional)
          <input
            type="number"
            min="0"
            max="1"
            step="0.05"
            value={score}
            onChange={(e) => setScore(e.target.value)}
            aria-describedby="threshold-score-help"
          />
        </label>
        <p id="threshold-score-help" className="console__muted">
          Leave blank for no score floor.
        </p>
        <button type="submit" disabled={!canSave}>
          Save override
        </button>
      </form>
    </main>
  )
}
