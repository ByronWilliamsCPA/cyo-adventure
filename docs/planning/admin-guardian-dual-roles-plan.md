---
title: "Dual Admin/Guardian Roles and a Parallel Admin Console"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Implementation plan for letting one adult hold the guardian role, the admin role, or both, with admin functions moved to a dedicated /admin surface parallel to the guardian console."
tags:
  - planning
  - architecture
component: Development-Tools
source: "Codebase survey of src/cyo_adventure/api/deps.py, api routers, frontend/src/auth and frontend/src/guardian (2026-07-12); docs/planning/authorization-matrix.md v0.3"
---

# Dual Admin/Guardian Roles and a Parallel Admin Console

> **Status**: Draft | **Version**: 0.1 | **Updated**: 2026-07-12

## Goal

An adult account can be a guardian, an admin, or both. Admin functions move out of the
guardian console into their own `/admin/*` page tree that sits in parallel with the
standard `/guardian/*` pages, with a switcher for users who hold both roles.

## Why this is currently impossible

The role model is single-valued end to end, and the two adult roles are deliberately
non-hierarchical (an admin is rejected from guardian-only endpoints and vice versa;
see `tests/integration/test_authz_matrix.py:17-32`):

1. **Storage**: `User.role` is one `String(16)` column (`db/models.py:170`) with
   `CHECK (role IN ('guardian','child','admin'))` (`db/models.py:164-166`,
   `supabase/migrations/20260710000000_baseline.sql:350`). `authn_subject` is unique
   (`db/models.py:171`), so one login identity maps to exactly one role. Today the seed
   models "both" as two separate User rows with two distinct login subjects
   (`tests/integration/conftest.py:230-234`).
2. **Principal**: `require_principal` coerces the column to a single enum value,
   `role=Role(user.role)` (`api/deps.py:339`); `Principal.is_admin` / `is_guardian` are
   equality tests on that one value (`api/deps.py:103-111`).
3. **Profile ownership**: `_resolve_profiles` grants family profile access only when
   `user.role == Role.GUARDIAN` (`api/deps.py:394-401`). An admin structurally owns no
   profiles, so library, reading-state, ratings, and profile listing come back empty or
   403 for an admin even in their own family.
4. **Guardian-only gates explicitly reject admins**: `generation.py:194,254,338,416,486`,
   `profiles.py:53-70`, `assignments.py:100-136,446` (guardian books browse; the comment
   at `assignments.py:438-444` states admin is rejected on purpose).
5. **Frontend**: `Principal.role` is a single scalar (`frontend/src/auth/types.ts:1-20`),
   `/v1/me` returns one `role` string (`client/types.gen.ts:1115-1132`), and
   `ProtectedRoute` does `allowedRoles.includes(principal.role)`
   (`frontend/src/auth/ProtectedRoute.tsx:47`). Admin pages are nested inside
   `/guardian/*` (`frontend/src/router.tsx:112-127`), and several guardian pages branch
   on `principal?.role === 'admin'` inline (`ConsolePage.tsx:198-204`,
   `RequestsPage.tsx:329`).

## Recommended role representation

Keep `role` as the single **base persona** and add an orthogonal admin capability flag:

- `User.role IN ('guardian','child','admin')` stays as-is; its meaning narrows to the
  base persona. `'admin'` now means "adult with no family guardianship" (admin-only).
- New column `User.is_admin BOOLEAN NOT NULL DEFAULT FALSE`.
- The three adult states: guardian-only = `('guardian', false)`; both =
  `('guardian', true)`; admin-only = `('admin', true)`.
- Migration backfills `is_admin = TRUE` where `role = 'admin'`, plus a CHECK that
  `role = 'admin'` implies `is_admin` (`ck_user_admin_role_flag`).

Rationale over a roles array or join table:

- `Principal.is_guardian` and every guardian-only gate keep working unchanged; a
  dual-role user has `role='guardian'` and passes them, an admin-only user is still
  rejected, which preserves the documented non-hierarchy.
- `Principal.is_admin` changes from an equality test to reading the flag
  (`user.is_admin or role == Role.ADMIN`), one line in `deps.py`.
- `_resolve_profiles` needs no change for the guardian branch; dual-role users resolve
  their family's profiles because their base role is guardian.
- `initiator_role` / `actor_role` audit stamps (`story_requests/service.py:387`,
  `events/models.py:97`) and their CHECK constraints stay valid; see the audit decision
  below.
- No new table, no array column, one additive migration.

`Principal` gains `is_admin: bool` as a stored field (set from the User row) instead of
the derived property; `is_guardian` stays derived from `role`.

## The real risk: privilege-scoping forks, not gates

Several endpoints do not gate on admin, they **fork scope** on it. With dual roles these
become silent escalations for a guardian-who-is-admin acting on guardian surfaces:

- `GET /story-requests` widens to all families and full moderation detail when
  `is_admin` (`api/story_requests.py:578,594`).
- `_load_scoped_request` skips the family check for admins (`api/story_requests.py:636-638`).
- `_resolve_authored_family` is an either/or contract: admin must supply `family_id`,
  guardian must omit it (`api/story_requests.py:385-403`).
- `child_sessions.py:77` and `_resolve_authored_profile`
  (`api/story_requests.py:438`) skip `authorize_profile` for admins.
- `library.py:400-427` three-way branch: admin reads any family and any status.
- `assignments.py:170,177` content-summary skips `authorize_family` for admins.

**Principle for the fix**: the surface, not the caller's maximal privilege, selects the
scope. Concretely:

- Guardian-surface endpoints are always family-scoped, even for admins. The admin
  bypass in each fork above moves behind an explicit signal: either a dedicated
  `/api/v1/admin/...` route (preferred, matches `families.py`, `moderation_*`,
  `provider_allowlist.py`) or an explicit `scope=all` query parameter that requires
  `is_admin`.
- `GET /story-requests`: family-scoped for everyone; add
  `GET /api/v1/admin/story-requests` (requires `is_admin`) for the global queue the
  admin RequestsPage view uses today.
- `_resolve_authored_family`: `family_id` optional for everyone; omitted means the
  caller's own family (requires `is_guardian`), provided-and-different requires
  `is_admin`. This removes the either/or 422 fork that has no "both" answer.
- Approval, review-queue, covers, moderation, provider allowlist, families: unchanged,
  already admin-gated (`approval.py:86,289`, `covers.py:30-33`, etc.).

**Audit stamping decision**: `initiator_role` / `actor_role` record the capacity in
which the action was authorized, not the base persona: admin-gated endpoints stamp
`'admin'`, guardian-surface endpoints stamp `'guardian'`. Implement by passing the
acting role explicitly at the call sites that are admin-gated instead of deriving from
`principal.role.value`.

## Backend work items

1. **Migration** (`supabase/migrations/`): add `is_admin` with backfill and the
   implication CHECK; mirror in `db/models.py` (`User.is_admin`).
2. **`api/deps.py`**: load the flag in `require_principal`; `Principal.is_admin`
   becomes flag-based; child principals keep `is_admin=False`.
3. **`api/me.py` contract**: `MeResponse` gains `is_admin: bool` (keep `role` for the
   base persona so the kid/guardian shell selection logic is untouched). This is a
   frontend contract change, so regenerate the client (Architecture note 1).
4. **Scoping-fork rework** per the principle above: `story_requests.py` (list, scoped
   load, authored family/profile), `child_sessions.py`, `library.py` version fetch,
   `assignments.py` content-summary. Each site gets a deliberate decision recorded in
   the authorization matrix.
5. **Audit stamps**: explicit acting-role at admin call sites.
6. **Tests**:
   - `tests/integration/test_authz_matrix.py`: add a dual-role principal to the
     matrix; relax the "exactly one role passes" invariant to "every listed capability
     set passes, everything else 403"; extend `_ROUTE_SPECS`.
   - `tests/integration/conftest.py` seed: add `both-a` (guardian + is_admin) alongside
     the existing `admin-a` and `guardian-a`.
   - New tests: dual-role user sees only their own family on guardian surfaces; global
     scope only via admin routes; admin-only user still 403 on guardian-only endpoints;
     authored-request family resolution for all three adult states.
   - Update pinned exclusivity tests (`test_profiles.py`, `test_guardian_books_api.py`,
     `test_story_requests_api.py`) where semantics change.
7. **Docs**: update `docs/planning/authorization-matrix.md` (action-by-role table gains
   the dual-role column and the surface-selects-scope rule); short ADR for the role
   model change (amends the role notes in ADR-005/ADR-009 context).

## Frontend work items

1. **Auth model** (`frontend/src/auth/types.ts`, `AuthContext.tsx`): `Principal` gains
   `isAdmin: boolean` from the regenerated `MeResponse`; `role` stays the base persona.
   Fail-closed validation unchanged.
2. **Route guard** (`ProtectedRoute.tsx`): replace `allowedRoles.includes(role)` with a
   capability check (`requireGuardian` / `requireAdmin` style props, or keep
   `allowedRoles` and treat `is_admin` as granting `'admin'` membership).
3. **New `/admin/*` tree** (`router.tsx`, `routes.ts`, new `frontend/src/admin/`):
   - `AdminShell` paralleling `GuardianShell` with its own nav; both shells show a
     console switcher when the principal holds both capabilities
     (`GuardianShell.tsx:32-39` already renders a role label to build on).
   - Move: `ModerationThresholdsPage`, `ModerationDashboardPage` (and their API
     modules), the review queue plus admin nav currently inside `ConsolePage.tsx`
     (`:40-48,70-83,117-126,198-204`), `ReviewDetailPage` (also fixes the existing gap
     that it is not admin-gated at the router level, only server-side), the admin
     story-request approval queue half of `RequestsPage.tsx` (`:78-87`), and
     `RequestStoryForm mode="admin"` with its family selector.
   - Add admin pages that have backend support but no UI today if desired: provider
     allowlist, families list.
4. **Guardian pages become single-purpose**: `ConsolePage` and `RequestsPage` drop
   their `role === 'admin'` branches; `GuardianShell` drops the guardian-only
   conditional on the Books link if a dual-role user should see it (they will, since
   their base role is guardian).
5. **Client regen**: `npm run generate-client` against the updated backend; commit the
   diff (CI contract job fails on drift).
6. **Login flow**: `/guardian/login` stays the shared entry; post-login landing picks
   `/admin` for admin-only users, `/guardian` otherwise.

## Sequencing (three PRs)

1. **feat(auth): dual-role principal model**: migration, deps, /me, client regen,
   authz-matrix test rework. Behavior-neutral for existing single-role users.
2. **feat(api): surface-scoped admin access**: scoping-fork rework, new
   `/admin/story-requests` route, audit stamping, matrix doc update.
3. **feat(frontend): parallel admin console**: `/admin/*` tree, page moves and splits,
   shell switcher.

Rough size: PR1 small-to-medium, PR2 medium (highest review risk, touches IDOR-adjacent
code), PR3 medium-to-large (mostly moves plus two page splits). The authz matrix test
suite is the regression harness for PRs 1 and 2.

## Open decisions

- Whether an admin-only user keeps a mandatory `family_id` (today NOT NULL and admins
  have one). Recommendation: keep NOT NULL for now, revisit if pure-admin provisioning
  becomes a product surface.
- Whether guardian-surface behavior for dual-role users should ever widen (for example
  seeing unpublished versions in `library.py`). Recommendation: no, keep guardian
  surfaces strictly family-scoped and published-only; admins use the review surface.
- Whether `role='admin'` should be renamed to `'adult'` once it only means
  "non-guardian adult". Defer, it is a cosmetic migration.
