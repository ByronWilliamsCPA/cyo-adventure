import { lazy } from 'react'

export function RouteFallback() {
  return (
    <div role="status" aria-live="polite">
      Loading…
    </div>
  )
}

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
export const KidShell = lazy(() => import('./kid/KidShell').then((m) => ({ default: m.KidShell })))
export const LibraryPage = lazy(() =>
  import('./kid/LibraryPage').then((m) => ({ default: m.LibraryPage }))
)
export const ReaderRoute = lazy(() =>
  import('./reader/ReaderRoute').then((m) => ({ default: m.ReaderRoute }))
)
