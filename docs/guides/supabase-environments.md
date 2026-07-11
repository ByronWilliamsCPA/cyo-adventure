---
title: "Supabase Multi-Environment Pipeline: Operator Runbook"
schema_type: common
status: published
owner: core-maintainer
purpose: "Operator runbook for the local / staging / production Supabase environment topology and its CLI-driven migration pipeline (ADR-012)."
tags:
  - deployment
  - guide
  - infrastructure
---

This is the day-to-day and one-time-setup reference for the Supabase multi-environment
pipeline. It covers three tiers built from one migration history: a local `supabase start`
stack, a staging Cloud project, and the production Cloud project, with schema promoted by
GitHub Actions rather than by hand-running a migration tool against whichever database is
targeted. See
`docs/superpowers/specs/2026-07-10-supabase-environments-pipeline-design.md` for the full
design rationale; this document is the operational how-to.

## 1. Environment topology

| Tier | Backing | Schema applied by |
| --- | --- | --- |
| Local | `supabase start` stack (Postgres `:54322`, Auth, Studio `:54323`) | `supabase db reset` / `supabase migration up` |
| Staging | New Supabase Cloud project | `Deploy Supabase Migrations (staging)` on merge to `main` |
| Production | Existing live project | `Deploy Supabase Migrations (production)`, `workflow_dispatch` + required-reviewer GitHub Environment |

The docker-compose `db` service used by the `api-tests` (newman) CI job stays; it receives its
schema from the same `supabase/migrations/*.sql` files via `supabase db push --db-url`, so
there is a single schema source across every tier, including that compose service.

## 2. Local development

Install the pinned Supabase CLI (2.109.1). The release tarball contains two binaries,
`supabase` and `supabase-go`; extracting only `supabase` breaks `supabase start` (it shells
out to `supabase-go` for some local-stack operations), so extract both into the same
directory on your `PATH`:

    curl -fsSL "https://github.com/supabase/cli/releases/download/v2.109.1/supabase_linux_amd64.tar.gz" \
      | tar -xz -C ~/.local/bin

On macOS or Windows, `brew install supabase/tap/supabase` or `scoop install supabase` install
the same pinned-compatible releases without the manual tarball step; pin the version
explicitly if the package manager does not default to 2.109.1.

Confirm the install; it must print `2.109.1`:

    supabase --version

Start the local stack from the repository root:

    supabase start
    supabase db reset

`supabase start` brings up Postgres, GoTrue (Auth), and Studio in Docker containers.
`supabase db reset` drops and recreates the local database, then applies every migration in
`supabase/migrations/` in order, starting from the baseline
(`supabase/migrations/20260710000000_baseline.sql`).

Local stack ports:

| Service | Port |
| --- | --- |
| Postgres | 54322 |
| API (GoTrue, PostgREST, Storage) | 54321 |
| Studio | 54323 |

Point the backend at the local stack:

    CYO_ADVENTURE_DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres

The docker-compose `db` service (port 5432, used by the containerized dev stack and the
`api-tests` newman job) remains in place; it is a separate Postgres instance from the CLI
stack above and is not affected by `supabase start`.

## 3. Authoring a migration

Migrations are forward-only: there are no downgrade scripts. Recovery from a bad migration is
roll-forward (a new migration that corrects the previous one), rehearsed on staging before
production ever sees it.

1. Create a new migration file:

       supabase migration new <slug>

   or capture schema changes made interactively in local Studio:

       supabase db diff -f <slug>

2. Prove the full chain applies cleanly from scratch:

       supabase db reset

3. Update the SQLAlchemy models in `src/cyo_adventure/db/models.py` (or the relevant module)
   to match the new schema.
4. The schema-parity integration test (`tests/integration/test_schema_parity.py`) fails CI if
   the SQLAlchemy models and the applied migration chain disagree (mismatched tables, columns,
   types, nullability, primary keys, foreign keys, uniques, or indexes). Fix the drift before
   the PR can merge.

Any PR that touches `supabase/migrations/**` also triggers **Supabase Migrations CI**
(`.github/workflows/supabase-ci.yml`), which starts a fresh local stack and applies the
migration chain (`supabase db start` + `supabase migration up`) to catch a broken chain before
merge.

## 4. Promotion

Promotion is a one-way ratchet: local, then staging, then production, in that order.

1. Merge a PR containing new migrations to `main`. **Deploy Supabase Migrations (staging)**
   (`.github/workflows/supabase-staging.yml`) triggers automatically on `push` to `main` when
   the change touches `supabase/migrations/**`, links the staging project, and runs
   `supabase db push` against it.
2. Confirm the staging workflow run is green before promoting further.
3. Dispatch **Deploy Supabase Migrations (production)**
   (`.github/workflows/supabase-production.yml`) manually (`workflow_dispatch`) once staging is
   green for the same migration set. The job is bound to the `production` GitHub Environment,
   which requires an approving reviewer before the job runs; this is the human gate between a
   rehearsed migration and the live database.

## 5. One-time setup (Gate A / Gate B checklist)

These steps run once, with the user present, before the pipeline can move schema anywhere
but the local stack:

- [ ] **Create the staging project** in the Supabase dashboard (a new Cloud project; the
      free plan allows two projects, and the existing live project remains production).
- [ ] **Create GitHub Environments** named `staging` and `production` under the repository's
      Settings -> Environments. Configure `production` with a required-reviewer protection
      rule; `staging` needs no reviewer gate (it deploys automatically on merge to `main`).
- [ ] **Set three secrets per environment** (`staging` and `production`, six secrets total):
  - `SUPABASE_ACCESS_TOKEN`
  - `SUPABASE_PROJECT_ID`
  - `SUPABASE_DB_PASSWORD`
- [ ] **Adopt production onto the migration chain.** With the nightly `pg_dump` backup
      verified fresh, run against production:

        supabase migration repair --status applied 20260710000000

      This is a metadata-only write to `supabase_migrations.schema_migrations`; the baseline
      migration's SQL never executes against production (the schema it describes already
      exists there). Only after this step can `supabase db push` promote future migrations to
      production without attempting to replay the baseline.

## 6. Operations

- **Free-plan staging pauses** after roughly a week of inactivity. If the staging deploy
  workflow fails with a connection error, check the Supabase dashboard for a paused-project
  banner and unpause it there before re-running the workflow.
- **Recovery is roll-forward.** There is no downgrade path; a bad migration is corrected by
  authoring and promoting a new migration, not by reverting the old one in place.
- **Backups** are nightly `pg_dump` (application-level) plus Supabase's built-in
  point-in-time recovery (PITR) on the Cloud projects. Verify the nightly `pg_dump` is fresh
  before the Gate B production-adoption step above; PITR is the fallback for anything the
  dump misses.
- **Failed staging push blocks production by convention**, not by a technical lock: the
  production workflow's run instructions require a green staging run for the same migration
  set, and the required-reviewer approval on the `production` GitHub Environment is the hard
  stop if that convention is not followed.
