import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

import { ProgressBar } from '@ds/components/ProgressBar'
import { StatusBadge } from '@ds/components/StatusBadge'
import { useOnlineStatus } from '../hooks/useOnlineStatus'
import { emitReaderSoundEvent, onReaderSoundEvent } from './readerSoundEvents'
import { playChoiceTapSound, playEndingChimeSound, playPageTurnSound } from './sounds'
import {
  DEVICE_PREFERENCE_KEY,
  getSoundMutedPreference,
  setSoundMutedPreference,
} from './soundPreference'

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
   * The bound persistent character's name (ADR-028), or null/undefined when
   * no character is bound to this read. Rendered as a small "Playing as"
   * label; omitted entirely (no placeholder, no empty label) when absent,
   * matching every other optional chrome affordance's own pattern
   * (`readAloud`, `flag`).
   */
  characterName?: string | null
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
  /**
   * Bookmarks affordance (Phase 4b). Same optional-ReactNode shape as
   * `flag`, for the same reason: `Reader.tsx` (via `BookmarksButton`) owns
   * its own open/save/load/delete state, and ReaderChrome only needs a slot
   * to render it in.
   */
  bookmarks?: ReactNode
  /**
   * Profile id for per-profile sound-mute persistence (W4.2). Optional and
   * not threaded through by any caller today: `Reader.tsx` does not pass it
   * (out of scope for this change; see `soundPreference.ts`'s doc comment).
   * Omitted, the mute toggle falls back to one device-level preference
   * instead of a true per-profile one. When a future change threads a real
   * profile id through, per-profile scoping activates with no further
   * change to this component.
   */
  profileId?: string
}

/**
 * The reader's slim sticky top bar: reading progress plus a connection badge
 * that appears only while offline. Being online is the unremarkable normal,
 * so no badge renders then; going offline shows a kid-readable "No internet"
 * so the change of state is the thing that gets named.
 *
 * Also owns the sound-effects mute toggle (W4.2, D7) end to end: default
 * resolution, persistence, and playback. See `readerSoundEvents.ts`'s doc
 * comment for why sound *triggering* lives here rather than in `Reader.tsx`
 * (a concurrent agent owns that file for this change): page-turn and
 * ending-chime moments are derived from this component's own `position`
 * prop, which already changes on every page turn and the moment the story
 * completes; choice-tap has no equivalent prop, so it is detected via a
 * document-level click listener matching `Reader.tsx`'s existing (unedited)
 * `data-testid="choice-{id}"` markup on each `ChoiceButton`.
 */
export function ReaderChrome({
  position,
  characterName = null,
  showLabel = false,
  back,
  fontControl,
  readAloud,
  flag,
  bookmarks,
  profileId,
}: ReaderChromeProps) {
  const online = useOnlineStatus()
  const headerRef = useRef<HTMLElement>(null)
  const mutePreferenceKey = profileId ?? DEVICE_PREFERENCE_KEY
  // `null` = "not yet resolved" (the very first render, before the mount
  // effect below has had a chance to check the stored preference and the
  // reduce-motion signal); treated as muted in the meantime so no sound can
  // play before the real default is known.
  const [muted, setMuted] = useState<boolean | null>(null)
  const effectiveMuted = muted ?? true

  // Resolve the mute default once per mount / preference-key change: an
  // explicit stored choice wins; otherwise fall back to the plan default
  // (sound on, except a reduce_motion profile default of muted). Mirrors
  // Reader.tsx's own reduce-motion detection (OS media query OR the
  // guardian-set per-profile flag riding in as data-reduce-motion on the
  // kid shell, see band-tokens.css) -- done here via `headerRef` since this
  // component has no `ageBand`/profile data of its own to look the flag up
  // any other way.
  // #ASSUME: timing dependencies: the resolution itself is deferred through
  // setTimeout(fn, 0) rather than calling setMuted directly in the effect
  // body; a direct call here would set state synchronously from inside the
  // effect, which `react-hooks/set-state-in-effect` flags as a
  // cascading-render risk (the established fix elsewhere in this codebase,
  // e.g. guardian/BudgetBanner.tsx and guardian/NotificationBell.tsx). No
  // sound can play before this resolves regardless (`effectiveMuted`
  // defaults `null` to muted), so the one-tick delay is inaudible.
  useEffect(() => {
    const resolve = () => {
      const stored = getSoundMutedPreference(mutePreferenceKey)
      if (stored !== undefined) {
        setMuted(stored)
        return
      }
      // #EDGE: browser-compat: jsdom implements neither matchMedia nor a
      // real DOM tree rooted under data-reduce-motion in every test; both
      // guards degrade to "no reduced-motion signal" rather than throwing.
      const reduceMotion =
        (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false) ||
        Boolean(headerRef.current?.closest('[data-reduce-motion="true"]'))
      setMuted(reduceMotion)
    }
    const timer = setTimeout(resolve, 0)
    return () => clearTimeout(timer)
  }, [mutePreferenceKey])

  const toggleMuted = (): void => {
    const next = !effectiveMuted
    setMuted(next)
    setSoundMutedPreference(mutePreferenceKey, next)
  }

  // Page-turn sound: the position label changes on every page turn (page
  // bands) and every rendered-stop change (flowed bands, ADR-026); skip the
  // very first label the component sees (mount), which is not a turn.
  const lastLabelRef = useRef<string | null>(null)
  useEffect(() => {
    const previous = lastLabelRef.current
    lastLabelRef.current = position.label
    if (previous !== null && previous !== position.label) {
      emitReaderSoundEvent('page-turn')
    }
  }, [position.label])

  // Ending chime: fires once, the moment `position.complete` first becomes
  // true (never on mount already-complete, e.g. a caller re-rendering an
  // already-finished ending screen after a font-size change).
  const wasCompleteRef = useRef(false)
  useEffect(() => {
    const isComplete = position.complete === true
    if (isComplete && !wasCompleteRef.current) {
      emitReaderSoundEvent('ending')
    }
    wasCompleteRef.current = isComplete
  }, [position.complete])

  // Choice tap: document-level delegation against Reader.tsx's existing,
  // unedited `data-testid="choice-{id}"` markup (see the module doc comment
  // on readerSoundEvents.ts for why this is the chosen integration point).
  useEffect(() => {
    function onDocumentClick(event: MouseEvent): void {
      const target = event.target
      if (!(target instanceof Element)) return
      // #ASSUME: UI state: a document-level listener sees clicks from anywhere
      // in the tree, including inside a modal rendered over the reader. The
      // design-system Dialog used to shield it by accident: its dialog element
      // carried an onClick calling stopPropagation(), and React's synthetic
      // stopPropagation also stops the native event, so nothing inside a dialog
      // ever reached document. That handler was a mouse listener on a
      // role="dialog" element, tripped jsx-a11y, and was removed; the shielding
      // went with it. Guard here instead of putting the listener back: the
      // assumption belongs to this delegation, not to every dialog that might
      // ever render choice-like markup.
      // #VERIFY: covered by "ignores clicks originating inside a modal dialog"
      // in ReaderChrome.test.tsx.
      if (target.closest('[role="dialog"]')) return
      if (target.closest('[data-testid^="choice-"]')) {
        emitReaderSoundEvent('choice-tap')
      }
    }
    document.addEventListener('click', onDocumentClick)
    return () => document.removeEventListener('click', onDocumentClick)
  }, [])

  // The single playback subscription: every sound moment, muted or not,
  // funnels through here so there is exactly one place that decides
  // whether a sound actually plays.
  //
  // #CRITICAL: timing dependencies: this MUST be a layout effect, not a
  // passive one. Each listener captures `effectiveMuted` from the render that
  // scheduled it, so the subscription is only correct once it has been
  // re-established for the current value. A layout effect runs synchronously
  // inside the commit that produced the DOM, and entirely before any passive
  // effect, which closes two distinct windows a passive subscription leaves
  // open:
  //   1. Microtask gap. When the mute value settles from an update React is
  //      not already flushing synchronously (here: the deferred resolver
  //      above, whose setMuted lands outside any act()/flushSync boundary),
  //      the passive flush is scheduled in a later scheduler macrotask. The
  //      rendered DOM already says "sound is on" while the bus still holds the
  //      previous render's muted closure, so a tap arriving in between is
  //      silently swallowed. This is specific to that trigger, not a property
  //      of useEffect in general: React also flushes passive effects
  //      synchronously inside act() and before a subsequent render.
  //   2. Declaration-order gap. A single passive flush runs every cleanup
  //      before any create, then the creates in hook order. Were this
  //      subscription passive, a commit changing BOTH the mute value and the
  //      position would run its cleanup (emptying the bus) and then reach the
  //      page-turn and ending emitters declared ABOVE it, which would emit
  //      into an empty bus and drop the sound outright. That is ordering
  //      rather than timing, so act() cannot paper over it either.
  // Issue #588's CI flake is consistent with window 1, where the test's own
  // MutationObserver-based wait resolved inside exactly that gap; per that
  // issue, causation was established by widening the race rather than by
  // reproducing the original failure.
  // #VERIFY: the three "(issue #588)" tests in ReaderChrome.test.tsx. All
  // three fail when this is reverted to `useEffect`. The sibling page-turn and
  // ending tests that do not also change the mute value in the same commit
  // stay green either way, so they are not guards for this.
  useLayoutEffect(() => {
    const unsubscribe = [
      onReaderSoundEvent('page-turn', () => {
        if (!effectiveMuted) playPageTurnSound()
      }),
      onReaderSoundEvent('choice-tap', () => {
        if (!effectiveMuted) playChoiceTapSound()
      }),
      onReaderSoundEvent('ending', () => {
        if (!effectiveMuted) playEndingChimeSound()
      }),
    ]
    return () => unsubscribe.forEach((unsub) => unsub())
  }, [effectiveMuted])

  return (
    <header className="reader-chrome" ref={headerRef}>
      {back}
      {bookmarks}
      {flag}
      <button
        type="button"
        className={
          effectiveMuted ? 'reader-sound-toggle' : 'reader-sound-toggle reader-sound-toggle--on'
        }
        aria-pressed={!effectiveMuted}
        aria-label={effectiveMuted ? 'Turn sound effects on' : 'Turn sound effects off'}
        onClick={toggleMuted}
      >
        <span aria-hidden="true">{effectiveMuted ? '🔇' : '🔊'}</span>
      </button>
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
      {characterName ? (
        <p className="reader-chrome__character" data-testid="reader-character-name">
          Playing as {characterName}
        </p>
      ) : null}
      {fontControl}
    </header>
  )
}
