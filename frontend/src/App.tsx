import { RouterProvider } from 'react-router-dom'

import { AppErrorBoundary } from './AppErrorBoundary'
import { ToastProvider } from './notifications/ToastProvider'
import { router } from './router'
import { ThemeProvider } from './theme/ThemeProvider'

// AuthProvider is intentionally NOT here: it is scoped to the guardian subtree
// via the lazy GuardianAuthLayout (router.tsx) so the unauthenticated kid
// surface never loads @supabase/supabase-js or requires VITE_SUPABASE_* env.
//
// ThemeProvider IS here, outermost: every surface (landing, kid, guardian,
// admin) mounts a ThemeToggle in its own chrome, so the preference and the
// <html data-theme> it drives (tokens.css) must be available before any of
// them render. index.html's inline script already stamped the resolved
// theme before this component mounts (no flash); this just keeps React in
// sync with it (see theme/ThemeProvider.tsx).
//
// ToastProvider IS here too: it wraps the router so every surface (kid, guardian,
// admin) can call useToast(), and its always-mounted live-region viewport
// renders alongside the routed tree (see notifications/ToastProvider.tsx).
//
// AppErrorBoundary wraps the router (not the reverse) so an unexpected
// render-time throw anywhere in the routed tree still shows a styled
// recovery screen instead of unmounting React into a blank page; each
// route's own errorElement (router.tsx) handles loader/render errors closer
// to the source first, this is the outermost net.
function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AppErrorBoundary>
          <RouterProvider router={router} />
        </AppErrorBoundary>
      </ToastProvider>
    </ThemeProvider>
  )
}

export default App
