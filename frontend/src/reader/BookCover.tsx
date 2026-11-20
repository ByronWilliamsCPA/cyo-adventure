import { useState } from 'react'

import { coverGradient } from '../library/coverPalette'

export interface BookCoverProps {
  /** Presigned cover URL, or null for the letter tile. */
  coverUrl: string | null
  /** The kid-facing (already resolved) title; its first letter fills the tile. */
  title: string
  /**
   * The string the shelf hashes for the tile colour (BookCard passes the raw
   * library title), so a coverless book keeps the colour the child just saw.
   */
  gradientSeed: string
  size: 'lg' | 'sm'
}

/**
 * The book's cover as the shelf shows it (BookCard): the cover image, or the
 * same letter-on-gradient tile when there is no cover or it fails to load.
 * Decorative only (aria-hidden): the title is always rendered as text beside
 * it, so the image adds nothing a screen reader needs.
 *
 * #ASSUME: external-resources: cover URLs are presigned and expire, and an
 * offline device cannot fetch them at all; the image's onError is the only
 * signal of either, so it must swap in the tile rather than leave a broken
 * image icon on a child's title page.
 * #VERIFY: BookCover.test.tsx "falls back to the letter tile when the cover
 * fails to load".
 */
export function BookCover({ coverUrl, title, gradientSeed, size }: BookCoverProps) {
  // Keyed on the URL that failed, not a bare boolean, so a different URL
  // arriving later (the cached shelf entry resolving after mount) gets its
  // own chance to load.
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  const showImage = coverUrl !== null && failedUrl !== coverUrl
  const base = `reader-cover reader-cover--${size}`
  return (
    <div
      className={showImage ? base : `${base} reader-cover--painted`}
      style={showImage ? undefined : { background: coverGradient(gradientSeed) }}
      data-testid="book-cover"
      aria-hidden="true"
    >
      {showImage ? (
        <img
          className="reader-cover__image"
          src={coverUrl}
          alt=""
          decoding="async"
          onError={() => setFailedUrl(coverUrl)}
        />
      ) : (
        <span className="reader-cover__letter">{title.charAt(0).toUpperCase()}</span>
      )}
    </div>
  )
}
