import type { FindingVerdict } from './reviewApi'
import type { BadgeTone } from './FlagBadge'

/**
 * Map a moderation verdict to a badge tone (pass shows as advisory).
 *
 * Its own module rather than a second export from FlagBadge.tsx: a file that
 * exports both a component and a plain function breaks React Fast Refresh for
 * that file, which is what `react-refresh/only-export-components` reports. That
 * was the single standing warning in `npm run lint`, and the lint script now
 * runs with --max-warnings 0, so it had to be fixed rather than tolerated.
 */
export function verdictTone(verdict: FindingVerdict): BadgeTone {
  if (verdict === 'block') return 'block'
  if (verdict === 'flag') return 'flag'
  return 'advisory'
}
