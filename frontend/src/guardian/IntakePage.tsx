import { useCallback, useEffect, useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { useApi } from '../hooks/useApi'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { AssignChildrenDialog } from './AssignChildrenDialog'
import {
  TONES,
  buildBrief,
  makeIntakeApi,
  statusPill,
  type GenerationJobSummary,
  type ToneValue,
} from './intakeApi'

// Poll interval while any request is still generating; matches the ApiStatus
// polling shape (setInterval + clearInterval cleanup), tuned to ~8s here.
const POLL_MS = 8000

function isActive(job: GenerationJobSummary): boolean {
  return job.status === 'queued' || job.status === 'running'
}

/**
 * Guardian concept intake + "My Requests" status list (C4a-5, wireframe 4.5).
 *
 * "Who's it for?" child chips constrain the age band / reading level; a premise
 * textarea and a tone chip row complete the request. Submitting posts the
 * concept then immediately enqueues generation. The request list polls while
 * anything is generating and shows a status pill per row. Assignment ("Assign
 * more") is C4a-6 and is intentionally not built here.
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
  const [error, setError] = useState(false)
  // The storybook id whose "Assign to children" dialog is open, or null when
  // closed. Approved request rows carry a non-null storybook_id (see statusPill).
  const [assigning, setAssigning] = useState<string | null>(null)
  // Distinct from `error` (a submit failure): a read failure on the initial
  // load or a poll. Surfacing it prevents an empty/stale list from masquerading
  // as a genuine "no requests" state after a session expiry or network drop.
  const [loadError, setLoadError] = useState(false)

  const refreshJobs = useCallback(async () => {
    const rows = await intakeApi.listJobs()
    setJobs(rows)
    setLoadError(false)
  }, [intakeApi])

  // #ASSUME: external-resources: profiles/jobs fetch can reject (session expiry,
  // network). A swallowed rejection would render a false "no profiles / no
  // requests" state, so failures set loadError for a visible retry affordance.
  // #VERIFY: IntakePage.test.tsx initial-load-failure test.
  const loadData = useCallback(async () => {
    try {
      const [rows, jobRows] = await Promise.all([
        profilesApi.list(),
        intakeApi.listJobs(),
      ])
      setProfiles(rows)
      setJobs(jobRows)
      setLoadError(false)
    } catch (err) {
      console.error('intake load failed', err)
      setLoadError(true)
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
        setLoadError(true)
      })
    }, POLL_MS)
    return () => clearInterval(id)
  }, [jobs, refreshJobs])

  const selected = profiles.find((p) => p.id === selectedId) ?? null
  const canSubmit = selected !== null && premise.trim().length > 0 && !saving

  async function submit() {
    if (selected === null) return
    setSaving(true)
    setError(false)
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
      })
      const { concept_id } = await intakeApi.createConcept(brief)
      await intakeApi.generate(concept_id)
      submitted = true
    } catch (err) {
      console.error('story request failed', err)
      setError(true)
    } finally {
      setSaving(false)
    }
    // Only after the durable POSTs succeed: clear the input and refresh the
    // list. A failed refresh surfaces as loadError, never as a submit failure.
    if (submitted) {
      setPremise('')
      await refreshJobs().catch((err) => {
        console.error('post-submit refresh failed', err)
        setLoadError(true)
      })
    }
  }

  return (
    <section className="intake">
      <h1>Request a story</h1>
      {loadError ? (
        <div role="alert" className="intake-form__error">
          We could not load your requests.{' '}
          <button
            type="button"
            className="intake-retry"
            onClick={() => void loadData()}
          >
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
        {error ? (
          <p role="alert" className="intake-form__error">
            We could not send this request. Please try again.
          </p>
        ) : null}

        <fieldset className="intake-form__chips">
          <legend>Who&apos;s it for?</legend>
          {profiles.length === 0 ? (
            <p className="intake-form__hint">Add a child profile first.</p>
          ) : (
            profiles.map((p) => (
              <button
                key={p.id}
                type="button"
                data-testid={`child-chip-${p.id}`}
                className={`intake-chip${selectedId === p.id ? ' intake-chip--on' : ''}`}
                aria-pressed={selectedId === p.id}
                onClick={() => setSelectedId(p.id)}
              >
                {p.display_name}
              </button>
            ))
          )}
        </fieldset>

        <label className="intake-form__field">
          What&apos;s it about?
          <textarea
            value={premise}
            onChange={(e) => setPremise(e.target.value)}
            maxLength={2000}
            rows={4}
            required
          />
        </label>

        <fieldset className="intake-form__chips">
          <legend>Tone</legend>
          {TONES.map((t) => (
            <button
              key={t.value}
              type="button"
              className={`intake-chip${tone === t.value ? ' intake-chip--on' : ''}`}
              aria-pressed={tone === t.value}
              onClick={() => setTone(t.value)}
            >
              {t.label}
            </button>
          ))}
        </fieldset>

        <Button type="submit" disabled={!canSubmit}>
          {saving ? 'Requesting…' : 'Request Story'}
        </Button>
      </form>

      <h2>My Requests</h2>
      {jobs.length === 0 ? (
        <EmptyState
          title="No requests yet"
          description="Request a story above to see it here."
        />
      ) : (
        <ul className="intake-requests">
          {jobs.map((job) => {
            const pill = statusPill(job)
            return (
              <li
                key={job.id}
                data-testid={`request-${job.id}`}
                className="intake-request"
              >
                <div className="intake-request__body">
                  <span className="intake-request__title">
                    {job.title ?? (job.premise_snippet || 'Untitled request')}
                  </span>
                  {/* Any Failed row (pipeline failure OR gate-failed
                      needs_review) shows the short error field if present;
                      the raw report is never fetched or rendered. */}
                  {pill === 'Failed' && job.error ? (
                    <span className="intake-request__error">{job.error}</span>
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
                    onClick={() => setAssigning(job.storybook_id)}
                  >
                    Assign more
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
        />
      ) : null}
    </section>
  )
}
