import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

// #CRITICAL: external-resources: the guardian surface cannot function without a
// Supabase project. This module is imported only inside the guardian lazy chunk
// (auth/GuardianAuthLayout, wired lazily under /guardian in router.tsx), so a
// missing key fails the guardian route (caught by that subtree's errorElement),
// never the unauthenticated kid surface (/ and /read/*), which never imports it.
// #VERIFY: GuardianAuthLayout is lazy-loaded only under /guardian in router.tsx;
// createClient throws on a falsy url/key, so we surface an actionable message.
if (!supabaseUrl || !supabaseAnonKey) {
  const msg =
    'Missing VITE_SUPABASE_URL or VITE_SUPABASE_ANON_KEY: the guardian sign-in ' +
    'surface cannot start. Set both from Supabase dashboard > Project Settings > API.'
  throw new Error(msg)
}

/**
 * The Supabase client for guardian sign-in (ADR-009). Never used on the kid
 * surface: a child never authenticates as a guardian, and this session is
 * guardian/admin-only per the auth seam in api/deps.py. The module is loaded
 * only inside the guardian lazy chunk so the kid bundle omits it entirely.
 */
export const supabase = createClient(supabaseUrl, supabaseAnonKey)
