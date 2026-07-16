import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminShell } from './AdminShell'

const mockUseAuth = vi.fn()
vi.mock('../auth/useAuth', () => ({
  useAuth: (): unknown => mockUseAuth(),
}))

function principal(role: 'guardian' | 'admin', isAdmin = true) {
  return { subject: 's', role, isAdmin, familyId: 'f', profileIds: [] }
}

function renderShell() {
  return render(
    <MemoryRouter initialEntries={['/admin']}>
      <Routes>
        <Route path="/admin" element={<AdminShell />}>
          <Route index element={<div>admin content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

const mockSignOut = vi.fn()

beforeEach(() => {
  mockUseAuth.mockReset()
  mockSignOut.mockReset()
})

describe('AdminShell', () => {
  it('renders the admin nav links and the Admin role hint', () => {
    mockUseAuth.mockReturnValue({ principal: principal('admin'), signOut: mockSignOut })
    renderShell()
    expect(screen.getByRole('link', { name: 'Review queue' })).toHaveAttribute('href', '/admin')
    expect(screen.getByRole('link', { name: 'Story requests' })).toHaveAttribute(
      'href',
      '/admin/requests'
    )
    expect(screen.getByRole('link', { name: 'Authoring queue' })).toHaveAttribute(
      'href',
      '/admin/authoring-queue'
    )
    expect(screen.getByRole('link', { name: 'Moderation dashboard' })).toHaveAttribute(
      'href',
      '/admin/moderation-dashboard'
    )
    expect(screen.getByRole('link', { name: 'Moderation thresholds' })).toHaveAttribute(
      'href',
      '/admin/moderation-thresholds'
    )
    expect(screen.getByRole('link', { name: 'Provider allowlist' })).toHaveAttribute(
      'href',
      '/admin/provider-allowlist'
    )
    expect(screen.getByText('Admin')).toBeInTheDocument()
  })

  it('renders the nested route content via Outlet', () => {
    mockUseAuth.mockReturnValue({ principal: principal('admin'), signOut: mockSignOut })
    renderShell()
    expect(screen.getByText('admin content')).toBeInTheDocument()
  })

  it('shows the Guardian console cross-link for a dual-role adult', () => {
    mockUseAuth.mockReturnValue({ principal: principal('guardian', true), signOut: mockSignOut })
    renderShell()
    expect(screen.getByRole('link', { name: 'Guardian console' })).toHaveAttribute(
      'href',
      '/guardian'
    )
  })

  it('hides the Guardian console cross-link from an admin-only adult', () => {
    mockUseAuth.mockReturnValue({ principal: principal('admin'), signOut: mockSignOut })
    renderShell()
    expect(screen.queryByRole('link', { name: 'Guardian console' })).not.toBeInTheDocument()
  })

  it('renders no sign-out button when there is no principal', () => {
    mockUseAuth.mockReturnValue({ principal: null, signOut: mockSignOut })
    renderShell()
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument()
  })

  it('signs out on click with no error banner on success', async () => {
    const user = userEvent.setup()
    mockSignOut.mockResolvedValue(undefined)
    mockUseAuth.mockReturnValue({ principal: principal('admin'), signOut: mockSignOut })
    renderShell()

    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(mockSignOut).toHaveBeenCalled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows an error banner when sign-out rejects', async () => {
    const user = userEvent.setup()
    mockSignOut.mockRejectedValue(new Error('network down'))
    mockUseAuth.mockReturnValue({ principal: principal('admin'), signOut: mockSignOut })
    renderShell()

    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/sign-out failed/i)
  })
})
