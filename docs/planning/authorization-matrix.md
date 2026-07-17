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

> **Status**: Active | **Version**: 0.8 | **Updated**: 2026-07-16

> **Planned amendment ([ADR-015](./adr/adr-015-story-request-initiation-and-gating.md),
> accepted 2026-07-16)**: the three initiator flows below are already implemented (WS-B,
> story-lifecycle redesign). The remaining ADR-015 delta is consent-time budget semantics:
> the guardian approve action additionally debits family quota/credits, and per-child
> pre-authorization envelopes (register G3) can auto-consent within a guardian-set budget.
> No further token-scope widening is planned.

## Overview

Authorization is enforced server-side on every endpoint. The Supabase OIDC (ADR-009)
token subject maps to an allowed set of profiles. A guardian may act on any profile
within their own family. A child token is scoped to reader and library endpoints and may
only act on its own assigned profile. `profile_id` is never trusted alone.

Approval is a single state-machine transition reserved for the global admin capability
(`Principal.is_admin`). A guardian or child token that calls the approve endpoint
receives 403 regardless of the `profile_id` in the request. There is no separate publish
transition: the single approve action stamps `approved_by` and `published_at` and returns
`status='published'` (approve and publish in one call).

### Dual-role capability model (2026-07-12)

`User.role` is the single base persona (`guardian`, `child`, or `admin`) and the
global admin capability is the orthogonal `User.is_admin` flag, so one adult account
can be a guardian, an admin, or both. `Principal.is_guardian` derives from the base
role; `Principal.is_admin` derives from the flag, with the `admin` base role implying
the capability (an admin-only adult with no family guardianship). A dual-role
principal (`role='guardian'`, `is_admin=true`) therefore passes the UNION of the
guardian-only and admin-only gates, and its guardian base role resolves the family
profile set, so ownership-scoped endpoints work too.

**Surface selects scope.** Holding the admin capability never widens what a
guardian-surface endpoint returns: `GET /story-requests` is family-scoped for every
caller, and the global review queue is the explicit admin surface
`GET /admin/story-requests`. Per-id actions (approve, decline, child-session mint,
version fetch, content-summary) retain their admin-global reach, because acting on an
explicitly named resource is the admin capability working as designed, not a silent
scope widening of an everyday list.

**Audit stamps record the acting capacity.** `initiator_role` and pipeline-event
`actor_role` record the role that authorized the action: admin-gated endpoints stamp
`admin`, and cross-family actions by a dual-role adult stamp `admin`
(`Principal.acting_role`), while own-family actions stamp the guardian base role.

### Device principal (ADR-014)

A fourth base role, `Role.DEVICE`, represents a durable, family-scoped device
grant rather than a login: a guardian mints it once per shared device
(`POST /v1/device-grants`), and the resulting HS256 token (audience
`cyo-device-grant`, 90-day expiry) lets that device act on behalf of its
family without a live guardian Supabase session. `Principal.__post_init__`
force-clears `is_admin` for `Role.DEVICE` (it can never hold the admin
capability) and the principal carries an empty `profile_ids` (it is scoped
to no individual profile). It is allowlisted to exactly two endpoints:

- `POST /v1/child-sessions`: mint a child session for a profile in the
  grant's own family (per-profile PIN enforcement is unchanged).
- `GET /v1/profiles`: list the grant's own family's profiles (for the kid
  picker), family-scoped, never cross-family.

Every other endpoint, including the device grant's own management endpoints
(`POST`/`GET`/`DELETE /v1/device-grants`), refuses a device token with 403;
device-grant management itself remains guardian/admin-only. See ADR-014 for
the full three-token model (Supabase JWT, device grant, child session).

---

## Action-by-Role Table

Roles below are the base personas; a dual-role adult (guardian base role plus the
admin capability) receives the union of the Admin and Guardian columns, with list
surfaces staying family-scoped as described above. The Device column (ADR-014)
is included only where it is reachable at all; every action not listed for
Device is a flat 403.

| Action | Admin | Guardian | Child (own profile) | Device (own family) | Enforcement |
|--------|-------|----------|---------------------|----------------------|-------------|
| Create a story request (`POST /story-requests`) | No (no profile; use `/authored`) | Own family profile | Own profile only | No (403) | `authorize_profile` on the token subject; intake text screened (PII vs family child names + safety) before persist; per-profile pending cap (409) |
| Create an authored request (`POST /story-requests/authored`) | Yes (any family, or catalog-targeted with no family; `family_id` required) | Own family (created `approved`) | No (403) | No (403) | Guardian/admin only; screening still runs; blocked rows persist with no concept |
| Approve / decline a request | Yes | Own family | No (403) | No (403) | Guardian or admin; approval confirms band/length/style (422 on band-style mismatch); a child never approves its own request |
| Build an authoring plan (`POST /story-requests/{id}/authoring-plan`) | Yes | No (403) | No (403) | No (403) | Admin only; assigns method, mechanism, provider, and model against the server-side allowlist; this is what creates the GenerationJob |
| List story requests (`GET /story-requests`) | Own family only | Own family only | Own profile via filter | No (403) | Family-scoped for every caller; the global queue is the admin surface below |
| Global request queue (`GET /admin/story-requests`) | Yes (all families) | No (403) | No (403) | No (403) | Admin capability required; surfaces every moderation flag (no threshold filtering) |
| List profiles (`GET /profiles`) | Any family | Own family | No (403) | Own family only | Device is family-scoped, never cross-family, and carries no `profile_ids` of its own |
| Mint a child session (`POST /child-sessions`) | Yes (any family) | Own family | No (403) | Own family only | Guardian/admin bearer or a matching device grant; per-profile PIN enforcement unchanged |
| Read own library / story / state | Any profile | Any family profile | Own profile only | No (403) | Token subject maps to allowed-profile set; 403 otherwise |
| Write own reading state | Any profile | Any family profile | Own profile only | No (403) | Same, plus `state_revision` and version guards on the PUT |
| Record a completion | Any profile | Any family profile | Own profile only | No (403) | `ending_id` must belong to the cited published version |
| Generate / submit concept | Yes | Yes | No (403) | No (403) | Guardian role required; child and device tokens are scoped to reader endpoints |
| Manage device grants (`POST`/`GET`/`DELETE /device-grants`) | Yes (own family; admin may target another family on mint) | Own family only | No (403) | No (403) | Guardian or admin role required; a device token cannot mint, list, or revoke its own or any other grant |
| Approve (and publish) | Yes (global, cross-family) | No (403) | No (403) | No (403) | Global admin role (`Role.ADMIN` / `is_admin`) required; enforced in the state machine. `authorize_family` is not applied |
| Access another family's data | Yes (admin, cross-family) | No (403) | No (403) | No (403) | Family ownership is checked on every non-admin resource access; cross-family 403 |
| Edit a passage (Phase 4b) | Yes | Yes | No (403) | No (403) | Guardian role required; `PATCH /storybooks/{id}/versions/{v}/nodes/{node_id}` |
| Browse / assign a catalog book (cross-family, WS-E) | No (403; browse and assignment endpoints are guardian-only) | Any `visibility='catalog'` book, any family | No (403) | No (403) | `visibility='catalog'` widens guardian browse and assignment eligibility past own-family; browse and assignment endpoints are guardian-only, so a child or device token gets 403 regardless of `profile_id`; the `StorybookAssignment` gate is unchanged for child read/write paths |
| List families (`GET /admin/families`) | Yes (all families, name-ordered, capped at 50) | No (403) | No (403) | No (403) | `ctx.principal.is_admin` checked before any query (`api/families.py::list_families`); powers the admin authored-request family selector |
| Provider allowlist CRUD (`GET`/`POST`/`PUT`/`DELETE /admin/provider-allowlist[/{entry_id}]`) | Yes (list; add, toggle enabled/display_name, and delete a (provider, model_id) pair; every write audited) | No (403) | No (403) | No (403) | `_require_admin` gates every verb before any read or write (`api/provider_allowlist.py`); this allowlist is the control keeping free-string model ids out of billing |
| Moderation thresholds + noise floor (`GET`/`PUT`/`DELETE /admin/moderation-thresholds/{age_band}`, `GET`/`PUT /admin/moderation/noise-floor`) | Yes (list/upsert/delete per-band overrides; read/update the global noise floor; every write audited and emits a pipeline event) | No (403) | No (403) | No (403) | `_require_admin` gates every verb before any read or write (`api/moderation_thresholds.py`); threshold edits change what every family's guardians see on the review surface |
| Moderation dashboard (`GET /admin/moderation/dashboard`, `GET /admin/moderation/suggestions`) | Yes (read-only aggregated override evidence, recent threshold-change feed, and computed threshold suggestions) | No (403) | No (403) | No (403) | `_require_admin` gates both routes (`api/moderation_dashboard.py`); the aggregates describe moderation posture across every family |
| Cover generate / status (`POST`/`GET /storybooks/{storybook_id}/versions/{version}/cover`) | Yes (enqueue AI cover generation; poll status and URL) | No (403) | No (403) | No (403) | `_require_admin` gates both routes (`api/covers.py`); a non-admin must never learn whether a cover exists or is in flight for a given story version |

Key implementation rules:

- The token subject is the canonical identity. `profile_id` in the query string or
  request body is used only after the subject has been verified to own it.
- Child tokens are issued with a scope that excludes authoring, generation, review,
  approval, and publish endpoints at the API gateway layer. The backend enforces the
  same restriction independently (defense in depth).
- Family ownership is checked on every resource access, not only on listing endpoints.
  A story that belongs to family A is inaccessible to a guardian from family B.

### Arriving with PR #267 (not yet merged)

PR #267 (branch `claude/admin-user-management-rk111f`) adds a WS-J admin user-management
console: four new admin-only route modules. None of this has merged to `main`; the rows
below are verified directly against the PR branch's code (`git show FETCH_HEAD:...`), not
assumed from the PR title. Every route gates on the same `_require_admin` pattern
(`ctx.principal.is_admin`, checked before any read or write) as the rest of this
document; no new authorization primitive is introduced.

| Action | Admin | Guardian | Child (own profile) | Device (own family) | Enforcement |
|--------|-------|----------|---------------------|----------------------|-------------|
| Admin users CRUD (`GET/POST /admin/users`, `PATCH /admin/users/{user_id}`) | Yes (list/filter guardian+admin accounts across every family; invite a new `status='pending'` account; reassign family, re-role, toggle `is_admin`, or activate/deactivate an existing one) | No (403) | No (403) | No (403) | `_require_admin` (`api/admin_users.py`); `role='child'` rows are always excluded from every read; an admin may not edit their own row through `PATCH` (self-lockout guard, `AuthorizationError` regardless of which field changed); a `status` transition into or out of `'pending'` is rejected (422, that state is onboarding-owned) |
| Admin child-profile CRUD, incl. PIN set/reset (`GET/POST /admin/profiles`, `PATCH /admin/profiles/{profile_id}`) | Yes (list/filter child profiles across every family; create one in any family; update any field including `pin` -- an explicit `pin` sets or, if `null`, clears the profile's picker PIN) | No (403) | No (403) | No (403) | `_require_admin` (`api/admin_profiles.py`); kept deliberately separate from the guardian-scoped `api/profiles.py` (own-family-only) so the two authorization models cannot blend; `pin_hash` is never serialized back, only the derived `has_pin` boolean |
| Family create / rename / deactivate (`POST /admin/families`, `PATCH /admin/families/{family_id}`) | Yes (create a family; rename it; deactivate it, which cascades to deactivate every member `User` and `ChildProfile` in the same transaction; reactivating the family does not auto-reactivate its members) | No (403) | No (403) | No (403) | `_require_admin` (`api/families.py`, same module as the already-shipped `GET /admin/families` listing above) |
| Family-connection CRUD (`GET/POST /admin/family-connections`, `DELETE /admin/family-connections/{connection_id}`) | Yes (list every directional connection with both family names; create a directional opt-in; hard-delete one) | No (403) | No (403) | No (403) | `_require_admin` (`api/family_connections.py`); a connection is a permission edge, not identity data, so deletion is a real `DELETE`, not a soft-deactivate (mirrors `provider_allowlist`); per the capability register (G17/A15, [ADR-016](./adr/adr-016-recommendation-sharing-social-boundary.md)) this admin console is not itself sufficient consent -- nothing yet reads this table to widen child-facing visibility |

### Catalog visibility (WS-E)

WS-E adds a `visibility` axis (`family` or `catalog`) on `Storybook`, set by the admin at
approval. The plain family-ownership rule above still governs the default case; catalog
visibility adds a narrow, server-checked exception on top of it. The contract is three-way:

1. **Own-family**: unchanged. A guardian or child acting within their own family reads,
   writes, or is assigned any book in that family exactly as before; visibility never
   restricts an own-family action.
2. **Cross-family, `visibility='family'`**: unchanged. `authorize_family` still returns 403;
   the catalog widening does not touch the default (private) visibility case.
3. **Cross-family, `visibility='catalog'`**: a guardian may browse the book in
   `GET /api/v1/guardian/books` and assign it to any of their own children's profiles
   without a 403, but every child-facing read or write path still requires a
   `StorybookAssignment` row for the acting profile. On an assignment mismatch the
   responses differ by surface: ratings and reading-state (progress saves and
   completions) return 403, while the direct version-blob fetch returns 404 to hide an
   unassigned book's existence rather than leaking a 403. In short: the family filter
   widens to admit catalog books, but the assignment gate that already governs child
   access is never bypassed.

This contract (the E5 amendment, ratified 2026-07-09, shipped in WS-E's PR #180) is pinned
against `api/library.py`, `api/ratings.py`, and `api/reading.py`.

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

5. **Device token calls any guardian/admin/child-only endpoint** (ADR-014): a
   verified device grant token sends a request to any endpoint other than its
   two allowlisted routes (`POST /api/v1/child-sessions`,
   `GET /api/v1/profiles`), for example
   `POST /api/v1/concepts`, `POST /api/v1/storybooks/{id}/approve`,
   `GET /api/v1/library`, or its own management endpoints
   (`POST`/`GET`/`DELETE /api/v1/device-grants`). Expected: 403 in every case.
   `Principal.__post_init__` force-clears `is_admin` for `Role.DEVICE` and the
   principal carries no `profile_ids`, so a device token cannot pass a
   guardian-only, admin-only, or profile-scoped gate regardless of the claims
   in the token.

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
- [ADR-009: Supabase as the managed platform for auth, database, and storage](./adr/adr-009-supabase-platform.md)
- [ADR-004: Homelab-first deployment](./adr/adr-004-homelab-first-deployment.md) (governs the homelab / family tier)
