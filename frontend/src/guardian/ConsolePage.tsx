import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { EmptyState } from '@ds/components/EmptyState'
import { ErrorBanner } from '@ds/components/ErrorBanner'
import {
  clearDeviceGrant,
  getDeviceGrant,
  hasValidDeviceGrant,
  setDeviceGrant,
} from '../auth/deviceGrant'
import { makeDeviceGrantApi } from '../auth/deviceGrantApi'
import { useAuth } from '../auth/useAuth'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'
import { ADMIN_CONSOLE_PATH, KID_PICKER_PATH } from '../routes'

/** Local UI status for the authorize-device action; independent of childCount's load. */
type DeviceActionStatus = 'idle' | 'busy' | 'error'

/**
 * Guardian console home. The safety review queue that used to live here
 * moved to the admin console (AdminConsolePage) when admin functions gained
 * their own surface; this page is now the guardian's family home: an
 * onboarding nudge toward profile creation for a childless family, quick
 * links into the guardian surfaces, a device-authorization control (ADR-014
 * Phase 3), and (for an adult who also holds the admin capability) the
 * pointer into the admin console.
 */
export function ConsolePage() {
  const api = useApi()
  const navigate = useNavigate()
  const deviceGrantApi = useMemo(() => makeDeviceGrantApi(api), [api])
  const { principal, signOut } = useAuth()
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

  // Device-authorization control (ADR-014 Phase 3): mints, re-mints, or
  // forgets a durable device grant so this device's `/kids` surface can read
  // without a live guardian session. Read directly from localStorage on
  // mount; this page is guardian-only (a signed-in adult), so it never needs
  // the async IndexedDB-mirror fallback DeviceAuthorizedRoute uses on the kid
  // side.
  const [grant, setGrant] = useState(() => getDeviceGrant())
  const [deviceStatus, setDeviceStatus] = useState<DeviceActionStatus>('idle')
  // Guards the one-click "Remove from this device" action behind a confirm
  // step: a misclick would otherwise lock kids out of reading on this device
  // until a guardian re-authorizes it.
  // #VERIFY: ConsolePage.test.tsx "asks for confirmation before removing the
  // device grant" and "does not revoke when the confirmation is cancelled".
  const [confirmingRemove, setConfirmingRemove] = useState(false)

  async function authorizeDevice() {
    setDeviceStatus('busy')
    // #CRITICAL: security: capture the grant this device currently holds BEFORE
    // minting its replacement. "Re-authorize this device" reuses this action,
    // and without revoking the prior grant that old 90-day family-scoped
    // credential stays valid server-side (the online revocation check only
    // rejects grants whose revoked_at is set), silently orphaning a live
    // credential on every re-authorize. null on first-time setup.
    // #VERIFY: ConsolePage.test.tsx "re-authorize revokes the superseded grant".
    const previous = getDeviceGrant()
    try {
      const view = await deviceGrantApi.mint()
      setDeviceGrant({
        token: view.token,
        expiresAt: view.expires_at,
        familyId: view.family_id,
        id: view.id,
      })
      setGrant(getDeviceGrant())
      // Revoke the superseded grant only after the replacement is minted and
      // stored, so a revoke failure cannot strand this device without a usable
      // credential. Best-effort: a failed revoke logs but does not fail the
      // re-authorize (the new grant is already active). Skipped on first-time
      // setup (no previous) and when the id is unchanged (defensive).
      if (previous && previous.id !== view.id) {
        await deviceGrantApi.revoke(previous.id).catch((err: unknown) => {
          logApiError('superseded device grant revoke failed', err)
        })
      }
      setDeviceStatus('idle')
    } catch (err) {
      logApiError('device grant mint failed', err)
      setDeviceStatus('error')
    }
  }

  // #CRITICAL: security: shed the guardian session before this device becomes a
  // kid surface. The launch button previously only navigated, leaving the
  // guardian bearer in localStorage where the useApi fallthrough would attach
  // it on a kid route that misses the child-session/device-grant branches,
  // exposing the family library to the child. signOut() clears the local
  // credential synchronously (fail closed) before its network revoke, so the
  // token is gone the instant we hand off; the network revoke is best effort
  // and navigation does not wait on it.
  // #VERIFY: ConsolePage.test.tsx "hands the device to a child and signs the
  // guardian out".
  function handDeviceToChild() {
    void signOut().catch((err: unknown) => {
      logApiError('sign-out on device handoff failed', err)
    })
    void navigate(KID_PICKER_PATH)
  }

  // #CRITICAL: security: only clear the LOCAL grant after the server confirms
  // the revoke; if the DELETE fails (network blip, already-revoked-elsewhere),
  // the button's "removed" claim would otherwise be a lie: the grant record
  // stays active server-side while this page shows it as gone, and a guardian
  // who believes it removed would not think to check the device list again.
  // #VERIFY: ConsolePage.test.tsx "keeps showing the grant when revoke fails".
  async function removeFromThisDevice() {
    if (!grant) return
    setDeviceStatus('busy')
    try {
      await deviceGrantApi.revoke(grant.id)
      clearDeviceGrant()
      setGrant(null)
      setDeviceStatus('idle')
    } catch (err) {
      logApiError('device grant revoke failed', err)
      setDeviceStatus('error')
    }
  }

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
      {isAdminOnly ? null : (
        <section aria-label="Device setup" className="console-device">
          <h2>This device</h2>
          {grant ? (
            <>
              <p className="console__notice cyo-text-muted">
                This device is set up for your family; kids can now read here.
              </p>
              <div className="console-device__actions">
                {hasValidDeviceGrant() ? (
                  // The launch affordance carries no authorization of its own:
                  // the durable device grant is what authorizes `/kids`.
                  // hasValidDeviceGrant() is the same local, client-side
                  // pre-check DeviceAuthorizedRoute uses to gate `/kids`
                  // (auth/deviceGrant.ts), so this button is never shown when
                  // that gate would immediately bounce the child back to
                  // guardian login. handDeviceToChild() sheds the guardian
                  // session before navigating (see its #CRITICAL note).
                  <div className="console-device__action">
                    <Button
                      variant="primary"
                      size="sm"
                      disabled={deviceStatus === 'busy'}
                      aria-describedby="device-hand-hint"
                      onClick={() => handDeviceToChild()}
                    >
                      Hand device to a child
                    </Button>
                    <p id="device-hand-hint" className="console-device__hint cyo-text-muted">
                      This signs you out so your child can read safely.
                    </p>
                  </div>
                ) : null}
                <div className="console-device__action">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={deviceStatus === 'busy'}
                    onClick={() => void authorizeDevice()}
                  >
                    Re-authorize this device
                  </Button>
                </div>
                <div className="console-device__action">
                  <Button
                    variant="danger"
                    size="sm"
                    disabled={deviceStatus === 'busy'}
                    aria-describedby="device-remove-hint"
                    onClick={() => setConfirmingRemove(true)}
                  >
                    Remove from this device
                  </Button>
                  <p id="device-remove-hint" className="console-device__hint cyo-text-muted">
                    Kids can no longer read on this device until you authorize
                    it again.
                  </p>
                </div>
              </div>
            </>
          ) : (
            <>
              <p className="console__notice cyo-text-muted">
                Set up this device so your kids can read here without you signing in every time.
              </p>
              <Button
                variant="primary"
                size="sm"
                disabled={deviceStatus === 'busy'}
                onClick={() => void authorizeDevice()}
              >
                Set up this device for your kids
              </Button>
            </>
          )}
          {deviceStatus === 'error' ? (
            <ErrorBanner className="console-device__error">
              That didn&apos;t work. Check your connection and try again.
            </ErrorBanner>
          ) : null}
        </section>
      )}
      {confirmingRemove ? (
        <Dialog
          title="Remove this device?"
          onClose={() => setConfirmingRemove(false)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setConfirmingRemove(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                onClick={() => {
                  setConfirmingRemove(false)
                  void removeFromThisDevice()
                }}
              >
                Remove device
              </Button>
            </>
          }
        >
          <p>Kids will not be able to read on this device until you authorize it again.</p>
        </Dialog>
      ) : null}
    </section>
  )
}
