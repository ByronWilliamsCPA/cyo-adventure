/**
 * Vite exposes every env var as a string (or undefined), so a boolean feature
 * flag is really a stringly-typed value. Treat ONLY the literal "true" as on;
 * everything else, including "false", "1", "TRUE", and unset, is off. Using
 * this instead of a bare `Boolean(import.meta.env.X)` avoids the trap where the
 * string "false" is truthy. Centralized so the on/off convention lives in one
 * place as more flags are added.
 */
export function flagEnabled(value: string | undefined): boolean {
  return value === 'true'
}

/**
 * Whether story personalization (ADR-023) renders at all on this build.
 *
 * Off means: no values fetch, no settings UI, no dedication overlay, and the
 * reader shows generic prose. The backend routes may exist while this is off,
 * because the server-side artifact is generic either way, so a half-deployed
 * state is safe by construction (design plan 7.5).
 *
 * Build-time, read per call rather than captured at module load: a captured
 * constant cannot be stubbed per test, and every consumer calls this at render
 * or on an event, never in a hot loop.
 *
 * Gate G3: this flag must not be enabled anywhere a real family can reach until
 * Task D1 (toggle-aware Route A copy) has merged.
 */
export function isPersonalizationEnabled(): boolean {
  return flagEnabled(import.meta.env.VITE_FEATURE_PERSONALIZATION)
}
