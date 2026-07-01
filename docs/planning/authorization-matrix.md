---
title: "Authorization Matrix"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Document the endpoint-level authorization model, role mapping, and IDOR negative tests for CYO Adventure."
tags:
  - planning
  - architecture
component: Development-Tools
source: "docs/planning/tech-spec.md sections Security, Authorization, API Specification (2026-06-20)"
---

# Authorization Matrix

> **Status**: Draft | **Version**: 0.2 | **Updated**: 2026-07-01

## Overview

Authorization is enforced server-side on every endpoint. The Authentik OIDC token subject
maps to an allowed set of profiles. A guardian may act on any profile within their own
family. A child token is scoped to reader and library endpoints and may only act on its
own assigned profile. `profile_id` is never trusted alone.

There are three roles: **guardian** (family-scoped), **child** (own profile only), and
**admin** (the safety operator; per the ADR-005 amendment of 2026-06-30 the approver is a
global admin, not the child's parent-as-guardian). The `approve` action is admin-only and
cross-family; a guardian or child token that calls it receives 403. Per
[ADR-008](./adr/adr-008-first-release-trust-boundary.md), the approving parent is
provisioned as `admin`, and from C4a-0 the admin role additionally inherits guardian scope
within its own family (approval authority stays global; family powers do not).

---

## Action-by-Role Table

| Action | Admin | Guardian | Child (own profile) | Enforcement |
|--------|-------|----------|---------------------|-------------|
| Read own library / story / state | Own-family profiles (from C4a-0) | Any family profile | Own profile only | Token subject maps to allowed-profile set; 403 otherwise |
| Write own reading state | Own-family profiles (from C4a-0) | Any family profile | Own profile only | Same, plus `state_revision` and version guards on the PUT |
| Record a completion | Own-family profiles (from C4a-0) | Any family profile | Own profile only | `ending_id` must belong to the cited published version |
| Generate / submit concept | Own family (from C4a-0) | Yes | No (403) | Guardian-scope role required; child tokens are scoped to reader endpoints |
| Review surface (read blob + moderation report) | Yes, cross-family | No (403) | No (403) | Admin role checked before any row load |
| Approve (in_review to published, one action) | Yes, cross-family | No (403) | No (403) | Admin role required; `approved_by` and `published_at` stamped in the same transition |
| Send back (in_review to needs_revision) | Yes, cross-family | No (403) | No (403) | Admin role required |
| Archive (published to archived) | Yes, cross-family | No (403) | No (403) | Admin role required |
| Access another family's data | Approval surface only | No (403) | No (403) | Family ownership is checked on every non-approval resource; cross-family 403 |
| Edit a passage (Phase 4b) | Own family (planned) | Yes (planned) | No (403) | Guardian-scope role required; `PATCH /storybooks/{id}/versions/{v}/nodes/{node_id}` |

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

3. **Child or guardian calls approve**: a child or guardian token sends
   `POST /api/v1/storybooks/{id}/approve` (or `/send-back`, `/archive`). Expected: 403.
   The admin role is required on every approval-surface action; the role is checked
   before any row load so a non-admin never learns whether the story exists.

4. **Guardian from another family accesses a story**: a guardian token belonging to
   family B sends any read or write request against a storybook owned by family A.
   Expected: 403. Family ownership is checked independently of the role.

---

## State Machine and Role Enforcement

The publish state machine (`publishing/state_machine.py`, the single source of truth) has
five resting states; generation and auto-check happen while the row rests in `draft`, and
`approved` is collapsed into the `approve` action rather than being a distinct state:

```text
draft --submit------> in_review --approve---> published --archive--> archived
  |                    |    ^
  +--auto_reject--+    |    |
                  v    v    |
                needs_revision --submit--(re-review after repair / regenerate)
```

- `in_review -> published` (action `approve`): admin role required. The approver ID and
  publish time are stamped in the same transition (`storybook_version.approved_by`,
  `published_at`), so approval and publish are audited as one recorded human decision.
- `in_review -> needs_revision` (action `send_back`): admin role required.
- `draft -> in_review` (action `submit`) and `draft -> needs_revision` (action
  `auto_reject`): driven by the moderation pipeline after the validation gate; no role
  check because no human action initiates them. A hard moderation block auto-rejects; a
  clean or repaired story submits to review.
- `published -> archived` (action `archive`): admin role required.

A story is visible in a child's library only in the `published` state, and the library
additionally requires a recorded approver (`approved_by IS NOT NULL`) as a backstop.

---

## Related Documents

- [Tech Spec: Security](./tech-spec.md#security)
- [Tech Spec: API Specification](./tech-spec.md#api-specification)
- [ADR-005: Mandatory human approval](./adr/adr-005-mandatory-human-approval.md) (amended
  2026-06-30: the approver is a global admin)
- [ADR-008: First-release trust boundary](./adr/adr-008-first-release-trust-boundary.md)
  (C4a-0: real OIDC verification, admin-inherits-guardian, offline session model)
- [ADR-004: Homelab-first deployment (Authentik OIDC)](./adr/adr-004-homelab-first-deployment.md)
