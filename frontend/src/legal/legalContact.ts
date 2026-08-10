/**
 * Shared constants for the two public legal/support surfaces.
 *
 * These pages are reachable without signing in, and one of them is registered
 * with Epic's Kids Web Services as our Privacy Policy and Support URLs
 * (ADR-018 D1). A parent who is midway through a verification flow may land
 * here from KWS's screens, so the contact route below is the one an outside
 * reader is told to use.
 *
 * #ASSUME: external resources: CONTACT_EMAIL is a real, monitored mailbox. It
 * is currently the maintainer's personal address, which is what
 * `docs/compliance/privacy-notice.md` already names, rather than a role
 * address that does not exist yet. Publishing an address that bounces is worse
 * than publishing a personal one, so this stays until a role mailbox is
 * actually provisioned; changing it is a one-line edit here and nowhere else.
 * #VERIFY: legal/PrivacyPolicyPage.test.tsx and legal/SupportPage.test.tsx
 * both assert the rendered mailto matches this constant, so a change here
 * cannot silently leave one page pointing at a stale address.
 */
export const CONTACT_EMAIL = 'byronawilliams@gmail.com'

/**
 * The date the public-facing text below was last changed.
 *
 * Deliberately NOT wired to the consent-capture version stamp
 * (`auth/onboardingApi.ts`'s CONSENT_POLICY_VERSION). That constant records
 * which text a guardian agreed to, and coupling the two would let an editorial
 * fix to this page invalidate every recorded consent. They are kept separate on
 * purpose; see PrivacyPolicyPage's own note on the relationship.
 */
export const POLICY_LAST_UPDATED = '10 August 2026'

/** Who is responsible for the information described on these pages. */
export const CONTROLLER_NAME = 'Byron Williams'
