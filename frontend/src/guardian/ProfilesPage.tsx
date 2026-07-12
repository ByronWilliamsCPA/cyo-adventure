import { useEffect, useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { EmptyState } from '@ds/components/EmptyState'
import { useApi } from '../hooks/useApi'
import { AvatarCircle } from '../profiles/AvatarCircle'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { ProfileFormDialog, type ProfileFormBody } from './ProfileFormDialog'

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

  useEffect(() => {
    let cancelled = false
    async function load() {
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
  }, [profilesApi])

  async function create(body: ProfileFormBody) {
    // POST /profiles has no pin field (extra=forbid); the dialog never emits
    // one in create mode, and rebuilding the body here guarantees it.
    const created = await profilesApi.create({
      display_name: body.display_name,
      age_band: body.age_band,
      reading_level_cap: body.reading_level_cap,
      avatar: body.avatar,
      tts_enabled: body.tts_enabled,
    })
    setProfiles((rows) => [...(rows ?? []), created])
  }

  async function update(id: string, body: ProfileFormBody) {
    const updated = await profilesApi.update(id, body)
    setProfiles((rows) =>
      (rows ?? []).map((row) => (row.id === updated.id ? updated : row))
    )
  }

  if (loadError) {
    return (
      <p role="alert" className="profiles__error">
        We could not load your family&apos;s profiles. Please reload.
      </p>
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
                  Ages {profile.age_band} · Reading cap {profile.reading_level_cap}
                  {profile.tts_enabled ? ' · Read-aloud on' : ''}
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
