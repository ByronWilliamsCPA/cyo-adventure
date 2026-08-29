/**
 * Reader (not role) persona substrate. Task C2.
 *
 * "Persona" means two different things in this tier and they must not be
 * confused: `personas.ts` (this directory) holds three ROLE personas (kid,
 * guardian, admin) that are walk drivers (session setup, entry point,
 * recognised terminals). This module instead loads the ten fixed,
 * age-banded READER personas (emerging/average/strong/reluctant readers
 * across the app's bands) from the canonical fixture at
 * schema/personas/reader_personas.json. The two are unrelated data; this
 * module does not touch personas.ts or its exports.
 *
 * The fixture lives under schema/, not tests/fixtures/, because it already
 * has a proven, working example of exactly this problem: schema/conformance/
 * player_traces.json is read by both the backend pytest suite
 * (tests/unit/test_player_conformance.py) and this frontend (frontend/
 * e2e/support/fixtures.ts, frontend/src/player/*.test.ts), with no copy.
 * tests/fixtures/ has no such precedent: every existing consumer there is
 * Python-only (conftest.py fixtures). schema/personas/reader_personas.json
 * follows the proven pattern instead of the Python-only one, so the future
 * agentic runner under tools/usersim-agent/ (task D2, may be Python or
 * Node) can read the identical file this module reads.
 *
 * `resolveJsonModule` is not set in any of this frontend's tsconfigs, so a
 * static `import data from './x.json'` will not compile; that is confirmed,
 * not assumed, and is not being changed here (see the task report for why).
 * This module reads the file at runtime with node:fs and validates the
 * parsed JSON by hand instead. `JSON.parse` returns `any`; this branch
 * already shipped a Critical defect from an `as { ... }` cast over parsed
 * JSON that let a wrong field path type-check while being permanently
 * `undefined`. Nothing in this module casts a parsed value to a shape
 * without having already checked it field by field: every exported value is
 * built from a local `const` that a user-defined type guard (`value is
 * string`, `value is Record<string, unknown>`) has already narrowed, so
 * there is no point where an unverified shape is asserted away. A malformed
 * or drifted fixture throws at import time, naming the offending persona
 * (by id, or by index if the id itself is what's missing) and field.
 */
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// Type-only import of the OpenAPI-generated client's AgeBand union, the same
// generated artifact ci.yml's `contract` job fails the build on drift
// against (see CLAUDE.md, "The OpenAPI schema is the source of truth").
// KNOWN_AGE_BANDS below is typed `Record<AgeBand, true>`, so if the backend
// ever renames, adds, or removes a band and the client is regenerated, this
// file fails `npm run typecheck` (a missing or excess key) rather than
// silently going stale. frontend/e2e-usersim/support/real-canaries.ts
// already imports this same generated module from this directory, so this
// is an established, working import path, not a new one.
import type { AgeBand } from '../../src/client/types.gen'

const here = path.dirname(fileURLToPath(import.meta.url))

/** Repo-relative: frontend/e2e-usersim/support -> frontend -> repo root -> schema/personas. */
const FIXTURE_PATH = path.resolve(here, '../../../schema/personas/reader_personas.json')

export interface ReaderPersona {
  readonly id: string
  readonly band: string
  readonly reader_type: string
  readonly persona_text: string
  readonly constraints: readonly string[]
}

function fixtureError(message: string): never {
  throw new Error(`reader persona fixture (${FIXTURE_PATH}): ${message}`)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/** Reads and validates one required non-empty-string field, naming `label` and `field` on failure. */
function requireString(record: Record<string, unknown>, field: string, label: string): string {
  const value = record[field]
  if (!isNonEmptyString(value)) {
    fixtureError(`persona "${label}": "${field}" is missing or not a non-empty string`)
  }
  return value
}

/** Reads and validates a required non-empty array of non-empty strings. */
function requireStringArray(
  record: Record<string, unknown>,
  field: string,
  label: string
): string[] {
  const value = record[field]
  if (!Array.isArray(value) || value.length === 0) {
    fixtureError(`persona "${label}": "${field}" is missing or not a non-empty array`)
  }
  return value.map((item: unknown, index: number) => {
    if (!isNonEmptyString(item)) {
      fixtureError(`persona "${label}": "${field}[${index}]" is not a non-empty string`)
    }
    return item
  })
}

/** The only keys a persona object may declare; anything else is a typo or drift. */
const PERSONA_FIELDS = ['id', 'band', 'reader_type', 'persona_text', 'constraints'] as const

/**
 * Rejects any key on `record` that is not in `allowed`, naming `label` and
 * the offending key. TypeScript's structural typing lets a typo'd key
 * (e.g. `"bnad"` beside a correct `band`) type-check fine, since a dropped,
 * unread field is invisible to this consumer. But this fixture has a
 * second, prospective consumer (a Python or Node runner under
 * tools/usersim-agent/, task D2) that will read the raw JSON directly and
 * WILL see the typo this consumer silently swallowed. Rejecting unknown
 * keys here keeps both readers' picture of a persona in agreement.
 */
function rejectUnknownKeys(
  record: Record<string, unknown>,
  label: string,
  allowed: readonly string[]
): void {
  for (const key of Object.keys(record)) {
    if (!allowed.includes(key)) {
      fixtureError(
        `persona "${label}": unexpected key "${key}" (allowed keys: ${allowed.join(', ')})`
      )
    }
  }
}

function validatePersona(candidate: unknown, index: number): ReaderPersona {
  if (!isPlainRecord(candidate)) {
    fixtureError(`personas[${index}] is not an object`)
  }
  // "id" is read (and validated) before it is used as the label in every
  // other field's error message, so a malformed id still names the
  // offending entry by index rather than producing "undefined".
  const idField = candidate.id
  const label = isNonEmptyString(idField) ? idField : `personas[${index}]`
  rejectUnknownKeys(candidate, label, PERSONA_FIELDS)
  const id = requireString(candidate, 'id', label)
  const band = requireString(candidate, 'band', label)
  const readerType = requireString(candidate, 'reader_type', label)
  const personaText = requireString(candidate, 'persona_text', label)
  const constraints = requireStringArray(candidate, 'constraints', label)
  return {
    id,
    band,
    reader_type: readerType,
    persona_text: personaText,
    constraints,
  }
}

function loadReaderPersonas(): ReaderPersona[] {
  const raw: unknown = JSON.parse(readFileSync(FIXTURE_PATH, 'utf-8'))
  if (!isPlainRecord(raw)) {
    fixtureError('root is not an object')
  }
  const personasValue = raw.personas
  if (!Array.isArray(personasValue) || personasValue.length === 0) {
    fixtureError('"personas" is missing or not a non-empty array')
  }
  const personas = personasValue.map((candidate: unknown, index: number) =>
    validatePersona(candidate, index)
  )
  const seenIds = new Set<string>()
  for (const persona of personas) {
    if (seenIds.has(persona.id)) {
      fixtureError(`duplicate persona id "${persona.id}"`)
    }
    seenIds.add(persona.id)
  }
  return personas
}

/**
 * The full fixed reader-persona set, validated at module load. Because this
 * runs at import time, a malformed or drifted fixture throws before
 * Playwright ever collects a test, so `npx playwright test --project=usersim`
 * reports `Error: No tests found.` with a nonzero exit rather than one red
 * test beside passing ones. That is fail-loud working as intended, not a
 * bug in the check.
 */
export const READER_PERSONAS: readonly ReaderPersona[] = loadReaderPersonas()

/**
 * Every age band the backend actually defines
 * (src/cyo_adventure/validator/band_profile.py), sourced from the
 * OpenAPI-generated `AgeBand` type rather than re-typed by hand: a plain
 * object literal assigned to `Record<AgeBand, true>` must supply exactly
 * `AgeBand`'s members, so a backend band rename that reaches the generated
 * client fails `npm run typecheck` here, not just at runtime.
 */
const KNOWN_AGE_BANDS: Record<AgeBand, true> = {
  '3-5': true,
  '5-8': true,
  '8-11': true,
  '10-13': true,
  '13-16': true,
  '16+': true,
}

export const KNOWN_AGE_BAND_LIST: readonly string[] = Object.keys(KNOWN_AGE_BANDS)

/** True if `value` is one of the backend's actual age bands. */
export function isKnownAgeBand(value: string): value is AgeBand {
  return Object.hasOwn(KNOWN_AGE_BANDS, value)
}

/**
 * The four reader types this fixture's own stated purpose names (see the
 * module docstring above: "emerging/average/strong/reluctant readers").
 * Unlike `band`, these are not defined by the backend, so there is no
 * generated type to pin them to; declaring the union here, beside the one
 * paragraph that states the fixture's purpose, is the closest available
 * substitute for that generated-type guarantee. Constraining the
 * vocabulary and asserting coverage gives `reader_type` the same treatment
 * KNOWN_AGE_BANDS above already gives `band`: an out-of-vocabulary value,
 * or the fixture silently losing every persona of one type, both fail
 * loudly instead of passing unnoticed.
 */
export type ReaderType = 'emerging' | 'average' | 'strong' | 'reluctant'

const KNOWN_READER_TYPES: Record<ReaderType, true> = {
  emerging: true,
  average: true,
  strong: true,
  reluctant: true,
}

export const KNOWN_READER_TYPE_LIST: readonly string[] = Object.keys(KNOWN_READER_TYPES)

/** True if `value` is one of this fixture's defined reader types. */
export function isKnownReaderType(value: string): value is ReaderType {
  return Object.hasOwn(KNOWN_READER_TYPES, value)
}
