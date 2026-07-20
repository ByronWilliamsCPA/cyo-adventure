import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuardianConsentPage } from './GuardianConsentPage'

const mockRecordConsent = vi.fn()
let mockAuth: { status: string; principal: { role: string } | null } = {
  status: 'needs-consent',
  principal: null,
}
vi.mock('./useAuth', () => ({
  useAuth: (): unknown => ({ ...mockAuth, recordConsent: mockRecordConsent }),
}))

function renderWithRouter() {
  return render(
    <MemoryRouter initialEntries={['/guardian/consent']}>
      <Routes>
        <Route path="/guardian/login" element={<div>Login page</div>} />
        <Route path="/guardian/awaiting-approval" element={<div>Awaiting approval page</div>} />
        <Route path="/guardian" element={<div>Guardian console</div>} />
        <Route path="/admin" element={<div>Admin console</div>} />
        <Route path="/guardian/consent" element={<GuardianConsentPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  mockRecordConsent.mockReset()
  mockAuth = { status: 'needs-consent', principal: null }
})

describe('GuardianConsentPage', () => {
  it('redirects a signed-out visitor to login', () => {
    mockAuth = { status: 'signed-out', principal: null }
    renderWithRouter()
    expect(screen.getByText('Login page')).toBeInTheDocument()
  })

  it('redirects an awaiting-approval guardian to the approval page', () => {
    mockAuth = { status: 'awaiting-approval', principal: null }
    renderWithRouter()
    expect(screen.getByText('Awaiting approval page')).toBeInTheDocument()
  })

  it('redirects an already-consented guardian to their console', () => {
    mockAuth = { status: 'signed-in', principal: { role: 'guardian' } }
    renderWithRouter()
    expect(screen.getByText('Guardian console')).toBeInTheDocument()
  })

  it('redirects an already-consented admin to the admin console', () => {
    mockAuth = { status: 'signed-in', principal: { role: 'admin' } }
    renderWithRouter()
    expect(screen.getByText('Admin console')).toBeInTheDocument()
  })

  it('disables submit until a name is typed and the checkbox is checked', () => {
    renderWithRouter()
    const submit = screen.getByRole('button', { name: /agree and continue/i })
    expect(submit).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/your full legal name/i), {
      target: { value: 'Jane A. Guardian' },
    })
    expect(submit).toBeDisabled()

    fireEvent.click(screen.getByRole('checkbox'))
    expect(submit).toBeEnabled()
  })

  it('submits the trimmed typed name on agree', async () => {
    mockRecordConsent.mockResolvedValue(undefined)
    renderWithRouter()
    fireEvent.change(screen.getByLabelText(/your full legal name/i), {
      target: { value: '  Jane A. Guardian  ' },
    })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /agree and continue/i }))

    await waitFor(() => expect(mockRecordConsent).toHaveBeenCalledWith('Jane A. Guardian'))
  })

  it('shows an error and re-enables the form when recordConsent rejects', async () => {
    mockRecordConsent.mockRejectedValue(new Error('422 from backend'))
    renderWithRouter()
    fireEvent.change(screen.getByLabelText(/your full legal name/i), {
      target: { value: 'Jane A. Guardian' },
    })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /agree and continue/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /agree and continue/i })).toBeEnabled()
  })
})
