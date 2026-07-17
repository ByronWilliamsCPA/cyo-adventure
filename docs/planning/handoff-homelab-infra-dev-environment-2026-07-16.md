---
purpose: What the homelab-infra team needs to build to support a dev frontend environment and DNS entry for pre-staging E2E testing
component: deployment, frontend, testing infrastructure
source: Frontend testing infrastructure review, 2026-07-16
---

# Handoff: dev environment support needed from homelab-infra

Written 2026-07-16, for the team operating `homelab-infra`. This documents a
concrete gap found while building out cyo-adventure's E2E testing tiers: a
`dev` environment was proposed to give more robust pre-staging testing, but
this repo has no way to build it alone, because **cyo-adventure has no
frontend deploy workflow of its own.** homelab-infra owns that entirely.
This doc is the specification of what's needed on your side.

## Why this is coming from us

`cyo-adventure`'s CI (`.github/workflows/trigger-image-build.yml`) only
dispatches a `repository_dispatch` (`cyo-adventure-push`) to
`homelab-infra` on every push to `main`; homelab-infra's own
`cyo-adventure-build.yml` is what actually builds and ships the frontend
and backend images (with a weekly scheduled build as a backstop if the
dispatch is ever missed). We have no visibility into what that receiver
does after the dispatch fires: what it deploys to, on what cadence, or
whether a `staging`-labeled frontend deployment already exists anywhere.
**First question for your team: does a staging frontend deployment already
exist today, and if so, what's its URL?** If yes, several of the items
below are already partially done and this doc just needs the remaining
pieces (see "Already expected by our CI" below). If no staging frontend
deployment exists yet, everything below is net-new.

## What we need: a `dev` frontend environment

### 1. A new DNS entry and deployment target

A subdomain (e.g. `dev.cyo-adventure.<your domain>`) serving a frontend
build, separate from whatever `production` currently serves. Doesn't need
to be highly available or backed by redundant infrastructure: it's a test
environment, disposable and reseedable.

### 2. Decoupled from the production deploy cadence

We'd like `dev` to redeploy more eagerly than production, ideally on every
merge to `main` (or close to it), so it reflects the tip of the tree for
pre-staging smoke testing. If your pipeline already distinguishes branches
or tags for deploy targets, `dev` should track `main` directly. Production
should keep whatever gate/approval process it already has; we are not
asking to change that.

### 3. Build-time environment variables for the `dev` deployment

The frontend needs these at **build** time (Vite bakes them in, they
cannot be injected at runtime):

- `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` — pointed at the
  **staging** Supabase Cloud project, not a new one. See "Why dev shares
  staging's backend" below; there is no dev-specific Supabase project to
  point at.
- `VITE_API_URL` — however your deployment resolves the backend API for
  this environment (likely relative `/api` through the same nginx proxy
  pattern the production image uses; see `frontend/nginx.conf` and
  `frontend/Dockerfile` in this repo for the existing proxy_pass
  convention via a resolver variable).

These are the same values used for whatever already serves the "staging"
label, if one exists; `dev` and `staging` are meant to be two frontend
deployments pointed at the same backend.

### Why dev shares staging's backend

cyo-adventure is on the Supabase **free plan**, which caps active projects
at two. One is production, one is staging (see
`docs/guides/supabase-environments.md` for the full three-tier topology:
local CLI stack, staging Cloud project, production Cloud project). There
is no budget for a third project, and Supabase's preview-branching feature
(which would otherwise solve this cleanly) requires the Pro plan. So `dev`
and `staging` frontend deployments must point at the **same** staging
Supabase project; they differ only in which frontend build/deployment
serves them. This is documented on our side in
`docs/testing/README.md`, along with the data-isolation approach (a
concurrency-guarded, scheduled E2E workflow using disposable seeded
fixtures from `scripts/seed_staging.py`) that assumes this shared-backend
model.

If your team later stands up Supabase Pro or an equivalent, revisit this;
proper per-environment backend isolation would be strictly better. This is
a cost-constrained workaround, not the target end state.

## Already expected by our CI (needs your URL/credentials to complete)

We've already built the cyo-adventure-side half of a **staging** E2E tier
(not `dev` yet, since dev doesn't exist): `.github/workflows/e2e-staging.yml`
runs daily plus on manual dispatch, and expects these secrets on the
`staging` GitHub Environment in the cyo-adventure repo:

| Secret | What it needs to be |
|---|---|
| `E2E_STAGING_BASE_URL` | The URL of the already-deployed staging frontend |
| `E2E_STAGING_GUARDIAN_PASSWORD` | Password for the `cyo-test-guardian@example.com` account `scripts/seed_staging.py` creates on the staging Supabase project |
| `E2E_STAGING_ADMIN_PASSWORD` | Same, for `cyo-test-admin@example.com` |

**We cannot set these ourselves** (no GitHub admin access to configure
Environment secrets from this side); someone with access to both the
staging frontend's actual URL and the `seed_staging.py` run's passwords
needs to add them. If a staging frontend deployment doesn't exist yet,
this blocks on item 1 above (just aimed at `staging` instead of `dev`,
same requirements, minus the "decoupled cadence" ask).

## Suggested order of operations

1. Confirm whether a staging frontend deployment already exists (see the
   first question above). If yes, skip to step 4.
2. Stand up the staging frontend deployment: DNS + build pointed at the
   staging Supabase project's URL/anon key.
3. Set the three secrets above on the `staging` GitHub Environment in
   cyo-adventure.
4. Confirm `.github/workflows/e2e-staging.yml` goes green on its next
   scheduled or manually-dispatched run.
5. Stand up the `dev` deployment (steps 1-3 above, `dev` subdomain, same
   Supabase pointer, faster redeploy cadence). No new E2E workflow is
   needed for `dev` immediately; it can reuse the staging tier's specs
   pointed at a different `E2E_STAGING_BASE_URL`-equivalent once it
   exists, or we can add a parallel workflow at that point.

## Reference material in this repo

- `docs/testing/README.md` — the full environment/tier model this handoff
  extends.
- `docs/testing/coverage-matrix.md` — what's tested where, useful context
  for why we're asking for this.
- `docs/guides/supabase-environments.md` — the Supabase-side topology and
  the free-plan project-count constraint.
- `.github/workflows/trigger-image-build.yml` — the existing dispatch
  mechanism into homelab-infra.
- `.github/workflows/e2e-staging.yml` — the workflow waiting on the
  secrets above.
- `frontend/Dockerfile`, `frontend/nginx.conf`, `docker-compose.prod.yml` —
  the existing production container/proxy shape to mirror for `dev`.

`#ASSUME: external-resources: this handoff assumes homelab-infra's
deployment mechanism can support an additional named environment/subdomain
without a major pipeline rework. #VERIFY: confirm with the homelab-infra
team before committing to a specific dev cadence; if their pipeline is
single-environment today, standing up dev may be a bigger lift than this
doc implies and should be scoped as its own project rather than a quick
addition.`
