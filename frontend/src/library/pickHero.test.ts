import { describe, expect, it } from 'vitest'
import type { LibraryItemView } from './libraryApi'
import { pickHero } from './pickHero'

function item(overrides: Partial<LibraryItemView>): LibraryItemView {
  return {
    id: 'x',
    title: 'X',
    version: 1,
    age_band: '6-8',
    tier: 1,
    reading_level_target: 2,
    node_count: 10,
    rating: null,
    progress: null,
    series_id: null,
    book_index: null,
    ...overrides,
  }
}

describe('pickHero', () => {
  it('returns null when no book has been started', () => {
    expect(pickHero([item({ id: 'a' }), item({ id: 'b' })])).toBeNull()
  })

  it('returns null for an empty list', () => {
    expect(pickHero([])).toBeNull()
  })

  it('picks the most recently active started book', () => {
    const older = item({
      id: 'a',
      progress: { current_node: 'n1', nodes_visited: 1, updated_at: '2026-06-20T10:00:00Z' },
    })
    const newer = item({
      id: 'b',
      progress: { current_node: 'n2', nodes_visited: 3, updated_at: '2026-07-01T10:00:00Z' },
    })
    expect(pickHero([older, newer])?.id).toBe('b')
  })

  it('breaks equal-timestamp ties deterministically by id', () => {
    const ts = '2026-07-01T10:00:00Z'
    const a = item({ id: 'a', progress: { current_node: 'n1', nodes_visited: 1, updated_at: ts } })
    const b = item({ id: 'b', progress: { current_node: 'n1', nodes_visited: 1, updated_at: ts } })
    expect(pickHero([b, a])?.id).toBe('a')
    expect(pickHero([a, b])?.id).toBe('a')
  })
})
