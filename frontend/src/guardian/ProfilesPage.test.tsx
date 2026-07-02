import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ProfilesPage } from './ProfilesPage'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPatch = vi.fn()
const fakeApi = { get: mockGet, post: mockPost, patch: mockPatch }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const readerA = {
  id: 'p1',
  display_name: 'Reader A',
  age_band: '10-13',
  reading_level_cap: 99,
  avatar: 'fox',
  tts_enabled: false,
  created_at: '2026-07-02T00:00:00Z',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ProfilesPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockGet.mockReset().mockResolvedValue({ data: { profiles: [readerA] } })
  mockPost.mockReset()
  mockPatch.mockReset()
})

describe('ProfilesPage', () => {
  it('lists profiles with their caps', async () => {
    renderPage()
    expect(await screen.findByText('Reader A')).toBeInTheDocument()
    expect(screen.getByText(/Ages 10-13/)).toBeInTheDocument()
    expect(screen.getByText(/Ages 10-13 · Reading cap 99/)).toBeInTheDocument()
  })

  it('creates a profile through the dialog', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({
      data: { ...readerA, id: 'p2', display_name: 'Nova', age_band: '5-8', avatar: null },
    })
    renderPage()
    await user.click(await screen.findByRole('button', { name: /Add child/i }))
    await user.type(screen.getByLabelText(/Name/i), 'Nova')
    await user.selectOptions(screen.getByLabelText(/Age band/i), '5-8')
    await user.click(screen.getByRole('button', { name: /Save/i }))
    expect(mockPost).toHaveBeenCalledWith(
      '/v1/profiles',
      expect.objectContaining({ display_name: 'Nova', age_band: '5-8', avatar: null })
    )
    expect(await screen.findByText('Nova')).toBeInTheDocument()
  })

  it('edits caps through the dialog', async () => {
    const user = userEvent.setup()
    mockPatch.mockResolvedValue({
      data: { ...readerA, reading_level_cap: 4.5 },
    })
    renderPage()
    await user.click(await screen.findByRole('button', { name: /Edit Reader A/i }))
    const cap = screen.getByLabelText(/Reading level cap/i)
    await user.clear(cap)
    await user.type(cap, '4.5')
    await user.click(screen.getByRole('button', { name: /Save/i }))
    expect(mockPatch).toHaveBeenCalledWith(
      '/v1/profiles/p1',
      expect.objectContaining({ reading_level_cap: 4.5 })
    )
  })

  it('surfaces a create failure without closing silently', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue(new Error('boom'))
    renderPage()
    await user.click(await screen.findByRole('button', { name: /Add child/i }))
    await user.type(screen.getByLabelText(/Name/i), 'Nova')
    await user.click(screen.getByRole('button', { name: /Save/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save/i)
  })

  it('shows the load-failure alert when the list request fails', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    renderPage()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })

  it('shows the empty state when the family has no profiles', async () => {
    mockGet.mockResolvedValue({ data: { profiles: [] } })
    renderPage()
    expect(await screen.findByText('No profiles yet')).toBeInTheDocument()
  })

  it('surfaces an edit failure without closing silently', async () => {
    const user = userEvent.setup()
    mockPatch.mockRejectedValue(new Error('boom'))
    renderPage()
    await user.click(await screen.findByRole('button', { name: /Edit Reader A/i }))
    await user.click(screen.getByRole('button', { name: /Save/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save/i)
    expect(screen.getByText(/Ages 10-13 · Reading cap 99/)).toBeInTheDocument()
  })

  it('sends the picked avatar id from the radio group', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({
      data: { ...readerA, id: 'p3', display_name: 'Ivy', avatar: 'owl' },
    })
    renderPage()
    await user.click(await screen.findByRole('button', { name: /Add child/i }))
    await user.type(screen.getByLabelText(/Name/i), 'Ivy')
    await user.click(screen.getByRole('radio', { name: /Owl/i }))
    await user.click(screen.getByRole('button', { name: /Save/i }))
    expect(mockPost).toHaveBeenCalledWith(
      '/v1/profiles',
      expect.objectContaining({ display_name: 'Ivy', avatar: 'owl' })
    )
  })

  it('sends the read-aloud toggle state', async () => {
    const user = userEvent.setup()
    mockPatch.mockResolvedValue({
      data: { ...readerA, tts_enabled: true },
    })
    renderPage()
    await user.click(await screen.findByRole('button', { name: /Edit Reader A/i }))
    await user.click(screen.getByRole('checkbox', { name: /Read-aloud/i }))
    await user.click(screen.getByRole('button', { name: /Save/i }))
    expect(mockPatch).toHaveBeenCalledWith(
      '/v1/profiles/p1',
      expect.objectContaining({ tts_enabled: true })
    )
    expect(await screen.findByText(/Read-aloud on/)).toBeInTheDocument()
  })

  it('disables Save while the reading cap field is empty', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /Edit Reader A/i }))
    const cap = screen.getByLabelText(/Reading level cap/i)
    await user.clear(cap)
    expect(screen.getByRole('button', { name: /Save/i })).toBeDisabled()
    await user.type(cap, '7')
    expect(screen.getByRole('button', { name: /Save/i })).toBeEnabled()
  })
})
