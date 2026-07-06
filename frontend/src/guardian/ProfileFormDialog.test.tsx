import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ProfileFormDialog } from './ProfileFormDialog'

describe('ProfileFormDialog', () => {
  it('explains that a reading-level cap of 99 means no limit', () => {
    render(<ProfileFormDialog title="Add child" onSubmit={vi.fn()} onClose={vi.fn()} />)

    const cap = screen.getByLabelText(/reading level cap/i)
    const helpId = cap.getAttribute('aria-describedby')
    expect(helpId).toBeTruthy()

    const help = helpId ? document.getElementById(helpId) : null
    expect(help).not.toBeNull()
    expect(help).toHaveTextContent(/99.*no limit/i)
  })

  // naive-UX finding G2: an admin account is not a guardian, so the create
  // endpoint returns 403 by design. The message must say the account lacks
  // permission, not the transient "try again" copy that implies a retry would
  // work.
  it('shows a permission message (not a transient retry) on a 403 save', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockRejectedValue({
      isAxiosError: true,
      response: { status: 403 },
    })
    render(<ProfileFormDialog title="Add child" onSubmit={onSubmit} onClose={vi.fn()} />)

    await user.type(screen.getByLabelText(/name/i), 'Robin')
    await user.click(screen.getByRole('button', { name: /save/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/only a guardian/i)
    expect(alert).not.toHaveTextContent(/try again/i)
  })

  it('shows the transient save copy on a 500 save', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockRejectedValue({
      isAxiosError: true,
      response: { status: 500 },
    })
    render(<ProfileFormDialog title="Add child" onSubmit={onSubmit} onClose={vi.fn()} />)

    await user.type(screen.getByLabelText(/name/i), 'Robin')
    await user.click(screen.getByRole('button', { name: /save/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save.*try again/i)
  })
})
