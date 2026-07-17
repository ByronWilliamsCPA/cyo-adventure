import { useCallback, useEffect, useState } from 'react'

/**
 * Browser-native read-aloud (K7 / Phase 4b), built directly on the Web
 * Speech API's `SpeechSynthesis` interface per tech-spec: no new dependency.
 * This hook owns only the speak/stop mechanics and the "is it actually
 * usable" check; the caller (Reader.tsx) decides WHETHER to offer it
 * (the profile's `tts_enabled` flag, threaded in from `readAloudPreference`)
 * and WHAT to say (the current passage body, then the visible choice
 * labels).
 */

export interface ReadAloudControls {
  /**
   * True only when the caller passed `enabled` AND the browser's
   * speechSynthesis actually works. A kid never sees a broken button: any
   * failure (the API missing, or a throw while speaking) just turns this
   * false from then on; there is no error state to show mid-story.
   */
  available: boolean
  /** True while an utterance from this hook instance is playing. */
  speaking: boolean
  /**
   * Cancel any in-flight queue and speak the passage body, then (if any)
   * "Your choices are: ..." with the visible choice labels. A no-op when
   * `available` is false.
   */
  speak: (passageBody: string, choiceLabels: string[]) => void
  /** Cancel any in-flight speech. Safe to call whether or not anything is
   * currently speaking, and safe when speechSynthesis is unsupported. */
  stop: () => void
}

function speechSynthesisSupported(): boolean {
  try {
    return (
      typeof window !== 'undefined' &&
      'speechSynthesis' in window &&
      typeof window.SpeechSynthesisUtterance === 'function'
    )
  } catch {
    // #EDGE: browser-compat: a locked-down browser can throw on feature
    // detection itself rather than simply lacking the API; either way, that
    // means "not usable here".
    return false
  }
}

/**
 * @param enabled The profile's `tts_enabled` flag (already gated by the
 *   caller). Read-aloud is never offered unless this is true, regardless of
 *   browser support.
 */
export function useReadAloud(enabled: boolean): ReadAloudControls {
  const [speaking, setSpeaking] = useState(false)
  // Latches true the first time speak() itself throws, so a mid-session
  // failure hides the button rather than leaving a dead control a child
  // keeps tapping with no visible effect.
  const [broken, setBroken] = useState(false)
  // Support is a fixed fact of the current browser for the life of this
  // hook instance; a lazy initializer computes it once (not on every
  // render, and not via a ref read during render) and keeps `available`
  // stable across re-renders that do not change `enabled`.
  const [supported] = useState(() => speechSynthesisSupported())
  const available = enabled && supported && !broken

  const stop = useCallback(() => {
    if (!supported) return
    try {
      window.speechSynthesis.cancel()
    } catch {
      // #EDGE: kid-safe failure: swallow; nothing more to do and no error
      // state to show a child mid-story.
    }
    setSpeaking(false)
  }, [supported])

  // Cancel on unmount so navigating away (or a remount of the reader route)
  // never leaves the browser talking over the next screen.
  useEffect(() => stop, [stop])

  const speak = useCallback(
    (passageBody: string, choiceLabels: string[]) => {
      if (!available) return
      try {
        window.speechSynthesis.cancel()
        const texts = [passageBody]
        if (choiceLabels.length > 0) {
          texts.push(`Your choices are: ${choiceLabels.join(', ')}`)
        }
        const utterances = texts.map((text) => new window.SpeechSynthesisUtterance(text))
        const last = utterances[utterances.length - 1]
        last.onend = () => setSpeaking(false)
        last.onerror = () => setSpeaking(false)
        // Chain: each utterance's onend queues the next one, so the passage
        // body finishes before "Your choices are: ..." starts.
        for (let i = 0; i < utterances.length - 1; i += 1) {
          const next = utterances[i + 1]
          utterances[i].onend = () => window.speechSynthesis.speak(next)
          // #EDGE: kid-safe failure: an earlier utterance erroring must still
          // clear `speaking`, not leave the toggle stuck in its speaking
          // state with nothing left queued.
          utterances[i].onerror = () => setSpeaking(false)
        }
        setSpeaking(true)
        window.speechSynthesis.speak(utterances[0])
      } catch {
        // #EDGE: kid-safe failure: speak() can throw in a broken
        // implementation; hide the button rather than surface an error.
        setSpeaking(false)
        setBroken(true)
      }
    },
    [available]
  )

  return { available, speaking, speak, stop }
}
