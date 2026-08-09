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
import { usePageTitle } from '../hooks/usePageTitle'
import type { DeviceDownloadView, DeviceGrantListItem } from '../client/types.gen'
import { makeDeviceDownloadsApi, type DeviceDownloadsApi } from './deviceDownloadsApi'
import { formatRelativeTime } from './intakeApi'
import './guardian.css'

type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; devices: DeviceGrantListItem[] }

type DownloadsState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; downloads: DeviceDownloadView[] }

const LOAD_ERROR = 'We could not load your family’s devices. Please reload.'
const REVOKE_ERROR = 'That did not go through. Please try again.'
const DOWNLOADS_LOAD_ERROR = 'We could not load your family’s downloaded books.'

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

async function loadDownloads(
  deviceDownloadsApi: DeviceDownloadsApi,
  cancelled: () => boolean,
  setState: (state: DownloadsState) => void
): Promise<void> {
  setState({ kind: 'loading' })
  try {
    const downloads = await deviceDownloadsApi.list()
    if (!cancelled()) setState({ kind: 'ready', downloads })
  } catch (err) {
    console.error('device downloads load failed:', err instanceof Error ? err.message : err)
    if (!cancelled()) {
      setState({
        kind: 'error',
        message: classifyApiError(err, {
          transient: DOWNLOADS_LOAD_ERROR,
          server: DOWNLOADS_LOAD_ERROR,
        }).message,
      })
    }
  }
}

/** Group a flat download list by device_id, newest-confirmed-first within
 * each group, groups themselves ordered by their own newest entry. */
function groupByDevice(
  downloads: DeviceDownloadView[]
): Array<{ deviceId: string; items: DeviceDownloadView[] }> {
  const byDevice = new Map<string, DeviceDownloadView[]>()
  for (const item of downloads) {
    const group = byDevice.get(item.device_id)
    if (group) {
      group.push(item)
    } else {
      byDevice.set(item.device_id, [item])
    }
  }
  return [...byDevice.entries()]
    .map(([deviceId, items]) => ({
      deviceId,
      items: [...items].sort((a, b) => b.last_confirmed_at.localeCompare(a.last_confirmed_at)),
    }))
    .sort((a, b) => b.items[0].last_confirmed_at.localeCompare(a.items[0].last_confirmed_at))
}

/**
 * One device's downloaded-books group. `device_id` is a separate identity
 * from `DeviceGrant.id` (see `DeviceDownload`'s docstring in db/models.py),
 * so this cannot be matched back to a device grant's guardian-set label;
 * the last 6 characters of the id are shown only as a way to tell two
 * groups apart, not as a friendly name.
 */
function DownloadsGroup({
  deviceId,
  items,
  nowMs,
}: {
  deviceId: string
  items: DeviceDownloadView[]
  nowMs: number
}) {
  return (
    <li className="devices-card cyo-card">
      <div className="devices-card__main">
        <span className="devices-card__name">Device …{deviceId.slice(-6)}</span>
      </div>
      <ul className="devices-downloads__books">
        {items.map((item) => {
          const ago = formatRelativeTime(item.last_confirmed_at, nowMs)
          return (
            <li key={item.id} className="devices-downloads__book">
              <span>{item.storybook_title ?? item.storybook_id}</span>
              <span className="cyo-text-muted">
                {item.profile_name} · last confirmed{' '}
                {ago !== null ? ago : new Date(item.last_confirmed_at).toLocaleDateString()}
              </span>
            </li>
          )
        })}
      </ul>
    </li>
  )
}

/**
 * The offline-download inventory half of G15, alongside the device
 * list/revoke half above. A best-effort snapshot, not a strict inventory
 * (see `DeviceDownload`'s docstring): a device that goes permanently
 * offline right after downloading leaves a stale row behind, which is why
 * every book shows its own "last confirmed" time rather than a single
 * page-level sync timestamp.
 */
function DownloadsSection({ state, nowMs }: { state: DownloadsState; nowMs: number }) {
  if (state.kind === 'loading') {
    return <LoadingStatus>Loading downloaded books…</LoadingStatus>
  }
  if (state.kind === 'error') {
    return <ErrorBanner className="devices__error">{state.message}</ErrorBanner>
  }
  if (state.downloads.length === 0) {
    return (
      <EmptyState
        title="No books downloaded yet"
        description="Once a story is read offline on a device, it shows up here."
      />
    )
  }
  const groups = groupByDevice(state.downloads)
  return (
    <ul className="devices__list">
      {groups.map((group) => (
        <DownloadsGroup
          key={group.deviceId}
          deviceId={group.deviceId}
          items={group.items}
          nowMs={nowMs}
        />
      ))}
    </ul>
  )
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
 * Also renders the other half of G15 below the device list: which books
 * are downloaded on which device (`DownloadsSection`), backed by
 * `api/offline_downloads.py` and reported by the reader on every read
 * (`ReaderPage.tsx`'s `reportDownload` prop). The two halves use separate
 * device identities (a device grant's id vs. a plain client-generated
 * `device_id`, see `offline/deviceId.ts`) and are not cross-referenced.
 */
export function DevicesPage() {
  usePageTitle('Devices')
  const api = useApi()
  const deviceGrantApi = useMemo(() => makeDeviceGrantApi(api), [api])
  const deviceDownloadsApi = useMemo(() => makeDeviceDownloadsApi(api), [api])
  const [state, setState] = useState<PageState>({ kind: 'loading' })
  const [downloadsState, setDownloadsState] = useState<DownloadsState>({ kind: 'loading' })
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

  // Independent load, independent failure: a downloads-list error must
  // never block the device list above (and vice versa) from rendering.
  useEffect(() => {
    let cancelled = false
    void loadDownloads(deviceDownloadsApi, () => cancelled, setDownloadsState)
    return () => {
      cancelled = true
    }
  }, [deviceDownloadsApi])

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
      <h2 className="devices__downloads-heading">Downloaded books</h2>
      <p className="devices__intro cyo-text-muted">
        Which books are saved for offline reading, and where. This is a best-effort snapshot: a
        device that stops connecting can leave a book listed here after it is no longer actually
        stored on it.
      </p>
      <DownloadsSection state={downloadsState} nowMs={nowMs} />
    </section>
  )
}
