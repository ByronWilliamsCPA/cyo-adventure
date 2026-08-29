---
title: "Onboarding Overhaul Plan: Link to First Read"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "Two-persona registration walkthrough, 2026-08-14 (docs/qa/onboarding-flow-walkthrough-2026-08-14.md),
  run against commit fc163c5; code trace of router.tsx, auth/*, api/{onboarding,approval,assignments,library}.py."
purpose: "Sequence the work that closes the ten gaps found between a new visitor's first click and a child's first read, and name what is engineering versus what needs an owner ruling."
tags:
  - planning
  - quality_assurance
  - scope
---

> **Amended 2026-08-15, after PR [#720](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/720)
> (merged as `5f38917`) rebuilt the landing page as a sales funnel.** Three consequences, none of which
> change the wave ordering:
>
> 1. **Wave 2 got more urgent, not less.** #720 builds a conversion funnel whose every CTA lands on
>    self-signup, which lands in `awaiting_approval`, a queue nobody is notified about in either
>    direction. Its "We approve each new family by hand" copy sets the expectation honestly, which helps;
>    the loop (`UW-J29`, `UW-J30`) is still open, and more families will now reach it.
> 2. **Wave 2 item 2a (`UW-J28`) is done**, and grew before it closed: #720 promoted the same
>    reviewer misattribution to the homepage and added a claim that approval puts a book on a child's
>    shelf. Both are corrected, with mutation-verified tests.
> 3. **Wave 4 item 4a (`UW-J32`) is mostly done**, closed incidentally by #720 rather than by this plan.
>    Its residual is narrower and is now Low.
>
> Waves 1, 3, and 5 are untouched by #720 and stand exactly as written below.

## What this plan is for

The [registration walkthrough](../qa/onboarding-flow-walkthrough-2026-08-14.md) found ten gaps across
twelve steps. This document turns them into scheduled work. It does not re-argue the findings; read that
document first for the evidence behind each one.

Two framing constraints shape the sequencing:

- **Two gaps stop a family cold; eight make the product feel unfinished.** A family that cannot complete
  the journey is a different class of problem from one that completes it while noticing rough edges. The
  first class goes first, and nothing else in this plan is allowed to jump ahead of it.
- **Two items are owner rulings, not engineering.** They are isolated in Wave 0 so the code waves never
  wait on a decision that was never asked for, and so the plan does not quietly pre-decide them.

Every item carries a register ID. The rows are filed in cluster J (remediation-plan and console gaps) of
the [unscheduled work register](./unscheduled-work-register.md), alongside `UW-J01`, which the
2026-07-17 persona audit raised against this same flow.

## A correction that changes the critical path

`UW-J01` (auto-assign-on-publish) has sat at status `blocked` since 2026-07-28, and
[remediation-plan-2026-07-17.md](./remediation-plan-2026-07-17.md) records the blocker as "auto-assign
needs a schema migration threading `requested_by_profile_id` request -> concept -> storybook (no such link
exists)."

**That blocker no longer exists, and the highest-severity finding in the walkthrough is therefore
schedulable today with no migration.** The link is complete in the shipped schema:

- `story_request.profile_id` (`db/models.py`) holds the requesting child profile.
- `story_request.resulting_storybook_id` holds the storybook the request produced.
- `publishing/service.py::approve` already calls `_stamp_resulting_storybook_id` and emits
  `EventType.RELEASED` at the exact point an auto-assign hook would run, so both ends of the link are in
  scope of one function.

The column exists under the name `profile_id` rather than the `requested_by_profile_id` the blocker
named, which is the likeliest reason the row was never re-checked. `UW-J01` moves to `unscheduled` in
the same change that lands this plan.

## Wave 0: rulings needed before Wave 2 can be specified

No code. Both items are genuine decisions with defensible answers either way, and both change what gets
built rather than merely when.

### D1. Does an uninvited self-signup stay behind the admin approval gate?

**Register: `UW-J24` (decision, owner: project owner).**

Today every uninvited self-signup lands at `status="awaiting_approval"` and waits for a platform admin
(`api/onboarding.py`). For the current invite-shaped deployment that is coherent. For anything
resembling public signup it is a dead end: the new family has no relationship with the admin, no channel
to reach them, and nothing notifies either party in either direction.

The ruling decides Wave 2's shape entirely:

- **Keep the gate** and Wave 2 is a notification and queue problem: tell the admin a signup landed, tell
  the guardian when it clears, and give the admin a real queue instead of an unfiltered user list.
- **Open the gate for uninvited self-signup only** and Wave 2 is a compensating-controls problem: the
  guardian-created invite path must keep its gate (`api/onboarding.py` documents exactly why: a guardian
  can name any address and would otherwise capture a stranger into their family), and the abuse surface
  that approval was implicitly covering needs naming before it is removed.

Do not read this plan as recommending either. It is an abuse-posture and compliance question that sits
next to ADR-018's still-open VPC method decision (`UW-N02`, `UW-A52`), and the walkthrough deliberately
did not pre-judge it.

### D2. Is `kws_verification_required` turned on, and does an age affirmation ship regardless?

**Register: `UW-J25` (decision, owner: project owner with privacy counsel).**

`kws_verification_required` defaults to `False` (`core/config.py:1159`), so on a default deployment the
only adulthood checks are an unenforceable self-attestation on the consent form and the admin gate that
D1 may remove. If D1 opens the gate while D2 leaves verification off, the product has no adulthood check
at all, which is the one combination this plan flags as unsafe to ship.

The flag flip itself is counsel-gated and already tracked (`UW-M03`, `UW-N02`). What is **not** gated,
and is proposed here as unconditional Wave 4 work, is a plain age affirmation before the OAuth button:
cheap, honest about what it is, and it does not pretend to be verification.

## Wave 1: a published book reaches the child it was written for

The walkthrough's finding 1, and the only work in this plan that can strand a guardian who did everything
correctly. Independent of both Wave 0 rulings. Ship first.

### 1a. Assign on publish, from the request that produced the book

**Register: `UW-J01` (existing row, unblocked above). Phase 4b. Capabilities: G16, K12, S8.**

In `publishing/service.py::approve`, after `_stamp_resulting_storybook_id` and before the `RELEASED`
event, resolve the `story_request` whose `resulting_storybook_id` is this storybook and whose
`profile_id` is non-null, then create the `storybook_assignment` row for that profile.

Three constraints the implementation must honor, all of which already exist and must be reused rather
than reimplemented:

- **The age-band ceiling.** `api/assignments.py::assign_storybook` rejects a book banded above the target
  profile (the H1 fix, capability K13). The auto-assign path must go through the same check, and a
  band rejection must fail the assign, not the publish.
- **Idempotency.** Assigning is already add-only and idempotent; a re-approval or a retried publish must
  not double-write.
- **The event.** Emit `BOOK_ASSIGNED` so the existing `_compose_book_assigned` notification fires, which
  is what makes 1b's copy split work.

Explicitly out of scope: catalog books, multi-child families, and profile-less requests still need an
explicit guardian assign. Auto-assign closes the single-child request path, which is the first-run path;
it does not remove the assign control.

### 1b. Stop the notification claiming a shelf it did not reach

**Register: `UW-J23`. Phase 4b. Capabilities: G10, S9.**

`notifications/registry.py` has two composers and the wrong one carries the first-run case.
`_compose_book_assigned` says "ready to read" and is correct. The `story_ready` composer says "It has
been approved and published to your family library", which a guardian reasonably reads as "it is on the
shelf" when it is not.

Rewrite the published-but-unassigned message to name the remaining step and link to the assign control.
After 1a lands this case is rarer, but it is not gone (catalog books, second children, profile-less
requests), and a rare wrong message is worse than a common one because nobody is looking for it.

### 1c. Make an unassigned book visible as unassigned

**Register: `UW-J26`. Phase 4b. Capability: G16.**

`frontend/src/guardian/BooksPage.tsx` lists published books without distinguishing one on a child's shelf
from one on nobody's. Add the state and a direct assign affordance. This is the recovery path for any
guardian who already hit the gap, including anyone who hit it before 1a shipped.

### 1d. Pin the whole path

**Register: `UW-J27`. Phase 4b.**

An `e2e-real` spec that walks request to publish to the child's library and asserts the book is readable
with **no manual assign step**, plus an integration test that a band-exceeding auto-assign is refused
while the publish still succeeds. Without 1d, 1a is a behavior nothing holds in place.

## Wave 2: self-signup terminates

Blocked on D1. The copy correction below is the exception and ships immediately, because it is wrong
under either ruling.

### 2a. Correct who approves and who reviews

**Register: `UW-J28`. Phase `now`. No dependency on D1.**

Two strings describe a platform admin as though they were family:
`GuardianAwaitingApprovalPage.tsx` ("A family administrator needs to approve your account") and
`ConsolePage.tsx` ("your family's safety reviewer"). Both send a guardian looking for a person who does
not exist. Fix the wording, and add the existing public `/support` link to the waiting screen, which is
the one screen where a stuck guardian has nowhere to go.

### 2b. Close the notification loop in both directions

**Register: `UW-J29`. Phase 4b. Blocked on D1. Capabilities: G10, A12, S9.**

Only meaningful if D1 keeps the gate. Nothing currently fires when a signup lands, and nothing fires when
it clears; `EventType` has `USER_MANAGED` but no signup event, and the notification feed is family-scoped
to guardians with no admin-facing channel.

Needs: a signup event, an admin-facing delivery path for it (the first admin-scoped notification, so this
is where the family-scoping assumption in `notifications/service.py` gets its first real test), and a
guardian-facing notification on approval so the waiting page's poll stops being the only feedback.

### 2c. Give the admin a queue rather than a list

**Register: `UW-J30`. Phase 4b. Blocked on D1. Capability: A12.**

`admin/UserManagementPage.tsx`'s Users tab lists users with no status filter and no pending-accounts
view, so approving a signup means knowing to go looking for one. Add the filtered queue and a count on
the admin console home.

## Wave 3: the onboarding screens look finished

Independent of every other wave and of both rulings; touches disjoint files, so it can run in parallel
with Wave 1 rather than queueing behind it.

### 3a. Give the three interstitials a shell

**Register: `UW-J31`. Phase `now`. Capability: G11 (adjacent).**

`/guardian/verify`, `/guardian/awaiting-approval`, and `/guardian/consent` sit outside `GuardianShell`
in `router.tsx`, which is correct and must stay that way: each one exists precisely because the guardian
cannot yet pass `ProtectedRoute`. What is not correct is that they inherit no page container at all, so
they lose `.guardian-shell__main`'s padding and max-width and `.console` has no rule of its own.

The fix is a minimal `OnboardingShell` (brand, container, theme toggle, no nav and no authenticated
data) wrapping the three routes inside the existing `GuardianAuthLayout`. Do not solve this by moving
the routes under `GuardianShell`; that would reintroduce the `/v1/me` dependency the routes' own
docstrings explain they must not have.

In the same change: `GuardianConsentPage.tsx` and `GuardianVerificationPage.tsx` apply
`guardian-login__field` without the `cyo-field` design-system class that carries the field layout.
`LoginPage.tsx:461` applies both. Add it, and add a visual-regression snapshot for the consent page so a
legally load-bearing screen cannot silently regress to unstyled again.

## Wave 4: a first-time visitor knows what to do

Lower severity, and the wave where the walkthrough's minor persona is finally served.

### 4a. Make "Get started" a signup path

**Register: `UW-J32`. Phase 4b.**

"New here? Get started" and the Grown-ups door both land on a page headed "Guardian sign-in" whose only
kid-facing line is gated behind the `intent=authorize-device` parameter neither of them carries. Give the
landing page's new-visitor link its own intent, render signup-appropriate copy for it (including that
"Continue with Google" creates the account, which the page never says), and add the "this is for
grown-ups" line to that variant too.

Also in scope, both one-liners: a link back to the landing page from the login card, and raising the
kid-facing line out of the smallest, lowest-contrast slot on a page whose heading and subtitle are both
adult-voiced.

### 4b. Age affirmation before OAuth

**Register: `UW-J33`. Phase 4b. Informed by D2, not blocked on it.**

A plain "are you a grown-up?" affirmation before the OAuth button. It is not verification and the copy
must not imply it is. It ships regardless of D2's ruling, and if D1 opens the approval gate it becomes
the only pre-account check standing.

### 4c. Ask for a name, then offer the rest

**Register: `UW-J34`. Phase 4b. Capabilities: G2, G3, G19.**

`ProfileFormDialog.tsx` presents seventeen controls where only Name is required. Every one of them is a
capability somebody asked for (G2 content limits, G3 request permissions, G19 gamification), so the fix
is disclosure, not removal: name and age band up front, everything else behind an "Advanced" section that
states the defaults it is applying. Edit mode may stay expanded.

### 4d. Say how long the first story takes

**Register: `UW-J35`. Phase 4b. Capability: K12/G10 adjacent.**

`IntakePage.tsx` implies a faster result than the pipeline delivers, because nothing tells the guardian a
generation and review cycle stands between the request and the shelf. Set the expectation at the point of
request, and give the empty console a first-run checklist showing the real remaining sequence: profile,
device, request, and (for the cases 1a does not cover) assign.

## Wave 5: the flow cannot silently regress

**Register: `UW-J36`. Phase 5.**

`frontend/e2e/naive-user/` covers kid, guardian, and admin misuse but has no first-run journey, which is
why a twelve-step flow with two blocking gates and a silent required step was found by hand rather than
by the suite. Add a first-run spec that walks the whole path, and append the missing signed-out
first-visit scenario object (with all required fields) to `.claude/skills/naive-ux-check/scenarios.json`'s
guardian set so the comprehension set covers signup rather than starting from an existing account.

## Sequencing summary

| Wave | Items | Depends on | Ships when |
| --- | --- | --- | --- |
| 0 | D1, D2 | nothing | owner rulings, no code |
| 1 | 1a-1d | nothing | first, ahead of everything |
| 2 | 2a | nothing | immediately, with Wave 1 |
| 2 | 2b, 2c | D1 | after the ruling |
| 3 | 3a | nothing | parallel with Wave 1, disjoint files |
| 4 | 4a-4d | 4b informed by D2 | after Wave 1 |
| 5 | 5 | Waves 1-4 landed | last, as the regression pin |

Waves 1, 2a, and 3 together take a brand-new family from "stuck with an empty shelf and an unstyled
consent form" to "completes the journey", and none of them wait on a decision. That is the smallest
shippable set worth calling the overhaul.

## What this plan does not do

- **It does not decide D1 or D2.** Both are recorded as decisions with named owners rather than resolved
  by default, which is the failure mode the register exists to prevent.
- **It does not touch the pipeline itself.** Step 10 (admin approves and publishes) is a mandatory human
  gate by ADR-005 and stays one. The finding was that nobody warns the guardian it is coming, not that it
  should be removed.
- **It does not mint a capability ID.** No row in the capability register covers first-run account
  creation as a capability in its own right (G14 is adult auth, G1 is profiles). Whether that gap deserves
  a new `G*` row is worth an owner ruling, but minting one unasked would put an unratified capability into
  a register whose IDs are treated as commitments.
