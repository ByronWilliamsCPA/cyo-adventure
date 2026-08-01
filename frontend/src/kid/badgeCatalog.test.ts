import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { BADGE_CATALOG } from './badgeCatalog'

const here = path.dirname(fileURLToPath(import.meta.url))
const badgesPyPath = path.resolve(here, '../../../src/cyo_adventure/progress/badges.py')

describe('BADGE_CATALOG', () => {
  it('has exactly 10 entries (the v1 cut line: 9 and 12 trail dependencies)', () => {
    expect(BADGE_CATALOG).toHaveLength(10)
  })

  it('has no duplicate ids', () => {
    const ids = BADGE_CATALOG.map((b) => b.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('every entry has a non-empty name and description', () => {
    for (const entry of BADGE_CATALOG) {
      expect(entry.name.length).toBeGreaterThan(0)
      expect(entry.description.length).toBeGreaterThan(0)
    }
  })

  it('every id appears as a BADGE_CATALOG key in progress/badges.py (drift guard)', () => {
    const source = readFileSync(badgesPyPath, 'utf-8')
    for (const entry of BADGE_CATALOG) {
      expect(source).toContain(`"${entry.id}"`)
    }
  })
})
