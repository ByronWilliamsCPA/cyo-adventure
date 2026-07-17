import { useEffect, useMemo, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/useAuth'
import { useApi } from '../hooks/useApi'
import { ADMIN_CONSOLE_PATH } from '../routes'
import { NotificationBell } from './NotificationBell'
import { makeStoryRequestQueueApi, STORY_REQUESTS_CHANGED_EVENT } from './storyRequestQueueApi'
import './guardian.css'

/**
 * Layout chrome for the parent surface (wireframe section 2: the guardian
 * session is fully separate from the kid surface; nothing here links to it).
 */
export function GuardianShell() {
  const { principal, signOut } = useAuth()
  const [signOutError, setSignOutError] = useState(false)
  const api = useApi()
  const queueApi = useMemo(() => makeStoryRequestQueueApi(api, 'family'), [api])
  const location = useLocation()
  const [pendingCount, setPendingCount] = useState(0)
  // Bumped by StoryRequestQueue's post-action event so an approve/decline
  // updates the badge immediately instead of waiting for the next navigation.
  const [badgeRefresh, setBadgeRefresh] = useState(0)
  const hasPrincipal = principal !== null

  useEffect(() => {
    const bump = () => setBadgeRefresh((n) => n + 1)
    window.addEventListener(STORY_REQUESTS_CHANGED_EVENT, bump)
    return () => window.removeEventListener(STORY_REQUESTS_CHANGED_EVENT, bump)
  }, [])

  // Pending story-request count for the nav badge. Fetched on mount and
  // refreshed on every route change within the shell (location.pathname) and
  // on the queue's post-action event (badgeRefresh); no polling.
  //
  // #EDGE: external-resources: the badge is progressive enhancement, never an
  // error surface. Any failure (network, 403 for a non-reviewer guardian or
  // family-less admin, session expiry) silently hides it; the queue page owns
  // visible error states.
  // #VERIFY: GuardianShell.test.tsx badge-hidden-on-fetch-failure test.
  useEffect(() => {
    // No principal, no fetch; the render gate below hides any stale count.
    if (!hasPrincipal) return undefined
    let cancelled = false
    async function load() {
      try {
        const requests = await queueApi.listPending()
        if (!cancelled) setPendingCount(requests.length)
      } catch {
        if (!cancelled) setPendingCount(0)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [queueApi, hasPrincipal, location.pathname, badgeRefresh])

  // Derived, not reset in the effect: a principal-less shell (or one whose
  // principal was just cleared) shows no badge even if a count is still held.
  const pendingBadgeCount = hasPrincipal ? pendingCount : 0

  // #EDGE: external-resources: signOut rejects when Supabase cannot revoke
  // the session (network down). Surface it so the tap doesn't silently no-op
  // while the guardian believes they signed out on a shared device.
  // #VERIFY: AuthContext.test.tsx covers signOut rejection propagation.
  async function startSignOut() {
    setSignOutError(false)
    try {
      await signOut()
    } catch {
      setSignOutError(true)
    }
  }

  // Role is 'guardian' | 'child' | 'admin' (see auth/types.ts); GuardianShell
  // only ever mounts for a guardian or admin principal in practice (routed
  // behind ProtectedRoute's capability gate), but the hint is written to
  // degrade to nothing rather than mislabel a 'child' principal if that ever
  // changes. A dual-role adult reads "Guardian" here (this is the guardian
  // surface); the admin console's shell labels itself "Admin".
  const roleHint =
    principal === null
      ? null
      : principal.role === 'admin'
        ? 'Admin'
        : principal.role === 'guardian'
          ? 'Guardian'
          : null

  return (
    <div className="guardian-shell">
      <header className="guardian-shell__header">
        <span className="guardian-shell__brand">
          <span className="guardian-shell__title">CYO Adventure</span>
          {roleHint ? <span className="guardian-shell__role">{roleHint}</span> : null}
        </span>
        {principal ? (
          <div className="guardian-shell__header-actions">
            {/* G10: near the pending-count badge below, not merged with it.
                The nav badge tracks pending story requests; this tracks the
                separate guardian notification feed (safety alerts, requests
                awaiting consent, stories ready to read). */}
            <NotificationBell />
            <button
              type="button"
              className="guardian-shell__sign-out"
              onClick={() => void startSignOut()}
            >
              Sign out
            </button>
          </div>
        ) : null}
      </header>
      <nav className="guardian-shell__nav" aria-label="Guardian">
        <NavLink to="/guardian" end>
          Console
        </NavLink>
        <NavLink to="/guardian/intake">Request a story</NavLink>
        {/* G9: family-scoped like Console/Request a story/Story requests
            above (the reading-summary endpoint accepts guardian OR admin,
            api/reading_history.py::get_family_reading_summary), unlike
            Books/Profiles which are guardian-only family-management pages. */}
        <NavLink to="/guardian/reading">Reading</NavLink>
        {principal?.role === 'guardian' ? (
          <NavLink to="/guardian/books">Books</NavLink>
        ) : null}
        {/* aria-label folds the count into the accessible name; when the
            badge is hidden (zero or failed fetch) the name stays the plain
            link text. The span is aria-hidden so the bare number is never
            announced separately from that label. */}
        <NavLink
          to="/guardian/requests"
          aria-label={
            pendingBadgeCount > 0 ? `Story requests, ${pendingBadgeCount} waiting` : undefined
          }
        >
          Story requests
          {pendingBadgeCount > 0 ? (
            <span className="guardian-shell__nav-badge" aria-hidden="true">
              {pendingBadgeCount}
            </span>
          ) : null}
        </NavLink>
        {principal?.role === 'guardian' ? (
          <NavLink to="/guardian/profiles">Profiles</NavLink>
        ) : null}
        {/* ADR-016 register G17: consent is a guardian-only act (an
            admin-only adult may not stand in for a family's guardian), same
            guardian-only gating as Books/Profiles above. */}
        {principal?.role === 'guardian' ? (
          <NavLink to="/guardian/connections">Connections</NavLink>
        ) : null}
        {principal?.isAdmin ? <NavLink to={ADMIN_CONSOLE_PATH}>Admin console</NavLink> : null}
      </nav>
      {signOutError ? (
        <p role="alert" className="guardian-shell__error cyo-text-error">
          Sign-out failed. Check your connection and try again.
        </p>
      ) : null}
      <main className="guardian-shell__main">
        <Outlet />
      </main>
    </div>
  )
}
