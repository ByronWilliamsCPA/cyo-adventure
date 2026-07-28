import { Link } from 'react-router'

/**
 * Guardian-facing plain-language account of how family data is handled
 * (capability register G11, "plain-language trust surface").
 *
 * Deliberately NOT the legal privacy notice. That is a separate Phase 7
 * deliverable (ADR-018 D4) with retention periods, statutory rights, and a
 * contact route; this page explains the architecture in a parent's terms and
 * says so up front, so the two are never mistaken for each other.
 *
 * Every claim below is a property enforced somewhere in code, not an
 * aspiration. When editing, keep it that way: a privacy page that overclaims
 * is worse than no page at all, because a guardian acts on it. The specific
 * anchors, and the reason each sentence is worded the way it is:
 *
 * - "shaped by your settings, never by who they are" ->
 *   story_requests/brief.py::_content_controls sends age band, reading level,
 *   banned themes and content-flag caps, and pins the protagonist to the
 *   generic _DEFAULT_PROTAGONIST_NAME ("Explorer").
 * - "stops with an error rather than carrying on" -> generation/pii.py's
 *   assert_prompt_pii_safe RAISES ValidationError and fails the job. It does
 *   not strip or redact, and the wording must not imply that it does; a hard
 *   fail is the claim, because a hard fail cannot silently half-succeed.
 * - shared-catalog wording -> db/models.py Storybook.visibility ('family' vs
 *   'catalog') plus api/library.py's assignment check. Note the page says
 *   family-only is the DEFAULT rather than claiming promotion never happens:
 *   api/approval.py:149 lets the approver choose 'catalog' and falls back to
 *   Visibility.FAMILY only when no body is sent.
 * - "outside safety services" -> story_requests/screening.py sends the child's
 *   typed text to third-party classifiers. This is a real egress of
 *   child-typed words and is stated plainly rather than buried; the owner
 *   chose to describe the services generically rather than name vendors, so
 *   the page does not need editing when a provider changes.
 * - "not retained after the request and is not used to train their models" ->
 *   the OpenRouter workspace guardrail configured 2026-07-28 (ADR-003's
 *   amendment of that date) requires zero-retention endpoints and disables all
 *   three data-training paths. This is a ROUTING control on a mutable console
 *   setting, which is why the sentence says the account configuration enforces
 *   it rather than claiming a contractual guarantee: the DPA is still open in
 *   docs/compliance/processor-dpa-checklist.md. If that guardrail is ever
 *   relaxed, this paragraph becomes false and must change with it.
 * - "a person reviews it and has to approve it" -> ADR-005 mandatory human
 *   approval, publishing/state_machine.py. Worded as "a person", not "you",
 *   because the reviewer is the safety reviewer rather than necessarily the
 *   requesting guardian (see ConsolePage's own notice to that effect).
 * - "fixed in the code rather than a setting someone could switch on" ->
 *   core/observability.py hardcodes send_default_pii=False and deliberately
 *   does not expose it as a Settings field; the frontend keeps all three
 *   Sentry replay/trace sample rates at 0.
 *
 * Note on personalization: ADR-023 render-time slot substitution is Proposed
 * and NOT built ("Nothing in this ADR exists in code today"), so this page
 * describes only the customization that ships today. Do not add name-level
 * personalization language here before the client-side resolver exists.
 */
export function PrivacyPage() {
  return (
    <section className="privacy">
      <h1>How we handle your family&apos;s data</h1>
      <p className="privacy__intro cyo-text-muted">
        This is a plain-language explanation of how CYO Adventure treats your family&apos;s
        information, written so you can check our work rather than take our word for it. It is not
        the legal privacy notice; that is a separate document with retention periods, your formal
        rights, and how to contact us.
      </p>

      <div className="privacy__summary cyo-card">
        <h2>The short version</h2>
        <ul>
          <li>Stories are shaped by the settings you choose, never by who your child is.</li>
          <li>Your family&apos;s stories, reading progress, and requests stay with your family.</li>
          <li>
            Nothing your child asks for reaches them without passing safety checks and your
            approval.
          </li>
        </ul>
      </div>

      <h2>Stories made for your child</h2>
      <p>
        When a story is written for one of your children, the request describes the kind of reader
        it is for, not the child themselves. What we send is the age band, the reading level, the
        content limits you have set, and any themes you have ruled out.
      </p>
      <p>
        What we never send is anything that identifies your child: their name, their birthday, their
        photo, where they live, or where they go to school. The main character is a generic
        fictional adventurer, never your child.
      </p>
      <p>
        This is not left to good intentions. Every request is checked immediately before it leaves
        our servers, and if anything identifying is found, the request{' '}
        <strong>stops with an error rather than carrying on</strong>. There is no version of this
        that quietly continues with the personal details removed, because a check that fails loudly
        is one you can actually rely on.
      </p>

      <h2>Where the stories come from, and who checks them</h2>
      <p>
        The stories are written by an AI writing model, not by a person on our staff and not by
        other families. We think you should know that plainly rather than discover it.
      </p>
      <p>
        Nothing an AI writes reaches a child unchecked. Every story goes through automatic checks
        first, which look at its structure, its reading level, and its content against the limits
        set for that reader, and a story that fails them does not proceed. After that a person
        reviews it and has to approve it before it can be read. Both gates have to pass, and the
        human one is not optional or skippable.
      </p>
      <p>
        The services that write our stories are set up so that what we send them is not retained
        after the request and is not used to train their models. That is enforced by the account
        configuration we route through, not by a promise in a contract we hope holds.
      </p>

      <h2>Stories shared between families</h2>
      <p>
        Some stories are written for your family alone. Others are part of a shared library that any
        family can draw from. A shared story contains nothing about any particular child: it is the
        same words for every reader, which is exactly why it can be shared at all.
      </p>
      <p>
        A story written for your family stays with your family by default. Putting one into the
        shared library is a deliberate decision taken when the story is approved, not something that
        happens automatically because a story turned out well. And in the other direction, your
        child only ever sees a shared story if you assign it to them.
      </p>

      <h2>When your child asks for a story</h2>
      <p>
        Children can ask for a story in their own words. That is the one place where something a
        child typed travels beyond our servers, so it is worth being exact about what happens to it.
      </p>
      <ol className="privacy__steps">
        <li>
          <strong>We check it for personal information first, on our own servers.</strong> If it
          looks like a name, an address, a phone number, or an email, the request is blocked
          straight away. It does not reach your queue, and it does not reach anyone outside.
        </li>
        <li>
          <strong>Then it is checked for unsafe content by outside safety services.</strong> These
          are specialist services that screen text for harmful material. They see the words your
          child typed; they receive nothing about who your child is.
        </li>
        <li>
          <strong>Then it waits for you.</strong> A request that passes both checks appears in your
          queue as a suggestion. No story is written until you approve it.
        </li>
      </ol>
      <p>
        What your child typed is kept with your family&apos;s records so you can see what was asked
        for, and it is deleted when you delete the profile or the family.
      </p>

      <h2>What stays on our servers</h2>
      <p>
        Reading progress, saved places, the endings each child has reached, and the history of
        requests all live in our own database. They are what let you see how reading is going. None
        of it is sent to outside services, and all of it is deleted when you delete a child profile
        or your family account.
      </p>

      <h2>Cover art</h2>
      <p>
        Book covers are generated from the story&apos;s own details, its title, setting, and theme.
        Nothing about your child forms part of a cover request, and covers are served through
        short-lived private links rather than public addresses.
      </p>

      <h2>What we deliberately do not do</h2>
      <ul className="privacy__nots">
        <li>
          <strong>No advertising, ever.</strong> There are no ads in the app and no advertising or
          analytics tracking in the children&apos;s experience.
        </li>
        <li>
          <strong>No session or screen recording.</strong> We do not record what a child does on
          screen. The tooling that could do this is switched off in code.
        </li>
        <li>
          <strong>No accounts for children.</strong> Children never sign in to an outside service.
          The only adult account is yours, and your children read through it.
        </li>
        <li>
          <strong>No personal information in our error reports.</strong> When something breaks and
          we get a diagnostic report, names, email addresses, and network addresses are stripped
          out. That is fixed in the code rather than a setting someone could switch on.
        </li>
      </ul>

      <h2>What you control</h2>
      <ul className="privacy__controls">
        <li>
          The content limits, reading level, and banned themes on each child&apos;s profile, from{' '}
          <Link to="/guardian/profiles">Profiles</Link>.
        </li>
        <li>
          Whether any story your child asks for is ever written, from{' '}
          <Link to="/guardian/requests">Requests from your kids</Link>.
        </li>
        <li>
          Which books each child can see, from <Link to="/guardian/books">Books</Link>.
        </li>
        <li>Deleting a child profile, or your whole family account, along with all of its data.</li>
      </ul>

      <h2>What this page does not cover</h2>
      <p className="cyo-text-muted">
        Exact retention periods, your formal rights over your data, and how to make a request about
        them belong in the legal privacy notice, which is published separately. If something here
        does not match what you see in the app, treat that as a bug worth reporting rather than fine
        print you have missed.
      </p>
    </section>
  )
}
