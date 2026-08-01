import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  _resetAudioContextForTests,
  playChoiceTapSound,
  playEndingChimeSound,
  playPageTurnSound,
} from './sounds'

/** Minimal mock of the WebAudio nodes/graph this module touches. */
class MockGainParam {
  setValueAtTime = vi.fn()
  linearRampToValueAtTime = vi.fn()
  exponentialRampToValueAtTime = vi.fn()
}

class MockAudioParam {
  setValueAtTime = vi.fn()
  linearRampToValueAtTime = vi.fn()
}

class MockGainNode {
  gain = new MockGainParam()
  connect = vi.fn()
}

class MockOscillatorNode {
  type = 'sine'
  frequency = new MockAudioParam()
  connect = vi.fn()
  start = vi.fn()
  stop = vi.fn()
}

class MockAudioContext {
  currentTime = 0
  state: AudioContextState = 'running'
  destination = {}
  createGain = vi.fn(() => new MockGainNode())
  createOscillator = vi.fn(() => new MockOscillatorNode())
  resume = vi.fn(() => Promise.resolve())
  close = vi.fn(() => Promise.resolve())
}

describe('reader sounds (W4.2 placeholder WebAudio synthesis)', () => {
  let originalAudioContext: typeof window.AudioContext | undefined

  beforeEach(() => {
    _resetAudioContextForTests()
    originalAudioContext = window.AudioContext
    // #ASSUME: browser-compat: jsdom has no real AudioContext; the module
    // under test looks it up off `window`, so the mock is installed there.
    ;(window as unknown as { AudioContext: unknown }).AudioContext = MockAudioContext
  })

  afterEach(() => {
    if (originalAudioContext) {
      window.AudioContext = originalAudioContext
    } else {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (window as any).AudioContext
    }
  })

  it('reuses a single AudioContext across multiple sounds instead of creating one per call', () => {
    const constructed: MockAudioContext[] = []
    class TrackedAudioContext extends MockAudioContext {
      constructor() {
        super()
        constructed.push(this)
      }
    }
    ;(window as unknown as { AudioContext: unknown }).AudioContext = TrackedAudioContext

    playPageTurnSound()
    playChoiceTapSound()
    playEndingChimeSound()

    expect(constructed).toHaveLength(1)
    // Page turn (1 tone) + choice tap (1 tone) + ending chime (3 tones).
    expect(constructed[0].createOscillator).toHaveBeenCalledTimes(5)
    expect(constructed[0].createGain).toHaveBeenCalledTimes(5)
  })

  it('schedules the ending chime as three tones (an arpeggiated triad)', () => {
    const constructed: MockAudioContext[] = []
    class TrackedAudioContext extends MockAudioContext {
      constructor() {
        super()
        constructed.push(this)
      }
    }
    ;(window as unknown as { AudioContext: unknown }).AudioContext = TrackedAudioContext

    playEndingChimeSound()

    expect(constructed[0].createOscillator).toHaveBeenCalledTimes(3)
  })

  it('never throws when WebAudio is unsupported (no AudioContext at all)', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (window as any).AudioContext
    expect(() => playPageTurnSound()).not.toThrow()
    expect(() => playChoiceTapSound()).not.toThrow()
    expect(() => playEndingChimeSound()).not.toThrow()
  })

  it('never throws when the AudioContext constructor itself throws', () => {
    class ThrowingAudioContext {
      constructor() {
        throw new Error('blocked by a locked-down embedder')
      }
    }
    ;(window as unknown as { AudioContext: unknown }).AudioContext = ThrowingAudioContext
    expect(() => playPageTurnSound()).not.toThrow()
    // A construction failure latches "unavailable" so later calls do not
    // keep retrying (and do not throw either).
    expect(() => playChoiceTapSound()).not.toThrow()
  })

  it('resumes a suspended shared context on the next sound instead of creating a new one', () => {
    const constructed: MockAudioContext[] = []
    class TrackedAudioContext extends MockAudioContext {
      constructor() {
        super()
        this.state = 'suspended'
        constructed.push(this)
      }
    }
    ;(window as unknown as { AudioContext: unknown }).AudioContext = TrackedAudioContext

    playChoiceTapSound()
    playChoiceTapSound()

    expect(constructed).toHaveLength(1)
    expect(constructed[0].resume).toHaveBeenCalledTimes(2)
  })
})
