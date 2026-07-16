import { useRouteError } from 'react-router-dom'

import { lazyWithReload } from './lazyWithReload'

export function RouteFallback() {
  return (
    <div role="status" aria-live="polite">
      Loading…
    </div>
  )
}

/**
 * Route-level error boundary. Catches a lazy-chunk load failure (e.g. a kid
 * tablet losing connectivity mid-navigation) or a guardian-subtree module throw
 * (missing VITE_SUPABASE_* env) and renders an app-consistent fallback instead
 * of React Router's default unstyled boundary or a blank screen.
 *
 * The common post-deploy stale-chunk failure is handled earlier: lazyWithReload
 * force-reloads once on a failed dynamic import, so this boundary only renders
 * when recovery has already been attempted (truly offline, asset actually gone)
 * or for a non-chunk module throw.
 */
export function RouteError() {
  // #EDGE: browser-compat: the underlying error may carry internal detail; show
  // a generic message to the user and log the specifics for diagnosis.
  const error = useRouteError()
  if (error) {
    console.error('Route error:', error)
  }
  return (
    <div role="alert">
      <h1>Something went wrong</h1>
      <p>Please reload the page. If the problem persists, try again later.</p>
    </div>
  )
}

/** Catch-all for unmatched URLs and stale deep links. */
export function NotFoundPage() {
  return (
    <div role="alert">
      <h1>Page not found</h1>
      <p>The page you were looking for does not exist.</p>
    </div>
  )
}

export const GuardianAuthLayout = lazyWithReload('GuardianAuthLayout', () =>
  import('./auth/GuardianAuthLayout').then((m) => ({ default: m.GuardianAuthLayout }))
)
export const GuardianShell = lazyWithReload('GuardianShell', () =>
  import('./guardian/GuardianShell').then((m) => ({ default: m.GuardianShell }))
)
// Lazy like the rest of the guardian chunk, NOT imported eagerly in router.tsx
// the way ProtectedRoute is: AdultGate imports auth/supabaseClient, and an
// eager import would pull @supabase/supabase-js (and its env requirement) into
// the kid surface's bundle.
export const AdultGate = lazyWithReload('AdultGate', () =>
  import('./auth/AdultGate').then((m) => ({ default: m.AdultGate }))
)
export const LoginPage = lazyWithReload('LoginPage', () =>
  import('./guardian/LoginPage').then((m) => ({ default: m.LoginPage }))
)
export const ConsolePage = lazyWithReload('ConsolePage', () =>
  import('./guardian/ConsolePage').then((m) => ({ default: m.ConsolePage }))
)
export const IntakePage = lazyWithReload('IntakePage', () =>
  import('./guardian/IntakePage').then((m) => ({ default: m.IntakePage }))
)
export const BooksPage = lazyWithReload('BooksPage', () =>
  import('./guardian/BooksPage').then((m) => ({ default: m.BooksPage }))
)
export const RequestsPage = lazyWithReload('RequestsPage', () =>
  import('./guardian/RequestsPage').then((m) => ({ default: m.RequestsPage }))
)
export const KidShell = lazyWithReload('KidShell', () =>
  import('./kid/KidShell').then((m) => ({ default: m.KidShell }))
)
export const LandingPage = lazyWithReload('LandingPage', () =>
  import('./landing/LandingPage').then((m) => ({ default: m.LandingPage }))
)
export const LibraryPage = lazyWithReload('LibraryPage', () =>
  import('./library/LibraryPage').then((m) => ({ default: m.LibraryPage }))
)
export const ProfilePickerPage = lazyWithReload('ProfilePickerPage', () =>
  import('./kid/ProfilePickerPage').then((m) => ({ default: m.ProfilePickerPage }))
)
export const ProfilesPage = lazyWithReload('ProfilesPage', () =>
  import('./guardian/ProfilesPage').then((m) => ({ default: m.ProfilesPage }))
)
export const AdminShell = lazyWithReload('AdminShell', () =>
  import('./admin/AdminShell').then((m) => ({ default: m.AdminShell }))
)
export const AdminConsolePage = lazyWithReload('AdminConsolePage', () =>
  import('./admin/AdminConsolePage').then((m) => ({ default: m.AdminConsolePage }))
)
export const AdminRequestsPage = lazyWithReload('AdminRequestsPage', () =>
  import('./admin/AdminRequestsPage').then((m) => ({ default: m.AdminRequestsPage }))
)
export const ReviewDetailPage = lazyWithReload('ReviewDetailPage', () =>
  import('./admin/ReviewDetailPage').then((m) => ({ default: m.ReviewDetailPage }))
)
export const ModerationThresholdsPage = lazyWithReload('ModerationThresholdsPage', () =>
  import('./admin/ModerationThresholdsPage').then((m) => ({
    default: m.ModerationThresholdsPage,
  }))
)
export const ModerationDashboardPage = lazyWithReload('ModerationDashboardPage', () =>
  import('./admin/ModerationDashboardPage').then((m) => ({
    default: m.ModerationDashboardPage,
  }))
)
export const UserManagementPage = lazyWithReload('UserManagementPage', () =>
  import('./admin/UserManagementPage').then((m) => ({
    default: m.UserManagementPage,
  }))
)
export const ReaderRoute = lazyWithReload('ReaderRoute', () =>
  import('./reader/ReaderRoute').then((m) => ({ default: m.ReaderRoute }))
)
