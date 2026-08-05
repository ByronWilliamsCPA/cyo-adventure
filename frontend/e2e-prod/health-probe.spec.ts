import { expect, test } from '@playwright/test'

/**
 * Guards register item UW-L04 against live production. No credentials needed
 * (uses Playwright's `request` fixture, not a browser page): every assertion
 * here is a plain unauthenticated GET.
 *
 * Background (see `frontend/nginx.conf` and `src/cyo_adventure/app.py`):
 * `frontend/nginx.conf` proxies only `location /api/` to the FastAPI backend.
 * The health router used to be mounted at bare `/health/*` (outside that
 * prefix, so unreachable through the ingress) while nginx separately answered
 * `location /health` with a hardcoded `return 200 'OK'` stub. The result:
 * `https://cyo.williamshome.family/health/ready` returned 200 `text/plain`
 * straight from nginx, FastAPI's readiness logic (database connectivity,
 * privilege checks, etc.) never ran, and that false pass sat in the R1 live
 * checklist as a "verified" readiness check for a month. The fix mounts the
 * health router a second time under `/api/v1` (the canonical, reachable path)
 * and nginx now returns 404 for `/health` instead of shadowing it.
 *
 * #CRITICAL: external resources: this spec asserts the POST-FIX state of a
 * live, separately-deployed system (the frontend nginx image and the backend
 * container both have to be running the fixed config). If this fails
 * immediately after the fix PR merges to main, the most likely cause is that
 * production has not been redeployed yet, not that the test is wrong.
 * #VERIFY: check the deployed image tags/digests in the homelab-infra compose
 * stack before changing this spec; redeploy first.
 */
test.describe('platform health, unauthenticated', () => {
  test('the canonical readiness endpoint answers as real FastAPI JSON', async ({ request }) => {
    const res = await request.get('/api/v1/health/ready')
    // Three assertions, each closing a gap the others leave open: status alone
    // is forgeable by a static 200 stub (exactly what nginx used to serve at
    // the un-prefixed path); content-type alone would also accept a JSON 404
    // error body from FastAPI itself. Only the three together prove this is a
    // live 200 from the readiness handler.
    expect(res.status()).toBe(200)
    expect(res.headers()['content-type']).toContain('application/json')
    const body = (await res.json()) as Record<string, unknown>
    expect(body).toHaveProperty('status')
    expect(body).toHaveProperty('checks')
    // Not `typeof body.checks === 'object'`, which is also true of null: a
    // handler returning `{"checks": null}` would satisfy that and prove
    // nothing about the readiness payload's shape.
    expect(body.checks).toBeInstanceOf(Object)
  })

  test('the old shadowed path returns exactly 404 (nginx no longer stubs it)', async ({
    request,
  }) => {
    const res = await request.get('/health/ready')
    // Assert 404 exactly, not merely "not 200". `not.toBe(200)` would be
    // satisfied by a 502 or a 301, neither of which shows nginx replaced the
    // stub with the `return 404` the fix installed: a whole-site outage would
    // pass this test while proving nothing. 404 is what frontend/nginx.conf's
    // `location /health` block returns, so if that block is ever deleted this
    // fails on the SPA fallback's 200 text/html rather than quietly accepting
    // it.
    expect(res.status()).toBe(404)
  })

  test('the nginx-only diagnostic control answers, proving nginx itself is up', async ({
    request,
  }) => {
    // This is the failure-mode discriminator for the first test above: if
    // that one fails, checking THIS one tells you whether to look at "the
    // backend is unreachable through the ingress" (this still passes) or "the
    // whole site is down" (this fails too). Without it, a failure of the
    // canonical check alone is ambiguous between those two very different
    // causes.
    const res = await request.get('/nginx-health')
    expect(res.status()).toBe(200)
    expect(res.headers()['content-type']).toContain('text/plain')
  })
})
