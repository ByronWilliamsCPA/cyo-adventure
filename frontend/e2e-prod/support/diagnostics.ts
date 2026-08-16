/**
 * Failure diagnostics for the production tier.
 *
 * Why this exists: `e2e-prod` ran red from 2026-08-05 (issue #623) with every
 * authenticated console assertion reporting the same thing --
 * `expect(getByRole('heading', {level: 1})).toBeVisible() ... element(s) not
 * found` -- and nothing else. That message names what was ABSENT and never
 * what was present, so eleven consecutive scheduled runs produced no evidence
 * anyone could act on, and the traces that would have answered it expire after
 * seven days.
 *
 * The absence is genuinely puzzling on its own: `ConsolePage`, `BooksPage` and
 * `ProfilesPage` have no loading or error early-return, so each renders its
 * `<h1>` unconditionally once mounted, and sign-in cannot silently have failed
 * (`signInAsProdTestAdmin` throws on a login alert AND validates that the
 * landing path is under `/guardian` or `/admin`). Something upstream of the
 * page is therefore rendering instead -- a route-level Suspense fallback, a
 * redirect, a gate, or an interstitial -- and which of those it is decides
 * whether the fault is a stale deploy, a backend outage, or a product change
 * the tier has not caught up with.
 *
 * So: capture the page's actual state at the moment of failure and put it in
 * the assertion message, where the alert issue and the run log both show it
 * without anyone downloading a trace.
 */

import { expect, type Page } from '@playwright/test'

/** What the page actually showed, gathered for a failure message. */
interface PageState {
  url: string
  title: string
  headings: string[]
  alerts: string[]
  statuses: string[]
  routeFallbackPresent: boolean
  bodyStart: string
}

async function capturePageState(page: Page): Promise<PageState> {
  // Every read is best-effort and individually guarded: this runs only on a
  // path that is already failing, and a diagnostic that throws would replace
  // the real assertion error with its own, which is strictly worse than a
  // partial capture.
  const safe = async <T>(read: () => Promise<T>, fallback: T): Promise<T> => {
    try {
      return await read()
    } catch {
      return fallback
    }
  }
  return {
    // Synchronous in Playwright, so it needs no guard and no await.
    url: page.url(),
    title: await safe(() => page.title(), '<unavailable>'),
    headings: await safe(() => page.locator('h1, h2').allInnerTexts(), ['<unavailable>']),
    alerts: await safe(() => page.getByRole('alert').allInnerTexts(), ['<unavailable>']),
    statuses: await safe(() => page.getByRole('status').allInnerTexts(), ['<unavailable>']),
    // routeElements.tsx renders `<LoadingStatus className="route-fallback">`
    // while a lazy route chunk loads. Present here means the chunk never
    // resolved, which points at the deployed bundle (a stale index.html
    // referencing hashed chunks a redeploy removed) rather than at the app.
    routeFallbackPresent: await safe(
      async () => (await page.locator('.route-fallback').count()) > 0,
      false
    ),
    bodyStart: await safe(
      async () => (await page.locator('body').innerText()).slice(0, 400),
      '<unavailable>'
    ),
  }
}

function formatPageState(state: PageState): string {
  const list = (values: string[]) =>
    values.length === 0 ? '(none)' : values.map((v) => JSON.stringify(v)).join(', ')
  return [
    `url: ${state.url}`,
    `title: ${JSON.stringify(state.title)}`,
    `headings (h1/h2): ${list(state.headings)}`,
    `role=alert: ${list(state.alerts)}`,
    `role=status: ${list(state.statuses)}`,
    `lazy route fallback still mounted: ${state.routeFallbackPresent}`,
    `body text (first 400 chars): ${JSON.stringify(state.bodyStart)}`,
  ].join('\n  ')
}

/**
 * Assert an adult console's `<h1>` is visible, and on failure say what the
 * page actually showed.
 *
 * Behaviour on the happy path is identical to the bare
 * `expect(getByRole('heading', {name, level: 1})).toBeVisible()` it replaces,
 * including the same default timeout; the extra work happens only once the
 * assertion has already failed.
 */
export async function expectConsoleHeading(page: Page, name: string): Promise<void> {
  const heading = page.getByRole('heading', { name, level: 1 })
  try {
    await expect(heading).toBeVisible()
  } catch (error) {
    const state = await capturePageState(page)
    throw new Error(
      `Expected the <h1> "${name}" to be visible, and it was not.\n` +
        `  This page renders that heading unconditionally once it mounts, so its absence means ` +
        `something upstream rendered instead. What was actually on the page:\n  ` +
        formatPageState(state),
      // Keep Playwright's own assertion error (with its call log) attached
      // rather than flattening it into this message.
      { cause: error }
    )
  }
}
