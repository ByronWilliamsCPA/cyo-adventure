import { Link } from 'react-router-dom'

import { AvatarCircle } from '../profiles/AvatarCircle'
import { useKidProfile } from './useKidProfile'
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
 * The child's name/avatar is a best-effort touch (see useKidProfile); a
 * failure (offline, hiccup) degrades to the generic "Switch reader" control
 * rather than blocking the page.
 */
export function KidNav({ profileId }: KidNavProps) {
  const profile = useKidProfile(profileId)?.profile ?? null

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
