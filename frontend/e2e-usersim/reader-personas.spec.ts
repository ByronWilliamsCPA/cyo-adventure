/**
 * Task C2's required consumer: a check that goes RED when the reader-persona
 * fixture (schema/personas/reader_personas.json) is wrong, not merely code
 * that reads it. Runs as a non-browser test under the `usersim` Playwright
 * project (this tier's testDir is `./e2e-usersim`), so
 * `npx playwright test --project=usersim` already covers it without
 * widening ci.yml's per-PR `frontend-e2e` job, which only runs the
 * `chromium` project.
 *
 * Four checks:
 * - Referential integrity against the backend (the brief's minimum bar):
 *   every persona's `band` must be one of the age bands
 *   src/cyo_adventure/validator/band_profile.py actually defines, genuinely
 *   failing on drift in either direction (an invented band in the fixture,
 *   or a band renamed on the backend and regenerated into the OpenAPI
 *   client).
 * - Band coverage: every backend band has at least one persona, matching
 *   this fixture's own stated purpose ("... readers across the app's
 *   bands"), cheap to check alongside the first and honest about a second
 *   real way the fixture can silently rot (losing coverage of a band
 *   without inventing a bad one).
 * - Reader-type vocabulary: every persona's `reader_type` must be one of
 *   this fixture's own four defined types (emerging/average/strong/
 *   reluctant), the same referential-integrity treatment `band` gets above.
 * - Reader-type coverage: every one of those four types has at least one
 *   persona, so silently losing every persona of one type is as loud as
 *   losing coverage of a band.
 */
import { expect, test } from '@playwright/test'

import {
  isKnownAgeBand,
  isKnownReaderType,
  KNOWN_AGE_BAND_LIST,
  KNOWN_READER_TYPE_LIST,
  READER_PERSONAS,
} from './support/reader-personas'

test.describe('reader persona fixture (schema/personas/reader_personas.json)', () => {
  test('every persona band is one the backend actually defines', () => {
    for (const persona of READER_PERSONAS) {
      expect(
        isKnownAgeBand(persona.band),
        `persona "${persona.id}" declares band "${persona.band}", which is not a member of the ` +
          `generated AgeBand type (frontend/src/client/types.gen.ts:167): ` +
          `${KNOWN_AGE_BAND_LIST.join(', ')}. That type is regenerated from the OpenAPI schema, ` +
          'which is generated from the backend bands in src/cyo_adventure/validator/band_profile.py.'
      ).toBe(true)
    }
  })

  test('every backend band has at least one persona', () => {
    const coveredBands = new Set(READER_PERSONAS.map((persona) => persona.band))
    for (const band of KNOWN_AGE_BAND_LIST) {
      expect(
        coveredBands.has(band),
        `no reader persona declares band "${band}"; every backend band in ` +
          'src/cyo_adventure/validator/band_profile.py should have at least one persona.'
      ).toBe(true)
    }
  })

  test('every persona reader_type is one this fixture defines', () => {
    for (const persona of READER_PERSONAS) {
      expect(
        isKnownReaderType(persona.reader_type),
        `persona "${persona.id}" declares reader_type "${persona.reader_type}", which is not ` +
          `one of this fixture's reader types (${KNOWN_READER_TYPE_LIST.join(', ')}). See ` +
          'frontend/e2e-usersim/support/reader-personas.ts.'
      ).toBe(true)
    }
  })

  test('every reader type has at least one persona', () => {
    const coveredTypes = new Set(READER_PERSONAS.map((persona) => persona.reader_type))
    for (const type of KNOWN_READER_TYPE_LIST) {
      expect(
        coveredTypes.has(type),
        `no reader persona declares reader_type "${type}"; every reader type this fixture ` +
          'defines should have at least one persona.'
      ).toBe(true)
    }
  })
})
