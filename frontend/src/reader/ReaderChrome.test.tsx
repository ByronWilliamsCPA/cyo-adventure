import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ReaderChrome } from './ReaderChrome'
import { playChoiceTapSound, playEndingChimeSound, playPageTurnSound } from './sounds'

// W4.2: the mute toggle's playback path goes through sounds.ts's exported
// functions; mocked here so these tests assert "did it decide to play",
// not WebAudio mechanics (covered separately by sounds.test.ts against a
// mocked AudioContext).
vi.mock('./sounds', () => ({
  playPageTurnSound: vi.fn(),
  playChoiceTapSound: vi.fn(),
  playEndingChimeSound: vi.fn(),
}))

function setOnLine(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value })
}
afterEach(() => setOnLine(true))

beforeEach(() => {
  localStorage.clear()
  vi.mocked(playPageTurnSound).mockClear()
  vi.mocked(playChoiceTapSound).mockClear()
  vi.mocked(playEndingChimeSound).mockClear()
})

describe('ReaderChrome', () => {
  it('shows no connection badge while online, just the position pill', () => {
    setOnLine(true)
    render(<ReaderChrome position={{ label: 'Page 2' }} />)
    // Online is the unremarkable normal: no badge (and no jargon) renders.
    expect(screen.queryByText('Connected')).toBeNull()
    expect(screen.queryByRole('status')).toBeNull()
    // W1.2/AL-029: no percent bar while reading, just the visible text pill.
    expect(screen.queryByRole('progressbar')).toBeNull()
    expect(screen.getByTestId('reader-position').textContent).toBe('Page 2')
  })

  it('shows a kid-readable "No internet" badge when the device is offline', () => {
    setOnLine(false)
    render(<ReaderChrome position={{ label: 'Page 1' }} />)
    expect(screen.getByText('No internet')).toBeTruthy()
    expect(screen.queryByText('Offline')).toBeNull()
  })

  it('the position pill text is always visible (no hidden numeric label to withhold)', () => {
    setOnLine(true)
    render(<ReaderChrome position={{ label: 'Page 2' }} />)
    expect(screen.getByText('Page 2')).toBeInTheDocument()
  })

  it('shows a real, true 100% progress bar when the position is complete', () => {
    setOnLine(true)
    render(<ReaderChrome position={{ label: 'You finished this story!', complete: true }} />)
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('100')
    expect(bar.getAttribute('aria-label')).toBe('You finished this story!')
    // showLabel defaults to false: the ProgressBar's own numeric text stays
    // hidden (aria-label still carries it), matching the pre-W1.2 chrome.
    expect(screen.queryByText('You finished this story!')).toBeNull()
  })

  it('shows the complete bar numeric label when the caller vouches for it', () => {
    setOnLine(true)
    render(
      <ReaderChrome position={{ label: 'You finished this story!', complete: true }} showLabel />
    )
    expect(screen.getByText('You finished this story!')).toBeTruthy()
  })

  it('renders the back slot when provided', () => {
    setOnLine(true)
    render(
      <ReaderChrome position={{ label: 'Page 1' }} back={<button type="button">Leave</button>} />
    )
    expect(screen.getByRole('button', { name: 'Leave' })).toBeTruthy()
  })

  it('renders nothing extra when the back slot is omitted (only the always-on sound toggle)', () => {
    setOnLine(true)
    render(<ReaderChrome position={{ label: 'Page 1' }} />)
    // W4.2: the sound-effects mute toggle is always present, unlike back/
    // readAloud/flag which are opt-in slots; this is the one button left.
    expect(screen.getAllByRole('button')).toHaveLength(1)
    expect(screen.queryByRole('button', { name: 'Leave' })).toBeNull()
  })

  describe('read-aloud toggle (K7)', () => {
    it('is not rendered when the readAloud prop is omitted', () => {
      render(<ReaderChrome position={{ label: 'Page 1' }} />)
      expect(screen.queryByLabelText('Read this page aloud')).toBeNull()
      expect(screen.queryByLabelText('Stop reading aloud')).toBeNull()
    })

    it('renders an obvious, unpressed toggle when not speaking', () => {
      const onToggle = vi.fn()
      render(
        <ReaderChrome position={{ label: 'Page 1' }} readAloud={{ speaking: false, onToggle }} />
      )
      const button = screen.getByRole('button', { name: 'Read this page aloud' })
      // The unpressed state is fully observable: aria-pressed=false plus the
      // "Listen" visible affordance. (Dropped a redundant assertion on the
      // reader-tts-toggle--speaking class token, which is driven by the same
      // `speaking` flag as aria-pressed and carries no extra user-facing signal.)
      expect(button).toHaveAttribute('aria-pressed', 'false')
      expect(screen.getByText('Listen')).toBeInTheDocument()
      fireEvent.click(button)
      expect(onToggle).toHaveBeenCalledTimes(1)
    })

    it('shows a visually and semantically distinct pressed state while speaking', () => {
      const onToggle = vi.fn()
      render(
        <ReaderChrome position={{ label: 'Page 1' }} readAloud={{ speaking: true, onToggle }} />
      )
      const button = screen.getByRole('button', { name: 'Stop reading aloud' })
      // The pressed state is fully observable: aria-pressed=true plus the
      // "Stop" visible affordance. (Dropped a redundant assertion on the
      // reader-tts-toggle--speaking class token, which is driven by the same
      // `speaking` flag as aria-pressed and carries no extra user-facing signal.)
      expect(button).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByText('Stop')).toBeInTheDocument()
    })
  })

  describe('flag slot (K15)', () => {
    it('is not rendered when the flag prop is omitted', () => {
      render(<ReaderChrome position={{ label: 'Page 1' }} />)
      expect(screen.queryByRole('button', { name: 'Tell a grown-up' })).toBeNull()
    })

    it('renders the caller-supplied flag node', () => {
      render(
        <ReaderChrome
          position={{ label: 'Page 1' }}
          flag={<button type="button">Tell a grown-up</button>}
        />
      )
      expect(screen.getByRole('button', { name: 'Tell a grown-up' })).toBeTruthy()
    })
  })

  describe('sound-effects mute toggle (W4.2, D7)', () => {
    // The mute default is resolved a tick after mount (deferred via
    // setTimeout(fn, 0) to satisfy react-hooks/set-state-in-effect, see
    // ReaderChrome.tsx); until it resolves the toggle stays in its
    // fail-safe-silent "muted" state (`effectiveMuted` defaults `null` to
    // `true`). Every test below that cares about the RESOLVED default (or
    // that plays a sound, which requires the resolved default to be "on"
    // first) uses `findByRole` to wait for it rather than `getByRole`.

    it('defaults to sound ON when nothing is stored and there is no reduce-motion signal', async () => {
      render(<ReaderChrome position={{ label: 'Page 1' }} />)
      const button = await screen.findByRole('button', { name: 'Turn sound effects off' })
      expect(button).toHaveAttribute('aria-pressed', 'true')
    })

    it('defaults to muted when a reduce_motion ancestor is present (plan default)', async () => {
      render(
        <div data-reduce-motion="true">
          <ReaderChrome position={{ label: 'Page 1' }} />
        </div>
      )
      const button = await screen.findByRole('button', { name: 'Turn sound effects on' })
      expect(button).toHaveAttribute('aria-pressed', 'false')
    })

    it('tapping the toggle flips state and persists across a remount', async () => {
      const { unmount } = render(<ReaderChrome position={{ label: 'Page 1' }} />)
      const button = await screen.findByRole('button', { name: 'Turn sound effects off' })
      fireEvent.click(button)
      expect(screen.getByRole('button', { name: 'Turn sound effects on' })).toHaveAttribute(
        'aria-pressed',
        'false'
      )
      unmount()
      // A fresh mount picks up the persisted choice instead of re-deriving
      // the reduce-motion default.
      render(<ReaderChrome position={{ label: 'Page 1' }} />)
      expect(await screen.findByRole('button', { name: 'Turn sound effects on' })).toHaveAttribute(
        'aria-pressed',
        'false'
      )
    })

    // Kept as the plain-reading version of the choice-tap path: it waits with
    // `findByRole` and then clicks, which is how a caller would use it. It is
    // NOT the guard for issue #588 (it passes with the bug present, which is
    // why it flaked rather than failing); the "(issue #588)" test below is.
    it('plays the choice-tap sound on a click that lands on Reader.tsx-style choice markup', async () => {
      render(
        <div>
          <ReaderChrome position={{ label: 'Page 1' }} />
          <button type="button" data-testid="choice-abc">
            Open the door
          </button>
        </div>
      )
      // Wait for the default (sound ON) to resolve before the tap.
      await screen.findByRole('button', { name: 'Turn sound effects off' })
      fireEvent.click(screen.getByTestId('choice-abc'))
      expect(playChoiceTapSound).toHaveBeenCalledTimes(1)
    })

    it('has the playback subscription live at the microtask the DOM says sound is on (issue #588)', async () => {
      // The deterministic form of the flake that made the sibling test above
      // fail in CI on #585, a branch that changed no reader code. That test
      // waits with `findByRole` and then clicks, which only fails when CI
      // timing happens to open the window; this one opens the window on
      // purpose, so it fails 100% of the time when the bug is present.
      //
      // The window: `findByRole`/`waitFor` resolve from a MutationObserver
      // callback, which runs at the microtask checkpoint right after React
      // mutates the DOM. React's PASSIVE effects (`useEffect`) flush later, in
      // a scheduler macrotask. So between "the toggle's label says sound is on"
      // and "the playback subscription reflects sound being on" there is a real
      // gap, and a tap landing inside it hits the stale mount-time closure
      // (`effectiveMuted === true`) and plays nothing.
      //
      // Registering our own MutationObserver puts this click in exactly that
      // checkpoint. The fix is that the subscription is a LAYOUT effect, which
      // runs synchronously inside the commit that changed the label, before
      // the call stack unwinds and any microtask can run.
      render(
        <div>
          <ReaderChrome position={{ label: 'Page 1' }} />
          <button type="button" data-testid="choice-abc">
            Open the door
          </button>
        </div>
      )
      // Pre-resolution the toggle reads "on" (fail-safe-silent muted state);
      // the attribute flips in place on the same element when the default
      // resolves, which is the mutation observed below.
      const toggle = screen.getByRole('button', { name: 'Turn sound effects on' })
      let observer: MutationObserver | undefined
      let giveUp: ReturnType<typeof setTimeout> | undefined
      try {
        await new Promise<void>((resolve, reject) => {
          observer = new MutationObserver(() => {
            if (toggle.getAttribute('aria-label') !== 'Turn sound effects off') return
            // Deliberately synchronous inside the callback: deferring to a
            // later macrotask would let the passive flush win and make this
            // test flaky in the same way as the sibling it backs up. (A single
            // microtask hop would not, since the queue drains before the next
            // macrotask runs, but there is no reason to spend the margin.)
            fireEvent.click(screen.getByTestId('choice-abc'))
            resolve()
          })
          observer.observe(toggle, { attributes: true, attributeFilter: ['aria-label'] })
          // Without this the only failure signal is a bare 5s vitest timeout,
          // which says nothing about the cause. Regressions that land here:
          // the mute default stops resolving, the toggle is refactored so the
          // label moves between elements instead of flipping in place, or fake
          // timers are introduced into this file and stall the resolver's
          // setTimeout. None of those are the bug this test guards, so say so.
          giveUp = setTimeout(
            () =>
              reject(
                new Error(
                  "the toggle's aria-label never became 'Turn sound effects off', so the " +
                    'race window never opened; the mute default did not resolve, or the ' +
                    'label no longer flips in place on the same element'
                )
              ),
            2000
          )
        })
      } finally {
        observer?.disconnect()
        clearTimeout(giveUp)
      }
      expect(playChoiceTapSound).toHaveBeenCalledTimes(1)
    })

    it('does not play the choice-tap sound while muted', async () => {
      render(
        <div>
          <ReaderChrome position={{ label: 'Page 1' }} />
          <button type="button" data-testid="choice-abc">
            Open the door
          </button>
        </div>
      )
      fireEvent.click(await screen.findByRole('button', { name: 'Turn sound effects off' }))
      fireEvent.click(screen.getByTestId('choice-abc'))
      expect(playChoiceTapSound).not.toHaveBeenCalled()
    })

    it('does not play the choice-tap sound for a click elsewhere in the document', async () => {
      render(
        <div>
          <ReaderChrome position={{ label: 'Page 1' }} />
          <button type="button">Not a choice</button>
        </div>
      )
      await screen.findByRole('button', { name: 'Turn sound effects off' })
      fireEvent.click(screen.getByRole('button', { name: 'Not a choice' }))
      expect(playChoiceTapSound).not.toHaveBeenCalled()
    })

    it('ignores clicks originating inside a modal dialog', async () => {
      // Regression pin for the invariant that went missing when the
      // design-system Dialog dropped its stopPropagation handler (PR #754).
      // That handler was a mouse listener on a role="dialog" element, so it had
      // to go for accessibility; what it was incidentally providing was a
      // shield for this document-level listener. Without the guard in
      // ReaderChrome, a dialog rendering choice-shaped markup over the reader
      // would fire the choice-tap sound behind it.
      render(
        <div>
          <ReaderChrome position={{ label: 'Page 1' }} />
          <div role="dialog" aria-modal="true" aria-label="Confirm">
            <button type="button" data-testid="choice-in-dialog">
              Keep reading
            </button>
          </div>
        </div>
      )
      await screen.findByRole('button', { name: 'Turn sound effects off' })
      fireEvent.click(screen.getByTestId('choice-in-dialog'))
      expect(playChoiceTapSound).not.toHaveBeenCalled()
    })

    it('plays the page-turn sound when the position label changes, not on the first render', async () => {
      const { rerender } = render(<ReaderChrome position={{ label: 'Page 1' }} />)
      await screen.findByRole('button', { name: 'Turn sound effects off' })
      expect(playPageTurnSound).not.toHaveBeenCalled()
      rerender(<ReaderChrome position={{ label: 'Page 2' }} />)
      expect(playPageTurnSound).toHaveBeenCalledTimes(1)
    })

    // The page-turn and ending emitters fire from prop changes, so the
    // MutationObserver trick above cannot reach them: `rerender` is act()-
    // wrapped, and act() flushes passive effects, which closes the microtask
    // window before the emit. They are exposed by the OTHER window the layout
    // effect closes (window 2 in ReaderChrome.tsx's #CRITICAL note): one
    // passive flush runs every cleanup before any create, so a commit that
    // changes the mute value AND the position empties the bus in the
    // subscription's cleanup and then emits from an emitter declared above it.
    // That is ordering rather than timing, which is exactly why it reproduces
    // inside act() while the plain sibling tests below pass with the bug.
    it('plays the page-turn sound when the page turns in the same commit that unmutes (issue #588)', async () => {
      const { rerender } = render(<ReaderChrome position={{ label: 'Page 1' }} />)
      const toggle = await screen.findByRole('button', { name: 'Turn sound effects off' })
      fireEvent.click(toggle)
      vi.mocked(playPageTurnSound).mockClear()
      act(() => {
        fireEvent.click(toggle)
        rerender(<ReaderChrome position={{ label: 'Page 2' }} />)
      })
      expect(playPageTurnSound).toHaveBeenCalledTimes(1)
    })

    it('plays the ending chime exactly once when the position becomes complete', async () => {
      const { rerender } = render(<ReaderChrome position={{ label: 'Page 3' }} />)
      await screen.findByRole('button', { name: 'Turn sound effects off' })
      rerender(<ReaderChrome position={{ label: 'You finished this story!', complete: true }} />)
      expect(playEndingChimeSound).toHaveBeenCalledTimes(1)
      // Re-rendering while still complete (e.g. a font-size change) must not
      // replay the chime.
      rerender(
        <ReaderChrome position={{ label: 'You finished this story!', complete: true }} showLabel />
      )
      expect(playEndingChimeSound).toHaveBeenCalledTimes(1)
    })

    // Same window-2 mechanism as the page-turn guard above, via the ending
    // emitter (also declared above the subscription).
    it('plays the ending chime when the story completes in the same commit that unmutes (issue #588)', async () => {
      const { rerender } = render(<ReaderChrome position={{ label: 'Page 3' }} />)
      const toggle = await screen.findByRole('button', { name: 'Turn sound effects off' })
      fireEvent.click(toggle)
      vi.mocked(playEndingChimeSound).mockClear()
      act(() => {
        fireEvent.click(toggle)
        rerender(<ReaderChrome position={{ label: 'You finished this story!', complete: true }} />)
      })
      expect(playEndingChimeSound).toHaveBeenCalledTimes(1)
    })
  })
})
