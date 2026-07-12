import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuardianShell } from './GuardianShell'

const mockUseAuth = vi.fn()
vi.mock('../auth/useAuth', () => ({
  useAuth: (): unknown => mockUseAuth(),
}))

function principal(role: 'guardian' | 'admin' | 'child', isAdmin = role === 'admin') {
  return { subject: 's', role, isAdmin, familyId: 'f', profileIds: [] }
}

function renderShell() {
  return render(
    <MemoryRouter initialEntries={['/guardian']}>
      <Routes>
        <Route path="/guardian" element={<GuardianShell />}>
          <Route index element={<div>console content</div>} />
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

describe('GuardianShell', () => {
  it('renders the nav links but no sign-out button when there is no principal', () => {
    mockUseAuth.mockReturnValue({ principal: null, signOut: mockSignOut })
    renderShell()

    expect(screen.getByRole('link', { name: 'Console' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Request a story' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Story requests' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Profiles' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Sign out' })).not.toBeInTheDocument()
    // Books is guardian-only; no principal means it's absent too.
    expect(screen.queryByRole('link', { name: 'Books' })).not.toBeInTheDocument()
  })

  it('shows the Books link only for a guardian principal, not admin', () => {
    mockUseAuth.mockReturnValue({ principal: principal('admin'), signOut: mockSignOut })
    renderShell()
    expect(screen.queryByRole('link', { name: 'Books' })).not.toBeInTheDocument()
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
})
