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
  /**
   * Read-aloud speaker toggle (K7 / Phase 4b). Present only when the caller
   * has already decided the toggle should be offered: the profile's
   * `tts_enabled` flag is on AND the browser's speechSynthesis is actually
   * usable (see `useReadAloud`'s `available`). ReaderChrome stays a dumb
   * shell, it renders the button but owns no speech logic itself; omit this
   * prop entirely (not a disabled button) when either check fails, so a kid
   * on an unsupported browser or an un-gated profile never sees a dead
   * control.
   */
  readAloud?: {
    /** True while the caller is currently speaking; drives both the visible
     * "speaking" styling and the toggle's aria-pressed state. */
    speaking: boolean
    /** Tapping the toggle: starts speaking, or stops if already speaking. */
    onToggle: () => void
  }
  /**
   * "Tell a grown-up" flag affordance (K15). A full ReactNode, not a
   * speaking/onToggle shape like readAloud: the caller (Reader.tsx via
   * FlagButton) owns its own open/submit state and, unlike the read-aloud
   * toggle, ReaderChrome has no reason to know any of it. Omitted entirely
   * (not a disabled button) when the caller has decided the affordance
   * should not render, e.g. no child session for this profile.
   */
  flag?: ReactNode
}

/**
 * The reader's slim sticky top bar: reading progress plus a connection badge
 * that appears only while offline. Being online is the unremarkable normal,
 * so no badge renders then; going offline shows a kid-readable "No internet"
 * so the change of state is the thing that gets named.
 */
export function ReaderChrome({
  percent,
  label,
  showLabel = false,
  back,
  readAloud,
  flag,
}: ReaderChromeProps) {
  const online = useOnlineStatus()
  return (
    <header className="reader-chrome">
      {back}
      {flag}
      {readAloud ? (
        <button
          type="button"
          className={
            readAloud.speaking ? 'reader-tts-toggle reader-tts-toggle--speaking' : 'reader-tts-toggle'
          }
          aria-pressed={readAloud.speaking}
          aria-label={readAloud.speaking ? 'Stop reading aloud' : 'Read this page aloud'}
          onClick={readAloud.onToggle}
        >
          <span aria-hidden="true">{readAloud.speaking ? '⏹️' : '🔊'}</span>
          {readAloud.speaking ? 'Stop' : 'Listen'}
        </button>
      ) : null}
      {online ? null : <StatusBadge status="offline" label="No internet" />}
      <ProgressBar value={percent} label={label} showLabel={showLabel} />
    </header>
  )
}
