import { useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { classifyApiError } from '../hooks/classifyApiError'
import { AVATARS } from '../profiles/avatars'
import {
  AGE_BANDS,
  type AgeBandValue,
  type ProfileCreateBody,
  type ProfileView,
} from '../profiles/profilesApi'

interface ProfileFormDialogProps {
  title: string
  initial?: ProfileView
  onSubmit: (body: ProfileCreateBody) => Promise<void>
  onClose: () => void
}

/**
 * Shared create/edit form for the guardian Profiles page: name, age band,
 * reading level cap, illustrated avatar, TTS toggle (the fields backing the
 * wireframe 4.1 picker's profiles). Photos are deliberately absent; see the
 * avatar catalog's module docstring.
 */
export function ProfileFormDialog({
  title,
  initial,
  onSubmit,
  onClose,
}: ProfileFormDialogProps) {
  const [displayName, setDisplayName] = useState(initial?.display_name ?? '')
  const [ageBand, setAgeBand] = useState(initial?.age_band ?? '5-8')
  const [cap, setCap] = useState(String(initial?.reading_level_cap ?? 99))
  const [avatar, setAvatar] = useState<string | null>(initial?.avatar ?? null)
  const [tts, setTts] = useState(initial?.tts_enabled ?? false)
  const [saving, setSaving] = useState(false)
  // Classified failure message (null when there is no error). A 403 here is the
  // by-design admin rejection (an admin is not a guardian, so `_require_guardian`
  // returns 403): naive-UX finding G2 saw it read as a transient "try again",
  // which is misleading because retrying can never succeed for this account.
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  async function save() {
    setSaving(true)
    setErrorMsg(null)
    try {
      await onSubmit({
        display_name: displayName,
        age_band: ageBand,
        reading_level_cap: Number(cap),
        avatar,
        tts_enabled: tts,
      })
      onClose()
    } catch (err) {
      console.error('profile save failed', err)
      setErrorMsg(
        classifyApiError(err, {
          forbidden: 'Only a guardian can add child profiles.',
          transient: 'We could not save this profile. Please try again.',
        }).message,
      )
      setSaving(false)
    }
  }

  // Number('') and Number('   ') are both 0, so an emptied cap field would
  // otherwise validate and silently save the most restrictive cap.
  const capNum = Number(cap)
  const valid =
    displayName.trim().length > 0 &&
    cap.trim() !== '' &&
    Number.isFinite(capNum) &&
    capNum >= 0 &&
    capNum <= 99

  return (
    <Dialog
      title={title}
      onClose={onClose}
      actions={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => void save()} disabled={!valid || saving}>
            Save
          </Button>
        </>
      }
    >
      <form
        className="profile-form"
        onSubmit={(e) => {
          e.preventDefault()
          if (valid && !saving) void save()
        }}
      >
        {errorMsg ? (
          <p role="alert" className="profile-form__error cyo-text-error">
            {errorMsg}
          </p>
        ) : null}
        <label className="cyo-field">
          Name
          <input
            className="cyo-field__control"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={120}
            required
          />
        </label>
        <label className="cyo-field">
          Age band
          <select
            className="cyo-field__control"
            value={ageBand}
            onChange={(e) => setAgeBand(e.target.value as AgeBandValue)}
          >
            {AGE_BANDS.map((band) => (
              <option key={band} value={band}>
                {band}
              </option>
            ))}
          </select>
        </label>
        <label className="cyo-field">
          Reading level cap
          <input
            type="number"
            min="0"
            max="99"
            step="0.5"
            className="cyo-field__control"
            value={cap}
            onChange={(e) => setCap(e.target.value)}
            aria-describedby="reading-level-cap-help"
          />
        </label>
        <p id="reading-level-cap-help" className="profile-form__hint">
          99 means no limit.
        </p>
        <fieldset className="profile-form__avatars">
          <legend>Avatar</legend>
          <label className="cyo-field">
            <input
              type="radio"
              name="avatar"
              checked={avatar === null}
              onChange={() => setAvatar(null)}
            />
            None
          </label>
          {AVATARS.map((option) => (
            <label key={option.id} className="cyo-field">
              <input
                type="radio"
                name="avatar"
                checked={avatar === option.id}
                onChange={() => setAvatar(option.id)}
              />
              <img
                className="profile-form__avatar-thumb"
                src={option.src}
                alt=""
                draggable={false}
              />{' '}
              {option.label}
            </label>
          ))}
        </fieldset>
        <label className="cyo-field">
          <input
            type="checkbox"
            checked={tts}
            onChange={(e) => setTts(e.target.checked)}
          />
          Read-aloud (TTS) enabled
        </label>
      </form>
    </Dialog>
  )
}
