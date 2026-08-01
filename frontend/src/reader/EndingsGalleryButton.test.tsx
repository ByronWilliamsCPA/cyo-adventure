import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ProgressApi, ProgressSummary } from '../kid/progressApi'
import { EndingsGalleryButton } from './EndingsGalleryButton'

const BOOK = {
  storybook_id: 's1',
  title: 'The Lantern Cave',
  endings_found: 2,
  total_endings: 4,
  finished: true,
  every_path_walked: false,
  found_endings: [
    { ending_id: 'e1', title: 'The Treasure Found', valence: 'positive' },
    { ending_id: 'e2', title: 'A Quiet Walk Home', valence: 'neutral' },
  ],
}

function progressWith(books: (typeof BOOK)[]): ProgressSummary {
  return {
    badges: [],
    books,
    totals: { books_finished: 1, endings_found: 2 },
    days_read_this_week: 0,
    lifetime_days_read: 0,
    settings: {
      ring_enabled: false,
      ring_goal_days: 3,
      badges_enabled: true,
      time_capture_paused: false,
    },
  }
}

function apiWith(result: Promise<ProgressSummary>): ProgressApi {
  return { getProgress: vi.fn(() => result) }
}

describe('EndingsGalleryButton', () => {
  it('opens the gallery with the book collection once the fetch settles', async () => {
    const user = userEvent.setup()
    const api = apiWith(Promise.resolve(progressWith([BOOK])))
    render(
      <EndingsGalleryButton
        profileId="p1"
        storybookId="s1"
        bookTitle="The Lantern Cave"
        api={api}
      />
    )
    // The modal must not render mid-flight (it would flash the misleading
    // empty-state copy at a child whose collection just has not loaded yet).
    await user.click(screen.getByTestId('open-endings-gallery'))
    expect(await screen.findByText('The Treasure Found')).toBeInTheDocument()
    expect(screen.getByText('A Quiet Walk Home')).toBeInTheDocument()
    expect(screen.queryByText(/Keep reading/)).not.toBeInTheDocument()
  })

  it('disables the button while the fetch is in flight', async () => {
    const user = userEvent.setup()
    let resolveFetch: (value: ProgressSummary) => void = () => {}
    const api = apiWith(
      new Promise<ProgressSummary>((resolve) => {
        resolveFetch = resolve
      })
    )
    render(<EndingsGalleryButton profileId="p1" storybookId="s1" bookTitle="Book" api={api} />)
    const button = screen.getByTestId('open-endings-gallery')
    await user.click(button)
    expect(button).toBeDisabled()
    resolveFetch(progressWith([BOOK]))
    await waitFor(() => expect(button).not.toBeDisabled())
  })

  it('opens with the empty state and logs profile context when the fetch fails', async () => {
    const user = userEvent.setup()
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    // Pre-attach a catch so the intentionally rejected promise never trips
    // vitest's unhandled-rejection detector; the component attaches its own
    // handler only after the click.
    const rejection = Promise.reject(new Error('offline'))
    rejection.catch(() => {})
    const api = apiWith(rejection)
    render(<EndingsGalleryButton profileId="p1" storybookId="s1" bookTitle="Book" api={api} />)
    await user.click(screen.getByTestId('open-endings-gallery'))
    expect(await screen.findByText(/Keep reading/)).toBeInTheDocument()
    expect(consoleError).toHaveBeenCalledWith(
      '[reader] endings gallery fetch failed',
      expect.objectContaining({ profileId: 'p1', storybookId: 's1' })
    )
    consoleError.mockRestore()
  })

  it('opens with the empty state when the book is not in the progress payload', async () => {
    const user = userEvent.setup()
    const api = apiWith(Promise.resolve(progressWith([])))
    render(<EndingsGalleryButton profileId="p1" storybookId="missing" bookTitle="Book" api={api} />)
    await user.click(screen.getByTestId('open-endings-gallery'))
    expect(await screen.findByText(/Keep reading/)).toBeInTheDocument()
  })
})
