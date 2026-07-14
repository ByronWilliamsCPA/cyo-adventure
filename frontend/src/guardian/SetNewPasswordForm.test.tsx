import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthContextValue } from '../auth/authContext'
import { SetNewPasswordForm } from './SetNewPasswordForm'

const mockUpdatePassword = vi.fn()

// Typed against AuthContextValue (via Pick) rather than a bare object literal
// so a future rename/reshape of updatePassword's real signature fails to
// typecheck here, instead of only failing at runtime.
vi.mock('../auth/useAuth', () => ({
  useAuth: (): Pick<AuthContextValue, 'updatePassword'> => ({
    updatePassword: mockUpdatePassword,
  }),
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

  it('surfaces the real Supabase rejection reason from updatePassword', async () => {
    // A backend password-policy rejection (or an expired recovery session) must
    // be shown verbatim so the guardian can fix the actual problem, not a
    // generic message that leaves them guessing.
    mockUpdatePassword.mockRejectedValue(
      new Error('New password should be different from the old password')
    )
    render(<SetNewPasswordForm />)
    fillPasswords('new-password-123', 'new-password-123')
    fireEvent.click(screen.getByRole('button', { name: /set new password/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      /new password should be different from the old password/i
    )
  })

  it('falls back to a generic message when updatePassword rejects with a non-Error value', async () => {
    mockUpdatePassword.mockRejectedValue('boom')
    render(<SetNewPasswordForm />)
    fillPasswords('new-password-123', 'new-password-123')
    fireEvent.click(screen.getByRole('button', { name: /set new password/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't update your password/i)
  })

  it('submits via native Enter-key form submission, not only the button click', async () => {
    render(<SetNewPasswordForm />)
    fillPasswords('new-password-123', 'new-password-123')
    fireEvent.submit(screen.getByRole('button', { name: /set new password/i }).closest('form')!)
    await waitFor(() => expect(mockUpdatePassword).toHaveBeenCalledWith('new-password-123'))
  })

  it('does not submit a second time while the first update is still in flight', async () => {
    let resolveUpdate: (value?: unknown) => void = () => {}
    mockUpdatePassword.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve
      })
    )
    render(<SetNewPasswordForm />)
    fillPasswords('new-password-123', 'new-password-123')
    fireEvent.click(screen.getByRole('button', { name: /set new password/i }))
    fireEvent.click(await screen.findByRole('button', { name: /saving/i }))
    expect(mockUpdatePassword).toHaveBeenCalledTimes(1)
    resolveUpdate()
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
