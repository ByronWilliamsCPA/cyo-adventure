import { useState } from 'react'

import { ErrorBanner } from '@ds/components/ErrorBanner'
import { classifyApiError } from '../hooks/classifyApiError'
import { AVATARS } from '../profiles/avatars'
import { AGE_BANDS, type AgeBandValue } from '../profiles/profilesApi'
import type { AdminProfileUpdateBody, AdminProfileView, FamilyView } from '../client/types.gen'
import type { UserManagementApi } from './userManagementApi'

type AvatarValue = NonNullable<AdminProfileUpdateBody['avatar']>

interface KidsTabProps {
  api: UserManagementApi
  families: FamilyView[]
  profiles: AdminProfileView[]
  onChanged: () => Promise<void>
}

const PIN_SHAPE = /^[0-9]{4,8}$/

interface EditState {
  displayName: string
  ageBand: AgeBandValue
  readingLevelCap: string
  avatar: string
  ttsEnabled: boolean
  reduceMotion: boolean
  pinInput: string
}

function familyName(families: FamilyView[], familyId: string): string {
  return families.find((f) => f.id === familyId)?.name ?? familyId
}

/**
 * Admin roster of child profiles across every family. Kept separate from
 * the guardian-scoped Profiles page: an admin can create/edit a profile in
 * ANY family here, whereas a guardian only ever manages their own family's
 * kids. Deactivating hides the profile from its family's own picker and
 * blocks a new reading-session mint (see api/child_sessions.py); a picker
 * PIN is never echoed back once set (write-only, mirrors the guardian
 * profile form).
 */
export function KidsTab({ api, families, profiles, onChanged }: KidsTabProps) {
  const [familyId, setFamilyId] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [ageBand, setAgeBand] = useState<AgeBandValue>(AGE_BANDS[0])
  const [creating, setCreating] = useState(false)

  const [editingId, setEditingId] = useState<string | null>(null)
  const [edit, setEdit] = useState<EditState | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const canCreate = familyId.length > 0 && displayName.trim().length > 0 && !creating

  async function create() {
    if (!canCreate) return
    setCreating(true)
    setActionError(null)
    try {
      await api.createProfile({
        family_id: familyId,
        display_name: displayName.trim(),
        age_band: ageBand,
      })
      setDisplayName('')
      await onChanged()
    } catch (err) {
      console.error('profile create failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          forbidden: 'Only an admin can create a profile in any family.',
          transient: 'We could not create that profile. Please try again.',
        }).message
      )
    } finally {
      setCreating(false)
    }
  }

  function startEdit(profile: AdminProfileView) {
    setEditingId(profile.id)
    setEdit({
      displayName: profile.display_name,
      ageBand: profile.age_band,
      readingLevelCap: String(profile.reading_level_cap),
      avatar: profile.avatar ?? '',
      ttsEnabled: profile.tts_enabled,
      reduceMotion: profile.reduce_motion,
      pinInput: '',
    })
  }

  const editCapNum = edit ? Number(edit.readingLevelCap) : 0
  const editValid =
    edit !== null &&
    edit.displayName.trim().length > 0 &&
    Number.isFinite(editCapNum) &&
    editCapNum >= 0 &&
    editCapNum <= 99 &&
    (edit.pinInput === '' || PIN_SHAPE.test(edit.pinInput))

  async function saveEdit(profileId: string) {
    if (edit === null || !editValid) return
    setBusy(true)
    setActionError(null)
    try {
      await api.updateProfile(profileId, {
        display_name: edit.displayName.trim(),
        age_band: edit.ageBand,
        reading_level_cap: Number(edit.readingLevelCap),
        // The <select> below is constrained to AVATARS' ids (plus the empty
        // "None" option), so this cast is safe: the DOM value can only ever
        // be one of AvatarValue or ''.
        avatar: edit.avatar === '' ? null : (edit.avatar as AvatarValue),
        tts_enabled: edit.ttsEnabled,
        reduce_motion: edit.reduceMotion,
        ...(edit.pinInput !== '' ? { pin: edit.pinInput } : {}),
      })
      setEditingId(null)
      setEdit(null)
      await onChanged()
    } catch (err) {
      console.error('profile update failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not save that profile. Please try again.',
        }).message
      )
    } finally {
      setBusy(false)
    }
  }

  async function clearPin(profileId: string) {
    setBusy(true)
    setActionError(null)
    try {
      await api.updateProfile(profileId, { pin: null })
      await onChanged()
    } catch (err) {
      console.error('profile pin clear failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not remove that PIN. Please try again.',
        }).message
      )
    } finally {
      setBusy(false)
    }
  }

  async function toggleStatus(profile: AdminProfileView) {
    setBusy(true)
    setActionError(null)
    try {
      await api.updateProfile(profile.id, {
        status: profile.status === 'active' ? 'deactivated' : 'active',
      })
      await onChanged()
    } catch (err) {
      console.error('profile status change failed:', err instanceof Error ? err.message : err)
      setActionError(
        classifyApiError(err, {
          transient: 'We could not change that profile status. Please try again.',
        }).message
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>Kids</h2>
      {actionError ? <ErrorBanner className="console__error">{actionError}</ErrorBanner> : null}
      {profiles.length === 0 ? (
        <p className="console__muted cyo-text-muted">No child profiles yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Family</th>
              <th scope="col">Age band</th>
              <th scope="col">Reading cap</th>
              <th scope="col">Has PIN</th>
              <th scope="col">Status</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {profiles.map((profile) => (
              <tr key={profile.id}>
                <td>
                  {editingId === profile.id && edit ? (
                    <input
                      value={edit.displayName}
                      onChange={(e) => setEdit({ ...edit, displayName: e.target.value })}
                      aria-label={`Name for ${profile.display_name}`}
                    />
                  ) : (
                    profile.display_name
                  )}
                </td>
                <td>{familyName(families, profile.family_id)}</td>
                <td>
                  {editingId === profile.id && edit ? (
                    <select
                      value={edit.ageBand}
                      onChange={(e) =>
                        setEdit({ ...edit, ageBand: e.target.value as AgeBandValue })
                      }
                      aria-label={`Age band for ${profile.display_name}`}
                    >
                      {AGE_BANDS.map((b) => (
                        <option key={b} value={b}>
                          {b}
                        </option>
                      ))}
                    </select>
                  ) : (
                    profile.age_band
                  )}
                </td>
                <td>
                  {editingId === profile.id && edit ? (
                    <input
                      type="number"
                      min="0"
                      max="99"
                      step="0.5"
                      value={edit.readingLevelCap}
                      onChange={(e) => setEdit({ ...edit, readingLevelCap: e.target.value })}
                      aria-label={`Reading level cap for ${profile.display_name}`}
                    />
                  ) : (
                    profile.reading_level_cap
                  )}
                </td>
                <td>{profile.has_pin ? 'Yes' : 'No'}</td>
                <td>{profile.status}</td>
                <td>
                  {editingId === profile.id && edit ? (
                    <>
                      <label>
                        Avatar
                        <select
                          value={edit.avatar}
                          onChange={(e) => setEdit({ ...edit, avatar: e.target.value })}
                          aria-label={`Avatar for ${profile.display_name}`}
                        >
                          <option value="">None</option>
                          {AVATARS.map((option) => (
                            <option key={option.id} value={option.id}>
                              {option.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        New PIN
                        <input
                          type="password"
                          inputMode="numeric"
                          autoComplete="off"
                          maxLength={8}
                          value={edit.pinInput}
                          onChange={(e) =>
                            setEdit({
                              ...edit,
                              pinInput: e.target.value.replace(/[^0-9]/g, ''),
                            })
                          }
                          aria-label={`New PIN for ${profile.display_name}`}
                        />
                      </label>
                      <button
                        type="button"
                        disabled={busy || !editValid}
                        onClick={() => void saveEdit(profile.id)}
                      >
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
                      <button type="button" disabled={busy} onClick={() => startEdit(profile)}>
                        Edit
                      </button>
                      {profile.has_pin ? (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void clearPin(profile.id)}
                        >
                          Remove PIN
                        </button>
                      ) : null}
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void toggleStatus(profile)}
                      >
                        {profile.status === 'active' ? 'Deactivate' : 'Reactivate'}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3>Add a kid profile</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void create()
        }}
      >
        <label>
          Family
          <select value={familyId} onChange={(e) => setFamilyId(e.target.value)} required>
            <option value="">Select a family</option>
            {families.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Name
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={120}
            required
          />
        </label>
        <label>
          Age band
          <select value={ageBand} onChange={(e) => setAgeBand(e.target.value as AgeBandValue)}>
            {AGE_BANDS.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={!canCreate}>
          Create profile
        </button>
      </form>
      <p className="console__muted cyo-text-muted">
        Set an avatar or picker PIN from the Edit control after creating the profile.
      </p>
    </section>
  )
}
