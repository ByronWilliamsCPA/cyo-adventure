import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { EmptyState } from '@ds/components/EmptyState'
import { useAuth } from '../auth/useAuth'
import { useApi } from '../hooks/useApi'
import { ADMIN_CONSOLE_PATH } from '../routes'

/**
 * Guardian console home. The safety review queue that used to live here
 * moved to the admin console (AdminConsolePage) when admin functions gained
 * their own surface; this page is now the guardian's family home: an
 * onboarding nudge toward profile creation for a childless family, quick
 * links into the guardian surfaces, and (for an adult who also holds the
 * admin capability) the pointer into the admin console.
 */
export function ConsolePage() {
  const api = useApi()
  const { principal } = useAuth()
  // An admin-only adult (isAdmin without the guardian base role) has no
  // guardian family surface here: /v1/profiles always resolves to an empty
  // set for this role (api/deps.py::_resolve_profiles never scans a family's
  // children for a non-guardian principal), and profile creation is
  // guardian-only (api/profiles.py::_require_guardian), so both the
  // onboarding nudge and the quick-link grid would be dead ends for this
  // principal. A dual-role adult (role='guardian', isAdmin=true) is NOT
  // admin-only and keeps the full guardian experience.
  const isAdminOnly = principal !== null && principal.isAdmin && principal.role !== 'guardian'
  // #ASSUME: data integrity: /v1/profiles returns { profiles: [...] }. On any
  // failure childCount stays null; the onboarding nudge is gated on a
  // confirmed-empty family (childCount === 0), so a guardian keeps their
  // quick links over a transient load hiccup rather than being pushed into
  // the childless-onboarding path. The admin-only dead-link case (I4) is
  // handled by the isAdminOnly branch above, which never fetches at all.
  // #VERIFY: ConsolePage.test.tsx nudge / no-nudge / load-failure / admin-only cases.
  const [childCount, setChildCount] = useState<number | null>(null)

  useEffect(() => {
    if (isAdminOnly) return
    let cancelled = false
    async function loadChildren() {
      try {
        const res = await api.get<{ profiles?: unknown[] }>('/v1/profiles')
        const profiles = res.data.profiles ?? []
        if (!cancelled) setChildCount(profiles.length)
      } catch {
        if (!cancelled) setChildCount(null)
      }
    }
    void loadChildren()
    return () => {
      cancelled = true
    }
  }, [api, isAdminOnly])

  return (
    <section className="console">
      <h1>Family console</h1>
      {principal?.isAdmin ? (
        <p className="console__notice cyo-text-muted">
          You also have safety-reviewer access.{' '}
          <Link to={ADMIN_CONSOLE_PATH}>Open the admin console</Link> to review stories and requests
          across families.
        </p>
      ) : (
        <p className="console__notice cyo-text-muted">
          Stories are checked by your family&apos;s safety reviewer before they reach your children;
          you do not need to approve them here.
        </p>
      )}
      {isAdminOnly ? (
        <EmptyState
          title="No family console for this account"
          description="This account only has safety-reviewer access; family features like requesting stories and managing profiles aren't available here."
        />
      ) : childCount === 0 ? (
        <EmptyState
          title="Add your first reader"
          description="Create a child profile to start requesting stories."
          actions={
            <Link className="console__cta" to="/guardian/profiles">
              Add a child profile to get started
            </Link>
          }
        />
      ) : (
        <nav aria-label="Guardian quick links" className="console-group">
          <ul className="console-list">
            <li className="console-row cyo-card cyo-card--interactive">
              <Link className="console-row__link" to="/guardian/intake">
                <span className="console-row__title">Request a story</span>
              </Link>
            </li>
            <li className="console-row cyo-card cyo-card--interactive">
              <Link className="console-row__link" to="/guardian/requests">
                <span className="console-row__title">
                  Review your children&apos;s story requests
                </span>
              </Link>
            </li>
            <li className="console-row cyo-card cyo-card--interactive">
              <Link className="console-row__link" to="/guardian/books">
                <span className="console-row__title">Browse and assign books</span>
              </Link>
            </li>
            <li className="console-row cyo-card cyo-card--interactive">
              <Link className="console-row__link" to="/guardian/profiles">
                <span className="console-row__title">Manage child profiles</span>
              </Link>
            </li>
          </ul>
        </nav>
      )}
    </section>
  )
}
