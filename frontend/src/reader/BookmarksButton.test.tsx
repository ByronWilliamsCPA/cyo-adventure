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
        canSave
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
        canSave
        onSave={onSave}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    fireEvent.click(screen.getByTestId('save-bookmark'))
    expect(onSave).toHaveBeenCalledTimes(1)
  })

  it('disables saving and shows a limit notice when canSave is false', () => {
    render(
      <BookmarksButton
        bookmarks={[]}
        positionLabel="Page 3"
        canSave={false}
        onSave={vi.fn()}
        onLoad={vi.fn()}
        onDelete={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    expect(screen.getByTestId('save-bookmark')).toBeDisabled()
    expect(screen.getByText(/saved as many spots as you can/i)).toBeInTheDocument()
  })

  it('lists saved bookmarks with Go here / Remove, and closes on Go here', () => {
    const onLoad = vi.fn()
    render(
      <BookmarksButton
        bookmarks={[{ id: 'slot-1', bookmark: bookmark({ label: 'Before the fork' }) }]}
        positionLabel="Page 3"
        canSave
        onSave={vi.fn()}
        onLoad={onLoad}
        onDelete={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    expect(screen.getByText('Before the fork')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /go here/i }))
    expect(onLoad).toHaveBeenCalledWith('slot-1')
    expect(screen.queryByRole('dialog', { name: /bookmarks/i })).not.toBeInTheDocument()
  })

  it('Remove calls onDelete with the slot id and keeps the dialog open', () => {
    const onDelete = vi.fn()
    render(
      <BookmarksButton
        bookmarks={[{ id: 'slot-1', bookmark: bookmark({ label: 'Before the fork' }) }]}
        positionLabel="Page 3"
        canSave
        onSave={vi.fn()}
        onLoad={vi.fn()}
        onDelete={onDelete}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /bookmarks/i }))
    fireEvent.click(screen.getByRole('button', { name: /remove bookmark: before the fork/i }))
    expect(onDelete).toHaveBeenCalledWith('slot-1')
    expect(screen.getByRole('dialog', { name: /bookmarks/i })).toBeInTheDocument()
  })
})
