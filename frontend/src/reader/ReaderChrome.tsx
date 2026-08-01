import type { ReactNode } from 'react'

import { ProgressBar } from '@ds/components/ProgressBar'
import { StatusBadge } from '@ds/components/StatusBadge'
import { useOnlineStatus } from '../hooks/useOnlineStatus'

export interface ReaderChromeProps {
  /**
   * The reading-position indicator (W1.2/AL-029, replacing the old
   * corpus-coverage `percent`/`label` pair). `complete: true` renders the
   * design system's real `ProgressBar` at a genuinely-true 100% -- the only
   * percent this chrome ever shows, because "the story is finished" is the
   * one completion figure that is actually known. Otherwise it renders a
   * plain "Page N" text pill with no percent or fill semantics at all: the
   * corpus carries no reliable "how much is left on the path this child
   * took" figure (see `readerProgress.ts`), so nothing here fabricates one.
   * `label` is always the pill's own VISIBLE text in that case, not a hidden
   * aria-only string, so there is no separate description that can drift out
   * of sync with what a sighted reader sees (AL-029's original complaint:
   * the old bar's `aria-label` kept naming a figure the visible UI already
   * hid).
   */
  position: { label: string; complete?: boolean }
  /**
   * Show the `complete` `ProgressBar`'s own numeric label text, not just its
   * fill and aria-label. Defaults to false, unchanged from the pre-W1.2
   * chrome: the finished-story bar's aria-label already announces it, and
   * the ending screen's own heading carries the celebratory message
   * visibly. Has no effect while `position.complete` is falsy -- the plain
   * text pill is always visible.
   */
  showLabel?: boolean
  /**
   * Optional leading control, rendered at the start of the bar. The reader
   * passes an always-visible "Leave" button here so a child can exit a story
   * at any point, not only from the ending screen.
   */
  back?: ReactNode
  /**
   * Optional trailing control, rendered at the end of the bar. The reader
   * passes the A/A+/A++ text-size picker here (UX-K2).
   */
  fontControl?: ReactNode
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
  position,
  showLabel = false,
  back,
  fontControl,
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
            readAloud.speaking
              ? 'reader-tts-toggle reader-tts-toggle--speaking'
              : 'reader-tts-toggle'
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
      {position.complete ? (
        <ProgressBar value={100} label={position.label} showLabel={showLabel} />
      ) : (
        // W1.2/AL-029: a plain, honest position readout -- no percent, no
        // fill. No separate aria-label is set here on purpose: a <p>'s own
        // text content IS its accessible name, so a screen reader can never
        // announce something different from what a sighted reader sees.
        <p className="reader-chrome__position" data-testid="reader-position">
          {position.label}
        </p>
      )}
      {fontControl}
    </header>
  )
}
