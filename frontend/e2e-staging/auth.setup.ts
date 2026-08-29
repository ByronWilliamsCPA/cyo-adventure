import { readFileSync } from 'node:fs'

import { expect, type Page, test as setup } from '@playwright/test'

import { signInAsStagingTestUser } from './support/auth'
import { stagingStorageStatePath } from './support/auth-storage'
import { TOKEN_STORAGE_KEY } from '../src/auth/tokenStorageKey'

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
/**
 * Captures `storageState` for a signed-in role, and refuses to produce a file
 * that does not actually hold a credential.
 *
 * #CRITICAL: security: this setup project's entire output is two credential
 * files, and before this helper existed it asserted NOTHING about them.
 * `signInAsStagingTestUser`'s own guards cover the login form (no error alert,
 * and a post-login destination under `/guardian` or `/admin`), but nothing
 * waited for `AuthContext` to write the bearer into `localStorage`, and
 * `storageState({ path })` captures whatever happens to be present at that
 * instant. Verified: it resolves with no error on a context that has never
 * authenticated and never navigated, writing a well-formed
 * `{"cookies":[],"origins":[]}`.
 *
 * A green setup that wrote a useless file is the worst available outcome,
 * because the failure then surfaces two steps downstream, in a different
 * process, as `device-grant-sweep.spec.ts`'s "no guardian auth_token in
 * localStorage". That message points at the sweep, which is fine, and at
 * staging, which is wrong: the fault is here. Both checks below convert that
 * into a setup-project failure that names its own cause.
 * #VERIFY: the poll is not decoration. It is what makes the capture wait for
 * the token write rather than race it; `TOKEN_STORAGE_KEY` is imported from
 * `src/auth/tokenStorageKey.ts` rather than repeated as a literal so a rename
 * on the app side breaks `tsc` here instead of silently checking a key nothing
 * writes any more.
 */
async function captureAuthenticatedState(page: Page, role: 'guardian' | 'admin'): Promise<void> {
  await expect
    .poll(async () => page.evaluate((key) => window.localStorage.getItem(key), TOKEN_STORAGE_KEY), {
      message:
        `signed in as the staging ${role} but AuthContext never wrote ` +
        `${TOKEN_STORAGE_KEY} into localStorage, so capturing storageState now ` +
        'would write a structurally valid, functionally empty credential file',
      timeout: 10_000,
    })
    .toBeTruthy()

  const statePath = stagingStorageStatePath(role)
  await page.context().storageState({ path: statePath })

  // Read the artifact back rather than trusting the capture. The poll proves
  // the browser had a token; this proves the FILE has one, which is the thing
  // every downstream reader actually consumes.
  // eslint-disable-next-line security/detect-non-literal-fs-filename -- statePath comes from stagingStorageStatePath, a pure helper over this file's own directory, never event input
  const captured = JSON.parse(readFileSync(statePath, 'utf8')) as {
    origins?: Array<{ localStorage?: Array<{ name: string; value: string }> }>
  }
  const token = (captured.origins ?? [])
    .flatMap((origin) => origin.localStorage ?? [])
    .find((entry) => entry.name === TOKEN_STORAGE_KEY)

  expect(
    token?.value,
    `the ${role} storageState file was written without a ${TOKEN_STORAGE_KEY} ` +
      'entry, so every spec and the post-run sweep that restore it would start ' +
      'unauthenticated. Nothing between this write and those reads inspects the ' +
      'file, so this assertion is the only thing standing between a racing ' +
      'capture and a downstream failure that names the wrong subject.'
  ).toBeTruthy()
}

setup('authenticate as the seeded staging guardian', async ({ page }) => {
  await signInAsStagingTestUser(page, 'guardian')
  await captureAuthenticatedState(page, 'guardian')
})

setup('authenticate as the seeded staging admin', async ({ page }) => {
  await signInAsStagingTestUser(page, 'admin')
  await captureAuthenticatedState(page, 'admin')
})
