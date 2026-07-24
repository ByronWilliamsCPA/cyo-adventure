import { useEffect, useState } from 'react'

import { probeConnectivity } from './probeConnectivity'

// Probes the app's own PWA icon: a tiny, always-present, same-origin asset that
// never needs auth and is cache-bustable, so it exercises a real round trip
// without depending on the API's CORS/auth posture.
const PROBE_URL = '/pwa-icon-192.png'
const PROBE_TIMEOUT_MS = 3000

/**
 * True while the device has real connectivity. navigator.onLine === false is
 * trusted immediately (authoritative offline); a reported-online state is
 * confirmed with an active probe, so captive portals and dead mobile data do
 * not read as online.
 */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState<boolean>(() =>
    typeof navigator === 'undefined' ? true : navigator.onLine
  )

  useEffect(() => {
    let cancelled = false
    const refresh = async () => {
      if (typeof navigator !== 'undefined' && !navigator.onLine) {
        if (!cancelled) setOnline(false)
        return
      }
      const reachable = await probeConnectivity(`${PROBE_URL}?t=${Date.now()}`, PROBE_TIMEOUT_MS)
      if (!cancelled) setOnline(reachable)
    }
    const handler = () => void refresh()
    void refresh()
    window.addEventListener('online', handler)
    window.addEventListener('offline', handler)
    return () => {
      cancelled = true
      window.removeEventListener('online', handler)
      window.removeEventListener('offline', handler)
    }
  }, [])

  return online
}
