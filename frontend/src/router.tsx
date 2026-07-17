import { Suspense } from 'react'
import type { ReactNode } from 'react'
import { createBrowserRouter } from 'react-router-dom'

import { DeviceAuthorizedRoute } from './auth/DeviceAuthorizedRoute'
import { ProtectedRoute } from './auth/ProtectedRoute'
import {
  AdminConsolePage,
  AdminRequestsPage,
  AdminShell,
  AdultGate,
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
  ProfilePickerPage,
  ProfilesPage,
  ReaderRoute,
  ReadingPage,
  RequestsPage,
  ReviewDetailPage,
  RouteError,
  RouteFallback,
  UserManagementPage,
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
          {
            // Device-authorization gate (ADR-014 Phase 4): the whole kid
            // surface requires a valid local device grant, not just the
            // picker. Nested inside KidShell so KidShell's chrome still
            // wraps an authorized render; an unauthorized visitor is
            // redirected to guardian login before any kid content mounts.
            element: <DeviceAuthorizedRoute />,
            children: [
              // KID_PICKER_PATH minus its leading slash: React Router child
              // paths are relative segments, so this ties the picker's URL to
              // the same constant that LandingPage and ReaderRoute navigate to.
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
        // Adult step-up gate (ADR-014 Phase 5): ONE pathless layout at the
        // root of the whole adult subtree, wrapping BOTH the guardian and
        // admin ProtectedRoute branches below. This is the collapse of the
        // two former per-page ParentalGate placements (P6-08): because this
        // sits ABOVE both role-gated branches instead of on individual
        // sibling pages, React Router never unmounts/remounts it while an
        // adult navigates guardian<->guardian, guardian<->admin, or
        // admin<->guardian, so that navigation is free once warm. It sits
        // OUTSIDE the login route (a signed-out visitor must reach login
        // without a step-up) but does its own session check ahead of each
        // ProtectedRoute below, redirecting to login itself when there is no
        // session at all; ProtectedRoute still does the role/capability
        // gating beneath it.
        element: suspended(<AdultGate />),
        children: [
          {
            // The guardian console admits both adult capabilities: a
            // dual-role adult lives here day-to-day, and an admin-only adult
            // who lands here sees the family home's pointer into the admin
            // console rather than a redirect loop (a child still bounces to
            // the kid picker).
            path: GUARDIAN_CONSOLE_PATH,
            element: (
              <ProtectedRoute
                redirectTo={GUARDIAN_LOGIN_PATH}
                allowedRoles={['guardian', 'admin']}
              />
            ),
            children: [
              {
                element: suspended(<GuardianShell />),
                children: [
                  // Intake and the request list moved inside the single
                  // adult gate along with everything else (ADR-014 Phase 5):
                  // once warm, an adult reaches any guardian page, including
                  // these, with no further challenge. They are no longer
                  // singled out as "viewing/asking, not gated" the way P6-08
                  // originally split them; the gate is now a kid-to-adult
                  // boundary, not a per-page distinction.
                  { index: true, element: suspended(<ConsolePage />) },
                  { path: 'intake', element: suspended(<IntakePage />) },
                  { path: 'requests', element: suspended(<RequestsPage />) },
                  { path: 'reading', element: suspended(<ReadingPage />) },
                  { path: 'books', element: suspended(<BooksPage />) },
                  { path: 'profiles', element: suspended(<ProfilesPage />) },
                ],
              },
            ],
          },
          {
            // Admin console: the parallel adult surface for admin-capability
            // functions (review queue, global request queue, moderation
            // admin). 'admin' is the CAPABILITY (principal.isAdmin), so a
            // dual-role guardian passes; a plain guardian is sent back to
            // their console (NOT the login page, which would loop for a
            // signed-in user). The admin-only ProtectedRoute still runs
            // beneath the shared AdultGate above, so an admin capability
            // check happens after the step-up rather than gating it.
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
                  {
                    path: 'users',
                    element: suspended(<UserManagementPage />),
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  },
  {
    // Catch-all 404. Like the two trees above, it carries an errorElement so
    // an unexpected throw on the unmatched-URL path degrades to the styled
    // RouteError instead of React Router's default unstyled boundary.
    path: '*',
    element: <NotFoundPage />,
    errorElement: <RouteError />,
  },
]

export const router = createBrowserRouter(routes)
