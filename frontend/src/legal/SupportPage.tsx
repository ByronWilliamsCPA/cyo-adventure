import { Link } from 'react-router'

import { usePageTitle } from '../hooks/usePageTitle'
import { PRIVACY_PATH } from '../routes'

import { CONTACT_EMAIL, CONTROLLER_NAME } from './legalContact'
import './legal.css'

/**
 * The PUBLIC support and contact page, at `/support`, reachable without
 * signing in.
 *
 * This is the URL registered with Epic's Kids Web Services in place of their
 * default support link (`support.kidswebservices.com/contact`). That default
 * sends a parent to Epic, who cannot answer anything about our app, our data,
 * or their child's account; the questions a parent has at that moment are ours
 * to answer. Epic's own page is a contact route rather than a knowledge base,
 * which is why this page leads with a way to reach a person and puts the
 * questions underneath.
 *
 * #CRITICAL: security: the audience for this page includes a parent who is
 * midway through a KWS verification and has just been asked for a payment card.
 * That is exactly the context a phishing page imitates, so this page must never
 * ask for a card number, a password, or any credential, and must not host a
 * form that collects one. It is deliberately static: a mailto link and prose,
 * with no inputs at all.
 * #VERIFY: SupportPage.test.tsx asserts the rendered page contains no <input>,
 * <form>, or <textarea> element, so adding one trips a test rather than
 * shipping.
 *
 * Answers here must match `PrivacyPolicyPage.tsx` where they overlap. When one
 * changes, change both: a support page that contradicts the privacy policy is
 * worse than one that stays silent, because a parent reasonably treats the
 * friendlier page as the real answer.
 */
export function SupportPage() {
  usePageTitle('Support')
  return (
    <main className="legal">
      <Link className="legal__back" to="/">
        Back to CYO Adventure
      </Link>
      <h1>Support</h1>

      <div className="legal__summary cyo-card">
        <h2>Contact us</h2>
        <p>
          Email <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> and a person will read it.
          There is no phone line and no chatbot.
        </p>
        <p>
          If you are writing about a specific child&apos;s profile or a story, tell us the
          profile&apos;s display name and roughly when it happened. Please do not send us your
          child&apos;s real name, birthday, or photograph: we do not need them, and we do not want
          to hold them.
        </p>
      </div>

      <h2>Questions we are asked most</h2>
      <dl className="legal__faq">
        <dt>Why am I being asked to verify that I am an adult?</dt>
        <dd>
          Children&apos;s privacy law requires that a parent or legal guardian, not a child, gives
          permission before a child&apos;s profile is created. We use Epic&apos;s Kids Web Services
          to confirm that the person giving permission is an adult. We receive the result of that
          check; we do not receive or store your payment card details. Some parents are not asked
          anything at all: if Epic already holds a record that this email address belongs to a
          verified adult, it tells us so directly, and that earlier check is one we did not see and
          cannot inspect. The <Link to={PRIVACY_PATH}>privacy policy</Link> explains what Epic
          receives and keeps.
        </dd>

        {/* #ASSUME: payment/financial: what the card method actually does to a
            card, an authorisation or a small refunded charge, and how it is
            labelled on a statement, is Epic's behaviour and not ours. It is an
            open question in docs/operations/kws-test-runbook.md (Q2) and is
            unanswered as of 2026-08-10. This answer therefore states only what
            we can stand behind: the card is not charged BY US and we never see
            it. Do not add a specific amount, a statement descriptor, or the
            word "refunded" here until the Q2 run establishes them.
            #VERIFY: SupportPage.test.tsx asserts this answer names no currency
            amount. */}
        <dt>Will I be charged?</dt>
        <dd>
          The card check is a verification step, not a purchase, and CYO Adventure does not charge
          your card or receive any money from it. The card is handled entirely by the verification
          service; we never see the number. If you see something on your statement you do not
          recognise and think it came from this process, email us and we will help you trace it.
        </dd>

        <dt>What does my child give you?</dt>
        <dd>
          A display name, which should be a nickname rather than a real name, an age band, and
          whatever story ideas they type. We never ask a child for a real name, birthday, photo,
          address, phone number, or email. See the <Link to={PRIVACY_PATH}>privacy policy</Link> for
          the full list.
        </dd>

        <dt>Who writes the stories, and who checks them?</dt>
        <dd>
          Stories are written by an AI writing model, not by staff and not by other families.
          Nothing reaches a child unchecked: every story passes automatic checks on structure,
          reading level, and content, and then a person reviews and approves it. Both gates have to
          pass and neither is skippable.
        </dd>

        <dt>Can other families see my child&apos;s stories or reading?</dt>
        <dd>
          No. A story written for your family stays with your family unless it is deliberately
          promoted into the shared library when it is approved, and a shared story contains nothing
          about any particular child. Reading progress and requests are never shown to another
          family.
        </dd>

        <dt>How do I delete our data?</dt>
        <dd>
          You can delete a single child&apos;s profile yourself, from your guardian console.
          Deleting your entire family account, exporting your data, and pausing a profile do not
          have a button in the app yet: email us and a person will do it. Deletion is permanent
          either way.
        </dd>

        <dt>I think something unsafe reached my child.</dt>
        <dd>
          Email us with the book title and the profile&apos;s display name and we will pull the
          story and look at what got through. Please tell us even if you are not sure: a false alarm
          costs us nothing, and a missed one is the failure we care most about.
        </dd>

        <dt>Who is responsible for this app?</dt>
        <dd>
          {CONTROLLER_NAME}. The <Link to={PRIVACY_PATH}>privacy policy</Link> sets out what is
          collected, who it is shared with, and how long it is kept.
        </dd>
      </dl>
    </main>
  )
}
