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
 * The canonical sentinel pattern, the ONLY pattern this module ever compiles.
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

// Wire-pattern trust (design decision): `payload.sentinel_pattern` is never read
// by any production path. It is not compiled, and it is not even compared
// against the constant; the constant is simply the only pattern this module
// uses. The field stays on the wire for schema compatibility.
//
// Compiling the wire value bought nothing, because
// tests/unit/test_sentinel_pattern_frontend_pin.py pins the backend's
// SENTINEL_RE.pattern character-identical to the constant, so a well-behaved
// server can only ever send the constant back. It also exposed three failure
// modes: an empty pattern matching everywhere and garbling output, a
// capture-group arity shift putting a number or the whole subject string into
// prose, and a catastrophic-backtracking (ReDoS) hang. Ignoring the field
// outright is strictly stronger than validating it.
//
// The constant is therefore compiled exactly once here at module level. Sharing
// one /g regex across calls is safe because String.replace with a global regex
// always starts from index 0 and resets lastIndex; no stateful exec/test is ever
// run on it.
const SENTINEL_RE = new RegExp(SENTINEL_PATTERN_FALLBACK, 'g')

/**
 * A conservative residue pattern for a marker the canonical pattern did NOT
 * match: a malformed or unterminated token. The at-rest integrity gate
 * (`validator/sentinel_integrity.py`, backed by
 * `storybook/sentinels.py::find_malformed_sentinels`) fails closed on these, so
 * a published blob should never contain one; this pass exists because an
 * unresolved marker on a kid-facing surface is the single outcome ADR-023
 * section 10 forbids without exception, and a defensive strip is cheaper than
 * trusting every future write path.
 *
 * What IS caught (mirroring the backend near-miss grammar's anchor rule: a
 * span counts only when it carries a sentinel-distinctive `{~` opener or `~}`
 * closer):
 *
 * - `{~...}` with a brace-free interior: a missing-closing-tilde near miss
 *   (`{~HERO:Explorer}`) and any leftover `{~...~}` the canonical pattern
 *   rejected (bad slot id, forbidden value chars).
 * - `{~...}` whose interior embeds ONE balanced brace pair: the
 *   brace-embedded forgery (`{~HERO:El{evated}~}`). The backend captures this
 *   as a single span via `sentinels.py::_closer_end`'s depth counter, which
 *   tolerates an embedded `{`...`}` rather than ending the span at the inner
 *   brace. Without the `\{[^{}]*\}` alternative below, such a span fell
 *   through to the unterminated branch, which stops at the inner `{` and so
 *   left the trailing `~}` closer intact on a kid-facing surface. Nesting
 *   deeper than one level is not matched here (a regex cannot count); the
 *   at-rest integrity gate is what rejects those before publication.
 * - `{~...` unterminated: matched through the token's whitespace-free run,
 *   ending at the next whitespace, brace, or end of text (`{~HERO:Explorer~`
 *   mid-sentence or at end of text). This is narrower than the backend, which
 *   reports the whole span to the next `{~` opener or end of text; stopping at
 *   whitespace keeps the surrounding prose instead of eating it.
 * - `{...~}` with a brace-free interior: a missing-opening-tilde near miss
 *   (`{HERO:Explorer~}`).
 *
 * What is NOT caught, deliberately: an ordinary prose brace span with no tilde
 * marker at either end (`{not a marker}`) survives untouched, because nothing
 * identifies it as a sentinel attempt.
 *
 * The strip is LOSSY for near-miss forms: the replacement keeps only the text
 * after the LAST colon of the interior (minus trailing tildes), so a
 * brace-and-tilde span that was never a sentinel collapses, e.g.
 * `{~note: he waited~}` becomes ` he waited`. That is the accepted cost of
 * guaranteeing no marker fragment reaches a child; the at-rest gate is what
 * keeps real prose from ever containing these shapes.
 */
// safe-regex flags
// this on STAR HEIGHT alone (the `*` inside the outer `*`), without checking
// whether the alternation is ambiguous. It is not: `[^{}]` and `\{[^{}]*\}`
// are disjoint on their first character, so the engine never has two live
// branches and cannot backtrack catastrophically. Measured 2026-08-24 on
// Node, replacing against an unterminated `{~` + 'a'.repeat(n) worst case:
// n=1000 0.05ms, n=10000 0.13ms, n=40000 0.27ms. Linear, so a 40x input costs
// ~5x time. #VERIFY: re-measure if the alternation gains a branch that can
// start with a non-brace character, which is what would introduce ambiguity.
// eslint-disable-next-line security/detect-unsafe-regex -- measured linear above
const MALFORMED_SENTINEL_RE = /\{~(?:[^{}]|\{[^{}]*\})*\}|\{~[^{}\s]*(?=[\s{]|$)|\{[^{}]*~\}/g

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function stripMalformed(text: string): string {
  let residues = 0
  const stripped = text.replace(MALFORMED_SENTINEL_RE, (match) => {
    residues += 1
    const inner = match.replace(/^\{~?/, '').replace(/~?\}$/, '')
    const colon = inner.lastIndexOf(':')
    const candidate = colon === -1 ? inner : inner.slice(colon + 1)
    return candidate.replace(/~+$/, '')
  })
  if (residues > 0) {
    // Child-facing silence preserved: a console.warn only, never UI. Firing at
    // all means a published blob carried a malformed sentinel past the at-rest
    // integrity gate, which the team must learn about. Value-free by design:
    // the residue count only, never the residue text, slot values, or any
    // payload contents.
    console.warn('[personalization] stripped malformed sentinel residue from rendered text', {
      residues,
    })
  }
  return stripped
}

/**
 * Resolve every sentinel in `text` against `payload`.
 *
 * @param text - Prose (or an ending title) that may carry sentinels.
 * @param payload - The values payload, or null when there is none. A payload
 *   whose `values` or `slot_bindings` is not a plain object is treated as null
 *   (generic resolution and the malformed strip still run).
 * @returns The text with every marker replaced by its personalized value where
 *   one exists, and by its own generic inner word everywhere else. Never returns
 *   text containing a canonical marker or a near-miss form the residue pattern
 *   covers (see `MALFORMED_SENTINEL_RE` for the exact grammar and its
 *   deliberate lossiness on near misses).
 */
export function resolvePersonalization(text: string, payload: ValuesPayload | null): string {
  if (text === '') return ''

  // #ASSUME: data-integrity: the payload arrives from an unvalidated axios cast
  // (personalizationApi.ts) and from IndexedDB with no runtime validation; a
  // malformed shape must degrade to the generic read rather than throw inside
  // render into the app error boundary.
  // #VERIFY: personalization.test.ts "treats a payload with malformed values as
  // absent" / "treats a payload with malformed slot_bindings as absent".
  const safePayload =
    payload !== null && isPlainRecord(payload.values) && isPlainRecord(payload.slot_bindings)
      ? payload
      : null

  const resolved = text.replace(SENTINEL_RE, (_match, slotId: string, generic: unknown) => {
    // Belt-and-braces: with the pinned two-group pattern `generic` is always a
    // string, but a capture-arity surprise must never put a non-string into a
    // child's prose; dropping the marker entirely is the safe failure.
    if (typeof generic !== 'string') return ''
    if (safePayload === null) return generic
    const field = safePayload.slot_bindings[slotId]
    if (field === undefined) return generic
    const value = safePayload.values[field]
    if (value === undefined || value === '') return generic
    return value
  })

  return stripMalformed(resolved)
}

/**
 * Strip every sentinel in `text` to its generic word, with the same malformed
 * residue pass as `resolvePersonalization`. For surfaces that must never carry
 * a personal value OR a marker (choice labels, any future incidental text):
 * equivalent to `resolvePersonalization(text, null)`, named so the call site
 * reads as the defensive strip it is rather than a resolution with no payload.
 */
export function stripSentinels(text: string): string {
  return resolvePersonalization(text, null)
}
