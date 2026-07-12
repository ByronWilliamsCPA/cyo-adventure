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
  // #ASSUME: data integrity: /v1/profiles returns { profiles: [...] }. On any
  // failure childCount stays null and the onboarding nudge simply does not
  // render, so a first-time guardian is nudged but a load hiccup is silent.
  // #VERIFY: ConsolePage.test.tsx nudge / no-nudge cases.
  const [childCount, setChildCount] = useState<number | null>(null)

  useEffect(() => {
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
  }, [api])

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
      {childCount === 0 ? (
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
