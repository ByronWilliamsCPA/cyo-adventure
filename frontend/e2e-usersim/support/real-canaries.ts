/**
 * I5 canaries for the real-tier usersim walk (walk-real.spec.ts, task B3a).
 *
 * The mocked tier's canaries (invariants.ts's GUARDIAN_ONLY_CANARY /
 * FAMILY_B_CANARY) are literals embedded into route-mocked fixture bodies:
 * a false negative there costs nothing, because the mock IS the row. On the
 * real tier there is no mock; the canary must be a REAL row in the REAL
 * database, or the "kid never sees it" assertion in invariants.ts is a check
 * that cannot fail (the exact defect class task B3a's brief calls out).
 *
 * Both canaries below are literals that already exist in this repo's
 * deterministic dev-data seed (scripts/seed_dev_data.py), reused rather than
 * re-seeded, so this module adds no new mutation of its own:
 *
 * - REAL_FAMILY_B_CANARY: the name of "Unrelated Family"
 *   (_seed_unrelated_family), a second family the seeded dev-admin/
 *   dev-guardian bearers do not belong to. Legitimate for the admin ring
 *   only (GET /v1/admin/families lists every family, cross-family by
 *   design); neither a plain guardian nor the kid ring may ever see it.
 * - REAL_GUARDIAN_ONLY_CANARY: the moderation-finding message seeded onto
 *   the in-review "Bridge Builder" story (_flagged_moderation_report, "Dev
 *   seed: sample flag so the review queue has work."), owned by the Dev
 *   Family both dev-guardian and dev-admin belong to. Legitimate for the
 *   guardian/admin rings (GET /v1/storybooks/s_bridge_builder/review); the
 *   kid ring has no auth path to that endpoint at all and must never render
 *   it.
 *
 * `proveRealCanariesExist` reads both rows through the real backend as the
 * privileged bearer that legitimately sees each one, BEFORE the walk starts,
 * per the brief: "assert its presence from the privileged side before
 * asserting its absence from the kid side." Both calls are GETs; nothing
 * here mutates state, including across the family boundary the walk itself
 * must also never cross by write.
 */
import { expect } from '@playwright/test'

import type { FamilyListView, ReviewSurfaceView } from '../../src/client/types.gen'
import { BACKEND } from '../../e2e-real/real-stack'
import type { RoleFamilyCanaries } from './invariants'

// scripts/seed_dev_data.py _GUARDIAN_SUBJECT / _ADMIN_SUBJECT. In
// ENVIRONMENT=local the backend trusts the bearer string directly as the
// authn subject (see real-stack.ts).
const GUARDIAN_BEARER = 'dev-guardian'
const ADMIN_BEARER = 'dev-admin'

// scripts/seed_dev_data.py _seed_unrelated_family: `Family(name="Unrelated
// Family")`. Kept as one literal here (not re-derived from a fixture id)
// because the family has no fixed id of its own to key off, unlike
// _UNRELATED_PROFILE_ID; the name is what the admin UI (FamiliesTab.tsx)
// and GET /v1/admin/families both expose verbatim.
export const REAL_FAMILY_B_CANARY = 'Unrelated Family'

// scripts/seed_dev_data.py _flagged_moderation_report's `message`, seeded
// onto the review story `_REVIEW_STORY_ID` = 's_bridge_builder'
// (reset_e2e_real_state.py). Rendered verbatim by ReviewPassage.tsx's
// `finding.message` on both the guardian and admin review surfaces.
export const REAL_GUARDIAN_ONLY_CANARY = 'Dev seed: sample flag so the review queue has work.'

export const REAL_CANARIES: RoleFamilyCanaries = {
  guardianOnly: REAL_GUARDIAN_ONLY_CANARY,
  familyB: REAL_FAMILY_B_CANARY,
}

const REVIEW_STORY_ID = 's_bridge_builder'

async function authedGet(bearer: string, path: string): Promise<Response> {
  return fetch(`${BACKEND}${path}`, {
    headers: { Authorization: `Bearer ${bearer}` },
    signal: AbortSignal.timeout(5000),
  })
}

/**
 * Assert both real-tier I5 canaries exist, reading each through the bearer
 * that legitimately sees it. Call once, before any persona's walk starts
 * (walk-real.spec.ts's `test.beforeAll`).
 *
 * Deliberately throws a descriptive error rather than delegating to
 * invariants.ts's `recordAndThrow`: a missing canary here is not an I5
 * finding (nothing has rendered anything yet), it is a broken seed/reset
 * pipeline, and the fix is "re-run scripts/seed_dev_data.py", not "audit the
 * app for a leak". Conflating the two would send whoever reads a red run
 * straight to the wrong investigation.
 */
export async function proveRealCanariesExist(): Promise<void> {
  const familiesRes = await authedGet(ADMIN_BEARER, '/api/v1/admin/families')
  expect(
    familiesRes.ok,
    `GET /admin/families as ${ADMIN_BEARER} failed (HTTP ${familiesRes.status}); cannot prove ` +
      'the I5 cross-family canary exists before the walk starts.'
  ).toBe(true)
  // Cast to the OpenAPI-generated response type (frontend/src/client/types.gen.ts,
  // regenerated from FamilyListView in src/cyo_adventure/api/schemas.py) rather
  // than a hand-written shape: `.json()` still returns `unknown` at runtime, so
  // this remains an assertion, but it is now an assertion against a
  // compiler-checked, CI-drift-gated shape. A future rename of `FamilyView.name`
  // fails `npm run typecheck` here, instead of quietly making `hasFamilyB`
  // always false the way the hand-rolled shape did for `passage.message` below.
  const families = (await familiesRes.json()) as FamilyListView
  const hasFamilyB = families.families.some((family) => family.name === REAL_FAMILY_B_CANARY)
  expect(
    hasFamilyB,
    `seeded "${REAL_FAMILY_B_CANARY}" is missing from GET /admin/families as ${ADMIN_BEARER}. ` +
      'scripts/seed_dev_data.py did not run, or _seed_unrelated_family regressed; ' +
      'without this row I5 cannot fail on the real tier no matter what the kid ' +
      'session renders, which is exactly the defect this proof step exists to catch.'
  ).toBe(true)

  const reviewRes = await authedGet(GUARDIAN_BEARER, `/api/v1/storybooks/${REVIEW_STORY_ID}/review`)
  expect(
    reviewRes.ok,
    `GET /storybooks/${REVIEW_STORY_ID}/review as ${GUARDIAN_BEARER} failed ` +
      `(HTTP ${reviewRes.status}); cannot prove the I5 guardian-only canary exists ` +
      'before the walk starts. scripts/reset_e2e_real_state.py should have reverted ' +
      `${REVIEW_STORY_ID} to in_review; re-run it if this persists.`
  ).toBe(true)
  // Same reasoning as the families cast above: type from the generated
  // ReviewSurfaceView (src/cyo_adventure/api/schemas.py's ReviewSurfaceView,
  // via FlaggedPassage/FindingView) rather than a hand-written shape. The
  // message lives on each finding (FlaggedPassage.findings[].message), not on
  // the passage itself; typing this from the generated shape is what makes
  // `passage.message` a compile error instead of a silently-undefined read.
  const review = (await reviewRes.json()) as ReviewSurfaceView
  const hasGuardianOnly = review.flagged_passages.some((passage) =>
    passage.findings.some((finding) => finding.message === REAL_GUARDIAN_ONLY_CANARY)
  )
  expect(
    hasGuardianOnly,
    `seeded flag message "${REAL_GUARDIAN_ONLY_CANARY}" is missing from ` +
      `GET /storybooks/${REVIEW_STORY_ID}/review as ${GUARDIAN_BEARER}. ` +
      'scripts/seed_dev_data.py did not run, or _flagged_moderation_report ' +
      'regressed; without this row I5 cannot fail on the real tier no matter ' +
      'what the kid session renders, which is exactly the defect this proof ' +
      'step exists to catch.'
  ).toBe(true)
}
