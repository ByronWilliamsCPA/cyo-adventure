---
title: "ADR-020: Dedicated least-privilege service accounts, enforced RLS, and in-repo worker deployment"
schema_type: planning
status: proposed
owner: core-maintainer
purpose: "Record the decision to replace the shared postgres owner-role database
  connection with dedicated least-privilege service accounts for the API and the
  generation/cover workers, to attach real RLS policies to those accounts, and to
  bring the RQ worker's deployment and liveness signal into this repository."
tags:
  - planning
  - architecture
  - decisions
  - infrastructure
  - security
---

# ADR-020: Dedicated least-privilege service accounts, enforced RLS, and in-repo worker deployment

> **Status**: Proposed
> **Date**: 2026-07-20
> **Amends**: [ADR-009](./adr-009-supabase-platform.md) (Decision point 6, "Compute: FastAPI
> + worker on one container host," and Decision point 7, "the service connects with the
> service-role key... Row Level Security is optional defense-in-depth later"; the auth and
> Postgres-hosting decisions in ADR-009 stand)

## TL;DR

Replace the single shared `postgres` owner-role database connection with two dedicated,
least-privilege Postgres roles (`cyo_api`, `cyo_worker`), attach real `CREATE POLICY`
grants to those roles so the RLS already enabled on every table stops being a placeholder,
and add an in-repo worker service definition plus a stale-job observability check so a
generated story reaching the guardian/admin review queue no longer depends silently on a
sibling infrastructure repository being correctly configured.

## Context

### Problem

A workflow review of the story-generation-to-review pipeline (2026-07-20) traced the
actual code path from guardian request to review queue and found the pipeline itself
writes correctly at every stage (`StoryRequest` → `Concept` → `GenerationJob` →
`Storybook`/`StorybookVersion` → moderation report → `in_review` status →
`GET /api/v1/review-queue`). Two gaps sit underneath that working pipeline, both already
flagged in code comments but never resolved:

1. **No dedicated service account exists.** `core/database.py:123` builds one async engine
   from `settings.database_url` for both the FastAPI web process and the RQ workers
   (`generation/worker.py`, `covers/worker.py`). All three connect as the `postgres` role
   (table owner via the Supavisor pooler). `supabase/migrations/20260711200745_enable_rls_all_tables.sql`
   enables RLS on all 19 application tables but defines zero `CREATE POLICY` statements,
   with its own `#CRITICAL` comment warning: *"If the app's DB connection role is ever
   changed to a non-owner role... RLS enabled here WILL start restricting backend
   queries... add explicit policies for it first."* Standing up any least-privilege
   service account today would trip that exact landmine.
2. **The worker process is not deployed or observable from this repo.**
   `docs/operations/runbook.md` already documents that `python -m
   cyo_adventure.generation.worker_main` is not defined in `docker-compose.yml` or
   `docker-compose.prod.yml`; the live deployment runs it as `cyo-worker` in the separate
   `ByronWilliamsCPA/homelab-infra` repository. The worker's own stranded-job reclaim sweep
   (`_DEFAULT_STALE_AFTER`, 30 minutes) only runs *when a worker process starts* — so an
   environment where the worker container silently isn't running has no self-healing and
   no alarm; `GenerationJob` rows sit `queued` forever with nothing surfacing that fact.

Both gaps were raised together because the fix for #1 (introducing a real service account)
is unsafe to ship without also fixing the RLS placeholder it would activate, and #2 is the
more likely explanation for "a drafted story doesn't reach review" in practice today.

### Constraints

- **Technical**: must not break the Supavisor transaction-pooler branch (Task 1.7's
  prepared-statement-cache workaround, `database_disable_prepared_cache`); Supabase CLI
  migrations are forward-only (ADR-012) with no down-migrations, so role/policy creation
  must be purely additive; migrations are plain SQL committed to git, so credentials must
  never be embedded in migration files.
- **Business**: solo operator (ADR-009's operating premise); this must not become a second
  ongoing ops burden or a re-litigation of the Phase 9 hosted-infra decision (container
  host, pgmq vs. Redis), which stays deliberately deferred.
- **Regulatory**: tables hold child-linked data; reducing blast radius on either process's
  credentials is consistent with the ADR-018 privacy posture.

### Significance

ADR-005 requires that no story reach a child without a recorded human approval, enforced by
the `GenerationJob`/`Storybook` state machines. Both machines depend on a worker process
actually running and a database identity actually permitted to write. If either silently
fails, the product's core guarantee doesn't get violated, it just never gets exercised
(nothing to approve or reject), which is a worse failure mode than a loud error because
nothing in the current system reports it.

## Decision

**We will introduce two least-privilege Postgres service roles for the API and the
worker processes, ship the RLS policies that make them (and the existing deny-by-default
posture for `anon`/`authenticated`) actually enforced, and bring the worker's deployment
and a staleness check into this repository.**

1. **Two dedicated roles**: `cyo_api` (FastAPI web process) and `cyo_worker`
   (`generation/worker.py`, `generation/worker_main.py`, `covers/worker.py`). Both created
   `NOLOGIN` in migration SQL; a login password is set out-of-band per environment (Supabase
   dashboard SQL editor or a one-time `ALTER ROLE`) and stored in the existing secrets
   mechanism, never committed. Both roles get an identical grant set initially (`SELECT`,
   `INSERT`, `UPDATE`, `DELETE` on the 19 tables already listed in
   `20260711200745_enable_rls_all_tables.sql`, `USAGE`/`SELECT` on their sequences, no DDL,
   no role-management privileges). Splitting them now buys blast-radius separation and
   independent rotation/audit trails even before their grants diverge; tightening one
   relative to the other (e.g., the worker plausibly never needs to touch `user`/`family`
   directly) is deliberately deferred to a follow-up once real usage is observed.
2. **Explicit RLS policies** for `cyo_api` and `cyo_worker` on every table currently listed
   in the RLS-enable migration, so enforcement is a named grant instead of incidental table
   ownership. The existing deny-by-default posture for `anon`/`authenticated` (no
   PostgREST usage anywhere in the codebase, verified in that migration's own comment) is
   unchanged.
3. **Config/code split**: `core/config.py` gains `worker_database_url` (same
   `AliasChoices`/env-prefix pattern as `database_url`), defaulting to `database_url` when
   unset so any environment that hasn't split credentials yet keeps working unchanged.
   `core/database.py` gains a second engine and `get_worker_session()`; the three worker
   entry points switch to it. FastAPI request handlers keep using `get_session()`.
4. **Explicit pool sizing**, folded in because it touches the same file: add
   `database_pool_size`/`database_max_overflow` settings, applied to both engines. This
   closes the `#CRITICAL` item already recorded against `core/database.py` in ADR-009's
   Components Affected list ("now live and unsized").
5. **In-repo worker service**: add a `worker` service to `docker-compose.yml` (same image,
   `worker_main` command in place of `uvicorn`) and `docker-compose.prod.yml`, and
   uncomment Redis in the dev compose file. This does not replace `homelab-infra` as the
   deployment orchestrator of record for the live environment; it removes this repo's
   dependency on that sibling repo for locally or CI-verifying that the full pipeline
   works, and gives a definition that matches what's actually deployed. The Phase 9 /
   P9-03 decision (final container host, queue vendor) is unchanged and stays deferred.
6. **Stale-job observability**: extend `api/health.py` (or a small admin endpoint) with a
   check counting `GenerationJob` rows in `queued`/`running` past
   `worker_main._DEFAULT_STALE_AFTER` (30 minutes), so "nothing is consuming the queue"
   becomes an observable, alertable condition rather than a silent one.

### Rationale

Least-privilege service accounts close the blast-radius gap the current shared owner-role
connection has and finally act on the RLS migration's own `#VERIFY` instruction, rather
than leaving it as a comment nobody has followed up on. Bringing the worker's definition
into this repo (without displacing `homelab-infra`) closes the reproducibility gap that let
the queue go silently unconsumed; the staleness check converts that failure mode from
invisible to observable. Scoping this to credentials, RLS, and observability (not
container-host or queue-vendor choice) keeps it inside what a solo operator can ship and
verify quickly, leaving the larger, genuinely deferrable infra decision in Phase 9 where
the roadmap already puts it.

## Options Considered

### Option 1: Dedicated roles + explicit RLS grants + in-repo worker + staleness check ✓

**Pros**:

- ✅ Closes the exact landmine the existing RLS migration's comment already warns about.
- ✅ Makes "is the pipeline actually working" verifiable from this repo alone, in CI and
  locally, without trusting a sibling repo's state.
- ✅ Converts a silent failure mode (stuck queue, nobody notified) into an observable one.

**Cons**:

- ❌ Two roles to provision and rotate per environment instead of one.
- ❌ Touches `core/database.py`, a file already carrying two `#CRITICAL` markers; requires
  care not to regress the transaction-pooler branch.

### Option 2: Leave the owner-role connection as-is; treat this as pure Phase 9 work

**Pros**:

- ✅ Zero work now.

**Cons**:

- ❌ Leaves the RLS placeholder exactly as dangerous as it is today.
- ❌ Does nothing about the worker-deployment/observability gap, which is the more likely
  explanation for "a drafted story isn't reaching review" right now, and which has nothing
  to do with the Phase 9 hosted-infra decision.

### Option 3: Pull the full Phase 9 P9-03 decision forward (container host, pgmq vs. Redis)

**Pros**:

- ✅ Solves the credential and deployment question "for real," once, instead of twice.

**Cons**:

- ❌ Conflates an urgent, narrowly-scoped fix with a large, deliberately deferred
  infrastructure decision the roadmap gates behind R1 (full) and R2 for solo-operator
  bandwidth reasons; over-scopes this ADR and risks stalling it.

## Consequences

### Positive

- ✅ RLS becomes real enforcement instead of a comment describing a hypothetical.
- ✅ The generation pipeline is testable end-to-end from this repo alone (`docker-compose
  up`), not contingent on `homelab-infra`'s state matching expectations.
- ✅ A stopped or misconfigured worker becomes visible within the existing stale-job
  threshold instead of failing silently.
- ✅ The ADR-009 pool-sizing debt item closes as a side effect.

### Trade-offs

- ⚠️ Two service-account passwords to manage per environment instead of one. Mitigation:
  identical grant sets initially, so this is one extra secret, not a second policy surface
  to maintain.
- ⚠️ `worker_database_url` defaulting to `database_url` means an operator who never
  explicitly sets the new variable silently keeps single-role behavior. Acceptable because
  it's non-breaking, but should be checked explicitly at the M4.1/M5 hardening review so it
  isn't forgotten.

### Technical Debt

- Per-role privilege tightening (does `cyo_worker` need write access to `user`/`family` at
  all?) is deferred until real query patterns are observed under the split.
- This ADR does not decide the Phase 9 container host or queue vendor; both roles and the
  worker service definition here should be reparented onto whatever P9-03 chooses, not
  treated as that decision.

## Implementation

### Components Affected

1. **`supabase/migrations/<ts>_create_service_roles.sql`**: `CREATE ROLE cyo_api NOLOGIN`,
   `CREATE ROLE cyo_worker NOLOGIN`, `GRANT` statements against the 19-table list already
   named in `20260711200745_enable_rls_all_tables.sql`. No passwords in this file.
2. **`supabase/migrations/<ts>_add_service_role_policies.sql`**: `CREATE POLICY` per table
   for `cyo_api`/`cyo_worker` (e.g. `FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK
   (true)`, matching the app-owns-authorization posture ADR-009 decision point 7 already
   established).
3. **`core/config.py`**: add `worker_database_url` (defaults to `database_url`),
   `database_pool_size`, `database_max_overflow`.
4. **`core/database.py`**: add `get_worker_engine()` / `get_worker_session()`; pass the new
   pool settings into both engines; preserve the existing `disable_prepared_cache` branch
   for whichever engines run through the transaction pooler.
5. **`generation/worker.py`, `generation/worker_main.py`, `covers/worker.py`**: switch to
   `get_worker_session()`.
6. **`docker-compose.yml` / `docker-compose.prod.yml`**: add a `worker` service (same
   image, `worker_main` command); uncomment Redis in the dev file.
7. **`api/health.py`** (or a new small admin endpoint): stale-`GenerationJob` count check
   against `_DEFAULT_STALE_AFTER`.
8. **`docs/operations/runbook.md`**: update the two sections that already document this gap
   (worker not in `docker-compose.yml`; stranded-job sweep only runs on worker start) to
   point at the new in-repo service and staleness check.
9. **Passwords**: set once per environment (staging, production) via the Supabase dashboard
   SQL editor or CLI `--var` substitution, stored in the existing GitHub Actions
   secrets / `homelab-infra` secret store — never in a migration file or this repo's `.env*`
   examples beyond a placeholder.

### Testing Strategy

- Unit: extend `tests/unit/test_database.py` to cover the second engine/session factory and
  pool-setting plumbing.
- Integration: a new test proving `cyo_api`/`cyo_worker` can perform the exact CRUD the
  pipeline needs under RLS, and that `anon`/`authenticated` remain denied — the regression
  guard against the "policies missing" landmine this ADR closes.
- CI: `supabase-ci.yml` already applies the full migration chain to a fresh local stack on
  every PR touching `supabase/`, catching ordering/syntax errors in the new migrations.
- Staging rehearsal before the production `workflow_dispatch`, per ADR-012's existing
  forward-only process.

## Validation

### Success Criteria

- [ ] `cyo_api` and `cyo_worker` exist in staging and production with distinct passwords;
      no application traffic still connects as `postgres`.
- [ ] A test proves default-deny holds for `anon`/`authenticated` and explicit-allow holds
      for `cyo_api`/`cyo_worker`.
- [ ] `docker-compose up` in this repo alone exercises story request → generation → review
      queue end to end, with no dependency on `homelab-infra` to verify the pipeline.
- [ ] A stopped worker is visible via the staleness check within 30 minutes, not silently.
- [ ] `database_pool_size`/`database_max_overflow` are set explicitly (closes the ADR-009
      `#CRITICAL` item).

### Review Schedule

- Initial: M4.1 (R1-alpha sign-off) — this affects whether the core loop is trustworthy in
  the environment M4.1 is signing off on.
- Ongoing: revisit at Phase 9 start, when P9-03 makes the final hosted-infra call; the
  role/RLS model here should persist, just reparented onto whatever container host and
  queue P9-03 selects.

## Related

- [ADR-009](./adr-009-supabase-platform.md): the platform decision this amends (compute
  and authorization-model clauses only; auth and Postgres-hosting decisions stand).
- [ADR-012](./adr-012-supabase-cli-migrations.md): the migration mechanics (forward-only,
  CLI-applied SQL) this decision's migrations follow.
- [ADR-005](./adr-005-mandatory-human-approval.md): the guarantee this ADR closes a
  silent-failure path for (a story can't be approved or rejected if it never reaches a
  human because the worker isn't running).
- [ADR-007](./adr-007-raw-output-retention.md): precedent for a pg_cron-adjacent
  maintenance job, relevant if the staleness check becomes a scheduled job rather than a
  request-time health check.
- `docs/operations/runbook.md`: the operational gap this ADR resolves is already documented
  there; that document should be updated alongside implementation.
