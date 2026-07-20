import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { GuardianConsentPage } from './GuardianConsentPage'

const mockRecordConsent = vi.fn()
vi.mock('./useAuth', () => ({
  useAuth: (): unknown => ({ recordConsent: mockRecordConsent }),
}))

beforeEach(() => {
  mockRecordConsent.mockReset()
})

describe('GuardianConsentPage', () => {
  it('disables submit until a name is typed and the checkbox is checked', () => {
    render(<GuardianConsentPage />)
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
    render(<GuardianConsentPage />)
    fireEvent.change(screen.getByLabelText(/your full legal name/i), {
      target: { value: '  Jane A. Guardian  ' },
    })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /agree and continue/i }))

    await waitFor(() => expect(mockRecordConsent).toHaveBeenCalledWith('Jane A. Guardian'))
  })

  it('shows an error and re-enables the form when recordConsent rejects', async () => {
    mockRecordConsent.mockRejectedValue(new Error('422 from backend'))
    render(<GuardianConsentPage />)
    fireEvent.change(screen.getByLabelText(/your full legal name/i), {
      target: { value: 'Jane A. Guardian' },
    })
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: /agree and continue/i }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /agree and continue/i })).toBeEnabled()
  })
})
