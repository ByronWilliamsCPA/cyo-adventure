/**
 * Ending-screen framing: one short line per ending kind, and which endings
 * lead with "Try a different choice".
 *
 * The line sits under the ending passage. It never refers to a button (the
 * rewind action is hidden on a read with no earlier fork, and the line must
 * still make sense then), never judges the choice the child made, and stays
 * readable by a young reader: short words, one or two short sentences.
 * Owner-editable copy: change the strings here, nothing else depends on them.
 */

import type { Ending, EndingKind } from '../player/types'

export const ENDING_FRAMING: Record<EndingKind, string> = {
  success: 'You did it! Other choices lead to other endings, too.',
  completion: "That's one whole adventure. A different choice tells a different story.",
  discovery: 'What a find! Other paths hide other surprises.',
  setback: 'Not the ending you hoped for? Stories can go lots of ways.',
  capture: 'Caught! A different choice might keep you free.',
  death: 'This path stops here. Other choices lead somewhere new.',
}

const SETBACK_KINDS: ReadonlySet<string> = new Set(['setback', 'death', 'capture'])

/**
 * True for an ending that reads as a loss: negative valence, or a kind that
 * is mechanically a failure. Either signal is enough, because the two
 * disagree on real books (a `discovery` can be negative, a `setback` can be
 * authored neutral) and the cost of leading with "try again" on a borderline
 * ending is low while the cost of a triumphant frame on a loss is the
 * "verdict" feeling this exists to remove.
 */
export function isSetbackEnding(ending: Ending | null | undefined): boolean {
  if (!ending) return false
  return ending.valence === 'negative' || SETBACK_KINDS.has(ending.kind)
}

/** The framing line for an ending, or null when the ending has no known kind. */
export function endingFraming(ending: Ending | null | undefined): string | null {
  if (!ending) return null
  return (ENDING_FRAMING as Record<string, string | undefined>)[ending.kind] ?? null
}
