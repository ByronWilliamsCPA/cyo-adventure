---
title: "Naive-User UX Test Design: Playwright Misuse Regressions and Claude-for-Chrome Comprehension Prompts"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "Brainstorming session 2026-07-05; frontend/e2e/* and frontend/e2e-real/* existing suite (PR #112); frontend/src/router.tsx kid/guardian route map; src/cyo_adventure/api/{story_requests,approval,generation,profiles,assignments}.py."
purpose: "Design a naive-user UX test suite across kid, guardian, and admin personas: deterministic misuse scenarios become Playwright regression specs, comprehension/discoverability scenarios become Claude-for-Chrome prompts run through a reusable skill, since the two failure classes cannot both be caught by DOM assertions."
tags:
  - planning
  - testing
  - project
---

> **Status (2026-07-10)**: Partially superseded. The Section 4 route map and the
> Track B expected observations describe the app as of 2026-07-05. PR #140 (the
> landing page at `/` and the `/kids` profile picker) and PR #185 (the persistent
> KidNav bar, the reader "Leave" control, and the reordered library) have since
> changed the kid surface those sections describe. Two further points have moved
> since 2026-07-05: (1) the Track A specs this doc plans as future work already
> exist on `main` (`frontend/e2e/naive-user/*`, added by PR #132 and kept current
> through PR #185), so Sections 5, 8, and 9 read as a plan for work that has since
> been delivered; (2) the Section 5 and Section 10 analysis of `approval.py`'s
> storybook-approve as an unguarded concurrency gap is no longer accurate. A
> `SELECT ... FOR UPDATE` row lock was added to close issue #129 (see
> `_load_admin_story` in `src/cyo_adventure/api/approval.py`), so both "approve"
> endpoints are now guarded; the `story_requests.py` half of that comparison, and
> the backend code line citations (which reflect 2026-07-05), are otherwise
> unchanged in substance. The Track A and Track B methodology, the scenario
> inventory, and the promotion rules remain live.
>
> Date: 2026-07-05 | Author: Byron Williams (with Claude)

## 1. Problem

The existing Playwright suite (`frontend/e2e/*`, hardened through PR #112) is a
**functional-correctness suite**: for each journey it proves the happy path
completes and, in a few places, that one deliberate error case is handled
(the reader's 409 conflict in `reader-conflict.spec.ts`, the ADR-005
guardian-403 case in `guardian-review.spec.ts`). Every spec is written and run
by someone who already knows the intended flow.

Nobody has designed tests from the other side: what does a person who has
**never seen this app and received no instructions** actually try to do? Kids
share tablets and mash buttons; a first-time guardian doesn't know that
"requests," "review," and "books" are three different concepts; nobody has
checked whether the admin surface is even visually distinguishable from the
guardian surface it's built on top of, since no dedicated admin UI exists.

This class of gap splits into two kinds that need different tools:

1. **Deterministic misuse**: the correct behavior is known and stable
   (double-submitting a form should not create two records; a stale session
   token should fail closed). These are ordinary regression tests once
   written; Playwright is the right tool.
2. **Comprehension and discoverability**: whether a behavior is "confusing" or
   "discoverable" is not a DOM assertion, it requires judgment about what a
   human would understand. Playwright cannot express "the user didn't realize
   what to click next." An agent driving a real browser off a persona prompt,
   and reporting back a narrative, can.

## 2. Goals

1. Enumerate naive-user scenarios across all three personas (kid, guardian,
   admin), grounded in the routes and endpoints that actually exist today
   (Section 4), not a hypothetical future UI.
2. Split scenarios into Track A (Playwright, Section 5) and Track B
   (Claude for Chrome, Section 6) by which kind of correctness they test, and
   avoid duplicating anything the existing suite (Section 4.4) already covers.
3. Define a reusable skill (Section 7) that surfaces the Track B prompt set on
   demand, so this becomes a repeatable pre-release routine rather than a
   one-off exercise.

## 3. Non-goals

- Not replacing or restructuring the existing functional e2e suite; this work
  adds a parallel `frontend/e2e/naive-user/` tree, it does not touch
  `frontend/e2e/*` or `frontend/e2e-real/*`.
- Not automating the Claude-for-Chrome runs themselves. No browser-driving
  tool is available to this session; the skill hands a human a ready-to-paste
  prompt and a place to log the response, it does not invoke the extension.
- Not covering native mobile or non-Chromium browsers; both tracks target the
  same web app the existing suite already targets.
- Not scoring or gating CI on Track B results. Track B findings are read by a
  person and, where they reveal a genuine repeatable bug, get promoted into a
  new Track A spec in a follow-up change; Track B itself never blocks a merge.

## 4. Existing surface and coverage baseline

### 4.1 Kid routes (`frontend/src/router.tsx`, path constants in `frontend/src/routes.ts`)

Since PR #140 the root `/` is the audience-neutral landing page (the Kids and
Grown-ups doors), not the profile picker. The kid surface now begins one level
in: `/kids` (`ProfilePickerPage`, the `KID_PICKER_PATH` constant) →
`/library/:profileId` (`LibraryPage`, includes `RequestStory.tsx`) →
`/read/:profileId/:storybookId/:version` (`ReaderRoute`), all mounted under the
pathless `KidShell` wrapper. Backend: `POST /v1/story-requests`
(`api/story_requests.py:149`), `GET /library` (`api/library.py:243`), reading
state and completions (`api/reading.py:120/154/285`), ratings
(`api/ratings.py:38/93`).

### 4.2 Guardian routes (all under `/guardian/*`, `ProtectedRoute` roles `['guardian','admin']`)

`LoginPage`, `ConsolePage` (review-queue landing), `IntakePage`
(`/guardian/intake`, concept intake and generation trigger), `BooksPage`
(`/guardian/books`, sibling assignment), `RequestsPage`
(`/guardian/requests`, approve/decline kid requests), `ProfilesPage`
(`/guardian/profiles`, child CRUD), `ReviewDetailPage`
(`/guardian/review/:storybookId`, approve/send-back/archive per ADR-005).

### 4.3 Admin surface

No dedicated admin route tree exists. Admins reuse every `/guardian/*` page
under role `admin`; the only differences are server-side gates on specific
actions (the review queue's contents, the approve action in
`ReviewDetailPage`, per `approval.py:105`). Generation is triggered from
`IntakePage` (`POST /concepts`, `POST /concepts/{id}/generate`,
`api/generation.py:123/179`) and polled via `GET /generation-jobs/{job_id}`
(`api/generation.py:338`).

### 4.4 What the existing suite already covers

`frontend/e2e/`: `profiles.spec.ts`, `library.spec.ts`, `reader.spec.ts`,
`reader-conflict.spec.ts` (deliberate offline/409 handling),
`story-requests-kid.spec.ts`, `story-requests.spec.ts`, `guardian-auth.spec.ts`,
`guardian-console.spec.ts` (auth redirect guard), `guardian-books.spec.ts`,
`guardian-profiles.spec.ts` (guardian's own profile CRUD only, three tests:
create with preset avatar, edit reading cap, avatar presets-only; does not
visit any kid-side `/library/:profileId` route), `guardian-review.spec.ts`
(includes the ADR-005 guardian-403-on-approve case), `intake.spec.ts`,
`assignments.spec.ts`.
`frontend/e2e-real/`: `approval-flow.spec.ts`, `kid-reads.spec.ts`.

This is the baseline the two tracks below are diffed against: any scenario
already exercised by one of these files is dropped rather than duplicated.

## 5. Track A: Playwright misuse regressions

> Delivered (PR #132, kept current through PR #185): the plan below described
> a directory yet to be created; `frontend/e2e/naive-user/` and its four spec
> files now exist on `main` as planned. Retained as historical planning
> context per the status banner above.

New directory `frontend/e2e/naive-user/`, one file per persona plus one
shared file, mocked-network style matching the existing suite.

| Spec file | Persona | Scenario | Assertion |
| --- | --- | --- | --- |
| `naive-kid-misuse.spec.ts` | Kid | Double-submit a story request | Exactly one request record created; second submit is a no-op or disabled control |
| `naive-kid-misuse.spec.ts` | Kid | Refresh mid-reader (accidental, not the deliberate offline case in `reader-conflict.spec.ts`) | Reading position is not lost on a clean refresh |
| `naive-kid-misuse.spec.ts` | Kid | Rate a story before finishing it, then rate it again | Only the latest rating persists; no duplicate rating rows |
| `frontend/e2e-real/naive-kid-misuse-real.spec.ts` (real-backend tier, not mocked) | Kid | Hand-edit `/library/:otherProfileId` to a sibling's or stranger's profile | The mocked tier cannot test this: `library.py:262`'s `authorize_profile(principal, parsed)` is the actual guard and only runs against a real backend. Moved out of `naive-kid-misuse.spec.ts` for that reason |
| `naive-guardian-misuse.spec.ts` | Guardian | Two guardian sessions approve the same story *request* concurrently (`POST /story-requests/{id}/approve`) | Second approver gets 409 (stale transition); confirmed guarded server-side by a `SELECT ... FOR UPDATE` row lock in `_load_scoped_request(..., for_update=True)` |
| `naive-guardian-misuse.spec.ts` | Guardian | Visit `/guardian/books` or `/guardian/requests` with zero child profiles | Page renders a coherent empty state, not an unhandled error |
| `naive-admin-misuse.spec.ts` | Admin | Navigate away mid-generation-job, return later without the job ID | The job is still locatable from the console/queue by content, not just by URL |
| `naive-admin-misuse.spec.ts` | Admin | Attempt approve as a guardian-role session (re-confirms `guardian-review.spec.ts`'s existing 403 case from this suite's angle) | 403, fails closed, no partial state change |
| `naive-admin-misuse.spec.ts` | Admin | Two admin sessions approve the same *storybook* concurrently (ADR-005 gate, `approval.py`'s `/approve`, distinct from the request-approve endpoint above) | Confirmed gap, not a guarded path: `approve_storybook` loads the row with a plain `session.get`, no `FOR UPDATE`/version check, so both calls silently succeed (last-write-wins on `approved_by`/`published_at`). Test is a characterization of current behavior, not an assertion of a guard that doesn't exist; pair with a filed backend issue recommending the same row-lock pattern already used in `story_requests.py`. **Superseded (2026-07-10):** this gap is now closed. `approve_storybook` loads through `_load_admin_story`, which issues `SELECT ... FOR UPDATE` (`src/cyo_adventure/api/approval.py`, per issue #129), so concurrent approvals no longer race. The characterization test should now assert the guard (the second approver gets a 409), and the recommended backend issue is unnecessary. |
| `naive-misuse-shared.spec.ts` | All (parametrized) | Double-click every primary submit button (request, approve, generate, assign) | No duplicate record from any of the four actions |
| `naive-misuse-shared.spec.ts` | All (parametrized) | Browser back after a successful submit, then resubmit | No duplicate record (re-POST protection) |
| `naive-misuse-shared.spec.ts` | All (parametrized) | Hand-typed URL directly into a mid-flow page, skipping the preceding step | Redirects to the correct starting point or shows a clear guard, not a broken page |
| `naive-misuse-shared.spec.ts` | All (parametrized) | Session/token expiry mid-task, form partially filled | User is redirected to sign-in without a silent data loss the UI never mentions |

**Verified during implementation planning:** `guardian-profiles.spec.ts`
exercises only the guardian's own profile CRUD page; nothing in the existing
suite visits a kid-side `/library/:otherProfileId` route for a profile the
signed-in session does not own. The hand-edit cross-profile scenario is
confirmed net-new, and (per the table above) belongs in the real-backend
tier rather than the mocked one, since the guard it exercises is
server-side authorization, not frontend behavior a mock can stand in for.

## 6. Track B: Claude-for-Chrome comprehension prompts

One markdown file per persona under
`.claude/skills/naive-ux-check/prompts/`, each containing one prompt block per
scenario. Every prompt follows the same shape: a persona framing with an
explicit knowledge boundary, a task with no hints beyond what's on screen, and
a fixed four-question rubric so responses are comparable across runs.

### 6.1 Scenario list

| Persona | Scenario | What the response should reveal |
| --- | --- | --- |
| Kid | Cold start, zero profiles exist yet | Whether there's any usable next step at all |
| Kid | Empty library, first action is "request a story" | Whether the concept of a request is understandable with zero context |
| Kid | Garbage-input request (single word, mashed keys) | Whether the resulting pending-approval state reads as sensible to a child |
| Kid | Sibling switches profile mid-session | Whether the switch feels like a clean reset or a confusing leftover state |
| Guardian | First login, zero children | Whether the nudge toward creating a profile is discoverable unaided |
| Guardian | Edge-case profile creation (long name, emoji, duplicate name) | Whether feedback on unusual input is clear |
| Guardian | Requests vs. review vs. books | Whether the three concepts read as distinct or get conflated |
| Guardian | Approve a kid's request, unaware a second review step exists later | Whether the two-step approval flow is surfaced anywhere |
| Guardian | Use intake thinking it approves the kid's request | Whether intake vs. request-approval is distinguishable from the page alone |
| Guardian | Decline a story, then try to find it again | Whether the declined item's fate is discoverable |
| Guardian | Hand the device to your kid after your own setup | Whether the path from guardian console to child reading screen is discoverable unaided |
| Admin | Compare the admin console to a guardian's | Whether elevated capability is visible at all |
| Admin | Minimum-viable intake, every optional field skipped | Whether the flow still makes sense with nothing but the required fields |
| Admin | Approve a just-generated story without opening any flagged passage | Whether the review UI resists a zero-look rubber-stamp approval |

### 6.2 Prompt format (worked example)

```text
Persona: You are a 7-year-old using this app for the first time, unsupervised,
with no instructions. You don't know what "profile," "story request," or
"guardian approval" mean beyond ordinary vocabulary.

Task: Go to <URL>. Try to find and read a story. If none is available, try
to get one made for you, using only what's visible on screen, no guessing
at hidden menus or URLs.

Report back:
1. What you clicked, in order, and why at each step.
2. Any point you were unsure what to do, or what a label/button meant.
3. Any dead end you hit.
4. If you succeeded, how many steps it took and whether any felt unnecessary.
```

A second worked example, for the guardian three-page conflation scenario:

```text
Persona: You are a parent who just created an account. Nobody explained the
app to you. You know your child wants to read a story you haven't seen yet.

Task: Go to <URL>, sign in, and do whatever seems necessary so your child can
read something new. Stop as soon as you believe you've either succeeded or
hit a wall.

Report back:
1. Which pages you visited, in order, and what you expected each one to do
   before you clicked into it.
2. Whether you could tell "requests," "review," and "books" apart, or thought
   any two of them did the same thing.
3. Whether you found the thing you were looking for, and how long it took.
4. Anything you clicked that turned out to do something you didn't expect.
```

The remaining eleven prompts follow this shape; the full set is authored
during implementation, not in this design doc.

## 7. The `/naive-ux-check` skill

New project-local skill at `.claude/skills/naive-ux-check/`:

- `SKILL.md`: describes the skill, takes an optional target URL (default
  local dev), and on invocation lists the Track B scenarios with a run/not-run
  status, then prints the next unrun prompt ready to paste into the
  Claude-for-Chrome extension.
- `prompts/{kid,guardian,admin}.md`: the persona prompt files from Section 6.
- After the user pastes back a response, the skill appends it to
  `docs/qa/naive-ux-reports/YYYY-MM-DD.md`: one row per scenario with a
  pass / friction-found / dead-end verdict and the verbatim narrative.
- No browser-driving tool is invoked by the skill itself (Non-goals, Section
  3); it is a prompt organizer and a findings log, not an automation harness.

## 8. Documentation follow-through

- Now that the Track A specs are delivered (see status banner above), no
  coverage-diagram change was needed; they are additive regression coverage,
  not new user-facing journeys.
- Track B findings that reveal a confirmed, repeatable bug get filed as a
  normal GitHub issue and, where warranted, promoted into a new Track A spec
  in a follow-up change (Non-goals, Section 3).
- CHANGELOG entry per the repo's changelog gate once implementation lands.

## 9. Delivery

- This design doc: branch `docs/naive-user-ux-testing-design`, based on
  `main` at the current HEAD.
- Suggested implementation order: Track A specs first (self-contained,
  mechanical, matches the existing suite's style), then the Track B prompt
  files, then the skill that wires them together, since the skill's only job
  is to surface files that need to exist first.
- Each Track A step lands with the full frontend gate green: `npm run lint`,
  `npm run typecheck`, `npm run test:run`, `npm run test:e2e`.

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| Track B narrative feedback is inherently subjective, findings could be noise | The fixed four-question rubric keeps responses comparable; only findings that reproduce on a second run get promoted to Track A |
| The two "approve" endpoints in this domain behave differently under concurrency and are easy to conflate | Verified directly: `story_requests.py`'s request-approve uses `.with_for_update()` and is properly guarded (409 on stale transition); `approval.py`'s ADR-005 storybook-approve has no such guard. Section 5 keeps them as two separate table rows, targeting the correct endpoint by name rather than a shared "approve" scenario. **Superseded (2026-07-10):** `approval.py`'s storybook-approve is now also guarded by a `SELECT ... FOR UPDATE` lock (issue #129); the "has no such guard" statement above reflected the 2026-07-05 code only |
| The cross-profile kid-route scenario may already be covered, wasting effort if duplicated | Section 5 explicitly calls out checking `guardian-profiles.spec.ts` first |
| The skill's manual paste-and-log loop is friction-heavy compared to full automation | Accepted for now (Non-goals, Section 3); revisit if a Claude-for-Chrome automation tool becomes available to this session |
