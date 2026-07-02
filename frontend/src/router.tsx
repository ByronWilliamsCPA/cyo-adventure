import { Suspense } from 'react'
import type { ReactNode } from 'react'
import { createBrowserRouter } from 'react-router-dom'

import { ProtectedRoute } from './auth/ProtectedRoute'
import {
  ConsolePage,
  GuardianShell,
  IntakePage,
  KidShell,
  LibraryPage,
  LoginPage,
  ReaderRoute,
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
 * Exported separately from `router` so tests can build a MemoryRouter
 * against the same route config instead of driving jsdom's real History API.
 */
export const routes = [
  {
    path: '/',
    element: suspended(<KidShell />),
    children: [
      { index: true, element: suspended(<LibraryPage />) },
      {
        path: 'read/:profileId/:storybookId/:version',
        element: suspended(<ReaderRoute />),
      },
    ],
  },
  {
    path: '/guardian/login',
    element: suspended(<LoginPage />),
  },
  {
    path: '/guardian',
    element: <ProtectedRoute redirectTo="/guardian/login" allowedRoles={['guardian', 'admin']} />,
    children: [
      {
        element: suspended(<GuardianShell />),
        children: [
          { index: true, element: suspended(<ConsolePage />) },
          { path: 'intake', element: suspended(<IntakePage />) },
        ],
      },
    ],
  },
]

export const router = createBrowserRouter(routes)
