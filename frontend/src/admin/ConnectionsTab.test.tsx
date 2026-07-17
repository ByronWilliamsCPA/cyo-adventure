import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ConnectionsTab } from './ConnectionsTab'
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
  guardian_count: 1,
  kid_count: 0,
  created_at: '2026-01-02T00:00:00Z',
}

const CONNECTION_A = {
  id: 'conn-1',
  family_id: 'fam-a',
  family_name: 'Family A',
  connected_family_id: 'fam-b',
  connected_family_name: 'Family B',
  created_at: '2026-01-03T00:00:00Z',
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

describe('ConnectionsTab', () => {
  it('renders the empty state with no connections', () => {
    render(
      <ConnectionsTab
        api={fakeApi()}
        families={[FAMILY_A, FAMILY_B]}
        connections={[]}
        onChanged={vi.fn()}
      />,
    )
    expect(screen.getByText(/no family connections yet/i)).toBeInTheDocument()
  })

  it('shows the self-connection warning and disables Create when both selects match', async () => {
    const user = userEvent.setup()
    render(
      <ConnectionsTab
        api={fakeApi()}
        families={[FAMILY_A, FAMILY_B]}
        connections={[]}
        onChanged={vi.fn()}
      />,
    )
    await user.selectOptions(screen.getByLabelText('Family'), 'fam-a')
    await user.selectOptions(screen.getByLabelText('Sees recommendations from'), 'fam-a')

    expect(screen.getByText(/cannot connect to itself/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create connection' })).toBeDisabled()
  })

  it('shows an error when deleting a connection fails', async () => {
    const user = userEvent.setup()
    const deleteConnection = vi.fn().mockRejectedValue(new Error('boom'))
    render(
      <ConnectionsTab
        api={fakeApi({ deleteConnection })}
        families={[FAMILY_A, FAMILY_B]}
        connections={[CONNECTION_A]}
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Remove' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not remove/i)
  })
})
