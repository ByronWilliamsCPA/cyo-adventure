/**
 * Deterministic cover colouring for the letter-tile fallback.
 *
 * A book with no cover art still reads as a picture rather than plain text: its
 * first letter sits on a coloured "spine" gradient chosen from the title, so the
 * same book keeps the same colour across renders and sessions. The gradients are
 * defined as `--cover-*` tokens in the design system.
 */

const COVER_TOKENS = [
  'var(--cover-forest)',
  'var(--cover-lagoon)',
  'var(--cover-berry)',
  'var(--cover-plum)',
  'var(--cover-sunset)',
  'var(--cover-teal)',
] as const

/** Stable index into the cover palette derived from the book title. */
export function coverGradient(title: string): string {
  let hash = 0
  for (let i = 0; i < title.length; i += 1) {
    hash = (hash * 31 + title.charCodeAt(i)) % 100000
  }
  return COVER_TOKENS[hash % COVER_TOKENS.length]
}
