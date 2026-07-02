import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@ds/components/EmptyState'
import { useApi } from '../hooks/useApi'
import { AvatarCircle } from '../profiles/AvatarCircle'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'

type PickerState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; profiles: ProfileView[] }

/**
 * Kid-surface entry point (wireframe 4.1): a 2-column avatar grid; picking a
 * profile lands the child in their own library. The book-status pill ships
 * with C4a-3 (it needs library/reading-state data). The "Add Child" tile
 * routes to the auth-gated guardian surface, so kids cannot create profiles.
 */
export function ProfilePickerPage() {
  const api = useApi()
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const [state, setState] = useState<PickerState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    async function load() {
      setState({ status: 'loading' })
      try {
        const profiles = await profilesApi.list()
        if (!cancelled) setState({ status: 'ready', profiles })
      } catch {
        if (!cancelled) setState({ status: 'error' })
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [profilesApi])

  if (state.status === 'loading') {
    return (
      <div role="status" aria-live="polite" className="picker-loading">
        Loading profiles…
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div role="alert" className="picker-error">
        We could not load your profiles. Please try again.
      </div>
    )
  }

  if (state.profiles.length === 0) {
    return (
      <EmptyState
        title="No profiles yet"
        description="Ask a grown-up to add you!"
        actions={
          <Link className="picker-tile__add-link" to="/guardian/profiles">
            I am a grown-up
          </Link>
        }
      />
    )
  }

  return (
    <section className="picker">
      <h1 className="picker__title">Who&apos;s reading?</h1>
      <ul className="picker__grid">
        {state.profiles.map((profile) => (
          <li key={profile.id}>
            <Link className="picker-tile" to={`/library/${profile.id}`}>
              <AvatarCircle avatar={profile.avatar} name={profile.display_name} />
              <span className="picker-tile__name">{profile.display_name}</span>
            </Link>
          </li>
        ))}
        <li>
          <Link className="picker-tile picker-tile--add" to="/guardian/profiles">
            <AvatarCircle avatar={null} name="+" />
            <span className="picker-tile__name">Add Child</span>
          </Link>
        </li>
      </ul>
    </section>
  )
}
