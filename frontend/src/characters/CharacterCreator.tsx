import { isAxiosError } from 'axios'
import { useState, type FormEvent } from 'react'

import { Button } from '@ds/components/Button'

import { classifyApiError } from '../hooks/classifyApiError'
import { logApiError } from '../hooks/logApiError'
import { useApi } from '../hooks/useApi'

import {
  ARCHETYPE_ROSTER,
  CHARACTER_LOOKS,
  CHARACTER_NAME_MAX_LENGTH,
  makeCharactersApi,
  type CharacterArchetype,
} from './characterApi'
import './characters.css'

import type { CharacterView } from '../client/types.gen'

export interface CharacterCreatorProps {
  profileId: string
  /** Called once the server confirms the new character was created (and is
   * now the profile's active character). */
  onCreated?: (character: CharacterView) => void
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

// Placeholder swatches for the twelve `look` ids (avatar_01..avatar_12).
// This catalog has no illustrated art yet (unlike the profile-level named
// avatar set in profiles/avatars.ts); each swatch just needs to be visually
// distinct so a child can tell the twelve apart. Swap for real artwork
// later without touching CHARACTER_LOOKS' ids or order.
const LOOK_SWATCHES: Record<string, string> = {
  avatar_01: '🔴',
  avatar_02: '🟠',
  avatar_03: '🟡',
  avatar_04: '🟢',
  avatar_05: '🔵',
  avatar_06: '🟣',
  avatar_07: '🟤',
  avatar_08: '⚫',
  avatar_09: '⚪',
  avatar_10: '🔶',
  avatar_11: '🔷',
  avatar_12: '⭐',
}

function nameTooLongMessage(): string {
  return `That name is a bit long. Try ${CHARACTER_NAME_MAX_LENGTH} letters or fewer.`
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
export function CharacterCreator({ profileId, onCreated }: CharacterCreatorProps) {
  const api = useApi()
  const charactersApi = makeCharactersApi(api)
  const [name, setName] = useState('')
  const [archetype, setArchetype] = useState<CharacterArchetype | null>(null)
  const [look, setLook] = useState<string | null>(null)
  const [nameError, setNameError] = useState<string | null>(null)
  const [choiceError, setChoiceError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

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
      setSubmitting(false)
      onCreated?.(character)
    } catch (err) {
      setSubmitting(false)
      logApiError('character create failed', err)
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
        <input
          id="character-name"
          className="character-creator__name-input"
          type="text"
          value={name}
          maxLength={64}
          autoComplete="off"
          onChange={(event) => {
            setName(event.target.value)
            if (nameError) setNameError(null)
          }}
        />
      </div>
      {nameError ? (
        <p role="alert" className="character-creator__name-error">
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
              <input
                type="radio"
                name="character-look"
                value={option}
                checked={look === option}
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
