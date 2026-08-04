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
| Mail UI (Inbucket) | 54324 |

The mail UI matters now that `enable_confirmations = true` applies to the local stack as well: a
locally created account cannot sign in until its confirmation link is collected from port 54324.

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

Promotion is a one-way ratchet: local, then staging, then production, in that order. Both
workflows now promote two things, not one: the migration chain and `supabase/config.toml`.
In each job the order is fixed: link the project, then `supabase config push`, then
`supabase db push`.

1. Merge a PR containing new migrations, a config.toml change, or both to `main`. **Deploy
   Supabase Migrations (staging)** (`.github/workflows/supabase-staging.yml`) triggers
   automatically on `push` to `main` when the change touches `supabase/migrations/**` or
   `supabase/config.toml`, links the staging project, runs `supabase config push`, then runs
   `supabase db push` against it. A config-only change still runs `db push`; with no new
   migrations pending, that step is a no-op.
2. Confirm the staging workflow run is green before promoting further.
3. Dispatch **Deploy Supabase Migrations (production)**
   (`.github/workflows/supabase-production.yml`) manually (`workflow_dispatch`) once staging is
   green for the same migration and config set. The job is bound to the `production` GitHub
   Environment, which requires an approving reviewer before the job runs; this is the human gate
   between a rehearsed change and the live database. This gate is unchanged by config push: it
   still applies to the whole job, config included.

### Promoting a config.toml change

`supabase config push` (CLI 2.109.1) **writes five surfaces**, in this fixed order. Each one is
gated twice: by a precondition in the config file, and then by a diff against the remote. The
"snapshot endpoint" column is what section 4's recovery procedure captures, and it is the same
endpoint the CLI itself reads to compute the diff.

| Surface | What it covers | Writes only when | Snapshot `GET`, under `/v1/projects/<ref>/` |
| --- | --- | --- | --- |
| API | PostgREST exposed schemas, search path, max rows | always attempted | `postgrest` |
| DB | `db.settings`, raw Postgres server config | always attempted | `config/database/postgres` |
| DB | network restrictions | `[db.network_restrictions] enabled`; now `false` | `network-restrictions` |
| DB | `ssl_enforcement`, a separate call | the key is present; now absent | see the Postgres row above |
| Auth | the whole `[auth]` tree | `[auth] enabled`; now `true` | `config/auth` |
| Storage | `[storage]` size limit, image transformation | `[storage] enabled`; now `true` | `config/storage` |
| Experimental | enabling database webhooks | `[experimental.webhooks] enabled`; block absent | **none exists** |

`db.settings` is raw Postgres server configuration, not pgbouncer configuration; `[db.pooler]` is
never pushed at all.

Two surfaces need their preconditions stated plainly rather than left in the table:

- **Storage is a write surface, not a read-only report.** `UpdateRemoteConfig` calls
  `UpdateStorageConfig` unconditionally, and it issues a real `PATCH` whenever `[storage] enabled
  = true`, which is this repo's value. Treat it exactly like Auth.
- **Experimental is inert here, and cannot be snapshotted.** `UpdateExperimentalConfig` does
  nothing unless an `[experimental.webhooks]` block exists with `enabled = true`, and this file
  has no such block. Its only action is a one-way `POST /v1/projects/<ref>/database/webhooks/enable`;
  the Management API exposes no corresponding `GET`, so there is no before-state to capture and no
  documented way back. Adding `[experimental.webhooks]` is therefore **out of scope for the
  recovery procedure below** and must not ride along with an unrelated config change: it needs its
  own change record stating that the enable is not reversible by this runbook.

In practice the API, DB, Storage, and Experimental surfaces are already in sync with the
dashboard, so a push whose only change is in `[auth]` moves only `[auth]`. That is an observation
about the current state of the file, not a property of the command: any surface whose precondition
holds is written the moment the file diverges from its remote.

Three properties make this a change to treat with more care than a migration:

- **It diffs, but it diffs against a fully-defaulted view of your file.** Each surface reads its
  remote config, calls `DiffWithRemote`, and returns early with `Remote <surface> config is up to
  date.` when nothing differs, so a genuine no-op push really is a no-op and says so in the log.
  What makes it dangerous is what it diffs: keys the file omits are filled with the CLI's own
  defaults first, so an omitted key whose remote value is non-default shows up as a difference and
  gets overwritten. Omitting a key does not mean "leave the remote alone"; it means "assert the
  CLI default". Deleting a key from `[auth]` is a live policy change, the same as setting it
  explicitly.
- **There is no dry run.** `config push` has no subcommand flags of its own beyond
  `--project-ref`; `--yes` is one of the CLI-wide global flags, and is required in CI because the
  CLI otherwise prompts per service. The staging rehearsal below is the closest thing to a preview
  this CLI version offers.
- **A failed push is safe to re-run.** Because each surface asserts the file's full desired state
  rather than applying a delta, re-running after a partial failure converges on the same result.
  What is never safe is re-running against a different `--project-ref`.

Per-environment values live in `[remotes.staging]` and `[remotes.production]` blocks at the
bottom of `config.toml`, keyed by `project_id`. The CLI matches `--project-ref` against those
blocks and merges the matching block over the base config; only `site_url` and
`additional_redirect_urls` differ per environment, so those are the only two fields the
`[remotes.*]` blocks carry. A successful match prints `Loading config override: [remotes.staging]`
(or `[remotes.production]`) as the first line of the run log. If that line is absent, the
override did not match and the base config went out instead, whose `site_url` is
`http://localhost:5173`.

Both deploy workflows guard this with two controls, and the distinction between them matters when
you are reading a red job:

- **Prevention, before the push.** The `Push project config` step first compares its
  `SUPABASE_PROJECT_ID` against the `project_id` declared by the matching `[remotes.*]` block in
  `config.toml`, and exits non-zero when it is empty or different. On that failure the CLI is
  never invoked, so nothing reached the project and there is nothing to restore. The comparison
  parses the TOML rather than grepping it, so a ref that appears only in a comment cannot satisfy
  it.
- **Detection, after the push.** The step then pipes the push through `tee` and greps for the
  expected `Loading config override:` line, failing the job when it is missing. This one is
  **detection, not prevention**: the push has already been applied by the time its log can be
  read, so a red job here means an incident to restore from using the snapshot procedure below.
  It is kept because it catches what the pre-flight check cannot see, namely a CLI whose
  `[remotes.*]` matching behaviour changes under a version bump.

So a failure in this step is not one condition but two, and they call for opposite responses:
check which message appeared before deciding whether a restore is needed.

Some settings stay dashboard-managed and are deliberately absent from config.toml: Google OAuth
(declaring it without a client_id and secret would push an empty client_id and break guardian
login), captcha (the `[auth.captcha]` block is a pointer in this CLI; absent means unmanaged,
whereas `enabled = false` would actively assert "off"), and `password_hibp_enabled` (no
config.toml key exists at 2.109.1, and the setting is Pro-plan-only; this org is on the free
plan, where the API call returns HTTP 402).

`[auth.sessions]` is absent for a different reason: it is simply not set yet, so adult sessions
renew indefinitely under refresh-token rotation. That is the Supabase default rather than
something this file loosened, and adding `timebox` or `inactivity_timeout` later is a live policy
change that signs adults out, so it belongs in its own rehearsed push rather than folded into an
unrelated one.

**Snapshot before any push, including a rehearsal.** Capture every surface the push can write, not
only the one you intend to change. Auth is the one that moves in practice, but a surface with no
snapshot has no documented way back, and which surface moves is decided by the diff, not by
intent. These five `GET`s cover every writable surface that the Management API can read:

    for path in \
      postgrest \
      config/database/postgres \
      network-restrictions \
      config/auth \
      config/storage
    do
      curl -sS -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
        "https://api.supabase.com/v1/projects/<ref>/$path" \
        > "snapshot-$(echo "$path" | tr / -).json"
    done

Save all five responses alongside the run they precede. If a push produces an unintended change,
restore it by `PATCH`ing the same endpoint the change landed on, with the same auth header,
sending back only the fields that moved. A snapshot taken before the push is what makes a bad push
a reversible mistake instead of an irreversible one.

The Experimental surface is the one gap, and it is bounded rather than covered: it has no `GET`,
so it cannot be snapshotted. It is also inert for this repo, because no `[experimental.webhooks]`
block exists. Those two facts have to stay true together. If a change ever adds that block, this
procedure does not cover it, and the change is not recoverable by this runbook.

**Verify a config change on staging before dispatching production.** Reading the workflow run
log is not sufficient evidence on its own, because `config push` reports success whether or not
the `[remotes.*]` override matched:

1. Snapshot all five of staging's readable surfaces with the loop above.
2. Merge the change (or dispatch the staging workflow) and let it deploy.
3. Re-fetch the same endpoints.
4. Diff the payloads field by field and confirm only the fields the config.toml change intended to
   touch actually moved.

Only once that diff is clean should the production dispatch run, itself preceded by its own
pre-push snapshot.

### Repairing an out-of-order divergence

`supabase db push` refuses to apply a migration whose filename timestamp sorts **before** the
last one already applied remotely, and reports:

    Found local migration files to be inserted before the last migration on remote database.
    Rerun the command with --include-all flag to apply these migrations:
      supabase/migrations/<file>.sql

**Staging hits this and production usually does not**, structurally rather than by accident.
Staging auto-deploys on every merge touching migrations, so it can apply a later-numbered
migration before an earlier-numbered one is merged; a PR that renumbers a migration during a
merge with `main` then lands "in the past". Production deploys by manual dispatch in ordered
batches, so it usually sees both files in one run and applies them in order. That is a property
of the dispatch cadence, not a guarantee: a production dispatch that lands between the two merges
is exposed the same way. Staging can therefore be red while production is green on the identical
migration set, which is a divergence in *applied history*, not a defect in the SQL.

To repair, dispatch **Deploy Supabase Migrations (staging)** with the `include_all` input set to
`true`. It runs `supabase db push --include-all` for that one run; every automatic deploy keeps
the ordering guard. The workflow serializes runs through the `supabase-staging-migrations`
concurrency group, so a repair dispatch queues behind an in-flight automatic deploy instead of
racing it for the same history table. Note that the `staging` GitHub Environment carries no
reviewer protection rule, so the dispatch gate is repository write access, not a second pair of
eyes: the checks below are the only thing standing between a dispatch and applied history.

**Read the remote state first.** Do not infer what staging has applied from which workflow runs
are green; a run can fail after applying some migrations, and the last *successful* run is what
bounds applied history. Two commands give the ground truth:

    supabase migration list

shows which timestamps the remote history table records, and for the constraint family below:

    select pg_get_constraintdef(oid)
    from pg_constraint
    where conname = 'ck_pipeline_event_event_type';

shows which values the remote constraint currently allows.

**Check before you dispatch.** `--include-all` is not unconditionally safe. A migration that
replaces a CHECK constraint with an absolute cumulative list (the `ck_pipeline_event_event_type`
family; see the `#CRITICAL` header in
`20260729050000_add_storybook_archived_to_pipeline_event.sql`) can drop values that are already
in the remote constraint, because each file's idempotency guard only tests for its **own** new
value. The danger condition is precise: an absolute-list migration runs **after** another
absolute-list migration for the same constraint is already in remote history, and does not carry
that other file's values. For every file named in the CLI output, confirm one of:

- its idempotency guard is already satisfied against the remote schema, so it is a true no-op
  and only the history row gets recorded; or
- it is genuinely order-independent (an additive column or index, no absolute list); or
- every absolute-list migration for that constraint is itself in the pending set, and the
  last-sorting one carries the full cumulative list. `--include-all` applies the whole pending
  set in filename order, so a later file restating the complete list overwrites any intermediate
  narrowing. Verify by diffing that file's list against the query output above plus every value
  the pending files add; do not assume it, since a pending file that sorts last but restates only
  a partial list fails this criterion.

If none holds, fix the ordering by writing a **new** migration that restates the correct
cumulative state. Never renumber or edit a migration that has already been applied anywhere:
history is forward-only per ADR-012 and there is no down script.

**Close the history gap afterwards.** A corrective migration fixes the *schema* but leaves the
skipped file permanently absent from the remote history table, so every later `db push`
re-proposes it and hits the same ordering guard. Retire it with the metadata-only write already
used in section 5, once the corrective migration has landed and the query above confirms the
schema is correct:

    supabase migration repair --status applied <skipped-timestamp>

`repair` writes a history row without executing that file's SQL, so it is correct only when the
schema state the file would have produced is already present; running it earlier records a lie.
Both `--include-all` and `repair` are one-off repair tools. A normal deploy needs neither, and
reaching for `--include-all` on successive pushes means the ordering guard is being routed around
rather than the divergence being fixed.

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
