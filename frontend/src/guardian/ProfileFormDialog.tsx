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

/**
 * Create-mode submit payload: exactly the create fields. `pin` is
 * unrepresentable here by design: POST /profiles has no pin field
 * (extra=forbid on the backend), so the type keeps a create body that
 * carries one from compiling at all.
 */
export type ProfileFormCreateBody = ProfileCreateBody

/**
 * Edit-mode submit payload: the create fields plus the optional picker-PIN
 * mutation (P6-07). `pin` is present only when the guardian chose to set,
 * change (a 4-8 digit string), or remove (null) the PIN; it is omitted
 * entirely otherwise, matching PATCH's omitted-vs-null semantics.
 */
export interface ProfileFormEditBody extends ProfileCreateBody {
  pin?: string | null
}

interface ProfileFormDialogBaseProps {
  title: string
  onClose: () => void
}

/**
 * Discriminated on `initial`: absent means create mode, whose `onSubmit` can
 * only ever receive a pin-less body; present means edit mode, whose
 * `onSubmit` may receive the PIN mutation. The compiler now enforces what
 * used to be a runtime convention (a create body carrying `pin` was
 * representable but rejected server-side by extra=forbid).
 */
type ProfileFormDialogProps =
  | (ProfileFormDialogBaseProps & {
      initial?: undefined
      onSubmit: (body: ProfileFormCreateBody) => Promise<void>
    })
  | (ProfileFormDialogBaseProps & {
      initial: ProfileView
      onSubmit: (body: ProfileFormEditBody) => Promise<void>
    })

const PIN_SHAPE = /^[0-9]{4,8}$/

type PinChoice = 'keep' | 'set' | 'clear'

/**
 * Shared create/edit form for the guardian Profiles page: name, age band,
 * reading level cap, illustrated avatar, TTS toggle (the fields backing the
 * wireframe 4.1 picker's profiles), and, when editing, the optional picker
 * PIN (set/change/remove). Photos are deliberately absent; see the avatar
 * catalog's module docstring.
 */
export function ProfileFormDialog(props: ProfileFormDialogProps) {
  const { title, initial, onClose } = props
  const [displayName, setDisplayName] = useState(initial?.display_name ?? '')
  const [ageBand, setAgeBand] = useState(initial?.age_band ?? '5-8')
  const [cap, setCap] = useState(String(initial?.reading_level_cap ?? 99))
  const [avatar, setAvatar] = useState<string | null>(initial?.avatar ?? null)
  const [tts, setTts] = useState(initial?.tts_enabled ?? false)
  // Picker-PIN controls (edit mode only). `keep` leaves the stored PIN (or
  // its absence) untouched; the typed value is held only in this state and
  // discarded with the dialog; it is never echoed back by the server.
  const [pinChoice, setPinChoice] = useState<PinChoice>('keep')
  const [pinValue, setPinValue] = useState('')
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
      const base: ProfileFormCreateBody = {
        display_name: displayName,
        age_band: ageBand,
        reading_level_cap: Number(cap),
        avatar,
        tts_enabled: tts,
      }
      // Narrow on the discriminant so create mode structurally cannot emit
      // a pin; only edit mode builds the wider body.
      if (props.initial === undefined) {
        await props.onSubmit(base)
      } else {
        const body: ProfileFormEditBody = { ...base }
        // Include `pin` only for an actual mutation: a string sets/changes,
        // an explicit null removes, and omitting it keeps whatever is stored.
        if (pinChoice === 'set') body.pin = pinValue
        if (pinChoice === 'clear') body.pin = null
        await props.onSubmit(body)
      }
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
  // Mirrors the backend PinCode constraint (4-8 digits) so a bad PIN is
  // caught before the request rather than surfacing as a 422.
  const pinValid = pinChoice !== 'set' || PIN_SHAPE.test(pinValue)
  const valid =
    displayName.trim().length > 0 &&
    cap.trim() !== '' &&
    Number.isFinite(capNum) &&
    capNum >= 0 &&
    capNum <= 99 &&
    pinValid

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
        {initial ? (
          <fieldset className="profile-form__pin">
            <legend>Picker PIN</legend>
            <p className="profile-form__hint">
              {initial.has_pin
                ? 'This profile asks for a PIN on the kid picker.'
                : 'Optionally ask for a 4-8 digit PIN on the kid picker.'}
            </p>
            <label>
              <input
                type="radio"
                name="pin-choice"
                checked={pinChoice === 'keep'}
                onChange={() => setPinChoice('keep')}
              />
              {initial.has_pin ? 'Keep current PIN' : 'No PIN'}
            </label>
            <label>
              <input
                type="radio"
                name="pin-choice"
                checked={pinChoice === 'set'}
                onChange={() => setPinChoice('set')}
              />
              {initial.has_pin ? 'Change PIN' : 'Set a PIN'}
            </label>
            {initial.has_pin ? (
              <label>
                <input
                  type="radio"
                  name="pin-choice"
                  checked={pinChoice === 'clear'}
                  onChange={() => setPinChoice('clear')}
                />
                Remove PIN
              </label>
            ) : null}
            {pinChoice === 'set' ? (
              <label>
                New PIN (4-8 digits)
                {/* password + autoComplete=off: the PIN must never be offered
                    to a password manager or echoed on a shared screen. */}
                <input
                  type="password"
                  inputMode="numeric"
                  autoComplete="off"
                  maxLength={8}
                  value={pinValue}
                  onChange={(e) =>
                    setPinValue(e.target.value.replace(/[^0-9]/g, ''))
                  }
                />
              </label>
            ) : null}
          </fieldset>
        ) : null}
      </form>
    </Dialog>
  )
}
