import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { hasValidDeviceGrant, hydrateDeviceGrant } from '../auth/deviceGrant'
import { Mascot } from '../kid/Mascot'
import {
  AUTHORIZE_DEVICE_INTENT_PARAM,
  AUTHORIZE_DEVICE_INTENT_VALUE,
  GUARDIAN_CONSOLE_PATH,
  GUARDIAN_LOGIN_PATH,
  KID_PICKER_PATH,
} from '../routes'

import './landing.css'

/**
 * Guardian login, carrying the authorize-device intent marker (ADR-014
 * section 5): the destination for the Kids door on a device with no valid
 * device grant yet. A guardian who signs in from here is authorizing THIS
 * device, not just visiting their console; DeviceAuthorizedRoute reads the
 * same intent constants (auth/DeviceAuthorizedRoute.tsx, routes.ts).
 */
const AUTHORIZE_DEVICE_PATH = `${GUARDIAN_LOGIN_PATH}?${AUTHORIZE_DEVICE_INTENT_PARAM}=${AUTHORIZE_DEVICE_INTENT_VALUE}`

/**
 * Root landing page: the one page both audiences see. Static by design (no
 * data fetching, no auth) so it imports neither the guardian/Supabase chunk nor
 * any kid data hooks: only the presentational Mascot glyph is shared, which
 * keeps the router's two-surface split intact. `auth/deviceGrant.ts` is
 * Supabase-free by design (same contract the kid chunk relies on), so reading
 * the device grant here does not pull Supabase into this page either.
 */
export function LandingPage() {
  // Device-state-aware Kids door (ADR-014 section 5): an authorized device
  // sends a child straight to the profile picker; an unauthorized one routes
  // through guardian login carrying the authorize-device intent so the
  // guardian mints a grant for this device before handing it back. The
  // synchronous localStorage check covers the common case with no loading
  // flicker; hydrateDeviceGrant's IndexedDB-mirror fallback (the same
  // sync-then-hydrate pattern DeviceAuthorizedRoute uses) runs once after
  // mount and upgrades the door target if it finds a valid grant localStorage
  // lost (private-mode eviction, a fresh clear).
  // #ASSUME: timing dependencies: a device that gains a valid grant WHILE the
  // landing page is already mounted (e.g. a second tab authorizes it) is not
  // picked up until the door is followed and DeviceAuthorizedRoute re-checks;
  // this page does not poll or listen for storage events.
  // #VERIFY: LandingPage.test.tsx "kids door" sync + post-hydrate cases.
  const [kidsDoorPath, setKidsDoorPath] = useState(() =>
    hasValidDeviceGrant() ? KID_PICKER_PATH : AUTHORIZE_DEVICE_PATH
  )

  useEffect(() => {
    if (kidsDoorPath === KID_PICKER_PATH) return
    let cancelled = false
    void hydrateDeviceGrant().then((grant) => {
      if (cancelled) return
      if (grant) setKidsDoorPath(KID_PICKER_PATH)
    })
    return () => {
      cancelled = true
    }
  }, [kidsDoorPath])

  return (
    <main className="landing">
      <div className="landing__hero">
        <Mascot size={128} />
        <h1 className="landing__title">CYO Adventure</h1>
        <p className="landing__tagline">Choose-your-own adventures for young readers.</p>
      </div>
      <nav className="landing__doors" aria-label="Pick who you are">
        <Link className="landing-door landing-door--kids" to={kidsDoorPath}>
          <span className="landing-door__icon" aria-hidden="true">
            <svg width="30" height="30" viewBox="0 0 24 24" focusable="false">
              <path
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M4 5 C7 3 10 3 12 5 C14 3 17 3 20 5 V19 C17 17 14 17 12 19 C10 17 7 17 4 19 Z M12 5 V19"
              />
            </svg>
          </span>
          <span className="landing-door__text">
            <span className="landing-door__heading">Kids</span>
            <span className="landing-door__sub">Start reading</span>
          </span>
        </Link>
        <Link className="landing-door landing-door--guardian" to={GUARDIAN_CONSOLE_PATH}>
          <span className="landing-door__icon" aria-hidden="true">
            <svg width="30" height="30" viewBox="0 0 24 24" focusable="false">
              <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2" />
              <path fill="currentColor" d="M12 12 L15.5 8.5 L13 12 Z M12 12 L8.5 15.5 L11 12 Z" />
            </svg>
          </span>
          <span className="landing-door__text">
            <span className="landing-door__heading">Grown-ups</span>
            <span className="landing-door__sub">Guardian console</span>
            <span className="landing-door__note">Admins sign in here too</span>
          </span>
        </Link>
      </nav>
    </main>
  )
}
