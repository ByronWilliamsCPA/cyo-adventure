import { useEffect, useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { EmptyState } from '@ds/components/EmptyState'
import { ErrorBanner } from '@ds/components/ErrorBanner'
import { LoadingStatus } from '@ds/components/LoadingStatus'
import { getDeviceGrant } from '../auth/deviceGrant'
import { makeDeviceGrantApi, type DeviceGrantApi } from '../auth/deviceGrantApi'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import type { DeviceGrantListItem } from '../client/types.gen'
import { formatRelativeTime } from './intakeApi'
import './guardian.css'

type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; devices: DeviceGrantListItem[] }

const LOAD_ERROR = 'We could not load your family’s devices. Please reload.'
const REVOKE_ERROR = 'That did not go through. Please try again.'

/**
 * How long an already-open reading session can outlive its device grant's
 * revocation, in hours.
 *
 * This is not a UI choice. Revoking clears the DEVICE token (the backend's
 * `revoke_device_grant` sets `revoked_at`, and `api/deps.py::_child_principal`'s
 * sibling `_device_principal` rejects a revoked grant on the next request), so
 * the device cannot mint a NEW child reading session. But a child session token
 * already minted is backend-signed and self-contained: `_child_principal` does
 * no database round-trip and the token carries no reference to the grant that
 * minted it, so it keeps authenticating until it expires on its own. That
 * lifetime is `child_session_ttl_seconds` in `core/config.py`, which defaults to
 * 43_200 seconds, i.e. 12 hours. See ADR-014 "Negative / risks" and UW-A43 in
 * the unscheduled work register for the durable fix.
 *
 * #ASSUME: security: the guardian-facing copy below states the DEPLOYED
 * CHILD_SESSION_TTL_SECONDS, which this constant mirrors by hand because the
 * frontend never reads backend settings.
 * #VERIFY: update this constant whenever CHILD_SESSION_TTL_SECONDS changes, or
 * the copy will overstate or understate how long revocation takes to bite.
 */
const CHILD_SESSION_MAX_HOURS = 12

async function loadDevices(
  deviceGrantApi: DeviceGrantApi,
  cancelled: () => boolean,
  setState: (state: PageState) => void
): Promise<void> {
  setState({ kind: 'loading' })
  try {
    const devices = await deviceGrantApi.list()
    if (!cancelled()) setState({ kind: 'ready', devices })
  } catch (err) {
    console.error('device grant list load failed:', err instanceof Error ? err.message : err)
    if (!cancelled()) {
      setState({
        kind: 'error',
        message: classifyApiError(err, { transient: LOAD_ERROR, server: LOAD_ERROR }).message,
      })
    }
  }
}

/**
 * One device row: the guardian-facing label (or a fallback for an
 * unlabeled grant), when it was granted, and a revoke action. "This
 * device" is derived by comparing the row's id against the locally stored
 * grant (`auth/deviceGrant.ts`), the same id ConsolePage's own
 * authorize/remove actions key off of; it is a display hint only, not an
 * authorization decision, so a stale or cleared local grant simply shows no
 * badge rather than misidentifying a row.
 */
function DeviceRow({
  device,
  isThisDevice,
  isPending,
  error,
  nowMs,
  onRevoke,
}: {
  device: DeviceGrantListItem
  isThisDevice: boolean
  isPending: boolean
  error: string | undefined
  nowMs: number
  onRevoke: () => void
}) {
  const ago = formatRelativeTime(device.created_at, nowMs)
  return (
    <li className="devices-card cyo-card">
      <div className="devices-card__main">
        <span className="devices-card__name">{device.label ?? 'Unnamed device'}</span>
        {isThisDevice ? <span className="devices-chip devices-chip--this">This device</span> : null}
      </div>
      <p className="devices-card__meta cyo-text-muted">
        {ago !== null ? (
          <span title={new Date(device.created_at).toLocaleString()}>Granted {ago}</span>
        ) : (
          <span>Granted {new Date(device.created_at).toLocaleString()}</span>
        )}
      </p>
      <div className="devices-card__actions">
        <Button variant="danger" disabled={isPending} onClick={onRevoke}>
          Revoke
        </Button>
      </div>
      {error ? <ErrorBanner className="devices-card__error">{error}</ErrorBanner> : null}
    </li>
  )
}

/**
 * Guardian device management (register G15, ADR-014's own lost-device
 * mitigation): lists every currently-active device grant for the caller's
 * family and lets a guardian revoke one, e.g. a lost or no-longer-shared
 * tablet. Backed by the mint/list/revoke endpoints in
 * `api/device_grants.py`, which were already family-scoped and tested
 * (`test_list_returns_only_own_family_active_grants`) but had no UI caller
 * before this page; `deviceGrantApi.ts.list()` was dead code until now.
 *
 * Deliberately does NOT cover the other half of G15 (which books are
 * downloaded on which device, storage use): that needs a backend
 * `offline/` module that does not exist yet and depends on K10's
 * client-side offline architecture; the register still lists it as open.
 */
export function DevicesPage() {
  const api = useApi()
  const deviceGrantApi = useMemo(() => makeDeviceGrantApi(api), [api])
  const [state, setState] = useState<PageState>({ kind: 'loading' })
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({})
  const [confirming, setConfirming] = useState<DeviceGrantListItem | null>(null)
  // Captured once per mount for "granted N days ago" phrasing; the page
  // recomputes on the next reload rather than ticking live, matching
  // ReadingPage.tsx's syncedAt pattern.
  const [nowMs] = useState(() => Date.now())
  const thisDeviceId = useMemo(() => getDeviceGrant()?.id ?? null, [])

  useEffect(() => {
    let cancelled = false
    void loadDevices(deviceGrantApi, () => cancelled, setState)
    return () => {
      cancelled = true
    }
  }, [deviceGrantApi])

  async function runRevoke(device: DeviceGrantListItem): Promise<void> {
    if (pendingId !== null) return
    setPendingId(device.id)
    setRowErrors((prev) => {
      if (!(device.id in prev)) return prev
      const next = { ...prev }
      delete next[device.id]
      return next
    })
    try {
      await deviceGrantApi.revoke(device.id)
      setState((prev) =>
        prev.kind === 'ready'
          ? { kind: 'ready', devices: prev.devices.filter((d) => d.id !== device.id) }
          : prev
      )
    } catch (err) {
      console.error('device grant revoke failed:', err instanceof Error ? err.message : err)
      setRowErrors((prev) => ({ ...prev, [device.id]: REVOKE_ERROR }))
    } finally {
      setPendingId(null)
    }
  }

  function confirmAndClose(): void {
    if (confirming === null) return
    const device = confirming
    setConfirming(null)
    void runRevoke(device)
  }

  if (state.kind === 'loading') {
    return <LoadingStatus>Loading your family&apos;s devices…</LoadingStatus>
  }

  if (state.kind === 'error') {
    return <ErrorBanner className="devices__error">{state.message}</ErrorBanner>
  }

  const { devices } = state

  return (
    <section className="devices">
      <h1>Devices</h1>
      <p className="devices__intro cyo-text-muted">
        Every device authorized for your family shows up here. Revoking a device stops it from
        starting any new reading sessions right away. If one of your kids is already reading on that
        device, that session is not cut off: it can keep going for up to {CHILD_SESSION_MAX_HOURS}{' '}
        hours, until it runs out on its own.
      </p>
      {devices.length === 0 ? (
        <EmptyState
          title="No devices authorized yet"
          description="Set up a device for your kids from the family console to see it listed here."
        />
      ) : (
        <ul className="devices__list">
          {devices.map((device) => (
            <DeviceRow
              key={device.id}
              device={device}
              isThisDevice={thisDeviceId !== null && thisDeviceId === device.id}
              isPending={pendingId === device.id}
              error={rowErrors[device.id]}
              nowMs={nowMs}
              onRevoke={() => setConfirming(device)}
            />
          ))}
        </ul>
      )}
      {confirming !== null ? (
        <Dialog
          title="Revoke this device?"
          onClose={() => setConfirming(null)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setConfirming(null)}>
                Cancel
              </Button>
              <Button variant="danger" onClick={confirmAndClose}>
                Revoke
              </Button>
            </>
          }
        >
          <p>
            {confirming.label ?? 'This device'} will not be able to start a new reading session. A
            reading session already open on it can keep going for up to {CHILD_SESSION_MAX_HOURS}{' '}
            hours, until it runs out on its own.
          </p>
        </Dialog>
      ) : null}
    </section>
  )
}
