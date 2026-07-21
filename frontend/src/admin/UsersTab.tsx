import { useState } from 'react'

import { ErrorBanner } from '@ds/components/ErrorBanner'
import { classifyApiError } from '../hooks/classifyApiError'
import type { FamilyView, UserView } from '../client/types.gen'
import type { UserManagementApi } from './userManagementApi'

interface UsersTabProps {
  api: UserManagementApi
  families: FamilyView[]
  users: UserView[]
  onChanged: () => Promise<void>
}

const ROLES = ['guardian', 'admin'] as const

interface EditState {
  familyId: string
  role: (typeof ROLES)[number]
  isAdmin: boolean
}

function familyName(families: FamilyView[], familyId: string): string {
  return families.find((f) => f.id === familyId)?.name ?? familyId
}

/**
 * Admin roster of guardian/admin accounts across every family. Creating a
 * user here always invites a pending account (bound to a real Supabase
 * login later, by email match); editing lets an admin reassign family,
 * role, the dual-role capability, or activate/deactivate an account. An
 * admin editing their OWN row is refused server-side (self-lockout guard);
 * the resulting 403 is surfaced with a specific message below rather than
 * the generic "forbidden" copy.
 */
export function UsersTab({ api, families, users, onChanged }: UsersTabProps) {
  const [email, setEmail] = useState('')
  const [newFamilyId, setNewFamilyId] = useState('')
  const [newRole, setNewRole] = useState<(typeof ROLES)[number]>('guardian')
  const [newIsAdmin, setNewIsAdmin] = useState(false)
  const [creating, setCreating] = useState(false)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [edit, setEdit] = useState<EditState | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const canCreate = email.trim().length > 0 && newFamilyId.length > 0 && !creating

  async function create() {
    if (!canCreate) return
    setCreating(true)
    setActionError(null)
    try {
      await api.createUser({
        email: email.trim(),
        family_id: newFamilyId,
        role: newRole,
        is_admin: newIsAdmin,
      })
      setEmail('')
      setNewIsAdmin(false)
      await onChanged()
    } catch (err) {
      console.error('user invite failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          forbidden: 'Only an admin can invite guardians or admins.',
          transient: 'We could not send that invite. Please try again.',
        }).message
      )
    } finally {
      setCreating(false)
    }
  }

  function startEdit(user: UserView) {
    setEditingId(user.id)
    setEdit({ familyId: user.family_id, role: user.role, isAdmin: user.is_admin })
  }

  async function saveEdit(userId: string) {
    if (edit === null) return
    setBusy(true)
    setActionError(null)
    try {
      await api.updateUser(userId, {
        family_id: edit.familyId,
        role: edit.role,
        is_admin: edit.isAdmin,
      })
      setEditingId(null)
      setEdit(null)
      await onChanged()
    } catch (err) {
      console.error('user update failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          forbidden: 'You cannot edit your own account from this page.',
          transient: 'We could not save that change. Please try again.',
        }).message
      )
    } finally {
      setBusy(false)
    }
  }

  async function toggleStatus(user: UserView) {
    if (user.status === 'pending') return
    setBusy(true)
    setActionError(null)
    try {
      await api.updateUser(user.id, {
        status: user.status === 'active' ? 'deactivated' : 'active',
      })
      await onChanged()
    } catch (err) {
      console.error('user status change failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          forbidden: 'You cannot deactivate your own account from this page.',
          transient: 'We could not change that account status. Please try again.',
        }).message
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>Guardians &amp; admins</h2>
      {actionError ? <ErrorBanner className="console__error">{actionError}</ErrorBanner> : null}
      {users.length === 0 ? (
        <p className="console__muted cyo-text-muted">No guardians or admins yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Email</th>
              <th scope="col">Family</th>
              <th scope="col">Role</th>
              <th scope="col">Dual admin</th>
              <th scope="col">Status</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.email ?? '(no email on file)'}</td>
                <td>
                  {editingId === user.id && edit ? (
                    <select
                      value={edit.familyId}
                      onChange={(e) => setEdit({ ...edit, familyId: e.target.value })}
                      aria-label={`Family for ${user.email ?? user.id}`}
                    >
                      {families.map((f) => (
                        <option key={f.id} value={f.id}>
                          {f.name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    familyName(families, user.family_id)
                  )}
                </td>
                <td>
                  {editingId === user.id && edit ? (
                    <select
                      value={edit.role}
                      onChange={(e) => {
                        const role = e.target.value as (typeof ROLES)[number]
                        // Keep the submitted payload consistent with the
                        // force-checked+disabled checkbox below: switching to
                        // 'admin' sets isAdmin in state immediately, not just
                        // visually (the backend also re-forces this, but the
                        // UI should never send a payload it isn't showing).
                        setEdit({ ...edit, role, isAdmin: role === 'admin' ? true : edit.isAdmin })
                      }}
                      aria-label={`Role for ${user.email ?? user.id}`}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  ) : (
                    user.role
                  )}
                </td>
                <td>
                  {editingId === user.id && edit ? (
                    <input
                      type="checkbox"
                      checked={edit.role === 'admin' ? true : edit.isAdmin}
                      disabled={edit.role === 'admin'}
                      onChange={(e) => setEdit({ ...edit, isAdmin: e.target.checked })}
                      aria-label={`Dual admin for ${user.email ?? user.id}`}
                    />
                  ) : user.is_admin ? (
                    'Yes'
                  ) : (
                    'No'
                  )}
                </td>
                <td>{user.status}</td>
                <td>
                  {editingId === user.id ? (
                    <>
                      <button type="button" disabled={busy} onClick={() => void saveEdit(user.id)}>
                        Save
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          setEditingId(null)
                          setEdit(null)
                        }}
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <>
                      <button type="button" disabled={busy} onClick={() => startEdit(user)}>
                        Edit
                      </button>
                      {user.status !== 'pending' ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void toggleStatus(user)}
                        >
                          {user.status === 'active' ? 'Deactivate' : 'Reactivate'}
                        </button>
                      ) : null}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Invite a guardian or admin</h3>
      <p className="console__muted cyo-text-muted">
        Creates a pending invite. It becomes active the first time that email signs in.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void create()
        }}
      >
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Family
          <select value={newFamilyId} onChange={(e) => setNewFamilyId(e.target.value)} required>
            <option value="">Select a family</option>
            {families.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Role
          <select
            value={newRole}
            onChange={(e) => setNewRole(e.target.value as (typeof ROLES)[number])}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={newRole === 'admin' ? true : newIsAdmin}
            disabled={newRole === 'admin'}
            onChange={(e) => setNewIsAdmin(e.target.checked)}
          />
          Also grant admin capability
        </label>
        <button type="submit" disabled={!canCreate}>
          Send invite
        </button>
      </form>
    </section>
  )
}
