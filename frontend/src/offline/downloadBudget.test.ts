import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  OFFLINE_BUDGET_FULL_MESSAGE,
  checkDownloadBudget,
  consumeDownloadRefusal,
  estimateByteSize,
  forgetStoryRecency,
  pickEvictionCandidate,
  recordDownloadRefusal,
  recordStoryOpened,
} from './downloadBudget'

const MB = 1024 * 1024

/** Installs a mocked `navigator.storage.estimate()` returning `usage` bytes
 * (jsdom does not implement StorageManager, so there is nothing to restore
 * beyond deleting the property afterEach). */
function mockStorageEstimate(usage: number | null): void {
  if (usage === null) {
    Object.defineProperty(navigator, 'storage', { configurable: true, value: undefined })
    return
  }
  Object.defineProperty(navigator, 'storage', {
    configurable: true,
    value: { estimate: vi.fn().mockResolvedValue({ usage, quota: 1024 * MB }) },
  })
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  Object.defineProperty(navigator, 'storage', { configurable: true, value: undefined })
})

describe('estimateByteSize', () => {
  it('returns a positive size for a real payload', () => {
    expect(estimateByteSize({ id: 'story-1', nodes: [1, 2, 3] })).toBeGreaterThan(0)
  })

  it('returns 0 for a value that cannot be serialized (defensive, never throws)', () => {
    const circular: Record<string, unknown> = {}
    circular.self = circular
    expect(() => estimateByteSize(circular)).not.toThrow()
    expect(estimateByteSize(circular)).toBe(0)
  })
})

describe('pickEvictionCandidate', () => {
  it('returns null when there is nothing eligible', () => {
    expect(pickEvictionCandidate([], 'a')).toBeNull()
    expect(pickEvictionCandidate(['a'], 'a')).toBeNull()
  })

  it('excludes the story currently being downloaded', () => {
    recordStoryOpened('a')
    expect(pickEvictionCandidate(['a'], 'a')).toBeNull()
  })

  it('picks the least-recently-opened candidate', () => {
    recordStoryOpened('old')
    recordStoryOpened('newer')
    expect(pickEvictionCandidate(['old', 'newer'], 'current')).toBe('old')
  })

  it('treats a candidate with no recorded recency as the oldest', () => {
    recordStoryOpened('recently-opened')
    // 'never-opened' has no entry at all.
    expect(pickEvictionCandidate(['recently-opened', 'never-opened'], 'current')).toBe(
      'never-opened'
    )
  })

  it('forgetting a story\'s recency resets it to "no evidence of recent use"', () => {
    recordStoryOpened('a')
    recordStoryOpened('b')
    forgetStoryRecency('a')
    expect(pickEvictionCandidate(['a', 'b'], 'current')).toBe('a')
  })
})

describe('checkDownloadBudget', () => {
  it('fails open (allows, no eviction) when storage.estimate is unsupported', async () => {
    mockStorageEstimate(null)
    const result = await checkDownloadBudget('story-1', 10 * MB, ['other'])
    expect(result).toEqual({ allowed: true })
  })

  it('fails open but logs when storage.estimate() rejects', async () => {
    // The distinction the untested `catch` erased: a browser whose estimate()
    // throws produced byte-for-byte the same result as a browser sitting
    // comfortably under budget, so the entire D20 budget could be off with
    // nothing anywhere saying so. `db.ts` does log when checkDownloadBudget
    // throws, but the swallow here guarantees that log never fires. Failing
    // open is still correct; failing open in silence is not.
    Object.defineProperty(navigator, 'storage', {
      configurable: true,
      value: { estimate: vi.fn().mockRejectedValue(new Error('estimate boom')) },
    })
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const result = await checkDownloadBudget('story-1', 500 * MB, ['other'])

    // 500MB is past the HARD cap, so this is the case the budget would
    // otherwise refuse outright: proof that the null really does bypass every
    // band of the gate rather than just the soft one.
    expect(result).toEqual({ allowed: true })
    expect(warn).toHaveBeenCalledOnce()
    warn.mockRestore()
  })

  it('does not log when the estimate succeeds', async () => {
    // Pins the warn to the failure path only. Without it, hoisting the log
    // out of the catch leaves the test above green while every download on
    // every healthy browser writes a console warning.
    mockStorageEstimate(100 * MB)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    await checkDownloadBudget('story-1', 10 * MB, ['other'])

    expect(warn).not.toHaveBeenCalled()
    warn.mockRestore()
  })

  it('allows without eviction when projected usage stays under the 250MB soft cap', async () => {
    mockStorageEstimate(100 * MB)
    const result = await checkDownloadBudget('story-1', 10 * MB, ['other'])
    expect(result.allowed).toBe(true)
    expect(result.evictStoryId).toBeUndefined()
  })

  it('prefers evicting the oldest other book once projected usage crosses the 250MB soft cap', async () => {
    mockStorageEstimate(245 * MB)
    recordStoryOpened('old-book')
    recordStoryOpened('newer-book')
    const result = await checkDownloadBudget('story-1', 10 * MB, ['old-book', 'newer-book'])
    expect(result.allowed).toBe(true)
    expect(result.evictStoryId).toBe('old-book')
  })

  it('allows without eviction past the soft cap when there is nothing else cached', async () => {
    mockStorageEstimate(245 * MB)
    const result = await checkDownloadBudget('story-1', 10 * MB, [])
    expect(result.allowed).toBe(true)
    expect(result.evictStoryId).toBeUndefined()
  })

  it('evicts the oldest candidate as a best effort past the 500MB hard cap', async () => {
    mockStorageEstimate(495 * MB)
    recordStoryOpened('old-book')
    const result = await checkDownloadBudget('story-1', 10 * MB, ['old-book'])
    expect(result.allowed).toBe(true)
    expect(result.evictStoryId).toBe('old-book')
  })

  it('refuses the download past the 500MB hard cap with nothing left to evict', async () => {
    mockStorageEstimate(495 * MB)
    const result = await checkDownloadBudget('story-1', 10 * MB, [])
    expect(result.allowed).toBe(false)
    expect(result.evictStoryId).toBeUndefined()
  })

  it('refuses even with candidates present if they are all the story being downloaded', async () => {
    mockStorageEstimate(495 * MB)
    recordStoryOpened('story-1')
    const result = await checkDownloadBudget('story-1', 10 * MB, ['story-1'])
    expect(result.allowed).toBe(false)
  })
})

describe('download refusal flag', () => {
  it('consumeDownloadRefusal returns false when nothing is pending', () => {
    expect(consumeDownloadRefusal()).toBe(false)
  })

  it('round-trips a refusal exactly once (consume-once, like a toast)', () => {
    recordDownloadRefusal()
    expect(consumeDownloadRefusal()).toBe(true)
    expect(consumeDownloadRefusal()).toBe(false)
  })
})

describe('OFFLINE_BUDGET_FULL_MESSAGE', () => {
  it('is kid-readable and names the grown-up as the next step', () => {
    expect(OFFLINE_BUDGET_FULL_MESSAGE).toMatch(/grown-up/i)
  })
})
