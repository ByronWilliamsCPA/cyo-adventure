import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getChildSession, setChildSession } from '../auth/childSession'
import { setDeviceGrant } from '../auth/deviceGrant'
import { ProfilePickerPage } from './ProfilePickerPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

function renderPicker() {
  return render(
    <MemoryRouter>
      <ProfilePickerPage />
    </MemoryRouter>
  )
}

const ONE_PROFILE = {
  profiles: [
    {
      id: 'p1',
      display_name: 'Reader A',
      age_band: '10-13',
      reading_level_cap: 99,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-07-02T00:00:00Z',
    },
  ],
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockNavigate.mockReset()
  localStorage.clear()
})

describe('ProfilePickerPage', () => {
  it('renders a tile per profile linking to that library', async () => {
    mockGet.mockResolvedValue({
      data: {
        profiles: [
          {
            id: 'p1',
            display_name: 'Reader A',
            age_band: '10-13',
            reading_level_cap: 99,
            avatar: 'fox',
            tts_enabled: false,
            created_at: '2026-07-02T00:00:00Z',
          },
          {
            id: 'p2',
            display_name: 'Nova',
            age_band: '5-8',
            reading_level_cap: 99,
            avatar: null,
            tts_enabled: false,
            created_at: '2026-07-02T00:00:00Z',
          },
        ],
      },
    })
    // A signed-in guardian is viewing the picker (auth_token present), so the
    // grown-up-only "Add Child" tile is shown.
    localStorage.setItem('auth_token', 'guardian-jwt')
    renderPicker()
    const tile = await screen.findByRole('link', { name: /Reader A/ })
    expect(tile).toHaveAttribute('href', '/library/p1')
    // Avatar-less profile falls back to the initial letter.
    expect(screen.getByText('N')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Add Child/i })).toHaveAttribute(
      'href',
      '/guardian/profiles'
    )
  })

  it('hides the Add Child tile on a device-grant-only (kid) device', async () => {
    // No auth_token: this device holds only a device grant, so a child is
    // using it. The guardian-only "Add Child" tile must not appear (tapping it
    // would bounce the child to the guardian sign-in page). The child's own
    // profile tiles still render.
    mockGet.mockResolvedValue({ data: ONE_PROFILE })
    renderPicker()
    expect(await screen.findByRole('link', { name: /Reader A/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Add Child/i })).not.toBeInTheDocument()
  })

  it('reveals the Add Child tile when a guardian signs in from another tab', async () => {
    // Starts as a kid-only device (no auth_token), so the tile is hidden.
    mockGet.mockResolvedValue({ data: ONE_PROFILE })
    renderPicker()
    await screen.findByRole('link', { name: /Reader A/ })
    expect(screen.queryByRole('link', { name: /Add Child/i })).not.toBeInTheDocument()

    // A grown-up signs in in ANOTHER tab: localStorage gains the token and the
    // browser fires a `storage` event in this tab. The tile must appear without
    // a remount.
    localStorage.setItem('auth_token', 'guardian-jwt')
    fireEvent(window, new StorageEvent('storage', { key: 'auth_token' }))

    expect(await screen.findByRole('link', { name: /Add Child/i })).toHaveAttribute(
      'href',
      '/guardian/profiles'
    )
  })

  it('hides the Add Child tile when a guardian signs out from another tab', async () => {
    // A guardian is signed in when the picker mounts, so the tile shows.
    localStorage.setItem('auth_token', 'guardian-jwt')
    mockGet.mockResolvedValue({ data: ONE_PROFILE })
    renderPicker()
    expect(await screen.findByRole('link', { name: /Add Child/i })).toBeInTheDocument()

    // Cross-tab sign-out clears the token and fires a `storage` event; the
    // grown-up affordance must disappear so a handed-off child cannot reach it.
    localStorage.removeItem('auth_token')
    fireEvent(window, new StorageEvent('storage', { key: 'auth_token' }))

    await waitFor(() =>
      expect(screen.queryByRole('link', { name: /Add Child/i })).not.toBeInTheDocument()
    )
  })

  it('shows the empty state when no profiles exist', async () => {
    mockGet.mockResolvedValue({ data: { profiles: [] } })
    renderPicker()
    expect(await screen.findByText(/No profiles yet/i)).toBeInTheDocument()
  })

  it('shows an error state when the list fails', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    renderPicker()
    expect(await screen.findByText(/Oops, we hit a snag/i)).toBeInTheDocument()
  })

  it('announces the error state via a role=alert live region', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    renderPicker()
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/Oops, we hit a snag/i)
  })

  it('recovers to the ready state when Try again succeeds after a failed load', async () => {
    const user = userEvent.setup()
    mockGet.mockRejectedValueOnce(new Error('boom'))
    mockGet.mockResolvedValueOnce({
      data: {
        profiles: [
          {
            id: 'p1',
            display_name: 'Reader A',
            age_band: '10-13',
            reading_level_cap: 99,
            avatar: 'fox',
            tts_enabled: false,
            created_at: '2026-07-02T00:00:00Z',
          },
        ],
      },
    })
    renderPicker()

    await screen.findByText(/Oops, we hit a snag/i)
    await user.click(screen.getByRole('button', { name: /try again/i }))

    expect(await screen.findByRole('link', { name: /Reader A/ })).toHaveAttribute(
      'href',
      '/library/p1'
    )
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('offers a grown-up sign-in link from the error state', async () => {
    mockGet.mockRejectedValue(new Error('boom'))
    renderPicker()

    await screen.findByText(/Oops, we hit a snag/i)
    expect(screen.getByRole('link', { name: /I am a grown-up/i })).toHaveAttribute(
      'href',
      '/guardian/login'
    )
  })

  it('shows the empty state without any transient-error copy', async () => {
    mockGet.mockResolvedValue({ data: { profiles: [] } })
    renderPicker()
    await screen.findByText(/No profiles yet/i)
    expect(screen.queryByText(/hit a snag/i)).not.toBeInTheDocument()
  })

  it('shows the ask-a-grown-up gate on a 401, with no retry', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 401 } })
    renderPicker()

    expect(await screen.findByText(/Ask a grown-up to help/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /I am a grown-up/i })).toHaveAttribute(
      'href',
      '/guardian/login'
    )
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/hit a snag/i)).not.toBeInTheDocument()
  })

  it('shows the forbidden copy on a 403, with no retry', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 403 } })
    renderPicker()

    expect(await screen.findByText(/We can't show this right now/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /I am a grown-up/i })).toHaveAttribute(
      'href',
      '/guardian/login'
    )
    expect(screen.queryByRole('button', { name: /try again/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/hit a snag/i)).not.toBeInTheDocument()
  })

  it('logs the raw fallback value for a non-Error, non-axios rejection', async () => {
    // A thrown string has no .message and is not an AxiosError, so the
    // redacted-logging ternary must pass it through as-is.
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    mockGet.mockRejectedValue('socket hangup')
    renderPicker()

    expect(await screen.findByText(/Oops, we hit a snag/i)).toBeInTheDocument()
    expect(errorSpy).toHaveBeenCalledWith('profile list failed', 'socket hangup')
    errorSpy.mockRestore()
  })

  it('ignores a load that fails after unmount (cancelled guard)', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    let rejectList!: (err: unknown) => void
    mockGet.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectList = reject
        })
    )
    const { unmount } = renderPicker()
    unmount()
    rejectList(new Error('late boom'))

    // The redacted log still fires (it precedes the cancelled check); the
    // point is that no state write follows on the unmounted component.
    await waitFor(() => expect(errorSpy).toHaveBeenCalledWith('profile list failed', 'late boom'))
    errorSpy.mockRestore()
  })

  it('ignores a load that resolves after unmount (cancelled guard)', async () => {
    let resolveList!: (value: unknown) => void
    mockGet.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveList = resolve
        })
    )
    const { unmount } = renderPicker()
    unmount()
    resolveList({ data: { profiles: [] } })

    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).toBe('')
  })
})

describe('ProfilePickerPage child session mint (G1 / P6-04)', () => {
  it('mints and stores a child session before navigating to the library', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: ONE_PROFILE })
    mockPost.mockResolvedValue({
      data: { token: 'child-token', expires_at: '2099-01-01T00:00:00Z', profile_id: 'p1' },
    })
    renderPicker()

    const tile = await screen.findByRole('link', { name: /Reader A/ })
    await user.click(tile)

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/child-sessions', { profile_id: 'p1' })
    )
    expect(getChildSession()).toEqual({
      token: 'child-token',
      expiresAt: '2099-01-01T00:00:00Z',
      profileId: 'p1',
    })
    expect(mockNavigate).toHaveBeenCalledWith('/library/p1')
  })

  it('still navigates to the library when the mint call fails, without storing a session', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: ONE_PROFILE })
    mockPost.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    renderPicker()

    const tile = await screen.findByRole('link', { name: /Reader A/ })
    await user.click(tile)

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/library/p1'))
    expect(getChildSession()).toBeNull()
    errorSpy.mockRestore()
  })

  it('does not navigate on click before the mint call settles', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: ONE_PROFILE })
    let resolveMint!: (value: unknown) => void
    mockPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveMint = resolve
        })
    )
    renderPicker()

    const tile = await screen.findByRole('link', { name: /Reader A/ })
    await user.click(tile)

    expect(mockNavigate).not.toHaveBeenCalled()

    resolveMint({
      data: { token: 'child-token', expires_at: '2099-01-01T00:00:00Z', profile_id: 'p1' },
    })
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/library/p1'))
  })

  it('clears a prior session before minting so a failed mint does not carry the old token', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()
    // A leftover session for a DIFFERENT profile is present before the pick.
    setChildSession({ token: 'old-token', expiresAt: '2099-01-01T00:00:00Z', profileId: 'p_old' })
    mockGet.mockResolvedValue({ data: ONE_PROFILE })
    mockPost.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    renderPicker()

    const tile = await screen.findByRole('link', { name: /Reader A/ })
    await user.click(tile)

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/library/p1'))
    // The stale p_old session must be gone: the interceptor would otherwise
    // attach it on /library/p1 and 403 as the wrong profile.
    expect(getChildSession()).toBeNull()
    errorSpy.mockRestore()
  })

  it('fires only one mint when the tile is double-clicked', async () => {
    mockGet.mockResolvedValue({ data: ONE_PROFILE })
    let resolveMint!: (value: unknown) => void
    mockPost.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveMint = resolve
        })
    )
    renderPicker()

    const tile = await screen.findByRole('link', { name: /Reader A/ })
    // Two rapid clicks while the first mint is still in flight.
    fireEvent.click(tile)
    fireEvent.click(tile)

    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1))
    resolveMint({
      data: { token: 'child-token', expires_at: '2099-01-01T00:00:00Z', profile_id: 'p1' },
    })
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/library/p1'))
    expect(mockPost).toHaveBeenCalledTimes(1)
  })

  it('lets a modified click fall through to the browser without minting', async () => {
    mockGet.mockResolvedValue({ data: ONE_PROFILE })
    mockPost.mockResolvedValue({
      data: { token: 'child-token', expires_at: '2099-01-01T00:00:00Z', profile_id: 'p1' },
    })
    renderPicker()

    const tile = await screen.findByRole('link', { name: /Reader A/ })
    // A Ctrl/Cmd-click (open-in-new-tab) must not hijack into the async mint
    // flow; the native href navigation is left to the browser.
    fireEvent.click(tile, { ctrlKey: true })

    expect(mockPost).not.toHaveBeenCalled()
    expect(mockNavigate).not.toHaveBeenCalled()
  })
})

describe('ProfilePickerPage with a device grant and no guardian session (ADR-014 Phase 3)', () => {
  // useApi is mocked wholesale in this file, so the picker component itself
  // never touches bearer selection: which token (guardian, device grant, or
  // child session) rides on `mockGet`/`mockPost` is entirely useApi's
  // interceptor's job (covered directly in useApi.test.ts). This test is a
  // documentation/regression check that the picker's list-then-mint flow
  // still completes normally when the only credential in storage is a device
  // grant and there is no live guardian session at all.
  it('lists profiles and mints a child session with only a device grant present', async () => {
    const user = userEvent.setup()
    setDeviceGrant({
      token: 'device-token',
      expiresAt: '2099-01-01T00:00:00Z',
      familyId: 'fam-1',
      id: 'grant-1',
    })
    expect(localStorage.getItem('auth_token')).toBeNull()
    mockGet.mockResolvedValue({ data: ONE_PROFILE })
    mockPost.mockResolvedValue({
      data: { token: 'child-token', expires_at: '2099-01-01T00:00:00Z', profile_id: 'p1' },
    })
    renderPicker()

    const tile = await screen.findByRole('link', { name: /Reader A/ })
    // With only a device grant (no guardian session), the guardian-only
    // "Add Child" tile stays hidden.
    expect(screen.queryByRole('link', { name: /Add Child/i })).not.toBeInTheDocument()
    await user.click(tile)

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/child-sessions', { profile_id: 'p1' })
    )
    expect(getChildSession()).toEqual({
      token: 'child-token',
      expiresAt: '2099-01-01T00:00:00Z',
      profileId: 'p1',
    })
    expect(mockNavigate).toHaveBeenCalledWith('/library/p1')
  })
})

describe('ProfilePickerPage PIN gate (P6-07)', () => {
  const PIN_PROFILE = {
    profiles: [
      {
        id: 'p1',
        display_name: 'Reader A',
        age_band: '10-13',
        reading_level_cap: 99,
        avatar: 'fox',
        tts_enabled: false,
        has_pin: true,
        created_at: '2026-07-02T00:00:00Z',
      },
    ],
  }

  async function openPinPrompt(user: ReturnType<typeof userEvent.setup>) {
    const tile = await screen.findByRole('link', { name: /Reader A/ })
    await user.click(tile)
    return screen.getByLabelText(/secret pin/i)
  }

  it('marks a locked tile with a padlock badge and "needs a PIN" in its accessible name', async () => {
    mockGet.mockResolvedValue({
      data: {
        profiles: [
          ...PIN_PROFILE.profiles,
          {
            id: 'p2',
            display_name: 'Nova',
            age_band: '5-8',
            reading_level_cap: 99,
            avatar: null,
            tts_enabled: false,
            has_pin: false,
            created_at: '2026-07-02T00:00:00Z',
          },
        ],
      },
    })
    renderPicker()

    // The hint text extends the tile link's accessible name so the PIN gate
    // is announced before the tap, not discovered after it.
    const locked = await screen.findByRole('link', { name: /Reader A needs a PIN/i })
    expect(locked).toHaveAttribute('href', '/library/p1')
    // The padlock glyph itself is decorative and hidden from the tree.
    const badge = locked.querySelector('.picker-tile__pin')
    expect(badge).toHaveAttribute('aria-hidden', 'true')
    expect(badge).toHaveTextContent('🔒')

    // A PIN-less profile gets neither the badge nor the hint.
    const unlocked = screen.getByRole('link', { name: /Nova/ })
    expect(unlocked).not.toHaveAccessibleName(/needs a PIN/i)
    expect(unlocked.querySelector('.picker-tile__pin')).toBeNull()
  })

  it('shows the PIN prompt instead of minting when the profile has a PIN', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: PIN_PROFILE })
    renderPicker()

    const input = await openPinPrompt(user)

    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('type', 'password')
    expect(input).toHaveAttribute('autocomplete', 'off')
    expect(input).toHaveAttribute('inputmode', 'numeric')
    expect(mockPost).not.toHaveBeenCalled()
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('does not show the PIN prompt for a PIN-less profile', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: ONE_PROFILE })
    mockPost.mockResolvedValue({
      data: { token: 't', expires_at: '2099-01-01T00:00:00Z', profile_id: 'p1' },
    })
    renderPicker()

    const tile = await screen.findByRole('link', { name: /Reader A/ })
    await user.click(tile)

    expect(screen.queryByLabelText(/secret pin/i)).not.toBeInTheDocument()
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/child-sessions', { profile_id: 'p1' })
    )
  })

  it('mints with the typed PIN and navigates on success', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: PIN_PROFILE })
    mockPost.mockResolvedValue({
      data: { token: 'child-token', expires_at: '2099-01-01T00:00:00Z', profile_id: 'p1' },
    })
    renderPicker()

    const input = await openPinPrompt(user)
    await user.type(input, '4321')
    await user.click(screen.getByRole('button', { name: /let's read/i }))

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/child-sessions', {
        profile_id: 'p1',
        pin: '4321',
      })
    )
    expect(getChildSession()).toEqual({
      token: 'child-token',
      expiresAt: '2099-01-01T00:00:00Z',
      profileId: 'p1',
    })
    expect(mockNavigate).toHaveBeenCalledWith('/library/p1')
  })

  it('shows a gentle retry message and does not navigate when the PIN is wrong', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: PIN_PROFILE })
    mockPost.mockRejectedValue({
      isAxiosError: true,
      response: { status: 403, data: { code: 'PIN_MISMATCH' } },
    })
    renderPicker()

    const input = await openPinPrompt(user)
    await user.type(input, '9999')
    await user.click(screen.getByRole('button', { name: /let's read/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/didn't work.*try/i)
    // Gentle retry only: never the ask-a-grown-up gate, never a navigation
    // that would fall back to the guardian token and bypass the lock.
    expect(screen.queryByText(/ask a grown-up/i)).not.toBeInTheDocument()
    expect(mockNavigate).not.toHaveBeenCalled()
    expect(getChildSession()).toBeNull()
    // The prompt stays up for another try, with the field cleared.
    expect(screen.getByLabelText(/secret pin/i)).toHaveValue('')
    errorSpy.mockRestore()
  })

  it('never persists the typed PIN anywhere', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: PIN_PROFILE })
    mockPost.mockRejectedValue({
      isAxiosError: true,
      response: { status: 403, data: { code: 'PIN_MISMATCH' } },
    })
    renderPicker()

    const input = await openPinPrompt(user)
    await user.type(input, '9999')
    await user.click(screen.getByRole('button', { name: /let's read/i }))
    await screen.findByRole('alert')

    const stores = [localStorage, sessionStorage]
    for (const store of stores) {
      for (let i = 0; i < store.length; i += 1) {
        const key = store.key(i)
        expect(key === null ? '' : (store.getItem(key) ?? '')).not.toContain('9999')
      }
    }
    errorSpy.mockRestore()
  })

  it('refuses an Enter-key submit with fewer than 4 digits (no mint fired)', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: PIN_PROFILE })
    renderPicker()

    const input = await openPinPrompt(user)
    // The button disables below 4 digits, but Enter submits the form
    // directly; a 1-3 digit submit would be a guaranteed 403 shown as
    // "wrong PIN", so submitPin must refuse it too.
    await user.type(input, '123{Enter}')

    expect(mockPost).not.toHaveBeenCalled()
    expect(mockNavigate).not.toHaveBeenCalled()
    // The typed digits stay in the field; nothing was consumed.
    expect(input).toHaveValue('123')
  })

  it('routes an expired guardian session (401) to the ask-a-grown-up gate, not wrong-PIN copy', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: PIN_PROFILE })
    mockPost.mockRejectedValue({ isAxiosError: true, response: { status: 401 } })
    renderPicker()

    const input = await openPinPrompt(user)
    await user.type(input, '4321')
    await user.click(screen.getByRole('button', { name: /let's read/i }))

    expect(await screen.findByText(/Ask a grown-up to help/i)).toBeInTheDocument()
    expect(screen.queryByText(/didn't work/i)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/secret pin/i)).not.toBeInTheDocument()
    expect(mockNavigate).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('routes a non-PIN 403 to the forbidden gate, not wrong-PIN copy', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: PIN_PROFILE })
    // A 403 WITHOUT the PIN_MISMATCH code (role/family rejection).
    mockPost.mockRejectedValue({
      isAxiosError: true,
      response: { status: 403, data: { error: 'AuthorizationError' } },
    })
    renderPicker()

    const input = await openPinPrompt(user)
    await user.type(input, '4321')
    await user.click(screen.getByRole('button', { name: /let's read/i }))

    expect(await screen.findByText(/We can't show this right now/i)).toBeInTheDocument()
    expect(screen.queryByText(/didn't work/i)).not.toBeInTheDocument()
    expect(mockNavigate).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('shows the kid-safe try-again-later copy on a network or server failure', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: PIN_PROFILE })
    mockPost.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    renderPicker()

    const input = await openPinPrompt(user)
    await user.type(input, '4321')
    await user.click(screen.getByRole('button', { name: /let's read/i }))

    const alert = await screen.findByRole('alert')
    // A correct-PIN child mid-outage must never read "that PIN didn't work".
    expect(alert).toHaveTextContent(/couldn't check your PIN right now/i)
    expect(screen.queryByText(/didn't work/i)).not.toBeInTheDocument()
    // The prompt stays up for another try; no navigation, no session.
    expect(screen.getByLabelText(/secret pin/i)).toBeInTheDocument()
    expect(mockNavigate).not.toHaveBeenCalled()
    expect(getChildSession()).toBeNull()
    errorSpy.mockRestore()
  })

  it('keeps the mint button disabled until at least 4 digits are typed', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: PIN_PROFILE })
    renderPicker()

    const input = await openPinPrompt(user)
    const go = screen.getByRole('button', { name: /let's read/i })
    expect(go).toBeDisabled()
    await user.type(input, '123')
    expect(go).toBeDisabled()
    await user.type(input, '4')
    expect(go).toBeEnabled()
  })

  it('returns to the grid via Go back without minting', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: PIN_PROFILE })
    renderPicker()

    await openPinPrompt(user)
    await user.click(screen.getByRole('button', { name: /go back/i }))

    expect(await screen.findByRole('link', { name: /Reader A/ })).toBeInTheDocument()
    expect(mockPost).not.toHaveBeenCalled()
  })
})
