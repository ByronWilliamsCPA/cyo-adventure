import { useState } from 'react'

import { ErrorBanner } from '@ds/components/ErrorBanner'
import { classifyApiError } from '../hooks/classifyApiError'
import type { FamilyView } from '../client/types.gen'
import type { UserManagementApi } from './userManagementApi'

interface FamiliesTabProps {
  api: UserManagementApi
  families: FamilyView[]
  onChanged: () => Promise<void>
}

/**
 * Admin family roster: create, rename, and activate/deactivate. Deactivating
 * cascades server-side to every member guardian/admin/kid; reactivating the
 * family does NOT auto-reactivate them (see api/families.py).
 */
export function FamiliesTab({ api, families, onChanged }: FamiliesTabProps) {
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  async function create() {
    const trimmed = name.trim()
    if (trimmed.length === 0) return
    setCreating(true)
    setActionError(null)
    try {
      await api.createFamily({ name: trimmed })
      setName('')
      await onChanged()
    } catch (err) {
      console.error('family create failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          forbidden: 'Only an admin can create families.',
          transient: 'We could not create that family. Please try again.',
        }).message
      )
    } finally {
      setCreating(false)
    }
  }

  function startEdit(family: FamilyView) {
    setEditingId(family.id)
    setEditName(family.name)
  }

  async function saveEdit(familyId: string) {
    const trimmed = editName.trim()
    if (trimmed.length === 0) return
    setBusy(true)
    setActionError(null)
    try {
      await api.updateFamily(familyId, { name: trimmed })
      setEditingId(null)
      await onChanged()
    } catch (err) {
      console.error('family rename failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not rename that family. Please try again.',
        }).message
      )
    } finally {
      setBusy(false)
    }
  }

  async function toggleStatus(family: FamilyView) {
    setBusy(true)
    setActionError(null)
    try {
      await api.updateFamily(family.id, {
        status: family.status === 'active' ? 'deactivated' : 'active',
      })
      await onChanged()
    } catch (err) {
      console.error('family status change failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not change that family status. Please try again.',
        }).message
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>Families</h2>
      {actionError ? <ErrorBanner className="console__error">{actionError}</ErrorBanner> : null}
      {families.length === 0 ? (
        <p className="console__muted cyo-text-muted">No families yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Status</th>
              <th scope="col">Guardians/admins</th>
              <th scope="col">Kids</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {families.map((family) => (
              <tr key={family.id}>
                <td>
                  {editingId === family.id ? (
                    <input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      aria-label={`Rename ${family.name}`}
                    />
                  ) : (
                    family.name
                  )}
                </td>
                <td>{family.status}</td>
                <td>{family.guardian_count}</td>
                <td>{family.kid_count}</td>
                <td>
                  {editingId === family.id ? (
                    <>
                      <button
                        type="button"
                        disabled={busy || editName.trim().length === 0}
                        onClick={() => void saveEdit(family.id)}
                      >
                        Save
                      </button>
                      <button type="button" disabled={busy} onClick={() => setEditingId(null)}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button type="button" disabled={busy} onClick={() => startEdit(family)}>
                        Rename
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void toggleStatus(family)}
                      >
                        {family.status === 'active' ? 'Deactivate' : 'Reactivate'}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Add a family</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void create()
        }}
      >
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <button type="submit" disabled={creating || name.trim().length === 0}>
          Create family
        </button>
      </form>
    </section>
  )
}
