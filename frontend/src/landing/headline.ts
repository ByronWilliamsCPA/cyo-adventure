/**
 * The landing page's h1, exported once so the unit test, the landing e2e
 * spec, the a11y readiness assertion, and the production smoke test all pin
 * the same string instead of carrying five drift-prone copies (a copy tweak
 * previously had to be repeated in every one of them or it broke the
 * required frontend-e2e gate). index.html's og/twitter titles remain
 * literals by necessity; keep them in sync by hand when this changes.
 */
export const LANDING_HEADLINE = 'They pick the path. You approve every page.'
