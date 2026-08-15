/**
 * The guardian login page's h1.
 *
 * A standalone module, mirroring `landing/headline.ts`, and standalone for a
 * concrete reason: the Playwright specs that assert this string run in Node,
 * so importing it from `LoginPage.tsx` would pull the whole component into
 * their module graph, along with `./guardian.css` and the Supabase client.
 *
 * Shared because every landing-funnel CTA lands on that page, so this string
 * is pinned by unit, e2e, and production-canary specs at once. A copy change
 * that updated only some of them would fail against live production rather
 * than in CI.
 */
export const LOGIN_HEADLINE = 'Sign in or create your account'
