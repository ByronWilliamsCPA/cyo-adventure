import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { EmptyState } from '@ds/components/EmptyState'
import { ErrorBanner } from '@ds/components/ErrorBanner'
import { LoadingStatus } from '@ds/components/LoadingStatus'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import { usePageTitle } from '../hooks/usePageTitle'
import { AvatarCircle } from '../profiles/AvatarCircle'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { previewAsChildPath } from '../routes'
import { makeBudgetApi, type ChildEnvelopeUsage } from './budgetApi'
import {
  ProfileFormDialog,
  type ProfileFormCreateBody,
  type ProfileFormEditBody,
} from './ProfileFormDialog'

type Editing = { mode: 'create' } | { mode: 'edit'; profile: ProfileView } | null

/**
 * Guardian profile management (C4a-2): create and edit per-child profiles,
 * surfacing the age-band and reading-level caps that gate the child's
 * library. Deletion (P-6c) is confirm-gated: DELETE /v1/profiles/{id}
 * cascades into the child's reading state, completions, ratings,
 * assignments, and picker PIN server-side (api/profiles.py), so the
 * confirm dialog names the child and states that this cannot be undone.
 */
export function ProfilesPage() {
  usePageTitle('Profiles')
  const api = useApi()
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const budgetApi = useMemo(() => makeBudgetApi(api), [api])
  const [profiles, setProfiles] = useState<ProfileView[] | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [editing, setEditing] = useState<Editing>(null)
  // The profile awaiting delete confirmation (null when the dialog is
  // closed). Deletion is permanent and cascades into reading history, so it
  // gets the same confirm-before-destructive-action pattern as
  // StoryRequestQueue's decline dialog, rather than a one-click button.
  const [deletingProfile, setDeletingProfile] = useState<ProfileView | null>(null)
  // #ASSUME: external-resources: the delete call can fail (network, session
  // expiry, server error). Surface it inline in the dialog rather than
  // silently closing it, so a guardian is not left believing the profile is
  // gone when the request never landed.
  // #VERIFY: ProfilesPage.test.tsx delete-failure test.
  const [deleteError, setDeleteError] = useState(false)
  const [deleting, setDeleting] = useState(false)
  // ADR-015 G3: each child's current auto-approve setting, keyed by
  // profile id, sourced from GET /v1/families/me/budget (ProfileView itself
  // does not carry these fields; see ProfileFormDialog's envelopeInfo prop
  // doc). Powers both the "Auto-approve on" card badge and the edit
  // dialog's seeded toggle/limit. A failed fetch leaves this empty rather
  // than blocking the page: it is a secondary signal, not the profile list
  // itself.
  const [envelopeByProfile, setEnvelopeByProfile] = useState<Record<string, ChildEnvelopeUsage>>({})

  const [reloadKey, setReloadKey] = useState(0)
  const retry = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoadError(false)
      setProfiles(null)
      try {
        const rows = await profilesApi.list()
        if (!cancelled) setProfiles(rows)
      } catch (err) {
        console.error('profile list failed', err)
        if (!cancelled) setLoadError(true)
      }
      try {
        const budget = await budgetApi.get()
        if (!cancelled) {
          const byProfile: Record<string, ChildEnvelopeUsage> = {}
          for (const child of budget.children) byProfile[child.profile_id] = child
          setEnvelopeByProfile(byProfile)
        }
      } catch (err) {
        // Non-fatal: badges/seeded envelope info just stay absent.
        console.error('budget fetch for profiles page failed', err)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [profilesApi, budgetApi, reloadKey])

  async function create(body: ProfileFormCreateBody) {
    // POST /profiles has no pin field (extra=forbid); the dialog's
    // discriminated create/edit union makes a create body carrying `pin`
    // uncompilable, so the body can be passed through as-is.
    const created = await profilesApi.create(body)
    setProfiles((rows) => [...(rows ?? []), created])
  }

  async function update(id: string, body: ProfileFormEditBody) {
    const updated = await profilesApi.update(id, body)
    setProfiles((rows) => (rows ?? []).map((row) => (row.id === updated.id ? updated : row)))
  }

  // P-6c: permanent, confirm-gated. Called only from the confirm dialog
  // (confirmDelete), never directly from the row's Delete button.
  async function deleteProfile(id: string) {
    setDeleting(true)
    setDeleteError(false)
    try {
      await profilesApi.deleteProfile(id)
      setProfiles((rows) => (rows ?? []).filter((row) => row.id !== id))
      setDeletingProfile(null)
    } catch (err) {
      // Redacted, never the raw AxiosError: its `config.headers.Authorization`
      // carries the guardian bearer token. See logApiError's own doc comment
      // for the "no auth material in the console" invariant.
      logApiError('profile delete failed', err)
      setDeleteError(true)
    } finally {
      setDeleting(false)
    }
  }

  if (loadError) {
    return (
      <ErrorBanner className="profiles__error" onRetry={retry}>
        We could not load your family&apos;s profiles.
      </ErrorBanner>
    )
  }

  if (profiles === null) {
    return <LoadingStatus>Loading profiles…</LoadingStatus>
  }

  return (
    <section className="profiles">
      <header className="profiles__header">
        <h1>Profiles</h1>
        <Button onClick={() => setEditing({ mode: 'create' })}>Add child</Button>
      </header>
      {profiles.length === 0 ? (
        <EmptyState title="No profiles yet" description="Add a child to start assigning stories." />
      ) : (
        <ul className="profiles__list">
          {profiles.map((profile) => (
            <li key={profile.id} className="profiles__card cyo-card">
              <AvatarCircle avatar={profile.avatar} name={profile.display_name} />
              <div className="profiles__card-body">
                <span className="profiles__name">{profile.display_name}</span>
                <span className="profiles__caps">
                  {/* 99 is the unset-ceiling sentinel (profilesApi.ts), not a
                      real grade level, so it reads as "no limit" here. */}
                  Ages {profile.age_band} ·{' '}
                  {profile.reading_level_cap === 99
                    ? 'No reading limit'
                    : `Reading level ${profile.reading_level_cap}`}
                </span>
                {envelopeByProfile[profile.id]?.request_auto_approve ? (
                  <span className="profiles__badge">Auto-approve on</span>
                ) : null}
              </div>
              <Link
                className="profiles__preview-link"
                aria-label={`Preview as ${profile.display_name}`}
                to={previewAsChildPath(profile.id)}
              >
                Preview
              </Link>
              <Button
                variant="ghost"
                aria-label={`Edit ${profile.display_name}`}
                onClick={() => setEditing({ mode: 'edit', profile })}
              >
                Edit
              </Button>
              {/* P-6c: destructive and confirm-gated (see the dialog below),
                  placed last and styled as danger so it reads distinctly
                  from Preview/Edit rather than competing for the default
                  tap target. */}
              <Button
                variant="danger"
                size="sm"
                className="profiles__delete-btn"
                aria-label={`Delete ${profile.display_name}`}
                onClick={() => {
                  setDeleteError(false)
                  setDeletingProfile(profile)
                }}
              >
                Delete
              </Button>
            </li>
          ))}
        </ul>
      )}
      {editing?.mode === 'create' ? (
        <ProfileFormDialog title="Add child" onSubmit={create} onClose={() => setEditing(null)} />
      ) : null}
      {editing?.mode === 'edit' ? (
        <ProfileFormDialog
          title={`Edit ${editing.profile.display_name}`}
          initial={editing.profile}
          envelopeInfo={envelopeByProfile[editing.profile.id]}
          onSubmit={(body) => update(editing.profile.id, body)}
          onClose={() => setEditing(null)}
        />
      ) : null}
      {deletingProfile !== null ? (
        <Dialog
          title={`Delete ${deletingProfile.display_name}'s profile?`}
          onClose={() => setDeletingProfile(null)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setDeletingProfile(null)} disabled={deleting}>
                Cancel
              </Button>
              <Button
                variant="danger"
                disabled={deleting}
                onClick={() => void deleteProfile(deletingProfile.id)}
              >
                {deleting ? 'Deleting…' : 'Delete profile'}
              </Button>
            </>
          }
        >
          <p>
            This permanently deletes <strong>{deletingProfile.display_name}&apos;s</strong> profile,
            including their reading history, ratings, and story assignments. This cannot be undone.
          </p>
          {deleteError ? (
            <ErrorBanner className="profiles__delete-error">
              We could not delete this profile. Please try again.
            </ErrorBanner>
          ) : null}
        </Dialog>
      ) : null}
    </section>
  )
}
