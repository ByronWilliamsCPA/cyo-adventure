import 'fake-indexeddb/auto'

import type { AxiosInstance } from 'axios'
import { IDBFactory } from 'fake-indexeddb'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { _resetDbHandle, getReadingTimeBucket, putReadingTimeBucket } from './db'
import {
  accrueReadingTime,
  flushAllReadingTime,
  flushReadingTimeBucket,
  makeReadingTimeApi,
  type ReadingTimeApi,
  RetryableFlushError,
} from './readingTimeSync'
import { OfflineError } from './sync'

const PROFILE_ID = 'profile-1'
const DATE = '2026-01-01'

/**
 * `failFor.date` makes that bucket's IndexedDB write fail, simulating a
 * local-storage failure. Declared via vi.hoisted because vi.mock factories are
 * hoisted above ordinary module-scope declarations. Only the reading-time put
 * is wrapped; every other export of './db' passes straight through to the real
 * fake-indexeddb-backed implementation the rest of this file relies on.
 */
const failFor = vi.hoisted(() => ({ date: null as string | null }))

vi.mock('./db', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./db')>()
  return {
    ...actual,
    putReadingTimeBucket: async (bucket: Parameters<typeof actual.putReadingTimeBucket>[0]) => {
      if (failFor.date !== null && bucket.date === failFor.date) {
        throw new TypeError('IndexedDB is unavailable')
      }
      return actual.putReadingTimeBucket(bucket)
    },
  }
})

function makeApi(impl: ReadingTimeApi['flush']): ReadingTimeApi {
  return { flush: impl }
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory()
  _resetDbHandle()
  failFor.date = null
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

  it('a clamped flush leaves the unsettled remainder to be retried', async () => {
    // The server clamps a delta to a plausibility ceiling. Marking the whole
    // delta synced would delete the clamped seconds outright, because
    // accrueReadingTime only ever grows `seconds` and nothing re-sends them.
    const flush = vi.fn().mockResolvedValue({
      activity_date: DATE,
      active_seconds: 120,
      updated_at: 't',
      settled_seconds: 120,
    })
    await accrueReadingTime(PROFILE_ID, DATE, 1800)
    const bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    await flushReadingTimeBucket(makeApi(flush), bucket!, { newId: () => 'flush-1' })

    const after = await getReadingTimeBucket(PROFILE_ID, DATE)
    expect(after?.syncedSeconds).toBe(120)
    expect(after?.seconds).toBe(1800)
    expect(after?.pending).toBeNull()

    // The next flush picks the remainder back up rather than dropping it.
    const retry = vi.fn().mockResolvedValue({
      activity_date: DATE,
      active_seconds: 1800,
      updated_at: 't',
      settled_seconds: 1680,
    })
    await flushReadingTimeBucket(makeApi(retry), after!, { newId: () => 'flush-2' })
    expect(retry).toHaveBeenCalledWith(DATE, 1680, 'flush-2', undefined)
    expect((await getReadingTimeBucket(PROFILE_ID, DATE))?.syncedSeconds).toBe(1800)
  })

  it('never advances the baseline past a nonsense settled_seconds', async () => {
    const flush = vi.fn().mockResolvedValue({
      activity_date: DATE,
      active_seconds: 30,
      updated_at: 't',
      settled_seconds: 999_999,
    })
    await accrueReadingTime(PROFILE_ID, DATE, 30)
    const bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    await flushReadingTimeBucket(makeApi(flush), bucket!, { newId: () => 'flush-1' })
    expect((await getReadingTimeBucket(PROFILE_ID, DATE))?.syncedSeconds).toBe(30)
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

  it('a 5xx keeps the attempt pending for a verbatim retry', async () => {
    // A gateway timeout may have committed server-side. Dropping `pending`
    // would mint a NEW flush_id for the same seconds, which the server's
    // single-slot dedupe cannot catch, double-counting the range.
    const flush = vi.fn().mockRejectedValue(new RetryableFlushError(504))
    await accrueReadingTime(PROFILE_ID, DATE, 20)
    let bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    await flushReadingTimeBucket(makeApi(flush), bucket!, { newId: () => 'flush-a' })

    bucket = await getReadingTimeBucket(PROFILE_ID, DATE)
    expect(bucket?.pending).toEqual({
      flushId: 'flush-a',
      deltaSeconds: 20,
      snapshotSeconds: 20,
    })
    expect(bucket?.syncedSeconds).toBe(0)

    await flushReadingTimeBucket(makeApi(flush), bucket!, { newId: () => 'flush-b' })
    expect(flush).toHaveBeenLastCalledWith(DATE, 20, 'flush-a', undefined)
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

describe('makeReadingTimeApi', () => {
  // Real axios rejections are `AxiosError` instances (an `Error` subclass), so
  // these doubles build a real `Error` carrying the shape axios attaches
  // (`isAxiosError`, `response`), mirroring api/readerApi.test.ts.
  function mockAxiosError(props: Record<string, unknown>): Error {
    return Object.assign(new Error('mock axios error'), props)
  }

  function axiosPostReject(error: Error): AxiosInstance {
    return { post: () => Promise.reject(error) } as unknown as AxiosInstance
  }

  it('posts the flush body and returns the response data', async () => {
    const post = vi.fn(() =>
      Promise.resolve({ data: { activity_date: DATE, active_seconds: 30, updated_at: 't' } })
    )
    const api = makeReadingTimeApi({ post } as unknown as AxiosInstance)
    const result = await api.flush(DATE, 30, 'flush-1', 'device-1')
    expect(post).toHaveBeenCalledWith('/v1/me/reading-time', {
      date: DATE,
      seconds_delta: 30,
      flush_id: 'flush-1',
      device_id: 'device-1',
    })
    expect(result.active_seconds).toBe(30)
  })

  it('maps a transport failure (no HTTP response) to OfflineError', async () => {
    const api = makeReadingTimeApi(
      axiosPostReject(mockAxiosError({ isAxiosError: true, response: undefined }))
    )
    await expect(api.flush(DATE, 30, 'flush-1')).rejects.toBeInstanceOf(OfflineError)
  })

  it('maps a 5xx to RetryableFlushError carrying the status', async () => {
    const api = makeReadingTimeApi(
      axiosPostReject(mockAxiosError({ isAxiosError: true, response: { status: 503 } }))
    )
    await expect(api.flush(DATE, 30, 'flush-1')).rejects.toMatchObject({
      name: 'RetryableFlushError',
      status: 503,
    })
  })

  it('maps a 429 to RetryableFlushError', async () => {
    const api = makeReadingTimeApi(
      axiosPostReject(mockAxiosError({ isAxiosError: true, response: { status: 429 } }))
    )
    await expect(api.flush(DATE, 30, 'flush-1')).rejects.toBeInstanceOf(RetryableFlushError)
  })

  it('rethrows a 4xx as itself so the caller drops the attempt', async () => {
    const error = mockAxiosError({ isAxiosError: true, response: { status: 422 } })
    const api = makeReadingTimeApi(axiosPostReject(error))
    await expect(api.flush(DATE, 30, 'flush-1')).rejects.toBe(error)
  })

  it('rethrows a non-axios error untouched', async () => {
    const error = new TypeError('serializer exploded')
    const api = makeReadingTimeApi(axiosPostReject(error))
    await expect(api.flush(DATE, 30, 'flush-1')).rejects.toBe(error)
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

  it("one bucket's local-write failure does not strand the remaining days", async () => {
    // flushReadingTimeBucket writes `pending` to IndexedDB BEFORE its try
    // block, so a local write failure escapes the function entirely. The
    // documented "one bucket's failure never stops the others" contract has to
    // hold anyway, which means flushAllReadingTime must contain it.
    await accrueReadingTime(PROFILE_ID, '2026-01-01', 10)
    await accrueReadingTime(PROFILE_ID, '2026-01-02', 20)
    await accrueReadingTime(PROFILE_ID, '2026-01-03', 30)
    vi.spyOn(console, 'error').mockImplementation(() => {})
    failFor.date = '2026-01-01'

    const flush = vi.fn((date: string) =>
      Promise.resolve({ activity_date: date, active_seconds: 0, updated_at: 't' })
    )
    await flushAllReadingTime(makeApi(flush), PROFILE_ID)

    // The failing day never reached the network, but both later days did.
    const dates: string[] = flush.mock.calls.map((call: unknown[]) => call[0] as string)
    expect(dates.sort()).toEqual(['2026-01-02', '2026-01-03'])
  })

  it("never touches a different profile's buckets", async () => {
    await accrueReadingTime('other-profile', DATE, 30)
    const flush = vi.fn()
    await flushAllReadingTime(makeApi(flush), PROFILE_ID)
    expect(flush).not.toHaveBeenCalled()
  })
})
