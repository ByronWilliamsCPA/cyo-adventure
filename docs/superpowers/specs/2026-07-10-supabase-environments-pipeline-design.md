---
schema_type: common
title: "Supabase Multi-Environment Pipeline: Full CLI Transition"
status: draft
owner: core-maintainer
purpose: "Adopt the Supabase managing-environments structure (local CLI stack, staging project, gated production) with Supabase CLI SQL migrations replacing Alembic as the schema source of truth."
tags:
  - deployment
  - planning
---

## Problem

The app runs against a single Supabase Cloud project that holds real family data
and serves the live site (`cyo.williamshome.family`). There is no staging
environment, no local Supabase stack, and no automated migration promotion:
schema changes are applied by hand-running `alembic upgrade head` against
whichever database is targeted. Two consequences forced this work:

1. Naive-UX testing (and any other credentialed testing) has nowhere safe to
   run; it currently risks mixing test noise into real family data
   (`docs/superpowers/specs/2026-07-10-naive-ux-check-scenario-redesign-design.md`,
   Section C).
2. Migration promotion has no rehearsal step: the first database a new
   migration meets outside CI's throwaway Postgres is production.

Supabase's managing-environments guide
(<https://supabase.com/docs/guides/deployment/managing-environments>) outlines
the target structure: a CLI-run local stack, a staging project, a production
project, and branch-driven migration promotion via GitHub Actions.

## Decisions (ratified 2026-07-10)

1. **Full Supabase CLI migrations.** The schema source of truth moves from
   Alembic to `supabase/migrations/*.sql`. Alembic is retired entirely. This
   supersedes the migration-tooling clause of ADR-009 and requires a new ADR
   (ADR-012). The ejection path changes shape rather than disappearing: plain
   SQL migration files remain applicable to any Postgres via `psql`; only the
   runner is Supabase's CLI.
2. **main -> staging, human-gated production.** No `develop` branch. Merging to
   `main` auto-deploys migrations to staging. Production promotion is an
   explicit `workflow_dispatch` bound to a GitHub Environment with
   required-reviewer approval. The merge queue, semantic-release, and Portainer
   GitOps triggers are untouched.
3. **Existing project = production; one new staging project.** The current
   live project is formally designated production. The user creates one new
   Supabase Cloud project as staging (dashboard action; free plan allows two
   projects). No data migration.
4. **Staging seeding is in scope.** The test guardian, test admin, and one
   age-band 5-8 child profile from the naive-ux spec are seeded here, so the
   delayed agent redesign finds staging ready.
5. **Cutover strategy: squash baseline (Approach 1).** One baseline SQL
   migration generated from the current Alembic-head schema; Alembic deleted in
   the same workstream; production never re-runs the baseline (it is marked
   applied via `supabase migration repair`).

## Goals

1. Three working tiers: local (`supabase start`), staging (new Cloud project),
   production (existing project), all built from one migration history.
2. Automated, rehearsed promotion: every migration lands on a fresh local
   stack (PR CI), then staging (merge to main), then production (approved
   dispatch), in that order.
3. Alembic fully retired with no loss of the model-drift guard it provided.
4. Staging seeded with disposable test credentials for future credentialed
   testing.

## Non-goals

- **Not redesigning the naive-ux-check skill or scenarios.** That work is
  deliberately delayed until this pipeline exists; its spec gets a status
  banner pointing here (see Follow-ups).
- **Not fixing issue #196's UI.**
- **Not adopting Supabase Branching (the paid preview feature).** The staging
  tier is a plain second project, per the guide's core pattern.
- **Not moving local auth off the `ENVIRONMENT=local` dev stub.** The local
  stack's Auth service becomes available for full-flow testing, but nothing in
  this pass requires it.
- **Not introducing RLS or changing how the app connects to Postgres** (direct
  or session-mode per ADR-009 Task 1.7 remains).

## Design

### 1. Environment topology

| Tier | Backing | Schema applied by |
| --- | --- | --- |
| Local | `supabase start` stack (Postgres `:54322`, Auth, Studio `:54323`) | `supabase db reset` / `supabase migration up` |
| Staging | New Supabase Cloud project | `supabase-staging.yml` on merge to `main` |
| Production | Existing live project | `supabase-production.yml`, `workflow_dispatch` + required-reviewer GitHub Environment |

Local dev's canonical database becomes the CLI stack. The docker-compose `db`
service stays (CI's newman job and containerized dev use it) but receives its
schema from the same SQL migrations via `supabase db push --db-url`, keeping a
single schema source.

### 2. Repository layout

```text
supabase/
  config.toml                  # local stack + auth config as code
  migrations/
    <ts>_baseline.sql          # squash of current Alembic-head schema
.env.staging.example           # committed template; .env.staging is git-ignored
scripts/seed_staging.py        # NEW: Supabase Auth users via admin API + DB fixtures
```

`supabase/seed.sql` stays unused. Seeding remains in Python:
`scripts/seed_dev_data.py` for local (unchanged), `scripts/seed_staging.py`
for staging (new), because fixtures need ORM logic and Auth-admin-API calls
that plain SQL cannot express.

### 3. Migration authoring workflow (post-cutover)

1. `supabase migration new <name>` -- hand-write SQL, or prototype in local
   Studio and capture with `supabase db diff -f <name>`.
2. `supabase db reset` locally to prove the chain applies from scratch.
3. Update the SQLAlchemy models to match.
4. The schema-parity test (Section 4) fails CI if models and migrations
   disagree.

Migrations are **forward-only**: no downgrade scripts. Recovery is
roll-forward, rehearsed on staging before production ever sees a migration.
TECHNICAL_BASELINE's migration-reversibility policy is rewritten to this
effect.

### 4. Drift guard replacing `alembic check`

A new integration test applies all `supabase/migrations/*.sql` files (in
lexicographic order) to one throwaway database and `Base.metadata.create_all`
to another, then diffs tables, columns, types, nullability, primary keys,
foreign keys, uniques, and indexes via SQLAlchemy's Inspector. Any mismatch is
a test failure naming the divergent object. This runs in the normal pytest
integration suite.

The 11 Alembic round-trip test files and
`tests/integration/_migration_utils.py` are deleted with Alembic. Their
data-preservation intent (upgrade/downgrade with rows in place) is only
partially inherited: the staging rehearsal step covers "applies to a database
with real data", but automated downgrade coverage is lost by design with the
move to forward-only migrations. This loss is accepted and documented in
ADR-012.

### 5. CI/CD workflows

- **`ci.yml` (edit):** in the api-tests job, replace the
  `uv run alembic upgrade head` step with: install Supabase CLI
  (`supabase/setup-cli` action, pinned), then
  `supabase db push --db-url postgresql://cyo_adventure:password@localhost:5432/cyo_adventure`.
  The `seed_dev_data.py` step is unchanged. A migration-validation step (fresh
  `supabase db start` + apply) guards PRs that touch `supabase/migrations/**`.
- **`supabase-staging.yml` (new):** trigger `push` to `main` with path filter
  `supabase/migrations/**`; steps: checkout, setup-cli,
  `supabase link --project-ref $SUPABASE_PROJECT_ID`, `supabase db push`.
  Secrets (`SUPABASE_ACCESS_TOKEN`, `SUPABASE_PROJECT_ID`,
  `SUPABASE_DB_PASSWORD`) come from a `staging` GitHub Environment.
- **`supabase-production.yml` (new):** trigger `workflow_dispatch`; the job is
  bound to a `production` GitHub Environment configured with required-reviewer
  approval; same steps against the production project's secrets. The dispatch
  instructions require a green staging deploy for the same migration set
  before running.

### 6. Cutover sequence

User-gated checkpoints are marked with (GATE); everything else is agent work
in stacked PRs off `main`.

1. **PR-1 (additive, Alembic untouched):** `supabase/` scaffold with
   `config.toml`; baseline migration generated from the Alembic-head schema;
   PR migration-validation CI; `supabase-staging.yml` and
   `supabase-production.yml`; developer docs for the new local workflow.
2. **(GATE) Staging provisioning:** the user creates the staging project in
   the Supabase dashboard and sets the GitHub Environments and secrets. The
   staging workflow then pushes the baseline to staging.
3. **PR-2 (retirement):** delete `migrations/`, `alembic.ini`, the 11
   round-trip tests and `_migration_utils.py`; drop `alembic` from the `api`
   extra; rewrite the ci.yml step; add the schema-parity test; update
   TECHNICAL_BASELINE.md, CLAUDE.md, REUSE.toml, `docs/api/README.md`, and the
   r1 checklist reference; write ADR-012 (supersedes ADR-009's migration
   clause).
4. **(GATE) Production adoption:** with the user present and the nightly
   pg_dump backup verified fresh, run
   `supabase migration repair --status applied <baseline>` against production
   (metadata-only write to `supabase_migrations.schema_migrations`; the
   baseline never executes there), and set production secrets.
5. **PR-3 (seeding):** `scripts/seed_staging.py` (idempotent; creates the two
   Supabase Auth users via the admin API and the family/child-profile rows via
   the ORM), `.env.staging.example`, and a run of the seed against staging.
   Staging's generation provider defaults to Ollama so test runs place no
   billed LLM calls.

### 7. Error handling and risks

- **Failed staging push:** blocks production by convention; the production
  workflow's run instructions require a green staging run for the same
  migrations, and the required-reviewer gate is the hard stop.
- **`migration repair` on production** is the single risky manual step. It is
  metadata-only, performed at the gate with the user, after verifying the
  nightly backup.
- **Free-plan staging pauses** after roughly a week of inactivity; the runbook
  documents the dashboard unpause step.
- **Model/migration drift** is caught by the parity test (Section 4) rather
  than by review vigilance.
- **Baseline fidelity:** the baseline SQL is generated from a database built
  by the real Alembic chain (not `create_all`), then verified by the parity
  test, so historical migration quirks (server defaults, constraint names)
  survive the squash.

## Follow-ups (filed, not designed here)

1. Amend
   `docs/superpowers/specs/2026-07-10-naive-ux-check-scenario-redesign-design.md`
   with a status banner: its Section C (hand-provisioned staging, no CLI) is
   superseded by this pipeline; the scenario redesign itself remains pending
   and resumes on top of this staging environment.
2. File an issue for the delayed naive-ux-check scenario redesign referencing
   both specs.
3. Consider Supabase config-as-code push (`supabase config push`) for remote
   auth settings once the CLI feature is stable enough to trust.
