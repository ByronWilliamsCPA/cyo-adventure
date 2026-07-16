import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'

import { mockEmptyConsole, mockMe, seedDeviceGrant, seedGuardianSession } from './support/auth'

/**
 * Automated accessibility smoke, WCAG 2.1 A/AA rules via axe-core, across one
 * representative page per surface (landing, kid picker, kid library
 * populated/empty, guardian console, admin console). This is a floor, not a
 * substitute for manual testing: axe catches programmatically detectable
 * issues (missing labels, contrast, ARIA misuse) but not things like
 * keyboard-trap logic or whether an alternative text is actually meaningful.
 */

const TWO_PROFILES = {
  profiles: [
    {
      id: 'child-fox',
      display_name: 'Remy',
      age_band: '5-8',
      reading_level_cap: 3,
      avatar: 'fox',
      tts_enabled: false,
      created_at: '2026-01-01T00:00:00Z',
    },
  ],
}

const ONE_STORY = {
  stories: [
    {
      id: 's1',
      title: 'The Lantern',
      version: 2,
      age_band: '6-8',
      tier: 1,
      reading_level_target: 2,
      node_count: 10,
      rating: null,
      progress: null,
    },
  ],
}

async function assertNoViolations(page: Page) {
  // Scoped to WCAG 2.1 A/AA, matching this file's stated intent. axe's full
  // default ruleset also includes "best-practice" rules (e.g. requiring a
  // <main> landmark or exactly one <h1>) that are worth fixing but are not
  // WCAG conformance failures; keeping the gate to WCAG tags avoids drowning
  // real conformance regressions in opinionated-but-optional findings.
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze()
  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([])
}

test('landing page has no detectable accessibility violations', async ({ page }) => {
  await page.goto('/')
  await assertNoViolations(page)
})

test('kid profile picker has no detectable accessibility violations', async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
  await seedDeviceGrant(context)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  await page.goto('/kids')
  await expect(page.getByRole('heading', { name: "Who's reading?" })).toBeVisible()
  await assertNoViolations(page)
})

test('kid library (populated) has no detectable accessibility violations', async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
  await seedDeviceGrant(context)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: ONE_STORY }))
  await page.goto('/library/child-fox')
  await expect(page.getByRole('heading', { name: 'My Books' })).toBeVisible()
  await assertNoViolations(page)
})

test('kid library (empty) has no detectable accessibility violations', async ({ page, context }) => {
  await context.addInitScript(() => {
    window.localStorage.setItem('auth_token', 'child-fox')
  })
  await seedDeviceGrant(context)
  await page.route('**/api/v1/profiles', (route) => route.fulfill({ json: TWO_PROFILES }))
  await page.route('**/api/v1/library*', (route) => route.fulfill({ json: { stories: [] } }))
  await page.goto('/library/child-fox')
  await expect(page.getByRole('heading', { name: 'No books yet' })).toBeVisible()
  await assertNoViolations(page)
})

test('guardian console has no detectable accessibility violations', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'guardian' })
  await mockEmptyConsole(page)
  await page.goto('/guardian')
  await expect(page.getByRole('heading', { name: 'Family console' })).toBeVisible()
  await assertNoViolations(page)
})

test('admin console has no detectable accessibility violations', async ({ page, context }) => {
  await seedGuardianSession(context)
  await mockMe(page, { role: 'admin' })
  await mockEmptyConsole(page)
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
  await assertNoViolations(page)
})
