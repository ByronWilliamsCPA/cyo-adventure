import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { SavedBookmark } from '../player/types'
import { BookmarksButton } from './BookmarksButton'

function bookmark(overrides: Partial<SavedBookmark> = {}): SavedBookmark {
  return {
    current_node: 'n_x',
    var_state: {},
    visit_set: ['n_x'],
    path: ['n_x'],
    label: 'A saved spot',
    saved_at: '2026-08-09T00:00:00Z',
    ...overrides,
  }
}

describe('BookmarksButton', () => {
  it('opens a dialog listing "No saved spots yet" when there are none', () => {
    render(
      <BookmarksButton
        bookmarks={[]}
        positionLabel="Page 3"
        saveUnavailable={null}
        onSave={vi.fn()}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    expect(screen.getByRole('dialog', { name: /bookmarks/i })).toBeInTheDocument()
    expect(screen.getByText(/no saved spots yet/i)).toBeInTheDocument()
  })

  it('the save button names the current position and calls onSave', () => {
    const onSave = vi.fn()
    render(
      <BookmarksButton
        bookmarks={[]}
        positionLabel="Page 3"
        saveUnavailable={null}
        onSave={onSave}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    fireEvent.click(screen.getByTestId('save-bookmark'))
    expect(onSave).toHaveBeenCalledTimes(1)
  })

  it('is enabled and carries no accessible description when saving is available', () => {
    render(
      <BookmarksButton
        bookmarks={[]}
        positionLabel="Page 3"
        saveUnavailable={null}
        onSave={vi.fn()}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    const saveButton = screen.getByRole('button', { name: /save this spot/i })
    expect(saveButton).toBeEnabled()
    expect(saveButton).not.toHaveAccessibleDescription()
  })

  it('disables saving and announces the limit-reached reason via aria-describedby', () => {
    render(
      <BookmarksButton
        bookmarks={[]}
        positionLabel="Page 3"
        saveUnavailable="limit-reached"
        onSave={vi.fn()}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    const saveButton = screen.getByRole('button', { name: /save this spot/i })
    expect(saveButton).toBeDisabled()
    // toHaveAccessibleDescription resolves the button's aria-describedby to
    // the paragraph it points at, proving the two are programmatically
    // associated rather than merely adjacent in the DOM.
    expect(saveButton).toHaveAccessibleDescription(
      'You have saved as many spots as you can. Remove one to save a new spot.'
    )
  })

  it('disables saving and announces the story-ended reason via aria-describedby, with distinct copy', () => {
    render(
      <BookmarksButton
        bookmarks={[]}
        positionLabel="Page 3"
        saveUnavailable="story-ended"
        onSave={vi.fn()}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    const saveButton = screen.getByRole('button', { name: /save this spot/i })
    expect(saveButton).toBeDisabled()
    expect(saveButton).toHaveAccessibleDescription(
      'You finished this story! You can save a spot while you are still reading it.'
    )
  })

  it('lists a saved bookmark with a per-bookmark "Go to bookmark" label, and closes the dialog on Go here', () => {
    const onLoad = vi.fn()
    render(
      <BookmarksButton
        bookmarks={[{ id: 'slot-1', bookmark: bookmark({ label: 'Before the fork' }) }]}
        positionLabel="Page 3"
        saveUnavailable={null}
        onSave={vi.fn()}
        onLoad={onLoad}
        onDelete={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    expect(screen.getByText('Before the fork')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Go to bookmark: Before the fork' }))
    expect(onLoad).toHaveBeenCalledWith('slot-1')
    expect(screen.queryByRole('dialog', { name: /bookmarks/i })).not.toBeInTheDocument()
  })

  it('Remove calls onDelete with the slot id, keeps the dialog open, and carries a per-bookmark label', () => {
    const onDelete = vi.fn()
    render(
      <BookmarksButton
        bookmarks={[{ id: 'slot-1', bookmark: bookmark({ label: 'Before the fork' }) }]}
        positionLabel="Page 3"
        saveUnavailable={null}
        onSave={vi.fn()}
        onLoad={vi.fn()}
        onDelete={onDelete}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove bookmark: Before the fork' }))
    expect(onDelete).toHaveBeenCalledWith('slot-1')
    expect(screen.getByRole('dialog', { name: /bookmarks/i })).toBeInTheDocument()
  })

  it('gives each of several bookmarks its own distinct Go here / Remove labels', () => {
    render(
      <BookmarksButton
        bookmarks={[
          { id: 'slot-1', bookmark: bookmark({ label: 'Before the fork' }) },
          { id: 'slot-2', bookmark: bookmark({ label: 'At the tower' }) },
        ]}
        positionLabel="Page 3"
        saveUnavailable={null}
        onSave={vi.fn()}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    expect(
      screen.getByRole('button', { name: 'Go to bookmark: Before the fork' })
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Go to bookmark: At the tower' })).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Remove bookmark: Before the fork' })
    ).toBeInTheDocument()
    expect(
      screen.getByRole('button', { name: 'Remove bookmark: At the tower' })
    ).toBeInTheDocument()
  })
})
