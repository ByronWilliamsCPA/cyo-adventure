---
title: "ADR-012: Supabase CLI SQL migrations replace Alembic"
schema_type: planning
status: accepted
owner: core-maintainer
purpose: "Record the decision to retire Alembic in favor of Supabase CLI SQL migrations
  as the schema source of truth, squashed from the Alembic head into a single baseline."
tags:
  - planning
  - architecture
  - decisions
  - infrastructure
---

# ADR-012: Supabase CLI SQL migrations replace Alembic

> **Status**: Accepted (2026-07-10)
> **Date**: 2026-07-10
> **Supersedes**: the migration-tooling clause of [ADR-009](./adr-009-supabase-platform.md)
> (Decision point 2 there said "Alembic unchanged on Supabase"; the auth and Postgres-hosting
> decisions in ADR-009 stand)

## TL;DR

Retire Alembic. `supabase/migrations/*.sql` plus the pinned Supabase CLI is the schema
source of truth going forward. A single squash migration, `20260710000000_baseline.sql`,
was generated via `supabase db dump` from a Postgres 16 instance built by the full
Alembic chain, so the pre-cutover history is preserved as one file rather than replayed
migration by migration. Migrations are forward-only: PR validation applies the chain to a
fresh local stack, merge to `main` deploys staging automatically, and production is a
human-approved `workflow_dispatch`.

## Context

### Problem

ADR-009 kept Alembic unchanged when the project moved its database onto Supabase
Postgres: "async SQLAlchemy and Alembic migrations unchanged." That worked while Alembic
ran against a plain Postgres connection string, but it duplicated the CLI's own migration
model (Supabase projects, staging branches, and the hosted dashboard all assume
`supabase/migrations/*.sql` as the schema history) and left two migration systems
disagreeing about which one owned the schema.

### Constraints

- **Technical**: the CLI applies plain SQL; there is no Python migration DSL to port, so
  the cutover is a squash-and-replace, not a line-by-line translation of Alembic's
  `upgrade()`/`downgrade()` pairs.
- **Operational**: a solo operator cannot maintain two migration tools in parallel
  without one silently drifting from the other.
- **Regulatory**: none beyond the existing data-integrity posture; no PII schema changes
  are introduced by the cutover itself.

### Significance

This decision changes how every future schema change ships: a plain SQL file under
`supabase/migrations/` reviewed in a normal PR, rather than an Alembic revision generated
by `alembic revision --autogenerate`.

## Decision

**`supabase/migrations/*.sql` applied by the pinned Supabase CLI is the schema source of
truth; Alembic is retired.**

1. **Baseline squash**: `supabase/migrations/20260710000000_baseline.sql` was generated
   via `supabase db dump` from a Postgres 16 instance that Alembic had built to its head,
   so the file is the full schema as of the cutover, not a re-derivation from the ORM
   models. `alembic.ini` and `migrations/` (the Alembic environment) are deleted.
2. **Promotion path**: `supabase-ci.yml` validates the migration chain against a fresh
   local stack (`supabase db start` + `supabase migration up`) on every PR touching
   `supabase/`; `supabase-staging.yml` runs `supabase db push` automatically on merge to
   `main`; `supabase-production.yml` runs the same push only on a human-approved
   `workflow_dispatch`.
3. **Forward-only**: no downgrade scripts. Recovery from a bad migration is roll-forward
   (a corrective migration), rehearsed on staging before it reaches the approved
   production dispatch. A destructive data migration must document a manual recovery
   note in a leading SQL comment.
4. **Drift guard**: `tests/integration/test_schema_parity.py` replaces `alembic check`;
   it fails CI when the schema produced by the migration chain and `Base.metadata`
   disagree on tables, constraints, and indexes.

## Options Considered

### Option 1: Supabase CLI SQL migrations, Alembic retired ✓

**Pros**:

- One migration system, matching how the CLI, staging branches, and the hosted
  dashboard already model schema history.
- Plain SQL is directly reviewable and directly portable to any Postgres via `psql`; no
  Python tooling required to read or replay it.

**Cons**:

- Downgrade scripts are gone; recovery is roll-forward only (accepted, see Consequences).
- `supabase db dump`/`db push` behavior under a non-TLS local target required a
  workaround (see Notes).

### Option 2: Keep Alembic, treat Supabase CLI migrations as a mirror

**Pros**:

- No squash risk; Alembic's autogenerate diffing stays available.

**Cons**:

- Two systems must agree forever; the exact drift risk this ADR exists to remove.

### Option 3: Keep Alembic only, never adopt the CLI's migration model

**Pros**:

- Zero migration-tooling change.

**Cons**:

- Fights the platform: Supabase's staging branches and dashboard schema diff assume
  `supabase/migrations/*.sql` exists and is current.

## Consequences

### Positive

- One schema history, one CLI, matching the platform's own model.
- The drift guard (`test_schema_parity.py`) is a behavioral test in the existing suite
  rather than a separate `alembic check` invocation, so it runs in the same CI job as
  everything else.

### Trade-offs

- ⚠️ **Downgrade coverage is deliberately lost.** Every Alembic migration paired
  `upgrade()` with `downgrade()`; the SQL migrations here do not. Roll-forward plus a
  staging rehearsal on every migration before production replaces it. This is an
  accepted trade, not an oversight: forward-only is the CLI's own model and fighting it
  with hand-written down-migrations would reintroduce the two-systems drift risk this
  ADR removes.
- ⚠️ **Ejection path changed.** ADR-009 named Postgres plus Alembic as the low-risk
  ejection path off Supabase ("plain Postgres... ejection is a migration, not a
  rewrite"). Post-ADR-012 the ejection path is "plain SQL applied by `psql`" instead of
  "Alembic against any Postgres." This is narrower (no Python migration tool needed) but
  loses Alembic's per-revision autogenerate diffing if a future non-Supabase Postgres
  needs a schema change authored without the CLI present.
- ⚠️ The `pipeline_event` append-only trigger (`BEFORE UPDATE OR DELETE` raising an
  exception) exists only in migration SQL, not in SQLAlchemy `Base.metadata`, because
  ORM metadata has no portable trigger representation. `test_schema_parity.py` compares
  tables, constraints, and indexes but does not inspect triggers, so this behavior needs
  its own dedicated tests rather than relying on the parity gate:
  `tests/integration/test_pipeline_event_append_only.py` exercises the trigger directly
  (attempted `UPDATE`/`DELETE` against a `pipeline_event` row both raise).

### Technical Debt

- None identified beyond the accepted downgrade-coverage loss above.

## Implementation

### Components Affected

1. **`supabase/migrations/`**: `20260710000000_baseline.sql` (squash) plus
   `20260711031627_drop_alembic_version.sql` (drops Alembic's own `alembic_version`
   bookkeeping table once the cutover is confirmed).
2. **CI/CD**: `.github/workflows/supabase-ci.yml` (PR validation, non-required
   initially), `supabase-staging.yml` (auto-deploy on merge to `main`), and
   `supabase-production.yml` (human-approved `workflow_dispatch`). All three pin the CLI
   via `supabase/setup-cli@46f7f98c7f948ad727d22c1e67fab04c223a0520 # v3.0.0` at
   `version: 2.109.1`.
3. **`ci.yml`**: the `api-tests` job's migrate step now runs `supabase db push` instead
   of `alembic upgrade head`.
4. **Deleted**: `alembic.ini`, `migrations/` (Alembic environment and versions).
5. **`tests/integration/test_schema_parity.py`**: the drift guard, comparing the schema
   produced by `supabase/migrations/*.sql` against `Base.metadata`.

### Notes (implementation facts worth preserving)

- **CLI version**: pinned to `2.109.1` via `supabase/setup-cli`, itself pinned by SHA
  (`46f7f98c7f948ad727d22c1e67fab04c223a0520`, tag `v3.0.0`).
- **Baseline generation**: `20260710000000_baseline.sql` was produced with
  `supabase db dump`, pointed at a Postgres 16 instance that the (still-present at the
  time) Alembic chain had built to its head. This captures the real, applied schema
  rather than a re-derivation from `Base.metadata`, which matters because ORM metadata
  and the actually-applied schema can diverge (the `pipeline_event` trigger being the
  clearest example, see Consequences above).
- **TLS gotcha**: CLI `2.109.1`'s `db push`/`db dump` use `pgx`, which attempts a TLS
  handshake against any `--db-url` target and ignores a `?sslmode=disable` query
  parameter on that URL; there is no in-URL fallback to plain connections. Against the
  plain, non-TLS local/CI Postgres target, the workaround is the standard libpq
  environment variable `PGSSLMODE=disable` set on the step, not the URL query parameter.
  This is why `ci.yml`'s migrate step and local-dev instructions both set
  `PGSSLMODE=disable` ahead of `supabase db push --db-url ...`.
- **Trigger-only behavior**: see the `pipeline_event` bullet under Consequences; it is
  called out here again because it is the concrete reason the parity gate could not be
  the only test for this migration.

### Testing Strategy

- `tests/integration/test_schema_parity.py`: schema-vs-`Base.metadata` drift gate.
- `tests/integration/test_pipeline_event_append_only.py`: dedicated behavioral coverage
  for the append-only trigger the parity gate cannot see.
- `supabase-ci.yml`: applies the full migration chain to a fresh local stack on every PR
  touching `supabase/`, catching syntax errors and ordering problems before merge.

## Validation

### Success Criteria

- [x] Full Alembic history squashed into `20260710000000_baseline.sql` without schema
      loss (verified against the Alembic-built Postgres 16 instance via `supabase db
      dump`).
- [x] `alembic.ini` and `migrations/` removed from the repository.
- [x] CI applies the migration chain to a fresh stack on every PR touching `supabase/`.
- [x] Staging deploys automatically on merge to `main`; production requires an approved
      `workflow_dispatch`.
- [ ] A real roll-forward recovery (not just a rehearsal) has not yet been exercised in
      production; revisit after the first corrective migration ships.

### Review Schedule

- Initial: this cutover (2026-07-10).
- Ongoing: revisit if the Supabase CLI's TLS handling changes (the `PGSSLMODE=disable`
  workaround could become unnecessary in a future CLI release) or if a non-Supabase
  Postgres ejection is planned (re-evaluate the narrowed ejection path noted above).

## Related

- [ADR-009](./adr-009-supabase-platform.md): the platform decision this amends
  (migration-tooling clause only; auth and Postgres-hosting decisions stand).
- [ADR-004](./adr-004-homelab-first-deployment.md): homelab remains dev/family staging;
  the same plain-SQL migrations apply there via `supabase db push` against the homelab
  Postgres.
- `TECHNICAL_BASELINE.md`: version pin and migration convention record.
