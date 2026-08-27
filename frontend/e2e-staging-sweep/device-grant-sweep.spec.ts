import { expect, test } from '@playwright/test'

/**
 * Authoritative end-of-job device-grant sweep for the staging tier.
 *
 * Runs AFTER the main tier (see `.github/workflows/e2e-staging.yml`, the
 * `if: always()` sweep step) and asks staging itself the only question that
 * matters: does the test guardian's family hold any ACTIVE device grant?
 *
 * Why this exists on top of the jsonl leak ledger
 * ------------------------------------------------
 * `e2e-staging/support/device-grant.ts` writes a leak ledger, but that ledger
 * is SELF-REPORTED teardown state: it can only describe runs whose teardown
 * actually ran and actually wrote. Three real paths leave a live grant and no
 * ledger line, and each of them reproduces the original false-green (flaky
 * report, exit 0, green job, live 90-day kid-access credential):
 *
 * 1. The worker dies after the mint (OOM, browser crash, "Worker process
 *    exited unexpectedly"). Playwright marks the attempt failed and retries;
 *    a passing retry makes the run flaky and the job exits 0.
 * 2. The `afterAll` hook itself blows the tier's 30s timeout before reaching
 *    `recordLeakedGrant`.
 * 3. `recordLeakedGrant` fails open: it swallows filesystem errors down to a
 *    `console.warn` that nothing reads.
 *
 * The two signals are deliberately complementary and BOTH are kept. The ledger
 * is the DIAGNOSTIC: it names which spec leaked and why, which this sweep
 * cannot tell you (the API returns rows, not culprits). This sweep is the
 * DETERMINISTIC BACKSTOP: it shares none of the ledger's failure modes because
 * it reads staging rather than a file the failing process was supposed to
 * write.
 *
 * #CRITICAL: security: "could not list" is NEVER "nothing leaked". A 429 from
 * the 60 rpm/IP limiter, a network error, an auth failure, a non-2xx, a
 * non-JSON body, or a body that is not a list all FAIL this spec. Degrading
 * any of them to a pass would recreate exactly the silent-failure class this
 * whole PR exists to close: an unobservable leak reported as clean.
 * #VERIFY: every branch below either throws or asserts; there is no early
 * `return` that reaches the end of the test without an assertion.
 *
 * #CRITICAL: security: nothing here may print a credential. `GET
 * /v1/device-grants` never returns the grant token (it is issued once, at mint
 * time; see `src/cyo_adventure/api/device_grants.py`), and this spec logs only
 * DB row ids and labels, never the bearer it authenticates with.
 * #VERIFY: keep the failure message built from `id`/`label` only.
 *
 * Report and fail, do not auto-revoke. A found grant leaves the job red until
 * a human acts, and it stays red on every subsequent scheduled run for as long
 * as the grant is live. Auto-revoking would turn a persistent red into a
 * single red followed by green, which is the weaker signal, and it would also
 * silently destroy a device a human deliberately authorized for manual QA on
 * this shared staging family.
 */
test.describe('staging device-grant sweep', () => {
  test('the test guardian family holds no active device grant after the tier', async ({ page }) => {
    // No sign-in here: `page` was created from `playwright.e2e-staging-sweep.config.ts`'s
    // `storageState`, a guardian session `playwright.e2e-staging.config.ts`'s
    // `staging-auth-setup` project authenticated earlier in the same job. If
    // that setup never ran or failed (wrong password, sustained 429, staging
    // down), the storageState file does not exist and Playwright fails this
    // test's context creation before reaching this line. That is correct and
    // deliberate: an unlistable family is an unproven family, whether the
    // failure surfaces here or at context creation.
    const result = await page.evaluate(async () => {
      const token = window.localStorage.getItem('auth_token')
      if (token === null) {
        return { listed: false as const, reason: 'no guardian auth_token in localStorage' }
      }
      let res: Response
      try {
        res = await fetch('/api/v1/device-grants', {
          headers: { Authorization: `Bearer ${token}` },
        })
      } catch (err) {
        return { listed: false as const, reason: `GET /v1/device-grants threw: ${String(err)}` }
      }
      if (!res.ok) {
        return { listed: false as const, reason: `GET /v1/device-grants returned ${res.status}` }
      }
      let body: unknown
      try {
        body = (await res.json()) as unknown
      } catch (err) {
        return {
          listed: false as const,
          reason: `GET /v1/device-grants body was not JSON: ${String(err)}`,
        }
      }
      if (!Array.isArray(body)) {
        return {
          listed: false as const,
          reason: 'GET /v1/device-grants did not return a list',
        }
      }
      // Row ids and labels only. The endpoint never returns a token, and
      // nothing else from the row is needed to act on a leak.
      const grants = (body as Array<Record<string, unknown>>).map((row) => ({
        id: typeof row.id === 'string' ? row.id : 'unidentified',
        label: typeof row.label === 'string' ? row.label : '',
      }))
      return { listed: true as const, grants }
    })

    if (!result.listed) {
      throw new Error(
        'Could not list the staging test family device grants, so this sweep ' +
          'cannot prove the family is clean. Treated as a FAILURE, never as ' +
          `"no leaks": ${result.reason}`
      )
    }

    const described = result.grants
      .map((grant) => (grant.label ? `${grant.id} ("${grant.label}")` : grant.id))
      .join(', ')
    expect(
      result.grants,
      'The staging test guardian family still holds active device grants after ' +
        'the e2e tier finished, so the tier leaked at least one live 90-day ' +
        `kid-access credential: ${described}. Revoke them from the guardian ` +
        'console (or DELETE /v1/device-grants/{id}) and check ' +
        'test-results/leaked-device-grants.jsonl in this run for which spec ' +
        'left them behind.'
    ).toEqual([])
  })
})
