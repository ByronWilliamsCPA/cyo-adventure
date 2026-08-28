/**
 * Checked-in walkable-route list for the usersim tier.
 *
 * This is the ground truth a later task's random walk consults to know
 * which paths exist and which persona may walk each one.
 * frontend/src/router.usersim-manifest.test.ts asserts this list stays in
 * sync with the real route tree in frontend/src/router.tsx, in both
 * directions: every reachable leaf path has an entry here, and every entry
 * here corresponds to a real leaf path.
 *
 * Parameter values reuse the fixtures the existing mocked E2E tier's
 * session helpers already seed (frontend/e2e/support/auth.ts's DEFAULT_ME),
 * so a walk built on this manifest agrees with the session personas.ts
 * establishes. Where no such fixture exists (storybookId, version), a fixed
 * synthetic value is used instead, called out below.
 */
import type { PersonaId } from './personas'

export interface RouteManifestEntry {
  /** Exactly as it appears as a leaf path in frontend/src/router.tsx's `routes` export. */
  path: string
  /**
   * Personas whose seeded session (personas.ts) renders this route without
   * being redirected elsewhere. Empty when no current persona's session
   * reaches it; see the per-entry note for why.
   */
  walkers: readonly PersonaId[]
  /**
   * Concrete substitutions for this path's `:param` segments (the param
   * name, without the leading colon). Omitted for paths with no parameters.
   */
  params?: Readonly<Record<string, string>>
  /** Why this entry has the walkers/params it does. */
  note: string
}

// DEFAULT_ME.profile_ids[0] (frontend/e2e/support/auth.ts). Reused for every
// :profileId occurrence so every parameterised route agrees with the same
// mocked session.
const PROFILE_ID = 'p1'

// No fixture for a storybook id or version exists in DEFAULT_ME or
// DEFAULT_DEVICE_GRANT (frontend/e2e/support/auth.ts); these are synthetic
// placeholders, not fixture values pulled from an existing helper. A later
// task wiring an actual reader/review response mock decides whether either
// value needs to match a specific mocked body.
const STORYBOOK_ID = 'sb-1'
const STORYBOOK_VERSION = '1'

export const ROUTE_MANIFEST: readonly RouteManifestEntry[] = [
  // ---- Public: outside every gate (routes.ts PRIVACY_PATH/SUPPORT_PATH
  // doc comment; router.test.tsx's public-route assertions). ----
  {
    path: '/',
    walkers: ['kid', 'guardian', 'admin'],
    note: 'Landing page. Outside every gate; renders identically regardless of session.',
  },
  {
    path: '/privacy',
    walkers: ['kid', 'guardian', 'admin'],
    note: 'Public privacy policy. routes.ts #CRITICAL security: must stay outside every gate (KWS parent verification, ADR-018 D1).',
  },
  {
    path: '/support',
    walkers: ['kid', 'guardian', 'admin'],
    note: 'Public support page. Same gate-free placement as /privacy, for the same reason.',
  },

  // ---- Kid surface: gated by DeviceAuthorizedRoute only. ----
  {
    path: '/kids',
    walkers: ['kid'],
    note: 'Kid profile picker. Gated by DeviceAuthorizedRoute; only the kid persona (seedDeviceGrant) passes it.',
  },
  {
    path: '/library/:profileId',
    walkers: ['kid'],
    params: { profileId: PROFILE_ID },
    note: 'Same DeviceAuthorizedRoute gate as /kids.',
  },
  {
    path: '/read/:profileId/:storybookId/:version',
    walkers: ['kid'],
    params: { profileId: PROFILE_ID, storybookId: STORYBOOK_ID, version: STORYBOOK_VERSION },
    note: 'Same DeviceAuthorizedRoute gate as /kids.',
  },

  // ---- Guardian-tree interstitials: sit inside GuardianAuthLayout but
  // outside AdultGate/ProtectedRoute (see the comment above each route in
  // router.tsx). None of the three current personas' seeded sessions
  // produce the AuthStatus each of these exists for, so no persona
  // currently walks them; `walkers` is deliberately empty rather than
  // guessed at. See personas.ts for the one interstitial (/guardian/login)
  // that IS a recognised terminal, for the kid persona specifically. ----
  {
    path: '/guardian/login',
    walkers: [],
    note: 'Reached by a signed-out visitor, or by the kid persona\'s "Ask a grown-up" link (personas.ts). No current persona seeds a signed-out session here.',
  },
  {
    path: '/guardian/awaiting-approval',
    walkers: [],
    note: "AuthStatus 'awaiting-approval' interstitial; seedGuardianSession's mocked onboarding response is always already-active, so no current persona reaches it.",
  },
  {
    path: '/guardian/verify',
    walkers: [],
    note: "AuthStatus 'needs-verification' interstitial (ADR-018 D1); seedGuardianSession's mocked onboarding response is always already-verified.",
  },
  {
    path: '/guardian/consent',
    walkers: [],
    note: "AuthStatus 'needs-consent' interstitial; seedGuardianSession's mocked onboarding response always has consent_recorded: true.",
  },
  {
    path: '/guardian/unavailable',
    walkers: [],
    note: "AuthStatus 'backend-unreachable' interstitial (#452); no current persona's setup simulates an unreachable backend.",
  },

  // ---- Guardian console: gated by GuardianAuthLayout -> AdultGate ->
  // ProtectedRoute(allowedRoles: ['guardian', 'admin']). An admin persona
  // passes this gate too (router.tsx's comment on GUARDIAN_CONSOLE_PATH: "a
  // dual-role adult lives here day-to-day, and an admin-only adult who
  // lands here sees the family home's pointer into the admin console"). ----
  {
    path: '/guardian',
    walkers: ['guardian', 'admin'],
    note: 'Guardian console home (ConsolePage). allowedRoles includes admin.',
  },
  {
    path: '/guardian/intake',
    walkers: ['guardian', 'admin'],
    note: 'Same guardian-console gate as /guardian.',
  },
  {
    path: '/guardian/requests',
    walkers: ['guardian', 'admin'],
    note: 'Same guardian-console gate as /guardian.',
  },
  {
    path: '/guardian/review/:storybookId',
    walkers: ['guardian', 'admin'],
    params: { storybookId: STORYBOOK_ID },
    note: 'Same guardian-console gate as /guardian.',
  },
  {
    path: '/guardian/reading',
    walkers: ['guardian', 'admin'],
    note: 'Same guardian-console gate as /guardian.',
  },
  {
    path: '/guardian/books',
    walkers: ['guardian', 'admin'],
    note: 'Same guardian-console gate as /guardian.',
  },
  {
    path: '/guardian/profiles',
    walkers: ['guardian', 'admin'],
    note: 'Same guardian-console gate as /guardian.',
  },
  {
    path: '/guardian/connections',
    walkers: ['guardian', 'admin'],
    note: 'Same guardian-console gate as /guardian.',
  },
  {
    path: '/guardian/devices',
    walkers: ['guardian', 'admin'],
    note: 'Same guardian-console gate as /guardian.',
  },
  {
    path: '/guardian/privacy',
    walkers: ['guardian', 'admin'],
    note: 'G11 trust surface, signed-in only (distinct from the public /privacy). Same guardian-console gate as /guardian.',
  },
  {
    path: '/guardian/preview/:profileId',
    walkers: ['guardian', 'admin'],
    params: { profileId: PROFILE_ID },
    note: 'Same guardian-console gate as /guardian.',
  },

  // ---- Admin console: gated by GuardianAuthLayout -> AdultGate ->
  // ProtectedRoute(allowedRoles: ['admin']). A plain guardian is denied and
  // redirected back to GUARDIAN_CONSOLE_PATH, so 'guardian' is deliberately
  // excluded from every entry below. ----
  {
    path: '/admin',
    walkers: ['admin'],
    note: 'Admin console home (AdminConsolePage). allowedRoles is admin-only.',
  },
  {
    path: '/admin/library',
    walkers: ['admin'],
    note: 'Same admin-console gate as /admin.',
  },
  {
    path: '/admin/requests',
    walkers: ['admin'],
    note: 'Same admin-console gate as /admin.',
  },
  {
    path: '/admin/review/:storybookId',
    walkers: ['admin'],
    params: { storybookId: STORYBOOK_ID },
    note: 'Same admin-console gate as /admin.',
  },
  {
    path: '/admin/moderation-thresholds',
    walkers: ['admin'],
    note: 'Same admin-console gate as /admin.',
  },
  {
    path: '/admin/moderation-dashboard',
    walkers: ['admin'],
    note: 'Same admin-console gate as /admin.',
  },
  {
    path: '/admin/authoring-queue',
    walkers: ['admin'],
    note: 'Same admin-console gate as /admin.',
  },
  {
    path: '/admin/provider-allowlist',
    walkers: ['admin'],
    note: 'Same admin-console gate as /admin.',
  },
  {
    path: '/admin/users',
    walkers: ['admin'],
    note: 'Same admin-console gate as /admin.',
  },
  {
    path: '/admin/audit',
    walkers: ['admin'],
    note: 'Same admin-console gate as /admin.',
  },
]

/**
 * Substitute this entry's params into its path, turning e.g.
 * '/library/:profileId' into '/library/p1'. Throws if a required param is
 * missing: a walk navigating to a literal ':profileId' is a manifest bug to
 * fix, not a runtime condition to degrade gracefully from.
 */
export function toConcretePath(entry: RouteManifestEntry): string {
  return entry.path.replace(/:([A-Za-z0-9_]+)/g, (matched, name: string) => {
    const value = entry.params?.[name]
    if (value === undefined) {
      throw new Error(`route-manifest: ${entry.path} has no param value for ${matched}`)
    }
    return value
  })
}
