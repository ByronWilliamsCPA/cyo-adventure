/**
 * Actively confirm reachability. navigator.onLine only reflects the link layer,
 * so it reports "online" behind captive portals and on dead mobile data. This
 * fires a short-timeout, no-body GET; any non-error response (even a 4xx) proves
 * the round trip completed, so the connection is real.
 */
export async function probeConnectivity(url: string, timeoutMs: number): Promise<boolean> {
  if (typeof fetch === 'undefined') return true
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    await fetch(url, {
      method: 'GET',
      cache: 'no-store',
      signal: controller.signal,
    })
    return true
  } catch {
    // Any rejection (network error, CORS failure, abort/timeout) means we could
    // not complete a round trip: treat as offline.
    return false
  } finally {
    clearTimeout(timer)
  }
}
