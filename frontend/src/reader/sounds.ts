/**
 * Reader UI sound effects (W4.2, D7): page turn, choice tap, ending chime.
 *
 * These are PLACEHOLDER sounds, synthesized at runtime via the WebAudio API
 * (short envelopes on plain oscillator tones), the same placeholder
 * convention `kid/Mascot.tsx` uses for its vector art ("placeholder... the
 * curated illustrated set replaces them later without touching callers").
 * No binary audio asset is committed: a curated SFX set (the media
 * recommendation's "10-20 short SFX at 10-30KB each, app-bundled once in
 * the service-worker precache") replaces this module's synthesis later
 * without changing its exported function signatures.
 *
 * Every function here is a best-effort side effect: it must never throw out
 * of a click handler or a render-effect over something as inconsequential
 * as a chime not playing (#EDGE: browser-compat, and the autoplay-policy
 * case below).
 */

// #EDGE: browser-compat: Safari historically only exposed `webkitAudioContext`.
// This is the standard fallback shape; TS has no ambient type for the
// prefixed constructor, so it is looked up defensively off `window`.
type AudioContextConstructor = typeof AudioContext

function resolveAudioContextConstructor(): AudioContextConstructor | null {
  if (typeof window === 'undefined') return null
  const candidate =
    window.AudioContext ??
    (window as unknown as { webkitAudioContext?: AudioContextConstructor }).webkitAudioContext
  return candidate ?? null
}

let sharedContext: AudioContext | null = null
// Once a context construction/resume has failed, stop retrying for the rest
// of the session rather than risk a repeated console error per sound.
let contextUnavailable = false

/**
 * Lazily create (or reuse) a single shared AudioContext for every sound this
 * module plays. Returns null when WebAudio is unsupported or construction
 * failed; callers treat null as "silently do nothing".
 *
 * #ASSUME: timing dependencies: browsers only allow an AudioContext to start
 * (or resume from 'suspended') inside a user-gesture call stack. The choice
 * tap sound is always triggered from a real click handler, so the FIRST
 * sound played each session reliably starts the context; page-turn and
 * ending sounds fire from a React effect a tick after the gesture that
 * caused them (a page turn/ending always follows a choice tap in this
 * reader), so by the time they run the context this function returns is
 * already running. A context that never got a first user gesture (e.g. a
 * screen-reader-driven page load with no tap yet) simply plays nothing
 * until the first tap, which is the correct silent degrade, not an error.
 */
function getAudioContext(): AudioContext | null {
  if (contextUnavailable) return null
  if (sharedContext) {
    // Autoplay policies can leave a previously-created context 'suspended'
    // after a navigation; resume is safe to call unconditionally and a
    // rejection here is not worth surfacing.
    if (sharedContext.state === 'suspended') {
      void sharedContext.resume().catch(() => undefined)
    }
    return sharedContext
  }
  const Ctor = resolveAudioContextConstructor()
  if (!Ctor) {
    contextUnavailable = true
    return null
  }
  try {
    sharedContext = new Ctor()
    // A freshly constructed context can itself start 'suspended' (some
    // browsers create it that way outside a user gesture); attempt the same
    // resume a reused context gets above, so the very first sound of a
    // session is not silently dropped.
    if (sharedContext.state === 'suspended') {
      void sharedContext.resume().catch(() => undefined)
    }
    return sharedContext
  } catch {
    contextUnavailable = true
    return null
  }
}

interface ToneSpec {
  /** Oscillator waveform. */
  type: OscillatorType
  /** Starting frequency in Hz. */
  freqStart: number
  /** Ending frequency in Hz (equal to freqStart for a flat tone). */
  freqEnd: number
  /** Total tone duration in seconds. */
  duration: number
  /** Peak gain (0-1); kept low across every sound in this module so SFX
   * never compete with read-aloud or story ambience. */
  peakGain: number
  /** Delay, in seconds, from "now" before this tone starts (for chords/arpeggios). */
  startOffset?: number
}

/** Schedule one short tone with a soft attack/decay envelope. Never throws. */
function playTone(ctx: AudioContext, spec: ToneSpec): void {
  try {
    const now = ctx.currentTime + (spec.startOffset ?? 0)
    const oscillator = ctx.createOscillator()
    const gain = ctx.createGain()
    oscillator.type = spec.type
    oscillator.frequency.setValueAtTime(spec.freqStart, now)
    if (spec.freqEnd !== spec.freqStart) {
      oscillator.frequency.linearRampToValueAtTime(spec.freqEnd, now + spec.duration)
    }
    // Soft attack (avoids a click), then decay to silence before the tone ends.
    const attack = Math.min(0.015, spec.duration / 4)
    gain.gain.setValueAtTime(0, now)
    gain.gain.linearRampToValueAtTime(spec.peakGain, now + attack)
    gain.gain.exponentialRampToValueAtTime(0.0001, now + spec.duration)
    oscillator.connect(gain)
    gain.connect(ctx.destination)
    oscillator.start(now)
    oscillator.stop(now + spec.duration + 0.02)
  } catch {
    // #EDGE: kid-safe failure: a scheduling error (e.g. a mocked/partial
    // AudioContext in an unusual embedder) must not propagate.
  }
}

/**
 * Gentle page-turn swish: a quick descending sweep, low volume. Fires on a
 * stop advance (a page turn at 3-5/5-8, or a rendered-stop change at 8-11+).
 */
export function playPageTurnSound(): void {
  const ctx = getAudioContext()
  if (!ctx) return
  playTone(ctx, { type: 'sine', freqStart: 520, freqEnd: 240, duration: 0.16, peakGain: 0.05 })
}

/** Soft acknowledgment tick on a choice tap: brief, unobtrusive. */
export function playChoiceTapSound(): void {
  const ctx = getAudioContext()
  if (!ctx) return
  playTone(ctx, { type: 'triangle', freqStart: 700, freqEnd: 700, duration: 0.05, peakGain: 0.045 })
}

/** Warm three-note major chime on reaching an ending. */
export function playEndingChimeSound(): void {
  const ctx = getAudioContext()
  if (!ctx) return
  // C5, E5, G5: a simple, warm major triad, gently arpeggiated.
  const notes = [523.25, 659.25, 783.99]
  notes.forEach((freq, index) => {
    if (ctx) {
      playTone(ctx, {
        type: 'sine',
        freqStart: freq,
        freqEnd: freq,
        duration: 0.22,
        peakGain: 0.06,
        startOffset: index * 0.11,
      })
    }
  })
}

/** Test-only reset: drops the memoized context/unavailability flag so each
 * test starts from a clean slate against its own mocked AudioContext. */
export function _resetAudioContextForTests(): void {
  sharedContext = null
  contextUnavailable = false
}
