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

beforeEach(() => {
  localStorage.clear()
  mockGet.mockReset().mockResolvedValue({ data: LIST_VIEW })
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
    mockGet.mockResolvedValue({ data: { ...LIST_VIEW, rows: [] } })
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

  it('saves a new override with the form values and refreshes the list', async () => {
    const user = userEvent.setup()
    mockPut.mockResolvedValue({
      data: { age_band: '5-8', category: 'gore', min_verdict: 'block', min_score: null },
    })
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    await user.selectOptions(screen.getByLabelText(/Age band/i), '5-8')
    await user.type(screen.getByLabelText(/Category/i), 'gore')
    await user.selectOptions(screen.getByLabelText(/Surfaces at/i), 'block')
    await user.click(screen.getByRole('button', { name: /Save override/i }))

    expect(mockPut).toHaveBeenCalledWith('/v1/admin/moderation-thresholds/5-8/gore', {
      min_verdict: 'block',
      min_score: null,
    })
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('surfaces a save failure without losing the existing rows', async () => {
    const user = userEvent.setup()
    mockPut.mockRejectedValue(new Error('boom'))
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    await user.type(screen.getByLabelText(/Category/i), 'gore')
    await user.click(screen.getByRole('button', { name: /Save override/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save/i)
    expect(screen.getByText('violence')).toBeInTheDocument()
  })

  it('surfaces a post-save refresh failure as a scoped alert without losing the table', async () => {
    const user = userEvent.setup()
    mockPut.mockResolvedValue({
      data: { age_band: '5-8', category: 'gore', min_verdict: 'block', min_score: null },
    })
    // First call (initial load) succeeds; second call (post-save refresh) fails.
    mockGet.mockReset()
    mockGet.mockResolvedValueOnce({ data: LIST_VIEW }).mockRejectedValueOnce(new Error('boom'))
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    await user.type(screen.getByLabelText(/Category/i), 'gore')
    await user.click(screen.getByRole('button', { name: /Save override/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not refresh/i)
    // The table (from the last known-good state) must still be visible, not
    // replaced by the top-level error page.
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

  it('removes an override using its row key and applies the returned list', async () => {
    const user = userEvent.setup()
    mockDelete.mockResolvedValue({ data: { ...LIST_VIEW, rows: [] } })
    render(<ModerationThresholdsPage />)
    await screen.findByText('violence')

    await user.click(screen.getByRole('button', { name: /Remove violence override for 3-5/i }))

    expect(mockDelete).toHaveBeenCalledWith('/v1/admin/moderation-thresholds/3-5/violence')
    expect(await screen.findByText(/no overrides yet/i)).toBeInTheDocument()
  })

  it('surfaces a delete failure without losing the existing rows', async () => {
    const user = userEvent.setup()
    mockDelete.mockRejectedValue(new Error('boom'))
    render(<ModerationThresholdsPage />)
    await screen.findByText('violence')

    await user.click(screen.getByRole('button', { name: /Remove violence override for 3-5/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not remove/i)
    expect(screen.getByText('violence')).toBeInTheDocument()
  })
})
