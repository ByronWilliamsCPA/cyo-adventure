import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminLibraryPage } from './AdminLibraryPage'

const mockGet = vi.fn()
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const PUBLISHED = {
  storybook_id: 's1',
  title: 'The Lantern',
  status: 'published',
  version: 2,
  age_band: '6-8',
  family_id: 'fam-1',
  current_published_version: 2,
  created_at: '2026-06-01T00:00:00Z',
  updated_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
  themes: ['friendship'],
  content_flags: { violence: 'none', scariness: 'mild', peril: 'none' },
}
const ARCHIVED = {
  storybook_id: 's2',
  title: 'Old Tale',
  status: 'archived',
  version: 1,
  age_band: null,
  family_id: 'fam-1',
  current_published_version: null,
  created_at: '2026-05-01T00:00:00Z',
  updated_at: null,
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/admin/library']}>
      <Routes>
        <Route path="/admin/library" element={<AdminLibraryPage />} />
        <Route path="/admin/review/:storybookId" element={<div>REVIEW DETAIL</div>} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset().mockResolvedValue({ data: { items: [PUBLISHED, ARCHIVED] } })
})

describe('AdminLibraryPage', () => {
  it('lists stories of any status with their status and links to the detail page', async () => {
    renderPage()
    const lantern = await screen.findByRole('link', { name: /The Lantern/i })
    expect(lantern).toHaveAttribute('href', '/admin/review/s1')
    expect(screen.getByText('Old Tale')).toBeInTheDocument()
    // Row status labels are humanized (scoped to the row, not the filter chips).
    const list = screen.getByRole('list')
    expect(within(list).getByText('Published')).toBeInTheDocument()
    expect(within(list).getByText('Archived')).toBeInTheDocument()
    // The published book shows its age band and a relative update time.
    expect(screen.getByText(/Ages 6-8/)).toBeInTheDocument()
    expect(screen.getByText(/Updated 3 hours ago/i)).toBeInTheDocument()
  })

  it('refetches with the status filter when a chip is selected', async () => {
    renderPage()
    await screen.findByRole('link', { name: /The Lantern/i })
    // Baseline: initial load passes no status.
    expect(mockGet).toHaveBeenLastCalledWith('/v1/admin/storybooks', { params: undefined })

    fireEvent.click(screen.getByRole('button', { name: 'Archived' }))

    await waitFor(() =>
      expect(mockGet).toHaveBeenLastCalledWith('/v1/admin/storybooks', {
        params: { status: 'archived' },
      })
    )
  })

  it('shows a forbidden notice on a 403', async () => {
    mockGet.mockReset().mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    renderPage()
    expect(await screen.findByText(/does not have review access/i)).toBeInTheDocument()
  })

  it('shows an error with retry on a non-403 failure', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockGet.mockReset().mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    renderPage()
    expect(await screen.findByText(/could not load the story library/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
    errorSpy.mockRestore()
  })

  it('shows an empty state when no stories match', async () => {
    mockGet.mockReset().mockResolvedValue({ data: { items: [] } })
    renderPage()
    expect(await screen.findByText(/No stories here/i)).toBeInTheDocument()
  })

  it('opens a book-details dialog with themes and content flags, no moderation row', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /View details for The Lantern/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByText('Ages 6-8')).toBeInTheDocument()
    expect(within(dialog).getByText('friendship')).toBeInTheDocument()
    expect(within(dialog).getByText(/Scariness: mild/)).toBeInTheDocument()
    // The master library's list item carries no screened/flagged_count, so
    // the dialog omits the Moderation row rather than showing a placeholder.
    expect(within(dialog).queryByText('Moderation')).not.toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: /^Close$/ }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('omits age band and themes from the dialog when a story carries neither', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /View details for Old Tale/ }))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByText('Age band')).not.toBeInTheDocument()
    expect(within(dialog).queryByText('Themes')).not.toBeInTheDocument()
  })
})
