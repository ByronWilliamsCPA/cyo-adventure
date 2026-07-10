import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { useApi } from '../hooks/useApi'
import { AvatarCircle } from '../profiles/AvatarCircle'
import { makeProfilesApi, type ProfileView } from '../profiles/profilesApi'
import { KID_PICKER_PATH } from '../routes'

export interface KidNavProps {
  /** The profile whose library/story is on screen. */
  profileId: string
}

/**
 * Persistent kid wayfinding bar (the "easy to navigate" fix). The kid surface
 * previously had no chrome at all, so once a child reached their library there
 * was no visible way back. This bar sits above the library and always offers a
 * way to switch readers, and shows whose books these are.
 *
 * The child's name/avatar is a best-effort touch: it reuses the same
 * authenticated `/v1/profiles` list the picker uses, scoped server-side to
 * whatever session token the browser holds, and a failure (offline, hiccup)
 * degrades to the generic "Switch reader" control rather than blocking the page.
 */
export function KidNav({ profileId }: KidNavProps) {
  const api = useApi()
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const [loaded, setLoaded] = useState<{ forId: string; profile: ProfileView | null } | null>(
    null
  )
  // Derived, not stored: the fetched profile only shows while it still belongs
  // to the profileId on screen, so a profile switch instantly falls back to the
  // generic label instead of flashing the previous child's identity.
  const profile = loaded?.forId === profileId ? loaded.profile : null

  // #ASSUME: external-resources: the profile list can fail or resolve after the
  // child has already switched profiles.
  // #VERIFY: `cancelled` guards the setState, and the fetched result is keyed
  // by the profileId it was loaded for; a switch to a new profileId or a
  // failed re-fetch therefore shows the generic label, never the previous
  // child's name/avatar.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const profiles = await profilesApi.list()
        if (!cancelled) {
          setLoaded({ forId: profileId, profile: profiles.find((p) => p.id === profileId) ?? null })
        }
      } catch (err) {
        console.error('kid nav profile lookup failed', err instanceof Error ? err.message : err)
        if (!cancelled) setLoaded({ forId: profileId, profile: null })
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [profilesApi, profileId])

  return (
    <nav className="kid-nav" aria-label="Reader navigation">
      <span className="kid-nav__who">
        {profile ? (
          <>
            <span className="kid-nav__avatar">
              <AvatarCircle avatar={profile.avatar} name={profile.display_name} />
            </span>
            <span className="kid-nav__label">
              <b>{profile.display_name}</b>
              <span>reading</span>
            </span>
          </>
        ) : (
          <span className="kid-nav__label">
            <b>My books</b>
          </span>
        )}
      </span>
      <Link className="kid-nav__switch" to={KID_PICKER_PATH}>
        <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M4 8 H16 L13 5 M20 16 H8 L11 19"
          />
        </svg>
        Switch reader
      </Link>
    </nav>
  )
}
