import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { UserManagementPage } from './UserManagementPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPatch = vi.fn()
const mockDelete = vi.fn()
const fakeApi = { get: mockGet, post: mockPost, patch: mockPatch, delete: mockDelete }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const FAMILY_A = {
  id: 'fam-a',
  name: 'Family A',
  status: 'active' as const,
  guardian_count: 2,
  kid_count: 1,
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

const USER_ACTIVE = {
  id: 'user-1',
  family_id: 'fam-a',
  email: 'guardian@example.com',
  role: 'guardian' as const,
  is_admin: false,
  status: 'active' as const,
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

const CONNECTION_A = {
  id: 'conn-1',
  family_id: 'fam-a',
  family_name: 'Family A',
  connected_family_id: 'fam-b',
  connected_family_name: 'Family B',
  created_at: '2026-01-03T00:00:00Z',
}

function mockGetByPath(overrides: Record<string, unknown> = {}) {
  mockGet.mockImplementation((path: string) => {
    if (path === '/v1/admin/users') {
      return Promise.resolve({ data: overrides.users ?? { users: [USER_ACTIVE] } })
    }
    if (path === '/v1/admin/profiles') {
      return Promise.resolve({ data: overrides.profiles ?? { profiles: [PROFILE_A] } })
    }
    if (path === '/v1/admin/families') {
      return Promise.resolve({
        data: overrides.families ?? { families: [FAMILY_A, FAMILY_B] },
      })
    }
    if (path === '/v1/admin/family-connections') {
      return Promise.resolve({
        data: overrides.connections ?? { connections: [CONNECTION_A] },
      })
    }
    return Promise.reject(new Error(`unexpected GET ${path}`))
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockGetByPath()
  mockPost.mockReset()
  mockPatch.mockReset()
  mockDelete.mockReset()
})

describe('UserManagementPage', () => {
  it('loads all four lists and shows the Users tab by default', async () => {
    render(<UserManagementPage />)
    expect(await screen.findByText('guardian@example.com')).toBeInTheDocument()
    expect(mockGet).toHaveBeenCalledWith('/v1/admin/users', { params: undefined })
    expect(mockGet).toHaveBeenCalledWith('/v1/admin/profiles', { params: undefined })
    expect(mockGet).toHaveBeenCalledWith('/v1/admin/families')
    expect(mockGet).toHaveBeenCalledWith('/v1/admin/family-connections')
  })

  it('shows a top-level error when the initial load fails', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    render(<UserManagementPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })

  it('switches to the Kids tab and shows its data', async () => {
    const user = userEvent.setup()
    render(<UserManagementPage />)
    await screen.findByText('guardian@example.com')

    await user.click(screen.getByRole('button', { name: 'Kids' }))
    expect(await screen.findByText('Reader One')).toBeInTheDocument()
  })

  it('switches to the Families tab and shows member counts', async () => {
    const user = userEvent.setup()
    render(<UserManagementPage />)
    await screen.findByText('guardian@example.com')

    await user.click(screen.getByRole('button', { name: 'Families' }))
    const row = (await screen.findByText('Family A')).closest('tr')
    expect(row).not.toBeNull()
    expect(within(row as HTMLElement).getByText('2')).toBeInTheDocument()
    expect(within(row as HTMLElement).getByText('1')).toBeInTheDocument()
  })

  it('switches to the Family connections tab and shows the directional row', async () => {
    const user = userEvent.setup()
    render(<UserManagementPage />)
    await screen.findByText('guardian@example.com')

    await user.click(screen.getByRole('button', { name: 'Family connections' }))
    const table = await screen.findByRole('table')
    expect(within(table).getByText('Family A')).toBeInTheDocument()
    expect(within(table).getByText('Family B')).toBeInTheDocument()
  })

  it('creates a family and refreshes every list', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({
      data: { ...FAMILY_A, id: 'fam-c', name: 'New Family', guardian_count: 0, kid_count: 0 },
    })
    render(<UserManagementPage />)
    await screen.findByText('guardian@example.com')

    await user.click(screen.getByRole('button', { name: 'Families' }))
    await screen.findByText('Family A')
    await user.type(screen.getByLabelText('Name'), 'New Family')
    await user.click(screen.getByRole('button', { name: 'Create family' }))

    expect(mockPost).toHaveBeenCalledWith('/v1/admin/families', { name: 'New Family' })
    // The refresh re-fetches all four lists (initial 4 + 4 after create).
    expect(mockGet).toHaveBeenCalledTimes(8)
  })

  it('invites a guardian with the selected family and role', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({
      data: {
        id: 'user-2',
        family_id: 'fam-a',
        email: 'new@example.com',
        role: 'guardian',
        is_admin: false,
        status: 'pending',
        created_at: '2026-01-05T00:00:00Z',
      },
    })
    render(<UserManagementPage />)
    await screen.findByText('guardian@example.com')

    await user.type(screen.getByLabelText('Email'), 'new@example.com')
    await user.selectOptions(screen.getByLabelText('Family'), 'fam-a')
    await user.click(screen.getByRole('button', { name: 'Send invite' }))

    expect(mockPost).toHaveBeenCalledWith('/v1/admin/users', {
      email: 'new@example.com',
      family_id: 'fam-a',
      role: 'guardian',
      is_admin: false,
    })
  })

  it('forces the dual-admin checkbox on when role is admin', async () => {
    const user = userEvent.setup()
    render(<UserManagementPage />)
    await screen.findByText('guardian@example.com')

    await user.selectOptions(screen.getByLabelText('Role'), 'admin')
    const checkbox = screen.getByRole('checkbox', { name: /also grant admin capability/i })
    expect(checkbox).toBeChecked()
    expect(checkbox).toBeDisabled()
  })

  it('deletes a family connection', async () => {
    const user = userEvent.setup()
    mockDelete.mockResolvedValue({ data: undefined })
    render(<UserManagementPage />)
    await screen.findByText('guardian@example.com')

    await user.click(screen.getByRole('button', { name: 'Family connections' }))
    await screen.findByRole('table')
    await user.click(screen.getByRole('button', { name: 'Remove' }))

    expect(mockDelete).toHaveBeenCalledWith('/v1/admin/family-connections/conn-1')
  })

  it('shows a scoped error when creating a connection fails, keeping the page usable', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue(new Error('network down'))
    render(<UserManagementPage />)
    await screen.findByText('guardian@example.com')

    await user.click(screen.getByRole('button', { name: 'Family connections' }))
    const table = await screen.findByRole('table')
    await user.selectOptions(screen.getByLabelText('Family'), 'fam-a')
    await user.selectOptions(screen.getByLabelText('Sees recommendations from'), 'fam-b')
    await user.click(screen.getByRole('button', { name: 'Create connection' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not create/i)
    // Page stays on the connections tab with its table still rendered.
    expect(within(table).getByText('Family A')).toBeInTheDocument()
  })
})
