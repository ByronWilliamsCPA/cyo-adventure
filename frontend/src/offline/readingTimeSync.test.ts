import 'fake-indexeddb/auto'

import { IDBFactory } from 'fake-indexeddb'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { _resetDbHandle, getReadingTimeBucket, putReadingTimeBucket } from './db'
import {
  accrueReadingTime,
  flushAllReadingTime,
  flushReadingTimeBucket,
  type ReadingTimeApi,
} from './readingTimeSync'
import { OfflineError } from './sync'

const PROFILE_ID = 'profile-1'
const DATE = '2026-01-01'

function makeApi(impl: ReadingTimeApi['flush']): ReadingTimeApi {
  return { flush: impl }
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('accrueReadingTime', () => {
  it('creates a bucket on first accrual', async () => {
    await accrueReadingTime(PROFILE_ID, DATE, 30)
    const bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    expect(bucket).toEqual({
      profileId: PROFILE_ID,
      date: DATE,
      seconds: 30,
      syncedSeconds: 0,
      pending: null,
    })
  })

  it('adds to an existing bucket rather than overwriting it', async () => {
    await accrueReadingTime(PROFILE_ID, DATE, 30)
    await accrueReadingTime(PROFILE_ID, DATE, 15)
    const bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    expect(bucket?.seconds).toBe(45)
  })

  it('is a no-op for zero or negative seconds', async () => {
    await accrueReadingTime(PROFILE_ID, DATE, 0)
    await accrueReadingTime(PROFILE_ID, DATE, -5)
    const bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    expect(bucket).toBeUndefined()
  })

  it('accrual during a pending flush is not lost (grows seconds, never touches pending)', async () => {
    await putReadingTimeBucket({
      profileId: PROFILE_ID,
      date: DATE,
      seconds: 100,
      syncedSeconds: 40,
      pending: { flushId: 'f1', deltaSeconds: 60, snapshotSeconds: 100 },
    })
    await accrueReadingTime(PROFILE_ID, DATE, 10)
    const bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    expect(bucket?.seconds).toBe(110)
    expect(bucket?.pending).toEqual({ flushId: 'f1', deltaSeconds: 60, snapshotSeconds: 100 })
  })
})

describe('flushReadingTimeBucket', () => {
  it('is a no-op when nothing is unsynced', async () => {
    const flush = vi.fn()
    await flushReadingTimeBucket(makeApi(flush), {
      profileId: PROFILE_ID,
      date: DATE,
      seconds: 30,
      syncedSeconds: 30,
      pending: null,
    })
    expect(flush).not.toHaveBeenCalled()
  })

  it('mints a flush_id and delta from unsynced seconds, then advances syncedSeconds on success', async () => {
    const flush = vi
      .fn()
      .mockResolvedValue({ activity_date: DATE, active_seconds: 30, updated_at: 't' })
    await accrueReadingTime(PROFILE_ID, DATE, 30)
    const bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    await flushReadingTimeBucket(makeApi(flush), bucket!, { newId: () => 'flush-1' })
    expect(flush).toHaveBeenCalledWith(DATE, 30, 'flush-1', undefined)
    const after = await getReadingTimeBucket(PROFILE_ID, DATE)
    expect(after).toEqual({
      profileId: PROFILE_ID,
      date: DATE,
      seconds: 30,
      syncedSeconds: 30,
      pending: null,
    })
  })

  it('a pending attempt survives across separate flush calls with the same flush_id and delta', async () => {
    const flush = vi.fn().mockRejectedValue(new OfflineError())
    await accrueReadingTime(PROFILE_ID, DATE, 20)
    let bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    await flushReadingTimeBucket(makeApi(flush), bucket!, { newId: () => 'flush-a' })
    bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    expect(bucket?.pending).toEqual({ flushId: 'flush-a', deltaSeconds: 20, snapshotSeconds: 20 })

    // More seconds accrue while the flush is still pending -- must NOT be
    // folded into the pending attempt's frozen delta.
    await accrueReadingTime(PROFILE_ID, DATE, 5)
    bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    expect(bucket?.seconds).toBe(25)
    expect(bucket?.pending?.deltaSeconds).toBe(20)

    // Retry: same flush_id and delta resent verbatim, even though seconds
    // have since grown to 25.
    await flushReadingTimeBucket(makeApi(flush), bucket!, { newId: () => 'flush-b' })
    expect(flush).toHaveBeenLastCalledWith(DATE, 20, 'flush-a', undefined)
  })

  it('a non-offline failure drops pending and the next flush recomputes from the unadvanced synced baseline', async () => {
    const flush = vi.fn().mockRejectedValueOnce(new Error('server error'))
    await accrueReadingTime(PROFILE_ID, DATE, 20)
    let bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    await flushReadingTimeBucket(makeApi(flush), bucket!, { newId: () => 'flush-a' })
    bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    expect(bucket?.pending).toBeNull()
    expect(bucket?.syncedSeconds).toBe(0)

    // More seconds accrue, then a fresh flush attempt covers everything
    // (the failed range plus the new growth) under a new flush_id.
    await accrueReadingTime(PROFILE_ID, DATE, 5)
    bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    const flushOk = vi
      .fn()
      .mockResolvedValue({ activity_date: DATE, active_seconds: 25, updated_at: 't' })
    await flushReadingTimeBucket(makeApi(flushOk), bucket!, { newId: () => 'flush-c' })
    expect(flushOk).toHaveBeenCalledWith(DATE, 25, 'flush-c', undefined)
  })

  it('forwards deviceId when provided', async () => {
    const flush = vi
      .fn()
      .mockResolvedValue({ activity_date: DATE, active_seconds: 10, updated_at: 't' })
    await accrueReadingTime(PROFILE_ID, DATE, 10)
    const bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    await flushReadingTimeBucket(makeApi(flush), bucket!, {
      newId: () => 'flush-x',
      deviceId: 'device-1',
    })
    expect(flush).toHaveBeenCalledWith(DATE, 10, 'flush-x', 'device-1')
  })
})

describe('flushAllReadingTime', () => {
  it('flushes every unsynced bucket for the profile and skips fully-synced ones', async () => {
    await accrueReadingTime(PROFILE_ID, '2026-01-01', 10)
    await accrueReadingTime(PROFILE_ID, '2026-01-02', 20)
    await putReadingTimeBucket({
      profileId: PROFILE_ID,
      date: '2026-01-03',
      seconds: 5,
      syncedSeconds: 5,
      pending: null,
    })
    const flush = vi
      .fn()
      .mockResolvedValue({ activity_date: '2026-01-01', active_seconds: 0, updated_at: 't' })
    await flushAllReadingTime(makeApi(flush), PROFILE_ID)
    expect(flush).toHaveBeenCalledTimes(2)
    const dates: string[] = flush.mock.calls.map((call: unknown[]) => call[0] as string)
    expect(dates.sort()).toEqual(['2026-01-01', '2026-01-02'])
  })

  it("never touches a different profile's buckets", async () => {
    await accrueReadingTime('other-profile', DATE, 30)
    const flush = vi.fn()
    await flushAllReadingTime(makeApi(flush), PROFILE_ID)
    expect(flush).not.toHaveBeenCalled()
  })
})
