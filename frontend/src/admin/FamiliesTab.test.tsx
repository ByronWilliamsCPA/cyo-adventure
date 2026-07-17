import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { FamiliesTab } from './FamiliesTab'
import type { UserManagementApi } from './userManagementApi'

const FAMILY_A = {
  id: 'fam-a',
  name: 'Family A',
  status: 'active' as const,
  guardian_count: 2,
  kid_count: 1,
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

describe('FamiliesTab', () => {
  it('renders the empty state with no families', () => {
    const onChanged = vi.fn()
    render(<FamiliesTab api={fakeApi()} families={[]} onChanged={onChanged} />)
    expect(screen.getByText(/no families yet/i)).toBeInTheDocument()
  })

  it('renders a family row with counts and status', () => {
    render(<FamiliesTab api={fakeApi()} families={[FAMILY_A]} onChanged={vi.fn()} />)
    expect(screen.getByText('Family A')).toBeInTheDocument()
    expect(screen.getByText('active')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('creates a family and calls onChanged', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn().mockResolvedValue(undefined)
    const createFamily = vi.fn().mockResolvedValue({ ...FAMILY_A, id: 'fam-b', name: 'New' })
    render(<FamiliesTab api={fakeApi({ createFamily })} families={[]} onChanged={onChanged} />)

    await user.type(screen.getByLabelText('Name'), 'New')
    await user.click(screen.getByRole('button', { name: 'Create family' }))

    expect(createFamily).toHaveBeenCalledWith({ name: 'New' })
    expect(onChanged).toHaveBeenCalled()
  })

  it('shows a forbidden message when create fails with 403', async () => {
    const user = userEvent.setup()
    const createFamily = vi.fn().mockRejectedValue({
      isAxiosError: true,
      response: { status: 403 },
    })
    render(
      <FamiliesTab api={fakeApi({ createFamily })} families={[]} onChanged={vi.fn()} />,
    )
    await user.type(screen.getByLabelText('Name'), 'New')
    await user.click(screen.getByRole('button', { name: 'Create family' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/only an admin can create/i)
  })

  it('renames a family via the inline edit row', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn().mockResolvedValue(undefined)
    const updateFamily = vi.fn().mockResolvedValue({ ...FAMILY_A, name: 'Renamed' })
    render(
      <FamiliesTab
        api={fakeApi({ updateFamily })}
        families={[FAMILY_A]}
        onChanged={onChanged}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Rename' }))
    const input = screen.getByLabelText('Rename Family A')
    await user.clear(input)
    await user.type(input, 'Renamed')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(updateFamily).toHaveBeenCalledWith('fam-a', { name: 'Renamed' })
    expect(onChanged).toHaveBeenCalled()
  })

  it('cancels an in-progress rename without calling the API', async () => {
    const user = userEvent.setup()
    const updateFamily = vi.fn()
    render(
      <FamiliesTab api={fakeApi({ updateFamily })} families={[FAMILY_A]} onChanged={vi.fn()} />,
    )
    await user.click(screen.getByRole('button', { name: 'Rename' }))
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByLabelText('Rename Family A')).not.toBeInTheDocument()
    expect(updateFamily).not.toHaveBeenCalled()
  })

  it('shows an error when rename fails', async () => {
    const user = userEvent.setup()
    const updateFamily = vi.fn().mockRejectedValue(new Error('network down'))
    render(
      <FamiliesTab api={fakeApi({ updateFamily })} families={[FAMILY_A]} onChanged={vi.fn()} />,
    )
    await user.click(screen.getByRole('button', { name: 'Rename' }))
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not rename/i)
  })

  it('deactivates an active family', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn().mockResolvedValue(undefined)
    const updateFamily = vi.fn().mockResolvedValue({ ...FAMILY_A, status: 'deactivated' })
    render(
      <FamiliesTab
        api={fakeApi({ updateFamily })}
        families={[FAMILY_A]}
        onChanged={onChanged}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Deactivate' }))
    expect(updateFamily).toHaveBeenCalledWith('fam-a', { status: 'deactivated' })
    expect(onChanged).toHaveBeenCalled()
  })

  it('reactivates a deactivated family', async () => {
    const user = userEvent.setup()
    const updateFamily = vi.fn().mockResolvedValue({ ...FAMILY_A, status: 'active' })
    render(
      <FamiliesTab
        api={fakeApi({ updateFamily })}
        families={[{ ...FAMILY_A, status: 'deactivated' }]}
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Reactivate' }))
    expect(updateFamily).toHaveBeenCalledWith('fam-a', { status: 'active' })
  })

  it('shows an error when a status change fails', async () => {
    const user = userEvent.setup()
    const updateFamily = vi.fn().mockRejectedValue(new Error('boom'))
    render(
      <FamiliesTab api={fakeApi({ updateFamily })} families={[FAMILY_A]} onChanged={vi.fn()} />,
    )
    await user.click(screen.getByRole('button', { name: 'Deactivate' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not change/i)
  })
})
