/**
 * Shared age-band/length/style option lists for the guardian/admin
 * story-request surfaces (RequestsPage.tsx's confirm-strip and
 * RequestStoryForm.tsx's create form, WS-B PR2). Kept in their own module,
 * not exported from RequestsPage.tsx, because exporting plain constants
 * alongside a component trips the `react-refresh/only-export-components`
 * lint rule.
 */

// ADR-011 restricts the gamebook narrative style to teen bands; both surfaces
// reset narrative_style back to 'prose' when the band select leaves this set.
export const TEEN_BANDS = ['13-16', '16+']
export const AGE_BANDS = ['3-5', '5-8', '8-11', '10-13', '13-16', '16+']
export const LENGTHS = ['short', 'medium', 'long']

/**
 * Human-readable option labels for the raw age-band values. The VALUES above
 * are the API contract (they travel in request/approve bodies) and must stay
 * raw; only the rendered <option> text uses these labels, so tests and e2e
 * specs keep selecting by value.
 */
export const AGE_BAND_LABELS: Record<string, string> = {
  '3-5': 'Ages 3-5',
  '5-8': 'Ages 5-8',
  '8-11': 'Ages 8-11',
  '10-13': 'Ages 10-13',
  '13-16': 'Ages 13-16',
  '16+': 'Ages 16+',
}

/** Label for a band value; falls back to `Ages <value>` for an unknown band. */
export function ageBandLabel(band: string): string {
  return AGE_BAND_LABELS[band] ?? `Ages ${band}`
}
