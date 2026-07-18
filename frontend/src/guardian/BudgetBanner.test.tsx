import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BudgetBanner } from './BudgetBanner'
import { STORY_REQUESTS_CHANGED_EVENT } from './storyRequestQueueApi'

const mockGet = vi.fn()
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

beforeEach(() => {
  mockGet.mockReset()
})

describe('BudgetBanner', () => {
  it('shows the normal "N of M" state', async () => {
    mockGet.mockResolvedValue({
      data: { quota: 5, spent_this_month: 2, remaining: 3, children: [] },
    })
    render(<BudgetBanner />)
    expect(await screen.findByTestId('budget-banner')).toHaveTextContent(
      '3 of 5 stories left this month'
    )
    expect(screen.getByTestId('budget-banner')).not.toHaveClass('budget-banner--warning')
  })

  it('applies the warning tone at zero remaining', async () => {
    mockGet.mockResolvedValue({
      data: { quota: 5, spent_this_month: 5, remaining: 0, children: [] },
    })
    render(<BudgetBanner />)
    const banner = await screen.findByTestId('budget-banner')
    expect(banner).toHaveTextContent('0 of 5 stories left this month')
    expect(banner).toHaveClass('budget-banner--warning')
  })

  it('renders nothing on a fetch failure', async () => {
    mockGet.mockRejectedValue({ isAxiosError: true, response: { status: 500 } })
    render(<BudgetBanner />)
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(screen.queryByTestId('budget-banner')).not.toBeInTheDocument()
  })

  it('renders nothing while loading (no flash of stale content)', () => {
    mockGet.mockImplementation(() => new Promise(() => {}))
    render(<BudgetBanner />)
    expect(screen.queryByTestId('budget-banner')).not.toBeInTheDocument()
  })

  it('refetches on STORY_REQUESTS_CHANGED_EVENT', async () => {
    mockGet.mockResolvedValueOnce({
      data: { quota: 5, spent_this_month: 2, remaining: 3, children: [] },
    })
    render(<BudgetBanner />)
    expect(await screen.findByTestId('budget-banner')).toHaveTextContent(
      '3 of 5 stories left this month'
    )

    mockGet.mockResolvedValueOnce({
      data: { quota: 5, spent_this_month: 3, remaining: 2, children: [] },
    })
    window.dispatchEvent(new Event(STORY_REQUESTS_CHANGED_EVENT))

    await waitFor(() =>
      expect(screen.getByTestId('budget-banner')).toHaveTextContent(
        '2 of 5 stories left this month'
      )
    )
  })
})
