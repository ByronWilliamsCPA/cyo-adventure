import { lazy } from 'react'
import { useRouteError } from 'react-router-dom'

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

export const GuardianAuthLayout = lazy(() =>
  import('./auth/GuardianAuthLayout').then((m) => ({ default: m.GuardianAuthLayout }))
)
export const GuardianShell = lazy(() =>
  import('./guardian/GuardianShell').then((m) => ({ default: m.GuardianShell }))
)
export const LoginPage = lazy(() =>
  import('./guardian/LoginPage').then((m) => ({ default: m.LoginPage }))
)
export const ConsolePage = lazy(() =>
  import('./guardian/ConsolePage').then((m) => ({ default: m.ConsolePage }))
)
export const IntakePage = lazy(() =>
  import('./guardian/IntakePage').then((m) => ({ default: m.IntakePage }))
)
export const BooksPage = lazy(() =>
  import('./guardian/BooksPage').then((m) => ({ default: m.BooksPage }))
)
export const RequestsPage = lazy(() =>
  import('./guardian/RequestsPage').then((m) => ({ default: m.RequestsPage }))
)
export const KidShell = lazy(() => import('./kid/KidShell').then((m) => ({ default: m.KidShell })))
export const LibraryPage = lazy(() =>
  import('./library/LibraryPage').then((m) => ({ default: m.LibraryPage }))
)
export const ProfilePickerPage = lazy(() =>
  import('./kid/ProfilePickerPage').then((m) => ({ default: m.ProfilePickerPage }))
)
export const ProfilesPage = lazy(() =>
  import('./guardian/ProfilesPage').then((m) => ({ default: m.ProfilesPage }))
)
export const ReviewDetailPage = lazy(() =>
  import('./guardian/ReviewDetailPage').then((m) => ({ default: m.ReviewDetailPage }))
)
export const ReaderRoute = lazy(() =>
  import('./reader/ReaderRoute').then((m) => ({ default: m.ReaderRoute }))
)
