/**
 * Bookmarks (save-slot feature, Phase 4b, distinct from the Go back undo): a
 * reader can save the current spot under a label, keep reading past it, and
 * jump back to it later. Backed by `ReadingState.save_slots`, which the
 * backend has always persisted, byte-capped, and synced across devices
 * (api/schemas.py's `ReadingStateBody`/`ReadingStateView`); this is the
 * first client feature to actually write to it (see
 * `player/engine.ts`'s bookmark functions and `ReaderPage.tsx`'s save
 * signature, both updated alongside this component).
 *
 * A pill toggle in the reader chrome, mirroring FlagButton's shape (same
 * "chrome sibling, not a special state" styling convention) but its own
 * dialog: a "Save this spot" action at the top, then the saved list, each
 * with "Go here" and "Remove".
 */

import { useId, useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'

import type { SavedBookmark } from '../player/types'
import './reader.css'

/**
 * Why "Save this spot" is unavailable, or `null` when it is available.
 *
 * Deliberately not a bare `canSave` boolean: the two reasons need different
 * copy, and conflating them is what let the ending screen offer an enabled
 * Save button that the machine's `ended` state has no transition for (it
 * wires LOAD/DELETE_BOOKMARK only, by design -- see `player/machine.ts`).
 * XState drops an unmatched event silently, so the button did nothing at all
 * and said nothing about why.
 */
export type SaveUnavailableReason = 'limit-reached' | 'story-ended'

const SAVE_UNAVAILABLE_COPY: Record<SaveUnavailableReason, string> = {
  'limit-reached': 'You have saved as many spots as you can. Remove one to save a new spot.',
  'story-ended': 'You finished this story! You can save a spot while you are still reading it.',
}

export interface BookmarksButtonProps {
  bookmarks: Array<{ id: string; bookmark: SavedBookmark }>
  /** The current position's display label (e.g. "Page 12"), reused verbatim
   * as the new bookmark's label so saving never prompts for text input --
   * kid-friendly (no reading/typing required) and keeps every bookmark
   * unambiguously tied to a real position in the story. */
  positionLabel: string
  /** `null` when saving is available; otherwise why it is not. */
  saveUnavailable: SaveUnavailableReason | null
  onSave: () => void
  onLoad: (slotId: string) => void
  onDelete: (slotId: string) => void
}

export function BookmarksButton({
  bookmarks,
  positionLabel,
  saveUnavailable,
  onSave,
  onLoad,
  onDelete,
}: BookmarksButtonProps) {
  const [open, setOpen] = useState(false)
  const hintId = useId()

  function goHere(slotId: string) {
    onLoad(slotId)
    setOpen(false)
  }

  return (
    <>
      <button
        type="button"
        className="reader-bookmarks-toggle"
        aria-label="Bookmarks"
        onClick={() => setOpen(true)}
      >
        <span aria-hidden="true">🔖</span>
        Bookmarks
      </button>
      <Dialog
        title="Bookmarks"
        open={open}
        onClose={() => setOpen(false)}
        actions={
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Close
          </Button>
        }
      >
        <Button
          variant="primary"
          disabled={saveUnavailable !== null}
          // Points the disabled button at its own explanation so a screen
          // reader announces the reason on focus, instead of leaving the
          // sibling paragraph as unassociated text a keyboard user may never
          // reach.
          aria-describedby={saveUnavailable !== null ? hintId : undefined}
          onClick={() => onSave()}
          data-testid="save-bookmark"
        >
          <span aria-hidden="true">🔖</span>
          Save this spot ({positionLabel})
        </Button>
        {saveUnavailable !== null && (
          <p className="reader-bookmarks-limit" id={hintId}>
            {SAVE_UNAVAILABLE_COPY[saveUnavailable]}
          </p>
        )}
        {bookmarks.length === 0 ? (
          <p className="reader-bookmarks-empty">No saved spots yet.</p>
        ) : (
          <ul className="reader-bookmarks-list">
            {bookmarks.map(({ id, bookmark }) => (
              <li key={id} className="reader-bookmarks-item">
                <span className="reader-bookmarks-item__label">{bookmark.label}</span>
                <div className="reader-bookmarks-item__actions">
                  <Button
                    variant="ghost"
                    aria-label={`Go to bookmark: ${bookmark.label}`}
                    onClick={() => goHere(id)}
                  >
                    Go here
                  </Button>
                  <Button
                    variant="danger"
                    aria-label={`Remove bookmark: ${bookmark.label}`}
                    onClick={() => onDelete(id)}
                  >
                    Remove
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Dialog>
    </>
  )
}
