import { useEffect, useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import type {
  AgeBand,
  FamilyView,
  Length,
  NarrativeStyle,
  ProfileView,
  StoryRequestAuthoredCreateBody,
} from '../client/types.gen'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { makeAuthoredRequestApi } from './authoredRequestApi'
import { AGE_BANDS, LENGTHS, TEEN_BANDS, ageBandLabel } from './storyRequestOptions'

type LoadState = { kind: 'loading' } | { kind: 'error' } | { kind: 'ready' }

type SubmitResult =
  { kind: 'idle' } | { kind: 'success' } | { kind: 'blocked' } | { kind: 'error'; message: string }

interface RequestStoryFormProps {
  mode: 'guardian' | 'admin'
}

// Sentinel value for the guardian child select's "No specific child" option
// and the admin family select's unselected placeholder. Both selects are
// native <select> elements, whose values are always strings, so an empty
// string reads unambiguously as "nothing chosen yet" for either field.
const UNSELECTED = ''

// Mirrors the backend RequestText cap (api/schemas.py, max_length=500, same
// as the story_request.request_text column) and the kid-facing form
// (library/RequestStory.tsx). A looser client cap would let the author type
// past the contract and hit a 422 the form can only render generically.
const REQUEST_TEXT_MAX = 500

// The "N / 500" counter is always visible but only becomes a polite live
// region near the cap (>=90%), so screen readers hear the shrinking budget
// when it matters instead of on every keystroke.
const REQUEST_TEXT_WARN_AT = REQUEST_TEXT_MAX * 0.9

/**
 * Oxford-comma join for the disabled-submit hint ("a, b, and c"). Local to
 * this module on purpose: the other guardian forms have at most two missing
 * inputs and spell their hints out directly.
 */
function joinPhrases(phrases: string[]): string {
  if (phrases.length <= 1) return phrases[0] ?? ''
  if (phrases.length === 2) return `${phrases[0]} and ${phrases[1]}`
  return `${phrases.slice(0, -1).join(', ')}, and ${phrases[phrases.length - 1]}`
}

/**
 * Guardian/admin "authored" story request (WS-B PR2): a pre-approved request
 * that skips the child free-text moderation queue (RequestsPage.tsx). A
 * guardian may optionally tie the request to one of their children, which
 * only prefills the age band (the backend derives the family server-side and
 * rejects a guardian-supplied family_id, so the guardian body never carries
 * one, not even as an explicit null). An admin must name the target family
 * (decision B3) and has no cross-family child picker in this PR, so the admin
 * body never carries profile_id.
 */
export function RequestStoryForm({ mode }: RequestStoryFormProps) {
  const api = useApi()
  const requestApi = useMemo(() => makeAuthoredRequestApi(api), [api])

  const [loadState, setLoadState] = useState<LoadState>({ kind: 'loading' })
  const [profiles, setProfiles] = useState<ProfileView[]>([])
  const [families, setFamilies] = useState<FamilyView[]>([])

  const [profileId, setProfileId] = useState(UNSELECTED)
  const [familyId, setFamilyId] = useState(UNSELECTED)
  const [band, setBand] = useState<AgeBand | ''>('')
  const [length, setLength] = useState<Length | ''>('')
  const [narrativeStyle, setNarrativeStyle] = useState<NarrativeStyle>('prose')
  const [requestText, setRequestText] = useState('')
  const [seriesTitle, setSeriesTitle] = useState('')

  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<SubmitResult>({ kind: 'idle' })

  // #ASSUME: external-resources: the child/family list backing this form can
  // fail to load (network, session expiry, server error). Degrade to a clear
  // error notice rather than a form that silently offers zero options.
  // #VERIFY: RequestStoryForm.test.tsx "shows a reload notice when the child
  // list fails to load" test covers the guardian-mode branch (mirrors
  // RequestsPage.tsx's own load effect); admin mode's symmetric
  // listFamilies failure is not separately covered and remains manual QA.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        if (mode === 'guardian') {
          const rows = await requestApi.listProfiles()
          if (!cancelled) setProfiles(rows)
        } else {
          const rows = await requestApi.listFamilies()
          if (!cancelled) setFamilies(rows)
        }
        if (!cancelled) setLoadState({ kind: 'ready' })
      } catch (err) {
        console.error('request-story-form load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) setLoadState({ kind: 'error' })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [mode, requestApi])

  // #ASSUME: data-integrity: selecting a child can move the band out of the
  // teen set the same way changeBand's manual selection can; a stale
  // gamebook choice must not resurface if the guardian later re-enters a
  // teen band via the band select. Same rule as changeBand below.
  // #VERIFY: RequestStoryForm.test.tsx "resets the story style to prose when
  // selecting a child moves the band out of the teen set" test.
  function selectChild(id: string) {
    setProfileId(id)
    if (id === UNSELECTED) return
    const profile = profiles.find((p) => p.id === id)
    if (profile) {
      setBand(profile.age_band)
      if (!TEEN_BANDS.includes(profile.age_band)) setNarrativeStyle('prose')
    }
  }

  // #ASSUME: data-integrity: ADR-011 restricts the gamebook narrative style to
  // teen bands (13-16, 16+), same rule as RequestsPage.tsx's confirm-strip.
  // Switching away from a teen band must not leave a stale gamebook selection
  // behind for a band that does not support it.
  // #VERIFY: RequestStoryForm.test.tsx style-select-teen-only test.
  function changeBand(value: string) {
    const next = value as AgeBand | ''
    setBand(next)
    if (!TEEN_BANDS.includes(next)) setNarrativeStyle('prose')
  }

  const isTeenBand = band !== '' && TEEN_BANDS.includes(band)
  const canSubmit =
    requestText.trim().length > 0 &&
    band !== '' &&
    length !== '' &&
    (mode === 'guardian' || familyId !== UNSELECTED) &&
    !submitting

  // Names what still blocks Send request while it is disabled for missing
  // inputs (null while submitting or once everything is filled). Derived from
  // the same conditions as canSubmit so the hint can never contradict the
  // button.
  const missingInputs: string[] = []
  if (mode === 'admin' && familyId === UNSELECTED) missingInputs.push('pick a family')
  if (requestText.trim().length === 0) missingInputs.push('describe the story')
  if (band === '') missingInputs.push('pick an age band')
  if (length === '') missingInputs.push('pick a story length')
  const submitHint =
    !submitting && missingInputs.length > 0
      ? `To send this request: ${joinPhrases(missingInputs)}.`
      : null

  // #CRITICAL: concurrency: the submit button is only re-enabled once the
  // in-flight request settles (canSubmit includes !submitting), so a
  // double-click cannot fire a second authored-request POST for the same
  // draft the way RequestsPage.tsx guards its per-row approve/decline.
  // #VERIFY: RequestStoryForm.test.tsx "double-clicking Send request results
  // in exactly one POST call" test.
  async function submit() {
    // canSubmit is a `const` alias of a chain that includes `band !== ''`
    // and `length !== ''`; TypeScript's aliased-condition narrowing carries
    // that into this branch, so band/length are AgeBand/Length (not '')
    // below without a separate emptiness re-check.
    if (!canSubmit) return
    setSubmitting(true)
    setResult({ kind: 'idle' })
    try {
      const body: StoryRequestAuthoredCreateBody =
        mode === 'guardian'
          ? {
              request_text: requestText.trim(),
              age_band: band,
              length,
              narrative_style: isTeenBand ? narrativeStyle : 'prose',
              ...(profileId !== UNSELECTED ? { profile_id: profileId } : {}),
              ...(seriesTitle.trim().length > 0 ? { series_title: seriesTitle.trim() } : {}),
            }
          : {
              request_text: requestText.trim(),
              age_band: band,
              length,
              narrative_style: isTeenBand ? narrativeStyle : 'prose',
              family_id: familyId,
              ...(seriesTitle.trim().length > 0 ? { series_title: seriesTitle.trim() } : {}),
            }
      const created = await requestApi.createAuthored(body)
      if (created.status === 'blocked') {
        setResult({ kind: 'blocked' })
      } else {
        setResult({ kind: 'success' })
        setRequestText('')
        setProfileId(UNSELECTED)
        setFamilyId(UNSELECTED)
        setBand('')
        setLength('')
        setNarrativeStyle('prose')
        setSeriesTitle('')
      }
    } catch (err) {
      // #ASSUME: external-resources: the create call can fail (network,
      // session expiry, server error). Log the message, not the axios error
      // object (its config.headers carries the caller's bearer token).
      // #VERIFY: RequestStoryForm.test.tsx "shows a transient error alert and
      // re-enables submit when the create call rejects" test; classifyApiError
      // itself is unit-tested in classifyApiError.test.ts.
      console.error('authored story request failed:', err instanceof Error ? err.message : err)
      setResult({
        kind: 'error',
        message: classifyApiError(err, {
          transient: 'We could not send this request. Please try again.',
          server: 'We could not send this request. Please try again.',
        }).message,
      })
    } finally {
      setSubmitting(false)
    }
  }

  if (loadState.kind === 'loading') {
    return (
      <div role="status" aria-live="polite">
        Loading request form…
      </div>
    )
  }
  if (loadState.kind === 'error') {
    return (
      <p role="alert" className="console__error cyo-text-error">
        We could not load {mode === 'guardian' ? 'your children' : 'families'}. Please reload.
      </p>
    )
  }

  return (
    <form
      className="request-form"
      onSubmit={(e) => {
        e.preventDefault()
        if (canSubmit) void submit()
      }}
    >
      <h3 className="request-form__heading">Request a story</h3>
      {result.kind === 'success' ? (
        <p role="status" className="request-form__notice">
          Request approved and sent for authoring.
        </p>
      ) : null}
      {result.kind === 'blocked' ? (
        <p role="alert" className="request-form__notice request-form__notice--blocked">
          This idea did not pass our content check, so it was not sent for authoring.
        </p>
      ) : null}
      {result.kind === 'error' ? (
        <p role="alert" className="request-form__error cyo-text-error">
          {result.message}
        </p>
      ) : null}

      {mode === 'guardian' ? (
        <label className="request-form__field cyo-field" htmlFor="request-form-child">
          Child (optional)
          <select
            id="request-form-child"
            className="cyo-field__control"
            value={profileId}
            onChange={(e) => selectChild(e.target.value)}
          >
            <option value={UNSELECTED}>No specific child</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.display_name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <label className="request-form__field cyo-field" htmlFor="request-form-family">
          Family
          <select
            id="request-form-family"
            required
            className="cyo-field__control"
            value={familyId}
            onChange={(e) => setFamilyId(e.target.value)}
          >
            <option value={UNSELECTED}>Choose a family…</option>
            {families.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className="request-form__field cyo-field" htmlFor="request-form-text">
        What should the story be about?
        <textarea
          id="request-form-text"
          className="cyo-field__control"
          value={requestText}
          onChange={(e) => setRequestText(e.target.value)}
          rows={4}
          maxLength={REQUEST_TEXT_MAX}
          required
        />
      </label>
      {/* Sibling of the label, not a child: the counter must not leak into
          the textarea's accessible name. */}
      <p
        className="request-form__counter cyo-text-muted"
        aria-live={requestText.length >= REQUEST_TEXT_WARN_AT ? 'polite' : 'off'}
      >
        {requestText.length} / {REQUEST_TEXT_MAX}
      </p>

      <label className="request-form__field cyo-field" htmlFor="request-form-band">
        Age band
        <select
          id="request-form-band"
          required
          className="cyo-field__control"
          value={band}
          onChange={(e) => changeBand(e.target.value)}
        >
          <option value="">Choose…</option>
          {AGE_BANDS.map((b) => (
            <option key={b} value={b}>
              {ageBandLabel(b)}
            </option>
          ))}
        </select>
      </label>

      <label className="request-form__field cyo-field" htmlFor="request-form-length">
        Story length
        <select
          id="request-form-length"
          required
          className="cyo-field__control"
          value={length}
          onChange={(e) => setLength(e.target.value as Length | '')}
        >
          <option value="">Choose…</option>
          {LENGTHS.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
      </label>

      {isTeenBand ? (
        <label className="request-form__field cyo-field" htmlFor="request-form-style">
          Story style
          <select
            id="request-form-style"
            className="cyo-field__control"
            value={narrativeStyle}
            onChange={(e) => setNarrativeStyle(e.target.value as NarrativeStyle)}
          >
            <option value="prose">prose</option>
            <option value="gamebook">gamebook</option>
          </select>
        </label>
      ) : null}

      <label className="request-form__field cyo-field" htmlFor="request-form-series-title">
        Series title (optional)
        <input
          id="request-form-series-title"
          type="text"
          className="cyo-field__control"
          value={seriesTitle}
          maxLength={120}
          onChange={(e) => setSeriesTitle(e.target.value)}
        />
      </label>

      {submitHint !== null ? (
        <p className="request-form__hint cyo-text-muted">{submitHint}</p>
      ) : null}
      <Button type="submit" disabled={!canSubmit}>
        {submitting ? 'Sending…' : 'Send request'}
      </Button>
    </form>
  )
}
