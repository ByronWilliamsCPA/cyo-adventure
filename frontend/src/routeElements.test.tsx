import { render, screen } from '@testing-library/react'
import { Suspense } from 'react'
import { MemoryRouter, createMemoryRouter } from 'react-router'
import { RouterProvider } from 'react-router/dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MockInstance } from 'vitest'

import {
  AdminLibraryPage,
  AuditPage,
  AuthoringQueuePage,
  DevicesPage,
  GuardianReviewDetailPage,
  NotFoundPage,
  OutstandingDecisionsPage,
  PrivacyPage,
  PrivacyPolicyPage,
  ProviderAllowlistPage,
  RouteError,
  RouteFallback,
  SupportPage,
  UserManagementPage,
} from './routeElements'
import * as routeElements from './routeElements'
import { routes } from './router'

// The lazy route chunks below are loaded through their real dynamic-import
// factories; AdminLibraryPage is the only one that reaches the network on mount,
// so stub its data hook to an empty library.
vi.mock('./hooks/useApi', () => ({
  useApi: () => ({ get: vi.fn().mockResolvedValue({ data: { items: [] } }) }),
}))
vi.mock('./admin/AuditPage', () => ({
  AuditPage: () => <div>AuditPage loaded</div>,
}))
vi.mock('./admin/AuthoringQueuePage', () => ({
  AuthoringQueuePage: () => <div>AuthoringQueuePage loaded</div>,
}))
vi.mock('./admin/OutstandingDecisionsPage', () => ({
  OutstandingDecisionsPage: () => <div>OutstandingDecisionsPage loaded</div>,
}))
vi.mock('./admin/ProviderAllowlistPage', () => ({
  ProviderAllowlistPage: () => <div>ProviderAllowlistPage loaded</div>,
}))
vi.mock('./admin/UserManagementPage', () => ({
  UserManagementPage: () => <div>UserManagementPage loaded</div>,
}))
vi.mock('./guardian/DevicesPage', () => ({
  DevicesPage: () => <div>DevicesPage loaded</div>,
}))
vi.mock('./guardian/GuardianReviewDetailPage', () => ({
  GuardianReviewDetailPage: () => <div>GuardianReviewDetailPage loaded</div>,
}))
vi.mock('./guardian/PrivacyPage', () => ({
  PrivacyPage: () => <div>PrivacyPage loaded</div>,
}))
vi.mock('./legal/PrivacyPolicyPage', () => ({
  PrivacyPolicyPage: () => <div>PrivacyPolicyPage loaded</div>,
}))
vi.mock('./legal/SupportPage', () => ({
  SupportPage: () => <div>SupportPage loaded</div>,
}))

describe('NotFoundPage', () => {
  it('renders friendly 404 copy with a way home for both audiences', () => {
    // NotFoundPage renders outside every shell, so it must carry its own
    // framing and exits: the landing page and the kid profile picker.
    render(
      <MemoryRouter>
        <NotFoundPage />
      </MemoryRouter>
    )
    expect(
      screen.getByRole('heading', { level: 1, name: /we can't find that page/i })
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to the start' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: "Who's reading?" })).toHaveAttribute('href', '/kids')
  })
})

describe('RouteFallback', () => {
  it('announces itself as a status region with kid-neutral copy', () => {
    // The Suspense fallback renders on every surface (kid tablets included),
    // so the copy stays friendly and the region is announced politely.
    render(<RouteFallback />)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Just a sec...')
    expect(status).toHaveAttribute('aria-live', 'polite')
  })
})

describe('RouteError', () => {
  let consoleErrorSpy: MockInstance

  beforeEach(() => {
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders an app-consistent fallback and logs the underlying error', async () => {
    // Drive RouteError the way it is actually reached in production: as a
    // route's errorElement, so useRouteError() resolves a real thrown error
    // from that route's loader.
    const router = createMemoryRouter(
      [
        {
          path: '/boom',
          loader: () => {
            throw new Error('lazy chunk failed to load')
          },
          errorElement: <RouteError />,
          element: <div>never rendered</div>,
        },
      ],
      { initialEntries: ['/boom'] }
    )
    render(<RouterProvider router={router} />)

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Something went wrong')
    expect(alert).toHaveTextContent('Please reload the page')
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      'Route error:',
      expect.objectContaining({ message: 'lazy chunk failed to load' })
    )
  })

  it('renders the fallback without logging when there is no route error to report', () => {
    // Rendered as a plain element (no errorElement context) useRouteError()
    // resolves undefined; the component must still render its fallback and
    // must not log a spurious "Route error: undefined" line.
    const router = createMemoryRouter([{ path: '/', element: <RouteError /> }], {
      initialEntries: ['/'],
    })
    render(<RouterProvider router={router} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong')
    expect(consoleErrorSpy).not.toHaveBeenCalledWith('Route error:', expect.anything())
  })
})

describe('lazy route chunks', () => {
  it('loads the AdminLibraryPage chunk through its dynamic-import factory', async () => {
    // Rendering the lazy export exercises the real chunk factory
    // (`() => import('./admin/AdminLibraryPage').then(...)`), the same wiring the
    // router mounts in production, and confirms the resolved module renders.
    render(
      <MemoryRouter>
        <Suspense fallback={<div>loading</div>}>
          <AdminLibraryPage />
        </Suspense>
      </MemoryRouter>
    )

    expect(await screen.findByText(/No stories here/i)).toBeInTheDocument()
  })
})

describe('router catch-all (router.tsx)', () => {
  it('renders the styled 404 for an unmatched URL', async () => {
    const router = createMemoryRouter(routes, {
      initialEntries: ['/definitely/not/a/page'],
    })
    render(<RouterProvider router={router} />)

    expect(
      await screen.findByRole('heading', { level: 1, name: /we can't find that page/i })
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: "Who's reading?" })).toHaveAttribute('href', '/kids')
  })

  it('declares an errorElement on the catch-all route', () => {
    // A throw on the unmatched-URL path must degrade to the styled RouteError
    // boundary, same as the two main route trees.
    const catchAll = routes.find((route) => 'path' in route && route.path === '*')
    expect(catchAll).toBeDefined()
    expect(catchAll && 'errorElement' in catchAll && catchAll.errorElement).toBeTruthy()
  })
})

describe('lazy page loaders', () => {
  // The loader thunk and its named-export mapper are the only code this file
  // adds per page; mounting each lazy component through Suspense executes both
  // without needing the real page's data layer. Pages exercised only through
  // full-router navigation cover their thunks nondeterministically (Suspense
  // timing), which is exactly the per-file function-coverage flake this block
  // pins down.
  const cases = [
    ['AuditPage', AuditPage],
    ['AuthoringQueuePage', AuthoringQueuePage],
    ['ProviderAllowlistPage', ProviderAllowlistPage],
    ['UserManagementPage', UserManagementPage],
    // Guardian G11 trust surface. Reached only from a footer link, so it is
    // never pulled in by the router-navigation tests that incidentally cover
    // the busier guardian chunks; without this entry its loader thunk is the
    // one uncovered function that drops this file under the 70% per-file gate.
    ['PrivacyPage', PrivacyPage],
    // Guardian G15 device-management surface, same situation as PrivacyPage
    // above: it is reached only from the guardian nav, so the router-navigation
    // tests cover its loader thunk nondeterministically (Suspense timing). Its
    // two uncovered functions dropped this file to 68.11% function coverage
    // against the 70% per-file gate, which is how CI caught it on PR #473.
    ['DevicesPage', DevicesPage],
    // Guardian G6 edit-and-review route, the third instance of the same
    // pattern: it is reached only from a per-book link on BooksPage, so the
    // router-navigation tests never resolve its chunk deterministically. Its
    // two uncovered functions held this file at 69.01% against the 70%
    // per-file gate once #473's DevicesPage entry grew the denominator.
    ['GuardianReviewDetailPage', GuardianReviewDetailPage],
    // The two PUBLIC legal surfaces, and the fourth and fifth instance of the
    // same pattern. Neither is reached by any router-navigation test: nothing
    // in the app links to /privacy or /support except the landing footer, and
    // the page tests in legal/ render the components directly rather than
    // through these lazy wrappers. Without these entries their two loader
    // thunks are uncovered functions in this file, which is the shape that
    // failed the 70% per-file gate three times already (PrivacyPage,
    // DevicesPage on PR #473, GuardianReviewDetailPage).
    ['PrivacyPolicyPage', PrivacyPolicyPage],
    ['SupportPage', SupportPage],
    // The admin outstanding-decisions surface, and the sixth instance. It is
    // reached only from an admin nav link, so no router-navigation test
    // resolves its chunk deterministically; its two uncovered functions took
    // this file from 71.43% to 69.62% against the 70% per-file gate.
    ['OutstandingDecisionsPage', OutstandingDecisionsPage],
  ] as const

  it.each(cases)('resolves the %s loader to the named export', async (name, LazyPage) => {
    render(
      <MemoryRouter>
        <Suspense fallback={<RouteFallback />}>
          <LazyPage />
        </Suspense>
      </MemoryRouter>
    )
    expect(await screen.findByText(`${name} loaded`)).toBeInTheDocument()
  })

  // Every entry above was appended only AFTER CI failed the 70% per-file
  // function-coverage gate on this file: six times now. The gate reports
  // "Coverage for functions (69.62%) does not meet global threshold (70%)",
  // which names the file but not the export that moved the denominator, so
  // each recurrence cost a fresh diagnosis of the same defect.
  //
  // This guard converts that into a named, local failure. Adding a
  // `lazyWithReload` export to routeElements.tsx without classifying it fails
  // here, in plain `npm run test:run`, saying which export is unaccounted for.
  // Both directions are checked, so a deleted export cannot rot either list.
  //
  // Classification is deliberate rather than automatic: mounting all 38 lazy
  // wrappers would require mocking all 38 pages, and the ones reached by the
  // router-navigation tests above already have their thunks executed.
  const ROUTER_NAVIGATION_COVERED = [
    'AdminConsolePage',
    'AdminLibraryPage',
    'AdminRequestsPage',
    'AdminShell',
    'AdultGate',
    'BooksPage',
    'ConnectionsPage',
    'ConsolePage',
    'GuardianAuthLayout',
    'GuardianAwaitingApprovalPage',
    'GuardianBackendUnavailablePage',
    'GuardianConsentPage',
    'GuardianShell',
    'GuardianVerificationPage',
    'IntakePage',
    'KidShell',
    'LandingPage',
    'LibraryPage',
    'LoginPage',
    'ModerationDashboardPage',
    'ModerationThresholdsPage',
    'PreviewAsChildPage',
    'ProfilePickerPage',
    'ProfilesPage',
    'ReaderRoute',
    'ReadingPage',
    'RequestsPage',
    'ReviewDetailPage',
  ] as const

  const REACT_LAZY = Symbol.for('react.lazy')

  function lazyExportNames(): string[] {
    return Object.entries(routeElements)
      .filter(
        ([, value]) =>
          typeof value === 'object' &&
          value !== null &&
          ($$typeofOf(value) as symbol | undefined) === REACT_LAZY
      )
      .map(([name]) => name)
      .sort()
  }

  function $$typeofOf(value: object): unknown {
    return (value as { $$typeof?: unknown }).$$typeof
  }

  it('accounts for every lazy route export in exactly one coverage bucket', () => {
    const accounted = new Set<string>([
      ...cases.map(([name]) => name),
      ...ROUTER_NAVIGATION_COVERED,
    ])
    const lazyExports = lazyExportNames()

    // A new lazy export nobody classified: add it to `cases` (and mock it) if
    // no router-navigation test mounts it, otherwise to ROUTER_NAVIGATION_COVERED.
    expect(lazyExports.filter((name) => !accounted.has(name))).toEqual([])

    // A name that is classified but no longer exported: drop the stale entry.
    const exported = new Set(lazyExports)
    expect([...accounted].filter((name) => !exported.has(name)).sort()).toEqual([])
  })
})
