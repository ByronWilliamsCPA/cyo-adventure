import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ModerationThresholdsPage } from './ModerationThresholdsPage'

const { mockList, mockUpsert, mockDelete } = vi.hoisted(() => ({
  mockList: vi.fn(),
  mockUpsert: vi.fn(),
  mockDelete: vi.fn(),
}))
vi.mock('../client/sdk.gen', () => ({
  listThresholdsApiV1AdminModerationThresholdsGet: mockList,
  upsertThresholdApiV1AdminModerationThresholdsAgeBandCategoryPut: mockUpsert,
  deleteThresholdApiV1AdminModerationThresholdsAgeBandCategoryDelete: mockDelete,
}))

const LIST_VIEW = {
  default_min_verdict: 'flag',
  default_min_score: null,
  known_categories: ['toxicity', 'violence'],
  rows: [{ age_band: '3-5', category: 'violence', min_verdict: 'advisory', min_score: 0.3 }],
}

beforeEach(() => {
  localStorage.clear()
  mockList.mockReset().mockResolvedValue({ data: LIST_VIEW })
  mockUpsert.mockReset()
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
    mockList.mockResolvedValue({ data: { ...LIST_VIEW, rows: [] } })
    render(<ModerationThresholdsPage />)
    expect(await screen.findByText(/no overrides yet/i)).toBeInTheDocument()
  })

  it('shows a load-failure alert when the list request fails', async () => {
    mockList.mockRejectedValue(new Error('network down'))
    render(<ModerationThresholdsPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })

  it('sends an Authorization header sourced from auth_token on every call', async () => {
    localStorage.setItem('auth_token', 'test-token-123')
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)
    expect(mockList).toHaveBeenCalledWith(
      expect.objectContaining({
        headers: { Authorization: 'Bearer test-token-123' },
        baseURL: window.location.origin,
      })
    )
  })

  it('saves a new override with the form values and refreshes the list', async () => {
    const user = userEvent.setup()
    mockUpsert.mockResolvedValue({
      data: { age_band: '5-8', category: 'gore', min_verdict: 'block', min_score: null },
    })
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    await user.selectOptions(screen.getByLabelText(/Age band/i), '5-8')
    await user.type(screen.getByLabelText(/Category/i), 'gore')
    await user.selectOptions(screen.getByLabelText(/Surfaces at/i), 'block')
    await user.click(screen.getByRole('button', { name: /Save override/i }))

    expect(mockUpsert).toHaveBeenCalledWith(
      expect.objectContaining({
        path: { age_band: '5-8', category: 'gore' },
        body: { min_verdict: 'block', min_score: null },
      })
    )
    expect(mockList).toHaveBeenCalledTimes(2)
  })

  it('surfaces a save failure without losing the existing rows', async () => {
    const user = userEvent.setup()
    mockUpsert.mockRejectedValue(new Error('boom'))
    render(<ModerationThresholdsPage />)
    await screen.findByText(/surface to families at/i)

    await user.type(screen.getByLabelText(/Category/i), 'gore')
    await user.click(screen.getByRole('button', { name: /Save override/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not save/i)
    expect(screen.getByText('violence')).toBeInTheDocument()
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

    expect(mockDelete).toHaveBeenCalledWith(
      expect.objectContaining({ path: { age_band: '3-5', category: 'violence' } })
    )
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
