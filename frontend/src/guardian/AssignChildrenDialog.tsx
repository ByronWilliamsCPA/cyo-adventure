import { useEffect, useMemo, useRef, useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { ErrorBanner } from '@ds/components/ErrorBanner'
import { LoadingStatus } from '@ds/components/LoadingStatus'
import { makeFetchStory } from '../api/readerApi'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { AvatarCircle } from '../profiles/AvatarCircle'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { makeAssignApi, type ContentSummary } from './assignApi'
import { FlagBadge } from './FlagBadge'
import { verdictTone } from './verdictTone'
import { StoryStructureSummary } from './StoryStructureSummary'
import './guardian.css'

interface AssignChildrenDialogProps {
  storybookId: string
  onClose: () => void
  onAssigned?: (profileIds: string[]) => void
  /**
   * Fired after a successful per-child unassign (G8 kill switch), with the
   * book's full remaining assignment list. Distinct from onAssigned so callers
   * can word "removed" vs "assigned" honestly; both carry the authoritative
   * post-change list, so a caller that only tracks the count can wire both to
   * the same handler.
   */
  onUnassigned?: (profileIds: string[]) => void
}

/**
 * Redacted content review tags for the guardian assign flow: the screened
 * state, a flagged-count pill, and story-level findings only. Reuses FlagBadge
 * and verdictTone; per-node passages are intentionally never fetched here.
 */
function ContentSummarySection({ summary }: { summary: ContentSummary }) {
  if (!summary.screened) {
    return (
      <div className="assign__content-summary">
        <h3>Content review</h3>
        <FlagBadge tone="unscreened" />
      </div>
    )
  }
  return (
    <div className="assign__content-summary">
      <h3>Content review</h3>
      {summary.flagged_count > 0 ? (
        <FlagBadge tone="flag" label={`${summary.flagged_count} flagged`} />
      ) : (
        <FlagBadge tone="clean" />
      )}
      {summary.findings.length > 0 ? (
        <ul className="assign__findings">
          {summary.findings.map((finding) => (
            // Content-derived key: the merged concern list is distinct by
            // (concern-or-category, severity, verdict, message), matching
            // the backend's own merge key (review_surface.py::
            // _guardian_group_key), so this stays stable if the list is ever
            // reordered or spliced, unlike an array index.
            <li
              key={`${finding.concern ?? finding.category}-${finding.severity ?? ''}-${finding.verdict}-${finding.message}`}
              className="review-finding"
            >
              <FlagBadge tone={verdictTone(finding.verdict)} />
              {/* Stage B3 (design doc 2.6): severity pill when the merge
                  stage assigned one; absent on a pre-Stage-B report. */}
              {finding.severity ? (
                <span
                  className={`review-finding__severity review-finding__severity--${finding.severity}`}
                >
                  {finding.severity}
                </span>
              ) : null}
              <span className="review-finding__category">
                {finding.concern ?? finding.category}
              </span>
              <span className="review-finding__message">{finding.message}</span>
              {/* node_count is a COUNT only, never a node id or passage: the
                  guardian must never see per-node detail (invariant 4). */}
              {finding.node_count !== undefined && finding.node_count > 1 ? (
                <span className="review-finding__node-count cyo-text-muted">
                  {finding.node_count} passages
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {/* Stage B3 follow-up (design doc 2.7 option (a)): a story-level,
          node-id-free RL-13/PL-19 aggregate. Plain text, one line per note;
          no severity pill or FlagBadge (deliberately lighter weight than the
          findings list above, since these are advisory validator counts, not
          moderation findings). */}
      {summary.validator_notes && summary.validator_notes.length > 0 ? (
        <ul className="assign__validator-notes cyo-text-muted">
          {summary.validator_notes.map((note) => (
            <li key={`${note.rule_id}-${note.severity}`}>
              {note.rule_id} {note.severity} x{note.count}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

/**
 * G5 skim aid, compact variant: endings, read time, and themes for the book
 * being assigned, so a guardian sees what it is without opening every
 * passage. Additive to ContentSummarySection above (which already owns the
 * flagged-count pill and itemized findings); this block renders once the
 * published version's blob has loaded, and is silently omitted while it is
 * still loading or unavailable -- it is a supplementary skim aid, not a
 * blocker for assignment.
 *
 * #ASSUME: external resources: the blob fetch (GET
 * /v1/storybooks/{id}/versions/{version}) is a second, best-effort request
 * beyond the content-summary call; a failure here must never block the
 * assign flow, so it degrades to "nothing rendered" rather than an error.
 * #VERIFY: AssignChildrenDialog.test.tsx asserts a failed/slow blob fetch
 * still leaves the dialog usable.
 */
function StoryOverviewSection({
  summary,
  structureBlob,
}: {
  summary: ContentSummary
  structureBlob: Record<string, unknown> | null
}) {
  if (structureBlob === null) return null
  return (
    <div className="assign__story-overview">
      <h3>Story overview</h3>
      <StoryStructureSummary
        compact
        blob={structureBlob}
        screened={summary.screened}
        flaggedCount={summary.flagged_count}
      />
    </div>
  )
}

/**
 * Guardian "Assign more" dialog (wireframe 4.5): a multi-select checklist of
 * family child profiles. Already-assigned children are shown checked and
 * disabled; Assign posts only the newly selected ids (add-only, idempotent).
 *
 * Each already-assigned row also carries a per-child "Remove" control (G8
 * kill switch): a two-step inline confirm that revokes just that child's
 * access immediately, separate from the additive Assign action. Removal only
 * revokes access; the child's reading progress is preserved server-side and
 * resurrects if the book is reassigned.
 */
export function AssignChildrenDialog({
  storybookId,
  onClose,
  onAssigned,
  onUnassigned,
}: AssignChildrenDialogProps) {
  const api = useApi()
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const assignApi = useMemo(() => makeAssignApi(api), [api])
  const fetchStory = useMemo(() => makeFetchStory(api), [api])
  const [profiles, setProfiles] = useState<ProfileView[] | null>(null)
  const [assigned, setAssigned] = useState<Set<string>>(new Set())
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  // Per-child unassign (G8): confirmId is the row awaiting its second click,
  // removingId is the row whose DELETE is in flight. Only one row can be in
  // either state at a time.
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [removingId, setRemovingId] = useState<string | null>(null)
  const [removeError, setRemoveError] = useState<string | null>(null)
  const [summary, setSummary] = useState<ContentSummary | null>(null)
  const [summaryError, setSummaryError] = useState(false)
  const [structureBlob, setStructureBlob] = useState<Record<string, unknown> | null>(null)
  // G8 a11y: the row list is the query root for the focus handoff below. A ref
  // on the container (rather than one ref per button) keeps the lookup keyed by
  // profile id, which is the only stable identity a row has across the
  // trigger <-> confirm-cluster swap that unmounts one and mounts the other.
  const listRef = useRef<HTMLUListElement>(null)
  const prevConfirmIdRef = useRef<string | null>(null)

  // #CRITICAL: security: this is a destructive flow, so focus must never be
  // silently dropped mid-confirm. Clicking Remove unmounts the trigger and
  // clicking Keep/Remove access unmounts the confirm cluster; React returns
  // focus to document.body both times, ejecting a keyboard or screen-reader
  // user out of the dialog without any announcement. Entering confirm moves
  // focus to the destructive button (whose aria-label names the child);
  // leaving it returns focus to that row's Remove trigger, or to the dialog
  // itself when the row no longer offers one (a successful removal).
  // #VERIFY: AssignChildrenDialog.test.tsx "focus management" describe block
  // covers all four transitions (enter, Keep, success, failure).
  useEffect(() => {
    const previous = prevConfirmIdRef.current
    prevConfirmIdRef.current = confirmId
    // First render (both null) and no-op re-renders must not steal the focus
    // Dialog itself placed on mount.
    if (previous === confirmId) return
    const list = listRef.current
    if (list === null) return
    const focusable = (selector: string): HTMLElement | null => {
      const el = list.querySelector<HTMLElement>(selector)
      return el !== null && !(el as HTMLButtonElement).disabled ? el : null
    }
    if (confirmId !== null) {
      focusable(`[data-confirm-remove="${confirmId}"]`)?.focus()
      return
    }
    const trigger = previous === null ? null : focusable(`[data-remove-trigger="${previous}"]`)
    if (trigger !== null) {
      trigger.focus()
      return
    }
    // The row lost its Remove trigger (the child was actually unassigned), so
    // there is nothing row-level to return to; park focus on the dialog
    // container, which is tabIndex=-1 and inside the focus trap.
    list.closest<HTMLElement>('[role="dialog"]')?.focus()
  }, [confirmId])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [rows, assignedIds] = await Promise.all([
          profilesApi.list(),
          assignApi.get(storybookId),
        ])
        if (!cancelled) {
          setProfiles(rows)
          setAssigned(new Set(assignedIds))
        }
      } catch (err) {
        console.error('assign dialog load failed', err)
        if (!cancelled) {
          setLoadError(
            classifyApiError(err, {
              transient: "We could not load your family's profiles and assignments.",
              server: "We could not load your family's profiles and assignments.",
            }).message
          )
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [profilesApi, assignApi, storybookId])

  useEffect(() => {
    let cancelled = false
    async function loadSummary() {
      // Reset stale results from a previous storybookId before the new fetch
      // resolves; without this a guardian could briefly (or, if the fetch
      // never settles, indefinitely) see the prior story's flags. This runs
      // in the nested async function, not the effect body itself, per the
      // set-state-in-effect rule (see LibraryPage.tsx for the same pattern).
      if (cancelled) return
      setSummary(null)
      setSummaryError(false)
      try {
        const result = await assignApi.contentSummary(storybookId)
        if (!cancelled) setSummary(result)
      } catch (err) {
        // Content tags are supplementary: a failure here must not block
        // assignment. Log the message (not the axios error, whose config
        // headers carry the bearer token) and surface a visible notice so
        // the failure is never mistaken for "nothing was flagged".
        console.error('content summary load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) setSummaryError(true)
      }
    }
    void loadSummary()
    return () => {
      cancelled = true
    }
  }, [assignApi, storybookId])

  // G5 skim aid: fetch the published version's blob (same immutable-version
  // endpoint the reader uses) once the content summary tells us which version
  // is current, and derive the structure overview from it client-side. Reset
  // to null on every storybookId/summary change so a stale story's structure
  // never bleeds into the next one; a fetch failure is logged and left null
  // (StoryOverviewSection renders nothing), never surfaced as a blocking error.
  useEffect(() => {
    let cancelled = false
    async function loadStructure() {
      // Reset stale structure from a previous storybookId/summary before the
      // new fetch resolves, same set-state-in-effect rule as loadSummary
      // above: the reset lives in the nested async function, not the effect
      // body itself.
      if (cancelled) return
      setStructureBlob(null)
      if (!summary) return
      try {
        const story = await fetchStory(storybookId, summary.version)
        if (!cancelled) setStructureBlob(story as unknown as Record<string, unknown>)
      } catch (err) {
        console.error('story structure load failed:', err instanceof Error ? err.message : err)
      }
    }
    void loadStructure()
    return () => {
      cancelled = true
    }
  }, [fetchStory, storybookId, summary])

  function toggle(id: string) {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const additions = useMemo(() => [...picked].filter((id) => !assigned.has(id)), [picked, assigned])

  async function save() {
    if (additions.length === 0) {
      onClose()
      return
    }
    setSaving(true)
    setSaveError(null)
    try {
      const result = await assignApi.add(storybookId, additions)
      onAssigned?.(result)
      onClose()
    } catch (err) {
      console.error('assign save failed', err)
      setSaveError(
        classifyApiError(err, {
          transient: 'We could not assign this story. Please try again.',
          server: 'We could not assign this story. Please try again.',
        }).message
      )
      setSaving(false)
    }
  }

  // #ASSUME: external resources: the DELETE can fail (session expiry, backend
  // down). On failure keep the child shown as assigned and surface a message
  // rather than optimistically dropping the row; the endpoint is idempotent,
  // so retrying after an uncertain failure is safe.
  // #VERIFY: AssignChildrenDialog.test.tsx asserts a rejected remove() surfaces
  // an alert and leaves the row assigned.
  async function removeOne(profileId: string) {
    setRemovingId(profileId)
    setRemoveError(null)
    try {
      const remaining = await assignApi.remove(storybookId, profileId)
      setAssigned(new Set(remaining))
      // A just-removed child is no longer a pending addition either.
      setPicked((prev) => {
        const next = new Set(prev)
        next.delete(profileId)
        return next
      })
      onUnassigned?.(remaining)
    } catch (err) {
      console.error('unassign failed', err)
      setRemoveError(
        classifyApiError(err, {
          transient: 'We could not remove this child. Please try again.',
          server: 'We could not remove this child. Please try again.',
        }).message
      )
    } finally {
      setRemovingId(null)
      setConfirmId(null)
    }
  }

  return (
    <Dialog
      title="Assign to children"
      onClose={onClose}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={additions.length === 0 || saving}>
            Assign
          </Button>
        </>
      }
    >
      {loadError ? (
        <ErrorBanner>{loadError}</ErrorBanner>
      ) : profiles === null ? (
        <LoadingStatus />
      ) : (
        <>
          {saveError ? <ErrorBanner>{saveError}</ErrorBanner> : null}
          {removeError ? <ErrorBanner>{removeError}</ErrorBanner> : null}
          {summaryError ? (
            <p className="assign__content-summary console__notice cyo-text-muted">
              Content review unavailable right now. You can still assign, but flags could not be
              loaded.
            </p>
          ) : summary ? (
            <>
              <StoryOverviewSection summary={summary} structureBlob={structureBlob} />
              <ContentSummarySection summary={summary} />
            </>
          ) : null}
          {profiles.length === 0 ? (
            // A family with no profiles would otherwise see a bare empty
            // checklist with a permanently disabled Assign button and no way
            // to tell why.
            <p className="assign__empty cyo-text-muted">
              Add a child profile first, then assign books.
            </p>
          ) : (
            <ul className="assign__list" ref={listRef}>
              {profiles.map((profile) => {
                const already = assigned.has(profile.id)
                return (
                  <li key={profile.id} className="assign__row">
                    <label>
                      <input
                        type="checkbox"
                        checked={already || picked.has(profile.id)}
                        disabled={already}
                        onChange={() => toggle(profile.id)}
                      />
                      <AvatarCircle avatar={profile.avatar} name={profile.display_name} />
                      {profile.display_name}
                    </label>
                    {already ? (
                      confirmId === profile.id ? (
                        <span className="assign__remove-confirm">
                          {/* role=status announces the state change for a
                              screen-reader user who reached the cluster
                              without the focus move (e.g. a virtual-cursor
                              read). Its own text stays short for layout; the
                              per-child identity lives on the two buttons'
                              aria-labels below, which is what gets announced
                              on the focus handoff. */}
                          <span className="assign__remove-prompt cyo-text-muted" role="status">
                            Remove access?
                          </span>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setConfirmId(null)}
                            disabled={removingId !== null}
                            aria-label={`Keep ${profile.display_name}'s access`}
                          >
                            Keep
                          </Button>
                          <Button
                            variant="danger"
                            size="sm"
                            data-confirm-remove={profile.id}
                            onClick={() => void removeOne(profile.id)}
                            disabled={removingId !== null}
                            aria-label={`Confirm removing ${profile.display_name}'s access`}
                          >
                            {removingId === profile.id ? 'Removing…' : 'Remove access'}
                          </Button>
                        </span>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="assign__remove-trigger"
                          data-remove-trigger={profile.id}
                          onClick={() => setConfirmId(profile.id)}
                          disabled={removingId !== null}
                          aria-label={`Remove ${profile.display_name}'s access`}
                        >
                          Remove
                        </Button>
                      )
                    ) : null}
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}
    </Dialog>
  )
}
