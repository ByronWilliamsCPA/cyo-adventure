import 'fake-indexeddb/auto'

import { render, screen } from '@testing-library/react'
import { RouterProvider, createMemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import { coolParentalGate, warmParentalGate } from '../auth/parentalGateState'
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
  // Cold-cache server resume, completion posting, and series continuation are
  // exercised by their own suites (readerApi.test.ts, ReaderPage.test.tsx,
  // ReaderRoute.test.tsx); here they just need to resolve so the wired route
  // mounts without a backend.
  makeFetchServerState: () => () => Promise.resolve(null),
  makeRecordCompletion: () => () => Promise.resolve(),
  makeFetchSeriesNext: () => () => Promise.resolve(null),
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
      getSession: (...args: unknown[]): unknown => mockGetSession(...args),
      onAuthStateChange: (...args: unknown[]): unknown => mockOnAuthStateChange(...args),
      signInWithOAuth: vi.fn(),
      signInWithPassword: vi.fn(),
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

/**
 * A signed-in guardian session whose user carries the password identity the
 * parental gate (P6-08) challenges against. The gated guardian tests below
 * pre-warm the gate for this user id; the gate's own behavioral matrix lives
 * in auth/ParentalGate.test.tsx.
 */
const guardianSession = {
  data: {
    session: {
      access_token: 'tok-1',
      user: {
        id: 'u1',
        email: 'guardian@example.com',
        app_metadata: { provider: 'email', providers: ['email'] },
      },
    },
  },
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
  // The parental gate keeps its warm state in module memory; reset it so no
  // test inherits another test's unlock.
  coolParentalGate()
  mockGet.mockReset()
  mockGetSession.mockReset().mockResolvedValue({ data: { session: null } })
  mockOnAuthStateChange
    .mockReset()
    .mockReturnValue({ data: { subscription: { unsubscribe: vi.fn() } } })
})

describe('router: kid surface', () => {
  it('renders the landing page at /', async () => {
    renderAt('/')
    expect(await screen.findByRole('link', { name: /grown-ups/i })).toHaveAttribute(
      'href',
      '/guardian'
    )
    expect(screen.getByRole('link', { name: /kids/i })).toHaveAttribute('href', '/kids')
  })

  it('renders the profile picker at /kids', async () => {
    mockGet.mockResolvedValue({ data: { profiles: [] } })
    renderAt('/kids')
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
    expect(await screen.findByText('That story link looks wrong')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to my books' })).toBeInTheDocument()
  })

  it('never mounts the parental gate on the kid surface', async () => {
    // The gate (P6-08) lives only inside the guardian route tree; kid routes
    // must render with zero interaction with it even when its module state is
    // cold. (Structurally guaranteed too: ParentalGate is a lazy chunk imported
    // only by the guardian subtree in router.tsx.)
    mockGet.mockResolvedValue({ data: { profiles: [] } })
    renderAt('/kids')
    expect(await screen.findByText(/No profiles yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Grown-ups only' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
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

  it('renders the family console for a signed-in guardian with a warm parental gate', async () => {
    mockGetSession.mockResolvedValue(guardianSession)
    // The family console route sits behind the parental gate (P6-08); warm it
    // so this test keeps asserting what it always did (the route mounts). The
    // cold-gate path has its own test below.
    warmParentalGate('u1')
    // One shared get mock serves the auth /v1/me lookup and the console's
    // /v1/profiles fetch, so branch on the URL: an empty profile list is
    // enough to confirm the console mounts (its behavioral matrix lives in
    // ConsolePage.test.tsx).
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/profiles') {
        return Promise.resolve({ data: { profiles: [] } })
      }
      return Promise.resolve({
        data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
      })
    })
    renderAt('/guardian')
    expect(await screen.findByText(/Family console/)).toBeInTheDocument()
  })

  it('renders the admin console (review queue) for a signed-in admin with a warm parental gate', async () => {
    mockGetSession.mockResolvedValue(guardianSession)
    // The admin tree is gated twice: the is_admin capability from /v1/me
    // (ProtectedRoute) admits the adult, and the parental gate (P6-08) proves a
    // grown-up is present. Warm the gate so this test asserts the console
    // mounts; the cold-gate path is covered by the guardian cold-gate test.
    warmParentalGate('u1')
    // Empty queue responses are enough to confirm the console mounts (its
    // behavioral matrix lives in AdminConsolePage.test.tsx).
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/review-queue') {
        return Promise.resolve({ data: { items: [] } })
      }
      if (url === '/v1/generation-jobs') {
        return Promise.resolve({ data: { jobs: [] } })
      }
      return Promise.resolve({
        data: {
          subject: 'sub-1',
          role: 'admin',
          is_admin: true,
          family_id: 'fam-1',
          profile_ids: [],
        },
      })
    })
    renderAt('/admin')
    expect(await screen.findByText(/Review queue/)).toBeInTheDocument()
  })

  it('renders the admin cross-family request queue for a signed-in admin with a warm parental gate', async () => {
    mockGetSession.mockResolvedValue(guardianSession)
    // AdminRequestsPage renders cross-family child request text, so it moved
    // inside the admin ParentalGate (I1); warm it so this test asserts the
    // route mounts. The cold-gate path is covered by the test below.
    warmParentalGate('u1')
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/v1/admin/story-requests')) {
        return Promise.resolve({ data: { requests: [] } })
      }
      if (url === '/v1/admin/families') {
        return Promise.resolve({ data: { families: [] } })
      }
      return Promise.resolve({
        data: {
          subject: 'sub-1',
          role: 'admin',
          is_admin: true,
          family_id: 'fam-1',
          profile_ids: [],
        },
      })
    })
    renderAt('/admin/requests')
    expect(await screen.findByLabelText(/what should the story be about/i)).toBeInTheDocument()
  })

  it('challenges a cold parental gate before the admin request queue renders (I1)', async () => {
    mockGetSession.mockResolvedValue(guardianSession)
    // No warmParentalGate call: the gate is cold, so /admin/requests must
    // render the re-auth challenge instead of the cross-family request queue,
    // even though the admin capability from /v1/me admits the principal.
    mockGet.mockImplementation((url: string) => {
      if (url.startsWith('/v1/admin/story-requests')) {
        return Promise.resolve({ data: { requests: [] } })
      }
      if (url === '/v1/admin/families') {
        return Promise.resolve({ data: { families: [] } })
      }
      return Promise.resolve({
        data: {
          subject: 'sub-1',
          role: 'admin',
          is_admin: true,
          family_id: 'fam-1',
          profile_ids: [],
        },
      })
    })
    renderAt('/admin/requests')
    expect(await screen.findByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(
      screen.queryByLabelText(/what should the story be about/i)
    ).not.toBeInTheDocument()
  })

  it('renders the review detail page at /admin/review/:storybookId with a warm parental gate', async () => {
    mockGetSession.mockResolvedValue(guardianSession)
    // The review detail moved to the admin tree, which is behind the parental
    // gate (P6-08); warm it so the route mounts.
    warmParentalGate('u1')
    // Shared get mock: serve the auth /v1/me lookup and the review surface fetch.
    // A minimal screened-clean surface is enough to confirm the detail route
    // mounts (its behavioral matrix lives in ReviewDetailPage.test.tsx). The
    // principal is a dual-role adult: the admin tree admits it via the
    // is_admin capability even though the base role is guardian.
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
        data: {
          subject: 'sub-1',
          role: 'guardian',
          is_admin: true,
          family_id: 'fam-1',
          profile_ids: [],
        },
      })
    })
    renderAt('/admin/review/s1')
    expect(await screen.findByRole('heading', { name: 'The Cave' })).toBeInTheDocument()
  })

  it('renders the profiles page at /guardian/profiles', async () => {
    mockGetSession.mockResolvedValue(guardianSession)
    warmParentalGate('u1')
    // Shared get mock: the auth /v1/me lookup plus the profiles list fetch.
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/profiles') {
        return Promise.resolve({ data: { profiles: [] } })
      }
      return Promise.resolve({
        data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
      })
    })
    renderAt('/guardian/profiles')
    expect(await screen.findByText(/No profiles yet/i)).toBeInTheDocument()
  })

  it('challenges a cold parental gate before the console renders (P6-08)', async () => {
    mockGetSession.mockResolvedValue(guardianSession)
    // No warmParentalGate call: the gate is cold, so the console route must
    // render the re-auth challenge instead of the family console.
    mockGet.mockResolvedValue({
      data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
    })
    renderAt('/guardian')
    expect(await screen.findByRole('heading', { name: 'Grown-ups only' })).toBeInTheDocument()
    expect(screen.queryByText(/Family console/)).not.toBeInTheDocument()
  })

  it('redirects a plain guardian away from /admin to the guardian console (I7)', async () => {
    mockGetSession.mockResolvedValue(guardianSession)
    // A plain guardian (is_admin false/absent) fails the admin-only capability
    // gate; ProtectedRoute's deniedRedirectTo sends them to
    // GUARDIAN_CONSOLE_PATH ('/guardian'), not the login page (which would
    // loop for an already signed-in user). Warm the gate so a successful
    // redirect resolves all the way to the family console, distinguishing it
    // from a redirect failure (which would leave the shared "Grown-ups only"
    // challenge markup ambiguous between the guardian and admin trees).
    warmParentalGate('u1')
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/profiles') {
        return Promise.resolve({ data: { profiles: [] } })
      }
      return Promise.resolve({
        data: {
          subject: 'sub-1',
          role: 'guardian',
          is_admin: false,
          family_id: 'fam-1',
          profile_ids: [],
        },
      })
    })
    renderAt('/admin')
    expect(await screen.findByText(/Family console/)).toBeInTheDocument()
    expect(screen.queryByText(/Guardian sign-in/)).not.toBeInTheDocument()
  })

  it('keeps intake outside the parental gate (requesting is not the gated action)', async () => {
    mockGetSession.mockResolvedValue(guardianSession)
    // No warm gate, yet the intake page must render: viewing/asking surfaces
    // stay outside the gate; approval, settings, and profiles are what it wraps.
    mockGet.mockImplementation((url: string) => {
      if (url === '/v1/profiles') {
        return Promise.resolve({ data: { profiles: [] } })
      }
      if (url === '/v1/generation-jobs') {
        return Promise.resolve({ data: { jobs: [] } })
      }
      return Promise.resolve({
        data: { subject: 'sub-1', role: 'guardian', family_id: 'fam-1', profile_ids: [] },
      })
    })
    renderAt('/guardian/intake')
    expect(await screen.findByRole('heading', { name: /request a story/i })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Grown-ups only' })).not.toBeInTheDocument()
  })
})

describe('App', () => {
  // App.tsx itself only wires <RouterProvider router={router} />, using the
  // real singleton `router` (createBrowserRouter) rather than the
  // createMemoryRouter used above; jsdom's default test URL is
  // http://localhost:3000/, which resolves to the same kid-surface landing
  // route exercised by the memory-router test above.
  it('mounts and renders the landing page at the default browser URL', async () => {
    render(<App />)
    expect(await screen.findByRole('link', { name: /grown-ups/i })).toHaveAttribute(
      'href',
      '/guardian'
    )
  })
})
