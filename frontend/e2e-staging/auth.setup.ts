import { test as setup } from '@playwright/test'

import { signInAsStagingTestUser } from './support/auth'
import { stagingStorageStatePath } from './support/auth-storage'

/**
 * Authenticates once per distinct role the staging tier's specs need, and
 * persists each session's `storageState` to disk so every spec (and the
 * separate post-run sweep, a different `npm run` invocation entirely) can
 * restore an already-signed-in session instead of resubmitting the login
 * form.
 *
 * This is the whole remedy for the tier's self-inflicted HTTP 429 streak: the
 * root cause was never worker concurrency (`workers: 1` already), it was
 * sign-in VOLUME against the shared 60 rpm/IP limiter. Before this file
 * existed, six separate call sites each ran the full interactive Supabase
 * sign-in (`guardian-admin-smoke.spec.ts` x2, `kid-library-smoke.spec.ts` x1,
 * `moderation-qa-invisibility.spec.ts` x2, and the sweep's own x1), and two of
 * those six ran in a SEPARATE process from the other four (the main tier and
 * the sweep are two separate `npm run` invocations against
 * `playwright.e2e-staging.config.ts` and
 * `playwright.e2e-staging-sweep.config.ts` respectively), so no amount of
 * in-process pacing (`paceNavigation`/`gotoResilient`,
 * `e2e-support/rate-limit.ts`) could coordinate the two processes' spend
 * against one server-side window. This file cuts the whole job to exactly two
 * sign-ins, both here, and the sweep now performs zero: see
 * `playwright.e2e-staging-sweep.config.ts`'s `storageState` option, which
 * points at the guardian file this writes.
 *
 * Named `*.setup.ts`, not `*.spec.ts`, on purpose: Playwright's default
 * `testMatch` only picks up `test`/`spec` filenames, so this file is invisible
 * to the `e2e-staging` project's implicit glob and is reachable only through
 * the dedicated `staging-auth-setup` project
 * (`playwright.e2e-staging.config.ts`) that the tier's real project declares
 * as a `dependencies` entry. This mirrors the existing
 * `real-backend-setup`/`_reset.setup.ts` pattern in the mocked/real-backend
 * config (`playwright.config.ts`), not a new convention invented for this
 * tier.
 *
 * #CRITICAL: security: signInAsStagingTestUser also clears the ADR-018
 * guardian-consent interstitial the first time the seeded guardian signs in
 * (see `acceptGuardianConsentIfPresent` in `./support/auth`), which is the
 * tier's one non-idempotent write beyond this file's own two logins. It
 * happens here now, not in `guardian-admin-smoke.spec.ts`'s `beforeAll` where
 * it used to: the consent record this writes is server-tracked and read live
 * from `/v1/me` on every subsequent session (guaranteed by
 * `src/auth/AuthContext.tsx`'s `syncPrincipal`, which calls
 * `onboardingApi.onboard()` and `GET /v1/me` fresh on every page load rather
 * than trusting anything cached in the browser), so a restored `storageState`
 * still resolves correctly through `ProtectedRoute` without re-consenting.
 * #VERIFY: if the seeded guardian is ever recreated with a fresh row lacking
 * `consent_accepted_at`, the first run of this setup project performs that
 * write again; nothing downstream depends on it being skippable.
 */
setup('authenticate as the seeded staging guardian', async ({ page }) => {
  await signInAsStagingTestUser(page, 'guardian')
  await page.context().storageState({ path: stagingStorageStatePath('guardian') })
})

setup('authenticate as the seeded staging admin', async ({ page }) => {
  await signInAsStagingTestUser(page, 'admin')
  await page.context().storageState({ path: stagingStorageStatePath('admin') })
})
