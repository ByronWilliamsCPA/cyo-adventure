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
  content_flag_caps: {},
  banned_themes: [],
  created_at: '2026-07-02T00:00:00Z',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ProfilesPage />
    </MemoryRouter>
  )
}

const EMPTY_BUDGET = { quota: 5, spent_this_month: 0, remaining: 5, children: [] }

// Routes GET calls by URL (profiles list vs. the ADR-015 G3 budget fetch),
// like IntakePage.test.tsx's getMock: the two calls now return different
// shapes, so a single shared mockResolvedValue would feed the wrong body to
// whichever call ran second.
function mockProfilesAndBudget(profiles: unknown[], budget: unknown = EMPTY_BUDGET) {
  mockGet.mockReset().mockImplementation((url: string) => {
    if (url === '/v1/profiles') return Promise.resolve({ data: { profiles } })
    if (url === '/v1/families/me/budget') return Promise.resolve({ data: budget })
    throw new Error(`unexpected GET ${url}`)
  })
}

beforeEach(() => {
  mockProfilesAndBudget([readerA])
  mockPost.mockReset()
  mockPatch.mockReset()
})

describe('ProfilesPage', () => {
  it('lists profiles with their caps', async () => {
    renderPage()
    expect(await screen.findByText('Reader A')).toBeInTheDocument()
    expect(screen.getByText(/Ages 10-13/)).toBeInTheDocument()
    expect(screen.getByText(/Ages 10-13 · No reading limit/)).toBeInTheDocument()
  })

  it('links each profile to its read-only preview route', async () => {
    renderPage()
    const link = await screen.findByRole('link', { name: /Preview as Reader A/i })
    expect(link).toHaveAttribute('href', '/guardian/preview/p1')
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
    expect(screen.getByText(/Ages 10-13 · No reading limit/)).toBeInTheDocument()
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

  // The read-aloud toggle is hidden until the reader ships read-aloud
  // support: no checkbox in the dialog, no card badge, and an edit passes the
  // stored tts_enabled value through unchanged.
  it('preselects the read-aloud checkbox and passes tts_enabled through unchanged on edit', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { profiles: [{ ...readerA, tts_enabled: true }] } })
    mockPatch.mockResolvedValue({
      data: { ...readerA, tts_enabled: true },
    })
    renderPage()
    expect(await screen.findByText('Reader A')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Edit Reader A/i }))
    expect(screen.getByRole('checkbox', { name: /Read-aloud/i })).toBeChecked()
    await user.click(screen.getByRole('button', { name: /Save/i }))
    expect(mockPatch).toHaveBeenCalledWith(
      '/v1/profiles/p1',
      expect.objectContaining({ tts_enabled: true })
    )
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

  // ADR-015 G3: the budget fetch's per-child usage rows are the only place
  // request_auto_approve round-trips (ProfileView does not carry it), so the
  // badge and the edit dialog's seeded toggle both depend on this join.
  it('shows an Auto-approve badge for a child whose budget row has it on', async () => {
    mockProfilesAndBudget([readerA], {
      quota: 5,
      spent_this_month: 1,
      remaining: 4,
      children: [
        {
          profile_id: 'p1',
          display_name: 'Reader A',
          request_auto_approve: true,
          monthly_request_envelope: 3,
          used_this_month: 1,
        },
      ],
    })
    renderPage()
    expect(await screen.findByText('Auto-approve on')).toBeInTheDocument()
  })

  it('shows no Auto-approve badge when the budget row has it off', async () => {
    renderPage()
    await screen.findByText('Reader A')
    expect(screen.queryByText('Auto-approve on')).not.toBeInTheDocument()
  })

  it('seeds the edit dialog toggle and limit from the budget row', async () => {
    const user = userEvent.setup()
    mockProfilesAndBudget([readerA], {
      quota: 5,
      spent_this_month: 1,
      remaining: 4,
      children: [
        {
          profile_id: 'p1',
          display_name: 'Reader A',
          request_auto_approve: true,
          monthly_request_envelope: 3,
          used_this_month: 1,
        },
      ],
    })
    renderPage()
    await screen.findByText('Auto-approve on')
    await user.click(screen.getByRole('button', { name: /Edit Reader A/i }))
    expect(
      screen.getByRole('checkbox', { name: /Auto-approve this child's requests/i })
    ).toBeChecked()
    expect(screen.getByLabelText(/Monthly auto-approve limit/i)).toHaveValue(3)
  })
})
