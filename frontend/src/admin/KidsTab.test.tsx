import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { KidsTab } from './KidsTab'
import type { UserManagementApi } from './userManagementApi'

const FAMILY_A = {
  id: 'fam-a',
  name: 'Family A',
  status: 'active' as const,
  guardian_count: 1,
  kid_count: 1,
  created_at: '2026-01-01T00:00:00Z',
}

const PROFILE_A = {
  id: 'profile-1',
  family_id: 'fam-a',
  display_name: 'Reader One',
  age_band: '5-8' as const,
  reading_level_cap: 10,
  avatar: null,
  tts_enabled: false,
  has_pin: false,
  status: 'active' as const,
  created_at: '2026-01-01T00:00:00Z',
}

function fakeApi(overrides: Partial<UserManagementApi> = {}): UserManagementApi {
  return {
    listUsers: vi.fn(),
    createUser: vi.fn(),
    updateUser: vi.fn(),
    listProfiles: vi.fn(),
    createProfile: vi.fn(),
    updateProfile: vi.fn(),
    listFamilies: vi.fn(),
    createFamily: vi.fn(),
    updateFamily: vi.fn(),
    listConnections: vi.fn(),
    createConnection: vi.fn(),
    deleteConnection: vi.fn(),
    ...overrides,
  }
}

describe('KidsTab', () => {
  it('renders the empty state with no profiles', () => {
    render(<KidsTab api={fakeApi()} families={[FAMILY_A]} profiles={[]} onChanged={vi.fn()} />)
    expect(screen.getByText(/no child profiles yet/i)).toBeInTheDocument()
  })

  it('renders a profile row', () => {
    render(
      <KidsTab
        api={fakeApi()}
        families={[FAMILY_A]}
        profiles={[PROFILE_A]}
        onChanged={vi.fn()}
      />,
    )
    const row = screen.getByText('Reader One').closest('tr')
    expect(row).not.toBeNull()
    expect(within(row as HTMLElement).getByText('Family A')).toBeInTheDocument()
    expect(within(row as HTMLElement).getByText('No')).toBeInTheDocument() // has_pin
  })

  it('creates a profile and calls onChanged', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn().mockResolvedValue(undefined)
    const createProfile = vi.fn().mockResolvedValue({ ...PROFILE_A, id: 'profile-2' })
    render(
      <KidsTab
        api={fakeApi({ createProfile })}
        families={[FAMILY_A]}
        profiles={[]}
        onChanged={onChanged}
      />,
    )
    await user.selectOptions(screen.getByLabelText('Family'), 'fam-a')
    await user.type(screen.getByLabelText('Name'), 'New Kid')
    await user.selectOptions(screen.getByLabelText('Age band'), '5-8')
    await user.click(screen.getByRole('button', { name: 'Create profile' }))

    expect(createProfile).toHaveBeenCalledWith({
      family_id: 'fam-a',
      display_name: 'New Kid',
      age_band: '5-8',
    })
    expect(onChanged).toHaveBeenCalled()
  })

  it('shows a forbidden message when create fails with 403', async () => {
    const user = userEvent.setup()
    const createProfile = vi.fn().mockRejectedValue({
      isAxiosError: true,
      response: { status: 403 },
    })
    render(
      <KidsTab
        api={fakeApi({ createProfile })}
        families={[FAMILY_A]}
        profiles={[]}
        onChanged={vi.fn()}
      />,
    )
    await user.selectOptions(screen.getByLabelText('Family'), 'fam-a')
    await user.type(screen.getByLabelText('Name'), 'New Kid')
    await user.click(screen.getByRole('button', { name: 'Create profile' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/only an admin can create/i)
  })

  it('edits a profile and saves the updated fields, including a new PIN', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn().mockResolvedValue(undefined)
    const updateProfile = vi.fn().mockResolvedValue({ ...PROFILE_A, display_name: 'Renamed' })
    render(
      <KidsTab
        api={fakeApi({ updateProfile })}
        families={[FAMILY_A]}
        profiles={[PROFILE_A]}
        onChanged={onChanged}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    const nameInput = screen.getByLabelText('Name for Reader One')
    await user.clear(nameInput)
    await user.type(nameInput, 'Renamed')
    await user.type(screen.getByLabelText('New PIN for Reader One'), '1234')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(updateProfile).toHaveBeenCalledWith('profile-1', {
      display_name: 'Renamed',
      age_band: '5-8',
      reading_level_cap: 10,
      avatar: null,
      tts_enabled: false,
      pin: '1234',
    })
    expect(onChanged).toHaveBeenCalled()
  })

  it('cancels an in-progress edit without calling the API', async () => {
    const user = userEvent.setup()
    const updateProfile = vi.fn()
    render(
      <KidsTab
        api={fakeApi({ updateProfile })}
        families={[FAMILY_A]}
        profiles={[PROFILE_A]}
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByLabelText('Name for Reader One')).not.toBeInTheDocument()
    expect(updateProfile).not.toHaveBeenCalled()
  })

  it('disables Save when the typed PIN does not match the 4-8 digit shape', async () => {
    const user = userEvent.setup()
    render(
      <KidsTab
        api={fakeApi()}
        families={[FAMILY_A]}
        profiles={[PROFILE_A]}
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.type(screen.getByLabelText('New PIN for Reader One'), '12')
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled()
  })

  it('shows an error when saving an edit fails', async () => {
    const user = userEvent.setup()
    const updateProfile = vi.fn().mockRejectedValue(new Error('boom'))
    render(
      <KidsTab
        api={fakeApi({ updateProfile })}
        families={[FAMILY_A]}
        profiles={[PROFILE_A]}
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save/i)
  })

  it('removes a PIN via the Remove PIN action', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn().mockResolvedValue(undefined)
    const updateProfile = vi.fn().mockResolvedValue({ ...PROFILE_A, has_pin: false })
    render(
      <KidsTab
        api={fakeApi({ updateProfile })}
        families={[FAMILY_A]}
        profiles={[{ ...PROFILE_A, has_pin: true }]}
        onChanged={onChanged}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Remove PIN' }))
    expect(updateProfile).toHaveBeenCalledWith('profile-1', { pin: null })
    expect(onChanged).toHaveBeenCalled()
  })

  it('shows an error when removing a PIN fails', async () => {
    const user = userEvent.setup()
    const updateProfile = vi.fn().mockRejectedValue(new Error('boom'))
    render(
      <KidsTab
        api={fakeApi({ updateProfile })}
        families={[FAMILY_A]}
        profiles={[{ ...PROFILE_A, has_pin: true }]}
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Remove PIN' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not remove that pin/i)
  })

  it('deactivates and reactivates a profile', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn().mockResolvedValue(undefined)
    const updateProfile = vi.fn().mockResolvedValue({ ...PROFILE_A, status: 'deactivated' })
    render(
      <KidsTab
        api={fakeApi({ updateProfile })}
        families={[FAMILY_A]}
        profiles={[PROFILE_A]}
        onChanged={onChanged}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Deactivate' }))
    expect(updateProfile).toHaveBeenCalledWith('profile-1', { status: 'deactivated' })
    expect(onChanged).toHaveBeenCalled()
  })

  it('shows an error when a status change fails', async () => {
    const user = userEvent.setup()
    const updateProfile = vi.fn().mockRejectedValue(new Error('boom'))
    render(
      <KidsTab
        api={fakeApi({ updateProfile })}
        families={[FAMILY_A]}
        profiles={[PROFILE_A]}
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Deactivate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not change/i)
  })
})
