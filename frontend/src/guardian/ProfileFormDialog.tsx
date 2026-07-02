import { useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'
import { AVATARS } from '../profiles/avatars'
import {
  AGE_BANDS,
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
 * Shared create/edit form (wireframe 4.1 scope): name, age band, reading
 * level cap, illustrated avatar, TTS toggle. Photos are deliberately absent;
 * see the avatar catalog's module docstring.
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
  const [error, setError] = useState(false)

  async function save() {
    setSaving(true)
    setError(false)
    try {
      await onSubmit({
        display_name: displayName,
        age_band: ageBand,
        reading_level_cap: Number(cap),
        avatar,
        tts_enabled: tts,
      })
      onClose()
    } catch {
      setError(true)
      setSaving(false)
    }
  }

  const capNum = Number(cap)
  const valid =
    displayName.trim().length > 0 &&
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
        {error ? (
          <p role="alert" className="profile-form__error">
            We could not save this profile. Please try again.
          </p>
        ) : null}
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
          <select value={ageBand} onChange={(e) => setAgeBand(e.target.value)}>
            {AGE_BANDS.map((band) => (
              <option key={band} value={band}>
                {band}
              </option>
            ))}
          </select>
        </label>
        <label>
          Reading level cap
          <input
            type="number"
            min="0"
            max="99"
            step="0.5"
            value={cap}
            onChange={(e) => setCap(e.target.value)}
          />
        </label>
        <fieldset className="profile-form__avatars">
          <legend>Avatar</legend>
          <label>
            <input
              type="radio"
              name="avatar"
              checked={avatar === null}
              onChange={() => setAvatar(null)}
            />
            None
          </label>
          {AVATARS.map((option) => (
            <label key={option.id}>
              <input
                type="radio"
                name="avatar"
                checked={avatar === option.id}
                onChange={() => setAvatar(option.id)}
              />
              <span aria-hidden="true">{option.glyph}</span> {option.label}
            </label>
          ))}
        </fieldset>
        <label>
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
