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
 * The child's name/avatar is a best-effort touch: it is fetched from the same
 * unauthenticated profile list the picker uses, and a failure (offline, hiccup)
 * degrades to the generic "Switch reader" control rather than blocking the page.
 */
export function KidNav({ profileId }: KidNavProps) {
  const api = useApi()
  const profilesApi = useMemo(() => makeProfilesApi(api), [api])
  const [profile, setProfile] = useState<ProfileView | null>(null)

  // #ASSUME: external-resources: the profile list can fail or resolve after the
  // child has already switched profiles.
  // #VERIFY: `cancelled` guards the setState; a failure just leaves the name
  // unshown, and the Switch control (which needs no data) still works.
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const profiles = await profilesApi.list()
        if (!cancelled) setProfile(profiles.find((p) => p.id === profileId) ?? null)
      } catch (err) {
        console.error('kid nav profile lookup failed', err)
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
