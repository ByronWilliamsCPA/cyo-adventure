/**
 * The localStorage key under which the guardian bearer token is persisted.
 *
 * This lives in its own dependency-free module ON PURPOSE. The kid surface
 * (`guardianToken.ts`) needs the same key to detect a signed-in guardian, but
 * it is mounted OUTSIDE the Supabase-backed AuthProvider so the kid chunk never
 * imports @supabase/supabase-js. Importing the key from AuthContext.tsx would
 * pull the Supabase client (and its VITE_SUPABASE_* env requirement) into that
 * chunk. A leaf module with zero imports lets every consumer (AuthContext,
 * useApi, guardianToken) share ONE literal without that coupling, so the key
 * can never drift between the guardian and kid halves of the app.
 */
export const TOKEN_STORAGE_KEY = 'auth_token'
