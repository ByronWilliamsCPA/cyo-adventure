import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@ds/components/EmptyState'
import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import { AvatarCircle } from '../profiles/AvatarCircle'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { GUARDIAN_LOGIN_PATH } from '../routes'
import { Mascot } from './Mascot'

// `unauthenticated` is the stable, expected no-grown-up-signed-in gate, not a
// flaky fetch. `forbidden` is defensive: GET /v1/profiles does not authorize
// per role today (the backend never returns 403 on list), so that branch only
// fires if a future backend change adds one. `error` stays the transient-only
// label so its existing role="alert" and retry copy keep meaning "this should
// have worked, try again".
type PickerState =
  | { status: 'loading' }
  | { status: 'unauthenticated' }
  | { status: 'forbidden' }
  | { status: 'error' }
  | { status: 'ready'; profiles: ProfileView[] }

/**
 * Kid-surface entry point (wireframe 4.1): a 2-column avatar grid; picking a
 * profile lands the child in their own library. The book-status pill
 * (wireframe 4.1) is deferred: a child principal cannot read sibling
 * profiles' libraries (authorize_profile), so the pill needs a bulk status
 * endpoint; tracked for C4a-6. The "Add Child" tile routes to the auth-gated
 * guardian surface, so kids cannot create profiles.
 */
export function ProfilePickerPage() {
  const api = useApi()
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const [state, setState] = useState<PickerState>({ status: 'loading' })
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setState({ status: 'loading' })
      try {
        const profiles = await profilesApi.list()
        if (!cancelled) setState({ status: 'ready', profiles })
      } catch (err) {
        // Redacted shape only, never the raw axios error (its `config` carries
        // the Authorization header); see logApiError.
        logApiError('profile list failed', err)
        if (!cancelled) {
          const { kind } = classifyApiError(err)
          if (kind === 'unauthenticated') setState({ status: 'unauthenticated' })
          else if (kind === 'forbidden') setState({ status: 'forbidden' })
          else setState({ status: 'error' })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [profilesApi, reloadKey])

  if (state.status === 'loading') {
    return (
      <div role="status" aria-live="polite" className="picker-loading">
        Loading profiles…
      </div>
    )
  }

  if (state.status === 'unauthenticated') {
    return (
      <div role="status" aria-live="polite">
        <EmptyState
          title="Ask a grown-up to help"
          description="A grown-up needs to sign in before you can pick who's reading."
          icon={<Mascot size={96} />}
          actions={
            <Link className="picker-tile__add-link" to={GUARDIAN_LOGIN_PATH}>
              I am a grown-up
            </Link>
          }
        />
      </div>
    )
  }

  if (state.status === 'forbidden') {
    return (
      <div role="status" aria-live="polite">
        <EmptyState
          title="We can't show this right now"
          description="Ask a grown-up to take a look."
          icon={<Mascot size={96} />}
          actions={
            <Link className="picker-tile__add-link" to={GUARDIAN_LOGIN_PATH}>
              I am a grown-up
            </Link>
          }
        />
      </div>
    )
  }

  if (state.status === 'error') {
    return (
      <div role="alert">
        <EmptyState
          title="Oops, we hit a snag"
          description="We could not load your profiles right now."
          actions={
            <>
              <button
                type="button"
                className="picker-retry"
                onClick={() => setReloadKey((k) => k + 1)}
              >
                Try again
              </button>
              <Link className="picker-tile__add-link" to={GUARDIAN_LOGIN_PATH}>
                I am a grown-up
              </Link>
            </>
          }
        />
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
      <div className="picker__hello">
        <Mascot size={88} />
        <h1 className="picker__title">Who&apos;s reading?</h1>
      </div>
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
