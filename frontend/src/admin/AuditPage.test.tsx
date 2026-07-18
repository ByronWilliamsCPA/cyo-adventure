import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AuditPage } from './AuditPage'

const mockGet = vi.fn()
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const AUDIT_PATH = '/v1/admin/audit'

const EMPTY_PAGE = { events: [], limit: 50, offset: 0, has_more: false }

const ONE_EVENT_PAGE = {
  events: [
    {
      id: 'evt-1',
      occurred_at: '2026-07-01T12:00:00Z',
      actor_id: 'user-1',
      actor_role: 'admin',
      entity_type: 'user',
      entity_id: 'user-2',
      event_type: 'user_managed',
      from_state: null,
      to_state: null,
      payload: { action: 'deactivate' },
    },
  ],
  limit: 50,
  offset: 0,
  has_more: false,
}

const SYSTEM_EVENT_PAGE = {
  events: [
    {
      id: 'evt-2',
      occurred_at: '2026-07-02T09:00:00Z',
      actor_id: null,
      actor_role: 'system',
      entity_type: 'generation_job',
      entity_id: 'job-1',
      event_type: 'generation_started',
      from_state: null,
      to_state: null,
      payload: {},
    },
  ],
  limit: 50,
  offset: 0,
  has_more: false,
}

interface ExpectedParams {
  kind?: string
  actor_id?: string
  storybook_id?: string
  profile_id?: string
  since?: string
  until?: string
  limit?: number
  offset?: number
}

// The adapter (auditApi.ts) always sends the full param shape, undefined
// keys included, so assertions match the exact object rather than using
// `expect.objectContaining` (which types as `any` and trips
// @typescript-eslint/no-unsafe-assignment on this project's ESLint config).
function expectedParams(overrides: ExpectedParams = {}) {
  return {
    kind: undefined,
    actor_id: undefined,
    storybook_id: undefined,
    profile_id: undefined,
    since: undefined,
    until: undefined,
    limit: 50,
    offset: 0,
    ...overrides,
  }
}

function mockGetByPath(overrides: Record<string, unknown> = {}) {
  mockGet.mockImplementation((path: string) => {
    if (path === AUDIT_PATH) {
      return Promise.resolve({ data: overrides.page ?? EMPTY_PAGE })
    }
    throw new Error(`mockGetByPath: unexpected GET path "${path}"`)
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockGetByPath()
})

describe('AuditPage', () => {
  it('shows a loading state before the first response resolves', () => {
    mockGet.mockReturnValue(new Promise(() => {}))
    render(<AuditPage />)
    expect(screen.getByRole('status')).toHaveTextContent(/loading/i)
  })

  it('loads the audit log on mount from the admin audit endpoint', async () => {
    render(<AuditPage />)
    await waitFor(() => expect(mockGet).toHaveBeenCalled())
    expect(mockGet).toHaveBeenCalledWith(AUDIT_PATH, { params: expectedParams() })
  })

  it('shows the empty state when there are no matching events', async () => {
    render(<AuditPage />)
    expect(await screen.findByText(/no matching audit events/i)).toBeInTheDocument()
  })

  it('shows a load-failure alert when the request fails', async () => {
    mockGet.mockRejectedValue(new Error('network down'))
    render(<AuditPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })

  it('shows a forbidden-specific message on a 403', async () => {
    const err = Object.assign(new Error('forbidden'), {
      isAxiosError: true,
      response: { status: 403 },
    })
    mockGet.mockRejectedValue(err)
    render(<AuditPage />)
    expect(await screen.findByRole('alert')).toHaveTextContent(/admin access is required/i)
  })

  it('renders a row for each returned event with actor, entity, kind, and payload', async () => {
    mockGetByPath({ page: ONE_EVENT_PAGE })
    render(<AuditPage />)
    // "user_managed" also appears as an <option> in the kind-filter <select>,
    // so every assertion here is scoped to the <table> region rather than
    // the page as a whole.
    const table = await screen.findByRole('table')
    expect(within(table).getByText('user_managed')).toBeInTheDocument()
    expect(within(table).getByText(/admin \(user-1\)/)).toBeInTheDocument()
    expect(within(table).getByText(/user: user-2/)).toBeInTheDocument()
    expect(within(table).getByText(/"action":"deactivate"/)).toBeInTheDocument()
  })

  it('renders "system" for an unattributed (system-actor) event', async () => {
    mockGetByPath({ page: SYSTEM_EVENT_PAGE })
    render(<AuditPage />)
    // "generation_started" also appears as an <option> in the kind-filter
    // <select>, so this is scoped to the <table> region too.
    const table = await screen.findByRole('table')
    expect(within(table).getByText('generation_started')).toBeInTheDocument()
    expect(within(table).getByText('system')).toBeInTheDocument()
  })

  it('applies the kind filter as a query param on submit', async () => {
    const user = userEvent.setup()
    render(<AuditPage />)
    await screen.findByText(/no matching audit events/i)
    mockGet.mockClear()
    mockGetByPath()

    await user.selectOptions(screen.getByLabelText(/filter by event kind/i), 'book_assigned')
    await user.click(screen.getByRole('button', { name: /apply filters/i }))

    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(AUDIT_PATH, {
        params: expectedParams({ kind: 'book_assigned' }),
      })
    )
  })

  it('applies the storybook id and profile id filters as query params on submit', async () => {
    const user = userEvent.setup()
    render(<AuditPage />)
    await screen.findByText(/no matching audit events/i)
    mockGet.mockClear()
    mockGetByPath()

    await user.type(screen.getByLabelText(/filter by storybook id/i), 'the-lighthouse-mystery')
    await user.type(screen.getByLabelText(/filter by profile id/i), 'profile-9')
    await user.click(screen.getByRole('button', { name: /apply filters/i }))

    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(AUDIT_PATH, {
        params: expectedParams({
          storybook_id: 'the-lighthouse-mystery',
          profile_id: 'profile-9',
        }),
      })
    )
  })

  it('applies the since/until date range as query params on submit', async () => {
    const user = userEvent.setup()
    render(<AuditPage />)
    await screen.findByText(/no matching audit events/i)
    mockGet.mockClear()
    mockGetByPath()

    const sinceInput = screen.getByLabelText(/filter events since this date/i)
    const untilInput = screen.getByLabelText(/filter events until this date/i)
    await user.type(sinceInput, '2026-01-01')
    await user.type(untilInput, '2026-12-31')
    await user.click(screen.getByRole('button', { name: /apply filters/i }))

    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(AUDIT_PATH, {
        params: expectedParams({ since: '2026-01-01', until: '2026-12-31' }),
      })
    )
  })

  it('clear filters resets the form and reloads with no filters', async () => {
    const user = userEvent.setup()
    render(<AuditPage />)
    await screen.findByText(/no matching audit events/i)

    await user.selectOptions(screen.getByLabelText(/filter by event kind/i), 'book_assigned')
    await user.click(screen.getByRole('button', { name: /apply filters/i }))
    await waitFor(() =>
      expect(mockGet).toHaveBeenLastCalledWith(AUDIT_PATH, {
        params: expectedParams({ kind: 'book_assigned' }),
      })
    )

    mockGet.mockClear()
    mockGetByPath()
    await user.click(screen.getByRole('button', { name: /clear filters/i }))

    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(AUDIT_PATH, { params: expectedParams() })
    )
    expect(screen.getByLabelText(/filter by event kind/i)).toHaveValue('')
  })

  it('paginates: next page requests the following offset, previous returns to 0', async () => {
    const user = userEvent.setup()
    const pageOne = {
      events: [{ ...ONE_EVENT_PAGE.events[0], id: 'evt-page-1' }],
      limit: 50,
      offset: 0,
      has_more: true,
    }
    const pageTwo = {
      events: [{ ...ONE_EVENT_PAGE.events[0], id: 'evt-page-2' }],
      limit: 50,
      offset: 50,
      has_more: false,
    }
    mockGet.mockImplementation((path: string, config: { params: { offset: number } }) => {
      if (path !== AUDIT_PATH) throw new Error(`unexpected GET path "${path}"`)
      return Promise.resolve({ data: config.params.offset === 0 ? pageOne : pageTwo })
    })

    render(<AuditPage />)
    await screen.findByRole('table')

    const nextButton = screen.getByRole('button', { name: /next page/i })
    const previousButton = screen.getByRole('button', { name: /previous page/i })
    expect(previousButton).toBeDisabled()
    expect(nextButton).not.toBeDisabled()

    await user.click(nextButton)
    await waitFor(() =>
      expect(mockGet).toHaveBeenLastCalledWith(AUDIT_PATH, {
        params: expectedParams({ offset: 50 }),
      })
    )
    await waitFor(() => expect(nextButton).toBeDisabled())
    expect(previousButton).not.toBeDisabled()

    await user.click(previousButton)
    await waitFor(() =>
      expect(mockGet).toHaveBeenLastCalledWith(AUDIT_PATH, {
        params: expectedParams({ offset: 0 }),
      })
    )
  })

  it('table rows are scoped within the table region (sanity check on structure)', async () => {
    mockGetByPath({ page: ONE_EVENT_PAGE })
    render(<AuditPage />)
    await screen.findByRole('table')
    const table = screen.getByRole('table')
    expect(within(table).getByText('user_managed')).toBeInTheDocument()
  })

  it('keeps the last page visible while a subsequent filter change is loading', async () => {
    const user = userEvent.setup()
    mockGetByPath({ page: ONE_EVENT_PAGE })
    render(<AuditPage />)
    const table = await screen.findByRole('table')
    expect(within(table).getByText('user_managed')).toBeInTheDocument()

    // A refetch that never resolves must not blank out the already-rendered
    // row: only a "Refreshing..." status appears alongside it.
    mockGet.mockReturnValue(new Promise(() => {}))
    await user.selectOptions(screen.getByLabelText(/filter by event kind/i), 'book_assigned')
    await user.click(screen.getByRole('button', { name: /apply filters/i }))

    await screen.findByText(/refreshing/i)
    expect(within(screen.getByRole('table')).getByText('user_managed')).toBeInTheDocument()
  })

  it('shows a refresh-error banner without discarding the last-good page on a refetch failure', async () => {
    const user = userEvent.setup()
    mockGetByPath({ page: ONE_EVENT_PAGE })
    render(<AuditPage />)
    const table = await screen.findByRole('table')
    expect(within(table).getByText('user_managed')).toBeInTheDocument()

    mockGet.mockRejectedValue(new Error('network down'))
    await user.selectOptions(screen.getByLabelText(/filter by event kind/i), 'book_assigned')
    await user.click(screen.getByRole('button', { name: /apply filters/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
    // The last-good row is still on screen; the failure is a dismissible
    // notice, not a full-page error replacing the table.
    expect(within(screen.getByRole('table')).getByText('user_managed')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /dismiss/i }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
