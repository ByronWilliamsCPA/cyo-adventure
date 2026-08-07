import { Link } from 'react-router'

import { usePageTitle } from '../hooks/usePageTitle'

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
 * - "we send those words too, as the premise" -> the settings list above is
 *   NOT the whole payload and must never be written as if it were.
 *   story_requests/brief.py:197 is literally `premise=request.request_text`,
 *   and generation/prompts.py's build_bind_prompt / build_interpret_bind_prompt
 *   serialise that brief into the provider prompt inside the
 *   UNTRUSTED_USER_INPUT fence. docs/compliance/records-of-processing-activities.md
 *   row 3 records the recipients of "Request text" accordingly. An earlier
 *   version of this page listed the settings as exhaustive, which made the
 *   page false by omission about the single most sensitive egress it has.
 * - "stops with an error rather than carrying on" -> generation/pii.py's
 *   assert_prompt_pii_safe RAISES ValidationError and fails the job. It does
 *   not strip or redact, and the wording must not imply that it does; a hard
 *   fail is the claim, because a hard fail cannot silently half-succeed.
 * - "one of your children's names, or something shaped like an address, a
 *   phone number, or an email" -> that enumeration is the guard's real reach,
 *   not a sample of it. story_requests/screening.py:82-83 passes only the
 *   family's REGISTERED child display names, and generation/pii.py's pattern
 *   layer covers email, phone, and street-address shapes only. Its own
 *   docstring says general free-text PII detection "can never be complete".
 *   A friend's name, an unregistered sibling, a school or a city passes
 *   through, so the page must not say "if it looks like a name".
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
 * - "not kept after the request and is not used to train models" -> the
 *   OpenRouter workspace guardrail configured 2026-07-28 (ADR-003's amendment
 *   of that date) requires zero-retention endpoints and disables all three
 *   data-training paths. Two qualifications are load-bearing:
 *   1. That ADR-003 amendment is NOT yet on main. It lands with PR #439
 *      (branch docs/adr-provider-restriction-rescope), which is expected to
 *      merge before this page does. The citation is deliberately kept so the
 *      anchor is right once #439 lands; if #439 is abandoned, this paragraph
 *      loses its basis and must change with it.
 *   2. The guardrail is a ROUTING control on one vendor's workspace, so it
 *      reaches only the legs that go through that vendor. core/config.py's
 *      generation_provider Literal still admits "anthropic", a direct
 *      first-party adapter (generation/providers/anthropic.py) that bypasses
 *      OpenRouter entirely, and the amendment's own #CRITICAL block says so;
 *      the ZDR "Anthropic" toggle disables first-party Anthropic endpoints
 *      through the route, not the direct leg. Cover art goes to Google Gemini,
 *      also outside it. That is why the page scopes the sentence to the route
 *      and then names what the route does not cover, rather than claiming it
 *      of "the services that write our stories" generally.
 *   It is a mutable console setting either way, which is why the sentence says
 *   the account configuration enforces it rather than claiming a contractual
 *   guarantee: the DPA is still open in
 *   docs/compliance/processor-dpa-checklist.md.
 * - "a person reviews it and has to approve it" -> ADR-005 mandatory human
 *   approval, publishing/state_machine.py. Worded as "a person", not "you",
 *   because the reviewer is the safety reviewer rather than necessarily the
 *   requesting guardian (see ConsolePage's own notice to that effect).
 * - "we do not send your names, email addresses, or network addresses along
 *   with it" -> core/observability.py hardcodes send_default_pii=False and
 *   deliberately does not expose it as a Settings field; the frontend keeps
 *   all three Sentry replay/trace sample rates at 0. Note the verb: that flag
 *   stops Sentry ATTACHING identity, client IP, and request bodies. It does
 *   not scrub PII that happens to appear inside an exception message or a
 *   breadcrumb, so "stripped out" would claim a redactor we do not run.
 * - the profile-vs-family erasure split -> api/profiles.py::delete_profile
 *   cascades reading state, completions, ratings, assignments and kid flags,
 *   but its docstring records that story requests the child submitted are
 *   "de-linked (``profile_id`` set null) rather than deleted, since they
 *   remain family-owned content". Only api/me.py::delete_my_family erases the
 *   request text. This is a GDPR Article 17 / COPPA 312.10 statement, so the
 *   two routes must never be collapsed into one sentence.
 * - "There is no button for this yet" -> DELETE /v1/me/family exists
 *   (api/me.py:265) and is in the generated client as
 *   deleteMyFamilyApiV1MeFamilyDelete, but nothing under frontend/src outside
 *   src/client/ calls it, and capability-register G12 is still partial. Every
 *   other bullet in that list links to a live surface; this one says plainly
 *   that it does not, rather than promising a control a parent cannot find.
 *   When the deletion UI ships, replace the sentence with the link.
 *
 * Note on personalization: ADR-023 render-time slot substitution is Proposed
 * and NOT built ("Nothing in this ADR exists in code today"), so this page
 * describes only the customization that ships today. Do not add name-level
 * personalization language here before the client-side resolver exists.
 */
export function PrivacyPage() {
  usePageTitle('Privacy')
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
          <li>
            Your family&apos;s stories, reading progress, and requests are never shown to another
            family.
          </li>
          <li>
            Nothing your child asks for reaches them without passing safety checks and your
            approval.
          </li>
        </ul>
      </div>

      <h2>Stories made for your child</h2>
      <p>
        When a story is written for one of your children, the request describes the kind of reader
        it is for, not the child themselves. We send the age band, the reading level, the content
        limits you have set, and any themes you have ruled out.
      </p>
      <p>
        We also send the wish itself. If your child asked for a story about a dragon who runs a
        bakery, those are the words we send, exactly as they were typed, because they are the
        premise the story gets built from. There is no way to write the story somebody asked for
        without sending what they asked for, so we would rather say so here than let you assume
        otherwise.
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
        Story writing is routed through one service, and our account with that service is configured
        so that what we send is{' '}
        <strong>not kept after the request and is not used to train models</strong>. That is
        enforced by the account we route through rather than by a promise in a contract we hope
        holds, which is the stronger of the two.
      </p>
      <p>
        Being exact about how far that reaches, because it is a setting on one route rather than a
        rule about every company we deal with: an administrator can send story writing to a writing
        service directly instead of through that route, and the pictures on the covers are drawn by
        a different service again. Neither of those is covered by the setting above.
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
        Children can ask for a story in their own words. Those words are the one thing a child types
        that travels beyond our servers, so it is worth walking through every place they go.
      </p>
      <ol className="privacy__steps">
        <li>
          <strong>We check them for personal information first, on our own servers.</strong> If they
          contain one of your children&apos;s names, or something shaped like an address, a phone
          number, or an email, the request is blocked straight away. It does not reach your queue,
          and it does not reach anyone outside.
        </li>
        <li>
          <strong>Then they are checked for unsafe content by outside safety services.</strong>{' '}
          These are specialist services that screen text for harmful material. They see the words
          your child typed; they receive nothing about who your child is.
        </li>
        <li>
          <strong>Then it waits for you.</strong> A request that passes both checks appears in your
          queue as a suggestion. No story is written until you approve it.
        </li>
        <li>
          <strong>If you approve it, the words go to the writing model.</strong> What your child
          typed becomes the premise the story is written from, and it is sent to the writing service
          word for word. This is the step people are most likely to assume does not happen, so we
          are saying it plainly: approving a request is what sends your child&apos;s own sentence
          out to be written from.
        </li>
      </ol>
      <p>
        What your child typed is kept with your family&apos;s records so you can see what was asked
        for. It is erased when you delete your family account. Deleting a single child profile
        erases that child&apos;s reading records and unlinks the request from them, but the request
        itself stays with your family&apos;s records, because it may already have produced a story
        your family owns.
      </p>

      <h2>What stays on our servers</h2>
      <p>
        Reading progress, saved places, the endings each child has reached, and the history of
        requests all live in our own database. They are what let you see how reading is going. None
        of it is sent to outside services. Deleting a child profile erases that child&apos;s reading
        records; deleting your family account erases everything, the request history included.
      </p>

      <h2>Cover art</h2>
      <p>
        Book covers are generated from the story&apos;s own details, its title, setting, and theme.
        Nothing about your child forms part of a cover request, and covers are served through
        short-lived private links rather than public addresses.
      </p>

      <h2>What we deliberately do not do</h2>
      {/*
        role="list" is not redundant here: .privacy__nots sets list-style: none,
        and Safari/VoiceOver drops list semantics from a list with no marker.
        Without it these items are announced as loose text.
      */}
      <ul className="privacy__nots" role="list">
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
          we get a diagnostic report, we do not send your names, email addresses, or network
          addresses along with it. That is fixed in the code rather than a setting someone could
          switch on.
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
        <li>
          Deleting a child profile, and that child&apos;s reading records with it, from{' '}
          <Link to="/guardian/profiles">Profiles</Link>.
        </li>
        <li>
          Deleting your whole family account and everything in it. There is no button for this in
          the app yet, so for now it is done by asking us; the legal privacy notice is where the
          contact details live.
        </li>
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
