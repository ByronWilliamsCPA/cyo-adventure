import { errors, expect, type Page } from '@playwright/test'

import { GUARDIAN_CONSENT_PATH, GUARDIAN_LOGIN_PATH } from '../../src/routes'
import { requireStagingCredentials } from './staging-env'
import {
  assertPositiveAttempts,
  backoffDelayMs,
  paceNavigation,
  RATE_LIMIT_ALERT,
} from '../../e2e-support/rate-limit'

/**
 * Legal name typed into the ADR-018 consent form's electronic-signature field.
 * Deliberately self-identifying: this string is persisted on the staging
 * guardian's consent record, so anyone auditing staging consent data can see at
 * a glance that it came from the automated tier, not from a real guardian.
 */
const CONSENT_SIGNER_NAME = 'Staging E2E Test Guardian'

/**
 * Signs in through the real login form against the staging Supabase project,
 * as either the seeded test guardian or the seeded test admin (see
 * scripts/seed_staging.py). Adapted from e2e-prod/support/auth.ts's
 * signInAsProdTestAdmin: same real-Supabase-signin mechanics, parameterized
 * by role since staging seeds two separate accounts rather than one
 * dual-role account.
 *
 * The rate-limit retry is adapted from the same source. Staging is not a
 * lighter-weight target in this respect: `app.py` enables the 60 rpm/IP limiter
 * for every `ENVIRONMENT != "local"` deployment, so the identical ceiling
 * applies here.
 *
 * Called exactly twice per staging job now, both from
 * `e2e-staging/auth.setup.ts` (once per role), not from the specs
 * themselves. Before that setup project existed, this ran once per spec file
 * per role (five call sites across three of the tier's four spec files;
 * `kws-public-urls.spec.ts` exercises unauthenticated URLs and never signed
 * in) plus once more
 * in the separate device-grant sweep's own `npm run` invocation, six sign-ins
 * total against one runner IP across two processes that could not coordinate
 * their spend against the same server-side rate-limit window; that volume,
 * not worker concurrency (`workers: 1` was already the config), was the cause
 * of this tier's self-inflicted 429 streak. See
 * `playwright.e2e-staging.config.ts`'s `staging-auth-setup` project and
 * `playwright.e2e-staging-sweep.config.ts`'s `storageState` option, which
 * between them are why every other caller now restores a session from disk
 * instead of calling this function.
 *
 * A 429 on the post-login `/v1/me` renders AuthContext's "we couldn't load your
 * account" alert, which is indistinguishable at the UI from a real auth break,
 * so the whole sign-in is retried behind RATE_LIMIT_ALERT. As on prod, that
 * means a genuine `/v1/me` 5xx is also retried before it surfaces (AuthContext
 * maps every non-200 from that endpoint to the same copy); it still fails, one
 * backoff cycle later. A wrong password renders a different alert and surfaces
 * on the first attempt.
 *
 * #CRITICAL: security: this loop re-submits real staging credentials, so an
 * upstream auth throttle could be deepened by the retry rather than waited out.
 * #VERIFY: keep `maxAttempts` at 3 or lower, and keep the retry gated on
 * RATE_LIMIT_ALERT so a wrong-password alert can never loop.
 */
export async function signInAsStagingTestUser(
  page: Page,
  role: 'guardian' | 'admin',
  maxAttempts = 3
): Promise<void> {
  const { email, password } = requireStagingCredentials(role)
  assertPositiveAttempts(maxAttempts, 'signInAsStagingTestUser')

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    // Through the shared pacer rather than a bare goto, for both reasons the
    // prod tier does it: sign-in is the heaviest request burst in a run, and a
    // bare goto would leave `lastNavAt` stale so the next paced navigation
    // skipped its floor entirely.
    await paceNavigation(page)
    await page.goto(GUARDIAN_LOGIN_PATH)
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Password').fill(password)
    await page.getByRole('button', { name: 'Sign in' }).click()

    const left = page
      .waitForURL((url) => url.pathname !== GUARDIAN_LOGIN_PATH, { timeout: 15_000 })
      .then(() => null)
    const failed = page
      .getByRole('alert')
      .waitFor({ state: 'visible', timeout: 15_000 })
      .then(() => page.getByRole('alert').innerText())

    const alertText = await Promise.race([left, failed])
    if (alertText !== null) {
      if (!RATE_LIMIT_ALERT.test(alertText) || attempt === maxAttempts) {
        throw new Error(`Staging login failed for role=${role}: ${alertText}`)
      }
      await page.waitForTimeout(backoffDelayMs(attempt))
      continue
    }

    const destination = new URL(page.url()).pathname
    if (!destination.startsWith('/guardian') && !destination.startsWith('/admin')) {
      throw new Error(`Unexpected post-login destination for role=${role}: ${destination}`)
    }

    await acceptGuardianConsentIfPresent(page)
    return
  }
}

/**
 * Completes the ADR-018 guardian-consent interstitial if the post-login
 * destination is it.
 *
 * #CRITICAL: data integrity: this is the ONE staging interstitial that is not
 * re-presented on a later visit. ProtectedRoute derives `needs-consent` from
 * `/v1/me`, so an unconsented guardian is bounced to GUARDIAN_CONSENT_PATH from
 * EVERY protected route, and submitting the form writes a persistent consent
 * record rather than a per-session flag. That is why the call sits in
 * signInAsStagingTestUser rather than beside unlockParentalGateIfPresent at each
 * navigation: clearing it once per sign-in is sufficient, and probing per page
 * would spend the 5s absent-gate timeout on every goto for no added coverage.
 *
 * The gap this closes: guardian-admin-smoke.spec.ts and kid-library-smoke.spec.ts
 * only ever handled the ADR-014 AdultGate ("Grown-ups only"), a different
 * interstitial with a different trigger, so both specs asserted against a
 * consent form they had no way to get past. Every run of the staging tier since
 * it was added failed here, and the Playwright error-context snapshot named the
 * cause plainly: `heading "Before you get started" [level=1]`.
 *
 * #VERIFY: this makes the otherwise read-only staging smoke tier perform exactly
 * one write, and only on a guardian who has never consented.
 *
 * The seed is NOT the gap. scripts/seed_staging.py already records
 * consent_accepted_at, consent_policy_version, consent_signer_name, and
 * consent_ip when it creates the guardian. What it does not do is backfill:
 * it returns early when the guardian already exists, so the guardian seeded
 * 2026-07-11, before those columns existed, still has no consent record and
 * never acquires one no matter how often the seed re-runs. Once that row is
 * backfilled (or a fresh staging project is seeded), this becomes a no-op
 * probe rather than dead code, which is the intended steady state. Prefer
 * fixing the backfill over widening this helper: 1518fc9 already established
 * the seed layer as where this class of gap gets closed.
 */
export async function acceptGuardianConsentIfPresent(page: Page): Promise<void> {
  const consentHeading = page.getByRole('heading', { name: 'Before you get started', level: 1 })
  // Only a timeout means "no consent gate here". A closed page or context, a
  // navigation abort, or any other Playwright failure is a real browser fault:
  // swallowing it would let this return `false`, skip the write, and surface as
  // a confusing assertion failure in the caller instead of at its cause.
  const gated = await consentHeading
    .waitFor({ state: 'visible', timeout: 5_000 })
    .then(() => true)
    .catch((error: unknown) => {
      if (error instanceof errors.TimeoutError) return false
      throw error
    })
  if (!gated) return

  // #CRITICAL: data integrity: everything below this line WRITES to staging. It
  // records a persistent ADR-018 consent record against the seeded guardian, so
  // this scheduled, unattended tier is no longer purely read-only. The write is
  // idempotent in effect (a consented guardian never reaches here, because the
  // `gated` probe above returns false) but it is not reversible from the test.
  // #VERIFY: keep this the ONLY write signInAsStagingTestUser performs. Before
  // adding another, confirm it is safe to run unattended on a cron against
  // shared staging data, and update the write's description in both
  // e2e-staging/auth.setup.ts (where it now runs, once per role) and
  // guardian-admin-smoke.spec.ts (which documents it happening upstream) to
  // match.
  await page.getByLabel('Your full legal name').fill(CONSENT_SIGNER_NAME)
  await page
    .getByRole('checkbox', {
      name: /electronic signature agreeing to CYO Adventure's Privacy Notice/,
    })
    .check()
  await page.getByLabel('Your country of residence').selectOption('US')
  await page.getByRole('checkbox', { name: 'I confirm that I am an adult.' }).check()
  await page.getByRole('button', { name: 'Agree and continue' }).click()

  // The page has no local success state: recordConsent's syncPrincipal flips
  // AuthStatus to 'signed-in' and ProtectedRoute re-renders past this component.
  // Assert on both halves of that transition so a consent POST that 4xxs surfaces
  // here, at its cause, instead of as a confusing assertion failure in the caller.
  // Compare the pathname, not a URL suffix: a `?next=...` query or a `#section`
  // hash would defeat an anchored regex and let this pass while the browser is
  // still sitting on the consent interstitial.
  await expect(consentHeading).not.toBeVisible({ timeout: 15_000 })
  await expect(page).not.toHaveURL((url) => url.pathname === GUARDIAN_CONSENT_PATH)
}

/**
 * Completes the AdultGate re-auth challenge if `page.goto()` landed on it.
 * See e2e-prod/support/auth.ts's unlockParentalGateIfPresent for the ADR-014
 * warm/cold-gate rationale this mirrors.
 */
export async function unlockParentalGateIfPresent(
  page: Page,
  role: 'guardian' | 'admin'
): Promise<void> {
  const gateHeading = page.getByRole('heading', { name: 'Grown-ups only', level: 1 })
  const gated = await gateHeading
    .waitFor({ state: 'visible', timeout: 5_000 })
    .then(() => true)
    .catch(() => false)
  if (!gated) return

  const { password } = requireStagingCredentials(role)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Confirm' }).click()
  await expect(gateHeading).not.toBeVisible({ timeout: 15_000 })
}
