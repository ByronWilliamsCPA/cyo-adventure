import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ToastProvider } from '../notifications/ToastProvider'
import { NotificationBell } from './NotificationBell'

const mockUseAuth = vi.fn()
vi.mock('../auth/useAuth', () => ({
  useAuth: (): unknown => mockUseAuth(),
}))

const mockGet = vi.fn()
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

function principal(subject = 'guardian-1') {
  return { subject, role: 'guardian', isAdmin: false, familyId: 'f', profileIds: [] }
}

const INFO_ITEM = {
  id: 'evt-info-1',
  occurred_at: '2026-07-15T12:00:00Z',
  kind: 'story_ready',
  severity: 'info' as const,
  title: 'A story is ready',
  body: 'It has been published to your family library.',
  storybook_id: 's1',
  request_id: null,
  profile_id: null,
}

const ALERT_ITEM = {
  id: 'evt-alert-1',
  occurred_at: '2026-07-15T13:00:00Z',
  kind: 'kid_flagged',
  severity: 'alert' as const,
  title: 'Reader A flagged a story',
  body: 'Reader A said this story scared them; it needs your review.',
  storybook_id: 's2',
  request_id: null,
  profile_id: 'p1',
}

function renderBell() {
  return render(
    <ToastProvider>
      <NotificationBell />
    </ToastProvider>
  )
}

beforeEach(() => {
  mockGet.mockReset()
  mockUseAuth.mockReturnValue({ principal: principal() })
  localStorage.clear()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('NotificationBell', () => {
  it('renders nothing when there is no principal', () => {
    mockUseAuth.mockReturnValue({ principal: null })
    mockGet.mockResolvedValue({ data: { notifications: [] } })
    renderBell()
    expect(screen.queryByRole('button', { name: /Notifications/ })).not.toBeInTheDocument()
  })

  it('shows an unread badge from the since-filtered poll', async () => {
    mockGet.mockResolvedValue({ data: { notifications: [INFO_ITEM] } })
    renderBell()
    expect(
      await screen.findByRole('button', { name: 'Notifications, 1 unread' })
    ).toBeInTheDocument()
  })

  it('hides the badge when there is nothing unread', async () => {
    mockGet.mockResolvedValue({ data: { notifications: [] } })
    renderBell()
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument()
  })

  it('hides the badge and logs, rather than throwing, on a failed poll', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    mockGet.mockRejectedValue(new Error('backend down'))
    renderBell()
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument()
    expect(errorSpy).toHaveBeenCalled()
    errorSpy.mockRestore()
  })

  it('opens the panel, lists recent items newest first, and marks seen', async () => {
    const user = userEvent.setup()
    mockGet.mockImplementation((_url: string, config: { params?: { since?: string } }) => {
      // The since-filtered poll and the panel's full-list fetch share one
      // mocked GET; both return the same two-item fixture here.
      void config
      return Promise.resolve({ data: { notifications: [ALERT_ITEM, INFO_ITEM] } })
    })
    renderBell()
    const toggle = await screen.findByRole('button', { name: /Notifications/ })
    await user.click(toggle)

    const panel = await screen.findByRole('dialog', { name: 'Notifications' })
    expect(panel).toBeInTheDocument()
    // Scoped to the panel: a toasted alert also renders "Reader A flagged a
    // story" text in the (separately mounted) toast viewport, so an
    // unscoped query would over-match.
    const titles = await within(panel).findAllByText(
      /^A story is ready$|^Reader A flagged a story$/
    )
    expect(titles[0]).toHaveTextContent('Reader A flagged a story') // newest first
    expect(titles[1]).toHaveTextContent('A story is ready')

    // Opening the panel marks-seen: the badge resets to hidden immediately.
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument()
    )
    expect(localStorage.getItem('cyo:notifications:seen:guardian-1')).toContain(
      ALERT_ITEM.occurred_at
    )
  })

  it('marks alert items as visually distinct with an Alert tag', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { notifications: [ALERT_ITEM] } })
    renderBell()
    await user.click(await screen.findByRole('button', { name: /Notifications/ }))
    expect(await screen.findByText('Alert')).toBeInTheDocument()
    const item = screen.getByText('Reader A flagged a story').closest('li')
    expect(item).toHaveClass('notification-bell__item--alert')
  })

  it('shows an empty message when the panel has no items', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { notifications: [] } })
    renderBell()
    await user.click(await screen.findByRole('button', { name: /Notifications/ }))
    expect(await screen.findByText('Nothing here yet.')).toBeInTheDocument()
  })

  it('closes the panel on Escape and returns focus to the toggle', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { notifications: [] } })
    renderBell()
    const toggle = await screen.findByRole('button', { name: /Notifications/ })
    await user.click(toggle)
    await screen.findByRole('dialog', { name: 'Notifications' })
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: 'Notifications' })).not.toBeInTheDocument()
    expect(toggle).toHaveFocus()
  })

  it('closes the panel on an outside click', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue({ data: { notifications: [] } })
    render(
      <ToastProvider>
        <div>
          <span data-testid="outside">outside</span>
          <NotificationBell />
        </div>
      </ToastProvider>
    )
    await user.click(await screen.findByRole('button', { name: /Notifications/ }))
    await screen.findByRole('dialog', { name: 'Notifications' })
    await user.click(screen.getByTestId('outside'))
    expect(screen.queryByRole('dialog', { name: 'Notifications' })).not.toBeInTheDocument()
  })

  it('toasts a new alert-severity item exactly once', async () => {
    mockGet.mockResolvedValue({ data: { notifications: [ALERT_ITEM] } })
    renderBell()
    const toast = await screen.findByText(/Reader A flagged a story\./)
    expect(toast).toBeInTheDocument()
    expect(screen.getAllByTestId('toast')).toHaveLength(1)
  })

  it('does not toast an info-severity item', async () => {
    mockGet.mockResolvedValue({ data: { notifications: [INFO_ITEM] } })
    renderBell()
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
  })

  it('does not re-toast an alert already recorded as toasted', async () => {
    localStorage.setItem(
      'cyo:notifications:seen:guardian-1',
      JSON.stringify({ lastSeenAt: null, toastedIds: [ALERT_ITEM.id] })
    )
    mockGet.mockResolvedValue({ data: { notifications: [ALERT_ITEM] } })
    renderBell()
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(screen.queryByTestId('toast')).not.toBeInTheDocument()
  })
})
