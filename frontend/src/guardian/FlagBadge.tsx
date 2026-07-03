import type { FindingVerdict } from './reviewApi'

export type BadgeTone = 'block' | 'flag' | 'advisory' | 'clean' | 'processing' | 'unscreened'

const TONE_LABEL: Record<BadgeTone, string> = {
  block: 'Blocked',
  flag: 'Flagged',
  advisory: 'Advisory',
  clean: 'Clean',
  processing: 'Processing…',
  unscreened: 'Unscreened',
}

/**
 * Severity pill for the guardian console (queue rows and review findings).
 * Built from guardian.css color vars because the design system has no flag
 * badge; StatusBadge only covers connection states.
 */
export function FlagBadge({ tone, label }: { tone: BadgeTone; label?: string }) {
  return <span className={`flag-badge flag-badge--${tone}`}>{label ?? TONE_LABEL[tone]}</span>
}

/** Map a moderation verdict to a badge tone (pass shows as advisory). */
export function verdictTone(verdict: FindingVerdict): BadgeTone {
  if (verdict === 'block') return 'block'
  if (verdict === 'flag') return 'flag'
  return 'advisory'
}
