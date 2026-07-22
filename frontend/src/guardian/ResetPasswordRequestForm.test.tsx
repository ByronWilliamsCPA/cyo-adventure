import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthContextValue } from '../auth/authContext'
import { ResetPasswordRequestForm } from './ResetPasswordRequestForm'

const mockRequestPasswordReset = vi.fn()

// Typed against AuthContextValue (via Pick) rather than a bare object literal
// so a future rename/reshape of requestPasswordReset's real signature fails to
// typecheck here, instead of only failing at runtime.
vi.mock('../auth/useAuth', () => ({
  useAuth: (): Pick<AuthContextValue, 'requestPasswordReset'> => ({
    requestPasswordReset: mockRequestPasswordReset,
  }),
}))

beforeEach(() => {
  mockRequestPasswordReset.mockReset()
  mockRequestPasswordReset.mockResolvedValue(undefined)
})

describe('ResetPasswordRequestForm', () => {
  it('renders the email field and a submit control', () => {
    render(<ResetPasswordRequestForm />)
    expect(screen.getByLabelText('Email for reset link')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send reset link/i })).toBeInTheDocument()
  })

  it('sends a reset link to the entered email', async () => {
    render(<ResetPasswordRequestForm />)
    fireEvent.change(screen.getByLabelText('Email for reset link'), {
      target: { value: 'guardian@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }))
    await waitFor(() =>
      expect(mockRequestPasswordReset).toHaveBeenCalledWith('guardian@example.com')
    )
    expect(
      await screen.findByText(/if an account exists for that email/i)
    ).toBeInTheDocument()
  })

  it('shows a neutral confirmation even when the address is not registered', async () => {
    // requestPasswordReset resolves regardless of whether the address exists
    // (Supabase does not disclose it); the UI must not distinguish the two.
    mockRequestPasswordReset.mockResolvedValue(undefined)
    render(<ResetPasswordRequestForm />)
    fireEvent.change(screen.getByLabelText('Email for reset link'), {
      target: { value: 'unknown@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }))
    expect(await screen.findByRole('status')).toHaveTextContent(
      /if an account exists for that email/i
    )
  })

  it('surfaces a connection error when the request rejects', async () => {
    mockRequestPasswordReset.mockRejectedValue(new Error('network down'))
    render(<ResetPasswordRequestForm />)
    fireEvent.change(screen.getByLabelText('Email for reset link'), {
      target: { value: 'guardian@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't send a reset link/i)
  })

  it('shows a busy state while the request is in flight and re-enables after completion', async () => {
    let resolveRequest: () => void = () => {}
    mockRequestPasswordReset.mockReturnValue(
      new Promise<void>((resolve) => {
        resolveRequest = () => resolve()
      })
    )
    render(<ResetPasswordRequestForm />)
    fireEvent.change(screen.getByLabelText('Email for reset link'), {
      target: { value: 'guardian@example.com' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send reset link/i }))

    const busyButton = await screen.findByRole('button', { name: /sending/i })
    expect(busyButton).toBeDisabled()

    resolveRequest()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /send reset link/i })).not.toBeDisabled()
    )
  })

  it('submits via native Enter-key form submission, not only the button click', async () => {
    render(<ResetPasswordRequestForm />)
    fireEvent.change(screen.getByLabelText('Email for reset link'), {
      target: { value: 'guardian@example.com' },
    })
    fireEvent.submit(screen.getByRole('button', { name: /send reset link/i }).closest('form')!)
    await waitFor(() =>
      expect(mockRequestPasswordReset).toHaveBeenCalledWith('guardian@example.com')
    )
  })
})
