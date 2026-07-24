import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// Read as text, like tokens.test.ts: this asserts on source, not computed
// styles (band-tokens.css is imported for its side effect elsewhere).
const cssPath = resolve(dirname(fileURLToPath(import.meta.url)), 'band-tokens.css')
const css = readFileSync(cssPath, 'utf8')

// Mirrors the six-band vocabulary (cyo_adventure/storybook/models.py AgeBand,
// frontend/src/profiles/profilesApi.ts AGE_BANDS, frontend/src/kid/ageBand.ts
// BAND_TIERS). Kept as an independent literal list, like tokens.test.ts's own
// intentionallyUnthemed set, so a drift in any one place fails a test rather
// than silently rendering an unmapped band as neutral.
const ALL_AGE_BANDS = ['3-5', '5-8', '8-11', '10-13', '13-16', '16+']

// Bands with no `[data-age-band='...']` block: the neutral tier IS the
// :root default, deliberately not repeated in its own selector.
const NEUTRAL_BANDS = new Set(['13-16', '16+'])

describe('band-tokens.css tier coverage', () => {
  it('accounts for every AgeBand literal in a tier selector or as neutral', () => {
    const selectorBands = [...css.matchAll(/\[data-age-band='([^']+)'\]/g)].map(
      (match) => match[1],
    )
    const missing = ALL_AGE_BANDS.filter(
      (band) => !selectorBands.includes(band) && !NEUTRAL_BANDS.has(band),
    )
    expect(missing).toEqual([])

    // The inverse: every band literal actually used in the file must be a
    // real AgeBand value (catches a typo'd selector that would silently
    // never match anything).
    const unknown = selectorBands.filter((band) => !ALL_AGE_BANDS.includes(band))
    expect(unknown).toEqual([])

    // A band the file treats as neutral must not ALSO appear in a tier
    // selector (that would just be dead, contradictory CSS).
    const neutralInSelectors = selectorBands.filter((band) => NEUTRAL_BANDS.has(band))
    expect(neutralInSelectors).toEqual([])
  })

  it('places the reduced-motion overrides after every tier block', () => {
    const tierBlockEnds = [
      ...css.matchAll(/:where\(\[data-age-band='[^{]*\{[^}]*\}/g),
    ].map((match) => (match.index ?? 0) + match[0].length)
    const reducedMotionStart = css.indexOf('@media (prefers-reduced-motion: reduce)')
    const reduceMotionAttrStart = css.indexOf("[data-reduce-motion='true']")

    expect(reducedMotionStart).toBeGreaterThan(-1)
    expect(reduceMotionAttrStart).toBeGreaterThan(-1)
    for (const end of tierBlockEnds) {
      expect(reducedMotionStart).toBeGreaterThan(end)
      expect(reduceMotionAttrStart).toBeGreaterThan(end)
    }
  })
})
