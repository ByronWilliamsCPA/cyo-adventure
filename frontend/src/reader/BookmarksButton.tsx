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

import { useState } from 'react'

import { Button } from '@ds/components/Button'
import { Dialog } from '@ds/components/Dialog'

import type { SavedBookmark } from '../player/types'
import './reader.css'

export interface BookmarksButtonProps {
  bookmarks: Array<{ id: string; bookmark: SavedBookmark }>
  /** The current position's display label (e.g. "Page 12"), reused verbatim
   * as the new bookmark's label so saving never prompts for text input --
   * kid-friendly (no reading/typing required) and keeps every bookmark
   * unambiguously tied to a real position in the story. */
  positionLabel: string
  canSave: boolean
  onSave: () => void
  onLoad: (slotId: string) => void
  onDelete: (slotId: string) => void
}

export function BookmarksButton({
  bookmarks,
  positionLabel,
  canSave,
  onSave,
  onLoad,
  onDelete,
}: BookmarksButtonProps) {
  const [open, setOpen] = useState(false)

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
          disabled={!canSave}
          onClick={() => onSave()}
          data-testid="save-bookmark"
        >
          <span aria-hidden="true">🔖</span>
          Save this spot ({positionLabel})
        </Button>
        {!canSave && (
          <p className="reader-bookmarks-limit">
            You have saved as many spots as you can. Remove one to save a new spot.
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
                  <Button variant="ghost" onClick={() => goHere(id)}>
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
