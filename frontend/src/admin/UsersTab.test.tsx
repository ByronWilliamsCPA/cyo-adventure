import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { UsersTab } from './UsersTab'
import type { UserManagementApi } from './userManagementApi'

const FAMILY_A = {
  id: 'fam-a',
  name: 'Family A',
  status: 'active' as const,
  guardian_count: 1,
  kid_count: 0,
  created_at: '2026-01-01T00:00:00Z',
}
const FAMILY_B = {
  id: 'fam-b',
  name: 'Family B',
  status: 'active' as const,
  guardian_count: 0,
  kid_count: 0,
  created_at: '2026-01-02T00:00:00Z',
}

const USER_A = {
  id: 'user-1',
  family_id: 'fam-a',
  email: 'guardian@example.com',
  role: 'guardian' as const,
  is_admin: false,
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

describe('UsersTab', () => {
  it('renders the empty state with no users', () => {
    render(<UsersTab api={fakeApi()} families={[FAMILY_A]} users={[]} onChanged={vi.fn()} />)
    expect(screen.getByText(/no guardians or admins yet/i)).toBeInTheDocument()
  })

  it('renders a user row with the resolved family name', () => {
    render(
      <UsersTab api={fakeApi()} families={[FAMILY_A]} users={[USER_A]} onChanged={vi.fn()} />,
    )
    const row = screen.getByText('guardian@example.com').closest('tr')
    expect(row).not.toBeNull()
    expect(within(row as HTMLElement).getByText('Family A')).toBeInTheDocument()
    expect(within(row as HTMLElement).getByText('guardian')).toBeInTheDocument()
  })

  it('invites a guardian and calls onChanged', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn().mockResolvedValue(undefined)
    const createUser = vi.fn().mockResolvedValue({ ...USER_A, id: 'user-2' })
    render(
      <UsersTab
        api={fakeApi({ createUser })}
        families={[FAMILY_A]}
        users={[]}
        onChanged={onChanged}
      />,
    )
    await user.type(screen.getByLabelText('Email'), 'new@example.com')
    await user.selectOptions(screen.getByLabelText('Family'), 'fam-a')
    await user.click(screen.getByRole('button', { name: 'Send invite' }))

    expect(createUser).toHaveBeenCalledWith({
      email: 'new@example.com',
      family_id: 'fam-a',
      role: 'guardian',
      is_admin: false,
    })
    expect(onChanged).toHaveBeenCalled()
  })

  it('shows a forbidden message when the invite fails with 403', async () => {
    const user = userEvent.setup()
    const createUser = vi.fn().mockRejectedValue({
      isAxiosError: true,
      response: { status: 403 },
    })
    render(
      <UsersTab
        api={fakeApi({ createUser })}
        families={[FAMILY_A]}
        users={[]}
        onChanged={vi.fn()}
      />,
    )
    await user.type(screen.getByLabelText('Email'), 'new@example.com')
    await user.selectOptions(screen.getByLabelText('Family'), 'fam-a')
    await user.click(screen.getByRole('button', { name: 'Send invite' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/only an admin can invite/i)
  })

  it('forces the dual-admin checkbox on for role=admin in the invite form', async () => {
    const user = userEvent.setup()
    render(<UsersTab api={fakeApi()} families={[FAMILY_A]} users={[]} onChanged={vi.fn()} />)
    await user.selectOptions(screen.getByLabelText('Role'), 'admin')
    const checkbox = screen.getByRole('checkbox', { name: /also grant admin capability/i })
    expect(checkbox).toBeChecked()
    expect(checkbox).toBeDisabled()
  })

  it('edits a user: reassigns family, role, and the dual-admin flag', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn().mockResolvedValue(undefined)
    const updateUser = vi.fn().mockResolvedValue({ ...USER_A, family_id: 'fam-b' })
    render(
      <UsersTab
        api={fakeApi({ updateUser })}
        families={[FAMILY_A, FAMILY_B]}
        users={[USER_A]}
        onChanged={onChanged}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.selectOptions(screen.getByLabelText('Family for guardian@example.com'), 'fam-b')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(updateUser).toHaveBeenCalledWith('user-1', {
      family_id: 'fam-b',
      role: 'guardian',
      is_admin: false,
    })
    expect(onChanged).toHaveBeenCalled()
  })

  it('forces is_admin on when the edited role is switched to admin', async () => {
    const user = userEvent.setup()
    const updateUser = vi.fn().mockResolvedValue(USER_A)
    render(
      <UsersTab
        api={fakeApi({ updateUser })}
        families={[FAMILY_A]}
        users={[USER_A]}
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.selectOptions(screen.getByLabelText('Role for guardian@example.com'), 'admin')
    const checkbox = screen.getByRole('checkbox', { name: /dual admin for/i })
    expect(checkbox).toBeChecked()
    expect(checkbox).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(updateUser).toHaveBeenCalledWith('user-1', {
      family_id: 'fam-a',
      role: 'admin',
      is_admin: true,
    })
  })

  it('cancels an in-progress edit without calling the API', async () => {
    const user = userEvent.setup()
    const updateUser = vi.fn()
    render(
      <UsersTab
        api={fakeApi({ updateUser })}
        families={[FAMILY_A]}
        users={[USER_A]}
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(updateUser).not.toHaveBeenCalled()
  })

  it('shows the self-lockout forbidden message when saving an edit fails with 403', async () => {
    const user = userEvent.setup()
    const updateUser = vi.fn().mockRejectedValue({
      isAxiosError: true,
      response: { status: 403 },
    })
    render(
      <UsersTab
        api={fakeApi({ updateUser })}
        families={[FAMILY_A]}
        users={[USER_A]}
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/cannot edit your own account/i)
  })

  it('deactivates an active user', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn().mockResolvedValue(undefined)
    const updateUser = vi.fn().mockResolvedValue({ ...USER_A, status: 'deactivated' })
    render(
      <UsersTab
        api={fakeApi({ updateUser })}
        families={[FAMILY_A]}
        users={[USER_A]}
        onChanged={onChanged}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Deactivate' }))
    expect(updateUser).toHaveBeenCalledWith('user-1', { status: 'deactivated' })
    expect(onChanged).toHaveBeenCalled()
  })

  it('shows no status button for a pending invite', () => {
    render(
      <UsersTab
        api={fakeApi()}
        families={[FAMILY_A]}
        users={[{ ...USER_A, status: 'pending' }]}
        onChanged={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: 'Deactivate' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reactivate' })).not.toBeInTheDocument()
  })

  it('shows an error when a status change fails', async () => {
    const user = userEvent.setup()
    const updateUser = vi.fn().mockRejectedValue(new Error('boom'))
    render(
      <UsersTab
        api={fakeApi({ updateUser })}
        families={[FAMILY_A]}
        users={[USER_A]}
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Deactivate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not change/i)
  })
})
