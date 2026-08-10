/**
 * Paths the service worker must never answer with the SPA shell.
 *
 * Workbox's `generateSW` registers a NavigationRoute that serves the precached
 * `index.html` for EVERY top-level navigation on this origin, which is what
 * makes client-side routing survive a reload and work offline. The backend is
 * mounted on the same origin behind the reverse proxy, so without a denylist
 * that fallback also claims the few paths the SERVER renders as real HTML
 * pages, and the app's catch-all route paints its "we can't find that page"
 * over them.
 *
 * #CRITICAL: external-resources: the KWS verification return page
 * (`GET /api/v1/consent/kws/return`, ADR-018 D1) is server-rendered HTML that
 * a parent reaches by clicking a link in Epic's email. Any browser that has
 * opened this app once carries this service worker, so the parent who
 * completes verification is precisely the visitor whose navigation gets
 * intercepted: verification succeeds at Epic and the parent is shown a 404.
 * Observed on staging on 2026-08-10. curl, Postman, and CI never reproduce
 * it, because none of them run a service worker, so the route looks healthy
 * from every vantage point except the only one that matters.
 * #VERIFY: navigateFallbackDenylist.test.ts checks these patterns against the
 * server-rendered paths and against the real SPA routes.
 *
 * Only prefixes the backend owns belong here. Workbox matches each pattern
 * against `url.pathname + url.search` (workbox-routing/NavigationRoute.js), so
 * `^` anchors at the path root and no query string can move a path out of the
 * denylist, nor a path fragment further along move one into it.
 */
export const NAVIGATE_FALLBACK_DENYLIST: readonly RegExp[] = [
  // The same-origin proxy shape, which is what every deployed tier serves.
  /^\/api\//,
  // The bare shape a cross-origin backend serves. Same-origin it is only
  // reachable if the proxy is ever reconfigured, and no SPA route starts with
  // `/v1/`, so denying it now costs nothing and removes a repeat of this bug.
  /^\/v1\//,
]
