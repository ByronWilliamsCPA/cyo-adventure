import { Link } from 'react-router'

import { usePageTitle } from '../hooks/usePageTitle'
import { SUPPORT_PATH } from '../routes'

import { CONTACT_EMAIL, CONTROLLER_NAME, POLICY_LAST_UPDATED } from './legalContact'
import './legal.css'

/**
 * The PUBLIC privacy policy, at `/privacy`, reachable without signing in.
 *
 * This is the URL registered with Epic's Kids Web Services as our Privacy
 * Policy (ADR-018 D1). KWS will not let us call the verification API until a
 * brand name and a Privacy Policy URL are published, and a parent partway
 * through verification may follow that link, so this page has to resolve for
 * someone with no account and no session.
 *
 * Three things this page is NOT, each for a specific reason:
 *
 * 1. It is not `guardian/PrivacyPage.tsx`. That page (capability register G11)
 *    is a signed-in trust surface explaining the architecture in a parent's
 *    terms, and it says of itself that it is not the legal notice. Both exist;
 *    they answer different questions and are linked to each other rather than
 *    merged.
 * 2. It is not a verbatim publication of `docs/compliance/privacy-notice.md`.
 *    That draft carries `[COUNSEL: ...]` brackets and, in three places, tells
 *    its own reader not to publish a sentence yet. Those sentences are absent
 *    here rather than softened; see the omissions list below.
 * 3. It is not counsel-approved text. The notice is still in review. What is
 *    published here is the subset that is true of the system as built and that
 *    the draft does not itself hold back.
 *
 * #CRITICAL: security: every claim on this page must be a property something
 * enforces, not an intention. A privacy policy that overclaims is acted on by
 * parents and is a regulatory exposure in its own right. Four claims from the
 * draft notice are deliberately ABSENT and must not be added back without the
 * thing behind them being true first:
 *   - the per-purpose GDPR Article 6 legal-basis column (draft Note 1: not yet
 *     reviewed by counsel);
 *   - "none of them may use your information for their own purposes", asserted
 *     of every processor (docs/compliance/processor-dpa-checklist.md shows
 *     several DPAs unexecuted);
 *   - a named international-transfer mechanism, Standard Contractual Clauses or
 *     DPF (coppa-gdpr-remediation-plan.md Phase 5 paperwork is not complete);
 *   - "we will ask you to review and re-confirm your consent" on a material
 *     change (the re-consent flow is Phase 2b and is not built; this page
 *     describes the manual interim instead).
 * #VERIFY: PrivacyPolicyPage.test.tsx pins each of the four absences, so
 * re-adding one fails a test that names the reason rather than passing quietly.
 *
 * The same rule cuts the other way, and six statements here are PRESENT for a
 * reason rather than by default. Each one reads as an awkward hedge and is the
 * kind of sentence an editor tidies away, so each is pinned by a test too:
 *   - the PII check "stops the request rather than editing it".
 *     `generation/pii.py::assert_prompt_pii_safe` RAISES; it strips nothing,
 *     and guardian/PrivacyPage.tsx already carries a standing instruction that
 *     the wording must not imply otherwise. "Checked to remove" is the exact
 *     phrasing that instruction forbids.
 *   - the Epic row naming a country code and a language, not just an email.
 *     `consent/kws_client.py` sends `{email, location, language, ...}` and
 *     documents `location` as the CHILD's, so an email-only row would be false
 *     by omission about a child-linked transfer.
 *   - the AgeGraph paragraph. `core/config.py`'s kws_enabled_methods note
 *     records that a matched hashed email pre-verifies a parent with no new
 *     verification event on our side, under a method the webhook never reports.
 *   - Epic "not acting solely on our instructions", which is ADR-018's
 *     independent-controller finding. It is deliberately NOT phrased as the
 *     inverse of the withheld processor-only claim above; both can be true of
 *     different vendors, and the tests pin them independently.
 *   - which rights have an in-app control and which are done by email.
 *     guardian/PrivacyPage.test.tsx pins "no button for this in the app yet"
 *     for family deletion; a public page promising the button would contradict
 *     a named regression test on the signed-in page.
 *   - raw-output retention scoped to "after the generation run finishes" and to
 *     an undecided story, plus "no timer on it at all" for a run that never
 *     finished. The nightly purge predicate
 *     (20260810000000_exempt_reviewed_generation_job_report_from_purge.sql) is
 *     gated on status IN ('passed','needs_review','failed') and exempts a
 *     human-decided storybook entirely, so an unqualified "30 days" and the old
 *     "or as soon as the story is published" are both false: publishing is now
 *     an exemption from deletion, not a trigger for it.
 *   - "a later approval does not bring it back", and the "never finished" scope
 *     on the no-timer clause. Both are forced by the same predicate: the
 *     exemption is evaluated when the sweep runs, not when the human decides, so
 *     a story still in review on day 31 is purged and the day-32 approval
 *     recovers nothing. Only queued/running/awaiting_manual_fill sit outside the
 *     status filter, and those are runs that have not finished; a run waiting on
 *     a REVIEWER is at status "passed" and is on the clock. An earlier draft of
 *     this row said "a run left waiting on a person has no timer on it at all",
 *     which conflated the two and read as a promise for the reviewer case. See
 *     UW-C227 and test_slow_review_report_is_purged_before_the_human_decides.
 *
 * Relationship to the consent record: `auth/onboardingApi.ts` holds
 * CONSENT_POLICY_VERSION, the stamp stored on `User.consent_policy_version` so
 * a recorded consent points at the exact text agreed to. That is deliberately
 * NOT the same value as POLICY_LAST_UPDATED here. Coupling them would mean a
 * typo fix on this page invalidated every consent on file. When the substance
 * changes rather than the wording, bump the consent version too, as a decision.
 */
export function PrivacyPolicyPage() {
  usePageTitle('Privacy Policy')
  return (
    <main className="legal">
      <Link className="legal__back" to="/">
        Back to CYO Adventure
      </Link>
      <h1>CYO Adventure Privacy Policy</h1>
      <p className="legal__updated cyo-text-muted">Last updated: {POLICY_LAST_UPDATED}</p>

      <div className="legal__summary cyo-card">
        <h2>The short version</h2>
        <ul>
          <li>
            Children do not have their own accounts, and we never ask a child for a real name,
            birthday, photo, address, phone number, or email.
          </li>
          <li>
            We do not sell information, and there is no advertising or marketing code anywhere in
            the part of the app a child uses.
          </li>
          <li>
            A grown-up sets up every profile, approves every story, and can delete a child&apos;s
            profile at any time. Exporting your data, deleting the whole family account, and pausing
            a profile are done by emailing us, not yet by a button in the app.
          </li>
        </ul>
      </div>

      <h2>Who we are</h2>
      <p>
        CYO Adventure (&quot;we&quot;, &quot;us&quot;) is a choose-your-own-adventure reading app
        for children. The person responsible for your and your child&apos;s information is{' '}
        {CONTROLLER_NAME}. You can reach us at{' '}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>

      <h2>Who this policy covers</h2>
      <p>
        This policy is written for <strong>guardians</strong>: the parents and legal guardians who
        create and manage accounts. It describes what we collect about you, and what we collect
        about the children whose profiles you set up.
      </p>
      <p>
        Children do not create accounts, do not give their own consent, and receive no marketing of
        any kind. Every child-linked interaction happens inside a profile a guardian created and
        controls.
      </p>

      <h2>What we collect, and why</h2>
      {/* tabIndex on the scroll container, not decoration: these tables set a
          min-width and scroll sideways on a phone, and a region that scrolls
          but cannot be focused is unreachable by keyboard alone. */}
      <div className="legal__table-wrap" tabIndex={0} role="region" aria-label="What we collect">
        <table className="legal__table">
          <thead>
            <tr>
              <th scope="col">What</th>
              <th scope="col">About whom</th>
              <th scope="col">Why</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Email address, sign-in identity, account role</td>
              <td>Guardian</td>
              <td>Run your account and let you sign in</td>
            </tr>
            <tr>
              <td>
                The consent record: your typed name, the date, and the version of this policy you
                agreed to
              </td>
              <td>Guardian</td>
              <td>Show that a parent gave permission before any child profile existed</td>
            </tr>
            <tr>
              <td>Country of residence, chosen from a list</td>
              <td>Guardian</td>
              <td>
                Work out which country&apos;s privacy and online-safety rules apply to your account
              </td>
            </tr>
            <tr>
              <td>Your confirmation that you are an adult, and the date you confirmed it</td>
              <td>Guardian</td>
              <td>
                Work out which age-related rules apply. This is something you tell us; we record the
                date you said it, not proof of your age or identity
              </td>
            </tr>
            <tr>
              <td>
                Display name (a nickname, not a legal name), age band, reading-level cap, an avatar
                chosen from a fixed set of drawings, and content settings
              </td>
              <td>Child</td>
              <td>Build and safely tailor your child&apos;s reading profile</td>
            </tr>
            <tr>
              <td>Story requests (typed story ideas), reading progress, completions, ratings</td>
              <td>Child</td>
              <td>
                Write, check, and deliver stories, and let your child pick up where they left off
              </td>
            </tr>
            <tr>
              <td>Cross-family connection settings, if you choose to link with another family</td>
              <td>Guardian</td>
              <td>
                Let book recommendations pass between families you have explicitly agreed to connect
              </td>
            </tr>
            <tr>
              <td>
                A record of administrator actions on your account, and of an administrator opening
                one of your child&apos;s profiles
              </td>
              <td>Guardian, Child</td>
              <td>Safety review, account support, and an audit trail of who did what</td>
            </tr>
            <tr>
              <td>
                Security records: the IP address a request came from, what was asked for, and what
                happened. These are written for requests from a child&apos;s device as well as from
                yours
              </td>
              <td>Guardian, Child</td>
              <td>Spotting and investigating abuse, and keeping an account-security trail</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        <strong>About the country and adulthood answers</strong>: we do not verify the country you
        pick, and we do not check any identification to confirm you are an adult. We record what you
        tell us and nothing more.
      </p>
      <p>
        <strong>What we deliberately never collect from a child</strong>: their real name,
        birthdate, exact age, photograph, email address, or phone number. A child never has their
        own email, phone number, or sign-in identity. Every way into the app resolves back to a
        guardian&apos;s account.
      </p>
      <p>
        We do not collect a child&apos;s precise location. The only place a location is involved at
        all is the age-verification step described below, which sends a country or region code
        derived from the country you chose for your own account.
      </p>

      <h2>How we get your permission</h2>
      <p>
        Before you can create a child profile, we ask you to type your full legal name and confirm
        that you are that child&apos;s parent or legal guardian and that you agree to this policy.
        We record your typed name, the date, the version of this policy, and your IP address at the
        time, alongside the sign-in you had already completed.
      </p>
      <p>
        We are in the process of moving this to a verification service operated by Epic&apos;s Kids
        Web Services, which confirms that the person giving permission is an adult before a profile
        can be created. Until that is switched on, the process above is what happens.
      </p>
      <p>
        Two things about that service are worth knowing before it is switched on. Epic keeps a
        record of parents it has already checked, matched on a one-way scrambled form of the email
        address. If yours is in that record, Epic can tell us you are an adult without sending you
        anything: the check that stands behind it happened somewhere else, at a time we do not see,
        and Epic does not tell us which method was used. Separately, Epic uses that same record to
        answer the same question for its other customers, which is why we describe it above as not
        acting solely on our instructions.
      </p>

      <h2>Who we share information with</h2>
      <p>We use the following outside companies to run the app:</p>
      <div
        className="legal__table-wrap"
        tabIndex={0}
        role="region"
        aria-label="Who we share information with"
      >
        <table className="legal__table">
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col">What they receive</th>
              <th scope="col">Why</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Supabase</td>
              <td>Your account and your child&apos;s profile data, stored in our database</td>
              <td>Hosting and sign-in</td>
            </tr>
            <tr>
              <td>OpenRouter and the AI model providers it routes to, and Anthropic directly</td>
              <td>
                Story prompts. A prompt is rejected and no story is written if it contains a
                registered child&apos;s name, an email address, a phone number, or something shaped
                like a street address. The check stops the request rather than editing it, and it
                cannot catch every name a child might type, such as a friend&apos;s or a
                school&apos;s
              </td>
              <td>Writing your child&apos;s stories</td>
            </tr>
            <tr>
              <td>OpenAI Moderation, Google Perspective</td>
              <td>Generated story text and typed story ideas, subject to the same check</td>
              <td>Safety-checking content before it reaches your child</td>
            </tr>
            <tr>
              <td>Google (Gemini)</td>
              <td>Cover-art prompts, subject to the same check</td>
              <td>Drawing book cover art</td>
            </tr>
            <tr>
              <td>Cloudflare (R2)</td>
              <td>Cover images, reachable only through a short-lived, non-public link</td>
              <td>Image storage</td>
            </tr>
            <tr>
              <td>Epic Games (Kids Web Services)</td>
              <td>
                A parent&apos;s email address, the country or region code that parent selected for
                their own account, and which language to write in, when a verification is requested.
                Nothing about the child
              </td>
              <td>
                Confirming that a person giving permission is an adult. Epic also keeps what it
                receives in a record it uses to answer the same question for its other customers, so
                for this one step it is not acting solely on our instructions
              </td>
            </tr>
            <tr>
              <td>Sentry</td>
              <td>Error reports, built to exclude your child&apos;s reading content</td>
              <td>Fixing bugs</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        We do not sell your or your child&apos;s information, and we do not use it for advertising.
        There are no advertising or marketing SDKs of any kind in the parts of the app your child
        uses.
      </p>
      <p>
        Each company named above is based in the United States. OpenRouter passes prompts on to
        model providers we have put on an allowlist, and those providers may in turn run on
        infrastructure operated by other companies; we do not independently verify where every one
        of them processes data.
      </p>

      <h2>How long we keep information</h2>
      <div
        className="legal__table-wrap"
        tabIndex={0}
        role="region"
        aria-label="How long we keep information"
      >
        <table className="legal__table">
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col">How long</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Your active account and your child&apos;s active profile</td>
              <td>For as long as they are in use</td>
            </tr>
            <tr>
              <td>
                Reading progress, completions, and ratings for a profile you deactivated but did not
                delete
              </td>
              <td>Up to 90 days after deactivation, then deleted</td>
            </tr>
            <tr>
              <td>A story request we blocked or you declined</td>
              <td>
                The decision and its category are kept; the original typed text is replaced with a
                placeholder 30 days after the decision
              </td>
            </tr>
            <tr>
              <td>
                Raw story-generation output: the unedited text the AI produced, before our automated
                checks ran and before an adult read it
              </td>
              <td>
                Deleted 30 days after the generation run finishes, unless an adult reached a
                decision about that story within those 30 days. Once an adult approves a story or
                sends it back, we keep the raw output for as long as the story exists, so we can
                check whether our safety checks got that story right and improve them. If nobody has
                decided by day 30 we delete it anyway, and a later approval does not bring it back.
                A run that never finished, because it is still generating or is waiting for a person
                to fill something in, has no timer on it at all. All of it goes when you delete your
                family account
              </td>
            </tr>
            <tr>
              <td>Records of safety reviews</td>
              <td>
                Up to two years. Nothing deletes these on a timer yet; until that is built they go
                when we remove them by hand, so treat two years as the target rather than a
                guarantee
              </td>
            </tr>
            <tr>
              <td>
                Our internal record of who did what: an accountability log that holds identifiers
                and categories, never your child&apos;s name or story text
              </td>
              <td>Kept indefinitely, as a compliance and dispute-resolution record</td>
            </tr>
            <tr>
              <td>The security records described above, including IP addresses</td>
              <td>
                Kept indefinitely. These are written so they cannot be altered afterwards, which
                also means there is no routine deletion path for them today
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2>Your rights, and your child&apos;s</h2>
      <p>
        Your child does not hold their own account, so you exercise these on their behalf as their
        guardian, as well as for your own information:
      </p>
      <ul>
        <li>
          <strong>See what we have.</strong> Ask for a full export of your family&apos;s data. There
          is no button for this in the app yet, so it is done by email.
        </li>
        <li>
          <strong>Correct it.</strong> Update your child&apos;s profile settings in the app.
          Changing your own account details is done by email; the app has no screen for it yet.
        </li>
        <li>
          <strong>Delete it.</strong> Delete a single child&apos;s profile in the app. Deleting your
          whole family account is done by email, not yet by a button. Deletion is permanent.
        </li>
        <li>
          <strong>Pause a profile.</strong> Stop active use of one profile&apos;s data without
          deleting it, for example while you sort out a concern. This is done by email too.
        </li>
        <li>
          <strong>Complain.</strong> If you are in the EU or UK, you can complain to your local data
          protection authority.
        </li>
      </ul>
      <p>
        Where a right above says &quot;in the app&quot;, the control is in your guardian console.
        Everything else is done by emailing <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>,
        where a person actions it by hand. We say which is which rather than describing them all as
        app features, because the difference changes how long a request takes.
      </p>

      <h2>Security</h2>
      <p>
        We use encrypted connections, strict access controls, and regular security reviews. No
        system is perfectly secure. If something goes wrong, we follow a documented internal
        breach-response process.
      </p>

      <h2>Changes to this policy</h2>
      <p>
        If we change this policy, the date at the top of the page changes with it. If a change
        materially affects what you agreed to, we will contact you at the email address on your
        account. There is no automated mailing behind that: a person sends it, so check this page if
        you want the current text rather than waiting to be told.
      </p>

      <h2 className="legal__contact">Contact us</h2>
      <p>
        Questions about this policy, or about your family&apos;s information, go to{' '}
        <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. Our{' '}
        <Link to={SUPPORT_PATH}>support page</Link> covers the questions we are asked most often.
      </p>
    </main>
  )
}
