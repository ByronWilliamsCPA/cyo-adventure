import { useEffect, useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { AGE_BANDS, type AgeBandValue } from '../profiles/profilesApi'
import { makeThresholdsApi } from './moderationThresholdsApi'
import type { ThresholdListView, ThresholdView } from '../client/types.gen'

const VERDICTS = ['advisory', 'flag', 'block'] as const
type VerdictValue = (typeof VERDICTS)[number]

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; data: ThresholdListView }

// Every mutation on this page changes live safety behavior for families, so
// each one is gated behind a confirm dialog (the ReviewDetailPage pattern)
// instead of firing on a single click. Only one confirm can be pending at a
// time.
type PendingConfirm =
  | { kind: 'remove'; row: ThresholdView }
  | { kind: 'noise-floor'; value: number }
  | { kind: 'new-category'; category: string }
  | null

// Above this floor most advisory findings score lower and would be hidden
// from reviewers, so the confirm dialog adds an explicit warning line.
const NOISE_FLOOR_WARN_ABOVE = 0.3

const isFloorInRange = (value: number) => value >= 0 && value <= 1

/**
 * Admin-only editor for age-band moderation surfacing thresholds (WS-A Task 7).
 *
 * Lists the code default plus every stored (age_band, category) override and
 * lets an admin add, update, or remove one. Registered admin-only in
 * router.tsx: guardians who are not admins never reach this page, and the
 * backend re-checks the admin role on every call regardless.
 */
export function ModerationThresholdsPage() {
  const api = useApi()
  const thresholdsApi = useMemo(() => makeThresholdsApi(api), [api])

  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [band, setBand] = useState<AgeBandValue>(AGE_BANDS[0])
  const [category, setCategory] = useState('')
  const [verdict, setVerdict] = useState<VerdictValue>('advisory')
  const [score, setScore] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [noiseFloorInput, setNoiseFloorInput] = useState('')
  const [savingFloor, setSavingFloor] = useState(false)
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm>(null)

  // Mount-time load, matching ReviewDetailPage's cancelled-guard idiom so an
  // unmount before the request resolves never calls setState on a gone
  // component. refreshAfterMutation() below (used after a successful save,
  // from an event handler rather than an effect) is a separate function on
  // purpose: an effect body must not call an outside setState-calling
  // function directly (react-hooks/set-state-in-effect), so the initial load
  // is inlined here. This initial load is also the only place a failure
  // should replace the whole page with the top-level error state: it is the
  // only point where there is no ready table/form to preserve yet. The admin
  // noise floor is folded into this same load: both requests are part of the
  // one initial page-readiness check, so a failure of either one is a
  // top-level load failure, not a scoped action error.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [data, floor] = await Promise.all([
          thresholdsApi.list(),
          thresholdsApi.getNoiseFloor(),
        ])
        if (!cancelled) {
          setState({ kind: 'ready', data })
          setNoiseFloorInput(String(floor.value))
        }
      } catch (err) {
        // Log the message, not the axios error object (its config.headers
        // carries the caller's Authorization bearer token).
        console.error('threshold list load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) {
          setState({
            kind: 'error',
            message: classifyApiError(err, {
              transient: 'We could not load moderation thresholds. Please reload.',
              server: 'We could not load moderation thresholds. Please reload.',
            }).message,
          })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [thresholdsApi])

  // Re-fetches the list after a save that has already succeeded. A failure
  // here must NOT replace the ready table/form with the top-level error
  // state: the admin's edit went through, only the on-screen list is stale.
  // Surface it as the same scoped actionError the save/delete failure paths
  // use instead, so the table and form stay visible and usable.
  async function refreshAfterMutation() {
    try {
      const data = await thresholdsApi.list()
      setState({ kind: 'ready', data })
    } catch (err) {
      console.error('threshold list refresh failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient:
            'That override saved, but the list could not refresh. Reload to see the latest changes.',
          server:
            'That override saved, but the list could not refresh. Reload to see the latest changes.',
        }).message
      )
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

  const { data } = state
  const trimmedCategory = category.trim()
  const scoreValid = score === '' || (Number(score) >= 0 && Number(score) <= 1)
  const canSave = trimmedCategory.length > 0 && scoreValid && !submitting
  const noiseFloorValid = noiseFloorInput !== '' && isFloorInRange(Number(noiseFloorInput))
  const canSaveFloor = noiseFloorValid && !savingFloor
  // known_categories is advisory, never a gate (backend KNOWN_CATEGORIES:
  // classifier categories are open-ended, provider-defined strings), so an
  // unknown category is legal but usually a typo that would create an
  // override that never matches a finding. It routes through an extra
  // confirm instead of a hard block.
  const isKnownCategory = data.known_categories.includes(trimmedCategory)

  async function save() {
    if (!canSave) return
    setSubmitting(true)
    setActionError(null)
    try {
      await thresholdsApi.upsert(band, trimmedCategory, {
        min_verdict: verdict,
        min_score: score === '' ? null : Number(score),
      })
      setCategory('')
      setScore('')
      await refreshAfterMutation()
    } catch (err) {
      console.error('threshold upsert failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not save that override. Please try again.',
          server: 'We could not save that override. Please try again.',
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
      // separate refreshAfterMutation() round-trip is needed after a
      // successful removal.
      const data = await thresholdsApi.remove(rowBand, rowCategory)
      setState({ kind: 'ready', data })
    } catch (err) {
      console.error('threshold delete failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not remove that override. Please try again.',
          server: 'We could not remove that override. Please try again.',
        }).message
      )
    } finally {
      setSubmitting(false)
    }
  }

  // Saves the admin noise floor. A save failure is a scoped actionError, not
  // a top-level page error: the threshold table and this control both stay
  // usable, only the attempted edit did not take.
  async function saveNoiseFloor() {
    if (!canSaveFloor) return
    setSavingFloor(true)
    setActionError(null)
    try {
      const floor = await thresholdsApi.setNoiseFloor(Number(noiseFloorInput))
      setNoiseFloorInput(String(floor.value))
    } catch (err) {
      console.error('noise floor save failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not save the noise floor. Please try again.',
          server: 'We could not save the noise floor. Please try again.',
        }).message
      )
    } finally {
      setSavingFloor(false)
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
        <p role="alert" className="console__error cyo-text-error">
          {actionError}
        </p>
      ) : null}
      <section>
        <h2>Admin noise floor</h2>
        <p id="noise-floor-help" className="console__muted cyo-text-muted">
          Advisory findings scoring below this value are hidden from the admin review surface. Flag
          and block findings always show.
        </p>
        <label>
          Noise floor (0-1)
          <input
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={noiseFloorInput}
            onChange={(e) => setNoiseFloorInput(e.target.value)}
            aria-describedby="noise-floor-help"
          />
        </label>
        {/*
          #CRITICAL: security: the noise floor hides advisory findings from
          every reviewer, so the save is gated behind a confirm dialog that
          states the concrete consequence instead of firing on one click.
          #VERIFY: ModerationThresholdsPage.test.tsx noise-floor confirm and
          cancel tests (cancel fires no PUT; confirm fires exactly one).
        */}
        <button
          type="button"
          disabled={!canSaveFloor}
          onClick={() => setPendingConfirm({ kind: 'noise-floor', value: Number(noiseFloorInput) })}
        >
          Save noise floor
        </button>
      </section>
      {data.rows.length === 0 ? (
        <p className="console__muted cyo-text-muted">
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
                  {/*
                    #CRITICAL: security: removing an override instantly changes
                    what this band/category surfaces to families, so the
                    delete is gated behind a confirm dialog naming the default
                    it reverts to instead of firing on one click.
                    #VERIFY: ModerationThresholdsPage.test.tsx remove confirm
                    and cancel tests (cancel fires no DELETE; confirm fires
                    exactly one).
                  */}
                  <button
                    type="button"
                    disabled={submitting}
                    onClick={() => setPendingConfirm({ kind: 'remove', row })}
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
          if (!canSave) return
          // An unknown category is not blocked (categories are open-ended and
          // provider-defined) but it needs a deliberate extra confirmation:
          // a typo here silently creates an override that never applies.
          if (isKnownCategory) {
            void save()
          } else {
            setPendingConfirm({ kind: 'new-category', category: trimmedCategory })
          }
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
        <p id="threshold-score-help" className="console__muted cyo-text-muted">
          Leave blank for no score floor.
        </p>
        <button type="submit" disabled={!canSave}>
          Save override
        </button>
      </form>

      {pendingConfirm?.kind === 'remove' ? (
        <Dialog
          title={`Remove the ${pendingConfirm.row.category} override for ${pendingConfirm.row.age_band}?`}
          onClose={() => setPendingConfirm(null)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setPendingConfirm(null)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                disabled={submitting}
                onClick={() => {
                  const { row } = pendingConfirm
                  setPendingConfirm(null)
                  void remove(row.age_band, row.category)
                }}
              >
                Confirm remove
              </Button>
            </>
          }
        >
          <p>
            {pendingConfirm.row.category} findings for {pendingConfirm.row.age_band} revert to the
            default surfacing level: <strong>{data.default_min_verdict}</strong>.
          </p>
        </Dialog>
      ) : null}

      {pendingConfirm?.kind === 'noise-floor' ? (
        <Dialog
          title="Save admin noise floor?"
          onClose={() => setPendingConfirm(null)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setPendingConfirm(null)}>
                Cancel
              </Button>
              <Button
                disabled={savingFloor}
                onClick={() => {
                  setPendingConfirm(null)
                  void saveNoiseFloor()
                }}
              >
                Confirm noise floor
              </Button>
            </>
          }
        >
          <p>
            Advisory findings scoring below {pendingConfirm.value} will be hidden from reviewers on
            the review surface.
          </p>
          {pendingConfirm.value > NOISE_FLOOR_WARN_ABOVE ? (
            <p className="cyo-text-error">
              Warning: a noise floor above {NOISE_FLOOR_WARN_ABOVE} will hide most advisory
              findings.
            </p>
          ) : null}
        </Dialog>
      ) : null}

      {pendingConfirm?.kind === 'new-category' ? (
        <Dialog
          title={`Create override for new category '${pendingConfirm.category}'?`}
          onClose={() => setPendingConfirm(null)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setPendingConfirm(null)}>
                Cancel
              </Button>
              <Button
                disabled={submitting}
                onClick={() => {
                  setPendingConfirm(null)
                  void save()
                }}
              >
                Create new-category override
              </Button>
            </>
          }
        >
          <p>
            '{pendingConfirm.category}' is not in the known category list. It only applies if
            classifiers emit this exact name; if this is a typo, the override will never match a
            finding.
          </p>
        </Dialog>
      ) : null}
    </main>
  )
}
