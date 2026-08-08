import { isAxiosError } from 'axios'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'

import { Button } from '@ds/components/Button'

import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'

import {
  ARCHETYPE_ROSTER,
  CHARACTER_LOOKS,
  CHARACTER_NAME_MAX_LENGTH,
  LOOK_LABELS,
  LOOK_SWATCHES,
  makeCharactersApi,
  type CharacterArchetype,
  type CharacterLook,
} from './characterApi'
import './characters.css'

import type { CharacterView } from '../client/types.gen'

export interface CharacterCreatorProps {
  profileId: string
  /** Called once the server confirms the new character was created (and is
   * now the profile's active character). */
  onCreated?: (character: CharacterView) => void
  /**
   * When set, renders a "never mind" affordance that calls this instead of
   * submitting. LibraryPage.tsx passes this when the creator was reached by
   * tapping a book gated on `accepts_character` (see `pendingRead`), so a
   * child who got here by accident has a way back to the shelf; it clears
   * `pendingRead` on the caller's side, which is what un-renders this
   * component. Left undefined for CharacterPicker.tsx's own usage (a
   * profile with zero characters), where creating one is not optional and
   * there is nowhere to "go back" to.
   * #VERIFY: CharacterCreator.test.tsx "renders a way back only when onBack
   * is supplied" / LibraryPage.test.tsx's character-gate suite.
   */
  onBack?: () => void
}

const ARCHETYPE_LABELS: Record<CharacterArchetype, string> = {
  scout: 'Scout',
  guardian: 'Guardian',
  trickster: 'Trickster',
  scholar: 'Scholar',
  healer: 'Healer',
  wildheart: 'Wildheart',
}

const ARCHETYPE_HINTS: Record<CharacterArchetype, string> = {
  scout: 'Finds the way',
  guardian: 'Keeps friends safe',
  trickster: 'Full of clever tricks',
  scholar: 'Loves to learn',
  healer: 'Helps others feel better',
  wildheart: 'Wild and free',
}

function nameTooLongMessage(): string {
  return `That name is a bit long. Try ${CHARACTER_NAME_MAX_LENGTH} letters or fewer.`
}

const NAME_ERROR_ID = 'character-name-error'

/**
 * The accessible name for one look option: its position, then the property
 * that actually distinguishes it. Without the second half the option is
 * announced only by an ordinal, since the swatch itself is an aria-hidden
 * emoji whose spoken name belongs to the platform, not to this app.
 */
function lookLabel(look: string, index: number): string {
  const described = LOOK_LABELS[look]
  return described ? `Look ${index + 1}, ${described}` : `Look ${index + 1}`
}

/**
 * The once-per-profile "make your character" form. Visually a sibling of
 * ProfilePickerPage's tile grid (large tappable cards for archetype and
 * look), even though these are radio choices rather than links.
 *
 * #CRITICAL: security: `name` is free text rendered into story prose. Every
 * safety rule beyond "not empty" and "not over the length limit" (the
 * children's-safety denylist) is enforced ONLY server-side
 * (api/characters.py's naming-violation check); this component must never
 * reimplement any part of that check, since shipping the denylist to the
 * client would publish a map for working around it. The 422 the server
 * returns on a violation is surfaced verbatim, since its message names the
 * specific rule broken, rather than replaced with a generic message.
 * #VERIFY: CharacterCreator.test.tsx "surfaces the server's naming message
 * verbatim on a 422".
 */
export function CharacterCreator({ profileId, onCreated, onBack }: CharacterCreatorProps) {
  const api = useApi()
  // Memoized so its identity is stable across renders (matches
  // CharacterPicker.tsx's own `useMemo(() => makeCharactersApi(api), [api])`
  // pattern); a fresh adapter every render has no correctness cost here (this
  // component has no effect that lists it as a dependency), but keeping the
  // two call sites consistent means the next reader does not have to work out
  // why one memoizes and the other does not.
  const charactersApi = useMemo(() => makeCharactersApi(api), [api])
  const [name, setName] = useState('')
  const [archetype, setArchetype] = useState<CharacterArchetype | null>(null)
  const [look, setLook] = useState<CharacterLook | null>(null)
  const [nameError, setNameError] = useState<string | null>(null)
  const [choiceError, setChoiceError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // Matches the same guard in CharacterPicker.tsx and useActiveCharacter.ts:
  // every post-await state write in this module is gated on the component
  // still being mounted. A child who taps "Start my adventure" and then
  // leaves (KidShell swaps this creator for the library the moment the
  // profile has a character) would otherwise land a setState on an unmounted
  // tree. Harmless in React 19, which dropped the warning, but the point is
  // that the three async surfaces in this feature behave the same way.
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitError(null)
    setChoiceError(null)
    const trimmedName = name.trim()

    // #ASSUME: UI state: this pair of checks is UX-only, not a safety
    // boundary. The server independently enforces 1-32 characters
    // (CharacterName) regardless of what this component does; a slow
    // network or a bypassed client cannot widen that bound.
    // #VERIFY: CharacterCreator.test.tsx "blocks a name over 32 characters
    // client-side and never calls the API".
    if (trimmedName.length > CHARACTER_NAME_MAX_LENGTH) {
      setNameError(nameTooLongMessage())
      return
    }
    if (trimmedName.length === 0) {
      setNameError('Give them a name to get started.')
      return
    }
    setNameError(null)
    if (archetype === null) {
      setChoiceError('Choose a role for your character.')
      return
    }
    if (look === null) {
      setChoiceError('Choose a look for your character.')
      return
    }

    setSubmitting(true)
    try {
      const character = await charactersApi.create({
        profile_id: profileId,
        name: trimmedName,
        archetype,
        look,
      })
      if (!isMountedRef.current) return
      setSubmitting(false)
      onCreated?.(character)
    } catch (err) {
      logApiError('character create failed', err)
      if (!isMountedRef.current) return
      setSubmitting(false)
      const serverMessage = extractNamingViolationMessage(err)
      if (serverMessage) {
        setSubmitError(serverMessage)
        return
      }
      const { kind } = classifyApiError(err)
      setSubmitError(
        kind === 'unauthenticated' || kind === 'forbidden'
          ? 'Ask a grown-up to help with this.'
          : "That didn't work. Let's try again."
      )
    }
  }

  return (
    <form
      className="character-creator"
      onSubmit={(event) => {
        void handleSubmit(event)
      }}
    >
      <h1 className="character-creator__heading">Make your character</h1>
      <p className="character-creator__intro">This character will join you in every book.</p>

      <div className="character-creator__field">
        <label htmlFor="character-name">What&apos;s their name?</label>
        {/* role="alert" announces the message once, when it appears. That
            leaves a child who tabs back to the field afterwards with no
            description of what is wrong, so the field also points at the
            message programmatically (and reports itself invalid) for as long
            as the error stands.
            autoFocus (UX-K8, matching ProfilePickerPage's PIN field): this
            form is always an interposed prompt, either from tapping a gated
            book (LibraryPage.tsx's pendingRead) or from a freshly-created
            profile with no character yet, so the caret should be ready
            without a second tap, and focus landing on a properly labelled
            field is what announces the prompt to assistive tech. */}
        <input
          id="character-name"
          className="character-creator__name-input"
          type="text"
          value={name}
          maxLength={CHARACTER_NAME_MAX_LENGTH}
          autoComplete="off"
          autoFocus
          aria-invalid={nameError !== null}
          aria-describedby={nameError ? NAME_ERROR_ID : undefined}
          onChange={(event) => {
            setName(event.target.value)
            if (nameError) setNameError(null)
          }}
        />
      </div>
      {nameError ? (
        <p id={NAME_ERROR_ID} role="alert" className="character-creator__name-error">
          {nameError}
        </p>
      ) : null}

      <fieldset className="character-creator__field">
        <legend>Choose their role</legend>
        <div
          className="character-creator__archetype-grid"
          role="radiogroup"
          aria-label="Choose their role"
        >
          {ARCHETYPE_ROSTER.map((option) => (
            <label
              key={option}
              className={
                archetype === option ? 'character-tile character-tile--selected' : 'character-tile'
              }
            >
              <input
                type="radio"
                name="character-archetype"
                value={option}
                checked={archetype === option}
                onChange={() => {
                  setArchetype(option)
                  setChoiceError(null)
                }}
              />
              <span className="character-tile__name">{ARCHETYPE_LABELS[option]}</span>
              <span className="character-tile__hint">{ARCHETYPE_HINTS[option]}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="character-creator__field">
        <legend>Choose their look</legend>
        <div
          className="character-creator__look-grid"
          role="radiogroup"
          aria-label="Choose their look"
        >
          {CHARACTER_LOOKS.map((option, index) => (
            <label
              key={option}
              className={
                look === option
                  ? 'character-tile character-tile--look character-tile--selected'
                  : 'character-tile character-tile--look'
              }
            >
              {/* The visible text stays the bare ordinal (the swatch itself
                  is the design), but the accessible name names the color, so
                  the choice does not rest on how a given platform happens to
                  announce the emoji. */}
              <input
                type="radio"
                name="character-look"
                value={option}
                checked={look === option}
                aria-label={lookLabel(option, index)}
                onChange={() => {
                  setLook(option)
                  setChoiceError(null)
                }}
              />
              <span className="character-tile__swatch" aria-hidden="true">
                {LOOK_SWATCHES[option]}
              </span>
              <span className="character-tile__name">Look {index + 1}</span>
            </label>
          ))}
        </div>
      </fieldset>

      {choiceError ? (
        <p role="alert" className="character-creator__choice-error">
          {choiceError}
        </p>
      ) : null}
      {submitError ? (
        <p role="alert" className="character-creator__submit-error">
          {submitError}
        </p>
      ) : null}

      <Button type="submit" variant="primary" size="lg" disabled={submitting}>
        {submitting ? 'Making your character…' : 'Start my adventure'}
      </Button>
      {/* Only rendered when this creator was reached optionally (a gated
          book tap), never for the mandatory empty-profile creation path; see
          the onBack prop doc above. type="button" so it never submits the
          form it sits inside. */}
      {onBack ? (
        <Button type="button" variant="ghost" size="sm" disabled={submitting} onClick={onBack}>
          Never mind, take me back
        </Button>
      ) : null}
    </form>
  )
}

/**
 * Extracts the server's naming-violation message from a 422 response, if
 * that is what the error is. Returns null for every other shape (network
 * error, 401/403, 500, a 422 with no parseable message) so the caller falls
 * back to a generic message instead of guessing at server intent.
 */
function extractNamingViolationMessage(err: unknown): string | null {
  if (!isAxiosError(err) || err.response?.status !== 422) return null
  const data = err.response.data as { message?: unknown } | undefined
  return typeof data?.message === 'string' ? data.message : null
}
