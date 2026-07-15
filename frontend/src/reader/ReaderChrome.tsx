import type { ReactNode } from 'react'

import { ProgressBar } from '@ds/components/ProgressBar'
import { StatusBadge } from '@ds/components/StatusBadge'
import { useOnlineStatus } from '../hooks/useOnlineStatus'

export interface ReaderChromeProps {
  /** 0-100 reading progress. */
  percent: number
  /** Human label for the progress bar, e.g. "2 of 5 pages explored". */
  label: string
  /**
   * Show the label's text, not just the bar's fill and aria-label. Defaults to
   * false: the percent is computed against all of the story's nodes, not the
   * reachable subset for the branch taken, so it can under-report and a
   * playthrough can end without ever showing 100%. Only pass true once the
   * caller has a total it can vouch for.
   */
  showLabel?: boolean
  /**
   * Optional leading control, rendered at the start of the bar. The reader
   * passes an always-visible "Leave" button here so a child can exit a story
   * at any point, not only from the ending screen.
   */
  back?: ReactNode
}

/**
 * The reader's slim sticky top bar: reading progress plus a connection badge
 * that appears only while offline. Being online is the unremarkable normal,
 * so no badge renders then; going offline shows a kid-readable "No internet"
 * so the change of state is the thing that gets named.
 */
export function ReaderChrome({ percent, label, showLabel = false, back }: ReaderChromeProps) {
  const online = useOnlineStatus()
  return (
    <header className="reader-chrome">
      {back}
      {online ? null : <StatusBadge status="offline" label="No internet" />}
      <ProgressBar value={percent} label={label} showLabel={showLabel} />
    </header>
  )
}
