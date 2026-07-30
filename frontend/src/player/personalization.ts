/**
 * Client-side sentinel resolution (ADR-023 P6, execution-plan Task C1).
 *
 * The server stores and serves ONE generic, sentinel-bearing blob, byte-identical
 * for every reader; a small per-profile values payload is fetched separately and
 * resolved here at render time. Real child data therefore never reaches a
 * provider, never lands in `storybook_version.blob`, and never rides a server
 * response except the values endpoint itself.
 *
 * Two keyings meet in this module and they are NOT the same:
 *
 * - a sentinel in prose carries the SLOT ID: `{~HERO:Explorer~}`
 *   (`src/cyo_adventure/storybook/sentinels.py::wrap`);
 * - the payload's `values` map is keyed by SLOT TYPE: `protagonist_first_name`.
 *
 * `payload.slot_bindings` is the join, computed server-side from the book's theme
 * contract, which no client can read. A sentinel whose slot id is unbound, or
 * whose field has no value, resolves to its own inner generic word, so the story
 * always reads correctly.
 *
 * Pure, total, synchronous: callable straight from render with no loading state,
 * and a missing payload degrades to the generic experience rather than an error.
 */

import type { PersonalizationValuesView } from '../client/types.gen'

/**
 * The values payload, aliased from the generated client rather than hand-typed.
 * Repo convention (see `api/readerApi.ts`'s `ConflictBody` and
 * `auth/AuthContext.tsx`'s `MeResponseBody`): the generated OpenAPI type is the
 * single source of truth for a wire shape, so C0's `sentinel_pattern` and
 * `slot_bindings` arrive here without a second declaration to keep in step.
 */
export type ValuesPayload = PersonalizationValuesView

/**
 * The canonical sentinel pattern, used ONLY when no payload is available (flag
 * off, offline with nothing cached, a failed fetch) and a marker still has to be
 * stripped to its generic word before a child sees it.
 *
 * #CRITICAL: data-integrity: this string duplicates
 * `cyo_adventure.storybook.sentinels.SENTINEL_RE.pattern`, and plan risk R9 is
 * exactly that two rendering implementations drift. The duplication is
 * unavoidable (a strip with no payload has no server-supplied pattern) so it is
 * PINNED instead: tests/unit/test_sentinel_pattern_frontend_pin.py reads this
 * file and asserts the literal below equals the backend pattern character for
 * character. Change one and that test fails.
 * #VERIFY: tests/unit/test_sentinel_pattern_frontend_pin.py
 */
export const SENTINEL_PATTERN_FALLBACK = "\\{~([A-Z][A-Z0-9_]*):([^{}<>'~]+)~\\}"

/**
 * A conservative residue pattern for a marker the canonical pattern did NOT
 * match: an unterminated or otherwise malformed token. The at-rest integrity
 * gate fails closed on these, so a published blob cannot contain one; this pass
 * exists because an unresolved marker on a kid-facing surface is the single
 * outcome ADR-023 section 10 forbids without exception, and a defensive strip is
 * cheaper than trusting every future write path.
 */
const MALFORMED_SENTINEL_RE = /\{~([^{}]*)\}/g

function compilePattern(source: string): RegExp | null {
  try {
    return new RegExp(source, 'g')
  } catch {
    // A payload whose pattern is not a valid JS regex (a server-side pattern
    // using syntax JS does not accept, a truncated response) must not throw
    // inside render. Fall back rather than fail.
    return null
  }
}

function stripMalformed(text: string): string {
  return text.replace(MALFORMED_SENTINEL_RE, (_match, inner: string) => {
    const colon = inner.lastIndexOf(':')
    const candidate = colon === -1 ? inner : inner.slice(colon + 1)
    return candidate.replace(/~+$/, '')
  })
}

/**
 * Resolve every sentinel in `text` against `payload`.
 *
 * @param text - Prose (or an ending title) that may carry sentinels.
 * @param payload - The values payload, or null when there is none.
 * @returns The text with every marker replaced by its personalized value where
 *   one exists, and by its own generic inner word everywhere else. Never returns
 *   text containing a marker.
 */
export function resolvePersonalization(text: string, payload: ValuesPayload | null): string {
  if (text === '') return ''

  const pattern =
    (payload === null ? null : compilePattern(payload.sentinel_pattern)) ??
    compilePattern(SENTINEL_PATTERN_FALLBACK)
  if (pattern === null) return stripMalformed(text)

  const resolved = text.replace(pattern, (_match, slotId: string, generic: string) => {
    if (payload === null) return generic
    const field = payload.slot_bindings[slotId]
    if (field === undefined) return generic
    const value = payload.values[field]
    if (value === undefined || value === '') return generic
    return value
  })

  return stripMalformed(resolved)
}
