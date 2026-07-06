import { useEffect, useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import { AvatarCircle } from '../profiles/AvatarCircle'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { makeAssignApi, type ContentSummary } from './assignApi'
import { FlagBadge, verdictTone } from './FlagBadge'
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
  const [profiles, setProfiles] = useState<ProfileView[] | null>(null)
  const [assigned, setAssigned] = useState<Set<string>>(new Set())
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [summary, setSummary] = useState<ContentSummary | null>(null)
  const [summaryError, setSummaryError] = useState(false)

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
            }).message,
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
        console.error(
          'content summary load failed:',
          err instanceof Error ? err.message : err
        )
        if (!cancelled) setSummaryError(true)
      }
    }
    void loadSummary()
    return () => {
      cancelled = true
    }
  }, [assignApi, storybookId])

  function toggle(id: string) {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const additions = useMemo(
    () => [...picked].filter((id) => !assigned.has(id)),
    [picked, assigned],
  )

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
        }).message,
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
          <Button
            onClick={() => void save()}
            disabled={additions.length === 0 || saving}
          >
            Assign
          </Button>
        </>
      }
    >
      {loadError ? (
        <p role="alert">{loadError}</p>
      ) : profiles === null ? (
        <div role="status" aria-live="polite">
          Loading…
        </div>
      ) : (
        <>
          {saveError ? <p role="alert">{saveError}</p> : null}
          {summaryError ? (
            <p className="assign__content-summary console__notice">
              Content review unavailable right now. You can still assign, but
              flags could not be loaded.
            </p>
          ) : summary ? (
            <ContentSummarySection summary={summary} />
          ) : null}
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
        </>
      )}
    </Dialog>
  )
}
