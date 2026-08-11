import { describe, expect, it } from 'vitest'

import {
  ADMIN_CONSOLE_PATH,
  GUARDIAN_CONSENT_PATH,
  GUARDIAN_CONSOLE_PATH,
  GUARDIAN_LOGIN_PATH,
  KID_PICKER_PATH,
  PRIVACY_PATH,
  SUPPORT_PATH,
} from '../routes'
import { NAVIGATE_FALLBACK_DENYLIST } from './navigateFallbackDenylist'

/**
 * Workbox tests each denylist pattern against `url.pathname + url.search`
 * (workbox-routing/NavigationRoute.js), so the test feeds the patterns the
 * same string the service worker will.
 */
function isDenied(pathAndSearch: string): boolean {
  return NAVIGATE_FALLBACK_DENYLIST.some((pattern) => pattern.test(pathAndSearch))
}

describe('navigate-fallback denylist', () => {
  it('excludes the KWS return page exactly as KWS sends it', () => {
    // The real shape: three query parameters Epic appends to the registered
    // return URL. The query string is included because Workbox matches on
    // pathname AND search, so a pattern anchored only on a bare path would
    // pass a test written without one and still fail in a browser.
    const kwsReturn =
      '/api/v1/consent/kws/return?status=%7B%22verified%22%3Atrue%7D' +
      '&externalPayload=%7B%22v%22%3A1%7D&signature=9cfe4e8e'

    expect(isDenied(kwsReturn)).toBe(true)
    expect(isDenied('/api/v1/consent/kws/return')).toBe(true)
  })

  it('leaves every SPA route on the offline shell', () => {
    // The other half of the contract. A denylist that is too broad breaks
    // client-side routing offline, which is the whole reason the navigation
    // fallback exists, and it would do so silently for anyone already online.
    const spaRoutes = [
      '/',
      KID_PICKER_PATH,
      PRIVACY_PATH,
      SUPPORT_PATH,
      GUARDIAN_LOGIN_PATH,
      GUARDIAN_CONSENT_PATH,
      GUARDIAN_CONSOLE_PATH,
      ADMIN_CONSOLE_PATH,
      '/library/1f0c0c1e-0000-4000-8000-000000000001',
      '/read/1f0c0c1e-0000-4000-8000-000000000001/abc/3',
      '/guardian/login?intent=authorize-device',
    ]

    for (const route of spaRoutes) {
      expect(isDenied(route), `${route} must still get the app shell`).toBe(false)
    }
  })

  it('anchors at the path root rather than matching anywhere', () => {
    // A story slug or profile name containing "api" is a real possibility and
    // must not knock that navigation off the app shell.
    expect(isDenied('/read/api/v1')).toBe(false)
    expect(isDenied('/library/api-adventures')).toBe(false)
  })

  it('excludes every server-rendered path, not just the one that broke', () => {
    // One case per pattern, so a typo in any single entry fails a test rather
    // than waiting for a parent to report a 404. Without the bare `/v1/` case
    // that entry could be misspelled `/^\/v2\//` and every other test here
    // would still pass.
    const serverPaths = [
      '/api/v1/consent/kws/return',
      '/v1/consent/kws/return',
      // `app.py` mounts health at the origin root as well as under /api/v1.
      '/health',
      '/health/live',
      '/health/ready',
      '/health/startup',
      '/docs',
      '/docs/oauth2-redirect',
      '/redoc',
      '/openapi.json',
    ]

    for (const path of serverPaths) {
      expect(isDenied(path), `${path} must reach the server`).toBe(true)
    }
  })

  it('still excludes an exact path that arrives with a query string', () => {
    // Workbox matches on pathname AND search, so an exact-path pattern closed
    // with `$` alone would let `/health?probe=1` through: after `/health` the
    // next character is `?`, which is neither a slash nor the end of input.
    // This is the failure mode a bare-path test cannot see.
    expect(isDenied('/health?probe=1')).toBe(true)
    expect(isDenied('/openapi.json?version=3.1')).toBe(true)
    expect(isDenied('/docs?ref=email')).toBe(true)
  })

  it('leaves SPA-owned paths that merely start like a server path', () => {
    // The negative half of the exact-path patterns. A future route named for
    // reading habits or in-app help must not be knocked off the shell by the
    // `/health` or `/docs` entries.
    expect(isDenied('/healthy-reading-habits')).toBe(false)
    expect(isDenied('/documents')).toBe(false)
    expect(isDenied('/redocument')).toBe(false)
    expect(isDenied('/openapi.json.html')).toBe(false)
  })
})
