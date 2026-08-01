/**
 * Ending-screen entry point into the Endings Gallery (W3.2). Self-contained:
 * fetches this profile's progress lazily (only once tapped, not on every
 * ending-screen render) and renders the gallery modal for this one book.
 * Reuses `library/EndingsGallery.tsx`, the same component `BookCard` opens
 * from the shelf, so the two entry points can never disagree about a
 * book's collection state.
 */

import { useState } from 'react'

import { EndingsGallery } from '../library/EndingsGallery'
import '../library/library.css'
import type { BookProgressCard, ProgressApi } from '../kid/progressApi'

export interface EndingsGalleryButtonProps {
  profileId: string
  storybookId: string
  bookTitle: string
  api: ProgressApi
}

export function EndingsGalleryButton({
  storybookId,
  bookTitle,
  api,
}: EndingsGalleryButtonProps) {
  const [open, setOpen] = useState(false)
  const [book, setBook] = useState<BookProgressCard | null>(null)
  const [loading, setLoading] = useState(false)

  const handleOpen = () => {
    setOpen(true)
    setLoading(true)
    api
      .getProgress()
      .then((progress) => {
        setBook(progress.books.find((b) => b.storybook_id === storybookId) ?? null)
      })
      .catch((error: unknown) => {
        // Best-effort, decorative surface: a failed fetch just shows the
        // empty-gallery state, never an error the child has to dismiss.
        console.error('[reader] endings gallery fetch failed', { storybookId, error })
        setBook(null)
      })
      .finally(() => setLoading(false))
  }

  return (
    <>
      <button
        type="button"
        className="reader-ending__gallery-button"
        data-testid="open-endings-gallery"
        onClick={handleOpen}
      >
        See your endings
      </button>
      {open ? (
        <EndingsGallery
          open={open}
          onClose={() => setOpen(false)}
          bookTitle={bookTitle}
          totalEndings={book?.total_endings ?? 0}
          foundEndings={loading ? [] : (book?.found_endings ?? [])}
        />
      ) : null}
    </>
  )
}
