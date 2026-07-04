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
}

/**
 * The reader's slim sticky top bar: always-visible connection status and reading
 * progress. Chrome is intentionally persistent (offline reading is a core
 * feature, so connection status stays visible) per the phase-4a wireframes.
 */
export function ReaderChrome({ percent, label, showLabel = false }: ReaderChromeProps) {
  const online = useOnlineStatus()
  return (
    <header className="reader-chrome">
      <StatusBadge status={online ? 'connected' : 'offline'} />
      <ProgressBar value={percent} label={label} showLabel={showLabel} />
    </header>
  )
}
