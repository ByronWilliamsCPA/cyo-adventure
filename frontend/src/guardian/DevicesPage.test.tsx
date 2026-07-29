import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DevicesPage } from './DevicesPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockDelete = vi.fn()
const fakeApi = { get: mockGet, post: mockPost, delete: mockDelete }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const GRANT_KEY = 'device_grant'

const KITCHEN_TABLET = {
  id: 'grant-1',
  label: 'Kitchen tablet',
  created_at: '2026-07-16T12:00:00Z',
}

const UNLABELED_GRANT = {
  id: 'grant-2',
  label: null,
  created_at: '2026-07-15T12:00:00Z',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <DevicesPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockDelete.mockReset()
  localStorage.clear()
})

describe('DevicesPage', () => {
  it('shows the empty state when the family has no authorized devices', async () => {
    mockGet.mockResolvedValue({ data: [] })
    renderPage()
    expect(await screen.findByText('No devices authorized yet')).toBeInTheDocument()
  })

  it('renders each granted device with its label and grant date', async () => {
    mockGet.mockResolvedValue({ data: [KITCHEN_TABLET] })
    renderPage()
    expect(await screen.findByText('Kitchen tablet')).toBeInTheDocument()
    const card = screen.getByText('Kitchen tablet').closest('li')
    expect(card).not.toBeNull()
    expect(within(card as HTMLElement).getByText(/Granted/)).toBeInTheDocument()
    expect(within(card as HTMLElement).getByRole('button', { name: 'Revoke' })).toBeInTheDocument()
  })

  it('falls back to a placeholder name for an unlabeled device', async () => {
    mockGet.mockResolvedValue({ data: [UNLABELED_GRANT] })
    renderPage()
    expect(await screen.findByText('Unnamed device')).toBeInTheDocument()
  })

  it("marks the row matching this browser's stored device grant", async () => {
    localStorage.setItem(
      GRANT_KEY,
      JSON.stringify({
        token: 'tok',
        expiresAt: '2099-01-01T00:00:00Z',
        familyId: 'fam-1',
        id: 'grant-1',
      })
    )
    mockGet.mockResolvedValue({ data: [KITCHEN_TABLET, UNLABELED_GRANT] })
    renderPage()

    const thisDeviceCard = (await screen.findByText('Kitchen tablet')).closest('li')
    expect(thisDeviceCard).not.toBeNull()
    expect(within(thisDeviceCard as HTMLElement).getByText('This device')).toBeInTheDocument()

    const otherCard = screen.getByText('Unnamed device').closest('li')
    expect(otherCard).not.toBeNull()
    expect(within(otherCard as HTMLElement).queryByText('This device')).not.toBeInTheDocument()
  })

  it('shows a load error when the device list fails to fetch', async () => {
    mockGet.mockRejectedValue(Object.assign(new Error('boom'), { response: { status: 500 } }))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'We could not load your family’s devices. Please reload.'
    )
  })

  it('revoking opens a confirm dialog, then deletes and removes the row on confirm', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: [KITCHEN_TABLET] })
    mockDelete.mockResolvedValue({ data: undefined })
    renderPage()

    await screen.findByText('Kitchen tablet')
    await user.click(screen.getByRole('button', { name: 'Revoke' }))

    const dialog = await screen.findByRole('dialog', { name: 'Revoke this device?' })
    expect(within(dialog).getByText(/Kitchen tablet will not be able to read/)).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Revoke' }))

    expect(mockDelete).toHaveBeenCalledWith('/v1/device-grants/grant-1')
    expect(await screen.findByText('No devices authorized yet')).toBeInTheDocument()
  })

  it('cancelling the dialog leaves the device list untouched', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: [KITCHEN_TABLET] })
    renderPage()

    await screen.findByText('Kitchen tablet')
    await user.click(screen.getByRole('button', { name: 'Revoke' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mockDelete).not.toHaveBeenCalled()
    expect(screen.getByText('Kitchen tablet')).toBeInTheDocument()
  })

  it('shows a row error and keeps the device listed when revoke fails', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: [KITCHEN_TABLET] })
    mockDelete.mockRejectedValue(new Error('boom'))
    renderPage()

    await screen.findByText('Kitchen tablet')
    await user.click(screen.getByRole('button', { name: 'Revoke' }))
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Revoke' }))

    expect(
      await screen.findByText('That did not go through. Please try again.')
    ).toBeInTheDocument()
    expect(screen.getByText('Kitchen tablet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Revoke' })).not.toBeDisabled()
  })
})
