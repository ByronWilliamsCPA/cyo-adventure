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
 * book-card link, so navigation and rating stay separate gestures.
 */
export function StarRating({ value, onRate, bookTitle }: StarRatingProps) {
  return (
    <div className="star-rating" role="group" aria-label={`Rate ${bookTitle}`}>
      {STARS.map((star) => {
        const filled = value !== null && star <= value
        return (
          <button
            key={star}
            type="button"
            className={filled ? 'star-rating__star star-rating__star--filled' : 'star-rating__star'}
            aria-pressed={value === star}
            aria-label={`${star} ${star === 1 ? 'star' : 'stars'}`}
            onClick={(event) => {
              event.preventDefault()
              event.stopPropagation()
              onRate(star)
            }}
          >
            {filled ? '★' : '☆'}
          </button>
        )
      })}
    </div>
  )
}
