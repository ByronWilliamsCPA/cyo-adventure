import { useState } from 'react'

import { Button } from '@ds/components/Button'
import { Chip } from '@ds/components/Chip'
import { Dialog } from '@ds/components/Dialog'
import { classifyApiError } from '../hooks/classifyApiError'
import { AVATARS } from '../profiles/avatars'
import {
  AGE_BANDS,
  CONTENT_FLAG_LEVELS,
  type AgeBandValue,
  type ContentFlagCaps,
  type ContentFlagLevelValue,
  type ProfileCreateBody,
  type ProfileView,
} from '../profiles/profilesApi'
import { ageBandLabel } from './storyRequestOptions'

// Mirrors api/schemas.py's _BANNED_THEMES_MAX / BannedTheme constraints:
// up to 20 themes, each 1-40 characters after trim/lowercase.
const BANNED_THEMES_MAX = 20
const BANNED_THEME_MAX_LENGTH = 40

const CONTENT_FLAG_LABELS: Record<'violence' | 'scariness' | 'peril', string> = {
  violence: 'Violence',
  scariness: 'Scariness',
  peril: 'Peril',
}

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

/** Seeds the "Story requests" section's initial state on edit; see the
 * `envelopeInfo` prop doc below for why this cannot come from `initial`. */
export interface ProfileEnvelopeInfo {
  request_auto_approve: boolean
  monthly_request_envelope: number | null
}

interface ProfileFormDialogBaseProps {
  title: string
  onClose: () => void
  /**
   * The child's current ADR-015 G3 pre-approval settings, when known.
   * ProfileView carries neither field (see profilesApi.ts's
   * ProfileEnvelopeFields doc), so this cannot be derived from `initial`;
   * the only place they round-trip today is GET /v1/families/me/budget's
   * per-child usage rows (budgetApi.ts's ChildEnvelopeUsage), which the
   * caller (ProfilesPage) fetches separately and matches by profile id.
   * Absent (create mode, or a failed/not-yet-loaded budget fetch) seeds the
   * section to its off/no-limit default.
   */
  envelopeInfo?: ProfileEnvelopeInfo
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
 * reading level cap, illustrated avatar (the fields backing the wireframe
 * 4.1 picker's profiles), and, when editing, the optional picker PIN
 * (set/change/remove). Photos are deliberately absent; see the avatar
 * catalog's module docstring.
 */
export function ProfileFormDialog(props: ProfileFormDialogProps) {
  const { title, initial, onClose, envelopeInfo } = props
  const [displayName, setDisplayName] = useState(initial?.display_name ?? '')
  const [ageBand, setAgeBand] = useState(initial?.age_band ?? '5-8')
  const [cap, setCap] = useState(String(initial?.reading_level_cap ?? 99))
  const [avatar, setAvatar] = useState<string | null>(initial?.avatar ?? null)
  const [ttsEnabled, setTtsEnabled] = useState(initial?.tts_enabled ?? false)
  // G2 content controls: '' means "no override" for a flag (defer to the
  // child's age-band ceiling); a set value can only ever tighten that
  // ceiling, never loosen it (enforced server-side in story_requests/brief.py).
  // #ASSUME: data-integrity: content_flag_caps is always present on a
  // ProfileView fetched from the current API, but a stale/mocked profile
  // object may omit it; the extra optional-chain link keeps this dialog from
  // throwing on such a shape (mirrors IntakePage's banned_themes fallback).
  const [violenceCap, setViolenceCap] = useState<ContentFlagLevelValue | ''>(
    initial?.content_flag_caps?.violence ?? ''
  )
  const [scarinessCap, setScarinessCap] = useState<ContentFlagLevelValue | ''>(
    initial?.content_flag_caps?.scariness ?? ''
  )
  const [perilCap, setPerilCap] = useState<ContentFlagLevelValue | ''>(
    initial?.content_flag_caps?.peril ?? ''
  )
  const [bannedThemes, setBannedThemes] = useState<string[]>(initial?.banned_themes ?? [])
  const [themeInput, setThemeInput] = useState('')
  // ADR-015 G3 "Story requests" section. Seeded from envelopeInfo (not
  // `initial`, which cannot carry these fields -- see the prop's doc); a
  // fresh create or a missing envelopeInfo seeds off/no-limit.
  const initialAutoApprove = envelopeInfo?.request_auto_approve ?? false
  const initialEnvelope = envelopeInfo?.monthly_request_envelope ?? null
  const [autoApprove, setAutoApprove] = useState(initialAutoApprove)
  // String state (not number), same rationale as `cap`: an emptied field is
  // the deliberate "no envelope" value, and Number('') === 0 would otherwise
  // read as a real, most-restrictive limit rather than "unset".
  const [envelopeText, setEnvelopeText] = useState(
    initialEnvelope !== null ? String(initialEnvelope) : ''
  )
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

  // Adds the trimmed/lowercased theme-input value as a new banned theme.
  // Mirrors the backend's normalization (api/schemas.py::_normalize_theme)
  // client-side so the chip shown here matches what is actually stored;
  // the server still re-validates and is the source of truth.
  function addTheme() {
    const normalized = themeInput.trim().toLowerCase()
    if (normalized === '' || bannedThemes.includes(normalized)) {
      setThemeInput('')
      return
    }
    if (bannedThemes.length >= BANNED_THEMES_MAX) return
    setBannedThemes((themes) => [...themes, normalized])
    setThemeInput('')
  }

  function removeTheme(theme: string) {
    setBannedThemes((themes) => themes.filter((t) => t !== theme))
  }

  async function save() {
    setSaving(true)
    setErrorMsg(null)
    try {
      const contentFlagCaps: ContentFlagCaps = {
        violence: violenceCap || undefined,
        scariness: scarinessCap || undefined,
        peril: perilCap || undefined,
      }
      // ADR-015 G3: only include these two keys when the guardian actually
      // changed the section from its seeded value. #CRITICAL:
      // external-resources: the live backend does not accept these fields
      // yet (see ProfileEnvelopeFields' doc in profilesApi.ts) -- omitting
      // them whenever the section is untouched keeps an ordinary name/
      // avatar/cap edit working today regardless of that gap; touching the
      // section will 422 until the backend catches up, by design (nothing
      // safe to do client-side about a schema the server does not have yet).
      const trimmedEnvelope = envelopeText.trim()
      const envelopeValue = trimmedEnvelope === '' ? null : Number(trimmedEnvelope)
      const envelopeTouched =
        autoApprove !== initialAutoApprove || envelopeValue !== initialEnvelope
      const base: ProfileFormCreateBody = {
        display_name: displayName,
        age_band: ageBand,
        reading_level_cap: Number(cap),
        avatar,
        tts_enabled: ttsEnabled,
        content_flag_caps: contentFlagCaps,
        banned_themes: bannedThemes,
        ...(envelopeTouched
          ? { request_auto_approve: autoApprove, monthly_request_envelope: envelopeValue }
          : {}),
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
          server: 'We could not save this profile. Please try again.',
        }).message
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
  const nameMissing = displayName.trim().length === 0
  const capInvalid = cap.trim() === '' || !Number.isFinite(capNum) || capNum < 0 || capNum > 99
  // Mirrors the backend's CHECK constraint (monthly_request_envelope IS NULL
  // OR >= 0): blank is always valid (it means "no envelope"), so this only
  // gates a non-blank value that is not a non-negative integer. Checked
  // regardless of whether the toggle is currently on, so a value typed
  // while the toggle was on and left behind after toggling off still blocks
  // Save rather than silently saving something the guardian never approved.
  const envelopeTrimmed = envelopeText.trim()
  const envelopeNum = Number(envelopeTrimmed)
  const envelopeInvalid =
    envelopeTrimmed !== '' &&
    (!Number.isFinite(envelopeNum) || !Number.isInteger(envelopeNum) || envelopeNum < 0)
  const valid = !nameMissing && !capInvalid && pinValid && !envelopeInvalid

  // Names what still blocks Save while it is disabled for missing/invalid
  // inputs (null while saving or once everything is filled). Derived from
  // the same booleans as `valid` so the hint can never contradict the button.
  const missingInputs: string[] = []
  if (nameMissing) missingInputs.push('a name')
  if (capInvalid) missingInputs.push('a reading level from 0 to 99')
  if (!pinValid) missingInputs.push('a 4-8 digit PIN')
  if (envelopeInvalid) missingInputs.push('a monthly auto-approve limit of 0 or more, or blank')
  const saveHint =
    !saving && missingInputs.length > 0 ? `Enter ${missingInputs.join(' and ')} to save.` : null

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
                {ageBandLabel(band)}
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
          Rough reading grade level for stories (2 = early reader, 5 = confident reader). 99 means
          no limit.
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
        <label className="cyo-field cyo-field--checkbox">
          <input
            type="checkbox"
            checked={ttsEnabled}
            onChange={(e) => setTtsEnabled(e.target.checked)}
          />
          Read-aloud
        </label>
        <fieldset className="profile-form__budget">
          <legend>Story requests</legend>
          <label className="cyo-field cyo-field--checkbox">
            <input
              type="checkbox"
              checked={autoApprove}
              onChange={(e) => setAutoApprove(e.target.checked)}
              aria-describedby="auto-approve-help"
            />
            Auto-approve this child&apos;s requests
          </label>
          <p id="auto-approve-help" className="profile-form__hint">
            Requests will start writing immediately, using your monthly budget, up to the limit
            below.
          </p>
          <label className="cyo-field">
            Monthly auto-approve limit
            <input
              type="number"
              min="0"
              step="1"
              className="cyo-field__control"
              value={envelopeText}
              disabled={!autoApprove}
              onChange={(e) => setEnvelopeText(e.target.value)}
              aria-describedby="envelope-help"
            />
          </label>
          <p id="envelope-help" className="profile-form__hint cyo-text-muted">
            {autoApprove && envelopeTrimmed === ''
              ? 'Leave this blank and auto-approve stays off, even with the toggle on above: a limit is required to auto-approve.'
              : "Stories made under auto-approve count toward this limit and your family's overall monthly budget."}
          </p>
        </fieldset>
        <fieldset className="profile-form__content-controls">
          <legend>Content limits</legend>
          <p className="profile-form__hint">
            Leave a limit as &quot;No extra limit&quot; to use the age band&apos;s default; a
            chosen limit can only make stories gentler for this child, never less gentle than the
            age band already allows.
          </p>
          {(['violence', 'scariness', 'peril'] as const).map((flag) => {
            const value = flag === 'violence' ? violenceCap : flag === 'scariness' ? scarinessCap : perilCap
            const setValue =
              flag === 'violence' ? setViolenceCap : flag === 'scariness' ? setScarinessCap : setPerilCap
            return (
              <label key={flag} className="cyo-field">
                {CONTENT_FLAG_LABELS[flag]}
                <select
                  className="cyo-field__control"
                  value={value}
                  onChange={(e) => setValue(e.target.value as ContentFlagLevelValue | '')}
                >
                  <option value="">No extra limit</option>
                  {CONTENT_FLAG_LEVELS.map((level) => (
                    <option key={level} value={level}>
                      {level}
                    </option>
                  ))}
                </select>
              </label>
            )
          })}
          <label className="cyo-field">
            Excluded themes
            <div className="profile-form__theme-input">
              <input
                className="cyo-field__control"
                value={themeInput}
                maxLength={BANNED_THEME_MAX_LENGTH}
                placeholder="e.g. spiders"
                onChange={(e) => setThemeInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addTheme()
                  }
                }}
              />
              <Button
                type="button"
                variant="ghost"
                onClick={addTheme}
                disabled={themeInput.trim() === '' || bannedThemes.length >= BANNED_THEMES_MAX}
              >
                Add
              </Button>
            </div>
          </label>
          {bannedThemes.length > 0 ? (
            <ul className="profile-form__theme-chips">
              {bannedThemes.map((theme) => (
                <li key={theme}>
                  <Chip
                    aria-label={`Remove ${theme}`}
                    onClick={() => removeTheme(theme)}
                  >
                    {theme} ✕
                  </Chip>
                </li>
              ))}
            </ul>
          ) : (
            <p className="profile-form__hint cyo-text-muted">No excluded themes yet.</p>
          )}
        </fieldset>
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
                  onChange={(e) => setPinValue(e.target.value.replace(/[^0-9]/g, ''))}
                />
              </label>
            ) : null}
          </fieldset>
        ) : null}
        {saveHint !== null ? <p className="profile-form__hint cyo-text-muted">{saveHint}</p> : null}
      </form>
    </Dialog>
  )
}
