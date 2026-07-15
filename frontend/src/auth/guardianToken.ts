/**
 * Kid-safe signal for "a guardian is signed in on this device".
 *
 * The kid surface (`/kids`, `/library/*`, `/read/*`) is mounted OUTSIDE the
 * Supabase-backed AuthProvider on purpose: router.tsx scopes AuthProvider to
 * the guardian subtree so the kid chunk never imports @supabase/supabase-js
 * and never needs the VITE_SUPABASE_* env vars. That means kid-surface code
 * cannot call `useAuth()`. The presence of the guardian bearer that
 * `useApi`/AuthContext persist under the `auth_token` localStorage key is the
 * lightweight, Supabase-free proxy the kid surface can read instead.
 *
 * This is intentionally a coarse presence check, not a validity check: an
 * expired-but-present token still renders the grown-up affordance, and the
 * guardian route's own ProtectedRoute/AdultGate does the real session check on
 * navigation. The common handed-off-kid device has no `auth_token` at all, so
 * this returns false and kid-surface guardian affordances stay hidden.
 */

// Mirrors AuthContext.tsx's TOKEN_STORAGE_KEY and useApi.ts's literal usage.
// It cannot be imported from AuthContext without pulling the Supabase client
// (and its env requirement) into the kid chunk, so the key is duplicated here
// with this note as the single point of coordination.
const TOKEN_STORAGE_KEY = 'auth_token'

export function hasGuardianSession(): boolean {
  // #EDGE: browser-compat: localStorage access can throw in hardened privacy
  // modes; treat any failure as "no guardian signed in" rather than crashing
  // the kid picker.
  // #VERIFY: guardianToken.test.ts covers present, absent, and throwing-storage.
  try {
    return Boolean(window.localStorage.getItem(TOKEN_STORAGE_KEY))
  } catch {
    return false
  }
}
