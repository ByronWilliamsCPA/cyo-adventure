---
title: "ADR-009: Supabase as the managed platform for auth, database, and storage"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the decision to adopt Supabase (Auth, Postgres, Storage, queue evaluation)
  as the public-tier platform, replacing the self-hosted Authentik broker and the
  Azure-hosted service set chosen in ADR-008."
tags:
  - planning
  - architecture
  - decisions
  - infrastructure
---

# ADR-009: Supabase as the managed platform for auth, database, and storage

> **Status**: Accepted (2026-07-03; auth decision ratified and implemented, while the P6/P7/P9 items (native Apple sign-in, Supabase Storage, and the pgmq queue) remain outstanding)
> **Date**: 2026-07-02
> **Amends**: [ADR-008](./adr-008-public-app-store-launch.md) (auth broker and public-tier
> hosting; the distribution, monetization, and compliance decisions in ADR-008 stand)

## TL;DR

Adopt Supabase as the public tier's managed platform: Supabase Auth for guardian sign-in
(native Sign in with Apple and Google), Supabase Postgres as the database (async
SQLAlchemy and Alembic unchanged; story blobs stay inline JSONB at launch, with Supabase
Storage adopted later via `blob_ref` when catalog size warrants), and Supabase Queues
(pgmq) evaluated as the Redis/RQ replacement, with FastAPI and the generation worker
remaining our own code on a single small container host. This replaces
ADR-008's self-hosted Authentik broker and multi-service Azure deployment because a solo
operator's scarcest resource is operational attention, and this consolidates roughly five
self-managed or separately-purchased services into one platform plus one container host.

## Context

### Problem

ADR-008 chose Authentik (self-hosted, made highly available) as the public OIDC broker
and Azure Container Apps hosting Postgres, Redis, object storage, and Authentik. For a
solo developer running a commercial kids' app, that plan carries two concentrated risks
already named in the project risk register: operating a public, always-on identity
service, and the Sign in with Apple operational traps (a client-secret JWT that expires
every 6 months, one-time name/email capture, revocation wiring).

A pricing and capability review of consumer auth options (Firebase / Google Identity
Platform, Supabase Auth, AWS Cognito, Clerk, Auth0, Stytch, Descope, hosted Authentik,
2026-07-01 list prices) narrowed the field. Two facts specific to this architecture
drove the read:

- **MAU equals guardians, not readers.** Children never touch the identity provider
  (ADR-008 decision 2, unchanged here), so a family of four kids is one MAU. Every
  viable option costs between $0 and ~$25/month until far past 10,000 paying families;
  auth list price cannot be the deciding variable.
- **The backend needs a managed home regardless.** The plan must buy managed Postgres,
  object storage, and a queue no matter which auth vendor is chosen, so the deciding
  variable is how much of that bill and operational surface the auth platform also
  covers.

### Constraints

- **Technical**: the Python safety pipeline (validation gate, moderation, staged
  generation, publish state machine) and the `Principal` authorization layer stay our
  code; any platform must host plain Postgres (SQLAlchemy 2.x async + Alembic) and
  S3-compatible storage (the seam ADR-004 deliberately preserved). asyncpg's own
  prepared-statement cache collides under a transaction-mode pooler (a reused or
  renamed server-side statement once the pooler reassigns a backend mid-session);
  Task 1.7 mitigates this with `CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE` (disables
  both asyncpg's and the SQLAlchemy dialect's caches, unique-names every prepared
  statement, and switches to `NullPool`), so a Supavisor transaction-pooler connection
  (`:6543`) is viable alongside the direct/session-mode DSN Alembic still uses.
- **Business**: solo operation; minimize vendor count and pager surface. Login
  availability is the one failure a subscription product cannot tolerate.
- **Regulatory**: guardian-only IdP identities, kid-context SDK bans, and the deletion
  obligations (including Apple token revocation) from ADR-008 and Phase 7 are invariant.

### Significance

This decision sets the public tier's vendor topology. It is cheaper to change now, on
paper, than after Phase 6 builds against an issuer.

## Decision

**We will build the public tier on Supabase: Auth and Postgres adopted now, the
Storage seam reserved (adoption deferred until blobs externalize via `blob_ref`),
Queues (pgmq) evaluated as the Redis/RQ replacement, with FastAPI and the generation
worker deployed as our own containers on a single small host.**

The decision decomposes as follows:

1. **Auth: Supabase Auth, guardians only.** Apple and Google configured as providers.
   On iOS the native flow uses `signInWithIdToken` with the identity token from the
   native Apple sign-in sheet, which keeps the Apple Services-ID client secret out of
   the native path entirely; the web OAuth path still uses a client secret rotated at
   most every 6 months. The backend validates Supabase-issued JWTs only (enable
   asymmetric JWT signing keys; verify issuer, audience, expiry, signature via cached
   JWKS). `User.authn_subject` keys on the Supabase user id (`sub` claim), never email.
   Children remain backend-minted scoped sessions exactly as in ADR-008; Supabase's
   anonymous users are not used.
2. **Database: Supabase Postgres.** Async SQLAlchemy and Alembic migrations unchanged;
   connect via a direct connection or session-mode pooling (asyncpg constraint above).
   Automated backups/PITR on the Pro plan; the restore drill remains ours to run.
3. **Storage: deferred adoption of Supabase Storage.** Story blobs are currently
   stored inline in Postgres (`storybook_version.blob` JSONB; the `blob_ref` column
   is reserved but no object-storage code exists yet). They stay inline at launch,
   which is well within Supabase database limits at the 500 KB/story cap. When
   catalog size warrants externalizing blobs, implement `blob_ref` against Supabase
   Storage's S3-compatible API (the portability posture ADR-004 intended, applied at
   that point rather than ported now).
4. **Queue: evaluate Supabase Queues (pgmq) at Phase 9 start.** If the worker's RQ
   usage ports cleanly, Redis disappears from the topology; if not, the fallback is
   managed Redis (e.g., Upstash) with RQ unchanged. The evaluation is time-boxed; the
   fallback is pre-approved so it cannot stall the phase.
5. **Scheduled jobs: pg_cron** for the ADR-007 raw-output retention purge and similar
   maintenance.
6. **Compute: FastAPI + worker on one container host** (Fly.io, Railway, or Azure
   Container Apps; decide at Phase 9 start, P9-03). The safety pipeline never moves
   into Edge Functions.
7. **Authorization stays in FastAPI.** The service connects with the service-role key;
   the `Principal` layer and IDOR suite remain the sole authority. Row Level Security
   is optional defense-in-depth later, never the primary model.
8. **Account deletion** uses the Supabase Auth admin API to remove the guardian
   identity; calling Apple's token-revocation endpoint remains our code (P7-04).
9. **Environments and plan tiers**: local dev keeps the existing auth stub
   (`environment == "local"`); integration/staging runs on a **free-plan** Supabase
   project (limits as of 2026-07: 50,000 MAU, 500 MB database, 1 GB file storage,
   5 GB egress; ample for Phases 6-8 and for the starter library at the 500 KB/story
   blob cap). The **production project upgrades to Pro (~$25/month) at TestFlight
   start (P9-09)**: free projects pause when inactive and lack daily backups, both
   unacceptable in production. The homelab remains the dev/family-staging environment;
   homelab Authentik keeps its existing internal roles but is no longer on the public
   product's path.

### Rationale

At guardian-only MAU counts every candidate's auth line item is noise, so leverage
decides. Firebase's adjacent products (Firestore, Cloud Functions, Firebase Analytics)
fit neither a relational SQLAlchemy backend, a long-running Python worker, nor a
no-third-party-SDKs kids app; picking Firebase means still buying Postgres, storage, and
a queue elsewhere. Supabase's adjacent products are exactly that missing list. Cognito
prices similarly but has the highest configuration friction on the list; Clerk, Stytch,
Descope, and Auth0 charge CIAM prices for B2B features this consumer app never uses;
hosted Authentik starts at $20k/year and targets workforce identity; and self-hosting
Authentik publicly is the operational burden this ADR exists to remove. Consolidating to
Supabase plus one container host takes the vendor count from roughly five to two and
deletes the two riskiest non-product workstreams (public IdP operation, Apple
client-secret plumbing in the native path).

## Options Considered

### Option 1: Supabase platform (Auth + Postgres + Storage + queue evaluation) ✓

**Pros**:

- ✅ One platform covers auth, database, storage, queue candidate, cron, and backups;
  $25/month Pro tier covers 100k guardian MAU.
- ✅ Native `signInWithIdToken` keeps the Apple client secret out of the iOS app path.
- ✅ Plain Postgres + S3 API + open-source auth server underneath: ejection is a
  migration, not a rewrite.

**Cons**:

- ❌ Single platform dependency: a Supabase incident is our login and data-plane outage.
- ❌ pgmq is the least-proven element (mitigated by the pre-approved Redis fallback).

### Option 2: Firebase Auth + separately managed Postgres/storage/queue

**Pros**:

- ✅ Most battle-tested consumer mobile auth SDKs; generous free tier.

**Cons**:

- ❌ Zero leverage beyond auth for this stack; still requires buying and operating
  Postgres, storage, and a queue from other vendors (vendor count stays ~5).
- ❌ Firebase's wider ecosystem (Firestore, Analytics) is unusable here, inviting
  accidental kid-context SDK drift.

### Option 3: Keep ADR-008 baseline (self-hosted Authentik + Azure services)

**Pros**:

- ✅ Maximum control; no new platform dependency; reuses owner's Authentik experience.

**Cons**:

- ❌ Solo operator runs a public IdP with HA, upgrades, and on-call; the risk register's
  "login SPOF" row stays open.
- ❌ Full Apple federation plumbing (client-secret JWT rotation, source configuration)
  is ours in every path, not just web.

### Option 4: AWS Cognito + AWS backend

**Pros**:

- ✅ Cheap at scale; deep AWS integration if the backend moved there.

**Cons**:

- ❌ Highest setup and debugging friction of the shortlist; nothing else in the plan
  argues for AWS.

## Consequences

### Positive

- ✅ The "Authentik becomes a public login SPOF" risk is retired; login availability is
  a platform SLA, not a homelab pager.
- ✅ Phase 6 (P6-05, P6-06) and Phase 9 (P9-03, P9-06) shrink; roughly a week of
  infrastructure work each, plus the HA-Authentik workstream, disappear.
- ✅ Backups/PITR, staging branches, and cron come with the platform.

### Trade-offs

- ⚠️ Platform concentration risk. Mitigation: components are open (Postgres, S3 API,
  GoTrue) and the FastAPI issuer validation is config, so a forced migration is
  bounded; export drills piggyback on the P9-06 restore drill.
- ⚠️ Child-linked rows live in Supabase-managed Postgres (a US processor). Posture is
  equivalent to ADR-008's Azure decision: DPA and SOC 2 available; guardian-only
  identities and the privacy-model classification are unchanged. Verify the DPA and
  data-region selection during P7-08.
- ⚠️ asyncpg + pooling: connections must use direct or session mode; document in
  `TECHNICAL_BASELINE.md` when Phase 6 lands.

### Technical Debt

- The web-path Apple client secret still expires every 6 months; the rotation runbook
  survives in reduced form (one dashboard credential).
- If the pgmq evaluation fails, Redis returns as a third vendor (accepted fallback).

## Implementation

### Components Affected

1. **`api/deps.py`** (P6-01): validate Supabase-issued JWTs (asymmetric signing keys,
   cached JWKS); the dev stub remains for `environment == "local"`. ✅ **Implemented**
   (pulled forward into C4a-1, 2026-07-02): `_verify_oidc_jwt()` uses
   `jwt.PyJWKClient` against `oidc_jwks_url`, allowlists `RS256`/`ES256` only
   (defeats `alg=none`/algorithm-confusion), and checks issuer, audience, and
   expiry. **Deviation from the P6-01 spec**: the spec calls for deleting the
   import-time environment guard outright; instead the guard was kept but made
   conditional (`environment != "local" and not (oidc_issuer and oidc_jwks_url)`
   raises `ConfigurationError` at import time). Rationale: a process that starts
   in a non-local environment with no way to verify any bearer token should fail
   at startup, not on the first request.
2. **`core/config.py`** (P6-02): `oidc_issuer`, `oidc_audience`, `oidc_jwks_url` point
   at the Supabase project; provider-agnostic names are deliberate (ejection path).
   ✅ **Implemented** (2026-07-02), including a `_require_oidc_config_outside_local`
   model_validator mirroring the existing `_reject_dev_database_url_outside_local`
   pattern, so `Settings()` itself refuses to construct outside `local` without
   both values set (defense in depth alongside the deps.py guard above, since
   deps.py's own tests mock `settings` directly and bypass Pydantic validation).
3. **Onboarding** (P6-03): JIT provisioning keys on the Supabase `sub`. Not started;
   `GET /api/v1/me` (added 2026-07-02) returns the verified subject and resolved
   `Principal`, but does not yet provision a `User`/`family_id` row on first sign-in.
4. **Frontend** (P6-06): supabase-js manages sessions, refresh, and Capacitor deep-link
   callbacks; native Apple sign-in via `signInWithIdToken`. **Partially implemented**
   (2026-07-02): `AuthContext` wraps `supabase.auth.getSession()` /
   `onAuthStateChange()`, calls `GET /api/v1/me` to resolve a `Principal`, and syncs
   the access token into the existing `useApi()` localStorage-based interceptor.
   Native Apple `signInWithIdToken`, Capacitor deep-link callbacks, 401-triggered
   token refresh in `useApi.ts`/`offline/sync.ts`, and the CSP `connect-src` update
   are **not yet built** and remain scoped to a future P6-06 pass.
5. **Deletion** (P7-04): Supabase Auth admin API + our Apple revocation call.
6. **Infra** (P9-03): Supabase project (prod) + Supabase project (staging) + one
   container host for API and worker; queue decision executed here. The RQ surface
   is already thin by design: `generation/worker.py` keeps the async core
   Redis/RQ-free and `generation/queue.py` (~75 lines) is the only RQ-coupled
   module, so the pgmq port replaces one module plus a polling loop.
7. **`core/database.py`** (P9-03): set explicit `pool_size`/`max_overflow` for the
   direct/session-mode connection branch (the module's existing `#CRITICAL` marker
   already requires this before production; Supabase session-mode connections are a
   bounded resource, so defaults are not acceptable there). Does not apply to the
   Task 1.7 transaction-pooler branch, which uses `NullPool` and has no pool size of
   its own.
8. **Retention** (ADR-007): purge job moves to pg_cron.

### Testing Strategy

- The Phase 6 negative-token suite (expired, wrong issuer, wrong audience, algorithm
  confusion, tampered signature) runs against Supabase-shaped JWTs. ✅ **Implemented**
  (`tests/unit/test_oidc_verification.py`, 2026-07-02) using real RSA keypairs and a
  fake JWKS client; covers `alg=none` forgery, wrong signing key, missing subject
  claim, and JWKS fetch failure in addition to the criteria above.
- Queue evaluation: run the existing generation integration tests against pgmq before
  committing; fall back to Redis on any failure or time-box expiry.
- Restore drill (P9-06) includes a full export from Supabase (schema + data + storage)
  to prove the ejection path.

## Validation

### Success Criteria

- [ ] Guardian signs in with native Apple and with Google on iOS; backend accepts only
      Supabase-issued JWTs; stranger-family IDOR suite green.
- [ ] Queue decision (pgmq or Redis fallback) made and recorded by end of the P9-03
      evaluation time-box.
- [ ] Restore/export drill from Supabase succeeds.
- [ ] DPA and data-region verified in the P7-08 compliance checklist.

### Review Schedule

- Initial: Phase 6 exit (M6).
- Pre-submission: P7-08 checklist (DPA, privacy labels reflect Supabase as processor).
- Ongoing: revisit if Supabase pricing/terms change materially or MAU approaches plan
  limits.

## Related

- [ADR-008](./adr-008-public-app-store-launch.md): the launch decision this amends
  (distribution, monetization, and compliance portions unchanged).
- [ADR-004](./adr-004-homelab-first-deployment.md): homelab remains dev/family staging;
  the S3 portability it preserved is what makes the storage swap cheap.
- [ADR-007](./adr-007-raw-output-retention.md): retention purge moves to pg_cron.
- [PROJECT-PLAN.md](../PROJECT-PLAN.md): Phases 6, 7, and 9 items updated to this
  topology (plan v2.1).
