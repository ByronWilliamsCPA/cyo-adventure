import { createClient } from '@supabase/supabase-js'

/**
 * The Supabase client for guardian sign-in (ADR-009). Never used on the kid
 * surface: a child never authenticates as a guardian, and this session is
 * guardian/admin-only per the auth seam in api/deps.py.
 */
export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY
)
