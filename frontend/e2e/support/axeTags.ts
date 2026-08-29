/**
 * Shared axe-core rule scope for every Playwright tier that runs an
 * accessibility scan: `e2e/a11y.spec.ts` (the per-PR gate and its weekly
 * `A11Y_EXTENDED=1` re-run) and, since task B3b, the usersim walk tier's I7
 * invariant (`e2e-usersim/support/invariants.ts`), which the weekly
 * `accessibility-compliance-weekly.yml` job also runs behind the same flag.
 *
 * Extracted to one module rather than left as two independent literals: this
 * repo has already hit the "a copy-pasted second literal silently drifts"
 * defect class once (see invariants.ts's own doc comment on
 * GUARDIAN_ONLY_CANARY/FAMILY_B_CANARY), and the B3b task brief is explicit
 * that I7 must "match the rule set the weekly job already scans with. Do not
 * invent a different rule set." A single source makes that true by
 * construction instead of by discipline.
 */

/**
 * Per-PR CI stays scoped to WCAG 2.1 conformance tags only: fast and
 * non-noisy, so it can gate every PR. The weekly "Accessibility Compliance"
 * workflow (.github/workflows/accessibility-compliance-weekly.yml) sets
 * A11Y_EXTENDED=1 to widen this to WCAG 2.2 (both wcag22a AND wcag22aa:
 * axe's WCAG tags are additive per level, so wcag22aa alone would silently
 * skip the 2.2 Level A criteria, UW-N04) plus axe's "best-practice" rules
 * (e.g. missing landmark/heading structure), without adding that scope, or
 * run time, to every PR.
 */
export const AXE_TAGS =
  process.env.A11Y_EXTENDED === '1'
    ? ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22a', 'wcag22aa', 'best-practice']
    : ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

/**
 * True when an axe violation carries a `wcag*` tag, i.e. it is a WCAG
 * conformance failure rather than axe's own non-normative "best-practice"
 * opinion (missing landmark/heading structure, redundant roles, and
 * similar). See a11y.spec.ts's own `assertNoViolations` for the full
 * rationale behind conformance-fails/structural-reports-only split; this
 * predicate is shared so both callers apply it identically.
 */
export function isConformance(violation: { tags: string[] }): boolean {
  return violation.tags.some((tag) => tag.startsWith('wcag'))
}
