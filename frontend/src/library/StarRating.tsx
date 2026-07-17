import { useState } from 'react'

export interface StarRatingProps {
  /** Current rating 1-5, or null when unrated. */
  value: number | null
  /** Called with the tapped star's value (1-5). */
  onRate: (value: number) => void
  /** Book title for the accessible group label. */
  bookTitle: string
}

const STARS = [1, 2, 3, 4, 5] as const

/**
 * Kid-sized tap-to-rate star row. Stars are real buttons (44px touch targets
 * via CSS) inside a labelled group; taps must not bubble into the surrounding
 * book-card link, so navigation and rating stay separate gestures. A saved
 * rating gets a brief pulse on the chosen stars as a "got it!" acknowledgment
 * (decorative only; disabled under prefers-reduced-motion in library.css).
 *
 * Ratings cannot be cleared: the backend accepts only 1-5 (POST /v1/ratings,
 * RatingBody value ge=1 le=5) and has no delete endpoint, so tapping the
 * currently-selected star simply re-saves the same value.
 */
export function StarRating({ value, onRate, bookTitle }: StarRatingProps) {
  // The parent flips `value` only after the rating POST lands, so a prop
  // change to a non-null value is the "rating saved" signal. Comparing
  // against the previous prop during render (React's documented "adjusting
  // state" escape hatch, matching RequestStory's anchor handling) avoids a
  // setState-in-effect cascade. Each save bumps pulseSeq, which keys the
  // glyph span below: the remount replays the CSS animation without any
  // animationend bookkeeping, and focus stays on the button itself.
  // Initializing prevValue to the mount value means a book that arrives
  // already rated does not pulse on first render.
  const [prevValue, setPrevValue] = useState(value)
  const [pulseSeq, setPulseSeq] = useState(0)
  if (value !== prevValue) {
    setPrevValue(value)
    if (value !== null) setPulseSeq((seq) => seq + 1)
  }
  return (
    <div className="star-rating" role="group" aria-label={`Rate ${bookTitle}`}>
      {STARS.map((star) => {
        const filled = value !== null && star <= value
        const pulsing = filled && pulseSeq > 0
        return (
          <button
            key={star}
            type="button"
            className={filled ? 'star-rating__star star-rating__star--filled' : 'star-rating__star'}
            aria-pressed={value === star}
            aria-label={`Rate ${star} ${star === 1 ? 'star' : 'stars'}`}
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              onRate(star)
            }}
          >
            <span
              key={pulseSeq}
              className={
                pulsing ? 'star-rating__glyph star-rating__glyph--pulse' : 'star-rating__glyph'
              }
            >
              {filled ? '★' : '☆'}
            </span>
          </button>
        )
      })}
    </div>
  )
}
