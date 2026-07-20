import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuardianAwaitingApprovalPage } from './GuardianAwaitingApprovalPage'

const mockSignOut = vi.fn()
let mockAuth: { status: string; principal: { role: string } | null } = {
  status: 'awaiting-approval',
  principal: null,
}
vi.mock('./useAuth', () => ({
  useAuth: (): unknown => ({ ...mockAuth, signOut: mockSignOut }),
}))

function renderWithRouter() {
  return render(
    <MemoryRouter initialEntries={['/guardian/awaiting-approval']}>
      <Routes>
        <Route path="/guardian/login" element={<div>Login page</div>} />
        <Route path="/guardian/consent" element={<div>Consent page</div>} />
        <Route path="/guardian" element={<div>Guardian console</div>} />
        <Route path="/admin" element={<div>Admin console</div>} />
        <Route
          path="/guardian/awaiting-approval"
          element={<GuardianAwaitingApprovalPage />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockSignOut.mockReset().mockResolvedValue(undefined)
  mockAuth = { status: 'awaiting-approval', principal: null }
})

describe('GuardianAwaitingApprovalPage', () => {
  it('explains the account is awaiting approval', () => {
    renderWithRouter()
    expect(screen.getByText(/awaiting approval/i)).toBeInTheDocument()
  })

  it('signs out on request', () => {
    renderWithRouter()
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(mockSignOut).toHaveBeenCalledTimes(1)
  })

  it('redirects a signed-out visitor to login', () => {
    mockAuth = { status: 'signed-out', principal: null }
    renderWithRouter()
    expect(screen.getByText('Login page')).toBeInTheDocument()
  })

  it('redirects a consent-pending guardian to the consent page', () => {
    mockAuth = { status: 'needs-consent', principal: null }
    renderWithRouter()
    expect(screen.getByText('Consent page')).toBeInTheDocument()
  })

  it('redirects an already-approved guardian to their console', () => {
    mockAuth = { status: 'signed-in', principal: { role: 'guardian' } }
    renderWithRouter()
    expect(screen.getByText('Guardian console')).toBeInTheDocument()
  })

  it('redirects an already-approved admin to the admin console', () => {
    mockAuth = { status: 'signed-in', principal: { role: 'admin' } }
    renderWithRouter()
    expect(screen.getByText('Admin console')).toBeInTheDocument()
  })
})
