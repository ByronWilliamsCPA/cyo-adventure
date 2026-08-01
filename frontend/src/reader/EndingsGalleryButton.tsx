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
  profileId,
  storybookId,
  bookTitle,
  api,
}: EndingsGalleryButtonProps) {
  const [open, setOpen] = useState(false)
  const [book, setBook] = useState<BookProgressCard | null>(null)
  const [loading, setLoading] = useState(false)
  // Distinguishes "loaded, nothing collected yet" from "could not load at
  // all". Both leave `book` null, but only the first should show the
  // gallery's "Keep reading" copy; see the `unavailable` prop's own note.
  const [failed, setFailed] = useState(false)

  // The modal opens only once the fetch settles: rendering it mid-flight
  // with zero endings would flash the gallery's "keep reading" empty-state
  // copy at a child whose real collection just has not loaded yet. The
  // button disables while loading so a double-tap cannot stack fetches.
  const handleOpen = () => {
    setLoading(true)
    setFailed(false)
    api
      .getProgress()
      .then((progress) => {
        setBook(progress.books.find((b) => b.storybook_id === storybookId) ?? null)
      })
      .catch((error: unknown) => {
        // Best-effort, decorative surface: never an error the child has to
        // dismiss. But it must not be reported as an EMPTY collection either.
        // #ASSUME: external-resources: `/v1/me/progress` is child-principal
        // only, so a guardian previewing as their child gets a 403 here, and
        // a real child gets a transient failure on a slow network. Reporting
        // either as "no endings found yet" tells a child who just finished
        // the book that they have collected nothing.
        // #VERIFY: EndingsGalleryButton.test.tsx "shows a could-not-load
        // message rather than the empty state when the progress fetch fails".
        console.error('[reader] endings gallery fetch failed', {
          profileId,
          storybookId,
          error,
        })
        setBook(null)
        setFailed(true)
      })
      .finally(() => {
        setLoading(false)
        setOpen(true)
      })
  }

  return (
    <>
      <button
        type="button"
        className="reader-ending__gallery-button"
        data-testid="open-endings-gallery"
        onClick={handleOpen}
        disabled={loading}
      >
        See your endings
      </button>
      {open ? (
        <EndingsGallery
          open={open}
          onClose={() => setOpen(false)}
          bookTitle={bookTitle}
          totalEndings={book?.total_endings ?? 0}
          foundEndings={book?.found_endings ?? []}
          unavailable={failed}
        />
      ) : null}
    </>
  )
}
