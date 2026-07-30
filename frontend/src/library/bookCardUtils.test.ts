import { describe, expect, it } from 'vitest'
import type { LibraryItemView } from './libraryApi'
import { isRecentlyPublished, NEW_BADGE_WINDOW_MS } from './bookCardUtils'

const NOW = new Date('2026-07-28T12:00:00Z')

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
    cover_url: null,
    published_at: null,
    ...overrides,
  }
}

describe('isRecentlyPublished', () => {
  it('is false when published_at is null', () => {
    expect(isRecentlyPublished(item({ published_at: null }), NOW)).toBe(false)
  })

  it('is false when published_at is absent (offline-cached item predating the field)', () => {
    const full = item({})
    const withoutField: LibraryItemView = {
      id: full.id,
      title: full.title,
      version: full.version,
      age_band: full.age_band,
      tier: full.tier,
      reading_level_target: full.reading_level_target,
      node_count: full.node_count,
      rating: full.rating,
      progress: full.progress,
      series_id: full.series_id,
      book_index: full.book_index,
      cover_url: full.cover_url,
      // published_at intentionally omitted (optional field).
    }
    expect(isRecentlyPublished(withoutField, NOW)).toBe(false)
  })

  it('is true for a book published moments ago', () => {
    expect(isRecentlyPublished(item({ published_at: '2026-07-28T11:00:00Z' }), NOW)).toBe(true)
  })

  it('is true right at the edge of the window', () => {
    const edge = new Date(NOW.getTime() - NEW_BADGE_WINDOW_MS).toISOString()
    expect(isRecentlyPublished(item({ published_at: edge }), NOW)).toBe(true)
  })

  it('is false just past the window', () => {
    const pastEdge = new Date(NOW.getTime() - NEW_BADGE_WINDOW_MS - 1000).toISOString()
    expect(isRecentlyPublished(item({ published_at: pastEdge }), NOW)).toBe(false)
  })

  it('is false for a book published long ago', () => {
    expect(isRecentlyPublished(item({ published_at: '2026-01-01T00:00:00Z' }), NOW)).toBe(false)
  })

  it('is false for a malformed timestamp', () => {
    expect(isRecentlyPublished(item({ published_at: 'not-a-date' }), NOW)).toBe(false)
  })

  it('is false for a future timestamp (clock skew defense)', () => {
    expect(isRecentlyPublished(item({ published_at: '2026-08-01T00:00:00Z' }), NOW)).toBe(false)
  })
})
