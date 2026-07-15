import { RouterProvider } from 'react-router-dom'

import { ToastProvider } from './notifications/ToastProvider'
import { router } from './router'

// AuthProvider is intentionally NOT here: it is scoped to the guardian subtree
// via the lazy GuardianAuthLayout (router.tsx) so the unauthenticated kid
// surface never loads @supabase/supabase-js or requires VITE_SUPABASE_* env.
//
// ToastProvider IS here: it wraps the router so every surface (kid, guardian,
// admin) can call useToast(), and its always-mounted live-region viewport
// renders alongside the routed tree (see notifications/ToastProvider.tsx).
function App() {
  return (
    <ToastProvider>
      <RouterProvider router={router} />
    </ToastProvider>
  )
}

export default App
