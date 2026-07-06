import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ProtectedRoute } from './ProtectedRoute'
import type { Principal } from './types'

const mockUseAuth = vi.fn()
vi.mock('./useAuth', () => ({
  useAuth: () => mockUseAuth(),
}))

function renderProtected(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/kids" element={<div>Kid picker</div>} />
        <Route path="/login" element={<div>Login page</div>} />
        <Route
          element={<ProtectedRoute redirectTo="/login" allowedRoles={['guardian', 'admin']} />}
        >
          <Route path="/protected" element={<div>Protected content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  )
}

function principal(role: Principal['role']): Principal {
  return { subject: 's', role, familyId: 'f', profileIds: [] }
}

beforeEach(() => {
  mockUseAuth.mockReset()
})

describe('ProtectedRoute', () => {
  it('shows a loading indicator while auth status is loading', () => {
    mockUseAuth.mockReturnValue({ status: 'loading', principal: null })
    renderProtected('/protected')
    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.queryByText('Protected content')).not.toBeInTheDocument()
  })

  it('redirects to redirectTo when signed out', () => {
    mockUseAuth.mockReturnValue({ status: 'signed-out', principal: null })
    renderProtected('/protected')
    expect(screen.getByText('Login page')).toBeInTheDocument()
  })

  it('sends a signed-in but disallowed role to the kid picker, not the login page', () => {
    // Regression guard for the redirect loop: a child hitting /guardian must
    // NOT be bounced to the guardian login (redirectTo), because a login page
    // redirects an already-signed-in user straight back, looping forever. The
    // default deniedRedirectTo (KID_PICKER_PATH, /kids) breaks that cycle.
    mockUseAuth.mockReturnValue({ status: 'signed-in', principal: principal('child') })
    renderProtected('/protected')
    expect(screen.getByText('Kid picker')).toBeInTheDocument()
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
  })

  it('honors an explicit deniedRedirectTo for a disallowed role', () => {
    mockUseAuth.mockReturnValue({ status: 'signed-in', principal: principal('child') })
    render(
      <MemoryRouter initialEntries={['/protected']}>
        <Routes>
          <Route path="/denied" element={<div>Access denied</div>} />
          <Route
            element={
              <ProtectedRoute
                redirectTo="/login"
                allowedRoles={['guardian']}
                deniedRedirectTo="/denied"
              />
            }
          >
            <Route path="/protected" element={<div>Protected content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText('Access denied')).toBeInTheDocument()
  })

  it('renders the nested route for an allowed role', () => {
    mockUseAuth.mockReturnValue({ status: 'signed-in', principal: principal('guardian') })
    renderProtected('/protected')
    expect(screen.getByText('Protected content')).toBeInTheDocument()
  })

  it('renders for a second allowed role (admin)', () => {
    mockUseAuth.mockReturnValue({ status: 'signed-in', principal: principal('admin') })
    renderProtected('/protected')
    expect(screen.getByText('Protected content')).toBeInTheDocument()
  })
})
