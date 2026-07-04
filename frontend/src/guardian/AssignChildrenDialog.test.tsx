import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AssignChildrenDialog } from './AssignChildrenDialog'

const mockGet = vi.fn()
const mockPost = vi.fn()
const fakeApi = { get: mockGet, post: mockPost }
vi.mock('../hooks/useApi', () => ({ useApi: () => fakeApi }))

const PROFILES = {
  profiles: [
    { id: 'p1', display_name: 'Reader A', age_band: '10-13', reading_level_cap: 99,
      avatar: 'fox', tts_enabled: false, created_at: '2026-07-02T00:00:00Z' },
    { id: 'p2', display_name: 'Reader A2', age_band: '8-11', reading_level_cap: 99,
      avatar: 'owl', tts_enabled: false, created_at: '2026-07-02T00:00:00Z' },
  ],
}

const CONTENT_SUMMARY = {
  storybook_id: 's1',
  version: 1,
  screened: true,
  summary: {
    count: 1,
    hard_block: false,
    soft_flag: true,
    repaired: false,
    reviewer_independent: true,
  },
  flagged_count: 2,
  findings: [{ category: 'coherence', verdict: 'advisory', message: 'slightly disjoint' }],
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  // /content-summary -> tags; /assignments -> current assignments; else profiles.
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/content-summary'))
      return Promise.resolve({ data: CONTENT_SUMMARY })
    if (url.includes('/assignments'))
      return Promise.resolve({ data: { storybook_id: 's1', profile_ids: ['p1'] } })
    return Promise.resolve({ data: PROFILES })
  })
})

describe('AssignChildrenDialog', () => {
  it('shows already-assigned children checked and disabled', async () => {
    render(<AssignChildrenDialog storybookId="s1" onClose={vi.fn()} />)
    const readerA = await screen.findByRole('checkbox', { name: /Reader A$/ })
    expect(readerA).toBeChecked()
    expect(readerA).toBeDisabled()
    const readerA2 = screen.getByRole('checkbox', { name: /Reader A2/ })
    expect(readerA2).not.toBeChecked()
    expect(readerA2).toBeEnabled()
  })

  it('posts only newly selected ids on save', async () => {
    const user = userEvent.setup()
    mockPost.mockResolvedValue({ data: { storybook_id: 's1', profile_ids: ['p1', 'p2'] } })
    const onClose = vi.fn()
    render(<AssignChildrenDialog storybookId="s1" onClose={onClose} />)
    await user.click(await screen.findByRole('checkbox', { name: /Reader A2/ }))
    await user.click(screen.getByRole('button', { name: /Assign/i }))
    await waitFor(() =>
      expect(mockPost).toHaveBeenCalledWith('/v1/storybooks/s1/assignments', {
        profile_ids: ['p2'],
      })
    )
    expect(onClose).toHaveBeenCalled()
  })

  it('disables Assign and fires no POST when nothing new is selected', async () => {
    const user = userEvent.setup()
    // Every shown profile is already assigned, so no NEW id can be picked.
    mockGet.mockImplementation((url: string) =>
      url.includes('/assignments')
        ? Promise.resolve({ data: { storybook_id: 's1', profile_ids: ['p1', 'p2'] } })
        : Promise.resolve({ data: PROFILES })
    )
    const onClose = vi.fn()
    render(<AssignChildrenDialog storybookId="s1" onClose={onClose} />)
    await screen.findByRole('checkbox', { name: /Reader A$/ })
    const assign = screen.getByRole('button', { name: /Assign/i })
    expect(assign).toBeDisabled()
    // A disabled button dispatches no click, so save() never runs.
    await user.click(assign)
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('surfaces a save failure without closing', async () => {
    const user = userEvent.setup()
    mockPost.mockRejectedValue(new Error('boom'))
    const onClose = vi.fn()
    render(<AssignChildrenDialog storybookId="s1" onClose={onClose} />)
    await user.click(await screen.findByRole('checkbox', { name: /Reader A2/ }))
    await user.click(screen.getByRole('button', { name: /Assign/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not assign/i)
    expect(onClose).not.toHaveBeenCalled()
  })

  it('shows a load-failure alert when profiles fail', async () => {
    mockGet.mockRejectedValue(new Error('down'))
    render(<AssignChildrenDialog storybookId="s1" onClose={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })

  it('shows content review tags for the story', async () => {
    render(<AssignChildrenDialog storybookId="s1" onClose={vi.fn()} />)
    expect(await screen.findByText('2 flagged')).toBeInTheDocument()
    expect(screen.getByText('coherence')).toBeInTheDocument()
    expect(screen.getByText('slightly disjoint')).toBeInTheDocument()
  })

  it('still renders the assign list and a review-unavailable notice when the content summary fails', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/content-summary')) return Promise.reject(new Error('down'))
      if (url.includes('/assignments'))
        return Promise.resolve({ data: { storybook_id: 's1', profile_ids: ['p1'] } })
      return Promise.resolve({ data: PROFILES })
    })
    render(<AssignChildrenDialog storybookId="s1" onClose={vi.fn()} />)
    expect(
      await screen.findByRole('checkbox', { name: /Reader A$/ })
    ).toBeInTheDocument()
    expect(screen.getByText(/content review unavailable/i)).toBeInTheDocument()
  })

  it('renders the content-review-unavailable notice on a rejected contentSummary()', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/content-summary')) return Promise.reject(new Error('down'))
      if (url.includes('/assignments'))
        return Promise.resolve({ data: { storybook_id: 's1', profile_ids: ['p1'] } })
      return Promise.resolve({ data: PROFILES })
    })
    render(<AssignChildrenDialog storybookId="s1" onClose={vi.fn()} />)
    expect(
      await screen.findByText(/content review unavailable right now/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/you can still assign/i)).toBeInTheDocument()
    // Never both: a load failure must never look identical to "no flags".
    expect(screen.queryByText('Clean')).not.toBeInTheDocument()
  })
})
