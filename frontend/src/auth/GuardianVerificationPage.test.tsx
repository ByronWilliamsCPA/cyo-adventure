import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { GuardianVerificationPage } from './GuardianVerificationPage'

const mockStartVerification = vi.fn()
const mockRefreshStatus = vi.fn()
const mockSignOut = vi.fn()
let mockAuth: {
  status: string
  principal: { role: string } | null
  verificationStatus: string | null
} = {
  status: 'needs-verification',
  principal: null,
  verificationStatus: 'none',
}
vi.mock('./useAuth', () => ({
  useAuth: (): unknown => ({
    ...mockAuth,
    startVerification: mockStartVerification,
    refreshStatus: mockRefreshStatus,
    signOut: mockSignOut,
  }),
}))

function renderWithRouter() {
  return render(
    <MemoryRouter initialEntries={['/guardian/verify']}>
      <Routes>
        <Route path="/guardian/login" element={<div>Login page</div>} />
        <Route path="/guardian/awaiting-approval" element={<div>Awaiting approval page</div>} />
        <Route path="/guardian/consent" element={<div>Consent page</div>} />
        <Route path="/guardian/unavailable" element={<div>Backend unavailable</div>} />
        <Route path="/guardian" element={<div>Guardian console</div>} />
        <Route path="/admin" element={<div>Admin console</div>} />
        <Route path="/guardian/verify" element={<GuardianVerificationPage />} />
      </Routes>
    </MemoryRouter>
  )
}

/** Pick a country in the start form, the only gate on the submit button. */
function chooseCountry(code = 'US') {
  fireEvent.change(screen.getByLabelText('Your country of residence'), {
    target: { value: code },
  })
}

/** An axios-shaped rejection carrying just the status this page branches on. */
function refusal(status: number): Error {
  return Object.assign(new Error(`refused with ${String(status)}`), {
    isAxiosError: true,
    response: { status },
  })
}

beforeEach(() => {
  mockStartVerification.mockReset()
  mockRefreshStatus.mockReset()
  mockSignOut.mockReset()
  mockAuth = { status: 'needs-verification', principal: null, verificationStatus: 'none' }
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('GuardianVerificationPage redirects', () => {
  it('redirects a signed-out visitor to login', () => {
    mockAuth = { status: 'signed-out', principal: null, verificationStatus: null }
    renderWithRouter()
    expect(screen.getByText('Login page')).toBeInTheDocument()
  })

  it('redirects to the backend-unavailable interstitial when the backend is down', () => {
    // Reachable from this page's OWN poll, which runs the same resolution
    // that classifies an outage as transient.
    mockAuth = { status: 'backend-unreachable', principal: null, verificationStatus: 'pending' }
    renderWithRouter()
    expect(screen.getByText('Backend unavailable')).toBeInTheDocument()
  })

  it('sends a now-verified guardian on to the approval step', () => {
    // The normal exit, not an edge case: verification precedes approval, so
    // this is what the poll produces the moment KWS reports success.
    mockAuth = { status: 'awaiting-approval', principal: null, verificationStatus: 'verified' }
    renderWithRouter()
    expect(screen.getByText('Awaiting approval page')).toBeInTheDocument()
  })

  it('sends an already-approved guardian on to the consent step', () => {
    mockAuth = { status: 'needs-consent', principal: null, verificationStatus: 'verified' }
    renderWithRouter()
    expect(screen.getByText('Consent page')).toBeInTheDocument()
  })

  it('redirects a fully signed-in guardian to their console', () => {
    mockAuth = {
      status: 'signed-in',
      principal: { role: 'guardian' },
      verificationStatus: 'verified',
    }
    renderWithRouter()
    expect(screen.getByText('Guardian console')).toBeInTheDocument()
  })

  it('renders nothing while auth is still loading', () => {
    mockAuth = { status: 'loading', principal: null, verificationStatus: null }
    const { container } = renderWithRouter()
    expect(container).toBeEmptyDOMElement()
  })
})

describe('GuardianVerificationPage start form', () => {
  it('will not send until a country is picked', () => {
    renderWithRouter()
    const submit = screen.getByRole('button', { name: 'Email me a verification link' })
    expect(submit).toBeDisabled()

    chooseCountry()

    expect(submit).toBeEnabled()
  })

  it('sends the picked country', async () => {
    mockStartVerification.mockResolvedValue(undefined)
    renderWithRouter()
    chooseCountry('GB')

    fireEvent.click(screen.getByRole('button', { name: 'Email me a verification link' }))

    await waitFor(() => expect(mockStartVerification).toHaveBeenCalledWith('GB'))
  })

  it('offers no way to name the recipient', () => {
    // #CRITICAL: security: the whole anti-automation story rests on the
    // recipient being fixed server-side from the verified token. A form field
    // here would not change the backend's behaviour, but it would advertise
    // an address-taking shape that a later refactor could wire up. Asserted
    // by absence so adding one breaks this test.
    renderWithRouter()
    expect(screen.queryByLabelText(/email/i)).not.toBeInTheDocument()
    expect(document.querySelector('input[type="email"]')).toBeNull()
  })

  it('discloses the email handoff to KWS before the button that performs it', () => {
    // #CRITICAL: security: assurance-register O-125 requires the guardian be
    // told their email address is disclosed to Epic BEFORE they trigger the
    // disclosure. KWS's own "Verify you're an adult" email carries similar
    // wording, but that email only exists because the address was already
    // shared, so this page is the only pre-send surface there is.
    // Order is asserted, not just presence: the same sentence moved below the
    // submit button would still satisfy a presence check while no longer being
    // a pre-send disclosure at all.
    renderWithRouter()

    const disclosure = screen.getByText(/we send Kids Web Services your email address/i)
    const submit = screen.getByRole('button', { name: 'Email me a verification link' })
    expect(disclosure).toHaveTextContent('We send them nothing about your child.')

    const form = submit.closest('form')
    expect(form).not.toBeNull()
    const ordered = Array.from(form?.querySelectorAll('p, button') ?? [])
    expect(ordered.indexOf(disclosure)).toBeGreaterThanOrEqual(0)
    expect(ordered.indexOf(disclosure)).toBeLessThan(ordered.indexOf(submit))
  })

  it('tells a parent an email is already on its way rather than that it failed', async () => {
    // The 409 case. Reporting the generic failure here is the specific harm
    // worth avoiding: it tells a parent to expect nothing, so they stop
    // watching the inbox that already holds their link.
    mockStartVerification.mockRejectedValue(refusal(409))
    renderWithRouter()
    chooseCountry()

    fireEvent.click(screen.getByRole('button', { name: 'Email me a verification link' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/already emailed you/i)
    expect(alert).not.toHaveTextContent(/could not send/i)
  })

  it('explains the hourly cap rather than reporting a failure', async () => {
    mockStartVerification.mockRejectedValue(refusal(429))
    renderWithRouter()
    chooseCountry()

    fireEvent.click(screen.getByRole('button', { name: 'Email me a verification link' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/as many verification emails as we can send/i)
  })

  it('reports a real failure as a failure', async () => {
    // The complement of the two above: a 500 IS a fault, and must not be
    // dressed up as "check your inbox" for mail that was never sent.
    mockStartVerification.mockRejectedValue(refusal(500))
    renderWithRouter()
    chooseCountry()

    fireEvent.click(screen.getByRole('button', { name: 'Email me a verification link' }))

    const alert = await screen.findByRole('alert')
    expect(alert).not.toHaveTextContent(/already emailed you/i)
    expect(alert).not.toHaveTextContent(/as many verification emails/i)
    // Positively assert the retry advice. Without this the case is satisfied
    // by any message at all, including the permanent-refusal copy below, which
    // would be exactly wrong for a fault that a second attempt may well clear.
    expect(alert).toHaveTextContent(/try again/i)
  })

  it.each([400, 403])(
    'does not invite a retry the endpoint will refuse again (%i)',
    async (status) => {
      // Neither status changes on a second attempt: 400 is an unconfigured
      // tier or an account with no row and no address, 403 is a child or
      // deactivated caller. "Please try again" would send a parent into a
      // retry loop that cannot terminate and hide that somebody else has to
      // act.
      mockStartVerification.mockRejectedValue(refusal(status))
      renderWithRouter()
      chooseCountry()

      fireEvent.click(screen.getByRole('button', { name: 'Email me a verification link' }))

      const alert = await screen.findByRole('alert')
      expect(alert).toHaveTextContent(/trying again will not help/i)
      expect(alert).not.toHaveTextContent(/please try again\./i)
    }
  )

  it('treats a KWS outage as a fault worth retrying, not a permanent refusal', async () => {
    // UW-A55: a 502 (backend's ExternalServiceError, e.g. a KWS timeout or
    // outage) used to be indistinguishable from the 400/403 permanent
    // refusals above and got the same "trying again will not help" copy,
    // which was wrong: the backend even closes the attempt out as
    // send_failed so an immediate retry is accepted. This is the case the
    // 400/403 test above must NOT also cover, and the positive counterpart of
    // "reports a real failure as a failure": both a 500 and a 502 are faults
    // that clear on their own, and both must read as retryable.
    mockStartVerification.mockRejectedValue(refusal(502))
    renderWithRouter()
    chooseCountry()

    fireEvent.click(screen.getByRole('button', { name: 'Email me a verification link' }))

    const alert = await screen.findByRole('alert')
    expect(alert).not.toHaveTextContent(/trying again will not help/i)
    expect(alert).toHaveTextContent(/try again/i)
  })

  it('leaves the form usable when a start resolves without moving the status', async () => {
    // The gap that `finally` closes. startVerification resolves, so nothing
    // is thrown, but verificationStatus stays 'none' (a re-resolve that read
    // a stale answer, or an onboarding round trip that failed after the send
    // succeeded), so the component never re-renders into its waiting face.
    // Clearing `busy` only in `catch` freezes this parent on 'Sending…'
    // forever, with no error text and no way to retry.
    mockStartVerification.mockResolvedValue(undefined)
    renderWithRouter()
    chooseCountry()

    fireEvent.click(screen.getByRole('button', { name: 'Email me a verification link' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Email me a verification link' })).toBeEnabled()
    })
  })

  it('re-enables the button after a refusal so the parent can retry', async () => {
    mockStartVerification.mockRejectedValue(refusal(500))
    renderWithRouter()
    chooseCountry()
    const submit = screen.getByRole('button', { name: 'Email me a verification link' })

    fireEvent.click(submit)

    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: 'Email me a verification link' })).toBeEnabled()
  })
})

describe('GuardianVerificationPage waiting state', () => {
  it('shows the check-your-email state once an attempt is in flight', () => {
    mockAuth = { status: 'needs-verification', principal: null, verificationStatus: 'pending' }
    renderWithRouter()
    expect(screen.getByText('We sent you a verification link')).toBeInTheDocument()
    // The form is gone: a second send would be refused with a 409 anyway.
    expect(
      screen.queryByRole('button', { name: 'Email me a verification link' })
    ).not.toBeInTheDocument()
  })

  it('rechecks on demand', async () => {
    mockAuth = { status: 'needs-verification', principal: null, verificationStatus: 'pending' }
    mockRefreshStatus.mockResolvedValue(undefined)
    renderWithRouter()

    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))

    await waitFor(() => expect(mockRefreshStatus).toHaveBeenCalledTimes(1))
  })

  it('polls while waiting', async () => {
    vi.useFakeTimers()
    mockAuth = { status: 'needs-verification', principal: null, verificationStatus: 'pending' }
    mockRefreshStatus.mockResolvedValue(undefined)
    renderWithRouter()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000)
    })

    expect(mockRefreshStatus).toHaveBeenCalled()
  })

  it('does not poll before an attempt exists', async () => {
    // Nothing is in flight, so there is no result that could arrive; a timer
    // here would be a request per 20s per idle tab for no possible answer.
    vi.useFakeTimers()
    mockRefreshStatus.mockResolvedValue(undefined)
    renderWithRouter()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })

    expect(mockRefreshStatus).not.toHaveBeenCalled()
  })

  it('swallows a failed recheck instead of alarming the parent', async () => {
    // The poll fires on a timer the parent did not touch, so an error banner
    // from it reads as a failure of the verification they are waiting on.
    mockAuth = { status: 'needs-verification', principal: null, verificationStatus: 'pending' }
    mockRefreshStatus.mockRejectedValue(new Error('network'))
    renderWithRouter()

    fireEvent.click(screen.getByRole('button', { name: 'Check again' }))

    await waitFor(() => expect(mockRefreshStatus).toHaveBeenCalled())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    // And the control comes back: swallowing the error is only harmless if the
    // busy flag is cleared on the failure path too, otherwise one failed poll
    // leaves the button stuck on "Checking…" for the rest of the wait.
    await waitFor(() => expect(screen.getByRole('button', { name: 'Check again' })).toBeEnabled())
  })
})
