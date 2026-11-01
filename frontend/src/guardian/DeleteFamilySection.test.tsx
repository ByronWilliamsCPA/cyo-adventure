import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DeleteFamilySection } from './DeleteFamilySection'

const mockDelete = vi.fn()
const mockSignOut = vi.fn()
const fakeApi = { delete: mockDelete }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))
vi.mock('../auth/useAuth', () => ({
  useAuth: () => ({ signOut: mockSignOut }),
}))

function openDialog() {
  fireEvent.click(screen.getByRole('button', { name: 'Delete family account' }))
}

function confirmButton() {
  return screen.getByRole('button', { name: /delete everything|deleting/i })
}

function typeConfirmation(value: string) {
  fireEvent.change(screen.getByLabelText(/to confirm/i), { target: { value } })
}

beforeEach(() => {
  mockDelete.mockReset()
  mockSignOut.mockReset()
  mockSignOut.mockResolvedValue(undefined)
})

describe('DeleteFamilySection', () => {
  it('sends nothing until the dialog is confirmed', () => {
    render(<DeleteFamilySection />)
    openDialog()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(mockDelete).not.toHaveBeenCalled()
  })

  it('keeps the delete button disabled until DELETE is typed', () => {
    render(<DeleteFamilySection />)
    openDialog()
    expect(confirmButton()).toBeDisabled()
    typeConfirmation('delet')
    expect(confirmButton()).toBeDisabled()
    typeConfirmation('delete')
    expect(confirmButton()).toBeDisabled()
    typeConfirmation('DELETE')
    expect(confirmButton()).toBeEnabled()
  })

  it('names what is lost, including co-parent sign-ins and cover art', () => {
    render(<DeleteFamilySection />)
    openDialog()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent(/every child profile/i)
    expect(dialog).toHaveTextContent(/cover art/i)
    expect(dialog).toHaveTextContent(/including any co-parent/i)
    expect(dialog).toHaveTextContent(/cannot be undone/i)
  })

  it('cancelling closes the dialog without deleting anything', () => {
    render(<DeleteFamilySection />)
    openDialog()
    typeConfirmation('DELETE')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(mockDelete).not.toHaveBeenCalled()
  })

  it('does not carry a typed confirmation over into a reopened dialog', () => {
    render(<DeleteFamilySection />)
    openDialog()
    typeConfirmation('DELETE')
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    openDialog()
    expect(confirmButton()).toBeDisabled()
  })

  it('deletes the family and signs out on success', async () => {
    mockDelete.mockResolvedValue({ status: 204 })
    render(<DeleteFamilySection />)
    openDialog()
    typeConfirmation('DELETE')
    fireEvent.click(confirmButton())
    await waitFor(() => expect(mockSignOut).toHaveBeenCalledTimes(1))
    expect(mockDelete).toHaveBeenCalledWith('/v1/me/family')
  })

  it('still ends in a settled state when sign-out fails after a successful delete', async () => {
    mockDelete.mockResolvedValue({ status: 204 })
    mockSignOut.mockRejectedValue(new Error('network down'))
    render(<DeleteFamilySection />)
    openDialog()
    typeConfirmation('DELETE')
    fireEvent.click(confirmButton())
    await waitFor(() => expect(mockSignOut).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows an error and does not sign out when the delete fails', async () => {
    mockDelete.mockRejectedValue(new Error('server error'))
    render(<DeleteFamilySection />)
    openDialog()
    typeConfirmation('DELETE')
    fireEvent.click(confirmButton())
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(mockSignOut).not.toHaveBeenCalled()
    expect(confirmButton()).toBeEnabled()
  })
})
