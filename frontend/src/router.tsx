import { Suspense } from 'react'
import type { ReactNode } from 'react'
import { createBrowserRouter } from 'react-router-dom'

import { ProtectedRoute } from './auth/ProtectedRoute'
import {
  BooksPage,
  ConsolePage,
  GuardianAuthLayout,
  GuardianShell,
  IntakePage,
  KidShell,
  LandingPage,
  LibraryPage,
  LoginPage,
  NotFoundPage,
  ProfilePickerPage,
  ProfilesPage,
  ReaderRoute,
  RequestsPage,
  ReviewDetailPage,
  RouteError,
  RouteFallback,
} from './routeElements'
import { GUARDIAN_LOGIN_PATH } from './routes'

function suspended(element: ReactNode) {
  return <Suspense fallback={<RouteFallback />}>{element}</Suspense>
}

/**
 * Three entry points plus two disjoint route trees (wireframe section 2 / section 6):
 * the landing page at (/), the kid surface (/kids, /library/*, /read/*),
 * and the guardian surface (/guardian/*) share no navigation. Only the
 * component library, axios client, and this router module are shared. Each tree
 * is a separate lazy chunk (routeElements.tsx) so a kid device never downloads the
 * guardian console's code, and vice versa.
 *
 * The landing page is chunk-neutral and doesn't inherit KidShell chrome.
 * The Supabase-backed AuthProvider is scoped to the guardian subtree via the
 * lazy GuardianAuthLayout, so the kid surface never imports
 * @supabase/supabase-js and does not require the VITE_SUPABASE_* env vars.
 *
 * Both trees carry an errorElement so a lazy-chunk load failure or a missing
 * guardian env var degrades to an app-consistent fallback rather than a blank
 * screen.
 *
 * Exported separately from `router` so tests can build a MemoryRouter
 * against the same route config instead of driving jsdom's real History API.
 */
export const routes = [
  {
    // Root subtree: the index is the audience-neutral landing page (its own
    // lazy chunk, outside KidShell so it inherits no kid chrome). The
    // pathless KidShell wrapper keeps the kid surface's deep-link URLs
    // (/library/..., /read/...) unchanged; only the profile picker moved,
    // from the index to /kids, when the landing page took the root.
    path: '/',
    errorElement: <RouteError />,
    children: [
      { index: true, element: suspended(<LandingPage />) },
      {
        element: suspended(<KidShell />),
        children: [
          { path: 'kids', element: suspended(<ProfilePickerPage />) },
          { path: 'library/:profileId', element: suspended(<LibraryPage />) },
          {
            path: 'read/:profileId/:storybookId/:version',
            element: suspended(<ReaderRoute />),
          },
        ],
      },
    ],
  },
  {
    // Guardian subtree: the AuthProvider (and thus @supabase/supabase-js) is
    // loaded here as a lazy chunk, so the kid surface above never imports it.
    element: suspended(<GuardianAuthLayout />),
    errorElement: <RouteError />,
    children: [
      {
        path: GUARDIAN_LOGIN_PATH,
        element: suspended(<LoginPage />),
      },
      {
        path: '/guardian',
        element: (
          <ProtectedRoute redirectTo={GUARDIAN_LOGIN_PATH} allowedRoles={['guardian', 'admin']} />
        ),
        children: [
          {
            element: suspended(<GuardianShell />),
            children: [
              { index: true, element: suspended(<ConsolePage />) },
              { path: 'intake', element: suspended(<IntakePage />) },
              { path: 'books', element: suspended(<BooksPage />) },
              { path: 'requests', element: suspended(<RequestsPage />) },
              { path: 'profiles', element: suspended(<ProfilesPage />) },
              { path: 'review/:storybookId', element: suspended(<ReviewDetailPage />) },
            ],
          },
        ],
      },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]

export const router = createBrowserRouter(routes)
