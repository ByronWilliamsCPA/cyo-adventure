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
