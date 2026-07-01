---
title: "ADR-008: The first release verifies identity at the API, not at the ingress"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Record the first-release trust-boundary design: real OIDC verification behind the deps.py seam, the role model that lets one parent both manage a family and approve stories, and the offline-capable PWA session contract."
tags:
  - planning
  - architecture
  - decisions
  - security
---

# ADR-008: The first release verifies identity at the API, not at the ingress

> **Status**: Proposed
> **Date**: 2026-07-01

## TL;DR

Ship real authentication inside the first release as workstream **C4a-0**: the PWA runs OIDC
Authorization Code + PKCE directly against Authentik, and the backend verifies every access
token's signature, issuer, audience, and expiry itself behind the existing `deps.py` seam,
because on a home LAN the ingress can be bypassed and the API is the only trust boundary that
holds. Roles stay authoritative in Postgres; the approving parent is provisioned as `admin`,
and the admin role inherits guardian family scope so one account runs the whole guardian
console. Refresh tokens (rotating) give the PWA an offline-tolerant session: reading offline
needs no token, and the sync queue refreshes before it replays.

## Context

### Problem

The merged backend enforces ADR-005's central guarantee, no story reaches a child without a
recorded human approval, through an authorization layer that is real and well tested. But the
authentication layer beneath it is a development stub: `api/deps.py::_extract_subject` treats
any bearer token as an already-verified OIDC subject. An import-time `ConfigurationError`
stops the stub from starting outside `environment == "local"`, which prevents accidental
deployment, but the first release plan (Phases 0-4a) contained no workstream that replaces
the stub. As shipped, the bearer token is just the subject string.

The threat model makes this concrete. This product's adversary is not an internet attacker;
it is the household's own clever child, who is on the same LAN as the server, may know or
guess a guardian's or admin's subject string, and has periodic physical access to shared
family devices. With the stub, `curl -H "Authorization: Bearer <admin-subject>"` from a
child's tablet is a full approval-authority takeover. ADR-005's invariant is enforceable only
against actors who cannot mint a token, and on a trusted LAN with the stub, everyone can.

Three secondary problems ride along:

1. **Role-model contradiction.** ADR-005 (amended 2026-06-30) and the merged code make the
   approver a **global admin**; `docs/planning/authorization-matrix.md` still says the
   guardian approves, and the PROJECT-PLAN state diagram still shows a two-step
   `approved -> published` that the code collapsed into one `approve` action. Phase 4a's
   guardian console (C4a-4) cannot be built against contradictory role documents.
2. **One parent, two hats.** The `Role` enum is single-valued and an `admin` principal
   resolves an **empty** profile set (`deps.py::_resolve_profiles` grants family profiles
   only to guardians). A parent provisioned as `admin` to approve stories would lose every
   family-scoped power (concepts, generation, library management) that the same console
   needs. The role model must let one human hold both authorities in one session.
3. **Offline sessions.** ADR-002 makes offline reading first-class, and the offline sync
   queue durably holds progress writes for later replay. Tokens expire; the session design
   must survive hours offline without either losing queued progress or resorting to
   long-lived bearer secrets a sibling can lift from a shared device.

### Constraints

- **Technical**: the fix must slot behind the existing seam. `deps.py` was designed so that
  only subject extraction changes; the `Principal` resolution, profile scoping, and family
  checks (and their IDOR test suite) must not be reworked.
- **Technical**: Authentik and Pangolin already run in the homelab (ADR-004). Phase 5 wires
  deployment; it must not have to rework authentication.
- **Business**: the users include young children. Login UX for a 6-year-old cannot be a
  password ceremony on every read; the guardian sets up the child's device once.

### Significance

This is the last Critical finding standing between the Phase 3 backend and a first release
whose child-safety invariant holds against its actual threat model. Getting the seam contract
wrong forces a Phase 5 rework of every Phase 4a surface built on top of it.

## Decision

**We will verify identity at the API boundary with full OIDC token verification, keep
authorization authority in Postgres, make `admin` a superset of guardian family scope, and
give the PWA a rotating-refresh-token session that tolerates offline periods, shipping all of
it as workstream C4a-0 before any other Phase 4a surface.** Specifically:

### 1. The API is the trust boundary; the ingress is not

The backend verifies every access token itself: RS256 signature against Authentik's JWKS
(fetched by `kid`, cached), exact `iss` match, exact `aud` match, `exp`/`nbf` with a small
clock-skew leeway (60 s), and algorithm pinned to RS256 (reject `none` and any HS*
downgrade). The verified `sub` claim becomes `Principal.subject`; everything downstream of
`_extract_subject` is unchanged, which is precisely the swap the seam was built for.

Pangolin remains TLS termination and network ingress only. **Forward-auth headers are never
used as identity**: a LAN client can reach the backend container directly, bypassing the
ingress entirely, so any identity asserted only at the proxy is forgeable by exactly the
adversary this design is for. Ingress-level auth may be layered on later as defense in depth;
it can never be the boundary.

JWKS handling fails closed with a warm-cache allowance: a cold start that cannot reach
Authentik refuses to authenticate anyone (503, not open), while a warm cache keeps verifying
through a brief IdP outage. An unknown `kid` triggers one forced JWKS refetch (bounded) to
absorb key rotation, then rejects.

### 2. Authentik authenticates; Postgres authorizes

The token proves **who** is calling; the `User` row (matched on `authn_subject = sub`) says
**what** they may do, exactly as today. We do not map Authentik group claims to roles in the
first release: a second authority source would have to be reconciled with the DB on every
request, and drift between them is a child-safety bug. Authentik groups may later drive
*provisioning* of `User` rows; they never bypass them. An authenticated subject with no
`User` row is rejected (401), so creating an Authentik account does not grant access.

### 3. One parent, two hats: admin inherits guardian family scope

The approving parent is provisioned with `role = "admin"` (recording the ADR-005 amendment's
"parents are provisioned as admins" decision), and C4a-0 makes `admin` a strict superset of
guardian **within its own family**:

- `_resolve_profiles` grants an admin the same family profile set a guardian gets.
- Guardian-gated routes (concepts, generation, library management) accept
  `role in {guardian, admin}` via a single `can_act_as_guardian` property on `Principal`.
- Approval routes remain admin-only and cross-family, unchanged.
- Family-scoped routes still run `authorize_family`, so an admin's guardian powers reach only
  their own family; only the approval surface is global.

The second parent may stay a plain `guardian`. A future multi-family deployment can provision
a dedicated safety operator as an `admin` in an operator family with no children; nothing
above assumes the admin has child profiles. We chose this over dual accounts (one guardian
login plus one admin login for the same human) because the C4a-4 console intentionally puts
concept intake, library management, and approval in one surface; forcing an account switch
per approval is friction that trains exactly the credential-sharing habits this ADR exists to
prevent.

### 4. Offline-tolerant sessions: short access tokens, rotating refresh tokens

- **Access tokens are short-lived** (target 15 minutes; set in Authentik per application).
  Interception or theft of one is a bounded loss.
- **Refresh tokens rotate on every use** (Authentik's rotation policy), with `offline_access`
  scope and a device-appropriate absolute lifetime: long (about 90 days) on a child's own
  device where the blast radius is a child-scoped token, shorter (about 14 days) for guardian
  and admin sessions.
- **Reading offline requires no token at all.** The player runs from IndexedDB; progress
  writes queue locally. Token expiry while offline is therefore a non-event.
- **The sync path refreshes before it replays.** On reconnect, the client first refreshes the
  access token, then replays the queue. If refresh fails (revoked or expired), the queue
  stays durably persisted, the user re-authenticates, and replay proceeds after login. Queued
  progress is never dropped for auth reasons.
- **Token storage**: the OIDC client keeps tokens in its web storage store so sessions
  survive PWA restarts. This is readable by same-origin script, an accepted risk for v1: the
  app serves no third-party script, ships a strict CSP, and the alternative (a
  backend-for-frontend holding sessions in httpOnly cookies) adds server session state and a
  second auth code path that Phase 5 would have to carry. Revisit if the XSS posture changes
  (for example, if user-authored HTML ever renders).

### 5. Step-up freshness on approval (defense in depth)

The approval transitions guard the child-safety invariant, and the residual threat after
token verification is a child holding a parent's unlocked device with a live session. C4a-0
therefore enforces **authentication freshness on approval**: `POST .../approve` and
`.../send-back` require the token's `auth_time` to be within 10 minutes; a stale session
receives 403 with a distinct error code, and the console responds by re-running login with
`max_age=600` (an OIDC-standard re-auth, not a second credential system). This is the one
deliberate UX cost in the design; it is scoped to the two approval actions only and the
project owner may relax the window.

### 6. The stub survives as a mode, tests keep their ergonomics

`Settings` gains `auth_mode: Literal["stub", "oidc"] = "stub"` plus `oidc_issuer` and
`oidc_audience` (JWKS URL discovered from the issuer). The existing import-time kill switch
keeps its semantics: `auth_mode == "stub"` outside `environment == "local"` raises
`ConfigurationError` at startup. `oidc` mode is valid in any environment, including local
against the homelab Authentik for pre-release testing. The unit and integration suites keep
using the stub; a dedicated verifier test module covers `oidc` mode with a locally generated
RSA keypair and a mocked JWKS endpoint (no live IdP in CI).

### 7. The frontend contract C4a-1 builds against once

C4a-0 defines (and C4a-1 consumes) a single auth context:

```text
AuthContext
  status: 'authenticated' | 'anonymous' | 'refreshing'
  me: { role, familyId, profileIds }        // from GET /api/v1/me, never from token claims
  login(): void                             // redirect to Authentik (PKCE)
  logout(): void
  getAccessToken(): Promise<string>         // returns fresh token, refreshing if stale;
                                            // rejects with OfflineError when offline
```

Backing it: a new `GET /api/v1/me` endpoint returning the resolved `Principal` (role, family,
profile ids), so the SPA never parses or trusts JWT claims for UI decisions; the axios layer
attaches `getAccessToken()` output and retries exactly once on 401 after a forced refresh;
the offline replay queue calls `getAccessToken()` before replaying. Children are real
Authentik users with guardian-managed simple credentials, set up once per device; their
privilege comes from the DB `role = "child"` row, so even an eternal child session holds only
child-scoped power.

### Rationale

Every alternative that avoids backend token verification founders on the same fact: the
adversary is *inside* the network perimeter. Proxy-injected identity headers, IP allowlists,
and "the LAN is trusted" all collapse when the attacker owns a device on that LAN. Verifying
a signature the child cannot forge is the minimum sufficient mechanism, and the codebase
already isolated exactly the right seam for it. Everything else in this ADR exists to keep
that mechanism from being bypassed in practice: roles that do not force credential sharing,
sessions that do not tempt anyone to disable expiry, and an offline path that never trades
queued child progress against auth strictness.

## Options Considered

### Option 1: SPA PKCE + backend as pure OIDC resource server ✓

**Pros**:

- ✅ The boundary holds even when the ingress is bypassed; stateless backend; the seam swap
  is surgical; Authentik does all credential UX including child-friendly flows.

**Cons**:

- ❌ Tokens live in web storage (accepted, mitigated above); JWKS availability becomes a
  startup dependency (mitigated by caching and fail-closed rules).

### Option 2: Pangolin/proxy forward-auth with identity headers

**Pros**:

- ✅ Zero backend auth code; central policy at the ingress.

**Cons**:

- ❌ Identity is asserted, not proven, at the API: any LAN client that reaches the backend
  directly forges `X-Forwarded-User` trivially. This fails against precisely our threat
  model. Rejected as the boundary; acceptable later only as an additional layer.

### Option 3: Backend-for-frontend session cookies (httpOnly)

**Pros**:

- ✅ Tokens never touch script-readable storage; best XSS posture.

**Cons**:

- ❌ Server-side session state plus a second auth code path in a stateless backend; CSRF
  handling; complicates the PWA offline/replay flow (cookie expiry vs queued writes) for an
  XSS threat the v1 app (no third-party script, strict CSP, no user HTML) does not carry.
  Revisit trigger recorded in the Decision.

### Option 4: Dual accounts instead of admin-inherits-guardian

**Pros**:

- ✅ No authorization code change; maximal audit separation between the two hats.

**Cons**:

- ❌ The one console (C4a-4) would demand an account switch per approval, which in a family
  setting degenerates into a shared always-on admin login, the worst outcome. Rejected; the
  superset design keeps the audit trail (approvals still stamp the admin's `user_id`) without
  the friction.

## Consequences

### Positive

- ✅ ADR-005's invariant holds against the actual adversary; forged-subject takeover is
  closed by signature verification.
- ✅ One parent account runs the entire guardian console; the role documents and the code
  stop contradicting each other.
- ✅ Offline reading and queued sync survive token expiry with no auth compromise.
- ✅ Phase 5 inherits working auth; deployment adds configuration, not code.

### Trade-offs

- ⚠️ Authentik becomes a login-time availability dependency. Mitigation: JWKS caching keeps
  existing sessions verifying through brief outages; offline reading is unaffected by
  definition.
- ⚠️ Approval actions demand a fresh login within 10 minutes. Deliberate; scoped to two
  endpoints; owner-adjustable.
- ⚠️ Web-storage tokens accept a same-origin XSS risk for v1. Compensating controls: strict
  CSP, no third-party scripts, short access-token lifetime, rotating refresh tokens; recorded
  revisit trigger.

### Technical Debt

- Authentik group-to-role provisioning automation is deferred; v1 provisions `User` rows
  manually (a documented one-time admin task per family member).
- Ingress-layer auth as an additional defense layer is deferred to Phase 5 hardening.

## Implementation

### Components Affected

1. **`api/deps.py`**: `_extract_subject` gains an `oidc` implementation (JWT verification as
   specified); `Principal.can_act_as_guardian`; `_resolve_profiles` superset for admins;
   `auth_time` freshness check exported for the approval router.
2. **`core/config.py`**: `auth_mode`, `oidc_issuer`, `oidc_audience`; kill-switch condition
   updated to `auth_mode == "stub" and environment != "local"`.
3. **`api/approval.py`**: freshness guard on `approve` and `send_back`.
4. **New `api/me.py`**: `GET /api/v1/me` returning the resolved principal.
5. **Frontend**: OIDC client (Authorization Code + PKCE), `AuthContext` as specified, axios
   401-refresh-retry, replay-queue token hook.
6. **Authentik (infra, not code)**: one application (audience), token lifetimes, refresh
   rotation, child user accounts; captured as a runbook in `docs/` during C4a-0.
7. **Dependency**: one JWT/JWKS library (for example PyJWT with its JWK client), pinned and
   audited like every other dependency.

### Testing Strategy

- **Forged-token matrix (unit, no network)**: unsigned token, `alg=none`, HS256 signed with
  the public key (downgrade confusion), wrong issuer, wrong audience, expired, `nbf` in the
  future, unknown `kid`, tampered payload, valid-but-no-User-row. Every row must yield 401
  and, critically, the stub-mode suite must yield the same downstream behavior so the IDOR
  suite stays valid in both modes.
- **JWKS lifecycle (integration)**: rotation mid-session, cold start with IdP down (503),
  warm cache with IdP down (still verifying), unknown-kid single refetch.
- **Freshness (integration)**: stale `auth_time` on approve yields 403 with the distinct
  code; fresh re-auth clears it.
- **E2E (pre-release, manual runbook)**: full login, child device setup, offline read and
  reconnect replay against the homelab Authentik.

### Rollout

C4a-0 lands **before** C4a-1 (the app shell consumes `AuthContext`), and the first release
cut requires `auth_mode == "oidc"` in the deployed environment, which the existing
`ConfigurationError` kill switch enforces mechanically.

## Validation

### Success Criteria

- [ ] A syntactically valid but forged bearer token (any row of the forged-token matrix) is
      rejected on every endpoint.
- [ ] A child-role session, regardless of lifetime, cannot invoke approval transitions
      (already tested) and cannot obtain a guardian or admin token without Authentik
      credentials (new).
- [ ] The approval endpoints reject sessions whose authentication is older than the
      freshness window.
- [ ] A story read offline for two hours syncs its queued progress after reconnect with no
      queued write lost, across an access-token expiry.
- [ ] The dev stub cannot start outside `environment == "local"` (unchanged, retested under
      the new `auth_mode` condition).

### Review Schedule

- Initial: C4a-0 acceptance, before C4a-1 begins.
- Ongoing: any change to roles, token lifetimes, or the approval surface; any introduction of
  third-party script or user-authored HTML (revisit Option 3).

## Related

- [ADR-004](./adr-004-homelab-first-deployment.md): the Authentik and Pangolin infrastructure
  this design binds to, and the privacy posture it serves.
- [ADR-005](./adr-005-mandatory-human-approval.md): the approval invariant this boundary
  makes enforceable, including the 2026-06-30 admin-approver amendment this ADR records the
  provisioning decision for.
- [ADR-002](./adr-002-client-pwa.md): the offline-first constraint the session model
  satisfies.
- [Authorization Matrix](../authorization-matrix.md): the endpoint-level role table this ADR
  updates (admin approver, collapsed approve transition).
- 2026-07-01 full-repository senior review, Critical finding 3 (stub auth in the first
  release) and the role-drift finding it consolidates.
