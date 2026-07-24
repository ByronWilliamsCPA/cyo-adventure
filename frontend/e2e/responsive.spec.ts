import { test } from '@playwright/test'

import { defineResponsiveChecks } from './support/responsiveChecks'

/**
 * Responsive breakpoint sweep: the same Desktop Chrome engine (this file
 * only ever runs under the `chromium` project) at three viewport sizes, to
 * catch layout bugs that only appear at specific widths regardless of
 * engine or device. See cross-device.spec.ts for the complementary
 * check -- real device/browser engines, each at its own native viewport.
 *
 * A story: library.css's shelf grid used `auto-fill`, which reserves empty
 * grid tracks instead of collapsing them, so a shelf with only one book
 * left a dead empty column beside it at any viewport between one and two
 * 16rem cards (roughly 640-1280px content width, i.e. exactly tablet
 * portrait and common desktop widths) -- not narrow enough to be memorable
 * as a "mobile bug" and not wide enough to be dismissed as desktop-only.
 * Similarly, guardian.css's admin/guardian table overflow-x escape valve was
 * scoped to a max-width: 640px breakpoint, leaving tablet-portrait widths
 * (641-900px) with no scroll fallback for a table whose content is wider
 * than the viewport. Neither bug showed up testing only a single desktop
 * viewport size.
 */

const VIEWPORTS = {
  desktop: { width: 1920, height: 1080 },
  tablet: { width: 768, height: 1024 }, // iPad Mini / iPad (gen 7) portrait
  mobile: { width: 390, height: 844 }, // iPhone 14
}

for (const [sizeName, viewport] of Object.entries(VIEWPORTS)) {
  test.describe(`@ ${sizeName}`, () => {
    test.use({ viewport })
    defineResponsiveChecks()
  })
}
