import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuardianConsentPage } from './GuardianConsentPage'
import { clearResidenceDraft, rememberResidenceDraft } from './residenceDraft'

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
        <Route path="/guardian/unavailable" element={<div>Backend unavailable</div>} />
        <Route path="/guardian" element={<div>Guardian console</div>} />
        <Route path="/admin" element={<div>Admin console</div>} />
        <Route path="/guardian/consent" element={<GuardianConsentPage />} />
      </Routes>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockRecordConsent.mockReset()
  mockAuth = { status: 'needs-consent', principal: null }
  clearResidenceDraft()
})

describe('GuardianConsentPage residence draft', () => {
  function countrySelect(): HTMLSelectElement {
    return screen.getByLabelText('Your country of residence')
  }

  it('seeds the country field from a drafted code that is in the list', () => {
    rememberResidenceDraft('GB')
    renderWithRouter()

    expect(countrySelect().value).toBe('GB')
  })

  it('ignores a drafted country that is not in the list', () => {
    // The failure this prevents is not "the wrong country is selected", it is
    // a control that LOOKS empty while testing as filled. Seeding 'ZZ' gives
    // the select no matching <option>, so it renders blank, but the submit
    // guard reads residenceCountry.length > 0 and enables the button. The
    // adult then posts a country they were never shown and gets a 422 they
    // have no way to act on. Falling back to '' costs one re-pick instead.
    rememberResidenceDraft('ZZ')
    renderWithRouter()

    expect(countrySelect().value).toBe('')
  })
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

  // #452: reachable from a sibling tab's poll or a direct URL. Handled so
  // the catch-all below never renders a blank page during an outage.
  it('redirects to the backend-unavailable interstitial when the backend is down', () => {
    mockAuth = { status: 'backend-unreachable', principal: null }
    renderWithRouter()
    expect(screen.getByText('Backend unavailable')).toBeInTheDocument()
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

  /** Fills every required field except the one named in `except`. */
  function fillAllExcept(except?: 'name' | 'guardian' | 'country' | 'adulthood') {
    if (except !== 'name') {
      fireEvent.change(screen.getByLabelText(/your full legal name/i), {
        target: { value: 'Jane A. Guardian' },
      })
    }
    if (except !== 'guardian') {
      fireEvent.click(screen.getByLabelText(/parent or legal guardian/i))
    }
    if (except !== 'country') {
      fireEvent.change(screen.getByLabelText(/country of residence/i), {
        target: { value: 'US' },
      })
    }
    if (except !== 'adulthood') {
      fireEvent.click(screen.getByLabelText(/i confirm that i am an adult/i))
    }
  }

  it('disables submit until the name, both checkboxes, and the country are all set', () => {
    renderWithRouter()
    const submit = screen.getByRole('button', { name: /agree and continue/i })
    expect(submit).toBeDisabled()

    fillAllExcept('adulthood')
    expect(submit).toBeDisabled()

    fireEvent.click(screen.getByLabelText(/i confirm that i am an adult/i))
    expect(submit).toBeEnabled()
  })

  it('disables submit when the country of residence is not selected', () => {
    renderWithRouter()
    fillAllExcept('country')
    expect(screen.getByRole('button', { name: /agree and continue/i })).toBeDisabled()
  })

  it('submits the trimmed typed name and selected country on agree', async () => {
    mockRecordConsent.mockResolvedValue(undefined)
    renderWithRouter()
    fireEvent.change(screen.getByLabelText(/your full legal name/i), {
      target: { value: '  Jane A. Guardian  ' },
    })
    fireEvent.click(screen.getByLabelText(/parent or legal guardian/i))
    fireEvent.change(screen.getByLabelText(/country of residence/i), {
      target: { value: 'CA' },
    })
    fireEvent.click(screen.getByLabelText(/i confirm that i am an adult/i))
    fireEvent.click(screen.getByRole('button', { name: /agree and continue/i }))

    await waitFor(() => expect(mockRecordConsent).toHaveBeenCalledWith('Jane A. Guardian', 'CA'))
  })

  it('shows an error and re-enables the form when recordConsent rejects', async () => {
    mockRecordConsent.mockRejectedValue(new Error('422 from backend'))
    renderWithRouter()
    fillAllExcept()
    fireEvent.click(screen.getByRole('button', { name: /agree and continue/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /agree and continue/i })).toBeEnabled()
  })
})
