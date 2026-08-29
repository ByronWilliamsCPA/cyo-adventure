/**
 * Real-backend session-setup strategies for the three usersim personas
 * (task B3a), kept in its own module rather than added to personas.ts.
 *
 * Deliberately NOT a change to personas.ts: `entryPath` and `terminals`
 * (personas.ts's `PERSONAS`) describe this app's real client-side
 * route/gate structure, which is identical whether the API underneath is
 * mocked or real, so those values already apply unchanged to the real tier
 * (including through `getPersona`, which invariants.ts::assertNotDeadEnd
 * calls for every persona regardless of tier). Only *how a session is
 * established* differs, and that lives here instead:
 *
 * - kid: `seedDeviceGrant` (personas.ts's own KID_PERSONA) writes a
 *   fabricated grant blob with no backing row; a real backend rejects any
 *   API call made with it. `authorizeDevice` mints a REAL device grant via
 *   POST /api/v1/device-grants (authorized as the seeded dev-guardian
 *   bearer) and injects the real token, then the kid's own subsequent calls
 *   authenticate as the seeded dev-child bearer (mirrors every existing
 *   e2e-real kid spec, e.g. kid-reads.spec.ts).
 * - guardian/admin: `seedGuardianSession`'s default token
 *   ('e2e-guardian-token') is not a real backend principal at all; the real
 *   tier must pass the actual seeded authn subjects
 *   (scripts/seed_dev_data.py's `_GUARDIAN_SUBJECT`/`_ADMIN_SUBJECT`), which
 *   `ENVIRONMENT=local` trusts directly as the bearer. The mocked admin
 *   persona's `mockMe(page, { role: 'admin' })` must NOT run here: it would
 *   override the real backend's own real GET /v1/me response with a fake
 *   one, which is exactly the kind of mock this tier exists to not have.
 */
import type { BrowserContext } from '@playwright/test'

import { seedGuardianSession } from '../../e2e/support/auth'
import { authorizeDevice } from '../../e2e-real/real-stack'
import type { PersonaId } from './personas'

export const REAL_SESSION_SETUP: Record<PersonaId, (context: BrowserContext) => Promise<void>> = {
  async kid(context: BrowserContext): Promise<void> {
    await authorizeDevice(context)
    await context.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'dev-child')
    })
  },
  async guardian(context: BrowserContext): Promise<void> {
    await seedGuardianSession(context, 'dev-guardian')
  },
  async admin(context: BrowserContext): Promise<void> {
    await seedGuardianSession(context, 'dev-admin')
  },
}
