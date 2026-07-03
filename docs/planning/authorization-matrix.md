---
title: "Authorization Matrix"
schema_type: planning
status: active
owner: core-maintainer
purpose: "Document the endpoint-level authorization model, role mapping, and IDOR negative tests for CYO Adventure."
tags:
  - planning
  - architecture
component: Development-Tools
source: "docs/planning/tech-spec.md sections Security, Authorization, API Specification (2026-06-20)"
---

# Authorization Matrix

> **Status**: Active | **Version**: 0.2 | **Updated**: 2026-07-03

## Overview

Authorization is enforced server-side on every endpoint. The Supabase OIDC (ADR-009)
token subject maps to an allowed set of profiles. A guardian may act on any profile
within their own family. A child token is scoped to reader and library endpoints and may
only act on its own assigned profile. `profile_id` is never trusted alone.

Approval is a single state-machine transition reserved for the global admin role
(`Role.ADMIN` / `is_admin`). A guardian or child token that calls the approve endpoint
receives 403 regardless of the `profile_id` in the request. There is no separate publish
transition: the single approve action stamps `approved_by` and `published_at` and returns
`status='published'` (approve and publish in one call).

---

## Action-by-Role Table

| Action | Admin | Guardian | Child (own profile) | Enforcement |
|--------|-------|----------|---------------------|-------------|
| Read own library / story / state | Any profile | Any family profile | Own profile only | Token subject maps to allowed-profile set; 403 otherwise |
| Write own reading state | Any profile | Any family profile | Own profile only | Same, plus `state_revision` and version guards on the PUT |
| Record a completion | Any profile | Any family profile | Own profile only | `ending_id` must belong to the cited published version |
| Generate / submit concept | Yes | Yes | No (403) | Guardian role required; child tokens are scoped to reader endpoints |
| Approve (and publish) | Yes (global, cross-family) | No (403) | No (403) | Global admin role (`Role.ADMIN` / `is_admin`) required; enforced in the state machine. `authorize_family` is not applied |
| Access another family's data | Yes (admin, cross-family) | No (403) | No (403) | Family ownership is checked on every non-admin resource access; cross-family 403 |
| Edit a passage (Phase 4b) | Yes | Yes | No (403) | Guardian role required; `PATCH /storybooks/{id}/versions/{v}/nodes/{node_id}` |

Key implementation rules:

- The token subject is the canonical identity. `profile_id` in the query string or
  request body is used only after the subject has been verified to own it.
- Child tokens are issued with a scope that excludes authoring, generation, review,
  approval, and publish endpoints at the API gateway layer. The backend enforces the
  same restriction independently (defense in depth).
- Family ownership is checked on every resource access, not only on listing endpoints.
  A story that belongs to family A is inaccessible to a guardian from family B.

---

## IDOR Negative Tests

Each test below expects a 403 response. These are acceptance-level tests that must be
green before Phase 3 closes.

1. **Child A requests child B's library or reading state**: a child token belonging to
   profile A sends `GET /api/v1/library?profile_id={B}` or
   `GET /api/v1/reading-state/{B}/{storybook_id}`. Expected: 403. The token subject does
   not own profile B; the server must not return B's data.

2. **Child mutates `profile_id` in a reading-state PUT**: a child token belonging to
   profile A sends `PUT /api/v1/reading-state/{B}/{storybook_id}` with a body that
   includes `profile_id: B`. Expected: 403. The server must validate the subject against
   the path parameter, not the body field.

3. **Child (or guardian) calls approve**: a child token sends
   `POST /api/v1/storybooks/{id}/versions/{v}/approve`. Expected: 403. Note the reason is
   "admin required," not "wrong family": approval is reserved for the global admin role,
   so a guardian token calling the same endpoint also receives 403. A child token must not
   escalate, and a guardian must not self-approve.

4. **Guardian from another family accesses a story**: a guardian token belonging to
   family B sends any read or write request against a storybook owned by family A.
   Expected: 403. Family ownership is checked independently of the role.

---

## State Machine and Role Enforcement

The publish state machine transitions are enforced as follows:

```text
GenerationJob:  queued -> running -+-> passed        (validator + moderation gates pass)
                                   +-> needs_review  (safety flag; a human must clear it)
                                   +-> failed        (hard validation failure)

Storybook:      draft -> in_review -+-> published -> archived
                                    +-> needs_revision -> (repair / regenerate)
```

- `in_review -> published`: global admin role required (`Role.ADMIN` / `is_admin`). This
  is a single approve-and-publish transition: the approve action stamps both
  `storybook_version.approved_by` and `storybook_version.published_at` and returns
  `status='published'`. The check is cross-family: `authorize_family` is not applied to
  approval, so an admin from any family may approve. There is no separate `approved`
  resting state and no separate publish endpoint in the current code. A two-step
  approve-then-publish split (with an intermediate `approved` state audited independently)
  remains a not-yet-built future design if separate audit of approval and publish is
  later required.
- `running -> passed`: automated; the GenerationJob's validator and moderation gates pass,
  and the resulting draft version becomes reviewable. No role check because no human initiates it.
- `running -> needs_review` / `running -> failed`: automated on gate outcome. A safety flag
  routes the job to `needs_review` (a person must clear it); a hard validation failure routes
  to `failed` for repair or regeneration.

A story is visible in a child's library only in the `published` state.

---

## Related Documents

- [Tech Spec: Security](./tech-spec.md#security)
- [Tech Spec: API Specification](./tech-spec.md#api-specification)
- [ADR-005: Mandatory human approval](./adr/adr-005-mandatory-human-approval.md) (amended 2026-06-30: approver is the global admin role)
- [ADR-009: Supabase OIDC and guardian-identity / child-session split](./adr/adr-009-supabase-platform.md)
- [ADR-004: Homelab-first deployment](./adr/adr-004-homelab-first-deployment.md) (governs the homelab / family tier)
