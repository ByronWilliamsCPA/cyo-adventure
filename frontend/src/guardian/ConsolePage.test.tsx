import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getDeviceGrant, setDeviceGrant } from '../auth/deviceGrant'
import { ConsolePage } from './ConsolePage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockDelete = vi.fn()
const fakeApi = { get: mockGet, post: mockPost, delete: mockDelete }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const mockUseAuth = vi.fn()
vi.mock('../auth/useAuth', () => ({
  useAuth: (): unknown => mockUseAuth(),
}))

function principal(role: 'guardian' | 'admin', isAdmin = role === 'admin') {
  return { principal: { subject: 's', role, isAdmin, familyId: 'f', profileIds: [] } }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ConsolePage />
    </MemoryRouter>
  )
}

function mockProfiles(profiles: unknown[]) {
  mockGet.mockImplementation((url: string) =>
    url === '/v1/profiles'
      ? Promise.resolve({ data: { profiles } })
      : Promise.reject(new Error(`unexpected GET ${url}`))
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockProfiles([{ id: 'p1' }])
  mockPost.mockReset()
  mockDelete.mockReset()
  mockUseAuth.mockReset()
  mockUseAuth.mockReturnValue(principal('guardian'))
  localStorage.clear()
})

describe('ConsolePage', () => {
  it('renders the family home with quick links for a family with children', async () => {
    renderPage()
    expect(await screen.findByRole('link', { name: /request a story/i })).toHaveAttribute(
      'href',
      '/guardian/intake'
    )
    expect(screen.getByRole('link', { name: /story requests/i })).toHaveAttribute(
      'href',
      '/guardian/requests'
    )
    expect(screen.getByRole('link', { name: /browse and assign books/i })).toHaveAttribute(
      'href',
      '/guardian/books'
    )
    expect(screen.getByRole('link', { name: /manage child profiles/i })).toHaveAttribute(
      'href',
      '/guardian/profiles'
    )
  })

  it('nudges a childless family to add a profile instead of quick links', async () => {
    mockProfiles([])
    renderPage()
    const link = await screen.findByRole('link', { name: /add a child profile/i })
    expect(link).toHaveAttribute('href', '/guardian/profiles')
    expect(screen.queryByRole('link', { name: /request a story/i })).not.toBeInTheDocument()
  })

  it('tells a plain guardian that reviews are handled by the safety reviewer', async () => {
    renderPage()
    expect(await screen.findByText(/safety reviewer/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /admin console/i })).not.toBeInTheDocument()
  })

  it('points a dual-role adult at the admin console', async () => {
    mockUseAuth.mockReturnValue(principal('guardian', true))
    renderPage()
    expect(await screen.findByRole('link', { name: /open the admin console/i })).toHaveAttribute(
      'href',
      '/admin'
    )
  })

  it('still renders quick links when the profiles fetch fails (childCount stays null)', async () => {
    // The onboarding read is best-effort: on failure childCount stays null, so
    // the nudge is suppressed but the quick links (childCount !== 0) still show.
    mockGet.mockRejectedValue(new Error('profiles fetch failed'))
    renderPage()
    expect(await screen.findByRole('link', { name: /request a story/i })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /add a child profile/i })).not.toBeInTheDocument()
  })

  it('does not render the review queue or the request-a-story form here', async () => {
    // Both moved to the admin console (AdminConsolePage / AdminRequestsPage)
    // when admin functions gained their own surface.
    renderPage()
    await screen.findByText(/Family console/)
    expect(screen.queryByText(/review queue/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/what should the story be about/i)).not.toBeInTheDocument()
  })

  it('shows a dedicated message for an admin-only account instead of dead family links', async () => {
    // role='admin', NOT dual: an admin-only adult has no guardian family
    // surface (I4). It must not see the four quick-links (each 403s/empties
    // for this role) or the "add your first reader" onboarding CTA.
    mockUseAuth.mockReturnValue(principal('admin'))
    renderPage()
    expect(await screen.findByText(/no family console for this account/i)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /request a story/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /add a child profile/i })).not.toBeInTheDocument()
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('hides the device-setup section entirely for an admin-only account', async () => {
    mockUseAuth.mockReturnValue(principal('admin'))
    renderPage()
    await screen.findByText(/no family console for this account/i)
    expect(screen.queryByRole('heading', { name: /this device/i })).not.toBeInTheDocument()
  })
})

describe('ConsolePage device authorization (ADR-014 Phase 3)', () => {
  it('offers to set up this device when no grant exists yet', async () => {
    renderPage()
    expect(
      await screen.findByRole('button', { name: /set up this device for your kids/i })
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /re-authorize/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /remove from this device/i })).not.toBeInTheDocument()
  })

  it('mints a device grant and shows the confirmation state', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({
      data: { id: 'grant-1', token: 'tok-1', expires_at: '2099-01-01T00:00:00Z', family_id: 'fam-1' },
    })
    renderPage()

    const setupButton = await screen.findByRole('button', { name: /set up this device for your kids/i })
    await user.click(setupButton)

    expect(await screen.findByText(/kids can now read here/i)).toBeInTheDocument()
    expect(mockPost).toHaveBeenCalledWith('/v1/device-grants', undefined)
    expect(getDeviceGrant()).toEqual({
      token: 'tok-1',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    })
    expect(screen.getByRole('button', { name: /re-authorize this device/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /remove from this device/i })).toBeInTheDocument()
  })

  it('shows an error and keeps the setup button when the mint call fails', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue(new Error('mint failed'))
    renderPage()

    const setupButton = await screen.findByRole('button', { name: /set up this device for your kids/i })
    await user.click(setupButton)

    expect(await screen.findByRole('alert')).toHaveTextContent(/didn't work/i)
    expect(getDeviceGrant()).toBeNull()
    expect(screen.getByRole('button', { name: /set up this device for your kids/i })).toBeInTheDocument()
  })

  it('shows the re-authorize/remove actions when a grant already exists', async () => {
    setDeviceGrant({
      token: 'tok-1',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    })
    renderPage()

    expect(await screen.findByText(/kids can now read here/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /re-authorize this device/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /remove from this device/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^set up this device for your kids$/i })).not.toBeInTheDocument()
  })

  it('removes the grant from this device after a successful revoke', async () => {
    const user = userEvent.setup()
    setDeviceGrant({
      token: 'tok-1',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    })
    mockDelete.mockResolvedValue({ data: undefined })
    renderPage()

    await user.click(await screen.findByRole('button', { name: /remove from this device/i }))

    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/v1/device-grants/grant-1'))
    expect(await screen.findByRole('button', { name: /set up this device for your kids/i })).toBeInTheDocument()
    expect(getDeviceGrant()).toBeNull()
  })

  it('keeps showing the grant when revoke fails, so the UI never lies about removal', async () => {
    const user = userEvent.setup()
    setDeviceGrant({
      token: 'tok-1',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    })
    mockDelete.mockRejectedValue(new Error('revoke failed'))
    renderPage()

    await user.click(await screen.findByRole('button', { name: /remove from this device/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/didn't work/i)
    // The grant must still be present, both in the UI and in storage: the
    // server-side revoke did not actually succeed.
    expect(screen.getByRole('button', { name: /remove from this device/i })).toBeInTheDocument()
    expect(getDeviceGrant()).toEqual({
      token: 'tok-1',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    })
  })
})
