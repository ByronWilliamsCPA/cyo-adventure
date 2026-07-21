import { useEffect, useMemo, useState } from 'react'

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
import { FlagBadge, verdictTone } from './FlagBadge'
import { StoryStructureSummary } from './StoryStructureSummary'
import './guardian.css'

interface AssignChildrenDialogProps {
  storybookId: string
  onClose: () => void
  onAssigned?: (profileIds: string[]) => void
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
            // Content-derived key: story-level findings are distinct by
            // (category, verdict, message), so this stays stable if the list
            // is ever reordered or spliced, unlike an array index.
            <li
              key={`${finding.category}-${finding.verdict}-${finding.message}`}
              className="review-finding"
            >
              <FlagBadge tone={verdictTone(finding.verdict)} />
              <span className="review-finding__category">{finding.category}</span>
              <span className="review-finding__message">{finding.message}</span>
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
 * disabled; Save posts only the newly selected ids (add-only, idempotent).
 */
export function AssignChildrenDialog({
  storybookId,
  onClose,
  onAssigned,
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
  const [summary, setSummary] = useState<ContentSummary | null>(null)
  const [summaryError, setSummaryError] = useState(false)
  const [structureBlob, setStructureBlob] = useState<Record<string, unknown> | null>(null)

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
            <ul className="assign__list">
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
