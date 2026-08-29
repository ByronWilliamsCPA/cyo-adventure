/**
 * Allowlist of known third-party console noise for the usersim walk's
 * clean-console invariant (one of the two cheapest-win invariants this tier
 * exists to provide).
 *
 * Ship this EMPTY, or with only entries that have actually been observed in
 * a real run and can be named. Do not pre-populate with guesses: an
 * unjustified allowlist entry is exactly how the clean-console invariant
 * gets silently hollowed out later, by hiding a real defect behind a broad
 * pattern nobody can trace back to a specific, known source.
 */

export interface ConsoleAllowlistEntry {
  /** Matched against the console message's text. */
  pattern: RegExp
  /** Which known third-party source this is, and why it is safe to ignore rather than a real defect. */
  reason: string
}

// No entries yet: nothing has been walked with this tier, so nothing has
// been observed. Add an entry here only once a real run surfaces a
// specific, named piece of third-party noise, with the pattern and reason
// describing exactly that message and its source.
export const CONSOLE_ALLOWLIST: readonly ConsoleAllowlistEntry[] = []

/** True when a console message text matches a known, allowlisted source. */
export function isAllowlistedConsoleMessage(text: string): boolean {
  return CONSOLE_ALLOWLIST.some((entry) => entry.pattern.test(text))
}
