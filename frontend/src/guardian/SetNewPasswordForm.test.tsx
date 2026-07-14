import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { SetNewPasswordForm } from './SetNewPasswordForm'

const mockUpdatePassword = vi.fn()

vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ updatePassword: mockUpdatePassword }),
}))

function fillPasswords(newPassword: string, confirm: string) {
  fireEvent.change(screen.getByLabelText('New password'), { target: { value: newPassword } })
  fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: confirm } })
}

beforeEach(() => {
  mockUpdatePassword.mockReset()
  mockUpdatePassword.mockResolvedValue(undefined)
})

describe('SetNewPasswordForm', () => {
  it('renders both password fields and a submit control', () => {
    render(<SetNewPasswordForm />)
    expect(screen.getByLabelText('New password')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirm password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /set new password/i })).toBeInTheDocument()
  })

  it('submits the new password when both entries match and meet the length rule', async () => {
    render(<SetNewPasswordForm />)
    fillPasswords('new-password-123', 'new-password-123')
    fireEvent.click(screen.getByRole('button', { name: /set new password/i }))
    await waitFor(() => expect(mockUpdatePassword).toHaveBeenCalledWith('new-password-123'))
  })

  it('blocks submission and warns when the two entries do not match', () => {
    render(<SetNewPasswordForm />)
    fillPasswords('new-password-123', 'different-456')
    fireEvent.click(screen.getByRole('button', { name: /set new password/i }))
    expect(screen.getByRole('alert')).toHaveTextContent(/don't match/i)
    expect(mockUpdatePassword).not.toHaveBeenCalled()
  })

  it('blocks submission and warns when the password is too short', () => {
    render(<SetNewPasswordForm />)
    fillPasswords('short', 'short')
    fireEvent.click(screen.getByRole('button', { name: /set new password/i }))
    expect(screen.getByRole('alert')).toHaveTextContent(/at least 8 characters/i)
    expect(mockUpdatePassword).not.toHaveBeenCalled()
  })

  it('surfaces a server-side failure from updatePassword', async () => {
    // A backend password-policy rejection (or an expired recovery session) must
    // be shown so the guardian can retry, not swallowed.
    mockUpdatePassword.mockRejectedValue(new Error('New password should be different'))
    render(<SetNewPasswordForm />)
    fillPasswords('new-password-123', 'new-password-123')
    fireEvent.click(screen.getByRole('button', { name: /set new password/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't update your password/i)
  })

  it('shows a busy state while the update is in flight and re-enables after a failure', async () => {
    let rejectUpdate: (reason: Error) => void = () => {}
    mockUpdatePassword.mockReturnValue(
      new Promise((_resolve, reject) => {
        rejectUpdate = reject
      })
    )
    render(<SetNewPasswordForm />)
    fillPasswords('new-password-123', 'new-password-123')
    fireEvent.click(screen.getByRole('button', { name: /set new password/i }))

    const busyButton = await screen.findByRole('button', { name: /saving/i })
    expect(busyButton).toBeDisabled()

    rejectUpdate(new Error('boom'))
    // Recovers: the button comes back enabled so the guardian can retry.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /set new password/i })).not.toBeDisabled()
    )
  })
})
