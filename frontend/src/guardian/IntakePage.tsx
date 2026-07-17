import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@ds/components/Button'
import { Chip } from '@ds/components/Chip'
import { EmptyState } from '@ds/components/EmptyState'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { AssignChildrenDialog } from './AssignChildrenDialog'
import { BudgetBanner } from './BudgetBanner'
import { BUDGET_EXCEEDED_MESSAGE, isBudgetExceededError } from './budgetApi'
import {
  TONES,
  buildBrief,
  formatRelativeTime,
  makeIntakeApi,
  statusPill,
  type GenerationJobSummary,
  type StatusPill,
  type ToneValue,
} from './intakeApi'
import { STORY_REQUESTS_CHANGED_EVENT } from './storyRequestQueueApi'

// Poll interval while any request is still generating; matches the ApiStatus
// polling shape (setInterval + clearInterval cleanup), tuned to ~8s here.
const POLL_MS = 8000

// Client cap on the premise textarea; mirrored by the "N / 2000" counter.
const PREMISE_MAX = 2000

// The counter is always visible but only becomes a polite live region near
// the cap (>=90%), so screen readers hear the shrinking budget when it
// matters instead of on every keystroke.
const PREMISE_WARN_AT = PREMISE_MAX * 0.9

// Transient (network / 5xx) copy per surface. classifyApiError swaps in a
// distinct message for a 401/403 so a permanent auth/role failure no longer
// reads as a retryable blip (naive-UX report F1); these are the fallbacks.
const LOAD_ERROR_TRANSIENT = 'We could not load your requests and profiles.'
const SUBMIT_ERROR_TRANSIENT = 'We could not send this request. Please try again.'

const SUBMIT_SUCCESS_NOTICE = 'Request sent! Your story is being made; watch My Requests below.'

// A Failed row leads with this friendly cause; the short technical error
// field is kept visible below it (demoted) for debugging.
const FAILED_FRIENDLY_CAUSE = 'This story could not be made.'

// What-to-expect sublines for the non-terminal pill states, so a busy parent
// is not left waiting blind on generation or review.
const EXPECTATION_COPY: Partial<Record<StatusPill, string>> = {
  Generating: 'Usually ready in a few minutes.',
  'Waiting for review': 'A grown-up reviewer checks every story before kids can read it.',
}

function isActive(job: GenerationJobSummary): boolean {
  return job.status === 'queued' || job.status === 'running'
}

function assignedNotice(count: number): string {
  return `Assigned to ${count} ${count === 1 ? 'child' : 'children'}.`
}

/**
 * Guardian concept intake + "My Requests" status list (C4a-5, wireframe 4.5).
 *
 * "Who's it for?" child chips constrain the age band / reading level; a premise
 * textarea and a tone chip row complete the request. Submitting posts the
 * concept then immediately enqueues generation and confirms inline. The
 * request list polls while anything is generating and shows, per row, a
 * status pill, the request's age, and a what-to-expect subline; Failed rows
 * offer a Try again prefill and Approved rows open the assign dialog (C4a-6).
 */
export function IntakePage() {
  const api = useApi()
  const intakeApi = useMemo(() => makeIntakeApi(api), [api])
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])

  const [profiles, setProfiles] = useState<ProfileView[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [premise, setPremise] = useState('')
  const [tone, setTone] = useState<ToneValue>('gentle')
  const [jobs, setJobs] = useState<GenerationJobSummary[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Explicit post-submit confirmation near the form (RequestStoryForm's
  // success-notice pattern); cleared on the next submit attempt or Try again.
  const [submitSuccess, setSubmitSuccess] = useState(false)
  // Inline confirmation after the assign dialog saves ("Assigned to N
  // children."); cleared when the dialog is reopened.
  const [assignNotice, setAssignNotice] = useState<string | null>(null)
  // "Now" for the "Requested N minutes ago" lines, stamped whenever the job
  // list is (re)fetched. Each 8s poll tick refreshes it, so active lists stay
  // current without a dedicated clock timer (and render stays pure; the
  // react-hooks/purity rule forbids Date.now() during render). Rows only
  // exist after a fetch has stamped it, so the 0 initial value never shows.
  const [jobsSyncedAt, setJobsSyncedAt] = useState(0)
  const premiseRef = useRef<HTMLTextAreaElement>(null)
  // The storybook id whose "Assign to children" dialog is open, or null when
  // closed. Approved request rows carry a non-null storybook_id (see statusPill).
  const [assigning, setAssigning] = useState<string | null>(null)
  // Distinct from `error` (a submit failure): a read failure on the initial
  // load or a poll. Surfacing it prevents an empty/stale list from masquerading
  // as a genuine "no requests" state after a session expiry or network drop.
  const [loadError, setLoadError] = useState<string | null>(null)

  const refreshJobs = useCallback(async () => {
    const rows = await intakeApi.listJobs()
    setJobs(rows)
    setJobsSyncedAt(Date.now())
    setLoadError(null)
  }, [intakeApi])

  // #ASSUME: external-resources: profiles/jobs fetch can reject (session expiry,
  // network). A swallowed rejection would render a false "no profiles / no
  // requests" state, so failures set loadError for a visible retry affordance.
  // #VERIFY: IntakePage.test.tsx initial-load-failure test.
  const loadData = useCallback(async () => {
    try {
      const [rows, jobRows] = await Promise.all([profilesApi.list(), intakeApi.listJobs()])
      setProfiles(rows)
      setJobs(jobRows)
      setJobsSyncedAt(Date.now())
      setLoadError(null)
    } catch (err) {
      console.error('intake load failed', err)
      setLoadError(
        classifyApiError(err, { transient: LOAD_ERROR_TRANSIENT, server: LOAD_ERROR_TRANSIENT })
          .message
      )
    }
  }, [profilesApi, intakeApi])

  useEffect(() => {
    async function run() {
      await loadData()
    }
    void run()
  }, [loadData])

  // #ASSUME: timing-dependencies: poll only while a job is active; clear the
  // interval on unmount and whenever nothing is generating so the page does not
  // hold a live timer forever. A failing poll sets loadError (not swallowed to
  // console) so a job cannot appear frozen on "Generating" without any signal.
  // #VERIFY: IntakePage.test.tsx polling transition test (fake timers).
  useEffect(() => {
    if (!jobs.some(isActive)) return undefined
    const id = setInterval(() => {
      void refreshJobs().catch((err) => {
        console.error('poll failed', err)
        setLoadError(
          classifyApiError(err, { transient: LOAD_ERROR_TRANSIENT, server: LOAD_ERROR_TRANSIENT })
            .message
        )
      })
    }, POLL_MS)
    return () => clearInterval(id)
  }, [jobs, refreshJobs])

  const selected = profiles.find((p) => p.id === selectedId) ?? null
  // #ASSUME: data-integrity: banned_themes is always present on a ProfileView
  // fetched from the current API, but a stale/mocked profile object may omit
  // it; the fallback keeps this read-only display (and the buildBrief call
  // above) from throwing on such a shape.
  const selectedBannedThemes = selected?.banned_themes ?? []
  const canSubmit = selected !== null && premise.trim().length > 0 && !saving

  // Names what still blocks Request Story while it is disabled for missing
  // inputs. Derived from the same conditions as canSubmit; suppressed while
  // saving and for a childless family (the chips row already links to
  // profile creation, so "pick a child" would point at nothing).
  const premiseMissing = premise.trim().length === 0
  let submitHint: string | null = null
  if (!saving && profiles.length > 0) {
    if (selected === null && premiseMissing) {
      submitHint = 'Pick a child and write a premise to continue.'
    } else if (selected === null) {
      submitHint = 'Pick a child to continue.'
    } else if (premiseMissing) {
      submitHint = 'Write a premise to continue.'
    }
  }

  async function submit() {
    if (selected === null) return
    setSaving(true)
    setError(null)
    setSubmitSuccess(false)
    // #CRITICAL: data-integrity: createConcept + generate create durable rows
    // (and downstream generation cost). The success/failure of the request is
    // decided by these two POSTs ALONE. The trailing job-list refresh is a
    // non-critical read; if it were inside this try, a transient refresh
    // failure would flip `error` on an already-succeeded request and a retry
    // would create a duplicate concept + generation job (no idempotency key).
    // #VERIFY: IntakePage.test.tsx submit-then-refresh-fails test.
    let submitted = false
    try {
      const brief = buildBrief({
        premise: premise.trim(),
        tone,
        ageBand: selected.age_band,
        readingLevelCap: selected.reading_level_cap,
        // G2: fold the selected child's guardian-set theme exclusions into
        // the brief instead of the previously hardcoded empty list.
        bannedThemes: selectedBannedThemes,
      })
      const { concept_id } = await intakeApi.createConcept(brief)
      await intakeApi.generate(concept_id)
      submitted = true
    } catch (err) {
      console.error('story request failed', err)
      // ADR-015 G7: a family-budget-exhausted 409 gets its own friendly
      // copy (with a hint to wait for next month) instead of the generic
      // transient/server fallback. #ASSUME: external-resources: neither
      // /v1/concepts nor /v1/concepts/{id}/generate enforces the family
      // quota at this writing (only the story-requests approve/authored-
      // create endpoints do; see budgetApi.ts's isBudgetExceededError doc),
      // so this branch is defensive/forward-compatible rather than
      // reachable today -- it costs nothing and stays correct if/when the
      // guardian-authored intake path gains the same gate.
      // #VERIFY: IntakePage.test.tsx "budget-exhausted submit" test.
      setError(
        isBudgetExceededError(err)
          ? BUDGET_EXCEEDED_MESSAGE
          : classifyApiError(err, {
              transient: SUBMIT_ERROR_TRANSIENT,
              server: SUBMIT_ERROR_TRANSIENT,
            }).message
      )
    } finally {
      setSaving(false)
    }
    // Only after the durable POSTs succeed: clear the input, confirm inline,
    // and refresh the list. A failed refresh surfaces as loadError, never as
    // a submit failure.
    if (submitted) {
      setPremise('')
      setSubmitSuccess(true)
      // Refreshes BudgetBanner (this page and RequestsPage's, if mounted)
      // via the shared window event; also a no-op nudge to the guardian
      // shell's pending-count badge, which StoryRequestQueue's approve/
      // decline already use this same event for.
      window.dispatchEvent(new Event(STORY_REQUESTS_CHANGED_EVENT))
      await refreshJobs().catch((err) => {
        console.error('post-submit refresh failed', err)
        setLoadError(
          classifyApiError(err, { transient: LOAD_ERROR_TRANSIENT, server: LOAD_ERROR_TRANSIENT })
            .message
        )
      })
    }
  }

  // "Try again" on a Failed row prefills the form from that job's summary and
  // hands control back to the guardian; it must NEVER auto-submit (a re-run
  // creates a new concept + generation job with real cost, so the parent
  // confirms). The list payload carries only a premise snippet (the backend
  // truncates to 120 chars, api/generation.py) and the age band; tone and the
  // originally selected child are not in the payload, so tone keeps its
  // current selection and the child chip is set only when the band matches
  // exactly one profile (anything else would be a guess).
  // #ASSUME: data-integrity: premise_snippet can be a truncated prefix of the
  // original premise. #VERIFY: the guardian reviews the prefilled form before
  // submitting; IntakePage.test.tsx asserts Try again fires no POST.
  function tryAgain(job: GenerationJobSummary) {
    setSubmitSuccess(false)
    if (job.premise_snippet) setPremise(job.premise_snippet)
    const bandMatches = profiles.filter((p) => p.age_band === job.age_band)
    if (bandMatches.length === 1) setSelectedId(bandMatches[0].id)
    // Optional call: jsdom (Vitest) does not implement scrollIntoView.
    premiseRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    premiseRef.current?.focus()
  }

  return (
    <section className="intake">
      <h1>Request a story</h1>
      {loadError ? (
        <div role="alert" className="intake-form__error cyo-text-error">
          {loadError}{' '}
          <button type="button" className="intake-retry" onClick={() => void loadData()}>
            Retry
          </button>
        </div>
      ) : null}
      <form
        className="intake-form"
        onSubmit={(e) => {
          e.preventDefault()
          if (canSubmit) void submit()
        }}
      >
        {submitSuccess ? (
          <p role="status" className="intake-form__notice">
            {SUBMIT_SUCCESS_NOTICE}
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="intake-form__error cyo-text-error">
            {error}
          </p>
        ) : null}

        <fieldset className="intake-form__chips">
          <legend>Who&apos;s it for?</legend>
          {profiles.length === 0 ? (
            <Link to="/guardian/profiles" className="intake-form__hint cyo-text-muted">
              Add a child profile first.
            </Link>
          ) : (
            profiles.map((p) => (
              <Chip
                key={p.id}
                data-testid={`child-chip-${p.id}`}
                on={selectedId === p.id}
                onClick={() => setSelectedId(p.id)}
              >
                {p.display_name}
              </Chip>
            ))
          )}
        </fieldset>

        {/* G2: read-only proof that the per-child content controls (set on
            the Profiles page) actually apply to this request; content_nogo
            is derived from these themes in buildBrief above. */}
        {selectedBannedThemes.length > 0 ? (
          <p className="intake-form__hint cyo-text-muted" data-testid="intake-excluded-themes">
            Excluded for this child: {selectedBannedThemes.join(', ')}
          </p>
        ) : null}

        <label className="intake-form__field cyo-field">
          What&apos;s it about?
          <textarea
            ref={premiseRef}
            className="cyo-field__control"
            value={premise}
            onChange={(e) => setPremise(e.target.value)}
            maxLength={PREMISE_MAX}
            rows={4}
            required
          />
        </label>
        {/* Sibling of the label, not a child: the counter must not leak into
            the textarea's accessible name. */}
        <p
          className="intake-form__counter cyo-text-muted"
          aria-live={premise.length >= PREMISE_WARN_AT ? 'polite' : 'off'}
        >
          {premise.length} / {PREMISE_MAX}
        </p>

        <fieldset className="intake-form__chips">
          <legend>Tone</legend>
          {TONES.map((t) => (
            <Chip key={t.value} on={tone === t.value} onClick={() => setTone(t.value)}>
              {t.label}
            </Chip>
          ))}
        </fieldset>

        {submitHint !== null ? (
          <p className="intake-form__hint cyo-text-muted">{submitHint}</p>
        ) : null}
        {/* G13 (interim) balance: "N of M stories left this month", near
            the submit button per the deliverable. */}
        <BudgetBanner />
        <Button type="submit" disabled={!canSubmit}>
          {saving ? 'Requesting…' : 'Request Story'}
        </Button>
      </form>

      <h2>My Requests</h2>
      {assignNotice ? (
        <p role="status" className="intake-assign-notice">
          {assignNotice}
        </p>
      ) : null}
      {jobs.length === 0 ? (
        <EmptyState title="No requests yet" description="Request a story above to see it here." />
      ) : (
        <ul className="intake-requests">
          {jobs.map((job) => {
            const pill = statusPill(job)
            const requestedAgo = formatRelativeTime(job.created_at, jobsSyncedAt)
            const expectation = EXPECTATION_COPY[pill]
            return (
              <li
                key={job.id}
                data-testid={`request-${job.id}`}
                className="intake-request cyo-card"
              >
                <div className="intake-request__body">
                  <span className="intake-request__title">
                    {job.title ?? (job.premise_snippet || 'Untitled request')}
                  </span>
                  {requestedAgo !== null ? (
                    <span
                      className="intake-request__age cyo-text-muted"
                      title={new Date(job.created_at).toLocaleString()}
                    >
                      Requested {requestedAgo}
                    </span>
                  ) : null}
                  {expectation !== undefined ? (
                    <span className="intake-request__hint cyo-text-muted">{expectation}</span>
                  ) : null}
                  {/* Any Failed row (pipeline failure OR gate-failed
                      needs_review) leads with a friendly cause; the short
                      error field stays visible but demoted for debugging;
                      the raw report is never fetched or rendered. */}
                  {pill === 'Failed' ? (
                    <>
                      <span className="intake-request__error cyo-text-error">
                        {FAILED_FRIENDLY_CAUSE}
                      </span>
                      {job.error ? (
                        <span className="intake-request__error-detail cyo-text-muted">
                          {job.error}
                        </span>
                      ) : null}
                    </>
                  ) : null}
                </div>
                <span
                  data-testid={`request-status-${job.id}`}
                  data-status={pill}
                  className="intake-pill"
                >
                  {pill}
                </span>
                {/* Only Approved rows carry a published storybook to assign.
                    Guard on storybook_id so the button never opens the dialog
                    with a null id even if the pill mapping ever changes. */}
                {pill === 'Approved' && job.storybook_id !== null ? (
                  <button
                    type="button"
                    className="intake-request__assign"
                    onClick={() => {
                      setAssignNotice(null)
                      setAssigning(job.storybook_id)
                    }}
                  >
                    Assign more
                  </button>
                ) : null}
                {pill === 'Failed' ? (
                  <button
                    type="button"
                    className="intake-request__retry"
                    onClick={() => tryAgain(job)}
                  >
                    Try again
                  </button>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
      {assigning ? (
        <AssignChildrenDialog
          key={assigning}
          storybookId={assigning}
          onClose={() => setAssigning(null)}
          // onAssigned receives the storybook's full post-save assignment
          // list (assignApi.add returns the server's complete profile_ids),
          // so the count reads "assigned to N total". Nothing else on this
          // page renders assignments, so the notice is the whole refresh.
          onAssigned={(profileIds) => setAssignNotice(assignedNotice(profileIds.length))}
        />
      ) : null}
    </section>
  )
}
