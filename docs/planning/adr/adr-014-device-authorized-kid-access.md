---
title: "ADR-014: Device-authorized kid access"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the device-authorization model for the kid surface: a durable, revocable,
  family-scoped device grant that lets a child read online or offline without a live guardian
  session, and the reframing of the parental step-up as a single kid-to-adult boundary crossing
  instead of a per-page gate."
tags:
  - planning
  - architecture
  - decisions
  - security
---

# ADR-014: Device-authorized kid access

> **Status**: Accepted (2026-07-13)
> **Date**: 2026-07-13
> **Relates to**: [ADR-009](./adr-009-supabase-platform.md) (Supabase auth and JWKS
> verification), [ADR-005](./adr-005-mandatory-human-approval.md) (guardian gating of the
> pipeline), [ADR-002](./adr-002-client-pwa.md) (offline-first client), [ADR-012](./adr-012-supabase-cli-migrations.md)
> (migration mechanism for the new table)

## TL;DR

Introduce a third token type, the **device grant**: a durable (90-day, revocable),
family-scoped credential a guardian mints once per shared device. The child-session mint
endpoint begins accepting the device grant as authority in addition to a guardian JWT, so a
child can pick a profile and read, online or offline, without a live guardian Supabase session
sitting in the device's `localStorage`. The kid surface (`/kids`, `/library`, `/read`) moves
behind a local device-grant check (no Supabase in the kid bundle). The "Grown-ups only"
password step-up is reframed from a per-page gate (which caused remount churn and repeated
prompts) into a single **kid-to-adult boundary crossing**: adult-to-adult navigation is free
once warm, and only crossing up from kid mode re-demands the password.

## Context

### Problem

The product requires that a child cannot open the app on a device and start reading without a
guardian having first authorized that device, yet once authorized the device must keep working
for the child online **and** offline, without the guardian logging in again each time.

Two facts about the code as of `feat/parental-gate-switch-account` make the naive approach
impossible:

1. **Minting a child session already requires a live guardian/admin bearer** server-side
   (`api/child_sessions.py:72-74`), and that bearer is the guardian's short-lived Supabase
   access token. So today a child can only begin reading while a guardian's live Supabase
   session happens to be cached in `localStorage` (`auth_token`). When it expires, the child is
   locked out. A purely client-side "device authorized" flag cannot fix this, because the mint
   call is authorized on the server.

2. **The parental step-up (`ParentalGate`) wraps individual adult pages** that are siblings of
   ungated ones (`router.tsx:119-137`), so React Router unmounts and remounts it as the user
   crosses the nav bar. Its "warmed" state lived in module memory with a 5-minute TTL and was
   deliberately reset on any page reload, so the switch-account OAuth round-trip (a full reload)
   and ordinary nav both re-fired the password box. To the user this reads as "sign in again on
   every page," even though the underlying Supabase session was healthy the whole time.

### Constraints

- **Technical**: the kid route tree is a separate lazy chunk that intentionally does not import
  `@supabase/supabase-js` (`router.tsx:42-56`, `GuardianAuthLayout.tsx`), preserving offline
  operation and a small kid bundle. Any kid-side gate must not pull the Supabase client into
  that chunk. Offline reading is served from IndexedDB (`offline/db.ts`, stores keyed by
  profile/storybook), so a valid token is not required to read already-synced content; the token
  gates online API calls and sync.
- **Security**: children's profile data is COPPA-adjacent. A device left with a child must not
  expose guardian/admin capabilities, and a lost device must be revocable. Supabase remains the
  sole identity provider for adults (ADR-009); the device grant is an authorization artifact
  derived from a Supabase-authenticated guardian, never a competing identity.
- **Operational**: a solo operator; the model must be mechanically testable and must not add a
  per-session login step for either the guardian (beyond first setup) or the child.

### Significance

This decision defines how the two audiences share one physical device, and it establishes the
separation between "this device is set up for kids" (durable) and "a grown-up is present right
now" (ephemeral), which is the property that makes the kid-to-adult boundary enforceable.

## Decision

### 1. A third token type: the device grant

| Token | Means | Lifetime | Signing | Audience | Scope |
| --- | --- | --- | --- | --- | --- |
| Supabase JWT | a grown-up is present now | short (auto-refresh) | RS256/ES256 (JWKS) | `authenticated` | full guardian/admin per role |
| **Device grant (new)** | a grown-up authorized this device for their family | 90 days, revocable | HS256 | `cyo-device-grant` | list this family's profiles + mint child sessions, nothing else |
| Child session | this profile is reading | 12 hours, no refresh | HS256 | `cyo-child-session` | one profile's library/reading |

The device grant carries `family_id`, `authorized_by` (the guardian's user id), and a `jti`. It
is signed with a new `DEVICE_GRANT_SECRET` (validated at startup like `CHILD_SESSION_SECRET`,
`config.py:591-653`) and recorded in a new `device_grants` table so a guardian can list and
revoke authorized devices. Revocation is enforced on online calls (jti checked against the
table); it cannot be enforced offline, which is an accepted limitation bounded by the grant TTL.

### 2. The child-session mint accepts the device grant

`POST /v1/child-sessions` and the picker's `GET /v1/profiles` accept a device principal scoped
to the matching `family_id`, in addition to guardian/admin. Per-profile PIN enforcement is
unchanged (`child_sessions.py:100-113`). `api/deps.py` gains a third routing branch on the
unverified `aud` claim (mirroring the child-session branch at `deps.py:442`), and the device
principal is refused on every other route via an explicit allowlist, not a denylist.

### 3. The kid surface is gated by a local device-grant check

`DeviceAuthorizedRoute` wraps the kid tree. It inspects the durable device grant
(`localStorage` + an IndexedDB mirror for offline resilience), decoding `exp`/`family_id`
locally for routing only (the backend verifies the signature on use, the same trust split the
child session already uses in `childSession.ts`). No `useAuth`, so the kid chunk stays
Supabase-free. A missing or expired grant redirects to guardian login to authorize the device.

### 4. The step-up becomes a single kid-to-adult boundary

The two `ParentalGate` placements collapse into one `AdultGate` at the root of the adult
subtree. Logic: no Supabase session then login; session but not warm (cold entry, or returning
from kid mode) then the password step-up; warm then free adult-to-adult navigation. Warm state
moves to `sessionStorage` so it survives the switch-account OAuth reload, and is cleared on
sign-out and on entering kid mode. Entering kid mode from an adult page explicitly parks the
warm state, so returning up always re-demands the grown-up password.

### 5. Device-state-aware front door

The two-door landing stays. On a device with no valid device grant, both doors route through
guardian login (the Kids door logs a guardian in to authorize the device, then drops to
`/kids`). On an authorized device, the Kids door goes straight to `/kids` (the grant supplies
the authorizing family's profiles; the child needs only their PIN), and the Grown-ups door
enters the `AdultGate`.

## Consequences

### Positive

- A child reads on an authorized device with only a per-profile PIN, online or offline, with no
  guardian re-login, satisfying the core requirement.
- A child's device holds only a narrow, revocable, family-scoped grant, never a full guardian
  session, which is a security improvement over today's implicit reliance on a cached
  `auth_token`.
- The repeated-prompt bug is eliminated structurally: the step-up no longer remounts during
  adult navigation and its warm state survives the OAuth reload.
- Role-based navigation (guardian-only, admin-only, dual-role cross-links) is made consistent as
  part of the same change.

### Negative / risks

- New credential type to secure and test. `#CRITICAL security:` the device principal must never
  reach a guardian/admin route; `#VERIFY:` every guardian/admin endpoint is tested for 403 with
  a device token, and the mint/profiles endpoints are tested for correct family scoping.
- Offline revocation is impossible; a lost device retains family profile-list and child-mint
  capability until the grant expires or the device reconnects and the revocation is seen.
  Bounded by the 90-day TTL and mitigated by the guardian-visible device list.
- `#ASSUME security:` `sessionStorage` warm-state for the adult step-up is acceptable because it
  clears on tab close, sign-out, and kid-mode entry; `#VERIFY:` those three clears are covered
  by tests.

### Neutral

- Adds one table (`device_grants`, via Supabase CLI migration per ADR-012), one env var
  (`DEVICE_GRANT_SECRET`), and three endpoints (`POST`/`GET`/`DELETE /v1/device-grants`). The
  OpenAPI client is regenerated and the contract-drift CI job gates the diff.

## Alternatives considered

- **Rely on Supabase refresh tokens to keep the guardian session alive on the kid device.**
  Rejected: it leaves a full guardian session on a child's device (the exact thing the step-up
  exists to defend against) and still means "a grown-up is logged in here," which defeats the
  boundary.
- **Client-side-only device flag, keep guardian-bearer minting.** Rejected: the mint is
  server-authorized, so a client flag cannot grant offline/after-expiry minting.
- **Keep the per-page parental gate, only fix the reload.** Rejected: it fixes the symptom
  (switch-account cold-start) but not the remount churn, and it keeps more friction than the
  device-authorization model needs.
