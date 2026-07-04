---
title: "User Journeys"
schema_type: common
status: published
owner: core-maintainer
purpose: "Target-state end-to-end user-experience flow for CYO Adventure, from a child asking for a story through guardian and admin approval to reading and rating."
tags:
  - architecture
  - overview
---

The other architecture diagrams describe how the system is built: containers,
components, data model, and API sequences. This page describes what a *person*
does, screen by screen, to get value from the app. It is a product/UX-clarity
view, not an API sequence, so the boxes are user actions and user-facing waits
rather than endpoints and database locks.

## Target-state end-to-end journey

![Target-state end-to-end user journey](diagrams/journey-end-to-end.svg)

### How to read it

- **Columns are who is acting.** The journey deliberately crosses four lanes:
  the **Child** and **Guardian** each drive their own disjoint surface (the kid
  app and the guardian console share no navigation; see
  [router.tsx](../../frontend/src/router.tsx)), the **Admin** holds the mandatory
  approval gate, and **System** collapses the behind-the-scenes generation and
  safety work into user-facing waits.
- **Node fill marks maturity.** White nodes are shipped in the app today.
  Rose nodes are planned target-state steps that are not yet built, so the
  diagram doubles as a gap map. The unbuilt steps line up with the gaps tracked
  in the R1 deployment review.
- **Primary path is child-initiated.** The diagram shows the intended future
  where a child asks for a story and the guardian approves the request. Today
  the entry point is reversed: a guardian starts requests from the Intake page.
  See the note under Act 2.

## The journey, act by act

Each act below names the real screen or route it maps to and whether it is
shipped or planned.

### Act 1: Guardian onboarding (once)

A guardian signs in at `/guardian/login` (email/password or Google today; Apple
sign-in is gated behind a config flag) and creates a profile for each child at
`/guardian/profiles`. Profiles use preset illustrated avatars only, never
uploaded photos. This act runs once and sits outside the repeating story loop.

### Act 2: Requesting a story

**Target state (primary path, planned):** a child opens the kid app, taps their
avatar on the Profile Picker (`/`), taps "I want a new story," and says what it
is about. That request surfaces to the guardian, who approves or tweaks it.

**Shipped today:** the request is guardian-initiated. A guardian uses the Intake
page (`/guardian/intake`) with "Who's it for?" first, then a topic and tone,
then "Request Story." The child-tap entry point and the guardian
request-approval step (the two rose nodes in Act 2) are the not-yet-built delta
between these two flows.

### Act 3: Behind the scenes

The system writes the story through a staged pipeline with a provider fallback
cascade, then runs a deterministic safety check that flags risky passages. To
the guardian this is just a "Generating..." status in their "My Requests" list.
For the engineering detail behind this lane, see the
[generation sequence](diagrams/seq-generation.svg) and the
[generation pipeline](generation-pipeline.md) page.

### Act 4: The approval gate (ADR-005)

This is the single mandatory checkpoint before any story reaches a child. In the
Guardian Console (`/guardian`), the review queue is ordered Flagged, then Ready
to review, then Still processing. Opening a story (`/guardian/review/:id`)
surfaces its flagged passages first, then the full text. The reviewer either
**approves** or **sends it back** with a note; a sent-back story is rewritten and
re-enters the queue (the inner loop in the diagram).

The approve action is the recorded human gate required by
[ADR-005](../planning/adr/adr-005-mandatory-human-approval.md) and is
admin-only: a guardian can monitor the queue but cannot self-approve (the API
returns 403). The diagram places the whole review-and-approve sequence in the
Admin lane to keep that gate visually unambiguous.

### Act 5: Assignment

An approved story is assigned to the child it was written for; "Assign more"
widens it to siblings without re-requesting. On the kid surface, the child's
avatar on the Profile Picker flips to a "new story ready!" status pill.

### Act 6: Reading and rating

The child opens their Library (`/library/:profileId`), which leads with a
"Continue Reading" hero card and a shelf grid, then opens the Reader
(`/read/:profileId/:storybookId/:version`). They read passages and make
branching choices until they reach an ending. Reading is offline-first: if the
device is offline, the child reads from cache and progress waits in a queue,
syncing on reconnect and reconciling if it clashes (see
[offline and reconnect](diagrams/seq-offline.svg) and
[reading-state sync](diagrams/seq-reading-state.svg) for the mechanics). Rating
the finished story is a planned step: completion and rating are not yet recorded
by the UI.

### Loop

Wanting another story returns to the top of the loop (Act 2). Guardian
onboarding in Act 1 is not repeated.

## Shipped vs planned at a glance

| Journey step | Screen / route | Status |
| ------------ | -------------- | ------ |
| Guardian sign-in | `/guardian/login` | Shipped |
| Create child profiles | `/guardian/profiles` | Shipped |
| Child taps "I want a new story" | Profile Picker (`/`) | Planned |
| Guardian approves the child's request | (new) | Planned |
| Generation + safety validation | generation pipeline | Shipped |
| Guardian-initiated request | `/guardian/intake` | Shipped |
| Admin review + approve/send-back | `/guardian`, `/guardian/review/:id` | Shipped |
| Assign / assign more | Intake / assign | Shipped |
| "New story ready!" pill | Profile Picker (`/`) | Shipped |
| Library and Reader | `/library/...`, `/read/...` | Shipped |
| Offline read + reconnect sync | Reader | Shipped |
| Rate the story | Reader ending | Planned |

## Related pages

- [System Overview](system-overview.md): the same three actors as C4 boxes
  rather than journey lanes.
- [Validation and Player](validation-and-player.md): the reader engine and
  offline sync that Act 6 rides on.
- [Generation Pipeline](generation-pipeline.md): the System lane of Act 3 in
  full.
