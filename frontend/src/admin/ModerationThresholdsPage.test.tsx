import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ModerationThresholdsPage } from './ModerationThresholdsPage'

const mockGet = vi.fn()
const mockPut = vi.fn()
const mockDelete = vi.fn()
const fakeApi = { get: mockGet, put: mockPut, delete: mockDelete }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const LIST_VIEW = {
  default_min_verdict: 'flag',
  default_min_score: null,
  known_categories: ['toxicity', 'violence'],
  rows: [{ age_band: '3-5', category: 'violence', min_verdict: 'advisory', min_score: 0.3 }],
}

const NOISE_FLOOR_VIEW = { value: 0.05 }

// The initial load fires GET requests to both the threshold list and the
// noise-floor endpoints (Promise.all in the page); route each mock by path so
// order does not matter.
function mockGetByPath(overrides: Record<string, unknown> = {}) {
  mockGet.mockImplementation((path: string) => {
    if (path === '/v1/admin/moderation/noise-floor') {
      return Promise.resolve({ data: overrides.noiseFloor ?? NOISE_FLOOR_VIEW })
    }
    return Promise.resolve({ data: overrides.list ?? LIST_VIEW })
  })
}

beforeEach(() => {
  localStorage.clear()
  mockGet.mockReset()
  mockGetByPath()
  mockPut.mockReset()
  mockDelete.mockReset()
})

describe('ModerationThresholdsPage', () => {
  it('renders the default policy and override rows', async () => {
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)
    expect(screen.getByText('violence')).toBeInTheDocument()
    expect(screen.getByText('0.3')).toBeInTheDocument()
  })

  it('shows the empty state when there are no overrides', async () => {
    mockGetByPath({ list: { ...LIST_VIEW, rows: [] } })
    render(<ModerationThresholdsPage />)
    expect(await screen.findByText(/no overrides yet/i)).toBeInTheDocument()
  })

  it('shows a load-failure alert when the list request fails', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    render(<ModerationThresholdsPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })

  it('fetches the list from the admin moderation-thresholds endpoint', async () => {
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)
    expect(mockGet).toHaveBeenCalledWith('/v1/admin/moderation-thresholds')
  })

  it('saves a known-category override directly and refreshes the list', async () => {
    const user = userEvent.setup()
    mockPut.mockResolvedValue({
      data: { age_band: '5-8', category: 'toxicity', min_verdict: 'block', min_score: null },
    })
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    await user.selectOptions(screen.getByLabelText(/Age band/i), '5-8')
    await user.type(screen.getByLabelText(/Category/i), 'toxicity')
    await user.selectOptions(screen.getByLabelText(/Surfaces at/i), 'block')
    await user.click(screen.getByRole('button', { name: /Save override/i }))

    // A known category needs no extra confirmation step.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    // category rides as a query param (slash-containing categories cannot
    // travel in a path segment).
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut).toHaveBeenCalledWith(
      '/v1/admin/moderation-thresholds/5-8',
      { min_verdict: 'block', min_score: null },
      { params: { category: 'toxicity' } }
    )
    // Initial load fires 2 GETs (list + noise floor); the post-save refresh
    // fires 1 more (list only).
    expect(mockGet).toHaveBeenCalledTimes(3)
  })

  it('asks for confirmation before saving an unknown-category override', async () => {
    const user = userEvent.setup()
    mockPut.mockResolvedValue({
      data: { age_band: '3-5', category: 'gore', min_verdict: 'advisory', min_score: null },
    })
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    await user.type(screen.getByLabelText(/Category/i), 'gore')
    await user.click(screen.getByRole('button', { name: /Save override/i }))

    // 'gore' is not in known_categories, so nothing fires yet; a confirm
    // dialog explains the never-matches risk first.
    expect(mockPut).not.toHaveBeenCalled()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent("Create override for new category 'gore'?")
    expect(dialog).toHaveTextContent(/only applies if classifiers emit this exact name/i)

    await user.click(screen.getByRole('button', { name: /Create new-category override/i }))
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut).toHaveBeenCalledWith(
      '/v1/admin/moderation-thresholds/3-5',
      { min_verdict: 'advisory', min_score: null },
      { params: { category: 'gore' } }
    )
  })

  it('cancelling the unknown-category confirm fires no save', async () => {
    const user = userEvent.setup()
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    await user.type(screen.getByLabelText(/Category/i), 'gore')
    await user.click(screen.getByRole('button', { name: /Save override/i }))
    await user.click(screen.getByRole('button', { name: /Cancel/i }))

    expect(mockPut).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    // The form keeps its values so the admin can fix the typo.
    expect(screen.getByLabelText(/Category/i)).toHaveValue('gore')
  })

  it('surfaces a save failure without losing the existing rows', async () => {
    const user = userEvent.setup()
    mockPut.mockRejectedValue(new Error('boom'))
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    await user.type(screen.getByLabelText(/Category/i), 'toxicity')
    await user.click(screen.getByRole('button', { name: /Save override/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save/i)
    expect(screen.getByText('violence')).toBeInTheDocument()
  })

  it('surfaces a post-save refresh failure as a scoped alert without losing the table', async () => {
    const user = userEvent.setup()
    mockPut.mockResolvedValue({
      data: { age_band: '5-8', category: 'toxicity', min_verdict: 'block', min_score: null },
    })
    // Initial load's list + noise-floor GETs succeed; the post-save refresh's
    // list GET (the second call to the list path) fails.
    let listCalls = 0
    mockGet.mockReset()
    mockGet.mockImplementation((path: string) => {
      if (path === '/v1/admin/moderation/noise-floor') {
        return Promise.resolve({ data: NOISE_FLOOR_VIEW })
      }
      listCalls += 1
      return listCalls === 1
        ? Promise.resolve({ data: LIST_VIEW })
        : Promise.reject(new Error('boom'))
    })
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    await user.type(screen.getByLabelText(/Category/i), 'toxicity')
    await user.click(screen.getByRole('button', { name: /Save override/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not refresh/i)
    // The table (from the last known-good state) must still be visible, not
    // replaced by the top-level error page.
    expect(screen.getByText('violence')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save override/i })).toBeInTheDocument()
  })

  it('renders the current admin noise floor from the mocked GET', async () => {
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)
    expect(screen.getByLabelText(/Noise floor/i)).toHaveValue(0.05)
  })

  it('confirms a noise-floor save with the concrete consequence, then PUTs once', async () => {
    const user = userEvent.setup()
    mockPut.mockResolvedValue({ data: { value: 0.2 } })
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    const floorInput = screen.getByLabelText(/Noise floor/i)
    await user.clear(floorInput)
    await user.type(floorInput, '0.2')
    await user.click(screen.getByRole('button', { name: /Save noise floor/i }))

    // Nothing fires until the consequence is confirmed.
    expect(mockPut).not.toHaveBeenCalled()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent(
      'Advisory findings scoring below 0.2 will be hidden from reviewers on the review surface.'
    )
    // 0.2 is at or below the 0.3 warning line, so no extra warning shows.
    expect(dialog).not.toHaveTextContent(/hide most advisory findings/i)

    await user.click(screen.getByRole('button', { name: /Confirm noise floor/i }))
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut).toHaveBeenCalledWith('/v1/admin/moderation/noise-floor', { value: 0.2 })
  })

  it('warns inside the noise-floor confirm when the value is above 0.3', async () => {
    const user = userEvent.setup()
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    const floorInput = screen.getByLabelText(/Noise floor/i)
    await user.clear(floorInput)
    await user.type(floorInput, '0.4')
    await user.click(screen.getByRole('button', { name: /Save noise floor/i }))

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent(
      'Advisory findings scoring below 0.4 will be hidden from reviewers on the review surface.'
    )
    expect(dialog).toHaveTextContent(/will hide most advisory findings/i)
  })

  it('does not warn inside the noise-floor confirm when the value is exactly the 0.3 boundary', async () => {
    const user = userEvent.setup()
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    const floorInput = screen.getByLabelText(/Noise floor/i)
    await user.clear(floorInput)
    await user.type(floorInput, '0.3')
    await user.click(screen.getByRole('button', { name: /Save noise floor/i }))

    // The warning gate is a strict "> 0.3", so the boundary value itself
    // must not trip it.
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent(
      'Advisory findings scoring below 0.3 will be hidden from reviewers on the review surface.'
    )
    expect(dialog).not.toHaveTextContent(/will hide most advisory findings/i)
  })

  it('cancelling the noise-floor confirm fires no PUT', async () => {
    const user = userEvent.setup()
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    const floorInput = screen.getByLabelText(/Noise floor/i)
    await user.clear(floorInput)
    await user.type(floorInput, '0.2')
    await user.click(screen.getByRole('button', { name: /Save noise floor/i }))
    await user.click(screen.getByRole('button', { name: /Cancel/i }))

    expect(mockPut).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('surfaces a noise-floor save failure as a scoped alert without wiping the page', async () => {
    const user = userEvent.setup()
    mockPut.mockRejectedValue(new Error('boom'))
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    const floorInput = screen.getByLabelText(/Noise floor/i)
    await user.clear(floorInput)
    await user.type(floorInput, '0.3')
    await user.click(screen.getByRole('button', { name: /Save noise floor/i }))
    await user.click(screen.getByRole('button', { name: /Confirm noise floor/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save the noise floor/i)
    // The rest of the page (table, override form) must stay visible.
    expect(screen.getByText('violence')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save override/i })).toBeInTheDocument()
  })

  it('disables Save while the score floor is out of range', async () => {
    const user = userEvent.setup()
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    await user.type(screen.getByLabelText(/Category/i), 'gore')
    const scoreInput = screen.getByLabelText(/Score floor/i)
    await user.type(scoreInput, '1.5')
    expect(screen.getByRole('button', { name: /Save override/i })).toBeDisabled()
  })

  it('confirms a removal naming the default it reverts to, then deletes once', async () => {
    const user = userEvent.setup()
    mockDelete.mockResolvedValue({ data: { ...LIST_VIEW, rows: [] } })
    render(<ModerationThresholdsPage />)
    await screen.findByText('violence')

    await user.click(screen.getByRole('button', { name: /Remove violence override for 3-5/i }))

    // Nothing fires until the consequence is confirmed; the dialog names the
    // actual default surfacing level from page state (LIST_VIEW's 'flag').
    expect(mockDelete).not.toHaveBeenCalled()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent(
      'violence findings for 3-5 revert to the default surfacing level: flag'
    )

    await user.click(screen.getByRole('button', { name: /Confirm remove/i }))
    expect(mockDelete).toHaveBeenCalledTimes(1)
    expect(mockDelete).toHaveBeenCalledWith('/v1/admin/moderation-thresholds/3-5', {
      params: { category: 'violence' },
    })
    expect(await screen.findByText(/no overrides yet/i)).toBeInTheDocument()
  })

  it('cancelling the remove confirm fires no delete and keeps the row', async () => {
    const user = userEvent.setup()
    render(<ModerationThresholdsPage />)
    await screen.findByText('violence')

    await user.click(screen.getByRole('button', { name: /Remove violence override for 3-5/i }))
    await user.click(screen.getByRole('button', { name: /Cancel/i }))

    expect(mockDelete).not.toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText('violence')).toBeInTheDocument()
  })

  it('surfaces a delete failure without losing the existing rows', async () => {
    const user = userEvent.setup()
    mockDelete.mockRejectedValue(new Error('boom'))
    render(<ModerationThresholdsPage />)
    await screen.findByText('violence')

    await user.click(screen.getByRole('button', { name: /Remove violence override for 3-5/i }))
    await user.click(screen.getByRole('button', { name: /Confirm remove/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not remove/i)
    expect(screen.getByText('violence')).toBeInTheDocument()
  })
})
