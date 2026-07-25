import { afterEach, describe, expect, it, vi } from 'vitest'
import { probeConnectivity } from './probeConnectivity'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('probeConnectivity', () => {
  it('returns true when the probe request resolves ok', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
    await expect(probeConnectivity('/health', 2000)).resolves.toBe(true)
  })

  it('returns false when the probe rejects (dead connection)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')))
    await expect(probeConnectivity('/health', 2000)).resolves.toBe(false)
  })

  it('assumes reachable when fetch is unavailable (no-fetch runtime)', async () => {
    vi.stubGlobal('fetch', undefined)
    await expect(probeConnectivity('/health', 2000)).resolves.toBe(true)
  })

  it('returns false when the probe aborts on timeout', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        (_url: string, init?: RequestInit) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () =>
              reject(new DOMException('aborted', 'AbortError'))
            )
          })
      )
    )
    await expect(probeConnectivity('/health', 10)).resolves.toBe(false)
  })
})
