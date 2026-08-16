import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { GuardianAwaitingApprovalPage } from './GuardianAwaitingApprovalPage'

const mockSignOut = vi.fn()
const mockRefreshStatus = vi.fn()
let mockAuth: { status: string; principal: { role: string } | null } = {
  status: 'awaiting-approval',
  principal: null,
}
vi.mock('./useAuth', () => ({
  useAuth: (): unknown => ({
    ...mockAuth,
    signOut: mockSignOut,
    refreshStatus: mockRefreshStatus,
  }),
}))

function renderWithRouter() {
  return render(
    <MemoryRouter initialEntries={['/guardian/awaiting-approval']}>
      <Routes>
        <Route path="/guardian/login" element={<div>Login page</div>} />
        <Route path="/guardian/consent" element={<div>Consent page</div>} />
        <Route path="/guardian/unavailable" element={<div>Backend unavailable</div>} />
        <Route path="/guardian" element={<div>Guardian console</div>} />
        <Route path="/admin" element={<div>Admin console</div>} />
        <Route path="/guardian/awaiting-approval" element={<GuardianAwaitingApprovalPage />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockSignOut.mockReset().mockResolvedValue(undefined)
  mockRefreshStatus.mockReset().mockResolvedValue(undefined)
  mockAuth = { status: 'awaiting-approval', principal: null }
})

afterEach(() => {
  vi.useRealTimers()
})

describe('GuardianAwaitingApprovalPage', () => {
  it('explains the account is awaiting approval', () => {
    renderWithRouter()
    expect(screen.getByText(/awaiting approval/i)).toBeInTheDocument()
  })

  // UW-J28. Two separate defects in one sentence, so two separate assertions.
  // "A family administrator needs to approve your account" named an authority
  // inside the reader's family; approval is granted by a platform admin
  // (PATCH /api/v1/admin/users/{id}). And "come back after you've heard from
  // them" promised a message nothing sends: no notification fires on approval
  // (UW-J29), so this page's own poll is the entire feedback channel.
  it('does not blame a family member or promise a message that is never sent', () => {
    renderWithRouter()
    expect(screen.queryByText(/family administrator/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/heard from them/i)).not.toBeInTheDocument()
    expect(
      screen.getByText(/someone on the cyo adventure team reviews each new account/i)
    ).toBeInTheDocument()
  })

  // The one screen in onboarding a guardian can sit on indefinitely had no
  // route anywhere. SUPPORT_PATH is public and outside every auth gate by
  // construction (routes.ts), which is what makes it reachable for a caller
  // whose account require_principal still refuses.
  it('offers a support route for a guardian who is stuck', () => {
    renderWithRouter()
    expect(screen.getByRole('link', { name: /contact support/i })).toHaveAttribute(
      'href',
      '/support'
    )
  })

  // P-6d: this page used to be a true dead end while still pending; it now
  // shows a manual recheck action alongside Sign out.
  it('still pending: shows the waiting copy and a Check again action', () => {
    renderWithRouter()
    expect(screen.getByText(/awaiting approval/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Check again' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Sign out' })).toBeInTheDocument()
  })

  it('signs out on request', () => {
    renderWithRouter()
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(mockSignOut).toHaveBeenCalledTimes(1)
  })

  // P-6d: clicking Check again calls refreshStatus; a status flip to
  // 'signed-in' (an admin approved the account) must advance the guardian
  // off this page without a sign-out/sign-in round trip.
  it('Check again calls refreshStatus and advances off the page once status flips to signed-in', async () => {
    mockRefreshStatus.mockImplementation(() => {
      mockAuth = { status: 'signed-in', principal: { role: 'guardian' } }
      return Promise.resolve()
    })
    renderWithRouter()
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
    expect(mockRefreshStatus).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(screen.getByText('Guardian console')).toBeInTheDocument())
  })

  // P-6d: still-pending is the common case; a failed recheck must not throw,
  // crash the page, or strand the "Checking…" label past the failure.
  it('a failed Check again leaves the page on the waiting state', async () => {
    mockRefreshStatus.mockRejectedValue(new Error('network down'))
    renderWithRouter()
    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Check again' })).toBeInTheDocument()
    )
    expect(screen.getByText(/awaiting approval/i)).toBeInTheDocument()
  })

  // P-6d: the background poll is a convenience, not a requirement; it must
  // fire refreshStatus on its own without any user interaction.
  it('polls refreshStatus automatically while still pending', async () => {
    vi.useFakeTimers()
    renderWithRouter()
    expect(mockRefreshStatus).not.toHaveBeenCalled()
    // Deviation from the brief: Testing Library's fake-timer detection only
    // fires when a `jest` global exists (jestFakeTimersAreEnabled in
    // @testing-library/dom), so under Vitest waitFor cannot advance the
    // faked timers and would hang. Drive the flush explicitly with act +
    // advanceTimersByTimeAsync instead (same pattern as
    // IntakePage.test.tsx's "polls while a job is active" test).
    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000)
    })
    expect(mockRefreshStatus).toHaveBeenCalledTimes(1)
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

  // #452: this page's own poll can now surface a transient backend outage.
  // Without the redirect it would fall through to the render-nothing branch
  // and leave the guardian staring at a blank page.
  it('redirects to the backend-unavailable interstitial when the backend drops', () => {
    mockAuth = { status: 'backend-unreachable', principal: null }
    renderWithRouter()
    expect(screen.getByText('Backend unavailable')).toBeInTheDocument()
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
