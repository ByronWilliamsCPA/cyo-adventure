/**
 * Copy for the pre-OAuth adult affirmation on the guardian login page
 * (unscheduled-work register `UW-J33`).
 *
 * A standalone module for the same reason as `loginHeadline.ts`: Playwright
 * specs that assert these strings run in Node, and importing them from
 * `LoginPage.tsx` would drag the component, its CSS, and the Supabase client
 * into that module graph.
 *
 * This is an AFFIRMATION, not verification, and the wording must stay that
 * way (register rows `UW-J25` / `UW-J33`): nothing here checks anything, it
 * records nothing, and it must never read as though it did. The checkbox
 * mirrors the consent page's own adulthood line ("I confirm that I am an
 * adult.") so the two read as one voice, with the age spelled out because a
 * first-time visitor has not yet met the consent page. It deliberately does
 * NOT claim guardianship: the same button signs in admin-only adults who are
 * nobody's guardian, and guardianship is affirmed, per child, on
 * `GuardianConsentPage` where the recorded consent lives.
 */
export const ADULT_AFFIRMATION_LABEL = 'I confirm that I am an adult (18 or older).'

/**
 * The reason the provider buttons are inert until the box is ticked. Visible
 * text (never colour alone) and the `aria-describedby` target of each locked
 * button, so a screen-reader user tabbing onto one hears why it will not act.
 */
export const ADULT_AFFIRMATION_HINT =
  'Only an adult can sign in or create an account here. Check the box above to continue.'
