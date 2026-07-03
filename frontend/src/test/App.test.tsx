import 'fake-indexeddb/auto'

import { render, screen } from '@testing-library/react'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { _resetDbHandle } from '../offline/db'
import { routes } from '../router'

// Mock the API adapters so the reader route mounts deterministically without a backend.
vi.mock('../api/readerApi', () => ({
  makeSyncApi: () => ({
    putReadingState: (
      _profileId: string,
      _storybookId: string,
      body: { state_revision?: number }
    ) =>
      Promise.resolve({
        status: 200,
        row: { ...body, state_revision: (body.state_revision ?? 0) + 1 },
      }),
  }),
  makeFetchStory: () => () =>
    Promise.resolve({
      schema_version: '1.0',
      id: 's_demo',
      version: 1,
      title: 'Demo',
      metadata: {},
      variables: [],
      start_node: 'n0',
      nodes: [
        {
          id: 'n0',
          body: 'Hello reader',
          is_ending: false,
          choices: [{ id: 'c', label: 'Go', target: 'n1' }],
        },
        {
          id: 'n1',
          body: 'The end',
          is_ending: true,
          ending: { id: 'e', type: 'good', title: 'End' },
          choices: [],
        },
      ],
    }),
}))

const mockGet = vi.fn()
// A stable object, not a fresh literal per call: see the matching comment in
// auth/AuthContext.test.tsx for why this matters.
const fakeApi = { get: mockGet }
vi.mock('../hooks/useApi', () => ({
  useApi: () => fakeApi,
}))

const mockGetSession = vi.fn()
const mockOnAuthStateChange = vi.fn()
vi.mock('../auth/supabaseClient', () => ({
  supabase: {
    auth: {
      getSession: (...args: unknown[]) => mockGetSession(...args),
      onAuthStateChange: (...args: unknown[]) => mockOnAuthStateChange(...args),
      signInWithOAuth: vi.fn(),
      signOut: vi.fn(),
    },
  },
}))

function renderAt(initialPath: string) {
  // No <AuthProvider> wrapper here: it is scoped to the guardian subtree via
  // the lazy GuardianAuthLayout in `routes`, mirroring production (App.tsx
  // renders only <RouterProvider>). The kid-surface tests below therefore
  // exercise routes that never mount AuthProvider, which is the point of
  // scoping it; the guardian tests get it through the route tree.
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] })
  return render(<RouterProvider router={router} />)
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
  mockGet.mockReset()
  mockGetSession.mockReset().mockResolvedValue({ data: { session: null } })
  mockOnAuthStateChange
    .mockReset()
    .mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
})

describe('router: kid surface', () => {
  it('renders the profile picker at /', async () => {
    mockGet.mockResolvedValue({ data: { profiles: [] } })
    renderAt('/')
    expect(await screen.findByText(/No profiles yet/i)).toBeInTheDocument()
  })

  it('renders the library page at /library/:profileId', async () => {
    mockGet.mockResolvedValue({ data: { stories: [] } })
    renderAt('/library/p1')
    expect(await screen.findByText(/No books yet/i)).toBeInTheDocument()
  })

  it('renders the reader for a valid story route', async () => {
    renderAt('/read/p1/s_demo/1')
    expect(await screen.findByTestId('reader')).toBeInTheDocument()
    expect(screen.getByText('Hello reader')).toBeInTheDocument()
  })

  it('shows an error for a non-numeric version segment', async () => {
    renderAt('/read/p1/s_demo/not-a-number')
    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid/i)
  })
})

describe('router: guardian surface', () => {
  // The unauthenticated/wrong-role redirect itself (ProtectedRoute rendering
  // <Navigate>) is covered directly in auth/ProtectedRoute.test.tsx via a
  // plain <MemoryRouter>/<Routes>. It's deliberately not re-exercised here
  // through createMemoryRouter: a client-side <Navigate> triggers
  // react-router's data-router navigate(), which constructs a fetch Request
  // internally and crashes on an AbortSignal instanceof mismatch under this
  // vitest/jsdom/undici combination (an environment issue, not an app bug).
  // These tests only exercise routes that resolve on their initial match.

  it('renders the login page directly', async () => {
    renderAt('/guardian/login')
    expect(await screen.findByText(/Guardian sign-in/)).toBeInTheDocument()
  })

  it('renders the console for a signed-in guardian', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    // One shared get mock serves the auth /v1/me lookup and the console's
    // /v1/review-queue and /v1/generation-jobs fetches, so branch on the URL:
    // empty responses are enough to confirm the console mounts (its behavioral
    // matrix lives in ConsolePage.test.tsx).
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/review-queue') {
        return Promise.resolve({ data: { items: [] } })
      }
      if (url === '/v1/generation-jobs') {
        return Promise.resolve({ data: { jobs: [] } })
      }
      return Promise.resolve({
        data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
      })
    })
    renderAt('/guardian')
    expect(await screen.findByText(/Review queue/)).toBeInTheDocument()
  })

  it('renders the review detail page at /guardian/review/:storybookId', async () => {
    mockGetSession.mockResolvedValue({
      data: { session: { access_token: 'tok-1', user: { id: 'u1' } } },
    })
    // Shared get mock: serve the auth /v1/me lookup and the review surface fetch.
    // A minimal screened-clean surface is enough to confirm the detail route
    // mounts (its behavioral matrix lives in ReviewDetailPage.test.tsx).
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/storybooks/s1/review') {
        return Promise.resolve({
          data: {
            storybook_id: 's1',
            version: 1,
            status: 'in_review',
            screened: true,
            summary: null,
            blob: { title: 'The Cave', nodes: [] },
            flagged_passages: [],
            story_level_findings: [],
          },
        })
      }
      return Promise.resolve({
        data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
      })
    })
    renderAt('/guardian/review/s1')
    expect(await screen.findByRole('heading', { name: 'The Cave' })).toBeInTheDocument()
  })
})
