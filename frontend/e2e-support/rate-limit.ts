import { errors, type Page } from '@playwright/test'

/**
 * Shared by the e2e-prod and e2e-staging tiers. Every deployed environment
 * enforces a 60 rpm/IP rolling rate limit; `app.py` enables the limiter
 * whenever `ENVIRONMENT != "local"`, so staging is subject to exactly the same
 * ceiling as production. One SPA navigation fans out into several backend GETs
 * (`/v1/me` plus the destination page's own data), so walking the consoles'
 * pages back-to-back can burst past that ceiling even though both tiers are
 * serial (`workers: 1`) and sign in only once.
 *
 * When the limit trips, the backend returns 429 and the app renders an advisory
 * alert in place of the data:
 *   - a page's data fetch: "You're doing that a bit fast. Please wait a moment
 *     and try again."
 *   - the post-login `/v1/me`: "You're signed in, but we couldn't load your
 *     account. Please try again."
 *
 * This module keeps a tier under the limit two ways that compose: a minimum gap
 * between navigations, and an exponential backoff-and-retry when one still
 * trips. Only a limit that never clears surfaces as a failure.
 *
 * #ASSUME: external resources: the constants below encode the deployed
 * limiter's shape (60 requests, rolling one-minute window, per source IP).
 * #VERIFY: `src/cyo_adventure/app.py` (`enable_rate_limiting`) and the limiter
 * config it reads are the source of truth; re-tune MIN_NAV_GAP_MS and
 * BACKOFF_BASE_MS if that ceiling or window ever changes.
 */
export const RATE_LIMIT_ALERT =
  /doing that a bit fast|too many requests|couldn.t load your account/i

/**
 * Minimum gap between paced navigations.
 *
 * This floor is one of three contributors to the real inter-navigation spacing,
 * not the whole budget: `gotoResilient` also pays the settle wait in
 * `isRateLimited` and the page load itself, which together put the observed
 * floor nearer 3-4s per navigation. Do NOT reason about the effective request
 * rate from this constant alone; 2s in isolation would permit ~30 navigations
 * per minute (roughly 120-180 backend calls), well over the ceiling. The
 * measured behaviour of the full sequence is what keeps a run legal: a live
 * production run of the prod tier issued 1051 requests with zero 429s.
 *
 * Module-level state is shared across every spec in a single-worker tier, so
 * the floor paces a whole run rather than one file.
 */
const MIN_NAV_GAP_MS = 2_000

/**
 * Exponential backoff base when a navigation still comes back rate-limited:
 * `BACKOFF_BASE_MS * 2 ** (attempt - 1)`. At the default `maxAttempts = 3` the
 * final attempt throws instead of sleeping, so the delays actually emitted are
 * 2s and 4s; the 8s step is only reachable if a caller raises `maxAttempts`.
 *
 * #EDGE: timing: this backoff is sized for a burst that has just crossed the
 * ceiling, not for a window that is saturated end to end. 6s of total backoff
 * only ages out requests made 54-60s ago, so a run that spends its whole
 * 60-request budget in the first few seconds will exhaust the retries.
 * #VERIFY: if `gotoResilient` starts throwing routinely, the fix is more
 * spacing (raise MIN_NAV_GAP_MS) or fewer navigations, not a longer backoff.
 */
const BACKOFF_BASE_MS = 2_000

/**
 * Bounded wait for the SPA's mount fetches to settle before judging whether a
 * navigation was rate-limited. `page.goto` resolves on `load`, which fires
 * before the mounted route issues its own requests, so a check made at that
 * instant races the very response it is trying to observe.
 *
 * #ASSUME: timing: a route's mount fetches reach network idle within
 * SETTLE_TIMEOUT_MS. If they do not (a long-poll or an unresponsive backend),
 * the wait times out and the alert check below still runs, so a slow mount
 * degrades to the previous best-effort behaviour rather than failing.
 * #VERIFY: a spec failing on a missing heading where the page in fact showed a
 * rate-limit alert means this budget is too small for that route.
 */
const SETTLE_TIMEOUT_MS = 3_000

/** Grace period for the alert to paint once the mount fetches have settled. */
const ALERT_TIMEOUT_MS = 1_000

let lastNavAt = 0

/**
 * Re-throws anything that is not a Playwright timeout. A bare `.catch(() =>
 * false)` would fold a real fault (the page closed mid-check, a locator
 * resolution error) into "not rate limited", which is the answer most likely to
 * produce a confusing downstream failure.
 *
 * Matches on `errors.TimeoutError` rather than `err.name === 'TimeoutError'`,
 * the idiom e2e-staging/support/auth.ts already uses: a name check would also
 * swallow an unrelated DOMException that happens to carry that name.
 */
function rethrowUnlessTimeout(err: unknown): void {
  if (err instanceof errors.TimeoutError) return
  throw err
}

/**
 * Enforces the inter-navigation floor: if less than MIN_NAV_GAP_MS has elapsed
 * since the previous paced navigation, wait out the remainder. Records the
 * timestamp so successive calls stay spaced regardless of which spec or helper
 * makes them, which is why the sign-in flow calls this too rather than issuing
 * a bare `page.goto`.
 *
 * #EDGE: concurrency: `lastNavAt` is per-worker module state; both tiers run
 * `workers: 1`, so one instance paces the entire run. If a tier ever goes
 * multi-worker, each worker would pace independently and the aggregate rate
 * could still exceed the limit, at which point the backoff is the backstop.
 * #VERIFY: playwright.e2e-prod.config.ts and playwright.e2e-staging.config.ts
 * must both keep `workers: 1`.
 */
export async function paceNavigation(page: Page): Promise<void> {
  const elapsed = Date.now() - lastNavAt
  if (elapsed < MIN_NAV_GAP_MS) {
    await page.waitForTimeout(MIN_NAV_GAP_MS - elapsed)
  }
  lastNavAt = Date.now()
}

/**
 * Resolves true when a rate-limit / account-load advisory alert is showing once
 * the page's mount fetches have settled, false otherwise.
 *
 * Note the two-phase wait. Checking for the alert immediately after `goto`
 * would race the mount fetch that produces it: a 429 whose response lands a
 * moment later would read as "clean", the caller would skip its retry, and the
 * spec would fail on a missing heading instead of on the rate limit that
 * actually caused it. Waiting for network idle first makes the check observe a
 * settled page.
 */
export async function isRateLimited(
  page: Page,
  settleTimeout = SETTLE_TIMEOUT_MS
): Promise<boolean> {
  await page.waitForLoadState('networkidle', { timeout: settleTimeout }).catch(rethrowUnlessTimeout)
  return page
    .getByRole('alert')
    .filter({ hasText: RATE_LIMIT_ALERT })
    .first()
    .waitFor({ state: 'visible', timeout: ALERT_TIMEOUT_MS })
    .then(() => true)
    .catch((err: unknown) => {
      rethrowUnlessTimeout(err)
      return false
    })
}

/**
 * `page.goto` that respects the navigation pacing floor and, if the destination
 * comes back rate-limited, backs off and reloads rather than handing the caller
 * a page whose data region is a rate-limit alert. Throws only if the limit never
 * clears across `maxAttempts`.
 */
export async function gotoResilient(page: Page, path: string, maxAttempts = 3): Promise<void> {
  assertPositiveAttempts(maxAttempts, 'gotoResilient')
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    await paceNavigation(page)
    await page.goto(path)
    if (!(await isRateLimited(page))) return
    if (attempt === maxAttempts) {
      throw new Error(
        `${path} was still rate-limited after ${maxAttempts} attempts. Either ` +
          'production is under a sustained external throttle, or this tier is ' +
          'issuing requests faster than MIN_NAV_GAP_MS assumes; check the run ' +
          'for unpaced navigations before blaming the backend.'
      )
    }
    await page.waitForTimeout(backoffDelayMs(attempt))
  }
}

/** Backoff delay for the Nth (1-indexed) retry, exported for callers that run
 * their own attempt loop (e.g. the sign-in flow, which is not a plain goto). */
export function backoffDelayMs(attempt: number): number {
  return BACKOFF_BASE_MS * 2 ** (attempt - 1)
}

/**
 * Guards the retry helpers against a non-positive `maxAttempts`, which would
 * skip the loop body entirely and return success without having navigated or
 * signed in. The subsequent assertion failure would then point at page content
 * rather than at the helper that silently did nothing.
 */
export function assertPositiveAttempts(maxAttempts: number, caller: string): void {
  if (!Number.isInteger(maxAttempts) || maxAttempts < 1) {
    throw new Error(`${caller}: maxAttempts must be a positive integer, got ${maxAttempts}`)
  }
}
