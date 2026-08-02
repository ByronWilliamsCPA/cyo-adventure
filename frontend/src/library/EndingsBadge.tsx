/**
 * K6 endings tracker, shelf half: a kid-friendly "3 of 7 endings found" line
 * with a decorative dot row underneath the text (the text alone carries the
 * meaning; the dots are aria-hidden). Shown on BookCard for a finished-or-
 * started book once its reading-history row is known.
 *
 * AL-028/W1.3: above `ENDINGS_MILESTONE_THRESHOLD`, the denominator stops
 * being a legible motivator (see `reader/endingsFraming.ts`'s doc), so this
 * drops both the dot row and the "of M" text in favor of "N endings found"
 * only. `EndingsProgress` (the ending-screen half of K6) imports the SAME
 * threshold and framing helpers, so the shelf and the ending screen never
 * disagree about where the switch happens (AL-028's explicit requirement).
 */

import { isLargeEndingCatalog, milestoneBadgeText } from '../reader/endingsFraming'

export interface EndingsBadgeProps {
  found: number
  total: number
}

export function EndingsBadge({ found, total }: EndingsBadgeProps) {
  if (total <= 0) return null
  const clampedFound = Math.max(0, Math.min(found, total))

  if (isLargeEndingCatalog(total)) {
    return (
      <p className="endings-badge">
        <span className="endings-badge__text">{milestoneBadgeText(clampedFound)}</span>
      </p>
    )
  }

  // Below the threshold, `total <= ENDINGS_MILESTONE_THRESHOLD` always holds
  // here (isLargeEndingCatalog just returned false), so the dot row's own
  // display cap can never trigger; it is reused as the shared constant, not
  // duplicated as a separate MAX_DOTS.
  return (
    <p className="endings-badge">
      <span className="endings-badge__dots" aria-hidden="true">
        {Array.from({ length: total }, (_, index) => (
          <span
            key={index}
            className={
              index < clampedFound
                ? 'endings-badge__dot endings-badge__dot--filled'
                : 'endings-badge__dot'
            }
          />
        ))}
      </span>
      <span className="endings-badge__text">
        {clampedFound} of {total} endings found
      </span>
    </p>
  )
}
