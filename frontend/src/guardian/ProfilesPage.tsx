import { useCallback, useEffect, useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { useApi } from '../hooks/useApi'
import { AvatarCircle } from '../profiles/AvatarCircle'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import {
  ProfileFormDialog,
  type ProfileFormCreateBody,
  type ProfileFormEditBody,
} from './ProfileFormDialog'

type Editing = { mode: 'create' } | { mode: 'edit'; profile: ProfileView } | null

/**
 * Guardian profile management (C4a-2): create and edit per-child profiles,
 * surfacing the age-band and reading-level caps that gate the child's
 * library. Deletion is deferred (it cascades into reading state and ratings).
 */
export function ProfilesPage() {
  const api = useApi()
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const [profiles, setProfiles] = useState<ProfileView[] | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [editing, setEditing] = useState<Editing>(null)

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
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [profilesApi, reloadKey])

  async function create(body: ProfileFormCreateBody) {
    // POST /profiles has no pin field (extra=forbid); the dialog's
    // discriminated create/edit union makes a create body carrying `pin`
    // uncompilable, so the body can be passed through as-is.
    const created = await profilesApi.create(body)
    setProfiles((rows) => [...(rows ?? []), created])
  }

  async function update(id: string, body: ProfileFormEditBody) {
    const updated = await profilesApi.update(id, body)
    setProfiles((rows) =>
      (rows ?? []).map((row) => (row.id === updated.id ? updated : row))
    )
  }

  if (loadError) {
    return (
      <div role="alert" className="profiles__error">
        <p>We could not load your family&apos;s profiles.</p>
        <Button variant="primary" onClick={retry}>
          Try again
        </Button>
      </div>
    )
  }

  if (profiles === null) {
    return (
      <div role="status" aria-live="polite">
        Loading profiles…
      </div>
    )
  }

  return (
    <section className="profiles">
      <header className="profiles__header">
        <h1>Profiles</h1>
        <Button onClick={() => setEditing({ mode: 'create' })}>Add child</Button>
      </header>
      {profiles.length === 0 ? (
        <EmptyState
          title="No profiles yet"
          description="Add a child to start assigning stories."
        />
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
              </div>
              <Button
                variant="ghost"
                aria-label={`Edit ${profile.display_name}`}
                onClick={() => setEditing({ mode: 'edit', profile })}
              >
                Edit
              </Button>
            </li>
          ))}
        </ul>
      )}
      {editing?.mode === 'create' ? (
        <ProfileFormDialog
          title="Add child"
          onSubmit={create}
          onClose={() => setEditing(null)}
        />
      ) : null}
      {editing?.mode === 'edit' ? (
        <ProfileFormDialog
          title={`Edit ${editing.profile.display_name}`}
          initial={editing.profile}
          onSubmit={(body) => update(editing.profile.id, body)}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </section>
  )
}
