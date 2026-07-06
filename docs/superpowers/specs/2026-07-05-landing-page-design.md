---
title: "Root Landing Page: Kid and Guardian Doors (Design)"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "Brainstorming session 2026-07-05; frontend/src/router.tsx two-tree route comments; naive-UX findings 2026-07-05 (K1/G1/G2 onboarding and entry-point friction)."
purpose: "Give cyo.williamshome.family a landing page at / with clear entry points to the kid surface, the guardian console, and (via the guardian door) admin capabilities, replacing the kid profile picker as the root route."
tags:
  - planning
  - project
---

> Date: 2026-07-05 | Author: Byron Williams (with Claude)

## Problem

Visiting the bare domain drops every visitor onto the kid profile picker. A kid
cannot do anything until a guardian has signed in and set up profiles, yet the
guardian entry point (`/guardian/login`) is undiscoverable from the root. The
2026-07-05 naive-UX passes flagged exactly this class of entry-point confusion.
There is no admin surface to link to: admins are guardians with extra powers
and use the same console.

## Decision Summary

- The landing page owns `/`. The kid profile picker moves to `/kids`.
- Two doors, not three: **Kids** and **Guardians**. The guardian card notes
  "Admins sign in here too" because admin is a role inside the guardian
  console, not a separate page.
- Visual scope is simple styled cards using existing design-system components.
  No hero art, no marketing copy.

## Approach (selected: A, pathless-parent reshuffle)

The root route keeps `path: '/'` but loses its element. Its children become:

1. `{ index: true }`: the new `LandingPage`, its own lazy chunk, rendered
   outside `KidShell` so the grown-up-forward landing does not inherit kid
   chrome or `kid.css`.
2. A pathless `KidShell` wrapper holding:
   - `kids`: the relocated `ProfilePickerPage`
   - `library/:profileId`: unchanged URL
   - `read/:profileId/:storybookId/:version`: unchanged URL

Kid deep links keep their exact URLs; only the picker moves. `errorElement`
stays on the root route so a lazy-chunk load failure still degrades to the
app-consistent fallback.

Rejected alternatives: rendering the landing inside `KidShell` (muddies the
deliberate two-surface separation documented in `router.tsx`), and moving the
whole kid tree under `/kids/*` (churns every kid bookmark and e2e spec for no
user-visible benefit).

## Components

### `frontend/src/landing/LandingPage.tsx` (new)

App name, one-line tagline, two large tappable door cards:

- **Kids: start reading** -> `/kids`
- **Grown-ups: guardian console** -> `/guardian`, with the admin note line.
  Targeting `/guardian` rather than `/guardian/login` lets `ProtectedRoute`
  do the work: signed-out visitors bounce to login, an already-signed-in
  guardian lands straight on the console.

Registered in `routeElements.tsx` as a lazy export like every other page.

### `frontend/src/routes.ts`

Add `KID_PICKER_PATH = '/kids'` beside `GUARDIAN_LOGIN_PATH` so the router,
the landing card, and the reader fallback share one source of truth.

### Touch-ups

- `frontend/src/reader/ReaderRoute.tsx:49`: fallback `navigate('/')` becomes
  `navigate(KID_PICKER_PATH)`.
- `frontend/e2e/profiles.spec.ts` (and any sibling spec that starts at `/`
  expecting the picker) retargets to `/kids`.

## Error Handling

No new error surface. The landing page is static (no data fetching, no auth).
Chunk-load failure is covered by the existing root `errorElement`.

## Testing

- New `LandingPage.test.tsx`: both doors render; links point at
  `KID_PICKER_PATH` and `/guardian`.
- Router/App tests updated: `/` renders the landing, `/kids` renders the
  picker, `/library/:id` and `/read/...` unchanged.
- Retarget affected Playwright specs, then run the FULL unit and e2e suites,
  not only edited files (per the PR #135 lesson).

## Out of Scope

Hero art and marketing copy, a real `/admin` route or alias, any auth or
role changes, redirects from `/` history states (there are none: `/` was the
picker and remains a valid, now-different page).
