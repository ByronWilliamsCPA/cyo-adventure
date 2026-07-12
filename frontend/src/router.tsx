import { Suspense } from 'react'
import type { ReactNode } from 'react'
import { createBrowserRouter } from 'react-router-dom'

import { ProtectedRoute } from './auth/ProtectedRoute'
import {
  AdminConsolePage,
  AdminRequestsPage,
  AdminShell,
  BooksPage,
  ConsolePage,
  GuardianAuthLayout,
  GuardianShell,
  IntakePage,
  KidShell,
  LandingPage,
  LibraryPage,
  LoginPage,
  ModerationDashboardPage,
  ModerationThresholdsPage,
  NotFoundPage,
  ParentalGate,
  ProfilePickerPage,
  ProfilesPage,
  ReaderRoute,
  RequestsPage,
  ReviewDetailPage,
  RouteError,
  RouteFallback,
} from './routeElements'
import {
  ADMIN_CONSOLE_PATH,
  GUARDIAN_CONSOLE_PATH,
  GUARDIAN_LOGIN_PATH,
  KID_PICKER_PATH,
} from './routes'

function suspended(element: ReactNode) {
  return <Suspense fallback={<RouteFallback />}>{element}</Suspense>
}

/**
 * Three entry points plus disjoint route trees (wireframe section 2 / section 6):
 * the landing page at (/), the kid surface (/kids, /library/*, /read/*),
 * and the adult surfaces (/guardian/* and its parallel /admin/* console)
 * share no navigation with the kid tree. Only the component library, axios
 * client, and this router module are shared. Each tree is a separate lazy
 * chunk (routeElements.tsx) so a kid device never downloads the guardian or
 * admin console's code, and vice versa. The admin console is gated on the
 * admin CAPABILITY (principal.isAdmin), so one adult holding both roles
 * moves between /guardian and /admin via the shell nav.
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
          // KID_PICKER_PATH minus its leading slash: React Router child paths
          // are relative segments, so this ties the picker's URL to the same
          // constant that LandingPage and ReaderRoute navigate to.
          { path: KID_PICKER_PATH.slice(1), element: suspended(<ProfilePickerPage />) },
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
        // The guardian console admits both adult capabilities: a dual-role
        // adult lives here day-to-day, and an admin-only adult who lands
        // here sees the family home's pointer into the admin console rather
        // than a redirect loop (a child still bounces to the kid picker).
        path: GUARDIAN_CONSOLE_PATH,
        element: (
          <ProtectedRoute redirectTo={GUARDIAN_LOGIN_PATH} allowedRoles={['guardian', 'admin']} />
        ),
        children: [
          {
            element: suspended(<GuardianShell />),
            children: [
              // Outside the parental gate: requesting a story and watching the
              // request list are viewing/asking surfaces, not the high-stakes
              // actions (P6-08 gates approval, assignments, and profile
              // management, not every guardian page).
              { path: 'intake', element: suspended(<IntakePage />) },
              { path: 'requests', element: suspended(<RequestsPage />) },
              {
                // Parental gate (P6-08): a pathless layout route wrapping the
                // sensitive console surfaces so a kid holding a signed-in
                // device cannot reach the family home (console), assignments
                // (books), or profile management without a guardian re-auth.
                // Sits INSIDE ProtectedRoute (a signed-in guardian/admin is a
                // precondition of re-auth) and renders its challenge in place
                // of the child route until warm. The admin-capability
                // surfaces that P6-08 also gated (approval queue, review,
                // moderation) moved to the parallel /admin tree below, which
                // carries its own ParentalGate.
                element: suspended(<ParentalGate />),
                children: [
                  { index: true, element: suspended(<ConsolePage />) },
                  { path: 'books', element: suspended(<BooksPage />) },
                  { path: 'profiles', element: suspended(<ProfilesPage />) },
                ],
              },
            ],
          },
        ],
      },
      {
        // Admin console: the parallel adult surface for admin-capability
        // functions (review queue, global request queue, moderation admin).
        // 'admin' is the CAPABILITY (principal.isAdmin), so a dual-role
        // guardian passes; a plain guardian is sent back to their console
        // (NOT the login page, which would loop for a signed-in user).
        path: ADMIN_CONSOLE_PATH,
        element: (
          <ProtectedRoute
            redirectTo={GUARDIAN_LOGIN_PATH}
            allowedRoles={['admin']}
            deniedRedirectTo={GUARDIAN_CONSOLE_PATH}
          />
        ),
        children: [
          {
            element: suspended(<AdminShell />),
            children: [
              {
                // Parental gate (P6-08): wraps every admin-console surface,
                // including the global request queue. Unlike the guardian
                // subtree's own request list (own-family only, left ungated
                // above as a viewing surface), AdminRequestsPage renders
                // CROSS-FAMILY child request text plus a family selector, so
                // it is high-stakes on privacy grounds even though it is not
                // an approval action: the admin capability (is_admin,
                // enforced by the ProtectedRoute above) proves the adult HAS
                // admin rights, but not that a grown-up is holding the
                // device right now, so a kid on a signed-in dual-role device
                // would otherwise read other families' child PII with no
                // challenge. The approval/review queue, review detail, and
                // moderation settings moved here from the guardian subtree in
                // the dual-role refactor, so the re-auth gate that P6-08
                // placed around approval/review/moderation follows them too.
                // Nested inside the admin-only ProtectedRoute, so a
                // signed-in admin is a precondition.
                element: suspended(<ParentalGate />),
                children: [
                  { index: true, element: suspended(<AdminConsolePage />) },
                  { path: 'requests', element: suspended(<AdminRequestsPage />) },
                  { path: 'review/:storybookId', element: suspended(<ReviewDetailPage />) },
                  {
                    path: 'moderation-thresholds',
                    element: suspended(<ModerationThresholdsPage />),
                  },
                  {
                    path: 'moderation-dashboard',
                    element: suspended(<ModerationDashboardPage />),
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
]

export const router = createBrowserRouter(routes)
