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
 * denylist, nor a path fragment further along move one into it. That same rule
 * is why every EXACT path below ends `(\/|\?|$)` rather than `(\/|$)`: the
 * string under test can be `/health?probe=1`, and `$` alone would not reach it.
 *
 * `frontend/nginx.conf`, not this file, is the authority on which origin paths
 * are not SPA routes; keep the two in step. Its `location` blocks currently
 * carve out `/api/`, `/health`, `/nginx-health`, `/sw.js`, and `/registerSW.js`.
 * Deliberately absent here: `/sw.js` and `/registerSW.js` are scripts, never
 * navigations, so the NavigationRoute cannot claim them; `/nginx-health` is a
 * container probe path that no browser navigates to.
 */
export const NAVIGATE_FALLBACK_DENYLIST: readonly RegExp[] = [
  // The same-origin proxy shape, which is what every deployed tier serves.
  /^\/api\//,
  // The bare shape a cross-origin backend serves. Same-origin it is only
  // reachable if the proxy is ever reconfigured, and no SPA route starts with
  // `/v1/`, so denying it now costs nothing and removes a repeat of this bug.
  /^\/v1\//,
  // `app.py` includes `health.router` TWICE, once under `/api/v1` and once with
  // no prefix, so the probe paths also sit at the origin root and match neither
  // pattern above. nginx answers `/health` with a deliberate 404 to "fail a
  // stale probe LOUDLY" (see the #CRITICAL note on that block); letting the
  // shell answer it instead returns index.html with a 200 and re-creates in the
  // browser the exact false-healthy signal that block exists to prevent.
  /^\/health(\/|\?|$)/,
  // FastAPI's own docs surfaces, unoverridden. nginx has no `location` for
  // these today, so they already fall through to the SPA and this changes
  // nothing in the deployed tiers; it stops them becoming the next `/health`
  // if the proxy ever routes them to the backend.
  /^\/docs(\/|\?|$)/,
  /^\/redoc(\/|\?|$)/,
  /^\/openapi\.json(\?|$)/,
]
