import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { ProviderAllowlistPage } from './ProviderAllowlistPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
const mockDelete = vi.fn()
const fakeApi = { get: mockGet, post: mockPost, put: mockPut, delete: mockDelete }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const ONE_ROW = {
  rows: [
    {
      id: 'a1',
      provider: 'anthropic',
      model_id: 'claude-sonnet-4-6',
      enabled: true,
      display_name: 'Claude Sonnet 4.6 (direct)',
    },
  ],
}

function mockList(data: unknown = ONE_ROW) {
  mockGet.mockImplementation(() => Promise.resolve({ data }))
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ProviderAllowlistPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockPut.mockReset()
  mockDelete.mockReset()
  mockList()
})

describe('ProviderAllowlistPage', () => {
  it('renders existing allowlist rows', async () => {
    renderPage()
    expect(await screen.findByText('claude-sonnet-4-6')).toBeInTheDocument()
    expect(screen.getByText('Claude Sonnet 4.6 (direct)')).toBeInTheDocument()
    expect(screen.getByText('Enabled')).toBeInTheDocument()
  })

  it('shows the empty state when there are no rows', async () => {
    mockList({ rows: [] })
    renderPage()
    expect(await screen.findByText('No allowlist entries yet.')).toBeInTheDocument()
  })

  it('adds a new entry and refreshes the list', async () => {
    mockPost.mockResolvedValue({
      data: { id: 'a2', provider: 'ollama', model_id: 'qwen2.5:14b', enabled: true, display_name: null },
    })
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('claude-sonnet-4-6')

    await user.selectOptions(screen.getByLabelText('Provider'), 'ollama')
    await user.type(screen.getByLabelText('Model id'), 'qwen2.5:14b')
    await user.click(screen.getByRole('button', { name: 'Add to allowlist' }))

    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/admin/provider-allowlist', {
        provider: 'ollama',
        model_id: 'qwen2.5:14b',
        display_name: null,
      })
    )
  })

  it('toggles a row disabled', async () => {
    mockPut.mockResolvedValue({ data: { ...ONE_ROW.rows[0], enabled: false } })
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('claude-sonnet-4-6')

    await user.click(screen.getByRole('button', { name: 'Disable claude-sonnet-4-6' }))

    await waitFor(() =>
      expect(mockPut).toHaveBeenCalledWith('/v1/admin/provider-allowlist/a1', {
        enabled: false,
        display_name: 'Claude Sonnet 4.6 (direct)',
      })
    )
  })

  it('removes a row', async () => {
    mockDelete.mockResolvedValue({ data: { rows: [] } })
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('claude-sonnet-4-6')

    await user.click(screen.getByRole('button', { name: 'Remove claude-sonnet-4-6' }))

    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('/v1/admin/provider-allowlist/a1'))
    expect(await screen.findByText('No allowlist entries yet.')).toBeInTheDocument()
  })

  it('shows a generic error state on load failure', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    renderPage()
    expect(
      await screen.findByText('We could not load the provider allowlist. Please reload.')
    ).toBeInTheDocument()
  })
})
