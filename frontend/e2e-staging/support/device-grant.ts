import { appendFile, mkdir } from 'node:fs/promises'
import path from 'node:path'

import type { Page } from '@playwright/test'

/**
 * Device-grant teardown helpers shared by the tier's two grant-writing specs
 * (kid-library-smoke and moderation-qa-invisibility).
 *
 * Both specs mint exactly one grant and revoke it in a final test, with an
 * `afterAll` backstop for the case where that test never runs. Serial mode
 * makes that case the NORMAL one on failure: a failing test skips the rest of
 * its describe, so the explicit revoke is precisely what does not happen when
 * something goes wrong.
 *
 * #CRITICAL: security: the backstop must not depend on state the failure path
 * destroys. Both specs previously re-read `localStorage['device_grant']` at
 * teardown to find the id, but `useApi.ts`'s response interceptor calls
 * `clearDeviceGrant()` on any device-grant 401, so a grant the backend refuses
 * has already had its client record erased by the time `afterAll` runs. The
 * two conditions therefore coincided exactly: the backstop no-opped in every
 * run where it was the only cleanup left, silently accumulating live 90-day
 * kid-access credentials on shared staging.
 * #VERIFY: capture the id at mint time via `readPersistedGrantId` into a
 * test-scoped variable and pass it to `revokeDeviceGrantBackstop`, which
 * treats a null id and a missing guardian token as reportable outcomes rather
 * than as nothing to do.
 *
 * #CRITICAL: security: a failed revoke used to be observable only through a
 * `console.warn` line. Playwright's serial-block retry spawns a fresh worker
 * process on the first failure, so a failed first attempt leaks its own
 * grant, the retry mints and cleanly revokes a NEW one, and the file reports
 * "flaky" rather than "failed": the job exits 0 and the console line is
 * never read by anything. Every path that leaves a grant live now also
 * appends a machine-readable record to `test-results/leaked-device-grants.jsonl`
 * (see `recordLeakedGrant` below), which `.github/workflows/e2e-staging.yml`
 * reads in a dedicated `if: always()` step and fails the job on.
 * #VERIFY: seed that file locally and confirm the workflow's leak-check step
 * exits non-zero; confirm it exits zero on a run that produced no file.
 */

/** Shape persisted by the frontend under `localStorage['device_grant']`. */
const DEVICE_GRANT_KEY = 'device_grant'

/**
 * Append-only leak ledger, one JSON object per line. Lives under
 * `test-results/`, already gitignored and already the directory Playwright
 * writes trace output to, so no new top-level artifact path needs wiring
 * into CI upload/cleanup steps.
 */
const LEAK_LOG_PATH = path.join(process.cwd(), 'test-results', 'leaked-device-grants.jsonl')

interface LeakedGrantRecord {
  grantId: string
  specLabel: string
  detail: string
  timestamp: string
}

/**
 * Records a grant this teardown could not confirm as revoked.
 *
 * #CRITICAL: external resource: the write itself must never throw. This
 * function runs inside a teardown path that is already reporting a problem;
 * a filesystem error here must not replace that signal with a new,
 * unrelated one. Both `mkdir` (directory may not exist on a fresh checkout)
 * and `appendFile` are wrapped, and any failure degrades to the existing
 * `console.warn` only, never to a thrown error.
 * #VERIFY: the CI leak-check step (`.github/workflows/e2e-staging.yml`)
 * treats a missing file as "nothing leaked", so a write failure here is
 * fail-open for the deterministic check too; the `console.warn` in the
 * caller is what remains as a human-visible signal in that narrow case.
 */
async function recordLeakedGrant(record: LeakedGrantRecord): Promise<void> {
  try {
    await mkdir(path.dirname(LEAK_LOG_PATH), { recursive: true })
    await appendFile(LEAK_LOG_PATH, `${JSON.stringify(record)}\n`, 'utf8')
  } catch (err) {
    console.warn(`could not record leaked device grant to ${LEAK_LOG_PATH}: ${String(err)}`)
  }
}

/**
 * Reads the persisted grant id immediately after a mint.
 *
 * Call this from the authorize test, while the record still exists. Returns
 * null when nothing is stored or the payload carries no string id, which the
 * caller should assert on so a shape change fails loudly instead of quietly
 * disarming the backstop.
 */
export async function readPersistedGrantId(page: Page): Promise<string | null> {
  const raw = await page.evaluate((key) => window.localStorage.getItem(key), DEVICE_GRANT_KEY)
  if (raw === null) {
    return null
  }
  try {
    const grant = JSON.parse(raw) as { id?: unknown }
    return typeof grant.id === 'string' && grant.id.length > 0 ? grant.id : null
  } catch {
    return null
  }
}

/**
 * Best-effort revoke of a grant minted by this spec, for the case where the
 * explicit revoke test was skipped.
 *
 * Never throws: teardown runs after a failure has already been recorded, and
 * masking that failure with a cleanup error would hide the real cause. Every
 * path that leaves a grant live instead warns with the id, so an operator can
 * finish the job by hand.
 *
 * @param page - The spec's shared page, still on the app origin.
 * @param grantId - The id captured at mint time, or null if none was captured.
 * @param specLabel - Log prefix identifying the calling spec.
 */
export async function revokeDeviceGrantBackstop(
  page: Page,
  grantId: string | null,
  specLabel: string
): Promise<void> {
  if (grantId === null) {
    // No mint happened, or the mint test failed before capturing the id. The
    // former is the common case (a beforeAll sign-in failure) and leaves
    // nothing live; the latter cannot be cleaned up from here.
    //
    // #EDGE: security: this second case (a mint that happened but was never
    // captured) is not recordable as a leak: recordLeakedGrant requires a
    // grant id, and by construction none was captured here. It is not a gap
    // in the deterministic check, because the mint test's own assertion
    // (`readPersistedGrantId(...).not.toBeNull()`) already fails that test
    // whenever a mint leaves no id behind, which fails the job on its own.
    // #VERIFY: if that assertion is ever weakened or removed, this path
    // becomes a silent leak again; keep the two changes coupled.
    return
  }

  let outcome: { ok: boolean; status: number; reason: string } = {
    ok: false,
    status: 0,
    reason: 'teardown could not run in the page context',
  }
  try {
    outcome = await page.evaluate(
      async ([id, key]) => {
        const token = window.localStorage.getItem('auth_token')
        if (token === null) {
          return { ok: false, status: 0, reason: 'no guardian auth_token in localStorage' }
        }
        try {
          const res = await fetch(`/api/v1/device-grants/${id}`, {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${token}` },
          })
          // 404 means it is already gone, which is the desired end state.
          return { ok: res.ok || res.status === 404, status: res.status, reason: '' }
        } catch (err) {
          return { ok: false, status: 0, reason: `DELETE threw: ${String(err)}` }
        } finally {
          window.localStorage.removeItem(key)
        }
      },
      [grantId, DEVICE_GRANT_KEY] as const
    )
  } catch {
    /* page already closed / evaluate unavailable: fall through to the warning */
  }

  if (!outcome.ok) {
    const detail = outcome.reason.length > 0 ? outcome.reason : `HTTP ${outcome.status}`
    console.warn(
      `${specLabel} backstop device-grant revoke did not confirm (${detail}). ` +
        `Device grant ${grantId} may still be live on staging; revoke it manually.`
    )
    // Keep this never-throwing: recordLeakedGrant already swallows its own
    // errors, so this call cannot itself introduce a new teardown failure.
    await recordLeakedGrant({
      grantId,
      specLabel,
      detail,
      timestamp: new Date().toISOString(),
    })
  }
}
