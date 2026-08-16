---
title: "Registration Flow Walkthrough: Minor to Guardian to First Read"
schema_type: common
status: draft
owner: core-maintainer
purpose: "Record the as-built path a brand-new minor and their guardian follow from the landing page to a child's first read, and the friction found along it."
tags:
  - quality_assurance
  - analysis
  - compliance
---

> **Status (2026-08-15): partially superseded by PR [#720](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/720)**
> (merged as `5f38917`, v0.80.0), which rebuilt the landing page as a sales funnel after this walkthrough
> was run. This document is a dated snapshot and is deliberately NOT rewritten; the live status of every
> finding lives in its register row. What changed:
>
> - **Finding 9** (no way back from login): closed. The login page carries a "Back to CYO Adventure" link.
> - **Finding 4** (no create-account wording): closed. The h1 is now "Sign in or create your account", with
>   "New family? Continuing above creates your account." under the provider buttons. The residual is
>   narrower than this document describes; see `UW-J32`.
> - **Finding 7** (the kid-facing line ranked third): largely closed. Under the authorize-device intent the
>   line now replaces the adult lede instead of sitting beneath it.
> - **Finding 5** (the reviewer misattributed to the family): widened, then closed. #720 promoted the same
>   misattribution to the homepage and added a false claim that approval puts a book on a shelf. Both were
>   corrected on 2026-08-15; see `UW-J28`.
> - **Findings 1, 2, 3, 6, 8, 10**: unchanged. #720 touches none of them.
>
> Everything below reads as it did on 2026-08-14.

## Scope and method

Two personas, walked end to end against the app as it stands on `main` (`fc163c5`):

1. **The minor.** A kid who was handed the home page URL by a friend. No account, no device grant, no
   instructions. Question: does the app make it clear that they cannot do this themselves and need a
   grown-up?
2. **Their guardian.** Question: can they create an account, verify, consent, set up the child, and get
   the child reading, without outside help?

The walkthrough was run two ways and the two agree:

- **Live UI.** The frontend was built and served (`vite preview` on `:4173`), then driven with Playwright
  as each persona, with the backend's `POST /api/v1/onboarding` and `GET /v1/me` responses stepped through
  every real onboarding state. Screens were captured at each step.
- **Code trace.** `frontend/src/router.tsx`, `auth/*`, `guardian/*`, and the backend routers
  (`api/onboarding.py`, `api/approval.py`, `api/assignments.py`, `api/library.py`) were read to confirm what
  the screens imply about server-side gating.

Configuration note: `kws_verification_required` defaults to `False` (`core/config.py:1159`), so on a default
deployment the KWS adulthood-verification step is **skipped**. Both variants are described below.

## Part 1: the minor's path

### What they see

The landing page (`/`) offers exactly three ways forward: a **Kids / Start reading** door, a
**Grown-ups / Guardian console** door, and a smaller **"New here? Get started"** line beneath them.

There is no age gate, no "are you a grown-up?" question, and no sentence anywhere on the landing page saying
an adult has to create the account. The kid reads "Kids: Start reading" and takes it, which is correct
behavior on their part.

### Where the Kids door leads

On a device with no valid device grant, the Kids door routes to `/guardian/login?intent=authorize-device`
(`LandingPage.tsx`, `DeviceAuthorizedRoute.tsx`). What renders is:

```text
Guardian sign-in
Sign in to review, approve, and request stories for your family.
Ask a grown-up to set up this device for you.       <- the only kid-facing line
[ Continue with Google ]
Email / Password / Sign in
Forgot your password?
```

**Verdict: the signal exists, but it is the weakest element on the screen.** The one line written for the
child is third in reading order, in the smallest and lowest-contrast type on the page, sitting under a
heading and a subtitle that are both written for an adult. A child scanning this page sees a big heading
they cannot parse, a big orange button, and two form fields. The line that tells them what to do is the
easiest thing to miss.

Also on this screen: **there is no way back.** No link home, no "not a grown-up?" escape. The child's only
exit is the browser back button.

### Where "Get started" leads

This is the more serious gap. A brand-new visitor of any age reads "New here? Get started" as the signup
link. It goes to the same `/guardian/login`, but **without** the `intent=authorize-device` parameter, and
that parameter is what gates the kid-facing line. So the child sees:

```text
Guardian sign-in
Sign in to review, approve, and request stories for your family.
[ Continue with Google ] ...
```

No "ask a grown-up" line at all. The most inviting link on the landing page, the one written specifically
for someone with no account, drops the visitor on an adult sign-in form with zero guidance. The Grown-ups
door behaves identically.

### Can a minor just sign up anyway?

Yes, up to a point. Nothing before the OAuth button asks about age. A minor with a Google account can
complete sign-in and `POST /api/v1/onboarding` will provision them a `Family` and a guardian `User`
(`api/onboarding.py`). What stops them is downstream, not at the door:

- the row starts at `status="awaiting_approval"`, so a platform admin has to approve it;
- the consent form asks them to attest, by typed legal name, that they are an adult and the child's guardian;
- if `KWS_VERIFICATION_REQUIRED=true`, Epic's Kids Web Services check runs first.

With KWS off (the default), the only real barriers are an unenforceable self-attestation and a human admin.

## Part 2: the guardian's path

Each step below is a real screen, captured in the walkthrough.

### Step 1. Find the signup

There is no signup route. "Continue with Google" on the guardian login page **is** the signup path;
`LoginPage.tsx` says so in a comment. The page never uses the words "create account", "sign up", or "new
account". A first-time guardian has to infer that signing in to an account they do not have will create one.

### Step 2. Verify adulthood (only when KWS is enabled, off by default)

`/guardian/verify`. Explains the legal reason clearly, names Epic's Kids Web Services as the partner,
discloses exactly what data is sent before sending it, and asks for country of residence. Then a
"Check your email" wait screen with a "Check again" button and a 20-second background poll. The copy on this
screen is the best-written in the whole flow.

### Step 3. Wait for admin approval

`/guardian/awaiting-approval`. This is the hardest stop in the flow. The account sits at
`status="awaiting_approval"` until a **platform** admin runs `PATCH /api/v1/admin/users/{id}`. The screen says:

> "A family administrator needs to approve your account before you can start adding profiles or requesting
> stories. This is usually quick, check back soon, or come back after you've heard from them."

Three problems with that:

- **"A family administrator" is wrong.** It is a platform administrator the new family has never met and has
  no relationship with. A guardian reads this as "someone in my family needs to click something" and goes
  looking for a person who does not exist.
- **"heard from them" implies a message is coming.** Nothing in the flow tells the admin a signup is waiting,
  and nothing emails the guardian when approval lands. The only feedback is this page's own poll.
- **No support link and no ETA** on the one screen where a stuck guardian most needs one, even though
  `/support` exists as a public page.

For a genuinely new family with no existing relationship to an operator, this step is a dead end.

### Step 4. Give consent

`/guardian/consent`. Four required inputs: full legal name, guardianship checkbox, country of residence,
adulthood checkbox. The logic is correct and the submit button stays disabled until all four are set.

**But this screen is visually broken.** It renders with no app shell, no logo, no page container, raw
browser-default checkboxes and select, labels butted against their inputs, and a full-bleed button. Next to
the polished login card it looks like an unstyled prototype. This is the legally load-bearing screen in the
product.

Root cause, confirmed in the CSS: the three onboarding interstitials (`/guardian/verify`,
`/guardian/awaiting-approval`, `/guardian/consent`) sit **outside** `GuardianShell` in the router, so they
never get `.guardian-shell__main`'s padding and max-width, and `.console` has no style rule of its own.
Separately, `GuardianConsentPage.tsx` and `GuardianVerificationPage.tsx` apply `guardian-login__field`
without the `cyo-field` design-system class that actually carries the field layout;
`LoginPage.tsx:461` applies both, which is why only the login page looks right.

### Step 5. Land on the family console

`/guardian`. Correct and welcoming: "Add your first reader" with a single call to action. Below it, an
"Invite a co-parent" section, then a "This device / Set up this device for your kids" section.

One inaccuracy: the console tells the guardian "Stories are checked by your family's safety reviewer before
they reach your children." Same problem as Step 3. It is a platform admin, not the family's reviewer.

### Step 6. Add the child

`/guardian/profiles` then "Add child". Everything works, but the dialog presents **17 controls at once**:
name, age band, reading level cap, avatar, read-aloud, reduce animations, weekly reading ring, weekly goal,
badges, pause reading-time tracking, auto-approve requests, monthly auto-approve limit, violence, scariness,
peril, excluded themes, and save. Only **Name** is actually required, and nothing on the form says so. A
first-time guardian is asked to make sixteen policy decisions before they have seen a single story.

By design, no picker PIN is offered at create time; it is an edit-mode-only field.

### Step 7. Authorize the device

Either the console's "Set up this device for your kids" button or `/guardian/devices`. This works well, and
the "Hand device to a child" button correctly signs the guardian out first so a kid device never carries a
guardian bearer token.

Discoverability is the only issue: the device section sits below the co-parent invite, off the first screen
on a laptop, and the console's onboarding nudge points only at profiles.

### Step 8. Get a book

`/guardian/books` says: "No published books yet. Books appear here once a story you request is approved."
Accurate. A new family's shelf is empty, and the only way to fill it is:

request (`/guardian/intake`) → generation → validator gate → moderation → **admin approves and publishes**
(`api/approval.py`, admin-only) → book exists.

This is the **second** blocking dependency on a platform admin, and neither screen warns the guardian it is
coming.

### Step 9. Assign the book (the silent required step)

This is the gap most likely to strand a guardian who has otherwise done everything right.

Publishing a story does **not** put it on any child's shelf. `api/library.py:425` requires an
`EXISTS` match on a `storybook_assignment` row for that exact profile, and the only writer of that row is the
guardian's own `POST /v1/storybooks/{id}/assignments` (`api/assignments.py:328`). Nothing auto-assigns, not
even a story the guardian requested naming a specific child.

Meanwhile the notification the guardian receives says:

> "<Story> is ready on the shelf. It has been approved and published to your family library."

Nothing in that message says "now assign it." A guardian who reads it, hands over the tablet, and watches
their child find an empty library has no reason to suspect a missing step.

### Step 10. The child reads

`/kids` → "Who's reading?" → tap profile (PIN prompt if one was set) → library → read. This part is good.
The kid-facing empty and error states are all written in kid language ("Ask a grown-up to add you!",
"Ask a grown-up to help").

## The flow at a glance

| # | Step | Who acts | Blocking? |
| --- | --- | --- | --- |
| 1 | Land on `/`, pick a door | Visitor | no |
| 2 | Sign in with Google (this is signup) | Guardian | no |
| 3 | KWS adulthood verification | Guardian + Epic | only when `KWS_VERIFICATION_REQUIRED=true` |
| 4 | Account approval | **Platform admin** | **yes, blocks everything** |
| 5 | VPC consent (name, guardianship, country, adulthood) | Guardian | yes |
| 6 | Create child profile | Guardian | yes |
| 7 | Authorize this device | Guardian | yes, for kid reading |
| 8 | Request a story | Guardian | yes |
| 9 | Generate, validate, moderate | System | yes |
| 10 | Approve and publish | **Platform admin** | **yes** |
| 11 | Assign the book to the child | Guardian | **yes, and undocumented in the UI** |
| 12 | Hand device over, child reads | Child | done |

Twelve steps from link to first page read, gated on a platform admin twice, with one required step
(assignment) that no screen or notification tells the guardian about.

## Findings, ranked

| # | Finding | Where | Severity |
| --- | --- | --- | --- |
| 1 | Publishing does not assign. A guardian who does everything right still lands their child on an empty shelf, and the `story_ready` notification does not mention assigning. | `api/library.py:425`, `notifications/registry.py:147` | High |
| 2 | Self-signup dead-ends on a platform admin nobody tells, with no notification either way, no ETA, and no support link on the waiting screen. | `api/onboarding.py`, `GuardianAwaitingApprovalPage.tsx` | High |
| 3 | The consent screen, the legally load-bearing one, renders unstyled: no shell, no container, raw form controls. Verification and awaiting-approval share the defect. | `router.tsx`, `GuardianConsentPage.tsx`, `guardian.css` | High |
| 4 | "New here? Get started", the natural link for a new visitor of any age, leads to an adult sign-in form with no "ask a grown-up" line and no "create account" wording. | `LandingPage.tsx`, `LoginPage.tsx` | Medium |
| 5 | "A family administrator" and "your family's safety reviewer" both describe a platform admin. Guardians will look for a person who does not exist. | `GuardianAwaitingApprovalPage.tsx`, `ConsolePage.tsx` | Medium |
| 6 | The add-child dialog asks 17 questions when only Name is required, with nothing marking which. | `ProfileFormDialog.tsx` | Medium |
| 7 | The kid-facing "Ask a grown-up to set up this device for you" line is the smallest, lowest-contrast text on a page whose heading and subtitle are both adult-voiced. | `LoginPage.tsx` | Medium |
| 8 | No age gate before OAuth. With KWS off by default, the only adulthood checks are self-attestation and the admin gate. | `core/config.py:1159` | Medium |
| 9 | No way back to `/` from the login page. A child who took the Kids door has only the browser back button. | `LoginPage.tsx` | Low |
| 10 | Nothing warns the guardian that a first story takes an admin approval cycle, so the intake page implies a faster result than the pipeline delivers. | `IntakePage.tsx` | Low |

## What already works well

- The kid/grown-up door split on the landing page is immediately legible.
- The KWS verification copy is genuinely good: it names the partner, gives the legal reason, and discloses
  what is sent before sending it.
- Kid-surface empty and error states are all written in kid language.
- The device handoff sheds the guardian session before handing the tablet over, so a kid device never carries
  a guardian bearer token.
- Both the verification and approval waiting screens poll in the background, so neither is a true dead end
  requiring a sign-out and sign-in round trip.
- The child's PIN gate correctly distinguishes a wrong PIN from a server error, so a child typing the right
  PIN during an outage is never told it was wrong.
