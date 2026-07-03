import { Suspense } from 'react'
import type { ReactNode } from 'react'
import { createBrowserRouter } from 'react-router-dom'

import { ProtectedRoute } from './auth/ProtectedRoute'
import {
  ConsolePage,
  GuardianAuthLayout,
  GuardianShell,
  IntakePage,
  KidShell,
  LibraryPage,
  LoginPage,
  NotFoundPage,
  ProfilePickerPage,
  ProfilesPage,
  ReaderRoute,
  ReviewDetailPage,
  RouteError,
  RouteFallback,
} from './routeElements'

function suspended(element: ReactNode) {
  return <Suspense fallback={<RouteFallback />}>{element}</Suspense>
}

/**
 * Two disjoint route trees (wireframe section 2 / section 6): the kid
 * surface (/, /read/*) and the guardian surface (/guardian/*) share no
 * navigation. Only the component library, axios client, and this router
 * module are shared. Each tree is a separate lazy chunk (routeElements.tsx)
 * so a kid device never downloads the guardian console's code, and vice versa.
 *
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
    path: '/',
    element: suspended(<KidShell />),
    errorElement: <RouteError />,
    children: [
      { index: true, element: suspended(<ProfilePickerPage />) },
      { path: 'library/:profileId', element: suspended(<LibraryPage />) },
      {
        path: 'read/:profileId/:storybookId/:version',
        element: suspended(<ReaderRoute />),
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
        path: '/guardian/login',
        element: suspended(<LoginPage />),
      },
      {
        path: '/guardian',
        element: (
          <ProtectedRoute redirectTo="/guardian/login" allowedRoles={['guardian', 'admin']} />
        ),
        children: [
          {
            element: suspended(<GuardianShell />),
            children: [
              { index: true, element: suspended(<ConsolePage />) },
              { path: 'intake', element: suspended(<IntakePage />) },
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
