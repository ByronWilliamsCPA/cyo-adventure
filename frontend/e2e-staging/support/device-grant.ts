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
 * #VERIFY: capture the id at mint time via `readPersistedGrantId` into the
 * spec's `DeviceGrantMintState` and pass that state to
 * `revokeDeviceGrantBackstop`, which treats a null id, an uncaptured id, and
 * a missing guardian token as reportable outcomes rather than as nothing to do.
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
 *
 * #CRITICAL: security: this ledger is SELF-REPORTED teardown state, so it can
 * only describe runs where teardown actually ran. A worker killed after the
 * mint (OOM, browser crash, "Worker process exited unexpectedly"), an
 * `afterAll` that blows the 30s tier timeout before reaching
 * `recordLeakedGrant`, and the fail-open inside `recordLeakedGrant` itself all
 * leave a live grant and no ledger line.
 * #VERIFY: the ledger is the DIAGNOSTIC (it names which spec leaked, which no
 * external check can tell you) and must never be the only signal. The
 * authoritative backstop is the post-run sweep in
 * `e2e-staging-sweep/device-grant-sweep.spec.ts`, which asks staging itself
 * whether the test family holds any active grant. Keep both.
 */

/** Shape persisted by the frontend under `localStorage['device_grant']`. */
const DEVICE_GRANT_KEY = 'device_grant'

/**
 * Append-only leak ledger, one JSON object per line.
 *
 * #CRITICAL: external resource: this path must land exactly where the CI
 * leak-check step reads it, or a leak is recorded somewhere nothing looks and
 * the gate fails open to "no leaks". Playwright resolves a config's default
 * `outputDir` relative to the CONFIG FILE's directory, NOT to `process.cwd()`;
 * the two only coincide when the tier is launched from `frontend/` (which the
 * workflow does via `working-directory: ./frontend`, and a repo-root
 * invocation does not). Deriving it from this module's own location tracks
 * Playwright's rule instead of the caller's shell: this file lives at
 * `frontend/e2e-staging/support/`, so `../..` is `frontend/`, the directory
 * holding `playwright.e2e-staging.config.ts`.
 * #VERIFY: if the config file or this module ever moves, re-derive the `../..`
 * hops together; `npm run test:e2e:staging` from the repo root must still put
 * the ledger under `frontend/test-results/`.
 */
const LEAK_LOG_PATH = path.resolve(
  import.meta.dirname,
  '../../test-results/leaked-device-grants.jsonl'
)

/**
 * Fixed-vocabulary `detail` for the case where a mint happened but its id was
 * never captured. Deliberately actionable: with no id there is nothing to
 * DELETE, so the only remedy is a human (or the post-run sweep) looking at the
 * test family's device-grant list.
 */
const UNCAPTURED_MINT_DETAIL =
  'a device grant was minted but its id was never captured, so teardown had ' +
  'nothing to revoke; sweep the staging test family device-grant list by hand'

interface LeakedGrantRecord {
  /**
   * The grant's DB row id, or null when a mint happened but the id was never
   * captured. Never a token: only the row id is safe to print into CI logs.
   */
  grantId: string | null
  specLabel: string
  detail: string
  timestamp: string
}

/**
 * Per-describe-block record of whether this spec may have left a grant live.
 *
 * Two fields rather than one nullable id, because "no mint happened" and "a
 * mint happened but produced no id" are different outcomes with the same
 * `grantId === null` shape, and only the second is a leak.
 */
export interface DeviceGrantMintState {
  /**
   * Set to true immediately BEFORE the click that mints, and back to false
   * only once the grant is known to be revoked. From the moment it is true a
   * grant may exist server-side, whether or not this process ever learns its
   * id.
   */
  mintAttempted: boolean
  /** The id captured at mint time, or null if none was captured. */
  grantId: string | null
}

/** Builds the initial "nothing minted yet" state for a describe block. */
export function createDeviceGrantMintState(): DeviceGrantMintState {
  return { mintAttempted: false, grantId: null }
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
 * fail-open for that check. That fail-open is why the workflow also runs the
 * post-run sweep against staging's own device-grant list, which does not read
 * this file and therefore does not share its failure modes.
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
 * path that leaves a grant live instead warns with what it knows and appends a
 * ledger record, so an operator can finish the job by hand.
 *
 * @param page - The spec's shared page, still on the app origin.
 * @param state - The describe block's mint state (see `DeviceGrantMintState`).
 * @param specLabel - Log prefix identifying the calling spec.
 */
export async function revokeDeviceGrantBackstop(
  page: Page,
  state: DeviceGrantMintState,
  specLabel: string
): Promise<void> {
  if (state.grantId === null) {
    if (!state.mintAttempted) {
      // No mint was ever started (the common case is a beforeAll sign-in
      // failure), so nothing is live and there is nothing to record.
      return
    }
    // #CRITICAL: security: a mint that happened but was never captured. The
    // POST can succeed server-side and still leave `grantId` null here: the
    // visibility assertion after the click can time out, or a device-grant
    // 401 can make useApi.ts's interceptor call `clearDeviceGrant()` before
    // `readPersistedGrantId` runs. This IS a leak and is recorded as one with
    // a null id.
    //
    // It is recorded rather than left to the mint test's own
    // `expect(readPersistedGrantId(...)).not.toBeNull()` assertion, because
    // that assertion does not fail the JOB: a failed attempt that passes on
    // retry is reported "flaky" and the run still exits 0, which is exactly
    // the retry-swallow this ledger exists to close. Relying on it here would
    // have been circular.
    // #VERIFY: the recorded id is null, so nothing can be revoked from the
    // ledger alone; the post-run sweep in `e2e-staging-sweep/` is what
    // actually proves the family is clean. Keep the two coupled.
    console.warn(
      `${specLabel} minted a device grant whose id was never captured. ` +
        `A grant may still be live on staging for the test family; ` +
        `list and revoke it manually.`
    )
    await recordLeakedGrant({
      grantId: null,
      specLabel,
      detail: UNCAPTURED_MINT_DETAIL,
      timestamp: new Date().toISOString(),
    })
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
      [state.grantId, DEVICE_GRANT_KEY] as const
    )
  } catch {
    /* page already closed / evaluate unavailable: fall through to the warning */
  }

  if (!outcome.ok) {
    const detail = outcome.reason.length > 0 ? outcome.reason : `HTTP ${outcome.status}`
    console.warn(
      `${specLabel} backstop device-grant revoke did not confirm (${detail}). ` +
        `Device grant ${state.grantId} may still be live on staging; revoke it manually.`
    )
    // Keep this never-throwing: recordLeakedGrant already swallows its own
    // errors, so this call cannot itself introduce a new teardown failure.
    await recordLeakedGrant({
      grantId: state.grantId,
      specLabel,
      detail,
      timestamp: new Date().toISOString(),
    })
  }
}
