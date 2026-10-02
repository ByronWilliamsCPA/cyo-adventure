---
title: "ADR-032: Self-hosted Supabase-equivalent stack for non-production environments"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the decision to move the combined dev/test environment off Supabase Cloud onto
  a self-hosted stack on the docker-host homelab, so the freed Supabase Cloud project slot can be
  repurposed, while production stays on Supabase Cloud untouched."
tags:
  - planning
  - architecture
  - decisions
  - infrastructure
---

# ADR-032: Self-hosted Supabase-equivalent stack for non-production environments

> **Status**: Accepted (2026-09-21). Ratification is per decision point, not blanket:
> Decisions 1, 2, 3 and 6 were ratified by the project owner via AskUserQuestion in the
> authoring session on 2026-09-21. Decision 5 (stack tier placement) and Decision 4's backup
> *target* (a separate R2 bucket, revised from the original "reuse production's bucket") were
> ratified on 2026-10-02 during review, as was the migration path in Decision 2. Decision 4's
> *script split* (`scripts/backup_database.py` stays production-only) remains an unratified
> recommendation, tracked as `UW-A62`.
> **Date**: 2026-09-21
> **Amends**: [ADR-009](./adr-009-supabase-platform.md) (Decision point 9, "Environments and plan
> tiers": the free-plan staging Supabase project and the "homelab remains the dev/family-staging
> environment... no longer on the public product's path" framing are both superseded for the
> combined dev/test environment specifically. ADR-009's Auth/Database/Storage/Queue/Compute/
> Authorization decisions, and the production plan-tier decision, are unchanged.)
> **Relates to**: [ADR-021](./adr-021-service-account-rls-and-worker-deployment.md) (the
> `cyo_api`/`cyo_worker` roles and RLS policies apply unchanged, since they ship as environment-
> agnostic migration SQL per ADR-012), [ADR-012](./adr-012-supabase-cli-migrations.md) (the
> migration mechanism this decision reuses against the new stack's Postgres), and
> [ADR-004](./adr-004-homelab-first-deployment.md) (the homelab-first precedent this decision
> extends to a second environment)

## TL;DR

Byron's Supabase account allows exactly two Cloud projects. Production keeps one; the combined
dev/test environment currently occupies the other. This ADR moves dev/test to a self-hosted
stack (the full official `supabase/docker` reference: Postgres, GoTrue, PostgREST, Realtime,
Storage, Kong, Studio) on the existing docker-host homelab, images mirrored through
`container-images` rather than pulled from upstream, deployed through the existing Portainer
GitOps + Infisical + Traefik automation, reachable at a public HTTPS hostname because Apple/Google
OAuth requires a real redirect URI. This frees the second Cloud project slot for a different
project. MinIO/object storage is explicitly out of scope; the `storage-api` service ships as part
of the stack but is not backed by S3-compatible storage in this phase. Production is untouched.

## Context

### Problem

CYO Adventure's Supabase account has a hard cap of two Cloud projects. One is production; the
other is a single combined project serving both integration/staging and local-adjacent testing
(ADR-009 Decision point 9). Byron wants a second project slot free for an unrelated project, which
means the current dev/test project must either be deleted outright (losing the environment) or
relocated off Supabase Cloud entirely. Deleting it without replacement is not acceptable: it is the
only environment that exercises the full Supabase-shaped surface (GoTrue-issued JWTs, RLS-scoped
Postgres, Supavisor pooling) before a change reaches production.

A 2026-09-21 design session (brainstorming skill, six `AskUserQuestion` rounds, three
`Explore`-agent research passes across this repo, `homelab-infra`, and `container-images`)
established that this is tractable specifically because ADR-009 already narrowed the app's
Supabase surface deliberately: the backend validates JWTs against provider-agnostic
`OIDC_ISSUER`/`OIDC_JWKS_URL` config rather than a Supabase SDK, RLS is plain Postgres SQL
(ADR-021, ADR-022), migrations are portable Supabase CLI SQL (ADR-012) with no Alembic
dependency, and PostgREST/Realtime/Storage/Edge Functions are already documented as unused. The
one Supabase-CLI-specific piece found is the nightly backup job
(`.github/workflows/supabase-backup.yml`, `scripts/backup_database.py`), which shells out to
`supabase db dump`.

### Constraints

- **Technical**: Apple and Google OAuth require a real, publicly reachable HTTPS redirect URI at
  sign-in time; an internal-only deployment would break real OAuth testing and force a dev-only
  auth bypass that diverges from production's auth path. `homelab-infra` already runs Portainer
  GitOps (5-minute poll, no webhook), Infisical for secrets (`scripts/infisical/deploy.sh`), and a
  hand-maintained Traefik dynamic config; any new service should use these, not a bespoke mechanism.
  `container-images` already mirrors public images by digest with Trivy/SBOM/drift-check tooling,
  but its `source_tier` catalog field is a hard-coded two-value enum
  (`scripts/validate_catalog_schema.py`), both meaning "hardened base image," which does not
  describe an unmodified vendor mirror.
- **Business**: solo operator (ADR-009's operating premise, unchanged). The point of this work is
  to free an account slot, not to add a second ongoing ops burden; the design deliberately reuses
  existing automation in all three repos rather than building new tooling.
- **Regulatory**: non-production data carries no real guardian or child PII by design (test
  fixtures only), so this ADR does not reopen ADR-018's children's-privacy posture. Production
  stays on Supabase Cloud, so the DPA and data-region posture ADR-009 recorded for production is
  unaffected.

### Significance

This changes where non-production data and identity live, and it is the template for a possible
future split of non-prod into separate staging/dev/test stacks (explicitly anticipated, not
committed to here: Phase 1's stack is built as a reusable pattern rather than a one-off). Getting
the image-provenance and secrets handling wrong here would be cheap to notice (non-prod) but sets
the pattern a later staging/dev/test split, and any future self-hosted addition, would copy.

## Decision

**We will self-host the full official Supabase stack for the combined dev/test environment on the
existing docker-host homelab, mirror its container images through `container-images` under a new
`vendor` source-tier category, deploy it through the existing Portainer/Infisical/Traefik
automation at a public hostname, and give it its own lightweight backup independent of production's
backup script. Production remains on Supabase Cloud, untouched.**

1. **Auth and full stack scope**: self-host the complete official `supabase/docker` stack
   (Postgres, GoTrue, PostgREST, Realtime, Storage, Kong, Studio, and the stack's supporting
   services), not a leaner Postgres+GoTrue-only setup, and not a swap to Authentik (already
   running in `homelab-infra`) as the OIDC provider. This was the non-default option among what
   was recommended; taken as the owner's explicit choice (see Options Considered, Dead end 1).
2. **Network exposure**: a public hostname via the existing Traefik + ZeroSSL setup, not
   internal-only, because Apple/Google OAuth needs a real redirect URI at sign-in. The public
   surface is an explicit allowlist, not the whole stack:
   - **Public**: only GoTrue, through the Kong gateway's `/auth/v1/` path prefix (sign-in,
     OAuth `authorize`/`callback`, token refresh, and the JWKS document). The frontend uses
     `supabase-js` for auth only; nothing in `frontend/src/` calls PostgREST, Realtime,
     Storage or Functions, so `/rest/v1/`, `/realtime/v1/`, `/storage/v1/` and
     `/functions/v1/` get no public route. Confirm the prefix list against the current
     official compose during `UW-A60` before the router is written.
   - **Internal only, never routed by Traefik**: Postgres, Supavisor, Studio, `postgres-meta`
     (Kong's `/pg/` route), and any admin or metrics endpoint. Studio, if run at all, is
     reached over the homelab network or a tunnel, not the public hostname.
   - **Migrations (ratified 2026-10-02)**: `.github/workflows/supabase-staging.yml` runs
     `supabase db push` from GitHub-hosted runners today, which against this stack would need
     Postgres reachable from the internet. Instead, the non-prod migration job runs on a
     self-hosted GitHub Actions runner on the homelab, so the database never needs a public
     route. Publishing the pooler behind an IP allowlist was rejected: GitHub's runner ranges
     are wide and change.
3. **Object storage**: MinIO is explicitly out of scope for this phase. The stack's `storage-api`
   service still runs (it ships with the official compose), but story blobs remain inline JSONB
   per ADR-009; nothing in this app writes to Supabase Storage today. **Open item**: confirm the
   official compose's default storage backend works filesystem-only with no extra config, since an
   unconfigured `storage-api` that hard-requires S3-compatible config would undercut this
   deferral (see Follow-on work, `UW-A60`).
4. **Backup**: a new, lightweight `pg_dumpall`-based backup for the new stack, with daily-only
   cadence and short retention, not production's tiered daily/weekly/monthly scheme.
   - **Target (revised and ratified 2026-10-02)**: a *separate* non-production bucket in the
     same R2 account, not production's bucket. Sharing the bucket was the original wording and
     is unsafe for two verified reasons. First, `scripts/backup_database.py` replaces the
     production bucket's entire lifecycle configuration on each run: it owns only the
     `expire-daily`/`expire-weekly`/`expire-monthly` rule IDs and reports, then overwrites,
     anything else, so a non-prod retention rule there would be deleted nightly. Second, R2
     API tokens are scoped per bucket rather than per key prefix (the production token is
     deliberately limited to one bucket for exactly this reason), so any non-prod credential
     able to write the production bucket could also overwrite or delete production backups.
   - **Isolation requirements for the new bucket**: its own `.cyo-backup-bucket`-style marker
     object, checked before any write; its own lifecycle rule; an object-scoped API token
     limited to that bucket only; and an encryption key distinct from production's
     `BACKUP_ENCRYPTION_KEY`. No non-prod credential is granted any access to the production
     backup bucket.
   - **Restore restrictions**: a non-prod restore reads only from the non-prod bucket and
     writes only to the self-hosted stack's Postgres. Production restores remain governed by
     `docs/operations/runbook.md` section 6 and are unaffected.
   - **Script split**: `scripts/backup_database.py` stays production-only rather than being
     parameterized for both targets; the new stack gets an independent backup sidecar built in
     `homelab-infra`. This split was the design session's recommendation and is not yet
     ratified (Follow-on work, `UW-A62`).
5. **Stack tier placement**: `homelab-infra`'s `stacks/platform/cyo-supabase/`. `stacks/platform/`
   already exists as a real, if empty, tier folder. Proposed in the 2026-09-21 design session and
   ratified by the owner on 2026-10-02.
6. **Image sourcing**: mirror the stack's vendor images through `container-images`'s existing
   digest-copy/Trivy/SBOM/drift-check pipeline under a new `source_tier: "vendor"` catalog
   category, rather than pulling directly from Docker Hub in the compose file (the initial
   recommendation, corrected by the owner; see Options Considered, Dead end 2), and rather than
   mislabeling the images under the existing `"primary"` (hardened-base) category (Dead end 3).

**Rollout order** (each a separate repo, separate branch, tracked in Follow-on work): this ADR
first; then `container-images` catalog work; then the `homelab-infra` stack build; then this repo
wires the app at the new stack; then a burn-in period; then the old Supabase Cloud dev/test project
is decommissioned, which is the actual point of this ADR.

### Rationale

At non-production data volumes and a solo operator's time budget, the deciding factors are
consistency with existing patterns and blast-radius containment, not marginal cost. Self-hosting
the full stack (rather than a leaner Postgres+GoTrue substitute) keeps the new environment
behaviorally identical to what production's Supabase Cloud project presents, so staging continues
to catch integration issues a narrower substitute would hide; the Authentik alternative was
rejected for the same reason; it would require reworking the frontend auth flow and re-registering
OAuth apps for no corresponding gain. Routing images through `container-images` costs one schema
extension in a shared repo and buys the same digest-pin/Trivy/SBOM/drift-detection coverage every
other image in the fleet already gets, which is a real supply-chain benefit for a stack that will
handle even test-shaped OAuth tokens. Deferring MinIO keeps this phase scoped to what the app
already exercises rather than building ahead of need.

## Options Considered

### Option 1: Self-hosted full Supabase stack via `container-images`, public hostname ✓

**Pros**:

- ✅ Frees the second Supabase Cloud project slot, the actual goal.
- ✅ Behaviorally matches production's Supabase surface (GoTrue, RLS-scoped Postgres), so
  staging keeps catching what a narrower substitute would hide.
- ✅ Reuses all three repos' existing automation (Portainer GitOps, Infisical, Traefik,
  `container-images` mirror pipeline); no new ops mechanism to learn or maintain.

**Cons**:

- ❌ One-time schema extension needed in `container-images` (`source_tier: "vendor"`).
- ❌ GoTrue's SMTP requirement at boot is unverified for a guardian-OAuth-only app (see Follow-on
  work, `UW-A60`).

### Option 2: Swap auth provider to Authentik, self-host plain Postgres only

**Pros**:

- ✅ Avoids running GoTrue at all; homelab already runs Authentik for other purposes.

**Cons**:

- ❌ Requires reworking the frontend auth flow (currently `supabase-js`) and re-registering
  Apple/Google OAuth apps against a new issuer, for an environment whose entire purpose is to
  mirror production's auth path.
- ❌ Rejected by the owner in the authoring session (Dead end 1).

### Option 3: Pull Supabase's images directly from upstream Docker Hub in the compose file

**Pros**:

- ✅ Zero changes needed in `container-images`.

**Cons**:

- ❌ Bypasses this org's established "copy of a public container" pattern entirely, losing
  digest-pinning, Trivy scanning, and SBOM generation for every image in this stack.
- ❌ This was the initial recommendation in the design session; the owner corrected it (Dead
  end 2), calling out `container-images` as the established pattern.

### Option 4: Delete the dev/test project outright, run nothing self-hosted

**Pros**:

- ✅ Zero infrastructure work; frees the slot immediately.

**Cons**:

- ❌ Removes the only environment that exercises the full Supabase-shaped surface before a change
  reaches production, reopening exactly the integration-blind-spot risk ADR-009 closed by
  adopting Supabase in the first place.

## Consequences

### Positive

- ✅ The second Supabase Cloud project slot frees up once the old dev/test project is
  decommissioned (Follow-on work, `UW-A63`), which is the actual point of this ADR.
- ✅ Non-production stays behaviorally close to production's auth and database surface, so it
  keeps catching what it already catches today.
- ✅ Every Supabase vendor image gains the same digest-pin/Trivy/SBOM/drift-detection coverage
  the rest of the fleet already has, a supply-chain improvement that has no equivalent today
  (images are currently pulled straight from Supabase Cloud's managed infrastructure, outside any
  of this org's own scanning).
- ✅ Phase 1's stack is built as a reusable template, so a later split into separate
  staging/dev/test stacks (anticipated, not committed to) reuses this pattern rather than starting
  over.

### Trade-offs

- ⚠️ The homelab becomes a second place identity and test data live, alongside Supabase Cloud
  production. Mitigation: non-production data carries no real guardian/child PII by design, so
  this does not reopen ADR-018's compliance posture; production's own DPA and data-region
  decisions are unaffected.
- ⚠️ A public hostname on the homelab is new attack surface (though the homelab already runs
  publicly reachable services via Traefik). Mitigation: reuses the existing Traefik + ZeroSSL TLS
  termination and Infisical secrets pattern rather than a bespoke exposure mechanism, and
  publishes only GoTrue's `/auth/v1/` routes; Postgres, Supavisor, Studio and admin endpoints are
  never routed publicly (Decision point 2).
- ⚠️ A homelab self-hosted GitHub Actions runner is new infrastructure that executes workflow code
  with network access to the non-prod database. Mitigation: register it to this repository only,
  restrict it to the non-prod migration workflow by label, and never schedule it for
  `pull_request` events from forks.
- ⚠️ `container-images`' `source_tier` field gains a value (`vendor`) whose supply-chain posture
  differs from `primary`/`distroless` (an unmodified vendor image, not a hardened rebuild); this
  must be documented clearly in that repo so a future reader does not conflate the two meanings.

### Technical Debt

- Per-role/per-environment credential rotation for the new stack's Postgres superuser and
  GoTrue JWT signing secret is deferred to whenever `homelab-infra`'s existing secret-rotation
  practice next runs; not a new mechanism, just a new set of secrets under it.
- If the GoTrue SMTP requirement (Follow-on work, `UW-A60`) turns out to be hard-blocking, an SMTP
  relay becomes a second thing to provision that this ADR did not originally scope.

## Implementation

### Components Affected

1. **`container-images`** (separate repo, separate branch off up-to-date `main`, not the
   stale-looking `feat/mirror-drift-check`): add `"vendor"` to `ALLOWED_SOURCE_TIERS` in
   `scripts/validate_catalog_schema.py`; add a README note distinguishing hardened-base mirrors
   from vendor mirrors; add `catalog/images.yaml` entries with `disposition: mirror_only` for each
   Supabase stack image. The exact image list must be confirmed against Supabase's current
   `docker/docker-compose.yml` before entries are written, not assumed from prior knowledge (see
   Follow-on work, `UW-A59`).
2. **`homelab-infra`** (separate repo, separate branch): new
   `stacks/platform/cyo-supabase/compose.yaml` adapted from Supabase's official self-hosting
   reference, every image reference pointed at this org's GHCR mirror; new Traefik router/service/
   middleware entries in `services/traefik/dynamic/services.yml` for the chosen hostname (not yet
   decided, owner's call), routing only the `/auth/v1/` prefix (Decision point 2); secrets
   provisioned through the existing `scripts/infisical/deploy.sh` pattern, never a committed
   `.env`; a new backup image via one matrix entry in the existing `dhi-build.yml` pattern,
   writing to its own non-prod R2 bucket (Decision point 4); and a self-hosted GitHub Actions
   runner for the non-prod migration job (see Follow-on work, `UW-A60`).
3. **CYO_Adventure** (this repo, separate branch, after the stack exists): new Infisical/env
   entries for `DATABASE_URL`, `WORKER_DATABASE_URL` (via the new stack's Supavisor session-mode
   pooler, keeping `CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE`), `OIDC_ISSUER`/
   `OIDC_JWKS_URL` (new GoTrue), `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` (new Kong gateway);
   run the existing `supabase/migrations/` unchanged against the new stack's Postgres (this is
   exactly the portability ADR-012's migration mechanism was chosen for); register the new
   callback URL in both the Apple and Google developer consoles (the one step with no config/file
   equivalent); move the non-prod leg of `.github/workflows/supabase-staging.yml` onto the
   homelab self-hosted runner and point it at the new stack with `supabase db push --db-url`,
   replacing the Cloud-only `supabase link --project-ref` step (see Follow-on work, `UW-A61`).
   The same workflow's `supabase config push --project-ref` step has no self-hosted equivalent:
   it deploys Auth settings through the Supabase Cloud Management API, which a self-hosted stack
   does not expose, and it would fail outright once the Cloud project is deleted. It is removed
   from the non-prod leg. The Auth settings it carried (the base `[auth]` block of
   `supabase/config.toml`, plus the `[remotes.staging.auth]` overlay's `site_url` and
   `additional_redirect_urls`) are instead set as GoTrue `GOTRUE_*` environment variables in the
   `homelab-infra` compose, non-secret values in the compose file and OAuth client secrets via
   Infisical. A committed mapping from each `config.toml` auth key to its `GOTRUE_*` variable
   gives an Auth change a known place to land in both environments; without it, an Auth setting
   changed in `config.toml` would silently reach production only.
   **Google is not in that mapping and needs its own step.** `config.toml` deliberately omits
   `[auth.external.google]` (see its `#CRITICAL` comment): Google sign-in, the guardian login
   path, is enabled on staging with a client ID and secret held only in the Supabase Cloud
   dashboard. Before the Cloud project is deleted, those credentials (or a new non-prod Google
   OAuth client) must be put in Infisical and wired as `GOTRUE_EXTERNAL_GOOGLE_ENABLED`,
   `GOTRUE_EXTERNAL_GOOGLE_CLIENT_ID`, `GOTRUE_EXTERNAL_GOOGLE_SECRET` and
   `GOTRUE_EXTERNAL_GOOGLE_REDIRECT_URI`, with the new callback URL registered in the Google
   console; otherwise guardian Google sign-in fails on the new stack.

### Testing Strategy

- `homelab-infra`: bring the new stack up locally/on the homelab and verify GoTrue issues a valid
  JWT against a real Apple/Google OAuth round trip before this repo is repointed at it.
- CYO_Adventure: the existing OIDC negative-token suite
  (`tests/unit/test_oidc_verification.py`) needs no change, since it tests Supabase-shaped JWTs
  generically. It is offline by design (an autouse fixture swaps the JWKS client for a fake and
  points the URL at `example.invalid`), so it proves nothing about the new stack and is NOT the
  smoke check. The live check is separate: fetch `/auth/v1/.well-known/jwks.json` from the public
  hostname and confirm it serves a signing key, then sign in with a synthetic test account and
  call an authenticated backend endpoint (`GET /api/v1/me`) with the issued token, which proves
  the backend's `OIDC_ISSUER`/`OIDC_JWKS_URL` configuration accepts the new GoTrue end to end.
- CYO_Adventure: `supabase/migrations/` applied clean, end to end, against the new stack's fresh
  Postgres is the acceptance test for ADR-012's portability claim actually holding under a new
  target.
- Burn-in: the new stack runs the combined dev/test workload for an owner-determined period before
  the old Cloud project is decommissioned (see Follow-on work, `UW-A63`).

## Validation

### Success Criteria

- [ ] The new self-hosted stack is reachable at its public hostname with a valid TLS certificate
      and issues GoTrue JWTs the backend accepts under the existing OIDC verification path.
- [ ] `supabase/migrations/` applies cleanly against the new stack's Postgres with no manual
      intervention.
- [ ] A guardian can complete real Apple and Google OAuth sign-in against the new stack, using
      dedicated synthetic test accounts only: one Apple ID and one Google account created for
      this purpose and owned by the core-maintainer, never a family member's or any real
      guardian's account. The GoTrue `auth.users` and `auth.identities` rows those sign-ins create
      are deleted after each validation run (or wiped with the stack on reset), so the
      provider claims they hold (email, name, provider subject) do not persist in non-prod. This
      keeps the Regulatory constraint above ("no real guardian or child PII") true for identity
      records as well as fixture data.
- [ ] The new stack's backup runs on schedule and a restore has been exercised at least once.
- [ ] The old combined dev/test Supabase Cloud project is deleted and the account shows one free
      project slot.

### Review Schedule

- Initial: once `container-images` and `homelab-infra` work (Follow-on work, `UW-A59`, `UW-A60`)
  land and the stack is reachable.
- Ongoing: at the end of the burn-in period, before decommissioning the old project
  (`UW-A63`); revisit if a later staging/dev/test split (anticipated, not committed to) is taken up.

## Follow-on work

- **`UW-A59`** (`container-images`, `external:container-images`): extend
  `scripts/validate_catalog_schema.py`'s `ALLOWED_SOURCE_TIERS` with `"vendor"`, document the
  distinction from the existing hardened-base tiers, and add catalog entries for the Supabase
  stack's images once confirmed against Supabase's current `docker/docker-compose.yml` (the exact
  image list, and whether it includes `vector`/`imgproxy`/`postgres-meta` beyond the
  `postgres, gotrue, postgrest, realtime, storage-api, studio, supavisor, kong` starting guess, is
  unverified as of this ADR).
- **`UW-A60`** (`homelab-infra`, `external:homelab-infra`): build
  `stacks/platform/cyo-supabase/compose.yaml`, wire Traefik dynamic config for the chosen hostname
  (not yet decided) with a public router for the `/auth/v1/` prefix only (Decision point 2),
  provision secrets via Infisical, add the daily `pg_dumpall`-based backup sidecar via
  `dhi-build.yml` writing to its own non-prod R2 bucket with the isolation requirements in
  Decision point 4, and stand up the self-hosted GitHub Actions runner for non-prod migrations.
  Two open items to resolve during this work: whether GoTrue hard-requires SMTP configuration to
  boot even though guardians sign in via Apple/Google OAuth only (unverified), and whether the
  official compose's default storage backend for `storage-api` works filesystem-only without
  extra config (Decision point 3).
- **`UW-A61`** (CYO_Adventure, `now`, status `blocked` on `UW-A60` landing): wire the app at the
  new stack (env/Infisical entries, run migrations, register the new OAuth redirect URI in both
  developer consoles, move the non-prod leg of `supabase-staging.yml` onto the self-hosted
  runner, and remove its `supabase config push` step in favour of the `GOTRUE_*` environment
  mapping described in Components Affected, item 3). No application code changes; config and
  workflow only.
- **`UW-A62`** (CYO_Adventure, `now`, status `decision`, owner: core-maintainer): ratify that
  `scripts/backup_database.py` stays production-only and the new stack gets its own
  `homelab-infra`-owned backup sidecar (Decision point 4), rather than parameterizing the existing
  script for both targets. This was the design session's recommendation, not something the owner
  separately confirmed.
- **`UW-A63`** (CYO_Adventure, `now`, status `blocked` on `UW-A59` through `UW-A62` landing and an
  owner-determined burn-in period elapsing): decommission the old combined dev/test Supabase Cloud
  project once the new stack has run clean, freeing the second Cloud project slot. Deleting the
  Cloud project is irreversible, so each of the first four Success Criteria above must be met and
  recorded with evidence before it happens: the public hostname serves a valid TLS certificate and
  GoTrue JWTs the backend accepts; `supabase/migrations/` applied clean; Apple and Google OAuth
  sign-in completed with the synthetic test accounts; and a backup restore exercised from the
  non-prod bucket.

## Related

- [ADR-009](./adr-009-supabase-platform.md): the platform decision this amends (Decision point 9,
  environments and plan tiers, for the dev/test environment only; auth, database, storage, queue,
  compute, and authorization decisions, and the production plan tier, stand unchanged).
- [ADR-021](./adr-021-service-account-rls-and-worker-deployment.md): the `cyo_api`/`cyo_worker`
  roles and RLS policies apply to the new stack unchanged, since they ship as portable migration
  SQL rather than Cloud-project-specific configuration.
- [ADR-012](./adr-012-supabase-cli-migrations.md): the forward-only, CLI-applied migration
  mechanism this decision relies on for portability between Supabase Cloud and the new self-hosted
  Postgres.
- [ADR-004](./adr-004-homelab-first-deployment.md): the homelab-first precedent; this ADR extends
  homelab hosting to a second, non-prod Supabase-equivalent environment.
- [ADR-018](./adr-018-childrens-privacy-compliance.md): unaffected; non-production data carries no
  real guardian/child PII by design.
- [docs/planning/unscheduled-work-register.md](../unscheduled-work-register.md): `UW-A59` through
  `UW-A63`, this ADR's follow-on work.
