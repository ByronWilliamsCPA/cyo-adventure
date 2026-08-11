import type { Page, Response } from '@playwright/test'
import { expect, test } from '@playwright/test'

import { GUARDIAN_LOGIN_PATH, PRIVACY_PATH, SUPPORT_PATH } from '../src/routes'
import { backoffDelayMs, paceNavigation } from '../e2e-support/rate-limit'

/**
 * Closes the coverage-matrix gap under "Public: privacy policy and support
 * (signed-out)" and "Guardian: KWS parent verification (ADR-018 D1)": no test
 * asserted that the URLs registered with Epic's Kids Web Services actually
 * resolve over HTTP for a signed-out client against a deployed environment.
 * That is the exact blind spot PR #679 fixed a real bug in: the service
 * worker's navigation fallback answered every navigation on this origin with
 * the cached SPA shell, so `GET /api/v1/consent/kws/return`
 * (`src/cyo_adventure/api/kws_redirect.py`), a page the backend renders as
 * real HTML, 404'd in every browser that had ever opened the app once, while
 * curl, Postman, and every prior CI tier (none of which run a service
 * worker) saw it as healthy. `frontend/src/pwa/navigateFallbackDenylist.ts`
 * is the fix; this spec is what proves the fix holds against a real deployed
 * origin rather than only against the denylist's own regex unit test
 * (`navigateFallbackDenylist.test.ts`, which never loads a real service
 * worker).
 *
 * HARD SAFETY CONSTRAINT: this spec must never trigger a real KWS
 * verification send. `POST /api/v1/consent/kws/start` discloses a real
 * adult's email address to Epic Games with no DPA in place (register row
 * O-125), and that is a standing block on production sends. Every request
 * below is a plain, unauthenticated GET; the KWS redirect-return leg is hit
 * with no `signature` query parameter, which the backend genuinely refuses
 * (`api/kws_redirect.py`, a real backend answer this spec depends on) rather
 * than accepts, and every refusal branch there is display-only and writes
 * nothing to `kws_verification` (see that module's docstring). Do not add a
 * `signature` here, and do not call the `/start` endpoint from this file.
 *
 * "Second visit matters" throughout: a service worker never controls the
 * navigation that installs it, so a check made only once, right after that
 * first navigation, can pass by accident and hide exactly the bug PR #679
 * fixed. Every URL below is therefore requested twice in the same browser
 * context, once immediately after the service worker's registration reports
 * `active` and once more after that, so a fluke in Workbox's first-match
 * routing on the earlier request cannot hide behind a single lucky pass.
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
 */
async function gotoAndCapture(page: Page, path: string, maxAttempts = 3): Promise<Response> {
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

  test('/privacy resolves with its real content for a signed-out client, before and after SW control', async () => {
    for (const visit of ['first', 'second'] as const) {
      const response = await gotoAndCapture(sharedPage, PRIVACY_PATH)
      expect(response.status(), `${visit} visit to ${PRIVACY_PATH}`).toBe(200)

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

  test('/support resolves with its real content for a signed-out client, before and after SW control', async () => {
    for (const visit of ['first', 'second'] as const) {
      const response = await gotoAndCapture(sharedPage, SUPPORT_PATH)
      expect(response.status(), `${visit} visit to ${SUPPORT_PATH}`).toBe(200)

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

  test('the KWS redirect-return leg is answered by the backend, not a 404 SPA shell, before and after SW control', async () => {
    for (const visit of ['first', 'second'] as const) {
      // No `signature` query parameter (see the safety note at the top of
      // this file): api/kws_redirect.py::kws_verification_return refuses this
      // deterministically, a real backend 400. Nothing about that outcome is
      // faked for the test; it is the same refusal a stray or tampered link
      // produces in production, and it is what makes this a safe, repeatable
      // regression check rather than a one-off.
      const response = await gotoAndCapture(sharedPage, KWS_RETURN_PATH)

      // This is the assertion the SW bug breaks. A service worker serving
      // its cached index.html for this path answers with status 200 and the
      // SPA's own catch-all content; the backend's real refusal is 400. A
      // regression here reads as this test seeing 200 where it expects 400,
      // which is exactly the symptom PR #679's incident report describes.
      expect(response.status(), `${visit} visit to ${KWS_RETURN_PATH}`).toBe(400)

      // A bare status check is not enough on its own. Every deployed
      // environment sits behind Cloudflare, and an edge interstitial can also
      // answer 400 without the origin ever seeing the request, so the body has
      // to prove which box replied.
      //
      // The origin has TWO legitimate 400s here and the deployment state
      // decides which one arrives, so this asserts their union rather than
      // pinning one:
      //   1. The HTML refusal page, when KWS_VERIFICATION_SECRET is set. The
      //      unsigned link fails _reject and renders _UNCONFIRMED_PAGE.
      //   2. A JSON ConfigurationError, when that secret is unset or empty.
      //      _require_verification_configured refuses BEFORE reading the
      //      signature, and ConfigurationError is absent from app.py's
      //      _STATUS_BY_EXCEPTION table, so it takes the 400 fallback and
      //      renders as JSON with no <h1> at all.
      // Which branch answers is operator state this repo cannot see, so it is
      // deliberately not pinned. KWS_VERIFICATION_SECRET is blank in
      // homelab-infra's services/cyo-adventure-staging/stack.env, but so is
      // every other secret-bearing key there (R2_*, GEMINI_API_KEY, the rest of
      // KWS_*): the file carries placeholders and the real values are injected
      // at the stack layer, so a blank there is not evidence the deployed value
      // is empty. Staging was observed serving branch 1 on 2026-08-11. Pinning
      // either branch makes this spec red on a config change that has nothing
      // to do with the property under test, and a red-on-arrival test gets
      // muted rather than read.
      //
      // Both branches still falsify the regression this spec exists for: the
      // service worker's cached shell renders NotFoundPage's "We can't find
      // that page", which neither branch contains, and Cloudflare's own error
      // body matches neither.
      const body = await response.text()
      const isRefusalPage = /could not confirm this link/i.test(body)
      const isSecretUnset = /"error"\s*:\s*"ConfigurationError"/.test(body)

      expect(
        body,
        `${visit} visit to ${KWS_RETURN_PATH} must not be answered by the SPA shell`
      ).not.toMatch(/we can.t find that page/i)
      expect(
        isRefusalPage || isSecretUnset,
        `${visit} visit to ${KWS_RETURN_PATH} returned a 400 that came from neither ` +
          `origin branch (not the refusal page, not a ConfigurationError), which points ` +
          `at an edge or proxy answering instead of the backend. Body: ${body.slice(0, 400)}`
      ).toBe(true)

      // Surfaced rather than silently tolerated, so branch 2 stays visible in
      // the run report instead of reading as an unqualified pass.
      if (isSecretUnset) {
        test.info().annotations.push({
          type: 'staging-config-gap',
          description:
            'KWS_VERIFICATION_SECRET is unset or empty on this environment (register ' +
            'row O-124). The origin answered, which is what this spec asserts, but the ' +
            'signature path was never exercised.',
        })
      }

      // Same "no redirect" property as the two SPA pages above: a forged or
      // stale link should render a page in place, not bounce the parent's
      // browser anywhere, least of all to a sign-in form.
      const { pathname } = new URL(sharedPage.url())
      expect(pathname, `${visit} visit to ${KWS_RETURN_PATH} must not redirect`).toBe(
        KWS_RETURN_PATH
      )
      expect(pathname).not.toBe(GUARDIAN_LOGIN_PATH)
    }
  })
})
