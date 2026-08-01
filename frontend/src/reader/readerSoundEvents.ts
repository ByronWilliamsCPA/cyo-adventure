/**
 * A tiny module-level pub/sub bus for the three reader UI sound moments
 * (W4.2 / D7: page turn, choice tap, ending chime).
 *
 * Why this exists instead of a prop: `ReaderChrome.tsx` is the only reader
 * file this change may touch (a concurrent agent owns `Reader.tsx` and
 * `ReaderPage.tsx`), and neither `Reader.tsx`'s existing `ReaderChromeProps`
 * wiring nor its choice-button markup can be edited to call an emitter
 * directly. `ReaderChrome` already learns about page turns and endings from
 * its existing `position` prop (see `ReaderChrome.tsx`'s own effects), so
 * those two events are emitted onto this bus from inside `ReaderChrome`
 * itself, purely as a matter of internal consistency (one playback path for
 * all three sounds, see below) rather than necessity.
 *
 * `choice-tap` has no equivalent prop: it is detected via a document-level
 * click listener in `ReaderChrome` matching the `data-testid="choice-{id}"`
 * attribute `Reader.tsx` already renders on every `ChoiceButton` (unedited,
 * pre-existing markup), and emitted onto this same bus.
 *
 * The indirection through a bus (rather than `ReaderChrome` just calling the
 * sound functions directly from its own effects/listener) is deliberate
 * groundwork: when `Reader.tsx` is next free to change, its `choose()`
 * handler can call `emitReaderSoundEvent('choice-tap')` directly and the
 * document-click listener below can be deleted, with no change needed to
 * how the sound actually plays. Until then, `ReaderChrome` is both the sole
 * publisher and the sole subscriber.
 */

export type ReaderSoundEventName = 'page-turn' | 'choice-tap' | 'ending'

type Listener = () => void

const listeners: Record<ReaderSoundEventName, Set<Listener>> = {
  'page-turn': new Set(),
  'choice-tap': new Set(),
  ending: new Set(),
}

/** Publish one reader sound moment. Never throws: a listener that throws is
 * caught and dropped rather than breaking sibling listeners or the caller. */
export function emitReaderSoundEvent(name: ReaderSoundEventName): void {
  for (const listener of listeners[name]) {
    try {
      listener()
    } catch {
      // #EDGE: kid-safe failure: a sound is decoration, never worth a crash.
    }
  }
}

/** Subscribe to one reader sound moment. Returns an unsubscribe function. */
export function onReaderSoundEvent(name: ReaderSoundEventName, listener: Listener): () => void {
  listeners[name].add(listener)
  return () => {
    listeners[name].delete(listener)
  }
}
