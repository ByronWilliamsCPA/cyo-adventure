/**
 * K6 endings tracker, shelf half: a kid-friendly "3 of 7 endings found" line
 * with a decorative dot row underneath the text (the text alone carries the
 * meaning; the dots are aria-hidden). Shown on BookCard for a finished-or-
 * started book once its reading-history row is known.
 */

export interface EndingsBadgeProps {
  found: number
  total: number
}

// #EDGE: UI state: a very long book (many endings) would render a very wide
// dot row on a small phone card.
// #VERIFY: cap the decorative row at this many dots; the text label always
// shows the real numbers regardless, so nothing is ever hidden, only the
// dot visualization degrades to text-only past the cap.
const MAX_DOTS = 10

export function EndingsBadge({ found, total }: EndingsBadgeProps) {
  if (total <= 0) return null
  const clampedFound = Math.max(0, Math.min(found, total))
  const showDots = total <= MAX_DOTS
  return (
    <p className="endings-badge">
      {showDots ? (
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
      ) : null}
      <span className="endings-badge__text">
        {clampedFound} of {total} endings found
      </span>
    </p>
  )
}
