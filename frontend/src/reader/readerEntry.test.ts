import { describe, expect, it } from 'vitest'

import { choose, start } from '../player/engine'
import { runStory } from '../test/runStory'
import { isOpeningRead, parseShelfState } from './readerEntry'

describe('parseShelfState', () => {
  it('reads the shelf handed over by BookCard', () => {
    expect(
      parseShelfState({ shelf: { coverUrl: 'https://covers.example/a.webp', rating: 4 } })
    ).toEqual({ coverUrl: 'https://covers.example/a.webp', rating: 4 })
  })

  it('returns null without a shelf key (deep link, reload, series hand-off)', () => {
    expect(parseShelfState(null)).toBeNull()
    expect(parseShelfState({ personalizationEligible: true })).toBeNull()
  })

  it('rejects a malformed shelf state field by field', () => {
    expect(parseShelfState({ shelf: { coverUrl: 7, rating: 'five' } })).toEqual({
      coverUrl: null,
      rating: null,
    })
    expect(parseShelfState({ shelf: { coverUrl: null, rating: 9 } })).toEqual({
      coverUrl: null,
      rating: null,
    })
    expect(parseShelfState({ shelf: 'x' })).toBeNull()
  })

  it('rejects a non-http cover URL', () => {
    for (const coverUrl of ['javascript:alert(1)', 'data:image/png;base64,AAAA', '/local.png']) {
      expect(parseShelfState({ shelf: { coverUrl, rating: null } })?.coverUrl).toBeNull()
    }
  })
})

describe('isOpeningRead', () => {
  it('is true with no saved state or one still on the first page', () => {
    expect(isOpeningRead(runStory, undefined, false)).toBe(true)
    expect(isOpeningRead(runStory, start(runStory), false)).toBe(true)
  })

  it('is false once a page band has tapped past page one', () => {
    expect(isOpeningRead(runStory, choose(runStory, start(runStory), 'c_go'), false)).toBe(false)
  })

  it('at a flowed band, counts the untouched opening stop as the opening', () => {
    const atFork = choose(runStory, start(runStory), 'c_go')
    expect(isOpeningRead(runStory, atFork, true)).toBe(true)
    const pastFork = choose(runStory, atFork, 'c_left')
    expect(isOpeningRead(runStory, pastFork, true)).toBe(false)
  })
})
