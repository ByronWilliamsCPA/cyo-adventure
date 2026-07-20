import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuardianAwaitingApprovalPage } from './GuardianAwaitingApprovalPage'

const mockSignOut = vi.fn()
vi.mock('./useAuth', () => ({
  useAuth: (): unknown => ({ signOut: mockSignOut }),
}))

beforeEach(() => {
  mockSignOut.mockReset().mockResolvedValue(undefined)
})

describe('GuardianAwaitingApprovalPage', () => {
  it('explains the account is awaiting approval', () => {
    render(<GuardianAwaitingApprovalPage />)
    expect(screen.getByText(/awaiting approval/i)).toBeInTheDocument()
  })

  it('signs out on request', () => {
    render(<GuardianAwaitingApprovalPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(mockSignOut).toHaveBeenCalledTimes(1)
  })
})
