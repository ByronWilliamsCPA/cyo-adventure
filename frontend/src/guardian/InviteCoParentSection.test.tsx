import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { InviteCoParentSection } from './InviteCoParentSection'

const mockPost = vi.fn()
const fakeApi = { post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

function fillEmail(value: string) {
  fireEvent.change(screen.getByLabelText(/co-parent's email/i), {
    target: { value },
  })
}

function submitForm() {
  fireEvent.click(screen.getByRole('button', { name: /send invite/i }))
}

beforeEach(() => {
  mockPost.mockReset()
})

describe('InviteCoParentSection', () => {
  it('renders the email field and a submit control', () => {
    render(<InviteCoParentSection />)
    expect(screen.getByLabelText(/co-parent's email/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send invite/i })).toBeInTheDocument()
  })

  it('invites a co-parent by email on the happy path', async () => {
    mockPost.mockResolvedValue({
      data: {
        id: 'user-1',
        family_id: 'family-1',
        role: 'guardian',
        is_admin: false,
        status: 'pending_guardian_invite',
      },
    })
    render(<InviteCoParentSection />)
    fillEmail('co-parent@example.com')
    submitForm()

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/me/family/invite-guardian', {
        email: 'co-parent@example.com',
      })
    )
    expect(await screen.findByRole('status')).toHaveTextContent(/invite sent/i)
  })

  it('clears the email field after a successful invite', async () => {
    mockPost.mockResolvedValue({ data: { id: 'user-1', status: 'pending_guardian_invite' } })
    render(<InviteCoParentSection />)
    fillEmail('co-parent@example.com')
    submitForm()
    await screen.findByRole('status')
    expect(screen.getByLabelText(/co-parent's email/i)).toHaveValue('')
  })

  it('shows a specific message for a duplicate pending invite (409)', async () => {
    mockPost.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409, data: { detail: 'a pending invite already exists' } },
    })
    render(<InviteCoParentSection />)
    fillEmail('already-invited@example.com')
    submitForm()

    expect(await screen.findByRole('alert')).toHaveTextContent(/already a pending invite/i)
  })

  it('shows a generic error message for a non-409 failure', async () => {
    mockPost.mockRejectedValue({
      isAxiosError: true,
      response: { status: 500 },
    })
    render(<InviteCoParentSection />)
    fillEmail('someone@example.com')
    submitForm()

    expect(await screen.findByRole('alert')).toHaveTextContent(/something went wrong on our end/i)
  })

  it('shows a busy state while the request is in flight and clears it after completion', async () => {
    let resolveRequest: () => void = () => {}
    mockPost.mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = () =>
          resolve({ data: { id: 'user-1', status: 'pending_guardian_invite' } })
      })
    )
    render(<InviteCoParentSection />)
    fillEmail('co-parent@example.com')
    submitForm()

    const busyButton = await screen.findByRole('button', { name: /sending invite/i })
    expect(busyButton).toBeDisabled()

    resolveRequest()
    // The success path clears the email field, which independently disables
    // the button (no email entered); the busy label going away, not the
    // disabled attribute, is what proves the request is no longer in flight.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /send invite/i })).toBeInTheDocument()
    )
  })

  it('disables the submit control until an email is entered', () => {
    render(<InviteCoParentSection />)
    expect(screen.getByRole('button', { name: /send invite/i })).toBeDisabled()
    fillEmail('co-parent@example.com')
    expect(screen.getByRole('button', { name: /send invite/i })).not.toBeDisabled()
  })

  it('resets a stale duplicate/error state once the email is edited again', async () => {
    mockPost.mockRejectedValue({
      isAxiosError: true,
      response: { status: 409 },
    })
    render(<InviteCoParentSection />)
    fillEmail('already-invited@example.com')
    submitForm()
    await screen.findByRole('alert')

    fillEmail('already-invited2@example.com')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
