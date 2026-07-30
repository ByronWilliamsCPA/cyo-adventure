/**
 * The dedication line (ADR-023 row 8, design plan section 9, execution-plan C5).
 *
 * The one personalized surface that does NOT resolve a sentinel, because there is
 * no sentinel in the blob for it: a dedication is not story prose. It composes
 * two values the payload already carries into a FIXED template and is a sibling
 * of the passage, never part of it: it never enters `node.body`, never reaches
 * `PassageText`, and never appears in any title field.
 *
 * Promoted from "first thing to drop" to mandatory by the Stage R measurement:
 * the corpus is second-person, so 11 of 30 stories never name the hero in prose
 * and cross-run HERO coverage ranges from roughly 27% to 42%. This is the surface
 * that carries the child's name in every personalized story regardless of what
 * the fill produced.
 *
 * #CRITICAL: security: the template is fixed and never guardian-authored. A
 * free-text dedication would be a new unmoderated-prose surface on a kid-facing
 * screen, which is the one thing this architecture exists to avoid. Both halves
 * come from validated, closed sources: the name is `child_profile.display_name`
 * (checked by storybook/personalization_values.py on profile write) and the
 * kinship is a closed enum. If the product ever wants free-text dedications that
 * is a separate feature with its own moderation path, and it must not borrow this
 * one's justification.
 * #VERIFY: storybook/personalization_values.py::CLOSED_VOCABULARIES has a
 * `dedication` key, so a value_text dedication is rejected at write time
 * (tests/unit/test_personalization_values.py::test_dedication_rejects_free_text).
 */

import type { ValuesPayload } from '../player/personalization'

export interface DedicationOverlayProps {
  /** The resolved values payload, or null for a generic read. */
  personalization: ValuesPayload | null
}

/**
 * Render the dedication line, or nothing at all.
 *
 * Renders nothing when there is no payload, when the payload is ring 2 (a
 * dedication is addressed to its own household), or when no name is available.
 * Renders the name alone when no kinship value is available, which is today's
 * real path: the dedication kinship vocabulary is still empty, and the child's
 * name must appear either way.
 */
export function DedicationOverlay({ personalization }: DedicationOverlayProps) {
  if (personalization === null) return null
  if (personalization.ring === 2) return null

  // #ASSUME: data-integrity: the payload arrives from an unvalidated axios cast
  // and from IndexedDB; `values` may not be the plain object the type claims.
  // Render nothing on a malformed shape rather than throw inside render into
  // the app error boundary (same guard as resolvePersonalization's).
  // #VERIFY: DedicationOverlay.test.tsx "renders nothing when the payload
  // values shape is malformed".
  const values: unknown = personalization.values
  if (typeof values !== 'object' || values === null || Array.isArray(values)) return null
  const record = values as Record<string, unknown>

  const name = record.protagonist_first_name
  if (typeof name !== 'string' || name === '') return null

  const kinship = record.dedication
  const line =
    typeof kinship !== 'string' || kinship === '' ? `For ${name}` : `For ${name}, love ${kinship}`

  return (
    <p className="reader-dedication" data-testid="dedication">
      {line}
    </p>
  )
}
