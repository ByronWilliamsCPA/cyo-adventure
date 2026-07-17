import { useState } from 'react'

import { classifyApiError } from '../hooks/classifyApiError'
import type { FamilyConnectionView, FamilyView } from '../client/types.gen'
import type { UserManagementApi } from './userManagementApi'

interface ConnectionsTabProps {
  api: UserManagementApi
  families: FamilyView[]
  connections: FamilyConnectionView[]
  onChanged: () => Promise<void>
}

/**
 * Directional cross-family recommendation opt-ins: family_id "views"
 * connected_family_id's recommendations; the reverse direction is a separate
 * row (see db.models.FamilyConnection). No recommendation engine reads this
 * yet -- this is only the admin allowlist.
 */
export function ConnectionsTab({ api, families, connections, onChanged }: ConnectionsTabProps) {
  const [viewerId, setViewerId] = useState('')
  const [sourceId, setSourceId] = useState('')
  const [creating, setCreating] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const canCreate = viewerId.length > 0 && sourceId.length > 0 && viewerId !== sourceId && !creating

  async function create() {
    if (!canCreate) return
    setCreating(true)
    setActionError(null)
    try {
      await api.createConnection({ family_id: viewerId, connected_family_id: sourceId })
      setViewerId('')
      setSourceId('')
      await onChanged()
    } catch (err) {
      console.error('connection create failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          forbidden: 'Only an admin can create family connections.',
          transient: 'We could not create that connection. Please try again.',
        }).message
      )
    } finally {
      setCreating(false)
    }
  }

  async function remove(connectionId: string) {
    setBusyId(connectionId)
    setActionError(null)
    try {
      await api.deleteConnection(connectionId)
      await onChanged()
    } catch (err) {
      console.error('connection delete failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not remove that connection. Please try again.',
        }).message
      )
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section>
      <h2>Family connections</h2>
      <p className="console__muted cyo-text-muted">
        A connection lets one family see recommendations sourced from another. It is one-way:
        connecting A to B does not also connect B to A.
      </p>
      {actionError ? (
        <p role="alert" className="console__error cyo-text-error">
          {actionError}
        </p>
      ) : null}
      {connections.length === 0 ? (
        <p className="console__muted cyo-text-muted">No family connections yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Family</th>
              <th scope="col">Sees recommendations from</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {connections.map((conn) => (
              <tr key={conn.id}>
                <td>{conn.family_name}</td>
                <td>{conn.connected_family_name}</td>
                <td>
                  <button
                    type="button"
                    disabled={busyId === conn.id}
                    onClick={() => void remove(conn.id)}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Add a connection</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void create()
        }}
      >
        <label>
          Family
          <select value={viewerId} onChange={(e) => setViewerId(e.target.value)} required>
            <option value="">Select a family</option>
            {families.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Sees recommendations from
          <select value={sourceId} onChange={(e) => setSourceId(e.target.value)} required>
            <option value="">Select a family</option>
            {families.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
        {viewerId.length > 0 && viewerId === sourceId ? (
          <p role="alert" className="console__error cyo-text-error">
            A family cannot connect to itself.
          </p>
        ) : null}
        <button type="submit" disabled={!canCreate}>
          Create connection
        </button>
      </form>
    </section>
  )
}
