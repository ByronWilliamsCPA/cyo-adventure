import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

  it('shows a generic error state when the load rejects with a non-Error value', async () => {
    // #EDGE: data-integrity: mirrors the non-Error-rejection case covered on
    // AuthoringQueuePage for the same `err instanceof Error` guard.
    // #VERIFY: covered here by rejecting with a plain string.
    mockGet.mockRejectedValue('boom')
    renderPage()
    expect(
      await screen.findByText('We could not load the provider allowlist. Please reload.')
    ).toBeInTheDocument()
  })

  it('renders a disabled row with no display name using its fallback label and button copy', async () => {
    mockList({
      rows: [{ id: 'a1', provider: 'anthropic', model_id: 'claude-sonnet-4-6', enabled: false, display_name: null }],
    })
    renderPage()
    expect(await screen.findByText('claude-sonnet-4-6')).toBeInTheDocument()
    expect(screen.getByText('-')).toBeInTheDocument()
    expect(screen.getByText('Disabled')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enable claude-sonnet-4-6' })).toBeInTheDocument()
  })

  it('leaves the Add to allowlist submit a no-op while the model id is blank', async () => {
    // The submit button is disabled while canAdd is false, but the form can
    // still receive a native submit event (e.g. Enter in another field); the
    // handler's own `if (!canAdd) return` guard must short-circuit before
    // calling the API.
    renderPage()
    await screen.findByText('claude-sonnet-4-6')
    const form = screen.getByRole('button', { name: 'Add to allowlist' }).closest('form')
    if (form === null) throw new Error('expected the Add to allowlist button to be inside a form')
    fireEvent.submit(form)
    await waitFor(() => expect(mockPost).not.toHaveBeenCalled())
  })

  it('surfaces an add failure without losing the existing rows', async () => {
    mockPost.mockRejectedValue(new Error('boom'))
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('claude-sonnet-4-6')

    await user.type(screen.getByLabelText('Model id'), 'qwen2.5:14b')
    await user.click(screen.getByRole('button', { name: 'Add to allowlist' }))

    expect(
      await screen.findByText('We could not add that entry. It may already be on the allowlist.')
    ).toBeInTheDocument()
    expect(screen.getByText('claude-sonnet-4-6')).toBeInTheDocument()
  })

  it('surfaces a toggle failure', async () => {
    mockPut.mockRejectedValue(new Error('boom'))
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('claude-sonnet-4-6')

    await user.click(screen.getByRole('button', { name: 'Disable claude-sonnet-4-6' }))

    expect(
      await screen.findByText('We could not update that entry. Please try again.')
    ).toBeInTheDocument()
  })

  it('surfaces a remove failure', async () => {
    mockDelete.mockRejectedValue(new Error('boom'))
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('claude-sonnet-4-6')

    await user.click(screen.getByRole('button', { name: 'Remove claude-sonnet-4-6' }))

    expect(
      await screen.findByText('We could not remove that entry. Please try again.')
    ).toBeInTheDocument()
  })

  it('surfaces a refresh failure after a successful add, without discarding the saved change', async () => {
    // create() succeeds, but the follow-up list() refresh fails: the row was
    // saved server-side, so this must show the softer "reload to see it"
    // copy via refreshAfterMutation's own catch, distinct from the initial
    // load and add-failure error strings above.
    mockPost.mockResolvedValue({
      data: { id: 'a2', provider: 'ollama', model_id: 'qwen2.5:14b', enabled: true, display_name: null },
    })
    let getCalls = 0
    mockGet.mockImplementation(() => {
      getCalls += 1
      if (getCalls === 1) return Promise.resolve({ data: ONE_ROW })
      return Promise.reject(new Error('refresh down'))
    })
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('claude-sonnet-4-6')

    await user.type(screen.getByLabelText('Model id'), 'qwen2.5:14b')
    await user.click(screen.getByRole('button', { name: 'Add to allowlist' }))

    expect(
      await screen.findByText('That change saved, but the list could not refresh. Reload to see it.')
    ).toBeInTheDocument()
  })
})
