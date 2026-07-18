import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useReadAloud } from './useReadAloud'

// A minimal stand-in for SpeechSynthesisUtterance: real browsers fire onend
// asynchronously once audio playback finishes, but the hook only cares that
// onend/onerror get called eventually, so tests trigger them directly.
class MockUtterance {
  text: string
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(text: string) {
    this.text = text
  }
}

const speakMock = vi.fn()
const cancelMock = vi.fn()

function installSpeechSynthesis() {
  vi.stubGlobal('speechSynthesis', { speak: speakMock, cancel: cancelMock })
  vi.stubGlobal('SpeechSynthesisUtterance', MockUtterance)
}

beforeEach(() => {
  speakMock.mockReset()
  cancelMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useReadAloud', () => {
  it('is unavailable when the browser has no speechSynthesis', () => {
    // Deliberately do not install the stub.
    const { result } = renderHook(() => useReadAloud(true))
    expect(result.current.available).toBe(false)
  })

  it('is unavailable when enabled is false, even with speechSynthesis present', () => {
    installSpeechSynthesis()
    const { result } = renderHook(() => useReadAloud(false))
    expect(result.current.available).toBe(false)
  })

  it('is available when enabled and speechSynthesis is present', () => {
    installSpeechSynthesis()
    const { result } = renderHook(() => useReadAloud(true))
    expect(result.current.available).toBe(true)
    expect(result.current.speaking).toBe(false)
  })

  it('speaks the passage body then the choices, in order, and reports speaking', () => {
    installSpeechSynthesis()
    const { result } = renderHook(() => useReadAloud(true))

    act(() => {
      result.current.speak('Once upon a time.', ['Go north', 'Go south'])
    })

    expect(result.current.speaking).toBe(true)
    expect(cancelMock).toHaveBeenCalled()
    expect(speakMock).toHaveBeenCalledTimes(1)
    const bodyUtterance = speakMock.mock.calls[0][0] as MockUtterance
    expect(bodyUtterance.text).toBe('Once upon a time.')

    // Simulate the body finishing: the hook should queue the choices next.
    act(() => {
      bodyUtterance.onend?.()
    })
    expect(speakMock).toHaveBeenCalledTimes(2)
    const choicesUtterance = speakMock.mock.calls[1][0] as MockUtterance
    expect(choicesUtterance.text).toBe('Your choices are: Go north, Go south')
    expect(result.current.speaking).toBe(true)

    // Simulate the choices utterance finishing: speaking clears.
    act(() => {
      choicesUtterance.onend?.()
    })
    expect(result.current.speaking).toBe(false)
  })

  it('speaks only the passage body when there are no visible choices', () => {
    installSpeechSynthesis()
    const { result } = renderHook(() => useReadAloud(true))

    act(() => {
      result.current.speak('The end.', [])
    })

    expect(speakMock).toHaveBeenCalledTimes(1)
    const bodyUtterance = speakMock.mock.calls[0][0] as MockUtterance
    expect(bodyUtterance.text).toBe('The end.')

    act(() => {
      bodyUtterance.onend?.()
    })
    expect(result.current.speaking).toBe(false)
  })

  it('stop() cancels in-flight speech and clears speaking', () => {
    installSpeechSynthesis()
    const { result } = renderHook(() => useReadAloud(true))

    act(() => {
      result.current.speak('Once upon a time.', [])
    })
    expect(result.current.speaking).toBe(true)

    act(() => {
      result.current.stop()
    })
    expect(cancelMock).toHaveBeenCalledTimes(2) // once from speak's own cancel, once from stop
    expect(result.current.speaking).toBe(false)
  })

  it('cancels speech on unmount', () => {
    installSpeechSynthesis()
    const { result, unmount } = renderHook(() => useReadAloud(true))

    act(() => {
      result.current.speak('Once upon a time.', [])
    })
    cancelMock.mockClear()

    unmount()
    expect(cancelMock).toHaveBeenCalledTimes(1)
  })

  it('speak() is a no-op when not available', () => {
    // No speechSynthesis installed, so available stays false.
    const { result } = renderHook(() => useReadAloud(true))
    act(() => {
      result.current.speak('Once upon a time.', [])
    })
    expect(speakMock).not.toHaveBeenCalled()
    expect(result.current.speaking).toBe(false)
  })

  it('kid-safe failure: a throw from speak() hides the toggle instead of surfacing an error', () => {
    vi.stubGlobal('speechSynthesis', {
      speak: speakMock,
      cancel: () => {
        throw new Error('boom')
      },
    })
    vi.stubGlobal('SpeechSynthesisUtterance', MockUtterance)
    const { result } = renderHook(() => useReadAloud(true))
    expect(result.current.available).toBe(true)

    act(() => {
      result.current.speak('Once upon a time.', [])
    })

    expect(result.current.available).toBe(false)
    expect(result.current.speaking).toBe(false)
  })
})
