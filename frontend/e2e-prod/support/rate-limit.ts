import type { Page } from '@playwright/test'

/**
 * Production enforces a 60 rpm/IP rolling rate limit (disabled only in
 * ENVIRONMENT=local). One SPA navigation fans out into several backend GETs
 * (`/v1/me` plus the destination page's own data), so walking the consoles'
 * pages back-to-back can burst past that ceiling even though this tier is
 * serial (`workers:1`) and signs in only once. When it trips, the backend
 * returns 429 and the app renders an advisory alert in place of the data:
 *   - a page's data fetch: "You're doing that a bit fast. Please wait a moment
 *     and try again."
 *   - the post-login `/v1/me`: "You're signed in, but we couldn't load your
 *     account. Please try again." (AuthContext maps any `/v1/me` non-200 to
 *     this generic copy, so a transient 429 is indistinguishable from a real
 *     auth break at the UI layer.)
 *
 * Both are transient. This module keeps the tier under the limit two ways that
 * compose: a minimum gap between navigations so ordinary bursts stay below the
 * ceiling, and, if one still trips, an exponential backoff-and-retry so a
 * rate-limit blip never fails an otherwise-green run. Only a limit that never
 * clears (a real sustained throttle) surfaces as a failure.
 */
export const RATE_LIMIT_ALERT =
  /doing that a bit fast|too many requests|couldn.t load your account/i

// One SPA navigation is ~4-6 backend calls; a 2s floor between navigations
// keeps the rolling one-minute window comfortably under 60 requests without
// making the ~15-navigation tier crawl. Module-level state is shared across
// every spec in this single-worker tier, so the floor paces the whole run,
// not just one file.
const MIN_NAV_GAP_MS = 2_000

// Exponential backoff schedule when a navigation still comes back rate-limited:
// 2s, 4s, 8s. The 60 rpm window is one minute, so a couple of seconds is
// usually enough for enough of the rolling window to age out.
const BACKOFF_BASE_MS = 2_000

let lastNavAt = 0

/**
 * Enforces the inter-navigation floor: if less than MIN_NAV_GAP_MS has elapsed
 * since the previous paced navigation, wait out the remainder. Records the
 * timestamp so successive calls stay spaced regardless of which spec makes them.
 */
async function paceNavigation(page: Page): Promise<void> {
  // #EDGE: timing: `lastNavAt` is per-worker module state; this tier is
  // `workers:1`, so one instance paces the entire run. If the tier ever goes
  // multi-worker, each worker would pace independently and the aggregate rate
  // could still exceed the limit, at which point the backoff below is the
  // backstop.
  // #VERIFY: playwright.e2e-prod.config.ts must keep `workers: 1`.
  const elapsed = Date.now() - lastNavAt
  if (elapsed < MIN_NAV_GAP_MS) {
    await page.waitForTimeout(MIN_NAV_GAP_MS - elapsed)
  }
  lastNavAt = Date.now()
}

/**
 * Resolves true when a rate-limit / account-load advisory alert becomes visible
 * within `timeout`, false otherwise. Kept short: a real 429 renders its alert as
 * soon as the mount fetch resolves, so a couple of seconds is ample and a clean
 * page simply falls through.
 */
export async function isRateLimited(page: Page, timeout = 2_000): Promise<boolean> {
  return page
    .getByRole('alert')
    .filter({ hasText: RATE_LIMIT_ALERT })
    .first()
    .waitFor({ state: 'visible', timeout })
    .then(() => true)
    .catch(() => false)
}

/**
 * `page.goto` that respects the navigation pacing floor and, if the destination
 * comes back rate-limited, backs off and reloads rather than handing the caller
 * a page whose data region is a rate-limit alert. Throws only if the limit never
 * clears across `maxAttempts`, which indicates a sustained throttle rather than
 * the ordinary burst this tier is prone to.
 */
export async function gotoResilient(page: Page, path: string, maxAttempts = 3): Promise<void> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    await paceNavigation(page)
    await page.goto(path)
    if (!(await isRateLimited(page))) return
    if (attempt === maxAttempts) {
      throw new Error(
        `${path} stayed rate-limited after ${maxAttempts} attempts; production ` +
          'may be under a sustained throttle rather than a transient burst.'
      )
    }
    await page.waitForTimeout(BACKOFF_BASE_MS * 2 ** (attempt - 1))
  }
}

/** Backoff delay for the Nth (1-indexed) retry, exported for callers that run
 * their own attempt loop (e.g. the sign-in flow, which is not a plain goto). */
export function backoffDelayMs(attempt: number): number {
  return BACKOFF_BASE_MS * 2 ** (attempt - 1)
}
