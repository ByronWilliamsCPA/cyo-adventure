import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// tokens.css is a plain stylesheet (imported for its side effect elsewhere),
// so it is read as text here rather than imported as a module: this test
// asserts on the source text, not on computed styles.
const tokensCssPath = resolve(dirname(fileURLToPath(import.meta.url)), 'tokens.css')
const tokensCss = readFileSync(tokensCssPath, 'utf8')

/** Every `--custom-property:` declared directly inside the given CSS text. */
function customPropertyNames(css: string): Set<string> {
  return new Set([...css.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((match) => match[1]))
}

describe('tokens.css dark mode', () => {
  it('defines a prefers-color-scheme: dark override block', () => {
    expect(tokensCss).toMatch(/@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{/)
  })

  it('overrides every color custom property :root defines', () => {
    const rootBlock = tokensCss.match(/^:root\s*\{([\s\S]*?)\n\}/m)?.[1]
    const darkBlock = tokensCss.match(
      /@media \(prefers-color-scheme: dark\)\s*\{\s*:root\s*\{([\s\S]*?)\n\s*\}\n\s*\}/,
    )?.[1]
    expect(rootBlock, ':root block not found in tokens.css').toBeTruthy()
    expect(darkBlock, 'dark-mode :root block not found in tokens.css').toBeTruthy()

    const rootProps = customPropertyNames(rootBlock ?? '')
    const darkProps = customPropertyNames(darkBlock ?? '')

    // Non-color tokens (typography, spacing, radius, motion) and the
    // reserved/decorative families (berry, gold, cover-*) are intentionally
    // not re-themed; everything else must have a dark equivalent so a future
    // token addition can't be forgotten in the dark set.
    const intentionallyUnthemed = new Set([
      '--color-berry',
      '--color-berry-light',
      '--color-gold',
      '--cover-forest',
      '--cover-lagoon',
      '--cover-berry',
      '--cover-plum',
      '--cover-sunset',
      '--cover-teal',
      '--font-serif',
      '--font-sans',
      '--font-mono',
      '--text-xs',
      '--text-sm',
      '--text-base',
      '--text-lg',
      '--text-xl',
      '--text-2xl',
      '--text-3xl',
      '--leading-tight',
      '--leading-normal',
      '--leading-relaxed',
      '--weight-normal',
      '--weight-medium',
      '--weight-semibold',
      '--weight-bold',
      '--space-1',
      '--space-2',
      '--space-3',
      '--space-4',
      '--space-5',
      '--space-6',
      '--space-8',
      '--space-10',
      '--space-12',
      '--space-16',
      '--radius-sm',
      '--radius-md',
      '--radius-lg',
      '--radius-xl',
      '--radius-full',
      '--duration-fast',
      '--duration-normal',
      '--duration-slow',
      '--easing-default',
    ])

    const missingFromDark = [...rootProps].filter(
      (name) => !darkProps.has(name) && !intentionallyUnthemed.has(name),
    )
    expect(missingFromDark).toEqual([])

    // Guard the other direction too: the dark block should never define a
    // property :root doesn't have (a typo'd name would silently no-op).
    const unknownInDark = [...darkProps].filter((name) => !rootProps.has(name))
    expect(unknownInDark).toEqual([])
  })
})
