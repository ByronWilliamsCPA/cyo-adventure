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

/**
 * Wire mockGet to answer the two endpoints DevicesPage fetches
 * independently and concurrently (device grants, offline downloads) by
 * URL, so a test that only cares about one does not have to know the
 * other's wire shape. Defaults downloads to an empty list; pass
 * `downloads` to override.
 */
function mockDevicesAndDownloads(
  devicesResult: { data: unknown[] } | { error: Error },
  downloads: unknown[] = []
) {
  mockGet.mockImplementation((url: string) => {
    if (url === '/v1/device-downloads') {
      return Promise.resolve({ data: downloads })
    }
    if ('error' in devicesResult) {
      return Promise.reject(devicesResult.error)
    }
    return Promise.resolve({ data: devicesResult.data })
  })
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
    mockDevicesAndDownloads({ data: [] })
    renderPage()
    expect(await screen.findByText('No devices authorized yet')).toBeInTheDocument()
  })

  it('tells the guardian revocation stops new sessions but not an open one', async () => {
    // Pins the corrected copy against the actual backend behavior: revoking
    // clears the DEVICE token immediately, but `api/deps.py::_child_principal`
    // does no database round-trip, so a child session already minted on that
    // device authenticates for the rest of its 12-hour TTL
    // (`child_session_ttl_seconds`). Reconnecting is NOT the cut-off event.
    // See ADR-014 "Negative / risks" and UW-A43.
    mockDevicesAndDownloads({ data: [] })
    renderPage()

    const intro = await screen.findByText(/Every device authorized for your family/)
    expect(intro).toHaveTextContent(/stops it from starting any new reading sessions right away/)
    expect(intro).toHaveTextContent(/keep going for up to 12 hours/)
    expect(intro).not.toHaveTextContent(/next time it connects/)
  })

  it('renders each granted device with its label and grant date', async () => {
    mockDevicesAndDownloads({ data: [KITCHEN_TABLET] })
    renderPage()
    expect(await screen.findByText('Kitchen tablet')).toBeInTheDocument()
    const card = screen.getByText('Kitchen tablet').closest('li')
    expect(card).not.toBeNull()
    expect(within(card as HTMLElement).getByText(/Granted/)).toBeInTheDocument()
    expect(within(card as HTMLElement).getByRole('button', { name: 'Revoke' })).toBeInTheDocument()
  })

  it('falls back to a placeholder name for an unlabeled device', async () => {
    mockDevicesAndDownloads({ data: [UNLABELED_GRANT] })
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
    mockDevicesAndDownloads({ data: [KITCHEN_TABLET, UNLABELED_GRANT] })
    renderPage()

    const thisDeviceCard = (await screen.findByText('Kitchen tablet')).closest('li')
    expect(thisDeviceCard).not.toBeNull()
    expect(within(thisDeviceCard as HTMLElement).getByText('This device')).toBeInTheDocument()

    const otherCard = screen.getByText('Unnamed device').closest('li')
    expect(otherCard).not.toBeNull()
    expect(within(otherCard as HTMLElement).queryByText('This device')).not.toBeInTheDocument()
  })

  it('shows a load error when the device list fails to fetch', async () => {
    mockDevicesAndDownloads({
      error: Object.assign(new Error('boom'), { response: { status: 500 } }),
    })
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'We could not load your family’s devices. Please reload.'
    )
  })

  it('revoking opens a confirm dialog, then deletes and removes the row on confirm', async () => {
    const user = userEvent.setup()
    mockDevicesAndDownloads({ data: [KITCHEN_TABLET] })
    mockDelete.mockResolvedValue({ data: undefined })
    renderPage()

    await screen.findByText('Kitchen tablet')
    await user.click(screen.getByRole('button', { name: 'Revoke' }))

    const dialog = await screen.findByRole('dialog', { name: 'Revoke this device?' })
    expect(
      within(dialog).getByText(/Kitchen tablet will not be able to start a new reading session/)
    ).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Revoke' }))

    expect(mockDelete).toHaveBeenCalledWith('/v1/device-grants/grant-1')
    expect(await screen.findByText('No devices authorized yet')).toBeInTheDocument()
  })

  it('cancelling the dialog leaves the device list untouched', async () => {
    const user = userEvent.setup()
    mockDevicesAndDownloads({ data: [KITCHEN_TABLET] })
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
    mockDevicesAndDownloads({ data: [KITCHEN_TABLET] })
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

  describe('downloads section (G15)', () => {
    it('shows the empty state when nothing is downloaded', async () => {
      mockDevicesAndDownloads({ data: [] }, [])
      renderPage()
      expect(await screen.findByText('No books downloaded yet')).toBeInTheDocument()
    })

    it('groups downloads by device and shows the book title and child name', async () => {
      mockDevicesAndDownloads({ data: [] }, [
        {
          id: 'row-1',
          device_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
          profile_id: 'p1',
          profile_name: 'Maya',
          storybook_id: 's1',
          storybook_title: 'The Lighthouse Mystery',
          downloaded_at: '2026-08-01T00:00:00Z',
          last_confirmed_at: '2026-08-09T00:00:00Z',
        },
      ])
      renderPage()

      expect(await screen.findByText('Device …eeeeee')).toBeInTheDocument()
      expect(screen.getByText('The Lighthouse Mystery')).toBeInTheDocument()
      expect(screen.getByText(/Maya/)).toBeInTheDocument()
    })

    it('falls back to the storybook id when no title is known', async () => {
      mockDevicesAndDownloads({ data: [] }, [
        {
          id: 'row-1',
          device_id: 'device-1',
          profile_id: 'p1',
          profile_name: 'Maya',
          storybook_id: 's_unpublished',
          storybook_title: null,
          downloaded_at: '2026-08-01T00:00:00Z',
          last_confirmed_at: '2026-08-09T00:00:00Z',
        },
      ])
      renderPage()
      expect(await screen.findByText('s_unpublished')).toBeInTheDocument()
    })

    it('shows a load error independently of the device list succeeding', async () => {
      mockGet.mockImplementation((url: string) => {
        if (url === '/v1/device-downloads') {
          return Promise.reject(Object.assign(new Error('boom'), { response: { status: 500 } }))
        }
        return Promise.resolve({ data: [KITCHEN_TABLET] })
      })
      renderPage()

      expect(await screen.findByText('Kitchen tablet')).toBeInTheDocument()
      expect(
        await screen.findByText('We could not load your family’s downloaded books.')
      ).toBeInTheDocument()
    })
  })
})
