import { useEffect, useMemo, useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { EmptyState } from '@ds/components/EmptyState'
import { LoadingStatus } from '@ds/components/LoadingStatus'
import { classifyApiError } from '../hooks/classifyApiError'
import { useApi } from '../hooks/useApi'
import {
  makeConnectionsApi,
  type ConnectionDirection,
  type FamilyConnectionMineItem,
} from './connectionsApi'
import './guardian.css'

type PageState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; connections: FamilyConnectionMineItem[] }

type PendingAction = 'consent' | 'revoke'

const LOAD_ERROR = 'We could not load your family connections. Please reload.'
const ACTION_ERROR = 'That did not go through. Please try again.'

/**
 * Plain-language explanation of what a connection does, from the caller's
 * own side (ADR-016 ring 2, the cousins case). "viewer" reads books IN from
 * the counterpart; "sharer" sends books OUT to the counterpart.
 */
function directionSummary(direction: ConnectionDirection, counterpart: string): string {
  return direction === 'viewer'
    ? `Your kids can see books the ${counterpart} kids loved.`
    : `The ${counterpart} kids can see books your kids loved.`
}

/**
 * The consequence sentence quoted inside the confirm dialog. Consenting is
 * conditional on the OTHER guardian too (ADR-016 dual-consent), so its
 * copy is framed as "once both families agree"; revoking an active
 * connection takes effect immediately, so that copy says so plainly.
 */
function consequenceCopy(
  connection: FamilyConnectionMineItem,
  action: PendingAction
): string {
  const summary = directionSummary(connection.direction, connection.counterpart_family_name)
  if (action === 'revoke') {
    return connection.active
      ? `${summary} Revoking now will stop this immediately.`
      : `${summary} Revoking removes your side of this connection.`
  }
  return `${summary} This only takes effect once the ${connection.counterpart_family_name} family's guardian agrees too.`
}

function StatusChip({ connection }: { connection: FamilyConnectionMineItem }) {
  if (connection.active) {
    return <span className="connections-chip connections-chip--active">Active</span>
  }
  if (connection.my_consent) {
    return (
      <span className="connections-chip connections-chip--waiting">
        Waiting on the other family
      </span>
    )
  }
  return <span className="connections-chip connections-chip--inactive">Not active</span>
}

/**
 * Guardian consent console for cross-family recommendation connections
 * (ADR-016 ring 2, register G17). Connections themselves are set up by the
 * app admin (the cousins case: an admin links two families on request); this
 * page is where a guardian actually turns their family's side on or off.
 * Nothing flows until BOTH families' guardians have consented, and either
 * side may revoke at any time, which deactivates the connection immediately.
 */
export function ConnectionsPage() {
  const api = useApi()
  const connectionsApi = useMemo(() => makeConnectionsApi(api), [api])
  const [state, setState] = useState<PageState>({ kind: 'loading' })
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({})
  const [confirming, setConfirming] = useState<{
    connection: FamilyConnectionMineItem
    action: PendingAction
  } | null>(null)

  // Mount-time load only: nothing on this page re-fetches the whole list
  // afterward (a consent/revoke action patches its own row in place from the
  // response body), so unlike ReadingPage.tsx this needs no reusable,
  // externally-callable `load`. The async function is therefore inlined
  // directly in the effect body, not hoisted to a useCallback invoked via
  // `void load()`: an effect body must not call an outside setState-calling
  // function directly (react-hooks/set-state-in-effect); see
  // ModerationThresholdsPage.tsx and LibraryPage.tsx for the same fix.
  // #ASSUME: timing dependencies: `cancelled` guards both setState calls so
  // an unmount before the request resolves never writes state on a gone
  // component.
  // #VERIFY: ConnectionsPage.test.tsx covers the ready and error states.
  useEffect(() => {
    let cancelled = false
    async function load() {
      setState({ kind: 'loading' })
      try {
        const connections = await connectionsApi.listMine()
        if (!cancelled) setState({ kind: 'ready', connections })
      } catch (err) {
        console.error('connections load failed:', err instanceof Error ? err.message : err)
        if (!cancelled) {
          setState({
            kind: 'error',
            message: classifyApiError(err, { transient: LOAD_ERROR, server: LOAD_ERROR })
              .message,
          })
        }
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [connectionsApi])

  async function runAction(
    connection: FamilyConnectionMineItem,
    action: PendingAction
  ): Promise<void> {
    if (pendingId !== null) return
    setPendingId(connection.id)
    setRowErrors((prev) => {
      if (!(connection.id in prev)) return prev
      const next = { ...prev }
      delete next[connection.id]
      return next
    })
    try {
      const updated =
        action === 'consent'
          ? await connectionsApi.consent(connection.id)
          : await connectionsApi.revoke(connection.id)
      setState((prev) =>
        prev.kind === 'ready'
          ? {
              kind: 'ready',
              connections: prev.connections.map((c) => (c.id === updated.id ? updated : c)),
            }
          : prev
      )
    } catch (err) {
      console.error(
        'connection consent action failed:',
        err instanceof Error ? err.message : err
      )
      setRowErrors((prev) => ({ ...prev, [connection.id]: ACTION_ERROR }))
    } finally {
      setPendingId(null)
    }
  }

  function confirmAndClose(): void {
    if (confirming === null) return
    const { connection, action } = confirming
    setConfirming(null)
    void runAction(connection, action)
  }

  if (state.kind === 'loading') {
    return (
      <LoadingStatus>Loading your family connections…</LoadingStatus>
    )
  }

  if (state.kind === 'error') {
    return (
      <p role="alert" className="connections__error cyo-text-error">
        {state.message}
      </p>
    )
  }

  const { connections } = state

  return (
    <section className="connections">
      <h1>Connections</h1>
      <p className="connections__intro cyo-text-muted">
        A family connection lets book recommendations flow between two
        families your admin has linked, like cousins sharing favorites. Only
        book titles, ratings, and first names ever cross, and only once both
        families&apos; guardians agree.
      </p>
      {connections.length === 0 ? (
        <EmptyState
          title="No connections yet"
          description="Family connections are set up by the app admin. Once your family is linked to another, it will show up here for you to allow or decline."
        />
      ) : (
        <ul className="connections__list">
          {connections.map((connection) => {
            const isInFlight = pendingId === connection.id
            return (
              <li key={connection.id} className="connections-card cyo-card">
                <div className="connections-card__main">
                  <span className="connections-card__name">
                    {connection.counterpart_family_name}
                  </span>
                  <StatusChip connection={connection} />
                </div>
                <p className="connections-card__summary cyo-text-muted">
                  {directionSummary(connection.direction, connection.counterpart_family_name)}
                </p>
                <div className="connections-card__actions">
                  {connection.my_consent ? (
                    <Button
                      variant="danger"
                      disabled={isInFlight}
                      onClick={() => setConfirming({ connection, action: 'revoke' })}
                    >
                      Revoke
                    </Button>
                  ) : (
                    <Button
                      disabled={isInFlight}
                      onClick={() => setConfirming({ connection, action: 'consent' })}
                    >
                      Allow
                    </Button>
                  )}
                </div>
                {rowErrors[connection.id] ? (
                  <p role="alert" className="connections-card__error cyo-text-error">
                    {rowErrors[connection.id]}
                  </p>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
      {confirming !== null ? (
        <Dialog
          title={confirming.action === 'revoke' ? 'Revoke this connection?' : 'Allow this connection?'}
          onClose={() => setConfirming(null)}
          actions={
            <>
              <Button variant="ghost" onClick={() => setConfirming(null)}>
                Cancel
              </Button>
              <Button
                variant={confirming.action === 'revoke' ? 'danger' : 'primary'}
                onClick={confirmAndClose}
              >
                {confirming.action === 'revoke' ? 'Revoke' : 'Allow'}
              </Button>
            </>
          }
        >
          <p>{consequenceCopy(confirming.connection, confirming.action)}</p>
        </Dialog>
      ) : null}
    </section>
  )
}
