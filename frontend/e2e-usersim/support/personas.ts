/**
 * Persona substrate for the usersim walk tier: one entry per persona (kid,
 * guardian, admin), each pairing a session-setup routine with an entry
 * point and a small, explicitly justified list of recognised terminals.
 *
 * Session setup is never reimplemented here: kid/guardian/admin sessions
 * are seeded with the same helpers the existing mocked E2E tier already
 * uses (frontend/e2e/support/auth.ts). route-manifest.ts (this directory)
 * carries the complementary per-route walkability data.
 *
 * PLAN CORRECTION (see the task brief for the full account): recognised
 * terminals are NOT "the auth gates K0, G0, A0 already define as legitimate
 * stops". K0/G0/A0 are scenario IDs in the Claude-for-Chrome naive-ux-check
 * skill's manual UX testing scenarios
 * (docs/superpowers/specs/2026-07-10-naive-ux-check-scenario-redesign-design.md,
 * lines 92-96); they are not auth-gate identifiers and define no terminal
 * set. The terminals below are instead derived directly from the real
 * route tree (frontend/src/router.tsx) and the real gate components, each
 * with a comment saying why it is a legitimate stop rather than a defect.
 *
 * Keep this list minimal: an over-broad terminal list silently disables the
 * dead-end invariant this whole tier exists to provide.
 */
import type { BrowserContext, Page } from '@playwright/test'

import { mockMe, seedDeviceGrant, seedGuardianSession } from '../../e2e/support/auth'
import {
  ADMIN_CONSOLE_PATH,
  GUARDIAN_CONSOLE_PATH,
  GUARDIAN_LOGIN_PATH,
  KID_PICKER_PATH,
} from '../../src/routes'

export type PersonaId = 'kid' | 'guardian' | 'admin'

export interface PersonaTerminal {
  /** A real path, present in route-manifest.ts. */
  path: string
  /** Why landing here is a legitimate stop for this persona, not a dead end the walk should flag. */
  reason: string
}

export interface Persona {
  id: PersonaId
  /** Seed the browser context/page so this persona's session exists before the walk starts. */
  setupSession(context: BrowserContext, page: Page): Promise<void>
  /** Where this persona's walk begins. */
  entryPath: string
  /** Auth gates this persona's session cannot pass. Landing on one of these is a legitimate stop, not a dead end. */
  terminals: readonly PersonaTerminal[]
}

const KID_PERSONA: Persona = {
  id: 'kid',
  async setupSession(context: BrowserContext, _page: Page): Promise<void> {
    await seedDeviceGrant(context)
  },
  entryPath: KID_PICKER_PATH,
  terminals: [
    {
      path: GUARDIAN_LOGIN_PATH,
      // Verified: frontend/src/kid/KidNav.tsx renders a persistent "Ask a
      // grown-up" link to GUARDIAN_LOGIN_PATH on every kid-surface page
      // (pinned by KidNav.test.tsx: "always offers a persistent Ask a
      // grown-up link to guardian login"). The kid persona's session here is
      // a device grant only, with no guardian auth token, so it cannot pass
      // GuardianAuthLayout/AdultGate from there. This is the product's own
      // intended escape hatch for a child, not a defect the dead-end
      // invariant should flag.
      reason:
        "KidNav's persistent 'Ask a grown-up' link leads here, and the kid " +
        'persona holds no guardian session, so it cannot proceed past this ' +
        'page under its own session. Intentional, per KidNav.tsx/KidNav.test.tsx.',
    },
  ],
}

const GUARDIAN_PERSONA: Persona = {
  id: 'guardian',
  async setupSession(context: BrowserContext, _page: Page): Promise<void> {
    await seedGuardianSession(context)
  },
  entryPath: GUARDIAN_CONSOLE_PATH,
  // Empty, deliberately: seedGuardianSession's mocked onboarding response is
  // always already-active/verified/consented (frontend/e2e/support/auth.ts,
  // DEFAULT_ONBOARDING_RESPONSE), so this persona's AuthStatus never becomes
  // one of the values the five guardian-tree interstitials exist for, and it
  // never lands on any of them. A stray link into /admin/* redirects back to
  // GUARDIAN_CONSOLE_PATH (ProtectedRoute's deniedRedirectTo), which is
  // already-walked, linked territory rather than a dead end, so it needs no
  // terminal entry either.
  terminals: [],
}

const ADMIN_PERSONA: Persona = {
  id: 'admin',
  async setupSession(context: BrowserContext, page: Page): Promise<void> {
    await seedGuardianSession(context)
    await mockMe(page, { role: 'admin' })
  },
  entryPath: ADMIN_CONSOLE_PATH,
  // Empty, for the same reason as the guardian persona above: a fully
  // provisioned session that never surfaces one of the five auth
  // interstitials. The guardian console's allowedRoles includes 'admin'
  // (router.tsx), so this persona has a walkable destination for every link
  // it can reach; there is no gate it hits that it cannot pass.
  terminals: [],
}

export const PERSONAS: readonly Persona[] = [KID_PERSONA, GUARDIAN_PERSONA, ADMIN_PERSONA]

export function getPersona(id: PersonaId): Persona {
  const persona = PERSONAS.find((candidate) => candidate.id === id)
  if (!persona) {
    throw new Error(`Unknown persona id: ${id}`)
  }
  return persona
}
