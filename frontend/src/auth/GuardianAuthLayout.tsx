import { Outlet } from 'react-router-dom'

import { AuthProvider } from './AuthContext'

/**
 * Layout route that scopes the Supabase-backed {@link AuthProvider} to the
 * guardian subtree only. Loaded as a lazy chunk (routeElements.tsx) so the kid
 * surface (/, /read/*) never imports @supabase/supabase-js and does not require
 * the VITE_SUPABASE_* env vars to render. A missing-env throw from
 * supabaseClient therefore lands in the guardian subtree's errorElement, not on
 * the kid surface.
 */
export function GuardianAuthLayout() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  )
}
