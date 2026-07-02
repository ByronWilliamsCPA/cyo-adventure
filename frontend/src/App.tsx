import { RouterProvider } from 'react-router-dom'

import { router } from './router'

// AuthProvider is intentionally NOT here: it is scoped to the guardian subtree
// via the lazy GuardianAuthLayout (router.tsx) so the unauthenticated kid
// surface never loads @supabase/supabase-js or requires VITE_SUPABASE_* env.
function App() {
  return <RouterProvider router={router} />
}

export default App
