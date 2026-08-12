import type { Page, Response } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { PRIVACY_PATH, SUPPORT_PATH } from '../src/routes'
import { assertPositiveAttempts, backoffDelayMs, paceNavigation } from '../e2e-support/rate-limit'

/**
 * Closes the coverage-matrix gap under "Public: privacy policy and support
 * (signed-out)" and "Guardian: KWS parent verification (ADR-018 D1)": no test
 * asserted that the URLs registered with Epic's Kids Web Services actually
 * resolve over HTTP for a signed-out client against a deployed environment.
 * That is the exact blind spot PR #679 fixed a real bug in: the service
 * worker's navigation fallback answered every navigation on this origin with
 * the cached SPA shell, so `GET /api/v1/consent/kws/return`
 * (`src/cyo_adventure/api/kws_redirect.py`), a page the backend renders as
 * real HTML, came back in every browser that had ever opened the app once as
 * the SPA's own client-side not-found page: an HTTP 200 carrying "we can't
 * find that page", never an HTTP 404. curl, Postman, and every prior CI tier
 * (none of which run a service worker) saw the backend's real answer instead,
 * which is why nothing caught it. `frontend/src/pwa/navigateFallbackDenylist.ts`
 * is the fix; this spec is what proves the fix holds against a real deployed
 * origin rather than only against the denylist's own regex unit test
 * (`navigateFallbackDenylist.test.ts`, which never loads a real service
 * worker).
 *
 * HARD SAFETY CONSTRAINT: this spec must never trigger a real KWS
 * verification send.
 *
 * #CRITICAL: security: `POST /api/v1/consent/kws/start` discloses a real
 * adult's email address to Epic Games with no DPA in place (register row
 * O-125), and that is a standing block on production sends. Every request
 * below is a plain, unauthenticated GET; the KWS redirect-return leg is hit
 * with no `signature` query parameter, which the backend genuinely refuses
 * (`api/kws_redirect.py`, a real backend answer this spec depends on) rather
 * than accepts, and every refusal branch there is display-only and writes
 * nothing to `kws_verification` (see that module's docstring).
 * #VERIFY: never add a `signature` parameter to any URL in this file, and
 * never call `/api/v1/consent/kws/start` from it.
 * `tests/unit/test_kws_redirect.py::TestNoPersistence` is the in-repo proof
 * that the route this spec drives cannot write consent state at all.
 *
 * #ASSUME: external-resources: every assertion below describes a
 * separately-deployed staging origin (a frontend image homelab-infra builds
 * and ships on its own cadence, plus the backend behind the same proxy), not
 * this repo's source tree. A failure shortly after a denylist change means
 * "staging has not been redeployed yet" at least as often as it means "the
 * fix regressed".
 * #VERIFY: check the deployed image tag before weakening anything here.
 * `uv run python scripts/kws_probe_endpoints.py --origin <origin>` answers
 * the same question from outside a browser and is the faster first check.
 *
 * Why every URL is requested twice, and what that is NOT: it is not "before
 * and after service worker control". The first test in this serial block
 * navigates to `/` and waits for the registration to report `active`, so
 * every navigation after it, including the one each loop below labels its
 * "first" visit, is already made against an active worker. No uncontrolled
 * state survives that point, so there is nothing "before" left to exercise.
 * What the second request actually buys is determinism across two
 * already-controlled requests: Workbox resolves a navigation by first-match
 * over its registered routes, and one sample cannot separate "the denylist
 * holds" from "this one request happened to miss the NavigationRoute".
 */

const KWS_RETURN_PATH = '/api/v1/consent/kws/return'

/**
 * `page.goto` that respects this tier's shared navigation-pacing floor
 * (`paceNavigation`, `e2e-support/rate-limit.ts`: every deployed environment,
 * staging included, enforces a 60 rpm/IP limit) and returns the real
 * `Response` object. Deliberately not `gotoResilient`: that helper judges a
 * rate limit by polling the rendered DOM for an advisory alert and returns
 * `void`, but this spec's whole point is asserting the network-level status
 * code Playwright observed, so the response has to survive the call. A 429
 * is retried with the same backoff `gotoResilient` uses; any other status is
 * returned as-is for the caller to assert on, including a 4xx or 5xx, which
 * must reach the test rather than being treated as a retry condition.
 *
 * Keeps `gotoResilient`'s `assertPositiveAttempts` guard rather than dropping
 * it along with the rest: without it a `maxAttempts` of 0 skips the loop body
 * entirely and falls straight through to the throw below, which blames "the
 * helper exhausted its attempts" for a call that never navigated once.
 */
async function gotoAndCapture(page: Page, path: string, maxAttempts = 3): Promise<Response> {
  assertPositiveAttempts(maxAttempts, 'gotoAndCapture')
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    await paceNavigation(page)
    const response = await page.goto(path)
    if (!response) {
      throw new Error(
        `${path} produced no response object; the navigation may have been ` +
          'intercepted before it reached the network.'
      )
    }
    if (response.status() !== 429) return response
    if (attempt === maxAttempts) {
      throw new Error(`${path} was still rate-limited (429) after ${maxAttempts} attempts.`)
    }
    await page.waitForTimeout(backoffDelayMs(attempt))
  }
  // Unreachable: maxAttempts is always >= 1, so the loop above either returns
  // or throws. Only here to satisfy the return type.
  throw new Error(`${path}: gotoAndCapture exhausted its attempts without returning or throwing`)
}

/**
 * Waits until this origin's service worker registration reports an `active`
 * worker, polled from the page rather than asserted once. Deliberately not a
 * wait for `navigator.serviceWorker.controller`: `vite.config.ts`'s VitePWA
 * config sets no `clientsClaim`, so the very tab that registers the worker is
 * never guaranteed to become its own controller, and a wait keyed on that
 * would hang for a reason unrelated to what this spec checks. A NEW
 * navigation request, which is what every `gotoAndCapture` call below makes,
 * is matched against the registration's active worker regardless of
 * `clientsClaim`; `active` is therefore the precise condition this spec's
 * "service worker installed" language depends on.
 */
async function waitForServiceWorkerActive(page: Page, timeout = 20_000): Promise<void> {
  await page.waitForFunction(
    async () => {
      if (!('serviceWorker' in navigator)) return false
      const registration = await navigator.serviceWorker.getRegistration()
      return registration?.active != null
    },
    undefined,
    { timeout }
  )
}

test.describe('KWS-registered public URLs resolve for a signed-out client', () => {
  test.describe.configure({ mode: 'serial' })

  let sharedPage: Page

  test.beforeAll(async ({ browser }) => {
    sharedPage = await browser.newPage()
  })

  test.afterAll(async () => {
    await sharedPage.close()
  })

  test('the service worker installs and becomes active on this origin', async () => {
    // This navigation is the one PR #679's bug depended on: a browser that
    // has opened the app at least once. Every check after this one runs in
    // the same context, so it inherits the now-active worker.
    const response = await gotoAndCapture(sharedPage, '/')
    expect(
      response.status(),
      'the landing page must itself resolve, or nothing below proves anything'
    ).toBe(200)
    await waitForServiceWorkerActive(sharedPage)
  })

  test('/privacy resolves with its real content for a signed-out client on two consecutive controlled visits', async () => {
    for (const visit of ['first', 'second'] as const) {
      const response = await gotoAndCapture(sharedPage, PRIVACY_PATH)
      expect(response.status(), `${visit} visit to ${PRIVACY_PATH}`).toBe(200)
      expect(
        response.headers()['content-type'] ?? '',
        `${visit} visit to ${PRIVACY_PATH} content-type`
      ).toContain('text/html')

      // POSITIVE CONTROL for the KWS-return test below, and the reason it
      // lives here rather than there. That test asserts
      // `response.fromServiceWorker()` is FALSE, which is also what a context
      // with no working service worker would report, for every path, forever.
      // `/privacy` is a real SPA route and is deliberately absent from
      // navigateFallbackDenylist.ts, so the worker SHOULD answer it from the
      // precached shell; asserting that here is what proves the worker is
      // genuinely intercepting navigations in this context and that the
      // `false` below therefore means something.
      //
      // If this ever goes red while everything else passes, the premise the
      // whole file rests on (an active registration answers each subsequent
      // top-level navigation regardless of `clientsClaim`) is what failed, not
      // the privacy page.
      expect(
        response.fromServiceWorker(),
        `${visit} visit to ${PRIVACY_PATH} should be answered by the service worker; ` +
          'if it is not, the worker is not intercepting navigations in this context ' +
          'and the KWS-return assertion below is vacuous'
      ).toBe(true)

      // Distinctive text, not just "navigation resolved": a SW-served
      // fallback shell also resolves and would satisfy a weaker check. The
      // heading text is PrivacyPolicyPage's own <h1>, pinned identically by
      // src/legal/PrivacyPolicyPage.test.tsx.
      await expect(sharedPage.getByRole('heading', { level: 1 })).toContainText(
        /cyo adventure privacy policy/i
      )

      // The phishing-redirect risk the coverage matrix names: a gate on this
      // route would bounce a mid-verification parent to a login page. Checked
      // by pathname rather than a login-only regex, so ANY redirect away from
      // this exact route fails the assertion, not only one to guardian login.
      const { pathname } = new URL(sharedPage.url())
      expect(pathname, `${visit} visit to ${PRIVACY_PATH} must not redirect`).toBe(PRIVACY_PATH)
    }
  })

  test('/support resolves with its real content for a signed-out client on two consecutive controlled visits', async () => {
    for (const visit of ['first', 'second'] as const) {
      const response = await gotoAndCapture(sharedPage, SUPPORT_PATH)
      expect(response.status(), `${visit} visit to ${SUPPORT_PATH}`).toBe(200)
      expect(
        response.headers()['content-type'] ?? '',
        `${visit} visit to ${SUPPORT_PATH} content-type`
      ).toContain('text/html')

      // No `fromServiceWorker` assertion here on purpose: `/support` is an SPA
      // route exactly like `/privacy`, so the positive control that test
      // carries already covers this one, and repeating it would only add a
      // second way for the same premise to report the same failure.

      // "Support" alone would also match a generic error boundary title in
      // some fonts of bad luck, so this pins both the exact h1 (SupportPage's
      // own, per SupportPage.test.tsx) and one sentence from the page body
      // that only the real component renders.
      await expect(
        sharedPage.getByRole('heading', { level: 1, exact: true, name: 'Support' })
      ).toBeVisible()
      await expect(sharedPage.getByText(/we never see the number/i)).toBeVisible()

      const { pathname } = new URL(sharedPage.url())
      expect(pathname, `${visit} visit to ${SUPPORT_PATH} must not redirect`).toBe(SUPPORT_PATH)
    }
  })

  test('the KWS redirect-return leg is answered by the origin, not the service worker, on two consecutive controlled visits', async () => {
    for (const visit of ['first', 'second'] as const) {
      // No `signature` query parameter (see the safety note at the top of
      // this file): api/kws_redirect.py::kws_verification_return refuses this
      // deterministically, a real backend 400. Nothing about that outcome is
      // faked for the test; it is the same refusal a stray or tampered link
      // produces in production, and it is what makes this a safe, repeatable
      // regression check rather than a one-off.
      const response = await gotoAndCapture(sharedPage, KWS_RETURN_PATH)

      // THE assertion this file is named for, and the only one that states the
      // property directly rather than inferring it. Playwright reports whether
      // a Service Worker fetch handler fulfilled the response, so this
      // separates "the origin answered" from "something in the page's own
      // process answered" without reasoning backwards from a status code.
      //
      // Everything below is corroboration, and none of it can replace this:
      // a future Workbox route that intercepted `/api/` and forwarded it to
      // the network (`event.respondWith(fetch(event.request))`) would produce a
      // byte-identical 400 with a byte-identical body while quietly putting the
      // worker back on the path this denylist exists to keep it off. Only this
      // line goes red for that. Its positive control is in the `/privacy` test
      // above; without one, `false` here is also what a context with no
      // functioning worker reports.
      expect(
        response.fromServiceWorker(),
        `${visit} visit to ${KWS_RETURN_PATH} was fulfilled by a service worker fetch ` +
          'handler. navigateFallbackDenylist.ts exists to keep the worker off this ' +
          'path entirely; check that the deployed sw.js carries the denylist patterns.'
      ).toBe(false)

      // A service worker serving its cached index.html for this path answers
      // 200 with the SPA's own catch-all content; the backend's real refusal
      // is 400. A regression reads as this seeing 200 where it expects 400,
      // which is exactly the symptom PR #679's incident report describes.
      expect(response.status(), `${visit} visit to ${KWS_RETURN_PATH}`).toBe(400)

      // Status alone is not enough, and neither is status plus body. This
      // follows the three-part rule e2e-prod/health-probe.spec.ts documents
      // (status, content-type, body: each closes a gap the others leave open),
      // because every deployed environment sits behind Cloudflare and an edge
      // interstitial can answer 400 too, with HTML, without the origin ever
      // seeing the request.
      //
      // The origin has TWO legitimate 400s here and the deployment state
      // decides which one arrives, so this asserts their union rather than
      // pinning one. Each branch is a content-type AND body pair, never a body
      // match on its own, which is the same discrimination
      // scripts/kws_probe_endpoints.py::_classify_return makes:
      //   1. text/html carrying the refusal page, when KWS_VERIFICATION_SECRET
      //      is set. The unsigned link fails _reject and renders
      //      _UNCONFIRMED_PAGE.
      //   2. application/json carrying a ConfigurationError, when that secret
      //      is unset or empty. _require_verification_configured refuses BEFORE
      //      reading the signature, and ConfigurationError is absent from
      //      app.py's _STATUS_BY_EXCEPTION table, so it takes the 400 fallback
      //      and renders as JSON with no <h1> at all.
      //
      // Which branch answers is readable, just not from this repo's source
      // tree: `uv run python scripts/kws_probe_endpoints.py --origin <origin>`
      // classifies exactly these two cases against a live origin, and reports
      // branch 2 as "route is live but KWS_VERIFICATION_SECRET is unset". It is
      // left unpinned here because it is DEPLOYED state that an operator can
      // change without touching this repo, not because it is unknowable.
      // Reading it costs a probe run; pinning it would make this spec red on a
      // config change that has nothing to do with the property under test, and
      // a red-on-arrival test gets muted rather than read. (KWS_VERIFICATION_SECRET
      // is blank in homelab-infra's services/cyo-adventure-staging/stack.env, but
      // so is every other secret-bearing key there (R2_*, GEMINI_API_KEY, the
      // rest of KWS_*): the file carries placeholders and the real values are
      // injected at the stack layer. Staging was probed serving branch 1 on
      // 2026-08-11.)
      //
      // Both branches still falsify the regression this spec exists for: the
      // service worker's cached shell renders NotFoundPage's "We can't find
      // that page", which neither branch contains, and Cloudflare's own error
      // body matches neither.
      const contentType = response.headers()['content-type'] ?? ''
      const body = await response.text()
      // The marker string is api/kws_redirect.py's `_UNCONFIRMED_PAGE`
      // heading, and this is its fourth copy: the other three are
      // kws_redirect.py itself (the source of truth, line ~216),
      // scripts/kws_probe_endpoints.py::_UNCONFIRMED_MARKER, and
      // tests/unit/test_kws_redirect.py. Not coupled to any of them because
      // the coupling would have to cross the Python/TypeScript boundary, and
      // this tier deliberately has no build-time dependency on the backend
      // package. Change the heading and all four move together.
      const isRefusalPage =
        contentType.includes('text/html') && /could not confirm this link/i.test(body)
      const isSecretUnset =
        contentType.includes('application/json') && /"error"\s*:\s*"ConfigurationError"/.test(body)

      expect(
        body,
        `${visit} visit to ${KWS_RETURN_PATH} must not be answered by the SPA shell`
      ).not.toMatch(/we can.t find that page/i)
      expect(
        isRefusalPage || isSecretUnset,
        `${visit} visit to ${KWS_RETURN_PATH} returned a 400 that matches neither ` +
          `origin branch (not text/html + the refusal page, not application/json + a ` +
          `ConfigurationError), which points at an edge or proxy answering instead of ` +
          `the backend. Content-type: ${contentType}. Body: ${body.slice(0, 400)}`
      ).toBe(true)

      // Surfaced rather than silently tolerated, so branch 2 stays visible in
      // the run report instead of reading as an unqualified pass. No register
      // row is cited because none governs this: the assurance register's KWS
      // rows cover the environment (O-123), the enabled-methods declaration
      // (O-124), and the processor disclosure (O-125); the presence of the
      // redirect-leg HMAC secret is tracked nowhere, which is itself worth
      // knowing when this annotation appears.
      if (isSecretUnset) {
        test.info().annotations.push({
          type: 'staging-config-gap',
          description:
            'KWS_VERIFICATION_SECRET is unset or empty on this environment ' +
            '(core/config.py::kws_verification_secret; the same state ' +
            'scripts/kws_probe_endpoints.py reports as "route is live but ' +
            'KWS_VERIFICATION_SECRET is unset"). The origin answered, which is what ' +
            'this spec asserts, but the signature path was never exercised.',
        })
      }

      // Same "no redirect" property as the two SPA pages above: a forged or
      // stale link should render a page in place, not bounce the parent's
      // browser anywhere, least of all to a sign-in form. Pinned to the exact
      // path, so ANY redirect fails, including one to guardian login; a
      // separate `not.toBe(GUARDIAN_LOGIN_PATH)` alongside it could never fail
      // independently and only read as though it could.
      const { pathname } = new URL(sharedPage.url())
      expect(pathname, `${visit} visit to ${KWS_RETURN_PATH} must not redirect`).toBe(
        KWS_RETURN_PATH
      )
    }
  })
})
