import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { ProfileView } from '../profiles/profilesApi'
import { ProfileFormDialog } from './ProfileFormDialog'

function existingProfile(hasPin: boolean): ProfileView {
  return {
    id: 'p1',
    display_name: 'Robin',
    age_band: '5-8',
    reading_level_cap: 99,
    avatar: null,
    tts_enabled: false,
    has_pin: hasPin,
    created_at: '2026-07-02T00:00:00Z',
  }
}

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

  it('allows a reading level cap of exactly 99 (the boundary)', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<ProfileFormDialog title="Add child" onSubmit={onSubmit} onClose={vi.fn()} />)

    await user.type(screen.getByLabelText(/name/i), 'Robin')
    const capInput = screen.getByLabelText(/reading level cap/i)
    await user.clear(capInput)
    await user.type(capInput, '99')

    const saveButton = screen.getByRole('button', { name: /save/i })
    expect(saveButton).toBeEnabled()
    await user.click(saveButton)

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({ reading_level_cap: 99 }),
      )
    )
  })

  it('blocks a reading level cap of 100 (one past the boundary)', () => {
    const onSubmit = vi.fn()
    const { container } = render(
      <ProfileFormDialog title="Add child" onSubmit={onSubmit} onClose={vi.fn()} />
    )

    const nameInput = screen.getByLabelText(/name/i)
    fireEvent.change(nameInput, { target: { value: 'Robin' } })
    const capInput = screen.getByLabelText(/reading level cap/i)
    fireEvent.change(capInput, { target: { value: '100' } })

    const saveButton = screen.getByRole('button', { name: /save/i })
    expect(saveButton).toBeDisabled()

    // Guard the form-submit path too, not just the Save button's disabled
    // attribute (see the "does not call onSubmit ... while invalid" test).
    const form = container.querySelector('form.profile-form')
    expect(form).not.toBeNull()
    fireEvent.submit(form as HTMLFormElement)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  // The read-aloud (TTS) toggle is hidden until the reader ships read-aloud
  // support; tts_enabled still travels in the payload (false on create, the
  // stored value passed through unchanged on edit).
  it('renders no read-aloud checkbox and defaults tts_enabled to false on create', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<ProfileFormDialog title="Add child" onSubmit={onSubmit} onClose={vi.fn()} />)

    expect(screen.queryByRole('checkbox', { name: /read-aloud/i })).not.toBeInTheDocument()

    await user.type(screen.getByLabelText(/name/i), 'Robin')
    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ tts_enabled: false }))
    )
  })

  it('passes an edited profile tts_enabled value through unchanged', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <ProfileFormDialog
        title="Edit Robin"
        initial={{ ...existingProfile(false), tts_enabled: true }}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />
    )

    expect(screen.queryByRole('checkbox', { name: /read-aloud/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ tts_enabled: true }))
    )
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

describe('ProfileFormDialog picker PIN controls (P6-07)', () => {
  it('hides the PIN controls entirely in create mode', () => {
    render(<ProfileFormDialog title="Add child" onSubmit={vi.fn()} onClose={vi.fn()} />)
    expect(screen.queryByText(/picker pin/i)).not.toBeInTheDocument()
  })

  it('sets a PIN on a PIN-less profile via Set a PIN', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <ProfileFormDialog
        title="Edit Robin"
        initial={existingProfile(false)}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByText(/picker pin/i)).toBeInTheDocument()
    // A PIN-less profile offers No PIN / Set a PIN, never Remove.
    expect(screen.getByRole('radio', { name: /no pin/i })).toBeChecked()
    expect(screen.queryByRole('radio', { name: /remove pin/i })).not.toBeInTheDocument()

    await user.click(screen.getByRole('radio', { name: /set a pin/i }))
    await user.type(screen.getByLabelText(/new pin/i), '4321')
    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ pin: '4321' }))
    )
  })

  it('omits the pin field when Keep current PIN is left selected', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <ProfileFormDialog
        title="Edit Robin"
        initial={existingProfile(true)}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />
    )

    expect(screen.getByRole('radio', { name: /keep current pin/i })).toBeChecked()
    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    const body = onSubmit.mock.calls[0][0] as Record<string, unknown>
    expect('pin' in body).toBe(false)
  })

  it('sends an explicit null pin when Remove PIN is chosen', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <ProfileFormDialog
        title="Edit Robin"
        initial={existingProfile(true)}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />
    )

    await user.click(screen.getByRole('radio', { name: /remove pin/i }))
    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ pin: null }))
    )
  })

  it('sends the new value when Change PIN is chosen', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <ProfileFormDialog
        title="Edit Robin"
        initial={existingProfile(true)}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />
    )

    await user.click(screen.getByRole('radio', { name: /change pin/i }))
    await user.type(screen.getByLabelText(/new pin/i), '87654321')
    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ pin: '87654321' }))
    )
  })

  it('disables Save while a chosen PIN is shorter than 4 digits', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(
      <ProfileFormDialog
        title="Edit Robin"
        initial={existingProfile(false)}
        onSubmit={onSubmit}
        onClose={vi.fn()}
      />
    )

    await user.click(screen.getByRole('radio', { name: /set a pin/i }))
    await user.type(screen.getByLabelText(/new pin/i), '123')
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled()

    await user.type(screen.getByLabelText(/new pin/i), '4')
    expect(screen.getByRole('button', { name: /save/i })).toBeEnabled()
  })

  it('strips non-digit input from the PIN field', async () => {
    const user = userEvent.setup()
    render(
      <ProfileFormDialog
        title="Edit Robin"
        initial={existingProfile(false)}
        onSubmit={vi.fn()}
        onClose={vi.fn()}
      />
    )

    await user.click(screen.getByRole('radio', { name: /set a pin/i }))
    const input = screen.getByLabelText(/new pin/i)
    await user.type(input, '1a2b3c4d')
    expect(input).toHaveValue('1234')
  })
})
