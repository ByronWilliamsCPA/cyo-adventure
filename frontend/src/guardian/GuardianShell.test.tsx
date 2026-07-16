import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuardianShell } from './GuardianShell'
import { STORY_REQUESTS_CHANGED_EVENT } from './storyRequestQueueApi'

const mockUseAuth = vi.fn()
vi.mock('../auth/useAuth', () => ({
  useAuth: (): unknown => mockUseAuth(),
}))

// The shell's pending-count nav badge reads the family queue on mount; the
// default (rejected) implementation keeps the badge hidden in every
// pre-existing test, matching the shell's silent-failure behavior.
const mockGet = vi.fn()
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

function principal(role: 'guardian' | 'admin' | 'child', isAdmin = role === 'admin') {
  return { subject: 's', role, isAdmin, familyId: 'f', profileIds: [] }
}

function pendingRequests(count: number) {
  return {
    data: { requests: Array.from({ length: count }, (_, i) => ({ id: `req-${i + 1}` })) },
  }
}

function renderShell() {
  return render(
    <MemoryRouter initialEntries={['/guardian']}>
      <Routes>
        <Route path="/guardian" element={<GuardianShell />}>
          <Route index element={<div>console content</div>} />
          <Route path="intake" element={<div>intake content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

const mockSignOut = vi.fn()

beforeEach(() => {
  mockUseAuth.mockReset()
  mockSignOut.mockReset()
  mockGet.mockReset()
  mockGet.mockRejectedValue(new Error('no queue backend in this test'))
})

describe('GuardianShell', () => {
  it('renders the nav links but no sign-out button when there is no principal', () => {
    mockUseAuth.mockReturnValue({ principal: null, signOut: mockSignOut })
    renderShell()

    expect(screen.getByRole('link', { name: 'Console' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Request a story' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Story requests' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument()
    // Books and Profiles are both guardian-only (family-management
    // affordances an admin-only adult has no family for); no principal
    // means they're absent too.
    expect(screen.queryByRole('link', { name: 'Books' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Profiles' })).not.toBeInTheDocument()
  })

  it('shows the Books link only for a guardian principal, not admin', () => {
    mockUseAuth.mockReturnValue({ principal: principal('admin'), signOut: mockSignOut })
    renderShell()
    expect(screen.queryByRole('link', { name: 'Books' })).not.toBeInTheDocument()
  })

  it('shows the Profiles link only for a guardian principal, not admin', () => {
    mockUseAuth.mockReturnValue({ principal: principal('admin'), signOut: mockSignOut })
    renderShell()
    expect(screen.queryByRole('link', { name: 'Profiles' })).not.toBeInTheDocument()
  })

  it('shows the Admin console link for a principal holding the admin capability', () => {
    // A dual-role adult (guardian base role + is_admin) gets the switcher
    // into the parallel /admin surface; an admin-only principal does too.
    mockUseAuth.mockReturnValue({
      principal: principal('guardian', true),
      signOut: mockSignOut,
    })
    renderShell()
    expect(screen.getByRole('link', { name: 'Admin console' })).toHaveAttribute('href', '/admin')
  })

  it('hides the Admin console link from a plain guardian', () => {
    mockUseAuth.mockReturnValue({ principal: principal('guardian'), signOut: mockSignOut })
    renderShell()
    expect(screen.queryByRole('link', { name: 'Admin console' })).not.toBeInTheDocument()
  })

  it('shows the Books link and a sign-out button for a guardian principal', () => {
    mockUseAuth.mockReturnValue({ principal: principal('guardian'), signOut: mockSignOut })
    renderShell()
    expect(screen.getByRole('link', { name: 'Books' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Profiles' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
  })

  it('signs out on click with no error banner on success', async () => {
    const user = userEvent.setup()
    mockSignOut.mockResolvedValue(undefined)
    mockUseAuth.mockReturnValue({ principal: principal('guardian'), signOut: mockSignOut })
    renderShell()

    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(mockSignOut).toHaveBeenCalled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows an error banner when sign-out rejects', async () => {
    const user = userEvent.setup()
    mockSignOut.mockRejectedValue(new Error('network down'))
    mockUseAuth.mockReturnValue({ principal: principal('guardian'), signOut: mockSignOut })
    renderShell()

    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/sign-out failed/i)
  })

  it('renders the nested route content via Outlet', () => {
    mockUseAuth.mockReturnValue({ principal: principal('guardian'), signOut: mockSignOut })
    renderShell()
    expect(screen.getByText('console content')).toBeInTheDocument()
  })

  it('shows an "Admin" role hint for an admin principal', () => {
    mockUseAuth.mockReturnValue({ principal: principal('admin'), signOut: mockSignOut })
    renderShell()
    expect(screen.getByText('Admin')).toBeInTheDocument()
  })

  it('shows a "Guardian" role hint for a guardian principal', () => {
    mockUseAuth.mockReturnValue({ principal: principal('guardian'), signOut: mockSignOut })
    renderShell()
    expect(screen.getByText('Guardian')).toBeInTheDocument()
  })

  it('shows no role hint when there is no principal', () => {
    mockUseAuth.mockReturnValue({ principal: null, signOut: mockSignOut })
    renderShell()
    expect(screen.queryByText('Admin')).not.toBeInTheDocument()
    expect(screen.queryByText('Guardian')).not.toBeInTheDocument()
  })

  it('shows no role hint for a child principal (defensive; GuardianShell never mounts for one)', () => {
    mockUseAuth.mockReturnValue({ principal: principal('child'), signOut: mockSignOut })
    renderShell()
    expect(screen.queryByText('Admin')).not.toBeInTheDocument()
    expect(screen.queryByText('Guardian')).not.toBeInTheDocument()
  })

  describe('pending story-request nav badge', () => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue({ principal: principal('guardian'), signOut: mockSignOut })
    })

    it('renders the pending count with an accessible link name', async () => {
      mockGet.mockResolvedValue(pendingRequests(3))
      renderShell()
      const link = await screen.findByRole('link', { name: 'Story requests, 3 waiting' })
      expect(within(link).getByText('3')).toBeInTheDocument()
      expect(mockGet).toHaveBeenCalledWith('/v1/story-requests?status=pending')
    })

    it('hides the badge when there are zero pending requests', async () => {
      mockGet.mockResolvedValue(pendingRequests(0))
      renderShell()
      // Wait for the fetch to settle before asserting absence.
      await waitFor(() =>
        expect(mockGet).toHaveBeenCalledWith('/v1/story-requests?status=pending')
      )
      const link = screen.getByRole('link', { name: 'Story requests' })
      expect(link).not.toHaveAttribute('aria-label')
      expect(within(link).queryByText('0')).not.toBeInTheDocument()
    })

    it('hides the badge when the fetch fails (silent progressive enhancement)', async () => {
      mockGet.mockRejectedValue(new Error('backend down'))
      renderShell()
      await waitFor(() =>
        expect(mockGet).toHaveBeenCalledWith('/v1/story-requests?status=pending')
      )
      const link = screen.getByRole('link', { name: 'Story requests' })
      expect(link).not.toHaveAttribute('aria-label')
    })

    it('skips the fetch entirely when there is no principal', () => {
      mockUseAuth.mockReturnValue({ principal: null, signOut: mockSignOut })
      renderShell()
      expect(screen.getByText('console content')).toBeInTheDocument()
      expect(mockGet).not.toHaveBeenCalled()
    })

    it('refetches when the queue signals a change (approve/decline landed)', async () => {
      mockGet.mockResolvedValueOnce(pendingRequests(2))
      renderShell()
      await screen.findByRole('link', { name: 'Story requests, 2 waiting' })

      mockGet.mockResolvedValueOnce(pendingRequests(1))
      act(() => {
        window.dispatchEvent(new Event(STORY_REQUESTS_CHANGED_EVENT))
      })
      expect(
        await screen.findByRole('link', { name: 'Story requests, 1 waiting' })
      ).toBeInTheDocument()
    })

    it('refetches when the route changes between guardian pages', async () => {
      const user = userEvent.setup()
      mockGet.mockResolvedValueOnce(pendingRequests(1))
      renderShell()
      await screen.findByRole('link', { name: 'Story requests, 1 waiting' })

      mockGet.mockResolvedValueOnce(pendingRequests(4))
      await user.click(screen.getByRole('link', { name: 'Request a story' }))
      await screen.findByText('intake content')
      expect(
        await screen.findByRole('link', { name: 'Story requests, 4 waiting' })
      ).toBeInTheDocument()
    })
  })
})
