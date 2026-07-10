import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

  // The Save/Cancel actions render outside the <form> (Dialog's `actions`
  // prop), so clicking them never fires the form's own onSubmit handler.
  // jsdom's implicit Enter-to-submit only fires for a form with exactly one
  // text field or an in-form submit button; this form has neither (multiple
  // fields, no in-form submit button), so a real `submit` event is the only
  // way to reach onSubmit at all. fireEvent.submit is a deliberate, narrow
  // exception to the userEvent-only rule for that reason.
  it('submits via the form onSubmit event (not the Save button)', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const onClose = vi.fn()
    const { container } = render(
      <ProfileFormDialog title="Add child" onSubmit={onSubmit} onClose={onClose} />
    )

    await user.type(screen.getByLabelText(/name/i), 'Robin')
    const form = container.querySelector('form.profile-form')
    expect(form).not.toBeNull()
    fireEvent.submit(form as HTMLFormElement)

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ display_name: 'Robin' }))
    )
    expect(onClose).toHaveBeenCalled()
  })

  it('does not call onSubmit on a form submit event while the form is invalid', () => {
    const onSubmit = vi.fn()
    const { container } = render(
      <ProfileFormDialog title="Add child" onSubmit={onSubmit} onClose={vi.fn()} />
    )
    // Name is required and left blank: the form is invalid.
    const form = container.querySelector('form.profile-form')
    expect(form).not.toBeNull()
    fireEvent.submit(form as HTMLFormElement)

    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('selects an avatar via its radio input', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<ProfileFormDialog title="Add child" onSubmit={onSubmit} onClose={vi.fn()} />)

    const foxRadio = screen.getByRole('radio', { name: /fox/i })
    expect(foxRadio).not.toBeChecked()
    await user.click(foxRadio)
    expect(foxRadio).toBeChecked()

    await user.type(screen.getByLabelText(/name/i), 'Robin')
    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ avatar: 'fox' }))
    )
  })
})
