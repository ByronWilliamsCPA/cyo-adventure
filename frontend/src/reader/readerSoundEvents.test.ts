import { describe, expect, it, vi } from 'vitest'
import { emitReaderSoundEvent, onReaderSoundEvent } from './readerSoundEvents'

describe('readerSoundEvents (W4.2 module-level bus)', () => {
  it('calls every subscriber of an event when it is emitted', () => {
    const a = vi.fn()
    const b = vi.fn()
    const unsubA = onReaderSoundEvent('choice-tap', a)
    const unsubB = onReaderSoundEvent('choice-tap', b)
    emitReaderSoundEvent('choice-tap')
    expect(a).toHaveBeenCalledTimes(1)
    expect(b).toHaveBeenCalledTimes(1)
    unsubA()
    unsubB()
  })

  it('does not call a listener after it unsubscribes', () => {
    const listener = vi.fn()
    const unsubscribe = onReaderSoundEvent('page-turn', listener)
    unsubscribe()
    emitReaderSoundEvent('page-turn')
    expect(listener).not.toHaveBeenCalled()
  })

  it("keeps event names isolated: emitting one never calls a different event's listener", () => {
    const listener = vi.fn()
    const unsubscribe = onReaderSoundEvent('ending', listener)
    emitReaderSoundEvent('page-turn')
    emitReaderSoundEvent('choice-tap')
    expect(listener).not.toHaveBeenCalled()
    unsubscribe()
  })

  it('a throwing listener does not stop a sibling listener from running', () => {
    const throwing = vi.fn(() => {
      throw new Error('boom')
    })
    const sibling = vi.fn()
    const unsub1 = onReaderSoundEvent('ending', throwing)
    const unsub2 = onReaderSoundEvent('ending', sibling)
    expect(() => emitReaderSoundEvent('ending')).not.toThrow()
    expect(sibling).toHaveBeenCalledTimes(1)
    unsub1()
    unsub2()
  })
})
