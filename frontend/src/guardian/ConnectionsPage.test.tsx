import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ConnectionsPage } from './ConnectionsPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockDelete = vi.fn()
const fakeApi = { get: mockGet, post: mockPost, delete: mockDelete }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const VIEWER_ITEM = {
  id: 'conn-1',
  direction: 'viewer',
  counterpart_family_id: 'fam-2',
  counterpart_family_name: 'Smith Family',
  my_consent: false,
  active: false,
  created_at: '2026-07-16T12:00:00Z',
}

const SHARER_ACTIVE_ITEM = {
  id: 'conn-2',
  direction: 'sharer',
  counterpart_family_id: 'fam-3',
  counterpart_family_name: 'Jones Family',
  my_consent: true,
  active: true,
  created_at: '2026-07-16T12:00:00Z',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ConnectionsPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockDelete.mockReset()
})

describe('ConnectionsPage', () => {
  it('shows the empty state pointing at the admin when there are no connections', async () => {
    mockGet.mockResolvedValue({ data: { connections: [] } })
    renderPage()
    expect(await screen.findByText('No connections yet')).toBeInTheDocument()
    expect(screen.getByText(/set up by the app admin/)).toBeInTheDocument()
  })

  it('renders a viewer-side connection with its plain-language direction and status', async () => {
    mockGet.mockResolvedValue({ data: { connections: [VIEWER_ITEM] } })
    renderPage()
    expect(await screen.findByText('Smith Family')).toBeInTheDocument()
    const card = screen.getByText('Smith Family').closest('li')
    expect(card).not.toBeNull()
    expect(
      within(card as HTMLElement).getByText(/Your kids can see books the Smith Family kids loved/)
    ).toBeInTheDocument()
    expect(within(card as HTMLElement).getByText('Not active')).toBeInTheDocument()
    expect(within(card as HTMLElement).getByRole('button', { name: 'Allow' })).toBeInTheDocument()
  })

  it('renders a sharer-side active connection with the reverse direction copy', async () => {
    mockGet.mockResolvedValue({ data: { connections: [SHARER_ACTIVE_ITEM] } })
    renderPage()
    expect(await screen.findByText('Jones Family')).toBeInTheDocument()
    const card = screen.getByText('Jones Family').closest('li')
    expect(card).not.toBeNull()
    expect(
      within(card as HTMLElement).getByText(/The Jones Family kids can see books your kids loved/)
    ).toBeInTheDocument()
    expect(within(card as HTMLElement).getByText('Active')).toBeInTheDocument()
    expect(
      within(card as HTMLElement).getByRole('button', { name: 'Revoke' })
    ).toBeInTheDocument()
  })

  it('shows a load error when the family connection list fails to fetch', async () => {
    mockGet.mockRejectedValue(Object.assign(new Error('boom'), { response: { status: 500 } }))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'We could not load your family connections. Please reload.'
    )
  })

  it('consenting opens a confirm dialog, then posts and updates the row on confirm', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { connections: [VIEWER_ITEM] } })
    mockPost.mockResolvedValue({ data: { ...VIEWER_ITEM, my_consent: true } })
    renderPage()

    await screen.findByText('Smith Family')
    await user.click(screen.getByRole('button', { name: 'Allow' }))

    const dialog = await screen.findByRole('dialog', { name: 'Allow this connection?' })
    expect(
      within(dialog).getByText(/only takes effect once the Smith Family family's guardian agrees/)
    ).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Allow' }))

    expect(mockPost).toHaveBeenCalledWith('/v1/family-connections/conn-1/consent')
    expect(await screen.findByRole('button', { name: 'Revoke' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('revoking an active connection warns the change is immediate, then deletes on confirm', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { connections: [SHARER_ACTIVE_ITEM] } })
    mockDelete.mockResolvedValue({
      data: { ...SHARER_ACTIVE_ITEM, my_consent: false, active: false },
    })
    renderPage()

    await screen.findByText('Jones Family')
    await user.click(screen.getByRole('button', { name: 'Revoke' }))

    const dialog = await screen.findByRole('dialog', { name: 'Revoke this connection?' })
    expect(within(dialog).getByText(/Revoking now will stop this immediately/)).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Revoke' }))

    expect(mockDelete).toHaveBeenCalledWith('/v1/family-connections/conn-2/consent')
    expect(await screen.findByRole('button', { name: 'Allow' })).toBeInTheDocument()
  })

  it('cancelling the dialog leaves the connection state untouched', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { connections: [VIEWER_ITEM] } })
    renderPage()

    await screen.findByText('Smith Family')
    await user.click(screen.getByRole('button', { name: 'Allow' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Allow' })).toBeInTheDocument()
  })

  it('shows a row error and keeps the row actionable when the consent call fails', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { connections: [VIEWER_ITEM] } })
    mockPost.mockRejectedValue(new Error('boom'))
    renderPage()

    await screen.findByText('Smith Family')
    await user.click(screen.getByRole('button', { name: 'Allow' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Allow' }))

    expect(await screen.findByText('That did not go through. Please try again.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Allow' })).not.toBeDisabled()
  })
})
