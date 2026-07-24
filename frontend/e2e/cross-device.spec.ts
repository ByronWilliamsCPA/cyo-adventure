import { defineResponsiveChecks } from './support/responsiveChecks'

/**
 * Real device/browser sweep (npm run test:e2e:cross-device): the same
 * structural checks as responsive.spec.ts, run once per project at that
 * project's OWN native viewport/UA/engine rather than a swept size. Matched
 * by the cross-device-mobile/cross-device-tablet/cross-browser-mobile-
 * safari/cross-browser-firefox projects in playwright.config.ts, which pick
 * real Playwright device descriptors (Pixel 7, iPad (gen 7), iPhone 14,
 * Desktop Firefox) -- iPad/iPhone default to the webkit engine, matching
 * actual Mobile Safari, and Desktop Firefox is the only non-Chromium
 * desktop engine covered anywhere in this repo's e2e suite.
 *
 * Deliberately a separate file from responsive.spec.ts rather than the same
 * file reused across projects: responsive.spec.ts overrides the viewport
 * per breakpoint via `test.use({ viewport })`, which would silently
 * multiply into nonsensical combinations here (e.g. the iPad project's
 * webkit engine and touch/UA forced down to a 390px phone-sized viewport).
 * This file takes each project's device descriptor as-is.
 */
defineResponsiveChecks()
