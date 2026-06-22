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

> **Status**: Draft | **Version**: 0.1 | **Updated**: 2026-06-20

## Overview

Authorization is enforced server-side on every endpoint. The Authentik OIDC token subject
maps to an allowed set of profiles. A guardian may act on any profile within their own
family. A child token is scoped to reader and library endpoints and may only act on its
own assigned profile. `profile_id` is never trusted alone.

The `approve` and `publish` state-machine transitions require the guardian role. A child
token that calls either endpoint receives 403 regardless of the `profile_id` in the
request.

---

## Action-by-Role Table

| Action | Guardian | Child (own profile) | Enforcement |
|--------|----------|---------------------|-------------|
| Read own library / story / state | Any family profile | Own profile only | Token subject maps to allowed-profile set; 403 otherwise |
| Write own reading state | Any family profile | Own profile only | Same, plus `state_revision` and version guards on the PUT |
| Record a completion | Any family profile | Own profile only | `ending_id` must belong to the cited published version |
| Generate / submit concept | Yes | No (403) | Guardian role required; child tokens are scoped to reader endpoints |
| Approve (in_review to approved) | Yes | No (403) | Guardian role required on the transition; enforced in the state machine |
| Publish (approved to published) | Yes | No (403) | Guardian role required on the transition; enforced in the state machine |
| Access another family's data | No (403) | No (403) | Family ownership is checked on every resource; cross-family 403 |
| Edit a passage (Phase 4b) | Yes | No (403) | Guardian role required; `PATCH /storybooks/{id}/versions/{v}/nodes/{node_id}` |

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

3. **Child calls approve or publish**: a child token sends
   `POST /api/v1/storybooks/{id}/versions/{v}/approve` or `.../publish`. Expected: 403.
   The guardian role is required on both transitions; child tokens must not escalate.

4. **Guardian from another family accesses a story**: a guardian token belonging to
   family B sends any read or write request against a storybook owned by family A.
   Expected: 403. Family ownership is checked independently of the role.

---

## State Machine and Role Enforcement

The publish state machine transitions are enforced as follows:

```text
draft -> generating -> auto_check -+-> needs_revision -> (repair / regenerate) -+
                                   |                                             |
                                   +-> in_review -> approved -> published -> archived
```

- `in_review -> approved`: guardian role required. The approver ID is persisted in
  `storybook_version.approved_by`.
- `approved -> published`: guardian role required. The transition is separate from
  approval so that approval and publish can be audited independently.
- `auto_check -> in_review`: automated; triggered by the validator and moderation gate
  passing. No role check needed because no human action initiates it.
- `auto_check -> needs_revision`: automated on gate failure. Routes to human review if
  moderation flags content; routes to repair if only structural issues are found.

A story is visible in a child's library only in the `published` state.

---

## Related Documents

- [Tech Spec: Security](./tech-spec.md#security)
- [Tech Spec: API Specification](./tech-spec.md#api-specification)
- [ADR-005: Mandatory human approval](./adr/adr-005-mandatory-human-approval.md)
- [ADR-004: Homelab-first deployment (Authentik OIDC)](./adr/adr-004-homelab-first-deployment.md)
